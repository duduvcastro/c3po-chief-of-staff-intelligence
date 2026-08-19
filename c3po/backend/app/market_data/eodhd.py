from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..schemas import NormalizedQuote
from .http import JsonHttpClient
from .models import (
    canonical_us_security_name,
    canonical_us_security_type,
    from_unix,
    number,
    quality_for,
    require_price,
    utc_now,
)


class EodhdClient:
    code = "eodhd"
    name = "EODHD"

    def __init__(self, base_url: str, token: str, http: JsonHttpClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.http = http

    def quotes(self, symbols: list[str]) -> list[NormalizedQuote]:
        provider_symbols = [self._provider_symbol(symbol) for symbol in symbols]
        first, *rest = provider_symbols
        params: dict[str, Any] = {"api_token": self.token, "fmt": "json"}
        if rest:
            params["s"] = ",".join(rest)
        payload = self.http.get_json(f"{self.base_url}/api/real-time/{first}", params=params)
        records = payload if isinstance(payload, list) else [payload]
        # One symbol in a batch can come back HTTP 200 with placeholder
        # ("NA") fields instead of a real quote -- confirmed live for
        # SSEC.INDX (2026-08-19): the plain list comprehension this used to
        # be let that one record's ValueError (from require_price) abort the
        # whole batch, silently dropping every other symbol's valid quote
        # (N225.INDX/GDAXI.INDX) along with it. Skip bad records individually.
        quotes: list[NormalizedQuote] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            try:
                quotes.append(self._normalize(record))
            except (ValueError, TypeError):
                continue
        return quotes

    def fundamentals(self, symbols: list[str], *, exchange: str = "SA", workers: int = 8) -> dict[str, dict[str, Any]]:
        clean_symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
        if not clean_symbols:
            return {}

        def fetch(symbol: str) -> tuple[str, dict[str, Any]]:
            provider_symbol = symbol if "." in symbol else f"{symbol}.{exchange}"
            try:
                payload = self.http.get_json(
                    f"{self.base_url}/api/v1.1/fundamentals/{provider_symbol}",
                    params={"api_token": self.token, "fmt": "json"},
                )
                return symbol.partition(".")[0], self._normalize_fundamentals(payload)
            except Exception:
                return symbol.partition(".")[0], {}

        output: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as executor:
            for symbol, payload in executor.map(fetch, clean_symbols):
                if payload:
                    output[symbol] = payload
        return output

    def history(self, symbol: str, *, exchange: str = "US", days: int = 365) -> list[dict[str, Any]]:
        clean = symbol.strip().upper()
        provider_symbol = clean if "." in clean else f"{clean}.{exchange}"
        end = date.today()
        start = end - timedelta(days=max(30, min(days, 730)))
        payload = self.http.get_json(
            f"{self.base_url}/api/eod/{provider_symbol}",
            params={
                "api_token": self.token,
                "fmt": "json",
                "period": "d",
                "from": start.isoformat(),
                "to": end.isoformat(),
            },
        )
        if not isinstance(payload, list):
            return []
        output = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            close = number(item.get("adjusted_close")) or number(item.get("close"))
            if close is not None:
                output.append({
                    "date": item.get("date"),
                    "close": close,
                    "volume": number(item.get("volume")),
                })
        return output

    def intraday(
        self,
        symbol: str,
        *,
        exchange: str = "US",
        interval: str = "5m",
        days: int = 7,
    ) -> list[dict[str, Any]]:
        clean = symbol.strip().upper()
        provider_symbol = clean if "." in clean else f"{clean}.{exchange}"
        now = datetime.now(timezone.utc)
        payload = self.http.get_json(
            f"{self.base_url}/api/intraday/{provider_symbol}",
            params={
                "api_token": self.token,
                "fmt": "json",
                "interval": interval,
                "from": int((now - timedelta(days=max(2, min(days, 120)))).timestamp()),
                "to": int(now.timestamp()),
            },
        )
        rows = payload if isinstance(payload, list) else payload.get("data", []) if isinstance(payload, dict) else []
        return [self._normalize_intraday(item) for item in rows if isinstance(item, dict)]

    @staticmethod
    def _normalize_intraday(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "timestamp": item.get("timestamp", item.get("datetime")),
            "open": number(item.get("open")),
            "high": number(item.get("high")),
            "low": number(item.get("low")),
            "close": number(item.get("close", item.get("price"))),
            "volume": number(item.get("volume")) or 0.0,
        }

    def histories(
        self,
        symbols: list[str],
        *,
        exchange: str = "SA",
        days: int = 120,
        workers: int = 8,
    ) -> dict[str, list[dict[str, Any]]]:
        clean_symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
        if not clean_symbols:
            return {}

        def fetch(symbol: str) -> tuple[str, list[dict[str, Any]]]:
            try:
                return symbol.partition(".")[0], self.history(symbol, exchange=exchange, days=days)
            except Exception:
                return symbol.partition(".")[0], []

        output: dict[str, list[dict[str, Any]]] = {}
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as executor:
            for symbol, rows in executor.map(fetch, clean_symbols):
                if rows:
                    output[symbol] = rows
        return output

    @staticmethod
    def _normalize_fundamentals(payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict) or not payload.get("General"):
            return {}
        general = payload.get("General", {})
        etf_data = payload.get("ETF_Data", {}) if isinstance(payload.get("ETF_Data"), dict) else {}
        highlights = payload.get("Highlights", {})
        valuation = payload.get("Valuation", {})
        shares = payload.get("SharesStats", {})
        technicals = payload.get("Technicals", {})
        analyst_ratings = payload.get("AnalystRatings", {})
        trend = payload.get("Earnings", {}).get("Trend", {})
        annual_trend = trend.get("Annual", {}) if isinstance(trend, dict) else {}
        trend_rows = list(annual_trend.values()) if isinstance(annual_trend, dict) else []
        analyst_count = max(
            (int(number(item.get("earningsEstimateNumberOfAnalysts")) or 0) for item in trend_rows if isinstance(item, dict)),
            default=0,
        )
        financials = payload.get("Financials", {})
        balance = EodhdClient._latest_statement(financials.get("Balance_Sheet", {}))
        cash_flow = EodhdClient._latest_statement(financials.get("Cash_Flow", {}))
        income = EodhdClient._latest_statement(financials.get("Income_Statement", {}))
        quarterly_income = EodhdClient._statement_rows(financials.get("Income_Statement", {}), "quarterly", 8)
        annual_income = EodhdClient._statement_rows(financials.get("Income_Statement", {}), "yearly", 6)
        quarterly_cash_flow = EodhdClient._statement_rows(financials.get("Cash_Flow", {}), "quarterly", 8)
        quarterly_balance = EodhdClient._statement_rows(financials.get("Balance_Sheet", {}), "quarterly", 8)
        financial_periods = [
            parsed
            for rows in (quarterly_income, quarterly_cash_flow, quarterly_balance)
            for row in rows
            if (parsed := EodhdClient._valid_date(row.get("date")))
        ]
        most_recent_quarter = EodhdClient._valid_date(highlights.get("MostRecentQuarter"))
        if most_recent_quarter:
            financial_periods.append(most_recent_quarter)
        financials_as_of = max(financial_periods) if financial_periods else None
        earnings = payload.get("Earnings", {})
        earnings_history = EodhdClient._dated_rows(earnings.get("History", {}), 8)
        quarterly_trend = EodhdClient._dated_rows(
            trend.get("Quarterly", {}) if isinstance(trend, dict) else {},
            8,
        )
        short_debt = number(balance.get("shortTermDebt")) or number(balance.get("shortLongTermDebt")) or 0.0
        long_debt = number(balance.get("longTermDebt")) or 0.0
        debt = short_debt + long_debt
        equity = number(balance.get("totalStockholderEquity")) or number(balance.get("totalEquity"))
        ebitda = number(highlights.get("EBITDA")) or number(income.get("ebitda"))
        revenue = number(highlights.get("RevenueTTM")) or number(income.get("totalRevenue"))
        performance = etf_data.get("Performance", {}) if isinstance(etf_data.get("Performance"), dict) else {}
        valuations_growth = etf_data.get("Valuations_Growth", {}) if isinstance(etf_data.get("Valuations_Growth"), dict) else {}
        valuation_rows = [value for value in valuations_growth.values() if isinstance(value, dict)]
        latest_etf_valuation = valuation_rows[0] if valuation_rows else {}
        provider_symbol = str(general.get("Code") or "")
        security_type = canonical_us_security_type(
            provider_symbol,
            general.get("Type") or general.get("TypeName"),
            has_etf_data=bool(etf_data),
        )
        is_etf = security_type == "ETF"
        return {
            "provider": "eodhd",
            "provider_symbol": provider_symbol,
            "companyName": canonical_us_security_name(
                provider_symbol,
                general.get("Name") or provider_symbol,
            ),
            "securityType": security_type,
            "isETF": is_etf,
            "sector": str(general.get("Sector") or ""),
            "industry": str(general.get("Industry") or ""),
            "gicSector": str(general.get("GicSector") or general.get("GICS_Sector") or ""),
            "gicGroup": str(general.get("GicGroup") or general.get("GICS_Group") or ""),
            "gicIndustry": str(general.get("GicIndustry") or general.get("GICS_Industry") or ""),
            "gicSubIndustry": str(general.get("GicSubIndustry") or general.get("GICS_SubIndustry") or ""),
            "description": str(general.get("Description") or ""),
            "country": str(general.get("CountryName") or general.get("CountryISO") or ""),
            "website": str(general.get("WebURL") or ""),
            "logoUrl": EodhdClient.normalize_logo_url(general.get("LogoURL")),
            "updated_at": EodhdClient._valid_date(general.get("UpdatedAt")) or most_recent_quarter,
            "financialsAsOf": financials_as_of,
            "marketCap": number(highlights.get("MarketCapitalization")),
            "trailingPE": number(valuation.get("TrailingPE")) or number(highlights.get("PERatio")),
            "forwardPE": number(valuation.get("ForwardPE")),
            "enterpriseToEbitda": number(valuation.get("EnterpriseValueEbitda")),
            "pegRatio": number(highlights.get("PEGRatio")),
            "priceToBook": number(valuation.get("PriceBookMRQ")),
            "beta": number(technicals.get("Beta")),
            "sharesOutstanding": number(shares.get("SharesOutstanding")),
            "trailingEps": number(highlights.get("DilutedEpsTTM")) or number(highlights.get("EarningsShare")),
            "forwardEps": number(highlights.get("EPSEstimateNextYear")) or number(highlights.get("EPSEstimateCurrentYear")),
            "bookValue": number(highlights.get("BookValue")),
            "dividendYield": number(highlights.get("DividendYield")),
            "returnOnEquity": number(highlights.get("ReturnOnEquityTTM")),
            "profitMargins": number(highlights.get("ProfitMargin")),
            "operatingMargins": number(highlights.get("OperatingMarginTTM")),
            "returnOnAssets": number(highlights.get("ReturnOnAssetsTTM")),
            "revenueGrowthAnnual": number(highlights.get("QuarterlyRevenueGrowthYOY")),
            "earningsGrowthAnnual": number(highlights.get("QuarterlyEarningsGrowthYOY")),
            "freeCashflow": number(cash_flow.get("freeCashFlow")),
            "operatingCashflow": number(cash_flow.get("totalCashFromOperatingActivities")),
            "ebitda": ebitda,
            "totalRevenue": revenue,
            "ebitdaMargins": ebitda / revenue if ebitda and revenue else None,
            "totalCash": number(balance.get("cashAndEquivalents")) or number(balance.get("cash")),
            "totalDebt": debt or number(balance.get("netDebt")),
            "totalEquity": equity,
            "debtToEquity": debt / equity if debt and equity and equity > 0 else None,
            "targetMeanPrice": number(highlights.get("WallStreetTargetPrice")),
            "numberOfAnalystOpinions": analyst_count,
            "analystRatings": {
                "rating": number(analyst_ratings.get("Rating")),
                "targetPrice": number(analyst_ratings.get("TargetPrice")),
                "strongBuy": int(number(analyst_ratings.get("StrongBuy")) or 0),
                "buy": int(number(analyst_ratings.get("Buy")) or 0),
                "hold": int(number(analyst_ratings.get("Hold")) or 0),
                "sell": int(number(analyst_ratings.get("Sell")) or 0),
                "strongSell": int(number(analyst_ratings.get("StrongSell")) or 0),
            },
            "technical52WeekHigh": number(technicals.get("52WeekHigh")),
            "technical52WeekLow": number(technicals.get("52WeekLow")),
            "movingAverage50Day": number(technicals.get("50DayMA")),
            "movingAverage200Day": number(technicals.get("200DayMA")),
            "quarterlyIncome": quarterly_income,
            "annualIncome": annual_income,
            "quarterlyCashFlow": quarterly_cash_flow,
            "quarterlyBalance": quarterly_balance,
            "earningsHistory": earnings_history,
            "earningsTrendQuarterly": quarterly_trend,
            "etfCategory": str(etf_data.get("Category") or etf_data.get("Type") or general.get("Category") or ""),
            "etfTotalAssets": number(etf_data.get("TotalAssets")) or number(highlights.get("MarketCapitalization")),
            "etfNetExpenseRatio": (
                number(etf_data.get("NetExpenseRatio"))
                or number(etf_data.get("Net_Expense_Ratio"))
                or number(etf_data.get("Ongoing_Charge"))
                or number(etf_data.get("Max_Annual_Mgmt_Charge"))
            ),
            "etfHoldingsCount": int(number(etf_data.get("Holdings_Count")) or number(etf_data.get("HoldingsCount")) or 0),
            "etfExpectedReturn3Y": number(etf_data.get("ThreeYearExpectedReturn")) or number(performance.get("3y_ExpectedReturn")),
            "etfVolatility1Y": number(performance.get("1y_Volatility")) or number(etf_data.get("Volatility_1y")),
            "etfSharpe3Y": number(performance.get("3y_SharpRatio")) or number(performance.get("3y_SharpeRatio")),
            "etfReturnYTD": number(performance.get("Returns_YTD")) or number(performance.get("YTD")),
            "etfReturn1Y": number(performance.get("Returns_1Y")) or number(performance.get("1Y")),
            "etfReturn3Y": number(performance.get("Returns_3Y")) or number(performance.get("3Y")),
            "etfReturn5Y": number(performance.get("Returns_5Y")) or number(performance.get("5Y")),
            "etfForwardPE": number(latest_etf_valuation.get("Forward_PE")) or number(latest_etf_valuation.get("ForwardPE")),
            "etfPriceToBook": number(latest_etf_valuation.get("Price_Book")) or number(latest_etf_valuation.get("PriceBook")),
        }

    @staticmethod
    def _latest_statement(section: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(section, dict):
            return {}
        periods = section.get("quarterly") or section.get("yearly") or {}
        if not isinstance(periods, dict) or not periods:
            return {}
        latest_key = max(periods)
        latest = periods.get(latest_key)
        return latest if isinstance(latest, dict) else {}

    @staticmethod
    def _valid_date(value: Any) -> str | None:
        if not value:
            return None
        try:
            parsed = date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
        return parsed.isoformat() if 1900 <= parsed.year <= 2100 else None

    @staticmethod
    def _statement_rows(section: dict[str, Any], frequency: str, limit: int) -> list[dict[str, Any]]:
        if not isinstance(section, dict):
            return []
        periods = section.get(frequency, {})
        return EodhdClient._dated_rows(periods, limit)

    @staticmethod
    def _dated_rows(periods: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        if not isinstance(periods, dict):
            return []
        rows: list[dict[str, Any]] = []
        for key in sorted(periods, reverse=True)[:limit]:
            item = periods.get(key)
            if not isinstance(item, dict):
                continue
            normalized: dict[str, Any] = {"date": item.get("date") or key}
            for field, value in item.items():
                if field == "date":
                    continue
                parsed = number(value)
                normalized[field] = parsed if parsed is not None else value
            rows.append(normalized)
        return rows

    @staticmethod
    def _provider_symbol(symbol: str) -> str:
        clean = symbol.strip().upper()
        if "." in clean:
            return clean
        return f"{clean}.US"

    @staticmethod
    def normalize_logo_url(value: Any) -> str:
        clean = str(value or "").strip()
        if not clean:
            return ""
        if clean.startswith("//"):
            return f"https:{clean}"
        if clean.startswith("/"):
            return f"https://eodhd.com{clean}"
        return clean

    def _normalize(self, item: dict[str, Any]) -> NormalizedQuote:
        collected_at = utc_now()
        provider_symbol = str(item.get("code") or item.get("symbol") or "").upper()
        symbol, _, exchange = provider_symbol.partition(".")
        quote = NormalizedQuote(
            provider="eodhd",
            symbol=symbol,
            provider_symbol=provider_symbol,
            exchange=exchange or "US",
            currency=str(item.get("currency") or "USD"),
            price=require_price(item.get("close", item.get("price")), provider_symbol),
            change=number(item.get("change")),
            change_percent=number(item.get("change_p", item.get("changePercent"))),
            open=number(item.get("open")),
            low=number(item.get("low")),
            high=number(item.get("high")),
            previous_close=number(item.get("previousClose")),
            volume=number(item.get("volume")),
            market_cap=number(item.get("market_capitalization", item.get("marketCap"))),
            as_of=from_unix(item.get("timestamp"), collected_at),
            collected_at=collected_at,
            quality_score=76,
            is_delayed=True,
        )
        quote.quality_score = quality_for(quote)
        return quote
