"""Generator of K8's test fixtures (tests/fixtures/DAY_SETS.json). Offline; run once by the author, never by a test.

The documents of a capacity day are made by the real offline tool, capacity_day_documents.py (sha256 888a48e6...,
the tool the signed Act B names), driven through the helpers of its own repository test file with SYNTHETIC inputs:
seven synthetic chain documents, synthetic hashes for every release, receipt, authority and host fact, synthetic
instrument-shaped names (they exist only in the synthetic commitment written here). Nothing here is a real document
of the epoch, a real list or a real receipt; the fixture file says so in every day it holds.

What this adds to the tool's inputs: the capacity roots are the container paths /c3po-capacity/<root> with the
AnchoredRoot identity that the emulated host of K8's tests gives them (the inodes below, device 801), so the identity
comparison of K8 can be tested both ways; and the causal scope of each session is the digest of a synthetic
commitment of the shape r2d2_v2_causal_list.build_commitment returns, written beside the documents as the two files
the K9 commit step leaves in Dd/causal (the draft k9_runner.py, op_commit_launch): commitment.private.json = canonical
JSON of build()['commitment'] and build_audit_receipt.json = canonical JSON of build()['audit_receipt'].

usage (with the backend environment of the opsart checkout, e.g. W/night23-test-venv/bin/python):
  cd <opsart>/c3po/backend && <python> -B <this file> <opsart> <output json> <scratch directory>
"""
import base64
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

OPSART=Path(sys.argv[1]).resolve();OUT=Path(sys.argv[2]).resolve();SCRATCH=sys.argv[3]
sys.path.insert(0,str(OPSART/'c3po'/'backend'));sys.path.insert(0,str(OPSART/'c3po'/'backend'/'tests'))
import test_r2d2_v2_capacity_day_documents as t          # noqa: E402  (the tool's own test helpers, read only)

ROOT_DEVICE=801                                          # tests/hostemu.py ROOT_DEVICE: "/" and /var/lib
CAPACITY_INODES={'c3po-capacity':7100,'config':7101,'documents':7102,'payload':7103,'go':7104}
DAYS={'2026-10-06':['ZZQB','ZZQA','ZZQ.C','ZZQ-D'],                       # four synthetic names (the tool test's own)
      '2026-10-07':['ZQ%04d'%index for index in range(550)],             # the capacity, all synthetic
      '2026-10-08':[]}                                                    # D12: an empty committed list
PREVIOUS={'2026-10-06':'2026-10-05','2026-10-07':'2026-10-06','2026-10-08':'2026-10-07'}

def b64(raw):return base64.b64encode(raw).decode('ascii')
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()   # the store's canonical()
def h(label):return t.h('k8-fixture:'+label)

def identity(name):
    """AnchoredRoot.identity of /c3po-capacity/<name> as the container would compute it, with the emulated host's numbers."""
    return t.store_digest([['c3po-capacity',ROOT_DEVICE,CAPACITY_INODES['c3po-capacity']],[name,ROOT_DEVICE,CAPACITY_INODES[name]]])

def commitment_of(day,symbols):
    """A synthetic commitment of the shape build_commitment returns (keys as at dd4ec4bb), and its audit receipt."""
    built=day+'T00:30:00+00:00'
    c={'schema':'V2_CAUSAL_LIST_COMMITMENT_V1','epoch':t.EPOCH,'n_cut':550,'manifest_sha':h('manifest'),'amendment_sha':h('amendment'),
       'epoch_contract_sha256':h('epoch-contract'),'session':day,'previous_session':PREVIOUS[day],'built_at':built,
       'cutoff_at':day+'T04:00:00+00:00','decision_at':day+'T14:00:00+00:00','calendar_sha256':h('calendar'),
       'registry_sha256':hashlib.sha256(b'SYNTHETIC REGISTRY '+day.encode()).hexdigest(),
       'daily_contract_sha256':hashlib.sha256(b'SYNTHETIC DAILY '+day.encode()).hexdigest(),
       'registry_raw_base64':b64(b'SYNTHETIC REGISTRY '+day.encode()),'daily_raw_base64':b64(b'SYNTHETIC DAILY '+day.encode()),
       'list':list(symbols),'list_sha256':t.store_digest(list(symbols)),'filtered_symbols':sorted(symbols),
       'ranked_liquidity':[{'symbol':name,'adv20_usd':str(1000000-index)} for index,name in enumerate(symbols)],'exclusions':[],
       'counts':{'registry':len(symbols),'filtered':len(symbols),'liquidity_passed':len(symbols),'selected':len(symbols),'reasons':{}},
       'coverage':{'numerator':len(symbols),'denominator':len(symbols)+3,'ratio':len(symbols)/(len(symbols)+3),
                   'scope':'FILTERED_PROVIDER_REGISTRY_ONLY','outside_registry_observed':False,'complete_exchange_universe':False}}
    sha=t.store_digest(c)
    receipt={'event_id':'synthetic-'+day,'event_type':'r2d2.v2.causal_list_built','occurred_at':built,
             'payload':{'epoch':t.EPOCH,'session':day,'manifest_sha':c['manifest_sha'],'amendment_sha':c['amendment_sha'],
                        'list_sha256':c['list_sha256'],'n_cut':550,'commitment_sha256':sha}}
    return canonical(c),canonical(receipt),sha,c['list_sha256']

def main():
    base=Path(tempfile.mkdtemp(prefix='k8-fixtures-',dir=SCRATCH))
    code,line=t.run('templates','--order-file',t.write_json(base/'order.json',t.ORDER),'--output-directory',base/'templates')
    assert code==0,line
    templates=json.loads((base/'templates'/'ACT_B_TEMPLATES.json').read_bytes())
    files,pins=t.signed_chain(templates)
    chain=base/'chain';chain.mkdir()
    for name,raw in files.items():(chain/name).write_bytes(raw)
    roots={'config':{'path':'/c3po-capacity/config'},**{name:{'path':'/c3po-capacity/'+name,'identity':identity(name)} for name in ('documents','payload','go')}}
    epoch=t.copy(t.epoch_inputs(pins,roots));epoch_file=t.write_json(base/'epoch.json',epoch)
    out={'schema':'K8_TEST_FIXTURES_V1','synthetic':True,
         'warning':'SYNTHETIC test documents made by capacity_day_documents.py from synthetic inputs; no real document, list or receipt',
         'tool_sha256':hashlib.sha256((OPSART/'c3po'/'deployment'/'capacity-day'/'capacity_day_documents.py').read_bytes()).hexdigest(),
         'tool_test_sha256':hashlib.sha256((OPSART/'c3po'/'backend'/'tests'/'test_r2d2_v2_capacity_day_documents.py').read_bytes()).hexdigest(),
         'capacity_inodes':CAPACITY_INODES,'root_device':ROOT_DEVICE,'chain':{name:b64(raw) for name,raw in sorted(files.items())},
         'windows':list(t.WINDOW_NAMES),'days':{}}
    for day,symbols in DAYS.items():
        commitment,audit,commitment_sha,list_sha=commitment_of(day,symbols)
        session=t.session_inputs(day);session['causal_scope']={'commitment_sha256':commitment_sha,'list_sha256':list_sha}
        session_file=t.write_json(base/(day+'.json'),session);roles={}
        for window in t.WINDOW_NAMES:
            target=base/('out-'+day+'-'+window)
            code,line=t.run('day','--epoch-inputs',epoch_file,'--session-inputs',session_file,'--window',window,'--output-directory',target,
                            '--chain-directory',chain)
            assert (code,line['status'],line['documentary_authority'])==(0,'WRITTEN','VERIFIED'),line
            assert line['list']==('EMPTY' if not symbols else 'NOT_EMPTY'),line
            summary=json.loads((target/'SUMMARY.json').read_bytes())
            for role,path in summary['roles'].items():
                if role in ('request','dispatch_go'):continue
                key=role if role in t.DAY_FILES else role+':'+window
                raw=(target/path).read_bytes()
                if key in roles:assert roles[key]['b64']==b64(raw),(key,'day files are the same in every window')
                roles[key]={'path':path,'b64':b64(raw)}
        out['days'][day]={'files':{key:value['b64'] for key,value in sorted(roles.items())},'paths':{key:value['path'] for key,value in sorted(roles.items())},
                          'commitment_file':b64(commitment),'audit_file':b64(audit),'commitment_sha256':commitment_sha,'list_sha256':list_sha,'symbols':len(symbols)}
    OUT.write_text(json.dumps(out,indent=1,sort_keys=True)+'\n',encoding='ascii')
    print('WRITTEN',OUT,hashlib.sha256(OUT.read_bytes()).hexdigest())

if __name__=='__main__':main()
