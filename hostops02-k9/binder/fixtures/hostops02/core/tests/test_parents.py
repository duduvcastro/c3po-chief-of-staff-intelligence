"""The pinned-parent primitives of parts/core.py, on the emulated host: the walk from "/" against signed rows, the
held descriptor proved again before each use, the probe that never follows a link, the bounded read of a regular
file, the boot identifier. These are the functions every operation of the family stands on; HOSTOPS01 tested them
through its four operations, here they are tested directly."""
import os
import stat
import types

import pytest

import demos
import family as f
import hostemu

M=lambda:f.load(demos.WRITE).m
refusal=f.refusal
gate=lambda:60.0
def host_of(m):return f.wire(types.SimpleNamespace(m=m),hostemu.world())
def walk(m,host,rows,**options):
    observed=[];fd=m.walk_pinned(host,rows,gate,observed,**options);return fd,observed

# ---------------------------------------------------------------- the walk against signed rows
def test_walk_opens_every_component_by_descriptor_without_following_and_returns_the_last():
    m=M();host=host_of(m);rows=hostemu.rows(host,hostemu.LOCK_DIRECTORY);fd,observed=walk(m,host,rows)
    assert observed==rows and host.path_of(fd)==hostemu.LOCK_DIRECTORY and len(host.fds)==1,'only the last descriptor stays open'
    opens=[entry for entry in host.log if entry[0]=='open'];assert [entry[1] for entry in opens]==[row['path'] for row in rows]
    assert all(entry[2]==os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|hostemu.NOATIME for entry in opens)
    assert [entry[1] for entry in host.log if entry[0]=='lstat']==[row['path'] for row in rows[1:]],'each component is classified by lstat before it is opened'

@pytest.mark.parametrize('field,value',[('device',999),('inode',123456),('uid',1),('gid',1),('mode',0o750),('mode',0o1755),('mode',0o2755)])
@pytest.mark.parametrize('depth',[0,1,-1])
def test_walk_compares_every_value_of_every_row_with_the_descriptor_held(field,value,depth):
    m=M();host=host_of(m);rows=hostemu.rows(host,'/etc/systemd/system');rows[depth]=dict(rows[depth],**{field:value});observed=[]
    assert refusal(lambda:m.walk_pinned(host,rows,gate,observed))=='PARENT_IDENTITY_MISMATCH' and host.fds=={}
    assert observed[-1]['path']==rows[depth]['path'] and observed[-1][field]!=value,'the refusal carries what was seen'

def test_walk_without_the_device_comparison_still_compares_the_rest():
    m=M();host=host_of(m);rows=hostemu.rows(host,'/etc');changed=[dict(row,device=row['device']+7) for row in rows]
    fd,_=walk(m,host,changed,compare_device=False);host.close(fd)
    assert refusal(lambda:walk(m,host,changed))=='PARENT_IDENTITY_MISMATCH'
    assert refusal(lambda:walk(m,host,[dict(row,inode=row['inode']+1) for row in rows],compare_device=False))=='PARENT_IDENTITY_MISMATCH'

def test_walk_classifies_a_missing_component_a_symbolic_link_and_a_file_before_opening():
    m=M();host=host_of(m);rows=hostemu.rows(host,hostemu.LOCK_DIRECTORY)
    host.tree.remove(hostemu.LOCK_DIRECTORY);assert refusal(lambda:walk(m,host,rows))=='PARENT_MISSING' and host.fds=={}
    host.tree.add(hostemu.LOCK_DIRECTORY,kind='symlink');observed=[]
    assert refusal(lambda:m.walk_pinned(host,rows,gate,observed))=='PARENT_SYMLINK_COMPONENT' and observed[-1]['type']=='symlink'
    assert not [entry for entry in host.log if entry[0]=='open' and entry[1]==hostemu.LOCK_DIRECTORY],'a link is never opened'
    host.tree.remove(hostemu.LOCK_DIRECTORY);host.tree.add(hostemu.LOCK_DIRECTORY,kind='file')
    assert refusal(lambda:walk(m,host,rows))=='PARENT_NOT_DIRECTORY' and host.fds=={}

def test_walk_sees_a_component_swapped_between_the_lstat_and_the_open():
    m=M();host=host_of(m);rows=hostemu.rows(host,hostemu.LOCK_DIRECTORY)
    def hook(host,name,detail,calls):
        if name=='open' and detail[0]==hostemu.DEPLOY+'/runtime':host.tree.get(hostemu.DEPLOY+'/runtime').ino+=1
    host.hook=hook;assert refusal(lambda:walk(m,host,rows))=='PARENT_CHANGED_DURING_WALK' and host.fds=={}
    host=host_of(m)
    def hook(host,name,detail,calls):
        if name=='open' and detail[0]==hostemu.DEPLOY+'/runtime':raise OSError(40,'ELOOP')
    host.hook=hook;assert refusal(lambda:walk(m,host,rows))=='PARENT_CHANGED_DURING_WALK' and host.fds=={}

def test_walk_closes_its_descriptor_whatever_stops_it_and_stops_at_an_expired_gate():
    m=M();rows=None
    for index in range(1,12):
        host=host_of(m);rows=hostemu.rows(host,'/etc/systemd/system')
        def hook(host,name,detail,calls,index=index):
            if calls==index:raise hostemu.Death('dead')
        host.hook=hook
        try:fd,_=walk(m,host,rows);host.close(fd)
        except hostemu.Death:pass
        assert host.fds=={},index
    host=host_of(m);calls=[0]
    def expiring():
        calls[0]+=1
        if calls[0]>3:raise m.Refused('GO_EXPIRED')
        return 60.0
    assert refusal(lambda:m.walk_pinned(host,hostemu.rows(host,'/etc/systemd/system'),expiring,[]))=='GO_EXPIRED' and host.fds=={}

@pytest.mark.parametrize('change',[lambda rows:rows[:-1],lambda rows:rows+[dict(rows[-1],path=rows[-1]['path']+'/x')],lambda rows:[dict(row,path='/other') if index==1 else row for index,row in enumerate(rows)],
                                   lambda rows:[dict(rows[0],extra=1)]+rows[1:],lambda rows:[{key:value for key,value in rows[0].items() if key!='gid'}]+rows[1:],
                                   lambda rows:rows[:-1]+[dict(rows[-1],inode=0)],lambda rows:rows[:-1]+[dict(rows[-1],device=-1)],lambda rows:rows[:-1]+[dict(rows[-1],mode=0o10000)],
                                   lambda rows:rows[:-1]+[dict(rows[-1],uid=True)],lambda rows:rows[:-1]+[dict(rows[-1],gid='0')],lambda rows:tuple(rows),lambda rows:None])
def test_chain_rows_are_one_row_per_component_with_exactly_six_integer_members(change):
    m=M();host=host_of(m);rows=hostemu.rows(host,'/etc/systemd/system');assert m.chain_rows(rows,'/etc/systemd/system') is rows
    assert refusal(lambda:m.chain_rows(change(rows),'/etc/systemd/system'))=='CHAIN_ROW_INVALID'

def test_mount_point_is_the_deepest_component_whose_device_differs_from_its_parent():
    m=M();host=host_of(m)
    assert m.mount_point_of(hostemu.rows(host,hostemu.DATA))==hostemu.DATA and m.mount_point_of(hostemu.rows(host,'/var/lib'))=='/'
    host.tree.add(hostemu.DATA+'/a/b',dev=hostemu.DATA_DEVICE);host.tree.get(hostemu.DATA+'/a').dev=hostemu.DATA_DEVICE
    assert m.mount_point_of(hostemu.rows(host,hostemu.DATA+'/a/b'))==hostemu.DATA
    host.tree.get(hostemu.DATA+'/a/b').dev=77;assert m.mount_point_of(hostemu.rows(host,hostemu.DATA+'/a/b'))==hostemu.DATA+'/a/b'


# ---------------------------------------------------------------- the held descriptor, proved again before each use
def pinned(m,host,path):
    rows=hostemu.rows(host,path);return m.Pinned(host,m.walk_pinned(host,rows,gate,[]),rows=rows)
def test_pinned_verify_walks_again_and_compares_the_fresh_descriptor_with_the_one_held():
    m=M();host=host_of(m);parent=pinned(m,host,hostemu.DATA);parent.verify(gate);assert len(host.fds)==1
    for change in (lambda:setattr(host.tree.get(hostemu.DATA),'mode',0o700),lambda:setattr(host.tree.get('/mnt'),'uid',5),lambda:setattr(host.tree.get(hostemu.DATA),'gid',0)):
        host=host_of(m);parent=pinned(m,host,hostemu.DATA);change();assert refusal(lambda:parent.verify(gate))=='PARENT_REPLACED' and len(host.fds)==1
    # the name now leads to another directory with the same owner and mode: the descriptor held is no longer the one at the path
    host=host_of(m);parent=pinned(m,host,hostemu.DATA);old=host.tree.get('/mnt').children.pop('day-d-data')
    host.tree.add(hostemu.DATA,uid=1000,gid=1000,dev=hostemu.DATA_DEVICE,ino=old.ino+1);assert refusal(lambda:parent.verify(gate))=='PARENT_REPLACED'
    host=host_of(m);parent=pinned(m,host,hostemu.DATA);host.tree.remove(hostemu.DATA);assert refusal(lambda:parent.verify(gate))=='PARENT_REPLACED'
    host=host_of(m);parent=pinned(m,host,hostemu.DATA)
    def expired():raise m.Refused('GO_EXPIRED')
    assert refusal(lambda:parent.verify(expired))=='GO_EXPIRED','an expiry is not reported as a replacement'
    parent.close();parent.close();assert host.fds=={}

def test_pinned_child_is_proved_through_its_parent_and_its_own_name():
    m=M();host=host_of(m);parent=pinned(m,host,hostemu.DEPLOY);flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|hostemu.NOATIME
    child=m.Pinned(host,host.open('runtime',flags,dir_fd=parent.fd),parent=parent,name='runtime');child.verify(gate)
    host.tree.get(hostemu.DEPLOY+'/runtime').ino+=1;assert refusal(lambda:child.verify(gate))=='PARENT_REPLACED'
    host=host_of(m);parent=pinned(m,host,hostemu.DEPLOY);child=m.Pinned(host,host.open('runtime',flags,dir_fd=parent.fd),parent=parent,name='runtime')
    host.tree.get(hostemu.DEPLOY).mode=0o700;assert refusal(lambda:child.verify(gate))=='PARENT_REPLACED','a change above the parent is a change of the child'
    host=host_of(m);parent=pinned(m,host,hostemu.DEPLOY);child=m.Pinned(host,host.open('runtime',flags,dir_fd=parent.fd),parent=parent,name='runtime')
    host.tree.remove(hostemu.DEPLOY+'/runtime');assert refusal(lambda:child.verify(gate))=='PARENT_REPLACED'


# ---------------------------------------------------------------- probe and descend: no signed expectation, never a link followed
def test_probe_reports_presence_with_metadata_and_proves_absence_at_the_first_missing_component():
    m=M();host=host_of(m);found=m.probe(host,hostemu.PIN,gate);node=host.tree.get(hostemu.PIN)
    assert found=={'status':'COMPLETE','exists':True,'links':1,'type':'file','uid':0,'gid':0,'mode_octal':'0600','device':hostemu.DATA_DEVICE,'inode':node.ino}
    assert m.probe(host,hostemu.DATA+'/release-x/release.json',gate)=={'status':'COMPLETE','exists':False,'absent_at':hostemu.DATA+'/release-x','absence_proved_at_read':True}
    assert m.probe(host,'/etc/c3po-bar',gate)['exists'] is False and m.probe(host,'/',gate)['type']=='dir' and host.fds=={}
    host.tree.add('/etc/link',kind='symlink',mode=0o777);assert m.probe(host,'/etc/link',gate)['type']=='symlink','a link as the leaf is reported, not followed'
    assert m.probe(host,'/etc/link/below',gate)=={'status':'UNAVAILABLE','code':'SYMLINK_COMPONENT','exists':None,'at':'/etc/link'},'through a link nothing is said to be absent'
    assert refusal(lambda:m.probe(host,hostemu.PIN+'/below',gate))=='COMPONENT_NOT_DIRECTORY' and host.fds=={}
    def hook(host,name,detail,calls):
        if name=='open' and detail[0]=='/mnt':host.tree.get('/mnt').ino+=1
    host.hook=hook;assert refusal(lambda:m.probe(host,hostemu.PIN,gate))=='PATH_CHANGED' and host.fds=={}

def test_descend_returns_rows_in_the_signed_format_and_never_enters_a_link():
    m=M();host=host_of(m);rows=[];fd=m.descend(host,hostemu.LOCK_DIRECTORY,gate,rows)
    assert rows==hostemu.rows(host,hostemu.LOCK_DIRECTORY) and host.path_of(fd)==hostemu.LOCK_DIRECTORY;host.close(fd)
    assert all(entry[2]&os.O_NOFOLLOW for entry in host.log if entry[0]=='open')
    host.tree.add('/etc/link',kind='symlink');assert refusal(lambda:m.descend(host,'/etc/link/x',gate))=='SYMLINK_COMPONENT'
    assert refusal(lambda:m.descend(host,hostemu.PIN,gate))=='COMPONENT_NOT_DIRECTORY' and host.fds=={}
    with pytest.raises(FileNotFoundError):m.descend(host,'/no/such',gate)
    assert host.fds=={}

def test_count_entries_is_bounded_and_names_never_leave_it():
    m=M();host=host_of(m);parent=pinned(m,host,hostemu.DATA);assert m.count_entries(host,parent.fd,gate)==3
    for index in range(10):host.tree.add(hostemu.DATA+'/e%d'%index,dev=hostemu.DATA_DEVICE)
    assert m.count_entries(host,parent.fd,gate)==13 and refusal(lambda:m.count_entries(host,parent.fd,gate,limit=12))=='ENTRY_LIMIT'
    assert host.tree.get(hostemu.DATA).atime==1,'listed through a descriptor opened O_NOATIME'


# ---------------------------------------------------------------- one regular file, bounded and unchanged while read
def test_read_regular_returns_the_bytes_of_a_regular_file_that_did_not_change_while_read():
    m=M();host=host_of(m);parent=pinned(m,host,hostemu.DEPLOY);raw,info=m.read_regular(host,'.deploy-version',parent.fd,gate,64)
    assert raw==(hostemu.REVISION+'\n').encode() and info.st_size==41 and len(host.fds)==1
    opened=[entry for entry in host.log if entry[0]=='open'][-1];assert opened[2]==os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|hostemu.NOATIME
    assert refusal(lambda:m.read_regular(host,'.deploy-version',parent.fd,gate,40))=='FILE_TOO_LARGE'
    assert m.read_regular(host,'.deploy-version',parent.fd,gate,41)[0]==raw
    assert refusal(lambda:m.read_regular(host,'c3po',parent.fd,gate,64))=='FILE_NOT_REGULAR'
    host.tree.add(hostemu.DEPLOY+'/fifo',kind='fifo');assert refusal(lambda:m.read_regular(host,'fifo',parent.fd,gate,64))=='FILE_NOT_REGULAR'
    host.tree.add(hostemu.DEPLOY+'/link',kind='symlink')
    with pytest.raises(OSError):m.read_regular(host,'link',parent.fd,gate,64)
    with pytest.raises(FileNotFoundError):m.read_regular(host,'absent',parent.fd,gate,64)
    assert len(host.fds)==1,'the file descriptor is closed in every case'

@pytest.mark.parametrize('change',[lambda node:node.content.extend(b'x'),lambda node:setattr(node,'mtime',node.mtime+1),lambda node:setattr(node,'ctime',node.ctime+1),
                                   lambda node:setattr(node,'ino',node.ino+1),lambda node:setattr(node,'content',node.content[:-1])])
def test_read_regular_refuses_a_file_that_changes_while_it_is_read(change):
    m=M();host=host_of(m);parent=pinned(m,host,hostemu.DEPLOY);node=host.tree.get(hostemu.DEPLOY+'/.deploy-version')
    def hook(host,name,detail,calls):
        if name=='read' and not getattr(host,'changed',False):host.changed=True;change(node)
    host.hook=hook;assert refusal(lambda:m.read_regular(host,'.deploy-version',parent.fd,gate,64))=='FILE_CHANGED_DURING_READ'

def test_boot_identifier_is_hashed_and_its_shape_is_required():
    m=M();host=host_of(m);assert m.boot_id_sha256(host,gate)==f.BOOT_SHA and host.fds=={}
    node=host.tree.get('/proc/sys/kernel/random/boot_id')
    node.content=bytearray(hostemu.BOOT.strip());assert m.boot_id_sha256(host,gate)==f.BOOT_SHA,'with or without the newline'
    for bad in (b'',b'not-a-uuid\n',hostemu.BOOT.upper(),hostemu.BOOT+b'x',b'0'*36+b'\n'):
        node.content=bytearray(bad);assert refusal(lambda:m.boot_id_sha256(host,gate))=='BOOT_ID_INVALID'
    node.content=bytearray(b'1f8fad5b-d9cb-469f-a165-70867728950e\n');assert m.boot_id_sha256(host,gate)!=f.BOOT_SHA

def test_documents_and_small_helpers():
    m=M()
    assert m.clean_path('/mnt/day-d-data/x') and not any(m.clean_path(value) for value in ('relative','/a//b','/a/../b','/a/./b','/a b','/'+'x/'*17+'y',None,'/a/'))
    assert m.inside('/a/b','/a') and m.inside('/a','/a') and not m.inside('/ab','/a') and m.inside('/a','/')
    assert m.prefixes('/a/b')==['/','/a','/a/b'] and m.hexpin('a'*64) and not m.hexpin('0'*64) and not m.hexpin('A'*64) and not m.hexpin(None)
    assert m.integer(0) and not m.integer(True) and not m.integer(-1) and m.integer(5,1,5) and not m.integer(6,1,5) and not m.integer(1.0)
    assert m.combined([{'status':'COMPLETE'},{'status':'COMPLETE'}])=='COMPLETE' and m.combined([{'status':'COMPLETE'},{'status':'UNAVAILABLE'}])=='PARTIAL'
    assert m.combined([{'status':'UNAVAILABLE'}])=='UNAVAILABLE' and m.combined([])=='PARTIAL'
    assert m.safe(OSError(13,'x'))=={'status':'UNAVAILABLE','code':'OS_ERROR','errno':13} and m.safe(KeyError('secret text'))=={'status':'UNAVAILABLE','code':'OBSERVATION_FAILED'}
    assert m.safe(m.Refused('lower case is not a code'))=={'status':'UNAVAILABLE','code':'OBSERVATION_FAILED'} and m.code_of(m.Refused('A_CODE'),'X')=='A_CODE'
    assert m.code_of(ValueError('A_CODE'),'FALLBACK')=='FALLBACK' and m.code_of(m.Refused('raw text of an error'),'FALLBACK')=='FALLBACK'
    assert m.strict(b'{"a":1}')=={'a':1} and refusal(lambda:m.strict(b'x'*10,limit=5))=='DOCUMENT_SIZE' and m.strict(b'{"a":"'+b'x'*70000+b'"}',limit=80000)['a']=='x'*70000
    clock=iter([m.datetime(2026,10,5,8,tzinfo=m.timezone.utc)]);begun=m.datetime(2026,10,5,7,59,58,tzinfo=m.timezone.utc)
    assert m.timing(begun,10.0,lambda:next(clock),lambda:12.5)=={'utc_start':'2026-10-05T07:59:58+00:00','utc_end':'2026-10-05T08:00:00+00:00','monotonic_elapsed_ms':2500}
    def broken():raise OSError(5,'clock')
    assert m.timing(begun,10.0,broken,lambda:12.5) is None
