"""Fixtures of K10 (install_release): the request plan built from the emulated host exactly as a binder would copy it
from a read-only receipt, and the synthetic release bytes. Nothing here is authoritative.

The release fixture (fixtures/release.SYNTHETIC.json) was verified by the application's own Release.verify at
dd4ec4bb with a synthetic build revision (fixtures/RELEASE_VERIFY.SYNTHETIC.json, written by make_synthetic_release.py):
it has the shape and the constants of a release of this epoch and can never pass on the host."""
import base64
import json
from pathlib import Path

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
RELEASE=(HERE/'fixtures'/'release.SYNTHETIC.json').read_bytes()
RECORD=json.loads((HERE/'fixtures'/'RELEASE_VERIFY.SYNTHETIC.json').read_bytes())
DATA=hostemu.DATA
LEAF='r2d2-v2-release-20261005'
BASE=DATA+'/'+LEAF
NAME='release.CERTIFIED.json'
TARGET=BASE+'/'+NAME
PIN=hostemu.PIN
EPOCH='R2D2-V2-SHADOW-2026-10-05'
def b64(raw):return base64.b64encode(raw).decode('ascii')
def K():return f.load(DIRECTORY)

def release_member(raw=RELEASE):
    """The plan member a binder writes from the release file: the bytes, their hash, their size, the constant path."""
    return {'path':TARGET,'content_b64':b64(raw),'sha256':f.sha(raw),'bytes':len(raw)}
def fields(host,raw=RELEASE):
    return {'parent':hostemu.rows(host,DATA),'release':release_member(raw),'evidence_boot_id_sha256':f.BOOT_SHA}
def case(now=None,raw=RELEASE,**options):
    """(docs, host): a bound fixture that completes on a fresh emulated host."""
    k=K();host=f.world(k);return f.Docs(k,fields(host,raw),now=now,**options),host

def altered(**changes):
    """The synthetic release with members changed or (value ...) removed, in the same byte form."""
    body=json.loads(RELEASE)
    for key,value in changes.items():
        if value is ...:body.pop(key,None)
        else:body[key]=value
    return (json.dumps(body,indent=1,sort_keys=True)+'\n').encode('ascii')

def state_of(host):
    """Everything a run could change on the emulated host."""
    return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True),json.dumps(host.docker.images,sort_keys=True)

def classify(host,go16,content=RELEASE):
    """What a later read finds of an install, from the tree alone: one of the five states of DESIGN.md section 5.
    Asserts what must hold in every state: the final name, whenever it exists, holds exactly the signed bytes."""
    node=host.tree.get(BASE)
    if node is None:return 'A_NOTHING'
    assert node.kind=='dir' and (node.uid,node.gid,node.mode)==(0,0,0o700),'the directory of this run'
    names=sorted(node.children);temporary='.hostops-%s-0.partial'%go16
    assert set(names)<={temporary,NAME},names
    if NAME in names:
        final=node.children[NAME];assert bytes(final.content)==content and final.kind=='file' and (final.uid,final.gid,final.mode)==(0,0,0o600)
    if names==[]:return 'B_DIRECTORY_ONLY'
    if names==[temporary]:
        assert content.startswith(bytes(node.children[temporary].content));return 'C_TEMPORARY_ONLY'
    if names==sorted([temporary,NAME]):
        assert node.children[temporary] is node.children[NAME] and node.children[NAME].nlink==2;return 'D_LINKED_TEMPORARY_PRESENT'
    assert node.children[NAME].nlink==1;return 'E_INSTALLED'
