from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any, Literal

from .config import Settings
from .database import Database
from .market_data.brapi import BrapiClient
from .market_data.http import JsonHttpClient
from .valuation_v2_data import ValuationV2DataService, _configure_cli_logging
from .valuation_v2_engine import ENGINE_VERSION, ValuationV2Engine


V2Market = Literal["B3", "NASDAQ", "NYSE"]

ANALYSIS_TYPE = "valuation_v2_shadow"
METHODOLOGY_KEY = "valuation_v2_shadow"
METHODOLOGY_VERSION = 2

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


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


class ValuationV2ShadowService:
    """Runs the V2 engine side by side with production V1, writing shadow
    snapshots that nothing consumes. This is V2.3's evidence trail: the same
    divergence distribution the V2.0 baseline measured, now for V2, directly
    comparable market by market and profile by profile.

    Peer multiples are resolved from data already persisted by the nightly
    cycles (screener universes and the Chewie full-listing fundamentals
    snapshots) -- the shadow costs zero provider calls beyond the B3
    risk-free curve read.
    """

    def __init__(self, settings: Settings, database: Database, http: JsonHttpClient) -> None:
        self.settings = settings
        self.database = database
        self.http = http
        self.v2_data = ValuationV2DataService(settings, database, http)

    # ------------------------------------------------------------------ runs

    def run(self, market: V2Market) -> dict[str, Any]:
        rows = self._universe_rows(market)
        packets = self.v2_data.packets(market)
        multiples_index = self._multiples_index(market)
        sector_medians = self._sector_fair_multiples(rows)
        engine = ValuationV2Engine(
            market="B3" if market == "B3" else "US",
            risk_free_rate=self._risk_free(market),
        )

        results: dict[str, dict[str, Any]] = {}
        comparisons: list[dict[str, Any]] = []
        for row in rows:
            symbol = str(row.get("symbol"))
            packet = packets.get(symbol)
            peer_symbols = [
                str(peer.get("canonical_symbol") or peer.get("symbol"))
                for peer in (packet or {}).get("peers") or []
                if isinstance(peer, dict) and peer.get("symbol")
            ]
            peer_multiples = {
                peer: multiples_index[peer]
                for peer in peer_symbols
                if peer in multiples_index and peer != symbol
            }
            result = engine.evaluate(
                row,
                packet,
                peer_multiples=peer_multiples,
                sector_fair_multiples=sector_medians.get(str(row.get("sector") or "")),
            )
            if result is None:
                continue
            v1_final_tp = _number(row.get("our_tp"))
            v1_internal_tp = _number(row.get("internal_tp"))
            if v1_final_tp is None:
                v1_final_tp = v1_internal_tp
            if v1_internal_tp is None:
                v1_internal_tp = v1_final_tp
            consensus = result.get("consensus_tp")
            result["v1_final_tp"] = v1_final_tp
            result["v1_internal_tp"] = v1_internal_tp
            result["v1_final_divergence_vs_consensus"] = (
                round(abs(v1_final_tp / consensus - 1), 4)
                if v1_final_tp and consensus else None
            )
            result["v1_internal_divergence_vs_consensus"] = (
                round(abs(v1_internal_tp / consensus - 1), 4)
                if v1_internal_tp and consensus else None
            )
            result["peer_multiples_resolved"] = len(peer_multiples)
            results[symbol] = result
            comparisons.append(result)

        summary = self._summary(comparisons)
        methodology_id = self.database.ensure_methodology_version(
            METHODOLOGY_KEY,
            METHODOLOGY_VERSION,
            {
                "engine_version": ENGINE_VERSION,
                "comparison_rulers": "internal_to_internal,final_to_final",
                "consumers": "none_shadow_only",
            },
            "Valuation V2 shadow: V2 computed beside V1, consumed by nothing.",
        )
        self.database.save_analysis_snapshot(
            ANALYSIS_TYPE,
            f"{market}_V2_SHADOW",
            methodology_id,
            {"market": market, **{k: v for k, v in summary.items() if isinstance(v, (int, float))}},
            {"results": results, "summary": summary},
            datetime.now(timezone.utc),
        )
        return summary

    def run_all(self) -> dict[str, dict[str, Any]]:
        return {market: self.run(market) for market in ("B3", "NASDAQ", "NYSE")}

    def last_run_at(self) -> datetime | None:
        stamps: list[datetime] = []
        for market in ("B3", "NASDAQ", "NYSE"):
            snapshot = self.database.latest_analysis_snapshot(ANALYSIS_TYPE, f"{market}_V2_SHADOW")
            published = snapshot.get("published_at") if snapshot else None
            if not isinstance(published, datetime):
                return None
            stamps.append(published if published.tzinfo else published.replace(tzinfo=timezone.utc))
        return min(stamps)

    def results(self, market: V2Market) -> dict[str, dict[str, Any]]:
        snapshot = self.database.latest_analysis_snapshot(ANALYSIS_TYPE, f"{market}_V2_SHADOW")
        outputs = snapshot.get("outputs") if snapshot else None
        results = outputs.get("results") if isinstance(outputs, dict) else None
        return {
            str(symbol): item
            for symbol, item in (results or {}).items()
            if isinstance(item, dict)
        } if isinstance(results, dict) else {}

    def result_for(self, market: V2Market, symbol: str) -> dict[str, Any] | None:
        return self.results(market).get(symbol.strip().upper())

    # ------------------------------------------------------------------ summary

    @staticmethod
    def _summary(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
        def values(field: str) -> list[float]:
            return [
                float(item[field]) for item in comparisons if item.get(field) is not None
            ]

        v2_internal = values("internal_divergence_vs_consensus")
        v1_internal = values("v1_internal_divergence_vs_consensus")
        v2_final = values("final_divergence_vs_consensus")
        v1_final = values("v1_final_divergence_vs_consensus")
        by_profile: dict[str, list[float]] = {}
        for item in comparisons:
            if item.get("internal_divergence_vs_consensus") is not None:
                by_profile.setdefault(str(item.get("profile")), []).append(
                    item["internal_divergence_vs_consensus"]
                )

        def percentile(values_: list[float], fraction: float) -> float | None:
            result = _percentile(values_, fraction)
            return round(result, 4) if result is not None else None

        v2_internal_p50 = percentile(v2_internal, 0.50)
        v2_internal_p90 = percentile(v2_internal, 0.90)
        v1_internal_p50 = percentile(v1_internal, 0.50)
        v1_internal_p90 = percentile(v1_internal, 0.90)
        return {
            "evaluated": len(comparisons),
            "with_consensus": len(v2_internal),
            "low_conviction": sum(bool(item.get("low_conviction")) for item in comparisons),
            "comparison_ruler_for_p4": "internal_tp_vs_consensus",
            "v2_internal_divergence_p50": v2_internal_p50,
            "v2_internal_divergence_p90": v2_internal_p90,
            "v1_internal_divergence_p50": v1_internal_p50,
            "v1_internal_divergence_p90": v1_internal_p90,
            "v2_final_divergence_p50": percentile(v2_final, 0.50),
            "v2_final_divergence_p90": percentile(v2_final, 0.90),
            "v1_final_divergence_p50": percentile(v1_final, 0.50),
            "v1_final_divergence_p90": percentile(v1_final, 0.90),
            # Operator-compatible names are explicit aliases of the frozen P4
            # internal ruler, never a mixture of internal and final TPs.
            "v2_divergence_p50": v2_internal_p50,
            "v2_divergence_p90": v2_internal_p90,
            "v1_divergence_p50": v1_internal_p50,
            "v1_divergence_p90": v1_internal_p90,
            "meets_p50_target": v2_internal_p50 <= 0.15 if v2_internal_p50 is not None else None,
            "meets_p90_target": v2_internal_p90 <= 0.30 if v2_internal_p90 is not None else None,
            "internal_divergence_p50_by_profile": {
                profile: percentile(profile_values, 0.50)
                for profile, profile_values in sorted(by_profile.items())
            },
            "divergence_p50_by_profile": {
                profile: percentile(profile_values, 0.50)
                for profile, profile_values in sorted(by_profile.items())
            },
        }

    # ------------------------------------------------------------------ inputs

    def _universe_rows(self, market: V2Market) -> list[dict[str, Any]]:
        snapshot = self.database.latest_analysis_snapshot(
            "valuation_universe", _UNIVERSE_SNAPSHOT_KEY[market]
        )
        outputs = snapshot.get("outputs") if snapshot else None
        rows = outputs.get("rows") if isinstance(outputs, dict) else None
        rows = rows if isinstance(rows, list) else []
        return [
            row for row in rows
            if isinstance(row, dict)
            and row.get("symbol")
            and (market == "B3" or row.get("security_type") == "Stock")
        ]

    def _multiples_index(self, market: V2Market) -> dict[str, dict[str, Any]]:
        """symbol -> multiples for peer resolution, built from persisted
        snapshots only. US peers may sit on either exchange, so both US
        universes and both US Chewie snapshots feed one shared index."""
        markets: tuple[V2Market, ...] = ("B3",) if market == "B3" else ("NASDAQ", "NYSE")
        index: dict[str, dict[str, Any]] = {}
        for source_market in markets:
            for item in self._chewie_items(source_market):
                symbol = str(item.get("symbol") or "")
                multiples = item.get("multiples") if isinstance(item.get("multiples"), dict) else {}
                profitability = (
                    item.get("profitability") if isinstance(item.get("profitability"), dict) else {}
                )
                roe_percent = _number(profitability.get("roe_percent"))
                if symbol:
                    index[symbol] = {
                        "pe": _number(multiples.get("pe")),
                        "forward_pe": _number(multiples.get("forward_pe")),
                        "ev_ebitda": _number(multiples.get("ev_ebitda")),
                        "price_to_book": _number(multiples.get("price_to_book")),
                        "roe": roe_percent / 100 if roe_percent is not None else None,
                    }
        for source_market in markets:
            for row in self._universe_rows(source_market):
                symbol = str(row.get("symbol") or "")
                if not symbol:
                    continue
                roe = _number(row.get("roe"))
                if roe is None:
                    roe_percent = _number(row.get("roe_percent"))
                    roe = roe_percent / 100 if roe_percent is not None else None
                index[symbol] = {
                    "pe": _number(row.get("pe")),
                    "forward_pe": _number(row.get("forward_pe")),
                    "ev_ebitda": _number(row.get("ev_ebitda")),
                    "price_to_book": _number(row.get("price_to_book")),
                    "roe": roe,
                }
        return index

    @staticmethod
    def _sector_fair_multiples_for(rows: list[dict[str, Any]], sector: str) -> dict[str, float]:
        output: dict[str, float] = {}
        for metric in ("pe", "forward_pe", "ev_ebitda", "price_to_book"):
            values = [
                value for row in rows
                if str(row.get("sector") or "") == sector
                and (value := _number(row.get(metric))) is not None
                and value > 0
            ]
            if len(values) >= 5:
                output[metric] = median(values)
        return output

    def _sector_fair_multiples(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        sectors = {str(row.get("sector") or "") for row in rows if row.get("sector")}
        return {
            sector: self._sector_fair_multiples_for(rows, sector) for sector in sectors
        }

    def _chewie_items(self, market: V2Market) -> list[dict[str, Any]]:
        snapshot = self.database.latest_analysis_snapshot(
            "chewie_fundamentals", f"{market}_FUNDAMENTALS"
        )
        outputs = snapshot.get("outputs") if snapshot else None
        items = outputs.get("items") if isinstance(outputs, dict) else None
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def _risk_free(self, market: V2Market) -> float | None:
        """B3: the prefixado point closest to the model's five-year horizon.

        Taking the median of every listed maturity silently mixed short and
        long duration. Matching the reverse-DCF horizon makes the observed
        curve an auditable input. US keeps the engine fallback until the
        shadow grows a Treasury feed.
        """
        if market != "B3":
            return None
        if not self.settings.brapi_token:
            return None
        try:
            client = BrapiClient(self.settings.brapi_base_url, self.settings.brapi_token, self.http)
            candidates: list[tuple[int, float]] = []
            fallback_rates: list[float] = []
            for bond in client.treasury_rates(indexer="prefixado"):
                bond_rates = [
                    rate for field in ("buy_rate", "sell_rate")
                    if (rate := _number(bond.get(field))) is not None and 0 < rate < 50
                ]
                if not bond_rates:
                    continue
                rate = median(bond_rates)
                fallback_rates.append(rate)
                duration_days = int(_number(bond.get("duration_days")) or 0)
                if duration_days > 0:
                    candidates.append((duration_days, rate))
            if not fallback_rates:
                return None
            value = (
                min(candidates, key=lambda item: abs(item[0] - 5 * 365))[1]
                if candidates else median(fallback_rates)
            )
            return value / 100 if value > 1 else value
        except Exception:
            return None


def main() -> int:
    """Explicit operator run (outside trading hours): compute and persist the
    V2 shadow now instead of waiting for the next off-hours cycle."""
    import json

    from .config import get_settings
    from .market_data.service import MarketDataService

    _configure_cli_logging()
    settings = get_settings()
    database = Database(settings)
    database.initialize()
    market_data = MarketDataService(settings, database)
    service = ValuationV2ShadowService(settings, database, market_data.http)
    summaries = service.run_all()
    print(json.dumps(summaries, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
