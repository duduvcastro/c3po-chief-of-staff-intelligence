from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, time
from statistics import median
from zoneinfo import ZoneInfo

from .models import (
    AdministrativeUnavailability,
    SecurityDailySnapshot,
    UniverseManifest,
    UniverseMember,
)

NEW_YORK = ZoneInfo("America/New_York")

ELIGIBLE_MICS = {"XNAS", "XNYS"}
ELIGIBLE_SECURITY_TYPES = {
    "US_DOMESTIC_OPERATING_COMPANY_COMMON_STOCK",
    "US_DOMESTIC_EQUITY_REIT_COMMON_STOCK",
}
ALLOWED_SUBSTITUTION_REASONS = {
    "DELISTING_EFFECTIVE_BEFORE_REGULAR_OPEN",
    "MERGER_OR_SECURITY_CANCELLATION_EFFECTIVE_BEFORE_REGULAR_OPEN",
    "POINT_IN_TIME_SYMBOL_MAPPING_RETIRED_BEFORE_REGULAR_OPEN",
}
FORBIDDEN_SUBSTITUTION_REASONS = {
    "MISSING_INTRADAY_BAR",
    "MISSING_LIVE_QUOTE",
    "PROVIDER_OUTAGE",
    "TRADING_HALT",
    "LOW_INTRADAY_VOLUME",
    "INTRADAY_PRICE_MOVE",
}


def _normalized_symbol(symbol: str) -> str:
    return "".join(character for character in symbol.upper().strip() if character.isalnum())


def _quintile(rank: int, total: int) -> int:
    if total <= 0:
        raise ValueError("cannot assign a quintile to an empty universe")
    return min(5, ((rank - 1) * 5 // total) + 1)


def build_d1_universe(
    *,
    session_date: date,
    previous_session_date: date,
    generated_at: datetime,
    d1_information_cutoff_at: datetime,
    snapshots: list[SecurityDailySnapshot],
    unavailability: list[AdministrativeUnavailability] | None = None,
    selection_count: int = 60,
) -> UniverseManifest:
    """Build the immutable Day D universe using information available pre-open.

    Corrections whose ``available_at`` is after ``generated_at`` are invisible.
    Administrative substitutions use only events known by 09:25 ET and never
    recompute the D-1 ranking.
    """

    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    if (
        d1_information_cutoff_at.tzinfo is None
        or d1_information_cutoff_at.utcoffset() is None
    ):
        raise ValueError("d1_information_cutoff_at must be timezone-aware")
    if selection_count <= 0:
        raise ValueError("selection_count must be positive")
    if previous_session_date >= session_date:
        raise ValueError("previous_session_date must precede session_date")
    if d1_information_cutoff_at.date() != previous_session_date:
        raise ValueError("D-1 information cutoff must belong to previous_session_date")
    if generated_at < d1_information_cutoff_at:
        raise ValueError("universe cannot be generated before its D-1 cutoff")

    cutoff = datetime.combine(session_date, time(9, 25), tzinfo=NEW_YORK)
    if generated_at < cutoff:
        effective_cutoff = generated_at
    else:
        effective_cutoff = cutoff

    unavailable_by_symbol: dict[str, AdministrativeUnavailability] = {}
    for event in unavailability or []:
        reason = event.reason_code.upper()
        if reason in FORBIDDEN_SUBSTITUTION_REASONS:
            raise ValueError(f"{reason} cannot remove a symbol from the frozen universe")
        if reason not in ALLOWED_SUBSTITUTION_REASONS:
            raise ValueError(f"unknown administrative unavailability reason: {reason}")
        if event.available_at <= effective_cutoff:
            current = unavailable_by_symbol.get(event.symbol)
            if current is None or event.available_at > current.available_at:
                unavailable_by_symbol[event.symbol] = event

    latest_by_symbol_date: dict[tuple[str, date], SecurityDailySnapshot] = {}
    for snapshot in snapshots:
        if snapshot.session_date > previous_session_date:
            continue
        if snapshot.available_at > d1_information_cutoff_at:
            continue
        key = (snapshot.symbol, snapshot.session_date)
        current = latest_by_symbol_date.get(key)
        if current is None or snapshot.available_at > current.available_at:
            latest_by_symbol_date[key] = snapshot

    history_by_symbol: dict[str, list[SecurityDailySnapshot]] = defaultdict(list)
    for snapshot in latest_by_symbol_date.values():
        history_by_symbol[snapshot.symbol].append(snapshot)

    candidates: list[tuple[float, str, str, SecurityDailySnapshot]] = []
    for symbol, history in history_by_symbol.items():
        history.sort(key=lambda item: item.session_date)
        d1 = next(
            (item for item in reversed(history) if item.session_date == previous_session_date),
            None,
        )
        if d1 is None or not d1.active:
            continue
        if d1.listing_mic not in ELIGIBLE_MICS:
            continue
        if d1.security_type not in ELIGIBLE_SECURITY_TYPES:
            continue
        if d1.adjusted_close_usd < 3.0:
            continue
        completed = [item for item in history if item.session_date <= previous_session_date]
        if len(completed) < 20:
            continue
        window = completed[-20:]
        if len({item.session_date for item in window}) != 20:
            continue
        median_dollar_volume = float(median(item.dollar_volume_usd for item in window))
        candidates.append((
            median_dollar_volume,
            _normalized_symbol(symbol),
            symbol.upper(),
            d1,
        ))

    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

    # The first candidate for an issuer is necessarily its most liquid class.
    ranked_unique_issuers: list[
        tuple[float, str, str, SecurityDailySnapshot]
    ] = []
    seen_issuers: set[str] = set()
    for candidate in candidates:
        d1 = candidate[3]
        if d1.issuer_id in seen_issuers:
            continue
        seen_issuers.add(d1.issuer_id)
        ranked_unique_issuers.append(candidate)

    selected: list[UniverseMember] = []
    skipped: list[tuple[str, str]] = []
    for median_dollar_volume, _normalized, _raw_symbol, d1 in ranked_unique_issuers:
        unavailable = unavailable_by_symbol.get(d1.symbol)
        if unavailable is not None:
            skipped.append((d1.symbol, unavailable.reason_code.upper()))
            continue
        if len(selected) >= selection_count:
            break
        is_substitute = len(selected) + len(skipped) >= selection_count
        substitution_reason = None
        selection_reason = "D1_MEDIAN_DOLLAR_VOLUME"
        if is_substitute and skipped:
            removed_symbol, reason = skipped[len(selected) + len(skipped) - selection_count]
            selection_reason = "PREOPEN_ADMINISTRATIVE_SUBSTITUTION"
            substitution_reason = f"{removed_symbol}:{reason}"
        selected.append(
            UniverseMember(
                rank=len(selected) + 1,
                symbol=d1.symbol,
                issuer_id=d1.issuer_id,
                listing_mic=d1.listing_mic,
                security_type=d1.security_type,
                d1_close_usd=d1.adjusted_close_usd,
                median_dollar_volume_20d_usd=median_dollar_volume,
                history_session_count=20,
                liquidity_quintile=1,
                data_as_of=d1.available_at,
                selection_reason=selection_reason,
                substitution_reason=substitution_reason,
            )
        )

    total = len(selected)
    selected = [
        replace(member, liquidity_quintile=_quintile(member.rank, total))
        for member in selected
    ]
    return UniverseManifest(
        session_date=session_date,
        previous_session_date=previous_session_date,
        generated_at=generated_at,
        information_cutoff_at=d1_information_cutoff_at,
        universe_version="DAY-D-UNIVERSE-v1",
        members=tuple(selected),
        shortfall=max(0, selection_count - total),
    )
