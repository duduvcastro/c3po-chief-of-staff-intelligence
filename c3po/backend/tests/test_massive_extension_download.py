from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.day_d_replay import massive_extension_download as download_module
from app.day_d_replay import massive_extension_write_preflight as preflight_module
from app.day_d_replay.massive_campaign import EXTENSION_SCOPE_REPORT_SHA256
from app.day_d_replay.massive_extension_download import (
    EXTENSION_SESSIONS,
    MassiveExtensionDownloadError,
    build_extension_manifest,
)
from app.day_d_replay.massive_extension_write_preflight import (
    FROZEN_PLAN_SHA256,
    MassiveExtensionWritePreflightError,
    STATIC_CROSS_DIRECTORY_PAIR_COUNT,
    STATIC_WRITE_TARGET_COUNT,
    build_write_manifest,
    run_write_preflight,
)


def _session_manifests(root: Path) -> list[Path]:
    manifests: list[Path] = []
    for index, session_date in enumerate(EXTENSION_SESSIONS):
        payload = bytes([index + 1])
        source_path = (
            root
            / "provider=massive"
            / "dataset=minute_aggregates"
            / f"session_date={session_date.isoformat()}"
            / "source.csv.gz"
        )
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(payload)
        manifest_path = root / "manifests" / f"{session_date.isoformat()}.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({
            "schema_version": "DAY-D-MASSIVE-ARCHIVE-v1",
            "session_date": session_date.isoformat(),
            "artifacts": [{
                "dataset": "minute_aggregates",
                "session_date": session_date.isoformat(),
                "bucket": "flatfiles",
                "object_key": (
                    "us_stocks_sip/minute_aggs_v1/"
                    f"{session_date:%Y/%m}/{session_date.isoformat()}.csv.gz"
                ),
                "content_length": len(payload),
                "remote_etag": f"etag-{index}",
                "local_path": str(source_path),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "reused_existing_file": False,
            }],
        }), encoding="utf-8")
        manifests.append(manifest_path)
    return manifests


def test_extension_manifest_rehashes_all_eight_sources_and_self_hashes(tmp_path: Path) -> None:
    generated_at = datetime(2026, 9, 3, 6, tzinfo=timezone.utc)
    write_preflight = {
        "status": "ok",
        "frozen_plan_sha256": EXTENSION_SCOPE_REPORT_SHA256,
        "checked_directories": [f"sink-{index}" for index in range(22)],
        "checked_directory_count": 22,
        "checked_targets": [
            {"kind": f"sink-{index}"} for index in range(STATIC_WRITE_TARGET_COUNT)
        ],
        "checked_target_count": STATIC_WRITE_TARGET_COUNT,
        "frozen_artifacts": [{} for _ in EXTENSION_SESSIONS],
        "existing_orphan_parts": [],
        "cross_directory_checked": [
            f"pair-{index}" for index in range(STATIC_CROSS_DIRECTORY_PAIR_COUNT)
        ],
        "cross_directory_probe_count": STATIC_CROSS_DIRECTORY_PAIR_COUNT,
        "network_calls_before_preflight": 0,
        "locked_preflight_recheck_count": len(EXTENSION_SESSIONS),
    }
    manifest = build_extension_manifest(
        root=tmp_path,
        session_manifests=_session_manifests(tmp_path),
        generated_at=generated_at,
        head_revision="a" * 40,
        workflow_run_id=123,
        workflow_run_attempt=1,
        expected_total_bytes=8,
        write_preflight=write_preflight,
    )

    assert manifest["session_count"] == 8
    assert manifest["downloaded_bytes"] == 8
    assert manifest["raw_files_returned_to_ci"] is False
    assert manifest["plan_report_sha256"] == EXTENSION_SCOPE_REPORT_SHA256
    assert manifest["write_preflight"] == write_preflight
    assert manifest["evidence_expires_at"] == "2026-10-03T06:00:00+00:00"
    expected_self_hash = manifest.pop("manifest_sha256")
    canonical = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == expected_self_hash


def test_extension_manifest_rejects_source_tampering(tmp_path: Path) -> None:
    manifests = _session_manifests(tmp_path)
    first = json.loads(manifests[0].read_text(encoding="utf-8"))
    Path(first["artifacts"][0]["local_path"]).write_bytes(b"changed")

    with pytest.raises(MassiveExtensionDownloadError, match="artifact is invalid"):
        build_extension_manifest(
            root=tmp_path,
            session_manifests=manifests,
            generated_at=datetime.now(timezone.utc),
            head_revision="a" * 40,
            workflow_run_id=123,
            workflow_run_attempt=1,
            expected_total_bytes=8,
        )


def _preflight_output(root: Path) -> Path:
    return (
        root
        / "evidence"
        / "r2d2-massive-minute-extension-download-v1"
        / "run-123-attempt-1"
        / "extension-download-manifest.json"
    )


def _create_preflight_directories(root: Path, output: Path) -> dict[str, Any]:
    manifest = build_write_manifest(
        root=root,
        output=output,
        include_existing_orphans=False,
    )
    for relative in manifest["write_directories"]:
        (root / str(relative)).mkdir(parents=True, exist_ok=True)
    return manifest


def test_write_preflight_manifest_exactly_covers_every_frozen_sink(tmp_path: Path) -> None:
    root = tmp_path / "day-d-data"
    root.mkdir()
    manifest = build_write_manifest(root=root, output=_preflight_output(root))

    assert manifest["frozen_plan_sha256"] == FROZEN_PLAN_SHA256
    assert [row["session_date"] for row in manifest["sessions"]] == [
        value.isoformat() for value in EXTENSION_SESSIONS
    ]
    assert len(manifest["sessions"]) == 8
    assert len(manifest["privileged_write_directories"]) == 20
    assert len(manifest["cross_directory_pairs"]) == STATIC_CROSS_DIRECTORY_PAIR_COUNT
    assert {
        operation: sum(
            pair["operation"] == operation
            for pair in manifest["cross_directory_pairs"]
        )
        for operation in {pair["operation"] for pair in manifest["cross_directory_pairs"]}
    } == {"remote-changed": 8, "remote-rehead-failed": 8}
    assert manifest["orphan_hardlink_pairs"] == []
    assert len(manifest["write_directories"]) == 22
    assert len(manifest["write_targets"]) == STATIC_WRITE_TARGET_COUNT
    assert manifest["provision_parent_directories"] == [
        "provider=massive",
        "provider=massive/campaign",
        "provider=massive/dataset=minute_aggregates",
        "provider=massive/manifests",
        "provider=massive/quarantine",
    ]
    assert "trades" not in json.dumps(manifest)
    assert "quotes" not in json.dumps(manifest)
    assert {
        str(Path(target["relative_path"]).parent)
        for target in manifest["write_targets"]
    } <= set(manifest["write_directories"])
    assert {target["validation"] for target in manifest["write_targets"]} == {
        "directory_atomic_pattern",
        "exact_absent_or_immutable",
        "exact_absent_then_directory_atomic",
        "exact_lock",
    }

    for row in manifest["sessions"]:
        session_date = row["session_date"]
        expected_key = (
            "us_stocks_sip/minute_aggs_v1/"
            f"{session_date[:4]}/{session_date[5:7]}/{session_date}.csv.gz"
        )
        expected_event = hashlib.sha256(
            f"flatfiles\n{expected_key}".encode("utf-8")
        ).hexdigest()
        assert row["object_key"] == expected_key
        assert row["source_relative_path"].endswith(
            f"session_date={session_date}/source.csv.gz"
        )
        assert row["metadata_relative_path"].endswith(
            f"session_date={session_date}/source.csv.gz.metadata.json"
        )
        assert row["manifest_directory_relative_path"].endswith(
            f"manifests/session_date={session_date}"
        )
        assert row["campaign_event_relative_path"].endswith(
            f"verified-events/{expected_event}.json"
        )

    expected_self_hash = manifest.pop("manifest_sha256")
    canonical = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == expected_self_hash


def test_write_preflight_probes_every_directory_and_cleans_up(tmp_path: Path) -> None:
    root = tmp_path / "day-d-data"
    root.mkdir()
    output = _preflight_output(root)
    manifest = _create_preflight_directories(root, output)

    report = run_write_preflight(
        root=root,
        output=output,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )

    assert report["status"] == "ok"
    assert report["checked_directories"] == manifest["write_directories"]
    assert report["checked_directory_count"] == 22
    assert report["checked_targets"] == manifest["write_targets"]
    assert report["checked_target_count"] == STATIC_WRITE_TARGET_COUNT
    assert len(report["frozen_artifacts"]) == 8
    frozen_plan = download_module._frozen_local_plan(
        root=root,
        write_preflight=report,
    )
    assert [item.session_date for item in frozen_plan] == [
        value.isoformat() for value in EXTENSION_SESSIONS
    ]
    assert sum(item.content_length for item in frozen_plan) == 214_983_688
    assert report["existing_orphan_parts"] == []
    assert report["cross_directory_probe_count"] == 16
    assert len(report["cross_directory_checked"]) == 16
    assert all(
        label.startswith(("remote-changed:", "remote-rehead-failed:"))
        for label in report["cross_directory_checked"]
    )
    assert report["network_calls_before_preflight"] == 0
    assert list(root.rglob(".massive-extension-write-probe-*")) == []
    assert list(root.rglob(".massive-extension-cross-probe-*")) == []


def test_write_preflight_aggregates_all_failures_and_visits_every_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "day-d-data"
    root.mkdir()
    output = _preflight_output(root)
    manifest = _create_preflight_directories(root, output)
    failed = {
        manifest["write_directories"][1],
        manifest["write_directories"][7],
        manifest["write_directories"][-1],
    }
    visited: list[str] = []

    monkeypatch.setattr(preflight_module.os, "geteuid", lambda: 1234)
    monkeypatch.setattr(preflight_module.os, "getegid", lambda: 1234)

    def fake_probe(path: Path) -> str | None:
        relative = str(path.relative_to(root))
        visited.append(relative)
        if relative in failed:
            return "PermissionError(errno=13): denied"
        return None

    monkeypatch.setattr(preflight_module, "_probe_directory", fake_probe)

    with pytest.raises(MassiveExtensionWritePreflightError) as exc_info:
        run_write_preflight(
            root=root,
            output=output,
            expected_uid=1234,
            expected_gid=1234,
        )

    assert visited == manifest["write_directories"]
    for relative in failed:
        assert str(exc_info.value).count(relative) == 1
    assert str(exc_info.value).splitlines()[1:] == sorted(
        str(exc_info.value).splitlines()[1:]
    )


def test_write_preflight_aggregates_symlink_and_file_collisions(tmp_path: Path) -> None:
    root = tmp_path / "day-d-data"
    root.mkdir()
    output = _preflight_output(root)
    manifest = _create_preflight_directories(root, output)

    file_collision = root / manifest["write_directories"][3]
    file_collision.rmdir()
    file_collision.write_text("not-a-directory", encoding="utf-8")
    symlink_collision = root / manifest["write_directories"][9]
    symlink_collision.rmdir()
    symlink_collision.symlink_to(root / "evidence", target_is_directory=True)

    with pytest.raises(MassiveExtensionWritePreflightError) as exc_info:
        run_write_preflight(
            root=root,
            output=output,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
        )

    assert manifest["write_directories"][3] in str(exc_info.value)
    assert manifest["write_directories"][9] in str(exc_info.value)
    assert list(root.rglob(".massive-extension-write-probe-*")) == []


def test_write_preflight_rejects_all_exact_target_collisions_before_network(
    tmp_path: Path,
) -> None:
    root = tmp_path / "day-d-data"
    root.mkdir()
    output = _preflight_output(root)
    manifest = _create_preflight_directories(root, output)
    first = manifest["sessions"][0]

    source = root / str(first["source_relative_path"])
    source.mkdir()
    metadata = root / str(first["metadata_relative_path"])
    metadata.symlink_to(root / "evidence" / "missing-metadata.json")
    event = root / str(first["campaign_event_relative_path"])
    event.mkdir()
    lock = root / "evidence" / ".massive-download.lock"
    lock.mkdir()
    output.write_text("must-not-overwrite", encoding="utf-8")

    with pytest.raises(MassiveExtensionWritePreflightError) as exc_info:
        run_write_preflight(
            root=root,
            output=output,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
        )

    observed = str(exc_info.value)
    for target in (source, metadata, event, lock, output):
        assert str(target.relative_to(root)) in observed
    assert observed.splitlines()[1:] == sorted(observed.splitlines()[1:])


def test_write_preflight_enumerates_and_cross_links_every_existing_orphan(
    tmp_path: Path,
) -> None:
    root = tmp_path / "day-d-data"
    root.mkdir()
    output = _preflight_output(root)
    _create_preflight_directories(root, output)
    first_orphan = root / "provider=massive" / "legacy-a" / ".source-a.part"
    second_orphan = root / "provider=massive" / "legacy-b" / ".source-b.part"
    for orphan in (first_orphan, second_orphan):
        orphan.parent.mkdir(parents=True)
        orphan.write_bytes(b"partial")
    ignored_quarantine_part = (
        root
        / "provider=massive"
        / "quarantine"
        / "category=orphan-part"
        / "already-quarantined.part"
    )
    ignored_quarantine_part.write_bytes(b"quarantined")

    report = run_write_preflight(
        root=root,
        output=output,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )

    expected_orphans = sorted(
        str(path.relative_to(root)) for path in (first_orphan, second_orphan)
    )
    assert report["existing_orphan_parts"] == expected_orphans
    assert report["checked_target_count"] == STATIC_WRITE_TARGET_COUNT + 2
    assert report["checked_directory_count"] == 24
    assert report["cross_directory_probe_count"] == 18
    assert len(report["cross_directory_checked"]) == 18
    for orphan in expected_orphans:
        assert any(
            label.startswith(f"orphan-part:{orphan}->")
            for label in report["cross_directory_checked"]
        )
    assert first_orphan.read_bytes() == b"partial"
    assert second_orphan.read_bytes() == b"partial"
    assert ignored_quarantine_part.read_bytes() == b"quarantined"
    assert list(root.rglob(".massive-extension-write-probe-*")) == []
    assert list(root.rglob(".massive-extension-cross-probe-*")) == []
    assert list(root.rglob(".massive-orphan-link-probe-*")) == []


def test_orphan_probe_rejects_sticky_parent_owned_by_another_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_directory = tmp_path / "source"
    destination_directory = tmp_path / "destination"
    source_directory.mkdir(mode=0o700)
    source_directory.chmod(0o1777)
    destination_directory.mkdir()
    orphan = source_directory / ".root-owned-simulation.part"
    orphan.write_bytes(b"partial")
    simulated_uid = os.geteuid() + 10_000
    monkeypatch.setattr(preflight_module.os, "geteuid", lambda: simulated_uid)

    failure = preflight_module._probe_existing_orphan(
        orphan,
        destination_directory,
    )

    assert failure is not None
    assert "sticky source directory prevents unlinking" in failure
    assert orphan.read_bytes() == b"partial"
    assert list(destination_directory.iterdir()) == []


def test_write_preflight_rejects_root_identity_before_any_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "day-d-data"
    root.mkdir()
    visited: list[Path] = []
    monkeypatch.setattr(preflight_module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(preflight_module, "_probe_directory", lambda path: visited.append(path))

    with pytest.raises(MassiveExtensionWritePreflightError, match="must not be root"):
        run_write_preflight(
            root=root,
            output=_preflight_output(root),
            expected_uid=0,
            expected_gid=os.getegid(),
        )

    assert visited == []


def test_download_preflight_failure_builds_no_store_or_remote_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "day-d-data"
    root.mkdir()
    output = _preflight_output(root)
    manifest = _create_preflight_directories(root, output)
    source_collision = root / manifest["sessions"][0]["source_relative_path"]
    source_collision.mkdir()
    calls: list[str] = []
    settings = SimpleNamespace(
        day_d_dataset_root=root,
        massive_flat_files_access_key="access",
        massive_flat_files_secret_key="secret",
        massive_flat_files_endpoint="https://example.invalid",
        massive_flat_files_bucket="flatfiles",
        day_d_dataset_min_free_disk_gb=0,
        day_d_historical_download_authorized=True,
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)

    def forbidden_store(*_args: object, **_kwargs: object) -> object:
        calls.append("remote-client")
        raise AssertionError("remote client must not be built")

    monkeypatch.setattr(download_module, "_build_store", forbidden_store)

    with pytest.raises(
        MassiveExtensionWritePreflightError,
        match="source.csv.gz: target is not a regular file",
    ):
        download_module.main([
            "--output", str(output),
            "--head-revision", "a" * 40,
            "--workflow-run-id", "123",
            "--workflow-run-attempt", "1",
            "--expected-uid", str(os.geteuid()),
            "--expected-gid", str(os.getegid()),
        ])

    assert calls == []


def test_download_preflight_completes_before_first_remote_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "day-d-data"
    root.mkdir()
    output = _preflight_output(root)
    calls: list[str] = []
    settings = SimpleNamespace(
        day_d_dataset_root=root,
        massive_flat_files_access_key="access",
        massive_flat_files_secret_key="secret",
        massive_flat_files_endpoint="https://example.invalid",
        massive_flat_files_bucket="flatfiles",
        day_d_dataset_min_free_disk_gb=0,
        day_d_historical_download_authorized=True,
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)

    def successful_preflight(**kwargs: object) -> dict[str, object]:
        calls.append(
            "locked-preflight" if kwargs.get("archive_lock_held") else "preflight"
        )
        return {"status": "ok", "existing_orphan_parts": []}

    def frozen_local_plan(**_kwargs: object) -> tuple[download_module.PlannedArtifact, ...]:
        calls.append("frozen-plan")
        return tuple(
            download_module.PlannedArtifact(
                dataset="minute_aggregates",
                session_date=session_date.isoformat(),
                bucket="flatfiles",
                object_key=f"object-{session_date}",
                content_length=1,
                remote_etag="etag",
                local_path=str(root / f"source-{session_date}.csv.gz"),
            )
            for session_date in EXTENSION_SESSIONS
        )

    def local_ready(**_kwargs: object) -> None:
        calls.append("local-ready")

    def build_store(*_args: object, **_kwargs: object) -> object:
        calls.append("build-store")
        return object()

    class FakeArchive:
        def __init__(self, *_args: object, **kwargs: object) -> None:
            calls.append("archive")
            self.locked_write_preflight = kwargs["locked_write_preflight"]

        def download(self, **_kwargs: object) -> Path:
            self.locked_write_preflight()
            calls.append("remote-head")
            return root / f"session-{len(calls)}.json"

    def build_manifest(**_kwargs: object) -> dict[str, object]:
        calls.append("manifest")
        return {
            "manifest_sha256": "a" * 64,
            "session_count": 8,
            "downloaded_bytes": 214_983_688,
        }

    def write_manifest(_path: Path, _payload: dict[str, object]) -> None:
        calls.append("write-manifest")

    monkeypatch.setattr(download_module, "run_write_preflight", successful_preflight)
    monkeypatch.setattr(download_module, "_frozen_local_plan", frozen_local_plan)
    monkeypatch.setattr(download_module, "_assert_local_download_ready", local_ready)
    monkeypatch.setattr(download_module, "_build_store", build_store)
    monkeypatch.setattr(download_module, "MassiveFlatFileArchive", FakeArchive)
    monkeypatch.setattr(download_module, "build_extension_manifest", build_manifest)
    monkeypatch.setattr(download_module, "_atomic_json", write_manifest)

    assert download_module.main([
        "--output", str(output),
        "--head-revision", "a" * 40,
        "--workflow-run-id", "123",
        "--workflow-run-attempt", "1",
        "--expected-uid", str(os.geteuid()),
        "--expected-gid", str(os.getegid()),
    ]) == 0

    assert calls[:7] == [
        "preflight",
        "frozen-plan",
        "local-ready",
        "build-store",
        "archive",
        "locked-preflight",
        "remote-head",
    ]
    assert calls.count("locked-preflight") == 8
    assert calls.count("remote-head") == 8
