"""The family's conformance suite (121 tests per fixture) applied to K9R in each of its four modes. RESULT is the mode
whose outcome is COMPLETE_OUTCOME; PROBE, POLICY and TREE complete with their own outcomes, so the one test of the
suite that names the outcome is restated for them with success_of(plan) in the place of the constant, and nothing
else is changed. A fifth fixture runs the suite on a RESULT that collects the packaged risk CLI (acquire_result).
OTHERS: the sibling operations of hostops02 that stand beside this directory (links to the sealed ones), as they are
on disk when the suite runs. A sibling that is not there is not asked (the private copies of a mutation run have none)."""
import json
from pathlib import Path

import conformance
import family as f
import hostemu
import k9r

SIBLINGS=tuple(str(Path(k9r.DIRECTORY).parent/name) for name in ('epoch_readback','install_release','catalog_init','activate')
               if (Path(k9r.DIRECTORY).parent/name/'build'/'ASSEMBLY.json').is_file())

class Restated(conformance.Conformance):
    def test_bound_fixture_completes_and_the_reviewed_transport_accepts_the_sealed_receipt(self):
        k,docs,host=self.one();m=k.m;before=conformance.engine_state(host);receipt=docs.run(host)
        assert m.success_of(docs.plan)==m.K9_SUCCESS[docs.plan['mode']] and docs.go['success_criterion']==m.success_of(docs.plan)
        assert receipt['status']==m.COMPLETE_STATUS and receipt['outcome']==m.success_of(docs.plan) and receipt['code'] is None and f.sealed(receipt)
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

class TestResult(conformance.Conformance):
    DIRECTORY=k9r.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k9r.case('collect_result',now)

class TestResultPackaged(conformance.Conformance):
    DIRECTORY=k9r.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k9r.case('acquire_result',now)

class TestProbe(Restated):
    DIRECTORY=k9r.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k9r.case('readiness_probe',now)

class TestPolicy(Restated):
    DIRECTORY=k9r.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k9r.case('policy_read',now)

class TestTree(Restated):
    DIRECTORY=k9r.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k9r.case('TREE',now)
