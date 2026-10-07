"""Private operator data only. No network, app imports, encryption child or dispatch.

Publication/encryption are Fable actions. A finished-byte capsule is evidence;
its original signed programs and the physical-job binder remain authoritative.
"""
import argparse,base64,datetime as dt,hashlib,io,json,os,pathlib,re,stat,tarfile
ROOT='https://api.github.com/repos/duduvcastro/c3po-chief-of-staff-intelligence'
LAYOUT='b106708d7e72d3c6b529021a1a35fa85d1076a52eb01883cd7b28597334eeac0'
WORKFLOW='3413dc4d76fcca5e65e092ed57b6c2b644cf0bc58be1c3ef4fbcdb3b8332012f'
AUTHORITY='c0af50a35a90cb226346d775cd8854db1afc681744a8255a383a1d8de45677bc'
INVENTORY='8671e15a46627734dbcc133d59b42b574ffea134548d0cec408bec2177bb5e69'
INPUT_TAR='1580db0b3e72dcb92c2f81ee167ca02a7a28e8b73c1eefc9cecc95bf2bad6cd6'
SOURCE_INDEX='d726d8e7764dc9cc8da8c8c85fd52f60239a64f81cf5a28e6030592c2e5e8b91'
BOT_ID=41898282
OPS=('commit_result','publish_launch')
PATH=re.compile(r'(commit_result|publish_launch)/bound/(?:[A-Za-z0-9_.-]{1,100}|templates/[A-Za-z0-9_.-]{1,100}|\.dispatch-root/\.go-[0-9a-f]{64}\.claim|\.dispatch-root/[a-z0-9-]{1,100}-once/(?:exit.json|intent.json|spawn.claim|stderr.private|stdout.private.json))')
class Refused(ValueError):pass
def need(v,code):
    if not v:raise Refused(code)
def sha(b):return hashlib.sha256(b).hexdigest()
def gitsha(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def strict(b):
    def pairs(rows):
        v={}
        for k,x in rows:need(k not in v,'DUPLICATE_JSON_FIELD');v[k]=x
        return v
    return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda _:need(False,'NONFINITE_JSON'))
def pin(v):need(type(v) is str and re.fullmatch('[0-9a-f]{64}',v),'HASH');return v
def instant(v):
    need(type(v) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',v),'UTC_TIME')
    return dt.datetime.fromisoformat(v.replace('Z','+00:00'))
def receipt_instant(v):
    need(type(v) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)',v),'RECEIPT_UTC_TIME');return dt.datetime.fromisoformat(v.replace('Z','+00:00'))
def ident(s):return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns
def safe_path(p):
    p=pathlib.Path(p).absolute()
    for q in (p,*p.parents):need(not q.is_symlink(),'INPUT_LINK')
    return p
def read(p,limit=16*1024*1024,empty=False):
    p=safe_path(p);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        a=os.fstat(f.fileno());need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_uid==os.getuid() and not a.st_mode&0o022 and 0<=a.st_size<=limit and (a.st_size or empty),'INPUT_FILE');b=f.read(limit+1);z=os.fstat(f.fileno())
    need(ident(a)==ident(z)==ident(p.lstat()) and len(b)==a.st_size,'INPUT_CHANGED');return b

def put(p,b):
    p=safe_path(p);need(p.parent.is_dir(),'OUTPUT_PARENT');fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
def output_dir(p):
    p=safe_path(p);need(p.parent.is_dir() and not p.exists(),'OUTPUT_ALREADY_EXISTS');p.mkdir(mode=0o700);return p

def location(c):
    need(type(c) is dict and type(c.get('id')) is int and c['id']>0 and c.get('url')==ROOT+'/issues/comments/'+str(c['id']) and c.get('issue_url')==ROOT+'/issues/429' and c.get('created_at')==c.get('updated_at'),'COMMENT_LOCATION_OR_EDIT');instant(c['created_at']);need(type(c.get('body')) is str,'COMMENT_BODY');return strict(c['body'])
def bot_comment(c):
    body=location(c);u=c.get('user',{});app=c.get('performed_via_github_app')
    need(u.get('login')=='github-actions[bot]' and u.get('id')==BOT_ID and u.get('type')=='Bot','COMMENT_NOT_ACTIONS_BOT')
    need(app is None or type(app) is dict and app.get('slug')=='github-actions','COMMENT_UNEXPECTED_APP');return body

def own_context(v,session='2026-10-08'):
    need(v.get('session')==session and type(v.get('run_id')) is str and re.fullmatch('[1-9][0-9]{5,19}',v['run_id']) and type(v.get('run_attempt')) is int and v['run_attempt']==1 and type(v.get('nonce')) is str and re.fullmatch('[0-9a-f]{32}',v['nonce']),'JOB_CONTEXT');return {k:v[k] for k in ('session','run_id','run_attempt','nonce')}

def ephemeral(first,second,run,commit,tree,authority,now):
    need(first==second,'EPHEMERAL_READBACK_CHANGED');v=bot_comment(first);ctx=own_context(v)
    need(set(v)=={'schema','kind',*ctx,'recipient','manifest_sha256','status'} and v['schema']=='CAPTURE_JOB_PUBLIC_V1' and v['kind']=='EPHEMERAL_RECIPIENT' and v['status']=='AWAITING_PRIVATE_INPUTS' and v['manifest_sha256']==INVENTORY,'EPHEMERAL_BODY')
    need(type(v['recipient']) is str and re.fullmatch('age1[023456789acdefghjklmnpqrstuvwxyz]{58}',v['recipient']),'EPHEMERAL_RECIPIENT')
    need(type(run) is dict and run.get('id')==int(ctx['run_id']) and type(run.get('run_attempt')) is int and run['run_attempt']==1 and run.get('repository',{}).get('full_name')=='duduvcastro/c3po-chief-of-staff-intelligence' and run.get('event')=='push' and run.get('head_branch')=='ops/capture-thursday-single-job-20261008' and run.get('path')=='.github/workflows/capture-thursday-single-job.yml' and run.get('status')=='in_progress' and run.get('conclusion') is None,'EPHEMERAL_RUN')
    head=run.get('head_sha');need(type(head) is str and re.fullmatch('[0-9a-f]{40}',head),'RUN_HEAD')
    need(commit.get('sha')==head and commit.get('url')==ROOT+'/git/commits/'+head and type(commit.get('tree')) is dict,'RUN_COMMIT');tree_sha=commit['tree'].get('sha');need(type(tree_sha) is str and re.fullmatch('[0-9a-f]{40}',tree_sha) and commit['tree'].get('url')==ROOT+'/git/trees/'+tree_sha,'RUN_COMMIT_TREE')
    need(tree.get('sha')==tree_sha and tree.get('url')==ROOT+'/git/trees/'+tree_sha and tree.get('truncated') is False and type(tree.get('tree')) is list,'RUN_TREE')
    w=[r for r in tree['tree'] if r.get('type')=='blob' and r.get('path','').startswith('.github/workflows/')]
    expected=pathlib.Path(__file__).parent/'reference/capture-thursday-single-job.yml';workflow=read(expected)
    index_raw=read(pathlib.Path(__file__).parent/'reference/SOURCE_GIT_BLOBS.json');need(sha(index_raw)==SOURCE_INDEX,'SOURCE_INDEX_PIN');index=strict(index_raw);blobs={r.get('path'):r for r in tree['tree'] if r.get('type')=='blob'}
    need(all(blobs.get(r['path'],{}).get('sha')==r['git_blob_sha'] and blobs.get(r['path'],{}).get('size')==r['bytes'] for r in index['files']),'RUN_SOURCE_BYTES')
    need(blobs.get('capture-authority/DATED_AUTHORITY.json',{}).get('sha')==gitsha(authority),'RUN_AUTHORITY_BYTES')
    need(sha(workflow)==WORKFLOW and len(w)==1 and w[0].get('path')==run['path'] and w[0].get('sha')==gitsha(workflow),'RUN_WORKFLOW_BYTES')
    need(sha(authority)==AUTHORITY,'DATED_AUTHORITY_BYTES');a=strict(authority);need(a.get('source_layout_sha256')==LAYOUT and a.get('session')==ctx['session'],'DATED_AUTHORITY_CONTEXT')
    need(instant('2026-10-08T11:45:00Z')<=instant(run['created_at'])<=instant(first['created_at'])<=now<=instant('2026-10-08T11:50:00Z'),'EPHEMERAL_WINDOW')
    return dict(schema='CAPTURE_OPERATOR_JOB_CONTEXT_V1',**ctx,source_public_comment_id=first['id'],source_public_body_sha256=sha(first['body'].encode()),source_public_created_at=first['created_at'],source_head_sha=head,source_layout_sha256=LAYOUT,dated_authority_sha256=AUTHORITY,recipient=v['recipient'])

def context_file(raw):
    v=strict(raw);ctx=own_context(v)
    need(set(v)=={'schema',*ctx,'source_public_comment_id','source_public_body_sha256','source_public_created_at','source_head_sha','source_layout_sha256','dated_authority_sha256','recipient'} and v['schema']=='CAPTURE_OPERATOR_JOB_CONTEXT_V1' and v['source_layout_sha256']==LAYOUT and v['dated_authority_sha256']==AUTHORITY and type(v['source_public_comment_id']) is int and v['source_public_comment_id']>0,'CONTEXT_FIELDS')
    pin(v['source_public_body_sha256']);need(re.fullmatch('[0-9a-f]{40}',v['source_head_sha']) and re.fullmatch('age1[023456789acdefghjklmnpqrstuvwxyz]{58}',v['recipient']),'CONTEXT_PINS');need(instant('2026-10-08T11:45:00Z')<=instant(v['source_public_created_at'])<=instant('2026-10-08T11:50:00Z'),'CONTEXT_TIME');need(raw==canonical(v),'CONTEXT_NOT_CANONICAL');return v,ctx

def cipher(b):need(0<len(b)<=16*1024*1024 and b.startswith(b'age-encryption.org/v1\n') and b.find(b'\n--- ')>0,'CIPHERTEXT_FORMAT');return b

def blob_request(raw):return canonical(dict(content=base64.b64encode(cipher(raw)).decode(),encoding='base64'))
def blob_readback(raw,v):
    cipher(raw);need(type(v) is dict and v.get('sha')==gitsha(raw) and v.get('url')==ROOT+'/git/blobs/'+gitsha(raw) and v.get('encoding')=='base64' and type(v.get('size')) is int and v['size']==len(raw) and type(v.get('content')) is str,'BLOB_METADATA');b=base64.b64decode(v['content'].replace('\n',''),validate=True);need(b==raw,'BLOB_READBACK_BYTES');return gitsha(raw),sha(raw)

def private_inputs(context,archive,inventory,archive_cipher,inventory_cipher,archive_blob,inventory_blob,now):
    v,ctx=context_file(context);need(instant(v['source_public_created_at'])<=now<=instant('2026-10-08T11:50:00Z'),'PRIVATE_INPUTS_DEADLINE');need(sha(archive)==INPUT_TAR and sha(inventory)==INVENTORY,'FIXED_PRIVATE_INPUT_PINS')
    b,c=blob_readback(archive_cipher,archive_blob);mb,mc=blob_readback(inventory_cipher,inventory_blob)
    return dict(schema='CAPTURE_JOB_CONTROL_V1',kind='PRIVATE_INPUTS',sequence=1,**ctx,document_sha256=INVENTORY,blob_sha=b,ciphertext_sha256=c,manifest_sha256=INVENTORY,manifest_blob_sha=mb,manifest_ciphertext_sha256=mc)

def sums(raw):
    v={}
    for line in raw.decode('ascii').splitlines():
        m=re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_./-]+)',line);need(m and m[2] not in v,'BOUND_SUMS');v[m[2]]=m[1]
    return v

def bound_files(bound,op,slot):
    """Copy only the exact signed set and its completed attempt. Never follows its references."""
    p=safe_path(bound);need(p.is_dir() and p.stat().st_uid==os.getuid() and not p.stat().st_mode&0o022,'BOUND_DIRECTORY');rows={};dirs={};file_ids={};start=ident(p.stat())
    for q in sorted(p.rglob('*')):
        rel=q.relative_to(p).as_posix();need(not q.is_symlink(),'BOUND_LINK');s=q.lstat()
        if stat.S_ISDIR(s.st_mode):need(s.st_uid==os.getuid() and not s.st_mode&0o022,'BOUND_DIRECTORY_MODE');dirs[rel]=ident(s)
        else:
            need(PATH.fullmatch(op+'/bound/'+rel),'BOUND_PATH');rows[rel]=read(q,2*1024*1024,True);file_ids[rel]=ident(q.lstat());need(len(rows)<=255 and sum(map(len,rows.values()))<=16*1024*1024,'BOUND_SIZE')
    need(ident(p.stat())==start and all(ident((p/n).lstat())==i for n,i in {**dirs,**file_ids}.items()),'BOUND_TREE_CHANGED')
    return validate_bound_rows(rows,op,slot)

def validate_bound_rows(rows,op,slot):
    required={'PREPARE.json','OWNER_QUESTION.txt','PARAMETERS.json','REQUEST.BOUND.json','DISPATCH.BOUND.json','CLAIM_ROOT_IDENTITY.json','GO_SCOPE.txt','FINAL_PAYLOAD.BOUND.py','SHA256SUMS'};need(required<=set(rows),'BOUND_REQUIRED')
    sheet=strict(rows['PREPARE.json']);params=strict(rows['PARAMETERS.json']);request=strict(rows['REQUEST.BOUND.json']);config=strict(rows['DISPATCH.BOUND.json']);need(type(sheet) is dict and type(params) is dict and type(request) is dict and type(config) is dict and type(request.get('plan')) is dict and type(params.get('plan')) is dict and type(sheet.get('files_sha256')) is dict and all(k in sheet for k in ('label','authority_name','go_name','host_binding_sha256','request_sha256','parameters_sha256','source_sha256','success_criterion','prepared_at_utc')),'BOUND_DOCUMENT_SHAPE');plan=request['plan'];label=sheet['label']
    need(type(label) is str and re.fullmatch('[a-z0-9-]{1,100}',label) and sheet.get('profile')=='core' and sheet.get('mode')=='REAL','BOUND_SHEET')
    need(params.get('k9_grid')=='G19' and plan.get('day')=='2026-10-08' and plan.get('slot')==slot and plan.get('k9_operation')==op and all(params['plan'].get(k)==plan[k] for k in ('day','slot','k9_operation','evidence_boot_id_sha256','attempt_key')),'NIGHT_BRANCH')
    host=pin(sheet['host_binding_sha256']);boot=pin(plan['evidence_boot_id_sha256']);need(request['host_binding_sha256']==host and plan['host_binding_sha256']==host and sha(rows['REQUEST.BOUND.json'])==sheet['request_sha256'] and sha(rows['PARAMETERS.json'])==sheet['parameters_sha256'],'BOUND_IDENTITY')
    signed={sheet['authority_name'],sheet['go_name'],'FINAL_PAYLOAD.BOUND.py','DISPATCH.BOUND.json','CLAIM_ROOT_IDENTITY.json','SHA256SUMS'};base=set(sheet['files_sha256'])|{'PREPARE.json','OWNER_QUESTION.txt'}|signed
    proofs={n for n in rows if re.fullmatch(r'PUBLICATION\.PROOF(\.R[2-9])?\.json',n)};need(len(proofs)<=1,'PUBLICATION_PROOF_RETRY')
    attempt='.dispatch-root/'+label+'-once/';go=rows[sheet['go_name']];go_hash=sha(go);claim='.dispatch-root/.go-'+go_hash+'.claim';names={attempt+n for n in ('exit.json','intent.json','spawn.claim','stderr.private','stdout.private.json')}
    need(set(rows)==base|proofs|names|{claim},'BOUND_EXACT_SET');need(all(sha(rows[n])==pin(h) for n,h in sheet['files_sha256'].items()),'PREPARE_FILE_PINS')
    need(sums(rows['SHA256SUMS'])=={n:sha(rows[n]) for n in base if n!='SHA256SUMS'},'SIGNED_FILE_PINS')
    need(config.get('retry') is False and config.get('single_use') is True and config.get('host_binding_sha256')==host and config['request']['sha256']==sheet['request_sha256'] and config['go']['sha256']==go_hash and config['authority']['sha256']==sha(rows[sheet['authority_name']]) and config['payload']['sha256']==sha(rows['FINAL_PAYLOAD.BOUND.py']),'DISPATCH_BINDINGS')
    exraw=rows[attempt+'exit.json'];ex=strict(exraw);stdout=rows[attempt+'stdout.private.json'];stderr=rows[attempt+'stderr.private'];receipt=strict(stdout)
    need(exraw==canonical(ex) and ex.get('status')=='KNOWN_COMPLETE' and ex.get('returncode')==0 and ex.get('config_sha256')==sha(rows['DISPATCH.BOUND.json']) and ex.get('request_sha256')==sheet['request_sha256'] and ex.get('go_sha256')==go_hash and ex.get('stdout_sha256')==sha(stdout) and ex.get('stderr_sha256')==sha(stderr) and stderr==b'','NIGHT_TRANSPORT_INCOMPLETE')
    r=dict(receipt);metadata=r.pop('metadata_sha256',None);need(metadata==sha(canonical(r)) and receipt.get('status')=='METADATA_ONLY_REQUIRES_REVIEW' and receipt.get('outcome')==sheet['success_criterion'] and receipt.get('request_sha256')==sheet['request_sha256'] and receipt.get('authority_sha256')==sha(rows[sheet['authority_name']]) and receipt.get('go_sha256')==go_hash and receipt.get('payload_sha256')==sheet['source_sha256'] and receipt.get('host_binding_sha256')==host,'NIGHT_RECEIPT_BINDINGS')
    expected={'commit_result':'K9_PHASE_RESULT_COMPLETE_ALL_OBSERVED','publish_launch':'K9_STEP_LAUNCHED_DETACHED_READ_BACK'};need(sheet['success_criterion']==expected[op],'NIGHT_OUTCOME');need(receipt_instant(ex['finished_at'])>=instant(sheet['prepared_at_utc']),'NIGHT_RESULT_ORDER')
    # Do not turn this structural check into the physical-job binder's executable verdict.
    return {op+'/bound/'+n:b for n,b in rows.items()},dict(slot=slot,host=host,boot=boot,finished_at=ex['finished_at'],request_sha256=sheet['request_sha256'],receipt_sha256=sha(stdout))

def tar_bytes(rows):
    b=io.BytesIO()
    with tarfile.open(fileobj=b,mode='w',format=tarfile.USTAR_FORMAT) as t:
        for n,raw in sorted(rows.items()):
            info=tarfile.TarInfo(n);info.size=len(raw);info.mode=0o600;info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0;t.addfile(info,io.BytesIO(raw))
    raw=b.getvalue();need(len(rows)<=256 and len(raw)<=16*1024*1024,'NIGHT_CAPSULE_LIMIT');return raw

def night_capsule(commit,publish,slot,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    a,aa=bound_files(commit,'commit_result',slot);b,bb=bound_files(publish,'publish_launch',slot);need(aa['host']==bb['host'] and aa['boot']==bb['boot'],'NIGHT_HOST_OR_BOOT_MISMATCH');need(receipt_instant(aa['finished_at'])<=receipt_instant(bb['finished_at'])<=now,'NIGHT_CAUSAL_ORDER');rows={**a,**b}
    m=dict(schema='CAPTURE_NIGHT_EVIDENCE_V1',session='2026-10-08',grid='G19',slot=slot,files=[dict(path=n,bytes=len(raw),sha256=sha(raw)) for n,raw in sorted(rows.items())]);manifest=canonical(m);return tar_bytes({**rows,'MANIFEST.private.json':manifest}),manifest,dict(schema='CAPTURE_OPERATOR_NIGHT_BYTES_V1',status='STRUCTURAL_FINISHED_BYTES_ONLY_REQUIRES_JOB_BINDER_REDERIVATION',slot=slot,files=len(rows),manifest_sha256=sha(manifest),complete_received_pairs=2,operational_READY=False)

def inspect_night_tar(raw,manifest,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    need(0<len(raw)<=16*1024*1024 and len(raw)%512==0,'NIGHT_TAR_SIZE');rows={};used=0
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as t:
        for m in t:
            need(m.isfile() and m.type==tarfile.REGTYPE and not m.pax_headers and not m.linkname and m.uid==m.gid==0 and m.size<=2*1024*1024 and m.name not in rows and (m.name=='MANIFEST.private.json' or PATH.fullmatch(m.name)) and m.offset_data==m.offset+512 and raw[m.offset+257:m.offset+265]==b'ustar\x0000','NIGHT_TAR_MEMBER');rows[m.name]=t.extractfile(m).read();used=max(used,m.offset_data+((m.size+511)//512)*512)
    need(len(rows)<=256 and len(raw)-used>=1024 and not any(raw[used:]) and rows.pop('MANIFEST.private.json',None)==manifest,'NIGHT_TAR_MANIFEST_OR_END');v=strict(manifest);need(manifest==canonical(v) and set(v)=={'schema','session','grid','slot','files'} and v['schema']=='CAPTURE_NIGHT_EVIDENCE_V1' and v['session']=='2026-10-08' and v['grid']=='G19' and v['slot'] in ('PRIMARY','SPARE'),'NIGHT_MANIFEST')
    need(type(v['files']) is list and len(rows)==len(v['files']),'NIGHT_MANIFEST_COUNT');listed={}
    for r in v['files']:
        need(set(r)=={'path','bytes','sha256'} and r['path'] in rows and r['path'] not in listed and type(r['bytes']) is int and r['bytes']==len(rows[r['path']]) and r['sha256']==sha(rows[r['path']]),'NIGHT_MANIFEST_ROW');listed[r['path']]=True
    pairs=[]
    for op in OPS:
        subset={n[len(op+'/bound/'):]:b for n,b in rows.items() if n.startswith(op+'/bound/')}
        _,facts=validate_bound_rows(subset,op,v['slot']);pairs.append(facts)
    need(pairs[0]['host']==pairs[1]['host'] and pairs[0]['boot']==pairs[1]['boot'],'NIGHT_HOST_OR_BOOT_MISMATCH');need(receipt_instant(pairs[0]['finished_at'])<=receipt_instant(pairs[1]['finished_at'])<=now,'NIGHT_CAUSAL_ORDER')
    return v

def night_gates(context,archive,manifest,ciphertext,blob,now):
    v,ctx=context_file(context);need(instant(v['source_public_created_at'])<=now<=instant('2026-10-08T13:58:39Z'),'NIGHT_GATES_DEADLINE');inspect_night_tar(archive,manifest,now);b,c=blob_readback(ciphertext,blob);h=sha(manifest)
    return dict(schema='CAPTURE_JOB_CONTROL_V1',kind='NIGHT_GATES',sequence=1,**ctx,document_sha256=h,manifest_sha256=h,blob_sha=b,ciphertext_sha256=c)

COMMANDS=('ephemeral-context','blob-requests','private-inputs','night-capsule','night-gates')
def main(argv=None):
    ap=argparse.ArgumentParser(allow_abbrev=False);sub=ap.add_subparsers(dest='command',required=True)
    s=sub.add_parser('ephemeral-context')
    for k in ('public-readback1','public-readback2','run-readback','commit-readback','tree-readback','dated-authority','out'):s.add_argument('--'+k,required=True)
    s=sub.add_parser('blob-requests');s.add_argument('--cipher',required=True,action='append');s.add_argument('--out',required=True)
    s=sub.add_parser('private-inputs')
    for k in ('context','archive','inventory','archive-cipher','inventory-cipher','archive-blob-readback','inventory-blob-readback','out'):s.add_argument('--'+k,required=True)
    s=sub.add_parser('night-capsule');s.add_argument('--commit-bound',required=True);s.add_argument('--publish-bound',required=True);s.add_argument('--slot',required=True,choices=('PRIMARY','SPARE'));s.add_argument('--out',required=True)
    s=sub.add_parser('night-gates')
    for k in ('context','archive','manifest','cipher','blob-readback','out'):s.add_argument('--'+k,required=True)
    a=ap.parse_args(argv);now=dt.datetime.now(dt.timezone.utc);j=lambda p:strict(read(p,32*1024*1024))
    if a.command=='ephemeral-context':put(a.out,canonical(ephemeral(j(a.public_readback1),j(a.public_readback2),j(a.run_readback),j(a.commit_readback),j(a.tree_readback),read(a.dated_authority),now)))
    elif a.command=='blob-requests':
        out=output_dir(a.out)
        for i,p in enumerate(a.cipher,1):
            raw=read(p);put(out/('BLOB'+str(i)+'.request.json'),blob_request(raw));put(out/('BLOB'+str(i)+'.metadata.private.json'),canonical(dict(ciphertext_sha256=sha(raw),blob_sha=gitsha(raw),bytes=len(raw))))
    elif a.command=='private-inputs':put(a.out,canonical(dict(body=canonical(private_inputs(read(a.context),read(a.archive),read(a.inventory),read(a.archive_cipher),read(a.inventory_cipher),j(a.archive_blob_readback),j(a.inventory_blob_readback),now)).decode())))
    elif a.command=='night-capsule':
        archive,manifest,report=night_capsule(a.commit_bound,a.publish_bound,a.slot);out=output_dir(a.out);put(out/'NIGHT_GATES.private.tar',archive);put(out/'MANIFEST.private.json',manifest);put(out/'BUILD.private.json',canonical(dict(**report,archive_sha256=sha(archive),archive_bytes=len(archive))))
    else:put(a.out,canonical(dict(body=canonical(night_gates(read(a.context),read(a.archive),read(a.manifest),read(a.cipher),j(a.blob_readback),now)).decode())))
    print('{"status":"OPERATOR_DATA_ONLY_NOT_SIGNATURE_RUNTIME_PASS_OR_GO"}')
if __name__=='__main__':
    try:main()
    except Exception:print('{"status":"OPERATOR_DATA_REFUSED_NO_RETRY"}');raise SystemExit(2)
