"""F385-8 step 2 — the live round runner without any provider: the inventory from the collector's state, the schedule
guards before any provider call, the round bound to inventory / document / receipt, facts from the producer's known
events (also before the round session), repeat protection, the quarantine audit and the signed purge, the CLI (OFF)."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping

import pytest

from app import r2d2_v2_round_emitter as emitter
from app import r2d2_v2_round_runner as runner
from app.r2d2_v2_producer_daily import ProducerError, Response, canonical
from tests.test_r2d2_v2_round_emitter import MATURITY, NOW, OPENED, RECEIVED, _iso, _known, _mode, _standard

PUBLISHED = {"2026-04-30": {"reportDate": "2026-05-20", "epsActual": 0.5}}


class _Ticker:
    """A deterministic clock: every call returns the next instant; ``last`` is the instant handed out most recently."""

    def __init__(self, start: datetime, step: timedelta = timedelta(minutes=2)) -> None:
        self.now, self.step = start, step

    def __call__(self) -> datetime:
        current = self.now
        self.now = current + self.step
        return current

    @property
    def last(self) -> datetime:
        return self.now - self.step


def _fetch(calendar: list[dict[str, Any]], histories: Mapping[str, Any], *, fail: frozenset[str] = frozenset(),
           stamp: Callable[[], datetime] | None = None) -> tuple[Callable[[str, Mapping[str, str]], Response], list[tuple[str, dict[str, str]]]]:
    """Provider responses received 30 s (calendar) / 45 s (history) after ``stamp()``; the default is the emitter tests' timeline."""
    calls: list[tuple[str, dict[str, str]]] = []

    def fetch(path: str, params: Mapping[str, str]) -> Response:
        calls.append((path, dict(params)))
        base = stamp() if stamp else RECEIVED
        if path == "/api/calendar/earnings":
            return Response(json.dumps({"type": "Earnings", "earnings": calendar}).encode(), base + timedelta(seconds=30), path)
        symbol = path.removeprefix("/api/fundamentals/").removesuffix(".US")
        if symbol in fail:
            raise ProducerError("HTTP_502")
        return Response(json.dumps(histories.get(symbol, {})).encode(), base + timedelta(seconds=45), path)

    return fetch, calls


def _record(key: str, instrument: str, status: str = "OPEN", opened: datetime = OPENED, maturity: datetime = MATURITY) -> dict[str, Any]:
    return {"episode_key": key, "instrument_key": instrument, "session": opened.astimezone(emitter.NEW_YORK).date().isoformat(),
            "opened_at": _iso(opened), "maturity_at": _iso(maturity), "arm": "ELIGIBLE", "status": status, "quantity": 1.0}


def _state(*records: dict[str, Any], ledger: bool = True) -> dict[str, Any]:
    research = {record["episode_key"]: record for record in records}
    return {"epoch": "R2D2-V2-SHADOW-test", "ledger": {"research": research, "portfolio": {}} if ledger else None, "instrument_episodes": {}}


def test_inventory_is_the_open_research_records_of_the_collector_ledger() -> None:
    state = _state(_record("ep-3", "NASDAQ:BBB"), _record("ep-1", "NYSE:AAA"), _record("ep-2", "US:AAA", status="CLOSED"),
                   _record("ep-4", "US:AAA", opened=OPENED + timedelta(days=2), maturity=MATURITY + timedelta(days=2)))
    episodes = runner.live_episodes_from_state(state)
    assert [e.instrument_key for e in episodes] == ["US:AAA", "US:BBB", "US:AAA"]  # by episode key; CLOSED excluded; keys normalized
    assert episodes[0] == emitter.Episode("US:AAA", OPENED, MATURITY) and episodes[2].opened_at == OPENED + timedelta(days=2)
    assert runner.live_episodes_from_state(_state(ledger=False)) == []  # DIAGNOSTIC epoch: no ledger, no episodes
    assert runner.lookback(episodes) == (date(2026, 9, 1), date(2026, 9, 17)) and runner.lookback([]) is None
    with pytest.raises(emitter.RoundEmitterError, match="EPISODE_INSTRUMENT_INVALID"):
        runner.live_episodes_from_state(_state(_record("ep-9", "B3:PETR4")))
    with pytest.raises(emitter.RoundEmitterError, match="LEDGER_INVALID"):
        runner.live_episodes_from_state({"ledger": {"portfolio": {}}})
    with pytest.raises(emitter.RoundEmitterError, match="EPISODE_CLOCK_INVALID"):
        runner.live_episodes_from_state(_state({**_record("ep-5", "US:CCC"), "maturity_at": "2026-09-15"}))

    class Reader:
        def read(self, epoch: str) -> dict[str, Any] | None:
            assert epoch == "R2D2-V2-SHADOW-test"
            return {"state": state, "state_sha": "a" * 64, "version": 7}

    class Empty:
        def read(self, epoch: str) -> dict[str, Any] | None:
            return None

    stored, source = runner.inventory_from_store(Reader(), "R2D2-V2-SHADOW-test")
    assert len(stored) == 3 and source == {"kind": "store", "epoch": "R2D2-V2-SHADOW-test", "state_sha": "a" * 64, "version": 7}
    with pytest.raises(emitter.RoundEmitterError, match="EPOCH_NOT_FOUND"):
        runner.inventory_from_store(Empty(), "R2D2-V2-SHADOW-test")


def test_run_round_queries_only_the_live_names_and_binds_inventory_document_and_receipt(tmp_path: Path) -> None:
    episodes = [emitter.Episode("US:AAA", OPENED, MATURITY), emitter.Episode("US:BBB", OPENED, MATURITY)]
    calendar = [{"code": "AAA.US", "report_date": "2026-09-10", "before_after_market": "AfterMarket"},
                {"code": "AAA.US", "report_date": "2026-09-03", "before_after_market": "BeforeMarket"},  # before the round session, inside the live window
                {"code": "AAA.US", "report_date": "2026-11-20", "before_after_market": "None"},         # far outside the live window
                {"code": "ZZZ.US", "report_date": "2026-09-10", "before_after_market": "None"}]         # not a live name: never consulted
    fetch, calls = _fetch(calendar, {"AAA": PUBLISHED}, fail=frozenset({"BBB"}))
    root = tmp_path / "source"
    result = runner.run_round(fetch, episodes, root, clock=_Ticker(RECEIVED), inventory_source={"kind": "store", "epoch": "R2D2-V2-SHADOW-test"})
    assert [call[0] for call in calls] == ["/api/calendar/earnings", "/api/fundamentals/AAA.US", "/api/fundamentals/BBB.US"]
    assert calls[0][1] == {"from": "2026-08-24", "to": "2026-10-06"}  # [D-15 d ∪ earliest opened, horizon maturity + 15 d ∪ latest maturity + 15 d]
    assert result["round_session"] == "2026-09-08" and result["published"] == 3 and result["quarantined"] == 0 and result["live_symbols"] == 2
    document_path = Path(result["document"])
    assert document_path.parent.parent.parent == root / "documents" and document_path.name == "earnings.json"
    assert _mode(document_path) == 0o600 and _mode(document_path.parent) == 0o700 and _mode(root / "documents") == 0o700
    data = document_path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == result["document_sha256"]
    document = json.loads(data)
    assert document["session_date"] == "2026-09-08" and document["round"]["executed_at"] == _iso(RECEIVED) and document["live_symbols"] == ["AAA", "BBB"]
    assert document["round"]["live_lookback"] == ["2026-09-01", "2026-09-15"] and set(document["symbols"]) == {"AAA", "BBB"}
    receipt = json.loads(Path(result["receipt"]).read_bytes())
    assert receipt["document_sha256"] == result["document_sha256"] and receipt["round_received_at"] == _iso(RECEIVED) and receipt["published_at"] == _iso(NOW)
    assert receipt["instruments"] == ["US:AAA", "US:BBB"] and receipt["producer"] == "fable-eodhd-earnings"
    run = json.loads(Path(result["run"]).read_bytes())
    assert run["schema"] == runner.RUN_SCHEMA and run["round_id"] == receipt["round_id"] == result["round_id"]
    assert run["repeat"] is False and run["previous_rounds"] == [] and run["live_symbols"] == ["AAA", "BBB"] and run["live_lookback"] == ["2026-09-01", "2026-09-15"]
    assert run["document"]["sha256"] == result["document_sha256"] and run["inventory"]["source"] == {"kind": "store", "epoch": "R2D2-V2-SHADOW-test"}
    assert run["inventory"]["episodes"][0] == {"instrument_key": "US:AAA", "opened_at": _iso(OPENED), "maturity_at": _iso(MATURITY)}
    assert run["inventory_sha256"] == hashlib.sha256(canonical(run["inventory"])).hexdigest() and _mode(Path(result["run"])) == 0o600
    facts: dict[str, list[tuple[Any, ...]]] = {}
    for name in sorted(os.listdir(root / "events")):
        envelope = json.loads((root / "events" / name).read_bytes())
        emitter.validate_envelope(envelope, now=NOW + timedelta(seconds=1))
        event = envelope["event"]
        facts.setdefault(event["instrument_key"], []).append((event["type"], event.get("event_date"), event.get("granularity"), event.get("reason")))
    assert sorted(facts["US:AAA"]) == [("EARNINGS", "2026-09-03", "BMO", None), ("EARNINGS", "2026-09-10", "AMC", None)]  # the pre-session fact is observed too
    assert facts["US:BBB"] == [("EARNINGS_OBSERVATION_FAILED", None, None, "EARNINGS_SOURCE_UNAVAILABLE")]
    # a second round for the same session is refused before any provider call unless the repeat is explicit
    before = len(calls)
    with pytest.raises(emitter.RoundEmitterError, match="ROUND_ALREADY_EMITTED_FOR_SESSION"):
        runner.run_round(fetch, episodes, root, clock=_Ticker(NOW + timedelta(minutes=1)))
    assert len(calls) == before
    ticker = _Ticker(NOW + timedelta(minutes=1))
    fetch2, _ = _fetch(calendar, {"AAA": PUBLISHED}, fail=frozenset({"BBB"}), stamp=lambda: ticker.last)
    again = runner.run_round(fetch2, episodes, root, clock=ticker, repeat=True)
    assert again["round_id"] != result["round_id"] and again["repeat"] is True and again["published"] == 3
    assert json.loads(Path(again["run"]).read_bytes())["previous_rounds"] == [Path(result["receipt"]).name]
    tape = [json.loads((root / "events" / name).read_bytes())["event"] for name in os.listdir(root / "events")]
    identities = {(event["earnings_event_id"], event["revision_sha256"]) for event in tape if event["type"] == "EARNINGS"}
    assert len(tape) == 6 and len(identities) == 2  # the same facts keep identity and revision across rounds; only the round ids differ


def test_schedule_guards_run_before_any_provider_call(tmp_path: Path) -> None:
    calendar = [{"code": "ZZZ.US", "report_date": "2026-09-10", "before_after_market": "None"}]
    fetch, calls = _fetch(calendar, {})
    episodes = [emitter.Episode("US:AAA", OPENED, MATURITY)]
    root = tmp_path / "source"
    cases = [
        (datetime(2026, 9, 8, 21, 30, tzinfo=timezone.utc), None, "ROUND_BEFORE_18_00_NY"),        # 17:30 ET, after the close
        (datetime(2026, 9, 12, 23, 0, tzinfo=timezone.utc), None, "ROUND_SESSION_NOT_A_SESSION"),   # Saturday
        (datetime(2026, 9, 8, 23, 0, tzinfo=timezone.utc), date(2026, 9, 7), "ROUND_SESSION_NOT_A_SESSION"),  # Labor Day
        (datetime(2026, 11, 27, 18, 30, tzinfo=timezone.utc), None, "ROUND_BEFORE_18_00_NY"),       # early close 13:00 ET; 13:30 ET
        (datetime(2026, 9, 9, 4, 30, tzinfo=timezone.utc), None, "ROUND_BEFORE_18_00_NY"),          # 00:30 ET of 09/09: 'auto' is the new date
    ]
    for instant, session, code in cases:
        with pytest.raises(emitter.RoundEmitterError, match=code):
            runner.run_round(fetch, episodes, root, session=session, clock=_Ticker(instant))
    assert calls == [] and not root.exists()
    # a delayed run keeps its intended session when told so: 00:30 ET of 09/09 is a valid round for the session of 08/09
    ticker = _Ticker(datetime(2026, 9, 9, 4, 30, tzinfo=timezone.utc))
    fetch_late, calls_late = _fetch(calendar, {}, stamp=lambda: ticker.last)
    late = runner.run_round(fetch_late, episodes, root, session=date(2026, 9, 8), clock=ticker)
    assert late["round_session"] == "2026-09-08" and [call[0] for call in calls_late] == ["/api/calendar/earnings", "/api/fundamentals/AAA.US"]
    receipt = json.loads(Path(late["receipt"]).read_bytes())
    assert receipt["round_received_at"] == "2026-09-09T04:30:00+00:00" and receipt["official_close"] == "2026-09-08T20:00:00+00:00"


def test_a_round_with_no_live_episodes_still_leaves_a_retained_receipt(tmp_path: Path) -> None:
    fetch, calls = _fetch([{"code": "ZZZ.US", "report_date": "2026-09-10", "before_after_market": "None"}], {})
    root = tmp_path / "source"
    result = runner.run_round(fetch, [], root, clock=_Ticker(RECEIVED))
    assert [call[0] for call in calls] == ["/api/calendar/earnings"] and result["published"] == 0 and result["live_symbols"] == 0
    receipt = json.loads(Path(result["receipt"]).read_bytes())
    assert receipt["instruments"] == [] and receipt["live_episodes"] == 0 and receipt["producer"] is None
    assert json.loads(Path(result["run"]).read_bytes())["live_lookback"] is None and os.listdir(root / "events") == []


def test_quarantine_audit_and_signed_purge(tmp_path: Path) -> None:
    document, episodes = _standard()
    document["symbols"]["AAA"]["evidence"]["known_events"].append(_known({"event_date": "2026-09-12", "granularity": "AMC",
                                                                          "available_at": _iso(RECEIVED - timedelta(minutes=1))}))
    root = tmp_path / "source"
    summary = emitter.emit_round(document, episodes, root, now=NOW)
    assert summary["quarantined"] == 1
    inventory = runner.quarantine_inventory(root)
    assert len(inventory) == 1 and inventory[0]["kind"] == "QUARANTINED" and inventory[0]["code"] == "AT_BEFORE_ROUND"
    item = inventory[0]
    assert item["session"] == "2026-09-08" and item["instrument_key"] == "US:AAA" and item["type"] == "EARNINGS" and item["round_id"] == summary["round_id"]
    path = root / "quarantine" / "2026-09-08" / item["file"]
    assert item["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest() and item["event_id"].startswith("earn-2026-09-08-")
    tape_file = os.listdir(root / "events")[0]
    refused = [
        ("2026-09-08", item["file"], "", "x", "PURGE_REQUIRES_SIGNER_AND_REASON"),
        ("2026-09-08", item["file"], "fable", " ", "PURGE_REQUIRES_SIGNER_AND_REASON"),
        ("2026-09-08", "../../events/" + tape_file, "fable", "x", "PURGE_TARGET_INVALID"),
        ("../events", tape_file, "fable", "x", "PURGE_TARGET_INVALID"),
        ("2026-09-08", ".hidden.json", "fable", "x", "PURGE_TARGET_INVALID"),
        ("2026-09-08", tape_file, "fable", "x", "PURGE_TARGET_NOT_IN_QUARANTINE"),
        ("2026-09-09", item["file"], "fable", "x", "PURGE_TARGET_NOT_IN_QUARANTINE"),
    ]
    for session, name, signer, reason, code in refused:
        with pytest.raises(emitter.RoundEmitterError, match=code):
            runner.purge_quarantined(root, session, name, signed_by=signer, reason=reason, now=NOW)
    assert path.exists() and len(os.listdir(root / "events")) == 4
    receipt = runner.purge_quarantined(root, "2026-09-08", item["file"], signed_by="fable",
                                       reason="AT_BEFORE_ROUND: provider clock earlier than the round; refuted by audit", now=NOW + timedelta(hours=1))
    assert not path.exists() and receipt["sha256"] == item["sha256"] and receipt["code"] == "AT_BEFORE_ROUND" and receipt["signed_by"] == "fable"
    assert receipt["round_id"] == summary["round_id"] and receipt["purged_at"] == _iso(NOW + timedelta(hours=1))
    receipt_path = root / "quarantine" / "2026-09-08" / (item["file"][:-5] + ".purge.json")
    assert _mode(receipt_path) == 0o600 and json.loads(receipt_path.read_bytes()) == receipt
    after = runner.quarantine_inventory(root)
    assert [entry["kind"] for entry in after] == ["PURGE_RECEIPT"] and after[0]["file"] == receipt_path.name
    with pytest.raises(emitter.RoundEmitterError, match="PURGE_TARGET_NOT_IN_QUARANTINE"):
        runner.purge_quarantined(root, "2026-09-08", item["file"], signed_by="fable", reason="again", now=NOW)
    (root / "quarantine" / "2026-09-08" / "garbage.json").write_bytes(b"{not json")
    kinds = {entry["file"]: entry["kind"] for entry in runner.quarantine_inventory(root)}
    assert kinds == {receipt_path.name: "PURGE_RECEIPT", "garbage.json": "UNREADABLE"}
    assert len(os.listdir(root / "events")) == 4  # the tape is never touched by the quarantine procedure


def test_cli_is_off_by_default_audits_read_only_and_runs_with_explicit_or_stored_inventory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                                            capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "source"
    settings = SimpleNamespace(r2d2_v2_shadow_source_dir=root, eodhd_base_url="https://example.invalid", eodhd_api_token="never-logged",
                               market_data_timeout_seconds=1.0)
    monkeypatch.setattr(runner, "_settings", lambda: settings)
    monkeypatch.delenv("C3PO_R2D2_V2_PRODUCERS_ENABLED", raising=False)
    episodes_file = tmp_path / "episodes.json"
    episodes_file.write_text(json.dumps([{"instrument_key": "US:AAA", "opened_at": _iso(OPENED), "maturity_at": _iso(MATURITY)}]), encoding="utf-8")
    assert runner.main(["--audit-quarantine"]) == 0  # read-only, allowed while OFF
    assert json.loads(capsys.readouterr().out) == {"status": "AUDIT", "root": str(root), "quarantine": []}
    assert runner.main(["--episodes-file", str(episodes_file)]) == 0  # OFF: nothing happens
    assert json.loads(capsys.readouterr().out)["status"] == "OFF" and not root.exists()
    monkeypatch.setenv("C3PO_R2D2_V2_PRODUCERS_ENABLED", "true")
    ticker = _Ticker(RECEIVED)
    fetch, calls = _fetch([{"code": "AAA.US", "report_date": "2026-09-10", "before_after_market": "AfterMarket"}], {"AAA": PUBLISHED}, stamp=lambda: ticker.last)
    monkeypatch.setattr(runner, "_fetcher", lambda settings: fetch)
    monkeypatch.setattr(runner, "_utc", ticker)
    assert runner.main(["--episodes-file", str(episodes_file)]) == 0
    out = capsys.readouterr().out
    first = json.loads(out)
    assert first["status"] == "EMITTED" and first["published"] == 1 and first["round_session"] == "2026-09-08" and "never-logged" not in out
    run = json.loads(Path(first["run"]).read_bytes())
    assert run["inventory"]["source"] == {"kind": "file", "path": str(episodes_file)} and run["live_symbols"] == ["AAA"]
    assert runner.main(["--episodes-file", str(episodes_file)]) == 1  # the same session again: refused
    assert json.loads(capsys.readouterr().out) == {"status": "REFUSED", "code": "ROUND_ALREADY_EMITTED_FOR_SESSION"}
    assert [call[0] for call in calls] == ["/api/calendar/earnings", "/api/fundamentals/AAA.US"]

    class Reader:
        def read(self, epoch: str) -> dict[str, Any] | None:
            assert epoch == "R2D2-V2-SHADOW-test"
            return {"state": _state(_record("ep-1", "NYSE:AAA"), _record("ep-2", "NASDAQ:BBB")), "state_sha": "b" * 64, "version": 9}

    monkeypatch.setattr(runner, "_store_reader", lambda settings: Reader())
    assert runner.main(["--epoch", "R2D2-V2-SHADOW-test", "--repeat"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["status"] == "EMITTED" and second["repeat"] is True and second["live_symbols"] == 2 and second["round_id"] != first["round_id"]
    run2 = json.loads(Path(second["run"]).read_bytes())
    assert run2["inventory"]["source"] == {"kind": "store", "epoch": "R2D2-V2-SHADOW-test", "state_sha": "b" * 64, "version": 9}
    assert runner.main(["--session-date", "2026-09-12", "--episodes-file", str(episodes_file)]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "ROUND_SESSION_NOT_A_SESSION"
    assert runner.main(["--purge-quarantine", "2026-09-08", "nothing.json", "--signed-by", "fable", "--reason", "x"]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "PURGE_TARGET_NOT_IN_QUARANTINE"
    assert runner.main(["--audit-quarantine", "--root", str(tmp_path / "elsewhere")]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "AUDIT", "root": str(tmp_path / "elsewhere"), "quarantine": []}
