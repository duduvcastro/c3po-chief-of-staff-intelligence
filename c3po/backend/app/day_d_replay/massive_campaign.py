from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4


class CampaignGuardError(RuntimeError):
    pass


MINUTE_AGGREGATE_START = date(2021, 8, 23)
MINUTE_AGGREGATE_END = date(2026, 8, 21)
QUALIFICATION_SESSIONS = frozenset({
    date(2022, 6, 13),
    date(2024, 8, 5),
    date(2024, 9, 18),
    date(2024, 12, 24),
    date(2025, 3, 21),
    date(2025, 6, 20),
    date(2025, 6, 27),
    date(2025, 9, 19),
    date(2025, 11, 28),
    date(2026, 8, 19),
    date(2026, 8, 20),
    date(2026, 8, 21),
})

# Derived byte-for-byte from the frozen T0 sweep report. This scope contains
# all five-year minute aggregates plus trades and quotes for the 12 frozen
# qualification sessions. The 252-session replay window is deliberately absent.
AUTHORIZED_SCOPE_BYTES = 131_006_214_944
CAMPAIGN_PAUSE_BYTES = 137_556_525_692
CANONICAL_SCOPE_REPORT_RELATIVE_PATH = Path(
    "provider=massive/plans/t0-plan-sweep-20260823T021819.718086Z.json"
)
CANONICAL_SCOPE_REPORT_SHA256 = (
    "3b68d8f70197cd6257fe90e9d8e8360cfc48df123cd4c255c4acde97d9c0ceb2"
)


@dataclass(frozen=True, slots=True)
class CampaignArtifact:
    bucket: str
    object_key: str
    dataset: str
    session_date: str
    verified_bytes: int
    sha256: str
    verified_at: str


class MassiveCampaignGuard:
    """Executable first-byte scope and append-only verified-byte accounting."""

    schema_version = "DAY-D-MASSIVE-CAMPAIGN-EVENT-v1"

    def __init__(
        self,
        *,
        root: Path,
        download_authorized: bool,
        canonical_scope_report: Path | None = None,
        canonical_scope_report_sha256: str = CANONICAL_SCOPE_REPORT_SHA256,
        authorized_scope_bytes: int = AUTHORIZED_SCOPE_BYTES,
        campaign_pause_bytes: int = CAMPAIGN_PAUSE_BYTES,
        require_complete_frozen_scope: bool = True,
    ) -> None:
        self.root = root
        self.download_authorized = download_authorized
        self.canonical_scope_report = (
            canonical_scope_report
            if canonical_scope_report is not None
            else root / CANONICAL_SCOPE_REPORT_RELATIVE_PATH
        )
        self.canonical_scope_report_sha256 = canonical_scope_report_sha256
        self.authorized_scope_bytes = authorized_scope_bytes
        self.campaign_pause_bytes = campaign_pause_bytes
        self.require_complete_frozen_scope = require_complete_frozen_scope
        self.events_root = root / "provider=massive" / "campaign" / "verified-events"
        self._frozen_scope: dict[tuple[str, str], dict[str, Any]] | None = None

    def assert_download_authorized(self) -> None:
        if not self.download_authorized:
            raise CampaignGuardError(
                "historical download remains disabled pending reviewed first-byte authorization"
            )

    def assert_scope(self, *, dataset: str, session_date: date) -> None:
        allowed = (
            dataset == "minute_aggregates"
            and MINUTE_AGGREGATE_START <= session_date <= MINUTE_AGGREGATE_END
        ) or (
            dataset in {"trades", "quotes"}
            and session_date in QUALIFICATION_SESSIONS
        )
        if not allowed:
            raise CampaignGuardError(
                f"artifact is outside the authorized first-byte scope: {dataset} {session_date}"
            )

    def assert_projected_bytes(self, artifacts: Iterable[Any]) -> None:
        current = self.verified_bytes()
        additional = 0
        for artifact in artifacts:
            session_date = date.fromisoformat(str(artifact.session_date))
            self.assert_scope(dataset=str(artifact.dataset), session_date=session_date)
            self._assert_frozen_artifact(artifact)
            if not self._event_path(str(artifact.bucket), str(artifact.object_key)).exists():
                additional += int(artifact.content_length)
        projected = current + additional
        if projected > self.campaign_pause_bytes:
            raise CampaignGuardError(
                "campaign pause guard blocked download: "
                f"verified={current}, requested={additional}, pause={self.campaign_pause_bytes}"
            )

    def record_verified(self, artifact: Any, *, verified_at: datetime) -> Path:
        if verified_at.tzinfo is None or verified_at.utcoffset() is None:
            raise ValueError("verified_at must be timezone-aware")
        self.assert_scope(
            dataset=str(artifact.dataset),
            session_date=date.fromisoformat(str(artifact.session_date)),
        )
        self._assert_frozen_artifact(artifact)
        if int(artifact.content_length) <= 0:
            raise CampaignGuardError("verified artifact bytes must be positive")
        sha256 = str(artifact.sha256)
        if len(sha256) != 64 or any(
            character not in "0123456789abcdef" for character in sha256
        ):
            raise CampaignGuardError("verified artifact SHA-256 is invalid")
        event = CampaignArtifact(
            bucket=str(artifact.bucket),
            object_key=str(artifact.object_key),
            dataset=str(artifact.dataset),
            session_date=str(artifact.session_date),
            verified_bytes=int(artifact.content_length),
            sha256=sha256,
            verified_at=verified_at.astimezone(timezone.utc).isoformat(),
        )
        target = self._event_path(event.bucket, event.object_key)
        if target.exists():
            existing = json.loads(target.read_text(encoding="utf-8"))
            comparable = {key: existing.get(key) for key in asdict(event) if key != "verified_at"}
            expected = {key: value for key, value in asdict(event).items() if key != "verified_at"}
            if comparable != expected:
                raise CampaignGuardError(
                    f"verified campaign event conflicts with immutable artifact: {event.object_key}"
                )
            return target
        if self.verified_bytes() + event.verified_bytes > self.campaign_pause_bytes:
            raise CampaignGuardError("campaign pause threshold crossed after artifact verification")
        self._atomic_immutable_json(target, {
            "schema_version": self.schema_version,
            **asdict(event),
            "authorized_scope_bytes": self.authorized_scope_bytes,
            "pause_bytes": self.campaign_pause_bytes,
        })
        return target

    def verified_bytes(self) -> int:
        total = 0
        if not self.events_root.exists():
            return total
        for path in self.events_root.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != self.schema_version:
                raise CampaignGuardError(f"unknown campaign event schema: {path}")
            total += int(payload["verified_bytes"])
        if total > self.campaign_pause_bytes:
            raise CampaignGuardError("verified campaign bytes exceed the frozen pause threshold")
        return total

    def _assert_frozen_artifact(self, artifact: Any) -> None:
        if str(artifact.bucket) != "flatfiles":
            raise CampaignGuardError(
                "artifact bucket differs from the frozen Massive source"
            )
        frozen = self._load_frozen_scope().get(
            (str(artifact.dataset), str(artifact.session_date))
        )
        if frozen is None:
            raise CampaignGuardError(
                "artifact is absent from the immutable T0 scope report: "
                f"{artifact.dataset} {artifact.session_date}"
            )
        observed = {
            "object_key": str(artifact.object_key),
            "content_length": int(artifact.content_length),
            "remote_etag": getattr(artifact, "remote_etag", None),
        }
        if observed != frozen:
            raise CampaignGuardError(
                "artifact metadata differs from the immutable T0 scope report: "
                f"{artifact.dataset} {artifact.session_date}"
            )

    def _load_frozen_scope(self) -> dict[tuple[str, str], dict[str, Any]]:
        if self._frozen_scope is not None:
            return self._frozen_scope
        path = self.canonical_scope_report
        if not path.exists():
            raise CampaignGuardError(f"canonical T0 scope report is missing: {path}")
        observed_sha = self._sha256_file(path)
        if observed_sha != self.canonical_scope_report_sha256:
            raise CampaignGuardError("canonical T0 scope report checksum mismatch")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            payload.get("schema_version") != "DAY-D-MASSIVE-T0-PLAN-SWEEP-v1"
            or payload.get("downloaded") is not False
            or int(payload.get("source_csv_files", -1)) != 0
        ):
            raise CampaignGuardError("canonical T0 scope report metadata is invalid")
        sessions = payload.get("sessions")
        if not isinstance(sessions, list):
            raise CampaignGuardError("canonical T0 scope report has no session rows")
        scope: dict[tuple[str, str], dict[str, Any]] = {}
        for row in sessions:
            if not isinstance(row, dict):
                raise CampaignGuardError("canonical T0 scope report has a malformed session")
            session_date = str(row.get("session_date") or "")
            artifacts = row.get("artifacts")
            if not isinstance(artifacts, dict):
                raise CampaignGuardError("canonical T0 session has no artifacts")
            for dataset, metadata in artifacts.items():
                if not isinstance(metadata, dict):
                    raise CampaignGuardError("canonical T0 artifact metadata is malformed")
                permitted = dataset == "minute_aggregates" or (
                    dataset in {"trades", "quotes"}
                    and date.fromisoformat(session_date) in QUALIFICATION_SESSIONS
                )
                if not permitted:
                    continue
                key = (str(dataset), session_date)
                if key in scope:
                    raise CampaignGuardError("canonical T0 scope contains a duplicate artifact")
                scope[key] = {
                    "object_key": str(metadata.get("object_key") or ""),
                    "content_length": int(metadata.get("content_length") or 0),
                    "remote_etag": metadata.get("remote_etag"),
                }
        measured_bytes = sum(item["content_length"] for item in scope.values())
        if self.require_complete_frozen_scope:
            minute_count = sum(1 for dataset, _ in scope if dataset == "minute_aggregates")
            tick_count = sum(1 for dataset, _ in scope if dataset in {"trades", "quotes"})
            if minute_count != 1_255 or tick_count != 24:
                raise CampaignGuardError("canonical T0 scope has unexpected artifact coverage")
        if measured_bytes != self.authorized_scope_bytes:
            raise CampaignGuardError(
                "canonical T0 scope byte total differs from the frozen authorization"
            )
        self._frozen_scope = scope
        return scope

    def _event_path(self, bucket: str, object_key: str) -> Path:
        identity = hashlib.sha256(f"{bucket}\n{object_key}".encode()).hexdigest()
        return self.events_root / f"{identity}.json"

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _atomic_immutable_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.part")
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise CampaignGuardError(f"campaign event already exists: {path}") from exc
            temporary.unlink()
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
