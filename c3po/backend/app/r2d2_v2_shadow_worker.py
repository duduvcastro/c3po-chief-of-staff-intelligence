"""Standalone V2 process. Default OFF, no app startup or schema migration.

No certified release is supplied. Operators must pin independently audited code,
sources and accepted calibration before CERTIFIED collection; DIAGNOSTIC has a
separate receipt/epoch and cannot create episodes or start a cohort clock.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import stat
import time

from .r2d2_v2_calendar import ShadowCalendar
from .r2d2_v2_causal_audit import PostgresCausalReceiptVerifier
from .r2d2_v2_shadow import Release, ShadowCollector, export_cohort
from .r2d2_v2_sources import FileShadowSource, capabilities
from .r2d2_v2_store import PostgresShadowStore, ShadowIntegrityError, canonical

logger = logging.getLogger(__name__)


def _release_bytes(path: str) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > 65536:
            raise ShadowIntegrityError("RELEASE_FILE_NOT_PRIVATE_OR_INVALID")
        data = stream.read(65537)
        after = os.fstat(stream.fileno())
        if (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ShadowIntegrityError("RELEASE_CHANGED_DURING_READ")
        if len(data) != info.st_size:
            raise ShadowIntegrityError("RELEASE_CHANGED_DURING_READ")
    return data


def recheck_release(settings, collector: ShadowCollector) -> None:
    """Revoke on deletion/mutation without rebuilding calendar, source or DB."""
    if (not settings.r2d2_v2_shadow_enabled
            or settings.build_sha != collector.release.code_revision
            or settings.r2d2_v2_shadow_release_sha != collector.release.receipt_sha):
        raise ShadowIntegrityError("RELEASE_CHANGED")
    if sha256(_release_bytes(settings.r2d2_v2_shadow_release_file)).hexdigest() != collector.release.receipt_sha:
        raise ShadowIntegrityError("RELEASE_CHANGED")


def build_collector(settings, *, now: datetime) -> ShadowCollector | None:
    if not settings.r2d2_v2_shadow_enabled:
        return None  # OFF has no filesystem/DB/provider side effects.
    if not settings.database_url:
        raise ShadowIntegrityError("PERSISTENT_DATABASE_REQUIRED")
    data = _release_bytes(settings.r2d2_v2_shadow_release_file)
    calendar = ShadowCalendar()
    release = Release.verify(data, settings.r2d2_v2_shadow_release_sha, now=now,
                             build_sha=settings.build_sha, calendar=calendar)
    # Construction alone does not open a connection. Never initialize() here:
    # that routine owns application-wide migrations/backfills outside V2.
    from .database import Database
    database = Database(settings)
    return ShadowCollector(PostgresShadowStore(database.connection),
                           FileShadowSource(settings.r2d2_v2_shadow_source_dir,
                               causal_receipt_verifier=PostgresCausalReceiptVerifier(database.connection)),
                           release, calendar=calendar)


def _private_export(path: Path, payload: dict) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(canonical(payload) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capabilities", action="store_true", help="Static read-only source readiness; no database")
    parser.add_argument("--once", action="store_true", help="One authorized live cycle")
    parser.add_argument("--export-cohort", type=int, choices=(40, 60))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.capabilities:
        print(json.dumps(capabilities(), sort_keys=True))
        return 0
    if args.export_cohort and not args.output:
        parser.error("--export-cohort requires a new private --output file")
    from .config import get_settings
    settings = get_settings()
    now = datetime.now(timezone.utc)
    collector = build_collector(settings, now=now)
    if collector is None:
        print('{"status":"OFF","collection":false}')
        return 0
    if args.export_cohort:
        saved = collector.store.read(collector.release.epoch)
        if saved is None:
            raise ShadowIntegrityError("EPOCH_NOT_FOUND")
        _private_export(args.output, export_cohort(saved["state"], args.export_cohort, now=now, calendar=collector.calendar))
        print('{"status":"EXPORTED","statistical_verdict":"NOT_COMPUTED"}')
        return 0
    logging.basicConfig(level=logging.INFO)
    last_public = None
    while True:
        # Recheck the pinned release at every cycle: removing it stops intake.
        recheck_release(settings, collector)
        # Retain the source's in-process receipt cache; durable dedup is in DB.
        result = collector.cycle()
        public = {k: v for k, v in result.items() if k not in {"last_cycle_at", "observed_at"}}
        for session in public["sessions"]:
            session.pop("snapshot_attempts", None)
        if public != last_public:
            logger.info("V2 status %s", json.dumps(public, sort_keys=True))
            last_public = public
        if args.once:
            return 0
        time.sleep(settings.r2d2_v2_shadow_poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
