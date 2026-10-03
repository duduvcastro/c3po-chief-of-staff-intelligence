"""One attempt over an explicitly authorized, byte-pinned transport command.
No target, credentials, SSH policy or authority is inferred. Never retries.
"""
import hashlib
import json
import os
import selectors
import signal
import subprocess
import time
from typing import BinaryIO, cast

MAX_OUTPUT=4*1024*1024

class Refused(ValueError):pass

def need(value,code):
    if not value:raise Refused(code)

def digest(raw):return hashlib.sha256(raw).hexdigest()

def command_pin(command):
    return digest(json.dumps(command,separators=(',',':')).encode())

def once(payload,*,payload_sha256,command: list[str],command_sha256,authorize,seconds=250,monotonic=time.monotonic):
    need(type(payload) is bytes and 0<len(payload)<=2*1024*1024 and digest(payload)==payload_sha256,'FINAL_PAYLOAD_PIN')
    need(type(command) is list and command and all(type(x) is str and x and '\x00' not in x for x in command)
         and command[0].startswith('/') and command_pin(command)==command_sha256,'TRANSPORT_COMMAND_PIN')
    need(type(seconds) is int and 1<=seconds<=270,'WATCHDOG_LIMIT')
    # authorize must check independently authenticated GO, final bytes, target and UTC window.
    # No launcher exists until those real values and this callback are reviewed/bound.
    deadline=monotonic()+seconds
    need(authorize(payload_sha256,command_sha256) is True,'TRANSPORT_AUTHORITY_UNBOUND')
    need(monotonic()<deadline,'WATCHDOG_EXPIRED_BEFORE_SPAWN')
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},start_new_session=True,bufsize=0)
    selector=selectors.DefaultSelector();out=bytearray();err=bytearray();sent=0;failure=None
    try:
        for stream,event in ((process.stdin,selectors.EVENT_WRITE),(process.stdout,selectors.EVENT_READ),(process.stderr,selectors.EVENT_READ)):
            assert stream is not None
            os.set_blocking(stream.fileno(),False);selector.register(stream,event)
        while selector.get_map():
            remaining=deadline-monotonic()
            if remaining<=0:raise Refused('WATCHDOG_EXPIRED')
            for key,event in selector.select(min(remaining,.1)):
                stream=cast(BinaryIO,key.fileobj)
                if stream is process.stdin:
                    try:sent+=os.write(stream.fileno(),payload[sent:sent+65536])
                    except BrokenPipeError:sent=len(payload)
                    if sent==len(payload):selector.unregister(stream);stream.close()
                else:
                    chunk=os.read(stream.fileno(),65536)
                    if not chunk:selector.unregister(stream);stream.close();continue
                    target=out if stream is process.stdout else err
                    need(len(out)+len(err)+len(chunk)<=MAX_OUTPUT,'TRANSPORT_OUTPUT_LIMIT')
                    target.extend(chunk)
        process.wait(timeout=max(.001,deadline-monotonic()))
    except Exception as error:
        failure=str(error) if isinstance(error,Refused) else 'TRANSPORT_IO_UNCERTAIN'
    finally:
        if failure is not None or process.poll() is None:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:pass
        selector.close()
        for stream in (process.stdin,process.stdout,process.stderr):
            if stream is not None and not stream.closed:stream.close()
    result={'schema':'POSTDEPLOY01_TRANSPORT_RESULT_V1','attempts':1,'retry_allowed':False,
            'payload_sha256':payload_sha256,'command_sha256':command_sha256,
            'stdout_sha256':digest(out),'stderr_sha256':digest(err),'returncode':process.returncode,
            'status':'UNCERTAIN','code':failure or 'RESULT_INVALID'}
    if failure is None:
        try:
            def pairs(items):
                value={}
                for key,item in items:
                    need(key not in value,'DUPLICATE_RESULT');value[key]=item
                return value
            value=json.loads(out,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(Refused('RESULT_CONSTANT')))
            status=value.get('status')
            expected={0:'METADATA_ONLY_REQUIRES_REVIEW',2:'PARTIAL_METADATA_REQUIRES_REVIEW',1:'REFUSED'}
            need(not err and expected.get(process.returncode)==status,'RESULT_EXIT_MISMATCH')
            if process.returncode in (0,2):
                claimed=value.pop('metadata_sha256')
                raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
                need(digest(raw)==claimed,'RESULT_HASH')
            result.update(status='KNOWN_PARTIAL' if process.returncode==2 else 'KNOWN_COMPLETE' if process.returncode==0 else 'KNOWN_REFUSAL',code=None)
        except Exception:pass
    # Bytes are returned privately to caller, never printed/logged by this module.
    return result,bytes(out),bytes(err)
