"""The family's conformance suite (121 tests per fixture) applied to K9W in each of its modes: LAUNCH (collect_launch,
which creates the day's directories; commit_launch, which also removes the previous exited container), ATTACHED with the
runner (bind) and with the packaged CLI (preflight), and CLEANUP (capture_cleanup). ATTACHED and CLEANUP complete with
their own outcomes, so the one test of the suite that names the outcome is restated for them with success_of(plan) in
the place of the constant; nothing else is changed. OTHERS: the sealed siblings of hostops02 and K9R beside this
directory (links), as they are on disk when the suite runs; one that is not there is not asked."""
import json
from pathlib import Path

import conformance
import family as f
import hostemu
import k9w

SIBLINGS=tuple(str(Path(k9w.DIRECTORY).parent/name) for name in ('epoch_readback','install_release','catalog_init','activate','k9_phase_read')
               if (Path(k9w.DIRECTORY).parent/name/'build'/'ASSEMBLY.json').is_file())

class Restated(conformance.Conformance):
    def test_bound_fixture_completes_and_the_reviewed_transport_accepts_the_sealed_receipt(self):
        k,docs,host=self.one();m=k.m;receipt=docs.run(host)
        assert m.success_of(docs.plan)==m.K9W_SUCCESS[docs.plan['mode']] and docs.go['success_criterion']==m.success_of(docs.plan)
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
        value=json.loads(f.line(receipt));claimed=value.pop('metadata_sha256');assert f.sha(f.canonical(value))==claimed

class TestLaunchCreatesTheDay(conformance.Conformance):
    DIRECTORY=k9w.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k9w.case('collect_launch',now)

class TestLaunchRemovesThePrevious(conformance.Conformance):
    DIRECTORY=k9w.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k9w.case('commit_launch',now)

class TestAttachedRunner(Restated):
    DIRECTORY=k9w.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k9w.case('bind',now)

class TestAttachedPackaged(Restated):
    DIRECTORY=k9w.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k9w.case('preflight',now)

class TestCleanup(Restated):
    DIRECTORY=k9w.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k9w.case('capture_cleanup',now)
