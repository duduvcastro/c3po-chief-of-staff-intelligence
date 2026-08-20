from app.market_data.brapi import BrapiClient


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_treasury_rates_parses_the_documented_response_shape():
    http = FakeHttp({
        "results": [{
            "symbol": "tesouro-prefixado-com-juros-semestrais-01012037",
            "bondType": "Tesouro Prefixado com Juros Semestrais",
            "indexer": "prefixado",
            "couponType": "semestral",
            "maturityDate": "2037-01-01",
            "durationDays": 4000,
            "baseDate": "2026-05-15",
            "buyRate": 0.132,
            "sellRate": 0.135,
            "buyPrice": 950.0,
            "sellPrice": 945.0,
            "basePrice": 945.0,
            "rateInfo": {"rateType": "nominal", "rateUnit": "% a.a."},
        }],
        "requestedAt": "2026-08-20T12:00:00.000Z",
        "took": 12,
    })
    client = BrapiClient("https://brapi.dev", "test-token", http)

    result = client.treasury_rates()

    assert result == [{
        "symbol": "tesouro-prefixado-com-juros-semestrais-01012037",
        "bond_type": "Tesouro Prefixado com Juros Semestrais",
        "indexer": "prefixado",
        "maturity_date": "2037-01-01",
        "duration_days": 4000,
        "buy_rate": 0.132,
        "sell_rate": 0.135,
    }]
    call = http.calls[0]
    assert call["url"] == "https://brapi.dev/api/v2/treasury/list"
    assert call["params"] == {"indexer": "prefixado", "sortBy": "maturityDate", "sortOrder": "desc", "limit": 20}
    assert call["headers"] == {"Authorization": "Bearer test-token"}


def test_treasury_rates_skips_rows_without_any_usable_rate():
    http = FakeHttp({"results": [{"symbol": "no-rate-bond"}]})
    client = BrapiClient("https://brapi.dev", "test-token", http)

    assert client.treasury_rates() == []


def test_treasury_rates_returns_empty_list_on_failure_or_bad_shape():
    assert BrapiClient("https://brapi.dev", "t", FakeHttp(RuntimeError("boom"))).treasury_rates() == []
    assert BrapiClient("https://brapi.dev", "t", FakeHttp({"results": "not-a-list"})).treasury_rates() == []
    assert BrapiClient("https://brapi.dev", "t", FakeHttp([])).treasury_rates() == []
