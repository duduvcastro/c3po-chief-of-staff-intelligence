"""Pinned consumer codec: four exact function source segments, no app imports.

Source document_format e7c1758e985d27e4a0bf15f911eba176eefc5154e7929c5f5aba472f9e28c0da.
Only normalize_document('ACT_B', raw) is exposed by the finalizer. Other label
branches require original app dependencies and are deliberately not used.
"""
import json
from datetime import timedelta
import veto_emitter as veto
BEGIN=veto.BEGIN
END=veto.END
SCHEMA=veto.DOCUMENT_SCHEMA
COMMON={'schema','kind','state','body'}
canonical=veto.canonical
is_sha=lambda value:type(value)is str and veto.SHA.fullmatch(value)is not None
utc=veto.instant
class ShadowIntegrityError(ValueError):pass
def need(ok,code):
    if not ok:raise ShadowIntegrityError(code)

def parse_document(raw,*,allow_draft=False):
    try:
        need(type(raw) is bytes and len(raw)<=1024*1024,'DOCUMENT_SIZE')
        text=raw.decode('utf-8')
        need(text.count(BEGIN)==text.count(END)==1,'DOCUMENT_MARKERS')
        before,tail=text.split(BEGIN);payload,after=tail.split(END)
        need(not after.strip(),'DOCUMENT_TRAILING_TEXT')
        lines=payload.strip().splitlines()
        need(len(lines)==3 and lines[0]=='```json' and lines[2]=='```','DOCUMENT_CANONICAL_BLOCK')
        def pairs(items):
            result={}
            for key,value in items:need(key not in result,'DOCUMENT_DUPLICATE_KEY');result[key]=value
            return result
        doc=json.loads(lines[1],object_pairs_hook=pairs)
        need(type(doc) is dict and set(doc)==COMMON and doc['schema']==SCHEMA,'DOCUMENT_FIELDS')
        need(canonical(doc).decode()==lines[1],'DOCUMENT_NOT_CANONICAL')
        need(doc['state'] in ({'DRAFT','ISSUED'} if allow_draft else {'ISSUED'}),'DOCUMENT_DRAFT_OR_UNBOUND')
        need(type(doc['body']) is dict,'DOCUMENT_BODY')
        return doc
    except ShadowIntegrityError:raise
    except (ValueError,UnicodeError,TypeError,KeyError):raise ShadowIntegrityError('DOCUMENT_PARSE_INVALID') from None

def normalized_fields(body,required,optional=()):
    need(set(required)<=set(body)<=set(required)|set(optional),'DOCUMENT_BODY_FIELDS')

def act_b_template_shas(body):
    """Contract-template digest per authorized session; each template binds its own day.

    `template_shas` must name exactly the authorized sessions. The scalar
    `template_sha` form is accepted only for an Act B scoped to a single session.
    """
    days=body['authorized_sessions']
    need(type(days) is list and days and all(type(d) is str for d in days) and len(days)==len(set(days)),'ACT_B_TEMPLATE_DAYS')
    need(('template_sha' in body)!=('template_shas' in body),'ACT_B_TEMPLATE_FORM')
    if 'template_sha' in body:
        need(len(days)==1 and is_sha(body['template_sha']),'ACT_B_TEMPLATE_SCALAR')
        return {days[0]:body['template_sha']}
    shas=body['template_shas']
    need(type(shas) is dict and set(shas)==set(days) and len(shas)==len(days)
         and all(is_sha(v) for v in shas.values()) and len(set(shas.values()))==len(shas),'ACT_B_TEMPLATE_MAP')
    return dict(shas)

def normalize_document(label,raw):
    if label in {'CODEX','FABLE','DUDU'} and raw.lstrip().startswith(b'{'):
        return normalize_owner_signature(raw) if label=='DUDU' else normalize_legacy_a(label,raw)
    doc=parse_document(raw);body=doc['body'];kind=doc['kind']
    try:
        if label in {'CODEX','FABLE','DUDU'} or label in {'B_CODEX','B_FABLE','B_DUDU'}:
            need(kind=='APPROVAL','DOCUMENT_KIND')
            required={'role','decision','previous_sha','epoch','first_session','authorized_sessions'}
            if not label.startswith('B_'):required.add('document_sha256')
            if label.removeprefix('B_')=='DUDU':required.add('owner_evidence')
            if label.startswith('B_'):required|={'body_sha','act_a_head'}
            normalized_fields(body,required)
            if label.removeprefix('B_')=='DUDU':validate_owner_evidence(body['owner_evidence'],act='B' if label=='B_DUDU' else 'A')
            need(body['role']==label.removeprefix('B_') and body['decision']=='APPROVED','DOCUMENT_APPROVAL')
            need(body['previous_sha'] is None or is_sha(body['previous_sha']),'DOCUMENT_PREVIOUS_SHA')
            if label.startswith('B_'):need(is_sha(body['body_sha']) and is_sha(body['act_a_head']),'DOCUMENT_B_SHA')
        elif label=='ACT_B':
            need(kind=='ACT_B','DOCUMENT_KIND')
            normalized_fields(body,{'status','chain_head','order_sha','policy_sha','capacity','cut_rule',
                'subphases','individual_go_issuers','owner_countersign_phases','rollback_disposition','epoch','first_session',
                'authorized_sessions','causal_order','policy_epoch_validity','automatic_retry','document_order_sha','act_a_scope_map','templates','template_set_sha'},
                {'template_sha','template_shas'})
            need(body['status']=='ACCEPTED' and type(body['capacity']) is int and body['capacity']==550,'ACT_B_UNBOUND')
            need(all(is_sha(body[k]) for k in ('chain_head','order_sha','policy_sha','document_order_sha','template_set_sha')),'ACT_B_HASH_UNBOUND')
            act_b_template_shas(body)
            need(body['individual_go_issuers']==['FABLE'],'ACT_B_ISSUER_DECISION')
            need(body['owner_countersign_phases']==['bar_merge_deploy_recertify','install_release','activate','wind_down_28'],'ACT_B_OWNER_SCOPE')
            need(body['rollback_disposition']=='REVALIDATE_UNCOMMITTED_ONLY' and body['automatic_retry'] is False,'ACT_B_RETRY_DECISION')
            need(body['causal_order']=={'primary':'ADV_DESC','tie_break':'SYMBOL_ASC','cut':'TAIL_NEW_ONLY'},'ACT_B_CUT_ORDER')
            need(body['subphases']=={},'ACT_B_SUBPHASES')
            need(body['policy_epoch_validity'] is True,'ACT_B_POLICY_EPOCH')
        elif label=='TEMPLATE':
            need(kind=='TEMPLATE','DOCUMENT_KIND');normalized_fields(body,{'sha','epoch','first_session','authorized_sessions','phases'})
            need(is_sha(body['sha']),'TEMPLATE_HASH')
        elif label.startswith('GO:') or label.startswith('OWNER_GO:'):
            need(kind=='GO','DOCUMENT_KIND')
            normalized_fields(body,{'go_sha','template_sha','decision','role','epoch','first_session','day','phase'}, {'published_at'})
            need(body['phase']==label.split(':',1)[1] and body['decision']=='GO' and is_sha(body['go_sha']) and is_sha(body['template_sha']),'DOCUMENT_GO')
            need(body['role'] in {'FABLE','DUDU'},'DOCUMENT_GO_ROLE')
            if 'published_at' in body:utc(body['published_at'])
        elif label.startswith('PUBLICATION:'):
            need(kind=='PUBLICATION','DOCUMENT_KIND')
            normalized_fields(body,{'role','template_sha','phase','day','published_at','epoch','first_session'})
            need(body['role']=='FABLE' and body['phase']==label.split(':',1)[1] and is_sha(body['template_sha']),'DOCUMENT_PUBLICATION')
            utc(body['published_at'])
        else:raise ShadowIntegrityError('DOCUMENT_LABEL_UNSUPPORTED')
        return body
    except ShadowIntegrityError:raise
    except (ValueError,TypeError,KeyError):raise ShadowIntegrityError('DOCUMENT_NORMALIZATION_INVALID') from None
