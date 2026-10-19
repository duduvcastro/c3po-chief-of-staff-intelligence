"""The SERVED internal TP re-executed point-in-time (``valuation_pit_served``, ``official_internal_pit``) — PREREG_VALUATION_PIT_
BACKTEST_US_V1 rev 2: equivalence with the live US producer (``USScreeningService._analyze_stock`` on the same quote and
fundamentals, consensus removed), the point-in-time filters (a fact accepted after T is invisible, forward EPS absent → the
trailing EPS, counted; the calibration published before T only; the dated earnings history), records never selectable, the
grid running both sources with a V3 run byte-identical to a V3-only grid, the report's two verdicts and the mutation checks
on the source routing. Synthetic symbols, no network."""
from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter
from datetime import date, datetime, time as wall_time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping
from uuid import uuid4

import pytest
import yaml

from app import valuation_accuracy_report as accuracy
from app import valuation_official as official
from app import valuation_pit_backtest_report as backtest
from app import valuation_pit_grid as grid
from app import valuation_pit_rerun as pit
from app import valuation_pit_served as served
from app.config import Settings
from app.database import Database
from app.market_data.eodhd import EodhdClient
from app.market_data.service import MarketDataService
from app.market_data.us_screener import USScreeningService
from app.one_pager import OnePagerService
from app.valuation_official_engine import OFFICIAL_SOURCES
from tests import asfiled_front
from tests.test_us_screener import DummyRealtime
from tests.test_valuation_pit_backtest_report import ENGINE, OBJECTS, SOURCE_VERSION, Synthetic, _negative, _positive, _settings as _report_settings, small  # noqa: F401
from tests.test_valuation_pit_grid import CATALOGUE_PIN, PIN, US, _args, _manifest as _grid_manifest, _store, short_grid  # noqa: F401
from tests.test_valuation_pit_rerun import ISSUERS, NOW, T, _accepted, _consistent_payload, _file, _file_payload, _ready, _republish_payload, _service, _settings

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "valuation-pit-backtest.yml"
REVENUE = "us-gaap:Revenues"


@pytest.fixture
def front() -> Iterator[Any]:
    with asfiled_front.installed() as modules:
        yield modules


def _served(database: Database, *, at: datetime = T, statements: str = "provider") -> served.ServedComputation:
    service = served.PitServedService(database, settings=_settings())
    return service.compute("NASDAQ", as_of=at, prices=_service(database).pin_vintage("NASDAQ", as_of=at, pinned_at=NOW), statements=statements)


def _live(tmp_path: Path) -> USScreeningService:
    """The LIVE US producer, built as the application builds it (a real One Pager service behind it)."""
    settings = Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", one_pager_output_dir=tmp_path, auth_cookie_secure=False)
    database = Database(settings)
    return USScreeningService(settings, database, DummyRealtime(), OnePagerService(settings, database, MarketDataService(settings, database), output_dir=tmp_path))


# ------------------------------------------------------------------ identity and governance
def test_the_source_is_recordable_in_its_snapshots_only_never_selectable_and_its_producer_names_the_one_pager() -> None:
    assert served.SOURCE == backtest.SERVED_SOURCE == "official_internal_pit" and served.ANALYSIS_TYPE == backtest.SERVED_RUN_ANALYSIS_TYPE
    assert served.SERVED_SOURCE == backtest.SERVED_TP_SOURCE == official.SOURCE_INTERNAL
    assert served.SOURCE not in OFFICIAL_SOURCES and served.SOURCE not in official.RECORDABLE_SOURCES  # never selectable, never in the table
    with pytest.raises(ValueError, match="unknown recordable source"):
        official.prediction_from_row({"symbol": "AAA", "our_tp": 1.0, "buy_in": 1.0}, market="NASDAQ", scope="universe", cycle_id="c", source_version="v",
                                     prediction_instant=T, source=served.SOURCE)
    assert {"one_pager.py", "market_data/us_screener.py", "market_data/eodhd.py", "valuation_pit_served.py"} <= set(served.IMPLEMENTATION_FILES)
    assert set(served.implementation_files()) == set(served.IMPLEMENTATION_FILES) and served.implementation_objects() == pit.implementation_objects()
    for name in ("one_pager.py", "market_data/us_screener.py"):  # hashed only: the bytes of the live producer
        assert served.implementation_files()[name] == hashlib.sha256((Path(served.__file__).parent / name).read_bytes()).hexdigest()
    assert served.producer()["engine_sha256"] == official.canonical_sha256({"files": served.implementation_files(), "objects": served.implementation_objects()})
    # the workflow computes the served producer from the prereg commit, file for file
    steps = [step for job in yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))["jobs"].values() for step in job.get("steps", [])]
    run = next(step for step in steps if step.get("name") == "Read the pre-registration and the producer at the prereg commit")["run"]
    listed = run.split("for name in", 2)[2].split("; do", 1)[0].replace("\\", " ").split()
    assert tuple(listed) == served.IMPLEMENTATION_FILES and '--expect-served-producer-sha256 "$SERVED_PRODUCER"' in WORKFLOW_PATH.read_text(encoding="utf-8")


# ------------------------------------------------------------------ equivalence with the live producer
def test_the_served_tp_is_the_live_producers_internal_tp_on_the_same_quote_and_fundamentals_consensus_removed(tmp_path: Path) -> None:
    database = _ready()
    run = _served(database)
    assert set(run.results) == set(pit.PitRerunService(database, settings=_settings()).compute(
        "NASDAQ", as_of=T, prices=_service(database).pin_vintage("NASDAQ", as_of=T, pinned_at=NOW)).resolver.per_symbol)  # the V3 run's evaluable names
    records = {record["symbol"]: record for record in run.records(cycle_id="c-1", published_at=NOW)}
    live = _live(tmp_path)
    peer_medians, rate = run.manifest["peer_medians"], run.manifest["risk_free"]["rate"]
    assert rate == pytest.approx(0.05)  # the 10-year point of the PIT curve at T (5.0 % in the fixture), clamped as the live rate
    for symbol, item in run.resolver.per_symbol.items():
        fundamentals = served.fundamentals_at(symbol, run.resolver.payloads[symbol], item, market="NASDAQ", economic_date=run.resolver.economic_date, excluded=Counter())
        quote = {"symbol": symbol, "price": item["row"]["price"], "currency": "USD", "as_of": T.isoformat()}
        expected = live._analyze_stock("NASDAQ", quote, fundamentals, [], 0.0, risk_free_rate=rate, peer_medians=peer_medians)
        assert expected["public_consensus_tp"] is None and expected["internal_tp"] == pytest.approx(statistics.mean(expected["methods"].values()))
        record = records[symbol]
        assert record["tp"] == expected["internal_tp"] and record["buy_in"] == expected["internal_buy_in"]  # exact: the same producer
        assert record["internal_tp"] == expected["internal_tp"] and record["decomposition"]["methods"] == expected["methods"]
        assert record["source"] == served.SOURCE and record["consensus_weight_percent"] == 0.0 and record["consensus_tp"] is None
        assert record["decomposition"]["weights"]["calibration_factor"] == 1.0 and served.record_verifies(record)
        # the consensus never enters the internal TP: the live row with a consensus has another blended TP and the SAME internal TP
        with_consensus = live._analyze_stock("NASDAQ", quote, {**fundamentals, "targetMeanPrice": item["row"]["price"] * 1.3, "numberOfAnalystOpinions": 12},
                                             [], 0.0, risk_free_rate=rate, peer_medians=peer_medians)
        assert with_consensus["public_consensus_tp"] is not None and with_consensus["our_tp"] != with_consensus["internal_tp"]
        assert with_consensus["internal_tp"] == expected["internal_tp"]
    # the peer medians are the One Pager's own over the run's PIT fundamentals; the live normaliser built them
    assert peer_medians == OnePagerService._us_peer_medians({symbol: served.fundamentals_at(symbol, run.resolver.payloads[symbol], item, market="NASDAQ",
                                                                                            economic_date=run.resolver.economic_date, excluded=Counter())
                                                             for symbol, item in run.resolver.per_symbol.items()})


def test_the_provider_shape_is_rebuilt_from_the_statements_eligible_at_t_only() -> None:
    database = _ready()
    run = _served(database)
    item = run.resolver.per_symbol["AAA"]
    fundamentals = served.fundamentals_at("AAA", run.resolver.payloads["AAA"], item, market="NASDAQ", economic_date=run.resolver.economic_date, excluded=Counter())
    payload = run.resolver.payloads["AAA"]["Financials"]["Income_Statement"]["quarterly"]
    last_four = [payload[key] for key in ("2023-06-30", "2023-09-30", "2023-12-31", "2024-03-31")]
    net_income, revenue = sum(row["netIncome"] for row in last_four), sum(row["totalRevenue"] for row in last_four)
    assert fundamentals["trailingEps"] == pytest.approx(net_income / 1_000_000.0) and fundamentals["sharesOutstanding"] == 1_000_000.0
    assert fundamentals["forwardEps"] is None and fundamentals["targetMeanPrice"] is None and fundamentals["earningsTrendQuarterly"] == []  # absent
    assert fundamentals["profitMargins"] == pytest.approx(net_income / revenue) and fundamentals["ebitda"] == pytest.approx(sum(r["ebitda"] for r in last_four))
    assert fundamentals["revenueGrowthAnnual"] == pytest.approx(payload["2024-03-31"]["totalRevenue"] / payload["2023-03-31"]["totalRevenue"] - 1)
    assert fundamentals["beta"] == item["row"]["beta"] and fundamentals["marketCap"] == pytest.approx(item["row"]["price"] * 1_000_000.0)
    assert fundamentals["quarterlyIncome"][0]["date"] == "2024-03-31" and fundamentals["sector"] == "Industrials"
    # a quarter reported after T is never in the shape: at the close of 2024-05-14 the 2024Q1 filing (2024-05-15) does not exist yet
    early = datetime(2024, 5, 14, 21, 0, tzinfo=UTC)
    before = _served(database, at=early)
    shape = served.fundamentals_at("AAA", before.resolver.payloads["AAA"], before.resolver.per_symbol["AAA"], market="NASDAQ",
                                   economic_date=before.resolver.economic_date, excluded=Counter())
    assert shape["quarterlyIncome"][0]["date"] == "2023-12-31" and all(row["date"] <= "2023-12-31" for row in shape["quarterlyIncome"])
    counted = run.summary()["pit_excluded_inputs"]
    assert counted["forward_eps:absent_trailing_eps_used"] == 6 and counted["forward_eps:no_point_in_time_history"] == 6  # absent → trailing, counted
    assert counted["insider_activity:no_point_in_time_history"] == 6 and counted["consensus:never_in_the_internal_tp"] == 6
    assert counted["earnings_surprise:not_read"] == 6


def test_the_current_earnings_block_is_never_read_in_either_mode() -> None:
    """Provider mode: the payload's Earnings.History (a CURRENT provider block, forbidden in V3 §3) never reaches the served TP."""
    database = _ready()
    base = _served(database)
    for snapshot in database._analysis_snapshots:  # type: ignore[attr-defined]
        payload = (snapshot.get("outputs") or {}).get("payload")
        if snapshot["analysis_type"] == pit.SOURCE_ANALYSIS_TYPE and isinstance(payload, dict) and "Financials" in payload:
            payload["Earnings"] = {"History": {"2024-03-31": {"reportDate": "2024-05-02", "surprisePercent": 50.0, "date": "2024-03-31"}}}
    later = _served(database)
    assert all(later.results[s]["internal_tp"] == base.results[s]["internal_tp"] for s in base.results)
    assert later.summary()["pit_excluded_inputs"]["earnings_surprise:not_read"] == 6
    poisoned = _served(_ready(poison=True))  # every current block poisoned: nothing moves
    for symbol, result in base.results.items():
        assert all(poisoned.results[symbol][key] == result[key] for key in ("internal_tp", "internal_buy_in", "methods", "risk_score", "valuation_confidence"))


def test_a_fact_accepted_after_t_is_invisible_to_the_served_tp(front: Any) -> None:
    database = _ready()
    for symbol in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"):
        consistent = _consistent_payload(symbol)
        _republish_payload(database, symbol, consistent)
        _file_payload(front, database, symbol, consistent)
    base = _served(database, statements="vintages")
    assert base.summary()["statements"]["basis"] == {"statement_vintages": 6} and len(base.results) == 6
    # a 10-Q for 2024Q2 with a revenue ten times larger, accepted AFTER T: the same run, the same TP
    _file(front, database, "AAA", f"{ISSUERS['AAA']}-late", _accepted(date(2024, 6, 20)),
          [(REVENUE, 1e10, date(2024, 6, 30), date(2024, 4, 1))])
    later = _served(database, statements="vintages")
    assert later.run_key == base.run_key and later.results["AAA"]["internal_tp"] == base.results["AAA"]["internal_tp"]
    # accepted BEFORE T (a restatement of 2024Q1 revenue the day before): another run, another TP
    _file(front, database, "AAA", f"{ISSUERS['AAA']}-restated", _accepted(date(2024, 6, 13)),
          [(REVENUE, 3e7, date(2024, 3, 31), date(2024, 1, 1))])
    restated = _served(database, statements="vintages")
    assert restated.run_key != base.run_key and restated.results["AAA"]["internal_tp"] != base.results["AAA"]["internal_tp"]


def test_the_calibration_factor_is_the_one_published_before_t_never_after(tmp_path: Path) -> None:
    database = _ready()
    base = _served(database)
    assert base.calibration["status"] == "absent_at_T" and base.calibration["factors"] == {}
    database.save_analysis_snapshot("valuation_calibration", "NASDAQ_POWER_MODEL", "mv", {}, {"status": "active", "factors": {"general": 1.5, "global": 0.97}},
                                    T + timedelta(hours=1))  # after T: invisible
    assert _served(database).run_key == base.run_key
    database.save_analysis_snapshot("valuation_calibration", "NASDAQ_POWER_MODEL", "mv", {}, {"status": "active", "factors": {"general": 1.5, "global": 0.97}},
                                    T - timedelta(days=1))
    applied = _served(database)
    assert applied.calibration["status"] == "applied" and applied.calibration["factors"] == {"general": 1.05, "global": 0.97}  # clamped by the live loader
    records = {record["symbol"]: record for record in applied.records(cycle_id="c", published_at=NOW)}
    for symbol, result in applied.results.items():
        # the factor is keyed by the ONE PAGER's profile (Industrials → "quality": the global factor), not the row's screener profile ("general")
        assert applied.profiles[symbol] == "quality" and result["valuation_profile"] == "general"
        assert result["internal_tp"] == pytest.approx(base.results[symbol]["internal_tp"] * 0.97)
        assert result["internal_tp"] == pytest.approx(statistics.mean(result["methods"].values()) * records[symbol]["decomposition"]["weights"]["calibration_factor"])
        assert records[symbol]["decomposition"]["weights"]["calibration_factor"] == 0.97 and records[symbol]["decomposition"]["provenance"]["calibration"]["status"] == "applied"
    database.save_analysis_snapshot("valuation_calibration", "NASDAQ_POWER_MODEL", "mv", {}, {"status": "active", "factors": {"quality": 1.02, "global": 0.97}},
                                    T - timedelta(hours=1))
    quality = _served(database)
    assert all(result["internal_tp"] == pytest.approx(base.results[symbol]["internal_tp"] * 1.02) for symbol, result in quality.results.items())


def test_a_served_run_persists_one_snapshot_with_its_records_is_idempotent_and_never_writes_the_predictions_table() -> None:
    database = _ready()
    service = served.PitServedService(database, settings=_settings())
    first, run = service.rerun("NASDAQ", as_of=T, clock=lambda: NOW)
    again, _ = service.rerun("NASDAQ", as_of=T, clock=lambda: NOW + timedelta(hours=1))
    assert first["idempotent"] is False and again["idempotent"] is True and again["run_key"] == first["run_key"] == run.run_key
    snapshots = [item for item in database._analysis_snapshots if item["analysis_type"] == served.ANALYSIS_TYPE]
    assert len(snapshots) == 1 and database._valuation_predictions == []  # type: ignore[attr-defined]
    outputs = snapshots[0]["outputs"]
    assert len(outputs["records"]) == 6 and all(served.record_verifies(record) for record in outputs["records"])
    assert outputs["governance"]["selectable"] is False and outputs["screen"] == run.screen_inputs() and not json.dumps(first).count("AAA")
    assert served.reusable_run(database, "NASDAQ", T, publication_id=run.manifest["price_vintage"]["publication_id"], statements="provider") is not None
    snapshots[0]["outputs"]["records"][0]["tp"] = 1.0  # a tampered record: never reused, and the next run refuses the cycle
    assert served.reusable_run(database, "NASDAQ", T, publication_id=run.manifest["price_vintage"]["publication_id"], statements="provider") is None
    with pytest.raises(pit.PitRerunIntegrityError):
        service.rerun("NASDAQ", as_of=T, clock=lambda: NOW)


# ------------------------------------------------------------------ the grid: both sources, the V3 run byte-identical
def test_the_grid_runs_both_sources_and_the_v3_runs_are_byte_identical_to_a_v3_only_grid(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    short_grid(monkeypatch)
    both_db = _store()
    assert grid.main(_args(tmp_path / "v3.json", "--to", "2024-06-10", "--sources", "v3_2_shadow"), database=both_db, settings=_settings()) == 0
    v3_rows = sorted((r["symbol"], r["session_date"], r["row_sha256"]) for r in both_db._valuation_predictions)  # type: ignore[attr-defined]
    v3_snapshots = len([s for s in both_db._analysis_snapshots if s["analysis_type"] == pit.ANALYSIS_TYPE])
    # the same grid with both sources, every V3 run recomputed through the public API: each comes back IDEMPOTENT — the same run_key, nothing written
    assert grid.main(_args(tmp_path / "both.json", "--to", "2024-06-10", "--recompute-existing"), database=both_db, settings=_settings()) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    both, v3_only = _grid_manifest(tmp_path / "both.json"), _grid_manifest(tmp_path / "v3.json")
    assert "served_grid" not in v3_only and "sources" not in v3_only and "served_producer" not in v3_only  # the rev-1 manifest
    assert both["sources"] == ["v3_2_shadow", "official_internal_pit"] and both["served_producer"] == served.producer()
    assert [entry["run_key"] for entry in both["grid"]] == [entry["run_key"] for entry in v3_only["grid"]]  # the V3 runs: the same identities
    assert all(entry["idempotent"] for entry in both["grid"]) and v3_snapshots == len([s for s in both_db._analysis_snapshots if s["analysis_type"] == pit.ANALYSIS_TYPE])
    assert sorted((r["symbol"], r["session_date"], r["row_sha256"]) for r in both_db._valuation_predictions) == v3_rows  # type: ignore[attr-defined]
    v3_db = both_db
    assert [(e["session_date"], e["market"]) for e in both["served_grid"]] == [(e["session_date"], e["market"]) for e in both["grid"]]
    assert [e["v3_run_key"] for e in both["served_grid"]] == [e["run_key"] for e in both["grid"]] and all(e["records"] == 5 for e in both["served_grid"])
    t_lines = [line for line in lines if line["kind"] == "t"]
    assert "served" not in t_lines[0] and set(t_lines[-1]["served"]) == {"NASDAQ", "NYSE"} and t_lines[-1]["served"]["NYSE"]["records"] == 5
    # a standalone V3 run of the same (exchange, T) is the grid's run: the served run in between changed nothing
    receipt, _ = pit.PitRerunService(v3_db, settings=_settings()).rerun("NASDAQ", as_of=datetime.fromisoformat(both["grid"][0]["as_of"]), price_pinned_at=PIN,
                                                                         catalogue_pinned_at=CATALOGUE_PIN, statements="provider")
    assert receipt["run_key"] == both["grid"][0]["run_key"] and receipt["idempotent"] is True
    # resume: both sources reused; a served producer other than this code's refuses to run
    assert grid.main(_args(tmp_path / "again.json", "--to", "2024-06-10"), database=both_db, settings=_settings()) == 0
    again = _grid_manifest(tmp_path / "again.json")
    assert all(entry["reused"] for entry in again["served_grid"]) and [e["run_key"] for e in again["served_grid"]] == [e["run_key"] for e in both["served_grid"]]
    with pytest.raises(SystemExit):
        grid.main(_args(tmp_path / "x.json", "--expect-served-producer-sha256", "0" * 64), database=both_db, settings=_settings())
    with pytest.raises(SystemExit):
        grid.main(_args(tmp_path / "y.json", "--sources", "official_internal_pit"), database=both_db, settings=_settings())  # never the served one alone
    capsys.readouterr()


# ------------------------------------------------------------------ the report: two verdicts on ONE decisory set
class Dual(Synthetic):
    """``Synthetic`` (whose every V3 run has its served sibling, the same screen inputs, catalogue and coverage) with the
    served upside = the V3 upside × ``sign``."""

    def __init__(self, *args: Any, sign: float = 1.0, **kwargs: Any) -> None:
        super().__init__(*args, served_sign=sign, **kwargs)

    @property
    def served_entries(self) -> list[dict[str, Any]]:
        return [self.served_of[entry["run_key"]] for entry in self.entries]

    def dual_manifest(self, served_entries: list[dict[str, Any]] | None = None, **changes: Any) -> dict[str, Any]:
        return self.manifest(**changes) if served_entries is None else self.manifest(served_grid=served_entries, **changes)

    def served_snapshot(self, entry: Mapping[str, Any]) -> dict[str, Any]:
        return next(item for item in self.database._analysis_snapshots if item["analysis_type"] == backtest.SERVED_RUN_ANALYSIS_TYPE
                    and item["inputs"]["run_key"] == entry["run_key"])


def _bound() -> dict[str, Any]:
    return {"prereg_sha256": "f" * 64, "code_pins": accuracy.pins_of(backtest.code_fingerprint())}


def test_the_receipt_carries_two_verdicts_each_its_own_decision_on_one_decisory_set_and_the_labels_are_read_once(small: None) -> None:
    store = Dual(_positive, sign=-1.0)  # the V3 shadow ranks the returns; the served TP ranks them backwards
    service = store.service()
    receipt = service.report(store.dual_manifest(), **_bound())
    payload = receipt["payload"]
    verdicts = payload["verdicts"]
    assert verdicts["primary"] == "served_internal_tp" and verdicts["v3_shadow"] == payload["verdict"] and payload["verdict"]["status"] == "PASS"
    assert verdicts["served_internal_tp"] == payload["served_internal_tp"]["verdict"] and verdicts["served_internal_tp"]["status"] == "NEGATIVE"
    block = payload["served_internal_tp"]
    assert block["records"]["admissible"] == 58 * 30 and block["records"]["refused"] == {} and block["runs"]["status"] == {"current": 116}
    assert block["coverage"]["US"]["records_share"] == 1.0 and block["screen"] == payload["screen"] and block["grid"]["status"] == "PREREG"
    assert block["horizons"]["10"]["ic_executable"]["blocks"]["estimate"] == pytest.approx(-payload["horizons"]["10"]["ic_executable"]["blocks"]["estimate"], abs=0.1)
    assert service.labels_read == 58 * 30 * len(backtest.label_horizons())  # one label per (symbol, session, horizon): never twice for two sources
    assert payload["protocol"]["verdicts"]["primary"] == "served_internal_tp" and "no multiplicity correction" in payload["protocol"]["verdicts"]["rule"]
    assert not any(symbol in json.dumps(receipt) for _m, symbol in store.names)
    same = Dual(_positive)
    cell = same.service().report(same.dual_manifest(), **_bound())["payload"]
    assert cell["verdicts"]["served_internal_tp"]["status"] == cell["verdicts"]["v3_shadow"]["status"] == "PASS"
    assert cell["verdicts"]["served_internal_tp"]["ic_estimate"] == cell["verdicts"]["v3_shadow"]["ic_estimate"]
    # the V3 runs screen small caps out: the served verdict reads the SAME decisory set (the V3 runs' screen), never its own
    caps = frozenset(s for _m, s in store.names[:8])
    screened = Dual(_positive, count=60, small_caps=caps)
    payload = screened.service().report(screened.dual_manifest(), **_bound())["payload"]
    assert payload["screen"]["screened"] < payload["screen"]["records"] and payload["served_internal_tp"]["screen"] == payload["screen"]


def _void(store: Dual, manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], int]:
    service = store.service()
    payload = service.report(manifest, **_bound())["payload"]
    return payload["verdicts"]["served_internal_tp"], payload["verdicts"]["v3_shadow"], service.labels_read


def test_a_primary_failure_voids_the_whole_reading_a_v3_failure_the_secondary_only(small: None) -> None:
    store = Dual(_positive, count=60)
    served_cell, v3_cell, labels = _void(store, store.manifest(with_served=False))  # a rev-1 manifest: no served source → the whole reading void
    assert served_cell["status"] == v3_cell["status"] == "VOID" and labels == 0
    assert "served:source_not_in_manifest" in served_cell["reasons"] and v3_cell["reasons"] == ["primary_verdict_void"]
    # routing mutations of the served records: identity, source, a duplicated symbol — each voids the whole reading, no label read
    for tamper, reason in (("tp", "served:records_refused:identity_not_verified:1"), ("source", "served:records_refused:record_not_of_its_run:1")):
        fresh = Dual(_positive, count=60)
        first = fresh.entries[0]
        v3 = next(item for item in fresh.database._analysis_snapshots if item["analysis_type"] == backtest.RUN_ANALYSIS_TYPE and item["inputs"]["run_key"] == first["run_key"])
        bad = fresh.served_run(first["market"], date.fromisoformat(first["session_date"]), {s: 0.1 for m, s in fresh.names if m == first["market"]},
                               v3_run_key=first["run_key"], inputs=v3["inputs"], outputs=v3["outputs"], tamper=tamper)
        served_cell, v3_cell, labels = _void(fresh, fresh.dual_manifest([bad, *fresh.served_entries[1:]]))
        assert served_cell["status"] == v3_cell["status"] == "VOID" and reason in served_cell["reasons"] and labels == 0, (tamper, served_cell["reasons"])
    fresh = Dual(_positive, count=60)
    snapshot = fresh.served_snapshot(fresh.served_entries[0])
    snapshot["outputs"]["records"].append(dict(snapshot["outputs"]["records"][0]))
    served_cell, v3_cell, labels = _void(fresh, fresh.dual_manifest())
    assert "served:records_refused:duplicate_symbol_in_run:1" in served_cell["reasons"] and v3_cell["status"] == "VOID" and labels == 0
    # half a served T, a missing served run: the whole reading
    fresh = Dual(_positive, count=60)
    served_cell, v3_cell, labels = _void(fresh, fresh.dual_manifest(fresh.served_entries[:-1]))
    assert served_cell["reasons"] == ["served:grid_sessions_without_both_exchanges:1"] and v3_cell["reasons"] == ["primary_verdict_void"] and labels == 0
    missing = [{**fresh.served_entries[0], "run_key": "e" * 64}, *fresh.served_entries[1:]]
    assert _void(fresh, fresh.dual_manifest(missing))[0]["reasons"] == ["served:runs_missing:1"]
    # a V3 failure that leaves the served siblings intact (the V3 run superseded): the secondary verdict only
    fresh = Dual(_positive, count=60)
    first = fresh.entries[0]
    later = fresh.run(first["market"], date.fromisoformat(first["session_date"]), {s: 0.0 for m, s in fresh.names if m == first["market"]},
                      supersedes=first["run_key"], served=False)
    del later
    served_cell, v3_cell, labels = _void(fresh, fresh.dual_manifest())
    assert v3_cell["status"] == "VOID" and v3_cell["reasons"][0] == "runs_superseded:1" and labels == 0  # no V3 sibling: the served verdict voids too
    assert "served:v3_sibling_mismatch:1" in served_cell["reasons"]
    fresh = Dual(_positive, count=60)
    snapshot = next(item for item in fresh.database._analysis_snapshots if item["analysis_type"] == backtest.RUN_ANALYSIS_TYPE)
    snapshot["outputs"]["prediction_identities"].append(["ZZZ", "0" * 64])  # a V3 run incomplete: the served sibling is intact
    served_cell, v3_cell, labels = _void(fresh, fresh.dual_manifest())
    assert v3_cell["reasons"] == ["runs_incomplete:1"] and served_cell["status"] != "VOID" and labels > 0
    # a shared failure (manifest incomplete) voids both, reading no label
    fresh = Dual(_positive, count=60)
    served_cell, v3_cell, labels = _void(fresh, fresh.dual_manifest(complete=False))
    assert served_cell["reasons"] == v3_cell["reasons"] == ["manifest_not_complete"] and labels == 0
    with pytest.raises(backtest.ManifestError, match="appears twice"):  # the served entries are validated as the V3 ones
        backtest.load_manifest(json.dumps(fresh.dual_manifest([fresh.served_entries[0], fresh.served_entries[0]])))
    with pytest.raises(backtest.ManifestError, match="served_grid is not a list"):
        backtest.load_manifest(json.dumps(fresh.dual_manifest(served_grid={"x": 1})))


def test_every_served_run_must_be_its_v3_siblings_twin_screen_catalogue_coverage_and_link(small: None) -> None:
    store = Dual(_positive, count=60)
    snapshot = store.served_snapshot(store.served_entries[0])
    symbol = sorted(snapshot["outputs"]["screen"])[0]
    snapshot["outputs"]["screen"][symbol]["market_cap"] = 1.0  # another screen than the V3 run's
    served_cell, v3_cell, labels = _void(store, store.dual_manifest())
    assert served_cell["reasons"] == ["served:screen_not_the_v3_runs:1"] and v3_cell["reasons"] == ["primary_verdict_void"] and labels == 0
    for mutate in ("catalogue", "coverage", "link"):
        fresh = Dual(_positive, count=60)
        entries = fresh.served_entries
        snapshot = fresh.served_snapshot(entries[1])
        if mutate == "catalogue":
            snapshot["inputs"]["manifest"]["sources"][0]["classification_sha256"] = "d" * 64
        elif mutate == "coverage":
            snapshot["outputs"]["summary"]["statements"]["coverage"]["covered_in_catalogue"] = 7
        else:
            entries = [{**entry, "v3_run_key": "0" * 64} if index == 1 else entry for index, entry in enumerate(entries)]
        served_cell, _v3, labels = _void(fresh, fresh.dual_manifest(entries))
        assert "served:v3_sibling_mismatch:1" in served_cell["reasons"] and labels == 0, mutate


def test_the_workflow_reads_both_verdicts_and_the_look_is_one_across_revisions(small: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
                                                                               tmp_path: Path) -> None:
    from tests.test_valuation_pit_backtest_report import PREREG_PATH, SERVED_PRODUCER
    from tests.test_valuation_pit_backtest_workflow import _python, _real_receipt, _verify
    store = Dual(_positive, count=60)
    out, manifest = _real_receipt(store, monkeypatch, capsys, store.dual_manifest())
    refused = _verify(tmp_path, "report", out, expected_manifest=manifest["manifest_sha256"], served_producer=None)
    assert refused.returncode != 0 and "served producer" in refused.stderr  # a non-VOID served verdict needs the prereg commit's served producer
    other = _verify(tmp_path, "report", out, expected_manifest=manifest["manifest_sha256"],
                    served_producer={**SERVED_PRODUCER, "files": {**SERVED_PRODUCER["files"], "one_pager.py": "9" * 64}})
    assert other.returncode != 0 and "served producer" in other.stderr
    accepted = _verify(tmp_path, "report", out, expected_manifest=manifest["manifest_sha256"])
    assert accepted.returncode == 0, accepted.stderr
    metadata = json.loads((tmp_path / "out" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["verdicts"] == {"primary": "served_internal_tp", "served_internal_tp": "FAIL", "v3_shadow": "FAIL"}
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "served_internal_tp (PRIMARY: the TP served)" in summary and "v3_shadow (secondary)" in summary
    prereg_sha = hashlib.sha256(PREREG_PATH.read_bytes()).hexdigest()
    cases = {"served spent the look": ({"prereg_sha256": prereg_sha, "manifest_sha256": "a" * 64, "verdict": "VOID",
                                         "verdicts": {"served_internal_tp": "FAIL", "v3_shadow": "VOID"}}, False),
             "another revision's non-VOID reading": ({"prereg_sha256": "9" * 64, "manifest_sha256": "a" * 64, "verdict": "FAIL",
                                                      "verdicts": {"served_internal_tp": "VOID", "v3_shadow": "FAIL"}}, False),
             "another revision, same manifest": ({"prereg_sha256": "9" * 64, "manifest_sha256": "b" * 64, "verdict": "FAIL"}, False),
             "another revision, all VOID": ({"prereg_sha256": "9" * 64, "manifest_sha256": "a" * 64, "verdict": "VOID",
                                             "verdicts": {"served_internal_tp": "VOID", "v3_shadow": "VOID"}}, True)}
    for index, (name, (metadata, passes)) in enumerate(cases.items()):
        previous = tmp_path / f"previous-{index}"
        (previous / "1").mkdir(parents=True)
        (previous / "1" / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        result = _python("Check the single look", str(previous), str(PREREG_PATH), env={"EXPECTED": "b" * 64})
        assert (result.returncode == 0) is passes and (passes or "single look was spent" in result.stderr), name


# ------------------------------------------------------------------ the real equivalence: a consistent provider payload, live vs point-in-time
def _consistent_raw(symbol: str, payload: dict[str, Any], *, price: float, beta: float | None) -> dict[str, Any]:
    """A full EODHD payload whose current blocks AGREE with its Financials and the price at T (T after every filing),
    computed here by hand: the TTM of the four newest quarters, the newest balance, the growth over the quarter a year before."""
    financials = payload["Financials"]
    quarters = financials["Income_Statement"]["quarterly"]
    newest = sorted(quarters, reverse=True)[:4]
    ttm = {field: sum(quarters[key][field] for key in newest) for field in ("netIncome", "totalRevenue", "operatingIncome", "ebitda")}
    balance = financials["Balance_Sheet"]["quarterly"][newest[0]]
    shares, equity = balance["commonStockSharesOutstanding"], balance["totalStockholderEquity"]
    net_debt = balance["shortTermDebt"] + balance["longTermDebt"] - balance["cashAndEquivalents"]
    year_ago = sorted(quarters)[-5]
    growth = {field: quarters[newest[0]][field] / quarters[year_ago][field] - 1 for field in ("totalRevenue", "netIncome")}
    eps = ttm["netIncome"] / shares
    return {"General": {"Code": symbol, "Name": symbol, "Sector": "Industrials", "Industry": "Machinery", "Type": "Common Stock"},
            "Highlights": {"MarketCapitalization": price * shares, "DilutedEpsTTM": eps, "BookValue": equity / shares, "ReturnOnEquityTTM": ttm["netIncome"] / equity,
                           "ProfitMargin": ttm["netIncome"] / ttm["totalRevenue"], "OperatingMarginTTM": ttm["operatingIncome"] / ttm["totalRevenue"],
                           "EBITDA": ttm["ebitda"], "RevenueTTM": ttm["totalRevenue"], "QuarterlyRevenueGrowthYOY": growth["totalRevenue"],
                           "QuarterlyEarningsGrowthYOY": growth["netIncome"]},
            "Valuation": {"TrailingPE": price / eps, "EnterpriseValueEbitda": (price * shares + net_debt) / ttm["ebitda"]}, "Technicals": {"Beta": beta},
            "SharesStats": {"SharesOutstanding": shares}, "AnalystRatings": {}, "Earnings": {}, "Financials": json.loads(json.dumps(financials))}


TP_FIELDS = ("trailingEps", "bookValue", "sharesOutstanding", "ebitda", "totalCash", "totalDebt", "returnOnEquity", "profitMargins", "operatingMargins",
             "revenueGrowthAnnual", "earningsGrowthAnnual", "trailingPE", "enterpriseToEbitda", "marketCap", "beta", "freeCashflow")
ROW_FIELDS = {"quarterlyIncome": ("date", "totalRevenue", "netIncome", "operatingIncome", "ebitda"),
              "quarterlyCashFlow": ("date", "freeCashFlow", "totalCashFromOperatingActivities"),
              "quarterlyBalance": ("date", "totalStockholderEquity", "cashAndEquivalents")}


def _assert_same_shape(live: dict[str, Any], pit_shape: dict[str, Any]) -> None:
    for field in TP_FIELDS:
        if field == "freeCashflow":  # the latest quarter's (the normaliser's), unused while the four quarters sum: compared as the One Pager reads it
            assert OnePagerService._sum_rows(live["quarterlyCashFlow"], "freeCashFlow", 4) == pytest.approx(
                OnePagerService._sum_rows(pit_shape["quarterlyCashFlow"], "freeCashFlow", 4)), field
            continue
        assert pit_shape[field] == pytest.approx(live[field], rel=1e-12), field
    for block, fields in ROW_FIELDS.items():
        for live_row, pit_row in zip(live[block][:4], pit_shape[block][:4], strict=True):
            assert {key: pit_row.get(key) for key in fields} == pytest.approx({key: live_row.get(key) for key in fields}), block
    debt = [(row.get("shortTermDebt") or 0) + (row.get("longTermDebt") or 0) for row in (live["quarterlyBalance"][0], pit_shape["quarterlyBalance"][0])]
    assert debt[0] == pytest.approx(debt[1])


@pytest.mark.parametrize("statements", ["provider", "vintages"])
def test_live_and_point_in_time_normalised_fundamentals_agree_field_by_field_and_give_the_same_tp(statements: str, tmp_path: Path) -> None:
    with asfiled_front.installed() as front:
        database = _ready()
        payloads = {}
        for symbol in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"):
            payloads[symbol] = _consistent_payload(symbol)
            _republish_payload(database, symbol, payloads[symbol])
            if statements == "vintages":
                _file_payload(front, database, symbol, payloads[symbol])
        run = _served(database, statements=statements)
        assert run.summary()["statements"]["basis"] == ({"provider_payload": 6} if statements == "provider" else {"statement_vintages": 6})
        live_shapes: dict[str, dict[str, Any]] = {}
        for symbol, item in run.resolver.per_symbol.items():
            live_shapes[symbol] = EodhdClient._normalize_fundamentals(_consistent_raw(symbol, payloads[symbol], price=item["row"]["price"], beta=item["row"]["beta"]))
            _assert_same_shape(live_shapes[symbol], served.fundamentals_at(symbol, run.resolver.payloads[symbol], item, market="NASDAQ",
                                                                           economic_date=run.resolver.economic_date, excluded=Counter()))
        assert run.summary()["pit_excluded_inputs"].get("served_ttm_sum_incomplete:ebitda") is None  # four consecutive complete quarters: kept
        live = _live(tmp_path)
        medians = OnePagerService._us_peer_medians(live_shapes)
        assert medians == run.manifest["peer_medians"]
        records = {record["symbol"]: record for record in run.records(cycle_id="c", published_at=NOW)}
        for symbol, shape in live_shapes.items():
            quote = {"symbol": symbol, "price": run.resolver.per_symbol[symbol]["row"]["price"], "currency": "USD", "as_of": T.isoformat()}
            row = live._analyze_stock("NASDAQ", quote, shape, [], 0.0, risk_free_rate=run.manifest["risk_free"]["rate"], peer_medians=medians)
            assert records[symbol]["tp"] == pytest.approx(row["internal_tp"], rel=1e-12) and records[symbol]["buy_in"] == pytest.approx(row["internal_buy_in"], rel=1e-12)


def _mutate_provider_payloads(database: Database, change: Any) -> None:
    for snapshot in database._analysis_snapshots:  # type: ignore[attr-defined]
        payload = (snapshot.get("outputs") or {}).get("payload")
        if snapshot["analysis_type"] == pit.SOURCE_ANALYSIS_TYPE and isinstance(payload, dict) and "Financials" in payload:
            change(payload["Financials"])


def _shape(run: served.ServedComputation, symbol: str = "AAA") -> dict[str, Any]:
    return served.fundamentals_at(symbol, run.resolver.payloads[symbol], run.resolver.per_symbol[symbol], market="NASDAQ",
                                  economic_date=run.resolver.economic_date, excluded=Counter())


def test_a_partial_quarter_never_lets_the_one_pager_sum_fewer_than_four_quarters() -> None:
    database = _ready()

    def partial(financials: dict[str, Any]) -> None:
        financials["Income_Statement"]["quarterly"]["2024-03-31"].pop("ebitda")
        financials["Cash_Flow"]["quarterly"]["2024-03-31"].pop("freeCashFlow")

    _mutate_provider_payloads(database, partial)
    run = _served(database)
    shape = _shape(run)
    fundamentals = pit.pit_fundamentals(run.resolver.payloads["AAA"], market="NASDAQ", economic_date=run.resolver.economic_date)
    assert all("ebitda" not in row for row in shape["quarterlyIncome"]) and all("freeCashFlow" not in row for row in shape["quarterlyCashFlow"])
    assert OnePagerService._sum_rows(shape["quarterlyIncome"], "ebitda", 4) is None  # the One Pager falls back to the rebuilt TTM
    assert shape["ebitda"] == fundamentals["ttm"]["ebitda"] and shape["freeCashflow"] == fundamentals["cash_flow_ttm"]["free_cash_flow"]
    counted = run.summary()["pit_excluded_inputs"]
    assert counted["served_ttm_sum_incomplete:ebitda"] == 6 and counted["served_ttm_sum_incomplete:freeCashFlow"] == 6


def test_a_gap_quarter_never_lets_the_one_pager_sum_around_it_and_the_fiscal_year_serves() -> None:
    database = _ready()

    def gap(financials: dict[str, Any]) -> None:
        for statement in ("Income_Statement", "Cash_Flow"):
            financials[statement]["quarterly"].pop("2023-09-30")

    _mutate_provider_payloads(database, gap)
    run = _served(database)
    shape = _shape(run)
    yearly = run.resolver.payloads["AAA"]["Financials"]
    assert OnePagerService._sum_rows(shape["quarterlyIncome"], "ebitda", 4) is None and OnePagerService._sum_rows(shape["quarterlyCashFlow"], "freeCashFlow", 4) is None
    assert shape["ebitda"] == pytest.approx(yearly["Income_Statement"]["yearly"]["2023-12-31"]["ebitda"])  # the latest fiscal year (the TTM's fallback)
    assert shape["freeCashflow"] == pytest.approx(yearly["Cash_Flow"]["yearly"]["2023-12-31"]["freeCashFlow"])
    assert run.summary()["pit_excluded_inputs"]["served_ttm_sum_incomplete:ebitda"] == 6


def test_a_programming_error_is_raised_never_counted_as_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _ready()
    for error in (AttributeError, NameError, KeyError):
        monkeypatch.setattr(served, "analyze", lambda *args, _error=error, **kwargs: (_ for _ in ()).throw(_error("bug")))
        with pytest.raises(error):
            _served(database)
    monkeypatch.setattr(served, "analyze", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("no methods")))
    run = _served(database)
    assert run.results == {} and set(run.not_evaluable.values()) == {"producer_refused"} and run.summary()["pit_excluded_inputs"]["producer_refused:ValueError"] == 6


# ------------------------------------------------------------------ no clock in the economic computation (both statements modes)
_REAL_DATETIME, _REAL_DATE = datetime, date


class _DtMeta(type):
    def __instancecheck__(cls, obj: Any) -> bool:
        return isinstance(obj, _REAL_DATETIME)


class _DMeta(type):
    def __instancecheck__(cls, obj: Any) -> bool:
        return isinstance(obj, _REAL_DATE)


class _ExplodingDatetime(datetime, metaclass=_DtMeta):
    @classmethod
    def now(cls, tz: Any = None) -> Any:  # type: ignore[override]
        raise AssertionError("wall clock read (datetime.now)")

    @classmethod
    def today(cls) -> Any:  # type: ignore[override]
        raise AssertionError("wall clock read (datetime.today)")

    @classmethod
    def utcnow(cls) -> Any:  # type: ignore[override]
        raise AssertionError("wall clock read (utcnow)")


class _ExplodingDate(date, metaclass=_DMeta):
    @classmethod
    def today(cls) -> Any:  # type: ignore[override]
        raise AssertionError("wall clock read (date.today)")


@pytest.mark.parametrize("statements", ["provider", "vintages"])
def test_no_path_of_the_served_computation_reads_now(statements: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib
    with asfiled_front.installed() as front:
        database = _ready()
        if statements == "vintages":
            for symbol in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"):
                consistent = _consistent_payload(symbol)
                _republish_payload(database, symbol, consistent)
                _file_payload(front, database, symbol, consistent)
        prices = _service(database).pin_vintage("NASDAQ", as_of=T, pinned_at=NOW)
        service = served.PitServedService(database, settings=_settings())
        modules = [served, pit, importlib.import_module("app.one_pager"), importlib.import_module("app.market_data.us_screener"),
                   importlib.import_module("app.market_data.eodhd"), official, importlib.import_module("app.valuation_official_engine"),
                   importlib.import_module("app.valuation_v3_macro"), importlib.import_module("app.valuation_price_history")]
        for name in ("app.statement_vintages", "app.sec_xbrl", "app.valuation_asfiled"):
            try:
                modules.append(importlib.import_module(name))
            except ImportError:
                pass
        for module in modules:
            if hasattr(module, "datetime"):
                monkeypatch.setattr(module, "datetime", _ExplodingDatetime)
            if hasattr(module, "date"):
                monkeypatch.setattr(module, "date", _ExplodingDate)
        computation = service.compute("NASDAQ", as_of=T, prices=prices, statements=statements)
        assert len(computation.results) == 6 and len(computation.records(cycle_id="c", published_at=NOW)) == 6
        monkeypatch.undo()


# ------------------------------------------------------------------ the curve's unit: percent, per series
def _history(three: float, ten: float) -> dict[str, Any]:
    return {"source": "EODHD Government Bonds", "fetched_at": NOW.isoformat(),
            "series": {"US3Y.GBOND": [{"date": "2021-06-01", "close": three}], "US10Y.GBOND": [{"date": "2021-06-01", "close": ten}]}}


def test_the_treasury_history_is_percent_per_series_sub_one_percent_yields_included() -> None:
    from app import valuation_v3_macro as macro
    at = datetime(2021, 6, 2, 4, 0, tzinfo=UTC)
    package = pit.curve_package_at(_history(0.30, 1.60), as_of=at, economic_date=date(2021, 6, 2))
    assert package is not None
    rates = {point["tenor_years"]: point["annual_rate"] for point in package["points"]}
    assert rates == {3: pytest.approx(0.003), 10: pytest.approx(0.016)}  # 0.30 % is 0.003, never 30 %
    assert package["interpolated_5y_rate"] == pytest.approx(0.003 + (2 / 7) * (0.016 - 0.003))
    for bad in (_history(25.0, 1.6), {**_history(0.3, 1.6), "source": "another provider"}):
        with pytest.raises(pit.PitRerunInputError):
            pit.curve_package_at(bad, as_of=at, economic_date=date(2021, 6, 2))
    # the live macro path reads the same series the same way: identical above 1 %, percent below, refused out of range
    assert macro._percent_rate("4.25", series="US10Y.GBOND") == macro._annual_rate("4.25") == pytest.approx(0.0425)
    assert macro._percent_rate(0.3, series="US3Y.GBOND") == pytest.approx(0.003) and macro._annual_rate(0.3) == 0.3  # the old per-value guess
    assert macro._percent_rate(0, series="US3Y.GBOND") is None
    with pytest.raises(macro.ValuationV3MacroDataError, match="US3Y.GBOND"):
        macro._percent_rate(30.0, series="US3Y.GBOND")
    assert "_percent_rate(item.get(\"close\"), series=symbol)" in Path(macro.__file__).read_text(encoding="utf-8")
    assert "curve_unit" in pit.DECLARED_ASSUMPTIONS  # in every V3 run's manifest (a new V3 identity: no run of the grid exists yet)


# ------------------------------------------------------------------ the grid: served beside a reused V3 run; the stop between the two
def test_a_reused_v3_run_gets_its_served_sibling_computed_on_its_own_pin_and_the_stop_is_checked_between_them(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    short_grid(monkeypatch)
    database = _store()
    assert grid.main(_args(tmp_path / "v3.json", "--to", "2024-06-10", "--sources", "v3_2_shadow"), database=database, settings=_settings()) == 0
    assert grid.main(_args(tmp_path / "both.json", "--to", "2024-06-10"), database=database, settings=_settings()) == 0
    both, v3 = _grid_manifest(tmp_path / "both.json"), _grid_manifest(tmp_path / "v3.json")
    assert all(entry["reused"] for entry in both["grid"]) and not any(entry["reused"] for entry in both["served_grid"])
    assert [entry["run_key"] for entry in both["grid"]] == [entry["run_key"] for entry in v3["grid"]]
    assert [entry["v3_run_key"] for entry in both["served_grid"]] == [entry["run_key"] for entry in both["grid"]]
    capsys.readouterr()
    fresh = _store()
    calls = {"n": 0}

    def stop_on_the_third(self: grid.GridRun, stop_before: Any, *, predict: Any) -> str | None:
        calls["n"] += 1
        return "stop_before" if calls["n"] == 3 else None  # 1: before T, 2: before the NASDAQ V3 run, 3: before its served run

    monkeypatch.setattr(grid.GridRun, "_stop_reason", stop_on_the_third)
    assert grid.main(_args(tmp_path / "stopped.json", "--to", "2024-06-10"), database=fresh, settings=_settings()) == 0
    stopped = _grid_manifest(tmp_path / "stopped.json")
    assert stopped["grid"] == [] and stopped["served_grid"] == [] and stopped["stopped"]["source"] == "official_internal_pit"
    # by prediction before any instant is measured: 300 s per run, a served run per V3 run → 4 runs per T, × 1.5 = 1,800 s
    monkeypatch.undo()
    short_grid(monkeypatch)
    now = datetime.now(UTC)
    for seconds, starts in ((1700, False), (1900, True)):
        run = grid.GridRun(_store(), _settings(), market_group="US", price_pinned_at=PIN, catalogue_pinned_at=CATALOGUE_PIN, statements="provider", step=5,
                           clock=lambda: now, monotonic=lambda: 0.0, emit=lambda line: None)
        result = run.run(start=None, end=date(2024, 6, 3), max_runs=None, stop_before=now + timedelta(seconds=seconds), recompute_existing=False,
                         owner_order_sha256=None)
        assert (result["stopped"] is None) is starts and (len(result["served_grid"]) == 2) is starts, seconds
    capsys.readouterr()
