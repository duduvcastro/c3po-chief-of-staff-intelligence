"""New T14 Linux proof of the native F6 capsule, with ephemeral fixture keys.

Invoke only in the own Linux proof: python -I -S -B test_crypto_fixture.py
<age> <age-keygen>. No production inputs/credential/key, provider or host.
The private keys/capsules never enter stdout or the uploaded proof artifact.
"""
import io
import os
import platform
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).absolute().parent))
from common import Hold,PinnedDirectory,canonical,digest,need
from runtime import physical
from processes import BoundedProcess
from retention import NativeRetainer,pack,unpack,MAXIMUM

PINS={'age':'eb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c',
      'age-keygen':'0a0009db842259d6717f7eeb30acb6b90d2a2eb924c6acd0a0db0ca1f1537899'}
CTX={'model':'SERVER_EPOCH_V2','epoch':'TEST_F6_CRYPTO_20261012','session':'2026-10-12','lane':'AM','release_sha256':digest(b'FIXTURE release')}
TOOLS={}


class Guard:
    mode='FIXTURE';context=CTX
    def __init__(self):self.value={'spec':{'executables':{name:{'path':path} for name,path in TOOLS.items()}}}
    def recheck(self):
        for name,path in TOOLS.items():
            raw,ident=physical(path,maximum=16*1024*1024,executable=True)
            need(digest(raw)==PINS[name] and ident['mode']==0o500,'CRYPTO_FIXTURE_TOOL_PIN')
        return digest(b'FIXTURE runtime')


class TestCrypto(unittest.TestCase):
    def setUp(self):
        need(platform.system()=='Linux','CRYPTO_LINUX_ONLY')
        self.tmp=tempfile.TemporaryDirectory(prefix='f6-crypto-FIXTURE-',dir=str(Path(tempfile.gettempdir()).resolve()))
        self.base=Path(self.tmp.name);os.chmod(self.base,0o700);self.root=PinnedDirectory(self.base)
        self.guard=Guard();self.runner=BoundedProcess(self.guard)
    def tearDown(self):self.root.close();self.tmp.cleanup()
    def keypair(self,name):
        private=self.runner.run([TOOLS['age-keygen']],limit=4096,seconds=10)
        self.assertEqual(private['returncode'],0);self.assertIn(b'AGE-SECRET-KEY-',private['stdout'])
        self.root.create(name,private['stdout']);path=str(self.base/name)
        result=self.runner.run([TOOLS['age-keygen'],'-y',path],limit=4096,seconds=10)
        self.assertEqual(result['returncode'],0);return path,result['stdout'].decode().strip()
    def original_set(self):
        return {role:{'raw':canonical({'schema':'FIXTURE_'+role.upper(),'context':CTX,'not_human_authority':True,
                                      'body':('x'*300000 if role=='request' else 'own original')})}
                for role in ('request','question','owner','bound','review','authority')}
    def test_t14_native_retainer_actual_cipher_roundtrip_preserves_all_original_bytes(self):
        key,recipient=self.keypair('own.key');originals=self.original_set();result=canonical({'schema':'FIXTURE_RESULT','context':CTX})
        authority=digest(b'FIXTURE own retention authority');retainer=NativeRetainer(self.guard,self.runner,self.root,{'recipient':recipient,'authority_sha256':authority})
        receipt=retainer.retain(result,originals,{'pins':{'retention_authority_sha256':authority}},recheck=self.guard.recheck)
        cipher=self.root.read(digest(result)+'.age',pin=receipt['cipher_sha256'],limit=MAXIMUM+65536,modes=(0o600,))
        decrypted=self.runner.run([TOOLS['age'],'--decrypt','--identity',key],stdin=cipher,limit=MAXIMUM,seconds=20)
        self.assertEqual(decrypted['returncode'],0);expected={k+'.json':v['raw'] for k,v in originals.items()};expected['RESULT.json']=result
        self.assertEqual(unpack(decrypted['stdout']),expected);self.assertFalse(receipt['plaintext_posted'] or receipt['signature_generated'])
    def test_t14_wrong_recipient_or_damaged_cipher_never_yields_verified_capsule(self):
        key,recipient=self.keypair('own.key');other,unused=self.keypair('other.key')
        plain,_=pack({'RESULT.json':canonical({'fixture':True})})
        result=self.runner.run([TOOLS['age'],'--encrypt','--recipient',recipient],stdin=plain,limit=MAXIMUM+65536,seconds=20)
        self.assertEqual(result['returncode'],0)
        for chosen,cipher in ((other,result['stdout']),(key,result['stdout'][:-30])):
            decoded=self.runner.run([TOOLS['age'],'--decrypt','--identity',chosen],stdin=cipher,limit=MAXIMUM,seconds=20)
            self.assertNotEqual(decoded['returncode'],0)
    def test_t14_cipher_deadline_output_limit_no_complete_evidence(self):
        _,recipient=self.keypair('own.key');plain,_=pack({'RESULT.json':b'x'*300000})
        with self.assertRaisesRegex(Hold,'PROCESS_OUTPUT_LIMIT'):self.runner.run([TOOLS['age'],'--encrypt','--recipient',recipient],stdin=plain,limit=32,seconds=20)
        with self.assertRaisesRegex(Hold,'PROCESS_TIMEOUT'):self.runner.run([TOOLS['age'],'--encrypt','--recipient',recipient],stdin=plain,limit=MAXIMUM+65536,seconds=1e-9)
    def test_t14_private_duplicate_cipher_name_is_not_overwritten_or_retried(self):
        _,recipient=self.keypair('own.key');result=canonical({'fixture':True});name=digest(result)+'.age'
        self.root.create(name,b'FIXTURE retained old outcome')
        authority=digest(b'fixture retention');retainer=NativeRetainer(self.guard,self.runner,self.root,{'recipient':recipient,'authority_sha256':authority})
        with self.assertRaises(FileExistsError):retainer.retain(result,{'request':{'raw':b'FIXTURE original'}},
              {'pins':{'retention_authority_sha256':authority}},recheck=self.guard.recheck)
        self.assertEqual(self.root.read(name,modes=(0o600,)),b'FIXTURE retained old outcome')


if __name__=='__main__':
    need(len(sys.argv)==3,'CRYPTO_FIXED_TOOL_ARGUMENTS');TOOLS.update(age=str(Path(sys.argv[1]).absolute()),**{'age-keygen':str(Path(sys.argv[2]).absolute())})
    output=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromTestCase(TestCrypto)
    result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
    record={'schema':'F6_NATIVE_CAPSULE_LINUX_CRYPTO_FIXTURE_RESULT_V2','mode':'FIXTURE','status':'PASS' if result.wasSuccessful() else 'FAIL',
        'test_count':result.testsRun,'failure_count':len(result.failures),'error_count':len(result.errors),'tool_sha256':PINS,
        'private_keys_or_bodies_uploaded':False,'production_host_operated':False,'operational_GO':False}
    print(canonical(record).decode(),end='');sys.exit(0 if result.wasSuccessful() else 2)
