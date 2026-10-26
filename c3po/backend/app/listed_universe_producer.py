"""Live adapter for unchanged canonical methods, used only by the opt-in runner.

Provider reads pass through a durable, operator-rated quota transport with no
hidden transport retries. No call publishes a generation or updates a study.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx

from .listed_universe import Listing, digest, positive, utc
from .listed_universe_runtime import CollectionPaused, QuotaWindow, TransientInputFailure, UnavailableInput, ready


class BudgetedHttp:
    def __init__(self, quota: QuotaWindow, *, timeout: float = 30, client: Any = None, deadline_guard=None) -> None:
        self.quota, self.timeout, self.client, self.deadline_guard = quota, timeout, client, deadline_guard

    def _read(self, url: str, *, params=None, headers=None, text=False):
        if self.deadline_guard is not None:
            self.deadline_guard()
        parsed = urlparse(url)
        rules = [rule for rule in self.quota.rate_card.values()
                 if parsed.hostname == rule.get("host") and parsed.path.startswith(str(rule.get("path_prefix") or "/"))]
        if not rules:
            self.quota.stop("provider_rate_card_missing")
            raise CollectionPaused("provider_rate_card_missing")
        rule = max(rules, key=lambda item: len(str(item.get("path_prefix") or "/")))
        self.quota.reserve(str(rule.get("provider")), rule.get("units"))
        try:
            # A transport read is one reservation; no automatic retry/redirect
            # can spend units outside the persistent budget.
            response = (self.client.get(url, params=params, headers=headers, timeout=self.timeout)
                        if self.client else httpx.get(url, params=params, headers=headers,
                                                     timeout=self.timeout, follow_redirects=False))
            if response.status_code in {403, 429}:
                self.quota.stop("provider_throttled_or_refused")
                raise CollectionPaused("provider_throttled_or_refused")
            response.raise_for_status()
            return response.text if text else response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TransientInputFailure(type(exc).__name__) from exc

    def get_json(self, url, *, params=None, headers=None):
        return self._read(url, params=params, headers=headers)

    def get_text(self, url, *, params=None, headers=None):
        return self._read(url, params=params, headers=headers, text=True)


class LiveCanonicalAdapter:
    """Collect in small resumable units; value against one full-market context."""
    def __init__(self, settings, database, *, market: str, deadline: datetime,
                 provider_symbols: Mapping[str, str] | None = None) -> None:
        self.settings, self.database, self.market = settings, database, market
        if market not in {"NASDAQ", "NYSE", "B3"}:
            raise ValueError("unsupported canonical market")
        self.deadline = utc(deadline)
        self.provider_symbols = dict(provider_symbols or {})
        if len(set(self.provider_symbols.values())) != len(self.provider_symbols):
            raise ValueError("two official identities map to the same provider identity")
        from .official_statements import fieldwise_overlay_enabled
        self.fieldwise_overlay = fieldwise_overlay_enabled()
        self.identity = {"adapter": "unchanged_canonical_methods_v1", "market": market,
                         "deadline": self.deadline.isoformat(), "provider_symbols": self.provider_symbols,
                         "settings_sha256": digest(settings.model_dump(mode="json")),
                         "cvm_fieldwise_overlay": self.fieldwise_overlay}
        # Only this digest is retained; credentials/settings values are never
        # written to the checkpoint or printed in a receipt.
        self.http = self.us = self.b3 = self.one = self.realtime = None
        self._quote_map = None

    def _check_deadline(self):
        if datetime.now(timezone.utc) >= self.deadline:
            raise CollectionPaused("valuation_collection_deadline_reached")

    def _services(self, quota):
        self._check_deadline()
        from .official_statements import fieldwise_overlay_enabled
        if fieldwise_overlay_enabled() != self.fieldwise_overlay:
            raise CollectionPaused("cvm_overlay_policy_changed")
        if self.http is not None:
            if self.http.quota is not quota:
                self.http.quota = quota
            return
        from .market_data.b3_screener import B3ScreenerService
        from .market_data.us_screener import USScreeningService
        from .market_data.realtime import RealtimeMarketsService
        from .market_data.service import MarketDataService
        from .one_pager import OnePagerService

        self.http = BudgetedHttp(quota, deadline_guard=self._check_deadline)
        market_data = MarketDataService(self.settings, self.database)
        market_data.http = self.http
        self.b3 = B3ScreenerService(self.settings, self.database, self.http)
        self.one = OnePagerService(self.settings, self.database, market_data, b3_screener=self.b3)
        self.realtime = RealtimeMarketsService(self.settings, self.database, self.http)
        self.us = USScreeningService(self.settings, self.database, self.realtime, self.one)

    def _provider_symbol(self, listing: Listing) -> str:
        if listing.market != self.market:
            raise ValueError("listing market does not match the canonical adapter")
        supplied = self.provider_symbols.get(listing.symbol)
        if supplied:
            suffix = "SA" if listing.market == "B3" else "US"
            if not re.fullmatch(r"[A-Z0-9.^_-]+\." + suffix, supplied):
                raise UnavailableInput("provider_identity_mapping_invalid")
            return supplied
        # Existing EodhdClient batch helpers truncate symbols at '.', so an
        # official class such as BRK.B needs an explicit verified mapping.
        if not re.fullmatch(r"[A-Z0-9]+", listing.symbol):
            raise UnavailableInput("provider_identity_unmapped")
        return listing.symbol + (".SA" if listing.market == "B3" else ".US")

    def validate_catalogue(self, listings):
        """Reject alias collisions against implicit identities before any read."""
        resolved = {}
        for listing in listings:
            try:
                provider_symbol = self._provider_symbol(listing)
            except UnavailableInput:
                continue  # retained with an explicit reason during collection
            if provider_symbol in resolved and resolved[provider_symbol] != listing.symbol:
                raise ValueError("two official identities map to the same provider identity")
            resolved[provider_symbol] = listing.symbol

    def collect(self, listing: Listing, quota: QuotaWindow) -> Mapping[str, Any]:
        self._services(quota)
        if listing.market != self.market:
            raise ValueError("listing market does not match the canonical adapter")
        provider_symbol = self._provider_symbol(listing)
        now = datetime.now(timezone.utc)
        if listing.market == "B3":
            quote = self.b3._quotes([listing.symbol]).get(listing.symbol)
            if quote is None:
                quota.check()
                raise UnavailableInput("price_missing")
            stats = self.b3._fundamental_map("statistics", [listing.symbol]).get(listing.symbol, {})
            finance = self.b3._fundamental_map("financial-data", [listing.symbol]).get(listing.symbol, {})
            brapi_at = datetime.now(timezone.utc)
            history = self.b3._historical_map([listing.symbol]).get(listing.symbol, {})
            if history.get("history_days", 0) < 40:
                # Preserve the canonical adjusted-close fallback while avoiding
                # its ingestion bookkeeping writes in the expanded stage.
                from .market_data.eodhd import EodhdClient
                fallback = self.b3._history_statistics(EodhdClient(
                    self.settings.eodhd_base_url, self.settings.eodhd_api_token, self.http,
                ).history(provider_symbol, exchange="SA", days=120))
                if fallback and fallback.get("history_days", 0) > history.get("history_days", 0):
                    history = fallback
        else:
            self.us._require_completed_session_volume(now)
            if self._quote_map is None:
                self._quote_map = {self.realtime._us_symbol(row.get("code") or row.get("Code")): row
                                   for row in self.realtime._us_bulk_quotes(now)}
            raw_quote = self._quote_map.get(listing.symbol) or self._quote_map.get(provider_symbol.removesuffix(".US"))
            if raw_quote is None:
                raise UnavailableInput("price_missing")
            quote = self.realtime._us_row(raw_quote, {"Code": listing.symbol, "Name": listing.name,
                                                    "Exchange": listing.market, "Type": "Common Stock"}, listing.market, now)
            if quote is None:
                raise UnavailableInput("price_missing")
            quote = quote.model_copy(update={"symbol": listing.symbol})
            stats, finance, brapi_at = {}, {}, None
            from .market_data.eodhd import EodhdClient
            history = EodhdClient(self.settings.eodhd_base_url, self.settings.eodhd_api_token, self.http).history(
                provider_symbol, exchange="US", days=400,
            )  # same adjusted-close normalization as the canonical producer
        if not positive(quote.price):
            raise UnavailableInput("price_missing")
        if (len(history) if isinstance(history, list) else history.get("history_days", 0)) < 40:
            raise UnavailableInput("insufficient_history")
        from .market_data.eodhd import EodhdClient
        fundamental_payload = self.http.get_json(
            f"{self.settings.eodhd_base_url.rstrip('/')}/api/v1.1/fundamentals/{provider_symbol}",
            params={"api_token": self.settings.eodhd_api_token, "fmt": "json"})
        fundamental = EodhdClient._normalize_fundamentals(fundamental_payload)
        if listing.market == "B3":
            from .market_data import b3_screener as canonical_b3
            overlay = (canonical_b3.apply_official_statements_map if self.fieldwise_overlay
                       else canonical_b3.apply_official_fundamentals_map)
            fundamental = overlay(self.database, {listing.symbol: fundamental}, market="B3").get(listing.symbol, {})
        fetched_at = datetime.now(timezone.utc)
        if not fundamental:
            raise UnavailableInput("statements_missing")
        if fundamental.get("isETF"):
            raise UnavailableInput("provider_security_type_conflict")
        fmp = self.one._fmp_consensus_batch([listing.symbol]).get(listing.symbol, (None, None)) if listing.market != "B3" else (None, None)
        fmp_at = datetime.now(timezone.utc)
        institutional = self.one._fmp_institutional_batch([listing.symbol]).get(listing.symbol) if listing.market != "B3" else None
        grades = self.one._fmp_recent_grades_batch([listing.symbol]).get(listing.symbol) if listing.market != "B3" else None
        quota.check()
        return ready({"listing": {"symbol": listing.symbol, "name": listing.name}, "quote": quote.model_dump(),
                      "fundamental": fundamental, "history": history, "statistics": stats, "financial": finance,
                      "consensus": fmp, "institutional": institutional, "grades": grades,
                      "received_at": fetched_at, "brapi_received_at": brapi_at, "fmp_received_at": fmp_at,
                      "provider_symbol": provider_symbol})

    def prepare_context(self, inputs, quota):
        self._services(quota)
        if not inputs:
            return {"market": self.market, "empty": True}
        symbols = sorted(inputs)
        if self.market == "B3":
            macro = self.b3._macro_context()
            self.b3._load_calibration_factors()
            cut = datetime.now(timezone.utc)
            ir_events = self.database.latest_valuation_ir_events(symbols, market="B3")
            from .market_data.b3_screener import INSIDER_GOVERNANCE_LOOKBACK_DAYS
            insider = self.database.insider_transaction_activity(
                symbols, "B3", cut - timedelta(days=INSIDER_GOVERNANCE_LOOKBACK_DAYS))
            quota.check()
            return ready({"market": self.market, "macro": macro,
                          "calibration": self.b3._calibration_factors,
                          "row_inputs": {"cut": cut, "ir_events": ir_events, "insider_activity": insider}})
        self.us._load_calibration_factors(self.market)
        rate = self.one._us_risk_free_rate()
        peer_medians = self.one._us_peer_medians({symbol: item["fundamental"] for symbol, item in inputs.items()})
        ir_events = self.database.latest_valuation_ir_events(symbols, market=self.market)
        sentiment = self.database.latest_news_sentiment(symbols, market="US")
        insider = self.database.insider_transaction_activity(symbols, self.market,
                                                             datetime.now(timezone.utc) - timedelta(days=180))
        quota.check()
        return ready({"market": self.market, "risk_free_rate": rate, "peer_medians": peer_medians,
                      "ir_events": ir_events, "sentiment": sentiment, "insider_activity": insider,
                      "calibration": self.us._calibration_factors[self.market]})

    def value(self, inputs, context, quota):
        # A resumed process can load a complete context without collecting any
        # new inputs. It still needs fresh service objects bound to the ledger.
        self._services(quota)
        if not inputs:
            return {}
        from .schemas import NormalizedQuote
        if self.market == "B3":
            self.b3._calibration_factors = dict(context["calibration"])
            quotes = {symbol: NormalizedQuote(**item["quote"]) for symbol, item in inputs.items()}
            finances = {symbol: item["financial"] for symbol, item in inputs.items()}
            fundamentals = {symbol: item["fundamental"] for symbol, item in inputs.items()}
            receipts = {"brapi": max(utc(item["brapi_received_at"]) for item in inputs.values()),
                        "eodhd": {symbol: utc(item["received_at"]) for symbol, item in inputs.items()}}
            rows = self.b3._prepare_rows(
                [item["listing"] for item in inputs.values()],
                quotes,
                {symbol: item["statistics"] for symbol, item in inputs.items()},
                finances,
                {symbol: item["history"] for symbol, item in inputs.items()}, context["macro"],
                fundamentals, self.b3._consensus_reference_rows(quotes, finances, fundamentals, receipts),
                enforce_screening_gates=False, enforce_quality_gate=True,
                consensus_fetched_at=receipts,
                row_inputs={**context["row_inputs"], "cut": utc(context["row_inputs"]["cut"])},
            )
            self._check_deadline()
            return {row["symbol"]: ready(row) for row in rows}
        self.us._calibration_factors[self.market] = dict(context["calibration"])
        rows = []
        for symbol, item in inputs.items():
            self._check_deadline()
            try:
                row = self.us._analyze_stock(
                    self.market, item["quote"], item["fundamental"], item["history"],
                    positive(item["quote"].get("cash_volume")) or positive(item["quote"].get("volume")) or 0.0,
                    risk_free_rate=context["risk_free_rate"], peer_medians=context["peer_medians"],
                    insider_activity=context["insider_activity"].get(symbol),
                    news_sentiment=context["sentiment"].get(symbol),
                    fmp_consensus=item["consensus"][0], fmp_summary=item["consensus"][1],
                    institutional_positions=item["institutional"], recent_grades=item["grades"],
                    consensus_fetched_at={"eodhd": utc(item["received_at"]), "fmp": utc(item["fmp_received_at"])},
                )
                row.update(self.us._ir_freshness(item["fundamental"].get("financialsAsOf") or item["fundamental"].get("updated_at"),
                                                  context["ir_events"].get(symbol)))
                rows.append(row)
            except (ValueError, KeyError, TypeError):
                continue  # runner retains the name as canonical_inputs_or_quality_insufficient
        self.us._assign_statuses(rows, context["risk_free_rate"])
        self._check_deadline()
        return {row["symbol"]: ready(row) for row in rows}
