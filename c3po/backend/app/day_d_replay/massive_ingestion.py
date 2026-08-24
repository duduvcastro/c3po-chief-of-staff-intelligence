from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping
from uuid import uuid4

from .point_in_time_universe import (
    PointInTimeUniverseError,
    load_point_in_time_universe_manifest,
)


class MassiveIngestionError(RuntimeError):
    pass


class QualityDropReason(StrEnum):
    MALFORMED_ROW = "malformed_row"
    NONPOSITIVE_PRICE = "nonpositive_price"
    NONPOSITIVE_TRADE_SIZE = "nonpositive_trade_size"
    CROSSED_OR_INVALID_BBO = "crossed_or_invalid_bbo"
    TIMESTAMP_MISSING_OR_INVALID = "timestamp_missing_or_invalid"
    AVAILABLE_BEFORE_EVENT = "available_before_event"
    DUPLICATE_EXACT = "duplicate_exact"


class ScopeFilterReason(StrEnum):
    OUT_OF_SESSION_WINDOW = "out_of_session_window"
    SYMBOL_NOT_IN_SCOPE = "symbol_not_in_scope"


@dataclass(frozen=True, slots=True)
class RowDisposition:
    outcome: str
    normalized: dict[str, Any] | None = None
    reason: QualityDropReason | ScopeFilterReason | None = None


class MassiveR1Normalizer:
    """Fail-closed R1 normalizer for Massive SIP trades and quotes.

    Raw rows are never rewritten. Every row receives exactly one terminal
    outcome: emitted, quality-dropped, or scope-filtered. No clamp, repair,
    timestamp swap, price winsorization, or missing-value imputation exists in
    this layer.
    """

    policy_version = "DAY-D-MASSIVE-INGESTION-POLICY-v1"
    manifest_version = "DAY-D-MASSIVE-NORMALIZED-DATASET-v1"
    quality_thresholds = {"trades": 0.005, "quotes": 0.010}
    sample_limit_per_reason = 100

    def normalize_file(
        self,
        *,
        raw_path: Path,
        output_path: Path,
        dataset: str,
        session_date: date,
        regular_open: datetime,
        regular_close: datetime,
        universe_manifest_path: Path | None,
        measured_at: datetime | None = None,
    ) -> Path:
        self._validate_window(session_date, regular_open, regular_close)
        if dataset not in self.quality_thresholds:
            raise MassiveIngestionError(f"R1 dataset is unsupported: {dataset}")
        if output_path.exists() or self._manifest_path(output_path).exists():
            raise MassiveIngestionError(f"immutable normalized artifact already exists: {output_path}")
        observed_at = measured_at or datetime.now(timezone.utc)
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("measured_at must be timezone-aware")
        if universe_manifest_path is None:
            raise MassiveIngestionError(
                "R1 requires a hash-bound point-in-time universe manifest"
            )
        try:
            universe_payload, frozen_scope = load_point_in_time_universe_manifest(
                universe_manifest_path,
                expected_session_date=session_date,
            )
        except PointInTimeUniverseError as exc:
            raise MassiveIngestionError(f"R1 universe gate failed: {exc}") from exc
        scope = set(frozen_scope)
        universe_evidence = {
            "path": str(universe_manifest_path),
            "bytes": universe_manifest_path.stat().st_size,
            "sha256": self._sha256_file(universe_manifest_path),
            "payload_sha256": universe_payload["payload_sha256"],
            "policy_version": universe_payload["policy_version"],
            "session_date": universe_payload["session_date"],
            "symbol_count": len(scope),
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_name(f".{output_path.name}.{uuid4().hex}.part")
        manifest_path = self._manifest_path(output_path)
        quarantine_written = False
        manifest_published = False
        output_published = False
        counts = self._empty_counts()
        samples: dict[str, list[dict[str, Any]]] = {
            reason.value: []
            for reason in (*QualityDropReason, *ScopeFilterReason)
        }
        seen_exact: set[str] = set()
        try:
            with temporary.open("x", encoding="utf-8") as output:
                for row in self._rows(raw_path):
                    counts["raw_rows_seen"] += 1
                    disposition = self._classify(
                        row=row,
                        dataset=dataset,
                        regular_open=regular_open,
                        regular_close=regular_close,
                        symbols_in_scope=scope,
                        seen_exact=seen_exact,
                    )
                    self._account(disposition, counts=counts, samples=samples, raw_row=row)
                    if disposition.outcome == "emitted":
                        assert disposition.normalized is not None
                        output.write(json.dumps(
                            disposition.normalized,
                            ensure_ascii=True,
                            sort_keys=True,
                            separators=(",", ":"),
                        ))
                        output.write("\n")
                output.flush()
                os.fsync(output.fileno())

            self._assert_identity(counts)
            quality_denominator = counts["emitted_rows"] + counts["dropped_rows"]
            quality_drop_rate = (
                counts["dropped_rows"] / quality_denominator
                if quality_denominator else 0.0
            )
            threshold = self.quality_thresholds[dataset]
            if quality_drop_rate > threshold:
                self._quarantine_report(
                    raw_path=raw_path,
                    dataset=dataset,
                    session_date=session_date,
                    observed_at=observed_at,
                    reason="quality_drop_rate_exceeded",
                    counts=counts,
                    samples=samples,
                    quality_drop_rate=quality_drop_rate,
                    threshold=threshold,
                )
                quarantine_written = True
                raise MassiveIngestionError(
                    f"R1 quality threshold exceeded for {dataset}: "
                    f"{quality_drop_rate:.6f} > {threshold:.6f}"
                )

            manifest = {
                "schema_version": self.manifest_version,
                "policy_version": self.policy_version,
                "dataset": dataset,
                "session_date": session_date.isoformat(),
                "created_at": observed_at.astimezone(timezone.utc).isoformat(),
                "raw_parent": {
                    "path": str(raw_path),
                    "bytes": raw_path.stat().st_size,
                    "sha256": self._sha256_file(raw_path),
                },
                "normalized_artifact": {
                    "path": str(output_path),
                    "bytes": temporary.stat().st_size,
                    "sha256": self._sha256_file(temporary),
                },
                "session_window": {
                    "regular_open": regular_open.astimezone(timezone.utc).isoformat(),
                    "regular_close": regular_close.astimezone(timezone.utc).isoformat(),
                },
                "point_in_time_universe": universe_evidence,
                "counters": counts,
                "identity": {
                    "formula": "raw_rows_seen == emitted_rows + dropped_rows + filtered_rows",
                    "passed": True,
                },
                "quality_drop_rate": quality_drop_rate,
                "quality_drop_threshold": threshold,
                "discard_samples_first_100_per_reason": samples,
                "clamping_performed": False,
                "imputation_performed": False,
                "official_replay_ready": False,
            }
            self._atomic_immutable_json(manifest_path, manifest)
            manifest_published = True
            try:
                os.link(temporary, output_path)
            except FileExistsError as exc:
                raise MassiveIngestionError(
                    f"normalized artifact appeared concurrently: {output_path}"
                ) from exc
            output_published = True
            temporary.unlink()
            return manifest_path
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            if output_published:
                output_path.unlink(missing_ok=True)
            if manifest_published:
                manifest_path.unlink(missing_ok=True)
            if isinstance(exc, MassiveIngestionError) and not quarantine_written:
                self._quarantine_report(
                    raw_path=raw_path,
                    dataset=dataset,
                    session_date=session_date,
                    observed_at=observed_at,
                    reason="normalization_failure",
                    counts=counts,
                    samples=samples,
                    quality_drop_rate=(
                        counts["dropped_rows"]
                        / max(1, counts["emitted_rows"] + counts["dropped_rows"])
                    ),
                    threshold=self.quality_thresholds[dataset],
                )
            raise

    def aggregate_session(
        self,
        *,
        manifest_paths: Iterable[Path],
        output_path: Path,
    ) -> Path:
        paths = tuple(manifest_paths)
        manifests = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        if not manifests:
            raise MassiveIngestionError("session aggregation requires at least one file manifest")
        session_dates = {manifest.get("session_date") for manifest in manifests}
        if len(session_dates) != 1:
            raise MassiveIngestionError("session aggregation cannot mix session dates")
        totals = self._empty_counts()
        samples: dict[str, list[dict[str, Any]]] = {
            reason.value: []
            for reason in (*QualityDropReason, *ScopeFilterReason)
        }
        quality_by_dataset: dict[str, dict[str, int | float | bool]] = {}
        universe_evidence: dict[str, Any] | None = None
        for manifest in manifests:
            if manifest.get("policy_version") != self.policy_version:
                raise MassiveIngestionError("session aggregation encountered an unknown policy")
            for key in totals:
                value = manifest["counters"].get(key)
                if isinstance(value, dict):
                    for reason, count in value.items():
                        totals[key][reason] += int(count)
                else:
                    totals[key] += int(value)
            for reason, rows in manifest[
                "discard_samples_first_100_per_reason"
            ].items():
                remaining = self.sample_limit_per_reason - len(samples[reason])
                if remaining > 0:
                    samples[reason].extend(rows[:remaining])
            dataset = str(manifest["dataset"])
            if dataset in quality_by_dataset:
                raise MassiveIngestionError(
                    "session aggregation received duplicate dataset manifests"
                )
            quality_by_dataset[dataset] = {
                "emitted_rows": int(manifest["counters"]["emitted_rows"]),
                "dropped_rows": int(manifest["counters"]["dropped_rows"]),
                "quality_drop_rate": float(manifest["quality_drop_rate"]),
                "quality_drop_threshold": float(
                    manifest["quality_drop_threshold"]
                ),
                "passed": True,
            }
            candidate_universe = manifest.get("point_in_time_universe")
            if not isinstance(candidate_universe, dict):
                raise MassiveIngestionError(
                    "session aggregation encountered a file without universe evidence"
                )
            if universe_evidence is None:
                universe_evidence = candidate_universe
            elif candidate_universe != universe_evidence:
                raise MassiveIngestionError(
                    "session aggregation cannot mix point-in-time universes"
                )
        self._assert_identity(totals)
        payload = {
            "schema_version": "DAY-D-MASSIVE-R1-SESSION-v1",
            "policy_version": self.policy_version,
            "session_date": next(iter(session_dates)),
            "file_manifests": [str(path) for path in paths],
            "point_in_time_universe": universe_evidence,
            "counters": totals,
            "identity": {
                "formula": "raw_rows_seen == emitted_rows + dropped_rows + filtered_rows",
                "passed": True,
            },
            "quality_by_dataset": quality_by_dataset,
            "discard_samples_first_100_per_reason": samples,
            "official_replay_ready": False,
        }
        self._atomic_immutable_json(output_path, payload)
        return output_path

    def _classify(
        self,
        *,
        row: Mapping[str, Any] | Any,
        dataset: str,
        regular_open: datetime,
        regular_close: datetime,
        symbols_in_scope: set[str],
        seen_exact: set[str],
    ) -> RowDisposition:
        if not isinstance(row, Mapping):
            return RowDisposition("dropped", reason=QualityDropReason.MALFORMED_ROW)
        symbol = str(row.get("ticker") or row.get("symbol") or "").strip()
        if not symbol:
            return RowDisposition("dropped", reason=QualityDropReason.MALFORMED_ROW)
        if symbol not in symbols_in_scope:
            return RowDisposition("filtered", reason=ScopeFilterReason.SYMBOL_NOT_IN_SCOPE)

        event_ns = self._positive_int(row.get("participant_timestamp"))
        available_ns = self._positive_int(row.get("sip_timestamp"))
        if event_ns is None or available_ns is None:
            return RowDisposition(
                "dropped",
                reason=QualityDropReason.TIMESTAMP_MISSING_OR_INVALID,
            )
        if available_ns < event_ns:
            return RowDisposition("dropped", reason=QualityDropReason.AVAILABLE_BEFORE_EVENT)
        event_at = datetime.fromtimestamp(event_ns / 1_000_000_000, tz=timezone.utc)
        available_at = datetime.fromtimestamp(available_ns / 1_000_000_000, tz=timezone.utc)
        if not regular_open <= event_at < regular_close:
            return RowDisposition("filtered", reason=ScopeFilterReason.OUT_OF_SESSION_WINDOW)

        try:
            serialized_row = json.dumps(
                dict(row),
                ensure_ascii=True,
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            return RowDisposition("dropped", reason=QualityDropReason.MALFORMED_ROW)
        exact_key = hashlib.sha256(serialized_row.encode()).hexdigest()
        if exact_key in seen_exact:
            return RowDisposition("dropped", reason=QualityDropReason.DUPLICATE_EXACT)
        seen_exact.add(exact_key)

        if dataset == "trades":
            return self._trade(row, symbol, event_at, available_at)
        if dataset == "quotes":
            return self._quote(row, symbol, event_at, available_at)
        raise MassiveIngestionError(f"unknown R1 dataset: {dataset}")

    def _trade(
        self,
        row: Mapping[str, Any],
        symbol: str,
        event_at: datetime,
        available_at: datetime,
    ) -> RowDisposition:
        price = self._number(row.get("price"))
        size = self._number(row.get("decimal_size") or row.get("size"))
        sequence = self._positive_int(row.get("sequence_number"))
        exchange = self._nonnegative_int(row.get("exchange"))
        if None in (price, size, sequence, exchange):
            return RowDisposition("dropped", reason=QualityDropReason.MALFORMED_ROW)
        assert price is not None and size is not None
        if price <= 0:
            return RowDisposition("dropped", reason=QualityDropReason.NONPOSITIVE_PRICE)
        if size <= 0:
            return RowDisposition("dropped", reason=QualityDropReason.NONPOSITIVE_TRADE_SIZE)
        return RowDisposition("emitted", normalized={
            "symbol": symbol,
            "event_at": event_at.isoformat(),
            "available_at": available_at.isoformat(),
            "participant_timestamp": int(row["participant_timestamp"]),
            "sip_timestamp": int(row["sip_timestamp"]),
            "sequence_number": sequence,
            "exchange": exchange,
            "price": price,
            "size": size,
            "conditions": row.get("conditions"),
        })

    def _quote(
        self,
        row: Mapping[str, Any],
        symbol: str,
        event_at: datetime,
        available_at: datetime,
    ) -> RowDisposition:
        bid = self._number(row.get("bid_price"))
        ask = self._number(row.get("ask_price"))
        bid_size = self._number(row.get("bid_size"))
        ask_size = self._number(row.get("ask_size"))
        sequence = self._positive_int(row.get("sequence_number"))
        if None in (bid, ask, bid_size, ask_size, sequence):
            return RowDisposition("dropped", reason=QualityDropReason.MALFORMED_ROW)
        assert bid is not None and ask is not None
        assert bid_size is not None and ask_size is not None
        if bid < 0 or ask < 0 or (bid == 0 and ask == 0):
            return RowDisposition("dropped", reason=QualityDropReason.NONPOSITIVE_PRICE)
        if bid_size < 0 or ask_size < 0:
            return RowDisposition("dropped", reason=QualityDropReason.CROSSED_OR_INVALID_BBO)
        if bid_size == 0 and ask_size == 0:
            return RowDisposition(
                "dropped", reason=QualityDropReason.CROSSED_OR_INVALID_BBO
            )
        if bid > 0 and ask > 0 and ask < bid:
            return RowDisposition("dropped", reason=QualityDropReason.CROSSED_OR_INVALID_BBO)
        if (bid == 0 and bid_size > 0) or (ask == 0 and ask_size > 0):
            return RowDisposition("dropped", reason=QualityDropReason.CROSSED_OR_INVALID_BBO)
        return RowDisposition("emitted", normalized={
            "symbol": symbol,
            "event_at": event_at.isoformat(),
            "available_at": available_at.isoformat(),
            "participant_timestamp": int(row["participant_timestamp"]),
            "sip_timestamp": int(row["sip_timestamp"]),
            "sequence_number": sequence,
            "bid": bid if bid > 0 else None,
            "ask": ask if ask > 0 else None,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "bid_exchange": self._nonnegative_int(row.get("bid_exchange")),
            "ask_exchange": self._nonnegative_int(row.get("ask_exchange")),
            "conditions": row.get("conditions"),
        })

    def _account(
        self,
        disposition: RowDisposition,
        *,
        counts: dict[str, Any],
        samples: dict[str, list[dict[str, Any]]],
        raw_row: Any,
    ) -> None:
        if disposition.outcome == "emitted" and disposition.reason is None:
            counts["emitted_rows"] += 1
            return
        if disposition.outcome == "dropped" and isinstance(disposition.reason, QualityDropReason):
            counts["dropped_rows"] += 1
            counts["drop_reasons"][disposition.reason.value] += 1
            reason_samples = samples[disposition.reason.value]
            if len(reason_samples) < self.sample_limit_per_reason:
                reason_samples.append(dict(raw_row) if isinstance(raw_row, Mapping) else {"raw": repr(raw_row)})
            return
        if disposition.outcome == "filtered" and isinstance(disposition.reason, ScopeFilterReason):
            counts["filtered_rows"] += 1
            counts["filter_reasons"][disposition.reason.value] += 1
            reason_samples = samples[disposition.reason.value]
            if len(reason_samples) < self.sample_limit_per_reason:
                reason_samples.append(
                    dict(raw_row)
                    if isinstance(raw_row, Mapping)
                    else {"raw": repr(raw_row)}
                )
            return
        raise MassiveIngestionError("row classifier returned an unknown terminal outcome")

    @staticmethod
    def _rows(path: Path) -> Iterator[dict[str, Any]]:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8", newline="") as handle:
            yield from csv.DictReader(handle)

    @staticmethod
    def _empty_counts() -> dict[str, Any]:
        return {
            "raw_rows_seen": 0,
            "emitted_rows": 0,
            "dropped_rows": 0,
            "filtered_rows": 0,
            "clamped_rows": 0,
            "imputed_rows": 0,
            "drop_reasons": {reason.value: 0 for reason in QualityDropReason},
            "filter_reasons": {reason.value: 0 for reason in ScopeFilterReason},
        }

    @staticmethod
    def _assert_identity(counts: Mapping[str, Any]) -> None:
        if int(counts["clamped_rows"]) != 0 or int(counts["imputed_rows"]) != 0:
            raise MassiveIngestionError("R1 forbids clamping and imputation")
        accounted = (
            int(counts["emitted_rows"])
            + int(counts["dropped_rows"])
            + int(counts["filtered_rows"])
        )
        if int(counts["raw_rows_seen"]) != accounted:
            raise MassiveIngestionError("R1 row-accounting identity failed")

    @staticmethod
    def _validate_window(session_date: date, regular_open: datetime, regular_close: datetime) -> None:
        for value in (regular_open, regular_close):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("regular session bounds must be timezone-aware")
        if regular_open >= regular_close:
            raise ValueError("regular session open must precede close")
        if regular_open.date() != session_date and regular_open.astimezone(timezone.utc).date() != session_date:
            # Calendar implementations may express the local session on a UTC
            # date boundary; only reject an obviously unrelated date.
            if abs((regular_open.date() - session_date).days) > 1:
                raise ValueError("regular session does not belong to session_date")

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number == number and abs(number) != float("inf") else None

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @staticmethod
    def _nonnegative_int(value: Any) -> int | None:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number >= 0 else None

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _manifest_path(output_path: Path) -> Path:
        return output_path.with_name(f"{output_path.name}.manifest.json")

    def _quarantine_report(
        self,
        *,
        raw_path: Path,
        dataset: str,
        session_date: date,
        observed_at: datetime,
        reason: str,
        counts: dict[str, Any],
        samples: dict[str, list[dict[str, Any]]],
        quality_drop_rate: float,
        threshold: float,
    ) -> Path:
        suffix = observed_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        path = raw_path.parent / "quarantine" / f"r1-{suffix}-{reason}.json"
        self._atomic_immutable_json(path, {
            "schema_version": "DAY-D-MASSIVE-R1-QUARANTINE-v1",
            "policy_version": self.policy_version,
            "reason": reason,
            "dataset": dataset,
            "session_date": session_date.isoformat(),
            "raw_parent": {
                "path": str(raw_path),
                "sha256": self._sha256_file(raw_path),
            },
            "counters": counts,
            "discard_samples_first_100_per_reason": samples,
            "quality_drop_rate": quality_drop_rate,
            "quality_drop_threshold": threshold,
            "normalized_artifact_emitted": False,
        })
        return path

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
                raise MassiveIngestionError(f"immutable JSON artifact already exists: {path}") from exc
            temporary.unlink()
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
