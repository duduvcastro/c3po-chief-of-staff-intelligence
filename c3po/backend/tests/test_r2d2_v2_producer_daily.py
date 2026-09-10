from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping

import pytest

from app import r2d2_v2_producer_daily as prod

D = date(2026, 9, 8)  # Tuesday; D-1 = Friday 2026-09-04 (Monday 07/09 is Labor Day, not a session)
PREVIOUS = date(2026, 9, 4)


def _response(payload, received_at: datetime, path: str = "/api/x") -> prod.Response:
    return prod.Response(json.dumps(payload).encode(), received_at, path)


def _after_close(day: date, minutes: int = 90) -> datetime:
    return prod.session_close(day) + timedelta(minutes=minutes)


def _registry(symbols: list[str]) -> dict:
    return {"instruments": [{"symbol": s, "market": "NYSE", "security_type": "COMMON_STOCK", "classification_verified": True} for s in symbols]}


def _bar_row(code: str, session: date, close: float = 10.5, volume: float = 1000.0) -> dict:
    return {"code": code, "exchange_short_name": "US", "date": session.isoformat(), "open": 10.0, "high": 11.0, "low": 9.0, "close": close, "volume": volume}


def test_calendar_helpers_use_official_sessions() -> None:
    assert prod.previous_session(D) == PREVIOUS  # Labor Day skipped
    assert prod.previous_session(date(2026, 9, 7)) == PREVIOUS
    sessions = prod.xnys_sessions_ending(PREVIOUS, 20)
    assert len(sessions) == 20 and sessions[-1] == PREVIOUS and sessions == tuple(sorted(sessions))
    assert prod.session_close(PREVIOUS).astimezone(prod.NEW_YORK).hour == 16
    assert prod.is_session(PREVIOUS) and not prod.is_session(date(2026, 9, 7)) and not prod.is_session(date(2026, 9, 5))
    with pytest.raises(prod.ProducerError, match="LAST_SESSION_NOT_OFFICIAL"):
        prod.xnys_sessions_ending(date(2026, 9, 7), 20)


def test_split_factor_parsing() -> None:
    assert prod.parse_split_factor("4.000000/1.000000") == 4.0
    assert prod.parse_split_factor("1.000000/10.000000") == pytest.approx(0.1)
    assert prod.parse_split_factor("3/2") == 1.5
    assert prod.parse_split_factor("0/1") is None and prod.parse_split_factor("x") is None and prod.parse_split_factor(None) is None
    assert prod.parse_split_factor("NaN/1") is None and prod.parse_split_factor("Infinity/1") is None and prod.parse_split_factor("unknown-ratio") is None


def test_registry_is_the_exact_port_document_with_a_separate_receipt() -> None:
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
    response = _response(rows, _after_close(PREVIOUS))
    registry, receipt = prod.build_registry(response, previous_close=prod.session_close(PREVIOUS))
    assert registry["schema"] == "V2_CAUSAL_REGISTRY_V1" and registry["coverage_verified"] is True
    assert set(registry) == prod.REGISTRY_FIELDS == {"schema", "source_id", "source_at", "available_at", "captured_at", "coverage_verified", "instruments"}
    symbols = {item["symbol"]: item for item in registry["instruments"]}
    assert set(symbols) == {"AAA", "BBB", "EEE", "BRK-B", "ZZZ"}
    assert symbols["AAA"] == {"symbol": "AAA", "market": "NYSE", "security_type": "COMMON_STOCK", "classification_verified": True}
    assert symbols["BBB"]["security_type"] == "ETF" and symbols["EEE"]["security_type"] == "PREFERRED_STOCK" and symbols["ZZZ"]["security_type"] == "OTHER"
    assert receipt["schema"] == "V2_PRODUCER_RECEIPT_V1" and receipt["document"] == "registry"
    assert receipt["counts"] == {"provider_rows": 9, "kept": 5, "skipped_exchange": 2, "skipped_symbol": 1, "duplicates": 1}
    assert receipt["provider_payload_sha256"] == response.sha256
    with pytest.raises(prod.ProducerError, match="REGISTRY_CAPTURED_BEFORE_CLOSE"):
        prod.build_registry(_response(rows, prod.session_close(PREVIOUS) - timedelta(minutes=1)), previous_close=prod.session_close(PREVIOUS))
    with pytest.raises(prod.ProducerError, match="REGISTRY_EMPTY"):
        prod.build_registry(_response([], _after_close(PREVIOUS)), previous_close=prod.session_close(PREVIOUS))


def test_daily_contract_assembles_20_sessions_raw_with_window_splits() -> None:
    sessions = prod.xnys_sessions_ending(PREVIOUS, 20)
    bulk, splits = {}, {}
    for index, session in enumerate(sessions):
        received = _after_close(session, 120)
        rows = [_bar_row("AAA", session, volume=1000 + index), _bar_row("BBB", session, close=9.5, volume=0),
                {"code": "CCC", "date": session.isoformat(), "open": 10.0, "high": 9.0, "low": 9.0, "close": 10.5, "volume": 1}]  # invalid OHLC every session
        if index == 3:
            rows = rows[:1]  # BBB misses one session -> incomplete window
        if index == 5:
            rows.append({"code": "AAA", "date": "1999-01-01", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1})  # wrong date ignored
            rows.append(_bar_row("AAA", session, volume=1000 + index))  # identical duplicate: counts once
        bulk[session] = _response(rows, received)
        splits[session] = _response([{"code": "AAA", "date": session.isoformat(), "split": "2.000000/1.000000"}] if index == 10 else [], received + timedelta(seconds=5))
    registry = _registry(["AAA", "BBB", "CCC"])
    registry["instruments"].append({"symbol": "ETF1", "market": "NYSE", "security_type": "ETF", "classification_verified": True})
    contract, receipt = prod.build_daily_contract(registry, bulk, splits, sessions=sessions, previous_close=prod.session_close(PREVIOUS))
    assert contract["schema"] == "V2_CAUSAL_DAILY_CONTRACT_V1"
    assert set(contract) == prod.DAILY_FIELDS == {"schema", "source_id", "source_at", "available_at", "instruments"}
    by_symbol = {item["symbol"]: item["daily"] for item in contract["instruments"]}
    assert set(by_symbol) == {"AAA", "BBB", "CCC"}  # classes the builder excludes by classification get no daily rows (size)
    aaa = by_symbol["AAA"]
    assert set(aaa) == {"bars", "splits", "adjustment", "coverage_verified", "split_coverage_verified", "source_at", "available_at"}
    assert aaa["adjustment"] == "RAW_UNADJUSTED" and len(aaa["bars"]) == 20 and aaa["coverage_verified"] is True and aaa["split_coverage_verified"] is True
    assert [bar["session_date"] for bar in aaa["bars"]] == [s.isoformat() for s in sessions]
    bar = aaa["bars"][0]
    assert set(bar) == {"session_date", "open", "high", "low", "close", "volume", "source_at", "available_at", "complete", "regular_session"}
    assert bar["close"] == 10.5 and "adjusted_close" not in bar and bar["complete"] is True and bar["regular_session"] is True
    assert datetime.fromisoformat(bar["source_at"]) > prod.session_close(sessions[0])
    assert len(aaa["splits"]) == 1 and aaa["splits"][0]["factor"] == 2.0
    assert datetime.fromisoformat(aaa["splits"][0]["effective_at"]) == prod.session_open(sessions[10])
    assert len(by_symbol["BBB"]["bars"]) == 19 and by_symbol["BBB"]["coverage_verified"] is False  # missing session left missing, never filled
    assert by_symbol["CCC"]["bars"] == [] and by_symbol["CCC"]["coverage_verified"] is False
    assert receipt["document"] == "daily_contract" and receipt["counts"]["complete_bars"] == 1 and receipt["bar_conflicts"] == {}
    assert receipt["bulk_payload_sha256"][sessions[0].isoformat()] == bulk[sessions[0]].sha256
    assert datetime.fromisoformat(contract["available_at"]) >= max(r.received_at for r in bulk.values())


def test_daily_contract_conflicting_bars_are_evidence_not_a_choice() -> None:
    sessions = prod.xnys_sessions_ending(PREVIOUS, 20)
    first = sessions[0]
    bulk = {s: _response([_bar_row("AAA", s)], _after_close(s)) for s in sessions}
    splits = {s: _response([], _after_close(s)) for s in sessions}
    forward = {**bulk, first: _response([_bar_row("AAA", first, close=10.5), _bar_row("AAA", first, close=20.0)], _after_close(first))}
    backward = {**bulk, first: _response([_bar_row("AAA", first, close=20.0), _bar_row("AAA", first, close=10.5)], _after_close(first))}
    a, receipt_a = prod.build_daily_contract(_registry(["AAA"]), forward, splits, sessions=sessions, previous_close=prod.session_close(PREVIOUS))
    b, receipt_b = prod.build_daily_contract(_registry(["AAA"]), backward, splits, sessions=sessions, previous_close=prod.session_close(PREVIOUS))
    assert a["instruments"] == b["instruments"]  # order of the payload never decides
    daily = a["instruments"][0]["daily"]
    assert daily["coverage_verified"] is False and len(daily["bars"]) == 19 and daily["bars"][0]["session_date"] == sessions[1].isoformat()
    assert receipt_a["bar_conflicts"] == {"AAA": [first.isoformat()]} == receipt_b["bar_conflicts"] and receipt_a["counts"]["bar_conflicts"] == 1


def test_daily_contract_unreadable_split_rows_make_split_coverage_unknown() -> None:
    sessions = prod.xnys_sessions_ending(PREVIOUS, 20)
    target = sessions[10]
    bulk = {s: _response([_bar_row("AAA", s), _bar_row("BBB", s)], _after_close(s)) for s in sessions}
    clean = {s: _response([], _after_close(s)) for s in sessions}
    # unreadable factor for AAA: AAA coverage unknown, BBB untouched; a split of an unlisted symbol is irrelevant
    splits = {**clean, target: _response([{"code": "AAA", "date": target.isoformat(), "split": "unknown-ratio"},
                                          {"code": "NOTLISTED", "date": target.isoformat(), "split": "x"}], _after_close(target))}
    contract, receipt = prod.build_daily_contract(_registry(["AAA", "BBB"]), bulk, splits, sessions=sessions, previous_close=prod.session_close(PREVIOUS))
    by_symbol = {item["symbol"]: item["daily"] for item in contract["instruments"]}
    assert by_symbol["AAA"]["splits"] == [] and by_symbol["AAA"]["split_coverage_verified"] is False and by_symbol["AAA"]["coverage_verified"] is True
    assert by_symbol["BBB"]["split_coverage_verified"] is True
    assert receipt["unreadable_split_rows"] == {"AAA": [{"session": target.isoformat(), "reason": "FACTOR_UNREADABLE"}]}
    # a mismatched date for AAA is unreadable too
    splits = {**clean, target: _response([{"code": "AAA", "date": "2026-01-02", "split": "2/1"}], _after_close(target))}
    contract, receipt = prod.build_daily_contract(_registry(["AAA", "BBB"]), bulk, splits, sessions=sessions, previous_close=prod.session_close(PREVIOUS))
    assert receipt["unreadable_split_rows"] == {"AAA": [{"session": target.isoformat(), "reason": "DATE_MISMATCH"}]}
    # a row that cannot be attributed to any symbol makes split coverage unknown for every symbol
    splits = {**clean, target: _response([{"date": target.isoformat(), "split": "2/1"}], _after_close(target))}
    contract, receipt = prod.build_daily_contract(_registry(["AAA", "BBB"]), bulk, splits, sessions=sessions, previous_close=prod.session_close(PREVIOUS))
    assert all(item["daily"]["split_coverage_verified"] is False for item in contract["instruments"])
    assert receipt["unattributable_split_rows"] == {target.isoformat(): 1} and receipt["counts"]["unattributable_split_rows"] == 1


def test_daily_contract_rejects_bad_windows_and_early_receipts() -> None:
    sessions = prod.xnys_sessions_ending(PREVIOUS, 20)
    ok = {s: _response([], _after_close(s)) for s in sessions}
    with pytest.raises(prod.ProducerError, match="LIQUIDITY_WINDOW_INVALID"):
        prod.build_daily_contract(_registry(["AAA"]), ok, ok, sessions=sessions[:19], previous_close=prod.session_close(PREVIOUS))
    unofficial = (*sessions[:-1], date(2026, 9, 5))  # Saturday
    with pytest.raises(prod.ProducerError, match="LIQUIDITY_WINDOW_INVALID"):
        prod.build_daily_contract(_registry(["AAA"]), ok, ok, sessions=unofficial, previous_close=prod.session_close(PREVIOUS))
    with pytest.raises(prod.ProducerError, match="LIQUIDITY_WINDOW_INVALID"):
        prod.build_daily_contract(_registry(["AAA"]), ok, ok, sessions=tuple(reversed(sessions)), previous_close=prod.session_close(PREVIOUS))
    with pytest.raises(prod.ProducerError, match="BULK_RESPONSES_INCOMPLETE"):
        prod.build_daily_contract(_registry(["AAA"]), dict(list(ok.items())[:19]), ok, sessions=sessions, previous_close=prod.session_close(PREVIOUS))
    early = dict(ok)
    early[sessions[0]] = _response([], prod.session_close(sessions[0]) - timedelta(minutes=1))
    with pytest.raises(prod.ProducerError, match="BULK_RECEIVED_BEFORE_SESSION_CLOSE"):
        prod.build_daily_contract(_registry(["AAA"]), early, ok, sessions=sessions, previous_close=prod.session_close(PREVIOUS))


def _rows61(sessions) -> list[dict]:
    return [{"date": s.isoformat(), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "adjusted_close": 50.25, "volume": 1e6} for s in sessions]


def test_instrument_component_has_exactly_61_official_sessions_and_split_history() -> None:
    sessions = prod.xnys_sessions_ending(PREVIOUS, 61)
    received = _after_close(PREVIOUS, 200)
    rows = _rows61(sessions)
    rows.insert(0, {"date": "2026-01-02", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1})  # outside the window, ignored
    splits = [{"date": "2020-08-31", "split": "4.000000/1.000000"}, {"date": "2014-06-09", "split": "7.000000/1.000000"}]
    component = prod.build_instrument_component("AAPL", _response(rows, received), _response(splits, received + timedelta(seconds=1)), sessions=sessions)
    daily = component["daily"]
    assert component["schema"] == "V2_INSTRUMENT_DAILY_COMPONENT_V1" and component["symbol"] == "AAPL" and set(component) == {"schema", "symbol", "daily", "receipt"}
    assert set(daily) == {"bars", "splits", "adjustment", "coverage_verified", "split_coverage_verified", "source_at", "available_at"}
    assert len(daily["bars"]) == 61 and daily["coverage_verified"] is True and daily["split_coverage_verified"] is True
    assert daily["bars"][0]["session_date"] == sessions[0].isoformat() and daily["bars"][-1]["session_date"] == PREVIOUS.isoformat()
    assert [s["factor"] for s in daily["splits"]] == [4.0, 7.0]
    assert datetime.fromisoformat(daily["splits"][0]["effective_at"]) == prod.session_open(date(2020, 8, 31))
    assert component["receipt"]["missing_sessions"] == [] and component["receipt"]["conflicting_sessions"] == [] and component["receipt"]["unreadable_split_rows"] == []
    short = prod.build_instrument_component("AAPL", _response(rows[:-3], received), _response([], received), sessions=sessions)
    assert short["daily"]["coverage_verified"] is False and short["receipt"]["missing_sessions"] == [s.isoformat() for s in sessions[-3:]]
    assert len(short["daily"]["bars"]) == 58  # missing sessions are left missing, never filled


def test_instrument_component_unreadable_split_rows_make_split_coverage_unknown() -> None:
    sessions = prod.xnys_sessions_ending(PREVIOUS, 61)
    received = _after_close(PREVIOUS, 200)
    eod = _response(_rows61(sessions), received)
    cases = [
        ([{"date": sessions[-2].isoformat(), "split": "unknown-ratio"}], "FACTOR_UNREADABLE"),
        ([{"date": "not-a-date", "split": "2/1"}], "DATE_UNREADABLE"),
        ([{"date": "2026-9-4", "split": "2/1"}], "DATE_UNREADABLE"),
        ([{"date": "2020-08-29", "split": "2/1"}], "DATE_NOT_AN_OFFICIAL_SESSION"),  # Saturday: no effective instant is invented
        (["2/1"], "ROW_NOT_OBJECT"),
    ]
    for rows, reason in cases:
        component = prod.build_instrument_component("AAPL", eod, _response(rows, received), sessions=sessions)
        assert component["daily"]["splits"] == [] and component["daily"]["split_coverage_verified"] is False
        assert component["receipt"]["unreadable_split_rows"] == [{"index": 0, "reason": reason}]
    mixed = prod.build_instrument_component("AAPL", eod, _response([{"date": "2020-08-31", "split": "4/1"}, {"date": "x", "split": "2/1"}], received), sessions=sessions)
    assert [s["factor"] for s in mixed["daily"]["splits"]] == [4.0] and mixed["daily"]["split_coverage_verified"] is False


def test_instrument_component_split_history_covers_1990_and_out_of_calendar_dates_are_named_never_raised() -> None:
    # The night of D=10/09 stopped in the components phase with DateOutOfBounds: the default XNYS calendar starts twenty years
    # before today (2006-09-11) and a split row of 2000 was asked to it. The calendar now covers the split history requested
    # (SPLIT_HISTORY_FROM = 1990-01-01) and a date outside its domain is named, never asked, never a crash.
    first, last = prod.calendar_bounds()
    assert prod.SPLIT_HISTORY_FROM == date(1990, 1, 1) and first == date(1990, 1, 2) and last >= D
    sessions = prod.xnys_sessions_ending(PREVIOUS, 61)
    received = _after_close(PREVIOUS, 200)
    eod = _response(_rows61(sessions), received)
    old = prod.build_instrument_component("MSFT", eod, _response([{"date": "2000-01-03", "split": "2/1"}, {"date": "2020-08-31", "split": "4/1"}], received), sessions=sessions)
    assert [s["factor"] for s in old["daily"]["splits"]] == [2.0, 4.0] and old["daily"]["split_coverage_verified"] is True
    assert datetime.fromisoformat(old["daily"]["splits"][0]["effective_at"]) == prod.session_open(date(2000, 1, 3))
    assert old["receipt"]["unreadable_split_rows"] == []
    assert prod.session_status(date(2000, 1, 3)) == "SESSION" and prod.session_status(date(2000, 1, 1)) == "NOT_SESSION"  # a Saturday
    assert prod.session_status(first) == "SESSION" and prod.session_status(first - timedelta(days=1)) == "OUT_OF_CALENDAR"
    for stamp in ("1985-06-03", "1989-12-29", (last + timedelta(days=1)).isoformat(), "2099-01-04"):
        assert prod.session_status(date.fromisoformat(stamp)) == "OUT_OF_CALENDAR"
        component = prod.build_instrument_component("MSFT", eod, _response([{"date": stamp, "split": "2/1"}, {"date": "2020-08-31", "split": "4/1"}], received), sessions=sessions)
        assert [s["factor"] for s in component["daily"]["splits"]] == [4.0] and component["daily"]["split_coverage_verified"] is False
        assert component["receipt"]["unreadable_split_rows"] == [{"index": 0, "reason": "DATE_OUTSIDE_CALENDAR"}]


def test_instrument_component_conflicts_and_early_receipts_are_never_resolved_silently() -> None:
    sessions = prod.xnys_sessions_ending(PREVIOUS, 61)
    received = _after_close(PREVIOUS, 200)
    rows = _rows61(sessions)
    conflict = {"date": sessions[0].isoformat(), "open": 20.0, "high": 21.0, "low": 19.0, "close": 20.0, "volume": 2_000_000}
    a = prod.build_instrument_component("SYN", _response(rows + [conflict], received), _response([], received), sessions=sessions)
    b = prod.build_instrument_component("SYN", _response([conflict] + rows, received), _response([], received), sessions=sessions)
    assert a["daily"] == b["daily"] and a["daily"]["coverage_verified"] is False and len(a["daily"]["bars"]) == 60
    assert a["daily"]["bars"][0]["session_date"] == sessions[1].isoformat()
    assert a["receipt"]["conflicting_sessions"] == [sessions[0].isoformat()] and a["receipt"]["missing_sessions"] == []
    same = prod.build_instrument_component("SYN", _response(rows + [dict(rows[0])], received), _response([], received), sessions=sessions)
    assert same["daily"]["coverage_verified"] is True and len(same["daily"]["bars"]) == 61  # identical duplicate is not a conflict
    early = prod.session_close(PREVIOUS) - timedelta(hours=1)
    with pytest.raises(prod.ProducerError, match="EOD_RECEIVED_BEFORE_SESSION_CLOSE"):
        prod.build_instrument_component("SYN", _response(rows, early), _response([], received), sessions=sessions)
    with pytest.raises(prod.ProducerError, match="EOD_RECEIVED_BEFORE_SESSION_CLOSE"):
        prod.build_instrument_component("SYN", _response(rows, received), _response([], early), sessions=sessions)
    with pytest.raises(prod.ProducerError, match="ATR_WINDOW_INVALID"):
        prod.build_instrument_component("SYN", _response(rows, received), _response([], received), sessions=sessions[1:])
    with pytest.raises(prod.ProducerError, match="ATR_WINDOW_INVALID"):
        prod.build_instrument_component("SYN", _response(rows, received), _response([], received), sessions=(*sessions[:-1], date(2026, 9, 7)))


def test_write_private_is_atomic_and_private(tmp_path: Path) -> None:
    target = tmp_path / "out" / "registry.json"
    digest = prod.write_private(target, b'{"a":1}')
    assert target.read_bytes() == b'{"a":1}' and len(digest) == 64
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600 and stat.S_IMODE(os.stat(target.parent).st_mode) == 0o700
    assert not (target.parent / ".registry.json.tmp").exists()


def test_orchestration_writes_port_documents_and_bound_receipts(tmp_path: Path) -> None:
    sessions61 = prod.xnys_sessions_ending(PREVIOUS, 61)
    now = _after_close(PREVIOUS, 240)
    calls: list[tuple[str, dict]] = []

    def fetch(path: str, params: Mapping[str, str]) -> prod.Response:
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
    assert result["registry_symbols"] == 1 and result["complete_bars"] == 1 and result["bar_conflicts"] == 0
    for name in ("registry", "daily_contract"):
        document_bytes = (tmp_path / f"{name}.json").read_bytes()
        receipt = json.loads((tmp_path / f"{name}.receipt.json").read_bytes())
        assert hashlib.sha256(document_bytes).hexdigest() == result[f"{name}_sha256"] == receipt["document_sha256"]
        assert receipt["document_file"] == f"{name}.json" and receipt["session_date"] == D.isoformat() and receipt["schema"] == "V2_PRODUCER_RECEIPT_V1"
        assert hashlib.sha256((tmp_path / f"{name}.receipt.json").read_bytes()).hexdigest() == result[f"{name}_receipt_sha256"]
    registry = json.loads((tmp_path / "registry.json").read_bytes())
    daily = json.loads((tmp_path / "daily_contract.json").read_bytes())
    assert set(registry) == prod.REGISTRY_FIELDS and set(daily) == prod.DAILY_FIELDS  # exactly what the signed reader accepts
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
