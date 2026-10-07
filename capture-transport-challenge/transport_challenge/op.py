OPERATION='GO_READONLY_HOSTOPS02_CAPTURE_TRANSPORT_CHALLENGE_01'
PHASE='READONLY_CAPTURE_TRANSPORT_CHALLENGE'
REQUEST_SCHEMA='READONLY_HOSTOPS02_CAPTURE_TRANSPORT_CHALLENGE_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS02_CAPTURE_TRANSPORT_CHALLENGE_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS02_CAPTURE_TRANSPORT_CHALLENGE_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS02_CAPTURE_TRANSPORT_CHALLENGE_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_CAPTURE_TRANSPORT_CHALLENGE_PLAN_V1'
SOURCE_NAME='capture_transport_challenge.py'
WRITES_ALLOWED=False
ACTIVATION_ALLOWED=False
DATE_CLASS='READ'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=False
EVIDENCE_OPERATIONS=()
MAX_GATE_SPAN_SECONDS=600
COMPLETE_OUTCOME='AUTHENTICATED_CAPTURE_TRANSPORT_CHALLENGE_RETURNED'
PARTIAL_OUTCOME='PARTIAL_CHALLENGE_REQUIRES_REVIEW'
REFUSED_OUTCOME='REFUSED_NOTHING_OBSERVED'
REDUCED_OUTCOME='PARTIAL_CHALLENGE_REQUIRES_REVIEW'
ESCAPED_OUTCOME='PARTIAL_CHALLENGE_REQUIRES_REVIEW'
PLAN_KEYS=frozenset(('session','run_id','run_attempt','nonce'))
SCOPE_STATEMENT=('One dated authenticated stdin transport challenge on 08 October 2026, in the same Thursday '
    'runner job before any policy or capture PREPARE. Only returns signed session/run/attempt/nonce and '
    'authentication digests after exact request/authority/GO verification and UID 0 check. '
    'No host filesystem read, write, root source walk, BOOT claim, SQL, container, app import, activation or retry. '
    'The runner dispatcher creates its own durable local once claims and public intent; SSH/sudo can produce '
    'ordinary remote authentication/audit logs. This is only transport evidence, not K9 host readiness.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
 'writes_allowed':False,'activation_allowed':False,'never':['host file read/write','BOOT claim','SQL','Docker','app import','activation','retry'],
 'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT},
 'dated_session':'2026-10-08','dated_window_UTC':['2026-10-08T11:52:00+00:00','2026-10-08T12:02:00+00:00']}
SCOPE_SHA256=sha(canonical(SCOPE))
REDUCTIONS=[]
class Native:
    pass

def validate_plan(plan):
    need(plan['session']=='2026-10-08','CAPTURE_TRANSPORT_SESSION')
    need(text(plan['run_id'],'[1-9][0-9]{5,19}'),'CAPTURE_TRANSPORT_RUN')
    need(type(plan['run_attempt']) is int and plan['run_attempt']==1,'CAPTURE_TRANSPORT_RETRY_FORBIDDEN')
    need(text(plan['nonce'],'[0-9a-f]{32}'),'CAPTURE_TRANSPORT_NONCE')
    need(plan['window']=={'not_before':'2026-10-08T11:52:00+00:00','expires_at':'2026-10-08T12:02:00+00:00'},'CAPTURE_TRANSPORT_DATED_WINDOW')

def effects_of(plan):
    return {'operation':OPERATION,'session':plan['session'],'run_id':plan['run_id'],
            'run_attempt':plan['run_attempt'],'nonce':plan['nonce'],'host_writes':0,'host_file_reads':0,
            'root_source_walks':0,'BOOT_claims':0,'SQL':0,'containers':0,'activation':False}

def success_of(plan):
    return COMPLETE_OUTCOME

def perform(plan,gate,host,bound,clock,monotonic,state):
    # All inputs authenticated by the frozen core. No host object method is called.
    gate()
    result=dict(bound,session=plan['session'],run_id=plan['run_id'],run_attempt=plan['run_attempt'],
                nonce=plan['nonce'],executor_uid_verified=0,effects=effects_of(plan),
                mutating_calls=state.counts(),host_reads=0,writes=0,activation_performed=False,
                daemon_reload_performed=False,transport_only=True,host_readiness=False)
    gate()
    return seal(envelope(COMPLETE_STATUS,COMPLETE_OUTCOME,None,result))
