from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any

from .http import JsonHttpClient
from .models import number


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

        def fetch(chunk: list[str]) -> list[dict[str, Any]]:
            try:
                payload = self.http.get_json(
                    f"{self.base_url}/stable/batch-quote",
                    params={"symbols": ",".join(chunk), "apikey": self.token},
                )
            except Exception:
                return []
            return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []

        output: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(chunks), 10))) as executor:
            for rows in executor.map(fetch, chunks):
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
