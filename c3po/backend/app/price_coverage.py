"""Price collection identity, separate from liquidity/fundamental/ranking eligibility.

B3: Brapi's paginated stock/unit/ETF/BDR taxonomy plus positively identified EODHD
listings. US: stocks and ETFs on Nasdaq and the NYSE family (including Arca and
American). No OTC/Cboe expansion or ticker-suffix guesses about instrument type.
Catalog failures refuse the run; they never fall back to the smaller screener.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .market_data.http import JsonHttpClient

POLICY = "STOCKS_ETFS_BDRS_B3_NASDAQ_NYSE_V2"
SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.-]{0,31}\Z")
NASDAQ = {"NASDAQ", "XNAS", "NASDAQ GLOBAL SELECT", "NASDAQ GLOBAL MARKET", "NASDAQ CAPITAL MARKET"}
NYSE = {"NYSE", "XNYS", "NYSE ARCA", "ARCA", "NYSE AMERICAN", "NYSE MKT", "AMEX", "AMERICAN"}
US_TYPES = {"Common Stock": "stock", "Preferred Stock": "preferred_stock", "ETF": "etf"}
ELIGIBLE = {"stock", "preferred_stock", "unit", "etf", "bdr"}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def select_catalog(market: str, eodhd: list[dict[str, Any]], brapi: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Pure, deterministic identity decision. Conflicting duplicate identities refuse,
    and every other exclusion has a reason. Metadata (not names/quotes) is retained.
    B3 fractional aliases aren't additional securities and aren't collected twice.
    """
    if market not in {"B3", "NASDAQ", "NYSE"}:
        raise ValueError("unsupported price coverage market")
    selected: dict[str, dict[str, Any]] = {}
    excluded: dict[str, str] = {}
    eod: dict[str, dict[str, Any]] = {}
    for row in eodhd:
        symbol = str(row.get("Code") or "").strip().upper()
        identity = {k: row.get(k) for k in ("Type", "Exchange", "Currency", "Isin")}
        if symbol in eod and eod[symbol] != identity:
            raise ValueError("conflicting EODHD catalog identities")
        eod[symbol] = identity
    b3: dict[str, dict[str, Any]] = {}
    for row in brapi or []:
        symbol = str(row.get("symbol") or "").strip().upper()
        identity = {k: row.get(k) for k in ("assetType", "subType", "exchange", "currency", "isActive")}
        if symbol in b3 and b3[symbol] != identity:
            raise ValueError("conflicting Brapi catalog identities")
        b3[symbol] = identity
    for symbol in sorted(set(eod) | (set(b3) if market == "B3" else set())):
        row, classification = eod.get(symbol, {}), b3.get(symbol)
        venue = str(row.get("Exchange") or "").upper()
        if market != "B3" and venue not in (NASDAQ if market == "NASDAQ" else NYSE):
            excluded[symbol] = "outside_market" if row.get("Type") in US_TYPES and row.get("Currency") == "USD" else "outside_market_ineligible"
            continue
        if not SYMBOL.fullmatch(symbol):
            excluded[symbol] = "invalid_symbol"
            continue
        kind, source = None, "eodhd"
        if market == "B3":
            if classification is not None:
                subtype, asset = classification.get("subType"), classification.get("assetType")
                if classification.get("isActive") is not True:
                    excluded[symbol] = "inactive"
                    continue
                if classification.get("currency") != "BRL" or str(classification.get("exchange")).upper() != "B3":
                    excluded[symbol] = "identity_currency_or_venue"
                    continue
                if asset == "stock" and subtype in {"stock", "unit"}:
                    kind = subtype
                elif asset == "fund" and subtype == "etf":
                    kind = "etf"
                elif asset == "bdr" and subtype == "bdr":
                    kind = "bdr"
                if kind is None:
                    excluded[symbol] = "excluded_instrument_type"
                    continue
                # A fractional lot symbol represents the same security, not a new stock.
                if re.fullmatch(r"[A-Z]{4}[0-9]{1,2}F", symbol):
                    excluded[symbol] = "fractional_alias"
                    continue
                isin = str(row.get("Isin") or "")
                if kind != "bdr" and len(isin) == 12 and isin.startswith("BR") and isin[6:9] == "BDR":
                    raise ValueError("Brapi stock/ETF conflicts with BDR ISIN")
                source = "brapi"
            else:
                isin = str(row.get("Isin") or "")
                asset_class = isin[6:9] if len(isin) == 12 and isin.startswith("BR") else ""
                if asset_class == "ACN" and row.get("Type") in {"Common Stock", "Preferred Stock"}:
                    kind = US_TYPES[str(row["Type"])]
                elif asset_class in {"CDA", "UNT"} and row.get("Type") == "Common Stock":
                    kind = "unit"
                elif asset_class == "BDR":
                    kind = "bdr"
                # An ETF type alone cannot identify a domestic ETF versus its BDR.
                # Require positive Brapi taxonomy or a BDR ISIN rather than guess.
                if kind is None:
                    excluded[symbol] = "unclassified_or_outside_scope"
                    continue
            if row and row.get("Currency") != "BRL":
                excluded[symbol] = "provider_currency_conflict"
                continue
        else:
            kind = US_TYPES.get(str(row.get("Type")))
            if kind is None:
                excluded[symbol] = "excluded_instrument_type"
                continue
            if row.get("Currency") != "USD":
                excluded[symbol] = "non_usd_currency"
                continue
        selected[symbol] = {"kind": kind, "venue": "B3" if market == "B3" else venue, "classifier": source,
                            "provider_listed": symbol in eod}
    if not selected:
        raise ValueError("empty stocks/ETFs/BDRs catalog refused")
    return {"policy": POLICY, "market": market, "selected": selected, "excluded": excluded,
            "counts": dict(sorted(Counter(excluded.values()).items())),
            "catalog_sha256": digest({"eodhd": eod, "brapi": b3 if market == "B3" else {}})}


class PriceCoverageCatalog:
    def __init__(self, settings: Settings, http: JsonHttpClient) -> None:
        self.settings, self.http = settings, http
        self._cache: dict[str, tuple[str, dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._rate_lock = threading.Lock()
        self._next_request = 0.0

    def _eodhd(self, path: str) -> Any:
        if not self.settings.eodhd_api_token:
            raise ValueError("price catalog credential missing")
        try:
            return self.http.get_json(f"{self.settings.eodhd_base_url.rstrip('/')}/api/{path}",
                                      params={"api_token": self.settings.eodhd_api_token, "fmt": "json"})
        except Exception:
            # HTTP exception strings can include the authenticated URL.
            raise ValueError("price catalog provider request failed") from None

    def _brapi(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        total = None
        for page in range(1, 101):
            try:
                payload = self.http.get_json(f"{self.settings.brapi_base_url.rstrip('/')}/api/v2/tickers",
                                             params={"page": page, "limit": 2000, "sortBy": "symbol", "sortOrder": "asc"})
            except Exception:
                raise ValueError("Brapi classification request failed") from None
            meta = payload.get("pagination", {}) if isinstance(payload, dict) else {}
            batch = payload.get("results") if isinstance(payload, dict) else None
            if (not isinstance(batch, list) or not batch or not all(isinstance(r, dict) for r in batch)
                    or meta.get("page") != page or type(meta.get("totalItems")) is not int or type(meta.get("hasNextPage")) is not bool):
                raise ValueError("Brapi catalog pagination invalid")
            if total is None:
                total = meta["totalItems"]
            if total != meta["totalItems"]:
                raise ValueError("Brapi catalog changed during pagination")
            rows.extend(batch)
            if not meta["hasNextPage"]:
                if len(rows) != total or len({r.get("symbol") for r in rows}) != total:
                    raise ValueError("Brapi catalog incomplete or duplicated")
                return rows
        raise ValueError("Brapi catalog exceeded pagination bound")

    def plan(self, market: str, *, previous: dict[str, Any], legacy: list[str]) -> dict[str, Any]:
        today = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            cached = self._cache.get(market)
            if cached is None or cached[0] != today:
                exchange = "SA" if market == "B3" else "US"
                raw = self._eodhd(f"exchange-symbol-list/{exchange}")
                if not isinstance(raw, list) or not raw or not all(isinstance(r, dict) for r in raw):
                    raise ValueError("EODHD catalog invalid")
                plan = select_catalog(market, raw, self._brapi() if market == "B3" else None)
                plan["catalog_fetched_at"] = datetime.now(timezone.utc).isoformat()
                self._cache[market] = (today, plan)
            result = copy.deepcopy(self._cache[market][1])
        retained = []
        # Previously classified names keep their label series when delisted or
        # transferred to another venue. A known incompatible type/currency wins.
        for symbol, identity in previous.items():
            if (symbol not in result["selected"] and result["excluded"].get(symbol) in {None, "outside_market"}
                    and isinstance(identity, dict) and identity.get("kind") in ELIGIBLE):
                result["selected"][symbol] = identity
                retained.append(symbol)
                result["excluded"].pop(symbol, None)
        result["counts"] = dict(sorted(Counter(result["excluded"].values()).items()))
        result["retained_from_previous"] = sorted(retained)
        result["legacy_not_selected"] = {s: result["excluded"].get(s, "absent_unclassified") for s in legacy if s not in result["selected"]}
        result["selected"] = dict(sorted(result["selected"].items()))
        result["selection_sha256"] = digest(result["selected"])
        if len(result["selected"]) > 20000:
            raise ValueError("price catalog exceeds per-market capacity bound")
        return result

    def allowance(self, symbols: int) -> dict[str, int]:
        account = self._eodhd("user")
        if not isinstance(account, dict) or account.get("apiRequestsDate") != datetime.now(timezone.utc).date().isoformat():
            raise ValueError("provider allowance date unavailable")
        limit, used = account.get("dailyRateLimit"), account.get("apiRequests")
        if type(limit) is not int or type(used) is not int or min(limit, used) < 0:
            raise ValueError("provider ordinary allowance unavailable")
        maximum_calls = symbols * (max(0, self.http.max_retries) + 1)
        if limit - used < maximum_calls + 10000:
            raise ValueError("insufficient ordinary provider allowance; extra credits not used")
        return {"daily_limit": limit, "used_before": used, "maximum_bar_calls": maximum_calls, "reserve": 10000}

    def throttle(self) -> None:
        # <= 240 initial calls/minute; at the configured two retries, <= 720
        # attempts/minute for this producer, leaving room for other processes.
        with self._rate_lock:
            delay = max(0.0, self._next_request - time.monotonic())
            if delay:
                time.sleep(delay)
            self._next_request = time.monotonic() + max(0.25, (self.http.max_retries + 1) / 12)
