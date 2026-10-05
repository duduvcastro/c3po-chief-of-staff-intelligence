"""The family's conformance suite (121 tests) applied to DBR, once per signed mode: the bound fixture of mode QUERIES and
the bound fixture of mode PRIV are two different requests of the same source."""
import json

import conformance
import dbr
import family as f
import hostemu

class TestConformance(conformance.Conformance):
    DIRECTORY=dbr.DIRECTORY
    OTHERS=(dbr.DIRECTORY.parent/'supervisor_activate',)
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


class TestPriv(conformance.Conformance):
    DIRECTORY=dbr.DIRECTORY
    OTHERS=(dbr.DIRECTORY.parent/'supervisor_activate',)
    @staticmethod
    def case(now=None):return dbr.case(now,mode='PRIV')
    def test_bound_fixture_completes_and_the_reviewed_transport_accepts_the_sealed_receipt(self):
        """The suite's test compares the outcome with COMPLETE_OUTCOME, the success of mode QUERIES. PRIV succeeds with its
        own outcome, the one success_of() gives its plan and its GO carries; everything else is asserted unchanged."""
        k,docs,host=self.one();m=k.m;before=conformance.engine_state(host);receipt=docs.run(host)
        assert m.success_of(docs.plan)==m.PRIV_COMPLETE_OUTCOME!=m.COMPLETE_OUTCOME and docs.go['success_criterion']==m.PRIV_COMPLETE_OUTCOME
        assert receipt['status']==m.COMPLETE_STATUS and receipt['outcome']==m.PRIV_COMPLETE_OUTCOME and receipt['code'] is None and f.sealed(receipt)
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
