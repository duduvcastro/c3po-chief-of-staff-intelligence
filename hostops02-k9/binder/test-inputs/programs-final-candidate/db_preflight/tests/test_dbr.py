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

def run(docs,host,**options):return docs.run(host,**options)
def outcome(receipt):return (receipt['status'],receipt['outcome'],receipt['code'])
COMPLETE=('METADATA_ONLY_REQUIRES_REVIEW','DB_PREFLIGHT_ALL_OBSERVED_ALL_EXPECTATIONS_MET',None)

def test_static_op_is_the_composition_of_its_three_readable_pieces_and_the_snippet_hash_is_pinned():
    sys.path.insert(0,str(dbr.DIRECTORY))
    try:import make_op
    finally:sys.path.remove(str(dbr.DIRECTORY))
    assert (dbr.DIRECTORY/'op.py').read_text()==make_op.compose()
    m=dbr.K().m;assert m.DBR_SNIPPET==(dbr.DIRECTORY/'snippet.py').read_bytes() and m.DBR_SNIPPET_SHA256==f.sha(m.DBR_SNIPPET)
    assert m.SCOPE['snippet']['sha256']==m.DBR_SNIPPET_SHA256

def test_complete_run_starts_one_container_with_exactly_the_signed_argv_and_reads_the_line():
    docs,host=dbr.case();m=docs.k.m;host.database.epoch_row={'state_sha':dbr.STATE_SHA,'version':3,'release_sha':dbr.RELEASE,'journal_head':'ab'}
    host.database.bindings['2026-10-05']=dbr.BINDING_SHA;host.database.journal['2026-10-05']=1
    receipt=run(docs,host);assert outcome(receipt)==COMPLETE and f.sealed(receipt) and dbr.clean(receipt)
    runs=host.container_runs();assert len(runs)==1
    argv=runs[0]['argv'][1:];name='hostops02-dbr-'+docs.go16()
    assert argv==m.DBR_RUN_PREFIX+['--name',name,'--mount','type=bind,source=%s/risk-db.env,target=/c3po-dbr-risk-db.env,readonly'%dbr.SECRETS,
                                   '--mount','type=bind,source=%s/emitter,target=/c3po-dbr-emitter,readonly'%dbr.SECRETS,hostemu.BACKEND,
                                   'python','-I','-B','-','QUERIES','/c3po-dbr-risk-db.env','/c3po-dbr-emitter/password',dbr.EPOCH,'2026-10-05',dbr.RELEASE]
    assert runs[0]['stdin']==m.DBR_SNIPPET and runs[0]['seconds']==40 and runs[0]['docker_config'] is None and runs[0]['variables']=={}
    line=receipt['items']['query']['line']
    assert sorted(line)==['binding','emitter','emitter_password','epoch_row','mode','queries','risk_url'] and line['queries']==3 and line['mode']=='QUERIES'
    assert line['epoch_row']=={'status':'COMPLETE','rows':1,'state_sha':dbr.STATE_SHA,'version':3,'release_sha_equal':True,'journal_head_empty':False}
    assert line['binding']=={'status':'COMPLETE','session':'2026-10-05','committed':True,'binding_sha256':dbr.BINDING_SHA,'journal_entries':1}
    assert line['emitter']=={'status':'COMPLETE','authority_passed':True,'database_is_c3po':True,'current_user_is_the_emitter':True,
                             'session_user_equal':True,'replication_role_origin':True,'transaction_read_only':True}
    assert receipt['items']['containers_after']['dbr_container_present'] is False and receipt['containers_run']==1
    assert host.mutating()==[] and receipt['mutating_calls']['issued']==0
    # the credentials are never opened or read by this process: lstat only
    for path in (dbr.SECRETS+'/risk-db.env',dbr.SECRETS+'/emitter/password',dbr.SECRETS+'/provider.env'):
        assert not [entry for entry in host.log if entry[0] in ('open','read') and entry[1]==path]
    assert [entry for entry in host.log if entry[0]=='lstat' and entry[1]==dbr.SECRETS+'/risk-db.env']

def test_every_statement_is_one_of_the_fixed_reads_in_a_read_only_transaction_that_is_rolled_back():
    docs,host=dbr.case();run(docs,host);m=docs.k.m;snippet=dbr.snippet_module()
    statements=host.database.statements;sqls=[sql for _,sql,_ in statements]
    reader=[sql for user,sql,_ in statements if user=='c3po_v2_risk_reader'];emitter=[sql for user,sql,_ in statements if user=='c3po_v2_causal_emitter']
    assert reader==[snippet.BEGIN_READER,snippet.TIMEOUT,snippet.EPOCH_ROW_SQL,snippet.BINDING_SQL,'ROLLBACK'],'exactly queries 1 and 3, one snapshot, no privilege read'
    assert emitter==[snippet.BEGIN_EMITTER,snippet.TIMEOUT,'AUTHORITY_THREE_SELECTS',snippet.IDENTITY_SQL,'ROLLBACK']
    for sql in (snippet.EPOCH_ROW_SQL,snippet.BINDING_SQL,snippet.IDENTITY_SQL):
        assert sql.startswith('SELECT ') and not re.search(r'\b(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|GRANT|REVOKE|TRUNCATE|COPY|LOCK|ROLE|nextval|setval)\b',sql,re.I)
    assert len(host.database.connections)==2 and all(connection['application_name']=='hostops02-dbr' for connection in host.database.connections)
    texts=[value for name,value in vars(snippet).items() if type(value) is str and name!='__doc__' and name.isupper()]
    assert [text for text in texts if re.search(r"\b(?:INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|GRANT|REVOKE|TRUNCATE|SET ROLE|SET SESSION)\b",text)]==[]

# ---------------------------------------------------------------- the database answers
def _row(**values):return dict({'state_sha':dbr.STATE_SHA,'version':3,'release_sha':dbr.RELEASE,'journal_head':'ab'},**values)
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

@pytest.mark.parametrize('label,change,plan,code,sqlstate',DATABASE,ids=[row[0] for row in DATABASE])
def test_every_answer_of_the_database_is_judged_and_nothing_secret_leaves(label,change,plan,code,sqlstate):
    docs,host=dbr.case(**plan);change(host.database)
    if label=='dsn names another host':host.tree.get(dbr.SECRETS+'/risk-db.env').content=bytearray(dbr.RISK_FILE.replace(b'@db:',b'@127.0.0.1:'));host.database.dsn=host.database.dsn.replace('@db:','@127.0.0.1:')
    receipt=run(docs,host)
    if code is None:assert outcome(receipt)==COMPLETE,receipt.get('findings')
    else:
        assert (receipt['status'],receipt['outcome'])==('PARTIAL_METADATA_REQUIRES_REVIEW','DB_PREFLIGHT_OBSERVED_EXPECTATIONS_NOT_MET') and code in receipt['findings']
    line=receipt['items']['query']['line']
    if sqlstate is not None:assert sqlstate in json.dumps(line)
    assert dbr.clean(receipt) and 'password authentication' not in f.line(receipt).decode() and 'permission denied' not in f.line(receipt).decode()
    if label=='emitter not restricted':assert line['emitter']=={'status':'UNAVAILABLE','code':'CAUSAL_ROLE_NOT_RESTRICTED'}
    if label=='old libpq':assert line['emitter']=={'status':'UNAVAILABLE','code':'LIBPQ16_REQUIRED'}
    if label=='reader cannot select the epochs':assert {'QUERY_UNAVAILABLE_EPOCH_ROW','QUERY_UNAVAILABLE_BINDING'}<=set(receipt['findings']) and line['emitter']['status']=='COMPLETE'
    if label=='two rows':assert line['epoch_row']=={'status':'UNAVAILABLE','code':'EPOCH_ROW_COUNT'}
    if label=='binding sha not a hash':assert line['binding']=={'status':'UNAVAILABLE','code':'BINDING_SHA_FORMAT'}

# ---------------------------------------------------------------- the host before the container
def _tree(path,**attributes):
    def change(host):
        node=host.tree.get(path)
        for key,value in attributes.items():setattr(node,key,value)
    return change
def _add(path,**attributes):return lambda host:host.tree.add(path,**attributes)
def _remove(path):return lambda host:host.tree.remove(path)
def _named(host):host.docker.containers.append(hostemu.container('hostops02-dbr-'+'0'*16,hostemu.BACKEND,hostemu.BACKEND,[],running=False))
def _revision(host):host.docker.images[0]['Config']['Labels']['org.opencontainers.image.revision']='0'*40
def _boot(host):host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'11111111-2222-3333-4444-555555555555\n')
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

@pytest.mark.parametrize('label,change,code',HOST,ids=[row[0] for row in HOST])
def test_every_host_precondition_holds_the_container_back_and_is_a_finding(label,change,code):
    docs,host=dbr.case()
    if label=='container name taken':
        name='hostops02-dbr-'+docs.go16();change=lambda host:host.docker.containers.append(hostemu.container(name,hostemu.BACKEND,hostemu.BACKEND,[],running=False))
    change(host);receipt=run(docs,host)
    assert (receipt['status'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW',code) or code in receipt['findings'],receipt['findings']
    assert host.container_runs()==[] and receipt['items']['query']=={'status':'UNAVAILABLE','code':'NOT_STARTED_PRECONDITIONS'} and dbr.clean(receipt)

def test_secrets_directory_not_as_signed_is_unavailable_and_no_container_starts():
    docs,host=dbr.case();host.tree.get(dbr.SECRETS).mode=0o750;receipt=run(docs,host)
    assert receipt['items']['secrets']=={'status':'UNAVAILABLE','code':'PARENT_IDENTITY_MISMATCH'} and host.container_runs()==[]
    assert (receipt['status'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW','OBSERVATION_INCOMPLETE')

def test_an_image_that_is_not_there_holds_the_container_back():
    docs,host=dbr.case();host.docker.images.pop(0);receipt=run(docs,host)
    assert receipt['items']['image']['code']=='COMMAND_FAILED' and host.container_runs()==[]

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

@pytest.mark.parametrize('label,mutate',LINES,ids=[row[0] for row in LINES])
def test_every_member_of_the_line_is_checked(label,mutate):
    docs,host=dbr.case();host.docker.on_run=_line(mutate)(host.database);receipt=run(docs,host)
    assert receipt['items']['query']=={'status':'UNAVAILABLE','code':'SNIPPET_LINE_INVALID'} and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
    assert receipt['items']['containers_after']['status']=='COMPLETE','a container that ran is looked for afterwards'

@pytest.mark.parametrize('result,code',[((3,b'{"code":"IMPORT_FAILED","schema":"HOSTOPS02_DBR_SNIPPET_V1","status":"REFUSED"}\n'),'QUERY_RUN_FAILED'),
                                        ((125,b''),'QUERY_RUN_FAILED'),((0,b''),'RUN_OUTPUT_NOT_ONE_LINE'),((0,b'{}\n{}\n'),'RUN_OUTPUT_NOT_ONE_LINE')])
def test_a_container_that_fails_or_prints_no_line_is_unavailable(result,code):
    docs,host=dbr.case();host.docker.on_run=lambda call:result;receipt=run(docs,host)
    assert receipt['items']['query']['code']==code and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
    if result[0]==125:assert receipt['items']['query']['engine_failure'] is True

def test_a_container_that_does_not_return_is_said_to_be_possibly_left_and_is_looked_for():
    docs,host=dbr.case();host.hang={('run','--rm')};receipt=run(docs,host);query=receipt['items']['query']
    assert (query['status'],query['code'],query['started'],query['returned'],query['container_may_still_exist'])==('UNAVAILABLE','COMMAND_TIMEOUT',True,False,True)
    assert receipt['items']['containers_after']['status']=='COMPLETE'
    docs,host=dbr.case()
    def leave(call):
        host.docker.containers.append(hostemu.container(call.name,hostemu.BACKEND,hostemu.BACKEND,[],running=True));return dbr.container(host.database)(call)
    host.docker.on_run=leave;receipt=run(docs,host)
    assert receipt['code']=='DBR_CONTAINER_LEFT' and receipt['items']['containers_after']['dbr_container_present'] is True

def test_a_container_that_cannot_start_for_lack_of_time_is_unavailable_and_nothing_ran():
    docs,host=dbr.case();budget=f.Budget(docs.now).attach(host).cost(18,'ps');receipt=run(docs,host,**budget.options())
    assert receipt['items']['query']['code']=='COMMAND_NOT_STARTED_BUDGET' and host.container_runs()==[]

# ---------------------------------------------------------------- the plan
def _set(path,value):
    def change(plan):
        target=plan
        for key in path[:-1]:target=target[key]
        target[path[-1]]=value
    return change
PLAN=[(('session',),'2026-10-10','SESSION_NOT_OF_THE_EPOCH'),(('session',),'2026-10-04','SESSION_NOT_OF_THE_EPOCH'),(('session',),None,'SESSION_NOT_OF_THE_EPOCH'),
      (('release_receipt_sha256',),'0'*64,'RELEASE_SHA_INVALID'),(('release_receipt_sha256',),'5D'*32,'RELEASE_SHA_INVALID'),
      (('expected','epoch_rows'),2,'EXPECTATION_INVALID'),(('expected','epoch_rows'),True,'EXPECTATION_INVALID'),(('expected','epoch_rows'),1.0,'EXPECTATION_INVALID'),
      (('expected','binding_committed'),1,'EXPECTATION_INVALID'),(('expected','other'),None,'EXPECTATION_INVALID'),
      (('image_id',),'c3po/backend:production','IMAGE_PLAN_INVALID'),(('image_revision',),'dd4ec4bb','IMAGE_PLAN_INVALID'),
      (('secrets_chain',-1,'mode'),0o750,'SECRETS_CHAIN_NOT_ROOT_0700'),(('secrets_chain',-2,'gid'),5,'SECRETS_CHAIN_NOT_ROOT_0700'),
      (('secrets_chain',3,'mode'),0o775,'CHAIN_ROW_UNSAFE'),(('secrets_chain',),None,'CHAIN_ROW_INVALID'),(('secrets_chain',-1,'path'),'/var/lib/c3po/x','CHAIN_ROW_INVALID'),
      (('evidence_boot_id_sha256',),'0'*64,'EVIDENCE_BOOT_UNBOUND')]

@pytest.mark.parametrize('path,value,code',PLAN,ids=['.'.join(map(str,row[0]))+'='+repr(row[1])[:16] for row in PLAN])
def test_every_member_of_the_plan_has_its_constant_refusal(path,value,code):
    docs,host=dbr.case();_set(path,value)(docs.plan);docs.chain();assert f.refusal(docs.authenticate)==code
    receipt=run(docs,f.Untouchable());assert (receipt['status'],receipt['code'])==('REFUSED',code)

def test_effects_are_exactly_what_the_signers_see():
    for mode in ('QUERIES',):
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
        assert effects['evidence_boot_id_sha256']==f.BOOT_SHA and m.EVIDENCE_OPERATIONS==('GO_WRITE_HOSTOPS02_K3K9_SECRETS_01','GO_READONLY_HOSTOPS02_DB_PRIV_01',)
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

@pytest.mark.parametrize('raw',[b'x'*63,b'x'*64+b'\n',b'x'*63+b'!',b''])
def test_snippet_password_grammar(raw):
    with pytest.raises(ValueError,match='EMITTER_PASSWORD_FORMAT'):dbr.snippet_module().emitter_password(raw)

@pytest.mark.parametrize('arguments',[[],['OTHER','a'],['PRIV'],['PRIV','a','b'],['QUERIES','a','b','R2D2-V2-SHADOW-2026-10-05','2026-10-05'],
                                      ['QUERIES','a','b','OTHER','2026-10-05','5d'*32],['QUERIES','a','b','R2D2-V2-SHADOW-2026-10-05','2026-10-10','5d'*32],
                                      ['QUERIES','a','b','R2D2-V2-SHADOW-2026-10-05','2026-10-05','5D'*32],['a','b','R2D2-V2-SHADOW-2026-10-05','2026-10-05','5d'*32]])
def test_snippet_refuses_arguments_outside_the_grammar_before_reading_anything(arguments):
    def read(path,limit):raise AssertionError('read before the arguments were checked')
    out=dbr.snippet_module().main(arguments,None,None,read=read)
    assert out.pop('mode',None) in (None,'PRIV','QUERIES') and out=={'schema':'HOSTOPS02_DBR_SNIPPET_V2','status':'REFUSED','code':'ARGUMENTS'}

def test_snippet_exception_text_never_leaves_only_its_code_and_sqlstate():
    snippet=dbr.snippet_module()
    assert snippet.failure(dbr.DatabaseError('28P01'),'X')=={'status':'UNAVAILABLE','code':'X','sqlstate':'28P01'}
    assert snippet.failure(ValueError('CAUSAL_ROLE_NOT_RESTRICTED'),'X')=={'status':'UNAVAILABLE','code':'CAUSAL_ROLE_NOT_RESTRICTED'}
    assert snippet.failure(ValueError('a text with postgresql://x:y@db'),'X')=={'status':'UNAVAILABLE','code':'X'}
    assert snippet.failure(RuntimeError('CAUSAL_ROLE_NOT_RESTRICTED'),'X')=={'status':'UNAVAILABLE','code':'X'}

# ---------------------------------------------------------------- query 2 against the release's own _authority()
EMITTER_PIN='9b52751adfc10f2cad17ceb3f7dc1906988c688e8a1b77f20bd9f82f6a29b60d'      # c3po/backend/app/r2d2_v2_causal_emitter.py at dd4ec4bb
def release_backend():
    tree=os.environ.get('HOSTOPS02_TEST_RELEASE_TREE')
    if not tree:return None
    backend=Path(tree)/'c3po'/'backend'
    try:return backend if f.sha((backend/'app'/'r2d2_v2_causal_emitter.py').read_bytes())==EMITTER_PIN else None
    except OSError:return None

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

def test_query_two_with_the_release_authority_passes_and_refuses_as_the_release_does():
    backend=release_backend()
    if backend is None:pytest.skip('no tree of the release at hand (HOSTOPS02_TEST_RELEASE_TREE)')
    sys.path.insert(0,str(backend))
    try:
        from app import r2d2_v2_causal_emitter as emitter
        snippet=dbr.snippet_module()
        def module(connection):return type('M',(),{'connect':staticmethod(lambda **options:connection),'pq':type('P',(),{'version':staticmethod(lambda:160004)})})
        good=ReleaseConnection(emitter._APPEND_ONLY_BODY);out=snippet.emitter_query(module(good),emitter._authority,'x'*64)
        assert out['status']=='COMPLETE' and out['authority_passed'] is True and len(good.sql)==6,out
        bad=ReleaseConnection(emitter._APPEND_ONLY_BODY+' ');out=snippet.emitter_query(module(bad),emitter._authority,'x'*64)
        assert out=={'status':'UNAVAILABLE','code':'CAUSAL_APPEND_ONLY_TRIGGERS_INVALID'}
        off=ReleaseConnection(emitter._APPEND_ONLY_BODY,triggers_enabled='D');out=snippet.emitter_query(module(off),emitter._authority,'x'*64)
        assert out=={'status':'UNAVAILABLE','code':'CAUSAL_APPEND_ONLY_TRIGGERS_INVALID'}
        auto=ReleaseConnection(emitter._APPEND_ONLY_BODY);auto.autocommit=True;out=snippet.emitter_query(module(auto),emitter._authority,'x'*64)
        assert out=={'status':'UNAVAILABLE','code':'CAUSAL_TRANSACTION_REQUIRED'}
    finally:
        sys.path.remove(str(backend))
        for name in [name for name in sys.modules if name=='app' or name.startswith('app.')]:del sys.modules[name]

def test_the_three_queries_and_the_transaction_statements_are_these_texts():
    """Pinned here as literals (not read back from the snippet), so a changed query text is a failing test."""
    snippet=dbr.snippet_module()
    assert snippet.EPOCH_ROW_SQL==("SELECT count(e.epoch),max(e.state_sha),max(e.version),max(e.state->>'release_sha'),max(e.journal_head) "
        "FROM public.r2d2_v2_shadow_epochs e WHERE e.epoch=%s::text")
    assert snippet.BINDING_SQL==("SELECT (SELECT e.state->'daily_capacity'->(%s::text)->>'sha' FROM public.r2d2_v2_shadow_epochs e WHERE e.epoch=%s::text),"
        "(SELECT count(*) FROM public.r2d2_v2_shadow_journal j WHERE j.epoch=%s::text AND j.journal_key=%s::text)")
    assert snippet.IDENTITY_SQL==("SELECT current_database(),current_user,session_user,current_setting('session_replication_role'),"
        "current_setting('transaction_read_only')")
    assert snippet.BEGIN_READER=='SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY' and snippet.BEGIN_EMITTER=='SET TRANSACTION READ ONLY'
    assert snippet.TIMEOUT=="SET LOCAL statement_timeout='3s'" and (snippet.CONNECT_SECONDS,snippet.EMITTER_LATEST_START_SECONDS)==(5,20) and snippet.DATABASE=={'host':'db','port':5432,'dbname':'c3po'}
    assert (snippet.READER_ROLE,snippet.EMITTER_ROLE)==('c3po_v2_risk_reader','c3po_v2_causal_emitter')

def test_a_sqlstate_that_is_not_one_never_leaves():
    snippet=dbr.snippet_module()
    assert snippet.failure(dbr.DatabaseError('password=x'),'X')=={'status':'UNAVAILABLE','code':'X'}
    assert snippet.failure(dbr.DatabaseError('28p01'),'X')=={'status':'UNAVAILABLE','code':'X'}
    assert snippet.failure(dbr.DatabaseError(28001),'X')=={'status':'UNAVAILABLE','code':'X'}

def test_a_row_count_said_as_a_boolean_is_refused_even_when_a_row_exists():
    docs,host=dbr.case();host.database.epoch_row=_row()
    host.docker.on_run=_line(lambda v:v['epoch_row'].update(rows=True))(host.database);receipt=run(docs,host)
    assert receipt['items']['query']=={'status':'UNAVAILABLE','code':'SNIPPET_LINE_INVALID'}

def test_an_image_inspect_that_answers_another_image_is_a_finding():
    docs,host=dbr.case();found=host.docker.find;other=host.docker.images[3]
    host.docker.find=lambda reference:other if reference==hostemu.BACKEND else found(reference)
    receipt=run(docs,host);assert 'IMAGE_ID_MISMATCH' in receipt['findings'] and host.container_runs()==[]

def test_a_password_file_longer_than_64_bytes_is_not_read_beyond_them():
    docs,host=dbr.case();host.tree.get(dbr.SECRETS+'/emitter/password').content.extend(b'x');receipt=run(docs,host)
    assert receipt['items']['query']['line']['emitter_password']=={'status':'UNAVAILABLE','code':'FILE_FORMAT'}

def test_after_a_failed_query_one_query_three_runs_in_a_new_read_only_transaction():
    docs,host=dbr.case();host.database.reader_can_read=False;run(docs,host);snippet=dbr.snippet_module()
    reader=[sql for user,sql,_ in host.database.statements if user=='c3po_v2_risk_reader']
    assert reader==[snippet.BEGIN_READER,snippet.TIMEOUT,snippet.EPOCH_ROW_SQL,'ROLLBACK',snippet.BEGIN_READER,snippet.TIMEOUT,snippet.BINDING_SQL,'ROLLBACK']

def test_query_two_is_not_begun_after_the_snippet_deadline():
    docs,host=dbr.case();snippet=dbr.snippet_module();clock=iter([0.0,25.0])
    def read(path,limit):return dbr.RISK_FILE if path.endswith('risk-db.env') else dbr.PASSWORD_CANARY.encode()
    out=snippet.main(['QUERIES','/c3po-dbr-risk-db.env','/c3po-dbr-emitter/password',dbr.EPOCH,'2026-10-05',dbr.RELEASE],dbr.driver(host.database),
                     dbr.model_authority(host.database),read=read,monotonic=lambda:next(clock))
    assert out['emitter']=={'status':'UNAVAILABLE','code':'SNIPPET_DEADLINE'} and out['epoch_row']['status']=='COMPLETE'
    assert not [user for user,_,_ in host.database.statements if user=='c3po_v2_causal_emitter']

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



def test_a_queries_line_in_a_priv_run_and_the_reverse_are_refused():
    docs,host=dbr.case(mode='QUERIES');host.docker.on_run=_line(lambda v:v.update(reader_privileges={'status':'COMPLETE'}))(host.database);receipt=run(docs,host)
    assert receipt['items']['query']=={'status':'UNAVAILABLE','code':'SNIPPET_LINE_INVALID'}
    docs,host=dbr.case(mode='QUERIES');host.docker.on_run=_line(lambda v:v.update(mode='PRIV'))(host.database);receipt=run(docs,host)
    assert receipt['items']['query']=={'status':'UNAVAILABLE','code':'SNIPPET_LINE_INVALID'}

# ---------------------------------------------------------------- QUERIES requires a PRIV receipt of the same boot and day that proved SELECT
@pytest.mark.parametrize('value,code',[(None,'PRIV_RECEIPT_REQUIRED'),({},'PRIV_RECEIPT_REQUIRED'),
    (lambda:dbr.priv_receipt(operation='GO_READONLY_HOSTOPS02_K9R_TREE_01'),'PRIV_RECEIPT_NOT_OF_THIS_OPERATION'),
    (lambda:dbr.priv_receipt(mode='QUERIES'),'PRIV_RECEIPT_NOT_OF_THIS_OPERATION'),
    (lambda:dbr.priv_receipt(outcome='DB_PREFLIGHT_OBSERVED_EXPECTATIONS_NOT_MET'),'PRIV_RECEIPT_DID_NOT_PROVE_SELECT'),
    (lambda:dbr.priv_receipt(outcome='DB_PREFLIGHT_PARTIAL'),'PRIV_RECEIPT_DID_NOT_PROVE_SELECT'),
    (lambda:dbr.priv_receipt(receipt_sha256='0'*64),'PRIV_RECEIPT_REQUIRED'),
    (lambda:dbr.priv_receipt(boot_id_sha256='b0'*32),'PRIV_RECEIPT_OF_ANOTHER_BOOT'),
    (lambda:dbr.priv_receipt(observed_at='2026-10-04T23:59:59+00:00'),'PRIV_RECEIPT_NOT_OF_THIS_DAY'),
    (lambda:dbr.priv_receipt(observed_at='2026-10-05T20:41:00+00:00'),'PRIV_RECEIPT_NOT_OF_THIS_DAY'),
    (lambda:dbr.priv_receipt(observed_at='2026-10-05T20:40:00+00:00'),'PRIV_RECEIPT_NOT_OF_THIS_DAY'),
    (lambda:dbr.priv_receipt(observed_at='yesterday'),'WINDOW_UNBOUND'),
    (lambda:dict(dbr.priv_receipt(),extra=1),'PRIV_RECEIPT_REQUIRED')])
def test_queries_refuses_without_a_priv_receipt_of_the_same_boot_and_day_that_proved_select(value,code):
    docs,host=dbr.case();docs.plan['priv_receipt']=value() if callable(value) else value;docs.chain()
    assert f.refusal(docs.authenticate)==code
    receipt=run(docs,f.Untouchable());assert (receipt['status'],receipt['code'])==('REFUSED',code)


@pytest.mark.parametrize('value',[None,'QUERY','priv',3])
def test_the_mode_is_one_of_two(value):
    docs,host=dbr.case();docs.plan['mode']=value;docs.chain();assert f.refusal(docs.authenticate)=='MODE_INVALID'

