from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

from .config import Settings
from .database import Database
from .r2d2 import (
    ACTIVE_MARKETS,
    NEW_YORK,
    R2D2Repository,
    US_REGULAR_CLOSE_ET,
    US_REGULAR_OPEN_ET,
    _float,
    _paper_exit_execution,
)

class WindDownPreconditionError(RuntimeError):
    pass


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _regular_us_session_open(now: datetime) -> bool:
    local = now.astimezone(NEW_YORK)
    return (
        local.weekday() < 5
        and US_REGULAR_OPEN_ET <= local.time().replace(tzinfo=None) < US_REGULAR_CLOSE_ET
    )


class R2D2WindDownService:
    """Plan or execute an administrative, strategy-excluded paper liquidation."""

    def __init__(
        self,
        settings: Settings,
        repository: R2D2Repository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _operator_reason(operator: str, reason: str) -> tuple[str, str]:
        operator = operator.strip()
        reason = reason.strip()
        if not operator or not reason:
            raise ValueError("operator and reason are required")
        return operator, reason

    def _position_plan(self, position: dict[str, Any], now: datetime) -> dict[str, Any]:
        market = str(position.get("market") or "")
        symbol = str(position.get("symbol") or "")
        if market not in ACTIVE_MARKETS:
            raise WindDownPreconditionError(f"{market}:{symbol}: market is not eligible for US wind-down")
        if not _regular_us_session_open(now):
            raise WindDownPreconditionError("US regular session is not open (09:30-16:00 ET)")

        strategy = dict(position.get("strategy_snapshot") or {})
        quote_status = str(strategy.get("quote_status") or "").lower()
        decision_state = str(strategy.get("decision_state") or "").lower()
        quote_as_of = _datetime(strategy.get("quote_as_of"))
        if quote_status != "live" or quote_as_of is None:
            raise WindDownPreconditionError(
                f"{market}:{symbol}: no persisted live-stream quote evidence"
            )
        protected_quote_state = (
            decision_state in {"validating quote", "awaiting live quote"}
            or "delayed quote" in decision_state
        )
        if protected_quote_state:
            raise WindDownPreconditionError(
                f"{market}:{symbol}: quote is under protection state {decision_state!r}"
            )
        now_utc = now.astimezone(timezone.utc)
        quote_age_seconds = (now_utc - quote_as_of.astimezone(timezone.utc)).total_seconds()
        if quote_age_seconds < -5:
            raise WindDownPreconditionError(f"{market}:{symbol}: quote timestamp is in the future")
        if quote_age_seconds > self.settings.r2d2_live_quote_max_age_seconds:
            raise WindDownPreconditionError(
                f"{market}:{symbol}: live quote is {quote_age_seconds:.1f}s old; "
                f"maximum is {self.settings.r2d2_live_quote_max_age_seconds}s"
            )

        quantity = _float(position.get("quantity"))
        mark = _float(position.get("last_price_local"))
        fx = _float(position.get("fx_to_usd"), 1.0)
        average_cost_usd = _float(position.get("average_cost_usd"))
        if min(quantity, mark, fx, average_cost_usd) <= 0:
            raise WindDownPreconditionError(f"{market}:{symbol}: invalid position economics")
        execution = _paper_exit_execution(
            market=market,
            price=mark,
            quantity=quantity,
            fx=fx,
        )
        estimated_realized_pnl_usd = (
            execution["gross_value_usd"]
            - execution["fees_usd"]
            - quantity * average_cost_usd
        )
        return {
            "market": market,
            "symbol": symbol,
            "name": str(position.get("name") or symbol),
            "currency": str(position.get("currency") or "USD"),
            "quantity": quantity,
            "average_cost_usd": average_cost_usd,
            "live_mark_local": mark,
            "fx_to_usd": fx,
            "quote_status": quote_status,
            "decision_state": decision_state,
            "quote_as_of": quote_as_of.astimezone(timezone.utc).isoformat(),
            "quote_age_seconds": round(max(0.0, quote_age_seconds), 3),
            "position_updated_at": (
                position["updated_at"].isoformat()
                if isinstance(position.get("updated_at"), datetime)
                else str(position.get("updated_at") or "")
            ),
            "fill_price_local": execution["fill_price"],
            "slippage_rate": execution["slippage_rate"],
            "fee_rate": execution["fee_rate"],
            "gross_value_usd": execution["gross_value_usd"],
            "fees_usd": execution["fees_usd"],
            "slippage_usd": execution["slippage_usd"],
            "estimated_realized_pnl_usd": estimated_realized_pnl_usd,
            "prior_strategy_snapshot_sha256": _canonical_sha256(strategy),
        }

    def plan(
        self,
        *,
        operator: str,
        reason: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        operator, reason = self._operator_reason(operator, reason)
        now = now or self.clock()
        experiment = self.repository.experiment(self.settings.r2d2_experiment_code)
        if experiment is None:
            raise WindDownPreconditionError(
                f"R2D2 experiment not found: {self.settings.r2d2_experiment_code}"
            )
        positions = self.repository.positions(experiment["id"])
        blockers: list[str] = []
        if experiment.get("status") != "running":
            blockers.append(f"experiment status is {experiment.get('status')!r}, expected 'running'")
        if not experiment.get("entries_paused"):
            blockers.append("new entries are not paused")

        planned_positions: list[dict[str, Any]] = []
        if positions:
            for position in positions:
                try:
                    planned_positions.append(self._position_plan(position, now))
                except WindDownPreconditionError as exc:
                    blockers.append(str(exc))

        fingerprint = {
            "experiment_code": experiment["code"],
            "operator": operator,
            "reason": reason,
            "entries_paused": bool(experiment.get("entries_paused")),
            "experiment_status": experiment.get("status"),
            "positions": [
                {
                    key: item[key]
                    for key in (
                        "market", "symbol", "quantity", "live_mark_local", "fx_to_usd",
                        "quote_as_of", "fill_price_local", "fees_usd", "slippage_usd",
                        "prior_strategy_snapshot_sha256",
                    )
                }
                for item in planned_positions
            ],
        }
        return {
            "mode": "plan",
            "operation": "r2d2_operator_wind_down",
            "generated_at": now.astimezone(timezone.utc).isoformat(),
            "experiment_code": experiment["code"],
            "experiment_status": experiment.get("status"),
            "entries_paused": bool(experiment.get("entries_paused")),
            "operator": operator,
            "reason": reason,
            "quote_source": "persisted live-stream mark from r2d2_positions",
            "quote_max_age_seconds": self.settings.r2d2_live_quote_max_age_seconds,
            "state_change_required": bool(positions),
            "ready_for_execute": not blockers,
            "blockers": blockers,
            "position_count": len(positions),
            "positions": planned_positions,
            "estimated_realized_pnl_usd": round(
                sum(item["estimated_realized_pnl_usd"] for item in planned_positions), 2,
            ),
            "expected_final_state": {
                "open_positions": 0,
                "entries_paused": True,
                "experiment_status": "running",
            },
            "plan_sha256": _canonical_sha256(fingerprint),
        }

    def execute(
        self,
        *,
        operator: str,
        reason: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        operator, reason = self._operator_reason(operator, reason)
        initial_now = now or self.clock()
        experiment = self.repository.experiment(self.settings.r2d2_experiment_code)
        if experiment is None:
            raise WindDownPreconditionError(
                f"R2D2 experiment not found: {self.settings.r2d2_experiment_code}"
            )

        with self.repository.risk_evaluation_lock(experiment["id"]) as acquired:
            if not acquired:
                raise WindDownPreconditionError("R2D2 risk evaluation is busy; no SELL was attempted")
            preflight = self.plan(operator=operator, reason=reason, now=initial_now)
            if preflight["blockers"]:
                raise WindDownPreconditionError("; ".join(preflight["blockers"]))
            if not preflight["state_change_required"]:
                return {
                    **preflight,
                    "mode": "execute",
                    "executed": False,
                    "idempotent_noop": True,
                    "trade_count": 0,
                    "trades": [],
                    "audit_event_created": False,
                    "remaining_positions": 0,
                }

            cycle_id = self.repository.start_cycle(
                experiment["id"], ["OPERATOR-WIND-DOWN"], "running",
            )
            trades: list[dict[str, Any]] = []
            try:
                for expected in preflight["positions"]:
                    current_experiment = self.repository.experiment(experiment["code"])
                    if current_experiment is None:
                        raise WindDownPreconditionError("R2D2 experiment disappeared during wind-down")
                    if current_experiment.get("status") != "running":
                        raise WindDownPreconditionError("experiment stopped running during wind-down")
                    if not current_experiment.get("entries_paused"):
                        raise WindDownPreconditionError("new entries resumed during wind-down")
                    current_positions = {
                        (item["market"], item["symbol"]): item
                        for item in self.repository.positions(experiment["id"])
                    }
                    position = current_positions.get((expected["market"], expected["symbol"]))
                    if position is None:
                        raise WindDownPreconditionError(
                            f"{expected['market']}:{expected['symbol']}: position changed after plan"
                        )
                    execution_now = initial_now if now is not None else self.clock()
                    planned = self._position_plan(position, execution_now)
                    candidate = {
                        "market": planned["market"],
                        "symbol": planned["symbol"],
                        "name": planned["name"],
                        "currency": planned["currency"],
                        "stop_price": _float(position.get("stop_price_local")),
                        "fundamental_score": 0,
                        "technical_score": 0,
                        "risk_score": 0,
                        "composite_score": 0,
                    }
                    trade_reason = (
                        f"Administrative operator wind-down authorized by {operator}: {reason}"
                    )
                    decision = {
                        **candidate,
                        "paper_only": True,
                        "strategy_excluded": True,
                        "strategy_exclusion_reason": "operator_wind_down",
                        "operator_wind_down": {
                            "operation_id": cycle_id,
                            "operator": operator,
                            "reason": reason,
                            "requested_at": initial_now.astimezone(timezone.utc).isoformat(),
                            "full_position": True,
                            "quote_source": "persisted_live_stream_mark",
                            "quote_status": planned["quote_status"],
                            "quote_as_of": planned["quote_as_of"],
                            "quote_age_seconds": planned["quote_age_seconds"],
                            "position_updated_at": planned["position_updated_at"],
                            "preflight_plan_sha256": preflight["plan_sha256"],
                        },
                        "position_before": {
                            "quantity": planned["quantity"],
                            "average_cost_usd": planned["average_cost_usd"],
                            "live_mark_local": planned["live_mark_local"],
                            "high_water_price_local": _float(position.get("high_water_price_local")),
                            "opened_at": str(position.get("opened_at") or ""),
                            "defense_streak": int(
                                _float((position.get("strategy_snapshot") or {}).get("defense_streak"))
                            ),
                            "defense_reductions": int(
                                _float((position.get("strategy_snapshot") or {}).get("defense_reductions"))
                            ),
                        },
                        "execution_friction": {
                            "slippage_rate": planned["slippage_rate"],
                            "fee_rate": planned["fee_rate"],
                        },
                        "prior_strategy_snapshot_sha256": planned[
                            "prior_strategy_snapshot_sha256"
                        ],
                    }
                    trade = self.repository.execute_trade(
                        current_experiment,
                        cycle_id=cycle_id,
                        candidate=candidate,
                        side="SELL",
                        quantity=planned["quantity"],
                        signal_price=planned["live_mark_local"],
                        fill_price=planned["fill_price_local"],
                        fx=planned["fx_to_usd"],
                        fees=planned["fees_usd"],
                        slippage=planned["slippage_usd"],
                        reason=trade_reason,
                        decision=decision,
                        quote_as_of=_datetime(planned["quote_as_of"]) or execution_now,
                    )
                    trades.append(trade)
                    self.repository.save_decision(
                        experiment["id"], cycle_id, decision, "SELL", [trade_reason], trade["id"],
                    )

                remaining = self.repository.positions(experiment["id"])
                final_experiment = self.repository.experiment(experiment["code"])
                if remaining:
                    raise WindDownPreconditionError(
                        f"wind-down completed with {len(remaining)} open positions"
                    )
                if final_experiment is None or final_experiment.get("status") != "running":
                    raise WindDownPreconditionError("experiment is not running after wind-down")
                if not final_experiment.get("entries_paused"):
                    raise WindDownPreconditionError("entries are not paused after wind-down")

                total_realized = sum(_float(item.get("realized_pnl_usd")) for item in trades)
                detail = {
                    "operation_id": cycle_id,
                    "operator": operator,
                    "reason": reason,
                    "preflight_plan_sha256": preflight["plan_sha256"],
                    "trade_ids": [item["id"] for item in trades],
                    "symbols": [f"{item['market']}:{item['symbol']}" for item in trades],
                    "trade_count": len(trades),
                    "realized_pnl_usd": round(total_realized, 2),
                    "remaining_positions": 0,
                    "entries_paused": True,
                    "experiment_status": "running",
                }
                self.repository.finish_cycle(
                    cycle_id,
                    "succeeded",
                    len(preflight["positions"]),
                    len(preflight["positions"]),
                    len(trades),
                    metadata={"operator_wind_down": detail},
                )
                self.repository.database.record_audit_event(
                    operator,
                    "r2d2.operator_wind_down",
                    "r2d2_experiment",
                    experiment["code"],
                    detail,
                )
                return {
                    **preflight,
                    "mode": "execute",
                    "executed": True,
                    "idempotent_noop": False,
                    "operation_id": cycle_id,
                    "trade_count": len(trades),
                    "trades": [
                        {
                            "id": item["id"],
                            "market": item["market"],
                            "symbol": item["symbol"],
                            "quantity": item["quantity"],
                            "signal_price_local": item["signal_price_local"],
                            "fill_price_local": item["fill_price_local"],
                            "fees_usd": item["fees_usd"],
                            "slippage_usd": item["slippage_usd"],
                            "realized_pnl_usd": item["realized_pnl_usd"],
                        }
                        for item in trades
                    ],
                    "realized_pnl_usd": round(total_realized, 2),
                    "audit_event_created": True,
                    "audit_action": "r2d2.operator_wind_down",
                    "remaining_positions": 0,
                    "entries_paused": True,
                    "experiment_status": "running",
                }
            except Exception as exc:
                remaining = self.repository.positions(experiment["id"])
                error = f"{type(exc).__name__}: {exc}"[:1000]
                failure_detail = {
                    "operation_id": cycle_id,
                    "operator": operator,
                    "reason": reason,
                    "preflight_plan_sha256": preflight["plan_sha256"],
                    "completed_trade_ids": [item["id"] for item in trades],
                    "remaining_symbols": [
                        f"{item['market']}:{item['symbol']}" for item in remaining
                    ],
                    "error": error,
                }
                self.repository.finish_cycle(
                    cycle_id,
                    "failed",
                    len(preflight["positions"]),
                    len(preflight["positions"]),
                    len(trades),
                    error=error,
                    metadata={"operator_wind_down": failure_detail},
                )
                self.repository.database.record_audit_event(
                    operator,
                    "r2d2.operator_wind_down_failed",
                    "r2d2_experiment",
                    experiment["code"],
                    failure_detail,
                )
                raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or execute the audited R2D2 administrative wind-down.",
    )
    parser.add_argument("--operator", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Sell every open paper position. Without this flag the command is read-only.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings()
    service = R2D2WindDownService(
        settings,
        R2D2Repository(Database(settings)),
    )
    try:
        output = (
            service.execute(operator=args.operator, reason=args.reason)
            if args.execute
            else service.plan(operator=args.operator, reason=args.reason)
        )
    except WindDownPreconditionError as exc:
        print(json.dumps({
            "mode": "execute" if args.execute else "plan",
            "operation": "r2d2_operator_wind_down",
            "executed": False,
            "error": str(exc),
        }, sort_keys=True))
        return 2
    print(json.dumps(output, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
