"""New H16 DBR/M6/V read adapters, elected by the new model's registry.

No connection, subprocess or observation occurs on import. These are new
contracts, not the expired ORD:28/IND programs. SQL is fixed/parameterized, in a
read-only transaction rolled back even on refusal. No GRANT/activation/retry.
"""
import math
import re
from common import canonical,context,digest,fields,need,sha,strict
from runtime import physical

BEGIN='BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'
TIMEOUT="SET LOCAL statement_timeout = '5000ms'"
PRIVILEGES=("SELECT current_database(),current_user,session_user,current_setting('transaction_read_only'),"
 "(SELECT NOT (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls) FROM pg_catalog.pg_roles WHERE rolname=current_user),"
 "has_table_privilege(current_user,'public.r2d2_v2_shadow_epochs','SELECT'),"
 "has_table_privilege(current_user,'public.r2d2_v2_shadow_journal','SELECT')")
EPOCH=("SELECT count(epoch),max(state_sha),max(version),max(state->>'release_sha') "
 "FROM public.r2d2_v2_shadow_epochs WHERE epoch=%s::text")
BINDING=("SELECT (SELECT state->'daily_capacity'->(%s::text)->>'sha' FROM public.r2d2_v2_shadow_epochs WHERE epoch=%s::text),"
 "(SELECT count(*) FROM public.r2d2_v2_shadow_journal WHERE epoch=%s::text AND journal_key=%s::text)")


class DBReader:
    def __init__(self,guard,entry,connector):self.guard,self.entry,self.connector=guard,entry,connector

    def read(self,ctx,capacity_binding_sha256):
        context(ctx);entry=self.entry
        raw,ident=physical(entry['credential_path'],maximum=4096)
        need(ident['mode']==0o400 and ident['uid']==self.guard.value['measurement']['euid']
             and digest(raw)==sha(entry['credential_sha256']),'H16_DB_CREDENTIAL')
        # The exact private DSN is an independently measured registry input.
        # It is passed only to the connector, never argv/env/public output.
        dsn=raw.decode('utf-8').strip();need(dsn and '\n' not in dsn and '\x00' not in dsn,'H16_DB_DSN')
        self.guard.recheck();connection=self.connector(dsn,autocommit=False,connect_timeout=5,
            application_name='server-h16-reader-v2',options='-c default_transaction_read_only=on')
        try:
            connection.execute(BEGIN);connection.execute(TIMEOUT)
            p=connection.execute(PRIVILEGES).fetchone()
            need(p is not None and len(p)==7 and p[0]==entry['database'] and p[1]==p[2]==entry['restricted_role']
                 and p[3]=='on' and all(v is True for v in p[4:]),'H16_DB_PRIVILEGES')
            self.guard.recheck();row=connection.execute(EPOCH,(ctx['epoch'],)).fetchone()
            need(row is not None and len(row)==4 and row[0]==1 and type(row[0]) is int
                 and row[1]==sha(entry['expected_state_sha256']) and type(row[2]) is int
                 and row[2]==entry['expected_version'] and row[3]==ctx['release_sha256'],'H16_DB_EPOCH')
            self.guard.recheck();binding=connection.execute(BINDING,(ctx['session'],ctx['epoch'],ctx['epoch'],'capacity-prepared:'+ctx['session'])).fetchone()
            need(binding is not None and len(binding)==2 and binding[0]==sha(capacity_binding_sha256)
                 and type(binding[1]) is int and binding[1]==1,'H16_DB_BINDING')
            self.guard.recheck()
            return {'readonly_role':True,'epoch_state_version_release':True,'capacity_binding_once':True,
                    'queries':3,'mutation_performed':False}
        finally:
            try:connection.rollback()
            finally:connection.close()


INSPECT='{{json .}}'
UNIT_FORMAT=['ActiveState','SubState','LoadState','UnitFileState','FragmentPath','ExecMainStatus','MainPID']


class ReaderHost:
    def __init__(self,guard,runner,entry):self.guard,self.runner,self.entry=guard,runner,entry

    def read(self,ctx):
        e=self.entry;context(ctx);self.guard.recheck()
        need(re.fullmatch('[0-9a-f]{64}',e['container_id']) is not None,'H16_READER_CONTAINER')
        exe=self.guard.value['spec']['executables'];sock=self.guard.value['spec']['socket']
        argv=[exe['docker']['path'],'--host','unix://'+sock,'inspect','--format',INSPECT,e['container_id']]
        result=self.runner.run(argv,limit=65536,seconds=10);need(result['returncode']==0,'H16_READER_INSPECT')
        row=strict(result['stdout']);state=row['State'];config=row['Config'];host=row['HostConfig']
        need(row['Id']==e['container_id'] and row['Image']==e['image_id'] and config['Cmd']==e['argv']
             and config['Labels']==e['labels'] and config['User']==e['user']
             and state['Running'] is True and state['Status']=='running' and row['RestartCount']==0
             and host['ReadonlyRootfs'] is True and host['NetworkMode']==e['network']
             and host['RestartPolicy']['Name']=='no','H16_READER_IDENTITY_POSTURE')
        mounts=[{'source':m['Source'],'destination':m['Destination'],'rw':m['RW']} for m in row['Mounts']]
        need(mounts==e['mounts'] and all(m['rw'] is False for m in mounts),'H16_READER_MOUNTS')
        need(config['Labels'].get('c3po.server.epoch')==ctx['epoch']
             and config['Labels'].get('c3po.server.release_sha256')==ctx['release_sha256'],'H16_READER_EPOCH')
        need(set(e['units'])=={'service','timer'} and type(e['readonly_sources']) is list and e['readonly_sources'],
             'H16_READER_COMPONENT_SET')
        for role,unit in e['units'].items():
            need(role in ('service','timer') and re.fullmatch('[A-Za-z0-9_.@-]{1,120}',unit['name']),'H16_READER_UNIT')
            argv=[exe['systemctl']['path'],'show','--no-pager']+['--property='+k for k in UNIT_FORMAT]+['--',unit['name']]
            out=self.runner.run(argv,limit=16384,seconds=5);need(out['returncode']==0,'H16_UNIT_UNAVAILABLE')
            values={}
            for line in out['stdout'].decode('utf-8').splitlines():
                key,sep,value=line.partition('=');need(sep and key in UNIT_FORMAT and key not in values,'H16_UNIT_FIELDS');values[key]=value
            need(values==unit['expected'],'H16_UNIT_POSTURE')
            need(values['LoadState']=='loaded' and values['UnitFileState'] in ('enabled','static','transient')
                 and values['ExecMainStatus']=='0','H16_UNIT_NOT_READY')
            if role=='timer':need(values['ActiveState']=='active' and values['SubState']=='waiting','H16_TIMER_NOT_WAITING')
            else:need((values['ActiveState'],values['SubState']) in (('inactive','dead'),('active','running')),'H16_SERVICE_POSTURE')
            raw,_=physical(values['FragmentPath']);need(digest(raw)==sha(unit['fragment_sha256']),'H16_UNIT_SOURCE')
        for entry in e['readonly_sources']:
            raw,_=physical(entry['path']);need(digest(raw)==sha(entry['sha256']),'H16_READER_SOURCE')
        self.guard.recheck();return {'reader_identity_posture':True,'readonly_mounts':True,'units_sources':True,'activation_performed':False}


class CompleteReader:
    reader_id='H16_SERVER_READER_V2'
    def __init__(self,source_sha256,artifacts,database,host,entry):
        self.source_sha256=sha(source_sha256);self.artifacts,self.database,self.host,self.entry=artifacts,database,host,entry

    def read_once(self,request,binding):
        need(binding['reader_id']==self.reader_id and binding['reader_source_sha256']==self.source_sha256,'H16_SERVER_READER_BINDING')
        adapted=dict(binding,reader_id=self.artifacts.reader_id,reader_source_sha256=self.artifacts.source_sha256)
        actual=self.artifacts.read_once(request,adapted)
        dbr=self.database.read(request['context'],self.entry['capacity_binding_sha256'])
        live=self.host.read(request['context'])
        checks=dict(actual['checks']);checks.update(DBR=dbr['readonly_role'] and dbr['epoch_state_version_release'] and dbr['capacity_binding_once'],
                                                M6=live['reader_identity_posture'] and live['readonly_mounts'],V=live['units_sources'])
        return {'schema':'H16_READER_RESULT_V2','status':'COMPLETE','context':request['context'],
                'request_sha256':binding['request_sha256'],'actual_receipts':binding['actual_receipts'],'checks':checks,
                'scope':'NEW_H16_SERVER_DBR_M6_V_AND_ARTIFACTS','owner_question_sent':False,'activation_performed':False}
