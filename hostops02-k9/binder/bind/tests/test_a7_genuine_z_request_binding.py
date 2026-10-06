"""Genuine synthetic REQUEST/receipt bytes from the r12 sealed FakeHost producers.
Only the context facts/sheet projection are inert synthetic scaffolding. This does
not prove load_evidence, physical runtime identity, Linux, host, or authority.
No signed receipt or request field is remapped to manufacture a positive case.
"""
import copy
import json
import sys
import types
from datetime import timedelta
from pathlib import Path

import pytest
import helpers as h

b=h.b
FIXTURES=Path(__file__).parent/'fixtures/a7-genuine-z-request'
LAYERS=['py39','py312']


def read_fixture(name):
    proof=json.loads((FIXTURES/'PROVENANCE.json').read_bytes())
    raw=(FIXTURES/name).read_bytes()
    assert b.sha(raw)==proof['input_files'][name]
    return raw


def genuine_context(layer):
    boot=json.loads(read_fixture(layer+'/BOOTSTRAP.stdout.original.json'))
    k3=json.loads(read_fixture(layer+'/K3.stdout.original.json'))
    raw=read_fixture(layer+'/REQUEST.BOUND.original.json')
    sheet=json.loads(read_fixture(layer+'/SHEET.SCOPED_PROJECTION.json'))
    request=json.loads(raw)
    assert request['not_before'].endswith('Z') and request['not_after'].endswith('Z')
    assert k3['request_sha256']==b.sha(raw)
    for receipt in (boot,k3):
        unsealed=dict(receipt);sealed=unsealed.pop('metadata_sha256')
        assert sealed==b.sha(b.canonical(unsealed))
    start=b.parse_utc('2026-10-06T13:26:00Z')
    ctx={'operation':'GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01','mode':b.REHEARSAL,
        'window':{'start':start,'end':start+timedelta(minutes=5)},
        'plan':{'worker_container_id':k3['effects']['values']['provider_env']['container_id'],
                'evidence_boot_id_sha256':k3['effects']['evidence_boot_id_sha256']},
        'entries':[{'role':'BOOTSTRAP','operation':boot['operation']},{'role':'K3','operation':k3['operation']}],
        'receipts':{'BOOTSTRAP':boot,'K3':k3},'evidence_facts':[],
        'blobs':{'BOOTSTRAP':{'source':'bound'},'K3':{'source':'bound','request':raw,'sheet':sheet}},
        'copied':[{'plan_pointer':'/worker_container_id','evidence_role':'K3','receipt_pointer':'/effects/values/provider_env/container_id'},
                  {'plan_pointer':'/evidence_boot_id_sha256','evidence_role':'K3','receipt_pointer':'/effects/evidence_boot_id_sha256'}]}
    # These booleans model a helper context only. They are not a fabricated BOUND
    # artifact: the independent original-stream coupling is recorded in provenance.
    for role in ('BOOTSTRAP','K3'):
        ctx['evidence_facts'].append({'role':role,'complete':True,'source':'BOUND_SET',
            'receipt_host_binding_is_the_one_of_this_set':True,
            'receipt_payload_is_the_sealed_source_of_that_operation':True,'exit_json_binds_these_bytes':True,
            'bound_set':{'stderr_empty':True,'exit_json_binds_config_request_go_and_output':True}})
    return ctx


@pytest.mark.parametrize('layer',LAYERS)
def test_a7_accepts_genuine_k3_Z_request_and_preserves_both_receipts(layer):
    ctx=genuine_context(layer);before=b.canonical(ctx['receipts']);request=ctx['blobs']['K3']['request']
    answer=b.bootstrap_k3env_identity(ctx)
    assert answer['identity_observed_role']=='BOOTSTRAP' and answer['k3_role']=='K3'
    assert answer['k3_effects_are_independent_observation'] is False
    assert b.canonical(ctx['receipts'])==before and ctx['blobs']['K3']['request']==request


@pytest.mark.parametrize('layer',LAYERS)
def test_real_bind_request_reemits_the_exact_genuine_Z_bytes(layer):
    ctx=genuine_context(layer);raw=ctx['blobs']['K3']['request'];request=json.loads(raw)
    source=read_fixture('producer/k3k9_secrets.py')
    module=types.ModuleType('_genuine_k3_source_'+layer)
    sys.modules[module.__name__]=module
    try:
        exec(compile(source,'<pinned-genuine-k3-source>','exec'),module.__dict__)
        template={'request':json.loads(read_fixture('producer/REQUEST.UNBOUND.json'))}
        window={'start':b.parse_utc(request['not_before']),'end':b.parse_utc(request['not_after'])}
        _,emitted=b.bind_request('core',template,module,{},window,request['host_binding_sha256'],request['evidence'],
                                {key:request['plan'][key] for key in module.PLAN_KEYS})
        assert emitted==raw
    finally:
        sys.modules.pop(module.__name__,None)


@pytest.mark.parametrize('layer',LAYERS)
@pytest.mark.parametrize('damage,code',[
    ('request_bytes','BOOTSTRAP_K3_CHAIN_NOT_BOUND'),
    ('link_role','BOOTSTRAP_K3_CHAIN_NOT_LINKED'),
    ('sheet_copy','BOOTSTRAP_K3_CHAIN_NOT_LINKED'),
    ('stderr','BOOTSTRAP_K3_CHAIN_NOT_BOUND'),
    ('worker','BOOTSTRAP_IDENTITY_NOT_EXACT_COPIES'),
    ('boot','BOOTSTRAP_IDENTITY_NOT_OBSERVED_SAME_BOOT'),
    ('band','BOOTSTRAP_WINDOW_NOT_FIRST_NIGHT'),
    ('predecessor','BOOTSTRAP_PREDECESSOR_NOT_FINISHED')])
def test_a7_genuine_Z_chain_refuses_broken_links_bands_and_identity(layer,damage,code):
    ctx=genuine_context(layer);before=b.canonical(ctx['receipts'])
    if damage=='request_bytes':ctx['blobs']['K3']['request']+=b' '
    elif damage=='link_role':ctx['blobs']['K3']['sheet']['hostops02']['rules']['k9_prerequisite']['bootstrap_role']='OTHER'
    elif damage=='sheet_copy':ctx['blobs']['K3']['sheet']['plan_values_copied_from_receipts']=[row for row in ctx['blobs']['K3']['sheet']['plan_values_copied_from_receipts'] if row['plan_pointer']!='/worker_container_id']
    elif damage=='stderr':ctx['evidence_facts'][1]['bound_set']['stderr_empty']=False
    elif damage=='worker':ctx['plan']['worker_container_id']='d2'*32
    elif damage=='boot':ctx['plan']['evidence_boot_id_sha256']='d2'*32
    elif damage=='band':
        start=b.parse_utc('2026-10-06T16:26:00Z');ctx['window']={'start':start,'end':start+timedelta(minutes=5)}
    elif damage=='predecessor':
        start=b.parse_utc('2026-10-06T12:38:02Z');ctx['window']={'start':start,'end':start+timedelta(minutes=5)}
    with h.refused(code):b.bootstrap_k3env_identity(ctx)
    # Negatives alter context/provenance only; original signed receipt hashes stay intact.
    assert b.canonical(ctx['receipts'])==before


@pytest.mark.parametrize('value',['2026-10-06T12:38:00.1Z','2026-10-06T12:38:00-03:00','2026-10-06T12:38:00',None])
def test_request_parser_remains_strict_and_preserves_link_refusal_code(value):
    with h.refused('BOOTSTRAP_K3_CHAIN_NOT_LINKED'):
        b.parse_utc(value,code='BOOTSTRAP_K3_CHAIN_NOT_LINKED')
