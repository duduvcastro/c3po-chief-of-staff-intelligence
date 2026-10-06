"""Fixtures of K4-E0: the request plan built from the emulated host exactly as a binder would copy it from a read-only
receipt, and SYNTHETIC runner bytes. The runner of the K9 note does not exist yet; nothing here is or imitates it: the
bytes are comment lines that say so, and the source judges them by hash and size only. Nothing here is authoritative."""
import base64
import json
from pathlib import Path

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
EPOCH='R2D2-V2-SHADOW-2026-10-05'
VAR_LIB='/var/lib'
C3PO='/var/lib/c3po'
SOURCE=C3PO+'/r2d2-v2-source-20261005'
K9=C3PO+'/r2d2-v2-k9-20261005'
TOOLS=K9+'/tools'
ORDER=[C3PO,SOURCE,K9,TOOLS,K9+'/days',K9+'/claims',K9+'/secrets']   # the creation order when /var/lib/c3po is absent
KEYS=['VAR_LIB_C3PO','SOURCE_ROOT','K9_ROOT','K9_TOOLS','K9_DAYS','K9_CLAIMS','K9_SECRETS']
ENTRIES={C3PO:2,SOURCE:0,K9:4,TOOLS:1,K9+'/days':0,K9+'/claims':0,K9+'/secrets':0}
RUNNER=b''.join(b'# SYNTHETIC TEST BYTES %03d: NOT THE K9 RUNNER, never delivered anywhere\n'%index for index in range(40))

def b64(raw):return base64.b64encode(raw).decode('ascii')
def K():return f.load(DIRECTORY)
def runner_name(raw=RUNNER):return 'k9_runner-%s.py'%f.sha(raw)
def runner_path(raw=RUNNER):return TOOLS+'/'+runner_name(raw)

def runner_member(raw=RUNNER):
    """The plan member a binder writes from the runner file: the bytes, their hash, their size, the content-addressed path."""
    return {'path':runner_path(raw),'content_b64':b64(raw),'sha256':f.sha(raw),'bytes':len(raw)}
def fields(host,raw=RUNNER):
    return {'parent':hostemu.rows(host,VAR_LIB),'runner':runner_member(raw),'evidence_boot_id_sha256':f.BOOT_SHA}
def with_c3po(host,mode=0o755,uid=0,gid=0):
    """/var/lib/c3po already there (its state on the host was never observed: both cases are tested)."""
    host.tree.add(C3PO,mode=mode,uid=uid,gid=gid);return host
def case(now=None,raw=RUNNER,c3po=False,**options):
    """(docs, host): a bound fixture that completes on a fresh emulated host (/var/lib/c3po absent unless c3po=True)."""
    k=K();host=f.world(k)
    if c3po:with_c3po(host)
    return f.Docs(k,fields(host,raw),now=now,**options),host

def state_of(host):
    """Everything a run could change on the emulated host."""
    return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True),json.dumps(host.docker.images,sort_keys=True)

STATES=['A_NOTHING','B1_C3PO','B2_SOURCE_ROOT','B3_K9_ROOT','B4_TOOLS','B5_DAYS','B6_CLAIMS','B7_SECRETS','C_TEMPORARY_ONLY','D_LINKED_TEMPORARY_PRESENT','E_DELIVERED']
def classify(host,go16,content=RUNNER,c3po_existed=False):
    """What a later read finds of an E0 run, from the tree alone: one of the states of DESIGN.md section 5. Asserts what
    must hold in every state: the directories that exist are a prefix of the creation order, each created one root:root
    0700 and holding nothing but what this run puts there, and the final name of the runner, whenever it exists, holds
    exactly the signed bytes. With c3po_existed, /var/lib/c3po is not this run's and counts as given."""
    order=[path for path in ORDER if not (c3po_existed and path==C3PO)]
    present=[path for path in order if host.tree.get(path) is not None]
    assert present==order[:len(present)],present
    for path in present:
        node=host.tree.get(path);assert node.kind=='dir' and (node.uid,node.gid,node.mode)==(0,0,0o700),path
    if host.tree.get(C3PO) is not None and not c3po_existed:assert set(host.tree.get(C3PO).children)<={'r2d2-v2-source-20261005','r2d2-v2-k9-20261005'}
    k9=host.tree.get(K9)
    if k9 is not None:assert set(k9.children)<={'tools','days','claims','secrets'}
    for path in (SOURCE,K9+'/days',K9+'/claims',K9+'/secrets'):
        if host.tree.get(path) is not None:assert host.tree.get(path).children=={},path
    if len(present)<len(order):
        if host.tree.get(TOOLS) is not None:assert host.tree.get(TOOLS).children=={}
        states=[state for state in STATES if not (c3po_existed and state=='B1_C3PO')]
        return states[len(present)]
    tools=host.tree.get(TOOLS);names=sorted(tools.children);temporary='.hostops-%s-0.partial'%go16;final=runner_name(content)
    assert set(names)<={temporary,final},names
    if final in names:
        node=tools.children[final];assert bytes(node.content)==content and node.kind=='file' and (node.uid,node.gid,node.mode)==(0,0,0o600)
    if names==[]:return 'B7_SECRETS'
    if names==[temporary]:
        assert content.startswith(bytes(tools.children[temporary].content));return 'C_TEMPORARY_ONLY'
    if names==sorted([temporary,final]):
        assert tools.children[temporary] is tools.children[final] and tools.children[final].nlink==2;return 'D_LINKED_TEMPORARY_PRESENT'
    assert tools.children[final].nlink==1;return 'E_DELIVERED'
