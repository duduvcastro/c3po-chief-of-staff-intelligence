"""Revision 3: real acquisition primitive, hostile file/JSON boundaries, no child secret reader."""
import json
import pytest
import k3
import family as f
from test_k3k9_secrets import run,refused,nothing_changed,set_node

def config_path():return k3.m().DOCKER_CONTAINER_ROOT+'/'+k3.WORKER_ID+'/'+k3.m().WORKER_CONFIG_NAME

@pytest.mark.parametrize('change,code',[
    ({'uid':1000},'WORKER_CONFIG_METADATA_UNSAFE'),
    ({'gid':1000},'WORKER_CONFIG_METADATA_UNSAFE'),
    ({'mode':0o644},'WORKER_CONFIG_METADATA_UNSAFE'),
    ({'nlink':2},'WORKER_CONFIG_METADATA_UNSAFE'),
    ({'kind':'fifo'},'WORKER_CONFIG_METADATA_UNSAFE'),
])
def test_unsafe_config_refuses_before_a_secret_read(change,code):
    docs,host,before,receipt=run(set_node(config_path(),**change));refused(receipt,code);nothing_changed(host,before)
    assert not any(e[0]=='read' and e[1]==config_path() for e in host.log)

@pytest.mark.parametrize('component,change',[
    ('/var/lib/docker',{'uid':1000}),
    ('/var/lib/docker/containers',{'gid':1000}),
    ('/var/lib/docker/containers',{'mode':0o777}),
    ('/var/lib/docker/containers/'+k3.WORKER_ID,{'mode':0o755}),
])
def test_root_chain_and_private_container_directory_are_required(component,change):
    docs,host,before,receipt=run(set_node(component,**change));refused(receipt,'WORKER_CONFIG_CHAIN_UNSAFE');nothing_changed(host,before)
    assert not any(e[0]=='open' and e[1]==config_path() for e in host.log)

@pytest.mark.parametrize('raw,code',[
    (b'{not JSON','JSON_INVALID'),
    (b'{"ID":"x","ID":"y"}','DUPLICATE_KEY'),
    (b'{}','WORKER_CONFIG_IDENTITY'),
    (json.dumps({'ID':k3.WORKER_ID,'Name':'/other','Config':{'Env':[]}}).encode(),'WORKER_CONFIG_IDENTITY'),
    (json.dumps({'ID':k3.WORKER_ID,'Name':'/'+k3.WORKER,'Config':{'Env':None}}).encode(),'WORKER_CONFIG_FORMAT'),
    (b'x'*1048577,'WORKER_CONFIG_UNREADABLE'),
])
def test_strict_bounded_config_and_identity(raw,code):
    docs,host,before,receipt=run(lambda host:setattr(host,'config_override',raw));refused(receipt,code);nothing_changed(host,before)

def test_environment_file_read_requires_protection_again():
    m=k3.m();k,host=k3.world();host.dumpable_refused=True
    assert f.refusal(lambda:m.token_values(host,lambda:60,k3.WORKER_ID))=='PROCESS_DUMPABLE_NOT_DISABLED'
    assert not any(e[0]=='open' for e in host.log)

def test_no_secret_row_or_worker_inspect_can_be_spawned():
    m=k3.m();assert set(m.COMMANDS)=={'container_list'}
    docs,host,before,receipt=run()
    assert receipt['code'] is None
    assert all('inspect' not in e['argv'] and 'Env' not in ''.join(e['argv']) for e in host.commands)

@pytest.mark.parametrize('change,code',[
    (lambda worker:worker.update(Id='6f'*32),'WORKER_CONTAINER_MISMATCH'),
    (lambda worker:worker['State'].update(Status='exited',Running=False),'WORKER_NOT_RUNNING'),
])
def test_worker_must_still_match_and_run_after_both_secret_reads(change,code):
    def hook(host,name,detail,calls):
        if name=='run' and len([e for e in host.log if e[0]=='run'])==2:change(host.docker.container(k3.WORKER))
    docs,host,before,receipt=run(hook=hook);refused(receipt,code);nothing_changed(host,before)
    assert receipt['mutating_calls']['issued']==0

def test_duplicate_parse_zeroes_every_buffer_already_created():
    m=k3.m();found=[];original=m.zero_secret_values
    def spy(values):
        found.extend(values.values());original(values)
    m.zero_secret_values=spy
    value=k3.TOKENS['C3PO_EODHD_API_TOKEN'].encode()
    try:
        assert f.refusal(lambda:m.secret_entries(b'"EODHD_API_TOKEN='+value+b'"\n"EODHD_API_TOKEN='+value+b'"\n\n',m.SECRET_ENVIRONMENT_NAMES))=='SECRET_ENVIRONMENT_REPEATED'
    finally:m.zero_secret_values=original
    assert len(found)==1 and set(found[0])=={0}


def test_stopped_worker_refuses_before_config_acquisition():
    docs,host,before,receipt=run(lambda host:host.docker.container(k3.WORKER)['State'].update(Status='exited',Running=False))
    refused(receipt,'WORKER_NOT_RUNNING')
    assert not any(e[0]=='open' and e[1]==config_path() for e in host.log)


@pytest.mark.parametrize('field,value',[('mode',0o644),('uid',1000)])
def test_config_metadata_cannot_change_between_name_check_and_open(field,value):
    def hook(host,name,detail,calls):
        if name=='open' and detail[0]==config_path():
            setattr(host.tree.get(config_path()),field,value)
    docs,host,before,receipt=run(hook=hook)
    refused(receipt,'WORKER_CONFIG_CHANGED')
    assert receipt['mutating_calls']['issued']==0
