from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .http import JsonHttpClient
from .models import number


def _first_number(*values: Any) -> float | None:
    """Return the first numeric value, preserving valid zeroes."""
    for value in values:
        parsed = number(value)
        if parsed is not None:
            return parsed
    return None


class FmpClient:
    """Financial Modeling Prep, Ultimate plan (2026-08-20): real analyst
    consensus with broker-level provenance, replacing EODHD's single
    targetMeanPrice (no update date, and its accompanying
    numberOfAnalystOpinions counts EPS estimators, not necessarily the
    same analysts behind the price target -- see one_pager.py's
    _valuation_profile-adjacent consensus wiring for the full story).
    Endpoints and response shapes verified live against production data
    (JPM/AAPL) on 2026-08-20 before this shipped -- see
    https://site.financialmodelingprep.com/developer/docs/stable/{price-target-consensus,price-target-summary,grades}.
    """

    code = "fmp"
    name = "Financial Modeling Prep"

    def __init__(self, base_url: str, token: str, http: JsonHttpClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.http = http

    def price_target_consensus(self, symbol: str) -> dict[str, float] | None:
        """High/low/median/consensus across all analyst history -- no
        per-record date, this is FMP's blended aggregate."""
        try:
            payload = self.http.get_json(
                f"{self.base_url}/stable/price-target-consensus",
                params={"symbol": symbol, "apikey": self.token},
            )
        except Exception:
            return None
        row = self._first_row(payload)
        if row is None:
            return None
        consensus = number(row.get("targetConsensus"))
        if consensus is None:
            return None
        return {
            "consensus": consensus,
            "median": number(row.get("targetMedian")),
            "high": number(row.get("targetHigh")),
            "low": number(row.get("targetLow")),
        }

    def batch_quotes(
        self, symbols: list[str], *, chunk_size: int = 100, workers: int = 6,
        diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Fetch lightweight real-time quotes for a large candidate set.

        FMP Ultimate exposes ``stable/batch-quote`` so R2D2 can preflight many
        candidates without consuming scarce EODHD WebSocket subscriptions.
        Per-chunk failures are isolated; callers can safely fall back to their
        existing ranking when FMP is unavailable.
        """
        clean_symbols = list(dict.fromkeys(
            symbol.strip().upper() for symbol in symbols if symbol.strip()
        ))
        if not clean_symbols:
            return {}
        size = max(1, min(chunk_size, 250))
        chunks = [clean_symbols[index:index + size] for index in range(0, len(clean_symbols), size)]

        def fetch(chunk: list[str]) -> tuple[list[str], list[dict[str, Any]], str | None]:
            try:
                payload = self.http.get_json(
                    f"{self.base_url}/stable/batch-quote",
                    params={"symbols": ",".join(chunk), "apikey": self.token},
                )
            except Exception as exc:
                # Never expose exception text here: HTTP client errors can
                # contain the request URL, including the FMP API key.
                return chunk, [], type(exc).__name__
            rows = [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []
            return chunk, rows, None

        output: dict[str, dict[str, Any]] = {}
        successful_symbols: set[str] = set()
        failed_symbols: set[str] = set()
        failure_types: set[str] = set()
        failed_chunk_count = 0
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(chunks), 10))) as executor:
            for chunk, rows, failure_type in executor.map(fetch, chunks):
                if failure_type:
                    failed_chunk_count += 1
                    failed_symbols.update(chunk)
                    failure_types.add(failure_type)
                    continue
                successful_symbols.update(chunk)
                for row in rows:
                    symbol = str(row.get("symbol") or "").strip().upper()
                    price = number(row.get("price"))
                    if not symbol or price is None or price <= 0:
                        continue
                    output[symbol] = {
                        "symbol": symbol,
                        "price": price,
                        "volume": number(row.get("volume")),
                        "average_volume": number(row.get("avgVolume")),
                        "change_percent": number(row.get("changePercentage")),
                        "timestamp": int(number(row.get("timestamp")) or 0),
                    }
        if diagnostics is not None:
            diagnostics.update({
                "request_count": len(chunks),
                "failed_chunk_count": failed_chunk_count,
                "successful_symbols": sorted(successful_symbols),
                "failed_symbols": sorted(failed_symbols),
                "failure_types": sorted(failure_types),
            })
        return output

    def price_target_summary(self, symbol: str) -> dict[str, Any] | None:
        """Recency-scoped average target + analyst count per window (last
        month/quarter/year/all-time) -- what actually fixes the freshness
        gap EODHD has: its target price carries no update date at all."""
        try:
            payload = self.http.get_json(
                f"{self.base_url}/stable/price-target-summary",
                params={"symbol": symbol, "apikey": self.token},
            )
        except Exception:
            return None
        row = self._first_row(payload)
        if row is None:
            return None
        return {
            "last_month_count": int(number(row.get("lastMonthCount")) or 0),
            "last_month_avg": number(row.get("lastMonthAvgPriceTarget")),
            "last_quarter_count": int(number(row.get("lastQuarterCount")) or 0),
            "last_quarter_avg": number(row.get("lastQuarterAvgPriceTarget")),
        }

    def consensus_batch(
        self, symbols: list[str], *, workers: int = 10,
    ) -> dict[str, tuple[dict[str, float] | None, dict[str, Any] | None]]:
        """price_target_consensus + price_target_summary for many symbols in
        parallel -- mirrors EodhdClient.fundamentals()/histories()'s
        ThreadPoolExecutor pattern for the batch US screener, where these
        are single-symbol-only endpoints and a nightly cycle covers ~650
        symbols across both exchanges. A failed symbol contributes
        (None, None), never breaks the batch."""
        clean_symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
        if not clean_symbols:
            return {}

        def fetch(symbol: str) -> tuple[str, tuple[dict[str, float] | None, dict[str, Any] | None]]:
            return symbol, (self.price_target_consensus(symbol), self.price_target_summary(symbol))

        output: dict[str, tuple[dict[str, float] | None, dict[str, Any] | None]] = {}
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 20))) as executor:
            for symbol, result in executor.map(fetch, clean_symbols):
                output[symbol] = result
        return output

    def institutional_positions_batch(
        self, symbols: list[str], *, year: int, quarter: int, workers: int = 10,
    ) -> dict[str, dict[str, Any] | None]:
        """institutional_positions() for many symbols in parallel, same
        quarter for the whole batch (one nightly cycle run against the
        same "today") -- mirrors consensus_batch's pattern."""
        clean_symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
        if not clean_symbols:
            return {}

        def fetch(symbol: str) -> tuple[str, dict[str, Any] | None]:
            return symbol, self.institutional_positions(symbol, year=year, quarter=quarter)

        output: dict[str, dict[str, Any] | None] = {}
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 20))) as executor:
            for symbol, result in executor.map(fetch, clean_symbols):
                output[symbol] = result
        return output

    def recent_grades(self, symbol: str, *, since: date | None = None) -> list[dict[str, Any]]:
        """Individual broker upgrade/downgrade/maintain actions with a real
        date and grading company name -- the broker-level provenance
        EODHD doesn't expose at all. Returns [] on any failure; callers
        must never let one bad symbol break a batch."""
        try:
            payload = self.http.get_json(
                f"{self.base_url}/stable/grades",
                params={"symbol": symbol, "apikey": self.token},
            )
        except Exception:
            return []
        rows = payload if isinstance(payload, list) else []
        output: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            grade_date = self._valid_date(row.get("date"))
            if grade_date is None or (since and grade_date < since):
                continue
            output.append({
                "date": grade_date,
                "grading_company": str(row.get("gradingCompany") or ""),
                "previous_grade": str(row.get("previousGrade") or ""),
                "new_grade": str(row.get("newGrade") or ""),
                "action": str(row.get("action") or "").lower(),
            })
        return output

    def recent_grades_batch(
        self, symbols: list[str], *, since: date | None = None, workers: int = 10,
    ) -> dict[str, list[dict[str, Any]]]:
        """recent_grades() for many symbols in parallel -- mirrors
        consensus_batch()/institutional_positions_batch()'s pattern for
        the nightly cycle."""
        clean_symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
        if not clean_symbols:
            return {}

        def fetch(symbol: str) -> tuple[str, list[dict[str, Any]]]:
            return symbol, self.recent_grades(symbol, since=since)

        output: dict[str, list[dict[str, Any]]] = {}
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 20))) as executor:
            for symbol, result in executor.map(fetch, clean_symbols):
                output[symbol] = result
        return output

    def institutional_positions(self, symbol: str, *, year: int, quarter: int) -> dict[str, Any] | None:
        """Quarterly 13F positioning snapshot for one symbol -- how many
        institutions hold it, how that count and share count changed, and
        the breakdown of new/increased/reduced/closed positions this
        quarter. Phase 2's institutional-conviction signal, mirroring
        _insider_net_signal's role for Form 4 insider activity."""
        try:
            payload = self.http.get_json(
                f"{self.base_url}/stable/institutional-ownership/symbol-positions-summary",
                params={"symbol": symbol, "year": year, "quarter": quarter, "apikey": self.token},
            )
        except Exception:
            return None
        row = self._first_row(payload)
        if row is None:
            return None
        return {
            "investors_holding": int(number(row.get("investorsHolding")) or 0),
            "investors_holding_change": int(number(row.get("investorsHoldingChange")) or 0),
            "shares": number(row.get("numberOf13Fshares")),
            "shares_change": number(row.get("numberOf13FsharesChange")),
            "new_positions": int(number(row.get("newPositions")) or 0),
            "increased_positions": int(number(row.get("increasedPositions")) or 0),
            "reduced_positions": int(number(row.get("reducedPositions")) or 0),
            "closed_positions": int(number(row.get("closedPositions")) or 0),
        }

    @staticmethod
    def latest_reportable_13f_quarter(today: date) -> tuple[int, int]:
        """13F filings are due 45 days after quarter-end; picks the most
        recent calendar quarter whose deadline (plus a few days for FMP to
        finish processing) has already passed, so a request made right at
        the edge of a deadline doesn't get back a mostly-empty quarter."""
        quarter_end = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
        year, quarter = today.year, (today.month - 1) // 3 + 1
        while True:
            month, day = quarter_end[quarter]
            if today >= date(year, month, day) + timedelta(days=50):
                return year, quarter
            quarter -= 1
            if quarter == 0:
                quarter, year = 4, year - 1

    def stock_peers(self, symbol: str) -> list[dict[str, Any]]:
        """Real peer companies for ``symbol`` (FMP's own peer taxonomy) --
        the Valuation V2 replacement for fair-multiple constants. Returns
        [] on any failure; a missing peer set is a fallback-ladder signal,
        never an error."""
        rows, _status = self._stock_peers_result(symbol)
        return rows

    def _stock_peers_result(self, symbol: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows, status = self._valuation_v2_rows(
            "stock-peers",
            {"symbol": symbol, "apikey": self.token},
        )
        output: list[dict[str, Any]] = []
        source_symbol = symbol.strip().upper()
        for row in rows:
            # Legacy v4 shape: one row carrying the whole list.
            peers_list = row.get("peersList")
            if isinstance(peers_list, list):
                output.extend(
                    self._peer_item(str(peer), source_symbol=source_symbol)
                    for peer in peers_list
                    if str(peer).strip() and str(peer).strip().upper() != source_symbol
                )
                continue
            peer_symbol = str(row.get("symbol") or "").strip().upper()
            if not peer_symbol or peer_symbol == source_symbol:
                continue
            output.append(self._peer_item(
                peer_symbol,
                source_symbol=source_symbol,
                company_name=str(row.get("companyName") or ""),
                price=number(row.get("price")),
                market_cap=number(row.get("mktCap")),
            ))
        unique = {str(item["symbol"]): item for item in output}
        parsed = list(unique.values())
        return parsed, self._finalize_v2_status(status, len(parsed))

    def analyst_estimates_annual(self, symbol: str, *, limit: int = 8) -> list[dict[str, Any]]:
        """Forward consensus estimates per FISCAL YEAR (revenue/EBITDA/EPS
        avg-low-high plus analyst counts) -- the term structure that
        replaces EODHD's single-point forwardEps in Valuation V2. Rows are
        returned in fiscal-date order so callers can select FY1/FY2 relative
        to their as-of date instead of trusting provider response order. []
        on any failure."""
        rows, _status = self._analyst_estimates_annual_result(symbol, limit=limit)
        return rows

    def _analyst_estimates_annual_result(
        self, symbol: str, *, limit: int = 8,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows, status = self._valuation_v2_rows(
            "analyst-estimates",
            {
                "symbol": symbol,
                "period": "annual",
                "limit": max(1, min(limit, 20)),
                "apikey": self.token,
            },
        )
        output: list[dict[str, Any]] = []
        for row in rows:
            fiscal_end = self._valid_date(row.get("date"))
            if fiscal_end is None:
                continue
            output.append({
                "fiscal_year_end": fiscal_end.isoformat(),
                "revenue_avg": number(row.get("revenueAvg")),
                "revenue_low": number(row.get("revenueLow")),
                "revenue_high": number(row.get("revenueHigh")),
                "ebitda_avg": number(row.get("ebitdaAvg")),
                "eps_avg": number(row.get("epsAvg")),
                "eps_low": number(row.get("epsLow")),
                "eps_high": number(row.get("epsHigh")),
                "analysts_revenue": int(
                    _first_number(
                        row.get("numAnalystsRevenue"),
                        row.get("numberAnalystEstimatedRevenue"),
                    )
                    or 0
                ),
                "analysts_eps": int(
                    _first_number(
                        row.get("numAnalystsEps"),
                        row.get("numberAnalystsEstimatedEps"),
                    )
                    or 0
                ),
            })
        output.sort(key=lambda row: str(row["fiscal_year_end"]))
        return output, self._finalize_v2_status(status, len(output))

    def ratios_annual(self, symbol: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Up to ``limit`` fiscal years of reported valuation/profitability
        ratios -- the company's OWN historical band, Valuation V2's second
        external anchor. [] on any failure."""
        rows, _status = self._ratios_annual_result(symbol, limit=limit)
        return rows

    def _ratios_annual_result(
        self, symbol: str, *, limit: int = 10,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows, status = self._valuation_v2_rows(
            "ratios",
            {
                "symbol": symbol,
                "period": "annual",
                "limit": max(1, min(limit, 20)),
                "apikey": self.token,
            },
        )
        output: list[dict[str, Any]] = []
        for row in rows:
            fiscal_end = self._valid_date(row.get("date"))
            if fiscal_end is None:
                continue
            output.append({
                "fiscal_year_end": fiscal_end.isoformat(),
                "pe": _first_number(row.get("priceToEarningsRatio"), row.get("priceEarningsRatio")),
                "price_to_book": _first_number(row.get("priceToBookRatio"), row.get("priceToBookValueRatio")),
                "price_to_sales": number(row.get("priceToSalesRatio")),
                "ev_ebitda": number(row.get("enterpriseValueMultiple")),
                "roe": number(row.get("returnOnEquity")),
                "net_margin": number(row.get("netProfitMargin")),
                "operating_margin": number(row.get("operatingProfitMargin")),
                "gross_margin": number(row.get("grossProfitMargin")),
                "debt_to_equity": _first_number(row.get("debtToEquityRatio"), row.get("debtEquityRatio")),
                "dividend_yield": number(row.get("dividendYield")),
            })
        output.sort(key=lambda row: str(row["fiscal_year_end"]), reverse=True)
        return output, self._finalize_v2_status(status, len(output))

    def key_metrics_annual(self, symbol: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Up to ``limit`` fiscal years of per-share/return metrics (ROIC,
        market cap, revenue and FCF per share) complementing ratios_annual
        for the own-history anchor. [] on any failure."""
        rows, _status = self._key_metrics_annual_result(symbol, limit=limit)
        return rows

    def _key_metrics_annual_result(
        self, symbol: str, *, limit: int = 10,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows, status = self._valuation_v2_rows(
            "key-metrics",
            {
                "symbol": symbol,
                "period": "annual",
                "limit": max(1, min(limit, 20)),
                "apikey": self.token,
            },
        )
        output: list[dict[str, Any]] = []
        for row in rows:
            fiscal_end = self._valid_date(row.get("date"))
            if fiscal_end is None:
                continue
            output.append({
                "fiscal_year_end": fiscal_end.isoformat(),
                "market_cap": number(row.get("marketCap")),
                "enterprise_value": number(row.get("enterpriseValue")),
                "roic": _first_number(row.get("returnOnInvestedCapital"), row.get("roic")),
                "revenue_per_share": number(row.get("revenuePerShare")),
                "fcf_per_share": number(row.get("freeCashFlowPerShare")),
                "eps": number(row.get("netIncomePerShare")),
            })
        output.sort(key=lambda row: str(row["fiscal_year_end"]), reverse=True)
        return output, self._finalize_v2_status(status, len(output))

    def valuation_v2_packet(self, symbol: str) -> dict[str, Any]:
        """The complete per-symbol V2.1 data packet: real peers, forward
        estimates per fiscal year, and ten years of own-history ratios and
        key metrics. Every section degrades to []/None independently."""
        peers, peers_status = self._stock_peers_result(symbol)
        estimates, estimates_status = self._analyst_estimates_annual_result(symbol)
        ratios, ratios_status = self._ratios_annual_result(symbol)
        metrics, metrics_status = self._key_metrics_annual_result(symbol)
        return {
            "symbol": symbol.strip().upper(),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "peers": peers,
            "analyst_estimates_annual": estimates,
            "ratios_annual": ratios,
            "key_metrics_annual": metrics,
            "provider_status": {
                "peers": peers_status,
                "analyst_estimates": estimates_status,
                "ratios": ratios_status,
                "key_metrics": metrics_status,
            },
        }

    def valuation_v2_batch(
        self, symbols: list[str], *, workers: int = 10,
    ) -> dict[str, dict[str, Any]]:
        """valuation_v2_packet() for many symbols in parallel -- mirrors
        consensus_batch()'s pattern for the nightly cycle."""
        clean_symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
        if not clean_symbols:
            return {}

        def fetch(symbol: str) -> tuple[str, dict[str, Any]]:
            return symbol, self.valuation_v2_packet(symbol)

        output: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 20))) as executor:
            for symbol, result in executor.map(fetch, clean_symbols):
                output[symbol] = result
        return output

    def _valuation_v2_rows(
        self, endpoint: str, params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Fetch one V2 endpoint without exposing request URLs or API keys.

        Public list-returning helpers keep their existing fallback contract,
        while the packet records whether an empty list was a real empty
        response, an invalid payload, or a provider failure.
        """
        try:
            payload = self.http.get_json(
                f"{self.base_url}/stable/{endpoint}", params=params,
            )
        except Exception as exc:
            return [], {
                "status": "error",
                "error_type": type(exc).__name__,
                "raw_rows": 0,
                "parsed_rows": 0,
            }
        if not isinstance(payload, list):
            return [], {
                "status": "invalid_payload",
                "error_type": None,
                "raw_rows": 0,
                "parsed_rows": 0,
            }
        rows = [row for row in payload if isinstance(row, dict)]
        return rows, {
            "status": "ok" if payload else "empty",
            "error_type": None,
            "raw_rows": len(payload),
            "parsed_rows": 0,
        }

    @staticmethod
    def _finalize_v2_status(status: dict[str, Any], parsed_rows: int) -> dict[str, Any]:
        result = {**status, "parsed_rows": parsed_rows}
        if result.get("status") == "ok" and parsed_rows == 0:
            result["status"] = "empty"
        return result

    @staticmethod
    def _peer_item(
        symbol: str,
        *,
        source_symbol: str,
        company_name: str = "",
        price: float | None = None,
        market_cap: float | None = None,
    ) -> dict[str, Any]:
        peer_symbol = symbol.strip().upper()
        canonical = (
            peer_symbol.removesuffix(".SA")
            if source_symbol.endswith(".SA") and peer_symbol.endswith(".SA")
            else peer_symbol
        )
        return {
            "symbol": peer_symbol,
            "canonical_symbol": canonical,
            "company_name": company_name,
            "price": price,
            "market_cap": market_cap,
        }

    @staticmethod
    def _first_row(payload: Any) -> dict[str, Any] | None:
        rows = payload if isinstance(payload, list) else []
        return rows[0] if rows and isinstance(rows[0], dict) else None

    @staticmethod
    def _valid_date(value: Any) -> date | None:
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None
