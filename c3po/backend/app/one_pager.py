from __future__ import annotations

import math
import re
import statistics
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import Settings
from .database import Database
from .foreign_listings import normalize_foreign_fundamentals, policy_for
from .market_data.eodhd import EodhdClient
from .market_data.fmp import FmpClient
from .market_data.sector_taxonomy import canonical_b3_company_name
from .market_data.service import MarketDataService
from .one_pager_pdf import PremiumOnePagerRenderer
from .official_fundamentals import apply_official_fundamentals_map
from .schemas import OnePagerReport
from .valuation_policy import C3PO_VALUATION_POLICY, METHODOLOGY_KEY, METHODOLOGY_NAME, METHODOLOGY_VERSION

if TYPE_CHECKING:
    from .investor_relations import InvestorRelationsService
    from .market_data.b3_screener import B3ScreenerService
    from .market_data.us_screener import USScreeningService


class OnePagerGenerationError(RuntimeError):
    pass


# Bounded, evidence-scaled contributions from Tatooine Updates content (as opposed
# to the pre-existing pure freshness/staleness gate) -- see _insider_net_signal and
# _sentiment_confidence_adjustment. Kept small relative to the rest of each formula
# so a single filing or a thin news week can't dominate the score.
INSIDER_GOVERNANCE_LOOKBACK_DAYS = 180
INSIDER_SIGNAL_MIN_TRANSACTIONS_FOR_FULL_WEIGHT = 4
INSIDER_RISK_MAX_SWING = 8.0
SENTIMENT_CONFIDENCE_MAX_SWING = 5.0
SENTIMENT_MIN_ARTICLES_FOR_FULL_WEIGHT = 5

# Root-caused 2026-08-20 (TP methodology audit): the US DCF used one fixed
# 10.5% discount rate for every stock regardless of risk, unlike B3's
# per-security beta/Selic-derived WACC (b3_screener.py). This is a real
# CAPM-style discount rate instead: US 10-year Treasury yield (live, EODHD
# GBOND) as the risk-free rate, plus beta times a standard long-run US
# equity risk premium.
US_RISK_FREE_FALLBACK_RATE = 0.042
US_RISK_FREE_CACHE_HOURS = 6
US_EQUITY_RISK_PREMIUM = 0.055
US_DISCOUNT_RATE_MIN = 0.06
US_DISCOUNT_RATE_MAX = 0.16

# Root-caused 2026-08-20 (production incident): the 5 "methods" (Goldman
# Sachs/Morgan Stanley/etc -- fictional internal labels, not real data from
# those firms) each only bake real analyst consensus in at a modest,
# diluted 10-25% weight alongside fundamentals-derived components. When
# those fundamentals-derived components move together (as they did for
# JPM: consensus $374.57, our blended TP $625.49 -- 67% too high), nothing
# pulls the final number back toward the one real, externally-sourced
# anchor we have. B3 avoids this with an explicit, separate final blend
# against public_consensus_tp (b3_screener.py's _consensus_weight, 20-35%
# scaled by analyst coverage) -- applied once, after the internal model,
# not diluted inside it. Mirrored here as US_CONSENSUS_WEIGHT_MIN/MAX.
US_CONSENSUS_WEIGHT_MIN = 0.20
US_CONSENSUS_WEIGHT_MAX = 0.35
US_CONSENSUS_ANALYST_BREADTH_ANALYSTS = 10

# Root-caused 2026-08-20 (TP methodology audit): fair_pe/fair_ev_ebitda used a
# fixed constant per valuation profile with no peer comparison at all, unlike
# B3's live sector-median benchmarking (b3_screener.py's _sector_medians).
# These are now only the FALLBACK when a profile bucket in the current
# screening batch doesn't have enough peers (see _us_peer_medians) --
# US_PEER_MEDIAN_MIN_SAMPLE mirrors B3's own minimum-peer-count threshold.
US_PEER_MEDIAN_MIN_SAMPLE = 4
# Root-caused 2026-08-20: _valuation_profile's coarse keyword taxonomy let a
# genuinely heterogeneous bucket through once (banks pooled with high-multiple
# diversified financials under "financial"). Rather than trust the taxonomy
# alone, a peer sample is also rejected if it's statistically too spread out
# to be a coherent comparison group -- (Q3-Q1)/(Q3+Q1) above this threshold --
# regardless of which profile it's in. This is the general safety net; the
# taxonomy fix in _valuation_profile is the specific one.
US_PEER_MEDIAN_MAX_DISPERSION = 0.40
FAIR_PE_BASE_FALLBACK = {
    "financial": 9.0, "utilities": 12.0, "cyclical": 10.0, "real_estate": 11.0,
    "technology": 21.0, "quality": 18.0, "general": 15.0,
}
FAIR_EV_EBITDA_BASE_FALLBACK = {
    "financial": 8.0, "utilities": 9.0, "cyclical": 7.0, "real_estate": 10.0,
    "technology": 17.0, "quality": 13.0, "general": 10.0,
}


class OnePagerService:
    SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")

    def __init__(
        self,
        settings: Settings,
        database: Database,
        market_data: MarketDataService,
        *,
        b3_screener: B3ScreenerService | None = None,
        investor_relations: InvestorRelationsService | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.market_data = market_data
        self.b3_screener = b3_screener
        self.us_screener: USScreeningService | None = None
        self.investor_relations = investor_relations
        self.output_dir = output_dir or settings.one_pager_output_dir
        self._us_risk_free_cache: tuple[datetime, float] | None = None

    def set_us_screener(self, screener: USScreeningService) -> None:
        self.us_screener = screener

    def generate(self, requested_symbol: str) -> OnePagerReport:
        symbol, market = self._normalize_symbol(requested_symbol)
        provider = "brapi" if market == "B3" else "eodhd"
        if provider == "brapi" and not self.settings.brapi_token:
            raise OnePagerGenerationError("A credencial da Brapi não está configurada.")
        if not self.settings.eodhd_api_token:
            raise OnePagerGenerationError("A credencial da EODHD não está configurada.")

        run_id = self.database.begin_ingestion_run(
            "one-pager",
            "C3PO One Pager",
            "equity_research",
            {"symbol": symbol, "market": market},
        )
        try:
            quote = self._fetch_quote(symbol, market)
            eodhd = EodhdClient(
                self.settings.eodhd_base_url,
                self.settings.eodhd_api_token,
                self.market_data.http,
            )
            exchange = "SA" if market == "B3" else "US"
            fundamentals = eodhd.fundamentals([symbol], exchange=exchange).get(symbol, {})
            if not fundamentals:
                raise OnePagerGenerationError(f"A EODHD não retornou fundamentos para {symbol}.")
            listing_policy = policy_for(symbol)
            if listing_policy:
                try:
                    fx_quote = eodhd.quotes([listing_policy.fx_symbol])[0]
                    fundamentals = normalize_foreign_fundamentals(
                        fundamentals,
                        policy=listing_policy,
                        fx_rate=fx_quote.price,
                        quote_price=quote.price,
                    )
                except Exception as exc:
                    raise OnePagerGenerationError(
                        f"Não gerei o One Pager de {symbol}: a conversão canônica de "
                        f"{listing_policy.primary_ticker} não pôde ser validada ({exc})."
                    ) from exc
            ri_context = self._refresh_official_sources(symbol, market, fundamentals)
            fundamentals = apply_official_fundamentals_map(
                self.database,
                {symbol: fundamentals},
                market=market,
            )[symbol]
            fundamentals_period = self._latest_fundamental_period(fundamentals)
            self.database.reconcile_ir_results({symbol: fundamentals_period}, market)
            official_disclosure = self._official_disclosure_context(symbol, market, fundamentals_period)
            history = eodhd.history(symbol, exchange=exchange, days=365)
            insider_since = datetime.now(timezone.utc) - timedelta(days=INSIDER_GOVERNANCE_LOOKBACK_DAYS)
            insider_activity = self.database.insider_transaction_activity([symbol], market, insider_since).get(symbol)
            news_sentiment = (
                self.database.latest_news_sentiment([symbol], market).get(symbol) if market != "B3" else None
            )
            risk_free_rate = self._us_risk_free_rate() if market != "B3" else None
            peer_medians = (
                self.us_screener.peer_medians() if market != "B3" and self.us_screener else None
            )
            fmp_consensus, fmp_summary = self._fmp_consensus_data(symbol) if market != "B3" else (None, None)
            shared_valuation = (
                self.b3_screener.valuation_for(symbol, build_if_missing=True)
                if market == "B3" and self.b3_screener
                else self.us_screener.valuation_for(symbol)
                if market == "US" and self.us_screener
                else None
            )
            if market == "B3" and shared_valuation is None:
                raise OnePagerGenerationError(
                    f"Não gerei o One Pager de {symbol}: os dados disponíveis ainda não sustentam pelo menos "
                    f"três métodos internos utilizáveis no valuation canônico v{METHODOLOGY_VERSION}. "
                    "Os cortes de Candidate Stocks e Jedi Force não bloqueiam a geração do documento."
                )
            analysis = self._analyze(
                symbol,
                market,
                quote.model_dump(),
                fundamentals,
                history,
                shared_valuation=shared_valuation,
                insider_activity=insider_activity,
                news_sentiment=news_sentiment,
                risk_free_rate=risk_free_rate,
                peer_medians=peer_medians,
                fmp_consensus=fmp_consensus,
                fmp_summary=fmp_summary,
            )
            verification_label = (
                "RI da companhia + regulador verificados"
                if ri_context.get("verification_status") == "issuer_and_regulator"
                else "CVM/SEC oficial verificado"
            )
            analysis["source"] = f"{analysis['source']} + {verification_label}"
            consensus_origin = (
                str(shared_valuation.get("consensus_origin_symbol") or "")
                if market == "B3" and shared_valuation else ""
            )
            if consensus_origin and consensus_origin != symbol:
                analysis["source"] = f"{analysis['source']} + consenso normalizado de {consensus_origin}"
            if (
                market == "B3"
                and shared_valuation
                and shared_valuation.get("fundamental_quality_status") == "review_required"
            ):
                analysis["source"] = f"{analysis['source']} + valuation canônico sob demanda com ressalvas"
            if official_disclosure["status"] == "pending_review":
                disclosure_label = "CVM First" if market == "B3" else "RI/SEC"
                analysis["source"] = (
                    f"{analysis['source']} + {disclosure_label} pendente: {official_disclosure['title']}"
                )
            analysis["official_disclosure"] = official_disclosure
            analysis["ri_url"] = ri_context["ri_url"]
            analysis["ri_checked_at"] = ri_context["checked_at"]
            report = self._write_report(analysis, history)
            self._persist_us_valuation_snapshot(analysis, report)
            self.database.finish_ingestion_run(run_id, "succeeded", 2, 1)
            return report
        except OnePagerGenerationError:
            self.database.finish_ingestion_run(run_id, "failed", 1, 0, "One Pager generation failed")
            raise
        except Exception as exc:
            self.database.finish_ingestion_run(run_id, "failed", 1, 0, str(exc)[:500])
            raise OnePagerGenerationError(f"Não foi possível gerar o One Pager de {symbol}: {exc}") from exc

    def _fetch_quote(self, symbol: str, market: str):
        attempts: list[tuple[str, list[str]]] = (
            [("brapi", [symbol]), ("eodhd", [f"{symbol}.SA"])]
            if market == "B3"
            else [("eodhd", [symbol])]
        )
        for provider, symbols in attempts:
            try:
                quotes = self.market_data.fetch_quotes(provider, symbols, persist=True)  # type: ignore[arg-type]
            except Exception:
                continue
            if quotes:
                return quotes[0]
        sources = "Brapi e na EODHD" if market == "B3" else "EODHD"
        raise OnePagerGenerationError(
            f"Não encontrei uma cotação válida para {symbol} na {sources}. Tente novamente em alguns minutos."
        )

    def _refresh_official_sources(
        self,
        symbol: str,
        market: str,
        fundamentals: dict[str, Any],
    ) -> dict[str, Any]:
        if self.investor_relations is None:
            raise OnePagerGenerationError("A verificação obrigatória do RI oficial não está configurada.")
        try:
            return self.investor_relations.refresh_company(
                symbol,
                market,
                company_name=str(fundamentals.get("companyName") or symbol),
            )
        except Exception as exc:
            raise OnePagerGenerationError(
                f"Não gerei o One Pager de {symbol}: não foi possível validar o RI oficial ({exc})."
            ) from exc

    def _official_disclosure_context(
        self,
        symbol: str,
        market: str,
        fundamentals_period: str | None,
    ) -> dict[str, Any]:
        latest = self.database.latest_valuation_ir_events([symbol], market).get(symbol)
        if not latest:
            return {"status": "unavailable", "title": None, "reference_date": None, "fundamentals_period": fundamentals_period}
        reference_date = str(latest.get("reference_date") or "")[:10] or None
        status = str(latest.get("valuation_status") or "informational")
        if (
            status == "pending_review"
            and latest.get("event_type") == "Financial Results"
            and reference_date
            and fundamentals_period
            and fundamentals_period >= reference_date
        ):
            status = "incorporated"
        return {
            "status": status,
            "title": latest.get("title") or latest.get("event_type"),
            "reference_date": reference_date,
            "fundamentals_period": fundamentals_period,
            "materiality": latest.get("materiality"),
            "document_url": latest.get("document_url") or latest.get("official_url"),
        }

    @classmethod
    def _latest_fundamental_period(cls, fundamentals: dict[str, Any]) -> str | None:
        values: list[date] = []
        for field in ("quarterlyIncome", "quarterlyCashFlow", "quarterlyBalance", "earningsHistory"):
            for row in cls._rows(fundamentals.get(field)):
                raw = str(row.get("date") or row.get("filing_date") or "")[:10]
                try:
                    values.append(date.fromisoformat(raw))
                except ValueError:
                    continue
        return max(values).isoformat() if values else None

    def list_reports(self, limit: int = 12) -> list[OnePagerReport]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        items: list[OnePagerReport] = []
        metadata_files = sorted(
            self.output_dir.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for path in metadata_files[:limit]:
            try:
                items.append(OnePagerReport.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return items

    def report_path(self, filename: str) -> Path | None:
        if Path(filename).name != filename or not filename.endswith(".pdf"):
            return None
        path = self.output_dir / filename
        return path if path.is_file() else None

    def _normalize_symbol(self, value: str) -> tuple[str, str]:
        clean = value.strip().upper().replace(" ", "")
        if clean.endswith(".SA"):
            clean = clean[:-3]
            market = "B3"
        elif clean.endswith(".US"):
            clean = clean[:-3]
            market = "US"
        else:
            market = "B3" if re.search(r"(?:3|4|5|6|11)$", clean) else "US"
        if not self.SYMBOL_PATTERN.fullmatch(clean):
            raise OnePagerGenerationError("Ticker inválido. Use, por exemplo, PRNR3, AMZN ou MSFT.")
        return clean, market

    def _analyze(
        self,
        symbol: str,
        market: str,
        quote: dict[str, Any],
        fundamentals: dict[str, Any],
        history: list[dict[str, Any]] | None = None,
        *,
        shared_valuation: dict[str, Any] | None = None,
        insider_activity: dict[str, Any] | None = None,
        news_sentiment: dict[str, Any] | None = None,
        risk_free_rate: float | None = None,
        peer_medians: dict[str, dict[str, float]] | None = None,
        fmp_consensus: dict[str, float] | None = None,
        fmp_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        price = self._positive(quote.get("price"))
        if price is None:
            raise OnePagerGenerationError(f"A cotação de {symbol} não contém um preço válido.")
        currency = str(quote.get("currency") or ("BRL" if market == "B3" else "USD"))
        company_name = str(fundamentals.get("companyName") or symbol)
        sector = str(fundamentals.get("sector") or fundamentals.get("industry") or "Setor não informado")
        industry = str(fundamentals.get("industry") or sector)
        if market == "B3" and shared_valuation:
            company_name = canonical_b3_company_name(
                symbol,
                shared_valuation.get("name") or company_name,
            )
            sector = str(shared_valuation.get("sector") or sector)
            industry = str(shared_valuation.get("subsector") or shared_valuation.get("peer_group") or industry)

        earnings_growth = self._ratio(fundamentals.get("earningsGrowthAnnual"))
        revenue_growth = self._ratio(fundamentals.get("revenueGrowthAnnual"))
        margin = self._ratio(fundamentals.get("profitMargins"))
        operating_margin = self._ratio(fundamentals.get("operatingMargins"))
        roe = self._ratio(fundamentals.get("returnOnEquity"))
        beta = self._positive(fundamentals.get("beta"))
        analyst_ratings = fundamentals.get("analystRatings") if isinstance(fundamentals.get("analystRatings"), dict) else {}
        eodhd_consensus = self._bounded_tp(
            fundamentals.get("targetMeanPrice") or analyst_ratings.get("targetPrice"),
            price,
        )
        analyst_buy = sum(int(analyst_ratings.get(key) or 0) for key in ("strongBuy", "buy"))
        analyst_hold = int(analyst_ratings.get("hold") or 0)
        analyst_sell = sum(int(analyst_ratings.get(key) or 0) for key in ("sell", "strongSell"))
        rating_count = analyst_buy + analyst_hold + analyst_sell
        eodhd_analyst_count = max(int(fundamentals.get("numberOfAnalystOpinions") or 0), rating_count) or None
        raw_consensus, analyst_count, consensus_source = self._resolve_us_consensus(
            fmp_consensus, fmp_summary, eodhd_consensus, eodhd_analyst_count,
        )
        consensus = self._bounded_tp(raw_consensus, price)

        forward_eps = self._positive(fundamentals.get("forwardEps"))
        trailing_eps = self._positive(fundamentals.get("trailingEps"))
        book_value = self._positive(fundamentals.get("bookValue"))
        shares = self._positive(fundamentals.get("sharesOutstanding"))
        ebitda = self._positive(fundamentals.get("ebitda"))
        total_debt = self._positive(fundamentals.get("totalDebt")) or 0.0
        total_cash = self._positive(fundamentals.get("totalCash")) or 0.0
        quarterly_income = self._rows(fundamentals.get("quarterlyIncome"))
        quarterly_cash = self._rows(fundamentals.get("quarterlyCashFlow"))
        quarterly_balance = self._rows(fundamentals.get("quarterlyBalance"))
        earnings_history = self._rows(fundamentals.get("earningsHistory"))
        earnings_trend = self._rows(fundamentals.get("earningsTrendQuarterly"))

        ttm_fcf = self._sum_rows(quarterly_cash, "freeCashFlow", 4)
        ttm_ebitda = self._sum_rows(quarterly_income, "ebitda", 4) or ebitda
        free_cashflow = ttm_fcf if ttm_fcf is not None else self._number(fundamentals.get("freeCashflow"))
        if quarterly_balance:
            latest_balance = quarterly_balance[0]
            total_cash = self._number(latest_balance.get("cashAndShortTermInvestments")) or self._number(latest_balance.get("cash")) or total_cash
            total_debt = (
                self._number(latest_balance.get("shortLongTermDebtTotal"))
                or self._number(latest_balance.get("netDebt"))
                or total_debt
            )

        profile = self._valuation_profile(sector, industry)
        growth = self._clamp(statistics.mean([revenue_growth or 0.0, earnings_growth or 0.0]), -0.08, 0.22)
        peer = (peer_medians or {}).get(profile, {})
        fair_pe_base = peer.get("pe") or FAIR_PE_BASE_FALLBACK[profile]
        fair_pe = self._clamp(
            fair_pe_base + max(growth, -0.05) * 35 + max((roe or 0) - 0.12, -0.08) * 16,
            6.0,
            34.0,
        )
        normalized_eps = forward_eps or trailing_eps
        earnings_tp = self._bounded_tp((normalized_eps or 0) * fair_pe, price)

        fair_ev_base = peer.get("ev_ebitda") or FAIR_EV_EBITDA_BASE_FALLBACK[profile]
        fair_ev_ebitda = self._clamp(fair_ev_base + max(growth, -0.05) * 20 + (operating_margin or margin or 0) * 8, 4.5, 24.0)
        # Root-caused 2026-08-20 (production incident): for JPM, enterprise_tp
        # came out to $1,096.77 -- 3x price -- because EV/EBITDA-minus-net-debt
        # is not a valid framework for banks. A bank's "total debt" is
        # dominated by customer deposits and borrowings ($1.24T for JPM),
        # which are the raw material of the banking business, not financial
        # leverage the way it is for a non-financial company -- no real
        # equity analyst uses EV/EBITDA to value a bank. Same reasoning for
        # dcf_tp ($578, still elevated after the fix above): a bank's
        # reported "free cash flow" is dominated by financing/investing
        # activity (loan originations, deposit changes), not owner earnings
        # -- banks are valued on P/E and P/B (or DDM), not FCF-DCF. Both are
        # skipped for the financial profile; _weighted_value already treats
        # None as "not usable" and re-normalizes over what's left.
        enterprise_tp = None
        if profile != "financial" and ttm_ebitda and shares:
            enterprise_tp = self._bounded_tp((ttm_ebitda * fair_ev_ebitda - total_debt + total_cash) / shares, price)

        fair_pb = self._clamp(0.8 + max((roe or 0) - 0.08, 0) * 10 + max(growth, 0) * 2, 0.7, 6.0)
        book_tp = self._bounded_tp((book_value or 0) * fair_pb, price)
        dcf_tp = None
        if profile != "financial":
            dcf_tp = self._dcf_value(
                free_cashflow=free_cashflow,
                shares=shares,
                growth=growth,
                market=market,
                price=price,
                fallback_eps=normalized_eps,
                beta=beta,
                risk_free_rate=risk_free_rate,
            )

        fundamental_anchor = self._weighted_value(
            ((earnings_tp, 0.40), (enterprise_tp, 0.30), (dcf_tp, 0.20), (book_tp, 0.10)),
            consensus or price,
        )
        consensus_anchor = consensus or fundamental_anchor
        surprise = self._ratio((earnings_history[0] if earnings_history else {}).get("surprisePercent")) or 0.0
        next_trend = self._forward_trend(earnings_trend)
        eps_revision = self._eps_revision(next_trend)
        debt_to_ebitda = total_debt / ttm_ebitda if ttm_ebitda and total_debt >= 0 else None

        risk_score = 32.0
        if beta is not None:
            risk_score += self._clamp((beta - 0.85) * 24, -8, 25)
        if debt_to_ebitda is not None:
            risk_score += self._clamp((debt_to_ebitda - 1.5) * 7, -8, 24)
        if earnings_growth is not None and earnings_growth < 0:
            risk_score += min(16, abs(earnings_growth) * 38)
        if free_cashflow is not None and free_cashflow < 0:
            risk_score += 9
        insider_signal = self._insider_net_signal(insider_activity)
        risk_score -= insider_signal * INSIDER_RISK_MAX_SWING
        risk_score = self._clamp(risk_score, 15, 90)
        risk_adjustment = self._clamp((risk_score - 40) / 500, -0.04, 0.10)
        quality_adjustment = self._clamp((roe or 0.12) * 0.20 + (margin or 0.08) * 0.15 + max(growth, -0.05) * 0.20, -0.04, 0.12)

        raw_methods = OrderedDict(
            (
                (
                    "Goldman Sachs",
                    self._weighted_value(
                        ((earnings_tp, 0.42), (enterprise_tp, 0.33), (book_tp, 0.10), (consensus_anchor, 0.15)),
                        fundamental_anchor,
                    ),
                ),
                (
                    "Morgan Stanley",
                    self._weighted_value(((dcf_tp, 0.72), (earnings_tp, 0.18), (consensus_anchor, 0.10)), fundamental_anchor),
                ),
                (
                    "Bridgewater",
                    self._weighted_value(
                        ((dcf_tp, 0.28), (enterprise_tp, 0.22), (earnings_tp, 0.20), (book_tp, 0.10), (consensus_anchor, 0.20)),
                        fundamental_anchor,
                    )
                    * (1 - risk_adjustment),
                ),
                (
                    "JPMorgan",
                    self._weighted_value(((earnings_tp, 0.65), (enterprise_tp, 0.15), (consensus_anchor, 0.20)), fundamental_anchor)
                    * self._clamp(1 + surprise * 0.12 + eps_revision * 0.20, 0.90, 1.12),
                ),
                (
                    "BlackRock",
                    self._weighted_value(((dcf_tp, 0.30), (earnings_tp, 0.25), (enterprise_tp, 0.20), (consensus_anchor, 0.25)), fundamental_anchor)
                    * self._clamp(1 + quality_adjustment - risk_adjustment * 0.45, 0.90, 1.14),
                ),
            )
        )
        method_median = statistics.median(raw_methods.values())
        methods = OrderedDict(
            (name, self._clamp(value, max(price * 0.40, method_median * 0.68), min(price * 2.75, method_median * 1.45)))
            for name, value in raw_methods.items()
        )
        internal_tp = statistics.mean(methods.values())
        consensus_weight = self._us_consensus_weight(consensus, analyst_count)
        c3po_tp = (
            internal_tp * (1 - consensus_weight) + consensus * consensus_weight
            if consensus_weight
            else internal_tp
        )
        foreign_policy = fundamentals.get("foreignListingPolicy")
        foreign_buy_in_override = None
        if isinstance(foreign_policy, dict):
            foreign_methods = foreign_policy.get("methodTargets")
            foreign_buy_in = self._positive(foreign_policy.get("buyIn"))
            if isinstance(foreign_methods, dict) and len(foreign_methods) == 5 and foreign_buy_in:
                methods = OrderedDict(
                    (str(name), float(value))
                    for name, value in foreign_methods.items()
                    if self._positive(value)
                )
                if len(methods) != 5:
                    raise OnePagerGenerationError(
                        f"{symbol}: a ponte de valuation da listagem primária está incompleta."
                    )
                c3po_tp = statistics.mean(methods.values())
                foreign_buy_in_override = foreign_buy_in
        method_values = list(methods.values())
        dispersion = self._dispersion(method_values)
        completeness_fields = (
            consensus,
            normalized_eps,
            book_value,
            shares,
            ttm_ebitda,
            free_cashflow,
            roe,
            margin,
            revenue_growth,
            beta,
        )
        completeness = sum(value is not None for value in completeness_fields) / len(completeness_fields)
        sentiment_adjustment = self._sentiment_confidence_adjustment(news_sentiment)
        confidence = self._clamp(
            45 + completeness * 28 + min(analyst_count or 0, 30) * 0.35 - dispersion * 0.35 + sentiment_adjustment,
            45, 94,
        )
        required_return = 0.12 if market == "US" else 0.20
        entry_discount = required_return + risk_score / 100 * 0.11 + (100 - confidence) / 100 * 0.06
        if foreign_buy_in_override is None:
            buy_in = statistics.mean(value / (1 + entry_discount) for value in methods.values())
            buy_in = min(buy_in, c3po_tp * 0.90)
        else:
            buy_in = foreign_buy_in_override
        if shared_valuation:
            shared_tp = self._positive(shared_valuation.get("our_tp"))
            shared_buy_in = self._positive(shared_valuation.get("buy_in"))
            if shared_tp and shared_buy_in:
                c3po_tp = shared_tp
                buy_in = shared_buy_in
                methods = self._shared_framework_methods(shared_valuation, shared_tp)
                method_values = list(methods.values())
                consensus = self._bounded_tp(shared_valuation.get("public_consensus_tp"), price) or consensus
                analyst_count = int(shared_valuation.get("analyst_count") or analyst_count or 0) or None
                risk_score = self._clamp(float(shared_valuation.get("risk_score") or risk_score), 0, 100)
                confidence = self._clamp(float(shared_valuation.get("valuation_confidence") or confidence), 0, 100)
                dispersion = max(0.0, float(shared_valuation.get("method_dispersion_percent") or self._dispersion(method_values)))
        upside = (c3po_tp / price - 1) * 100
        consensus_upside = (consensus / price - 1) * 100 if consensus else None
        rating = "COMPRA" if upside >= 25 else "ACUMULAR" if upside >= 10 else "NEUTRO" if upside >= -10 else "REDUZIR"

        latest_income, prior_income = self._latest_and_year_ago(quarterly_income)
        latest_cash, prior_cash = self._latest_and_year_ago(quarterly_cash)
        latest_earnings, prior_earnings = self._latest_and_year_ago(earnings_history)
        latest_period = self._quarter_label((latest_income or latest_earnings).get("date") if (latest_income or latest_earnings) else None)
        comparison_period = self._quarter_label((prior_income or prior_earnings).get("date") if (prior_income or prior_earnings) else None)
        if comparison_period == "N/D" and latest_period != "N/D":
            comparison_period = f"{latest_period[:-2]}{int(latest_period[-2:]) - 1:02d}"

        revenue_now = self._number(latest_income.get("totalRevenue"))
        revenue_prior = self._number(prior_income.get("totalRevenue"))
        op_now = self._number(latest_income.get("operatingIncome"))
        op_prior = self._number(prior_income.get("operatingIncome"))
        margin_now = op_now / revenue_now if op_now is not None and revenue_now else operating_margin
        margin_prior = op_prior / revenue_prior if op_prior is not None and revenue_prior else None
        net_now = self._number(latest_income.get("netIncome"))
        net_prior = self._number(prior_income.get("netIncome"))
        fcf_now = self._number(latest_cash.get("freeCashFlow"))
        fcf_prior = self._number(prior_cash.get("freeCashFlow"))
        eps_now = self._number(latest_earnings.get("epsActual")) or trailing_eps
        eps_prior = self._number(prior_earnings.get("epsActual"))
        eps_estimate = self._number(latest_earnings.get("epsEstimate"))
        eps_surprise = self._number(latest_earnings.get("surprisePercent"))
        financial_rows = [
            self._financial_row("Receita", revenue_now, revenue_prior, currency),
            self._financial_row("Lucro operacional", op_now, op_prior, currency),
            self._margin_row("Margem operacional", margin_now, margin_prior),
            self._financial_row("Lucro líquido", net_now, net_prior, currency),
            self._financial_row("Fluxo de caixa livre", fcf_now, fcf_prior, currency),
            (
                "EPS diluído",
                self._plain_number(eps_now),
                self._plain_number(eps_prior),
                self._percent(eps_surprise / 100 if eps_surprise is not None else None, signed=True),
            ),
        ]

        revenue_delta = self._change(revenue_now, revenue_prior)
        op_delta = self._change(op_now, op_prior)
        fcf_delta = self._change(fcf_now, fcf_prior)
        next_revenue = self._number(next_trend.get("revenueEstimateAvg"))
        next_revenue_growth = self._ratio(next_trend.get("revenueEstimateGrowth"))
        next_eps = self._number(next_trend.get("earningsEstimateAvg"))
        business_summary = self._business_summary(company_name, sector, industry)
        analyst_mix = self._analyst_mix(analyst_ratings)
        public_coverage = fundamentals.get("publicCoverage") if isinstance(fundamentals.get("publicCoverage"), list) else []
        coverage_summary = self._public_coverage_summary(public_coverage, currency)
        cash_display = self._compact_money(total_cash, currency)
        debt_display = self._compact_money(total_debt, currency)
        other_income = self._number(latest_income.get("totalOtherIncomeExpenseNet"))
        capex = self._number(latest_cash.get("capitalExpenditures"))
        unusual_income = (
            other_income is not None
            and op_now not in (None, 0)
            and abs(other_income) >= abs(op_now) * 0.25
        )

        quarter_read = [
            self._shorten(
                f"A receita foi de {self._compact_money(revenue_now, currency)}, {self._percent(revenue_delta, signed=True)} em 12 meses; o lucro operacional variou {self._percent(op_delta, signed=True)}.",
                165,
            ),
            self._shorten(
                f"A margem operacional ficou em {self._percent(margin_now)} e o lucro líquido em {self._compact_money(net_now, currency)}; o EPS de {self._plain_number(eps_now)} teve surpresa de {self._percent(eps_surprise / 100 if eps_surprise is not None else None, signed=True)}.",
                180,
            ),
            self._shorten(
                f"Receita e lucro apresentam crescimento anual de {self._percent(revenue_growth, signed=True)} e {self._percent(earnings_growth, signed=True)}; o próximo trimestre projeta receita de {self._compact_money(next_revenue, currency)}.",
                175,
            ),
        ]
        cash_quality = [
            self._shorten(
                f"O FCF trimestral foi de {self._compact_money(fcf_now, currency)} ({self._percent(fcf_delta, signed=True)} YoY), com caixa operacional de {self._compact_money(self._number(latest_cash.get('totalCashFromOperatingActivities')), currency)} e capex de {self._compact_money(abs(capex) if capex is not None else None, currency)}.",
                175,
            ),
            self._shorten(
                f"Caixa e aplicações somam {cash_display}, contra dívida de {debt_display}{f' e dívida/EBITDA de {debt_to_ebitda:.1f}x' if debt_to_ebitda is not None else ''}.",
                165,
            ),
            self._shorten(
                f"O lucro líquido inclui {self._compact_money(other_income, currency)} de resultado não operacional; a recorrência deve ser separada da expansão do negócio."
                if unusual_income
                else f"Margem líquida de {self._percent(margin)}, ROE de {self._percent(roe)} e conversão de caixa determinam a qualidade e a sustentabilidade do crescimento.",
                165,
            ),
        ]
        thesis = [
            business_summary,
            self._shorten(
                f"A combinação de crescimento de receita ({self._percent(revenue_growth, signed=True)}), margem operacional ({self._percent(operating_margin)}) e ROE ({self._percent(roe)}) sustenta a leitura fundamental.",
                178,
            ),
            self._shorten(
                coverage_summary
                or f"As cinco metodologias convergem em {self._money(c3po_tp, currency)}, com dispersão de {dispersion:.1f}%; o consenso de {self._money(consensus, currency)} funciona como validação externa, não como único motor.",
                182,
            ),
            self._shorten(
                f"A cobertura pública registra {analyst_mix}; o buy-in de {self._money(buy_in, currency)} exige retorno mínimo e margem de segurança compatíveis com risco {risk_score:.0f}/100.",
                180,
            ),
        ]
        risks = [
            self._shorten(
                f"Risco quantitativo de {risk_score:.0f}/100 e beta de {beta:.2f}" if beta is not None else f"Risco quantitativo de {risk_score:.0f}/100; o provedor não informou beta confiável.",
                150,
            ),
            self._shorten(
                f"Alavancagem{f' de {debt_to_ebitda:.1f}x dívida/EBITDA' if debt_to_ebitda is not None else ' sem cobertura completa'} e FCF de {self._compact_money(fcf_now, currency)} precisam ser acompanhados a cada resultado.",
                170,
            ),
            self._shorten(
                f"Para o próximo trimestre, o mercado estima EPS de {self._plain_number(next_eps)} e crescimento de receita de {self._percent(next_revenue_growth, signed=True)}; revisões negativas alteram rapidamente o cenário-base.",
                180,
            ),
            self._shorten(
                "O preço-alvo deve ser revisto após novo guidance, mudança material no consenso, alteração de custo de capital ou deterioração operacional; não é uma promessa de retorno.",
                175,
            ),
        ]

        bear = max(min(method_values) * (1 - self._clamp(risk_score / 350, 0.06, 0.22)), price * 0.35)
        bull = max(method_values) * (1 + self._clamp(max(growth, 0) * 0.40 + 0.05, 0.06, 0.18))
        headline = self._shorten(
            f"{latest_period}: receita {self._percent(revenue_delta, signed=True)}; margem operacional {self._percent(margin_now)}; C3PO TP aponta {upside:+.0f}% de upside",
            112,
        )
        return {
            "symbol": symbol,
            "company_name": company_name,
            "market": market,
            "sector": sector,
            "currency": currency,
            "price": price,
            "price_date": self._date_display(quote.get("as_of")),
            "change_percent": quote.get("change_percent"),
            "headline": headline,
            "results_title": f"{latest_period} - resultado operacional" if latest_period != "N/D" else "Resultado operacional mais recente",
            "latest_period": latest_period,
            "comparison_period": comparison_period,
            "financial_rows": financial_rows,
            "c3po_tp": c3po_tp,
            "profile": profile,
            "consensus_tp": consensus,
            "consensus_source": consensus_source,
            "consensus_upside": consensus_upside,
            "analyst_count": analyst_count,
            "analyst_buy": analyst_buy if rating_count else None,
            "analyst_hold": analyst_hold if rating_count else None,
            "analyst_sell": analyst_sell if rating_count else None,
            "buy_in": buy_in,
            "upside_percent": upside,
            "rating": rating,
            "confidence": confidence,
            "risk_score": risk_score,
            "dispersion": dispersion,
            "methods": methods,
            "multiples": OrderedDict(
                (
                    ("P/E REPORTADO", self._positive(fundamentals.get("trailingPE"))),
                    ("FWRD P/E", self._positive(fundamentals.get("forwardPE"))),
                    ("EV/EBITDA", self._positive(fundamentals.get("enterpriseToEbitda"))),
                    ("PEG RATIO", self._positive(fundamentals.get("pegRatio"))),
                )
            ),
            "quarter_read": quarter_read,
            "cash_quality": cash_quality,
            "thesis": thesis,
            "risks": risks,
            "scenarios": (("BEAR", bear), ("BASE", c3po_tp), ("BULL", bull)),
            "as_of": quote.get("as_of"),
            "source": (
                f"Brapi Pro + EODHD All-In-One | {C3PO_VALUATION_POLICY.label}"
                if shared_valuation
                else f"Brapi + EODHD | {C3PO_VALUATION_POLICY.label}"
                if market == "B3"
                else f"EODHD | {C3PO_VALUATION_POLICY.label}"
            ) + (f" + listagem primária {fundamentals.get('primaryTicker')} normalizada" if fundamentals.get("primaryTicker") else ""),
            "methodology_name": METHODOLOGY_NAME,
            "methodology_version": METHODOLOGY_VERSION,
        }

    def _write_report(self, data: dict[str, Any], history: list[dict[str, Any]]) -> OnePagerReport:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        generated_at = datetime.now().astimezone()
        stamp = generated_at.strftime("%Y%m%d-%H%M%S")
        filename = f"{data['symbol'].lower()}-one-pager-{stamp}.pdf"
        path = self.output_dir / filename
        self._render_pdf(path, data, history, generated_at)
        report = OnePagerReport(
            symbol=data["symbol"],
            company_name=data["company_name"],
            market=data["market"],
            currency=data["currency"],
            filename=filename,
            generated_at=generated_at,
            source=data["source"],
            methodology_name=data["methodology_name"],
            methodology_version=data["methodology_version"],
            price=round(data["price"], 2),
            c3po_tp=round(data["c3po_tp"], 2),
            consensus_tp=round(data["consensus_tp"], 2) if data["consensus_tp"] else None,
            buy_in=round(data["buy_in"], 2),
            upside_percent=round(data["upside_percent"], 1),
            confidence=round(data["confidence"]),
            method_count=len(data["methods"]),
            download_url=f"/api/v1/one-pagers/{filename}",
        )
        metadata_path = path.with_suffix(".json")
        metadata_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return report

    @classmethod
    def _public_coverage_summary(cls, rows: list[dict[str, Any]], currency: str) -> str:
        calls = []
        for row in rows[:3]:
            firm = str(row.get("firm") or "").strip()
            target = cls._positive(row.get("target"))
            published = str(row.get("publishedOn") or "")[:10]
            if not firm or target is None:
                continue
            calls.append(f"{firm} {cls._money(target, currency)} ({published})")
        return "Cobertura da ação principal: " + "; ".join(calls) + "." if calls else ""

    def _resolve_us_exchange(self, symbol: str) -> str:
        """Best-effort NASDAQ/NYSE lookup for a One Pager symbol, for Ben Kenobi
        Records' exchange classification. One Pager itself only knows the binary
        B3/US split (``_normalize_symbol``), so this cross-references the bulk US
        screener's own universe snapshots (already computed, no extra API calls).
        Falls back to the generic "US" bucket if the symbol isn't found in either
        -- e.g. it was covered by One Pager before ever appearing in a screener
        cycle. Never raises; a resolution failure just leaves the record generic.
        """
        target = symbol.strip().upper()
        snapshots = self.database.latest_analysis_snapshots(
            "valuation_universe", ["NASDAQ_UNIVERSE", "NYSE_UNIVERSE"],
        )
        for entity_key, snapshot in snapshots.items():
            rows = (snapshot.get("outputs") or {}).get("rows")
            if not isinstance(rows, list):
                continue
            if any(str(row.get("symbol") or "").upper() == target for row in rows if isinstance(row, dict)):
                return entity_key.split("_")[0]
        return "US"

    def _persist_us_valuation_snapshot(self, data: dict[str, Any], report: OnePagerReport) -> None:
        """B3 already persists its canonical universe; US valuations are born in One Pager."""
        if report.market != "US":
            return
        methodology_id = self.database.active_methodology_version_id(METHODOLOGY_KEY, METHODOLOGY_VERSION)
        if methodology_id is None:
            return
        disclosure = data.get("official_disclosure") if isinstance(data.get("official_disclosure"), dict) else {}
        source_url = disclosure.get("document_url") or data.get("ri_url")
        trigger_title = disclosure.get("title") or f"One Pager de {report.symbol} recalculado"
        exchange = self._resolve_us_exchange(report.symbol)
        self.database.save_analysis_snapshot(
            "one_pager_valuation",
            f"US:{report.symbol}",
            methodology_id,
            {
                "market": exchange,
                "source": report.source,
                "source_url": source_url,
                "trigger_title": trigger_title,
                "methodology_name": report.methodology_name,
                "methodology_version": report.methodology_version,
            },
            {
                "row": {
                    "symbol": report.symbol,
                    "company_name": report.company_name,
                    "currency": report.currency,
                    "price": report.price,
                    "c3po_tp": report.c3po_tp,
                    "consensus_tp": report.consensus_tp,
                    "buy_in": report.buy_in,
                    "confidence": report.confidence,
                    "source": report.source,
                }
            },
            report.generated_at,
        )

    def _render_pdf(self, path: Path, data: dict[str, Any], history: list[dict[str, Any]], generated_at: datetime) -> None:
        PremiumOnePagerRenderer().render(path, data, history, generated_at)

    @staticmethod
    def _rows(value: Any) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _insider_net_signal(activity: dict[str, Any] | None) -> float:
        """-1..1: net insider selling to net insider buying over the lookback
        window (Tatooine Updates: CVM VLMO for B3, Finnhub Form 4 for US),
        scaled down when the sample is thin so one lone filing can't swing it
        to the full extent. 0.0 (neutral) when there's no recent activity."""
        if not activity:
            return 0.0
        total = int(activity.get("total_count") or 0)
        if total <= 0:
            return 0.0
        net_ratio = (int(activity.get("buy_count") or 0) - int(activity.get("sell_count") or 0)) / total
        confidence = min(1.0, total / INSIDER_SIGNAL_MIN_TRANSACTIONS_FOR_FULL_WEIGHT)
        return net_ratio * confidence

    @staticmethod
    def _sentiment_confidence_adjustment(sentiment: dict[str, Any] | None) -> float:
        """Bounded +/-SENTIMENT_CONFIDENCE_MAX_SWING points from Finnhub weekly
        news sentiment (US-only source), scaled down on thin news coverage."""
        if not sentiment:
            return 0.0
        bullish = sentiment.get("bullish_percent")
        bearish = sentiment.get("bearish_percent")
        if bullish is None or bearish is None:
            return 0.0
        try:
            net = (float(bullish) - float(bearish)) / 100.0
        except (TypeError, ValueError):
            return 0.0
        articles = 0.0
        try:
            articles = float(sentiment.get("articles_last_week") or 0)
        except (TypeError, ValueError):
            pass
        weight = min(1.0, articles / SENTIMENT_MIN_ARTICLES_FOR_FULL_WEIGHT)
        return max(
            -SENTIMENT_CONFIDENCE_MAX_SWING,
            min(SENTIMENT_CONFIDENCE_MAX_SWING, net * SENTIMENT_CONFIDENCE_MAX_SWING * weight),
        )

    @classmethod
    def _sum_rows(cls, rows: list[dict[str, Any]], field: str, limit: int) -> float | None:
        values = [cls._number(row.get(field)) for row in rows[:limit]]
        clean = [value for value in values if value is not None]
        return sum(clean) if clean else None

    @staticmethod
    def _valuation_profile(sector: str, industry: str) -> str:
        """Root-caused 2026-08-20: the bare "financial" and "electric"
        keywords match on their own sector names ("Financial Services",
        "Industrials" -> "Electrical Equipment & Parts"), not just on
        actual banks/insurers/utilities. That pooled JPM's peer-median
        basket with Visa/Mastercard/CME/BlackRock (high-multiple
        diversified financials, not banks) and could pool electrical-
        equipment industrials into the low-multiple utilities bucket.
        "bank"/"insurance"/"utility"/"utilities" alone already catch every
        real bank, insurer, and utility (their EODHD industry values are
        literally "Banks-...", "Insurance-...", "Utilities-..."), so the
        broader terms were pure risk with no real coverage benefit."""
        text = f"{sector} {industry}".lower()
        if any(term in text for term in ("bank", "insurance", "banco", "segur")):
            return "financial"
        if any(term in text for term in ("utility", "utilities", "water", "energia elétrica", "saneamento")):
            return "utilities"
        if any(term in text for term in ("real estate", "reit", "property", "imobili")):
            return "real_estate"
        if any(term in text for term in ("technology", "software", "semiconductor", "internet", "tecnologia")):
            return "technology"
        if any(term in text for term in ("energy", "materials", "mining", "steel", "oil", "commodity", "petróleo", "mineração")):
            return "cyclical"
        if any(term in text for term in ("health", "consumer defensive", "industrial", "saúde")):
            return "quality"
        return "general"

    @classmethod
    def _us_peer_medians(cls, fundamentals_by_symbol: dict[str, dict[str, Any]]) -> dict[str, dict[str, float]]:
        """Live median trailing P/E and EV/EBITDA per valuation profile across
        the current US screening batch -- an actual peer comparison instead of
        the fixed FAIR_PE_BASE_FALLBACK/FAIR_EV_EBITDA_BASE_FALLBACK constants,
        mirroring B3's _sector_medians (b3_screener.py). Falls back to those
        constants per-profile whenever a bucket doesn't clear
        US_PEER_MEDIAN_MIN_SAMPLE peers, or whenever it clears the sample
        size but is too dispersed to be a coherent comparison group (see
        US_PEER_MEDIAN_MAX_DISPERSION) -- the caller does that fallback,
        not this method -- this only returns what the live data actually
        supports.
        """
        buckets: dict[str, dict[str, list[float]]] = {}
        for fundamentals in fundamentals_by_symbol.values():
            sector = str(fundamentals.get("sector") or fundamentals.get("industry") or "")
            industry = str(fundamentals.get("industry") or sector)
            profile = cls._valuation_profile(sector, industry)
            bucket = buckets.setdefault(profile, {"pe": [], "ev_ebitda": []})
            pe = cls._number(fundamentals.get("trailingPE"))
            if pe is not None and 3.0 <= pe <= 80.0:
                bucket["pe"].append(pe)
            ev_ebitda = cls._number(fundamentals.get("enterpriseToEbitda"))
            if ev_ebitda is not None and 2.0 <= ev_ebitda <= 40.0:
                bucket["ev_ebitda"].append(ev_ebitda)
        medians: dict[str, dict[str, float]] = {}
        for profile, values in buckets.items():
            entry: dict[str, float] = {}
            for metric, samples in values.items():
                if len(samples) < US_PEER_MEDIAN_MIN_SAMPLE:
                    continue
                q1, _, q3 = statistics.quantiles(samples, n=4, method="inclusive")
                dispersion = (q3 - q1) / (q3 + q1) if (q3 + q1) else 0.0
                if dispersion > US_PEER_MEDIAN_MAX_DISPERSION:
                    continue
                entry[metric] = statistics.median(samples)
            if entry:
                medians[profile] = entry
        return medians

    def _us_risk_free_rate(self) -> float:
        """Live US 10-year Treasury yield (EODHD GBOND, same feed and symbol
        Master Luke's market dashboard already uses), cached for a few hours
        since it's a slow-moving macro input, not worth re-fetching per
        valuation call. Falls back to a fixed recent-observed level if the
        feed is unavailable, mirroring b3_screener.py's LATEST_COPOM_SELIC
        fallback pattern."""
        now = datetime.now(timezone.utc)
        if self._us_risk_free_cache and now < self._us_risk_free_cache[0]:
            return self._us_risk_free_cache[1]
        rate = US_RISK_FREE_FALLBACK_RATE
        try:
            client = EodhdClient(self.settings.eodhd_base_url, self.settings.eodhd_api_token, self.market_data.http)
            history = sorted(
                client.history("US10Y", exchange="GBOND", days=10),
                key=lambda row: str(row.get("date") or ""),
            )
            closes = [self._number(row.get("close")) for row in history]
            closes = [value for value in closes if value is not None]
            if closes:
                rate = self._clamp(closes[-1] / 100.0, 0.02, 0.08)
        except Exception:
            pass
        self._us_risk_free_cache = (now + timedelta(hours=US_RISK_FREE_CACHE_HOURS), rate)
        return rate

    def _fmp_consensus_batch(
        self, symbols: list[str],
    ) -> dict[str, tuple[dict[str, float] | None, dict[str, Any] | None]]:
        """Batch counterpart of _fmp_consensus_data, for the US screener's
        nightly cycle (~650 symbols across both exchanges) -- fetched once
        per _build() call and passed per-row into _analyze_stock, same
        pattern as insider_activity/news_sentiment. Returns {} when the
        credential isn't configured or the batch itself fails; per-symbol
        failures inside the batch already degrade to (None, None) via
        FmpClient.consensus_batch, which _resolve_us_consensus falls back
        from to EODHD."""
        if not self.settings.fmp_api_token or not symbols:
            return {}
        try:
            client = FmpClient(self.settings.fmp_base_url, self.settings.fmp_api_token, self.market_data.http)
            return client.consensus_batch(symbols)
        except Exception:
            return {}

    def _fmp_consensus_data(self, symbol: str) -> tuple[dict[str, float] | None, dict[str, Any] | None]:
        """FMP Ultimate price-target-consensus + price-target-summary for a
        single US symbol, fetched fresh per Laser Pager (unlike the shared,
        slow-moving risk-free rate, analyst consensus is per-symbol and not
        worth caching here). Returns (None, None) on any failure or when
        the credential isn't configured -- _resolve_us_consensus already
        falls back to EODHD, so this must never raise."""
        if not self.settings.fmp_api_token:
            return None, None
        try:
            client = FmpClient(self.settings.fmp_base_url, self.settings.fmp_api_token, self.market_data.http)
            return client.price_target_consensus(symbol), client.price_target_summary(symbol)
        except Exception:
            return None, None

    @staticmethod
    def _us_consensus_weight(consensus: float | None, analyst_count: int | None) -> float:
        """Mirrors B3's _consensus_weight (b3_screener.py) -- how much real
        external analyst consensus should count in the FINAL target price,
        applied once after the internal model, not diluted inside it. 0.0
        when there's no consensus or analyst coverage to lean on."""
        if not consensus or not analyst_count or analyst_count <= 0:
            return 0.0
        analyst_breadth = OnePagerService._clamp(analyst_count / US_CONSENSUS_ANALYST_BREADTH_ANALYSTS, 0, 1)
        weight = US_CONSENSUS_WEIGHT_MIN + analyst_breadth * (US_CONSENSUS_WEIGHT_MAX - US_CONSENSUS_WEIGHT_MIN)
        return OnePagerService._clamp(weight, US_CONSENSUS_WEIGHT_MIN, US_CONSENSUS_WEIGHT_MAX)

    @staticmethod
    def _resolve_us_consensus(
        fmp_consensus: dict[str, float] | None,
        fmp_summary: dict[str, Any] | None,
        eodhd_consensus: float | None,
        eodhd_analyst_count: int | None,
    ) -> tuple[float | None, int | None, str]:
        """Root-caused 2026-08-20: EODHD's targetMeanPrice carries no update
        date, and its accompanying numberOfAnalystOpinions counts EPS
        estimators (Earnings.Trend), not necessarily the analysts behind
        the price target itself -- confirmed on a live sample where the
        two counts diverged for the majority of a 50-symbol sample. FMP
        Ultimate gives broker-level, dated price targets instead; prefers
        the most recent well-supported window (last month, then quarter)
        over its own all-time blended consensus, since recency is exactly
        what EODHD was missing. Falls back to EODHD only when FMP has
        nothing usable -- verified live that FMP's blended consensus and
        EODHD's landed within 0.25% of each other for JPM, so this is
        about provenance and freshness, not disagreement over the number.
        """
        if fmp_summary:
            if fmp_summary.get("last_month_count", 0) >= 3 and fmp_summary.get("last_month_avg"):
                return fmp_summary["last_month_avg"], fmp_summary["last_month_count"], "fmp_last_month"
            if fmp_summary.get("last_quarter_count", 0) >= 3 and fmp_summary.get("last_quarter_avg"):
                return fmp_summary["last_quarter_avg"], fmp_summary["last_quarter_count"], "fmp_last_quarter"
        if fmp_consensus and fmp_consensus.get("consensus"):
            return fmp_consensus["consensus"], eodhd_analyst_count, "fmp_all_time"
        return eodhd_consensus, eodhd_analyst_count, "eodhd"

    def _dcf_value(
        self,
        *,
        free_cashflow: float | None,
        shares: float | None,
        growth: float,
        market: str,
        price: float,
        fallback_eps: float | None,
        beta: float | None = None,
        risk_free_rate: float | None = None,
    ) -> float | None:
        if free_cashflow is not None and free_cashflow > 0 and shares:
            if market == "US":
                risk_free = risk_free_rate if risk_free_rate is not None else US_RISK_FREE_FALLBACK_RATE
                discount = self._clamp(
                    risk_free + (beta if beta is not None else 1.0) * US_EQUITY_RISK_PREMIUM,
                    US_DISCOUNT_RATE_MIN, US_DISCOUNT_RATE_MAX,
                )
            else:
                discount = 0.18
            terminal_growth = 0.03 if market == "US" else 0.055
            forecast_growth = self._clamp(growth, 0.01, 0.09)
            fcf_per_share = free_cashflow / shares
            present_value = 0.0
            projected = fcf_per_share
            for year in range(1, 6):
                projected *= 1 + forecast_growth * (1 - (year - 1) * 0.08)
                present_value += projected / ((1 + discount) ** year)
            terminal = projected * (1 + terminal_growth) / max(discount - terminal_growth, 0.035)
            return self._bounded_tp(present_value + terminal / ((1 + discount) ** 5), price)
        if fallback_eps:
            normalized_multiple = 17 if market == "US" else 10
            return self._bounded_tp(fallback_eps * normalized_multiple, price)
        return None

    @staticmethod
    def _weighted_value(values: tuple[tuple[float | None, float], ...], fallback: float) -> float:
        usable = [(float(value), weight) for value, weight in values if value is not None and value > 0]
        total_weight = sum(weight for _, weight in usable)
        if not usable or total_weight <= 0:
            return fallback
        return sum(value * weight for value, weight in usable) / total_weight

    @classmethod
    def _shared_framework_methods(cls, row: dict[str, Any], shared_tp: float) -> OrderedDict[str, float]:
        components = row.get("methods") if isinstance(row.get("methods"), dict) else {}
        internal_tp = cls._positive(row.get("internal_tp")) or shared_tp
        earnings = cls._positive(components.get("earnings") or components.get("cycle_earnings"))
        enterprise = cls._positive(components.get("enterprise") or components.get("cycle_enterprise"))
        dcf = cls._positive(components.get("dcf") or components.get("residual"))
        book = cls._positive(components.get("book"))
        dividend = cls._positive(components.get("dividend"))
        public_consensus = cls._positive(row.get("public_consensus_tp"))
        risk_score = cls._clamp(float(row.get("risk_score") or 50), 0, 100)
        quality_score = cls._clamp(float(row.get("operating_quality") or 50), 0, 100)
        raw = OrderedDict(
            (
                ("Goldman Sachs", cls._weighted_value(((enterprise, 0.45), (earnings, 0.35), (book, 0.20)), internal_tp)),
                ("Morgan Stanley", cls._weighted_value(((dcf, 0.75), (enterprise, 0.25)), internal_tp)),
                (
                    "Bridgewater",
                    cls._weighted_value(((dcf, 0.30), (earnings, 0.25), (book, 0.15), (public_consensus, 0.30)), internal_tp)
                    * cls._clamp(1 - (risk_score - 50) / 500, 0.88, 1.08),
                ),
                ("JPMorgan", cls._weighted_value(((earnings, 0.70), (enterprise, 0.15), (public_consensus, 0.15)), internal_tp)),
                (
                    "BlackRock",
                    cls._weighted_value(((dcf, 0.25), (earnings, 0.20), (enterprise, 0.20), (dividend, 0.10), (public_consensus, 0.25)), internal_tp)
                    * cls._clamp(1 + (quality_score - 50) / 700, 0.92, 1.08),
                ),
            )
        )
        center = statistics.median(raw.values())
        reconciled = OrderedDict((name, cls._clamp(value, center * 0.70, center * 1.30)) for name, value in raw.items())
        scale = shared_tp / statistics.mean(reconciled.values())
        return OrderedDict((name, value * scale) for name, value in reconciled.items())

    @staticmethod
    def _forward_trend(rows: list[dict[str, Any]]) -> dict[str, Any]:
        for row in rows:
            period = str(row.get("period") or "")
            if period in ("0q", "+1q"):
                return row
        return rows[0] if rows else {}

    @classmethod
    def _eps_revision(cls, trend: dict[str, Any]) -> float:
        current = cls._number(trend.get("epsTrendCurrent"))
        prior = cls._number(trend.get("epsTrend30daysAgo"))
        if current is None or prior in (None, 0):
            return 0.0
        return cls._clamp((current / prior) - 1, -0.25, 0.25)

    @staticmethod
    def _latest_and_year_ago(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
        if not rows:
            return {}, {}
        latest = rows[0]
        latest_date = str(latest.get("date") or "")
        if len(latest_date) >= 7:
            target_year = str(int(latest_date[:4]) - 1)
            target_month = latest_date[5:7]
            for row in rows[1:]:
                row_date = str(row.get("date") or "")
                if row_date.startswith(f"{target_year}-{target_month}"):
                    return latest, row
        return latest, rows[4] if len(rows) > 4 else rows[1] if len(rows) > 1 else {}

    @staticmethod
    def _quarter_label(value: Any) -> str:
        text = str(value or "")
        try:
            parsed = datetime.fromisoformat(text[:10])
        except ValueError:
            return "N/D"
        quarter = (parsed.month - 1) // 3 + 1
        return f"{quarter}T{parsed.year % 100:02d}"

    def _financial_row(self, label: str, current: float | None, previous: float | None, currency: str) -> tuple[str, str, str, str]:
        return (
            label,
            self._compact_money(current, currency),
            self._compact_money(previous, currency),
            self._percent(self._change(current, previous), signed=True),
        )

    def _margin_row(self, label: str, current: float | None, previous: float | None) -> tuple[str, str, str, str]:
        delta = (current - previous) * 100 if current is not None and previous is not None else None
        delta_text = "N/D" if delta is None else f"{delta:+.1f} p.p.".replace(".", ",")
        return label, self._percent(current), self._percent(previous), delta_text

    @staticmethod
    def _change(current: float | None, previous: float | None) -> float | None:
        if current is None or previous in (None, 0):
            return None
        return current / previous - 1

    @staticmethod
    def _percent(value: float | None, *, signed: bool = False) -> str:
        if value is None:
            return "N/D"
        template = f"{value * 100:+.1f}%" if signed else f"{value * 100:.1f}%"
        return template.replace(".", ",")

    @staticmethod
    def _plain_number(value: float | None) -> str:
        return "N/D" if value is None else f"{value:.2f}".replace(".", ",")

    @staticmethod
    def _compact_money(value: float | None, currency: str) -> str:
        if value is None:
            return "N/D"
        prefix = "R$" if currency == "BRL" else "US$" if currency == "USD" else currency
        absolute = abs(value)
        if absolute >= 1_000_000_000:
            scaled, suffix = value / 1_000_000_000, "bi"
        elif absolute >= 1_000_000:
            scaled, suffix = value / 1_000_000, "mi"
        elif absolute >= 1_000:
            scaled, suffix = value / 1_000, "mil"
        else:
            scaled, suffix = value, ""
        number = f"{scaled:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{prefix} {number} {suffix}".strip()

    @staticmethod
    def _shorten(text: str, limit: int) -> str:
        clean = " ".join(
            text.replace("–", "-")
            .replace("—", "-")
            .replace("‑", "-")
            .replace("“", '"')
            .replace("”", '"')
            .split()
        )
        if len(clean) <= limit:
            return clean
        shortened = clean[: max(limit - 1, 1)].rsplit(" ", 1)[0].rstrip(" ,;:")
        return f"{shortened}."

    @staticmethod
    def _analyst_mix(ratings: dict[str, Any]) -> str:
        buys = int(ratings.get("strongBuy") or 0) + int(ratings.get("buy") or 0)
        holds = int(ratings.get("hold") or 0)
        sells = int(ratings.get("sell") or 0) + int(ratings.get("strongSell") or 0)
        total = buys + holds + sells
        return f"{buys} Compra, {holds} Neutro e {sells} Venda" if total else "distribuição Buy/Hold/Sell indisponível"

    @classmethod
    def _business_summary(cls, company_name: str, sector: str, industry: str) -> str:
        text = f"{sector} {industry}".lower()
        descriptions = (
            (("internet retail", "e-commerce", "comércio eletrônico"), "comércio eletrônico, marketplace, publicidade digital e serviços associados"),
            (("software", "application", "infrastructure"), "software, infraestrutura digital e soluções recorrentes para empresas e consumidores"),
            (("semiconductor", "chip"), "semicondutores e infraestrutura computacional, com demanda ligada a data centers, IA e eletrônicos"),
            (("bank", "financial", "insurance"), "serviços financeiros, crédito, investimentos e gestão de risco"),
            (("oil", "gas", "energy", "petróleo"), "energia, produção e comercialização de petróleo, gás e derivados"),
            (("mining", "steel", "materials", "mineração"), "materiais básicos, mineração e cadeias industriais intensivas em capital"),
            (("utility", "electric", "water", "energia elétrica", "saneamento"), "infraestrutura regulada, geração e distribuição de serviços essenciais"),
            (("health", "biotech", "pharma", "saúde"), "saúde, biotecnologia e produtos de alto conteúdo científico"),
            (("telecom", "communication"), "telecomunicações, conectividade e infraestrutura de redes"),
            (("auto", "vehicle", "transport"), "mobilidade, veículos e soluções para transporte"),
            (("real estate", "reit", "property", "imobili"), "incorporação, propriedades e serviços ligados ao mercado imobiliário"),
            (("industrial", "engineering", "construction"), "serviços industriais, engenharia e soluções para infraestrutura"),
        )
        for terms, description in descriptions:
            if any(term in text for term in terms):
                return cls._shorten(f"{company_name} atua em {description}; escala, execução e disciplina de capital são os principais vetores da tese.", 180)
        sector_pt = {
            "technology": "tecnologia",
            "consumer cyclical": "consumo discricionário",
            "consumer defensive": "consumo essencial",
            "industrials": "indústria",
            "basic materials": "materiais básicos",
            "financial services": "serviços financeiros",
            "communication services": "comunicações",
        }.get(sector.lower(), sector)
        return cls._shorten(
            f"{company_name} atua no setor de {sector_pt}; crescimento, rentabilidade, geração de caixa e disciplina de capital são os vetores centrais da tese.",
            180,
        )

    @staticmethod
    def _date_display(value: Any) -> str:
        if isinstance(value, datetime):
            return value.astimezone().strftime("%d/%m/%y")
        text = str(value or "")
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone().strftime("%d/%m/%y")
        except ValueError:
            return text[:10] or "N/D"

    @staticmethod
    def _positive(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) and number > 0 else None

    @staticmethod
    def _ratio(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        return number / 100 if abs(number) > 2 else number

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def _bounded_tp(self, value: Any, price: float) -> float | None:
        candidate = self._positive(value)
        if candidate is None or candidate < price * 0.25 or candidate > price * 4:
            return None
        return candidate

    @staticmethod
    def _dispersion(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        return math.sqrt(variance) / mean * 100 if mean else 0.0

    @staticmethod
    def _money(value: float | None, currency: str) -> str:
        if value is None:
            return "N/D"
        prefix = "R$" if currency == "BRL" else "US$" if currency == "USD" else currency
        return f"{prefix} {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @staticmethod
    def _signed(value: Any) -> str:
        try:
            return f"{float(value):+.2f}%"
        except (TypeError, ValueError):
            return "variação N/D"

    @staticmethod
    def _metric_sentence(label: str, value: float | None) -> str:
        return f"{label} não informado" if value is None else f"{label} de {value * 100:+.1f}%"
