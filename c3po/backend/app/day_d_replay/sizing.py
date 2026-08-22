from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from .costs import execution_fee
from .models import FeeSchedule, SetupSignal, Side


@dataclass(frozen=True, slots=True)
class SizingDecision:
    accepted: bool
    reason: str
    quantity: int
    risk_budget_usd: float
    risk_per_share_usd: float
    initial_stop: float
    entry_fee_usd: float
    estimated_stop_fee_usd: float
    entry_gross_cost_usd: float


def _reject(reason: str, risk_budget: float = 0.0) -> SizingDecision:
    return SizingDecision(
        accepted=False,
        reason=reason,
        quantity=0,
        risk_budget_usd=risk_budget,
        risk_per_share_usd=0.0,
        initial_stop=0.0,
        entry_fee_usd=0.0,
        estimated_stop_fee_usd=0.0,
        entry_gross_cost_usd=0.0,
    )


def size_position(
    *,
    signal: SetupSignal,
    entry_price: float,
    entry_vwap: float,
    entry_at: datetime,
    nav_usd: float,
    cash_usd: float,
    prior_five_minute_volume_shares: float,
    point_half_spread_usd: float,
    fee_schedule: FeeSchedule,
) -> SizingDecision:
    if min(entry_price, entry_vwap, nav_usd, cash_usd) <= 0:
        return _reject("INVALID_POSITIVE_INPUT")
    risk_budget = nav_usd * 0.0015
    if signal.setup_version == "S3-v1":
        structural_stop = max(signal.structural_stop, entry_vwap)
    elif signal.setup_version == "S5-v1":
        structural_stop = signal.structural_stop
    else:
        return _reject("UNKNOWN_SETUP_VERSION", risk_budget)

    minimum_distance = max(
        0.5 * signal.entry_atr,
        2.0 * point_half_spread_usd,
        2.0 * signal.minimum_tick,
    )
    structural_distance = entry_price - structural_stop
    initial_stop = structural_stop
    if structural_distance < minimum_distance:
        initial_stop = entry_price - minimum_distance
    stop_distance = entry_price - initial_stop
    if stop_distance <= 0:
        return _reject("STOP_NOT_BELOW_ENTRY", risk_budget)
    if stop_distance > 2.0 * signal.entry_atr:
        return _reject("STOP_WIDER_THAN_2_ATR", risk_budget)

    # Commission minima make risk/share weakly quantity-dependent. Iterate to a
    # stable integer instead of silently dropping the fee from risk sizing.
    quantity = max(1, math.floor(risk_budget / stop_distance))
    prior_quantity = None
    entry_fee = 0.0
    stop_fee = 0.0
    risk_per_share = 0.0
    for _ in range(12):
        entry_gross = entry_price * quantity
        entry_fee = execution_fee(
            fee_schedule,
            side=Side.BUY,
            quantity=quantity,
            gross_notional_usd=entry_gross,
            event_at=entry_at,
        )
        modeled_stop_price = initial_stop - 2.0 * point_half_spread_usd
        if modeled_stop_price <= 0:
            return _reject("MODELED_STOP_PRICE_NOT_POSITIVE", risk_budget)
        stop_gross = modeled_stop_price * quantity
        stop_fee = execution_fee(
            fee_schedule,
            side=Side.SELL,
            quantity=quantity,
            gross_notional_usd=stop_gross,
            event_at=entry_at,
        )
        entry_basis_per_share = entry_price + entry_fee / quantity
        stop_net_per_share = modeled_stop_price - stop_fee / quantity
        risk_per_share = entry_basis_per_share - stop_net_per_share
        if risk_per_share <= 0:
            return _reject("RISK_PER_SHARE_NOT_POSITIVE", risk_budget)
        updated = math.floor(risk_budget / risk_per_share)
        if updated <= 0:
            return _reject("RISK_BUDGET_BELOW_ONE_SHARE", risk_budget)
        if updated == quantity or updated == prior_quantity:
            quantity = min(quantity, updated)
            break
        prior_quantity, quantity = quantity, updated

    entry_gross = entry_price * quantity
    entry_fee = execution_fee(
        fee_schedule,
        side=Side.BUY,
        quantity=quantity,
        gross_notional_usd=entry_gross,
        event_at=entry_at,
    )
    modeled_stop_price = initial_stop - 2.0 * point_half_spread_usd
    stop_fee = execution_fee(
        fee_schedule,
        side=Side.SELL,
        quantity=quantity,
        gross_notional_usd=modeled_stop_price * quantity,
        event_at=entry_at,
    )
    risk_per_share = (
        entry_price
        + entry_fee / quantity
        - modeled_stop_price
        + stop_fee / quantity
    )
    if entry_gross > nav_usd * 0.20:
        return _reject("POSITION_NOTIONAL_CAP_BREACH", risk_budget)
    if prior_five_minute_volume_shares <= 0:
        return _reject("PRIOR_FIVE_MINUTE_VOLUME_UNAVAILABLE", risk_budget)
    if quantity > math.floor(prior_five_minute_volume_shares * 0.01):
        return _reject("PARTICIPATION_CAP_BREACH", risk_budget)
    if entry_gross + entry_fee > cash_usd:
        return _reject("INSUFFICIENT_CASH", risk_budget)
    return SizingDecision(
        accepted=True,
        reason="ACCEPTED",
        quantity=quantity,
        risk_budget_usd=risk_budget,
        risk_per_share_usd=risk_per_share,
        initial_stop=initial_stop,
        entry_fee_usd=entry_fee,
        estimated_stop_fee_usd=stop_fee,
        entry_gross_cost_usd=entry_gross,
    )
