"""Calendar and maturity derived from reference-publication metadata, no labels."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Mapping


def report_calendar_for(rev3_manifest: Mapping[str, Any]) -> dict[str, Any]:
    # Reuse the frozen rev3 definitions; these calls read exchange sessions only.
    from . import valuation_accuracy_report as accuracy
    from . import valuation_pit_backtest_report as backtest
    from . import valuation_panel as panel

    pins, entries = rev3_manifest.get("price_pin"), rev3_manifest.get("grid")
    if (not isinstance(pins, Mapping) or not isinstance(entries, list) or not entries
            or rev3_manifest.get("grid_start") != backtest.GRID_START.isoformat()):
        raise ValueError("ensemble_reference_calendar_metadata_missing")
    cuts = []
    for market in ("NASDAQ", "NYSE"):
        pin = pins.get(market)
        if not isinstance(pin, Mapping) or pin.get("status") != "ok":
            raise ValueError("ensemble_reference_publication_metadata_missing")
        cuts.append(panel._utc(pin["available_at"]) + timedelta(microseconds=1))
    label_cut = min(cuts)
    sessions = sorted({str(entry["session_date"]) for entry in entries})
    anchor = backtest.first_session_on_or_after(backtest.GRID_START)
    closed = panel.last_closed_session(backtest.CALENDAR_MARKET, label_cut)
    end = max([date.fromisoformat(day) for day in [closed, *sessions] if day] + [anchor])
    calendar = accuracy._calendar_dates(backtest.CALENDAR_MARKET, anchor, end)
    index = {session: i for i, session in enumerate(calendar)}
    if any(session not in index for session in sessions):
        raise ValueError("ensemble_reference_session_outside_calendar")
    maturity: dict[str, int | None] = {}
    for horizon in (21, 22, 63, 64, 126, 127, 252, 253):
        through = accuracy._mature_through(backtest.CALENDAR_MARKET, label_cut, horizon)
        maturity[str(horizon)] = (None if through is None or through < anchor
            else sum(1 for session in calendar if session <= through.isoformat()) - 1)
    return {"index_of": index, "mature_through": maturity,
            "partition_last": index[sessions[-1]]}
