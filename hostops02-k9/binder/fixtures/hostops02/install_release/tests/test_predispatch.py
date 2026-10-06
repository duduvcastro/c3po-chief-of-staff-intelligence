"""The Monday gate of K10: binding/predispatch.py reads the snapshot M0 and says whether the host would refuse M1.

The contract had no such gate (review of 2026-10-02): the binding checks were all "before the owner is asked to
sign", and on Monday the request would have been dispatched into a refusal that M0 had shown 27 minutes earlier, which
by the signed order ends the epoch. Each test below is one such state: the tool answers DO_NOT_DISPATCH and names the
check, and K10 run on the same state answers the refusal the check predicts.

M0's receipt is not modelled here: fixtures/M0_RECEIPT.W1_EMULATION.json was produced by the W1 source itself on the
emulated host of its own test file (tests/make_m0_fixture.py); a test changes one value of it and seals it again.
The tool is called in this process with a fixed clock; the command line (which has no clock option) is run once."""
import copy
from datetime import datetime,timedelta,timezone
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

import family as f
import hostemu
import k10

TOOL=k10.DIRECTORY/'binding'/'predispatch.py'
FIXTURES=k10.HERE/'fixtures'
M0_REQUEST=(FIXTURES/'M0_REQUEST.W1_EMULATION.json').read_bytes()
M0_RECEIPT=(FIXTURES/'M0_RECEIPT.W1_EMULATION.json').read_bytes()
RECORD=json.loads((FIXTURES/'M0_FIXTURE.W1_EMULATION.json').read_bytes())
START=datetime(2026,10,5,8,26,tzinfo=timezone.utc)                    # M1: 05:26 to 05:41 BRT
SPARE=datetime(2026,10,5,8,42,tzinfo=timezone.utc)                    # M1': 05:42 to 05:57 BRT
M0_END=datetime(2026,10,5,8,0,tzinfo=timezone.utc)
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
PRECHECK='GO_READONLY_HOSTOPS_PRECHECK_01'

def tool():
    spec=importlib.util.spec_from_file_location('_k10_predispatch',TOOL);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def seal(receipt):
    body=dict(receipt);body.pop('metadata_sha256',None);return dict(body,metadata_sha256=f.sha(f.canonical(body)))
def line(receipt):return f.canonical(receipt)+b'\n'

class Case:
    """One Monday: the bound K10 request, the evidence it names, M0's request, receipt and exit record, as files."""
    def __init__(self,directory,start=START):
        self.directory=Path(str(directory));self.k=k10.K();self.m0=json.loads(M0_RECEIPT);self.m0_request=json.loads(M0_REQUEST)
        self.evidence=seal({'schema':'READONLY_HOSTOPS_PRECHECK_RECEIPT_V1','operation':PRECHECK,'status':'METADATA_ONLY_REQUIRES_REVIEW',
                            'observed_at':'2026-10-04T12:10:00+00:00','items':{'boot':{'status':'COMPLETE','boot_id_sha256':f.BOOT_SHA}}})
        rows=[{'path':row['path'],'device':row['device'],'inode':row['inode'],'uid':row['uid'],'gid':row['gid'],'mode':int(row['mode_octal'],8)}
              for row in self.m0['observation']['sections']['data_volume']['ancestors']]
        self.docs=f.Docs(self.k,{'parent':rows,'release':k10.release_member(),'evidence_boot_id_sha256':f.BOOT_SHA},now=start,minutes=15,
                         evidence=[{'role':'S1_PRECHECK','operation':PRECHECK,'receipt_sha256':self.evidence['metadata_sha256']}])
        self.exit={'status':'KNOWN_COMPLETE','finished_at':(M0_END+timedelta(seconds=2)).isoformat()};self.resealed=True
    @property
    def sections(self):return self.m0['observation']['sections']
    def files(self):
        receipt=line(seal(self.m0) if self.resealed else self.m0);request=f.canonical(self.m0_request)
        if self.resealed and request!=M0_REQUEST:
            self.m0['request_sha256']=f.sha(request);receipt=line(seal(self.m0))
        record=dict({'stdout_sha256':f.sha(receipt),'request_sha256':f.sha(request)},**self.exit);out={}
        for name,raw in (('request',self.docs.raw()[0]),('evidence',line(self.evidence)),('m0-request',request),('m0-receipt',receipt),('m0-exit',f.canonical(record))):
            path=self.directory/(name+'.json');path.write_bytes(raw);out[name]=str(path)
        return out
    def run(self,now,step='prepare',role='primary',extra=()):
        files=self.files();arguments=['--step',step,'--role',role]
        for name in ('request','evidence','m0-request','m0-receipt','m0-exit'):arguments+=['--'+name,files[name]]
        out=io.StringIO();code=tool().main(arguments+list(extra),clock=lambda:now,out=out)
        text=out.getvalue();return code,(json.loads(text) if text else None),text
PREPARE=START-timedelta(minutes=6)                                   # 05:20 BRT: after M0, before the window opens
RESUME=START+timedelta(seconds=150)

def allowed(case,**options):
    code,result,text=case.run(options.pop('now',PREPARE),**options)
    assert code==0 and result['decision']=='DISPATCH_ALLOWED' and result['failed']==[] and all(row['ok'] is True for row in result['checks']),result['failed']
    return result,text
def denied(case,*names,**options):
    code,result,text=case.run(options.pop('now',PREPARE),**options)
    assert code==1 and result['decision']=='DO_NOT_DISPATCH' and result['failed']==list(names),(names,result['failed'])
    return result

def test_fixture_is_the_receipt_the_w1_bytes_emit_and_k10_completes_on_the_host_it_describes(tmp_path):
    assert f.sha(M0_RECEIPT)==RECORD['receipt_sha256'] and f.sha(M0_REQUEST)==RECORD['request_sha256'] and RECORD['every_value_is_synthetic'] is True
    receipt=json.loads(M0_RECEIPT);assert f.sealed(receipt) and receipt['schema']=='READONLY_W1PREFLIGHT01_RECEIPT_V1' and receipt['request_sha256']==f.sha(M0_REQUEST)
    assert json.loads(M0_REQUEST)['collection']['candidates']['release_directories']==[k10.LEAF]
    case=Case(tmp_path);case.docs.authenticate()                      # the request the tool is given is one the source accepts
    assert tool().M0_PAYLOAD_SHA256==RECORD['w1_source_sha256']==receipt['payload_sha256'],'the tool reads the receipt of the bytes the fixture was produced by'

def test_a_clean_snapshot_allows_the_prepare_and_the_resume_and_prints_no_row_of_the_host(tmp_path):
    case=Case(tmp_path);result,text=allowed(case)
    assert result['schema']=='HOSTOPS02_INSTALL_RELEASE_PREDISPATCH_V1' and result['payload_sha256']==f.sha(case.k.source) and (result['step'],result['role'])==('prepare','primary')
    assert result['request_sha256']==f.sha(case.docs.raw()[0]) and len(result['not_covered'])>=5 and result['evaluated_at']==PREPARE.isoformat()
    ids=[row['id'] for row in result['checks']]
    assert ids==['REQUEST_IS_OF_THIS_PAYLOAD','PLAN_IS_ONE_THE_SOURCE_ACCEPTS','EVIDENCE_IS_THE_PRECHECK_RECEIPT_THE_REQUEST_NAMES','M0_RECEIPT_IS_SEALED_AND_OF_THE_M0_REQUEST',
                 'M0_IS_OF_THE_W1_BYTES_THIS_TOOL_READS','M0_EXIT_IS_OF_THAT_RECEIPT','M0_SECTIONS_COMPLETE','M0_IS_OF_THE_SAME_DAY_AND_NOT_OLDER_THAN_AN_HOUR','HOST_CLOCK_AGREES_WITH_THIS_MACHINE',
                 'TIME_LEFT_TO_PREPARE_PUBLISH_AND_RESUME','EXECUTOR_IS_ROOT','SAME_BOOT_AS_THE_EVIDENCE','PARENT_ROWS_ARE_THE_SIGNED_ROWS','VOLUME_IS_MOUNTED_READ_WRITE',
                 'FILESYSTEM_HAS_HARD_LINKS','PIN_IS_A_REGULAR_FILE_OF_ROOT_ROOT','DESTINATION_IS_ABSENT_BY_ITS_EXACT_NAME','FREE_BYTES_FAR_ABOVE_THE_FLOOR','FREE_INODES_FAR_ABOVE_TWO']
    # every refusal code of K10's host precheck that state can cause is predicted by some check
    predicted=' '.join(row['predicts'] for row in result['checks'])
    for code in ('EXECUTOR_IDENTITY','EVIDENCE_FROM_EARLIER_BOOT','PARENT_IDENTITY_MISMATCH','MAINTENANCE_PIN_ABSENT','MAINTENANCE_PIN_NOT_A_REGULAR_FILE','MAINTENANCE_PIN_NOT_ROOT_OWNED',
                 'DESTINATION_PRESENT','DATA_VOLUME_FREE_SPACE_BELOW_FLOOR','FILESYSTEM_READ_ONLY','FILESYSTEM_FULL','OUTSIDE_GO_WINDOW'):assert code in predicted,code
    # nothing of the host's rows is printed: no device, no inode, no size
    volume=case.sections['data_volume']
    for value in [row[key] for row in volume['ancestors'] for key in ('device','inode')]+[volume['filesystem'][key] for key in ('f_bavail','f_blocks','f_favail','bytes_total')]:
        if value>99:assert str(value) not in text,value
    result,_=allowed(case,now=RESUME,step='resume')
    assert [row['id'] for row in result['checks']][9:11]==['RESUME_NOT_BEFORE_NOT_BEFORE_PLUS_120_SECONDS','RESUME_BEFORE_THE_LATEST_START']

def k10_refusal(change):
    """What K10 itself answers on the emulated host in the state a snapshot would have shown."""
    docs,host=k10.case();change(host);receipt=docs.run(host);assert receipt['status']=='REFUSED' and receipt['mutating_calls']['issued']==0;return receipt['code']

def test_every_state_that_k10_would_refuse_on_the_host_is_a_do_not_dispatch(tmp_path):
    """One directory per case; the code K10 answers in the same state is taken from K10 itself where the emulation has it."""
    count=[0]
    def case():
        count[0]+=1;directory=tmp_path/str(count[0]);directory.mkdir();return Case(directory)
    def state(change,*names):
        one=case();change(one);return denied(one,*names)
    # the executor
    state(lambda c:c.m0['observation'].update(actor={'uid':1000,'gid':1000}),'EXECUTOR_IS_ROOT')
    state(lambda c:c.m0['observation'].update(actor={'uid':0,'gid':1000}),'EXECUTOR_IS_ROOT')
    assert k10_refusal(lambda host:setattr(host,'actor',(0,1000)))=='EXECUTOR_IDENTITY'
    # a reboot after the evidence: M0's boot began after the evidence was taken, or the margin is not there
    evidence_at=datetime.fromisoformat('2026-10-04T12:10:00+00:00').timestamp()
    for epoch in (int(M0_END.timestamp())-600,int(evidence_at),int(evidence_at)-59):
        state(lambda c,epoch=epoch:c.sections['runtime']['boot'].update(boot_epoch_utc=epoch),'SAME_BOOT_AS_THE_EVIDENCE')
    one=case();one.sections['runtime']['boot'].update(boot_epoch_utc=int(evidence_at)-60);allowed(one)
    state(lambda c:c.sections['runtime']['boot'].update(boot_epoch_utc=float(evidence_at)-600.5),'SAME_BOOT_AS_THE_EVIDENCE')
    assert k10_refusal(lambda host:host.tree.get('/proc/sys/kernel/random/boot_id').content.__setitem__(slice(0,1),b'1'))=='EVIDENCE_FROM_EARLIER_BOOT'
    # the three parents: any value of any row, an unmounted volume, another source
    rows=lambda c:c.sections['data_volume']['ancestors']
    for index,key,value in ((0,'inode',9),(1,'inode',9),(2,'inode',9),(2,'device',66305),(1,'device',7),(2,'uid',0),(2,'gid',0),(1,'mode_octal','0775'),(2,'mode_octal','2755'),
                            (2,'type','symlink'),(1,'path','/media')):
        state(lambda c,index=index,key=key,value=value:rows(c)[index].update({key:value}),'PARENT_ROWS_ARE_THE_SIGNED_ROWS')
    state(lambda c:rows(c).pop(),'PARENT_ROWS_ARE_THE_SIGNED_ROWS')
    state(lambda c:c.sections['data_volume'].update(source='/var/lib/docker/volumes/c3po_c3po_day_d_data/_data'),'PARENT_ROWS_ARE_THE_SIGNED_ROWS')
    assert k10_refusal(lambda host:setattr(host.tree.get('/mnt/day-d-data'),'ino',99999))=='PARENT_IDENTITY_MISMATCH'
    # read-only, or not the mount it was
    state(lambda c:c.sections['data_volume']['filesystem'].update(read_only=True),'VOLUME_IS_MOUNTED_READ_WRITE')
    for key,value in (('read_write',False),('mount_point_is_the_path',False),('device_equals_the_directory_device',False),('mount_point','/mnt')):
        state(lambda c,key=key,value=value:c.sections['data_volume']['mount'].update({key:value}),'VOLUME_IS_MOUNTED_READ_WRITE')
    for value in ('vfat','OTHER','overlay','tmpfs',None):
        state(lambda c,value=value:c.sections['data_volume']['mount'].update(filesystem_type=value),'FILESYSTEM_HAS_HARD_LINKS')
    # the pin: absent, not a regular file, another owner, another group (the group is what the earlier reads did not judge)
    pin=lambda c:c.sections['data_volume']['root']['pin']
    state(lambda c:c.sections['data_volume']['root'].update(pin={'exists':False}),'PIN_IS_A_REGULAR_FILE_OF_ROOT_ROOT')
    state(lambda c:pin(c).update(exists=False),'PIN_IS_A_REGULAR_FILE_OF_ROOT_ROOT')
    for key,value in (('type','symlink'),('type','dir'),('uid',1000),('gid',1000),('gid',20)):
        state(lambda c,key=key,value=value:pin(c).update({key:value}),'PIN_IS_A_REGULAR_FILE_OF_ROOT_ROOT')
    assert k10_refusal(lambda host:setattr(host.tree.get(k10.PIN),'gid',1000))=='MAINTENANCE_PIN_NOT_ROOT_OWNED'
    assert k10_refusal(lambda host:host.tree.remove(k10.PIN))=='MAINTENANCE_PIN_ABSENT'
    # the destination, by its exact name
    candidates=lambda c:c.sections['release_directories']['candidates']
    state(lambda c:candidates(c)[0].update(exists=True,type='dir',uid=0,gid=0,mode_octal='0700'),'DESTINATION_IS_ABSENT_BY_ITS_EXACT_NAME')
    state(lambda c:candidates(c).__setitem__(0,{'status':'UNAVAILABLE','code':'OS_ERROR','candidate_index':0}),'DESTINATION_IS_ABSENT_BY_ITS_EXACT_NAME')
    def unanswered(c):
        candidates(c).__setitem__(0,{'status':'UNAVAILABLE','code':'OS_ERROR','candidate_index':0});c.sections['release_directories'].update(status='PARTIAL')
    state(unanswered,'M0_SECTIONS_COMPLETE','DESTINATION_IS_ABSENT_BY_ITS_EXACT_NAME')
    state(lambda c:candidates(c)[0].update(candidate_index=1),'DESTINATION_IS_ABSENT_BY_ITS_EXACT_NAME')
    state(lambda c:c.m0_request['collection']['candidates'].update(release_directories=['r2d2-v2-release-20260928']),'DESTINATION_IS_ABSENT_BY_ITS_EXACT_NAME')
    state(lambda c:c.m0_request['collection']['candidates'].update(release_directories=[]),'DESTINATION_IS_ABSENT_BY_ITS_EXACT_NAME')
    assert k10_refusal(lambda host:host.tree.add(k10.BASE,dev=hostemu.DATA_DEVICE,mode=0o700))=='DESTINATION_PRESENT'
    # space: bytes and inodes
    floor=16*1048576//4096
    state(lambda c:c.sections['data_volume']['filesystem'].update(f_bavail=floor-1),'FREE_BYTES_FAR_ABOVE_THE_FLOOR')
    one=case();one.sections['data_volume']['filesystem'].update(f_bavail=floor);allowed(one)
    state(lambda c:c.sections['data_volume']['filesystem'].update(f_favail=1023),'FREE_INODES_FAR_ABOVE_TWO')
    state(lambda c:c.sections['data_volume']['filesystem'].update(f_favail=0),'FREE_INODES_FAR_ABOVE_TWO')
    one=case();one.sections['data_volume']['filesystem'].update(f_favail=1024);allowed(one)
    assert k10_refusal(lambda host:setattr(host.vfs[hostemu.DATA_DEVICE],'f_bavail',255))=='DATA_VOLUME_FREE_SPACE_BELOW_FLOOR'

def test_a_snapshot_that_cannot_answer_is_a_do_not_dispatch_never_a_guess(tmp_path):
    count=[0]
    def case():
        count[0]+=1;directory=tmp_path/str(count[0]);directory.mkdir();return Case(directory)
    # a receipt reduced for size: every section is a status only
    one=case();one.m0['observation']['sections']={name:{'status':section.get('status'),'reduced_for_size':True} for name,section in one.sections.items()}
    result=denied(one,'M0_SECTIONS_COMPLETE','M0_IS_OF_THE_SAME_DAY_AND_NOT_OLDER_THAN_AN_HOUR','HOST_CLOCK_AGREES_WITH_THIS_MACHINE','SAME_BOOT_AS_THE_EVIDENCE',
                  'PARENT_ROWS_ARE_THE_SIGNED_ROWS','VOLUME_IS_MOUNTED_READ_WRITE','FILESYSTEM_HAS_HARD_LINKS','PIN_IS_A_REGULAR_FILE_OF_ROOT_ROOT',
                  'DESTINATION_IS_ABSENT_BY_ITS_EXACT_NAME','FREE_BYTES_FAR_ABOVE_THE_FLOOR','FREE_INODES_FAR_ABOVE_TWO')
    # one section that did not complete
    one=case();one.sections['data_volume'].update(status='PARTIAL');denied(one,'M0_SECTIONS_COMPLETE')
    one=case();one.sections['data_volume']['root'].update(status='PARTIAL',issues=['CENSUS_CAPPED']);denied(one,'M0_SECTIONS_COMPLETE')
    one=case();one.sections['runtime']['boot']={'status':'UNAVAILABLE','code':'RUNTIME_FIELD_INVALID'};denied(one,'M0_SECTIONS_COMPLETE','SAME_BOOT_AS_THE_EVIDENCE')
    # a receipt that is not the sealed one, of another request, of another host, or whose exit record is of another output
    one=case();one.resealed=False;one.sections['data_volume']['root']['pin'].update(gid=0,uid=0,mode_octal='0644');denied(one,'M0_RECEIPT_IS_SEALED_AND_OF_THE_M0_REQUEST')
    one=case();one.m0['request_sha256']='a'*64;denied(one,'M0_RECEIPT_IS_SEALED_AND_OF_THE_M0_REQUEST')
    one=case();one.m0['host_binding_sha256']='2'*64;denied(one,'M0_RECEIPT_IS_SEALED_AND_OF_THE_M0_REQUEST')
    one=case();one.m0['schema']='READONLY_SUPERVISOR_HOSTFACTS_RECEIPT_V1';denied(one,'M0_RECEIPT_IS_SEALED_AND_OF_THE_M0_REQUEST')
    one=case();one.m0['payload_sha256']='e'*64;denied(one,'M0_IS_OF_THE_W1_BYTES_THIS_TOOL_READS')       # a snapshot taken with other bytes than the ones this tool reads
    for change in ({'stdout_sha256':'b'*64},{'request_sha256':'b'*64},{'status':'UNCERTAIN'},{'status':'KNOWN_REFUSAL'}):
        one=case();one.exit.update(change);denied(one,'M0_EXIT_IS_OF_THAT_RECEIPT')
    one=case();one.exit.update(status='KNOWN_PARTIAL');allowed(one)       # a partial snapshot whose needed sections are complete still answers

def test_clock_of_the_host_and_of_this_machine_and_the_age_of_the_snapshot(tmp_path):
    count=[0]
    def case(start=START):
        count[0]+=1;directory=tmp_path/str(count[0]);directory.mkdir();return Case(directory,start)
    # the host's clock against this machine's, measured at the end of M0: 30 s either way
    for seconds,names in ((30,()),(-30,()),(31,('HOST_CLOCK_AGREES_WITH_THIS_MACHINE',)),(-31,('HOST_CLOCK_AGREES_WITH_THIS_MACHINE',)),(3600,('HOST_CLOCK_AGREES_WITH_THIS_MACHINE',))):
        one=case();one.exit.update(finished_at=(M0_END+timedelta(seconds=seconds)).isoformat())
        if names:denied(one,*names)
        else:allowed(one)
    one=case();one.exit.pop('finished_at');denied(one,'HOST_CLOCK_AGREES_WITH_THIS_MACHINE')
    # a snapshot older than an hour, of the day before, or "from the future"
    late=datetime(2026,10,5,8,50,tzinfo=timezone.utc)                # a window that is still open one hour after M0
    one=case(late);allowed(one,now=M0_END+timedelta(seconds=3600));one=case(late);denied(one,'M0_IS_OF_THE_SAME_DAY_AND_NOT_OLDER_THAN_AN_HOUR',now=M0_END+timedelta(seconds=3601))
    one=case();denied(one,'M0_IS_OF_THE_SAME_DAY_AND_NOT_OLDER_THAN_AN_HOUR',now=M0_END-timedelta(seconds=31))
    one=case();one.m0['observed_at']='2026-10-04T23:30:00+00:00';denied(one,'M0_IS_OF_THE_SAME_DAY_AND_NOT_OLDER_THAN_AN_HOUR')
    # the two steps: prepare while there is room for publication and the 120 s; resume from not_before + 120 s to 15 s before the latest start
    latest=START+timedelta(minutes=15)-timedelta(seconds=80)
    one=case();allowed(one,now=latest-timedelta(seconds=61));one=case();denied(one,'TIME_LEFT_TO_PREPARE_PUBLISH_AND_RESUME',now=latest-timedelta(seconds=60))
    one=case();denied(one,'RESUME_NOT_BEFORE_NOT_BEFORE_PLUS_120_SECONDS',now=START+timedelta(seconds=119),step='resume')
    one=case();allowed(one,now=START+timedelta(seconds=120),step='resume')
    one=case();denied(one,'RESUME_NOT_BEFORE_NOT_BEFORE_PLUS_120_SECONDS',now=START-timedelta(seconds=1),step='resume')
    one=case();allowed(one,now=latest-timedelta(seconds=16),step='resume');one=case();denied(one,'RESUME_BEFORE_THE_LATEST_START',now=latest-timedelta(seconds=15),step='resume')

def test_request_and_evidence_must_be_this_payloads_and_the_ones_the_request_names(tmp_path):
    count=[0]
    def case():
        count[0]+=1;directory=tmp_path/str(count[0]);directory.mkdir();return Case(directory)
    one=case();one.docs.request['payload_sha256']='a'*64;denied(one,'REQUEST_IS_OF_THIS_PAYLOAD')
    one=case();one.docs.request['status']='UNBOUND';denied(one,'REQUEST_IS_OF_THIS_PAYLOAD')
    one=case();one.docs.request['operation']='GO_WRITE_HOSTOPS02_ACTIVATE_01';denied(one,'REQUEST_IS_OF_THIS_PAYLOAD')
    one=case();one.docs.plan['parent'][2]['mode']=0o2755;denied(one,'PLAN_IS_ONE_THE_SOURCE_ACCEPTS','PARENT_ROWS_ARE_THE_SIGNED_ROWS')
    one=case();one.docs.plan['release']=k10.release_member(k10.altered(epoch='R2D2-V2-SHADOW-2026-09-28'));denied(one,'PLAN_IS_ONE_THE_SOURCE_ACCEPTS')
    # the host evidence the contract asks the request to name beside the precheck (the receipts of the creating calls of the
    # sibling family on this host) is accepted by the source and changes nothing here
    one=case();one.docs.request['evidence']+=[{'role':'HOST_PROOF_A3_PROVISION','operation':'GO_WRITE_SUPERVISOR_READER_PROVISION_01','receipt_sha256':'a'*64},
                                              {'role':'HOST_PROOF_B1_INSTALL_UNITS','operation':'GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01','receipt_sha256':'b'*64}]
    one.docs.chain();one.docs.authenticate();allowed(one)
    # the evidence: another receipt than the one named, another boot than the signed one, another operation, not sealed, a failed boot item
    one=case();one.docs.request['evidence'][0]['receipt_sha256']='c'*64;denied(one,'EVIDENCE_IS_THE_PRECHECK_RECEIPT_THE_REQUEST_NAMES')
    one=case();one.docs.plan['evidence_boot_id_sha256']='d'*64;denied(one,'EVIDENCE_IS_THE_PRECHECK_RECEIPT_THE_REQUEST_NAMES')
    one=case();one.evidence=seal(dict(one.evidence,operation='GO_READONLY_SUPERVISOR_READBACK_01'));one.docs.request['evidence'][0]['receipt_sha256']=one.evidence['metadata_sha256']
    denied(one,'EVIDENCE_IS_THE_PRECHECK_RECEIPT_THE_REQUEST_NAMES')
    one=case();one.evidence['observed_at']='2026-10-04T12:11:00+00:00';denied(one,'EVIDENCE_IS_THE_PRECHECK_RECEIPT_THE_REQUEST_NAMES')
    one=case();one.evidence=seal(dict(one.evidence,items={'boot':{'status':'UNAVAILABLE','code':'BOOT_ID_INVALID'}}));one.docs.request['evidence'][0]['receipt_sha256']=one.evidence['metadata_sha256']
    denied(one,'EVIDENCE_IS_THE_PRECHECK_RECEIPT_THE_REQUEST_NAMES')
    # an evidence receipt taken AFTER the snapshot proves nothing about the boot of the snapshot
    one=case();one.evidence=seal(dict(one.evidence,observed_at='2026-10-05T08:00:01+00:00'));one.docs.request['evidence'][0]['receipt_sha256']=one.evidence['metadata_sha256']
    denied(one,'SAME_BOOT_AS_THE_EVIDENCE')

def test_spare_is_allowed_only_while_the_primary_was_never_dispatched(tmp_path):
    """The claim of the dispatcher is keyed by the GO hash: two bound sets of the same payload have two claims, and
    nothing in the dispatcher stops the spare after the primary. This check does: the primary's claim must not exist."""
    def dispatcher(case,directory,start):
        dispatch=f.Dispatch(case.docs,directory);dispatch.config['latest_start']=(start+timedelta(minutes=15)-timedelta(seconds=80)).isoformat()
        return dispatch.save(rebind=False)
    primary_directory=tmp_path/'primary';primary_directory.mkdir();primary=Case(primary_directory);dispatch=dispatcher(primary,primary_directory,START)
    spare_directory=tmp_path/'spare';spare_directory.mkdir();spare=Case(spare_directory,SPARE)
    go=primary_directory/'GO.primary.json';go.write_bytes(primary.docs.raw()[2])
    extra=['--primary-go',str(go),'--claim-root',str(dispatch.root)];now=SPARE-timedelta(minutes=2)
    assert primary.docs.raw()[2]!=spare.docs.raw()[2] and dispatch.claims()==[]
    result,_=allowed(spare,now=now,role='spare',extra=extra);assert result['checks'][-1]=={'id':'PRIMARY_WAS_NEVER_DISPATCHED','predicts':'DESTINATION_PRESENT','ok':True}
    dispatch.prepare(clock=lambda:START+timedelta(seconds=30));assert [item.name for item in dispatch.claims()]==['.go-'+f.sha(primary.docs.raw()[2])+'.claim']
    denied(spare,'PRIMARY_WAS_NEVER_DISPATCHED',now=now,role='spare',extra=extra)
    # the spare's own GO given as "the primary's" would look for a claim that cannot exist: refused as such
    own=spare_directory/'GO.own.json';spare.docs.chain();own.write_bytes(spare.docs.raw()[2])
    denied(spare,'PRIMARY_WAS_NEVER_DISPATCHED',now=now,role='spare',extra=['--primary-go',str(own),'--claim-root',str(tmp_path/'spare')])
    other=spare_directory/'GO.other.json';other.write_bytes(f.canonical(dict(json.loads(primary.docs.raw()[2]),schema='WRITE_HOSTOPS02_ACTIVATE_GO_V1')))
    denied(spare,'PRIMARY_WAS_NEVER_DISPATCHED',now=now,role='spare',extra=['--primary-go',str(other),'--claim-root',str(dispatch.root)])
    # and what the dispatcher does without this check: the second set is prepared without any refusal
    second=dispatcher(spare,spare_directory,SPARE);assert second.prepare(clock=lambda:SPARE+timedelta(seconds=30))['status']=='AWAITING_PUBLICATION_NO_SPAWN'

def test_usage_and_unreadable_inputs_are_exit_2_and_the_command_line_has_no_clock_option(tmp_path):
    case=Case(tmp_path);files=case.files();module=tool()
    full=['--step','prepare','--role','primary']+[word for name in ('request','evidence','m0-request','m0-receipt','m0-exit') for word in ('--'+name,files[name])]
    def call(arguments):
        out=io.StringIO();return module.main(arguments,clock=lambda:PREPARE,out=out),out.getvalue()
    assert call(full)[0]==0
    for arguments in ([],full[:-2],full+['--now','2026-10-05T08:20:00+00:00'],full+['--step','resume'],['--step','later']+full[2:],['--step','prepare','--role','owner']+full[4:],
                      full+['--primary-go',files['request']],full+['--claim-root',str(tmp_path)],['--step','prepare','--role','spare']+full[4:],
                      ['--step','prepare','--role','spare']+full[4:]+['--primary-go',files['request']],full[:-1]):
        assert call(arguments)==(2,''),arguments
    for name,raw in (('m0-receipt',b'{not json'),('request',b''),('m0-exit',b'[1]'),('evidence',b'{"a":1,"a":2}')):
        saved=Path(files[name]).read_bytes();Path(files[name]).write_bytes(raw);assert call(full)==(2,''),name;Path(files[name]).write_bytes(saved)
    assert call(full[:-1]+[str(tmp_path/'absent.json')])==(2,'')
    assert call(['--step','prepare','--role','spare']+full[4:]+['--primary-go',files['request'],'--claim-root',str(tmp_path/'absent')])==(2,'')
    # the command line as the binder runs it: this machine's clock is not Monday's, so the three checks of time fail, and only they
    done=subprocess.run([sys.executable,'-B',str(TOOL)]+full,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
    result=json.loads(done.stdout);assert done.returncode==1 and done.stderr==b'' and done.stdout.count(b'\n')==1 and result['decision']=='DO_NOT_DISPATCH'
    if datetime.now(timezone.utc).date().isoformat()!='2026-10-05':
        assert set(result['failed'])<={'M0_IS_OF_THE_SAME_DAY_AND_NOT_OLDER_THAN_AN_HOUR','TIME_LEFT_TO_PREPARE_PUBLISH_AND_RESUME'} and result['failed']
    done=subprocess.run([sys.executable,'-B',str(TOOL)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
    assert done.returncode==2 and done.stdout==b'' and b'--m0-receipt' in done.stderr
