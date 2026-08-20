from datetime import date

from app.market_data.eodhd import EodhdClient


class SequenceHttp:
    """Returns responses/raises in call order, for pagination tests."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append({"url": url, "params": params})
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def form4_filing(filed_at, *, non_derivative=None):
    return {
        "accession_number": f"acc-{filed_at}",
        "filed_at": filed_at,
        "period_of_report": filed_at,
        "non_derivative": non_derivative or [],
        "derivative": [],
        "footnotes": [],
    }


def form4_row(**overrides):
    row = {
        "reporting_owner_cik": "0001771340",
        "reporting_owner_name": "Taneja Vaibhav",
        "security_title": "Common Stock",
        "transaction_date": "2026-05-13T00:00:00+00:00",
        "transaction_code": "S",
        "acquired_or_disposed": "D",
        "shares_amount": 3000,
        "price_per_share": 450,
        "shares_owned_after": 18106.5,
    }
    row.update(overrides)
    return row


def test_insider_transactions_normalizes_the_documented_response_shape():
    http = SequenceHttp([
        {
            "data": [form4_filing("2026-05-15", non_derivative=[form4_row()])],
            "meta": {"total": 1, "page": {"offset": 0, "limit": 100}},
            "links": {"next": None},
        },
    ])
    client = EodhdClient("https://eodhd.com", "secret", http)

    transactions = client.insider_transactions("AAPL")

    assert transactions == [{
        "insider_name": "Taneja Vaibhav", "transaction_code": "S",
        "is_purchase": False, "is_sale": True, "share_change": -3000.0,
        "shares_held_after": 18106.5, "price": 450.0,
        "transaction_date": "2026-05-13", "filing_date": "2026-05-15",
    }]
    assert http.calls[0]["url"] == "https://eodhd.com/api/sec-filings/AAPL.US/form4"
    assert http.calls[0]["params"] == {"api_token": "secret", "page[offset]": 0, "page[limit]": 100}


def test_insider_transactions_marks_acquisitions_as_purchases_with_positive_share_change():
    http = SequenceHttp([{
        "data": [form4_filing("2026-05-15", non_derivative=[
            form4_row(transaction_code="P", acquired_or_disposed="A", shares_amount=1000),
        ])],
        "meta": {"total": 1, "page": {"offset": 0, "limit": 100}},
        "links": {"next": None},
    }])
    client = EodhdClient("https://eodhd.com", "secret", http)

    transactions = client.insider_transactions("AAPL")

    assert transactions[0]["is_purchase"] is True
    assert transactions[0]["is_sale"] is False
    assert transactions[0]["share_change"] == 1000.0


def test_insider_transactions_paginates_until_a_short_page_or_since_cutoff():
    full_page = [form4_filing(f"2026-05-{15 - i:02d}", non_derivative=[form4_row()]) for i in range(100)]
    http = SequenceHttp([
        {"data": full_page, "meta": {}, "links": {"next": "..."}},
        {"data": [form4_filing("2026-01-01", non_derivative=[form4_row()])], "meta": {}, "links": {"next": None}},
    ])
    client = EodhdClient("https://eodhd.com", "secret", http)

    transactions = client.insider_transactions("AAPL", since=date(2026, 3, 1))

    # 100 from the first (full) page + 0 from the second (filed before the cutoff)
    assert len(transactions) == 100
    assert len(http.calls) == 2
    assert http.calls[1]["params"]["page[offset]"] == 100


def test_insider_transactions_returns_empty_list_without_a_token_or_on_failure():
    assert EodhdClient("https://eodhd.com", "", SequenceHttp([])).insider_transactions("AAPL") == []
    assert EodhdClient("https://eodhd.com", "secret", SequenceHttp([RuntimeError("boom")])).insider_transactions("AAPL") == []
