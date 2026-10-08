"""F6 physical runtime and installation acceptance. No effects on import.

The acceptance digest is pinned in the independently reviewed service unit;
receiving an acceptance file or a runtime measurement does not elect a service.
Production requires Linux, a root-controlled acceptance and all exact physical
identities. A FIXTURE acceptance is never reported as physical acceptance.
"""
import os
import platform
import stat
import sys
from pathlib import Path
from common import canonical, context, digest, fields, need, sha, snapshot, strict


def identity(st):
    return {k:snapshot(st)[k] for k in ("device","inode","uid","gid","mode")}


def physical(path, *, maximum=16*1024*1024, executable=False):
    path = Path(path)
    need(path.is_absolute(), "RUNTIME_PATH_ABSOLUTE")
    for parent in (path, *path.parents):
        st = parent.lstat()
        need(not stat.S_ISLNK(st.st_mode), "RUNTIME_LINK")
        if parent != path:
            need(stat.S_ISDIR(st.st_mode), "RUNTIME_ANCESTOR_TYPE")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= maximum,
             "RUNTIME_FILE_TYPE_SIZE")
        if executable: need(stat.S_IMODE(before.st_mode) & 0o111, "RUNTIME_NOT_EXECUTABLE")
        parts=[]; remaining=maximum+1
        while remaining:
            chunk=os.read(fd,min(remaining,65536))
            if not chunk: break
            parts.append(chunk); remaining-=len(chunk)
        raw=b"".join(parts)
        need(0 < len(raw) <= maximum and snapshot(before)==snapshot(os.fstat(fd))
             and snapshot(before)==snapshot(path.lstat()), "RUNTIME_FILE_CHANGED")
        return raw, identity(before)
    finally: os.close(fd)


def directory_chain(path, mode):
    path=Path(path); need(path.is_absolute(), "RUNTIME_ROOT_ABSOLUTE")
    rows=[]
    for parent in reversed((path,*path.parents)):
        st=parent.lstat()
        need(stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode), "RUNTIME_DIRECTORY_LINK")
        if mode=="REAL":
            need(st.st_uid in (0,os.geteuid()) and stat.S_IMODE(st.st_mode)&0o022==0,
                 "RUNTIME_WRITABLE_ANCESTOR")
        rows.append({"path":str(parent),"identity":identity(st)})
    return rows


def measure(spec):
    """Read only. Caller must publish exact bytes and obtain their own review."""
    fields(spec,("mode","context","roots","files","mutable_files","executables","socket"),"RUNTIME_SPEC_FIELDS")
    context(spec["context"]); need(spec["mode"] in ("REAL","FIXTURE"),"RUNTIME_MODE")
    if spec["mode"]=="REAL": need(platform.system()=="Linux", "RUNTIME_NOT_LINUX")
    roots={}
    for role,path in spec["roots"].items():
        chain=directory_chain(path,spec["mode"])
        need(chain[-1]["identity"]["uid"]==os.geteuid() and chain[-1]["identity"]["mode"] in (0o700,0o500),
             "RUNTIME_ROOT_PERMISSION")
        roots[role]=chain
    files={}
    for role,item in spec["files"].items():
        fields(item,("path","sha256","mode"),"RUNTIME_FILE_SPEC")
        raw, ident=physical(item["path"])
        need(digest(raw)==sha(item["sha256"]) and ident["mode"]==item["mode"]
             and ident["uid"] in (0,os.geteuid()), "RUNTIME_FILE_PIN")
        files[role]={"sha256":digest(raw),"identity":ident}
    mutable={}
    for role,item in spec["mutable_files"].items():
        fields(item,("path","identity"),"RUNTIME_MUTABLE_SPEC")
        _,ident=physical(item["path"])
        need(ident==item["identity"] and ident["uid"]==os.geteuid() and ident["mode"]==0o600,
             "RUNTIME_MUTABLE_IDENTITY")
        mutable[role]=ident
    executables={}
    for role,item in spec["executables"].items():
        fields(item,("path","sha256"),"RUNTIME_EXEC_SPEC")
        raw,ident=physical(item["path"],maximum=128*1024*1024,executable=True)
        need(digest(raw)==sha(item["sha256"]) and ident["mode"]&0o022==0 and ident["uid"] in (0,os.geteuid()),
             "RUNTIME_EXEC_PIN")
        executables[role]={"path":item["path"],"sha256":digest(raw),"identity":ident}
    need(executables["python"]["path"]==sys.executable,"RUNTIME_PYTHON_PHYSICAL_PATH")
    sock=spec["socket"]; socket_identity=None
    if sock is not None:
        need(type(sock) is str and Path(sock).is_absolute(),"RUNTIME_SOCKET_PATH")
        directory_chain(str(Path(sock).parent),spec["mode"])
        st=Path(sock).lstat()
        need(stat.S_ISSOCK(st.st_mode) and not stat.S_ISLNK(st.st_mode),"RUNTIME_SOCKET_TYPE")
        socket_identity=identity(st)
    boot=(Path('/proc/sys/kernel/random/boot_id').read_text().strip() if spec["mode"]=="REAL" else "FIXTURE_NO_PHYSICAL_BOOT")
    return {"schema":"SERVER_RUNTIME_MEASUREMENT_V2","mode":spec["mode"],"context":spec["context"],
            "euid":os.geteuid(),"egid":os.getegid(),"boot":boot,"python_version":platform.python_version(),
            "roots":roots,"files":files,"mutable_files":mutable,"executables":executables,"socket":socket_identity,
            "physical_acceptance":False}


class RuntimeGuard:
    def __init__(self, acceptance_path, acceptance_pin, *, fixture=False):
        raw,ident=physical(acceptance_path)
        need(digest(raw)==sha(acceptance_pin),"RUNTIME_ACCEPTANCE_PIN")
        self.acceptance=str(acceptance_path); self.pin=acceptance_pin; self.acceptance_identity=ident
        self.value=strict(raw); v=self.value
        need(v["schema"]=="SERVER_RUNTIME_ACCEPTANCE_V2" and v["accepted"] is True,
             "RUNTIME_ACCEPTANCE_SCHEMA")
        self.mode=v["spec"]["mode"]
        need((fixture and self.mode=="FIXTURE") or (not fixture and self.mode=="REAL"),"RUNTIME_FIXTURE_NOT_REAL")
        if self.mode=="REAL": need(ident["uid"]==0 and ident["mode"]==0o444,"RUNTIME_ACCEPTANCE_NOT_ROOT_CONTROLLED")
        else: need(ident["uid"]==os.geteuid() and ident["mode"] in (0o400,0o444),"FIXTURE_ACCEPTANCE_PERMISSION")
        self.context=context(v["spec"]["context"])
        need(v["measurement_sha256"]==digest(canonical(v["measurement"])) and v["measurement"]["context"]==self.context,
             "RUNTIME_MEASUREMENT_BINDING")
        sha(v["review_sha256"]); sha(v["installation_authority_sha256"])
        need(type(v['source_pins']) is dict and v['source_pins'], 'RUNTIME_SOURCE_PIN_SET')
        for name,pin in v['source_pins'].items():
            need(name in v['spec']['files'] and v['spec']['files'][name]['sha256']==sha(pin), 'RUNTIME_SOURCE_NOT_MEASURED')
        need(v['registry_sha256']==v['spec']['files']['registry']['sha256'], 'RUNTIME_REGISTRY_NOT_MEASURED')
        need(type(v["allowed_operations"]) is list and v["allowed_operations"] and len(set(v["allowed_operations"]))==len(v["allowed_operations"]),
             "RUNTIME_ALLOWED_OPERATIONS")
        self.recheck()

    def recheck(self):
        raw,ident=physical(self.acceptance)
        need(digest(raw)==self.pin and ident==self.acceptance_identity,"RUNTIME_ACCEPTANCE_CHANGED")
        now=measure(self.value["spec"])
        need(now==self.value["measurement"],"RUNTIME_PHYSICAL_CHANGED")
        return self.pin

    def allow(self,operation):
        need(operation in self.value["allowed_operations"],"RUNTIME_OPERATION_NOT_ELECTED")
        self.recheck()
