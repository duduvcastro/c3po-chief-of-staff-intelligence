"""Projeções atuais sobre recibos emitidos por fontes seladas em FakeHost.
As facts de proveniência são contextos sintéticos inertes; não provam load_evidence/BOUND ou host.
Nenhuma identidade da estação ou hash de recibo real foi convertido em fixture.
"""
import copy,types
from datetime import datetime,timezone,timedelta
import pytest
import helpers as h
import hostops02_fixtures as x
from test_programs import programs
b=h.b
NOW=datetime(2026,10,6,12,26,tzinfo=timezone.utc)

@pytest.fixture(scope='module')
def emitted_projection_receipts(tmp_path_factory,families):
    root=h.resolved(tmp_path_factory.mktemp('projection-producers'));h2=x.hostops02(x.sealed_copy(root/'tier'))
    release=x.k10_receipt(h2,x.M1,x.release_bytes(h2))
    docs,host=h2.k6a.case(now=x.M3);policy=docs.run(host)
    assert policy['outcome']=='ACTIVATE_WORKER_RECREATED_AND_VERIFIED'
    h1=x.hostops01(families['hostops']);f=h1.family;k=f.load('readback');host,provision,install=f.ready_host(k,placement='A')
    readback=f.Docs(k,f.readback_fields(k,host,provision,install),now=h.HOSTOPS_NOW).run(host)
    assert readback['outcome']=='READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
    return {'release':release,'policy':policy,'unit':readback}

def context(receipt,operation,mode):
    r=copy.deepcopy(receipt);producer=r['operation'];role='READBACK' if operation=='GO_WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_01' else 'PRODUCER'
    return {'operation':operation,'plan_mode':mode,'source':types.SimpleNamespace(OPERATION=operation),
        'operations':{role:producer},'entries':[{'role':role,'operation':producer}],
        'receipts':{role:r},'evidence_facts':[{'role':role,'operation':producer,'receipt_sha256':r['metadata_sha256'],
        'complete':True,'source':'BOUND_SET','receipt_host_binding_is_the_one_of_this_set':True,
        'receipt_payload_is_the_sealed_source_of_that_operation':True,'exit_json_binds_these_bytes':True,
        'bound_set':{'stderr_empty':True,'exit_json_binds_config_request_go_and_output':True}}],
        'blobs':{role:{'source':'bound'}},'inputs':{},'used':[],'copied':[],
        'plan':{'mode':mode,'evidence_boot_id_sha256':b.receipt_boot(r)},'window':{'start':NOW}}

def reseal(ctx,role):
    r=ctx['receipts'][role];r.pop('metadata_sha256',None);r['metadata_sha256']=b.sha(b.canonical(r));ctx['evidence_facts'][0]['receipt_sha256']=r['metadata_sha256']

@pytest.mark.parametrize('kind',['release','policy'])
def test_created_chain_uses_genuine_emulated_receipt_and_whole_list_provenance(emitted_projection_receipts,kind):
    c=context(emitted_projection_receipts[kind],b.BOOTSTRAP_OPERATION,b.BOOTSTRAP_MODE);before=b.canonical(c['receipts'])
    p='/policy_read/'+kind+'/directory/rows';rows=b.resolve_hostops02({'$created_directory_chain':{'evidence':'PRODUCER','kind':kind}},c,p)
    assert rows[-1]['mode']==0o700 and rows[-1]['uid']==rows[-1]['gid']==0
    assert b.created_directory_chain_provenance(c,c['copied'][0])==rows
    assert b.canonical(c['receipts'])==before

@pytest.mark.parametrize('damage,code',[
    ('pointer','CREATED_DIRECTORY_CHAIN_INVALID'),('fact','CREATED_DIRECTORY_CHAIN_NOT_BOUND_COMPLETE'),
    ('seal','CREATED_DIRECTORY_CHAIN_RECEIPT_SEAL'),('boot','CREATED_DIRECTORY_CHAIN_BOOT_UNKNOWN'),
    ('clock','CREATED_DIRECTORY_CHAIN_CLOCK_INVALID'),('future','CREATED_DIRECTORY_CHAIN_PREDECESSOR_NOT_FINISHED')])
@pytest.mark.parametrize('kind',['release','policy'])
def test_created_chain_refuses_unproved_stale_or_uncertain_identity(emitted_projection_receipts,kind,damage,code):
    c=context(emitted_projection_receipts[kind],b.BOOTSTRAP_OPERATION,b.BOOTSTRAP_MODE);r=c['receipts']['PRODUCER'];p='/policy_read/'+kind+'/directory/rows'
    if damage=='pointer':p='/caller_chosen'
    if damage=='fact':c['evidence_facts'][0]['bound_set']['stderr_empty']=False
    if damage=='seal':r['directories'][0]['observed']['inode']+=1
    if damage=='boot':r['effects']['evidence_boot_id_sha256']=None;reseal(c,'PRODUCER')
    if damage=='clock':r['clock']['monotonic_elapsed_ms']=True;reseal(c,'PRODUCER')
    if damage=='future':c['window']['start']=datetime.fromisoformat(r['clock']['utc_end'])-timedelta(seconds=1)
    with h.refused(code):b.created_directory_chain(c,{'evidence':'PRODUCER','kind':kind},p)

@pytest.mark.parametrize('kind',['service','timer'])
def test_supervisor_whole_unit_record_is_observed_not_child_scalar_guess(emitted_projection_receipts,kind):
    c=context(emitted_projection_receipts['unit'],'GO_WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_01','ACTIVATE');before=b.canonical(c['receipts'])
    result=b.resolve_hostops02({'$supervisor_unit_record':{'evidence':'READBACK','kind':kind}},c,'/units/'+kind)
    assert set(result)=={'name','sha256','bytes','device','inode'}
    assert b.supervisor_unit_record_provenance(c,c['copied'][0])==result and b.canonical(c['receipts'])==before

@pytest.mark.parametrize('damage,code',[
    ('pointer','SUPERVISOR_UNIT_RECORD_INVALID'),('fact','SUPERVISOR_UNIT_RECORD_NOT_BOUND_COMPLETE'),
    ('seal','SUPERVISOR_UNIT_RECORD_RECEIPT_SEAL'),('boot','SUPERVISOR_UNIT_RECORD_BOOT_UNKNOWN'),
    ('clock','SUPERVISOR_UNIT_RECORD_CLOCK_INVALID'),('future','SUPERVISOR_UNIT_RECORD_PREDECESSOR_NOT_FINISHED')])
@pytest.mark.parametrize('kind',['service','timer'])
def test_supervisor_unit_refuses_unproved_stale_or_uncertain_identity(emitted_projection_receipts,kind,damage,code):
    c=context(emitted_projection_receipts['unit'],'GO_WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_01','ACTIVATE');r=c['receipts']['READBACK'];p='/units/'+kind
    if damage=='pointer':p='/caller_chosen'
    if damage=='fact':c['evidence_facts'][0]['bound_set']['stderr_empty']=False
    if damage=='seal':r['items']['units']['files']['c3po-massive.'+kind]['inode']+=1
    if damage=='boot':r['items']['boot']['device_numbers_compared']=False;reseal(c,'READBACK')
    if damage=='clock':r['observed_at']='not-a-time';reseal(c,'READBACK')
    if damage=='future':c['window']['start']=datetime.fromisoformat(r['observed_at'])-timedelta(seconds=1)
    with h.refused(code):b.supervisor_unit_record(c,{'evidence':'READBACK','kind':kind},p)

@pytest.mark.parametrize('damage,code',[('numeric','SEALED_PROGRAM_MODE_ENUM_INVALID'),('operation','SEALED_PROGRAM_MODE_SOURCE_MISMATCH')])
def test_operational_mode_enum_ignores_permission_tuples_and_refuses_wrong_source(programs,damage,code):
    op='GO_WRITE_HOSTOPS02_K4_FILES_01';m=types.SimpleNamespace(**vars(programs.modules[op][2]['source']))
    m.FILE_MODES=(0o600,0o644);m.DIRECTORY_MODES=(0o700,)
    if damage=='numeric':m.K4_MODES=(0o700,)
    if damage=='operation':m.OPERATION='GO_UNKNOWN'
    with h.refused(code):b.sealed_program_modes(m,op)
