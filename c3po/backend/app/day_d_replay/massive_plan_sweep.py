from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Any, Sequence

from .massive_archive import (
    FlatFileDataset,
    MassiveFlatFileArchive,
    _build_store,
)


def _is_missing_object(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    if not isinstance(response, dict):
        return False
    error = response.get("Error", {})
    status = int(response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) or 0)
    return str(error.get("Code", "")) in {"404", "NoSuchKey", "NotFound"} or status == 404


def _nearest_rank(values: Sequence[int], percentile: float) -> int:
    if not values:
        raise ValueError("distribution requires at least one value")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _distribution(values: Sequence[int]) -> dict[str, int]:
    if not values:
        raise ValueError("distribution requires at least one value")
    return {
        "count": len(values),
        "sum_bytes": sum(values),
        "minimum_bytes": min(values),
        "p50_bytes": _nearest_rank(values, 0.50),
        "p95_bytes": _nearest_rank(values, 0.95),
        "maximum_bytes": max(values),
        "mean_bytes": round(sum(values) / len(values)),
    }


def run_plan_sweep(
    archive: MassiveFlatFileArchive,
    *,
    start_date: date,
    end_date: date,
    datasets: Sequence[FlatFileDataset],
    measured_at: datetime,
    workers: int = 6,
    spot_dates: Sequence[date] = (),
) -> dict[str, Any]:
    if end_date < start_date:
        raise ValueError("end_date must not precede start_date")
    if measured_at.tzinfo is None or measured_at.utcoffset() is None:
        raise ValueError("measured_at must be timezone-aware")
    unique_datasets = tuple(dict.fromkeys(datasets))
    if not unique_datasets:
        raise ValueError("at least one dataset is required")

    weekdays: list[date] = []
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5:
            weekdays.append(cursor)
        cursor += timedelta(days=1)

    def fetch(day: date, dataset: FlatFileDataset) -> tuple[date, str, dict[str, Any] | None]:
        try:
            item = archive.plan(session_date=day, datasets=(dataset,))[0]
        except Exception as exc:
            if _is_missing_object(exc):
                return day, dataset.value, None
            raise
        return day, dataset.value, {
            "content_length": item.content_length,
            "remote_etag": item.remote_etag,
            "object_key": item.object_key,
        }

    observations: dict[date, dict[str, dict[str, Any]]] = defaultdict(dict)
    tasks = [(day, dataset) for day in weekdays for dataset in unique_datasets]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(fetch, day, dataset) for day, dataset in tasks]
        for future in as_completed(futures):
            day, dataset, item = future.result()
            if item is not None:
                observations[day][dataset] = item

    required = {dataset.value for dataset in unique_datasets}
    complete_sessions: list[dict[str, Any]] = []
    partial_sessions: list[dict[str, Any]] = []
    non_session_weekdays: list[str] = []
    for day in weekdays:
        present = set(observations[day])
        if present == required:
            artifacts = observations[day]
            row = {
                "session_date": day.isoformat(),
                "artifacts": artifacts,
                "total_bytes": sum(item["content_length"] for item in artifacts.values()),
            }
            if {FlatFileDataset.TRADES.value, FlatFileDataset.QUOTES.value} <= present:
                row["raw_trades_quotes_bytes"] = (
                    artifacts[FlatFileDataset.TRADES.value]["content_length"]
                    + artifacts[FlatFileDataset.QUOTES.value]["content_length"]
                )
            complete_sessions.append(row)
        elif present:
            partial_sessions.append({
                "session_date": day.isoformat(),
                "present": sorted(present),
                "missing": sorted(required - present),
            })
        else:
            non_session_weekdays.append(day.isoformat())

    if not complete_sessions:
        raise ValueError("sweep found no complete sessions")

    dataset_distributions = {
        dataset: _distribution([
            row["artifacts"][dataset]["content_length"] for row in complete_sessions
        ])
        for dataset in sorted(required)
    }
    total_distribution = _distribution([row["total_bytes"] for row in complete_sessions])
    raw_rows = [
        row["raw_trades_quotes_bytes"] for row in complete_sessions
        if "raw_trades_quotes_bytes" in row
    ]
    raw_distribution = _distribution(raw_rows) if raw_rows else None
    rows_by_date = {row["session_date"]: row for row in complete_sessions}
    partial_dates = {row["session_date"] for row in partial_sessions}
    spot_checks = []
    for spot_date in spot_dates:
        row = rows_by_date.get(spot_date.isoformat())
        spot_checks.append({
            "session_date": spot_date.isoformat(),
            "status": "complete" if row else (
                "partial" if spot_date.isoformat() in partial_dates else "missing"
            ),
            "total_bytes": row["total_bytes"] if row else None,
            "raw_trades_quotes_bytes": row.get("raw_trades_quotes_bytes") if row else None,
        })

    maximum_session = max(complete_sessions, key=lambda row: row["total_bytes"])
    report = {
        "schema_version": "DAY-D-MASSIVE-T0-PLAN-SWEEP-v1",
        "mode": "read_only_head_only",
        "downloaded": False,
        "source_csv_files": 0,
        "measured_at": measured_at.astimezone(timezone.utc).isoformat(),
        "campaign": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "weekday_candidates": len(weekdays),
            "complete_sessions": len(complete_sessions),
            "non_session_weekdays": non_session_weekdays,
            "partial_sessions": partial_sessions,
            "head_requests": len(tasks),
        },
        "quantile_method": "nearest_rank",
        "datasets": dataset_distributions,
        "raw_trades_quotes": raw_distribution,
        "all_requested_datasets": total_distribution,
        "maximum_session": {
            "session_date": maximum_session["session_date"],
            "total_bytes": maximum_session["total_bytes"],
        },
        "spot_checks": spot_checks,
        "sessions": complete_sessions,
    }
    return report


def main(argv: Sequence[str] | None = None) -> int:
    from app.config import get_settings

    parser = argparse.ArgumentParser(description="HEAD-only capacity sweep of Massive stock Flat Files")
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--dataset",
        action="append",
        choices=[dataset.value for dataset in FlatFileDataset],
        required=True,
    )
    parser.add_argument("--spot-date", action="append", type=date.fromisoformat, default=[])
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args(argv)

    settings = get_settings()
    archive = MassiveFlatFileArchive(
        _build_store(
            settings.massive_flat_files_access_key,
            settings.massive_flat_files_secret_key,
            settings.massive_flat_files_endpoint,
        ),
        root=settings.day_d_dataset_root,
        bucket=settings.massive_flat_files_bucket,
        minimum_free_bytes=int(settings.day_d_dataset_min_free_disk_gb * 1024**3),
    )
    measured_at = datetime.now(timezone.utc)
    report = run_plan_sweep(
        archive,
        start_date=args.start_date,
        end_date=args.end_date,
        datasets=tuple(FlatFileDataset(value) for value in args.dataset),
        measured_at=measured_at,
        workers=args.workers,
        spot_dates=tuple(args.spot_date),
    )
    destination = (
        settings.day_d_dataset_root
        / "provider=massive"
        / "plans"
        / f"t0-plan-sweep-{measured_at.strftime('%Y%m%dT%H%M%S.%fZ')}.json"
    )
    MassiveFlatFileArchive._atomic_json(destination, report)
    summary = {
        "downloaded": False,
        "report": str(destination),
        "complete_sessions": report["campaign"]["complete_sessions"],
        "datasets": report["datasets"],
        "raw_trades_quotes": report["raw_trades_quotes"],
        "all_requested_datasets": report["all_requested_datasets"],
        "maximum_session": report["maximum_session"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
