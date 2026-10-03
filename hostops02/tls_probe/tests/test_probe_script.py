"""The REAL pinned script, in a child interpreter under `python -I -B -` as the container runs it, against a local TLS
server with a throwaway certificate authority made at test time. The test-only prelude (tests/c3.py) is written in front
of the pinned bytes: it answers the provider's name with the local server and adds the throwaway authority to the
default verifying context, nothing else. Each situation's line is compared, member for member, with the model the
emulated tests use (tests/c3.model_line), and must meet the source's own grammar; the server says which name the
client asked for and how many application bytes arrived after the handshake. Timings are checked against the
script's bounds. Nothing here reaches the network: every address is 127.0.0.1."""
import json
import os
import signal

import pytest

import c3

K=c3.K
needs_openssl=pytest.mark.skipif(c3.openssl() is None,reason='no openssl program to make the throwaway authority')

@pytest.fixture(scope='module')
def certs(tmp_path_factory):
    if c3.openssl() is None:pytest.skip('no openssl program')
    return c3.certificates(tmp_path_factory.mktemp('authority'))

def probe(addresses,ca=None,dns='answer',verifying=True,timeout=40,**situation):
    stdin=c3.prelude(addresses,ca,dns,verifying,**situation)+K().m.script_bytes()
    assert stdin.endswith(K().m.script_bytes()) and c3.PROVIDER.encode() in stdin[:len(stdin)-len(K().m.script_bytes())]
    returncode,out,err,seconds=c3.run_script(stdin,timeout)
    return returncode,out,err,seconds

def line_of(returncode,out,err):
    assert returncode==0 and err==b'' and out.endswith(b'\n') and out.count(b'\n')==1,(returncode,out,err[-400:])
    row=json.loads(out);assert out==(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode(),'compact, sorted, one line'
    assert K().m.line_grammar(row) is True,row
    return row

def same_as_model(row,kind,**exact):
    """Member for member equal to the model of that kind, timings aside (each checked for its bound), and the members
    of a handshake checked against what the test knows of the server."""
    model=c3.model_line(kind);seconds=K().m.PROBE_SECONDS
    for step,key in (('dns','dns'),('tcp','connect'),('tls','handshake')):
        assert (row[step]['ms'] is None)==(model[step]['ms'] is None),(step,row[step]['ms'])
        if row[step]['ms'] is not None:assert 0<=row[step]['ms']<seconds[key]*1000+800,(step,row[step]['ms'])
        row[step]['ms']=model[step]['ms']
    assert 0<=row['total_ms']<sum(seconds[key] for key in ('dns','connect','handshake'))*1000+1500;row['total_ms']=model['total_ms']
    for key,value in exact.items():
        step,member=key.split('__');assert row[step][member]==value,(key,row[step][member])
    if kind=='verified':
        assert row['tls']['version'] in K().m.TLS_VERSIONS and row['tls']['cipher']
        for member in ('version','cipher','leaf_sha256'):row['tls'][member]=model['tls'][member]
    assert row==model,(row,model)

@needs_openssl
def test_verified_handshake_with_the_default_context_sends_the_name_and_nothing_else(certs):
    server=c3.Server(certs,'good')
    try:row=line_of(*probe([('127.0.0.1',server.port)],certs['ca'])[:3])
    finally:server.close()
    assert row['tls']['leaf_sha256']==certs['leaf_sha256'],'the hash is the leaf the server presented'
    same_as_model(row,'verified')
    assert len(server.connections)==1 and server.connections[0]=={'server_name':'socket.massive.com','handshake':True,'application_bytes':0}

@needs_openssl
def test_an_authority_the_default_store_does_not_know_is_not_verified(certs):
    server=c3.Server(certs,'good')
    try:row=line_of(*probe([('127.0.0.1',server.port)],None)[:3])
    finally:server.close()
    assert row['tls']['verify_code'] in (19,20);row['tls']['verify_code']=20
    same_as_model(row,'untrusted');assert server.connections[0]['server_name']=='socket.massive.com' and server.connections[0]['handshake'] is False

@needs_openssl
def test_a_certificate_of_another_name_is_not_verified_for_the_provider(certs):
    server=c3.Server(certs,'other_name')
    try:row=line_of(*probe([('127.0.0.1',server.port)],certs['ca'])[:3])
    finally:server.close()
    same_as_model(row,'other_name',tls__verify_code=62)

@needs_openssl
def test_a_refused_port_and_then_the_next_address(certs):
    row=line_of(*probe([('127.0.0.1',c3.closed_port())],certs['ca'])[:3]);same_as_model(row,'refused')
    server=c3.Server(certs,'good')
    try:row=line_of(*probe([('127.0.0.1',c3.closed_port()),('127.0.0.1',server.port)],certs['ca'])[:3])
    finally:server.close()
    assert (row['status'],row['dns']['addresses'],row['dns']['ipv4'],row['tcp']['attempts'],row['tcp']['family'])==('TLS_VERIFIED',2,2,2,'ipv4')
    assert len(server.connections)==1 and server.connections[0]['application_bytes']==0

@pytest.mark.parametrize('dns,kind',[('nxdomain','nxdomain'),('failed','dns_failed')])
def test_a_name_that_does_not_resolve(dns,kind):
    row=line_of(*probe([],None,dns)[:3]);same_as_model(row,kind)

def test_an_answer_without_an_address():
    row=line_of(*probe([],None,'answer')[:3]);same_as_model(row,'no_address')

def test_a_resolver_that_does_not_answer_is_bounded_by_its_own_seconds():
    returncode,out,err,seconds=probe([],None,'hang')
    row=line_of(returncode,out,err);assert 4.0<=seconds<8.0 and 4000<=row['dns']['ms']<5000,(seconds,row['dns']['ms'])
    same_as_model(row,'dns_timeout')

@needs_openssl
def test_a_server_that_never_answers_the_handshake_is_bounded_by_its_own_seconds(certs):
    server=c3.Server(certs,'hang')
    try:returncode,out,err,seconds=probe([('127.0.0.1',server.port)],certs['ca'])
    finally:server.close()
    row=line_of(returncode,out,err);assert 4.0<=seconds<8.0 and 4000<=row['tls']['ms']<5000,(seconds,row['tls']['ms'])
    same_as_model(row,'hang')

@needs_openssl
def test_a_server_that_is_not_tls_is_a_protocol_error(certs):
    server=c3.Server(certs,'garbage')
    try:row=line_of(*probe([('127.0.0.1',server.port)],certs['ca'])[:3])
    finally:server.close()
    same_as_model(row,'garbage')

@needs_openssl
def test_a_context_that_would_not_check_the_name_is_never_used(certs):
    server=c3.Server(certs,'good')
    try:row=line_of(*probe([('127.0.0.1',server.port)],certs['ca'],verifying=False)[:3])
    finally:server.close()
    same_as_model(row,'context');assert server.connections==[],'no connection is opened with a context that does not verify'

def test_at_most_sixteen_addresses_are_counted_and_tried_within_the_connect_seconds():
    row=line_of(*probe([('127.0.0.1',c3.closed_port()+index) for index in range(17)])[:3])
    assert (row['status'],row['dns']['addresses'],row['dns']['ipv4'],row['tcp']['attempts'],row['tcp']['code'])==('TCP_NOT_CONNECTED',16,16,16,'TCP_REFUSED')

def test_a_connect_that_never_completes_is_bounded_by_its_own_seconds():
    returncode,out,err,seconds=probe([('127.0.0.1',c3.closed_port())],connect='hang')
    row=line_of(returncode,out,err);assert 4.0<=seconds<8.0 and 3900<=row['tcp']['ms']<5000,(seconds,row['tcp']['ms'])
    same_as_model(row,'tcp_timeout')

@needs_openssl
def test_the_handshake_has_its_own_seconds_whatever_the_connect_took(certs):
    """The first address takes three of the four connect seconds and is refused; the second connects at once to a server
    that never answers: the handshake still gets its full four seconds, not what was left of the connect's."""
    server=c3.Server(certs,'hang')
    try:returncode,out,err,seconds=probe([('127.0.0.1',c3.closed_port()),('127.0.0.1',server.port)],certs['ca'],connect='slow')
    finally:server.close()
    row=line_of(returncode,out,err);assert 3000<=row['tcp']['ms']<4000 and 4000<=row['tls']['ms']<5000,(row['tcp']['ms'],row['tls']['ms'])
    assert (row['status'],row['tls']['code'],row['tcp']['attempts'],row['dns']['addresses'])==('TLS_HANDSHAKE_FAILED','TLS_HANDSHAKE_TIMEOUT',2,2)

def test_the_prelude_resolves_no_other_name_and_never_through_the_network():
    stdin=c3.prelude([('127.0.0.1',1)])+b"import socket\ntry:\n    socket.getaddrinfo('example.com', 443)\nexcept socket.gaierror:\n    print('REFUSED')\n"
    returncode,out,err,seconds=c3.run_script(stdin);assert (returncode,out)==(0,b'REFUSED\n')

def test_an_exception_inside_the_script_is_its_own_constant_status():
    row=line_of(*probe([('127.0.0.1',c3.closed_port())],fail=True)[:3]);same_as_model(row,'failed')

def test_the_alarm_ends_the_script_by_itself_before_the_limit_of_the_docker_cli():
    """A resolver thread that is never given up on (the join of the prelude waits forever): the kernel's alarm, armed
    by the first statement, ends the interpreter at 14 s with SIGALRM, as docker-init reports it (status 142)."""
    stdin=c3.prelude([],None,'hang',True,hang=60).replace(b'_socket.getaddrinfo=_getaddrinfo',
           b'_socket.getaddrinfo=_getaddrinfo\nimport threading as _threading\n_join=_threading.Thread.join\n_threading.Thread.join=lambda self,timeout=None:_join(self)')
    returncode,out,err,seconds=c3.run_script(stdin+K().m.script_bytes(),timeout=40)
    assert returncode==-signal.SIGALRM and out==b'' and 13.5<=seconds<18,(returncode,out,seconds)
    assert 128+signal.SIGALRM==K().m.PROBE_ALARM_STATUS
