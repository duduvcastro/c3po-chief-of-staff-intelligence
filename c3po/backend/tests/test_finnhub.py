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


def test_the_news_methods_left_with_the_contract():
    # owner 03/11/2026: Finnhub is cut. The weekly news sentiment comes from Massive's article insights
    # (investor_relations.sync_massive_news); only the insider reader stays, which the blank token keeps from being called
    assert not hasattr(FinnhubClient, "news_sentiment") and not hasattr(FinnhubClient, "company_news")
    assert callable(FinnhubClient.insider_transactions)


def test_finnhub_is_switched_off_in_every_backend_service(monkeypatch):
    """Finnhub is cancelled (owner 03/11/2026). Every service built from the backend image reads Settings, and each one
    blanks the PREFIXED token in its own ``environment:``, as FMP's: compose's environment beats ``../.env`` (env_file), the
    prefixed alias beats the legacy ``FINNHUB_API_TOKEN`` in config.py (frozen), and an empty value is kept, not skipped.
    With it blank the insider step reads EODHD's Form 4 and the news sentiment comes from Massive."""
    from pathlib import Path

    import yaml

    from app.config import Settings

    root = Path(__file__).resolve().parents[2]
    services = yaml.safe_load((root / "compose.yml").read_text(encoding="utf-8"))["services"]
    backend = {name for name, service in services.items() if service.get("image") == "c3po/backend:production"}
    assert backend == {"api", "investor-relations-worker", "valuation-worker", "server-usage-worker", "r2d2-live"}
    for name in sorted(backend):
        assert services[name]["environment"]["C3PO_FINNHUB_API_TOKEN"] == "", name
    monkeypatch.setenv("FINNHUB_API_TOKEN", "a-token-still-in-the-env-file")
    monkeypatch.setenv("C3PO_FINNHUB_API_TOKEN", "")
    assert Settings().finnhub_api_token == ""
    monkeypatch.delenv("C3PO_FINNHUB_API_TOKEN")
    assert Settings().finnhub_api_token == "a-token-still-in-the-env-file"  # what the blank prevents
    assert "FINNHUB" not in (root / ".env.example").read_text(encoding="utf-8")


def test_with_the_token_blank_the_insider_step_reads_eodhd_and_never_finnhub(tmp_path):
    """The insider Form 4 of a US name keeps coming, from EODHD (source_code still "sec"), once Finnhub's token is blank."""
    from datetime import timedelta

    from app.config import Settings
    from app.database import Database
    from app.investor_relations import InvestorRelationsService

    settings = Settings(database_url="", migrations_dir=tmp_path, investor_relations_output_dir=tmp_path / "ir-pdf",
                        finnhub_api_token="", eodhd_api_token="test-token")
    ir = InvestorRelationsService(settings, Database(settings))
    recent = (date.today() - timedelta(days=5)).isoformat()

    class NeverCalled:
        def get(self, *args, **kwargs):
            raise AssertionError("Finnhub must not be called with its token blank")

    class EodhdForm4:
        def get_json(self, url, *, params=None, headers=None):
            return {"data": [{"accession_number": "acc-1", "filed_at": recent, "period_of_report": recent,
                              "non_derivative": [{"reporting_owner_name": "COOK TIMOTHY D", "transaction_code": "S",
                                                  "acquired_or_disposed": "D", "shares_amount": 1000, "price_per_share": 227.5,
                                                  "shares_owned_after": 511000, "transaction_date": f"{recent}T00:00:00+00:00"}],
                              "derivative": [], "footnotes": []}], "meta": {}, "links": {"next": None}}

    ir.finnhub.client = NeverCalled()
    ir.eodhd.http = EodhdForm4()
    events = ir._finnhub_insider_events("AAPL", "0000320193", None, "Apple Inc.") or ir._eodhd_insider_events(
        "AAPL", "0000320193", None, "Apple Inc.")

    assert [event["source_code"] for event in events] == ["sec"] and events[0]["external_id"].startswith("eodhd-insider-AAPL-")
