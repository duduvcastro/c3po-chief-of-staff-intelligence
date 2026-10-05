"""Byte and text pins of K2a against the release it is frozen for (dd4ec4bb): the README's command and script, the
compiled epoch constant, the names the application uses. Every test here is named "static": a mutation run deselects
them, so that no mutant dies merely because a pinned text changed. The comparisons with the files of the release run
when a tree of it is at hand (k2a.release_tree) and are skipped otherwise; the literal pins always run."""
import ast
import json
import re

import pytest

import family as f
import hostemu
import k2a

README_COMMAND='''DOCKER_CONFIG=<HOST_CONFIG_DIR>/docker-cli docker run --rm -i --pull never --init --user 0:0 --network none --read-only \\
  --cap-drop ALL --security-opt no-new-privileges \\
  --mount type=bind,source=<HOST_JOURNAL_ROOT>,target=<CONTAINER_JOURNAL_ROOT> \\
  <IMAGE_ID> python -I -B - <CONTAINER_JOURNAL_ROOT> "$epoch" < catalog-init.py
'''
def release():
    tree=k2a.release_tree()
    if tree is None:pytest.skip('no tree of the release at hand (HOSTOPS02_TEST_RELEASE_TREE)')
    return tree
def readme_words(journal,target,image,epoch,config):
    """The README's command as the words a process is started with: continuation lines joined, the variable prefix
    and the redirection taken off (they are the environment and the standard input), the four placeholders filled."""
    words=README_COMMAND.replace('\\\n',' ').split()
    assert words[0]=='DOCKER_CONFIG=<HOST_CONFIG_DIR>/docker-cli' and words[1]=='docker' and words[-2:]==['<','catalog-init.py']
    table={'<HOST_JOURNAL_ROOT>':journal,'<CONTAINER_JOURNAL_ROOT>':target,'<IMAGE_ID>':image,'"$epoch"':epoch}
    out=[]
    for word in words[2:-2]:
        for old,new in table.items():word=word.replace(old,new)
        out.append(word)
    return words[0].replace('<HOST_CONFIG_DIR>/docker-cli',config),out

@pytest.mark.parametrize('mode',['REAL','REHEARSAL'])
def test_static_the_process_started_is_the_command_of_the_readme_word_for_word(mode):
    docs,host=k2a.case(mode);receipt=docs.run(host);assert receipt['status']==docs.k.m.COMPLETE_STATUS
    entry=[entry for entry in host.commands if entry['argv'][1]=='run'];assert len(entry)==1
    prefix,words=readme_words(k2a.root_of(mode),k2a.TARGET,hostemu.BACKEND,k2a.EPOCH if mode=='REAL' else k2a.DIAG,k2a.config_of(mode))
    assert entry[0]['argv']==['/usr/bin/docker']+words and prefix=='DOCKER_CONFIG='+entry[0]['docker_config'] and entry[0]['variables']=={}
    assert (prefix=='DOCKER_CONFIG=/etc/c3po-bar/docker-cli')==(mode=='REAL'),'<HOST_CONFIG_DIR>/docker-cli itself in REAL only; a rehearsal fills the placeholder with its own directory'
    assert entry[0]['stdin']==k2a.script() and docs.go['effects']['container']['docker_arguments']==words

def test_static_the_readme_of_the_release_holds_that_command_and_that_script():
    readme=(release()/'c3po/deployment/massive-supervisor/README.md').read_text()
    assert readme.count(README_COMMAND)==1 and readme.splitlines()[335:339]==README_COMMAND.splitlines()
    found=re.findall(r'^<!-- catalog-init-script:begin -->\n```python\n(.*?)```\n<!-- catalog-init-script:end -->$',readme,re.S|re.M)
    assert len(found)==1 and found[0].encode()==k2a.script() and readme.splitlines()[352:373]==found[0].splitlines()
    assert 'Its SHA-256 is `'+k2a.SCRIPT_SHA+'`' in readme and readme.count(k2a.SCRIPT_SHA)==1
    assert '**Epoch `R2D2-V2-SHADOW-2026-10-05` uses placement A, by decision of the owner.**' in readme
    # the layout floor of the operation part is the layout of the README (operation 2, placement A)
    m=k2a.K().m;lines=readme.splitlines()
    assert lines[96]=='  | `%s` | `root:root` | 0700 | empty, and it stays empty |'%m.UNIT_DOCKER_CONFIG
    assert lines[97]=='  | `%s` | `root:root` | 0700 | the state root below and, under placement A, the journal root |'%m.JOURNAL_PARENT
    assert lines[98]=='  | `%s` = `@HOST_STATE_ROOT@` | `root:root` | 0700 | empty |'%m.STATE_ROOT
    assert lines[99].startswith('  | placement A: `%s/journal` = `@HOST_JOURNAL_ROOT@` | `root:root` | 0700 | empty; created new below `%s`, on the filesystem of `%s`,'%(m.JOURNAL_PARENT,m.JOURNAL_PARENT,m.THROWAWAY_PARENT))
    assert 'a new name below `%s` under placement A'%m.JOURNAL_PARENT in lines[302]
    assert 'under placement A `/var/lib/c3po-bar/journal` and `/c3po-bar-journal`' in readme

def test_static_script_constant_and_its_hash():
    m=k2a.K().m;raw=m.script_bytes()
    assert f.sha(raw)=='715d7a660e7a2c4dd5c11287063726cc971156dd6fefc2365c431c9aee0f4bb7'==m.CATALOG_SCRIPT_SHA256==m.SCOPE['script']['sha256'] and len(raw)==1040==m.CATALOG_SCRIPT_BYTES
    assert raw.startswith(b"import json, os, sys\nsys.path.insert(0, '/app')\ntry:\n") and raw.endswith(b"print(json.dumps(receipt, sort_keys=True))\n") and raw.count(b'\n')==21
    assert m.CATALOG_SCRIPT_SHA256 in m.SCOPE_STATEMENT and m.EPOCH_COMPILED in m.SCOPE_STATEMENT

def test_static_epoch_constant_is_the_compiled_constant_of_the_release_and_the_names_are_the_applications():
    m=k2a.K().m;tree=release()/'c3po/backend/app'
    lines=(tree/'r2d2_v2_epoch_assembler.py').read_text().splitlines()
    assert lines[8]=="EPOCH = 'R2D2-V2-SHADOW-2026-10-05'" and ast.literal_eval(lines[8].split('=',1)[1].strip())==m.EPOCH_COMPILED
    assert m.EPOCH_SOURCE=='c3po/backend/app/r2d2_v2_epoch_assembler.py:9 EPOCH at '+k2a.RELEASE
    sessions=(tree/'r2d2_v2_massive_sessions.py').read_text().splitlines()
    assert sessions[203]=="                    _immutable(directory, 'epoch.json', {'schema': 'MASSIVE_SESSION_ROOT_V1', 'epoch': self.epoch," and sessions[204].strip()=="'device': info.st_dev, 'inode': info.st_ino})"
    assert sessions[58]=='    data = canonical(value)' and "0o600, dir_fd=directory)" in sessions[61]
    maintenance=(tree/'r2d2_v2_massive_maintenance.py').read_text().splitlines()
    assert maintenance[25].strip()=="lock=os.open('maintenance.lock',flags|os.O_NOFOLLOW|os.O_NONBLOCK," and maintenance[26].strip()=="0o600,dir_fd=directory)"
    store=(tree/'r2d2_v2_store.py').read_text().splitlines()
    assert 're.fullmatch(r"R2D2-V2-(?:SHADOW|DIAG)-[A-Za-z0-9_-]{1,80}", epoch)' in store[38]
    assert (m.CATALOG_FILES,m.CATALOG_SCHEMA,m.CATALOG_FILE_MODE,m.REHEARSAL_EPOCH)==(('epoch.json','maintenance.lock'),'MASSIVE_SESSION_ROOT_V1',0o600,'R2D2-V2-DIAG-[A-Za-z0-9_-]{1,80}')
    sources=(tree/'r2d2_v2_sources.py').read_text()
    assert 'return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()' in sources

def test_static_identity_dates_evidence_and_the_command_table():
    m=k2a.K().m
    assert (m.OPERATION,m.PHASE,m.WRITES_ALLOWED,m.ACTIVATION_ALLOWED,m.DATE_CLASS)==('GO_WRITE_HOSTOPS02_CATALOG_INIT_01','WRITE_BAR_JOURNAL_CATALOG_INITIALISATION_4B',True,False,'WRITE_WEEKEND')
    assert m.DATES==('2026-10-02','2026-10-03','2026-10-04') and m.MAX_GATE_SPAN_SECONDS==900
    assert m.EVIDENCE_OPERATIONS==('GO_READONLY_HOSTOPS_PRECHECK_01','GO_WRITE_SUPERVISOR_READER_PROVISION_01') and m.EVIDENCE_REQUIRED is True
    assert (m.COMPLETE_OUTCOME,m.REHEARSAL_COMPLETE_OUTCOME,m.PARTIAL_OUTCOME,m.REFUSED_OUTCOME,m.ESCAPED_OUTCOME)==(
        'CATALOG_READY_VERIFIED','REHEARSAL_CATALOG_READY_VERIFIED','PARTIAL_SEE_ROOT_VERDICT','REFUSED_NOTHING_CHANGED_NO_CONTAINER_STARTED','PARTIAL_STATE_UNKNOWN_ROOT_NOT_TO_BE_USED_AGAIN')
    assert sorted(m.COMMANDS)==['catalog_init','container_list','image'] and m.BINARIES=={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
    run=m.COMMANDS['catalog_init']
    assert (run['tool'],run['argv'],run['tail'],run['class'],run['kind'],run['stdin'])==('docker',['run','--rm','-i','--pull','never','--init','--user','0:0','--network','none',
        '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges'],[],'RUN','EFFECT',True)
    assert m.COMMAND_CLASSES['RUN']=={'seconds':40,'output_bytes':65536} and m.AFTER_EFFECT_RESERVE_SECONDS==4 and m.effects_budget('catalog_init')==44
    assert [(m.COMMANDS[name]['class'],m.COMMANDS[name]['kind']) for name in ('image','container_list')]==[('QUICK','READ')]*2
    assert (m.UNIT_DOCKER_CONFIG,m.JOURNAL_PARENT,m.STATE_ROOT,m.THROWAWAY_PARENT,m.THROWAWAY_CONFIG_SUFFIX)==('/etc/c3po-bar/docker-cli','/var/lib/c3po-bar','/var/lib/c3po-bar/supervisor','/var/lib','.docker-cli')
    assert set(m.PLAN_KEYS)=={'mode','journal_chain','throwaway_name','reference_chain','container_journal_root','docker_config_chain','image_id','image_revision','epoch',
                              'script_sha256','evidence_boot_id_sha256'}
    assert [name for name in dir(m.Native) if not name.startswith('_')]==sorted(['identity','noatime','open','close','fstat','lstat','fstatvfs','read','names','run',
                                                                               'umask','mkdir','create','write','fsync','link','unlink'])
    spec=f.assembler().load_spec(k2a.DIRECTORY);assert spec.PARTS==['core','runner','docker','parents','files'] and spec.SUCCESS_IN_TEMPLATE is False

def test_static_scope_says_what_the_signers_must_see():
    m=k2a.K().m;scope=json.loads(m.canonical(m.SCOPE))
    assert scope['modes']==['REAL','REHEARSAL'] and scope['success_outcome']=={'REAL':'CATALOG_READY_VERIFIED','REHEARSAL':'REHEARSAL_CATALOG_READY_VERIFIED'}
    assert scope['epoch']=={'REAL':'R2D2-V2-SHADOW-2026-10-05','REAL_source':m.EPOCH_SOURCE,'REHEARSAL_grammar':'R2D2-V2-DIAG-[A-Za-z0-9_-]{1,80}'}
    assert scope['catalog']['names']==['epoch.json','maintenance.lock'] and scope['catalog']['mode_octal']=='0600' and scope['throwaway_name']=='c3po-bar-rehearsal-[a-z0-9][a-z0-9-]{0,39}'
    assert scope['layout']=={'docker_config_of_the_unit':'/etc/c3po-bar/docker-cli','journal_root':'a leaf of /var/lib/c3po-bar','never_a_journal_root':'/var/lib/c3po-bar/supervisor',
                             'throwaway_parent':'/var/lib','throwaway_docker_config':'<throwaway root>.docker-cli'}
    assert 'a docker command of a rehearsal under the configuration directory of the unit' in scope['never']
    assert scope['evidence_operations_required']==list(m.EVIDENCE_OPERATIONS) and scope['limits']['max_seconds']==60 and scope['files_allowance_seconds']==2
    for word in ('any removal','a second run on a root','docker exec','a network for the container','--name or any option the README does not write'):assert word in scope['never']
    for sentence in ('removed on exit, never a pull, an init process, uid 0, no network, read-only root filesystem, no capability','as its only mount',
                     'Nothing is removed','is not to be used again','a timeout stops the docker CLI, not the container','a leaf of /var/lib/c3po-bar that is not the state root',
                     'the docker CLI under /etc/c3po-bar/docker-cli','two private throwaway directories in /var/lib','no docker command of a rehearsal runs under the directory of the unit'):assert sentence in m.SCOPE_STATEMENT
