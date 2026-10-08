"""New data-only entry tests; own private originals are explicit fixtures."""
import os
import pwd
import unittest
import test_real_adapters as adapter_fixtures
from common import Hold,canonical,digest,strict
from install_main import acceptance_input,unit_packet


class TestAssemblyEntry(unittest.TestCase):
    def setUp(self):
        self.f=adapter_fixtures.TestAdapters();self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def input(self,args):
        roles=('spec','measurement','prepared','definition');refs={}
        for role,body in zip(roles,(args[0],args[1],args[2],args[4])):
            path=self.f.file(role+'-entry.json',body)
            refs[role]={'path':str(path),'sha256':digest(body)}
        return canonical({'schema':'SERVER_ACCEPTANCE_INPUT_V2','inputs':refs,'channel':{}})
    def test_t05_t13_entry_assembles_original_acceptance_and_units_without_activation(self):
        args,channel,source=self.f.acceptance()
        body=acceptance_input(self.input(args),args[3],channel=channel,clock=lambda:'2026-10-11T23:08:00Z',fixture=True)
        path=self.f.file('own-entry-acceptance.json',body)
        data=canonical({'schema':'SERVER_UNIT_INPUT_V2','acceptance':{'path':str(path),'sha256':digest(body)},
              'source_root':'/fixture/source','executor_user':pwd.getpwuid(os.geteuid()).pw_name})
        packet=unit_packet(data,digest(args[3]),fixture=True)
        self.assertEqual(len(packet['units']),2);self.assertEqual(packet['timers_installed'],0)
        self.assertFalse(packet['operational_GO']);self.assertNotIn('signature',packet)
    def test_t05_t16_entry_changed_private_pin_or_fixture_in_real_path_is_refused(self):
        args,channel,source=self.f.acceptance();raw=self.input(args)
        with self.assertRaisesRegex(Hold,'ACCEPT_INPUT_RUNTIME'):
            acceptance_input(raw,args[3],channel=channel,clock=lambda:'2026-10-11T23:08:00Z')
        value=strict(raw);value['inputs']['prepared']['sha256']=digest(b'wrong own bytes')
        with self.assertRaisesRegex(Hold,'ACCEPT_INPUT_PIN'):
            acceptance_input(canonical(value),args[3],channel=channel,clock=lambda:'2026-10-11T23:08:00Z',fixture=True)
