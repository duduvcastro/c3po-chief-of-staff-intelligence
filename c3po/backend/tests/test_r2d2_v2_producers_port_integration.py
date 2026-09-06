"""Producers -> real V2 port (PR #383 modules). Skipped where the port is not checked out."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping

import pytest

causal_list = pytest.importorskip("app.r2d2_v2_causal_list")
sources = pytest.importorskip("app.r2d2_v2_sources")
shadow = pytest.importorskip("app.r2d2_v2_shadow")
contract = pytest.importorskip("app.r2d2_v2_contract")
calendar_module = pytest.importorskip("app.r2d2_v2_calendar")

from app import r2d2_v2_producer_daily as prod  # noqa: E402
from app import r2d2_v2_producer_earnings as earn  # noqa: E402
from app import r2d2_v2_producer_snapshot as snap  # noqa: E402

D = date(2026, 9, 8)
PREVIOUS = date(2026, 9, 4)
EPOCH = "R2D2-V2-SHADOW-SYNTHETIC"
STAMP = prod.session_close(PREVIOUS) + timedelta(minutes=30)
BUILT = STAMP + timedelta(minutes=30)
NOW = snap.capture_window(D)[0] + timedelta(seconds=4)
HISTORIES = {
    "published_far": {"2026-04-30": {"reportDate": "2026-05-20", "epsActual": 0.5}},
    "cadence_inside": {"2026-05-31": {"reportDate": "2026-06-20", "epsActual": 1.0}},   # Codex E2: expected 19/09 inside the window
    "future_only": {"2026-08-31": {"reportDate": "2026-11-20", "epsActual": None}},       # Codex E3a: no published report
    "bad_date": {"2026-05-31": {"reportDate": "bad", "epsActual": None}},                # Codex E3b: unreadable evidence
}


def _response(payload, at: datetime = STAMP, path: str = "/synthetic") -> prod.Response:
    return prod.Response(json.dumps(payload).encode(), at, path)


def _fetcher(history: str):
    def fetch(path: str, params: Mapping[str, str]) -> prod.Response:
        if path == "/api/exchange-symbol-list/US":
            return _response([{"Code": "SYNTH", "Exchange": "NYSE", "Type": "Common Stock"}])
        if path == "/api/eod-bulk-last-day/US":
            if params.get("type") == "splits":
                return _response([])
            return _response([{"code": "SYNTH", "date": params["date"], "open": 10, "high": 11, "low": 9, "close": 10, "volume": 2_000_000}])
        if path.startswith("/api/eod/SYNTH.US"):
            sessions = prod.xnys_sessions_ending(PREVIOUS, 61)
            return _response([{"date": s.isoformat(), "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 2_000_000} for s in sessions])
        if path.startswith("/api/splits/SYNTH.US"):
            return _response([])
        if path == "/api/calendar/earnings":
            return _response({"earnings": [{"code": "OTHER.US", "report_date": "2026-09-15", "before_after_market": "BeforeMarket"}]})
        if path == "/api/fundamentals/SYNTH.US":
            return _response(HISTORIES[history], STAMP + timedelta(seconds=5))
        raise AssertionError(path)
    return fetch


def test_registry_and_daily_contract_are_consumed_by_the_real_list_builder(tmp_path: Path) -> None:
    result = prod.produce_causal_inputs(_fetcher("published_far"), session_date=D, output_dir=tmp_path, now=STAMP + timedelta(minutes=5))
    commitment = causal_list.build_commitment(epoch=EPOCH, day=D, built_at=BUILT,
                                              registry_bytes=(tmp_path / "registry.json").read_bytes(),
                                              daily_bytes=(tmp_path / "daily_contract.json").read_bytes(),
                                              calendar=calendar_module.ShadowCalendar())
    assert commitment["list"] == ["SYNTH"] and result["registry_symbols"] == 1


def _observe(root: Path, loader, book, calendar, sequence: int):
    body = snap.assemble_snapshot(["SYNTH"], book, loader(), now=NOW, sequence=sequence)
    prod.write_private(root / "snapshot.json", prod.canonical(body))
    batch = sources.FileShadowSource(root).snapshot(NOW)
    assert batch["status"] == "AVAILABLE"
    row = batch["universe"]["instruments"][0]
    inputs = shadow.candidate_inputs(row, batch, NOW, calendar)
    return row, inputs, contract.evaluate_candidate(inputs).to_dict()


def _root_with_quote(tmp_path: Path, history: str):
    root = tmp_path / "root"
    base = root / "components" / D.isoformat()
    fetch = _fetcher(history)
    prod.produce_causal_inputs(fetch, session_date=D, output_dir=base, now=STAMP + timedelta(minutes=5))
    book = snap.QuoteBook()
    tick_at = NOW - timedelta(seconds=1)
    book.record(json.dumps({"s": "SYNTH", "t": int(tick_at.timestamp() * 1000), "bp": 10.0, "ap": 10.01}), NOW - timedelta(milliseconds=500), {"SYNTH"})
    return root, base, fetch, book


def _deliver_components(base: Path, fetch) -> None:
    prod.produce_instrument_components(fetch, ["SYNTH"], session_date=D, output_dir=base)
    prod.write_private(base / "risk.json", prod.canonical({"schema": "V2_RISK_COMPONENTS_V1", "session_date": D.isoformat(), "symbols": {
        "SYNTH": {"value": 30.5, "producer": "codex-risk", "source_at": (NOW - timedelta(minutes=10)).isoformat(), "available_at": (NOW - timedelta(minutes=9)).isoformat()}}}))
    earn.produce_earnings(fetch, ["SYNTH"], session_date=D, output_dir=base, now=STAMP + timedelta(seconds=10))


def test_snapshot_keeps_names_pending_until_components_arrive_and_the_legacy_port_refuses_the_new_earnings_policy(tmp_path: Path) -> None:
    root, base, fetch, book = _root_with_quote(tmp_path, "published_far")
    loader = snap.ComponentLoader(root, D, ["SYNTH"])
    calendar = calendar_module.ShadowCalendar()
    # 1. nothing but the quote and the registry: the name is pending, not a concluded DATA_INELIGIBLE
    row, inputs, evaluation = _observe(root, loader, book, calendar, 1)
    assert row["data_available"] is False and contract.input_complete(inputs) is False
    assert inputs.available_at["daily"] is None and inputs.available_at["risk"] is None and inputs.available_at["earnings"] is None
    # 2. the responses land during the window: the next assembly carries them; daily and risk are complete and valid,
    #    while the EMENDA 3 earnings component (policy/evidence/exclusion) is refused by the legacy reader BY SCHEMA:
    #    a concluded invalid response, hence DATA_INELIGIBLE — never legacy coverage, never ELIGIBLE, never pending.
    _deliver_components(base, fetch)
    row, inputs, evaluation = _observe(root, loader, book, calendar, 2)
    assert contract.input_complete(inputs) is True and row["data_available"] is False
    assert [d["code"] for d in row["diagnostics"]] == ["EARNINGS_MISSING"]
    assert evaluation["status"] == "DATA_INELIGIBLE", evaluation
    assert any("EARNINGS" in reason for reason in evaluation["reasons"]), evaluation
    for code in ("SOURCE_DAILY_COVERAGE_UNVERIFIED", "SPLIT_COVERAGE_UNVERIFIED", "DAILY_BARS_COUNT_OR_TYPE", "RISK_SCORE_INVALID"):
        assert code not in evaluation["reasons"], evaluation
    # 3. a concluded invalid risk response (extra field) is carried as concluded, not turned into a wait
    prod.write_private(base / "risk.json", prod.canonical({"schema": "V2_RISK_COMPONENTS_V1", "session_date": D.isoformat(), "symbols": {
        "SYNTH": {"value": 30.5, "producer": "codex-risk", "extra": 1, "source_at": (NOW - timedelta(minutes=10)).isoformat(), "available_at": (NOW - timedelta(minutes=9)).isoformat()}}}))
    row, inputs, evaluation = _observe(root, loader, book, calendar, 3)
    assert contract.input_complete(inputs) is True and evaluation["status"] == "DATA_INELIGIBLE"
    assert "RISK_MISSING" in [d["code"] for d in row["diagnostics"]]


@pytest.mark.parametrize("history,expected_reason", [("cadence_inside", "EARNINGS_EXPECTED_WITHIN_HORIZON"),
                                                     ("future_only", "EARNINGS_LAST_REPORT_UNKNOWN"),
                                                     ("bad_date", "EARNINGS_EVIDENCE_INVALID")])
def test_codex_earnings_counterexamples_never_reach_eligible(tmp_path: Path, history: str, expected_reason: str) -> None:
    root, base, fetch, book = _root_with_quote(tmp_path, history)
    _deliver_components(base, fetch)
    component = json.loads((base / "earnings.json").read_bytes())["symbols"]["SYNTH"]
    assert expected_reason in component["exclusion"]["reasons"] and component["exclusion"]["excluded"] is True
    row, inputs, evaluation = _observe(root, snap.ComponentLoader(root, D, ["SYNTH"]), book, calendar_module.ShadowCalendar(), 1)
    assert contract.input_complete(inputs) is True and evaluation["status"] == "DATA_INELIGIBLE", evaluation
