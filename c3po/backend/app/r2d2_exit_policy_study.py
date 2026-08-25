from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .config import Settings, get_settings
from .database import Database
from .r2d2_exit_policy_engine import (
    BOOTSTRAP_ITERATIONS,
    BOOTSTRAP_SEED,
    PANEL_I_POLICIES,
    PANEL_II_POLICIES,
    ConsistencyGateError,
    Episode,
    ExitPolicyStudyError,
    LedgerFill,
    StudyBar,
    build_episodes,
    excursion_report,
    observed_outcome,
    panel_report,
    real_excursions,
    reconcile_binding_gate,
    simulate_mechanical,
    simulate_overlay,
)


NEW_YORK = ZoneInfo("America/New_York")
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
SPEC_SHA256 = "21882372220d55aa01c0a23b9288d75788d25b1187c01b4954e0c500ec0216a2"
DELIVERABLE_ZERO_SHA256 = "ae83428ac0444329efc7405e06078c144b575a0909699e15b16ce5a26de20098"
FROZEN_POLICY_COMMIT = "39ff427fd2f1fa0f42141776921a63651508495f"
FROZEN_METHODOLOGY = "R2D2-HYBRID-V27-15M-LIQUIDITY-FLOOR"
REPORT_SCHEMA_VERSION = "EXIT-POLICY-STUDY-V1.1-REPORT-v1"
TERMINAL_SESSIONS = 10
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _json_ready(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_immutable_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(
        _json_ready(payload),
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == encoded:
            return
        raise FileExistsError(f"immutable report already exists with different bytes: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() == encoded:
                return
            raise FileExistsError(
                f"immutable report appeared concurrently with different bytes: {path}"
            )
    finally:
        temporary.unlink(missing_ok=True)


def require_frozen_document(path: Path, expected_sha256: str, name: str) -> dict[str, Any]:
    if not path.is_file():
        raise ExitPolicyStudyError(f"{name} is missing: {path}")
    observed = sha256_file(path)
    if observed != expected_sha256:
        raise ExitPolicyStudyError(
            f"{name} hash mismatch: expected {expected_sha256}, observed {observed}"
        )
    return {"path": str(path), "sha256": observed, "size_bytes": path.stat().st_size}


class LedgerReader:
    def __init__(self, database: Database) -> None:
        self.database = database

    def read(self, experiment_code: str) -> tuple[dict[str, Any], list[LedgerFill]]:
        if not self.database.database_url:
            memory = getattr(self.database, "_r2d2_memory", None) or {}
            experiment = memory.get("experiment")
            if not experiment or experiment.get("code") != experiment_code:
                raise ExitPolicyStudyError(f"R2D2 experiment not found: {experiment_code}")
            rows = [dict(item) for item in memory.get("trades", ())]
            return dict(experiment), [_ledger_fill(row) for row in rows]
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
                raise ExitPolicyStudyError(f"R2D2 experiment not found: {experiment_code}")
            rows = connection.execute(
                """
                SELECT id::text, market, symbol, name, side, quantity,
                       signal_price_local, fill_price_local, fx_to_usd,
                       gross_value_usd, fees_usd, slippage_usd,
                       realized_pnl_usd, reason, decision_snapshot,
                       executed_at, quote_as_of
                FROM r2d2_trades
                WHERE experiment_id = %s
                ORDER BY executed_at, id
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
            "id", "market", "symbol", "name", "side", "quantity",
            "signal_price_local", "fill_price_local", "fx_to_usd",
            "gross_value_usd", "fees_usd", "slippage_usd",
            "realized_pnl_usd", "reason", "decision_snapshot",
            "executed_at", "quote_as_of",
        )
        return experiment, [_ledger_fill(dict(zip(keys, row))) for row in rows]


def _aware(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ledger_fill(row: Mapping[str, Any]) -> LedgerFill:
    snapshot = row.get("decision_snapshot")
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    return LedgerFill(
        id=str(row["id"]),
        market=str(row["market"]),
        symbol=str(row["symbol"]),
        name=str(row.get("name") or row["symbol"]),
        side=str(row["side"]),
        quantity=float(row["quantity"]),
        signal_price_local=float(row["signal_price_local"]),
        fill_price_local=float(row["fill_price_local"]),
        fx_to_usd=float(row["fx_to_usd"]),
        gross_value_usd=float(row["gross_value_usd"]),
        fees_usd=float(row["fees_usd"]),
        slippage_usd=float(row["slippage_usd"]),
        realized_pnl_usd=(
            float(row["realized_pnl_usd"])
            if row.get("realized_pnl_usd") is not None else None
        ),
        reason=str(row.get("reason") or ""),
        decision_snapshot=dict(snapshot or {}),
        executed_at=_aware(row["executed_at"]),
        quote_as_of=_aware(row["quote_as_of"]),
    )


class MinuteAggregateReader:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.dataset_root = root / "provider=massive" / "dataset=minute_aggregates"

    def available(self) -> list[tuple[date, Path]]:
        output = []
        for path in sorted(self.dataset_root.glob("session_date=*/source.csv.gz")):
            try:
                session = date.fromisoformat(path.parent.name.split("=", 1)[1])
            except (IndexError, ValueError) as exc:
                raise ExitPolicyStudyError(f"invalid minute-aggregate path: {path}") from exc
            output.append((session, path))
        if not output:
            raise ExitPolicyStudyError(f"no Day D minute aggregates found under {self.dataset_root}")
        return output

    def selected_sources(
        self,
        episodes: Sequence[Episode],
        *,
        prior_sessions: int = 20,
    ) -> list[tuple[date, Path]]:
        available = self.available()
        eligible = [
            item for item in episodes
            if item.market in {"NASDAQ", "NYSE"} and item.closed_at is not None
        ]
        if not eligible:
            raise ExitPolicyStudyError("no closed US episodes are available")
        earliest = min(item.entry_session for item in eligible)
        latest = max(item.exit_session for item in eligible if item.exit_session is not None)
        sessions = [session for session, _path in available]
        before = [session for session in sessions if session < earliest]
        start = before[-prior_sessions] if len(before) >= prior_sessions else sessions[0]
        usable = [item for item in available if start <= item[0] <= latest]
        if not usable:
            raise ExitPolicyStudyError("minute aggregates do not overlap the ledger")
        return usable

    def read(
        self,
        sources: Sequence[tuple[date, Path]],
        symbols: set[str],
    ) -> tuple[dict[str, list[StudyBar]], list[dict[str, Any]]]:
        bars: dict[str, list[StudyBar]] = {symbol: [] for symbol in symbols}
        evidence: list[dict[str, Any]] = []
        seen: set[tuple[str, datetime]] = set()
        for session, path in sources:
            metadata_path = path.with_name(f"{path.name}.metadata.json")
            if not metadata_path.is_file():
                raise ExitPolicyStudyError(f"minute aggregate metadata is missing: {metadata_path}")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            observed_size = path.stat().st_size
            if int(metadata.get("content_length", -1)) != observed_size:
                raise ExitPolicyStudyError(f"minute aggregate size mismatch: {path}")
            observed_sha = sha256_file(path)
            if metadata.get("sha256") != observed_sha:
                raise ExitPolicyStudyError(f"minute aggregate checksum mismatch: {path}")
            evidence.append({
                "session_date": session.isoformat(),
                "path": str(path.relative_to(self.root)),
                "size_bytes": observed_size,
                "sha256": observed_sha,
            })
            with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                required = {"ticker", "window_start", "open", "high", "low", "close", "volume"}
                if not reader.fieldnames or not required.issubset(reader.fieldnames):
                    missing = sorted(required - set(reader.fieldnames or ()))
                    raise ExitPolicyStudyError(f"minute aggregate columns missing in {path}: {missing}")
                for row in reader:
                    symbol = str(row.get("ticker") or "")
                    if symbol not in symbols:
                        continue
                    try:
                        start_at = datetime.fromtimestamp(
                            int(str(row["window_start"])) / 1_000_000_000,
                            tz=timezone.utc,
                        )
                        local_time = start_at.astimezone(NEW_YORK).time().replace(tzinfo=None)
                        if not (REGULAR_OPEN <= local_time < REGULAR_CLOSE):
                            continue
                        bar = StudyBar(
                            symbol=symbol,
                            start_at=start_at,
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=float(row["volume"]),
                        )
                    except (TypeError, ValueError) as exc:
                        raise ExitPolicyStudyError(f"invalid minute aggregate row in {path}") from exc
                    if bar.session_date != session:
                        raise ExitPolicyStudyError(
                            f"bar session mismatch in {path}: {bar.session_date} != {session}"
                        )
                    key = (symbol, start_at)
                    if key in seen:
                        raise ExitPolicyStudyError(f"duplicate minute aggregate: {symbol} {start_at}")
                    seen.add(key)
                    bars[symbol].append(bar)
        for values in bars.values():
            values.sort(key=lambda item: item.start_at)
        return bars, evidence


def _ledger_evidence(fills: Sequence[LedgerFill]) -> dict[str, Any]:
    payload = [asdict(fill) for fill in fills]
    return {
        "row_count": len(fills),
        "canonical_json_sha256": canonical_sha256(payload),
        "first_executed_at": min((fill.executed_at for fill in fills), default=None),
        "last_executed_at": max((fill.executed_at for fill in fills), default=None),
        "filter": "all experiment rows; correction rows excluded during episode construction",
    }


def _base_cohort(episodes: Sequence[Episode], latest_bar_session: date) -> tuple[list[Episode], dict[str, int]]:
    counts: dict[str, int] = {
        "open": 0,
        "administrative": 0,
        "unsupported_market": 0,
        "beyond_bar_cutoff": 0,
    }
    output = []
    for episode in episodes:
        if not episode.closed:
            counts["open"] += 1
        elif episode.strategy_excluded:
            counts["administrative"] += 1
        elif episode.market not in {"NASDAQ", "NYSE"}:
            counts["unsupported_market"] += 1
        elif episode.exit_session and episode.exit_session > latest_bar_session:
            counts["beyond_bar_cutoff"] += 1
        else:
            output.append(episode)
    return output, counts


def _coverage_cohort(
    episodes: Sequence[Episode],
    bars: Mapping[str, Sequence[StudyBar]],
) -> tuple[list[Episode], dict[str, int]]:
    covered = []
    censored = {"missing_fill_minute_bar": 0, "empty_episode_price_path": 0}
    for episode in episodes:
        symbol_bars = list(bars.get(episode.symbol, ()))
        available_minutes = {bar.start_at for bar in symbol_bars}
        if not symbol_bars:
            censored["empty_episode_price_path"] += 1
            continue
        missing_fill = False
        for fill in episode.fills:
            minute = fill.executed_at.astimezone(timezone.utc).replace(second=0, microsecond=0)
            if not any(
                minute + timedelta(minutes=offset) in available_minutes
                for offset in (0, -1, 1)
            ):
                missing_fill = True
                break
        if missing_fill:
            censored["missing_fill_minute_bar"] += 1
            continue
        covered.append(episode)
    return covered, censored


def _run_panel_i(
    episodes: Sequence[Episode],
    bars: Mapping[str, Sequence[StudyBar]],
    starting_capital: float,
) -> tuple[dict[str, Any], list[Episode], dict[str, int]]:
    outcomes: dict[str, list[Any]] = {policy: [] for policy in PANEL_I_POLICIES}
    cohort: list[Episode] = []
    censored: dict[str, int] = {"simulation_infeasible": 0}
    for episode in episodes:
        path = list(bars.get(episode.symbol, ()))
        try:
            per_policy = {"A": observed_outcome(episode, path)}
            for policy in PANEL_I_POLICIES[1:]:
                per_policy[policy] = simulate_overlay(episode, path, policy)
        except ExitPolicyStudyError:
            censored["simulation_infeasible"] += 1
            continue
        cohort.append(episode)
        for policy, outcome in per_policy.items():
            outcomes[policy].append(outcome)
    if not cohort:
        raise ExitPolicyStudyError("Panel I common cohort is empty")
    report = panel_report(
        outcomes,
        baseline_policy="A",
        starting_capital=starting_capital,
    )
    report["binding_interpretation"] = True
    report["overlay_rule"] = "challengers may only anticipate observed A exits"
    report["parameters"] = {
        "A": "observed ledger sequence",
        "B": {"take_profit_net_percent": 0.15},
        "B_PRIME": {"take_profit_net_percent": 0.30},
        "C": {"arm_net_percent": 0.30, "stop_net_percent": 0.0},
        "C_PRIME": {"arm_net_percent": 0.30, "trailing_from_peak_percent": 0.40},
    }
    report["observed_baseline"] = {
        "ledger_exact": True,
        "real_partial_exits_preserved_before_overlay": True,
        "opportunity_cost_rotation_included_in_A_sequence": True,
        "corrections_excluded": True,
        "operator_wind_down_excluded_from_strategy_cohort": True,
    }
    return report, cohort, censored


def _run_panel_ii(
    episodes: Sequence[Episode],
    bars: Mapping[str, Sequence[StudyBar]],
    starting_capital: float,
) -> tuple[dict[str, Any] | None, dict[str, int]]:
    outcomes: dict[str, list[Any]] = {policy: [] for policy in PANEL_II_POLICIES}
    censored: dict[str, int] = {"simulation_infeasible_or_window_censored": 0}
    for episode in episodes:
        path = list(bars.get(episode.symbol, ()))
        per_policy = {
            policy: simulate_mechanical(
                episode,
                path,
                policy,
                terminal_sessions=TERMINAL_SESSIONS,
            )
            for policy in PANEL_II_POLICIES
        }
        if any(outcome is None for outcome in per_policy.values()):
            censored["simulation_infeasible_or_window_censored"] += 1
            continue
        for policy, outcome in per_policy.items():
            outcomes[policy].append(outcome)
    if not outcomes["A_MINUTE"]:
        return None, censored
    report = panel_report(
        outcomes,
        baseline_policy="A_MINUTE",
        starting_capital=starting_capital,
    )
    report["binding_interpretation"] = False
    report["parameters"] = {
        "A_MINUTE": "current mechanical stop stack reconstructible from minute bars",
        "D": {"fixed_stop_from_weighted_real_entry_fill_percent": -0.80},
        "D_PRIME": {"daily_wilder_atr_period": 14, "stop_atr_multiple": -1.5},
    }
    report["limitation"] = (
        "Bars do not reproduce live technical decisions; this panel measures stop geometry "
        "versus noise and can authorize only a prospective read-only shadow proposal."
    )
    report["terminal_horizon_sessions"] = TERMINAL_SESSIONS
    report["terminal_horizon_source"] = "Deliverable 0 confirmed no current terminal horizon"
    report["a_minute_reconstruction_scope"] = (
        "Persisted entry stop, cost-aware ATR hard stop, 2.5x five-minute ATR chandelier, "
        "peak locks, positive EOD close proxy and terminal horizon. Live defense/weekly/rotation "
        "state is intentionally absent and measured only through the fidelity diagnostic."
    )
    report["fidelity_diagnostic"] = [
        {
            "episode_id": outcome.episode_id,
            **dict(outcome.fidelity_to_observed or {}),
        }
        for outcome in outcomes["A_MINUTE"]
    ]
    return report, censored


def _report_hash(report: Mapping[str, Any]) -> str:
    return canonical_sha256({key: value for key, value in report.items() if key != "report_sha256"})


def build_report(
    *,
    settings: Settings,
    generated_at: datetime | None = None,
    spec_path: Path | None = None,
    deliverable_path: Path | None = None,
) -> dict[str, Any]:
    generated_at = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    c3po_root = Path(__file__).resolve().parents[2]
    spec = require_frozen_document(
        spec_path or c3po_root / "docs" / "EXIT_POLICY_STUDY_V1_1.md",
        SPEC_SHA256,
        "frozen EXIT_POLICY_STUDY_V1.1 spec",
    )
    deliverable = require_frozen_document(
        deliverable_path or c3po_root / "docs" / "EXIT_POLICY_STUDY_V1_1_DELIVERABLE_0.md",
        DELIVERABLE_ZERO_SHA256,
        "approved Deliverable 0",
    )
    database = Database(settings)
    experiment, fills = LedgerReader(database).read(settings.r2d2_experiment_code)
    if str(experiment.get("methodology_version")) != FROZEN_METHODOLOGY:
        raise ExitPolicyStudyError(
            "experiment methodology does not match the frozen policy: "
            f"{experiment.get('methodology_version')}"
        )
    episodes, construction_counts = build_episodes(fills)
    aggregate_reader = MinuteAggregateReader(settings.day_d_dataset_root)
    sources = aggregate_reader.selected_sources(episodes)
    symbols = {
        episode.symbol for episode in episodes
        if episode.market in {"NASDAQ", "NYSE"}
    }
    bars, bar_evidence = aggregate_reader.read(sources, symbols)
    latest_bar_session = max(session for session, _path in sources)
    base_cohort, base_censoring = _base_cohort(episodes, latest_bar_session)
    covered_cohort, coverage_censoring = _coverage_cohort(base_cohort, bars)

    common_gate = None
    panel_i = None
    panel_ii = None
    excursions = None
    panel_i_censoring: dict[str, int] = {}
    panel_ii_censoring: dict[str, int] = {}
    analysis_interpretable = False
    gate_failures: list[dict[str, Any]] = []
    try:
        common_gate = reconcile_binding_gate(covered_cohort, bars)
        panel_i, panel_i_cohort, panel_i_censoring = _run_panel_i(
            covered_cohort,
            bars,
            float(experiment["starting_capital"]),
        )
        panel_ii, panel_ii_censoring = _run_panel_ii(
            covered_cohort,
            bars,
            float(experiment["starting_capital"]),
        )
        excursion_rows = []
        excursion_censored = 0
        for episode in panel_i_cohort:
            try:
                excursion_rows.append(
                    real_excursions(episode, bars.get(episode.symbol, ()))
                )
            except ExitPolicyStudyError:
                excursion_censored += 1
        excursions = excursion_report(excursion_rows)
        excursions["censored_episode_count"] = excursion_censored
        analysis_interpretable = True
    except ConsistencyGateError as exc:
        gate_failures = exc.failures
        common_gate = {
            "passed": False,
            "failures": gate_failures,
            "failure_count": len(gate_failures),
            "rule": "stop analysis; do not interpret either panel",
        }

    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": generated_at,
        "classification": (
            panel_i.get("classification") if panel_i else "BLOCKED_BY_BINDING_GATE"
        ),
        "analysis_interpretable": analysis_interpretable,
        "governance": {
            "read_only": True,
            "external_api_calls": 0,
            "strategy_change_authorized": False,
            "production_write_authorized": False,
            "panel_i_can_only_support_a_future_six_hands_proposal": True,
            "panel_ii_can_only_support_a_prospective_shadow_proposal": True,
        },
        "frozen_contract": {
            "spec": spec,
            "deliverable_zero": deliverable,
            "policy_commit": FROZEN_POLICY_COMMIT,
            "methodology": FROZEN_METHODOLOGY,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
            "bootstrap_session_timezone": "America/New_York",
            "realized_accounting_timezone": "America/Sao_Paulo",
            "terminal_horizon_sessions": TERMINAL_SESSIONS,
            "intrabar_precedence": ["gap_at_open", "stop", "take_profit", "positive_eod"],
            "activation_delay": "breakeven/trailing armed on bar N apply from bar N+1",
        },
        "experiment": {
            "id": str(experiment["id"]),
            "code": str(experiment["code"]),
            "starting_capital_usd": float(experiment["starting_capital"]),
            "start_date": experiment["start_date"],
        },
        "inputs": {
            "ledger": _ledger_evidence(fills),
            "minute_aggregates": bar_evidence,
            "minute_aggregate_manifest_sha256": canonical_sha256(bar_evidence),
            "last_bar_session": latest_bar_session,
        },
        "cohort": {
            "constructed_episode_count": len(episodes),
            "construction": construction_counts,
            "base_eligible_episode_count": len(base_cohort),
            "base_censoring": base_censoring,
            "data_covered_episode_count": len(covered_cohort),
            "coverage_censoring": coverage_censoring,
            "panel_i_censoring": panel_i_censoring,
            "panel_ii_censoring": panel_ii_censoring,
            "common_cohort_within_each_panel": True,
        },
        "binding_consistency_gate": common_gate,
        "panel_i": panel_i,
        "panel_ii": panel_ii,
        "real_episode_excursions": excursions,
        "limitations": [
            "Minute bars establish accounting/OHLC compatibility, not intraminute causal reconstruction.",
            "MFE/MAE excludes a minute containing a ledger fill because event order inside that bar is unknowable.",
            "Panel II omits live technical state and is exploratory by preregistration.",
            "The positive EOD rule uses the final regular-session minute close as the bars-only proxy.",
            "A policy with fewer than 15 observed sessions remains PILOT and cannot move production.",
        ],
    }
    report["report_sha256"] = _report_hash(report)
    return report


def build_plan(
    *,
    settings: Settings,
    spec_path: Path | None = None,
    deliverable_path: Path | None = None,
) -> dict[str, Any]:
    c3po_root = Path(__file__).resolve().parents[2]
    spec = require_frozen_document(
        spec_path or c3po_root / "docs" / "EXIT_POLICY_STUDY_V1_1.md",
        SPEC_SHA256,
        "frozen EXIT_POLICY_STUDY_V1.1 spec",
    )
    deliverable = require_frozen_document(
        deliverable_path or c3po_root / "docs" / "EXIT_POLICY_STUDY_V1_1_DELIVERABLE_0.md",
        DELIVERABLE_ZERO_SHA256,
        "approved Deliverable 0",
    )
    database = Database(settings)
    experiment, fills = LedgerReader(database).read(settings.r2d2_experiment_code)
    episodes, construction = build_episodes(fills)
    sources = MinuteAggregateReader(settings.day_d_dataset_root).selected_sources(episodes)
    return {
        "command": "plan",
        "read_only": True,
        "external_api_calls": 0,
        "report_written": False,
        "spec": spec,
        "deliverable_zero": deliverable,
        "experiment_id": str(experiment["id"]),
        "ledger_rows": len(fills),
        "episodes": len(episodes),
        "episode_construction": construction,
        "minute_sources": [str(path) for _session, path in sources],
        "minute_source_count": len(sources),
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
        "run_window": "00:00-08:00 America/Sao_Paulo",
    }


def require_off_hours(at: datetime) -> None:
    if at.tzinfo is None:
        raise ExitPolicyStudyError("run time must be timezone-aware")
    local = at.astimezone(SAO_PAULO)
    if not (0 <= local.hour < 8):
        raise ExitPolicyStudyError(
            "study run is restricted to 00:00-08:00 America/Sao_Paulo; "
            f"observed {local.isoformat()}"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only runner for frozen EXIT_POLICY_STUDY_V1.1",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("plan", "run"):
        child = subparsers.add_parser(command)
        child.add_argument("--spec", type=Path)
        child.add_argument("--deliverable-zero", type=Path)
        if command == "run":
            child.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = get_settings()
    if args.command == "plan":
        payload = build_plan(
            settings=settings,
            spec_path=args.spec,
            deliverable_path=args.deliverable_zero,
        )
        print(json.dumps(_json_ready(payload), sort_keys=True, indent=2))
        return 0
    now = datetime.now(timezone.utc)
    require_off_hours(now)
    payload = build_report(
        settings=settings,
        generated_at=now,
        spec_path=args.spec,
        deliverable_path=args.deliverable_zero,
    )
    write_immutable_json(args.output, payload)
    print(json.dumps({
        "artifact": str(args.output),
        "report_sha256": payload["report_sha256"],
        "analysis_interpretable": payload["analysis_interpretable"],
        "classification": payload["classification"],
    }, sort_keys=True))
    return 0 if payload["analysis_interpretable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
