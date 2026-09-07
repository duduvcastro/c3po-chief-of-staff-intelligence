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
from tests.test_r2d2_v2_round_emitter import MATURITY, NOW, OPENED, RECEIVED, _component, _document, _episode, _event, _known, _standard  # noqa: E402
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
