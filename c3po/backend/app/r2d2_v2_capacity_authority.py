"""Offline strict boundary; externally verified documents required, no GO issuer."""
from datetime import date
from copy import deepcopy
from .r2d2_v2_epoch_assembler import plan, is_sha, digest as assembler_digest
from .r2d2_v2_store import ShadowIntegrityError, digest


def need(ok, code):
    if not ok: raise ShadowIntegrityError(code)


def calendar_pin(calendar, identity):
    return digest({'version':calendar.version, 'sessions':[
        {'day':day,'sha':calendar.details(date.fromisoformat(day))['sha256']}
        for day in identity['authorized_sessions']]})


def validate_contract(contract, *, release, day, causal, calendar):
    try:
        c=deepcopy(contract)
        need(set(c)=={'assembler_plan','policy','order','template','owner_sha','causal_scope','consumer_plans'},'CAPACITY_CONTRACT_FIELDS')
        a=c['assembler_plan'];p=a['proposal'];bindings=p['bindings'];identity=p['identity']
        need(a['status']=='BOUND_FOR_REVIEW_ONLY' and not a['missing_bindings'],'CAPACITY_ASSEMBLER_UNBOUND')
        authority_inputs={key:c[key] for key in ('owner_sha','order','policy','template','causal_scope')}
        consumer_binding={'schema':'CAPACITY_CONSUMER_INPUT_BINDING_V1','authority_inputs_sha':digest(authority_inputs)}
        need(p['consumer_capacity_binding']==consumer_binding,'CAPACITY_CONSUMER_UNBOUND')
        actual=plan(identity,day=day,phase=p['phase'],bindings=bindings,policy=c['policy'],calendar=calendar,consumer_binding=consumer_binding)
        need(actual['proposal']==p and a['proposal_sha']==assembler_digest(p),'CAPACITY_ASSEMBLER_MISMATCH')
        need(p['phase']=='admission','CAPACITY_ASSEMBLER_PHASE')
        need(set(c['consumer_plans'])=={'bar_manifest','quote_refresh','quote_capture'},'CAPACITY_CONSUMER_PHASES')
        for phase, consumer in c['consumer_plans'].items():
            cp=consumer['proposal']
            need(cp['phase']==phase and cp['identity']==identity and cp['daily']['day']==day,'CAPACITY_CONSUMER_PHASE')
            need({k:v for k,v in cp['bindings'].items() if k!='phase_window_sha'}=={k:v for k,v in bindings.items() if k!='phase_window_sha'},'CAPACITY_CONSUMER_BINDINGS')
            need(is_sha(cp['bindings']['phase_window_sha']) and cp['bindings']['phase_window_sha']!=bindings['phase_window_sha'],'CAPACITY_CONSUMER_WINDOW')
            expected=plan(identity,day=day,phase=phase,bindings=cp['bindings'],policy=c['policy'],calendar=calendar,consumer_binding=consumer_binding)
            need(consumer['status']=='BOUND_FOR_REVIEW_ONLY' and consumer['proposal']==expected['proposal']
                 and consumer['proposal_sha']==assembler_digest(cp),'CAPACITY_CONSUMER_PLAN')
        need(release.epoch==identity['epoch'] and release.first_session.isoformat()==identity['first_session']
             and release.receipt_sha==bindings['release_sha'],'CAPACITY_RELEASE')
        need(calendar_pin(calendar,identity)==bindings['calendar_pin_sha'],'CAPACITY_CALENDAR_PIN')
        order=c['order'];template=c['template']
        need(is_sha(c['owner_sha']) and all(is_sha(bindings[k]) for k in bindings),'CAPACITY_SHA')
        need(digest(order)==bindings['signed_epoch_order_sha'] and digest(template)==bindings['template_sha'],'CAPACITY_AUTHORITY_HASH')
        need(order['owner_sha']==template['owner_sha']==c['owner_sha'],'CAPACITY_OWNER')
        need(order['epoch']==template['epoch']==release.epoch and order['authorized_sessions']==identity['authorized_sessions']
             and template['day']==day and template['phases']==['admission','bar_manifest','quote_refresh','quote_capture'],'CAPACITY_AUTHORITY_SCOPE')
        need(type(order['capacity']) is int and order['capacity']==c['policy']['capacity']==550,'CAPACITY_LIMIT')
        need(template['rule']=='OPEN_FIRST_THEN_EXISTING_CAUSAL_ORDER_V1_PROPOSED','CAPACITY_RULE')
        scope=c['causal_scope']
        need(scope=={'epoch':release.epoch,'session':day,'commitment_sha256':causal['commitment_sha256'],
                     'list_sha256':causal['list_sha256']},'CAPACITY_CAUSAL_SCOPE')
        need(causal['epoch']==release.epoch and causal['session']==day and
             is_sha(causal['commitment_sha256']) and causal['list_sha256']==digest(causal['symbols']), 'CAPACITY_CAUSAL_BINDING')
        return c
    except ShadowIntegrityError: raise
    except (ValueError,TypeError,KeyError,AttributeError):
        raise ShadowIntegrityError('CAPACITY_CONTRACT_INVALID') from None
