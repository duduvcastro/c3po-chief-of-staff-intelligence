"""The family's conformance suite (121 tests) applied to the token placement, with one test replaced.

The bound fixture is dated 2026-10-03 17:00 UTC. The suite's test of the date scope asks every day of the class
WRITE_WEEKEND (2026-10-02 to 2026-10-04) to pass; this source narrows the class to 2026-10-03 and 2026-10-04, so the
test is replaced by one that asserts the same literal set at the dispatcher (the class, unchanged) and, at the source
and through the dispatcher's local authentication, the narrower set: 2026-10-02 refused with WINDOW_NOT_ON_A_TOKEN_DAY,
the dispatcher saying the source's own code, before any claim. Everything else of the suite runs unchanged, and the
sibling operations are added to the operations whose documents this one must refuse when they lie beside the core."""
from datetime import datetime,timedelta

import conformance
import family as f
import tok

SIBLINGS=tuple(str(path) for path in (f.CORE.parent/name for name in ('catalog_init','install_release','epoch_readback','activate','tls_probe'))
               if (path/'build'/'ASSEMBLY.json').is_file())

def noon(day):return datetime.fromisoformat(day+'T12:00:00+00:00')

class TestConformance(conformance.Conformance):
    DIRECTORY=tok.DIRECTORY
    OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return tok.case(now)

    def test_date_scope_is_the_class_of_the_source_at_both_layers(self,tmp_path):
        """Literal sets, not the module's own. The dispatcher carries the class WRITE_WEEKEND and refuses every other day
        itself; the source accepts two days of it, and the dispatcher, which runs the source's authenticate() before
        any claim, refuses the third."""
        k,docs,_=self.one();m=k.m;expected=conformance.DATE_SETS[m.DATE_CLASS];assert m.DATES==expected==('2026-10-02','2026-10-03','2026-10-04')
        assert m.TOKEN_DAYS==('2026-10-03','2026-10-04')
        for day in ('2026-10-01',)+conformance.EPOCH_DAYS+('2026-10-11','2027-10-03'):
            instant=noon(day);docs.shift(instant,instant+timedelta(minutes=5))
            directory=tmp_path/day;directory.mkdir();fresh,_=self.case(instant);dispatch=f.Dispatch(fresh,directory)
            if day in m.TOKEN_DAYS:
                docs.authenticate(clock=lambda:instant);assert dispatch.prepare()['status']=='AWAITING_PUBLICATION_NO_SPAWN'
            elif day in expected:
                assert conformance.refusal(lambda:docs.authenticate(clock=lambda:instant))=='WINDOW_NOT_ON_A_TOKEN_DAY'
                result=docs.run(f.Untouchable(),clock=lambda:instant);assert (result['status'],result['code'])==('REFUSED','WINDOW_NOT_ON_A_TOKEN_DAY')
                assert conformance.refusal(dispatch.prepare)=='WINDOW_NOT_ON_A_TOKEN_DAY' and not dispatch.claims()
            else:
                assert conformance.refusal(lambda:docs.authenticate(clock=lambda:instant))=='DATE_NOT_IN_SCOPE'
                result=docs.run(f.Untouchable(),clock=lambda:instant);assert (result['status'],result['code'])==('REFUSED','DATE_NOT_IN_SCOPE')
                assert conformance.refusal(dispatch.prepare)=='DISPATCH_DATE' and not dispatch.claims()
        # the first and the last instant of the two days, at both layers
        for start,end in ((datetime.fromisoformat('2026-10-03T00:00:00+00:00'),datetime.fromisoformat('2026-10-03T00:15:00+00:00')),
                          (datetime.fromisoformat('2026-10-04T23:45:00+00:00'),datetime.fromisoformat('2026-10-04T23:59:59.999999+00:00'))):
            label=start.strftime('%d%H%M');directory=tmp_path/label;directory.mkdir()
            k,host=tok.world();fresh=f.Docs(k,tok.fields(host),now=start,minutes=(end-start).total_seconds()/60);dispatch=f.Dispatch(fresh,directory)
            dispatch.config['latest_start']=(end-timedelta(seconds=80)).isoformat();dispatch.save()
            fresh.authenticate(clock=lambda:start);assert dispatch.prepare()['status']=='AWAITING_PUBLICATION_NO_SPAWN'
        last=datetime.fromisoformat('2026-10-02T23:50:00+00:00');k,host=tok.world()
        fresh=f.Docs(k,tok.fields(host),now=last,minutes=9);assert conformance.refusal(lambda:fresh.authenticate(clock=lambda:last))=='WINDOW_NOT_ON_A_TOKEN_DAY'
        instant=noon('2026-10-03');docs.shift(instant,instant+timedelta(minutes=5))
        for value in (None,20261003,['2026-10-03']):
            docs.request['date']=value;docs.chain();assert conformance.refusal(docs.authenticate)=='DATE_NOT_IN_SCOPE'
        docs.request['date']='2026-10-04';docs.chain();assert conformance.refusal(lambda:docs.authenticate(clock=lambda:instant))=='DATE_WINDOW_MISMATCH'
