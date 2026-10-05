"""parts/files.py and parts/parents.py on the emulated host: a private directory and private files, state by state,
with every call failing once and the process dying at every call. No file of this machine is touched."""
from datetime import timedelta
import errno
import os
import stat
import types

import pytest

import demos
import family as f
import hostemu

M=lambda:f.load(demos.WRITE).m
refusal=f.refusal
GO16='0123456789abcdef'
PARENT=hostemu.DATA
CONTENT=b'{"schema":"SYNTHETIC_RELEASE","epoch":"R2D2-V2-SHADOW-2026-10-05"}'
ZERO={'issued':0,'succeeded':0,'failed_nothing_changed':0,'uncertain':0}

class Bench:
    """A pinned parent on a fresh emulated host, and the calls of the part with that host."""
    def __init__(self,parent=PARENT,umask=0o077):
        self.m=m=M();self.host=host=f.wire(types.SimpleNamespace(m=m),hostemu.world());self.state=m.Effects();self.gate=lambda:60.0;self.handles={}
        host.umask(umask);self.rows=hostemu.rows(host,parent)
        self.parent=m.Pinned(host,m.walk_pinned(host,self.rows,self.gate,[]),rows=self.rows);self.path=parent
        host.log.clear();host.calls=0
    def directory(self,name='release-20261005',mode=0o700,key='DIR'):
        return self.m.create_directory(key,self.path+'/'+name,mode,self.parent,self.host,self.gate,self.state,self.handles)
    def file(self,name='release.json',content=CONTENT,mode=0o600,index=0,directory=None,go16=GO16):
        directory=directory or self.handles['DIR'];base=self.path+'/release-20261005' if directory is self.handles.get('DIR') else self.path
        return self.m.create_file(index,'FILE',base+'/'+name,content,mode,directory,self.host,self.gate,self.state,go16)
    def names(self,path):return sorted(self.host.tree.get(path).children)
    def calls(self,*kinds):return [entry for entry in self.host.log if entry[0] in kinds]

def ready():
    bench=Bench();assert bench.directory()['state']=='CREATED_DURABLE';bench.host.log.clear();bench.host.calls=0;return bench

# ---------------------------------------------------------------- the directory
def test_directory_is_one_mkdir_by_descriptor_proved_through_a_descriptor_and_fsynced():
    bench=Bench();before=bench.host.tree.snapshot();entry=bench.directory()
    assert entry=={'key':'DIR','path':PARENT+'/release-20261005','state':'CREATED_DURABLE','code':None,'errno':None,'fsync_directory':True,'fsync_parent':True,
                   'observed':{'type':'dir','uid':0,'gid':0,'mode_octal':'0700','device':hostemu.DATA_DEVICE,'inode':bench.host.tree.get(PARENT+'/release-20261005').ino,'entries':0}}
    assert bench.calls('mkdir')==[('mkdir',PARENT+'/release-20261005',0o700)] and [entry[1] for entry in bench.calls('fsync')]==[PARENT+'/release-20261005',PARENT]
    assert bench.state.counts()=={'issued':1,'succeeded':1,'failed_nothing_changed':0,'uncertain':0} and bench.handles['DIR'].fd in bench.host.fds
    node=bench.host.tree.get(PARENT+'/release-20261005');assert (node.kind,node.uid,node.gid,node.mode,node.synced)==('dir',0,0,0o700,True)
    assert bench.m.readback_directory(PARENT+'/release-20261005',0o700,bench.handles['DIR'],bench.host,bench.gate,0) is None
    assert bench.m.readback_directory(PARENT+'/release-20261005',0o700,bench.handles['DIR'],bench.host,bench.gate,1)=='READBACK_MISMATCH'
    # the parent before the run, plus exactly the one new name
    assert bench.names(PARENT)==sorted(['.r2d2-v2-pinned','lost+found','provider=synthetic','release-20261005'])

def test_directory_that_exists_is_never_touched():
    bench=Bench();bench.host.tree.add(PARENT+'/release-20261005',uid=1000,mode=0o755,dev=hostemu.DATA_DEVICE);before=bench.host.tree.snapshot()
    entry=bench.directory();assert (entry['state'],entry['code'],entry['errno'])==('NOT_CREATED','DESTINATION_APPEARED_AFTER_PRECHECK',errno.EEXIST)
    assert bench.host.tree.snapshot()==before and bench.state.clean() and bench.state.counts()['failed_nothing_changed']==1 and 'DIR' not in bench.handles

@pytest.mark.parametrize('mode,name',[(0o755,'x'),(0o777,'x'),('0700','x'),(448.0,'x'),(True,'x'),(0o700,'.hidden'),(0o700,'a b'),(0o700,''),(0o700,'sub/x'),(0o700,'../x'),
                                      (0o700,None)])
def test_directory_request_outside_the_grammar_changes_nothing(mode,name):
    path=None if name is None else PARENT+'/'+name                      # '' names the parent itself; sub/x is not a direct child of the pinned parent
    bench=Bench();entry=bench.m.create_directory('DIR',path,mode,bench.parent,bench.host,bench.gate,bench.state,bench.handles)
    assert (entry['state'],entry['code'])==('NOT_ATTEMPTED','DIRECTORY_REQUEST_INVALID') and bench.calls('mkdir')==[] and bench.state.counts()==ZERO

def test_directory_metadata_that_is_not_what_was_asked_is_labelled_and_left_in_place():
    for prepare,state,code in ((lambda host:setattr(host,'mask',0o022),'CREATED_DURABLE',None),                    # 0700 survives 0022
                               (lambda host:setattr(host,'mask',0o277),'CREATED_METADATA_MISMATCH','CREATED_METADATA_MISMATCH'),
                               (lambda host:setattr(host,'creator',(1000,0)),'CREATED_METADATA_MISMATCH','CREATED_METADATA_MISMATCH'),
                               (lambda host:setattr(host,'grpid',True),'CREATED_METADATA_MISMATCH','CREATED_METADATA_MISMATCH'),   # the group of the parent (1000)
                               (lambda host:setattr(host,'created_device',999),'CREATED_METADATA_MISMATCH','CREATED_METADATA_MISMATCH')):
        bench=Bench();prepare(bench.host);entry=bench.directory()
        assert (entry['state'],entry['code'])==(state,code) and 'release-20261005' in bench.names(PARENT)
        assert bench.calls('unlink')==[] and bench.state.counts()['succeeded']==1,'nothing is removed or corrected'

def test_directory_whose_name_is_replaced_or_filled_right_after_the_mkdir_is_labelled_not_trusted():
    path=PARENT+'/release-20261005'
    bench=Bench()
    def swap(host,name,detail,calls):
        if name=='fstat' and detail[0]==path and not getattr(host,'swapped',False):
            host.swapped=True;host.tree.get(PARENT).children['release-20261005']=hostemu.Node('dir',mode=0o700,dev=hostemu.DATA_DEVICE,ino=987654)
    bench.host.hook=swap;entry=bench.directory()
    assert (entry['state'],entry['code'])==('CREATED_UNVERIFIED','CREATED_NAME_REPLACED') and bench.calls('fsync')==[] and bench.state.counts()['succeeded']==1
    bench=Bench()
    def fill(host,name,detail,calls):
        if name=='names' and detail[0]==path:host.tree.add(path+'/intruder',kind='file',dev=hostemu.DATA_DEVICE)
    bench.host.hook=fill;entry=bench.directory()
    assert (entry['state'],entry['code'],entry['observed']['entries'])==('CREATED_NOT_EMPTY','CREATED_NOT_EMPTY',1) and bench.calls('fsync')==[]
    assert 'intruder' in bench.names(path),'what appeared in it is left alone'

def test_directory_readback_compares_the_resolved_path_owner_mode_and_entries():
    path=PARENT+'/release-20261005';readback=lambda bench,entries=0:bench.m.readback_directory(path,0o700,bench.handles['DIR'],bench.host,bench.gate,entries)
    bench=ready();assert readback(bench) is None
    bench.host.tree.get(PARENT).children['release-20261005']=hostemu.Node('dir',mode=0o700,dev=hostemu.DATA_DEVICE,ino=987654);assert readback(bench)=='READBACK_MISMATCH'
    for change in (lambda node:setattr(node,'mode',0o755),lambda node:setattr(node,'uid',1000),lambda node:setattr(node,'gid',5)):
        bench=ready();change(bench.host.tree.get(path));assert readback(bench)=='READBACK_MISMATCH'
    bench=ready();bench.host.tree.remove(path);assert readback(bench)=='READBACK_MISMATCH'
    bench=ready();bench.host.tree.remove(path);bench.host.tree.add(path,kind='symlink');assert readback(bench)=='READBACK_MISMATCH'

def test_directory_parent_is_proved_again_before_the_mkdir():
    bench=Bench();bench.host.tree.get(PARENT).ino+=1;entry=bench.directory()
    assert (entry['state'],entry['code'])==('NOT_ATTEMPTED','PARENT_REPLACED') and bench.calls('mkdir')==[] and bench.state.counts()==ZERO
    bench=Bench();bench.host.tree.get('/mnt').mode=0o777;assert bench.directory()['code']=='PARENT_REPLACED' and bench.calls('mkdir')==[]

def test_directory_failures_by_errno_and_expiry():
    for number,code in ((errno.EROFS,'FILESYSTEM_READ_ONLY'),(errno.ENOSPC,'FILESYSTEM_FULL'),(errno.EDQUOT,'FILESYSTEM_FULL'),(errno.EACCES,'FILESYSTEM_ACCESS_DENIED'),
                        (errno.EPERM,'FILESYSTEM_ACCESS_DENIED'),(errno.EIO,'FILESYSTEM_ERROR')):
        bench=Bench()
        def hook(host,name,detail,calls,number=number):
            if name=='mkdir':raise OSError(number,'injected')
        bench.host.hook=hook;entry=bench.directory()
        assert (entry['state'],entry['code'],entry['errno'])==('NOT_CREATED',code,number) and bench.state.clean() and 'release-20261005' not in bench.names(PARENT)
    bench=Bench();calls=[0]
    def gate():
        calls[0]+=1
        if calls[0]>4:raise bench.m.Refused('GO_EXPIRED')
        return 60.0
    bench.gate=gate;entry=bench.directory();assert (entry['state'],entry['code'])==('NOT_ATTEMPTED','GO_EXPIRED') and bench.calls('mkdir')==[]

def test_directory_every_call_fails_once_and_the_row_never_claims_less_than_what_exists():
    baseline=Bench();baseline.directory();total=baseline.host.calls;assert total>=10
    for kind in (OSError,RuntimeError):
        for index in range(1,total+1):
            bench=Bench()
            def hook(host,name,detail,calls,index=index,kind=kind):
                if calls==index:raise kind(5,'injected') if kind is OSError else kind('injected')
            bench.host.hook=hook
            try:entry=bench.directory()
            except RuntimeError:entry=None                         # an exception that is not an OS error may escape a mutating call: the run's last resort files it
            exists='release-20261005' in bench.names(PARENT)
            if entry is None:
                assert bench.state.pending or not exists;continue
            assert entry['state'] in bench.m.DIRECTORY_STATES
            if exists:assert entry['state'].startswith('CREATED') and bench.state.counts()['succeeded']==1
            else:assert entry['state'] in ('NOT_ATTEMPTED','NOT_CREATED') and bench.state.clean()
            if entry['state']=='CREATED_DURABLE':assert entry['fsync_directory'] and entry['fsync_parent']


# ---------------------------------------------------------------- one file
def test_file_is_written_under_a_temporary_fsynced_linked_and_the_temporary_removed_by_identity():
    bench=ready();entry=bench.file();temp='.hostops-%s-0.partial'%GO16;base=PARENT+'/release-20261005'
    node=bench.host.tree.get(base+'/release.json')
    assert entry=={'key':'FILE','path':base+'/release.json','state':'INSTALLED_DURABLE','code':None,'errno':None,'bytes':len(CONTENT),'sha256_signed':f.sha(CONTENT),
                   'sha256_observed':None,'mode_octal':'0600','uid':0,'gid':0,'links':1,'device':hostemu.DATA_DEVICE,'inode':node.ino,'temporary_name':temp,
                   'temporary_removed':True,'temporary_removal_code':None,'temporary_removal_errno':None,'fsync_file':True,'fsync_directory_after_link':True,
                   'fsync_directory_after_removal':True}
    order=[entry[0] for entry in bench.calls('create','write','fsync','link','unlink')]
    assert order==['create','write','fsync','link','fsync','unlink','fsync']
    create=bench.calls('create')[0];assert create[1]==base+'/'+temp and create[3]==0o600
    assert create[2]==os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
    assert bench.calls('link')==[('link',base+'/'+temp,base+'/release.json')] and bench.calls('unlink')==[('unlink',base+'/'+temp)]
    assert [entry[1] for entry in bench.calls('fsync')]==[base+'/'+temp,base,base]
    assert bench.names(base)==['release.json'] and (bytes(node.content),node.mode,node.uid,node.gid,node.nlink,node.synced)==(CONTENT,0o600,0,0,1,True)
    assert bench.state.counts()=={'issued':5,'succeeded':5,'failed_nothing_changed':0,'uncertain':0}       # the mkdir of ready(), create, write, link, unlink
    assert bench.m.readback_file(entry,CONTENT,0o600,bench.handles['DIR'],bench.host,bench.gate) is None and entry['sha256_observed']==f.sha(CONTENT)
    assert bench.m.objects_left([{'state':'CREATED_DURABLE'}],[entry])==2

def test_file_larger_than_one_write_is_written_in_blocks_each_counted():
    bench=ready();content=bytes(range(256))*600;entry=bench.file(content=content)           # 153600 bytes: three blocks
    assert entry['state']=='INSTALLED_DURABLE' and [call[2] for call in bench.calls('write')]==[65536,65536,22528]
    assert bytes(bench.host.tree.get(PARENT+'/release-20261005/release.json').content)==content and bench.state.counts()['succeeded']==7

def test_file_mode_0644_under_umask_0022_and_a_umask_that_strips_the_mode_is_withdrawn():
    bench=Bench(umask=0o022);bench.directory();assert bench.file(mode=0o644)['mode_octal']=='0644'
    bench=ready();entry=bench.file(mode=0o644)                                           # umask 0077 leaves 0600: not what was asked
    assert (entry['state'],entry['code'],entry['temporary_removed'])==('NOT_CREATED','CREATED_METADATA_MISMATCH',True) and bench.names(PARENT+'/release-20261005')==[]

@pytest.mark.parametrize('change',[dict(content=b''),dict(content='text'),dict(content=b'x'*1048577),dict(mode=0o640),dict(mode=0o666),dict(mode='0600'),dict(mode=True),
                                   dict(name='.hidden'),dict(name='a b'),dict(name='.hostops-0123456789abcdef-0.partial'),dict(index=100),dict(index=-1),dict(index='0'),
                                   dict(go16='0123'),dict(go16='G'*16),dict(go16=None),dict(index=None),dict(index=1.0)])
def test_file_request_outside_the_grammar_changes_nothing(change):
    bench=ready();entry=bench.file(**change)
    assert (entry['state'],entry['code'])==('NOT_ATTEMPTED','FILE_REQUEST_INVALID') and bench.calls('create')==[] and bench.state.counts()['issued']==1   # the mkdir of ready()

def test_file_never_replaces_a_name_that_exists_or_appears():
    base=PARENT+'/release-20261005'
    # the final name exists before the link: the link fails, the temporary is withdrawn, the existing file is untouched
    bench=ready();bench.host.tree.add(base+'/release.json',kind='file',content=b'foreign',dev=hostemu.DATA_DEVICE,mode=0o644);entry=bench.file()
    assert (entry['state'],entry['code'],entry['errno'],entry['temporary_removed'])==('NOT_CREATED','DESTINATION_APPEARED_AFTER_PRECHECK',errno.EEXIST,True)
    assert bench.names(base)==['release.json'] and bytes(bench.host.tree.get(base+'/release.json').content)==b'foreign'
    # the temporary name is taken: nothing is created and nothing is removed
    bench=ready();bench.host.tree.add(base+'/.hostops-%s-0.partial'%GO16,kind='file',content=b'older',dev=hostemu.DATA_DEVICE);entry=bench.file()
    assert (entry['state'],entry['code'])==('NOT_CREATED','TEMPORARY_NAME_OCCUPIED') and bench.calls('unlink')==[] and bench.names(base)==['.hostops-%s-0.partial'%GO16]
    # a symbolic link at the final name is a name that exists
    bench=ready();bench.host.tree.add(base+'/release.json',kind='symlink',dev=hostemu.DATA_DEVICE);entry=bench.file()
    assert entry['code']=='DESTINATION_APPEARED_AFTER_PRECHECK' and bench.host.tree.get(base+'/release.json').kind=='symlink'

def test_temporary_swapped_before_the_link_or_before_the_removal_is_not_linked_and_not_removed():
    base=PARENT+'/release-20261005';temp='.hostops-%s-0.partial'%GO16
    def swap(host):
        node=host.tree.get(base).children.pop(temp);host.tree.add(base+'/'+temp,kind='file',content=b'not ours',dev=hostemu.DATA_DEVICE);return node
    # swapped after the fsync of the file: the lstat before the link sees another inode
    bench=ready()
    def hook(host,name,detail,calls):
        if name=='fsync' and detail[0].endswith(temp) and not getattr(host,'swapped',False):host.swapped=True;swap(host)
    bench.host.hook=hook;entry=bench.file()
    assert (entry['state'],entry['code'])==('TEMPORARY_ONLY','TEMPORARY_REPLACED') and bench.calls('link')==[] and bench.calls('unlink')==[]
    assert bytes(bench.host.tree.get(base+'/'+temp).content)==b'not ours'
    # swapped after the link: the final name holds our file, the removal finds another inode at the temporary name and leaves it
    bench=ready()
    def hook(host,name,detail,calls):
        if name=='link':host.pending_swap=True
        elif name=='fsync' and getattr(host,'pending_swap',False):host.pending_swap=False;swap(host)
    bench.host.hook=hook;entry=bench.file()
    assert (entry['state'],entry['code'],entry['temporary_removed'])==('LINKED_TEMPORARY_PRESENT','TEMPORARY_REPLACED',False) and bench.calls('unlink')==[]
    assert sorted(bench.names(base))==[temp,'release.json'] and bench.m.objects_left([],[entry])==2

def test_created_file_must_be_on_the_device_of_its_directory_with_one_link_before_and_after():
    base=PARENT+'/release-20261005';temp='.hostops-%s-0.partial'%GO16
    bench=ready();bench.host.created_device=999;entry=bench.file()
    assert (entry['state'],entry['code'],entry['device'],entry['temporary_removed'])==('NOT_CREATED','CREATED_METADATA_MISMATCH',999,True) and bench.names(base)==[]
    # a second name for the temporary before it is looked at: not the file this run alone holds
    bench=ready()
    def linked_early(host,name,detail,calls):
        if name=='write':host.tree.get(base+'/'+temp).nlink=2
    bench.host.hook=linked_early;entry=bench.file();assert (entry['state'],entry['code'],entry['links'])==('NOT_CREATED','CREATED_METADATA_MISMATCH',2) and bench.calls('link')==[]
    # a second name that appears after the metadata was read and before the link: seen by the lstat right before the link
    bench=ready()
    def linked_late(host,name,detail,calls):
        if name=='lstat' and detail[0]==base+'/'+temp and not getattr(host,'done',False):host.done=True;host.tree.get(base+'/'+temp).nlink=2
    bench.host.hook=linked_late;entry=bench.file()
    assert (entry['state'],entry['code'])==('TEMPORARY_ONLY','TEMPORARY_REPLACED') and bench.calls('link')==[] and bench.calls('unlink')==[] and bench.names(base)==[temp]
    # a second name for the final file after the temporary was removed: installed, but not what this run alone made
    bench=ready()
    def linked_after(host,name,detail,calls):
        if name=='unlink':host.tree.get(base+'/release.json').nlink+=1
    bench.host.hook=linked_after;entry=bench.file()
    assert (entry['state'],entry['code'],entry['links'],entry['temporary_removed'])==('INSTALLED_NOT_DURABLE','CREATED_METADATA_MISMATCH',2,True)

def test_errno_of_the_failure_is_kept_when_the_withdrawal_fails_too():
    base=PARENT+'/release-20261005';temp='.hostops-%s-0.partial'%GO16;bench=ready()
    def hook(host,name,detail,calls):
        if name=='write':raise OSError(errno.ENOSPC,'injected')
        if name=='unlink':raise OSError(errno.EIO,'injected')
    bench.host.hook=hook;entry=bench.file()
    assert (entry['state'],entry['code'],entry['errno'])==('TEMPORARY_ONLY','FILESYSTEM_FULL',errno.ENOSPC)
    assert (entry['temporary_removed'],entry['temporary_removal_code'],entry['temporary_removal_errno'])==(False,'TEMPORARY_REMOVAL_FAILED',errno.EIO) and bench.names(base)==[temp]

def test_file_failures_before_the_final_name_exists_withdraw_the_temporary_of_this_run():
    base=PARENT+'/release-20261005'
    for call,number,code in (('write',errno.ENOSPC,'FILESYSTEM_FULL'),('write',errno.EIO,'FILESYSTEM_ERROR'),('fsync',errno.EIO,'FSYNC_FAILED'),('link',errno.EPERM,'FILESYSTEM_ACCESS_DENIED')):
        bench=ready();fired=[False]
        def hook(host,name,detail,calls,call=call,number=number):
            if name==call and not fired[0]:fired[0]=True;raise OSError(number,'injected')
        bench.host.hook=hook;entry=bench.file()
        assert (entry['state'],entry['code'],entry['errno'],entry['temporary_removed'])==('NOT_CREATED',code,number,True),call
        assert bench.names(base)==[] and not bench.state.clean(),'a create and an unlink succeeded: the run is no longer a refusal'
    bench=ready()
    def hook(host,name,detail,calls):
        if name=='create':raise OSError(errno.EROFS,'injected')
    bench.host.hook=hook;entry=bench.file();assert (entry['state'],entry['code'])==('NOT_CREATED','FILESYSTEM_READ_ONLY') and bench.state.counts()['failed_nothing_changed']==1
    # a short write is not a complete file
    bench=ready();bench.host.write=lambda fd,data:0;entry=bench.file();assert (entry['state'],entry['code'])==('NOT_CREATED','WRITE_INCOMPLETE') and bench.names(base)==[]

def test_file_expiry_never_removes_and_the_state_says_what_is_on_the_host():
    base=PARENT+'/release-20261005';temp='.hostops-%s-0.partial'%GO16;baseline=ready();counter=[0]
    def counting():
        counter[0]+=1;return 60.0
    baseline.gate=counting;baseline.file();total=counter[0];assert total>=8
    seen=set()
    for limit in range(total+1):
        bench=ready();calls=[0]
        def gate(limit=limit):
            calls[0]+=1
            if calls[0]>limit:raise bench.m.Refused('GO_EXPIRED')
            return 60.0
        bench.gate=gate;entry=bench.file();names=bench.names(base);seen.add(entry['state'])
        assert entry['code']==('GO_EXPIRED' if entry['state']!='INSTALLED_DURABLE' else None) or entry['code']=='PARENT_REPLACED'
        assert {'NOT_ATTEMPTED':[],'TEMPORARY_ONLY':[temp],'LINKED_TEMPORARY_PRESENT':[temp,'release.json'],'INSTALLED_DURABLE':['release.json']}[entry['state']]==names
        assert entry['temporary_removed']==(entry['state']=='INSTALLED_DURABLE')
    assert seen=={'NOT_ATTEMPTED','TEMPORARY_ONLY','LINKED_TEMPORARY_PRESENT','INSTALLED_DURABLE'}

def test_file_every_call_fails_once_or_the_process_dies_and_the_ledger_matches_the_tree():
    """For every call of the installation: an OS error, another exception, and the death of the process. Whatever the
    row says is what the directory holds; only this run's own temporary is ever removed; the final name, when it
    exists, holds the complete signed bytes."""
    base=PARENT+'/release-20261005';temp='.hostops-%s-0.partial'%GO16;baseline=ready();baseline.file();total=baseline.host.calls;assert total>=20
    expect={'NOT_ATTEMPTED':[[]],'NOT_CREATED':[[]],'TEMPORARY_ONLY':[[temp]],'LINKED_TEMPORARY_PRESENT':[[temp,'release.json']],
            'INSTALLED_NOT_DURABLE':[['release.json']],'INSTALLED_DURABLE':[['release.json']]}
    for kind in (OSError,RuntimeError,hostemu.Death):
        for index in range(1,total+1):
            bench=ready()
            def hook(host,name,detail,calls,index=index,kind=kind):
                if calls==index:raise kind(5,'injected') if kind is OSError else kind('injected')
            bench.host.hook=hook
            try:entry=bench.file()
            except (RuntimeError,hostemu.Death):entry=None
            names=bench.names(base);final=bench.host.tree.get(base+'/release.json')
            if final is not None:assert bytes(final.content)==CONTENT and final.mode==0o600,'only complete bytes ever appear under the final name'
            assert all(call[1]==base+'/'+temp for call in bench.calls('unlink')),'nothing but the temporary of this run is removed'
            if entry is None:
                assert not bench.state.clean() or names==[],(kind,index);continue
            assert entry['state'] in bench.m.FILE_STATES and names in expect[entry['state']],(kind,index,entry['state'],names)
            if entry['state']=='INSTALLED_DURABLE':assert entry['fsync_file'] and entry['fsync_directory_after_link'] and entry['fsync_directory_after_removal']
            if names and bench.state.clean():raise AssertionError('something exists and the run still counts as clean')

def test_file_directory_replaced_before_the_temporary_or_before_the_link_stops_without_removal():
    base=PARENT+'/release-20261005'
    bench=ready();bench.host.tree.get(base).ino+=1;entry=bench.file();assert (entry['state'],entry['code'])==('NOT_ATTEMPTED','PARENT_REPLACED') and bench.calls('create')==[]
    bench=ready()
    def hook(host,name,detail,calls):
        if name=='fsync':host.tree.get(PARENT).mode=0o777            # the parent of the directory changes after the bytes are written
    bench.host.hook=hook;entry=bench.file()
    assert (entry['state'],entry['code'])==('TEMPORARY_ONLY','PARENT_REPLACED') and bench.calls('link')==[] and bench.calls('unlink')==[]

def test_readback_file_finds_every_difference():
    base=PARENT+'/release-20261005'
    for change,code in ((lambda node:node.content.extend(b'x'),'READBACK_HASH_MISMATCH'),(lambda node:setattr(node,'mode',0o644),'READBACK_HASH_MISMATCH'),
                        (lambda node:setattr(node,'uid',1000),'READBACK_HASH_MISMATCH'),(lambda node:setattr(node,'nlink',2),'READBACK_HASH_MISMATCH'),
                        (lambda node:setattr(node,'ino',node.ino+1),'READBACK_HASH_MISMATCH'),(lambda node:setattr(node,'kind','fifo'),'FILE_NOT_REGULAR')):
        bench=ready();entry=bench.file();change(bench.host.tree.get(base+'/release.json'))
        assert bench.m.readback_file(entry,CONTENT,0o600,bench.handles['DIR'],bench.host,bench.gate)==code
    bench=ready();entry=bench.file();bench.host.tree.remove(base+'/release.json')
    assert bench.m.readback_file(entry,CONTENT,0o600,bench.handles['DIR'],bench.host,bench.gate)=='READBACK_UNAVAILABLE'
    bench=ready();entry=bench.file();assert bench.m.readback_file(entry,CONTENT+b'x',0o600,bench.handles['DIR'],bench.host,bench.gate)=='READBACK_HASH_MISMATCH'
    bench=ready();entry=bench.file();bench.host.tree.get(PARENT).ino+=1
    assert bench.m.readback_file(entry,CONTENT,0o600,bench.handles['DIR'],bench.host,bench.gate)=='PARENT_REPLACED'

def test_objects_left_counts_what_the_rows_say_exists():
    m=M();row=lambda state:{'state':state}
    assert m.objects_left([row('CREATED_DURABLE'),row('NOT_CREATED'),row('CREATED_METADATA_MISMATCH'),row('NOT_ATTEMPTED')],
                          [row('INSTALLED_DURABLE'),row('TEMPORARY_ONLY'),row('LINKED_TEMPORARY_PRESENT'),row('NOT_CREATED'),row('INSTALLED_NOT_DURABLE'),row('NOT_ATTEMPTED')])==2+1+1+2+1

def test_file_request_validator():
    m=M();ok=lambda **change:m.file_request(**dict(dict(name='release.json',content_sha256='a'*64,size=10,mode=0o600),**change))
    assert ok() and ok(mode=0o644) and ok(size=1048576)
    for change in (dict(name='.x'),dict(name='a/b'),dict(name=''),dict(content_sha256='0'*64),dict(content_sha256='A'*64),dict(size=0),dict(size=1048577),dict(size=True),
                   dict(mode=0o640),dict(mode=True),dict(mode='0600')):assert not ok(**change),change


# ---------------------------------------------------------------- parents.py
def row(path,uid=0,gid=0,mode=0o755,device=1,inode=2):return {'path':path,'device':device,'inode':inode,'uid':uid,'gid':gid,'mode':mode}
def test_chain_rows_outside_an_open_root_are_root_owned_and_closed_and_inside_it_as_signed_with_one_floor():
    m=M();good=[row('/'),row('/mnt'),row('/mnt/day-d-data',uid=1000,gid=1000)]
    assert m.validate_chain(good,'/mnt/day-d-data','/mnt/day-d-data') is good
    assert refusal(lambda:m.validate_chain(good,'/mnt/day-d-data'))=='CHAIN_ROW_UNSAFE'
    assert refusal(lambda:m.validate_chain(good,'/mnt/day-d-data','/mnt/other'))=='CHAIN_ROW_UNSAFE'
    assert refusal(lambda:m.validate_chain([row('/'),row('/mnt',uid=1000),good[2]],'/mnt/day-d-data','/mnt/day-d-data'))=='CHAIN_ROW_UNSAFE','above the open root nothing is relaxed'
    assert refusal(lambda:m.validate_chain([row('/'),row('/mnt',mode=0o775),good[2]],'/mnt/day-d-data','/mnt/day-d-data'))=='CHAIN_ROW_UNSAFE'
    for mode,code in ((0o775,None),(0o1777,None),(0o757,'CHAIN_ROW_WORLD_WRITABLE'),(0o777,'CHAIN_ROW_WORLD_WRITABLE'),(0o700,None)):
        rows=[row('/'),row('/mnt'),row('/mnt/day-d-data',uid=1000,gid=1000,mode=mode)]
        if code is None:m.validate_chain(rows,'/mnt/day-d-data','/mnt/day-d-data')
        else:assert refusal(lambda:m.validate_chain(rows,'/mnt/day-d-data','/mnt/day-d-data'))==code
    deep=good+[row('/mnt/day-d-data/sub',uid=1000,mode=0o2755)]
    m.validate_chain(deep,'/mnt/day-d-data/sub','/mnt/day-d-data')
    assert refusal(lambda:m.validate_chain(deep,'/mnt/day-d-data/sub','/mnt/day-d-data',receives_entry=True))=='PARENT_SETGID'
    for open_root in ('/','relative','/a/../b',7,''):assert refusal(lambda:m.validate_chain(good,'/mnt/day-d-data',open_root))=='PATH_INVALID'
    # the rows themselves: one per component, in order, every value an integer in range
    for rows in (good[:2],good+[row('/x')],[row('/'),row('/mnt'),row('/mnt/other')],[row('/'),row('/mnt'),dict(good[2],inode=0)],[row('/'),row('/mnt'),dict(good[2],mode=0o10000)],
                 [row('/'),row('/mnt'),dict(good[2],uid='0')],[row('/'),row('/mnt'),dict(good[2],extra=1)],None):
        assert refusal(lambda:m.validate_chain(rows,'/mnt/day-d-data','/mnt/day-d-data'))=='CHAIN_ROW_INVALID'

def test_stat_signature_changes_with_content_identity_owner_and_mode_and_not_with_a_read():
    m=M();host=hostemu.world();node=host.tree.get(hostemu.ENV_FILE);before=m.stat_signature(node.stat())
    assert before==m.stat_signature(node.stat()) and len(before)==8
    for change in (lambda:node.content.extend(b'x'),lambda:setattr(node,'mtime',node.mtime+1),lambda:setattr(node,'ctime',node.ctime+1),lambda:setattr(node,'ino',node.ino+1),
                   lambda:setattr(node,'uid',0),lambda:setattr(node,'mode',0o644),lambda:setattr(node,'dev',node.dev+1),lambda:setattr(node,'gid',0)):
        change();after=m.stat_signature(node.stat());assert after!=before;before=after
    node.atime+=5;assert m.stat_signature(node.stat())==before,'the access time is not part of it'

def test_chain_effects_and_free_bytes():
    m=M();host=hostemu.world();rows=hostemu.rows(host,hostemu.DATA);effects=m.chain_effects(rows)
    assert effects=={'path':hostemu.DATA,'row':rows[-1],'chain_sha256':f.sha(f.canonical(rows)),'mount_point_by_device_change':hostemu.DATA}
    assert m.chain_effects(hostemu.rows(host,'/var/lib'))['mount_point_by_device_change']=='/'
    bench=Bench();assert bench.m.free_bytes(bench.host,bench.parent.fd)==13200816*4096
    bench=Bench(parent='/var/lib');assert bench.m.free_bytes(bench.host,bench.parent.fd)==145315507*4096==595212316672
