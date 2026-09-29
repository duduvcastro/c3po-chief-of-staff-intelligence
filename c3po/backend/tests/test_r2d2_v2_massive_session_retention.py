"""Session ACKs must never be collapsed into an epoch-wide numeric cursor."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import pytest
from app.r2d2_v2_sources import SourceUnavailable, canonical
from app.r2d2_v2_massive_retention import read_committed_ack, plan_committed_retention
from app.r2d2_v2_massive_journal import MassiveJournal
from test_r2d2_v2_massive_retention import ack_snapshot_fixture, v2_ack_cursor, gap

EPOCH='R2D2-V2-SHADOW-SESSION-FIXTURE'
DAY='2026-09-25'
NEXT='2026-09-28'
NOW=datetime(2026,9,29,tzinfo=timezone.utc)


def session_cursor():
    cursor=v2_ack_cursor()
    cursor['massive']={'version':2,'epoch':EPOCH,'sessions':{DAY:3,NEXT:1}}
    return cursor


def test_session_ack_observation_requires_explicit_selection_for_scalar():
    store,_,_=ack_snapshot_fixture(session_cursor())
    ack=read_committed_ack(store,epoch=EPOCH,release_sha='a'*64)
    assert ack['committed_sessions']=={DAY:3,NEXT:1}
    assert 'committed_sequence' not in ack and 'session' not in ack
    selected=read_committed_ack(store,epoch=EPOCH,release_sha='a'*64,session=NEXT)
    assert selected['committed_sequence']==1 and selected['session']==NEXT
    assert selected['committed_sessions'][DAY]==3


@pytest.mark.parametrize('bad',['epoch','extra','version','boolean','negative','date','oversized','not_dict'])
def test_bad_session_map_cannot_become_retention_authority(bad):
    cursor=session_cursor();child=cursor['massive']
    if bad=='epoch':child['epoch']='other'
    elif bad=='extra':child['unexpected']=3
    elif bad=='version':child['version']=True
    elif bad=='boolean':child['sessions'][DAY]=True
    elif bad=='negative':child['sessions'][DAY]=-1
    elif bad=='date':child['sessions']['not-a-session']=1
    elif bad=='oversized':child['sessions']={str(i):0 for i in range(257)}
    elif bad=='not_dict':child['sessions']=[]
    store,row,records=ack_snapshot_fixture(cursor)
    before=deepcopy((row,records))
    with pytest.raises((SourceUnavailable,ValueError)):
        read_committed_ack(store,epoch=EPOCH,release_sha='a'*64)
    assert (row,records)==before


def test_missing_session_or_implicit_numeric_selection_cannot_plan(tmp_path,monkeypatch):
    from app import r2d2_v2_massive_retention as retention
    store,_,_=ack_snapshot_fixture(session_cursor())
    journal=MassiveJournal(tmp_path);journal(None,gap(DAY,0))
    before=journal.path.read_bytes()
    monkeypatch.setattr(retention,'_plan_retention_locked',lambda *a,**k:pytest.fail('bad ACK reached planner'))
    for selection in (None,'2026-09-24'):
        with pytest.raises(SourceUnavailable):
            plan_committed_retention(journal,store,epoch=EPOCH,release_sha='a'*64,now=NOW,
                retain_from_session=NEXT,session=selection)
    assert journal.path.read_bytes()==before


def test_session_argument_cannot_relabel_legacy_scalar_ack():
    store,_,_=ack_snapshot_fixture(v2_ack_cursor())
    with pytest.raises(SourceUnavailable,match='RETENTION_LEGACY_SESSION_UNBOUND'):
        read_committed_ack(store,epoch=EPOCH,release_sha='a'*64,session=DAY)


def full_gap(day,n):
    at=f'{day}T14:00:{n:02d}+00:00'
    return {'event':{'type':'DATA_GAP','session':day,'at':at,'available_at':at,
                    'instrument_key':'US:SYNTH','reason':'synthetic'}}


def bind_local_journal(journal,day,committed=None):
    from app.r2d2_v2_massive_events import session_envelope
    cursor=session_cursor();cursor['massive']['sessions'][day]=journal.page()['through'] if committed is None else committed
    store,row,records=ack_snapshot_fixture(cursor)
    receipts={}
    for record in journal.page()['records']:
        if record['sequence']>cursor['massive']['sessions'][day]:continue
        envelope=session_envelope(record,NOW,epoch=EPOCH,session=day)
        receipts[envelope['event_id']]=hashlib.sha256(canonical(envelope)).hexdigest()
    records[0]['payload']['raw_receipts']=receipts
    return store


def test_session_bound_plan_verifies_only_the_selected_local_journal(tmp_path):
    journal=MassiveJournal(tmp_path/'old')
    for n in range(3):journal(None,full_gap(DAY,n))
    store=bind_local_journal(journal,DAY)
    plan=plan_committed_retention(journal,store,epoch=EPOCH,release_sha='a'*64,now=NOW,
        retain_from_session=NEXT,session=DAY)
    assert plan['committed_sequence']==3 and plan['journal_session']==DAY
    assert plan['ack']['session']==DAY and plan['verified_committed_receipts']==3
    assert plan['prune_through']==2 and journal.retention_floor()==0
    wrong=MassiveJournal(tmp_path/'new')
    for n in range(3):wrong(None,full_gap(NEXT,n))
    with pytest.raises(SourceUnavailable,match='RETENTION_JOURNAL_SESSION_MISMATCH'):
        plan_committed_retention(wrong,store,epoch=EPOCH,release_sha='a'*64,now=NOW,
            retain_from_session=NEXT,session=DAY)
    assert wrong.retention_floor()==0


def test_all_consumers_are_bound_to_the_same_explicit_session(tmp_path):
    from app.r2d2_v2_massive_retention import plan_consumers_retention
    journal=MassiveJournal(tmp_path)
    for n in range(3):journal(None,full_gap(DAY,n))
    fast=bind_local_journal(journal,DAY,3)
    slow=bind_local_journal(journal,DAY,2)
    consumers={name:{'store':store,'epoch':EPOCH,'release_sha':'a'*64}
               for name,store in [('fast',fast),('slow',slow)]}
    plan=plan_consumers_retention(journal,consumers,required_consumers=['fast','slow'],
        now=NOW,retain_from_session=NEXT,session=DAY)
    assert plan['committed_sequence']==2 and plan['prune_through']==1
    assert {ack['session'] for ack in plan['consumer_acks'].values()}=={DAY}
    assert plan['consumer_acks']['fast']['committed_sessions'][NEXT]==1
    assert journal.retention_floor()==0
    with pytest.raises(SourceUnavailable,match='RETENTION_SESSION_REQUIRED'):
        plan_consumers_retention(journal,consumers,required_consumers=['fast','slow'],
            now=NOW,retain_from_session=NEXT)


def test_session_envelope_preserves_contract_prices_clocks_and_policy_pins(tmp_path):
    from app.r2d2_v2_massive_events import journal_envelope,session_envelope
    journal=MassiveJournal(tmp_path);journal(None,full_gap(DAY,0))
    record=journal.page()['records'][0]
    original=journal_envelope(record,NOW)
    wrapped=session_envelope(record,NOW,epoch=EPOCH,session=DAY)
    assert wrapped['source_id']=='massive-am-v2-'+hashlib.sha256(EPOCH.encode()).hexdigest()[:32]+'-'+DAY
    for key in ('schema','manifest_sha','amendment_sha','source_at','available_at','sequence','event_id','event'):
        assert wrapped[key]==original[key]
    assert wrapped['provenance']['payload_sha256']==original['provenance']['payload_sha256']
    assert wrapped['self_sha256']!=original['self_sha256']
    other=session_envelope(record,NOW,epoch=EPOCH+'-OTHER',session=DAY)
    assert other['source_id']!=wrapped['source_id'] and other['self_sha256']!=wrapped['self_sha256']
    with pytest.raises(SourceUnavailable,match='MASSIVE_SESSION_RECEIPT_MISMATCH'):
        session_envelope(record,NOW,epoch=EPOCH,session=NEXT)
