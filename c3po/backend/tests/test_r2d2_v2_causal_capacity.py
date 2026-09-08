"""Causal byte limits: synthetic local inputs only; no database or providers."""
import base64
from datetime import date, datetime, timezone
import hashlib

import pytest

from app import r2d2_v2_causal_list as causal
from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_sources import MAX_SNAPSHOT_BYTES, SourceUnavailable, canonical

DAY = date(2026, 9, 8)
BUILT = datetime(2026, 9, 4, 20, 5, 1, 123456, tzinfo=timezone.utc)
EPOCH = 'R2D2-V2-DIAG-CAPACITY-FIXTURE'


@pytest.fixture(scope='module')
def calendar():
    return ShadowCalendar()


def inputs(calendar, count=1):
    bars=[]
    for session in calendar.details(DAY)['previous_sessions'][-20:]:
        at=calendar.details(session)['close'].isoformat()
        bars.append({'session_date':session.isoformat(),'open':100.01,'high':101.23,'low':99.45,
                     'close':100.67,'volume':150001,'complete':True,'regular_session':True,
                     'source_at':at,'available_at':at})
    daily={'bars':bars,'splits':[],'adjustment':'RAW_UNADJUSTED','coverage_verified':True,
           'split_coverage_verified':True,'source_at':bars[-1]['source_at'],'available_at':'2026-09-04T20:02:00+00:00'}
    names=[f'S{index:05d}' for index in range(count)]
    registry={'schema':causal.REGISTRY_SCHEMA,'source_id':'synthetic-capacity-registry',
              'source_at':'2026-09-04T20:00:01+00:00','available_at':'2026-09-04T20:01:00+00:00',
              'captured_at':'2026-09-04T20:01:00+00:00','coverage_verified':True,
              'instruments':[{'symbol':name,'market':'NASDAQ','security_type':'COMMON_STOCK',
                              'classification_verified':True} for name in names]}
    contract={'schema':causal.DAILY_SCHEMA,'source_id':'synthetic-capacity-daily',
              'source_at':bars[-1]['source_at'],'available_at':'2026-09-04T20:02:00+00:00',
              'instruments':[{'symbol':name,'daily':daily} for name in names]}
    return canonical(registry),canonical(contract)


def build(calendar, registry, daily, epoch=EPOCH):
    return causal.build_commitment(epoch=epoch,day=DAY,built_at=BUILT,
                                   registry_bytes=registry,daily_bytes=daily,calendar=calendar)


def envelope(commitment, reference='synthetic'):
    binding={key:commitment[key] for key in
             ('epoch','session','manifest_sha','amendment_sha','list_sha256','n_cut')}
    binding['commitment_sha256']=causal.digest(commitment)
    audit={'event_id':'00000000-0000-4000-8000-000000000001','event_type':'r2d2.v2.causal_list_built',
           'occurred_at':commitment['built_at'],'payload':binding}
    publication={'event_id':'00000000-0000-4000-8000-000000000002','event_type':'r2d2.v2.causal_list_published',
                 'occurred_at':'2026-09-05T12:00:01.123456+00:00',
                 'payload':{**binding,'build_audit_event_id':audit['event_id'],'channel':'github_issue_348',
                            'publication_reference':reference,'published_at':'2026-09-05T12:00:01.123456+00:00'}}
    return {'commitment':commitment,'audit_receipt':audit,'publication_receipt':publication}


def test_input_and_final_envelope_share_existing_64mib_ceiling():
    assert causal.MAX_INPUT_BYTES == causal.MAX_CAUSAL_ENVELOPE_BYTES == MAX_SNAPSHOT_BYTES == 64*1024*1024
    assert causal.CAUSAL_RECEIPT_RESERVE_BYTES == 16*1024


def test_valid_6001_common_stock_daily_rows_above_20mib_are_accepted(calendar):
    registry,daily=inputs(calendar,6001)
    assert 20*1024*1024 < len(daily) < causal.MAX_INPUT_BYTES
    result=build(calendar,registry,daily)
    assert result['counts']['registry']==result['counts']['liquidity_passed']==6001
    assert result['counts']['selected']==550 and result['counts']['reasons']['N_CUT_EXCLUDED']==5451
    assert result['list']==[f'S{index:05d}' for index in range(550)]
    assert hashlib.sha256(base64.b64decode(result['daily_raw_base64'])).hexdigest()==hashlib.sha256(daily).hexdigest()
    assert causal.check_causal_envelope_size(envelope(result)) <= causal.MAX_CAUSAL_ENVELOPE_BYTES


def test_valid_43mb_raw_json_remains_accepted_with_small_registry(calendar):
    registry,daily=inputs(calendar)
    # Preserve exact input bytes; whitespace is valid JSON and creates an exact
    # raw-byte boundary without pretending to benchmark a full provider universe.
    daily += b' '*(43_067_980-len(daily))
    result=build(calendar,registry,daily)
    assert result['counts']['selected']==1
    assert result['daily_contract_sha256']==hashlib.sha256(daily).hexdigest()
    assert causal.check_causal_envelope_size(envelope(result)) <= causal.MAX_CAUSAL_ENVELOPE_BYTES


def test_raw_input_over_64mib_is_rejected_before_parser(calendar,monkeypatch):
    def forbidden(*_):
        pytest.fail('oversized raw input must not reach JSON parser')
    monkeypatch.setattr(causal,'_load_json',forbidden)
    with pytest.raises(SourceUnavailable,match='^CAUSAL_INPUT_SIZE_LIMIT$'):
        build(calendar,b'{}',b'x'*(causal.MAX_INPUT_BYTES+1))


def test_individually_valid_raw_sizes_can_fail_combined_base64_before_parser(calendar,monkeypatch):
    monkeypatch.setattr(causal,'MAX_CAUSAL_ENVELOPE_BYTES',1024)
    monkeypatch.setattr(causal,'CAUSAL_RECEIPT_RESERVE_BYTES',0)
    def forbidden(*_):
        pytest.fail('combined encoded overflow must not reach JSON parser')
    monkeypatch.setattr(causal,'_load_json',forbidden)
    with pytest.raises(SourceUnavailable,match='^CAUSAL_ENVELOPE_SIZE_LIMIT$'):
        build(calendar,b'a'*400,b'b'*400)


def test_projection_boundary_is_exact_and_overflow_precedes_base64(calendar,monkeypatch):
    registry,daily=inputs(calendar)
    baseline=build(calendar,registry,daily)
    expected=len(canonical(baseline))
    empty={**baseline,'registry_raw_base64':'','daily_raw_base64':''}
    assert expected==len(canonical(empty))+4*((len(registry)+2)//3)+4*((len(daily)+2)//3)
    monkeypatch.setattr(causal,'MAX_CAUSAL_ENVELOPE_BYTES',expected+causal.CAUSAL_RECEIPT_RESERVE_BYTES)
    assert len(canonical(build(calendar,registry,daily)))==expected
    monkeypatch.setattr(causal,'MAX_CAUSAL_ENVELOPE_BYTES',expected+causal.CAUSAL_RECEIPT_RESERVE_BYTES-1)
    def forbidden(*_):
        pytest.fail('metadata overflow must not allocate encoded raw inputs')
    monkeypatch.setattr(causal.base64,'b64encode',forbidden)
    with pytest.raises(SourceUnavailable,match='^CAUSAL_ENVELOPE_SIZE_LIMIT$'):
        build(calendar,registry,daily)


def test_full_envelope_boundary_checked_before_receipt_verifier(calendar,monkeypatch):
    registry,daily=inputs(calendar)
    complete=envelope(build(calendar,registry,daily))
    size=len(canonical(complete))
    monkeypatch.setattr(causal,'MAX_CAUSAL_ENVELOPE_BYTES',size)
    assert causal.check_causal_envelope_size(complete)==size
    monkeypatch.setattr(causal,'MAX_CAUSAL_ENVELOPE_BYTES',size-1)
    def forbidden(*_):
        pytest.fail('oversized envelope must not reach any external receipt verifier')
    with pytest.raises(SourceUnavailable,match='^CAUSAL_ENVELOPE_SIZE_LIMIT$'):
        causal.validate_commitment(complete,epoch=EPOCH,day=DAY,
            now=datetime(2026,9,8,13,tzinfo=timezone.utc),calendar=calendar,receipt_verifier=forbidden)


@pytest.mark.parametrize('length',[4,5,6])
def test_decoded_cap_rejects_rounding_slack_in_base64(monkeypatch,length):
    monkeypatch.setattr(causal,'MAX_INPUT_BYTES',4)
    encoded=base64.b64encode(b'x'*length).decode()
    assert len(encoded)==8
    if length==4:
        assert causal._decode(encoded)==b'x'*4
    else:
        with pytest.raises(SourceUnavailable,match='^CAUSAL_INPUT_SIZE_LIMIT$'):
            causal._decode(encoded)


def test_receipt_reserve_covers_long_epoch_and_maximally_escaped_reference(calendar):
    registry,daily=inputs(calendar)
    commitment=build(calendar,registry,daily,epoch='R2D2-V2-SHADOW-'+'S'*80)
    complete=envelope(commitment,reference='\U0001f600'*512)
    overhead=len(canonical(complete))-len(canonical(commitment))
    assert 512*12 < overhead <= causal.CAUSAL_RECEIPT_RESERVE_BYTES
    assert causal.check_causal_envelope_size(complete)<=causal.MAX_CAUSAL_ENVELOPE_BYTES


def test_max_registry_count_metadata_is_measured_not_assumed(calendar):
    registry,daily=inputs(calendar,causal.MAX_REGISTRY)
    # Remove daily rows so this checks the maximum count/metadata surface
    # without a second full universe of market-bar objects.
    daily=canonical({'schema':causal.DAILY_SCHEMA,'source_id':'synthetic-capacity-daily',
                     'source_at':'2026-09-04T20:00:00+00:00','available_at':'2026-09-04T20:02:00+00:00',
                     'instruments':[]})
    result=build(calendar,registry,daily)
    assert result['counts']['registry']==causal.MAX_REGISTRY
    assert len(result['exclusions'])==causal.MAX_REGISTRY and result['list']==[]
    assert causal.check_causal_envelope_size(envelope(result))<=causal.MAX_CAUSAL_ENVELOPE_BYTES
