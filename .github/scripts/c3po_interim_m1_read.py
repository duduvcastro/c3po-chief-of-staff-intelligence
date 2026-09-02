from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import get_settings
from app.database import Database
from app.r2d2_entry_quality_study import (
    CURRENT_M1_POLICY_EPOCH,
    _report_hash,
    build_report,
)


QUERY_SHA256 = os.environ.get("C3PO_EVIDENCE_QUERY_SHA256", "")
if not re.fullmatch(r"[0-9a-f]{64}", QUERY_SHA256):
    raise SystemExit("query source SHA-256 is missing or invalid")

settings = get_settings()
database = Database(settings)
with database.connection() as connection:
    if connection is None:
        raise SystemExit("production database is unavailable")
    access = connection.execute(
        """
        SELECT current_user,
               current_setting('transaction_read_only'),
               current_setting('statement_timeout'),
               current_setting('lock_timeout')
        """
    ).fetchone()
    connection.rollback()

effective_role, read_only, statement_timeout, lock_timeout = map(str, access)
if effective_role != "pg_read_all_data":
    raise SystemExit("effective database role is not the dedicated read-all role")
if read_only != "on":
    raise SystemExit("database transaction is not read-only")
if statement_timeout not in {"2min", "120s", "120000ms"}:
    raise SystemExit("database statement timeout is not the pinned 120 seconds")
if lock_timeout not in {"5s", "5000ms"}:
    raise SystemExit("database lock timeout is not the pinned 5 seconds")

generated_at = datetime.now(timezone.utc)
docs = Path("/legacy/c3po/docs")
manifest, report = build_report(
    settings=settings,
    policy_epochs_path=docs / "ENTRY_QUALITY_STUDY_V1_POLICY_EPOCHS.json",
    spec_path=docs / "ENTRY_QUALITY_STUDY_V1.md",
    attestation_path=docs / "ENTRY_QUALITY_STUDY_V1_RUNNER_ATTESTATION_1.md",
    attestation_two_path=docs / "ENTRY_QUALITY_STUDY_V1_RUNNER_ATTESTATION_2.md",
    generated_at=generated_at,
    dry_run=True,
)
if report["report_sha256"] != _report_hash(report, "report_sha256"):
    raise SystemExit("entry-study report self-hash mismatch")

m1 = report["kill_criterion_m1_current_epoch"]
summary = m1.get("summary") or {}
barrier = summary.get("barrier") or {}
epoch = report["policy_epoch_results"].get(CURRENT_M1_POLICY_EPOCH) or {}
h3 = (epoch.get("hypotheses") or {}).get("H3") or {}

payload = {
    "schema": "C3PO_ENTRY_QUALITY_M1_INTERIM_REDUCED-v1",
    "generated_at": generated_at.isoformat(),
    "retention": {
        "days": 30,
        "expires_at": (generated_at + timedelta(days=30)).isoformat(),
        "enforcement": "github_private_artifact_retention",
        "expiry_action": "automatic_expungement_and_gate_item_reopen",
    },
    "query": {
        "path": ".github/scripts/c3po_interim_m1_read.py",
        "sha256": QUERY_SHA256,
    },
    "database_access": {
        "effective_role": effective_role,
        "transaction_read_only": True,
        "statement_timeout": statement_timeout,
        "lock_timeout": lock_timeout,
        "ddl_or_dml_executed": False,
    },
    "source_evidence": {
        "manifest_sha256": manifest["manifest_sha256"],
        "report_sha256": report["report_sha256"],
    },
    "dry_run": report["dry_run"],
    "analysis_interpretable": report["analysis_interpretable"],
    "classification": report["classification"],
    "entry_gate_passed": report["entry_consistency_gate"]["passed"],
    "cohort": report["cohort"],
    "m1": {
        "policy_epoch": m1.get("policy_epoch"),
        "available": m1.get("available"),
        "classification": m1.get("classification"),
        "cross_epoch_pooling": m1.get("cross_epoch_pooling"),
        "population": {
            "entry_count": summary.get("entry_count"),
            "session_count": summary.get("session_count"),
        },
        "barrier": {
            "categories": barrier.get("categories"),
            "resolved_count": barrier.get("resolved_count"),
            "p_hat": barrier.get("p_hat"),
            "p_hat_conservative": barrier.get("p_hat_conservative"),
            "bootstrap_ci95": barrier.get("bootstrap_ci95"),
            "p_hat_ucb_98_75": barrier.get("p_hat_ucb_98_75"),
            "p_hat_cons_ucb_98_75": barrier.get("p_hat_cons_ucb_98_75"),
            "verdict_against_50_percent": barrier.get(
                "verdict_against_50_percent"
            ),
            "censorship_percent": barrier.get("censorship_percent"),
            "censorship_status": barrier.get("censorship_status"),
        },
    },
    "h3": {
        "status": h3.get("status"),
        "observed_session_count": h3.get("observed_session_count"),
        "required_session_count": h3.get("required_session_count"),
        "required_decided_entries_per_cell": h3.get(
            "required_decided_entries_per_cell"
        ),
        "insufficient_cells": h3.get("insufficient_cells", []),
        "cells": h3.get("cells", {}),
    },
    "partial_verdict": {
        "status": "PILOT_ONLY" if report["analysis_interpretable"] else "BLOCKED",
        "m1": barrier.get("verdict_against_50_percent"),
        "h3": h3.get("status"),
        "strategy_change_authorized": False,
        "canonical_admission_automatic": False,
    },
}
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
