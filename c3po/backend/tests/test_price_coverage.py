from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.database import Database
from app.price_coverage import POLICY, PriceCoverageCatalog, digest, select_catalog
from app.valuation_price_history import ANALYSIS_TYPE, PriceHistoryService


def listing(symbol, kind="Common Stock", venue="NASDAQ", currency="USD", isin=None):
    return {"Code": symbol, "Type": kind, "Exchange": venue, "Currency": currency, "Isin": isin}


def b3(symbol, subtype="stock", asset="stock", active=True):
    return {"symbol": symbol, "assetType": asset, "subType": subtype, "exchange": "B3", "currency": "BRL", "isActive": active}


def test_us_full_catalog_includes_illiquid_and_preferred_and_all_family_etfs():
    rows = [listing("TINY"), listing("PREF", "Preferred Stock"), listing("FUND", "FUND"),
            listing("ETF", "ETF"), listing("UNIT", "Unit"), listing("W", "Warrant"), listing("N", "Notes"),
            listing("ARCA", "ETF", "NYSE ARCA"), listing("AMEX", venue="AMEX"), listing("BATS", "ETF", "BATS"),
            listing("OTC", venue="OTCQX"), listing("BRK.B", venue="NYSE"), listing("BAD/USD"),
            listing("EUR", currency="EUR"), listing("UNKNOWN", kind=None)]
    nasdaq = select_catalog("NASDAQ", rows)
    assert set(nasdaq["selected"]) == {"TINY", "PREF", "ETF"}
    assert set(select_catalog("NYSE", rows)["selected"]) == {"ARCA", "AMEX", "BRK.B"}
    assert nasdaq["excluded"]["BAD/USD"] == "invalid_symbol"
    assert nasdaq["excluded"]["EUR"] == "non_usd_currency"
    assert nasdaq["policy"] == POLICY
    assert select_catalog("NASDAQ", list(reversed(rows))) == nasdaq


def test_b3_taxonomy_excludes_bdr_fii_and_fractional_without_suffix_type_guess():
    raw = [listing("PETR4", venue="SA", currency="BRL"),
           listing("BDRX34", venue="SA", currency="BRL"),
           listing("ONLY3", venue="SA", currency="BRL", isin="BRONLYACNOR1"),
           listing("EUR11", kind="ETF", venue="SA", currency="EUR")]
    taxonomy = [b3("PETR4"), b3("PETR4F"), b3("UNIT11", "unit"), b3("ETF11", "etf", "fund"),
                b3("FII11", "fii", "fund"), b3("BDRX34", "bdr", "bdr"), b3("OFF3", active=False),
                b3("EUR11", "etf", "fund")]
    result = select_catalog("B3", raw, taxonomy)
    assert set(result["selected"]) == {"PETR4", "UNIT11", "ETF11", "ONLY3"}
    assert result["selected"]["ETF11"]["provider_listed"] is False  # try it; do not hide this lack of provider coverage
    assert result["excluded"]["EUR11"] == "provider_currency_conflict"
    assert result["excluded"]["PETR4F"] == "fractional_alias"
    assert result["excluded"]["BDRX34"] == "excluded_instrument_type"


def test_conflicting_identity_never_uses_first_row():
    rows = [listing("A"), listing("A", kind="ETF")]
    for ordered in (rows, list(reversed(rows))):
        with pytest.raises(ValueError, match="conflicting"):
            select_catalog("NASDAQ", ordered)
    with pytest.raises(ValueError, match="conflicting"):
        select_catalog("B3", [], [b3("A3"), b3("A3", "bdr", "bdr")])
    with pytest.raises(ValueError, match="BDR ISIN"):
        select_catalog("B3", [listing("A3", venue="SA", currency="BRL", isin="BRAAAABDR007")], [b3("A3")])


class Http:
    max_retries = 2

    def __init__(self):
        self.rows = [listing("A"), listing("WIDE"), listing("ETF", "ETF")]
        self.pages = [[b3("A3")], [b3("ETF11", "etf", "fund")]]
        self.calls = []
        self.account = {"dailyRateLimit": 400000, "apiRequests": 40000, "extraLimit": 999999,
                        "apiRequestsDate": datetime.now(timezone.utc).date().isoformat()}
        self.fail = False

    def get_json(self, url, *, params=None, **kwargs):
        self.calls.append((url, params))
        if self.fail:
            raise RuntimeError("secret_token_must_never_escape")
        if url.endswith("/user"):
            return self.account
        if "/exchange-symbol-list/" in url:
            return self.rows
        if "/tickers" in url:
            page = params["page"]
            return {"results": self.pages[page - 1], "pagination": {"page": page, "totalItems": 2, "hasNextPage": page < 2}}
        return [{"date": "2026-09-04", "close": 100.0, "adjusted_close": 90.0, "volume": 100}]


def test_brapi_pagination_complete_not_first_page_and_inconsistent_total_refused():
    http = Http()
    catalog = PriceCoverageCatalog(Settings(eodhd_api_token="test"), http)
    assert [r["symbol"] for r in catalog._brapi()] == ["A3", "ETF11"]
    http.pages[1] = [b3("A3")]
    with pytest.raises(ValueError, match="duplicated"):
        catalog._brapi()
    http.pages[1] = []
    with pytest.raises(ValueError, match="pagination invalid"):
        catalog._brapi()


def test_catalog_failure_is_sanitized_and_no_monitored_fallback_or_bar_request():
    http = Http()
    settings = Settings(eodhd_api_token="test", valuation_price_history_scope="stocks_etfs")
    database = Database(settings)
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "m", {}, {"rows": [{"symbol": "A"}]}, datetime.now(timezone.utc))
    service = PriceHistoryService(settings, database, http)
    http.fail = True
    with pytest.raises(ValueError, match="catalog provider request failed") as exc:
        service.backfill("NASDAQ")
    assert "secret_token" not in str(exc.value)
    assert len(http.calls) == 1 and "/exchange-symbol-list/US" in http.calls[0][0]
    assert not database._price_bars


def test_ordinary_allowance_reserves_retries_and_never_counts_extra_credit():
    http = Http()
    catalog = PriceCoverageCatalog(Settings(eodhd_api_token="test"), http)
    assert catalog.allowance(1000)["maximum_bar_calls"] == 3000
    http.account["apiRequests"] = 390000
    with pytest.raises(ValueError, match="ordinary provider allowance"):
        catalog.allowance(1000)
    http.account["apiRequestsDate"] = "2000-01-01"
    with pytest.raises(ValueError, match="date unavailable"):
        catalog.allowance(1)


def test_two_nights_keep_full_coverage_new_listings_and_prior_classified_delistings(monkeypatch):
    http = Http()
    settings = Settings(eodhd_api_token="test", valuation_price_history_scope="stocks_etfs")
    database = Database(settings)
    service = PriceHistoryService(settings, database, http)
    monkeypatch.setattr(service.coverage_catalog, "throttle", lambda: None)
    now = datetime(2026, 9, 11, 16, tzinfo=timezone.utc)
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "m", {}, {"rows": [{"symbol": "A"}]}, now)
    result = service.backfill("NASDAQ", now=now)
    assert set(result["series_bars"]) == {"A", "WIDE", "ETF"}
    assert result["coverage"]["selection_sha256"] == digest(result["coverage"]["selected"])
    assert result["bars_inserted"] == 3
    # A new catalog day drops WIDE, adds IPO. The next nightly vintage retains
    # the positively classified prior stock, not just today's screener member A.
    http.rows = [listing("A"), listing("IPO"), listing("ETF", "ETF")]
    service.coverage_catalog._cache.clear()
    next_night = service.nightly("NASDAQ", now=now + timedelta(days=1))
    assert set(next_night["series_bars"]) == {"A", "WIDE", "ETF", "IPO"}
    assert next_night["coverage"]["retained_from_previous"] == ["WIDE"]
    assert next_night["bars_unchanged"] == 3 and next_night["bars_inserted"] == 1
    manifest = database.latest_analysis_snapshot(ANALYSIS_TYPE, "NASDAQ")
    assert manifest["outputs"]["coverage"] == next_night["coverage"]
    # Explicit current reclassification to a non-stock must not be revived by
    # the previous manifest. Existing historical rows are never erased.
    http.rows.append(listing("WIDE", "FUND"))
    service.coverage_catalog._cache.clear()
    third = service.nightly("NASDAQ", now=now + timedelta(days=2))
    assert "WIDE" not in third["series_bars"]
    assert third["coverage"]["legacy_not_selected"]["WIDE"] == "excluded_instrument_type"
    assert len(database._price_bars) == 4


def test_scope_default_remains_monitored_until_explicit_activation():
    assert Settings().valuation_price_history_scope == "monitored"
    with pytest.raises(ValueError):
        Settings(valuation_price_history_scope="anything")


def test_prior_classified_stock_moving_venue_keeps_its_label_series_not_new_otc_names():
    http = Http()
    catalog = PriceCoverageCatalog(Settings(eodhd_api_token="test"), http)
    first = catalog.plan("NASDAQ", previous={}, legacy=[])
    http.rows = [listing("A"), listing("WIDE", venue="NYSE"), listing("NEWOTC", venue="OTC")]
    catalog._cache.clear()
    second = catalog.plan("NASDAQ", previous=first["selected"], legacy=list(first["selected"]))
    assert "WIDE" in second["selected"] and "WIDE" not in second["excluded"]
    assert "NEWOTC" not in second["selected"]
    assert sum(second["counts"].values()) == len(second["excluded"])
    http.rows[1] = listing("WIDE", kind="FUND", venue="NYSE")
    catalog._cache.clear()
    third = catalog.plan("NASDAQ", previous=second["selected"], legacy=list(second["selected"]))
    assert "WIDE" not in third["selected"]
