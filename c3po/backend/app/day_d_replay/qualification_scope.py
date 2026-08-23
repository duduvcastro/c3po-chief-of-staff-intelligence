from __future__ import annotations

from datetime import date


QUALIFICATION_TICK_DATASETS = frozenset({"trades", "quotes"})
QUALIFICATION_SESSION_DATES = frozenset({
    date(2022, 6, 13),
    date(2024, 8, 5),
    date(2024, 9, 18),
    date(2024, 12, 24),
    date(2025, 3, 21),
    date(2025, 6, 20),
    date(2025, 6, 27),
    date(2025, 9, 19),
    date(2025, 11, 28),
    date(2026, 8, 19),
    date(2026, 8, 20),
    date(2026, 8, 21),
})


def is_complete_qualification_tick_lot(
    *,
    session_dates: set[date],
    datasets: set[str],
) -> bool:
    return (
        len(session_dates) == 1
        and session_dates <= QUALIFICATION_SESSION_DATES
        and datasets == QUALIFICATION_TICK_DATASETS
    )
