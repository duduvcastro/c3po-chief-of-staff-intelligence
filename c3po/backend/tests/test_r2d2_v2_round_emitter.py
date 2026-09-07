"""F385-8 step 1 — the live earnings round emitter, without any provider: receipt rules (18:00 NY and the official
close), one window per instrument to maturity + 15 days, stable fact identities, hidden staging + atomic publication,
validation before the tape, audited quarantine, file limit refused before any write, retained round receipt."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import r2d2_v2_round_emitter as emitter
from app.r2d2_v2_producer_daily import canonical
from app.r2d2_v2_producer_earnings import AMENDMENT, AMENDMENT_SHA, REASON_EVIDENCE_INVALID, REASON_UNAVAILABLE, SCHEMA

SESSION = date(2026, 9, 8)                                   # Tuesday, a regular XNYS session (close 16:00 ET = 20:00Z)
RECEIVED = datetime(2026, 9, 8, 22, 5, tzinfo=timezone.utc)   # 18:05 ET: after 18:00 NY and after the official close
CALENDAR_AT = datetime(2026, 9, 8, 22, 5, 30, tzinfo=timezone.utc)
HISTORY_AT = datetime(2026, 9, 8, 22, 5, 45, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 8, 22, 7, tzinfo=timezone.utc)
OPENED = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)
MATURITY = datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc)
CAL_SHA = hashlib.sha256(b"calendar").hexdigest()
HIST_SHA = hashlib.sha256(b"history").hexdigest()


def _iso(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat()


def _component(events: list[dict] | None = None, reasons: list[str] | None = None) -> dict:
    return {"coverage_verified": not reasons, "window_start": _iso(CALENDAR_AT), "window_end": "2026-09-15T20:00:00+00:00",
            "events": events or [], "source_at": _iso(CALENDAR_AT), "available_at": _iso(HISTORY_AT),
            "policy": {"rule": "EXCLUSION_RULE_V1", "amendment": AMENDMENT, "amendment_sha": AMENDMENT_SHA, "producer": "fable-eodhd-earnings", "version": "v3"},
            "evidence": {"calendar_payload_sha256": CAL_SHA, "history_payload_sha256": HIST_SHA},
            "exclusion": {"excluded": bool(reasons), "reasons": reasons or []}}


def _event(event_date: str, granularity: str = "AMC", available_at: datetime = CALENDAR_AT, event_at: str | None = None) -> dict:
    item = {"event_date": event_date, "granularity": granularity, "available_at": _iso(available_at)}
    if event_at is not None:
        item["event_at"] = event_at
    return item


def _document(symbols: dict[str, dict], *, executed_at: datetime = RECEIVED, session: date = SESSION) -> dict:
    return {"schema": SCHEMA, "session_date": session.isoformat(), "rule": "EXCLUSION_RULE_V1", "amendment": AMENDMENT, "amendment_sha": AMENDMENT_SHA,
            "round": {"target": "18:00 America/New_York after the official close", "executed_at": _iso(executed_at),
                      "calendar_window": ["2026-08-24", "2026-10-06"], "live_lookback": ["2026-09-01", "2026-09-15"]},
            "horizon": {"decision_at": "2026-09-09T14:00:00+00:00", "maturity_date": "2026-09-23", "maturity_at": "2026-09-23T13:55:00+00:00",
                        "tolerance_window": ["2026-09-08", "2026-09-24"]},
            "calendar": {"from": "2026-08-24", "to": "2026-10-06", "rows": 3, "payload_sha256": CAL_SHA, "received_at": _iso(CALENDAR_AT)},
            "granularity_map": {"BeforeMarket": "BMO", "AfterMarket": "AMC", "other": "DAY", "instant": "never from this provider"},
            "live_symbols": sorted(symbols), "symbols": symbols, "counts": {"symbols": len(symbols)}}


def _episode(symbol: str, opened_at: datetime = OPENED, maturity_at: datetime = MATURITY) -> emitter.Episode:
    return emitter.Episode(f"US:{symbol}", opened_at, maturity_at)


def _standard() -> tuple[dict, list[emitter.Episode]]:
    document = _document({
        "AAA": _component([_event("2026-09-10"), _event("2026-11-20", "BMO")]),   # one inside the window, one far outside
        "BBB": _component(reasons=[REASON_UNAVAILABLE]),
        "CCC": _component([_event("2026-09-11")], reasons=[REASON_EVIDENCE_INVALID]),
        "DDD": _component(),                                                      # observed clean: nothing to emit
    })
    episodes = [_episode("AAA"), _episode("BBB"), _episode("CCC"), _episode("DDD"), _episode("EEE")]  # EEE never consulted
    return document, episodes


def test_receipt_requires_a_session_after_18_ny_and_after_the_official_close() -> None:
    document, episodes = _standard()
    receipt = emitter.build_receipt(document, episodes, published_at=NOW)
    assert len(receipt["round_id"]) == 64 and receipt["round_session"] == "2026-09-08"
    assert receipt["official_close"] == "2026-09-08T20:00:00+00:00" and receipt["round_received_at"] == _iso(RECEIVED)
    assert receipt["observation_windows"]["US:AAA"] == ["2026-09-01", "2026-09-30"]  # opened_at NY date .. maturity NY date + 15 d
    assert receipt["instruments"] == ["US:AAA", "US:BBB", "US:CCC", "US:DDD", "US:EEE"] and receipt["live_episodes"] == 5
    core = {key: value for key, value in receipt.items() if key != "round_id"}
    assert receipt["round_id"] == hashlib.sha256(canonical(core)).hexdigest()  # never date-backfilled: the hash of what was known
    with pytest.raises(emitter.RoundEmitterError, match="ROUND_BEFORE_18_00_NY"):
        emitter.build_receipt(_document(document["symbols"], executed_at=datetime(2026, 9, 8, 21, 30, tzinfo=timezone.utc)), episodes, published_at=NOW)
    with pytest.raises(emitter.RoundEmitterError, match="ROUND_SESSION_NOT_A_SESSION"):
        emitter.build_receipt(_document(document["symbols"], session=date(2026, 9, 12), executed_at=datetime(2026, 9, 12, 23, 0, tzinfo=timezone.utc)),
                              episodes, published_at=datetime(2026, 9, 12, 23, 5, tzinfo=timezone.utc))
    # early close (Friday after Thanksgiving, 13:00 ET): 13:30 ET is after the close but before 18:00 NY — both rules hold
    with pytest.raises(emitter.RoundEmitterError, match="ROUND_BEFORE_18_00_NY"):
        emitter.build_receipt(_document(document["symbols"], session=date(2026, 11, 27), executed_at=datetime(2026, 11, 27, 18, 30, tzinfo=timezone.utc)),
                              episodes, published_at=datetime(2026, 11, 27, 23, 30, tzinfo=timezone.utc))
    with pytest.raises(emitter.RoundEmitterError, match="PUBLISHED_BEFORE_ROUND"):
        emitter.build_receipt(document, episodes, published_at=RECEIVED - timedelta(seconds=1))
    with pytest.raises(emitter.RoundEmitterError, match="ROUND_DOCUMENT_SCHEMA"):
        emitter.build_receipt({**document, "schema": "OTHER"}, episodes, published_at=NOW)
    with pytest.raises(emitter.RoundEmitterError, match="ROUND_DOCUMENT_POLICY"):
        emitter.build_receipt({**document, "amendment": "EMENDA_3_REV2"}, episodes, published_at=NOW)


def test_events_are_built_per_live_instrument_with_windows_and_stable_identities() -> None:
    document, episodes = _standard()
    receipt = emitter.build_receipt(document, episodes, published_at=NOW)
    envelopes = emitter.build_events(document, episodes, receipt)
    by_instrument = {}
    for envelope in envelopes:
        emitter.validate_envelope(envelope, now=NOW)  # every produced envelope passes the collector's rules
        assert envelope["self_sha256"] == hashlib.sha256(canonical({k: v for k, v in envelope.items() if k != "self_sha256"})).hexdigest()
        by_instrument.setdefault(envelope["event"]["instrument_key"], []).append(envelope)
    assert [e["sequence"] for e in envelopes] == list(range(len(envelopes)))
    assert len({e["event_id"] for e in envelopes}) == len(envelopes) and all(e["event_id"].startswith(f"earn-2026-09-08-{receipt['round_id'][:12]}-") for e in envelopes)
    aaa = by_instrument["US:AAA"]
    assert len(aaa) == 1  # 2026-11-20 is outside the live window and is not an observation for the tape
    fact = aaa[0]["event"]
    assert fact["type"] == "EARNINGS" and fact["event_date"] == "2026-09-10" and fact["granularity"] == "AMC" and "event_at" not in fact
    assert fact["earnings_event_id"] == "ern:US:AAA:2026-09-10" and fact["revision_sha256"] == emitter.revision_sha256(fact)
    assert fact["at"] == _iso(CALENDAR_AT) and fact["available_at"] == _iso(NOW) and fact["session"] == "2026-09-08"
    assert fact["round_id"] == receipt["round_id"] and fact["round_received_at"] == _iso(RECEIVED) and fact["observation_window"] == ["2026-09-01", "2026-09-30"]
    assert fact["earnings_policy_sha"] == AMENDMENT_SHA
    assert aaa[0]["source_at"] == _iso(CALENDAR_AT) and aaa[0]["available_at"] == _iso(NOW) and aaa[0]["provenance"]["payload_sha256"] == receipt["document_sha256"]
    assert by_instrument["US:BBB"][0]["event"]["type"] == "EARNINGS_OBSERVATION_FAILED" and by_instrument["US:BBB"][0]["event"]["reason"] == "EARNINGS_SOURCE_UNAVAILABLE"
    assert by_instrument["US:CCC"][0]["event"]["reason"] == "EARNINGS_EVIDENCE_INVALID" and len(by_instrument["US:CCC"]) == 1  # invalid evidence: no EARNINGS facts
    assert "US:DDD" not in by_instrument  # observed, nothing known in the window: nothing to emit (the receipt records the instrument)
    eee = by_instrument["US:EEE"][0]["event"]
    assert eee["type"] == "EARNINGS_OBSERVATION_FAILED" and eee["reason"] == "EARNINGS_SOURCE_UNAVAILABLE" and eee["at"] == _iso(CALENDAR_AT)
    # the same fact in a later round keeps its identity and revision; another date is another fact
    later = emitter.build_receipt(_document(document["symbols"], executed_at=RECEIVED + timedelta(days=1), session=date(2026, 9, 9)), episodes,
                                  published_at=NOW + timedelta(days=1))
    again = [e for e in emitter.build_events(document, episodes, later) if e["event"]["type"] == "EARNINGS"][0]["event"]
    assert again["earnings_event_id"] == fact["earnings_event_id"] and again["revision_sha256"] == fact["revision_sha256"] and again["round_id"] != fact["round_id"]
    moved = {**fact, "event_date": "2026-09-12"}
    assert emitter.earnings_event_id("US:AAA", "2026-09-12") != fact["earnings_event_id"] and emitter.revision_sha256(moved) != fact["revision_sha256"]


def test_two_episodes_of_the_same_instrument_share_the_widest_window() -> None:
    document = _document({"AAA": _component([_event("2026-09-25")])})
    episodes = [_episode("AAA"), _episode("AAA", opened_at=OPENED + timedelta(days=5), maturity_at=MATURITY + timedelta(days=9))]
    receipt = emitter.build_receipt(document, episodes, published_at=NOW)
    assert receipt["observation_windows"] == {"US:AAA": ["2026-09-01", "2026-10-09"]}
    envelopes = emitter.build_events(document, episodes, receipt)
    assert len(envelopes) == 1 and envelopes[0]["event"]["event_date"] == "2026-09-25"


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_publish_is_atomic_private_idempotent_and_names_files_by_identity_and_hash(tmp_path: Path) -> None:
    document, episodes = _standard()
    root = tmp_path / "source"
    summary = emitter.emit_round(document, episodes, root, now=NOW)
    events_dir = root / "events"
    names = sorted(os.listdir(events_dir))
    assert summary["published"] == 4 and summary["quarantined"] == 0 and len(names) == 4
    assert not any(name.startswith(".") for name in names)  # no staging leftovers
    assert _mode(root) == 0o700 and _mode(events_dir) == 0o700 and all(_mode(events_dir / name) == 0o600 for name in names)
    for name in names:
        data = (events_dir / name).read_bytes()
        envelope = json.loads(data)
        assert name == f"{envelope['event_id']}.{envelope['self_sha256']}.json" and data == canonical(envelope)
        emitter.validate_envelope(envelope, now=NOW)
    receipt_path = Path(summary["receipt"])
    receipt = json.loads(receipt_path.read_bytes())
    assert receipt_path.name == f"2026-09-08.{receipt['round_id']}.json" and _mode(receipt_path) == 0o600 and _mode(root / "rounds") == 0o700
    assert receipt["published_count"] == 4 and [item["file"] for item in receipt["published"]] == names
    assert all(item["sha256"] == hashlib.sha256((events_dir / item["file"]).read_bytes()).hexdigest() for item in receipt["published"])
    assert receipt["events_in_tape_after"] == 4 and receipt["quarantined"] == [] and receipt["instruments"] == ["US:AAA", "US:BBB", "US:CCC", "US:DDD", "US:EEE"]
    # the same round emitted again (same receipt core) links the same bytes under the same names: no duplicates, no rewrite
    again = emitter.emit_round(document, episodes, root, now=NOW)
    assert again["round_id"] == summary["round_id"] and sorted(os.listdir(events_dir)) == names
    # a later publication instant is a new round: new round_id, new event ids, old files untouched
    later = emitter.emit_round(document, episodes, root, now=NOW + timedelta(minutes=1))
    assert later["round_id"] != summary["round_id"] and len(os.listdir(events_dir)) == 8 and all(name in os.listdir(events_dir) for name in names)


def test_invalid_envelopes_are_quarantined_and_never_reach_the_tape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    document, episodes = _standard()
    # an event whose provider reception predates the round: AT_BEFORE_ROUND — quarantined, the rest of the round is published
    document["symbols"]["AAA"]["events"].append(_event("2026-09-12", available_at=RECEIVED - timedelta(minutes=1)))
    root = tmp_path / "source"
    summary = emitter.emit_round(document, episodes, root, now=NOW)
    assert summary["published"] == 4 and summary["quarantined"] == 1
    tape = sorted(os.listdir(root / "events"))
    assert len(tape) == 4 and all(json.loads((root / "events" / name).read_bytes())["event"].get("event_date") != "2026-09-12" for name in tape)
    quarantine = root / "quarantine" / "2026-09-08"
    assert _mode(quarantine) == 0o700
    files = os.listdir(quarantine)
    assert len(files) == 1 and _mode(quarantine / files[0]) == 0o600
    item = json.loads((quarantine / files[0]).read_bytes())
    assert item["schema"] == emitter.QUARANTINE_SCHEMA and item["code"] == "AT_BEFORE_ROUND" and item["envelope"]["event"]["event_date"] == "2026-09-12"
    receipt = json.loads(Path(summary["receipt"]).read_bytes())
    assert receipt["quarantined_count"] == 1 and receipt["quarantined"][0]["code"] == "AT_BEFORE_ROUND"
    # an envelope corrupted after being built (hash no longer matches) is quarantined too
    original = emitter.build_events

    def corrupted(document, episodes, receipt):
        envelopes = original(document, episodes, receipt)
        envelopes[0]["event"]["granularity"] = "DAY"  # bytes changed after hashing
        return envelopes

    monkeypatch.setattr(emitter, "build_events", corrupted)
    summary = emitter.emit_round(_standard()[0], episodes, tmp_path / "source2", now=NOW)
    assert summary["quarantined"] == 1 and summary["published"] == 3
    codes = [json.loads((tmp_path / "source2" / "quarantine" / "2026-09-08" / name).read_bytes())["code"] for name in os.listdir(tmp_path / "source2" / "quarantine" / "2026-09-08")]
    assert codes == ["ENVELOPE_HASH_MISMATCH"]


def test_file_limit_is_refused_before_any_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    document, episodes = _standard()
    root = tmp_path / "source"
    emitter.emit_round(document, episodes, root, now=NOW)  # 4 files in the tape
    monkeypatch.setattr(emitter, "MAX_EVENT_FILES", 6)
    before = sorted(os.listdir(root / "events"))
    with pytest.raises(emitter.RoundEmitterError, match="EVENT_FILE_LIMIT"):
        emitter.emit_round(document, episodes, root, now=NOW + timedelta(minutes=2))  # 4 + 4 > 6
    assert sorted(os.listdir(root / "events")) == before and len(os.listdir(root / "rounds")) == 1  # nothing staged, no receipt


def test_read_episodes_validates_the_inventory(tmp_path: Path) -> None:
    path = tmp_path / "episodes.json"
    path.write_text(json.dumps([{"instrument_key": "US:AAA", "opened_at": _iso(OPENED), "maturity_at": _iso(MATURITY)}]), encoding="utf-8")
    episodes = emitter.read_episodes(path)
    assert episodes == [emitter.Episode("US:AAA", OPENED, MATURITY)] and episodes[0].symbol == "AAA"
    for bad in ({"instrument_key": "AAA", "opened_at": _iso(OPENED), "maturity_at": _iso(MATURITY)},
                {"instrument_key": "US:AAA", "opened_at": "2026-09-01T14:00:00", "maturity_at": _iso(MATURITY)},
                {"instrument_key": "US:AAA", "opened_at": _iso(MATURITY), "maturity_at": _iso(OPENED)}):
        path.write_text(json.dumps([bad]), encoding="utf-8")
        with pytest.raises(emitter.RoundEmitterError):
            emitter.read_episodes(path)
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(emitter.RoundEmitterError, match="EPISODES_NOT_A_LIST"):
        emitter.read_episodes(path)


def test_validate_envelope_mirrors_the_collector_rules() -> None:
    document, episodes = _standard()
    receipt = emitter.build_receipt(document, episodes, published_at=NOW)
    good = [e for e in emitter.build_events(document, episodes, receipt) if e["event"]["type"] == "EARNINGS"][0]
    failed = [e for e in emitter.build_events(document, episodes, receipt) if e["event"]["type"] != "EARNINGS"][0]

    def reseal(envelope: dict, **changes) -> dict:
        body = {k: v for k, v in envelope.items() if k != "self_sha256"}
        body["event"] = {**body["event"], **changes}
        return {**body, "self_sha256": hashlib.sha256(canonical(body)).hexdigest()}

    cases = [
        (reseal(good, event_at="2026-09-10T20:05:00+00:00"), "EVENT_AT_ONLY_FOR_INSTANT"),
        (reseal(good, event_date="2026-11-20"), "EVENT_OUTSIDE_WINDOW"),
        (reseal(good, earnings_policy_sha="0" * 64), "EARNINGS_POLICY_SHA"),
        (reseal(good, revision_sha256="0" * 64), "REVISION_SHA_MISMATCH"),
        (reseal(good, session="2026-09-09"), "EVENT_SESSION_INVALID"),
        (reseal(good, extra=1), "EVENT_KIND_OR_FIELDS"),
        (reseal(failed, reason="SOMETHING_ELSE"), "FAILURE_REASON_INVALID"),
        (reseal(good, at=_iso(RECEIVED - timedelta(seconds=1))), "AT_BEFORE_ROUND"),
        ({**good, "self_sha256": "0" * 64}, "ENVELOPE_HASH_MISMATCH"),
    ]
    for envelope, code in cases:
        with pytest.raises(emitter.RoundEmitterError, match=code):
            emitter.validate_envelope(envelope, now=NOW)
    with pytest.raises(emitter.RoundEmitterError, match="SOURCE_FUTURE_OR_REVERSED"):
        emitter.validate_envelope(good, now=NOW - timedelta(minutes=5))  # published in the future relative to the reader's clock
    emitter.validate_envelope(good, now=NOW)
    emitter.validate_envelope(failed, now=NOW)
