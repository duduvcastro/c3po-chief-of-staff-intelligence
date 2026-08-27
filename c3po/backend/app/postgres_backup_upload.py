from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

from .config import Settings, get_settings
from .observability import init_sentry


MAX_SINGLE_PUT_BYTES = 5 * 1024**3


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _client(settings: Settings):
    kwargs: dict[str, Any] = {
        "region_name": settings.postgres_backup_region,
        "aws_access_key_id": settings.postgres_backup_access_key_id,
        "aws_secret_access_key": settings.postgres_backup_secret_access_key,
    }
    if settings.postgres_backup_endpoint:
        kwargs["endpoint_url"] = settings.postgres_backup_endpoint
    return boto3.client("s3", **kwargs)


def upload_backup(
    path: Path, *, session_date: date, settings: Settings
) -> dict[str, Any]:
    required = {
        "bucket": settings.postgres_backup_bucket,
        "access_key_id": settings.postgres_backup_access_key_id,
        "secret_access_key": settings.postgres_backup_secret_access_key,
    }
    missing = sorted(key for key, value in required.items() if not value)
    if missing:
        raise RuntimeError(
            f"postgres backup storage is not configured: {', '.join(missing)}"
        )
    size = path.stat().st_size
    if size <= 0 or size >= MAX_SINGLE_PUT_BYTES:
        raise RuntimeError(
            f"backup size {size} is outside the single-PUT contract"
        )
    sha256 = _sha256(path)
    prefix = settings.postgres_backup_prefix.strip("/") or "c3po-postgres"
    filename = f"c3po-postgres-{session_date.isoformat()}-{sha256}.dump"
    keys = [f"{prefix}/daily/{session_date:%Y/%m/%d}/{filename}"]
    if session_date.day == 1:
        keys.append(f"{prefix}/monthly/{session_date:%Y/%m}/{filename}")

    client = _client(settings)
    uploads = []
    for key in keys:
        try:
            with path.open("rb") as source:
                response = client.put_object(
                    Bucket=settings.postgres_backup_bucket,
                    Key=key,
                    Body=source,
                    ContentLength=size,
                    ContentType="application/octet-stream",
                    Metadata={
                        "sha256": sha256,
                        "session-date": session_date.isoformat(),
                        "format": "postgres-custom",
                    },
                    ServerSideEncryption="AES256",
                    StorageClass="STANDARD",
                    IfNoneMatch="*",
                )
            uploads.append(
                {
                    "key": key,
                    "etag": str(response.get("ETag") or "").strip('"'),
                    "version_id": response.get("VersionId"),
                }
            )
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 412:
                uploads.append({"key": key, "already_present": True})
                continue
            raise
    return {
        "schema": "C3PO_POSTGRES_BACKUP_UPLOAD-v1",
        "session_date": session_date.isoformat(),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "file_size": size,
        "file_sha256": sha256,
        "bucket": settings.postgres_backup_bucket,
        "region": settings.postgres_backup_region,
        "endpoint_configured": bool(settings.postgres_backup_endpoint),
        "uploads": uploads,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--session-date", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    settings = get_settings()
    init_sentry(settings, service_name="postgres-backup")
    result = upload_backup(
        args.file, session_date=args.session_date, settings=settings
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
