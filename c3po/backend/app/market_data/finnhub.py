from datetime import date
from typing import Any, Protocol


class HttpGetClient(Protocol):
    def get(self, url: str, *, params: dict[str, Any] | None = None) -> Any: ...


class FinnhubClient:
    """Fundamental-1 plan (US market only, $50/month) -- insider transactions
    for now; company news / news sentiment are a natural follow-up once this
    is confirmed working against the real API (no key available to verify
    response shapes live while writing this, unlike the EDGAR integration).
    Takes any httpx.Client-shaped object (get() -> response with
    raise_for_status()/json()), matching investor_relations.py's existing
    self.client rather than market_data's separate JsonHttpClient wrapper.
    """

    code = "finnhub"
    name = "Finnhub"

    def __init__(self, base_url: str, token: str, client: HttpGetClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = client

    def insider_transactions(self, symbol: str, *, since: date | None = None) -> list[dict[str, Any]]:
        """Recent Form 3/4/5-derived insider buy/sell activity for ``symbol``.
        Returns [] on any missing/unexpected field rather than raising --
        callers must never let one bad row break the whole enrichment pass.
        """
        params: dict[str, Any] = {"symbol": symbol, "token": self.token}
        if since:
            params["from"] = since.isoformat()
        response = self.client.get(f"{self.base_url}/api/v1/stock/insider-transactions", params=params)
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        transactions = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            transaction = self._normalize_transaction(row)
            if transaction:
                transactions.append(transaction)
        return transactions

    @staticmethod
    def _normalize_transaction(row: dict[str, Any]) -> dict[str, Any] | None:
        name = str(row.get("name") or "").strip()
        code = str(row.get("transactionCode") or "").strip().upper()
        transaction_date = row.get("transactionDate")
        if not name or not code or not transaction_date:
            return None
        try:
            share_change = float(row.get("change") or 0)
        except (TypeError, ValueError):
            share_change = 0.0
        try:
            price = float(row.get("transactionPrice") or 0) or None
        except (TypeError, ValueError):
            price = None
        return {
            "insider_name": name,
            "transaction_code": code,
            "is_purchase": code == "P",
            "is_sale": code == "S",
            "share_change": share_change,
            "shares_held_after": row.get("share"),
            "price": price,
            "transaction_date": str(transaction_date),
            "filing_date": str(row.get("filingDate") or transaction_date),
        }
