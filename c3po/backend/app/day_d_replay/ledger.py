from __future__ import annotations

from datetime import datetime
from typing import Iterable
from zoneinfo import ZoneInfo

from .models import ClosedTrade, Fill, LedgerRecord, Position, Side, TradePrint

NEW_YORK = ZoneInfo("America/New_York")


def entry_cash_cost(fill: Fill) -> float:
    if fill.side is not Side.BUY:
        raise ValueError("entry fill must be a buy")
    return fill.economic_price * fill.quantity + fill.fee_usd


def exit_cash_proceeds(fill: Fill) -> float:
    if fill.side is not Side.SELL:
        raise ValueError("exit fill must be a sell")
    return fill.economic_price * fill.quantity - fill.fee_usd


def build_closed_trade(
    *,
    position: Position,
    exit_fills: Iterable[Fill],
    entry_official_close_at: datetime | None = None,
    entry_official_close_price: float | None = None,
    cash_dividends: Iterable[tuple[datetime, float]] = (),
    path_trades: Iterable[TradePrint] = (),
    include_transfer_record: bool = True,
    include_dividend_records: bool = True,
) -> tuple[ClosedTrade, tuple[LedgerRecord, ...]]:
    """Close one position and preserve the intraday/overnight R identity."""

    exits = tuple(sorted(exit_fills, key=lambda item: item.filled_at))
    if not exits:
        raise ValueError("a closed trade requires at least one exit fill")
    if any(fill.symbol != position.symbol for fill in exits):
        raise ValueError("exit fills must match the position symbol")
    if sum(fill.quantity for fill in exits) != position.quantity:
        raise ValueError("exit quantities must close the original position exactly")
    if position.risk_budget_usd <= 0:
        raise ValueError("risk budget must be positive")

    entry_cost = entry_cash_cost(position.entry_fill)
    exit_proceeds = sum(exit_cash_proceeds(fill) for fill in exits)
    dividends = tuple(sorted(cash_dividends, key=lambda item: item[0]))
    dividend_total = sum(amount for _, amount in dividends)
    gross_pnl = (
        sum(fill.economic_price * fill.quantity for fill in exits)
        - position.entry_fill.economic_price * position.quantity
    )
    net_pnl = exit_proceeds + dividend_total - entry_cost

    closed_at = exits[-1].filled_at
    carried = any(
        fill.filled_at.astimezone(NEW_YORK).date() != position.session_date
        for fill in exits
    )
    if carried:
        if entry_official_close_at is None or entry_official_close_price is None:
            raise ValueError("carried trade requires its entry-session transfer mark")
        if entry_official_close_price <= 0:
            raise ValueError("entry-session official close must be positive")
        entry_day_exits = [
            fill for fill in exits if fill.filled_at <= entry_official_close_at
        ]
        exited_quantity = sum(fill.quantity for fill in entry_day_exits)
        remaining_at_transfer = position.quantity - exited_quantity
        transfer_value = remaining_at_transfer * entry_official_close_price
        entry_day_dividends = sum(
            amount for event_at, amount in dividends if event_at <= entry_official_close_at
        )
        intraday_pnl = (
            sum(exit_cash_proceeds(fill) for fill in entry_day_exits)
            + transfer_value
            + entry_day_dividends
            - entry_cost
        )
        overnight_pnl = net_pnl - intraday_pnl
    else:
        transfer_value = 0.0
        intraday_pnl = net_pnl
        overnight_pnl = 0.0

    consolidated_r = net_pnl / position.risk_budget_usd
    intraday_r = intraday_pnl / position.risk_budget_usd
    overnight_r = overnight_pnl / position.risk_budget_usd
    if abs(consolidated_r - (intraday_r + overnight_r)) > 1e-10:
        raise AssertionError("R ledger identity was violated")

    path_prices = [
        trade.price
        for trade in path_trades
        if position.opened_at <= trade.event_at <= closed_at
    ]
    path_prices.extend(fill.raw_reference_price for fill in exits)
    if path_prices:
        excursions = [
            (price - position.average_cost_per_share)
            * position.quantity
            / position.risk_budget_usd
            for price in path_prices
        ]
        mfe_r = max(0.0, max(excursions))
        mae_r = min(0.0, min(excursions))
    else:
        mfe_r = 0.0
        mae_r = 0.0

    audit_metadata = {
        "same_symbol_session_reentry": position.same_symbol_session_reentry,
    }
    records: list[LedgerRecord] = [
        LedgerRecord(
            position_id=position.position_id,
            setup_version=position.setup_version,
            symbol=position.symbol,
            session_date=position.session_date,
            component="intraday",
            event_at=position.opened_at,
            event_type="entry_fill",
            cash_delta_usd=-entry_cost,
            mark_delta_usd=0.0,
            r_delta=-entry_cost / position.risk_budget_usd,
            raw_r_lifetime_after_event=-entry_cost / position.risk_budget_usd,
            metadata={"fill_kind": position.entry_fill.kind, **audit_metadata},
        )
    ]
    running_cash_pnl = -entry_cost
    # Compute lifetime values in event order, not construction order. Dividend
    # rows may already have been persisted by the engine, but their cash still
    # belongs in the cumulative value shown by a later exit row.
    timeline: list[tuple[datetime, int, str, object]] = []
    timeline.extend((fill.filled_at, 1, "exit", fill) for fill in exits)
    timeline.extend((event_at, 0, "dividend", amount) for event_at, amount in dividends)
    if carried:
        assert entry_official_close_at is not None
        timeline.append((entry_official_close_at, 2, "transfer", transfer_value))

    for event_at, _priority, event_type, payload in sorted(
        timeline, key=lambda item: (item[0], item[1])
    ):
        if event_type == "exit":
            fill = payload
            assert isinstance(fill, Fill)
            component = (
                "intraday"
                if entry_official_close_at is None
                or fill.filled_at <= entry_official_close_at
                else "overnight"
            )
            proceeds = exit_cash_proceeds(fill)
            running_cash_pnl += proceeds
            records.append(
                LedgerRecord(
                    position_id=position.position_id,
                    setup_version=position.setup_version,
                    symbol=position.symbol,
                    session_date=fill.filled_at.astimezone(NEW_YORK).date(),
                    component=component,
                    event_at=fill.filled_at,
                    event_type="exit_fill",
                    cash_delta_usd=proceeds,
                    mark_delta_usd=0.0,
                    r_delta=proceeds / position.risk_budget_usd,
                    raw_r_lifetime_after_event=(
                        running_cash_pnl / position.risk_budget_usd
                    ),
                    metadata={"fill_kind": fill.kind, **audit_metadata},
                )
            )
            continue

        if event_type == "dividend":
            amount = float(payload)
            running_cash_pnl += amount
            if include_dividend_records:
                component = (
                    "intraday"
                    if entry_official_close_at is None
                    or event_at <= entry_official_close_at
                    else "overnight"
                )
                records.append(
                    LedgerRecord(
                        position_id=position.position_id,
                        setup_version=position.setup_version,
                        symbol=position.symbol,
                        session_date=event_at.astimezone(NEW_YORK).date(),
                        component=component,
                        event_at=event_at,
                        event_type="cash_dividend",
                        cash_delta_usd=amount,
                        mark_delta_usd=0.0,
                        r_delta=amount / position.risk_budget_usd,
                        raw_r_lifetime_after_event=(
                            running_cash_pnl / position.risk_budget_usd
                        ),
                        metadata=dict(audit_metadata),
                    )
                )
            continue

        if include_transfer_record:
            records.append(
                LedgerRecord(
                    position_id=position.position_id,
                    setup_version=position.setup_version,
                    symbol=position.symbol,
                    session_date=position.session_date,
                    component="transfer",
                    event_at=event_at,
                    event_type="official_close_transfer_mark",
                    cash_delta_usd=0.0,
                    mark_delta_usd=float(payload),
                    r_delta=0.0,
                    raw_r_lifetime_after_event=(
                        (running_cash_pnl + float(payload))
                        / position.risk_budget_usd
                    ),
                    metadata={"fictitious_fee_usd": 0.0, **audit_metadata},
                )
            )

    if abs(running_cash_pnl - net_pnl) > 1e-8:
        raise AssertionError("cash ledger does not reconcile to closed-trade P&L")

    closed = ClosedTrade(
        position_id=position.position_id,
        setup_version=position.setup_version,
        symbol=position.symbol,
        entry_fill=position.entry_fill,
        exit_fills=exits,
        risk_budget_usd=position.risk_budget_usd,
        gross_pnl_usd=gross_pnl,
        net_pnl_usd=net_pnl,
        intraday_net_pnl_usd=intraday_pnl,
        overnight_net_pnl_usd=overnight_pnl,
        raw_r=consolidated_r,
        intraday_r=intraday_r,
        overnight_r=overnight_r,
        consolidated_r=consolidated_r,
        mfe_r=mfe_r,
        mae_r=mae_r,
        opened_at=position.opened_at,
        closed_at=closed_at,
        same_symbol_session_reentry=position.same_symbol_session_reentry,
    )
    return closed, tuple(sorted(records, key=lambda item: item.event_at))
