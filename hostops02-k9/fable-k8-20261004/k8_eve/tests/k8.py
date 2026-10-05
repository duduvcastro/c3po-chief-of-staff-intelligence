"""Fixtures of K8: the request plan built from the emulated host as a binder would copy it from a read-only receipt, and
the documents of SYNTHETIC capacity days (tests/fixtures/DAY_SETS.json, made by the real capacity_day_documents.py from
synthetic inputs by tests/make_fixtures.py). The emulated host is the baseline of the core plus what the epoch has put
there before an eve: the capacity tree as provisioned on 03/10 (root:root 0700), the seven chain documents delivered
into documents (B5), the K9 tree of E0 and, for the day, what the K9 commit step leaves (the commitment, its audit
receipt, the commit receipt). Every name, hash, list and receipt here is synthetic. Nothing here is authoritative."""
import base64
from datetime import datetime
import json
from pathlib import Path

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
FIXTURES=json.loads((HERE/'fixtures'/'DAY_SETS.json').read_bytes())
EPOCH='R2D2-V2-SHADOW-2026-10-05'
DAY='2026-10-06'                       # four synthetic names
FULL='2026-10-07'                      # 550 synthetic names
EMPTY='2026-10-08'                     # an empty committed list (D12)
WINDOWS=list(FIXTURES['windows'])
VAR_LIB='/var/lib'
CAPACITY='/var/lib/c3po-capacity'
ROOTS=('config','documents','go','payload')
C3PO='/var/lib/c3po'
K9='/var/lib/c3po/r2d2-v2-k9-20261005'
DAYS=K9+'/days'
PACKAGE='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
COMMITMENT_KEY='day/causal/commitment.private.json'
AUDIT_KEY='day/causal/build_audit_receipt.json'
EVE={'2026-10-06':'2026-10-05','2026-10-07':'2026-10-06','2026-10-08':'2026-10-07','2026-10-09':'2026-10-08'}

def raw(value):return base64.b64decode(value)
def b64(data):return base64.b64encode(data).decode('ascii')
def K():return f.load(DIRECTORY)
def files_of(day=DAY):return {key:raw(value) for key,value in FIXTURES['days'][day]['files'].items()}
def contract_of(day=DAY):return files_of(day)['contract']
def blob(data):return {'sha256':f.sha(data),'bytes':len(data),'content_b64':b64(data)}
def commitment_of(day=DAY):return raw(FIXTURES['days'][day]['commitment_file'])
def audit_of(day=DAY):return raw(FIXTURES['days'][day]['audit_file'])
def symbols_of(day=DAY):return json.loads(commitment_of(day))['list']
def chain():return {name:raw(value) for name,value in FIXTURES['chain'].items()}
def attempt_key(day,phase='causal_list',operation='commit_launch'):return f.sha(f.canonical([EPOCH,day,phase,operation]))
def moment(day=DAY,hour=21,minute=38):
    """An instant of the eve of day (21:38Z = 18:38 BRT, inside A2's E6 band)."""
    return datetime.fromisoformat(EVE[day]+'T%02d:%02d:00+00:00'%(hour,minute))

LAYOUT_KEYS=['template','go_admission_record','go_bar_manifest_record','publication_bar_manifest']+['veto_view:'+w for w in WINDOWS]+[
    'go_admission','go_bar_manifest']+['capacity_config:'+w for w in WINDOWS]
def names(day=DAY,windows=WINDOWS):
    """(key, root, name) in creation order, the payload file last: the table of DESIGN.md section 2."""
    stem='session='+day
    table=[('template','documents',stem+'.template.md'),('go_admission_record','documents',stem+'.go-admission.md'),
           ('go_bar_manifest_record','documents',stem+'.go-bar_manifest.md'),('publication_bar_manifest','documents',stem+'.publication-bar_manifest.md')]
    table+=[('veto_view:'+w,'documents',stem+'.view-'+w+'.md') for w in windows]
    table+=[('go_admission','go',stem+'.admission.json'),('go_bar_manifest','go',stem+'.bar_manifest.json')]
    table+=[('capacity_config:'+w,'config',stem+'.'+w+'.capacity.json') for w in windows]
    return table+[('payload','payload',stem+'.json')]
def path_of(root,name):return CAPACITY+'/'+root+'/'+name

def commit_receipt(day=DAY,commitment=None,audit=None,**changes):
    """The commit step's receipt as the runner writes it (K9_STEP_RECEIPT_V1, the member set of K9R section 5)."""
    commitment=commitment_of(day) if commitment is None else commitment;audit=audit_of(day) if audit is None else audit
    body={'schema':'K9_STEP_RECEIPT_V1','status':'COMPLETE','code':None,'epoch':EPOCH,'day':day,'phase':'causal_list','operation':'commit_launch',
          'attempt_key':attempt_key(day),'step_plan_sha256':f.sha(b'synthetic step plan'),'started_at':EVE[day]+'T21:52:10+00:00',
          'completed_at':EVE[day]+'T21:53:02+00:00','package_sha256':PACKAGE,'build_sha':REVISION,
          'outputs':{COMMITMENT_KEY:f.sha(commitment),AUDIT_KEY:f.sha(audit)},'aggregates':{},'counts':{'n_cut':550,'confirmed':1}}
    body.update(changes);return f.canonical(body)

def provision(host,day=DAY,chain_files=None,k9_day=True,c3po_mode=0o755):
    """What the epoch has put on the host before the eve of day (synthetic): capacity tree, chain documents, K9 tree, the
    commit step's three files. The capacity tree's inodes are the ones the fixture configs' root identities pin."""
    inodes=FIXTURES['capacity_inodes']
    host.tree.add(CAPACITY,mode=0o700,ino=inodes['c3po-capacity'])
    for root in ROOTS:host.tree.add(CAPACITY+'/'+root,mode=0o700,ino=inodes[root])
    for name,data in (chain() if chain_files is None else chain_files).items():host.tree.add(CAPACITY+'/documents/'+name,kind='file',mode=0o600,content=data)
    host.tree.add(C3PO,mode=c3po_mode)
    for path in (K9,K9+'/tools',DAYS,K9+'/claims',K9+'/secrets'):host.tree.add(path,mode=0o700)
    if k9_day:
        for path in (DAYS+'/'+day,DAYS+'/'+day+'/causal',DAYS+'/'+day+'/receipts',DAYS+'/'+day+'/inputs'):host.tree.add(path,mode=0o700)
        host.tree.add(DAYS+'/'+day+'/causal/commitment.private.json',kind='file',mode=0o600,content=commitment_of(day))
        host.tree.add(DAYS+'/'+day+'/causal/build_audit_receipt.json',kind='file',mode=0o600,content=audit_of(day))
        host.tree.add(DAYS+'/'+day+'/receipts/commit_launch.RECEIPT.json',kind='file',mode=0o600,content=commit_receipt(day))
    return host

def fields(host,day=DAY,rule='REFUSE_ON_MISMATCH',windows=None):
    files=files_of(day);windows=WINDOWS if windows is None else windows
    return {'day':day,'windows':list(windows),'contract':blob(files['contract']),
            'files':{key:blob(data) for key,data in files.items() if key!='contract' and (':' not in key or key.split(':')[1] in windows)},
            'days_parent':hostemu.rows(host,DAYS),'identity_rule':rule,'evidence_boot_id_sha256':f.BOOT_SHA}
def world(k=None,day=DAY,**options):return provision(f.world(k or K()),day,**options)
def case(now=None,day=DAY,rule='REFUSE_ON_MISMATCH',**options):
    """(docs, host): a bound fixture that completes on a fresh emulated host at an instant of the eve of day."""
    k=K();host=world(k,day,**options)
    return f.Docs(k,fields(host,day,rule),now=now or moment(day)),host

def state_of(host):
    """Everything a run could change on the emulated host."""
    return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True),json.dumps(host.docker.images,sort_keys=True)

def payload_of(day=DAY):
    """The payload file as the host must assemble it: canonical {contract, causal} (the store's canonical())."""
    contract=json.loads(contract_of(day));commitment=json.loads(commitment_of(day))
    causal={'epoch':EPOCH,'session':day,'status':'AVAILABLE','symbols':commitment['list'],'list_sha256':f.sha(f.canonical(commitment['list'])),
            'commitment_sha256':f.sha(commitment_of(day))}
    return f.canonical({'contract':contract,'causal':causal})

def classify(host,go16,day=DAY):
    """What a later read finds of a K8 run, from the tree alone: 'F<n>' = the first n files of the creation order are
    delivered, with '_TEMPORARY' when the temporary of the next one exists alone and '_LINKED' when the last one still
    has its temporary as a second name. Asserts what must hold in every state: the delivered files are a prefix of the
    creation order, each root:root 0600, one link unless _LINKED, exactly its bytes; at most one temporary exists, and
    nothing else is in the four roots but the chain documents."""
    table=names(day);contents=dict(files_of(day),payload=payload_of(day));present=0;spares=[];ours=set()
    for index,(key,root,name) in enumerate(table):
        directory=host.tree.get(CAPACITY+'/'+root);temporary='.hostops-%s-%d.partial'%(go16,index)
        node=directory.children.get(name);spare=directory.children.get(temporary);ours|={(root,name),(root,temporary)}
        if node is not None:
            assert node.kind=='file' and (node.uid,node.gid,node.mode)==(0,0,0o600) and bytes(node.content)==contents[key],key
            assert present==index,('not a prefix',key);present=index+1
        if spare is not None:
            assert contents[key].startswith(bytes(spare.content)),key;spares.append((index,spare is node))
    for root in ROOTS:
        for name in host.tree.get(CAPACITY+'/'+root).children:
            assert (root,name) in ours or (root=='documents' and name in FIXTURES['chain']),(root,name)
    assert len(spares)<=1,spares
    if not spares:
        if present:assert host.tree.get(path_of(table[present-1][1],table[present-1][2])).nlink==1
        return 'F%02d'%present
    index,linked=spares[0]
    if linked:
        assert index==present-1 and host.tree.get(path_of(table[index][1],table[index][2])).nlink==2;return 'F%02d_LINKED'%present
    assert index==present;return 'F%02d_TEMPORARY'%present
