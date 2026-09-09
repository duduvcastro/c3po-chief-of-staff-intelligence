"""The §7.3 weekly panel (rev 7: PROMO-1, PROMO-2, PROMO-2-ZERO; §2.2 labels and clocks; §2.6 log-error): pure functions
pinned on hand-built observations, the service pinned on the in-memory double with synthetic records and synthetic
bars (never the network, never a real database), the reader pinned in memory and by its SQL text, the CLI by its
stdout. Every behaviour named in the design has a test here."""
from __future__ import annotations

import json
import math
import os
import random
import stat
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import pytest

from app import valuation_official as official
from app import valuation_panel as panel
from app import valuation_price_history as series
from app import valuation_v3_shadow as frozen_v3
from app.config import Settings
from app.database import Database
from app.market_data.eodhd import EodhdClient

UTC = timezone.utc
D = timedelta(days=1)
H = timedelta(hours=1)
SOURCE_V32 = "v3_2_shadow"
T_FRIDAY = date(2026, 9, 4)  # 2026-09-07 is Labor Day (XNYS) and Independence Day (BVMF): two sessions after Friday 09-04 is Wednesday 09-09


class ScriptedHttp:
    """Answers /api/eod calls per provider symbol (the producer's path only — the panel never asks)."""

    def __init__(self, bars_by_symbol: dict[str, list[dict]]) -> None:
        self.bars_by_symbol = bars_by_symbol
        self.calls: list[dict] = []

    def get_json(self, url: str, *, params=None, headers=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        return self.bars_by_symbol.get(url.rsplit("/", 1)[-1], [])


def _settings() -> Settings:
    return Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False)


def _producer(database: Database, bars_by_symbol: dict[str, list[dict]]) -> series.PriceHistoryService:
    http = ScriptedHttp(bars_by_symbol)
    return series.PriceHistoryService(_settings(), database, http, eodhd=EodhdClient("https://eodhd.com", "secret", http))  # type: ignore[arg-type]


def _bar(day: str, close: float, adjusted: float | None = None, volume: float = 1000.0) -> dict:
    return {"date": day, "close": close, "adjusted_close": close if adjusted is None else adjusted, "volume": volume}


def _row(symbol: str, *, tp: float, buy_in: float, price: float | None, internal_tp: float, **extra: object) -> dict:
    return {"symbol": symbol, "our_tp": tp, "buy_in": buy_in, "price": price, "internal_tp": internal_tp, "public_consensus_tp": tp * 1.1,
            "analyst_count": 12, "consensus_weight_percent": 25.0, "methods": {"dcf": tp * 1.01, "multiples": tp * 0.99},
            "calibration_factor": 1.02, "risk_score": 40.0, "valuation_confidence": 70.0, "method_dispersion_percent": 3.0,
            "signal_quality": "validated", "bear_tp": tp * 0.8, "bull_tp": tp * 1.2, "as_of": "2026-09-07T22:00:00+00:00", **extra}


def _resigned(record: dict, **changes: object) -> dict:
    """A record with ``changes`` applied and its ``row_sha256`` recomputed (the identity a reader verifies)."""
    core = {key: value for key, value in record.items() if key not in ("id", "row_sha256")}
    core.update(changes)
    return {**core, "id": record["id"], "row_sha256": official.canonical_sha256(core)}


def _record(market: str, symbol: str, *, tp: float, price: float | None, instant: datetime, published_at: datetime | None = None,
            source: str = official.SOURCE_OFFICIAL, source_version: str = "7", cycle_id: str | None = None, rerun_of: str | None = None, **extra: object) -> dict:
    """A prediction record of any source: the official emitter's shape (``prediction_from_row``), re-signed when the
    source is not the official one (the panel reads the record; the store verifies only V1 hashes). The consensus block
    is attested one hour BEFORE the prediction instant unless the caller says otherwise (``consensus_published_at``)."""
    extra.setdefault("consensus_published_at", instant - H)
    row = _row(symbol, tp=tp, buy_in=(price or tp) * 0.9, price=price, internal_tp=tp, **extra)
    record = official.prediction_from_row(row, market=market, scope="universe", cycle_id=cycle_id or f"{market}-{symbol}-{instant.isoformat()}-{source}",
                                          source_version=source_version, prediction_instant=instant, published_at=published_at, rerun_of=rerun_of)
    assert record is not None
    return _resigned(record, source=source) if source != official.SOURCE_OFFICIAL else record


def _obs(symbol: str, session: str, *, status: str = "labelled", e_source: float | None = None, e_consensus: float | None = None,
         consensus_status: str = "present", within: bool | None = None, horizon: int = 126, tp: float = 100.0, consensus_tp: float | None = 110.0) -> dict:
    """A hand-built observation for the pure metrics (the shape ``observation`` produces, one horizon)."""
    labelled = status == "labelled"
    entry = {"status": status, "eligible": status not in panel.INELIGIBLE, "session": None, "realized": None, "close": None, "bar_sha256": None,
             "e_source": e_source if labelled else None, "e_consensus": e_consensus if labelled else None, "within_bands": within if labelled else None}
    return {"symbol": symbol, "session": session, "tp": tp, "consensus": {"tp": consensus_tp}, "consensus_status": consensus_status, "rerun_of": None,
            "basis_status": "ok", "source_version": "7", "horizons": {str(horizon): entry}}


# ------------------------------------------------------------------ pure functions
def test_quantile_is_the_frozen_linear_convention() -> None:
    for values in ([3.0, 1.0, 2.0], [5.5, -1.0, 2.0, 2.0, 9.0, 0.5], [7.0], [0.0, -0.0]):
        for fraction in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
            assert panel.quantile(values, fraction) == frozen_v3._percentile(list(values), fraction)
    assert panel.quantile([], 0.5) is None
    assert math.copysign(1.0, panel.quantile([-0.0, -0.0], 0.5) or 0.0) == 1.0  # -0.0 normalised: the hash must survive a JSON round trip


def test_log_error_is_the_spec_formula_in_the_basis_of_the_prediction_session() -> None:
    # e = ln(tp · a(T)) − ln(adjusted_close(T+h)), a(T) = adjusted_close(T) / close(T) of the same vintage (§2.2, §2.6)
    assert panel.log_error(100.0, 1.0, 100.0) == 0.0
    assert panel.log_error(120.0, 0.5, 60.0) == 0.0  # a split before T: the TP in T's close basis × a(T) is the adjusted basis
    assert panel.log_error(100.0, 1.0, 110.0) == pytest.approx(math.log(100.0 / 110.0))
    assert panel.log_error(100.0, 1.0, 110.0) > panel.log_error(100.0, 1.0, 112.0)  # a dividend credited to the realized price lowers the error of a high TP
    assert math.copysign(1.0, panel.log_error(100.0, 1.0, 100.0)) == 1.0


def test_admissible_records_refuse_late_publications_duplicates_windows_and_clockless_rows() -> None:
    cut = datetime(2026, 9, 12, tzinfo=UTC)
    friday = datetime(2026, 9, 4, 22, 0, tzinfo=UTC)
    original = _record("NASDAQ", "AAPL", tp=250.0, price=230.0, instant=friday, cycle_id="c1")
    later_same_session = _record("NASDAQ", "AAPL", tp=251.0, price=230.0, instant=friday + H, cycle_id="c2")
    rerun = _record("NASDAQ", "AAPL", tp=252.0, price=230.0, instant=friday, published_at=friday + 6 * D, cycle_id="c3", rerun_of="c1")
    published_after_cut = _record("NASDAQ", "AAPL", tp=253.0, price=230.0, instant=datetime(2026, 9, 8, 22, 0, tzinfo=UTC), published_at=cut + H, cycle_id="c4")
    tuesday = _record("NASDAQ", "AAPL", tp=254.0, price=230.0, instant=datetime(2026, 9, 8, 22, 0, tzinfo=UTC), cycle_id="c5")
    other_version = _record("NASDAQ", "AAPL", tp=255.0, price=230.0, instant=friday, cycle_id="c6", source_version="8")
    other_source = _record("NASDAQ", "AAPL", tp=256.0, price=230.0, instant=friday, cycle_id="c7", source=SOURCE_V32)
    legacy = {**_record("NASDAQ", "MSFT", tp=400.0, price=380.0, instant=friday, cycle_id="c8"), "published_at": None}  # a V1 row: no availability clock
    non_positive = {**_record("NASDAQ", "MSFT", tp=400.0, price=380.0, instant=friday, cycle_id="c9"), "tp": 0.0}
    unparseable = {**_record("NASDAQ", "MSFT", tp=400.0, price=380.0, instant=friday, cycle_id="c10"), "session_date": "soon"}
    saturday = _resigned(_record("NASDAQ", "MSFT", tp=400.0, price=380.0, instant=friday, cycle_id="c11"), session_date="2026-09-05")  # not a session of XNYS
    holiday = _resigned(_record("B3", "PETR4", tp=40.0, price=36.0, instant=friday, cycle_id="c12"), session_date="2026-09-07")  # Independence Day on BVMF
    marketless = _resigned(_record("NASDAQ", "MSFT", tp=400.0, price=380.0, instant=friday, cycle_id="c13"), market="XETRA")  # no calendar can answer
    records = [tuesday, later_same_session, rerun, published_after_cut, original, other_version, other_source, legacy, non_positive, unparseable, saturday, holiday, marketless]
    kept, refusals = panel.admissible_records(records, cut=cut)
    # ONE record per (source, symbol, session): c1 is the first that existed (smallest published_at) — the later cycle, the re-run AND the
    # other version of the same source are duplicates of it; another source is another key
    assert [r["cycle_id"] for r in kept] == ["c1", "c7", "c5"]
    assert refusals == {"duplicate_session": 3, "no_published_at": 1, "published_at_not_before_cut": 1, "session_not_in_calendar": 3, "session_unparseable": 1,
                        "tp_not_positive": 1}
    # a re-run without its original in the window is admissible (its published_at < C) and is what the service counts as a re-run
    kept, refusals = panel.admissible_records([rerun, tuesday], cut=cut)
    assert [r["cycle_id"] for r in kept] == ["c3", "c5"] and refusals == {}
    # the tie-break is (published_at, prediction_instant, symbol, cycle): the smallest published_at enters even when its prediction_instant is later
    kept, refusals = panel.admissible_records([rerun, later_same_session], cut=cut)
    assert [r["cycle_id"] for r in kept] == ["c2"] and refusals == {"duplicate_session": 1}
    same_clocks = _record("NASDAQ", "AAPL", tp=257.0, price=230.0, instant=friday, cycle_id="c0")  # equal clocks: the cycle id decides, deterministically
    assert [r["cycle_id"] for r in panel.admissible_records([original, same_clocks], cut=cut)[0]] == ["c0"] == [r["cycle_id"] for r in panel.admissible_records([same_clocks, original], cut=cut)[0]]
    # the window is on prediction_instant, [since, until)
    kept, refusals = panel.admissible_records([original, tuesday], cut=cut, since=friday, until=datetime(2026, 9, 8, 22, 0, tzinfo=UTC))
    assert [r["cycle_id"] for r in kept] == ["c1"] and refusals == {"outside_window": 1}
    kept, refusals = panel.admissible_records([original, tuesday], cut=cut, since=friday + timedelta(seconds=1))
    assert [r["cycle_id"] for r in kept] == ["c5"] and refusals == {"outside_window": 1}
    # published_at exactly at the cut is not before it
    at_cut = _record("NASDAQ", "AAPL", tp=1.0, price=1.0, instant=friday, published_at=cut, cycle_id="c11")
    assert panel.admissible_records([at_cut], cut=cut) == ([], {"published_at_not_before_cut": 1})


def test_observation_resolves_labels_adjustment_basis_bands_and_the_persisted_consensus() -> None:
    record = _record("NASDAQ", "AAPL", tp=250.0, price=230.0, instant=datetime(2026, 9, 4, 22, 0, tzinfo=UTC))
    at_session = {"close": 230.0, "adjusted_close": 115.0}  # a(T) = 0.5
    labels = {21: {"status": "labelled", "session": "2026-10-05", "close": 240.0, "adjusted_close": 120.0, "bar_sha256": "b" * 64},
              42: {"status": "not_yet_mature", "session": "2026-11-04"}, 63: {"status": "beyond_calendar", "session": None},
              126: {"status": "missing_bar", "session": "2027-03-08"}}
    row = panel.observation(record, at_session, labels)
    assert row["symbol"] == "AAPL" and row["session"] == "2026-09-04" and row["adjustment"] == 0.5 and row["basis_status"] == "ok" and row["close_at_session"] == 230.0
    assert row["consensus"]["tp"] == 275.0 and row["consensus"]["currency"] == "USD" and row["consensus"]["horizon"] == "12m" and row["consensus_status"] == "present"
    assert row["consensus"]["published_at"] == "2026-09-04T21:00:00+00:00"  # the block's own instant, before the prediction: the consensus that existed then
    assert len(row["consensus"]["payload_sha256"]) == 64 and row["bands"] == {"bear_tp": 200.0, "bull_tp": 300.0} and row["rerun_of"] is None
    h21 = row["horizons"]["21"]
    assert h21["eligible"] and h21["status"] == "labelled" and h21["realized"] == 120.0 and h21["close"] == 240.0 and h21["bar_sha256"] == "b" * 64
    assert h21["e_source"] == pytest.approx(math.log(250.0 * 0.5 / 120.0)) and h21["e_consensus"] == pytest.approx(math.log(275.0 * 0.5 / 120.0))
    assert h21["within_bands"] is True  # realized in T's basis = 120 / 0.5 = 240 ∈ [200, 300]
    assert row["horizons"]["42"] == {**row["horizons"]["42"], "eligible": False, "status": "not_yet_mature", "e_source": None}
    assert row["horizons"]["63"]["eligible"] is False and row["horizons"]["63"]["status"] == "beyond_calendar"
    assert row["horizons"]["126"]["eligible"] is True and row["horizons"]["126"]["status"] == "missing_bar" and row["horizons"]["126"]["e_source"] is None
    # realized outside the bands (in T's basis: 80 / 0.5 = 160 < 200)
    outside = panel.observation(record, at_session, {21: {**labels[21], "adjusted_close": 80.0}})["horizons"]["21"]
    assert outside["within_bands"] is False and outside["e_source"] == pytest.approx(math.log(125.0 / 80.0))
    # no bar at T in the vintage: a(T) unknown → the labelled bar is not a label (§2.2)
    unknown = panel.observation(record, None, labels)
    assert unknown["adjustment"] is None and unknown["basis_status"] == series.LABEL_ADJUSTMENT_UNKNOWN
    assert unknown["horizons"]["21"]["status"] == series.LABEL_ADJUSTMENT_UNKNOWN and unknown["horizons"]["21"]["eligible"] and unknown["horizons"]["21"]["e_source"] is None
    assert unknown["horizons"]["42"]["status"] == "not_yet_mature" and unknown["horizons"]["126"]["status"] == "missing_bar"  # the label's own cause first
    # basis check: |price − close(T)| / close(T) > TOL_BASIS → basis_mismatch; no price → basis_unverifiable
    mismatch = panel.observation(record, {"close": 300.0, "adjusted_close": 300.0}, labels)
    assert mismatch["basis_status"] == panel.BASIS_MISMATCH and mismatch["horizons"]["21"]["status"] == panel.BASIS_MISMATCH and mismatch["adjustment"] == 1.0
    within_tolerance = panel.observation(record, {"close": 234.0, "adjusted_close": 234.0}, labels)  # 1.7 % ≤ 2 %
    assert within_tolerance["basis_status"] == "ok"
    priceless = panel.observation(_record("NASDAQ", "AAPL", tp=250.0, price=None, instant=datetime(2026, 9, 4, 22, 0, tzinfo=UTC)), at_session, labels)
    assert priceless["price"] is None and priceless["basis_status"] == panel.BASIS_UNVERIFIABLE and priceless["horizons"]["21"]["status"] == panel.BASIS_UNVERIFIABLE
    # §2.2: the bar at T must be in the record's currency — a bar in another currency is no basis, whatever the tolerance says (its own cause)
    foreign_bar = panel.observation(record, {**at_session, "currency": "BRL"}, labels)
    assert foreign_bar["basis_status"] == panel.BASIS_CURRENCY_MISMATCH == foreign_bar["horizons"]["21"]["status"] and foreign_bar["horizons"]["21"]["e_source"] is None
    assert foreign_bar["adjustment"] == 0.5 and foreign_bar["horizons"]["21"]["eligible"] and foreign_bar["horizons"]["42"]["status"] == "not_yet_mature"
    assert panel.observation(record, {**at_session, "currency": "USD"}, labels)["basis_status"] == "ok"
    assert panel.observation(record, {**at_session, "currency": ""}, labels)["basis_status"] == "ok"  # no currency on either side: nothing to compare
    assert panel.observation({**record, "currency": None}, {**at_session, "currency": "BRL"}, labels)["basis_status"] == "ok"
    # the consensus is the block the record persisted: absent, or in another currency → outside the common mask, the source still measured
    absent = panel.observation(_record("NASDAQ", "AAPL", tp=250.0, price=230.0, instant=datetime(2026, 9, 4, 22, 0, tzinfo=UTC), public_consensus_tp=None),
                               at_session, labels)
    assert absent["consensus_status"] == "absent" and absent["consensus"]["tp"] is None and absent["horizons"]["21"]["e_consensus"] is None
    assert absent["horizons"]["21"]["e_source"] == h21["e_source"]
    foreign = panel.observation(_record("NASDAQ", "AAPL", tp=250.0, price=230.0, instant=datetime(2026, 9, 4, 22, 0, tzinfo=UTC), consensus_currency="BRL"),
                                at_session, labels)
    assert foreign["consensus_status"] == "consensus_currency_mismatch" and foreign["consensus"]["currency"] == "BRL" and foreign["horizons"]["21"]["e_consensus"] is None
    # PROMO-2 c: the consensus that EXISTED at the prediction instant — a block published later (a re-run's) is not it; at the instant it is
    instant = datetime(2026, 9, 4, 22, 0, tzinfo=UTC)
    later = panel.observation(_record("NASDAQ", "AAPL", tp=250.0, price=230.0, instant=instant, consensus_published_at=instant + timedelta(seconds=1)), at_session, labels)
    assert later["consensus_status"] == "consensus_after_prediction" and later["consensus"]["tp"] == 275.0 and later["horizons"]["21"]["e_consensus"] is None
    assert later["horizons"]["21"]["e_source"] == h21["e_source"]
    at_instant = panel.observation(_record("NASDAQ", "AAPL", tp=250.0, price=230.0, instant=instant, consensus_published_at=instant), at_session, labels)
    assert at_instant["consensus_status"] == "present" and at_instant["horizons"]["21"]["e_consensus"] == h21["e_consensus"]
    dated = panel.observation(_record("NASDAQ", "AAPL", tp=250.0, price=230.0, instant=instant, consensus_published_at="", consensus_as_of="2026-09-04"), at_session, labels)
    assert dated["consensus"]["published_at"] == "2026-09-04" and dated["consensus_status"] == "present"  # a date-only clock: that day's midnight UTC, before 22:00
    # an unattested block — no instant, no currency, no hash, or an unparseable instant — is never the consensus of PROMO-2 c
    for field, value in (("published_at", None), ("published_at", ""), ("published_at", "soon"), ("currency", None), ("payload_sha256", None)):
        block = {**record["decomposition"]["consensus"], field: value}
        unattested = panel.observation({**record, "decomposition": {**record["decomposition"], "consensus": block}}, at_session, labels)
        assert unattested["consensus_status"] == "consensus_unattested" and unattested["consensus"]["tp"] == 275.0 and unattested["horizons"]["21"]["e_consensus"] is None, field
        assert unattested["horizons"]["21"]["e_source"] == h21["e_source"]
    # a record without the block (not the official emitter's shape): the flat column is reported as the tp, and attests nothing
    flat = panel.observation({**record, "decomposition": {**record["decomposition"], "consensus": {}}, "consensus_tp": 280.0}, at_session, labels)
    assert flat["consensus_status"] == "consensus_unattested" and flat["consensus"] == {"tp": 280.0, "source": None, "horizon": None, "currency": None, "published_at": None,
                                                                                        "payload_sha256": None}
    assert flat["horizons"]["21"]["e_consensus"] is None and flat["horizons"]["21"]["e_source"] == h21["e_source"]
    assert panel.observation({**record, "decomposition": {}, "consensus_tp": None}, at_session, labels)["consensus_status"] == "absent"
    # null bands: no coverage verdict, counted by the metrics
    bandless = panel.observation(_record("NASDAQ", "AAPL", tp=250.0, price=230.0, instant=datetime(2026, 9, 4, 22, 0, tzinfo=UTC), bear_tp=None, bull_tp=None),
                                 at_session, labels)
    assert bandless["bands"] == {"bear_tp": None, "bull_tp": None} and bandless["horizons"]["21"]["within_bands"] is None and bandless["horizons"]["21"]["e_source"] == h21["e_source"]
    # a re-run keeps its provenance
    rerun = panel.observation(_record("NASDAQ", "AAPL", tp=250.0, price=230.0, instant=datetime(2026, 9, 4, 22, 0, tzinfo=UTC),
                                      published_at=datetime(2026, 9, 6, tzinfo=UTC), rerun_of="c1"), at_session, labels)
    assert rerun["rerun_of"] == "c1" and rerun["published_at"] == "2026-09-06T00:00:00+00:00" and rerun["prediction_instant"] == "2026-09-04T22:00:00+00:00"


def test_horizon_metrics_keep_immature_out_of_the_denominator_and_intersect_the_mask() -> None:
    observations = [
        _obs("A", "s1", e_source=0.1, e_consensus=0.2, within=True),
        _obs("A", "s2", e_source=-0.1, consensus_status="absent", within=None),
        _obs("B", "s1", e_source=0.3, e_consensus=0.1, within=False),
        _obs("B", "s2", status="missing_bar"),
        _obs("C", "s1", status="not_yet_mature"),
        _obs("C", "s2", status="beyond_calendar"),
        _obs("D", "s1", status="no_vintage"),
        _obs("E", "s1", e_source=0.0, consensus_status="consensus_currency_mismatch", within=True),
        _obs("F", "s1", status=panel.BASIS_MISMATCH),
        _obs("G", "s1", e_source=0.0, consensus_status="consensus_unattested", within=True),
        _obs("G", "s2", e_source=0.0, consensus_status="consensus_after_prediction", within=True),
        _obs("H", "s1", status=panel.BASIS_CURRENCY_MISMATCH),
    ]
    assert panel.INELIGIBLE == ("not_yet_mature", "beyond_calendar")  # a session not in the calendar is refused before any observation exists
    metrics = panel.horizon_metrics(observations, 126)
    assert metrics["horizon_sessions"] == 126 and metrics["diagnostic_only"] is False
    assert panel.horizon_metrics([_obs("A", "s1", e_source=0.1, horizon=21)], 21)["diagnostic_only"] is True
    assert metrics["eligible"] == 10 and metrics["ineligible"] == {"beyond_calendar": 1, "not_yet_mature": 1}  # immature/beyond: outside the denominator (§2.2)
    assert metrics["labelled"] == 6
    assert metrics["attrition"] == {"rate": pytest.approx(4 / 10), "unavailable": 4, "by_cause": {panel.BASIS_CURRENCY_MISMATCH: 1, panel.BASIS_MISMATCH: 1, "missing_bar": 1, "no_vintage": 1}}
    assert metrics["source"] == {"n": 6, "mse": pytest.approx(0.11 / 6), "median_abs_log_error": pytest.approx(0.05), "mean_log_error": pytest.approx(0.05)}
    assert metrics["consensus"] == {"n": 2, "mse": pytest.approx(0.025), "median_abs_log_error": pytest.approx(0.15), "mean_log_error": pytest.approx(0.15)}
    assert metrics["source_on_common_mask"] == {"n": 2, "mse": pytest.approx(0.05), "median_abs_log_error": pytest.approx(0.2), "mean_log_error": pytest.approx(0.2)}
    assert metrics["common_mask"] == {"n": 2, "names": 2, "sessions": 1, "max_share_single_name": 0.5,
                                      "excluded": {"absent": 1, "consensus_after_prediction": 1, "consensus_currency_mismatch": 1, "consensus_unattested": 1}}
    assert metrics["band_coverage"] == {**metrics["band_coverage"], "n_with_bands": 5, "n_null_bands": 1, "within": 4, "fraction": pytest.approx(4 / 5)}
    empty = panel.horizon_metrics([], 126)
    assert empty["eligible"] == 0 and empty["attrition"]["rate"] is None and empty["source"]["mse"] is None and empty["band_coverage"]["fraction"] is None
    only_immature = panel.horizon_metrics([_obs("A", "s1", status="not_yet_mature")], 126)
    assert only_immature["eligible"] == 0 and only_immature["attrition"]["rate"] is None and only_immature["ineligible"] == {"not_yet_mature": 1}  # never 100 % false attrition


def test_decision_follows_the_pre_registered_order_and_the_zero_branches() -> None:
    # attrition first, before any count (§2.6, PROMO-2 d)
    unmeasured = panel.decision(0.001, 0.05, 100, 12, 12, 0.2)
    assert unmeasured["status"] == "UNMEASURED" and unmeasured["reasons"] == ["attrition_above_cap:0.2000>0.1"] and unmeasured["ratio"] == "N/D"
    assert not unmeasured["passes_k_1_00"] and not unmeasured["passes_k_1_05"] and unmeasured["tie"] is False
    assert panel.decision(0.0, 0.0, 100, 12, 12, None)["reasons"] == ["no_eligible_observations"]
    assert panel.decision(0.0, 0.0, 100, 12, 12, 0.1)["status"] == "TIE"  # exactly the cap is within it
    # the minimums after the intersection
    assert panel.decision(0.01, 0.02, 29, 12, 12, 0.0) == {**panel.decision(0.01, 0.02, 29, 12, 12, 0.0), "status": "INSUFFICIENT", "reasons": ["n_below_n_eval:29<30"]}
    assert panel.decision(0.01, 0.02, 30, 9, 12, 0.0)["reasons"] == ["names_below_min:9<10"]
    assert panel.decision(0.01, 0.02, 30, 12, 9, 0.0)["reasons"] == ["sessions_below_min:9<10"]
    assert panel.decision(0.01, 0.02, 5, 3, 2, 0.0)["reasons"] == ["n_below_n_eval:5<30", "names_below_min:3<10", "sessions_below_min:2<10"]
    assert panel.decision(None, 0.02, 30, 10, 10, 0.0)["reasons"] == ["mse_unavailable"] and panel.decision(None, 0.02, 30, 10, 10, 0.0)["status"] == "INSUFFICIENT"
    # PROMO-2-ZERO: both zero → tie (passes, marked); consensus zero and source > 0 → fail, ratio N/D; no epsilon
    tie = panel.decision(0.0, 0.0, 30, 10, 10, 0.0)
    assert tie["status"] == "TIE" and tie["tie"] is True and tie["ratio"] == "N/D" and tie["passes_k_1_00"] and tie["passes_k_1_05"] and tie["reasons"] == ["both_mse_zero"]
    fail_zero = panel.decision(1e-12, 0.0, 30, 10, 10, 0.0)
    assert fail_zero["status"] == "FAIL" and fail_zero["ratio"] == "N/D" and not fail_zero["passes_k_1_00"] and not fail_zero["passes_k_1_05"] and fail_zero["tie"] is False
    assert fail_zero["reasons"] == ["consensus_mse_zero_source_positive"]
    # the inequality at k = 1.00, with k = 1.05 reported
    passed = panel.decision(0.01, 0.01, 30, 10, 10, 0.05)
    assert passed["status"] == "PASS" and passed["ratio"] == 1.0 and passed["passes_k_1_00"] and passed["passes_k_1_05"] and passed["reasons"] == []
    assert panel.decision(0.0, 0.01, 30, 10, 10, 0.0)["status"] == "PASS" and panel.decision(0.0, 0.01, 30, 10, 10, 0.0)["ratio"] == 0.0
    secondary = panel.decision(0.0103, 0.01, 30, 10, 10, 0.0)
    assert secondary["status"] == "FAIL" and secondary["ratio"] == pytest.approx(1.03) and not secondary["passes_k_1_00"] and secondary["passes_k_1_05"]
    assert secondary["reasons"] == ["ratio_above_k_primary:1.030000"]
    neither = panel.decision(0.0106, 0.01, 30, 10, 10, 0.0)
    assert neither["status"] == "FAIL" and not neither["passes_k_1_00"] and not neither["passes_k_1_05"]
    assert passed == {**passed, "n": 30, "names": 10, "sessions": 10, "attrition": 0.05, "mse_source": 0.01, "mse_consensus": 0.01, "k_primary": 1.0, "k_secondary": 1.05}


def test_protocol_combination_needs_the_three_markets_measured() -> None:
    passed = panel.decision(0.009, 0.01, 30, 10, 10, 0.0)
    tie = panel.decision(0.0, 0.0, 30, 10, 10, 0.0)
    secondary = panel.decision(0.0103, 0.01, 30, 10, 10, 0.0)
    failed = panel.decision(0.02, 0.01, 30, 10, 10, 0.0)
    insufficient = panel.decision(0.009, 0.01, 10, 10, 10, 0.0)
    verdict = panel.protocol_combination({"B3": passed, "NASDAQ": tie, "NYSE": secondary})
    assert verdict == {"status": "PASS", "markets_missing": [], "markets_unmeasured": [], "passed_k_1_00": ["B3", "NASDAQ"], "passed_k_1_05": ["B3", "NASDAQ", "NYSE"],
                       "ties": ["NASDAQ"], "gate": False}
    assert panel.protocol_combination({"B3": passed, "NASDAQ": secondary, "NYSE": secondary})["status"] == "FAIL"  # one market at k = 1.00 is not two
    assert panel.protocol_combination({"B3": passed, "NASDAQ": passed, "NYSE": failed})["status"] == "FAIL"
    assert panel.protocol_combination({"B3": tie, "NASDAQ": tie, "NYSE": tie})["status"] == "PASS"
    partial = panel.protocol_combination({"B3": passed, "NASDAQ": passed})
    assert partial["status"] == "NOT_EVALUABLE" and partial["markets_missing"] == ["NYSE"]
    unmeasured = panel.protocol_combination({"B3": passed, "NASDAQ": passed, "NYSE": insufficient})
    assert unmeasured["status"] == "NOT_EVALUABLE" and unmeasured["markets_unmeasured"] == ["NYSE"] and unmeasured["passed_k_1_00"] == ["B3", "NASDAQ"]


def test_level_dispersion_publishes_median_centred_quantiles_and_non_blocking_sanity() -> None:
    rows = [_obs("A", "s1", tp=100.0 * (1 + deviation), consensus_tp=100.0) for deviation in (-0.2, -0.1, 0.0, 0.1, 0.5)]
    rows.append(_obs("B", "s1", consensus_status="absent", consensus_tp=None))
    rows.append(_obs("C", "s1", consensus_status="consensus_currency_mismatch"))
    rows.append(_obs("D", "s1", consensus_status="consensus_unattested"))
    rows.append(_obs("E", "s1", consensus_status="consensus_after_prediction"))
    result = panel.level_dispersion(rows, lambda row: str(row["source_version"]))
    assert list(result) == ["7"]
    profile = result["7"]
    assert profile["n"] == 5 and profile["median_level"] == pytest.approx(0.0)
    assert profile["consensus_excluded"] == {"absent": 1, "consensus_after_prediction": 1, "consensus_currency_mismatch": 1, "consensus_unattested": 1}
    assert profile["centred_quantiles"] == {"p10": pytest.approx(-0.16), "p25": pytest.approx(-0.1), "p75": pytest.approx(0.1), "p90": pytest.approx(0.34)}
    assert profile["sanity"] == {"p50_abs": pytest.approx(0.1), "p90_abs": pytest.approx(0.38), "threshold_p50": 0.15, "threshold_p90": 0.3, "status": "SANITY_OUT",
                                 "blocking": False}  # p90 above 30 %: reported, never blocking
    # a caller's label groups every observation under it; a tight profile is SANITY_OK; an unmeasured one says so
    labelled = panel.level_dispersion(rows, lambda row: "rev7")
    assert list(labelled) == ["rev7"] and labelled["rev7"]["n"] == 5
    tight = panel.level_dispersion([_obs("A", "s1", tp=105.0, consensus_tp=100.0), _obs("A", "s2", tp=103.0, consensus_tp=100.0)], lambda row: "x")["x"]
    assert tight["sanity"]["status"] == "SANITY_OK" and tight["median_level"] == pytest.approx(0.04) and tight["centred_quantiles"]["p10"] == pytest.approx(-0.008)
    none = panel.level_dispersion([_obs("B", "s1", consensus_status="absent", consensus_tp=None)], lambda row: "x")["x"]
    assert none == {**none, "n": 0, "median_level": None, "sanity": {**none["sanity"], "status": "SANITY_UNMEASURED", "p50_abs": None, "p90_abs": None}}


def test_the_protocol_constants_are_pre_registered_and_travel_inside_the_hashed_payload() -> None:
    assert panel.HORIZONS == (21, 42, 63, 126) and panel.DECISORY_HORIZON == 126 and panel.CONSENSUS_DECLARED_HORIZON == 252
    assert (panel.K_PRIMARY, panel.K_SECONDARY, panel.N_EVAL, panel.MIN_NAMES, panel.MIN_SESSIONS, panel.ATTRITION_CAP) == (1.0, 1.05, 30, 10, 10, 0.1)
    assert (panel.SANITY_P50, panel.SANITY_P90, panel.TOL_BASIS, panel.QUANTILES) == (0.15, 0.30, 0.02, (0.10, 0.25, 0.75, 0.90))
    assert panel.LABEL_CONVENTION == "total_return:adjusted_close" and panel.SCHEMA_VERSION == "VALUATION-PANEL-7-3-v1"
    assert panel.CALENDARS == {"B3": "BVMF", "NASDAQ": "XNYS", "NYSE": "XNYS"} == series.CALENDARS == official.CALENDARS
    protocol = panel.protocol()
    assert protocol["calendar"] == {"markets": panel.CALENDARS, "exchange_calendars": xcals.__version__} and protocol["gate"] is False  # the installed version (>=4.13,<5)
    assert protocol["horizons_sessions"] == [21, 42, 63, 126] and protocol["quantiles"] == [0.1, 0.25, 0.75, 0.9] and protocol["label_convention"] == panel.LABEL_CONVENTION
    cut = datetime(2026, 9, 14, 3, 0, tzinfo=UTC)
    decided = panel.decision(0.0, 0.0, 30, 10, 10, 0.0)
    results = {"B3": {"official_blend_v1": {"decision": decided}}}
    receipt = panel.receipt(cut=cut, window={"since": None, "until": None, "profile_label": None}, markets=["B3"], sources=["official_blend_v1"], results=results)
    assert receipt["schema"] == panel.SCHEMA_VERSION and receipt["payload_sha256"] == official.canonical_sha256(receipt["payload"])
    assert receipt["payload"]["protocol"] == protocol and receipt["payload"]["cut"] == "2026-09-14T03:00:00+00:00" and "built_at" not in json.dumps(receipt)
    assert receipt["payload"]["combination"]["official_blend_v1"]["status"] == "NOT_EVALUABLE" and receipt["payload"]["combination"]["official_blend_v1"]["markets_missing"] == ["NASDAQ", "NYSE"]
    assert receipt["payload"]["results"] == results and receipt["payload"]["results"] is not results  # a copy: the receipt never aliases the caller's dicts


def test_write_private_detail_is_exclusive_private_and_never_follows_a_link(tmp_path: Path) -> None:
    target = tmp_path / "detail.json"
    panel.write_private_detail(target, {"rows": [{"symbol": "AAPL"}]})
    assert stat.S_IMODE(target.stat().st_mode) == 0o600 and json.loads(target.read_text()) == {"rows": [{"symbol": "AAPL"}]}
    with pytest.raises(FileExistsError):
        panel.write_private_detail(target, {"rows": []})
    assert json.loads(target.read_text()) == {"rows": [{"symbol": "AAPL"}]}  # untouched
    link = tmp_path / "link.json"
    link.symlink_to(tmp_path / "elsewhere.json")  # dangling: O_EXCL refuses a symlink regardless of its target
    with pytest.raises(FileExistsError):
        panel.write_private_detail(link, {"rows": []})
    assert not (tmp_path / "elsewhere.json").exists()


# ------------------------------------------------------------------ the service on the double
def _friday_store() -> tuple[Database, dict[str, str]]:
    """Records at T = 2026-09-04 in NASDAQ (AAPL with consensus, MSFT without) and B3 (PETR4), and one vintage per market
    published 2026-09-11T02:00Z with bars for 09-04, 09-08 and 09-09 (PETR4 also 09-10)."""
    database = Database(_settings())
    friday = datetime(2026, 9, 4, 22, 0, tzinfo=UTC)
    cycles = {"NASDAQ": "nasdaq-0904", "B3": "b3-0904"}
    database.insert_valuation_predictions([
        _record("NASDAQ", "AAPL", tp=250.0, price=230.0, instant=friday, cycle_id=cycles["NASDAQ"]),
        _record("NASDAQ", "MSFT", tp=450.0, price=400.0, instant=friday, cycle_id=cycles["NASDAQ"], public_consensus_tp=None),
        _record("B3", "PETR4", tp=40.0, price=36.0, instant=friday, cycle_id=cycles["B3"]),
    ])
    producer = _producer(database, {"AAPL.US": [_bar("2026-09-04", 230.0, 115.0), _bar("2026-09-08", 231.0, 115.5), _bar("2026-09-09", 232.0, 116.0)],
                                    "MSFT.US": [_bar("2026-09-04", 400.0), _bar("2026-09-08", 401.0)],
                                    "PETR4.SA": [_bar("2026-09-04", 36.0), _bar("2026-09-08", 36.2), _bar("2026-09-09", 36.5), _bar("2026-09-10", 36.8)]})
    vintage_at = datetime(2026, 9, 11, 2, 0, tzinfo=UTC)
    producer.persist_run("NASDAQ", start=date(2026, 9, 1), end=date(2026, 9, 10), symbols=["AAPL", "MSFT"], now=vintage_at)
    producer.persist_run("B3", start=date(2026, 9, 1), end=date(2026, 9, 10), symbols=["PETR4"], now=vintage_at + timedelta(minutes=1))
    return database, cycles


def _by_symbol(detail: list[dict], market: str, symbol: str) -> dict:
    return next(row for row in detail if row["market"] == market and row["symbol"] == symbol)


def test_the_service_counts_sessions_over_the_holiday_refuses_look_ahead_and_never_touches_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(panel, "HORIZONS", (2,))  # the arithmetic under test is the calendar's; the real horizons are pinned elsewhere
    monkeypatch.setattr(panel, "DECISORY_HORIZON", 2)
    monkeypatch.setattr(panel, "CONSENSUS_DECLARED_HORIZON", 100000)  # beyond the calendar — after a cut within it: not yet mature, outside the denominator
    database, _ = _friday_store()
    database.insert_valuation_predictions([_resigned(_record("NASDAQ", "NVDA", tp=100.0, price=90.0, instant=datetime(2026, 9, 5, 22, 0, tzinfo=UTC), cycle_id="weekend"),
                                                     session_date="2026-09-05")])  # a Saturday: not a session of XNYS — refused, never an observation
    assert series.sessions_after("NASDAQ", T_FRIDAY, 2) == (date(2026, 9, 9), "ok") == series.sessions_after("B3", T_FRIDAY, 2)
    service = panel.PanelService(database, settings=_settings())
    cut = datetime(2026, 9, 12, tzinfo=UTC)
    receipt, detail = service.run(cut=cut, markets=("NASDAQ", "B3"))
    aapl, msft, petr = _by_symbol(detail, "NASDAQ", "AAPL"), _by_symbol(detail, "NASDAQ", "MSFT"), _by_symbol(detail, "B3", "PETR4")
    assert aapl["horizons"]["2"]["session"] == "2026-09-09" == petr["horizons"]["2"]["session"]  # 09-07 is a holiday on both calendars
    assert aapl["adjustment"] == 0.5 and aapl["horizons"]["2"]["realized"] == 116.0 and aapl["horizons"]["2"]["e_source"] == pytest.approx(math.log(250.0 * 0.5 / 116.0))
    assert aapl["horizons"]["2"]["e_consensus"] == pytest.approx(math.log(275.0 * 0.5 / 116.0)) and aapl["horizons"]["2"]["within_bands"] is True
    assert petr["adjustment"] == 1.0 and petr["horizons"]["2"]["e_source"] == pytest.approx(math.log(40.0 / 36.5)) and petr["horizons"]["2"]["e_consensus"] == pytest.approx(math.log(44.0 / 36.5))
    assert msft["horizons"]["2"]["status"] == "missing_bar" and msft["consensus_status"] == "absent"  # the provider gave no 09-09 bar for it
    assert series.sessions_after("NASDAQ", T_FRIDAY, 100000) == (None, "beyond_calendar")  # the calendar ends at today + 1 year: a wall-clock bound
    assert aapl["horizons"]["100000"] == {**aapl["horizons"]["100000"], "status": "not_yet_mature", "session": None, "eligible": False}  # after the cut either way
    assert not any(row["symbol"] == "NVDA" for row in detail)
    nasdaq = receipt["payload"]["results"]["NASDAQ"]["official_blend_v1"]
    assert nasdaq["records"] == {"read": 3, "admissible": 2, "refused": {"session_not_in_calendar": 1}, "reruns": 0} and nasdaq["observations"]["basis"] == {"ok": 2}
    assert nasdaq["horizons"]["2"]["eligible"] == 2 and nasdaq["horizons"]["2"]["labelled"] == 1 and nasdaq["horizons"]["2"]["attrition"] == {"rate": 0.5, "unavailable": 1, "by_cause": {"missing_bar": 1}}
    assert nasdaq["decision"]["status"] == "UNMEASURED" and nasdaq["decision"]["reasons"] == ["attrition_above_cap:0.5000>0.1"]
    assert nasdaq["consensus_declared_horizon"] == {**nasdaq["consensus_declared_horizon"], "consensus_only": True, "eligible": 0, "ineligible": {"not_yet_mature": 2}}
    assert "source" not in nasdaq["consensus_declared_horizon"] and "band_coverage" not in nasdaq["consensus_declared_horizon"]
    assert nasdaq["cut_within_calendar_horizon"] is True and "beyond_calendar" not in json.dumps(receipt)
    assert nasdaq["last_closed_session"] == "2026-09-11" and nasdaq["vintage"]["status"] == "ok" and nasdaq["vintage"]["window"] == ["2026-09-01", "2026-09-10"]
    assert nasdaq["vintage"]["available_at"] == "2026-09-11T02:00:00+00:00" and nasdaq["level_dispersion"]["7"]["n"] == 1 and nasdaq["level_dispersion"]["7"]["consensus_excluded"] == {"absent": 1}
    b3 = receipt["payload"]["results"]["B3"]["official_blend_v1"]
    assert b3["horizons"]["2"]["labelled"] == 1 and b3["horizons"]["2"]["attrition"]["rate"] == 0.0 and b3["decision"]["status"] == "INSUFFICIENT"
    assert b3["decision"]["reasons"] == ["n_below_n_eval:1<30", "names_below_min:1<10", "sessions_below_min:1<10"]
    # never the network: the reader's HTTP client raises, and was never asked; the vintage reads are memoised per market for the whole run
    assert service.http is not None and service.http.calls == 0
    with pytest.raises(RuntimeError, match="never reaches the network"):
        service.http.get_json("https://eodhd.com/api/eod/AAPL.US")
    assert service.http.calls == 1 and service.reads.reads == 4  # one publication + one manifest per market, not one pair per label_bar
    assert isinstance(service.price_history, series.PriceHistoryService) and service.price_history.database is not database  # the proxy, not the store
    # look-ahead: a cut before the publication sees no vintage (the bars exist in the store, but were not available) — a missing label, never a price
    blind = panel.PanelService(database, settings=_settings())
    before_publication, rows = blind.run(cut=datetime(2026, 9, 10, tzinfo=UTC), markets=("NASDAQ",))
    cell = before_publication["payload"]["results"]["NASDAQ"]["official_blend_v1"]
    assert cell["vintage"] == {"status": None, "publication_id": None, "price_snapshot_id": None, "available_at": None, "fetched_at": None, "window": None}
    assert cell["horizons"]["2"]["attrition"] == {"rate": 1.0, "unavailable": 2, "by_cause": {"no_vintage": 2}} and cell["decision"]["status"] == "UNMEASURED"
    assert cell["observations"]["basis"] == {series.LABEL_ADJUSTMENT_UNKNOWN: 2} and _by_symbol(rows, "NASDAQ", "AAPL")["horizons"]["2"]["status"] == "no_vintage"
    assert blind.reads.reads == 1  # "nothing before the cut" is memoised too
    # maturity is the exchange close: a cut exactly at the close of T + h is not mature — outside the denominator, not attrition
    at_close, _ = panel.PanelService(database, settings=_settings()).run(cut=datetime(2026, 9, 9, 20, 0, tzinfo=UTC), markets=("NASDAQ", "B3"))
    for market in ("NASDAQ", "B3"):
        cell = at_close["payload"]["results"][market]["official_blend_v1"]
        assert cell["horizons"]["2"]["eligible"] == 0 and cell["horizons"]["2"]["ineligible"] == {"not_yet_mature": 2 if market == "NASDAQ" else 1}
        assert cell["horizons"]["2"]["attrition"]["rate"] is None and cell["decision"] == {**cell["decision"], "status": "UNMEASURED", "reasons": ["no_eligible_observations"]}
    assert at_close["payload"]["results"]["NASDAQ"]["official_blend_v1"]["last_closed_session"] == "2026-09-08"
    # a record published at/after the cut is refused, and a source without records is an empty, declared cell
    late = _record("NASDAQ", "NVDA", tp=100.0, price=90.0, instant=datetime(2026, 9, 8, 22, 0, tzinfo=UTC), published_at=cut + H, cycle_id="late")
    database.insert_valuation_predictions([late])
    again, _ = panel.PanelService(database, settings=_settings()).run(cut=cut, markets=("NASDAQ",), sources=("official_blend_v1", SOURCE_V32))
    assert again["payload"]["results"]["NASDAQ"]["official_blend_v1"]["records"] == {"read": 4, "admissible": 2, "refused": {"published_at_not_before_cut": 1, "session_not_in_calendar": 1},
                                                                                     "reruns": 0}
    empty = again["payload"]["results"]["NASDAQ"][SOURCE_V32]
    assert empty["records"]["read"] == 0 and empty["decision"]["status"] == "UNMEASURED" and empty["level_dispersion"] == {} and empty["observations"]["n"] == 0
    assert again["payload"]["sources"] == ["official_blend_v1", SOURCE_V32] and set(again["payload"]["combination"]) == {"official_blend_v1", SOURCE_V32}


def test_the_service_refuses_naive_clocks_unknown_markets_and_empty_sources() -> None:
    service = panel.PanelService(Database(_settings()), settings=_settings())
    with pytest.raises(ValueError, match="cut must be a time-zone aware datetime"):
        service.run(cut=datetime(2026, 9, 12))
    with pytest.raises(ValueError, match="since must be a time-zone aware datetime"):
        service.run(cut=datetime(2026, 9, 12, tzinfo=UTC), since=datetime(2026, 9, 1))
    with pytest.raises(ValueError, match="since .* must precede until"):
        service.run(cut=datetime(2026, 9, 12, tzinfo=UTC), since=datetime(2026, 9, 2, tzinfo=UTC), until=datetime(2026, 9, 1, tzinfo=UTC))
    with pytest.raises(ValueError, match="unknown markets \\['XETRA'\\]"):
        service.run(cut=datetime(2026, 9, 12, tzinfo=UTC), markets=("B3", "xetra"))
    with pytest.raises(ValueError, match="no sources"):
        service.run(cut=datetime(2026, 9, 12, tzinfo=UTC), sources=("", " "))
    receipt, detail = service.run(cut=datetime(2026, 9, 12, tzinfo=UTC), markets=("nasdaq",))  # case-insensitive market; an empty store is a declared empty panel
    assert receipt["payload"]["markets"] == ["NASDAQ"] and detail == [] and receipt["payload"]["results"]["NASDAQ"]["official_blend_v1"]["records"]["read"] == 0


def _decisory_store(*, permute: bool = False) -> tuple[Database, datetime, list[str], list[date]]:
    """NASDAQ, ten names × ten sessions from 2026-02-02, bars for every session up to T + 126 of the last one, one
    vintage published after that close. The official source predicts the realized price exactly (and so does its
    consensus): both MSE zero. ``v3_2_shadow`` predicts with log-error ±d, d² = 1.03 × 0.01, against a consensus with
    log-error ±0.1: ratio 1.03. Special cases on the first session: S00 without consensus, S01 with a BRL consensus,
    S02 without bands, S03 with a consensus published AFTER the prediction; S08 adjusted at half its close (a(T) =
    0.5, a constant split factor); the bar at T + 126 of S09's last session is missing. A duplicate session and a late
    re-run of the official source; for the shadow, a re-run of (S05, session 3) under another source version WITH its
    original in the window (a duplicate of it) and a re-run of (S06, session 4) WITHOUT its original (admissible,
    counted). ``permute`` reverses the order of the bars the provider answers and of the records inserted."""
    database = Database(_settings())
    market = "NASDAQ"
    symbols = [f"S{k:02d}" for k in range(10)]
    sessions = [series.sessions_after(market, date(2026, 2, 2), j)[0] for j in range(10)]
    assert all(session is not None for session in sessions)
    sessions = [session for session in sessions if session is not None]
    last_target, reason = series.sessions_after(market, sessions[-1], 126)
    assert last_target is not None and reason == "ok"
    calendar_sessions = [stamp.date() for stamp in series._calendar(market).sessions_in_range(sessions[0].isoformat(), last_target.isoformat())]
    d = 0.1 * math.sqrt(1.03)
    bars: dict[str, list[dict]] = {}
    for k, symbol in enumerate(symbols):
        close = 100.0 + k
        rows = [_bar(day.isoformat(), close, close / 2 if k == 8 else close) for day in calendar_sessions]
        if k == 9:
            rows = [row for row in rows if row["date"] != last_target.isoformat()]
        bars[f"{symbol}.US"] = rows[::-1] if permute else rows
    records: list[dict] = []
    for j, session in enumerate(sessions):
        instant = series.session_close(market, session) + H
        for k, symbol in enumerate(symbols):
            close = 100.0 + k
            sign = 1.0 if (j + k) % 2 == 0 else -1.0
            extra: dict[str, Any] = {}
            if j == 0 and k == 0:
                extra["public_consensus_tp"] = None
            if j == 0 and k == 1:
                extra["consensus_currency"] = "BRL"
            if j == 0 and k == 2:
                extra.update(bear_tp=None, bull_tp=None)
            if j == 0 and k == 3:
                extra["consensus_published_at"] = instant + H  # a block published after the prediction: not the consensus that existed then (PROMO-2 c)
            official_extra = {**extra, "public_consensus_tp": close} if "public_consensus_tp" not in extra else extra
            shadow_extra = {**extra, "public_consensus_tp": close * math.exp(sign * 0.1)} if "public_consensus_tp" not in extra else extra
            records.append(_record(market, symbol, tp=close, price=close, instant=instant, cycle_id=f"official-{j}", **official_extra))
            if j == 4 and k == 6:
                continue  # the shadow's original of (S06, session 4) is lost: only its re-run below exists
            records.append(_record(market, symbol, tp=close * math.exp(sign * d), price=close, instant=instant, source=SOURCE_V32, cycle_id=f"shadow-{j}", **shadow_extra))
    records.append(_record(market, "S03", tp=103.5, price=103.0, instant=series.session_close(market, sessions[1]) + 2 * H, cycle_id="official-1-again"))  # duplicate session
    records.append(_record(market, "S04", tp=104.5, price=104.0, instant=series.session_close(market, sessions[2]) + H, published_at=series.session_close(market, sessions[2]) + D,
                           cycle_id="official-2-rerun", rerun_of="official-2"))  # a late re-run of an original in the window: duplicate (the original wins)
    records.append(_record(market, "S05", tp=105.0 * math.exp(d), price=105.0, instant=series.session_close(market, sessions[3]) + H,
                           published_at=series.session_close(market, sessions[3]) + D, source=SOURCE_V32, cycle_id="shadow-3-rerun", rerun_of="shadow-3", source_version="9",
                           public_consensus_tp=105.0 * math.exp(0.1)))  # another VERSION of the same source for the same (symbol, session): a duplicate, never a second observation
    records.append(_record(market, "S06", tp=106.0 * math.exp(d), price=106.0, instant=series.session_close(market, sessions[4]) + H,
                           published_at=series.session_close(market, sessions[4]) + D, source=SOURCE_V32, cycle_id="shadow-4-rerun", rerun_of="shadow-4-lost", source_version="9",
                           public_consensus_tp=106.0 * math.exp(0.1)))  # (4 + 6) even: sign +1, as its lost original
    if permute:
        records.reverse()
    assert database.insert_valuation_predictions(records) == len(records)
    vintage_at = series.session_close(market, last_target) + 6 * H
    _producer(database, bars).persist_run(market, start=sessions[0], end=last_target, symbols=symbols, now=vintage_at)
    return database, vintage_at + H, symbols, sessions


def test_the_decisory_horizon_end_to_end_tie_ratio_and_k_1_05() -> None:
    database, cut, symbols, sessions = _decisory_store()
    service = panel.PanelService(database, settings=_settings())
    receipt, detail = service.run(cut=cut, markets=("NASDAQ",), sources=("official_blend_v1", SOURCE_V32))
    official_cell, shadow_cell = receipt["payload"]["results"]["NASDAQ"]["official_blend_v1"], receipt["payload"]["results"]["NASDAQ"][SOURCE_V32]
    assert official_cell["records"] == {"read": 102, "admissible": 100, "refused": {"duplicate_session": 2}, "reruns": 0}
    # one observation per (source, symbol, session) whatever the version: the S05 re-run under version 9 duplicates its original (the smallest
    # published_at enters); the S06 re-run without its original is admissible, and counted
    assert shadow_cell["records"] == {"read": 101, "admissible": 100, "refused": {"duplicate_session": 1}, "reruns": 1}
    for cell in (official_cell, shadow_cell):
        assert cell["observations"] == {"n": 100, "names": 10, "sessions": 10, "max_share_single_name": 0.1, "basis": {"ok": 100}}
        decisory = cell["horizons"]["126"]
        assert decisory["diagnostic_only"] is False and decisory["eligible"] == 100 and decisory["ineligible"] == {}
        assert decisory["attrition"] == {"rate": pytest.approx(0.01), "unavailable": 1, "by_cause": {"missing_bar": 1}}
        assert decisory["common_mask"]["excluded"] == {"absent": 1, "consensus_after_prediction": 1, "consensus_currency_mismatch": 1}
        assert decisory["common_mask"]["names"] == 10 and decisory["common_mask"]["sessions"] == 10 and decisory["common_mask"]["n"] == 96
        assert decisory["band_coverage"] == {**decisory["band_coverage"], "n_null_bands": 1, "n_with_bands": 98, "within": 98, "fraction": 1.0}
        for horizon in ("21", "42", "63"):
            assert cell["horizons"][horizon]["diagnostic_only"] is True and cell["horizons"][horizon]["labelled"] == 100
        assert cell["consensus_declared_horizon"]["eligible"] == 0 and cell["consensus_declared_horizon"]["ineligible"] == {"not_yet_mature": 100}
        assert cell["vintage"]["status"] == "ok" and cell["last_closed_session"] == series.sessions_after("NASDAQ", sessions[-1], 126)[0].isoformat()  # type: ignore[union-attr]
        assert cell["cut_within_calendar_horizon"] is True
    # PROMO-2-ZERO: the official source and its consensus both predict the realized price exactly → TIE, counted as passed
    assert official_cell["horizons"]["126"]["source"]["mse"] == 0.0 and official_cell["horizons"]["126"]["consensus"]["mse"] == 0.0
    assert official_cell["decision"] == {**official_cell["decision"], "status": "TIE", "tie": True, "ratio": "N/D", "passes_k_1_00": True, "passes_k_1_05": True,
                                         "n": 96, "names": 10, "sessions": 10, "attrition": 0.01}
    assert official_cell["level_dispersion"]["7"]["sanity"]["status"] == "SANITY_OK" and official_cell["level_dispersion"]["7"]["median_level"] == 0.0
    assert official_cell["level_dispersion"]["7"]["consensus_excluded"] == {"absent": 1, "consensus_after_prediction": 1, "consensus_currency_mismatch": 1}
    # the inequality at k = 1.00 fails at ratio 1.03 and holds at k = 1.05; the errors are the log-errors of §2.6 in log²
    decided = shadow_cell["decision"]
    assert decided["status"] == "FAIL" and decided["ratio"] == pytest.approx(1.03) and not decided["passes_k_1_00"] and decided["passes_k_1_05"] and decided["tie"] is False
    assert decided["mse_source"] == pytest.approx(0.0103) and decided["mse_consensus"] == pytest.approx(0.01) and decided["n"] == 96 and decided["attrition"] == pytest.approx(0.01)
    assert shadow_cell["horizons"]["126"]["source"]["median_abs_log_error"] == pytest.approx(0.1 * math.sqrt(1.03))
    assert shadow_cell["horizons"]["126"]["consensus"]["median_abs_log_error"] == pytest.approx(0.1) and shadow_cell["horizons"]["126"]["source"]["n"] == 99
    # level and dispersion by profile: the record's source_version, or the caller's label
    assert set(shadow_cell["level_dispersion"]) == {"7", "9"} and shadow_cell["level_dispersion"]["7"]["n"] == 96 and shadow_cell["level_dispersion"]["9"]["n"] == 1
    assert shadow_cell["level_dispersion"]["7"]["sanity"]["status"] == "SANITY_OK" and abs(shadow_cell["level_dispersion"]["7"]["median_level"]) < 0.01
    relabelled, _ = panel.PanelService(database, settings=_settings()).run(cut=cut, markets=("NASDAQ",), sources=(SOURCE_V32,), profile_label="rev7")
    assert list(relabelled["payload"]["results"]["NASDAQ"][SOURCE_V32]["level_dispersion"]) == ["rev7"] and relabelled["payload"]["window"]["profile_label"] == "rev7"
    # the combination needs the three markets: one market is never a verdict
    assert receipt["payload"]["combination"][SOURCE_V32] == {**receipt["payload"]["combination"][SOURCE_V32], "status": "NOT_EVALUABLE", "markets_missing": ["B3", "NYSE"]}
    assert receipt["payload"]["combination"]["official_blend_v1"]["ties"] == ["NASDAQ"]
    # the detail carries the symbols and the arithmetic per (i, T): S08's constant split factor leaves the error unchanged; S09's last label is the missing bar
    s08 = [row for row in detail if row["symbol"] == "S08" and row["source"] == SOURCE_V32]
    assert len(s08) == 10 and all(row["adjustment"] == 0.5 and abs(row["horizons"]["126"]["e_source"]) == pytest.approx(0.1 * math.sqrt(1.03)) for row in s08)
    s09_last = next(row for row in detail if row["symbol"] == "S09" and row["session"] == sessions[-1].isoformat() and row["source"] == "official_blend_v1")
    assert s09_last["horizons"]["126"]["status"] == "missing_bar" and s09_last["horizons"]["63"]["status"] == "labelled"
    assert {row["symbol"] for row in detail} == set(symbols) and len(detail) == 200
    s05_session_3 = [row for row in detail if row["symbol"] == "S05" and row["session"] == sessions[3].isoformat() and row["source"] == SOURCE_V32]
    assert [(row["cycle_id"], row["source_version"], row["rerun_of"]) for row in s05_session_3] == [("shadow-3", "7", None)]  # the original, once
    s06_session_4 = [row for row in detail if row["symbol"] == "S06" and row["session"] == sessions[4].isoformat() and row["source"] == SOURCE_V32]
    assert [(row["cycle_id"], row["source_version"], row["rerun_of"]) for row in s06_session_4] == [("shadow-4-rerun", "9", "shadow-4-lost")]
    s03_first = next(row for row in detail if row["symbol"] == "S03" and row["session"] == sessions[0].isoformat() and row["source"] == "official_blend_v1")
    assert s03_first["consensus_status"] == "consensus_after_prediction" and s03_first["horizons"]["126"]["e_consensus"] is None and s03_first["horizons"]["126"]["e_source"] == 0.0
    # a window on prediction_instant narrows the cohort (PROMO-2 b) and the receipt says so
    windowed, _ = panel.PanelService(database, settings=_settings()).run(cut=cut, markets=("NASDAQ",), sources=("official_blend_v1",),
                                                                        since=series.session_close("NASDAQ", sessions[5]), until=cut)
    cell = windowed["payload"]["results"]["NASDAQ"]["official_blend_v1"]
    assert cell["records"]["read"] == 50 and cell["observations"]["sessions"] == 5 and cell["decision"]["status"] == "INSUFFICIENT" and cell["decision"]["reasons"] == ["sessions_below_min:5<10"]
    assert windowed["payload"]["window"]["since"] == series.session_close("NASDAQ", sessions[5]).isoformat()


def test_the_receipt_is_deterministic_under_permutation_and_carries_no_symbol() -> None:
    database, cut, symbols, _ = _decisory_store()
    receipt, detail = panel.PanelService(database, settings=_settings()).run(cut=cut, markets=("NASDAQ",), sources=("official_blend_v1", SOURCE_V32))
    payload_text = json.dumps(receipt["payload"], sort_keys=True)
    assert not any(symbol in payload_text for symbol in symbols) and "cycle_id" not in payload_text and "row_sha256" not in payload_text
    assert any(symbol in json.dumps(detail) for symbol in symbols) and all("symbol" in row for row in detail)
    assert receipt["payload_sha256"] == official.canonical_sha256(receipt["payload"]) and "built_at" not in payload_text
    # the same store, its rows permuted (the stores are lists in the double): the same hash
    random.Random(7).shuffle(database._valuation_predictions)
    random.Random(11).shuffle(database._price_bars)
    shuffled, _ = panel.PanelService(database, settings=_settings()).run(cut=cut, markets=("NASDAQ",), sources=("official_blend_v1", SOURCE_V32))
    assert shuffled["payload_sha256"] == receipt["payload_sha256"] and shuffled["payload"] == receipt["payload"]
    # a store built in the reverse order (the provider's answer and the inserts reversed): the same numbers, the same hash but for the vintage's ids
    reversed_database, reversed_cut, _, _ = _decisory_store(permute=True)
    assert reversed_cut == cut
    mirrored, _ = panel.PanelService(reversed_database, settings=_settings()).run(cut=cut, markets=("NASDAQ",), sources=("official_blend_v1", SOURCE_V32))
    for original_cell, mirrored_cell in zip(receipt["payload"]["results"]["NASDAQ"].values(), mirrored["payload"]["results"]["NASDAQ"].values()):
        assert {k: v for k, v in original_cell.items() if k != "vintage"} == {k: v for k, v in mirrored_cell.items() if k != "vintage"}
        assert original_cell["vintage"]["available_at"] == mirrored_cell["vintage"]["available_at"] and original_cell["vintage"]["window"] == mirrored_cell["vintage"]["window"]
    assert mirrored["payload"]["combination"] == receipt["payload"]["combination"]
    # the same store and cut, read twice: the same hash (a function of (cut, store), never of the wall clock)
    twice, _ = panel.PanelService(database, settings=_settings()).run(cut=cut, markets=("NASDAQ",), sources=("official_blend_v1", SOURCE_V32))
    assert twice["payload_sha256"] == receipt["payload_sha256"]


def test_resolve_label_reads_beyond_calendar_against_the_calendar_horizon() -> None:
    cut = datetime(2026, 9, 12, tzinfo=UTC)
    beyond = {"session": None, "status": "beyond_calendar"}
    # the calendar's last session closes at or after the cut: the target, later still, has not closed before C — not yet mature, deterministically
    assert panel.resolve_label(beyond, cut=cut, calendar_close=cut) == {"session": None, "status": "not_yet_mature"}
    assert panel.resolve_label(beyond, cut=cut, calendar_close=cut + D) == {"session": None, "status": "not_yet_mature"}
    # the cut is past the calendar (or there is none): the target may have matured — the calendar cannot say; beyond_calendar stays
    assert panel.resolve_label(beyond, cut=cut, calendar_close=cut - timedelta(microseconds=1)) == beyond
    assert panel.resolve_label(beyond, cut=cut, calendar_close=None) == beyond
    # every other answer passes untouched (a copy)
    for label in ({"session": "2026-10-05", "status": "not_yet_mature"}, {"session": None, "status": "not_a_session"}, {"session": "2026-10-05", "status": "missing_bar"},
                  {"session": "2026-10-05", "status": "labelled", "close": 1.0, "adjusted_close": 1.0, "bar_sha256": "b" * 64}):
        resolved = panel.resolve_label(label, cut=cut, calendar_close=cut)
        assert resolved == label and resolved is not label
    # the horizon is the close of the calendar's last session, the calendar label_bar reads; a session is one of that calendar
    for market in panel.MARKETS:
        horizon = panel.calendar_horizon(market)
        assert horizon is not None and horizon == series.session_close(market, series._calendar(market).last_session.date())
    assert panel.session_in_calendar("NASDAQ", date(2026, 9, 4)) and panel.session_in_calendar("B3", date(2026, 9, 4))
    assert not panel.session_in_calendar("NASDAQ", date(2026, 9, 5)) and not panel.session_in_calendar("B3", date(2026, 9, 7)) and panel.session_in_calendar("NASDAQ", date(2026, 9, 7)) is False
    assert not panel.session_in_calendar("XETRA", date(2026, 9, 4)) and not panel.session_in_calendar("NASDAQ", date(1900, 1, 2))  # unknown market; out of the calendar's bounds


def test_the_receipt_does_not_depend_on_the_calendar_bound_while_the_cut_is_within_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """``exchange_calendars`` builds a calendar to today + 1 year: a target session past that end is ``beyond_calendar`` today and a
    real session next year. The receipt must not change with the day it is built: a shorter calendar (the bound moved back) is
    the same receipt as long as the cut lies within it."""
    database, _ = _friday_store()
    cut = datetime(2026, 9, 12, tzinfo=UTC)  # h = 21 from 09-04 is 10-05, h = 126 is 2027-03-08: both after the cut, whatever the calendar's end
    with_default, _ = panel.PanelService(database, settings=_settings()).run(cut=cut, markets=("NASDAQ",))
    assert with_default["payload"]["results"]["NASDAQ"]["official_blend_v1"]["horizons"]["21"]["ineligible"] == {"not_yet_mature": 2}
    monkeypatch.setitem(series._calendars, "XNYS", xcals.get_calendar("XNYS", start="2026-01-02", end="2026-09-30"))  # the bound moved back: 10-05 is beyond it
    assert series.sessions_after("NASDAQ", T_FRIDAY, 21) == (None, "beyond_calendar") and panel.calendar_horizon("NASDAQ") == datetime(2026, 9, 30, 20, 0, tzinfo=UTC)
    with_short, detail = panel.PanelService(database, settings=_settings()).run(cut=cut, markets=("NASDAQ",))
    assert with_short["payload_sha256"] == with_default["payload_sha256"] and with_short["payload"] == with_default["payload"]
    assert with_short["payload"]["results"]["NASDAQ"]["official_blend_v1"]["cut_within_calendar_horizon"] is True
    assert _by_symbol(detail, "NASDAQ", "AAPL")["horizons"]["126"] == {**_by_symbol(detail, "NASDAQ", "AAPL")["horizons"]["126"], "status": "not_yet_mature", "session": None}
    # a cut PAST the calendar's end: the calendar cannot say whether 10-05 closed before it — beyond_calendar stays, ineligible, and the cell says the
    # receipt is not a function of (cut, store) alone (the default calendar resolves the session and reads the vintage: another receipt)
    past = datetime(2026, 10, 15, tzinfo=UTC)
    beyond, rows = panel.PanelService(database, settings=_settings()).run(cut=past, markets=("NASDAQ",))
    cell = beyond["payload"]["results"]["NASDAQ"]["official_blend_v1"]
    assert cell["cut_within_calendar_horizon"] is False and cell["horizons"]["21"]["ineligible"] == {"beyond_calendar": 2} and cell["horizons"]["21"]["eligible"] == 0
    assert _by_symbol(rows, "NASDAQ", "AAPL")["horizons"]["21"]["status"] == "beyond_calendar" and cell["decision"]["reasons"] == ["no_eligible_observations"]
    monkeypatch.delitem(series._calendars, "XNYS")
    resolved, _ = panel.PanelService(database, settings=_settings()).run(cut=past, markets=("NASDAQ",))
    cell = resolved["payload"]["results"]["NASDAQ"]["official_blend_v1"]
    assert cell["cut_within_calendar_horizon"] is True and cell["horizons"]["21"]["eligible"] == 2 and cell["horizons"]["21"]["attrition"]["by_cause"] == {"outside_window": 2}
    assert resolved["payload_sha256"] != beyond["payload_sha256"]


# ------------------------------------------------------------------ the reader
def test_the_window_reader_filters_in_memory_and_pins_its_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    database = Database(_settings())
    friday, tuesday = datetime(2026, 9, 4, 22, 0, tzinfo=UTC), datetime(2026, 9, 8, 22, 0, tzinfo=UTC)
    records = [
        _record("NASDAQ", "MSFT", tp=400.0, price=380.0, instant=friday, cycle_id="m1"),
        _record("NASDAQ", "AAPL", tp=250.0, price=230.0, instant=friday, cycle_id="a1"),
        _record("NASDAQ", "AAPL", tp=251.0, price=230.0, instant=tuesday, cycle_id="a2"),
        _record("NASDAQ", "AAPL", tp=252.0, price=230.0, instant=friday, published_at=tuesday, cycle_id="a1-rerun", rerun_of="a1"),
        _record("NASDAQ", "AAPL", tp=253.0, price=230.0, instant=friday, cycle_id="a1-shadow", source=SOURCE_V32),
        _record("NYSE", "KO", tp=70.0, price=65.0, instant=friday, cycle_id="k1"),
    ]
    assert database.insert_valuation_predictions(records) == 6
    everything = database.list_valuation_predictions_in_window("NASDAQ", source=official.SOURCE_OFFICIAL)
    assert [r["cycle_id"] for r in everything] == ["a2", "a1-rerun", "a1", "m1"]  # by symbol, then newest first (_PREDICTION_ORDER: a re-run follows its original)
    assert all(r["source"] == official.SOURCE_OFFICIAL and r["market"] == "NASDAQ" for r in everything)
    assert [r["cycle_id"] for r in database.list_valuation_predictions_in_window("NASDAQ", source=SOURCE_V32)] == ["a1-shadow"]
    assert [r["cycle_id"] for r in database.list_valuation_predictions_in_window("NASDAQ", source=official.SOURCE_OFFICIAL, since=friday, until=tuesday)] == ["a1-rerun", "a1", "m1"]
    assert [r["cycle_id"] for r in database.list_valuation_predictions_in_window("NASDAQ", source=official.SOURCE_OFFICIAL, since=tuesday)] == ["a2"]
    assert [r["cycle_id"] for r in database.list_valuation_predictions_in_window("NASDAQ", source=official.SOURCE_OFFICIAL, until=friday)] == []
    assert database.list_valuation_predictions_in_window("B3", source=official.SOURCE_OFFICIAL) == []
    copy_of = database.list_valuation_predictions_in_window("NYSE", source=official.SOURCE_OFFICIAL)[0]
    copy_of["tp"] = 1.0
    assert database.list_valuation_predictions_in_window("NYSE", source=official.SOURCE_OFFICIAL)[0]["tp"] == 70.0  # copies, never the store's dicts
    # the SQL text (a recording connection: no database is reached): the same column tuple, a window, the shared order, no LIMIT
    pg = Database(Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False, database_url="postgresql://configured"))
    queries: list[tuple[str, Any]] = []

    class Recording:
        def execute(self, query: str, params: Any = None) -> "Recording":
            queries.append((" ".join(query.split()), params))
            return self

        def fetchall(self) -> list[Any]:
            return []

    @contextmanager
    def fake_connection() -> Any:
        yield Recording()

    monkeypatch.setattr(pg, "connection", fake_connection)
    assert pg.list_valuation_predictions_in_window("NASDAQ", source=official.SOURCE_OFFICIAL, since=friday, until=tuesday) == []
    assert pg.list_valuation_predictions_in_window("B3", source=SOURCE_V32) == []
    assert len(queries) == 2
    text, params = queries[0]
    assert text.startswith("SELECT id::text, source, source_version, market, symbol, scope, session_date::text, cycle_id::text, prediction_instant, published_at, tp, buy_in, "
                           "internal_tp, consensus_tp, consensus_source, analyst_count, consensus_weight_percent, price, currency, decomposition, row_sha256 FROM valuation_predictions")
    assert ("WHERE market = %s AND source = %s AND (%s::timestamptz IS NULL OR prediction_instant >= %s) AND (%s::timestamptz IS NULL OR prediction_instant < %s) "
            "ORDER BY symbol, prediction_instant DESC, published_at DESC NULLS LAST, created_at DESC") in text
    assert "LIMIT" not in text and params == ("NASDAQ", official.SOURCE_OFFICIAL, friday, friday, tuesday, tuesday)
    assert queries[1][1] == ("B3", SOURCE_V32, None, None, None, None)


# ------------------------------------------------------------------ the CLI
def test_the_cli_prints_the_receipt_without_symbols_refuses_naive_clocks_and_writes_the_detail_privately(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
                                                                                                            tmp_path: Path) -> None:
    database, _ = _friday_store()
    monkeypatch.setattr(panel, "get_settings", _settings)
    monkeypatch.setattr(panel, "Database", lambda settings: database)
    assert panel.main(["--as-of", "2026-09-12T00:00:00+00:00", "--markets", "NASDAQ,B3"]) == 0
    out = capsys.readouterr().out
    receipt = json.loads(out)
    assert receipt["schema"] == panel.SCHEMA_VERSION and receipt["payload_sha256"] == official.canonical_sha256(receipt["payload"])
    assert not any(symbol in out for symbol in ("AAPL", "MSFT", "PETR4")) and receipt["payload"]["markets"] == ["NASDAQ", "B3"] and receipt["payload"]["sources"] == ["official_blend_v1"]
    nasdaq = receipt["payload"]["results"]["NASDAQ"]["official_blend_v1"]
    assert nasdaq["horizons"]["126"]["ineligible"] == {"not_yet_mature": 2} and nasdaq["decision"]["status"] == "UNMEASURED" and nasdaq["decision"]["reasons"] == ["no_eligible_observations"]
    assert receipt["payload"]["combination"]["official_blend_v1"]["status"] == "NOT_EVALUABLE" and receipt["payload"]["protocol"] == panel.protocol()
    assert receipt["payload"]["cut"] == "2026-09-12T00:00:00+00:00" and receipt["payload"]["window"] == {"since": None, "until": None, "profile_label": None}
    # the cut in another zone is the same instant; --since/--until/--profile-label travel into the receipt
    assert panel.main(["--as-of", "2026-09-11T21:00:00-03:00", "--markets", "b3", "--since", "2026-09-01T00:00:00+00:00", "--until", "2026-09-10T00:00:00+00:00",
                       "--profile-label", "rev7", "--sources", "official_blend_v1,v3_2_shadow"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["payload"]["cut"] == "2026-09-12T00:00:00+00:00" and receipt["payload"]["window"] == {"since": "2026-09-01T00:00:00+00:00", "until": "2026-09-10T00:00:00+00:00",
                                                                                                           "profile_label": "rev7"}
    assert receipt["payload"]["markets"] == ["B3"] and receipt["payload"]["sources"] == ["official_blend_v1", "v3_2_shadow"]
    assert list(receipt["payload"]["results"]["B3"]["official_blend_v1"]["level_dispersion"]) == ["rev7"]
    # a naive --as-of, a bad market, an empty source list, a window that does not precede: refused by the parser, nothing printed
    for arguments in (["--as-of", "2026-09-12T00:00:00"], ["--as-of", "soon"], ["--as-of", "2026-09-12T00:00:00+00:00", "--markets", "XETRA"],
                      ["--as-of", "2026-09-12T00:00:00+00:00", "--sources", " , "], ["--as-of", "2026-09-12T00:00:00+00:00", "--since", "2026-09-02"],
                      ["--as-of", "2026-09-12T00:00:00+00:00", "--since", "2026-09-02T00:00:00+00:00", "--until", "2026-09-01T00:00:00+00:00"], []):
        with pytest.raises(SystemExit) as refused:
            panel.main(arguments)
        assert refused.value.code == 2 and capsys.readouterr().out == ""
    # --detail: a new path only, 0600, the symbols inside it and the receipt's hash; an existing path (or a symlink) is refused before anything runs
    detail_path = tmp_path / "detail.json"
    assert panel.main(["--as-of", "2026-09-12T00:00:00+00:00", "--markets", "NASDAQ", "--detail", str(detail_path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert stat.S_IMODE(detail_path.stat().st_mode) == 0o600
    detail = json.loads(detail_path.read_text())
    assert detail["schema"] == f"{panel.SCHEMA_VERSION}:detail" and detail["payload_sha256"] == printed["payload_sha256"] and detail["cut"] == printed["payload"]["cut"]
    assert {row["symbol"] for row in detail["rows"]} == {"AAPL", "MSFT"} and all(row["market"] == "NASDAQ" for row in detail["rows"])
    before = detail_path.read_bytes()
    with pytest.raises(SystemExit) as refused:
        panel.main(["--as-of", "2026-09-12T00:00:00+00:00", "--markets", "NASDAQ", "--detail", str(detail_path)])
    assert refused.value.code == 2 and capsys.readouterr().out == "" and detail_path.read_bytes() == before
    link = tmp_path / "link.json"
    link.symlink_to(tmp_path / "nowhere.json")
    with pytest.raises(SystemExit):
        panel.main(["--as-of", "2026-09-12T00:00:00+00:00", "--markets", "NASDAQ", "--detail", str(link)])
    assert not (tmp_path / "nowhere.json").exists() and capsys.readouterr().out == ""
