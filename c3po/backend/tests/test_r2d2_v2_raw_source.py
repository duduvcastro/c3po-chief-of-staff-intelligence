"""Real local files + collector transactions; no live data or provider calls."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json

import pytest

from app import r2d2_v2_raw_source as raw
from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_sources import canonical
from app.r2d2_v2_store import ShadowIntegrityError
from tests.test_r2d2_v2_shadow_counterexamples import setup_state, INSTRUMENT

AT = datetime(2026, 9, 8, 19, 59, 40, tzinfo=timezone.utc)
NOW = AT + timedelta(seconds=5)
PART = "session_date=2026-09-08/feed=quote-part-00001.ndjson"


def line(price=101, *, feed="quote", at=AT, received=None):
    payload = {"s": "SYNTH", "t": int(at.timestamp() * 1000)}
    payload.update({"bp": price, "ap": price} if feed == "quote" else {"p": price})
    return canonical({"schema_version": 1, "provider": "EODHD", "feed": feed,
        "received_at": (received or at).isoformat(), "event_at": at.isoformat(),
        "payload_raw": json.dumps(payload)}) + b"\n"


@pytest.fixture
def source(tmp_path):
    root = tmp_path.resolve() / "source"
    root.mkdir(mode=0o700)
    (root / "events").mkdir(mode=0o700)
    spool = tmp_path.resolve() / "raw"
    (spool / "session_date=2026-09-08").mkdir(parents=True)
    return raw.SpoolShadowSource(root, raw_root=spool, first_session=date(2026, 9, 8), calendar=ShadowCalendar())


def write(source, data, part=PART):
    path = source.raw_root / part
    path.write_bytes(data)
    path.chmod(0o600)
    return path


def test_proposed_cursor_is_replayable_until_commit_and_partial_append_is_retained(source):
    first, second = line(99), line(101)
    path = write(source, first + second[:30])
    cursor = {}
    batch = source.prepare_events(NOW, cursor)
    assert cursor == {} and batch["diagnostics"] == [{"code": "RAW_APPEND_IN_PROGRESS"}]
    assert batch["events"] == []
    assert source.prepare_events(NOW, {}) == batch
    assert batch["cursor"] == {}
    with path.open("ab") as stream:
        stream.write(second[30:])
    rest = source.prepare_events(NOW, batch["cursor"])
    assert not rest["diagnostics"] and [e["bid"] for e in rest["events"]] == [99, 101]
    assert rest["events"][1]["sequence"] == 1


def test_restart_append_to_older_part_is_not_missed(source):
    first = write(source, line(99))
    write(source, line(100), PART.replace("00001", "00002"))
    batch = source.prepare_events(NOW, {})
    with first.open("ab") as stream:
        stream.write(line(102))
    rebuilt = raw.SpoolShadowSource(source.root, raw_root=source.raw_root,
                                   first_session=source.first_session, calendar=source.calendar)
    rest = rebuilt.prepare_events(NOW, batch["cursor"])
    assert not rest["diagnostics"]
    assert [e["bid"] for e in rest["events"]] == [102]


@pytest.mark.parametrize("mutation,code", [
    ("truncate", "RAW_TRUNCATED_OR_CURSOR_INVALID"),
    ("replace", "RAW_FILE_REPLACED"),
    ("rewrite", "RAW_APPEND_BOUNDARY_CHANGED"),
    ("delete", "RAW_CAPTURE_NOT_OBSERVED"),
])
def test_continuity_failure_never_advances_cursor_or_returns_partial_events(source, mutation, code):
    path = write(source, line())
    cursor = source.prepare_events(NOW, {})["cursor"]
    old = deepcopy(cursor)
    if mutation == "truncate":
        path.write_bytes(b"")
    elif mutation == "replace":
        other = path.with_suffix(".new")
        other.write_bytes(path.read_bytes())
        other.replace(path)
    elif mutation == "rewrite":
        path.write_bytes(path.read_bytes().replace(b'101', b'102'))
    else:
        path.unlink()
    batch = source.prepare_events(NOW, cursor)
    assert batch["diagnostics"] == [{"code": code}]
    assert batch["events"] == [] and batch["cursor"] == old and cursor == old


def test_volume_is_not_a_permanent_refusal_and_joint_feed_is_delivered(source, monkeypatch):
    quote, trade = line(), line(90, feed="trade")
    write(source, quote)
    write(source, trade, PART.replace("quote", "trade"))
    monkeypatch.setattr(raw, "MAX_CYCLE_EVENTS", 1)
    batch = source.prepare_events(NOW, {})
    assert batch["diagnostics"] == []
    assert {event["type"] for event in batch["events"]} == {"QUOTE", "TRADE"}
    assert batch["has_more"] is False


def test_symlink_is_rejected_and_does_not_read_target(source, tmp_path):
    target = tmp_path / "target"
    target.write_bytes(line())
    (source.raw_root / PART).symlink_to(target)
    batch = source.prepare_events(NOW, {})
    assert batch["events"] == [] and batch["diagnostics"]


def seed_collector(source):
    collector, state, _ = setup_state()
    collector.source = source
    for book in ("research", "portfolio"):
        state["ledger"][book]["synthetic-entry"]["maturity_at"] = "2026-09-21T19:55:00+00:00"
    state["coverage_until"][INSTRUMENT] = NOW.isoformat()
    collector.store.atomic(collector.release.epoch, collector._initial(),
                           lambda unused: (state, [], {}), AT - timedelta(seconds=1))
    return collector


def test_real_collector_commits_first_positive_and_cursor_together_then_restarts(source):
    write(source, line(99) + line(101) + line(103))
    collector = seed_collector(source)
    collector.cycle(NOW)
    saved = collector.store.read(collector.release.epoch)
    assert saved["state"]["raw_source_cursor"]["files"][PART]["sequence"] == 3
    for book in ("research", "portfolio"):
        row = saved["state"]["ledger"][book]["synthetic-entry"]
        assert row["exit_cause"] == "EOD_POSITIVE" and row["exit_price"] == 101
        assert row["exit_at"] == AT.isoformat()
        assert row["exit_available_at"] == NOW.isoformat()
    journal = collector.store.journal(collector.release.epoch)
    assert len([r for r in journal if r["payload"]["type"] == "SOURCE_EVENT"]) == 3
    assert len([r for r in journal if r["payload"]["type"] == "SOURCE_CURSOR"]) == 1
    collector.source = raw.SpoolShadowSource(source.root, raw_root=source.raw_root,
        first_session=source.first_session, calendar=source.calendar)
    collector.cycle(NOW + timedelta(seconds=1))
    assert collector.store.read(collector.release.epoch)["state"]["event_receipts"] == saved["state"]["event_receipts"]
    assert collector.store.journal(collector.release.epoch) == journal


def test_failed_commit_does_not_lose_raw_quote_or_cursor(source, monkeypatch):
    write(source, line())
    collector = seed_collector(source)
    before = collector.store.read(collector.release.epoch)
    atomic = collector.store.atomic

    def fail(epoch, initial, transition, now):
        def wrapped(state):
            state, records, response = transition(state)
            assert state["raw_source_cursor"] and any(r["type"] == "SOURCE_CURSOR" for r in records)
            raise RuntimeError("synthetic commit failure")
        return atomic(epoch, initial, wrapped, now)

    monkeypatch.setattr(collector.store, "atomic", fail)
    with pytest.raises(RuntimeError, match="commit failure"):
        collector.cycle(NOW)
    assert collector.store.read(collector.release.epoch) == before
    monkeypatch.setattr(collector.store, "atomic", atomic)
    collector.cycle(NOW)
    saved = collector.store.read(collector.release.epoch)["state"]
    assert saved["raw_source_cursor"] and saved["ledger"]["research"]["synthetic-entry"]["exit_cause"] == "EOD_POSITIVE"


def test_same_snapshot_trade_stop_precedes_quote_across_two_spool_files(source):
    write(source, line(103))
    write(source, line(90, feed="trade", received=AT + timedelta(seconds=1)), PART.replace("quote", "trade"))
    collector = seed_collector(source)
    collector.cycle(NOW)
    saved = collector.store.read(collector.release.epoch)["state"]
    assert all(saved["ledger"][book]["synthetic-entry"]["exit_cause"] == "STOP" for book in ("research", "portfolio"))


def test_concurrent_cursor_change_is_refused(source):
    collector = seed_collector(source)
    state = collector.store.read(collector.release.epoch)["state"]
    state["raw_source_cursor"] = {"files": {"newer": {}}}
    with pytest.raises(ShadowIntegrityError, match="CURSOR_CONCURRENT"):
        collector._cycle_with_cursor(state, {}, [], [], NOW, causal=None, cursor={}, next_cursor={})


def test_partial_trade_does_not_expose_positive_quote_from_other_file(source):
    write(source, line(103))
    write(source, line(90, feed="trade")[:-15], PART.replace("quote", "trade"))
    batch = source.prepare_events(NOW, {})
    assert batch == {"events": [], "diagnostics": [{"code": "RAW_APPEND_IN_PROGRESS"}], "cursor": {}}


def test_raw_receipts_are_bounded_in_epoch_state_and_remain_verified_by_p5(source):
    from app.r2d2_v2_counterfactual_archive import summarize
    from app.r2d2_v2_store import digest
    write(source, line(99) + line(101) + line(103))
    collector = seed_collector(source)
    collector.cycle(NOW)
    saved, journal = collector.store.read_with_journal(collector.release.epoch)
    assert saved['state']['event_receipts'] == {}
    cursor_records = [r for r in journal if r['payload']['type'] == 'SOURCE_CURSOR']
    assert len(cursor_records[0]['payload']['raw_receipts']) == 3
    result = summarize(saved, journal, sessions=['2026-09-08'], cutoff=NOW.isoformat())
    assert result['archive_status'] == 'VERIFIED' and result['archive_record_count'] == 3
    changed = deepcopy(saved)
    changed['state']['raw_source_cursor']['files'][PART]['sequence'] += 1
    changed['state_sha'] = digest(changed['state'])
    with pytest.raises(ShadowIntegrityError, match='RAW_CURSOR_HEAD'):
        summarize(changed, journal, sessions=['2026-09-08'], cutoff=NOW.isoformat())


def test_failed_source_leaves_durable_cursor_unchanged(source):
    write(source, line(99))
    collector = seed_collector(source)
    collector.cycle(NOW)
    before = collector.store.read(collector.release.epoch)['state']['raw_source_cursor']
    with (source.raw_root / PART).open('ab') as stream:
        stream.write(b'partial')
    collector.cycle(NOW + timedelta(seconds=1))
    after = collector.store.read(collector.release.epoch)['state']
    assert after['raw_source_cursor'] == before
    assert not after['data_issues']


@pytest.mark.parametrize('mode', ['CERTIFIED', 'DIAGNOSTIC'])
def test_worker_binds_existing_spool_only_for_certified_without_starting_capture(tmp_path, monkeypatch, mode):
    from hashlib import sha256
    from types import SimpleNamespace
    from app import database, r2d2_v2_shadow_worker as worker
    from tests.test_r2d2_v2_store_worker import release_body, BUILD, NOW as APPROVED_NOW

    class NoDatabaseIO:
        def __init__(self, settings):
            pass
        def connection(self):
            pytest.fail('Construction must not query the database')
        def initialize(self):
            pytest.fail('Construction must not migrate')

    monkeypatch.setattr(database, 'Database', NoDatabaseIO)
    data = canonical(release_body(mode))
    release = tmp_path / 'release.json'
    release.write_bytes(data)
    release.chmod(0o600)
    settings = SimpleNamespace(r2d2_v2_shadow_enabled=True, database_url='synthetic-only',
        r2d2_v2_shadow_release_file=str(release), r2d2_v2_shadow_release_sha=sha256(data).hexdigest(),
        build_sha=BUILD, r2d2_v2_shadow_source_dir=tmp_path / 'source',
        r2d2_microstructure_raw_dir=tmp_path / 'existing-raw')
    collector = worker.build_collector(settings, now=APPROVED_NOW)
    assert isinstance(collector.source, raw.SpoolShadowSource) is (mode == 'CERTIFIED')
    assert not settings.r2d2_microstructure_raw_dir.exists()
    assert not settings.r2d2_v2_shadow_source_dir.exists()


@pytest.mark.parametrize("append", [False, True])
def test_boundary_rewrite_during_short_read_never_reseals_changed_history(source, monkeypatch, append):
    # A large witness makes even one valid new record a short read; the empty
    # read exercises the normal idle poll. Rewrite after the first witness check.
    monkeypatch.setattr(raw, "WITNESS_BYTES", 1024)
    original = line(101)
    path = write(source, original)
    cursor = source.prepare_events(NOW, {})["cursor"]
    suffix = line(103) if append else b""
    with path.open("ab") as stream:
        stream.write(suffix)
    pread = raw.os.pread
    changed = False

    def racing_read(fd, size, offset):
        nonlocal changed
        data = pread(fd, size, offset)
        if (offset == len(original) or not append) and not changed:
            changed = True
            path.write_bytes(original.replace(b"101", b"102") + suffix)
        return data

    monkeypatch.setattr(raw.os, "pread", racing_read)
    batch = source.prepare_events(NOW, cursor)
    assert changed
    assert batch["diagnostics"] == [{"code": "RAW_CHANGED_DURING_READ"}]
    assert batch["events"] == [] and batch["cursor"] == cursor


def test_partial_append_defers_then_recovers_without_a_global_gap(source):
    path = write(source, line(99))
    collector = seed_collector(source)
    collector.cycle(NOW)
    before = collector.store.read(collector.release.epoch)["state"]
    final = line(101, at=AT + timedelta(seconds=1))
    with path.open("ab") as output:
        output.write(final[:-20])
    result = collector.cycle(NOW + timedelta(seconds=1))
    after = collector.store.read(collector.release.epoch)["state"]
    assert result["raw_poll_deferred"] == ["RAW_APPEND_IN_PROGRESS"]
    assert after == before
    with path.open("ab") as output:
        output.write(final[-20:])
    collector.cycle(NOW + timedelta(seconds=2))
    after = collector.store.read(collector.release.epoch)["state"]
    assert collector._admission_block(after, "2026-09-08", INSTRUMENT) is None
    assert after["ledger"]["research"]["synthetic-entry"]["exit_cause"] == "EOD_POSITIVE"


def test_preopen_drains_existing_raw_without_opening_a_session(source):
    at = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
    write(source, line(99, at=at))
    collector, state, _ = setup_state(position=False)
    state = collector._initial()
    collector.source = source
    collector.store.atomic(collector.release.epoch, collector._initial(),
                           lambda unused: (state, [], {}), at-timedelta(hours=1))
    collector.cycle(at+timedelta(minutes=30))
    saved = collector.store.read(collector.release.epoch)["state"]
    assert saved["raw_source_cursor"]["files"][PART]["offset"] == len(line(99, at=at))
    assert saved["sessions"] == {} and saved["ledger"]["session"] is None
    assert any(r["payload"]["type"] == "SOURCE_EVENT" for r in collector.store.journal(collector.release.epoch))


@pytest.mark.parametrize("bad", [b'{not json}\n', canonical({"schema_version": 1, "provider": "EODHD", "feed": "quote",
    "received_at": AT.isoformat(), "event_at": AT.isoformat(), "payload_raw": '{"status":"connected"}'})+b"\n",
    line().replace(b'101', b'null'), b'x'*70000+b'\n'])
def test_bad_frame_is_receipted_and_following_tick_is_committed(source, bad):
    from hashlib import sha256
    write(source, line(99) + bad + line(101))
    collector = seed_collector(source)
    collector.cycle(NOW)
    state, journal = collector.store.read_with_journal(collector.release.epoch)
    assert state['state']['data_issues'] == []
    cursor = state['state']['raw_source_cursor']['files'][PART]
    assert cursor['sequence'] == 2 and cursor['offset'] == len(line(99)+bad+line(101))
    receipt = [r['payload'] for r in journal if r['payload']['type']=='SOURCE_CURSOR'][0]
    skipped = receipt['skipped_receipts']
    assert len(skipped)==1 and skipped[0]['offset']==len(line(99))
    assert skipped[0]['raw_sha256']==sha256(bad).hexdigest()
    assert skipped[0]['disposition'] in {'QUARANTINED', 'SKIPPED'}
    if b'connected' in bad:
        assert skipped[0]['code']=='RAW_NON_TICK'
    assert all(state['state']['ledger'][book]['synthetic-entry']['exit_cause']=='EOD_POSITIVE'
               for book in ('research','portfolio'))
    collector.cycle(NOW)
    assert collector.store.journal(collector.release.epoch)==journal


def pages(source, monkeypatch, budget):
    monkeypatch.setattr(raw, 'MAX_CYCLE_EVENTS', budget)
    cursor = {}; result=[]; snapshot=None
    for _ in range(100):
        page = source.prepare_events(NOW, cursor, snapshot=snapshot)
        assert not page['diagnostics']
        assert page['cursor'] != cursor
        result.append(page);cursor=page['cursor'];snapshot=page['snapshot']
        if not page['has_more']: return result
    pytest.fail('Pagination did not converge')


def test_common_cut_includes_stop_at_w_and_defers_stop_after_w(source, monkeypatch):
    write(source, line(103) + line(103, at=AT+timedelta(seconds=2)))
    tradepart=PART.replace('quote','trade')
    write(source, line(90, feed='trade')+line(90, feed='trade', received=AT+timedelta(seconds=1)),tradepart)
    rows=pages(source,monkeypatch,2)
    assert rows[0]['page']['cutoff_received_at']==AT.isoformat()
    assert [e['type'] for e in rows[0]['events']]==['QUOTE','TRADE']
    assert len(rows[1]['events'])==2
    collector=seed_collector(source)
    monkeypatch.setattr(raw,'MAX_DRAIN_SECONDS',10)
    from itertools import count
    clock_ticks=count()
    collector.clock=lambda: NOW+timedelta(microseconds=next(clock_ticks))
    result=collector.cycle()
    assert result['raw_pages']==2 and not result['raw_backlog_pending']
    events=[r['payload']['source'] for r in collector.store.journal(collector.release.epoch)
            if r['payload']['type']=='SOURCE_EVENT']
    assert [e['type'] for e in events[:2]]==['TRADE','QUOTE']
    state=collector.store.read(collector.release.epoch)['state']
    assert all(state['ledger'][b]['synthetic-entry']['exit_cause']=='STOP' for b in ('research','portfolio'))


def test_tied_reception_group_is_not_split_even_past_page_target(source, monkeypatch):
    write(source,b''.join(line(99) for _ in range(5)))
    write(source,line(90,feed='trade'),PART.replace('quote','trade'))
    result=pages(source,monkeypatch,2)
    assert len(result)==1 and len(result[0]['events'])==6
    assert result[0]['page']['target_exceeded'] is True


def test_three_budgets_converge_in_three_pages_with_monotone_balanced_feeds(source,monkeypatch):
    write(source,b''.join(line(99,at=AT+timedelta(milliseconds=i)) for i in range(6)))
    write(source,b''.join(line(99,feed='trade',at=AT+timedelta(milliseconds=i)) for i in range(6)),
          PART.replace('quote','trade'))
    result=pages(source,monkeypatch,4)
    assert len(result)==3 and [p['page']['record_count'] for p in result]==[4,4,4]


def test_page_discard_and_restart_reread_identical_bytes_and_cursor_bounds(source,monkeypatch):
    rows=[line(99,at=AT+timedelta(milliseconds=i)) for i in range(6)]
    write(source,b''.join(rows));monkeypatch.setattr(raw,'MAX_CYCLE_EVENTS',2)
    first=source.prepare_events(NOW,{})
    assert first==source.prepare_events(NOW,{})
    assert first['cursor']['files'][PART]['offset']==sum(map(len,rows[:2]))
    cursor=first['cursor']
    next_page=source.prepare_events(NOW,cursor,snapshot=first['snapshot'])
    rebuilt=raw.SpoolShadowSource(source.root,raw_root=source.raw_root,
                                  first_session=source.first_session,calendar=source.calendar)
    assert rebuilt.prepare_events(NOW,cursor)==next_page
    assert next_page['cursor']['files'][PART]['offset']==sum(map(len,rows[:4]))


def test_reception_regression_is_counted_without_global_gap(source,monkeypatch):
    write(source,line(99,received=AT+timedelta(seconds=2))+line(99)+line(101,received=AT+timedelta(seconds=3)))
    monkeypatch.setattr(raw,'MAX_CYCLE_EVENTS',1);monkeypatch.setattr(raw,'MAX_DRAIN_SECONDS',10)
    collector=seed_collector(source)
    from itertools import count
    ticks=count()
    collector.clock=lambda: NOW+timedelta(microseconds=next(ticks))
    collector.cycle()
    saved,journal=collector.store.read_with_journal(collector.release.epoch)
    assert saved['state']['data_issues']==[]
    cursors=[r['payload'] for r in journal if r['payload']['type']=='SOURCE_CURSOR']
    assert sum(r['page']['diagnostic_counts'].get('RAW_RECEIVED_AT_DECREASED',0) for r in cursors)==1
    assert saved['state']['raw_source_cursor']['files'][PART]['received_max']==(AT+timedelta(seconds=3)).isoformat()


def test_one_cycle_keeps_joint_snapshot_while_appends_wait_for_next_cycle(source,monkeypatch):
    rows=[line(99,at=AT+timedelta(milliseconds=i)) for i in range(4)]
    path=write(source,b''.join(rows));monkeypatch.setattr(raw,'MAX_CYCLE_EVENTS',2)
    first=source.prepare_events(NOW,{})
    with path.open('ab') as stream:stream.write(line(103))
    second=source.prepare_events(NOW,first['cursor'],snapshot=first['snapshot'])
    assert not second['has_more'] and len(second['events'])==2
    following=source.prepare_events(NOW,second['cursor'])
    assert len(following['events'])==1


def test_frozen_clock_defers_next_page_without_fabricating_observation_time(source,monkeypatch):
    write(source,line(103)+line(103,at=AT+timedelta(seconds=2)))
    write(source,line(90,feed='trade',received=AT+timedelta(seconds=1)),PART.replace('quote','trade'))
    monkeypatch.setattr(raw,'MAX_CYCLE_EVENTS',2);monkeypatch.setattr(raw,'MAX_DRAIN_SECONDS',10)
    collector=seed_collector(source)
    result=collector.cycle(NOW)
    assert result['raw_backlog_pending'] and result['raw_pages']==1
    assert result['raw_drain_deferred']=='COLLECTOR_CLOCK_NOT_ADVANCED'
    assert collector.store.read(collector.release.epoch)['state']['last_cycle_at']==NOW.isoformat()
    collector.cycle(NOW+timedelta(seconds=1))
    state=collector.store.read(collector.release.epoch)['state']
    assert state['raw_source_cursor']['files'][PART.replace('quote','trade')]['sequence']==1


def test_equivalence_preopen_ordered_backlog_same_events_and_full_state_hash(source,monkeypatch):
    from app.r2d2_v2_store import digest
    at=AT.replace(hour=12,minute=0,second=0)
    observed=at+timedelta(minutes=30)
    write(source,b''.join(line(99,at=at+timedelta(milliseconds=i)) for i in range(12)))
    outcomes=[]
    for budget in (1,3,7,16384):
        monkeypatch.setattr(raw,'MAX_CYCLE_EVENTS',budget)
        collector,_,_=setup_state(position=False);collector.source=source
        initial=collector._initial();cursor={};snapshot=None;first=True
        while True:
            batch=source.prepare_events(observed,cursor,snapshot=snapshot)
            assert not batch['diagnostics']
            collector.store.atomic(collector.release.epoch,initial,
                lambda state:collector._cycle_with_cursor(state,None,batch['events'],[],observed,
                    causal=None,cursor=cursor,next_cursor=batch['cursor'],raw_receipts=batch['raw_receipts'],
                    skipped_receipts=batch['skipped_receipts'],raw_page=batch['page'],continuation=not first),observed)
            first=False;cursor=batch['cursor'];snapshot=batch['snapshot']
            if not batch['has_more']:break
        saved,journal=collector.store.read_with_journal(collector.release.epoch)
        events=[r['payload']['source'] for r in journal if r['payload']['type']=='SOURCE_EVENT']
        outcomes.append((digest(events),saved['state_sha']))
    assert len(set(outcomes))==1


def test_design_counterexample_late_trade_prevents_unrestricted_snapshot_equivalence(source,monkeypatch):
    # This PASS proves a contradiction in the requested universal equivalence;
    # it is explicitly NOT a passing equivalence certification.
    write(source,line(103)+line(103,at=AT+timedelta(seconds=2)))
    write(source,line(90,feed='trade',received=AT+timedelta(seconds=1)),PART.replace('quote','trade'))
    from app.r2d2_v2_store import digest
    def ordered(batch):
        return sorted(batch['events'],key=lambda e:(e['at'],3 if e['type']=='TRADE' else 4,
                      e['available_at'],e['source_id'],e['sequence'],e['event_id']))
    full=pages(source,monkeypatch,16384)
    paged=pages(source,monkeypatch,2)
    full_sequence=[e['type'] for p in full for e in ordered(p)]
    page_sequence=[e['type'] for p in paged for e in ordered(p)]
    assert full_sequence==['TRADE','QUOTE','QUOTE']
    assert page_sequence==['QUOTE','TRADE','QUOTE']
    assert digest(full_sequence)!=digest(page_sequence)
    # Real collector outcome also differs, with actual observation clocks
    # advancing between pages. No timestamp is backdated to the cutoff W.
    from itertools import count
    outcomes=[]
    for budget in (16384,2):
        monkeypatch.setattr(raw,'MAX_CYCLE_EVENTS',budget)
        monkeypatch.setattr(raw,'MAX_DRAIN_SECONDS',10)
        collector=seed_collector(source);ticks=count()
        collector.clock=lambda:NOW+timedelta(microseconds=next(ticks))
        collector.cycle()
        saved=collector.store.read(collector.release.epoch)
        outcomes.append(saved['state_sha'])
    assert outcomes[0]!=outcomes[1]


def test_design_counterexample_fixed_per_file_shares_can_need_more_than_three_pages(source,monkeypatch):
    # Three times a budget of two: five early quotes + one late trade. The
    # design's fixed per-file share admits one quote per early page, not two.
    write(source,b''.join(line(99,at=AT+timedelta(milliseconds=i)) for i in range(5)))
    write(source,line(99,feed='trade',at=AT+timedelta(seconds=4)),PART.replace('quote','trade'))
    result=pages(source,monkeypatch,2)
    assert sum(p['page']['record_count'] for p in result)==6
    assert len(result)==5 and len(result)>3


def test_failed_second_page_commit_is_reread_with_identical_receipts(source,monkeypatch):
    from itertools import count
    write(source,b''.join(line(99,at=AT+timedelta(milliseconds=i)) for i in range(6)))
    monkeypatch.setattr(raw,'MAX_CYCLE_EVENTS',2);monkeypatch.setattr(raw,'MAX_DRAIN_SECONDS',10)
    collector=seed_collector(source);ticks=count()
    collector.clock=lambda:NOW+timedelta(microseconds=next(ticks))
    atomic=collector.store.atomic;attempts=[];failed_page=[]
    prepare=source.prepare_events
    def observed_prepare(*args,**kwargs):
        batch=prepare(*args,**kwargs)
        failed_page.append(deepcopy(batch))
        return batch
    monkeypatch.setattr(source,'prepare_events',observed_prepare)
    def fail_second(epoch,initial,transition,now):
        attempts.append(True)
        if len(attempts)==2:
            def failure(state):
                transition(state)
                raise RuntimeError('second page commit failed')
            return atomic(epoch,initial,failure,now)
        return atomic(epoch,initial,transition,now)
    monkeypatch.setattr(collector.store,'atomic',fail_second)
    with pytest.raises(RuntimeError,match='second page commit failed'):collector.cycle()
    saved=collector.store.read(collector.release.epoch)['state']
    assert saved['raw_source_cursor']['files'][PART]['sequence']==2
    reread=prepare(NOW,saved['raw_source_cursor'])
    assert reread==failed_page[-1]
    monkeypatch.setattr(collector.store,'atomic',atomic)
    collector.cycle()
    assert collector.store.read(collector.release.epoch)['state']['raw_source_cursor']['files'][PART]['sequence']==6
    events=[r['payload']['source']['event_id'] for r in collector.store.journal(collector.release.epoch)
            if r['payload']['type']=='SOURCE_EVENT']
    assert len(events)==len(set(events))==6


def test_page_cap_leaves_durable_backlog_for_next_cycle(source,monkeypatch):
    from itertools import count
    write(source,b''.join(line(99,at=AT+timedelta(milliseconds=i)) for i in range(6)))
    monkeypatch.setattr(raw,'MAX_CYCLE_EVENTS',2);monkeypatch.setattr(raw,'MAX_PAGES_PER_CYCLE',2)
    monkeypatch.setattr(raw,'MAX_DRAIN_SECONDS',10)
    collector=seed_collector(source);ticks=count()
    collector.clock=lambda:NOW+timedelta(microseconds=next(ticks))
    result=collector.cycle()
    assert result['raw_pages']==2 and result['raw_backlog_pending']
    assert collector.store.read(collector.release.epoch)['state']['raw_source_cursor']['files'][PART]['sequence']==4
    result=collector.cycle()
    assert result['raw_pages']==1 and not result['raw_backlog_pending']


def test_actual_16384_budget_balanced_three_page_backlog(source,monkeypatch):
    budget=16384
    write(source,b''.join(line(99,received=AT+timedelta(microseconds=i)) for i in range(3*budget//2)))
    write(source,b''.join(line(99,feed='trade',received=AT+timedelta(microseconds=i)) for i in range(3*budget//2)),
          PART.replace('quote','trade'))
    result=pages(source,monkeypatch,budget)
    assert len(result)==3 and [p['page']['record_count'] for p in result]==[budget]*3
    assert [len(p['events']) for p in result]==[budget]*3
    assert all(not p['skipped_receipts'] for p in result)



def test_regressed_reception_after_restart_uses_cursor_maximum(source):
    path=write(source,line(99,received=AT+timedelta(seconds=2)))
    collector=seed_collector(source);collector.cycle(NOW)
    with path.open('ab') as stream:stream.write(line(101))
    collector.source=raw.SpoolShadowSource(source.root,raw_root=source.raw_root,
        first_session=source.first_session,calendar=source.calendar)
    collector.cycle(NOW+timedelta(seconds=1))
    saved,journal=collector.store.read_with_journal(collector.release.epoch)
    assert saved['state']['data_issues']==[]
    cursor_rows=[r['payload'] for r in journal if r['payload']['type']=='SOURCE_CURSOR']
    assert cursor_rows[-1]['page']['diagnostic_counts']=={'RAW_RECEIVED_AT_DECREASED':1}
    assert saved['state']['raw_source_cursor']['files'][PART]['received_max']==(AT+timedelta(seconds=2)).isoformat()


def test_partial_later_page_keeps_prior_commits_and_reports_backlog(source,monkeypatch):
    from itertools import count
    write(source,b''.join(line(99,at=AT+timedelta(milliseconds=i)) for i in range(6))+b'partial')
    monkeypatch.setattr(raw,'MAX_CYCLE_EVENTS',2);monkeypatch.setattr(raw,'MAX_DRAIN_SECONDS',10)
    collector=seed_collector(source);ticks=count()
    collector.clock=lambda:NOW+timedelta(microseconds=next(ticks))
    result=collector.cycle()
    assert result['raw_poll_deferred']==['RAW_APPEND_IN_PROGRESS']
    assert result['raw_backlog_pending'] is True
    state=collector.store.read(collector.release.epoch)['state']
    assert state['raw_source_cursor']['files'][PART]['sequence']==4
    assert state['data_issues']==[]


@pytest.mark.parametrize('budget',[1,2,3,7])
def test_reception_prefix_closure_and_equivalent_cut_snapshot_schedule(source,monkeypatch,budget):
    # Independent prefix oracle: use original receipt timestamps/byte lengths,
    # not the reader's selected events, to form the comparison snapshots.
    frames={PART:[line(99,received=AT+timedelta(milliseconds=i)) for i in (0,2,4,7)],
        PART.replace('quote','trade'):[line(90,feed='trade',received=AT+timedelta(milliseconds=i)) for i in (0,1,4,8)]}
    for path,rows in frames.items():write(source,b''.join(rows),path)
    batches=pages(source,monkeypatch,budget)
    previous={};snapshot_cursor={};cut_before=None
    collectors=[seed_collector(source),seed_collector(source)]
    for page_index,batch in enumerate(batches):
        cutoff=batch['page']['cutoff_received_at']
        if cutoff is not None:
            cut=datetime.fromisoformat(cutoff)
            if cut_before is not None:assert cut>cut_before
            cut_before=cut
        snapshot=deepcopy(batch['snapshot'])
        for path,rows in frames.items():
            expected=sum(len(row) for row in rows if cutoff is None or
                datetime.fromisoformat(json.loads(row)['received_at'])<=datetime.fromisoformat(cutoff))
            assert batch['cursor']['files'][path]['offset']==expected
            assert expected>=previous.get(path,0)
            previous[path]=expected
            snapshot[path]['size']=expected
        assert all(cutoff is None or datetime.fromisoformat(event['source_at'])<=datetime.fromisoformat(cutoff)
                   for event in batch['events'])
        # A full snapshot with exactly these cut sizes must return byte-for-byte
        # identical envelopes and cursor. Late trade clocks are left unchanged.
        monkeypatch.setattr(raw,'MAX_CYCLE_EVENTS',16384)
        equivalent=source.prepare_events(NOW,snapshot_cursor,snapshot=snapshot)
        assert not equivalent['diagnostics']
        assert equivalent['events']==batch['events']
        assert equivalent['raw_receipts']==batch['raw_receipts']
        assert equivalent['cursor']==batch['cursor']
        for collector,offered in zip(collectors,(batch,equivalent)):
            observed=NOW+timedelta(microseconds=page_index+1)
            before=collector.store.read(collector.release.epoch)['state'].get('raw_source_cursor',{})
            collector.store.atomic(collector.release.epoch,collector._initial(),
                lambda state:collector._cycle_with_cursor(state,None,offered['events'],[],observed,
                    causal=None,cursor=before,next_cursor=offered['cursor'],
                    raw_receipts=offered['raw_receipts'],skipped_receipts=offered['skipped_receipts'],
                    raw_page=offered['page'],continuation=page_index>0),observed)
        snapshot_cursor=equivalent['cursor']
    assert collectors[0].store.read(collectors[0].release.epoch)['state_sha']==collectors[1].store.read(collectors[1].release.epoch)['state_sha']


@pytest.mark.parametrize('counts,budget',[( (5,1),2),((13,2,7),4),((1,1,1),1),((9,),3)])
def test_monotonic_progress_and_qualified_convergence_bound(source,monkeypatch,counts,budget):
    from math import ceil
    paths=[]
    for index,count in enumerate(counts):
        path=PART.replace('00001',f'{index+1:05d}');paths.append(path)
        write(source,b''.join(line(99,received=AT+timedelta(milliseconds=index*50+i)) for i in range(count)),path)
    batches=pages(source,monkeypatch,budget)
    share=max(1,budget//len(counts));bound=sum(ceil(count/share) for count in counts)
    assert len(batches)<=bound
    assert sum(page['page']['record_count'] for page in batches)==sum(counts)
    last={path:0 for path in paths}
    for page in batches:
        assert page['page']['record_count']>=1
        current={path:page['cursor']['files'][path]['offset'] for path in paths}
        assert all(current[path]>=last[path] for path in paths)
        assert any(current[path]>last[path] for path in paths)
        last=current
    assert not batches[-1]['has_more']


def test_tied_reception_group_is_complete_and_target_exceeded_is_counted(source,monkeypatch):
    write(source,b''.join(line(99) for _ in range(4))+line(99,received=AT+timedelta(seconds=1)))
    write(source,line(90,feed='trade')+line(99,feed='trade',received=AT+timedelta(seconds=1)),
          PART.replace('quote','trade'))
    batches=pages(source,monkeypatch,2)
    assert [b['page']['record_count'] for b in batches]==[5,2]
    assert sum(b['page']['target_exceeded'] for b in batches)==1
    assert {event['source_at'] for event in batches[0]['events']}=={AT.isoformat()}
