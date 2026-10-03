"""The family's conformance suite (121 tests) applied to C3, with one test replaced.

The bound fixture is dated inside the band of the weekend authority (2026-10-04, 11:45 to 12:30 UTC), the only window
the source accepts. The suite's test of the date scope asks every day of the class READ to pass; this source narrows
the class to that band, so the test is replaced by one that asserts the same literal set at the dispatcher (the class,
unchanged) and, at the source and through the dispatcher's local authentication, the narrower band: every other day of
the class refused with PROBE_DAY_NOT_IN_SCOPE, a window outside the band with PROBE_WINDOW_OUTSIDE_THE_BAND, the dispatcher
saying the source's own code, before any claim. Everything else of the suite runs unchanged, and the four sibling operations of tier 0 are added to the
operations whose documents this one must refuse when they lie beside the core."""
from datetime import datetime,timedelta,timezone
from pathlib import Path

import conformance
import family as f
import c3

SIBLINGS=tuple(str(path) for path in (f.CORE.parent/name for name in ('catalog_init','install_release','epoch_readback','activate'))
               if (path/'build'/'ASSEMBLY.json').is_file())

def noon(day):return datetime.fromisoformat(day+'T12:00:00+00:00')

class TestConformance(conformance.Conformance):
    DIRECTORY=c3.DIRECTORY
    OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return c3.case(now)

    def test_date_scope_is_the_class_of_the_source_at_both_layers(self,tmp_path):
        """Literal sets, not the module's own. The dispatcher carries the class READ (nine days) and refuses every other
        day itself; the source accepts one band of one day of it, and the dispatcher, which runs the source's
        authenticate() before any claim, refuses every other day of the class and every window outside the band."""
        k,docs,_=self.one();m=k.m;expected=conformance.DATE_SETS[m.DATE_CLASS];assert m.DATES==expected==conformance.EPOCH_DAYS
        assert (m.PROBE_DAY,m.PROBE_BAND)==('2026-10-04',('2026-10-04T11:45:00+00:00','2026-10-04T12:30:00+00:00'))
        for day in ('2026-10-01',)+conformance.EPOCH_DAYS+('2026-10-11','2027-10-05'):
            instant=noon(day);docs.shift(instant,instant+timedelta(minutes=5))
            directory=tmp_path/day;directory.mkdir();fresh,_=self.case(instant);dispatch=f.Dispatch(fresh,directory)
            if day==m.PROBE_DAY:
                docs.authenticate(clock=lambda:instant);assert dispatch.prepare()['status']=='AWAITING_PUBLICATION_NO_SPAWN'
            elif day in expected:
                assert conformance.refusal(lambda:docs.authenticate(clock=lambda:instant))=='PROBE_DAY_NOT_IN_SCOPE'
                result=docs.run(f.Untouchable(),clock=lambda:instant);assert (result['status'],result['code'])==('REFUSED','PROBE_DAY_NOT_IN_SCOPE')
                assert conformance.refusal(dispatch.prepare)=='PROBE_DAY_NOT_IN_SCOPE' and not dispatch.claims()
            else:
                assert conformance.refusal(lambda:docs.authenticate(clock=lambda:instant))=='DATE_NOT_IN_SCOPE'
                result=docs.run(f.Untouchable(),clock=lambda:instant);assert (result['status'],result['code'])==('REFUSED','DATE_NOT_IN_SCOPE')
                assert conformance.refusal(dispatch.prepare)=='DISPATCH_DATE' and not dispatch.claims()
        # the band, to the second, at both layers
        band=[datetime.fromisoformat(value) for value in m.PROBE_BAND]
        for start,end,code in ((band[0],band[0]+timedelta(minutes=5),None),(band[1]-timedelta(minutes=5),band[1],None),
                               (band[0]-timedelta(seconds=1),band[0]+timedelta(minutes=5),'PROBE_WINDOW_OUTSIDE_THE_BAND'),
                               (band[1]-timedelta(minutes=5),band[1]+timedelta(seconds=1),'PROBE_WINDOW_OUTSIDE_THE_BAND'),
                               (band[1],band[1]+timedelta(minutes=5),'PROBE_WINDOW_OUTSIDE_THE_BAND'),
                               (band[0]-timedelta(minutes=10),band[0]-timedelta(minutes=5),'PROBE_WINDOW_OUTSIDE_THE_BAND')):
            label='%s-%s'%(start.strftime('%H%M%S'),end.strftime('%H%M%S'));directory=tmp_path/label;directory.mkdir()
            k,_=c3.world();fresh=f.Docs(k,c3.fields(),now=start,minutes=(end-start).total_seconds()/60);dispatch=f.Dispatch(fresh,directory)
            dispatch.config['latest_start']=(end-timedelta(seconds=80)).isoformat();dispatch.save()
            if code is None:
                fresh.authenticate(clock=lambda:start);assert dispatch.prepare()['status']=='AWAITING_PUBLICATION_NO_SPAWN'
            else:
                assert conformance.refusal(lambda:fresh.authenticate(clock=lambda:start))==code
                assert conformance.refusal(dispatch.prepare)==code and not dispatch.claims()
        instant=noon(m.PROBE_DAY);docs.shift(instant,instant+timedelta(minutes=5))
        for value in (None,20261004,[m.PROBE_DAY]):
            docs.request['date']=value;docs.chain();assert conformance.refusal(docs.authenticate)=='DATE_NOT_IN_SCOPE'
        docs.request['date']='2026-10-03';docs.chain();assert conformance.refusal(lambda:docs.authenticate(clock=lambda:instant))=='DATE_WINDOW_MISMATCH'
