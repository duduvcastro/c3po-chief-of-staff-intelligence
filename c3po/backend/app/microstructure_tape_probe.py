from __future__ import annotations

import argparse
import gzip
import json
import os
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence
from zoneinfo import ZoneInfo

from .config import Settings, get_settings
from .database import Database
from .market_data.http import JsonHttpClient
from .market_data.massive import MassiveClient
from .r2d2_entry_quality_engine import classify_entry_market_compatibility
from .r2d2_entry_quality_study import EntryLedgerReader, _read_price_paths
from .r2d2_exit_policy_engine import (
    LedgerFill,
    StudyBar,
    build_episodes,
    classify_market_compatibility,
)
from .r2d2_exit_policy_study import (
    LedgerReader,
    MinuteAggregateReader,
    _base_cohort,
    _coverage_cohort,
    _frozen_ledger_input,
    canonical_json_bytes,
    canonical_sha256,
    require_frozen_document,
    sha256_file,
    write_immutable_json,
)


NEW_YORK = ZoneInfo("America/New_York")
SPEC_SHA256 = "b97354c5a4889effefff2d39caae73a8a8a579e56ffc57b33c4353aab43ce3e9"
AMENDMENT_SHA256 = "5bd49ae90f800ef16a2b643439e8c1f1690c549cc869bd99fac72c76911e29ff"
DUDU_ATTESTATION_SHA256 = "3168b5f0bec3e714a2ceaa01f7e5ab9f1af2f3525c50995786d79583e9480de2"
CODEX_ATTESTATION_SHA256 = "c1415c1efa63c3cc1618c67e0391b542e75cb6b3463bd09f96d1350c80ef3925"
REPORT_SCHEMA_VERSION = "MICROSTRUCTURE-TAPE-PROBE-V1-REPORT-v1"
MANIFEST_SCHEMA_VERSION = "MICROSTRUCTURE-TAPE-PROBE-V1-MANIFEST-v1"
TARGET_GATE_CLASSES = frozenset({"clock_extended", "tolerance_band", "violation"})
TAPE_CLASSES = (
    "condition_explained",
    "aggregation_diff",
    "no_tape_support",
    "inconclusive",
)
WINDOW_RADIUS_MINUTES = 5
MAX_LOGICAL_WINDOW_REQUESTS = 300
ENTITLEMENT_PROBE_REQUESTS = 1


class TapeProbeError(RuntimeError):
    pass


class TapeClient(Protocol):
    def iter_raw_trades_between(
        self,
        symbol: str,
        *,
        start_at: datetime,
        end_at: datetime,
        limit: int = 50_000,
    ) -> Iterable[dict[str, Any]]: ...

    def trade_conditions(self) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class ProbeCase:
    case_id: str
    study: str
    fill_id: str
    episode_id: str | None
    market: str
    symbol: str
    side: str
    session_date: date
    signal_price: float
    executed_at: datetime
    quote_as_of: datetime
    gate_classification: str
    gate_breach_bps: float | None
    gate_matched_anchor: str | None
    gate_matched_offset_minutes: int | None

    def __post_init__(self) -> None:
        if self.gate_classification not in TARGET_GATE_CLASSES:
            raise ValueError(f"unsupported gate classification: {self.gate_classification}")
        if self.executed_at.tzinfo is None or self.quote_as_of.tzinfo is None:
            raise ValueError("probe case timestamps must be timezone-aware")
        if self.signal_price <= 0:
            raise ValueError("probe signal price must be positive")


@dataclass(frozen=True, slots=True)
class ProbeWindow:
    window_id: str
    symbol: str
    session_date: date
    start_at: datetime
    end_at: datetime
    cases: tuple[ProbeCase, ...]


def _aware(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _load_self_hashed_json(
    path: Path,
    *,
    hash_field: str,
    expected_schema: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.is_file():
        raise TapeProbeError(f"frozen input is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TapeProbeError(f"frozen input must be a JSON object: {path}")
    if expected_schema is not None and payload.get("schema_version") != expected_schema:
        raise TapeProbeError(
            f"unsupported schema for {path}: {payload.get('schema_version')}"
        )
    claimed = str(payload.get(hash_field) or "")
    observed = canonical_sha256({
        key: value for key, value in payload.items() if key != hash_field
    })
    if claimed != observed:
        raise TapeProbeError(
            f"self-hash mismatch for {path}: expected {claimed}, observed {observed}"
        )
    return payload, {
        "path": str(path),
        "file_sha256": sha256_file(path),
        hash_field: observed,
        "size_bytes": path.stat().st_size,
    }


def _minute_bars(values: Sequence[StudyBar], session: date) -> dict[datetime, StudyBar]:
    return {
        bar.start_at.astimezone(timezone.utc): bar
        for bar in values
        if bar.session_date == session
    }


def _case(
    *,
    study: str,
    fill: LedgerFill,
    compatibility: Mapping[str, Any],
    episode_id: str | None,
) -> ProbeCase:
    return ProbeCase(
        case_id=f"{study}:{fill.id}",
        study=study,
        fill_id=fill.id,
        episode_id=episode_id,
        market=fill.market,
        symbol=fill.symbol,
        side=fill.side,
        session_date=fill.executed_at.astimezone(NEW_YORK).date(),
        signal_price=fill.signal_price_local,
        executed_at=fill.executed_at,
        quote_as_of=fill.quote_as_of,
        gate_classification=str(compatibility["classification"]),
        gate_breach_bps=(
            float(compatibility["breach_bps"])
            if compatibility.get("breach_bps") is not None else None
        ),
        gate_matched_anchor=(
            str(compatibility["matched_anchor"])
            if compatibility.get("matched_anchor") is not None else None
        ),
        gate_matched_offset_minutes=(
            int(compatibility["matched_offset_minutes"])
            if compatibility.get("matched_offset_minutes") is not None else None
        ),
    )


def _derive_exit_cases(
    settings: Settings,
    report: Mapping[str, Any],
) -> tuple[list[ProbeCase], dict[str, Any]]:
    if not report.get("analysis_interpretable"):
        raise TapeProbeError("exit-study report is not interpretable")
    inputs = _mapping(report.get("inputs"))
    ledger_input = _mapping(inputs.get("ledger"))
    cutoff = _aware(ledger_input["input_cutoff_at"])
    expected_ledger = str(ledger_input["canonical_json_sha256"])
    expected_minutes = str(inputs["minute_aggregate_manifest_sha256"])

    database = Database(settings)
    _experiment, all_fills = LedgerReader(database).read(settings.r2d2_experiment_code)
    fills, ledger_evidence = _frozen_ledger_input(
        all_fills,
        cutoff_at=cutoff,
        expected_sha256=expected_ledger,
    )
    episodes, _construction = build_episodes(fills)
    reader = MinuteAggregateReader(settings.day_d_dataset_root)
    sources = reader.selected_sources(episodes)
    symbols = {
        episode.symbol for episode in episodes
        if episode.market in {"NASDAQ", "NYSE"}
    }
    bars, bar_evidence = reader.read(sources, symbols)
    minute_hash = canonical_sha256(bar_evidence)
    if minute_hash != expected_minutes:
        raise TapeProbeError(
            f"exit minute manifest mismatch: expected {expected_minutes}, observed {minute_hash}"
        )
    latest = max(session for session, _path in sources)
    base, _base_censoring = _base_cohort(episodes, latest)
    covered, _coverage_censoring = _coverage_cohort(base, bars)
    cases: list[ProbeCase] = []
    for episode in covered:
        for fill in episode.fills:
            session = fill.executed_at.astimezone(NEW_YORK).date()
            compatibility = classify_market_compatibility(
                fill,
                _minute_bars(bars.get(fill.symbol, ()), session),
            )
            if compatibility["classification"] in TARGET_GATE_CLASSES:
                cases.append(_case(
                    study="exit_policy_v1_1",
                    fill=fill,
                    compatibility=compatibility,
                    episode_id=episode.id,
                ))
    return cases, {
        "ledger": ledger_evidence,
        "minute_aggregate_manifest_sha256": minute_hash,
        "target_case_count": len(cases),
    }


def _derive_entry_cases(
    settings: Settings,
    report: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> tuple[list[ProbeCase], dict[str, Any]]:
    if not report.get("analysis_interpretable"):
        raise TapeProbeError("entry-study report is not interpretable")
    if report.get("manifest_sha256") != manifest.get("manifest_sha256"):
        raise TapeProbeError("entry report does not reference the supplied manifest")
    ledger_input = _mapping(manifest.get("ledger"))
    cutoff = _aware(ledger_input["last_executed_at"])
    expected_ledger = str(ledger_input["canonical_json_sha256"])

    database = Database(settings)
    _experiment, all_records = EntryLedgerReader(database).read(
        settings.r2d2_experiment_code
    )
    records = [
        record for record in all_records
        if record.fill.executed_at <= cutoff
    ]
    observed_ledger = canonical_sha256([asdict(record.fill) for record in records])
    if observed_ledger != expected_ledger:
        raise TapeProbeError(
            f"entry ledger hash mismatch: expected {expected_ledger}, observed {observed_ledger}"
        )
    bars, bar_evidence = _read_price_paths(settings, records)
    observed_prices = canonical_sha256(bar_evidence)
    expected_prices = str(manifest["price_source_manifest_sha256"])
    if observed_prices != expected_prices:
        raise TapeProbeError(
            f"entry price-source manifest mismatch: expected {expected_prices}, observed {observed_prices}"
        )
    cases: list[ProbeCase] = []
    for record in records:
        fill = record.fill
        session = fill.executed_at.astimezone(NEW_YORK).date()
        compatibility = classify_entry_market_compatibility(
            fill,
            _minute_bars(bars.get(fill.symbol, ()), session),
        )
        if compatibility["classification"] in TARGET_GATE_CLASSES:
            cases.append(_case(
                study="entry_quality_v1",
                fill=fill,
                compatibility=compatibility,
                episode_id=None,
            ))
    return cases, {
        "ledger": {
            "last_executed_at": cutoff,
            "canonical_json_sha256": observed_ledger,
            "organic_buy_count": len(records),
        },
        "price_source_manifest_sha256": observed_prices,
        "target_case_count": len(cases),
    }


def deduplicate_windows(cases: Sequence[ProbeCase]) -> list[ProbeWindow]:
    grouped: dict[tuple[str, date, datetime], list[ProbeCase]] = defaultdict(list)
    for case in cases:
        center = case.quote_as_of.astimezone(timezone.utc).replace(second=0, microsecond=0)
        grouped[(case.symbol, case.session_date, center)].append(case)
    windows: list[ProbeWindow] = []
    for (symbol, session, center), grouped_cases in sorted(grouped.items()):
        start = center - timedelta(minutes=WINDOW_RADIUS_MINUTES)
        end = center + timedelta(minutes=WINDOW_RADIUS_MINUTES + 1)
        identity = {
            "symbol": symbol,
            "session_date": session,
            "start_at": start,
            "end_at": end,
        }
        windows.append(ProbeWindow(
            window_id=canonical_sha256(identity)[:24],
            symbol=symbol,
            session_date=session,
            start_at=start,
            end_at=end,
            cases=tuple(sorted(grouped_cases, key=lambda item: item.case_id)),
        ))
    return windows


def _frozen_contract(
    *,
    spec_path: Path | None,
    amendment_path: Path | None,
    dudu_attestation_path: Path | None,
    codex_attestation_path: Path | None,
) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    return {
        "spec": require_frozen_document(
            spec_path or root / "docs" / "MICROSTRUCTURE_TAPE_PROBE_V1.md",
            SPEC_SHA256,
            "MICROSTRUCTURE_TAPE_PROBE_V1 spec",
        ),
        "amendment_one": require_frozen_document(
            amendment_path or root / "docs" / "MICROSTRUCTURE_TAPE_PROBE_V1_AMENDMENT_1.md",
            AMENDMENT_SHA256,
            "MICROSTRUCTURE_TAPE_PROBE_V1 Amendment 1",
        ),
        "dudu_attestation": require_frozen_document(
            dudu_attestation_path
            or root / "docs" / "MICROSTRUCTURE_TAPE_PROBE_V1_AMENDMENT_1_ATTESTATION_DUDU.md",
            DUDU_ATTESTATION_SHA256,
            "Dudu Amendment 1 attestation",
        ),
        "codex_attestation": require_frozen_document(
            codex_attestation_path
            or root / "docs" / "MICROSTRUCTURE_TAPE_PROBE_V1_AMENDMENT_1_ATTESTATION_CODEX.md",
            CODEX_ATTESTATION_SHA256,
            "Codex Amendment 1 attestation",
        ),
    }


def build_plan(
    *,
    settings: Settings,
    exit_report_path: Path,
    entry_report_path: Path,
    entry_manifest_path: Path,
    spec_path: Path | None = None,
    amendment_path: Path | None = None,
    dudu_attestation_path: Path | None = None,
    codex_attestation_path: Path | None = None,
) -> dict[str, Any]:
    contract = _frozen_contract(
        spec_path=spec_path,
        amendment_path=amendment_path,
        dudu_attestation_path=dudu_attestation_path,
        codex_attestation_path=codex_attestation_path,
    )
    exit_report, exit_ref = _load_self_hashed_json(
        exit_report_path,
        hash_field="report_sha256",
        expected_schema="EXIT-POLICY-STUDY-V1.1-REPORT-v2",
    )
    entry_report, entry_report_ref = _load_self_hashed_json(
        entry_report_path,
        hash_field="report_sha256",
        expected_schema="ENTRY-QUALITY-STUDY-V1-REPORT-v1",
    )
    entry_manifest, entry_manifest_ref = _load_self_hashed_json(
        entry_manifest_path,
        hash_field="manifest_sha256",
        expected_schema="ENTRY-QUALITY-STUDY-V1-MANIFEST-v1",
    )
    exit_cases, exit_inputs = _derive_exit_cases(settings, exit_report)
    entry_cases, entry_inputs = _derive_entry_cases(
        settings,
        entry_report,
        entry_manifest,
    )
    cases = sorted(exit_cases + entry_cases, key=lambda item: item.case_id)
    if len({case.case_id for case in cases}) != len(cases):
        raise TapeProbeError("derived probe case IDs are not unique")
    windows = deduplicate_windows(cases)
    logical_requests = len(windows) + ENTITLEMENT_PROBE_REQUESTS
    cap_passed = logical_requests <= MAX_LOGICAL_WINDOW_REQUESTS
    return {
        "command": "plan",
        "read_only": True,
        "external_api_calls": 0,
        "report_written": False,
        "frozen_contract": contract,
        "frozen_inputs": {
            "exit_report": exit_ref,
            "entry_report": entry_report_ref,
            "entry_manifest": entry_manifest_ref,
            "exit_rederivation": exit_inputs,
            "entry_rederivation": entry_inputs,
        },
        "sample": {
            "case_count": len(cases),
            "window_count": len(windows),
            "case_counts_by_study": dict(sorted(Counter(
                case.study for case in cases
            ).items())),
            "case_counts_by_gate_class": dict(sorted(Counter(
                case.gate_classification for case in cases
            ).items())),
            "dedup_key": ["symbol", "session_date", "quote_as_of_minute"],
            "window_minute_offsets_inclusive": [-5, 5],
            "cases": [asdict(case) for case in cases],
            "windows": [asdict(window) for window in windows],
        },
        "logical_cap": {
            "maximum_window_requests": MAX_LOGICAL_WINDOW_REQUESTS,
            "entitlement_probe_requests": ENTITLEMENT_PROBE_REQUESTS,
            "sample_window_requests": len(windows),
            "total_window_requests": logical_requests,
            "passed": cap_passed,
        },
        "execution_ready": cap_passed,
        "execution_blockers": (
            [] if cap_passed else ["logical_window_request_cap_exceeded"]
        ),
        "governance": {
            "fable_audit_required_before_run": True,
            "production_writes": 0,
            "strategy_changes": 0,
            "gate_changes": 0,
        },
    }


def _condition_updates_high_low(row: Mapping[str, Any]) -> bool | None:
    update_rules = _mapping(row.get("update_rules"))
    consolidated = _mapping(update_rules.get("consolidated"))
    value = consolidated.get("updates_high_low")
    return value if isinstance(value, bool) else None


def _condition_index(rows: Sequence[Mapping[str, Any]]) -> dict[str, bool | None]:
    output: dict[str, bool | None] = {}
    for row in rows:
        condition_id = row.get("id")
        if condition_id is None:
            continue
        key = str(condition_id)
        if key in output:
            raise TapeProbeError(f"Massive returned duplicate condition code {key}")
        output[key] = _condition_updates_high_low(row)
    if not output:
        raise TapeProbeError("Massive returned no stock trade condition codes")
    return output


def _raw_trade(row: Mapping[str, Any]) -> dict[str, Any] | None:
    try:
        event_ns = int(row["participant_timestamp"])
        sip_ns = int(row["sip_timestamp"])
        price = float(row["price"])
        size = float(row.get("decimal_size") or row["size"])
    except (KeyError, TypeError, ValueError):
        return None
    if min(event_ns, sip_ns) <= 0 or price <= 0 or size <= 0 or sip_ns < event_ns:
        return None
    return {
        "trade_id": str(row.get("id") or row.get("sequence_number") or ""),
        "event_at": datetime.fromtimestamp(event_ns / 1_000_000_000, tz=timezone.utc),
        "available_at": datetime.fromtimestamp(sip_ns / 1_000_000_000, tz=timezone.utc),
        "price": price,
        "size": size,
        "exchange": row.get("exchange"),
        "conditions": tuple(str(value) for value in (row.get("conditions") or ())),
        "sequence_number": row.get("sequence_number"),
        "tape": row.get("tape"),
    }


def classify_tape_case(
    case: ProbeCase,
    trades: Sequence[Mapping[str, Any]],
    condition_index: Mapping[str, bool | None],
) -> dict[str, Any]:
    distances = [
        (abs(float(trade["price"]) - case.signal_price) / case.signal_price * 10_000.0, trade)
        for trade in trades
    ]
    distances.sort(key=lambda item: (
        item[0],
        _aware(item[1]["event_at"]),
        str(item[1].get("trade_id") or ""),
    ))
    nearest = distances[0] if distances else None
    within_two = [item for item in distances if item[0] <= 2.0]
    classification = "inconclusive"
    reason = "provider_window_empty_or_invalid"
    matched: Mapping[str, Any] | None = None
    if within_two:
        non_updating = []
        normal = []
        unknown = []
        for distance, trade in within_two:
            conditions = tuple(str(value) for value in trade.get("conditions", ()))
            rules = [condition_index.get(value) for value in conditions]
            if any(rule is False for rule in rules):
                non_updating.append((distance, trade))
            elif not conditions or all(rule is True for rule in rules):
                normal.append((distance, trade))
            else:
                unknown.append((distance, trade))
        if non_updating:
            classification = "condition_explained"
            reason = "trade_within_2bps_has_non_high_low_updating_condition"
            matched = non_updating[0][1]
        elif normal:
            classification = "aggregation_diff"
            reason = "normal_trade_within_2bps"
            matched = normal[0][1]
        else:
            reason = "trade_within_2bps_has_unknown_condition_semantics"
            matched = unknown[0][1] if unknown else None
    elif nearest is not None and nearest[0] > 10.0:
        classification = "no_tape_support"
        reason = "no_trade_within_10bps"
        matched = nearest[1]
    elif nearest is not None:
        reason = "nearest_trade_between_2_and_10bps"
        matched = nearest[1]

    matched_distance = (
        abs(float(matched["price"]) - case.signal_price) / case.signal_price * 10_000.0
        if matched is not None else None
    )
    return {
        "case_id": case.case_id,
        "study": case.study,
        "fill_id": case.fill_id,
        "episode_id": case.episode_id,
        "market": case.market,
        "symbol": case.symbol,
        "session_date": case.session_date,
        "side": case.side,
        "signal_price": case.signal_price,
        "executed_at": case.executed_at,
        "quote_as_of": case.quote_as_of,
        "gate_classification": case.gate_classification,
        "gate_breach_bps": case.gate_breach_bps,
        "classification": classification,
        "classification_reason": reason,
        "valid_tape_trade_count": len(trades),
        "nearest_trade_bps": nearest[0] if nearest is not None else None,
        "matched_trade": (
            {
                "trade_id": matched.get("trade_id"),
                "event_at": matched.get("event_at"),
                "available_at": matched.get("available_at"),
                "price": matched.get("price"),
                "size": matched.get("size"),
                "exchange": matched.get("exchange"),
                "conditions": list(matched.get("conditions", ())),
                "distance_bps": matched_distance,
            }
            if matched is not None else None
        ),
    }


def _write_raw_line(handle: Any, payload: Mapping[str, Any]) -> None:
    handle.write(canonical_json_bytes(payload) + b"\n")


def _publish_immutable_file(temporary: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256_file(target) == sha256_file(temporary):
            temporary.unlink(missing_ok=True)
            return
        raise FileExistsError(f"immutable evidence already exists: {target}")
    os.link(temporary, target)
    temporary.unlink(missing_ok=True)


def run_probe(
    *,
    plan: Mapping[str, Any],
    client: TapeClient,
    output: Path,
    generated_at: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    generated_at = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not plan.get("execution_ready"):
        raise TapeProbeError(
            f"probe plan is blocked: {plan.get('execution_blockers')}"
        )
    windows = [
        ProbeWindow(
            window_id=str(row["window_id"]),
            symbol=str(row["symbol"]),
            session_date=date.fromisoformat(str(row["session_date"])),
            start_at=_aware(row["start_at"]),
            end_at=_aware(row["end_at"]),
            cases=tuple(ProbeCase(
                case_id=str(case["case_id"]),
                study=str(case["study"]),
                fill_id=str(case["fill_id"]),
                episode_id=(
                    str(case["episode_id"])
                    if case.get("episode_id") is not None else None
                ),
                market=str(case["market"]),
                symbol=str(case["symbol"]),
                side=str(case["side"]),
                session_date=date.fromisoformat(str(case["session_date"])),
                signal_price=float(case["signal_price"]),
                executed_at=_aware(case["executed_at"]),
                quote_as_of=_aware(case["quote_as_of"]),
                gate_classification=str(case["gate_classification"]),
                gate_breach_bps=(
                    float(case["gate_breach_bps"])
                    if case.get("gate_breach_bps") is not None else None
                ),
                gate_matched_anchor=(
                    str(case["gate_matched_anchor"])
                    if case.get("gate_matched_anchor") is not None else None
                ),
                gate_matched_offset_minutes=(
                    int(case["gate_matched_offset_minutes"])
                    if case.get("gate_matched_offset_minutes") is not None else None
                ),
            ) for case in row["cases"]),
        )
        for row in _mapping(plan.get("sample")).get("windows", ())
    ]
    if not windows:
        raise TapeProbeError("probe sample has no windows")

    output.mkdir(parents=True, exist_ok=True)
    raw_target = output / "raw" / "massive-trades.ndjson.gz"
    raw_target.parent.mkdir(parents=True, exist_ok=True)
    temporary = raw_target.with_name(f".{raw_target.name}.{os.getpid()}.tmp")
    status = "COMPLETE"
    error: str | None = None
    entitlement: dict[str, Any]
    window_evidence: list[dict[str, Any]] = []
    case_results: list[dict[str, Any]] = []
    condition_rows: list[dict[str, Any]] = []
    processed = 0
    first = windows[0]
    proof_end = first.start_at + timedelta(microseconds=1)
    try:
        list(client.iter_raw_trades_between(
            first.symbol,
            start_at=first.start_at,
            end_at=proof_end,
            limit=1,
        ))
        entitlement = {
            "passed": True,
            "read_only": True,
            "symbol": first.symbol,
            "start_at": first.start_at,
            "end_at": proof_end,
            "result": "historical trades endpoint accepted bounded request",
        }
    except Exception as exc:
        entitlement = {
            "passed": False,
            "read_only": True,
            "symbol": first.symbol,
            "start_at": first.start_at,
            "end_at": proof_end,
            "error": str(exc),
        }
        status = "BLOCKED_ENTITLEMENT"
        error = str(exc)

    with temporary.open("xb") as compressed_handle, gzip.GzipFile(
        filename="",
        mode="wb",
        compresslevel=6,
        fileobj=compressed_handle,
        mtime=0,
    ) as raw_handle:
        if status == "COMPLETE":
            try:
                condition_rows = client.trade_conditions()
                condition_index = _condition_index(condition_rows)
            except Exception as exc:
                condition_index = {}
                status = "BLOCKED_CONDITION_REFERENCE"
                error = str(exc)
            if status == "COMPLETE":
                for window in windows:
                    try:
                        raw_rows = list(client.iter_raw_trades_between(
                            window.symbol,
                            start_at=window.start_at,
                            end_at=window.end_at,
                        ))
                    except Exception as exc:
                        status = "PARTIAL"
                        error = str(exc)
                        break
                    normalized = [
                        parsed for parsed in (_raw_trade(row) for row in raw_rows)
                        if parsed is not None
                    ]
                    for row in raw_rows:
                        _write_raw_line(raw_handle, {
                            "window_id": window.window_id,
                            "symbol": window.symbol,
                            "session_date": window.session_date,
                            "provider": "massive",
                            "provider_row": row,
                        })
                    for case in window.cases:
                        case_results.append(classify_tape_case(
                            case,
                            normalized,
                            condition_index,
                        ))
                    window_evidence.append({
                        "window_id": window.window_id,
                        "symbol": window.symbol,
                        "session_date": window.session_date,
                        "start_at": window.start_at,
                        "end_at": window.end_at,
                        "case_ids": [case.case_id for case in window.cases],
                        "provider_row_count": len(raw_rows),
                        "valid_trade_count": len(normalized),
                    })
                    processed += 1
    _publish_immutable_file(temporary, raw_target)

    counts = Counter(row["classification"] for row in case_results)
    by_study: dict[str, Counter[str]] = defaultdict(Counter)
    by_session: dict[str, Counter[str]] = defaultdict(Counter)
    for row in case_results:
        by_study[str(row["study"])][str(row["classification"])] += 1
        by_session[str(row["session_date"])][str(row["classification"])] += 1
    classified_count = len(case_results)
    explained_count = counts["condition_explained"] + counts["aggregation_diff"]
    inconclusive_count = counts["inconclusive"]
    strong_interpretation = (
        status == "COMPLETE"
        and classified_count > 0
        and explained_count / classified_count >= 0.70
        and inconclusive_count / classified_count <= 0.10
    )

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": generated_at,
        "provider": "massive",
        "source_endpoint": "/v3/trades/{ticker}",
        "read_only": True,
        "plan_sha256": canonical_sha256(plan),
        "frozen_contract": plan["frozen_contract"],
        "frozen_inputs": plan["frozen_inputs"],
        "logical_cap": plan["logical_cap"],
        "entitlement_proof": entitlement,
        "condition_reference": {
            "endpoint": "/v3/reference/conditions",
            "row_count": len(condition_rows),
            "canonical_json_sha256": canonical_sha256(condition_rows),
        },
        "sample": {
            "planned_case_count": _mapping(plan["sample"])["case_count"],
            "planned_window_count": len(windows),
            "processed_window_count": processed,
            "window_evidence": window_evidence,
        },
        "raw_tape": {
            "path": str(raw_target),
            "sha256": sha256_file(raw_target),
            "size_bytes": raw_target.stat().st_size,
            "format": "gzip NDJSON; provider rows preserved without credentials",
        },
        "status": status,
        "error": error,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": status,
        "error": error,
        "analysis_interpretable": status == "COMPLETE",
        "manifest_sha256": manifest["manifest_sha256"],
        "governance": {
            "read_only": True,
            "incremental_cost_usd": 0,
            "strategy_change_authorized": False,
            "gate_change_authorized": False,
            "consumer_change_authorized": False,
        },
        "entitlement_proof": entitlement,
        "sample": {
            "planned_case_count": _mapping(plan["sample"])["case_count"],
            "classified_case_count": classified_count,
            "planned_window_count": len(windows),
            "processed_window_count": processed,
        },
        "classification_order": list(TAPE_CLASSES),
        "classification_counts": {
            name: counts[name] for name in TAPE_CLASSES
        },
        "classification_counts_by_study": {
            study: {name: values[name] for name in TAPE_CLASSES}
            for study, values in sorted(by_study.items())
        },
        "classification_counts_by_session": {
            session: {name: values[name] for name in TAPE_CLASSES}
            for session, values in sorted(by_session.items())
        },
        "preregistered_reading": {
            "condition_plus_aggregation_percent": (
                explained_count / classified_count * 100.0
                if classified_count else None
            ),
            "inconclusive_percent": (
                inconclusive_count / classified_count * 100.0
                if classified_count else None
            ),
            "strong_interpretation_requires_explained_at_least_percent": 70.0,
            "strong_interpretation_requires_inconclusive_at_most_percent": 10.0,
            "strong_interpretation_passed": strong_interpretation,
        },
        "cases": case_results,
        "limitations": [
            "A nearest trade between 2 and 10 bps is inconclusive because the frozen spec assigns no stronger class.",
            "Massive participant and SIP timestamps are preserved for future work but do not create a new Phase 1 class.",
            "No result from this probe changes a gate, tolerance, consumer or strategy without a separate signed amendment.",
        ],
    }
    report["report_sha256"] = canonical_sha256(report)
    write_immutable_json(output / "manifest.json", manifest)
    write_immutable_json(output / "report.json", report)
    sums = {
        "manifest.json": sha256_file(output / "manifest.json"),
        "report.json": sha256_file(output / "report.json"),
        "raw/massive-trades.ndjson.gz": sha256_file(raw_target),
    }
    write_immutable_json(output / "SHA256SUMS.json", sums)
    return manifest, report


def _client(settings: Settings) -> MassiveClient:
    return MassiveClient(
        settings.massive_base_url,
        settings.massive_api_token,
        JsonHttpClient(
            timeout=settings.market_data_timeout_seconds,
            max_retries=settings.market_data_max_retries,
        ),
        historical_access_authorized=True,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Massive tape probe for signed microstructure Phase 1",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("plan", "run"):
        child = subparsers.add_parser(command)
        child.add_argument("--exit-report", type=Path, required=True)
        child.add_argument("--entry-report", type=Path, required=True)
        child.add_argument("--entry-manifest", type=Path, required=True)
        child.add_argument("--spec", type=Path)
        child.add_argument("--amendment", type=Path)
        child.add_argument("--dudu-attestation", type=Path)
        child.add_argument("--codex-attestation", type=Path)
        if command == "run":
            child.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = get_settings()
    plan = build_plan(
        settings=settings,
        exit_report_path=args.exit_report,
        entry_report_path=args.entry_report,
        entry_manifest_path=args.entry_manifest,
        spec_path=args.spec,
        amendment_path=args.amendment,
        dudu_attestation_path=args.dudu_attestation,
        codex_attestation_path=args.codex_attestation,
    )
    if args.command == "plan":
        print(json.dumps(plan, sort_keys=True, indent=2, default=str))
        return 0 if plan["execution_ready"] else 2
    manifest, report = run_probe(
        plan=plan,
        client=_client(settings),
        output=args.output,
    )
    print(json.dumps({
        "status": report["status"],
        "analysis_interpretable": report["analysis_interpretable"],
        "manifest_sha256": manifest["manifest_sha256"],
        "report_sha256": report["report_sha256"],
        "output": str(args.output),
    }, sort_keys=True))
    return 0 if report["analysis_interpretable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
