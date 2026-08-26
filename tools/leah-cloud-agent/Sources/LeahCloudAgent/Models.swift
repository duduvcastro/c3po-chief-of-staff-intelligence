import Foundation

struct LeahDevice: Codable {
    let id: String
    let name: String
    let platform: String
}

struct PairRequest: Codable {
    let code: String
    let name: String
    let platform: String
}

struct PairResponse: Codable {
    let token: String
    let device: LeahDevice
}

struct LeahItem: Codable, Identifiable {
    var id: String?
    var kind: String
    var externalId: String?
    var containerId: String?
    var title: String
    var notes: String
    var startsAt: Date?
    var endsAt: Date?
    var dueAt: Date?
    var isAllDay: Bool
    var isCompleted: Bool
    var source: String
    var sourceModifiedAt: Date?
    var deletedAt: Date?

    enum CodingKeys: String, CodingKey {
        case id, kind, title, notes, source
        case externalId = "external_id"
        case containerId = "container_id"
        case startsAt = "starts_at"
        case endsAt = "ends_at"
        case dueAt = "due_at"
        case isAllDay = "is_all_day"
        case isCompleted = "is_completed"
        case sourceModifiedAt = "source_modified_at"
        case deletedAt = "deleted_at"
    }
}

struct EventOccurrence: Codable, Hashable {
    let externalId: String
    let startsAt: Date

    enum CodingKeys: String, CodingKey {
        case externalId = "external_id"
        case startsAt = "starts_at"
    }
}

struct EventSnapshotDelta {
    let added: Set<EventOccurrence>
    let removed: Set<EventOccurrence>

    static func between(
        previous: [EventOccurrence],
        current: [EventOccurrence],
        windowStart: Date,
        windowEnd: Date
    ) -> EventSnapshotDelta {
        let previousInWindow = Set(previous.filter {
            $0.startsAt >= windowStart && $0.startsAt < windowEnd
        })
        let currentSet = Set(current)
        return EventSnapshotDelta(
            added: currentSet.subtracting(previousInWindow),
            removed: previousInWindow.subtracting(currentSet)
        )
    }
}

struct LocalItemBatch {
    let items: [LeahItem]
    let eventItems: [LeahItem]
    let eventOccurrences: [EventOccurrence]
    let windowStart: Date
    let windowEnd: Date

    func syncItems(includingAdded addedOccurrences: Set<EventOccurrence>) -> [LeahItem] {
        var result = items
        var included = Set(result.compactMap(Self.eventOccurrence))
        for item in eventItems {
            guard let occurrence = Self.eventOccurrence(item),
                  addedOccurrences.contains(occurrence),
                  included.insert(occurrence).inserted else { continue }
            result.append(item)
        }
        return result
    }

    private static func eventOccurrence(_ item: LeahItem) -> EventOccurrence? {
        guard item.kind == "event", let externalId = item.externalId, let startsAt = item.startsAt else {
            return nil
        }
        return EventOccurrence(externalId: externalId, startsAt: startsAt)
    }
}

struct SyncRequest: Codable {
    let cursor: Date?
    let calendarAuthorized: Bool
    let remindersAuthorized: Bool
    let items: [LeahItem]
    let calendarSnapshot: [EventOccurrence]?
    let calendarSnapshotStart: Date?
    let calendarSnapshotEnd: Date?

    enum CodingKeys: String, CodingKey {
        case cursor, items
        case calendarAuthorized = "calendar_authorized"
        case remindersAuthorized = "reminders_authorized"
        case calendarSnapshot = "calendar_snapshot"
        case calendarSnapshotStart = "calendar_snapshot_start"
        case calendarSnapshotEnd = "calendar_snapshot_end"
    }
}

struct SyncResponse: Codable {
    let cursor: Date
    let items: [LeahItem]
}

enum LeahAgentError: LocalizedError {
    case invalidServer
    case missingToken
    case server(String)

    var errorDescription: String? {
        switch self {
        case .invalidServer: return "Endereço do C3PO inválido."
        case .missingToken: return "Este Mac ainda não está pareado."
        case .server(let message): return message
        }
    }
}
