"""K10: guards of the creating calls and of their proofs (the sealed core's files and parents parts, as this operation
reaches them) that K10's first suite did not pin. A reviewer's mutants on the assembled bytes survived it (review of
2026-10-02: A07, A08, W04, F02, F04, F06, F10 and the core's F13; then F07, F09, F11, F12, the core's T08 here).
On the emulated host only: no SSH, no host, no credential. Two of the states below (a descriptor of an exclusive
creation that is not a regular file; a held directory that stops being one) are states no kernel produces: they are
here so that the check cannot be removed unnoticed, and they say so."""
import errno
import os

import pytest

import family as f
import hostemu
import k10

BASE,DATA,NAME=k10.BASE,k10.DATA,k10.NAME

@pytest.mark.parametrize('call',['mkdir','create','link','unlink'])
@pytest.mark.parametrize('kind',[MemoryError,RuntimeError,KeyboardInterrupt])
def test_a_creating_call_that_took_effect_and_then_raised_something_else_is_never_a_refusal(call,kind):
    docs,host=k10.case();original=getattr(host,call)
    def after(*args,**kwargs):
        original(*args,**kwargs);raise kind('after the effect')
    setattr(host,call,after);receipt=docs.run(host)
    assert receipt['status']==docs.k.m.PARTIAL_STATUS and receipt['code']=='RUN_ESCAPED_STATE_UNKNOWN' and receipt['phase_reached']=='ESCAPED',receipt
    assert receipt['mutating_calls']['uncertain']==1 and host.tree.get(BASE) is not None

def test_owner_alone_of_what_the_kernel_created_is_judged():
    docs,host=k10.case();host.creator=(1000,0);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==(docs.k.m.PARTIAL_STATUS,'CREATED_METADATA_MISMATCH') and receipt['directories'][0]['state']=='CREATED_METADATA_MISMATCH'
    assert host.tree.get(BASE).children=={} and [e[0] for e in host.mutating()]==['mkdir']
    docs,host=k10.case()
    def hook(host,name,detail,calls):
        if name=='create':host.creator=(1000,0)
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==(docs.k.m.PARTIAL_STATUS,'CREATED_METADATA_MISMATCH') and receipt['ledger'][0]['state']=='NOT_CREATED'
    assert host.tree.get(BASE).children=={},'withdrawn before the final name exists'

def test_a_temporary_that_grew_between_the_write_and_its_proof_never_gets_the_final_name():
    docs,host=k10.case();temporary=BASE+'/.hostops-%s-0.partial'%docs.go16()
    def hook(host,name,detail,calls):
        if name=='fsync' and detail[0]==temporary:host.tree.get(temporary).content.extend(b'x')
    host.hook=hook;receipt=docs.run(host)
    assert receipt['status']==docs.k.m.PARTIAL_STATUS and receipt['code']=='CREATED_METADATA_MISMATCH' and NAME not in host.tree.get(BASE).children

def test_every_read_open_of_the_data_volume_is_noatime_and_the_installed_file_is_read_noatime():
    docs,host=k10.case();receipt=docs.run(host);assert receipt['status']==docs.k.m.COMPLETE_STATUS
    opens=[e for e in host.log if e[0]=='open' and (e[1]==DATA or e[1].startswith(DATA+'/'))]
    assert opens and all(e[2]&hostemu.NOATIME for e in opens),[e for e in opens if not e[2]&hostemu.NOATIME]
    assert [e for e in opens if e[1]==BASE+'/'+NAME]

def test_mode_or_owner_of_the_created_directory_changed_later_is_never_complete():
    for change in (lambda n:setattr(n,'mode',0o755),lambda n:setattr(n,'uid',1000),lambda n:setattr(n,'gid',1000)):
        docs,host=k10.case()
        def hook(host,name,detail,calls,change=change):
            if name=='link':change(host.tree.get(BASE))
        host.hook=hook;receipt=docs.run(host)
        assert receipt['status']==docs.k.m.PARTIAL_STATUS and receipt['installed'] is None and receipt['code'] in ('READBACK_MISMATCH','PARENT_REPLACED')

def test_created_directory_with_another_mode_is_left_labelled_and_no_file_is_written():
    for mode in (0o750,0o755,0o600,0o2700):
        docs,host=k10.case();original=host.mkdir
        def mkdir(name,m,dir_fd,mode=mode):
            original(name,m,dir_fd);host.tree.get(BASE).mode=mode
        host.mkdir=mkdir;receipt=docs.run(host)
        assert (receipt['status'],receipt['code'])==(docs.k.m.PARTIAL_STATUS,'CREATED_METADATA_MISMATCH'),mode
        assert host.tree.get(BASE).children=={} and receipt['ledger'][0]['state']=='NOT_ATTEMPTED'

def test_directory_whose_mode_or_owner_changed_before_the_link_never_receives_the_final_name():
    for change in (lambda n:setattr(n,'mode',0o755),lambda n:setattr(n,'uid',1000),lambda n:setattr(n,'gid',1000)):
        docs,host=k10.case()
        def hook(host,name,detail,calls,change=change):
            if name=='write':change(host.tree.get(BASE))
        host.hook=hook;receipt=docs.run(host)
        assert (receipt['status'],receipt['code'])==(docs.k.m.PARTIAL_STATUS,'PARENT_REPLACED') and receipt['ledger'][0]['state']=='TEMPORARY_ONLY'
        assert NAME not in host.tree.get(BASE).children and 'link' not in [e[0] for e in host.log]


# ---------------------------------------------------------------- what the reviewer's list named equivalent and is not
def test_a_refusal_raised_inside_a_creating_call_after_its_effect_is_never_reported_as_nothing_changed():
    """The core's Effects.clean() counts a call that was issued and never settled. A creating call that took effect and
    then raised a Refused is caught by the files part as a refusal of the gate; only the count of uncertain calls keeps
    the run from being reported REFUSED_NOTHING_CHANGED over a directory that exists."""
    docs,host=k10.case();m=docs.k.m;original=host.mkdir
    def after(*args,**kwargs):
        original(*args,**kwargs);raise m.Refused('GO_EXPIRED')
    host.mkdir=after;receipt=docs.run(host)
    assert receipt['status']==m.PARTIAL_STATUS and receipt['outcome']=='PARTIAL_REQUIRES_RECONCILIATION' and receipt['installed'] is None,receipt
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':0,'uncertain':1} and host.tree.get(BASE) is not None

def test_an_expiry_while_the_file_is_written_touches_nothing_more_and_a_clock_that_recovers_does_not_withdraw_the_temporary():
    """DESIGN.md 3.3: on GO_EXPIRED or CLOCK_REVERSED before the link the temporary stays, labelled TEMPORARY_ONLY. The
    withdrawal is for failures of the kernel only: after a refusal of the gate nothing is looked at and nothing is
    removed, even when the next look at the clock would pass again (a clock that stepped back once)."""
    for code,recovers in (('GO_EXPIRED',False),('CLOCK_REVERSED',True)):
        docs,host=k10.case();m=docs.k.m;plan,real=docs.authenticate();temporary=BASE+'/.hostops-%s-0.partial'%docs.go16();fired=[0]
        def gate(code=code,recovers=recovers):
            created=any(entry[0]=='create' for entry in host.log)
            if created and (fired[0]==0 or not recovers):
                fired[0]+=1;raise m.Refused(code)
            return real()
        receipt=docs.perform(host,gate=gate);row=receipt['ledger'][0]
        assert (receipt['status'],receipt['code'])==(m.PARTIAL_STATUS,code) and fired[0]>=1,(receipt['status'],receipt['code'])
        assert (row['state'],row['code'],row['temporary_removed'],row['temporary_removal_code'],row['bytes'])==('TEMPORARY_ONLY',code,False,None,None),row
        after=[entry for entry in host.log[[entry[0] for entry in host.log].index('create')+1:]]
        assert after==[] and sorted(host.tree.get(BASE).children)==[temporary.rsplit('/',1)[1]],'no host call follows the refusal of the gate'
        assert receipt['mutating_calls']=={'issued':2,'succeeded':2,'failed_nothing_changed':0,'uncertain':0} and receipt['objects_left_by_this_run']==2

def test_a_short_read_of_the_installed_file_is_reported_as_a_file_that_changed_while_read():
    """The readback compares the number of bytes read with the size of both fstat calls before it compares the bytes."""
    docs,host=k10.case();m=docs.k.m;original=host.read
    def read(fd,size):
        block=original(fd,size);return block[:-1] if host.path_of(fd)==BASE+'/'+NAME and block else block
    host.read=read;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==(m.PARTIAL_STATUS,'FILE_CHANGED_DURING_READ') and receipt['ledger'][0]['state']=='INSTALLED_DURABLE' and receipt['installed'] is None

def test_states_no_kernel_produces_still_stop_the_run_a_created_descriptor_that_is_not_a_regular_file_and_a_directory_that_is_no_longer_one():
    docs,host=k10.case();m=docs.k.m;temporary=BASE+'/.hostops-%s-0.partial'%docs.go16()
    def hook(host,name,detail,calls):
        if name=='fsync' and detail[0]==temporary:host.tree.get(temporary).kind='fifo'
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==(m.PARTIAL_STATUS,'CREATED_METADATA_MISMATCH') and receipt['ledger'][0]['state']=='NOT_CREATED'
    assert host.tree.get(BASE).children=={} and 'link' not in [entry[0] for entry in host.log],'what is not a regular file never gets the final name'
    docs,host=k10.case()
    def hook(host,name,detail,calls):
        if name=='unlink':host.tree.get(BASE).kind='fifo'
    host.hook=hook;receipt=docs.run(host)
    assert receipt['status']==m.PARTIAL_STATUS and receipt['installed'] is None and receipt['readback'] is None and receipt['code']=='READBACK_MISMATCH',receipt['code']
