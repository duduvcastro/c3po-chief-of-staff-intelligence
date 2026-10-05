"""The pinned snippet itself, run by a real interpreter in isolated mode with exactly the standard input a run gives
its container: against the stand-in package (every answer the deployed code can give, on both interpreters), and
against the application modules of the release (where a checkout that holds dd4ec4bb is named by
HOSTOPS02_TEST_RELEASE_REPOSITORY and the calendar library is installed)."""
import ast
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import types

import pytest

import family as f
import hostemu
import k11

COMPLETE='METADATA_ONLY_REQUIRES_REVIEW';PARTIAL='PARTIAL_METADATA_REQUIRES_REVIEW'
def fresh(mode='PRE',**options):
    docs,host=k11.case(mode,**options);return docs.k.m,docs,host

def test_static_snippet_is_plain_python_that_prints_one_line_and_names_nothing_of_the_host():
    k=f.load(k11.DIRECTORY);m=k.m;text=m.VERIFY_SNIPPET;tree=ast.parse(text,feature_version=(3,7))
    assert text.isascii() and text.endswith('\n') and "'''" not in text and m.VERIFY_SNIPPET_SHA256==f.sha(text.encode('ascii'))
    assert [type(node).__name__ for node in tree.body[:2]]==['Import','Expr'] and ast.unparse(tree.body[1]) if hasattr(ast,'unparse') else True
    imported={alias.name for node in ast.walk(tree) if isinstance(node,ast.Import) for alias in node.names}|{node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)}
    assert imported=={'signal','base64','hashlib','json','os','re','sys','types','datetime','app.r2d2_v2_shadow','app.r2d2_v2_earnings_package','app','app.r2d2_v2_shadow_worker','app.r2d2_v2_store'}
    # every module of the application is imported at the head of the one try block, in every run: none under a condition
    attempt=[node for node in tree.body if isinstance(node,ast.Try)];assert len(attempt)==1
    application=[node for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) and node.module.startswith('app')]
    assert application==attempt[0].body[:len(application)] and len(application)==6
    assert sorted(alias.name for node in application for alias in node.names)==['EBAR_AMENDMENT_SHA','Release','ShadowCalendar','ShadowIntegrityError','_release_bytes','implementation_package_sha',
                                                                                'r2d2_v2_epoch_assembler','r2d2_v2_live_controller']
    names={node.id for node in ast.walk(tree) if isinstance(node,ast.Name)}|{node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
    assert not names&{'environ','getenv','socket','subprocess','system','popen','unlink','remove','mkdir','rename','chmod','chown','print','exec','eval'}
    assert [node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id=='os']==['write']
    assert text.count('os.write(1,')==1 and 'open(' not in text.replace('_release_bytes','')

def test_alarm_is_the_first_thing_the_snippet_does_and_it_ends_a_container_that_hangs():
    """The alarm is armed with the signed number of seconds before anything is imported; with the application stuck,
    the kernel ends the interpreter (here after one second: the test scales the alarm, the snippet's bytes are the
    real ones) and the run is a failed run with the status of the signal, never a container that stays."""
    m,docs,host=fresh('PRE');container=k11.Container(k11.fake_tree(hang=True),alarm_scale=1);host.docker.on_run=container;receipt=docs.run(host)
    assert container.stderr==[b'ALARM=%d\n'%m.VERIFY_ALARM_SECONDS] and receipt['items']['verify']['findings']==['VERIFY_RUN_FAILED']
    assert (receipt['items']['verify']['returncode'],receipt['items']['verify']['returned'])==(128+14,True) and receipt['status']==PARTIAL
    m,docs,host=fresh('PRE');container=k11.Container(alarm_scale=5);host.docker.on_run=container;receipt=docs.run(host)
    assert container.stderr==[b'ALARM=30\n'] and receipt['status']==COMPLETE,'a run that finishes is not disturbed by the alarm'

@pytest.mark.parametrize('mode',['PRE','POST'])
def test_snippet_prints_exactly_one_line_writes_nothing_else_and_exits_by_its_status(mode):
    m,docs,host=fresh(mode);container=k11.Container();host.docker.on_run=container;seen=[]
    def capture(call):
        code,out=container(call);seen.append((code,out));return code,out
    host.docker.on_run=capture;receipt=docs.run(host);code,out=seen[0]
    assert receipt['status']==COMPLETE and code==0 and out.count(b'\n')==1 and out.endswith(b'\n') and container.stderr==[b'']
    line=json.loads(out);assert out==f.canonical(line)+b'\n' and line['context_request_sha256']==docs.pins().request
    assert set(line)=={'status','release','policy','probe','package_equal_signed','facts','context_request_sha256'} and line['facts']['python']=='%d.%d.%d'%sys.version_info[:3]
    assert line['probe']==({'valid':True,'code':None} if mode=='PRE' else None)
    for knobs,status,code_expected in ((dict(import_error=True),{'status':'FAILED','code':'ImportError'},1),(dict(calendar_error=True),{'status':'FAILED','code':'RuntimeError'},1)):
        m,docs,host=fresh(mode);container=k11.Container(k11.fake_tree(**knobs));seen=[]
        host.docker.on_run=lambda call:seen.append(container(call)) or seen[-1]
        docs.run(host);assert seen[0]==(code_expected,f.canonical(status)+b'\n')

def test_the_frame_cannot_be_turned_into_code_by_a_signed_value():
    """Every value of the context is a literal written by repr(); the names of the plan cannot leave their grammar."""
    m,docs,host=fresh('POST');docs.plan['release']['file_name']="x';import os;os.system('id');'";docs.chain()
    assert f.refusal(docs.authenticate)=='RELEASE_PLAN_INVALID'
    m,docs,host=fresh('POST');frame=m.frame_of(docs.plan,docs.pins().request);head=frame.split(b'\n',1)[0]
    assert head.count(b'\n')==0 and type(ast.literal_eval(head[len(b'SIGNED_CONTEXT='):].decode())) is dict


# ---------------------------------------------------------------- the application modules of the release themselves
REPOSITORY=os.environ.get('HOSTOPS02_TEST_RELEASE_REPOSITORY','')
@pytest.fixture(scope='module')
def real(tmp_path_factory):
    """The package `app` of the release commit, extracted from the checkout, and documents its own code accepts."""
    try:import exchange_calendars
    except ImportError:pytest.skip('the calendar library of the application is not installed for this interpreter')
    if not REPOSITORY or not Path(REPOSITORY).is_dir():pytest.skip('HOSTOPS02_TEST_RELEASE_REPOSITORY does not name a checkout that holds the release')
    root=tmp_path_factory.mktemp('release')
    archive=subprocess.run(['git','-C',REPOSITORY,'archive',k11.REVISION,'c3po/backend/app'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
    assert archive.returncode==0,archive.stderr.decode()[-500:]
    subprocess.run(['tar','-x','-C',str(root)],input=archive.stdout,check=True,timeout=120);tree=str(root/'c3po'/'backend')
    def documents(release=None,policy=None):
        done=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('real_documents.py')),tree,k11.REVISION,json.dumps(release or {}),json.dumps(policy or {})],
                            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
        assert done.returncode==0,done.stderr.decode()[-2000:]
        value=json.loads(done.stdout);return base64.b64decode(value['release']),base64.b64decode(value['policy'])
    return tree,documents

def real_case(real,mode,release=None,policy=None,**options):
    tree,documents=real;release_raw,policy_raw=documents(release,policy)
    docs,host=k11.case(mode,release=release_raw,policy=policy_raw,**options);host.docker.on_run=k11.Container(tree);return docs.k.m,docs,host

@pytest.mark.parametrize('mode',['PRE','POST'])
def test_release_code_itself_verifies_the_release_and_accepts_the_policy_through_the_snippet(real,mode):
    m,docs,host=real_case(real,mode,render=True);receipt=docs.run(host)
    assert receipt['status']==COMPLETE and receipt['outcome']==m.success_of(docs.plan),(receipt['findings'],receipt['items']['verify'])
    verify=receipt['items']['verify'];assert verify['package_equal_signed'] is True,'the package hash the release code computes from its own files is the signed one'
    assert verify['release']=={'source':'STDIN' if mode=='PRE' else 'FILE','read':True,'bytes_equal_signed':True,'verified':True,'code':None,'mode_certified':True,
                               'epoch_equal':True,'first_session_equal':True,'ebar_bound':True}
    assert verify['policy']=={'hash_equal_signed':True,'controller_now':{'valid':True,'code':None},'controller_at':[{'valid':True,'code':None}]*3,'assembler':{'valid':True,'code':None}}
    assert host.docker.on_run.stderr==[b''],'the application imports and runs without a word on standard error'

def test_release_code_itself_refuses_what_it_must_and_the_receipt_carries_its_code(real):
    for change,code in ((dict(package_consents=[]),'PACKAGE_CONSENTS_REQUIRED'),(dict(approved_at='2026-10-05T13:30:00+00:00'),'RELEASE_MUST_PRECEDE_FIRST_SESSION'),
                        (dict(readiness_at='2026-10-01T12:00:00+00:00',deploy_completed_at='2026-10-01T11:00:00+00:00'),'READINESS_FIRST_SESSION_MISMATCH'),
                        (dict(calibration_status='PENDING'),'CALIBRATION_AND_SOURCES_REQUIRED'),(dict(manifest_sha='a'*64),'RELEASE_POLICY_MISMATCH')):
        m,docs,host=real_case(real,'PRE',release=change);receipt=docs.run(host)
        assert 'RELEASE_NOT_VERIFIED' in receipt['findings'] and receipt['items']['verify']['release']['code']==code,(code,receipt['items']['verify'])
    m,docs,host=real_case(real,'POST',release=dict(ebar_amendment_sha='a'*64));receipt=docs.run(host)
    assert receipt['items']['verify']['release']['code']=='RELEASE_EBAR_POLICY_MISMATCH'
    for change,finding,member,code in ((dict(capacity=551),'POLICY_REFUSED_BY_THE_CONTROLLER','controller_at','LIVE_POLICY_INVALID'),
                                       (dict(head_go_sha='x'),'POLICY_REFUSED_BY_THE_CONTROLLER','controller_at','LIVE_POLICY_INVALID'),
                                       (dict(valid_until='2026-10-09T19:59:59.500000+00:00'),'POLICY_REFUSED_BY_THE_ASSEMBLER','assembler','POLICY_NOT_EPOCH_WIDE'),
                                       (dict(valid_from='2026-10-05T08:00:00+00:00',valid_until='2027-02-01T00:00:00+00:00'),'POLICY_REFUSED_BY_THE_CONTROLLER','controller_at','LIVE_POLICY_MODE_INVALID')):
        m,docs,host=real_case(real,'POST',policy=change);receipt=docs.run(host);policy=receipt['items']['verify']['policy'];found=policy[member]
        assert finding in receipt['findings'] and (found[0] if type(found) is list else found)=={'valid':False,'code':code},(change,policy)
        assert receipt['items']['verify']['release']['verified'] is True
    # the worker's own reader refuses an installed file that group or other can read
    m,docs,host=real_case(real,'POST');host.tree.get(k11.RELEASE_HOST+'/'+k11.RELEASE_FILE).mode=0o640;receipt=docs.run(host)
    assert receipt['items']['verify']['release']['code']=='RELEASE_FILE_NOT_PRIVATE_OR_INVALID' and 'RELEASE_NOT_READ_IN_THE_CONTAINER' in receipt['findings']

def test_stand_in_reader_is_the_reader_of_the_release_line_for_line(real):
    """The stand-in package copies the worker's reader; the copy is compared with the release's function text."""
    tree,_=real;source=(Path(tree)/'app'/'r2d2_v2_shadow_worker.py').read_text()
    def body(text):
        node=[node for node in ast.parse(text).body if isinstance(node,ast.FunctionDef) and node.name=='_release_bytes'][0]
        node.body=[item for item in node.body if not (isinstance(item,ast.Expr) and isinstance(getattr(item,'value',None),ast.Constant))];node.returns=None
        for argument in node.args.args:argument.annotation=None
        return ast.dump(node)
    assert body(source)==body(k11.FAKE['r2d2_v2_shadow_worker.py'])


# ---------------------------------------------------------------- the snippet given a context of its own (not through the source)
def direct(context,tree=None,files=None):
    """The snippet run on a context written by the test: what it compares with what, value by value. files maps a
    container directory to {name: (bytes, mode)}; it is given to the interpreter as a read-only bind would be."""
    k=f.load(k11.DIRECTORY);frame=b'SIGNED_CONTEXT='+repr(context).encode('ascii')+b'\n'+k.m.VERIFY_SNIPPET.encode('ascii');nodes={}
    for target,entries in (files or {}).items():
        for name,(content,mode) in entries.items():nodes[target+'/'+name]=types.SimpleNamespace(kind='file',mode=mode,content=content,target='')
    call=types.SimpleNamespace(command=['python','-I','-B','-'],network='none',read_only_root=True,stdin=frame,
                               mounts=[{'source':'/unused','target':target,'read_only':True} for target in (files or {})],
                               listdir=lambda target:sorted(name.rsplit('/',1)[1] for name in nodes if name.startswith(target+'/')),node=lambda path:nodes[path])
    code,out=k11.Container(tree)(call);return code,json.loads(out)
def context(**changes):
    value={'request_sha256':'9'*64,'revision':k11.REVISION,'package_sha256':k11.PACKAGE,'epoch':k11.EPOCH,'first_session':k11.FIRST,
           'release_sha256':f.sha(k11.RELEASE),'release_bytes':len(k11.RELEASE),'release_b64':k11.b64(k11.RELEASE),'release_path':None,
           'policy_b64':k11.b64(k11.POLICY),'policy_sha256':f.sha(k11.POLICY),'policy_valid_at':k11.VALID_AT,'probe_path':None}
    value.update(changes);return value
def with_release(raw,**changes):return context(release_sha256=f.sha(raw),release_bytes=len(raw),release_b64=k11.b64(raw),**changes)

def test_snippet_compares_every_signed_value_with_what_the_deployed_code_and_the_bytes_say():
    code,line=direct(context());assert code==0 and line['release']['verified'] and line['policy']['controller_at']==[{'valid':True,'code':None}]*3 and line['policy']['assembler']['valid']
    assert line['context_request_sha256']=='9'*64 and line['package_equal_signed'] is True and line['probe'] is None
    # the release: the signed revision is what the worker will give as its build, not what the release says of itself
    code,line=direct(context(revision='0'*40));assert (line['release']['verified'],line['release']['code'])==(False,'RELEASE_CODE_OR_AUTHORIZATION_UNVERIFIED')
    code,line=direct(context(release_sha256='a'*64));assert (line['release']['bytes_equal_signed'],line['release']['code'])==(False,'RELEASE_HASH_MISMATCH')
    code,line=direct(context(release_bytes=len(k11.RELEASE)+1));assert line['release']['bytes_equal_signed'] is False and line['release']['verified'] is True
    code,line=direct(context(epoch='R2D2-V2-SHADOW-2026-09-28'));assert line['release']['epoch_equal'] is False and line['release']['first_session_equal'] is True
    code,line=direct(context(first_session='2026-10-06'));assert line['release']['first_session_equal'] is False and line['release']['epoch_equal'] is True
    other=k11.release_bytes(epoch='R2D2-V2-SHADOW-2026-09-28')
    code,line=direct(with_release(other,epoch='R2D2-V2-SHADOW-2026-09-28'));assert line['release']['epoch_equal'] is False,'equal to the signed epoch and not to the compiled one'
    code,line=direct(with_release(other),k11.fake_tree(assembler_epoch='R2D2-V2-SHADOW-2026-09-28'));assert line['release']['epoch_equal'] is False,'equal to the compiled epoch and not to the signed one'
    code,line=direct(with_release(k11.release_bytes(first_session='2026-10-06')));assert line['release']['first_session_equal'] is False
    code,line=direct(with_release(k11.release_bytes(mode='DIAGNOSTIC')));assert line['release']['mode_certified'] is False and line['release']['verified'] is True
    code,line=direct(with_release(k11.release_bytes(ebar_amendment_sha='a'*64)));assert line['release']['ebar_bound'] is False
    code,line=direct(context(package_sha256='a'*64));assert line['package_equal_signed'] is False and line['release']['verified'] is True
    # the policy: the signed hash is the pin, the signed revision the build, the signed release the binding
    code,line=direct(context(policy_sha256='a'*64));policy=line['policy']
    assert policy['hash_equal_signed'] is False and policy['controller_at']==[{'valid':False,'code':'LIVE_POLICY_HASH_MISMATCH'}]*3 and policy['assembler']=={'valid':False,'code':'POLICY_HASH'}
    code,line=direct(context(revision='0'*40));assert line['policy']['controller_at'][0]=={'valid':False,'code':'LIVE_POLICY_INVALID'}
    code,line=direct(context(release_sha256='a'*64));assert line['policy']['assembler']=={'valid':False,'code':'POLICY_IDENTITY'}
    code,line=direct(context(policy_valid_at=['2026-10-01T00:00:00+00:00','2026-10-05T13:30:00+00:00']))
    assert line['policy']['controller_at']==[{'valid':False,'code':'LIVE_POLICY_OUTSIDE_WINDOW'},{'valid':True,'code':None}]
    code,line=direct(context(policy_b64=None,policy_sha256=None,policy_valid_at=[]));assert line['policy'] is None
    code,line=direct(context(release_b64='not base64 !'));assert (line['release']['read'],line['release']['code'])==(False,'Error')

def test_snippet_reads_the_installed_file_and_the_probe_with_the_reader_of_the_worker():
    good={'/c3po-epoch-release':{k11.RELEASE_FILE:(k11.RELEASE,0o600)}}
    code,line=direct(context(release_b64=None,release_path='/c3po-epoch-release/'+k11.RELEASE_FILE),files=good)
    assert line['release']=={'source':'FILE','read':True,'bytes_equal_signed':True,'verified':True,'code':None,'mode_certified':True,'epoch_equal':True,'first_session_equal':True,'ebar_bound':True}
    for mode in (0o640,0o604,0o644):
        code,line=direct(context(release_b64=None,release_path='/c3po-epoch-release/'+k11.RELEASE_FILE),files={'/c3po-epoch-release':{k11.RELEASE_FILE:(k11.RELEASE,mode)}})
        assert (line['release']['read'],line['release']['code'])==(False,'RELEASE_FILE_NOT_PRIVATE_OR_INVALID'),'the reader of the worker, not a plain open'
    code,line=direct(context(release_b64=None,release_path='/c3po-epoch-release/absent.json'),files=good);assert (line['release']['read'],line['release']['code'])==(False,'FileNotFoundError')
    probe={'/c3po-bind-probe':{'epoch.json':(b'{}',0o600),'open.json':(b'{}',0o644)}}
    code,line=direct(context(probe_path='/c3po-bind-probe/epoch.json'),files=probe);assert line['probe']=={'valid':True,'code':None}
    code,line=direct(context(probe_path='/c3po-bind-probe/open.json'),files=probe);assert line['probe']=={'valid':False,'code':'RELEASE_FILE_NOT_PRIVATE_OR_INVALID'}
    code,line=direct(context(probe_path='/c3po-bind-probe/absent'),files=probe);assert line['probe']=={'valid':False,'code':'FileNotFoundError'}


# ---------------------------------------------------------------- the review of 02/10
@pytest.mark.parametrize('mode,options',[('PRE',dict(policy=None,probe=None)),('PRE',{}),('POST',{})])
def test_reader_of_the_worker_and_the_controller_are_imported_in_every_run_signed_policy_or_not(mode,options):
    """What Monday's readback imports is imported by every dry run, the reduced one included: a module that cannot
    be imported in a fresh read-only container is found on Sunday whatever the request signs."""
    for knobs in (dict(controller_import_error=True),dict(reader_import_error=True)):
        m,docs,host=fresh(mode,**options);container=k11.Container(k11.fake_tree(**knobs));host.docker.on_run=container;receipt=docs.run(host)
        assert receipt['items']['verify']['findings']==['VERIFY_SNIPPET_FAILED'] and receipt['items']['verify']['snippet_code']=='ImportError' and receipt['status']==PARTIAL
        assert 'cannot be imported' not in json.dumps(receipt)

def test_a_code_is_the_argument_of_the_release_s_own_refusals_and_otherwise_the_name_of_the_class():
    """Only an exception of the release's two refusal classes carries its argument out (their arguments are constant
    codes of the release code). Any other exception, whatever its argument looks like, leaves as the name of its class."""
    code,line=direct(context(),k11.fake_tree(verify_error='RELEASE_CLOCK_INVALID'));assert line['release']['code']=='RELEASE_CLOCK_INVALID'
    code,line=direct(context(),k11.fake_tree(verify_foreign_error='AAPL'));assert (line['release']['verified'],line['release']['code'])==(False,'RuntimeError')
    code,line=direct(context(),k11.fake_tree(assembler_error='POLICY_CAPACITY'));assert line['policy']['assembler']=={'valid':False,'code':'POLICY_CAPACITY'}
    code,line=direct(context(),k11.fake_tree(assembler_foreign_error='AAPL'));assert line['policy']['assembler']=={'valid':False,'code':'ValueError'}
    code,line=direct(context(),k11.fake_tree(policy_error='LIVE_POLICY_INVALID'));assert line['policy']['controller_now']=={'valid':False,'code':'LIVE_POLICY_INVALID'}
    code,line=direct(context(),k11.fake_tree(policy_foreign_error='MSFT'));assert line['policy']['controller_now']=={'valid':False,'code':'KeyError'} and 'MSFT' not in json.dumps(line)
    code,line=direct(context(),k11.fake_tree(calendar_token_error='AAPL'));assert (code,line)==(1,{'status':'FAILED','code':'RuntimeError'})
    # an argument of a refusal class that is not an upper-case token is not carried either
    for value in ('postgresql://user:secret@db/c3po','lower_case','WITH SPACE','A'*81,'9LIVES'):
        code,line=direct(context(),k11.fake_tree(verify_error=value));assert line['release']['code']=='ShadowIntegrityError',value
    m,docs,host=fresh('PRE');host.docker.on_run=k11.Container(k11.fake_tree(verify_foreign_error='AAPL'));receipt=docs.run(host)
    assert receipt['items']['verify']['release']['code']=='RuntimeError' and 'AAPL' not in json.dumps(receipt)

def test_release_code_itself_is_imported_whole_by_a_dry_run_that_signs_no_policy_and_no_probe(real):
    """The reduced dry run imports the reader of the worker and the live controller of the release as well, with their
    own imports (the causal audit, the raw source, the maintenance gate, the live group): nothing on standard error."""
    tree,documents=real;release,policy=documents()
    docs,host=k11.case('PRE',release=release,policy=None,probe=None);container=k11.Container(tree);host.docker.on_run=container;receipt=docs.run(host)
    assert receipt['status']==COMPLETE and receipt['outcome']==docs.k.m.PRE_REDUCED_OUTCOME and container.stderr==[b''],(receipt['findings'],receipt['items']['verify'])
    assert receipt['items']['verify']['policy'] is None and receipt['items']['verify']['probe'] is None and receipt['items']['verify']['release']['verified'] is True
    # and the full dry run against the release's own code: the probe is read by the release's own reader
    docs,host=k11.case('PRE',release=release,policy=policy);container=k11.Container(tree);host.docker.on_run=container;receipt=docs.run(host)
    assert receipt['status']==COMPLETE and receipt['outcome']==docs.k.m.PRE_OUTCOME and receipt['items']['verify']['probe']=={'valid':True,'code':None} and container.stderr==[b'']
    # a policy file that is not the canonical form: accepted by the release's controller, refused by its assembler; here it never reaches the host
    for raw in (policy+b'\n',json.dumps(json.loads(policy),indent=2,sort_keys=True).encode()):
        docs,host=k11.case('POST',release=release,policy=raw);docs.chain();assert f.refusal(docs.authenticate)=='POLICY_NOT_CANONICAL'
