"""The pinned readiness snippet, executed: the exact bytes K9R puts on standard input, run by a real interpreter in
isolated mode (`python -I -B - <D> <request sha256>`), against the stand-in package of tests/k9r.py on every
interpreter, and against the release's own modules (dd4ec4bb: the producer, the settings, the package hash, the XNYS
calendar) where a checkout of the release tree and its libraries are available, with the provider replaced by a
stand-in httpx module that records each request. A differential against E28's own evaluation
(probe_eligible_ready.py:evaluate) on the same payloads, where that file stands. Nothing here reaches a network."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

import family as f
import k9r

M=f.load(k9r.DIRECTORY).m
SNIPPET=M.K9_PROBE_SNIPPET.encode('ascii')
REQUEST='4f'*32
# The export of the release dd4ec4bb ($S/docs03/recert03/export: tree/ and dd4ec4bb.tar), named by the environment only;
# without it the release-module tests skip. No path of a workstation is written here.
EXPORT=os.environ.get('HOSTOPS02_TEST_RELEASE_EXPORT','')
SCRATCH=Path(EXPORT) if EXPORT else None
TREE=SCRATCH/'tree'/'c3po'/'backend' if SCRATCH else Path('/nonexistent-release-export/tree')
TAR=SCRATCH/'dd4ec4bb.tar' if SCRATCH else Path('/nonexistent-release-export/dd4ec4bb.tar')
TAR_SHA256='61bf5dd5e8b4c5b1e421b16949b4294f5dbfefe44a164d7097cdce7167e57660'
E28=Path(k9r.DIRECTORY).parent.parent/'r2d2-plan-b-baseline-20260927'/'bound-package-rev3'/'driver'/'probe_eligible_ready.py'

def test_static_snippet_bytes_and_hash():
    assert M.K9_PROBE_SNIPPET_SHA256=='a46e7609d70da12fe2288e59f4b6e396695ad7ec671c178286eb15aa773c4511'==hashlib.sha256(SNIPPET).hexdigest()
    assert len(SNIPPET)==4287 and SNIPPET.startswith(b'import signal\nsignal.alarm(34)\n') and SNIPPET.endswith(b"raise SystemExit(0 if out['status'] == 'DONE' else 1)\n")
    text=SNIPPET.decode('ascii')
    imports=sorted(line.strip() for line in text.splitlines() if line.strip().startswith(('import ','from ')))
    assert imports==['from app import r2d2_v2_producer_daily as producer','from app.config import get_settings',
                     'from app.r2d2_v2_earnings_package import implementation_package_sha','from datetime import date, datetime, timezone',
                     'import hashlib, json, os, re, sys','import signal']
    for word in ('print(','open(','subprocess','socket','eval(','exec(','environ[','write_private','sleep'):assert word not in text
    assert text.count('api_token')==1 and 'settings.eodhd_api_token,' in text                  # given to the packaged fetcher, never printed
    assert "EodhdFetcher(settings.eodhd_base_url, settings.eodhd_api_token, timeout=15.0, retries=0)" in text
    assert "NUMERATOR, DENOMINATOR = 95, 100" in text and "MINIMUM_ELIGIBLE = 4000" in text and "ready = denominator >= MINIMUM_ELIGIBLE and" in text and "'%s'"%k9r.PACKAGE in text

def execute(tree,arguments=('2026-10-06',REQUEST),environment=None,now='2026-10-05T21:26:30+00:00',alarm=None,python=None,extra=''):
    shim=k9r.SHIM%(tree,now)
    if alarm:shim+='import os as _k9_os,signal as _k9_signal\n_k9_alarm=_k9_signal.alarm\n_k9_signal.alarm=lambda seconds:(_k9_os.write(2,b"ALARM=%%d\\n"%%seconds),_k9_alarm(%d))[1]\n'%alarm
    shim+=extra
    env={'PATH':'/usr/bin:/bin','C3PO_EODHD_API_TOKEN':k9r.CANARY,'C3PO_R2D2_V2_PRODUCERS_ENABLED':'true'} if environment is None else environment
    done=subprocess.run([python or sys.executable,'-I','-B','-']+list(arguments),input=shim.encode()+SNIPPET,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=120)
    assert k9r.CANARY.encode() not in done.stdout+done.stderr
    return done
def line(done):
    assert done.stdout.endswith(b'\n') and done.stdout.count(b'\n')==1;return json.loads(done.stdout)

def fake(**knobs):
    registry,bulk=k9r.provider_rows(**{key:knobs.pop(key) for key in ('eligible','present','conflicts') if key in knobs})
    values=dict(registry=registry,bulk=bulk,token=k9r.CANARY,expect_date='2026-10-05');values.update(knobs);return k9r.fake_tree(**values)

def test_ready_line_on_the_stand_in():
    done=execute(fake());out=line(done)
    assert done.returncode==0 and done.stderr==b'' and set(out)==M.K9_PROBE_DONE_KEYS and out['readiness']=='READY' and out['request_sha256']==REQUEST
    assert out['previous_session']=='2026-10-05' and out['day']=='2026-10-06' and out['logical_fetch_calls']==2 and b'S000' not in done.stdout
    assert M.k9_probe_line(done.stdout,0,{'day':'2026-10-06'},REQUEST)==out
@pytest.mark.parametrize('arguments',[(),('2026-10-06',),('2026-10-6',REQUEST),('2026-10-06','X'*64),('2026-10-06',REQUEST,'extra')])
def test_arguments_are_two_and_in_their_grammar(arguments):
    done=execute(fake(),arguments=arguments);out=line(done)
    assert done.returncode==1 and out=={'status':'FAILED','code':'ARGUMENTS_INVALID','logical_fetch_calls':0,'request_sha256':None}
def test_the_producers_switch_and_the_package_come_before_any_call():
    done=execute(fake(),environment={'PATH':'/usr/bin:/bin','C3PO_EODHD_API_TOKEN':k9r.CANARY});out=line(done)
    assert out['code']=='PRODUCERS_NOT_ENABLED' and out['logical_fetch_calls']==0 and out['request_sha256']==REQUEST
    out=line(execute(fake(package='0'*64)));assert out['code']=='PACKAGE_NOT_THE_CERTIFIED_ONE' and out['logical_fetch_calls']==0
def test_a_message_never_leaves_only_a_class_name_or_a_constant():
    out=line(execute(fake(settings_error=True)));assert out['code']=='RuntimeError'
    out=line(execute(fake(fail_path='/api/eod-bulk-last-day/US')));assert out['code']=='PROVIDER_REQUEST_FAILED' and out['logical_fetch_calls']==2
def test_the_alarm_ends_a_hanging_interpreter():
    done=execute(fake(hang_path='/api/exchange-symbol-list/US'),alarm=1)
    assert done.returncode in (-14,142) and done.stdout==b'' and done.stderr==b'ALARM=34\n'

# ---------------------------------------------------------------- the release's own modules
HTTPX='''import sys,types,json,datetime as _k9_datetime
_k9_httpx=types.ModuleType('httpx')
class HTTPError(Exception):pass
_k9_httpx.HTTPError=HTTPError
_k9_payloads=%r
_k9_fail=%r
_k9_log=[]
class _Answer:
    def __init__(self,content):self.content=content
    def raise_for_status(self):pass
def _k9_get(url,params=None,timeout=None,follow_redirects=None):
    _k9_log.append([url,sorted(params),params.get('fmt'),params.get('api_token')==%r,timeout,follow_redirects,params.get('date')])
    sys.stderr.write(json.dumps(_k9_log[-1])+'\\n')
    if _k9_fail:raise HTTPError('a message with the url '+url+' and the token '+params.get('api_token',''))
    return _Answer(_k9_payloads[url.rsplit('/api/',1)[1]].encode())
_k9_httpx.get=_k9_get
sys.modules['httpx']=_k9_httpx
'''
def real_python():
    """An interpreter that can import the release's modules (pydantic-settings, exchange_calendars): this one or none."""
    if not (TREE/'app'/'r2d2_v2_producer_daily.py').is_file():return None
    done=subprocess.run([sys.executable,'-I','-c','import pydantic_settings,exchange_calendars,pandas'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    return sys.executable if done.returncode==0 else None

def real_rows(eligible=4000,present=3900,day='2026-09-25'):
    registry=[{'Code':'R%03d'%index,'Name':'synthetic','Country':'USA','Exchange':'NYSE','Currency':'USD','Type':'Common Stock','Isin':None} for index in range(eligible)]
    registry+=[{'Code':'F%02d'%index,'Name':'fund','Country':'USA','Exchange':'NYSE ARCA','Currency':'USD','Type':'ETF','Isin':None} for index in range(3)]
    bulk=[{'code':'R%03d'%index,'exchange_short_name':'US','date':day,'open':10.0,'high':11.0,'low':9.5,'close':10.5,'adjusted_close':10.5,'volume':1000}
          for index in range(present)]
    bulk.append({'code':'R000','exchange_short_name':'US','date':day,'open':12.0,'high':13.0,'low':11.0,'close':12.5,'adjusted_close':12.5,'volume':5})
    return registry,bulk

def run_real(registry,bulk,day='2026-09-28',fail=False):
    python=real_python()
    if python is None:pytest.skip('the release tree or its libraries (pydantic-settings, exchange_calendars) are not available to this interpreter')
    payloads={'exchange-symbol-list/US':json.dumps(registry),'eod-bulk-last-day/US':json.dumps(bulk)}
    shim='import sys\nsys.path.append(%r)\n'%str(TREE)+HTTPX%(payloads,fail,k9r.CANARY)
    env={'PATH':'/usr/bin:/bin','C3PO_EODHD_API_TOKEN':k9r.CANARY,'C3PO_R2D2_V2_PRODUCERS_ENABLED':'true','HOME':'/nonexistent'}
    done=subprocess.run([python,'-I','-B','-',day,REQUEST],input=shim.encode()+SNIPPET,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=300)
    assert k9r.CANARY.encode() not in done.stdout and b'R001' not in done.stdout
    calls=[json.loads(item) for item in done.stderr.decode().splitlines() if item.startswith('[')]
    return done,calls

def test_real_modules_ready_with_the_packaged_fetcher_at_zero_retries():
    registry,bulk=real_rows();done,calls=run_real(registry,bulk);out=line(done)
    assert done.returncode==0 and out['readiness']=='READY' and out['previous_session']=='2026-09-25' and out['eligible_symbols']==4000
    assert out['present_eligible_symbols']==3900 and out['conflicting_eligible_symbols']==1 and out['usable_eligible_symbols']==3899 and out['required_minimum']==3800
    assert out['registry_payload_sha256']==hashlib.sha256(json.dumps(registry).encode()).hexdigest()
    assert calls==[['https://eodhd.com/api/exchange-symbol-list/US',['api_token','fmt'],'json',True,15.0,True,None],
                   ['https://eodhd.com/api/eod-bulk-last-day/US',['api_token','date','fmt'],'json',True,15.0,True,'2026-09-25']]
def test_real_modules_not_ready_and_a_failed_call_is_not_retried():
    registry,bulk=real_rows(present=3799);done,calls=run_real(registry,bulk);assert line(done)['readiness']=='NOT_READY'
    registry40,bulk40=real_rows(eligible=40,present=40);done,calls=run_real(registry40,bulk40);assert line(done)['readiness']=='NOT_READY'     # degenerate registry
    done,calls=run_real(registry,bulk,fail=True);out=line(done)
    assert done.returncode==1 and out=={'status':'FAILED','code':'PROVIDER_REQUEST_FAILED','logical_fetch_calls':1,'request_sha256':REQUEST} and len(calls)==1
def test_real_modules_refuse_before_the_close_of_the_previous_session():
    registry,bulk=real_rows();done,calls=run_real(registry,bulk,day='2026-10-30');out=line(done)
    assert out['code']=='PREVIOUS_SESSION_NOT_CLOSED' and calls==[]

def test_differential_with_the_evaluation_of_e28():
    """E28's probe_eligible_ready.evaluate on the same two payloads, with the release's producer module: the same counts."""
    python=real_python()
    if python is None or not E28.is_file():pytest.skip('the release tree, its libraries or the E28 driver are not available')
    registry,bulk=real_rows()
    done,_=run_real(registry,bulk);out=line(done)
    script='''import sys,json
sys.path.insert(0,%r)
from datetime import date,datetime,timezone
import importlib.util
spec=importlib.util.spec_from_file_location('e28',%r);e28=importlib.util.module_from_spec(spec);spec.loader.exec_module(e28)
from app import r2d2_v2_producer_daily as producer
utc=timezone.utc
request=e28.ProbeRequest(date(2026,9,25),datetime(2026,9,25,20,tzinfo=utc),datetime(2026,9,27,21,tzinfo=utc),datetime(2026,9,28,2,30,tzinfo=utc))
registry=producer.Response(json.dumps(%r).encode(),datetime(2026,9,27,21,10,tzinfo=utc),e28.REGISTRY_PATH)
bulk=producer.Response(json.dumps(%r).encode(),datetime(2026,9,27,21,11,tzinfo=utc),e28.BULK_PATH)
outcome=e28.evaluate(producer,registry,bulk,request,datetime(2026,9,27,21,12,tzinfo=utc))
print(json.dumps(outcome.public,sort_keys=True))
'''%(str(TREE),str(E28),registry,bulk)
    done=subprocess.run([python,'-I','-B','-'],input=script.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent'},timeout=300)
    assert done.returncode==0,done.stderr.decode()[-2000:]
    public=json.loads(done.stdout)
    for key in ('registry_symbols','eligible_symbols','present_eligible_symbols','required_minimum','usable_eligible_symbols',
                'conflicting_eligible_symbols','duplicate_eligible_rows','bulk_rows','dated_rows','logical_fetch_calls'):
        assert out[key]==public[key],key
    assert out['readiness']==public['status']

def test_static_the_release_modules_used_are_those_of_the_pinned_tar():
    if not (TAR.is_file() and TREE.is_dir()):pytest.skip('the release export is not available')
    assert hashlib.sha256(TAR.read_bytes()).hexdigest()==TAR_SHA256
    with tarfile.open(str(TAR)) as archive:
        for name in ('__init__.py','config.py','r2d2_v2_earnings_package.py','r2d2_v2_producer_daily.py'):
            member=archive.extractfile('c3po/backend/app/'+name).read();assert member==(TREE/'app'/name).read_bytes(),name
