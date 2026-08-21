import Foundation

@MainActor
final class AgentModel: ObservableObject {
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
            let cursor = UserDefaults.standard.object(forKey: "serverCursor") as? Date
            let localCursor = UserDefaults.standard.object(forKey: "localCursor") as? Date
            var localItems = await eventKit.localItems(modifiedAfter: localCursor)
            let response = try await APIClient(serverURL: url).sync(
                SyncRequest(
                    cursor: cursor,
                    calendarAuthorized: calendarAuthorized,
                    remindersAuthorized: remindersAuthorized,
                    items: localItems
                ),
                token: token
            )
            let acknowledgements = try eventKit.apply(response.items)
            if !acknowledgements.isEmpty {
                _ = try await APIClient(serverURL: url).sync(
                    SyncRequest(
                        cursor: response.cursor,
                        calendarAuthorized: calendarAuthorized,
                        remindersAuthorized: remindersAuthorized,
                        items: acknowledgements
                    ),
                    token: token
                )
            }
            localItems.removeAll()
            let now = Date()
            UserDefaults.standard.set(response.cursor, forKey: "serverCursor")
            UserDefaults.standard.set(now, forKey: "localCursor")
            lastSync = now
            status = "Sincronização ativa"
        } catch {
            status = error.localizedDescription
        }
    }

    func disconnect() {
        syncTask?.cancel()
        syncTask = nil
        KeychainStore.delete()
        UserDefaults.standard.removeObject(forKey: "serverCursor")
        UserDefaults.standard.removeObject(forKey: "localCursor")
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
}
