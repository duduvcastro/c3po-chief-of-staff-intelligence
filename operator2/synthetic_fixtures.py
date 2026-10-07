"""Harmless fixtures for isolated proofs only. Never owner answers or runtime PASS."""
import pathlib,json,types,hashlib,base64
HOME=pathlib.Path(__file__).resolve().parent
m=types.ModuleType('fixture_capsule_data');m.__file__=str(HOME/'capsule_data.py');exec(compile((HOME/'capsule_data.py').read_bytes(),m.__file__,'exec'),m.__dict__)
CTX=dict(session='2026-10-08',run_id='12345678901',run_attempt=1,nonce='a'*32)
MARKER=b'SYNTHETIC_NEVER_EXECUTE_OR_DISPATCH\n'
def blob(b):return dict(sha=m.gitsha(b),url=m.ROOT+'/git/blobs/'+m.gitsha(b),encoding='base64',size=len(b),content=base64.b64encode(b).decode())
def fake_cipher(tag=b''):
 return b'age-encryption.org/v1\n-> X25519 SYNTHETIC\n'+base64.b64encode(tag or MARKER)+b'\n--- SYNTHETIC\n'+MARKER

def context():return m.canonical(dict(schema='CAPTURE_OPERATOR_JOB_CONTEXT_V1',**CTX,source_public_comment_id=1,source_public_body_sha256='b'*64,source_public_created_at='2026-10-08T11:46:00Z',source_head_sha='c'*40,source_layout_sha256=m.LAYOUT,dated_authority_sha256=m.AUTHORITY,recipient='age1'+'q'*58))
def comment(body,cid=1):
 return dict(id=cid,url=m.ROOT+'/issues/comments/'+str(cid),issue_url=m.ROOT+'/issues/429',created_at='2026-10-08T11:46:00Z',updated_at='2026-10-08T11:46:00Z',user=dict(login='github-actions[bot]',id=m.BOT_ID,type='Bot'),author_association='NONE',performed_via_github_app=dict(slug='github-actions'),body=m.canonical(body).decode())
def ephemeral_fixtures():
 a=pathlib.Path(__file__).resolve().parents[1]/'fable-capture-operator-private-20261008/DATED_AUTHORITY.json'
 # Only the existing documentary authority is used as a pinned fixture input; no job is created.
 authority=a.read_bytes() if a.is_file() else (HOME/'reference/DATED_AUTHORITY.fixture.json').read_bytes()
 v=dict(schema='CAPTURE_JOB_PUBLIC_V1',kind='EPHEMERAL_RECIPIENT',**CTX,recipient='age1'+'q'*58,manifest_sha256=m.INVENTORY,status='AWAITING_PRIVATE_INPUTS');c=comment(v)
 index=m.strict((HOME/'reference/SOURCE_GIT_BLOBS.json').read_bytes());wf=(HOME/'reference/capture-thursday-single-job.yml').read_bytes();head='d'*40
 tree_sha='e'*40;commit=dict(sha=head,url=m.ROOT+'/git/commits/'+head,tree=dict(sha=tree_sha,url=m.ROOT+'/git/trees/'+tree_sha))
 tree=dict(sha=tree_sha,url=m.ROOT+'/git/trees/'+tree_sha,truncated=False,tree=[dict(path=r['path'],sha=r['git_blob_sha'],type='blob',size=r['bytes']) for r in index['files']]+[dict(path='.github/workflows/capture-thursday-single-job.yml',sha=m.gitsha(wf),type='blob',size=len(wf)),dict(path='capture-authority/DATED_AUTHORITY.json',sha=m.gitsha(authority),type='blob',size=len(authority))])
 run=dict(id=int(CTX['run_id']),run_attempt=1,repository=dict(full_name='duduvcastro/c3po-chief-of-staff-intelligence'),event='push',head_branch='ops/capture-thursday-single-job-20261008',path='.github/workflows/capture-thursday-single-job.yml',status='in_progress',conclusion=None,head_sha=head,created_at='2026-10-08T11:45:20Z');return c,run,commit,tree,authority

def rows(op,slot='PRIMARY',host='a'*64,boot='b'*64):
 label='synthetic-'+op.replace('_','-');authority_name='SYNTHETIC_AUTHORITY.json';go_name='SYNTHETIC_GO.json';success={'commit_result':'K9_PHASE_RESULT_COMPLETE_ALL_OBSERVED','publish_launch':'K9_STEP_LAUNCHED_DETACHED_READ_BACK'}[op]
 plan=dict(day='2026-10-08',slot=slot,k9_operation=op,evidence_boot_id_sha256=boot,attempt_key=m.sha(op.encode()),host_binding_sha256=host)
 request=m.canonical(dict(plan=plan,host_binding_sha256=host));params=m.canonical(dict(k9_grid='G19',plan=plan));auth=m.canonical(dict(status='SYNTHETIC_NOT_OWNER_AUTHORITY'));go=m.canonical(dict(status='SYNTHETIC_NOT_OWNER_GO'));payload=MARKER;source=MARKER
 pinned={'REQUEST.BOUND.json':request,'PARAMETERS.json':params,'GO_SCOPE.txt':MARKER,'EFFECTS.json':b'{}','source.py':source,'templates/REQUEST.UNBOUND.json':b'{}'}
 sheet=dict(label=label,profile='core',mode='REAL',authority_name=authority_name,go_name=go_name,files_sha256={n:m.sha(b) for n,b in pinned.items()},host_binding_sha256=host,request_sha256=m.sha(request),parameters_sha256=m.sha(params),source_sha256=m.sha(source),success_criterion=success,prepared_at_utc='2026-10-07T12:00:00Z')
 cfg=m.canonical(dict(retry=False,single_use=True,host_binding_sha256=host,request=dict(sha256=m.sha(request)),go=dict(sha256=m.sha(go)),authority=dict(sha256=m.sha(auth)),payload=dict(sha256=m.sha(payload))))
 base={**pinned,'PREPARE.json':m.canonical(sheet),'OWNER_QUESTION.txt':MARKER,authority_name:auth,go_name:go,'FINAL_PAYLOAD.BOUND.py':payload,'DISPATCH.BOUND.json':cfg,'CLAIM_ROOT_IDENTITY.json':b'{}'}
 base['SHA256SUMS']=''.join(m.sha(b)+'  '+n+'\n' for n,b in sorted(base.items())).encode()
 receipt=dict(status='METADATA_ONLY_REQUIRES_REVIEW',outcome=success,request_sha256=m.sha(request),authority_sha256=m.sha(auth),go_sha256=m.sha(go),payload_sha256=m.sha(source),host_binding_sha256=host,fixture='SYNTHETIC_NOT_REAL_NIGHT');receipt['metadata_sha256']=m.sha(m.canonical(receipt));stdout=m.canonical(receipt);stderr=b'';finished='2026-10-07T23:10:00Z' if op=='commit_result' else '2026-10-07T23:20:00Z'
 ex=m.canonical(dict(status='KNOWN_COMPLETE',returncode=0,config_sha256=m.sha(cfg),request_sha256=m.sha(request),go_sha256=m.sha(go),stdout_sha256=m.sha(stdout),stderr_sha256=m.sha(stderr),finished_at=finished));at='.dispatch-root/'+label+'-once/'
 base.update({at+'exit.json':ex,at+'intent.json':MARKER,at+'spawn.claim':MARKER,at+'stdout.private.json':stdout,at+'stderr.private':stderr,'.dispatch-root/.go-'+m.sha(go)+'.claim':MARKER});return base

def write_bound(path,rows):
 path=pathlib.Path(path);path.mkdir(mode=0o700)
 for n,b in sorted(rows.items()):
  dest=path/n;dest.parent.mkdir(mode=0o700,parents=True,exist_ok=True);m.put(dest,b)
 return path
