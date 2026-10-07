"""Disposable Linux measurement/check proof. Never operation acceptance or host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import types

HELPER='796ec07043f628b96bfdab20e5103567a70cc62c15f3ee63ce74ea36f6a0e2d6'
def main():
    ap=argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('command',choices=('measure','check'))
    ap.add_argument('--root',required=True)
    ap.add_argument('--measurement',required=True)
    ap.add_argument('--measurement-sha256')
    a=ap.parse_args();root=Path(a.root).resolve();home=root/'binder'/'bind'
    helper=(home/'runtime_identity.py').read_bytes()
    if hashlib.sha256(helper).hexdigest()!=HELPER:raise ValueError('COMPONENT_GUARD_PIN')
    m=types.ModuleType('runtime_identity');m.__file__=str(home/'runtime_identity.py');sys.modules[m.__name__]=m
    exec(compile(helper,m.__file__,'exec'),m.__dict__)
    m.need(m.sha(m.read_regular(home/'bind_once.py'))==m.BINDER_SHA256,'COMPONENT_BINDER_PIN')
    m.need(m.sha(m.read_regular(home/'ACCEPTED_SEALS.json'))==m.ACCEPTED_SHA256,'COMPONENT_REGISTRY_PIN')
    expected=None
    if a.command=='check':
        raw=Path(a.measurement).read_bytes();m.need(m.sha(raw)==a.measurement_sha256,'COMPONENT_MEASUREMENT_PIN');expected=json.loads(raw)
    observed=m.observe(root,(home/'runtime_identity.py',),expected=expected)
    if expected is not None:
        result=m.compare(expected,observed);result.update(scope='DISPOSABLE_COMPONENT_ONLY_NOT_CURRENT_JOB_ACCEPTANCE',operational_READY=False)
    else:
        observed.update(runtime_guard_sha256=HELPER,measurement_is_not_acceptance=True)
        raw=(json.dumps(observed,sort_keys=True,indent=2)+'\n').encode()
        fd=os.open(a.measurement,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:f.write(raw)
        result=dict(status='MEASURED_NOT_ACCEPTED',measurement_sha256=m.sha(raw),binder_sha256=m.BINDER_SHA256,
                    guard_sha256=HELPER,python_version=observed['python_version'],calendar_version=observed['calendar_version'],
                    venv_files=len(observed['venv_files']),stdlib_files=len(observed['stdlib_files']),
                    distributions=len(observed['distributions']),loaded_modules=len(observed['module_origins']),
                    actual_host_calls=0,operational_READY=False)
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
