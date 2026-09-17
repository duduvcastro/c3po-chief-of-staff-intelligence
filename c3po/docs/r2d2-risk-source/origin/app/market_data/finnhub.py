from datetime import date, datetime, timezone
from typing import Any, Protocol


class HttpGetClient(Protocol):
    def get(self, url: str, *, params: dict[str, Any] | None = None) -> Any: ...


class FinnhubClient:
    """Fundamental-1 plan (US market only, $50/month): insider transactions,
    news sentiment, and company news. Response shapes for insider_transactions
    were verified against the real API after this shipped (2026-08-19,
    confirmed matching); company_news/news_sentiment are unverified the same
    way -- best-effort/defensive parsing for the same reason.
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

    def news_sentiment(self, symbol: str) -> dict[str, Any] | None:
        """Aggregate news-buzz/sentiment snapshot for ``symbol``. Returns None
        (not []) on any missing/unexpected field or empty payload, since this
        is a single object, not a list -- callers treat None as "nothing to
        report this cycle," never as an error.
        """
        response = self.client.get(
            f"{self.base_url}/api/v1/news-sentiment", params={"symbol": symbol, "token": self.token},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return None
        sentiment = payload.get("sentiment") if isinstance(payload.get("sentiment"), dict) else {}
        buzz = payload.get("buzz") if isinstance(payload.get("buzz"), dict) else {}
        try:
            bullish = float(sentiment.get("bullishPercent"))
            bearish = float(sentiment.get("bearishPercent"))
        except (TypeError, ValueError):
            return None
        try:
            articles_last_week = int(buzz.get("articlesInLastWeek") or 0)
        except (TypeError, ValueError):
            articles_last_week = 0
        return {
            "bullish_percent": round(bullish * 100, 1) if bullish <= 1 else round(bullish, 1),
            "bearish_percent": round(bearish * 100, 1) if bearish <= 1 else round(bearish, 1),
            "articles_last_week": articles_last_week,
            "company_news_score": payload.get("companyNewsScore"),
        }

    def company_news(self, symbol: str, *, since: date, until: date) -> list[dict[str, Any]]:
        """Recent news articles mentioning ``symbol``. Returns [] on any
        missing/unexpected field rather than raising, same defensive
        contract as insider_transactions -- one bad article must never break
        the whole sync.
        """
        response = self.client.get(
            f"{self.base_url}/api/v1/company-news",
            params={"symbol": symbol, "from": since.isoformat(), "to": until.isoformat(), "token": self.token},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return []
        articles = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            article = self._normalize_article(row)
            if article:
                articles.append(article)
        return articles

    @staticmethod
    def _normalize_article(row: dict[str, Any]) -> dict[str, Any] | None:
        headline = str(row.get("headline") or "").strip()
        article_id = row.get("id")
        timestamp = row.get("datetime")
        if not headline or article_id is None or not timestamp:
            return None
        try:
            published_at = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
        return {
            "article_id": str(article_id),
            "headline": headline,
            "summary": str(row.get("summary") or ""),
            "source": str(row.get("source") or ""),
            "url": str(row.get("url") or "") or None,
            "published_at": published_at,
        }

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
