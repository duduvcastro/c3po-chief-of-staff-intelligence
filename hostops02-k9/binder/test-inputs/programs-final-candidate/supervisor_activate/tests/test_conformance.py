"""The family's conformance suite (121 tests) applied to K5, once per signed mode: the bound fixture of mode ACTIVATE
and the bound fixture of mode RESET (after a complete ACTIVATE) are two different requests of the same source."""
import json

import conformance
import family as f
import hostemu
import k5

class TestActivate(conformance.Conformance):
    DIRECTORY=k5.DIRECTORY
    OTHERS=(k5.DIRECTORY.parent/'db_preflight',)
    @staticmethod
    def case(now=None):return k5.case(now,'ACTIVATE')

class TestReset(conformance.Conformance):
    DIRECTORY=k5.DIRECTORY
    OTHERS=(k5.DIRECTORY.parent/'db_preflight',)
    @staticmethod
    def case(now=None):return k5.case(now,'RESET')
    def test_bound_fixture_completes_and_the_reviewed_transport_accepts_the_sealed_receipt(self):
        """The suite's test compares the outcome with COMPLETE_OUTCOME, the success of mode ACTIVATE. A RESET succeeds with
        its own outcome, the one success_of() gives its plan and its GO carries; everything else is asserted unchanged."""
        k,docs,host=self.one();m=k.m;receipt=docs.run(host)
        assert m.success_of(docs.plan)==m.RESET_COMPLETE_OUTCOME!=m.COMPLETE_OUTCOME and docs.go['success_criterion']==m.RESET_COMPLETE_OUTCOME
        assert receipt['status']==m.COMPLETE_STATUS and receipt['outcome']==m.RESET_COMPLETE_OUTCOME and receipt['code'] is None and f.sealed(receipt)
        assert receipt['schema']==m.RECEIPT_SCHEMA and receipt['operation']==m.OPERATION and receipt['scope_sha256']==m.SCOPE_SHA256
        assert receipt['core_sha256']==m.CORE_SHA256==f.assembler().core_sha256()
        assert (receipt['request_sha256'],receipt['authority_sha256'],receipt['go_sha256'],receipt['payload_sha256'])==(
            docs.pins().request,docs.pins().authority,docs.pins().go,f.sha(k.source)) and receipt['host_binding_sha256']==f.HOST
        assert receipt['ready'] is False and receipt['secret_bytes_in_receipt'] is False
        assert receipt['activation_performed'] is False and receipt['daemon_reload_performed'] is False
        assert receipt['size_reductions']==[] and len(f.line(receipt))<=m.RECEIPT_LIMIT+m.SEAL_OVERHEAD
        assert m.canonical(receipt['effects'])==m.canonical(docs.go['effects'])
        assert hostemu.SECRET.encode() not in f.line(receipt) and b'never-emit' not in f.line(receipt)
        value=json.loads(f.line(receipt));claimed=value.pop('metadata_sha256');assert f.sha(f.canonical(value))==claimed
