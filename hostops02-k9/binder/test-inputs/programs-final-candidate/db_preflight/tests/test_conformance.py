"""The family's conformance suite (121 tests) applied to DBR, once per signed mode: the bound fixture of mode QUERIES and
the bound fixture of mode PRIV are two different requests of the same source."""
import json

import conformance
import dbr
import family as f
import hostemu

class TestConformance(conformance.Conformance):
    DIRECTORY=dbr.DIRECTORY
    OTHERS=(dbr.DIRECTORY.parent/'db_priv',)
    @staticmethod
    def case(now=None):return dbr.case(now)
    def test_date_scope_is_the_class_of_the_source_at_both_layers(self,tmp_path):
        """The suite's test, with one addition the mode QUERIES requires: when the request is moved to another day, its PRIV
        receipt is moved with it (a receipt of another day is refused by design, tests/test_dbr.py). Literal date sets."""
        k,docs,_=self.one();expected=conformance.DATE_SETS[k.m.DATE_CLASS];assert k.m.DATES==expected
        for day in ('2026-10-01',)+conformance.EPOCH_DAYS+('2026-10-11','2027-10-05'):
            instant=conformance.noon(day);docs.shift(instant,instant+conformance.timedelta(minutes=5))
            docs.plan['priv_receipt']=dbr.priv_receipt(observed_at=day+'T11:40:00+00:00');docs.chain()
            directory=tmp_path/day;directory.mkdir();fresh,_=self.case(instant);dispatch=f.Dispatch(fresh,directory)
            if day in expected:
                docs.authenticate(clock=lambda:instant);assert dispatch.prepare()['status']=='AWAITING_PUBLICATION_NO_SPAWN'
            else:
                assert conformance.refusal(lambda:docs.authenticate(clock=lambda:instant))=='DATE_NOT_IN_SCOPE'
                result=docs.run(conformance.Untouchable(),clock=lambda:instant);assert (result['status'],result['code'])==('REFUSED','DATE_NOT_IN_SCOPE')
                assert conformance.refusal(dispatch.prepare)=='DISPATCH_DATE' and not dispatch.claims()
        instant=conformance.noon(expected[0]);docs.shift(instant,instant+conformance.timedelta(minutes=5))
        for value in (None,20261003,[expected[0]]):
            docs.request['date']=value;docs.chain();assert conformance.refusal(docs.authenticate)=='DATE_NOT_IN_SCOPE'
