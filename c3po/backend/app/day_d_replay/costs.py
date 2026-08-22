from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from .models import CostScenario, FeeSchedule, Side, SpreadCell

NEW_YORK = ZoneInfo("America/New_York")
MINIMUM_CELL_OBSERVATIONS = 100


def time_bucket(
    at: datetime,
    *,
    regular_open: datetime,
    official_close: datetime,
) -> str:
    """Map an event to a causal liquidity bucket, including early closes."""

    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("at must be timezone-aware")
    local_at = at.astimezone(NEW_YORK)
    local_open = regular_open.astimezone(NEW_YORK)
    local_close = official_close.astimezone(NEW_YORK)
    if not local_open <= local_at < local_close:
        raise ValueError("event is outside the regular session")
    if local_at < local_open + timedelta(minutes=15):
        return "OPEN_15"
    if local_at < local_open + timedelta(minutes=60):
        return "OPEN_60"
    if local_at < local_close - timedelta(minutes=30):
        return "MIDDAY"
    if local_at < local_close - timedelta(minutes=5):
        return "CLOSE_30"
    return "CLOSE_5"


@dataclass(frozen=True, slots=True)
class CostTable:
    version: str
    cells: tuple[SpreadCell, ...]

    @classmethod
    def from_cells(cls, version: str, cells: Iterable[SpreadCell]) -> "CostTable":
        return cls(version=version, cells=tuple(cells))

    def half_spread(
        self,
        *,
        liquidity_quintile: int,
        bucket: str,
        scenario: CostScenario,
        replay_session: date,
        information_cutoff_at: datetime,
    ) -> float:
        if information_cutoff_at.tzinfo is None or information_cutoff_at.utcoffset() is None:
            raise ValueError("cost information cutoff must be timezone-aware")
        candidates = [
            cell
            for cell in self.cells
            if cell.liquidity_quintile == liquidity_quintile
            and cell.time_bucket == bucket
            and cell.source_sessions_end < replay_session
            and cell.available_at <= information_cutoff_at
        ]
        candidates.sort(
            key=lambda cell: (cell.source_sessions_end, cell.available_at),
            reverse=True,
        )
        cell = next(
            (
                item
                for item in candidates
                if item.observation_count >= MINIMUM_CELL_OBSERVATIONS
            ),
            None,
        )
        if cell is None:
            fallback = [
                item
                for item in self.cells
                if item.liquidity_quintile == liquidity_quintile
                and item.time_bucket == "ALL"
                and item.source_sessions_end < replay_session
                and item.available_at <= information_cutoff_at
                and item.observation_count >= MINIMUM_CELL_OBSERVATIONS
            ]
            fallback.sort(
                key=lambda item: (item.source_sessions_end, item.available_at),
                reverse=True,
            )
            cell = fallback[0] if fallback else None
        if cell is None:
            raise ValueError(
                f"no causal spread cell for quintile={liquidity_quintile} bucket={bucket}"
            )
        if scenario is CostScenario.OPTIMISTIC:
            return cell.half_spread_p25_usd
        if scenario is CostScenario.POINT:
            return cell.half_spread_p50_usd
        if scenario is CostScenario.PESSIMISTIC:
            return 2.0 * cell.half_spread_p50_usd
        raise ValueError(f"unsupported cost scenario: {scenario}")


def execution_fee(
    schedule: FeeSchedule,
    *,
    side: Side,
    quantity: int,
    gross_notional_usd: float,
    event_at: datetime,
) -> float:
    if quantity <= 0 or gross_notional_usd <= 0:
        raise ValueError("fee inputs must be positive")
    if event_at < schedule.effective_at:
        raise ValueError("fee schedule was not effective at the execution event")
    commission = max(
        schedule.minimum_commission_usd,
        schedule.commission_per_share_usd * quantity,
    )
    if side is Side.BUY:
        return commission
    regulatory = gross_notional_usd * schedule.sec_section_31_rate
    taf = min(
        schedule.finra_taf_cap_usd,
        schedule.finra_taf_per_share_usd * quantity,
    )
    return commission + regulatory + taf


def breakeven_win_rate(
    *, target_r: float, winning_trade_cost_r: float, losing_trade_cost_r: float
) -> float:
    denominator = 1.0 + target_r + losing_trade_cost_r - winning_trade_cost_r
    if denominator <= 0:
        raise ValueError("breakeven denominator must be positive")
    return (1.0 + losing_trade_cost_r) / denominator
