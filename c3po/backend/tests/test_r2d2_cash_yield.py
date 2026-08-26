from datetime import date, datetime, timezone
import hashlib
from pathlib import Path

import pytest

from app.config import Settings
from app.database import Database
from app.r2d2 import R2D2PaperService
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

    with pytest.raises(CashYieldDataError, match="2026-08-19"):
        service.run_latest()

    entries = database._r2d2_cash_yield_entries  # type: ignore[attr-defined]
    latest_run = database.latest_analysis_snapshot("r2d2_cash_yield_run", "R2D2_CASH_YIELD")
    assert [entry["session_date"] for entry in entries] == [
        date(2026, 8, 18),
        date(2026, 8, 20),
    ]
    assert len(http.calls) == 1
    assert latest_run is not None
    assert latest_run["outputs"]["status"] == "partial"
    assert latest_run["outputs"]["pending_sessions"] == [{
        "session_date": "2026-08-19",
        "source_observation_date": "2026-08-18",
        "reason": "Expected one Treasury observation for 2026-08-18, found 0",
    }]
    assert service.last_run_at() is None

    http.payload = _xml("2026-08-17", "2026-08-18", "2026-08-19")
    completed = service.run_latest()
    assert completed["status"] == "posted"
    assert completed["session_date"] == "2026-08-20"
    assert sorted(entry["session_date"] for entry in entries) == [
        date(2026, 8, 18),
        date(2026, 8, 19),
        date(2026, 8, 20),
    ]
