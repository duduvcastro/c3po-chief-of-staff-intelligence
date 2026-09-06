from __future__ import annotations

import json
import os
import stat
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import r2d2_v2_producer_daily as prod

D = date(2026, 9, 8)  # Tuesday; D-1 = Friday 2026-09-04 (Monday 07/09 is Labor Day, not a session)
PREVIOUS = date(2026, 9, 4)


def _response(payload, received_at: datetime, path: str = "/api/x") -> prod.Response:
    return prod.Response(json.dumps(payload).encode(), received_at, path)


def _after_close(day: date, minutes: int = 90) -> datetime:
    return prod.session_close(day) + timedelta(minutes=minutes)


def test_calendar_helpers_use_official_sessions() -> None:
    assert prod.previous_session(D) == PREVIOUS  # Labor Day skipped
    assert prod.previous_session(date(2026, 9, 7)) == PREVIOUS
    sessions = prod.xnys_sessions_ending(PREVIOUS, 20)
    assert len(sessions) == 20 and sessions[-1] == PREVIOUS and sessions == tuple(sorted(sessions))
    assert prod.session_close(PREVIOUS).astimezone(prod.NEW_YORK).hour == 16
    with pytest.raises(prod.ProducerError, match="LAST_SESSION_NOT_OFFICIAL"):
        prod.xnys_sessions_ending(date(2026, 9, 7), 20)


def test_split_factor_parsing() -> None:
    assert prod.parse_split_factor("4.000000/1.000000") == 4.0
    assert prod.parse_split_factor("1.000000/10.000000") == pytest.approx(0.1)
    assert prod.parse_split_factor("3/2") == 1.5
    assert prod.parse_split_factor("0/1") is None and prod.parse_split_factor("x") is None and prod.parse_split_factor(None) is None


def test_registry_maps_types_and_keeps_only_nyse_nasdaq() -> None:
    rows = [
        {"Code": "AAA", "Exchange": "NYSE", "Type": "Common Stock", "Currency": "USD", "Country": "USA"},
        {"Code": "BBB", "Exchange": "NASDAQ", "Type": "ETF"},
        {"Code": "CCC", "Exchange": "NYSE ARCA", "Type": "ETF"},
        {"Code": "DDD", "Exchange": "PINK", "Type": "Common Stock"},
        {"Code": "EEE", "Exchange": "NASDAQ", "Type": "Preferred Stock"},
        {"Code": "BRK-B", "Exchange": "NYSE", "Type": "Common Stock"},
        {"Code": "bad code", "Exchange": "NYSE", "Type": "Common Stock"},
        {"Code": "AAA", "Exchange": "NYSE", "Type": "Common Stock"},
        {"Code": "ZZZ", "Exchange": "NASDAQ", "Type": "Mystery"},
    ]
    registry = prod.build_registry(_response(rows, _after_close(PREVIOUS)), previous_close=prod.session_close(PREVIOUS))
    assert registry["schema"] == "V2_CAUSAL_REGISTRY_V1" and registry["coverage_verified"] is True
    assert set(registry) == {"schema", "source_id", "source_at", "available_at", "captured_at", "coverage_verified", "instruments", "producer_note"}
    symbols = {item["symbol"]: item for item in registry["instruments"]}
    assert set(symbols) == {"AAA", "BBB", "EEE", "BRK-B", "ZZZ"}
    assert symbols["AAA"] == {"symbol": "AAA", "market": "NYSE", "security_type": "COMMON_STOCK", "classification_verified": True}
    assert symbols["BBB"]["security_type"] == "ETF" and symbols["EEE"]["security_type"] == "PREFERRED_STOCK" and symbols["ZZZ"]["security_type"] == "OTHER"
    assert registry["producer_note"]["counts"] == {"provider_rows": 9, "kept": 5, "skipped_exchange": 2, "skipped_symbol": 1, "duplicates": 1}
    with pytest.raises(prod.ProducerError, match="REGISTRY_CAPTURED_BEFORE_CLOSE"):
        prod.build_registry(_response(rows, prod.session_close(PREVIOUS) - timedelta(minutes=1)), previous_close=prod.session_close(PREVIOUS))
    with pytest.raises(prod.ProducerError, match="REGISTRY_EMPTY"):
        prod.build_registry(_response([], _after_close(PREVIOUS)), previous_close=prod.session_close(PREVIOUS))


def _registry(symbols: list[str]) -> dict:
    return {"instruments": [{"symbol": s, "market": "NYSE", "security_type": "COMMON_STOCK", "classification_verified": True} for s in symbols]}


def test_daily_contract_assembles_20_sessions_raw_with_window_splits() -> None:
    sessions = prod.xnys_sessions_ending(PREVIOUS, 20)
    bulk, splits = {}, {}
    for index, session in enumerate(sessions):
        received = _after_close(session, 120)
        rows = [{"code": "AAA", "exchange_short_name": "US", "date": session.isoformat(), "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5, "adjusted_close": 10.4, "volume": 1000 + index},
                {"code": "BBB", "exchange_short_name": "US", "date": session.isoformat(), "open": 5.0, "high": 5.0, "low": 5.0, "close": 5.0, "volume": 0}]
        if index == 3:
            rows = rows[:1]  # BBB misses one session -> incomplete window
        if index == 5:
            rows.append({"code": "AAA", "date": "1999-01-01", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1})  # wrong date ignored
            rows.append({"code": "AAA", "date": session.isoformat(), "open": 10.0, "high": 9.0, "low": 9.0, "close": 10.5, "volume": 1})  # invalid OHLC ignored
        bulk[session] = _response(rows, received)
        splits[session] = _response([{"code": "AAA", "date": session.isoformat(), "split": "2.000000/1.000000"}] if index == 10 else [], received + timedelta(seconds=5))
    contract = prod.build_daily_contract(_registry(["AAA", "BBB"]), bulk, splits, sessions=sessions, previous_close=prod.session_close(PREVIOUS))
    assert contract["schema"] == "V2_CAUSAL_DAILY_CONTRACT_V1"
    assert set(contract) == {"schema", "source_id", "source_at", "available_at", "instruments", "producer_note"}
    by_symbol = {item["symbol"]: item["daily"] for item in contract["instruments"]}
    aaa = by_symbol["AAA"]
    assert set(aaa) == {"bars", "splits", "adjustment", "coverage_verified", "split_coverage_verified", "source_at", "available_at"}
    assert aaa["adjustment"] == "RAW_UNADJUSTED" and len(aaa["bars"]) == 20
    assert [bar["session_date"] for bar in aaa["bars"]] == [s.isoformat() for s in sessions]
    bar = aaa["bars"][0]
    assert set(bar) == {"session_date", "open", "high", "low", "close", "volume", "source_at", "available_at", "complete", "regular_session"}
    assert bar["close"] == 10.5 and "adjusted_close" not in bar and bar["complete"] is True and bar["regular_session"] is True
    assert datetime.fromisoformat(bar["source_at"]) > prod.session_close(sessions[0])
    assert len(aaa["splits"]) == 1 and aaa["splits"][0]["factor"] == 2.0
    assert datetime.fromisoformat(aaa["splits"][0]["effective_at"]) == prod.session_open(sessions[10])
    assert len(by_symbol["BBB"]["bars"]) == 19  # missing session left missing, never filled
    assert contract["producer_note"]["complete_bars"] == 1
    assert datetime.fromisoformat(contract["available_at"]) >= max(r.received_at for r in bulk.values())


def test_daily_contract_rejects_bad_windows_and_early_receipts() -> None:
    sessions = prod.xnys_sessions_ending(PREVIOUS, 20)
    ok = {s: _response([], _after_close(s)) for s in sessions}
    with pytest.raises(prod.ProducerError, match="LIQUIDITY_WINDOW_INVALID"):
        prod.build_daily_contract(_registry(["AAA"]), ok, ok, sessions=sessions[:19], previous_close=prod.session_close(PREVIOUS))
    with pytest.raises(prod.ProducerError, match="BULK_RESPONSES_INCOMPLETE"):
        prod.build_daily_contract(_registry(["AAA"]), dict(list(ok.items())[:19]), ok, sessions=sessions, previous_close=prod.session_close(PREVIOUS))
    early = dict(ok)
    early[sessions[0]] = _response([], prod.session_close(sessions[0]) - timedelta(minutes=1))
    with pytest.raises(prod.ProducerError, match="BULK_RECEIVED_BEFORE_SESSION_CLOSE"):
        prod.build_daily_contract(_registry(["AAA"]), early, ok, sessions=sessions, previous_close=prod.session_close(PREVIOUS))


def test_instrument_component_has_exactly_61_official_sessions_and_split_history() -> None:
    sessions = prod.xnys_sessions_ending(PREVIOUS, 61)
    received = _after_close(PREVIOUS, 200)
    rows = [{"date": s.isoformat(), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "adjusted_close": 50.25, "volume": 1e6} for s in sessions]
    rows.insert(0, {"date": "2026-01-02", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1})  # outside the window, ignored
    splits = [{"date": "2020-08-31", "split": "4.000000/1.000000"}, {"date": "2014-06-09", "split": "7.000000/1.000000"}, {"date": "bad", "split": "2/1"}]
    component = prod.build_instrument_component("AAPL", _response(rows, received), _response(splits, received + timedelta(seconds=1)), sessions=sessions)
    daily = component["daily"]
    assert component["schema"] == "V2_INSTRUMENT_DAILY_COMPONENT_V1" and component["symbol"] == "AAPL"
    assert len(daily["bars"]) == 61 and daily["coverage_verified"] is True and daily["split_coverage_verified"] is True
    assert daily["bars"][0]["session_date"] == sessions[0].isoformat() and daily["bars"][-1]["session_date"] == PREVIOUS.isoformat()
    assert [s["factor"] for s in daily["splits"]] == [4.0, 7.0]
    assert datetime.fromisoformat(daily["splits"][0]["effective_at"]) == prod.session_open(date(2020, 8, 31))
    short = prod.build_instrument_component("AAPL", _response(rows[:-3], received), _response([], received), sessions=sessions)
    assert short["daily"]["coverage_verified"] is False and short["producer_note"]["missing_sessions"] == [s.isoformat() for s in sessions[-3:]]
    assert len(short["daily"]["bars"]) == 58  # missing sessions are left missing, never filled


def test_write_private_is_atomic_and_private(tmp_path: Path) -> None:
    target = tmp_path / "out" / "registry.json"
    digest = prod.write_private(target, b'{"a":1}')
    assert target.read_bytes() == b'{"a":1}' and len(digest) == 64
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600 and stat.S_IMODE(os.stat(target.parent).st_mode) == 0o700
    assert not (target.parent / ".registry.json.tmp").exists()


def test_orchestration_with_fake_fetcher(tmp_path: Path) -> None:
    sessions20 = prod.xnys_sessions_ending(PREVIOUS, 20)
    sessions61 = prod.xnys_sessions_ending(PREVIOUS, 61)
    now = _after_close(PREVIOUS, 240)
    calls: list[tuple[str, dict]] = []

    def fetch(path: str, params: dict) -> prod.Response:
        calls.append((path, dict(params)))
        if path == "/api/exchange-symbol-list/US":
            return _response([{"Code": "AAA", "Exchange": "NYSE", "Type": "Common Stock"}], now - timedelta(minutes=30), path)
        if path == "/api/eod-bulk-last-day/US":
            session = date.fromisoformat(params["date"])
            if params.get("type") == "splits":
                return _response([], now - timedelta(minutes=20), path)
            return _response([{"code": "AAA", "date": session.isoformat(), "open": 10, "high": 11, "low": 9, "close": 10, "volume": 5}], now - timedelta(minutes=25), path)
        if path.startswith("/api/eod/AAA.US"):
            return _response([{"date": s.isoformat(), "open": 10, "high": 11, "low": 9, "close": 10, "volume": 5} for s in sessions61], now - timedelta(minutes=10), path)
        if path.startswith("/api/splits/AAA.US"):
            return _response([], now - timedelta(minutes=9), path)
        raise AssertionError(path)

    result = prod.produce_causal_inputs(fetch, session_date=D, output_dir=tmp_path, now=now)
    assert result["registry_symbols"] == 1 and result["complete_bars"] == 1
    registry = json.loads((tmp_path / "registry.json").read_bytes())
    daily = json.loads((tmp_path / "daily_contract.json").read_bytes())
    assert registry["schema"] == "V2_CAUSAL_REGISTRY_V1" and daily["schema"] == "V2_CAUSAL_DAILY_CONTRACT_V1"
    assert len(daily["instruments"][0]["daily"]["bars"]) == 20
    assert sum(1 for path, params in calls if path == "/api/eod-bulk-last-day/US") == 40  # 20 bars + 20 splits
    components = prod.produce_instrument_components(fetch, ["AAA"], session_date=D, output_dir=tmp_path)
    assert components["incomplete"] == [] and (tmp_path / "daily_61" / "AAA.json").exists()
    with pytest.raises(prod.ProducerError, match="PREVIOUS_SESSION_NOT_CLOSED"):
        prod.produce_causal_inputs(fetch, session_date=D, output_dir=tmp_path, now=prod.session_close(PREVIOUS) - timedelta(hours=1))
    with pytest.raises(prod.ProducerError, match="SYMBOL_INVALID"):
        prod.produce_instrument_components(fetch, ["bad symbol"], session_date=D, output_dir=tmp_path)


def test_cli_is_off_by_default(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    monkeypatch.delenv("C3PO_R2D2_V2_PRODUCERS_ENABLED", raising=False)
    assert prod.main(["--session-date", "2026-09-08", "--output-dir", str(tmp_path)]) == 0
    assert '"status":"OFF"' in capsys.readouterr().out


def test_fetcher_requires_token_and_never_exposes_it() -> None:
    with pytest.raises(prod.ProducerError, match="PROVIDER_TOKEN_MISSING"):
        prod.EodhdFetcher("https://example.invalid", "   ")
    fetcher = prod.EodhdFetcher("https://example.invalid", "secret-token", retries=0, timeout=0.5)
    with pytest.raises(prod.ProducerError) as info:
        fetcher("/api/eod/AAA.US", {"period": "d"})
    assert "secret-token" not in str(info.value) and str(info.value).startswith("PROVIDER_REQUEST_FAILED:/api/eod/AAA.US")
