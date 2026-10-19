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
from typing import Any, Iterator
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
        fundamentals = served.fundamentals_at(symbol, run.resolver.payloads[symbol], item, market="NASDAQ", economic_date=run.resolver.economic_date,
                                              session_date=run.resolver.prices.session_date, excluded=Counter())
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
                                                                                            economic_date=run.resolver.economic_date,
                                                                                            session_date=run.resolver.prices.session_date, excluded=Counter())
                                                             for symbol, item in run.resolver.per_symbol.items()})


def test_the_provider_shape_is_rebuilt_from_the_statements_eligible_at_t_only() -> None:
    database = _ready()
    run = _served(database)
    item = run.resolver.per_symbol["AAA"]
    fundamentals = served.fundamentals_at("AAA", run.resolver.payloads["AAA"], item, market="NASDAQ", economic_date=run.resolver.economic_date,
                                          session_date=run.resolver.prices.session_date, excluded=Counter())
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
                                   economic_date=before.resolver.economic_date, session_date=before.resolver.prices.session_date, excluded=Counter())
    assert shape["quarterlyIncome"][0]["date"] == "2023-12-31" and all(row["date"] <= "2023-12-31" for row in shape["quarterlyIncome"])
    counted = run.summary()["pit_excluded_inputs"]
    assert counted["forward_eps:absent_trailing_eps_used"] == 6 and counted["forward_eps:no_point_in_time_history"] == 6  # absent → trailing, counted
    assert counted["insider_activity:no_point_in_time_history"] == 6 and counted["consensus:never_in_the_internal_tp"] == 6
    assert counted["earnings_surprise:no_dated_history_in_the_statements_payload"] == 6


def test_the_earnings_history_keeps_only_the_rows_reported_by_the_session_of_t() -> None:
    excluded: Counter[str] = Counter()
    payload = {"Earnings": {"History": {"2024-03-31": {"reportDate": "2024-05-02", "surprisePercent": 5.0},
                                        "2024-06-30": {"reportDate": "2024-08-01", "surprisePercent": 30.0},
                                        "2023-12-31": {"surprisePercent": 1.0}}}}
    kept = served.earnings_history_at(payload, session_date="2024-06-14", excluded=excluded)
    assert list(kept) == ["2024-03-31"] and excluded == {"earnings_surprise:reported_after_T": 1, "earnings_surprise:row_without_report_date": 1}
    assert served.earnings_history_at({}, session_date="2024-06-14", excluded=excluded) == {}


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


# ------------------------------------------------------------------ the report: two verdicts
class Dual(Synthetic):
    """``Synthetic`` with the served source: beside every V3 run, a served run of the same (exchange, T) — its records inside
    its snapshot, as ``valuation_pit_served`` writes them — whose upside is the V3 upside × ``sign``."""

    def __init__(self, *args: Any, sign: float = 1.0, **kwargs: Any) -> None:
        self.sign = sign
        self.served_entries: list[dict[str, Any]] = []
        super().__init__(*args, **kwargs)

    def run(self, market: str, day: date, upsides: dict[str, float], **kwargs: Any) -> dict[str, Any]:
        entry = super().run(market, day, upsides, **kwargs)
        if not kwargs:
            self.served_entries.append(self.served_run(market, day, {s: u * self.sign for s, u in upsides.items()}, v3_run_key=entry["run_key"]))
        return entry

    def served_run(self, market: str, day: date, upsides: dict[str, float], *, v3_run_key: str, tamper: str | None = None) -> dict[str, Any]:
        instant = backtest.t_instant(day)
        run_key = hashlib.sha256(f"served|{market}|{day.isoformat()}|{uuid4()}".encode()).hexdigest()
        cycle_id = str(uuid4())
        published = self.published + timedelta(seconds=len(self.database._analysis_snapshots))
        records = []
        for symbol, upside in sorted(upsides.items()):
            price = self.closes[symbol][day]
            tp = price * (1.0 + upside)
            record = official.prediction_from_row({"symbol": symbol, "internal_tp": tp, "internal_buy_in": tp * 0.8, "price": price, "status": "retrospective"},
                                                  market=market, scope="universe", cycle_id=cycle_id, source_version="pit-served-v1+synthetic000",
                                                  prediction_instant=instant, published_at=published, source=official.SOURCE_INTERNAL,
                                                  extra_provenance={"run_key": run_key})
            assert record is not None
            records.append(served.relabelled(record))
        if tamper == "tp":
            records[0] = {**records[0], "tp": records[0]["tp"] * 2}  # not re-hashed
        elif tamper == "source":
            core = {k: v for k, v in records[0].items() if k not in ("id", "row_sha256")}
            core["source"] = official.SOURCE_V3_2_SHADOW
            records[0] = {**core, "id": records[0]["id"], "row_sha256": official.canonical_sha256(core)}
        inputs = {"run_key": run_key, "market": market, "as_of": instant.isoformat(), "source": served.SOURCE, "source_version": "pit-served-v1+synthetic000",
                  "price_pin": {"mode": "explicit", "requested_at": "x", "resolved_publication_id": self.pins[market]["publication_id"]},
                  "catalogue_pin": {"mode": "explicit", "requested_at": "x", "resolved_snapshot_id": "catalogue-1"},
                  "manifest": {"session_date": day.isoformat(), "engine": {"implementation_file_sha256": {"one_pager.py": "1" * 64}, "implementation_object_sha256": OBJECTS},
                               "price_vintage": {}, "sources": [{"role": "catalogue", "market": market, "classification_sha256": "c" * 64, "rows": 18}]}}
        screen = {symbol: {"security_type": "Stock", "close": self.closes[symbol][day], "market_cap": 5e9, "dollar_volume_median_20": 1e8 + index,
                           "split_adjusted_dollar_volume_median_20": 1e6 + index} for index, symbol in enumerate(sorted(upsides))}
        outputs = {"summary": {"evaluated": len(records), "with_internal_tp": len(records), "not_evaluable": {},
                               "statements": {"mode": "vintages", "table_present": True, "basis": {"statement_vintages": len(records)},
                                              "coverage": {"covered": 40, "covered_in_catalogue": 16, "covered_without_rows_by_T": 0}}},
                   "records": records, "prediction_identities": [[r["symbol"], r["row_sha256"]] for r in records], "screen": screen,
                   "catalogue_counts": {"rows": len(records) + 3, "stocks": len(records)}, "rows": {}}
        self.database.save_analysis_snapshot(backtest.SERVED_RUN_ANALYSIS_TYPE, f"{market}_PITSERVED_{run_key[:16]}", "mv-pit", inputs, outputs, published,
                                             snapshot_id=cycle_id)
        return {"as_of": instant.isoformat(), "session_date": day.isoformat(), "market": market, "run_key": run_key, "cycle_id": cycle_id, "idempotent": False,
                "reused": False, "evaluated": len(records), "records": len(records), "not_evaluable": {}, "v3_run_key": v3_run_key}

    def dual_manifest(self, served_entries: list[dict[str, Any]] | None = None, **changes: Any) -> dict[str, Any]:
        return self.manifest(sources=list(grid.SOURCES), served_grid=self.served_entries if served_entries is None else served_entries, **changes)


def test_the_receipt_carries_two_verdicts_each_its_own_decision_and_the_labels_are_read_once(small: None) -> None:
    store = Dual(_positive, sign=-1.0)  # the V3 shadow ranks the returns; the served TP ranks them backwards
    service = store.service()
    receipt = service.report(store.dual_manifest(), prereg_sha256="f" * 64, code_pins=accuracy.pins_of(backtest.code_fingerprint()))
    payload = receipt["payload"]
    verdicts = payload["verdicts"]
    assert verdicts["primary"] == "served_internal_tp" and verdicts["v3_shadow"] == payload["verdict"] and payload["verdict"]["status"] == "PASS"
    assert verdicts["served_internal_tp"] == payload["served_internal_tp"]["verdict"] and verdicts["served_internal_tp"]["status"] == "NEGATIVE"
    block = payload["served_internal_tp"]
    assert block["records"]["admissible"] == 58 * 30 and block["records"]["refused"] == {} and block["runs"]["status"] == {"current": 116}
    assert block["coverage"]["US"]["records_share"] == 1.0 and block["screen"]["screened"] == 58 * 30 and block["grid"]["status"] == "PREREG"
    assert block["horizons"]["10"]["ic_executable"]["blocks"]["estimate"] == pytest.approx(-payload["horizons"]["10"]["ic_executable"]["blocks"]["estimate"], abs=0.1)
    assert service.labels_read == 58 * 30 * len(backtest.label_horizons())  # one label per (symbol, session, horizon): never twice for two sources
    assert payload["protocol"]["verdicts"]["primary"] == "served_internal_tp" and "no multiplicity correction" in payload["protocol"]["verdicts"]["rule"]
    assert not any(symbol in json.dumps(receipt) for _m, symbol in store.names)
    # the same served TP as the V3 one: the same verdict, computed separately
    same = Dual(_positive)
    cell = same.service().report(same.dual_manifest(), prereg_sha256="f" * 64, code_pins=accuracy.pins_of(backtest.code_fingerprint()))["payload"]
    assert cell["verdicts"]["served_internal_tp"]["status"] == cell["verdicts"]["v3_shadow"]["status"] == "PASS"
    assert cell["verdicts"]["served_internal_tp"]["ic_estimate"] == cell["verdicts"]["v3_shadow"]["ic_estimate"]


def test_a_failure_of_one_source_voids_its_verdict_only_and_a_shared_failure_voids_both(small: None) -> None:
    binding = {"prereg_sha256": "f" * 64, "code_pins": accuracy.pins_of(backtest.code_fingerprint())}

    def verdicts(store: Dual, manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = store.service().report(manifest, **binding)["payload"]["verdicts"]
        return payload["served_internal_tp"], payload["v3_shadow"]

    store = Dual(_positive, count=60)
    served_cell, v3_cell = verdicts(store, store.manifest())  # a rev-1 manifest: no served source
    assert served_cell["status"] == "VOID" and "served:source_not_in_manifest" in served_cell["reasons"] and v3_cell["status"] != "VOID"
    # routing mutations: a served record whose identity does not recompute, or that claims the V3 source, voids the SERVED verdict only
    for tamper, reason in (("tp", "served:records_refused:identity_not_verified:1"), ("source", "served:records_refused:record_not_of_its_run:1")):
        fresh = Dual(_positive, count=60)
        first = fresh.served_entries[0]
        bad = fresh.served_run(first["market"], date.fromisoformat(first["session_date"]), {s: 0.1 for m, s in fresh.names if m == first["market"]},
                               v3_run_key=first["v3_run_key"], tamper=tamper)
        served_cell, v3_cell = verdicts(fresh, fresh.dual_manifest([bad, *fresh.served_entries[1:]]))
        assert served_cell["status"] == "VOID" and reason in served_cell["reasons"] and v3_cell["status"] != "VOID", (tamper, served_cell["reasons"])
    # a served run superseded/missing, or half a served T: the served verdict only
    fresh = Dual(_positive, count=60)
    served_cell, v3_cell = verdicts(fresh, fresh.dual_manifest(fresh.served_entries[:-1]))
    assert served_cell["reasons"] == ["served:grid_sessions_without_both_exchanges:1"] and v3_cell["status"] != "VOID"
    missing = [{**fresh.served_entries[0], "run_key": "e" * 64}, *fresh.served_entries[1:]]
    served_cell, _ = verdicts(fresh, fresh.dual_manifest(missing))
    assert served_cell["reasons"] == ["served:runs_missing:1"]
    # a V3 failure leaves the served verdict standing; a shared one (manifest incomplete) voids both, reading no label
    v3_bad = [{**fresh.entries[0], "run_key": "e" * 64}, *fresh.entries[1:]]
    served_cell, v3_cell = verdicts(fresh, fresh.dual_manifest(grid=v3_bad))
    assert v3_cell["reasons"] == ["runs_missing:1"] and served_cell["status"] != "VOID"
    service = fresh.service()
    both = service.report(fresh.dual_manifest(complete=False), **binding)["payload"]
    assert both["verdicts"]["served_internal_tp"]["reasons"] == both["verdicts"]["v3_shadow"]["reasons"] == ["manifest_not_complete"]
    assert service.labels_read == 0 and both["served_internal_tp"]["horizons"] is None and both["horizons"] is None
    # the served records are read from the served snapshots only: a V3 record of the same instant never enters the served reading
    assert verdicts(fresh, fresh.dual_manifest())[0]["status"] != "VOID"
    with pytest.raises(backtest.ManifestError, match="appears twice"):  # the served entries are validated as the V3 ones
        backtest.load_manifest(json.dumps(fresh.dual_manifest([fresh.served_entries[0], fresh.served_entries[0]])))
    with pytest.raises(backtest.ManifestError, match="served_grid is not a list"):
        backtest.load_manifest(json.dumps(fresh.dual_manifest(served_entries={"x": 1})))  # type: ignore[arg-type]


def test_the_workflow_reads_both_verdicts_and_a_served_reading_spends_the_look(small: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
                                                                                tmp_path: Path) -> None:
    from tests.test_valuation_pit_backtest_report import PREREG_PATH
    from tests.test_valuation_pit_backtest_workflow import PRODUCER, _python, _real_receipt, _verify
    store = Dual(_positive, count=60)
    out, manifest = _real_receipt(store, monkeypatch, capsys, store.dual_manifest())
    refused = _verify(tmp_path, "report", out, expected_manifest=manifest["manifest_sha256"])
    assert refused.returncode != 0 and "served producer" in refused.stderr  # a non-VOID served verdict needs the prereg commit's served producer
    payload = json.loads(out)["payload"]
    (tmp_path / "served-producer.json").write_text(json.dumps({"files": payload["served_internal_tp"]["runs"]["producer"]["engine_files"],
                                                               "objects": payload["served_internal_tp"]["runs"]["producer"]["engine_objects"]}), encoding="utf-8")
    accepted = _verify(tmp_path, "report", out, expected_manifest=manifest["manifest_sha256"], producer=PRODUCER)
    assert accepted.returncode == 0, accepted.stderr
    metadata = json.loads((tmp_path / "out" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["verdicts"] == {"primary": "served_internal_tp", "served_internal_tp": "FAIL", "v3_shadow": "FAIL"}
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "served_internal_tp (PRIMARY: the TP served)" in summary and "v3_shadow (secondary)" in summary
    previous = tmp_path / "previous"
    (previous / "1").mkdir(parents=True)
    prereg_sha = hashlib.sha256(PREREG_PATH.read_bytes()).hexdigest()
    (previous / "1" / "metadata.json").write_text(json.dumps({"prereg_sha256": prereg_sha, "manifest_sha256": "a" * 64, "verdict": "VOID",
                                                              "verdicts": {"served_internal_tp": "FAIL", "v3_shadow": "VOID"}}), encoding="utf-8")
    spent = _python("Check the single look", str(previous), str(PREREG_PATH), env={"EXPECTED": "b" * 64})
    assert spent.returncode != 0 and "single look was spent" in spent.stderr  # the V3 verdict VOID, the served one not: the look is spent
