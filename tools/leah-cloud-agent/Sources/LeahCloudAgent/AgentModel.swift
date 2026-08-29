import Foundation

@MainActor
final class AgentModel: ObservableObject {
    private static let syncSchemaVersion = 5
    private static let eventSnapshotVersion = 2
    private static let syncBatchSize = 50
    @Published var server = UserDefaults.standard.string(forKey: "server") ?? "https://c3po.eduardocastro.com.br"
    @Published var pairingCode = ""
    @Published var status = "Aguardando pareamento"
    @Published var isWorking = false
    @Published var lastSync: Date?

    private let eventKit = EventKitBridge()
    private var syncTask: Task<Void, Never>?
    private var token: String? { KeychainStore.load() }

    var isPaired: Bool { token != nil }
    var calendarAuthorized: Bool { eventKit.calendarAuthorized }
    var remindersAuthorized: Bool { eventKit.remindersAuthorized }

    init() {
        if isPaired {
            status = "Conectado ao C3PO"
            startLoop()
        }
    }

    func connect() {
        Task {
            isWorking = true
            defer { isWorking = false }
            do {
                guard let url = URL(string: server) else { throw LeahAgentError.invalidServer }
                try await eventKit.requestAccess()
                let response = try await APIClient(serverURL: url).pair(
                    code: pairingCode.replacingOccurrences(of: " ", with: ""),
                    deviceName: Host.current().localizedName ?? "Mac"
                )
                try KeychainStore.save(token: response.token)
                UserDefaults.standard.set(server, forKey: "server")
                status = "Conectado ao C3PO"
                pairingCode = ""
                await syncNow()
                startLoop()
                objectWillChange.send()
            } catch {
                status = error.localizedDescription
            }
        }
    }

    func authorizeAgain() {
        Task {
            do {
                try await eventKit.requestAccess()
                await syncNow()
                objectWillChange.send()
            } catch {
                status = error.localizedDescription
            }
        }
    }

    func syncNow() async {
        guard let token else { return }
        isWorking = true
        defer { isWorking = false }
        do {
            guard let url = URL(string: server) else { throw LeahAgentError.invalidServer }
            let storedSchemaVersion = UserDefaults.standard.integer(forKey: "syncSchemaVersion")
            let cursor = UserDefaults.standard.object(forKey: "serverCursor") as? Date
            let localCursor = UserDefaults.standard.object(forKey: "localCursor") as? Date
            let batch = await eventKit.localItems(modifiedAfter: localCursor)
            let storedEventSnapshotVersion = UserDefaults.standard.integer(forKey: "eventSnapshotVersion")
            let previousOccurrences = storedEventSnapshotVersion == Self.eventSnapshotVersion
                ? loadEventSnapshot()
                : []
            let eventDelta = EventSnapshotDelta.between(
                previous: previousOccurrences,
                current: batch.eventOccurrences,
                windowStart: batch.windowStart,
                windowEnd: batch.windowEnd
            )
            var localItems = batch.syncItems(includingAdded: eventDelta.added)
            let removedOccurrences = calendarAuthorized
                ? eventDelta.removed
                : []
            localItems += removedOccurrences.map { occurrence in
                LeahItem(
                    id: nil,
                    kind: "event",
                    externalId: occurrence.externalId,
                    containerId: nil,
                    title: "Evento removido",
                    notes: "",
                    startsAt: occurrence.startsAt,
                    endsAt: occurrence.startsAt,
                    dueAt: nil,
                    isAllDay: false,
                    isCompleted: false,
                    source: "icloud",
                    sourceModifiedAt: Date(),
                    deletedAt: Date()
                )
            }
            let needsFullCalendarSnapshot = storedEventSnapshotVersion != Self.eventSnapshotVersion
            let client = APIClient(serverURL: url)
            var nextCursor = cursor
            if storedSchemaVersion != Self.syncSchemaVersion {
                nextCursor = try await exchange(
                    client: client,
                    token: token,
                    cursor: nextCursor,
                    replayDeletedSince: .distantPast,
                    items: [],
                    calendarSnapshot: nil,
                    calendarSnapshotStart: nil,
                    calendarSnapshotEnd: nil
                )
            }

            let batches = stride(from: 0, to: localItems.count, by: Self.syncBatchSize).map {
                Array(localItems[$0..<min($0 + Self.syncBatchSize, localItems.count)])
            }
            let needsRegularExchange = storedSchemaVersion == Self.syncSchemaVersion
                || needsFullCalendarSnapshot
            let requestBatches = batches.isEmpty && needsRegularExchange
                ? [[]]
                : batches
            for (index, items) in requestBatches.enumerated() {
                let includesSnapshot = index == requestBatches.count - 1
                nextCursor = try await exchange(
                    client: client,
                    token: token,
                    cursor: nextCursor,
                    replayDeletedSince: nil,
                    items: items,
                    calendarSnapshot: calendarAuthorized && needsFullCalendarSnapshot && includesSnapshot
                        ? batch.eventOccurrences
                        : nil,
                    calendarSnapshotStart: calendarAuthorized && needsFullCalendarSnapshot && includesSnapshot
                        ? batch.windowStart
                        : nil,
                    calendarSnapshotEnd: calendarAuthorized && needsFullCalendarSnapshot && includesSnapshot
                        ? batch.windowEnd
                        : nil
                )
            }

            localItems.removeAll()
            let now = Date()
            UserDefaults.standard.set(nextCursor, forKey: "serverCursor")
            UserDefaults.standard.set(now, forKey: "localCursor")
            UserDefaults.standard.set(Self.syncSchemaVersion, forKey: "syncSchemaVersion")
            saveEventSnapshot(batch.eventOccurrences)
            lastSync = now
            status = "Sincronização ativa"
        } catch {
            status = error.localizedDescription
        }
    }

    private func exchange(
        client: APIClient,
        token: String,
        cursor: Date?,
        replayDeletedSince: Date?,
        items: [LeahItem],
        calendarSnapshot: [EventOccurrence]?,
        calendarSnapshotStart: Date?,
        calendarSnapshotEnd: Date?
    ) async throws -> Date {
        let response = try await client.sync(
            SyncRequest(
                cursor: cursor,
                replayDeletedSince: replayDeletedSince,
                calendarAuthorized: calendarAuthorized,
                remindersAuthorized: remindersAuthorized,
                items: items,
                calendarSnapshot: calendarSnapshot,
                calendarSnapshotStart: calendarSnapshotStart,
                calendarSnapshotEnd: calendarSnapshotEnd
            ),
            token: token
        )
        let acknowledgements = try eventKit.apply(response.items)
        if !acknowledgements.isEmpty {
            _ = try await client.sync(
                SyncRequest(
                    cursor: response.cursor,
                    replayDeletedSince: nil,
                    calendarAuthorized: calendarAuthorized,
                    remindersAuthorized: remindersAuthorized,
                    items: acknowledgements,
                    calendarSnapshot: nil,
                    calendarSnapshotStart: nil,
                    calendarSnapshotEnd: nil
                ),
                token: token
            )
        }
        return response.cursor
    }

    func disconnect() {
        syncTask?.cancel()
        syncTask = nil
        KeychainStore.delete()
        UserDefaults.standard.removeObject(forKey: "serverCursor")
        UserDefaults.standard.removeObject(forKey: "localCursor")
        UserDefaults.standard.removeObject(forKey: "syncSchemaVersion")
        UserDefaults.standard.removeObject(forKey: "eventSnapshot")
        UserDefaults.standard.removeObject(forKey: "eventSnapshotVersion")
        status = "Desconectado deste Mac"
        objectWillChange.send()
    }

    private func startLoop() {
        guard syncTask == nil else { return }
        syncTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.syncNow()
                try? await Task.sleep(for: .seconds(15))
            }
        }
    }

    private func loadEventSnapshot() -> [EventOccurrence] {
        guard let data = UserDefaults.standard.data(forKey: "eventSnapshot") else { return [] }
        return (try? PropertyListDecoder().decode([EventOccurrence].self, from: data)) ?? []
    }

    private func saveEventSnapshot(_ occurrences: [EventOccurrence]) {
        guard let data = try? PropertyListEncoder().encode(occurrences) else { return }
        UserDefaults.standard.set(data, forKey: "eventSnapshot")
        UserDefaults.standard.set(Self.eventSnapshotVersion, forKey: "eventSnapshotVersion")
    }
}
