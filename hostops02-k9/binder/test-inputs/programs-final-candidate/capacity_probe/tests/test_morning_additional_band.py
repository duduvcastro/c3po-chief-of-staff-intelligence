"""Local synthetic conformance of the proposed extra A5 band, never an actual host/authority proof."""
from datetime import datetime,timedelta
import json
import pytest
import family as f
import kprobe

def at(stamp):return datetime.fromisoformat(stamp+'+00:00')

@pytest.mark.parametrize('step',('CALENDAR','IDENT'))
@pytest.mark.parametrize('start,end',(('2026-10-06T11:26:00','2026-10-06T11:31:00'),('2026-10-06T15:25:00','2026-10-06T15:30:00'),('2026-10-06T20:38:00','2026-10-06T20:43:00'),('2026-10-06T23:25:00','2026-10-06T23:30:00')))
def test_morning_and_original_evening_authenticate_and_dispatch_without_host_observation(step,start,end,tmp_path):
    k,host=kprobe.world(step);now,until=at(start),at(end);docs=f.Docs(k,kprobe.fields(step,host),now=now,minutes=(until-now).total_seconds()/60)
    docs.authenticate(clock=lambda:now)
    dispatch=f.Dispatch(docs,tmp_path);dispatch.config['latest_start']=(until-timedelta(seconds=80)).isoformat();dispatch.save()
    assert dispatch.prepare()['status']=='AWAITING_PUBLICATION_NO_SPAWN'
    assert len(dispatch.claims())==1 and not (tmp_path/'attempt'/'stdout.original').exists()
    intent=json.loads((tmp_path/'attempt'/'intent.json').read_bytes());assert intent['attempts']==1 and intent['retry'] is False
    assert host.mutating()==[]

@pytest.mark.parametrize('step',('CALENDAR','IDENT','LOAD'))
@pytest.mark.parametrize('start,end',(('2026-10-06T11:25:59','2026-10-06T11:30:00'),('2026-10-06T15:25:00','2026-10-06T15:30:00.000001'),('2026-10-06T15:30:00','2026-10-06T15:35:00'),('2026-10-05T11:26:00','2026-10-05T11:31:00'),('2026-10-07T11:26:00','2026-10-07T11:31:00')))
def test_outside_extra_band_is_refused_before_dispatch_claim_or_host(step,start,end,tmp_path):
    k,host=kprobe.world(step);now,until=at(start),at(end);docs=f.Docs(k,kprobe.fields(step,host),now=now,minutes=(until-now).total_seconds()/60)
    assert f.refusal(lambda:docs.authenticate(clock=lambda:now))=='STEP_WINDOW_OUTSIDE_THE_BAND'
    result=docs.run(f.Untouchable(),clock=lambda:now)
    assert (result['status'],result['code'])==('REFUSED','STEP_WINDOW_OUTSIDE_THE_BAND')
    dispatch=f.Dispatch(docs,tmp_path);dispatch.config['latest_start']=(until-timedelta(seconds=80)).isoformat();dispatch.save()
    assert f.refusal(dispatch.prepare)=='STEP_WINDOW_OUTSIDE_THE_BAND' and not dispatch.claims()
    assert host.mutating()==[]

@pytest.mark.parametrize('start,end',(('2026-10-06T11:26:00','2026-10-06T11:31:00'),('2026-10-06T15:25:00','2026-10-06T15:30:00')))
def test_load_never_gains_the_proposed_morning_band(start,end,tmp_path):
    k,host=kprobe.world('LOAD');now,until=at(start),at(end);docs=f.Docs(k,kprobe.fields('LOAD',host),now=now,minutes=(until-now).total_seconds()/60)
    assert f.refusal(lambda:docs.authenticate(clock=lambda:now))=='STEP_WINDOW_OUTSIDE_THE_BAND'
    assert docs.run(f.Untouchable(),clock=lambda:now)['code']=='STEP_WINDOW_OUTSIDE_THE_BAND'
    dispatch=f.Dispatch(docs,tmp_path);assert f.refusal(dispatch.prepare)=='STEP_WINDOW_OUTSIDE_THE_BAND' and not dispatch.claims()

@pytest.mark.parametrize('step',('CALENDAR','IDENT'))
def test_no_window_may_bridge_the_gap_between_the_two_disjoint_bands(step):
    m=kprobe.K().m
    assert f.refusal(lambda:m.validate_window({'not_before':'2026-10-06T15:25:00+00:00','expires_at':'2026-10-06T20:43:00+00:00'},step))=='STEP_WINDOW_OUTSIDE_THE_BAND'

def test_signed_scope_effects_expose_new_band_only_for_a5_and_original_load_band_is_exact():
    m=kprobe.K().m
    evening=[['2026-10-05','20:38:00','23:30:00'],['2026-10-06','20:38:00','23:30:00'],['2026-10-07','20:38:00','23:30:00'],['2026-10-08','20:38:00','23:30:00']]
    for step in ('CALENDAR','IDENT'):
        docs,_=kprobe.case(step);effects=docs.go['effects']
        assert effects['bands']==[['2026-10-04','16:26:00','23:30:00']]+evening+[['2026-10-06','11:26:00','15:30:00']]
        assert effects['additional_band_source']==m.SCOPE['steps']['additional_band_source']
        assert m.SCOPE['steps'][step]['bands']==effects['bands']
    docs,_=kprobe.case('LOAD');assert docs.go['effects']['bands']==evening==m.SCOPE['steps']['LOAD']['bands']
    assert 'additional_band_source' not in docs.go['effects'] and m.STEP_ADDITIONAL_BANDS['LOAD']==()
