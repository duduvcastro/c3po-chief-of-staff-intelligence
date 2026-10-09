"""Only new S2/session-window delta methods; no earlier methods are run."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import image_path_adapter as a
from test_phase_delta import fixture, OPEN


class SessionWindowDeltaTests(unittest.TestCase):
    def setUp(self):
        self.parts = fixture()
        self.window = dict(not_before=OPEN - timedelta(seconds=90),
                           not_after=OPEN + timedelta(minutes=5),
                           session_close=OPEN + timedelta(hours=6, minutes=30))

    def gate(self, at, parts=None, **changed):
        return a.reader_gate(*(parts or self.parts), now=at, **dict(self.window, **changed))

    def assertHold(self, code, callback):
        with self.assertRaises(a.Hold) as error:
            callback()
        self.assertEqual(error.exception.args, (code,))

    def test_exact_open_minus_ten_seconds_ready_is_accepted_in_own_window(self):
        result = self.gate(OPEN - timedelta(seconds=10))
        self.assertEqual(result['status'], 'READER_PREREQUISITE_BYTES_RECONCILED')
        self.assertNotIn('before_open_ten_seconds', result)
        self.assertFalse(result['session_binding_copied'])

    def test_source_retry_ready_after_open_is_accepted_without_bypassing_evidence(self):
        result = self.gate(OPEN + timedelta(seconds=32))
        self.assertEqual(result['observed_at'], (OPEN + timedelta(seconds=32)).isoformat())
        parts = list(self.parts)
        ready = parts[5]
        parts[5] = replace(ready, raw=a.canonical({'epoch': parts[0].epoch, 'session':'2026-10-13'}))
        self.assertHold('READER_READY_MISMATCH', lambda: self.gate(OPEN + timedelta(seconds=32), parts=parts))

    def test_own_authority_window_and_calendar_cannot_be_extended_or_wrong_day(self):
        self.assertHold('READER_SESSION_WINDOW_CLOSED', lambda: self.gate(self.window['not_after']))
        self.assertHold('READER_SESSION_WINDOW_CLOSED', lambda: self.gate(self.window['not_before'] - timedelta(microseconds=1)))
        self.assertHold('READER_SESSION_WINDOW_CLOSED', lambda: self.gate(OPEN + timedelta(days=1)))
        self.assertHold('READER_SESSION_EFFECT_WINDOW_INVALID', lambda: self.gate(
              OPEN, not_before=OPEN - timedelta(seconds=91)))
        self.assertHold('READER_SESSION_EFFECT_WINDOW_INVALID', lambda: self.gate(
              OPEN, not_after=self.window['session_close'] + timedelta(minutes=20, microseconds=1)))
        self.assertHold('READER_SESSION_EFFECT_WINDOW_INVALID', lambda: self.gate(
              OPEN, session_close=OPEN + timedelta(days=1)))

    def test_window_is_mandatory_and_writer_scope_window_is_not_reused(self):
        with self.assertRaises(TypeError):
            a.reader_gate(*self.parts, now=OPEN)
        self.assertGreater(OPEN, self.parts[0].not_after)
        self.gate(OPEN)
        self.assertHold('READER_SESSION_EFFECT_WINDOW_INVALID', lambda: self.gate(
              OPEN, not_before=self.parts[0].not_before, not_after=self.parts[0].not_after))


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(
                   unittest.defaultTestLoader.loadTestsFromTestCase(SessionWindowDeltaTests))
    (ROOT/'SESSION_DELTA_RESULT.json').write_bytes(a.canonical({
        'schema':'CODEX_SESSION_WINDOW_DELTA_RESULT_V1','methods':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'earlier_methods_repeated':0,
        'source_sha256':a.sha((ROOT/'image_path_adapter.py').read_bytes()),
        'scope':'NEW_SYNTHETIC_SESSION_WINDOW_ONLY','app_imports':0,'host_operations':0,'db_queries':0})+b'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
