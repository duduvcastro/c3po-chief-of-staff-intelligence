import json
from datetime import datetime,timezone,timedelta
import pytest
from app.r2d2_v2_massive_transport import pump
from app.r2d2_v2_sources import SourceUnavailable

class State:
 def __init__(self,n=550):self.symbols={'S'+str(i) for i in range(n)};self.gaps=[];self.frames=[];self.connections=[]
 def gap(self,at,reason):self.gaps.append(reason)
 def connected(self,at):self.connections.append(at)
 def frame(self,raw,at):self.frames.append(raw)
class Socket:
 def __init__(self,frames):self.frames=list(frames);self.sent=[];self.closed=False
 def send(self,v):self.sent.append(json.loads(v))
 def recv(self,timeout):
  assert timeout==1
  if not self.frames:raise TimeoutError()
  f=self.frames.pop(0)
  if isinstance(f,Exception):raise f
  return f
 def close(self):self.closed=True

def run(frames,**kwargs):
 s=State();socket=Socket(frames);counter=[0];ticks=[]
 def mono():counter[0]+=1;return counter[0]
 now=lambda:datetime(2026,9,28,14,tzinfo=timezone.utc)+timedelta(seconds=counter[0])
 result=pump(socket,s,'private-token',utcnow=now,monotonic=mono,tick=ticks.append,stop=lambda:False,max_seconds=20,auth_seconds=5,idle_seconds=10,**kwargs)
 return result,s,socket,ticks

def test_auth_then_exact_550_bounded_subscription():
 result,s,ws,ticks=run(['[{"ev":"status","status":"auth_success"}]'])
 assert result=='IDLE' and len(s.connections)==1 and ticks
 params=ws.sent[1]['params'].split(',');assert len(params)==550 and set(params)=={'AM.'+x for x in s.symbols}
 assert ws.closed and s.gaps==['MASSIVE_STREAM_IDLE']

def test_auth_timeout_never_subscribes():
 result,s,ws,_=run([]);assert result=='AUTH_TIMEOUT' and len(ws.sent)==1 and not s.connections and ws.closed

@pytest.mark.parametrize('status',['auth_failed','error','not_authorized'])
def test_provider_refusal_never_retries(status):
 result,s,ws,_=run([json.dumps([{'ev':'status','status':status}])]);assert result=='PROVIDER_REFUSAL' and len(ws.sent)==1 and ws.closed

def test_exception_redacts_token():
 with pytest.raises(SourceUnavailable,match='^MASSIVE_TRANSPORT_FAILURE$') as e:run([RuntimeError('private-token')])
 assert 'private-token' not in str(e.value)

def test_data_before_auth_rejected():
 with pytest.raises(SourceUnavailable,match='TRANSPORT_FAILURE'):run(['[{"ev":"AM","sym":"S0"}]'])


def test_real_connection_wrapper_limits_and_no_token_in_url_or_options():
 from app.r2d2_v2_massive_transport import run_connection
 calls=[];ws=Socket([]);state=State();stopped=[False]
 def connect(uri,**options):calls.append((uri,options));stopped[0]=True;return ws
 at=datetime(2026,9,28,14,tzinfo=timezone.utc)
 assert run_connection(state,'private-token',utcnow=lambda:at,monotonic=lambda:0,tick=lambda at:None,stop=lambda:stopped[0],connector=connect)=='STOPPED'
 uri,options=calls[0]
 assert uri=='wss://socket.massive.com/stocks' and 'private-token' not in str(calls)
 assert options['max_queue']==1 and options['open_timeout']==10 and options['close_timeout']==3
 assert options['ping_timeout']==10 and options['compression'] is None and options['proxy'] is None
 assert options['logger'].disabled and ws.closed


def test_connect_failure_typed_without_retry_or_secret():
 from app.r2d2_v2_massive_transport import run_connection
 calls=[];state=State();at=datetime(2026,9,28,14,tzinfo=timezone.utc)
 def connect(*a,**k):calls.append(1);raise OSError('private-token network error')
 with pytest.raises(SourceUnavailable,match='^MASSIVE_CONNECT_FAILURE$'):
  run_connection(state,'private-token',utcnow=lambda:at,monotonic=lambda:0,tick=lambda at:None,stop=lambda:False,connector=connect)
 assert calls==[1] and state.gaps==['MASSIVE_CONNECT_FAILURE']


def test_stop_before_connector_never_opens_or_authenticates():
 from app.r2d2_v2_massive_transport import run_connection
 state=State();at=datetime(2026,9,28,14,tzinfo=timezone.utc)
 def forbidden(*a,**k):pytest.fail('opened after stop')
 assert run_connection(state,'private-token',utcnow=lambda:at,monotonic=lambda:0,tick=lambda at:None,stop=lambda:True,connector=forbidden)=='STOPPED'


def test_window_expires_during_connect_never_sends_authentication():
 from app.r2d2_v2_massive_transport import run_connection
 state=State();socket=Socket([]);allowed=[True];at=datetime(2026,9,28,14,tzinfo=timezone.utc)
 def connect(*a,**k):allowed[0]=False;return socket
 with pytest.raises(SourceUnavailable):
  run_connection(state,'private-token',utcnow=lambda:at,monotonic=lambda:0,tick=lambda at:None,stop=lambda:False,start_allowed=lambda:allowed[0],connector=connect)
 assert socket.closed and socket.sent==[]


def test_stop_during_auth_receive_never_subscribes():
 state=State();socket=Socket([]);stopped=[False];at=datetime(2026,9,28,14,tzinfo=timezone.utc)
 def recv(timeout):stopped[0]=True;return '[{"ev":"status","status":"auth_success"}]'
 socket.recv=recv
 assert pump(socket,state,'private-token',utcnow=lambda:at,monotonic=lambda:0,tick=lambda at:None,stop=lambda:stopped[0])=='STOPPED'
 assert [x['action'] for x in socket.sent]==['auth'] and socket.closed
