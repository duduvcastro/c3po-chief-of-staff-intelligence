from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from .config import Settings, get_settings
from .database import Database
from .r2d2_exit_policy_engine import Episode, LedgerFill, PositionState, StudyBar, build_episodes
from .r2d2_exit_policy_study import (
    MinuteAggregateReader,
    _aware,
    _ledger_fill,
    canonical_sha256,
    write_immutable_json,
)


NEW_YORK = ZoneInfo("America/New_York")
POLICY_EPOCH = "policy-a-resume-2026-08-26"
POLICY_EPOCH_FROM = datetime.fromisoformat("2026-08-26T13:30:24.983322+00:00")
SCHEMA_VERSION = "R2D2-CHANDELIER-PROBE-v1"
EXPERIMENT_QUERY = """
SELECT id::text, code, status, starting_capital, start_date,
       methodology_version, created_at, updated_at
FROM r2d2_experiments
WHERE code = %s
""".strip()
TRADE_QUERY = """
SELECT id::text, market, symbol, name, side, quantity,
       signal_price_local, fill_price_local, fx_to_usd,
       gross_value_usd, fees_usd, slippage_usd,
       realized_pnl_usd, reason, decision_snapshot,
       executed_at, quote_as_of, fast_exit_rule,
       fast_exit_level_local, fast_exit_atr_local, fast_exit_tick_as_of
FROM r2d2_trades
WHERE experiment_id = %s AND executed_at <= %s
ORDER BY executed_at, id
""".strip()
QUERY_TEXT = EXPERIMENT_QUERY + ";\n\n" + TRADE_QUERY + ";\n"
QUERY_SHA256 = hashlib.sha256(QUERY_TEXT.encode("utf-8")).hexdigest()
STOP_REASON_MARKERS = (
    "Immediate hard stop",
    "Adaptive intraday stop",
    "Fast risk watcher hard_stop",
    "Fast risk watcher chandelier_2tick",
)


class ChandelierProbeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TradeAudit:
    fast_exit_rule: str | None
    fast_exit_level_local: float | None
    fast_exit_atr_local: float | None
    fast_exit_tick_as_of: datetime | None


@dataclass(frozen=True, slots=True)
class FiveMinuteBar:
    symbol: str
    start_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source_minutes: int

    @property
    def session_date(self) -> date:
        return self.start_at.astimezone(NEW_YORK).date()


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _read_ledger(
    database: Database,
    *,
    experiment_code: str,
    cutoff_at: datetime,
) -> tuple[dict[str, Any], list[LedgerFill], dict[str, TradeAudit]]:
    if not database.database_url:
        raise ChandelierProbeError("the production probe requires PostgreSQL")
    with database.connection() as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        transaction_read_only = connection.execute(
            "SHOW transaction_read_only"
        ).fetchone()
        if not transaction_read_only or str(transaction_read_only[0]).lower() != "on":
            raise ChandelierProbeError("PostgreSQL transaction is not read-only")
        experiment_row = connection.execute(
            EXPERIMENT_QUERY, (experiment_code,),
        ).fetchone()
        if not experiment_row:
            raise ChandelierProbeError(f"R2D2 experiment not found: {experiment_code}")
        rows = connection.execute(
            TRADE_QUERY, (experiment_row[0], cutoff_at),
        ).fetchall()
        connection.rollback()
    experiment: dict[str, Any] = dict(zip(
        (
            "id", "code", "status", "starting_capital", "start_date",
            "methodology_version", "created_at", "updated_at",
        ),
        experiment_row,
    ))
    ledger_keys = (
        "id", "market", "symbol", "name", "side", "quantity",
        "signal_price_local", "fill_price_local", "fx_to_usd",
        "gross_value_usd", "fees_usd", "slippage_usd",
        "realized_pnl_usd", "reason", "decision_snapshot",
        "executed_at", "quote_as_of",
    )
    fills: list[LedgerFill] = []
    audits: dict[str, TradeAudit] = {}
    for row in rows:
        mapped: dict[str, Any] = dict(zip(
            (*ledger_keys, "fast_exit_rule", "fast_exit_level_local",
             "fast_exit_atr_local", "fast_exit_tick_as_of"),
            row,
        ))
        fill = _ledger_fill(mapped)
        fills.append(fill)
        audits[fill.id] = TradeAudit(
            fast_exit_rule=(
                str(mapped["fast_exit_rule"])
                if mapped.get("fast_exit_rule") is not None else None
            ),
            fast_exit_level_local=_optional_float(mapped.get("fast_exit_level_local")),
            fast_exit_atr_local=_optional_float(mapped.get("fast_exit_atr_local")),
            fast_exit_tick_as_of=(
                _aware(mapped["fast_exit_tick_as_of"])
                if mapped.get("fast_exit_tick_as_of") is not None else None
            ),
        )
    return experiment, fills, audits


def aggregate_five_minutes(bars: Sequence[StudyBar]) -> list[FiveMinuteBar]:
    buckets: dict[tuple[str, date, int, int], list[StudyBar]] = defaultdict(list)
    for bar in sorted(bars, key=lambda item: item.start_at):
        local = bar.start_at.astimezone(NEW_YORK)
        bucket_minute = local.minute - (local.minute % 5)
        buckets[(bar.symbol, local.date(), local.hour, bucket_minute)].append(bar)
    output: list[FiveMinuteBar] = []
    for values in buckets.values():
        ordered = sorted(values, key=lambda item: item.start_at)
        if len(ordered) != 5:
            continue
        expected = [ordered[0].start_at + timedelta(minutes=index) for index in range(5)]
        if [item.start_at for item in ordered] != expected:
            continue
        output.append(FiveMinuteBar(
            symbol=ordered[0].symbol,
            start_at=ordered[0].start_at,
            open=ordered[0].open,
            high=max(item.high for item in ordered),
            low=min(item.low for item in ordered),
            close=ordered[-1].close,
            volume=sum(item.volume for item in ordered),
            source_minutes=5,
        ))
    return sorted(output, key=lambda item: item.start_at)


def atr14_sma(bars: Sequence[FiveMinuteBar], index: int) -> float | None:
    if index < 14:
        return None
    window = bars[max(0, index - 39): index + 1]
    if len(window) < 35:
        return None
    ranges = [
        max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
        for previous, current in zip(window[-15:-1], window[-14:])
    ]
    return sum(ranges) / len(ranges) if ranges else None


def chandelier_e(*, original_stop: float, high_water: float, atr: float) -> float:
    return max(original_stop, high_water - 2.5 * atr)


def _episode_token(episode: Episode) -> str:
    return hashlib.sha256(
        f"{episode.id}|{episode.opened_at.isoformat()}|{episode.market}".encode("utf-8")
    ).hexdigest()[:16]


def _actual_pnl(episode: Episode) -> float:
    return sum(
        fill.realized_pnl_usd if fill.realized_pnl_usd is not None else 0.0
        for fill in episode.fills
    )


def _entry_stop(episode: Episode) -> float | None:
    for fill in episode.fills:
        if fill.side != "BUY":
            continue
        value: Any = fill.decision_snapshot.get("stop_price")
        try:
            stop = float(value)
        except (TypeError, ValueError):
            return None
        return stop if stop > 0 else None
    return None


def _single_entry_full_exit(episode: Episode) -> bool:
    buys = [fill for fill in episode.fills if fill.side == "BUY"]
    sells = [fill for fill in episode.fills if fill.side == "SELL"]
    return len(buys) == 1 and len(sells) == 1 and math.isclose(
        buys[0].quantity, sells[0].quantity, rel_tol=0.0, abs_tol=1e-7,
    )


def _synthetic_exit_pnl(
    episode: Episode,
    *,
    quote: float,
) -> float:
    entry = next(fill for fill in episode.fills if fill.side == "BUY")
    slip_rate = 0.0015 if episode.market == "B3" else 0.0010
    fee_rate = 0.0006 if episode.market == "B3" else 0.0004
    fill_price = quote * (1.0 - slip_rate)
    gross_usd = entry.quantity * fill_price * entry.fx_to_usd
    fee_usd = gross_usd * fee_rate
    state = PositionState()
    state.buy(entry)
    return gross_usd - fee_usd - entry.quantity * state.average_cost_usd


def analyze_winning_episode(
    episode: Episode,
    bars: Sequence[FiveMinuteBar],
    audits: Mapping[str, TradeAudit] | None = None,
) -> dict[str, Any]:
    token = _episode_token(episode)
    actual = _actual_pnl(episode)
    row: dict[str, Any] = {
        "episode_token": token,
        "entry_session": episode.entry_session.isoformat(),
        "actual_exit_engine": (
            audits[episode.fills[-1].id].fast_exit_rule
            if audits
            and episode.fills[-1].id in audits
            and audits[episode.fills[-1].id].fast_exit_rule
            else "main_cycle"
        ),
        "actual_net_pnl_usd": round(actual, 2),
        "counterfactual_f_net_pnl_usd": None,
        "avoidable_giveback_usd": None,
        "f_exit_at": None,
        "eligibility": "eligible",
    }
    original_stop = _entry_stop(episode)
    if original_stop is None:
        row["eligibility"] = "censored_missing_original_stop"
        return row
    if not _single_entry_full_exit(episode):
        row["eligibility"] = "censored_scaled_or_partial_episode"
        return row
    entry = next(fill for fill in episode.fills if fill.side == "BUY")
    ordered = sorted(bars, key=lambda item: item.start_at)
    high_water = entry.fill_price_local
    ratcheted: float | None = None
    maximum_loosen_bps = 0.0
    loosen_observations = 0
    synthetic_pnl: float | None = None
    synthetic_at: datetime | None = None
    for index, bar in enumerate(ordered):
        bar_end = bar.start_at + timedelta(minutes=5)
        if bar_end <= episode.opened_at or bar.start_at >= (episode.closed_at or bar.start_at):
            continue
        atr = atr14_sma(ordered, index)
        if atr is None:
            continue
        high_water = max(high_water, bar.close)
        stop_e = chandelier_e(
            original_stop=original_stop,
            high_water=high_water,
            atr=max(atr, bar.close * 0.004),
        )
        prior_f = ratcheted
        ratcheted = max(ratcheted or stop_e, stop_e)
        if prior_f is not None and stop_e < prior_f:
            loosen_observations += 1
            maximum_loosen_bps = max(
                maximum_loosen_bps,
                (prior_f - stop_e) / prior_f * 10_000.0,
            )
        if synthetic_pnl is None and bar.close <= ratcheted and bar.close > stop_e:
            synthetic_pnl = _synthetic_exit_pnl(episode, quote=bar.close)
            synthetic_at = bar_end
            break
    row.update({
        "maximum_trail_loosen_bps": round(maximum_loosen_bps, 2),
        "trail_loosen_observations": loosen_observations,
        "ratchet_only_exit_observed": synthetic_pnl is not None,
    })
    if synthetic_pnl is None:
        row["counterfactual_f_net_pnl_usd"] = round(actual, 2)
        row["avoidable_giveback_usd"] = 0.0
    else:
        row["counterfactual_f_net_pnl_usd"] = round(synthetic_pnl, 2)
        row["avoidable_giveback_usd"] = round(synthetic_pnl - actual, 2)
        row["f_exit_at"] = synthetic_at.isoformat() if synthetic_at else None
    return row


def _is_stop_out(fill: LedgerFill, audit: TradeAudit | None) -> bool:
    if audit and audit.fast_exit_rule in {"hard_stop", "chandelier_2tick"}:
        return True
    return any(marker in fill.reason for marker in STOP_REASON_MARKERS)


def analyze_stop_regret(
    episode: Episode,
    minute_bars: Sequence[StudyBar],
    audits: Mapping[str, TradeAudit],
) -> dict[str, Any] | None:
    final = episode.fills[-1]
    audit = audits.get(final.id)
    if final.side != "SELL" or not _is_stop_out(final, audit):
        return None
    original_stop = _entry_stop(episode)
    buys = [fill for fill in episode.fills if fill.side == "BUY"]
    if not buys or original_stop is None:
        return {
            "episode_token": _episode_token(episode),
            "exit_session": episode.exit_session.isoformat() if episode.exit_session else None,
            "eligibility": "censored_missing_entry_or_stop",
        }
    total_quantity = sum(fill.quantity for fill in buys)
    if total_quantity <= 0:
        return None
    entry_price = sum(fill.fill_price_local * fill.quantity for fill in buys) / total_quantity
    one_r = entry_price - original_stop
    if one_r <= 0:
        return {
            "episode_token": _episode_token(episode),
            "exit_session": episode.exit_session.isoformat() if episode.exit_session else None,
            "eligibility": "censored_nonpositive_initial_r",
        }
    exit_minute = final.executed_at.replace(second=0, microsecond=0)
    later = [
        bar for bar in minute_bars
        if bar.session_date == final.executed_at.astimezone(NEW_YORK).date()
        and bar.start_at > exit_minute
    ]
    if not later:
        return {
            "episode_token": _episode_token(episode),
            "exit_session": episode.exit_session.isoformat() if episode.exit_session else None,
            "eligibility": "censored_no_later_same_session_bar",
        }
    later_high = max(bar.high for bar in later)
    return {
        "episode_token": _episode_token(episode),
        "exit_session": episode.exit_session.isoformat() if episode.exit_session else None,
        "eligibility": "eligible",
        "exit_engine": audit.fast_exit_rule if audit and audit.fast_exit_rule else "main_cycle",
        "recovered_above_entry_same_session": later_high > entry_price,
        "reached_plus_1r_same_session": later_high >= entry_price + one_r,
        "post_exit_max_return_percent": round((later_high / entry_price - 1.0) * 100.0, 4),
    }


def _percent(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100.0, 4) if denominator else None


def _distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "min": None, "p50": None, "p90": None, "max": None, "mean": None}
    def percentile(q: float) -> float:
        index = (len(ordered) - 1) * q
        lower = math.floor(index)
        upper = math.ceil(index)
        if lower == upper:
            return ordered[lower]
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)
    return {
        "count": len(ordered),
        "min": round(ordered[0], 4),
        "p50": round(percentile(0.50), 4),
        "p90": round(percentile(0.90), 4),
        "max": round(ordered[-1], 4),
        "mean": round(sum(ordered) / len(ordered), 4),
    }


def build_report(
    *,
    settings: Settings,
    generated_at: datetime,
    cutoff_at: datetime,
) -> dict[str, Any]:
    database = Database(settings)
    experiment, fills, audits = _read_ledger(
        database,
        experiment_code=settings.r2d2_experiment_code,
        cutoff_at=cutoff_at,
    )
    episodes, construction = build_episodes(fills)
    cohort = [
        episode for episode in episodes
        if episode.closed
        and episode.market in {"NASDAQ", "NYSE"}
        and episode.opened_at >= POLICY_EPOCH_FROM
        and not episode.strategy_excluded
    ]
    if not cohort:
        raise ChandelierProbeError("no closed organic epoch-2 US episodes")
    reader = MinuteAggregateReader(settings.day_d_dataset_root)
    sources = reader.selected_sources(cohort, prior_sessions=20)
    symbols = {episode.symbol for episode in cohort}
    bars_by_symbol, source_evidence = reader.read(sources, symbols)
    five_by_symbol = {
        symbol: aggregate_five_minutes(bars)
        for symbol, bars in bars_by_symbol.items()
    }
    winners = [episode for episode in cohort if _actual_pnl(episode) > 0]
    probe_a = [
        analyze_winning_episode(
            episode,
            five_by_symbol.get(episode.symbol, ()),
            audits,
        )
        for episode in winners
    ]
    probe_b = [
        result
        for episode in cohort
        if (result := analyze_stop_regret(
            episode, bars_by_symbol.get(episode.symbol, ()), audits,
        )) is not None
    ]
    eligible_a = [row for row in probe_a if row["eligibility"] == "eligible"]
    eligible_b = [row for row in probe_b if row["eligibility"] == "eligible"]
    givebacks = [float(row["avoidable_giveback_usd"]) for row in eligible_a]
    loosening = [float(row["maximum_trail_loosen_bps"]) for row in eligible_a]
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "input_cutoff_at": cutoff_at,
        "policy_epoch": {
            "id": POLICY_EPOCH,
            "effective_from": POLICY_EPOCH_FROM,
            "selection": "closed organic flat-to-flat US episodes opened at/after effective_from",
        },
        "governance": {
            "read_only_transaction_verified": True,
            "external_api_calls": 0,
            "production_policy_changed": False,
            "artifact_class": "reduced statistics; no raw ledger rows or market bars",
            "retention_days": 30,
            "expires_at": generated_at + timedelta(days=30),
            "query_sha256": QUERY_SHA256,
        },
        "experiment": {
            "code": experiment["code"],
            "methodology_version": experiment["methodology_version"],
        },
        "inputs": {
            "ledger_row_count": len(fills),
            "ledger_canonical_sha256": canonical_sha256([asdict(fill) for fill in fills]),
            "minute_source_count": len(source_evidence),
            "minute_source_manifest_sha256": canonical_sha256(source_evidence),
            "minute_source_first_session": source_evidence[0]["session_date"],
            "minute_source_last_session": source_evidence[-1]["session_date"],
        },
        "cohort": {
            "constructed_episode_count": len(episodes),
            "construction": construction,
            "epoch_2_closed_organic_us_episode_count": len(cohort),
            "winning_episode_count": len(winners),
        },
        "probe_a": {
            "contract": {
                "e": "max(original_stop, close_high_water - 2.5 * max(ATR14_SMA, close * 0.004))",
                "f": "max(previous_f, e)",
                "observation_clock": "completed five-minute close; high-water uses closes like Candidate E",
                "counterfactual_trigger": "first close <= F and > E; fill uses the paper US exit friction",
                "scope": "winning episodes; scaled/partial episodes reported but censored",
            },
            "episodes": probe_a,
            "eligible_episode_count": len(eligible_a),
            "eligible_actual_exit_engine_counts": {
                engine: sum(row["actual_exit_engine"] == engine for row in eligible_a)
                for engine in sorted({str(row["actual_exit_engine"]) for row in eligible_a})
            },
            "ratchet_only_exit_count": sum(bool(row["ratchet_only_exit_observed"]) for row in eligible_a),
            "avoidable_giveback_usd_distribution": _distribution(givebacks),
            "maximum_cumulative_trail_loosen_bps_distribution": _distribution(loosening),
        },
        "probe_b": {
            "contract": {
                "stop_out": "final SELL tagged hard_stop/chandelier_2tick or matching main-cycle stop reason",
                "recovery_window": "strictly later one-minute bars in the same New York regular session",
                "entry": "quantity-weighted BUY fill price",
                "one_r": "entry minus original persisted entry stop",
            },
            "episodes": probe_b,
            "observed_stop_out_count": len(probe_b),
            "eligible_stop_out_count": len(eligible_b),
            "recovered_above_entry_count": sum(bool(row["recovered_above_entry_same_session"]) for row in eligible_b),
            "recovered_above_entry_percent": _percent(
                sum(bool(row["recovered_above_entry_same_session"]) for row in eligible_b), len(eligible_b),
            ),
            "reached_plus_1r_count": sum(bool(row["reached_plus_1r_same_session"]) for row in eligible_b),
            "reached_plus_1r_percent": _percent(
                sum(bool(row["reached_plus_1r_same_session"]) for row in eligible_b), len(eligible_b),
            ),
        },
        "limitations": [
            "Five-minute closes cannot reconstruct intrabar tick order or the watcher's two-tick cadence.",
            "A counterfactual is emitted only for a close that breaches F while remaining above E, isolating the ratchet difference.",
            "Per-episode identifiers are one-way tokens; symbols, fills and raw bars are excluded from the artifact.",
            "Fast-watcher and main-cycle stop-outs are stratified because the watcher already persists a monotonic stop when enabled.",
        ],
    }
    report["report_sha256"] = canonical_sha256(report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only epoch-2 Chandelier probes A and B")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--query-output", type=Path, required=True)
    parser.add_argument("--cutoff-at", type=_aware)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    now = datetime.now(timezone.utc)
    report = build_report(
        settings=get_settings(),
        generated_at=now,
        cutoff_at=args.cutoff_at or now,
    )
    write_immutable_json(args.output, report)
    args.query_output.parent.mkdir(parents=True, exist_ok=True)
    query_bytes = QUERY_TEXT.encode("utf-8")
    if args.query_output.exists() and args.query_output.read_bytes() != query_bytes:
        raise FileExistsError(f"query artifact differs: {args.query_output}")
    args.query_output.write_bytes(query_bytes)
    print(json.dumps({
        "report": str(args.output),
        "report_sha256": report["report_sha256"],
        "query_sha256": QUERY_SHA256,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
