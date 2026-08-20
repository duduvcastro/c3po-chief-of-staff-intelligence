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
