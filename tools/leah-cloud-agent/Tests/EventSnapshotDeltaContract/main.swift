import Foundation

let calendar = Calendar(identifier: .gregorian)

func date(_ year: Int, _ month: Int, _ day: Int) -> Date {
    calendar.date(from: DateComponents(
        timeZone: TimeZone(secondsFromGMT: 0),
        year: year,
        month: month,
        day: day
    ))!
}

func event(startsAt: Date, sourceModifiedAt: Date) -> LeahItem {
    LeahItem(
        id: nil,
        kind: "event",
        externalId: "contact-birthday",
        containerId: "birthdays",
        title: "Aniversário de Maria",
        notes: "",
        startsAt: startsAt,
        endsAt: calendar.date(byAdding: .day, value: 1, to: startsAt),
        dueAt: nil,
        isAllDay: true,
        isCompleted: false,
        source: "icloud",
        sourceModifiedAt: sourceModifiedAt,
        deletedAt: nil
    )
}

func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
    guard condition() else { fatalError(message) }
}

let oldBirthday = date(2026, 9, 14)
let newBirthday = date(2026, 9, 15)
let windowStart = date(2026, 8, 1)
let windowEnd = date(2027, 8, 1)
let oldOccurrence = EventOccurrence(externalId: "contact-birthday", startsAt: oldBirthday)
let newOccurrence = EventOccurrence(externalId: "contact-birthday", startsAt: newBirthday)
let staleModificationDate = date(2020, 1, 1)
let newEvent = event(startsAt: newBirthday, sourceModifiedAt: staleModificationDate)
let movedBatch = LocalItemBatch(
    items: [],
    eventItems: [newEvent],
    eventOccurrences: [newOccurrence],
    windowStart: windowStart,
    windowEnd: windowEnd
)
let movedDelta = EventSnapshotDelta.between(
    previous: [oldOccurrence],
    current: [newOccurrence],
    windowStart: windowStart,
    windowEnd: windowEnd
)
let movedItems = movedBatch.syncItems(includingAdded: movedDelta.added)

expect(movedDelta.removed == [oldOccurrence], "A data antiga deve ser removida.")
expect(movedDelta.added == [newOccurrence], "A data nova deve ser adicionada.")
expect(movedItems.count == 1, "A nova ocorrência deve ser enviada uma única vez.")
expect(movedItems[0].startsAt == newBirthday, "O aniversário deve chegar no novo dia.")
expect(
    movedItems[0].sourceModifiedAt == staleModificationDate,
    "A nova data não pode depender de lastModifiedDate recente do EventKit."
)

let unchangedBatch = LocalItemBatch(
    items: [],
    eventItems: [newEvent],
    eventOccurrences: [newOccurrence],
    windowStart: windowStart,
    windowEnd: windowEnd
)
let unchangedDelta = EventSnapshotDelta.between(
    previous: [newOccurrence],
    current: [newOccurrence],
    windowStart: windowStart,
    windowEnd: windowEnd
)

expect(unchangedDelta.added.isEmpty, "Aniversário inalterado não deve ser reenviado.")
expect(unchangedDelta.removed.isEmpty, "Aniversário inalterado não deve ser removido.")
expect(
    unchangedBatch.syncItems(includingAdded: unchangedDelta.added).isEmpty,
    "O ciclo incremental não deve gravar novamente um aniversário inalterado."
)

print("Event snapshot delta contract passed")
