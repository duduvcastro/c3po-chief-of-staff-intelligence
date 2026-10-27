"""Independent synthetic executor checks: bounded reads and private artifact writes.

The financial section is a double here. Its concrete PIT-source contract has a
separate grid suite. No connection, secret, real input or outcome is opened.
"""
from __future__ import annotations

import copy
import hashlib
import json
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pytest

from app import valuation_ensemble_calendar as calendar
from app import valuation_ensemble_executor as executor
from app import valuation_ensemble_grid as grid
from app import valuation_ensemble_pin as instrument
from app.valuation_ensemble_inputs import canonical_hash
from app.valuation_ensemble_persistence import FileReceiptStore


NOW = datetime(2026, 10, 27, 13, 10, tzinfo=timezone.utc)


class Clock:
    def __init__(self) -> None:
        self.at = NOW

    def __call__(self) -> datetime:
        return self.at


class Database:
    def __init__(self, snapshots: dict[str, Any], events: list[str]) -> None:
        self.snapshots, self.events = snapshots, events
        self.after_read: Callable[[str], None] | None = None
        self.writes = 0

    def analysis_snapshot_by_id(self, key: str) -> Any:
        self.events.append("read:" + key)
        result = copy.deepcopy(self.snapshots.get(key))
        if self.after_read is not None:
            self.after_read(key)
        return result

    def save_analysis_snapshot(self, *args: Any, **kwargs: Any) -> Any:
        self.writes += 1
        raise AssertionError("The grade executor reached a DB writer")


def fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    clock, events = Clock(), []
    files = instrument.instrument_file_hashes()
    pin = {"schema": instrument.PIN_SCHEMA, "prereg_commit": instrument.PREREG_COMMIT,
           "prereg_sha256": instrument.PREREG_SHA256, "instrument_commit": "1" * 40,
           "owner_signature_comment_id": 1, "technical_GO_comment_id": 2,
           "published_at": (NOW - timedelta(minutes=10)).isoformat(), "files": files,
           "constants": instrument.PROTOCOL_CONSTANTS}
    binding = instrument.InstrumentBinding(canonical_hash(pin), instrument.PREREG_COMMIT, "1" * 40, 1, 2)
    v3, served, snapshots = [], [], {}
    for index, (market, day) in enumerate((('NASDAQ', '2021-06-01'), ('NYSE', '2021-06-01'), ('NASDAQ', '2021-06-08'), ('NYSE', '2021-06-08'))):
        vkey, skey = canonical_hash(["v3", index]), canonical_hash(["served", index])
        as_of = "2021-06-02T04:00:00+00:00" if day.endswith("01") else "2021-06-09T04:00:00+00:00"
        base = {"market": market, "session_date": day, "as_of": as_of}
        v3.append({**base, "run_key": vkey, "cycle_id": f"V{index}"})
        served.append({**base, "run_key": skey, "cycle_id": f"S{index}", "v3_run_key": vkey})
        for cid, key in ((f"V{index}", vkey), (f"S{index}", skey)):
            snapshots[cid] = {"id": cid, "inputs": {"run_key": key, "market": market, "as_of": as_of}}
    rev3 = {"complete": True, "statements": "vintages", "grid": v3, "served_grid": served,
            "volume_basis": {"decision": "as_traded"}, "grid_start": "2021-06-01"}
    rev3["manifest_sha256"] = canonical_hash(rev3)
    monkeypatch.setattr(executor, "REV3_MANIFEST_SHA256", rev3["manifest_sha256"])
    monkeypatch.setattr(instrument, "REV3_MANIFEST_SHA256", rev3["manifest_sha256"])
    descriptor = {"index_of": {"2021-06-01": 0}, "mature_through": {}, "partition_last": 0}
    monkeypatch.setattr(calendar, "report_calendar_for", lambda source: copy.deepcopy(descriptor))
    order = {"schema": executor.ORDER_SCHEMA, "prereg": executor.PREREG, "modes": ["grid"],
             "prereg_commit": instrument.PREREG_COMMIT, "prereg_sha256": instrument.PREREG_SHA256,
             "instrument_pin_sha256": binding.expected_pin_sha256, "rev3_manifest_sha256": rev3["manifest_sha256"],
             "from_session": "2021-06-01", "to_session": "2021-06-08", "max_runs_cap": 4,
             "not_before": (NOW - timedelta(hours=1)).isoformat(), "not_after": (NOW + timedelta(hours=1)).isoformat()}
    db = Database(snapshots, events)
    store = FileReceiptStore(tmp_path / "receipts")
    context: dict[str, Any] = {"clock": clock, "events": events, "files": files, "pin": pin, "binding": binding,
                               "rev3": rev3, "order": order, "database": db, "store": store, "calendar": descriptor,
                               "compute_hook": None}
    def source_identity(v3_snapshot: Any, served_snapshot: Any) -> dict[str, Any]:
        return {"v3_run_key": v3_snapshot["inputs"]["run_key"], "served_run_key": served_snapshot["inputs"]["run_key"],
                "v3_cycle_id": v3_snapshot["id"], "served_cycle_id": served_snapshot["id"]}
    monkeypatch.setattr(grid, "paired_source_identity", source_identity)
    monkeypatch.setattr(grid, "validate_record_pair", lambda *args, **kwargs: [])
    def compute(database: Any, **kw: Any) -> dict[str, Any]:
        events.append("compute")
        if context["compute_hook"] is not None:
            context["compute_hook"](database, **kw)
        inputs = source_identity(kw["v3_snapshot"], kw["served_snapshot"])
        day = next(item["session_date"] for item in v3 if item["run_key"] == inputs["v3_run_key"])
        records = [{"source": "ensemble_pit", "market": kw["market"], "symbol": "SYNTHETIC", "session_date": day}]
        result = {"market": kw["market"], "session_date": day, "as_of": kw["as_of"].isoformat(),
                  "run_key": canonical_hash([kw["market"], day, kw["implementation"]]),
                  "records": records, "records_sha256": canonical_hash(records), "catalogue_stocks": 1,
                  "input_pins": inputs, "implementation": dict(kw["implementation"])}
        result["payload_sha256"] = canonical_hash(result)
        return result
    monkeypatch.setattr(grid, "compute_grid_section", compute)
    def prices(entry: Any) -> Any:
        events.append("prices")
        return object()
    context["prices"] = prices
    def guard() -> None:
        events.append("guard")
    context["guard"] = guard
    return context


def run(context: dict[str, Any], **changes: Any) -> dict[str, Any]:
    raw = json.dumps(context["order"], sort_keys=True).encode()
    args = {"rev3_manifest": context["rev3"], "pin": context["pin"], "binding": context["binding"],
            "file_hashes": context["files"], "owner_order_bytes": raw, "owner_order_sha256": hashlib.sha256(raw).hexdigest(),
            "store": context["store"], "prices_for": context["prices"], "operational_guard": context["guard"],
            "report_calendar": context["calendar"], "max_runs": 4, "stop_before": NOW + timedelta(hours=1),
            "clock": context["clock"]}
    args.update(changes)
    return executor.execute_grade_chunk(context["database"], **args)


def test_bounded_chunk_writes_only_private_receipts_and_completes_after_continuation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context = fixture(monkeypatch, tmp_path)
    first = run(context, max_runs=1)
    assert first["complete"] is False and first["remaining"] == 3 and first["computed_this_chunk"] == 1 and first["stopped"] == "chunk_cap"
    entry = first["entries"][0]
    stored = context["store"].read(entry["receipt_run_key"])
    assert stored is not None and stored["section"]["run_key"] == entry["run_key"]
    path = context["store"].directory / (entry["receipt_run_key"] + ".json")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    second = run(context, max_runs=3, prior_entries=tuple(first["entries"]))
    assert second["complete"] is True and second["remaining"] == 0 and second["computed_this_chunk"] == 3
    assert len(second["entries"]) == 4 and context["database"].writes == 0
    assert second["manifest_sha256"] == canonical_hash({k: v for k, v in second.items() if k != "manifest_sha256"})
    assert second["served_source_changed"] is False and second["buy_permission"] is False


@pytest.mark.parametrize("failure", ["pin", "files", "order_digest", "order_scope", "expired", "future_order", "future_pin", "calendar", "cap", "cap_bool", "reference", "duplicate_reference"])
def test_invalid_authority_or_reference_stops_before_all_data_reads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str) -> None:
    context = fixture(monkeypatch, tmp_path)
    changes: dict[str, Any] = {}
    if failure == "pin":
        changes["pin"] = None
    elif failure == "files":
        changes["file_hashes"] = {**context["files"], next(iter(context["files"])): "f" * 64}
    elif failure == "order_digest":
        changes["owner_order_sha256"] = "0" * 64
    elif failure == "order_scope":
        context["order"]["prereg"] = "PREREG_VALUATION_PIT_BACKTEST_US_V1"
    elif failure == "expired":
        context["order"]["not_after"] = NOW.isoformat()
    elif failure == "future_order":
        context["order"]["not_before"] = (NOW + timedelta(microseconds=1)).isoformat()
    elif failure == "future_pin":
        context["clock"].at = NOW - timedelta(minutes=11)
    elif failure == "calendar":
        changes["report_calendar"] = {"fake": "calendar"}
    elif failure in {"cap", "cap_bool"}:
        changes["max_runs"] = 5 if failure == "cap" else True
    elif failure == "reference":
        changes["rev3_manifest"] = {**context["rev3"], "manifest_sha256": "f" * 64}
    else:
        context["rev3"]["grid"].append(copy.deepcopy(context["rev3"]["grid"][0]))
    with pytest.raises((ValueError, TypeError)):
        run(context, **changes)
    assert not any(item.startswith("read:") or item == "prices" or item == "compute" for item in context["events"])
    assert not list(context["store"].directory.iterdir()) and context["database"].writes == 0


@pytest.mark.parametrize("returned", [False, True, 0, "unknown", {"healthy": True}])
def test_guard_success_is_no_return_not_a_truthy_or_falsey_approval_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, returned: Any) -> None:
    context = fixture(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="operational_guard"):
        run(context, operational_guard=lambda: returned)
    assert context["events"] == [] and not list(context["store"].directory.iterdir())


def test_blocked_guard_and_guard_crossing_expiry_precede_first_database_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context = fixture(monkeypatch, tmp_path)
    def blocked() -> None:
        raise ValueError("synthetic operational window blocked")
    with pytest.raises(ValueError, match="blocked"):
        run(context, operational_guard=blocked)
    def slow_guard() -> None:
        context["clock"].at = NOW + timedelta(hours=1)
    with pytest.raises(ValueError, match="expired|window_ended"):
        run(context, operational_guard=slow_guard)
    assert context["events"] == [] and not list(context["store"].directory.iterdir())


@pytest.mark.parametrize("expired_after", ["first_snapshot", "served_snapshot", "prices_factory", "internal_source"])
def test_expiration_after_source_read_stops_subsequent_reads_and_writes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, expired_after: str) -> None:
    context = fixture(monkeypatch, tmp_path)
    if expired_after in {"first_snapshot", "served_snapshot"}:
        def expire(key: str) -> None:
            if key == ("V0" if expired_after == "first_snapshot" else "S0"):
                context["clock"].at = NOW + timedelta(hours=1)
        context["database"].after_read = expire
    elif expired_after == "prices_factory":
        def prices(_entry: Any) -> Any:
            context["events"].append("prices")
            context["clock"].at = NOW + timedelta(hours=1)
            return object()
        context["prices"] = prices
    else:
        def compute_hook(database: Any, **kw: Any) -> None:
            def read() -> Any:
                result = database.analysis_snapshot_by_id("V1")
                context["clock"].at = NOW + timedelta(hours=1)
                return result
            grid._guarded(read, kw["before_read"])
            database.analysis_snapshot_by_id("S1")
        context["compute_hook"] = compute_hook
    with pytest.raises(ValueError, match="expired|window_ended"):
        run(context)
    events = context["events"]
    assert not list(context["store"].directory.iterdir()) and context["database"].writes == 0
    assert "read:S1" not in events
    if expired_after == "first_snapshot":
        assert "read:S0" not in events and "prices" not in events
    if expired_after in {"first_snapshot", "served_snapshot", "prices_factory"}:
        assert "compute" not in events


def test_stop_before_elapsed_does_no_source_work_and_misplaced_snapshots_are_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context = fixture(monkeypatch, tmp_path)
    stopped = run(context, stop_before=NOW)
    assert stopped["computed_this_chunk"] == 0 and stopped["stopped"] == "stop_before" and context["events"] == []
    context["database"].snapshots["V0"]["inputs"]["run_key"] = "different-run"
    with pytest.raises(ValueError, match="snapshot_missing_or_replaced"):
        run(context)
    assert context["events"] == ["guard", "read:V0"]


def _replace_receipt(context: dict[str, Any], entry: dict[str, Any], mutate: Callable[[dict[str, Any], dict[str, Any]], None]) -> dict[str, Any]:
    receipt = context["store"].read(entry["receipt_run_key"])
    assert receipt is not None
    receipt = {k: v for k, v in receipt.items() if k not in {"run_key", "payload_sha256"}}
    changed = copy.deepcopy(entry)
    mutate(receipt, changed)
    receipt["run_key"] = canonical_hash(receipt)
    receipt["payload_sha256"] = canonical_hash(receipt)
    context["store"].put(receipt)
    changed["receipt_run_key"] = receipt["run_key"]
    return changed


@pytest.mark.parametrize("failure", ["cross_pin", "cross_commit", "cross_files", "wrong_sibling", "wrong_input_pins", "different_order", "pre_pin_time", "duplicate"])
def test_prior_artifacts_are_not_boolean_reuse_or_a_cross_pin_shortcut(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str) -> None:
    context = fixture(monkeypatch, tmp_path)
    entry = run(context, max_runs=1)["entries"][0]
    context["events"].clear()
    if failure == "cross_pin":
        entry["instrument_pin_sha256"] = "f" * 64
    elif failure == "cross_commit":
        entry = _replace_receipt(context, entry, lambda receipt, changed: (receipt.update(instrument_commit="2" * 40), changed.update(instrument_commit="2" * 40)))
    elif failure == "cross_files":
        bad = {**context["files"], next(iter(context["files"])): "f" * 64}
        def wrong_files(receipt: Any, changed: Any) -> None:
            receipt["implementation_files"] = bad
            receipt["section"]["implementation"] = bad
            changed["implementation_files"] = bad
        entry = _replace_receipt(context, entry, wrong_files)
    elif failure == "wrong_sibling":
        entry["v3_cycle_id"] = "V1"
    elif failure == "wrong_input_pins":
        def wrong_pin(receipt: Any, changed: Any) -> None:
            wrong = {**changed["input_pins"], "v3_cycle_id": "V1"}
            receipt["section"]["input_pins"] = wrong
            changed["input_pins"] = wrong
        entry = _replace_receipt(context, entry, wrong_pin)
    elif failure == "different_order":
        context["order"]["max_runs_cap"] = 3
    elif failure == "pre_pin_time":
        before = (NOW - timedelta(hours=1)).isoformat()
        entry = _replace_receipt(context, entry, lambda receipt, changed: (receipt.update(started_at=before), changed.update(started_at=before)))
    prior = (entry, entry) if failure == "duplicate" else (entry,)
    with pytest.raises(ValueError, match="prior"):
        run(context, max_runs=1, prior_entries=prior)
    assert "compute" not in context["events"] and context["database"].writes == 0


def test_inventory_cli_and_workflow_are_inert_source_inventory_only(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(executor, "execute_grade_chunk", lambda *args, **kwargs: pytest.fail("CLI ran a grade"))
    assert executor.main(["--inventory"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["pin_issued"] is False and result["labels_read"] == 0
    assert result["files"] and "c3po/backend/app/valuation_ensemble_executor.py" in result["files"]
    workflow = Path(__file__).resolve().parents[3] / ".github/workflows/valuation-ensemble-grid.yml"
    text = workflow.read_text()
    assert "workflow_dispatch:" in text and "--inventory" in text
    assert "contents: read" in text and "persist-credentials: false" in text
    assert not any(fragment in text for fragment in ("schedule:", "push:", "ssh ", "DATABASE_URL", "secrets.", "--run-grade", "dispatches"))
