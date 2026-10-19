"""PREREG_VALUATION_DECISOR_V1 rev 2 — the read-only realized-accuracy report: the metric math pinned on synthetic
numbers (ranks, deciles, Student t and its inverse, batch means with the overlap inflation, Newey–West, the pro-rated
log-errors, the executable return, the verdict order), the design simulation the prereg's power table comes from, the
binding of the code to the prereg (the pins the prereg lists ARE the code at HEAD), the service pinned on the in-memory
double with synthetic records and synthetic bars (never the network, never a real database, never a writer) — a
noiseless store and a NOISY one whose real p-values and pending block are recomputed here by hand —, the CLI by its
stdout and the workflow's verifier by running its own script."""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

from app import valuation_accuracy_report as report
from app import valuation_official as official
from app import valuation_panel as panel
from app import valuation_price_history as series
from app.config import Settings
from app.database import Database
from app.market_data.eodhd import EodhdClient

UTC = timezone.utc
H = timedelta(hours=1)
ROOT = Path(__file__).resolve().parents[3]
PREREG_PATH = ROOT / "c3po" / "docs" / "PREREG_VALUATION_DECISOR_V1.md"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "valuation-readonly-report.yml"


# ------------------------------------------------------------------ pure statistics
def test_student_t_tail_and_its_inverse_match_tabulated_quantiles() -> None:
    # two-sided 5 % critical values: df=1 12.706, df=3 3.182, df=4 2.776, df=11 2.201; normal 1.960
    for t, df in ((12.706204736174707, 1), (3.182446305284263, 3), (2.7764451051977987, 4), (2.200985160082949, 11)):
        assert report.student_t_sf(t, df) == pytest.approx(0.025, abs=1e-9)
        assert report.student_t_sf(-t, df) == pytest.approx(0.975, abs=1e-9)
        assert report.student_t_isf(0.025, df) == pytest.approx(t, abs=1e-8)
    assert report.student_t_sf(1.959963984540054, 1e8) == pytest.approx(0.025, abs=1e-6)
    assert report.student_t_sf(0.0, 4) == 0.5
    assert report.student_t_sf(7.173182219782511, 4) == pytest.approx(0.001, abs=1e-9)
    for alpha in (report.ALPHA_INTERIM, report.ALPHA_FINAL, report.ALPHA_HARM):
        for df in (4, 11, 23):
            assert report.student_t_sf(report.student_t_isf(alpha, df), df) == pytest.approx(alpha, abs=1e-10)
    with pytest.raises(ValueError):
        report.student_t_sf(1.0, 0)
    with pytest.raises(ValueError):
        report.student_t_isf(0.5, 4)


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
         consensus_status: str | None = None, horizon_text: str = "12m", status: str | None = None, missing: tuple[int, ...] = ()) -> dict[str, Any]:
    consensus_status = consensus_status or ("present" if consensus_tp is not None else "absent")  # the panel's status: present implies a tp
    horizons = {str(h): {"status": "labelled", "eligible": True, "realized": value, "e_source": 0.0} for h, value in realized.items()}
    horizons.update({str(h): {"status": "missing_bar", "eligible": True, "realized": None, "e_source": None} for h in missing})
    return {"symbol": "X", "session": "2026-03-02", "tp": tp, "price": price, "adjustment": adjustment, "close_at_session": close,
            "consensus": {"tp": consensus_tp, "horizon": horizon_text}, "consensus_status": consensus_status, "producer_status": status, "horizons": horizons}


def test_point_pro_rates_the_twelve_month_tp_and_measures_both_returns_independently() -> None:
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
    # the executable pair without the label at h: the executable return is measured, the T → T+h quantities are not
    only_executable = report.point(_row(tp=120.0, price=100.0, adjustment=1.0, close=100.0, realized={1: 101.0, 22: 111.1}, missing=(21,)), 21)
    assert only_executable is not None and only_executable["return_executable"] == pytest.approx(111.1 / 101.0 - 1)
    assert only_executable["return"] is None and only_executable["e_model"] is None and only_executable["upside"] == pytest.approx(0.2)
    unlabelled = report.point(_row(tp=120.0, price=100.0, adjustment=1.0, close=100.0, realized={1: 101.0}, missing=(21, 22)), 21)
    assert unlabelled is None  # neither the label at h nor the executable pair


def test_executable_attrition_counts_the_pair_on_the_exit_target() -> None:
    def row(entry: str, exit_status: str, *, eligible: bool = True) -> dict[str, Any]:
        def label(status: str, eligible_: bool = True) -> dict[str, Any]:
            return {"status": status, "eligible": eligible_, "e_source": 0.0 if status == "labelled" else None}
        return {"horizons": {"1": label(entry), "22": label(exit_status, eligible)}}
    rows = [row("labelled", "labelled"), row("missing_bar", "labelled"), row("labelled", "no_vintage"), row("labelled", "not_yet_mature", eligible=False)]
    assert report.executable_attrition(rows, 21) == {"eligible": 3, "rate": pytest.approx(2 / 3), "unavailable": 2,
                                                     "by_cause": {"entry:missing_bar": 1, "no_vintage": 1}}
    assert report.executable_attrition([row("labelled", "not_yet_mature", eligible=False)], 21)["rate"] is None


def _blocks(estimate: float | None, *, blocks: int, p_greater: float | None = None, p_less: float | None = None, pending: int = 0) -> dict[str, Any]:
    return {"blocks": blocks, "blocks_pending": pending, "estimate": estimate, "p_greater": p_greater, "p_less": p_less}


def _primary(*, ic: dict[str, Any], eligible: int = 100, rate: float = 0.0, spread: float | None = 0.01, matured: int | None = 200,
             descriptive: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"attrition_executable": {"eligible": eligible, "rate": rate if eligible else None},
            "ic_executable": {"blocks": ic, "mature_through_index": matured},
            "decile_spread_executable": {"blocks": _blocks(spread, blocks=ic["blocks"])},
            "ic": {"blocks": descriptive or _blocks(None, blocks=0)}}


def test_verdict_follows_the_pre_registered_order_on_the_executable_ic() -> None:
    passing = _primary(ic=_blocks(0.05, blocks=6, p_greater=0.002, p_less=0.998))
    # NOT_YET_MATURE: no exit target of the holdout closed — not a reading, never an incident
    early = report.verdict({"21": _primary(ic=_blocks(None, blocks=0), eligible=0, matured=None)})
    assert early["status"] == "NOT_YET_MATURE" and early["reasons"] == ["no_target_matured"] and early["statistic"] == "ic_executable"
    # targets matured but nothing eligible (the producer published nothing): UNMEASURED — a data problem
    silent = report.verdict({"21": _primary(ic=_blocks(None, blocks=0), eligible=0, matured=3)})
    assert silent["status"] == "UNMEASURED" and silent["reasons"] == ["no_eligible_observations"]
    lossy = report.verdict({"21": _primary(ic=_blocks(0.05, blocks=6, p_greater=0.002, p_less=0.998), rate=0.2)})
    assert lossy["status"] == "UNMEASURED" and lossy["reasons"] == ["attrition_above_cap:0.2000>0.1"]
    # HARM on the executable IC with enough blocks — before INSUFFICIENT and before any pass
    harm = report.verdict({"21": _primary(ic=_blocks(-0.04, blocks=5, p_greater=0.99, p_less=0.01))})
    assert harm["status"] == "HARM" and harm["reasons"] == ["ic_executable_negative:p_less=0.010000<=0.025"]
    thin = report.verdict({"21": _primary(ic=_blocks(-0.04, blocks=4, p_greater=0.999, p_less=0.001))})
    assert thin["status"] == "INSUFFICIENT"  # four blocks are not enough for a harm verdict either
    # the T → T+h IC and the other horizons never decide: a strongly negative descriptive IC, a harmful h = 63 — still a pass
    descriptive = _primary(ic=_blocks(0.05, blocks=6, p_greater=0.002, p_less=0.998), descriptive=_blocks(-0.3, blocks=6, p_greater=1.0, p_less=1e-6))
    other = _primary(ic=_blocks(-0.04, blocks=5, p_greater=0.99, p_less=0.001))
    assert report.verdict({"21": descriptive, "63": other})["status"] == "SIGNAL_PASS"
    insufficient = report.verdict({"21": _primary(ic=_blocks(0.05, blocks=4, p_greater=0.0001, p_less=0.9999))})
    assert insufficient["status"] == "INSUFFICIENT" and insufficient["reasons"] == ["blocks_below_min:4<5"]
    interim = report.verdict({"21": passing})
    assert interim == {**interim, "status": "SIGNAL_PASS", "look": "INTERIM", "alpha": 0.003, "reasons": [], "blocks": 6, "buy_list_decisory": False, "gate": False}
    not_yet = report.verdict({"21": _primary(ic=_blocks(0.05, blocks=6, p_greater=0.01, p_less=0.99))})
    assert not_yet["status"] == "CONTINUE" and not_yet["reasons"] == ["ic_executable_not_significant:p_greater=0.01>0.003"]
    almost = report.verdict({"21": _primary(ic=_blocks(0.05, blocks=23, p_greater=0.03, p_less=0.97))})
    assert almost["status"] == "CONTINUE" and almost["look"] == "INTERIM"  # 23 blocks: still interim
    final = report.verdict({"21": _primary(ic=_blocks(0.05, blocks=24, p_greater=0.03, p_less=0.97))})
    assert final["status"] == "SIGNAL_PASS" and final["look"] == "FINAL" and final["alpha"] == 0.04
    small = report.verdict({"21": _primary(ic=_blocks(0.015, blocks=24, p_greater=0.001, p_less=0.999))})
    assert small["status"] == "INCONCLUSIVE" and small["reasons"] == ["ic_executable_below_min:0.015<0.02"]
    no_spread = report.verdict({"21": _primary(ic=_blocks(0.05, blocks=24, p_greater=0.001, p_less=0.999), spread=None)})
    assert no_spread["status"] == "INCONCLUSIVE" and no_spread["reasons"] == ["decile_spread_executable_unmeasured"]
    flat = report.verdict({"21": _primary(ic=_blocks(0.05, blocks=6, p_greater=0.0001, p_less=0.9999), spread=0.0)})
    assert flat["status"] == "CONTINUE" and flat["reasons"] == ["decile_spread_executable_not_positive"]
    deadline = report.verdict({"21": _primary(ic=_blocks(0.05, blocks=6, p_greater=0.03, p_less=0.97))}, final_by_deadline=True)
    assert deadline["status"] == "SIGNAL_PASS" and deadline["look"] == "FINAL" and deadline["alpha"] == 0.04  # the deadline makes the look final whatever B
    late = report.verdict({"21": _primary(ic=_blocks(0.05, blocks=3, p_greater=0.01, p_less=0.99))}, final_by_deadline=True)
    assert late["status"] == "INCONCLUSIVE" and late["reasons"] == ["blocks_below_min:3<5", "final_deadline"]


def test_the_design_simulation_decides_exactly_as_the_verdict() -> None:
    """simulate_design compares t with the critical values; the verdict compares p-values from batch_means_test: on
    random block means at every look the two decisions agree."""
    rng = random.Random(3)
    for _ in range(300):
        blocks = rng.randint(report.MIN_BLOCKS, report.FINAL_BLOCKS)
        means = [rng.gauss(rng.choice((-0.04, 0.0, 0.03, 0.06)), 0.05) for _b in range(blocks)]
        test = report.batch_means_test(means)
        decided = report.verdict({"21": _primary(ic={**test, "blocks": blocks, "blocks_pending": 0}, spread=0.01)})
        alpha = report.ALPHA_FINAL if blocks == report.FINAL_BLOCKS else report.ALPHA_INTERIM
        if test["t"] <= -report.student_t_isf(report.ALPHA_HARM, blocks - 1):
            expected = "HARM"
        elif test["estimate"] >= report.IC_MIN and test["t"] >= report.student_t_isf(alpha, blocks - 1):
            expected = "SIGNAL_PASS"
        else:
            expected = "INCONCLUSIVE" if blocks == report.FINAL_BLOCKS else "CONTINUE"
        assert decided["status"] == expected, (blocks, test)


def test_the_design_has_the_size_and_the_harm_rate_the_prereg_declares() -> None:
    first = report.simulate_design(0.0, 0.10, reps=3000, seed=11)
    assert first == report.simulate_design(0.0, 0.10, reps=3000, seed=11)  # deterministic for a seed
    assert 0.035 <= first["signal_pass"] <= 0.07  # the total size ≈ 0.05 (interim 0.003 at every look, final 0.04)
    assert 0.085 <= first["harm"] <= 0.13  # the cumulative false HARM ≈ 0.11, declared — not controlled at 0.025
    assert first["signal_pass"] + first["harm"] + first["inconclusive"] == pytest.approx(1.0)
    null_scale = report.simulate_design(0.0, 0.06, reps=3000, seed=11)
    assert null_scale["harm"] == pytest.approx(first["harm"], abs=0.005)  # under IC = 0 the t statistic does not depend on the sd (only IC_MIN does)
    strong = report.simulate_design(0.08, 0.06, reps=1000, seed=12)
    assert strong["signal_pass"] >= 0.99 and strong["harm"] == 0.0
    harmful = report.simulate_design(-0.05, 0.06, reps=1000, seed=13)
    assert harmful["harm"] >= 0.95 and harmful["signal_pass"] == 0.0
    with pytest.raises(ValueError):
        report.simulate_design(0.0, 0.0, reps=10, seed=1)


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
    assert constants["decisory_statistic"] == "ic_executable" and constants["prereg_revision"] == 2
    assert constants["min_blocks"] == 5 and constants["final_blocks"] == 24 and constants["final_deadline"] == "2029-01-31" and constants["adjacent_block_variance_factor"] == 1.5
    assert (constants["alpha_interim"], constants["alpha_final"], constants["alpha_harm"], constants["ic_min"]) == (0.003, 0.04, 0.025, 0.02)
    assert constants["market_groups"] == {"B3": ["B3"], "US": ["NASDAQ", "NYSE"]} and constants["buy_list_decisory"] is False and constants["gate"] is False
    assert constants["code_pins"] == {"files": list(report.PINNED_FILES), "objects": list(report.PINNED_OBJECTS)}
    assert "exchange_calendars" not in constants["calendar"]  # a version of the running code, recorded in payload.code — never a protocol constant
    assert report.label_horizons() == (1, 21, 22, 63, 64, 126, 127)
    text = PREREG_PATH.read_text(encoding="utf-8")
    for needle in ("rev 2", "h = 21", "MIN_BLOCKS = 5", "FINAL_BLOCKS = 24", "FINAL_DEADLINE = 2029-01-31", "1,5", "ALPHA_INTERIM = 0,003",
                   "ALPHA_FINAL = 0,04", "ALPHA_HARM = 0,025", "IC_MIN = 0,02", "DECISORY_STATISTIC = ic_executable", "252",
                   "VALUATION-ACCURACY-REPORT-v1", "NOT_YET_MATURE", f"DESIGN_SEED = {report.DESIGN_SEED}", f"DESIGN_REPS = {report.DESIGN_REPS}"):
        assert needle in text, needle


def test_the_prereg_pins_exactly_the_code_at_head() -> None:
    """The pins of §17 ARE this code: a change to a pinned module or object makes this fail — it voids every reading
    under the hashed prereg, so it needs a new prereg revision (new hash, new H0), never a silent edit."""
    pins = report.pins_from_prereg(PREREG_PATH.read_text(encoding="utf-8"))
    code = report.code_fingerprint()
    assert pins == report.pins_of(code), "a pinned module/object changed: PREREG_VALUATION_DECISOR_V1 needs a new revision (new hash, new H0)"
    assert len(pins) == len(report.PINNED_FILES) + len(report.PINNED_OBJECTS)
    assert report.bind_code(code, pins, prereg_sha256=hashlib.sha256(PREREG_PATH.read_bytes()).hexdigest())["status"] == "BOUND"


def test_the_code_binding_voids_any_other_code() -> None:
    code = report.code_fingerprint(build_sha="a" * 40)
    pins = report.pins_of(code)
    some = "f" * 64
    assert code["build_sha"] == "a" * 40 and set(code) == {"files", "objects", "exchange_calendars", "python", "build_sha"}
    assert report.bind_code(code, pins, prereg_sha256=some) == {"status": "BOUND", "pinned": len(pins), "reasons": []}
    assert report.bind_code(code, pins, prereg_sha256=None)["reasons"] == ["prereg_not_given"]
    assert report.bind_code(code, {}, prereg_sha256=some) == {"status": "UNBOUND", "pinned": 0, "reasons": ["no_code_pins_in_prereg"]}
    panel_pin = "file app/valuation_panel.py"
    changed = {**pins, panel_pin: "0" * 64}
    assert report.bind_code(code, changed, prereg_sha256=some) == {"status": "MISMATCH", "pinned": len(pins), "reasons": [f"code_mismatch:{panel_pin}"]}
    extra = {**pins, "object app.database.Database.insert_valuation_predictions": "1" * 64}
    assert report.bind_code(code, extra, prereg_sha256=some)["reasons"] == ["code_not_fingerprinted:object app.database.Database.insert_valuation_predictions"]
    fewer = {key: value for key, value in pins.items() if key != panel_pin}
    assert report.bind_code(code, fewer, prereg_sha256=some)["reasons"] == [f"code_not_pinned:{panel_pin}"]
    text = "# doc\nfile app/a.py " + "1" * 64 + "\n  object app.b.c " + "2" * 64 + "  \nfile app/a.py " + "1" * 64 + "\nnot a pin " + "3" * 64 + "\n"
    assert report.pins_from_prereg(text) == {"file app/a.py": "1" * 64, "object app.b.c": "2" * 64}
    with pytest.raises(ValueError, match="twice"):
        report.pins_from_prereg(text + "file app/a.py " + "4" * 64 + "\n")
    assert report.render_pins(code).splitlines() == sorted(f"{key} {value}" for key, value in pins.items())


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


def _bound() -> dict[str, Any]:
    """A binding of the running code to a prereg that pins exactly it (what the deployed prereg does)."""
    return {"prereg_sha256": "f" * 64, "code_pins": report.pins_of(report.code_fingerprint())}


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
    receipt = service.report(cut=cut, holdout_start=sessions[4], **_bound())
    payload = receipt["payload"]
    assert receipt["payload_sha256"] == official.canonical_sha256(payload) and payload["protocol"] == report.protocol()
    assert payload["holdout_start"] == sessions[4].isoformat() and payload["sources"] == list(report.DEFAULT_SOURCES) and payload["market_groups"] == ["B3", "US"]
    assert payload["code"] == report.code_fingerprint() and payload["code_binding"]["status"] == "BOUND"
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
        assert cell["attrition_executable"] == {"eligible": 48, "rate": 0.0, "unavailable": 0, "by_cause": {}}
        assert cell["observations"] == {"n": 48, "names": 12, "sessions": 4, "max_share_single_name": pytest.approx(1 / 12)}
        assert cell["observations_executable"] == cell["observations"]
        assert cell["ic"]["sessions_measured"] == 4 and cell["ic"]["blocks"]["mean_per_session"] == 1.0 and cell["ic"]["blocks"]["blocks"] == 2
        assert cell["ic"]["blocks"]["se"] == 0.0 and cell["ic"]["blocks"]["t"] is None  # +1 every session: no dispersion, no test
        assert cell["ic_executable"]["blocks"]["mean_per_session"] == 1.0 and cell["ic_executable"]["labelled_without_executable_return"] == 0
        for spread in ("decile_spread", "decile_spread_executable"):
            assert cell[spread]["sessions_measured"] == 0 and cell[spread]["sessions_not_measured"] == {"below_min_names": 4}
        excess = cell["buy_list_excess"]
        assert excess["list"] == report.BUY_LIST_PROXY and excess["decisory"] is False and excess["mean_listed_per_session"] == 3.0
        expected_excess = sum((1 + growth[f"S{k:02d}"]) ** 2 - 1 for k in (9, 10, 11)) / 3 - sum((1 + g) ** 2 - 1 for g in growth.values()) / 12
        assert excess["blocks"]["mean_per_session"] == pytest.approx(expected_excess, rel=1e-6) and expected_excess > 0
        assert cell["buy_list_excess_executable"]["blocks"]["mean_per_session"] == pytest.approx(expected_excess, rel=1e-6)  # same growth from T + 1
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
    assert us["verdict"]["status"] == "INSUFFICIENT" and us["verdict"]["reasons"] == ["blocks_below_min:2<5"] and us["verdict"]["statistic"] == "ic_executable"
    # the internal source reads the same producer rows (tp = internal_tp): the same numbers here
    assert payload["results"]["US"]["official_internal_v1"]["partitions"]["holdout"]["horizons"]["2"]["ic"]["blocks"]["mean_per_session"] == 1.0
    b3 = payload["results"]["B3"]["official_blend_v1"]
    assert b3["partitions"]["holdout"]["horizons"]["2"]["ic"]["sessions_not_measured"] == {"below_min_names": 4}
    assert b3["partitions"]["holdout"]["horizons"]["2"]["log_mse_vs_random_walk"]["n"] == 12 and set(b3["vintages"]) == {"B3"}


def test_a_reading_whose_code_is_not_the_pinned_one_is_void(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_horizons(monkeypatch)
    database, cut, sessions, _ = _store()
    service = report.AccuracyReportService(report.ReadOnlyStore(database), settings=_settings())  # type: ignore[arg-type]
    pins = {**report.pins_of(report.code_fingerprint()), "file app/valuation_panel.py": "0" * 64}  # the panel changed after the hash
    payload = service.report(cut=cut, holdout_start=sessions[4], prereg_sha256="f" * 64, code_pins=pins)["payload"]
    assert payload["code_binding"] == {"status": "MISMATCH", "pinned": len(pins), "reasons": ["code_mismatch:file app/valuation_panel.py"]}
    for group in ("B3", "US"):
        for source in report.DEFAULT_SOURCES:
            assert payload["results"][group][source]["verdict"] == {"status": "VOID", "reasons": ["code_mismatch", "code_mismatch:file app/valuation_panel.py"],
                                                                   "gate": False}
    unbound = service.report(cut=cut, holdout_start=sessions[4])["payload"]  # no prereg at all: nothing to bind to
    assert unbound["results"]["US"]["official_blend_v1"]["verdict"]["reasons"] == ["code_unbound", "prereg_not_given"]
    # the measurements are still published (the instrument is visible); only the verdict is void
    assert unbound["results"]["US"]["official_blend_v1"]["partitions"]["holdout"]["horizons"]["2"]["ic"]["blocks"]["blocks"] == 2


def test_the_receipt_is_deterministic_and_independent_of_the_store_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_horizons(monkeypatch)
    database, cut, sessions, _ = _store()
    first = report.AccuracyReportService(report.ReadOnlyStore(database), settings=_settings()).report(cut=cut, holdout_start=sessions[4], **_bound())  # type: ignore[arg-type]
    again = report.AccuracyReportService(report.ReadOnlyStore(database), settings=_settings()).report(cut=cut, holdout_start=sessions[4], **_bound())  # type: ignore[arg-type]
    random.Random(7).shuffle(database._valuation_predictions)  # the same store, its rows permuted (lists in the double): the same hash
    random.Random(11).shuffle(database._price_bars)
    shuffled = report.AccuracyReportService(report.ReadOnlyStore(database), settings=_settings()).report(cut=cut, holdout_start=sessions[4], **_bound())  # type: ignore[arg-type]
    assert first["payload_sha256"] == again["payload_sha256"] == shuffled["payload_sha256"]
    # a store built in the reverse order: the same numbers; only the vintages' ids (uuid4 of another store) differ
    permuted, _, _, _ = _store(permute=True)
    mirrored = report.AccuracyReportService(report.ReadOnlyStore(permuted), settings=_settings()).report(cut=cut, holdout_start=sessions[4], **_bound())  # type: ignore[arg-type]
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
        cut=blind, groups=("US",), sources=("official_blend_v1",), holdout_start=sessions[4], **_bound())["payload"]["results"]["US"]["official_blend_v1"]
    development = cell["partitions"]["development"]["horizons"]["2"]
    assert development["attrition"]["by_cause"] == {"no_vintage": 48} and development["attrition"]["rate"] == 1.0
    holdout = cell["partitions"]["holdout"]["horizons"]["2"]
    assert holdout["eligible"] == 24 and holdout["ineligible"] == {"not_yet_mature": 24}  # sessions 4 and 5: their targets (6, 7) closed before the cut
    # the executable pair matures one session later: only session 4 (exit target 7) — all unavailable without a vintage
    assert holdout["attrition_executable"] == {"eligible": 12, "rate": 1.0, "unavailable": 12, "by_cause": {"no_vintage": 12}}
    assert holdout["ic_executable"]["mature_through_index"] == 0 and holdout["ic"]["mature_through_index"] == 1
    assert cell["verdict"]["status"] == "UNMEASURED" and cell["verdict"]["reasons"] == ["attrition_above_cap:1.0000>0.1"]


def test_not_yet_mature_is_its_own_status_and_matured_silence_is_unmeasured(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_horizons(monkeypatch)
    database, cut, sessions, _ = _store()
    service = report.AccuracyReportService(report.ReadOnlyStore(database), settings=_settings())  # type: ignore[arg-type]
    # the first weeks after H0: holdout records exist, no exit target T + 3 has closed — NOT_YET_MATURE, never an incident
    early = series.session_close("NASDAQ", sessions[5]) + 2 * H
    cell = service.report(cut=early, groups=("US",), sources=("official_blend_v1",), holdout_start=sessions[4], **_bound())["payload"]["results"]["US"]["official_blend_v1"]
    assert cell["partitions"]["holdout"]["observations"] == 24 and cell["partitions"]["holdout"]["horizons"]["2"]["attrition_executable"]["eligible"] == 0
    assert cell["verdict"]["status"] == "NOT_YET_MATURE" and cell["verdict"]["reasons"] == ["no_target_matured"]
    # every target matured but the window holds no holdout record (a producer that published nothing): UNMEASURED
    until = series.session_close("NASDAQ", sessions[4])
    silent = service.report(cut=cut, groups=("US",), sources=("official_blend_v1",), until=until, holdout_start=sessions[4], **_bound())
    cell = silent["payload"]["results"]["US"]["official_blend_v1"]
    assert cell["partitions"]["holdout"]["observations"] == 0
    assert cell["verdict"]["status"] == "UNMEASURED" and cell["verdict"]["reasons"] == ["no_eligible_observations"]


NOISY_NAMES = [("NASDAQ" if k < 15 else "NYSE", f"N{k:02d}") for k in range(30)]


def _noisy_store(seed: int) -> tuple[Database, list[date], dict[date, dict[str, int]], dict[str, dict[date, float]]]:
    """US: thirty names (fifteen NASDAQ, fifteen NYSE) × nineteen XNYS sessions from 2026-03-02 with seeded random daily
    moves (±3 %); records of ``official_blend_v1`` on the first sixteen sessions (four development, twelve holdout).
    At every session the names' upsides are ``0.01 · rank − 0.12`` (0.01 apart: rounding never ties them) with the
    rank of a NOISY copy (+ N(0, 0.15)) of the executable return ``close(T + 3) / close(T + 1) − 1`` (h = 2): a real, imperfect
    signal. One vintage per market is published after session 17 closed; ``_publish`` adds the later one. Returns the
    store, the calendar, the upside rank by session and name, and the closes."""
    rng = random.Random(seed)
    calendar = [d for d in (series.sessions_after("NASDAQ", date(2026, 3, 2), j)[0] for j in range(19)) if d is not None]
    assert len(calendar) == 19
    closes: dict[str, dict[date, float]] = {}
    for _market, symbol in NOISY_NAMES:
        level, path = 100.0, {}
        for day in calendar:
            level *= 1.0 + rng.uniform(-0.03, 0.03)
            path[day] = round(level, 6)
        closes[symbol] = path
    ranks: dict[date, dict[str, int]] = {}
    records: list[dict] = []
    for j, session in enumerate(calendar[:16]):
        noisy = {symbol: closes[symbol][calendar[j + 3]] / closes[symbol][calendar[j + 1]] - 1.0 + rng.gauss(0.0, 0.15) for _m, symbol in NOISY_NAMES}
        ranks[session] = {symbol: rank for rank, symbol in enumerate(sorted(noisy, key=lambda name: noisy[name]))}
        instant = series.session_close("NASDAQ", session) + H
        for market, symbol in NOISY_NAMES:
            price = closes[symbol][session]
            upside = 0.01 * ranks[session][symbol] - 0.12
            records.append(_record(market, symbol, tp=price * (1.0 + upside), price=price, instant=instant, source="official_blend_v1",
                                   status="full_match" if ranks[session][symbol] >= 25 else "watchlist"))
    database = Database(_settings())
    assert database.insert_valuation_predictions(records) == len(records)
    _publish(database, calendar, closes, through=calendar[17])
    return database, calendar, ranks, closes


def _publish(database: Database, calendar: list[date], closes: dict[str, dict[date, float]], *, through: date) -> datetime:
    """A vintage of both US markets with every bar through ``through``, published two hours after it closed; returns a
    cut one hour later."""
    bars = {f"{symbol}.US": [{"date": day.isoformat(), "close": closes[symbol][day], "adjusted_close": closes[symbol][day], "volume": 1.0} for day in calendar]
            for _m, symbol in NOISY_NAMES}
    at = series.session_close("NASDAQ", through) + 2 * H
    for offset, market in enumerate(("NASDAQ", "NYSE")):
        _producer(database, bars).persist_run(market, start=calendar[0], end=through, symbols=[s for m, s in NOISY_NAMES if m == market],
                                              now=at + timedelta(minutes=offset))
    return at + H


def _spearman_without_ties(xs: list[float], ys: list[float]) -> float:
    rank_x = {index: rank for rank, index in enumerate(sorted(range(len(xs)), key=lambda i: xs[i]))}
    rank_y = {index: rank for rank, index in enumerate(sorted(range(len(ys)), key=lambda i: ys[i]))}
    n = len(xs)
    return 1.0 - 6.0 * sum((rank_x[i] - rank_y[i]) ** 2 for i in range(n)) / (n * (n * n - 1))


def _by_hand(calendar: list[date], ranks: dict[date, dict[str, int]], closes: dict[str, dict[date, float]], *, matured: int) -> dict[str, Any]:
    """The holdout's executable statistics recomputed from the construction alone: per session j (holdout index), the
    Spearman of rank vs executable return and the top-minus-bottom-decile spread (three names each); blocks of two
    sessions, complete when both sessions' exit targets closed (``j ≤ matured``); batch means with the 1.5 factor."""
    ics, spreads = [], []
    for j in range(matured + 1):
        session = calendar[4 + j]
        names = [symbol for _m, symbol in NOISY_NAMES]
        executable = [closes[s][calendar[4 + j + 3]] / closes[s][calendar[4 + j + 1]] - 1.0 for s in names]
        upside_rank = [float(ranks[session][s]) for s in names]
        assert len(set(executable)) == len(executable)  # no ties: the closed form of Spearman applies
        ics.append(_spearman_without_ties(upside_rank, executable))
        order = sorted(range(len(names)), key=lambda i: upside_rank[i])
        spreads.append(sum(executable[i] for i in order[-3:]) / 3 - sum(executable[i] for i in order[:3]) / 3)
    complete = (matured + 1) // 2

    def test(values: list[float]) -> dict[str, float]:
        means = [(values[2 * b] + values[2 * b + 1]) / 2 for b in range(complete)]
        center = sum(means) / complete
        sd = math.sqrt(sum((m - center) ** 2 for m in means) / (complete - 1))
        se = math.sqrt(1.5) * sd / math.sqrt(complete)
        return {"estimate": center, "se": se, "t": center / se, "p_greater": report.student_t_sf(center / se, complete - 1)}

    return {"blocks": complete, "pending": 1 if matured % 2 == 0 else 0, "ic": test(ics), "spread": test(spreads)}


def test_a_noisy_store_runs_real_p_values_and_a_pending_block_through_the_whole_service(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_horizons(monkeypatch)
    database, calendar, ranks, closes = _noisy_store(seed=29)
    service = report.AccuracyReportService(report.ReadOnlyStore(database), settings=_settings())  # type: ignore[arg-type]
    cut = series.session_close("NASDAQ", calendar[17]) + 3 * H  # session 17 closed (the vintage has it), session 18 not yet
    cell = service.report(cut=cut, groups=("US",), sources=("official_blend_v1",), holdout_start=calendar[4], **_bound())["payload"]["results"]["US"]["official_blend_v1"]
    holdout = cell["partitions"]["holdout"]
    assert holdout["anchor"] == calendar[4].isoformat() and holdout["sessions"] == 12 and holdout["observations"] == 360
    primary = holdout["horizons"]["2"]
    # the executable exit T + 3 of holdout session 10 is session 17 (closed); of session 11 it is 18 (not yet): matured through index 10
    assert primary["ic_executable"]["mature_through_index"] == 10 and primary["ic"]["mature_through_index"] == 11
    expected = _by_hand(calendar, ranks, closes, matured=10)
    blocks = primary["ic_executable"]["blocks"]
    assert (blocks["blocks"], blocks["blocks_pending"], blocks["blocks_empty"], blocks["sessions"], blocks["df"]) == (5, 1, 0, 10, 4)
    assert expected["blocks"] == 5 and expected["pending"] == 1
    assert blocks["estimate"] == pytest.approx(expected["ic"]["estimate"], abs=1e-12) and blocks["se"] == pytest.approx(expected["ic"]["se"], abs=1e-12)
    assert blocks["t"] == pytest.approx(expected["ic"]["t"], rel=1e-9) and blocks["p_greater"] == pytest.approx(expected["ic"]["p_greater"], rel=1e-9)
    assert 0.0 < blocks["p_greater"] < 0.5 and blocks["p_less"] == pytest.approx(1.0 - blocks["p_greater"])  # a REAL p-value, neither 0 nor None
    spread = primary["decile_spread_executable"]["blocks"]
    assert spread["blocks"] == 5 and spread["estimate"] == pytest.approx(expected["spread"]["estimate"], abs=1e-12)
    # the descriptive T → T+h IC matures one session earlier: six complete blocks, none pending
    assert (primary["ic"]["blocks"]["blocks"], primary["ic"]["blocks"]["blocks_pending"]) == (6, 0)
    assert primary["attrition_executable"] == {"eligible": 330, "rate": 0.0, "unavailable": 0, "by_cause": {}}  # 11 sessions × 30 names
    decided = cell["verdict"]
    assert (decided["blocks"], decided["blocks_pending"], decided["look"], decided["alpha"]) == (5, 1, "INTERIM", report.ALPHA_INTERIM)
    assert decided["ic_p_greater"] == blocks["p_greater"] and expected["ic"]["p_greater"] > report.ALPHA_INTERIM and expected["ic"]["estimate"] > report.IC_MIN
    assert decided["status"] == "CONTINUE" and decided["reasons"] == [f"ic_executable_not_significant:p_greater={blocks['p_greater']}>{report.ALPHA_INTERIM}"]
    # one session later (a new vintage with session 18): the pending block completes — B = 6, nothing pending, another p-value
    later = _publish(database, calendar, closes, through=calendar[18])
    cell = report.AccuracyReportService(report.ReadOnlyStore(database), settings=_settings()).report(  # type: ignore[arg-type]
        cut=later, groups=("US",), sources=("official_blend_v1",), holdout_start=calendar[4], **_bound())["payload"]["results"]["US"]["official_blend_v1"]
    blocks = cell["partitions"]["holdout"]["horizons"]["2"]["ic_executable"]["blocks"]
    expected = _by_hand(calendar, ranks, closes, matured=11)
    assert (blocks["blocks"], blocks["blocks_pending"], blocks["df"]) == (6, 0, 5) and expected["pending"] == 0
    assert blocks["p_greater"] == pytest.approx(expected["ic"]["p_greater"], rel=1e-9) and cell["verdict"]["blocks"] == 6
    # the completed block carries the p-value under the interim alpha: the same signal now passes (estimate ≥ IC_MIN, spread > 0)
    assert expected["ic"]["p_greater"] <= report.ALPHA_INTERIM and expected["ic"]["estimate"] >= report.IC_MIN and expected["spread"]["estimate"] > 0
    assert cell["verdict"]["status"] == "SIGNAL_PASS" and cell["verdict"]["reasons"] == [] and cell["verdict"]["blocks_pending"] == 0


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


def _workflow_verifier() -> str:
    """The Python the workflow runs to verify a receipt before uploading it, exactly as the workflow file carries it."""
    jobs = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))["jobs"]
    steps = [step for job in jobs.values() for step in job.get("steps", [])]
    script = next(step["run"] for step in steps if step.get("name") == "Verify the receipt and keep aggregates only")
    return script.split("<<'PY' || exit 1\n", 1)[1].split("\nPY\n", 1)[0]


def _verify(tmp_path: Path, receipt_text: str, prereg: Path, *, holdout_start: str) -> subprocess.CompletedProcess[str]:
    source = tmp_path / "stdout.json"
    source.write_text(receipt_text, encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    env = {**os.environ, "AS_OF": "2026-10-24T12:00:00-03:00", "HOLDOUT_START": holdout_start, "RUN_ID": "7", "REVISION": "c" * 40,
           "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md")}
    return subprocess.run([sys.executable, "-", str(source), str(out), str(prereg)], input=_workflow_verifier(), text=True, capture_output=True, env=env)


def test_the_cli_prints_aggregates_only_binds_the_prereg_and_the_workflow_verifies_it(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
                                                                                        tmp_path: Path) -> None:
    _small_horizons(monkeypatch)
    database, cut, sessions, _ = _store()
    monkeypatch.setattr(report, "get_settings", _settings)
    monkeypatch.setattr(report, "Database", lambda settings: database)
    monkeypatch.setenv("PGOPTIONS", "")
    monkeypatch.setenv("C3PO_BUILD_SHA", "b" * 40)
    assert report.main(["--as-of", cut.isoformat(), "--holdout-start", sessions[4].isoformat(), "--prereg", str(PREREG_PATH), "--groups", "us"]) == 0
    out = capsys.readouterr().out
    receipt = json.loads(out)
    payload = receipt["payload"]
    assert receipt["schema"] == report.SCHEMA_VERSION and receipt["payload_sha256"] == official.canonical_sha256(payload)
    assert payload["prereg_sha256"] == hashlib.sha256(PREREG_PATH.read_bytes()).hexdigest() and payload["market_groups"] == ["US"]
    assert payload["code"]["files"]["app/valuation_accuracy_report.py"] == hashlib.sha256(Path(report.__file__).read_bytes()).hexdigest()
    assert payload["code"]["build_sha"] == "b" * 40 and payload["code_binding"]["status"] == "BOUND" and set(receipt["provenance"]) == {"generated_at"}
    assert payload["results"]["US"]["official_blend_v1"]["verdict"]["status"] == "INSUFFICIENT"
    assert not any(symbol in out for symbol in ("S00", "S11", "T99", "R50")) and out.count("\n") == 1
    assert os.environ["PGOPTIONS"].endswith(report.READ_ONLY_PGOPTION)
    # the workflow's own verifier accepts this receipt against the repository's prereg, and writes the aggregates only
    verified = _verify(tmp_path, out, PREREG_PATH, holdout_start=sessions[4].isoformat())
    assert verified.returncode == 0, verified.stderr
    metadata = json.loads((tmp_path / "out" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["deployed_build_sha"] == "b" * 40 and metadata["code_pins_verified"] == len(report.PINNED_FILES) + len(report.PINNED_OBJECTS)
    assert json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))["payload_sha256"] == receipt["payload_sha256"]
    assert "INSUFFICIENT" in (tmp_path / "summary.md").read_text(encoding="utf-8")
    # a prereg without pins: the reading is VOID in the receipt, and the workflow refuses it
    bare = tmp_path / "bare.md"
    bare.write_bytes(b"pre-registration bytes\n")
    assert report.main(["--as-of", cut.isoformat(), "--holdout-start", sessions[4].isoformat(), "--prereg", str(bare), "--groups", "us"]) == 0
    void = capsys.readouterr().out
    assert json.loads(void)["payload"]["results"]["US"]["official_blend_v1"]["verdict"]["reasons"] == ["code_unbound", "no_code_pins_in_prereg"]
    refused = _verify(tmp_path, void, bare, holdout_start=sessions[4].isoformat())
    assert refused.returncode != 0 and "pins no code" in refused.stderr
    with pytest.raises(SystemExit):
        report.main(["--as-of", "2026-09-12T00:00:00"])  # naive: refused
    with pytest.raises(SystemExit):
        report.main(["--as-of", cut.isoformat(), "--holdout-start", "19/10/2026"])
    with pytest.raises(SystemExit):
        report.main(["--as-of", cut.isoformat(), "--prereg", str(tmp_path / "absent.md")])
    with pytest.raises(SystemExit):
        report.main(["--as-of", cut.isoformat(), "--groups", "B3,EU"])


def test_the_workflow_refuses_a_reading_that_is_not_valid_under_the_prereg(tmp_path: Path) -> None:
    prereg = tmp_path / "prereg.md"
    prereg.write_text("# prereg\n\n```text\nfile app/a.py " + "1" * 64 + "\nobject app.b.c " + "2" * 64 + "\n```\n", encoding="utf-8")
    prereg_sha256 = hashlib.sha256(prereg.read_bytes()).hexdigest()

    def receipt(**changes: Any) -> str:
        payload: dict[str, Any] = {"schema": report.SCHEMA_VERSION, "cut": "2026-10-24T15:00:00+00:00", "holdout_start": "2026-10-18", "prereg_sha256": prereg_sha256,
                                   "code": {"files": {"app/a.py": "1" * 64}, "objects": {"app.b.c": "2" * 64}, "build_sha": "a" * 40},
                                   "code_binding": {"status": "BOUND"},
                                   "results": {"US": {"official_blend_v1": {"verdict": {"status": "NOT_YET_MATURE"},
                                                                            "partitions": {"development": {"sessions": 3, "horizons": {}}}}}}}
        payload.update(changes)
        return json.dumps({"schema": report.SCHEMA_VERSION, "payload": payload, "payload_sha256": official.canonical_sha256(payload),
                           "provenance": {"generated_at": "2026-10-24T15:01:00+00:00"}})

    accepted = _verify(tmp_path, receipt(), prereg, holdout_start="2026-10-18")
    assert accepted.returncode == 0, accepted.stderr
    cases = {
        "the deployed code is not the pinned code (object app.b.c)": receipt(code={"files": {"app/a.py": "1" * 64}, "objects": {"app.b.c": "3" * 64}, "build_sha": "a" * 40}),
        "the deployed code is not the pinned code (object app.d)": receipt(code={"files": {"app/a.py": "1" * 64}, "objects": {"app.b.c": "2" * 64, "app.d": "4" * 64},
                                                                                "build_sha": "a" * 40}),
        "not a commit sha": receipt(code={"files": {"app/a.py": "1" * 64}, "objects": {"app.b.c": "2" * 64}, "build_sha": "development"}),
        "not the one of this workflow revision": receipt(prereg_sha256="e" * 64),
        "does not declare its code BOUND": receipt(code_binding={"status": "MISMATCH"}),
        "holdout_start is not the requested one": receipt(holdout_start="2026-10-25"),
    }
    for message, text in cases.items():
        result = _verify(tmp_path, text, prereg, holdout_start="2026-10-18")
        assert result.returncode != 0 and message in result.stderr, (message, result.stderr)
    tampered = json.loads(receipt())
    tampered["payload"]["cut"] = "2026-10-31T15:00:00+00:00"
    result = _verify(tmp_path, json.dumps(tampered), prereg, holdout_start="2026-10-18")
    assert result.returncode != 0 and "does not recompute" in result.stderr
