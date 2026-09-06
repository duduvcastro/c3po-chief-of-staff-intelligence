from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator

import pytest

from app import r2d2_v2_producer_snapshot as snap
from app.r2d2_v2_producer_daily import ProducerError, canonical

D = date(2026, 9, 8)
EPOCH = "R2D2-V2-SHADOW-TEST"
OPEN_AT, CLOSE_AT = snap.capture_window(D)
DAILY_AAA = {"bars": [{"session_date": "2026-09-04"}], "splits": [], "adjustment": "RAW_UNADJUSTED", "coverage_verified": True,
             "split_coverage_verified": True, "source_at": "2026-09-05T00:00:00+00:00", "available_at": "2026-09-05T00:00:01+00:00"}
RISK_AAA = {"value": 30.5, "producer": "codex-risk", "source_at": "2026-09-08T13:50:00+00:00", "available_at": "2026-09-08T13:50:01+00:00"}


def _tick(symbol: str, bid: float | None, ask: float | None, at: datetime, t=None) -> str:
    item: dict = {"s": symbol, "t": int(at.timestamp() * 1000) if t is None else t}
    if bid is not None:
        item["bp"] = bid
    if ask is not None:
        item["ap"] = ask
    return json.dumps(item)


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def _root(tmp_path: Path, symbols: list[str], *, with_components: bool = True) -> Path:
    root = tmp_path / "epoch-root"
    _write(root / "causal_list" / EPOCH / f"{D.isoformat()}.json",
           {"commitment": {"epoch": EPOCH, "session": D.isoformat(), "list": symbols}, "audit_receipt": {}, "publication_receipt": {}})
    if with_components:
        base = root / "components" / D.isoformat()
        _write(base / "daily_61" / f"{symbols[0]}.json", {"schema": "V2_INSTRUMENT_DAILY_COMPONENT_V1", "symbol": symbols[0], "daily": DAILY_AAA, "receipt": {}})
        _write(base / "risk.json", {"schema": "V2_RISK_COMPONENTS_V1", "session_date": D.isoformat(), "symbols": {symbols[0]: RISK_AAA}})
        _write(base / "registry.json", {"schema": "V2_CAUSAL_REGISTRY_V1", "instruments": [
            {"symbol": s, "market": "NASDAQ", "security_type": "COMMON_STOCK", "classification_verified": True} for s in symbols]})
    return root


def test_capture_window_is_10_00_to_10_01_new_york() -> None:
    assert OPEN_AT.astimezone(snap.NEW_YORK).strftime("%H:%M:%S") == "10:00:00"
    assert CLOSE_AT - OPEN_AT == timedelta(minutes=1)


def test_causal_symbols_and_components_are_read_and_validated(tmp_path: Path) -> None:
    root = _root(tmp_path, ["AAA", "BBB"])
    assert snap.read_causal_symbols(root, EPOCH, D) == ["AAA", "BBB"]
    with pytest.raises(ProducerError, match="CAUSAL_LIST_UNREADABLE"):
        snap.read_causal_symbols(root, "R2D2-V2-SHADOW-OTHER", D)
    _write(root / "causal_list" / EPOCH / f"{D.isoformat()}.json", {"commitment": {"epoch": EPOCH, "session": "2026-09-09", "list": ["AAA"]}})
    with pytest.raises(ProducerError, match="CAUSAL_LIST_INVALID"):
        snap.read_causal_symbols(root, EPOCH, D)
    components = snap.load_components(root, D, ["AAA", "BBB"])
    assert set(components.daily) == {"AAA"} and set(components.risk) == {"AAA"} and components.earnings == {}
    assert components.registry["BBB"]["market"] == "NASDAQ"
    assert components.diagnostics == {"AAA": ("EARNINGS_COMPONENT_ABSENT",),
                                      "BBB": ("DAILY_COMPONENT_ABSENT", "RISK_COMPONENT_ABSENT", "EARNINGS_COMPONENT_ABSENT")}
    assert components.diagnostic_counts() == {"EARNINGS_COMPONENT_ABSENT": 2, "DAILY_COMPONENT_ABSENT": 1, "RISK_COMPONENT_ABSENT": 1}
    base = root / "components" / D.isoformat()
    _write(base / "risk.json", {"schema": "V2_RISK_COMPONENTS_V1", "session_date": "2026-09-09", "symbols": {"AAA": RISK_AAA}})  # wrong session
    _write(base / "daily_61" / "AAA.json", {"schema": "V2_INSTRUMENT_DAILY_COMPONENT_V1", "symbol": "AAA", "daily": {**DAILY_AAA, "extra": 1}})
    _write(base / "earnings.json", {"schema": "V2_EARNINGS_COMPONENTS_V2", "session_date": D.isoformat(), "symbols": {"AAA": {"coverage_verified": True}}})
    components = snap.load_components(root, D, ["AAA", "BBB"])
    assert components.daily == {} and components.risk == {} and components.earnings == {}
    assert components.diagnostics["AAA"] == ("DAILY_COMPONENT_INVALID", "RISK_DOCUMENT_INVALID", "EARNINGS_COMPONENT_INVALID")
    assert components.diagnostics["BBB"] == ("DAILY_COMPONENT_ABSENT", "RISK_DOCUMENT_INVALID", "EARNINGS_COMPONENT_ABSENT")


def test_quote_book_accepts_only_finite_causal_ticks_and_never_raises() -> None:
    book = snap.QuoteBook()
    allowed = {"AAA"}
    t0 = OPEN_AT + timedelta(seconds=1)
    assert book.record(_tick("AAA", 10.0, 10.1, t0), t0 + timedelta(milliseconds=50), allowed) == "AAA"
    assert book.record(_tick("ZZZ", 1.0, 1.1, t0), t0, allowed) is None
    assert book.record(_tick("AAA", 9.0, 9.1, t0 - timedelta(seconds=5)), t0 + timedelta(seconds=1), allowed) is None  # older tick
    assert book.record("not json", t0, allowed) is None
    assert book.record("[1,2]", t0, allowed) is None
    # a tick clocked after its receipt is not causal: rejected, and the next causal tick is still accepted
    assert book.record(_tick("AAA", 50.0, 50.1, t0 + timedelta(minutes=5)), t0 + timedelta(seconds=2), allowed) is None
    assert book.record(_tick("AAA", None, 10.2, t0 + timedelta(seconds=2)), t0 + timedelta(seconds=2), allowed) == "AAA"
    quote = book.quotes["AAA"]
    assert quote.bid is None and quote.ask == 10.2 and quote.tick_at == t0 + timedelta(seconds=2)
    for bad in ("NaN", "Infinity", "-Infinity", "-5", "0", "true", '"1"', "1e300"):
        assert book.record('{"s":"AAA","t":' + bad + ',"bp":10,"ap":10.01}', t0 + timedelta(seconds=3), allowed) is None
    assert book.record('{"s":"AAA","t":' + str(int((t0 + timedelta(seconds=3)).timestamp() * 1000)) + ',"bp":NaN,"ap":-1}', t0 + timedelta(seconds=3), allowed) == "AAA"
    assert book.quotes["AAA"].bid is None and book.quotes["AAA"].ask is None  # non-finite or non-positive prices are unknown, not invented
    assert book.updates["AAA"] == 3 and len(book.tape) == 16  # the raw tape keeps every payload, valid or not
    assert book.rejected == {"SYMBOL_NOT_LISTED": 1, "TICK_REGRESSES": 1, "NOT_JSON": 1, "NOT_OBJECT": 1, "TICK_IN_FUTURE": 1,
                             "TICK_CLOCK_INVALID": 7, "PAYLOAD_ERROR": 1}
    assert book.tape_sha256() == hashlib.sha256("\n".join(book.tape).encode()).hexdigest()


def test_assembled_snapshot_matches_the_port_shape_and_keeps_absent_components_pending(tmp_path: Path) -> None:
    root = _root(tmp_path, ["AAA", "BBB"])
    components = snap.load_components(root, D, ["AAA", "BBB"])
    book = snap.QuoteBook()
    tick_at = OPEN_AT + timedelta(seconds=3)
    book.record(_tick("AAA", 99.95, 100.05, tick_at), tick_at + timedelta(milliseconds=20), {"AAA", "BBB"})
    now = OPEN_AT + timedelta(seconds=4)
    body = snap.assemble_snapshot(["AAA", "BBB"], book, components, now=now, sequence=7)
    assert set(body) == {"schema", "manifest_sha", "amendment_sha", "source_id", "provenance", "source_at", "available_at", "sequence", "universe", "self_sha256"}
    assert body["schema"] == "V2_SHADOW_SOURCE_SNAPSHOT_V2" and body["manifest_sha"] == snap.MANIFEST_SHA and body["amendment_sha"] == snap.AMENDMENT_SHA
    assert set(body["provenance"]) == {"producer", "version", "payload_sha256"} and body["sequence"] == 7
    expected = hashlib.sha256(canonical({k: v for k, v in body.items() if k != "self_sha256"})).hexdigest()
    assert body["self_sha256"] == expected
    assert body["universe"]["coverage_verified"] is True
    rows = {row["symbol"]: row for row in body["universe"]["instruments"]}
    assert set(rows) == {"AAA", "BBB"}
    for row in rows.values():
        assert set(row) == {"symbol", "market", "security_type", "classification_verified", "sequence", "source_at", "available_at", "quote", "daily", "risk", "earnings"}
        assert set(row["quote"]) == {"bid", "ask", "bid_source_at", "ask_source_at", "received_at", "available_at"}
        assert set(row["daily"]) == snap.DAILY_KEYS and set(row["risk"]) == snap.RISK_KEYS and set(row["earnings"]) == snap.EARNINGS_KEYS
    aaa = rows["AAA"]
    assert aaa["quote"]["bid"] == 99.95 and aaa["quote"]["ask"] == 100.05
    assert datetime.fromisoformat(aaa["quote"]["bid_source_at"]) == tick_at == datetime.fromisoformat(aaa["quote"]["ask_source_at"])
    assert datetime.fromisoformat(aaa["quote"]["received_at"]) == tick_at + timedelta(milliseconds=20)
    assert datetime.fromisoformat(aaa["quote"]["available_at"]) == now and aaa["sequence"] == 1
    assert aaa["risk"] == RISK_AAA and aaa["daily"] == DAILY_AAA  # prepared components pass through unchanged
    assert aaa["earnings"] == snap.pending_earnings() and aaa["earnings"]["available_at"] is None  # not arrived: PENDING, no invented clock
    assert datetime.fromisoformat(aaa["source_at"]) == datetime.fromisoformat(DAILY_AAA["source_at"])  # earliest source clock of the row
    bbb = rows["BBB"]
    assert bbb["quote"]["bid"] is None and bbb["quote"]["ask"] is None and bbb["quote"]["bid_source_at"] is None and bbb["sequence"] == 0
    assert bbb["daily"] == snap.pending_daily() and bbb["risk"] == snap.pending_risk() and bbb["earnings"] == snap.pending_earnings()
    assert all(component["source_at"] is None and component["available_at"] is None for component in (bbb["daily"], bbb["risk"], bbb["earnings"]))
    assert datetime.fromisoformat(bbb["source_at"]) == now  # nothing arrived for this row: its clocks describe the assembly only
    assert datetime.fromisoformat(body["source_at"]) == tick_at and datetime.fromisoformat(body["available_at"]) == now
    # a component that arrived and concluded invalid keeps its own clocks and verdict
    concluded = {**DAILY_AAA, "coverage_verified": False, "bars": []}
    _write(root / "components" / D.isoformat() / "daily_61" / "BBB.json", {"schema": "V2_INSTRUMENT_DAILY_COMPONENT_V1", "symbol": "BBB", "daily": concluded})
    body = snap.assemble_snapshot(["AAA", "BBB"], book, snap.load_components(root, D, ["AAA", "BBB"]), now=now, sequence=8)
    assert next(r for r in body["universe"]["instruments"] if r["symbol"] == "BBB")["daily"] == concluded


def _clock_and_sleep():
    clock_at = {"now": OPEN_AT - timedelta(seconds=2)}

    def clock() -> datetime:
        return clock_at["now"]

    async def sleep(seconds: float) -> None:
        clock_at["now"] += timedelta(seconds=0.5)
        await asyncio.sleep(0)

    return clock_at, clock, sleep


def test_run_capture_publishes_inside_the_window_reloads_components_and_keeps_the_tape(tmp_path: Path) -> None:
    root = _root(tmp_path, ["AAA", "BBB"])
    loader = snap.ComponentLoader(root, D, ["AAA", "BBB"])
    clock_at, clock, sleep = _clock_and_sleep()
    risk_written = {"done": False}

    async def ticks(symbols: list[str]) -> AsyncIterator[tuple[str, datetime]]:
        assert symbols == ["AAA", "BBB"]
        moments = [OPEN_AT - timedelta(seconds=1), OPEN_AT + timedelta(seconds=10), OPEN_AT + timedelta(seconds=40)]
        for index, at in enumerate(moments):
            while clock_at["now"] < at:
                await asyncio.sleep(0)
            yield _tick("AAA", 10.0 + index, 10.1 + index, at), at + timedelta(milliseconds=10)
            if index == 1:  # a risk response for BBB lands during the window
                _write(root / "components" / D.isoformat() / "risk.json",
                       {"schema": "V2_RISK_COMPONENTS_V1", "session_date": D.isoformat(), "symbols": {"AAA": RISK_AAA, "BBB": {**RISK_AAA, "value": 61.0}}})
                risk_written["done"] = True
        yield _tick("AAA", 99.0, 99.1, OPEN_AT + timedelta(seconds=50), t="NaN"), OPEN_AT + timedelta(seconds=50)
        while clock_at["now"] < CLOSE_AT:
            await asyncio.sleep(0)

    result = asyncio.run(snap.run_capture(root=root, epoch=EPOCH, session_date=D, symbols=["AAA", "BBB"], components=loader,
                                          ticks=ticks, clock=clock, sleep=sleep, publish_interval=10.0))
    published = result["published"]
    assert result["status"] == "CAPTURED" and result["consumer_error"] is None
    assert published and all(OPEN_AT <= datetime.fromisoformat(p["available_at"]) < CLOSE_AT for p in published)
    assert [p["sequence"] for p in published] == list(range(1, len(published) + 1))
    assert published[0]["component_diagnostics"]["RISK_COMPONENT_ABSENT"] == 1 and "RISK_COMPONENT_ABSENT" not in published[-1]["component_diagnostics"]
    assert published[-1]["quoted"] == 1 and result["quoted_symbols"] == 1 and result["rejected_ticks"] == {"TICK_CLOCK_INVALID": 1}
    assert result["component_diagnostics"] == {"AAA": ["EARNINGS_COMPONENT_ABSENT"], "BBB": ["DAILY_COMPONENT_ABSENT", "EARNINGS_COMPONENT_ABSENT"]}
    snapshot = json.loads((root / "snapshot.json").read_bytes())
    assert snapshot["sequence"] == published[-1]["sequence"] and snapshot["self_sha256"] == published[-1]["self_sha256"]
    rows = {r["symbol"]: r for r in snapshot["universe"]["instruments"]}
    assert rows["AAA"]["quote"]["bid"] == 12.0  # latest causal tick at 10:00:40; the NaN tick never replaced it
    assert rows["BBB"]["risk"]["value"] == 61.0 and risk_written["done"]  # the late component was picked up by a later publication
    assert stat.S_IMODE(os.stat(root / "snapshot.json").st_mode) == 0o600
    tape = Path(result["tape_file"])
    lines = [json.loads(line) for line in tape.read_text().splitlines()]
    assert len(lines) == 4 and all(set(line) == {"received_at", "payload"} for line in lines)
    assert stat.S_IMODE(os.stat(tape).st_mode) == 0o600
    assert snapshot["provenance"]["payload_sha256"] == hashlib.sha256("\n".join(l["payload"] for l in lines).encode()).hexdigest()


def test_run_capture_reports_a_failed_consumer_instead_of_declaring_capture(tmp_path: Path) -> None:
    root = _root(tmp_path, ["AAA"])
    components = snap.load_components(root, D, ["AAA"])
    clock_at, clock, sleep = _clock_and_sleep()

    async def ticks(symbols: list[str]) -> AsyncIterator[tuple[str, datetime]]:
        at = OPEN_AT + timedelta(seconds=5)
        while clock_at["now"] < at:
            await asyncio.sleep(0)
        yield _tick("AAA", 10.0, 10.1, at), at
        raise RuntimeError("feed broke")

    result = asyncio.run(snap.run_capture(root=root, epoch=EPOCH, session_date=D, symbols=["AAA"], components=components,
                                          ticks=ticks, clock=clock, sleep=sleep, publish_interval=10.0))
    assert result["status"] == "CAPTURE_DEGRADED_CONSUMER_FAILED" and result["consumer_error"] == "RuntimeError"
    assert len(result["published"]) >= 5  # publication continued with the last causal quotes until the window closed
    assert result["quoted_symbols"] == 1


def test_cli_is_off_by_default(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    monkeypatch.delenv("C3PO_R2D2_V2_PRODUCERS_ENABLED", raising=False)
    assert snap.main(["--epoch", EPOCH, "--session-date", D.isoformat(), "--root", str(tmp_path)]) == 0
    assert '"status":"OFF"' in capsys.readouterr().out
