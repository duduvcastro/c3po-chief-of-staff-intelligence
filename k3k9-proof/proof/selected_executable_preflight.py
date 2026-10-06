"""NOT_RUN candidate: exact hosted-runner executable mode preflight, no proof execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

PACKAGE = Path(__file__).resolve().parents[1]
EXACT_312_SHA256 = 'bef88f140b625959f8af25c7b75cce2cd5d4b29cc2f2b079befd7f68eda4dba0'
PRODUCTION = ('/etc/c3po-bar','/var/lib/c3po-bar','/etc/c3po-reader','/var/lib/c3po-reader',
              '/opt/chief-of-staff-digital','/mnt/day-d-data','/run/c3po-security',
              '/var/lib/c3po','/var/lib/c3po-capacity')
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC

def need(condition, code):
    if not condition:
        raise ValueError(code)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def signature(info):
    return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode,info.st_nlink,
            info.st_size,info.st_mtime_ns,info.st_ctime_ns)

def directory_signature(info):
    return info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode

def metadata(info, digest):
    return {'file_type_bits':stat.S_IFMT(info.st_mode),'mode_octal':format(stat.S_IMODE(info.st_mode),'04o'),
            'uid':info.st_uid,'gid':info.st_gid,'nlink':info.st_nlink,'device':info.st_dev,'inode':info.st_ino,
            'size':info.st_size,'mtime_ns':info.st_mtime_ns,'ctime_ns':info.st_ctime_ns,'buffer_sha256':digest}

def fd_bytes(fd):
    before = os.fstat(fd)
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,'NOT_SINGLE_REGULAR')
    os.lseek(fd,0,os.SEEK_SET)
    pieces = []
    while True:
        block = os.read(fd,1048576)
        if not block:
            break
        pieces.append(block)
    after = os.fstat(fd)
    data = b''.join(pieces)
    need(signature(before) == signature(after) and len(data) == before.st_size,'BUFFER_CHANGED_DURING_READ')
    return data,before

def guard():
    need(sys.platform == 'linux' and os.getuid() == os.geteuid() == 1001,'OWNED_NONROOT_LINUX_REQUIRED')
    need(sys.executable == '/usr/bin/python3','TRUSTED_SYSTEM_ORCHESTRATION_REQUIRED')
    need(all(os.environ.get(k) == v for k,v in (
        ('GITHUB_ACTIONS','true'),('RUNNER_ENVIRONMENT','github-hosted'),('HOSTOPS_THROWAWAY_RUNNER','yes'))),
        'THROWAWAY_GITHUB_REQUIRED')
    need(not any(os.path.lexists(p) for p in PRODUCTION),'PRODUCTION_PATH_PRESENT')

def proof_pins():
    config = PACKAGE/'proof/INPUTS.json'
    fd = os.open(config,READ_FLAGS)
    try:
        data,unused = fd_bytes(fd)
    finally:
        os.close(fd)
    pins = json.loads(data)
    hashes = {}
    for name,pin in pins['proof_files'].items():
        parts = name.split('/')
        need(not name.startswith('/') and all(p not in ('','..','.') for p in parts),'PROOF_PATH_INVALID')
        fd = os.open(PACKAGE/name,READ_FLAGS)
        try:
            raw,unused = fd_bytes(fd)
        finally:
            os.close(fd)
        need(sha(raw) == pin,'PROOF_FILE_PIN')
        hashes[name] = pin
    return sha(data),hashes

def held_parent(path):
    """Keep every no-follow ancestor descriptor until the selected leaf is checked again."""
    parts = Path(path).parts
    need(parts[0] == '/','ABSOLUTE_PATH_REQUIRED')
    held = []
    root = os.open('/',DIRECTORY_FLAGS)
    held.append((root,None,None,directory_signature(os.fstat(root))))
    try:
        current = root
        for name in parts[1:-1]:
            named = os.stat(name,dir_fd=current,follow_symlinks=False)
            need(stat.S_ISDIR(named.st_mode),'ANCESTOR_NOT_DIRECTORY')
            child = os.open(name,DIRECTORY_FLAGS,dir_fd=current)
            info = os.fstat(child)
            held.append((child,current,name,directory_signature(info)))
            need(directory_signature(named) == directory_signature(info),'ANCESTOR_CHANGED')
            current = child
        return held,current,parts[-1]
    except BaseException:
        for fd,parent,name,stamp in reversed(held):
            os.close(fd)
        raise

def verify_held(held):
    for fd,parent,name,stamp in held:
        need(directory_signature(os.fstat(fd)) == stamp,'HELD_ANCESTOR_CHANGED')
        if parent is not None:
            need(directory_signature(os.stat(name,dir_fd=parent,follow_symlinks=False)) == stamp,'NAMED_ANCESTOR_CHANGED')

def output_parent(path,label):
    workspace = Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True)
    need(str(workspace) == os.environ['GITHUB_WORKSPACE'],'WORKSPACE_NOT_CANONICAL')
    permitted = workspace/('k3k9-proof-out/'+label+'/preflight.json')
    alternate = workspace/'k3k9-proof-original-out/preflight-system312/preflight.json'
    need(Path(path) in (permitted,alternate) and (Path(path) != alternate or label == 'py312'),'OUTPUT_DOMAIN')
    current = workspace
    for part in Path(path).relative_to(workspace).parts[:-1]:
        current = current/part
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            pass
        info = current.lstat()
        need(stat.S_ISDIR(info.st_mode) and info.st_uid == 1001 and stat.S_IMODE(info.st_mode) == 0o700,
             'OUTPUT_PARENT_NOT_PRIVATE')
    need(not os.path.lexists(path),'OUTPUT_EXISTS')
    return held_parent(str(path))

def report_write(held,parent,name,result):
    verify_held(held)
    fd = os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
    try:
        data = (json.dumps(result,sort_keys=True,indent=1)+'\n').encode()
        view = memoryview(data)
        while view:
            view = view[os.write(fd,view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    verify_held(held)

def artifact_snapshot(path):
    """Observe every upload object through held no-follow descriptors, without rewriting it."""
    held,parent,unused = held_parent(str(Path(path)/'.privacy-root-anchor'))
    records = {}
    def walk(fd,prefix):
        before = os.fstat(fd)
        need(stat.S_ISDIR(before.st_mode),'ARTIFACT_NOT_DIRECTORY')
        records[prefix or '.'] = metadata(before,None)
        with os.scandir(fd) as entries:
            names = sorted(item.name for item in entries)
        for name in names:
            relative = name if not prefix else prefix+'/'+name
            named = os.stat(name,dir_fd=fd,follow_symlinks=False)
            need(not stat.S_ISLNK(named.st_mode),'LINKED_ARTIFACT_UPLOAD_REFUSED')
            if stat.S_ISDIR(named.st_mode):
                child = os.open(name,DIRECTORY_FLAGS,dir_fd=fd)
                try:
                    need(signature(os.fstat(child)) == signature(named),'ARTIFACT_DIRECTORY_CHANGED')
                    walk(child,relative)
                    need(signature(os.stat(name,dir_fd=fd,follow_symlinks=False)) == signature(os.fstat(child)),
                         'ARTIFACT_DIRECTORY_NAME_CHANGED')
                finally:
                    os.close(child)
            else:
                need(stat.S_ISREG(named.st_mode),'NONREGULAR_ARTIFACT_UPLOAD_REFUSED')
                leaf = os.open(name,READ_FLAGS,dir_fd=fd)
                try:
                    first = os.fstat(leaf)
                    need(signature(first) == signature(named),'ARTIFACT_FILE_NAME_CHANGED')
                    hasher = hashlib.sha256()
                    size = 0
                    while True:
                        block = os.read(leaf,1048576)
                        if not block:
                            break
                        hasher.update(block)
                        size += len(block)
                    last = os.fstat(leaf)
                    need(signature(first) == signature(last) and size == first.st_size,'ARTIFACT_FILE_CHANGED_DURING_READ')
                    need(signature(os.stat(name,dir_fd=fd,follow_symlinks=False)) == signature(last),
                         'ARTIFACT_FILE_NAME_CHANGED_AFTER_READ')
                    records[relative] = metadata(first,hasher.hexdigest())
                finally:
                    os.close(leaf)
        need(signature(os.fstat(fd)) == signature(before),'ARTIFACT_DIRECTORY_CHANGED_DURING_SCAN')
    try:
        verify_held(held)
        walk(parent,'')
        verify_held(held)
        return records
    finally:
        for fd,parent,name,stamp in reversed(held):
            os.close(fd)

def privacy_main(path,label):
    """Scan the entire literal upload root around the pinned original privacy gate through system Python."""
    guard()
    inputs_before,pins_before = proof_pins()
    workspace = Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True)
    need(str(workspace) == os.environ['GITHUB_WORKSPACE'],'WORKSPACE_NOT_CANONICAL')
    need(Path(path) == workspace/'k3k9-proof-out'
         or (label == 'py312' and Path(path) == workspace/'k3k9-proof-original-out'),
         'PRIVACY_OUTPUT_DOMAIN')
    record = {'schema':'CURRENT_K3K9_UPLOAD_BOUNDARY_OBSERVATION_V1','status':'HOLD',
              'original_scanner_called':False,'original_scanner_error':None,
              'before':None,'after':None,'after_error':None,'proof_success_not_inferred':True}
    try:
        record['before'] = artifact_snapshot(path)
    except BaseException as error:
        record['before_error'] = type(error).__name__+': '+str(error)
        print(json.dumps(record,sort_keys=True))
        raise
    source = PACKAGE/'proof/artifact_guard.py'
    fd = os.open(source,READ_FLAGS)
    try:
        data,unused = fd_bytes(fd)
    finally:
        os.close(fd)
    need(sha(data) == pins_before['proof/artifact_guard.py'],'PRIVACY_SOURCE_PIN')
    saved = sys.argv
    original_error = None
    after_error = None
    try:
        sys.argv = [str(source),str(path)]
        record['original_scanner_called'] = True
        exec(compile(data,str(source),'exec',dont_inherit=True),{'__name__':'__main__','__file__':str(source)})
    except BaseException as error:
        original_error = error
        record['original_scanner_error'] = type(error).__name__+': '+str(error)
    finally:
        sys.argv = saved
    try:
        record['after'] = artifact_snapshot(path)
        inputs_after,pins_after = proof_pins()
        record['proof_before_after_equal'] = inputs_after == inputs_before and pins_after == pins_before
        record['upload_before_after_equal'] = record['after'] == record['before']
        need(record['proof_before_after_equal'],'PRIVACY_PROOF_INPUTS_CHANGED')
        need(record['upload_before_after_equal'],'UPLOAD_DOMAIN_CHANGED_DURING_PRIVACY_GATE')
    except BaseException as error:
        after_error = error
        record['after_error'] = type(error).__name__+': '+str(error)
    if original_error is None and after_error is None:
        record['status'] = 'ARTIFACT_BOUNDARY_AND_ORIGINAL_PRIVACY_CHECKED'
    print(json.dumps(record,sort_keys=True))
    if original_error is not None:
        raise original_error
    if after_error is not None:
        raise after_error
    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--python')
    ap.add_argument('--label',choices=('py39','py312'),required=True)
    ap.add_argument('--out')
    ap.add_argument('--privacy-root')
    a = ap.parse_args()
    if a.privacy_root is not None:
        need(a.python is None and a.out is None,'PRIVACY_ARGUMENTS')
        return privacy_main(a.privacy_root,a.label)
    need(a.python is not None and a.out is not None,'PREFLIGHT_ARGUMENTS')
    result = {'schema':'CURRENT_K3K9_EXACT_EXECUTABLE_PREFLIGHT_V1','status':'HOLD','label':a.label,
              'proof_executed':False,'operational_dispatch':False,'selected_process_started':False,
              'mutation_issued':False,'mutation_completed':False,'before':None,'after':None,'failure':None,
              'orchestration_python':{'executable':sys.executable,'version':list(sys.version_info[:3]),
                                      'role':'SYSTEM_PREFLIGHT_ONLY_NOT_SELECTED_PROOF_LAYER'}}
    output = None
    held = []
    leaf = None
    try:
        guard()
        output = output_parent(a.out,a.label)
        inputs_before,proof_before = proof_pins()
        result['proof_input_sha256'] = inputs_before
        executable = Path(a.python).resolve(strict=True)
        match = re.fullmatch(r'/opt/hostedtoolcache/Python/(3\.(9|12)\.[0-9]+)/x64/bin/python(3\.(9|12))',str(executable))
        need(match is not None and match.group(2) == match.group(4),'SELECTED_CANONICAL_PATH')
        need((a.label == 'py39' and match.group(2) == '9') or (a.label == 'py312' and match.group(2) == '12'),
             'SELECTED_LAYER_MISMATCH')
        result['selected_realpath'] = str(executable)
        held,parent,name = held_parent(str(executable))
        verify_held(held)
        leaf = os.open(name,READ_FLAGS,dir_fd=parent)
        info = os.fstat(leaf)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == 1001,'SELECTED_FILE_IDENTITY')
        need(signature(os.stat(name,dir_fd=parent,follow_symlinks=False)) == signature(info),'SELECTED_NAME_IDENTITY')
        data,before = fd_bytes(leaf)
        digest = sha(data)
        result['before'] = metadata(before,digest)
        verify_held(held)
        need(signature(os.fstat(leaf)) == signature(before),'SELECTED_CHANGED_BEFORE_DECISION')
        if a.label == 'py39':
            need(before.st_mode & 0o022 == 0,'UNSAFE_OTHER_SELECTED_EXECUTABLE')
            result['action'] = 'NO_MUTATION_ALREADY_SAFE_PY39'
        else:
            need(match.group(1) == '3.12.14' and stat.S_IMODE(before.st_mode) == 0o777
                 and before.st_gid == 1000 and before.st_size == 17752 and digest == EXACT_312_SHA256,
                 'NOT_THE_EXACT_OBSERVED_UNSAFE_PY312')
            need(signature(os.stat(name,dir_fd=parent,follow_symlinks=False)) == signature(before),'SELECTED_CHANGED_BEFORE_FCHMOD')
            result['action'] = 'REMOVE_ONLY_GROUP_OTHER_WRITE_BITS_FROM_EXACT_OBSERVED_PY312'
            result['mutation_issued'] = True
            os.fchmod(leaf,stat.S_IMODE(before.st_mode) & ~0o022)
            result['mutation_completed'] = True
        data_after,after = fd_bytes(leaf)
        result['after'] = metadata(after,sha(data_after))
        result['bytes_equal'] = data_after == data
        need(data_after == data,'SELECTED_BUFFER_CHANGED')
        need((before.st_dev,before.st_ino,before.st_uid,before.st_gid,before.st_nlink,before.st_size,before.st_mtime_ns)
             == (after.st_dev,after.st_ino,after.st_uid,after.st_gid,after.st_nlink,after.st_size,after.st_mtime_ns),
             'SELECTED_IDENTITY_CHANGED')
        if a.label == 'py39':
            need(signature(before) == signature(after),'SAFE_PY39_METADATA_CHANGED')
        else:
            need(stat.S_IMODE(after.st_mode) == 0o755 and after.st_ctime_ns >= before.st_ctime_ns,
                 'EXACT_PY312_MODE_CHANGE_NOT_OBSERVED')
        verify_held(held)
        need(signature(os.stat(name,dir_fd=parent,follow_symlinks=False)) == signature(after),'SELECTED_NAME_CHANGED_AFTER')
        need(after.st_mode & 0o022 == 0,'UNSAFE_SELECTED_EXECUTABLE_AFTER')
        inputs_after,proof_after = proof_pins()
        result['proof_before_after_equal'] = inputs_after == inputs_before and proof_after == proof_before
        need(result['proof_before_after_equal'],'PROOF_INPUTS_CHANGED')
        result['status'] = 'PREFLIGHT_SAFE_SELECTED_EXECUTABLE'
    except BaseException as error:
        result['failure'] = type(error).__name__+': '+str(error)
        if leaf is not None:
            try:
                raw,info = fd_bytes(leaf)
                result['after_on_refusal'] = metadata(info,sha(raw))
            except BaseException as retained:
                result['after_on_refusal_error'] = type(retained).__name__+': '+str(retained)
    finally:
        if leaf is not None:
            os.close(leaf)
        for fd,parent,name,stamp in reversed(held):
            os.close(fd)
        if output is not None:
            try:
                report_write(*output,result)
            except BaseException as error:
                result['status'] = 'HOLD'
                result['report_write_failure'] = type(error).__name__+': '+str(error)
            finally:
                for fd,parent,name,stamp in reversed(output[0]):
                    os.close(fd)
        print(json.dumps(result,sort_keys=True))
    return 0 if result['status'] == 'PREFLIGHT_SAFE_SELECTED_EXECUTABLE' else 2

if __name__ == '__main__':
    raise SystemExit(main())
