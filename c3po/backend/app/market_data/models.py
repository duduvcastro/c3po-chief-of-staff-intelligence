from datetime import datetime, timezone
from typing import Any

from ..schemas import NormalizedQuote


US_COMMON_STOCK_OVERRIDES = {
    "SPCX": "Space Exploration Technologies Corp. Class A Common Stock",
}


def canonical_us_security_type(symbol: Any, provider_type: Any = "", *, has_etf_data: bool = False) -> str:
    normalized = str(symbol or "").strip().upper().split(".", 1)[0]
    if normalized in US_COMMON_STOCK_OVERRIDES:
        return "Stock"
    raw_type = str(provider_type or "").upper()
    if has_etf_data or "ETF" in raw_type or "EXCHANGE TRADED" in raw_type:
        return "ETF"
    return "Stock"


def canonical_us_security_name(symbol: Any, provider_name: Any = "") -> str:
    normalized = str(symbol or "").strip().upper().split(".", 1)[0]
    return US_COMMON_STOCK_OVERRIDES.get(normalized, str(provider_name or normalized))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def require_price(value: Any, symbol: str) -> float:
    parsed = number(value)
    if parsed is None:
        raise ValueError(f"{symbol}: provider response has no valid price")
    return parsed


def from_unix(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, str) and value.strip():
        try:
            parsed_date = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return parsed_date if parsed_date.tzinfo else parsed_date.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    parsed = number(value)
    if parsed is None:
        return fallback
    if parsed > 10_000_000_000:
        parsed /= 1000
    return datetime.fromtimestamp(parsed, tz=timezone.utc)


def quality_for(quote: NormalizedQuote) -> int:
    optional_values = (
        quote.change_percent,
        quote.open,
        quote.low,
        quote.high,
        quote.previous_close,
        quote.volume,
    )
    completeness = sum(value is not None for value in optional_values)
    return min(98, 76 + completeness * 3)
