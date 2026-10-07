"""New orchestration policy only; fake actor/clock, audit forbids network/children."""
import copy
import datetime as dt
import hashlib
import json
import pathlib
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import session_policy as m
import capture_checked_binder as guard

COUNT = 0
PIN = 'a'*64
class Adapter:
    def __init__(self):
        self.clock = m.instant('2026-10-08T11:45:00Z')
        self.context = dict(session=m.SESSION, run_id='12345678', run_attempt=1, nonce='b'*32)
        self.sheets = {}; self.sent = []; self.prepared = []; self.published = {}
        self.fail = None; self.branch = 'PRIMARY'; self.runtime = True
    def identity(self): return self.context
    def now(self): return self.clock
    def wait_until(self, text): self.clock = max(self.clock, m.instant(text))
    def verify_authority_runtime(self, current):
        m.need(self.runtime, 'FIXTURE_RUNTIME_REFUSAL')
    def challenge(self, current):
        self.wait_until('2026-10-08T11:54:00Z')
        return dict(current, verified=self.fail != 'transport', status='KNOWN_COMPLETE', remote_uid=0,
                    attempts=1, retry=False, remote_command='sudo -n /usr/bin/python3 -I -B -',
                    no_host_file_access=True, config_sha256=PIN, receipt_sha256=PIN)
    def prepare_sign_review(self, op, current, transport):
        self.prepared.append(op)
        self.sheets[op] = dict(current, operation=op, signature_model='PRE', slot='PRIMARY', signed=True,
            own_owner_record_verified=True, bound_review_verified=True, not_before=m.WINDOWS[op][0],
            not_after=m.WINDOWS[op][1], answered_at_utc='2026-10-08T11:54:00Z',
            observed_at_utc='2026-10-08T11:54:01Z', sheet_sha256=PIN, request_sha256=PIN,
            payload_sha256=PIN, config_sha256=PIN, owner_packet_sha256=PIN, host_binding_sha256=PIN)
        if self.fail == 'owner': self.sheets[op]['observed_at_utc'] = '2026-10-08T12:30:01Z'
        if self.fail == 'review': self.sheets[op]['bound_review_verified'] = False
        return self.sheets[op]
    def snapshot(self, op):
        value = copy.deepcopy(self.sheets[op])
        if self.fail == 'changed': value['request_sha256'] = 'c'*64
        return value
    def night_branch(self): return self.branch
    def prerequisite(self, op, branch):
        value = dict(verified=True, status='KNOWN_COMPLETE', outcome='COMPLETE', success_criterion='COMPLETE',
                     day=m.SESSION, grid='G19', k9_operation=op, slot=branch, host_binding_sha256=PIN,
                     request_sha256=PIN, payload_sha256=PIN, receipt_sha256=PIN)
        if self.fail == 'night': value['status'] = 'KNOWN_PARTIAL'
        if self.fail == 'old_day': value['day'] = '2026-10-07'
        if self.fail == 'wrong_host': value['host_binding_sha256'] = 'c'*64
        if self.fail == 'gate_changes' and 'capture_launch' in self.published: value['verified'] = False
        return value
    def check(self, op, stage):
        m.need(self.fail != stage, 'FIXTURE_REAL_CHECK_REFUSAL')
    def prepare_publish(self, op):
        self.published[op] = self.now()
        return dict(comment_id=100, readback_exact=self.fail != 'publication', attempts=1,
                    created_at=self.now().strftime('%Y-%m-%dT%H:%M:%SZ'))
    def resume_once(self, op):
        m.need(self.now() >= self.published[op]+dt.timedelta(seconds=120), 'FIXTURE_TOO_EARLY')
        m.need(op not in self.sent, 'FIXTURE_RETRY')
        self.sent.append(op)
    def status(self, op):
        return dict(verified=True, status='KNOWN_PARTIAL' if self.fail == 'result' else 'KNOWN_COMPLETE',
                    outcome='COMPLETE', success_criterion='COMPLETE', config_sha256=PIN)

class Tests(unittest.TestCase):
    def run_flow(self, actor):
        global COUNT; COUNT += 1
        return m.run(actor)
    def test_primary_and_spare_complete_order_with_delay(self):
        for branch in ('PRIMARY', 'SPARE'):
            a = Adapter(); a.branch = branch
            self.assertEqual(self.run_flow(a)['completed'], list(m.OPERATIONS))
            self.assertEqual(a.sent, list(m.OPERATIONS))
    def test_run_attempt_and_day_refused_before_challenge(self):
        for key, value in [('run_attempt', 2), ('session', '2026-10-09'), ('nonce', 'x')]:
            a = Adapter(); a.context[key] = value
            with self.assertRaises(m.Refused): self.run_flow(a)
            self.assertFalse(a.prepared); self.assertFalse(a.sent)
    def test_missing_runtime_and_transport_stop_before_four_prepares(self):
        for mode in ('runtime', 'transport'):
            a = Adapter(); a.runtime = mode != 'runtime'; a.fail = mode
            with self.assertRaises(m.Refused): self.run_flow(a)
            self.assertFalse(a.prepared); self.assertFalse(a.sent)
    def test_owner_late_and_missing_bound_review_refuse(self):
        for mode in ('owner', 'review'):
            a = Adapter(); a.fail = mode
            with self.assertRaises(m.Refused): self.run_flow(a)
            self.assertFalse(a.sent)
    def test_no_edit_to_signed_request(self):
        a = Adapter(); a.fail = 'changed'
        with self.assertRaises(m.Refused): self.run_flow(a)
        self.assertFalse(a.sent)
    def test_partial_wrong_day_host_night_never_send_capture(self):
        for mode in ('night', 'old_day', 'wrong_host'):
            a = Adapter(); a.fail = mode
            with self.assertRaises(m.Refused): self.run_flow(a)
            self.assertEqual(a.sent, ['policy_read'])
    def test_missing_branch_never_send_capture(self):
        a = Adapter(); a.branch = None
        with self.assertRaises(m.Refused): self.run_flow(a)
        self.assertEqual(a.sent, ['policy_read'])
    def test_check_refuses_before_prepare_or_resume(self):
        for stage in ('prepare', 'resume'):
            a = Adapter(); a.fail = stage
            with self.assertRaises(m.Refused): self.run_flow(a)
            self.assertFalse(a.sent)
    def test_publication_readback_failure_never_resumes(self):
        a = Adapter(); a.fail = 'publication'
        with self.assertRaises(m.Refused): self.run_flow(a)
        self.assertFalse(a.sent)
    def test_incomplete_or_uncertain_result_stops_remaining_chain(self):
        a = Adapter(); a.fail = 'result'
        with self.assertRaises(m.Refused): self.run_flow(a)
        self.assertEqual(a.sent, ['policy_read'])
    def test_missed_signature_deadline_no_dispatch(self):
        a = Adapter(); original = a.prepare_sign_review
        def late(*args):
            result = original(*args); a.clock = m.instant('2026-10-08T12:30:01Z'); return result
        a.prepare_sign_review = late
        with self.assertRaises(m.Refused): self.run_flow(a)
        self.assertFalse(a.sent)
    def test_changed_prerequisite_before_resume_refused(self):
        a = Adapter(); a.fail = 'gate_changes'
        with self.assertRaises(m.Refused): self.run_flow(a)
        self.assertEqual(a.sent, ['policy_read'])
    def test_runtime_approval_same_day_job_not_measured_self_acceptance(self):
        global COUNT
        raw = dict(schema='CAPTURE_LINUX_RUNTIME_APPROVAL_V2', session=m.SESSION, run_id='12345678', run_attempt=1,
                   verdict='PASS_PHYSICAL_RUNTIME', measurement_sha256=PIN, runtime_guard_sha256=guard.HELPER,
                   binder_sha256=guard.BINDER, accepted_seals_sha256=guard.REGISTRY, review_body_sha256=PIN,
                   dated_authority_sha256=PIN, measured_at_utc='2026-10-08T11:45:00Z', reviewed_at_utc='2026-10-08T11:46:00Z')
        measured=dict(runtime_guard_sha256=guard.HELPER); now=m.instant('2026-10-08T11:47:00Z')
        guard.approval(raw, PIN, measured, now, '12345678'); COUNT += 1
        for key, value in [('run_id','87654321'),('run_attempt',2),('measurement_sha256','c'*64),('session','2026-10-07'),('verdict','MEASURED_NOT_ACCEPTED'),('measured_at_utc','2026-10-07T11:45:00Z')]:
            changed=dict(raw);changed[key]=value;COUNT+=1
            with self.assertRaises(ValueError):guard.approval(changed,PIN,measured,now,'12345678')

if __name__ == '__main__':
    denied=[]
    def audit(event, args):
        if event.startswith(('socket.', 'subprocess.')) or event in ('os.system','os.exec','os.posix_spawn','os.fork'):
            denied.append(event); raise RuntimeError('POLICY_PROOF_NO_NETWORK_CHILD_HOST')
    sys.addaudithook(audit)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    root=pathlib.Path(__file__).resolve().parent
    report=dict(schema='CAPTURE_SESSION_POLICY_PROOF_V1', methods=result.testsRun, scenarios=COUNT,
                failures=len(result.failures),errors=len(result.errors),audit_denials=len(denied),
                source_sha256=m.digest((root/'session_policy.py').read_bytes()),
                guard_sha256=m.digest((root/'capture_checked_binder.py').read_bytes()),
                test_sha256=m.digest(pathlib.Path(__file__).read_bytes()),actual_host_calls=0,
                actual_prepare_sign_dispatch=0,actual_runtime_measurements=0,operational_READY=False)
    (root/'POLICY_TEST_RESULT.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(report));raise SystemExit(0 if result.wasSuccessful() and not denied else 1)
