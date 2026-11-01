"""Dormant, rollback-only PostgreSQL publication adapter for explicit review.

No connection is opened here. The caller supplies one idle connection belonging
to the dedicated authenticated publisher. Rehearsal uses exactly one outer
transaction and always raises through its context to roll it back. The public
commit operation is structurally unavailable; local doubles cannot prove real
PostgreSQL grants, triggers, locking, capacity or operational readiness.
"""
from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
import copy
from datetime import datetime, timezone
import json
from typing import Any, Iterator, Mapping, Protocol

from .config import Settings
from .database import Database
from .listed_universe import Catalogue, digest, utc
from .listed_universe_runtime import producer_identity
from . import listed_universe_publication as publication

PUBLISHER = "c3po_full_universe_publisher"
READ_EPOCH = """SELECT epoch_id::text, source, source_version, code_pins_sha256,
readiness_receipt_sha256, reviewed_at, readiness_valid_until
FROM c3po_full_universe.epochs ORDER BY sequence DESC LIMIT 1"""
REGISTER = """INSERT INTO c3po_full_universe.cohorts
(transaction_id, epoch_id, expected_predecessor, cycles, stages, catalogues, preparation_sha256)
VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s)"""
INSERT_SNAPSHOT = """INSERT INTO public.analysis_snapshots
(id, analysis_type, entity_key, methodology_version_id, inputs, outputs, published_at, supersedes_id)
VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)"""
INSERT_RECORD = """INSERT INTO public.valuation_predictions
(id, source, source_version, market, symbol, scope, session_date, cycle_id, prediction_instant, published_at,
tp, buy_in, internal_tp, consensus_tp, consensus_source, analyst_count, consensus_weight_percent, price, currency,
decomposition, row_sha256)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)"""
INSERT_SELECTION = """INSERT INTO public.valuation_official_selection
(generation_id,source,source_version,cycles,targeted,session_dates,validated_complete,activated_at,
activated_by,previous_generation_id,receipt)
VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s::jsonb)"""


class Connection(Protocol):
    @property
    def info(self) -> Any: ...
    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> Any: ...
    def transaction(self, *, force_rollback: bool = False) -> AbstractContextManager[Any]: ...


class ProductionReleaseClosed(RuntimeError):
    pass


class PublicationContractError(RuntimeError):
    pass


class _RollbackRehearsal(Exception):
    pass


class TransactionReadDatabase(Database):
    """Frozen Database read methods bound to the caller's existing transaction.

    Inherited committing persistence methods must never be called. The adapter
    performs all DML directly on the same supplied connection instead.
    """
    def __init__(self, connection: Connection) -> None:
        super().__init__(Settings(database_url="transaction-bound-read-view", auth_cookie_secure=False))
        self._bound = connection

    @contextmanager
    def connection(self) -> Iterator[Any]:
        yield self._bound

    def save_analysis_snapshot(self, *args: Any, **kwargs: Any) -> str:
        raise PublicationContractError("committing_snapshot_api_forbidden_in_cohort_transaction")

    def insert_valuation_predictions(self, records: list[dict[str, Any]]) -> int:
        raise PublicationContractError("committing_prediction_api_forbidden_in_cohort_transaction")

    def insert_valuation_official_selection(self, generation: dict[str, Any]) -> None:
        raise PublicationContractError("committing_selection_api_forbidden_in_cohort_transaction")


def _memory_from_basis(reader: Database, basis: Mapping[str, Any]) -> Database:
    """Pure compilation input from locked reads, not a PostgreSQL proof."""
    memory = publication._IsolatedDatabase(Settings(database_url="", auth_cookie_secure=False))
    snapshots, records = {}, {}
    for item in basis["stages"].values():
        for snapshot in [item["snapshot"], item["basis"]]:
            snapshots[str(snapshot["id"])] = copy.deepcopy(snapshot)
        for source_records in item["records"].values():
            records.update({str(record["id"]): copy.deepcopy(record) for record in source_records.values()})
        selected = reader.valuation_predictions_for_cycle(str(item["basis"]["id"]), source=str(basis["head"]["source"]))
        records.update({str(record["id"]): copy.deepcopy(record) for record in selected.values()})
    for item in basis["targeted"].values():
        snapshots[str(item["cycle"]["id"])] = copy.deepcopy(item["cycle"])
        records.update({str(record["id"]): copy.deepcopy(record) for record in item["records"].values()})
    for snapshot in basis["pending_targeted_cycles"].values():
        if snapshot is not None:
            snapshots[str(snapshot["id"])] = copy.deepcopy(snapshot)
    records.update({str(record["id"]): copy.deepcopy(record) for record in basis["pending_targeted_records"].values()})
    memory._analysis_snapshots = list(snapshots.values())
    memory._valuation_predictions = list(records.values())
    selections = {str(item["generation_id"]): copy.deepcopy(item) for item in [basis["explicit_order"], basis["head"]] if item}
    memory._valuation_official_selections = list(selections.values())
    return memory


def compile_locked(reader: Database, catalogues: Mapping[str, Catalogue], stages: Mapping[str, str], *,
                   expected_predecessor: str, max_age_seconds: float, published_at: datetime) -> dict[str, Any]:
    """Compile canonical INSERT values from one locked, consistent storage view."""
    preparation = publication.prepare_publication(reader, catalogues, stages, expected_predecessor=expected_predecessor,
                                                   max_age_seconds=max_age_seconds, now=published_at)
    basis = publication._read_basis(reader, catalogues, stages, expected_predecessor, published_at, max_age_seconds)
    if publication._hash(basis) != preparation["read_basis_sha256"]:
        raise PublicationContractError("locked_publication_basis_changed")
    memory = _memory_from_basis(reader, basis)
    sandbox = publication.AtomicPublicationSandbox(memory)
    receipt = sandbox.apply(preparation, now=published_at)
    view, generation = sandbox.view(), receipt["generation"]
    cycle_ids = set(generation["cycles"].values())
    snapshots = [copy.deepcopy(item) for item in view._analysis_snapshots if item["id"] in cycle_ids]
    records = [copy.deepcopy(item) for item in view._valuation_predictions if item["cycle_id"] in cycle_ids]
    superseded = {market: reader.latest_analysis_snapshot("valuation_universe", market + "_UNIVERSE") for market in publication.MARKETS}
    if any(item is None for item in superseded.values()):
        raise PublicationContractError("latest_published_cycle_for_supersession_is_absent")
    return {"preparation": preparation, "generation": generation, "snapshots": snapshots, "records": records,
            "superseded_cycles": {market: str(item["id"]) for market, item in superseded.items() if item is not None}}


def _clock(connection: Connection) -> datetime:
    row = connection.execute("SELECT clock_timestamp()").fetchone()
    if not row:
        raise PublicationContractError("postgresql_clock_unavailable")
    return utc(row[0])


def _epoch(connection: Connection, at: datetime) -> dict[str, Any]:
    row = connection.execute("SELECT current_user::text, session_user::text").fetchone()
    if not row or tuple(row) != (PUBLISHER, PUBLISHER):
        raise ProductionReleaseClosed("dedicated_authenticated_publisher_required")
    value = connection.execute(READ_EPOCH).fetchone()
    if not value:
        raise ProductionReleaseClosed("reviewed_database_epoch_absent_fence_not_enabled")
    keys = ("epoch_id", "source", "source_version", "code_pins_sha256", "readiness_receipt_sha256", "reviewed_at", "readiness_valid_until")
    epoch: dict[str, Any] = dict(zip(keys, value))
    if (not utc(epoch["reviewed_at"]) <= at < utc(epoch["readiness_valid_until"])
            or epoch["code_pins_sha256"] != digest(producer_identity())):
        raise ProductionReleaseClosed("reviewed_epoch_expired_or_code_pins_changed_fence_stays_closed")
    # This is an actual restricted DB row when used on PostgreSQL, still not an
    # independently verified operational receipt. Public commit remains closed.
    return epoch


def _write_cohort(connection: Connection, compiled: Mapping[str, Any], epoch: Mapping[str, Any]) -> dict[str, Any]:
    preparation, generation = compiled["preparation"], copy.deepcopy(compiled["generation"])
    _validate_compiled_bindings(compiled)
    if generation["source"] != epoch["source"] or generation["source_version"] != epoch["source_version"]:
        raise ProductionReleaseClosed("epoch_does_not_preserve_selected_source_and_version")
    connection.execute(REGISTER, (preparation["transaction_id"], epoch["epoch_id"], preparation["expected_predecessor"],
        json.dumps(generation["cycles"]), json.dumps(preparation["stage_ids"]),
        json.dumps({market: item["manifest_sha256"] for market, item in preparation["catalogues"].items()}),
        preparation["preparation_sha256"]))
    for snapshot in compiled["snapshots"]:
        market = str(snapshot["entity_key"]).removesuffix("_UNIVERSE")
        connection.execute(INSERT_SNAPSHOT, (snapshot["id"], snapshot["analysis_type"], snapshot["entity_key"],
            snapshot["methodology_version_id"], json.dumps(snapshot["inputs"]), json.dumps(snapshot["outputs"]),
            snapshot["published_at"], compiled["superseded_cycles"][market]))
    for record in compiled["records"]:
        numeric = Database._numeric_param
        connection.execute(INSERT_RECORD, (record["id"], record["source"], record["source_version"], record["market"], record["symbol"],
            record["scope"], record["session_date"], record["cycle_id"], record["prediction_instant"], record["published_at"],
            numeric(record["tp"]), numeric(record["buy_in"]), numeric(record.get("internal_tp")), numeric(record.get("consensus_tp")),
            record.get("consensus_source"), record.get("analyst_count"), numeric(record.get("consensus_weight_percent")),
            numeric(record.get("price")), record["currency"], json.dumps(record.get("decomposition") or {}), record["row_sha256"]))
    _verify_inserted(connection, compiled)
    # Real server clock after the records, never a prepared plan's old clock.
    activation = _clock(connection)
    if activation < utc(generation["activated_at"]):
        raise PublicationContractError("server_clock_receded_during_publication")
    generation["activated_at"] = activation.isoformat()
    connection.execute(INSERT_SELECTION, (generation["generation_id"], generation["source"], generation["source_version"],
        json.dumps(generation["cycles"]), json.dumps(generation["targeted"]), json.dumps(generation["session_dates"]),
        generation["validated_complete"], generation["activated_at"], generation["activated_by"],
        generation["previous_generation_id"], json.dumps(generation["receipt"])))
    return generation


def _validate_compiled_bindings(compiled: Mapping[str, Any]) -> None:
    """Defend the SQL boundary too; this is not a substitute for DB triggers."""
    cycles, stages = compiled["generation"]["cycles"], compiled["preparation"]["stage_ids"]
    if (set(cycles) != set(publication.MARKETS) or set(stages) != set(publication.MARKETS)
            or len(set(cycles.values())) != 3 or len(set(stages.values())) != 3
            or not all(isinstance(value, str) and value for value in [*cycles.values(), *stages.values()])):
        raise PublicationContractError("complete_market_cycle_stage_binding_required")
    snapshots = {item["id"]: item for item in compiled["snapshots"]}
    if set(snapshots) != set(cycles.values()) or len(compiled["snapshots"]) != 3:
        raise PublicationContractError("complete_market_cycle_stage_binding_required")
    for market, cycle in cycles.items():
        snapshot = snapshots[cycle]
        if (snapshot.get("analysis_type") != "valuation_universe" or snapshot.get("entity_key") != market + "_UNIVERSE"
                or snapshot.get("inputs", {}).get("rerun_of") != stages[market]):
            raise PublicationContractError("snapshot_market_cycle_stage_binding_required")
    for record in compiled["records"]:
        market = record.get("market")
        if (market not in publication.MARKETS or record.get("cycle_id") != cycles[market]
                or record.get("decomposition", {}).get("provenance", {}).get("rerun_of") != stages[market]):
            raise PublicationContractError("prediction_market_cycle_stage_binding_required")


def _verify_inserted(connection: Connection, compiled: Mapping[str, Any]) -> None:
    """Re-read transaction-local SQL values/hashes before any selection INSERT."""
    reader = TransactionReadDatabase(connection)
    if compiled["preparation"]["code_pins_sha256"] != digest(producer_identity()):
        raise PublicationContractError("application_code_changed_inside_publication_transaction")
    for expected in compiled["snapshots"]:
        snapshot = reader.analysis_snapshot_by_id(str(expected["id"]))
        if publication._hash(snapshot) != publication._hash(expected):
            raise PublicationContractError("inserted_snapshot_does_not_round_trip")
        for source in publication.official.OFFICIAL_SOURCES:
            records = reader.valuation_predictions_for_cycle(str(expected["id"]), source=source)
            planned = {item["symbol"]: item for item in compiled["records"] if item["cycle_id"] == expected["id"] and item["source"] == source}
            if set(records) != set(planned) or any(
                    not publication._record_integrity(value) or publication._hash(value) != publication._hash(planned[symbol])
                    for symbol, value in records.items()):
                raise PublicationContractError("inserted_canonical_record_does_not_round_trip")


def rehearse(connection: Connection, catalogues: Mapping[str, Catalogue], stages: Mapping[str, str], *,
             expected_predecessor: str, max_age_seconds: float) -> dict[str, Any]:
    """Execute a proposed cohort on ONE supplied transaction, ALWAYS roll back.

    No factory/login/DDL/install/commit option exists. The dormant DDL and actual
    restricted principals would need separate ordered setup before a real trial.
    This function was tested with local connection doubles only in this task.
    """
    if getattr(connection.info, "transaction_status", None) != 0:
        raise ProductionReleaseClosed("a_fresh_idle_connection_is_required_no_nested_transaction")
    result: dict[str, Any] | None = None
    try:
        with connection.transaction(force_rollback=True):
            isolation = connection.execute("SHOW transaction_isolation").fetchone()
            if not isolation or isolation[0] != "read committed":
                raise ProductionReleaseClosed("read_committed_required_no_stale_readiness_snapshot")
            connection.execute("SELECT c3po_full_universe.lock_cohort()")
            at = _clock(connection)
            epoch = _epoch(connection, at)
            compiled = compile_locked(TransactionReadDatabase(connection), catalogues, stages,
                                      expected_predecessor=expected_predecessor, max_age_seconds=max_age_seconds, published_at=at)
            generation = _write_cohort(connection, compiled, epoch)
            result = {"schema": "FULL-UNIVERSE-PG-ROLLBACK-REHEARSAL-v1", "transaction_id": compiled["preparation"]["transaction_id"],
                      "generation_candidate_id": generation["generation_id"], "snapshots_considered": len(compiled["snapshots"]),
                      "records_considered": len(compiled["records"]), "rolled_back": True, "committed": False,
                      "production_release_allowed": False, "postgresql_behavior_proven_by_this_receipt": False,
                      "post_commit_capture_performed": False}
            raise _RollbackRehearsal()
    except _RollbackRehearsal:
        pass
    if result is None:
        raise PublicationContractError("rehearsal_did_not_reach_complete_cohort")
    return result


def commit_publication() -> None:
    """Intentionally unavailable until genuine PostgreSQL/readiness review."""
    raise ProductionReleaseClosed("production_commit_not_implemented_or_authorized_by_local_rehearsal")


def legacy_write_disposition(error: BaseException, *, origin: str) -> dict[str, Any] | None:
    """Sanitized routing contract; no queue update, success or fallback is done.

    Frozen callers still need explicit integration/review before fencing is
    enabled. In particular IR must retain its claim/update and retry later,
    never mark a rejected valuation incorporated or create a targeted workaround.
    """
    sqlstate = getattr(error, "sqlstate", None)
    if sqlstate not in {"PZ001", "PZ002", "PZ003", "PZ004", "PZ005", "PZ006", "55P03", "40001", "40P01"}:
        return None
    if origin not in {"nightly", "ir", "b3_targeted", "us_cache_build", "operator"}:
        raise ValueError("unknown canonical writer origin")
    return {"status": "deferred_by_publication_contract", "origin": origin, "sqlstate": sqlstate,
            "success": False, "keep_current_generation": True, "keep_ir_update_pending": origin == "ir",
            "mark_ir_incorporated": False, "fallback_to_legacy_or_shadow": False,
            "retry_requires_fresh_head_and_window": sqlstate in {"PZ003", "55P03", "40001", "40P01"},
            "automatic_retry_allowed": False,
            "requires_integration_or_fact_review": sqlstate in {"PZ001", "PZ002", "PZ004", "PZ005", "PZ006"},
            "operator_order_not_executed": origin == "operator", "caller_integration_implemented": False}
