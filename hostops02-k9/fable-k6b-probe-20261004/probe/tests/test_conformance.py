"""The family's conformance suite (121 tests per fixture) applied to the capacity probe in each of its three steps.

LOAD is the step whose success is COMPLETE_OUTCOME; CALENDAR and IDENT complete with their own outcomes, so the one test
of the suite that names the outcome is restated for them with success_of(plan) in the place of the constant. The
suite's test of the date scope asks every day of the class READ to pass; this source narrows the class to the bands of
each step (A2 rev 3, section 6-A), so that test is replaced, for each step, by one that asserts the same literal set at
the dispatcher (the class, unchanged) and, at the source and through the dispatcher's local authentication, the bands:
every other day of the class refused with STEP_DAY_NOT_IN_SCOPE, a window outside the band of its day with
STEP_WINDOW_OUTSIDE_THE_BAND, the dispatcher saying the source's own code, before any claim. Everything else of the
suite runs unchanged. OTHERS: the sibling operations of hostops02 that lie beside the core, when there are any."""
from datetime import datetime,timedelta
import json

import conformance
import family as f
import hostemu
import kprobe

SIBLINGS=tuple(str(path) for path in (f.CORE.parent/name for name in ('catalog_init','install_release','epoch_readback','activate','tls_probe','k6b'))
               if (path/'build'/'ASSEMBLY.json').is_file())

def at(day,clock):return datetime.fromisoformat(day+'T'+clock+'+00:00')

class Steps(conformance.Conformance):
    DIRECTORY=kprobe.DIRECTORY
    OTHERS=SIBLINGS
    STEP=None

    def test_date_scope_is_the_class_of_the_source_at_both_layers(self,tmp_path):
        """Literal sets, not the module's own. The dispatcher carries the class READ (nine days) and refuses every other
        day itself; the source accepts the bands of its step only, and the dispatcher, which runs the source's
        authenticate() before any claim, refuses every other day of the class and every window outside a band."""
        k,docs,_=self.one();m=k.m;expected=conformance.DATE_SETS[m.DATE_CLASS];assert m.DATES==expected==conformance.EPOCH_DAYS
        bands={day:(begin,stop) for day,begin,stop in m.STEP_BANDS[self.STEP]}
        for day in ('2026-10-01',)+conformance.EPOCH_DAYS+('2026-10-11','2027-10-05'):
            instant=at(day,'22:00:00');docs.shift(instant,instant+timedelta(minutes=5))
            directory=tmp_path/day;directory.mkdir();fresh,_=self.case(instant);dispatch=f.Dispatch(fresh,directory)
            if day in bands:
                docs.authenticate(clock=lambda:instant);assert dispatch.prepare()['status']=='AWAITING_PUBLICATION_NO_SPAWN'
            elif day in expected:
                assert conformance.refusal(lambda:docs.authenticate(clock=lambda:instant))=='STEP_DAY_NOT_IN_SCOPE'
                result=docs.run(f.Untouchable(),clock=lambda:instant);assert (result['status'],result['code'])==('REFUSED','STEP_DAY_NOT_IN_SCOPE')
                assert conformance.refusal(dispatch.prepare)=='STEP_DAY_NOT_IN_SCOPE' and not dispatch.claims()
            else:
                assert conformance.refusal(lambda:docs.authenticate(clock=lambda:instant))=='DATE_NOT_IN_SCOPE'
                result=docs.run(f.Untouchable(),clock=lambda:instant);assert (result['status'],result['code'])==('REFUSED','DATE_NOT_IN_SCOPE')
                assert conformance.refusal(dispatch.prepare)=='DISPATCH_DATE' and not dispatch.claims()
        # each band, to the second, at both layers
        for day,(begin,stop) in sorted(bands.items()):
            first,last=at(day,begin),at(day,stop)
            for start,end,code in ((first,first+timedelta(minutes=5),None),(last-timedelta(minutes=5),last,None),
                                   (first-timedelta(seconds=1),first+timedelta(minutes=5),'STEP_WINDOW_OUTSIDE_THE_BAND'),
                                   (last-timedelta(minutes=5),last+timedelta(seconds=1),'STEP_WINDOW_OUTSIDE_THE_BAND'),
                                   (first-timedelta(minutes=10),first-timedelta(minutes=5),'STEP_WINDOW_OUTSIDE_THE_BAND')):
                label='%s-%s-%s'%(day,start.strftime('%H%M%S'),end.strftime('%H%M%S'));directory=tmp_path/label;directory.mkdir()
                k,host=kprobe.world(self.STEP);fresh=f.Docs(k,kprobe.fields(self.STEP,host),now=start,minutes=(end-start).total_seconds()/60)
                dispatch=f.Dispatch(fresh,directory);dispatch.config['latest_start']=(end-timedelta(seconds=80)).isoformat();dispatch.save()
                if code is None:
                    fresh.authenticate(clock=lambda:start);assert dispatch.prepare()['status']=='AWAITING_PUBLICATION_NO_SPAWN'
                else:
                    assert conformance.refusal(lambda:fresh.authenticate(clock=lambda:start))==code,(day,label)
                    assert conformance.refusal(dispatch.prepare)==code and not dispatch.claims()
        day=sorted(bands)[0];instant=at(day,'22:00:00');docs.shift(instant,instant+timedelta(minutes=5))
        for value in (None,20261004,[day]):
            docs.request['date']=value;docs.chain();assert conformance.refusal(docs.authenticate)=='DATE_NOT_IN_SCOPE'
        docs.request['date']='2026-10-03';docs.chain();assert conformance.refusal(lambda:docs.authenticate(clock=lambda:instant))=='DATE_WINDOW_MISMATCH'

class TestLoad(Steps):
    STEP='LOAD'
    @staticmethod
    def case(now=None):return kprobe.case('LOAD',now)

class OwnOutcome(Steps):
    def test_bound_fixture_completes_and_the_reviewed_transport_accepts_the_sealed_receipt(self):
        k,docs,host=self.one();m=k.m;before=conformance.engine_state(host);receipt=docs.run(host)
        assert m.success_of(docs.plan)==m.STEP_OUTCOMES[self.STEP]!=m.COMPLETE_OUTCOME and docs.go['success_criterion']==m.STEP_OUTCOMES[self.STEP]
        assert receipt['status']==m.COMPLETE_STATUS and receipt['outcome']==m.STEP_OUTCOMES[self.STEP] and receipt['code'] is None and f.sealed(receipt)
        assert receipt['schema']==m.RECEIPT_SCHEMA and receipt['operation']==m.OPERATION and receipt['scope_sha256']==m.SCOPE_SHA256
        assert receipt['core_sha256']==m.CORE_SHA256==f.assembler().core_sha256()
        assert (receipt['request_sha256'],receipt['authority_sha256'],receipt['go_sha256'],receipt['payload_sha256'])==(
            docs.pins().request,docs.pins().authority,docs.pins().go,f.sha(k.source)) and receipt['host_binding_sha256']==f.HOST
        assert receipt['ready'] is False and receipt['secret_bytes_in_receipt'] is False
        assert receipt['activation_performed'] is False and receipt['daemon_reload_performed'] is False
        assert receipt['size_reductions']==[] and len(f.line(receipt))<=m.RECEIPT_LIMIT+m.SEAL_OVERHEAD
        assert m.canonical(receipt['effects'])==m.canonical(docs.go['effects'])
        assert hostemu.SECRET.encode() not in f.line(receipt) and b'never-emit' not in f.line(receipt)
        assert host.mutating()==[] and conformance.engine_state(host)==before
        value=json.loads(f.line(receipt));claimed=value.pop('metadata_sha256');assert f.sha(f.canonical(value))==claimed

class TestCalendar(OwnOutcome):
    STEP='CALENDAR'
    @staticmethod
    def case(now=None):return kprobe.case('CALENDAR',now)

class TestIdent(OwnOutcome):
    STEP='IDENT'
    @staticmethod
    def case(now=None):return kprobe.case('IDENT',now)
