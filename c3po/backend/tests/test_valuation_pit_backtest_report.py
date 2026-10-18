"""PREREG_VALUATION_PIT_BACKTEST_US_V1 — the single look of the US point-in-time backtest: the verdict order on hand-built
cells (VOID → UNMEASURED → NEGATIVE → PASS → FAIL; the executable IC decides, never the T → T+h one; both halves), the
halves and the block rule (identical to the accuracy report's), the grid (T clock, bounds, anchoring), the manifest
(hash, shape, refusals), the binding of the code to the prereg, the design simulation, and the service on the in-memory
double over SYNTHETIC stores (synthetic symbols, synthetic bars, synthetic run snapshots: a true IC positive / zero /
negative, halves that disagree, a signal visible only in the day after T, attrition above the cap, fewer than 12 blocks,
and every integrity failure of a manifest: a foreign run, a superseded run, a missing run, an incomplete cycle, two
producers, a session off the grid, another statements mode, another publication, other code). Never the network."""
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
NAMES = [("NASDAQ" if k < 15 else "NYSE", f"N{k:02d}") for k in range(30)]  # synthetic symbols
SOURCE_VERSION = "pit-rerun-v1+synthetic000"
ENGINE = {name: hashlib.sha256(name.encode()).hexdigest() for name in ("valuation_v3_engine.py", "valuation_v3_inputs.py", "valuation_v3_macro.py",
                                                                       "valuation_v3_shadow.py", "valuation_pit_rerun.py")}


# ------------------------------------------------------------------ the verdict, pure
def _blocks(estimate: float | None, *, blocks: int, p_greater: float | None = None, p_less: float | None = None) -> dict[str, Any]:
    return {"blocks": blocks, "blocks_pending": 0, "estimate": estimate, "se": 0.01, "t": 1.0, "df": max(0, blocks - 1), "p_greater": p_greater, "p_less": p_less}


def _primary(*, ic: dict[str, Any], eligible: int = 100, rate: float = 0.0, spread: float | None = 0.01, descriptive: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"attrition_executable": {"eligible": eligible, "rate": rate if eligible else None},
            "ic_executable": {"blocks": ic, "mature_through_index": 300}, "decile_spread_executable": {"blocks": _blocks(spread, blocks=ic["blocks"])},
            "ic": {"blocks": descriptive or _blocks(None, blocks=0), "mature_through_index": 300}}


def _split(first: float | None = 0.05, second: float | None = 0.04) -> dict[str, Any]:
    return {"first": {"estimate": first}, "second": {"estimate": second}}


def test_the_verdict_follows_the_pre_registered_order_on_the_executable_ic() -> None:
    good = _primary(ic=_blocks(0.05, blocks=23, p_greater=0.001, p_less=0.999))
    passed = backtest.verdict(good, _split())
    assert passed["status"] == "PASS" and passed["reasons"] == [] and passed["look"] == "SINGLE" and passed["statistic"] == "ic_executable" and passed["gate"] is False
    assert backtest.verdict(good, _split(), void=["code_mismatch"]) == {**passed, "status": "VOID", "reasons": ["code_mismatch"]}
    # UNMEASURED before anything else: no eligible observation, or the executable attrition above the cap
    assert backtest.verdict(_primary(ic=_blocks(None, blocks=0), eligible=0), _split())["reasons"] == ["no_eligible_observations"]
    lossy = backtest.verdict(_primary(ic=_blocks(-0.2, blocks=23, p_greater=0.9999, p_less=0.0001), rate=0.11), _split())
    assert lossy["status"] == "UNMEASURED" and lossy["reasons"] == ["attrition_above_cap:0.1100>0.1"]
    assert backtest.verdict(_primary(ic=_blocks(0.05, blocks=23, p_greater=0.001, p_less=0.999), rate=0.10), _split())["status"] == "PASS"  # the cap is inclusive
    # NEGATIVE: the executable IC significantly below zero (one-sided 0.05)
    negative = backtest.verdict(_primary(ic=_blocks(-0.04, blocks=23, p_greater=0.99, p_less=0.01)), _split(-0.03, -0.05))
    assert negative["status"] == "NEGATIVE" and negative["reasons"] == ["ic_executable_negative:p_less=0.010000<=0.05"]
    assert backtest.verdict(_primary(ic=_blocks(-0.04, blocks=23, p_greater=0.94, p_less=0.06)), _split(-0.03, -0.05))["status"] == "FAIL"
    # FAIL lists every unmet condition of the pass
    cases = {
        "blocks_below_min:11<12": _primary(ic=_blocks(0.05, blocks=11, p_greater=0.001, p_less=0.999)),
        "ic_executable_below_min:0.015<0.02": _primary(ic=_blocks(0.015, blocks=23, p_greater=0.001, p_less=0.999)),
        "ic_executable_not_significant:p_greater=0.06>0.05": _primary(ic=_blocks(0.05, blocks=23, p_greater=0.06, p_less=0.94)),
        "decile_spread_executable_not_positive": _primary(ic=_blocks(0.05, blocks=23, p_greater=0.001, p_less=0.999), spread=0.0),
        "decile_spread_executable_unmeasured": _primary(ic=_blocks(0.05, blocks=23, p_greater=0.001, p_less=0.999), spread=None),
    }
    for reason, cell in cases.items():
        decided = backtest.verdict(cell, _split())
        assert decided["status"] == "FAIL" and decided["reasons"] == [reason], (reason, decided)
    assert backtest.verdict(good, _split(first=-0.001))["reasons"] == ["ic_executable_first_half_not_positive:-0.001"]
    assert backtest.verdict(good, _split(second=0.0))["reasons"] == ["ic_executable_second_half_not_positive:0.0"]
    assert backtest.verdict(good, _split(first=None))["reasons"] == ["ic_executable_first_half_not_positive:None"]
    # the T → T+h IC never decides: strongly positive there, nothing on the executable return → FAIL
    descriptive = _primary(ic=_blocks(0.0, blocks=23, p_greater=0.5, p_less=0.5), descriptive=_blocks(0.3, blocks=23, p_greater=1e-9, p_less=1.0))
    assert backtest.verdict(descriptive, _split())["status"] == "FAIL"


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
        length = rng.choice((2, 3, 5, 21))
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
    assert grid == sessions[::5] and grid[0] == date(2021, 6, 1) and len(grid) == 266 and (sessions.index(grid[-1]) // 21 + 1) == 64  # 64 blocks of 21
    # a 36-month nightly republication cannot start a 2021 grid: the bounds say so (the grid runner refuses it, the report voids it)
    nightly = _vintage("2023-10-01", "2026-10-19", "2026-10-19T04:30:00+00:00")
    short = backtest.eligible_bounds({"NASDAQ": nightly, "NYSE": nightly})
    assert short["starts_at_grid_start"] is False and short["first_eligible"] == "2024-10-02"  # 252 sessions after 2023-10-02
    later = backtest.eligible_bounds({"NASDAQ": nightly, "NYSE": nightly}, grid_start=date(2024, 10, 2))
    assert later["starts_at_grid_start"] is True and len(backtest.prereg_grid(later)) == 98
    # the exchanges intersect: a vintage of one exchange published a day earlier ends the grid a session earlier
    assert backtest.eligible_bounds({"NASDAQ": backfill, "NYSE": _vintage("2016-10-01", "2026-10-15", "2026-10-15T23:00:00+00:00")})["last_eligible"] == "2026-09-15"
    for unusable in ({"NASDAQ": backfill, "NYSE": None}, {"NASDAQ": backfill, "NYSE": {**backfill, "status": "manifest_mismatch"}},
                     {"NASDAQ": backfill, "NYSE": _vintage("2025-10-01", "2026-10-19", "2026-10-19T04:30:00+00:00")}):
        none = backtest.eligible_bounds(unusable)
        assert none["first_eligible"] is None and none["starts_at_grid_start"] is False and backtest.prereg_grid(none) == []
    with pytest.raises(ValueError):
        backtest.prereg_grid(bounds, step=0)


# ------------------------------------------------------------------ the manifest
def _manifest(entries: list[dict[str, Any]], pins: dict[str, dict[str, Any]], **changes: Any) -> dict[str, Any]:
    manifest: dict[str, Any] = {"schema": backtest.MANIFEST_SCHEMA, "market": "US", "markets": ["NASDAQ", "NYSE"], "price_pin": {"requested_at": "x", **pins},
                                "statements": "vintages", "step_sessions": backtest.STEP_SESSIONS, "grid_start": backtest.GRID_START.isoformat(), "grid": entries,
                                "complete": True}
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
    assert constants["grid_start"] == "2021-06-01" and "120-month" in constants["price_vintage"]
    assert (constants["min_blocks"], constants["ic_min"], constants["alpha"], constants["alpha_negative"], constants["attrition_cap"]) == (12, 0.02, 0.05, 0.05, 0.10)
    assert constants["decisory_statistic"] == "ic_executable" and constants["statements"] == "vintages" and constants["markets"] == ["NASDAQ", "NYSE"]
    assert constants["t_clock"] == "01:00 America/Sao_Paulo of the civil day after session D (session_date = D)" and constants["look"] == "single"
    assert constants["verdict_order"] == ["VOID", "UNMEASURED", "NEGATIVE", "PASS", "FAIL"] and constants["adjacent_block_variance_factor"] == 1.5
    assert constants["code_pins"] == {"files": list(backtest.PINNED_FILES), "objects": list(backtest.PINNED_OBJECTS)} and constants["gate"] is False
    assert backtest.label_horizons() == (1, 21, 22, 63, 64, 126, 127)
    text = PREREG_PATH.read_text(encoding="utf-8")
    for needle in ("VALUATION-PIT-BACKTEST-REPORT-v1", "VALUATION-PIT-GRID-MANIFEST-v1", "STEP_SESSIONS = 5", "MIN_PRIOR_SESSIONS = 252", "MIN_BLOCKS = 12",
                   "IC_MIN = 0,02", "ALPHA = 0,05", "ALPHA_NEGATIVE = 0,05", "ATTRITION_CAP = 0,10", "01:00 America/Sao_Paulo", "--statements vintages",
                   "ic_executable", f"DESIGN_SEED = {backtest.DESIGN_SEED}", f"DESIGN_REPS = {backtest.DESIGN_REPS}", "GRID_START = 2021-06-01", "--months 120",
                   "own_history", "vintages_coverage"):
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
    table = backtest.design_table(reps=1500, seed=5, sds=(0.10,), ics=(-0.05, 0.0, 0.05, 0.10), blocks=(12, 24))
    cells = {(cell["blocks"], cell["ic"]): cell for cell in table["cells"]}
    for blocks in (12, 24):
        assert cells[(blocks, 0.0)]["pass"] <= 0.07 and cells[(blocks, 0.0)]["negative"] <= 0.07  # the size of a one-sided 0.05 test (1500 paths: 3 sd of noise)
        assert cells[(blocks, -0.05)]["pass"] == 0.0 and cells[(blocks, -0.05)]["negative"] > cells[(blocks, 0.0)]["negative"]
        assert cells[(blocks, 0.0)]["pass"] < cells[(blocks, 0.05)]["pass"] < cells[(blocks, 0.10)]["pass"]
    assert cells[(24, 0.05)]["pass"] > cells[(12, 0.05)]["pass"]  # more blocks, more power
    assert backtest.design_table(reps=200, seed=5, sds=(0.10,), ics=(0.05,), blocks=(12,)) == backtest.design_table(reps=200, seed=5, sds=(0.10,), ics=(0.05,), blocks=(12,))
    with pytest.raises(ValueError):
        backtest.design_table(reps=10, blocks=(1,))


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
    """A protocol small enough for a test store: h = 10, every 2nd session, 3 prior sessions (12 blocks need 111 sessions)."""
    monkeypatch.setattr(backtest, "HORIZONS", (10,))
    monkeypatch.setattr(backtest, "PRIMARY_HORIZON", 10)
    monkeypatch.setattr(backtest, "STEP_SESSIONS", 2)
    monkeypatch.setattr(backtest, "MIN_PRIOR_SESSIONS", 3)
    monkeypatch.setattr(backtest, "GRID_START", date(2025, 1, 7))  # the 4th session of the synthetic calendar (3 prior sessions)


Rule = Callable[[random.Random, int, dict[str, float], dict[str, float], dict[str, float]], dict[str, float]]


class Synthetic:
    """A US store: thirty synthetic names (fifteen per exchange) × ``count`` XNYS sessions from 2025-01-02 of seeded random
    daily moves (±2 %), plus — with ``jump`` — a move of ``jump · z`` on the session AFTER each grid session (z standard
    normal per name and grid instant). One vintage per exchange published after the last session; at every grid session
    one synthetic re-executor run per exchange (a run snapshot with its prediction identities and producer, the records
    with their run_key) whose upside is ``rule(rng, k, executable return, total return, z)``; and the manifest."""

    def __init__(self, rule: Rule, *, count: int = 130, seed: int = 11, jump: float = 0.0, drop_from: dict[str, int] | None = None) -> None:
        self.rng = random.Random(seed)
        self.database = Database(_settings())
        self.sessions = [stamp.date() for stamp in series._calendar("NASDAQ").sessions_in_range("2025-01-02", "2025-12-31")][:count]
        h, lag = backtest.PRIMARY_HORIZON, backtest.EXECUTION_LAG_SESSIONS
        first, last = backtest.MIN_PRIOR_SESSIONS, count - 1 - (h + lag)
        grid_index = list(range(first, last + 1, backtest.STEP_SESSIONS))
        self.z = {j: {symbol: self.rng.gauss(0.0, 1.0) for _m, symbol in NAMES} for j in grid_index}
        self.closes: dict[str, dict[date, float]] = {}
        for k, (_market, symbol) in enumerate(NAMES):
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
            executable = {s: self.closes[s][self.sessions[j + h + lag]] / self.closes[s][self.sessions[j + lag]] - 1.0 for _m, s in NAMES}
            total = {s: self.closes[s][self.sessions[j + h]] / self.closes[s][day] - 1.0 for _m, s in NAMES}
            upsides = rule(self.rng, k, executable, total, self.z[j])
            for market in backtest.MARKETS:
                self.entries.append(self.run(market, day, {s: upsides[s] for m, s in NAMES if m == market}))
        self.grid_sessions = [self.sessions[j] for j in grid_index]

    def publish(self, at: datetime, *, scale: float = 1.0, drop_from: dict[str, int] | None = None) -> dict[str, dict[str, Any]]:
        """One vintage per exchange of every bar (× ``scale``; a name's bars stop at ``drop_from``), published at ``at``."""
        pins: dict[str, dict[str, Any]] = {}
        for offset, market in enumerate(backtest.MARKETS):
            bars = {f"{symbol}.US": [{"date": day.isoformat(), "close": round(self.closes[symbol][day] * scale, 6), "adjusted_close": round(self.closes[symbol][day] * scale, 6),
                                      "volume": 1.0} for j, day in enumerate(self.sessions) if j < (drop_from or {}).get(symbol, len(self.sessions))]
                    for m, symbol in NAMES if m == market}
            http = ScriptedHttp(bars)
            producer = series.PriceHistoryService(_settings(), self.database, http, eodhd=EodhdClient("https://eodhd.com", "secret", http))  # type: ignore[arg-type]
            producer.persist_run(market, start=self.sessions[0], end=self.sessions[-1], symbols=[s for m, s in NAMES if m == market], now=at + timedelta(minutes=offset))
            publication = self.database.latest_analysis_snapshot(series.PUBLICATION_TYPE, market)
            assert publication is not None
            pins[market] = {"publication_id": publication["id"], "available_at": panel._utc(publication["published_at"]).isoformat(),
                            "bars_sha256": publication["outputs"]["bars_sha256"]}
        return pins

    def run(self, market: str, day: date, upsides: dict[str, float], *, run_key: str | None = None, supersedes: str | None = None,
            engine: dict[str, str] | None = None, statements: str = "vintages", extra_identity: bool = False, published: datetime | None = None,
            publication_id: str | None = None) -> dict[str, Any]:
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
                                                  market=market, scope="universe", cycle_id=cycle_id, source_version=SOURCE_VERSION, prediction_instant=instant,
                                                  published_at=published, source=official.SOURCE_V3_2_SHADOW, extra_provenance={"run_key": run_key})
            assert record is not None
            records.append(record)
        identities = [[record["symbol"], record["row_sha256"]] for record in records] + ([["ZZZ", "0" * 64]] if extra_identity else [])
        inputs: dict[str, Any] = {"run_key": run_key, "market": market, "as_of": instant.isoformat(), "source": official.SOURCE_V3_2_SHADOW, "source_version": SOURCE_VERSION,
                                  "price_pin": {"mode": "explicit", "requested_at": "x", "resolved_publication_id": publication_id or self.pins[market]["publication_id"]},
                                  "manifest": {"session_date": day.isoformat(), "engine": {"implementation_file_sha256": engine or ENGINE}, "price_vintage": {}, "sources": ["heavy"]}}
        if supersedes:
            inputs["supersedes"] = supersedes
        outputs = {"summary": {"evaluated": len(records) + 1, "with_internal_tp": len(records), "not_evaluable": {"statement_vintages_missing": 2},
                               "statements": {"mode": statements, "table_present": True, "basis": {"statement_vintages": len(records) + 1},
                                              "coverage": {"covered": 40, "covered_in_catalogue": len(records) + 1, "covered_without_rows_by_T": 0}},
                               "price_basis_evidence": {"symbols_read": len(records) + 3}},
                   "prediction_identities": identities,
                   "rows": {symbol: {"models": {"own_history": {"tp": 1.0}} if index % 3 else {"peer_comps": {"tp": 1.0}}} for index, symbol in enumerate(sorted(upsides))}}
        self.database.save_analysis_snapshot(backtest.RUN_ANALYSIS_TYPE, f"{market}_PIT_{run_key[:16]}", "mv-pit", inputs, outputs, published, snapshot_id=cycle_id)
        assert self.database.insert_valuation_predictions(records) == len(records)
        return {"as_of": instant.isoformat(), "session_date": day.isoformat(), "market": market, "run_key": run_key, "cycle_id": cycle_id, "idempotent": False,
                "reused": False, "evaluated": len(records) + 1, "records": len(records), "not_evaluable": {"statement_vintages_missing": 2}}

    def manifest(self, entries: list[dict[str, Any]] | None = None, **changes: Any) -> dict[str, Any]:
        return _manifest(self.entries if entries is None else entries, self.pins, **changes)

    def report(self, manifest: dict[str, Any] | None = None, **binding: Any) -> dict[str, Any]:
        service = backtest.PitBacktestReportService(backtest.ReadOnlyStore(self.database), settings=_settings())  # type: ignore[arg-type]
        bound = binding or {"prereg_sha256": "f" * 64, "code_pins": accuracy.pins_of(backtest.code_fingerprint())}
        receipt = service.report(manifest or self.manifest(), **bound)
        assert service.http is not None and service.http.calls == 0  # never the network
        assert not any(symbol in json.dumps(receipt) for _m, symbol in NAMES)  # aggregates only
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
    assert payload["grid"]["status"] == "PREREG" and payload["grid"]["expected_sessions"] == len(store.grid_sessions) == 58
    assert payload["runs"]["status"] == {"current": 116} and payload["runs"]["incomplete"] == 0 and payload["runs"]["producer"]["uniform"] is True
    assert payload["runs"]["producer"]["engine_files"] == ENGINE and payload["runs"]["producer"]["source_versions"] == {SOURCE_VERSION: 116}
    assert payload["records"]["read"] == 58 * 30 and payload["records"]["observations"] == 58 * 30 and payload["records"]["refused"] == {}
    assert payload["records"]["cohort"] == {"retrospective": 58 * 30}  # every PIT record is retrospective: counted, never filtered
    primary = payload["horizons"]["10"]
    assert primary["attrition_executable"] == {"eligible": 1740, "rate": 0.0, "unavailable": 0, "by_cause": {}} and primary["decile_spread_executable"]["blocks"]["estimate"] > 0
    assert payload["names_per_session"]["executable_h_primary"] == {"n": 58, "min": 30.0, "median": 30.0, "max": 30.0}
    us = payload["coverage"]["US"]
    assert (us["runs"], us["evaluated"], us["records"], us["catalogue_names"], us["not_evaluable"]) == (116, 116 * 16, 1740, 116 * 18, {"statement_vintages_missing": 232})
    assert us["history_model_active"] == 58 * 20 and us["history_model_share"] == pytest.approx(20 * 58 / (116 * 16))  # 10 of 15 names per run, in its rows
    assert us["history_model_share_per_session"]["n"] == 58 and payload["coverage"]["NASDAQ"]["runs"] == 58
    assert payload["label_vintages"]["NASDAQ"]["publication_id"] == store.pins["NASDAQ"]["publication_id"] and payload["code_binding"]["status"] == "BOUND"
    assert payload["manifest"]["manifest_sha256"] == store.manifest()["manifest_sha256"] and payload["anchor"] == store.grid_sessions[0].isoformat()
    again = store.report()
    assert again["payload_sha256"] == receipt["payload_sha256"]  # a function of (manifest, store, code): the same look reproduces the same hash


def test_a_zero_ic_fails_and_a_negative_ic_is_negative(small: None) -> None:
    zero = Synthetic(_zero, seed=12).report()["payload"]["verdict"]
    assert zero["status"] == "FAIL" and abs(zero["ic_estimate"]) < 0.1 and zero["ic_p_greater"] > 0.05 and zero["ic_p_less"] > 0.05
    assert any(reason.startswith("ic_executable_not_significant") for reason in zero["reasons"])
    negative = Synthetic(_negative, seed=13).report()["payload"]["verdict"]
    assert negative["status"] == "NEGATIVE" and negative["ic_estimate"] < -0.5 and negative["reasons"][0].startswith("ic_executable_negative:p_less=")


def test_halves_that_disagree_fail_even_when_the_whole_is_significant(small: None) -> None:
    def rule(rng: random.Random, k: int, executable: dict[str, float], total: dict[str, float], z: dict[str, float]) -> dict[str, float]:
        weight = 2.0 if k < 30 else -0.1  # blocks 0–5 (grid instants 0–29) strongly right, blocks 6–11 slightly wrong
        return {s: max(-0.5, min(0.5, weight * value + rng.gauss(0.0, 0.1))) for s, value in executable.items()}

    payload = Synthetic(rule, seed=14).report()["payload"]
    decided = payload["verdict"]
    assert decided["blocks"] == 12 and decided["ic_estimate"] >= backtest.IC_MIN and decided["ic_p_greater"] <= backtest.ALPHA
    assert decided["halves"]["first"] > 0.5 and decided["halves"]["second"] < 0 and payload["horizons"]["10"]["decile_spread_executable"]["blocks"]["estimate"] > 0
    assert decided["status"] == "FAIL" and decided["reasons"] == [f"ic_executable_second_half_not_positive:{decided['halves']['second']}"]


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
    assert attrition["rate"] > backtest.ATTRITION_CAP and "missing_bar" in json.dumps(attrition["by_cause"]) or "adjustment_unknown" in json.dumps(attrition["by_cause"])
    assert payload["verdict"]["status"] == "UNMEASURED" and payload["verdict"]["reasons"][0].startswith("attrition_above_cap:")
    short = Synthetic(_positive, seed=17, count=100).report()["payload"]
    assert short["grid"]["status"] == "PREREG" and short["verdict"]["blocks"] == 9
    assert short["verdict"]["status"] == "FAIL" and short["verdict"]["reasons"] == ["blocks_below_min:9<12"]


def test_only_the_manifests_current_complete_runs_are_read_and_every_integrity_failure_voids_the_reading(small: None) -> None:
    store = Synthetic(_positive, seed=18, count=60)
    first_day = store.grid_sessions[0]
    first = next(entry for entry in store.entries if entry["market"] == "NASDAQ" and entry["session_date"] == first_day.isoformat())
    # a foreign run of the same T, published BEFORE the manifest's (an old diagnostic run): its records are refused, the manifest's run stays current
    store.run("NASDAQ", first_day, {s: 0.0 for m, s in NAMES if m == "NASDAQ"}, published=store.published - timedelta(hours=1))
    payload = store.report()["payload"]
    assert payload["records"]["refused"] == {"run_not_in_manifest": 15} and payload["runs"]["status"]["current"] == len(store.entries)
    assert payload["verdict"]["status"] != "VOID"

    def void(manifest: dict[str, Any] | None = None, **binding: Any) -> list[str]:
        cell = store.report(manifest, **binding)["payload"]["verdict"]
        assert cell["status"] == "VOID"
        return cell["reasons"]

    assert void(store.manifest(store.entries[2:])) == ["grid_sessions_missing:1"]
    assert void(store.manifest(store.entries[:-1])) == ["grid_sessions_without_both_exchanges:1"]
    assert void(store.manifest(statements="provider")) == ["manifest_statements_not_vintages", f"runs_mismatched:{len(store.entries)}", "no_current_run"]  # the runs say vintages
    assert void(store.manifest(step_sessions=5)) == ["manifest_step_not_2"]
    assert void(store.manifest(grid_start="2025-01-02")) == ["manifest_grid_start_not_prereg:2025-01-02"]
    assert void(store.manifest(price_pin={"requested_at": "x", "NASDAQ": {**store.pins["NASDAQ"], "publication_id": "other"}, "NYSE": store.pins["NYSE"]})) == \
        ["label_vintage_not_the_pinned_one:NASDAQ", "runs_mismatched:" + str(len(store.entries) // 2)]
    other_code = {**accuracy.pins_of(backtest.code_fingerprint()), "file app/valuation_pit_backtest_report.py": "0" * 64}
    assert void(prereg_sha256="f" * 64, code_pins=other_code) == ["code_mismatch", "code_mismatch:file app/valuation_pit_backtest_report.py"]
    # a run missing from the store
    missing = [{**entry, "run_key": "e" * 64} if entry is first else entry for entry in store.entries]
    assert void(store.manifest(missing)) == ["runs_missing:1"]

    def replaced(fresh: Synthetic, entry: dict[str, Any]) -> list[dict[str, Any]]:
        return [entry if (old["market"], old["session_date"]) == (entry["market"], entry["session_date"]) else old for old in fresh.entries]

    # a cycle whose records are not its identities (each case on its own store: a later run of a (exchange, T) changes the store's latest)
    fresh = Synthetic(_positive, seed=18, count=60)
    incomplete = fresh.run("NASDAQ", fresh.grid_sessions[1], {s: 0.0 for m, s in NAMES if m == "NASDAQ"}, extra_identity=True)
    assert fresh.report(fresh.manifest(replaced(fresh, incomplete)))["payload"]["verdict"]["reasons"] == ["runs_incomplete:1"]
    # two producers in one grid
    fresh = Synthetic(_positive, seed=18, count=60)
    other_producer = fresh.run("NYSE", fresh.grid_sessions[2], {s: 0.0 for m, s in NAMES if m == "NYSE"}, engine={**ENGINE, "valuation_v3_engine.py": "9" * 64})
    assert fresh.report(fresh.manifest(replaced(fresh, other_producer)))["payload"]["verdict"]["reasons"] == ["producer_not_uniform"]
    # a later run of a manifest's (exchange, T) that supersedes it: the manifest is stale, the superseded records are refused
    later = store.run("NASDAQ", first_day, {s: 0.0 for m, s in NAMES if m == "NASDAQ"}, supersedes=first["run_key"])
    stale = store.report()["payload"]
    assert stale["verdict"]["reasons"] == ["runs_superseded:1"] and stale["records"]["refused"]["superseded_run"] == 15
    current = [later if entry is first else entry for entry in store.entries]
    assert store.report(store.manifest(current))["payload"]["runs"]["status"] == {"current": len(store.entries)}
    with pytest.raises(backtest.ManifestError):
        store.report({**store.manifest(), "grid": []})  # the hash no longer recomputes


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
    assert payload["verdict"]["status"] == "FAIL" and payload["verdict"]["reasons"] == ["blocks_below_min:5<12"]  # 60 sessions: five blocks of 10
    assert not any(symbol in out for _m, symbol in NAMES) and backtest.READ_ONLY_PGOPTION in __import__("os").environ["PGOPTIONS"]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert backtest.main(["--manifest", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["payload"]["verdict"]["reasons"] == ["code_unbound", "prereg_not_given"]
    path.write_text(json.dumps({**manifest, "statements": "auto"}), encoding="utf-8")
    with pytest.raises(SystemExit):
        backtest.main(["--manifest", str(path)])  # the hash does not recompute: nothing read
    with pytest.raises(SystemExit):
        backtest.main(["--manifest", str(tmp_path / "absent.json")])


def test_a_grid_that_cannot_start_at_the_pre_registered_session_is_void_and_the_compaction_is_lossless(small: None, monkeypatch: pytest.MonkeyPatch) -> None:
    store = Synthetic(_positive, seed=20, count=60)
    full = store.report()
    monkeypatch.setattr(backtest, "_compact", lambda row: dict(row))  # every field of the observation kept
    assert store.report()["payload"]["horizons"] == full["payload"]["horizons"] and store.report()["payload_sha256"] == full["payload_sha256"]
    monkeypatch.undo()
    monkeypatch.setattr(backtest, "HORIZONS", (10,))
    monkeypatch.setattr(backtest, "PRIMARY_HORIZON", 10)
    monkeypatch.setattr(backtest, "STEP_SESSIONS", 2)
    monkeypatch.setattr(backtest, "MIN_PRIOR_SESSIONS", 3)
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
