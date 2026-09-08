"""F385-8 step 1 -> the real V2 port: the collector (`FileShadowSource.events`) reads the tape the emitter published
with zero diagnostics, every event passes `validate_observation`, `window_covers` accepts the live episode, hidden
staging files and the quarantine never reach the collector. Skipped where the port is not checked out."""
from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

import pytest

sources = pytest.importorskip("app.r2d2_v2_sources")
events_module = pytest.importorskip("app.r2d2_v2_earnings_events")

from app import r2d2_v2_round_emitter as emitter  # noqa: E402
from app import r2d2_v2_round_runner as runner  # noqa: E402
from tests.test_r2d2_v2_round_emitter import (MATURITY, NOW, OPENED, RECEIVED, _component, _crash_between_links, _document, _episode, _event,  # noqa: E402
                                              _crash_after_receipt, _known, _rolled_back_identity, _standard, _tape)
from tests.test_r2d2_v2_round_runner import PUBLISHED, _Ticker, _fetch  # noqa: E402


def test_constants_mirror_the_port() -> None:
    assert emitter.EVENT_SCHEMA == sources.EVENT_SCHEMA
    assert emitter.MANIFEST_SHA == sources.MANIFEST_SHA and emitter.SOURCE_AMENDMENT_SHA == sources.AMENDMENT_SHA
    assert emitter.MAX_EVENT_BYTES == sources.MAX_EVENT_BYTES and emitter.MAX_EVENT_FILES == sources.MAX_EVENT_FILES
    assert emitter.EARNINGS_POLICY_SHA == events_module.EARNINGS_AMENDMENT_SHA
    assert emitter._EARNINGS_FIELDS == {"type", "at", "available_at", "session", "instrument_key"} | events_module.EARNINGS_FIELDS
    assert emitter._FAILED_FIELDS == {"type", "at", "available_at", "session", "instrument_key"} | events_module.FAILURE_FIELDS


def test_the_collector_reads_the_published_round_with_zero_diagnostics(tmp_path: Path) -> None:
    document, episodes = _standard()
    document["symbols"]["AAA"]["evidence"]["known_events"].append(_known(_event("2026-09-12", available_at=RECEIVED - timedelta(minutes=1))))  # quarantined
    root = tmp_path / "source"
    summary = emitter.emit_round(document, episodes, root, now=NOW)
    assert summary["published"] == 4 and summary["quarantined"] == 1
    (root / "events" / ".stage-leftover.tmp").write_bytes(b"{}")  # a producer that died mid-staging leaves only hidden files
    os.chmod(root / "events" / ".stage-leftover.tmp", 0o600)
    source = sources.FileShadowSource(root)
    tape = source.events(NOW + timedelta(seconds=1))
    assert source.last_event_diagnostics == [] and len(tape) == 4
    kinds = sorted((event["instrument_key"], event["type"]) for event in tape)
    assert kinds == [("US:AAA", "EARNINGS"), ("US:BBB", "EARNINGS_OBSERVATION_FAILED"), ("US:CCC", "EARNINGS_OBSERVATION_FAILED"),
                     ("US:EEE", "EARNINGS_OBSERVATION_FAILED")]
    for event in tape:
        events_module.validate_observation(event, detected_at=NOW)
        assert event["round_id"] == summary["round_id"] and event["source_id"] == emitter.SOURCE_ID
        assert event["event_id"].startswith(f"earn-2026-09-08-{summary['round_id'][:12]}-")
    earnings = next(event for event in tape if event["type"] == "EARNINGS")
    assert events_module.window_covers(earnings, opened_at=OPENED, maturity_at=MATURITY)
    assert not events_module.window_covers(earnings, opened_at=OPENED, maturity_at=MATURITY + timedelta(days=1))  # the window is exact
    assert events_module.revision_sha256(earnings) == earnings["revision_sha256"]
    assert earnings["envelope_sha256"] in {item["sha256"] for item in json.loads(Path(summary["receipt"]).read_bytes())["published"]}
    # a second reading of the same tape is stable (no EVENT_ID_MUTATED), and the quarantine directory is never scanned
    assert len(source.events(NOW + timedelta(seconds=2))) == 4 and source.last_event_diagnostics == []


def test_the_runner_reads_the_collector_ledger_shape_and_the_collector_reads_the_round(tmp_path: Path) -> None:
    # F385-8 step 2: the inventory comes from records shaped by the port's own ledger (`_record`), the round queries only the
    # live names, and the real collector reads the published round (documents/, rounds/ and quarantine/ present) with zero diagnostics.
    portfolio = pytest.importorskip("app.r2d2_v2_portfolio")
    geometry = {"P": 100.0, "B": 100.1, "C": 100.14004, "S": 95.0, "T": 106.0, "R_unit": 5.0}
    ledger = portfolio.new_portfolio()
    for key, instrument, status in (("ep-a", "NYSE:AAA", "OPEN"), ("ep-b", "NASDAQ:BBB", "OPEN"), ("ep-c", "US:CCC", "CLOSED")):
        record = portfolio._record(episode_key=key, instrument_key=instrument, session="2026-09-01", opened_at=OPENED.isoformat(),
                                   maturity_at=MATURITY.isoformat(), geometry=geometry, arm="ELIGIBLE", quantity=1.0, kind="RESEARCH")
        record["status"] = status
        ledger["research"][key] = record
    state = {"epoch": "R2D2-V2-SHADOW-int", "ledger": ledger, "instrument_episodes": {"US:AAA": ["ep-a"], "US:BBB": ["ep-b"], "US:CCC": ["ep-c"]}}
    episodes = runner.live_episodes_from_state(state)
    assert [episode.instrument_key for episode in episodes] == ["US:AAA", "US:BBB"]
    calendar = [{"code": "AAA.US", "report_date": "2026-09-10", "before_after_market": "AfterMarket"},
                {"code": "AAA.US", "report_date": "2026-09-03", "before_after_market": "BeforeMarket"}]
    ticker = _Ticker(RECEIVED)
    fetch, calls = _fetch(calendar, {"AAA": PUBLISHED}, fail=frozenset({"BBB"}), stamp=lambda: ticker.last)
    root = tmp_path / "source"
    result = runner.run_round(fetch, episodes, root, clock=ticker, inventory_source={"kind": "store", "epoch": "R2D2-V2-SHADOW-int"})
    assert [call[0] for call in calls] == ["/api/calendar/earnings", "/api/fundamentals/AAA.US", "/api/fundamentals/BBB.US"]
    assert result["published"] == 3 and result["quarantined"] == 0
    source = sources.FileShadowSource(root)
    tape = source.events(NOW + timedelta(seconds=1))
    assert source.last_event_diagnostics == [] and len(tape) == 3
    for event in tape:
        events_module.validate_observation(event, detected_at=NOW + timedelta(seconds=1))
        assert event["round_id"] == result["round_id"] and event["source_id"] == emitter.SOURCE_ID
        episode = next(item for item in episodes if item.instrument_key == event["instrument_key"])
        assert events_module.window_covers(event, opened_at=episode.opened_at, maturity_at=episode.maturity_at)
    dates = sorted(event["event_date"] for event in tape if event["type"] == "EARNINGS")
    assert dates == ["2026-09-03", "2026-09-10"]  # the pre-session fact reaches the collector (C-F385-8-1)
    assert [event["reason"] for event in tape if event["type"] == "EARNINGS_OBSERVATION_FAILED"] == ["EARNINGS_SOURCE_UNAVAILABLE"]
    assert (root / "documents").is_dir() and (root / "rounds").is_dir()  # present beside the tape and never read as events


def test_an_invalid_file_in_the_tape_would_discard_it_which_is_why_validation_precedes_publication(tmp_path: Path) -> None:
    document, episodes = _standard()
    root = tmp_path / "source"
    emitter.emit_round(document, episodes, root, now=NOW)
    bad = root / "events" / "earn-bad.0000000000000000000000000000000000000000000000000000000000000000.json"
    bad.write_bytes(b'{"schema": "V2_SHADOW_SOURCE_EVENT_V2"}')
    os.chmod(bad, 0o600)
    source = sources.FileShadowSource(root)
    assert source.events(NOW + timedelta(seconds=1)) == [] and source.last_event_diagnostics  # the collector drops the whole tape


def test_a_crashed_round_is_never_consumed_partially_and_recovery_makes_it_whole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # F385-8-A against the real reader: between links the tape carries the guard -> zero events and a diagnostic (never 1 of 4).
    document, episodes = _standard()
    root = tmp_path / "source"
    real_link = os.link
    calls = {"n": 0}

    def failing(src, dst, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated crash between links")
        return real_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "link", failing)
    with pytest.raises(OSError):
        emitter.emit_round(document, episodes, root, now=NOW)
    monkeypatch.setattr(os, "link", real_link)
    source = sources.FileShadowSource(root)
    assert source.events(NOW + timedelta(seconds=1)) == [] and source.last_event_diagnostics  # refused as a whole, with a diagnostic
    outcomes = emitter.recover_rounds(root, now=NOW + timedelta(minutes=1))
    assert [outcome["commit"] for outcome in outcomes] == ["recovered"]
    tape = source.events(NOW + timedelta(minutes=2))
    assert source.last_event_diagnostics == [] and len(tape) == 4


def test_capacity_reservation_matches_the_real_reader_at_the_peak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # F385-8-C against the real reader: with both limits lowered to the same value, a round the emitter accepts never
    # trips the reader's EVENT_FILE_LIMIT at any instant, and a round it refuses would have.
    document, episodes = _standard()
    root = tmp_path / "source"
    emitter.emit_round(document, episodes, root, now=NOW)
    emitter.emit_round(document, episodes, root, now=NOW + timedelta(minutes=1))  # 8 files
    source = sources.FileShadowSource(root)
    for limit in (13, 16):  # 8 + 2*4 + 1 = 17 entries at the peak of a third round
        monkeypatch.setattr(emitter, "MAX_EVENT_FILES", limit)
        monkeypatch.setattr(sources, "MAX_EVENT_FILES", limit)
        with pytest.raises(emitter.RoundEmitterError, match="EVENT_FILE_LIMIT"):
            emitter.emit_round(document, episodes, root, now=NOW + timedelta(minutes=2))
        assert len(source.events(NOW + timedelta(minutes=3))) == 8 and source.last_event_diagnostics == []
    monkeypatch.setattr(emitter, "MAX_EVENT_FILES", 17)
    monkeypatch.setattr(sources, "MAX_EVENT_FILES", 17)
    seen_counts: list[int] = []
    real_link = os.link

    def observing_link(src, dst, *args, **kwargs):  # the reader polls between two links: it must never trip the limit
        real_link(src, dst, *args, **kwargs)
        seen_counts.append(len(os.listdir(root / "events")))
        source.events(NOW + timedelta(minutes=3))
        assert source.last_event_diagnostics == [{"code": "ENVELOPE_FIELDS"}] or source.last_event_diagnostics[0]["code"] != "EVENT_FILE_LIMIT"

    monkeypatch.setattr(os, "link", observing_link)
    third = emitter.emit_round(document, episodes, root, now=NOW + timedelta(minutes=2))
    monkeypatch.setattr(os, "link", real_link)
    assert third["new_files"] == 4 and max(seen_counts) <= 17
    assert len(source.events(NOW + timedelta(minutes=4))) == 12 and source.last_event_diagnostics == []


def test_a_closed_identity_retry_never_leaves_a_silent_subset_for_the_reader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # F385-8 A-R3 against the real reader: rollback -> retry of the same identity -> crash on the second link -> recovery.
    # The reader sees zero events with a diagnostic (guard) or zero events clean (rollback), never 1 of 4 with zero diagnostics.
    document, episodes = _standard()
    root = tmp_path / "source"
    retained, before = _rolled_back_identity(root, monkeypatch, document, episodes)
    source = sources.FileShadowSource(root)
    assert source.events(NOW + timedelta(minutes=1)) == [] and source.last_event_diagnostics == []  # clean empty tape after rollback
    with pytest.raises(emitter.RoundEmitterError, match="ROUND_IDENTITY_CLOSED"):
        emitter.emit_round(document, episodes, root, now=NOW)  # the refusal, before the tape is touched
    assert source.events(NOW + timedelta(minutes=2)) == [] and source.last_event_diagnostics == []
    original = emitter._retained_commit
    monkeypatch.setattr(emitter, "_retained_commit", lambda rounds_dir, receipt: None)  # bypass the refusal on purpose
    real_link = _crash_between_links(monkeypatch, at_call=2)
    with pytest.raises(OSError):
        emitter.emit_round(document, episodes, root, now=NOW)
    monkeypatch.setattr(os, "link", real_link)
    monkeypatch.setattr(emitter, "_retained_commit", original)
    assert len(_tape(root)["final"]) == 1
    assert source.events(NOW + timedelta(minutes=3)) == [] and source.last_event_diagnostics  # guard: refused as a whole
    outcomes = emitter.recover_rounds(root, now=NOW + timedelta(minutes=4))
    assert outcomes[0]["commit"] == "rolled_back"
    assert source.events(NOW + timedelta(minutes=5)) == [] and source.last_event_diagnostics == []  # zero and clean, never a subset
    assert retained.read_bytes() == before


def test_an_unverifiable_final_never_blocks_the_reader_forever(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # F385-8 A-R4 against the real reader: complete round + journal (crash before the journal was removed), then a final grown
    # past the per-file limit. Before recovery the reader refuses the whole tape (SOURCE_SIZE_LIMIT); recovery must dispose of
    # it — zero events, clean, twice — the closed identity is refused, and the exit (a new instant) is read clean.
    document, episodes = _standard()
    root = tmp_path / "source"
    real_retain = _crash_after_receipt(monkeypatch)
    with pytest.raises(OSError):
        emitter.emit_round(document, episodes, root, now=NOW)
    monkeypatch.setattr(emitter, "_retain", real_retain)
    source = sources.FileShadowSource(root)
    assert len(source.events(NOW + timedelta(minutes=1))) == 4 and source.last_event_diagnostics == []  # the complete round reads fine
    journal = json.loads((root / "rounds" / emitter.pending_rounds(root)[0]).read_bytes())
    victim = root / "events" / journal["files"][0]["name"]
    victim.write_bytes(victim.read_bytes() + b" " * emitter.MAX_EVENT_BYTES)
    assert source.events(NOW + timedelta(minutes=2)) == [] and any(d["code"] == "SOURCE_SIZE_LIMIT" for d in source.last_event_diagnostics)
    outcomes = emitter.recover_rounds(root, now=NOW + timedelta(minutes=3))
    assert outcomes[0]["commit"] == "rolled_back" and emitter.recover_rounds(root, now=NOW + timedelta(minutes=4)) == []
    assert source.events(NOW + timedelta(minutes=5)) == [] and source.last_event_diagnostics == []  # zero and clean, twice
    assert source.events(NOW + timedelta(minutes=6)) == [] and source.last_event_diagnostics == []
    with pytest.raises(emitter.RoundEmitterError, match="ROUND_IDENTITY_CLOSED"):
        emitter.emit_round(document, episodes, root, now=NOW)
    fresh = emitter.emit_round(document, episodes, root, now=NOW + timedelta(minutes=7))
    assert fresh["new_files"] == 4 and len(source.events(NOW + timedelta(minutes=8))) == 4 and source.last_event_diagnostics == []


def test_undoing_a_completed_round_never_shows_the_reader_a_clean_subset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # F385-8 A-R5 against the real reader: after the evidence is moved, after a crash at that boundary and between removals the
    # reader sees zero events WITH a diagnostic (the re-armed guard); the resumed recovery ends zero and clean; a new instant reads.
    document, episodes = _standard()
    root = tmp_path / "source"
    real_retain = _crash_after_receipt(monkeypatch)
    with pytest.raises(OSError):
        emitter.emit_round(document, episodes, root, now=NOW)
    monkeypatch.setattr(emitter, "_retain", real_retain)
    journal = json.loads((root / "rounds" / emitter.pending_rounds(root)[0]).read_bytes())
    finals = {item["name"] for item in journal["files"]}
    victim = root / "events" / journal["files"][0]["name"]
    victim.write_bytes(victim.read_bytes() + b" " * emitter.MAX_EVENT_BYTES)
    source = sources.FileShadowSource(root)
    readings: list[tuple[str, int, int]] = []
    real_preserve, real_unlink = emitter._preserve_evidence, emitter._unlink_at

    def observing_preserve(rounds_dir, round_id, events_fd, corrupt):
        real_preserve(rounds_dir, round_id, events_fd, corrupt)
        readings.append(("after_evidence", len(source.events(NOW + timedelta(minutes=2))), len(source.last_event_diagnostics)))
        raise OSError("simulated crash right after the evidence was moved")

    monkeypatch.setattr(emitter, "_preserve_evidence", observing_preserve)
    with pytest.raises(OSError):
        emitter.recover_rounds(root, now=NOW + timedelta(minutes=2))
    monkeypatch.setattr(emitter, "_preserve_evidence", real_preserve)
    readings.append(("after_crash", len(source.events(NOW + timedelta(minutes=3))), len(source.last_event_diagnostics)))

    def observing_unlink(dir_fd, name):
        if name in finals:
            readings.append(("between_removals", len(source.events(NOW + timedelta(minutes=4))), len(source.last_event_diagnostics)))
        real_unlink(dir_fd, name)

    monkeypatch.setattr(emitter, "_unlink_at", observing_unlink)
    outcomes = emitter.recover_rounds(root, now=NOW + timedelta(minutes=5))
    monkeypatch.setattr(emitter, "_unlink_at", real_unlink)
    assert outcomes[0]["commit"] == "rolled_back"
    assert len(readings) == 6 and all(count == 0 and diagnostics > 0 for _, count, diagnostics in readings), readings  # never a clean subset
    assert source.events(NOW + timedelta(minutes=6)) == [] and source.last_event_diagnostics == []
    assert emitter.recover_rounds(root, now=NOW + timedelta(minutes=7)) == []
    fresh = emitter.emit_round(document, episodes, root, now=NOW + timedelta(minutes=8))
    assert fresh["new_files"] == 4 and len(source.events(NOW + timedelta(minutes=9))) == 4 and source.last_event_diagnostics == []

