"""Text pins of the capacity probe against the release it is frozen against (dd4ec4bb), the deployment documents it
carries bytes of (opsart: capacity-day/README.documents.md, capacity-mount/README.md) and the frozen core. Every test
here is named "static": the mutation harness deselects them, so a mutant is never killed merely because a pinned text
changed. The release and opsart comparisons run when a tree is at hand and say so when they skip."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import pytest

import family as f
import kprobe

RELEASE_FILES={'c3po/backend/app/r2d2_v2_capacity_anchored.py':'e7e5b48ca890d93b2a5a9d86919f2c6c58e95606f2b0ec62f0afe98e4657163f',
               'c3po/backend/app/r2d2_v2_store.py':'9f9887c267af10c5494ec1a4dd2628b05f74f40dd2bae34e340bf81f00575254',
               'c3po/backend/app/r2d2_v2_capacity_bootstrap.py':'8f7a21dc13ba40d2bca26583ffa8598d40ffd4a8fc0a64ae0331c94b1d11e482',
               'c3po/backend/app/config.py':'91619929a513074f2eee01a6bcd78342305e0066e61ac79f2afd087c2e035897',
               'c3po/backend/app/r2d2_v2_epoch_assembler.py':'8ef584e2dd5d0b41d33f06a00926877573c65b5540f450236910e07ba51ee37c',
               'c3po/backend/Dockerfile':'508636d0bb9cbc81076dfcfeb49cab03f1762c613b740d4a7391faf1a26e8ebf',
               'c3po/compose.yml':'fd214c8e36e47cc88f58e947eebf33c959e81c42929c4ecbb9149f87bdbd499e'}
OPSART_FILES={'c3po/deployment/capacity-day/README.documents.md':'d1628d08ef185e23388abb1ec17a14b1a288222b17ce2b97765fff2c0c1503df',
              'c3po/deployment/capacity-mount/README.md':'1acd72b1d1ba345a52d4226fb0df4f4d9d53f0803aa1635eca67764d9c43474b'}

def tree():
    found=kprobe.release_tree()
    if found is None:pytest.skip('no tree of the release at hand (HOSTOPS02_TEST_RELEASE_TREE or work/release)')
    return found
def opsart():
    candidates=[Path(os.environ['HOSTOPS02_TEST_OPSART_TREE'])] if os.environ.get('HOSTOPS02_TEST_OPSART_TREE') else []
    candidates.append(kprobe.DIRECTORY/'work'/'opsart')
    for candidate in candidates:
        if all((candidate/name).is_file() for name in OPSART_FILES):return candidate
    pytest.skip('no tree of the deployment documents at hand (HOSTOPS02_TEST_OPSART_TREE or work/opsart)')
def text(root,name):return (root/name).read_text()

def test_static_release_files_are_the_pinned_bytes():
    root=tree()
    for name,pin in RELEASE_FILES.items():assert f.sha((root/name).read_bytes())==pin,name

def test_static_documents_are_the_pinned_bytes_and_calendar_pin_py_is_extracted_byte_for_byte():
    root=opsart();m=kprobe.K().m
    for name,pin in OPSART_FILES.items():assert f.sha((root/name).read_bytes())==pin,name
    lines=text(root,'c3po/deployment/capacity-day/README.documents.md').splitlines()
    begin=lines.index('<!-- calendar-pin-script:begin -->');end=lines.index('<!-- calendar-pin-script:end -->')
    assert lines[begin+1]=='```python' and lines[end-1]=='```'
    script=''.join(line+'\n' for line in lines[begin+2:end-1]).encode()
    assert hashlib.sha256(script).hexdigest()=='5a6066ae2925453a0def335d8f8ac7e802e149b56cf9e61ea3fe8843fe582b5f'==m.CALENDAR_SCRIPT_SHA256
    assert script==m.scripts()['CALENDAR'] and len(script)==m.CALENDAR_SCRIPT_BYTES==876
    readme=text(root,'c3po/deployment/capacity-day/README.documents.md')
    assert '--network none --read-only' in readme and "<IMAGE_ID> python -I -B - < calendar-pin.py" in readme

def test_static_the_startup_checks_and_their_expected_answer_are_the_mount_readme_s():
    root=opsart();readme=text(root,'c3po/deployment/capacity-mount/README.md');m=kprobe.K().m
    assert "    ${C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE:-c3po_capacity_unprovisioned}:/c3po-capacity:ro" in readme.splitlines()
    assert "from app.config import Settings; from app.r2d2_v2_capacity_bootstrap import CapacityConfig; c=CapacityConfig(Settings()); print(\"CAPACITY_STARTUP_OK\", sorted(c.roots), c.veto_mode); c.close()" in readme
    assert "Expected: `CAPACITY_STARTUP_OK ['documents', 'go', 'payload']\nDISPATCH_AND_DERIVATION_ONLY`" in readme
    for name in ('C3PO_R2D2_V2_CAPACITY_REQUIRED=true','C3PO_R2D2_V2_CAPACITY_VETO_MODE=DISPATCH_AND_DERIVATION_ONLY','C3PO_R2D2_V2_SHADOW_RELEASE_SHA'):
        assert name in readme
    assert "{{range .Mounts}}{{.Type}} {{.Name}} {{.Source}} {{.Destination}} RW={{.RW}}{{println}}{{end}}" in readme
    assert m.CAPACITY_ROOTS==('documents','go','payload') and m.VETO_MODE=='DISPATCH_AND_DERIVATION_ONLY' and m.CAPACITY_TARGET=='/c3po-capacity'

def test_static_epoch_order_and_package_are_the_release_s():
    root=tree();m=kprobe.K().m;assembler=text(root,'c3po/backend/app/r2d2_v2_epoch_assembler.py').splitlines()
    assert assembler[8]=="EPOCH = '%s'"%m.EPOCH_NAME and assembler[11]=="DOCUMENT_ORDER_SHA = '%s'"%m.DOCUMENT_ORDER
    python=kprobe.app_python()
    if python is None:pytest.skip('no interpreter for the package hash')
    done=subprocess.run([str(python),'-I','-B','-c','import sys;sys.path.insert(0,%r);from app.r2d2_v2_earnings_package import implementation_package_sha;print(implementation_package_sha())'
                         %str(root/'c3po'/'backend')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert done.stdout.decode().strip()==m.PACKAGE_SHA,done.stderr[-400:]

def test_static_anchored_root_bootstrap_and_settings_are_what_the_scripts_and_the_source_rely_on():
    root=tree();anchored=text(root,'c3po/backend/app/r2d2_v2_capacity_anchored.py');bootstrap=text(root,'c3po/backend/app/r2d2_v2_capacity_bootstrap.py')
    config=text(root,'c3po/backend/app/config.py');store=text(root,'c3po/backend/app/r2d2_v2_store.py')
    assert "            self.identity=digest([[part,*identity] for _,part,_,identity in self.nodes])" in anchored.splitlines()
    assert "need(stat.S_ISDIR(info.st_mode) and info.st_uid==os.geteuid() and not info.st_mode&0o077,'ROOT_NOT_PRIVATE')" in anchored
    assert "fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)" in anchored and "absolute=Path(os.path.abspath(path))" in anchored
    assert "before.st_nlink==1 and not before.st_mode&0o077 and before.st_size<=limit,'ROOT_FILE_POLICY')" in anchored and 'def read(self,name,limit=4*1024*1024):' in anchored
    assert 'return json.dumps(value, sort_keys=True, separators=(",", ":"),\n                      ensure_ascii=True, allow_nan=False).encode()' in store
    assert 'class ShadowIntegrityError(ValueError):' in store
    for attribute in ("getattr(settings,'r2d2_v2_capacity_config_file','')","getattr(settings,'r2d2_v2_capacity_config_sha','')",
                      "getattr(settings,'r2d2_v2_capacity_veto_mode','DISPATCH_AND_DERIVATION_ONLY')","settings.r2d2_v2_shadow_release_sha",
                      "set(b['roots'])=={'documents','payload','go'}","self.roots[key]=AnchoredRoot(value['path'],expected_identity=value['identity'])",
                      "self.config_root=AnchoredRoot(path.parent);self.name=path.name"):
        assert attribute in bootstrap,attribute
    assert 'model_config = SettingsConfigDict(env_prefix="C3PO_", extra="ignore", populate_by_name=True)' in config
    for field in ('r2d2_v2_capacity_required: bool = False','r2d2_v2_capacity_veto_mode: str = "DISPATCH_AND_DERIVATION_ONLY"',
                  'r2d2_v2_capacity_config_file: str = ""','r2d2_v2_capacity_config_sha: str = ""','r2d2_v2_shadow_release_sha: str = ""'):
        assert '    '+field in config.splitlines()
    assert 'env_file' not in config,'Settings reads the environment of the container only: none is given to these containers'
    dockerfile=text(root,'c3po/backend/Dockerfile').splitlines()
    assert 'WORKDIR /app' in dockerfile and 'COPY backend/app ./app' in dockerfile and not [line for line in dockerfile if line.startswith('ENTRYPOINT')]
    assert '      - ${C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE:-c3po_capacity_unprovisioned}:/c3po-capacity:ro' in text(root,'c3po/compose.yml').splitlines()

def test_static_build_names_this_core_and_these_two_files():
    k=kprobe.K();report=k.report;a=f.assembler()
    assert report['core_sha256']==a.core_sha256()=='4c24c5cfe4d6c70ce8aa57c61b070255dd67850be6697b8a0f58f95f6663d0d6'
    assert report['operation_part_sha256']==f.sha((kprobe.DIRECTORY/'op.py').read_bytes()) and report['spec_sha256']==f.sha((kprobe.DIRECTORY/'spec.py').read_bytes())
    assert report['operation']=='GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01' and report['writes_allowed'] is False
    assert report['parts']==['core','runner','docker','parents']
    m=k.m;assert (m.IDENT_SCRIPT_SHA256,m.IDENT_SCRIPT_BYTES)==('0b8b12216903b698b29a970f9e257e6e5f16e417102a637fda539dfde10545d1',1330)
    assert (m.LOAD_SCRIPT_SHA256,m.LOAD_SCRIPT_BYTES)==('c3019efaf1d51fea5188af9860f093faba4eb830f19220e222bc80b8aeaba99c',2050)

def test_static_unbound_request_carries_no_window_no_day_and_no_value_of_the_host():
    k=kprobe.K();request=json.loads((k.dir/'REQUEST.UNBOUND.json').read_bytes())
    assert request['date'] is None and request['plan']['window']=={'expires_at':None,'not_before':None}
    assert {key:request['plan'][key] for key in k.m.PLAN_KEYS}=={key:None for key in k.m.PLAN_KEYS}
    go=json.loads((k.dir/'GO.UNBOUND.json').read_bytes());assert go['success_criterion'] is None,'the success follows the signed step'
