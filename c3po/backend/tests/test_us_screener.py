import statistics
from datetime import date, datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.database import Database
from app.market_data.us_screener import USScreeningService
from app.valuation_policy import METHODOLOGY_VERSION


class DummyRealtime:
    http = object()


class DummyOnePagers:
    def _us_risk_free_rate(self):
        return 0.042

    def _us_peer_medians(self, fundamentals_by_symbol):
        return {}

    def _fmp_consensus_batch(self, symbols):
        return {}

    def _fmp_institutional_batch(self, symbols):
        return {}

    def _fmp_recent_grades_batch(self, symbols):
        return {}

    def _analyze(
        self, symbol, market, quote, fundamentals, history, *,
        insider_activity=None, news_sentiment=None, risk_free_rate=None, peer_medians=None,
        fmp_consensus=None, fmp_summary=None, institutional_positions=None, recent_grades=None, role="consumer",
    ):
        assert role == "producer"  # the screener is the official producer (V3.2 rev 7 §7-bis): never a consumer read
        return {
            "c3po_tp": 145.0,
            "consensus_tp": 150.0,
            "consensus_source": "fmp_last_month",
            "analyst_count": 12,
            "buy_in": 94.0,
            "confidence": 82.0,
            "risk_score": 29.0,
            "dispersion": 12.0,
            "methods": {
                "Goldman Sachs": 140.0,
                "Morgan Stanley": 146.0,
                "Bridgewater": 138.0,
                "JPMorgan": 149.0,
                "BlackRock": 152.0,
            },
            "thesis": ["Durable growth and cash generation support the valuation."],
            "risks": ["Execution and multiple compression remain the principal risks."],
        }


def _publish_official_universes(database, nasdaq_rows: list[dict], *, at: datetime | None = None, methodology_id: str = "mv-1") -> None:
    """Passo 0 (V3.2 rev 7 §7-bis): served rows come from the official selection, which needs every market recorded once."""
    at = at or datetime.now(timezone.utc)
    filler = {"B3": {"symbol": "PETR4", "our_tp": 40.0, "buy_in": 32.0, "price": 36.0, "internal_tp": 39.0},
              "NYSE": {"symbol": "KO", "our_tp": 70.0, "buy_in": 60.0, "price": 65.0, "internal_tp": 68.0}}
    for market, row in filler.items():
        database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", methodology_id, {"methodology_version": METHODOLOGY_VERSION},
                                        {"rows": [row], "universe_size": 1}, at)
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", methodology_id, {"methodology_version": METHODOLOGY_VERSION},
                                    {"rows": nasdaq_rows, "universe_size": len(nasdaq_rows)}, at)


def service(one_pagers: DummyOnePagers | None = None) -> USScreeningService:
    settings = Settings(eodhd_api_token="test", auth_cookie_secure=False)
    return USScreeningService(settings, Database(settings), DummyRealtime(), one_pagers or DummyOnePagers())


class OverridingOnePagers(DummyOnePagers):
    """The producer framework answering with a variant of the canonical analysis (no consensus; the foreign bridge)."""

    def __init__(self, **overrides):
        self.overrides = overrides

    def _analyze(self, *args, **kwargs):
        return {**super()._analyze(*args, **kwargs), **self.overrides}


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 8, 24, 14, 22, tzinfo=timezone.utc),
        datetime(2026, 8, 24, 20, 14, 59, tzinfo=timezone.utc),
        datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
    ],
)
def test_canonical_refresh_rejects_incomplete_us_session_volume(now: datetime) -> None:
    with pytest.raises(RuntimeError, match="blocked until 16:15 ET"):
        USScreeningService._require_completed_session_volume(now)


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 8, 24, 20, 15, tzinfo=timezone.utc),
        datetime(2026, 1, 5, 21, 15, tzinfo=timezone.utc),
        datetime(2026, 8, 25, 4, 0, tzinfo=timezone.utc),
        datetime(2026, 8, 23, 14, 22, tzinfo=timezone.utc),
    ],
)
def test_canonical_refresh_allows_completed_or_inactive_us_sessions(now: datetime) -> None:
    USScreeningService._require_completed_session_volume(now)


def test_intraday_refresh_fails_before_provider_calls_and_preserves_snapshot() -> None:
    class ExplodingRealtime(DummyRealtime):
        def _us_symbol_catalog(self, now):
            raise AssertionError("provider must not be called")

    settings = Settings(eodhd_api_token="test", auth_cookie_secure=False)
    database = Database(settings)
    methodology_id = database.ensure_methodology_version("test", 1, {}, "test")
    snapshot_id = database.save_analysis_snapshot(
        "valuation_universe",
        "NASDAQ_UNIVERSE",
        methodology_id,
        {},
        {"rows": [], "universe_size": 0},
        datetime(2026, 8, 23, 21, 0, tzinfo=timezone.utc),
    )
    screener = USScreeningService(
        settings, database, ExplodingRealtime(), DummyOnePagers(),
    )

    with pytest.raises(RuntimeError, match="blocked until 16:15 ET"):
        screener._build(
            "NASDAQ", now=datetime(2026, 8, 24, 14, 22, tzinfo=timezone.utc),
        )

    latest = database.latest_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE")
    assert latest and latest["id"] == snapshot_id


def rising_history(days: int = 260):
    start = datetime(2025, 8, 1, tzinfo=timezone.utc)
    return [
        {"date": (start + timedelta(days=index)).date().isoformat(), "close": 80 + index * 0.08, "volume": 2_000_000}
        for index in range(days)
    ]


def test_stock_analysis_uses_canonical_five_method_output() -> None:
    result = service()._analyze_stock(
        "NASDAQ",
        {
            "symbol": "TEST",
            "name": "Test Corp",
            "price": 100.0,
            "change_percent": 1.2,
            "volume": 3_000_000,
            "as_of": datetime.now(timezone.utc),
        },
        {
            "companyName": "Test Corp",
            "sector": "Technology",
            "industry": "Software",
            "marketCap": 5_000_000_000,
            "returnOnEquity": 0.24,
            "profitMargins": 0.18,
            "dividendYield": 0.01,
        },
        rising_history(),
        300_000_000,
    )

    assert result["security_type"] == "Stock"
    assert result["our_tp"] == 145.0
    assert result["signal_quality"] == "validated"
    assert result["valuation_method_count"] == 6
    # PROMO-2 (c): the row carries the consensus source; without a receipt instant handed over, NO instant is invented
    assert result["consensus_origin_source"] == "fmp_last_month" and result["consensus_published_at"] is None


STOCK_QUOTE = {"symbol": "TEST", "name": "Test Corp", "price": 100.0, "change_percent": 1.2, "volume": 3_000_000, "as_of": datetime(2026, 9, 7, 21, 0, tzinfo=timezone.utc)}
STOCK_FUNDAMENTALS = {"companyName": "Test Corp", "sector": "Technology", "industry": "Software", "marketCap": 5_000_000_000,
                      "returnOnEquity": 0.24, "profitMargins": 0.18, "dividendYield": 0.01}


def test_stock_rows_carry_the_internal_buy_in_derived_by_the_producers_own_entry_rule() -> None:
    """Passo 1 (official_internal_v1): the SAME row emits the buy-in of the INTERNAL TP — the uncalibrated method mean —
    by the rule the producer applied to the blend (``official_buy_in_v1`` with the mirrored entry hurdle of the pinned
    One Pager, ``official_entry_discount_v1``); no method is recomputed. Without a consensus the blend IS the internal
    TP and the producer's buy-in is the internal one; the primary-listing bridge keeps its registered buy-in."""
    from app.valuation_official_engine import official_buy_in_v1, official_entry_discount_v1

    with_consensus = service()._analyze_stock("NASDAQ", STOCK_QUOTE, STOCK_FUNDAMENTALS, rising_history(), 300_000_000)
    methods = {"Goldman Sachs": 140.0, "Morgan Stanley": 146.0, "Bridgewater": 138.0, "JPMorgan": 149.0, "BlackRock": 152.0}
    expected = official_buy_in_v1(methods.values(), official_entry_discount_v1("US", 29.0, 82.0), statistics.mean(methods.values()))
    assert with_consensus["buy_in"] == 94.0 and with_consensus["internal_buy_in"] == expected and expected != 94.0
    assert with_consensus["internal_buy_in"] == pytest.approx(145.0 / (1 + 0.12 + 0.29 * 0.11 + 0.18 * 0.06))  # the 90 % cap never binds for the internal TP
    assert with_consensus["internal_tp"] == 145.0 and with_consensus["public_consensus_tp"] == 150.0
    without_consensus = service(OverridingOnePagers(consensus_tp=None, analyst_count=None))._analyze_stock("NASDAQ", STOCK_QUOTE, STOCK_FUNDAMENTALS, rising_history(), 300_000_000)
    assert without_consensus["public_consensus_tp"] is None and without_consensus["internal_buy_in"] == without_consensus["buy_in"] == 94.0
    bridged = service(OverridingOnePagers(method_estimate_registered_on="2026-08-01"))._analyze_stock("NASDAQ", STOCK_QUOTE, STOCK_FUNDAMENTALS, rising_history(), 300_000_000)
    assert bridged["public_consensus_tp"] == 150.0 and bridged["internal_buy_in"] == bridged["buy_in"] == 94.0
    # the internal record of the cycle reads exactly these two fields
    from app import valuation_official as official
    record = official.prediction_from_row(with_consensus, market="NASDAQ", scope="universe", cycle_id="c", source_version="7",
                                          prediction_instant=datetime(2026, 9, 7, 21, 0, tzinfo=timezone.utc), source=official.SOURCE_INTERNAL)
    assert record is not None and record["tp"] == 145.0 and record["buy_in"] == expected and record["consensus_tp"] == 150.0 and record["consensus_weight_percent"] == 0.0


def test_etf_analysis_uses_fund_evidence_instead_of_corporate_dcf() -> None:
    result = service()._analyze_etf(
        "NYSE",
        {
            "symbol": "TESTETF",
            "name": "Test ETF",
            "price": 100.0,
            "change_percent": 0.4,
            "volume": 4_000_000,
            "as_of": datetime.now(timezone.utc),
        },
        {
            "companyName": "Test ETF",
            "isETF": True,
            "etfCategory": "Large Blend",
            "etfTotalAssets": 8_000_000_000,
            "etfNetExpenseRatio": 0.001,
            "etfHoldingsCount": 500,
            "etfExpectedReturn3Y": 0.12,
        },
        rising_history(),
        400_000_000,
    )

    assert result["security_type"] == "ETF"
    assert result["valuation_profile"] == "general"
    assert result["internal_method_count"] == 5
    assert "Asset allocation" in result["buy_in_models"]
    assert result["public_consensus_tp"] is None
    assert result["internal_tp"] == result["our_tp"] and result["internal_buy_in"] == result["buy_in"] > 0  # Passo 1: no consensus, the internal TP is the served one
    assert result["consensus_origin_source"] is None and result["consensus_published_at"] is None  # no consensus: no source, no instant


def test_spcx_never_uses_etf_screening_path() -> None:
    assert service()._is_etf({"Code": "SPCX", "Type": "ETF"}) is False


def test_candidate_ranking_combines_stocks_and_etfs_by_tp_upside() -> None:
    screener = service()
    stock = screener._analyze_stock(
        "NASDAQ",
        {
            "symbol": "STOCK",
            "name": "Stock Corp",
            "price": 100.0,
            "change_percent": 1.2,
            "volume": 3_000_000,
            "as_of": datetime.now(timezone.utc),
        },
        {
            "companyName": "Stock Corp",
            "sector": "Technology",
            "industry": "Software",
            "marketCap": 5_000_000_000,
            "returnOnEquity": 0.24,
            "profitMargins": 0.18,
        },
        rising_history(),
        300_000_000,
    )
    etf = screener._analyze_etf(
        "NASDAQ",
        {
            "symbol": "ETFONE",
            "name": "ETF One",
            "price": 100.0,
            "change_percent": 0.4,
            "volume": 4_000_000,
            "as_of": datetime.now(timezone.utc),
        },
        {
            "companyName": "ETF One",
            "isETF": True,
            "etfCategory": "Large Blend",
            "etfTotalAssets": 8_000_000_000,
            "etfNetExpenseRatio": 0.001,
            "etfHoldingsCount": 500,
            "etfExpectedReturn3Y": 0.12,
        },
        rising_history(),
        400_000_000,
    )
    stock["status"] = "full_match"
    etf["status"] = "full_match"
    screener._rows["NASDAQ"] = [etf, stock]
    screener._basis_at["NASDAQ"] = datetime.now(timezone.utc)

    assert screener._candidate_response("NASDAQ").items == []  # no official generation yet: the raw build is never served (F393-3)
    _publish_official_universes(screener.database, [etf, stock])
    response = screener._candidate_response("NASDAQ")

    assert [item.security_type for item in response.items] == ["Stock", "ETF"]
    assert response.items[0].upside_percent > response.items[1].upside_percent
    assert response.tp_source == "official_blend_v1" and response.official_generation_id and response.official_session_date
    assert all(item.tp_source == "official_blend_v1" and item.official_generation_id == response.official_generation_id
               and item.official_row_sha256 and item.official_session_date and item.prediction_instant for item in response.items)


def test_ir_freshness_flags_pending_review_when_fundamentals_predate_disclosure() -> None:
    """Root-caused 2026-08-20: US rows always shipped a hardcoded "current"/"unavailable"
    placeholder for ir_status because _build() never consulted Tatooine Updates
    (SEC EDGAR + Finnhub), unlike B3ScreenerService's rows. This mirrors
    B3ScreenerService._ir_freshness's behavior so Dark Side/Ben Kenobi Records/Laser
    Pager get a real freshness signal for US names too.
    """
    event = {
        "event_type": "Financial Results",
        "published_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "reference_date": date(2026, 6, 30),
        "valuation_status": "pending_review",
        "reviewed_at": None,
    }

    stale = USScreeningService._ir_freshness("2026-03-31", event)
    current = USScreeningService._ir_freshness("2026-06-30", event)

    assert stale == {
        "ir_status": "pending_review",
        "latest_ir_event_at": event["published_at"],
        "latest_ir_event_type": "Financial Results",
    }
    assert current["ir_status"] == "current"


def test_ir_freshness_defaults_to_unavailable_without_an_event() -> None:
    assert USScreeningService._ir_freshness("2026-06-30", None) == {
        "ir_status": "unavailable",
        "latest_ir_event_at": None,
        "latest_ir_event_type": None,
    }


def test_us_valuation_calibration_uses_mature_price_return_samples() -> None:
    """Root-caused 2026-08-20 (TP methodology audit): B3 has a rolling
    90-day backtest that measures forecast bias by valuation profile and
    corrects internal_tp by up to +/-5% (b3_screener.py's
    _persist_calibration); the US engine had no equivalent, so a systematic
    bias would never be detected. Mirrors B3's own regression test exactly.
    """
    svc = service()
    methodology_id = svc.database.ensure_methodology_version("test", 1, {}, "test")
    generated_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    prior_rows = [
        {"symbol": f"T{index:03d}", "price": 100.0, "expected_total_return_percent": 15.0, "valuation_profile": "general"}
        for index in range(40)
    ]
    current_rows = [{"symbol": row["symbol"], "price": 110.0, "valuation_profile": "general"} for row in prior_rows]
    svc.database.save_analysis_snapshot(
        "valuation_universe", "NASDAQ_UNIVERSE", methodology_id, {}, {"rows": prior_rows},
        generated_at - timedelta(days=90),
    )

    svc._persist_calibration("NASDAQ", methodology_id, generated_at, current_rows)
    calibration = svc.database.latest_analysis_snapshot("valuation_calibration", "NASDAQ_POWER_MODEL")

    assert calibration and calibration["outputs"]["status"] == "active"
    assert 1.0 < calibration["outputs"]["factors"]["global"] <= 1.05
    assert calibration["outputs"]["metrics"]["global"]["samples"] == 40


def test_us_valuation_calibration_warms_up_without_a_mature_prior_snapshot() -> None:
    svc = service()
    methodology_id = svc.database.ensure_methodology_version("test", 1, {}, "test")

    svc._persist_calibration("NASDAQ", methodology_id, datetime.now(timezone.utc), [])
    calibration = svc.database.latest_analysis_snapshot("valuation_calibration", "NASDAQ_POWER_MODEL")

    assert calibration and calibration["outputs"]["status"] == "warming_up"
    assert calibration["outputs"]["factors"] == {}


def test_peer_medians_returns_the_latest_batch_computed_multiples_per_market() -> None:
    """Root-caused 2026-08-20: the single-symbol Laser Pager path
    (one_pager.py::generate()) never threaded peer_medians through, so it
    silently kept using the pre-PR#72 hardcoded multiples for every US
    symbol regardless of the new methodology. This getter is what
    generate() now reuses instead of recomputing peer medians itself.
    """
    svc = service()
    assert svc.peer_medians("NASDAQ") == {}
    svc._peer_medians["NASDAQ"] = {"financial": {"pe": 11.0, "ev_ebitda": 9.0}}
    assert svc.peer_medians("NASDAQ") == {"financial": {"pe": 11.0, "ev_ebitda": 9.0}}
    assert svc.peer_medians("NYSE") == {}


def test_peer_medians_merges_both_exchanges_when_no_market_is_given() -> None:
    """Root-caused 2026-08-20 (hotfix): one_pager.py::generate() only knows
    market == "US", not the specific exchange a symbol lists on, so passing
    that straight into peer_medians("US") raised ValueError (_market()
    only accepts NASDAQ/NYSE) and broke every US Laser Pager in production.
    peer_medians() must accept no market and merge both exchanges instead.
    """
    svc = service()
    svc._peer_medians["NASDAQ"] = {"technology": {"pe": 24.0, "ev_ebitda": 16.0}}
    svc._peer_medians["NYSE"] = {"financial": {"pe": 10.5, "ev_ebitda": 8.5}}

    merged = svc.peer_medians()

    assert merged == {
        "technology": {"pe": 24.0, "ev_ebitda": 16.0},
        "financial": {"pe": 10.5, "ev_ebitda": 8.5},
    }
    with pytest.raises(ValueError):
        svc.peer_medians("US")


def test_peer_medians_hydrates_from_a_persisted_snapshot_across_processes() -> None:
    """Root-caused 2026-08-20 (second hotfix, found by regenerating JPM's
    Laser Pager after #75 shipped): the api and valuation-worker containers
    are separate processes (compose.yml) with no shared Python memory.
    peer_medians() only ever returned the in-memory dict, which is
    populated exclusively inside _build() — a method the api container's
    request-serving path never calls. Every Laser Pager generated from the
    api container saw an empty dict forever and kept falling back to the
    pre-#72 hardcoded multiples, even after #75's wiring fix. peer_medians()
    must hydrate from a persisted snapshot on first use, same idea as
    _rows/valuation_for()'s _hydrate().
    """
    svc = service()
    methodology_id = svc.database.ensure_methodology_version("test", 1, {}, "test")
    svc.database.save_analysis_snapshot(
        "peer_medians", "NASDAQ_PEER_MEDIANS", methodology_id, {},
        {"medians": {"technology": {"pe": 23.5, "ev_ebitda": 15.5}}},
        datetime.now(timezone.utc),
    )

    assert svc.peer_medians("NASDAQ") == {"technology": {"pe": 23.5, "ev_ebitda": 15.5}}


def test_peer_medians_rehydrates_when_a_newer_snapshot_is_persisted() -> None:
    """Root-caused 2026-08-20 (production incident): peer_medians()/
    valuation_for() only ever re-hydrated when the in-memory dict was
    EMPTY -- once populated once, a long-lived api-container process
    would serve that same snapshot forever, silently ignoring every
    subsequent valuation-worker refresh (including a full day's worth of
    TP methodology fixes) until the next deploy happened to restart it
    and clear the in-memory state. Confirmed live: JPM's Laser Pager kept
    returning identical numbers across three re-runs of refresh_all()
    because the api container simply never looked at the database again
    after its first hydrate.
    """
    svc = service()
    methodology_id = svc.database.ensure_methodology_version("test", 1, {}, "test")
    old_at = datetime(2026, 8, 20, 4, 0, tzinfo=timezone.utc)
    new_at = datetime(2026, 8, 20, 7, 0, tzinfo=timezone.utc)
    svc.database.save_analysis_snapshot(
        "peer_medians", "NASDAQ_PEER_MEDIANS", methodology_id, {},
        {"medians": {"technology": {"pe": 20.0, "ev_ebitda": 14.0}}}, old_at,
    )
    assert svc.peer_medians("NASDAQ") == {"technology": {"pe": 20.0, "ev_ebitda": 14.0}}

    svc.database.save_analysis_snapshot(
        "peer_medians", "NASDAQ_PEER_MEDIANS", methodology_id, {},
        {"medians": {"technology": {"pe": 25.0, "ev_ebitda": 17.0}}}, new_at,
    )

    assert svc.peer_medians("NASDAQ") == {"technology": {"pe": 25.0, "ev_ebitda": 17.0}}


def test_valuation_for_rehydrates_when_a_newer_snapshot_is_persisted() -> None:
    svc = service()
    methodology_id = svc.database.ensure_methodology_version("test", 1, {}, "test")
    old_at = datetime(2026, 8, 20, 4, 0, tzinfo=timezone.utc)
    new_at = datetime(2026, 8, 20, 7, 0, tzinfo=timezone.utc)
    assert svc.valuation_for("JPM", "NASDAQ") is None  # a consumer read: nothing official yet, nothing served (F393-3)
    _publish_official_universes(svc.database, [{"symbol": "JPM", "our_tp": 625.49, "buy_in": 500.0, "price": 560.0, "internal_tp": 620.0, "as_of": old_at.isoformat()}],
                                at=old_at, methodology_id=methodology_id)
    assert svc.valuation_for("JPM", "NASDAQ")["our_tp"] == 625.49

    svc.database.save_analysis_snapshot(
        "valuation_universe", "NASDAQ_UNIVERSE", methodology_id,
        {"methodology_version": METHODOLOGY_VERSION},
        {"rows": [{"symbol": "JPM", "our_tp": 388.33, "buy_in": 340.0, "price": 360.0, "internal_tp": 385.0, "as_of": new_at.isoformat()}], "universe_size": 1},
        new_at,
    )

    assert svc.valuation_for("JPM", "NASDAQ")["our_tp"] == 388.33


def test_build_persists_peer_medians_for_the_next_process_to_hydrate() -> None:
    svc = service()
    svc._rows["NASDAQ"] = []
    svc._basis_at["NASDAQ"] = datetime.now(timezone.utc)
    svc._peer_medians["NASDAQ"] = {"financial": {"pe": 11.5, "ev_ebitda": 9.5}}

    svc._persist("NASDAQ")
    snapshot = svc.database.latest_analysis_snapshot("peer_medians", "NASDAQ_PEER_MEDIANS")

    assert snapshot and snapshot["outputs"]["medians"] == {"financial": {"pe": 11.5, "ev_ebitda": 9.5}}


def test_load_calibration_factors_clamps_persisted_values_to_the_documented_limit() -> None:
    svc = service()
    methodology_id = svc.database.ensure_methodology_version("test", 1, {}, "test")
    svc.database.save_analysis_snapshot(
        "valuation_calibration", "NASDAQ_POWER_MODEL", methodology_id, {},
        {"status": "active", "factors": {"global": 1.20, "technology": 0.80}, "metrics": {}},
        datetime.now(timezone.utc),
    )

    svc._load_calibration_factors("NASDAQ")

    assert svc._calibration_factors["NASDAQ"]["global"] == 1.05
    assert svc._calibration_factors["NASDAQ"]["technology"] == 0.95


def test_stock_row_stamps_the_receipt_instant_of_the_provider_the_resolver_used_never_the_cycle_start() -> None:
    # F398-1 (Codex): the consensus instant must be a FACT — the receipt of the provider's answer — never the build's start
    # clock, which precedes every fetch and would make "consensus existed at the prediction instant" true by assignment.
    fmp_at = datetime(2026, 9, 10, 21, 0, 10, tzinfo=timezone.utc)
    eodhd_at = datetime(2026, 9, 10, 21, 0, 4, tzinfo=timezone.utc)
    quote = {"symbol": "TEST", "name": "Test Corp", "price": 100.0, "change_percent": 1.2, "volume": 3_000_000, "as_of": datetime.now(timezone.utc)}
    fundamentals = {"companyName": "Test Corp", "sector": "Technology", "industry": "Software", "marketCap": 5_000_000_000,
                    "returnOnEquity": 0.24, "profitMargins": 0.18, "dividendYield": 0.01}
    row = service()._analyze_stock("NASDAQ", quote, fundamentals, rising_history(), 300_000_000,
                                   consensus_fetched_at={"fmp": fmp_at, "eodhd": eodhd_at})
    assert row["consensus_origin_source"] == "fmp_last_month" and row["consensus_published_at"] == fmp_at.isoformat()  # the resolver used FMP
    # the emitter persists that receipt as the block's instant; the cycle's publication (= prediction instant) comes AFTER it
    from app import valuation_official as official
    published = datetime(2026, 9, 10, 21, 3, tzinfo=timezone.utc)
    record = official.prediction_from_row(row, market="NASDAQ", scope="universe", cycle_id="c1", source_version="7", prediction_instant=published)
    assert record is not None and record["decomposition"]["consensus"]["published_at"] == fmp_at.isoformat()
    assert datetime.fromisoformat(record["decomposition"]["consensus"]["published_at"]) <= datetime.fromisoformat(record["prediction_instant"])


def test_persist_publishes_the_cycle_at_its_publication_instant_after_every_receipt() -> None:
    # F398-1: the universe snapshot's published_at (= prediction_instant of every record) is taken at publication, after the
    # provider answers the rows consumed — a consensus received after the build started is still BEFORE the prediction instant.
    screener = service()
    started = datetime(2026, 9, 10, 10, 0, 0, tzinfo=timezone.utc)  # in the past: the publication instant is the wall clock at persist
    received = datetime(2026, 9, 10, 10, 0, 10, tzinfo=timezone.utc)  # the provider answered ten seconds after the build started
    screener._basis_at["NASDAQ"] = started
    screener._rows["NASDAQ"] = [{"symbol": "TEST", "market": "NASDAQ", "security_type": "Stock", "our_tp": 145.0, "buy_in": 120.0, "price": 100.0,
                                 "internal_tp": 140.0, "public_consensus_tp": 150.0, "analyst_count": 12, "consensus_weight_percent": 35.0,
                                 "consensus_origin_source": "fmp_last_month", "consensus_published_at": received.isoformat(),
                                 "methods": {"dcf": 140.0}, "as_of": started}]
    screener._universe_size["NASDAQ"] = 1
    screener._coverage["NASDAQ"] = {}
    screener._persist("NASDAQ")
    snapshot = screener.database.latest_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE")
    assert snapshot is not None
    published_at = snapshot["published_at"] if isinstance(snapshot["published_at"], datetime) else datetime.fromisoformat(str(snapshot["published_at"]))
    assert published_at > received > started  # publication after the receipt, which is after the start: no back-dating anywhere
    assert screener._basis_at["NASDAQ"] == published_at  # the staleness check compares against the instant actually persisted
    assert snapshot["outputs"]["rows"][0]["consensus_published_at"] == received.isoformat()
    from app import valuation_official as official
    clocks = official.cycle_clocks(snapshot)
    assert clocks is not None and clocks[0] == published_at  # the prediction instant IS the publication
