"""Pure offline planning. No executor, network, database, or authority issuer."""
from __future__ import annotations
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, cast

EPOCH = 'R2D2-V2-SHADOW-2026-10-05'
FIRST_SESSION = '2026-10-05'
SESSIONS = ('2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09')
DOCUMENT_ORDER_SHA = '4ecf60585900364ee8038ac855dc63f07a8cee7d35f39d802d29af7dd8f2204d'
RUNTIME_ORDER_SHA = '1ad8b90cfab651823eb677b830a0078d10c17447575c8d813c3883a718579d8e'
DELEGABLE = frozenset(('sources','causal_list','components','risk','bar_manifest','capture','policy_readonly'))
INDIVIDUAL = frozenset(('bar_merge_deploy_recertify','install_release','readback','activate','supervisor_install_activate','wind_down_28','admission','quote_refresh','quote_capture'))
REQUIRED_BINDINGS = ('signed_epoch_order_sha','release_sha','policy_sha','package_sha','calendar_pin_sha',
                     'recertification_receipt_sha','wind_down_28_receipt_sha','template_sha','input_receipts_sha','phase_window_sha')

class Refused(ValueError):
    pass

def need(condition: bool, code: str) -> None:
    if not condition: raise Refused(code)

def canonical(value: Any) -> bytes:
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()

def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()

def is_sha(value: Any) -> bool:
    return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None and value!='0'*64

def stamp(value: Any) -> datetime:
    need(isinstance(value,str),'CLOCK_REQUIRED')
    try: result=datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError,TypeError): raise Refused('CLOCK_INVALID') from None
    need(result.utcoffset() is not None,'CLOCK_UTC_REQUIRED')
    return result.astimezone(timezone.utc)

def session_day(value: Any) -> date:
    need(type(value) is str,'DAY_INVALID')
    try: parsed=date.fromisoformat(value)
    except ValueError: raise Refused('DAY_INVALID') from None
    need(parsed.isoformat()==value,'DAY_INVALID')
    return parsed

def validate_identity(identity: dict, day: str, calendar: Any) -> dict:
    need(type(identity) is dict and set(identity)=={'epoch','namespace','first_session','authorized_sessions','document_order_sha','runtime_order_sha'},'IDENTITY_FIELDS')
    need(identity['epoch']==identity['namespace']==EPOCH and identity['first_session']==FIRST_SESSION,'EPOCH_IDENTITY')
    need(identity['document_order_sha']==DOCUMENT_ORDER_SHA,'DOCUMENT_ORDER_BINDING')
    need(identity['runtime_order_sha']==RUNTIME_ORDER_SHA,'RUNTIME_ORDER_BINDING')
    need(identity['authorized_sessions']==list(SESSIONS),'AUTHORIZED_SESSIONS')
    actual=calendar.sessions(session_day(FIRST_SESSION),len(SESSIONS))
    need([d.isoformat() for d in actual]==list(SESSIONS),'CALENDAR_CHANGED')
    parsed=session_day(day)
    need(day in SESSIONS and calendar.is_session(parsed),'DAY_NOT_AUTHORIZED')
    detail=calendar.details(parsed)
    previous=detail['previous_sessions'][-1]
    return {'day':day,'previous_session':previous.isoformat(),
            'previous_close':calendar.details(previous)['close'].isoformat(),'calendar_sha':detail['sha256'],
            'open':detail['open'].isoformat(),'close':detail['close'].isoformat()}

def validate_policy(policy: dict, identity: dict, bindings: dict, calendar: Any) -> None:
    need(type(policy) is dict,'POLICY_REQUIRED')
    need(policy.get('schema')=='R2D2_V2_LIVE_POLICY_V1' and policy.get('mode')=='LIVE','POLICY_SCHEMA')
    need(policy.get('epoch')==identity['epoch'] and policy.get('release_sha')==bindings['release_sha'],'POLICY_IDENTITY')
    need(policy.get('order_sha')==identity['runtime_order_sha'],'POLICY_RUNTIME_ORDER')
    need(policy.get('package_sha')==bindings['package_sha'],'POLICY_PACKAGE')
    need(type(policy.get('capacity')) is int and 1<=policy['capacity']<=550,'POLICY_CAPACITY')
    need(re.fullmatch('[0-9a-f]{40}',str(policy.get('code_revision',''))) is not None,'POLICY_REVISION')
    need(all(is_sha(policy.get(k)) for k in ('c8_receipt_sha','head_go_sha')),'POLICY_RECERTIFICATION')
    start,end=stamp(policy.get('valid_from')),stamp(policy.get('valid_until'))
    need(start<end and end-start<=timedelta(days=90),'POLICY_WINDOW')
    first=calendar.details(session_day(FIRST_SESSION));last=calendar.details(session_day(SESSIONS[-1]))
    need(start<=first['open'] and end>=last['close'],'POLICY_NOT_EPOCH_WIDE')
    # No permission for a sixth session follows from a broader policy clock.
    # Every daily action separately validates membership in SESSIONS.
    need(digest(policy)==bindings['policy_sha'],'POLICY_HASH')

def bindings_missing(bindings: dict) -> list[str]:
    need(type(bindings) is dict and set(bindings)==set(REQUIRED_BINDINGS),'BINDING_FIELDS')
    need(all(value is None or is_sha(value) for value in bindings.values()),'BINDING_INVALID')
    return [name for name in REQUIRED_BINDINGS if bindings[name] is None]

def plan(identity: dict, *, day: str, phase: str, bindings: dict, policy: dict | None,
         calendar: Any, previous: dict | None=None, consumer_binding: dict | None=None) -> dict:
    daily=validate_identity(identity,day,calendar)
    need(phase in DELEGABLE|INDIVIDUAL,'PHASE_UNKNOWN')
    if phase in {'install_release','readback','activate'}:
        need(day==FIRST_SESSION,'FIRST_SESSION_PHASE_ONLY')
    missing=bindings_missing(bindings)
    if policy is None: missing=missing+['policy_document']
    elif not any(bindings[k] is None for k in ('release_sha','policy_sha','package_sha')):
        validate_policy(policy,identity,bindings,calendar)
    state={'identity':identity,'daily':daily,'phase':phase,'bindings':bindings,
           'authority_mode':'INDIVIDUAL_ONLY' if phase in INDIVIDUAL else 'INDIVIDUAL_OR_SIGNED_ACT_B',
           'consumer_capacity_binding':consumer_binding if consumer_binding is not None else 'UNBOUND','automatic_retry':False}
    # Round-trip isolates caller-owned objects. Plans never mutate their inputs.
    state=json.loads(canonical(state))
    delta=[]
    old=previous.get('proposal',{}) if previous else {}
    if old:
        need(old.get('identity')==identity,'EPOCH_IDENTITY_CHANGED')
        for key in ('release_sha','policy_sha','package_sha'):
            prior=old.get('bindings',{}).get(key)
            need(prior is None or prior==bindings[key],'EPOCH_BINDING_CHANGED')
    for key in sorted(set(old)|set(state)):
        if old.get(key)!=state.get(key):delta.append({'field':key,'before':old.get(key),'after':state.get(key)})
    return {'schema':'ASSEMBLER02_OFFLINE_PLAN_V1','status':'UNBOUND' if missing else 'BOUND_FOR_REVIEW_ONLY',
            'execution_authorized':False,'missing_bindings':missing,'proposal':state,
            'proposal_sha':digest(state),'diff':delta}

def validate_go(go: Any, proposed: dict, *, now: datetime,
                authority_verifier: Callable[[dict,dict],bool] | None=None) -> dict:
    """Validate supplied evidence only; never generates GO or executes anything.
    The injected verifier must independently verify signatures/publication/veto.
    No production verifier is supplied by this offline candidate.
    """
    need(proposed.get('status')=='BOUND_FOR_REVIEW_ONLY','PLAN_UNBOUND')
    need(type(go) is dict,'GO_REQUIRED')
    required={'decision','epoch','first_session','day','phase','proposal_sha','signed_order_sha','template_sha',
              'mode','not_before','not_after','automatic_retry','authority_receipts'}
    need(set(go)==required,'GO_FIELDS')
    p=proposed['proposal'];bindings=p['bindings']
    need(go['decision']=='GO' and go['epoch']==EPOCH and go['first_session']==FIRST_SESSION,'GO_IDENTITY')
    need(go['day']==p['daily']['day'] and go['phase']==p['phase'],'GO_DAY_PHASE')
    need(go['proposal_sha']==proposed['proposal_sha'] and digest(p)==proposed['proposal_sha'],'GO_PLAN_HASH')
    need(go['signed_order_sha']==bindings['signed_epoch_order_sha'] and go['template_sha']==bindings['template_sha'],'GO_AUTHORITY_BINDING')
    need(go['automatic_retry'] is False,'GO_RETRY_FORBIDDEN')
    need(isinstance(now,datetime) and now.utcoffset() is not None,'CLOCK_UTC_REQUIRED')
    before,after=stamp(go['not_before']),stamp(go['not_after'])
    need(before<=now<after,'GO_WINDOW')
    window: Any=go['authority_receipts'].get('phase_window') if type(go['authority_receipts']) is dict else None
    need(type(window) is dict and set(window)=={'epoch','day','phase','not_before','not_after'},'PHASE_WINDOW_REQUIRED')
    need(digest(window)==bindings['phase_window_sha'],'PHASE_WINDOW_HASH')
    need(window['epoch']==EPOCH and window['day']==go['day'] and window['phase']==go['phase'],'PHASE_WINDOW_SCOPE')
    need(before==stamp(window['not_before']) and after==stamp(window['not_after']),'PHASE_WINDOW_MISMATCH')
    need(go['mode'] in ('INDIVIDUAL','DELEGATED_ACT_B'),'GO_MODE')
    receipts=go['authority_receipts'];need(type(receipts) is dict,'GO_RECEIPTS')
    if go['mode']=='DELEGATED_ACT_B':
        need(p['phase'] in DELEGABLE,'GO_INDIVIDUAL_REQUIRED')
        need(is_sha(receipts.get('signed_act_b_sha')) and is_sha(receipts.get('publication_receipt_sha')),'ACT_B_REQUIRED')
        need(stamp(receipts.get('published_at'))<=before-timedelta(minutes=15),'GO_NOTICE_TOO_SHORT')
    need(authority_verifier is not None,'AUTHORITY_VERIFIER_UNBOUND')
    need(cast(Callable[[dict,dict],bool],authority_verifier)(go,proposed) is True,'AUTHORITY_UNVERIFIED_OR_VETOED')
    return {'status':'EVIDENCE_CHECKED_OFFLINE_ONLY','execution_authorized':False,
            'attempt_key':digest([EPOCH,go['day'],go['phase'],go['template_sha']]),
            'go_sha':digest(go),'requires_durable_single_use_executor':True}
