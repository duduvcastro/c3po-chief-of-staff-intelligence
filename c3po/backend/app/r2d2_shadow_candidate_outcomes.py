from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from .config import Settings, get_settings
from .database import Database
from .r2d2 import R2D2Repository, _paper_buy_execution
from .r2d2_entry_quality_engine import (
    EntryQualityStudyError,
    classify_entry_market_compatibility,
    measure_entry,
)
from .r2d2_entry_quality_study import (
    ATTESTATION_SHA256,
    ATTESTATION_TWO_SHA256,
    EntryRecord,
    _read_price_paths,
)
from .r2d2_exit_policy_engine import LedgerFill, StudyBar
from .r2d2_exit_policy_study import (
    _ledger_fill,
    ledger_candidate_line,
    require_frozen_document,
    sha256_file,
    write_immutable_json,
)
from .r2d2_shadow_candidate_log import (
    OUTCOME_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
    SPEC_SHA256,
    R2D2ShadowCandidateLog,
    canonical_json_bytes,
    canonical_sha256,
    json_ready,
    require_valid_observation_hash,
)


NEW_YORK = ZoneInfo("America/New_York")
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
REGULAR_CLOSE = time(16, 0)
FIRST_FORMAL_READING_SESSIONS = 5
SCORE_BANDS = (
    ("below_60", float("-inf"), 60.0),
    ("60_to_below_72", 60.0, 72.0),
    ("72_and_above", 72.0, float("inf")),
)


class ShadowCandidateOutcomeError(RuntimeError):
    pass


def _aware(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        return None
    return parsed


def _docs_root() -> Path:
    candidates = (
        Path("/legacy/c3po/docs"),
        Path(__file__).resolve().parents[2] / "docs",
        Path(__file__).resolve().parents[1] / "docs",
    )
    return next((path for path in candidates if path.is_dir()), candidates[1])


def frozen_contract(
    *,
    spec_path: Path | None = None,
    attestation_path: Path | None = None,
    attestation_two_path: Path | None = None,
) -> dict[str, Any]:
    docs = _docs_root()
    return {
        "spec": require_frozen_document(
            spec_path or docs / "R2D2_SHADOW_CANDIDATE_LOG_V1.md",
            SPEC_SHA256,
            "frozen R2D2_SHADOW_CANDIDATE_LOG_V1 spec",
        ),
        "entry_study_attestation_1": require_frozen_document(
            attestation_path or docs / "ENTRY_QUALITY_STUDY_V1_RUNNER_ATTESTATION_1.md",
            ATTESTATION_SHA256,
            "signed entry-study runner attestation 1",
        ),
        "entry_study_attestation_2": require_frozen_document(
            attestation_two_path or docs / "ENTRY_QUALITY_STUDY_V1_RUNNER_ATTESTATION_2.md",
            ATTESTATION_TWO_SHA256,
            "signed entry-study runner attestation 2",
        ),
    }


def _synthetic_fill(observation: Mapping[str, Any]) -> LedgerFill:
    point_in_time = dict(observation.get("point_in_time") or {})
    price = _number(point_in_time.get("price"))
    stop_price = _number(point_in_time.get("stop_price"))
    if price is None or price <= 0:
        raise ShadowCandidateOutcomeError(
            f"candidate {observation.get('id')} has no positive signal price"
        )
    if stop_price is None or stop_price <= 0:
        raise ShadowCandidateOutcomeError(
            f"candidate {observation.get('id')} has no positive point-in-time stop"
        )
    observed_at = _aware(observation["observed_at"])
    quote_as_of = _aware(point_in_time.get("quote_as_of") or observed_at)
    execution = _paper_buy_execution(
        market=str(observation["market"]),
        price=price,
        quantity=1.0,
        fx=1.0,
    )
    return LedgerFill(
        id=str(observation["id"]),
        market=str(observation["market"]),
        symbol=str(observation["symbol"]),
        name=str(point_in_time.get("name") or observation["symbol"]),
        side="BUY",
        quantity=1.0,
        signal_price_local=price,
        fill_price_local=execution["fill_price"],
        fx_to_usd=1.0,
        gross_value_usd=execution["gross_value_usd"],
        fees_usd=execution["fees_usd"],
        slippage_usd=execution["slippage_usd"],
        realized_pnl_usd=None,
        reason=" ".join(str(value) for value in observation.get("reason_detail") or ()),
        decision_snapshot={
            **point_in_time,
            "stop_price": stop_price,
            "entry_decision_reasons": list(observation.get("reason_detail") or ()),
            "shadow_counterfactual": True,
        },
        executed_at=observed_at,
        quote_as_of=quote_as_of,
    )


def candidate_fill(
    observation: Mapping[str, Any],
    store: R2D2ShadowCandidateLog,
) -> tuple[LedgerFill, str]:
    trade_id = observation.get("trade_id")
    if trade_id:
        trade = store.trade(str(trade_id))
        if trade is None:
            raise ShadowCandidateOutcomeError(
                f"accepted candidate {observation.get('id')} has no linked trade"
            )
        return _ledger_fill(trade), "linked_trade"
    return _synthetic_fill(observation), "synthetic_paper_buy"


def _bar_map(rows: Sequence[StudyBar]) -> dict[datetime, StudyBar]:
    return {bar.start_at.astimezone(timezone.utc): bar for bar in rows}


def measure_candidate_outcome(
    *,
    observation: Mapping[str, Any],
    fill: LedgerFill,
    fill_source: str,
    bars: Sequence[StudyBar],
    qqq_bars: Sequence[StudyBar],
    measured_at: datetime,
) -> dict[str, Any]:
    compatibility = classify_entry_market_compatibility(fill, _bar_map(bars))
    coverage = "available"
    barrier_category: str | None = None
    counterfactual_r: float | None = None
    measurement: dict[str, Any] | None = None
    censor_reason: str | None = None
    classification = str(compatibility.get("classification"))
    if classification == "bar_unavailable":
        coverage = "bar_unavailable"
        censor_reason = "entry_bar_unavailable"
    elif classification == "violation":
        coverage = "market_compatibility_violation"
        censor_reason = "numeric_market_compatibility_violation"
    else:
        try:
            measured = measure_entry(
                fill,
                bars,
                policy_epoch=str(observation["policy_epoch"]),
                qqq_bars=qqq_bars,
            )
        except EntryQualityStudyError as exc:
            if "post-entry bars" not in str(exc):
                raise
            coverage = "bar_unavailable"
            censor_reason = "post_entry_bar_unavailable"
        else:
            measurement = json_ready(asdict(measured))
            barrier_category = measured.barrier_category
            counterfactual_r = {
                "upper_first": 1.0,
                "lower_first": -1.0,
            }.get(barrier_category)
    payload: dict[str, Any] = {
        "schema_version": OUTCOME_SCHEMA_VERSION,
        "candidate_id": str(observation["id"]),
        "candidate_sha256": str(observation["candidate_sha256"]),
        "session_date": observation["session_date"],
        "market": observation["market"],
        "symbol": observation["symbol"],
        "decision": observation["decision"],
        "fill_source": fill_source,
        "fill": json_ready(asdict(fill)),
        "market_compatibility": json_ready(compatibility),
        "coverage_classification": coverage,
        "censor_reason": censor_reason,
        "barrier_category": barrier_category,
        "counterfactual_r": counterfactual_r,
        "measurement": measurement,
        "measured_at": measured_at,
    }
    outcome_sha256 = canonical_sha256(payload)
    return {
        "id": str(uuid4()),
        "candidate_id": str(observation["id"]),
        "session_date": observation["session_date"],
        "coverage_classification": coverage,
        "barrier_category": barrier_category,
        "counterfactual_r": counterfactual_r,
        "outcome_payload": payload,
        "outcome_sha256": outcome_sha256,
        "measured_at": measured_at,
    }


def _score_band(value: Any) -> str:
    score = _number(value)
    if score is None:
        return "unavailable"
    return next(
        name for name, lower, upper in SCORE_BANDS
        if lower <= score < upper
    )


def _median(values: Sequence[float]) -> float | None:
    return round(float(statistics.median(values)), 6) if values else None


def preregistered_metrics(
    observations: Sequence[Mapping[str, Any]],
    outcomes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    outcome_by_candidate = {
        str(row["candidate_id"]): row for row in outcomes
    }
    rejected = [row for row in observations if row["decision"] == "rejected"]
    rejection_distribution = Counter(str(row["reason_id"]) for row in rejected)
    cascade_distribution = Counter(str(row["cascade_step"]) for row in rejected)
    class_distribution = Counter(str(row["rejection_class"]) for row in rejected)

    r_by_step: dict[str, list[float]] = defaultdict(list)
    r_by_cascade_step: dict[str, list[float]] = defaultdict(list)
    for observation in rejected:
        outcome = outcome_by_candidate.get(str(observation["id"]))
        if outcome is None or outcome.get("counterfactual_r") is None:
            continue
        value = float(outcome["counterfactual_r"])
        r_by_step[str(observation["reason_id"])].append(value)
        r_by_cascade_step[str(observation["cascade_step"])].append(value)

    by_decision_and_score: dict[str, dict[str, Any]] = {}
    for decision in ("accepted", "rejected"):
        for band in (*[row[0] for row in SCORE_BANDS], "unavailable"):
            rows = [
                observation for observation in observations
                if observation["decision"] == decision
                and _score_band(
                    (observation.get("point_in_time") or {}).get("composite_score")
                ) == band
            ]
            categories = Counter(
                str(outcome_by_candidate[str(row["id"])].get("barrier_category"))
                for row in rows
                if str(row["id"]) in outcome_by_candidate
                and outcome_by_candidate[str(row["id"])].get("barrier_category") is not None
            )
            decided = categories["upper_first"] + categories["lower_first"]
            by_decision_and_score[f"{decision}:{band}"] = {
                "candidate_count": len(rows),
                "decided_count": decided,
                "upper_first": categories["upper_first"],
                "lower_first": categories["lower_first"],
                "ambiguous_same_bar": categories["ambiguous_same_bar"],
                "censored": categories["censored"],
                "win_rate_percent": (
                    round(categories["upper_first"] / decided * 100, 6)
                    if decided else None
                ),
            }

    return {
        "rejection_distribution_by_reason_id": dict(sorted(rejection_distribution.items())),
        "rejection_distribution_by_cascade_step": dict(sorted(cascade_distribution.items())),
        "quality_capacity_split": {
            "quality": class_distribution["quality"],
            "capacity": class_distribution["capacity"],
        },
        "renounced_r_by_reason_id": {
            reason_id: {
                "decided_count": len(values),
                "sum_r": round(sum(values), 6),
                "median_r": _median(values),
            }
            for reason_id, values in sorted(r_by_step.items())
        },
        "renounced_r_by_cascade_step": {
            cascade_step: {
                "decided_count": len(values),
                "sum_r": round(sum(values), 6),
                "median_r": _median(values),
            }
            for cascade_step, values in sorted(r_by_cascade_step.items())
        },
        "win_rate_by_decision_and_score_band": by_decision_and_score,
        "score_band_contract": [
            {
                "id": name,
                "minimum_inclusive": lower if lower != float("-inf") else None,
                "maximum_exclusive": upper if upper != float("inf") else None,
            }
            for name, lower, upper in SCORE_BANDS
        ],
    }


def _report_hash(report: Mapping[str, Any]) -> str:
    return canonical_sha256({
        key: value for key, value in report.items() if key != "report_sha256"
    })


def build_plan(
    *,
    store: R2D2ShadowCandidateLog,
    experiment_id: str,
    session_date: date,
    spec_path: Path | None = None,
    attestation_path: Path | None = None,
    attestation_two_path: Path | None = None,
) -> dict[str, Any]:
    contract = frozen_contract(
        spec_path=spec_path,
        attestation_path=attestation_path,
        attestation_two_path=attestation_two_path,
    )
    observations = store.observations(
        experiment_id=experiment_id,
        session_date=session_date,
    )
    return {
        "schema_version": "R2D2-SHADOW-CANDIDATE-PLAN-v1",
        "command": "plan",
        "read_only": True,
        "trading_state_writes": 0,
        "external_api_calls": 0,
        "session_date": session_date.isoformat(),
        "candidate_count": len(observations),
        "candidate_ids_sha256": canonical_sha256([
            row["id"] for row in observations
        ]),
        "candidate_rows_sha256": canonical_sha256([
            row["candidate_sha256"] for row in observations
        ]),
        "report_already_exists": store.report_exists(experiment_id, session_date),
        "frozen_contract": contract,
    }


def build_report(
    *,
    settings: Settings,
    store: R2D2ShadowCandidateLog,
    experiment_id: str,
    session_date: date,
    generated_at: datetime | None = None,
    spec_path: Path | None = None,
    attestation_path: Path | None = None,
    attestation_two_path: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], bytes]:
    generated_at = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    plan = build_plan(
        store=store,
        experiment_id=experiment_id,
        session_date=session_date,
        spec_path=spec_path,
        attestation_path=attestation_path,
        attestation_two_path=attestation_two_path,
    )
    observations = store.observations(
        experiment_id=experiment_id,
        session_date=session_date,
    )
    if not observations:
        raise ShadowCandidateOutcomeError(
            f"no shadow candidates were recorded for {session_date.isoformat()}"
        )
    fills_with_sources = [candidate_fill(row, store) for row in observations]
    records = [
        EntryRecord(fill=fill, cycle_id=str(row["cycle_id"]), adapter_observation=None)
        for row, (fill, _source) in zip(observations, fills_with_sources)
    ]
    bars, price_evidence = _read_price_paths(settings, records)
    outcomes = [
        measure_candidate_outcome(
            observation=observation,
            fill=fill,
            fill_source=fill_source,
            bars=bars.get(fill.symbol, ()),
            qqq_bars=bars.get("QQQ", ()),
            measured_at=generated_at,
        )
        for observation, (fill, fill_source) in zip(observations, fills_with_sources)
    ]
    outcome_by_candidate = {str(row["candidate_id"]): row for row in outcomes}
    jsonl_rows: list[dict[str, Any]] = []
    for observation in observations:
        outcome = outcome_by_candidate[str(observation["id"])]
        line: dict[str, Any] = {
            "observation": json_ready(observation),
            "outcome": json_ready(outcome["outcome_payload"]),
            "outcome_sha256": outcome["outcome_sha256"],
        }
        line["line_sha256"] = canonical_sha256(line)
        jsonl_rows.append(line)
    jsonl_bytes = b"".join(canonical_json_bytes(row) + b"\n" for row in jsonl_rows)
    jsonl_sha256 = hashlib.sha256(jsonl_bytes).hexdigest()
    all_sessions = {
        row["session_date"]
        for row in store.observations(experiment_id=experiment_id)
    }
    barrier_counts = Counter(
        str(row.get("barrier_category"))
        for row in outcomes if row.get("barrier_category") is not None
    )
    coverage_counts = Counter(str(row["coverage_classification"]) for row in outcomes)
    metrics = preregistered_metrics(observations, outcomes)
    formal_reading_available = len(all_sessions) >= FIRST_FORMAL_READING_SESSIONS
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": generated_at,
        "session_date": session_date,
        "classification": "PILOT" if formal_reading_available else "INSUFFICIENT_SAMPLE",
        "formal_reading_available": formal_reading_available,
        "required_session_count": FIRST_FORMAL_READING_SESSIONS,
        "observed_session_count": len(all_sessions),
        "governance": {
            "trading_read_only": True,
            "external_api_calls": 0,
            "policy_change_authorized": False,
            "automatic_ledger_admission_authorized": False,
            "same_entry_quality_estimators_reused": True,
        },
        "frozen_contract": plan["frozen_contract"],
        "plan_fingerprint": {
            "candidate_count": plan["candidate_count"],
            "candidate_ids_sha256": plan["candidate_ids_sha256"],
            "candidate_rows_sha256": plan["candidate_rows_sha256"],
        },
        "cohort": {
            "candidate_count": len(observations),
            "unique_symbol_count": len({
                (str(row["market"]), str(row["symbol"])) for row in observations
            }),
            "accepted_count": sum(row["decision"] == "accepted" for row in observations),
            "rejected_count": sum(row["decision"] == "rejected" for row in observations),
            "outcome_count": len(outcomes),
            "coverage_counts": dict(sorted(coverage_counts.items())),
            "barrier_category_counts": dict(sorted(barrier_counts.items())),
        },
        "price_sources": price_evidence,
        "daily_jsonl": {
            "name": "candidates.jsonl",
            "row_count": len(jsonl_rows),
            "sha256": jsonl_sha256,
        },
        "preregistered_metrics": metrics,
        "limitations": [
            "A candidate may have one first rejection and one later accepted row in the same session.",
            "Ambiguous same-bar and session-close censored outcomes are disclosed but not counted as decided wins or losses.",
            "bar_unavailable is coverage censorship and never a numeric market-compatibility violation.",
            "No policy interpretation is authorized before five collected sessions and table approval.",
        ],
    }
    report["ledger_candidate_lines"] = [
        ledger_candidate_line(
            runner="R2D2_SHADOW_CANDIDATE_LOG_V1",
            finding_type="daily_funnel_population",
            fact={
                "session_date": session_date.isoformat(),
                "candidate_count": len(observations),
                "unique_symbol_count": report["cohort"]["unique_symbol_count"],
                "accepted_count": report["cohort"]["accepted_count"],
                "rejected_count": report["cohort"]["rejected_count"],
                "quality_capacity_split": metrics["quality_capacity_split"],
            },
            evidence_path="cohort",
            evidence_payload=report["cohort"],
            implication=(
                "Wait for the preregistered five-session floor; this machine draft does not authorize a policy change."
                if not formal_reading_available
                else "Carry the preregistered funnel population metrics to the next six-hands table reading."
            ),
        ),
        ledger_candidate_line(
            runner="R2D2_SHADOW_CANDIDATE_LOG_V1",
            finding_type="daily_counterfactual_plus_minus_1r",
            fact={
                "session_date": session_date.isoformat(),
                "coverage_counts": report["cohort"]["coverage_counts"],
                "barrier_category_counts": report["cohort"]["barrier_category_counts"],
                "formal_reading_available": formal_reading_available,
            },
            evidence_path="preregistered_metrics",
            evidence_payload=metrics,
            implication="Outcome evidence is a non-authorizing draft measured on the signed entry-study ruler.",
        ),
    ]
    report["report_sha256"] = _report_hash(report)
    return report, outcomes, jsonl_bytes


def write_report_package(output: Path, report: Mapping[str, Any], jsonl_bytes: bytes) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        jsonl_path = output / "candidates.jsonl"
        if not jsonl_path.is_file() or jsonl_path.read_bytes() != jsonl_bytes:
            raise FileExistsError(
                f"immutable JSONL already exists with different bytes: {jsonl_path}"
            )
        write_immutable_json(output / "report.json", report)
        write_immutable_json(output / "SHA256SUMS.json", {
            "candidates.jsonl": sha256_file(jsonl_path),
            "report.json": sha256_file(output / "report.json"),
        })
        return

    staging = output.with_name(f".{output.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        staging.mkdir()
        jsonl_path = staging / "candidates.jsonl"
        with jsonl_path.open("xb") as handle:
            handle.write(jsonl_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        write_immutable_json(staging / "report.json", report)
        write_immutable_json(staging / "SHA256SUMS.json", {
            "candidates.jsonl": sha256_file(jsonl_path),
            "report.json": sha256_file(staging / "report.json"),
        })
        staging.rename(output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def run_session(
    *,
    settings: Settings,
    database: Database,
    session_date: date,
    output: Path,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    repository = R2D2Repository(database)
    experiment = repository.experiment(settings.r2d2_experiment_code)
    if experiment is None:
        raise ShadowCandidateOutcomeError(
            f"R2D2 experiment not found: {settings.r2d2_experiment_code}"
        )
    store = R2D2ShadowCandidateLog(database)
    report_path = output / "report.json"
    jsonl_path = output / "candidates.jsonl"
    if report_path.is_file() and jsonl_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("session_date") != session_date.isoformat():
            raise ShadowCandidateOutcomeError(
                "existing daily package belongs to a different session"
            )
        if report.get("report_sha256") != _report_hash(report):
            raise ShadowCandidateOutcomeError("existing daily report self-hash is invalid")
        jsonl_bytes = jsonl_path.read_bytes()
        if hashlib.sha256(jsonl_bytes).hexdigest() != report.get("daily_jsonl", {}).get("sha256"):
            raise ShadowCandidateOutcomeError("existing daily JSONL hash is invalid")
        expected_sums = {
            "candidates.jsonl": sha256_file(jsonl_path),
            "report.json": sha256_file(report_path),
        }
        sums_path = output / "SHA256SUMS.json"
        if sums_path.is_file():
            if json.loads(sums_path.read_text(encoding="utf-8")) != expected_sums:
                raise ShadowCandidateOutcomeError("existing SHA256SUMS manifest is invalid")
        else:
            write_immutable_json(sums_path, expected_sums)
        recovered_outcomes: list[dict[str, Any]] = []
        for raw_line in jsonl_bytes.splitlines():
            line = json.loads(raw_line)
            expected_line_sha = line.pop("line_sha256", None)
            if expected_line_sha != canonical_sha256(line):
                raise ShadowCandidateOutcomeError("existing daily JSONL line hash is invalid")
            payload = dict(line["outcome"])
            require_valid_observation_hash(dict(line["observation"]))
            if line.get("outcome_sha256") != canonical_sha256(payload):
                raise ShadowCandidateOutcomeError(
                    "existing daily JSONL outcome hash is invalid"
                )
            if payload.get("session_date") != session_date.isoformat():
                raise ShadowCandidateOutcomeError(
                    "existing daily JSONL contains a different session"
                )
            recovered_outcomes.append({
                "id": str(uuid4()),
                "candidate_id": payload["candidate_id"],
                "session_date": date.fromisoformat(str(payload["session_date"])),
                "coverage_classification": payload["coverage_classification"],
                "barrier_category": payload.get("barrier_category"),
                "counterfactual_r": payload.get("counterfactual_r"),
                "outcome_payload": payload,
                "outcome_sha256": line["outcome_sha256"],
                "measured_at": _aware(payload["measured_at"]),
            })
        written = store.append_outcomes(recovered_outcomes)
        store.save_report(
            experiment_id=str(experiment["id"]),
            session_date=session_date,
            generated_at=_aware(report["generated_at"]),
            candidate_count=int(report["cohort"]["candidate_count"]),
            jsonl_sha256=str(report["daily_jsonl"]["sha256"]),
            report_sha256=str(report["report_sha256"]),
            output_path=str(output),
            report=report,
        )
        return {
            "session_date": session_date.isoformat(),
            "candidate_count": report["cohort"]["candidate_count"],
            "outcomes_written": written,
            "report_sha256": report["report_sha256"],
            "jsonl_sha256": report["daily_jsonl"]["sha256"],
            "output": str(output),
            "recovered_existing_package": True,
        }
    report, outcomes, jsonl_bytes = build_report(
        settings=settings,
        store=store,
        experiment_id=str(experiment["id"]),
        session_date=session_date,
        generated_at=generated_at,
    )
    write_report_package(output, report, jsonl_bytes)
    written = store.append_outcomes(outcomes)
    store.save_report(
        experiment_id=str(experiment["id"]),
        session_date=session_date,
        generated_at=_aware(report["generated_at"]),
        candidate_count=int(report["cohort"]["candidate_count"]),
        jsonl_sha256=str(report["daily_jsonl"]["sha256"]),
        report_sha256=str(report["report_sha256"]),
        output_path=str(output),
        report=report,
    )
    return {
        "session_date": session_date.isoformat(),
        "candidate_count": report["cohort"]["candidate_count"],
        "outcomes_written": written,
        "report_sha256": report["report_sha256"],
        "jsonl_sha256": report["daily_jsonl"]["sha256"],
        "output": str(output),
    }


def session_is_closed(session_date: date, now: datetime) -> bool:
    close = datetime.combine(session_date, REGULAR_CLOSE, tzinfo=NEW_YORK)
    return now.astimezone(timezone.utc) >= close.astimezone(timezone.utc) + timedelta(minutes=30)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only counterfactual runner for R2D2_SHADOW_CANDIDATE_LOG_V1",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("plan", "run"):
        child = subparsers.add_parser(command)
        child.add_argument("--session", type=date.fromisoformat, required=True)
        if command == "run":
            child.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = get_settings()
    database = Database(settings)
    repository = R2D2Repository(database)
    experiment = repository.experiment(settings.r2d2_experiment_code)
    if experiment is None:
        raise ShadowCandidateOutcomeError(
            f"R2D2 experiment not found: {settings.r2d2_experiment_code}"
        )
    store = R2D2ShadowCandidateLog(database)
    if args.command == "plan":
        print(json.dumps(json_ready(build_plan(
            store=store,
            experiment_id=str(experiment["id"]),
            session_date=args.session,
        )), sort_keys=True, indent=2))
        return 0
    if not session_is_closed(args.session, datetime.now(timezone.utc)):
        raise ShadowCandidateOutcomeError("refusing to measure a session before its close")
    summary = run_session(
        settings=settings,
        database=database,
        session_date=args.session,
        output=args.output,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
