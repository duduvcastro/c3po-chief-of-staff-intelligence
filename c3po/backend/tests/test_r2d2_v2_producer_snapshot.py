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


def _tick(symbol: str, bid: float | None, ask: float | None, at: datetime) -> str:
    item: dict = {"s": symbol, "t": int(at.timestamp() * 1000)}
    if bid is not None:
        item["bp"] = bid
    if ask is not None:
        item["ap"] = ask
    return json.dumps(item)


def _root(tmp_path: Path, symbols: list[str], *, with_components: bool = True) -> Path:
    root = tmp_path / "epoch-root"
    (root / "causal_list" / EPOCH).mkdir(parents=True)
    commitment = {"commitment": {"epoch": EPOCH, "session": D.isoformat(), "list": symbols}, "audit_receipt": {}, "publication_receipt": {}}
    (root / "causal_list" / EPOCH / f"{D.isoformat()}.json").write_bytes(canonical(commitment))
    if with_components:
        base = root / "components" / D.isoformat()
        (base / "daily_61").mkdir(parents=True)
        for symbol in symbols[:1]:
            (base / "daily_61" / f"{symbol}.json").write_bytes(canonical({"schema": "V2_INSTRUMENT_DAILY_COMPONENT_V1", "symbol": symbol,
                "daily": {"bars": [{"session_date": "2026-09-04"}], "splits": [], "adjustment": "RAW_UNADJUSTED", "coverage_verified": True,
                          "split_coverage_verified": True, "source_at": "2026-09-05T00:00:00+00:00", "available_at": "2026-09-05T00:00:01+00:00"}}))
        (base / "risk.json").write_bytes(canonical({symbols[0]: {"value": 30.5, "producer": "codex-risk", "source_at": "2026-09-08T13:50:00+00:00", "available_at": "2026-09-08T13:50:01+00:00"}}))
        (base / "registry.json").write_bytes(canonical({"schema": "V2_CAUSAL_REGISTRY_V1", "instruments": [
            {"symbol": s, "market": "NASDAQ", "security_type": "COMMON_STOCK", "classification_verified": True} for s in symbols]}))
    return root


def test_capture_window_is_10_00_to_10_01_new_york() -> None:
    assert OPEN_AT.astimezone(snap.NEW_YORK).strftime("%H:%M:%S") == "10:00:00"
    assert CLOSE_AT - OPEN_AT == timedelta(minutes=1)


def test_causal_symbols_and_components_are_read_strictly(tmp_path: Path) -> None:
    root = _root(tmp_path, ["AAA", "BBB"])
    assert snap.read_causal_symbols(root, EPOCH, D) == ["AAA", "BBB"]
    with pytest.raises(ProducerError, match="CAUSAL_LIST_UNREADABLE"):
        snap.read_causal_symbols(root, "R2D2-V2-SHADOW-OTHER", D)
    (root / "causal_list" / EPOCH / f"{D.isoformat()}.json").write_bytes(canonical({"commitment": {"epoch": EPOCH, "session": "2026-09-09", "list": ["AAA"]}}))
    with pytest.raises(ProducerError, match="CAUSAL_LIST_INVALID"):
        snap.read_causal_symbols(root, EPOCH, D)
    components = snap.load_components(root, D, ["AAA", "BBB"])
    assert set(components.daily) == {"AAA"} and set(components.risk) == {"AAA"} and components.earnings == {}
    assert components.registry["BBB"]["market"] == "NASDAQ"


def test_quote_book_keeps_latest_tick_and_ignores_unlisted_or_regressing() -> None:
    book = snap.QuoteBook()
    allowed = {"AAA"}
    t0 = OPEN_AT + timedelta(seconds=1)
    assert book.record(_tick("AAA", 10.0, 10.1, t0), t0 + timedelta(milliseconds=50), allowed) == "AAA"
    assert book.record(_tick("ZZZ", 1.0, 1.1, t0), t0, allowed) is None
    assert book.record(_tick("AAA", 9.0, 9.1, t0 - timedelta(seconds=5)), t0 + timedelta(seconds=1), allowed) is None  # older tick
    assert book.record("not json", t0, allowed) is None
    assert book.record(_tick("AAA", None, 10.2, t0 + timedelta(seconds=2)), t0 + timedelta(seconds=2), allowed) == "AAA"
    quote = book.quotes["AAA"]
    assert quote.bid is None and quote.ask == 10.2 and quote.tick_at == t0 + timedelta(seconds=2)
    assert book.updates["AAA"] == 2 and len(book.tape) == 5  # the raw tape keeps every payload, valid or not
    assert book.tape_sha256() == hashlib.sha256("\n".join(book.tape).encode()).hexdigest()


def test_assembled_snapshot_matches_the_port_envelope_and_instrument_shape(tmp_path: Path) -> None:
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
        assert set(row["daily"]) == {"bars", "splits", "adjustment", "coverage_verified", "split_coverage_verified", "source_at", "available_at"}
        assert set(row["risk"]) == {"value", "producer", "source_at", "available_at"}
        assert set(row["earnings"]) == {"coverage_verified", "window_start", "window_end", "events", "source_at", "available_at"}
    aaa = rows["AAA"]
    assert aaa["quote"]["bid"] == 99.95 and aaa["quote"]["ask"] == 100.05
    assert datetime.fromisoformat(aaa["quote"]["bid_source_at"]) == tick_at == datetime.fromisoformat(aaa["quote"]["ask_source_at"])
    assert datetime.fromisoformat(aaa["quote"]["received_at"]) == tick_at + timedelta(milliseconds=20)
    assert datetime.fromisoformat(aaa["quote"]["available_at"]) == now and aaa["sequence"] == 1
    assert aaa["risk"]["value"] == 30.5 and aaa["daily"]["coverage_verified"] is True
    assert aaa["earnings"]["coverage_verified"] is False  # component missing -> explicit invalid, never invented
    bbb = rows["BBB"]
    assert bbb["quote"]["bid"] is None and bbb["quote"]["ask"] is None and bbb["quote"]["bid_source_at"] is None and bbb["sequence"] == 0
    assert bbb["risk"]["value"] is None and bbb["daily"]["coverage_verified"] is False
    assert datetime.fromisoformat(body["source_at"]) == tick_at and datetime.fromisoformat(body["available_at"]) == now


def test_run_capture_publishes_only_inside_the_window_and_keeps_the_tape(tmp_path: Path) -> None:
    root = _root(tmp_path, ["AAA", "BBB"])
    components = snap.load_components(root, D, ["AAA", "BBB"])
    clock_at = {"now": OPEN_AT - timedelta(seconds=2)}

    def clock() -> datetime:
        return clock_at["now"]

    async def sleep(seconds: float) -> None:
        clock_at["now"] += timedelta(seconds=0.5)
        await asyncio.sleep(0)

    async def ticks(symbols: list[str]) -> AsyncIterator[tuple[str, datetime]]:
        assert symbols == ["AAA", "BBB"]
        moments = [OPEN_AT - timedelta(seconds=1), OPEN_AT + timedelta(seconds=10), OPEN_AT + timedelta(seconds=40)]
        for index, at in enumerate(moments):
            while clock_at["now"] < at:
                await asyncio.sleep(0)
            yield _tick("AAA", 10.0 + index, 10.1 + index, at), at + timedelta(milliseconds=10)
        while clock_at["now"] < CLOSE_AT:
            await asyncio.sleep(0)

    result = asyncio.run(snap.run_capture(root=root, epoch=EPOCH, session_date=D, symbols=["AAA", "BBB"], components=components,
                                          ticks=ticks, clock=clock, sleep=sleep, publish_interval=10.0))
    published = result["published"]
    assert published and all(OPEN_AT <= datetime.fromisoformat(p["available_at"]) < CLOSE_AT for p in published)
    assert [p["sequence"] for p in published] == list(range(1, len(published) + 1))
    assert published[-1]["quoted"] == 1 and result["quoted_symbols"] == 1
    snapshot = json.loads((root / "snapshot.json").read_bytes())
    assert snapshot["sequence"] == published[-1]["sequence"] and snapshot["self_sha256"] == published[-1]["self_sha256"]
    row = next(r for r in snapshot["universe"]["instruments"] if r["symbol"] == "AAA")
    assert row["quote"]["bid"] == 12.0  # latest tick at 10:00:40
    assert stat.S_IMODE(os.stat(root / "snapshot.json").st_mode) == 0o600
    tape = Path(result["tape_file"])
    lines = [json.loads(line) for line in tape.read_text().splitlines()]
    assert len(lines) == 3 and all(set(line) == {"received_at", "payload"} for line in lines)
    assert stat.S_IMODE(os.stat(tape).st_mode) == 0o600
    assert snapshot["provenance"]["payload_sha256"] == hashlib.sha256("\n".join(l["payload"] for l in lines).encode()).hexdigest()


def test_cli_is_off_by_default(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    monkeypatch.delenv("C3PO_R2D2_V2_PRODUCERS_ENABLED", raising=False)
    assert snap.main(["--epoch", EPOCH, "--session-date", D.isoformat(), "--root", str(tmp_path)]) == 0
    assert '"status":"OFF"' in capsys.readouterr().out
