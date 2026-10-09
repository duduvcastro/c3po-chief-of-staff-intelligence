"""New exact transport framing beyond the conserved26+4 vectors."""
import unittest
from unittest.mock import patch
import finite_batch as c
import j4_receipt_adapter as d
from test_j4_receipt_codec import Fixture,encoded

class NewStdoutDelta(unittest.TestCase):
    def test_child_print_exact_single_lf_is_preserved(self):
        f=Fixture();raw=f.stdout()
        with patch.object(d,'native_utc',return_value=f.now):
            out=f.adapter().decode(raw,f.invocation,config_raw=f.config)
        self.assertEqual(out.core_receipt.raw,raw)
        self.assertEqual(out.writer_raw,c.canonical(f.writer)+b'\n')
    def test_truncated_stdout_without_print_lf_is_refused(self):
        f=Fixture()
        with patch.object(d,'native_utc',return_value=f.now):
            with self.assertRaisesRegex(c.Hold,'J4_PROCESS_STDOUT_INVALID'):f.adapter().decode(f.stdout()[:-1],f.invocation,config_raw=f.config)
    def test_missing_writer_raw_has_no_hash_only_fallback(self):
        f=Fixture();f.stdout();f.slot['writer_receipt_base64']=None
        with patch.object(d,'native_utc',return_value=f.now):
            with self.assertRaisesRegex(c.Hold,'J4_WRITER_ORIGINAL_INVALID'):f.adapter().decode(c.canonical(f.process)+b'\n',f.invocation,config_raw=f.config)
    def test_duplicate_writer_json_key_is_refused(self):
        f=Fixture();f.stdout();raw=b'{"mode":"PUBLISH",'+c.canonical(f.writer)[1:]+b'\n'
        f.slot['writer_receipt_base64'],f.slot['writer_receipt_sha256']=encoded(raw),c.sha(raw)
        with patch.object(d,'native_utc',return_value=f.now):
            with self.assertRaisesRegex(c.Hold,'JSON_DUPLICATE_KEY'):f.adapter().decode(c.canonical(f.process)+b'\n',f.invocation,config_raw=f.config)

if __name__=='__main__':unittest.main()
