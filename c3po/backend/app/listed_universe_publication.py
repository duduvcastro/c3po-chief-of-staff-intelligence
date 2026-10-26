"""Closed publication preparation and an isolated atomic-composition sandbox.

There is deliberately no PostgreSQL writer or production activation entry point.
The sandbox accepts only Database's in-memory double, copies it, and commits only
to its private copy. It exercises the real canonical validators/selection readers
without claiming that a process-local lock excludes existing production writers.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import math
import re
from threading import RLock
from typing import Any, Mapping
from uuid import UUID, uuid4, uuid5

from .config import Settings
from .database import Database
from .listed_universe import Catalogue, catalogue_from_payload, digest, utc
from .listed_universe_runtime import STAGE_ANALYSIS, producer_identity
from . import valuation_official as official

SCHEMA = "FULL-UNIVERSE-PUBLICATION-PREPARATION-v1"
MARKETS = ("B3", "NASDAQ", "NYSE")
BLOCKERS = (
    "postgresql_single_transaction_adapter_not_implemented_or_tested",
    "legacy_nightly_ir_and_on_demand_writer_ownership_not_enforced",
    "source_authenticated_capacity_and_exact_head_fable_go_required",
    "genuine_pit_free_operating_window_required",
    "post_commit_served_capture_and_cross_process_cache_policy_required",
)


def _hash(value: Any) -> str:
    # Stored snapshots may carry datetime values; normalize exactly as JSONB
    # evidence, without changing the stored/source objects.
    if isinstance(value, datetime):
        return digest(utc(value).isoformat())
    def normalized(item: Any) -> Any:
        if isinstance(item, datetime):
            return utc(item).isoformat()
        if isinstance(item, Mapping):
            return {str(key): normalized(part) for key, part in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalized(part) for part in item]
        return item
    return digest(normalized(value))


def production_preflight() -> dict[str, Any]:
    """No supplied flag, JSON receipt or callback can assert writer ownership."""
    return {"production_release_allowed": False, "production_sql_writer_implemented": False,
            "legacy_writer_ownership_enforced": False, "schedule_enabled": False,
            "blockers": list(BLOCKERS)}


def _limit(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("stage/catalogue freshness requires an explicit positive finite limit")
    return float(value)


def _fresh(value: Any, at: datetime, limit: float) -> datetime:
    instant = utc(value)
    if not 0 <= (at - instant).total_seconds() <= limit:
        raise ValueError("publication basis is future-dated or stale")
    return instant


def _record_integrity(record: Mapping[str, Any]) -> bool:
    core = {key: value for key, value in record.items() if key not in {"id", "row_sha256"}}
    return official.canonical_sha256(core) == record.get("row_sha256")


def _head(database: Database, expected: str, at: datetime) -> tuple[dict[str, Any], dict[str, Any] | None]:
    head = database.latest_valuation_official_selection()
    if not head or head.get("generation_id") != expected:
        raise ValueError("publication CAS predecessor changed or is absent")
    if head.get("source") not in official.OFFICIAL_SOURCES or head.get("validated_complete") is not True:
        raise ValueError("publication requires a valid already-selected canonical source")
    if database.valuation_official_selection_successor(expected) is not None:
        raise ValueError("publication predecessor is not the chain tip")
    if utc(head["activated_at"]) >= at:
        raise ValueError("publication clock must follow its predecessor")
    if official.selection_freeze(head, now=at) is not None:
        raise ValueError("publication is held by the existing freeze")
    return head, database.latest_explicit_valuation_official_selection()


def _stage(database: Database, catalogue: Catalogue, stage_id: str, head: Mapping[str, Any],
           order: Mapping[str, Any] | None, at: datetime, max_age: float) -> dict[str, Any]:
    market = catalogue.market
    _fresh(catalogue.received_at, at, max_age)
    snapshot = database.analysis_snapshot_by_id(stage_id)
    if not snapshot or snapshot.get("analysis_type") != STAGE_ANALYSIS or snapshot.get("entity_key") != market:
        raise ValueError("stage FK is not a canonical stage of its named market")
    published = _fresh(snapshot["published_at"], at, max_age)
    inputs, outputs = snapshot.get("inputs"), snapshot.get("outputs")
    if not isinstance(inputs, Mapping) or not isinstance(outputs, Mapping):
        raise ValueError("stage lacks its recorded inputs/outputs")
    version = str(inputs.get("canonical_methodology_version") or "")
    if version != str(head.get("source_version")):
        raise ValueError("stage must preserve the selected canonical methodology version")
    manifest = catalogue.payload()["manifest_sha256"]
    if inputs.get("source_manifest_sha256") != manifest or not re.fullmatch(r"[a-f0-9]{64}", str(inputs.get("run_identity") or "")):
        raise ValueError("stage does not bind the complete catalogue and run identity")
    if not re.fullmatch(r"[a-f0-9]{64}", str(outputs.get("context_sha256") or "")):
        raise ValueError("stage lacks its canonical cohort context")
    rows, unavailable = outputs.get("rows"), outputs.get("not_evaluable")
    if not isinstance(rows, list) or not isinstance(unavailable, Mapping) or not rows:
        raise ValueError("stage has no selectable canonical rows or missing unavailable reasons")
    names = {item.symbol for item in catalogue.listings if item.security_type != "ETF"}
    equity = {item.symbol for item in catalogue.listings if item.listing_class == "equity" and item.security_type != "ETF"}
    valued = [str(row.get("symbol") or "") for row in rows if isinstance(row, Mapping)]
    if (len(valued) != len(rows) or len(set(valued)) != len(valued) or not set(valued) <= equity
            or set(valued) & set(unavailable) or set(valued) | set(unavailable) != names
            or isinstance(outputs.get("inventory_count"), bool) or outputs.get("inventory_count") != len(names)
            or any(not re.fullmatch(r"[a-z0-9_]+", str(reason or "")) for reason in unavailable.values())):
        raise ValueError("stage inventory omits, duplicates or invents listings/reasons")
    recorded, instants = {}, set()
    for source in official.OFFICIAL_SOURCES:
        records = database.valuation_predictions_for_cycle(stage_id, source=source)
        if set(records) != set(valued):
            raise ValueError("stage lacks exactly one immutable record per valued name and canonical source")
        for row in rows:
            original = records[row["symbol"]]
            predicted = _fresh(original["prediction_instant"], at, max_age)
            if predicted > published or utc(catalogue.received_at) > predicted:
                raise ValueError("stage prediction/publication clocks are not causal")
            if order and predicted <= utc(order["activated_at"]):
                raise ValueError("stage prediction is held by the latest explicit order")
            expected = official.prediction_from_row(
                row, market=market, scope="universe", cycle_id=stage_id, source_version=version,
                prediction_instant=predicted, published_at=published, source_manifest_sha256=manifest, source=source,
                extra_provenance={"full_universe_stage": True, "run_identity": inputs["run_identity"],
                                  "context_sha256": outputs["context_sha256"]})
            # The frozen reader verifies legacy V1 hashes but deliberately
            # returns V2 as stored. Recompute V2 here too; comparing two stored
            # digest strings alone would accept a damaged value under an old hash.
            if not _record_integrity(original) or expected is None or expected["row_sha256"] != original["row_sha256"]:
                raise ValueError("stage immutable record does not reproduce its canonical row and clocks")
            instants.add(predicted.isoformat())
        recorded[source] = records
    if len(instants) != 1:
        raise ValueError("one stage must have one canonical cohort prediction clock")
    basis_id = (head.get("cycles") or {}).get(market)
    basis = database.analysis_snapshot_by_id(str(basis_id))
    if (not basis or basis.get("analysis_type") != official.UNIVERSE_ANALYSIS
            or basis.get("entity_key") != f"{market}_UNIVERSE"
            or str((basis.get("inputs") or {}).get("methodology_version")) != version):
        raise ValueError("current official cycle lacks its canonical methodology binding")
    selected_records = database.valuation_predictions_for_cycle(str(basis_id), source=str(head["source"]))
    if (not all(_record_integrity(record) for record in selected_records.values())
            or not official.cycle_validation(basis, recorded=selected_records, source=str(head["source"]))["valid"]):
        raise ValueError("current official cycle is invalid for its selected source")
    return {"snapshot": snapshot, "records": recorded, "basis": basis,
            "prediction_instant": next(iter(instants)), "catalogue": catalogue.payload()}


def _read_basis(database: Database, catalogues: Mapping[str, Catalogue], stages: Mapping[str, str],
                expected: str, at: datetime, max_age: float) -> dict[str, Any]:
    if set(catalogues) != set(MARKETS) or set(stages) != set(MARKETS) or len(set(stages.values())) != 3:
        raise ValueError("one distinct stage and complete catalogue for each of the three markets is required")
    if any(catalogues[market].market != market for market in MARKETS):
        raise ValueError("catalogue was assigned to another market")
    head, order = _head(database, expected, at)
    raw_targeted = official._normalized_targeted(head.get("targeted") or {})
    if official.targeted_valid_for(database, head, source=str(head["source"])) != raw_targeted:
        raise ValueError("an existing targeted admission cannot be silently discarded or carried unvalidated")
    targeted = {symbol: {"cycle": database.analysis_snapshot_by_id(cycle),
                         "records": database.valuation_predictions_for_cycle(cycle, source=str(head["source"]))}
                for symbol, cycle in raw_targeted.items()}
    # Bind registered-but-unadmitted records too: canonical targeted recovery is
    # re-run inside the sandbox and must not consume a different read set.
    pending = database.latest_targeted_predictions("B3", source=str(head["source"]))
    pending_cycles = {str(record["cycle_id"]): database.analysis_snapshot_by_id(str(record["cycle_id"]))
                      for record in pending.values()}
    if (not all(_record_integrity(record) for record in pending.values())
            or not all(_record_integrity(record) for item in targeted.values() for record in item["records"].values())):
        raise ValueError("targeted immutable record integrity does not verify")
    items = {market: _stage(database, catalogues[market], stages[market], head, order, at, max_age) for market in MARKETS}
    final, final_order = _head(database, expected, at)
    if _hash([head, order]) != _hash([final, final_order]):
        raise ValueError("head or explicit order moved during the publication read")
    return {"head": head, "explicit_order": order, "stages": items, "targeted": targeted,
            "pending_targeted_records": pending, "pending_targeted_cycles": pending_cycles}


def prepare_publication(database: Database, catalogues: Mapping[str, Catalogue], stages: Mapping[str, str], *,
                        expected_predecessor: str, max_age_seconds: float, now: datetime | None = None) -> dict[str, Any]:
    """Read and bind real storage interfaces; never append or select anything.

    This receipt proves local structure/integrity, not provider provenance,
    capacity, writer exclusion, a scientific PASS or permission to publish.
    """
    at, limit = utc(now or datetime.now(timezone.utc)), _limit(max_age_seconds)
    basis = _read_basis(database, catalogues, stages, expected_predecessor, at, limit)
    result = {"schema": SCHEMA, "transaction_id": str(uuid4()), "prepared_at": at.isoformat(),
              "expected_predecessor": expected_predecessor, "max_age_seconds": limit,
              "code_pins_sha256": digest(producer_identity()),
              "catalogues": {market: catalogues[market].payload() for market in MARKETS},
              "stage_ids": dict(stages), "read_basis_sha256": _hash(basis), **production_preflight()}
    return {**result, "preparation_sha256": _hash(result)}


class _IsolatedDatabase(Database):
    def _capture_served_after_selection(self) -> None:
        # A post-commit operational capture is deliberately NOT simulated as
        # successful merely because the canonical selection validates.
        return None


def _clone_memory(database: Database) -> _IsolatedDatabase:
    if database.database_url:
        raise ValueError("the publication sandbox accepts only the in-memory Database double")
    clone = _IsolatedDatabase(Settings(database_url="", auth_cookie_secure=False))
    clone._analysis_snapshots = copy.deepcopy(database._analysis_snapshots)
    clone._valuation_predictions = copy.deepcopy(database._valuation_predictions)
    clone._valuation_official_selections = copy.deepcopy(database._valuation_official_selections)
    return clone


class AtomicPublicationSandbox:
    """A private copy with one commit pointer; never a live Database adapter.

    Readers observe a complete prior/new private database. Failure at any point
    discards the work copy. This models atomicity/CAS; it does not verify SQL
    locking/isolation and cannot make a production ownership claim.
    """
    def __init__(self, database: Database) -> None:
        self._database = _clone_memory(database)
        self._lock = RLock()

    def view(self) -> Database:
        with self._lock:
            return _clone_memory(self._database)

    def apply(self, preparation: Mapping[str, Any], *, now: datetime) -> dict[str, Any]:
        with self._lock:
            core = {key: value for key, value in preparation.items() if key != "preparation_sha256"}
            if (preparation.get("schema") != SCHEMA or _hash(core) != preparation.get("preparation_sha256")
                    or preparation.get("code_pins_sha256") != digest(producer_identity())
                    or any(preparation.get(key) != value for key, value in production_preflight().items())):
                raise ValueError("publication preparation integrity or closed production gates changed")
            transaction = UUID(str(preparation["transaction_id"]))
            at = utc(now)
            if at < utc(preparation["prepared_at"]):
                raise ValueError("sandbox commit clock precedes preparation")
            limit = _limit(preparation["max_age_seconds"])
            catalogues = {market: catalogue_from_payload(preparation["catalogues"][market]) for market in MARKETS}
            work = _clone_memory(self._database)
            basis = _read_basis(work, catalogues, preparation["stage_ids"], str(preparation["expected_predecessor"]), at, limit)
            if _hash(basis) != preparation["read_basis_sha256"]:
                raise ValueError("publication storage read set changed after preparation")
            head, order = basis["head"], basis["explicit_order"]
            cycles, sessions, validation = {}, {}, {}
            for market in MARKETS:
                item = basis["stages"][market]
                stage, prior = item["snapshot"], item["basis"]
                inputs, outputs = stage["inputs"], stage["outputs"]
                cycle_id = str(uuid5(transaction, market))
                snapshot = {"id": cycle_id, "analysis_type": official.UNIVERSE_ANALYSIS,
                            "entity_key": f"{market}_UNIVERSE", "methodology_version_id": prior["methodology_version_id"],
                            "inputs": {"methodology_version": inputs["canonical_methodology_version"],
                                       "source_manifest_sha256": inputs["source_manifest_sha256"],
                                       "run_identity": inputs["run_identity"], "rerun_of": str(stage["id"]),
                                       "prediction_instant": item["prediction_instant"]},
                            "outputs": {**copy.deepcopy(outputs), "universe_size": outputs["inventory_count"]},
                            "published_at": at}
                # Deliberately no save_analysis_snapshot: that method commits and
                # auto-activates each market, which would expose intermediates.
                work._analysis_snapshots.append(copy.deepcopy(snapshot))
                records = []
                for source in official.OFFICIAL_SOURCES:
                    for row in outputs["rows"]:
                        original = item["records"][source][row["symbol"]]
                        record = official.prediction_from_row(
                            row, market=market, scope="universe", cycle_id=cycle_id,
                            source_version=str(inputs["canonical_methodology_version"]),
                            prediction_instant=utc(item["prediction_instant"]), published_at=at,
                            source_manifest_sha256=inputs["source_manifest_sha256"], source=source, rerun_of=str(stage["id"]),
                            extra_provenance={"full_universe_stage": True, "run_identity": inputs["run_identity"],
                                              "context_sha256": outputs["context_sha256"],
                                              "stage_record_sha256": original["row_sha256"]})
                        if record is None:
                            raise ValueError("canonical record became unavailable during composition")
                        records.append(record)
                if work.insert_valuation_predictions(records) != 2 * len(outputs["rows"]):
                    raise ValueError("sandbox composition did not append both canonical sources exactly once")
                for source in official.OFFICIAL_SOURCES:
                    checked = official.cycle_validation(snapshot, recorded=work.valuation_predictions_for_cycle(cycle_id, source=source), source=source)
                    if checked["valid"] is not True:
                        raise ValueError("composed official cycle failed the canonical validator")
                    if source == head["source"]:
                        validation[market], sessions[market] = checked, checked["session_date"]
                cycles[market] = cycle_id
            targeted, recovered, refused = official._recovered_targeted(
                work, official._normalized_targeted(head.get("targeted") or {}), cycles["B3"],
                head=head, order=order, source=str(head["source"]))
            generation = official._new_generation(
                work, expected_previous=str(head["generation_id"]), cycles=cycles, targeted=targeted,
                source=str(head["source"]), source_version=str(head["source_version"]), session_dates=sessions,
                now=at, strict=True, activated_by="full_universe_isolated_sandbox",
                receipt={"full_universe_preparation_sha256": preparation["preparation_sha256"],
                         "explicit_order": order["generation_id"] if order else None, "validation": validation,
                         "targeted_recovered": recovered, "targeted_refused": refused})
            if generation is None or generation["previous_generation_id"] != preparation["expected_predecessor"]:
                raise ValueError("sandbox CAS did not extend exactly its expected predecessor")
            # The only sandbox commit; production/source database is untouched.
            self._database = work
            return {"sandbox_only": True, "generation": copy.deepcopy(generation),
                    "three_market_cycles_committed": True, "post_commit_served_capture_performed": False,
                    **production_preflight()}
