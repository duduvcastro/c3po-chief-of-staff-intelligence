from __future__ import annotations

from datetime import date
from typing import Any


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def canonical_symbol(symbol: str) -> str:
    clean = symbol.strip().upper()
    return clean[:-3] if clean.endswith(".SA") else clean


def fmp_forward_quality(packet: dict[str, Any] | None, *, as_of: date) -> dict[str, Any] | None:
    """Return the frozen V3 forward-quality pair from one V2.1 packet.

    ROE and growth always come from the same FMP packet. Growth requires two
    positive forward fiscal-year revenue estimates; no trailing field is used
    to complete an otherwise partial forward record.
    """
    packet = packet or {}
    ratios: list[tuple[date, float]] = []
    for row in packet.get("ratios_annual") or []:
        if not isinstance(row, dict):
            continue
        try:
            fiscal_end = date.fromisoformat(str(row.get("fiscal_year_end") or ""))
        except ValueError:
            continue
        roe = _number(row.get("roe"))
        if fiscal_end <= as_of and roe is not None:
            ratios.append((fiscal_end, roe))
    if not ratios:
        return None
    ratios.sort(key=lambda item: item[0], reverse=True)

    estimates: list[tuple[date, float]] = []
    for row in packet.get("analyst_estimates_annual") or []:
        if not isinstance(row, dict):
            continue
        try:
            fiscal_end = date.fromisoformat(str(row.get("fiscal_year_end") or ""))
        except ValueError:
            continue
        revenue = _number(row.get("revenue_avg"))
        if fiscal_end >= as_of and revenue is not None and revenue > 0:
            estimates.append((fiscal_end, revenue))
    estimates.sort(key=lambda item: item[0])
    if len(estimates) < 2:
        return None

    growth = estimates[1][1] / estimates[0][1] - 1
    return {
        "roe": ratios[0][1],
        "revenue_growth": growth,
        "roe_fiscal_year_end": ratios[0][0].isoformat(),
        "fy1_end": estimates[0][0].isoformat(),
        "fy2_end": estimates[1][0].isoformat(),
        "source": "fmp_forward",
    }


def chewie_trailing_quality(item: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return ROE and revenue growth from one persisted Chewie item only."""
    item = item or {}
    profitability = item.get("profitability")
    profitability = profitability if isinstance(profitability, dict) else {}
    growth = item.get("growth")
    growth = growth if isinstance(growth, dict) else {}
    roe_percent = _number(profitability.get("roe_percent"))
    revenue_growth_percent = _number(growth.get("revenue_growth_percent"))
    if roe_percent is None or revenue_growth_percent is None:
        return None
    return {
        "roe": roe_percent / 100,
        "revenue_growth": revenue_growth_percent / 100,
        "source": "chewie_trailing",
        "fundamentals_as_of": item.get("fundamentals_as_of"),
    }


def build_quality_index(
    packets: dict[str, dict[str, Any]],
    chewie_items: list[dict[str, Any]],
    *,
    as_of: date,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Build the deterministic quality ladder consumed by Valuation V3.

    The two bases remain separate all the way to the engine. A missing field in
    one source never borrows from the other source.
    """
    packet_by_symbol: dict[str, dict[str, Any]] = {}
    for raw_symbol in sorted(packets):
        symbol = canonical_symbol(str(raw_symbol))
        if symbol:
            packet_by_symbol.setdefault(symbol, packets[raw_symbol])
    chewie_by_symbol: dict[str, dict[str, Any]] = {}
    for item in sorted(
        (item for item in chewie_items if isinstance(item, dict) and item.get("symbol")),
        key=lambda item: str(item.get("symbol")),
    ):
        chewie_by_symbol.setdefault(canonical_symbol(str(item["symbol"])), item)
    symbols = set(packet_by_symbol) | set(chewie_by_symbol)
    output: dict[str, dict[str, dict[str, Any]]] = {}
    for symbol in sorted(symbols):
        packet = packet_by_symbol.get(symbol)
        bases: dict[str, dict[str, Any]] = {}
        if (forward := fmp_forward_quality(packet, as_of=as_of)) is not None:
            bases["fmp_forward"] = forward
        if (trailing := chewie_trailing_quality(chewie_by_symbol.get(symbol))) is not None:
            bases["chewie_trailing"] = trailing
        output[symbol] = bases
    return output


def attach_quality_to_multiples(
    multiples_index: dict[str, dict[str, Any]],
    quality_index: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """Copy a multiples index and attach quality without mutating V2 inputs."""
    output: dict[str, dict[str, Any]] = {}
    for raw_symbol in sorted(multiples_index):
        symbol = canonical_symbol(raw_symbol)
        output.setdefault(
            symbol,
            {
                **multiples_index[raw_symbol],
                "quality": quality_index.get(symbol, {}),
            },
        )
    return output
