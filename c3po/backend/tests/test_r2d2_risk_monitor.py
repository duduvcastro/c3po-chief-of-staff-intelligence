from __future__ import annotations

from datetime import datetime, timezone
from threading import Event, Thread
from types import SimpleNamespace

from app.config import Settings
from app.database import Database
from app.r2d2 import R2D2PaperService


def _service() -> R2D2PaperService:
    settings = Settings(
        database_url="",
        r2d2_start_date="2026-08-17",
        r2d2_risk_monitor_enabled=True,
        r2d2_risk_monitor_interval_seconds=3,
    )
    return R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]


def _open_position(service: R2D2PaperService, symbol: str = "LOCK") -> tuple[dict, str]:
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": symbol, "name": "Lock Test Corp", "currency": "USD",
        "stop_price": 99.35, "fundamental_score": 70.0, "technical_score": 70.0,
        "risk_score": 30.0, "composite_score": 70.0,
    }
    opened = datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc)
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=10,
        signal_price=100.0, fill_price=100.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="test entry", decision=candidate, quote_as_of=opened,
    )
    service.repo.memory["positions"][("NASDAQ", symbol)]["opened_at"] = opened
    return experiment, cycle_id


def _live_technical() -> dict:
    return {
        "score": 45.0, "atr": 1.0, "atr_percent": 1.0, "vwap": 100.0,
        "ema8": 99.0, "ema20": 100.0, "macd_histogram": -0.5,
        "macd_acceleration": -0.2, "momentum15": -0.8, "momentum30": -1.0,
        "price_structure": "breakdown", "trend_state": "bearish",
        "volume_state": "distribution", "data_status": "live",
        "as_of": datetime(2026, 8, 20, 14, 5, tzinfo=timezone.utc).isoformat(),
    }


def test_concurrent_risk_loops_cannot_sell_the_same_position_twice() -> None:
    service = _service()
    experiment, cycle_id = _open_position(service)
    entered = Event()
    release = Event()

    def blocking_technical(item: dict) -> dict:
        entered.set()
        assert release.wait(timeout=2)
        return _live_technical()

    service._technical_snapshot = blocking_technical  # type: ignore[method-assign]
    now = datetime(2026, 8, 20, 14, 5, tzinfo=timezone.utc)
    quote = SimpleNamespace(price=99.0, change_percent=-1.0, as_of=now, status="live")
    results: list[int] = []

    def evaluate() -> None:
        results.append(service._mark_and_exit(
            experiment, cycle_id, service.repo.positions(experiment["id"]),
            {("NASDAQ", "LOCK"): quote}, now,
        ))

    first = Thread(target=evaluate)
    first.start()
    assert entered.wait(timeout=2)
    second = Thread(target=evaluate)
    second.start()
    second.join(timeout=2)
    release.set()
    first.join(timeout=2)

    assert sorted(results) == [0, 1]
    sells = [trade for trade in service.repo.trades(experiment["id"]) if trade["side"] == "SELL"]
    assert len(sells) == 1
    assert service.repo.positions(experiment["id"]) == []


def test_stale_position_list_cannot_trigger_a_second_sale() -> None:
    service = _service()
    experiment, cycle_id = _open_position(service)
    stale_positions = service.repo.positions(experiment["id"])
    service._technical_snapshot = lambda item: _live_technical()  # type: ignore[method-assign]
    now = datetime(2026, 8, 20, 14, 5, tzinfo=timezone.utc)
    quote = SimpleNamespace(price=99.0, change_percent=-1.0, as_of=now, status="live")
    quotes = {("NASDAQ", "LOCK"): quote}

    assert service._mark_and_exit(experiment, cycle_id, stale_positions, quotes, now) == 1
    assert service._mark_and_exit(experiment, cycle_id, stale_positions, quotes, now) == 0

    sells = [trade for trade in service.repo.trades(experiment["id"]) if trade["side"] == "SELL"]
    assert len(sells) == 1


def test_risk_monitor_cycle_never_enters_the_screening_pipeline() -> None:
    service = _service()
    experiment, _ = _open_position(service, "RISK")
    calls: list[str] = []
    service._position_quotes = lambda positions, now: calls.append("quotes") or {}  # type: ignore[method-assign]
    service._mark_and_exit = lambda *args, **kwargs: calls.append("risk") or 0  # type: ignore[method-assign]
    service._us_candidates = lambda *args, **kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
        AssertionError("dedicated risk monitor must not screen candidates")
    )

    service.run_risk_monitor_cycle(datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc))

    assert calls == ["quotes", "risk"]
    cycle = service.repo.memory["cycles"][-1]
    assert cycle["metadata"]["risk_monitor"]["positions"] == 1
    assert cycle["trade_count"] == 0


def test_risk_monitor_continues_after_screening_cutoff_until_regular_close() -> None:
    service = _service()
    _open_position(service, "FINAL10")
    calls: list[str] = []
    service._position_quotes = lambda positions, now: calls.append("quotes") or {}  # type: ignore[method-assign]
    service._mark_and_exit = lambda *args, **kwargs: calls.append("risk") or 0  # type: ignore[method-assign]
    service._us_candidates = lambda *args, **kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
        AssertionError("final-ten-minute risk protection must not screen candidates")
    )
    final_ten_minutes = datetime(2026, 8, 20, 19, 55, tzinfo=timezone.utc)  # 15:55 ET

    assert service.open_markets(final_ten_minutes) == []
    assert service.risk_markets(final_ten_minutes) == ["NASDAQ", "NYSE"]
    service.run_risk_monitor_cycle(final_ten_minutes)

    assert calls == ["quotes", "risk"]
    cycle = service.repo.memory["cycles"][-1]
    assert cycle["markets"] == ["NASDAQ", "NYSE"]
    assert cycle["metadata"]["risk_monitor"]["positions"] == 1


def test_screening_remains_closed_during_final_ten_minutes() -> None:
    service = _service()
    service._us_candidates = lambda *args, **kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
        AssertionError("screening must remain closed after 15:50 ET")
    )
    final_ten_minutes = datetime(2026, 8, 20, 19, 55, tzinfo=timezone.utc)  # 15:55 ET

    dashboard = service.run_cycle(final_ten_minutes)

    assert dashboard.last_cycle is not None
    assert dashboard.last_cycle.status == "market_closed"


def test_risk_monitor_stops_at_regular_session_close() -> None:
    service = _service()
    _open_position(service, "AFTER")
    cycles_before = len(service.repo.memory["cycles"])

    exits = service.run_risk_monitor_cycle(
        datetime(2026, 8, 20, 20, 0, tzinfo=timezone.utc),  # 16:00 ET
    )

    assert exits == 0
    assert len(service.repo.memory["cycles"]) == cycles_before


def test_failed_risk_cycle_keeps_monitor_telemetry() -> None:
    service = _service()
    _open_position(service, "FAIL")
    service._position_quotes = lambda positions, now: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("quote failure")
    )

    service.run_risk_monitor_cycle(datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc))

    cycle = service.repo.memory["cycles"][-1]
    assert cycle["status"] == "failed"
    assert cycle["metadata"]["risk_monitor"]["positions"] == 1


def test_risk_priority_puts_stop_proximity_then_losses_first() -> None:
    positions = [
        {"market": "NASDAQ", "symbol": "GAIN", "average_cost_local": 100, "last_price_local": 102,
         "stop_price_local": 99},
        {"market": "NASDAQ", "symbol": "LOSS", "average_cost_local": 100, "last_price_local": 99,
         "stop_price_local": 95},
        {"market": "NASDAQ", "symbol": "STOP", "average_cost_local": 100, "last_price_local": 99.1,
         "stop_price_local": 99},
    ]
    quotes = {
        ("NASDAQ", "GAIN"): SimpleNamespace(price=102.0),
        ("NASDAQ", "LOSS"): SimpleNamespace(price=99.0),
        ("NASDAQ", "STOP"): SimpleNamespace(price=99.1),
    }

    ordered = sorted(positions, key=lambda item: R2D2PaperService._risk_priority(item, quotes))

    assert [item["symbol"] for item in ordered] == ["STOP", "LOSS", "GAIN"]
