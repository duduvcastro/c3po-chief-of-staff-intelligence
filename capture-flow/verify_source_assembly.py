"""Read/hash/AST assembly proof. Never imports app, prepares, signs or transports."""
import argparse,ast,hashlib,json,pathlib,sys,types

def main():
 ap=argparse.ArgumentParser(allow_abbrev=False)
 for k in ('root','layout','layout-sha256','out'):ap.add_argument('--'+k,required=True)
 a=ap.parse_args();root=pathlib.Path(a.root);raw=pathlib.Path(a.layout).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=a.layout_sha256:raise ValueError('ASSEMBLY_LAYOUT_PIN')
 manifest=json.loads(raw);p=root/'capture_job/checked_program.py';source=p.read_bytes()
 if hashlib.sha256(source).hexdigest()!=manifest['helpers'].get('capture_job/checked_program.py'):raise ValueError('ASSEMBLY_GUARD_PIN')
 m=types.ModuleType('assembly_checked_program');m.__file__=str(p);exec(compile(source,str(p),'exec'),m.__dict__);m.layout(manifest);before=m.sources(root,manifest)
 for relative,blob in before.items():ast.parse(blob,filename=relative)
 ctor=ast.parse((root/'capture_job/bootstrap/constructor.py').read_bytes());templates=next(ast.literal_eval(n.value) for n in ctor.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='TEMPLATE_PINS' for t in n.targets))
 for name,pin in templates.items():m.read(root/'capture_job/bootstrap/transport_challenge'/name,pin)
 family_pins=json.loads((pathlib.Path(a.layout).parent/'FAMILY_SEALS.public.json').read_bytes());family_files=0
 m.need(set(family_pins)=={'core','activate','epoch_readback','install_release','k4_e0','k9_phase_read','k9_phase_step'},'ASSEMBLY_FAMILY_SET')
 for name,pin_value in family_pins.items():
  family=root/'families'/name;seal=family/('CORE_SHA256SUMS' if name=='core' else 'SHA256SUMS');seal_raw=m.read(seal,pin_value)
  for row in seal_raw.decode().splitlines():
   expected,relative=row.split('  ',1);q=pathlib.PurePosixPath(relative);m.need(not q.is_absolute() and '..' not in q.parts,'ASSEMBLY_FAMILY_PATH');path=family/relative
   if expected==hashlib.sha256(b'').hexdigest():
    m.need(not path.is_symlink() and path.is_file() and path.stat().st_size==0 and path.read_bytes()==b'' and not path.stat().st_mode&0o022,'ASSEMBLY_EMPTY_FILE')
   else:m.read(path,expected)
   family_files+=1
 m.need(before==m.sources(root,manifest),'ASSEMBLY_CHANGED')
 result=dict(schema='CAPTURE_STAGED_SOURCE_ASSEMBLY_PROOF_V1',status='EXACT_SOURCE_ASSEMBLY_ONLY',source_layout_sha256=a.layout_sha256,programs=len(before),AST_parsed=len(before),templates=len(templates),family_seals=len(family_pins),family_files=family_files,divergences=0,app_imports=0,host_calls=0,actual_prepare_sign_dispatch=0,operational_READY=False)
 with pathlib.Path(a.out).open('x') as f:f.write(json.dumps(result,sort_keys=True,indent=2)+'\n')
 print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
