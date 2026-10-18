"""Decisor V1 in shadow (owner's direction of 2026-10-17; migration 052): per name per night COMPRA_PERMITIDA / OBSERVAR /
VETO with reason codes, over the SERVED official TP (internal when served); margin = buy-in AND the TP net of the measured
error clearing the market hurdle; freshness and quality vetoes; immutable records with two clocks, provenance and hashes
that every reader verifies; a flagged nightly phase that runs last; a read helper that answers only for the symbols asked."""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app import valuation_decision as decisor
from app import valuation_env
from app import valuation_official as official
from app.config import Settings
from app.database import Database
from app.valuation_official_engine import SOURCE_BLEND, SOURCE_INTERNAL
from app.valuation_v3_macro import canonical_payload_sha256, interpolate_us_five_year_rate
from app.valuation_worker_contract import VALUATION_WORKER_OFFHOURS_PHASES, VALUATION_WORKER_PHASES

ROOT = Path(__file__).resolve().parents[2]
CUT = datetime(2026, 10, 14, 3, 5, tzinfo=timezone.utc)  # 00:05 BRT Wednesday: the official cut after Tuesday's sessions
RUN = datetime(2026, 10, 14, 4, 30, tzinfo=timezone.utc)  # 01:30 BRT: the decisor's off-hours phase
SESSION = "2026-10-13"


def _database() -> Database:
    return Database(Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))


def _run(database: Database, *, now: datetime = RUN, **extra: Any) -> dict[str, Any]:
    """A RECORDED run: writes need the flag on (the worker and the CLI read the process's environment, ``valuation_env``)."""
    return decisor.run_shadow(database, now=now, write=True, enabled=True, **extra)


@contextmanager
def _activated_at(database: Database, at: datetime) -> Iterator[None]:
    """The automatic path dates an activation by the WALL clock — the day this suite runs — while the test world is the
    night of 2026-10-13: the generations a step activates are dated to the instant that step happened in that world, so
    ``generation_at`` (what the decisor reads) finds the generation in force at the run's clock, as on the host."""
    start = len(database._valuation_official_selections)
    yield
    for offset, generation in enumerate(database._valuation_official_selections[start:]):
        generation["activated_at"] = (at + timedelta(microseconds=offset)).isoformat()


def _row(symbol: str, *, tp: float, buy_in: float, price: float, market: str = "B3", **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "symbol": symbol, "our_tp": tp, "buy_in": buy_in, "price": price, "internal_tp": tp * 0.98, "internal_buy_in": buy_in * 0.98,
        "valuation_profile": "general", "valuation_confidence": 80.0, "method_dispersion_percent": 20.0, "fundamentals_as_of": "2026-09-30",
        "methods": {"dcf": tp}, "risk_score": 30.0, "as_of": "2026-10-13T21:00:00+00:00", "status": "full_match",
    }
    row.update({"tp_validation_status": "validated"} if market == "B3" else {"signal_quality": "validated"})
    return {**row, **extra}


def _universe(database: Database, market: str, rows: list[dict[str, Any]], at: datetime, *, selic: float = 0.14) -> str:
    outputs: dict[str, Any] = {"rows": rows, "universe_size": len(rows)}
    if market == "B3":
        outputs["macro"] = {"selic": selic, "ipca12m": 0.045}
    return database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", "mv-1",
                                           {"methodology_version": 32, "market": market, "source_manifest_sha256": "a" * 64}, outputs, at)


def _calibration(database: Database, market: str, at: datetime, *, status: str = "active", horizon: int = 90,
                 metrics: dict[str, Any] | None = None) -> str:
    return database.save_analysis_snapshot("valuation_calibration", f"{market}_POWER_MODEL", "mv-1", {"minimum_profile_samples": 15},
                                           {"status": status, "observed_horizon_days": horizon, "factors": {},
                                            "metrics": metrics if metrics is not None else {"general": {"samples": 20, "median_absolute_error_percent": 10.0},
                                                                                            "global": {"samples": 60, "median_absolute_error_percent": 12.0}}}, at)


def _tbill(database: Database, at: datetime, *, rate: float = 0.04, observed: str = SESSION, tamper: bool = False) -> str:
    package: dict[str, Any] = {"schema_version": "R2D2-CASH-YIELD-v2", "source": "U.S. Department of the Treasury", "observation_date": observed,
                               "annual_rate": rate, "available_at": "2026-10-14T00:00:00+00:00", "fetched_at": at.isoformat()}
    package["payload_sha256"] = canonical_payload_sha256(package)
    if tamper:
        package["annual_rate"] = rate * 2
    return database.save_analysis_snapshot("r2d2_cash_yield_rate", "US_TBILL_13_WEEK_COUPON_EQUIVALENT", "mv-1", {"observation_date": observed}, package, at)


def _selic(database: Database, at: datetime, *, observations: list[dict[str, Any]] | None = None) -> str:
    """The dated BCB SGS 432 package (valuation_v3_macro's shape): next-day availability, as its producer stamps it."""
    package: dict[str, Any] = {"schema_version": "VALUATION-V3-MACRO-v1", "engine_version": 3, "source": "Banco Central do Brasil SGS 432", "series": "SGS 432",
                               "as_of": SESSION, "fetched_at": at.isoformat(),
                               "observations": observations if observations is not None else
                               [{"observation_date": SESSION, "annual_rate": 0.14, "available_at": "2026-10-14T00:00:00+00:00"}]}
    package["payload_sha256"] = canonical_payload_sha256(package)
    return database.save_analysis_snapshot("valuation_macro_history", "B3_SELIC_REGIME", "mv-1", {}, package, at)


def _curve(database: Database, at: datetime, *, observed: str, as_of: str = SESSION, five_year: float | None = None) -> str:
    """The US 5Y package (valuation_v3_macro's shape): the producer takes the latest yields within 30 days of ``as_of``."""
    available = (datetime.fromisoformat(observed) + timedelta(days=1)).replace(tzinfo=timezone.utc).isoformat()
    points = [{"symbol": symbol, "tenor_years": tenor, "observation_date": observed, "annual_rate": rate, "available_at": available,
               "source": "EODHD Government Bonds"} for symbol, tenor, rate in (("US3Y.GBOND", 3, 0.038), ("US10Y.GBOND", 10, 0.045))]
    package: dict[str, Any] = {"schema_version": "VALUATION-V3-MACRO-v1", "engine_version": 3, "source": "EODHD Government Bonds", "as_of": as_of,
                               "fetched_at": at.isoformat(), "formula": "r3y + (2/7) * (r10y - r3y)", "points": points,
                               "interpolated_5y_rate": five_year if five_year is not None else interpolate_us_five_year_rate(0.038, 0.045)}
    package["payload_sha256"] = canonical_payload_sha256(package)
    return database.save_analysis_snapshot("valuation_macro_rates", "US_5Y_INTERPOLATED", "mv-1", {}, package, at)


def _night(database: Database, *, b3: list[dict[str, Any]] | None = None, us: list[dict[str, Any]] | None = None, selic: bool = True) -> dict[str, str]:
    """One official night: the three universe cycles (the generation activates when the third lands — dated then), the
    producers' calibration snapshots, the US cash-rate package and (``selic``) the dated SGS 432 package."""
    with _activated_at(database, CUT + timedelta(minutes=2, seconds=30)):
        cycles = {
            "B3": _universe(database, "B3", b3 if b3 is not None else [_row("PETR4", tp=45.0, buy_in=32.0, price=30.0), _row("VALE3", tp=70.0, buy_in=60.0, price=65.0)], CUT),
            "NASDAQ": _universe(database, "NASDAQ", us if us is not None else [_row("AAPL", tp=130.0, buy_in=105.0, price=100.0, market="NASDAQ")], CUT + timedelta(minutes=1)),
            "NYSE": _universe(database, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, market="NYSE")], CUT + timedelta(minutes=2)),
        }
    for market in official.MARKETS:
        _calibration(database, market, CUT + timedelta(minutes=3))
    _tbill(database, CUT + timedelta(minutes=4))
    if selic:
        _selic(database, CUT + timedelta(minutes=4))
    return cycles


GOOD_ERROR = {"status": "ok", "value": 0.10}
GOOD_RATE = {"status": "ok", "h_market": 0.14}


def _served(**extra: Any) -> dict[str, Any]:
    return {**_row("PETR4", tp=45.0, buy_in=32.0, price=30.0), "official_session_date": SESSION, **extra}


def _decide(row: dict[str, Any] | None = None, *, behind: int = 0, price: dict[str, Any] | None = None, error: dict[str, Any] = GOOD_ERROR,
            rate: dict[str, Any] = GOOD_RATE) -> dict[str, Any]:
    served = row if row is not None else _served()
    observation = price if price is not None else {"price": served["price"], "ask": None, "source": "official_cut", "session": served["official_session_date"]}
    return decisor.decide(served, expected_session=SESSION, tp_sessions_behind=behind, price=observation, error=error, rate=rate)


# ------------------------------------------------------------------ the pure verdict


def test_a_name_that_clears_every_gate_is_permitted_with_its_numbers() -> None:
    outcome = _decide()
    assert outcome["verdict"] == decisor.COMPRA_PERMITIDA and outcome["reason_codes"] == [decisor.ALL_GATES_PASSED]
    margin = outcome["checks"]["tp_margin"]
    assert margin["pass"] is True and margin["tp_after_error"] == pytest.approx(45.0 * 0.90) and margin["required"] == pytest.approx(30.0 * 1.14)
    assert outcome["checks"]["entry"] == {"pass": True, "entry_price": 30.0, "basis": "price", "buy_in": 32.0}
    assert outcome["checks"]["validated"] == {"pass": True, "field": "tp_validation_status", "value": "validated"}
    assert outcome["price"] == 30.0 and outcome["e_profile"] == 0.10 and outcome["h_market"] == 0.14
    # every class of code is disjoint, and the verdicts are exactly the migration's
    assert not set(decisor.VETO_CODES) & set(decisor.OBSERVAR_CODES) and decisor.VERDICTS == ("COMPRA_PERMITIDA", "OBSERVAR", "VETO")


@pytest.mark.parametrize(("change", "behind", "code"), [
    ({"tp_stale": True}, 0, "TP_STALE_FLAG"),
    ({"tp_stale": "statement superseded"}, 0, "TP_STALE_FLAG"),
    ({}, 2, "TP_SESSION_STALE"),
    ({"fundamentals_as_of": "2026-05-01"}, 0, "FUNDAMENTALS_STALE"),
    ({"fundamentals_as_of": None}, 0, "FUNDAMENTALS_DATE_UNKNOWN"),
    ({"tp_validation_status": "review_required"}, 0, "NOT_VALIDATED"),
    ({"method_dispersion_percent": 46.0}, 0, "METHOD_DISPERSION_HIGH"),
    ({"method_dispersion_percent": None}, 0, "METHOD_DISPERSION_UNKNOWN"),
    ({"valuation_confidence": 69.9}, 0, "CONFIDENCE_LOW"),
    ({"valuation_confidence": None}, 0, "CONFIDENCE_UNKNOWN"),
    ({"data_defects": ["restated revenue"]}, 0, "DATA_DEFECT"),
    ({"data_defect": True}, 0, "DATA_DEFECT"),
])
def test_every_freshness_and_quality_gate_vetoes(change: dict[str, Any], behind: int, code: str) -> None:
    outcome = _decide(_served(**change), behind=behind)
    assert outcome["verdict"] == decisor.VETO and code in outcome["reason_codes"] and decisor.ALL_GATES_PASSED not in outcome["reason_codes"]


def test_the_edges_of_the_freshness_gates() -> None:
    # one session behind is tolerated (a carried market) when the price was observed after the last session closed; two is not
    assert _decide(behind=1, price={"price": 30.0, "source": "latest_universe_cycle", "session": SESSION})["verdict"] == decisor.COMPRA_PERMITIDA
    # ...but never on the cut's own price: it is of the TP's session, so the last session's move was never observed (it would read 0 %)
    carried = _decide(behind=1, price={"price": 30.0, "source": "official_cut", "session": "2026-10-09"})
    assert carried["verdict"] == decisor.VETO and carried["reason_codes"] == ["PRICE_SESSION_STALE"]
    assert carried["checks"]["price_session"] == {"pass": False, "price_session": "2026-10-09", "expected_session": SESSION, "price_source": "official_cut"}
    assert carried["checks"]["price_move"]["move_percent"] == 0.0  # the move gate alone could not see it
    assert "PRICE_SESSION_STALE" in _decide(price={"price": 30.0, "source": "quote", "session": None})["reason_codes"]  # a session nobody can name
    assert _decide(_served(fundamentals_as_of="2026-05-29"))["verdict"] == decisor.COMPRA_PERMITIDA  # 137 days before 2026-10-13
    assert "FUNDAMENTALS_STALE" in _decide(_served(fundamentals_as_of="2026-05-28"))["reason_codes"]
    # the price moved more than 5 % since the cut, either way; no price at all is a veto too
    assert "PRICE_MOVED_SINCE_CUT" in _decide(price={"price": 31.6, "source": "quote", "session": SESSION})["reason_codes"]
    assert "PRICE_MOVED_SINCE_CUT" in _decide(price={"price": 28.4, "source": "quote", "session": SESSION})["reason_codes"]
    assert _decide(price={"price": 31.4, "source": "quote", "session": SESSION})["verdict"] == decisor.COMPRA_PERMITIDA
    unpriced = decisor.decide(_served(), expected_session=SESSION, tp_sessions_behind=0, price=None, error=GOOD_ERROR, rate=GOOD_RATE)
    assert unpriced["verdict"] == decisor.VETO and "PRICE_UNAVAILABLE" in unpriced["reason_codes"] and unpriced["checks"]["tp_margin"]["pass"] is None
    assert "PRICE_SESSION_STALE" not in unpriced["reason_codes"] and unpriced["checks"]["price_session"]["pass"] is None
    # a US row carries no tp_validation_status: its signal_quality decides
    us = {**_row("AAPL", tp=130.0, buy_in=105.0, price=100.0, market="NASDAQ"), "official_session_date": SESSION}
    assert _decide(us)["checks"]["validated"] == {"pass": True, "field": "signal_quality", "value": "validated"}
    assert "NOT_VALIDATED" in _decide({**us, "signal_quality": "provisional"})["reason_codes"]
    # a mark that is data, not a flag, is no defect: false-ish text and empty containers pass
    for clean in ("false", "", [], {}, None, False):
        assert _decide(_served(data_defects=clean, tp_stale=clean))["verdict"] == decisor.COMPRA_PERMITIDA


def test_no_margin_or_an_unmeasured_input_is_observar_never_permission() -> None:
    above = _decide(_served(buy_in=29.0))
    assert above["verdict"] == decisor.OBSERVAR and above["reason_codes"] == ["PRICE_ABOVE_BUY_IN"]
    thin = _decide(_served(our_tp=37.0))  # 37 × 0.9 = 33.3 < 30 × 1.14 = 34.2
    assert thin["verdict"] == decisor.OBSERVAR and thin["reason_codes"] == ["TP_MARGIN_INSUFFICIENT"] and thin["checks"]["tp_margin"]["pass"] is False
    warming = _decide(error={"status": "warming_up", "value": None})
    assert warming["verdict"] == decisor.OBSERVAR and warming["reason_codes"] == ["E_PROFILE_WARMING_UP"] and warming["checks"]["tp_margin"]["pass"] is None
    assert _decide(error={"status": "unavailable", "value": None})["reason_codes"] == ["E_PROFILE_UNAVAILABLE"]
    assert _decide(rate={"status": "unavailable", "h_market": None})["reason_codes"] == ["MARKET_RATE_UNAVAILABLE"]
    # a VETO keeps every failing code — the OBSERVAR ones too — in evaluation order
    both = _decide(_served(valuation_confidence=50.0, buy_in=29.0), error={"status": "warming_up", "value": None})
    assert both["verdict"] == decisor.VETO and both["reason_codes"] == ["CONFIDENCE_LOW", "E_PROFILE_WARMING_UP", "PRICE_ABOVE_BUY_IN"]


def test_the_ask_is_the_execution_price_when_the_observation_carries_one() -> None:
    outcome = _decide(price={"price": 30.0, "ask": 32.5, "source": "quote", "session": SESSION})
    assert outcome["checks"]["entry"] == {"pass": False, "entry_price": 32.5, "basis": "ask", "buy_in": 32.0}
    assert outcome["verdict"] == decisor.OBSERVAR and outcome["reason_codes"] == ["PRICE_ABOVE_BUY_IN"] and outcome["price"] == 32.5
    assert outcome["checks"]["tp_margin"]["required"] == pytest.approx(32.5 * 1.14)


# ------------------------------------------------------------------ the measured error and the market hurdle


def test_e_profile_is_the_producers_measured_median_absolute_error_and_warms_up_honestly() -> None:
    database = _database()
    assert decisor.profile_error(database, "B3", "general", at=RUN)["status"] == "unavailable"  # no calibration yet
    snapshot = _calibration(database, "B3", CUT)
    measured = decisor.profile_error(database, "B3", "general", at=RUN)
    assert measured["status"] == "ok" and measured["value"] == pytest.approx(0.10) and measured["snapshot_id"] == snapshot
    assert measured["samples"] == 20 and measured["basis"] == "general" and measured["calibration_status"] == "active"
    # causal: a calibration published after the decision instant is not read
    assert decisor.profile_error(database, "B3", "general", at=CUT - timedelta(seconds=1))["status"] == "unavailable"
    # a profile below its minimum samples warms up — unless the PREREG allows the global fallback
    assert decisor.profile_error(database, "B3", "growth", at=RUN)["status"] == "warming_up"
    fallback = decisor.profile_error(database, "B3", "growth", at=RUN, thresholds=replace(decisor.THRESHOLDS, allow_global_error_fallback=True))
    assert fallback["status"] == "ok" and fallback["basis"] == "global" and fallback["value"] == pytest.approx(0.12)
    # a calibration that is not active, or measured over a horizon out of range, warms up; a stale one is unavailable
    _calibration(database, "NYSE", CUT, status="warming_up")
    assert decisor.profile_error(database, "NYSE", "general", at=RUN)["status"] == "warming_up"
    _calibration(database, "NASDAQ", CUT, horizon=200)
    assert decisor.profile_error(database, "NASDAQ", "general", at=RUN)["status"] == "warming_up"
    assert decisor.profile_error(database, "B3", "general", at=CUT + timedelta(days=8))["status"] == "unavailable"
    # a producer that does not publish the metric yet (a calibration written before this change) gives no permission
    _calibration(database, "B3", CUT + timedelta(minutes=1), metrics={"general": {"samples": 20, "mean_absolute_error_percent": 9.0}})
    old = decisor.profile_error(database, "B3", "general", at=RUN)
    assert old["status"] == "unavailable" and "median_absolute_error_percent" in old["detail"]


def test_h_market_comes_from_the_first_fresh_declared_rate_source() -> None:
    database = _database()
    _night(database)
    generation = official.generation_at(database, RUN)
    b3 = decisor.market_rate(database, "B3", at=RUN, generation=generation)
    assert b3["status"] == "ok" and b3["source"] == decisor.RATE_BCB_SGS_432 and b3["observed_at"] == SESSION and b3["undated"] is False
    assert b3["annual_rate"] == 0.14 and b3["h_market"] == pytest.approx(0.14) and b3["payload_sha256"]
    us = decisor.market_rate(database, "NASDAQ", at=RUN, generation=generation)
    assert us["status"] == "ok" and us["source"] == decisor.RATE_US_TBILL_13W and us["h_market"] == pytest.approx(0.04) and us["payload_sha256"]
    # the premium and the horizon of the frozen block apply: h = (1 + r) ** years - 1 + premium
    shaped = decisor.market_rate(database, "NYSE", at=RUN, generation=generation,
                                 thresholds=replace(decisor.THRESHOLDS, market_premium=0.02, tp_horizon_years=2.0))
    assert shaped["h_market"] == pytest.approx(1.04 ** 2 - 1 + 0.02)
    # a stale observation is skipped for the next source; none fresh → unavailable, naming what was tried
    late = decisor.market_rate(database, "NASDAQ", at=RUN + timedelta(days=11), generation=generation)
    assert late["status"] == "unavailable" and [item["source"] for item in late["tried"]] == [decisor.RATE_US_TBILL_13W, decisor.RATE_US_5Y]
    # a package whose hash does not verify is never read
    tampered = _database()
    _tbill(tampered, CUT, tamper=True)
    refused = decisor.market_rate(tampered, "NYSE", at=RUN, generation=None)
    assert refused["status"] == "unavailable" and refused["tried"][0]["detail"] == "package hash does not verify"
    # the B3 hurdle reads the dated SGS 432 observation AVAILABLE by then (the next day's is not, whatever the package holds)
    _selic(tampered, CUT, observations=[{"observation_date": "2026-10-12", "annual_rate": 0.1415, "available_at": "2026-10-13T00:00:00+00:00"},
                                        {"observation_date": "2026-10-14", "annual_rate": 0.99, "available_at": "2026-10-15T00:00:00+00:00"}])
    sgs = decisor.market_rate(tampered, "B3", at=RUN, generation=None)
    assert sgs["status"] == "ok" and sgs["source"] == decisor.RATE_BCB_SGS_432 and sgs["annual_rate"] == 0.1415 and sgs["observed_at"] == "2026-10-12"
    # a T-bill observation not yet available at the run's clock is not read
    early = _database()
    _tbill(early, datetime(2026, 10, 13, 22, 0, tzinfo=timezone.utc))  # available 2026-10-14T00:00Z
    unavailable = decisor.market_rate(early, "NASDAQ", at=datetime(2026, 10, 13, 23, 0, tzinfo=timezone.utc), generation=None)
    assert unavailable["status"] == "unavailable" and unavailable["tried"][0]["detail"] == "the observation was not available at the run's clock"


def test_the_b3_cycles_selic_is_undated_and_never_passes_for_fresh_unless_the_block_admits_it() -> None:
    # the B3 producer falls back to a hard-coded governor constant when both of its feeds fail, and the cycle records only the
    # value: its publication says nothing about when the Selic was observed — without a dated SGS 432 there is no hurdle
    database = _database()
    cycles = _night(database, selic=False)
    generation = official.generation_at(database, RUN)
    refused = decisor.market_rate(database, "B3", at=RUN, generation=generation)
    assert refused["status"] == "unavailable" and [item["source"] for item in refused["tried"]] == [decisor.RATE_BCB_SGS_432, decisor.RATE_B3_CYCLE_SELIC]
    assert refused["tried"][1]["detail"].startswith("undated:")
    receipt = decisor.run_shadow(database, now=RUN)
    assert receipt["markets"]["B3"]["reasons"]["MARKET_RATE_UNAVAILABLE"] == 2 and receipt["markets"]["B3"]["verdicts"]["COMPRA_PERMITIDA"] == 0
    # a block that admits it knowingly reads it, aged by the cycle's publication and recorded as undated
    admitting = replace(decisor.THRESHOLDS, undated_rate_sources_admitted=(decisor.RATE_B3_CYCLE_SELIC,))
    admitted = decisor.market_rate(database, "B3", at=RUN, generation=generation, thresholds=admitting)
    assert admitted["status"] == "ok" and admitted["source"] == decisor.RATE_B3_CYCLE_SELIC and admitted["undated"] is True
    assert admitted["snapshot_id"] == cycles["B3"] and admitted["annual_rate"] == 0.14
    # causal: a cycle published after the run's clock is not read, admitted or not
    assert decisor.market_rate(database, "B3", at=CUT - timedelta(seconds=1), generation=generation, thresholds=admitting)["status"] == "unavailable"
    # a dated SGS observation comes first whenever it is fresh
    _selic(database, CUT + timedelta(minutes=5))
    assert decisor.market_rate(database, "B3", at=RUN, generation=generation, thresholds=admitting)["source"] == decisor.RATE_BCB_SGS_432


def test_the_us_5y_fallback_is_aged_by_its_yields_observation_not_by_the_package_as_of() -> None:
    database = _database()
    # a package asked for today, built from yields observed 25 days earlier (the producer looks back 30 days): stale
    _curve(database, CUT, observed="2026-09-18", as_of=SESSION)
    stale = decisor.market_rate(database, "NASDAQ", at=RUN, generation=None)
    assert stale["status"] == "unavailable" and [item["source"] for item in stale["tried"]] == [decisor.RATE_US_TBILL_13W, decisor.RATE_US_5Y]
    assert stale["tried"][1]["detail"] == "observation older than 10 days"
    _curve(database, CUT + timedelta(minutes=1), observed=SESSION)
    fresh = decisor.market_rate(database, "NYSE", at=RUN, generation=None)
    assert fresh["status"] == "ok" and fresh["source"] == decisor.RATE_US_5Y and fresh["observed_at"] == SESSION
    assert fresh["h_market"] == pytest.approx(0.038 + 2 / 7 * (0.045 - 0.038))
    # a package that does not validate as V3 validates it (here: an interpolation that does not reconcile) is never read
    _curve(database, CUT + timedelta(minutes=2), observed=SESSION, five_year=0.09)
    broken = decisor.market_rate(database, "NYSE", at=RUN, generation=None)
    assert broken["status"] == "unavailable" and broken["tried"][1]["detail"].startswith("package does not validate")


# ------------------------------------------------------------------ the nightly run and its records


def test_a_shadow_run_records_one_verified_verdict_per_served_name_with_its_provenance() -> None:
    database = _database()
    cycles = _night(database)
    generation = official.current_generation(database)
    assert generation is not None and generation["source"] == SOURCE_BLEND
    receipt = _run(database)
    assert receipt["status"] == "recorded" and receipt["recorded"] == 4 and receipt["generation_id"] == generation["generation_id"]
    assert receipt["markets"]["B3"]["verdicts"] == {"COMPRA_PERMITIDA": 1, "OBSERVAR": 1, "VETO": 0}  # VALE3: 65 > buy-in 60
    assert receipt["markets"]["NASDAQ"]["verdicts"]["COMPRA_PERMITIDA"] == 1 and receipt["markets"]["NYSE"]["reasons"] == {"PRICE_ABOVE_BUY_IN": 1, "TP_MARGIN_INSUFFICIENT": 1}  # KO: 65 > 60; 70 × 0.9 < 65 × 1.04
    # the receipt is aggregate: it names no symbol
    dumped = json.dumps(receipt)
    assert not any(symbol in dumped for symbol in ("PETR4", "VALE3", "AAPL", "KO"))
    petr = database.list_valuation_decisions("B3", "PETR4")
    assert len(petr) == 1
    record = petr[0]
    served = official.official_row(database, "B3", "PETR4", generation=generation)
    assert served is not None
    # the TP read is the SERVED row, by identity; the record's clocks and session are the run's
    assert (record["tp"], record["buy_in"], record["tp_source"], record["tp_cycle_id"]) == (served["our_tp"], served["buy_in"], SOURCE_BLEND, cycles["B3"])
    assert record["tp_row_sha256"] == served["official_row_sha256"] and record["generation_id"] == generation["generation_id"]
    assert record["prediction_instant"] == RUN.isoformat() and record["published_at"] >= record["prediction_instant"]
    assert record["session_date"] == SESSION and record["mode"] == "shadow" and record["verdict"] == decisor.COMPRA_PERMITIDA
    # provenance: the calibration and the rate it applied, the price source, the thresholds' hash
    inputs = record["inputs"]
    assert inputs["e_profile"]["status"] == "ok" and inputs["market_rate"]["source"] == decisor.RATE_BCB_SGS_432
    assert inputs["price"]["source"] == "official_cut" and inputs["price"]["session"] == SESSION and inputs["tp_record"]["row_sha256"] == served["official_row_sha256"]
    assert record["thresholds_sha256"] == inputs["thresholds_sha256"] == decisor.thresholds_sha256() and inputs["prereg_frozen"] is False
    # both hashes recompute
    core = {key: value for key, value in record.items() if key not in ("id", "row_sha256")}
    assert record["row_sha256"] == official.canonical_sha256(core) and record["inputs_sha256"] == official.canonical_sha256(inputs)
    # idempotent per (run, market, symbol): replaying the run's records adds nothing
    assert database.insert_valuation_decisions([dict(item) for item in database._valuation_decisions]) == 0


def _switch_to_internal(database: Database, cycles: dict[str, str], monkeypatch: pytest.MonkeyPatch, *, at: datetime) -> dict[str, Any]:
    """The mesa's explicit P1 switch to the internal source, dated ``at`` (the order carries the mesa's clock)."""
    report = official.before_after_report(database, cycles=cycles, targeted={})
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)
    return official.select_generation(database, cycles=cycles, now=at, activated_by="mesa", reason="P1 switch", source=SOURCE_INTERNAL,
                                      source_version="32", before_after_sha256=report["report_sha256"])


def test_the_decisor_reads_the_internal_tp_when_the_selection_serves_it(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database()
    cycles = _night(database)
    _switch_to_internal(database, cycles, monkeypatch, at=CUT + timedelta(minutes=20))
    _run(database)
    record = database.list_valuation_decisions("B3", "PETR4")[0]
    assert record["tp_source"] == SOURCE_INTERNAL and record["tp"] == pytest.approx(45.0 * 0.98) and record["buy_in"] == pytest.approx(32.0 * 0.98)


def test_a_run_reads_the_generation_in_force_at_its_clock_never_a_later_one(monkeypatch: pytest.MonkeyPatch) -> None:
    # a replay (or a backfill, or the PREREG grading a past night) decides what that night saw: a switch ordered after the run's
    # clock is not read by it, while a run after the switch reads the switched TP
    database = _database()
    cycles = _night(database)
    blend = official.current_generation(database)
    assert blend is not None
    internal = _switch_to_internal(database, cycles, monkeypatch, at=RUN + timedelta(hours=1))
    replay = _run(database)
    assert replay["generation_id"] == blend["generation_id"] and replay["tp_source"] == SOURCE_BLEND
    _run(database, now=RUN + timedelta(hours=2))
    newest, replayed = database.list_valuation_decisions("B3", "PETR4")
    assert (replayed["generation_id"], replayed["tp_source"]) == (blend["generation_id"], SOURCE_BLEND) and replayed["tp"] == 45.0
    assert (newest["generation_id"], newest["tp_source"]) == (internal["generation_id"], SOURCE_INTERNAL)
    # before the first generation was activated there is nothing to decide
    assert decisor.run_shadow(database, now=CUT)["status"] == "no_generation"


def test_a_served_row_predicted_after_the_runs_clock_is_not_decided(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database()
    _night(database)
    served_rows = decisor._served_rows

    def shifted(db: Any, market: str, generation: Any) -> dict[str, dict[str, Any]]:
        rows = served_rows(db, market, generation)
        if "PETR4" in rows:
            rows["PETR4"]["prediction_instant"] = (RUN + timedelta(seconds=1)).isoformat()
        return rows

    monkeypatch.setattr(decisor, "_served_rows", shifted)
    receipt = _run(database)
    assert receipt["markets"]["B3"]["tp_after_run_instant"] == 1 and receipt["markets"]["B3"]["decided"] == 1
    assert database.list_valuation_decisions("B3", "PETR4") == [] and len(database.list_valuation_decisions("B3", "VALE3")) == 1


def test_a_newer_universe_cycle_is_the_price_and_a_targeted_admission_is_decided() -> None:
    database = _database()
    _night(database)
    with _activated_at(database, CUT + timedelta(minutes=5, seconds=30)):
        targeted = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 32},
                                                   {"row": _row("WEGE3", tp=60.0, buy_in=45.0, price=44.0)}, CUT + timedelta(minutes=5))
    generation = official.current_generation(database)
    assert generation is not None and generation["targeted"] == {"WEGE3": targeted}
    _run(database)
    wege = database.list_valuation_decisions("B3", "WEGE3")[0]
    assert wege["tp_cycle_id"] == targeted and wege["inputs"]["tp_record"]["scope"] == "targeted" and wege["verdict"] == decisor.COMPRA_PERMITIDA
    # a quote handed over by the caller is the price (its ask the execution price) — and the move since the cut is measured on it
    quoted = decisor.run_shadow(database, now=RUN, quotes={("B3", "PETR4"): {"price": 33.0, "ask": 33.1, "as_of": RUN, "source": "eodhd_live"}})
    assert quoted["status"] == "dry_run" and quoted["markets"]["B3"]["reasons"]["PRICE_MOVED_SINCE_CUT"] == 1
    assert len(database.list_valuation_decisions("B3", "PETR4")) == 1  # a dry run writes nothing


def test_a_callers_quote_is_for_a_dry_run_only_and_a_stale_one_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database()
    _night(database)
    live = {("B3", "PETR4"): {"price": 33.0, "ask": 33.1, "as_of": RUN, "source": "eodhd_live"}}
    # a run on quotes never records: nothing intraday replaces the nightly verdicts the lab reads
    with pytest.raises(ValueError, match="dry run"):
        _run(database, quotes=live)
    # and no run records while the flag is off — whoever calls
    with pytest.raises(ValueError, match="C3PO_VALUATION_DECISOR_SHADOW is off"):
        decisor.run_shadow(database, now=RUN, write=True, enabled=False)
    monkeypatch.delenv(valuation_env.DECISOR_SHADOW_ENV, raising=False)  # the process's own flag (the worker's and the CLI's): off by default
    with pytest.raises(ValueError, match="C3PO_VALUATION_DECISOR_SHADOW is off"):
        decisor.run_shadow(database, now=RUN, write=True)
    assert database._valuation_decisions == [] and decisor.last_run_at(database) is None
    # a quote older than the block's limit, from after the run's clock, or undated is refused: the nightly sources answer
    for refused in ({"price": 33.0, "as_of": RUN - timedelta(minutes=16)}, {"price": 33.0, "as_of": RUN + timedelta(minutes=1)}, {"price": 33.0},
                    {"price": 33.0, "as_of": "not a time"}, {"price": 0.0, "as_of": RUN}):
        receipt = decisor.run_shadow(database, now=RUN, quotes={("B3", "PETR4"): refused})
        assert receipt["markets"]["B3"]["quotes_refused"] == 1 and "PRICE_MOVED_SINCE_CUT" not in receipt["markets"]["B3"]["reasons"], refused
    fresh = decisor.run_shadow(database, now=RUN, quotes={("B3", "PETR4"): {"price": 33.0, "as_of": RUN - timedelta(minutes=15)}})
    assert fresh["markets"]["B3"]["quotes_refused"] == 0 and fresh["markets"]["B3"]["reasons"]["PRICE_MOVED_SINCE_CUT"] == 1
    price = decisor._price_observation({"price": 30.0, "official_session_date": SESSION, "prediction_instant": CUT.isoformat()}, market="B3", symbol="PETR4",
                                       at=RUN, quotes={("B3", "PETR4"): {"price": 33.0, "as_of": RUN - timedelta(hours=2)}}, latest_universe=None)
    assert price["source"] == "official_cut" and price["quote_refused"] == "older than 15 minutes at the run's clock"


def test_a_tp_one_session_behind_is_never_decided_on_a_session_nobody_observed() -> None:
    # the canonical cut failed Wednesday night: Thursday 01:30 BRT the generation still serves Tuesday's TP (one session behind,
    # tolerated) and no cycle was published after Wednesday's close — the cut's own price would read a 0 % move
    database = _database()
    _night(database)
    thursday = RUN + timedelta(days=1)
    receipt = decisor.run_shadow(database, now=thursday)
    assert receipt["markets"]["B3"]["expected_session"] == "2026-10-14" and "TP_SESSION_STALE" not in receipt["markets"]["B3"]["reasons"]
    for market in official.MARKETS:
        assert receipt["markets"][market]["verdicts"]["COMPRA_PERMITIDA"] == 0
        assert receipt["markets"][market]["reasons"]["PRICE_SESSION_STALE"] == receipt["markets"][market]["decided"]
    # a cycle published after Wednesday's close observes the session: the generation keeps the old cycle (this one has an
    # unusable row, so it is not selectable), and its price is the one the verdict is taken at
    generation = official.current_generation(database)
    assert generation is not None
    _universe(database, "B3", [_row("PETR4", tp=46.0, buy_in=33.0, price=30.6), _row("BROKEN3", tp=10.0, buy_in=8.0, price=0.0)],
              datetime(2026, 10, 15, 3, 5, tzinfo=timezone.utc))
    assert official.current_generation(database)["generation_id"] == generation["generation_id"]  # type: ignore[index]
    _run(database, now=thursday)
    petr = database.list_valuation_decisions("B3", "PETR4")[0]
    assert petr["verdict"] == decisor.COMPRA_PERMITIDA and petr["tp"] == 45.0  # the SERVED TP, the newer cycle's price
    assert petr["inputs"]["price"]["source"] == "latest_universe_cycle" and petr["inputs"]["price"]["session"] == "2026-10-14"
    assert petr["checks"]["tp_session_age"]["sessions_behind"] == 1 and petr["checks"]["price_move"]["move_percent"] == pytest.approx(2.0)
    vale = database.list_valuation_decisions("B3", "VALE3")[0]  # not quoted by the newer cycle: only the cut's price
    assert vale["verdict"] == decisor.VETO and "PRICE_SESSION_STALE" in vale["reason_codes"]


def test_last_run_at_closes_the_night_only_over_the_generation_in_force() -> None:
    database = _database()
    assert decisor.last_run_at(database) is None and decisor.run_shadow(database, now=RUN)["status"] == "no_generation"
    assert decisor.last_run_at(database) is None
    _night(database)
    assert decisor.last_run_at(database) is None
    receipt = _run(database)
    assert decisor.last_run_at(database) == datetime.fromisoformat(receipt["published_at"])
    # a generation activated later in the window (a canonical retry, a new cycle) makes the night due again
    _universe(database, "NYSE", [_row("KO", tp=72.0, buy_in=60.0, price=58.0, market="NYSE")], CUT + timedelta(minutes=30))
    assert decisor.last_run_at(database) is None


def test_the_lab_reads_only_the_symbols_it_asks_and_no_permission_outlives_its_session() -> None:
    database = _database()
    _night(database)
    _run(database)
    intraday = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)
    views = decisor.latest_verdicts(database, "US", ["aapl", "KO", "MSFT"], now=intraday)
    assert set(views) == {"AAPL", "KO"}  # MSFT has no verdict: absent, never invented
    assert views["AAPL"]["market"] == "NASDAQ" and views["AAPL"]["current"] is True and views["AAPL"]["effective_verdict"] == decisor.COMPRA_PERMITIDA
    assert views["AAPL"]["session_current"] is True and views["AAPL"]["tp_served"] is True
    assert views["KO"]["effective_verdict"] == decisor.OBSERVAR and views["KO"]["effective_reason_codes"] == ["PRICE_ABOVE_BUY_IN", "TP_MARGIN_INSUFFICIENT"]
    petr = decisor.latest_verdict(database, "B3", "PETR4.SA", now=intraday)
    assert petr is not None and petr["verdict"] == decisor.COMPRA_PERMITIDA and petr["mode"] == "shadow"
    assert decisor.latest_verdicts(database, "B3", [], now=intraday) == {}
    # two sessions later the same verdict is no permission: served as VETO / VERDICT_NOT_CURRENT
    stale = decisor.latest_verdict(database, "B3", "PETR4", now=datetime(2026, 10, 16, 15, 0, tzinfo=timezone.utc))
    assert stale is not None and stale["current"] is False and stale["verdict"] == decisor.COMPRA_PERMITIDA
    assert stale["effective_verdict"] == decisor.VETO and stale["effective_reason_codes"] == [decisor.VERDICT_NOT_CURRENT]


def test_a_verdict_is_no_permission_once_its_tp_is_no_longer_served(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database()
    cycles = _night(database)
    _run(database)
    intraday = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)  # 12:00 BRT: inside the session the verdict was decided for
    # a targeted admission of ANOTHER name after the run is a new generation that still serves the verdict's TP: it stays current
    with _activated_at(database, RUN + timedelta(hours=4)):
        targeted = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 32},
                                                   {"row": _row("WEGE3", tp=60.0, buy_in=45.0, price=44.0)}, RUN + timedelta(hours=4))
    admitted = official.current_generation(database)
    assert admitted is not None and admitted["targeted"] == {"WEGE3": targeted}
    kept = decisor.latest_verdict(database, "B3", "PETR4", now=intraday)
    assert kept is not None and kept["generation_id"] != admitted["generation_id"]
    assert kept["tp_served"] is True and kept["current"] is True and kept["effective_verdict"] == decisor.COMPRA_PERMITIDA
    # the mesa switches the source at 09:00 BRT, outside the decisor's window: the TP and buy-in the verdict read are no longer served
    _switch_to_internal(database, cycles, monkeypatch, at=datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc))
    switched = decisor.latest_verdict(database, "B3", "PETR4", now=intraday)
    assert switched is not None and switched["session_current"] is True and switched["tp_served"] is False and switched["current"] is False
    assert switched["verdict"] == decisor.COMPRA_PERMITIDA and switched["effective_verdict"] == decisor.VETO
    assert switched["effective_reason_codes"] == [decisor.VERDICT_TP_NOT_SERVED]
    # asked at an instant before the switch, the generation in force then still served it
    assert decisor.latest_verdict(database, "B3", "PETR4", now=datetime(2026, 10, 14, 11, 0, tzinfo=timezone.utc))["current"] is True  # type: ignore[index]
    # a later session AND another TP: both reasons are named
    later = decisor.latest_verdict(database, "B3", "PETR4", now=datetime(2026, 10, 16, 15, 0, tzinfo=timezone.utc))
    assert later is not None and later["effective_reason_codes"] == [decisor.VERDICT_NOT_CURRENT, decisor.VERDICT_TP_NOT_SERVED]


def test_a_stored_decision_that_does_not_verify_is_never_served(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(decisor, "_integrity_logged", set())
    database = _database()
    _night(database)
    _run(database)
    stored = next(item for item in database._valuation_decisions if item["symbol"] == "KO")
    stored["verdict"] = decisor.COMPRA_PERMITIDA  # an edit in place: the hash no longer recomputes
    caplog.set_level(logging.INFO, logger="app.valuation_decision")
    assert database.list_valuation_decisions("NYSE", "KO") == [] and decisor.latest_verdict(database, "NYSE", "KO", now=RUN) is None
    levels = [record.levelno for record in caplog.records if "is not served" in record.getMessage()]
    assert levels == [logging.WARNING, logging.INFO]
    other = next(item for item in database._valuation_decisions if item["symbol"] == "AAPL")
    other["inputs"]["price"]["price"] = 1.0  # provenance edited: inputs_sha256 refuses it
    assert database.list_valuation_decisions("NASDAQ", "AAPL") == []


def test_the_double_mirrors_the_tables_checks() -> None:
    database = _database()
    _night(database)
    decisor.run_shadow(database, now=RUN, write=False)
    generation = official.current_generation(database)
    row = official.official_row(database, "B3", "PETR4", generation=generation)
    assert row is not None
    outcome = _decide({**row, "official_session_date": SESSION})
    good = decisor.decision_record(run_id="r", market="B3", symbol="PETR4", session_date=SESSION, prediction_instant=RUN, published_at=RUN,
                                   row=row, outcome=outcome, inputs={}, thresholds_hash=decisor.thresholds_sha256())
    with pytest.raises(ValueError, match="precedes prediction_instant"):
        decisor.decision_record(run_id="r", market="B3", symbol="PETR4", session_date=SESSION, prediction_instant=RUN, published_at=RUN - timedelta(seconds=1),
                                row=row, outcome=outcome, inputs={}, thresholds_hash=decisor.thresholds_sha256())
    with pytest.raises(ValueError, match="CHECK"):
        database.insert_valuation_decisions([good, {**good, "id": "x", "symbol": "VALE3", "mode": "live"}])
    with pytest.raises(ValueError, match="CHECK"):
        database.insert_valuation_decisions([{**good, "verdict": "COMPRAR"}])
    with pytest.raises(ValueError, match="NOT NULL"):
        database.insert_valuation_decisions([{**good, "tp_row_sha256": None}])
    assert database._valuation_decisions == []  # a refused batch stores nothing
    assert database.insert_valuation_decisions([good]) == 1 and database.insert_valuation_decisions([{**good, "id": "again"}]) == 0


def test_the_prereg_freeze_refuses_any_other_block(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database()
    _night(database)
    monkeypatch.setattr(decisor, "PREREG_THRESHOLDS_SHA256", decisor.thresholds_sha256())
    receipt = decisor.run_shadow(database, now=RUN, write=False)
    assert receipt["prereg_frozen"] is True
    with pytest.raises(ValueError, match="not the block the PREREG froze"):
        decisor.run_shadow(database, now=RUN, thresholds=replace(decisor.THRESHOLDS, max_price_move_percent=9.0))
    assert database._valuation_decisions == []


# ------------------------------------------------------------------ PostgreSQL shape, migration, worker


def test_the_postgresql_reader_rebuilds_the_hashed_shape_and_the_writer_binds_every_column(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database()
    _night(database)
    _run(database)
    record = database.list_valuation_decisions("B3", "PETR4")[0]
    pg = Database(Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False, database_url="postgresql://configured"))
    sao_paulo = ZoneInfo("America/Sao_Paulo")
    row = []
    for key in Database._DECISION_KEYS:  # what psycopg hands back: Decimal NUMERICs, aware datetimes in the session zone, JSON decoded
        value = record[key]
        if key in ("tp", "buy_in", "price", "e_profile", "h_market") and value is not None:
            value = Decimal(repr(value))
        elif key in ("prediction_instant", "published_at", "tp_prediction_instant"):
            value = datetime.fromisoformat(value).astimezone(sao_paulo)
        elif key == "checks":
            value = json.dumps(value)  # a driver that leaves JSONB as text is decoded too
        row.append(value)
    assert pg._decision_record(tuple(row)) == record
    row[Database._DECISION_KEYS.index("verdict")] = decisor.VETO
    assert pg._decision_record(tuple(row)) is None

    statements: list[tuple[str, Any]] = []

    class Recording:
        rowcount = 1

        def execute(self, query: str, params: Any = None) -> "Recording":
            statements.append((" ".join(query.split()), params))
            return self

        def commit(self) -> None:
            return None

        def fetchall(self) -> list[Any]:
            return []

        def fetchone(self) -> Any:
            return None

    @contextmanager
    def fake_connection() -> Any:
        yield Recording()

    monkeypatch.setattr(pg, "connection", fake_connection)
    assert pg.insert_valuation_decisions([record]) == 1
    query, params = statements[0]
    assert query.count("%s") == len(params) == len(Database._DECISION_KEYS) and "ON CONFLICT (run_id, market, symbol) DO NOTHING" in query
    assert params[1] == decisor.DECISION_SCHEMA and json.loads(params[11]) == record["reason_codes"] and params[17] == Decimal(repr(record["tp"]))
    assert pg.latest_valuation_decisions("B3", ["PETR4"]) == {} and pg.latest_valuation_decision_run() is None
    assert "SELECT DISTINCT ON (symbol)" in statements[1][0] and "symbol = ANY(%s)" in statements[1][0]
    assert "ORDER BY symbol, prediction_instant DESC, published_at DESC, created_at DESC" in statements[1][0]
    assert "ORDER BY published_at DESC, created_at DESC LIMIT 1" in statements[2][0]


def test_the_migration_is_an_append_only_shadow_table_with_the_records_discipline() -> None:
    sql = (ROOT / "db" / "052_valuation_decisions.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS valuation_decisions" in sql and "UNIQUE (run_id, market, symbol)" in sql
    assert "mode TEXT NOT NULL CHECK (mode IN ('shadow'))" in sql
    assert "verdict TEXT NOT NULL CHECK (verdict IN ('COMPRA_PERMITIDA', 'OBSERVAR', 'VETO'))" in sql and Database._DECISION_VERDICTS == decisor.VERDICTS
    assert "CHECK (published_at >= prediction_instant)" in sql and "REFERENCES valuation_official_selection(generation_id)" in sql
    assert "BEFORE UPDATE OR DELETE ON valuation_decisions" in sql and "BEFORE TRUNCATE ON valuation_decisions" in sql
    statements = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    assert "DROP TABLE" not in statements and "DELETE FROM" not in statements and "UPDATE valuation_decisions" not in statements
    assert all(line.startswith(("CREATE TABLE IF NOT EXISTS", "CREATE INDEX IF NOT EXISTS", "CREATE OR REPLACE FUNCTION", "DROP TRIGGER IF EXISTS", "CREATE TRIGGER"))
               for line in statements.splitlines() if line and line[0].isalpha() and line.split()[0] in ("CREATE", "DROP"))
    for column in Database._DECISION_COLUMNS.split(", "):
        name = column.split("::")[0]
        assert f"\n    {name} " in sql, name


def test_the_phase_decides_once_per_generation_inside_the_worker_iteration() -> None:
    from app.valuation_worker import OffhoursPhase, run_worker_iteration

    database = _database()
    _night(database)
    phase = OffhoursPhase("decisor_shadow", lambda: decisor.last_run_at(database), lambda: _run(database))
    local = RUN.astimezone(ZoneInfo("America/Sao_Paulo"))
    first = run_worker_iteration(database, now=local, canonical_due=False, canonical_operation=lambda: None, offhours_phases=(phase,))
    assert first.phase_statuses == {"decisor_shadow": "succeeded"} and len(database._valuation_decisions) == 4
    runs = [run for run in database._ingestion_runs.values() if run["source_code"] == VALUATION_WORKER_PHASES["decisor_shadow"]["code"]]
    assert [run["status"] for run in runs] == ["succeeded"]
    # the night is done: the next wake inside the window decides nothing again over the same generation
    second = run_worker_iteration(database, now=local + timedelta(minutes=30), canonical_due=False, canonical_operation=lambda: None, offhours_phases=(phase,))
    assert second.phase_statuses == {} and len(database._valuation_decisions) == 4


def test_the_nightly_phase_is_flagged_off_and_runs_last(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(valuation_env.DECISOR_SHADOW_ENV, raising=False)
    assert valuation_env.decisor_shadow_enabled() is False and "valuation_decisor_shadow" not in Settings.model_fields  # the environment, never config.py
    monkeypatch.setenv(valuation_env.DECISOR_SHADOW_ENV, "true")
    assert valuation_env.decisor_shadow_enabled() is True
    assert VALUATION_WORKER_PHASES["decisor_shadow"]["code"] == "valuation-worker-decisor-shadow"
    assert "decisor_shadow" not in VALUATION_WORKER_OFFHOURS_PHASES  # flag-gated, like price_history
    source = (ROOT / "backend" / "app" / "valuation_worker.py").read_text(encoding="utf-8")
    phases = source[source.index("offhours_phases = ("):source.index("while True:")]
    assert phases.index("OffhoursPhase(\"decisor_shadow\"") > max(phases.index("CASH_YIELD_PHASE_KEY"), phases.index("\"price_history\""))
    assert "if valuation_env.decisor_shadow_enabled() else ()" in phases
    assert "run_decisor_shadow(database, write=True)" in phases  # the phase records; run_shadow refuses it with the flag off
