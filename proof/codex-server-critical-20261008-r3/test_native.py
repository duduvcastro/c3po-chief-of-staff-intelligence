"""New F6 tests of native argv, disk journal, channel and integrated families.

No production Docker, SQL, provider or host is contacted. Fixture authority is
explicitly marked; no prior closed component test suite is executed here.
"""
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from common import Hold,PinnedDirectory,canonical,digest,instant,strict
from runtime import identity
from journal import IndependentWitness,Journal,bootstrap_fixture
from control import Controller,public_projection
from processes import BoundedProcess,DockerEngine
from channel import GitHub429,PREFIX
from families import ManifestStore

def h(v):return digest(v.encode())
CTX={'model':'SERVER_EPOCH_V2','epoch':'TEST_F6_NATIVE_20261012','session':'2026-10-12','lane':'CAPACITY','release_sha256':h('release')}


class Guard:
    mode='FIXTURE';pin=h('unit acceptance');context=CTX
    def __init__(self):
        self.fail=False;self.calls=0
        self.value={'measurement_sha256':h('physical fixture'),'source_pins':{'families.py':h('family fixture')},
          'registry_sha256':h('registry'),'allowed_operations':['F3_CAPACITY_VERIFY'],
          'spec':{'executables':{'python':{'path':sys.executable},'docker':{'path':'/fixture/docker'}},'socket':'/fixture/docker.sock'},
          'measurement':{'euid':os.geteuid()}}
    def recheck(self):
        self.calls+=1
        if self.fail:raise Hold('HOLD_RUNTIME')
        return self.pin
    def allow(self,operation):
        if operation not in self.value['allowed_operations']:raise Hold('HOLD_ADAPTER_UNAVAILABLE')
        return self.recheck()


class Adapter:
    operation='F3_CAPACITY_VERIFY';mode='FIXTURE';producer_sha256=h('adapter')
    def __init__(self,guard,output):self.guard=guard;self.results=output;self.source_pins=guard.value['source_pins'];self.calls=0;self.crash=False
    def validate(self,*args):pass
    def run_once(self,*args):
        self.calls+=1
        if self.crash:raise RuntimeError('private error should never be public')
        return {'fixture_native_test':True}


class Channel:
    def __init__(self,originals):self.values=originals;self.posts=0;self.uncertain=False
    def originals(self,refs):return copy.deepcopy(self.values)
    def post_once(self,body):
        self.posts+=1
        if self.uncertain:raise Hold('CHANNEL_UNCERTAIN')
    def recover_post(self,body,uid):return {'id':123,'body_sha256':digest(body),'executor_repeated':False}


def envelope(guard):
    req={'schema':'SERVER_FAMILY_REQUEST_V2','context':CTX,'operation':'F3_CAPACITY_VERIFY','authority_slot':'OWN_SLOT_1',
      'pins':{'runtime_measurement_sha256':guard.value['measurement_sha256']},'start_UTC':'2026-10-11T23:10:00Z',
      'end_UTC':'2026-10-11T23:12:01Z','budget_seconds':60,'required_gates':[],'gate_selectors':{},'payload':{}}
    auth={'schema':'SERVER_OPERATION_AUTHORITY_V2','context':CTX,'slot':'OWN_SLOT_1','request_sha256':digest(canonical(req)),
      'runtime_measurement_sha256':guard.value['measurement_sha256'],'registry_sha256':guard.value['registry_sha256'],'operation':req['operation']}
    review={'schema':'SERVER_OPERATION_REVIEW_V2','context':CTX,'request_sha256':digest(canonical(req)),'verdict':'ACCEPTED_OWN_BYTES',
      'authority_sha256':digest(canonical(auth)),'source_pins':guard.value['source_pins']}
    question={'schema':'SERVER_OWNER_QUESTION_V2','request_sha256':digest(canonical(req)),'published_UTC':'2026-10-11T23:00:00Z'}
    owner={'schema':'SERVER_OWNER_RESPONSE_V2','request_sha256':digest(canonical(req)),'question_sha256':digest(canonical(question)),
      'literal':'Assino','channel':'REGISTRO_PELA_FABLE','signed_at_UTC':'2026-10-11T23:01:00Z'}
    bound={'schema':'SERVER_BOUND_V2','context':CTX,'request_sha256':digest(canonical(req)),'question_sha256':digest(canonical(question)),
      'owner_sha256':digest(canonical(owner)),'review_sha256':digest(canonical(review)),
      'runtime_measurement_sha256':guard.value['measurement_sha256'],'gate_selectors_sha256':digest(canonical({}))}
    values=dict(request=req,authority=auth,review=review,question=question,owner=owner,bound=bound)
    refs={role:{'id':i+1,'author_id':313137248,'author_type':'User','body_sha256':digest(canonical(v))} for i,(role,v) in enumerate(values.items())}
    originals={role:{'value':v,'raw':canonical(v),'created_UTC':'2026-10-11T23:00:00Z','id':refs[role]['id']} for role,v in values.items()}
    originals['owner']['created_UTC']='2026-10-11T23:01:00Z'
    originals['bound']['created_UTC']='2026-10-11T23:02:00Z'
    election={'mode':'FIXTURE','context':CTX,'slots':{'OWN_SLOT_1':{'operation':req['operation'],
      'authority_sha256':digest(canonical(auth)),'review_sha256':digest(canonical(review)),'pins':req['pins'],
      'owner_deadline_UTC':'2026-10-12T00:45:00Z','max_lateness_seconds':5,'references':refs}}}
    guard.value['election']=election
    view={'schema':'SERVER_AUTHORITY_VIEW_V2','context':CTX,'veto':False,'revoked_shas':[],'concurrent_attempts':[],
      'deploy_in_progress':False,'release_sha256':CTX['release_sha256'],'observed_UTC':'2026-10-11T23:10:00Z',
      'valid_until_UTC':'2026-10-11T23:10:10Z'}
    return originals,{'references':copy.deepcopy(refs)},election,view


class TestNative(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='f6-native-FIXTURE-',dir=str(Path(tempfile.gettempdir()).resolve()))
        os.chmod(self.tmp.name,0o700);self.base=Path(self.tmp.name)
        for name in ('journal','witness','results','publish','manifests','capacity'):(self.base/name).mkdir(mode=0o700)
        self.guard=Guard();self.originals,self.bundle,self.election,self.view=envelope(self.guard)
        pins=bootstrap_fixture(self.base/'journal',self.base/'witness',self.election)
        self.roots={name:PinnedDirectory(self.base/name) for name in ('journal','witness','results','publish','manifests','capacity')}
        witness=IndependentWitness(self.roots['witness'],pins['witness']['events.jsonl'],pins['witness']['lock'],
          election=self.election,ledger_root=pins['root'],independence={},mode='FIXTURE')
        self.journal=Journal(self.roots['journal'],pins['ledger']['events.jsonl'],pins['ledger']['lock'],election=self.election,witness=witness)
        self.channel=Channel(self.originals);self.adapter=Adapter(self.guard,self.roots['results'])
        self.clock=lambda:'2026-10-11T23:10:00Z';self.tick=lambda:100.0
        self.controller=Controller(self.guard,self.journal,{self.adapter.operation:self.adapter},self.channel,clock=lambda:self.clock(),monotonic=lambda:self.tick())
    def tearDown(self):
        for d in self.roots.values():d.close()
        self.tmp.cleanup()
    def invoke(self):return self.controller.invoke('OWN_SLOT_1',self.bundle,view_reader=lambda:copy.deepcopy(self.view),gate_reader=lambda r:{})
    def test_t01_durable_complete_receipt_one_effect_second_invocation_consumed(self):
        result=self.invoke();self.assertEqual(result['verdict'],'COMPLETE_FIXTURE');self.assertEqual(self.adapter.calls,1)
        raw=self.roots['results'].read(result['attempt_key']+'.receipt.json');self.assertEqual(digest(raw),result['receipt_sha256'])
        self.assertEqual(strict(raw)['mode'],'FIXTURE');self.assertEqual(self.invoke()['verdict'],'HOLD_CONSUMED');self.assertEqual(self.adapter.calls,1)
    def test_t04_refused_owner_consumes_even_without_adapter_effect(self):
        self.channel.values['owner']['value']['literal']='Não'
        result=self.invoke();self.assertEqual(result['verdict'],'HOLD_OWNER');self.assertEqual(self.adapter.calls,0)
        self.assertEqual(self.invoke()['verdict'],'HOLD_CONSUMED')
    def test_t04_retroactive_and_offline_signature_refused(self):
        self.channel.values['owner']['value']['signed_at_UTC']='2026-10-12T01:00:00Z'
        self.assertEqual(self.invoke()['verdict'],'HOLD_OWNER');self.assertEqual(self.adapter.calls,0)
    def test_t05_runtime_failure_before_effect_consumes(self):
        self.guard.fail=True;self.assertEqual(self.invoke()['verdict'],'HOLD_RUNTIME');self.guard.fail=False
        self.assertEqual(self.invoke()['verdict'],'HOLD_CONSUMED');self.assertEqual(self.adapter.calls,0)
    def test_t05_changed_authority_reference_not_accepted_as_same_bytes(self):
        self.bundle['references']['owner']['author_id']=1
        self.assertEqual(self.invoke()['verdict'],'HOLD_AUTHORITY');self.assertEqual(self.adapter.calls,0)
    def test_t06_adapter_crash_uncertain_never_repeated(self):
        self.adapter.crash=True;result=self.invoke();self.assertEqual(result['verdict'],'HOLD_UNCERTAIN');self.assertTrue(result['effect_started'])
        self.adapter.crash=False;self.assertEqual(self.invoke()['verdict'],'HOLD_CONSUMED');self.assertEqual(self.adapter.calls,1)
    def test_t06_named_journal_replacement_refused(self):
        path=self.base/'journal'/'events.jsonl';raw=path.read_bytes();path.rename(path.with_suffix('.old'));path.write_bytes(raw);os.chmod(path,0o600)
        with self.assertRaisesRegex(Hold,'JOURNAL_FILE_IDENTITY'):self.invoke()
        self.assertEqual(self.adapter.calls,0)
    def test_t07_clock_jump_and_missed_slot_do_not_catch_up(self):
        self.clock=lambda:'2026-10-11T23:10:06Z';self.assertEqual(self.invoke()['verdict'],'HOLD_WINDOW');self.assertEqual(self.adapter.calls,0)
    def test_t08_state_root_replaced_or_symlink_refused(self):
        path=self.base/'journal';path.rename(self.base/'journal-old');path.mkdir(mode=0o700)
        with self.assertRaisesRegex(Hold,'ROOT_REPLACED'):self.invoke()
        self.assertEqual(self.adapter.calls,0)
    def test_t09_revocation_concurrency_deploy_block_before_effect(self):
        self.view['deploy_in_progress']=True;self.assertEqual(self.invoke()['verdict'],'HOLD_AUTHORITY');self.assertEqual(self.adapter.calls,0)
    def test_t12_native_docker_has_only_pinned_fixed_verbs(self):
        calls=[]
        class Runner:
            def run(_,argv,**opts):calls.append(argv);return {'returncode':0,'stdout':b''}
        docker=DockerEngine(self.guard,Runner());from k12 import INSPECT_FORMAT
        docker.call('inspect','a'*64,INSPECT_FORMAT);docker.call('logs','a'*64);docker.call('stop','a'*64)
        self.assertEqual(calls[-1][-4:],['stop','--time','10','a'*64]);self.assertTrue(all(a[:3]==['/fixture/docker','--host','unix:///fixture/docker.sock'] for a in calls))
        for bad in ('exec','run','restart','rm','sql'):
            with self.assertRaises(Hold):docker.call(bad,'a'*64)
        self.assertEqual(len(calls),3)
    def test_t12_native_process_does_not_forward_secret_environment(self):
        program=self.base/'fixture_child.py';program.write_text('import json,os;print(json.dumps({"secret":os.environ.get("TEST_NATIVE_SECRET"),"pythonpath":os.environ.get("PYTHONPATH")}))')
        os.environ['TEST_NATIVE_SECRET']='DO_NOT_FORWARD';os.environ['PYTHONPATH']='DO_NOT_FORWARD'
        try:
            result=BoundedProcess(self.guard).run([sys.executable,'-I','-S','-B',str(program)],seconds=5,limit=1024)
            self.assertEqual(strict(result['stdout']),{'secret':None,'pythonpath':None})
        finally:os.environ.pop('TEST_NATIVE_SECRET',None);os.environ.pop('PYTHONPATH',None)
    def test_t12_native_process_output_budget_and_timeout_refuse(self):
        program=self.base/'fixture_child.py';program.write_text('import sys;sys.stdout.write("x"*5000)')
        with self.assertRaisesRegex(Hold,'PROCESS_OUTPUT_LIMIT'):BoundedProcess(self.guard).run([sys.executable,'-I','-S',str(program)],limit=100,seconds=2)
        program.write_text('import time;time.sleep(2)')
        with self.assertRaisesRegex(Hold,'PROCESS_TIMEOUT'):BoundedProcess(self.guard).run([sys.executable,'-I','-S',str(program)],limit=100,seconds=.1)
    def test_t15_uncertain_post_recovers_by_reads_without_second_post(self):
        result=self.invoke();prepared=public_projection(result);self.channel.uncertain=True
        self.assertEqual(self.controller.publish(result['attempt_key'],prepared,self.roots['publish'],313137248)['verdict'],'HOLD_PUBLICATION_UNCERTAIN')
        self.channel.uncertain=False;closed=self.controller.publish(result['attempt_key'],prepared,self.roots['publish'],313137248)
        self.assertFalse(closed['executor_repeated']);self.assertEqual(self.channel.posts,1);self.assertEqual(self.adapter.calls,1)
    def test_t03_public_projection_never_contains_paths_tokens_or_exception(self):
        self.adapter.crash=True;raw=public_projection(self.invoke())
        for value in (b'private error',self.tmp.name.encode(),b'Bearer',b'configuration'):self.assertNotIn(value,raw)
    def test_t17_ledger_rollback_detected_by_durable_witness(self):
        path=self.base/'journal'/'events.jsonl';old=path.read_bytes();self.invoke();path.write_bytes(old)
        with self.assertRaisesRegex(Hold,'JOURNAL_WITNESS_MISMATCH'):self.invoke()
        self.assertEqual(self.adapter.calls,1)
    def test_t17_torn_append_and_no_production_bootstrap(self):
        path=self.base/'journal'/'events.jsonl'
        with path.open('ab') as f:f.write(b'{"sequence":')
        with self.assertRaisesRegex(Hold,'JOURNAL_TORN'):self.invoke()
        with self.assertRaisesRegex(Hold,'JOURNAL_NO_AUTOMATIC_PRODUCTION_BOOTSTRAP'):bootstrap_fixture('x','y',{'mode':'REAL'})
    def test_t02_duplicate_json_canonical_original_and_full_pagination(self):
        with self.assertRaises(Hold):strict(b'{"a":1,"a":2}')
        rows=[{'id':i} for i in range(100)];pages=[rows,[{'id':100}]]
        channel=object.__new__(GitHub429);channel._http=lambda path:pages.pop(0)
        self.assertEqual(len(channel.collection()),101)
        pages=[rows,[{'id':0}]]
        with self.assertRaisesRegex(Hold,'CHANNEL_DUPLICATE_ID'):channel.collection()
    def test_t02_wrong_author_edited_or_truncated_original_rejected(self):
        raw=canonical({'schema':'FIXTURE_ORIGINAL','marker':'NOT_AUTHORITY'})
        row={'id':1,'body':raw.decode(),'user':{'id':313137248,'type':'User'},'created_at':'2026-10-11T23:00:00Z',
             'updated_at':'2026-10-11T23:00:00Z','issue_url':PREFIX+'issues/429'}
        channel=object.__new__(GitHub429);channel._http=lambda path:copy.deepcopy(row)
        ref={'id':1,'author_id':313137248,'author_type':'User','body_sha256':digest(raw)}
        self.assertEqual(channel.original(ref,[row])['raw'],raw)
        row['updated_at']='2026-10-11T23:01:00Z'
        with self.assertRaisesRegex(Hold,'CHANNEL_ORIGINAL_EDITED_OR_AUTHOR'):channel.original(ref,[row])
    def test_t04_owner_register_time_cannot_backdate_or_follow_bound(self):
        self.channel.values['owner']['created_UTC']='2026-10-11T23:03:00Z'
        self.assertEqual(self.invoke()['verdict'],'HOLD_OWNER');self.assertEqual(self.adapter.calls,0)
    def test_t03_private_prepared_text_is_rejected_before_publication(self):
        result=self.invoke()
        with self.assertRaisesRegex(Hold,'HOLD_RESULT'):self.controller.publish(result['attempt_key'],b'private token or path',self.roots['publish'],313137248)
        self.assertEqual(self.channel.posts,0)
    def test_t06_two_isolated_processes_contend_one_effect(self):
        # Fork exists on both test platforms (Mac/Linux). Each child opens its
        # own flock descriptor, while effects stay in this temporary fixture.
        effect=self.base/'one-effect.fixture';statuses=[];children=[]
        def once(*args):
            fd=os.open(effect,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            try:os.write(fd,b'one FIXTURE effect\n');os.fsync(fd)
            finally:os.close(fd)
            return {'fixture':True}
        self.adapter.run_once=once
        for i in range(2):
            read,write=os.pipe();pid=os.fork()
            if pid==0:
                os.close(read)
                try:os.write(write,canonical(self.invoke()));code=0
                except Exception:code=2
                os.close(write);os._exit(code)
            os.close(write);children.append((pid,read))
        for pid,read in children:
            raw=os.read(read,4096);os.close(read);_,status=os.waitpid(pid,0)
            self.assertEqual(status,0);statuses.append(strict(raw)['verdict'])
        self.assertEqual(sorted(statuses),['COMPLETE_FIXTURE','HOLD_CONSUMED'])
        self.assertEqual(effect.read_bytes(),b'one FIXTURE effect\n')
    def test_t07_t13_new_controller_after_process_end_cannot_repeat(self):
        self.assertEqual(self.invoke()['verdict'],'COMPLETE_FIXTURE')
        other=Controller(self.guard,self.journal,{self.adapter.operation:self.adapter},self.channel,clock=self.clock,monotonic=self.tick)
        result=other.invoke('OWN_SLOT_1',self.bundle,view_reader=lambda:self.view,gate_reader=lambda r:{})
        self.assertEqual(result['verdict'],'HOLD_CONSUMED');self.assertEqual(self.adapter.calls,1)
    def test_t07_clock_jump_during_effect_is_uncertain_and_consumed(self):
        original=self.adapter.run_once
        def jump(*args):
            value=original(*args);self.clock=lambda:'2026-10-11T23:10:02Z';return value
        self.adapter.run_once=jump;self.assertEqual(self.invoke()['verdict'],'HOLD_CLOCK')
        self.assertEqual(self.invoke()['verdict'],'HOLD_CONSUMED');self.assertEqual(self.adapter.calls,1)
    def test_t16_old_date_has_no_new_authority_slot(self):
        self.channel.values['request']['value']['context']=dict(CTX,session='2026-10-09')
        self.assertEqual(self.invoke()['verdict'],'HOLD_UNCERTAIN');self.assertEqual(self.adapter.calls,0)

    def test_t07_admitted_effect_after_five_seconds_keeps_own_budget_and_current_gates(self):
        original=self.adapter.run_once
        def later(*args):
            result=original(*args);self.clock=lambda:'2026-10-11T23:10:06Z';self.tick=lambda:106.0
            return result
        self.adapter.run_once=later
        self.assertEqual(self.invoke()['verdict'],'COMPLETE_FIXTURE')
        self.assertEqual(self.invoke()['verdict'],'HOLD_CONSUMED');self.assertEqual(self.adapter.calls,1)

    def test_t07_t14_retention_over_budget_or_changed_runtime_has_no_complete_outcome(self):
        class LateRetention:
            def retain(other,*args,**kw):
                self.clock=lambda:'2026-10-11T23:11:01Z';self.tick=lambda:161.0
                return {'fixture_retention':True}
        self.controller.retainer=LateRetention()
        result=self.invoke();self.assertEqual(result['verdict'],'HOLD_CLOCK');self.assertIsNone(result['receipt_sha256'])
        self.assertEqual(self.invoke()['verdict'],'HOLD_CONSUMED');self.assertEqual(self.adapter.calls,1)


if __name__=='__main__':unittest.main()
