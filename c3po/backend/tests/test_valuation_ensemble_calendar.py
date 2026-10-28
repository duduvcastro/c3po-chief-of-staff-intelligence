"""Real XNYS calendar, synthetic publication metadata only; zero price labels."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

import exchange_calendars as xcals
import pytest

from app import valuation_ensemble_calendar as calendar
from app import valuation_price_history as prices


def reference(cut: datetime, *, first: str = "2021-06-01", last: str = "2021-06-08") -> dict[str, Any]:
    return {"grid_start": "2021-06-01", "grid": [{"session_date": first}, {"session_date": last}],
            "price_pin": {market: {"status": "ok", "available_at": cut.isoformat()} for market in ("NASDAQ", "NYSE")}}


def test_real_xnys_calendar_anchor_and_maturity_use_the_publication_metadata_not_price_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_labels(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Calendar helper requested price labels")
    monkeypatch.setattr(prices.PriceHistoryService, "label_bar", no_labels)
    cut = datetime(2022, 6, 3, 20, tzinfo=timezone.utc)
    descriptor = calendar.report_calendar_for(reference(cut))
    xnys = xcals.get_calendar("XNYS")
    expected_sessions = [stamp.date().isoformat() for stamp in xnys.sessions_in_range("2021-06-01", "2022-06-03")]
    assert descriptor["index_of"] == {session: i for i, session in enumerate(expected_sessions)}
    assert descriptor["partition_last"] == descriptor["index_of"]["2021-06-08"] == 5
    assert "2021-07-05" not in descriptor["index_of"]  # observed July4 holiday
    last_index = len(expected_sessions) - 1
    assert descriptor["mature_through"] == {str(h): last_index - h if last_index >= h else None for h in (21, 22, 63, 64, 126, 127, 252, 253)}
    assert descriptor == calendar.report_calendar_for(reference(cut))


def test_publication_cut_is_available_at_plus_one_microsecond_and_close_is_strict() -> None:
    xnys = xcals.get_calendar("XNYS")
    close = xnys.session_close("2022-06-03").to_pydatetime()
    included = calendar.report_calendar_for(reference(close))
    excluded = calendar.report_calendar_for(reference(close - timedelta(microseconds=1)))
    assert max(included["index_of"], key=included["index_of"].get) == "2022-06-03"
    assert max(excluded["index_of"], key=excluded["index_of"].get) == "2022-06-02"
    for h in (21, 22, 63, 64, 126, 127, 252, 253):
        left, right = included["mature_through"][str(h)], excluded["mature_through"][str(h)]
        if left is not None and right is not None:
            assert left == right + 1


def test_us_half_day_uses_actual_early_close_not_a_hardcoded_utc_hour() -> None:
    xnys = xcals.get_calendar("XNYS")
    close = xnys.session_close("2021-11-26").to_pydatetime()
    assert close.hour == 18  # day after Thanksgiving, 13:00ET
    before = calendar.report_calendar_for(reference(close - timedelta(microseconds=1)))
    after = calendar.report_calendar_for(reference(close))
    assert "2021-11-25" not in after["index_of"]
    assert "2021-11-26" not in before["index_of"] and "2021-11-26" in after["index_of"]


def test_the_earlier_exchange_publication_limits_both_markets() -> None:
    late = datetime(2022, 6, 6, 20, tzinfo=timezone.utc)
    early = late - timedelta(microseconds=1)
    ref = reference(late)
    ref["price_pin"]["NASDAQ"]["available_at"] = early.isoformat()
    result = calendar.report_calendar_for(ref)
    assert result == calendar.report_calendar_for(reference(early))
    assert "2022-06-06" not in result["index_of"]


def test_naive_price_run_api_clock_preserves_the_frozen_utc_convention() -> None:
    cut = datetime(2022, 6, 3, 20, tzinfo=timezone.utc)
    naive = reference(cut)
    for pin in naive["price_pin"].values():
        pin["available_at"] = cut.replace(tzinfo=None).isoformat()
    assert calendar.report_calendar_for(naive) == calendar.report_calendar_for(reference(cut))


def test_grid_end_and_calendar_end_are_distinct_and_immature_positions_stay_unavailable() -> None:
    cut = datetime(2021, 6, 8, 20, tzinfo=timezone.utc)
    result = calendar.report_calendar_for(reference(cut, last="2021-06-15"))
    assert result["partition_last"] == 10 and result["index_of"]["2021-06-15"] == 10
    assert all(value is None for value in result["mature_through"].values())


@pytest.mark.parametrize("failure", ["anchor", "pins", "one_market", "status", "grid", "weekend", "time"])
def test_missing_or_incompatible_calendar_metadata_is_refused(failure: str) -> None:
    ref = reference(datetime(2022, 6, 3, 20, tzinfo=timezone.utc))
    if failure == "anchor":
        ref["grid_start"] = "2021-01-01"
    elif failure == "pins":
        ref["price_pin"] = None
    elif failure == "one_market":
        del ref["price_pin"]["NYSE"]
    elif failure == "status":
        ref["price_pin"]["NYSE"]["status"] = "pending"
    elif failure == "grid":
        ref["grid"] = []
    elif failure == "weekend":
        ref["grid"][1]["session_date"] = "2021-06-06"
    else:
        ref["price_pin"]["NYSE"]["available_at"] = "not-a-time"
    with pytest.raises((ValueError, KeyError)):
        calendar.report_calendar_for(ref)
