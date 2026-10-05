"""Offline deterministic assembly of the HOSTOPS01 candidates. No host, no network, no credential, no launch.

Every shipped runtime file is a function of files in this directory:
  <op>/<source>.py      = header + shared parts + the operation's own part (parts/), in a fixed order
  <op>/dispatch_once.py = reviewed_base/dispatch_once.py with a fixed table of literal substitutions
  <op>/launcher_stdin.py= reviewed_base/launcher_stdin.py with five literal substitutions (same bytes in every <op>)
  <op>/transport_once.py= reviewed_base/transport_once.py, byte-identical
  <op>/*.UNBOUND.json, FINAL_PAYLOAD.UNBOUND.py = the unbound templates and the exact stdin bytes built from them
Run without arguments to (re)write everything; the test suite calls the pure functions and compares bytes. No output
depends on where this directory lies: a copy assembled at any other path yields the same bytes (tested).
"""
import base64
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
BASE=HERE/'reviewed_base'
REVIEWED={'dispatch_once.py':'8415e357e48e5662c959b4105acea19bc280cda10112b8370bafd27f7920c409',
          'launcher_stdin.py':'2842444ec6e46f5e47cad87265927ea3a1a853f21fe72ec2459cf7ac31c3a08e',
          'transport_once.py':'5900efbf916d679a6ce176dd71413f304e21e0c9ab65b0ff8ee742cc212f2918'}
TEMPLATES={'c3po-massive.service':'9e7de1c6eaf937e5b1fc9540986fdbdf2a2f821a9c57b944f9534a605d07f04a',
           'c3po-massive.timer':'ec61b1d6cbd1d604e5c2177d186f9045e67bf21ecc092498691591dfd9164ee6'}
def date_literal(dates):
    """The date set of one source as the literal its dispatcher carries (a test evaluates it and compares)."""
    return '('+','.join(repr(day) for day in dates)+')'
REMOTE_COMMAND='sudo -n /usr/bin/python3 -I -B -'
FOOTER=("\nif __name__=='__main__':\n"
        "    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')\n")

OPS={
 'provision':{'module':'provision_dirs','parts':['core','runner','layout','listing','op_provision'],'stem':'HOSTOPS_PROVISION',
  'doc':'WRITE_HOSTOPS_PROVISION','header':'''"""OP_PROVISION: exclusive creation of the supervisor and reader directories and of the retention tag.

Supervisor README operation 2 plus the directory part of the reader/capacity provisioning (W4). The journal root is
created in the signed placement: A, next to the state root, or B, a leaf of the data volume. Directories only,
root:root, mode 0700, each by one mkdir relative to a held descriptor of a parent that is either pinned by signed
rows (device, inode, owner, group, mode of every component from "/") or was created or verified by this run.
No file is ever opened for writing. No chmod, chown, rename or removal exists in this source. Everything is looked
at before the first creation; an object that exists is refused, or verified and left alone when the request signs
it as present. At most one image tag is added, last. The caller authenticates exact request/authority/GO/source
bytes first; every mutating call is preceded by the signed UTC window and a monotonic deadline. A run that changed
anything and did not finish is PARTIAL, never a refusal and never absent. No action on import.
"""
'''},
 'install_units':{'module':'install_units','parts':['core','scan','render','op_install_units'],'stem':'HOSTOPS_INSTALL_UNITS',
  'doc':'WRITE_HOSTOPS_INSTALL_UNITS','header':'''"""OP_INSTALL_UNITS: exclusive creation of rendered unit files in /etc/systemd/system. No activation.

Supervisor README operation 3 without daemon-reload, generic over a signed list of (template bytes hash,
destination name, rendered hash). This source starts no process: it does not import subprocess and has no systemctl
or docker call. Each file is written under a dot-prefixed temporary name that systemd does not load, fsynced,
verified, linked to its final name (a link never replaces anything) and the temporary is removed once its identity
is proved; a temporary whose file could not be completed is withdrawn the same way. Nothing else is ever removed.
No chmod, chown or rename exists in this source. Everything is looked at before the first creation, including
drop-in directories, dependency directories and alias links in every unit lookup directory. The caller authenticates exact
request/authority/GO/source bytes first; every mutating call is preceded by the signed UTC window and a monotonic
deadline. A run that changed anything and did not finish is PARTIAL, never a refusal. No action on import.
"""
'''},
 'readback':{'module':'readback_readonly','parts':['core','runner','scan','render','op_readback'],'stem':'HOSTOPS_READBACK',
  'doc':'READONLY_HOSTOPS_READBACK','header':'''"""OP_READBACK: the complete readback of supervisor README operation 4. Read-only.

Observations only. This source has no call that creates, changes or removes anything. The token is looked at with
one lstat and is never opened; its size, a digest or a timestamp never enter the receipt. The only file contents
read are the two unit files and the kernel boot identifier; of symbolic links of a unit type in the lookup
directories the link text is read. Each item is observed on its own: a failed observation
is UNAVAILABLE with a constant code, never an absence, and a mismatch is a finding that leaves every other item in
the receipt. Exit 0 exists for one outcome only; a reconciliation readback never reaches it. The caller
authenticates exact request/authority/GO/source bytes first. No action on import.
"""
'''},
 'precheck':{'module':'precheck_readonly','parts':['core','runner','layout','scan','listing','op_precheck'],'stem':'HOSTOPS_PRECHECK',
  'doc':'READONLY_HOSTOPS_PRECHECK','header':'''"""OP_PRECHECK: the baseline the write operations pin. Read-only.

Observations only. This source has no call that creates, changes or removes anything. It reads one row per
component of every parent directory the write operations pin, proves the absence or records the metadata of every
planned destination, scans the unit lookup directories, hashes the boot identifier, and reads the local ID and tags
of the production image. For a name that holds a secret only type, owner, mode and link count are reported, and
for a unit file found at a signed name no size. A failed observation is UNAVAILABLE with a constant code, never an
absence. The caller authenticates exact
request/authority/GO/source bytes first. No action on import.
"""
'''},
}

def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def reviewed(name):
    raw=(BASE/name).read_bytes()
    if sha(raw)!=REVIEWED[name]:raise SystemExit('REVIEWED_BASE_CHANGED '+name)
    return raw

def part(name):return (HERE/'parts'/(name+'.py')).read_text(encoding='ascii')

def source_bytes(op):
    """header, then each part between its two marker lines, then the footer."""
    out=[OPS[op]['header']]
    for name in OPS[op]['parts']:
        label=name.upper()
        note='shared part, byte-identical in every source that carries it' if not name.startswith('op_') else 'this operation only'
        out.append('# ==== BEGIN %s (%s) ====\n'%(label,note)+part(name).rstrip('\n')+'\n# ==== END %s ====\n'%label)
    return ('\n'.join(out)+FOOTER).encode('ascii')

def load(op,raw=None):
    """Import one assembled source in a private module object (no action on import)."""
    name=OPS[op]['module'];path=HERE/op/(name+'.py')
    spec=importlib.util.spec_from_file_location('_assemble_'+name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);return module

def dispatcher_bytes(op,module):
    """The reviewed dispatcher with literals replaced. No line is added or removed."""
    text=reviewed('dispatch_once.py').decode();p=OPS[op];m=p['module'];writes=module.WRITES_ALLOWED
    def sub(old,new,count=1):
        nonlocal text
        if text.count(old)!=count:raise SystemExit('DISPATCH_ANCHOR '+old)
        text=text.replace(old,new)
    sub('import hostfacts_readonly\nfrom hostfacts_readonly import','import %s\nfrom %s import'%(m,m))
    sub("'hostfacts_readonly.py')","'%s.py')"%m)
    sub('hostfacts_readonly.authenticate(',m+'.authenticate(')
    sub('pins=hostfacts_readonly.Pins(','pins=%s.Pins('%m)
    sub("'SUPERVISOR_HOSTFACTS_DISPATCH_AUTHORIZATION_V1'","'%s_DISPATCH_AUTHORIZATION_V1'"%p['stem'])
    sub("'GO_READONLY_SUPERVISOR_HOSTFACTS_01'","'%s'"%module.OPERATION,2)
    sub("start.date().isoformat()=='2026-10-02'","start.date().isoformat() in "+date_literal(module.DATES))
    sub("'READONLY_SUPERVISOR_HOSTFACTS_REQUEST_V1'","'%s'"%module.REQUEST_SCHEMA)
    sub("'READONLY_SUPERVISOR_HOSTFACTS_AUTHORITY_V1'","'%s'"%module.AUTHORITY_SCHEMA)
    sub("'READONLY_SUPERVISOR_HOSTFACTS_GO_V1'","'%s'"%module.GO_SCHEMA)
    sub("and request.get('status')=='BOUND' and request.get('executor_uid')==0\n",
        "and request.get('status')=='BOUND' and request.get('executor_uid')==0 and request.get('date')==start.date().isoformat()\n")
    sub("go.get('phase')=='READONLY_HOSTFACTS'","go.get('phase')=='%s'"%module.PHASE)
    if writes:
        sub("go.get('writes_allowed') is False","go.get('writes_allowed') is True")
        sub("authority.get('writes_allowed') is False and request.get('writes_allowed') is False,'READONLY_SCOPE')",
            "authority.get('writes_allowed') is True and request.get('writes_allowed') is True,'WRITE_SCOPE')")
    sub("'SUPERVISOR_HOSTFACTS_GO_CLAIM_V1'","'%s_GO_CLAIM_V1'"%p['stem'])
    sub("'SUPERVISOR_HOSTFACTS_DISPATCH_INTENT_V1'","'%s_DISPATCH_INTENT_V1'"%p['stem'],2)
    sub("'SUPERVISOR_HOSTFACTS_INTENT_PUBLICATION_V1'","'%s_INTENT_PUBLICATION_V1'"%p['stem'])
    sub("'READONLY_SUPERVISOR_HOSTFACTS_RECEIPT_V1'","'%s'"%module.RECEIPT_SCHEMA)
    if 'HOSTFACTS' in text or 'hostfacts' in text:raise SystemExit('DISPATCH_RESIDUE')
    compile(text,'dispatch_once.py','exec')
    return text.encode()

def launcher_bytes():
    """The reviewed launcher with five lines replaced. The payload is entered through run(); the exit code is 3 while
    run() executes, so an exception that escapes it is filed UNCERTAIN by the unchanged transport, never as a refusal."""
    text=reviewed('launcher_stdin.py').decode()
    def sub(old,new):
        nonlocal text
        if text.count(old)!=1:raise SystemExit('LAUNCHER_ANCHOR '+old)
        text=text.replace(old,new)
    sub("module=types.ModuleType('_pinned_supervisor_hostfacts')","module=types.ModuleType('_pinned_hostops')")
    sub("exec(compile(raw['source'],'<pinned-supervisor-hostfacts>','exec'),module.__dict__)",
        "exec(compile(raw['source'],'<pinned-hostops>','exec'),module.__dict__)")
    sub("    result=module.observe(raw['request'],raw['authority'],raw['go'],pins=module.Pins(**PINS),",
        "    exit_code=3;result=module.run(raw['request'],raw['authority'],raw['go'],pins=module.Pins(**PINS),")
    sub("    exit_code=0 if result.get('status')=='METADATA_ONLY_REQUIRES_REVIEW' else 2",
        "    exit_code={'METADATA_ONLY_REQUIRES_REVIEW':0,'REFUSED':1}.get(result.get('status'),2)")
    sub("    result={'schema':'READONLY_SUPERVISOR_HOSTFACTS_STDIN_RESULT_V1','status':'REFUSED','code':code,'source_mutation':False}",
        "    result={'schema':'HOSTOPS_STDIN_RESULT_V1','status':'REFUSED' if exit_code==1 else 'RUN_RAISED_STATE_UNKNOWN','code':code}")
    compile(text,'launcher_stdin.py','exec')
    return text.encode()

def launcher_module():
    spec=importlib.util.spec_from_file_location('_assemble_launcher',HERE/'provision'/'launcher_stdin.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def template(name):
    raw=(HERE/'templates'/name).read_bytes()
    if sha(raw)!=TEMPLATES[name]:raise SystemExit('TEMPLATE_CHANGED '+name)
    return raw
def unit_template(name):
    raw=template(name);return {'template_b64':base64.b64encode(raw).decode('ascii'),'template_sha256':sha(raw)}

NULL_ROW=lambda path:{'path':path,'device':None,'inode':None,'uid':None,'gid':None,'mode':None}
SIX={'IMAGE_ID':None,'HOST_JOURNAL_ROOT':None,'CONTAINER_JOURNAL_ROOT':None,'HOST_STATE_ROOT':None,'HOST_CONFIG_DIR':None,'NETWORK':None}

def unbound_plan(op,module):
    """Operation parameters with every open value null. What is already decided by the code is filled in."""
    if op=='provision':
        fixed=module.layout(['SUPERVISOR','READER'],None,None,None,None)
        creates=[dict(row,expect='ABSENT') for row in fixed if row['key'].startswith('SUP_')]
        creates.append({'key':'SUP_JOURNAL','path':None,'mode':448,'parent':None,'expect':'ABSENT'})        # path and parent follow the signed placement
        creates+=[dict(row,expect='ABSENT') for row in fixed if row['key'].startswith('RDR_')]
        creates+=[{'key':key,'path':None,'mode':448,'parent':parent,'expect':'ABSENT'} for key,parent in
                  [('CAP_ROOT',{'chain':None}),('CAP_CONFIG',{'entry':'CAP_ROOT'}),('CAP_DOCUMENTS',{'entry':'CAP_ROOT'}),
                   ('CAP_PAYLOAD',{'entry':'CAP_ROOT'}),('CAP_GO',{'entry':'CAP_ROOT'}),('CAP_RECEIPTS',{'entry':'RDR_STATE'})]]
        return {'groups':list(module.GROUPS),'journal_placement':None,'data_volume_path':None,'journal_leaf':None,'existing_journal_leaves':None,
                'capacity':{'root_path':None,'receipt_directory_path':None},
                'chains':{'ETC':[NULL_ROW('/'),NULL_ROW('/etc')],'VAR_LIB':[NULL_ROW('/'),NULL_ROW('/var'),NULL_ROW('/var/lib')],
                          'DATA_VOLUME':None,'CAPACITY_PARENT':None},
                'creates':creates,'retention_tag':{'repository':module.REPOSITORY,'tag':None,'image_id':None,'expect':'ABSENT'},
                'evidence_boot_id_sha256':None}
    if op=='install_units':
        timer=template('c3po-massive.timer')
        return {'unit_directory':[NULL_ROW(path) for path in ('/','/etc','/etc/systemd','/etc/systemd/system')],
                'units':[dict(unit_template('c3po-massive.service'),key='SUPERVISOR_SERVICE',destination_name='c3po-massive.service',mode=420,
                              profile='MASSIVE_SUPERVISOR_SERVICE_V1',placeholders=dict(SIX),rendered_sha256=None,rendered_bytes=None,expect='ABSENT'),
                         dict(unit_template('c3po-massive.timer'),key='SUPERVISOR_TIMER',destination_name='c3po-massive.timer',mode=420,
                              profile='MASSIVE_SUPERVISOR_TIMER_V1',placeholders={},rendered_sha256=sha(timer),rendered_bytes=len(timer),expect='ABSENT')],
                'network_allowlist':[],'journal_placement':None,'data_volume_path':None,'deploy_tree_path':None,'template_revision':None,
                'acknowledged_leftovers':[],
                'daemon_reload_owner':None,'evidence_boot_id_sha256':None}
    if op=='readback':
        timer=template('c3po-massive.timer')
        return {'mode':None,'install':{'receipt_sha256':None,'outcome':None},'provision':{'receipt_sha256':None},
                'evidence_boot_id_sha256':None,
                'unit_directory':[NULL_ROW(path) for path in ('/','/etc','/etc/systemd','/etc/systemd/system')],
                'service':{'template_b64':unit_template('c3po-massive.service')['template_b64'],'rendered_sha256':None,'rendered_bytes':None,
                           'device':None,'inode':None},
                'timer':{'template_b64':unit_template('c3po-massive.timer')['template_b64'],'rendered_sha256':sha(timer),
                         'rendered_bytes':len(timer),'device':None,'inode':None},
                'substitutions':dict(SIX),'network_allowlist':[],'journal_placement':None,'journal_mount_point':None,'deploy_tree_path':None,
                'data_volume':{'path':None,'rows':None},
                'layout':{key:{'device':None,'inode':None} for key in module.LAYOUT_KEYS},
                'retention_reference':None,'image_revision':None,'free_space_floor_bytes':None,'sessions_retained':None,
                'other_writers_allowance_bytes':None,
                'catalog':{'expected':None,'receipt_sha256':None,'device':None,'inode':None}}
    if op=='precheck':
        return {'groups':['SUPERVISOR','JOURNAL_LEAF','READER','CAPACITY'],'journal_placement':None,'data_volume_path':None,'journal_leaf':None,
                'existing_journal_leaves':None,'capacity':{'root_path':None,'receipt_directory_path':None},
                'unit_names':['c3po-massive.service','c3po-massive.timer'],'image_reference':module.PRODUCTION_REFERENCE}
    raise SystemExit('OP')

def unbound_documents(op,module,source,runtime):
    """REQUEST, AUTHORITY, GO, DISPATCH and PUBLICATION_PROOF templates and the exact stdin payload built from them.
    Windows, date, host binding, owner, decisions, effects, target, key and known-hosts references, command pin,
    claim root and every observed identity are null; status is UNBOUND; execution_authorized is false. The five blob
    references of the dispatch template carry the hash of the unbound bytes and a null path: where a blob lies is a
    binding (the bind step writes the bound files and names them), so nothing generated here depends on, or shows,
    the directory this is run in."""
    p=OPS[op]
    plan={'schema':module.PLAN_SCHEMA,'status':'UNBOUND','phase':module.PHASE,'scope':module.SCOPE,
          'window':{'not_before':None,'expires_at':None},'host_binding_sha256':None,'max_seconds':module.MAX_SECONDS}
    plan.update(unbound_plan(op,module))
    request={'schema':module.REQUEST_SCHEMA,'status':'UNBOUND','operation':module.OPERATION,'phase':module.PHASE,'date':None,
             'not_before':None,'not_after':None,'host_binding_sha256':None,'payload_sha256':sha(source),
             'scope_sha256':module.SCOPE_SHA256,'executor_uid':0,'max_seconds':module.MAX_SECONDS,
             'writes_allowed':module.WRITES_ALLOWED,'activation_allowed':False,'evidence':[],'plan':plan}
    request_raw=canonical(request)
    authority={'schema':module.AUTHORITY_SCHEMA,'status':'UNBOUND','operation':module.OPERATION,'phase':module.PHASE,'owner':None,
               'decision':None,'execution_authorized':False,'request_sha256':sha(request_raw),'payload_sha256':sha(source),
               'effects':None,'host_binding_sha256':None,'not_before':None,'not_after':None,
               'writes_allowed':module.WRITES_ALLOWED,'activation_allowed':False,'owner_evidence':None}
    authority_raw=canonical(authority)
    go={'schema':module.GO_SCHEMA,'status':'UNBOUND','operation':module.OPERATION,'phase':module.PHASE,'owner':None,'action':None,
        'execution_authorized':False,'request_sha256':sha(request_raw),'authority_sha256':sha(authority_raw),
        'payload_sha256':sha(source),'effects':None,'host_binding_sha256':None,'not_before':None,'not_after':None,
        'writes_allowed':module.WRITES_ALLOWED,'activation_allowed':False,
        'claim_root_identity':{'path':None,'device':None,'inode':None},
        'transport_binding':{'target':None,'remote_command':REMOTE_COMMAND,'command_sha256':None,'runtime_sha256':runtime},
        'scope_statement':module.SCOPE_STATEMENT,'success_criterion':module.COMPLETE_OUTCOME if op!='readback' else None}   # readback: it follows the signed mode
    go_raw=canonical(go)
    payload=launcher_module().build(source,request_raw,authority_raw,go_raw,expected_payload_sha256=sha(source),
        expected_request_sha256=sha(request_raw),expected_authority_sha256=sha(authority_raw),expected_go_sha256=sha(go_raw))
    def item(name,raw):return {'path':None,'sha256':sha(raw)}
    config={'schema':p['stem']+'_DISPATCH_AUTHORIZATION_V1','status':'UNBOUND','decision':'UNBOUND','operation':module.OPERATION,
            'single_use':True,'retry':False,'owner':None,'authorization_ref':None,'executor_uid':0,'not_before':None,'not_after':None,
            'latest_start':None,'watchdog_seconds':80,'finalize_local_receipts_after_window':True,'runtime_sha256':runtime,
            'source':item(p['module']+'.py',source),'request':item('REQUEST.UNBOUND.json',request_raw),
            'authority':item('AUTHORITY.UNBOUND.json',authority_raw),'go':item('GO.UNBOUND.json',go_raw),
            'payload':item('FINAL_PAYLOAD.UNBOUND.py',payload),'host_binding_sha256':None,'target':None,
            'remote_command':REMOTE_COMMAND,'command_sha256':None,'ssh_key':{'path':None,'sha256':None},
            'known_hosts':{'path':None,'sha256':None},'attempt_directory':None,
            'local_root_identity':{'path':None,'device':None,'inode':None}}
    config_raw=canonical(config)
    proof={'schema':p['stem']+'_INTENT_PUBLICATION_V1','status':'UNBOUND','owner':None,'publication_ref':None,
           'go_sha256':sha(go_raw),'config_sha256':sha(config_raw),'intent_sha256':None,'published_at':None}
    return {'REQUEST.UNBOUND.json':request_raw,'AUTHORITY.UNBOUND.json':authority_raw,'GO.UNBOUND.json':go_raw,
            'DISPATCH.UNBOUND.json':config_raw,'PUBLICATION_PROOF.UNBOUND.json':canonical(proof),'FINAL_PAYLOAD.UNBOUND.py':payload}

def diff(old,new,old_name,new_name):
    return ''.join(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),old_name,new_name)).encode()

def main():
    launcher=launcher_bytes();transport=reviewed('transport_once.py');report={}
    (HERE/'LAUNCHER_DELTA.diff').write_bytes(diff(reviewed('launcher_stdin.py'),launcher,
        'reviewed_supervisor_hostfacts/launcher_stdin.py','hostops01/launcher_stdin.py'))
    for name in TEMPLATES:template(name)
    for op,p in OPS.items():
        directory=HERE/op;directory.mkdir(exist_ok=True)
        source=source_bytes(op);compile(source,p['module']+'.py','exec')
        (directory/(p['module']+'.py')).write_bytes(source)
        (directory/'launcher_stdin.py').write_bytes(launcher);(directory/'transport_once.py').write_bytes(transport)
        module=load(op)
        dispatcher=dispatcher_bytes(op,module);(directory/'dispatch_once.py').write_bytes(dispatcher)
        (directory/'DISPATCH_SCOPE_DELTA.diff').write_bytes(diff(reviewed('dispatch_once.py'),dispatcher,
            'reviewed_supervisor_hostfacts/dispatch_once.py','hostops01/%s/dispatch_once.py'%op))
        runtime={'dispatch_once.py':sha(dispatcher),'transport_once.py':sha(transport),'launcher_stdin.py':sha(launcher),
                 p['module']+'.py':sha(source)}
        for name,raw in unbound_documents(op,module,source,runtime).items():(directory/name).write_bytes(raw)
        base=reviewed('dispatch_once.py').decode().splitlines();new=dispatcher.decode().splitlines()
        report[op]={'source_sha256':sha(source),'source_bytes':len(source),'scope_sha256':module.SCOPE_SHA256,
                    'dispatcher_sha256':sha(dispatcher),'dispatcher_changed_lines':[index+1 for index,(a,b) in enumerate(zip(base,new)) if a!=b],
                    'dispatcher_line_count_equal':len(base)==len(new),
                    'final_payload_sha256':sha((directory/'FINAL_PAYLOAD.UNBOUND.py').read_bytes()),
                    'final_payload_bytes':len((directory/'FINAL_PAYLOAD.UNBOUND.py').read_bytes())}
    report['launcher_sha256']=sha(launcher);report['transport_sha256']=sha(transport)
    print(json.dumps(report,indent=1,sort_keys=True))

if __name__=='__main__':main()
