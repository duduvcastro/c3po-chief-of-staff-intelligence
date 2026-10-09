"""Only new guards beyond the conserved first26 vectors."""
from datetime import timedelta
import time
import unittest
from unittest.mock import patch
import finite_batch as c
import j4_receipt_adapter as d
from test_j4_receipt_codec import Fixture

class NewFinalDelta(unittest.TestCase):
    def test_original_image_symbol_cap_550_accepted(self):
        f=Fixture();f.writer['symbol_count']=550
        self.assertEqual(f.decode().linked_receipt.status,'COMPLETE')
    def test_above_original_image_symbol_cap_refused(self):
        f=Fixture();f.writer['symbol_count']=551
        with self.assertRaisesRegex(c.Hold,'J4_WRITER_COUNTS_UNVERIFIED'):f.decode()
    def test_decoder_beyond_phase_rejects_wide_invocation_deadline(self):
        f=Fixture();f.now=d.instant(f.after)
        f.invocation=c.Invocation('admission_manifest',c.context(f.q),c.sha(f.request),c.sha(f.bound),f.now+timedelta(minutes=1),time.monotonic()+30,())
        with self.assertRaisesRegex(c.Hold,'J4_DECODE_OUTSIDE_PHASE'):f.decode()
    def test_callback_crossing_phase_refused_before_linked_receipt(self):
        f=Fixture()
        def late(*args):f.now=d.instant(f.after)
        f.original_callback=late
        f.invocation=c.Invocation('admission_manifest',c.context(f.q),c.sha(f.request),c.sha(f.bound),d.instant(f.after)+timedelta(minutes=1),time.monotonic()+30,())
        with patch.object(d,'native_utc',side_effect=lambda:f.now):
            with self.assertRaisesRegex(c.Hold,'J4_DECODE_OUTSIDE_PHASE'):f.adapter().decode(f.stdout(),f.invocation,config_raw=f.config)

if __name__=='__main__':unittest.main()
