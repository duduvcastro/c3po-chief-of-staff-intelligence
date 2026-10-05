"""The findings of the two reviews of 2026-10-02 (lenses: the host, and purity and authentication) and the tests that
answer them. One block per finding that changed a byte of the operation part; the reviewers' own tests are taken over
where they applied (the grammar boundaries, the recreated container, the unknown that stays unknown, the expected hash).
Synthetic and local: no host, no docker, no credential.

  F1  a rehearsal is neutral for production: none of its docker commands runs under the directory of the unit
  F8  which directory is a journal root, and where a rehearsal creates, is decided by the code (the layout floor)
  F2  one of docker's own statuses after a verified catalog is a finding, not a burnt root
  F10 what the docker CLI left in its directory during the two reads has its own code
  F12 no descriptor is left when a held directory cannot be looked at
  F9  the regression gaps the reviewer's own mutants showed
  F13 the limit of "only a constant code leaves" (kept, and said)
"""
import copy
import errno
import importlib.util
import json
from datetime import timedelta

import pytest

import family as f
import hostemu
import k2a
import test_catalog_init as base

MODES=('REAL','REHEARSAL')
PARTIAL='PARTIAL_METADATA_REQUIRES_REVIEW'
fresh,node,names,refused,partial=base.fresh,base.node,base.names,base.refused,base.partial
def code(docs):return f.refusal(docs.authenticate)
def clone(docs):return f.Docs(docs.k,copy.deepcopy({key:docs.plan[key] for key in docs.k.m.PLAN_KEYS}),now=docs.now)
def refused_from_the_bytes(docs,expected):
    """Refused by authenticate() (what the dispatcher runs locally before any claim) and by run() before any host call."""
    assert code(docs)==expected,code(docs)
    receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED',expected,'AUTHENTICATION')
def writing_cli(host):
    """A docker CLI that leaves a file in the directory it is given as DOCKER_CONFIG, at every command (K2A-U2: what
    has never been observed on the host's client version, and what a rehearsal must find without touching the unit)."""
    original=host.docker.run
    def run(args,stdin=None,environment=None):
        given=(environment or {}).get('DOCKER_CONFIG')
        if given is not None and host.tree.get(given) is not None and 'config.json' not in host.tree.get(given).children:
            host.tree.add(given+'/config.json',kind='file',mode=0o600)
        return original(args,stdin,environment)
    host.docker.run=run


# ================================================================ F1: a rehearsal never uses the directory of the unit
def production_untouched(host,label):
    """What a rehearsal may never do, whatever it ends in: start a docker command under the directory of the unit, or
    write into that directory or into the real journal root, or create anything but its two throwaway directories."""
    assert all(entry['docker_config']==k2a.REHEARSAL_CONFIG for entry in host.commands),(label,'a docker command under another directory')
    assert all(environment.get('DOCKER_CONFIG')==k2a.REHEARSAL_CONFIG for environment in host.docker.environments),label
    assert k2a.CONFIG not in json.dumps([[entry['argv'],entry['variables']] for entry in host.commands]),(label,'the directory of the unit named in a command')
    assert names(host,k2a.CONFIG)==[] and names(host,k2a.JOURNAL)==[],(label,'production was written')
    assert {entry[1] for entry in host.log if entry[0]=='mkdir'}<={k2a.REHEARSAL_CONFIG,k2a.REHEARSAL_ROOT},label
    assert [entry for entry in host.log if entry[0] in ('create','write','link','unlink')]==[],label

def test_f1_no_docker_command_of_a_rehearsal_runs_under_the_directory_of_the_unit_whatever_the_run_ends_in():
    # a complete rehearsal
    m,docs,host=fresh('REHEARSAL');assert docs.run(host)['status']==m.COMPLETE_STATUS;production_untouched(host,'complete');total=host.calls
    assert len(host.commands)==4 and len(host.docker.environments)==4
    # every finding of the docker reads, every hostile answer of the container, every hostile state it leaves
    for index,(prepare,_) in enumerate(base.DOCKER_PRECHECK):
        m,docs,host=fresh('REHEARSAL');prepare(host);assert docs.run(host)['status']==PARTIAL;production_untouched(host,('read',index))
    for index,(behaviour,_) in enumerate(base.ANSWERS+base.STATES):
        m,docs,host=fresh('REHEARSAL');host.docker.on_run=base.then(behaviour);assert docs.run(host)['status']==PARTIAL;production_untouched(host,('container',index))
    for group in ('hang','hang_after','absent'):
        for words in (('image','inspect'),('ps','-a'),('run','--rm')):
            m,docs,host=fresh('REHEARSAL');getattr(host,group).add(words);docs.run(host);production_untouched(host,(group,words))
    # a failure or a death at every call the run makes on the host
    for kind in (OSError,RuntimeError,hostemu.Death):
        for index in range(1,total+1):
            m,docs,host=fresh('REHEARSAL')
            def hook(host,name,detail,calls,index=index,kind=kind):
                if calls==index:raise kind(errno.EIO,'injected') if kind is OSError else kind('injected')
            host.hook=hook;docs.run(host);production_untouched(host,(kind.__name__,index))

def test_f1_a_cli_that_writes_into_its_configuration_directory_is_found_by_the_rehearsal_in_a_directory_of_its_own():
    """The case the finding is about. With the earlier bytes the rehearsal would have left the file in
    /etc/c3po-bar/docker-cli, where nothing of either family removes it and where it refuses every later run."""
    m,docs,host=fresh('REHEARSAL');writing_cli(host);receipt=docs.run(host)
    partial(receipt,'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_THE_READS')
    assert receipt['precheck']['docker_config_entries']==0 and receipt['precheck']['docker_config_entries_after_the_reads']==1 and receipt['commands_started']['READ']==2
    assert names(host,k2a.REHEARSAL_CONFIG)==['config.json'] and node(host,k2a.REHEARSAL_ROOT) is None and host.container_runs()==[]
    production_untouched(host,'writing cli')
    # the unit's directory is still what operation 2 left: the real request is not refused for it (here with a CLI that behaves)
    k=docs.k;host.docker.run=type(host.docker).run.__get__(host.docker);real=f.Docs(k,k2a.real_fields(host));receipt=real.run(host)
    assert receipt['status']==m.COMPLETE_STATUS and receipt['precheck']['docker_config_entries']==0 and names(host,k2a.CONFIG)==[]
    # when the CLI leaves nothing during the reads and something during the run, the rehearsal says so as a finding beside a verified catalog
    m,docs,host=fresh('REHEARSAL');host.docker.on_run=base.then(lambda call,result:call.docker.host.tree.add(k2a.REHEARSAL_CONFIG+'/config.json',kind='file',mode=0o600) and None)
    receipt=docs.run(host);partial(receipt,'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_RUN','CATALOG_VERIFIED_WITH_FINDINGS');production_untouched(host,'after the run')
    assert receipt['docker_config']=={'path':k2a.REHEARSAL_CONFIG,'is_the_directory_of_the_unit':False,'entries_before':0,'entries_after':1,'code':None}

def test_f1_the_real_run_is_the_first_and_only_mode_that_gives_docker_the_directory_of_the_unit():
    m,docs,host=fresh('REAL');receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS
    assert [entry['docker_config'] for entry in host.commands]==[k2a.CONFIG]*4 and receipt['docker_config']['is_the_directory_of_the_unit'] is True
    assert receipt['effects']['container']['docker_config_variable']==k2a.CONFIG and receipt['effects']['docker_config']['given_to_docker'] is True
    assert receipt['effects']['rehearsal_docker_config'] is None and receipt['directories']==[] and node(host,k2a.REHEARSAL_CONFIG) is None
    m,docs,host=fresh('REHEARSAL');effects=docs.go['effects']
    assert effects['docker_config']['given_to_docker'] is False and effects['docker_config']['path']==k2a.CONFIG and effects['container']['docker_config_variable']==k2a.REHEARSAL_CONFIG
    assert effects['rehearsal_docker_config']['path']==k2a.REHEARSAL_CONFIG==effects['creates']['by_this_process'][0] and effects['creates']['by_this_process'][1]==k2a.REHEARSAL_ROOT

def test_f1_the_directory_a_rehearsal_gives_docker_follows_the_throwaway_name_and_two_rehearsals_never_share_one():
    m,docs,host=fresh('REHEARSAL')
    for name in ('c3po-bar-rehearsal-a','c3po-bar-rehearsal-a-docker-cli','c3po-bar-rehearsal-'+'z'*40):
        plan=dict(docs.plan,throwaway_name=name);m.validate_plan(plan)
        assert m.docker_config_path(plan)=='/var/lib/'+name+'.docker-cli'!=m.journal_path(plan)=='/var/lib/'+name
        assert m.text(m.docker_config_path(plan),m.COMMAND_VARIABLES['DOCKER_CONFIG']) and m.text(m.docker_config_path(plan)[9:],m.FILE_NAME)
    assert not m.text('c3po-bar-rehearsal-a.docker-cli',m.THROWAWAY_NAME),'no throwaway root can take the name of a configuration directory'
    # a second rehearsal under the same name is refused before anything is created, whichever of the two directories is left
    for left in (k2a.REHEARSAL_CONFIG,k2a.REHEARSAL_ROOT):
        m,docs,host=fresh('REHEARSAL');host.tree.add(left,mode=0o700);before=k2a.state_of(host);receipt=docs.run(host)
        refused(receipt,'DESTINATION_PRESENT');assert k2a.state_of(host)==before and host.commands==[]
        assert receipt['precheck']['throwaway']=={'exists':left==k2a.REHEARSAL_ROOT} and (left==k2a.REHEARSAL_ROOT or receipt['precheck']['throwaway_docker_config']=={'exists':True})


# ================================================================ F8: the layout floor
def test_f8_the_signed_path_is_not_all_the_code_knows_about_which_directory_is_a_journal_root():
    """The reviewer's two cases, which the earlier bytes accepted and completed. (a) REAL on the state root of the
    supervisor, or on the manifests directory. (b) A REHEARSAL whose parent is the true journal root and whose reference
    names another empty private directory: its throwaway would have been created INSIDE the true journal root."""
    k,host=k2a.world();docs=f.Docs(k,k2a.real_fields(host,journal='/var/lib/c3po-bar/supervisor'));before=k2a.state_of(host)
    refused_from_the_bytes(docs,'JOURNAL_ROOT_IS_THE_STATE_ROOT')
    receipt=docs.run(host);assert receipt['status']=='REFUSED' and k2a.state_of(host)==before and host.log==[] and names(host,'/var/lib/c3po-bar/supervisor')==[]
    k,host=k2a.world();fields=k2a.real_fields(host);fields['journal_chain']=hostemu.rows(host,'/etc/c3po-bar/manifests')
    refused_from_the_bytes(f.Docs(k,fields),'JOURNAL_ROOT_NOT_A_LEAF_OF_THE_PRIVATE_PARENT')
    k,host=k2a.world();docs=f.Docs(k,k2a.rehearsal_fields(host,parent=k2a.JOURNAL,reference='/etc/c3po-bar/manifests'));before=k2a.state_of(host)
    refused_from_the_bytes(docs,'THROWAWAY_PARENT_NOT_THE_FIXED_ONE')
    receipt=docs.run(host);assert receipt['status']=='REFUSED' and k2a.state_of(host)==before and host.log==[] and names(host,k2a.JOURNAL)==[]
    # each half of (b) alone
    k,host=k2a.world();refused_from_the_bytes(f.Docs(k,k2a.rehearsal_fields(host,parent=k2a.JOURNAL)),'THROWAWAY_PARENT_NOT_THE_FIXED_ONE')
    k,host=k2a.world();refused_from_the_bytes(f.Docs(k,k2a.rehearsal_fields(host,reference='/etc/c3po-bar/manifests')),'REFERENCE_ROOT_NOT_A_LEAF_OF_THE_PRIVATE_PARENT')
    k,host=k2a.world();refused_from_the_bytes(f.Docs(k,k2a.rehearsal_fields(host,reference='/var/lib/c3po-bar/supervisor')),'REFERENCE_ROOT_IS_THE_STATE_ROOT')

def test_f8_the_dispatcher_refuses_a_plan_below_the_floor_before_any_claim(tmp_path):
    """The floor is in validate_plan, which the dispatcher runs locally: a request bound to the wrong directory cannot
    spend the signature, let alone reach the host."""
    k,host=k2a.world();docs=f.Docs(k,k2a.real_fields(host,journal='/var/lib/c3po-bar/supervisor'));(tmp_path/'real').mkdir();dispatch=f.Dispatch(docs,tmp_path/'real')
    assert f.refusal(dispatch.prepare)=='JOURNAL_ROOT_IS_THE_STATE_ROOT' and not dispatch.claims()
    k,host=k2a.world();docs=f.Docs(k,k2a.rehearsal_fields(host,parent=k2a.JOURNAL,reference='/etc/c3po-bar/manifests'));(tmp_path/'rehearsal').mkdir()
    dispatch=f.Dispatch(docs,tmp_path/'rehearsal');assert f.refusal(dispatch.prepare)=='THROWAWAY_PARENT_NOT_THE_FIXED_ONE' and not dispatch.claims()

def test_f8_only_a_leaf_of_the_private_parent_that_is_not_the_state_root_is_a_journal_root():
    """Every private root-owned directory of the emulated host, signed as the journal root of a REAL request with its
    true rows: accepted exactly when it is a leaf of /var/lib/c3po-bar other than supervisor."""
    k,host=k2a.world()
    for extra in ('/var/lib/c3po-bar/journal-2','/var/lib/c3po-bar/journal/inner','/var/lib/c3po-reader','/var/lib/c3po-bar-rehearsal-x','/etc/c3po-reader','/root/journal','/srv/c3po-bar/journal'):
        host.tree.add(extra,mode=0o700)
    host.tree.add('/srv/c3po-bar',mode=0o700);node(host,'/srv/c3po-bar').mode=0o700
    accepted=[];seen=set()
    for path in sorted(host.tree.paths() if hasattr(host.tree,'paths') else walk(host)):
        found=node(host,path)
        if found.kind!='dir' or (found.uid,found.gid,found.mode)!=(0,0,0o700) or path==k2a.CONFIG:continue
        fields=k2a.real_fields(host);fields['journal_chain']=hostemu.rows(host,path);docs=f.Docs(k,fields)
        try:docs.authenticate();accepted.append(path)
        except ValueError as error:seen.add(str(error))
    assert accepted==['/var/lib/c3po-bar/journal','/var/lib/c3po-bar/journal-2'],accepted
    assert {'JOURNAL_ROOT_NOT_A_LEAF_OF_THE_PRIVATE_PARENT','JOURNAL_ROOT_IS_THE_STATE_ROOT'}<=seen
def walk(host):
    found=[]
    def down(item,prefix):
        for name,child in sorted(item.children.items()):
            found.append(prefix+'/'+name)
            if child.kind=='dir':down(child,prefix+'/'+name)
    down(host.tree.root,'');return found

def test_f8_a_new_leaf_after_a_failed_run_is_a_journal_root_and_completes():
    """The recovery of a burnt root (a new leaf under a new authorisation) stays possible with these bytes."""
    k,host=k2a.world();host.tree.add('/var/lib/c3po-bar/journal-2',mode=0o700);docs=f.Docs(k,k2a.real_fields(host,journal='/var/lib/c3po-bar/journal-2'))
    assert docs.go['effects']['journal_root']['path']=='/var/lib/c3po-bar/journal-2' and docs.go['effects']['journal_root']['is_the_real_journal_root'] is True
    receipt=docs.run(host);assert receipt['status']==k.m.COMPLETE_STATUS and names(host,'/var/lib/c3po-bar/journal-2')==k2a.NAMES and names(host,k2a.JOURNAL)==[]

def test_f8_the_docker_configuration_directory_is_the_one_of_the_unit_in_both_modes():
    for mode in MODES:
        for other in ('/etc/c3po-bar/manifests','/var/lib/c3po-bar/supervisor','/var/lib/c3po-bar/journal'):
            k,host=k2a.world();fields=k2a.real_fields(host) if mode=='REAL' else k2a.rehearsal_fields(host)
            if other==k2a.JOURNAL and mode=='REAL':
                host.tree.add('/var/lib/c3po-bar/journal-2',mode=0o700);fields['journal_chain']=hostemu.rows(host,'/var/lib/c3po-bar/journal-2')
            fields['docker_config_chain']=hostemu.rows(host,other);refused_from_the_bytes(f.Docs(k,fields),'DOCKER_CONFIG_NOT_THE_DIRECTORY_OF_THE_UNIT')

def test_f8_a_rehearsal_creates_in_var_lib_only():
    k,host=k2a.world()
    for parent in ('/','/var','/etc','/etc/c3po-bar','/var/lib/c3po-bar','/var/lib/c3po-bar/journal','/var/lib/c3po-bar/supervisor','/var/lib/docker','/usr','/usr/bin','/opt','/mnt','/run','/proc'):
        fields=k2a.rehearsal_fields(host);fields['journal_chain']=hostemu.rows(host,parent);docs=f.Docs(k,fields)
        assert code(docs) in ('THROWAWAY_PARENT_NOT_THE_FIXED_ONE','CHAIN_ROW_INVALID'),(parent,code(docs))
        assert docs.run(f.Untouchable())['phase_reached']=='AUTHENTICATION'
    m,docs,host=fresh('REHEARSAL');assert docs.plan['journal_chain'][-1]['path']=='/var/lib'==m.THROWAWAY_PARENT and docs.authenticate()
    assert not m.inside(m.journal_path(docs.plan),m.JOURNAL_PARENT) and not m.inside(m.docker_config_path(docs.plan),m.JOURNAL_PARENT)


# ================================================================ F2: docker's own status after a verified catalog
@pytest.mark.parametrize('mode',MODES)
def test_f2_a_status_of_docker_itself_after_a_verified_catalog_is_a_finding_and_the_root_is_not_burnt(mode):
    """`--rm` can turn a clean exit into 125 when the wait for the removal fails (README, "Exit statuses"). The line of
    the script and the host readback decide what the root is; the status is reported as a finding beside it."""
    for status in (125,126,127):
        m,docs,host=fresh(mode);host.docker.on_run=base.then(lambda call,result,status=status:(status,result[1]));receipt=docs.run(host)
        partial(receipt,'ENGINE_STATUS_AFTER_A_VERIFIED_CATALOG','CATALOG_VERIFIED_WITH_FINDINGS')
        assert receipt['run']=={'state':'RETURNED','code':None,'returncode':status,'seconds':0} and receipt['script_line']['as_signed'] is True and receipt['script_line']['returncode']==status
        assert receipt['catalog']['status']=='COMPLETE' and receipt['catalog']['epoch_json']['equal_to_the_expected_bytes'] is True and receipt['catalog']['entries']==2
        assert receipt['mutating_calls']['uncertain']==0 and receipt['mutating_calls']['succeeded']==(1 if mode=='REAL' else 3),'the effect is known: it is the verified catalog'
        assert names(host,k2a.root_of(mode))==k2a.NAMES;base.invariants(mode,host)
        # the status outranks the other findings beside a verified catalog, and never hides a new container from the receipt
        def leaves(call,result,status=status):
            call.docker.containers.append(hostemu.container('zealous_hopper',hostemu.BACKEND,hostemu.BACKEND,[]));return status,result[1]
        m,docs,host=fresh(mode);host.docker.on_run=base.then(leaves);receipt=docs.run(host)
        partial(receipt,'ENGINE_STATUS_AFTER_A_VERIFIED_CATALOG','CATALOG_VERIFIED_WITH_FINDINGS');assert receipt['containers']['not_there_before']==1

@pytest.mark.parametrize('mode',MODES)
def test_f2_a_status_of_docker_itself_without_a_verified_catalog_still_spends_the_root(mode):
    """Anything short of the signed line AND the verified readback: the engine could not run the container, as before."""
    hostile=[lambda call,result:(125,b''),                                                                     # the usual 125: nothing ran
             lambda call,result:(125,b'{"code": "MASSIVE_SESSION_ROOT_OWNER", "status": "CATALOG_REFUSED"}\n'),
             lambda call,result:base.line_of((125,result[1]),created=False),lambda call,result:base.line_of((125,result[1]),inode=7),
             lambda call,result:(base.edit('epoch.json',mode=0o644)(call,result),(125,result[1]))[1],         # the readback differs
             lambda call,result:(base.remove('maintenance.lock')(call,result),(126,result[1]))[1],
             lambda call,result:(setattr(call.node(call.command[4]),'mode',0o755),(127,result[1]))[1]]         # the readback is unavailable
    for index,behaviour in enumerate(hostile):
        m,docs,host=fresh(mode);host.docker.on_run=base.then(behaviour);receipt=docs.run(host)
        partial(receipt,'ENGINE_COULD_NOT_RUN_THE_CONTAINER');assert receipt['mutating_calls']['uncertain']==1 and receipt['mutating_calls']['failed_nothing_changed']==0,index
    # and a status that is the script's own stays what it was, whatever the line and the disk say
    for status in (1,2,3,124,128,137,143,-9,255):
        m,docs,host=fresh(mode);host.docker.on_run=base.then(lambda call,result,status=status:(status,result[1]));receipt=docs.run(host)
        partial(receipt,'SCRIPT_FAILED');assert receipt['catalog']['epoch_json']['equal_to_the_expected_bytes'] is True and receipt['mutating_calls']['uncertain']==1


# ================================================================ F10: what the reads left in the directory docker was given
def unit_partial(receipt,code,first=None):
    """REAL: the run is not a refusal because the directory of the unit is not known to be as it was; the root is untouched."""
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'],receipt['root_verdict'])==(PARTIAL,'PARTIAL_SEE_ROOT_VERDICT',code,'PRECHECK','UNTOUCHED_NO_CONTAINER_STARTED')
    assert receipt['precheck'].get('first_finding')==first and receipt['mutating_calls']=={'issued':0,'succeeded':0,'failed_nothing_changed':0,'uncertain':0}
    assert receipt['run'] is None and receipt['catalog'] is None and receipt['journal_root'] is None and f.sealed(receipt)

def test_f10_a_real_run_that_finds_the_directory_of_the_unit_changed_by_its_reads_is_never_a_refusal():
    """REFUSED says that nothing changed. Found with content before any docker command: a refusal. Changed while the two
    reads ran under it: a PARTIAL with a code of its own, the root untouched and usable, the entry counted as left by
    this run in an object that existed before. Nothing of this family removes that entry."""
    m,docs,host=fresh('REAL');host.tree.add(k2a.CONFIG+'/config.json',kind='file',mode=0o600);receipt=docs.run(host)
    refused(receipt,'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY');assert receipt['commands_started']['READ']==0 and receipt['precheck']=={'docker_config_entries':1}
    m,docs,host=fresh('REAL');writing_cli(host);receipt=docs.run(host)
    unit_partial(receipt,'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_THE_READS')
    assert receipt['commands_started']=={'READ':2,'CONTAINER':0,'EFFECT':0} and receipt['precheck']['docker_config_entries']==0 and receipt['precheck']['docker_config_entries_after_the_reads']==1
    assert names(host,k2a.CONFIG)==['config.json'] and names(host,k2a.JOURNAL)==[] and host.container_runs()==[]
    assert receipt['objects_left_by_this_run']==1 and receipt['pre_existing_objects_modified'] is True
    # an entry that appears in the journal root during the reads keeps the code of the root, and is a refusal: the reads left nothing
    m,docs,host=fresh('REAL')
    def hook(host,name,detail,calls):
        if name=='run' and detail[0][1:3]==['ps','-a'] and 'producer.lock' not in node(host,k2a.JOURNAL).children:host.tree.add(k2a.JOURNAL+'/producer.lock',kind='file',mode=0o600)
    host.hook=hook;receipt=docs.run(host);refused(receipt,'JOURNAL_ROOT_NOT_EMPTY');assert receipt['precheck']['docker_config_entries_after_the_reads']==0

def test_f10_whatever_a_read_ends_in_the_directory_docker_was_given_is_counted_before_the_run_is_called_a_refusal():
    """A read that fails after the CLI wrote: the first finding alone would be "refused, nothing changed". The count is
    taken whatever the reads ended in, and what it shows outranks the first finding, which is kept beside it."""
    findings=[(lambda host:host.docker.images[0]['Config']['Labels'].update({'org.opencontainers.image.revision':'0'*40}),'IMAGE_REVISION_MISMATCH',1),
              (lambda host:host.docker.images.pop(0),'IMAGE_ABSENT_OR_UNREADABLE',1),(lambda host:setattr(host.docker,'ps_returncode',1),'CONTAINER_LISTING_FAILED',2),
              (lambda host:host.hang_after.add(('ps','-a')),'COMMAND_TIMEOUT',2),(lambda host:host.hang.add(('ps','-a')),'COMMAND_TIMEOUT',2)]
    for index,(prepare,first,started) in enumerate(findings):
        # a CLI that behaves: the finding is a refusal, and the receipt says that the directory was counted and is empty
        m,docs,host=fresh('REAL');prepare(host);receipt=docs.run(host);refused(receipt,first)
        assert receipt['precheck']['docker_config_entries_after_the_reads']==0 and 'first_finding' not in receipt['precheck'] and receipt['commands_started']['READ']==started,index
        # a CLI that writes: the same finding is no longer a refusal
        m,docs,host=fresh('REAL');writing_cli(host);prepare(host);receipt=docs.run(host)
        unit_partial(receipt,'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_THE_READS',first);assert receipt['precheck']['docker_config_entries_after_the_reads']==1,index
        assert receipt['objects_left_by_this_run']==1 and receipt['pre_existing_objects_modified'] is True and names(host,k2a.JOURNAL)==[] and host.container_runs()==[]
        # REHEARSAL: the same, in the directory of its own; nothing of the unit is touched
        m,docs,host=fresh('REHEARSAL');writing_cli(host);prepare(host);receipt=docs.run(host)
        partial(receipt,'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_THE_READS');assert receipt['precheck']['first_finding']==first and names(host,k2a.CONFIG)==[] and names(host,k2a.REHEARSAL_CONFIG)==['config.json']
        assert receipt['objects_left_by_this_run']==2 and receipt['pre_existing_objects_modified'] is False,index
    # no docker command was started at all: nothing to count, a refusal
    for prepare,first in ((lambda host:host.absent.add('docker'),'COMMAND_NOT_STARTED'),(lambda host:setattr(node(host,'/usr/bin/docker'),'mode',0o775),'BINARY_UNAVAILABLE_OR_UNSAFE')):
        m,docs,host=fresh('REAL');prepare(host);receipt=docs.run(host);refused(receipt,first)
        assert 'docker_config_entries_after_the_reads' not in receipt['precheck'] and receipt['commands_started']['READ']==0 and host.commands==[]

def test_f10_with_a_cli_that_writes_no_failure_of_a_call_makes_a_real_run_a_refusal_once_the_directory_of_the_unit_changed():
    """REAL, a CLI that leaves a file in its configuration directory, and a failure at every call the run makes on the
    host. A REFUSED receipt of perform() always goes with a directory of the unit that is as it was. The one exception is
    not this operation's: an exception that is not an Exception (an interrupt) escapes perform(), and the frozen core's
    last resort calls a run without a mutating call a refusal (phase BEFORE_ANY_EFFECT) whatever its READ commands did.
    It is exact once the rehearsal has shown on the host that the CLI writes nothing (K2A-U2); reported as a core limit."""
    m,docs,host=fresh('REAL');assert docs.run(host)['status']==m.COMPLETE_STATUS;total=host.calls;seen={}
    for kind in (OSError,RuntimeError,hostemu.Death):
        for index in range(1,total+1):
            m,docs,host=fresh('REAL');writing_cli(host)
            def hook(host,name,detail,calls,index=index,kind=kind):
                if calls==index:raise kind(errno.EIO,'injected') if kind is OSError else kind('injected')
            host.hook=hook;receipt=docs.run(host);changed=names(host,k2a.CONFIG)!=[]
            if receipt['status']=='REFUSED' and changed:
                assert kind is hostemu.Death and (receipt['phase_reached'],receipt['code'])==('BEFORE_ANY_EFFECT','RUN_FAILED_BEFORE_ANY_EFFECT'),(kind.__name__,index,receipt['code'])
                seen['core']=seen.get('core',0)+1
            if changed and kind is not hostemu.Death:
                assert receipt['status']==PARTIAL and receipt['root_verdict']=='UNTOUCHED_NO_CONTAINER_STARTED' and receipt['phase_reached']=='PRECHECK',(kind.__name__,index)
                assert receipt['code'] in ('DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_THE_READS','DOCKER_CONFIG_DIRECTORY_NOT_READ_AFTER_THE_READS') and receipt['pre_existing_objects_modified'] in (True,None)
                seen[receipt['code']]=seen.get(receipt['code'],0)+1
            assert names(host,k2a.JOURNAL)==[] and host.container_runs()==[],'a CLI that writes never lets the container start'
    assert seen.get('DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_THE_READS',0)>20 and seen.get('DOCKER_CONFIG_DIRECTORY_NOT_READ_AFTER_THE_READS',0)>=2 and seen.get('core',0)>0

@pytest.mark.parametrize('mode',MODES)
def test_f10_a_directory_that_cannot_be_counted_after_a_failed_read_is_unknown_and_not_empty_by_assumption(mode):
    given=k2a.config_of(mode);armed=[]
    def hook(host,name,detail,calls):
        if name=='run':armed.append(1)
        elif armed and name=='names' and detail[0]==given:raise OSError(errno.EIO,'injected')
    m,docs,host=fresh(mode);host.docker.images[0]['Config']['Labels'].update({'org.opencontainers.image.revision':'0'*40})
    host.hook=hook;receipt=docs.run(host)
    if mode=='REAL':
        unit_partial(receipt,'DOCKER_CONFIG_DIRECTORY_NOT_READ_AFTER_THE_READS','IMAGE_REVISION_MISMATCH');assert receipt['pre_existing_objects_modified'] is None
    else:
        partial(receipt,'DOCKER_CONFIG_DIRECTORY_NOT_READ_AFTER_THE_READS');assert receipt['precheck']['first_finding']=='IMAGE_REVISION_MISMATCH' and receipt['pre_existing_objects_modified'] is False
    assert receipt['precheck']['docker_config_entries_after_the_reads'] is None and receipt['objects_left_by_this_run'] is None and 'injected' not in json.dumps(receipt)
    # the same when the reads themselves found nothing: a count that could not be taken is its own finding, not "changed" and not "empty"
    m,docs,host=fresh(mode);armed=[];host.hook=hook;receipt=docs.run(host)
    if mode=='REAL':unit_partial(receipt,'DOCKER_CONFIG_DIRECTORY_NOT_READ_AFTER_THE_READS')
    else:
        partial(receipt,'DOCKER_CONFIG_DIRECTORY_NOT_READ_AFTER_THE_READS');assert 'first_finding' not in receipt['precheck']
    assert receipt['precheck']['docker_config_entries_after_the_reads'] is None and receipt['precheck']['containers']==8 and host.container_runs()==[] and receipt['objects_left_by_this_run'] is None

@pytest.mark.parametrize('mode',MODES)
def test_f10_what_docker_left_in_its_directory_is_counted_as_left_by_the_run(mode):
    """After the run as well: the entries found in the directory docker was given are objects this run left; in mode
    REAL they are in an object that existed before; a count that could not be taken makes both unknown."""
    given=k2a.config_of(mode);created=0 if mode=='REAL' else 2
    m,docs,host=fresh(mode);receipt=docs.run(host);assert receipt['objects_left_by_this_run']==created+2 and receipt['pre_existing_objects_modified'] is (mode=='REAL')
    m,docs,host=fresh(mode);host.docker.on_run=base.then(lambda call,result:call.docker.host.tree.add(given+'/config.json',kind='file',mode=0o600) and None);receipt=docs.run(host)
    partial(receipt,'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_RUN','CATALOG_VERIFIED_WITH_FINDINGS');assert receipt['objects_left_by_this_run']==created+3 and receipt['pre_existing_objects_modified'] is (mode=='REAL')
    m,docs,host=fresh(mode);host.docker.on_run=base.then(lambda call,result:setattr(call.docker.host.tree.get(given),'mode',0o755));receipt=docs.run(host)
    partial(receipt,'DOCKER_CONFIG_READBACK_UNAVAILABLE','CATALOG_VERIFIED_WITH_FINDINGS');assert receipt['objects_left_by_this_run'] is None and receipt['pre_existing_objects_modified'] is (True if mode=='REAL' else False)
    # REAL, a container that wrote nothing and a CLI that left an entry: the root was not modified, the directory of the unit was
    m,docs,host=fresh(mode)
    def nothing_but_the_cli(call):
        call.docker.host.tree.add(given+'/config.json',kind='file',mode=0o600);return 137,b''
    host.docker.on_run=nothing_but_the_cli;receipt=docs.run(host);partial(receipt,'SCRIPT_OUTPUT_NOT_ONE_LINE')
    assert receipt['catalog']['entries']==0 and receipt['objects_left_by_this_run']==created+1 and receipt['pre_existing_objects_modified'] is (mode=='REAL')


# ================================================================ F12: descriptors
@pytest.mark.parametrize('mode',MODES)
def test_f12_no_descriptor_is_left_when_a_held_directory_cannot_be_looked_at(mode):
    """A failure of any call at any point of the run leaves no descriptor of a walked chain open. What remains is the
    frozen core's own: files.create_directory does not close the directory it has just created and opened when the
    first look at it fails (core/parts/files.py, the Pinned built from the new descriptor). Reported as a core defect;
    it cannot occur in mode REAL, which creates nothing."""
    m,docs,host=fresh(mode);assert docs.run(host)['status']==m.COMPLETE_STATUS;total=host.calls;leaks=[]
    for kind in (OSError,RuntimeError):
        for index in range(1,total+1):
            m,docs,host=fresh(mode)
            def hook(host,name,detail,calls,index=index,kind=kind):
                if calls==index:raise kind(errno.EIO,'injected') if kind is OSError else kind('injected')
            host.hook=hook;receipt=docs.run(host)
            if host.fds!={}:leaks.append((host.log[-1][:2],sorted(value[3] for value in host.fds.values()),receipt['status'],receipt['code']))
    created=(k2a.REHEARSAL_CONFIG,k2a.REHEARSAL_ROOT)
    assert all(event[0]=='fstat' and event[1] in created and held==[event[1]] and (status,found)==(PARTIAL,'CREATED_STAT_FAILED') for event,held,status,found in leaks),leaks
    if mode=='REAL':assert leaks==[]

def test_f12_pin_chain_closes_the_descriptor_it_walked_to_when_the_directory_cannot_be_held():
    m,docs,host=fresh('REAL');gate=lambda:55.0
    def hook(host,name,detail,calls):
        if name=='fstat' and detail[0]==k2a.CONFIG and [entry[:2] for entry in host.log].count(('fstat',k2a.CONFIG))==2:raise OSError(errno.EIO,'injected')
    host.hook=hook
    with pytest.raises(OSError):m.pin_chain(host,docs.plan['docker_config_chain'],gate,[])
    assert host.fds=={}
    host.hook=None;held=m.pin_chain(host,docs.plan['docker_config_chain'],gate,[]);assert len(host.fds)==1 and held.identity[:2]==(node(host,k2a.CONFIG).dev,node(host,k2a.CONFIG).ino)
    held.close();assert host.fds=={}


# ================================================================ F9: what the reviewer's own mutants showed
def test_f9_the_epoch_of_a_real_request_is_exactly_the_constant():
    for other in ('R2D2-V2-SHADOW-2026-10-05-X','R2D2-V2-SHADOW-2026-10-05\n','R2D2-V2-SHADOW-2026-10-050',' R2D2-V2-SHADOW-2026-10-05','r2d2-v2-shadow-2026-10-05','R2D2-V2-SHADOW-2026-10-0',
                  'R2D2-V2-SHADOW-2026-10-05\x00','XR2D2-V2-SHADOW-2026-10-05',''):
        m,docs,host=fresh('REAL');docs.plan['epoch']=other;docs.chain();refused_from_the_bytes(docs,'EPOCH_NOT_THE_COMPILED_CONSTANT')

def test_f9_the_boundaries_of_the_three_grammars():
    m,docs,host=fresh('REAL');docs.plan['container_journal_root']='/'+'a'*64;docs.chain();assert docs.authenticate()
    m,docs,host=fresh('REAL');docs.plan['container_journal_root']='/'+'a'*65;docs.chain();assert code(docs)=='CONTAINER_JOURNAL_ROOT_INVALID'
    m,docs,host=fresh('REHEARSAL');docs.plan['throwaway_name']='c3po-bar-rehearsal-'+'a'*40;docs.chain();assert docs.authenticate()
    m,docs,host=fresh('REHEARSAL');docs.plan['throwaway_name']='c3po-bar-rehearsal-'+'a'*41;docs.chain();assert code(docs)=='THROWAWAY_NAME_INVALID'
    m,docs,host=fresh('REHEARSAL');docs.plan['epoch']='R2D2-V2-DIAG-'+'a'*80;docs.chain();assert docs.authenticate()
    m,docs,host=fresh('REHEARSAL');docs.plan['epoch']='R2D2-V2-DIAG-'+'a'*81;docs.chain();assert code(docs)=='EPOCH_NOT_A_DIAGNOSTIC_ONE'
    m,docs,host=fresh('REHEARSAL');docs.plan['epoch']='R2D2-V2-DIAG-abc\n';docs.chain();assert code(docs)=='EPOCH_NOT_A_DIAGNOSTIC_ONE'
    m,docs,host=fresh('REHEARSAL');docs.plan['throwaway_name']='c3po-bar-rehearsal-a\n';docs.chain();assert code(docs)=='THROWAWAY_NAME_INVALID'

def test_f9_the_entry_limit_of_the_readback_at_its_boundary():
    for extra,expected,entries in ((62,'CATALOG_READBACK_MISMATCH',64),(63,'CATALOG_READBACK_UNAVAILABLE',65)):
        m,docs,host=fresh('REAL')
        def many(call,extra=extra):
            result=k2a.container(call);root=call.node(call.command[4])
            for index in range(extra):root.children['f%d'%index]=hostemu.Node('file',mode=0o600)
            return result
        host.docker.on_run=many;receipt=docs.run(host);assert receipt['code']==expected and len(names(host,k2a.JOURNAL))==entries
        assert receipt['catalog']['entries']==(64 if extra==62 else None) and receipt['catalog']['code']==(None if extra==62 else 'ENTRY_LIMIT')

@pytest.mark.parametrize('mode',MODES)
def test_f9_a_container_recreated_under_the_same_name_during_the_run_is_a_newcomer(mode):
    """Containers are told apart by ID. A service recreated under its name while the run was under way is a container
    that was not there before."""
    def recreated(call):
        result=k2a.container(call);old=call.docker.containers[0]
        call.docker.containers[0]=hostemu.container(old['Name'][1:],old['Image'],old['Config']['Image'],[]);return result
    m,docs,host=fresh(mode);host.docker.on_run=recreated;receipt=docs.run(host)
    partial(receipt,'CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE','CATALOG_VERIFIED_WITH_FINDINGS')
    assert receipt['containers']['not_there_before']==1 and (receipt['containers']['before'],receipt['containers']['after'])==(8,8) and receipt['containers']['rows'][0]['name']=='c3po-api-1'

@pytest.mark.parametrize('mode',MODES)
def test_f9_what_is_not_known_is_not_reported_as_zero_or_false(mode):
    m,docs,host=fresh(mode);armed=[]
    def hook(host,name,detail,calls):
        if name=='run' and detail[0][1]=='run':armed.append(1)
        elif armed and name=='names' and detail[0]==k2a.root_of(mode):raise OSError(errno.EIO,'injected')
    host.hook=hook;receipt=docs.run(host)
    partial(receipt,'CATALOG_READBACK_UNAVAILABLE');assert receipt['catalog']['entries'] is None and receipt['catalog']['root_unchanged'] is None and receipt['catalog']['code']=='READBACK_OS_ERROR'
    assert receipt['objects_left_by_this_run'] is None and receipt['pre_existing_objects_modified'] is (False if mode=='REHEARSAL' else None)

def test_f9_the_expected_hash_of_a_mismatch_is_the_expected_one():
    m,docs,host=fresh('REAL')
    def other(call):
        result=k2a.container(call);call.node(call.command[4]+'/epoch.json').content=bytearray(b'{"device":1}');return result
    host.docker.on_run=other;receipt=docs.run(host);root=node(host,k2a.JOURNAL);row=receipt['catalog']['epoch_json']
    assert row['expected_sha256']==f.sha(k2a.expected_epoch_json(k2a.EPOCH,root.dev,root.ino))!=row['sha256']==f.sha(b'{"device":1}') and row['equal_to_the_expected_bytes'] is False

def test_f9_root_unchanged_is_false_only_for_a_root_that_was_replaced():
    """An expiry while the root is verified again is not a replaced root: root_unchanged stays unknown."""
    m,docs,host=fresh('REAL');wall=[docs.now];armed=[]
    def hook(host,name,detail,calls):
        if name=='read' and detail[0]==k2a.JOURNAL+'/epoch.json':armed.append(1)
        if armed and name=='fstat' and detail[0]==k2a.JOURNAL+'/epoch.json' and len(armed)==1:armed.append(2)
        if len(armed)>=2 and name=='open' and detail[0]=='/':wall[0]=docs.now+timedelta(minutes=30)
    host.hook=hook;receipt=docs.run(host,clock=lambda:wall[0])
    partial(receipt,'CATALOG_READBACK_UNAVAILABLE');assert receipt['catalog']['code']=='GO_EXPIRED' and receipt['catalog']['root_unchanged'] is None and receipt['catalog']['entries']==2

def test_f9_a_probe_that_could_not_establish_absence_is_not_an_absent_throwaway():
    """For the instant of the probe a component of the way is a symbolic link (and is what it was again afterwards, so
    that the last look cannot be what refuses): absence was not established, and nothing is created on a guess."""
    # /var/lib is looked at by name four times before anything is created: by the walk of the real root, by the walk
    # of the parent, by the probe of the throwaway root and by the probe of the directory for docker
    for target,nth in ((k2a.REHEARSAL_ROOT,3),(k2a.REHEARSAL_CONFIG,4)):
        m,docs,host=fresh('REHEARSAL');state={'kept':None,'probes':0};var=host.tree.root.children['var']
        def restore():
            if state['kept'] is not None:var.children['lib']=state['kept'];state['kept']=None
        def hook(host,name,detail,calls,nth=nth):
            restore()                                                    # as it was, at the first call after the lstat that saw the link
            if name=='lstat' and detail[0]=='/var/lib' and [entry[:2] for entry in host.log].count(('lstat','/var/lib'))==nth:
                state['probes']+=1;state['kept']=var.children['lib'];var.children['lib']=hostemu.Node('symlink',mode=0o777)
        host.hook=hook;before=k2a.state_of(host);receipt=docs.run(host);restore()
        assert state['probes']==1,'the hook met the probe of '+target
        refused(receipt,'DESTINATION_PRESENT');assert k2a.state_of(host)==before and host.commands==[] and host.mutating()==[]
        label='throwaway' if target==k2a.REHEARSAL_ROOT else 'throwaway_docker_config';assert receipt['precheck'][label]=={'exists':None}

@pytest.mark.parametrize('mode',MODES)
def test_f9_documents_that_allow_an_activation_are_refused_and_no_receipt_claims_one(mode):
    """Behavioural, not a pin of the constant: a request, an authority and a GO that all say activation_allowed true
    (and are otherwise the signed set) do not authenticate."""
    m,docs,host=fresh(mode)
    for document in (docs.request,docs.authority,docs.go):document['activation_allowed']=True
    docs.chain();assert code(docs)=='REQUEST_SCOPE'
    receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'],receipt['activation_performed'])==('REFUSED','REQUEST_SCOPE',False)
    for index,document in enumerate((docs.request,docs.authority,docs.go)):
        m,other,host=fresh(mode);(other.request,other.authority,other.go)[index]['activation_allowed']=True;other.chain()
        assert code(other) in ('REQUEST_SCOPE','AUTHORITY_UNBOUND','GO_UNBOUND')
    m,docs,host=fresh(mode);receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS and receipt['activation_performed'] is False and receipt['effects']['activation'] is False


# ================================================================ F13: the limit of "only a constant code leaves"
def test_f13_of_a_refusal_of_the_script_a_token_of_the_code_grammar_leaves_and_nothing_else():
    """What is kept is what fits the grammar of a constant code, [A-Z][A-Z0-9_]{0,79}: the application's own codes do.
    A text that happens to be such a token leaves as well; anything else is NOT_A_CONSTANT_CODE and the receipt
    carries the size and the hash of the line only. The container has no secret, no environment file and no network."""
    def answer(text):
        m,docs,host=fresh('REAL');host.docker.on_run=lambda call:(1,(json.dumps({'status':'CATALOG_REFUSED','code':text})+'\n').encode());return docs.run(host)
    for text in ('CATALOG_INIT_ROOT_NOT_EMPTY','EPOCH_INVALID','MASSIVE_SESSION_MANIFEST_CHANGED','MASSIVE_MAINTENANCE_BUSY','SOURCE_DIRECTORY_NOT_PRIVATE','AKIAIOSFODNN7EXAMPLE','A'*80):
        assert answer(text)['script_line']['refusal_code']==text
    for text in ("No module named 'app'",'not enough values to unpack (expected 2, got 1)','lower_case','A'*81,'WITH SPACE','ÀCCENT','A\n','',' A'):
        receipt=answer(text);assert receipt['script_line']['refusal_code']=='NOT_A_CONSTANT_CODE'
        if len(text)>=10 and text.isascii():assert text.encode() not in f.line(receipt),'the text itself is nowhere in the receipt'
        line=(json.dumps({'status':'CATALOG_REFUSED','code':text})+'\n').encode()
        assert (receipt['script_line']['bytes'],receipt['script_line']['sha256'])==(len(line),f.sha(line)),'the line can be matched offline by hashing candidates'


# ================================================================ static: the proof job and the seal (F6, F7)
def test_static_the_proof_job_builds_on_the_base_of_the_release_by_digest_and_on_the_paths_of_the_host():
    script=k2a.DIRECTORY/'linux_root'/'run_catalog.sh'
    if not script.is_file():pytest.skip('a private copy without linux_root/ (the mutation harness)')
    text=script.read_text();base_line=[line for line in text.splitlines() if line.startswith('BASE=')]
    assert base_line==['BASE=python:3.12-alpine3.24@sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a']
    assert "printf 'FROM %s\\n" in text and 'FROM python:3.12-alpine\\n' not in text and 'grep -Fxq "FROM $BASE" "$RELEASE/c3po/backend/Dockerfile"' in text
    assert '508636d0bb9cbc81076dfcfeb49cab03f1762c613b740d4a7391faf1a26e8ebf  c3po/backend/Dockerfile' in text
    for path in ('/etc/c3po-bar','/var/lib/c3po-bar','/etc/c3po-bar/docker-cli','/var/lib/c3po-bar/journal','REHEARSAL=/var/lib/c3po-bar-rehearsal-ci'):assert path in text
    tree=k2a.release_tree();dockerfile=None if tree is None else tree/'c3po'/'backend'/'Dockerfile'
    if dockerfile is None or not dockerfile.is_file():pytest.skip('no Dockerfile of the release at hand (HOSTOPS02_TEST_RELEASE_TREE)')
    raw=dockerfile.read_bytes();assert f.sha(raw)=='508636d0bb9cbc81076dfcfeb49cab03f1762c613b740d4a7391faf1a26e8ebf'
    assert raw.decode().splitlines().count('FROM '+base_line[0][5:])==1 and b'ENTRYPOINT' not in raw and raw.count(b'\nFROM ')==1

def test_static_the_seal_does_not_cover_the_directories_of_a_review(tmp_path):
    path=k2a.DIRECTORY/'seal.py';spec=importlib.util.spec_from_file_location('_hostops02_k2a_seal',path);seal=importlib.util.module_from_spec(spec);spec.loader.exec_module(seal)
    for name in ('op.py','build/x.py','tests/t.py','review-host/NOTES.md','review-host/work/probe.py','review-purity/deep/er/file','work/release/file','reviewed/kept.txt','x/review-host/kept.txt',
                 '_tmp/a','tests/__pycache__/t.pyc','SHA256SUMS','linux_root/CATALOG_SHAPE.linux-root.json','repair-notes/kept.md'):
        (tmp_path/name).parent.mkdir(parents=True,exist_ok=True);(tmp_path/name).write_bytes(b'x')
    seal.HERE=tmp_path
    assert seal.files()==['build/x.py','op.py','repair-notes/kept.md','reviewed/kept.txt','tests/t.py','x/review-host/kept.txt']
