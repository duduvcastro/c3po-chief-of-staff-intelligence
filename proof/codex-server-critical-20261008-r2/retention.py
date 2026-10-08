"""Bounded private evidence capsule, actual pinned age transport, no plaintext POST.

Encryption is confidentiality only. The request, actual owner original and
runtime acceptance are retained as their original bytes, never re-signed or
recanonicalized. A failed/uncertain cipher aborts completion; no retry.
"""
import io
import re
import tarfile
from common import canonical,digest,fields,need,sha,strict

MAXIMUM=768*1024


def pack(members):
    need(type(members) is dict and members and len(members)<=32,'CAPSULE_MEMBER_SET')
    need(all(type(name) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,120}',name)
         and name!='INVENTORY.json' and type(raw) is bytes and raw for name,raw in members.items()),'CAPSULE_MEMBER')
    total=sum(map(len,members.values()));need(total<=MAXIMUM-65536,'CAPSULE_LIMIT')
    inventory={'schema':'SERVER_PRIVATE_CAPSULE_INVENTORY_V2','members':{name:{'bytes':len(raw),'sha256':digest(raw)}
                for name,raw in sorted(members.items())},'total_bytes':total}
    files=dict(members,**{'INVENTORY.json':canonical(inventory)});out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,raw in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o600;info.uid=info.gid=info.mtime=0
            archive.addfile(info,io.BytesIO(raw))
    raw=out.getvalue();need(len(raw)<=MAXIMUM,'CAPSULE_LIMIT');return raw,digest(files['INVENTORY.json'])


def unpack(raw):
    need(type(raw) is bytes and 0<len(raw)<=MAXIMUM,'CAPSULE_LIMIT');files={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        members=archive.getmembers();need(0<len(members)<=33,'CAPSULE_MEMBER_SET')
        for member in members:
            need(member.isfile() and member.name not in files and re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,120}',member.name)
                 and 0<member.size<=MAXIMUM,'CAPSULE_MEMBER')
            files[member.name]=archive.extractfile(member).read()
    need('INVENTORY.json' in files,'CAPSULE_NO_INVENTORY');inv=strict(files.pop('INVENTORY.json'))
    need(inv['schema']=='SERVER_PRIVATE_CAPSULE_INVENTORY_V2' and set(inv['members'])==set(files)
         and sum(map(len,files.values()))==inv['total_bytes'],'CAPSULE_INVENTORY')
    for name,body in files.items():need(inv['members'][name]=={'bytes':len(body),'sha256':digest(body)},'CAPSULE_BODY_PIN')
    return files


class NativeRetainer:
    def __init__(self,guard,runner,output,entry):self.guard,self.runner,self.output,self.entry=guard,runner,output,entry

    def retain(self,result,originals,request,*,recheck,gates=None):
        entry=self.entry;need(request['pins']['retention_authority_sha256']==sha(entry['authority_sha256']),
                              'RETENTION_NOT_AUTHORIZED')
        recipient=entry['recipient'];need(re.fullmatch('age1[0-9a-z]{58}',recipient),'RETENTION_RECIPIENT')
        members={role+'.json':original['raw'] for role,original in originals.items()}
        members['RESULT.json']=result
        for role,raw in (gates or {}).items():
            need(re.fullmatch('[A-Za-z0-9_-]{1,64}',role),'RETENTION_GATE_ROLE');members['gate-'+role+'.json']=raw
        if self.guard.mode=='REAL':
            from runtime import physical
            acceptance,_=physical(self.guard.acceptance)
            need(digest(acceptance)==self.guard.pin,'RETENTION_ACCEPTANCE_CHANGED');members['RUNTIME_ACCEPTANCE.json']=acceptance
            for role,name in (('registry','REGISTRY.json'),('source_manifest','SOURCE_MANIFEST.json')):
                selected=self.guard.value['spec']['files'][role];raw,_=physical(selected['path'])
                need(digest(raw)==sha(selected['sha256']),'RETENTION_ORIGINAL_PIN');members[name]=raw
        private,pin=pack(members);recheck();self.guard.recheck()
        age=self.guard.value['spec']['executables']['age']['path']
        encrypted=self.runner.run([age,'--encrypt','--recipient',recipient],stdin=private,
                                   limit=MAXIMUM+65536,seconds=20)
        need(encrypted['returncode']==0 and encrypted['stdout'].startswith(b'age-encryption.org/v1\n'),
             'RETENTION_CIPHER_UNCERTAIN')
        recheck();name=digest(result)+'.age';cipher=encrypted['stdout'];self.output.create(name,cipher)
        return {'schema':'SERVER_RETENTION_RECEIPT_V2','inventory_sha256':pin,'cipher_sha256':digest(cipher),
                'cipher_bytes':len(cipher),'plaintext_posted':False,'signature_generated':False}
