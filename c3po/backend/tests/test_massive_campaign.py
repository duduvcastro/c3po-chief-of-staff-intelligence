from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json

import pytest

from app.day_d_replay.massive_campaign import (
    AUTHORIZED_SCOPE_BYTES,
    BASE_AUTHORIZED_SCOPE_BYTES,
    CAMPAIGN_PAUSE_BYTES,
    CampaignGuardError,
    EXTENSION_MINUTE_SESSIONS,
    EXTENSION_SCOPE_BYTES,
    MassiveCampaignGuard,
    QUALIFICATION_SESSIONS,
)


@dataclass
class Artifact:
    bucket: str = "flatfiles"
    object_key: str = "us_stocks_sip/trades_v1/2026/08/2026-08-21.csv.gz"
    dataset: str = "trades"
    session_date: str = "2026-08-21"
    content_length: int = 100
    sha256: str = "a" * 64
    remote_etag: str | None = "etag"


def _guard(
    tmp_path,
    *artifacts: Artifact,
    pause_bytes: int = CAMPAIGN_PAUSE_BYTES,
) -> MassiveCampaignGuard:
    sessions: dict[str, dict[str, object]] = {}
    for artifact in artifacts:
        row = sessions.setdefault(artifact.session_date, {"artifacts": {}})
        row["artifacts"][artifact.dataset] = {  # type: ignore[index]
            "content_length": artifact.content_length,
            "remote_etag": artifact.remote_etag,
            "object_key": artifact.object_key,
        }
    report = tmp_path / "scope.json"
    report.write_text(json.dumps({
        "schema_version": "DAY-D-MASSIVE-T0-PLAN-SWEEP-v1",
        "downloaded": False,
        "source_csv_files": 0,
        "sessions": [
            {"session_date": session_date, **row}
            for session_date, row in sorted(sessions.items())
        ],
    }), encoding="utf-8")
    return MassiveCampaignGuard(
        root=tmp_path,
        download_authorized=True,
        canonical_scope_report=report,
        canonical_scope_report_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
        authorized_scope_bytes=sum(item.content_length for item in artifacts),
        campaign_pause_bytes=pause_bytes,
        include_extension_scope=False,
        require_complete_frozen_scope=False,
    )


def test_campaign_scope_uses_fable_frozen_byte_budget() -> None:
    assert BASE_AUTHORIZED_SCOPE_BYTES == 131_006_214_944
    assert EXTENSION_SCOPE_BYTES == 214_983_688
    assert AUTHORIZED_SCOPE_BYTES == 131_221_198_632
    assert CAMPAIGN_PAUSE_BYTES == 137_782_258_564
    assert EXTENSION_MINUTE_SESSIONS == {
        date(2026, 8, 24),
        date(2026, 8, 25),
        date(2026, 8, 26),
        date(2026, 8, 27),
        date(2026, 8, 28),
        date(2026, 8, 31),
        date(2026, 9, 1),
        date(2026, 9, 2),
    }
    assert QUALIFICATION_SESSIONS == {
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
    }


def test_campaign_scope_allows_only_five_year_minutes_and_qualification_ticks(tmp_path) -> None:
    guard = MassiveCampaignGuard(root=tmp_path, download_authorized=True)

    guard.assert_scope(dataset="minute_aggregates", session_date=date(2021, 8, 23))
    guard.assert_scope(dataset="minute_aggregates", session_date=date(2026, 8, 21))
    guard.assert_scope(dataset="minute_aggregates", session_date=date(2026, 9, 2))
    guard.assert_scope(dataset="trades", session_date=date(2026, 8, 21))
    guard.assert_scope(dataset="quotes", session_date=date(2024, 12, 24))

    with pytest.raises(CampaignGuardError, match="outside"):
        guard.assert_scope(dataset="trades", session_date=date(2026, 8, 18))
    with pytest.raises(CampaignGuardError, match="outside"):
        guard.assert_scope(dataset="day_aggregates", session_date=date(2026, 8, 21))
    with pytest.raises(CampaignGuardError, match="outside"):
        guard.assert_scope(dataset="minute_aggregates", session_date=date(2021, 8, 22))
    with pytest.raises(CampaignGuardError, match="outside"):
        guard.assert_scope(dataset="minute_aggregates", session_date=date(2026, 9, 3))


def test_campaign_records_verified_bytes_once_in_immutable_event(tmp_path) -> None:
    artifact = Artifact()
    guard = _guard(tmp_path, artifact)
    observed_at = datetime(2026, 8, 23, tzinfo=timezone.utc)

    event_path = guard.record_verified(artifact, verified_at=observed_at)
    repeated_path = guard.record_verified(artifact, verified_at=observed_at)

    assert repeated_path == event_path
    assert guard.verified_bytes() == 100
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    assert payload["verified_bytes"] == 100
    assert payload["sha256"] == "a" * 64


def test_campaign_rejects_conflicting_event_and_projected_overage(tmp_path) -> None:
    artifact = Artifact()
    next_artifact = Artifact(
        object_key="us_stocks_sip/quotes_v1/2026/08/2026-08-21.csv.gz",
        dataset="quotes",
    )
    guard = _guard(tmp_path, artifact, next_artifact, pause_bytes=150)
    guard.record_verified(artifact, verified_at=datetime.now(timezone.utc))

    conflicting = Artifact(sha256="b" * 64)
    with pytest.raises(CampaignGuardError, match="conflicts"):
        guard.record_verified(conflicting, verified_at=datetime.now(timezone.utc))

    with pytest.raises(CampaignGuardError, match="pause guard"):
        guard.assert_projected_bytes((next_artifact,))


def test_campaign_rejects_artifact_not_frozen_in_campaign_scope(tmp_path) -> None:
    artifact = Artifact()
    guard = _guard(tmp_path, artifact)
    outside = Artifact(
        object_key="us_stocks_sip/quotes_v1/2026/08/2026-08-21.csv.gz",
        dataset="quotes",
    )

    with pytest.raises(CampaignGuardError, match="absent from the frozen campaign"):
        guard.assert_projected_bytes((outside,))


def test_campaign_rejects_modified_t0_report_and_wrong_bucket(tmp_path) -> None:
    artifact = Artifact()
    guard = _guard(tmp_path, artifact)
    guard.canonical_scope_report.write_text("{}", encoding="utf-8")

    with pytest.raises(CampaignGuardError, match="checksum mismatch"):
        guard.assert_projected_bytes((artifact,))

    wrong_bucket = Artifact(bucket="another-bucket")
    guard = _guard(tmp_path, wrong_bucket)
    with pytest.raises(CampaignGuardError, match="bucket differs"):
        guard.assert_projected_bytes((wrong_bucket,))


def test_campaign_keeps_old_verified_event_valid_after_budget_extension(tmp_path) -> None:
    artifact = Artifact()
    original = _guard(tmp_path, artifact)
    event_path = original.record_verified(
        artifact,
        verified_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
    )
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    assert payload["authorized_scope_bytes"] == artifact.content_length

    extended = _guard(
        tmp_path,
        artifact,
        pause_bytes=artifact.content_length + EXTENSION_SCOPE_BYTES,
    )
    extended.authorized_scope_bytes = artifact.content_length + EXTENSION_SCOPE_BYTES
    assert extended.verified_bytes() == artifact.content_length


def test_campaign_admits_only_metadata_from_the_frozen_minute_extension(tmp_path) -> None:
    base_artifact = Artifact()
    base = _guard(tmp_path, base_artifact)
    guard = MassiveCampaignGuard(
        root=tmp_path,
        download_authorized=True,
        canonical_scope_report=base.canonical_scope_report,
        canonical_scope_report_sha256=base.canonical_scope_report_sha256,
        authorized_scope_bytes=base_artifact.content_length + EXTENSION_SCOPE_BYTES,
        campaign_pause_bytes=base_artifact.content_length + EXTENSION_SCOPE_BYTES,
        include_extension_scope=True,
        require_complete_frozen_scope=False,
    )
    frozen = Artifact(
        object_key="us_stocks_sip/minute_aggs_v1/2026/09/2026-09-02.csv.gz",
        dataset="minute_aggregates",
        session_date="2026-09-02",
        content_length=27_003_693,
        remote_etag="45355619d1b4a6baa4a8c06ca25adf22",
    )

    guard.assert_projected_bytes((frozen,))

    changed = Artifact(
        object_key=frozen.object_key,
        dataset=frozen.dataset,
        session_date=frozen.session_date,
        content_length=frozen.content_length + 1,
        remote_etag=frozen.remote_etag,
    )
    with pytest.raises(CampaignGuardError, match="metadata differs"):
        guard.assert_projected_bytes((changed,))

    extension_payload = json.loads(
        guard.extension_scope_report.read_text(encoding="utf-8")
    )
    extension_payload["sessions"][0]["artifacts"]["trades"] = {
        "object_key": "us_stocks_sip/trades_v1/2026/08/2026-08-24.csv.gz",
        "content_length": 1,
        "remote_etag": "unexpected",
    }
    tampered_extension = tmp_path / "extension-with-trades.json"
    tampered_extension.write_text(json.dumps(extension_payload), encoding="utf-8")
    rejecting_guard = MassiveCampaignGuard(
        root=tmp_path,
        download_authorized=True,
        canonical_scope_report=base.canonical_scope_report,
        canonical_scope_report_sha256=base.canonical_scope_report_sha256,
        extension_scope_report=tampered_extension,
        extension_scope_report_sha256=hashlib.sha256(
            tampered_extension.read_bytes()
        ).hexdigest(),
        authorized_scope_bytes=base_artifact.content_length + EXTENSION_SCOPE_BYTES,
        campaign_pause_bytes=base_artifact.content_length + EXTENSION_SCOPE_BYTES,
        include_extension_scope=True,
        require_complete_frozen_scope=False,
    )
    with pytest.raises(CampaignGuardError, match="unauthorized dataset"):
        rejecting_guard.assert_projected_bytes((frozen,))
