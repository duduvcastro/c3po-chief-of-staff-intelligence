from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from .costs import execution_fee
from .models import (
    FeeSchedule,
    Fill,
    HaltInterval,
    Quote,
    SetupSignal,
    Side,
    TradePrint,
)


@dataclass(frozen=True, slots=True)
class Activation:
    event_at: datetime
    available_at: datetime
    source_id: str
    source_kind: str


class MarketTape:
    def __init__(
        self,
        *,
        symbol: str,
        trades: Iterable[TradePrint],
        quotes: Iterable[Quote],
        halts: Iterable[HaltInterval] = (),
    ) -> None:
        self.symbol = symbol
        self.trades = tuple(sorted(trades, key=lambda item: (item.event_at, item.trade_id)))
        self.quotes = tuple(sorted(quotes, key=lambda item: (item.event_at, item.quote_id)))
        self.halts = tuple(sorted(halts, key=lambda item: item.start_at))
        if any(item.symbol != symbol for item in (*self.trades, *self.quotes, *self.halts)):
            raise ValueError("market tape cannot mix symbols")

    def halt_at(self, at: datetime) -> HaltInterval | None:
        return next((halt for halt in self.halts if halt.contains(at)), None)

    def latest_quote(self, at: datetime) -> Quote | None:
        eligible = [
            quote
            for quote in self.quotes
            if quote.event_at <= at
            and quote.available_at <= at
            and not quote.crossed
        ]
        return eligible[-1] if eligible else None

    def first_trade_at_or_after(
        self, at: datetime, *, before: datetime | None = None
    ) -> TradePrint | None:
        for trade in self.trades:
            if trade.event_at < at:
                continue
            if before is not None and trade.event_at >= before:
                return None
            halt = self.halt_at(trade.event_at)
            if halt is not None:
                continue
            return trade
        return None

    def latest_trade(self, at: datetime) -> TradePrint | None:
        eligible = [
            trade
            for trade in self.trades
            if trade.event_at <= at and trade.available_at <= at
        ]
        return eligible[-1] if eligible else None

    def observable_times(
        self,
        *,
        after: datetime,
        before: datetime,
    ) -> tuple[datetime, ...]:
        values = {
            item.available_at
            for item in (*self.trades, *self.quotes)
            if after <= item.available_at < before
        }
        return tuple(sorted(values))

    def first_activation(self, signal: SetupSignal) -> Activation | None:
        candidates: list[Activation] = []
        for trade in self.trades:
            if trade.event_at <= signal.decision_at or trade.available_at <= signal.decision_at:
                continue
            if trade.available_at >= signal.expires_at:
                continue
            if trade.price > signal.activation_price:
                candidates.append(
                    Activation(
                        event_at=trade.event_at,
                        available_at=trade.available_at,
                        source_id=trade.trade_id,
                        source_kind="trade",
                    )
                )
        for quote in self.quotes:
            if quote.crossed:
                continue
            if quote.event_at <= signal.decision_at or quote.available_at <= signal.decision_at:
                continue
            if quote.available_at >= signal.expires_at:
                continue
            if quote.ask > signal.activation_price:
                candidates.append(
                    Activation(
                        event_at=quote.event_at,
                        available_at=quote.available_at,
                        source_id=quote.quote_id,
                        source_kind="quote",
                    )
                )
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item.available_at, item.event_at, item.source_id))

    def first_upward_activation(
        self,
        *,
        level: float,
        after: datetime,
        before: datetime,
    ) -> Activation | None:
        """Find the first observable event that makes a long exit executable."""

        candidates: list[Activation] = []
        for trade in self.trades:
            if trade.event_at <= after or trade.available_at <= after:
                continue
            if trade.available_at >= before:
                continue
            if trade.price >= level:
                candidates.append(
                    Activation(
                        event_at=trade.event_at,
                        available_at=trade.available_at,
                        source_id=trade.trade_id,
                        source_kind="trade",
                    )
                )
        for quote in self.quotes:
            if quote.crossed:
                continue
            if quote.event_at <= after or quote.available_at <= after:
                continue
            if quote.available_at >= before:
                continue
            if quote.bid >= level:
                candidates.append(
                    Activation(
                        event_at=quote.event_at,
                        available_at=quote.available_at,
                        source_id=quote.quote_id,
                        source_kind="quote",
                    )
                )
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item.available_at, item.event_at, item.source_id))


def deterministic_latency_milliseconds(
    *,
    run_seed: int,
    order_key: str,
    fixed_latency_milliseconds: int | None = None,
) -> int:
    if fixed_latency_milliseconds is not None:
        if fixed_latency_milliseconds < 0:
            raise ValueError("fixed latency cannot be negative")
        return fixed_latency_milliseconds
    digest = hashlib.sha256(f"{run_seed}|{order_key}".encode("utf-8")).digest()
    jitter = int.from_bytes(digest[:8], "big") % 501 - 250
    return 500 + jitter


def _milliseconds(delta: timedelta) -> int:
    return max(0, int(round(delta.total_seconds() * 1000)))


class ExecutionModel:
    def __init__(
        self,
        *,
        fee_schedule: FeeSchedule,
        run_seed: int,
        fixed_latency_milliseconds: int | None = None,
    ) -> None:
        self.fee_schedule = fee_schedule
        self.run_seed = run_seed
        self.fixed_latency_milliseconds = fixed_latency_milliseconds

    def _latency(self, order_key: str) -> int:
        return deterministic_latency_milliseconds(
            run_seed=self.run_seed,
            order_key=order_key,
            fixed_latency_milliseconds=self.fixed_latency_milliseconds,
        )

    @staticmethod
    def _after_halt(tape: MarketTape, arrival_at: datetime) -> datetime:
        current = arrival_at
        while (halt := tape.halt_at(current)) is not None:
            if halt.end_at <= current:
                raise ValueError("halt interval did not advance execution time")
            current = halt.end_at
        return current

    def fill_entry(
        self,
        *,
        signal: SetupSignal,
        tape: MarketTape,
        quantity: int,
        half_spread_usd: float,
        quote_max_age_milliseconds: int,
        order_sequence: int = 1,
    ) -> Fill | None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        activation = tape.first_activation(signal)
        if activation is None:
            return None
        decision_at = activation.available_at
        latency_ms = self._latency(
            f"{signal.session_date}|{signal.symbol}|{signal.setup_version}|BUY|{order_sequence}"
        )
        arrival_at = decision_at + timedelta(milliseconds=latency_ms)
        arrival_at = self._after_halt(tape, arrival_at)
        if arrival_at >= signal.expires_at:
            return None

        quote = tape.latest_quote(arrival_at)
        quote_age_ms = (
            _milliseconds(arrival_at - quote.event_at) if quote is not None else None
        )
        fresh = quote is not None and quote_age_ms <= quote_max_age_milliseconds
        trade: TradePrint | None = None
        if fresh:
            assert quote is not None
            raw_reference = quote.midpoint
            economic_price = max(quote.ask, quote.midpoint + half_spread_usd)
            filled_at = arrival_at
            used_trade_fallback = False
        else:
            trade = tape.first_trade_at_or_after(arrival_at, before=signal.expires_at)
            if trade is None:
                return None
            stale_ask = quote.ask if quote is not None else float("-inf")
            raw_reference = trade.price
            economic_price = max(stale_ask, trade.price + half_spread_usd)
            filled_at = trade.event_at
            used_trade_fallback = True
        gross = economic_price * quantity
        fee = execution_fee(
            self.fee_schedule,
            side=Side.BUY,
            quantity=quantity,
            gross_notional_usd=gross,
            event_at=filled_at,
        )
        return Fill(
            symbol=signal.symbol,
            side=Side.BUY,
            kind="entry",
            decision_at=decision_at,
            arrival_at=arrival_at,
            filled_at=filled_at,
            raw_reference_price=raw_reference,
            economic_price=economic_price,
            quantity=quantity,
            spread_cost_per_share_usd=half_spread_usd,
            fee_usd=fee,
            quote_id=quote.quote_id if quote is not None else None,
            trade_id=trade.trade_id if trade is not None else activation.source_id,
            latency_milliseconds=latency_ms,
            quote_age_milliseconds=quote_age_ms,
            used_trade_fallback=used_trade_fallback,
        )

    def fill_ordinary_sell(
        self,
        *,
        tape: MarketTape,
        symbol: str,
        decision_at: datetime,
        quantity: int,
        half_spread_usd: float,
        quote_max_age_milliseconds: int,
        kind: str,
        before: datetime,
        order_key: str,
    ) -> Fill | None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        latency_ms = self._latency(order_key)
        arrival_at = self._after_halt(
            tape, decision_at + timedelta(milliseconds=latency_ms)
        )
        if arrival_at >= before:
            return None
        quote = tape.latest_quote(arrival_at)
        quote_age_ms = (
            _milliseconds(arrival_at - quote.event_at) if quote is not None else None
        )
        fresh = quote is not None and quote_age_ms <= quote_max_age_milliseconds
        trade: TradePrint | None = None
        if fresh:
            assert quote is not None
            raw_reference = quote.midpoint
            economic_price = min(quote.bid, quote.midpoint - half_spread_usd)
            filled_at = arrival_at
            used_trade_fallback = False
        else:
            trade = tape.first_trade_at_or_after(arrival_at, before=before)
            if trade is None:
                return None
            stale_bid = quote.bid if quote is not None else float("inf")
            raw_reference = trade.price
            economic_price = min(stale_bid, trade.price - half_spread_usd)
            filled_at = trade.event_at
            used_trade_fallback = True
        if economic_price <= 0:
            raise ValueError("modeled sell price must be positive")
        gross = economic_price * quantity
        fee = execution_fee(
            self.fee_schedule,
            side=Side.SELL,
            quantity=quantity,
            gross_notional_usd=gross,
            event_at=filled_at,
        )
        return Fill(
            symbol=symbol,
            side=Side.SELL,
            kind=kind,
            decision_at=decision_at,
            arrival_at=arrival_at,
            filled_at=filled_at,
            raw_reference_price=raw_reference,
            economic_price=economic_price,
            quantity=quantity,
            spread_cost_per_share_usd=half_spread_usd,
            fee_usd=fee,
            quote_id=quote.quote_id if quote is not None else None,
            trade_id=trade.trade_id if trade is not None else None,
            latency_milliseconds=latency_ms,
            quote_age_milliseconds=quote_age_ms,
            used_trade_fallback=used_trade_fallback,
        )

    @staticmethod
    def find_stop_trigger(
        *,
        tape: MarketTape,
        stop_level: float,
        after: datetime,
        before: datetime,
        minimum_notional_usd: float = 5000.0,
        minimum_separation_milliseconds: int = 100,
        maximum_window_milliseconds: int = 1000,
    ) -> TradePrint | None:
        breaches: list[TradePrint] = []
        observed = sorted(
            tape.trades,
            key=lambda item: (item.available_at, item.event_at, item.trade_id),
        )
        for trade in observed:
            if trade.event_at <= after or trade.available_at <= after:
                continue
            if trade.available_at >= before:
                continue
            if tape.halt_at(trade.event_at) is not None:
                continue
            if trade.price > stop_level:
                breaches.clear()
                continue
            cutoff = trade.event_at - timedelta(milliseconds=maximum_window_milliseconds)
            breaches = [item for item in breaches if item.event_at >= cutoff]
            if all(item.trade_id != trade.trade_id for item in breaches):
                breaches.append(trade)
            if len(breaches) < 2:
                continue
            first = breaches[0]
            separated = any(
                _milliseconds(trade.event_at - item.event_at)
                >= minimum_separation_milliseconds
                for item in breaches[:-1]
            )
            notional = sum(item.notional_usd for item in breaches)
            if separated and notional >= minimum_notional_usd:
                return trade
        return None

    def fill_stop_sell(
        self,
        *,
        tape: MarketTape,
        symbol: str,
        stop_level: float,
        after: datetime,
        before: datetime,
        quantity: int,
        half_spread_usd: float,
        kind: str,
        order_key: str,
    ) -> Fill | None:
        trigger = self.find_stop_trigger(
            tape=tape,
            stop_level=stop_level,
            after=after,
            before=before,
        )
        if trigger is None:
            return None
        return self.fill_stop_from_trigger(
            tape=tape,
            symbol=symbol,
            stop_level=stop_level,
            trigger=trigger,
            before=before,
            quantity=quantity,
            half_spread_usd=half_spread_usd,
            kind=kind,
            order_key=order_key,
        )

    def fill_stop_from_trigger(
        self,
        *,
        tape: MarketTape,
        symbol: str,
        stop_level: float,
        trigger: TradePrint,
        before: datetime,
        quantity: int,
        half_spread_usd: float,
        kind: str,
        order_key: str,
        reopening_halt: HaltInterval | None = None,
    ) -> Fill | None:
        latency_ms = self._latency(order_key)
        if reopening_halt is None:
            decision_at = trigger.available_at
            arrival_at = self._after_halt(
                tape, decision_at + timedelta(milliseconds=latency_ms)
            )
            trade = tape.first_trade_at_or_after(arrival_at, before=before)
        else:
            # The protective order is treated as resting through the halt. It
            # cannot fill while halted and receives the first reopening print.
            decision_at = reopening_halt.start_at
            arrival_at = reopening_halt.end_at
            trade = trigger
        if trade is None:
            return None
        full_spread = 2.0 * half_spread_usd
        raw_reference = min(stop_level, trade.price)
        economic_price = min(
            stop_level - full_spread,
            trade.price - full_spread,
        )
        if economic_price <= 0:
            raise ValueError("modeled stop price must be positive")
        gross = economic_price * quantity
        fee = execution_fee(
            self.fee_schedule,
            side=Side.SELL,
            quantity=quantity,
            gross_notional_usd=gross,
            event_at=trade.event_at,
        )
        return Fill(
            symbol=symbol,
            side=Side.SELL,
            kind=kind,
            decision_at=decision_at,
            arrival_at=arrival_at,
            filled_at=trade.event_at,
            raw_reference_price=raw_reference,
            economic_price=economic_price,
            quantity=quantity,
            spread_cost_per_share_usd=full_spread,
            fee_usd=fee,
            quote_id=None,
            trade_id=trade.trade_id,
            latency_milliseconds=latency_ms,
            quote_age_milliseconds=None,
            used_trade_fallback=True,
        )
