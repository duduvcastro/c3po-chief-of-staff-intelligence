"""Pure candidate contract for the signed V2 shadow policy; no providers or I/O.

Calendars, raw regular daily bars and evidence are supplied by the collector.
Availability of an input is distinct from its validity: a resolved missing risk
score freezes an ineligible snapshot, while a missing quote can remain pending.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from types import MappingProxyType
from typing import Mapping, NamedTuple, TypeGuard, cast
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
RISK_C75 = 44.10596901963097
SLIPPAGE = 0.0010
FEE = 0.0004
EVIDENCE_COMPONENTS = ("quote", "universe", "risk", "daily", "splits", "earnings", "calendar")
ALLOWED_SECURITY_TYPES = frozenset(("COMMON_STOCK", "COMMON_STOCK_ADR"))


@dataclass(frozen=True, slots=True)
class DailyBar:
    """One complete regular-session bar in unadjusted historical share units."""
    session_date: date | None
    open: object
    high: object
    low: object
    close: object
    volume: object
    source_at: datetime | None
    available_at: datetime | None
    complete: bool = False
    regular_session: bool = False


class SplitRecord(NamedTuple):
    effective_at: datetime | None
    ratio: object  # new shares / old shares, validated before arithmetic
    source_at: datetime | None
    available_at: datetime | None


@dataclass(frozen=True, slots=True)
class CandidateInputs:
    symbol: str = ""
    market: str | None = None
    security_type: str | None = None
    session_date: date | None = None
    decision_at: datetime | None = None
    bid: float | None = None
    ask: float | None = None
    bid_at: datetime | None = None
    ask_at: datetime | None = None
    risk_score: object = None
    daily_bars: tuple[DailyBar, ...] = ()
    previous_sessions: tuple[date, ...] = ()  # exact 61 official sessions before entry
    horizon_sessions: tuple[date, ...] = ()  # exact 10 official sessions, entry included
    horizon_close_at: datetime | None = None  # official close of the tenth session
    splits: tuple[SplitRecord, ...] = ()
    split_coverage_verified: bool = False
    daily_price_basis: str | None = None  # must be RAW_UNADJUSTED
    earnings_dates: tuple[date, ...] = ()  # date-only announcements
    earnings_at: tuple[datetime | None, ...] = ()  # failed parsing remains invalid input
    earnings_coverage_start: date | None = None
    earnings_coverage_end: date | None = None
    earnings_coverage_verified: bool = False
    # Metadata also represents completed queries with absent/invalid field values.
    source_at: Mapping[str, datetime | None] = field(default_factory=dict)
    available_at: Mapping[str, datetime | None] = field(default_factory=dict)
    sources: Mapping[str, str | None] = field(default_factory=dict)
    source_versions: Mapping[str, str | None] = field(default_factory=dict)
    source_hashes: Mapping[str, str] = field(default_factory=dict)
    source_issues: tuple[str, ...] = ()  # completed but integrity-invalid upstream responses


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    status: str
    reasons: tuple[str, ...]
    complete: bool
    symbol: str | None
    market: str | None
    session_date: date | None
    decision_at: datetime | None
    maturity_at: datetime | None
    risk_score: float | None
    atr14: float | None
    adv20: float | None
    spread: float | None
    geometry: Mapping[str, float] | None
    provenance: tuple[tuple[str, str | None, str | None, str | None, datetime | None, datetime | None], ...]

    @property
    def arm(self) -> str | None:
        return self.status if self.status in ("ELIGIBLE", "CONTROL") else None

    def to_dict(self) -> dict:
        def iso(value):
            return value.astimezone(timezone.utc).isoformat() if isinstance(value, datetime) else value.isoformat() if isinstance(value, date) else None
        return {
            "status": self.status, "arm": self.arm, "reasons": list(self.reasons),
            "input_complete": self.complete, "research_eligible": self.arm is not None,
            "portfolio_eligible": self.arm == "ELIGIBLE",
            "symbol": self.symbol, "market": self.market,
            "session_date": iso(self.session_date), "decision_at": iso(self.decision_at),
            "opened_at": iso(self.decision_at), "maturity_at": iso(self.maturity_at),
            "risk_score": self.risk_score, "atr14": self.atr14, "adv20": self.adv20,
            "spread": self.spread, "geometry": dict(self.geometry) if self.geometry else None,
            "research_quantity": 1.0 if self.arm is not None else None,
            "provenance": {name: {"source": source, "version": version, "sha256": digest,
                "source_at": iso(source_at), "available_at": iso(available_at)}
                for name, source, version, digest, source_at, available_at in self.provenance},
        }


class CandidateValidationError(ValueError):
    def __init__(self, code: str, *, data: bool = True):
        super().__init__(code)
        self.code, self.data = code, data


def _require(condition: bool, code: str, *, data: bool = True) -> None:
    if not condition:
        raise CandidateValidationError(code, data=data)


def _number(value: object) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        number = float(cast(int | float, value))
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _aware(value: object) -> TypeGuard[datetime]:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _day(value: object) -> TypeGuard[date]:
    return type(value) is date


def _causal(source_at: object, available_at: object, decision_at: datetime) -> bool:
    return _aware(source_at) and _aware(available_at) and source_at <= available_at <= decision_at


def input_complete(inputs: CandidateInputs) -> bool:
    """Readiness only, never a retry opportunity based on eligibility.

    Completed source responses are denoted by available_at, even if risk or
    classification is absent. Missing quote fields remain pending. Integrity,
    freshness, coverage and thresholds are checked only by evaluate_candidate.
    """
    return (
        isinstance(inputs, CandidateInputs)
        and all(value is not None for value in (inputs.session_date, inputs.decision_at,
                                                inputs.bid, inputs.ask, inputs.bid_at, inputs.ask_at))
        and isinstance(inputs.available_at, Mapping)
        and all(inputs.available_at.get(component) is not None for component in EVIDENCE_COMPONENTS)
    )


def daily_metrics(
    bars: tuple[DailyBar, ...], previous_sessions: tuple[date, ...], splits: tuple[SplitRecord, ...],
    *, decision_at: datetime, session_date: date, price_basis: str | None,
) -> tuple[float, float]:
    """Wilder ATR14 from 60 TRs; ADV20 from raw close*raw volume.

    The authoritative exchange session sequence is supplied, not inferred from
    weekdays. Historical bars are adjusted only for known, effective splits;
    volume need not be adjusted because raw dollar turnover is unit invariant.
    """
    _require(_aware(decision_at) and _day(session_date), "DAILY_CLOCK_INVALID")
    _require(price_basis == "RAW_UNADJUSTED", "DAILY_PRICE_BASIS_UNVERIFIED")
    _require(type(previous_sessions) is tuple and len(previous_sessions) == 61
             and all(_day(day) for day in previous_sessions), "DAILY_CALENDAR_INVALID")
    _require(list(previous_sessions) == sorted(set(previous_sessions))
             and previous_sessions[-1] < session_date, "DAILY_CALENDAR_INVALID")
    _require(type(bars) is tuple and len(bars) == 61 and all(type(bar) is DailyBar for bar in bars), "DAILY_BARS_COUNT_OR_TYPE")
    _require(tuple(bar.session_date for bar in bars) == previous_sessions, "DAILY_SESSION_MISMATCH")
    _require(type(splits) is tuple and all(type(split) is SplitRecord for split in splits), "SPLIT_RECORD_INVALID")
    effective = []
    split_instants = set()
    for split in splits:
        ratio = _number(split.ratio)
        _require(_aware(split.effective_at) and ratio is not None and ratio > 0
                 and _causal(split.source_at, split.available_at, decision_at), "SPLIT_RECORD_INVALID")
        assert _aware(split.effective_at) and ratio is not None
        _require(split.effective_at not in split_instants, "SPLIT_DUPLICATE_EFFECTIVE_AT")
        split_instants.add(split.effective_at)
        if split.effective_at <= decision_at:
            effective.append((split.effective_at.astimezone(NEW_YORK).date(), ratio))
    normalized = []
    turnovers = []
    for bar in bars:
        values = [_number(value) for value in (bar.open, bar.high, bar.low, bar.close, bar.volume)]
        _require(all(value is not None for value in values), "DAILY_VALUE_INVALID")
        open_, high, low, close, volume = values
        assert open_ is not None and high is not None and low is not None and close is not None and volume is not None
        assert _day(bar.session_date)  # The exact calendar sequence was validated above.
        _require(min(open_, high, low, close) > 0 and volume >= 0
                 and low <= min(open_, close) <= max(open_, close) <= high, "DAILY_OHLC_INVALID")
        _require(bar.complete is True and bar.regular_session is True, "DAILY_NOT_COMPLETE_REGULAR")
        _require(_causal(bar.source_at, bar.available_at, decision_at), "DAILY_EVIDENCE_NOT_CAUSAL")
        factor = math.prod(ratio for effective_date, ratio in effective if bar.session_date < effective_date)
        _require(math.isfinite(factor) and factor > 0, "SPLIT_FACTOR_INVALID")
        normalized.append((high / factor, low / factor, close / factor))
        turnover = close * volume
        _require(math.isfinite(turnover), "DAILY_TURNOVER_INVALID")
        turnovers.append(turnover)
    ranges = [max(high - low, abs(high - normalized[index - 1][2]), abs(low - normalized[index - 1][2]))
              for index, (high, low, _) in enumerate(normalized) if index]
    atr = sum(ranges[:14]) / 14
    for true_range in ranges[14:]:
        atr = (13 * atr + true_range) / 14
    adv = sum(turnovers[-20:]) / 20
    _require(math.isfinite(atr) and atr > 0 and math.isfinite(adv), "DAILY_METRIC_INVALID")
    return atr, adv


def entry_geometry(mid: object, atr: object) -> dict[str, float]:
    mid, atr = _number(mid), _number(atr)
    _require(mid is not None and mid > 0 and atr is not None and atr > 0, "GEOMETRY_INPUT_INVALID")
    assert mid is not None and atr is not None
    buy = mid * (1 + SLIPPAGE)
    cost = buy * (1 + FEE)
    stop = buy - 1.5 * atr
    net_factor = (1 - SLIPPAGE) * (1 - FEE)
    risk = cost - stop * net_factor
    target = (cost + risk) / net_factor
    result = {"P": mid, "B": buy, "C": cost, "S": stop, "T": target, "R_unit": risk}
    _require(all(math.isfinite(value) for value in result.values()), "GEOMETRY_VALUE_INVALID")
    _require(0 < stop < mid < target and risk > 0, "GEOMETRY_INELIGIBLE", data=False)
    return result


def evaluate_candidate(inputs: CandidateInputs) -> CandidateEvaluation:
    """Evaluate one frozen snapshot; all non-score gates precede R1 division."""
    if not isinstance(inputs, CandidateInputs):
        raise TypeError("CANDIDATE_INPUTS_TYPE")
    reasons: list[str] = []
    data_invalid = False
    atr = adv = spread = geometry = maturity = None
    decision = inputs.decision_at if _aware(inputs.decision_at) else None
    session = inputs.session_date if _day(inputs.session_date) else None
    risk = _number(inputs.risk_score)
    complete = input_complete(inputs)

    def reject(code: str, *, data: bool = True):
        nonlocal data_invalid
        reasons.append(code)
        data_invalid = data_invalid or data

    if not complete:
        reject("SNAPSHOT_INCOMPLETE")
    if type(inputs.source_issues) is not tuple or not all(isinstance(code, str) for code in inputs.source_issues):
        reject("SOURCE_DIAGNOSTICS_INVALID")
    else:
        for code in inputs.source_issues:
            reject("SOURCE_" + code)
    if decision is None or session is None:
        reject("DECISION_CLOCK_INVALID")
    elif decision.astimezone(NEW_YORK).date() != session or not time(10) <= decision.astimezone(NEW_YORK).time() < time(10, 1):
        reject("OUTSIDE_CAPTURE_WINDOW")
    evidence = []
    maps = (inputs.sources, inputs.source_versions, inputs.source_hashes, inputs.source_at, inputs.available_at)
    maps_valid = all(isinstance(value, Mapping) for value in maps)
    for name in EVIDENCE_COMPONENTS:
        values = [mapping.get(name) if maps_valid else None for mapping in maps]
        source, version, digest, source_at, available_at = values
        evidence.append((name, source if isinstance(source, str) else None,
                         version if isinstance(version, str) else None, digest if isinstance(digest, str) else None,
                         source_at if _aware(source_at) else None, available_at if _aware(available_at) else None))
        if not all(isinstance(value, str) and value.strip() for value in (source, version)) or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            reject("EVIDENCE_PROVENANCE_" + name.upper())
        if decision is None or not _causal(source_at, available_at, decision):
            reject("EVIDENCE_NOT_CAUSAL_" + name.upper())
    if not isinstance(inputs.symbol, str) or not inputs.symbol.strip():
        reject("SYMBOL_UNVERIFIED")
    if inputs.market not in ("NYSE", "NASDAQ"):
        reject("MARKET_INELIGIBLE", data=inputs.market is None)
    if not isinstance(inputs.security_type, str) or inputs.security_type not in ALLOWED_SECURITY_TYPES:
        reject("SECURITY_TYPE_INELIGIBLE", data=inputs.security_type is None)
    horizon = inputs.horizon_sessions
    horizon_valid = (type(horizon) is tuple and len(horizon) == 10 and all(_day(day) for day in horizon)
                     and list(horizon) == sorted(set(horizon)) and horizon[0] == session)
    close = inputs.horizon_close_at
    if not horizon_valid or not _aware(close) or close.astimezone(NEW_YORK).date() != horizon[-1] or close.astimezone(NEW_YORK).time() <= time(10, 5):
        reject("HORIZON_CALENDAR_INVALID")
    else:
        maturity = close - timedelta(minutes=5)
    bid, ask = _number(inputs.bid), _number(inputs.ask)
    if bid is None or ask is None or not 0 < bid <= ask:
        reject("QUOTE_INVALID")
    else:
        mid = bid + (ask - bid) / 2
        spread = (ask - bid) / mid
        if not math.isfinite(mid) or not math.isfinite(spread):
            spread = None
            reject("QUOTE_INVALID")
        else:
            if mid < 5:
                reject("PRICE_BELOW_MINIMUM", data=False)
            if spread > .0020:
                reject("SPREAD_TOO_WIDE", data=False)
    for name, at in (("BID", inputs.bid_at), ("ASK", inputs.ask_at)):
        if decision is None or not _aware(at) or not 0 <= (decision - at).total_seconds() <= 10:
            reject("QUOTE_AGE_" + name)
        elif maps_valid and _aware(inputs.available_at.get("quote")) and at > cast(datetime, inputs.available_at["quote"]):
            reject("QUOTE_AVAILABILITY_" + name)
    if inputs.split_coverage_verified is not True:
        reject("SPLIT_COVERAGE_UNVERIFIED")
    if decision is not None and session is not None:
        try:
            atr, adv = daily_metrics(inputs.daily_bars, inputs.previous_sessions, inputs.splits,
                                     decision_at=decision, session_date=session, price_basis=inputs.daily_price_basis)
            if adv < 15_000_000:
                reject("ADV20_BELOW_MINIMUM", data=False)
        except CandidateValidationError as exc:
            reject(exc.code, data=exc.data)
    if atr is not None and bid is not None and ask is not None and 0 < bid <= ask:
        try:
            geometry = entry_geometry(bid + (ask - bid) / 2, atr)
        except CandidateValidationError as exc:
            reject(exc.code, data=exc.data)
    if (inputs.earnings_coverage_verified is not True or not horizon_valid
            or not _day(inputs.earnings_coverage_start) or not _day(inputs.earnings_coverage_end)
            or inputs.earnings_coverage_start > horizon[0] or inputs.earnings_coverage_end < horizon[-1]):
        reject("EARNINGS_COVERAGE_UNVERIFIED")
    if type(inputs.earnings_dates) is not tuple or not all(_day(day) for day in inputs.earnings_dates):
        reject("EARNINGS_DATES_INVALID")
    elif horizon_valid:
        for day in inputs.earnings_dates:
            if horizon[0] < day < horizon[-1]:
                reject("EARNINGS_WITHIN_HORIZON", data=False)
                break
            if day in (horizon[0], horizon[-1]):
                # A date without time cannot prove it falls outside entry/exit instants.
                reject("EARNINGS_BOUNDARY_TIME_UNKNOWN")
                break
    if type(inputs.earnings_at) is not tuple or not all(_aware(at) for at in inputs.earnings_at):
        reject("EARNINGS_INSTANT_INVALID")
    elif decision is not None and maturity is not None and any(decision <= at <= maturity for at in cast(tuple[datetime, ...], inputs.earnings_at)):
        reject("EARNINGS_WITHIN_HORIZON", data=False)
    # Only after all common gates, divide the research population into R1 arms.
    if risk is None or not 0 <= risk <= 100:
        reject("RISK_SCORE_INVALID")
    if reasons:
        status = "DATA_INELIGIBLE" if data_invalid else "INELIGIBLE"
    else:
        assert risk is not None  # Invalid scores always add RISK_SCORE_INVALID above.
        status = "ELIGIBLE" if risk <= RISK_C75 else "CONTROL"
    return CandidateEvaluation(status=status, reasons=tuple(dict.fromkeys(reasons)), complete=complete,
        symbol=inputs.symbol if isinstance(inputs.symbol, str) else None,
        market=inputs.market if isinstance(inputs.market, str) else None,
        session_date=session, decision_at=decision, maturity_at=maturity,
        risk_score=risk, atr14=atr, adv20=adv, spread=spread,
        geometry=MappingProxyType(geometry) if geometry else None, provenance=tuple(evidence))
