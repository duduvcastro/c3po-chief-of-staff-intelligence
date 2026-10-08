"""Explicit one-time native installation stages, never service auto-bootstrap.

Fable runs a separately authorized preparation. Missing/torn/partial state is
consumed and never repaired by this module. A fresh plan requires a fresh human
authority, not a renamed root. Final unit files are data only, for independent
review and authorized installation; this module never enables/starts a timer.
"""
import os
import platform
import pwd
import re
import sys
from pathlib import Path
from datetime import timedelta,timezone
from common import PinnedDirectory,canonical,context,digest,fields,instant,need,sha,strict
from runtime import directory_chain,identity,physical
from channel import GitHub429

BRT=timezone(timedelta(hours=-3))
ROOT_ROLES={'journal','witness','inputs','results','capacity','bars','receipts','publication','observer','retention'}


def host_preamble(mode):
    need(mode in ('REAL','FIXTURE'),'INSTALL_MODE')
    if mode=='REAL':need(platform.system()=='Linux','INSTALL_NOT_LINUX')
    python=str(Path(sys.executable).absolute());raw,_=physical(python,maximum=128*1024*1024,executable=True)
    boot=(Path('/proc/sys/kernel/random/boot_id').read_text().strip() if mode=='REAL' else 'FIXTURE_NO_PHYSICAL_BOOT')
    return {'mode':mode,'executor_uid':os.geteuid(),'executor_gid':os.getegid(),'python_path':python,
            'python_sha256':digest(raw),'python_version':platform.python_version(),'boot':boot}


class PreparationGuard:
    def __init__(self,plan):
        self.plan=plan;self.mode=plan['mode'];self.context=context(plan['context'])
        self.value={'measurement':{'euid':plan['host']['executor_uid']}}
    def recheck(self):
        need(host_preamble(self.mode)==self.plan['host'],'INSTALL_PHYSICAL_HOST_CHANGED')
        for item in self.plan['source_files']:
            raw,ident=physical(item['path'])
            need(digest(raw)==sha(item['sha256']) and ident['mode'] in (0o400,0o444),'INSTALL_SOURCE_CHANGED')
        return digest(canonical(self.plan))


def prepare(plan_raw,*,clock,fixture=False,channel=None):
    """Own original signatures precede the durable first claim and all roots.

    The journal's immutable seed uses the installation plan hash; future slot
    request/owner/review IDs live in the later acceptance, not its genesis. This
    separates measurement from those subsequent signatures without reset.
    """
    plan=strict(plan_raw);need(canonical(plan)==plan_raw,'INSTALL_PLAN_CANONICAL')
    fields(plan,('schema','mode','context','host','source_files','claim_parent','claim_name','roots',
           'registry_template','assets','authority_references','channel','start_UTC','end_UTC','budget_seconds',
           'witness_independence'),'INSTALL_PLAN_FIELDS')
    need(plan['schema']=='SERVER_INSTALLATION_PLAN_V2' and ((fixture and plan['mode']=='FIXTURE') or
         (not fixture and plan['mode']=='REAL')),'INSTALL_FIXTURE_NOT_REAL')
    ctx=context(plan['context']);pin=digest(plan_raw);guard=PreparationGuard(plan);guard.recheck()
    now=instant(clock());start,end=instant(plan['start_UTC']),instant(plan['end_UTC'])
    need(type(plan['budget_seconds']) is int and 0<plan['budget_seconds']<=120
         and start<=now and now+timedelta(seconds=plan['budget_seconds'])<end,'INSTALL_WINDOW')
    feed=plan['channel'];real=channel or GitHub429(guard,feed['token_path'],feed['token_sha256'],since=feed['collection_since_UTC'])
    # This is an installation-specific original set, not a dispatch leaf.
    references=plan['authority_references'];need(set(references)=={'question','owner','review'},'INSTALL_ORIGINAL_SET')
    collection=real.collection();originals={role:real.original(ref,collection) for role,ref in references.items()}
    q,o,r=[originals[role]['value'] for role in ('question','owner','review')]
    # A plan cannot contain its own hash in its embedded original references.
    # The signed subject is the exact plan body WITHOUT those late references.
    subject=dict(plan);subject.pop('authority_references');subject_pin=digest(canonical(subject))
    need(q['schema']=='SERVER_INSTALLATION_QUESTION_V2' and q['context']==ctx and q['subject_sha256']==subject_pin,
         'INSTALL_QUESTION')
    signed=instant(o['signed_at_UTC']);local=signed.astimezone(BRT)
    need(o['schema']=='SERVER_INSTALLATION_OWNER_V2' and o['subject_sha256']==subject_pin
         and o['question_sha256']==digest(originals['question']['raw']) and o['literal']=='Assino a instalação F6'
         and o['channel']=='REGISTRO_PELA_FABLE' and instant(originals['question']['created_UTC'])<=signed<start<=now
         and 7<=local.hour and (local.hour,local.minute,local.second,local.microsecond)<=(21,45,0,0)
         and signed<=instant(originals['owner']['created_UTC'])
         and (instant(originals['owner']['created_UTC'])-signed).total_seconds()<=60,'INSTALL_OWNER')
    need(r['schema']=='SERVER_INSTALLATION_REVIEW_V2' and r['context']==ctx and r['subject_sha256']==subject_pin
         and r['verdict']=='ACCEPTED_OWN_BYTES' and r['host']==plan['host']
         and r['source_files']==plan['source_files'],'INSTALL_REVIEW')
    roots=plan['roots'];need(set(roots)==ROOT_ROLES and len(set(roots.values()))==len(roots),'INSTALL_ROOT_SET')
    parent=Path(plan['claim_parent']);directory_chain(str(parent),plan['mode'])
    parent_store=PinnedDirectory(parent);opened={}
    try:
        PinnedDirectory.name(plan['claim_name'])
        for path in roots.values():
            p=Path(path);need(p.is_absolute() and p.name not in ('.','..') and not p.exists() and not p.is_symlink(),'INSTALL_ROOT_ALREADY_EXISTS')
            directory_chain(str(p.parent),plan['mode'])
        if plan['mode']=='REAL':
            wi=plan['witness_independence']
            need(Path(roots['journal']).parent.stat().st_dev!=Path(roots['witness']).parent.stat().st_dev
                 and wi['rollback_independent'] is True and wi['reviewed'] is True and sha(wi['review_sha256']),
                 'INSTALL_WITNESS_NOT_INDEPENDENT')
        def recheck():
            guard.recheck();at=instant(clock())
            need(now<=at<end and (at-now).total_seconds()<plan['budget_seconds'],'INSTALL_BUDGET')
        recheck()
        # A failed or partial installation is retained under this original claim.
        parent_store.create(plan['claim_name'],canonical({'schema':'SERVER_INSTALLATION_CLAIM_V2',
                'plan_sha256':pin,'subject_sha256':subject_pin,'context':ctx,'mode':plan['mode'],
                'owner_original_sha256':digest(originals['owner']['raw']),'reserved_UTC':now.isoformat()}))
        for role,path in roots.items():
            recheck();p=Path(path);os.mkdir(p,0o700);os.chmod(p,0o700)
            fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.fsync(fd)
            finally:os.close(fd)
            opened[role]=PinnedDirectory(p)
        seed={'schema':'SERVER_JOURNAL_INSTALLATION_ELECTION_V2','mode':plan['mode'],'context':ctx,'installation_plan_sha256':pin}
        if plan['mode']=='REAL':
            wi=plan['witness_independence']
            need(opened['journal'].identity['device']!=opened['witness'].identity['device']
                 and wi['rollback_independent'] is True and wi['reviewed'] is True and sha(wi['review_sha256']),
                 'INSTALL_WITNESS_NOT_INDEPENDENT')
        row={'sequence':0,'previous':'0'*64,'kind':'GENESIS','election':seed,'root_identity':opened['journal'].identity}
        raw=canonical(row);opened['journal'].create('events.jsonl',raw);opened['journal'].create('lock',b'F6_JOURNAL_LOCK_V2\n')
        anchor={'sequence':0,'digest':digest(raw)}
        opened['witness'].create('events.jsonl',canonical({'sequence':0,'previous':'0'*64,'kind':'WITNESS_GENESIS',
            'election':seed,'ledger_root':opened['journal'].identity,'ledger_anchor':anchor}))
        opened['witness'].create('lock',b'F6_WITNESS_LOCK_V2\n')
        journal_ids={label:{name:identity(os.stat(name,dir_fd=opened[role].fd,follow_symlinks=False))
                           for name in ('events.jsonl','lock')} for label,role in (('ledger','journal'),('witness','witness'))}
        for asset in plan['assets']:
            fields(asset,('role','name','source_path','sha256'),'INSTALL_ASSET_FIELDS')
            need(asset['role'] not in ('journal','witness'),'INSTALL_NO_JOURNAL_ASSET')
            recheck();raw,_=physical(asset['source_path']);need(digest(raw)==sha(asset['sha256']),'INSTALL_ASSET_PIN')
            opened[asset['role']].create(asset['name'],raw)
            os.chmod(asset['name'],0o400,dir_fd=opened[asset['role']].fd)
        registry=dict(plan['registry_template'],journal_identities=journal_ids,witness_independence=plan['witness_independence'])
        need(registry['schema']=='SERVER_NATIVE_REGISTRY_V2' and registry['context']==ctx,'INSTALL_REGISTRY_CONTEXT')
        opened['inputs'].create('registry.json',canonical(registry));os.chmod('registry.json',0o400,dir_fd=opened['inputs'].fd)
        recheck()
        receipt={'schema':'SERVER_INSTALLATION_PREPARED_V2','mode':plan['mode'],'context':ctx,'plan_sha256':pin,
            'subject_sha256':subject_pin,'journal_election':seed,'journal_identities':journal_ids,
            'roots':{k:d.identity for k,d in opened.items()},'registry_sha256':digest(canonical(registry)),
            'owner_original_sha256':digest(originals['owner']['raw']),'prepared_UTC':instant(clock()).isoformat(),
            'timers_installed':0,'operational_GO':False}
        opened['inputs'].create('installation-receipt.json',canonical(receipt));return receipt
    finally:
        for d in opened.values():d.close()
        parent_store.close()


def units(acceptance_raw,manifest_sha256,*,source_root,acceptance_path,executor_user,fixture=False):
    """Data only. Real installation/enablement requires its own approved act."""
    value=strict(acceptance_raw);need(canonical(value)==acceptance_raw and value['schema']=='SERVER_RUNTIME_ACCEPTANCE_V2'
        and value['accepted'] is True and value['spec']['mode']==('FIXTURE' if fixture else 'REAL'),'UNIT_OWN_ACCEPTANCE')
    ctx=context(value['spec']['context']);pin=digest(acceptance_raw);sha(manifest_sha256)
    need(re.fullmatch('[a-z_][a-z0-9_-]{0,31}|root',executor_user),'UNIT_EXECUTOR_NAME')
    need(pwd.getpwnam(executor_user).pw_uid==value['measurement']['euid'],'UNIT_EXECUTOR_UID')
    for path in (source_root,acceptance_path):
        need(re.fullmatch('/[A-Za-z0-9._/-]{1,220}',path) and '..' not in path.split('/'),'UNIT_PATH')
    result={}
    for slot,elected in value['election']['slots'].items():
        need(re.fullmatch('[A-Za-z0-9_-]{1,64}',slot),'UNIT_SLOT')
        need(elected['operation'] in value['allowed_operations'],'UNIT_OPERATION')
        start=instant(elected['start_UTC']);end=instant(elected['end_UTC'])
        need(start<end and 0<elected['budget_seconds']<=120 and elected['references'],'UNIT_WINDOW')
        name='c3po-f6-'+digest(canonical({'context':ctx,'slot':slot}))[:24]
        python=value['spec']['executables']['python']['path']
        need(re.fullmatch('/[A-Za-z0-9._/-]{1,220}',python),'UNIT_PYTHON_PATH')
        service=('''[Unit]\nDescription=F6 own finite slot\n[Service]\nType=oneshot\nUser=%s\nUMask=0077\nNoNewPrivileges=yes\nLimitCORE=0\nTimeoutStartSec=%s\nRestart=no\nExecStart=%s -I -S -B %s/service.py --manifest-sha256 %s --acceptance %s --acceptance-sha256 %s --slot %s\n'''
             %(executor_user,elected['budget_seconds']+15,python,source_root,manifest_sha256,acceptance_path,pin,slot)).encode()
        timer=('''[Unit]\nDescription=F6 one dated timer\n[Timer]\nOnCalendar=%s UTC\nAccuracySec=1s\nRandomizedDelaySec=0\nPersistent=false\nUnit=%s.service\n[Install]\nWantedBy=timers.target\n'''
               %(start.strftime('%Y-%m-%d %H:%M:%S'),name)).encode()
        result[name+'.service']=service;result[name+'.timer']=timer
    return result
