from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app import backtest, r2d2_strategy as strategy


NEW_YORK = ZoneInfo("America/New_York")
SCHEMA_VERSION = "R2D2-CANDIDATE-E-F-BACKTEST-v1"
FROZEN_POLICY_COMMIT = "bc79ca195c19bee9b9ef18c3098d28ae6c149597"
ORIGINAL_HARNESS_RECOVERED_AT = "2026-09-02"
SYMBOLS = (
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO", "COST", "NFLX",
    "AMD", "INTC", "CSCO", "QCOM", "AMAT", "MU", "PANW", "ADP", "BKNG", "GILD",
    "JPM", "BAC", "WMT", "XOM", "CVX", "JNJ", "V", "MA", "HD", "PG",
    "KO", "DIS", "CRM", "ORCL", "IBM", "CAT", "GE", "GS", "MS", "UNH",
)
SESSION_FROM = date(2026, 8, 6)
SESSION_TO = date(2026, 8, 19)
STARTING_CAPITAL = 1_000_000.0
MAX_POSITIONS = 20
FEES_BPS = 5.0
SLIPPAGE_BPS = 5.0
LOOKBACK_BARS = 40
MARKET = "NASDAQ"
EXPECTED_SESSIONS = tuple(
    date.fromordinal(ordinal)
    for ordinal in range(SESSION_FROM.toordinal(), SESSION_TO.toordinal() + 1)
    if date.fromordinal(ordinal).weekday() < 5
)
MIN_FIVE_MINUTE_BARS_PER_SYMBOL_SESSION = 70
STOP_REASON_MARKERS = ("Immediate hard stop", "Adaptive intraday stop")


class CandidateBacktestError(RuntimeError):
    pass


def _json_default(value: Any) -> str:
    return value.isoformat() if isinstance(value, (date, datetime)) else str(value)


def _require_sha256(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        raise CandidateBacktestError("frozen source SHA-256 must be 64 hexadecimal characters")
    return normalized


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
        default=_json_default,
    ).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_files(root: Path) -> list[Path]:
    output: list[Path] = []
    missing: list[str] = []
    for session in EXPECTED_SESSIONS:
        path = root / "provider=massive" / "dataset=minute_aggregates" / f"session_date={session}" / "source.csv.gz"
        if path.is_file():
            output.append(path)
        else:
            missing.append(session.isoformat())
    if missing:
        raise CandidateBacktestError(
            "Massive minute aggregates missing frozen session(s): " + ", ".join(missing)
        )
    return output


def _five_minute_bars(root: Path) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    minutes: dict[tuple[str, date, int, int], list[dict[str, Any]]] = defaultdict(list)
    evidence: list[dict[str, Any]] = []
    seen: set[tuple[str, datetime]] = set()
    for path in _source_files(root):
        expected_session = date.fromisoformat(path.parent.name.split("=", 1)[1])
        metadata_path = path.with_name(f"{path.name}.metadata.json")
        if not metadata_path.is_file():
            raise CandidateBacktestError(f"minute source metadata is missing: {metadata_path}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        digest = _sha256_file(path)
        if metadata.get("sha256") != digest:
            raise CandidateBacktestError(f"minute source checksum mismatch: {path}")
        if int(metadata.get("content_length", -1)) != path.stat().st_size:
            raise CandidateBacktestError(f"minute source size mismatch: {path}")
        evidence.append({
            "session_date": path.parent.name.split("=", 1)[1],
            "sha256": digest,
            "size_bytes": path.stat().st_size,
        })
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"ticker", "window_start", "open", "high", "low", "close", "volume"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                missing_columns = sorted(required - set(reader.fieldnames or ()))
                raise CandidateBacktestError(
                    f"minute source columns missing in {path}: {missing_columns}"
                )
            for row in reader:
                symbol = str(row.get("ticker") or "")
                if symbol not in SYMBOLS:
                    continue
                at = datetime.fromtimestamp(int(row["window_start"]) / 1_000_000_000, tz=timezone.utc)
                local = at.astimezone(NEW_YORK)
                if not (9, 30) <= (local.hour, local.minute) < (16, 0):
                    continue
                if local.date() != expected_session:
                    raise CandidateBacktestError(
                        f"bar session mismatch in {path}: {local.date()} != {expected_session}"
                    )
                key = (symbol, at)
                if key in seen:
                    raise CandidateBacktestError(f"duplicate minute aggregate: {symbol} {at}")
                seen.add(key)
                bucket = local.minute - local.minute % 5
                minutes[(symbol, local.date(), local.hour, bucket)].append({
                    "timestamp": at,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                })
    bars: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in SYMBOLS}
    for (symbol, _session, _hour, _minute), values in minutes.items():
        ordered = sorted(values, key=lambda item: item["timestamp"])
        if len(ordered) != 5:
            continue
        if any(
            ordered[index]["timestamp"] - ordered[index - 1]["timestamp"]
            != timedelta(minutes=1)
            for index in range(1, 5)
        ):
            continue
        bars[symbol].append({
            "timestamp": ordered[0]["timestamp"],
            "open": ordered[0]["open"],
            "high": max(item["high"] for item in ordered),
            "low": min(item["low"] for item in ordered),
            "close": ordered[-1]["close"],
            "volume": sum(item["volume"] for item in ordered),
        })
    bars = {symbol: sorted(values, key=lambda item: item["timestamp"]) for symbol, values in bars.items()}
    for symbol, values in bars.items():
        counts = {
            session: sum(
                item["timestamp"].astimezone(NEW_YORK).date() == session
                for item in values
            )
            for session in EXPECTED_SESSIONS
        }
        incomplete = {
            session.isoformat(): count
            for session, count in counts.items()
            if count < MIN_FIVE_MINUTE_BARS_PER_SYMBOL_SESSION
        }
        if incomplete:
            raise CandidateBacktestError(
                f"frozen universe has incomplete session(s) for {symbol}: {incomplete}"
            )
    return bars, evidence


def _candidate_f_wrapper(
    original: Callable[..., Any],
) -> Callable[..., Any]:
    def wrapped(**kwargs: Any) -> Any:
        state = kwargs["state"]
        technical = kwargs["technical"]
        quote = float(kwargs["quote_price"])
        original_stop = float(kwargs["stop_price"])
        atr = max(float(technical.get("atr") or 0.0), quote * 0.004)
        stop_e = max(original_stop, float(kwargs["high_water"]) - 2.5 * atr)
        previous_f = float(getattr(state, "_candidate_f_stop", original_stop))
        stop_f = max(previous_f, stop_e)
        forwarded = dict(kwargs)
        forwarded["stop_price"] = stop_f
        decision, new_state = original(**forwarded)
        setattr(new_state, "_candidate_f_stop", stop_f)
        return decision, new_state
    return wrapped


def _run_variant(
    bars: dict[str, list[dict[str, Any]]],
    *,
    candidate_f: bool,
) -> Any:
    original = strategy.exit_decision
    if candidate_f:
        strategy.exit_decision = _candidate_f_wrapper(original)
    try:
        return backtest.run_backtest(
            bars,
            starting_capital=STARTING_CAPITAL,
            max_positions=MAX_POSITIONS,
            fees_bps=FEES_BPS,
            slippage_bps=SLIPPAGE_BPS,
            lookback_bars=LOOKBACK_BARS,
            market=MARKET,
        )
    finally:
        strategy.exit_decision = original


def _premature_exit_metrics(
    report: Any,
    bars: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    observed = 0
    eligible = 0
    recovered = 0
    for symbol in SYMBOLS:
        quantity = 0.0
        entry_notional = 0.0
        trades = sorted(
            (trade for trade in report.trades if trade.symbol == symbol),
            key=lambda trade: trade.timestamp,
        )
        for trade in trades:
            if trade.side == "BUY":
                quantity += float(trade.quantity)
                entry_notional += float(trade.quantity) * float(trade.price)
                continue
            if trade.side != "SELL" or quantity <= 0:
                continue
            average_entry = entry_notional / quantity
            sold = min(quantity, float(trade.quantity))
            if any(marker in str(trade.reason) for marker in STOP_REASON_MARKERS):
                observed += 1
                session = trade.timestamp.astimezone(NEW_YORK).date()
                later = [
                    bar for bar in bars[symbol]
                    if bar["timestamp"].astimezone(NEW_YORK).date() == session
                    and bar["timestamp"] > trade.timestamp
                ]
                if later:
                    eligible += 1
                    recovered += max(float(bar["high"]) for bar in later) > average_entry
            remaining = quantity - sold
            if remaining <= 1e-9:
                quantity = 0.0
                entry_notional = 0.0
            else:
                entry_notional = average_entry * remaining
                quantity = remaining
    return {
        "definition": "stop exit with a strictly later same-session five-minute high above weighted entry",
        "observed_stop_exit_leg_count": observed,
        "eligible_stop_exit_leg_count": eligible,
        "premature_exit_count": recovered,
        "premature_exit_percent": round(recovered / eligible * 100.0, 4) if eligible else None,
    }


def _metrics(report: Any, bars: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    exits = [trade for trade in report.trades if trade.side == "SELL"]
    wins = [trade for trade in exits if float(trade.realized_pnl_usd or 0.0) > 0]
    losses = [trade for trade in exits if float(trade.realized_pnl_usd or 0.0) < 0]
    average_gain = (
        sum(float(trade.realized_pnl_usd) for trade in wins) / len(wins) if wins else 0.0
    )
    average_loss = (
        sum(float(trade.realized_pnl_usd) for trade in losses) / len(losses) if losses else 0.0
    )
    payoff = average_gain / abs(average_loss) if average_loss else None
    return {
        "buy_count": sum(trade.side == "BUY" for trade in report.trades),
        "exit_leg_count": len(exits),
        "win_rate_percent": report.win_rate_percent,
        "average_gain_usd": round(average_gain, 4),
        "average_loss_usd": round(average_loss, 4),
        "payoff_ratio": round(payoff, 4) if payoff is not None else None,
        "profit_factor": report.profit_factor,
        "total_return_percent": report.total_return_percent,
        "max_drawdown_percent": report.max_drawdown_percent,
        "ending_nav_usd": round(report.ending_nav, 2),
        "premature_exit": _premature_exit_metrics(report, bars),
    }


def build_report(
    data_root: Path,
    generated_at: datetime,
    *,
    frozen_source_sha256: str,
) -> dict[str, Any]:
    frozen_source_sha256 = _require_sha256(frozen_source_sha256)
    bars, source_evidence = _five_minute_bars(data_root)
    missing = sorted(set(SYMBOLS) - set(bars))
    if missing:
        raise CandidateBacktestError(f"frozen universe missing usable bars: {', '.join(missing)}")
    candidate_e = _run_variant(bars, candidate_f=False)
    candidate_f = _run_variant(bars, candidate_f=True)
    metrics_e = _metrics(candidate_e, bars)
    metrics_f = _metrics(candidate_f, bars)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "frozen_harness": {
            "policy_commit": FROZEN_POLICY_COMMIT,
            "source_package_sha256": frozen_source_sha256,
            "recovered_at": ORIGINAL_HARNESS_RECOVERED_AT,
            "symbols": list(SYMBOLS),
            "session_from": SESSION_FROM,
            "session_to": SESSION_TO,
            "bar_interval": "5m aggregated from checksum-verified one-minute bars",
            "starting_capital_usd": STARTING_CAPITAL,
            "max_positions": MAX_POSITIONS,
            "fees_bps": FEES_BPS,
            "slippage_bps": SLIPPAGE_BPS,
            "lookback_bars": LOOKBACK_BARS,
            "minimum_five_minute_bars_per_symbol_session": MIN_FIVE_MINUTE_BARS_PER_SYMBOL_SESSION,
            "neutral_fundamentals": True,
            "candidate_e": "2x ATR initial floor, 2.5x live-ATR Chandelier, 0.03% NAV risk budget",
            "candidate_f_only_delta": "stop_f = max(previous_stop_f, stop_e)",
        },
        "inputs": {
            "usable_symbol_count": len(bars),
            "five_minute_bar_count": sum(len(values) for values in bars.values()),
            "source_manifest_sha256": canonical_sha256(source_evidence),
            "source_sessions": source_evidence,
        },
        "candidate_e": metrics_e,
        "candidate_f": metrics_f,
        "paired_delta_f_minus_e": {
            "payoff_ratio": (
                round(float(metrics_f["payoff_ratio"]) - float(metrics_e["payoff_ratio"]), 4)
                if metrics_e["payoff_ratio"] is not None and metrics_f["payoff_ratio"] is not None else None
            ),
            "max_drawdown_percent": round(
                float(metrics_f["max_drawdown_percent"]) - float(metrics_e["max_drawdown_percent"]), 4,
            ),
            "total_return_percent": round(
                float(metrics_f["total_return_percent"]) - float(metrics_e["total_return_percent"]), 4,
            ),
            "premature_exit_percentage_points": (
                round(
                    float(metrics_f["premature_exit"]["premature_exit_percent"])
                    - float(metrics_e["premature_exit"]["premature_exit_percent"]),
                    4,
                )
                if metrics_e["premature_exit"]["premature_exit_percent"] is not None
                and metrics_f["premature_exit"]["premature_exit_percent"] is not None
                else None
            ),
        },
        "premature_exit_note": (
            "E-vs-F measures recovery above entry from frozen five-minute bars; "
            "Probe B is the canonical production measure and additionally evaluates +1R from the stored initial stop."
        ),
        "candidate_g": {
            "executed": False,
            "reason": "optional extension omitted to preserve a one-variable E-vs-F comparison",
        },
        "governance": {
            "production_policy_changed": False,
            "external_api_calls": 0,
            "artifact_class": "aggregate statistics; no raw bars or trades",
            "retention_days": 30,
            "expires_at": generated_at + timedelta(days=30),
        },
        "limitations": [
            "The original EODHD response bytes from 20/08 were not retained; the exact frozen harness, symbols and dates are replayed on the checksum-verified Massive archive.",
            "Provider-normalization differences mean this run must not be presented as a byte-for-byte rerun of the original Candidate E result.",
            "The historical engine evaluates completed five-minute closes and does not model the later one-second two-tick watcher.",
        ],
    }
    payload["report_sha256"] = canonical_sha256(payload)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Frozen Candidate E versus ratcheted Candidate F")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-source-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = build_report(
        args.data_root,
        datetime.now(timezone.utc),
        frozen_source_sha256=args.frozen_source_sha256,
    )
    encoded = json.dumps(
        payload,
        sort_keys=True,
        indent=2,
        allow_nan=False,
        default=_json_default,
    ).encode("utf-8") + b"\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != encoded:
        raise FileExistsError(f"immutable report differs: {args.output}")
    args.output.write_bytes(encoded)
    print(json.dumps({"report": str(args.output), "report_sha256": payload["report_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
