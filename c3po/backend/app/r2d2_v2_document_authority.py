"""Pinned documentary evidence; restoration does not renew a GO or its veto view."""
import hashlib
from datetime import date,timedelta
from typing import Any,Callable,cast
from .r2d2_v2_epoch_assembler import DELEGABLE,DOCUMENT_ORDER_SHA,digest,stamp,is_sha
from .r2d2_v2_store import ShadowIntegrityError,digest as store_digest
from .r2d2_v2_document_format import normalize_document,act_b_template_shas


def need(ok,code):
    if not ok:raise ShadowIntegrityError(code)


def one_digest_namespace(value,code):
    # The store digest escapes everything outside printable ASCII (DEL included) and the
    # assembler digest does not; the contract and GO layers compare one against the other.
    try:same=store_digest(value)==digest(value)
    except UnicodeError:same=False
    need(same,code)


def scope(record,epoch,first,day):
    need(record['epoch']==epoch and record['first_session']==first,'DOCUMENT_EPOCH_SCOPE')
    days=record['authorized_sessions']
    need(type(days) is list and days and days==sorted(set(days)) and first<=days[0]
         and all(type(d) is str and date.fromisoformat(d).isoformat()==d for d in days)
         and day in days,'DOCUMENT_SESSION_SCOPE')


class DocumentAuthority:
    def __init__(self,*,root,pins,normalizer=normalize_document,revocation_reader=None,restore_revocation_reader=None):
        self.root=root;self.pins=pins;self.normalizer=normalizer
        self.revocation_reader=revocation_reader;self.restore_revocation_reader=restore_revocation_reader

    def record(self,label):
        need(callable(self.normalizer),'DOCUMENT_FORMAT_UNBOUND')
        pin=self.pins[label];raw=self.root.read(pin['file'])
        need(hashlib.sha256(raw).hexdigest()==pin['sha256'],'DOCUMENT_HASH_MISMATCH')
        return self.normalizer(label,raw)

    def check_view(self,status,now):
        need(status['status']=='VERIFIED' and stamp(status['observed_at'])<=now<stamp(status['valid_until'])
             and (now-stamp(status['observed_at'])).total_seconds()<=10,'REVOCATION_STALE')
        hashes={p['sha256'] for p in self.pins.values()}
        need(not hashes.intersection(status['revoked_shas']) and status['owner_veto'] is False,'AUTHORITY_REVOKED_OR_VETOED')

    def current(self,now):
        need(callable(self.revocation_reader),'REVOCATION_UNBOUND')
        self.check_view(cast(Callable[...,Any],self.revocation_reader)(now),now)

    def check_restore_revocation(self,now):
        # Optional renewable evidence is distinct from the one GO dispatch snapshot.
        # Failure here only causes a controller fallback for this tick; no sticky admission flag.
        if self.restore_revocation_reader is not None:
            status=self.restore_revocation_reader(now)
            self.check_view(status,now)
            return status
        return None

    def chain(self,now,*,act=None,epoch=None,first=None,day=None):
        act=self.record('ACT_B') if act is None else act
        epoch=act['epoch'] if epoch is None else epoch
        first=act['first_session'] if first is None else first
        day=first if day is None else day
        previous=None
        mapping=act['act_a_scope_map']
        need(type(mapping) is dict and set(mapping)=={'CODEX','FABLE','DUDU'},'ACT_A_MAP')
        for role in ('CODEX','FABLE','DUDU'):
            record=self.record(role);mapped: Any=mapping[role]
            need(set(mapped)=={'signature_sha','document_sha256','epoch','first_session','authorized_sessions'},'ACT_A_MAP_FIELDS')
            need(mapped['signature_sha']==self.pins[role]['sha256'] and mapped['document_sha256']==act['document_order_sha'],'ACT_A_MAP_HASH')
            scope(mapped,epoch,first,day)
            need(record['role']==role and record['decision']=='APPROVED' and record['previous_sha']==previous
                 and record['document_sha256']==act['document_order_sha'],'DOCUMENT_CHAIN')
            if not record.get('legacy_documentary_signature',False):scope(record,epoch,first,day)
            previous=self.pins[role]['sha256']
        return self.record('DUDU')

    def act_b(self,now,*,epoch=None,first=None,day=None):
        body=self.record('ACT_B');epoch=body['epoch'] if epoch is None else epoch
        first=body['first_session'] if first is None else first;day=first if day is None else day
        scope(body,epoch,first,day)
        self.chain(now,act=body,epoch=epoch,first=first,day=day);previous=None
        for role in ('CODEX','FABLE','DUDU'):
            label='B_'+role;record=self.record(label)
            scope(record,epoch,first,day)
            need(record['role']==role and record['decision']=='APPROVED' and record['previous_sha']==previous
                 and record['body_sha']==self.pins['ACT_B']['sha256']
                 and record['act_a_head']==self.pins['DUDU']['sha256'],'ACT_B_DOCUMENT_CHAIN')
            previous=self.pins[label]['sha256']
        need(body['chain_head']==self.pins['DUDU']['sha256'] and body['status']=='ACCEPTED','ACT_B_SCOPE')
        need(body['document_order_sha']==DOCUMENT_ORDER_SHA and is_sha(body['order_sha']),'ACT_A_ORDER_MAP')
        need(type(body['templates']) is list and body['templates'] and digest(body['templates'])==body['template_set_sha'],'TEMPLATE_SET_HASH')
        for template in body['templates']:
            need(set(template)=={'sha','epoch','first_session','authorized_sessions','phases'} and is_sha(template['sha']),'TEMPLATE_SET_ENTRY')
            need(template['epoch']==epoch and template['first_session']==first and type(template['phases']) is list
                 and template['phases'] and len(template['phases'])==len(set(template['phases'])),'TEMPLATE_SET_SCOPE')
            need(set(template['authorized_sessions'])<=set(body['authorized_sessions']),'TEMPLATE_SET_DAYS')
        by_day=act_b_template_shas(body)
        if 'template_shas' in body:
            # Day-exclusive: a mapped digest may only belong to entries scoped to that one session.
            for d,sha in by_day.items():
                entries=[t for t in body['templates'] if t['sha']==sha]
                need(entries and all(t['authorized_sessions']==[d] for t in entries),'TEMPLATE_MAP_SET')
        return body

    def check_binding(self,document,now):
        c=document['contract'];identity=c['assembler_plan']['proposal']['identity']
        one_digest_namespace(c['template'],'DOCUMENT_BINDING_DIGEST_NAMESPACE');one_digest_namespace(c['order'],'DOCUMENT_BINDING_DIGEST_NAMESPACE')
        act=self.act_b(now,epoch=document['epoch'],first=identity['first_session'],day=document['day'])
        need(c['template']['day']==document['day'],'DOCUMENT_TEMPLATE_DAY')
        template_sha=act_b_template_shas(act)[document['day']]
        need(act['order_sha']==digest(c['order']) and template_sha==digest(c['template']) and act['policy_sha']==digest(c['policy']),'DOCUMENT_BINDING')
        need(act['capacity']==550 and act['cut_rule']==c['template']['rule'],'DOCUMENT_CAPACITY_RULE')

    def verify_binding(self,document,now):
        try:
            self.check_binding(document,now)
            return True
        except Exception:return False

    def verify_go(self,go,proposal,now):
        try:
            epoch,first,day=go['epoch'],go['first_session'],go['day']
            act=self.act_b(now,epoch=epoch,first=first,day=day)
            identity=proposal['proposal']['identity']
            scope(identity,epoch,first,day)
            need(go['signed_order_sha']==act['order_sha'],'DOCUMENT_GO_ORDER')
            template=self.record('TEMPLATE');record=self.record('GO:'+go['phase'])
            need(template in act['templates'],'DOCUMENT_TEMPLATE_MEMBERSHIP')
            need(template['epoch']==epoch and template['first_session']==first and day in template['authorized_sessions']
                 and go['phase'] in template['phases'],'DOCUMENT_TEMPLATE_SCOPE')
            need(record['epoch']==epoch and record['first_session']==first and record['day']==day and record['phase']==go['phase'],'DOCUMENT_GO_SCOPE')
            need(record['go_sha']==digest(go) and record['template_sha']==go['template_sha']
                 and template['sha']==go['template_sha'] and record['decision']=='GO','DOCUMENT_GO_BINDING')
            if go['mode']=='DELEGATED_ACT_B':
                need(go['phase'] in DELEGABLE and record['role']=='FABLE','DOCUMENT_GO_SCOPE')
                publication=self.record('PUBLICATION:'+go['phase'])
                need(go['authority_receipts']['signed_act_b_sha']==self.pins['ACT_B']['sha256'] and
                     go['authority_receipts']['publication_receipt_sha']==self.pins['PUBLICATION:'+go['phase']]['sha256'], 'DOCUMENT_GO_RECEIPT_HASH')
                need(publication['epoch']==epoch and publication['first_session']==first and publication['role']=='FABLE'
                     and publication['template_sha']==go['template_sha'] and publication['phase']==go['phase'] and publication['day']==day
                     and publication['published_at']==record['published_at']==go['authority_receipts']['published_at'],'DOCUMENT_PUBLICATION_SCOPE')
                need(stamp(record['published_at'])<=stamp(go['not_before'])-timedelta(minutes=15),'DOCUMENT_GO_NOTICE')
            else:
                need(record['role'] in act['individual_go_issuers'],'INDIVIDUAL_ISSUER_UNBOUND')
                if go['phase'] in act['owner_countersign_phases']:
                    owner=self.record('OWNER_GO:'+go['phase'])
                    need(owner['epoch']==epoch and owner['first_session']==first and owner['day']==day and owner['phase']==go['phase']
                         and owner['template_sha']==go['template_sha'] and owner['role']=='DUDU'
                         and owner['decision']=='GO' and owner['go_sha']==digest(go),'OWNER_ACT_REQUIRED')
            self.current(now)
            return True
        except Exception:return False
