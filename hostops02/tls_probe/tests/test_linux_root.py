"""linux_root/ of C3 offline: probe_shape.py against the emulated engine (every run made, every expectation met, an
expectation false when its run is missing or differs, a refusal anywhere but a throwaway runner), the two stand-ins of
linux_root/stubs.py with real sockets on 127.0.0.1 (the DNS answers, the TLS server reached by the REAL pinned script
through the test-only prelude), and the text of run.sh. Nothing here proves a real engine."""
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys

import pytest

import c3

LINUX=c3.DIRECTORY/'linux_root'
SCRIPT=LINUX/'probe_shape.py'
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
def environment():
    return dict(ENV,**{name:value for name,value in os.environ.items() if name.startswith('HOSTOPS02_TEST_')})
def present():
    if not SCRIPT.is_file():pytest.skip('a private copy without linux_root/ (the mutation harness)')
def module(name):
    spec=importlib.util.spec_from_file_location('_hostops02_c3_'+name,LINUX/(name+'.py'));loaded=importlib.util.module_from_spec(spec)
    sys.path.insert(0,str(LINUX))
    try:spec.loader.exec_module(loaded)
    finally:sys.path.remove(str(LINUX))
    return loaded

def test_shape_self_test_makes_every_run_and_meets_every_expectation_on_the_emulation():
    present()
    done=subprocess.run([sys.executable,'-B',str(SCRIPT),'--self-test'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment(),timeout=180)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);assert result['schema']=='HOSTOPS02_TLS_PROBE_LINUX_ROOT_SHAPE_V1' and result['all_runs_made'] and result['all_expectations_met']
    assert sorted(result['runs']['cases'])==sorted(['verified','image_without_the_test_authority','certificate_of_another_name','port_refused',
                                                     'name_not_found','handshake_never_answered']) and len(result['expectations'])==15
    assert result['runs']['cases']['verified']['outcome']=='TLS_VERIFIED_TO_THE_PROVIDER_HOST'
    assert result['runs']['shape']['no_log_kept_by_the_engine'] is True and all(result['runs']['alarm'].values()) and len(result['runs']['alarm'])==5

def test_shape_expectations_are_false_without_runs_and_for_a_run_that_differs():
    present();shape=module('probe_shape')
    assert not any(shape.expectations({},c3.LEAF).values()),'a run that was not made meets nothing'
    engine=shape.Emulated();out=shape.collect(engine);assert all(shape.expectations(out,c3.LEAF).values())
    def changed(edit):
        copy=json.loads(json.dumps(out));edit(copy);return shape.expectations(copy,c3.LEAF)
    key='the verified probe names the leaf the server presented, for the provider name'
    assert changed(lambda o:o['cases']['verified']['probe']['tls'].update(leaf_sha256='0'*63+'1'))[key] is False
    assert shape.expectations(out,'0'*63+'1')[key] is False
    shape_key='the running container has the network bridge, no bind, --rm, no log kept by the engine, a read-only root, no capability, uid 0, the image by ID'
    assert changed(lambda o:o['shape'].update(network_bridge_only=False))[shape_key] is False
    assert changed(lambda o:o['shape'].update(no_log_kept_by_the_engine=False))[shape_key] is False
    alarm_key='the alarm of the script ends the container through docker-init with status 142, and the engine removes it'
    for member in ('returned','status_is_128_plus_sigalrm_through_init','ended_by_the_alarm_not_by_the_limit_of_the_cli','nothing_printed',
                   'no_container_of_its_name_listed_after'):
        assert changed(lambda o,member=member:o['alarm'].update({member:False}))[alarm_key] is False,member
    assert changed(lambda o:o.update(alarm=None))[alarm_key] is False and shape.report(dict(out,alarm=None),c3.LEAF)['all_runs_made'] is False
    m=c3.K().m
    assert shape.alarm_facts(m,{'returned':True,'returncode':142,'output':b''},1.1,'n',['other'])=={key:True for key in shape.alarm_facts(m,{},0,'n',None)}
    assert shape.alarm_facts(m,{'returned':True,'returncode':137,'output':b''},1.1,'n',[])['status_is_128_plus_sigalrm_through_init'] is False
    assert shape.alarm_facts(m,{'returned':True,'returncode':142,'output':b''},20.0,'n',[])['ended_by_the_alarm_not_by_the_limit_of_the_cli'] is False
    assert shape.alarm_facts(m,{'returned':True,'returncode':142,'output':b''},1.1,'n',['n'])['no_container_of_its_name_listed_after'] is False
    version_key='the verified probe reports the TLS version and cipher the server negotiated'
    assert changed(lambda o:o['cases']['verified']['probe']['tls'].update(cipher='TLS_AES_128_GCM_SHA256'))[version_key] is False
    assert changed(lambda o:o['server']['verified']['connections'][0].update(version='TLSv1.2'))[version_key] is False
    assert changed(lambda o:o['server']['verified']['connections'][0].update(version=None))[version_key] is False
    assert changed(lambda o:o['cases']['port_refused'].update(container_removed=False))['every probe ran under 20 s and left no container'] is False
    assert changed(lambda o:o['server']['verified']['connections'][0].update(application_bytes=1))['the server saw the provider name and no application byte'] is False
    assert changed(lambda o:o['server']['name_not_found']['questions'].append({'name':'other.example','type':1,'mode':'nxdomain'}))['the stand-in DNS was asked for the provider name only'] is False
    assert changed(lambda o:o['events'].update(attached_to_bridge_only=False))['the engine created, attached to bridge only, started, ended 0 and destroyed the verified probe'] is False
    assert changed(lambda o:o['cases']['handshake_never_answered']['container'].update(seconds=15))['the handshake that is never answered ends at the script bound, far inside the class'] is False
    assert changed(lambda o:o['cases']['image_without_the_test_authority']['probe']['tls'].update(verify_code=62))['an image without the test authority does not verify (unknown issuer)'] is False
    assert changed(lambda o:o['resolver'].update(name_servers_are_the_stand_in=False))['the container of the network bridge asks the stand-in, and the provider name resolves to the stand-in only'] is False
    events=[{'Type':'container','Action':action,'Actor':{'ID':'i','Attributes':{'name':'n','exitCode':'0'}}} for action in ('create','start','die','destroy')]
    events.insert(1,{'Type':'network','Action':'connect','Actor':{'ID':'x','Attributes':{'container':'i','name':'bridge'}}})
    assert all(shape.event_facts(events,'n').values()) and shape.event_facts(None,'n')=={'events_read':False}
    other=json.loads(json.dumps(events));other[1]['Actor']['Attributes']['name']='host';assert shape.event_facts(other,'n')['attached_to_bridge_only'] is False
    other=json.loads(json.dumps(events));other.pop();assert shape.event_facts(other,'n')['created_started_died_destroyed_in_order'] is False

def test_shape_refuses_to_run_outside_a_throwaway_runner():
    present()
    if not (sys.platform.startswith('linux') and os.geteuid()==0 and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes'):
        done=subprocess.run([sys.executable,'-B',str(SCRIPT),'/nonexistent','gateway'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment(),timeout=120)
        assert done.returncode==1 and done.stdout==b'' and b'REFUSED' in done.stderr

def query(name,kind,identifier=0x1234):
    return struct.pack('!HHHHHH',identifier,0x0100,1,0,0,0)+b''.join(bytes([len(part)])+part.encode() for part in name.split('.'))+b'\x00'+struct.pack('!HH',kind,1)
def ask(port,packet):
    client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);client.settimeout(3)
    try:
        client.sendto(packet,('127.0.0.1',port))
        try:return client.recvfrom(4096)[0]
        except socket.timeout:return None
    finally:client.close()

def test_the_dns_stand_in_answers_the_provider_name_only():
    present();stubs=module('stubs');server=stubs.DnsStub('127.0.0.1',0,'answer')
    try:
        answer=ask(server.port,query('socket.massive.com',1));identifier,flags,questions,count=struct.unpack('!HHHH',answer[:8])
        assert (identifier,flags&0x800f,questions,count)==(0x1234,0x8000,1,1) and answer.endswith(socket.inet_aton('127.0.0.1'))
        answer=ask(server.port,query('SOCKET.massive.COM',28));assert struct.unpack('!HH',answer[2:4]+answer[6:8])[0]&0x000f==0 and struct.unpack('!H',answer[6:8])[0]==0
        answer=ask(server.port,query('api.massive.com',1));assert struct.unpack('!H',answer[2:4])[0]&0x000f==3 and struct.unpack('!H',answer[6:8])[0]==0
        assert ask(server.port,b'\x00\x01garbage') is None
        server.mode='nxdomain';answer=ask(server.port,query('socket.massive.com',1))
        assert struct.unpack('!H',answer[2:4])[0]&0x000f==3 and struct.unpack('!H',answer[6:8])[0]==0
        assert [(row['name'],row['type'],row['mode']) for row in server.questions]==[('socket.massive.com',1,'answer'),('socket.massive.com',28,'answer'),
                                                                                    ('api.massive.com',1,'answer'),('socket.massive.com',1,'nxdomain')]
    finally:server.close()
    assert stubs.question_of(query('a.b',1)[:-2]) is None and stubs.question_of(b'') is None
    assert stubs.response(query('socket.massive.com',1),'127.0.0.1','answer',name='other.name')[3]&0x0f==3

@pytest.fixture(scope='module')
def certs(tmp_path_factory):
    if c3.openssl() is None:pytest.skip('no openssl program')
    return c3.certificates(tmp_path_factory.mktemp('authority'))

def test_the_tls_stand_in_is_reached_by_the_real_script_in_each_mode(certs):
    present();stubs=module('stubs');port=c3.closed_port();server=stubs.TlsStub('127.0.0.1',port,certs,'good')
    def probe():
        returncode,out,err,seconds=c3.run_script(c3.prelude([('127.0.0.1',port)],certs['ca'])+c3.K().m.script_bytes())
        assert returncode==0 and err==b'',err[-300:];return json.loads(out)
    try:
        row=probe();assert (row['status'],row['tls']['leaf_sha256'])==('TLS_VERIFIED',certs['leaf_sha256'])
        server.set_mode('other_name');row=probe();assert (row['status'],row['tls']['verify_code'])==('TLS_NOT_VERIFIED',62)
        server.set_mode('closed');row=probe();assert (row['status'],row['tcp']['code'])==('TCP_NOT_CONNECTED','TCP_REFUSED')
        server.set_mode('good');row=probe();assert row['status']=='TLS_VERIFIED'
    finally:server.close()
    assert [(row['mode'],row['server_name'],row['handshake'],row['application_bytes']) for row in server.connections]==[
        ('good','socket.massive.com',True,0),('other_name','socket.massive.com',False,None),('good','socket.massive.com',True,0)]

def test_run_sh_is_valid_sh_guards_the_runner_and_puts_the_engine_back():
    present();text=(LINUX/'run.sh').read_text()
    assert subprocess.run(['sh','-n',str(LINUX/'run.sh')]).returncode==0
    for needle in ('[ "${RUNNER_ENVIRONMENT:-}" = github-hosted ]','[ "${HOSTOPS_THROWAWAY_RUNNER:-}" = yes ]','sha256sum -c --quiet SHA256SUMS',
                   '../core/assemble.py --check .','trap cleanup EXIT','guard_set','guard_remove','REJECTED4','REJECTED6','daemon.json.saved',
                   'probe_shape.py "$WORK" "$GATEWAY"','for tool in iptables ip6tables; do','sudo -n ip6tables -w -L FORWARD -n',
                   "--format '{{.EnableIPv6}}'",'[ "$IPV6" = false ]','CONFIG_BEFORE=$(docker_config_state)','CONFIG_AFTER=$(docker_config_state)',
                   'if sudo -n cp "$DAEMON" "$WORK/daemon.json.saved"; then EXISTED=yes; SAVED=yes; else'):
        assert needle in text,needle
    assert text.count('SAVED=yes')==2 and 'daemon.json could not be saved"; else' not in text,'SAVED only after the copy succeeded'
    assert text.index('CONFIG_BEFORE=$(docker_config_state)')<text.index('probe_shape.py "$WORK"')<text.index('CONFIG_AFTER=$(docker_config_state)')
    assert 'find /root/.docker -printf' in text and 'cat /root/.docker' not in text,'the directory is listed, never read'
    pins=dict(reversed(line.split('  ',1)) for line in text.split("<<'PINS'")[1].split('\n',1)[1].split('PINS\n')[0].strip().splitlines())
    assert pins==c3.RELEASE_FILES
    assert 'BASE=python:3.12-alpine3.24@sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a' in text
    assert not re.search(r'(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])',text),'no address is written: the gateway is read on the runner'
    assert text.index('guard_set ||')<text.index('probe_shape.py "$WORK"')<text.index('REJECTED4=')
    assert text.index('[ "$IPV6" = false ]')<text.index('guard_set ||')
    assert 'set -e' not in text.split('\n# Nothing here relies')[0]
