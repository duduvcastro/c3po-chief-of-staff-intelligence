"""Bounded native adapters. No shell, environment forwarding or generic command.

All subprocesses are fixed, pinned programs selected by the reviewed registry.
Any timeout, uncertain return or malformed result consumes the controller's
reserved invocation. Native adapters never retry or remove a container.
"""
import os
import re
import selectors
import subprocess
import time
from common import Hold, canonical, context, digest, fields, need, sha, strict
from runtime import physical


class BoundedProcess:
    def __init__(self, guard, *, launcher=subprocess.Popen, monotonic=time.monotonic):
        self.guard,self.launcher,self.monotonic=guard,launcher,monotonic

    def run(self, argv, *, stdin=b"", limit=1024*1024, seconds=20):
        need(type(argv) is list and argv and all(type(x) is str and '\x00' not in x for x in argv),"PROCESS_ARGV")
        need(type(stdin) is bytes and len(stdin)<=16*1024*1024 and 0<limit<=32*1024*1024 and 0<seconds<=120,"PROCESS_LIMIT")
        self.guard.recheck()
        executable=self.guard.value["spec"]["executables"]
        need(argv[0] in [v["path"] for v in executable.values()],"PROCESS_NOT_PINNED")
        env={"PATH":"/usr/bin:/bin","LANG":"C.UTF-8","LC_ALL":"C.UTF-8","PYTHONNOUSERSITE":"1","PYTHONDONTWRITEBYTECODE":"1"}
        # No inherited token, SSH variables, Docker context, PYTHONPATH or preload.
        process=self.launcher(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                              env=env,cwd='/',close_fds=True,start_new_session=True)
        selector=selectors.DefaultSelector(); data=[]; written=0; total=0
        start=self.monotonic()
        try:
            os.set_blocking(process.stdin.fileno(),False); os.set_blocking(process.stdout.fileno(),False)
            selector.register(process.stdout,selectors.EVENT_READ)
            if stdin: selector.register(process.stdin,selectors.EVENT_WRITE)
            else: process.stdin.close()
            while selector.get_map():
                remaining=seconds-(self.monotonic()-start); need(remaining>0,"PROCESS_TIMEOUT")
                for key,event in selector.select(min(remaining,.1)):
                    if key.fileobj is process.stdin:
                        n=os.write(process.stdin.fileno(),stdin[written:written+65536]);written+=n
                        if written==len(stdin): selector.unregister(process.stdin);process.stdin.close()
                    else:
                        part=os.read(process.stdout.fileno(),65536)
                        if not part: selector.unregister(process.stdout);process.stdout.close()
                        else:
                            total+=len(part);need(total<=limit,"PROCESS_OUTPUT_LIMIT");data.append(part)
            remaining=seconds-(self.monotonic()-start);need(remaining>0,"PROCESS_TIMEOUT")
            code=process.wait(timeout=remaining)
            self.guard.recheck()
            return {"returncode":code,"stdout":b''.join(data)}
        except BaseException:
            # Terminating the client does not undo or repeat a daemon effect.
            try: process.kill()
            except ProcessLookupError: pass
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: pass
            raise
        finally:
            selector.close()
            for stream in (process.stdin,process.stdout):
                if not stream.closed: stream.close()


class DockerEngine:
    def __init__(self,guard,runner):
        self.guard,self.runner=guard,runner
        self.path=guard.value['spec']['executables']['docker']['path']
        self.socket=guard.value['spec']['socket']
        need(self.socket is not None,'DOCKER_LOCAL_SOCKET_REQUIRED')

    def call(self, action, container, fmt=None, *, limit=65536):
        need(re.fullmatch('[0-9a-f]{64}',container or ''),'DOCKER_ID')
        argv=[self.path,'--host','unix://'+self.socket]
        if action=='inspect':
            from k12 import INSPECT_FORMAT
            need(fmt==INSPECT_FORMAT,'DOCKER_INSPECT_FORMAT');argv+=['inspect','--format',fmt,container]
        elif action=='logs': need(fmt is None,'DOCKER_LOGS_FORMAT');argv+=['logs',container]
        elif action=='stop': need(fmt is None,'DOCKER_STOP_FORMAT');argv+=['stop','--time','10',container]
        else: raise Hold('DOCKER_ACTION_NOT_REGISTERED')
        self.guard.recheck()
        return self.runner.run(argv,limit=limit,seconds=15)

    def launch(self,request,capacity_raw,recheck):
        from k12 import INSPECT_FORMAT,identified
        cap=strict(capacity_raw);ctx=context(request['context']);p=request['payload']
        need(request['operation']=='F4_K12_LAUNCH' and cap['schema']=='R2D2_CAPACITY_DAY_ONCE_REQUEST_V2'
             and cap['context']==ctx,'K12_LAUNCH_REQUEST')
        need(digest(capacity_raw)==sha(p['capacity_request_sha256']) and cap['window']==p['window']
             and cap['window_slot']==p['window_slot'] and cap['view_UTC']==p['view_UTC'],'K12_LAUNCH_CAPACITY')
        need(re.fullmatch('sha256:[0-9a-f]{64}',cap['image_id']) and re.fullmatch('[A-Za-z0-9_.-]{1,64}',cap['network']),
             'K12_IMAGE_NETWORK')
        need(type(cap['writer_argv']) is list and cap['writer_argv'] and all(type(x) is str and '\x00' not in x for x in cap['writer_argv']),
             'K12_WRITER_ARGV')
        # Registry must elect the exact producer ABI/argv/image/network/mounts.
        contract=self.guard.value['family_contracts']['K12_LAUNCH']
        need({k:cap[k] for k in ('image_id','writer_argv','network','mounts')}==contract,'K12_LAUNCH_NOT_ELECTED')
        name='c3po-k12-%s-w%s'%(ctx['session'],cap['window_slot']); reqpin=digest(canonical(request));cappin=digest(capacity_raw)
        argv=[self.path,'--host','unix://'+self.socket,'create','--pull','never','--init','--user','0:0',
              '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--restart','no','--name',name,
              '--network',cap['network'],'--label','c3po.k12.request_sha256='+reqpin,
              '--label','c3po.k12.capacity_request_sha256='+cappin]
        for mount in cap['mounts']:
            fields(mount,('source','destination','rw'),'K12_MOUNT_FIELDS')
            need(type(mount['rw']) is bool and all(type(mount[k]) is str and mount[k].startswith('/')
                 and not any(c in mount[k] for c in ',\x00\n') for k in ('source','destination')),'K12_MOUNT_VALUE')
            argv+=['--mount','type=bind,src='+mount['source']+',dst='+mount['destination']+('' if mount['rw'] else ',readonly')]
        argv+=[cap['image_id']]+cap['writer_argv']
        recheck();created=self.runner.run(argv,limit=1024,seconds=10)
        need(created['returncode']==0,'K12_CREATE_UNCERTAIN')
        container=created['stdout'].decode('ascii').strip();need(re.fullmatch('[0-9a-f]{64}',container),'K12_CREATE_ID')
        payload=dict(p,container_id=container,launch_request_sha256=reqpin,capacity_request_sha256=cappin)
        detail={k:p[k] for k in ('window','window_slot','view_UTC')}
        detail.update(container_id=container,image_id=cap['image_id'],capacity_request_sha256=cappin)
        before=self.call('inspect',container,INSPECT_FORMAT)
        need(before['returncode']==0,'K12_CREATE_INSPECT')
        row=identified(strict(before['stdout']),payload,cap,detail)
        need(row['state']=='created' and row['running'] is False,'K12_CREATE_STATE')
        recheck();self.guard.recheck()
        started=self.runner.run([self.path,'--host','unix://'+self.socket,'start',container],limit=1024,seconds=10)
        need(started['returncode']==0 and started['stdout'].decode('ascii').strip()==container,'K12_START_UNCERTAIN')
        after=self.call('inspect',container,INSPECT_FORMAT);need(after['returncode']==0,'K12_START_INSPECT')
        row=identified(strict(after['stdout']),payload,cap,detail)
        need(row['state'] in ('running','exited'),'K12_START_STATE')
        return detail


class ProtectedReader:
    def __init__(self,guard,runner,entry):
        fields(entry,('reader_id','source_path','source_sha256','source_files','configuration'),'READER_REGISTRY_FIELDS')
        self.guard,self.runner,self.entry=guard,runner,entry
        self.reader_id=entry['reader_id'];self.source_sha256=sha(entry['source_sha256'])

    def read_once(self,request,binding):
        self.guard.recheck()
        need(self.entry==self.guard.value['reader_registry'][self.reader_id],'READER_NOT_ELECTED')
        raw,_=physical(self.entry['source_path']);need(digest(raw)==self.source_sha256,'READER_SOURCE_CHANGED')
        for item in self.entry['source_files']:
            raw,_=physical(item['path']);need(digest(raw)==sha(item['sha256']),'READER_MODULE_CHANGED')
        payload=canonical({'schema':'H16_READER_INPUT_V2','request':request,'binding':binding,
                           'configuration':self.entry['configuration']})
        python=self.guard.value['spec']['executables']['python']['path']
        # -I ignores Python environment/user site; the reviewed reader itself has
        # no untrusted import path or generic command/SQL/provider interface.
        result=self.runner.run([python,'-I','-S','-B',self.entry['source_path'],'--bound-stdin'],stdin=payload,seconds=20)
        need(result['returncode']==0,'H16_READER_REFUSED_OR_UNCERTAIN')
        return strict(result['stdout'])
