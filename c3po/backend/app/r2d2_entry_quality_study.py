from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from .config import Settings, get_settings
from .database import Database
from .r2d2_entry_quality_engine import (
    BOOTSTRAP_ITERATIONS,
    BOOTSTRAP_SEED,
    EntryMeasurement,
    EntryQualityStudyError,
    atr_class,
    entry_regime,
    entry_route,
    entry_stretch,
    frozen_stretch_upper_quartile,
    hypothesis_reports,
    measure_entry,
    quote_age_class,
    reconcile_entry_gate,
    report_by_dimension,
    summarize_cell,
)
from .r2d2_exit_policy_engine import ExitPolicyStudyError, LedgerFill, StudyBar
from .r2d2_exit_policy_study import (
    NEW_YORK,
    REGULAR_CLOSE,
    REGULAR_OPEN,
    LedgerReader,
    MinuteAggregateReader,
    _ledger_fill,
    canonical_sha256,
    require_frozen_document,
    sha256_file,
    write_immutable_json,
)


SPEC_SHA256 = "63cdb045a69dfe31246e82fa64e00dd1f9e0357897259a0d420ad81d0957a41e"
ATTESTATION_SHA256 = "2319708dd4fff344f4536610b9588d242d157a5a464eb2120e6e71058016d355"
ATTESTATION_TWO_SHA256 = "c5cd8f88632bd9c80ab593ec1e60ba9bdecaee6eaf7c54c41cf1c37df0a11c8b"
REPORT_SCHEMA_VERSION = "ENTRY-QUALITY-STUDY-V1-REPORT-v1"
MANIFEST_SCHEMA_VERSION = "ENTRY-QUALITY-STUDY-V1-MANIFEST-v1"
POLICY_EPOCH_SCHEMA_VERSION = "ENTRY-QUALITY-STUDY-V1-POLICY-EPOCHS-v1"
CURRENT_M1_POLICY_EPOCH = "policy-a-resume-2026-08-26"


@dataclass(frozen=True, slots=True)
class EntryRecord:
    fill: LedgerFill
    cycle_id: str | None
    adapter_observation: Mapping[str, Any] | None


@dataclass(frozen=True, slots=True)
class PolicyEpoch:
    policy_epoch: str
    effective_from: datetime
    effective_to: datetime | None
    deployed_commit: str | None
    code_provenance_status: str
    policy_code_sha256: str | None
    workflow_run_id: int | None
    effective_from_evidence: str

    def contains(self, value: datetime) -> bool:
        observed = value.astimezone(timezone.utc)
        return self.effective_from <= observed and (
            self.effective_to is None or observed < self.effective_to
        )


def _aware(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return {}


def _report_hash(payload: Mapping[str, Any], field: str) -> str:
    return canonical_sha256({key: value for key, value in payload.items() if key != field})


def _load_policy_epochs(path: Path) -> tuple[list[PolicyEpoch], dict[str, Any]]:
    if not path.is_file():
        raise EntryQualityStudyError(f"policy epoch table is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != POLICY_EPOCH_SCHEMA_VERSION:
        raise EntryQualityStudyError("policy epoch table has an unsupported schema")
    expected = payload.get("manifest_sha256")
    observed = _report_hash(payload, "manifest_sha256")
    if expected != observed:
        raise EntryQualityStudyError(
            f"policy epoch table hash mismatch: expected {expected}, observed {observed}"
        )
    rows = payload.get("epochs")
    if not isinstance(rows, list) or not rows:
        raise EntryQualityStudyError("policy epoch table is empty")
    epochs: list[PolicyEpoch] = []
    for row in rows:
        item = _json_mapping(row)
        deployed_commit = item.get("deployed_commit")
        epoch = PolicyEpoch(
            policy_epoch=str(item.get("policy_epoch") or "").strip(),
            effective_from=_aware(item["effective_from"]),
            effective_to=(
                _aware(item["effective_to"])
                if item.get("effective_to") is not None else None
            ),
            deployed_commit=(
                str(deployed_commit).strip() if deployed_commit is not None else None
            ),
            code_provenance_status=str(
                item.get("code_provenance_status") or "AUDITED_DEPLOY"
            ).strip(),
            policy_code_sha256=(
                str(item["policy_code_sha256"]).strip()
                if item.get("policy_code_sha256") is not None else None
            ),
            workflow_run_id=(
                int(item["workflow_run_id"])
                if item.get("workflow_run_id") is not None else None
            ),
            effective_from_evidence=str(
                item.get("effective_from_evidence") or ""
            ).strip(),
        )
        if not epoch.policy_epoch:
            raise EntryQualityStudyError("policy epoch row is incomplete")
        if epoch.code_provenance_status == "AUDITED_DEPLOY":
            if (
                epoch.deployed_commit is None
                or len(epoch.deployed_commit) != 40
                or epoch.policy_code_sha256 is None
                or len(epoch.policy_code_sha256) != 64
                or epoch.workflow_run_id is None
            ):
                raise EntryQualityStudyError("audited policy epoch requires a full commit SHA")
        elif epoch.code_provenance_status == "UNRESOLVED_PRE_REPOSITORY":
            if (
                epoch.deployed_commit is not None
                or epoch.policy_code_sha256 is not None
                or epoch.workflow_run_id is not None
            ):
                raise EntryQualityStudyError("unresolved pre-repository epoch cannot claim a commit")
        else:
            raise EntryQualityStudyError(
                f"unsupported policy code provenance: {epoch.code_provenance_status}"
            )
        if not epoch.effective_from_evidence:
            raise EntryQualityStudyError("policy epoch requires effective_from evidence")
        epochs.append(epoch)
    epochs.sort(key=lambda item: item.effective_from)
    if len({item.policy_epoch for item in epochs}) != len(epochs):
        raise EntryQualityStudyError("policy epoch identifiers must be unique")
    for index, epoch in enumerate(epochs):
        expected_to = epochs[index + 1].effective_from if index + 1 < len(epochs) else None
        if epoch.effective_to != expected_to:
            raise EntryQualityStudyError(
                f"policy epoch intervals are not contiguous at {epoch.policy_epoch}"
            )
    return epochs, {
        "path": str(path),
        "sha256": sha256_file(path),
        "manifest_sha256": observed,
        "size_bytes": path.stat().st_size,
        "epochs": [asdict(item) for item in epochs],
    }


def _epoch_for(fill: LedgerFill, epochs: Sequence[PolicyEpoch]) -> str:
    matching = [epoch for epoch in epochs if epoch.contains(fill.executed_at)]
    if len(matching) != 1:
        raise EntryQualityStudyError(
            f"entry {fill.id} maps to {len(matching)} policy epochs"
        )
    expected = matching[0].policy_epoch
    persisted = str(fill.decision_snapshot.get("policy_epoch") or "").strip()
    if persisted and persisted != expected:
        raise EntryQualityStudyError(
            f"entry {fill.id} persisted epoch {persisted}, table resolves {expected}"
        )
    return persisted or expected


class EntryLedgerReader:
    def __init__(self, database: Database) -> None:
        self.database = database

    def read(self, experiment_code: str) -> tuple[dict[str, Any], list[EntryRecord]]:
        if not self.database.database_url:
            experiment, fills = LedgerReader(self.database).read(experiment_code)
            memory = getattr(self.database, "_r2d2_memory", None) or {}
            rows = [dict(item) for item in memory.get("trades", ())]
            cycles = {str(row.get("id")): row.get("cycle_id") for row in rows}
            observations = list(
                getattr(self.database, "_r2d2_entry_score_observations", ())
            )
            return experiment, self._records(fills, cycles, observations)

        with self.database.connection() as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            experiment_row = connection.execute(
                """
                SELECT id::text, code, status, starting_capital, start_date,
                       methodology_version, created_at, updated_at
                FROM r2d2_experiments
                WHERE code = %s
                """,
                (experiment_code,),
            ).fetchone()
            if not experiment_row:
                raise EntryQualityStudyError(f"R2D2 experiment not found: {experiment_code}")
            rows = connection.execute(
                """
                SELECT id::text, cycle_id::text, market, symbol, name, side, quantity,
                       signal_price_local, fill_price_local, fx_to_usd,
                       gross_value_usd, fees_usd, slippage_usd,
                       realized_pnl_usd, reason, decision_snapshot,
                       executed_at, quote_as_of
                FROM r2d2_trades
                WHERE experiment_id = %s AND side = 'BUY'
                ORDER BY executed_at, id
                """,
                (experiment_row[0],),
            ).fetchall()
            observations = connection.execute(
                """
                SELECT cycle_id::text, policy_epoch, decision_at, market, symbol,
                       source_references, valuation_comparisons, candidate_context,
                       candidate_sha256
                FROM r2d2_entry_score_observations
                WHERE experiment_id = %s
                ORDER BY decision_at, market, symbol
                """,
                (experiment_row[0],),
            ).fetchall()
            connection.rollback()
        experiment = dict(zip(
            (
                "id", "code", "status", "starting_capital", "start_date",
                "methodology_version", "created_at", "updated_at",
            ),
            experiment_row,
        ))
        keys = (
            "id", "cycle_id", "market", "symbol", "name", "side", "quantity",
            "signal_price_local", "fill_price_local", "fx_to_usd",
            "gross_value_usd", "fees_usd", "slippage_usd", "realized_pnl_usd",
            "reason", "decision_snapshot", "executed_at", "quote_as_of",
        )
        trade_rows = [dict(zip(keys, row)) for row in rows]
        fills = [_ledger_fill(row) for row in trade_rows]
        cycles = {str(row["id"]): row.get("cycle_id") for row in trade_rows}
        observation_keys = (
            "cycle_id", "policy_epoch", "decision_at", "market", "symbol",
            "source_references", "valuation_comparisons", "candidate_context",
            "candidate_sha256",
        )
        return experiment, self._records(
            fills,
            cycles,
            [dict(zip(observation_keys, row)) for row in observations],
        )

    @staticmethod
    def _records(
        fills: Sequence[LedgerFill],
        cycles: Mapping[str, Any],
        observations: Sequence[Mapping[str, Any]],
    ) -> list[EntryRecord]:
        by_key: dict[tuple[str, str, str], Mapping[str, Any]] = {}
        for row in observations:
            key = (str(row.get("cycle_id")), str(row.get("market")), str(row.get("symbol")))
            if key in by_key:
                raise EntryQualityStudyError(f"duplicate adapter observation for {key}")
            by_key[key] = row
        output = []
        for fill in fills:
            if fill.corrected or fill.strategy_excluded:
                continue
            cycle_id = cycles.get(fill.id)
            observation = by_key.get((str(cycle_id), fill.market, fill.symbol))
            output.append(EntryRecord(
                fill=fill,
                cycle_id=str(cycle_id) if cycle_id is not None else None,
                adapter_observation=observation,
            ))
        return output


class RawTradeMinuteReader:
    def __init__(self, root: Path) -> None:
        self.root = root

    def paths(self, session: date) -> list[Path]:
        names = (
            f"session_date={session.isoformat()}/feed=trade-part-*.ndjson",
            f"session_date={session.isoformat()}/feed=trade/*.ndjson",
        )
        output: list[Path] = []
        for pattern in names:
            output.extend(self.root.glob(pattern))
        return sorted(set(output))

    @staticmethod
    def _event_at(value: Any) -> datetime:
        observed = float(value)
        if observed > 1e17:
            observed /= 1e9
        elif observed > 1e14:
            observed /= 1e6
        elif observed > 1e11:
            observed /= 1e3
        return datetime.fromtimestamp(observed, tz=timezone.utc)

    def read(
        self,
        sessions: Sequence[date],
        symbols: set[str],
    ) -> tuple[dict[str, list[StudyBar]], list[dict[str, Any]], set[date]]:
        bars_by_key: dict[tuple[str, datetime], dict[str, float]] = {}
        evidence: list[dict[str, Any]] = []
        covered: set[date] = set()
        for session in sorted(set(sessions)):
            paths = self.paths(session)
            if not paths:
                continue
            covered.add(session)
            for path in paths:
                rows_seen = 0
                selected_rows = 0
                dark_pool_rows = 0
                with path.open("rt", encoding="utf-8") as handle:
                    for line_number, line in enumerate(handle, 1):
                        try:
                            wrapper = json.loads(line)
                            payload = _json_mapping(wrapper.get("payload_raw"))
                            rows_seen += 1
                            symbol = str(payload.get("s") or "")
                            if symbol not in symbols:
                                continue
                            if payload.get("dp") is True:
                                dark_pool_rows += 1
                                continue
                            price = float(payload["p"])
                            volume = max(0.0, float(payload.get("v") or 0.0))
                            event_at = self._event_at(payload["t"])
                        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                            raise EntryQualityStudyError(
                                f"invalid RAW trade row {path}:{line_number}"
                            ) from exc
                        local = event_at.astimezone(NEW_YORK)
                        local_time = local.time().replace(tzinfo=None)
                        if local.date() != session or not (REGULAR_OPEN <= local_time < REGULAR_CLOSE):
                            continue
                        selected_rows += 1
                        minute = event_at.replace(second=0, microsecond=0)
                        key = (symbol, minute)
                        current = bars_by_key.get(key)
                        if current is None:
                            bars_by_key[key] = {
                                "open": price,
                                "high": price,
                                "low": price,
                                "close": price,
                                "volume": volume,
                                "first_at": event_at.timestamp(),
                                "last_at": event_at.timestamp(),
                            }
                        else:
                            current["high"] = max(current["high"], price)
                            current["low"] = min(current["low"], price)
                            current["volume"] += volume
                            event_timestamp = event_at.timestamp()
                            if event_timestamp < current["first_at"]:
                                current["first_at"] = event_timestamp
                                current["open"] = price
                            if event_timestamp >= current["last_at"]:
                                current["last_at"] = event_timestamp
                                current["close"] = price
                evidence.append({
                    "session_date": session.isoformat(),
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "rows_seen": rows_seen,
                    "selected_rows": selected_rows,
                    "dark_pool_rows_excluded": dark_pool_rows,
                })
        bars: dict[str, list[StudyBar]] = {symbol: [] for symbol in symbols}
        for (symbol, minute), row in sorted(bars_by_key.items()):
            bars[symbol].append(StudyBar(
                symbol=symbol,
                start_at=minute,
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            ))
        return bars, evidence, covered


def _merge_bars(
    destinations: dict[str, list[StudyBar]],
    additions: Mapping[str, Sequence[StudyBar]],
) -> None:
    for symbol, rows in additions.items():
        existing = {bar.start_at: bar for bar in destinations.setdefault(symbol, [])}
        for bar in rows:
            if bar.start_at in existing:
                raise EntryQualityStudyError(
                    f"duplicate bar across input sources: {symbol} {bar.start_at.isoformat()}"
                )
            existing[bar.start_at] = bar
        destinations[symbol] = [existing[key] for key in sorted(existing)]


def _read_price_paths(
    settings: Settings,
    records: Sequence[EntryRecord],
) -> tuple[dict[str, list[StudyBar]], dict[str, Any]]:
    sessions = sorted({record.fill.executed_at.astimezone(NEW_YORK).date() for record in records})
    symbols = {record.fill.symbol for record in records} | {"QQQ"}
    aggregate_reader = MinuteAggregateReader(settings.day_d_dataset_root)
    try:
        available = dict(aggregate_reader.available())
    except ExitPolicyStudyError:
        available = {}
    aggregate_sources = [(session, available[session]) for session in sessions if session in available]
    bars: dict[str, list[StudyBar]] = {symbol: [] for symbol in symbols}
    aggregate_evidence: list[dict[str, Any]] = []
    if aggregate_sources:
        aggregate_bars, aggregate_evidence = aggregate_reader.read(aggregate_sources, symbols)
        _merge_bars(bars, aggregate_bars)
    missing_sessions = [session for session in sessions if session not in available]
    raw_reader = RawTradeMinuteReader(settings.r2d2_microstructure_raw_dir)
    raw_bars, raw_evidence, raw_covered = raw_reader.read(missing_sessions, symbols)
    _merge_bars(bars, raw_bars)
    return bars, {
        "aggregate_sources": aggregate_evidence,
        "raw_trade_sources": raw_evidence,
        "aggregate_sessions": [session.isoformat() for session, _path in aggregate_sources],
        "raw_sessions": [session.isoformat() for session in sorted(raw_covered)],
        "missing_sessions": [
            session.isoformat()
            for session in missing_sessions
            if session not in raw_covered
        ],
        "trade_bars_only": True,
        "raw_dark_pool_excluded": True,
        "raw_processor_invoked": False,
    }


def _adapter_causal(record: EntryRecord) -> bool | None:
    observation = record.adapter_observation
    if observation is None:
        return None
    decision_at = _aware(observation["decision_at"])
    if decision_at > record.fill.executed_at:
        return False
    references = _json_mapping(observation.get("source_references"))
    for value in references.values():
        reference = _json_mapping(value)
        if reference.get("status") != "eligible":
            continue
        published = _aware(reference["published_at"])
        available = _aware(reference["available_at"])
        if published > decision_at or available > decision_at:
            return False
    return True


def _coverage_gate(
    records: Sequence[EntryRecord],
    bars: Mapping[str, Sequence[StudyBar]],
    epochs: Mapping[str, str],
) -> dict[str, Any]:
    dimensions = (
        "persisted_stop",
        "entry_route",
        "canonical_scores",
        "atr",
        "symbol_vwap_ema8",
        "quote_age",
        "future_trade_bars",
        "qqq_regime",
        "adapter_causal_sources",
    )
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    qqq = bars.get("QQQ", ())
    for record in records:
        fill = record.fill
        epoch = epochs[fill.id]
        session = fill.executed_at.astimezone(NEW_YORK).date().isoformat()
        key = (session, fill.market, epoch)
        row = grouped.setdefault(key, {
            "session_date": session,
            "market": fill.market,
            "policy_epoch": epoch,
            "entry_count": 0,
            "available": {dimension: 0 for dimension in dimensions},
        })
        row["entry_count"] += 1
        technical = _json_mapping(fill.decision_snapshot.get("technical_indicators"))
        scores = (
            fill.decision_snapshot.get("composite_score"),
            fill.decision_snapshot.get("fundamental_score"),
            fill.decision_snapshot.get("technical_score"),
            fill.decision_snapshot.get("risk_score"),
        )
        entry_minute = fill.executed_at.astimezone(timezone.utc).replace(second=0, microsecond=0)
        session_date = fill.executed_at.astimezone(NEW_YORK).date()
        future_bars = any(
            bar.session_date == session_date and bar.start_at > entry_minute
            for bar in bars.get(fill.symbol, ())
        )
        values = {
            "persisted_stop": _positive(fill.decision_snapshot.get("stop_price")),
            "entry_route": entry_route(fill) != "unclassified",
            "canonical_scores": all(_finite(value) for value in scores),
            "atr": _positive(technical.get("atr")) or _positive(technical.get("atr_percent")),
            "symbol_vwap_ema8": (
                _positive(technical.get("vwap")) and _positive(technical.get("ema8"))
            ),
            "quote_age": fill.quote_as_of is not None,
            "future_trade_bars": future_bars,
            "qqq_regime": entry_regime(fill, qqq) is not None,
            "adapter_causal_sources": _adapter_causal(record) is True,
        }
        for dimension, available in values.items():
            if available:
                row["available"][dimension] += 1
    output = []
    for key in sorted(grouped):
        row = grouped[key]
        count = row["entry_count"]
        row["coverage_percent"] = {
            dimension: row["available"][dimension] / count * 100.0
            for dimension in dimensions
        }
        output.append(row)
    stretch_values = [entry_stretch(record.fill) for record in records]
    finite_stretch = sorted(value for value in stretch_values if value is not None)
    quartile = None
    if finite_stretch:
        index = max(0, min(len(finite_stretch) - 1, (3 * len(finite_stretch) + 3) // 4 - 1))
        quartile = finite_stretch[index]
    return {
        "published_before_outcomes": True,
        "rows": output,
        "missing_field_rule": "dimension absent; no proxy or retrospective reconstruction",
        "stretch_upper_quartile": quartile,
        "stretch_definition": "min(signal/VWAP-1, signal/EMA8-1)",
    }


def _finite(value: Any) -> bool:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False
    return parsed == parsed and parsed not in (float("inf"), float("-inf"))


def _positive(value: Any) -> bool:
    return _finite(value) and float(value) > 0


def _score_deciles(
    rows: Sequence[EntryMeasurement],
    field: str,
) -> dict[str, Any]:
    scored = sorted(
        (row for row in rows if getattr(row, field) is not None),
        key=lambda row: (float(getattr(row, field)), row.entry_id),
    )
    grouped: dict[str, list[EntryMeasurement]] = defaultdict(list)
    total = len(scored)
    for index, row in enumerate(scored):
        decile = min(10, int(index * 10 / total) + 1) if total else 1
        grouped[f"D{decile}"].append(row)
    return {key: summarize_cell(value) for key, value in sorted(grouped.items())}


def _stretch_groups(
    rows: Sequence[EntryMeasurement],
    upper_quartile: float | None,
) -> dict[str, Any]:
    if upper_quartile is None:
        return {"unavailable": summarize_cell(rows)}
    return {
        "upper_quartile": summarize_cell([
            row for row in rows
            if row.stretch is not None and row.stretch >= upper_quartile
        ]),
        "below_upper_quartile": summarize_cell([
            row for row in rows
            if row.stretch is not None and row.stretch < upper_quartile
        ]),
        "unavailable": summarize_cell([row for row in rows if row.stretch is None]),
    }


def _rank_axis_cells(axes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for axis, cells in axes.items():
        for cell, summary in cells.items():
            primary = _json_mapping(summary.get("primary_plus_60m"))
            mean = primary.get("mean_percent")
            if not _finite(mean):
                continue
            rows.append({
                "axis": axis,
                "cell": cell,
                "observed_count": int(primary.get("observed_count") or 0),
                "mean_plus_60m_percent": float(mean),
                "bootstrap_ci95_percent": primary.get("bootstrap_ci95_percent"),
            })
    ordered = sorted(
        rows,
        key=lambda row: (row["mean_plus_60m_percent"], row["axis"], row["cell"]),
    )
    return {
        "worst": ordered[:10],
        "best": list(reversed(ordered[-10:])),
        "descriptive_only": True,
    }


def _epoch_reports(rows: Sequence[EntryMeasurement]) -> dict[str, Any]:
    by_epoch: dict[str, list[EntryMeasurement]] = defaultdict(list)
    for row in rows:
        by_epoch[row.policy_epoch].append(row)
    output: dict[str, Any] = {}
    for epoch, values in sorted(by_epoch.items()):
        stretch_quartile = frozen_stretch_upper_quartile(values)
        axes = {
            "valuation_basis": report_by_dimension(values, lambda row: row.valuation_basis),
            "route": report_by_dimension(values, lambda row: row.route),
            "entry_hour_brt": report_by_dimension(values, lambda row: str(row.entry_hour_brt)),
            "regime": report_by_dimension(values, lambda row: row.regime or "unavailable"),
            "canonical_composite_decile": _score_deciles(values, "composite_score"),
            "fundamental_score_decile": _score_deciles(values, "fundamental_score"),
            "technical_score_decile": _score_deciles(values, "technical_score"),
            "buy_in_distance_decile": _score_deciles(values, "buy_in_distance_percent"),
            "risk_score_decile": _score_deciles(values, "risk_score"),
            "atr_class": report_by_dimension(values, lambda row: atr_class(row.atr_percent)),
            "quote_age_class": report_by_dimension(
                values,
                lambda row: quote_age_class(row.quote_age_seconds),
            ),
            "stretch_class": _stretch_groups(values, stretch_quartile),
        }
        output[epoch] = {
            "classification": (
                "PILOT" if len({row.session_date for row in values}) < 15 else "FULL_SAMPLE"
            ),
            "overall": summarize_cell(values),
            "axes": axes,
            "axis_contracts": {
                "atr_class": "existing strategy volatility-score bands: <0.25, 0.25-3.5, >3.5-5, >5 percent",
                "quote_age_class": "existing platform freshness thresholds: fresh <=5s, aging <=30s, stale >30s",
                "score_deciles": "ranked within policy epoch with entry_id deterministic tie-break",
            },
            "stretch_upper_quartile": stretch_quartile,
            "cell_ranking": _rank_axis_cells(axes),
            "hypotheses": hypothesis_reports(
                values,
                stretch_upper_quartile=stretch_quartile,
            ),
        }
    return output


def _build_inputs(
    *,
    settings: Settings,
    policy_epochs_path: Path,
    spec_path: Path | None,
    attestation_path: Path | None,
    attestation_two_path: Path | None,
) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    spec = require_frozen_document(
        spec_path or root / "docs" / "ENTRY_QUALITY_STUDY_V1.md",
        SPEC_SHA256,
        "frozen ENTRY_QUALITY_STUDY_V1 spec",
    )
    attestation = require_frozen_document(
        attestation_path or root / "docs" / "ENTRY_QUALITY_STUDY_V1_RUNNER_ATTESTATION_1.md",
        ATTESTATION_SHA256,
        "signed entry-study runner attestation",
    )
    attestation_two = require_frozen_document(
        attestation_two_path
        or root / "docs" / "ENTRY_QUALITY_STUDY_V1_RUNNER_ATTESTATION_2.md",
        ATTESTATION_TWO_SHA256,
        "signed entry-study runner attestation 2",
    )
    epochs, epoch_evidence = _load_policy_epochs(policy_epochs_path)
    database = Database(settings)
    experiment, records = EntryLedgerReader(database).read(settings.r2d2_experiment_code)
    if not records:
        raise EntryQualityStudyError("no organic BUY rows are available")
    epoch_by_entry = {record.fill.id: _epoch_for(record.fill, epochs) for record in records}
    bars, bar_evidence = _read_price_paths(settings, records)
    coverage = _coverage_gate(records, bars, epoch_by_entry)
    gate = reconcile_entry_gate(
        [record.fill for record in records],
        bars,
        constructed_entry_count=len(records),
    )
    return {
        "spec": spec,
        "attestation": attestation,
        "attestation_two": attestation_two,
        "policy_epochs": epoch_evidence,
        "experiment": experiment,
        "records": records,
        "epoch_by_entry": epoch_by_entry,
        "bars": bars,
        "bar_evidence": bar_evidence,
        "coverage": coverage,
        "entry_gate": gate,
    }


def build_plan(
    *,
    settings: Settings,
    policy_epochs_path: Path,
    spec_path: Path | None = None,
    attestation_path: Path | None = None,
    attestation_two_path: Path | None = None,
) -> dict[str, Any]:
    inputs = _build_inputs(
        settings=settings,
        policy_epochs_path=policy_epochs_path,
        spec_path=spec_path,
        attestation_path=attestation_path,
        attestation_two_path=attestation_two_path,
    )
    return {
        "command": "plan",
        "read_only": True,
        "external_api_calls": 0,
        "report_written": False,
        "entry_count": len(inputs["records"]),
        "session_count": len({
            record.fill.executed_at.astimezone(NEW_YORK).date()
            for record in inputs["records"]
        }),
        "policy_epoch_count": len(inputs["policy_epochs"]["epochs"]),
        "coverage_gate": inputs["coverage"],
        "entry_consistency_gate": inputs["entry_gate"],
        "price_sources": inputs["bar_evidence"],
        "run_window": "00:00-08:00 America/Sao_Paulo",
        "expected_current_dry_run_classification": "INSUFFICIENT_SAMPLE",
    }


def build_report(
    *,
    settings: Settings,
    policy_epochs_path: Path,
    generated_at: datetime | None = None,
    spec_path: Path | None = None,
    attestation_path: Path | None = None,
    attestation_two_path: Path | None = None,
    dry_run: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    generated_at = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    inputs = _build_inputs(
        settings=settings,
        policy_epochs_path=policy_epochs_path,
        spec_path=spec_path,
        attestation_path=attestation_path,
        attestation_two_path=attestation_two_path,
    )
    records: list[EntryRecord] = inputs["records"]
    gate = inputs["entry_gate"]
    gate_censorship = gate["g3_coverage_censorship"]
    violation_ids = set(gate_censorship["violation_entry_ids"])
    unavailable_ids = set(gate_censorship["bar_unavailable_entry_ids"])
    censored_ids = violation_ids | unavailable_ids
    measurements: list[EntryMeasurement] = []
    measurement_censoring: dict[str, int] = defaultdict(int)
    if gate["passed"]:
        for record in records:
            fill = record.fill
            if fill.id in violation_ids:
                measurement_censoring["market_compatibility_violation"] += 1
                continue
            if fill.id in unavailable_ids:
                measurement_censoring["bar_unavailable"] += 1
                continue
            try:
                measurements.append(measure_entry(
                    fill,
                    inputs["bars"].get(fill.symbol, ()),
                    policy_epoch=inputs["epoch_by_entry"][fill.id],
                    qqq_bars=inputs["bars"].get("QQQ", ()),
                ))
            except EntryQualityStudyError as exc:
                reason = str(exc)
                if "persisted stop" in reason:
                    measurement_censoring["missing_persisted_stop"] += 1
                elif "post-entry bars" in reason:
                    measurement_censoring["missing_future_trade_bars"] += 1
                else:
                    measurement_censoring["measurement_infeasible"] += 1
    epoch_reports = _epoch_reports(measurements) if gate["passed"] else {}
    hypothesis_statuses = [
        hypothesis["status"]
        for epoch in epoch_reports.values()
        for hypothesis in epoch["hypotheses"].values()
    ]
    classification = (
        "BLOCKED_BY_ENTRY_CONSISTENCY_GATE"
        if not gate["passed"]
        else "INSUFFICIENT_SAMPLE"
        if not hypothesis_statuses or all(status == "INSUFFICIENT_SAMPLE" for status in hypothesis_statuses)
        else "PILOT"
    )

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": generated_at,
        "dry_run": dry_run,
        "read_only": True,
        "external_api_calls": 0,
        "frozen_contract": {
            "spec": inputs["spec"],
            "runner_attestation": inputs["attestation"],
            "runner_attestation_2": inputs["attestation_two"],
            "policy_epochs": inputs["policy_epochs"],
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
        },
        "ledger": {
            "organic_buy_count": len(records),
            "canonical_json_sha256": canonical_sha256([
                asdict(record.fill) for record in records
            ]),
            "first_executed_at": min(record.fill.executed_at for record in records),
            "last_executed_at": max(record.fill.executed_at for record in records),
        },
        "price_sources": inputs["bar_evidence"],
        "price_source_manifest_sha256": canonical_sha256(inputs["bar_evidence"]),
    }
    manifest["manifest_sha256"] = _report_hash(manifest, "manifest_sha256")

    current_epoch_summary = (
        epoch_reports[CURRENT_M1_POLICY_EPOCH]["overall"]
        if CURRENT_M1_POLICY_EPOCH in epoch_reports else None
    )
    current_epoch_barrier = (
        _json_mapping(current_epoch_summary.get("barrier"))
        if current_epoch_summary is not None else {}
    )
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": generated_at,
        "dry_run": dry_run,
        "classification": classification,
        "analysis_interpretable": gate["passed"],
        "governance": {
            "read_only": True,
            "external_api_calls": 0,
            "consumer_change_authorized": False,
            "strategy_change_authorized": False,
            "official_tp_replacement_authorized": False,
            "policy_epochs_never_pooled_for_decision": True,
            "policy_code_provenance_complete": all(
                epoch["code_provenance_status"] == "AUDITED_DEPLOY"
                for epoch in inputs["policy_epochs"]["epochs"]
            ),
            "unresolved_policy_epochs": [
                epoch["policy_epoch"]
                for epoch in inputs["policy_epochs"]["epochs"]
                if epoch["code_provenance_status"] != "AUDITED_DEPLOY"
            ],
        },
        "manifest_sha256": manifest["manifest_sha256"],
        "experiment": {
            "id": str(inputs["experiment"]["id"]),
            "code": str(inputs["experiment"]["code"]),
            "status": str(inputs["experiment"]["status"]),
        },
        "coverage_gate_before_outcomes": inputs["coverage"],
        "entry_consistency_gate": gate,
        "cohort": {
            "constructed_entry_count": len(records),
            "market_compatibility_censored_count": len(censored_ids),
            "numeric_violation_censored_count": len(violation_ids),
            "bar_unavailable_censored_count": len(unavailable_ids),
            "measured_entry_count": len(measurements),
            "measurement_censoring": dict(sorted(measurement_censoring.items())),
        },
        "policy_epoch_results": epoch_reports,
        "kill_criterion_m1_current_epoch": {
            "policy_epoch": CURRENT_M1_POLICY_EPOCH,
            "available": CURRENT_M1_POLICY_EPOCH in epoch_reports,
            "classification": (
                epoch_reports[CURRENT_M1_POLICY_EPOCH]["classification"]
                if CURRENT_M1_POLICY_EPOCH in epoch_reports else "INSUFFICIENT_SAMPLE"
            ),
            "summary": (
                current_epoch_summary
            ),
            "p_hat_ucb_98_75": current_epoch_barrier.get("p_hat_ucb_98_75"),
            "p_hat_cons_ucb_98_75": current_epoch_barrier.get(
                "p_hat_cons_ucb_98_75"
            ),
            "cross_epoch_pooling": False,
        },
        "entry_measurements": [row.as_dict() for row in measurements],
        "limitations": [
            "All estimates are stratified by policy epoch; no cross-epoch decision estimator exists.",
            "The pre-repository epoch has unresolved code provenance and cannot support a decision-ready claim.",
            "The entry minute is excluded because intraminute ordering is unknowable.",
            "A horizon beyond the same-session close is censored, never replaced by close.",
            "The 50% barrier benchmark is descriptive under symmetry, not a theorem for minute bars.",
            "Fewer than 15 sessions or 30 decided entries per compared cell is INSUFFICIENT_SAMPLE.",
        ],
    }
    report["report_sha256"] = _report_hash(report, "report_sha256")
    return manifest, report


def require_off_hours(value: datetime) -> None:
    local = value.astimezone(ZoneInfo("America/Sao_Paulo"))
    if not 0 <= local.hour < 8:
        raise EntryQualityStudyError(
            "published study runs are restricted to 00:00-08:00 America/Sao_Paulo"
        )


def write_report_package(output: Path, manifest: Mapping[str, Any], report: Mapping[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    write_immutable_json(output / "manifest.json", manifest)
    write_immutable_json(output / "report.json", report)
    sums = {
        "manifest.json": sha256_file(output / "manifest.json"),
        "report.json": sha256_file(output / "report.json"),
    }
    write_immutable_json(output / "SHA256SUMS.json", sums)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only runner for frozen ENTRY_QUALITY_STUDY_V1",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("plan", "dry-run", "run"):
        child = subparsers.add_parser(command)
        child.add_argument("--spec", type=Path)
        child.add_argument("--attestation", type=Path)
        child.add_argument("--attestation-two", type=Path)
        child.add_argument("--policy-epochs", type=Path, required=True)
        if command in {"dry-run", "run"}:
            child.add_argument(
                "--output",
                type=Path,
                required=command == "run",
                help="optional immutable evidence package for dry-run; required for run",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = get_settings()
    if args.command == "plan":
        payload = build_plan(
            settings=settings,
            policy_epochs_path=args.policy_epochs,
            spec_path=args.spec,
            attestation_path=args.attestation,
            attestation_two_path=args.attestation_two,
        )
        print(json.dumps(payload, sort_keys=True, indent=2, default=str))
        return 0
    if args.command == "run":
        require_off_hours(datetime.now(timezone.utc))
    manifest, report = build_report(
        settings=settings,
        policy_epochs_path=args.policy_epochs,
        spec_path=args.spec,
        attestation_path=args.attestation,
        attestation_two_path=args.attestation_two,
        dry_run=args.command == "dry-run",
    )
    output = getattr(args, "output", None)
    if output is not None:
        write_report_package(output, manifest, report)
    print(json.dumps({
        "command": args.command,
        "classification": report["classification"],
        "analysis_interpretable": report["analysis_interpretable"],
        "manifest_sha256": manifest["manifest_sha256"],
        "report_sha256": report["report_sha256"],
        "output": str(output) if output is not None else None,
    }, sort_keys=True))
    return 0 if report["analysis_interpretable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
