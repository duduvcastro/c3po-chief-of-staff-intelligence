from datetime import date, datetime, timedelta, timezone
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import exchange_calendars as xcals
import pytest

from app.config import Settings
from app.database import Database
from app.r2d2 import (
    XNYS_CLOSE_SOURCE,
    R2D2PaperService,
    _build_nav_session_delta,
    _canonical_nav_close,
)
from app.schemas import R2D2Position
from app.r2d2_cash_yield import (
    CashYieldDataError,
    R2D2CashYieldService,
    coupon_equivalent_factor,
    parse_treasury_bill_xml,
)


def _xml(*observed_dates: str, coupon_equivalent: str = "4.20", bank_discount: str = "4.10") -> str:
    entries = "".join(f"""
      <entry><content><m:properties>
        <d:INDEX_DATE>{observed}T00:00:00</d:INDEX_DATE>
        <d:ROUND_B1_CLOSE_13WK_2>{bank_discount}</d:ROUND_B1_CLOSE_13WK_2>
        <d:ROUND_B1_YIELD_13WK_2>{coupon_equivalent}</d:ROUND_B1_YIELD_13WK_2>
      </m:properties></content></entry>""" for observed in observed_dates)
    return f"""<?xml version="1.0"?>
    <feed xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
          xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
          xmlns="http://www.w3.org/2005/Atom">
      {entries}
    </feed>"""


class FakeTreasuryHttp:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict]] = []

    def get_text(self, url: str, *, params=None, **_kwargs) -> str:
        self.calls.append((url, dict(params or {})))
        return self.payload


def _settings() -> Settings:
    return Settings(
        database_url="",
        r2d2_start_date="2026-08-17",
        r2d2_starting_capital_usd=1_000_000,
        r2d2_cash_yield_accounting_enabled=True,
    )


def _nav_close_benchmark(
    session_date: date,
    *,
    marks: list[dict] | None = None,
    captured_at: datetime | None = None,
) -> dict:
    session_close = xcals.get_calendar("XNYS").session_close(session_date).to_pydatetime()
    close_marks = marks or []
    return {
        "nav_close": {
            "schema": "R2D2_NAV_CLOSE_V1",
            "source": XNYS_CLOSE_SOURCE,
            "session_date": session_date.isoformat(),
            "session_close_at": session_close.isoformat(),
            "captured_at": (captured_at or session_close + timedelta(minutes=5)).isoformat(),
            "position_count": len(close_marks),
            "cash_only": not close_marks,
            "quote_window": {
                "earliest": (session_close - timedelta(minutes=5)).isoformat(),
                "latest": session_close.isoformat(),
            },
            "marks": close_marks,
        },
    }


def test_frozen_cash_yield_spec_and_attestation_hashes_match() -> None:
    docs = Path(__file__).resolve().parents[2] / "docs"
    expected = {
        "R2D2_CASH_YIELD_ACCOUNTING_V1.md": "778fc6b066f405229d8c710630f370274ddb3bc501aeaf0307499be7458791af",
        "R2D2_CASH_YIELD_ACCOUNTING_V1.attestation.md": "557e38b05f197ae8b17ee1fc79ae1dd361db5bccd7970c466247f13e7c4bc47e",
    }
    for filename, digest in expected.items():
        assert hashlib.sha256((docs / filename).read_bytes()).hexdigest() == digest


def test_treasury_parser_uses_coupon_equivalent_and_enforces_d_plus_one() -> None:
    observed = date(2026, 8, 24)
    package = parse_treasury_bill_xml(
        _xml("2026-08-24"),
        observation_date=observed,
        fetched_at=datetime(2026, 8, 25, 0, 0, tzinfo=timezone.utc),
    )

    assert package["annual_rate"] == 0.042
    assert package["field_label"] == "Coupon Equivalent"
    assert package["excluded_field"] == "Bank Discount"
    assert len(package["payload_sha256"]) == 64

    with pytest.raises(CashYieldDataError, match="not yet causally available"):
        parse_treasury_bill_xml(
            _xml("2026-08-24"),
            observation_date=observed,
            fetched_at=datetime(2026, 8, 24, 23, 59, 59, tzinfo=timezone.utc),
        )


def test_coupon_equivalent_factor_uses_calendar_days_and_splits_leap_year() -> None:
    assert coupon_equivalent_factor(0.0365, date(2026, 8, 28), date(2026, 8, 31)) == pytest.approx(0.0003)
    expected = 0.0365 / 365 + 0.0365 / 366
    assert coupon_equivalent_factor(0.0365, date(2023, 12, 31), date(2024, 1, 2)) == pytest.approx(expected)


def test_nav_session_delta_uses_friday_total_for_monday_and_reconciles_to_cents() -> None:
    delta = _build_nav_session_delta(
        now=datetime(2026, 8, 24, 15, 0, tzinfo=timezone.utc),
        experiment_start_date=date(2026, 8, 17),
        policy_epoch_started_at=None,
        current_marked_nav_usd=1_010_000.006,
        current_mark_available=True,
        snapshots=[{
            "session_date": date(2026, 8, 21),
            "nav_usd": 1_000_000.004,
            "cash_usd": 1_000_000.004,
            "gross_exposure_usd": 0,
            "is_final": True,
            "open_positions": 0,
            "benchmark_snapshot": _nav_close_benchmark(date(2026, 8, 21)),
        }],
        cash_yield_entries=[
            {"session_date": date(2026, 8, 21), "interest_income_usd": 40.016},
            {"session_date": date(2026, 8, 24), "interest_income_usd": 100.005},
        ],
    )

    assert delta.status == "available"
    assert delta.session_date == "2026-08-24"
    assert delta.previous_session_date == "2026-08-21"
    assert delta.current_total_nav_usd == 1_010_140.03
    assert delta.previous_total_nav_usd == 1_000_040.02
    assert delta.organic_delta_usd == 10_000.01
    assert delta.interest_delta_usd == 100.00
    assert delta.total_delta_usd == 10_100.01
    assert delta.total_delta_usd == delta.organic_delta_usd + delta.interest_delta_usd
    assert delta.total_delta_percent == pytest.approx(
        delta.total_delta_usd / delta.previous_total_nav_usd * 100,
        abs=0.0001,
    )
    assert delta.organic_delta_percent == pytest.approx(
        delta.organic_delta_usd / delta.previous_total_nav_usd * 100,
        abs=0.0001,
    )
    assert delta.interest_delta_percent == pytest.approx(
        delta.interest_delta_usd / delta.previous_total_nav_usd * 100,
        abs=0.0001,
    )
    assert delta.total_delta_percent == round(
        delta.organic_delta_percent + delta.interest_delta_percent,
        4,
    )
    assert delta.interest_status == "posted"


def test_nav_session_delta_skips_us_holiday_when_resolving_previous_session() -> None:
    delta = _build_nav_session_delta(
        now=datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc),
        experiment_start_date=date(2026, 8, 17),
        policy_epoch_started_at=None,
        current_marked_nav_usd=1_001_000,
        current_mark_available=True,
        snapshots=[{
            "session_date": date(2026, 9, 4),
            "nav_usd": 1_000_000,
            "cash_usd": 1_000_000,
            "gross_exposure_usd": 0,
            "is_final": True,
            "open_positions": 0,
            "benchmark_snapshot": _nav_close_benchmark(date(2026, 9, 4)),
        }],
        cash_yield_entries=[
            {"session_date": date(2026, 9, 4), "interest_income_usd": 10},
            {"session_date": date(2026, 9, 8), "interest_income_usd": 20},
        ],
    )

    assert delta.status == "available"
    assert delta.session_date == "2026-09-08"
    assert delta.previous_session_date == "2026-09-04"
    assert delta.organic_delta_usd == 1_000
    assert delta.interest_delta_usd == 20


def test_nav_session_delta_anchors_session_date_in_new_york_after_midnight_brt() -> None:
    delta = _build_nav_session_delta(
        # 00:30 BRT on Tuesday is still 23:30 ET on Monday.
        now=datetime(2026, 8, 25, 3, 30, tzinfo=timezone.utc),
        experiment_start_date=date(2026, 8, 17),
        policy_epoch_started_at=None,
        current_marked_nav_usd=1_001_000,
        current_mark_available=True,
        snapshots=[
            {
                "session_date": date(2026, 8, 21),
                "nav_usd": 1_000_000,
                "cash_usd": 1_000_000,
                "gross_exposure_usd": 0,
                "is_final": True,
                "open_positions": 0,
                "benchmark_snapshot": _nav_close_benchmark(date(2026, 8, 21)),
            },
            {
                "session_date": date(2026, 8, 24),
                "nav_usd": 1_001_000,
                "cash_usd": 1_001_000,
                "gross_exposure_usd": 0,
                "is_final": True,
                "open_positions": 0,
                "benchmark_snapshot": _nav_close_benchmark(date(2026, 8, 24)),
            },
        ],
        cash_yield_entries=[
            {"session_date": date(2026, 8, 24), "interest_income_usd": 20},
        ],
    )

    assert delta.status == "available"
    assert delta.session_date == "2026-08-24"
    assert delta.previous_session_date == "2026-08-21"


def test_nav_session_delta_fails_closed_when_regular_session_mark_is_not_live() -> None:
    delta = _build_nav_session_delta(
        now=datetime(2026, 8, 24, 15, 0, tzinfo=timezone.utc),
        experiment_start_date=date(2026, 8, 17),
        policy_epoch_started_at=None,
        current_marked_nav_usd=1_001_000,
        current_mark_available=False,
        snapshots=[{
            "session_date": date(2026, 8, 21),
            "nav_usd": 1_000_000,
            "cash_usd": 1_000_000,
            "gross_exposure_usd": 0,
            "is_final": True,
            "open_positions": 0,
            "benchmark_snapshot": _nav_close_benchmark(date(2026, 8, 21)),
        }],
        cash_yield_entries=[],
    )

    assert delta.status == "current_mark_unavailable"
    assert delta.session_date == "2026-08-24"
    assert delta.previous_session_date == "2026-08-21"
    assert delta.current_total_nav_usd is None
    assert delta.total_delta_percent is None


def test_nav_session_delta_is_unavailable_before_current_session_opens() -> None:
    delta = _build_nav_session_delta(
        now=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
        experiment_start_date=date(2026, 8, 17),
        policy_epoch_started_at=None,
        current_marked_nav_usd=1_001_000,
        current_mark_available=True,
        snapshots=[{
            "session_date": date(2026, 8, 21),
            "nav_usd": 1_000_000,
            "cash_usd": 1_000_000,
            "gross_exposure_usd": 0,
            "is_final": True,
            "open_positions": 0,
            "benchmark_snapshot": _nav_close_benchmark(date(2026, 8, 21)),
        }],
        cash_yield_entries=[],
    )

    assert delta.status == "current_mark_unavailable"
    assert delta.current_total_nav_usd is None


def test_nav_session_delta_uses_current_canonical_close_after_market_close() -> None:
    current_session = date(2026, 8, 24)
    current_captured_at = datetime(2026, 8, 24, 20, 0, 20, tzinfo=timezone.utc)
    delta = _build_nav_session_delta(
        now=datetime(2026, 8, 24, 20, 0, 30, tzinfo=timezone.utc),
        experiment_start_date=date(2026, 8, 17),
        policy_epoch_started_at=None,
        current_marked_nav_usd=999_000,
        current_mark_available=False,
        snapshots=[
            {
                "session_date": date(2026, 8, 21),
                "nav_usd": 1_000_000,
                "cash_usd": 1_000_000,
                "gross_exposure_usd": 0,
                "is_final": True,
                "open_positions": 0,
                "benchmark_snapshot": _nav_close_benchmark(date(2026, 8, 21)),
            },
            {
                "session_date": current_session,
                "nav_usd": 1_005_000,
                "cash_usd": 1_005_000,
                "gross_exposure_usd": 0,
                "is_final": True,
                "open_positions": 0,
                "benchmark_snapshot": _nav_close_benchmark(
                    current_session,
                    captured_at=current_captured_at,
                ),
            },
        ],
        cash_yield_entries=[],
    )

    assert delta.status == "available"
    assert delta.current_total_nav_usd == 1_005_000
    assert delta.previous_total_nav_usd == 1_000_000
    assert delta.total_delta_usd == 5_000


def test_nav_session_delta_is_nd_on_first_policy_epoch_session_even_with_prior_close() -> None:
    delta = _build_nav_session_delta(
        now=datetime(2026, 8, 26, 15, 0, tzinfo=timezone.utc),
        experiment_start_date=date(2026, 8, 17),
        policy_epoch_started_at=datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc),
        current_marked_nav_usd=1_001_000,
        current_mark_available=True,
        snapshots=[{
            "session_date": date(2026, 8, 25),
            "nav_usd": 1_000_000,
            "is_final": True,
        }],
        cash_yield_entries=[
            {"session_date": date(2026, 8, 26), "interest_income_usd": 100},
        ],
    )

    assert delta.status == "first_session"
    assert delta.session_date == "2026-08-26"
    assert delta.previous_session_date is None
    assert delta.total_delta_usd is None
    assert delta.total_delta_percent is None
    assert delta.organic_delta_percent is None
    assert delta.interest_delta_percent is None
    assert delta.interest_status == "not_applicable"


def test_nav_session_delta_starts_epoch_next_session_when_epoch_begins_after_close() -> None:
    delta = _build_nav_session_delta(
        now=datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc),
        experiment_start_date=date(2026, 8, 17),
        # XNYS closed at 20:00 UTC; this policy epoch therefore starts on Aug 27.
        policy_epoch_started_at=datetime(2026, 8, 26, 20, 30, tzinfo=timezone.utc),
        current_marked_nav_usd=1_001_000,
        current_mark_available=True,
        snapshots=[{
            "session_date": date(2026, 8, 26),
            "nav_usd": 1_000_000,
            "is_final": True,
        }],
        cash_yield_entries=[
            {"session_date": date(2026, 8, 27), "interest_income_usd": 100},
        ],
    )

    assert delta.status == "first_session"
    assert delta.session_date == "2026-08-27"
    assert delta.previous_session_date is None
    assert delta.current_total_nav_usd is None
    assert delta.previous_total_nav_usd is None
    assert delta.total_delta_usd is None
    assert delta.total_delta_percent is None
    assert delta.interest_status == "not_applicable"


def test_nav_session_delta_fails_honestly_when_exact_previous_close_is_missing() -> None:
    delta = _build_nav_session_delta(
        now=datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc),
        experiment_start_date=date(2026, 8, 17),
        policy_epoch_started_at=datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc),
        current_marked_nav_usd=1_001_000,
        current_mark_available=True,
        snapshots=[{
            "session_date": date(2026, 8, 25),
            "nav_usd": 1_000_000,
            "is_final": True,
        }],
        cash_yield_entries=[
            {"session_date": date(2026, 8, 27), "interest_income_usd": 100},
        ],
    )

    assert delta.status == "missing_previous_close"
    assert delta.session_date == "2026-08-27"
    assert delta.previous_session_date == "2026-08-26"
    assert delta.current_total_nav_usd is None
    assert delta.previous_total_nav_usd is None
    assert delta.total_delta_usd is None
    assert delta.interest_status == "posted"


def test_legacy_finalization_never_authenticates_intraday_as_nav_close() -> None:
    settings = _settings()
    paper = R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]
    experiment = paper.ensure_initialized()
    intraday = paper.repo.save_snapshot(
        experiment["id"], date(2026, 8, 21), 1_001_000, 1_001_000, 0, 0, False,
    )
    was_intraday = intraday["is_final"]

    paper.repo.finalize_before(experiment["id"], date(2026, 8, 24))
    stored = next(
        row for row in paper.repo.snapshots(experiment["id"])
        if row["session_date"] == date(2026, 8, 21)
    )
    delta = _build_nav_session_delta(
        now=datetime(2026, 8, 24, 15, 0, tzinfo=timezone.utc),
        experiment_start_date=date(2026, 8, 17),
        policy_epoch_started_at=None,
        current_marked_nav_usd=1_002_000,
        current_mark_available=True,
        snapshots=[stored],
        cash_yield_entries=[],
    )

    assert was_intraday is False
    # Legacy consumers keep their historical is_final lifecycle, while the
    # new tile requires independent close provenance.
    assert stored["is_final"] is True
    assert _canonical_nav_close(stored) is None
    assert delta.status == "missing_previous_close"


def test_normal_snapshot_cannot_overwrite_canonical_close() -> None:
    settings = _settings()
    paper = R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]
    experiment = paper.ensure_initialized()
    session_date = date(2026, 8, 21)
    canonical = paper.repo.save_snapshot(
        experiment["id"], session_date, 1_010_000, 1_010_000, 0, 0, True,
        benchmark_snapshot=_nav_close_benchmark(session_date),
    )

    paper.repo.save_snapshot(
        experiment["id"], session_date, 999_000, 899_000, 100_000, 1, False,
    )
    stored = next(
        row for row in paper.repo.snapshots(experiment["id"])
        if row["session_date"] == session_date
    )

    assert _canonical_nav_close(canonical) is not None
    assert stored == canonical


def test_close_capture_rejects_stale_position_quote_then_accepts_window_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    paper = R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]
    experiment = paper.ensure_initialized()
    paper.repo.memory["positions"][("NASDAQ", "PIN")] = {
        "market": "NASDAQ",
        "symbol": "PIN",
        "quantity": 10,
        "fx_to_usd": 1,
    }
    now = datetime(2026, 8, 21, 20, 0, 20, tzinfo=timezone.utc)
    quote = SimpleNamespace(
        price=100,
        as_of=datetime(2026, 8, 21, 19, 54, 59, tzinfo=timezone.utc),
        status="closed",
    )
    monkeypatch.setattr(
        paper,
        "_position_quotes",
        lambda _positions, _now: {("NASDAQ", "PIN"): quote},
    )

    assert paper._capture_canonical_close(experiment, now) is False
    assert not any(
        _canonical_nav_close(row) is not None
        for row in paper.repo.snapshots(experiment["id"])
        if row["session_date"] == date(2026, 8, 21)
    )

    quote.as_of = datetime(2026, 8, 21, 20, 0, 1, tzinfo=timezone.utc)
    assert paper._capture_canonical_close(experiment, now) is False

    quote.as_of = datetime(2026, 8, 21, 20, 0, tzinfo=timezone.utc)
    assert paper._capture_canonical_close(experiment, now) is True
    stored = next(
        row for row in paper.repo.snapshots(experiment["id"])
        if row["session_date"] == date(2026, 8, 21)
    )
    provenance = _canonical_nav_close(stored)
    assert provenance is not None
    assert stored["nav_usd"] == 1_001_000
    assert provenance["marks"][0]["quote_as_of"] == "2026-08-21T20:00:00+00:00"


def test_close_capture_refreshes_cash_inside_risk_lock() -> None:
    settings = _settings()
    paper = R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]
    stale_experiment = dict(paper.ensure_initialized())
    paper.repo.memory["experiment"]["cash_balance"] = 990_000

    assert paper._capture_canonical_close(
        stale_experiment,
        datetime(2026, 8, 21, 20, 0, 20, tzinfo=timezone.utc),
    ) is True
    stored = next(
        row for row in paper.repo.snapshots(stale_experiment["id"])
        if row["session_date"] == date(2026, 8, 21)
    )

    assert stored["cash_usd"] == 990_000
    assert stored["nav_usd"] == 990_000
    assert _canonical_nav_close(stored) is not None


@pytest.mark.parametrize(
    ("captured_at", "session_date", "expected_close"),
    [
        (datetime(2026, 8, 21, 20, 5, tzinfo=timezone.utc), date(2026, 8, 21), "2026-08-21T20:00:00+00:00"),
        # Black Friday is an XNYS early close (13:00 ET / 18:00 UTC).
        (datetime(2026, 11, 27, 18, 5, tzinfo=timezone.utc), date(2026, 11, 27), "2026-11-27T18:00:00+00:00"),
    ],
)
def test_market_closed_cycle_persists_cash_only_canonical_close(
    captured_at: datetime,
    session_date: date,
    expected_close: str,
) -> None:
    settings = _settings()
    paper = R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]
    experiment = paper.ensure_initialized()

    dashboard = paper.run_cycle(captured_at, force=True)
    stored = next(
        row for row in paper.repo.snapshots(experiment["id"])
        if row["session_date"] == session_date
    )
    provenance = _canonical_nav_close(stored)

    assert dashboard.last_cycle is not None
    assert dashboard.last_cycle.status == "market_closed"
    assert stored["is_final"] is True
    assert provenance is not None
    assert provenance["session_close_at"] == expected_close
    assert provenance["marks"] == []
    assert provenance["position_count"] == 0


def test_xnys_early_close_controls_screening_and_risk_windows() -> None:
    screening_cutoff = datetime(2026, 11, 27, 17, 50, tzinfo=timezone.utc)
    after_screening = screening_cutoff + timedelta(seconds=1)
    before_close = datetime(2026, 11, 27, 17, 59, tzinfo=timezone.utc)
    at_close = datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc)

    assert R2D2PaperService.open_markets(screening_cutoff) == ["NASDAQ", "NYSE"]
    assert R2D2PaperService.open_markets(after_screening) == []
    assert R2D2PaperService.risk_markets(before_close) == ["NASDAQ", "NYSE"]
    assert R2D2PaperService.risk_markets(at_close) == []
    assert R2D2PaperService._seconds_to_us_close("NASDAQ", before_close) == 60
    assert R2D2PaperService._seconds_to_us_close("NASDAQ", at_close) == 0


def test_dashboard_nav_session_delta_uses_live_marked_nav_not_realized_accounting_nav(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DuringMondaySession(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 8, 24, 15, 0, tzinfo=timezone.utc)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    monkeypatch.setattr("app.r2d2.datetime", DuringMondaySession)
    settings = _settings()
    database = Database(settings)
    paper = R2D2PaperService(settings, database, None, None, None)  # type: ignore[arg-type]
    experiment = paper.ensure_initialized()
    database._r2d2_cash_yield_entries = []  # type: ignore[attr-defined]
    paper.repo.memory["snapshots"][date(2026, 8, 21)] = {
        "session_date": date(2026, 8, 21),
        "nav_usd": 1_000_000,
        "cash_usd": 1_000_000,
        "gross_exposure_usd": 0,
        "is_final": True,
        "open_positions": 0,
        "benchmark_snapshot": _nav_close_benchmark(date(2026, 8, 21)),
    }
    database._r2d2_cash_yield_entries.extend([  # type: ignore[attr-defined]
        {
            "experiment_id": experiment["id"],
            "session_date": date(2026, 8, 21),
            "interest_income_usd": 40,
            "annual_coupon_equivalent_rate": 0.04,
            "source_observation_date": date(2026, 8, 20),
        },
        {
            "experiment_id": experiment["id"],
            "session_date": date(2026, 8, 24),
            "interest_income_usd": 100,
            "annual_coupon_equivalent_rate": 0.04,
            "source_observation_date": date(2026, 8, 21),
        },
    ])
    monkeypatch.setattr(
        paper,
        "_position_telemetry",
        lambda _experiment, _positions, _now: ([], 1_010_000, 0, 1_010_000),
    )

    dashboard = paper.dashboard()

    assert dashboard.accounting_total_nav_usd == 1_000_140
    assert [point.nav_usd for point in dashboard.track_record] == [
        1_000_000,
        1_000_040,
        1_000_140,
    ]
    assert dashboard.nav_usd == 1_010_000
    assert dashboard.nav_session_delta.current_total_nav_usd == 1_010_140
    assert dashboard.nav_session_delta.previous_total_nav_usd == 1_000_040
    assert dashboard.nav_session_delta.organic_delta_usd == 10_000
    assert dashboard.nav_session_delta.interest_delta_usd == 100
    assert dashboard.nav_session_delta.total_delta_usd == 10_100


@pytest.mark.parametrize(("market", "currency"), [("NASDAQ", "USD"), ("B3", "BRL")])
def test_dashboard_nav_session_delta_rejects_any_stored_position_mark(
    monkeypatch: pytest.MonkeyPatch,
    market: Literal["NASDAQ", "B3"],
    currency: str,
) -> None:
    class DuringMondaySession(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 8, 24, 15, 0, tzinfo=timezone.utc)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    monkeypatch.setattr("app.r2d2.datetime", DuringMondaySession)
    settings = _settings()
    database = Database(settings)
    paper = R2D2PaperService(settings, database, None, None, None)  # type: ignore[arg-type]
    experiment = paper.ensure_initialized()
    database._r2d2_cash_yield_entries = []  # type: ignore[attr-defined]
    paper.repo.memory["snapshots"][date(2026, 8, 21)] = {
        "session_date": date(2026, 8, 21),
        "nav_usd": 1_000_000,
        "cash_usd": 1_000_000,
        "gross_exposure_usd": 0,
        "is_final": True,
        "open_positions": 0,
        "benchmark_snapshot": _nav_close_benchmark(date(2026, 8, 21)),
    }
    marked_at = datetime(2026, 8, 24, 14, 55, tzinfo=timezone.utc)
    stored_position = R2D2Position(
        market=market,
        symbol="STALE",
        name="Stale Mark",
        currency=currency,
        quantity=10,
        average_cost_local=100,
        last_price_local=101,
        market_value_usd=1_010,
        unrealized_pnl_usd=10,
        unrealized_return_percent=1,
        mark_pnl_usd=10,
        mark_return_percent=1,
        estimated_exit_pnl_usd=9,
        estimated_exit_return_percent=0.9,
        allocation_percent=0.1,
        stop_price_local=95,
        quote_status="stored",
        quote_as_of=marked_at,
        opened_at=marked_at,
        updated_at=marked_at,
    )
    monkeypatch.setattr(
        paper,
        "_position_telemetry",
        lambda _experiment, _positions, _now: (
            [stored_position], 998_990, 1_010, 1_000_000,
        ),
    )

    dashboard = paper.dashboard()

    assert dashboard.nav_session_delta.status == "current_mark_unavailable"
    assert dashboard.nav_session_delta.current_total_nav_usd is None
    assert dashboard.nav_session_delta.total_delta_percent is None


def test_close_capture_fails_closed_for_legacy_b3_without_price_and_fx_provenance() -> None:
    settings = _settings()
    paper = R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]
    experiment = paper.ensure_initialized()
    paper.repo.memory["positions"][("B3", "OLD3")] = {
        "market": "B3",
        "symbol": "OLD3",
        "quantity": 10,
        "fx_to_usd": 0.18,
    }

    captured = paper._capture_canonical_close(
        experiment,
        datetime(2026, 8, 21, 20, 0, 20, tzinfo=timezone.utc),
    )

    assert captured is False
    assert not any(
        _canonical_nav_close(snapshot) is not None
        for snapshot in paper.repo.snapshots(experiment["id"])
    )


def test_cash_yield_is_append_only_idempotent_and_does_not_change_operational_nav() -> None:
    settings = _settings()
    database = Database(settings)
    paper = R2D2PaperService(settings, database, None, None, None)  # type: ignore[arg-type]
    experiment = paper.ensure_initialized()
    paper.repo.memory["snapshots"][date(2026, 8, 17)] = {
        "session_date": date(2026, 8, 17), "cash_usd": 900_000,
        "nav_usd": 1_000_000, "is_final": True,
    }
    paper.repo.memory["snapshots"][date(2026, 8, 18)] = {
        "session_date": date(2026, 8, 18), "cash_usd": 900_000,
        "nav_usd": 1_000_000, "is_final": True,
    }
    service = R2D2CashYieldService(
        settings, database, FakeTreasuryHttp(_xml("2026-08-17"))  # type: ignore[arg-type]
    )

    first = service.run_latest()
    second = service.run_latest()
    dashboard = paper.dashboard()

    expected_interest = 900_000 * 0.042 / 365
    assert first["status"] == "posted"
    assert first["interest_income_usd"] == pytest.approx(expected_interest, abs=1e-6)
    assert second["status"] == "idempotent"
    assert len(database._r2d2_cash_yield_entries) == 1  # type: ignore[attr-defined]
    assert experiment["cash_balance"] == 1_000_000
    assert dashboard.nav_usd == 1_000_000
    assert dashboard.accounting_nav_ex_interest_usd == 1_000_000
    assert dashboard.accounting_total_nav_usd == pytest.approx(1_000_000 + expected_interest, abs=0.01)
    assert database._r2d2_cash_yield_entries[0]["session_date"] == date(2026, 8, 18)  # type: ignore[attr-defined]
    assert dashboard.interest_income_session_date == "2026-08-18"
    assert dashboard.interest_income_epoch_start_date == "2026-08-17"
    assert dashboard.interest_income_rate_date == "2026-08-17"
    assert dashboard.interest_income_status == "posted"


def test_run_latest_catches_up_missing_sessions_oldest_first(monkeypatch) -> None:
    class AfterAllRatesAreAvailable(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    monkeypatch.setattr("app.r2d2_cash_yield.datetime", AfterAllRatesAreAvailable)
    settings = _settings()
    database = Database(settings)
    paper = R2D2PaperService(settings, database, None, None, None)  # type: ignore[arg-type]
    paper.ensure_initialized()
    for session_date, cash_usd in (
        (date(2026, 8, 17), 900_000),
        (date(2026, 8, 18), 850_000),
        (date(2026, 8, 19), 800_000),
    ):
        paper.repo.memory["snapshots"][session_date] = {
            "session_date": session_date,
            "cash_usd": cash_usd,
            "nav_usd": 1_000_000,
            "is_final": True,
        }
    http = FakeTreasuryHttp(_xml("2026-08-17", "2026-08-18"))
    service = R2D2CashYieldService(settings, database, http)  # type: ignore[arg-type]

    result = service.run_latest()
    repeated = service.run_latest()

    entries = database._r2d2_cash_yield_entries  # type: ignore[attr-defined]
    assert result["status"] == "posted"
    assert result["posted_count"] == 2
    assert result["posted_session_dates"] == ["2026-08-18", "2026-08-19"]
    assert [entry["session_date"] for entry in entries] == [
        date(2026, 8, 18),
        date(2026, 8, 19),
    ]
    assert [entry["source_observation_date"] for entry in entries] == [
        date(2026, 8, 17),
        date(2026, 8, 18),
    ]
    assert len(http.calls) == 1
    assert repeated["status"] == "idempotent"
    assert len(entries) == 2


def test_run_through_posts_current_session_before_its_final_snapshot() -> None:
    settings = _settings()
    database = Database(settings)
    paper = R2D2PaperService(settings, database, None, None, None)  # type: ignore[arg-type]
    paper.ensure_initialized()
    for session_date, cash_usd in (
        (date(2026, 8, 21), 700_000),
        (date(2026, 8, 24), 800_000),
        (date(2026, 8, 25), 917_445.99),
    ):
        paper.repo.memory["snapshots"][session_date] = {
            "session_date": session_date,
            "cash_usd": cash_usd,
            "nav_usd": 946_565.14,
            "is_final": True,
        }
    http = FakeTreasuryHttp(_xml("2026-08-21", "2026-08-24", "2026-08-25", coupon_equivalent="3.81"))
    service = R2D2CashYieldService(settings, database, http)  # type: ignore[arg-type]

    result = service.run_through(date(2026, 8, 26))

    entries = database._r2d2_cash_yield_entries  # type: ignore[attr-defined]
    current = next(entry for entry in entries if entry["session_date"] == date(2026, 8, 26))
    assert result["status"] == "posted"
    assert result["session_date"] == "2026-08-26"
    assert current["prior_session_date"] == date(2026, 8, 25)
    assert current["base_cash_usd"] == pytest.approx(917_445.99)
    assert current["calendar_days"] == 1
    assert current["interest_income_usd"] == pytest.approx(917_445.99 * 0.0381 / 365)


def test_run_through_skips_weekends_and_uses_friday_cash_for_monday() -> None:
    settings = _settings()
    database = Database(settings)
    paper = R2D2PaperService(settings, database, None, None, None)  # type: ignore[arg-type]
    paper.ensure_initialized()
    paper.repo.memory["snapshots"][date(2026, 8, 21)] = {
        "session_date": date(2026, 8, 21),
        "cash_usd": 778_406.28,
        "nav_usd": 1_000_000,
        "is_final": True,
    }
    http = FakeTreasuryHttp(_xml("2026-08-21", coupon_equivalent="3.81"))
    service = R2D2CashYieldService(settings, database, http)  # type: ignore[arg-type]

    saturday = service.run_through(date(2026, 8, 22))
    monday = service.run_through(date(2026, 8, 24))

    entries = database._r2d2_cash_yield_entries  # type: ignore[attr-defined]
    assert saturday["status"] == "skipped"
    assert saturday["target_session"] == "2026-08-22"
    assert saturday["reason"] == "target_is_not_a_us_equities_session"
    assert [entry["session_date"] for entry in entries] == [date(2026, 8, 24)]
    assert entries[0]["calendar_days"] == 3
    assert entries[0]["base_cash_usd"] == pytest.approx(778_406.28)
    assert entries[0]["interest_income_usd"] == pytest.approx(243.76, abs=0.01)


def test_run_through_does_not_create_a_us_market_holiday_entry() -> None:
    settings = _settings()
    database = Database(settings)
    paper = R2D2PaperService(settings, database, None, None, None)  # type: ignore[arg-type]
    paper.ensure_initialized()
    paper.repo.memory["snapshots"][date(2026, 9, 4)] = {
        "session_date": date(2026, 9, 4),
        "cash_usd": 800_000,
        "nav_usd": 1_000_000,
        "is_final": True,
    }
    service = R2D2CashYieldService(
        settings,
        database,
        FakeTreasuryHttp(_xml("2026-09-04")),  # type: ignore[arg-type]
    )

    result = service.run_through(date(2026, 9, 7))

    assert result["status"] == "skipped"
    assert result["reason"] == "target_is_not_a_us_equities_session"
    assert database._r2d2_cash_yield_entries == []  # type: ignore[attr-defined]


def test_missing_rate_is_recorded_without_blocking_later_sessions(monkeypatch) -> None:
    class AfterAllRatesAreAvailable(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    monkeypatch.setattr("app.r2d2_cash_yield.datetime", AfterAllRatesAreAvailable)
    settings = _settings()
    database = Database(settings)
    paper = R2D2PaperService(settings, database, None, None, None)  # type: ignore[arg-type]
    paper.ensure_initialized()
    for session_date in (
        date(2026, 8, 17),
        date(2026, 8, 18),
        date(2026, 8, 19),
        date(2026, 8, 20),
    ):
        paper.repo.memory["snapshots"][session_date] = {
            "session_date": session_date,
            "cash_usd": 800_000,
            "nav_usd": 1_000_000,
            "is_final": True,
        }
    http = FakeTreasuryHttp(_xml("2026-08-17", "2026-08-19"))
    service = R2D2CashYieldService(settings, database, http)  # type: ignore[arg-type]

    # A missing Treasury observation is the spec's expected "pending" state: the run
    # records it and returns normally (it no longer fails the phase every night).
    result = service.run_latest()

    entries = database._r2d2_cash_yield_entries  # type: ignore[attr-defined]
    latest_run = database.latest_analysis_snapshot("r2d2_cash_yield_run", "R2D2_CASH_YIELD")
    assert [entry["session_date"] for entry in entries] == [
        date(2026, 8, 18),
        date(2026, 8, 20),
    ]
    assert len(http.calls) == 1
    assert latest_run is not None
    assert result["status"] == latest_run["outputs"]["status"] == "pending_data"
    assert latest_run["outputs"]["pending_sessions"] == [{
        "session_date": "2026-08-19",
        "source_observation_date": "2026-08-18",
        "reason": "treasury_observation_absent_for_source_date",
        "detail": "Expected one Treasury observation for 2026-08-18, found 0",
    }]
    assert service.last_run_at() is not None

    http.payload = _xml("2026-08-17", "2026-08-18", "2026-08-19")
    completed = service.run_latest()
    assert completed["status"] == "posted"
    assert completed["session_date"] == "2026-08-20"
    assert sorted(entry["session_date"] for entry in entries) == [
        date(2026, 8, 18),
        date(2026, 8, 19),
        date(2026, 8, 20),
    ]


# --- Expected steady states vs real faults (owner complaint 20/10/2026) ---

from app.r2d2_cash_yield import CashYieldPendingData  # noqa: E402


def _service_with_sessions(
    sessions: dict[date, float],
    xml: str,
    *,
    experiment_status: str | None = None,
    entries_paused: bool = False,
):
    settings = _settings()
    database = Database(settings)
    paper = R2D2PaperService(settings, database, None, None, None)  # type: ignore[arg-type]
    paper.ensure_initialized()
    if experiment_status:
        paper.repo.memory["experiment"]["status"] = experiment_status
    paper.repo.memory["experiment"]["entries_paused"] = entries_paused
    for session_date, cash_usd in sessions.items():
        paper.repo.memory["snapshots"][session_date] = {
            "session_date": session_date, "cash_usd": cash_usd,
            "nav_usd": 1_000_000, "is_final": True,
        }
    http = FakeTreasuryHttp(xml)
    return database, R2D2CashYieldService(settings, database, http), http  # type: ignore[arg-type]


def test_parser_classifies_absent_versus_not_yet_published_versus_not_yet_causal() -> None:
    fetched = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
    with pytest.raises(CashYieldPendingData) as absent:
        parse_treasury_bill_xml(_xml("2026-10-09", "2026-10-13"),
                                observation_date=date(2026, 10, 12), fetched_at=fetched)
    assert absent.value.reason == "treasury_observation_absent_for_source_date"
    with pytest.raises(CashYieldPendingData) as unpublished:
        parse_treasury_bill_xml(_xml("2026-10-09"), observation_date=date(2026, 10, 12),
                                fetched_at=datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc))
    assert unpublished.value.reason == "treasury_observation_not_yet_published"
    # More than 4 days later with nothing on or after the source date: a stale feed (fault).
    with pytest.raises(CashYieldDataError, match="Treasury feed is stale") as stale:
        parse_treasury_bill_xml(_xml("2026-10-09"), observation_date=date(2026, 10, 12),
                                fetched_at=datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc))
    assert not isinstance(stale.value, CashYieldPendingData)
    # The Columbus Day gap stays pending however old it is: later dates were published.
    with pytest.raises(CashYieldPendingData) as old_gap:
        parse_treasury_bill_xml(_xml("2026-10-09", "2026-10-13"), observation_date=date(2026, 10, 12),
                                fetched_at=datetime(2026, 12, 31, tzinfo=timezone.utc))
    assert old_gap.value.reason == "treasury_observation_absent_for_source_date"
    with pytest.raises(CashYieldPendingData) as not_causal:
        parse_treasury_bill_xml(_xml("2026-10-19"), observation_date=date(2026, 10, 19),
                                fetched_at=datetime(2026, 10, 19, 23, 0, tzinfo=timezone.utc))
    assert not_causal.value.reason == "treasury_observation_not_yet_causal"


@pytest.mark.parametrize("xml,match", [
    ("<feed", "invalid XML"),
    (_xml("2026-10-09", coupon_equivalent="-0.10"), "negative"),
    (_xml("2026-10-09", coupon_equivalent="n/a"), "lacks 13-week"),
    (_xml("2026-10-09", "2026-10-09"), "found 2"),
    # Broken feeds that parse as XML must not look like "not yet published".
    ('<feed xmlns="http://www.w3.org/2005/Atom"/>', "no dated rows"),
    (_xml("2026-10-09").replace("INDEX_DATE", "RECORD_DATE"), "no dated rows"),
    ("<html><head><title>Error</title></head><body><p>Service unavailable</p></body></html>", "no dated rows"),
])
def test_parser_real_faults_are_not_pending(xml: str, match: str) -> None:
    with pytest.raises(CashYieldDataError, match=match) as fault:
        parse_treasury_bill_xml(xml, observation_date=date(2026, 10, 9),
                                fetched_at=datetime(2026, 10, 20, tzinfo=timezone.utc))
    assert not isinstance(fault.value, CashYieldPendingData)


def test_columbus_day_gap_stays_pending_without_failing_or_fabricating() -> None:
    # 12/10/2026: XNYS traded, the Treasury did not publish (Columbus Day). The
    # frozen spec allows no substitute rate, so 13/10 stays pending; 14/10 posts.
    database, service, _http = _service_with_sessions(
        {date(2026, 10, 9): 800_000, date(2026, 10, 12): 800_000, date(2026, 10, 13): 800_000},
        _xml("2026-10-09", "2026-10-13"),
    )
    result = service.run_through(date(2026, 10, 14))

    entries = database._r2d2_cash_yield_entries  # type: ignore[attr-defined]
    assert result["status"] == "pending_data"
    assert result["pending_reasons"] == ["treasury_observation_absent_for_source_date"]
    assert [row["session_date"] for row in result["pending_sessions"]] == ["2026-10-13"]
    assert sorted(entry["session_date"] for entry in entries) == [date(2026, 10, 12), date(2026, 10, 14)]
    assert all(entry["source_observation_date"] != date(2026, 10, 12) for entry in entries)
    assert service.last_run_at() is not None


def test_missing_prior_final_snapshot_is_pending_not_a_failure() -> None:
    database, service, http = _service_with_sessions(
        {date(2026, 10, 9): 800_000}, _xml("2026-10-09"),
    )
    result = service.run_through(date(2026, 10, 14))
    assert result["status"] == "pending_data"
    assert result["pending_reasons"] == ["prior_final_session_snapshot_missing"]
    assert [row["session_date"] for row in result["pending_sessions"]] == ["2026-10-13", "2026-10-14"]
    assert [entry["session_date"] for entry in database._r2d2_cash_yield_entries] == [date(2026, 10, 12)]  # type: ignore[attr-defined]


def test_real_fault_still_raises_after_posting_the_other_sessions() -> None:
    database, service, http = _service_with_sessions(
        {date(2026, 10, 12): 800_000, date(2026, 10, 13): 800_000},
        _xml("2026-10-12", "2026-10-12", "2026-10-13"),
    )
    with pytest.raises(CashYieldDataError, match="data fault: 2026-10-13") as fault:
        service.run_through(date(2026, 10, 14))
    assert not isinstance(fault.value, CashYieldPendingData)
    latest_run = database.latest_analysis_snapshot("r2d2_cash_yield_run", "R2D2_CASH_YIELD")
    assert latest_run is not None and latest_run["outputs"]["status"] == "partial"
    assert latest_run["outputs"]["fault_sessions"][0]["reason"] == (
        "Expected one Treasury observation for 2026-10-12, found 2"
    )
    assert [entry["session_date"] for entry in database._r2d2_cash_yield_entries] == [date(2026, 10, 14)]  # type: ignore[attr-defined]
    assert service.last_run_at() is None  # the phase retries a real fault


def test_canonical_entry_mismatch_remains_a_real_fault() -> None:
    _database, service, _http = _service_with_sessions({}, _xml())
    service.database.database_url = "postgresql://unused"  # route _insert_entry's mismatch branch
    service._entry = lambda *_args: {"interest_income_usd": 1.0, "entry_sha256": "other"}  # type: ignore[method-assign]

    class _Connection:
        def __enter__(self): return self
        def __exit__(self, *_exc): return False
        def execute(self, *_args): return self
        def fetchone(self): return None
        def commit(self): return None

    service.database.connection = lambda: _Connection()  # type: ignore[method-assign]
    with pytest.raises(CashYieldDataError, match="does not match the canonical entry") as fault:
        service._insert_entry({
            "id": "x", "experiment_id": "e", "session_date": date(2026, 10, 14),
            "prior_session_date": date(2026, 10, 13), "base_cash_usd": 1.0,
            "annual_coupon_equivalent_rate": 0.04, "calendar_days": 1, "daily_factor": 0.0001,
            "interest_income_usd": 0.0001, "source_name": "s", "source_series": "s",
            "source_observation_date": date(2026, 10, 13), "source_available_at": None,
            "source_fetched_at": None, "source_payload_sha256": "p", "entry_sha256": "mine",
            "backfilled_at": None,
        })
    assert not isinstance(fault.value, CashYieldPendingData)


@pytest.mark.parametrize("status", ["paused", "completed"])
def test_paused_or_completed_experiment_is_a_no_op_success(status: str) -> None:
    database, service, http = _service_with_sessions(
        {date(2026, 10, 12): 800_000, date(2026, 10, 13): 800_000},
        _xml("2026-10-12", "2026-10-13"), experiment_status=status,
    )
    for result in (service.run_through(date(2026, 10, 14)), service.run_latest()):
        assert result["status"] == "idle"
        assert result["reason"] == f"experiment_{status}"
    assert database._r2d2_cash_yield_entries == []  # type: ignore[attr-defined]
    assert http.calls == []
    assert service.last_run_at() is not None


def test_entries_paused_keeps_accruing_from_factual_final_snapshots() -> None:
    # entries_paused (the 06/09 breaker) stops new entries only; the paper worker
    # still writes final snapshots, so the accrual stays factual and continues.
    database, service, _http = _service_with_sessions(
        {date(2026, 10, 13): 800_000}, _xml("2026-10-13"), entries_paused=True,
    )
    result = service.run_through(date(2026, 10, 14))
    assert result["status"] == "posted"
    assert [entry["session_date"] for entry in database._r2d2_cash_yield_entries] == [date(2026, 10, 14)]  # type: ignore[attr-defined]


def test_worker_phase_succeeds_on_the_columbus_day_gap_and_opens_no_incident() -> None:
    from zoneinfo import ZoneInfo

    from app.valuation_worker import OffhoursPhase, run_worker_iteration

    database, service, _http = _service_with_sessions(
        {date(2026, 10, 9): 800_000, date(2026, 10, 12): 800_000, date(2026, 10, 13): 800_000},
        _xml("2026-10-09", "2026-10-13"),
    )
    phase = OffhoursPhase(
        "cash_yield", service.last_run_at, lambda: service.run_through(date(2026, 10, 14)),
        start_hour=6, end_hour=10,
    )
    result = run_worker_iteration(
        database, now=datetime(2026, 10, 14, 6, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
        canonical_due=False, canonical_operation=lambda: None, offhours_phases=(phase,),
    )
    assert result.phase_statuses == {"cash_yield": "succeeded"}
    assert database.list_operational_incidents(limit=10) == []
