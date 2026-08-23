from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Literal

from .config import Settings
from .database import Database
from .market_data.fmp import FmpClient
from .market_data.http import JsonHttpClient


V2Market = Literal["B3", "NASDAQ", "NYSE"]

ANALYSIS_TYPE = "valuation_v2_data"
METHODOLOGY_KEY = "valuation_v2_data_foundation"
METHODOLOGY_VERSION = 1

# Frozen anchor thresholds from the V2 design (Fable, 2026-08-23): a peer
# group anchors a fair multiple only with at least four peers; the own-history
# band needs at least five fiscal years; the forward term structure needs at
# least one future fiscal year with a consensus EPS.
MIN_PEER_SAMPLE = 4
MIN_HISTORY_YEARS = 5

_PACKET_DATA_KEYS = (
    "peers",
    "analyst_estimates_annual",
    "ratios_annual",
    "key_metrics_annual",
)
_PROVIDER_ENDPOINTS = ("peers", "analyst_estimates", "ratios", "key_metrics")
_PROVIDER_FAILURE_STATUSES = {"error", "invalid_payload"}

logger = logging.getLogger("c3po.valuation_v2_data")

_UNIVERSE_SNAPSHOT_KEY: dict[V2Market, str] = {
    "B3": "B3_UNIVERSE",
    "NASDAQ": "NASDAQ_UNIVERSE",
    "NYSE": "NYSE_UNIVERSE",
}


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


class ValuationV2DataService:
    """V2.1 data foundations: real FMP peers, forward estimates per fiscal
    year, and ten years of own-history ratios for every stock in the tracked
    B3/NASDAQ/NYSE universes, persisted once per day as immutable snapshots.

    Strictly additive and read-only for the rest of the system: nothing that
    already runs (screeners, One Pager, R2D2) reads these snapshots until the
    V2.2 engine lands, and this module never mutates any existing snapshot.
    Coverage accounting per symbol feeds the frozen fallback ladder: peers ->
    B3 sector medians -> own history -> low_conviction, never constants.
    """

    def __init__(self, settings: Settings, database: Database, http: JsonHttpClient) -> None:
        self.settings = settings
        self.database = database
        self.fmp = FmpClient(settings.fmp_base_url, settings.fmp_api_token, http)

    # ------------------------------------------------------------------ daily

    def refresh_daily(self, market: V2Market) -> dict[str, int]:
        if not self.settings.fmp_api_token:
            return {
                "universe": 0,
                "attempted": 0,
                "covered": 0,
                "all_anchors": 0,
                "provider_error_symbols": 0,
            }
        universe = self._universe_stocks(market)
        symbols = [str(row["symbol"]) for row in universe]
        provider_by_symbol = {
            symbol: (f"{symbol}.SA" if market == "B3" else symbol) for symbol in symbols
        }
        packets_by_provider = self.fmp.valuation_v2_batch(
            list(provider_by_symbol.values()), workers=10
        )
        today = datetime.now(timezone.utc).date()
        packets: dict[str, dict[str, Any]] = {}
        for symbol in symbols:
            provider_symbol = provider_by_symbol[symbol]
            packet = packets_by_provider.get(provider_symbol) or self._missing_packet(provider_symbol)
            enriched = {
                **packet,
                "symbol": symbol,
                "provider_symbol": provider_symbol,
            }
            forward = self._forward_estimates(enriched, today=today)
            enriched["forward_estimates"] = forward
            enriched["fy1_estimate"] = forward[0] if forward else None
            enriched["fy2_estimate"] = forward[1] if len(forward) > 1 else None
            enriched["coverage"] = self._coverage(enriched, today=today)
            packets[symbol] = enriched
        summary = self._summary(packets, universe_size=len(universe))
        if packets and summary["endpoint_responses"] == 0:
            logger.error(
                "Valuation V2.1 provider outage market=%s attempted=%s endpoint_errors=%s; "
                "previous snapshot preserved",
                market,
                summary["attempted"],
                summary["endpoint_errors"],
            )
            raise RuntimeError(f"FMP Valuation V2.1 provider outage for {market}")
        if summary["provider_error_symbols"]:
            logger.warning(
                "Valuation V2.1 partial provider failure market=%s symbols=%s endpoint_errors=%s",
                market,
                summary["provider_error_symbols"],
                summary["endpoint_errors"],
            )
        methodology_id = self.database.ensure_methodology_version(
            METHODOLOGY_KEY,
            METHODOLOGY_VERSION,
            {
                "anchors": "fmp_peers,fy_estimates,own_history_10y",
                "min_peer_sample": MIN_PEER_SAMPLE,
                "min_history_years": MIN_HISTORY_YEARS,
                "consumers": "none_until_v2_2_engine",
            },
            "Valuation V2.1 data foundations: external anchors only, no free constants.",
        )
        self.database.save_analysis_snapshot(
            ANALYSIS_TYPE,
            f"{market}_V2_DATA",
            methodology_id,
            {"market": market, "universe_size": len(universe), **summary},
            {"packets": packets, "universe_size": len(universe), "coverage_summary": summary},
            datetime.now(timezone.utc),
        )
        return {
            "universe": len(universe),
            "attempted": summary["attempted"],
            "covered": summary["covered"],
            "all_anchors": summary["all_anchors"],
            "provider_error_symbols": summary["provider_error_symbols"],
        }

    def refresh_all(self) -> dict[str, dict[str, int]]:
        return {market: self.refresh_daily(market) for market in ("B3", "NASDAQ", "NYSE")}

    def last_refreshed_at(self) -> datetime | None:
        stamps: list[datetime] = []
        for market in ("B3", "NASDAQ", "NYSE"):
            snapshot = self.database.latest_analysis_snapshot(ANALYSIS_TYPE, f"{market}_V2_DATA")
            published = snapshot.get("published_at") if snapshot else None
            if not isinstance(published, datetime):
                return None
            stamps.append(published if published.tzinfo else published.replace(tzinfo=timezone.utc))
        return min(stamps)

    # ------------------------------------------------------------------ reads

    def packets(self, market: V2Market) -> dict[str, dict[str, Any]]:
        snapshot = self.database.latest_analysis_snapshot(ANALYSIS_TYPE, f"{market}_V2_DATA")
        outputs = snapshot.get("outputs") if snapshot else None
        packets = outputs.get("packets") if isinstance(outputs, dict) else None
        return {
            str(symbol): packet
            for symbol, packet in (packets or {}).items()
            if isinstance(packet, dict)
        } if isinstance(packets, dict) else {}

    def coverage_summary(self, market: V2Market) -> dict[str, Any] | None:
        snapshot = self.database.latest_analysis_snapshot(ANALYSIS_TYPE, f"{market}_V2_DATA")
        outputs = snapshot.get("outputs") if snapshot else None
        summary = outputs.get("coverage_summary") if isinstance(outputs, dict) else None
        return summary if isinstance(summary, dict) else None

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _coverage(packet: dict[str, Any], *, today: date) -> dict[str, Any]:
        peers = [
            peer for peer in packet.get("peers") or []
            if isinstance(peer, dict) and peer.get("symbol")
        ]
        forward_estimates = ValuationV2DataService._forward_estimates(packet, today=today)
        history_years = {
            str(row.get("fiscal_year_end"))[:4]
            for row in packet.get("ratios_annual") or []
            if isinstance(row, dict)
            and any(
                _number(row.get(field)) is not None
                for field in ("pe", "ev_ebitda", "price_to_book")
            )
        }
        statuses = packet.get("provider_status")
        statuses = statuses if isinstance(statuses, dict) else {}
        endpoint_statuses = [
            statuses.get(endpoint) if isinstance(statuses.get(endpoint), dict) else {}
            for endpoint in _PROVIDER_ENDPOINTS
        ]
        provider_error_count = sum(
            str(status.get("status") or "") in _PROVIDER_FAILURE_STATUSES
            for status in endpoint_statuses
        )
        endpoint_response_count = sum(
            str(status.get("status") or "") in {"ok", "empty"}
            for status in endpoint_statuses
        )
        has_any_data = any(bool(packet.get(key)) for key in _PACKET_DATA_KEYS)
        return {
            "has_any_data": has_any_data,
            "provider_complete": endpoint_response_count == len(_PROVIDER_ENDPOINTS),
            "provider_error_count": provider_error_count,
            "endpoint_response_count": endpoint_response_count,
            "peer_count": len(peers),
            "peers_ok": len(peers) >= MIN_PEER_SAMPLE,
            "forward_fiscal_years": len(forward_estimates),
            "fy1_available": len(forward_estimates) >= 1,
            "fy2_available": len(forward_estimates) >= 2,
            "estimates_ok": len(forward_estimates) >= 1,
            "history_years": len(history_years),
            "history_ok": len(history_years) >= MIN_HISTORY_YEARS,
        }

    @staticmethod
    def _summary(
        packets: dict[str, dict[str, Any]], *, universe_size: int,
    ) -> dict[str, int]:
        coverages = [packet["coverage"] for packet in packets.values()]
        return {
            "universe": universe_size,
            "attempted": len(coverages),
            "covered": sum(bool(item["has_any_data"]) for item in coverages),
            "uncovered": max(0, universe_size - sum(bool(item["has_any_data"]) for item in coverages)),
            "provider_complete": sum(bool(item["provider_complete"]) for item in coverages),
            "provider_error_symbols": sum(bool(item["provider_error_count"]) for item in coverages),
            "endpoint_errors": sum(int(item["provider_error_count"]) for item in coverages),
            "endpoint_responses": sum(int(item["endpoint_response_count"]) for item in coverages),
            "peers_ok": sum(bool(item["peers_ok"]) for item in coverages),
            "estimates_ok": sum(bool(item["estimates_ok"]) for item in coverages),
            "history_ok": sum(bool(item["history_ok"]) for item in coverages),
            "all_anchors": sum(
                bool(item["peers_ok"] and item["estimates_ok"] and item["history_ok"])
                for item in coverages
            ),
        }

    @staticmethod
    def _forward_estimates(packet: dict[str, Any], *, today: date) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for row in packet.get("analyst_estimates_annual") or []:
            if not isinstance(row, dict) or _number(row.get("eps_avg")) is None:
                continue
            try:
                fiscal_end = date.fromisoformat(str(row.get("fiscal_year_end") or ""))
            except ValueError:
                continue
            if fiscal_end >= today:
                output.append(row)
        output.sort(key=lambda row: str(row.get("fiscal_year_end") or ""))
        return output

    @staticmethod
    def _missing_packet(provider_symbol: str) -> dict[str, Any]:
        missing_status = {
            "status": "error",
            "error_type": "MissingBatchResult",
            "raw_rows": 0,
            "parsed_rows": 0,
        }
        return {
            "symbol": provider_symbol,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "peers": [],
            "analyst_estimates_annual": [],
            "ratios_annual": [],
            "key_metrics_annual": [],
            "provider_status": {
                endpoint: dict(missing_status) for endpoint in _PROVIDER_ENDPOINTS
            },
        }

    def _universe_stocks(self, market: V2Market) -> list[dict[str, Any]]:
        snapshot = self.database.latest_analysis_snapshot(
            "valuation_universe", _UNIVERSE_SNAPSHOT_KEY[market]
        )
        outputs = snapshot.get("outputs") if snapshot else None
        rows = outputs.get("rows") if isinstance(outputs, dict) else None
        rows = rows if isinstance(rows, list) else []
        # Mirrors chewie_fundamentals._universe_stocks: the B3 screener never
        # sets "security_type" (stocks-only by construction); only the US
        # universe tags Stock vs ETF and needs the filter.
        stocks = [
            row for row in rows
            if isinstance(row, dict)
            and row.get("symbol")
            and (market == "B3" or row.get("security_type") == "Stock")
        ]
        stocks.sort(key=lambda row: _number(row.get("market_cap")) or 0.0, reverse=True)
        return stocks


def main() -> int:
    """Explicit operator backfill (outside trading hours): fetch and persist
    the V2.1 packets now instead of waiting for the next 01:00 cycle."""
    import json
    import logging

    from .config import get_settings
    from .market_data.service import MarketDataService

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    database = Database(settings)
    database.initialize()
    market_data = MarketDataService(settings, database)
    service = ValuationV2DataService(settings, database, market_data.http)
    counts = service.refresh_all()
    print(json.dumps(counts, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
