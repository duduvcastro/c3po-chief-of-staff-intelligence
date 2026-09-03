#!/usr/bin/env python3
"""Build one transient ENTRY_QUALITY M1 session snapshot.

This program is intentionally run *inside the already-running production API
container*.  It reads the small trade ledger, restricts it to one current-policy
session, and only then invokes the frozen price reader and measurement functions.
Consequently at most one session of minute bars is resident in memory.

The output is an intermediate input, not a retainable evidence artefact: it
contains entry identifiers solely so the runner can replace baseline rows
idempotently and reproduce the frozen H3 tie-break.  The runner-side reducer
removes all identifiers and rows before publishing evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.database import Database
from app.r2d2_entry_quality_engine import (
    EntryQualityStudyError,
    measure_entry,
    reconcile_entry_gate,
)
from app.r2d2_entry_quality_study import (
    CURRENT_M1_POLICY_EPOCH,
    EntryLedgerReader,
    _coverage_gate,
    _epoch_for,
    _load_policy_epochs,
    _read_price_paths,
)
from app.r2d2_exit_policy_study import _json_ready, _ledger_fill, canonical_sha256


SCHEMA = "C3PO_ENTRY_QUALITY_M1_SESSION_SNAPSHOT-v1"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_TIMEOUTS = {
    "statement_timeout": {"2min", "120s", "120000ms"},
    "lock_timeout": {"5s", "5000ms"},
}
FETCH_BATCH_SIZE = 128
NEW_YORK = __import__("zoneinfo").ZoneInfo("America/New_York")

EXPERIMENT_KEYS = (
    "id",
    "code",
    "status",
    "starting_capital",
    "start_date",
    "methodology_version",
    "created_at",
    "updated_at",
)
TRADE_KEYS = (
    "id",
    "cycle_id",
    "market",
    "symbol",
    "name",
    "side",
    "quantity",
    "signal_price_local",
    "fill_price_local",
    "fx_to_usd",
    "gross_value_usd",
    "fees_usd",
    "slippage_usd",
    "realized_pnl_usd",
    "reason",
    "decision_snapshot",
    "executed_at",
    "quote_as_of",
)
OBSERVATION_KEYS = (
    "cycle_id",
    "policy_epoch",
    "decision_at",
    "market",
    "symbol",
    "source_references",
    "valuation_comparisons",
    "candidate_context",
    "candidate_sha256",
)


def _parse_session(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("session must be YYYY-MM-DD") from exc


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_hashes() -> dict[str, str]:
    import app.r2d2_entry_quality_engine as engine
    import app.r2d2_entry_quality_study as study

    return {
        "r2d2_entry_quality_engine.py": _hash_file(Path(engine.__file__).resolve()),
        "r2d2_entry_quality_study.py": _hash_file(Path(study.__file__).resolve()),
    }


def _database_access(database: Database) -> dict[str, Any]:
    with database.connection() as connection:
        if connection is None:
            raise SystemExit("production database is unavailable")
        row = connection.execute(
            """
            SELECT current_user,
                   current_setting('transaction_read_only'),
                   current_setting('statement_timeout'),
                   current_setting('lock_timeout')
            """
        ).fetchone()
        connection.rollback()
    role, read_only, statement_timeout, lock_timeout = map(str, row)
    if role != "pg_read_all_data":
        raise SystemExit("effective database role is not the dedicated read-all role")
    if read_only != "on":
        raise SystemExit("database transaction is not read-only")
    observed = {
        "statement_timeout": statement_timeout,
        "lock_timeout": lock_timeout,
    }
    for field, accepted in ALLOWED_TIMEOUTS.items():
        if observed[field] not in accepted:
            raise SystemExit(f"database {field} is not pinned")
    return {
        "effective_role": role,
        "transaction_read_only": True,
        **observed,
        "ddl_or_dml_executed": False,
    }


def _server_rows(
    connection: Any,
    *,
    name: str,
    query: str,
    params: tuple[Any, ...],
) -> list[tuple[Any, ...]]:
    """Fetch one bounded session through a named PostgreSQL cursor."""
    rows: list[tuple[Any, ...]] = []
    with connection.cursor(name=name) as cursor:
        cursor.execute(query, params)
        while True:
            batch = cursor.fetchmany(FETCH_BATCH_SIZE)
            if not batch:
                break
            rows.extend(batch)
    return rows


def _session_bounds(session: date) -> tuple[datetime, datetime]:
    start = datetime.combine(session, time.min, tzinfo=NEW_YORK)
    end = datetime.combine(session + timedelta(days=1), time.min, tzinfo=NEW_YORK)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _read_session_records(
    database: Database,
    *,
    experiment_code: str,
    session: date,
) -> tuple[dict[str, Any], list[Any]]:
    """Exact EntryLedgerReader semantics, bounded to one NY session.

    The prior implementation called EntryLedgerReader.read(), whose observations
    query used fetchall() across the complete experiment.  This variant retains
    its selected columns, ordering, conversion and _records filtering while
    constraining both server cursors to the requested session.
    """
    if not database.database_url:
        raise SystemExit("production database is unavailable")
    start_at, end_at = _session_bounds(session)
    with database.connection() as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        experiment_row = connection.execute(
            """
            SELECT id::text, code, status, starting_capital, start_date,
                   methodology_version, created_at, updated_at
            FROM r2d2_experiments
            WHERE code = %s
            """,
            (experiment_code,),
        ).fetchone()
        if not experiment_row:
            raise EntryQualityStudyError(
                f"R2D2 experiment not found: {experiment_code}"
            )
        trade_tuples = _server_rows(
            connection,
            name="m1_session_trades",
            query="""
                SELECT id::text, cycle_id::text, market, symbol, name, side,
                       quantity, signal_price_local, fill_price_local, fx_to_usd,
                       gross_value_usd, fees_usd, slippage_usd,
                       realized_pnl_usd, reason, decision_snapshot,
                       executed_at, quote_as_of
                FROM r2d2_trades
                WHERE experiment_id = %s
                  AND side = 'BUY'
                  AND executed_at >= %s
                  AND executed_at < %s
                ORDER BY executed_at, id
            """,
            params=(experiment_row[0], start_at, end_at),
        )
        observation_tuples = _server_rows(
            connection,
            name="m1_session_observations",
            query="""
                SELECT observation.cycle_id::text, observation.policy_epoch,
                       observation.decision_at, observation.market,
                       observation.symbol, observation.source_references,
                       observation.valuation_comparisons,
                       observation.candidate_context,
                       observation.candidate_sha256
                FROM r2d2_entry_score_observations AS observation
                WHERE observation.experiment_id = %s
                  AND EXISTS (
                      SELECT 1
                      FROM r2d2_trades AS trade
                      WHERE trade.experiment_id = observation.experiment_id
                        AND trade.side = 'BUY'
                        AND trade.executed_at >= %s
                        AND trade.executed_at < %s
                        AND trade.cycle_id IS NOT DISTINCT FROM observation.cycle_id
                        AND trade.market = observation.market
                        AND trade.symbol = observation.symbol
                  )
                ORDER BY observation.decision_at,
                         observation.market,
                         observation.symbol
            """,
            params=(experiment_row[0], start_at, end_at),
        )
        connection.rollback()

    experiment = dict(zip(EXPERIMENT_KEYS, experiment_row))
    trade_rows = [dict(zip(TRADE_KEYS, row)) for row in trade_tuples]
    fills = [_ledger_fill(row) for row in trade_rows]
    cycles = {str(row["id"]): row.get("cycle_id") for row in trade_rows}
    observations = [
        dict(zip(OBSERVATION_KEYS, row)) for row in observation_tuples
    ]
    return experiment, EntryLedgerReader._records(fills, cycles, observations)


def build_snapshot(
    *,
    session: date,
    policy_epochs_path: Path,
    query_sha256: str,
) -> dict[str, Any]:
    if not HEX_64.fullmatch(query_sha256):
        raise SystemExit("query source SHA-256 is missing or invalid")
    settings = get_settings()
    database = Database(settings)
    access = _database_access(database)
    epochs, epoch_evidence = _load_policy_epochs(policy_epochs_path)
    experiment, all_records = _read_session_records(
        database,
        experiment_code=settings.r2d2_experiment_code,
        session=session,
    )

    selected = []
    epoch_by_entry: dict[str, str] = {}
    for record in all_records:
        observed_session = record.fill.executed_at.astimezone(NEW_YORK).date()
        if observed_session != session:
            continue
        epoch = _epoch_for(record.fill, epochs)
        if epoch != CURRENT_M1_POLICY_EPOCH:
            continue
        selected.append(record)
        epoch_by_entry[record.fill.id] = epoch
    if not selected:
        raise SystemExit(
            f"no {CURRENT_M1_POLICY_EPOCH} entries exist for {session.isoformat()}"
        )

    # Memory boundary: this is the first invocation that touches price files,
    # and selected contains exactly one session.
    bars, price_sources = _read_price_paths(settings, selected)
    coverage = _coverage_gate(selected, bars, epoch_by_entry)
    gate = reconcile_entry_gate(
        [record.fill for record in selected],
        bars,
        constructed_entry_count=len(selected),
    )
    censorship = gate["g3_coverage_censorship"]
    violation_ids = set(censorship["violation_entry_ids"])
    unavailable_ids = set(censorship["bar_unavailable_entry_ids"])
    measurements: list[dict[str, Any]] = []
    measurement_censoring: dict[str, int] = defaultdict(int)
    for record in selected:
        fill = record.fill
        if fill.id in violation_ids:
            measurement_censoring["market_compatibility_violation"] += 1
            continue
        if fill.id in unavailable_ids:
            measurement_censoring["bar_unavailable"] += 1
            continue
        try:
            measurements.append(asdict(measure_entry(
                fill,
                bars.get(fill.symbol, ()),
                policy_epoch=CURRENT_M1_POLICY_EPOCH,
                qqq_bars=bars.get("QQQ", ()),
            )))
        except EntryQualityStudyError as exc:
            reason = str(exc)
            if "persisted stop" in reason:
                key = "missing_persisted_stop"
            elif "post-entry bars" in reason:
                key = "missing_future_trade_bars"
            else:
                key = "measurement_infeasible"
            measurement_censoring[key] += 1

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc),
        "session_date": session,
        "policy_epoch": CURRENT_M1_POLICY_EPOCH,
        "query_sha256": query_sha256,
        "database_access": access,
        "experiment": {
            "code": str(experiment["code"]),
            "status": str(experiment["status"]),
        },
        "frozen_source_sha256": _source_hashes(),
        "policy_epochs_sha256": epoch_evidence["sha256"],
        "source_entry_ids": sorted(record.fill.id for record in selected),
        "ledger_session_sha256": canonical_sha256([
            asdict(record.fill) for record in selected
        ]),
        "price_sources_sha256": canonical_sha256(price_sources),
        "price_sources": price_sources,
        "coverage_sha256": canonical_sha256(coverage),
        "coverage": coverage,
        "entry_gate_sha256": canonical_sha256(gate),
        "entry_gate": gate,
        "measurement_censoring": dict(sorted(measurement_censoring.items())),
        "measurements": measurements,
    }
    # canonical_sha256 normalizes date/datetime values with _json_ready.  Return
    # that exact representation too, so a runner round-trip cannot change the
    # bytes covered by the self-hash.
    ready = _json_ready(payload)
    ready["snapshot_sha256"] = canonical_sha256(ready)
    return ready


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=_parse_session, required=True)
    parser.add_argument(
        "--policy-epochs",
        type=Path,
        default=Path("/legacy/c3po/docs/ENTRY_QUALITY_STUDY_V1_POLICY_EPOCHS.json"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = build_snapshot(
        session=args.session,
        policy_epochs_path=args.policy_epochs,
        query_sha256=os.environ.get("C3PO_EVIDENCE_QUERY_SHA256", ""),
    )
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
