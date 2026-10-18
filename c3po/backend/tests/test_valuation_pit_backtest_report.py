"""PREREG_VALUATION_PIT_BACKTEST_US_V1 — the single look of the US point-in-time backtest: the verdict order on hand-built
cells (VOID → UNMEASURED → NEGATIVE → PASS → FAIL; the executable IC decides, never the T → T+h one; both halves; the
63-session persistence co-condition; the coverage floor), the point-in-time screen, the halves and the block rule
(identical to the accuracy report's), the grid (T clock, bounds, anchoring), the manifest (hash, shape, refusals), the
binding of the code to the prereg, the design simulation, and the service on the in-memory double over SYNTHETIC stores
(synthetic symbols, bars and run snapshots: a true IC positive / zero / negative, halves that disagree, a signal that does
not persist, a signal visible only in the day after T, attrition above the cap, fewer than 12 blocks, the screen, the
coverage floor, and every integrity failure of a manifest — which voids the reading WITHOUT reading a label). Never the
network."""
from __future__ import annotations

import hashlib
import io
import json
import math
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import pytest

from app import valuation_accuracy_report as accuracy
from app import valuation_official as official
from app import valuation_panel as panel
from app import valuation_pit_backtest_report as backtest
from app import valuation_price_history as series
from app.config import Settings
from app.database import Database
from app.market_data.eodhd import EodhdClient

UTC = timezone.utc
H = timedelta(hours=1)
ROOT = Path(__file__).resolve().parents[3]
PREREG_PATH = ROOT / "c3po" / "docs" / "PREREG_VALUATION_PIT_BACKTEST_US_V1.md"
SOURCE_VERSION = "pit-rerun-v1+synthetic000"
ENGINE = {name: hashlib.sha256(name.encode()).hexdigest() for name in ("valuation_v3_engine.py", "valuation_v3_inputs.py", "valuation_v3_macro.py",
                                                                       "valuation_v3_shadow.py", "valuation_pit_rerun.py", "valuation_v2_engine.py",
                                                                       "valuation_official.py", "valuation_official_engine.py", "sec_xbrl.py",
                                                                       "valuation_asfiled.py", "statement_vintages.py", "valuation_price_history.py")}
OBJECTS = {name: hashlib.sha256(name.encode()).hexdigest() for name in ("app.database.Database.latest_analysis_snapshot", "app.database.Database.price_bars")}
PRODUCER = {"files": ENGINE, "objects": OBJECTS}  # what the workflow computes from the prereg commit


def _names(count: int = 30) -> list[tuple[str, str]]:
    return [("NASDAQ" if k < count // 2 else "NYSE", f"N{k:02d}") for k in range(count)]  # synthetic symbols


NAMES = _names()


# ------------------------------------------------------------------ the verdict, pure
def _blocks(estimate: float | None, *, blocks: int, p_greater: float | None = None, p_less: float | None = None) -> dict[str, Any]:
    return {"blocks": blocks, "blocks_pending": 0, "estimate": estimate, "se": 0.01, "t": 1.0, "df": max(0, blocks - 1), "p_greater": p_greater, "p_less": p_less}


def _primary(*, ic: dict[str, Any], eligible: int = 100, rate: float = 0.0, spread: float | None = 0.01, descriptive: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"attrition_executable": {"eligible": eligible, "rate": rate if eligible else None},
            "ic_executable": {"blocks": ic, "mature_through_index": 300}, "decile_spread_executable": {"blocks": _blocks(spread, blocks=ic["blocks"])},
            "ic": {"blocks": descriptive or _blocks(None, blocks=0), "mature_through_index": 300}}


def _split(first: float | None = 0.05, second: float | None = 0.04) -> dict[str, Any]:
    return {"first": {"estimate": first}, "second": {"estimate": second}}


GOOD_COVERAGE = {"records_share": 0.8, "screened_names_median": 400}
PERSISTENT = {"blocks": 22, "estimate": 0.05, "p_greater": 0.001}


def test_the_verdict_follows_the_pre_registered_order_on_the_executable_ic() -> None:
    def decide(primary: dict[str, Any], split: dict[str, Any] | None = None, **options: Any) -> dict[str, Any]:
        return backtest.verdict(primary, split or _split(), **{"persistence": PERSISTENT, "coverage": GOOD_COVERAGE, **options})

    good = _primary(ic=_blocks(0.05, blocks=64, p_greater=0.001, p_less=0.999))
    passed = decide(good)
    assert passed["status"] == "PASS" and passed["reasons"] == [] and passed["look"] == "SINGLE" and passed["statistic"] == "ic_executable" and passed["gate"] is False
    assert passed["coverage_records_share"] == 0.8 and passed["coverage_screened_names_median"] == 400 and passed["persistence_p_greater"] == 0.001
    # VOID reveals no statistic, whatever the cell held
    voided = decide(good, void=["code_mismatch"])
    assert voided["status"] == "VOID" and voided["reasons"] == ["code_mismatch"] and voided["ic_estimate"] is None and voided["ic_p_greater"] is None
    assert voided["halves"] == {"first": None, "second": None} and voided["decile_spread_executable_estimate"] is None and voided["persistence_p_greater"] is None
    assert backtest.verdict(None, None, void=["manifest_not_complete"])["status"] == "VOID"
    # UNMEASURED before anything else: no eligible observation, the executable attrition above the cap, the coverage floor
    assert decide(_primary(ic=_blocks(None, blocks=0), eligible=0))["reasons"] == ["no_eligible_observations"]
    lossy = decide(_primary(ic=_blocks(-0.2, blocks=64, p_greater=0.9999, p_less=0.0001), rate=0.11))
    assert lossy["status"] == "UNMEASURED" and lossy["reasons"] == ["attrition_above_cap:0.1100>0.1"]
    assert decide(_primary(ic=_blocks(0.05, blocks=64, p_greater=0.001, p_less=0.999), rate=0.10))["status"] == "PASS"  # the cap is inclusive
    thin = decide(good, coverage={"records_share": 0.59, "screened_names_median": 149})
    assert thin["status"] == "UNMEASURED" and thin["reasons"] == ["coverage_records_share_below_floor:0.59<0.6", "coverage_screened_names_below_floor:149<150"]
    assert decide(good, coverage={"records_share": 0.60, "screened_names_median": 150})["status"] == "PASS"  # both floors inclusive
    assert decide(good, coverage={})["status"] == "UNMEASURED"  # an unknown coverage is not met
    # NEGATIVE: the executable IC significantly below zero (one-sided 0.05), after the coverage floor
    negative = decide(_primary(ic=_blocks(-0.04, blocks=64, p_greater=0.99, p_less=0.01)), _split(-0.03, -0.05))
    assert negative["status"] == "NEGATIVE" and negative["reasons"] == ["ic_executable_negative:p_less=0.010000<=0.05"]
    assert decide(_primary(ic=_blocks(-0.04, blocks=64, p_greater=0.94, p_less=0.06)), _split(-0.03, -0.05))["status"] == "FAIL"
    # FAIL lists every unmet condition of the pass
    cases = {
        "blocks_below_min:11<12": _primary(ic=_blocks(0.05, blocks=11, p_greater=0.001, p_less=0.999)),
        "ic_executable_below_min:0.015<0.02": _primary(ic=_blocks(0.015, blocks=64, p_greater=0.001, p_less=0.999)),
        "ic_executable_not_significant:p_greater=0.06>0.05": _primary(ic=_blocks(0.05, blocks=64, p_greater=0.06, p_less=0.94)),
        "decile_spread_executable_not_positive": _primary(ic=_blocks(0.05, blocks=64, p_greater=0.001, p_less=0.999), spread=0.0),
        "decile_spread_executable_unmeasured": _primary(ic=_blocks(0.05, blocks=64, p_greater=0.001, p_less=0.999), spread=None),
    }
    for reason, cell in cases.items():
        decided = decide(cell)
        assert decided["status"] == "FAIL" and decided["reasons"] == [reason], (reason, decided)
    assert decide(good, _split(first=-0.001))["reasons"] == ["ic_executable_first_half_not_positive:-0.001"]
    assert decide(good, _split(second=0.0))["reasons"] == ["ic_executable_second_half_not_positive:0.0"]
    assert decide(good, _split(first=None))["reasons"] == ["ic_executable_first_half_not_positive:None"]
    assert decide(good, persistence={"blocks": 22, "estimate": 0.05, "p_greater": 0.07})["reasons"] == ["ic_executable_not_persistent:p_greater_63=0.07>0.05"]
    assert decide(good, persistence={"blocks": 1, "estimate": 0.05, "p_greater": None})["reasons"] == ["ic_executable_not_persistent:p_greater_63=None>0.05"]
    # the T → T+h IC never decides: strongly positive there, nothing on the executable return → FAIL
    descriptive = _primary(ic=_blocks(0.0, blocks=64, p_greater=0.5, p_less=0.5), descriptive=_blocks(0.3, blocks=64, p_greater=1e-9, p_less=1.0))
    assert decide(descriptive)["status"] == "FAIL"


def test_the_persistence_test_is_batch_means_with_its_own_factor() -> None:
    means = [0.1, 0.3, 0.2, 0.4]
    result = backtest.persistence_test(means)
    center, sd = 0.25, math.sqrt(sum((m - 0.25) ** 2 for m in means) / 3)
    se = math.sqrt(backtest.PERSISTENCE_VARIANCE_FACTOR) * sd / 2
    assert result["estimate"] == pytest.approx(center) and result["se"] == pytest.approx(se) and result["df"] == 3 and result["blocks"] == 4
    assert result["p_greater"] == pytest.approx(accuracy.student_t_sf(center / se, 3)) and result["variance_factor"] == 1.14 and result["block_sessions"] == 63
    assert backtest.persistence_test([0.2])["se"] is None and backtest.persistence_test([0.2, 0.2])["se"] == 0.0 and backtest.persistence_test([])["estimate"] is None


def test_the_point_in_time_screen_applies_the_screeners_rules_at_t(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.market_data import us_screener
    assert (backtest.SCREEN_MIN_CLOSE, backtest.SCREEN_MIN_MARKET_CAP, backtest.SCREEN_MIN_DOLLAR_VOLUME, backtest.SCREEN_TOP_PER_EXCHANGE) == \
        (us_screener.MIN_PRICE, us_screener.MIN_STOCK_MARKET_CAP, us_screener.MIN_STOCK_CASH_VOLUME, us_screener.STOCK_LIMIT)  # the 2026 screener's own numbers

    def item(*, kind: str = "Stock", close: float | None = 10.0, cap: float | None = 1e9, volume: float | None = 5e7) -> dict[str, Any]:
        return {"security_type": kind, "close": close, "market_cap": cap, "dollar_volume_median_20": volume}

    inputs = {"AAA": item(), "BBB": item(kind="ETF"), "CCC": item(close=2.99), "DDD": item(cap=7.4e8), "EEE": item(volume=1.9e7), "FFF": item(volume=None),
              "GGG": item(volume=9e7), "HHH": item(cap=None)}
    kept, removed = backtest.screen(inputs)
    assert kept == {"AAA", "GGG"} and removed == {"not_a_stock": 1, "close_below_min": 1, "market_cap_below_min": 2, "dollar_volume_below_min": 2}
    monkeypatch.setattr(backtest, "SCREEN_TOP_PER_EXCHANGE", 1)
    kept, removed = backtest.screen({"AAA": item(volume=5e7), "BBB": item(volume=5e7), "CCC": item(volume=4e7)})
    assert kept == {"AAA"} and removed == {"beyond_top_per_exchange": 2}  # the most liquid; a tie goes to the first symbol
    # the volume basis the grid decided picks the dollar volume: as traded (close × volume) or split-adjusted (adjusted close × volume)
    monkeypatch.setattr(backtest, "SCREEN_TOP_PER_EXCHANGE", 300)
    both = {"AAA": {**item(volume=5e7), "split_adjusted_dollar_volume_median_20": 1e7}, "BBB": {**item(volume=1e7), "split_adjusted_dollar_volume_median_20": 5e7}}
    assert backtest.screen(both)[0] == {"AAA"} and backtest.screen(both, basis="as_traded")[0] == {"AAA"}
    assert backtest.screen(both, basis="split_adjusted")[0] == {"BBB"}
    with pytest.raises(KeyError):
        backtest.screen(both, basis="undetermined")


def _series(*, at: int | None, factor: float, adjusted_volume: bool, sessions: int = 80) -> dict[str, dict[str, float]]:
    """A synthetic series with a ``factor``:1 split at index ``at`` (none with ``None``): the as-traded close is ``factor`` ×
    the adjusted close before it; the volume in traded shares jumps by ``factor`` there, a split-adjusted one does not."""
    rows: dict[str, dict[str, float]] = {}
    for index in range(sessions):
        before = at is not None and index < at
        traded = 1_000.0 * (1.0 if before or at is None else factor) * (1.0 + 0.05 * ((index * 7) % 5 - 2))
        rows[(date(2024, 1, 1) + timedelta(days=index)).isoformat()] = {
            "close": 20.0 * (factor if before else 1.0), "adjusted_close": 20.0,
            "volume": traded * (factor if adjusted_volume and before else 1.0)}
    return rows


def test_the_volume_check_reads_split_factors_from_the_vintage_and_decides_only_with_agreement() -> None:
    raw = [_series(at=40, factor=f, adjusted_volume=False) for f in (2.0, 3.0, 0.25)]  # two splits and a 1:4 reverse split
    assert backtest.volume_split_check(raw) == {"events": 3, "as_traded_like": 3, "split_adjusted_like": 0, "decision": "as_traded",
                                                "field": "dollar_volume_median_20"}
    adjusted = [_series(at=40, factor=f, adjusted_volume=True) for f in (2.0, 3.0, 0.25)]
    assert backtest.volume_split_check(adjusted)["decision"] == "split_adjusted" and backtest.volume_split_check(adjusted)["field"] == "split_adjusted_dollar_volume_median_20"
    assert backtest.volume_split_check(raw[:2])["decision"] == "undetermined"  # fewer than three clean events
    assert backtest.volume_split_check([*raw[:2], *adjusted[:2]])["decision"] == "undetermined"  # no two-thirds agreement
    assert backtest.volume_split_votes(_series(at=None, factor=2.0, adjusted_volume=False)) == {}  # no event, no vote
    assert backtest.volume_split_votes(_series(at=10, factor=2.0, adjusted_volume=False)) == {}  # fewer than 20 valid volumes before the event
    crowded = _series(at=40, factor=2.0, adjusted_volume=False)
    for session in sorted(crowded)[50:]:
        crowded[session]["close"] = crowded[session]["close"] * 2.0  # a second event ten sessions later: neither is a clean reading
    assert backtest.volume_split_votes(crowded) == {}


def test_the_median_of_screened_names_counts_every_grid_session_even_an_empty_one() -> None:
    items = [{"return_executable": 0.01}, {"return_executable": None}, {"return_executable": 0.02}]
    names = backtest.PitBacktestReportService._names_per_session({"2025-01-07": items, "2025-01-09": [{"return_executable": None}]},
                                                                  ["2025-01-07", "2025-01-09", "2025-01-13"])
    assert names == {"executable_h_primary": {"n": 3, "min": 0.0, "median": 0.0, "max": 2.0}}


def test_the_within_exchange_rank_ic_ranks_the_upside_inside_each_exchange() -> None:
    """NASDAQ upsides 0.01…0.10, NYSE 1.01…1.10 (a level difference between the exchanges); inside each exchange the higher
    upside has the higher executable return, but every NYSE return is below every NASDAQ one: the pooled IC is negative,
    the per-exchange ICs are 1 and the IC of the upside ranked WITHIN its exchange is positive."""
    items = ([{"market": "NASDAQ", "upside": 0.01 * k, "return_executable": 0.10 + 0.001 * k} for k in range(1, 11)]
             + [{"market": "NYSE", "upside": 1.0 + 0.01 * k, "return_executable": -0.10 + 0.001 * k} for k in range(1, 11)])
    session = "2025-01-07"
    pooled = accuracy.spearman([item["upside"] for item in items], [item["return_executable"] for item in items])
    assert pooled is not None and pooled < -0.4
    result = backtest.PitBacktestReportService._descriptive([], [], {session: items}, [(0, pooled)], index_of={session: 0},
                                                            mature_through={horizon: 100 for horizon in backtest.label_horizons()}, partition_last=0)
    within = result["within_exchange_rank_ic"]
    assert within["sessions_measured"] == 1 and within["blocks"]["estimate"] > 0.4
    assert all(result["per_exchange"][market]["blocks"]["estimate"] == pytest.approx(1.0) for market in backtest.MARKETS)
    assert result["ic_by_year"] == {"2025": {"sessions": 1, "mean": pooled}}


def test_the_halves_split_the_complete_blocks_and_leave_the_middle_one_out() -> None:
    means = [(0, 0.1), (1, 0.2), (2, 0.9), (3, -0.1), (4, -0.3)]
    split = backtest.halves(means)
    assert split["blocks"] == 5 and split["per_half"] == 2
    assert (split["first"]["first_block"], split["first"]["last_block"], split["second"]["first_block"], split["second"]["last_block"]) == (0, 1, 3, 4)
    assert split["first"]["estimate"] == pytest.approx(0.15) and split["second"]["estimate"] == pytest.approx(-0.2)  # block 2 (the middle) is in neither
    assert split["first"] == {**split["first"], **accuracy.batch_means_test([0.1, 0.2])}
    single = backtest.halves([(0, 0.5)])
    assert single["per_half"] == 0 and single["first"]["estimate"] is None and single["second"]["estimate"] is None


def test_the_complete_blocks_are_exactly_the_accuracy_reports() -> None:
    rng = random.Random(3)
    for _ in range(200):
        length = rng.choice((2, 3, 5, 21, 63))
        points = sorted({(rng.randrange(0, 120), round(rng.uniform(-1, 1), 6)) for _ in range(rng.randrange(1, 60))})
        mature = rng.choice((None, -1, rng.randrange(0, 130)))
        cap = rng.choice((None, rng.randrange(0, 130)))
        stats = accuracy.block_statistics(points, block_length=length, mature_through=mature, partition_last=cap)
        means = backtest.complete_block_means(points, block_length=length, mature_through=mature, partition_last=cap)
        assert len(means) == stats["blocks"] and accuracy.batch_means_test([m for _b, m in means])["estimate"] == stats["estimate"]


# ------------------------------------------------------------------ the grid
def test_t_is_one_in_the_morning_in_sao_paulo_after_the_session_whatever_new_yorks_clock() -> None:
    for session, expected in ((date(2024, 10, 2), "2024-10-03T04:00:00+00:00"), (date(2024, 12, 2), "2024-12-03T04:00:00+00:00"),
                              (date(2024, 10, 4), "2024-10-05T04:00:00+00:00"), (date(2024, 7, 3), "2024-07-04T04:00:00+00:00")):
        instant = backtest.t_instant(session)
        assert instant.isoformat() == expected and official.session_date_of("NASDAQ", instant) == session.isoformat()  # a Friday's T is Saturday; 4 July is no session
    with pytest.raises(ValueError):
        backtest.t_instant(date(2024, 10, 5))  # a Saturday is not a session: its T belongs to Friday


def _vintage(start: str, end: str, available_at: str, *, status: str = "ok") -> dict[str, Any]:
    return {"status": status, "from": start, "to": end, "available_at": available_at}


def test_the_bounds_and_the_grid_follow_the_pinned_vintages_and_start_at_the_pre_registered_session() -> None:
    backfill = _vintage("2016-10-01", "2026-10-19", "2026-10-19T00:30:00+00:00")  # the one-off 120-month backfill published on 18/10 at 21:30 BRT
    bounds = backtest.eligible_bounds({"NASDAQ": backfill, "NYSE": backfill})
    assert bounds["grid_start"] == "2021-06-01" and bounds["starts_at_grid_start"] is True
    assert (bounds["first_eligible"], bounds["last_eligible"]) == ("2021-06-01", "2026-09-16")  # 22 sessions before 2026-10-16, the last closed one
    assert bounds["per_market"]["NASDAQ"]["first_session"] == "2016-10-03" and bounds["per_market"]["NASDAQ"]["last_label_session"] == "2026-10-16"
    grid = backtest.prereg_grid(bounds)
    sessions = [stamp.date() for stamp in series._calendar("NASDAQ").sessions_in_range("2021-06-01", "2026-09-16")]
    assert grid == sessions[::5] and grid[0] == date(2021, 6, 1) and len(grid) == 266
    last_index = sessions.index(grid[-1])
    assert last_index // 21 + 1 == 64 and sum(1 for day in grid if sessions.index(day) // 21 == 63) == 1  # 64 blocks, the last holding ONE instant
    assert last_index // 63 + 1 == 22  # 22 blocks of 63 sessions for the persistence co-condition
    nightly = _vintage("2023-10-01", "2026-10-19", "2026-10-19T04:30:00+00:00")  # a 36-month nightly republication cannot start a 2021 grid
    short = backtest.eligible_bounds({"NASDAQ": nightly, "NYSE": nightly})
    assert short["starts_at_grid_start"] is False and short["first_eligible"] == "2024-10-02"
    later = backtest.eligible_bounds({"NASDAQ": nightly, "NYSE": nightly}, grid_start=date(2024, 10, 2))
    assert later["starts_at_grid_start"] is True and len(backtest.prereg_grid(later)) == 98
    assert backtest.eligible_bounds({"NASDAQ": backfill, "NYSE": _vintage("2016-10-01", "2026-10-15", "2026-10-15T23:00:00+00:00")})["last_eligible"] == "2026-09-15"
    for unusable in ({"NASDAQ": backfill, "NYSE": None}, {"NASDAQ": backfill, "NYSE": {**backfill, "status": "manifest_mismatch"}},
                     {"NASDAQ": backfill, "NYSE": _vintage("2025-10-01", "2026-10-19", "2026-10-19T04:30:00+00:00")}):
        none = backtest.eligible_bounds(unusable)
        assert none["first_eligible"] is None and none["starts_at_grid_start"] is False and backtest.prereg_grid(none) == []
    with pytest.raises(ValueError):
        backtest.prereg_grid(bounds, step=0)


# ------------------------------------------------------------------ the manifest
VOLUME_BASIS = {"events": 4, "as_traded_like": 4, "split_adjusted_like": 0, "decision": "as_traded", "field": "dollar_volume_median_20", "series_read": 30}


def _manifest(entries: list[dict[str, Any]], pins: dict[str, dict[str, Any]], **changes: Any) -> dict[str, Any]:
    manifest: dict[str, Any] = {"schema": backtest.MANIFEST_SCHEMA, "market": "US", "markets": ["NASDAQ", "NYSE"], "price_pin": {"requested_at": "x", **pins},
                                "catalogue_pin": {"requested_at": "x"}, "statements": "vintages", "step_sessions": backtest.STEP_SESSIONS,
                                "grid_start": backtest.GRID_START.isoformat(), "grid": entries, "complete": True, "volume_basis": dict(VOLUME_BASIS)}
    manifest.update(changes)
    manifest["manifest_sha256"] = backtest.manifest_sha256(manifest)
    return manifest


def _entry(market: str = "NASDAQ", run_key: str = "a" * 64, as_of: str = "2024-10-03T04:00:00+00:00") -> dict[str, Any]:
    return {"as_of": as_of, "session_date": "2024-10-02", "market": market, "run_key": run_key, "cycle_id": "c", "idempotent": False, "evaluated": 1, "not_evaluable": {}}


PINS = {"NASDAQ": {"publication_id": "p1", "available_at": "2026-10-19T04:30:00+00:00"}, "NYSE": {"publication_id": "p2", "available_at": "2026-10-19T04:31:00+00:00"}}


def test_the_manifest_is_refused_unless_its_hash_recomputes_and_its_shape_holds() -> None:
    manifest = _manifest([_entry(), _entry("NYSE", "b" * 64)], PINS)
    assert backtest.load_manifest(json.dumps(manifest)) == manifest
    tampered = {**manifest, "statements": "provider"}
    bad = {
        "not a JSON document": "{",
        "is not a VALUATION-PIT-GRID-MANIFEST-v1": json.dumps({**manifest, "schema": "other"}),
        "does not recompute": json.dumps(tampered),
        "no usable price pin for NYSE": json.dumps(_manifest([_entry()], {"NASDAQ": PINS["NASDAQ"]})),
        "lacks one of": json.dumps(_manifest([{k: v for k, v in _entry().items() if k != "cycle_id"}], PINS)),
        "not a zoned instant": json.dumps(_manifest([_entry(as_of="2024-10-03T04:00:00")], PINS)),
        "unknown exchange or a run_key": json.dumps(_manifest([_entry(market="B3")], PINS)),
        "appears twice": json.dumps(_manifest([_entry(), _entry(run_key="b" * 64)], PINS)),
        "larger than": " " * (backtest.MAX_MANIFEST_BYTES + 1),
    }
    for message, text in bad.items():
        with pytest.raises(backtest.ManifestError, match=message):
            backtest.load_manifest(text)
    with pytest.raises(backtest.ManifestError, match="appears twice"):  # one run_key for two (T, exchange)
        backtest.load_manifest(json.dumps(_manifest([_entry(), _entry("NYSE")], PINS)))


# ------------------------------------------------------------------ the protocol, the code binding, the design
def test_the_protocol_is_the_prereg() -> None:
    constants = backtest.protocol()
    assert (constants["step_sessions"], constants["min_prior_sessions"], constants["primary_horizon"], constants["horizons_sessions"]) == (5, 252, 21, [21, 63, 126])
    assert constants["grid_start"] == "2021-06-01" and "120-month" in constants["price_vintage"] and constants["price_vintage_from_latest"] == "2016-12-01"
    assert (constants["min_blocks"], constants["ic_min"], constants["alpha"], constants["alpha_negative"], constants["attrition_cap"]) == (12, 0.02, 0.05, 0.05, 0.10)
    assert constants["persistence"]["block_sessions"] == 63 and constants["persistence"]["variance_factor"] == 1.14
    assert constants["coverage_floor"]["min_records_share"] == 0.60 and constants["coverage_floor"]["min_screened_names_median"] == 150
    assert constants["screen"]["top_per_exchange"] == 300 and constants["allowed_refusals"] == ["duplicate_across_exchanges", "run_not_in_manifest"]
    assert constants["screen"]["volume_basis"]["min_events"] == 3 and constants["screen"]["volume_basis"]["min_factor"] == 1.5
    assert "split-only" in constants["screen"]["rank"] and "never the total-return adjusted close" in constants["screen"]["rank"]
    assert constants["screen"]["volume_basis"]["split_adjusted"].startswith("close x volume / S(s)")
    assert "covered_in_catalogue" in constants["statements_stability"] and "zero included" in constants["coverage_floor"]["screened_names_median"]
    assert constants["decisory_statistic"] == "ic_executable" and constants["statements"] == "vintages" and constants["markets"] == ["NASDAQ", "NYSE"]
    assert constants["t_clock"] == "01:00 America/Sao_Paulo of the civil day after session D (session_date = D)" and constants["look"] == "single"
    assert constants["verdict_order"] == ["VOID", "UNMEASURED", "NEGATIVE", "PASS", "FAIL"] and constants["adjacent_block_variance_factor"] == 1.5
    assert constants["code_pins"] == {"files": list(backtest.PINNED_FILES), "objects": list(backtest.PINNED_OBJECTS)} and constants["gate"] is False
    assert backtest.label_horizons() == (1, 21, 22, 63, 64, 126, 127)
    text = PREREG_PATH.read_text(encoding="utf-8")
    for needle in ("VALUATION-PIT-BACKTEST-REPORT-v1", "VALUATION-PIT-GRID-MANIFEST-v1", "VALUATION-PIT-BACKTEST-OWNER-ORDER-v1", "STEP_SESSIONS = 5",
                   "MIN_PRIOR_SESSIONS = 252", "MIN_BLOCKS = 12", "IC_MIN = 0,02", "ALPHA = 0,05", "ALPHA_NEGATIVE = 0,05", "ATTRITION_CAP = 0,10",
                   "PERSISTENCE_VARIANCE_FACTOR = 1,14", "COVERAGE_MIN_RECORDS_SHARE = 0,60", "COVERAGE_MIN_SCREENED_NAMES = 150",
                   "SCREEN_TOP_PER_EXCHANGE = 300", "PRICE_VINTAGE_FROM_LATEST = 2016-12-01", "01:00 America/Sao_Paulo", "--statements vintages",
                   "--catalogue-pinned-at", "23:30", "ic_executable", f"DESIGN_SEED = {backtest.DESIGN_SEED}", f"DESIGN_REPS = {backtest.DESIGN_REPS}",
                   "GRID_START = 2021-06-01", "--months 120", "own_history", "vintages_coverage", "covered_in_catalogue", "VOLUME_CHECK_MIN_FACTOR = 1,5",
                   "VOLUME_CHECK_MIN_EVENTS = 3", "não-`VOID`", "DESIGN_INSTANTS = (51, 101, 266)", "valuation_price_history.py", "implementation_object_sha256",
                   "git log -1 --format=%H", "manifest_volume_basis_not_decided", "≈ 1,51", "split_adjusted_dollar_volume_median_20", "close × volume ÷ S(s)",
                   "definido duas vezes"):
        assert needle in text, needle


def test_the_prereg_pins_exactly_the_code_at_head() -> None:
    """The pins of the prereg ARE this code: a change to a pinned module or object makes this fail — the reading would be
    VOID under the hashed prereg; a new revision (new hash) is needed BEFORE the first label is read."""
    pins = accuracy.pins_from_prereg(PREREG_PATH.read_text(encoding="utf-8"))
    code = backtest.code_fingerprint()
    assert pins == accuracy.pins_of(code), "a pinned module/object changed: PREREG_VALUATION_PIT_BACKTEST_US_V1 needs a new revision"
    assert len(pins) == len(backtest.PINNED_FILES) + len(backtest.PINNED_OBJECTS)
    assert backtest.render_pins(code) == "\n".join(sorted(f"{key} {value}" for key, value in pins.items()))
    assert accuracy.bind_code(code, pins, prereg_sha256=hashlib.sha256(PREREG_PATH.read_bytes()).hexdigest())["status"] == "BOUND"


def test_the_design_simulation_has_the_size_and_the_power_shape_the_prereg_declares() -> None:
    table = backtest.design_table(reps=1500, seed=5, sds=(0.10,), ics=(-0.05, 0.0, 0.05, 0.10), instants=(51, 101))
    cells = {(cell["blocks"], cell["ic"]): cell for cell in table["cells"]}
    assert table["blocks"] == {12: 51, 24: 101} and table["persistence_blocks"] == {12: 4, 24: 8}
    for blocks in (12, 24):
        assert cells[(blocks, 0.0)]["pass"] <= 0.07 and cells[(blocks, 0.0)]["negative"] <= 0.07  # a one-sided 0.05 test (1500 paths: 3 sd of noise)
        assert cells[(blocks, -0.05)]["pass"] <= 0.005 and cells[(blocks, -0.05)]["negative"] > cells[(blocks, 0.0)]["negative"]
        assert cells[(blocks, 0.0)]["pass"] < cells[(blocks, 0.05)]["pass"] < cells[(blocks, 0.10)]["pass"]
    assert cells[(24, 0.05)]["pass"] > cells[(12, 0.05)]["pass"]  # more blocks, more power
    assert backtest.design_table(reps=200, seed=5, sds=(0.10,), ics=(0.05,), instants=(51,)) == backtest.design_table(reps=200, seed=5, sds=(0.10,), ics=(0.05,),
                                                                                                                    instants=(51,))
    real = backtest.design_table(reps=2, seed=5, sds=(0.10,), ics=(0.0,), instants=(266,))["cells"][0]
    assert (real["instants"], real["blocks"], real["persistence_blocks"]) == (266, 64, 22) and backtest.DESIGN_INSTANTS[-1] == 266  # the pre-registered grid
    with pytest.raises(ValueError):
        backtest.design_table(reps=10, instants=(4,))  # one block


def test_the_store_exposes_readers_only() -> None:
    store = backtest.ReadOnlyStore(Database(_settings()))
    assert callable(store.list_valuation_predictions_in_window) and callable(store.latest_analysis_snapshot_by_inputs) and callable(store.price_bars)
    for writer in ("insert_valuation_predictions", "save_analysis_snapshot", "persist_price_history_run", "connection", "latest_analysis_snapshot"):
        with pytest.raises(AttributeError, match="read-only"):
            getattr(store, writer)


# ------------------------------------------------------------------ the service on synthetic stores
class ScriptedHttp:
    def __init__(self, bars_by_symbol: dict[str, list[dict]]) -> None:
        self.bars_by_symbol = bars_by_symbol

    def get_json(self, url: str, *, params=None, headers=None):
        return self.bars_by_symbol.get(url.rsplit("/", 1)[-1], [])


def _settings() -> Settings:
    return Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False)


@pytest.fixture
def small(monkeypatch: pytest.MonkeyPatch) -> None:
    """A protocol small enough for a test store: h = 10, every 2nd session, 3 prior sessions (12 blocks need 111 sessions),
    persistence blocks of 30 sessions (3 h, as 63 is 3 × 21), a 2025 vintage taken as the backfill, a floor of 20 names."""
    monkeypatch.setattr(backtest, "HORIZONS", (10,))
    monkeypatch.setattr(backtest, "PRIMARY_HORIZON", 10)
    monkeypatch.setattr(backtest, "STEP_SESSIONS", 2)
    monkeypatch.setattr(backtest, "MIN_PRIOR_SESSIONS", 3)
    monkeypatch.setattr(backtest, "GRID_START", date(2025, 1, 7))  # the 4th session of the synthetic calendar (3 prior sessions)
    monkeypatch.setattr(backtest, "PERSISTENCE_BLOCK_SESSIONS", 30)
    monkeypatch.setattr(backtest, "PRICE_VINTAGE_FROM_LATEST", date(2030, 1, 1))
    monkeypatch.setattr(backtest, "COVERAGE_MIN_SCREENED_NAMES", 20)


Rule = Callable[[random.Random, int, dict[str, float], dict[str, float], dict[str, float]], dict[str, float]]


class Synthetic:
    """A US store: ``names`` synthetic names (half per exchange) × ``count`` XNYS sessions from 2025-01-02 of seeded random
    daily moves (±2 %), plus — with ``jump`` — a move of ``jump · z`` on the session AFTER each grid session (z standard
    normal per name and grid instant). One vintage per exchange published after the last session; at every grid session
    one synthetic re-executor run per exchange (a run snapshot with its prediction identities, producer, catalogue
    reference, screen inputs and coverage; the records with their run_key) whose upside is ``rule(rng, k, executable
    return, total return, z)``; names in ``small_caps`` fail the point-in-time screen (market cap below the floor)."""

    def __init__(self, rule: Rule, *, count: int = 130, seed: int = 11, jump: float = 0.0, drop_from: dict[str, int] | None = None, names: int = 30,
                 small_caps: frozenset[str] = frozenset()) -> None:
        self.rng = random.Random(seed)
        self.names = _names(names)
        self.small_caps = small_caps
        self.database = Database(_settings())
        self.sessions = [stamp.date() for stamp in series._calendar("NASDAQ").sessions_in_range("2025-01-02", "2025-12-31")][:count]
        h, lag = backtest.PRIMARY_HORIZON, backtest.EXECUTION_LAG_SESSIONS
        first, last = backtest.MIN_PRIOR_SESSIONS, count - 1 - (h + lag)
        grid_index = list(range(first, last + 1, backtest.STEP_SESSIONS))
        self.z = {j: {symbol: self.rng.gauss(0.0, 1.0) for _m, symbol in self.names} for j in grid_index}
        self.closes: dict[str, dict[date, float]] = {}
        for k, (_market, symbol) in enumerate(self.names):
            level, path = math.log(100.0 + 5 * k), {}
            for j, day in enumerate(self.sessions):
                if j:
                    level += self.rng.gauss(0.0, 0.02) + (jump * self.z[j - 1][symbol] if j - 1 in self.z else 0.0)
                path[day] = round(math.exp(level), 6)
            self.closes[symbol] = path
        self.vintage_at = series.session_close("NASDAQ", self.sessions[-1]) + 6 * H
        self.pins = self.publish(self.vintage_at, drop_from=drop_from)
        self.published = self.vintage_at + timedelta(days=1)
        self.entries: list[dict[str, Any]] = []
        for k, j in enumerate(grid_index):
            day = self.sessions[j]
            executable = {s: self.closes[s][self.sessions[j + h + lag]] / self.closes[s][self.sessions[j + lag]] - 1.0 for _m, s in self.names}
            total = {s: self.closes[s][self.sessions[j + h]] / self.closes[s][day] - 1.0 for _m, s in self.names}
            upsides = rule(self.rng, k, executable, total, self.z[j])
            for market in backtest.MARKETS:
                self.entries.append(self.run(market, day, {s: upsides[s] for m, s in self.names if m == market}))
        self.grid_sessions = [self.sessions[j] for j in grid_index]

    def publish(self, at: datetime, *, scale: float = 1.0, drop_from: dict[str, int] | None = None) -> dict[str, dict[str, Any]]:
        """One vintage per exchange of every bar (× ``scale``; a name's bars stop at ``drop_from``), published at ``at``."""
        pins: dict[str, dict[str, Any]] = {}
        for offset, market in enumerate(backtest.MARKETS):
            bars = {f"{symbol}.US": [{"date": day.isoformat(), "close": round(self.closes[symbol][day] * scale, 6), "adjusted_close": round(self.closes[symbol][day] * scale, 6),
                                      "volume": 1.0} for j, day in enumerate(self.sessions) if j < (drop_from or {}).get(symbol, len(self.sessions))]
                    for m, symbol in self.names if m == market}
            http = ScriptedHttp(bars)
            producer = series.PriceHistoryService(_settings(), self.database, http, eodhd=EodhdClient("https://eodhd.com", "secret", http))  # type: ignore[arg-type]
            producer.persist_run(market, start=self.sessions[0], end=self.sessions[-1], symbols=[s for m, s in self.names if m == market], now=at + timedelta(minutes=offset))
            publication = self.database.latest_analysis_snapshot(series.PUBLICATION_TYPE, market)
            assert publication is not None
            pins[market] = {"publication_id": publication["id"], "available_at": panel._utc(publication["published_at"]).isoformat(),
                            "bars_sha256": publication["outputs"]["bars_sha256"]}
        return pins

    def run(self, market: str, day: date, upsides: dict[str, float], *, run_key: str | None = None, supersedes: str | None = None,
            engine: dict[str, str] | None = None, statements: str = "vintages", extra_identity: bool = False, published: datetime | None = None,
            publication_id: str | None = None, scope: str = "universe", catalogue: str = "c" * 64, covered: int = 40, covered_in_catalogue: int | None = None,
            stocks: int | None = None, objects: dict[str, str] | None = None,
            session_date: date | None = None) -> dict[str, Any]:
        """One synthetic run of (market, T): its records and its snapshot, as valuation_pit_rerun writes them."""
        instant = backtest.t_instant(day)
        run_key = run_key or hashlib.sha256(f"{market}|{day.isoformat()}|{uuid4()}".encode()).hexdigest()
        cycle_id = str(uuid4())
        published = published or (self.published + timedelta(seconds=len(self.database._analysis_snapshots)))
        records = []
        for symbol, upside in sorted(upsides.items()):
            price = self.closes[symbol][day]
            tp = price * (1.0 + upside)
            record = official.prediction_from_row({"symbol": symbol, "our_tp": tp, "buy_in": tp * 0.8, "internal_tp": tp, "price": price, "status": "retrospective"},
                                                  market=market, scope=scope, cycle_id=cycle_id, source_version=SOURCE_VERSION, prediction_instant=instant,
                                                  published_at=published, source=official.SOURCE_V3_2_SHADOW, extra_provenance={"run_key": run_key})
            assert record is not None
            records.append(record)
        identities = [[record["symbol"], record["row_sha256"]] for record in records] + ([["ZZZ", "0" * 64]] if extra_identity else [])
        inputs: dict[str, Any] = {"run_key": run_key, "market": market, "as_of": instant.isoformat(), "source": official.SOURCE_V3_2_SHADOW, "source_version": SOURCE_VERSION,
                                  "price_pin": {"mode": "explicit", "requested_at": "x", "resolved_publication_id": publication_id or self.pins[market]["publication_id"]},
                                  "catalogue_pin": {"mode": "explicit", "requested_at": "x", "resolved_snapshot_id": "catalogue-1"},
                                  "manifest": {"session_date": (session_date or day).isoformat(),
                                               "engine": {"implementation_file_sha256": engine or ENGINE, "implementation_object_sha256": objects or OBJECTS},
                                               "price_vintage": {}, "sources": [{"role": "catalogue", "market": market, "classification_sha256": catalogue, "rows": 18},
                                                                                {"role": "EODHD_FUNDAMENTALS", "symbol_sha256": "s" * 16}]}}
        if supersedes:
            inputs["supersedes"] = supersedes
        screen = {symbol: {"security_type": "Stock", "close": self.closes[symbol][day], "price_session": day.isoformat(),
                           "market_cap": 1e8 if symbol in self.small_caps else 5e9, "dollar_volume_median_20": 1e8 + index,
                           "split_adjusted_dollar_volume_median_20": 1e6 + index}
                  for index, symbol in enumerate(sorted(upsides))}
        outputs = {"summary": {"evaluated": len(records) + 1, "with_internal_tp": len(records), "not_evaluable": {"statement_vintages_missing": 2},
                               "statements": {"mode": statements, "table_present": True, "basis": {"statement_vintages": len(records) + 1},
                                              "coverage": {"covered": covered, "covered_in_catalogue": 16 if covered_in_catalogue is None else covered_in_catalogue,
                                                           "covered_without_rows_by_T": 0}},
                               "price_basis_evidence": {"symbols_read": len(records) + 3}},
                   "prediction_identities": identities, "screen": screen, "catalogue_counts": {"rows": len(records) + 3, "stocks": stocks or len(records)},
                   "rows": {symbol: {"models": {"own_history": {"tp": 1.0}} if index % 3 else {"peer_comps": {"tp": 1.0}}} for index, symbol in enumerate(sorted(upsides))}}
        self.database.save_analysis_snapshot(backtest.RUN_ANALYSIS_TYPE, f"{market}_PIT_{run_key[:16]}", "mv-pit", inputs, outputs, published, snapshot_id=cycle_id)
        assert self.database.insert_valuation_predictions(records) == len(records)
        return {"as_of": instant.isoformat(), "session_date": day.isoformat(), "market": market, "run_key": run_key, "cycle_id": cycle_id, "idempotent": False,
                "reused": False, "evaluated": len(records) + 1, "records": len(records), "not_evaluable": {"statement_vintages_missing": 2}}

    def replaced(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        return [entry if (old["market"], old["session_date"]) == (entry["market"], entry["session_date"]) else old for old in self.entries]

    def manifest(self, entries: list[dict[str, Any]] | None = None, **changes: Any) -> dict[str, Any]:
        return _manifest(self.entries if entries is None else entries, self.pins, **changes)

    def service(self) -> backtest.PitBacktestReportService:
        return backtest.PitBacktestReportService(backtest.ReadOnlyStore(self.database), settings=_settings())  # type: ignore[arg-type]

    def report(self, manifest: dict[str, Any] | None = None, **binding: Any) -> dict[str, Any]:
        service = self.service()
        bound = binding or {"prereg_sha256": "f" * 64, "code_pins": accuracy.pins_of(backtest.code_fingerprint())}
        receipt = service.report(manifest or self.manifest(), **bound)
        assert service.http is not None and service.http.calls == 0  # never the network
        assert not any(symbol in json.dumps(receipt) for _m, symbol in self.names)  # aggregates only
        if receipt["payload"]["verdict"]["status"] == "VOID":  # S3: a void reading read no label and published no statistic
            assert service.labels_read == 0 and receipt["payload"]["horizons"] is None and receipt["payload"]["descriptive"] is None
        return receipt


def _positive(rng: random.Random, k: int, executable: dict[str, float], total: dict[str, float], z: dict[str, float]) -> dict[str, float]:
    return {s: max(-0.5, min(0.5, 2.0 * value + rng.gauss(0.0, 0.1))) for s, value in executable.items()}


def _zero(rng: random.Random, k: int, executable: dict[str, float], total: dict[str, float], z: dict[str, float]) -> dict[str, float]:
    return {s: max(-0.5, min(0.5, rng.gauss(0.0, 0.1))) for s in executable}


def _negative(rng: random.Random, k: int, executable: dict[str, float], total: dict[str, float], z: dict[str, float]) -> dict[str, float]:
    return {s: max(-0.5, min(0.5, -2.0 * value + rng.gauss(0.0, 0.1))) for s, value in executable.items()}


def test_a_true_positive_ic_passes_and_the_receipt_is_aggregate_deterministic_and_complete(small: None) -> None:
    store = Synthetic(_positive)
    receipt = store.report()
    payload = receipt["payload"]
    assert receipt["schema"] == backtest.SCHEMA_VERSION and receipt["payload_sha256"] == official.canonical_sha256(payload) and payload["protocol"] == backtest.protocol()
    decided = payload["verdict"]
    assert decided["status"] == "PASS" and decided["reasons"] == [] and decided["blocks"] == 12 and decided["horizon_sessions"] == 10
    assert decided["ic_estimate"] == payload["horizons"]["10"]["ic_executable"]["blocks"]["estimate"] > 0.5 and decided["ic_p_greater"] < 1e-6
    assert decided["halves"]["first"] > 0 and decided["halves"]["second"] > 0 and payload["halves"]["ic_executable"]["per_half"] == 6
    assert payload["persistence"]["blocks"] == 4 and payload["persistence"]["p_greater"] < 0.01 and decided["persistence_p_greater"] == payload["persistence"]["p_greater"]
    assert decided["coverage_records_share"] == 1.0 and decided["coverage_screened_names_median"] == 30.0
    assert payload["grid"]["status"] == "PREREG" and payload["grid"]["expected_sessions"] == len(store.grid_sessions) == 58
    assert payload["runs"]["status"] == {"current": 116} and payload["runs"]["incomplete"] == 0 and payload["runs"]["producer"]["uniform"] is True
    assert payload["runs"]["producer"]["engine_files"] == ENGINE and payload["runs"]["producer"]["source_versions"] == {SOURCE_VERSION: 116}
    assert payload["runs"]["catalogues"] == {"NASDAQ": {"classification_hashes": 1, "covered_in_catalogue_values": 1},
                                             "NYSE": {"classification_hashes": 1, "covered_in_catalogue_values": 1}}
    assert payload["runs"]["producer"]["engine_objects"] == OBJECTS and payload["screen"]["volume_basis"] == "as_traded"
    assert payload["records"]["read"] == 58 * 30 and payload["records"]["observations"] == 58 * 30 and payload["records"]["refused"] == {}
    assert payload["records"]["cohort"] == {"retrospective": 58 * 30}  # every PIT record is retrospective: counted, never filtered
    assert payload["screen"]["screened"] == 58 * 30 and payload["screen"]["removed_by_rule"] == {} and payload["screen"]["removed_share"]["max"] == 0.0
    primary = payload["horizons"]["10"]
    assert primary["attrition_executable"] == {"eligible": 1740, "rate": 0.0, "unavailable": 0, "by_cause": {}} and primary["decile_spread_executable"]["blocks"]["estimate"] > 0
    assert payload["names_per_session"]["executable_h_primary"] == {"n": 58, "min": 30.0, "median": 30.0, "max": 30.0} and payload["realized_sd_per_session"] > 0
    descriptive = payload["descriptive"]
    assert descriptive["unscreened"]["10"]["ic_executable"]["blocks"]["estimate"] == pytest.approx(decided["ic_estimate"])  # nothing screened out here
    assert all(descriptive["per_exchange"][m]["blocks"]["estimate"] > 0.3 for m in ("NASDAQ", "NYSE")) and descriptive["within_exchange_rank_ic"]["blocks"]["estimate"] > 0.3
    assert set(descriptive["ic_by_year"]) == {"2025"} and descriptive["ic_by_year"]["2025"]["sessions"] == 58
    us = payload["coverage"]["US"]
    assert (us["runs"], us["evaluated"], us["records"], us["catalogue_names"], us["catalogue_stocks"], us["not_evaluable"]) == \
        (116, 116 * 16, 1740, 116 * 18, 1740, {"statement_vintages_missing": 232})
    assert us["history_model_active"] == 58 * 20 and us["history_model_share"] == pytest.approx(20 * 58 / (116 * 16)) and us["records_share"] == 1.0
    assert us["history_model_share_per_session"]["n"] == 58 and payload["coverage"]["NASDAQ"]["runs"] == 58
    assert payload["label_vintages"]["NASDAQ"]["publication_id"] == store.pins["NASDAQ"]["publication_id"] and payload["code_binding"]["status"] == "BOUND"
    first_cut = panel._utc(store.pins["NASDAQ"]["available_at"]) + timedelta(microseconds=1)  # NASDAQ published a minute before NYSE
    assert first_cut < panel._utc(store.pins["NYSE"]["available_at"]) and payload["label_cut"] == first_cut.isoformat()  # maturity by the EARLIER publication
    assert payload["manifest"]["manifest_sha256"] == store.manifest()["manifest_sha256"] and payload["anchor"] == store.grid_sessions[0].isoformat()
    again = store.report()
    assert again["payload_sha256"] == receipt["payload_sha256"]  # a function of (manifest, store, code): the same look reproduces the same hash


def test_a_zero_ic_fails_and_a_negative_ic_is_negative(small: None) -> None:
    zero = Synthetic(_zero, seed=12).report()["payload"]["verdict"]
    assert zero["status"] == "FAIL" and abs(zero["ic_estimate"]) < 0.1 and zero["ic_p_greater"] > 0.05 and zero["ic_p_less"] > 0.05
    assert any(reason.startswith("ic_executable_not_significant") for reason in zero["reasons"])
    negative = Synthetic(_negative, seed=13).report()["payload"]["verdict"]
    assert negative["status"] == "NEGATIVE" and negative["ic_estimate"] < -0.5 and negative["reasons"][0].startswith("ic_executable_negative:p_less=")


def test_halves_that_disagree_fail_even_when_the_whole_is_significant(small: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backtest, "PERSISTENCE_BLOCK_SESSIONS", 10)  # persistence on the same blocks (factor 1.14): only the halves can fail here

    def rule(rng: random.Random, k: int, executable: dict[str, float], total: dict[str, float], z: dict[str, float]) -> dict[str, float]:
        weight = 2.0 if k < 30 else -0.1  # blocks 0–5 (grid instants 0–29) strongly right, blocks 6–11 slightly wrong
        return {s: max(-0.5, min(0.5, weight * value + rng.gauss(0.0, 0.1))) for s, value in executable.items()}

    payload = Synthetic(rule, seed=14).report()["payload"]
    decided = payload["verdict"]
    assert decided["blocks"] == 12 and decided["ic_estimate"] >= backtest.IC_MIN and decided["ic_p_greater"] <= backtest.ALPHA
    assert decided["halves"]["first"] > 0.5 and decided["halves"]["second"] < 0 and payload["horizons"]["10"]["decile_spread_executable"]["blocks"]["estimate"] > 0
    assert decided["persistence_p_greater"] <= backtest.ALPHA
    assert decided["status"] == "FAIL" and decided["reasons"] == [f"ic_executable_second_half_not_positive:{decided['halves']['second']}"]


def test_a_signal_that_does_not_persist_over_longer_blocks_fails_the_co_condition(small: None) -> None:
    def rule(rng: random.Random, k: int, executable: dict[str, float], total: dict[str, float], z: dict[str, float]) -> dict[str, float]:
        weight = 2.0 if (2 * k) // 30 in (0, 2) else 0.15  # strong in persistence blocks 0 and 2, faint in 1 and 3: both halves positive
        return {s: max(-0.5, min(0.5, weight * value + rng.gauss(0.0, 0.1))) for s, value in executable.items()}

    payload = Synthetic(rule, seed=22).report()["payload"]
    decided = payload["verdict"]
    assert decided["ic_p_greater"] <= backtest.ALPHA and decided["halves"]["first"] > 0 and decided["halves"]["second"] > 0 and decided["blocks"] == 12
    assert payload["persistence"]["blocks"] == 4 and payload["persistence"]["p_greater"] > backtest.ALPHA
    assert decided["status"] == "FAIL" and decided["reasons"] == [f"ic_executable_not_persistent:p_greater_63={payload['persistence']['p_greater']}>{backtest.ALPHA}"]


def test_a_signal_seen_only_the_day_after_t_is_not_an_executable_signal(small: None) -> None:
    """The upside names the jump on the session after T: the total return T → T+h sees it (IC strongly positive), the
    executable return from the close of T + 1 does not — the verdict reads the executable one and fails."""
    def rule(rng: random.Random, k: int, executable: dict[str, float], total: dict[str, float], z: dict[str, float]) -> dict[str, float]:
        return {s: 0.1 * z[s] for s in executable}

    payload = Synthetic(rule, seed=15, jump=0.05).report()["payload"]
    primary, decided = payload["horizons"]["10"], payload["verdict"]
    assert primary["ic"]["blocks"]["estimate"] > 0.2 and primary["ic"]["blocks"]["p_greater"] < 1e-4  # the descriptive IC on r would pass
    assert decided["ic_estimate"] == primary["ic_executable"]["blocks"]["estimate"] and abs(decided["ic_estimate"]) < 0.1
    assert decided["status"] == "FAIL" and decided["ic_p_greater"] > backtest.ALPHA


def test_attrition_above_the_cap_is_unmeasured_and_fewer_than_twelve_blocks_fail(small: None) -> None:
    dropped = {symbol: 40 for _m, symbol in NAMES[:4] + NAMES[15:19]}  # eight names lose every bar from session 40 on
    payload = Synthetic(_positive, seed=16, drop_from=dropped).report()["payload"]
    attrition = payload["horizons"]["10"]["attrition_executable"]
    assert attrition["rate"] > backtest.ATTRITION_CAP and ("missing_bar" in json.dumps(attrition["by_cause"]) or "adjustment_unknown" in json.dumps(attrition["by_cause"]))
    assert payload["verdict"]["status"] == "UNMEASURED" and payload["verdict"]["reasons"][0].startswith("attrition_above_cap:")
    short = Synthetic(_positive, seed=17, count=100).report()["payload"]
    assert short["grid"]["status"] == "PREREG" and short["verdict"]["blocks"] == 9
    assert short["verdict"]["status"] == "FAIL" and short["verdict"]["reasons"] == ["blocks_below_min:9<12"]


def test_the_decisory_cross_section_is_the_point_in_time_screen_and_the_coverage_floor_measures_it(small: None, monkeypatch: pytest.MonkeyPatch) -> None:
    small_caps = frozenset([f"N{k:02d}" for k in range(5)] + [f"N{k:02d}" for k in range(20, 25)])  # five per exchange too small at T

    def rule(rng: random.Random, k: int, executable: dict[str, float], total: dict[str, float], z: dict[str, float]) -> dict[str, float]:
        return {s: max(-0.5, min(0.5, (-4.0 if s in small_caps else 2.0) * value + rng.gauss(0.0, 0.1))) for s, value in executable.items()}

    store = Synthetic(rule, seed=23, names=40, small_caps=small_caps)
    payload = store.report()["payload"]
    decided = payload["verdict"]
    assert payload["screen"]["removed_by_rule"] == {"market_cap_below_min": 10 * 58} and payload["screen"]["screened"] == 30 * 58
    assert payload["screen"]["per_session"][0] == {"session": store.grid_sessions[0].isoformat(), "records": 40, "screened": 30, "removed_share": 0.25}
    assert payload["horizons"]["10"]["observations_executable"]["n"] == 30 * 58  # the screened set decides
    unscreened = payload["descriptive"]["unscreened"]["10"]["ic_executable"]["blocks"]["estimate"]
    assert decided["status"] == "PASS" and unscreened < decided["ic_estimate"] - 0.2  # the small caps (anti-signal) only move the descriptive IC
    persistence = payload["persistence"]["estimate"]
    assert abs(persistence - decided["ic_estimate"]) < 0.1 and persistence > unscreened + 0.2  # the persistence co-condition reads the SCREENED set too
    assert decided["coverage_screened_names_median"] == 30.0
    # the floor: too few screened names per session, or too few records per catalogue stock → UNMEASURED
    monkeypatch.setattr(backtest, "COVERAGE_MIN_SCREENED_NAMES", 31)
    assert store.report()["payload"]["verdict"]["reasons"] == ["coverage_screened_names_below_floor:30.0<31"]
    monkeypatch.setattr(backtest, "COVERAGE_MIN_SCREENED_NAMES", 20)
    thin = Synthetic(_positive, seed=24, count=60)
    entries = [thin.run(entry["market"], date.fromisoformat(entry["session_date"]), {s: 0.0 for m, s in thin.names if m == entry["market"]}, stocks=100)
               for entry in thin.entries]
    cell = thin.report(thin.manifest(entries))["payload"]
    assert cell["coverage"]["US"]["records_share"] == pytest.approx(0.15) and cell["verdict"]["status"] == "UNMEASURED"
    assert cell["verdict"]["reasons"] == ["coverage_records_share_below_floor:0.15<0.6"]


def test_only_the_manifests_current_complete_runs_are_read_and_every_integrity_failure_voids_without_a_label(small: None) -> None:
    store = Synthetic(_positive, seed=18, count=60)
    first_day = store.grid_sessions[0]
    first = next(entry for entry in store.entries if entry["market"] == "NASDAQ" and entry["session_date"] == first_day.isoformat())
    # a foreign run of the same T, published BEFORE the manifest's (an old diagnostic run): its records are refused, the manifest's run stays current
    store.run("NASDAQ", first_day, {s: 0.0 for m, s in store.names if m == "NASDAQ"}, published=store.published - timedelta(hours=1))
    payload = store.report()["payload"]
    assert payload["records"]["refused"] == {"run_not_in_manifest": 15} and payload["runs"]["status"]["current"] == len(store.entries)
    assert payload["verdict"]["status"] != "VOID"

    def void(manifest: dict[str, Any] | None = None, *, of: Synthetic | None = None, **binding: Any) -> list[str]:
        cell = (of or store).report(manifest, **binding)["payload"]["verdict"]
        assert cell["status"] == "VOID" and cell["ic_estimate"] is None
        return cell["reasons"]

    assert void(store.manifest(complete=False)) == ["manifest_not_complete"]
    assert void(store.manifest(store.entries[2:])) == ["grid_sessions_missing:1"]
    assert void(store.manifest(store.entries[:-1])) == ["grid_sessions_without_both_exchanges:1"]
    assert void(store.manifest(statements="provider")) == ["manifest_statements_not_vintages", f"runs_mismatched:{len(store.entries)}", "no_current_run",
                                                           f"records_refused:no_current_run:{len(store.entries) * 15}"]  # the runs say vintages
    assert void(store.manifest(step_sessions=5)) == ["manifest_step_not_2"]
    assert void(store.manifest(grid_start="2025-01-02")) == ["manifest_grid_start_not_prereg:2025-01-02"]
    assert void(store.manifest(volume_basis={**VOLUME_BASIS, "decision": "undetermined"})) == ["manifest_volume_basis_not_decided"]
    unstated = {key: value for key, value in store.manifest().items() if key not in ("volume_basis", "manifest_sha256")}
    assert void({**unstated, "manifest_sha256": backtest.manifest_sha256(unstated)}) == ["manifest_volume_basis_not_decided"]
    other_pin = {"requested_at": "x", "NASDAQ": {**store.pins["NASDAQ"], "publication_id": "other"}, "NYSE": store.pins["NYSE"]}
    assert void(store.manifest(price_pin=other_pin))[:2] == ["label_vintage_not_the_pinned_one:NASDAQ", f"runs_mismatched:{len(store.entries) // 2}"]
    other_bars = {"requested_at": "x", "NASDAQ": {**store.pins["NASDAQ"], "bars_sha256": "0" * 64}, "NYSE": store.pins["NYSE"]}
    assert void(store.manifest(price_pin=other_bars)) == ["label_vintage_not_the_pinned_one:NASDAQ"]  # same id, another bars hash
    other_code = {**accuracy.pins_of(backtest.code_fingerprint()), "file app/valuation_pit_backtest_report.py": "0" * 64}
    assert void(prereg_sha256="f" * 64, code_pins=other_code) == ["code_mismatch", "code_mismatch:file app/valuation_pit_backtest_report.py"]
    missing = [{**entry, "run_key": "e" * 64} if entry is first else entry for entry in store.entries]
    assert void(store.manifest(missing)) == ["runs_missing:1"]
    shifted = [{**entry, "as_of": (datetime.fromisoformat(entry["as_of"]) + H).isoformat()} if entry is first else entry for entry in store.entries]
    assert "grid_t_clock_mismatch:1" in void(store.manifest(shifted))
    # each of these on its own store: a later run of an (exchange, T) changes the store's latest
    cases: list[tuple[Callable[[Synthetic], dict[str, Any]], list[str]]] = [
        (lambda s: s.run("NASDAQ", s.grid_sessions[1], {x: 0.0 for m, x in s.names if m == "NASDAQ"}, extra_identity=True), ["runs_incomplete:1"]),
        (lambda s: s.run("NYSE", s.grid_sessions[2], {x: 0.0 for m, x in s.names if m == "NYSE"}, engine={**ENGINE, "valuation_v3_engine.py": "9" * 64}),
         ["producer_not_uniform"]),
        (lambda s: s.run("NYSE", s.grid_sessions[2], {x: 0.0 for m, x in s.names if m == "NYSE"}, catalogue="d" * 64), ["catalogue_not_uniform:NYSE"]),
        (lambda s: s.run("NASDAQ", s.grid_sessions[3], {x: 0.0 for m, x in s.names if m == "NASDAQ"}, covered_in_catalogue=17),
         ["statements_table_not_stable:NASDAQ"]),
        (lambda s: s.run("NYSE", s.grid_sessions[1], {x: 0.0 for m, x in s.names if m == "NYSE"}, objects={**OBJECTS, "app.database.Database.price_bars": "9" * 64}),
         ["producer_not_uniform"]),
        (lambda s: s.run("NASDAQ", s.grid_sessions[3], {x: 0.0 for m, x in s.names if m == "NASDAQ"}, scope="targeted"), ["records_refused:scope_not_universe:15"]),
    ]
    for build, reasons in cases:
        fresh = Synthetic(_positive, seed=18, count=60)
        assert void(fresh.manifest(fresh.replaced(build(fresh))), of=fresh) == reasons
    # the live as-filed poll keeps adding the live universe's names to the store (``covered``): invisible to the grid, never a VOID
    fresh = Synthetic(_positive, seed=18, count=60)
    grown = fresh.run("NASDAQ", fresh.grid_sessions[3], {x: 0.0 for m, x in fresh.names if m == "NASDAQ"}, covered=41)
    assert fresh.report(fresh.manifest(fresh.replaced(grown)))["payload"]["verdict"]["status"] != "VOID"
    fresh = Synthetic(_positive, seed=18, count=60)
    moved = fresh.run("NYSE", fresh.grid_sessions[1], {x: 0.0 for m, x in fresh.names if m == "NYSE"}, session_date=fresh.grid_sessions[2])
    cell = fresh.report(fresh.manifest(fresh.replaced(moved)))["payload"]
    assert cell["verdict"]["reasons"][0] == "runs_mismatched:1" and cell["runs"]["mismatch_reasons"] == {"session_date": 1}
    # a later run of a manifest's (exchange, T) that supersedes it: the manifest is stale, the superseded records are refused (and void)
    later = store.run("NASDAQ", first_day, {s: 0.0 for m, s in store.names if m == "NASDAQ"}, supersedes=first["run_key"])
    stale = store.report()["payload"]
    assert stale["verdict"]["reasons"] == ["runs_superseded:1", "records_refused:superseded_run:15"] and stale["records"]["refused"]["superseded_run"] == 15
    current = [later if entry is first else entry for entry in store.entries]
    assert store.report(store.manifest(current))["payload"]["runs"]["status"] == {"current": len(store.entries)}
    with pytest.raises(backtest.ManifestError):
        store.report({**store.manifest(), "grid": []})  # the hash no longer recomputes


def test_one_record_per_name_and_session_across_the_exchanges_and_a_vintage_that_is_not_the_backfill(small: None, monkeypatch: pytest.MonkeyPatch) -> None:
    store = Synthetic(_positive, seed=25, count=60)
    day = store.grid_sessions[0]
    twin = store.run("NYSE", day, {**{s: 0.0 for m, s in store.names if m == "NYSE"}, "N00": 0.1})  # N00 is a NASDAQ name: also in the NYSE run of that T
    payload = store.report(store.manifest(store.replaced(twin)))["payload"]
    assert payload["records"]["refused"] == {"duplicate_across_exchanges": 1, "run_not_in_manifest": 15}  # the replaced NYSE run's records: not in the manifest
    assert payload["verdict"]["status"] != "VOID" and payload["records"]["admissible"] == 30 * len(store.grid_sessions)  # counted, allowed: NASDAQ's record kept
    monkeypatch.setattr(backtest, "PRICE_VINTAGE_FROM_LATEST", date(2016, 12, 1))  # the synthetic 2025 vintage is not a 120-month backfill
    assert store.report(store.manifest(store.replaced(twin)))["payload"]["verdict"]["reasons"] == ["price_vintage_not_120_months:NASDAQ",
                                                                                                 "price_vintage_not_120_months:NYSE"]


def test_the_cli_reads_the_manifest_from_stdin_binds_the_prereg_and_prints_aggregates_only(small: None, monkeypatch: pytest.MonkeyPatch,
                                                                                            capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    store = Synthetic(_positive, seed=19, count=60)
    manifest = store.manifest()
    monkeypatch.setattr(backtest, "get_settings", _settings)
    monkeypatch.setattr(backtest, "Database", lambda settings: store.database)
    monkeypatch.setenv("PGOPTIONS", "")
    monkeypatch.setenv("C3PO_BUILD_SHA", "b" * 40)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(manifest)))
    assert backtest.main(["--manifest", "-", "--prereg", str(PREREG_PATH)]) == 0
    out = capsys.readouterr().out
    receipt = json.loads(out)
    payload = receipt["payload"]
    assert out.count("\n") == 1 and set(receipt) == {"schema", "payload", "payload_sha256", "provenance"} and receipt["payload_sha256"] == official.canonical_sha256(payload)
    assert payload["prereg_sha256"] == hashlib.sha256(PREREG_PATH.read_bytes()).hexdigest() and payload["code"]["build_sha"] == "b" * 40
    assert payload["code_binding"]["status"] == "BOUND" and payload["manifest"]["manifest_sha256"] == manifest["manifest_sha256"]
    assert payload["verdict"]["status"] == "FAIL" and payload["verdict"]["reasons"][0] == "blocks_below_min:5<12"  # 60 sessions: five blocks of 10
    assert not any(symbol in out for _m, symbol in store.names) and backtest.READ_ONLY_PGOPTION in __import__("os").environ["PGOPTIONS"]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert backtest.main(["--manifest", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["payload"]["verdict"]["reasons"] == ["code_unbound", "prereg_not_given"]
    path.write_text(json.dumps({**manifest, "statements": "auto"}), encoding="utf-8")
    with pytest.raises(SystemExit):
        backtest.main(["--manifest", str(path)])  # the hash does not recompute: nothing read
    with pytest.raises(SystemExit):
        backtest.main(["--manifest", str(tmp_path / "absent.json")])
    monkeypatch.setattr(sys, "stdin", io.StringIO(" " * (backtest.MAX_MANIFEST_BYTES + 10)))
    with pytest.raises(SystemExit):
        backtest.main(["--manifest", "-"])  # a manifest larger than the cap is refused before anything is read


def test_a_grid_that_cannot_start_at_the_pre_registered_session_is_void_and_the_compaction_is_lossless(small: None, monkeypatch: pytest.MonkeyPatch) -> None:
    store = Synthetic(_positive, seed=20, count=60)
    full = store.report()
    monkeypatch.setattr(backtest, "_compact", lambda row: dict(row))  # every field of the observation kept
    assert store.report()["payload"]["horizons"] == full["payload"]["horizons"] and store.report()["payload_sha256"] == full["payload_sha256"]
    monkeypatch.setattr(backtest, "_compact", backtest._compact)
    monkeypatch.setattr(backtest, "GRID_START", date(2025, 1, 2))  # the vintage holds no 3 sessions before it: the grid cannot start there
    cell = store.report(store.manifest())["payload"]
    assert cell["bounds"]["starts_at_grid_start"] is False and cell["verdict"]["status"] == "VOID"
    assert cell["verdict"]["reasons"] == ["grid_start_not_prereg:2025-01-07"]


def test_the_labels_come_from_the_pinned_publication_never_a_later_republication(small: None) -> None:
    store = Synthetic(_positive, seed=21, count=60)
    pinned = store.report()["payload"]
    store.publish(store.published + timedelta(days=2), scale=2.0)  # a later republication of both exchanges, every close doubled: not the grid's pin
    again = store.report()["payload"]
    assert again["label_vintages"] == pinned["label_vintages"] and again["horizons"] == pinned["horizons"] and again["verdict"] == pinned["verdict"]
    assert pinned["horizons"]["10"]["attrition_executable"]["rate"] == 0.0  # the pinned publication's closes are the records' prices: the basis holds
