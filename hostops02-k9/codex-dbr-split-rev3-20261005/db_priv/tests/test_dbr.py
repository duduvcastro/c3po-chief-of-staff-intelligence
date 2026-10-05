def _set(path,value):
    def change(plan):
        target=plan
        for key in path[:-1]:target=target[key]
        target[path[-1]]=value
    return change

def _boot(host):host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'11111111-2222-3333-4444-555555555555\n')

def _revision(host):host.docker.images[0]['Config']['Labels']['org.opencontainers.image.revision']='0'*40

def _named(host):host.docker.containers.append(hostemu.container('hostops02-dbr-'+'0'*16,hostemu.BACKEND,hostemu.BACKEND,[],running=False))

def _remove(path):return lambda host:host.tree.remove(path)

def _add(path,**attributes):return lambda host:host.tree.add(path,**attributes)

def _tree(path,**attributes):
    def change(host):
        node=host.tree.get(path)
        for key,value in attributes.items():setattr(node,key,value)
    return change

def _row(**values):return dict({'state_sha':dbr.STATE_SHA,'version':3,'release_sha':dbr.RELEASE,'journal_head':'ab'},**values)

"""DBR on the emulated host with its pinned snippet executed against a model of the database: the complete run, every
host precheck (no container started), every plan refusal, every way the database answers, every way the snippet's
line can be wrong, and what never reaches a receipt. The snippet's own functions are also tested on real files and,
when a tree of the release is at hand, against the release's _authority()."""
import ast
import json
import os
from pathlib import Path
import re
import sys

import pytest

import dbr
import family as f
import hostemu

COMPLETE=('METADATA_ONLY_REQUIRES_REVIEW','DB_PREFLIGHT_ALL_OBSERVED_ALL_EXPECTATIONS_MET',None)

def test_static_op_is_the_composition_of_its_three_readable_pieces_and_the_snippet_hash_is_pinned():
    sys.path.insert(0,str(dbr.DIRECTORY))
    try:import make_op
    finally:sys.path.remove(str(dbr.DIRECTORY))
    assert (dbr.DIRECTORY/'op.py').read_text()==make_op.compose()
    m=dbr.K().m;assert m.DBR_SNIPPET==(dbr.DIRECTORY/'snippet.py').read_bytes() and m.DBR_SNIPPET_SHA256==f.sha(m.DBR_SNIPPET)
    assert m.SCOPE['snippet']['sha256']==m.DBR_SNIPPET_SHA256



# ---------------------------------------------------------------- the database answers
DATABASE=[('no row, none expected',lambda d:None,{'expected':{'epoch_rows':0,'binding_committed':False}},None,None),
          ('row expected, none there',lambda d:None,{'expected':{'epoch_rows':1,'binding_committed':None}},'EPOCH_ROW_COUNT_NOT_AS_SIGNED',None),
          ('row there, none expected',lambda d:setattr(d,'epoch_row',_row()),{'expected':{'epoch_rows':0,'binding_committed':None}},'EPOCH_ROW_COUNT_NOT_AS_SIGNED',None),
          ('another release',lambda d:setattr(d,'epoch_row',_row(release_sha='6e'*32)),{},'EPOCH_RELEASE_SHA_MISMATCH',None),
          ('zero version with a journal',lambda d:setattr(d,'epoch_row',_row(version=0,journal_head='ab')),{},'EPOCH_ZERO_VERSION_JOURNAL',None),
          ('zero version, empty journal',lambda d:setattr(d,'epoch_row',_row(version=0,journal_head='')),{},None,None),
          ('binding expected, none',lambda d:setattr(d,'epoch_row',_row()),{'expected':{'epoch_rows':1,'binding_committed':True}},'BINDING_NOT_AS_SIGNED',None),
          ('binding there, none expected',lambda d:(setattr(d,'epoch_row',_row()),d.bindings.update({'2026-10-05':dbr.BINDING_SHA}),d.journal.update({'2026-10-05':1})),
           {'expected':{'epoch_rows':1,'binding_committed':False}},'BINDING_NOT_AS_SIGNED',None),
          ('binding without journal',lambda d:(setattr(d,'epoch_row',_row()),d.bindings.update({'2026-10-05':dbr.BINDING_SHA})),{},'BINDING_AND_JOURNAL_DISAGREE',None),
          ('journal without binding',lambda d:(setattr(d,'epoch_row',_row()),d.journal.update({'2026-10-05':1})),{},'BINDING_AND_JOURNAL_DISAGREE',None),
          ('binding of another session',lambda d:(setattr(d,'epoch_row',_row()),d.bindings.update({'2026-10-06':dbr.BINDING_SHA}),d.journal.update({'2026-10-06':1})),
           {'expected':{'epoch_rows':1,'binding_committed':False}},None,None),
          ('reader cannot select the epochs',lambda d:setattr(d,'reader_can_read',False),{},'QUERY_UNAVAILABLE_BINDING','42501'),
          ('reader unreachable',lambda d:setattr(d,'reader_down',True),{},'QUERY_UNAVAILABLE_BINDING','08001'),
          ('emitter password refused',lambda d:setattr(d,'emitter_password','y'*64),{},'QUERY_UNAVAILABLE_EMITTER','28P01'),
          ('emitter not restricted',lambda d:setattr(d,'emitter_preconditions','CAUSAL_ROLE_NOT_RESTRICTED'),{},'QUERY_UNAVAILABLE_EMITTER',None),
          ('emitter triggers',lambda d:setattr(d,'emitter_preconditions','CAUSAL_APPEND_ONLY_TRIGGERS_INVALID'),{},'QUERY_UNAVAILABLE_EMITTER',None),
          ('emitter identity',lambda d:setattr(d,'emitter_identity',('c3po','c3po_v2_causal_emitter','c3po','origin','on')),{},'EMITTER_IDENTITY_NOT_AS_REQUIRED',None),
          ('emitter replica role',lambda d:setattr(d,'emitter_identity',('c3po','c3po_v2_causal_emitter','c3po_v2_causal_emitter','replica','on')),{},'EMITTER_IDENTITY_NOT_AS_REQUIRED',None),
          ('old libpq',lambda d:setattr(d,'libpq',150004),{},'QUERY_UNAVAILABLE_EMITTER',None),
          ('dsn names another host',lambda d:None,{},'RISK_URL_HOST_IS_NOT_DB',None),
          ('two rows',lambda d:(setattr(d,'epoch_row',_row()),setattr(d,'count',2)),{},'QUERY_UNAVAILABLE_EPOCH_ROW',None),
          ('emitter current user',lambda d:setattr(d,'emitter_identity',('c3po','c3po','c3po','origin','on')),{},'EMITTER_IDENTITY_NOT_AS_REQUIRED',None),
          ('binding sha not a hash',lambda d:(setattr(d,'epoch_row',_row()),d.bindings.update({'2026-10-05':'not-a-hash'}),d.journal.update({'2026-10-05':1})),{},'QUERY_UNAVAILABLE_BINDING',None)]


# ---------------------------------------------------------------- the host before the container
HOST=[('fourth entry',_add(dbr.SECRETS+'/extra.env',kind='file',mode=0o600),'SECRETS_DIRECTORY_NOT_AS_PLACED'),
      ('risk file absent',_remove(dbr.SECRETS+'/risk-db.env'),'CREDENTIAL_ABSENT'),
      ('risk file 0640',_tree(dbr.SECRETS+'/risk-db.env',mode=0o640),'CREDENTIAL_NOT_PRIVATE'),
      ('risk file of uid 1000',_tree(dbr.SECRETS+'/risk-db.env',uid=1000),'CREDENTIAL_NOT_PRIVATE'),
      ('risk file group 5',_tree(dbr.SECRETS+'/risk-db.env',gid=5),'CREDENTIAL_NOT_PRIVATE'),
      ('risk file two links',_tree(dbr.SECRETS+'/risk-db.env',nlink=2),'CREDENTIAL_NOT_PRIVATE'),
      ('risk file a link',lambda host:(host.tree.remove(dbr.SECRETS+'/risk-db.env'),host.tree.add(dbr.SECRETS+'/risk-db.env',kind='symlink',mode=0o777)),'CREDENTIAL_NOT_PRIVATE'),
      ('emitter a file',lambda host:(host.tree.remove(dbr.SECRETS+'/emitter'),host.tree.add(dbr.SECRETS+'/emitter',kind='file',mode=0o700)),'CREDENTIAL_NOT_PRIVATE'),
      ('emitter 0750',_tree(dbr.SECRETS+'/emitter',mode=0o750),'CREDENTIAL_NOT_PRIVATE'),
      ('emitter absent',lambda host:host.tree.remove(dbr.SECRETS+'/emitter'),'CREDENTIAL_ABSENT'),
      ('password absent',_remove(dbr.SECRETS+'/emitter/password'),'CREDENTIAL_ABSENT'),
      ('password 0644',_tree(dbr.SECRETS+'/emitter/password',mode=0o644),'CREDENTIAL_NOT_PRIVATE'),
      ('password two links',_tree(dbr.SECRETS+'/emitter/password',nlink=2),'CREDENTIAL_NOT_PRIVATE'),
      ('password of uid 1000',_tree(dbr.SECRETS+'/emitter/password',uid=1000),'CREDENTIAL_NOT_PRIVATE'),
      ('second file beside the password',_add(dbr.SECRETS+'/emitter/password.old',kind='file',mode=0o600),'EMITTER_DIRECTORY_NOT_AS_PLACED'),
      ('image revision',_revision,'IMAGE_REVISION_MISMATCH'),
      ('container name taken',_named,'DBR_CONTAINER_NAME_PRESENT'),
      ('another boot',_boot,'EVIDENCE_FROM_EARLIER_BOOT')]




# ---------------------------------------------------------------- the container's end and its line
def _line(mutate):
    def on_run_factory(database):
        inner=dbr.container(database)
        def on_run(call):
            code,raw=inner(call);value=json.loads(raw);mutate(value)
            return code,(json.dumps(value)+'\n').encode() if not isinstance(value,bytes) else value
        return on_run
    return on_run_factory
LINES=[('extra key',lambda v:v.update(extra=1)),('schema',lambda v:v.update(schema='OTHER')),('queries',lambda v:v.update(queries=4)),
       ('not done',lambda v:v.update(status='REFUSED')),('rows two',lambda v:v['epoch_row'].update(rows=2)),
       ('rows a bool',lambda v:v['epoch_row'].update(rows=True)),('state sha not hex',lambda v:v['epoch_row'].update(state_sha='x'*64)),
       ('role a string',lambda v:v['epoch_row'].update(role_restricted='yes')),('equal said without a row',lambda v:v['epoch_row'].update(release_sha_equal=True)),
       ('binding of another session',lambda v:v['binding'].update(session='2026-10-06')),
       ('binding sha while not committed',lambda v:v['binding'].update(binding_sha256='b1'*32)),
       ('committed without a sha',lambda v:v['binding'].update(committed=True)),('negative journal',lambda v:v['binding'].update(journal_entries=-1)),
       ('emitter value not a bool',lambda v:v['emitter'].update(authority_passed=1)),('emitter extra key',lambda v:v['emitter'].update(password='x')),
       ('unavailable with text',lambda v:v.update(risk_url={'status':'UNAVAILABLE','code':'X','detail':'password=x'})),
       ('code not a constant',lambda v:v.update(emitter_password={'status':'UNAVAILABLE','code':'not a code'})),
       ('sqlstate not a state',lambda v:v.update(emitter={'status':'UNAVAILABLE','code':'X','sqlstate':'28p01x'})),
       ('status other',lambda v:v['binding'].update(status='PARTIAL')),
       ('complete part with an extra boolean',lambda v:v['emitter'].update(superuser=True)),
       ('complete file part with an extra member',lambda v:v['risk_url'].update(value=True)),
       ('host flag not a boolean',lambda v:v['risk_url'].update(host_is_db='db'))]





# ---------------------------------------------------------------- the plan
PLAN=[(('session',),'2026-10-10','SESSION_NOT_OF_THE_EPOCH'),(('session',),'2026-10-04','SESSION_NOT_OF_THE_EPOCH'),(('session',),None,'SESSION_NOT_OF_THE_EPOCH'),
      (('release_receipt_sha256',),'0'*64,'RELEASE_SHA_INVALID'),(('release_receipt_sha256',),'5D'*32,'RELEASE_SHA_INVALID'),
      (('expected','epoch_rows'),2,'EXPECTATION_INVALID'),(('expected','epoch_rows'),True,'EXPECTATION_INVALID'),(('expected','epoch_rows'),1.0,'EXPECTATION_INVALID'),
      (('expected','binding_committed'),1,'EXPECTATION_INVALID'),(('expected','other'),None,'EXPECTATION_INVALID'),
      (('image_id',),'c3po/backend:production','IMAGE_PLAN_INVALID'),(('image_revision',),'dd4ec4bb','IMAGE_PLAN_INVALID'),
      (('secrets_chain',-1,'mode'),0o750,'SECRETS_CHAIN_NOT_ROOT_0700'),(('secrets_chain',-2,'gid'),5,'SECRETS_CHAIN_NOT_ROOT_0700'),
      (('secrets_chain',3,'mode'),0o775,'CHAIN_ROW_UNSAFE'),(('secrets_chain',),None,'CHAIN_ROW_INVALID'),(('secrets_chain',-1,'path'),'/var/lib/c3po/x','CHAIN_ROW_INVALID'),
      (('evidence_boot_id_sha256',),'0'*64,'EVIDENCE_BOOT_UNBOUND')]


def test_effects_are_exactly_what_the_signers_see():
    for mode in ('PRIV',):
        docs,host=dbr.case(mode=mode);m=docs.k.m;effects=m.effects_of(docs.plan);queries=mode=='QUERIES'
        assert sorted(effects)==sorted(['operation','mode','secrets','image_id','image_revision','network','binds','command','snippet_sha256','epoch','session',
                                        'release_receipt_sha256','expected','priv_receipt','queries','evidence_boot_id_sha256','writes','containers_run','activation'])
        assert effects['network']=='c3po_c3po_internal' and effects['epoch']=='R2D2-V2-SHADOW-2026-10-05' and effects['queries']==(3 if queries else 0)
        binds=[{'source':dbr.SECRETS+'/risk-db.env','target':'/c3po-dbr-risk-db.env','read_only':True}]
        if queries:binds.append({'source':dbr.SECRETS+'/emitter','target':'/c3po-dbr-emitter','read_only':True})
        assert effects['binds']==binds and effects['mode']==mode
        assert effects['command']==(['python','-I','-B','-','QUERIES','/c3po-dbr-risk-db.env','/c3po-dbr-emitter/password',dbr.EPOCH,'2026-10-05',dbr.RELEASE]
                                    if queries else ['python','-I','-B','-','PRIV','/c3po-dbr-risk-db.env'])
        assert effects['snippet_sha256']==m.DBR_SNIPPET_SHA256 and (effects['writes'],effects['containers_run'],effects['activation'])==(0,1,False)
        assert effects['secrets']['path']==dbr.SECRETS and effects['image_id']==hostemu.BACKEND and effects['image_revision']==hostemu.REVISION
        if queries:
            assert effects['session']=='2026-10-05' and effects['release_receipt_sha256']==dbr.RELEASE and effects['expected']=={'epoch_rows':None,'binding_committed':None}
            assert effects['priv_receipt']==dbr.priv_receipt()
        else:assert (effects['session'],effects['release_receipt_sha256'],effects['expected'],effects['priv_receipt'])==(None,None,None,None)
        assert effects['evidence_boot_id_sha256']==f.BOOT_SHA and m.EVIDENCE_OPERATIONS==('GO_WRITE_HOSTOPS02_K3K9_SECRETS_01',)
        assert m.success_of(docs.plan)==('DB_PREFLIGHT_ALL_OBSERVED_ALL_EXPECTATIONS_MET' if queries else 'DB_READER_PRIVILEGES_PROVEN')
    assert m.DBR_RUN_PREFIX==['run','--rm','-i','--pull','never','--init','--user','0:0','--network','c3po_c3po_internal','--read-only','--cap-drop','ALL',
                              '--security-opt','no-new-privileges'] and m.COMMANDS['query']['class']=='RUN' and m.COMMANDS['query']['kind']=='CONTAINER'

# ---------------------------------------------------------------- the snippet's own functions
def test_snippet_files_are_read_without_following_a_link_and_only_when_private(tmp_path):
    snippet=dbr.snippet_module();target=tmp_path/'real';target.write_bytes(dbr.RISK_FILE);os.chmod(target,0o600)
    os.symlink(str(target),str(tmp_path/'link'))
    with pytest.raises(ValueError,match='FILE_UNAVAILABLE'):snippet.private_bytes(str(tmp_path/'link'),4096)
    with pytest.raises(ValueError,match='FILE_UNAVAILABLE'):snippet.private_bytes(str(tmp_path/'absent'),4096)
    if os.geteuid()!=0:
        with pytest.raises(ValueError,match='FILE_NOT_PRIVATE'):snippet.private_bytes(str(target),4096)
    else:assert snippet.private_bytes(str(target),4096)==dbr.RISK_FILE

@pytest.mark.parametrize('raw,code',[(b'C3PO_R2D2_RISK_DATABASE_URL=postgresql://c3po:x@db/c3po\n','RISK_URL_NOT_THE_RESTRICTED_READER'),
                                     (b'OTHER=postgresql://c3po_v2_risk_reader:x@db/c3po\n','RISK_URL_FORMAT'),
                                     (b'C3PO_R2D2_RISK_DATABASE_URL=postgresql://c3po_v2_risk_reader:x@db/c3po\n\n','RISK_URL_FORMAT'),
                                     (b'C3PO_R2D2_RISK_DATABASE_URL=postgresql://c3po_v2_risk_reader:x y@db/c3po\n','RISK_URL_NOT_THE_RESTRICTED_READER'),
                                     (b'C3PO_R2D2_RISK_DATABASE_URL=postgresql://c3po_v2_risk_reader:\n','RISK_URL_NOT_THE_RESTRICTED_READER')])
def test_snippet_risk_url_grammar(raw,code):
    with pytest.raises(ValueError,match=code):dbr.snippet_module().risk_dsn(raw)
    assert dbr.snippet_module().risk_dsn(dbr.RISK_FILE)=='postgresql://c3po_v2_risk_reader:'+dbr.RISK_CANARY+'@db:5432/c3po'


@pytest.mark.parametrize('arguments',[[],['OTHER','a'],['PRIV'],['PRIV','a','b'],['QUERIES','a','b','R2D2-V2-SHADOW-2026-10-05','2026-10-05'],
                                      ['QUERIES','a','b','OTHER','2026-10-05','5d'*32],['QUERIES','a','b','R2D2-V2-SHADOW-2026-10-05','2026-10-10','5d'*32],
                                      ['QUERIES','a','b','R2D2-V2-SHADOW-2026-10-05','2026-10-05','5D'*32],['a','b','R2D2-V2-SHADOW-2026-10-05','2026-10-05','5d'*32]])
def test_snippet_refuses_arguments_outside_the_grammar_before_reading_anything(arguments):
    def read(path,limit):raise AssertionError('read before the arguments were checked')
    out=dbr.snippet_module().main(arguments,None,None,read=read)
    assert out.pop('mode',None) in (None,'PRIV','QUERIES') and out=={'schema':'HOSTOPS02_DBR_SNIPPET_V2','status':'REFUSED','code':'ARGUMENTS'}


# ---------------------------------------------------------------- query 2 against the release's own _authority()
EMITTER_PIN='9b52751adfc10f2cad17ceb3f7dc1906988c688e8a1b77f20bd9f82f6a29b60d'      # c3po/backend/app/r2d2_v2_causal_emitter.py at dd4ec4bb

class ReleaseConnection:
    """Answers the three SELECTs of the release's _authority() as a database that meets every precondition would."""
    def __init__(self,body,triggers_enabled='O'):self.autocommit=False;self.body=body;self.enabled=triggers_enabled;self.sql=[]
    def execute(self,sql,parameters=None):
        self.sql.append(sql);self.parameters=parameters;return self
    def fetchone(self):
        sql=self.sql[-1]
        if 'pg_catalog.pg_roles' in sql:return (True,True,True,True,True)
        if sql.startswith('SELECT current_database()'):return ('c3po','c3po_v2_causal_emitter','c3po_v2_causal_emitter','origin','on')
        return None
    def fetchall(self):
        sql=self.sql[-1]
        if 'pg_catalog.pg_class' in sql and 'pg_trigger' not in sql:return [(name,True,True,True,True,True,True,True) for name in self.parameters[0]]
        if 'pg_trigger' in sql:
            names,triggers=self.parameters
            return [(name,trigger,self.enabled in ('O','A'),True,True,True,self.body,True) for name,trigger in zip(names,triggers)]
        raise AssertionError(sql[:60])
    def rollback(self):pass
    def close(self):pass









ROWS=['/','/var','/var/lib','/var/lib/c3po','/var/lib/c3po/r2d2-v2-k9-20261005','/var/lib/c3po/r2d2-v2-k9-20261005/secrets']
@pytest.mark.parametrize('index',range(6))
@pytest.mark.parametrize('field,value',[('uid',1000),('mode',0o775),('mode',0o757),('mode',0o1777)])
def test_every_component_above_the_bind_sources_must_be_root_controlled(index,field,value):
    """Decision 6: the bind sources and every ancestor root-owned and closed to group and other writes; no open root."""
    docs,host=dbr.case();row=docs.plan['secrets_chain'][index];assert row['path']==ROWS[index];row[field]=value;docs.chain()
    assert f.refusal(docs.authenticate) in ('CHAIN_ROW_UNSAFE','SECRETS_CHAIN_NOT_ROOT_0700')

@pytest.mark.parametrize('path',ROWS[1:])
def test_a_component_given_to_another_owner_on_the_host_holds_the_container_back(path):
    docs,host=dbr.case();host.tree.get(path).uid=1000;receipt=run(docs,host)
    assert receipt['items']['secrets']=={'status':'UNAVAILABLE','code':'PARENT_IDENTITY_MISMATCH'} and host.container_runs()==[]

def test_a_bind_source_replaced_after_the_precheck_is_proved_again_and_holds_the_container_back():
    docs,host=dbr.case();seen=[0]
    def hook(host_,name,detail,calls):
        if name=='run' and detail[0][1:3]==['ps','-a']:
            seen[0]+=1
            if seen[0]==1:host.tree.get(dbr.SECRETS+'/emitter').ino=8888
    host.hook=hook;receipt=run(docs,host)
    assert receipt['items']['query']['code']=='PARENT_REPLACED' and host.container_runs()==[]


# ---------------------------------------------------------------- mode PRIV (its own request, GO and A2 line: Codex E1-11)
PRIV_COMPLETE=('METADATA_ONLY_REQUIRES_REVIEW','DB_READER_PRIVILEGES_PROVEN',None)
def test_priv_reads_only_the_privileges_with_only_the_reader_file_bound():
    docs,host=dbr.case(mode='PRIV');m=docs.k.m;receipt=run(docs,host);snippet=dbr.snippet_module()
    assert outcome(receipt)==PRIV_COMPLETE and f.sealed(receipt) and dbr.clean(receipt)
    argv=host.container_runs()[0]['argv'][1:]
    assert argv==m.DBR_RUN_PREFIX+['--name','hostops02-dbr-priv-'+docs.go16(),'--mount','type=bind,source=%s/risk-db.env,target=/c3po-dbr-risk-db.env,readonly'%dbr.SECRETS,
                                   hostemu.BACKEND,'python','-I','-B','-','PRIV','/c3po-dbr-risk-db.env']
    line=receipt['items']['query']['line']
    assert line['reader_privileges']=={'status':'COMPLETE','role_is_the_restricted_reader':True,'role_restricted':True,'transaction_read_only':True,
                                       'database_connect':True,'schema_usage':True,'epochs_select':True,'journal_select':True}
    assert sorted(line)==['mode','reader_privileges','risk_url']
    assert [sql for _,sql,_ in host.database.statements]==[snippet.BEGIN_READER,snippet.TIMEOUT,snippet.PRIVILEGE_SQL,'ROLLBACK'],'one catalog read, rolled back'
    assert len(host.database.connections)==1 and host.database.connections[0]['conninfo'] is not None,'only the reader connects'
    assert all(type(value) is bool for key,value in line['reader_privileges'].items() if key!='status'),'booleans only'

@pytest.mark.parametrize('change,code,sqlstate',[(lambda d:d.privileges.update(epochs_select=False),'READER_PRIVILEGE_NOT_PROVEN',None),
                                                 (lambda d:d.privileges.update(journal_select=False),'READER_PRIVILEGE_NOT_PROVEN',None),
                                                 (lambda d:d.privileges.update(connect=False),'READER_PRIVILEGE_NOT_PROVEN',None),
                                                 (lambda d:d.privileges.update(usage=False),'READER_PRIVILEGE_NOT_PROVEN',None),
                                                 (lambda d:setattr(d,'reader_role','c3po'),'READER_PRIVILEGE_NOT_PROVEN',None),
                                                 (lambda d:setattr(d,'reader_restricted',False),'READER_PRIVILEGE_NOT_PROVEN',None),
                                                 (lambda d:setattr(d,'session_role','c3po'),'READER_PRIVILEGE_NOT_PROVEN',None),
                                                 (lambda d:setattr(d,'read_only','off'),'READER_PRIVILEGE_NOT_PROVEN',None),
                                                 (lambda d:setattr(d,'privilege_error','42P01'),'QUERY_UNAVAILABLE_READER_PRIVILEGES','42P01'),
                                                 (lambda d:setattr(d,'reader_down',True),'QUERY_UNAVAILABLE_READER_PRIVILEGES','08001')])
def test_priv_reports_every_privilege_it_cannot_prove(change,code,sqlstate):
    docs,host=dbr.case(mode='PRIV');change(host.database);receipt=run(docs,host)
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and code in receipt['findings'] and receipt['outcome']=='DB_PRIV_OBSERVED_EXPECTATIONS_NOT_MET'
    line=receipt['items']['query']['line']
    if sqlstate:assert line['reader_privileges']['sqlstate']==sqlstate
    assert not [sql for _,sql,_ in host.database.statements if 'r2d2_v2_shadow_epochs e' in sql or 'daily_capacity' in sql],'PRIV never queries a table'
    assert dbr.clean(receipt)

@pytest.mark.parametrize('label,mutate',[('privilege not a boolean',lambda v:v['reader_privileges'].update(schema_usage=1)),
                                         ('privilege missing',lambda v:v['reader_privileges'].pop('database_connect')),
                                         ('privilege extra',lambda v:v['reader_privileges'].update(superuser=False)),
                                         ('a query part in a PRIV line',lambda v:v.update(epoch_row={'status':'COMPLETE'})),
                                         ('mode of the line',lambda v:v.update(mode='QUERIES')),
                                         ('schema',lambda v:v.update(schema='HOSTOPS02_DBR_SNIPPET_V1')),
                                         ('privileges missing',lambda v:v.pop('reader_privileges'))])
def test_every_member_of_a_priv_line_is_checked(label,mutate):
    docs,host=dbr.case(mode='PRIV');host.docker.on_run=_line(mutate)(host.database);receipt=run(docs,host)
    assert receipt['items']['query']=={'status':'UNAVAILABLE','code':'SNIPPET_LINE_INVALID'}


# ---------------------------------------------------------------- QUERIES requires a PRIV receipt of the same boot and day that proved SELECT

@pytest.mark.parametrize('key,value',[('session','2026-10-05'),('release_receipt_sha256','5d'*32),('expected',{'epoch_rows':None,'binding_committed':None}),
                                      ('priv_receipt',{'x':1})])
def test_a_priv_plan_carries_no_member_of_the_queries(key,value):
    docs,host=dbr.case(mode='PRIV');docs.plan[key]=value;docs.chain();assert f.refusal(docs.authenticate)=='PRIV_PLAN_CARRIES_QUERIES_MEMBERS'

@pytest.mark.parametrize('value',[None,'QUERY','priv',3])
def test_the_mode_is_one_of_two(value):
    docs,host=dbr.case();docs.plan['mode']=value;docs.chain();assert f.refusal(docs.authenticate)=='MODE_INVALID'




def run(docs,host,**options):return docs.run(host,**options)
def outcome(receipt):return (receipt["status"],receipt["outcome"],receipt["code"])
