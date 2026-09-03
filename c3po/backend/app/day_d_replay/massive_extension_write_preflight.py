from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, Sequence
from uuid import uuid4


class MassiveExtensionWritePreflightError(RuntimeError):
    pass


FROZEN_PLAN_PATH = Path(__file__).with_name(
    "massive_minute_extension_20260903_plan.json"
)
FROZEN_PLAN_SHA256 = (
    "cf78e15dfd48aa3eaafa2ef27bdc3b65b5f77894e54495e25fa99ab7c11b7a65"
)
EXPECTED_SESSIONS = (
    "2026-08-24",
    "2026-08-25",
    "2026-08-26",
    "2026-08-27",
    "2026-08-28",
    "2026-08-31",
    "2026-09-01",
    "2026-09-02",
)
QUARANTINE_CATEGORIES = (
    "orphan-part",
    "remote-changed",
    "remote-rehead-failed",
)
STATIC_WRITE_TARGET_COUNT = 76
STATIC_CROSS_DIRECTORY_PAIR_COUNT = 16


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return _sha256_bytes(canonical)


def _load_frozen_sessions() -> tuple[dict[str, Any], ...]:
    raw = FROZEN_PLAN_PATH.read_bytes()
    if _sha256_bytes(raw) != FROZEN_PLAN_SHA256:
        raise MassiveExtensionWritePreflightError(
            "frozen Massive extension plan checksum mismatch"
        )
    payload = json.loads(raw)
    if (
        payload.get("schema_version") != "DAY-D-MASSIVE-T0-PLAN-SWEEP-v1"
        or payload.get("mode") != "read_only_head_only"
        or payload.get("downloaded") is not False
        or payload.get("source_csv_files") != 0
        or sorted(payload.get("datasets", {})) != ["minute_aggregates"]
    ):
        raise MassiveExtensionWritePreflightError(
            "frozen Massive extension plan metadata is invalid"
        )
    sessions = payload.get("sessions")
    if not isinstance(sessions, list):
        raise MassiveExtensionWritePreflightError(
            "frozen Massive extension plan has no session rows"
        )
    if len(sessions) != len(EXPECTED_SESSIONS):
        raise MassiveExtensionWritePreflightError(
            "frozen Massive extension requires exactly eight sessions"
        )

    rows: list[dict[str, Any]] = []
    for expected_session, row in zip(EXPECTED_SESSIONS, sessions):
        if not isinstance(row, dict):
            raise MassiveExtensionWritePreflightError(
                "frozen Massive extension plan has a malformed session"
            )
        artifacts = row.get("artifacts")
        if (
            row.get("session_date") != expected_session
            or not isinstance(artifacts, dict)
            or sorted(artifacts) != ["minute_aggregates"]
        ):
            raise MassiveExtensionWritePreflightError(
                "frozen Massive extension plan coverage is invalid"
            )
        artifact = artifacts["minute_aggregates"]
        expected_key = (
            "us_stocks_sip/minute_aggs_v1/"
            f"{expected_session[:4]}/{expected_session[5:7]}/{expected_session}.csv.gz"
        )
        if (
            not isinstance(artifact, dict)
            or artifact.get("object_key") != expected_key
            or int(artifact.get("content_length") or 0) <= 0
            or not artifact.get("remote_etag")
        ):
            raise MassiveExtensionWritePreflightError(
                "frozen Massive extension artifact metadata is invalid"
            )
        rows.append({
            "session_date": expected_session,
            "object_key": expected_key,
            "content_length": int(artifact["content_length"]),
            "remote_etag": str(artifact["remote_etag"]),
        })
    return tuple(rows)


def _safe_relative(path: Path) -> Path:
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise MassiveExtensionWritePreflightError(
            f"unsafe Massive extension write path: {path}"
        )
    return path


def _validated_absolute(root: Path, relative: Path) -> Path:
    resolved_root = root.resolve()
    candidate = resolved_root / _safe_relative(relative)
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise MassiveExtensionWritePreflightError(
            f"Massive extension write path escaped through a symlink: {relative}"
        ) from exc
    if resolved_candidate != candidate:
        raise MassiveExtensionWritePreflightError(
            f"Massive extension write path contains a symlink: {relative}"
        )
    return candidate


def _parents_under_root(paths: set[Path]) -> list[str]:
    parents: set[Path] = set()
    for path in paths:
        for index in range(1, len(path.parts)):
            parents.add(Path(*path.parts[:index]))
    return [str(path) for path in sorted(parents, key=lambda item: (len(item.parts), str(item)))]


def _enumerate_orphan_parts(root: Path) -> tuple[Path, ...]:
    quarantine_root = root / "provider=massive" / "quarantine"
    failures: list[str] = []
    candidates: list[Path] = []

    def record_failure(exc: OSError) -> None:
        failures.append(
            f"{exc.filename or root}: {type(exc).__name__}(errno={exc.errno}): {exc}"
        )

    for directory, names, filenames in os.walk(
        root,
        topdown=True,
        onerror=record_failure,
        followlinks=False,
    ):
        current = Path(directory)
        if current == quarantine_root or quarantine_root in current.parents:
            names[:] = []
            continue
        names[:] = sorted(names)
        for filename in sorted(filenames):
            if filename.endswith(".part"):
                candidates.append(current / filename)
    if failures:
        raise MassiveExtensionWritePreflightError(
            "could not enumerate the complete Massive orphan manifest:\n- "
            + "\n- ".join(sorted(failures))
        )
    return tuple(sorted(candidates))


def build_write_manifest(
    *,
    root: Path,
    output: Path,
    include_existing_orphans: bool = True,
) -> dict[str, Any]:
    resolved_root = root.resolve()
    absolute_output = output if output.is_absolute() else Path.cwd() / output
    try:
        output_relative = _safe_relative(absolute_output.relative_to(resolved_root))
    except ValueError as exc:
        raise MassiveExtensionWritePreflightError(
            "Massive extension output escaped the Day-D root"
        ) from exc
    if output_relative.name != "extension-download-manifest.json":
        raise MassiveExtensionWritePreflightError(
            "Massive extension output filename is not canonical"
        )

    write_targets: list[dict[str, str]] = [
        {
            "kind": "archive_lock",
            "relative_path": "evidence/.massive-download.lock",
            "validation": "exact_lock",
        },
        {
            "kind": "extension_manifest",
            "relative_path": str(output_relative),
            "validation": "exact_absent_then_directory_atomic",
        },
        {
            "kind": "extension_manifest_temporary_pattern",
            "relative_path": str(
                output_relative.with_name(
                    f".{output_relative.name}.<pid>.part"
                )
            ),
            "validation": "directory_atomic_pattern",
        },
    ]
    write_directories: set[Path] = {
        Path("evidence"),
        output_relative.parent,
    }
    privileged_write_directories: set[Path] = set()
    cross_directory_pairs: list[dict[str, str]] = []
    orphan_hardlink_pairs: list[dict[str, str]] = []
    session_rows: list[dict[str, Any]] = []

    for row in _load_frozen_sessions():
        session_date = row["session_date"]
        object_key = row["object_key"]
        source = (
            Path("provider=massive")
            / "dataset=minute_aggregates"
            / f"session_date={session_date}"
            / "source.csv.gz"
        )
        metadata = source.with_name("source.csv.gz.metadata.json")
        session_manifest_directory = (
            Path("provider=massive")
            / "manifests"
            / f"session_date={session_date}"
        )
        event_identity = hashlib.sha256(
            f"flatfiles\n{object_key}".encode("utf-8")
        ).hexdigest()
        event = (
            Path("provider=massive")
            / "campaign"
            / "verified-events"
            / f"{event_identity}.json"
        )
        for kind, target, validation in (
            ("archive_source", source, "exact_absent_or_immutable"),
            ("archive_metadata", metadata, "exact_absent_or_immutable"),
            ("campaign_event", event, "exact_absent_or_immutable"),
        ):
            write_targets.append({
                "kind": kind,
                "relative_path": str(target),
                "validation": validation,
            })
        write_targets.extend((
            {
                "kind": "archive_source_temporary_pattern",
                "relative_path": str(
                    source.with_name(f".{source.name}.<uuid>.part")
                ),
                "validation": "directory_atomic_pattern",
            },
            {
                "kind": "archive_metadata_temporary_pattern",
                "relative_path": str(
                    metadata.with_name(f".{metadata.name}.<uuid>.part")
                ),
                "validation": "directory_atomic_pattern",
            },
            {
                "kind": "session_manifest_pattern",
                "relative_path": str(
                    session_manifest_directory / "manifest-<UTC>.json"
                ),
                "validation": "directory_atomic_pattern",
            },
            {
                "kind": "session_manifest_temporary_pattern",
                "relative_path": str(
                    session_manifest_directory / ".manifest-<UTC>.json.<uuid>.part"
                ),
                "validation": "directory_atomic_pattern",
            },
            {
                "kind": "campaign_event_temporary_pattern",
                "relative_path": str(
                    event.with_name(f".{event.name}.<uuid>.part")
                ),
                "validation": "directory_atomic_pattern",
            },
        ))
        write_directories.update({
            source.parent,
            session_manifest_directory,
            event.parent,
        })
        privileged_write_directories.update({
            source.parent,
            session_manifest_directory,
            event.parent,
        })
        for category in ("remote-changed", "remote-rehead-failed"):
            cross_directory_pairs.append({
                "operation": category,
                "source_directory_relative_path": str(source.parent),
                "destination_directory_relative_path": str(
                    Path("provider=massive")
                    / "quarantine"
                    / f"category={category}"
                ),
            })
        session_rows.append({
            "session_date": session_date,
            "object_key": object_key,
            "content_length": row["content_length"],
            "remote_etag": row["remote_etag"],
            "source_relative_path": str(source),
            "metadata_relative_path": str(metadata),
            "manifest_directory_relative_path": str(session_manifest_directory),
            "campaign_event_relative_path": str(event),
        })

    for category in QUARANTINE_CATEGORIES:
        directory = (
            Path("provider=massive")
            / "quarantine"
            / f"category={category}"
        )
        write_directories.add(directory)
        privileged_write_directories.add(directory)
        quarantine_pattern = directory / "<timestamp>-<uuid>-<source>"
        write_targets.extend((
            {
                "kind": f"quarantine_{category}_pattern",
                "relative_path": str(quarantine_pattern),
                "validation": "directory_atomic_pattern",
            },
            {
                "kind": f"quarantine_{category}_metadata_pattern",
                "relative_path": f"{quarantine_pattern}.metadata.json",
                "validation": "directory_atomic_pattern",
            },
            {
                "kind": f"quarantine_{category}_metadata_temporary_pattern",
                "relative_path": str(
                    directory
                    / ".<timestamp>-<uuid>-<source>.metadata.json.<uuid>.part"
                ),
                "validation": "directory_atomic_pattern",
            },
        ))

    existing_orphan_parts: list[str] = []
    if include_existing_orphans:
        orphan_candidates = _enumerate_orphan_parts(resolved_root)
        for orphan in orphan_candidates:
            try:
                relative = _safe_relative(orphan.relative_to(resolved_root))
            except ValueError as exc:
                raise MassiveExtensionWritePreflightError(
                    f"Massive orphan escaped the Day-D root: {orphan}"
                ) from exc
            existing_orphan_parts.append(str(relative))
            write_directories.add(relative.parent)
            write_targets.append({
                "kind": "existing_orphan_part",
                "relative_path": str(relative),
                "validation": "exact_existing_and_cross_directory",
            })
            orphan_hardlink_pairs.append({
                "source_relative_path": str(relative),
                "destination_directory_relative_path": (
                    "provider=massive/quarantine/category=orphan-part"
                ),
            })

    for path in write_directories:
        _safe_relative(path)
    if len(write_targets) != STATIC_WRITE_TARGET_COUNT + len(existing_orphan_parts):
        raise MassiveExtensionWritePreflightError(
            "Massive extension write target manifest is incomplete"
        )
    if len(cross_directory_pairs) != STATIC_CROSS_DIRECTORY_PAIR_COUNT:
        raise MassiveExtensionWritePreflightError(
            "Massive extension cross-directory manifest is incomplete"
        )
    manifest: dict[str, Any] = {
        "schema_version": "DAY-D-MASSIVE-EXTENSION-WRITE-PREFLIGHT-v1",
        "frozen_plan_sha256": FROZEN_PLAN_SHA256,
        "root": str(resolved_root),
        "output_relative_path": str(output_relative),
        "sessions": session_rows,
        "existing_orphan_parts": existing_orphan_parts,
        "write_targets": sorted(
            write_targets,
            key=lambda item: (item["relative_path"], item["kind"]),
        ),
        "write_directories": [str(path) for path in sorted(write_directories, key=str)],
        "privileged_write_directories": [
            str(path) for path in sorted(privileged_write_directories, key=str)
        ],
        "cross_directory_pairs": sorted(
            {
                (
                    pair["operation"],
                    pair["source_directory_relative_path"],
                    pair["destination_directory_relative_path"],
                )
                for pair in cross_directory_pairs
            }
        ),
        "orphan_hardlink_pairs": sorted(
            orphan_hardlink_pairs,
            key=lambda pair: (
                pair["source_relative_path"],
                pair["destination_directory_relative_path"],
            ),
        ),
        "provision_parent_directories": _parents_under_root(
            privileged_write_directories
        ),
    }
    manifest["cross_directory_pairs"] = [
        {
            "operation": operation,
            "source_directory_relative_path": source,
            "destination_directory_relative_path": destination,
        }
        for operation, source, destination in manifest["cross_directory_pairs"]
    ]
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    return manifest


def _probe_directory(path: Path) -> str | None:
    token = uuid4().hex
    source = path / f".massive-extension-write-probe-{token}.tmp"
    hardlink = path / f".massive-extension-write-probe-{token}.link"
    descriptor: int | None = None
    failure: str | None = None
    try:
        if path.is_symlink() or not path.is_dir():
            raise NotADirectoryError(f"not a real directory: {path}")
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(source, flags, 0o600)
        os.write(descriptor, b"write-preflight\n")
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.link(source, hardlink, follow_symlinks=False)
        hardlink.unlink()
        source.unlink()
        directory_descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        failure = f"{type(exc).__name__}(errno={exc.errno}): {exc}"
    finally:
        for probe_path in (hardlink, source):
            try:
                probe_path.unlink(missing_ok=True)
            except (FileNotFoundError, NotADirectoryError):
                pass
            except OSError as exc:
                if failure is None:
                    failure = (
                        f"probe cleanup {type(exc).__name__}(errno={exc.errno}): {exc}"
                    )
    return failure


def _probe_cross_directory(source_directory: Path, destination_directory: Path) -> str | None:
    token = uuid4().hex
    source = source_directory / f".massive-extension-cross-probe-{token}.tmp"
    destination = destination_directory / f".massive-extension-cross-probe-{token}.link"
    descriptor: int | None = None
    failure: str | None = None
    try:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(source, flags, 0o600)
        os.write(descriptor, b"cross-directory-hardlink-preflight\n")
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.link(source, destination, follow_symlinks=False)
        destination.unlink()
        source.unlink()
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        failure = f"{type(exc).__name__}(errno={exc.errno}): {exc}"
    finally:
        for probe_path in (destination, source):
            try:
                probe_path.unlink(missing_ok=True)
            except (FileNotFoundError, NotADirectoryError):
                pass
            except OSError as exc:
                if failure is None:
                    failure = (
                        f"probe cleanup {type(exc).__name__}(errno={exc.errno}): "
                        f"{exc}"
                    )
    return failure


def _probe_existing_orphan(orphan: Path, destination_directory: Path) -> str | None:
    token = uuid4().hex
    destination = destination_directory / f".massive-orphan-link-probe-{token}.link"
    failure: str | None = None
    try:
        orphan_stat = orphan.stat(follow_symlinks=False)
        parent_stat = orphan.parent.stat(follow_symlinks=False)
        if parent_stat.st_mode & stat.S_ISVTX and os.geteuid() not in {
            parent_stat.st_uid,
            orphan_stat.st_uid,
        }:
            raise PermissionError(
                "sticky source directory prevents unlinking this orphan identity"
            )
        os.link(orphan, destination, follow_symlinks=False)
        destination.unlink()
        directory_descriptor = os.open(destination_directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        failure = f"{type(exc).__name__}(errno={exc.errno}): {exc}"
    finally:
        try:
            destination.unlink(missing_ok=True)
        except (FileNotFoundError, NotADirectoryError):
            pass
        except OSError as exc:
            if failure is None:
                failure = (
                    f"probe cleanup {type(exc).__name__}(errno={exc.errno}): {exc}"
                )
    return failure


def _target_collision(path: Path, *, allow_absent: bool) -> str | None:
    if path.is_symlink():
        return "target is a symlink"
    if not path.exists():
        return None if allow_absent else "target is missing"
    if not path.is_file():
        return "target is not a regular file"
    return None


def _read_json_target(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    collision = _target_collision(path, allow_absent=False)
    if collision is not None:
        return None, collision
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"target is not readable canonical JSON: {type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return None, "target JSON is not an object"
    return payload, None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_session_targets(root: Path, row: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    source_relative = str(row["source_relative_path"])
    metadata_relative = str(row["metadata_relative_path"])
    event_relative = str(row["campaign_event_relative_path"])

    def validated(relative: str) -> Path | None:
        try:
            return _validated_absolute(root, Path(relative))
        except MassiveExtensionWritePreflightError as exc:
            failures.append(f"{relative}: {exc}")
            return None

    source = validated(source_relative)
    metadata = validated(metadata_relative)
    event = validated(event_relative)

    source_present = source is not None and (source.exists() or source.is_symlink())
    metadata_present = metadata is not None and (
        metadata.exists() or metadata.is_symlink()
    )
    source_collision = (
        _target_collision(source, allow_absent=True) if source is not None else None
    )
    metadata_collision = (
        _target_collision(metadata, allow_absent=True)
        if metadata is not None
        else None
    )
    if source_collision is not None:
        failures.append(f"{source_relative}: {source_collision}")
    if metadata_collision is not None:
        failures.append(f"{metadata_relative}: {metadata_collision}")
    if source_present != metadata_present:
        missing = metadata_relative if source_present else source_relative
        failures.append(f"{missing}: source and immutable metadata must coexist")
    observed_sha256: str | None = None
    if (
        source is not None
        and metadata is not None
        and source_present
        and metadata_present
        and source_collision is None
        and metadata_collision is None
    ):
        metadata_payload, metadata_error = _read_json_target(metadata)
        if metadata_error is not None or metadata_payload is None:
            failures.append(f"{metadata_relative}: {metadata_error}")
        else:
            expected_metadata = {
                "schema_version": "DAY-D-MASSIVE-ARCHIVE-v1",
                "bucket": "flatfiles",
                "object_key": row["object_key"],
                "content_length": row["content_length"],
                "remote_etag": row["remote_etag"],
            }
            observed_metadata = {
                key: metadata_payload.get(key) for key in expected_metadata
            }
            if observed_metadata != expected_metadata:
                failures.append(
                    f"{metadata_relative}: metadata differs from the frozen plan"
                )
            try:
                observed_size = source.stat().st_size
                observed_sha256 = _sha256_file(source)
            except OSError as exc:
                failures.append(
                    f"{source_relative}: source is unreadable: {type(exc).__name__}: {exc}"
                )
            else:
                if observed_size != row["content_length"]:
                    failures.append(
                        f"{source_relative}: source size differs from the frozen plan"
                    )
                if metadata_payload.get("sha256") != observed_sha256:
                    failures.append(
                        f"{source_relative}: source checksum differs from immutable metadata"
                    )

    event_collision = (
        _target_collision(event, allow_absent=True) if event is not None else None
    )
    if event is not None:
        if event_collision is not None:
            failures.append(f"{event_relative}: {event_collision}")
        elif event.exists():
            event_payload, event_error = _read_json_target(event)
            if event_error is not None or event_payload is None:
                failures.append(f"{event_relative}: {event_error}")
            else:
                expected_event = {
                    "schema_version": "DAY-D-MASSIVE-CAMPAIGN-EVENT-v1",
                    "bucket": "flatfiles",
                    "object_key": row["object_key"],
                    "dataset": "minute_aggregates",
                    "session_date": row["session_date"],
                    "verified_bytes": row["content_length"],
                }
                if {
                    key: event_payload.get(key) for key in expected_event
                } != expected_event:
                    failures.append(
                        f"{event_relative}: campaign event differs from the frozen plan"
                    )
                event_sha256 = event_payload.get("sha256")
                if (
                    not isinstance(event_sha256, str)
                    or len(event_sha256) != 64
                    or any(
                        character not in "0123456789abcdef"
                        for character in event_sha256
                    )
                ):
                    failures.append(
                        f"{event_relative}: campaign event SHA-256 is invalid"
                    )
                elif observed_sha256 is not None and event_sha256 != observed_sha256:
                    failures.append(
                        f"{event_relative}: campaign event checksum differs from the source"
                    )
                if not source_present or not metadata_present:
                    failures.append(
                        f"{event_relative}: campaign event exists without immutable "
                        "source and metadata"
                    )
    return failures


def _validate_exact_targets(
    root: Path,
    manifest: dict[str, Any],
    *,
    archive_lock_held: bool,
) -> list[str]:
    failures: list[str] = []
    lock_relative = Path("evidence/.massive-download.lock")
    lock_path = _validated_absolute(root, lock_relative)
    lock_collision = _target_collision(lock_path, allow_absent=True)
    if lock_collision is not None:
        failures.append(f"{lock_relative}: {lock_collision}")
    elif not archive_lock_held:
        try:
            with lock_path.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError as exc:
            failures.append(
                f"{lock_relative}: lock is not writable and acquirable: "
                f"{type(exc).__name__}(errno={exc.errno}): {exc}"
            )

    output_relative = Path(str(manifest["output_relative_path"]))
    output = _validated_absolute(root, output_relative)
    if output.exists() or output.is_symlink():
        failures.append(f"{output_relative}: output target already exists")

    for row in manifest["sessions"]:
        try:
            failures.extend(_validate_session_targets(root, row))
        except MassiveExtensionWritePreflightError as exc:
            failures.append(f"{row['session_date']}: {exc}")

    for relative in manifest["existing_orphan_parts"]:
        try:
            orphan = _validated_absolute(root, Path(relative))
        except MassiveExtensionWritePreflightError as exc:
            failures.append(f"{relative}: {exc}")
            continue
        collision = _target_collision(orphan, allow_absent=False)
        if collision is not None:
            failures.append(f"{relative}: {collision}")
    return failures


def run_write_preflight(
    *,
    root: Path,
    output: Path,
    expected_uid: int,
    expected_gid: int,
    archive_lock_held: bool = False,
) -> dict[str, Any]:
    effective_uid = os.geteuid()
    effective_gid = os.getegid()
    if effective_uid == 0:
        raise MassiveExtensionWritePreflightError(
            "Massive extension runtime identity must not be root"
        )
    if (effective_uid, effective_gid) != (expected_uid, expected_gid):
        raise MassiveExtensionWritePreflightError(
            "Massive extension runtime UID:GID differs from the operational identity"
        )

    manifest = build_write_manifest(root=root, output=output)
    failures: list[str] = []
    checked: list[str] = []
    for relative in manifest["write_directories"]:
        checked.append(relative)
        try:
            path = _validated_absolute(root, Path(relative))
            failure = _probe_directory(path)
        except MassiveExtensionWritePreflightError as exc:
            failure = str(exc)
        if failure is not None:
            failures.append(f"{relative}: {failure}")
    try:
        failures.extend(
            _validate_exact_targets(
                root,
                manifest,
                archive_lock_held=archive_lock_held,
            )
        )
    except MassiveExtensionWritePreflightError as exc:
        failures.append(f"exact target validation: {exc}")

    cross_directory_checked: list[str] = []
    for pair in manifest["cross_directory_pairs"]:
        source_relative = str(pair["source_directory_relative_path"])
        destination_relative = str(pair["destination_directory_relative_path"])
        label = f"{pair['operation']}:{source_relative}->{destination_relative}"
        cross_directory_checked.append(label)
        try:
            source_directory = _validated_absolute(root, Path(source_relative))
            destination_directory = _validated_absolute(
                root,
                Path(destination_relative),
            )
            failure = _probe_cross_directory(
                source_directory,
                destination_directory,
            )
        except MassiveExtensionWritePreflightError as exc:
            failure = str(exc)
        if failure is not None:
            failures.append(f"{label}: {failure}")
    for pair in manifest["orphan_hardlink_pairs"]:
        source_relative = str(pair["source_relative_path"])
        destination_relative = str(pair["destination_directory_relative_path"])
        label = f"orphan-part:{source_relative}->{destination_relative}"
        cross_directory_checked.append(label)
        try:
            orphan = _validated_absolute(root, Path(source_relative))
            destination_directory = _validated_absolute(
                root,
                Path(destination_relative),
            )
            failure = _probe_existing_orphan(orphan, destination_directory)
        except MassiveExtensionWritePreflightError as exc:
            failure = str(exc)
        if failure is not None:
            failures.append(f"{label}: {failure}")
    if failures:
        raise MassiveExtensionWritePreflightError(
            "Massive extension write preflight failed for all listed paths:\n- "
            + "\n- ".join(sorted(failures))
        )

    return {
        "schema_version": manifest["schema_version"],
        "status": "ok",
        "manifest_sha256": manifest["manifest_sha256"],
        "frozen_plan_sha256": manifest["frozen_plan_sha256"],
        "operational_identity": {
            "uid": effective_uid,
            "gid": effective_gid,
        },
        "checked_directories": checked,
        "checked_directory_count": len(checked),
        "checked_targets": manifest["write_targets"],
        "checked_target_count": len(manifest["write_targets"]),
        "frozen_artifacts": [
            {
                "dataset": "minute_aggregates",
                "session_date": row["session_date"],
                "bucket": "flatfiles",
                "object_key": row["object_key"],
                "content_length": row["content_length"],
                "remote_etag": row["remote_etag"],
                "local_path_relative": row["source_relative_path"],
            }
            for row in manifest["sessions"]
        ],
        "existing_orphan_parts": manifest["existing_orphan_parts"],
        "cross_directory_checked": cross_directory_checked,
        "cross_directory_probe_count": len(cross_directory_checked),
        "network_calls_before_preflight": 0,
    }


def _absolute_directories(
    *, root: Path, output: Path, field: str
) -> tuple[Path, ...]:
    manifest = build_write_manifest(
        root=root,
        output=output,
        include_existing_orphans=False,
    )
    return tuple(
        _validated_absolute(root, Path(relative))
        for relative in manifest[field]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enumerate the frozen Massive extension write allowlist"
    )
    parser.add_argument(
        "command",
        choices=(
            "list-provision-parent-directories",
            "list-privileged-write-directories",
        ),
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    field = (
        "provision_parent_directories"
        if args.command == "list-provision-parent-directories"
        else "privileged_write_directories"
    )
    for path in _absolute_directories(root=args.root, output=args.output, field=field):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
