from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from .database import Database


SPEC_SHA256 = "e200f2e70aae134f6c669b547d4ff7e435b21c0159069df2b89a5f7f7f7ae83b"
OBSERVATION_SCHEMA_VERSION = "R2D2-SHADOW-CANDIDATE-OBSERVATION-v1"
OUTCOME_SCHEMA_VERSION = "R2D2-SHADOW-CANDIDATE-OUTCOME-v1"
REPORT_SCHEMA_VERSION = "R2D2-SHADOW-CANDIDATE-REPORT-v1"
NEW_YORK = ZoneInfo("America/New_York")
CASCADE_STEPS = frozenset({
    "technical_review_capacity",
    "daily_order_capacity",
    "portfolio_capacity",
    "session_reentry_policy",
    "entry_quality",
    "entry_confirmation",
    "entry_cycle_capacity",
    "entry_execution",
})

POINT_IN_TIME_FIELDS = (
    "market",
    "symbol",
    "name",
    "currency",
    "security_type",
    "price",
    "quote_as_of",
    "quote_status",
    "upside",
    "buy_in_distance",
    "risk_score",
    "fundamental_score",
    "technical_score",
    "composite_score",
    "pretrade_rank",
    "confidence",
    "day_change",
    "raw_cash_volume_usd",
    "spread_bps",
    "stop_price",
    "technical_reviewed",
    "technical_validated",
    "technical_indicators",
    "technical_error",
    "listing_history",
    "valuation_basis",
    "modeled_intraday_edge_percent",
    "simulated_round_trip_cost_percent",
    "learning_version",
    "entry_policy",
    "policy_epoch",
    "methodology_version",
)
OBSERVATION_HASH_FIELDS = (
    "schema_version",
    "experiment_id",
    "cycle_id",
    "session_date",
    "observed_at",
    "market",
    "symbol",
    "policy_epoch",
    "cascade_step",
    "reason_id",
    "decision",
    "rejection_class",
    "quality_rejected",
    "capacity_rejected",
    "reason_detail",
    "point_in_time",
    "trade_id",
)


def _utc(value: datetime) -> datetime:
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc)


def json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        json_ready(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_valid_observation_hash(row: Mapping[str, Any]) -> None:
    payload = {field: row[field] for field in OBSERVATION_HASH_FIELDS}
    if row.get("candidate_sha256") != canonical_sha256(payload):
        raise ValueError(
            f"shadow candidate {row.get('id')} has an invalid candidate_sha256"
        )


def point_in_time_snapshot(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze only decision inputs; never retain a live mutable candidate mapping."""
    return {
        field: json_ready(candidate[field])
        for field in POINT_IN_TIME_FIELDS
        if field in candidate
    }


def entry_rejection_reason_id(reasons: Sequence[str]) -> str:
    joined = " ".join(reasons).lower()
    ordered = (
        ("quote_not_live", "quote is not live"),
        ("technical_confirmation_unavailable", "technical confirmation is unavailable"),
        ("upside_below_floor", "tp upside below"),
        ("risk_above_ceiling", "risk score above"),
        ("confidence_below_floor", "valuation confidence below"),
        ("buy_in_distance_above_ceiling", "above disciplined buy-in"),
        ("technical_score_below_floor", "momentum confirmation is insufficient"),
        ("composite_score_below_floor", "hybrid score below"),
        ("entry_route_not_satisfied", "neither strict tactical nor cost-aware"),
    )
    for reason_id, fragment in ordered:
        if fragment in joined:
            return reason_id
    return "entry_policy_reject"


def build_observation(
    *,
    experiment_id: str,
    cycle_id: str,
    observed_at: datetime,
    candidate: Mapping[str, Any],
    cascade_step: str,
    reason_id: str,
    decision: str,
    rejection_class: str,
    reason_detail: Sequence[str] = (),
    trade_id: str | None = None,
) -> dict[str, Any]:
    if decision not in {"accepted", "rejected"}:
        raise ValueError(f"unsupported shadow decision: {decision}")
    expected_class = "none" if decision == "accepted" else rejection_class
    if expected_class not in {"none", "quality", "capacity"}:
        raise ValueError(f"unsupported rejection class: {expected_class}")
    if (decision == "accepted") != bool(trade_id):
        raise ValueError("accepted shadow candidates require a trade link")
    observed_at = _utc(observed_at)
    market = str(candidate.get("market") or "")
    symbol = str(candidate.get("symbol") or "")
    policy_epoch = str(candidate.get("policy_epoch") or "").strip()
    if market not in {"NASDAQ", "NYSE"} or not symbol or not policy_epoch:
        raise ValueError("shadow candidate identity and policy_epoch are required")
    if cascade_step not in CASCADE_STEPS:
        raise ValueError(f"unsupported shadow cascade step: {cascade_step}")
    if not reason_id.strip():
        raise ValueError("shadow candidate reason_id is required")
    payload: dict[str, Any] = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "experiment_id": str(experiment_id),
        "cycle_id": str(cycle_id),
        "session_date": observed_at.astimezone(NEW_YORK).date(),
        "observed_at": observed_at,
        "market": market,
        "symbol": symbol,
        "policy_epoch": policy_epoch,
        "cascade_step": cascade_step,
        "reason_id": reason_id,
        "decision": decision,
        "rejection_class": expected_class,
        "quality_rejected": expected_class == "quality",
        "capacity_rejected": expected_class == "capacity",
        "reason_detail": [str(reason) for reason in reason_detail],
        "point_in_time": point_in_time_snapshot(candidate),
        "trade_id": str(trade_id) if trade_id else None,
    }
    payload["candidate_sha256"] = canonical_sha256(payload)
    payload["id"] = str(uuid4())
    return payload


class R2D2ShadowCandidateLog:
    """Append-only evidence sink that is never consulted by the trading path."""

    def __init__(self, database: Database) -> None:
        self.database = database
        if not hasattr(database, "_r2d2_shadow_candidates"):
            database._r2d2_shadow_candidates = []  # type: ignore[attr-defined]
        if not hasattr(database, "_r2d2_shadow_candidate_outcomes"):
            database._r2d2_shadow_candidate_outcomes = []  # type: ignore[attr-defined]
        if not hasattr(database, "_r2d2_shadow_candidate_reports"):
            database._r2d2_shadow_candidate_reports = []  # type: ignore[attr-defined]

    def append_observations(self, rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
        if not rows:
            return {"attempted": 0, "written": 0, "deduplicated": 0}
        for row in rows:
            require_valid_observation_hash(row)
        if not self.database.database_url:
            existing = {
                (
                    str(row["experiment_id"]),
                    str(row["session_date"]),
                    str(row["market"]),
                    str(row["symbol"]),
                    str(row["policy_epoch"]),
                    str(row["decision"]),
                )
                for row in self.database._r2d2_shadow_candidates  # type: ignore[attr-defined]
            }
            written = 0
            for source in rows:
                row = dict(source)
                key = (
                    str(row["experiment_id"]),
                    str(row["session_date"]),
                    str(row["market"]),
                    str(row["symbol"]),
                    str(row["policy_epoch"]),
                    str(row["decision"]),
                )
                if key in existing:
                    continue
                self.database._r2d2_shadow_candidates.append(row)  # type: ignore[attr-defined]
                existing.add(key)
                written += 1
            return {
                "attempted": len(rows),
                "written": written,
                "deduplicated": len(rows) - written,
            }

        written = 0
        with self.database.connection() as connection:
            for row in rows:
                cursor = connection.execute(
                    """
                    INSERT INTO r2d2_shadow_candidates
                        (id, schema_version, experiment_id, cycle_id, session_date, observed_at,
                         market, symbol, policy_epoch, cascade_step, reason_id,
                         decision, rejection_class, quality_rejected,
                         capacity_rejected, reason_detail, point_in_time, trade_id,
                         candidate_sha256)
                    VALUES
                        (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                         %s::jsonb,%s::jsonb,%s,%s)
                    ON CONFLICT (
                        experiment_id, session_date, market, symbol, policy_epoch, decision
                    )
                    DO NOTHING
                    """,
                    (
                        row["id"], row["schema_version"], row["experiment_id"],
                        row["cycle_id"], row["session_date"], row["observed_at"], row["market"],
                        row["symbol"], row["policy_epoch"], row["cascade_step"],
                        row["reason_id"], row["decision"], row["rejection_class"],
                        row["quality_rejected"], row["capacity_rejected"],
                        json.dumps(json_ready(row["reason_detail"])),
                        json.dumps(json_ready(row["point_in_time"])), row.get("trade_id"),
                        row["candidate_sha256"],
                    ),
                )
                written += max(0, cursor.rowcount)
            connection.commit()
        return {
            "attempted": len(rows),
            "written": written,
            "deduplicated": len(rows) - written,
        }

    def observations(
        self,
        *,
        experiment_id: str | None = None,
        session_date: date | None = None,
    ) -> list[dict[str, Any]]:
        if not self.database.database_url:
            rows = [
                dict(row)
                for row in self.database._r2d2_shadow_candidates  # type: ignore[attr-defined]
                if (experiment_id is None or str(row["experiment_id"]) == experiment_id)
                and (session_date is None or row["session_date"] == session_date)
            ]
            for row in rows:
                require_valid_observation_hash(row)
            return sorted(rows, key=self._observation_sort_key)
        clauses: list[str] = []
        arguments: list[Any] = []
        if experiment_id is not None:
            clauses.append("experiment_id = %s")
            arguments.append(experiment_id)
        if session_date is not None:
            clauses.append("session_date = %s")
            arguments.append(session_date)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.database.connection() as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            rows = connection.execute(
                f"""
                SELECT id::text, schema_version, experiment_id::text, cycle_id::text, session_date,
                       observed_at, market, symbol, policy_epoch, cascade_step,
                       reason_id, decision, rejection_class, quality_rejected,
                       capacity_rejected, reason_detail, point_in_time,
                       trade_id::text, candidate_sha256, created_at
                FROM r2d2_shadow_candidates
                {where}
                ORDER BY observed_at, market, symbol, decision, id
                """,
                arguments,
            ).fetchall()
            connection.rollback()
        keys: tuple[str, ...] = (
            "id", "schema_version", "experiment_id", "cycle_id", "session_date", "observed_at",
            "market", "symbol", "policy_epoch", "cascade_step", "reason_id",
            "decision", "rejection_class", "quality_rejected", "capacity_rejected",
            "reason_detail", "point_in_time", "trade_id", "candidate_sha256",
            "created_at",
        )
        output: list[dict[str, Any]] = [dict(zip(keys, row)) for row in rows]
        for row in output:
            require_valid_observation_hash(row)
        return output

    def trade(self, trade_id: str) -> dict[str, Any] | None:
        if not self.database.database_url:
            memory = getattr(self.database, "_r2d2_memory", None) or {}
            row = next(
                (item for item in memory.get("trades", ()) if str(item.get("id")) == trade_id),
                None,
            )
            return dict(row) if row else None
        with self.database.connection() as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            row = connection.execute(
                """
                SELECT id::text, cycle_id::text, market, symbol, name, side, quantity,
                       signal_price_local, fill_price_local, fx_to_usd,
                       gross_value_usd, fees_usd, slippage_usd, realized_pnl_usd,
                       reason, decision_snapshot, executed_at, quote_as_of
                FROM r2d2_trades WHERE id = %s
                """,
                (trade_id,),
            ).fetchone()
            connection.rollback()
        if row is None:
            return None
        keys = (
            "id", "cycle_id", "market", "symbol", "name", "side", "quantity",
            "signal_price_local", "fill_price_local", "fx_to_usd",
            "gross_value_usd", "fees_usd", "slippage_usd", "realized_pnl_usd",
            "reason", "decision_snapshot", "executed_at", "quote_as_of",
        )
        return dict(zip(keys, row))

    def append_outcomes(self, rows: Sequence[Mapping[str, Any]]) -> int:
        for row in rows:
            if row.get("outcome_sha256") != canonical_sha256(row["outcome_payload"]):
                raise ValueError(
                    f"shadow outcome {row.get('id')} has an invalid outcome_sha256"
                )
        if not self.database.database_url:
            existing = {
                str(row["candidate_id"])
                for row in self.database._r2d2_shadow_candidate_outcomes  # type: ignore[attr-defined]
            }
            written = 0
            for source in rows:
                row = dict(source)
                if str(row["candidate_id"]) in existing:
                    continue
                self.database._r2d2_shadow_candidate_outcomes.append(row)  # type: ignore[attr-defined]
                existing.add(str(row["candidate_id"]))
                written += 1
            return written
        written = 0
        with self.database.connection() as connection:
            for row in rows:
                cursor = connection.execute(
                    """
                    INSERT INTO r2d2_shadow_candidate_outcomes
                        (id, candidate_id, session_date, coverage_classification,
                         barrier_category, counterfactual_r, outcome_payload,
                         outcome_sha256, measured_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                    ON CONFLICT (candidate_id) DO NOTHING
                    """,
                    (
                        row["id"], row["candidate_id"], row["session_date"],
                        row["coverage_classification"], row.get("barrier_category"),
                        row.get("counterfactual_r"),
                        json.dumps(json_ready(row["outcome_payload"])),
                        row["outcome_sha256"], row["measured_at"],
                    ),
                )
                written += max(0, cursor.rowcount)
            connection.commit()
        return written

    def outcomes(self, session_date: date) -> list[dict[str, Any]]:
        if not self.database.database_url:
            rows = [
                dict(row)
                for row in self.database._r2d2_shadow_candidate_outcomes  # type: ignore[attr-defined]
                if row["session_date"] == session_date
            ]
            return sorted(rows, key=lambda row: str(row["candidate_id"]))
        with self.database.connection() as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            rows = connection.execute(
                """
                SELECT id::text, candidate_id::text, session_date,
                       coverage_classification, barrier_category, counterfactual_r,
                       outcome_payload, outcome_sha256, measured_at, created_at
                FROM r2d2_shadow_candidate_outcomes
                WHERE session_date = %s
                ORDER BY candidate_id
                """,
                (session_date,),
            ).fetchall()
            connection.rollback()
        keys = (
            "id", "candidate_id", "session_date", "coverage_classification",
            "barrier_category", "counterfactual_r", "outcome_payload",
            "outcome_sha256", "measured_at", "created_at",
        )
        return [dict(zip(keys, row)) for row in rows]

    def report_exists(self, experiment_id: str, session_date: date) -> bool:
        if not self.database.database_url:
            return any(
                str(row["experiment_id"]) == experiment_id
                and row["session_date"] == session_date
                for row in self.database._r2d2_shadow_candidate_reports  # type: ignore[attr-defined]
            )
        with self.database.connection() as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            exists = connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM r2d2_shadow_candidate_reports
                    WHERE experiment_id = %s AND session_date = %s
                )
                """,
                (experiment_id, session_date),
            ).fetchone()[0]
            connection.rollback()
        return bool(exists)

    def save_report(
        self,
        *,
        experiment_id: str,
        session_date: date,
        generated_at: datetime,
        candidate_count: int,
        jsonl_sha256: str,
        report_sha256: str,
        output_path: str,
        report: Mapping[str, Any],
    ) -> None:
        expected_report_sha256 = canonical_sha256({
            key: value for key, value in report.items() if key != "report_sha256"
        })
        if (
            report.get("report_sha256") != report_sha256
            or report_sha256 != expected_report_sha256
        ):
            raise ValueError("shadow candidate report has an invalid report_sha256")
        row = {
            "id": str(uuid4()),
            "experiment_id": experiment_id,
            "session_date": session_date,
            "generated_at": _utc(generated_at),
            "candidate_count": candidate_count,
            "jsonl_sha256": jsonl_sha256,
            "report_sha256": report_sha256,
            "output_path": output_path,
            "report": json_ready(report),
        }
        if not self.database.database_url:
            if self.report_exists(experiment_id, session_date):
                return
            self.database._r2d2_shadow_candidate_reports.append(row)  # type: ignore[attr-defined]
            return
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO r2d2_shadow_candidate_reports
                    (id, experiment_id, session_date, generated_at, candidate_count,
                     jsonl_sha256, report_sha256, output_path, report)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (experiment_id, session_date) DO NOTHING
                """,
                (
                    row["id"], experiment_id, session_date, row["generated_at"],
                    candidate_count, jsonl_sha256, report_sha256, output_path,
                    json.dumps(row["report"]),
                ),
            )
            connection.commit()

    def pending_sessions(self, experiment_id: str) -> list[date]:
        observed = {
            row["session_date"]
            for row in self.observations(experiment_id=experiment_id)
        }
        return sorted(
            session for session in observed
            if not self.report_exists(experiment_id, session)
        )

    @staticmethod
    def _observation_sort_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
        return (
            str(row.get("observed_at")),
            str(row.get("market")),
            str(row.get("symbol")),
            str(row.get("decision")),
            str(row.get("id")),
        )
