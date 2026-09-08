"""Independent E3 live-contract probes; no DB/provider/service instances."""
from copy import deepcopy
from datetime import datetime
import json
import pytest

from app.r2d2_v2_earnings_events import EARNINGS_AMENDMENT_SHA, revision_sha256, validate_observation
from app.r2d2_v2_earnings_policy import EarningsPolicyError
from app.r2d2_v2_portfolio import (SELL_FACTOR, apply_event, new_portfolio, register_candidate,
    earnings_observation_counts, export_session_statistics)
from app.r2d2_v2_sources import _validate_event, SourceUnavailable

SESSION = '2026-09-08'
OPEN = '2026-09-08T14:00:00+00:00'
MATURITY = '2026-09-21T19:55:00+00:00'
DETECTED = '2026-09-08T22:00:05+00:00'

def utc(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))

def admission():
    buy, stop = 100 * 1.001, 97.0
    cost = buy * 1.0004
    risk = cost - stop * SELL_FACTOR
    return register_candidate(new_portfolio(), episode_key='synthetic-eligible', instrument_key='US:SYNTH',
        arm='ELIGIBLE', session=SESSION, opened_at=OPEN, maturity_at=MATURITY,
        geometry={'P': 100.0, 'B': buy, 'C': cost, 'S': stop,
                  'T': (cost + risk) / SELL_FACTOR, 'R_unit': risk})[0]

def observation(*, event_id='synthetic-envelope-0', round_char='a', day='2026-09-15',
                granularity='DAY', instant=None, at='2026-09-08T22:00:01+00:00',
                available=DETECTED, failed=False, window=None):
    e = dict(event_id=event_id, type='EARNINGS_OBSERVATION_FAILED' if failed else 'EARNINGS',
        instrument_key='US:SYNTH', session=utc(available).date().isoformat(), at=at, available_at=available,
        round_id=round_char * 64, round_session='2026-09-08', round_received_at='2026-09-08T22:00:00Z',
        observation_window=window or ['2026-09-08', '2026-10-06'], earnings_policy_sha=EARNINGS_AMENDMENT_SHA)
    if failed:
        e['reason'] = 'EARNINGS_SOURCE_UNAVAILABLE'
    else:
        e.update(earnings_event_id='synthetic-announcement', event_date=day, granularity=granularity)
        if granularity == 'INSTANT':
            e['event_at'] = instant
        e['revision_sha256'] = revision_sha256(e)
    return e

def apply(s, e):
    return apply_event(s, e)[0]

def clock(s, kind, session, at):
    return apply(s, dict(event_id=f'clock-{kind}-{session}', type=kind, session=session, at=at, available_at=at))

def quote(*, at, bid_at=None, ask_at=None, available=None, event_id='synthetic-quote'):
    return dict(event_id=event_id, type='QUOTE', instrument_key='US:SYNTH', session=utc(at).date().isoformat(),
        at=at, available_at=available or at, bid=99.9, ask=100.1,
        bid_at=bid_at or at, ask_at=ask_at or at, regular=True)

@pytest.mark.parametrize('granularity', ['DAY', 'BMO', 'AMC'])
@pytest.mark.parametrize('day,intersects', [('2026-09-08', True), ('2026-09-21', True), ('2026-09-22', False)])
def test_coarse_original_episode_boundary(granularity, day, intersects):
    s = apply(admission(), observation(day=day, granularity=granularity))
    r = s['research']['synthetic-eligible']
    assert bool(r['intent']) is intersects and r['maturity_at'] == MATURITY
    assert bool(r['earnings_observations']) is intersects
    if intersects:
        assert r['intent'] == {'cause': 'EVENT', 'at': DETECTED}

@pytest.mark.parametrize('instant,intersects', [('2026-09-08T13:59:59Z', False),
    (OPEN, True), (MATURITY, True), ('2026-09-21T19:55:01Z', False)])
def test_instant_boundary_uses_original_episode_not_detection(instant, intersects):
    s = apply(admission(), observation(day=utc(instant).date().isoformat(), granularity='INSTANT', instant=instant))
    assert bool(s['research']['synthetic-eligible']['intent']) is intersects

def test_each_episode_uses_own_maturity_and_counts_only_research_arm():
    s = clock(admission(), 'SESSION_CLOSE', SESSION, '2026-09-08T20:00:00Z')
    s = clock(s, 'SESSION_OPEN', '2026-09-09', '2026-09-09T13:30:00Z')
    s, _, _ = register_candidate(s, episode_key='synthetic-control', instrument_key='US:SYNTH', arm='CONTROL',
        session='2026-09-09', opened_at='2026-09-09T14:00:00Z', maturity_at='2026-09-22T19:55:00Z',
        geometry=s['research']['synthetic-eligible']['original'])
    e = observation(day='2026-09-22', available='2026-09-09T22:00:05Z', at='2026-09-09T22:00:01Z',
                    window=['2026-09-08', '2026-10-07'])
    s = apply(s, e)
    assert s['research']['synthetic-eligible']['intent'] is None
    assert s['research']['synthetic-control']['intent']['cause'] == 'EVENT'
    counts = earnings_observation_counts(s, '2026-09-09')
    assert counts == {'ELIGIBLE': {'EARNINGS_DETECTED_AFTER_ENTRY': 0, 'EARNINGS_OBSERVATION_FAILED': 0},
                     'CONTROL': {'EARNINGS_DETECTED_AFTER_ENTRY': 1, 'EARNINGS_OBSERVATION_FAILED': 0}}
    assert 'SYNTH' not in json.dumps(counts) and 'episode' not in json.dumps(counts)

def test_strict_quote_clock_after_detection_and_factual_fill():
    # Delayed Friday scheduled round first detected during Tuesday trading.
    detected = '2026-09-08T14:01:05Z'
    e = observation(at='2026-09-08T14:01:01Z', available=detected)
    e.update(round_session='2026-09-04', round_received_at='2026-09-04T22:00:00Z')
    s = apply(admission(), e)
    s = apply(s, quote(at=detected))
    assert s['research']['synthetic-eligible']['status'] == 'OPEN'
    s = apply(s, quote(event_id='synthetic-one-side', at='2026-09-08T14:01:06Z', bid_at=detected))
    assert s['research']['synthetic-eligible']['status'] == 'OPEN'
    s = apply(s, quote(event_id='synthetic-both-after', at='2026-09-08T14:01:07Z'))
    r = s['research']['synthetic-eligible']
    assert r['status'] == 'CLOSED' and r['exit_cause'] == 'EVENT'
    assert r['exit_at'] == '2026-09-08T14:01:07+00:00' and r['category'] == 'time_or_event_exit'

def test_same_revision_round_restart_preserves_first_detection():
    s = apply(admission(), observation())
    first = deepcopy(s['research']['synthetic-eligible']['earnings_observations'])
    s = apply(json.loads(json.dumps(s)), observation(event_id='synthetic-envelope-1', round_char='b',
        at='2026-09-08T22:01:01Z', available='2026-09-08T22:01:05Z'))
    assert s['research']['synthetic-eligible']['earnings_observations'] == first
    assert s['research']['synthetic-eligible']['intent']['at'] == DETECTED
    assert earnings_observation_counts(s, SESSION)['ELIGIBLE']['EARNINGS_DETECTED_AFTER_ENTRY'] == 1

def test_failure_round_is_unknown_not_negative_and_dedupes():
    s = apply(admission(), observation(failed=True))
    r = s['research']['synthetic-eligible']
    assert r['category'] == 'unobservable' and r['order_unknown'] and r['mark'] is None and r['intent'] is None
    assert export_session_statistics(s, SESSION)['data_gate_unknown']
    assert earnings_observation_counts(s, SESSION)['ELIGIBLE']['EARNINGS_OBSERVATION_FAILED'] == 1
    s = apply(s, observation(event_id='synthetic-duplicate-failure', failed=True,
        available='2026-09-08T22:01:05Z', at='2026-09-08T22:01:01Z'))
    assert earnings_observation_counts(s, SESSION)['ELIGIBLE']['EARNINGS_OBSERVATION_FAILED'] == 1

def test_incomplete_live_window_is_failure_not_negative_evidence():
    s = apply(admission(), observation(window=['2026-09-08', '2026-09-30']))
    assert s['research']['synthetic-eligible']['category'] == 'unobservable'
    assert s['research']['synthetic-eligible']['intent'] is None
    assert earnings_observation_counts(s, SESSION)['ELIGIBLE']['EARNINGS_OBSERVATION_FAILED'] == 1

def test_closed_history_is_not_rewritten():
    s = apply(admission(), dict(event_id='synthetic-target', type='TRADE', instrument_key='US:SYNTH',
        session=SESSION, at='2026-09-08T14:00:10Z', available_at='2026-09-08T14:00:10Z', price=110, regular=True))
    before = deepcopy(s['research'])
    s = apply(s, observation())
    s = apply(s, observation(event_id='synthetic-failure', failed=True,
        available='2026-09-08T22:01:05Z', at='2026-09-08T22:01:01Z'))
    assert s['research'] == before
    assert all(n == 0 for arm in earnings_observation_counts(s, SESSION).values() for n in arm.values())

def test_mutated_revision_future_receipt_and_before_target_rejected():
    for field, value in [('event_date', '2026-09-16'), ('round_received_at', '2026-09-08T22:00:06Z'),
                         ('round_received_at', '2026-09-08T21:59:59Z')]:
        e = observation()
        e[field] = value
        with pytest.raises(EarningsPolicyError):
            validate_observation(e, detected_at=utc(DETECTED))

def test_same_instant_different_offset_has_one_semantic_revision():
    first = observation(granularity='INSTANT', instant='2026-09-15T14:00:00Z')
    second = observation(event_id='synthetic-envelope-1', round_char='b', granularity='INSTANT',
        instant='2026-09-15T10:00:00-04:00', at='2026-09-08T22:01:01Z', available='2026-09-08T22:01:05Z')
    s = apply(json.loads(json.dumps(apply(admission(), first))), second)
    assert first['revision_sha256'] == second['revision_sha256']
    assert earnings_observation_counts(s, SESSION)['ELIGIBLE']['EARNINGS_DETECTED_AFTER_ENTRY'] == 1

@pytest.mark.parametrize('granularity,instant', [('DAY', None), ('BMO', None), ('AMC', None),
    ('INSTANT', '2026-09-15T14:00:00Z')])
def test_exact_source_shape_accepts_only_declared_instant(granularity, instant):
    e = observation(granularity=granularity, instant=instant)
    e.pop('event_id')  # ID lives in the outer file envelope.
    _validate_event(e, utc(DETECTED))
    if granularity != 'INSTANT':
        e['event_at'] = None
    else:
        e.pop('event_at')
    with pytest.raises(SourceUnavailable):
        _validate_event(e, utc(DETECTED))


def collector_fixture():
    from datetime import date, timezone
    from app.r2d2_v2_shadow import Release, ShadowCollector
    from app.r2d2_v2_calendar import ShadowCalendar
    from app.r2d2_v2_earnings_package import (EARNINGS_CLOSED_MANIFEST_SHA,
        implementation_contract_sha, implementation_package_sha)
    from app.r2d2_v2_store import MemoryShadowStore
    release = Release('R2D2-V2-SHADOW-LIVE-INDEPENDENT', 'CERTIFIED', date(2026, 9, 8),
        datetime(2026, 9, 6, tzinfo=timezone.utc), 'a' * 40, 'b' * 64,
        earnings_amendment_sha=EARNINGS_AMENDMENT_SHA,
        earnings_closed_manifest_sha=EARNINGS_CLOSED_MANIFEST_SHA,
        implementation_contract_sha=implementation_contract_sha(),
        implementation_package_sha=implementation_package_sha())
    store = MemoryShadowStore()
    collector = ShadowCollector(store, None, release, calendar=ShadowCalendar())
    state = collector._initial()
    state['ledger'] = admission()
    state['instrument_episodes'] = {'US:SYNTH': ['synthetic-eligible']}
    # This unit exercises receipt processing only; the separate continuous-price
    # watch is intentionally not enrolled and no observability claim is made.
    return collector, store, state


def file_source(tmp_path, e):
    from app.r2d2_v2_sources import FileShadowSource, MANIFEST_SHA, AMENDMENT_SHA, canonical
    from app.r2d2_v2_store import digest
    root = tmp_path / 'private-spool'
    root.mkdir(mode=0o700)
    (root / 'events').mkdir(mode=0o700)
    raw = deepcopy(e)
    identity = raw.pop('event_id')
    body = dict(schema='V2_SHADOW_SOURCE_EVENT_V2', manifest_sha=MANIFEST_SHA,
        amendment_sha=AMENDMENT_SHA, source_id='synthetic-live-source', source_at=raw['at'],
        available_at=raw['available_at'], sequence=0,
        provenance={'producer': 'synthetic', 'version': 'v1', 'payload_sha256': digest(raw)},
        event_id=identity, event=raw)
    body['self_sha256'] = digest(body)
    target = root / 'events' / (identity + '.' + body['self_sha256'] + '.json')
    target.write_bytes(canonical(body)); target.chmod(0o600)
    return FileShadowSource(root), root


def test_real_file_collector_receipt_factual_then_restart_no_duplicate(tmp_path):
    from app.r2d2_v2_sources import FileShadowSource
    collector, store, initial = collector_fixture()
    event = observation()
    source, root = file_source(tmp_path, event)
    consumed = utc('2026-09-08T22:00:10Z')
    events = source.events(consumed)
    assert len(events) == 1 and source.last_event_diagnostics == []
    def transition(s):
        journals = []
        collector._events(s, journals, events, [], consumed, SESSION)
        return s, journals, {'ok': True}
    store.atomic(collector.release.epoch, initial, transition, consumed)
    saved = store.read(collector.release.epoch)
    row = saved['state']['ledger']['research']['synthetic-eligible']
    receipt = next(iter(row['earnings_observations'].values()))
    assert row['intent']['at'] == consumed.isoformat()
    assert receipt['source_detected_at'] == event['at']
    assert receipt['detected_at'] == consumed.isoformat()
    journal = store.journal(collector.release.epoch)[0]['payload']
    assert journal['applied_event']['source_available_at'] == event['available_at']
    assert journal['source']['at'] == event['at']
    # A fresh source object reads the immutable envelope again after restart.
    events = FileShadowSource(root).events(consumed)
    store.atomic(collector.release.epoch, initial, transition, consumed)
    assert store.read(collector.release.epoch) == saved
    assert len(store.journal(collector.release.epoch)) == 1


def test_official_holiday_round_rolls_back_without_receipt(tmp_path):
    from app.r2d2_v2_store import ShadowIntegrityError
    collector, store, initial = collector_fixture()
    e = observation()
    e.update(round_session='2026-09-07', round_received_at='2026-09-07T22:00:00Z')
    source, _ = file_source(tmp_path, e)
    now = utc(DETECTED)
    events = source.events(now)
    assert len(events) == 1  # shape and clock alone cannot certify the calendar.
    def transition(s):
        journals = []
        collector._events(s, journals, events, [], now, SESSION)
        return s, journals, {}
    with pytest.raises(ShadowIntegrityError, match='EARNINGS_ROUND_SESSION_INVALID'):
        store.atomic(collector.release.epoch, initial, transition, now)
    assert store.read(collector.release.epoch) is None
    assert store.journal(collector.release.epoch) == []


def test_absence_is_not_synthesized_into_successful_empty_round():
    s = admission()
    # The receipt inventory reports zero observed facts and the open research
    # remains unresolved; zero is not a statement that the provider was queried.
    assert earnings_observation_counts(s, SESSION) == {
        'ELIGIBLE': {'EARNINGS_DETECTED_AFTER_ENTRY': 0, 'EARNINGS_OBSERVATION_FAILED': 0},
        'CONTROL': {'EARNINGS_DETECTED_AFTER_ENTRY': 0, 'EARNINGS_OBSERVATION_FAILED': 0}}
    assert s['research']['synthetic-eligible']['earnings_observations'] == {}
    assert export_session_statistics(s, SESSION)['data_gate_unknown']


def test_later_event_and_quote_cannot_repair_failed_observation_gate():
    failure = observation(failed=True, at='2026-09-08T14:01:01Z', available='2026-09-08T14:01:05Z')
    failure.update(round_session='2026-09-04', round_received_at='2026-09-04T22:00:00Z')
    s = apply(admission(), failure)
    detected = observation(event_id='synthetic-later-known', round_char='b',
        at='2026-09-08T14:02:01Z', available='2026-09-08T14:02:05Z')
    detected.update(round_session='2026-09-04', round_received_at='2026-09-04T22:00:00Z')
    s = apply(s, detected)
    s = apply(s, quote(at='2026-09-08T14:02:06Z'))
    row = s['research']['synthetic-eligible']
    assert row['status'] == 'CLOSED' and row['exit_cause'] == 'EVENT'
    assert row['category'] == 'unobservable' and row['order_unknown']
    assert export_session_statistics(s, SESSION)['data_gate_unknown']
    assert earnings_observation_counts(s, SESSION)['ELIGIBLE'] == {
        'EARNINGS_DETECTED_AFTER_ENTRY': 1, 'EARNINGS_OBSERVATION_FAILED': 1}


def test_public_data_counts_use_valid_risk_stratum_before_exclusion():
    from app.r2d2_v2_shadow import _compact_evaluation, public_summary, RISK_C75
    _, _, state = collector_fixture()
    code = 'EARNINGS_WITHIN_HORIZON'
    candidates = {key: _compact_evaluation(dict(status='DATA_INELIGIBLE', arm=None,
        risk_score=risk, reasons=[code])) for key, risk in [
        ('US:SYNTH-LOW', RISK_C75), ('US:SYNTH-HIGH', RISK_C75 + 0.01),
        ('US:SYNTH-MISSING', None), ('US:SYNTH-BOOLEAN', True)]}
    assert all(c['arm'] is None for c in candidates.values())
    state['sessions'][SESSION] = dict(date=SESSION, entry_session=True, capture_closed=True,
        universe=list(candidates), candidates=candidates, attempts=1, diagnostics=[])
    public = public_summary(state)
    session = public['sessions'][0]
    assert session['earnings_counts_by_arm']['ELIGIBLE'][code] == 1
    assert session['earnings_counts_by_arm']['CONTROL'][code] == 1
    assert session['earnings_counts_by_arm']['UNASSIGNED'][code] == 2
    assert len(session['earnings_counts_by_arm']['ELIGIBLE']) == 8
    assert 'VALID_RISK_R1_STRATUM' in session['earnings_count_basis']
    assert 'SYNTH' not in json.dumps(public)


def test_event_exit_fraction_all_closed_denominator_latency_and_zero_none():
    from app.r2d2_v2_portfolio import earnings_public_sessions
    s = admission()
    s, _, _ = register_candidate(s, episode_key='synthetic-other', instrument_key='US:SYNTHB',
        arm='ELIGIBLE', session=SESSION, opened_at=OPEN, maturity_at=MATURITY,
        geometry=s['research']['synthetic-eligible']['original'])
    e = observation(at='2026-09-08T14:01:01Z', available='2026-09-08T14:01:05Z')
    e.update(round_session='2026-09-04', round_received_at='2026-09-04T22:00:00Z')
    s = apply(s, e)
    s = apply(s, quote(at='2026-09-08T14:01:06Z'))
    s = apply(s, dict(event_id='synthetic-other-target', type='TRADE', instrument_key='US:SYNTHB',
        session=SESSION, at='2026-09-08T14:01:07Z', available_at='2026-09-08T14:01:07Z', price=110, regular=True))
    public = earnings_public_sessions(s)[SESSION]
    eligible, control = public['exits']['ELIGIBLE'], public['exits']['CONTROL']
    assert eligible['closed_episodes'] == 2 and eligible['event_exits'] == 1
    assert eligible['event_exit_fraction'] == 0.5
    assert eligible['mean_detection_to_exit_seconds'] == 1
    assert eligible['detection_to_exit_seconds_sum'] == 1
    assert control['closed_episodes'] == control['event_exits'] == 0
    assert control['event_exit_fraction'] is None and control['mean_detection_to_exit_seconds'] is None
    assert 'SYNTH' not in json.dumps(public) and 'synthetic' not in json.dumps(public)


def test_delayed_round_before_open_publishes_factual_detection_session():
    collector, _, state = collector_fixture()
    state['last_session'] = SESSION
    state['last_cycle_at'] = '2026-09-08T22:00:00Z'
    state['clock_receipts'] = ['SESSION_OPEN:' + SESSION, 'SESSION_CLOSE:' + SESSION]
    state['sessions'][SESSION] = dict(date=SESSION, entry_session=True, capture_closed=True,
        universe=['US:SYNTH'], candidates={}, pending={}, attempts=1, diagnostics=[])
    e = observation(at='2026-09-09T12:59:58Z', available='2026-09-09T12:59:59Z')
    e.update(source_id='synthetic-live-source', sequence=0, envelope_sha256='d' * 64)
    now = utc('2026-09-09T13:00:00Z')  # 09:00 ET; official session opens 09:30.
    result, _, public = collector._cycle(state, None, [e], [], now)
    row = result['ledger']['research']['synthetic-eligible']
    receipt = next(iter(row['earnings_observations'].values()))
    assert receipt['detected_at'] == now.isoformat()
    assert receipt['session'] == '2026-09-09'
    assert receipt['processing_session'] == SESSION
    assert '2026-09-09' not in result['sessions']  # no premature economic session
    assert result['ledger']['session'] == SESSION
    assert public['sessions'][0]['earnings_counts_by_arm']['ELIGIBLE']['EARNINGS_DETECTED_AFTER_ENTRY'] == 0
    assert len(public['earnings_observation_dates']) == 1
    observed = public['earnings_observation_dates'][0]
    assert observed['date'] == '2026-09-09'
    assert observed['counts']['ELIGIBLE']['EARNINGS_DETECTED_AFTER_ENTRY'] == 1
    assert 'SYNTH' not in json.dumps(public)
