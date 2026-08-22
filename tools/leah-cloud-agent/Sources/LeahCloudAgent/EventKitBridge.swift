import EventKit
import Foundation

@MainActor
final class EventKitBridge {
    private let store = EKEventStore()

    var calendarAuthorized: Bool {
        EKEventStore.authorizationStatus(for: .event) == .fullAccess
    }

    var remindersAuthorized: Bool {
        EKEventStore.authorizationStatus(for: .reminder) == .fullAccess
    }

    func requestAccess() async throws {
        _ = try await store.requestFullAccessToEvents()
        _ = try await store.requestFullAccessToReminders()
    }

    func localItems(modifiedAfter: Date?) async -> LocalItemBatch {
        var result: [LeahItem] = []
        var eventOccurrences: [EventOccurrence] = []
        let start = Calendar.current.date(byAdding: .day, value: -30, to: Date())!
        let end = Calendar.current.date(byAdding: .day, value: 365, to: Date())!
        if calendarAuthorized {
            let predicate = store.predicateForEvents(withStart: start, end: end, calendars: nil)
            let events = store.events(matching: predicate)
            eventOccurrences = events.map {
                EventOccurrence(externalId: $0.calendarItemIdentifier, startsAt: $0.startDate)
            }
            result += events
                .filter { modifiedAfter == nil || ($0.lastModifiedDate ?? .distantPast) > modifiedAfter! }
                .map { event in
                    LeahItem(
                        id: nil,
                        kind: "event",
                        externalId: event.calendarItemIdentifier,
                        containerId: event.calendar.calendarIdentifier,
                        title: event.title ?? "Sem título",
                        notes: event.notes ?? "",
                        startsAt: event.startDate,
                        endsAt: event.endDate,
                        dueAt: nil,
                        isAllDay: event.isAllDay,
                        isCompleted: false,
                        source: "icloud",
                        sourceModifiedAt: event.lastModifiedDate,
                        deletedAt: nil
                    )
                }
        }
        if remindersAuthorized {
            let reminders = await withCheckedContinuation { continuation in
                store.fetchReminders(matching: store.predicateForReminders(in: nil)) { values in
                    continuation.resume(returning: values ?? [])
                }
            }
            result += reminders
                .filter { modifiedAfter == nil || ($0.lastModifiedDate ?? .distantPast) > modifiedAfter! }
                .map { reminder in
                    LeahItem(
                        id: nil,
                        kind: "task",
                        externalId: reminder.calendarItemIdentifier,
                        containerId: reminder.calendar.calendarIdentifier,
                        title: reminder.title ?? "Sem título",
                        notes: reminder.notes ?? "",
                        startsAt: nil,
                        endsAt: nil,
                        dueAt: reminder.dueDateComponents?.date,
                        isAllDay: reminder.dueDateComponents?.hour == nil,
                        isCompleted: reminder.isCompleted,
                        source: "icloud",
                        sourceModifiedAt: reminder.lastModifiedDate,
                        deletedAt: nil
                    )
                }
        }
        return LocalItemBatch(
            items: result,
            eventOccurrences: eventOccurrences,
            windowStart: start,
            windowEnd: end
        )
    }

    func apply(_ items: [LeahItem]) throws -> [LeahItem] {
        var acknowledgements: [LeahItem] = []
        for var item in items where item.source == "c3po" {
            if item.kind == "event", calendarAuthorized {
                let event = item.externalId.flatMap(store.event(withIdentifier:)) ?? EKEvent(eventStore: store)
                if item.deletedAt != nil {
                    if event.eventIdentifier != nil { try store.remove(event, span: .thisEvent, commit: true) }
                    continue
                }
                if event.calendar == nil { event.calendar = store.defaultCalendarForNewEvents }
                event.title = item.title
                event.notes = item.notes
                event.startDate = item.startsAt ?? Date()
                event.endDate = item.endsAt ?? event.startDate.addingTimeInterval(3600)
                event.isAllDay = item.isAllDay
                try store.save(event, span: .thisEvent, commit: true)
                item.externalId = event.calendarItemIdentifier
                item.containerId = event.calendar.calendarIdentifier
                item.sourceModifiedAt = event.lastModifiedDate
                acknowledgements.append(item)
            } else if item.kind == "task", remindersAuthorized {
                let reminder = item.externalId.flatMap { store.calendarItem(withIdentifier: $0) as? EKReminder } ?? EKReminder(eventStore: store)
                if item.deletedAt != nil {
                    if reminder.calendarItemIdentifier.isEmpty == false { try store.remove(reminder, commit: true) }
                    continue
                }
                if reminder.calendar == nil { reminder.calendar = store.defaultCalendarForNewReminders() }
                reminder.title = item.title
                reminder.notes = item.notes
                reminder.isCompleted = item.isCompleted
                if let dueAt = item.dueAt {
                    reminder.dueDateComponents = Calendar.current.dateComponents(
                        item.isAllDay ? [.year, .month, .day] : [.year, .month, .day, .hour, .minute],
                        from: dueAt
                    )
                } else {
                    reminder.dueDateComponents = nil
                }
                try store.save(reminder, commit: true)
                item.externalId = reminder.calendarItemIdentifier
                item.containerId = reminder.calendar.calendarIdentifier
                item.sourceModifiedAt = reminder.lastModifiedDate
                acknowledgements.append(item)
            }
        }
        return acknowledgements
    }
}
