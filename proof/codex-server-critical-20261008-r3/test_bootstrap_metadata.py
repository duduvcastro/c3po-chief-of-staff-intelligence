"""Regression of Linux read-induced atime, without weakening content guards.

All files are new private fixtures; no real installation/service/writer effect.
Four verifiers are called before any adapter import. Simulated atime and nine
stable-field adversaries prove the exact comparison independently of the OS.
"""
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).absolute().parent
FIELDS=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')


class Proxy:
    def __init__(self,original,delta,changed=None):self.original,self.delta,self.changed=original,delta,changed
    def __getattr__(self,name):
        value=getattr(self.original,name)
        if name in ('st_atime','st_atime_ns'):return value+self.delta
        if name==self.changed:return value+1
        return value
    def __eq__(self,other):
        return isinstance(other,Proxy) and self.delta==other.delta and self.changed==other.changed and self.original==other.original


class TestBootstrapMetadata(unittest.TestCase):
    def invoke(self,entry,changed=None):
        with tempfile.TemporaryDirectory(prefix='f6-relatime-FIXTURE-',dir=str(Path(tempfile.gettempdir()).resolve())) as tmp:
            root=Path(tmp);os.chmod(root,0o700)
            names=(entry,'fixture.py','k12_reader_reference.py','K12_READER_ORIGIN.json')
            bodies={n:(b'# own explicit fixture\n' if n=='fixture.py' else (ROOT/n).read_bytes()) for n in names}
            for name,raw in bodies.items():(root/name).write_bytes(raw);os.chmod(root/name,0o444)
            manifest={'files':[{'name':n,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in bodies.items()]}
            raw=(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n').encode();mp=root/'MANIFEST.json';mp.write_bytes(raw);os.chmod(mp,0o444)
            spec=importlib.util.spec_from_file_location('fixture_bootstrap_'+entry.replace('.','_'),root/entry)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            original=Path.lstat;calls={}
            def access(path,*args,**kw):
                value=original(path,*args,**kw);key=str(path);calls[key]=calls.get(key,0)+1
                # Kernel relatime updates atime without mtime/ctime changes.
                field=changed if path==mp and calls[key]>1 else None
                return Proxy(value,calls[key],field)
            with patch.object(Path,'lstat',access):
                if entry=='PROVA.py':return module.verify()
                if entry=='service.py':return module.source_manifest(hashlib.sha256(raw).hexdigest())
                return module.verified_source(hashlib.sha256(raw).hexdigest())
    def test_t05_t08_all_four_bootstraps_allow_only_read_induced_atime(self):
        for entry in ('PROVA.py','service.py','install_main.py','writer_main.py'):
            with self.subTest(entry=entry):self.invoke(entry)
    def test_t05_t08_every_stable_identity_content_field_still_rejects(self):
        for entry in ('PROVA.py','service.py','install_main.py','writer_main.py'):
            for field in FIELDS:
                with self.subTest(entry=entry,field=field):
                    with self.assertRaises(ValueError):self.invoke(entry,field)
