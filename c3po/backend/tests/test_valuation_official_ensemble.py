"""The ensemble switch (``valuation_official`` rev 10, ``official_ensemble_v1``): built before the PIT grid reports, merged only
after its PASS and the owner's acceptance. A third official source recorded from the SAME producer cycles: a US stock the
nightly live producer evaluated with origin ``ensemble`` carries the ensemble's primary TP (owner 28/10/2026: every US name,
the PIT-tested ones and the others alike — ``ensemble_pit_tested`` labels them), its buy-in by the internal buy-in's rule; B3,
ETFs and every name not evaluable carry the internal TP bit for bit (``fallback_internal:<reason>``). Nothing served changes until
the order; the switch is locked by its own lock and cites its own receipt (internal → ensemble); the rollback to the internal
source is never locked; an ensemble TP outside the tested population is never a buy permission (decisor, R2D2)."""
from __future__ import annotations

import dataclasses
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app import valuation_decision as decisor
from app import valuation_live_ensemble as live
from app import valuation_official as official
from app.config import Settings
from app.database import Database
from app.market_data import us_screener
from app.market_data.b3_screener import B3ScreenerService
from app.market_data.us_screener import USScreeningService
from app.valuation_ensemble_aggregation import aggregate_grid_variants
from app.valuation_ensemble_models import MODEL_IDS, ModelValue
from app.valuation_official_engine import (ENSEMBLE_FALLBACK_PREFIX, ENSEMBLE_MIRRORED_FIELDS, ENSEMBLE_ORIGIN, ENSEMBLE_POLICY, OFFICIAL_SOURCES,
                                           SOURCE_BLEND, SOURCE_ENSEMBLE, SOURCE_INTERNAL, ensemble_consensus_weight_v1, ensemble_fallback_view,
                                           official_buy_in_v1, official_ensemble_buy_in_v1, official_entry_discount_v1)
from tests import test_us_screener as tus
from tests import test_valuation_official_p1 as p1

APP = Path(__file__).resolve().parents[1] / "app"
STAMP_KEYS = ("generation_id", "official_cycle_id", "official_row_sha256", "tp_source", "tp_source_version")
SESSION = "2026-10-16"


# ------------------------------------------------------------------------------------------------------------- fixtures


def _primary(models: tuple[float, ...], consensus: float | None) -> float:
    """The ensemble's primary of these values, computed by the signed aggregation itself."""
    values = tuple(ModelValue(model, models[index] if index < len(models) else None, "evaluated" if index < len(models) else "not_evaluable",
                              None if index < len(models) else "absent") for index, model in enumerate(MODEL_IDS))
    variant = aggregate_grid_variants(values, consensus)["variants"][ENSEMBLE_POLICY.primary_variant]
    return float(variant["value"])


def _live_record(symbol: str, *, origin: str = ENSEMBLE_ORIGIN, pit_tested: bool | None = True, models: tuple[float, ...] = (150.0, 155.0, 165.0, 170.0),
                 consensus: float | None = 158.0, security_type: str = "Stock", **extra: Any) -> dict[str, Any]:
    """A record of the live producer's snapshot (``valuation_live_ensemble.compute_live_section``), the primary computed by the
    signed aggregation; ``pit_tested`` is the flag the producer adds (absent when ``None``)."""
    used = consensus is not None
    record: dict[str, Any] = {
        "symbol": symbol, "security_type": security_type, "screened": True, "origin": origin,
        "primary_tp": _primary(models, consensus) if origin == ENSEMBLE_ORIGIN else None,
        "models_evaluated": len(models), "sample_size": len(models) + used,
        "model_values": {model: (models[index] if index < len(models) else None) for index, model in enumerate(MODEL_IDS)},
        "consensus": {"used": used, "value": consensus, "analyst_count": 5 if used else 0, "reason": None if used else "unavailable"},
        "price": 126.0, "session_date": SESSION, "as_of": "2026-10-17T04:00:00+00:00", "inputs_sha256": "d" * 64, **extra,
    }
    if pit_tested is not None:
        record["pit_tested"] = pit_tested
    return record


def _live_snapshot(database: Database, market: str, records: list[dict[str, Any]], at: datetime, **outputs: Any) -> str:
    body = {"schema": ENSEMBLE_POLICY.live_schema, "source": "ensemble_live", "market": market, "as_of": at.isoformat(), "session_date": SESSION,
            "primary": ENSEMBLE_POLICY.primary_variant, "context_sha256": "c" * 64, "records": records, **outputs}
    return database.save_analysis_snapshot(ENSEMBLE_POLICY.live_analysis_type, f"{market}_UNIVERSE", "mv-live", {"schema": ENSEMBLE_POLICY.live_schema}, body, at)


def _row(symbol: str, *, tp: float, buy_in: float, price: float, internal_tp: float, internal_buy_in: float, ensemble_tp: float | None = None,
         pit_tested: bool | None = True, reason: str = "not_evaluable:statement_vintages_missing", **extra: Any) -> dict[str, Any]:
    """A producer row of this revision: Passo 1's row (blend, internal TP and view) plus its ensemble fields — the ensemble's TP
    and a view deliberately different from the internal one, or the internal fallback (``ensemble_fallback_view``)."""
    row = p1._row(symbol, tp=tp, buy_in=buy_in, price=price, internal_tp=internal_tp, internal_buy_in=internal_buy_in, **extra)
    if ensemble_tp is None:
        row.update(ensemble_fallback_view(row, reason))
        return row
    ensemble_buy_in = official_ensemble_buy_in_v1(ensemble_tp, 0.2)
    row.update({"ensemble_tp": ensemble_tp, "ensemble_buy_in": ensemble_buy_in, "ensemble_buy_in_models": {us_screener.ENSEMBLE_BUY_IN_MODEL: ensemble_tp / 1.2},
                "ensemble_upside_percent": (ensemble_tp / price - 1) * 100, "ensemble_price_vs_buy_in_percent": (price / ensemble_buy_in - 1) * 100,
                "ensemble_expected_total_return_percent": 30.5, "ensemble_score": 77.0, "ensemble_status": "watchlist",
                "ensemble_consensus_weight_percent": 25.0, "ensemble_origin": ENSEMBLE_ORIGIN, "ensemble_pit_tested": pit_tested,
                "ensemble_snapshot_id": "live-1", "ensemble_session_date": SESSION, "ensemble_inputs_sha256": "d" * 64})
    return row


def _three_markets(database: Database, at: datetime = p1.NOW) -> dict[str, str]:
    """B3 always falls back; NASDAQ: AAPL (ensemble, tested), MSFT (ensemble, outside the tested population), NVDA (not evaluable);
    NYSE: KO (ensemble, tested)."""
    return {
        "B3": p1._publish_universe(database, "B3", [
            _row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0, internal_buy_in=31.0, reason="market_outside_ensemble"),
            _row("VALE3", tp=70.0, buy_in=60.0, price=62.0, internal_tp=69.0, internal_buy_in=59.0, reason="market_outside_ensemble")], at),
        "NASDAQ": p1._publish_universe(database, "NASDAQ", [
            _row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0, internal_buy_in=196.0, ensemble_tp=260.0),
            _row("MSFT", tp=500.0, buy_in=400.0, price=450.0, internal_tp=490.0, internal_buy_in=392.0, ensemble_tp=470.0, pit_tested=False),
            _row("NVDA", tp=150.0, buy_in=120.0, price=130.0, internal_tp=148.0, internal_buy_in=118.0)], at + timedelta(minutes=1)),
        "NYSE": p1._publish_universe(database, "NYSE", [
            _row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0, internal_buy_in=58.0, ensemble_tp=72.0)], at + timedelta(minutes=2)),
    }


def _lock_ensemble(monkeypatch: pytest.MonkeyPatch, receipt: str) -> None:
    """The ensemble lock commit as it would be merged after the PIT PASS and the owner's acceptance."""
    monkeypatch.setattr(official, "ENSEMBLE_TP_REPLACEMENT_AUTHORIZED", True)
    monkeypatch.setattr(official, "ENSEMBLE_TP_REPLACEMENT_RECEIPT_SHA256", receipt)


def _to_internal(database: Database, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Today's state: the head serves the internal source (Passo 1's order, stamped with its cycles' versions, Q6)."""
    head = official.current_generation(database)
    assert head is not None
    cycles = dict(head["cycles"])
    report = official.before_after_report(database, cycles=cycles, targeted={})
    p1._authorize(monkeypatch, report["report_sha256"])
    return official.select_generation(database, cycles=cycles, targeted={}, now=p1._wall(), activated_by="mesa", reason="P1 switch",
                                      source=SOURCE_INTERNAL, before_after_sha256=report["report_sha256"])


def _to_ensemble(database: Database, monkeypatch: pytest.MonkeyPatch, *, targeted: dict[str, str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    head = official.current_generation(database)
    assert head is not None
    cycles = dict(head["cycles"])
    report = official.before_after_report(database, cycles=cycles, targeted=targeted or {}, source_to=SOURCE_ENSEMBLE)
    _lock_ensemble(monkeypatch, report["report_sha256"])
    generation = official.select_generation(database, cycles=cycles, targeted=targeted, now=p1._wall(), activated_by="mesa", reason="ensemble switch",
                                            source=SOURCE_ENSEMBLE, before_after_sha256=report["report_sha256"])
    return generation, report


def _without(row: dict[str, Any] | None, keys: tuple[str, ...] = STAMP_KEYS) -> dict[str, Any]:
    assert row is not None
    return {key: value for key, value in row.items() if key not in keys and not key.startswith("ensemble_")}


# -------------------------------------------------------------------------------------------------- the engine and policy


def test_the_source_the_policy_in_one_place_and_the_lock_closed_in_this_tree() -> None:
    assert SOURCE_ENSEMBLE == official.SOURCE_ENSEMBLE == "official_ensemble_v1" and OFFICIAL_SOURCES == (SOURCE_BLEND, SOURCE_INTERNAL, SOURCE_ENSEMBLE)
    assert official.RECORDABLE_SOURCES == (*OFFICIAL_SOURCES, official.SOURCE_V3_2_SHADOW)
    # the policy mirrors the live producer's own labels (a rename there would silently empty the switch)
    assert (ENSEMBLE_POLICY.live_analysis_type, ENSEMBLE_POLICY.live_schema, ENSEMBLE_POLICY.primary_variant) == (live.ANALYSIS_TYPE, live.SCHEMA, live.PRIMARY)
    assert ENSEMBLE_POLICY.markets == live.MARKETS and ENSEMBLE_POLICY.security_types == ("Stock",)
    assert ENSEMBLE_POLICY.require_pit_tested is False  # owner 28/10: every evaluated US name takes the ensemble TP
    assert ENSEMBLE_POLICY.receipt()["untested_buy_permitted"] is False and ENSEMBLE_POLICY.receipt()["max_snapshot_age_hours"] == 96.0
    # the ensemble lock is closed by literal in this tree, and its receipt is the placeholder: nothing switches before the lock commit
    source = (APP / "valuation_official.py").read_text(encoding="utf-8")
    assert official.ENSEMBLE_TP_REPLACEMENT_AUTHORIZED is False and "\nENSEMBLE_TP_REPLACEMENT_AUTHORIZED = False" in source
    assert official.ENSEMBLE_TP_REPLACEMENT_RECEIPT_SHA256 == official.RECEIPT_PLACEHOLDER
    assert official.BEFORE_AFTER_ARMS[SOURCE_INTERNAL][3] == official.BEFORE_AFTER_SCHEMA == "VALUATION_P1_BEFORE_AFTER_V3"  # Passo 1's receipt unchanged
    # the decisor and the ops workflow know the tested-population code
    assert official.ENSEMBLE_UNTESTED_CODE in decisor.OBSERVAR_CODES and official.ENSEMBLE_UNTESTED_CODE not in decisor.VETO_CODES


def test_the_ensemble_buy_in_is_the_internal_buy_ins_rule_on_the_ensemble_tp() -> None:
    """(b): ``official_ensemble_buy_in_v1`` is ``official_buy_in_v1`` over the one TP with the internal entry hurdle — on the
    internal TP it gives the internal buy-in the US producer emits (the mean of the discounted methods is the discounted mean)."""
    stock = tus.service()._analyze_stock("NASDAQ", tus.STOCK_QUOTE, tus.STOCK_FUNDAMENTALS, tus.rising_history(), 300_000_000)
    hurdle = official_entry_discount_v1("US", stock["risk_score"], stock["valuation_confidence"])
    assert stock["internal_buy_in"] == official_buy_in_v1(stock["methods"].values(), hurdle, stock["internal_tp"])
    assert official_ensemble_buy_in_v1(stock["internal_tp"], hurdle) == pytest.approx(stock["internal_buy_in"], rel=1e-12)
    assert official_ensemble_buy_in_v1(160.0, hurdle) == official_buy_in_v1((160.0,), hurdle, 160.0) == 160.0 / (1 + hurdle)
    assert official_ensemble_buy_in_v1(100.0, 0.05) == 90.0  # the same 90 % cap


@pytest.mark.parametrize("models, consensus", [
    ((150.0, 155.0, 165.0, 170.0), 158.0),  # retained, in the middle
    ((150.0, 155.0, 165.0, 170.0), 140.0),  # the minimum: trimmed
    ((150.0, 155.0, 165.0, 170.0), 190.0),  # the maximum: trimmed
    ((150.0, 155.0, 165.0, 170.0), 150.0),  # ties the minimum: the stable sort puts it after the model value — retained
    ((150.0, 155.0, 165.0, 170.0), 170.0),  # ties the maximum: last — trimmed
    ((150.0, 155.0), 152.0),  # three values: one retained
    ((150.0, 155.0, 165.0), None),  # no consensus
    ((100.0, 120.0, 130.0, 140.0, 150.0, 160.0, 170.0), 135.0),
])
def test_the_consensus_weight_is_the_one_the_signed_aggregation_gives_it(models: tuple[float, ...], consensus: float | None) -> None:
    labelled = sorted([(value, 0) for value in models] + ([(consensus, 1)] if consensus is not None else []), key=lambda item: item[0])
    retained = labelled[1:-1]
    assert _primary(models, consensus) == math.fsum(value / len(retained) for value, _ in retained)  # the aggregation's own trim and mean
    assert ensemble_consensus_weight_v1(models, consensus) == sum(flag for _, flag in retained) / len(retained)


def test_a_fallback_view_mirrors_the_whole_internal_view() -> None:
    row = p1._row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0, internal_buy_in=31.0,
                  internal_tp_validation_status="validated", internal_tp_validation_reasons=["ok"], internal_convergence_weight=0.4)
    view = ensemble_fallback_view(row, "market_outside_ensemble")
    for field in ENSEMBLE_MIRRORED_FIELDS:
        if f"internal_{field}" in row:
            assert view[f"ensemble_{field}"] == row[f"internal_{field}"], field
    assert view["ensemble_origin"] == "fallback_internal:market_outside_ensemble" and view["ensemble_consensus_weight_percent"] == 0.0
    assert view["ensemble_pit_tested"] is None and view["ensemble_tp_validation_reasons"] is not row["internal_tp_validation_reasons"]  # copies


# ------------------------------------------------------------------------------------------------------- the producers


def test_a_us_stock_takes_the_ensemble_tp_and_its_view_derived_as_the_internal_one() -> None:
    svc = tus.service()
    at = datetime(2026, 10, 17, 4, 0, tzinfo=timezone.utc)
    record = _live_record("TEST", pit_tested=False)
    snapshot_id = _live_snapshot(svc.database, "NASDAQ", [record], at)
    snapshot = svc._live_ensemble("NASDAQ", at + timedelta(hours=1))
    assert snapshot[2] is None and snapshot[1]["ensemble_snapshot_id"] == snapshot_id and set(snapshot[0]) == {"TEST"}
    row = svc._analyze_stock("NASDAQ", tus.STOCK_QUOTE, tus.STOCK_FUNDAMENTALS, tus.rising_history(), 300_000_000,
                             ensemble=svc._ensemble_input("TEST", snapshot))
    tp = record["primary_tp"]
    hurdle = official_entry_discount_v1("US", row["risk_score"], row["valuation_confidence"])
    assert row["ensemble_tp"] == tp and row["ensemble_buy_in"] == official_buy_in_v1((tp,), hurdle, tp) == official_ensemble_buy_in_v1(tp, hurdle)
    assert row["ensemble_upside_percent"] == (tp / 100.0 - 1) * 100 and row["ensemble_price_vs_buy_in_percent"] == (100.0 / row["ensemble_buy_in"] - 1) * 100
    assert row["ensemble_expected_total_return_percent"] == row["ensemble_upside_percent"] + 1.0  # the internal view's dividend yield
    assert row["ensemble_score"] == USScreeningService._power_score(row["ensemble_upside_percent"], row["risk_score"], row["operating_quality"],
                                                                    row["valuation_confidence"], row["ensemble_price_vs_buy_in_percent"])
    assert row["ensemble_consensus_weight_percent"] == pytest.approx(100 / 3) and row["ensemble_buy_in_models"] == {us_screener.ENSEMBLE_BUY_IN_MODEL: tp / (1 + hurdle)}
    assert row["ensemble_origin"] == ENSEMBLE_ORIGIN and row["ensemble_pit_tested"] is False  # (c) served, labelled untested
    assert (row["ensemble_snapshot_id"], row["ensemble_session_date"], row["ensemble_inputs_sha256"]) == (snapshot_id, SESSION, "d" * 64)
    USScreeningService._assign_statuses([row], 0.042)
    tp_cutoff, risk_cutoff = USScreeningService._tp_cutoff(0.042), USScreeningService._risk_cutoff([row])
    assert row["ensemble_status"] == USScreeningService._screen_status(row["signal_quality"], row["ensemble_upside_percent"], row["risk_score"],
                                                                        row["ensemble_price_vs_buy_in_percent"], tp_cutoff, risk_cutoff)
    # the ensemble record reads exactly these fields; its provenance names the origin, the snapshot and the label
    at_cut = datetime(2026, 10, 17, 21, 0, tzinfo=timezone.utc)
    ensemble = official.prediction_from_row(row, market="NASDAQ", scope="universe", cycle_id="c", source_version="7", prediction_instant=at_cut, source=SOURCE_ENSEMBLE)
    internal = official.prediction_from_row(row, market="NASDAQ", scope="universe", cycle_id="c", source_version="7", prediction_instant=at_cut, source=SOURCE_INTERNAL)
    assert ensemble is not None and internal is not None
    assert (ensemble["tp"], ensemble["buy_in"], ensemble["internal_tp"]) == (tp, row["ensemble_buy_in"], row["internal_tp"])
    assert ensemble["consensus_weight_percent"] == pytest.approx(100 / 3) and ensemble["decomposition"]["status"] == row["ensemble_status"]
    assert ensemble["decomposition"]["buy_in_models"] == row["ensemble_buy_in_models"] and ensemble["consensus_tp"] == internal["consensus_tp"] == 150.0
    provenance = ensemble["decomposition"]["provenance"]
    assert provenance["ensemble_origin"] == ENSEMBLE_ORIGIN and provenance["ensemble_pit_tested"] is False and provenance["ensemble_snapshot_id"] == snapshot_id
    assert internal["decomposition"]["provenance"].keys().isdisjoint(official.ENSEMBLE_PROVENANCE_KEYS)  # the internal record is untouched
    assert ensemble["row_sha256"] == official.canonical_sha256({k: v for k, v in ensemble.items() if k not in ("id", "row_sha256")})


def _fallback_origin(svc: USScreeningService, symbol: str, live_state: Any, *, etf: bool = False) -> dict[str, Any]:
    quote = {**tus.STOCK_QUOTE, "symbol": symbol}
    if etf:
        return svc._analyze_etf("NASDAQ", quote, {"companyName": "Test ETF", "isETF": True, "etfCategory": "Large Blend", "etfTotalAssets": 8e9,
                                                  "etfHoldingsCount": 500}, tus.rising_history(), 400_000_000)
    return svc._analyze_stock("NASDAQ", quote, tus.STOCK_FUNDAMENTALS, tus.rising_history(), 300_000_000,
                              ensemble=svc._ensemble_input(symbol, live_state) if live_state is not None else None)


def test_every_other_us_row_falls_back_to_its_internal_tp_with_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = tus.service()
    at = datetime(2026, 10, 17, 4, 0, tzinfo=timezone.utc)
    now = at + timedelta(hours=1)
    assert svc._live_ensemble("NASDAQ", now) == ({}, {}, "live_snapshot_missing")
    _live_snapshot(svc.database, "NASDAQ", [
        _live_record("TEST"), _live_record("NOPE", origin="not_evaluable:statement_vintages_missing"),
        _live_record("BAD", sample_size=9), _live_record("ODD", consensus=None, consensus_used=True) | {"consensus": {"used": True, "value": None}},
        _live_record("UNTS", pit_tested=None)], at)
    state = svc._live_ensemble("NASDAQ", now)
    cases = {
        "NOPE": "not_evaluable:statement_vintages_missing",  # the producer's own reason
        "GONE": "not_in_live_snapshot",
        "BAD": "live_record_invalid:ValueError",  # sample_size is not the count of the values it averaged
        "ODD": "live_record_invalid:ValueError",  # a consensus used without a value
    }
    rows = {symbol: _fallback_origin(svc, symbol, state) for symbol in cases}
    rows["ETF"] = _fallback_origin(svc, "ETFX", state, etf=True)
    cases["ETF"] = "not_a_stock"
    rows["UNREAD"] = _fallback_origin(svc, "TEST", None)  # a caller that read no snapshot (the PIT re-executor)
    cases["UNREAD"] = "live_snapshot_not_read"
    USScreeningService._assign_statuses(list(rows.values()), 0.042)
    for name, row in rows.items():
        assert row["ensemble_origin"] == ENSEMBLE_FALLBACK_PREFIX + cases[name], name
        for field in ("tp", "buy_in", "upside_percent", "price_vs_buy_in_percent", "expected_total_return_percent", "score", "status"):
            assert row[f"ensemble_{field}"] == row[f"internal_{field}"], (name, field)
        assert row["ensemble_consensus_weight_percent"] == 0.0 and row["ensemble_pit_tested"] is None and "ensemble_buy_in_models" not in row
        internal = official.prediction_from_row(row, market="NASDAQ", scope="universe", cycle_id="c", source_version="7", prediction_instant=at, source=SOURCE_INTERNAL)
        ensemble = official.prediction_from_row(row, market="NASDAQ", scope="universe", cycle_id="c", source_version="7", prediction_instant=at, source=SOURCE_ENSEMBLE)
        assert internal is not None and ensemble is not None
        for key in ("tp", "buy_in", "consensus_weight_percent", "bear_tp", "bull_tp"):
            assert ensemble[key] == internal[key], (name, key)
        assert ensemble["decomposition"]["buy_in_models"] == internal["decomposition"]["buy_in_models"] and ensemble["decomposition"]["status"] == internal["decomposition"]["status"]
    # an unknown pit_tested is carried as unknown (fail closed downstream), never as tested
    untested = _fallback_origin(svc, "UNTS", state)
    assert untested["ensemble_origin"] == ENSEMBLE_ORIGIN and untested["ensemble_pit_tested"] is None
    # a stale, foreign or ambiguous snapshot: every name falls back
    assert svc._live_ensemble("NASDAQ", at + ENSEMBLE_POLICY.max_snapshot_age + timedelta(seconds=1))[2] == "live_snapshot_stale"
    assert svc._live_ensemble("NYSE", now)[2] == "live_snapshot_missing"
    _live_snapshot(svc.database, "NYSE", [_live_record("KO")], at, schema="OTHER")
    assert svc._live_ensemble("NYSE", now)[2] == "live_snapshot_invalid:identity"
    _live_snapshot(svc.database, "NYSE", [_live_record("KO"), _live_record("KO")], at + timedelta(minutes=1))
    assert svc._live_ensemble("NYSE", now)[2] == "live_snapshot_invalid:duplicate_symbol"
    assert USScreeningService._ensemble_input("KO", svc._live_ensemble("NYSE", now))[2] == "live_snapshot_invalid:duplicate_symbol"
    # the policy in one place: restricting the TP itself to the tested population makes the untested names fall back
    monkeypatch.setattr(us_screener, "ENSEMBLE_POLICY", dataclasses.replace(ENSEMBLE_POLICY, require_pit_tested=True))
    assert USScreeningService._ensemble_input("UNTS", state)[2] == "outside_tested_population" and USScreeningService._ensemble_input("TEST", state)[2] is None


def test_b3_rows_carry_their_internal_tp_as_the_ensemble_fallback_bit_for_bit() -> None:
    """(a): B3 is outside the ensemble's population — ``_value_row`` (universe and on-demand) emits the internal TP and view as
    its ensemble fields, so a B3 cycle is selectable for the ensemble source and its ensemble records are the internal numbers."""
    from tests.test_market_data import PETROBRAS_BENCHMARK, _petrobras_row

    service = B3ScreenerService.__new__(B3ScreenerService)
    service._calibration_factors = {}
    row = _petrobras_row()
    row.update(B3ScreenerService._cyclical_market_multiples(row))
    service._value_row(row, PETROBRAS_BENCHMARK, {"selic": 0.14, "ipca12m": 0.045})
    assert row["ensemble_origin"] == "fallback_internal:market_outside_ensemble" and row["ensemble_consensus_weight_percent"] == 0.0
    mirrored = [field for field in ENSEMBLE_MIRRORED_FIELDS if f"internal_{field}" in row]
    assert {"tp", "buy_in", "buy_in_models", "status", "score", "tp_validation_status", "convergence_weight"} <= set(mirrored)
    assert all(row[f"ensemble_{field}"] == row[f"internal_{field}"] for field in mirrored)
    at = datetime(2026, 9, 4, 21, 30, tzinfo=timezone.utc)
    internal = official.prediction_from_row(row, market="B3", scope="universe", cycle_id="c", source_version="7", prediction_instant=at, source=SOURCE_INTERNAL)
    ensemble = official.prediction_from_row(row, market="B3", scope="universe", cycle_id="c", source_version="7", prediction_instant=at, source=SOURCE_ENSEMBLE)
    assert internal is not None and ensemble is not None
    assert {k: v for k, v in ensemble.items() if k not in ("id", "row_sha256", "source", "decomposition")} == \
        {k: v for k, v in internal.items() if k not in ("id", "row_sha256", "source", "decomposition")}
    assert {k: v for k, v in ensemble["decomposition"].items() if k != "provenance"} == {k: v for k, v in internal["decomposition"].items() if k != "provenance"}
    assert official._usable(row, SOURCE_ENSEMBLE) and official.source_view(row, SOURCE_ENSEMBLE) == official.internal_view(row)


# ------------------------------------------------------------------------------------- no behaviour change before the order


def test_served_rows_are_what_they_were_while_the_switch_was_never_ordered(monkeypatch: pytest.MonkeyPatch) -> None:
    """The producers' new fields reach no consumer before the switch: a blend or internal record is served without them, its
    identity is the same with and without them, and a night of this revision keeps the head on its source."""
    plain = p1._row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0, internal_buy_in=196.0)
    rich = _row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0, internal_buy_in=196.0, ensemble_tp=260.0)
    for source in (SOURCE_BLEND, SOURCE_INTERNAL):
        before = official.prediction_from_row(plain, market="NASDAQ", scope="universe", cycle_id="c", source_version="7", prediction_instant=p1.NOW, source=source)
        after = official.prediction_from_row(rich, market="NASDAQ", scope="universe", cycle_id="c", source_version="7", prediction_instant=p1.NOW, source=source)
        assert before is not None and after is not None and before["row_sha256"] == after["row_sha256"]  # the same identity, bit for bit
        served = official._served(rich, after, generation={"generation_id": "g"}, cycle_id="c", scope="universe", market="NASDAQ")
        assert served == official._served(plain, before, generation={"generation_id": "g"}, cycle_id="c", scope="universe", market="NASDAQ")
        assert served is not None and not any(key.startswith("ensemble_") for key in served)
    assert official.prediction_from_row(plain, market="NASDAQ", scope="universe", cycle_id="c", source_version="7", prediction_instant=p1.NOW,
                                        source=SOURCE_ENSEMBLE) is None  # a pre-revision row has no ensemble record
    # two stores, one with the producers of yesterday and one with this revision: every consumer reads the same rows
    today, tomorrow = p1._database(), p1._database()
    p1._three_markets(today)
    rich_cycles = _three_markets(tomorrow)
    assert sum(len(tomorrow.valuation_predictions_for_cycle(cycle, source=SOURCE_ENSEMBLE)) for cycle in rich_cycles.values()) == 6  # every row, the third source
    for _ in range(2):  # under the blend head, then under the internal one
        for market in official.MARKETS:
            served_today = official.official_rows(today, market)
            served_tomorrow = official.official_rows(tomorrow, market)
            assert set(served_today) <= set(served_tomorrow)
            for symbol, row in served_today.items():
                assert _without(served_tomorrow[symbol]) == _without(row) and not any(key.startswith("ensemble_") for key in served_tomorrow[symbol])
        _to_internal(today, monkeypatch)
        _to_internal(tomorrow, monkeypatch)
    # a night of this revision under the internal head: the automatic pass follows the internal source, never the ensemble
    new = p1._publish_universe(tomorrow, "NYSE", [_row("KO", tp=71.0, buy_in=61.0, price=65.0, internal_tp=69.0, internal_buy_in=59.0, ensemble_tp=75.0)], p1._wall())
    head = official.current_generation(tomorrow)
    assert head is not None and head["source"] == SOURCE_INTERNAL and head["cycles"]["NYSE"] == new
    assert official.official_row(tomorrow, "US", "KO")["our_tp"] == 69.0  # type: ignore[index]


# ------------------------------------------------------------------------------------------------- the switch and rollback


def test_the_switch_to_the_ensemble_is_locked_by_its_own_lock_and_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    database = p1._database()
    cycles = _three_markets(database)
    _to_internal(database, monkeypatch)  # Passo 1's lock is flipped and names its receipt — it never unlocks the ensemble
    report = official.before_after_report(database, cycles=cycles, targeted={}, source_to=SOURCE_ENSEMBLE)
    order: dict[str, Any] = dict(cycles=cycles, targeted={}, activated_by="mesa", reason="ensemble", source=SOURCE_ENSEMBLE)
    with pytest.raises(ValueError, match="ensemble_tp_replacement_authorized is false"):
        official.select_generation(database, now=p1._wall(), before_after_sha256=report["report_sha256"], **order)
    monkeypatch.setattr(official, "ENSEMBLE_TP_REPLACEMENT_AUTHORIZED", True)
    with pytest.raises(ValueError, match="must cite the before/after receipt"):
        official.select_generation(database, now=p1._wall(), before_after_sha256=None, **order)
    with pytest.raises(ValueError, match="the lock commit names no accepted before/after receipt"):  # the placeholder switches nothing
        official.select_generation(database, now=p1._wall(), before_after_sha256=report["report_sha256"], **order)
    p1_receipt = official.before_after_report(database, cycles=cycles, targeted={})["report_sha256"]  # Passo 1's receipt is not this one
    _lock_ensemble(monkeypatch, p1_receipt)
    with pytest.raises(ValueError, match="does not match its report_sha256"):
        official.select_generation(database, now=p1._wall(), before_after_sha256=p1_receipt, **order)
    monkeypatch.setattr(official, "ENSEMBLE_TP_REPLACEMENT_RECEIPT_SHA256", "f" * 64)
    with pytest.raises(ValueError, match="not the accepted one"):
        official.select_generation(database, now=p1._wall(), before_after_sha256=report["report_sha256"], **order)
    head = official.current_generation(database)
    assert head is not None and head["source"] == SOURCE_INTERNAL  # nothing switched
    # a cycle produced before this revision has no ensemble records: never selectable for the ensemble
    legacy = p1._publish_universe(database, "NYSE", [p1._row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0, internal_buy_in=58.0)], p1._wall())
    _lock_ensemble(monkeypatch, report["report_sha256"])
    with pytest.raises(ValueError, match="not complete/valid/recorded for source official_ensemble_v1"):
        official.select_generation(database, now=p1._wall(), before_after_sha256=report["report_sha256"], **{**order, "cycles": {**cycles, "NYSE": legacy}})


def test_after_the_switch_every_consumer_reads_the_ensemble_tp_and_after_the_rollback_the_internal_one(monkeypatch: pytest.MonkeyPatch) -> None:
    database = p1._database()
    _three_markets(database)
    internal_head = _to_internal(database, monkeypatch)
    before = {(market, symbol): row for market in official.MARKETS for symbol, row in official.official_rows(database, market).items()}
    generation, report = _to_ensemble(database, monkeypatch)
    assert generation["source"] == SOURCE_ENSEMBLE and generation["receipt"]["source_switch"] == {"from": SOURCE_INTERNAL, "to": SOURCE_ENSEMBLE,
                                                                                               "before_after_sha256": report["report_sha256"]}
    aapl = official.official_row(database, "US", "AAPL")
    assert aapl is not None and aapl["tp_source"] == SOURCE_ENSEMBLE and aapl["our_tp"] == 260.0 and aapl["buy_in"] == official_ensemble_buy_in_v1(260.0, 0.2)
    assert (aapl["status"], aapl["score"], aapl["expected_total_return_percent"]) == ("watchlist", 77.0, 30.5)  # the ensemble view, never the internal one
    assert aapl["upside_percent"] == (260.0 / 220.0 - 1) * 100 and aapl["consensus_weight_percent"] == 25.0 and aapl["internal_tp"] == 245.0
    assert aapl["ensemble_origin"] == ENSEMBLE_ORIGIN and aapl["ensemble_pit_tested"] is True and not official.ensemble_untested(aapl)
    msft = official.official_row(database, "US", "MSFT")
    assert msft is not None and msft["our_tp"] == 470.0 and msft["ensemble_pit_tested"] is False and official.ensemble_untested(msft)  # served, labelled
    nvda = official.official_row(database, "US", "NVDA")
    assert nvda is not None and nvda["our_tp"] == 148.0 and nvda["status"] == "near_buy" and nvda["ensemble_origin"].startswith(ENSEMBLE_FALLBACK_PREFIX)
    assert not official.ensemble_untested(nvda)
    # B3 unchanged: every served number and view is the internal one; only the stamp and the label differ
    for symbol in ("PETR4", "VALE3"):
        served = official.official_rows(database, "B3")[symbol]
        assert _without(served) == _without(before[("B3", symbol)]) and served["ensemble_origin"] == "fallback_internal:market_outside_ensemble"
    # the decisor: the untested ensemble TP is never a permission; the tested one and the fallback are decided as before
    for row, permitted in ((aapl, True), (msft, False), (nvda, True)):
        outcome = _decide_us(row)
        assert (outcome["verdict"] == decisor.COMPRA_PERMITIDA) is permitted, row["symbol"]
        assert outcome["checks"]["tested_population"]["pass"] is permitted
    assert _decide_us(msft)["reason_codes"] == [official.ENSEMBLE_UNTESTED_CODE]
    assert "tested_population" not in _decide_us(before[("NASDAQ", "AAPL")])["checks"]  # an internal row is not checked: nothing changed before the switch
    # a new night: the automatic pass follows the ensemble
    nyse = p1._publish_universe(database, "NYSE", [_row("KO", tp=71.0, buy_in=61.0, price=65.0, internal_tp=69.0, internal_buy_in=59.0, ensemble_tp=75.0)], p1._wall())
    head = official.current_generation(database)
    assert head is not None and head["source"] == SOURCE_ENSEMBLE and head["cycles"]["NYSE"] == nyse and official.official_row(database, "US", "KO")["our_tp"] == 75.0  # type: ignore[index]
    # the rollback to the internal source: never locked, no hash, over the head's composition
    monkeypatch.setattr(official, "ENSEMBLE_TP_REPLACEMENT_AUTHORIZED", False)
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", False)
    rolled = official.select_generation(database, cycles=head["cycles"], targeted=head["targeted"], now=p1._wall(), activated_by="mesa", reason="rollback",
                                        source=SOURCE_INTERNAL)
    assert rolled["source"] == SOURCE_INTERNAL and rolled["source_version"] == "rollback"
    assert rolled["receipt"]["source_switch"] == {"from": SOURCE_ENSEMBLE, "to": SOURCE_INTERNAL, "before_after_sha256": None}
    aapl_back = official.official_row(database, "US", "AAPL")
    assert aapl_back is not None and _without(aapl_back) == _without(before[("NASDAQ", "AAPL")]) and aapl_back["tp_source"] == SOURCE_INTERNAL
    assert not any(key.startswith("ensemble_") for key in aapl_back) and official.official_row(database, "US", "KO")["our_tp"] == 69.0  # type: ignore[index]
    # from any head but the ensemble's, an order to the internal source is Passo 1's switch: still locked
    with pytest.raises(ValueError, match="official_tp_replacement_authorized is false"):
        official.select_generation(database, cycles=rolled["cycles"], now=p1._wall(), activated_by="mesa", reason="again", source=SOURCE_INTERNAL)
    assert internal_head["source"] == SOURCE_INTERNAL


def test_a_rollback_decided_on_an_ensemble_head_the_chain_moved_past_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    database = p1._database()
    _three_markets(database)
    _to_internal(database, monkeypatch)
    ensemble_head, _ = _to_ensemble(database, monkeypatch)
    reads = iter([ensemble_head, {**ensemble_head, "generation_id": "moved"}])
    original = database.latest_valuation_official_selection
    monkeypatch.setattr(database, "latest_valuation_official_selection", lambda: next(reads, None) or original())
    with pytest.raises(ValueError, match="the rollback to 'official_internal_v1' was decided on the ensemble head"):
        official.select_generation(database, cycles=ensemble_head["cycles"], now=p1._wall(), activated_by="mesa", reason="rollback", source=SOURCE_INTERNAL)


def _decide_us(row: dict[str, Any]) -> dict[str, Any]:
    served = {**row, "official_session_date": SESSION, "official_market": "NASDAQ", "fundamentals_as_of": "2026-09-30", "method_dispersion_percent": 20.0,
              "valuation_confidence": 80.0, "signal_quality": "validated"}
    served.pop("tp_validation_status", None)
    price = float(served["buy_in"]) * 0.9
    served["price"] = price
    return decisor.decide(served, expected_session=SESSION, tp_sessions_behind=0, price={"price": price, "source": "official_cut", "session": SESSION},
                          error={"status": "ok", "value": 0.05}, rate={"status": "ok", "h_market": 0.04}, staleness={"status": "clear", "source_status": "ok"},
                          events={"market": "NASDAQ", "earnings": {"status": "calendar", "within": False}})


# ------------------------------------------------------------------------------------------------------------ the receipt


def test_the_ensemble_receipt_counts_the_names_changed_and_the_fallbacks_and_names_no_symbol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = p1._database()
    cycles = _three_markets(database)
    _to_internal(database, monkeypatch)
    report = official.before_after_report(database, cycles=cycles, targeted={}, source_to=SOURCE_ENSEMBLE, private_detail_path=tmp_path / "detail.json")
    assert report["schema"] == official.ENSEMBLE_BEFORE_AFTER_SCHEMA and (report["source_from"], report["source_to"]) == (SOURCE_INTERNAL, SOURCE_ENSEMBLE)
    assert report["ensemble_policy"] == ENSEMBLE_POLICY.receipt() and report["generation_source"] == SOURCE_INTERNAL
    b3, nasdaq, nyse = (report["markets"][market] for market in official.MARKETS)
    assert (b3["n"], b3["tp_changed"], b3["ensemble"], b3["fallback"], b3["fallback_tp_changed"]) == (2, 0, 0, 2, 0)
    assert b3["origins"] == {"fallback_internal:market_outside_ensemble": 2} and b3["tp"]["median"] == 0.0
    assert (nasdaq["n"], nasdaq["tp_changed"], nasdaq["ensemble"], nasdaq["fallback"], nasdaq["fallback_tp_changed"]) == (3, 2, 2, 1, 0)
    assert nasdaq["origins"] == {"ensemble": 2, "fallback_internal:not_evaluable:statement_vintages_missing": 1}
    assert nasdaq["tp"]["median"] == 0.0 and nasdaq["tp"]["p90"] == pytest.approx(0.8 * (260.0 / 245.0 - 1))  # AAPL up, MSFT down, NVDA flat
    assert (nasdaq["tp_change_buckets"]["up"], nasdaq["tp_change_buckets"]["down"], nasdaq["tp_change_buckets"]["flat"]) == (1, 1, 1)
    assert nasdaq["missing_ensemble"] == 0 and nasdaq["only_ensemble"] == 0
    assert nasdaq["served_pairs"] == 3 and nasdaq["status"]["transitions"] == {"near_buy->watchlist": 2}
    assert (nyse["tp_changed"], nyse["ensemble"]) == (1, 1) and nyse["tp"]["median"] == pytest.approx(72.0 / 68.0 - 1)
    printed = json.dumps(report)
    assert not any(symbol in printed for symbol in ("PETR4", "VALE3", "AAPL", "MSFT", "NVDA", "KO"))
    assert official.before_after_report(database, cycles=cycles, targeted={}, source_to=SOURCE_ENSEMBLE)["report_sha256"] == report["report_sha256"]  # deterministic
    detail = json.loads((tmp_path / "detail.json").read_text(encoding="utf-8"))
    assert detail["markets"]["NASDAQ"]["pairs"]["AAPL"]["tp_internal"] == 245.0 and detail["markets"]["NASDAQ"]["pairs"]["AAPL"]["tp_ensemble"] == 260.0
    assert detail["markets"]["NASDAQ"]["pairs"]["NVDA"]["ensemble_origin"].startswith(ENSEMBLE_FALLBACK_PREFIX)
    assert official.canonical_sha256(detail) == report["private_detail_sha256"]
    # Passo 1's receipt keeps its exact shape: none of the ensemble's keys
    p1_report = official.before_after_report(database, cycles=cycles, targeted={})
    assert p1_report["schema"] == official.BEFORE_AFTER_SCHEMA and "ensemble_policy" not in p1_report
    assert set(p1_report["markets"]["NASDAQ"]) == {"n", "missing_internal", "only_internal", "served_pairs", "before_unservable", "after_unservable", "tp",
                                                   "tp_change_buckets", "buy_in", "status", "rating", "buy", "upside_percent", "score_change", "tp_validation"}
    markdown = official.ensemble_before_after_markdown(report)
    assert report["report_sha256"] in markdown and "interno → ensemble" in markdown and "sem permissão de compra" in markdown
    assert not any(symbol in markdown for symbol in ("PETR4", "VALE3", "AAPL", "MSFT", "NVDA", "KO"))
    with pytest.raises(ValueError, match="no before/after receipt for a switch to"):
        official.before_after_report(database, source_to=SOURCE_BLEND)


def test_the_cli_receipt_switch_and_rollback_of_the_ensemble(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    database = p1._database()
    _three_markets(database)
    _to_internal(database, monkeypatch)
    wege = p1._targeted(database, "WEGE3", _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0, internal_buy_in=41.0,
                                                reason="market_outside_ensemble"), p1._wall())
    p1._targeted(database, "ITSA4", p1._row("ITSA4", tp=12.0, buy_in=10.0, price=11.0, internal_tp=11.8, internal_buy_in=9.8), p1._wall())  # pre-revision
    head = official.current_generation(database)
    assert head is not None and set(head["targeted"]) == {"WEGE3", "ITSA4"}
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))
    monkeypatch.setattr("app.database.Database", lambda settings: database)
    for argv in (["--to-ensemble"], ["--switch-to-ensemble", "--reason", "x"], ["--rollback-to-internal"], ["--before-after", "--to-ensemble", "--before-after-sha256", "a" * 64],
                 ["--rollback-to-internal", "--reason", "not an ensemble head"], ["--switch-to-ensemble", "--before-after-sha256", "a" * 64]):
        with pytest.raises(SystemExit):
            official.main(argv)
    summary = tmp_path / "summary.md"
    assert official.main(["--before-after", "--to-ensemble", "--keep-internal-targeted", "--markdown", str(summary)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["schema"] == official.ENSEMBLE_BEFORE_AFTER_SCHEMA and receipt["after_targeted_count"] == 1  # the pre-revision admission is dropped
    assert receipt["after_targeted_sha256"] == official.canonical_sha256({"WEGE3": wege}) and "producer_build_sha" in receipt
    assert receipt["report_sha256"] in summary.read_text(encoding="utf-8") and "WEGE3" not in summary.read_text(encoding="utf-8")
    switch = ["--switch-to-ensemble", "--keep-internal-targeted", "--before-after-sha256", receipt["report_sha256"], "--reason", "PIT PASS + owner"]
    with pytest.raises(ValueError, match="ensemble_tp_replacement_authorized is false"):
        official.main(switch)
    _lock_ensemble(monkeypatch, receipt["report_sha256"])
    assert official.main(switch) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["source"] == SOURCE_ENSEMBLE and printed["targeted_count"] == 1
    assert printed["source_switch"] == {"from": SOURCE_INTERNAL, "to": SOURCE_ENSEMBLE, "before_after_sha256": receipt["report_sha256"]}
    assert official.official_row(database, "US", "AAPL")["our_tp"] == 260.0 and official.official_row(database, "B3", "WEGE3")["our_tp"] == 49.0  # type: ignore[index]
    monkeypatch.setattr(official, "ENSEMBLE_TP_REPLACEMENT_AUTHORIZED", False)
    assert official.main(["--rollback-to-internal", "--reason", "drill"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["source"] == SOURCE_INTERNAL and printed["source_version"] == "rollback"
    assert printed["source_switch"] == {"from": SOURCE_ENSEMBLE, "to": SOURCE_INTERNAL, "before_after_sha256": None}
    assert official.official_row(database, "US", "AAPL")["our_tp"] == 245.0  # type: ignore[index]


# ------------------------------------------------------------------------------------------- Dark Side, Last Jedi and R2D2


def _filler(database: Database, at: datetime) -> None:
    p1._publish_universe(database, "B3", [_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0, internal_buy_in=31.0,
                                               reason="market_outside_ensemble")], at)
    p1._publish_universe(database, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0, internal_buy_in=58.0)], at)


def test_dark_side_and_last_jedi_read_the_ensemble_tp_after_the_switch_and_the_internal_one_after_the_rollback(
        monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    tus._offline_eodhd(monkeypatch)
    settings = Settings(eodhd_api_token="test", auth_cookie_secure=False)
    screener = USScreeningService(settings, Database(settings), tus._BuildRealtime(), tus.DummyOnePagers())
    build_at = datetime(2026, 10, 17, 15, 0, tzinfo=timezone.utc)
    record = _live_record("TEST", pit_tested=False, models=(150.0, 155.0, 175.0, 180.0), consensus=170.0)
    _live_snapshot(screener.database, "NASDAQ", [record], build_at - timedelta(hours=10))
    with caplog.at_level(logging.INFO, logger="app.market_data.us_screener"):
        rows = screener._build("NASDAQ", now=build_at)  # publishes the NASDAQ cycle
    assert rows[0]["ensemble_origin"] == ENSEMBLE_ORIGIN and rows[0]["ensemble_tp"] == record["primary_tp"] != rows[0]["internal_tp"]
    ensemble_lines = [entry.getMessage() for entry in caplog.records if "ensemble fields" in entry.getMessage()]
    assert ensemble_lines == ["US ensemble fields for NASDAQ: rows=1 origins={'ensemble': 1} untested=1"]  # counts only, no symbol
    _filler(screener.database, datetime.now(timezone.utc))
    _to_internal(screener.database, monkeypatch)

    def read() -> tuple[Any, Any]:
        return screener._candidate_response("NASDAQ"), screener._matrix_response("NASDAQ")

    candidates, matrix = read()
    assert candidates.tp_source == matrix.tp_source == SOURCE_INTERNAL and matrix.items[0].our_tp == round(rows[0]["internal_tp"], 2)
    assert matrix.items[0].ensemble_origin is None and matrix.items[0].ensemble_pit_tested is None  # no label before the switch
    _to_ensemble(screener.database, monkeypatch)
    candidates, matrix = read()
    assert candidates.tp_source == matrix.tp_source == SOURCE_ENSEMBLE and matrix.items[0].tp_source == SOURCE_ENSEMBLE
    assert matrix.items[0].our_tp == round(record["primary_tp"], 2) and matrix.items[0].buy_in == round(rows[0]["ensemble_buy_in"], 2)
    assert matrix.items[0].internal_tp == round(rows[0]["internal_tp"], 2)
    assert matrix.items[0].ensemble_origin == ENSEMBLE_ORIGIN and matrix.items[0].ensemble_pit_tested is False  # the screens' label
    assert matrix.items[0].consensus_weight_percent == pytest.approx(100 / 3)
    served = screener._served_rows("NASDAQ", official.current_generation(screener.database))
    assert [row["status"] for row in served] == [rows[0]["ensemble_status"]]  # the candidate gate reads the ensemble status
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", False)
    head = official.current_generation(screener.database)
    assert head is not None
    official.select_generation(screener.database, cycles=head["cycles"], now=p1._wall(), activated_by="mesa", reason="rollback", source=SOURCE_INTERNAL)
    candidates, matrix = read()
    assert candidates.tp_source == matrix.tp_source == SOURCE_INTERNAL and matrix.items[0].our_tp == round(rows[0]["internal_tp"], 2)
    assert matrix.items[0].ensemble_origin is None


def test_r2d2_never_takes_an_untested_ensemble_tp_as_its_canonical_basis(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_r2d2 import _service

    service = _service()
    database = service.repo.database
    now = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
    rows = [SimpleNamespace(symbol=symbol, name=f"{symbol} Co", price=220.0, cash_volume=30_000_000.0, change_percent=0.5, as_of=now, status="delayed")
            for symbol in ("TSTD", "UNTS", "FALL")]
    service.realtime = SimpleNamespace(  # type: ignore[assignment]
        _us_investable_rows=lambda market, at: rows,
        _us_symbol_catalog=lambda at: {row.symbol: {"Code": row.symbol, "Exchange": "NASDAQ", "Type": "Common Stock"} for row in rows},
        _portfolio_catalog_market=lambda metadata: "NASDAQ",
        _is_portfolio_security=lambda metadata: True,
    )
    _filler(database, p1.NOW)
    p1._publish_universe(database, "NASDAQ", [
        _row("TSTD", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0, internal_buy_in=196.0, ensemble_tp=260.0, pit_tested=True),
        _row("UNTS", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0, internal_buy_in=196.0, ensemble_tp=260.0, pit_tested=False),
        _row("FALL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0, internal_buy_in=196.0)], p1.NOW + timedelta(minutes=1))
    _to_internal(database, monkeypatch)
    _to_ensemble(database, monkeypatch)
    by_symbol = {item["symbol"]: item for item in service._us_candidates("NASDAQ", now)}
    canonical = "canonical C3PO valuation universe"
    assert by_symbol["TSTD"]["valuation_basis"] == canonical and by_symbol["FALL"]["valuation_basis"] == canonical
    assert by_symbol["UNTS"]["valuation_basis"] != canonical  # served and labelled on the screens, never R2D2's basis
