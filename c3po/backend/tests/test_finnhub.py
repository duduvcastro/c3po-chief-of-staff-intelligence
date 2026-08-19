from datetime import date

from app.market_data.finnhub import FinnhubClient


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, *, params=None):
        self.calls.append((url, params))
        return FakeResponse(self.payload)


def test_insider_transactions_normalizes_purchase_and_sale_rows():
    payload = {
        "symbol": "AAPL",
        "data": [
            {
                "name": "COOK TIMOTHY D", "share": 511000, "change": -223986,
                "filingDate": "2026-08-15", "transactionDate": "2026-08-13",
                "transactionCode": "S", "transactionPrice": 227.5, "symbol": "AAPL",
            },
            {
                "name": "JANE DOE", "share": 10000, "change": 5000,
                "filingDate": "2026-08-10", "transactionDate": "2026-08-09",
                "transactionCode": "P", "transactionPrice": 210.0, "symbol": "AAPL",
            },
        ],
    }
    client = FakeClient(payload)
    finnhub = FinnhubClient("https://finnhub.io", "test-token", client)

    transactions = finnhub.insider_transactions("AAPL", since=date(2026, 7, 1))

    assert len(transactions) == 2
    sale, purchase = transactions
    assert sale == {
        "insider_name": "COOK TIMOTHY D", "transaction_code": "S", "is_purchase": False,
        "is_sale": True, "share_change": -223986.0, "shares_held_after": 511000,
        "price": 227.5, "transaction_date": "2026-08-13", "filing_date": "2026-08-15",
    }
    assert purchase["is_purchase"] is True
    assert purchase["is_sale"] is False

    call_url, call_params = client.calls[0]
    assert call_url == "https://finnhub.io/api/v1/stock/insider-transactions"
    assert call_params == {"symbol": "AAPL", "token": "test-token", "from": "2026-07-01"}


def test_insider_transactions_skips_rows_missing_required_fields():
    payload = {"data": [
        {"name": "", "transactionCode": "S", "transactionDate": "2026-08-13"},
        {"name": "JOHN SMITH", "transactionCode": "", "transactionDate": "2026-08-13"},
        {"name": "JOHN SMITH", "transactionCode": "S", "transactionDate": None},
        "not-a-dict",
    ]}
    finnhub = FinnhubClient("https://finnhub.io", "test-token", FakeClient(payload))

    assert finnhub.insider_transactions("AAPL") == []


def test_insider_transactions_handles_unexpected_response_shape():
    finnhub = FinnhubClient("https://finnhub.io", "test-token", FakeClient({"data": "not-a-list"}))
    assert finnhub.insider_transactions("AAPL") == []

    finnhub_no_data = FinnhubClient("https://finnhub.io", "test-token", FakeClient(["unexpected", "list"]))
    assert finnhub_no_data.insider_transactions("AAPL") == []


def test_news_sentiment_normalizes_fractional_percentages():
    payload = {
        "symbol": "AAPL",
        "sentiment": {"bullishPercent": 0.68, "bearishPercent": 0.32},
        "buzz": {"articlesInLastWeek": 34, "buzz": 1.1, "weeklyAverage": 30},
        "companyNewsScore": 0.71,
    }
    finnhub = FinnhubClient("https://finnhub.io", "test-token", FakeClient(payload))

    sentiment = finnhub.news_sentiment("AAPL")

    assert sentiment == {
        "bullish_percent": 68.0, "bearish_percent": 32.0,
        "articles_last_week": 34, "company_news_score": 0.71,
    }


def test_news_sentiment_returns_none_on_missing_or_malformed_fields():
    assert FinnhubClient("https://finnhub.io", "t", FakeClient({})).news_sentiment("AAPL") is None
    assert FinnhubClient("https://finnhub.io", "t", FakeClient({"sentiment": {}})).news_sentiment("AAPL") is None
    assert FinnhubClient("https://finnhub.io", "t", FakeClient(["not", "a", "dict"])).news_sentiment("AAPL") is None


def test_company_news_normalizes_articles_and_skips_incomplete_rows():
    payload = [
        {
            "id": 123, "headline": "Apple announces new guidance", "summary": "Details here.",
            "source": "Reuters", "url": "https://example.com/1", "datetime": 1755556800,
        },
        {"id": None, "headline": "Missing id", "datetime": 1755556800},
        {"id": 456, "headline": "", "datetime": 1755556800},
        {"id": 789, "headline": "No timestamp"},
        "not-a-dict",
    ]
    finnhub = FinnhubClient("https://finnhub.io", "test-token", FakeClient(payload))

    articles = finnhub.company_news("AAPL", since=date(2026, 8, 1), until=date(2026, 8, 19))

    assert len(articles) == 1
    assert articles[0]["article_id"] == "123"
    assert articles[0]["headline"] == "Apple announces new guidance"
    assert articles[0]["published_at"].year == 2025


def test_company_news_handles_unexpected_response_shape():
    finnhub = FinnhubClient("https://finnhub.io", "test-token", FakeClient({"not": "a-list"}))
    assert finnhub.company_news("AAPL", since=date(2026, 8, 1), until=date(2026, 8, 19)) == []
