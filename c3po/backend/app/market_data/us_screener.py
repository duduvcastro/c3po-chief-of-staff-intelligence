from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta, timezone
from threading import Lock, RLock
from typing import Any, Literal, TYPE_CHECKING

from ..config import Settings
from ..database import Database
from ..schemas import B3Candidate, B3CandidateResponse, MatrixPowerItem, MatrixPowerResponse
from ..valuation_policy import C3PO_VALUATION_POLICY, METHODOLOGY_KEY, METHODOLOGY_NAME, METHODOLOGY_VERSION
from .b3_screener import ABSOLUTE_LOW_RISK_LIMIT, LATEST_COPOM_SELIC, MAX_ENTRY_DISTANCE, TP_UPSIDE_PREMIUM
from .eodhd import EodhdClient
from .models import canonical_us_security_type
from .realtime import RealtimeMarketsService

if TYPE_CHECKING:
    from ..one_pager import OnePagerService


USMarket = Literal["NASDAQ", "NYSE"]
STOCK_LIMIT = 300
ETF_LIMIT = 25
MIN_PRICE = 3.0
MIN_STOCK_MARKET_CAP = 750_000_000.0
MIN_ETF_ASSETS = 750_000_000.0
MIN_STOCK_CASH_VOLUME = 20_000_000.0
MIN_ETF_CASH_VOLUME = 10_000_000.0
MIN_HISTORY_DAYS = 40
MIN_CONFIDENCE = 70.0
MAX_DISPERSION = 45.0
PROVISIONAL_CONFIDENCE = 55.0
PROVISIONAL_DISPERSION = 60.0
MATRIX_REFRESH_SECONDS = 60
INSIDER_GOVERNANCE_LOOKBACK_DAYS = 180
# Root-caused 2026-08-20 (TP methodology audit): B3 has a rolling backtest
# that measures forecast bias by valuation profile and multiplicatively
# corrects internal_tp by up to +/-5% (b3_screener.py's _persist_calibration);
# the US engine had no equivalent, so a systematic bias would never be
# detected or corrected. Same thresholds as B3, mirrored exactly.
CALIBRATION_HORIZON_DAYS = 90
CALIBRATION_MIN_GLOBAL_SAMPLES = 40
CALIBRATION_MIN_PROFILE_SAMPLES = 15
CALIBRATION_FACTOR_LIMIT = 0.05
PROVIDER_DELAY_MINUTES = 15


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def positive(value: Any) -> float | None:
    result = number(value)
    return result if result is not None and result > 0 else None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalized_percent(value: Any) -> float | None:
    parsed = number(value)
    if parsed is None:
        return None
    return parsed * 100 if abs(parsed) <= 1.5 else parsed


class USScreeningService:
    """Canonical US screening shared by Dark Side, Last Jedi and Laser Pager."""

    def __init__(
        self,
        settings: Settings,
        database: Database,
        realtime: RealtimeMarketsService,
        one_pagers: OnePagerService,
    ) -> None:
        self.settings = settings
        self.database = database
        self.realtime = realtime
        self.one_pagers = one_pagers
        self._lock = RLock()
        self._matrix_lock = Lock()
        self._rows: dict[USMarket, list[dict[str, Any]]] = {"NASDAQ": [], "NYSE": []}
        self._basis_at: dict[USMarket, datetime | None] = {"NASDAQ": None, "NYSE": None}
        self._universe_size: dict[USMarket, int] = {"NASDAQ": STOCK_LIMIT + ETF_LIMIT, "NYSE": STOCK_LIMIT + ETF_LIMIT}
        self._coverage: dict[USMarket, dict[str, int]] = {"NASDAQ": {}, "NYSE": {}}
        self._calibration_factors: dict[USMarket, dict[str, float]] = {"NASDAQ": {}, "NYSE": {}}
        self._peer_medians: dict[USMarket, dict[str, dict[str, float]]] = {"NASDAQ": {}, "NYSE": {}}

    @staticmethod
    def _market(value: str) -> USMarket:
        market = value.strip().upper()
        if market not in {"NASDAQ", "NYSE"}:
            raise ValueError("US market must be NASDAQ or NYSE")
        return market  # type: ignore[return-value]

    def screen(self, market: str, *, refresh: bool = False) -> B3CandidateResponse:
        selected_market = self._market(market)
        with self._lock:
            if refresh:
                self._build(selected_market)
            elif not self._rows[selected_market]:
                self._hydrate(selected_market)
                if not self._rows[selected_market]:
                    self._build(selected_market)
            return self._candidate_response(selected_market)

    def matrix(self, market: str) -> MatrixPowerResponse:
        selected_market = self._market(market)
        if not self._rows[selected_market]:
            self.screen(selected_market)
        with self._matrix_lock:
            return self._matrix_response(selected_market)

    def refresh_all(self) -> dict[str, int]:
        return {market: len(self._build(market)) for market in ("NASDAQ", "NYSE")}

    def valuation_for(self, symbol: str, market: str | None = None) -> dict[str, Any] | None:
        clean = symbol.strip().upper().removesuffix(".US")
        markets = [self._market(market)] if market else ["NASDAQ", "NYSE"]
        for selected_market in markets:
            if not self._rows[selected_market]:
                self._hydrate(selected_market)
            row = next((item for item in self._rows[selected_market] if item["symbol"] == clean), None)
            if row:
                return dict(row)
        return None

    def peer_medians(self, market: str | None = None) -> dict[str, dict[str, float]]:
        """Latest batch-computed peer-median multiples, reused by the
        single-symbol Laser Pager path so it doesn't need its own bulk
        fundamentals fetch just to price one stock. `market` follows
        valuation_for()'s convention: pass "NASDAQ"/"NYSE" for one exchange,
        or omit it (the Laser Pager caller only knows "US", not the
        specific exchange) to merge both — profile buckets like
        "technology"/"financial" are the same taxonomy on either exchange.

        The api and valuation-worker containers are separate processes
        (see compose.yml) that don't share Python memory, so unlike this
        in-memory dict alone, this getter also hydrates from a persisted
        snapshot on first use — otherwise every Laser Pager generated from
        the api container would see an empty dict forever, since only the
        worker's _build() ever populates it in-process."""
        markets = [self._market(market)] if market else ["NASDAQ", "NYSE"]
        for selected_market in markets:
            if not self._peer_medians[selected_market]:
                self._load_peer_medians(selected_market)
        if market:
            return self._peer_medians[self._market(market)]
        merged: dict[str, dict[str, float]] = {}
        for exchange in ("NASDAQ", "NYSE"):
            for profile, values in self._peer_medians[exchange].items():
                merged.setdefault(profile, values)
        return merged

    def _load_peer_medians(self, market: USMarket) -> None:
        snapshot = self.database.latest_analysis_snapshot("peer_medians", f"{market}_PEER_MEDIANS")
        if not snapshot:
            return
        outputs = snapshot.get("outputs") if isinstance(snapshot.get("outputs"), dict) else {}
        medians = outputs.get("medians") if isinstance(outputs, dict) else None
        if not isinstance(medians, dict):
            return
        self._peer_medians[market] = {
            str(profile): {str(key): float(value) for key, value in values.items()}
            for profile, values in medians.items()
            if isinstance(values, dict)
        }

    def _build(self, market: USMarket) -> list[dict[str, Any]]:
        if not self.settings.eodhd_api_token:
            raise RuntimeError("EODHD credential is not configured")
        self._load_calibration_factors(market)
        now = datetime.now(timezone.utc)
        catalog = self.realtime._us_symbol_catalog(now)
        raw_quotes = self.realtime._us_bulk_quotes(now)
        quote_map = {
            self.realtime._us_symbol(raw.get("code") or raw.get("Code")): raw
            for raw in raw_quotes
            if isinstance(raw, dict)
        }
        stocks: list[tuple[float, Any, dict[str, Any]]] = []
        etfs: list[tuple[float, Any, dict[str, Any]]] = []
        audit = {
            "catalog": 0,
            "missing_quote": 0,
            "insufficient_history": 0,
            "market_cap_gate": 0,
            "liquidity_gate": 0,
            "fundamental_quality_gate": 0,
            "calculated_tp": 0,
        }
        for symbol, metadata in catalog.items():
            is_etf = self._is_etf(metadata)
            resolved_market = (
                self.realtime._portfolio_catalog_market(metadata)
                if is_etf else self.realtime._catalog_market(metadata)
            )
            if resolved_market != market or not self.realtime._is_portfolio_security(metadata):
                continue
            audit["catalog"] += 1
            raw_quote = quote_map.get(symbol)
            if not raw_quote:
                audit["missing_quote"] += 1
                continue
            quote = self.realtime._us_row(raw_quote, metadata, market, now)
            if not quote or quote.price < MIN_PRICE:
                audit["missing_quote"] += 1
                continue
            cash_volume = quote.cash_volume or 0.0
            target = etfs if is_etf else stocks
            target.append((cash_volume, quote, metadata))

        selected = sorted(stocks, key=lambda row: row[0], reverse=True)[:STOCK_LIMIT]
        selected += sorted(etfs, key=lambda row: row[0], reverse=True)[:ETF_LIMIT]
        symbols = [quote.symbol for _, quote, _ in selected]
        client = EodhdClient(self.settings.eodhd_base_url, self.settings.eodhd_api_token, self.realtime.http)
        fundamentals = client.fundamentals(symbols, exchange="US", workers=10)
        histories = client.histories(symbols, exchange="US", days=400, workers=10)
        ir_events = self.database.latest_valuation_ir_events(symbols, market=market)
        insider_since = datetime.now(timezone.utc) - timedelta(days=INSIDER_GOVERNANCE_LOOKBACK_DAYS)
        insider_activity = self.database.insider_transaction_activity(symbols, market, insider_since)
        news_sentiment = self.database.latest_news_sentiment(symbols, market="US")
        risk_free_rate = self.one_pagers._us_risk_free_rate()
        peer_medians = self.one_pagers._us_peer_medians(fundamentals)
        self._peer_medians[market] = peer_medians
        fmp_consensus_data = self.one_pagers._fmp_consensus_batch(symbols)
        rows: list[dict[str, Any]] = []
        for cash_volume, quote, metadata in selected:
            symbol = quote.symbol
            fundamental = fundamentals.get(symbol) or {}
            history = histories.get(symbol) or []
            is_etf = self._is_etf(metadata) or bool(fundamental.get("isETF"))
            minimum_liquidity = MIN_ETF_CASH_VOLUME if is_etf else MIN_STOCK_CASH_VOLUME
            if cash_volume < minimum_liquidity:
                audit["liquidity_gate"] += 1
                continue
            if len(history) < MIN_HISTORY_DAYS:
                audit["insufficient_history"] += 1
                continue
            size = positive(fundamental.get("etfTotalAssets") if is_etf else fundamental.get("marketCap"))
            minimum_size = MIN_ETF_ASSETS if is_etf else MIN_STOCK_MARKET_CAP
            if size is None or size < minimum_size:
                audit["market_cap_gate"] += 1
                continue
            fmp_consensus, fmp_summary = fmp_consensus_data.get(symbol, (None, None))
            try:
                row = (
                    self._analyze_etf(market, quote.model_dump(), fundamental, history, cash_volume)
                    if is_etf
                    else self._analyze_stock(
                        market, quote.model_dump(), fundamental, history, cash_volume,
                        insider_activity=insider_activity.get(symbol),
                        news_sentiment=news_sentiment.get(symbol),
                        risk_free_rate=risk_free_rate,
                        peer_medians=peer_medians,
                        fmp_consensus=fmp_consensus,
                        fmp_summary=fmp_summary,
                    )
                )
            except Exception:
                audit["fundamental_quality_gate"] += 1
                continue
            row.update(self._ir_freshness(
                fundamental.get("financialsAsOf") or fundamental.get("updated_at"),
                ir_events.get(symbol),
            ))
            rows.append(row)
            audit["calculated_tp"] += 1

        risk_cutoff = self._risk_cutoff(rows)
        tp_cutoff = self._tp_cutoff()
        for row in rows:
            row["status"] = (
                "full_match"
                if row["signal_quality"] == "validated"
                and row["upside_percent"] >= tp_cutoff
                and row["risk_score"] < risk_cutoff
                and -10 <= row["price_vs_buy_in_percent"] <= MAX_ENTRY_DISTANCE
                else "near_buy"
                if row["signal_quality"] == "validated" and row["upside_percent"] >= tp_cutoff
                else "watchlist"
            )

        self._rows[market] = rows
        self._basis_at[market] = now
        self._universe_size[market] = len(selected)
        self._coverage[market] = audit
        self._persist(market)
        return rows

    def _analyze_stock(
        self,
        market: USMarket,
        quote: dict[str, Any],
        fundamentals: dict[str, Any],
        history: list[dict[str, Any]],
        cash_volume: float,
        *,
        insider_activity: dict[str, Any] | None = None,
        news_sentiment: dict[str, Any] | None = None,
        risk_free_rate: float | None = None,
        peer_medians: dict[str, dict[str, float]] | None = None,
        fmp_consensus: dict[str, float] | None = None,
        fmp_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        symbol = str(quote["symbol"])
        analysis = self.one_pagers._analyze(
            symbol, "US", quote, fundamentals, history,
            insider_activity=insider_activity,
            news_sentiment=news_sentiment,
            risk_free_rate=risk_free_rate,
            peer_medians=peer_medians,
            fmp_consensus=fmp_consensus,
            fmp_summary=fmp_summary,
        )
        methods = {str(key): float(value) for key, value in analysis["methods"].items() if positive(value)}
        consensus = positive(analysis.get("consensus_tp"))
        internal_tp = statistics.mean(methods.values())
        profile = str(analysis.get("profile") or "general")
        market_factors = self._calibration_factors.get(market, {})
        calibration_factor = clamp(
            market_factors.get(profile, market_factors.get("global", 1.0)),
            1 - CALIBRATION_FACTOR_LIMIT, 1 + CALIBRATION_FACTOR_LIMIT,
        )
        internal_tp *= calibration_factor
        calibrated_tp = float(analysis["c3po_tp"]) * calibration_factor
        gap = abs(internal_tp / consensus - 1) * 100 if consensus else None
        agreement = clamp(100 - (gap or 45) * 1.35, 25, 100)
        confidence = float(analysis["confidence"])
        dispersion = float(analysis["dispersion"])
        analyst_count = int(analysis.get("analyst_count") or 0) or None
        data_sources = 2 if consensus and analyst_count and analyst_count >= 2 else 1
        validation_score = clamp(
            confidence * 0.45 + agreement * 0.30 + min(len(methods), 5) / 5 * 15 + min(analyst_count or 0, 10) / 10 * 10,
            0,
            100,
        )
        reasons: list[str] = []
        if confidence < MIN_CONFIDENCE:
            reasons.append("confidence below 70")
        if dispersion > MAX_DISPERSION:
            reasons.append("method dispersion above 45%")
        if data_sources < 2:
            reasons.append("public consensus unavailable")
        validated = not reasons and validation_score >= 65
        return self._common_row(
            market,
            quote,
            fundamentals,
            history,
            cash_volume,
            security_type="Stock",
            our_tp=calibrated_tp,
            internal_tp=internal_tp,
            consensus=consensus,
            analyst_count=analyst_count,
            buy_in=float(analysis["buy_in"]),
            methods=methods,
            risk=float(analysis["risk_score"]),
            confidence=confidence,
            dispersion=dispersion,
            agreement=agreement,
            data_sources=data_sources,
            validation_score=validation_score,
            reasons=reasons,
            validated=validated,
            thesis=str((analysis.get("thesis") or [""])[0]),
            risk_text=str((analysis.get("risks") or [""])[0]),
        )

    def _analyze_etf(
        self,
        market: USMarket,
        quote: dict[str, Any],
        fundamentals: dict[str, Any],
        history: list[dict[str, Any]],
        cash_volume: float,
    ) -> dict[str, Any]:
        price = float(quote["price"])
        closes = [float(row["close"]) for row in history if positive(row.get("close"))]
        daily_returns = [closes[index] / closes[index - 1] - 1 for index in range(1, len(closes)) if closes[index - 1] > 0]
        volatility = statistics.pstdev(daily_returns[-252:]) * math.sqrt(252) if len(daily_returns) >= 20 else 0.30
        momentum_3m = closes[-1] / closes[-min(63, len(closes))] - 1
        momentum_6m = closes[-1] / closes[-min(126, len(closes))] - 1
        momentum_12m = closes[-1] / closes[0] - 1
        peak = closes[0]
        max_drawdown = 0.0
        for close in closes:
            peak = max(peak, close)
            max_drawdown = min(max_drawdown, close / peak - 1)
        provider_return = normalized_percent(fundamentals.get("etfExpectedReturn3Y"))
        provider_return = provider_return / 100 if provider_return is not None and -50 <= provider_return <= 80 else None
        trend_return = (momentum_3m * 0.45 + momentum_6m * 0.35 + momentum_12m * 0.20)
        risk_adjusted = trend_return - volatility * 0.16
        expected = clamp(
            statistics.mean([value for value in (provider_return, momentum_12m, trend_return, risk_adjusted) if value is not None]),
            -0.18,
            0.48,
        )
        return_methods = {
            "Asset allocation": clamp(expected, -0.15, 0.45),
            "12M momentum": clamp(momentum_12m, -0.20, 0.50),
            "6M momentum": clamp(momentum_6m * 1.35, -0.20, 0.50),
            "Trend quality": clamp(trend_return, -0.18, 0.45),
            "Risk adjusted": clamp(risk_adjusted, -0.18, 0.40),
        }
        methods = {name: price * (1 + value) for name, value in return_methods.items()}
        our_tp = statistics.mean(methods.values())
        risk = clamp(18 + volatility * 85 + abs(max_drawdown) * 45, 15, 85)
        dispersion = statistics.pstdev(methods.values()) / statistics.mean(methods.values()) * 100
        holdings = int(fundamentals.get("etfHoldingsCount") or 0)
        assets = positive(fundamentals.get("etfTotalAssets")) or 0
        completeness = sum(value is not None for value in (provider_return, volatility, max_drawdown, fundamentals.get("etfNetExpenseRatio"))) / 4
        confidence = clamp(58 + completeness * 20 + min(holdings, 100) / 100 * 8 + min(len(history), 252) / 252 * 8, 55, 94)
        agreement = clamp(100 - dispersion * 2.2, 30, 100)
        validation_score = clamp(confidence * 0.55 + agreement * 0.35 + 10, 0, 100)
        reasons: list[str] = []
        if confidence < MIN_CONFIDENCE:
            reasons.append("ETF evidence confidence below 70")
        if dispersion > MAX_DISPERSION:
            reasons.append("ETF method dispersion above 45%")
        validated = not reasons and validation_score >= 65
        entry_discount = 0.12 + risk / 100 * 0.10 + (100 - confidence) / 100 * 0.04
        buy_in = our_tp / (1 + entry_discount)
        category = str(fundamentals.get("etfCategory") or fundamentals.get("sector") or "Diversified ETF")
        return self._common_row(
            market,
            quote,
            fundamentals,
            history,
            cash_volume,
            security_type="ETF",
            our_tp=our_tp,
            internal_tp=our_tp,
            consensus=None,
            analyst_count=None,
            buy_in=buy_in,
            methods=methods,
            risk=risk,
            confidence=confidence,
            dispersion=dispersion,
            agreement=agreement,
            data_sources=2,
            validation_score=validation_score,
            reasons=reasons,
            validated=validated,
            thesis=f"{category}: diversified return model combines trend, drawdown, volatility, assets and holdings quality.",
            risk_text=f"ETF risk reflects {volatility * 100:.1f}% annualized volatility and {abs(max_drawdown) * 100:.1f}% maximum drawdown.",
            quality_score=round(clamp(72 - volatility * 45 + min(math.log10(max(assets, 1)) - 8, 4) * 4, 30, 92)),
        )

    def _common_row(
        self,
        market: USMarket,
        quote: dict[str, Any],
        fundamentals: dict[str, Any],
        history: list[dict[str, Any]],
        cash_volume: float,
        *,
        security_type: Literal["Stock", "ETF"],
        our_tp: float,
        internal_tp: float,
        consensus: float | None,
        analyst_count: int | None,
        buy_in: float,
        methods: dict[str, float],
        risk: float,
        confidence: float,
        dispersion: float,
        agreement: float,
        data_sources: int,
        validation_score: float,
        reasons: list[str],
        validated: bool,
        thesis: str,
        risk_text: str,
        quality_score: int = 70,
    ) -> dict[str, Any]:
        price = float(quote["price"])
        upside = (our_tp / price - 1) * 100
        entry_distance = (price / buy_in - 1) * 100
        expected_return = upside + (normalized_percent(fundamentals.get("dividendYield")) or 0)
        consensus_gap = abs(internal_tp / consensus - 1) * 100 if consensus else None
        operating_quality = clamp(
            50
            + (normalized_percent(fundamentals.get("returnOnEquity")) or 0) * 0.45
            + (normalized_percent(fundamentals.get("profitMargins")) or 0) * 0.30,
            20,
            95,
        ) if security_type == "Stock" else quality_score
        score = self._power_score(upside, risk, operating_quality, confidence, entry_distance)
        return {
            "market": market,
            "symbol": str(quote["symbol"]),
            "name": str(fundamentals.get("companyName") or quote.get("name") or quote["symbol"]),
            "security_type": security_type,
            "logo_url": EodhdClient.normalize_logo_url(fundamentals.get("logoUrl")) or None,
            "sector": str(fundamentals.get("etfCategory") or fundamentals.get("sector") or "Unclassified"),
            "industry": str(fundamentals.get("industry") or fundamentals.get("etfCategory") or ""),
            "peer_group": str(fundamentals.get("industry") or fundamentals.get("etfCategory") or ""),
            "sector_source": "EODHD ETF_Data" if security_type == "ETF" else "EODHD GICS",
            "sector_confidence": 90.0 if fundamentals.get("sector") or fundamentals.get("etfCategory") else 60.0,
            "valuation_profile": "general" if security_type == "ETF" else self._profile(fundamentals),
            "price": price,
            "change_percent": number(quote.get("change_percent")),
            "volume": number(quote.get("volume")),
            "adtv_90d": cash_volume,
            "market_cap": positive(fundamentals.get("etfTotalAssets") if security_type == "ETF" else fundamentals.get("marketCap")),
            "our_tp": our_tp,
            "internal_tp": internal_tp,
            "consensus_weight_percent": 0.0 if consensus is None else 35.0,
            "upside_percent": upside,
            "expected_total_return_percent": expected_return,
            "buy_in": buy_in,
            "price_vs_buy_in_percent": entry_distance,
            "buy_in_models": {name: target / (1 + 0.12 + risk / 100 * 0.10) for name, target in methods.items()},
            "methods": methods,
            "public_consensus_tp": consensus,
            "analyst_count": analyst_count,
            "pe": positive(fundamentals.get("trailingPE")),
            "forward_pe": positive(fundamentals.get("forwardPE")) or positive(fundamentals.get("etfForwardPE")),
            "ev_ebitda": positive(fundamentals.get("enterpriseToEbitda")),
            "peg": positive(fundamentals.get("pegRatio")),
            "price_to_book": positive(fundamentals.get("priceToBook")) or positive(fundamentals.get("etfPriceToBook")),
            "roe_percent": normalized_percent(fundamentals.get("returnOnEquity")),
            "fcf_yield_percent": None,
            "score": score,
            "risk_score": risk,
            "operating_quality": operating_quality,
            "valuation_confidence": confidence,
            "method_dispersion_percent": dispersion,
            "data_source_count": data_sources,
            "source_agreement_percent": agreement,
            "fundamentals_as_of": fundamentals.get("financialsAsOf") or fundamentals.get("updated_at"),
            "ir_status": "current" if security_type == "Stock" else "unavailable",
            "latest_ir_event_at": None,
            "latest_ir_event_type": None,
            "tp_validation_score": validation_score,
            "tp_validation_reasons": reasons,
            "consensus_gap_percent": consensus_gap,
            "valuation_method_count": len(methods) + (1 if consensus else 0),
            "internal_method_count": len(methods),
            "signal_quality": "validated" if validated else "provisional",
            "quality_score": int(quality_score),
            "thesis": thesis,
            "risk": risk_text,
            "beta": positive(fundamentals.get("beta")),
            "volatility_90d": self._volatility(history),
            "as_of": quote.get("as_of") or datetime.now(timezone.utc),
        }

    def _candidate_response(self, market: USMarket) -> B3CandidateResponse:
        rows = self._rows[market]
        tp_cutoff = self._tp_cutoff()
        risk_cutoff = self._risk_cutoff(rows)
        selected = sorted(
            (row for row in rows if row["status"] == "full_match"),
            key=lambda row: (row["upside_percent"], row["score"]),
            reverse=True,
        )[:10]
        items = [self._candidate(row, rank) for rank, row in enumerate(selected, 1)]
        return B3CandidateResponse(
            market=market,
            source="EODHD All-In-One",
            methodology=METHODOLOGY_NAME,
            methodology_version=METHODOLOGY_VERSION,
            universe_size=self._universe_size[market],
            eligible_count=len(rows),
            generated_at=self._basis_at[market] or datetime.now(timezone.utc),
            items=items,
            criteria={
                "ranking": "C3PO TP upside descending inside the validated Power Zone",
                "universe": f"Up to {STOCK_LIMIT} liquid stocks and {ETF_LIMIT} liquid ETFs listed in {market}",
                "minimums": "Price USD 3; stock market cap USD 750m; ETF assets USD 750m; daily cash volume USD 20m stocks / USD 10m ETFs",
                "quality": "Stocks use the canonical five-method valuation; ETFs use asset-allocation, momentum, trend, volatility and drawdown evidence",
                "valuation": "Same canonical C3PO methodology consumed by Dark Side, Last Jedi and Laser Pager",
                "score": "Power Score: 35% return, 25% inverse risk, 15% quality, 15% confidence, 10% entry",
                "tp_upside": f"C3PO TP upside >= Selic + 6 p.p. = {tp_cutoff:.1f}%",
                "entry": "Price within -10% to +15% of disciplined buy-in",
                "risk": f"Risk below min(40, eligible-universe median) = {risk_cutoff:.1f}/100",
                "confidence": "Validated valuation only: confidence >= 70, dispersion <= 45% and independent market evidence",
            },
        )

    def _matrix_response(self, market: USMarket) -> MatrixPowerResponse:
        now = datetime.now(timezone.utc)
        rows = [dict(row) for row in self._rows[market]]
        self._refresh_quotes(market, rows, now)
        tp_cutoff = self._tp_cutoff()
        risk_cutoff = self._risk_cutoff(rows)
        returns = [row["upside_percent"] for row in rows]
        risks = [row["risk_score"] for row in rows]
        return_low, return_high = self._bounds(returns, tp_cutoff)
        risk_low, risk_high = self._bounds(risks, risk_cutoff)
        items: list[MatrixPowerItem] = []
        for row in sorted(rows, key=lambda item: item["upside_percent"], reverse=True):
            quadrant = self._quadrant(row["upside_percent"], row["risk_score"], tp_cutoff, risk_cutoff)
            items.append(MatrixPowerItem(
                symbol=row["symbol"], name=row["name"], security_type=row["security_type"], logo_url=EodhdClient.normalize_logo_url(row.get("logo_url")) or None,
                sector=row["sector"], industry=row.get("industry"), peer_group=row.get("peer_group"),
                sector_source=row.get("sector_source"), sector_confidence=row.get("sector_confidence"),
                valuation_profile=row["valuation_profile"], price=round(row["price"], 2),
                change_percent=round(row["change_percent"], 2) if row.get("change_percent") is not None else None,
                our_tp=round(row["our_tp"], 2), internal_tp=round(row["internal_tp"], 2),
                public_consensus_tp=round(row["public_consensus_tp"], 2) if row.get("public_consensus_tp") else None,
                analyst_count=row.get("analyst_count"), consensus_weight_percent=row["consensus_weight_percent"],
                expected_return_percent=round(row["expected_total_return_percent"], 2), tp_upside_percent=round(row["upside_percent"], 2),
                buy_in=round(row["buy_in"], 2), price_vs_buy_in_percent=round(row["price_vs_buy_in_percent"], 2),
                risk_score=round(row["risk_score"], 2), power_score=round(row["score"], 2),
                valuation_confidence=round(row["valuation_confidence"], 2), method_dispersion_percent=round(row["method_dispersion_percent"], 2),
                data_source_count=row["data_source_count"], source_agreement_percent=round(row["source_agreement_percent"], 2),
                fundamentals_as_of=row.get("fundamentals_as_of"), ir_status=row.get("ir_status", "unavailable"),
                latest_ir_event_at=row.get("latest_ir_event_at"), latest_ir_event_type=row.get("latest_ir_event_type"),
                tp_validation_score=round(row["tp_validation_score"], 2), tp_validation_reasons=row["tp_validation_reasons"],
                consensus_gap_percent=round(row["consensus_gap_percent"], 2) if row.get("consensus_gap_percent") is not None else None,
                valuation_method_count=row["valuation_method_count"], internal_method_count=row["internal_method_count"],
                signal_quality=row["signal_quality"], beta=row.get("beta"),
                volatility_90d_percent=round(row["volatility_90d"] * 100, 2) if row.get("volatility_90d") is not None else None,
                quadrant=quadrant,
                x_percent=round(self._axis(row["risk_score"], risk_cutoff, risk_low, risk_high), 2),
                y_percent=round(self._axis(row["upside_percent"], tp_cutoff, return_low, return_high), 2),
                as_of=row["as_of"],
            ))
        validated = sum(item.signal_quality == "validated" for item in items)
        return MatrixPowerResponse(
            market=market, source="EODHD All-In-One", methodology_name=METHODOLOGY_NAME,
            methodology_version=METHODOLOGY_VERSION, universe_size=self._universe_size[market],
            source_eligible_count=len(rows), item_count=len(items), validated_count=validated,
            provisional_count=len(items) - validated, coverage_audit=self._coverage[market],
            tp_upside_cutoff_percent=tp_cutoff, risk_cutoff=risk_cutoff,
            quote_refresh_seconds=MATRIX_REFRESH_SECONDS, provider_delay_minutes=PROVIDER_DELAY_MINUTES,
            basis_generated_at=self._basis_at[market] or now, generated_at=now, items=items,
            methodology={
                "return": "Raw C3PO TP upside is the return axis and must exceed live Selic + 6 p.p. for the Power Zone.",
                "risk": "Market volatility, beta, drawdown, balance-sheet evidence and liquidity produce the shared 0-100 risk score.",
                "power": "Power Score combines 35% upside, 25% inverse risk, 15% quality, 15% confidence and 10% entry discipline.",
                "universe": f"{market} stocks and ETFs that clear price, size, liquidity and history gates.",
                "confidence": "Stocks require convergent five-method valuation and public consensus evidence. ETFs use dedicated fund, trend, volatility and drawdown evidence.",
                "refresh": "Prices refresh every 60 seconds from EODHD; valuation inputs refresh in the nightly canonical cycle.",
            },
        )

    def _candidate(self, row: dict[str, Any], rank: int) -> B3Candidate:
        return B3Candidate(
            rank=rank, symbol=row["symbol"], name=row["name"], security_type=row["security_type"], logo_url=EodhdClient.normalize_logo_url(row.get("logo_url")) or None,
            sector=row["sector"], industry=row.get("industry"), peer_group=row.get("peer_group"),
            sector_source=row.get("sector_source"), sector_confidence=row.get("sector_confidence"), valuation_profile=row["valuation_profile"],
            price=round(row["price"], 2), change_percent=row.get("change_percent"), volume=row.get("volume"),
            average_daily_value_90d=round(row["adtv_90d"], 2), market_cap=row.get("market_cap"),
            our_tp=round(row["our_tp"], 2), internal_tp=round(row["internal_tp"], 2), consensus_weight_percent=row["consensus_weight_percent"],
            upside_percent=round(row["upside_percent"], 2), expected_total_return_percent=round(row["expected_total_return_percent"], 2),
            buy_in=round(row["buy_in"], 2), price_vs_buy_in_percent=round(row["price_vs_buy_in_percent"], 2),
            buy_in_models={name: round(value, 2) for name, value in row["buy_in_models"].items()},
            public_consensus_tp=round(row["public_consensus_tp"], 2) if row.get("public_consensus_tp") else None,
            analyst_count=row.get("analyst_count"), pe=row.get("pe"), forward_pe=row.get("forward_pe"), ev_ebitda=row.get("ev_ebitda"),
            peg=row.get("peg"), price_to_book=row.get("price_to_book"), roe_percent=row.get("roe_percent"), fcf_yield_percent=row.get("fcf_yield_percent"),
            score=round(row["score"], 1), risk_score=round(row["risk_score"], 1), valuation_confidence=round(row["valuation_confidence"], 1),
            method_dispersion_percent=round(row["method_dispersion_percent"], 1), data_source_count=row["data_source_count"],
            source_agreement_percent=round(row["source_agreement_percent"], 1), fundamentals_as_of=row.get("fundamentals_as_of"),
            ir_status=row.get("ir_status", "unavailable"), latest_ir_event_at=row.get("latest_ir_event_at"), latest_ir_event_type=row.get("latest_ir_event_type"),
            tp_validation_score=round(row["tp_validation_score"], 1), tp_validation_reasons=row["tp_validation_reasons"],
            consensus_gap_percent=round(row["consensus_gap_percent"], 1) if row.get("consensus_gap_percent") is not None else None,
            valuation_method_count=row["valuation_method_count"], internal_method_count=row["internal_method_count"], quality_score=row["quality_score"],
            status=row["status"], thesis=row["thesis"], risk=row["risk"], as_of=row["as_of"],
        )

    def _persist(self, market: USMarket) -> None:
        methodology_id = self.database.ensure_methodology_version(
            METHODOLOGY_KEY, METHODOLOGY_VERSION,
            {"market": market, "stocks": STOCK_LIMIT, "etfs": ETF_LIMIT, "shared_policy": C3PO_VALUATION_POLICY.label},
            C3PO_VALUATION_POLICY.release_note,
        )
        rows = [{**row, "as_of": row["as_of"].isoformat() if isinstance(row.get("as_of"), datetime) else row.get("as_of")} for row in self._rows[market]]
        generated_at = self._basis_at[market] or datetime.now(timezone.utc)
        self.database.save_analysis_snapshot(
            "valuation_universe", f"{market}_UNIVERSE", methodology_id,
            {"methodology_version": METHODOLOGY_VERSION, "market": market, "coverage": self._coverage[market]},
            {"rows": rows, "universe_size": self._universe_size[market]}, generated_at,
        )
        self._persist_calibration(market, methodology_id, generated_at, rows)
        self.database.save_analysis_snapshot(
            "peer_medians", f"{market}_PEER_MEDIANS", methodology_id,
            {"methodology_version": METHODOLOGY_VERSION, "market": market},
            {"medians": self._peer_medians[market]}, generated_at,
        )
        response = self._candidate_response(market)
        self.database.save_analysis_snapshot(
            "candidate_screen", f"{market}_TOP_10", methodology_id,
            {"methodology_version": METHODOLOGY_VERSION, "market": market},
            response.model_dump(mode="json"), response.generated_at,
        )

    def _load_calibration_factors(self, market: USMarket) -> None:
        snapshot = self.database.latest_analysis_snapshot("valuation_calibration", f"{market}_POWER_MODEL")
        if not snapshot:
            self._calibration_factors[market] = {}
            return
        outputs = snapshot.get("outputs") if isinstance(snapshot.get("outputs"), dict) else {}
        raw_factors = outputs.get("factors") if isinstance(outputs, dict) else None
        if not isinstance(raw_factors, dict):
            self._calibration_factors[market] = {}
            return
        self._calibration_factors[market] = {
            str(profile): clamp(float(factor), 1 - CALIBRATION_FACTOR_LIMIT, 1 + CALIBRATION_FACTOR_LIMIT)
            for profile, factor in raw_factors.items()
            if isinstance(factor, (int, float))
        }

    def _persist_calibration(
        self, market: USMarket, methodology_id: str, generated_at: datetime, current_rows: list[dict[str, Any]],
    ) -> None:
        """Rolling backtest measuring forecast bias by valuation profile,
        mirroring b3_screener.py's _persist_calibration exactly (same
        horizon/sample-size/factor-limit constants) -- compares this
        symbol's TP-implied expected return from ~90 days ago against the
        price move that actually happened, and nudges internal_tp by up to
        +/-5% per profile once enough evidence exists."""
        prior = self.database.analysis_snapshot_at_or_before(
            "valuation_universe", f"{market}_UNIVERSE", generated_at - timedelta(days=CALIBRATION_HORIZON_DAYS),
        )
        factors = dict(self._calibration_factors.get(market, {}))
        metrics: dict[str, dict[str, Any]] = {}
        status = "warming_up"
        horizon_days = None
        if prior:
            prior_published_at = prior.get("published_at")
            if isinstance(prior_published_at, datetime):
                horizon_days = max(1, (generated_at - prior_published_at).days)
            prior_output = prior.get("outputs") if isinstance(prior.get("outputs"), dict) else {}
            prior_rows = prior_output.get("rows") if isinstance(prior_output, dict) else []
            previous = {
                str(row.get("symbol")): row
                for row in prior_rows or []
                if isinstance(row, dict) and row.get("symbol")
            }
            grouped: dict[str, list[tuple[float, float]]] = {"global": []}
            if horizon_days is not None:
                for row in current_rows:
                    symbol = str(row.get("symbol") or "")
                    old = previous.get(symbol)
                    old_price = positive((old or {}).get("price"))
                    current_price = positive(row.get("price"))
                    expected_annual = number((old or {}).get("expected_total_return_percent"))
                    if not old_price or not current_price or expected_annual is None:
                        continue
                    annual = clamp(expected_annual / 100, -0.90, 3.0)
                    expected_period = (1 + annual) ** (horizon_days / 365) - 1
                    realized = current_price / old_price - 1
                    if abs(realized) > 0.75:
                        continue
                    sample = (realized, expected_period)
                    grouped["global"].append(sample)
                    grouped.setdefault(str((old or {}).get("valuation_profile") or "general"), []).append(sample)

            global_factor = 1.0
            for profile, samples in grouped.items():
                required = CALIBRATION_MIN_GLOBAL_SAMPLES if profile == "global" else CALIBRATION_MIN_PROFILE_SAMPLES
                errors = [realized - expected for realized, expected in samples]
                absolute_errors = [abs(error) for error in errors]
                directional = [
                    (realized >= 0) == (expected >= 0)
                    for realized, expected in samples
                    if realized != 0 or expected != 0
                ]
                factor = 1.0
                if horizon_days is not None and len(samples) >= required and 60 <= horizon_days <= 150:
                    factor = clamp(
                        1 + statistics.median(errors) * 0.25,
                        1 - CALIBRATION_FACTOR_LIMIT, 1 + CALIBRATION_FACTOR_LIMIT,
                    )
                    if profile == "global":
                        global_factor = factor
                    else:
                        factor = factor * 0.70 + global_factor * 0.30
                    factors[profile] = factor
                    status = "active"
                metrics[profile] = {
                    "samples": len(samples),
                    "median_forecast_error_percent": round(statistics.median(errors) * 100, 2) if errors else None,
                    "mean_absolute_error_percent": round(statistics.mean(absolute_errors) * 100, 2) if absolute_errors else None,
                    "directional_accuracy_percent": round(statistics.mean(directional) * 100, 2) if directional else None,
                    "factor": round(factor, 5),
                }

        self.database.save_analysis_snapshot(
            "valuation_calibration", f"{market}_POWER_MODEL", methodology_id,
            {
                "horizon_days": CALIBRATION_HORIZON_DAYS,
                "minimum_global_samples": CALIBRATION_MIN_GLOBAL_SAMPLES,
                "minimum_profile_samples": CALIBRATION_MIN_PROFILE_SAMPLES,
                "factor_limit": CALIBRATION_FACTOR_LIMIT,
            },
            {"status": status, "observed_horizon_days": horizon_days, "factors": factors, "metrics": metrics},
            generated_at,
        )

    def _hydrate(self, market: USMarket) -> None:
        snapshot = self.database.latest_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE")
        if not snapshot:
            return
        inputs = snapshot.get("inputs") if isinstance(snapshot.get("inputs"), dict) else {}
        outputs = snapshot.get("outputs") if isinstance(snapshot.get("outputs"), dict) else {}
        if inputs.get("methodology_version") != METHODOLOGY_VERSION:
            return
        rows = outputs.get("rows") if isinstance(outputs.get("rows"), list) else []
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("as_of"), str):
                try:
                    row["as_of"] = datetime.fromisoformat(row["as_of"].replace("Z", "+00:00"))
                except ValueError:
                    row["as_of"] = snapshot["published_at"]
        self._rows[market] = [dict(row) for row in rows if isinstance(row, dict)]
        self._basis_at[market] = snapshot.get("published_at")
        self._universe_size[market] = int(outputs.get("universe_size") or STOCK_LIMIT + ETF_LIMIT)
        self._coverage[market] = {str(key): int(value) for key, value in inputs.get("coverage", {}).items()}

    def _refresh_quotes(self, market: USMarket, rows: list[dict[str, Any]], now: datetime) -> None:
        catalog = self.realtime._us_symbol_catalog(now)
        quote_map = {self.realtime._us_symbol(raw.get("code") or raw.get("Code")): raw for raw in self.realtime._us_bulk_quotes(now)}
        for row in rows:
            raw = quote_map.get(row["symbol"])
            metadata = catalog.get(row["symbol"])
            quote = self.realtime._us_row(raw, metadata, market, now) if raw and metadata else None
            if not quote:
                continue
            row["price"] = quote.price
            row["change_percent"] = quote.change_percent
            row["as_of"] = quote.as_of
            row["upside_percent"] = (row["our_tp"] / quote.price - 1) * 100
            row["expected_total_return_percent"] = row["upside_percent"]
            row["price_vs_buy_in_percent"] = (quote.price / row["buy_in"] - 1) * 100
            row["score"] = self._power_score(row["upside_percent"], row["risk_score"], row["operating_quality"], row["valuation_confidence"], row["price_vs_buy_in_percent"])

    @staticmethod
    def _is_etf(metadata: dict[str, Any]) -> bool:
        return canonical_us_security_type(
            metadata.get("Code") or metadata.get("code") or metadata.get("symbol"),
            metadata.get("Type") or metadata.get("type"),
        ) == "ETF"

    @staticmethod
    def _ir_freshness(fundamentals_as_of: Any, event: dict[str, Any] | None) -> dict[str, Any]:
        """Mirrors B3ScreeningService._ir_freshness so Dark Side/Ben Kenobi Records/Laser
        Pager get the same Tatooine Updates freshness signal for US names (SEC EDGAR +
        Finnhub) that B3 names already get from CVM/RI -- flags whether this valuation's
        fundamentals already reflect the latest official disclosure, or predate one."""
        if not event:
            return {
                "ir_status": "unavailable",
                "latest_ir_event_at": None,
                "latest_ir_event_type": None,
            }
        current = bool(event.get("reviewed_at") or event.get("valuation_status") == "incorporated")
        reference_date = event.get("reference_date")
        if (
            not current
            and event.get("event_type") == "Financial Results"
            and reference_date
            and fundamentals_as_of
        ):
            current = str(fundamentals_as_of)[:10] >= str(reference_date)[:10]
        return {
            "ir_status": "current" if current else "pending_review",
            "latest_ir_event_at": event.get("published_at"),
            "latest_ir_event_type": event.get("event_type"),
        }

    @staticmethod
    def _profile(fundamentals: dict[str, Any]) -> str:
        text = f"{fundamentals.get('sector', '')} {fundamentals.get('industry', '')}".lower()
        if any(value in text for value in ("bank", "financial", "insurance")):
            return "financial"
        if any(value in text for value in ("real estate", "reit", "property")):
            return "real_estate"
        if any(value in text for value in ("utility", "electric", "water")):
            return "utilities"
        if any(value in text for value in ("materials", "mining", "oil", "gas", "steel")):
            return "cyclical"
        if any(value in text for value in ("technology", "software", "semiconductor", "biotech")):
            return "growth"
        return "general"

    @staticmethod
    def _volatility(history: list[dict[str, Any]]) -> float | None:
        closes = [float(row["close"]) for row in history[-91:] if positive(row.get("close"))]
        returns = [closes[index] / closes[index - 1] - 1 for index in range(1, len(closes)) if closes[index - 1] > 0]
        return statistics.pstdev(returns) * math.sqrt(252) if len(returns) >= 20 else None

    @staticmethod
    def _power_score(upside: float, risk: float, quality: float, confidence: float, entry_distance: float) -> float:
        return clamp(
            clamp((upside + 10) / 90 * 100, 0, 100) * 0.35
            + (100 - risk) * 0.25
            + quality * 0.15
            + confidence * 0.15
            + clamp(100 - abs(entry_distance) * 5, 0, 100) * 0.10,
            0,
            100,
        )

    @staticmethod
    def _tp_cutoff() -> float:
        return (LATEST_COPOM_SELIC + TP_UPSIDE_PREMIUM) * 100

    @staticmethod
    def _risk_cutoff(rows: list[dict[str, Any]]) -> float:
        risks = [float(row["risk_score"]) for row in rows if positive(row.get("risk_score"))]
        return min(ABSOLUTE_LOW_RISK_LIMIT, statistics.median(risks) if risks else ABSOLUTE_LOW_RISK_LIMIT)

    @staticmethod
    def _quadrant(upside: float, risk: float, upside_cutoff: float, risk_cutoff: float) -> str:
        return (
            "high_return_low_risk" if upside >= upside_cutoff and risk < risk_cutoff
            else "high_return_high_risk" if upside >= upside_cutoff
            else "low_return_low_risk" if risk < risk_cutoff
            else "low_return_high_risk"
        )

    @staticmethod
    def _bounds(values: list[float], center: float) -> tuple[float, float]:
        if not values:
            return center - 20, center + 20
        ordered = sorted(values)
        low = ordered[max(0, int(len(ordered) * 0.05) - 1)]
        high = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        return min(low, center - 1), max(high, center + 1)

    @staticmethod
    def _axis(value: float, center: float, low: float, high: float) -> float:
        if value < center:
            return clamp(4 + (value - low) / max(center - low, 0.01) * 44, 4, 48)
        return clamp(52 + (value - center) / max(high - center, 0.01) * 44, 52, 96)
