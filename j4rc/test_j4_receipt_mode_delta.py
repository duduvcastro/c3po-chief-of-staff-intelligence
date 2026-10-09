"""Only new parent-requested exact mode/terminal/original boundary vectors."""
import json,time,unittest
from unittest.mock import patch
from datetime import timedelta
import finite_batch as c
import j4_receipt_adapter as d
from test_j4_receipt_codec import Fixture,encoded

class NewExactModeDelta(unittest.TestCase):
    def test_monday_original_published_time_survives_general_refresh_after_link(self):
        f=Fixture();f.general.update(observed_at='2026-10-12T10:45:07Z',valid_until='2026-10-12T10:45:12Z')
        f.process['general_observation_base64']=encoded(c.canonical(f.general))
        result=f.decode()
        self.assertEqual(result.linked_receipt.completed_at,d.instant('2026-10-12T10:45:05Z'))
        self.assertEqual(result.writer_raw,c.canonical(f.writer)+b'\n')
    def test_bool_false_is_not_writer_exit_int_zero(self):
        f=Fixture();f.slot['writer_exit_code']=False
        with self.assertRaisesRegex(c.Hold,'J4_SLOT_NOT_COMPLETE'):f.decode()
    def test_claim_of_operational_go_is_not_source_protocol(self):
        f=Fixture();f.slot['operational_GO']=True
        with self.assertRaisesRegex(c.Hold,'J4_SLOT_NOT_COMPLETE'):f.decode()
    def test_uncommitted_family_terminal_cannot_supply_published_writer(self):
        f=Fixture();f.slot['code']='J_TERMINAL_LEDGER_UNVERIFIED'
        with self.assertRaisesRegex(c.Hold,'J4_SLOT_NOT_COMPLETE'):f.decode()
    def test_slot_fixture_mode_cannot_be_relabelled_real(self):
        f=Fixture();f.slot['mode']='REAL'
        with self.assertRaisesRegex(c.Hold,'J4_SLOT_NOT_COMPLETE'):f.decode()
    def test_original_verifier_cannot_rewrite_parsed_config_pin(self):
        f=Fixture()
        def corrupt(*args):args[7]['capacity_config_sha256']=c.sha(b'foreign-config')
        f.original_callback=corrupt
        with self.assertRaisesRegex(c.Hold,'J4_VERIFIER_CHANGED_ORIGINALS'):f.decode()
    def test_sunday_clock_cannot_be_relabelled_monday_j(self):
        f=Fixture()
        # Context/day stay Monday; all claimed clocks move to Sunday. This is
        # not execution evidence and must fail before the original verifier.
        f.before=f.before.replace('2026-10-12','2026-10-11');f.after=f.after.replace('2026-10-12','2026-10-11')
        f.q['tasks'][0].update(not_before=f.before,not_after=f.after)
        f.request=c.canonical(f.q);f.bound=c.canonical({'schema':'SYNTHETIC_BOUND_NOT_SIGNED','request':c.sha(f.request)})
        f.registry.update(not_before=f.before,not_after=f.after)
        f.registry['originals']['request']['sha256']=c.sha(f.request);f.registry['originals']['bound']['sha256']=c.sha(f.bound)
        f.registry_raw=c.canonical(f.registry)
        f.rule.update(invocation_request_sha256=c.sha(f.request),invocation_bound_sha256=c.sha(f.bound),phase_not_before=f.before,phase_not_after=f.after)
        f.process.update(request_sha256=c.sha(f.request),bound_sha256=c.sha(f.bound),registry_sha256=c.sha(f.registry_raw))
        for key in ('warm_at','image_observed_at','image_valid_until'):f.process[key]=f.process[key].replace('2026-10-12','2026-10-11')
        for key in ('cutoff_at','published_at'):f.writer[key]=f.writer[key].replace('2026-10-12','2026-10-11')
        f.writer['view']={k:v.replace('2026-10-12','2026-10-11')for k,v in f.writer['view'].items()}
        f.writer['window']={'not_before':f.before,'not_after':f.after}
        f.now-=timedelta(days=1)
        f.invocation=c.Invocation('admission_manifest',c.context(f.q),c.sha(f.request),c.sha(f.bound),f.now+timedelta(minutes=1),time.monotonic()+30,())
        with self.assertRaisesRegex(c.Hold,'J4_WRITER_ORIGINAL_CLOCK_UNBOUND'):f.decode()

if __name__=='__main__':unittest.main()
