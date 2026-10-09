"""R3 serialization defect tests only; no REAL authority or epoch04 original."""
from pathlib import Path
import hashlib
import json
import unittest
import config_finalizer as f
import veto_emitter as v
from fixture_builder_r3 import FixtureBuilder


class MachineOrderNoLFDelta(unittest.TestCase):
    def test_actual_historical_original_has_exact_no_lf_abi(self):
        raw=(Path(__file__).parent/'originals/ORDER.RUNTIME.epoch03.HISTORICAL.json').read_bytes()
        self.assertEqual(len(raw),220)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'518627919754f795ff551c9d833a3b1000fb930b555df647e7e00e2b19e775fe')
        self.assertFalse(raw.endswith(b'\n'))
        value=f.parse_machine_order(raw)
        self.assertEqual(set(value),{'authorized_sessions','capacity','epoch','owner_sha'})
        self.assertEqual(v.canonical(value),raw)
        # Historical acceptance of bytes is not epoch04 authority or scope.
        self.assertNotEqual(value['epoch'],f.EPOCH)

    def test_synthetic_epoch04_same_shape_finalizes_no_lf_and_preserves_originals(self):
        x=FixtureBuilder();x.setUp()
        self.assertFalse(x.order_raw.endswith(b'\n'))
        self.assertEqual(x.machine_sha,v.digest(x.order_raw))
        self.assertEqual(len({x.machine_sha,x.runtime_sha,x.markdown_sha}),3)
        out=x.finalize()
        self.assertFalse(out.operational_GO);self.assertFalse(out.installed)
        self.assertEqual(out.mode,'FIXTURE')
        self.assertEqual(len(x.calls),2)
        for call in x.calls:self.assertEqual(call[6:8],(x.act_raw,x.order_raw))

    def test_lf_appended_and_pretty_serializations_are_refused(self):
        x=FixtureBuilder();x.setUp()
        for raw in (x.order_raw+b'\n',json.dumps(x.order,sort_keys=True,indent=2).encode()):
            with self.subTest(raw=raw[:25]):
                with self.assertRaisesRegex(f.Refused,'^CONFIG_MACHINE_ORDER_CANONICAL$'):
                    f.parse_machine_order(raw)

    def test_duplicate_fields_are_refused_without_reserialization(self):
        with self.assertRaisesRegex(f.Refused,'^CONFIG_MACHINE_ORDER_DUPLICATE$'):
            f.parse_machine_order(b'{"capacity":550,"capacity":550}')

    def test_nonfinite_values_including_exponent_overflow_are_refused(self):
        for token in (b'NaN',b'Infinity',b'-Infinity',b'1e9999'):
            with self.subTest(token=token):
                with self.assertRaisesRegex(f.Refused,'^CONFIG_MACHINE_ORDER_INVALID$'):
                    f.parse_machine_order(b'{"capacity":'+token+b'}')

    def test_raw_original_pin_detects_lf_change_before_external_callbacks(self):
        x=FixtureBuilder();x.setUp()
        with self.assertRaisesRegex(f.Refused,'^CONFIG_MACHINE_ORDER_ORIGINAL_HASH$'):
            x.finalize(machine_order_raw=x.order_raw+b'\n')
        self.assertEqual(x.calls,[])

    def test_runtime_as_veto_machine_context_still_refuses(self):
        x=FixtureBuilder();x.setUp()
        vs=dict(x.vspec,context=dict(x.vspec['context'],order_sha=x.runtime_sha))
        raw=v.canonical(vs)+b'\n';spec=dict(x.spec,veto_spec_sha256=v.digest(raw))
        sr=v.canonical(spec)+b'\n'
        with self.assertRaisesRegex(f.Refused,'^CONFIG_VETO_MACHINE_ORDER_CONTEXT$'):
            x.finalize(veto_spec_raw=raw,spec_raw=sr,spec_sha256=v.digest(sr))
        self.assertEqual(x.calls,[])


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MachineOrderNoLFDelta))
    row={'schema':'CODEX_CONFIG_FINALIZER_R3_MACHINE_ORDER_NO_LF_DELTA_RESULT_V1','new_tests':result.testsRun,
         'failures':len(result.failures),'errors':len(result.errors),'previous_29_and_13_repeated':False,
         'real_epoch04_originals':0,'historical_originals':1,'mode':'FIXTURE','host_operations':0,'operational_GO':False}
    (Path(__file__).parent/'LOCAL_DELTA_RESULT.json').write_bytes(v.canonical(row)+b'\n')
    raise SystemExit(0 if result.wasSuccessful()else 1)
