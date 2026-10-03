"""C3 on the emulated host: the plan and its refusals from the bytes, the literal effects, every refusal of the
precheck (nothing started), the one container (what the engine is asked for, byte for byte), every verdict after it,
and the receipt (counts, booleans, constant codes, hashes and timings only). The container is the model of
tests/c3.py; tests/test_probe_script.py runs the real script and compares it with that model."""
import ast
from datetime import timedelta
import json
import re

import pytest

import c3
import family as f
import hostemu

K=c3.K
refusal=f.refusal

def go16(docs):return docs.go16()
def name_of(docs):return 'hostops02-tls-'+docs.go16()
def run(docs,host,**options):
    receipt=docs.run(host,**options);assert f.sealed(receipt) and receipt['schema']==K().m.RECEIPT_SCHEMA;return receipt
def docker_words(host):
    """The docker commands of a run, as words after the binary (the image ID and the tag shortened to labels)."""
    out=[]
    for entry in host.commands:
        argv=entry['argv'][1:]
        if argv[:2]==['image','inspect']:out.append(('image',argv[-1]))
        elif argv[:2]==['ps','-a']:out.append(('ps',))
        elif argv[:1]==['run']:out.append(('run',))
        else:out.append(tuple(argv[:2]))
    return out
def intercept(host,words,returncode,output):
    """The emulated CLI answers (returncode, output) to a command whose argv holds every one of words."""
    real=host.docker.run
    def run(args,stdin=None,environment=None):
        if all(word in args for word in words):return returncode,output
        return real(args,stdin,environment)
    host.docker.run=run
NOTHING_STARTED={'image':None,'retention_tag':None,'containers_before':None,'name_free':None}


# ---------------------------------------------------------------- the plan, from its bytes
@pytest.mark.parametrize('field,value,code',[
    ('evidence_boot_id_sha256',None,'EVIDENCE_BOOT_UNBOUND'),('evidence_boot_id_sha256','0'*64,'EVIDENCE_BOOT_UNBOUND'),
    ('evidence_boot_id_sha256','A'*64,'EVIDENCE_BOOT_UNBOUND'),('evidence_boot_id_sha256','a'*63,'EVIDENCE_BOOT_UNBOUND'),
    ('script_sha256',None,'SCRIPT_NOT_THE_PINNED_HASH'),('script_sha256','a'*64,'SCRIPT_NOT_THE_PINNED_HASH'),
    ('image_revision',None,'IMAGE_REVISION_NOT_THE_RELEASE'),('image_revision','0'*40,'IMAGE_REVISION_NOT_THE_RELEASE'),
    ('image_revision','DD4EC4BB8DAB4D8B0372B0F9EABC90BF6443E858','IMAGE_REVISION_NOT_THE_RELEASE'),
    ('image_revision','dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e85','IMAGE_REVISION_NOT_THE_RELEASE'),
    ('retention_tag',None,'RETENTION_TAG_INVALID'),('retention_tag','c3po/backend:production','RETENTION_TAG_INVALID'),
    ('retention_tag','c3po/web:massive-supervisor-epoch03','RETENTION_TAG_INVALID'),('retention_tag','c3po/backend:massive-supervisor-','RETENTION_TAG_INVALID'),
    ('retention_tag','c3po/backend:massive-supervisor-'+'a'*42,'RETENTION_TAG_INVALID'),('retention_tag','c3po/backend:massive-supervisor-Epoch03','RETENTION_TAG_INVALID'),
    ('retention_tag','c3po/backend@sha256:'+'a'*64,'RETENTION_TAG_INVALID'),('retention_tag','c3po/backend:massive-supervisor-epoch03 ','RETENTION_TAG_INVALID'),
    ('image_id',None,'IMAGE_ID'),('image_id','c3po/backend:production','IMAGE_ID'),('image_id','sha256:'+'A'*64,'IMAGE_ID'),
    ('image_id',hostemu.BACKEND[:-1],'IMAGE_ID'),
])
def test_every_member_of_the_plan_is_refused_from_its_bytes_before_any_claim(field,value,code,tmp_path):
    docs,_=c3.case();docs.plan[field]=value;docs.chain()
    assert refusal(docs.authenticate)==code
    result=docs.run(f.Untouchable());assert (result['status'],result['code'],result['phase_reached'])==('REFUSED',code,'AUTHENTICATION')
    dispatch=f.Dispatch(docs,tmp_path);assert refusal(dispatch.prepare)==code and not dispatch.claims()

def test_the_members_accept_exactly_their_grammar_at_its_edges():
    m=K().m
    for tag in ('c3po/backend:massive-supervisor-a','c3po/backend:massive-supervisor-'+'a'*41,'c3po/backend:massive-supervisor-0.1-x'):
        m.validate_members(c3.fields(retention_tag=tag))
    for tag in ('c3po/backend:massive-supervisor-.x','c3po/backend:massive-supervisor--x','c3po/backend:massive-supervisor_x'):
        assert refusal(lambda:m.validate_members(c3.fields(retention_tag=tag)))=='RETENTION_TAG_INVALID'
    m.validate_members(c3.fields());assert m.RELEASE_REVISION==c3.RELEASE==hostemu.REVISION

def test_the_window_is_validated_on_its_own_and_before_the_members():
    m=K().m
    window={'not_before':'2026-10-04T11:45:00+00:00','expires_at':'2026-10-04T12:30:00+00:00'};m.validate_window(window)
    for start,end,code in (('2026-10-03T11:45:00+00:00','2026-10-03T11:50:00+00:00','PROBE_DAY_NOT_IN_SCOPE'),
                           ('2026-10-05T11:45:00+00:00','2026-10-05T11:50:00+00:00','PROBE_DAY_NOT_IN_SCOPE'),
                           ('2026-10-04T11:44:59+00:00','2026-10-04T11:50:00+00:00','PROBE_WINDOW_OUTSIDE_THE_BAND'),
                           ('2026-10-04T12:20:00+00:00','2026-10-04T12:30:00.000001+00:00','PROBE_WINDOW_OUTSIDE_THE_BAND'),
                           ('2026-10-04T00:00:00+00:00','2026-10-04T00:05:00+00:00','PROBE_WINDOW_OUTSIDE_THE_BAND'),
                           ('2026-10-04T23:50:00+00:00','2026-10-04T23:55:00+00:00','PROBE_WINDOW_OUTSIDE_THE_BAND')):
        assert refusal(lambda:m.validate_window({'not_before':start,'expires_at':end}))==code,(start,end)
    plan=dict(c3.fields(retention_tag=None),window={'not_before':'2026-10-03T12:00:00+00:00','expires_at':'2026-10-03T12:05:00+00:00'})
    assert refusal(lambda:m.validate_plan(plan))=='PROBE_DAY_NOT_IN_SCOPE'
    plan['window']=window;assert refusal(lambda:m.validate_plan(plan))=='RETENTION_TAG_INVALID'

def test_a_window_of_the_band_longer_than_the_gate_is_signed_and_the_gate_is_the_short_window():
    """A1 section 5: the request and the authority carry the band, the GO the short window (at most 900 s)."""
    docs,host=c3.case();band=[c3.NOW.replace(hour=11,minute=45),c3.NOW.replace(hour=12,minute=30)]
    for document in (docs.request,docs.authority):document.update(not_before=band[0].isoformat(),not_after=band[1].isoformat())
    docs.plan['window']={'not_before':band[0].isoformat(),'expires_at':band[1].isoformat()}
    docs.go.update(not_before=c3.NOW.isoformat(),not_after=(c3.NOW+timedelta(seconds=900)).isoformat());docs.chain()
    plan,gate=docs.authenticate();assert (gate.start,gate.end)==(c3.NOW,c3.NOW+timedelta(seconds=900))
    assert run(docs,host)['outcome']==K().m.COMPLETE_OUTCOME
    docs.go['not_after']=(c3.NOW+timedelta(seconds=901)).isoformat();docs.chain();assert refusal(docs.authenticate)=='WINDOW_SPAN'

def test_the_evidence_names_the_precheck_and_the_provisioning():
    m=K().m;assert m.EVIDENCE_OPERATIONS==('GO_READONLY_HOSTOPS_PRECHECK_01','GO_WRITE_SUPERVISOR_READER_PROVISION_01') and m.EVIDENCE_REQUIRED
    for keep in (0,1):
        docs,_=c3.case();docs.request['evidence']=[docs.request['evidence'][keep]];docs.chain()
        assert refusal(docs.authenticate)=='EVIDENCE_OPERATION_MISSING'


# ---------------------------------------------------------------- what the signers see
def expected_effects(plan):
    return {'operation':'GO_READONLY_HOSTOPS02_TLS_PROBE_01',
            'container':{'image_id':plan['image_id'],'image_revision':plan['image_revision'],'retention_tag':plan['retention_tag'],
                         'docker_arguments':['run','--rm','-i','--pull','never','--init','--user','0:0','--network','bridge','--read-only','--cap-drop','ALL',
                                             '--security-opt','no-new-privileges','--log-driver','none','--name','hostops02-tls-<first 16 hex of the GO sha256>',
                                             plan['image_id'],'python','-I','-B','-'],
                         'network':'bridge','binds':[],'environment_file':None,'docker_config_variable':None,'token':None,'log_driver':'none',
                         'standard_input':{'sha256':K().m.PROBE_SCRIPT_SHA256,'bytes':len(K().m.PROBE_SCRIPT.encode())},
                         'time_limit_seconds':20,'alarm_seconds':14,'removed_by_the_engine':True},
            'provider':{'host':'socket.massive.com','port':443,
                        'source':'c3po/backend/app/r2d2_v2_massive_transport.py:99 (wss://socket.massive.com/stocks, wss default port 443) and '
                                 'c3po/deployment/massive-supervisor/README.md:580 at dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858',
                        'dns':'A and AAAA queries for socket.massive.com to the resolvers the engine gives the network bridge',
                        'tcp_attempts_max':16,'connections_established_max':1,'tls_handshakes_max':1,
                        'application_bytes':0,'http_request':False,'credential':False},
            'signature':'individual, by the hash of its own request (A1 rev 2, section 4.2, row C3): a container run, not a read (A1 4.2), never run '
                        'by the grid of reads of any authority, and never a listed read (sheet rev5, item 13: the TLS probe stays out)',
            'probe_seconds':{'dns':4,'connect':4,'handshake':4,'alarm':14},
            'band':{'day':'2026-10-04','not_before':'2026-10-04T11:45:00+00:00','not_after':'2026-10-04T12:30:00+00:00'},
            'success_outcome':'TLS_VERIFIED_TO_THE_PROVIDER_HOST','evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'writes':0,'removes':[],'activation':False,'containers_run':1}

def test_effects_are_literal_and_name_every_word_the_engine_gets():
    docs,host=c3.case();m=K().m
    assert docs.authority['effects']==docs.go['effects']==expected_effects(docs.plan)==json.loads(m.canonical(m.effects_of(docs.plan)))
    receipt=run(docs,host);call=host.docker.runs[0]
    argv=[entry['argv'][1:] for entry in host.commands if entry['argv'][1:2]==['run']][0]
    assert argv==[word.replace('<first 16 hex of the GO sha256>',docs.go16()) for word in expected_effects(docs.plan)['container']['docker_arguments']]
    assert receipt['effects']==expected_effects(docs.plan) and call.name==name_of(docs)
    other=c3.fields(image_id=hostemu.OTHER,retention_tag='c3po/backend:massive-supervisor-x')
    assert m.effects_of(other)==expected_effects(other) and m.success_of(other)==m.COMPLETE_OUTCOME

def test_the_row_is_the_prefix_of_the_core_with_the_network_bridge_and_nothing_else():
    m=K().m;row=m.COMMANDS[m.RUN_ROW]
    assert row['argv']==m.PROBE_PREFIX==['bridge' if word=='none' else word for word in m.RUN_PREFIX]+['--log-driver','none'] and row['argv']!=m.RUN_PREFIX
    assert m.SCOPE['container']['log_driver']=='none' and m.SCOPE['signature']==m.SIGNATURE_REGIME==expected_effects(c3.fields())['signature']
    assert m.SCOPE['script']['tcp_attempts_max']==m.MAX_ADDRESSES_COUNTED==16 and m.SCOPE['script']['connections_established_max']==1
    assert 'a second established connection, a second handshake, or any attempt after a handshake' in m.SCOPE['never']
    assert 'a log of the container output kept by the engine' in m.SCOPE['never']
    assert (row['kind'],row['class'],row['stdin'],row['tail'],row['tool'])==('CONTAINER','RUN_SHORT',True,[],'docker')
    assert m.COMMAND_CLASSES['RUN_SHORT']['seconds']==20 and m.effects_budget(m.RUN_ROW)==24
    assert set(m.COMMANDS)=={'image','container_list','probe'} and m.BINARIES=={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
    assert (m.COMMANDS['image']['kind'],m.COMMANDS['container_list']['kind'])==('READ','READ')
    assert m.WRITES_ALLOWED is False and m.ACTIVATION_ALLOWED is False and m.DATE_CLASS=='READ' and m.MAX_GATE_SPAN_SECONDS==900
    assert m.OPERATION=='GO_READONLY_HOSTOPS02_TLS_PROBE_01' and m.PHASE=='READONLY_SUPERVISOR_TLS_PROBE'

def test_script_constants_agree_with_the_source_and_the_alarm_comes_first():
    """The seconds, the host and the port of the script's text are the source's; the alarm is armed before any import
    that could block, and fires before the class limit of the docker CLI with room for the engine to remove the container."""
    m=K().m;tree=ast.parse(m.PROBE_SCRIPT);values={}
    for node in tree.body:
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and isinstance(node.value,ast.Constant):values[node.targets[0].id]=node.value.value
    assert values['HOST']==m.PROVIDER_HOST=='socket.massive.com' and values['PORT']==m.PROVIDER_PORT==443
    assert (values['DNS_SECONDS'],values['CONNECT_SECONDS'],values['HANDSHAKE_SECONDS'])==(m.PROBE_SECONDS['dns'],m.PROBE_SECONDS['connect'],m.PROBE_SECONDS['handshake'])
    assert values['MAX_ADDRESSES']==m.MAX_ADDRESSES_COUNTED
    first,second=tree.body[:2]
    assert isinstance(first,ast.Import) and [alias.name for alias in first.names]==['signal']
    assert ast.dump(second)==ast.dump(ast.parse('signal.alarm(%d)'%m.PROBE_SECONDS['alarm']).body[0])
    assert sum(m.PROBE_SECONDS[key] for key in ('dns','connect','handshake'))<m.PROBE_SECONDS['alarm']<m.COMMAND_CLASSES['RUN_SHORT']['seconds']-4
    assert m.PROBE_ALARM_STATUS==128+14 and "'application_bytes_sent': 0" in m.PROBE_SCRIPT and m.LINE_SCHEMA in m.PROBE_SCRIPT
    assert m.script_bytes()==m.PROBE_SCRIPT.encode('ascii') and len(m.script_bytes())==m.PROBE_SCRIPT_BYTES and f.sha(m.script_bytes())==m.PROBE_SCRIPT_SHA256
    calls={node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)}
    assert calls&{'send','sendall','sendto','sendmsg','request','urlopen','unwrap','makefile','recv','read'}==set(),'the script sends and reads nothing after the handshake'
    writes=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='write']
    assert len(writes)==1 and ast.dump(writes[0].func.value)==ast.dump(ast.parse('sys.stdout',mode='eval').body),'the one write is the line on standard output'
    assert 'create_default_context' in calls and 'wrap_socket' in calls and 'do_handshake' in calls and 'getpeercert' in calls

def test_a_script_that_is_not_the_pinned_one_is_never_given(monkeypatch):
    m=K().m;docs,host=c3.case()
    monkeypatch.setattr(m,'PROBE_SCRIPT',m.PROBE_SCRIPT+'\n')
    result=run(docs,host);assert (result['status'],result['code'],result['phase_reached'])==('REFUSED','SCRIPT_NOT_THE_PINNED_HASH','AUTHENTICATION') and host.log==[]
    assert refusal(docs.authenticate)=='SCRIPT_NOT_THE_PINNED_HASH','the dispatcher refuses it before any claim'
    monkeypatch.setattr(m,'PROBE_SCRIPT',m.PROBE_SCRIPT[:-1].replace("PORT = 443","PORT = 444"))
    assert refusal(m.script_bytes)=='SCRIPT_NOT_THE_PINNED_HASH'


# ---------------------------------------------------------------- the complete run
def test_complete_run_reads_four_times_runs_once_and_reports_only_counts_booleans_codes_hashes_and_timings():
    docs,host=c3.case();m=K().m;receipt=run(docs,host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('METADATA_ONLY_REQUIRES_REVIEW','TLS_VERIFIED_TO_THE_PROVIDER_HOST',None,'CONTAINER')
    assert docker_words(host)==[('image',hostemu.BACKEND),('image',c3.TAG),('ps',),('run',),('ps',)]
    assert [entry['docker_config'] for entry in host.commands]==[None]*5 and all(entry['variables']=={} for entry in host.commands)
    assert [entry['seconds'] for entry in host.commands]==[8,8,8,20,8] and host.commands[3]['stdin']==m.script_bytes()
    assert receipt['precheck']=={'image':{'id_as_signed':True,'revision_as_signed':True},'retention_tag':{'resolves_to_the_signed_image':True},
                                 'containers_before':8,'name_free':True}
    assert receipt['container']['name']==name_of(docs) and (receipt['container']['state'],receipt['container']['returncode'],receipt['container']['code'])==('RETURNED',0,None)
    assert type(receipt['container']['seconds']) is float or receipt['container']['seconds']==0
    line=c3.model_line('verified');probe=receipt['probe']
    assert probe=={'returncode':0,'bytes':len(c3.line_bytes(line)),'sha256':f.sha(c3.line_bytes(line)),'one_json_line':True,'valid':True,'status':'TLS_VERIFIED',
                   'context':line['context'],'dns':line['dns'],'tcp':line['tcp'],'tls':line['tls'],'application_bytes_sent':0,'total_ms':line['total_ms']}
    assert receipt['containers_after']=={'status':'COMPLETE','code':None,'before':8,'after':8,'not_there_before':0,'name_present':False,'rows':[]}
    assert (receipt['tls_verified'],receipt['container_removed'],receipt['writes'],receipt['containers_run'])==(True,True,0,1)
    assert receipt['commands_started']=={'READ':4,'CONTAINER':1,'EFFECT':0} and receipt['mutating_calls']['issued']==0
    assert host.mutating()==[] and host.fds=={}
    raw=f.line(receipt);assert len(raw)<16000 and b'never-emit' not in raw and hostemu.SECRET.encode() not in raw
    assert not re.search(rb'(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])',raw),'no address'
    assert set(receipt)=={'schema','operation','status','outcome','code','scope_sha256','core_sha256','activation_performed','daemon_reload_performed',
                          'secret_bytes_in_receipt','ready','size_reductions','metadata_sha256','request_sha256','authority_sha256','go_sha256',
                          'payload_sha256','host_binding_sha256','observed_at','effects','clock','commands_started','mutating_calls','precheck',
                          'container','probe','containers_after','tls_verified','container_removed','writes','containers_run','phase_reached'}

def test_the_budget_before_the_container_is_its_class_and_the_reserve():
    m=K().m
    docs,host=c3.case();budget=f.Budget(c3.NOW).attach(host).cost(1.2345,'run','--rm');receipt=run(docs,host,**budget.options())
    assert receipt['outcome']==m.COMPLETE_OUTCOME and receipt['container']['seconds']==1.234,'the seconds of the run, to the millisecond'
    for cost,expected in ((18.0,('METADATA_ONLY_REQUIRES_REVIEW',None)),(18.01,('REFUSED','BUDGET_INSUFFICIENT_BEFORE_THE_CONTAINER'))):
        docs,host=c3.case();budget=f.Budget(c3.NOW).attach(host).cost(cost,'image','inspect')
        receipt=run(docs,host,**budget.options())
        assert (receipt['status'],receipt['code'])==expected,cost
        assert bool(host.container_runs())==(expected[1] is None)
    assert m.effects_budget(m.RUN_ROW)==24


# ---------------------------------------------------------------- refusals of the precheck: nothing started
def refused(receipt,code,host,commands=None):
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('REFUSED','REFUSED_NO_CONTAINER_STARTED',code,'PRECHECK'),receipt['code']
    assert host.container_runs()==[] and receipt['container'] is None and receipt['probe'] is None and receipt['containers_after'] is None
    assert (receipt['tls_verified'],receipt['container_removed'],receipt['containers_run'])==(False,None,0)
    if commands is not None:assert docker_words(host)==commands
    assert host.fds=={}

def test_executor_must_be_root_before_anything():
    for actor in ((0,1000),(1000,0)):
        docs,host=c3.case();host.actor=actor;receipt=run(docs,host);refused(receipt,'EXECUTOR_IDENTITY',host,[])
        assert receipt['precheck']==NOTHING_STARTED and not [entry for entry in host.log if entry[0]!='identity']

def test_evidence_of_another_boot_is_refused_before_any_docker_command():
    docs,host=c3.case(evidence_boot_id_sha256='e'*64);receipt=run(docs,host);refused(receipt,'EVIDENCE_FROM_EARLIER_BOOT',host,[])
    docs,host=c3.case();host.tree.get('/proc/sys/kernel/random/boot_id').content=b'not a boot id\n';refused(run(docs,host),'BOOT_ID_INVALID',host,[])

def test_image_absent_other_or_without_the_release_label_is_refused():
    docs,host=c3.case(image_id='sha256:'+'ab'*32);refused(run(docs,host),'IMAGE_ABSENT_OR_UNREADABLE',host,[('image','sha256:'+'ab'*32)])
    docs,host=c3.case();c3.backend(host)['Config']['Labels']['org.opencontainers.image.revision']='0'*40
    receipt=run(docs,host);refused(receipt,'IMAGE_REVISION_MISMATCH',host,[('image',hostemu.BACKEND)]);assert receipt['precheck']['image'] is None
    docs,host=c3.case();del c3.backend(host)['Config']['Labels']['org.opencontainers.image.revision'];refused(run(docs,host),'IMAGE_REVISION_MISMATCH',host)
    docs,host=c3.case()
    intercept(host,[hostemu.BACKEND,'inspect'],0,json.dumps({'id':hostemu.OTHER,'repo_tags':['c3po/backend:production'],'revision':hostemu.REVISION}).encode()+b'\n')
    refused(run(docs,host),'IMAGE_ID_MISMATCH',host)
    docs,host=c3.case();intercept(host,[hostemu.BACKEND,'inspect'],0,b'{"id":"sha256:x"}\n');refused(run(docs,host),'IMAGE_METADATA_INVALID',host)
    docs,host=c3.case();intercept(host,[hostemu.BACKEND,'inspect'],0,b'not json\n');refused(run(docs,host),'JSON_INVALID',host)

def test_retention_tag_absent_or_on_another_image_is_refused():
    docs,host=c3.case();c3.backend(host)['RepoTags'].remove(c3.TAG)
    receipt=run(docs,host);refused(receipt,'RETENTION_TAG_ABSENT_OR_UNREADABLE',host,[('image',hostemu.BACKEND),('image',c3.TAG)])
    assert receipt['precheck']=={'image':{'id_as_signed':True,'revision_as_signed':True},'retention_tag':None,'containers_before':None,'name_free':None}
    docs,host=c3.case();c3.backend(host)['RepoTags'].remove(c3.TAG)
    [item for item in host.docker.images if item['Id']==hostemu.OTHER][0]['RepoTags'].append(c3.TAG)
    refused(run(docs,host),'RETENTION_TAG_NOT_ON_THE_SIGNED_IMAGE',host,[('image',hostemu.BACKEND),('image',c3.TAG)])
    docs,host=c3.case()          # the CLI answers the signed ID for the tag, but the tag is not among the image's tags
    intercept(host,[c3.TAG],0,json.dumps({'id':hostemu.BACKEND,'repo_tags':['c3po/backend:production'],'revision':hostemu.REVISION}).encode()+b'\n')
    refused(run(docs,host),'RETENTION_TAG_NOT_ON_THE_SIGNED_IMAGE',host)

def test_container_listing_that_fails_or_a_name_already_taken_is_refused():
    docs,host=c3.case();host.docker.ps_returncode=1;receipt=run(docs,host)
    refused(receipt,'CONTAINER_LISTING_FAILED',host,[('image',hostemu.BACKEND),('image',c3.TAG),('ps',)])
    docs,host=c3.case();intercept(host,['ps','-a'],0,b'{"id":"x","name":"y","state":"running"}\n');refused(run(docs,host),'CONTAINER_LIST_INVALID',host)
    docs,host=c3.case();host.docker.containers.append(hostemu.container(name_of(docs),hostemu.BACKEND,hostemu.BACKEND,[],running=False))
    receipt=run(docs,host);refused(receipt,'CONTAINER_NAME_TAKEN',host);assert receipt['precheck']['name_free'] is False and receipt['precheck']['containers_before']==9
    docs,host=c3.case();host.docker.containers.append(hostemu.container('hostops02-tls-'+'0'*16,hostemu.BACKEND,hostemu.BACKEND,[],running=False))
    assert run(docs,host)['outcome']=='TLS_VERIFIED_TO_THE_PROVIDER_HOST','another GO left its own container: not this name'

def test_docker_that_cannot_be_trusted_or_started_is_a_refusal():
    docs,host=c3.case();host.tree.get('/usr/bin/docker').mode=0o775;receipt=run(docs,host)
    refused(receipt,'BINARY_UNAVAILABLE_OR_UNSAFE',host,[])
    docs,host=c3.case();host.absent={'docker'};refused(run(docs,host),'COMMAND_NOT_STARTED',host,[])

def test_a_failing_system_call_of_the_precheck_is_told_apart_from_any_other_failure():
    for kind,code in ((OSError,'PRECHECK_OS_ERROR'),(RuntimeError,'PRECHECK_FAILED')):
        docs,host=c3.case()
        def hook(host,name,detail,calls,kind=kind):
            if name=='open' and detail and detail[0]=='/proc/sys/kernel/random/boot_id':raise kind(5,'injected') if kind is OSError else kind('injected')
        host.hook=hook;refused(run(docs,host),code,host,[])

def test_a_read_of_the_precheck_that_hangs_is_a_refusal_with_nothing_started():
    docs,host=c3.case();host.hang={('ps','-a')};refused(run(docs,host),'COMMAND_TIMEOUT',host)

def test_an_expiry_inside_the_precheck_is_a_refusal():
    docs,host=c3.case();budget=f.Budget(c3.NOW).attach(host).cost(400,'ps','-a')
    receipt=run(docs,host,**budget.options());refused(receipt,'GO_EXPIRED',host)


# ---------------------------------------------------------------- the container
def verdict(receipt):return receipt['status'],receipt['outcome'],receipt['code']

def test_a_container_the_engine_never_started_is_a_refusal_after_the_precheck():
    docs,host=c3.case();host.absent={('run','--rm')};receipt=run(docs,host)
    assert verdict(receipt)==('REFUSED','REFUSED_NO_CONTAINER_STARTED','COMMAND_NOT_STARTED') and receipt['phase_reached']=='CONTAINER_NOT_STARTED'
    assert receipt['container']=={'name':name_of(docs),'state':'NOT_STARTED','returncode':None,'code':'COMMAND_NOT_STARTED','seconds':receipt['container']['seconds']}
    assert receipt['probe'] is None and receipt['containers_after'] is None and receipt['containers_run']==0 and receipt['precheck']['name_free'] is True

@pytest.mark.parametrize('kind,code',[('nxdomain','DNS_NAME_NOT_RESOLVED'),('dns_timeout','DNS_TIMEOUT'),('dns_failed','DNS_FAILED'),('no_address','DNS_NO_ADDRESS'),
                                      ('refused','TCP_REFUSED'),('tcp_timeout','TCP_TIMEOUT'),('unreachable','TCP_UNREACHABLE'),
                                      ('untrusted','TLS_CERTIFICATE_NOT_VERIFIED'),('other_name','TLS_CERTIFICATE_NOT_VERIFIED'),
                                      ('hang','TLS_HANDSHAKE_TIMEOUT'),('garbage','TLS_PROTOCOL_ERROR'),('reset','TLS_CONNECTION_ERROR'),
                                      ('context','TLS_CONTEXT_NOT_VERIFYING'),('optional','TLS_CONTEXT_NOT_VERIFYING'),('failed','PROBE_FAILED')])
def test_a_valid_line_that_is_not_a_verified_tls_is_the_probes_own_answer(kind,code):
    docs,host=c3.case();host.docker.on_run=c3.answers(kind);receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','PROBE_RAN_TLS_NOT_VERIFIED',code)
    line=c3.model_line(kind);probe=receipt['probe']
    assert probe['valid'] and probe['status']==line['status'] and (probe['dns'],probe['tcp'],probe['tls'],probe['context'])==(line['dns'],line['tcp'],line['tls'],line['context'])
    assert receipt['tls_verified'] is False and receipt['container_removed'] is True and receipt['containers_after']['status']=='COMPLETE'

def test_a_verified_line_with_an_engine_status_or_something_left_is_a_finding_beside_it():
    def leave(name):
        def before(call):host.docker.containers.append(hostemu.container(name or call.name,hostemu.BACKEND,hostemu.BACKEND,[],running=True))
        return before
    for status in (125,126,127):
        docs,host=c3.case();host.docker.on_run=c3.answers('verified',returncode=status);receipt=run(docs,host)
        assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','TLS_VERIFIED_WITH_FINDINGS','ENGINE_STATUS_AFTER_A_VERIFIED_PROBE')
        assert receipt['tls_verified'] is True and receipt['container']['returncode']==status
    docs,host=c3.case();host.docker.on_run=c3.answers('verified',before=leave(None));receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','TLS_VERIFIED_WITH_FINDINGS','CONTAINER_OF_THE_PROBE_STILL_LISTED')
    after=receipt['containers_after'];assert (after['name_present'],after['not_there_before'],after['after'],receipt['container_removed'])==(True,1,9,False)
    assert after['rows']==[{'id':host.docker.containers[-1]['Id'],'state':'running','is_the_probe':True}]
    docs,host=c3.case();host.docker.on_run=c3.answers('verified',before=leave('someone-else'));receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','TLS_VERIFIED_WITH_FINDINGS','CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE')
    assert receipt['containers_after']['rows'][0]['is_the_probe'] is False and receipt['container_removed'] is False
    def fail_listing(call):host.docker.ps_returncode=1
    docs,host=c3.case();host.docker.on_run=c3.answers('verified',before=fail_listing);receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','TLS_VERIFIED_WITH_FINDINGS','CONTAINER_LISTING_UNAVAILABLE_AFTER_RUN')
    assert receipt['containers_after']=={'status':'UNAVAILABLE','code':'COMMAND_FAILED','before':8,'after':None,'not_there_before':None,'name_present':None,'rows':[]}
    assert receipt['container_removed'] is None and receipt['tls_verified'] is True
    docs,host=c3.case();host.docker.on_run=c3.answers('refused',before=leave(None));receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','PROBE_RAN_TLS_NOT_VERIFIED','TCP_REFUSED') and receipt['container_removed'] is False
    docs,host=c3.case();host.docker.on_run=c3.answers('untrusted',returncode=125);receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','PROBE_RAN_TLS_NOT_VERIFIED','TLS_CERTIFICATE_NOT_VERIFIED')
    many=[];docs,host=c3.case()
    def crowd(call):
        for index in range(12):host.docker.containers.append(hostemu.container('crowd-%d'%index,hostemu.BACKEND,hostemu.BACKEND,[],running=True))
    host.docker.on_run=c3.answers('verified',before=crowd);receipt=run(docs,host)
    assert receipt['containers_after']['not_there_before']==12 and len(receipt['containers_after']['rows'])==8==K().m.MAX_NEW_CONTAINER_ROWS
    assert (receipt['containers_after']['before'],receipt['containers_after']['after'])==(8,20)

@pytest.mark.parametrize('returncode,output,code',[
    (125,b'','ENGINE_COULD_NOT_RUN_THE_CONTAINER'),(126,b'','ENGINE_COULD_NOT_RUN_THE_CONTAINER'),(127,b'x\n','ENGINE_COULD_NOT_RUN_THE_CONTAINER'),
    (142,b'','PROBE_ENDED_BY_ITS_ALARM'),(137,b'','PROBE_OUTPUT_NOT_ONE_LINE'),(0,b'','PROBE_OUTPUT_NOT_ONE_LINE'),(1,b'Traceback\n','PROBE_OUTPUT_NOT_ONE_LINE'),
    (0,c3.line_bytes(c3.model_line())*2,'PROBE_OUTPUT_NOT_ONE_LINE'),(0,c3.line_bytes(c3.model_line())[:-1],'PROBE_OUTPUT_NOT_ONE_LINE'),
    (0,b'[1]\n','PROBE_OUTPUT_NOT_ONE_LINE'),(0,b'{"a":1,"a":2}\n','PROBE_OUTPUT_NOT_ONE_LINE'),(0,b'{}\n','PROBE_LINE_NOT_AS_SPECIFIED'),
    (1,c3.line_bytes(c3.model_line()),'PROBE_EXIT_STATUS_NOT_ZERO'),(142,c3.line_bytes(c3.model_line()),'PROBE_EXIT_STATUS_NOT_ZERO'),
    (-9,c3.line_bytes(c3.model_line()),'PROBE_EXIT_STATUS_NOT_ZERO'),
])
def test_output_that_is_not_one_valid_line_leaves_the_result_unknown(returncode,output,code):
    docs,host=c3.case();host.docker.on_run=c3.answers(returncode=returncode,output=output);receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_PROBE_RESULT_UNKNOWN',code)
    probe=receipt['probe'];assert (probe['returncode'],probe['bytes'],probe['sha256'])==(returncode,len(output),f.sha(output) if output else None)
    if code!='PROBE_EXIT_STATUS_NOT_ZERO':
        assert probe['valid'] is False and probe['status'] is None and probe['dns'] is None and probe['tls'] is None and receipt['tls_verified'] is False
    assert receipt['container_removed'] is True

def mutated(path,value):
    line=c3.model_line();target=line
    for key in path[:-1]:target=target[key]
    if value is DELETE:del target[path[-1]]
    else:target[path[-1]]=value
    return line
DELETE=object()
INVALID=[(('schema',),'HOSTOPS02_TLS_PROBE_LINE_V2'),(('host',),'api.massive.com'),(('port',),444),(('port',),443.0),(('port',),True),
         (('application_bytes_sent',),1),(('application_bytes_sent',),False),(('status',),'OK'),(('status',),None),(('total_ms',),-1),(('total_ms',),60001),
         (('total_ms',),1.5),(('extra',),1),(('context',),None),(('context','check_hostname'),False),(('context','verify_mode_required'),1),
         (('context','other'),True),(('dns',),[]),(('dns','addresses'),17),(('dns','addresses'),2),(('dns','ipv4'),True),(('dns','code'),'DNS_SLOW'),
         (('dns','ms'),-5),(('dns','answered'),False),(('dns','code'),'DNS_TIMEOUT'),(('tcp','attempts'),2),(('tcp','attempts'),0),(('tcp','family'),'ipx'),
         (('tcp','family'),None),(('tcp','code'),'TCP_REFUSED'),(('tcp','connected'),False),(('tcp','ms'),'1'),(('tls','version'),'TLSv1.1'),
         (('tls','version'),None),(('tls','cipher'),'aes'),(('tls','cipher'),None),(('tls','cipher'),'A'*65),(('tls','leaf_sha256'),'0'*64),
         (('tls','leaf_sha256'),'G'*64),(('tls','leaf_sha256'),None),(('tls','verify_code'),20),(('tls','verify_code'),True),(('tls','code'),'TLS_PROTOCOL_ERROR'),
         (('tls','verified'),False),(('tls','handshake'),False),(('tls','ms'),60001),(('tls','other'),1),(('tcp','code'),None),(('dns','ipv6'),1)]
@pytest.mark.parametrize('path,value',INVALID)
def test_every_member_of_the_line_is_checked_before_anything_of_it_is_kept(path,value):
    line=mutated(path,value)
    if path==('tcp','code') and value is None:line=mutated(('tcp','attempts'),99)
    docs,host=c3.case();host.docker.on_run=c3.answers(output=c3.line_bytes(line));receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_PROBE_RESULT_UNKNOWN','PROBE_LINE_NOT_AS_SPECIFIED'),(path,value)
    assert receipt['probe']['one_json_line'] is True and receipt['probe']['valid'] is False and receipt['probe']['tls'] is None
    assert K().m.line_grammar(line) is False and K().m.line_grammar(c3.model_line()) is True
    for key in ('dns','tcp','tls','context'):assert receipt['probe'][key] is None

def edited(kind,*edits):
    line=c3.model_line(kind)
    for path,value in edits:
        target=line
        for key in path[:-1]:target=target[key]
        target[path[-1]]=value
    return line
MORE_INVALID=[('verified',(('dns','addresses'),17),(('dns','ipv4'),17)),('verified',(('dns','addresses'),17),(('dns','ipv4'),9),(('dns','ipv6'),8)),('untrusted',(('tls','verify_code'),1001)),('verified',(('dns','answered'),1)),
              ('nxdomain',(('dns','code'),'DNS_SLOW')),('refused',(('tcp','code'),'TCP_SLOW')),('verified',(('tcp','connected'),1)),
              ('untrusted',(('tls','verify_code'),True)),('failed',(('tls','code'),'TLS_SLOW')),('failed',(('dns','code'),'DNS_SLOW')),
              ('failed',(('tcp','code'),'TCP_SLOW')),('verified',(('tls','handshake'),1),(('tls','verified'),1)),
              ('dns_timeout',(('dns','addresses'),1),(('dns','ipv4'),1),(('tcp','attempts'),1)),
              ('refused',(('dns','addresses'),0),(('dns','ipv4'),0),(('tcp','attempts'),0)),('verified',(('dns','other'),1)),('verified',(('tcp','other'),1)),
              ('context',(('dns','addresses'),1),(('dns','ipv4'),1),(('tcp','attempts'),1))]
@pytest.mark.parametrize('kind,edits',[(row[0],row[1:]) for row in MORE_INVALID])
def test_lines_that_differ_in_more_than_one_member_are_refused_as_well(kind,edits):
    line=edited(kind,*edits);assert K().m.line_grammar(line) is False
    docs,host=c3.case();host.docker.on_run=c3.answers(output=c3.line_bytes(line));receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_PROBE_RESULT_UNKNOWN','PROBE_LINE_NOT_AS_SPECIFIED')

def test_both_versions_of_tls_the_default_context_allows_are_a_verified_probe():
    for version,cipher in (('TLSv1.2','ECDHE-ECDSA-AES128-GCM-SHA256'),('TLSv1.3','TLS_CHACHA20_POLY1305_SHA256')):
        line=edited('verified',(('tls','version'),version),(('tls','cipher'),cipher));assert K().m.line_grammar(line) is True
        docs,host=c3.case();host.docker.on_run=c3.answers(output=c3.line_bytes(line));receipt=run(docs,host)
        assert verdict(receipt)==('METADATA_ONLY_REQUIRES_REVIEW','TLS_VERIFIED_TO_THE_PROVIDER_HOST',None) and receipt['probe']['tls']['version']==version

def test_the_members_of_each_status_must_agree_with_it():
    m=K().m
    for kind in ('verified','nxdomain','dns_timeout','dns_failed','no_address','refused','tcp_timeout','unreachable','untrusted','other_name','hang',
                 'garbage','reset','context','optional','failed'):
        assert m.line_grammar(c3.model_line(kind)) is True,kind
    def changed(kind,*edits):
        line=c3.model_line(kind)
        for path,value in edits:
            target=line
            for key in path[:-1]:target=target[key]
            target[path[-1]]=value
        return line
    wrong=[changed('nxdomain',(('dns','code'),None)),changed('nxdomain',(('tcp','attempts'),1)),changed('nxdomain',(('tls','code'),'TLS_HANDSHAKE_TIMEOUT')),
           changed('nxdomain',(('dns','answered'),True)),changed('nxdomain',(('context','check_hostname'),False)),changed('nxdomain',(('tcp','code'),'TCP_REFUSED')),
           changed('refused',(('tcp','code'),None)),changed('refused',(('tcp','family'),'ipv4')),changed('refused',(('dns','answered'),False),(('dns','code'),'DNS_TIMEOUT')),
           changed('refused',(('tls','verify_code'),20)),changed('refused',(('tls','code'),'TLS_CONNECTION_ERROR')),
           changed('untrusted',(('tls','code'),'TLS_HANDSHAKE_TIMEOUT')),changed('untrusted',(('tcp','connected'),False)),changed('untrusted',(('tls','leaf_sha256'),c3.LEAF)),
           changed('untrusted',(('tls','version'),'TLSv1.3')),changed('untrusted',(('tls','cipher'),'X')),changed('untrusted',(('tls','handshake'),True)),
           changed('untrusted',(('tls','verified'),True)),changed('untrusted',(('context','verify_mode_required'),False)),
           changed('hang',(('tls','code'),'TLS_CERTIFICATE_NOT_VERIFIED')),changed('hang',(('tls','code'),None)),changed('hang',(('tls','verify_code'),62)),
           changed('hang',(('dns','code'),'DNS_TIMEOUT')),changed('context',(('context','check_hostname'),True)),changed('context',(('dns','answered'),True)),
           changed('context',(('dns','code'),'DNS_TIMEOUT')),changed('context',(('tls','code'),'TLS_PROTOCOL_ERROR')),changed('verified',(('dns','code'),'DNS_TIMEOUT')),
           changed('verified',(('dns','addresses'),0),(('dns','ipv4'),0)),changed('verified',(('tcp','family'),None)),changed('verified',(('context','check_hostname'),False)),
           changed('dns_timeout',(('tls','verify_code'),20)),changed('dns_timeout',(('tcp','family'),'ipv4')),changed('verified',(('tcp','attempts'),0)),
           changed('refused',(('context','check_hostname'),False)),changed('refused',(('tcp','connected'),True)),changed('hang',(('tcp','connected'),False)),
           changed('optional',(('dns','answered'),True)),changed('optional',(('context','verify_mode_required'),True))]
    for index,line in enumerate(wrong):assert m.line_grammar(line) is False,index

def test_new_containers_are_told_by_id_and_the_probes_name_by_name():
    docs,host=c3.case()
    def recreate(call):           # someone recreated a container of the project during the run: same name, new ID
        old=[item for item in host.docker.containers if item['Name']=='/c3po-api-1'][0];host.docker.containers.remove(old)
        host.docker.containers.append(hostemu.container('c3po-api-1',hostemu.BACKEND,'c3po/backend:production',[],running=True))
    host.docker.on_run=c3.answers('verified',before=recreate);receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','TLS_VERIFIED_WITH_FINDINGS','CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE')
    assert receipt['containers_after']['not_there_before']==1 and receipt['containers_after']['name_present'] is False
    docs,host=c3.case()
    def rename(call):             # a container that was listed before now carries the probe's name: not a removal
        [item for item in host.docker.containers if item['Name']=='/c3po-web-1'][0]['Name']='/'+call.name
    host.docker.on_run=c3.answers('verified',before=rename);receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','TLS_VERIFIED_WITH_FINDINGS','CONTAINER_OF_THE_PROBE_STILL_LISTED')
    assert (receipt['containers_after']['not_there_before'],receipt['containers_after']['name_present'],receipt['container_removed'])==(0,True,False)

def test_a_run_that_did_not_return_lists_the_containers_and_says_what_is_left():
    docs,host=c3.case();host.hang={('run','--rm')};receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_PROBE_RESULT_UNKNOWN','COMMAND_TIMEOUT')
    assert receipt['container']['state']=='DID_NOT_RETURN' and receipt['probe'] is None and receipt['containers_after']['name_present'] is False
    docs,host=c3.case();host.hang_after={('run','--rm')}
    def stays(call):host.docker.containers.append(hostemu.container(call.name,hostemu.BACKEND,hostemu.BACKEND,[],running=True))
    host.docker.on_run=c3.answers('verified',before=stays);receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_PROBE_RESULT_UNKNOWN','COMMAND_TIMEOUT')
    assert receipt['containers_after']['name_present'] is True and receipt['container_removed'] is False and receipt['tls_verified'] is False
    assert docker_words(host)[-1]==('ps',)
    docs,host=c3.case();host.hang_after={('run','--rm')};host.docker.on_run=c3.answers('verified',before=lambda call:host.hang.add(('ps','-a')))
    receipt=run(docs,host);assert receipt['code']=='COMMAND_TIMEOUT' and receipt['containers_after']['status']=='UNAVAILABLE'
    assert receipt['containers_after']['code']=='COMMAND_TIMEOUT' and receipt['container_removed'] is None

def test_an_expiry_during_the_container_leaves_the_listing_after_it_unavailable():
    """The emulated engine returns whatever the time (the real runner checks the gate after the wait and reports a run
    that did not return: core tests/test_runner.py); the listing after it is then not started."""
    docs,host=c3.case();budget=f.Budget(c3.NOW).attach(host).cost(500,'run','--rm');receipt=run(docs,host,**budget.options())
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','TLS_VERIFIED_WITH_FINDINGS','CONTAINER_LISTING_UNAVAILABLE_AFTER_RUN')
    assert receipt['containers_after']['code']=='GO_EXPIRED' and receipt['container_removed'] is None and docker_words(host)[-1]==('run',)

def test_an_escape_after_the_container_was_issued_is_never_a_refusal():
    docs,host=c3.case()
    def die(call):raise hostemu.Death('engine gone')
    host.docker.on_run=die;receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_STATE_UNKNOWN_CONTAINER_MAY_REMAIN','RUN_ESCAPED_STATE_UNKNOWN')
    assert receipt['phase_reached']=='ESCAPED' and 'engine gone' not in json.dumps(receipt)

def test_the_receipt_never_carries_text_of_the_line():
    line=c3.model_line('verified');line['tls']['cipher']='TLS_AES_128_GCM_SHA256';raw=c3.line_bytes(line)
    docs,host=c3.case();host.docker.on_run=c3.answers(output=raw);receipt=run(docs,host);assert receipt['probe']['tls']['cipher']=='TLS_AES_128_GCM_SHA256'
    canary=c3.model_line('verified');canary['tls']['cipher']='never-emit-canary'
    docs,host=c3.case();host.docker.on_run=c3.answers(output=c3.line_bytes(canary));receipt=run(docs,host)
    assert b'never-emit' not in f.line(receipt) and receipt['code']=='PROBE_LINE_NOT_AS_SPECIFIED'
    docs,host=c3.case();host.docker.on_run=c3.answers(output=b'secret never-emit-canary at 192.0.2.7\n');receipt=run(docs,host)
    assert b'never-emit' not in f.line(receipt) and b'192.0.2.7' not in f.line(receipt)
