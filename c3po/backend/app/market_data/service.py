from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Literal

from ..config import Settings
from ..database import Database
from ..schemas import MarketDataProviderHealth, NormalizedQuote
from .brapi import BrapiClient
from .eodhd import EodhdClient
from .http import JsonHttpClient

ProviderCode = Literal["brapi", "eodhd"]


@dataclass(frozen=True)
class ProviderDefinition:
    code: ProviderCode
    name: str
    market: str
    configured: bool
    plan: str


class MarketDataService:
    def __init__(self, settings: Settings, database: Database, *, http: JsonHttpClient | None = None) -> None:
        self.settings = settings
        self.database = database
        self.http = http or JsonHttpClient(
            timeout=settings.market_data_timeout_seconds,
            max_retries=settings.market_data_max_retries,
        )
        self._health_probe_lock = Lock()
        self._health_probe_at: dict[ProviderCode, datetime] = {}

    def provider_definitions(self) -> list[ProviderDefinition]:
        return [
            ProviderDefinition("brapi", "Brapi", "Brazil / B3", bool(self.settings.brapi_token), self.settings.brapi_plan),
            ProviderDefinition("eodhd", "EODHD", "United States / Global", bool(self.settings.eodhd_api_token), self.settings.eodhd_plan),
        ]

    def health(self) -> list[MarketDataProviderHealth]:
        recent = self.database.market_data_provider_health()
        items: list[MarketDataProviderHealth] = []
        for provider in self.provider_definitions():
            state = recent.get(provider.code, {})
            if not provider.configured:
                status = "unconfigured"
            elif state.get("last_status") != "succeeded":
                status = "attention"
            else:
                status = "healthy"
            items.append(MarketDataProviderHealth(
                code=provider.code,
                name=provider.name,
                market=provider.market,
                configured=provider.configured,
                plan=provider.plan,
                status=status,
                last_success_at=state.get("last_success_at"),
                last_error=state.get("last_error"),
            ))
        return items

    def probe_health(self) -> list[MarketDataProviderHealth]:
        """Run a bounded quote heartbeat before returning provider health."""
        now = datetime.now(timezone.utc)
        probe_symbols: dict[ProviderCode, str] = {"brapi": "VALE3", "eodhd": "AAPL"}
        with self._health_probe_lock:
            for provider in self.provider_definitions():
                last_probe = self._health_probe_at.get(provider.code)
                if (
                    not provider.configured
                    or (last_probe is not None and now - last_probe < timedelta(minutes=15))
                ):
                    continue
                self._health_probe_at[provider.code] = now
                try:
                    self.fetch_quotes(provider.code, [probe_symbols[provider.code]], persist=True)
                except Exception:
                    # fetch_quotes persists the failed run and its diagnostic.
                    pass
        return self.health()

    def fetch_quotes(self, provider: ProviderCode, symbols: list[str], *, persist: bool = True) -> list[NormalizedQuote]:
        clean_symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
        if not clean_symbols:
            return []
        if len(clean_symbols) > 20:
            raise ValueError("A quote request accepts at most 20 symbols")

        definition = next(item for item in self.provider_definitions() if item.code == provider)
        if not definition.configured:
            raise RuntimeError(f"{definition.name} credential is not configured")

        run_id = self.database.begin_ingestion_run(provider, definition.name, "market_data", {"symbols": clean_symbols})
        try:
            client = self._client(provider)
            quotes = client.quotes(clean_symbols)
            if persist:
                self.database.save_quotes(provider, run_id, quotes)
            self.database.finish_ingestion_run(run_id, "succeeded", len(clean_symbols), len(quotes))
            return quotes
        except Exception as exc:
            self.database.finish_ingestion_run(run_id, "failed", len(clean_symbols), 0, str(exc))
            raise

    def _client(self, provider: ProviderCode):
        if provider == "brapi":
            return BrapiClient(self.settings.brapi_base_url, self.settings.brapi_token, self.http)
        return EodhdClient(self.settings.eodhd_base_url, self.settings.eodhd_api_token, self.http)
