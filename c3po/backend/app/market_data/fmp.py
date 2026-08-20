from datetime import date, datetime
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
