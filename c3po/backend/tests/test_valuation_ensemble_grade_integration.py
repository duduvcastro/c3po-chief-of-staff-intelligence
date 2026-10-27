"""Synthetic canonical PIT readers through private artifacts to the guarded report.

Only reference/signature anchors and the reduced session calendar are synthetic
substitutions. The database, financial computation, source comparison, artifact
store and reporter are their concrete implementations. Outcomes stay missing.
"""
from __future__ import annotations

import copy
import hashlib
import http.client
import json
import socket
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app import valuation_ensemble_calendar as calendar
from app import valuation_ensemble_executor as executor
from app import valuation_ensemble_pin as instrument
from app import valuation_ensemble_report as report
from app.valuation_ensemble_grid import paired_source_identity, validate_record_pair
from app.valuation_ensemble_inputs import canonical_hash
from app.valuation_ensemble_models import MODEL_IDS
from app.valuation_ensemble_persistence import FileReceiptStore
from app.valuation_pit_rerun import PinnedPrices
from tests.test_valuation_ensemble_grid import T, _fixture


NOW = datetime(2026, 10, 27, 13, 10, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _forbid_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("real network is forbidden in grade integration fixtures")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", forbidden)


@pytest.fixture
def integrated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    database, prices, v3, served = _fixture(etf="FFF")
    assert isinstance(prices, PinnedPrices)
    session = prices.session_date
    slot = {"market": "NASDAQ", "session_date": session, "as_of": T.isoformat()}
    rev3 = {"complete": True, "statements": "vintages", "grid_start": "2021-06-01",
            "volume_basis": {"decision": "as_traded"},
            "grid": [{**slot, "run_key": v3["inputs"]["run_key"], "cycle_id": v3["id"]}],
            "served_grid": [{**slot, "run_key": served["inputs"]["run_key"],
                             "cycle_id": served["id"], "v3_run_key": v3["inputs"]["run_key"]}]}
    rev3["manifest_sha256"] = canonical_hash(rev3)
    # A six-name unit reference is not the published historical grade manifest.
    for module in (executor, instrument, report):
        monkeypatch.setattr(module, "REV3_MANIFEST_SHA256", rev3["manifest_sha256"])
    descriptor = {"index_of": {session: 0},
                  "mature_through": {str(h): 0 for h in (21, 22, 63, 64, 126, 127, 252, 253)},
                  "partition_last": 0}
    monkeypatch.setattr(calendar, "report_calendar_for", lambda source: copy.deepcopy(descriptor))
    files = instrument.instrument_file_hashes()
    pin = {"schema": instrument.PIN_SCHEMA, "prereg_commit": instrument.PREREG_COMMIT,
           "prereg_sha256": instrument.PREREG_SHA256, "instrument_commit": "1" * 40,
           "owner_signature_comment_id": 1, "technical_GO_comment_id": 2,
           "published_at": (NOW - timedelta(minutes=10)).isoformat(), "files": files,
           "constants": instrument.PROTOCOL_CONSTANTS}
    binding = instrument.InstrumentBinding(canonical_hash(pin), instrument.PREREG_COMMIT, "1" * 40, 1, 2)
    order = {"schema": executor.ORDER_SCHEMA, "prereg": executor.PREREG, "modes": ["grid"],
             "prereg_commit": instrument.PREREG_COMMIT, "prereg_sha256": instrument.PREREG_SHA256,
             "instrument_pin_sha256": binding.expected_pin_sha256,
             "rev3_manifest_sha256": rev3["manifest_sha256"], "from_session": session,
             "to_session": session, "max_runs_cap": 1,
             "not_before": (NOW - timedelta(hours=1)).isoformat(),
             "not_after": (NOW + timedelta(hours=1)).isoformat()}
    raw = json.dumps(order, sort_keys=True).encode()
    store = FileReceiptStore(tmp_path / "receipts")
    events: list[str] = []

    def pinned_prices(reference: Any) -> PinnedPrices:
        assert reference == rev3["grid"][0]
        events.append("pinned_prices")
        return prices

    def guard() -> None:
        events.append("synthetic_operational_guard")

    def no_database_write(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the grade calculation must not persist a database snapshot")

    monkeypatch.setattr(database, "save_analysis_snapshot", no_database_write)
    args = {"rev3_manifest": rev3, "pin": pin, "binding": binding, "file_hashes": files,
            "owner_order_bytes": raw, "owner_order_sha256": hashlib.sha256(raw).hexdigest(),
            "store": store, "prices_for": pinned_prices, "operational_guard": guard,
            "report_calendar": descriptor, "max_runs": 1,
            "stop_before": NOW + timedelta(hours=1), "clock": lambda: NOW}
    manifest = executor.execute_grade_chunk(database, **args)
    entry = manifest["entries"][0]
    artifact = executor.load_grade_artifact(store, entry["receipt_run_key"])
    return {"database": database, "v3": v3, "served": served, "manifest": manifest,
            "section": artifact["section"], "store": store, "args": args, "events": events,
            "rev3": rev3, "pin": pin, "binding": binding, "files": files, "calendar": descriptor}


def _report(context: dict[str, Any], manifest: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    events = context["events"]

    def siblings(entry: Any) -> tuple[Any, Any]:
        events.append("paired_sources:start")
        database = context["database"]
        pair = (database.analysis_snapshot_by_id(entry["v3_cycle_id"]),
                database.analysis_snapshot_by_id(entry["served_cycle_id"]))
        assert all(snapshot is not None for snapshot in pair)
        events.append("paired_sources:read")
        return pair

    def missing_labels(row: Any, horizon: int) -> dict[str, Any]:
        assert "paired_sources:read" in events
        assert row["symbol"] != "FFF" and horizon in report.HORIZONS
        events.append("missing_label")
        return {"return": None, "return_executable": None, "reason": "synthetic_outcome_not_supplied"}

    descriptor = context["calendar"]
    return report.build_report(manifest, records, rev3_manifest=context["rev3"],
        pin=context["pin"], binding=context["binding"], file_hashes=context["files"],
        expected_manifest_sha256=manifest["manifest_sha256"], paired_sources_reader=siblings,
        label_reader=missing_labels, index_of=descriptor["index_of"],
        mature_through={int(h): value for h, value in descriptor["mature_through"].items()},
        partition_last=descriptor["partition_last"])


def test_real_readers_private_company_artifacts_reload_and_unmeasured_report(integrated: dict[str, Any]) -> None:
    context = integrated
    manifest, section, store = context["manifest"], context["section"], context["store"]
    entry = manifest["entries"][0]
    assert manifest["complete"] and manifest["computed_this_chunk"] == 1 and manifest["remaining"] == 0
    assert section["source"] == "ensemble_pit" and section["labels_read"] == section["external_api_calls"] == 0
    assert section["catalogue_stocks"] == 5 and len(section["records"]) == 6
    assert section["ledger"]["model_denominator_each"] == 6
    assert all(sum(counts.values()) == 6 for counts in section["ledger"]["model_results"].values())
    assert all(tuple(model["model"] for model in row["models"]) == MODEL_IDS and len(row["variants"]) == 8
               for row in section["records"])
    etf = next(row for row in section["records"] if row["symbol"] == "FFF")
    assert all(model["reason"] == "not_a_stock" for model in etf["models"])
    assert section["input_pins"] == paired_source_identity(context["v3"], context["served"])
    assert validate_record_pair(section["records"], context["v3"], context["served"], volume_basis="as_traded") == []
    assert section["run_key"] == canonical_hash(section["context_identity"]) != entry["receipt_run_key"]
    assert all(row["run_key"] == section["run_key"] for row in section["records"])
    assert not section["historical_original_admissibility"] and not section["promotion_authorized"]

    header = store.read(entry["receipt_run_key"])
    assert header is not None and "records" not in header["section"] and len(header["record_receipts"]) == 6
    assert len(list(store.directory.glob("*.json"))) == 7
    assert stat.S_IMODE(store.directory.stat().st_mode) == 0o700
    before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in store.directory.glob("*.json")}
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in store.directory.glob("*.json"))
    # Recomputing uses the same scientific context and immutable storage objects.
    assert executor.execute_grade_chunk(context["database"], **context["args"]) == manifest
    continued = executor.execute_grade_chunk(context["database"], **context["args"], prior_entries=tuple(manifest["entries"]))
    assert continued["complete"] and continued["computed_this_chunk"] == 0
    assert continued["entries"] == manifest["entries"]
    assert before == {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in store.directory.glob("*.json")}
    assert executor.load_grade_artifact(store, entry["receipt_run_key"])["section"] == section

    result = _report(context, manifest, section["records"])["payload"]
    assert result["verdict"]["status"] == "UNMEASURED"
    assert result["raw_records"] == result["admissible_records"] == 6 and result["stock_records"] == 5
    assert result["labels_read"] == context["events"].count("missing_label") == 5 * len(report.HORIZONS)
    assert context["events"].index("paired_sources:read") < context["events"].index("missing_label")
    assert len(result["variants"]) == 8 and sum(result["valid_value_count_distribution"].values()) == 6
    assert all(result["model_non_evaluations"][model + ":not_a_stock"] == 1 for model in MODEL_IDS)
    assert result["served_source_changed"] is result["real_money"] is False
    assert result["verdict"]["promotion_authorized_by_result"] is False


def test_rehashed_price_tamper_is_refused_by_actual_siblings_before_any_label(integrated: dict[str, Any]) -> None:
    context = integrated
    records = copy.deepcopy(context["section"]["records"])
    records[0]["price"] += 1
    manifest = copy.deepcopy(context["manifest"])
    manifest["entries"][0]["records_sha256"] = canonical_hash(records)
    manifest["manifest_sha256"] = canonical_hash({key: value for key, value in manifest.items() if key != "manifest_sha256"})
    result = _report(context, manifest, records)["payload"]
    assert result["verdict"]["status"] == "VOID"
    assert "ensemble_price_differs_from_rev3:AAA" in result["verdict"]["reasons"]
    assert result["labels_read"] == 0 and "missing_label" not in context["events"]
    assert "paired_sources:read" in context["events"] and result["variants"] is None
