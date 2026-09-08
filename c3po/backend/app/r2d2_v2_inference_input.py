"""Strict, pure collector-to-inference boundary for signed E1 rev2 + E3 rev3.

No estimator, calendar discovery, clock or I/O; only pure package constants. The caller
retains the hashed collector export (including all five outcome categories).
This module only validates finalized sufficient statistics and groups the fixed
calendar into ten-session batches. Empty sessions stay in their original slots;
empty batch denominators are passed through, never imputed, merged or removed.
Validation is not certification, a calibration result, or permission to collect.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import math
import re
from typing import Any, Mapping

from .r2d2_v2_earnings_package import (
    EARNINGS_AMENDMENT_SHA, EARNINGS_CLOSED_MANIFEST_SHA, EXPORT_SCHEMA,
    INFERENCE_SCHEMA, implementation_contract_sha,
)

MANIFEST_SHA = "eabbe18057b7e5823535dd61e93c5190b33f8c7ac80b9118229b7908f974f4d0"
AMENDMENT_SHA = "3a25b9929d0c65aa97fe90b9c9cfc7dd904fedde23df884e8e42f199ae2e5ff4"
SESSION_FIELDS = ("upper_e", "lower_e", "upper_c", "lower_c", "pnl_sum_usd",
                  "pnl_count", "unobservable_e", "unobservable_c", "indeterminate_pnl")
_CATEGORIES = ("upper_first", "lower_first", "ambiguous", "time_or_event_exit", "unobservable")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z")


class InferenceInputError(ValueError):
    """Controlled reason only; no source payload or private record identifiers."""


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise InferenceInputError(reason)


def _mapping(value: object, reason: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(k, str) for k in value):
        raise InferenceInputError(reason)
    return value


def _count(value: object) -> int:
    if type(value) is not int or value < 0:
        raise InferenceInputError("NONNEGATIVE_NATIVE_INTEGER_REQUIRED")
    return value


def _money(value: object) -> int | float:
    if type(value) not in (int, float):
        raise InferenceInputError("FINITE_NATIVE_PNL_REQUIRED")
    assert isinstance(value, (int, float))
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    _require(finite, "FINITE_NATIVE_PNL_REQUIRED")
    return value


def _text(value: object, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InferenceInputError(reason)
    return value


def _hash(value: object) -> str:
    text = _text(value, "SHA256_REQUIRED")
    _require(_SHA.fullmatch(text) is not None, "SHA256_REQUIRED")
    return text


def _day(value: object) -> str:
    text = _text(value, "ISO_SESSION_DATE_REQUIRED")
    try:
        _require(date.fromisoformat(text).isoformat() == text, "ISO_SESSION_DATE_REQUIRED")
    except ValueError:
        raise InferenceInputError("ISO_SESSION_DATE_REQUIRED") from None
    return text


def _digest(value: object) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                         allow_nan=False).encode()
    except (TypeError, ValueError, OverflowError):
        raise InferenceInputError("FINITE_JSON_EXPORT_REQUIRED") from None
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class SessionStatistics:
    upper_e: int
    lower_e: int
    upper_c: int
    lower_c: int
    pnl_sum_usd: int | float
    pnl_count: int
    unobservable_e: int
    unobservable_c: int
    indeterminate_pnl: int

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


@dataclass(frozen=True)
class InferenceInput:
    epoch: str
    manifest_sha: str
    amendment_sha: str
    earnings_amendment_sha: str
    earnings_closed_manifest_sha: str
    implementation_contract_sha: str
    implementation_package_sha: str
    release_sha: str
    readiness_sha: str
    code_revision: str
    calendar_version: str
    programmed_sessions: tuple[str, ...]
    sessions_completed: int
    sessions: tuple[SessionStatistics, ...]
    session_export_sha256: tuple[str, ...]
    source_export_sha256: str

    @property
    def cohort_size(self) -> int:
        return len(self.sessions)

    def to_session_rows(self) -> list[dict[str, int | float]]:
        """The nine fields required by inference, without metadata or coercion."""
        return [row.to_dict() for row in self.sessions]

    def to_dict(self) -> dict[str, Any]:
        rows = self.to_session_rows()
        batches = []
        for offset in range(0, self.cohort_size, 10):
            # Merely sufficient-statistic sums; no p, contrast, CI, or verdict.
            totals = {field: sum(row[field] for row in rows[offset:offset + 10]) for field in SESSION_FIELDS}
            _money(totals["pnl_sum_usd"])
            batches.append({"batch_index": offset // 10 + 1,
                            "first_programmed_session_index": offset + 1,
                            "last_programmed_session_index": offset + 10,
                            "session_dates": list(self.programmed_sessions[offset:offset + 10]),
                            "statistics": totals})
        return {"schema": INFERENCE_SCHEMA, "epoch": self.epoch,
                "manifest_sha": self.manifest_sha, "amendment_sha": self.amendment_sha,
                "earnings_amendment_sha": self.earnings_amendment_sha,
                "earnings_closed_manifest_sha": self.earnings_closed_manifest_sha,
                "implementation_contract_sha": self.implementation_contract_sha,
                "implementation_package_sha": self.implementation_package_sha,
                "release_sha": self.release_sha, "readiness_sha": self.readiness_sha,
                "code_revision": self.code_revision, "calendar_version": self.calendar_version,
                "source_export_sha256": self.source_export_sha256,
                "cohort_size": self.cohort_size, "sessions_completed": self.sessions_completed,
                "programmed_sessions": list(self.programmed_sessions),
                "session_dates": list(self.programmed_sessions[:self.cohort_size]),
                "maturity_session_index": self.cohort_size + 9,
                "maturity_session": self.programmed_sessions[self.cohort_size + 8],
                "batch_size": 10, "sessions": rows, "batches": batches,
                "session_export_sha256": list(self.session_export_sha256),
                "statistical_verdict": "NOT_COMPUTED"}


def _session(row: Mapping[str, Any], day: str, index: int) -> SessionStatistics:
    _require(row.get("schema_version") == "R2D2_V2_SESSION_STATISTICS_v1", "SESSION_SCHEMA_MISMATCH")
    _require(_day(row.get("session_date")) == day, "PROGRAMMED_SESSION_MISMATCH")
    _require(_count(row.get("programmed_session_index")) == index, "PROGRAMMED_SESSION_INDEX_MISMATCH")
    _require(row.get("finalized") is True, "SESSION_NOT_FINALIZED")
    for flag in ("data_gate_unknown", "capture_coverage_unknown", "terminal_veto"):
        _require(row.get(flag) is False, "SESSION_GATE_BLOCKED_OR_MISSING")
    arms = _mapping(row.get("arms"), "ARMS_REQUIRED")
    counts = {}
    for arm in ("ELIGIBLE", "CONTROL"):
        source = _mapping(arms.get(arm), "ARM_REQUIRED")
        values = {key: _count(source.get(key)) for key in (*_CATEGORIES, "episodes", "pending")}
        _require(sum(values[key] for key in _CATEGORIES) + values["pending"] == values["episodes"],
                 "ARM_COUNT_IDENTITY_FAILED")
        _require(values["pending"] == 0, "RESEARCH_PENDING")
        _require(values["unobservable"] == 0, "DATA_GATE_BLOCKED_UNOBSERVABLE")
        counts[arm] = values
    pnl_count = _count(row.get("portfolio_episode_count"))
    indeterminate = _count(row.get("portfolio_pnl_indeterminate_count"))
    _require(indeterminate <= pnl_count <= counts["ELIGIBLE"]["episodes"], "PORTFOLIO_COUNT_IDENTITY_FAILED")
    _require(indeterminate == 0, "DATA_GATE_BLOCKED_INDETERMINATE_PNL")
    pnl = _money(row.get("portfolio_pnl_usd_sum"))
    _require(pnl_count != 0 or pnl == 0, "EMPTY_PORTFOLIO_NONZERO_PNL")
    return SessionStatistics(counts["ELIGIBLE"]["upper_first"], counts["ELIGIBLE"]["lower_first"],
                             counts["CONTROL"]["upper_first"], counts["CONTROL"]["lower_first"],
                             pnl, pnl_count, counts["ELIGIBLE"]["unobservable"],
                             counts["CONTROL"]["unobservable"], indeterminate)


def adapt_collector_export(export: Mapping[str, object]) -> InferenceInput:
    """Validate a complete hashed V2 export. A rejected export remains auditable
    at the collector; it never becomes a zero-filled inference input.

    Calendar provenance/official closes are established by the collector. Here
    their supplied 69-session sequence, maturity count and row membership must
    agree exactly; this pure boundary does not claim independent calendar proof.
    """
    source = _mapping(export, "COHORT_EXPORT_REQUIRED")
    checksum = _hash(source.get("sha256"))
    _require(_digest({k: v for k, v in source.items() if k != "sha256"}) == checksum, "EXPORT_HASH_MISMATCH")
    _require(source.get("schema") == EXPORT_SCHEMA, "COHORT_SCHEMA_MISMATCH")
    _require(source.get("manifest_sha") == source.get("signed_manifest_sha") == MANIFEST_SHA,
             "SIGNED_MANIFEST_MISMATCH")
    _require(source.get("amendment_sha") == AMENDMENT_SHA, "SIGNED_AMENDMENT_MISMATCH")
    _require(source.get("earnings_amendment_sha") == EARNINGS_AMENDMENT_SHA
             and source.get("earnings_closed_manifest_sha") == EARNINGS_CLOSED_MANIFEST_SHA,
             "SIGNED_EARNINGS_AMENDMENT_MISMATCH")
    contract_sha = implementation_contract_sha()
    _require(source.get("implementation_contract_sha") == contract_sha, "EARNINGS_CONTRACT_MISMATCH")
    # Actual installed bytes are checked by Release.verify / ShadowCollector.
    # This pure adapter preserves that commitment, and never reads local files.
    package_sha = _hash(source.get("implementation_package_sha"))
    _require(source.get("statistical_verdict") == "NOT_COMPUTED", "COLLECTOR_VERDICT_FORBIDDEN")
    for flag in ("data_gate_unknown", "terminal_veto"):
        _require(source.get(flag) is False, "COHORT_GATE_BLOCKED_OR_MISSING")
    size = _count(source.get("cohort_size"))
    _require(size in (40, 60), "COHORT_SIZE_NOT_SIGNED")
    raw_schedule = source.get("programmed_sessions")
    _require(isinstance(raw_schedule, list) and len(raw_schedule) == 69, "PROGRAMMED_CALENDAR_REQUIRED")
    assert isinstance(raw_schedule, list)
    schedule = tuple(_day(day) for day in raw_schedule)
    _require(all(a < b for a, b in zip(schedule, schedule[1:])), "PROGRAMMED_CALENDAR_NOT_STRICTLY_ORDERED")
    completed = _count(source.get("sessions_completed"))
    _require(size + 9 <= completed <= 69, "COHORT_NOT_MATURE")
    _require(_count(source.get("maturity_session_index")) == size + 9, "MATURITY_INDEX_MISMATCH")
    _require(_day(source.get("maturity_session")) == schedule[size + 8], "MATURITY_SESSION_MISMATCH")
    raw_rows = source.get("sessions")
    _require(isinstance(raw_rows, list) and len(raw_rows) == size, "COHORT_ROW_COUNT_MISMATCH")
    assert isinstance(raw_rows, list)
    rows = tuple(_session(_mapping(row, "SESSION_REQUIRED"), schedule[i], i + 1)
                 for i, row in enumerate(raw_rows))
    revision = _text(source.get("code_revision"), "CODE_REVISION_REQUIRED")
    _require(_REVISION.fullmatch(revision) is not None, "CODE_REVISION_REQUIRED")
    return InferenceInput(epoch=_text(source.get("epoch"), "EPOCH_REQUIRED"), manifest_sha=MANIFEST_SHA,
                          amendment_sha=AMENDMENT_SHA, earnings_amendment_sha=EARNINGS_AMENDMENT_SHA,
                          earnings_closed_manifest_sha=EARNINGS_CLOSED_MANIFEST_SHA,
                          implementation_contract_sha=contract_sha, implementation_package_sha=package_sha,
                          release_sha=_hash(source.get("release_sha")),
                          readiness_sha=_hash(source.get("readiness_sha")), code_revision=revision,
                          calendar_version=_text(source.get("calendar_version"), "CALENDAR_VERSION_REQUIRED"),
                          programmed_sessions=schedule, sessions_completed=completed, sessions=rows,
                          session_export_sha256=tuple(_digest(row) for row in raw_rows),
                          source_export_sha256=checksum)


def validate_cohort_prefix(first: InferenceInput, second: InferenceInput) -> None:
    """Require the same frozen 40-session prefix of the 60-session export.

    No reading is executed here: the estimator separately enforces whether a
    second reading is allowed after the first decision and prohibits a third.
    """
    _require(first.cohort_size == 40 and second.cohort_size == 60, "COHORT_PAIR_REQUIRED")
    for name in ("epoch", "manifest_sha", "amendment_sha", "earnings_amendment_sha",
                 "earnings_closed_manifest_sha", "implementation_contract_sha", "implementation_package_sha",
                 "release_sha", "readiness_sha",
                 "code_revision", "calendar_version", "programmed_sessions"):
        _require(getattr(first, name) == getattr(second, name), "COHORT_IDENTITY_MISMATCH")
    _require(first.sessions_completed <= second.sessions_completed, "MATURITY_CLOCK_REGRESSED")
    _require(first.sessions == second.sessions[:40], "COHORT_PREFIX_CHANGED")
    _require(first.session_export_sha256 == second.session_export_sha256[:40], "COHORT_PREFIX_CHANGED")
