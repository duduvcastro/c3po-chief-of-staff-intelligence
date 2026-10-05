"""Throwaway GitHub Linux runner only. Synthetic tokens; no production host dispatch.
Exercises the candidate's actual provider_content/Native and Docker-created config.v2.json.
Prints only constant outcomes, counts and booleans. No inspect of the worker, no raw config output.
"""
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
STAGE="INITIAL"
SAFE_CODES=frozenset(("PROOF_DOCKER_FAILED","PROOF_FIXTURE_IMAGE_ABSENT","PROOF_IMAGE_UNBOUND","PROOF_CONTAINER_ID","PROOF_NOT_OWNED_CONFIG","PROOF_CONFIG_SHORT_WRITE","PROOF_CANARY_LEAK"))
def main():
    global STAGE
    if not (sys.platform=='linux' and os.getuid()==0 and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
            and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes' and os.environ.get('GITHUB_ACTIONS')=='true'):
        print(json.dumps({'verdict':'REFUSED_NOT_THROWAWAY_CI'}));return 1
    STAGE='LOAD_CANDIDATE'
    spec=importlib.util.spec_from_file_location('proof_candidate',ROOT/'build/k3k9_secrets.py')
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    # Protect this exact process before constructing or acquiring any value.
    STAGE='PROCESS_PROTECTION'
    m.dumps_disabled();lib=ctypes.CDLL(None);check=lambda:lib.prctl(3,0,0,0,0)==0
    def docker(*args):
        out=subprocess.run(['/usr/bin/docker',*args],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                           env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},timeout=20,check=False)
        if out.returncode:raise RuntimeError('PROOF_DOCKER_FAILED')
        return out.stdout
    STAGE='FIXTURE_PREFLIGHT'
    if docker('ps','-a','--filter','name=^/'+m.WORKER_CONTAINER_NAME+'$','--format','{{.ID}}').strip():
        print(json.dumps({'verdict':'REFUSED_EXISTING_WORKER'}));return 1
    if docker('info','--format','{{.DockerRootDir}}').strip()!=b'/var/lib/docker':
        print(json.dumps({'verdict':'REFUSED_DIFFERENT_DATA_ROOT'}));return 1
    STAGE='FIXTURE_IMAGE'
    image=None
    for tag in ('python:3.12-slim','public.ecr.aws/docker/library/python:3.12-slim'):
        try:image=docker('image','inspect','--format','{{.Id}}',tag).decode().strip();break
        except RuntimeError:pass
    if image is None:raise RuntimeError('PROOF_FIXTURE_IMAGE_ABSENT')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',image):raise RuntimeError('PROOF_IMAGE_UNBOUND')
    values={plain:'SyNtHeTiC'+plain.title().replace('_','')+'ToKeN123456789' for _,plain in m.PROVIDER_TOKEN_NAMES}
    cases=[('accepted',values,None),('absent',{k:v for k,v in values.items() if k!='FINNHUB_API_TOKEN'},'PROVIDER_TOKEN_ABSENT'),
           ('invalid',dict(values,FMP_API_TOKEN='short'),'PROVIDER_TOKEN_GRAMMAR'),('duplicate',values,'SECRET_ENVIRONMENT_REPEATED'),
           ('above_limit',dict(values,FMP_API_TOKEN='x'*4097),'PROVIDER_TOKEN_GRAMMAR')]
    results=[];owned=None;buffers=[];chain_metadata=[]
    try:
        for label,env,expected in cases:
            STAGE='CASE_'+label.upper()
            argv=['create','--name',m.WORKER_CONTAINER_NAME,'--network','none','--read-only','--cap-drop','ALL',
                  '--security-opt','no-new-privileges','--entrypoint','/usr/local/bin/python']
            for name,value in sorted(env.items()):argv+=['--env',name+'='+value]
            STAGE='CREATE_'+label.upper()
            owned=docker(*argv,image,'-c','import time; time.sleep(120)').decode().strip()
            if not re.fullmatch('[0-9a-f]{64}',owned):raise RuntimeError('PROOF_CONTAINER_ID')
            STAGE='START_'+label.upper()
            docker('start',owned)
            if label=='accepted':
                STAGE='ENGINE_METADATA'
                pieces=Path('/var/lib/docker/containers/'+owned).parts
                for depth in range(1,len(pieces)+1):
                    info=os.lstat(str(Path(*pieces[:depth])))
                    chain_metadata.append({'depth':depth-1,'uid':info.st_uid,'gid':info.st_gid,'mode_octal':format(stat.S_IMODE(info.st_mode),'04o'),'directory':stat.S_ISDIR(info.st_mode)})
            if label=='duplicate':
                # Only the config of the synthetic ID created by this proof is modified. No candidate write.
                # Docker CLI normalises duplicate --env names, so the on-disk parser boundary needs this fixture.
                path='/var/lib/docker/containers/'+owned+'/config.v2.json'
                fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
                try:
                    raw=os.read(fd,1048576);body=json.loads(raw)
                    if body.get('ID')!=owned:raise RuntimeError('PROOF_NOT_OWNED_CONFIG')
                    body['Config']['Env'].append('EODHD_API_TOKEN='+values['EODHD_API_TOKEN'])
                    raw=json.dumps(body).encode();os.lseek(fd,0,os.SEEK_SET);os.ftruncate(fd,0)
                    if os.write(fd,raw)!=len(raw):raise RuntimeError('PROOF_CONFIG_SHORT_WRITE')
                    os.fsync(fd)
                finally:os.close(fd)
            STAGE='ACQUIRE_'+label.upper()
            facts=m.worker_facts();code=None;content=None;buffers=[]
            try:content=m.provider_content(m.Commands(m.Native(),lambda:60.0),owned,facts,buffers)
            except m.Refused as error:code=str(error) if str(error) in m.RECEIPT_CODES else 'UNLISTED_CODE'
            protected=check()
            if expected is None:
                good=content==b''.join((prefixed+'='+values[plain]+'\n').encode() for prefixed,plain in m.PROVIDER_TOKEN_NAMES)
            else:good=code==expected
            STAGE='ZERO_'+label.upper()
            for buffer in buffers:m.zero(buffer)
            results.append({'case':label,'actual_code':code if code else 'NO_REFUSAL','expected_code_met':good,'protected_during_acquisition':protected,
                            'buffers_zeroed':all(not any(buffer) for buffer in buffers),'no_worker_inspect':set(m.COMMANDS)=={'container_list'}})
            STAGE='REMOVE_'+label.upper()
            docker('rm','-f',owned);owned=None
        # Crash this same protected process's fork, with no exec and with a synthetic value resident.
        STAGE='PROTECTED_CRASH'
        pid=os.fork()
        if pid==0:
            if not check():os._exit(2)
            os.kill(os.getpid(),signal.SIGABRT);os._exit(3)
        _,status=os.waitpid(pid,0)
        # Linux wait status's core-dump bit remains unset for this exact non-dumpable process.
        results.append({'case':'protected_crash','signal_abort':os.WIFSIGNALED(status) and os.WTERMSIG(status)==signal.SIGABRT,
                        'core_dump_bit_unset':not os.WCOREDUMP(status),'protected_parent':check()})
        # A different uid cannot open the protected process's memory through procfs.
        STAGE='PROCFS_ACCESS'
        own=os.getpid();pid=os.fork()
        if pid==0:
            os.setgroups([]);os.setgid(65534);os.setuid(65534)
            try:fd=os.open('/proc/%d/mem'%own,os.O_RDONLY);os.close(fd)
            except PermissionError:os._exit(0)
            os._exit(4)
        _,status=os.waitpid(pid,0);results.append({'case':'unprivileged_memory_access','refused':os.WIFEXITED(status) and os.WEXITSTATUS(status)==0})
        STAGE='SERIALIZE_RESULT'
        raw=json.dumps({'schema':'K3K9_REV3_SYNTHETIC_CONFIG_PROOF_V1','results':results,'engine_chain_metadata':chain_metadata,'all_expectations_met':all(
            all(v is True for k,v in row.items() if k not in ('case','actual_code')) for row in results)},sort_keys=True)
        if any(value in raw for value in values.values()):raise RuntimeError('PROOF_CANARY_LEAK')
        for row in results:
            if row.get('expected_code_met') is False:
                print('K3K9_PROOF_CASE '+row['case']+' '+row['actual_code'],file=sys.stderr)
        print(raw);return 0 if json.loads(raw)['all_expectations_met'] else 1
    finally:
        for buffer in buffers:m.zero(buffer)
        if owned is not None:docker('rm','-f',owned)
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        code=str(error) if isinstance(error,RuntimeError) and str(error) in SAFE_CODES else 'PROOF_UNEXPECTED_EXCEPTION'
        kind=type(error).__name__
        kind=kind if kind in ('AttributeError','TypeError','NameError','ValueError','TimeoutExpired','FileNotFoundError','PermissionError','OSError','RuntimeError') else 'OTHER_EXCEPTION'
        print('K3K9_PROOF_FAILED '+STAGE+' '+code+' '+kind,file=sys.stderr)
        print(json.dumps({'verdict':'PROOF_FAILED','stage':STAGE,'code':code,'exception_kind':kind}));raise SystemExit(1)
