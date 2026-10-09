"""Proposed exact documentary serialization, supplied/pinned offline evidence only.

DRAFT is readable for review but never normalizes into execution authority. File hashes
and complete approval chains are verified separately by DocumentAuthority.
"""
import hashlib,json,re
from datetime import timedelta
from .r2d2_v2_store import ShadowIntegrityError,utc
from .r2d2_v2_epoch_assembler import canonical,is_sha

BEGIN='<!-- R2D2-EVIDENCE-V1:BEGIN -->'
END='<!-- R2D2-EVIDENCE-V1:END -->'
SCHEMA='R2D2_DOCUMENTARY_EVIDENCE_V1'
COMMON={'schema','kind','state','body'}


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


class PinnedVetoReader:
    """Reads only the supplied file/pin; never polls, fetches or assumes no veto."""
    def __init__(self,root,*,file,sha256,epoch,day,order_sha):
        need(is_sha(sha256) and is_sha(order_sha),'VETO_PIN_UNBOUND')
        self.root=root;self.file=file;self.sha=sha256;self.epoch=epoch;self.day=day;self.order_sha=order_sha

    def __call__(self,now):
        raw=self.root.read(self.file)
        need(hashlib.sha256(raw).hexdigest()==self.sha,'VETO_HASH_MISMATCH')
        doc=parse_document(raw);need(doc['kind']=='VETO_VIEW','VETO_KIND')
        body=doc['body'];normalized_fields(body,{'status','role','epoch','day','order_sha','observed_at','valid_until','owner_veto','revoked_shas','evidence_sha'})
        need(body['status']=='VERIFIED' and body['role']=='FABLE' and body['epoch']==self.epoch and body['day']==self.day
             and body['order_sha']==self.order_sha and is_sha(body['evidence_sha']),'VETO_SCOPE')
        observed,until=utc(body['observed_at']),utc(body['valid_until']);now=utc(now)
        need(observed<=now<until and until-observed<=timedelta(seconds=10),'VETO_STALE')
        need(type(body['owner_veto']) is bool and type(body['revoked_shas']) is list
             and all(is_sha(item) for item in body['revoked_shas']),'VETO_FIELDS')
        return {key:body[key] for key in ('status','observed_at','valid_until','owner_veto','revoked_shas')}



def normalize_legacy_a(label,raw):
    """Map only the two actual issued A signature schemas; no operational authority.

    Missing DUDU evidence is never synthesized. Its explicit approval plus independent
    B chain must endorse the scope map binding these document hashes to runtime JSON.
    """
    try:
        need(type(raw) is bytes and len(raw)<=1024*1024,'DOCUMENT_SIZE')
        def pairs(items):
            result={}
            for key,value in items:need(key not in result,'DOCUMENT_DUPLICATE_KEY');result[key]=value
            return result
        body=json.loads(raw,object_pairs_hook=pairs)
        common={'schema','document','document_sha256','signer','verdict','execution_authorized','act_b_required_for_templates'}
        fields=common|({'authority_comment','review_sha256','operational_evidence_claimed','implementation_certified'} if label=='CODEX'
                       else {'codex_signature_sha256_verified_by_command','signed_at_utc'})
        need(set(body)==fields and body['schema']==label+'_DOCUMENTARY_SIGNATURE_V1' and body['signer']==label,'LEGACY_A_FORMAT')
        expected={'CODEX':'ACT_A_SCOPE_APPROVED_PENDING_FABLE_DUDU_SAME_REVISION','FABLE':'ACT_A_SCOPE_APPROVED_PENDING_DUDU_SAME_REVISION'}
        need(body['verdict']==expected[label] and body['execution_authorized'] is False and body['act_b_required_for_templates'] is True,'LEGACY_A_VERDICT')
        need(is_sha(body['document_sha256']),'LEGACY_A_DOCUMENT_HASH')
        previous=None if label=='CODEX' else body['codex_signature_sha256_verified_by_command']
        need(previous is None or is_sha(previous),'LEGACY_A_PREVIOUS_HASH')
        return {'role':label,'decision':'APPROVED','previous_sha':previous,'document_sha256':body['document_sha256'],'legacy_documentary_signature':True}
    except ShadowIntegrityError:raise
    except (ValueError,TypeError,KeyError):raise ShadowIntegrityError('LEGACY_A_INVALID') from None


class RenewableVetoReader:
    """Externally supplied pin provider; no implicit fetch, timestamp renewal or trust.

    The deployment must pin/authorize the provider itself. Each invocation supplies a
    fresh immutable evidence file and expected SHA; omission/change mismatch fails closed.
    """
    def __init__(self,root,*,pin_provider,epoch,day,order_sha):
        self.root=root;self.pin_provider=pin_provider;self.epoch=epoch;self.day=day;self.order_sha=order_sha

    def __call__(self,now):
        need(callable(self.pin_provider),'VETO_RENEWAL_UNBOUND')
        pin=self.pin_provider(now)
        need(type(pin) is dict and set(pin)=={'file','sha256'},'VETO_RENEWAL_PIN')
        return PinnedVetoReader(self.root,epoch=self.epoch,day=self.day,order_sha=self.order_sha,**pin)(now)



def validate_owner_evidence(evidence,*,act):
    need(type(evidence) is dict and set(evidence)=={'verbatim','channel','signed_at_utc'},'OWNER_EVIDENCE_FIELDS')
    need(all(type(evidence[k]) is str and evidence[k].strip() and len(evidence[k])<=8192 for k in evidence),'OWNER_EVIDENCE_UNBOUND')
    need(all(evidence[k].strip().upper() not in {'UNBOUND','PENDING','DRAFT'} for k in evidence),'OWNER_EVIDENCE_UNBOUND')
    validate_owner_answer(evidence['verbatim'],act=act)
    utc(evidence['signed_at_utc'])


def normalize_owner_signature(raw):
    """Map supplied OWNER_DOCUMENTARY_SIGNATURE_V1 bytes; never invent the answer.

    Only the shared exact affirmative allowlist is recognized. Other responses
    need explicit format review, not automatic reinterpretation as consent.
    """
    try:
        need(type(raw) is bytes and len(raw)<=1024*1024,'DOCUMENT_SIZE')
        def pairs(items):
            result={}
            for key,value in items:need(key not in result,'DOCUMENT_DUPLICATE_KEY');result[key]=value
            return result
        body=json.loads(raw,object_pairs_hook=pairs)
        required={'schema','document','document_sha256','prior_signatures','signer','owner_answer_verbatim','channel','signed_at_utc'}
        normalized_fields(body,required,{'supersedes_owner_signature_on','owner_question','order_note'})
        need(body['schema']=='OWNER_DOCUMENTARY_SIGNATURE_V1' and body['signer']=='DUDU' and is_sha(body['document_sha256']),'OWNER_SIGNATURE_FORMAT')
        evidence={'verbatim':body['owner_answer_verbatim'],'channel':body['channel'],'signed_at_utc':body['signed_at_utc']}
        validate_owner_evidence(evidence,act='A')
        prior=body['prior_signatures'];need(type(prior) is list and len(prior)==1 and type(prior[0]) is str,'OWNER_PREVIOUS_SIGNATURE')
        role,previous=prior[0].split(' ')
        need(role=='FABLE' and is_sha(previous),'OWNER_PREVIOUS_SIGNATURE')
        if 'supersedes_owner_signature_on' in body:need(is_sha(body['supersedes_owner_signature_on']),'OWNER_SUPERSEDES_HASH')
        return {'role':'DUDU','decision':'APPROVED','previous_sha':previous,'document_sha256':body['document_sha256'],
                'owner_evidence':evidence,'legacy_documentary_signature':True}
    except ShadowIntegrityError:raise
    except (ValueError,TypeError,KeyError):raise ShadowIntegrityError('OWNER_SIGNATURE_INVALID') from None



def validate_owner_answer(answer,*,act):
    """Exact phrases tied to the explicit A/B document label, never an inferred scope."""
    need(act in {'A','B'},'OWNER_ACT_KIND')
    pattern = r'assino(?: a ordem| a rev[0-9]+)?[.!]?' if act=='A' else r'assino(?: o ato b| o adendo)?[.!]?'
    need(type(answer) is str and re.fullmatch(
        pattern,
        answer,flags=re.IGNORECASE|re.ASCII) is not None,'OWNER_ANSWER_NOT_MAPPED')
