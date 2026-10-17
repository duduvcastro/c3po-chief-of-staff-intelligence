"""PREREG_VALUATION_DECISOR_V1 — the read-only realized-accuracy report: the metric math pinned on synthetic numbers
(ranks, deciles, Student t, batch means with the overlap inflation, Newey–West, the pro-rated log-errors, the verdict
order), and the service pinned on the in-memory double with synthetic records and synthetic bars (never the network,
never a real database, never a writer), the CLI by its stdout."""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app import valuation_accuracy_report as report
from app import valuation_official as official
from app import valuation_panel as panel
from app import valuation_price_history as series
from app.config import Settings
from app.database import Database
from app.market_data.eodhd import EodhdClient

UTC = timezone.utc
H = timedelta(hours=1)


# ------------------------------------------------------------------ pure statistics
def test_student_t_tail_matches_tabulated_quantiles() -> None:
    # two-sided 5 % critical values: df=1 12.706, df=3 3.182, df=4 2.776, df=11 2.201; normal 1.960
    for t, df in ((12.706204736174707, 1), (3.182446305284263, 3), (2.7764451051977987, 4), (2.200985160082949, 11)):
        assert report.student_t_sf(t, df) == pytest.approx(0.025, abs=1e-9)
        assert report.student_t_sf(-t, df) == pytest.approx(0.975, abs=1e-9)
    assert report.student_t_sf(1.959963984540054, 1e8) == pytest.approx(0.025, abs=1e-6)
    assert report.student_t_sf(0.0, 4) == 0.5
    assert report.student_t_sf(7.173182219782511, 4) == pytest.approx(0.001, abs=1e-9)  # the interim alpha at df = 4
    with pytest.raises(ValueError):
        report.student_t_sf(1.0, 0)


def test_spearman_uses_average_ranks_and_refuses_degenerate_sessions() -> None:
    assert report.average_ranks([10.0, 30.0, 20.0, 20.0]) == [1.0, 4.0, 2.5, 2.5]
    assert report.spearman([1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 35.0, 40.0]) == 1.0
    assert report.spearman([1.0, 2.0, 3.0, 4.0], [4.0, 3.0, 2.0, 1.0]) == -1.0
    assert report.spearman([1.0, 1.0, 2.0, 3.0], [1.0, 2.0, 3.0, 4.0]) == pytest.approx(0.9486832980505138)  # Pearson on ranks (1.5, 1.5, 3, 4)
    assert report.spearman([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None  # no variance of upside: the session is degenerate, never 0
    assert report.spearman([1.0], [1.0]) is None


def test_decile_spread_is_top_minus_bottom_and_ties_share_a_decile() -> None:
    upsides = [float(k) for k in range(30)]
    assert report.decile_spread(upsides, upsides) == 27.0  # (27 + 28 + 29) / 3 − (0 + 1 + 2) / 3
    assert [report.decile_of(rank, 30) for rank in (1.0, 3.0, 4.0, 27.0, 28.0, 30.0)] == [0, 0, 1, 8, 9, 9]
    tied = [0.0] * 4 + [float(k) for k in range(1, 27)]  # four names tied at the bottom: average rank 2.5 → all four in decile 0
    returns = [1.0] * 4 + [0.0] * 26
    assert report.decile_of(2.5, 30) == 0 and report.decile_of(5.0, 30) == 1
    assert report.decile_spread(tied, returns) == -1.0  # top (ranks 28–30) earns 0, the four tied bottom names earn 1 each


def test_decile_spread_with_every_name_tied_has_no_top_and_bottom() -> None:
    assert report.decile_spread([1.0] * 30, [float(k) for k in range(30)]) is None


def test_block_statistics_counts_complete_blocks_only_and_inflates_for_the_overlap() -> None:
    # blocks of 3: block means 1.0, 2.0, 4.0 (complete), block 3 pending (its last session 11 is beyond mature_through 9)
    points = [(0, 1.0), (1, 1.0), (2, 1.0), (3, 2.0), (4, 2.0), (5, 2.0), (6, 3.0), (7, 4.0), (8, 5.0), (9, 9.0), (10, 9.0)]
    stats = report.block_statistics(points, block_length=3, mature_through=9)
    assert stats["blocks"] == 3 and stats["blocks_pending"] == 1 and stats["blocks_empty"] == 0 and stats["sessions"] == 9 and stats["df"] == 2
    means = [1.0, 2.0, 4.0]
    center = sum(means) / 3
    sd = math.sqrt(sum((m - center) ** 2 for m in means) / 2)
    se = math.sqrt(1.5) * sd / math.sqrt(3)
    assert stats["estimate"] == pytest.approx(center) and stats["se"] == pytest.approx(se) and stats["t"] == pytest.approx(center / se)
    assert stats["p_greater"] == pytest.approx(report.student_t_sf(center / se, 2)) and stats["p_less"] == pytest.approx(1 - stats["p_greater"])
    assert stats["mean_per_session"] == pytest.approx(sum(value for _i, value in points) / len(points))  # every measured session, pending included
    assert stats["newey_west"]["n"] == 9 and stats["newey_west"]["lag"] == 3
    # a complete block without any value is empty, not counted; a partition cap completes the truncated last block
    gap = report.block_statistics([(0, 1.0), (7, 3.0)], block_length=3, mature_through=8)
    assert gap["blocks"] == 2 and gap["blocks_empty"] == 1 and gap["se"] == pytest.approx(math.sqrt(1.5) * math.sqrt(2.0) / math.sqrt(2))
    capped = report.block_statistics([(0, 1.0), (3, 2.0), (4, 3.0)], block_length=3, mature_through=4, partition_last=4)
    assert capped["blocks"] == 2 and capped["blocks_pending"] == 0  # block 1 ends at the partition's last session (4), matured
    uncapped = report.block_statistics([(0, 1.0), (3, 2.0), (4, 3.0)], block_length=3, mature_through=4)
    assert uncapped["blocks"] == 1 and uncapped["blocks_pending"] == 1 and uncapped["se"] is None and uncapped["t"] is None
    nothing = report.block_statistics([(0, 1.0)], block_length=3, mature_through=None)
    assert nothing["blocks"] == 0 and nothing["estimate"] is None and nothing["mean_per_session"] == 1.0
    constant = report.block_statistics([(0, 0.5), (3, 0.5)], block_length=3, mature_through=5)
    assert constant["se"] == 0.0 and constant["t"] is None and constant["p_greater"] is None  # no dispersion: no test, never an infinite t
    with pytest.raises(ValueError):
        report.block_statistics([(-1, 1.0)], block_length=3, mature_through=5)


def test_newey_west_is_the_bartlett_hac_of_the_mean() -> None:
    values = [1.0, 3.0, 2.0, 5.0, 4.0]
    n, mean = 5, 3.0
    deviations = [v - mean for v in values]
    gamma0 = sum(d * d for d in deviations) / n
    gamma1 = sum(deviations[t] * deviations[t - 1] for t in range(1, n)) / n
    se = math.sqrt((gamma0 + 2 * 0.5 * gamma1) / n)
    result = report.newey_west(values, 1)
    assert result["se"] == pytest.approx(se) and result["t"] == pytest.approx(mean / se) and result["mean"] == 3.0
    assert report.newey_west(values, 4)["se"] is None  # not longer than lag + 1


def _row(*, tp: float, price: float, adjustment: float, close: float, realized: dict[int, float], consensus_tp: float | None = None,
         consensus_status: str | None = None, horizon_text: str = "12m", status: str | None = None) -> dict[str, Any]:
    consensus_status = consensus_status or ("present" if consensus_tp is not None else "absent")  # the panel's status: present implies a tp
    horizons = {str(h): {"status": "labelled", "eligible": True, "realized": value, "e_source": 0.0} for h, value in realized.items()}
    return {"symbol": "X", "session": "2026-03-02", "tp": tp, "price": price, "adjustment": adjustment, "close_at_session": close,
            "consensus": {"tp": consensus_tp, "horizon": horizon_text}, "consensus_status": consensus_status, "producer_status": status, "horizons": horizons}


def test_point_pro_rates_the_twelve_month_tp_and_measures_both_returns() -> None:
    row = _row(tp=120.0, price=100.0, adjustment=0.5, close=100.0, realized={1: 51.0, 21: 55.0, 22: 56.1}, consensus_tp=110.0, status="full_match")
    item = report.point(row, 21)
    assert item is not None
    assert item["upside"] == pytest.approx(0.2) and item["return"] == pytest.approx(55.0 / 50.0 - 1) and item["return_executable"] == pytest.approx(56.1 / 51.0 - 1)
    rw = math.log(100.0 * 0.5) - math.log(55.0)
    assert item["e_random_walk"] == pytest.approx(rw)
    assert item["e_model"] == pytest.approx(math.log(100.0 * (1.2 ** (21 / 252)) * 0.5) - math.log(55.0))
    assert item["e_consensus"] == pytest.approx(math.log(100.0 * (1.1 ** (21 / 252)) * 0.5) - math.log(55.0)) and item["listed"] is True
    at_252 = report.point(_row(tp=120.0, price=100.0, adjustment=1.0, close=100.0, realized={252: 110.0}), 252)
    assert at_252 is not None and at_252["e_model"] == pytest.approx(panel.log_error(120.0, 1.0, 110.0))  # at 252 sessions the panel's §2.6 error
    assert at_252["return_executable"] is None and at_252["listed"] is False
    same = report.point(_row(tp=100.0, price=100.0, adjustment=1.0, close=100.0, realized={21: 90.0}), 21)
    assert same is not None and same["e_model"] == same["e_random_walk"]  # tp = price IS the random walk
    other_horizon = report.point(_row(tp=120.0, price=100.0, adjustment=1.0, close=100.0, realized={21: 90.0}, consensus_tp=110.0, horizon_text="6m"), 21)
    assert other_horizon is not None and other_horizon["e_consensus"] is None and other_horizon["consensus_cause"] == "consensus_horizon_not_12m"
    absent = report.point(_row(tp=120.0, price=100.0, adjustment=1.0, close=100.0, realized={21: 90.0}, consensus_status="absent"), 21)
    assert absent is not None and absent["e_consensus"] is None and absent["consensus_cause"] == "absent"
    unlabelled = _row(tp=120.0, price=100.0, adjustment=1.0, close=100.0, realized={21: 90.0})
    unlabelled["horizons"]["21"]["e_source"] = None
    assert report.point(unlabelled, 21) is None


def _blocks(estimate: float | None, *, blocks: int, p_greater: float | None = None, p_less: float | None = None) -> dict[str, Any]:
    return {"blocks": blocks, "estimate": estimate, "p_greater": p_greater, "p_less": p_less}


def _metrics(*, ic: dict[str, Any], rate: float | None = 0.0, spread: float | None = 0.01, executable: float | None = 0.03) -> dict[str, Any]:
    return {"attrition": {"rate": rate}, "ic": {"blocks": ic}, "decile_spread": {"blocks": _blocks(spread, blocks=ic["blocks"])},
            "ic_executable": {"blocks": _blocks(executable, blocks=ic["blocks"])}}


def test_verdict_follows_the_pre_registered_order() -> None:
    quiet = _metrics(ic=_blocks(None, blocks=0))
    passing = _metrics(ic=_blocks(0.05, blocks=6, p_greater=0.0005, p_less=0.9995))
    assert report.verdict({"21": _metrics(ic=_blocks(None, blocks=0), rate=None), "63": quiet})["reasons"] == ["no_eligible_observations"]
    unmeasured = report.verdict({"21": {**passing, "attrition": {"rate": 0.2}}, "63": quiet})
    assert unmeasured["status"] == "UNMEASURED" and unmeasured["reasons"] == ["attrition_above_cap:0.2000>0.1"]
    # HARM at ANY horizon with enough blocks — before INSUFFICIENT and before any pass
    harm = report.verdict({"21": passing, "63": _metrics(ic=_blocks(-0.04, blocks=5, p_greater=0.99, p_less=0.01))})
    assert harm["status"] == "HARM" and harm["reasons"] == ["ic_negative:h63:p_less=0.010000"]
    thin_harm = report.verdict({"21": passing, "63": _metrics(ic=_blocks(-0.04, blocks=4, p_greater=0.999, p_less=0.001))})
    assert thin_harm["status"] == "SIGNAL_PASS"  # four blocks are not enough for a harm verdict either
    unmeasured_harm = report.verdict({"21": passing, "63": _metrics(ic=_blocks(-0.04, blocks=5, p_greater=0.99, p_less=0.01), rate=0.5)})
    assert unmeasured_harm["status"] == "SIGNAL_PASS"  # a horizon whose attrition is above the cap is not measured: no harm read from it
    insufficient = report.verdict({"21": _metrics(ic=_blocks(0.05, blocks=4, p_greater=0.0001, p_less=0.9999)), "63": quiet})
    assert insufficient["status"] == "INSUFFICIENT" and insufficient["reasons"] == ["blocks_below_min:4<5"]
    interim = report.verdict({"21": passing, "63": quiet})
    assert interim == {**interim, "status": "SIGNAL_PASS", "look": "INTERIM", "alpha": 0.001, "reasons": [], "buy_list_decisory": False, "gate": False}
    not_yet = report.verdict({"21": _metrics(ic=_blocks(0.05, blocks=6, p_greater=0.01, p_less=0.99)), "63": quiet})
    assert not_yet["status"] == "CONTINUE" and not_yet["reasons"] == ["ic_not_significant:p_greater=0.01>0.001"]
    final = report.verdict({"21": _metrics(ic=_blocks(0.05, blocks=12, p_greater=0.01, p_less=0.99)), "63": quiet})
    assert final["status"] == "SIGNAL_PASS" and final["look"] == "FINAL" and final["alpha"] == 0.025
    small = report.verdict({"21": _metrics(ic=_blocks(0.015, blocks=12, p_greater=0.001, p_less=0.999)), "63": quiet})
    assert small["status"] == "INCONCLUSIVE" and small["reasons"] == ["ic_below_min:0.015<0.02"]
    conditions = report.verdict({"21": _metrics(ic=_blocks(0.05, blocks=12, p_greater=0.001, p_less=0.999), spread=None, executable=-0.01), "63": quiet})
    assert conditions["status"] == "INCONCLUSIVE" and conditions["reasons"] == ["decile_spread_unmeasured", "ic_executable_not_positive"]
    deadline = report.verdict({"21": _metrics(ic=_blocks(0.05, blocks=6, p_greater=0.01, p_less=0.99)), "63": quiet}, final_by_deadline=True)
    assert deadline["status"] == "SIGNAL_PASS" and deadline["look"] == "FINAL" and deadline["alpha"] == 0.025  # the deadline makes the look final whatever B
    late = report.verdict({"21": _metrics(ic=_blocks(0.05, blocks=3, p_greater=0.01, p_less=0.99)), "63": quiet}, final_by_deadline=True)
    assert late["status"] == "INCONCLUSIVE" and late["reasons"] == ["blocks_below_min:3<5", "final_deadline"]
    flat = report.verdict({"21": _metrics(ic=_blocks(0.05, blocks=6, p_greater=0.0001, p_less=0.9999), spread=0.0), "63": quiet})
    assert flat["status"] == "CONTINUE" and flat["reasons"] == ["decile_spread_not_positive"]


def test_the_session_is_forced_read_only_and_the_store_exposes_readers_only() -> None:
    env: dict[str, str] = {}
    assert report.force_read_only_session(env) == "-c default_transaction_read_only=on"
    env = {"PGOPTIONS": "-c default_transaction_read_only=on -c default_transaction_read_only=off"}
    assert report.force_read_only_session(env) == "-c default_transaction_read_only=off -c default_transaction_read_only=on"  # last wins: ours
    store = report.ReadOnlyStore(Database(_settings()))
    assert callable(store.list_valuation_predictions_in_window) and callable(store.price_bars)
    for writer in ("insert_valuation_predictions", "persist_price_history_run", "initialize", "connection"):
        with pytest.raises(AttributeError, match="read-only"):
            getattr(store, writer)


def test_the_protocol_is_the_prereg() -> None:
    constants = report.protocol()
    assert constants["horizons_sessions"] == [21, 63, 126] and constants["primary_horizon"] == 21 and constants["tp_horizon_sessions"] == 252
    assert constants["min_blocks"] == 5 and constants["final_blocks"] == 12 and constants["final_deadline"] == "2027-12-31" and constants["adjacent_block_variance_factor"] == 1.5
    assert (constants["alpha_interim"], constants["alpha_final"], constants["alpha_harm"], constants["ic_min"]) == (0.001, 0.025, 0.025, 0.02)
    assert constants["market_groups"] == {"B3": ["B3"], "US": ["NASDAQ", "NYSE"]} and constants["buy_list_decisory"] is False and constants["gate"] is False
    assert report.label_horizons() == (1, 21, 22, 63, 64, 126, 127)
    doc = Path(__file__).resolve().parents[2] / "docs" / "PREREG_VALUATION_DECISOR_V1.md"
    text = doc.read_text(encoding="utf-8")
    for needle in ("h = 21", "MIN_BLOCKS = 5", "FINAL_BLOCKS = 12", "1,5", "0,001", "0,025", "IC_MIN = 0,02", "252", "VALUATION-ACCURACY-REPORT-v1"):
        assert needle in text, needle


# ------------------------------------------------------------------ the service on the in-memory double
class ScriptedHttp:
    def __init__(self, bars_by_symbol: dict[str, list[dict]]) -> None:
        self.bars_by_symbol = bars_by_symbol

    def get_json(self, url: str, *, params=None, headers=None):
        return self.bars_by_symbol.get(url.rsplit("/", 1)[-1], [])


def _settings() -> Settings:
    return Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False)


def _producer(database: Database, bars_by_symbol: dict[str, list[dict]]) -> series.PriceHistoryService:
    http = ScriptedHttp(bars_by_symbol)
    return series.PriceHistoryService(_settings(), database, http, eodhd=EodhdClient("https://eodhd.com", "secret", http))  # type: ignore[arg-type]


def _record(market: str, symbol: str, *, tp: float, price: float, instant: datetime, source: str, status: str, scope: str = "universe",
            published_at: datetime | None = None, cycle: str = "c") -> dict:
    row = {"symbol": symbol, "our_tp": tp, "buy_in": price * 0.9, "internal_tp": tp, "internal_buy_in": price * 0.9, "price": price,
           "public_consensus_tp": tp * 1.1, "analyst_count": 10, "consensus_weight_percent": 25.0, "consensus_origin_source": "brapi",
           "consensus_published_at": instant - H, "valuation_confidence": 70.0, "status": status, "signal_quality": "validated"}
    record = official.prediction_from_row(row, market=market, scope=scope, cycle_id=f"{cycle}-{market}-{symbol}-{instant.isoformat()}", source_version="7",
                                          prediction_instant=instant, published_at=published_at, source=source)
    assert record is not None
    return record


US_NAMES = [("NASDAQ", f"S{k:02d}") for k in range(6)] + [("NYSE", f"S{k:02d}") for k in range(6, 12)]


def _store(*, permute: bool = False) -> tuple[Database, datetime, list[date], dict[str, float]]:
    """US: twelve names (six NASDAQ, six NYSE) × eight consecutive XNYS sessions from 2026-03-02. Name k grows at
    ``g_k = 0.001·k`` per session and its TP is ``close(T)·(1 + u_k)`` with ``u_k = 0.05·k − 0.2``: upside and return
    are both increasing in k, so every session's IC is +1 (executable too). S08 trades at an adjusted close half its
    close (a(T) = 0.5). Names 9–11 are ``full_match`` (the buy-list proxy). Plus: a targeted record (outside the
    universe), a re-run published months later (retrospective), three B3 names (below the per-session minimum). Both
    official sources; one vintage per market published after the last target closed."""
    database = Database(_settings())
    sessions = [d for d in (series.sessions_after("NASDAQ", date(2026, 3, 2), j)[0] for j in range(8)) if d is not None]
    last_target = series.sessions_after("NASDAQ", sessions[-1], 3)[0]
    assert last_target is not None
    calendar = [stamp.date() for stamp in series._calendar("NASDAQ").sessions_in_range(sessions[0].isoformat(), last_target.isoformat())]
    growth = {symbol: 0.001 * k for k, (_m, symbol) in enumerate(US_NAMES)}
    upside = {symbol: 0.05 * k - 0.2 for k, (_m, symbol) in enumerate(US_NAMES)}

    def close(symbol: str, day: date) -> float:
        return round(100.0 * (1 + growth[symbol]) ** calendar.index(day), 6)

    bars = {f"{symbol}.US": [{"date": day.isoformat(), "close": close(symbol, day), "adjusted_close": close(symbol, day) / (2 if symbol == "S08" else 1),
                              "volume": 1000.0} for day in calendar] for _m, symbol in US_NAMES}
    b3_sessions = [d for d in (series.sessions_after("B3", date(2026, 3, 2), j)[0] for j in range(8)) if d is not None]
    b3_last = series.sessions_after("B3", b3_sessions[-1], 3)[0]
    assert b3_last is not None
    b3_calendar = [stamp.date() for stamp in series._calendar("B3").sessions_in_range(b3_sessions[0].isoformat(), b3_last.isoformat())]
    b3_bars = {f"P{k:02d}.SA": [{"date": day.isoformat(), "close": 10.0 + k, "adjusted_close": 10.0 + k, "volume": 1.0} for day in b3_calendar] for k in range(3)}
    records: list[dict] = []
    for source in report.DEFAULT_SOURCES:
        for session in sessions:
            instant = series.session_close("NASDAQ", session) + H
            for market, symbol in US_NAMES:
                price = close(symbol, session)
                status = "full_match" if int(symbol[1:]) >= 9 else "watchlist"
                records.append(_record(market, symbol, tp=price * (1 + upside[symbol]), price=price, instant=instant, source=source, status=status))
            records.append(_record("NASDAQ", "T99", tp=200.0, price=100.0, instant=instant, source=source, status="full_match", scope="targeted"))
        for session in b3_sessions:
            instant = series.session_close("B3", session) + H
            for k in range(3):
                records.append(_record("B3", f"P{k:02d}", tp=12.0 + k, price=10.0 + k, instant=instant, source=source, status="watchlist"))
        late = series.session_close("NASDAQ", sessions[0]) + H
        records.append(_record("NYSE", "R50", tp=150.0, price=100.0, instant=late, source=source, status="full_match", published_at=late + timedelta(days=2), cycle="rerun"))  # after the live deadline, before the cut
    if permute:
        records.reverse()
    assert database.insert_valuation_predictions(records) == len(records)
    vintage_at = series.session_close("NASDAQ", last_target) + 6 * H
    _producer(database, bars).persist_run("NASDAQ", start=sessions[0], end=last_target, symbols=[s for m, s in US_NAMES if m == "NASDAQ"], now=vintage_at)
    _producer(database, bars).persist_run("NYSE", start=sessions[0], end=last_target, symbols=[s for m, s in US_NAMES if m == "NYSE"], now=vintage_at + timedelta(minutes=1))
    _producer(database, b3_bars).persist_run("B3", start=b3_sessions[0], end=b3_last, symbols=["P00", "P01", "P02"], now=vintage_at + timedelta(minutes=2))
    return database, vintage_at + H, sessions, growth


def _small_horizons(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report, "HORIZONS", (2,))
    monkeypatch.setattr(report, "PRIMARY_HORIZON", 2)


def test_the_service_measures_ic_spread_mse_and_the_buy_list_on_the_live_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_horizons(monkeypatch)
    database, cut, sessions, growth = _store()
    service = report.AccuracyReportService(report.ReadOnlyStore(database), settings=_settings())  # type: ignore[arg-type]
    receipt = service.report(cut=cut, holdout_start=sessions[4])
    payload = receipt["payload"]
    assert receipt["payload_sha256"] == official.canonical_sha256(payload) and payload["protocol"] == report.protocol()
    assert payload["holdout_start"] == sessions[4].isoformat() and payload["sources"] == list(report.DEFAULT_SOURCES) and payload["market_groups"] == ["B3", "US"]
    text = json.dumps(receipt)
    assert not any(symbol in text for symbol in ("S00", "S08", "S11", "T99", "R50", "P00"))  # aggregates only
    assert service.http is not None and service.http.calls == 0  # never the network
    us = payload["results"]["US"]["official_blend_v1"]
    # 12 names × 8 sessions + 8 targeted + 1 re-run read across NASDAQ and NYSE; the re-run is retrospective, the targeted outside the universe
    assert us["records"]["read"] == 105 and us["records"]["admissible"] == 105 and us["records"]["refused"] == {}
    assert us["records"]["cohort"] == {"live": 104, "retrospective": 1} and us["records"]["scope_live"] == {"targeted": 8, "universe": 96}
    assert us["records"]["source_versions_live_universe"] == {"7": 96} and set(us["vintages"]) == {"NASDAQ", "NYSE"}
    development, holdout = us["partitions"]["development"], us["partitions"]["holdout"]
    assert development["anchor"] == sessions[0].isoformat() and development["sessions"] == 4 and development["observations"] == 48 and development["partition_last_index"] == 3
    assert holdout["anchor"] == sessions[4].isoformat() and holdout["sessions"] == 4 and holdout["observations"] == 48 and holdout["partition_last_index"] is None
    for partition in (development, holdout):
        cell = partition["horizons"]["2"]
        assert cell["eligible"] == 48 and cell["labelled"] == 48 and cell["attrition"] == {"rate": 0.0, "unavailable": 0, "by_cause": {}}
        assert cell["observations"] == {"n": 48, "names": 12, "sessions": 4, "max_share_single_name": pytest.approx(1 / 12)}
        assert cell["ic"]["sessions_measured"] == 4 and cell["ic"]["blocks"]["mean_per_session"] == 1.0 and cell["ic"]["blocks"]["blocks"] == 2
        assert cell["ic"]["blocks"]["se"] == 0.0 and cell["ic"]["blocks"]["t"] is None  # +1 every session: no dispersion, no test
        assert cell["ic_executable"]["blocks"]["mean_per_session"] == 1.0 and cell["ic_executable"]["labelled_without_executable_return"] == 0
        assert cell["decile_spread"]["sessions_measured"] == 0 and cell["decile_spread"]["sessions_not_measured"] == {"below_min_names": 4}
        excess = cell["buy_list_excess"]
        assert excess["list"] == report.BUY_LIST_PROXY and excess["decisory"] is False and excess["mean_listed_per_session"] == 3.0
        expected_excess = sum((1 + growth[f"S{k:02d}"]) ** 2 - 1 for k in (9, 10, 11)) / 3 - sum((1 + g) ** 2 - 1 for g in growth.values()) / 12
        assert excess["blocks"]["mean_per_session"] == pytest.approx(expected_excess, rel=1e-6) and expected_excess > 0
        # the pro-rated log-errors, recomputed from the synthetic construction: e_rw = −2·ln(1 + g), e_model = e_rw + (2/252)·ln(1 + u)
        e_rw = {k: -2 * math.log(1 + 0.001 * k) for k in range(12)}
        e_model = {k: e_rw[k] + 2 / 252 * math.log(1 + 0.05 * k - 0.2) for k in range(12)}
        e_cons = {k: e_rw[k] + 2 / 252 * math.log((1 + 0.05 * k - 0.2) * 1.1) for k in range(12)}
        mse_rw, mse_model, mse_cons = (sum(v ** 2 for v in e.values()) / 12 for e in (e_rw, e_model, e_cons))
        vs_rw, vs_cons = cell["log_mse_vs_random_walk"], cell["log_mse_vs_consensus"]
        assert vs_rw["n"] == 48 and vs_rw["mse_random_walk"] == pytest.approx(mse_rw, rel=1e-5) and vs_rw["mse_model"] == pytest.approx(mse_model, rel=1e-5)
        assert vs_rw["ratio"] == pytest.approx(mse_model / mse_rw, rel=1e-5) and vs_rw["label"] == ("BETTER" if mse_model < mse_rw else "NOT_BETTER")
        assert vs_cons["n"] == 48 and vs_cons["excluded"] == {} and vs_cons["mse_consensus"] == pytest.approx(mse_cons, rel=1e-5)
        assert vs_rw["decisory"] is False and vs_cons["decisory"] is False and cell["log_mse_raw_tp"]["n"] == 48
    assert us["verdict"]["status"] == "INSUFFICIENT" and us["verdict"]["reasons"] == ["blocks_below_min:2<5"]
    # the internal source reads the same producer rows (tp = internal_tp): the same numbers here
    assert payload["results"]["US"]["official_internal_v1"]["partitions"]["holdout"]["horizons"]["2"]["ic"]["blocks"]["mean_per_session"] == 1.0
    b3 = payload["results"]["B3"]["official_blend_v1"]
    assert b3["partitions"]["holdout"]["horizons"]["2"]["ic"]["sessions_not_measured"] == {"below_min_names": 4}
    assert b3["partitions"]["holdout"]["horizons"]["2"]["log_mse_vs_random_walk"]["n"] == 12 and set(b3["vintages"]) == {"B3"}


def test_the_receipt_is_deterministic_and_independent_of_the_store_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_horizons(monkeypatch)
    database, cut, sessions, _ = _store()
    first = report.AccuracyReportService(report.ReadOnlyStore(database), settings=_settings()).report(cut=cut, holdout_start=sessions[4])  # type: ignore[arg-type]
    again = report.AccuracyReportService(report.ReadOnlyStore(database), settings=_settings()).report(cut=cut, holdout_start=sessions[4])  # type: ignore[arg-type]
    random.Random(7).shuffle(database._valuation_predictions)  # the same store, its rows permuted (lists in the double): the same hash
    random.Random(11).shuffle(database._price_bars)
    shuffled = report.AccuracyReportService(report.ReadOnlyStore(database), settings=_settings()).report(cut=cut, holdout_start=sessions[4])  # type: ignore[arg-type]
    assert first["payload_sha256"] == again["payload_sha256"] == shuffled["payload_sha256"]
    # a store built in the reverse order: the same numbers; only the vintages' ids (uuid4 of another store) differ
    permuted, _, _, _ = _store(permute=True)
    mirrored = report.AccuracyReportService(report.ReadOnlyStore(permuted), settings=_settings()).report(cut=cut, holdout_start=sessions[4])  # type: ignore[arg-type]
    for group in ("B3", "US"):
        for source in report.DEFAULT_SOURCES:
            original_cell, mirrored_cell = first["payload"]["results"][group][source], mirrored["payload"]["results"][group][source]
            assert {k: v for k, v in original_cell.items() if k != "vintages"} == {k: v for k, v in mirrored_cell.items() if k != "vintages"}
            assert [v["available_at"] for v in original_cell["vintages"].values()] == [v["available_at"] for v in mirrored_cell["vintages"].values()]
    without_holdout = report.AccuracyReportService(report.ReadOnlyStore(database), settings=_settings()).report(cut=cut)  # type: ignore[arg-type]
    cell = without_holdout["payload"]["results"]["US"]["official_blend_v1"]
    assert cell["verdict"] == {"status": "NO_HOLDOUT", "reasons": ["holdout_start_not_given"], "gate": False}
    assert cell["partitions"]["development"]["sessions"] == 8 and cell["partitions"]["holdout"]["observations"] == 0
    assert cell["partitions"]["development"]["horizons"]["2"]["ic"]["blocks"]["blocks"] == 4


def test_a_cut_before_the_vintage_is_attrition_and_an_immature_target_is_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_horizons(monkeypatch)
    database, cut, sessions, _ = _store()
    blind = series.session_close("NASDAQ", sessions[-1]) + 2 * H  # every record published, no vintage yet: labels unavailable, never a price from elsewhere
    cell = report.AccuracyReportService(report.ReadOnlyStore(database), settings=_settings()).report(  # type: ignore[arg-type]
        cut=blind, groups=("US",), sources=("official_blend_v1",), holdout_start=sessions[4])["payload"]["results"]["US"]["official_blend_v1"]
    development = cell["partitions"]["development"]["horizons"]["2"]
    assert development["attrition"]["by_cause"] == {"no_vintage": 48} and development["attrition"]["rate"] == 1.0
    assert cell["verdict"]["status"] == "UNMEASURED"  # the holdout's eligible labels are all unavailable (no vintage before the cut)
    holdout = cell["partitions"]["holdout"]["horizons"]["2"]
    assert holdout["eligible"] == 24 and holdout["ineligible"] == {"not_yet_mature": 24}  # sessions 4 and 5: their targets (6, 7) closed before the cut
    assert cell["verdict"]["reasons"] == ["attrition_above_cap:1.0000>0.1"]


def test_naive_clocks_unknown_groups_and_empty_sources_are_refused() -> None:
    service = report.AccuracyReportService(report.ReadOnlyStore(Database(_settings())), settings=_settings())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="time-zone aware"):
        service.report(cut=datetime(2026, 9, 12))
    with pytest.raises(ValueError, match="unknown market groups"):
        service.report(cut=datetime(2026, 9, 12, tzinfo=UTC), groups=("EU",))
    with pytest.raises(ValueError, match="no sources"):
        service.report(cut=datetime(2026, 9, 12, tzinfo=UTC), sources=(" ",))
    with pytest.raises(ValueError, match="sha256"):
        service.report(cut=datetime(2026, 9, 12, tzinfo=UTC), prereg_sha256="nope")


def test_the_cli_prints_aggregates_only_binds_the_prereg_and_forces_a_read_only_session(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
                                                                                          tmp_path: Path) -> None:
    _small_horizons(monkeypatch)
    database, cut, sessions, _ = _store()
    monkeypatch.setattr(report, "get_settings", _settings)
    monkeypatch.setattr(report, "Database", lambda settings: database)
    monkeypatch.setenv("PGOPTIONS", "")
    prereg = tmp_path / "prereg.md"
    prereg.write_bytes(b"pre-registration bytes\n")
    assert report.main(["--as-of", cut.isoformat(), "--holdout-start", sessions[4].isoformat(), "--prereg", str(prereg), "--groups", "us"]) == 0
    out = capsys.readouterr().out
    receipt = json.loads(out)
    assert receipt["schema"] == report.SCHEMA_VERSION and receipt["payload_sha256"] == official.canonical_sha256(receipt["payload"])
    assert receipt["payload"]["prereg_sha256"] == hashlib.sha256(b"pre-registration bytes\n").hexdigest() and receipt["payload"]["market_groups"] == ["US"]
    assert receipt["provenance"]["module_sha256"] == hashlib.sha256(Path(report.__file__).read_bytes()).hexdigest()
    assert not any(symbol in out for symbol in ("S00", "S11", "T99", "R50")) and out.count("\n") == 1
    assert os.environ["PGOPTIONS"].endswith(report.READ_ONLY_PGOPTION)
    with pytest.raises(SystemExit):
        report.main(["--as-of", "2026-09-12T00:00:00"])  # naive: refused
    with pytest.raises(SystemExit):
        report.main(["--as-of", cut.isoformat(), "--holdout-start", "19/10/2026"])
    with pytest.raises(SystemExit):
        report.main(["--as-of", cut.isoformat(), "--prereg", str(tmp_path / "absent.md")])
    with pytest.raises(SystemExit):
        report.main(["--as-of", cut.isoformat(), "--groups", "B3,EU"])
