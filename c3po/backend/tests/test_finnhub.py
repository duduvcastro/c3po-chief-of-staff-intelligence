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
