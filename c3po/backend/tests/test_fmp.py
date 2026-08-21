from datetime import date

from app.market_data.fmp import FmpClient


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append((url, params))
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_price_target_consensus_parses_the_documented_response_shape():
    http = FakeHttp([
        {"symbol": "JPM", "targetHigh": 420.0, "targetLow": 305.0, "targetConsensus": 373.64, "targetMedian": 370.0},
    ])
    fmp = FmpClient("https://financialmodelingprep.com", "test-token", http)

    result = fmp.price_target_consensus("JPM")

    assert result == {"consensus": 373.64, "median": 370.0, "high": 420.0, "low": 305.0}
    url, params = http.calls[0]
    assert url == "https://financialmodelingprep.com/stable/price-target-consensus"
    assert params == {"symbol": "JPM", "apikey": "test-token"}


def test_price_target_consensus_returns_none_on_empty_or_failed_response():
    assert FmpClient("https://x", "t", FakeHttp([])).price_target_consensus("JPM") is None
    assert FmpClient("https://x", "t", FakeHttp(RuntimeError("boom"))).price_target_consensus("JPM") is None


def test_batch_quotes_chunks_requests_and_normalizes_live_fields():
    class BatchHttp:
        def __init__(self):
            self.calls = []

        def get_json(self, url, *, params=None, headers=None):
            self.calls.append((url, params))
            return [{
                "symbol": symbol, "price": 100 + index, "volume": 1_000 + index,
                "avgVolume": 2_000 + index, "changePercentage": 0.5, "timestamp": 1_787_000_000,
            } for index, symbol in enumerate(params["symbols"].split(","))]

    http = BatchHttp()
    result = FmpClient("https://financialmodelingprep.com", "token", http).batch_quotes(
        ["AAPL", "MSFT", "JPM"], chunk_size=2, workers=1,
    )

    assert set(result) == {"AAPL", "MSFT", "JPM"}
    assert result["AAPL"]["price"] == 100.0
    assert result["MSFT"]["average_volume"] == 2001.0
    assert len(http.calls) == 2
    assert all(call[0].endswith("/stable/batch-quote") for call in http.calls)


def test_batch_quotes_isolates_failed_chunks():
    class PartialHttp:
        def get_json(self, url, *, params=None, headers=None):
            if "JPM" in params["symbols"]:
                raise RuntimeError("temporary FMP failure")
            return [{"symbol": "AAPL", "price": 200, "timestamp": 1_787_000_000}]

    diagnostics = {}
    result = FmpClient("https://x", "t", PartialHttp()).batch_quotes(
        ["AAPL", "JPM"], chunk_size=1, workers=1, diagnostics=diagnostics,
    )

    assert set(result) == {"AAPL"}
    assert diagnostics["failed_chunk_count"] == 1
    assert diagnostics["failed_symbols"] == ["JPM"]
    assert diagnostics["successful_symbols"] == ["AAPL"]
    assert diagnostics["failure_types"] == ["RuntimeError"]


def test_price_target_summary_parses_recency_scoped_counts():
    http = FakeHttp([
        {
            "symbol": "JPM", "lastMonthCount": 3, "lastMonthAvgPriceTarget": 388.33,
            "lastQuarterCount": 12, "lastQuarterAvgPriceTarget": 380.1,
        },
    ])
    fmp = FmpClient("https://financialmodelingprep.com", "test-token", http)

    result = fmp.price_target_summary("JPM")

    assert result == {
        "last_month_count": 3, "last_month_avg": 388.33,
        "last_quarter_count": 12, "last_quarter_avg": 380.1,
    }


def test_recent_grades_normalizes_broker_level_rows_and_filters_by_since():
    http = FakeHttp([
        {"symbol": "JPM", "date": "2026-08-14", "gradingCompany": "Wells Fargo", "previousGrade": "Equal-Weight", "newGrade": "Overweight", "action": "upgrade"},
        {"symbol": "JPM", "date": "2020-01-02", "gradingCompany": "UBS", "previousGrade": "Buy", "newGrade": "Buy", "action": "maintain"},
        {"symbol": "JPM", "date": "not-a-date", "gradingCompany": "Bad Row"},
    ])
    fmp = FmpClient("https://financialmodelingprep.com", "test-token", http)

    recent = fmp.recent_grades("JPM", since=date(2026, 1, 1))

    assert recent == [{
        "date": date(2026, 8, 14), "grading_company": "Wells Fargo",
        "previous_grade": "Equal-Weight", "new_grade": "Overweight", "action": "upgrade",
    }]


def test_recent_grades_returns_empty_list_on_failure_rather_than_raising():
    fmp = FmpClient("https://x", "t", FakeHttp(RuntimeError("boom")))
    assert fmp.recent_grades("JPM") == []


class FakeHttpPerSymbol:
    """Routes by the request's `symbol` param -- consensus_batch needs one
    fake response per symbol, unlike FakeHttp's single fixed payload."""

    def __init__(self, by_symbol):
        self.by_symbol = by_symbol

    def get_json(self, url, *, params=None, headers=None):
        symbol = (params or {}).get("symbol")
        payload = self.by_symbol.get(symbol)
        if isinstance(payload, Exception):
            raise payload
        return payload


def test_consensus_batch_fetches_both_endpoints_per_symbol_in_parallel():
    http = FakeHttpPerSymbol({
        "JPM": [{"symbol": "JPM", "targetHigh": 420.0, "targetLow": 305.0, "targetConsensus": 373.64, "targetMedian": 370.0}],
        "AAPL": RuntimeError("boom"),
    })
    fmp = FmpClient("https://financialmodelingprep.com", "test-token", http)

    result = fmp.consensus_batch(["JPM", "AAPL", "jpm"])

    assert set(result.keys()) == {"JPM", "AAPL"}  # de-duplicated case-insensitively
    consensus, summary = result["JPM"]
    assert consensus == {"consensus": 373.64, "median": 370.0, "high": 420.0, "low": 305.0}
    assert summary == {"last_month_count": 0, "last_month_avg": None, "last_quarter_count": 0, "last_quarter_avg": None}
    assert result["AAPL"] == (None, None)  # one symbol failing never breaks the batch


def test_institutional_positions_parses_the_documented_response_shape():
    http = FakeHttp([{
        "symbol": "AAPL", "cik": "0000320193", "date": "2023-09-30",
        "investorsHolding": 4863, "lastInvestorsHolding": 4805, "investorsHoldingChange": 58,
        "numberOf13Fshares": 9139920744, "numberOf13FsharesChange": -221018965,
        "newPositions": 162, "increasedPositions": 1941, "closedPositions": 158, "reducedPositions": 2408,
    }])
    fmp = FmpClient("https://financialmodelingprep.com", "test-token", http)

    result = fmp.institutional_positions("AAPL", year=2023, quarter=3)

    assert result == {
        "investors_holding": 4863, "investors_holding_change": 58,
        "shares": 9139920744.0, "shares_change": -221018965.0,
        "new_positions": 162, "increased_positions": 1941,
        "reduced_positions": 2408, "closed_positions": 158,
    }
    url, params = http.calls[0]
    assert url == "https://financialmodelingprep.com/stable/institutional-ownership/symbol-positions-summary"
    assert params == {"symbol": "AAPL", "year": 2023, "quarter": 3, "apikey": "test-token"}


def test_institutional_positions_returns_none_on_empty_or_failed_response():
    assert FmpClient("https://x", "t", FakeHttp([])).institutional_positions("AAPL", year=2023, quarter=3) is None
    assert FmpClient("https://x", "t", FakeHttp(RuntimeError("boom"))).institutional_positions("AAPL", year=2023, quarter=3) is None


def test_latest_reportable_13f_quarter_waits_out_the_filing_deadline():
    """13F filings are due 45 days after quarter-end. A request made right
    at that edge should NOT get back a mostly-unfiled quarter -- it should
    fall back to the prior one, whose deadline has cleared with margin."""
    # Q2 2026 ends 2026-06-30; deadline+buffer is 2026-08-19.
    assert FmpClient.latest_reportable_13f_quarter(date(2026, 8, 18)) == (2026, 1)
    assert FmpClient.latest_reportable_13f_quarter(date(2026, 8, 20)) == (2026, 2)
    assert FmpClient.latest_reportable_13f_quarter(date(2026, 1, 1)) == (2025, 3)


def test_institutional_positions_batch_isolates_per_symbol_failures():
    http = FakeHttpPerSymbol({
        "AAPL": [{
            "symbol": "AAPL", "investorsHolding": 4863, "newPositions": 162,
            "increasedPositions": 1941, "closedPositions": 158, "reducedPositions": 2408,
        }],
        "JPM": RuntimeError("boom"),
    })
    fmp = FmpClient("https://financialmodelingprep.com", "test-token", http)

    result = fmp.institutional_positions_batch(["AAPL", "JPM"], year=2026, quarter=2)

    assert result["AAPL"]["investors_holding"] == 4863
    assert result["JPM"] is None


def test_recent_grades_batch_isolates_per_symbol_failures():
    http = FakeHttpPerSymbol({
        "AAPL": [{"symbol": "AAPL", "date": "2026-07-20", "gradingCompany": "Jefferies", "previousGrade": "Hold", "newGrade": "Buy", "action": "upgrade"}],
        "JPM": RuntimeError("boom"),
    })
    fmp = FmpClient("https://financialmodelingprep.com", "test-token", http)

    result = fmp.recent_grades_batch(["AAPL", "JPM"])

    assert len(result["AAPL"]) == 1
    assert result["AAPL"][0]["grading_company"] == "Jefferies"
    assert result["JPM"] == []
