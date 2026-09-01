from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Any

import pytest

from app.config import Settings
from app.database import Database
from app.r2d2 import (
    SAO_PAULO,
    R2D2PaperService,
    R2D2Repository,
    _date_value,
    _episode_summary_from_trades,
    _listing_history_verdict,
    _quote_freshness,
)
from app import r2d2 as r2d2_module
from app import r2d2_entry_control
from app.market_data.eodhd_stream import EodhdRealtimeStream, EodhdStreamQuote
from fastapi.testclient import TestClient
from app import main as app_main


def _settings() -> Settings:
    return Settings(
        database_url="",
        r2d2_start_date="2026-08-17",
        r2d2_checkpoint_days=90,
        r2d2_starting_capital_usd=1_000_000,
    )


def _service() -> R2D2PaperService:
    settings = _settings()
    return R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]


def _qualifying_entry_candidate(
    symbol: str,
    quote_as_of: datetime,
    *,
    composite_score: float = 78.0,
) -> dict[str, Any]:
    return {
        "market": "NASDAQ", "symbol": symbol, "name": f"{symbol} Corp", "currency": "USD",
        "price": 100.0, "stop_price": 99.1, "upside": 35.0, "risk_score": 30.0,
        "confidence": 80.0, "buy_in_distance": 4.0, "technical_score": 82.0,
        "technical_validated": True, "technical_reviewed": True, "quote_status": "live",
        "composite_score": composite_score, "fundamental_score": 82.0,
        "thesis": "Persistent live quality momentum", "quote_as_of": quote_as_of,
        "technical_indicators": {
            "data_status": "live", "trend_state": "bullish",
            "volume_state": "accumulation", "price_structure": "breakout",
            "relative_volume": 1.7, "vwap": 99.5, "ema8": 99.8, "ema20": 99.4,
            "momentum15": 0.3, "momentum30": 0.5, "momentum60": 0.8,
            "macd_histogram": 0.2, "macd_acceleration": 0.1,
            "rsi14": 60.0, "relative_strength": 0.4,
        },
    }


def _capacity_candidate(index: int) -> dict[str, Any]:
    market = "NASDAQ" if index % 2 == 0 else "NYSE"
    return {
        "market": market, "symbol": f"T{index:02d}", "name": f"Test {index}",
        "currency": "USD", "price": 100.0, "stop_price": 95.0,
        "upside": 45.0, "risk_score": 22.0, "confidence": 82.0,
        "buy_in_distance": 2.0, "technical_score": 78.0,
        "technical_validated": True, "quote_status": "live", "composite_score": 82.0,
        "fundamental_score": 84.0, "thesis": "Derived portfolio capacity test",
        "technical_indicators": {"atr_percent": 1.8},
        "quote_as_of": datetime.now(timezone.utc),
    }


def test_r2d2_start_date_accepts_compose_timestamp() -> None:
    assert _date_value("2026-08-17 00:00:00 +0000 UTC").isoformat() == "2026-08-17"


def test_r2d2_live_policy_has_no_position_count_gate() -> None:
    app_dir = Path(r2d2_module.__file__).resolve().parent
    milestone = (
        app_dir.parents[1] / "docs" / "ENTRY_QUALITY_STUDY_V1_POLICY_MILESTONES.md"
    ).read_text()
    policy_sources = "\n".join([
        (app_dir / "r2d2.py").read_text(),
        (app_dir / "config.py").read_text(),
        (app_dir.parents[1] / "compose.yml").read_text(),
    ])

    assert "r2d2_max_positions" not in policy_sources
    assert "C3PO_R2D2_MAX_POSITIONS" not in policy_sources
    assert "remaining_slots_after_buy" not in policy_sources
    assert "2026-08-31 18:14:27 UTC - live review window 550" in milestone
    assert "2026-08-31 19:11:00 UTC - persistent entry admission" in milestone
    assert "2026-08-31-derived-portfolio-capacity-v1" in milestone
    assert "Confirmation remains two consecutive reviews" in milestone
    assert "New positions remain capped at four per scan" in milestone


def test_quote_freshness_has_explicit_fresh_aging_and_stale_boundaries() -> None:
    now = datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc)

    assert _quote_freshness(now, now - timedelta(seconds=5)) == (5.0, "fresh")
    assert _quote_freshness(now, now - timedelta(seconds=6)) == (6.0, "aging")
    assert _quote_freshness(now, now - timedelta(seconds=30)) == (30.0, "aging")
    assert _quote_freshness(now, now - timedelta(seconds=31)) == (31.0, "stale")
    assert _quote_freshness(now, None) == (None, "unknown")


def test_listing_history_verdict_accepts_twenty_current_listing_sessions() -> None:
    history = [
        {"date": (date(2026, 7, 1) + timedelta(days=index)).isoformat()}
        for index in range(20)
    ]

    assert _listing_history_verdict(history, as_of=date(2026, 8, 1)) == (
        True,
        "eligible",
        20,
        date(2026, 7, 20),
    )


def test_listing_history_verdict_quarantines_a_new_post_gap_listing() -> None:
    history = [
        {"date": "2023-05-01"},
        {"date": "2023-05-02"},
        *[
            {"date": (date(2026, 8, 1) + timedelta(days=index)).isoformat()}
            for index in range(19)
        ],
    ]

    assert _listing_history_verdict(history, as_of=date(2026, 8, 26)) == (
        False,
        "new_listing_insufficient_history",
        19,
        date(2026, 8, 19),
    )


def test_listing_history_verdict_quarantines_stale_or_missing_history() -> None:
    assert _listing_history_verdict(
        [{"date": "2023-05-01"}],
        as_of=date(2026, 8, 26),
    ) == (False, "listing_history_stale", 0, date(2023, 5, 1))
    assert _listing_history_verdict([], as_of=date(2026, 8, 26)) == (
        False,
        "listing_history_missing",
        0,
        None,
    )


def test_listing_guard_does_not_cache_a_failed_history_fetch_for_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    settings.eodhd_api_token = "configured"
    service = R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]
    service.one_pagers = SimpleNamespace(market_data=SimpleNamespace(http=None))  # type: ignore[assignment]
    session_date = datetime.now(SAO_PAULO).date()
    calls = {"count": 0}

    class StubEodhdClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def histories(self, symbols: list[str], **kwargs: object) -> dict[str, list[dict[str, str]]]:
            calls["count"] += 1
            if calls["count"] == 1:
                return {}
            return {"NEWCO": [
                {"date": (session_date - timedelta(days=index + 1)).isoformat()}
                for index in range(25)
            ]}

    monkeypatch.setattr(r2d2_module, "EodhdClient", StubEodhdClient)

    first, first_stats = service._apply_us_listing_history_guard(
        [{"market": "NASDAQ", "symbol": "NEWCO"}],
    )
    assert first == []
    assert first_stats["listing_history_quarantined_count"] == 1
    assert first_stats["listing_history_quarantine_reasons"] == {"listing_history_missing": 1}
    assert "NEWCO" not in service._us_listing_history

    second, second_stats = service._apply_us_listing_history_guard(
        [{"market": "NASDAQ", "symbol": "NEWCO"}],
    )
    assert [item["symbol"] for item in second] == ["NEWCO"]
    assert second_stats["listing_history_quarantined_count"] == 0
    assert calls["count"] == 2


def test_r2d2_experiment_is_paper_only_continuous_and_has_90_day_checkpoint() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    dashboard = service.dashboard()

    assert dashboard.experiment_code == "R2D2-90D-001"
    assert dashboard.methodology_version == r2d2_module.METHODOLOGY_VERSION
    assert dashboard.start_date == "2026-08-17"
    assert dashboard.checkpoint_date == "2026-11-14"
    assert dashboard.checkpoint_days == 90
    assert dashboard.starting_capital_usd == 1_000_000
    assert dashboard.entries_paused is False
    assert dashboard.entries_paused_at is None
    assert experiment["mandate"]["mode"] == "paper_only"
    assert experiment["mandate"]["markets"] == ["NASDAQ", "NYSE"]
    assert "B3" in experiment["mandate"]["retired_markets"]
    assert experiment["mandate"]["real_broker_execution"] is False
    assert experiment["mandate"]["leverage"] is False
    assert experiment["mandate"]["short_selling"] is False
    assert experiment["mandate"]["continuous_operation"] is True
    assert experiment["mandate"]["checkpoint_is_termination"] is False
    assert experiment["mandate"]["exit_replacement"] == "immediate eligible scan across open US markets"
    assert "max_positions" not in experiment["mandate"]
    assert experiment["mandate"]["max_position_percent"] == 6.0
    assert experiment["mandate"]["max_cash_percent"] == 25.0
    assert experiment["mandate"]["minimum_invested_percent"] == 75.0
    assert experiment["mandate"]["minimum_cash_buffer_percent"] == 5.0
    assert experiment["mandate"]["max_gross_exposure_percent"] == 95.0
    assert experiment["mandate"]["position_capacity"] == {
        "milestone": "2026-08-31-derived-portfolio-capacity-v1",
        "position_count_limit": None,
        "confirmation_reviews": 2,
        "max_new_positions_per_scan": 4,
        "max_position_percent": 6.0,
        "max_market_percent": 48.0,
        "max_gross_exposure_percent": 95.0,
        "minimum_cash_buffer_percent": 5.0,
        "capacity_rule": (
            "position count emerges from per-name, per-market, gross-exposure "
            "and minimum-cash constraints"
        ),
    }
    assert experiment["mandate"]["position_sizing"]["minimum_percent"] == 2.0
    assert experiment["mandate"]["position_sizing"]["risk_budget_percent"] == 0.02
    assert experiment["mandate"]["position_sizing"]["maximum_percent"] == 6.0
    assert experiment["mandate"]["daily_order_target_range"] == [20, 80]
    assert experiment["mandate"]["max_daily_orders"] == 500
    assert experiment["mandate"]["opportunity_funnel"]["coverage"].startswith("full quoted EODHD catalog")
    assert experiment["mandate"]["opportunity_funnel"]["security_types"] == ["stocks", "ETFs"]
    assert experiment["mandate"]["opportunity_funnel"]["deep_shortlist_per_market"] == (
        "uncapped -- every symbol clearing the price/liquidity bar"
    )
    assert experiment["mandate"]["opportunity_funnel"]["technical_reviews_per_market"] == {
        "cash_deployment": 32,
        "standard": 24,
    }
    assert experiment["mandate"]["opportunity_funnel"]["realtime_symbol_capacity_total"] == 550
    assert experiment["mandate"]["opportunity_funnel"]["realtime_symbol_capacity_scope"] == (
        "shared across all US markets; open positions reserve capacity first"
    )
    assert experiment["mandate"]["opportunity_funnel"]["entry_confirmation_reviews"] == 2
    assert experiment["mandate"]["opportunity_funnel"]["max_new_positions_per_scan"] == 4
    assert experiment["mandate"]["turnover_policy"]["minimum_hold_minutes"] == 5
    assert experiment["mandate"]["performance_target_percent"] == 0.5
    assert "weekly_conviction" in experiment["mandate"]["horizon_policy"]
    assert dashboard.learning.version == 1


def test_r2d2_dashboard_separates_cumulative_nav_from_calendar_day_pnl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    service.ensure_initialized()
    realized_sessions = [
        {"session_date": date(2026, 8, 20), "realized_pnl_usd": -10_000},
        {"session_date": date(2026, 8, 21), "realized_pnl_usd": 4_000},
    ]
    monkeypatch.setattr(
        service.repo,
        "realized_pnl_by_session",
        lambda experiment_id: list(realized_sessions),
    )
    service.repo.memory["snapshots"][date(2026, 8, 20)] = {
        "session_date": date(2026, 8, 20),
        "nav_usd": 990_000,
        "cash_usd": 990_000,
        "daily_pnl_usd": -10_000,
        "daily_return_percent": -1.0,
        "gross_exposure_usd": 0,
        "open_positions": 0,
        "is_final": True,
    }
    service.repo.memory["snapshots"][date(2026, 8, 21)] = {
        "session_date": date(2026, 8, 21),
        "nav_usd": 994_000,
        "cash_usd": 994_000,
        "daily_pnl_usd": 4_000,
        "daily_return_percent": 0.404,
        "gross_exposure_usd": 0,
        "open_positions": 0,
        "is_final": True,
    }

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: timezone | None = None) -> datetime:
            value = datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc)
            return value.astimezone(tz) if tz else value

    monkeypatch.setattr(r2d2_module, "datetime", FrozenDateTime)

    weekend_dashboard = service.dashboard()

    assert weekend_dashboard.accounting_nav_usd == 994_000
    assert weekend_dashboard.cumulative_pnl_usd == -6_000
    assert weekend_dashboard.total_return_percent == -0.6
    assert weekend_dashboard.daily_pnl_usd == 4_000
    assert weekend_dashboard.daily_return_percent == 0.404
    assert weekend_dashboard.daily_pnl_date == "2026-08-21"

    service.repo.memory["snapshots"][date(2026, 8, 22)] = {
        "session_date": date(2026, 8, 22),
        "nav_usd": 993_500,
        "cash_usd": 993_500,
        "daily_pnl_usd": -500,
        "daily_return_percent": -0.0503,
        "gross_exposure_usd": 0,
        "open_positions": 0,
        "is_final": False,
    }
    realized_sessions.append({"session_date": date(2026, 8, 22), "realized_pnl_usd": -500})

    today_dashboard = service.dashboard()

    assert today_dashboard.accounting_nav_usd == 993_500
    assert today_dashboard.cumulative_pnl_usd == -6_500
    assert today_dashboard.daily_pnl_usd == -500
    assert today_dashboard.daily_return_percent == -0.0503
    assert today_dashboard.daily_pnl_date == "2026-08-22"


def test_r2d2_realized_track_keeps_prior_week_in_nav_but_not_daily_pnl() -> None:
    # Keep the historical marked snapshots deliberately wrong: the accounting
    # track must ignore them and reconstruct the factual ledger series below.
    track = r2d2_module._realized_daily_track(
        [
            {
                "session_date": date(2026, 8, 21),
                "nav_usd": 955_044.15,
                "daily_pnl_usd": -39_981.68,
                "is_final": True,
            },
            {
                "session_date": date(2026, 8, 24),
                "nav_usd": 983_844.15,
                "daily_pnl_usd": 28_800.00,
                "is_final": False,
            },
        ],
        [
            {"session_date": date(2026, 8, 17), "realized_pnl_usd": -1_467.729213},
            {"session_date": date(2026, 8, 18), "realized_pnl_usd": -10_522.671632},
            {"session_date": date(2026, 8, 19), "realized_pnl_usd": -6_537.063977},
            {"session_date": date(2026, 8, 20), "realized_pnl_usd": -15_898.264934},
            {"session_date": date(2026, 8, 21), "realized_pnl_usd": -10_374.558379},
            {"session_date": date(2026, 8, 24), "realized_pnl_usd": -8_565.600410},
        ],
        1_000_000,
    )

    assert track[-2]["accounting_nav_usd"] == pytest.approx(955_199.711865)
    assert track[-1]["daily_pnl_usd"] == pytest.approx(-8_565.600410)
    assert round(track[-1]["daily_return_percent"], 6) == -0.896734
    assert track[-1]["cumulative_pnl_usd"] == pytest.approx(-53_365.888545)
    assert track[-1]["accounting_nav_usd"] == pytest.approx(946_634.111455)


def test_r2d2_scans_full_us_catalog_and_promotes_stocks_and_etfs() -> None:
    service = _service()
    now = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
    rows = []
    catalog: dict[str, dict[str, str]] = {}
    for index in range(320):
        symbol = f"S{index:03d}"
        rows.append(SimpleNamespace(
            symbol=symbol,
            name=f"Stock {index}",
            price=20.0 + index / 10,
            cash_volume=25_000_000.0 + index * 100_000,
            change_percent=0.4,
            as_of=now,
            status="delayed",
        ))
        catalog[symbol] = {"Code": symbol, "Exchange": "NASDAQ", "Type": "Common Stock"}
    for index in range(60):
        symbol = f"E{index:03d}"
        rows.append(SimpleNamespace(
            symbol=symbol,
            name=f"ETF {index}",
            price=50.0 + index / 10,
            cash_volume=12_000_000.0 + index * 100_000,
            change_percent=0.3,
            as_of=now,
            status="delayed",
        ))
        catalog[symbol] = {"Code": symbol, "Exchange": "NASDAQ", "Type": "ETF"}

    service.realtime = SimpleNamespace(
        _us_investable_rows=lambda market, at: rows,
        _us_symbol_catalog=lambda at: catalog,
        _portfolio_catalog_market=lambda metadata: "NASDAQ",
        _is_portfolio_security=lambda metadata: True,
    )  # type: ignore[assignment]

    candidates = service._us_candidates("NASDAQ", now)

    assert len(candidates) == 380
    assert sum(item["security_type"] == "Stock" for item in candidates) == 320
    assert sum(item["security_type"] == "ETF" for item in candidates) == 60
    assert service._us_scan_counts["NASDAQ"] == {
        "universe_count": 380,
        "quoted_count": 380,
        "missing_quote_count": 0,
        "tradeable_count": 380,
        "stock_count": 320,
        "etf_count": 60,
        "deep_shortlist_count": 380,
    }


def test_r2d2_us_candidates_rejects_provisional_canonical_valuation() -> None:
    """Root-caused 2026-08-20: B3 candidates already require signal_quality
    == "validated" before R2D2 will trade on a canonical row (b3_screener.py's
    stricter gate); this US path -- R2D2's actual trading market -- had no
    equivalent check and would use a "provisional" canonical row exactly as
    trustingly as a validated one. A provisional row must now fall through
    instead of being read directly as canonical evidence.
    """
    service = _service()
    now = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(symbol="VALD", name="Validated Co", price=100.0, cash_volume=30_000_000.0,
                         change_percent=0.5, as_of=now, status="delayed"),
        SimpleNamespace(symbol="PROV", name="Provisional Co", price=100.0, cash_volume=30_000_000.0,
                         change_percent=0.5, as_of=now, status="delayed"),
    ]
    catalog = {
        "VALD": {"Code": "VALD", "Exchange": "NASDAQ", "Type": "Common Stock"},
        "PROV": {"Code": "PROV", "Exchange": "NASDAQ", "Type": "Common Stock"},
    }
    service.realtime = SimpleNamespace(
        _us_investable_rows=lambda market, at: rows,
        _us_symbol_catalog=lambda at: catalog,
        _portfolio_catalog_market=lambda metadata: "NASDAQ",
        _is_portfolio_security=lambda metadata: True,
    )  # type: ignore[assignment]
    service.repo.database.save_analysis_snapshot(
        "valuation_universe", "NASDAQ_UNIVERSE", "test-methodology",
        {},
        {"rows": [
            {"symbol": "VALD", "our_tp": 130.0, "risk_score": 40.0, "valuation_confidence": 80.0,
             "buy_in": 95.0, "score": 75.0, "signal_quality": "validated", "thesis": "validated thesis"},
            {"symbol": "PROV", "our_tp": 130.0, "risk_score": 40.0, "valuation_confidence": 60.0,
             "buy_in": 95.0, "score": 75.0, "signal_quality": "provisional", "thesis": "provisional thesis"},
        ]},
        now,
    )

    candidates = service._us_candidates("NASDAQ", now)

    by_symbol = {item["symbol"]: item for item in candidates}
    assert by_symbol["VALD"]["valuation_basis"] == "canonical C3PO valuation universe"
    assert by_symbol["PROV"]["valuation_basis"] != "canonical C3PO valuation universe"


def test_r2d2_interleaves_live_reviews_across_us_markets() -> None:
    service = _service()

    class FakeStream:
        symbols: list[str] = []

        def set_group(self, name: str, symbols: list[str], *, priority: int) -> None:
            assert name == "r2d2-analysis"
            assert priority == 110
            self.symbols = symbols

        @staticmethod
        def quote(symbol: str):
            return None

    stream = FakeStream()
    service.realtime = SimpleNamespace(stream=stream)  # type: ignore[assignment]
    service._technical_snapshot = (  # type: ignore[method-assign]
        lambda item: (_ for _ in ()).throw(ValueError("test stops after stream selection"))
    )
    candidates = [
        {
            "market": market,
            "symbol": f"{'Q' if market == 'NASDAQ' else 'Y'}{index}",
            "fundamental_score": 70.0 - index,
            "pretrade_rank": 80.0 - index,
            "day_change": 0.5,
            "technical_score": 50.0,
            "risk_score": 40.0,
            "confidence": 60.0,
            "upside": 25.0,
            "buy_in_distance": 5.0,
        }
        for market in ("NASDAQ", "NYSE")
        for index in range(3)
    ]

    service._enrich_technicals(candidates, review_limit=3)

    assert stream.symbols == ["Q0", "Y0", "Q1", "Y1", "Q2", "Y2"]


def test_r2d2_trims_review_batch_to_available_websocket_capacity() -> None:
    """Root-caused 2026-08-19: the EODHD WebSocket only carries max_symbols
    concurrent tickers (50 on the current plan); requesting more technical
    review slots than that guarantees some candidates never get a live tick
    and fail as "confirmation unavailable" every cycle, no matter how liquid
    they are. _enrich_technicals must trim the batch to what the stream can
    actually carry, keep the best-ranked candidates across both markets, and
    mark the rest not-reviewed so they cleanly wait for a future cycle
    instead of being evaluated on stale/default technicals.
    """
    service = _service()

    class FakeStream:
        symbols: list[str] = []

        def set_group(self, name: str, symbols: list[str], *, priority: int) -> None:
            self.symbols = symbols

        @staticmethod
        def quote(symbol: str):
            return None

    stream = FakeStream()
    service.realtime = SimpleNamespace(stream=stream)  # type: ignore[assignment]
    service._technical_snapshot = (  # type: ignore[method-assign]
        lambda item: (_ for _ in ()).throw(ValueError("test stops after stream selection"))
    )
    candidates = [
        {
            "market": market,
            "symbol": f"{'Q' if market == 'NASDAQ' else 'Y'}{index}",
            "fundamental_score": 70.0 - index,
            "pretrade_rank": 80.0 - index,
            "day_change": 0.5,
            "technical_score": 50.0,
            "risk_score": 40.0,
            "confidence": 60.0,
            "upside": 25.0,
            "buy_in_distance": 5.0,
        }
        for market in ("NASDAQ", "NYSE")
        for index in range(3)
    ]

    service._enrich_technicals(candidates, review_limit=3, max_ws_symbols=4)

    # Q0/Y0 (rank 80) and Q1/Y1 (rank 79) fit within the 4-symbol budget; Q2/Y2
    # (rank 78, the weakest) are bumped.
    assert stream.symbols == ["Q0", "Y0", "Q1", "Y1"]
    reviewed = {item["symbol"]: item["technical_reviewed"] for item in candidates}
    assert reviewed == {"Q0": True, "Y0": True, "Q1": True, "Y1": True, "Q2": False, "Y2": False}


def test_contracted_websocket_capacity_is_global_and_wired_to_worker() -> None:
    settings = _settings()
    settings.r2d2_deployment_technical_review_per_market = 350
    settings.r2d2_standard_technical_review_per_market = 350

    assert settings.r2d2_deployment_technical_review_per_market == 350
    assert settings.r2d2_standard_technical_review_per_market == 350
    assert settings.r2d2_ws_max_symbols == 550

    worker_source = (
        Path(__file__).resolve().parents[1] / "app" / "r2d2_worker.py"
    ).read_text(encoding="utf-8")
    assert "max_symbols=settings.r2d2_ws_max_symbols" in worker_source


def test_r2d2_keeps_websocket_window_for_grace_then_rotates_deterministically() -> None:
    service = _service()
    service.settings.r2d2_ws_rotation_grace_cycles = 3
    service.settings.r2d2_ws_rotation_core_percent = 50.0
    candidates = [
        {
            "market": "NASDAQ",
            "symbol": f"Q{index}",
            "fundamental_score": 80.0 - index,
            "pretrade_rank": 100.0 - index,
        }
        for index in range(8)
    ]

    batches = [
        [item["symbol"] for item in service._rotating_ws_batch(candidates, 4)[0]]
        for _ in range(4)
    ]

    assert batches[:3] == [["Q0", "Q1", "Q2", "Q3"]] * 3
    assert batches[3] == ["Q0", "Q1", "Q4", "Q5"]


def test_r2d2_rotation_never_displaces_stable_top_ranked_core() -> None:
    service = _service()
    service.settings.r2d2_ws_rotation_grace_cycles = 1
    service.settings.r2d2_ws_rotation_core_percent = 50.0
    candidates = [
        {
            "market": "NYSE",
            "symbol": f"Y{index}",
            "fundamental_score": 80.0 - index,
            "pretrade_rank": 100.0 - index,
        }
        for index in range(8)
    ]

    for _ in range(6):
        batch, stats = service._rotating_ws_batch(candidates, 4)
        assert [item["symbol"] for item in batch[:2]] == ["Y0", "Y1"]
        assert stats["core_count"] == 2
        assert stats["rotating_count"] == 2


def test_fmp_prefilter_promotes_fresh_quotes_without_dropping_other_candidates() -> None:
    service = _service()
    service.settings.fmp_api_token = "configured"
    now = datetime.now(timezone.utc)
    service.one_pagers = SimpleNamespace(  # type: ignore[assignment]
        market_data=SimpleNamespace(http=object()),
    )
    candidates = [
        {"symbol": "STRONG", "pretrade_rank": 100.0, "fundamental_score": 90.0},
        {"symbol": "FRESH", "pretrade_rank": 70.0, "fundamental_score": 60.0},
        {"symbol": "STALE", "pretrade_rank": 80.0, "fundamental_score": 70.0},
    ]
    service._fmp_quote_cache = {
        "STRONG": (now, {"timestamp": int(now.timestamp()) - 500, "price": 100.0}),
        "FRESH": (now, {"timestamp": int(now.timestamp()), "price": 50.0}),
        "STALE": (now, {"timestamp": int(now.timestamp()) - 500, "price": 80.0}),
    }

    ranked, stats = service._fmp_prefilter_ws_candidates(candidates)

    assert [item["symbol"] for item in ranked] == ["FRESH", "STRONG", "STALE"]
    assert len(ranked) == len(candidates)
    assert stats["fmp_prefilter_fresh_count"] == 1
    assert stats["fmp_prefilter_fallback"] is False


def test_fmp_prefilter_falls_back_to_existing_order_without_fresh_quotes() -> None:
    service = _service()
    service.settings.fmp_api_token = "configured"
    now = datetime.now(timezone.utc)
    service.one_pagers = SimpleNamespace(  # type: ignore[assignment]
        market_data=SimpleNamespace(http=object()),
    )
    candidates = [
        {"symbol": "A", "pretrade_rank": 90.0, "fundamental_score": 80.0},
        {"symbol": "B", "pretrade_rank": 80.0, "fundamental_score": 70.0},
    ]
    service._fmp_quote_cache = {
        "A": (now, {"timestamp": int(now.timestamp()) - 500, "price": 100.0}),
        "B": (now, {"timestamp": int(now.timestamp()) - 500, "price": 90.0}),
    }

    ranked, stats = service._fmp_prefilter_ws_candidates(candidates)

    assert ranked == candidates
    assert stats["fmp_prefilter_fallback"] is True


def test_fmp_prefilter_negative_caches_uncovered_symbols_and_fetches_only_delta(monkeypatch) -> None:
    service = _service()
    service.settings.fmp_api_token = "configured"
    service.one_pagers = SimpleNamespace(  # type: ignore[assignment]
        market_data=SimpleNamespace(http=object()),
    )
    fetched_batches = []

    def fake_batch_quotes(self, symbols, *, chunk_size, diagnostics):
        fetched_batches.append(list(symbols))
        diagnostics.update({
            "successful_symbols": list(symbols), "failed_symbols": [],
            "failed_chunk_count": 0, "failure_types": [],
        })
        return {
            symbol: {"symbol": symbol, "price": 100.0, "timestamp": int(datetime.now(timezone.utc).timestamp())}
            for symbol in symbols if symbol != "UNCOVERED"
        }

    monkeypatch.setattr("app.r2d2.FmpClient.batch_quotes", fake_batch_quotes)
    first = [
        {"symbol": "A", "pretrade_rank": 90.0, "fundamental_score": 80.0},
        {"symbol": "UNCOVERED", "pretrade_rank": 80.0, "fundamental_score": 70.0},
    ]
    service._fmp_prefilter_ws_candidates(first)
    second = [
        *first,
        {"symbol": "DELTA", "pretrade_rank": 70.0, "fundamental_score": 60.0},
    ]
    _, stats = service._fmp_prefilter_ws_candidates(second)

    assert fetched_batches == [["A", "UNCOVERED"], ["DELTA"]]
    assert service._fmp_quote_cache["UNCOVERED"][1] is None
    assert stats["fmp_prefilter_cache_hit_count"] == 2
    assert stats["fmp_prefilter_fetched_symbol_count"] == 1


def test_r2d2_core_identity_survives_rank_changes_between_cycles() -> None:
    service = _service()
    service.settings.r2d2_ws_rotation_grace_cycles = 1
    service.settings.r2d2_ws_rotation_core_percent = 50.0
    candidates = [
        {
            "market": "NASDAQ",
            "symbol": f"Q{index}",
            "fundamental_score": 80.0 - index,
            "pretrade_rank": 100.0 - index,
        }
        for index in range(8)
    ]

    first, first_stats = service._rotating_ws_batch(candidates, 4)
    assert [item["symbol"] for item in first[:2]] == ["Q0", "Q1"]
    assert first_stats["core_retained_count"] == 0
    assert first_stats["core_replaced_count"] == 2

    # A fresh ranking would previously rebuild the core as Q7/Q6 and evict
    # both subscriptions before they had time to accumulate live bars.
    reranked = [
        {**item, "pretrade_rank": float(index)}
        for index, item in enumerate(candidates)
    ]
    second, second_stats = service._rotating_ws_batch(reranked, 4)

    assert [item["symbol"] for item in second[:2]] == ["Q0", "Q1"]
    assert second_stats["core_retained_count"] == 2
    assert second_stats["core_replaced_count"] == 0


def test_r2d2_position_sizing_is_risk_normalized_not_conviction_scored() -> None:
    """Replaced 2026-08-20: sizing is now Turtle-style risk-normalized -- a
    flat RISK_BUDGET_PERCENT of NAV, sized inversely to the ATR-derived stop
    distance. Backtested against the prior conviction/risk/volatility-scored
    formula (which let position size drift independently of how far away the
    stop actually was) and found to produce the best risk-adjusted profile of
    the three risk budgets tested. composite/confidence/risk_score no longer
    factor into sizing at all -- only atr_percent does.
    """
    # RISK_BUDGET_PERCENT lowered from 0.03 to 0.02 on 2026-08-20 (test-phase
    # trade-count goal) shrinks the achievable range above the 2.0% floor --
    # these ATR values were re-picked to stay distinctly above it.
    service = _service()
    low_vol = {"technical_indicators": {"atr_percent": 0.2}}
    mid_vol = {"technical_indicators": {"atr_percent": 0.35}}
    high_vol = {"technical_indicators": {"atr_percent": 0.5}}

    low_vol_size = service._target_position_percent(low_vol)
    mid_vol_size = service._target_position_percent(mid_vol)
    high_vol_size = service._target_position_percent(high_vol)

    assert low_vol_size == 3.08
    assert mid_vol_size == 2.86
    assert high_vol_size == 2.0
    assert low_vol_size > mid_vol_size > high_vol_size


def test_r2d2_cash_overhang_no_longer_influences_position_sizing() -> None:
    """Replaced 2026-08-20: the old deployment_adjustment term boosted size
    for ANY approved candidate on a high-cash day, independent of conviction
    or risk -- exactly the kind of size-inflation the risk-normalized formula
    is meant to prevent. cash_overhang_percent is still accepted for call-site
    compatibility but is now a no-op.
    """
    service = _service()
    item = {"technical_indicators": {"atr_percent": 0.5}}

    normal_size = service._target_position_percent(item)
    deployment_size = service._target_position_percent(item, cash_overhang_percent=50.0)

    assert deployment_size == normal_size


def test_r2d2_buy_records_dynamic_position_size_in_trade_audit() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": "SIZE", "name": "Sizing Corp", "currency": "USD",
        "price": 100.0, "stop_price": 95.0, "upside": 45.0, "risk_score": 22.0,
        "confidence": 82.0, "buy_in_distance": 2.0, "technical_score": 78.0,
        "technical_validated": True, "quote_status": "live", "composite_score": 82.0,
        "fundamental_score": 84.0, "thesis": "High-conviction sizing test",
        "technical_indicators": {"atr_percent": 1.8},
        "quote_as_of": datetime.now(timezone.utc),
    }

    trade = service._buy(experiment, cycle_id, candidate, [], candidate["quote_as_of"])

    assert trade is not None
    assert trade["decision_snapshot"]["sizing_model"] == "risk-normalized (Turtle-style)"
    # atr_percent 1.8 pushes the ATR-derived stop distance past the 1.5% cap,
    # so the risk-normalized formula bottoms out at the 2.0% floor here --
    # unlike the old conviction-scored formula, sizing no longer rewards a
    # high composite/confidence/technical_score directly.
    assert trade["decision_snapshot"]["target_position_percent"] == 2.0
    assert 1.99 <= trade["decision_snapshot"]["actual_position_percent"] <= 2.0
    assert trade["decision_snapshot"]["cash_deployment_mode"] is True
    assert trade["decision_snapshot"]["cash_ceiling_percent"] == 25.0
    assert 19_900 <= trade["gross_value_usd"] <= 20_000


def test_r2d2_buy_preserves_technical_entry_reason_separately_from_ranking_thesis() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": "AUDIT", "name": "Audit Corp", "currency": "USD",
        "price": 100.0, "stop_price": 95.0, "upside": 45.0, "risk_score": 22.0,
        "confidence": 82.0, "buy_in_distance": 2.0, "technical_score": 78.0,
        "technical_validated": True, "quote_status": "live", "composite_score": 82.0,
        "fundamental_score": 84.0,
        "thesis": "C3PO TP 150.00; valuation backfill completed for the current session.",
        "technical_indicators": {"atr_percent": 1.8},
        "quote_as_of": datetime.now(timezone.utc),
    }
    technical_reason = "Tactical quality-momentum route passed with live volume confirmation."

    trade = service._buy(
        experiment, cycle_id, candidate, [], candidate["quote_as_of"],
        entry_reasons=[technical_reason],
    )

    assert trade is not None
    assert trade["reason"].startswith(technical_reason)
    assert "valuation backfill" not in trade["reason"]
    assert trade["decision_snapshot"]["entry_decision_reasons"] == [technical_reason]
    assert "valuation backfill" in trade["decision_snapshot"]["ranking_thesis"]


def test_r2d2_derived_capacity_carries_forty_five_positions_through_risk_monitor() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ", "NYSE"])
    for index in range(45):
        candidate = _capacity_candidate(index)
        trade = service._buy(
            experiment, cycle_id, candidate, service.repo.positions(experiment["id"]),
            candidate["quote_as_of"],
        )
        assert trade is not None

    dashboard = service.dashboard()
    assert dashboard.open_positions == 45
    assert 88.0 <= dashboard.gross_exposure_usd / dashboard.nav_usd * 100 <= 91.0
    assert dashboard.cash_usd / dashboard.nav_usd * 100 >= 5.0

    groups: list[tuple[str, list[str], int]] = []
    seen_positions: list[int] = []

    class CaptureStream:
        max_symbols = 550

        def __init__(self, quotes: dict[str, Any]) -> None:
            self.quotes = quotes

        def set_group(self, name: str, symbols: list[str], *, priority: int) -> None:
            groups.append((name, list(symbols), priority))

        def quote(self, symbol: str) -> Any:
            return self.quotes.get(symbol)

    monitor_at = datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc)
    stream_quotes = {
        position.symbol: SimpleNamespace(
            price=position.last_price_local,
            as_of=monitor_at,
        )
        for position in dashboard.positions
    }
    service.realtime = SimpleNamespace(  # type: ignore[assignment]
        stream=CaptureStream(stream_quotes),
    )
    service._position_quotes = (  # type: ignore[method-assign]
        lambda positions, now: seen_positions.append(len(positions)) or {}
    )
    service._mark_and_exit = lambda *args, **kwargs: 0  # type: ignore[method-assign]

    exits = service.run_risk_monitor_cycle(monitor_at)
    fast_started = perf_counter()
    fast_exits = service.run_fast_risk_watcher_cycle(monitor_at)
    fast_elapsed = perf_counter() - fast_started

    assert exits == 0
    assert fast_exits == 0
    assert fast_elapsed < 5.0
    assert seen_positions == [45]
    expected_group = ("r2d2-positions", [f"T{index:02d}" for index in range(45)], 200)
    assert groups == [expected_group, expected_group]
    assert CaptureStream.max_symbols - dashboard.open_positions == 505


def test_r2d2_entry_capacity_is_bound_by_each_signed_portfolio_constraint() -> None:
    service = _service()
    item = {"market": "NASDAQ"}

    def dashboard(*, market: float = 0.0, gross: float = 0.0, cash: float = 1_000_000.0) -> Any:
        positions = (
            [SimpleNamespace(market="NASDAQ", market_value_usd=market)] if market else []
        )
        return SimpleNamespace(
            nav_usd=1_000_000.0,
            cash_usd=cash,
            gross_exposure_usd=gross,
            positions=positions,
        )

    assert service._entry_capacity_usd(item, dashboard()) == 60_000.0
    assert service._entry_capacity_usd(item, dashboard(market=470_000.0)) == 10_000.0
    assert service._entry_capacity_usd(item, dashboard(gross=940_000.0)) == 9_500.0
    assert service._entry_capacity_usd(item, dashboard(cash=8_000.0)) == 8_000.0
    service.settings.r2d2_max_gross_exposure_percent = 99.0
    assert service._entry_capacity_usd(item, dashboard(gross=940_000.0)) == 9_500.0


def test_r2d2_derived_capacity_stops_at_gross_limit_instead_of_position_count() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ", "NYSE"])
    trades = []

    for index in range(48):
        candidate = _capacity_candidate(index)
        trades.append(service._buy(
            experiment,
            cycle_id,
            candidate,
            service.repo.positions(experiment["id"]),
            candidate["quote_as_of"],
        ))

    dashboard = service.dashboard()
    assert all(trade is not None for trade in trades[:47])
    assert trades[47] is None
    assert dashboard.open_positions == 47
    assert dashboard.gross_exposure_usd / dashboard.nav_usd * 100 <= 95.0
    assert dashboard.cash_usd / dashboard.nav_usd * 100 >= 5.0


def test_r2d2_derived_capacity_rotates_without_breaching_signed_limits() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ", "NYSE"])
    for index in range(47):
        candidate = _capacity_candidate(index)
        assert service._buy(
            experiment,
            cycle_id,
            candidate,
            service.repo.positions(experiment["id"]),
            candidate["quote_as_of"],
        ) is not None

    rotation_at = datetime.now(timezone.utc)
    for position in service.repo.memory["positions"].values():
        position["opened_at"] = rotation_at - timedelta(minutes=20)
        position["strategy_snapshot"]["live_composite_score"] = 60.0
        position["strategy_snapshot"]["technical_score"] = 40.0
    replacement = _qualifying_entry_candidate(
        "ROTATE", rotation_at, composite_score=90.0,
    )
    replacement["market"] = "NYSE"
    replacement["technical_indicators"]["atr_percent"] = 1.8
    positions = service.repo.positions(experiment["id"])
    quotes = {
        (position["market"], position["symbol"]): SimpleNamespace(
            price=position["last_price_local"],
            as_of=rotation_at,
            status="live",
        )
        for position in positions
    }

    assert service._has_entry_capacity(replacement) is False
    trades = service._rotate_if_better(
        experiment, cycle_id, replacement, positions, quotes, rotation_at,
    )

    dashboard = service.dashboard()
    assert trades == 2
    assert dashboard.open_positions == 47
    assert any(position.symbol == "ROTATE" for position in dashboard.positions)
    assert dashboard.gross_exposure_usd / dashboard.nav_usd * 100 <= 95.0
    assert dashboard.cash_usd / dashboard.nav_usd * 100 >= 5.0


def test_r2d2_keeps_scheduling_cycles_after_90_day_checkpoint() -> None:
    service = _service()
    dashboard = service.run_cycle(datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc))

    assert dashboard.last_cycle is not None
    assert dashboard.last_cycle.status == "market_closed"


def test_r2d2_daily_learning_is_versioned_and_tightens_with_weak_evidence() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    service.repo.memory["learning"].clear()
    service._ensure_daily_learning(experiment, date(2026, 8, 24))
    for offset in range(5):
        session_date = date(2026, 8, 18) + timedelta(days=offset)
        service.repo.memory["snapshots"][session_date] = {
            "session_date": session_date,
            "nav_usd": 1_000_000 - (offset + 1) * 10_000,
            "cash_usd": 1_000_000,
            "daily_pnl_usd": -10_000,
            "daily_return_percent": -1.0,
            "gross_exposure_usd": 0,
            "open_positions": 0,
            "is_final": True,
        }
    for offset in range(8):
        service.repo.memory["trades"].append({
            "experiment_id": experiment["id"],
            "side": "SELL",
            "realized_pnl_usd": -1_000,
            "executed_at": datetime(2026, 8, 18, 18, offset, tzinfo=timezone.utc),
        })

    state = service._ensure_daily_learning(experiment, date(2026, 8, 25))

    assert state["version"] == 2
    assert state["parameters"]["entry_upside_floor"] == 20.5
    assert state["parameters"]["max_risk_score"] == 47.5
    assert "tightened" in state["rationale"][0]


def test_r2d2_market_windows_cover_only_live_us_execution_markets() -> None:
    regular_open = datetime(2026, 8, 17, 13, 30, tzinfo=timezone.utc)
    simultaneous_session = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
    after_close = datetime(2026, 8, 17, 22, 0, tzinfo=timezone.utc)

    assert R2D2PaperService.risk_markets(regular_open) == ["NASDAQ", "NYSE"]
    assert R2D2PaperService.open_markets(regular_open) == []
    assert R2D2PaperService.open_markets(simultaneous_session) == ["NASDAQ", "NYSE"]
    assert R2D2PaperService.open_markets(after_close) == []


def test_r2d2_entry_requires_fundamental_and_intraday_confirmation() -> None:
    service = _service()
    candidate = {
        "upside": 35.0,
        "risk_score": 35.0,
        "confidence": 75.0,
        "buy_in_distance": 5.0,
        "technical_score": 70.0,
        "technical_validated": False,
        "composite_score": 72.0,
        "thesis": "Validated valuation",
    }

    action, reasons = service._entry_decision(candidate)
    assert action == "REJECT"
    assert "technical confirmation" in reasons[0]

    candidate["technical_validated"] = True
    action, reasons = service._entry_decision(candidate)
    assert action == "REJECT"
    assert "Neither strict tactical nor cost-aware intraday entry route" in reasons[-1]


def test_r2d2_entry_does_not_fall_back_to_aggregate_scores() -> None:
    service = _service()
    candidate = {
        "market": "NASDAQ", "quote_status": "live", "price": 101.0,
        "upside": 35.0, "risk_score": 30.0, "confidence": 80.0,
        "buy_in_distance": 4.0, "technical_score": 80.0,
        "technical_validated": True, "composite_score": 82.0,
        "thesis": "Aggregate scores pass but strict timing does not",
        "technical_indicators": {
            "data_status": "live", "trend_state": "neutral",
            "volume_state": "accumulation", "price_structure": "breakout",
            "relative_volume": 2.0, "vwap": 100.5,
            "ema8": 100.8, "ema20": 100.4,
            "momentum15": 0.3, "momentum30": 0.5, "momentum60": 0.8,
            "macd_histogram": 0.2, "macd_acceleration": 0.1,
            "rsi14": 78.0, "relative_strength": 0.4,
        },
    }

    action, reasons = service._entry_decision(candidate)

    assert action == "REJECT"
    assert "Neither strict tactical nor cost-aware intraday entry route" in reasons[-1]


def test_r2d2_buy_checks_quote_age_against_fill_time(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    fill_now = datetime(2026, 8, 21, 16, 0, tzinfo=timezone.utc)
    stale_tick = fill_now - timedelta(seconds=91)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: timezone | None = None) -> datetime:
            return fill_now

    monkeypatch.setattr(r2d2_module, "datetime", FrozenDateTime)
    service.realtime = SimpleNamespace(
        stream=SimpleNamespace(
            quote=lambda symbol: SimpleNamespace(price=100.0, as_of=stale_tick),
        ),
    )
    candidate = {
        "market": "NASDAQ", "symbol": "STALE", "name": "Stale Tick Corp",
        "currency": "USD", "price": 100.0, "stop_price": 99.0,
        "quote_status": "live", "quote_as_of": stale_tick,
        "technical_indicators": {"atr_percent": 1.0},
    }

    trade = service._buy(
        experiment, cycle_id, candidate, [], fill_now - timedelta(minutes=5),
    )

    assert trade is None
    assert service.repo.positions(experiment["id"]) == []


def test_r2d2_virtual_ledger_records_buy_sell_costs_and_realized_pnl() -> None:
    settings = _settings()
    repository = R2D2Repository(Database(settings))
    experiment = repository.ensure_experiment(settings)
    cycle_id = repository.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": "TEST", "name": "Test Corp", "currency": "USD",
        "stop_price": 95.0, "fundamental_score": 80.0, "technical_score": 75.0,
        "risk_score": 25.0, "composite_score": 78.0,
    }
    as_of = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)

    repository.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=100,
        signal_price=100.0, fill_price=100.1, fx=1.0, fees=4.0, slippage=10.0,
        reason="test entry", decision=candidate, quote_as_of=as_of,
    )
    assert round(experiment["cash_balance"], 2) == 989_986.0
    assert repository.positions(experiment["id"])[0]["quantity"] == 100

    trade = repository.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="SELL", quantity=100,
        signal_price=103.0, fill_price=102.9, fx=1.0, fees=4.0, slippage=10.0,
        reason="test exit", decision=candidate, quote_as_of=as_of,
    )
    assert repository.positions(experiment["id"]) == []
    assert round(experiment["cash_balance"], 2) == 1_000_272.0
    assert round(float(trade["realized_pnl_usd"]), 2) == 272.0
    assert round(float(trade["realized_return_percent"]), 2) == 2.72
    assert repository.realized_pnl_by_session(experiment["id"]) == [
        {
            "session_date": trade["executed_at"].astimezone(SAO_PAULO).date(),
            "realized_pnl_usd": 272.0,
        }
    ]
    assert len(repository.trades(experiment["id"])) == 2
    assert repository.trade_summary(experiment["id"]) == {
        "total_transactions": 2,
        "positive_transactions": 1,
        "negative_transactions": 0,
    }


def test_r2d2_loss_sale_returns_full_net_proceeds_to_cash() -> None:
    settings = _settings()
    repository = R2D2Repository(Database(settings))
    experiment = repository.ensure_experiment(settings)
    cycle_id = repository.start_cycle(experiment["id"], ["NYSE"])
    candidate = {
        "market": "NYSE", "symbol": "LOSS", "name": "Loss Test Corp", "currency": "USD",
        "stop_price": 94.0, "fundamental_score": 70.0, "technical_score": 60.0,
        "risk_score": 40.0, "composite_score": 65.0,
    }
    as_of = datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc)

    repository.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=100,
        signal_price=100.0, fill_price=100.0, fx=1.0, fees=4.0, slippage=0.0,
        reason="test entry", decision=candidate, quote_as_of=as_of,
    )
    assert round(experiment["cash_balance"], 2) == 989_996.0

    trade = repository.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="SELL", quantity=100,
        signal_price=95.0, fill_price=95.0, fx=1.0, fees=4.0, slippage=0.0,
        reason="test loss exit", decision=candidate, quote_as_of=as_of,
    )

    assert repository.positions(experiment["id"]) == []
    assert round(experiment["cash_balance"], 2) == 999_492.0
    assert round(float(trade["gross_value_usd"] - trade["fees_usd"]), 2) == 9_496.0
    assert round(float(trade["realized_pnl_usd"]), 2) == -508.0


def test_r2d2_dashboard_api_contract() -> None:
    with TestClient(app_main.app) as client:
        response = client.get("/api/v1/r2d2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["starting_capital_usd"] == 1_000_000
    assert set(payload["stats"]) >= {
        "positive_days", "above_half_percent_days", "negative_days",
        "below_minus_half_percent_days", "total_transactions",
        "positive_transactions", "negative_transactions",
    }
    assert set(payload["today_episode_stats"]) == {
        "session_date", "closed_episodes", "decided_episodes",
        "positive_episodes", "negative_episodes", "flat_episodes",
        "win_rate_percent",
    }
    assert payload["mandate"]["real_broker_execution"] is False
    assert payload["mandate"]["continuous_operation"] is True
    assert "end_date" not in payload
    assert payload["learning"]["version"] >= 1


def test_r2d2_live_positions_uses_fresh_stream_marks_without_loading_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    observed_at = datetime.now(timezone.utc)
    candidate = {
        "market": "NASDAQ",
        "symbol": "LIVE",
        "name": "Live Mark Corp",
        "currency": "USD",
        "stop_price": 95.0,
        "decision_state": "awaiting live quote",
        "live_technical": {
            "score": 72.0,
            "trend_state": "uptrend",
            "volume_state": "confirmed",
            "data_status": "live",
            "as_of": observed_at.isoformat(),
        },
        "technical_defense": {
            "score": 55.0,
            "severity": "reduce",
            "drivers": ["price below VWAP", "price below EMA8"],
        },
        "defense_streak": 1,
        "defense_reductions": 0,
        "last_review_at": observed_at.isoformat(),
    }
    service.repo.execute_trade(
        experiment,
        cycle_id=cycle_id,
        candidate=candidate,
        side="BUY",
        quantity=10,
        signal_price=100.0,
        fill_price=100.0,
        fx=1.0,
        fees=0.0,
        slippage=0.0,
        reason="live telemetry test",
        decision=candidate,
        quote_as_of=observed_at,
    )

    class Stream:
        group: tuple[str, list[str], int] | None = None

        def set_group(self, name: str, symbols: list[str], *, priority: int) -> None:
            self.group = (name, symbols, priority)

        @staticmethod
        def quote(symbol: str) -> EodhdStreamQuote:
            assert symbol == "LIVE"
            return EodhdStreamQuote(symbol=symbol, price=105.0, as_of=observed_at, market_state="open")

    stream = Stream()
    service.realtime = SimpleNamespace(stream=stream)  # type: ignore[assignment]
    monkeypatch.setattr(
        service.repo,
        "snapshots",
        lambda experiment_id: pytest.fail("live telemetry must not load dashboard history"),
    )

    payload = service.live_positions()

    assert payload.refresh_seconds == 1
    assert payload.open_positions == 1
    assert payload.gross_exposure_usd == 1_050.0
    assert payload.nav_usd == 1_000_050.0
    assert stream.group == ("r2d2-dashboard", ["LIVE"], 140)
    position = payload.positions[0]
    assert position.last_price_local == 105.0
    assert position.market_value_usd == 1_050.0
    assert position.unrealized_pnl_usd == 50.0
    assert position.unrealized_return_percent == 5.0
    assert position.mark_pnl_usd == 50.0
    assert position.mark_return_percent == 5.0
    assert position.estimated_exit_pnl_usd == 48.53
    assert position.estimated_exit_return_percent == 4.853042
    assert position.quote_status == "live"
    assert position.quote_as_of == observed_at
    assert position.quote_age_seconds is not None
    assert position.quote_age_seconds < 5
    assert position.quote_freshness == "fresh"
    assert position.decision_state == "live monitoring"
    assert position.technical_defense_score == 55.0
    assert position.technical_defense_severity == "reduce"
    assert position.technical_defense_reviews == 1
    assert position.technical_defense_reductions == 0
    assert position.technical_defense_drivers == ["price below VWAP", "price below EMA8"]
    assert position.technical_defense_reviewed_at == observed_at


def test_r2d2_episode_summary_consolidates_partial_legs_and_exclusions() -> None:
    session_date = date(2026, 8, 24)
    start = datetime(2026, 8, 24, 13, 30, tzinfo=timezone.utc)
    trades: list[dict[str, object]] = []

    def leg(
        identifier: str,
        symbol: str,
        side: str,
        quantity: float,
        minutes: int,
        realized_pnl_usd: float | None = None,
        decision_snapshot: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            "id": identifier,
            "market": "NASDAQ",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "realized_pnl_usd": realized_pnl_usd,
            "decision_snapshot": decision_snapshot or {},
            "executed_at": start + timedelta(minutes=minutes),
        }

    # One winning episode and one losing episode, each closed in two SELL legs.
    trades.extend([
        leg("a-buy", "A", "BUY", 10, 0),
        leg("a-partial", "A", "SELL", 4, 10, 40),
        leg("a-final", "A", "SELL", 6, 20, -10),
        leg("b-buy", "B", "BUY", 8, 30),
        leg("b-partial", "B", "SELL", 3, 40, 5),
        leg("b-final", "B", "SELL", 5, 50, -15),
        leg("flat-buy", "FLAT", "BUY", 2, 60),
        leg("flat-sell", "FLAT", "SELL", 2, 70, 0),
    ])
    # Administrative liquidation closes inventory but is not a strategy episode.
    trades.extend([
        leg("wind-buy", "WIND", "BUY", 1, 80),
        leg(
            "wind-sell", "WIND", "SELL", 1, 90, 500,
            {"operator_wind_down": {"operator": "Dudu"}},
        ),
    ])
    # A corrected exit censors its episode without poisoning a later clean re-entry.
    trades.extend([
        leg("bad-buy", "BAD", "BUY", 1, 100),
        leg(
            "corrected", "BAD", "SELL", 1, 110, -999,
            {"correction": {"operator": "Dudu"}},
        ),
        leg("bad-rebuy", "BAD", "BUY", 1, 120),
        leg("bad-clean-sell", "BAD", "SELL", 1, 130, 20),
    ])

    summary = _episode_summary_from_trades(trades, session_date)

    details = summary.pop("closed_episode_details")
    assert summary == {
        "session_date": "2026-08-24",
        "closed_episodes": 4,
        "decided_episodes": 3,
        "positive_episodes": 2,
        "negative_episodes": 1,
        "flat_episodes": 1,
        "win_rate_percent": 66.67,
    }
    # The same walk now also names each strategy-eligible closed episode;
    # excluded episodes (wind-down, corrected) never appear in the details.
    assert [
        (item["episode_id"], item["net_realized_pnl_usd"]) for item in details
    ] == [
        ("NASDAQ:A:a-buy", 30.0),
        ("NASDAQ:B:b-buy", -10.0),
        ("NASDAQ:FLAT:flat-buy", 0.0),
        ("NASDAQ:BAD:bad-rebuy", 20.0),
    ]


def test_r2d2_live_positions_api_contract() -> None:
    with TestClient(app_main.app) as client:
        response = client.get("/api/v1/r2d2/live-positions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["refresh_seconds"] == 1
    assert payload["open_positions"] == len(payload["positions"])
    assert set(payload) == {
        "generated_at", "refresh_seconds", "nav_usd", "cash_usd",
        "gross_exposure_usd", "open_positions", "positions",
    }


def test_eodhd_stream_aggregates_live_trades_into_five_minute_bars() -> None:
    stream = EodhdRealtimeStream("test-token")
    base = int(datetime(2026, 8, 17, 14, 1, tzinfo=timezone.utc).timestamp() * 1000)
    stream._record(json.dumps({"s": "MSFT", "p": 500.0, "v": 10, "t": base, "ms": "open"}))
    stream._record(json.dumps({"s": "MSFT", "p": 502.0, "v": 15, "t": base + 60_000, "ms": "open"}))
    stream._record(json.dumps({"s": "MSFT", "p": 499.0, "v": 20, "t": base + 5 * 60_000, "ms": "open"}))

    bars = stream.bars("MSFT")

    assert len(bars) == 2
    assert bars[0]["open"] == 500.0
    assert bars[0]["high"] == 502.0
    assert bars[0]["close"] == 502.0
    assert bars[0]["volume"] == 25.0
    assert bars[0]["updated_at"] == datetime(2026, 8, 17, 14, 2, tzinfo=timezone.utc)
    assert bars[1]["close"] == 499.0


def test_r2d2_uses_last_trade_time_instead_of_candle_bucket_for_live_status() -> None:
    service = _service()
    now = datetime.now(timezone.utc)
    bucket = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
    history = [
        {
            "timestamp": bucket - timedelta(minutes=5 * (40 - index)),
            "open": 100.0 + index * 0.05,
            "high": 100.2 + index * 0.05,
            "low": 99.8 + index * 0.05,
            "close": 100.1 + index * 0.05,
            "volume": 1_000 + index * 10,
        }
        for index in range(40)
    ]
    live_bar = {
        "timestamp": bucket,
        "updated_at": now,
        "open": 102.0,
        "high": 102.4,
        "low": 101.9,
        "close": 102.3,
        "volume": 2_500,
        "source": "EODHD Real-Time WebSocket",
    }
    service._historical_intraday = lambda item: history  # type: ignore[method-assign]
    service.realtime = SimpleNamespace(  # type: ignore[assignment]
        stream=SimpleNamespace(bars=lambda symbol, limit=180: [live_bar]),
    )

    snapshot = service._technical_snapshot({
        "market": "NASDAQ", "symbol": "LIVE", "price": 102.35,
        "quote_as_of": now,
    })

    assert snapshot["data_status"] == "live"
    assert snapshot["data_age_minutes"] <= 0.1
    assert snapshot["as_of"] == now.isoformat()


def test_r2d2_technical_defense_weights_structure_trend_and_flow() -> None:
    healthy = R2D2PaperService._technical_defense(
        technical={
            "data_status": "live", "vwap": 99.5, "ema8": 100.5, "ema20": 100.0,
            "ema50": 99.0, "ema8_slope15": 0.2, "ema20_slope15": 0.1,
            "trend_state": "bullish", "price_structure": "higher-highs",
            "macd_histogram": 0.2, "macd_acceleration": 0.1, "momentum15": 0.3,
            "momentum30": 0.5, "momentum60": 0.8, "rsi14": 58,
            "volume_state": "accumulation", "relative_volume": 1.1,
            "obv_slope": 1.0, "sell_volume_ratio": 0.35, "drawdown_atr": 0.2,
        },
        price=101.0, day_change=0.8, market_change=0.3,
    )
    deteriorating = R2D2PaperService._technical_defense(
        technical={
            "data_status": "live", "vwap": 101.0, "ema8": 100.5, "ema20": 101.5,
            "ema50": 102.0, "ema8_slope15": -0.3, "ema20_slope15": -0.15,
            "trend_state": "bearish", "price_structure": "breakdown",
            "macd_histogram": -0.2, "macd_acceleration": -0.1, "momentum15": -0.5,
            "momentum30": -0.8, "momentum60": -1.2, "rsi14": 34,
            "volume_state": "distribution", "relative_volume": 1.5,
            "obv_slope": -1.2, "sell_volume_ratio": 0.75, "drawdown_atr": 1.5,
        },
        price=99.0, day_change=-1.5, market_change=0.2,
    )

    assert healthy["severity"] == "healthy"
    assert healthy["score"] < 20
    assert deteriorating["critical"] is True
    assert deteriorating["severity"] == "exit"
    assert deteriorating["score"] >= 82


def test_r2d2_progressive_sell_reduces_position_and_returns_proceeds_to_cash() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": "CUT", "name": "Cut Corp", "currency": "USD",
        "stop_price": 98.0, "fundamental_score": 70.0, "technical_score": 60.0,
        "risk_score": 35.0, "composite_score": 65.0,
    }
    as_of = datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc)
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=100,
        signal_price=100.0, fill_price=100.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="test entry", decision=candidate, quote_as_of=as_of,
    )
    cash_before = experiment["cash_balance"]
    quote = SimpleNamespace(price=99.8, as_of=as_of + timedelta(minutes=10))

    trade = service._sell(
        experiment, cycle_id, candidate, service.repo.positions(experiment["id"])[0],
        quote, 1.0, "progressive defense", quantity_fraction=0.5,
    )

    position = service.repo.positions(experiment["id"])[0]
    assert position["quantity"] == 50.0
    assert trade["quantity"] == 50.0
    assert experiment["cash_balance"] > cash_before


def test_eodhd_stream_uses_live_bid_ask_midpoint_between_trades() -> None:
    stream = EodhdRealtimeStream("test-token")
    base = int(datetime(2026, 8, 17, 14, 1, tzinfo=timezone.utc).timestamp() * 1000)
    stream._record(json.dumps({"s": "SPCX", "p": 72.0, "v": 10, "t": base, "ms": "open"}))
    stream._record_quote(json.dumps({
        "s": "SPCX", "bp": 72.20, "bs": 100, "ap": 72.40, "as": 80, "t": base + 5_000,
    }))

    quote = stream.quote("SPCX.US")

    assert quote is not None
    assert quote.price == pytest.approx(72.30)
    assert quote.bid == 72.20
    assert quote.ask == 72.40
    assert quote.source == "quote"
    assert stream.bars("SPCX")[0]["close"] == 72.0


def test_eodhd_stream_rejects_crossed_or_excessively_wide_quote() -> None:
    stream = EodhdRealtimeStream("test-token")
    base = int(datetime(2026, 8, 17, 14, 1, tzinfo=timezone.utc).timestamp() * 1000)
    stream._record(json.dumps({"s": "SPCX", "p": 72.0, "v": 10, "t": base, "ms": "open"}))

    stream._record_quote(json.dumps({
        "s": "SPCX", "bp": 80.0, "bs": 100, "ap": 70.0, "as": 80, "t": base + 5_000,
    }))
    stream._record_quote(json.dumps({
        "s": "SPCX", "bp": 60.0, "bs": 100, "ap": 90.0, "as": 80, "t": base + 10_000,
    }))

    quote = stream.quote("SPCX")
    assert quote is not None
    assert quote.price == 72.0
    assert quote.source == "trade"


def test_r2d2_anomalous_quote_requires_a_second_consistent_tick() -> None:
    position = {"last_price_local": 100.0}
    technical = {"atr_percent": 1.2}

    assert R2D2PaperService._quote_is_anomalous(position, 90.0, technical, {}) is True
    assert R2D2PaperService._quote_is_anomalous(
        position, 90.3, technical, {"pending_anomaly_price": 90.0},
    ) is False


def test_r2d2_seconds_to_us_close_counts_down_to_the_official_1600_et_close() -> None:
    # 16:00 ET is 20:00 UTC in August (EDT), independently of screening's
    # deliberate 15:50 ET cutoff.
    five_before = datetime(2026, 8, 17, 19, 55, tzinfo=timezone.utc)
    assert R2D2PaperService._seconds_to_us_close("NASDAQ", five_before) == pytest.approx(300.0)

    mid_session = datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc)
    assert R2D2PaperService._seconds_to_us_close("NASDAQ", mid_session) == pytest.approx(18_000.0)


def test_r2d2_seconds_to_us_close_is_none_after_the_close_or_off_market() -> None:
    after_close = datetime(2026, 8, 17, 20, 1, tzinfo=timezone.utc)
    assert R2D2PaperService._seconds_to_us_close("NASDAQ", after_close) is None

    weekend = datetime(2026, 8, 15, 15, 0, tzinfo=timezone.utc)  # Saturday
    assert R2D2PaperService._seconds_to_us_close("NASDAQ", weekend) is None

    assert R2D2PaperService._seconds_to_us_close(
        "B3", datetime(2026, 8, 17, 19, 45, tzinfo=timezone.utc),
    ) is None


def test_r2d2_hard_stop_exits_immediately_on_live_quote() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": "TEST", "name": "Test Corp", "currency": "USD",
        "stop_price": 95.0, "fundamental_score": 80.0, "technical_score": 70.0,
        "risk_score": 25.0, "composite_score": 78.0,
    }
    opened = datetime(2026, 8, 17, 13, 0, tzinfo=timezone.utc)
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=100,
        signal_price=100.0, fill_price=100.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="test entry", decision=candidate, quote_as_of=opened,
    )
    service.repo.memory["positions"][("NASDAQ", "TEST")]["opened_at"] = opened
    service._usd_fx = lambda now: 5.0  # type: ignore[method-assign]
    service._technical_snapshot = lambda item: {  # type: ignore[method-assign]
        "score": 45.0, "atr": 1.0, "atr_percent": 1.0, "vwap": 98.0,
        "ema8": 97.0, "ema20": 99.0, "macd_histogram": -1.0,
        "macd_acceleration": -0.5, "momentum30": -1.0, "price_structure": "breakdown",
        "trend_state": "bearish", "volume_state": "distribution", "data_status": "live",
        "as_of": datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc).isoformat(),
    }
    # atr_percent 1.0 pushes the ATR-derived hard-stop floor to the 1.5% cap
    # (2x ATR), so the quote needs to breach that -- not the old 0.65%/0.5x
    # floor -- to fire immediately.
    first_quote = SimpleNamespace(
        price=98.0, change_percent=-2.0,
        as_of=datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc),
    )
    first_positions = service.repo.positions(experiment["id"])

    first_exits = service._mark_and_exit(
        experiment, cycle_id, first_positions, {("NASDAQ", "TEST"): first_quote}, first_quote.as_of,
    )
    second_quote = SimpleNamespace(
        price=97.9, change_percent=-2.1,
        as_of=datetime(2026, 8, 17, 15, 1, tzinfo=timezone.utc),
    )
    second_exits = service._mark_and_exit(
        experiment, cycle_id, service.repo.positions(experiment["id"]),
        {("NASDAQ", "TEST"): second_quote}, second_quote.as_of,
    )

    assert first_exits == 1
    assert second_exits == 0
    assert service.repo.positions(experiment["id"]) == []


def test_r2d2_failed_entry_exits_before_the_hard_stop() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": "FAIL", "name": "Failed Setup", "currency": "USD",
        "stop_price": 99.35, "fundamental_score": 75.0, "technical_score": 76.0,
        "risk_score": 35.0, "composite_score": 76.0,
    }
    opened = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=100,
        signal_price=100.0, fill_price=100.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="test entry", decision=candidate, quote_as_of=opened,
    )
    service.repo.memory["positions"][("NASDAQ", "FAIL")]["opened_at"] = opened
    service._technical_snapshot = lambda item: {  # type: ignore[method-assign]
        "score": 48.0, "atr": 0.8, "atr_percent": 0.8, "vwap": 100.1,
        "ema8": 100.0, "ema20": 100.2, "macd_histogram": -0.1,
        "macd_acceleration": -0.05, "momentum15": -0.2, "momentum30": -0.1,
        "price_structure": "lower-highs", "trend_state": "bearish",
        "volume_state": "distribution", "data_status": "live",
        "as_of": datetime(2026, 8, 17, 14, 4, tzinfo=timezone.utc).isoformat(),
    }
    quote = SimpleNamespace(
        price=99.65, change_percent=-0.35,
        as_of=datetime(2026, 8, 17, 14, 4, tzinfo=timezone.utc),
    )

    exits = service._mark_and_exit(
        experiment, cycle_id, service.repo.positions(experiment["id"]),
        {("NASDAQ", "FAIL"): quote}, quote.as_of,
    )

    assert exits == 1
    assert service.repo.positions(experiment["id"]) == []
    assert "Failed-entry fast exit" in service.repo.trades(experiment["id"])[0]["reason"]


def test_r2d2_blocks_reentry_after_a_same_session_loss() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": "CHURN", "name": "No Churn Corp", "currency": "USD",
        "stop_price": 99.35, "fundamental_score": 75.0, "technical_score": 76.0,
        "risk_score": 35.0, "composite_score": 76.0,
    }
    now = datetime.now(timezone.utc)
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=10,
        signal_price=100.0, fill_price=100.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="test entry", decision=candidate, quote_as_of=now,
    )
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="SELL", quantity=10,
        signal_price=99.0, fill_price=99.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="test stop-loss exit", decision=candidate, quote_as_of=now,
    )

    assert service.repo.loss_exit_on_session(
        experiment["id"], "NASDAQ", "CHURN", now.astimezone(SAO_PAULO).date(),
    ) is True


def test_r2d2_allows_reentry_after_a_same_session_profit_exit() -> None:
    """A profit-taking exit ("Tactical profit harvested", "Armed profit locked", etc.)
    explicitly says the capital is "released for same-cycle replacement" -- blocking
    re-entry into the SAME symbol after a WIN contradicted that stated intent. Only a
    same-day LOSS exit should still block re-entry (see loss_exit_on_session docstring).
    """
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": "WINNER", "name": "Profit Corp", "currency": "USD",
        "stop_price": 99.35, "fundamental_score": 75.0, "technical_score": 76.0,
        "risk_score": 35.0, "composite_score": 76.0,
    }
    now = datetime.now(timezone.utc)
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=10,
        signal_price=100.0, fill_price=100.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="test entry", decision=candidate, quote_as_of=now,
    )
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="SELL", quantity=10,
        signal_price=101.0, fill_price=101.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="Tactical profit harvested at +1.00%", decision=candidate, quote_as_of=now,
    )

    assert service.repo.loss_exit_on_session(
        experiment["id"], "NASDAQ", "WINNER", now.astimezone(SAO_PAULO).date(),
    ) is False


def test_r2d2_blocks_us_entry_without_a_live_quote() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": "LATE", "name": "Delayed Corp", "currency": "USD",
        "price": 100.0, "stop_price": 98.5, "upside": 45.0, "risk_score": 22.0,
        "confidence": 82.0, "buy_in_distance": 2.0, "technical_score": 78.0,
        "technical_validated": True, "quote_status": "delayed", "composite_score": 82.0,
        "fundamental_score": 84.0, "thesis": "Delayed quote must not execute",
        "technical_indicators": {"data_status": "delayed", "atr_percent": 1.0},
        "quote_as_of": datetime.now(timezone.utc),
    }

    assert service._buy(experiment, cycle_id, candidate, []) is None
    assert service.repo.positions(experiment["id"]) == []


def test_r2d2_retires_existing_b3_position_during_b3_session() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["B3-EXIT-ONLY"])
    candidate = {
        "market": "B3", "symbol": "OLD3", "name": "Legacy B3", "currency": "BRL",
        "stop_price": 9.5, "fundamental_score": 70.0, "technical_score": 65.0,
        "risk_score": 30.0, "composite_score": 70.0,
    }
    opened = datetime(2026, 8, 17, 13, 0, tzinfo=timezone.utc)
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=1_000,
        signal_price=10.0, fill_price=10.0, fx=0.2, fees=0.0, slippage=0.0,
        reason="legacy B3 entry", decision=candidate, quote_as_of=opened,
    )
    quote = SimpleNamespace(
        price=10.1, change_percent=1.0,
        as_of=datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc),
        status="delayed",
    )

    exits = service._mark_and_exit(
        experiment, cycle_id, service.repo.positions(experiment["id"]),
        {("B3", "OLD3"): quote}, quote.as_of,
    )

    assert exits == 1
    assert service.repo.positions(experiment["id"]) == []
    assert "B3 position retired" in service.repo.trades(experiment["id"])[0]["reason"]


def test_r2d2_locks_unharvested_weekly_profit_after_pullback() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": "WIN", "name": "Winner Corp", "currency": "USD",
        "stop_price": 95.0, "fundamental_score": 80.0, "technical_score": 70.0,
        "risk_score": 25.0, "composite_score": 78.0, "confidence": 80.0,
    }
    opened = datetime(2026, 8, 17, 13, 0, tzinfo=timezone.utc)
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=100,
        signal_price=100.0, fill_price=100.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="test entry", decision=candidate, quote_as_of=opened,
    )
    service.repo.memory["positions"][("NASDAQ", "WIN")]["opened_at"] = opened
    # atr_percent 1.0 caps the ATR-derived stop distance at 1.5% (2x), which
    # is now also the profit-lock trigger floor (1R) -- peak/pnl raised
    # accordingly versus the pre-1R-floor version of this test.
    service.repo.memory["positions"][("NASDAQ", "WIN")]["high_water_price_local"] = 101.7
    service._technical_snapshot = lambda item: {  # type: ignore[method-assign]
        "score": 72.0, "atr": 1.0, "atr_percent": 1.0, "vwap": 100.0,
        "ema8": 100.8, "ema20": 100.3, "macd_histogram": 0.8,
        "macd_acceleration": 0.2, "momentum30": 0.7, "price_structure": "higher-highs",
        "trend_state": "bullish", "volume_state": "accumulation", "data_status": "live",
        "as_of": datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc).isoformat(),
    }
    quote = SimpleNamespace(
        price=101.1, change_percent=1.1,
        as_of=datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc),
    )

    exits = service._mark_and_exit(
        experiment, cycle_id, service.repo.positions(experiment["id"]),
        {("NASDAQ", "WIN"): quote}, quote.as_of,
    )
    assert exits == 1
    assert service.repo.positions(experiment["id"]) == []
    trade = service.repo.trades(experiment["id"])[0]
    assert "Weekly-conviction profit locked" in trade["reason"]


def test_r2d2_harvests_seventy_percent_of_a_weekly_winner_at_trigger() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": "RIOT", "name": "Riot Platforms", "currency": "USD",
        "stop_price": 95.0, "fundamental_score": 80.0, "technical_score": 76.0,
        "risk_score": 25.0, "composite_score": 80.0, "confidence": 80.0,
    }
    opened = datetime(2026, 8, 17, 13, 0, tzinfo=timezone.utc)
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=100,
        signal_price=100.0, fill_price=100.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="test entry", decision=candidate, quote_as_of=opened,
    )
    position = service.repo.memory["positions"][("NASDAQ", "RIOT")]
    position["opened_at"] = opened
    service._technical_snapshot = lambda item: {  # type: ignore[method-assign]
        "score": 80.0, "atr": 1.0, "atr_percent": 1.0, "vwap": 100.2,
        "ema8": 100.7, "ema20": 100.3, "macd_histogram": 0.8,
        "macd_acceleration": 0.2, "momentum30": 0.7, "price_structure": "higher-highs",
        "trend_state": "bullish", "volume_state": "accumulation", "data_status": "live",
        "as_of": datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc).isoformat(),
    }
    # atr_percent 1.0 caps the 1R profit-trigger floor at 1.5% now; raised
    # from the pre-1R-floor 0.97% so the harvest still fires.
    quote = SimpleNamespace(
        price=101.70, change_percent=1.70,
        as_of=datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc),
    )

    exits = service._mark_and_exit(
        experiment, cycle_id, service.repo.positions(experiment["id"]),
        {("NASDAQ", "RIOT"): quote}, quote.as_of,
    )

    assert exits == 1
    remaining = service.repo.positions(experiment["id"])[0]
    assert remaining["quantity"] == 30
    assert remaining["strategy_snapshot"]["profit_harvest_count"] == 1
    trade = service.repo.trades(experiment["id"])[0]
    assert "Weekly-conviction profit layer harvested" in trade["reason"]


def test_r2d2_harvests_tactical_profit_above_cost_aware_trigger() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": "FAST", "name": "Fast Corp", "currency": "USD",
        "stop_price": 95.0, "fundamental_score": 62.0, "technical_score": 70.0,
        "risk_score": 30.0, "composite_score": 68.0, "confidence": 60.0,
    }
    opened = datetime(2026, 8, 17, 13, 0, tzinfo=timezone.utc)
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=100,
        signal_price=100.0, fill_price=100.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="test entry", decision=candidate, quote_as_of=opened,
    )
    service.repo.memory["positions"][("NASDAQ", "FAST")]["opened_at"] = opened
    service._technical_snapshot = lambda item: {  # type: ignore[method-assign]
        "score": 64.0, "atr": 1.0, "atr_percent": 1.0, "vwap": 100.5,
        "ema8": 100.8, "ema20": 100.4, "macd_histogram": 0.2,
        "macd_acceleration": 0.1, "momentum30": 0.2, "price_structure": "higher-highs",
        "trend_state": "bullish", "volume_state": "neutral", "data_status": "live",
        "as_of": datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc).isoformat(),
    }
    # atr_percent 1.0 caps the 1R profit-trigger floor at 1.5% now; raised
    # from the pre-1R-floor 1.1% so the harvest still fires.
    quote = SimpleNamespace(
        price=101.75, change_percent=1.75,
        as_of=datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc),
    )

    exits = service._mark_and_exit(
        experiment, cycle_id, service.repo.positions(experiment["id"]),
        {("NASDAQ", "FAST"): quote}, quote.as_of,
    )

    assert exits == 1
    assert service.repo.positions(experiment["id"]) == []
    assert "Tactical profit harvested" in service.repo.trades(experiment["id"])[0]["reason"]


def test_r2d2_locks_an_armed_profit_after_pullback() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": "LOCK", "name": "Lock Corp", "currency": "USD",
        "stop_price": 95.0, "fundamental_score": 60.0, "technical_score": 58.0,
        "risk_score": 32.0, "composite_score": 64.0, "confidence": 58.0,
    }
    opened = datetime(2026, 8, 17, 13, 0, tzinfo=timezone.utc)
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=100,
        signal_price=100.0, fill_price=100.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="test entry", decision=candidate, quote_as_of=opened,
    )
    position = service.repo.memory["positions"][("NASDAQ", "LOCK")]
    position["opened_at"] = opened
    # atr_percent 1.0 caps the 1R profit-trigger floor at 1.5% now; peak/pnl
    # raised from the pre-1R-floor 1.35%/0.45% so the lock still fires.
    position["high_water_price_local"] = 101.8
    service._technical_snapshot = lambda item: {  # type: ignore[method-assign]
        "score": 58.0, "atr": 1.0, "atr_percent": 1.0, "vwap": 100.4,
        "ema8": 100.5, "ema20": 100.3, "macd_histogram": 0.1,
        "macd_acceleration": 0.0, "momentum30": 0.0, "price_structure": "range",
        "trend_state": "neutral", "volume_state": "neutral", "data_status": "live",
        "as_of": datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc).isoformat(),
    }
    quote = SimpleNamespace(
        price=101.1, change_percent=1.1,
        as_of=datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc),
    )

    exits = service._mark_and_exit(
        experiment, cycle_id, service.repo.positions(experiment["id"]),
        {("NASDAQ", "LOCK"): quote}, quote.as_of,
    )

    assert exits == 1
    assert "Armed profit locked" in service.repo.trades(experiment["id"])[0]["reason"]


def test_r2d2_tactical_quality_momentum_route_expands_the_entry_funnel() -> None:
    service = _service()
    candidate = {
        "market": "NASDAQ", "quote_status": "live", "price": 101.0,
        "upside": 35.0, "risk_score": 52.0, "confidence": 74.0,
        "buy_in_distance": 8.0, "technical_score": 76.0,
        "technical_validated": True, "composite_score": 76.0,
        "thesis": "Fresh momentum with controlled valuation risk",
        "technical_indicators": {
            "data_status": "live", "trend_state": "bullish",
            "volume_state": "accumulation", "price_structure": "breakout",
            # relative_volume raised past ENTRY_RELATIVE_VOLUME_MIN (1.5,
            # tightened 2026-08-20 from 1.05 -- barely-above-normal volume
            # doesn't confirm real participation behind a breakout).
            "relative_volume": 1.6, "vwap": 100.5, "ema8": 100.8, "ema20": 100.4,
            "momentum15": 0.20, "momentum30": 0.35,
            "macd_histogram": 0.2, "macd_acceleration": 0.1, "rsi14": 60.0,
            "relative_strength": 0.4,
        },
    }

    action, reasons = service._entry_decision(candidate)

    assert action == "BUY"
    assert "Tactical quality-momentum route passed" in reasons[-1]


def test_r2d2_cost_aware_intraday_route_accepts_live_liquid_momentum() -> None:
    service = _service()
    candidate = {
        "market": "NYSE", "quote_status": "live", "price": 101.0,
        "upside": 12.0, "risk_score": 52.0, "confidence": 58.0,
        "buy_in_distance": 12.0, "technical_score": 72.0,
        "technical_validated": True, "composite_score": 64.0,
        "thesis": "Live momentum with positive modeled edge after costs",
        "technical_indicators": {
            "data_status": "live", "trend_state": "bullish",
            "volume_state": "accumulation", "price_structure": "higher-highs",
            "momentum15": 0.30, "momentum30": 0.55, "momentum60": 0.80,
            # relative_volume raised past ENTRY_RELATIVE_VOLUME_MIN (1.5,
            # tightened 2026-08-20); modeled_edge stays above the 0.55
            # friction buffer either way.
            "relative_volume": 1.6, "vwap": 100.5, "ema8": 100.8, "ema20": 100.4,
            "macd_histogram": 0.2, "macd_acceleration": 0.1, "rsi14": 60.0,
            "relative_strength": 0.4,
        },
    }

    action, reasons = service._entry_decision(candidate)

    assert action == "BUY"
    assert candidate["modeled_intraday_edge_percent"] >= 0.55
    assert "Cost-aware intraday route passed" in reasons[-1]


def test_r2d2_cost_aware_route_rejects_weak_fundamental_anchor_despite_momentum() -> None:
    service = _service()
    candidate = {
        "market": "NASDAQ", "quote_status": "live", "price": 101.0,
        "upside": 0.5, "risk_score": 68.0, "confidence": 42.0,
        "buy_in_distance": 32.0, "technical_score": 69.0,
        "technical_validated": True, "composite_score": 58.0,
        "thesis": "Live technical edge with a neutral fundamental anchor",
        "technical_indicators": {
            "data_status": "live", "trend_state": "bullish",
            "volume_state": "accumulation", "price_structure": "breakout",
            "momentum15": 0.35, "momentum30": 0.45, "momentum60": 0.70,
            "relative_volume": 1.4, "vwap": 100.5, "ema8": 100.8, "ema20": 100.4,
            "macd_histogram": 0.2, "macd_acceleration": 0.1, "rsi14": 60.0,
            "relative_strength": 0.4,
        },
    }

    action, reasons = service._entry_decision(candidate)

    assert action == "REJECT"
    assert candidate["modeled_intraday_edge_percent"] >= 0.55
    assert any("Risk score" in reason for reason in reasons)


def test_r2d2_cost_aware_intraday_route_rejects_edge_below_friction_buffer() -> None:
    service = _service()
    candidate = {
        "market": "NASDAQ", "quote_status": "live", "price": 101.0,
        "upside": 12.0, "risk_score": 55.0, "confidence": 58.0,
        "buy_in_distance": 12.0, "technical_score": 64.0,
        "technical_validated": True, "composite_score": 59.0,
        "thesis": "Positive movement without enough edge after costs",
        "technical_indicators": {
            "data_status": "live", "trend_state": "bullish",
            "volume_state": "neutral", "price_structure": "higher-highs",
            "momentum15": 0.05, "momentum30": 0.05, "momentum60": 0.05,
            "relative_volume": 1.0, "vwap": 100.5, "ema8": 100.8, "ema20": 100.4,
            "macd_histogram": 0.1, "macd_acceleration": 0.0, "rsi14": 58.0,
            "relative_strength": 0.1,
        },
    }

    action, _ = service._entry_decision(candidate)

    assert action == "REJECT"
    assert candidate["modeled_intraday_edge_percent"] < 0.55


def test_r2d2_entry_confirmation_requires_consecutive_distinct_live_ticks() -> None:
    service = _service()
    first_tick = datetime(2026, 8, 31, 14, 0, tzinfo=timezone.utc)
    candidate = _qualifying_entry_candidate("PERSIST", first_tick)

    assert service._confirm_entry_setup(candidate, generation=1) == (1, False)
    assert service._confirm_entry_setup(candidate, generation=2) == (1, False)

    candidate["quote_as_of"] = first_tick + timedelta(seconds=30)
    assert service._confirm_entry_setup(candidate, generation=3) == (2, True)

    candidate["quote_as_of"] = first_tick + timedelta(seconds=60)
    assert service._confirm_entry_setup(candidate, generation=5) == (1, False)


def test_r2d2_run_cycle_waits_for_second_entry_confirmation() -> None:
    service = _service()
    first_scan = datetime(2026, 8, 31, 14, 0, tzinfo=timezone.utc)
    active_scan = {"at": datetime.now(timezone.utc)}
    service._position_quotes = lambda positions, now: {}  # type: ignore[method-assign]
    service._us_candidates = (  # type: ignore[method-assign]
        lambda market, now: (
            [_qualifying_entry_candidate("PERSIST", active_scan["at"])]
            if market == "NASDAQ" else []
        )
    )
    service._enrich_technicals = lambda candidates, **kwargs: None  # type: ignore[method-assign]

    first = service.run_cycle(first_scan)

    assert first.open_positions == 0
    assert first.last_cycle is not None
    assert first.last_cycle.metadata["entry_admission"]["confirmation_pending_count"] == 1

    active_scan["at"] = active_scan["at"] + timedelta(seconds=1)
    second = service.run_cycle(first_scan + timedelta(minutes=1))

    assert second.open_positions == 1
    assert second.positions[0].symbol == "PERSIST"
    assert second.last_cycle is not None
    assert second.last_cycle.metadata["entry_admission"]["new_positions_count"] == 1


def test_r2d2_limits_new_positions_from_one_market_snapshot() -> None:
    service = _service()
    service.settings.r2d2_entry_confirmation_reviews = 1
    service.settings.r2d2_max_new_positions_per_scan = 2
    scan_at = datetime(2026, 8, 31, 14, 0, tzinfo=timezone.utc)
    quote_at = datetime.now(timezone.utc)
    candidates = [
        _qualifying_entry_candidate(f"BATCH{index}", quote_at, composite_score=90 - index)
        for index in range(5)
    ]
    service._position_quotes = lambda positions, now: {}  # type: ignore[method-assign]
    service._us_candidates = (  # type: ignore[method-assign]
        lambda market, now: candidates if market == "NASDAQ" else []
    )
    service._enrich_technicals = lambda candidates, **kwargs: None  # type: ignore[method-assign]

    dashboard = service.run_cycle(scan_at)

    assert dashboard.open_positions == 2
    assert {position.symbol for position in dashboard.positions} == {"BATCH0", "BATCH1"}
    assert dashboard.last_cycle is not None
    assert dashboard.last_cycle.metadata["entry_admission"] == {
        "capacity_policy": {
            "milestone": "2026-08-31-derived-portfolio-capacity-v1",
            "position_count_limit": None,
            "confirmation_reviews": 1,
            "max_new_positions_per_scan": 2,
            "max_position_percent": 6.0,
            "max_market_percent": 48.0,
            "max_gross_exposure_percent": 95.0,
            "minimum_cash_buffer_percent": 5.0,
            "capacity_rule": (
                "position count emerges from per-name, per-market, gross-exposure "
                "and minimum-cash constraints"
            ),
        },
        "confirmation_reviews_required": 1,
        "max_new_positions_per_scan": 2,
        "confirmation_pending_count": 0,
        "burst_deferred_count": 3,
        "financial_capacity_deferred_count": 0,
        "new_positions_count": 2,
    }


def test_r2d2_counts_financial_capacity_deferral_separately_from_burst() -> None:
    service = _service()
    service.settings.r2d2_entry_confirmation_reviews = 1
    scan_at = datetime(2026, 8, 31, 14, 0, tzinfo=timezone.utc)
    candidate = _qualifying_entry_candidate("CAPACITY", datetime.now(timezone.utc))
    service._position_quotes = lambda positions, now: {}  # type: ignore[method-assign]
    service._us_candidates = (  # type: ignore[method-assign]
        lambda market, now: [candidate] if market == "NASDAQ" else []
    )
    service._enrich_technicals = lambda candidates, **kwargs: None  # type: ignore[method-assign]
    service._has_entry_capacity = lambda candidate: False  # type: ignore[method-assign]
    service._rotate_if_better = lambda *args, **kwargs: 0  # type: ignore[method-assign]

    dashboard = service.run_cycle(scan_at)

    assert dashboard.open_positions == 0
    assert dashboard.last_cycle is not None
    admission = dashboard.last_cycle.metadata["entry_admission"]
    assert admission["financial_capacity_deferred_count"] == 1
    assert admission["burst_deferred_count"] == 0
    assert admission["new_positions_count"] == 0


def test_r2d2_daily_order_cap_blocks_new_entries() -> None:
    service = _service()
    service.settings.r2d2_max_daily_orders = 0
    candidate = {
        "market": "NASDAQ", "symbol": "CAP", "name": "Cap Corp", "currency": "USD",
        "price": 100.0, "stop_price": 99.1, "upside": 35.0, "risk_score": 30.0,
        "confidence": 80.0, "buy_in_distance": 4.0, "technical_score": 76.0,
        "technical_validated": True, "quote_status": "live", "composite_score": 78.0,
        "fundamental_score": 82.0, "thesis": "Would otherwise qualify",
        "technical_indicators": {
            "data_status": "live", "trend_state": "bullish",
            "volume_state": "accumulation", "price_structure": "breakout",
        },
        "quote_as_of": datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc),
    }
    service._position_quotes = lambda positions, now: {}  # type: ignore[method-assign]
    service._us_candidates = (  # type: ignore[method-assign]
        lambda market, now: [candidate] if market == "NASDAQ" else []
    )
    service._enrich_technicals = lambda candidates, **kwargs: None  # type: ignore[method-assign]

    dashboard = service.run_cycle(datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc))

    assert dashboard.open_positions == 0
    assert dashboard.stats.total_transactions == 0


def test_r2d2_entry_pause_is_audited_and_visible_on_dashboard() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    changed_at = datetime(2026, 8, 24, 20, 0, tzinfo=timezone.utc)

    changed = service.repo.set_entries_paused(
        experiment["code"],
        paused=True,
        operator="Dudu",
        reason="Six-hands review of the exit-policy evidence",
        changed_at=changed_at,
    )

    assert changed["entries_paused"] is True
    assert changed["entries_paused_at"] == changed_at
    dashboard = service.dashboard()
    assert dashboard.status == "running"
    assert dashboard.entries_paused is True
    assert dashboard.entries_paused_at == changed_at
    assert dashboard.entries_pause_operator == "Dudu"
    assert dashboard.entries_pause_reason == "Six-hands review of the exit-policy evidence"
    events = service.repo.database.list_audit_events(action="r2d2.entries_paused")
    assert len(events) == 1
    assert events[0]["actor"] == "Dudu"
    assert events[0]["detail"]["previous_entries_paused"] is False
    assert events[0]["detail"]["entries_paused"] is True

    unchanged = service.repo.set_entries_paused(
        experiment["code"],
        paused=True,
        operator="Dudu",
        reason="Repeated operator command",
        changed_at=changed_at + timedelta(minutes=1),
    )
    assert unchanged["entries_paused_at"] == changed_at
    assert len(service.repo.database.list_audit_events(action="r2d2.entries_paused")) == 1


def test_r2d2_entry_pause_keeps_exits_running_but_skips_every_entry_scan() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    service.repo.set_entries_paused(
        experiment["code"], paused=True, operator="Dudu", reason="Evidence review",
    )
    exits: list[str] = []
    service._position_quotes = lambda positions, now: {}  # type: ignore[method-assign]
    service._mark_and_exit = (  # type: ignore[method-assign]
        lambda *args, **kwargs: exits.append("evaluated") or 1
    )
    service._us_candidates = (  # type: ignore[method-assign]
        lambda *args, **kwargs: pytest.fail("paused entries must not scan candidates")
    )

    dashboard = service.run_cycle(datetime(2026, 8, 24, 14, 0, tzinfo=timezone.utc))

    assert exits == ["evaluated"]
    assert dashboard.entries_paused is True
    assert dashboard.last_cycle is not None
    assert dashboard.last_cycle.status == "succeeded"
    assert dashboard.last_cycle.scanned_count == 0
    assert dashboard.last_cycle.trade_count == 1


def test_r2d2_entry_pause_blocks_stale_cycle_buy_and_rotation_defensively() -> None:
    service = _service()
    stale_experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(stale_experiment["id"], ["NASDAQ"])
    service.repo.set_entries_paused(
        stale_experiment["code"], paused=True, operator="Dudu", reason="Evidence review",
    )
    candidate = {
        "market": "NASDAQ", "symbol": "BLOCK", "name": "Blocked Corp",
        "quote_status": "live", "quote_as_of": datetime.now(timezone.utc),
    }

    assert service._buy(stale_experiment, cycle_id, candidate, []) is None
    assert service._rotate_if_better(
        stale_experiment, cycle_id, candidate, [], {}, datetime.now(timezone.utc),
    ) == 0


def test_r2d2_entry_control_is_plan_first(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = _settings()
    database = Database(settings)
    repository = R2D2Repository(database)
    repository.ensure_experiment(settings)
    monkeypatch.setattr(r2d2_entry_control, "Settings", lambda: settings)
    monkeypatch.setattr(r2d2_entry_control, "Database", lambda _: database)
    arguments = ["--pause", "--operator", "Dudu", "--reason", "Evidence review"]

    assert r2d2_entry_control.main(arguments) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["mode"] == "plan"
    assert repository.experiment(settings.r2d2_experiment_code)["entries_paused"] is False

    assert r2d2_entry_control.main([*arguments, "--execute"]) == 0
    executed = json.loads(capsys.readouterr().out)
    assert executed["mode"] == "execute"
    assert executed["entries_paused"] is True
    assert repository.experiment(settings.r2d2_experiment_code)["entries_paused"] is True


def test_r2d2_weekly_conviction_rejects_an_uncontrolled_pullback() -> None:
    result = R2D2PaperService._weekly_conviction(
        strategy={"fundamental_score": 90.0, "confidence": 90.0},
        technical={
            "score": 80.0, "trend_score": 85.0, "flow_score": 80.0,
            "momentum_score": 80.0, "trend_state": "bullish",
            "volume_state": "accumulation", "price_structure": "breakout",
            "data_status": "live",
        },
        price=95.0, high_water=105.0, atr=1.0, bearish_votes=0,
    )

    assert result["active"] is False
    assert "controlled pullback" not in result["reasons"]


def test_r2d2_exit_triggers_an_immediate_replacement_scan() -> None:
    service = _service()
    service.settings.r2d2_entry_confirmation_reviews = 1
    service.ensure_initialized()
    calls: list[str] = []
    candidate = {
        "market": "NASDAQ", "symbol": "NEXT", "name": "Next Corp", "currency": "USD",
        "price": 100.0, "stop_price": 95.0, "upside": 35.0, "risk_score": 30.0,
        "confidence": 80.0, "buy_in_distance": 4.0, "technical_score": 72.0,
        "technical_validated": True, "quote_status": "live", "composite_score": 78.0,
        "fundamental_score": 82.0, "thesis": "Best eligible replacement",
        "quote_as_of": datetime.now(timezone.utc),
        "technical_indicators": {
            "data_status": "live", "trend_state": "bullish",
            "volume_state": "accumulation", "price_structure": "breakout",
            "relative_volume": 1.6, "vwap": 99.5,
            "ema8": 99.8, "ema20": 99.4,
            "momentum15": 0.3, "momentum30": 0.5, "momentum60": 0.8,
            "macd_histogram": 0.2, "macd_acceleration": 0.1,
            "rsi14": 60.0, "relative_strength": 0.4,
        },
    }
    service._position_quotes = lambda positions, now: {}  # type: ignore[method-assign]
    service._mark_and_exit = lambda *args, **kwargs: 1  # type: ignore[method-assign]
    service._us_candidates = (  # type: ignore[method-assign]
        lambda market, now: calls.append(market) or ([candidate] if market == "NASDAQ" else [])
    )
    service._enrich_technicals = lambda candidates, **kwargs: None  # type: ignore[method-assign]

    dashboard = service.run_cycle(
        datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc), scan_entries=False,
    )

    assert calls == ["NASDAQ", "NYSE"]
    assert dashboard.open_positions == 1
    assert dashboard.positions[0].symbol == "NEXT"
    assert dashboard.positions[0].logo_url == "https://eodhd.com/img/logos/US/next.png"
    assert dashboard.last_cycle is not None
    assert dashboard.last_cycle.trade_count == 2
