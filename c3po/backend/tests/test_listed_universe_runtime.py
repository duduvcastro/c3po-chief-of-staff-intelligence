import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.database import Database
from app import valuation_official as official
from app.listed_universe import Catalogue, Listing
from app.listed_universe_producer import BudgetedHttp, LiveCanonicalAdapter
from app.listed_universe_runtime import (
    CollectionPaused, InputFiles, QuotaWindow, TransientInputFailure, UnavailableInput,
    produce_catalogue, stage_predictions,
)

NOW = datetime.now(timezone.utc)
RATE = {"read": {"provider": "TEST", "host": "provider.test", "path_prefix": "/", "units": 1}}


def inventory(size=501):
    entries = tuple(Listing("NASDAQ", f"S{index:04}", f"Company {index}") for index in range(size))
    return Catalogue("NASDAQ", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
                     "nasdaq-trader-pipe-v1", NOW.isoformat(), NOW.isoformat(), "a" * 64, size, {}, entries)


def row(symbol):
    return {"symbol": symbol, "name": symbol, "price": 1.0, "our_tp": 145.0, "buy_in": 94.0,
            "internal_tp": 140.0, "internal_buy_in": 91.0, "internal_score": 70.0,
            "internal_status": "full_match", "internal_expected_total_return_percent": 20.0}


class Adapter:
    identity = {"source": "canonical-test-fixture"}

    def __init__(self, missing=(), failures=None):
        self.calls = []
        self.missing, self.failures = set(missing), dict(failures or {})

    def collect(self, listing, quota):
        quota.reserve("TEST", 1)
        self.calls.append(listing.symbol)
        if listing.symbol in self.missing:
            raise UnavailableInput("statements_missing")
        if self.failures.get(listing.symbol, 0):
            self.failures[listing.symbol] -= 1
            raise TransientInputFailure("temporary")
        return {"symbol": listing.symbol, "fundamental": {"pe": 10.0}, "history": [1] * 50}

    def prepare_context(self, inputs, quota):
        assert isinstance(inputs, InputFiles)
        return {"peer_symbols": sorted(inputs)}

    def value(self, inputs, context, quota):
        assert sorted(inputs) == context["peer_symbols"]
        return {symbol: row(symbol) for symbol in inputs}


def run(cat, directory, adapter, *, limit=2000, window="night1", **kwargs):
    return produce_catalogue(cat, directory, adapter, window=window, limits={"TEST": limit},
                              rate_card=RATE, act=True, **kwargs)


def test_whole_catalogue_over300_is_reconciled_with_missing_inputs_retained(tmp_path):
    adapter = Adapter(missing={"S0030", "S0500"})
    result = run(inventory(), tmp_path, adapter)
    assert result["complete"] and result["remaining"] == 0
    assert result["inventory_count"] == len(set(adapter.calls)) == 501
    assert result["valued_count"] == 499 and result["not_evaluable_count"] == 2
    assert not result["generation_activated"]
    state = json.loads((tmp_path / "checkpoint.json").read_text())
    assert state["items"]["S0500"]["reason"] == "statements_missing"


def test_default_plan_neither_calls_provider_nor_writes_checkpoint(tmp_path):
    result = produce_catalogue(inventory(10), tmp_path / "plan", Adapter(), window="night1",
                               limits={"TEST": 0}, rate_card=RATE)
    assert result["network_calls"] == 0 and result["action"] == "plan"
    assert not (tmp_path / "plan").exists()


def test_pause_at_batch_boundary_and_resume_does_not_refetch_completed_inputs(tmp_path):
    adapter = Adapter()
    result = run(inventory(23), tmp_path, adapter, batch_size=5, max_batches=2)
    assert result["remaining"] == 23  # ten inputs ready, no valuation on an incomplete peer cohort
    assert len(adapter.calls) == 10
    result = run(inventory(23), tmp_path, adapter, batch_size=3)
    assert result["complete"] and len(adapter.calls) == 23
    context = json.loads((tmp_path / "context.json").read_text())["payload"]
    assert len(context["peer_symbols"]) == 23  # not per-batch medians


def test_quota_exhaustion_pauses_without_turning_unread_names_into_missing_data(tmp_path):
    adapter = Adapter()
    result = run(inventory(10), tmp_path, adapter, limit=3)
    assert not result["complete"] and result["not_evaluable_count"] == 0
    assert result["quota"]["used"]["TEST"] == len(adapter.calls) == 3
    assert result["pause_reason"] == "provider_quota_window_exhausted"
    result = run(inventory(10), tmp_path, adapter, limit=3)
    assert len(adapter.calls) == 3  # resume does not reset the persistent window
    result = run(inventory(10), tmp_path, adapter, window="operator-explicit-night2", limit=20)
    assert result["complete"] and len(adapter.calls) == 10


def test_transient_retry_is_bounded_and_each_attempt_consumes_units(tmp_path):
    adapter = Adapter(failures={"S0000": 10})
    result = run(inventory(2), tmp_path, adapter)
    assert result["not_evaluable_count"] == 1 and result["valued_count"] == 1
    assert adapter.calls.count("S0000") == 2
    assert result["quota"]["used"]["TEST"] == 3


def test_crash_after_input_artifact_before_checkpoint_reuses_verified_artifact(tmp_path, monkeypatch):
    from app import listed_universe_runtime as runtime
    original, failed = runtime.atomic_json, False

    def fail_once(path, data):
        nonlocal failed
        if path.name == "checkpoint.json" and not failed and data["items"]["S0000"]["status"] == "inputs_ready":
            failed = True
            raise OSError("simulated fsync boundary crash")
        original(path, data)

    adapter = Adapter()
    monkeypatch.setattr(runtime, "atomic_json", fail_once)
    with pytest.raises(OSError):
        run(inventory(2), tmp_path, adapter)
    monkeypatch.setattr(runtime, "atomic_json", original)
    result = run(inventory(2), tmp_path, adapter)
    assert result["complete"] and adapter.calls == ["S0000", "S0001"]


def test_tampered_or_other_catalogue_checkpoint_cannot_resume(tmp_path):
    run(inventory(5), tmp_path, Adapter(), max_batches=1, batch_size=1)
    with pytest.raises(ValueError, match="changed"):
        run(inventory(6), tmp_path, Adapter())
    source = next((tmp_path / "inputs").glob("*.json"))
    data = json.loads(source.read_text());data["payload"]["symbol"] = "FOREIGN";source.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="digest"):
        run(inventory(5), tmp_path, Adapter())


def test_no_generation_activation_when_staging_genuine_immutable_prediction_records(tmp_path):
    database = Database(Settings(database_url="", auth_cookie_secure=False))
    method = database.ensure_methodology_version("fixture", 32, {}, "fixture")
    for market in ["B3", "NASDAQ", "NYSE"]:
        database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", method,
                                        {"methodology_version": 32}, {"rows": [row("OLD")], "universe_size": 1}, NOW)
    original_generation = official.current_generation(database)
    run(inventory(401), tmp_path, Adapter())
    receipt = stage_predictions(database, tmp_path, act=True)
    assert receipt["records_considered"] == receipt["records_inserted"] == 802
    assert official.current_generation(database) == original_generation
    assert set(official.official_rows(database, "NASDAQ", generation=original_generation)) == {"OLD"}
    snapshot = database.analysis_snapshot_by_id(receipt["stage_snapshot_id"])
    assert snapshot["analysis_type"] == "full_universe_stage"
    records = database.valuation_predictions_for_cycle(receipt["stage_snapshot_id"], source=official.SOURCE_INTERNAL)
    assert len(records) == 401 and all(official.stored_prediction(record) for record in records.values())
    assert all(record["published_at"] >= record["prediction_instant"] for record in records.values())
    assert stage_predictions(database, tmp_path, act=True)["records_inserted"] == 0
    assert official.current_generation(database) == original_generation


def test_incomplete_stage_refused_and_stage_plan_writes_no_database(tmp_path):
    run(inventory(5), tmp_path, Adapter(), max_batches=1, batch_size=1)
    with pytest.raises(ValueError, match="incomplete"):
        stage_predictions(object(), tmp_path, act=True)
    run(inventory(5), tmp_path, Adapter())
    assert stage_predictions(object(), tmp_path)["written"] is False


def test_weighted_quota_transport_reserves_before_read_and_never_hides_retries(tmp_path):
    class Client:
        calls = 0
        def get(self, url, **kwargs):
            self.calls += 1
            return httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", url))
    rate = {"fundamentals": {"provider": "TEST", "host": "provider.test", "path_prefix": "/fundamentals/", "units": 20}}
    quota = QuotaWindow(tmp_path, window="test", limits={"TEST": 39}, rate_card=rate)
    client = Client();http = BudgetedHttp(quota, client=client)
    assert http.get_json("https://provider.test/fundamentals/A") == {"ok": True}
    with pytest.raises(CollectionPaused):
        http.get_json("https://provider.test/fundamentals/B")
    assert client.calls == 1 and quota.state["used"]["TEST"] == 20


def test_throttle_hold_survives_restart_and_unrated_origin_never_reaches_network(tmp_path):
    class Client:
        def get(self, url, **kwargs):
            return httpx.Response(429, request=httpx.Request("GET", url))
    quota = QuotaWindow(tmp_path, window="test", limits={"TEST": 5}, rate_card=RATE)
    with pytest.raises(CollectionPaused, match="throttled"):
        BudgetedHttp(quota, client=Client()).get_json("https://provider.test/A")
    reopened = QuotaWindow(tmp_path, window="test", limits={"TEST": 5}, rate_card=RATE)
    with pytest.raises(CollectionPaused, match="throttled"):
        reopened.reserve("TEST", 1)
    other = QuotaWindow(tmp_path, window="new", limits={"TEST": 5}, rate_card=RATE)
    with pytest.raises(CollectionPaused, match="rate_card"):
        BudgetedHttp(other, client=object()).get_json("https://unrated.test/A")


def test_official_share_class_requires_explicit_bijective_provider_identity():
    adapter = LiveCanonicalAdapter(Settings(), object(), market="NYSE", deadline=NOW + timedelta(hours=1))
    listing = Listing("NYSE", "BRK.B", "Berkshire - Class B Common Stock")
    with pytest.raises(UnavailableInput, match="unmapped"):
        adapter._provider_symbol(listing)
    mapped = LiveCanonicalAdapter(Settings(), object(), market="NYSE", deadline=NOW + timedelta(hours=1),
                                  provider_symbols={"BRK.B": "BRK-B.US"})
    assert mapped._provider_symbol(listing) == "BRK-B.US"
    with pytest.raises(ValueError, match="same provider"):
        LiveCanonicalAdapter(Settings(), object(), market="NYSE", deadline=NOW + timedelta(hours=1),
                             provider_symbols={"BRK.B": "BRK.US", "BRK.A": "BRK.US"})


def test_provider_aliases_cannot_cross_market_or_collide_with_implicit_identity(tmp_path):
    wrong = LiveCanonicalAdapter(Settings(), object(), market="NYSE", deadline=NOW + timedelta(hours=1),
                                 provider_symbols={"BRK.B": "PETR4.SA"})
    with pytest.raises(UnavailableInput, match="invalid"):
        wrong._provider_symbol(Listing("NYSE", "BRK.B", "Berkshire"))
    collision = LiveCanonicalAdapter(Settings(), object(), market="NYSE", deadline=NOW + timedelta(hours=1),
                                     provider_symbols={"BRK.B": "AAPL.US"})
    entries = (Listing("NYSE", "BRK.B", "Berkshire"), Listing("NYSE", "AAPL", "Synthetic identity"))
    cat = Catalogue("NYSE", "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt", "nasdaq-trader-pipe-v1",
                    NOW.isoformat(), NOW.isoformat(), "b" * 64, 2, {}, entries)
    with pytest.raises(ValueError, match="same provider"):
        run(cat, tmp_path, collision)
    assert not (tmp_path / "checkpoint.json").exists()  # reject before any input/provider read


def test_resume_identity_pins_runner_normalizer_settings_and_effective_overlay(monkeypatch):
    from app.listed_universe_runtime import producer_identity
    pins = producer_identity()
    assert {"listed_universe_runtime.py", "listed_universe_producer.py", "market_data/eodhd.py",
            "official_statements.py"} <= set(pins)
    settings = Settings(eodhd_api_token="test-fixture")
    first = LiveCanonicalAdapter(settings, object(), market="B3", deadline=NOW + timedelta(hours=1))
    changed = LiveCanonicalAdapter(Settings(eodhd_api_token="different-fixture"), object(),
                                   market="B3", deadline=NOW + timedelta(hours=1))
    assert changed.identity != first.identity and "test-fixture" not in json.dumps(first.identity)
    monkeypatch.setenv("C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_ENABLED", "false" if first.fieldwise_overlay else "true")
    second = LiveCanonicalAdapter(settings, object(), market="B3", deadline=NOW + timedelta(hours=1))
    assert second.identity != first.identity
    with pytest.raises(CollectionPaused, match="overlay_policy_changed"):
        first._services(object())


def canonical_input(symbol):
    return {"listing": {"symbol": symbol, "name": symbol},
            "quote": {"symbol": symbol, "name": symbol, "price": 100.0, "currency": "USD",
                      "change_percent": 1.0, "volume": 3_000_000, "as_of": NOW.isoformat()},
            "fundamental": {"companyName": symbol, "sector": "Technology", "industry": "Software",
                            "marketCap": 5_000_000_000, "trailingPE": 20.0, "forwardPE": 18.0,
                            "enterpriseToEbitda": 15.0, "trailingEps": 5.0, "forwardEps": 5.6,
                            "sharesOutstanding": 50_000_000, "freeCashflow": 500_000_000,
                            "ebitda": 700_000_000, "totalDebt": 200_000_000, "totalCash": 300_000_000,
                            "returnOnEquity": 0.24, "profitMargins": 0.18, "bookValue": 30.0,
                            "earningsGrowthAnnual": 0.1, "revenueGrowthAnnual": 0.1, "beta": 1.0},
            "history": [{"date": (NOW - timedelta(days=260 - index)).date().isoformat(),
                         "close": 80 + index * 0.08, "volume": 2_000_000} for index in range(260)],
            "consensus": [None, None], "institutional": None, "grades": None,
            "received_at": NOW.isoformat(), "fmp_received_at": NOW.isoformat()}


def test_cold_context_resume_calls_actual_canonical_us_engine_without_network(tmp_path, monkeypatch):
    from app.listed_universe import utc
    from app.listed_universe_runtime import _artifact
    settings = Settings(database_url="", eodhd_api_token="test", auth_cookie_secure=False)
    database = Database(settings)
    deadline = NOW + timedelta(hours=1)
    context = {"market": "NASDAQ", "risk_free_rate": 0.042, "peer_medians": {}, "ir_events": {},
               "sentiment": {}, "insider_activity": {}, "calibration": {}}

    class OfflineInputs(LiveCanonicalAdapter):
        def collect(self, listing, quota):
            quota.reserve("TEST", 1)
            return canonical_input(listing.symbol)
        def prepare_context(self, inputs, quota):
            return context

    first = OfflineInputs(settings, database, market="NASDAQ", deadline=deadline)
    monkeypatch.setattr(first, "value", lambda *args: (_ for _ in ()).throw(RuntimeError("process stops after context")))
    with pytest.raises(RuntimeError, match="process stops"):
        run(inventory(3), tmp_path, first)
    assert (tmp_path / "context.json").exists()
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network forbidden")))
    resumed = OfflineInputs(settings, database, market="NASDAQ", deadline=deadline)
    result = run(inventory(3), tmp_path, resumed)
    assert result["complete"] and result["valued_count"] == 3
    state = json.loads((tmp_path / "checkpoint.json").read_text())
    actual = _artifact(tmp_path / state["items"]["S0000"]["row_file"], identity=state["identity"], symbol="S0000")
    item = canonical_input("S0000")
    expected = resumed.us._analyze_stock("NASDAQ", item["quote"], item["fundamental"], item["history"], 3_000_000,
                                         risk_free_rate=0.042, peer_medians={},
                                         consensus_fetched_at={"eodhd": utc(item["received_at"]), "fmp": utc(item["fmp_received_at"])})
    resumed.us._assign_statuses([expected], 0.042)
    assert all(actual[key] == expected[key] for key in ("our_tp", "internal_tp", "buy_in", "internal_buy_in", "status", "internal_status"))
    assert result["quota"]["reservations"] == 3  # resume read no provider; actual canonical arithmetic only
    assert not database._valuation_decisions


def test_staging_retry_uses_first_actual_insert_clock_not_reserved_id_clock(tmp_path, monkeypatch):
    from app import listed_universe_runtime as runtime
    database = Database(Settings(database_url="", auth_cookie_secure=False))
    run(inventory(1), tmp_path, Adapter())
    original = database.save_analysis_snapshot
    monkeypatch.setattr(database, "save_analysis_snapshot", lambda *a, **k: (_ for _ in ()).throw(OSError("before insert")))
    with pytest.raises(OSError):
        stage_predictions(database, tmp_path, act=True)
    state = json.loads((tmp_path / "checkpoint.json").read_text())
    assert state["stage_snapshot_id"] and "stage_published_at" not in state
    insert_at = datetime.now(timezone.utc) + timedelta(minutes=2)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return insert_at
    monkeypatch.setattr(runtime, "datetime", Clock)
    monkeypatch.setattr(database, "save_analysis_snapshot", original)
    receipt = stage_predictions(database, tmp_path, act=True)
    snapshot = database.analysis_snapshot_by_id(receipt["stage_snapshot_id"])
    assert snapshot["published_at"] == insert_at
    assert stage_predictions(database, tmp_path, act=True)["records_inserted"] == 0


def test_real_b3_collection_keeps_legacy_quote_and_adjusted_history_fallbacks(tmp_path):
    from urllib.parse import urlparse
    paths = []
    class Client:
        def get(self, url, **kwargs):
            path = urlparse(url).path
            paths.append(path)
            status = 200
            if path == "/api/v2/stocks/quote":
                status, body = 404, {}
            elif path == "/api/quote/PETR4":
                body = {"results": [{"symbol": "PETR4", "regularMarketPrice": 36.0,
                                      "regularMarketVolume": 100_000, "marketCap": 1_000_000_000}]}
            elif path.startswith("/api/eod/"):
                body = [{"date": (NOW - timedelta(days=70 - index)).date().isoformat(), "close": 72.0,
                         "adjusted_close": 36.0, "volume": 100_000} for index in range(70)]
            elif path.startswith("/api/v1.1/fundamentals/"):
                body = {"General": {"Code": "PETR4", "Type": "Common Stock", "Name": "Petrobras"},
                        "Highlights": {"MarketCapitalization": 1_000_000_000}}
            else:
                body = {"results": []}
            return httpx.Response(status, json=body, request=httpx.Request("GET", url))
    settings = Settings(database_url="", eodhd_api_token="test", brapi_base_url="https://provider.test",
                        eodhd_base_url="https://provider.test")
    database = Database(settings)
    quota = QuotaWindow(tmp_path, window="test", limits={"TEST": 20}, rate_card=RATE)
    adapter = LiveCanonicalAdapter(settings, database, market="B3", deadline=NOW + timedelta(hours=1))
    adapter._services(quota)
    adapter.http.client = Client()
    result = adapter.collect(Listing("B3", "PETR4", "Petrobras"), quota)
    assert paths[:2] == ["/api/v2/stocks/quote", "/api/quote/PETR4"]
    assert "/api/eod/PETR4.SA" in paths
    assert result["history"]["history_days"] == 66 and result["history"]["last_close"] == 36.0
    assert result["history"]["adtv_90d"] == 3_600_000.0  # adjusted close, canonical normalization
    assert quota.state["reservations"] == len(paths) and not database._ingestion_runs


def test_worker_default_cli_is_only_a_plan_and_stage_requires_explicit_run(tmp_path, capsys, monkeypatch):
    from app.listed_universe_worker import main
    from app import config
    settings = Settings(database_url="", auth_cookie_secure=False)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network forbidden")))
    cat, policy = tmp_path / "catalogue.json", tmp_path / "policy.json"
    cat.write_text(json.dumps(inventory(10).payload()))
    policy.write_text(json.dumps({"window": "test", "deadline": (NOW + timedelta(hours=1)).isoformat(),
                                  "limits": {"TEST": 0}, "rate_card": RATE}))
    args = ["--catalogue", str(cat), "--policy", str(policy), "--checkpoint", str(tmp_path / "run")]
    assert main(args) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["action"] == "plan" and receipt["network_calls"] == 0
    assert not (tmp_path / "run").exists()
    with pytest.raises(SystemExit):
        main([*args, "--stage-records"])


def test_actual_b3_canonical_engine_evaluates_below_minimum_inputs_without_exclusion(tmp_path, monkeypatch):
    from app.schemas import NormalizedQuote
    settings = Settings(database_url="", auth_cookie_secure=False)
    database = Database(settings)
    adapter = LiveCanonicalAdapter(settings, database, market="B3", deadline=NOW + timedelta(hours=1))
    quota = QuotaWindow(tmp_path, window="test", limits={"TEST": 0}, rate_card=RATE)
    symbol = "SYNTH3"
    item = canonical_input(symbol)
    item.update({"statistics": {}, "financial": {}, "brapi_received_at": NOW.isoformat(),
                 "history": {"history_days": 66, "adtv_90d": 1000.0, "volatility_90d": 0.2,
                             "support_60d": 0.9, "median_20d": 1.0, "low_20d": .85, "last_close": 1.0}})
    item["quote"] = NormalizedQuote(provider="brapi", symbol=symbol, provider_symbol=symbol, exchange="B3",
                                     currency="BRL", price=1.0, volume=1000.0, market_cap=5_000_000,
                                     as_of=NOW, collected_at=NOW, quality_score=80).model_dump(mode="json")
    item["fundamental"].update(marketCap=5_000_000, sharesOutstanding=5_000_000, freeCashflow=500_000,
                               ebitda=700_000, trailingEps=.05, forwardEps=.056, bookValue=.30,
                               totalDebt=200_000, totalCash=300_000)
    context = {"market": "B3", "calibration": {}, "macro": {"selic": .15, "ipca12m": .045},
               "row_inputs": {"cut": NOW.isoformat(), "ir_events": {}, "insider_activity": {}}}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network forbidden")))
    rows = adapter.value({symbol: item}, context, quota)
    assert set(rows) == {symbol}
    assert rows[symbol]["price"] == 1.0 and rows[symbol]["adtv_90d"] == 1000.0
    assert rows[symbol]["our_tp"] > 0 and rows[symbol]["internal_tp"] > 0
    assert not database._valuation_official_selections and quota.state["reservations"] == 0


def test_canonical_transport_interface_never_adds_hidden_retries(tmp_path):
    from app.market_data.http import JsonHttpClient, MarketDataRequestError
    class Client:
        calls = 0
        def get(self, url, **kwargs):
            self.calls += 1
            return httpx.Response(500, json={"unavailable": True}, request=httpx.Request("GET", url))
    quota = QuotaWindow(tmp_path, window="test", limits={"TEST": 5}, rate_card=RATE)
    client = Client()
    http = BudgetedHttp(quota, client=client)
    assert isinstance(http, JsonHttpClient)
    with pytest.raises(MarketDataRequestError):
        http.get_json("https://provider.test/A")
    assert client.calls == quota.state["reservations"] == 1
    assert quota.state["used"]["TEST"] == 1 and quota.state["http_observations"]["status_counts"] == {"500": 1}


@pytest.mark.parametrize("units", [None, True, "20", 0, -1, {}, []])
def test_untrusted_rate_card_units_remain_closed_before_any_request(tmp_path, units):
    class Client:
        def get(self, *args, **kwargs):
            raise AssertionError("malformed quota must never reach a provider")
    rate = {"read": {**RATE["read"], "units": units}}
    quota = QuotaWindow(tmp_path, window="test", limits={"TEST": 20}, rate_card=rate)
    with pytest.raises(CollectionPaused, match="rate_card"):
        BudgetedHttp(quota, client=Client()).get_json("https://provider.test/A")
    assert quota.state["reservations"] == quota.state["http_observations"]["attempts_started"] == 0
    assert quota.state["used"]["TEST"] == 0
    with pytest.raises(CollectionPaused, match="rate_card"):
        quota.check()  # a canonical soft catch cannot reinterpret this as missing data
