"""Explicit grade executor for caller-owned read-only PIT readers.

No import opens a connection, chooses a current snapshot, reads labels, dispatches
or changes a served TP. The operational driver must be reviewed and included in
the instrument pin: an injected guard is not an authorization from this module.
The CLI inventories/verifies the instrument only; host execution is an explicit
API under the signed owner order and the operator's existing chunk guards.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .valuation_ensemble_frozen import FrozenAsFiledReader, FrozenIndex, check_section_statements
from .valuation_ensemble_inputs import canonical_hash, utc
from .valuation_ensemble_persistence import FileReceiptStore
from .valuation_ensemble_pin import (InstrumentBinding, MANIFEST_SCHEMA, PREREG_COMMIT,
    PREREG_SHA256, REV3_MANIFEST_SHA256, instrument_file_hashes, validate_instrument_pin)


ORDER_SCHEMA = "VALUATION-PIT-BACKTEST-OWNER-ORDER-v1"
PREREG = "PREREG_VALUATION_ENSEMBLE_PIT_US_V1"


def _instant(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("ensemble_order_zoned_time_required")
    return utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _written_at(snapshot: Mapping[str, Any]) -> datetime:
    """A section's statements cut (PREREG rev 2 §2): its V3 snapshot's persistence instant, zoned, or a refusal."""
    value = snapshot.get("published_at")
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            value = None
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("ensemble_statements_cut_missing")
    return utc(value)


def validate_owner_order(raw: bytes, expected_sha256: str, *, binding: InstrumentBinding,
                         now: datetime) -> dict[str, Any]:
    """Bind the already authorized order bytes; never infer an order from flags.

    The expected digest is supplied from the operator-verified owner channel.
    The old rev3 order cannot authorize the new ensemble just by sharing inputs.
    """
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("ensemble_owner_order_digest_mismatch")
    order = json.loads(raw)
    if (not isinstance(order, dict) or order.get("schema") != ORDER_SCHEMA
            or order.get("prereg") != PREREG or order.get("modes") != ["grid"]):
        raise ValueError("ensemble_owner_order_scope_mismatch")
    if (order.get("prereg_sha256") != PREREG_SHA256
            or order.get("prereg_commit") != PREREG_COMMIT
            or order.get("instrument_pin_sha256") != binding.expected_pin_sha256
            or order.get("rev3_manifest_sha256") != REV3_MANIFEST_SHA256):
        raise ValueError("ensemble_owner_order_instrument_or_inputs_mismatch")
    first, last = date.fromisoformat(order["from_session"]), date.fromisoformat(order["to_session"])
    if first > last or type(order.get("max_runs_cap")) is not int or not 1 <= order["max_runs_cap"] <= 200:
        raise ValueError("ensemble_owner_order_range_or_cap_invalid")
    if utc(now) >= _instant(order.get("not_after")):
        raise ValueError("ensemble_owner_order_expired")
    if order.get("not_before") is not None and utc(now) < _instant(order["not_before"]):
        raise ValueError("ensemble_owner_order_not_yet_effective")
    return order


def _slot(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return str(row["market"]), str(row["session_date"]), str(row["as_of"])


def _reference_pairs(rev3: Mapping[str, Any]) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    if (rev3.get("complete") is not True or rev3.get("statements") != "vintages"
            or rev3.get("manifest_sha256") != REV3_MANIFEST_SHA256
            or canonical_hash({k: v for k, v in rev3.items() if k != "manifest_sha256"}) != REV3_MANIFEST_SHA256):
        raise ValueError("ensemble_reference_manifest_not_the_complete_signed_rev3")
    grid, served = rev3.get("grid"), rev3.get("served_grid")
    if (not isinstance(grid, list) or not isinstance(served, list) or not grid
            or any(not isinstance(x, Mapping) for x in [*grid, *served])):
        raise ValueError("ensemble_reference_pairs_missing")
    v3_by_slot, served_by_slot = {_slot(x): x for x in grid}, {_slot(x): x for x in served}
    if (len(v3_by_slot) != len(grid) or len(served_by_slot) != len(served)
            or set(v3_by_slot) != set(served_by_slot)):
        raise ValueError("ensemble_reference_pairs_not_unique_and_complete")
    pairs = []
    for slot in sorted(v3_by_slot, key=lambda x: (x[1], x[0], x[2])):
        v3, other = v3_by_slot[slot], served_by_slot[slot]
        if other.get("v3_run_key") != v3.get("run_key"):
            raise ValueError("ensemble_reference_sibling_run_mismatch")
        pairs.append((v3, other))
    return pairs


def _snapshot(database: Any, entry: Mapping[str, Any]) -> Mapping[str, Any]:
    value = database.analysis_snapshot_by_id(str(entry["cycle_id"]))
    if (not isinstance(value, Mapping) or str(value.get("id")) != str(entry["cycle_id"])
            or not isinstance(value.get("inputs"), Mapping)
            or value["inputs"].get("run_key") != entry["run_key"]):
        raise ValueError("ensemble_reference_snapshot_missing_or_replaced")
    return value


def _put(store: FileReceiptStore, core: dict[str, Any]) -> str:
    core["run_key"] = canonical_hash(core)
    core["payload_sha256"] = canonical_hash(core)
    store.put(core)
    return core["run_key"]


def load_grade_artifact(store: FileReceiptStore, receipt_run_key: str, *,
                        before_read: Callable[[], None] | None = None) -> dict[str, Any]:
    """Reassemble one section from bounded private company objects and its header.

    The immutable header is written last. Orphan company objects from an interrupted
    attempt are not a completed section and cannot mark a manifest slot complete.
    """
    def read(key: str) -> dict[str, Any] | None:
        if before_read is not None:
            before_read()
        value = store.read(key)
        if before_read is not None:
            before_read()
        return value
    held = read(receipt_run_key)
    if (held is None or held.get("schema") != "VALUATION-ENSEMBLE-GRADE-ARTIFACT-v1"
            or not isinstance(held.get("section"), dict) or not isinstance(held.get("record_receipts"), list)):
        raise ValueError("ensemble_section_artifact_missing_or_invalid")
    section = dict(held["section"])
    records = []
    symbols: set[str] = set()
    for reference in held["record_receipts"]:
        if not isinstance(reference, dict) or not isinstance(reference.get("symbol"), str) or reference["symbol"] in symbols:
            raise ValueError("ensemble_company_artifact_reference_invalid")
        symbols.add(reference["symbol"])
        company = read(str(reference.get("run_key")))
        if (company is None or company.get("schema") != "VALUATION-ENSEMBLE-GRADE-COMPANY-ARTIFACT-v1"
                or company.get("section_run_key") != section.get("run_key") or not isinstance(company.get("record"), dict)):
            raise ValueError("ensemble_company_artifact_missing_or_invalid")
        record = company["record"]
        if (record.get("symbol") != reference["symbol"] or record.get("run_key") != section.get("run_key")
                or any(record.get(key) != section.get(key) for key in ("market", "session_date", "as_of"))):
            raise ValueError("ensemble_company_artifact_identity_mismatch")
        records.append(record)
    section["records"] = records
    if section.get("records_sha256") != canonical_hash(records):
        raise ValueError("ensemble_section_records_digest_mismatch")
    # The section's own scientific digest covers the reconstructed full records,
    # not just the small storage header and its list of private object references.
    if section.get("payload_sha256") != canonical_hash({k: v for k, v in section.items() if k != "payload_sha256"}):
        raise ValueError("ensemble_section_payload_digest_mismatch")
    return {**held, "section": section}


def execute_grade_chunk(database: Any, *, rev3_manifest: Mapping[str, Any], pin: Mapping[str, Any],
                        binding: InstrumentBinding, file_hashes: Mapping[str, str],
                        owner_order_bytes: bytes, owner_order_sha256: str, store: FileReceiptStore,
                        prices_for: Callable[[Mapping[str, Any]], Any],
                        operational_guard: Callable[[], None], report_calendar: Mapping[str, Any],
                        max_runs: int = 10, stop_before: datetime,
                        clock: Callable[[], datetime] | None = None,
                        prior_entries: tuple[Mapping[str, Any], ...] = ()) -> dict[str, Any]:
    """Calculate bounded sections from exact rev3 siblings; persist private artifacts.

    ``database`` is an already-open, read-only handle. ``prices_for`` must resolve
    the reference publication, never the latest; compute_grid_section verifies it.
    ``operational_guard`` must execute the operator's actual host/deploy/window/
    timer/blocking-ingestion/autopilot guards (no as-filed backfill or poll guard
    since PREREG rev 2: each section reads the store cut at its V3 published_at).
    It is mandatory and is invoked before and after each section, with expiration
    checked again after every source read.
    This library cannot authenticate external operational state from JSON fields.
    """
    now = clock or (lambda: datetime.now(timezone.utc))
    problems = validate_instrument_pin(pin, file_hashes=file_hashes, binding=binding)
    if problems:
        raise ValueError(";".join(problems))
    order = validate_owner_order(owner_order_bytes, owner_order_sha256, binding=binding, now=now())
    if type(max_runs) is not int or not 1 <= max_runs <= order["max_runs_cap"]:
        raise ValueError("ensemble_chunk_exceeds_owner_cap")
    stop = min(utc(stop_before), _instant(order["not_after"]))
    pairs = _reference_pairs(rev3_manifest)
    from .valuation_ensemble_calendar import report_calendar_for
    if dict(report_calendar) != report_calendar_for(rev3_manifest):
        raise ValueError("ensemble_calendar_differs_from_reference_publication")
    from .valuation_ensemble_grid import compute_grid_section

    def active() -> None:
        validate_owner_order(owner_order_bytes, owner_order_sha256, binding=binding, now=now())
        if utc(now()) >= stop:
            raise ValueError("ensemble_execution_window_ended")
        if utc(now()) < _instant(pin.get("published_at")):
            raise ValueError("ensemble_run_precedes_published_instrument_pin")

    def guard() -> None:
        active()
        if operational_guard() is not None:
            raise ValueError("ensemble_operational_guard_must_raise_on_unknown_or_blocked_state")
        active()

    # Prior entries are artifact references, never a boolean 'already computed'.
    entries: list[dict[str, Any]] = []
    all_slots = {_slot(v3) for v3, _ in pairs}
    pairs_by_slot = {_slot(v3): (v3, served) for v3, served in pairs}
    for item in prior_entries:
        guard()
        if _slot(item) not in all_slots or item.get("instrument_pin_sha256") != binding.expected_pin_sha256:
            raise ValueError("ensemble_prior_section_not_bound")
        held = load_grade_artifact(store, str(item.get("receipt_run_key")), before_read=active)
        active()
        if held is None or held.get("section", {}).get("run_key") != item.get("run_key"):
            raise ValueError("ensemble_prior_section_artifact_missing")
        if held.get("section", {}).get("records_sha256") != item.get("records_sha256"):
            raise ValueError("ensemble_prior_section_artifact_mismatch")
        for key in ("market", "session_date", "as_of", "run_key", "records_sha256", "catalogue_stocks", "input_pins"):
            if held["section"].get(key) != item.get(key):
                raise ValueError("ensemble_prior_section_metadata_mismatch")
        for key in ("started_at", "instrument_commit", "implementation_files", "instrument_pin_sha256"):
            if held.get(key) != item.get(key):
                raise ValueError("ensemble_prior_execution_binding_mismatch")
        if (held.get("owner_order_sha256") != owner_order_sha256
                or held.get("implementation_files") != dict(file_hashes)
                or held["section"].get("implementation") != dict(file_hashes)
                or held.get("instrument_commit") != binding.instrument_commit
                or _instant(held.get("started_at")) < _instant(pin.get("published_at"))):
            raise ValueError("ensemble_prior_instrument_or_order_mismatch")
        v3_ref, served_ref = pairs_by_slot[_slot(item)]
        for key, expected in (("v3_cycle_id", str(v3_ref["cycle_id"])),
                              ("served_cycle_id", str(served_ref["cycle_id"])),
                              ("v3_run_key", v3_ref["run_key"]), ("served_run_key", served_ref["run_key"])):
            if item.get(key) != expected:
                raise ValueError("ensemble_prior_reference_siblings_mismatch")
        v3_snapshot = _snapshot(database, v3_ref)
        active()
        served_snapshot = _snapshot(database, served_ref)
        active()
        from .valuation_ensemble_grid import paired_source_identity, validate_record_pair
        if held["section"].get("input_pins") != paired_source_identity(v3_snapshot, served_snapshot):
            raise ValueError("ensemble_prior_input_pins_mismatch")
        if validate_record_pair(held["section"].get("records", []), v3_snapshot, served_snapshot,
                volume_basis=str(rev3_manifest.get("volume_basis", {}).get("decision"))):
            raise ValueError("ensemble_prior_records_differ_from_reference")
        guard()
        entries.append(dict(item))
    if len({_slot(x) for x in entries}) != len(entries):
        raise ValueError("ensemble_prior_section_duplicate")
    completed = {_slot(x) for x in entries}
    computed = 0
    reason = None
    frozen: list[FrozenIndex] = []  # loaded once a chunk, the first time a section reads the store (rev 2 §2)

    def frozen_index() -> FrozenIndex:
        if not frozen:
            active()
            frozen.append(FrozenIndex.load(database))
            active()
        return frozen[0]
    for v3_ref, served_ref in pairs:
        if _slot(v3_ref) in completed or not order["from_session"] <= str(v3_ref["session_date"]) <= order["to_session"]:
            continue
        if computed == max_runs or utc(now()) >= stop:
            reason = "chunk_cap" if computed == max_runs else "stop_before"
            break
        guard()
        started = utc(now())
        if started < _instant(pin.get("published_at")):
            raise ValueError("ensemble_run_precedes_published_instrument_pin")
        v3_snapshot = _snapshot(database, v3_ref)
        active()
        served_snapshot = _snapshot(database, served_ref)
        active()
        prices = prices_for(v3_ref)
        active()
        vintages = FrozenAsFiledReader(database, written_until=_written_at(v3_snapshot), index=frozen_index)
        check_section_statements(database, market=str(v3_ref["market"]), as_of=_instant(v3_ref["as_of"]), v3_snapshot=v3_snapshot,
                                 served_snapshot=served_snapshot, reader=vintages, before_read=active)
        section = compute_grid_section(database, market=str(v3_ref["market"]),
            as_of=_instant(v3_ref["as_of"]), prices=prices, v3_snapshot=v3_snapshot,
            served_snapshot=served_snapshot, implementation=file_hashes, seed=20261026, vintages=vintages,
            volume_basis=str(rev3_manifest.get("volume_basis", {}).get("decision")), before_read=active)
        guard()
        company_refs = []
        for record in section["records"]:
            active()
            company_key = _put(store, {"schema": "VALUATION-ENSEMBLE-GRADE-COMPANY-ARTIFACT-v1",
                "section_run_key": section["run_key"], "record": record})
            company_refs.append({"symbol": record["symbol"], "run_key": company_key})
        active()
        receipt: dict[str, Any] = {"schema": "VALUATION-ENSEMBLE-GRADE-ARTIFACT-v1",
            "section": {k: v for k, v in section.items() if k != "records"}, "record_receipts": company_refs,
            "instrument_pin_sha256": binding.expected_pin_sha256, "owner_order_sha256": owner_order_sha256,
            "started_at": started.isoformat(), "instrument_commit": binding.instrument_commit,
            "implementation_files": dict(file_hashes)}
        receipt_key = _put(store, receipt)
        entry = {k: section[k] for k in ("market", "session_date", "as_of", "run_key", "records_sha256", "catalogue_stocks", "input_pins")}
        entry.update({"receipt_run_key": receipt_key, "v3_cycle_id": str(v3_ref["cycle_id"]),
            "served_cycle_id": str(served_ref["cycle_id"]), "v3_run_key": v3_ref["run_key"],
            "served_run_key": served_ref["run_key"], "instrument_commit": binding.instrument_commit,
            "instrument_pin_sha256": binding.expected_pin_sha256, "implementation_files": dict(file_hashes),
            "started_at": started.isoformat()})
        entries.append(entry)
        completed.add(_slot(v3_ref))
        computed += 1
    manifest: dict[str, Any] = {"schema": MANIFEST_SCHEMA, "source": "ensemble_pit",
        "complete": completed == all_slots, "remaining": len(all_slots - completed), "computed_this_chunk": computed,
        "stopped": reason, "entries": sorted(entries, key=lambda x: (x["session_date"], x["market"])),
        "prereg_sha256": PREREG_SHA256, "prereg_commit": PREREG_COMMIT,
        "instrument_pin_sha256": binding.expected_pin_sha256, "rev3_manifest_sha256": REV3_MANIFEST_SHA256,
        "owner_order_sha256": owner_order_sha256, "report_calendar": dict(report_calendar),
        "served_source_changed": False, "buy_permission": False}
    manifest["manifest_sha256"] = canonical_hash(manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory the ensemble instrument; never opens data or runs a grade implicitly")
    parser.add_argument("--repository-root", type=Path)
    parser.add_argument("--inventory", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        files = instrument_file_hashes(args.repository_root)
        print(json.dumps({"schema": "VALUATION-ENSEMBLE-INSTRUMENT-INVENTORY-v1", "files": files,
            "prereg_sha256": PREREG_SHA256, "prereg_commit": PREREG_COMMIT,
            "pin_issued": False, "labels_read": 0}, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError):
        print(json.dumps({"status": "refused", "reason": "ensemble_instrument_inventory_incomplete"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
