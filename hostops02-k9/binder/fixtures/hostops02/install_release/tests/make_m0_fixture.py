"""Author's tool, offline: writes the three fixtures binding/predispatch.py is tested with.

  tests/fixtures/M0_REQUEST.W1_EMULATION.json   the canonical bytes of a bound W1 request, as M0 will be bound
  tests/fixtures/M0_RECEIPT.W1_EMULATION.json   the line the stdin launcher would print for it
  tests/fixtures/M0_FIXTURE.W1_EMULATION.json   what they were made from

M0 (the Monday snapshot) is the W1 preflight read, a source of another family. Its receipt is not modelled by hand
here: it is PRODUCED by the W1 source itself (collect and observe, unmodified) on the emulated host of W1's own test
file, at Monday 2026-10-05 08:00 UTC, with the request naming this operation's destination among its release directory
candidates. So the shape binding/predispatch.py reads is the shape those bytes emit. Every value is synthetic: the
device numbers, inodes, sizes and names are the constants of W1's test emulation, never those of a host.

usage: <python with pytest> make_m0_fixture.py <the W1 candidate directory: holds w1_preflight_readonly.py and test_w1_preflight_once.py>
"""
from datetime import datetime,timedelta,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
DESTINATION='r2d2-v2-release-20261005'
NOW=datetime(2026,10,5,8,0,tzinfo=timezone.utc)
HOST='1'*64
def sha(raw):return hashlib.sha256(raw).hexdigest()

def main(candidate):
    candidate=Path(candidate).resolve();sys.path.insert(0,str(candidate))
    spec=importlib.util.spec_from_file_location('_w1_tests',candidate/'test_w1_preflight_once.py');tests=importlib.util.module_from_spec(spec)
    sys.modules['_w1_tests']=tests;spec.loader.exec_module(tests);w1=tests.p
    window={'not_before':NOW.isoformat(),'not_after':(NOW+timedelta(minutes=5)).isoformat()}
    request=json.loads((candidate/'REQUEST.UNBOUND.json').read_bytes());request.update(status='BOUND',host_binding_sha256=HOST,**window)
    request['collection'].update(status='BOUND',host_binding_sha256=HOST,window={'not_before':window['not_before'],'expires_at':window['not_after']})
    request['collection']['candidates']={'release_directories':[DESTINATION],'capacity_roots':[]}
    authority=json.loads((candidate/'AUTHORITY.UNBOUND.json').read_bytes())
    authority.update(status='SIGNED',decision='APPROVED',execution_authorized=True,owner='SYNTHETIC_NEVER_AUTHORITATIVE',host_binding_sha256=HOST,**window)
    go=json.loads((candidate/'GO.UNBOUND.json').read_bytes())
    go.update(status='SIGNED',action='GO',execution_authorized=True,owner=authority['owner'],host_binding_sha256=HOST,**window)
    authority['request_sha256']=w1.sha(w1.canonical(request))
    go.update(request_sha256=authority['request_sha256'],authority_sha256=w1.sha(w1.canonical(authority)),payload_sha256=w1.sha(tests.SOURCE),
              claim_root_identity={'path':'/synthetic/claim-root','device':1,'inode':2},
              transport_binding={'target':'fixture@unused.invalid','remote_command':'sudo -n /usr/bin/python3 -I -B -','command_sha256':'2'*64,'runtime_sha256':{}})
    raw=[w1.canonical(item) for item in (request,authority,go)]
    pins=w1.Pins(payload=w1.sha(tests.SOURCE),request=w1.sha(raw[0]),authority=w1.sha(raw[1]),go=w1.sha(raw[2]))
    host=tests.world();host.clock=NOW.timestamp()
    receipt=w1.observe(*raw,pins=pins,payload_bytes=tests.SOURCE,clock=lambda:NOW,monotonic=lambda:0,executor_uid=lambda:0,
                       collector=lambda collection,gate:w1.collect(collection,gate,host=host))
    assert receipt['status']==w1.COMPLETE_STATUS and receipt['observation']['status']=='OBSERVED_COMPLETE',receipt['observation'].get('problems')
    row=receipt['observation']['sections']['release_directories']['candidates'];assert row==[{'status':'COMPLETE','exists':False,'candidate_index':0}],row
    line=json.dumps(receipt,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
    target=HERE/'fixtures';target.mkdir(exist_ok=True)
    (target/'M0_REQUEST.W1_EMULATION.json').write_bytes(raw[0]);(target/'M0_RECEIPT.W1_EMULATION.json').write_bytes(line)
    record={'schema':'HOSTOPS02_INSTALL_RELEASE_M0_FIXTURE_V1','w1_source_sha256':sha(tests.SOURCE),'w1_test_file_sha256':sha((candidate/'test_w1_preflight_once.py').read_bytes()),
            'w1_operation':w1.OPERATION,'w1_receipt_schema':w1.RECEIPT_SCHEMA,'observed_at':NOW.isoformat(),'request_sha256':sha(raw[0]),'receipt_sha256':sha(line),
            'receipt_bytes':len(line),'release_directory_candidates':[DESTINATION],'produced_by':'w1_preflight_readonly.observe and collect, unmodified, on the emulated host of W1\'s own test file',
            'every_value_is_synthetic':True,'python':sys.version.split()[0]}
    (target/'M0_FIXTURE.W1_EMULATION.json').write_bytes((json.dumps(record,indent=1,sort_keys=True)+'\n').encode('ascii'))
    sys.stdout.write(json.dumps(record,indent=1,sort_keys=True)+'\n');return 0

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit(__doc__)
    raise SystemExit(main(sys.argv[1]))
