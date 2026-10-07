"""Render ONLY unsigned 08/10 PRIMARY PRE data. Never alters a signed copy.

The inventory authenticates source bytes; historical BOUND files themselves are
never rewritten. Host paths, attempt keys, candidates, dates and windows stay
exact. Only local evidence/document paths and the explanatory purpose change.
"""
import copy,hashlib,json,pathlib,re,os,stat
INVENTORY='8671e15a46627734dbcc133d59b42b574ffea134548d0cec408bec2177bb5e69'
OPERATIONS=('policy_read','capture_launch','capture_result','capture_cleanup')
class Refused(ValueError):pass
def need(value,code):
 if not value:raise Refused(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def strict(raw):
 def pairs(items):
  out={}
  for k,v in items:need(k not in out,'RENDER_DUPLICATE');out[k]=v
  return out
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:need(False,'RENDER_NONFINITE'))
def absolute(p):
 need(type(p) is str and p.startswith('/') and str(pathlib.PurePosixPath(p))==p
      and '..' not in pathlib.PurePosixPath(p).parts,'RENDER_PATH');return pathlib.PurePosixPath(p)
def render(base_raw,inventory_raw,private_root,family_root,operation):
 need(sha(inventory_raw)==INVENTORY,'RENDER_INVENTORY_PIN');inventory=strict(inventory_raw)
 need(inventory.get('schema')=='CAPTURE_PRIVATE_INPUT_INVENTORY_V1' and inventory.get('session')=='2026-10-08','RENDER_INVENTORY_SCOPE')
 private_root,family_root=absolute(private_root),absolute(family_root)
 need(operation in OPERATIONS,'RENDER_OPERATION');original=strict(base_raw)
 need(original.get('schema')=='BIND_ONCE_PARAMETERS_V1' and original.get('signature_model')=='PRE'
      and original.get('k9_grid')=='G19' and original.get('plan',{}).get('day')=='2026-10-08'
      and original['plan'].get('slot')=='PRIMARY' and original['plan'].get('k9_operation')==operation,'RENDER_BASE_SCOPE')
 rows=inventory['files'];matches=[r for r in rows if r['role']=='BASE_PARAMETERS_NOT_JOB_PARAMETERS' and r['bundle_path']=='base-parameters/'+original['label']+'/PARAMETERS.json']
 need(len(matches)==1 and matches[0]['sha256']==sha(base_raw) and matches[0]['bytes']==len(base_raw),'RENDER_BASE_PIN')
 source_to_alias={r['source_path']:r['bundle_path'] for r in rows}
 def relocated(source,role):
  absolute(source);exact=[(s,a) for s,a in source_to_alias.items() if s==source or s.startswith(source.rstrip('/')+'/')]
  need(exact,'RENDER_LOCAL_INPUT_NOT_LISTED')
  roots=set()
  for s,a in exact:
   tail=s[len(source):].lstrip('/')
   need(not tail or a.endswith('/'+tail),'RENDER_ALIAS_INCONSISTENT')
   roots.add(a[:-len(tail)-1] if tail else a)
  need(len(roots)==1,'RENDER_ALIAS_AMBIGUOUS');alias=roots.pop();need(not alias.startswith('/') and '..' not in pathlib.PurePosixPath(alias).parts,'RENDER_ALIAS_PATH')
  return str(private_root/alias)
 out=copy.deepcopy(original)
 for e in out['evidence']:
  e['bound']=relocated(e['bound'],e['role'])
  family=absolute(e['family']).name
  need(family in inventory['source_families'],'RENDER_FAMILY_NOT_LISTED');e['family']=str(family_root/family)
 for key in ('linux_job','review'):
  out[key]['document_file']=relocated(out[key]['document_file'],key)
 out['purpose_pt']='Conferir ou executar '+operation+' na janela fixada do G19, sessão08/10, nesta instância Linux própria. Exige aprovação do dono e gates próprios.'
 need(out['plan']==original['plan'] and all(out[k]==original[k] for k in original if k not in ('evidence','linux_job','review','purpose_pt')),'RENDER_SIGNED_SEMANTICS_CHANGED')
 return canonical(out)
def private_read(path,limit):
 p=pathlib.Path(path);absolute(str(p))
 for part in (p,*p.parents):need(not part.is_symlink(),'RENDER_INPUT_LINK')
 fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  a=os.fstat(f.fileno());need(stat.S_ISREG(a.st_mode) and a.st_uid==os.getuid() and a.st_nlink==1 and stat.S_IMODE(a.st_mode)==0o600 and 0<a.st_size<=limit,'RENDER_INPUT_PRIVATE')
  raw=f.read(limit+1);b=os.fstat(f.fileno())
 def identity(t):return t.st_dev,t.st_ino,t.st_size,t.st_mtime_ns,t.st_ctime_ns
 need(identity(a)==identity(b)==identity(p.lstat()) and len(raw)==a.st_size,'RENDER_INPUT_CHANGED')
 return raw
def main():
 import argparse,os
 ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--base',required=True);ap.add_argument('--inventory',required=True);ap.add_argument('--private-root',required=True);ap.add_argument('--family-root',required=True);ap.add_argument('--operation',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
 from pathlib import Path
 raw=render(private_read(a.base,65536),private_read(a.inventory,1024*1024),a.private_root,a.family_root,a.operation)
 p=Path(a.out);need(p.is_absolute() and p.parent.is_dir() and stat.S_IMODE(p.parent.stat().st_mode)==0o700 and p.parent.stat().st_uid==os.getuid(),'RENDER_OUTPUT')
 for q in p.parents:need(not q.is_symlink(),'RENDER_OUTPUT_LINK')
 fd=os.open(str(p),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 print(json.dumps(dict(status='UNSIGNED_PARAMETERS_RENDERED',parameters_sha256=sha(raw),operational_READY=False)))
if __name__=='__main__':main()
