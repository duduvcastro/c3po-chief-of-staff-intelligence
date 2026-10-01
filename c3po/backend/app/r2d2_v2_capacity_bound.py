"""OFFLINE CANDIDATE: executable daily capacity consumers, not factory-wired.

Requires an independent verified order/plan binding. This module does not sign,
issue GO, fetch a ledger, or authorize a socket. Existing runtime is unchanged.
"""
from copy import deepcopy
from datetime import date
from typing import Any
from .r2d2_v2_calendar import NEW_YORK
from .r2d2_v2_capacity_authority import validate_contract, calendar_pin
import re
from functools import wraps
from .r2d2_v2_shadow import ShadowCollector
from .r2d2_v2_store import ShadowIntegrityError, digest, utc


def need(condition, code):
    if not condition: raise ShadowIntegrityError(code)



def safe_input(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        try:return function(*args,**kwargs)
        except ShadowIntegrityError:raise
        except (ValueError,TypeError,KeyError,AttributeError):
            raise ShadowIntegrityError('CAPACITY_INPUT_INVALID') from None
    return wrapped

def open_symbols(state):
    symbols=set()
    for book in ('portfolio','research'):
        records=state.get('ledger',{}).get(book)
        need(isinstance(records,dict),'CAPACITY_LEDGER_BOOK')
        for row in records.values():
            if row.get('status')=='OPEN':
                key=row.get('instrument_key','')
                need(isinstance(key,str) and key.startswith('US:') and len(key)>3,'CAPACITY_OPEN_INSTRUMENT')
                symbols.add(key[3:])
    return symbols


@safe_input
def derive_document(*, release, day, causal, saved, observed_at, capacity, rule_sha, contract, calendar):
    contract=validate_contract(contract,release=release,day=day,causal=causal,calendar=calendar)
    need(capacity==550 and type(capacity) is int,'CAPACITY_LIMIT')
    need(rule_sha==digest(contract['template']),'CAPACITY_RULE_HASH')
    need(type(capacity) is int and 1<=capacity<=550,'CAPACITY_LIMIT')
    state=saved['state'];need(digest(state)==saved['state_sha'],'CAPACITY_LEDGER_HASH')
    need(state['epoch']==release.epoch and state['release_sha']==release.receipt_sha,'CAPACITY_RELEASE')
    names=causal['symbols']
    need(type(names) is list and all(isinstance(n,str) and re.fullmatch('[A-Z0-9][A-Z0-9.-]{0,19}',n) for n in names),'CAPACITY_SYMBOLS')
    need(causal.get('status')=='AVAILABLE' and type(names) is list and len(names)==len(set(names)),'CAPACITY_CAUSAL')
    opened=open_symbols(state);need(len(opened)<=capacity,'CAPACITY_OPEN_ONLY_OVERFLOW')
    candidates=[name for name in names if name not in opened]
    admitted=candidates[:capacity-len(opened)];cut=candidates[len(admitted):]
    return {'schema':'V2_DAILY_CAPACITY_BINDING_CANDIDATE_V1','epoch':release.epoch,'release_sha':release.receipt_sha,
            'contract':contract,'causal':deepcopy(causal),'day':day,'causal_commitment_sha':causal['commitment_sha256'],'causal_list_sha':causal['list_sha256'],
            'ledger_state_sha':saved['state_sha'],'observed_at':utc(observed_at).isoformat(),'capacity':capacity,
            'rule_sha':rule_sha,'open_symbols':sorted(opened),'monitored_symbols':sorted(opened|set(admitted)),
            'cut_symbols':cut,'admission_symbols':[name for name in names if name not in set(cut)]}



DOCUMENT_FIELDS=frozenset(('schema','epoch','release_sha','contract','causal','day','causal_commitment_sha',
    'causal_list_sha','ledger_state_sha','observed_at','capacity','rule_sha','open_symbols','monitored_symbols',
    'cut_symbols','admission_symbols'))


@safe_input
def validate_document(document: Any):
    from .r2d2_v2_epoch_assembler import is_sha
    p: dict[str,Any]=document
    need(type(p) is dict and set(p)==DOCUMENT_FIELDS,'CAPACITY_DOCUMENT_FIELDS')
    need(p['schema']=='V2_DAILY_CAPACITY_BINDING_CANDIDATE_V1','CAPACITY_DOCUMENT_SCHEMA')
    need(all(is_sha(p[k]) for k in ('release_sha','causal_commitment_sha','causal_list_sha','ledger_state_sha','rule_sha')),'CAPACITY_DOCUMENT_SHA')
    need(type(p['capacity']) is int and p['capacity']==550,'CAPACITY_DOCUMENT_LIMIT')
    for key in ('open_symbols','monitored_symbols','cut_symbols','admission_symbols'):
        names=p[key]
        need(type(names) is list and all(isinstance(n,str) and re.fullmatch('[A-Z0-9][A-Z0-9.-]{0,19}',n) for n in names)
             and len(names)==len(set(names)),'CAPACITY_DOCUMENT_SYMBOLS')
    names=p['causal']['symbols'];opened=p['open_symbols'];capacity=p['capacity']
    need(opened==sorted(opened) and len(opened)<=capacity,'CAPACITY_DOCUMENT_OPENS')
    need(type(names) is list and all(isinstance(n,str) for n in names) and len(names)==len(set(names)),'CAPACITY_DOCUMENT_CAUSAL')
    candidates=[n for n in names if n not in set(opened)]
    admitted=candidates[:capacity-len(opened)];cut=candidates[len(admitted):]
    need(p['cut_symbols']==cut and p['monitored_symbols']==sorted(set(opened)|set(admitted)) and
         p['admission_symbols']==[n for n in names if n not in set(cut)],'CAPACITY_DOCUMENT_DERIVED')
    proposal=p['contract']['assembler_plan']['proposal'];causal=p['causal']
    need(p['epoch']==proposal['identity']['epoch']==causal['epoch'] and p['day']==proposal['daily']['day']==causal['session']
         and p['release_sha']==proposal['bindings']['release_sha'],'CAPACITY_DOCUMENT_SCOPE')
    need(p['causal_commitment_sha']==causal['commitment_sha256'] and p['causal_list_sha']==causal['list_sha256']==digest(names)
         and p['rule_sha']==digest(p['contract']['template']),'CAPACITY_DOCUMENT_BINDINGS')
    need(p['observed_at']==utc(p['observed_at']).isoformat(),'CAPACITY_DOCUMENT_CLOCK')
    return p

class DailyCapacityBinding:
    @safe_input
    def __init__(self, document, *, release, causal, saved, now, maximum_age_seconds, authority_verifier, contract, calendar):
        need(callable(authority_verifier),'CAPACITY_AUTHORITY_UNBOUND')
        need(type(maximum_age_seconds) is int and maximum_age_seconds>0,'CAPACITY_FRESHNESS_UNBOUND')
        need(0<=(utc(now)-utc(document['observed_at'])).total_seconds()<=maximum_age_seconds,'CAPACITY_LEDGER_STALE')
        expected=derive_document(release=release,day=document['day'],causal=causal,saved=saved,
            observed_at=document['observed_at'],capacity=document['capacity'],rule_sha=document['rule_sha'],contract=contract,calendar=calendar)
        need(document==expected,'CAPACITY_PLAN_MISMATCH')
        need(authority_verifier(document) is True,'CAPACITY_AUTHORITY_UNVERIFIED')
        self.document=deepcopy(document);self.sha=digest(document)
        self.calendar=calendar

    @classmethod
    def restore(cls, persisted, *, release, calendar, authority_verifier):
        """Reattach evidence already committed atomically; never refresh/rederive it."""
        try:
            need(type(persisted) is dict and set(persisted)=={'sha','document'},'CAPACITY_RESTORE_FIELDS')
            doc: Any=deepcopy(persisted['document'])
            need(digest(doc)==persisted['sha'],'CAPACITY_RESTORE_HASH')
            validate_document(doc)
            validate_contract(doc['contract'],release=release,day=doc['day'],causal=doc['causal'],calendar=calendar)
            need(callable(authority_verifier) and authority_verifier(doc) is True,'CAPACITY_AUTHORITY_UNVERIFIED')
            obj=cls.__new__(cls);obj.document=doc;obj.sha=persisted['sha'];obj.calendar=calendar
            obj.verify()
            return obj
        except ShadowIntegrityError:raise
        except (ValueError,TypeError,KeyError,AttributeError):
            raise ShadowIntegrityError('CAPACITY_RESTORE_INVALID') from None

    @safe_input
    def verify(self, *, state=None, day=None, causal=None):
        p=self.document
        need(digest(p)==self.sha,'CAPACITY_PLAN_CHANGED')
        validate_document(p)
        need(calendar_pin(self.calendar,p['contract']['assembler_plan']['proposal']['identity'])==p['contract']['assembler_plan']['proposal']['bindings']['calendar_pin_sha'],'CAPACITY_CALENDAR_PIN')
        if day is not None:need(day==p['day'],'CAPACITY_DAY')
        if state is not None:
            need(state['epoch']==p['epoch'] and state['release_sha']==p['release_sha'],'CAPACITY_RELEASE')
            need(open_symbols(state)<=set(p['monitored_symbols']),'CAPACITY_UNCOVERED_OPEN')
        if causal is not None:
            need(causal['commitment_sha256']==p['causal_commitment_sha'] and causal['list_sha256']==p['causal_list_sha'],'CAPACITY_CAUSAL_CHANGED')
        return deepcopy(p)

    @safe_input
    def current_session(self, *, state, current_day, now, calendar):
        p=self.verify(state=state,day=current_day)
        need(calendar_pin(calendar,p['contract']['assembler_plan']['proposal']['identity'])==p['contract']['assembler_plan']['proposal']['bindings']['calendar_pin_sha'],'CAPACITY_CALENDAR_PIN')
        try:day=date.fromisoformat(current_day)
        except (ValueError,TypeError):raise ShadowIntegrityError('CAPACITY_CURRENT_DAY_INVALID') from None
        need(day.isoformat()==current_day and calendar.is_session(day),'CAPACITY_CURRENT_CALENDAR')
        at=utc(now)
        need(at.astimezone(NEW_YORK).date()==day,'CAPACITY_CURRENT_DAY')
        last=state.get('last_session')
        need(last is None or date.fromisoformat(last)<=day,'CAPACITY_STATE_SESSION_AHEAD')
        cycle=state.get('last_cycle_at')
        need(cycle is None or (utc(cycle)<=at and utc(cycle).astimezone(NEW_YORK).date()<=day),
             'CAPACITY_STATE_CLOCK_AHEAD')
        return p

    def bar_manifest(self, *, owner_uid, state, current_day, now, calendar):
        p=self.current_session(state=state,current_day=current_day,now=now,calendar=calendar)
        return {'epoch':p['epoch'],'session':p['day'],'symbols':p['monitored_symbols'],'owner_uid':owner_uid}

    def quote_refresh(self, stream, *, state, ttl, stop_event, current_day, now, calendar):
        p=self.current_session(state=state,current_day=current_day,now=now,calendar=calendar)
        # Check the actual stream's complete V1/V2 reservation under the same lock.
        # An over-capacity proposal must not call set_v2_group, which drops V2.
        try:
            with stream._lock:
                others={s for name,(_,_,names) in stream._groups.items() if name!='r2d2-v2-live' for s in names}
                need(len(others|set(p['monitored_symbols']))<=min(550,stream.max_symbols),'CAPACITY_SHARED_QUOTA')
                return stream.set_v2_group(p['monitored_symbols'],capacity=550,ttl=ttl,stop_event=stop_event)
        except ShadowIntegrityError:raise
        except ValueError:
            raise ShadowIntegrityError('CAPACITY_QUOTE_REFUSED') from None

    async def quote_capture(self, *, root, state, components, ticks, clock, sleep, current_day, calendar):
        from .r2d2_v2_producer_snapshot import run_capture
        p=self.current_session(state=state,current_day=current_day,now=clock(),calendar=calendar)
        return await run_capture(root=root,epoch=p['epoch'],session_date=date.fromisoformat(p['day']),
            symbols=p['monitored_symbols'],components=components,ticks=ticks,clock=clock,sleep=sleep)


class AdmissionDeferred(ShadowIntegrityError):
    pass


class CapacityBoundCollector(ShadowCollector):
    """Candidate factory must provide one verified immutable binding per DAY."""
    def __init__(self,*args,capacity_loader,capacity_authority_verifier=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.capacity_loader=capacity_loader
        self.capacity_authority_verifier=capacity_authority_verifier

    def _capacity(self,state,journals,session,now,causal=None):
        if session.get('capacity_admission_blocked'):return None
        try:
            prior=session.get('capacity_binding') or state.get('daily_capacity',{}).get(session['date'])
            if prior is not None:
                binding=DailyCapacityBinding.restore(prior,release=self.release,calendar=self.calendar,
                    authority_verifier=self.capacity_authority_verifier)
                # Persisted identity is authoritative. No loader or original freshness
                # test is replayed; changed external authority must fail its verifier.
            else:
                binding=(self.capacity_loader.derive(session['date'],state,causal) if callable(getattr(self.capacity_loader,'derive',None))
                         else self.capacity_loader(session['date']))
            need(isinstance(binding,DailyCapacityBinding),'CAPACITY_BINDING_MISSING')
            p=binding.verify(state=state,day=session['date'],causal=causal)
            if prior is not None and session.get('capacity_binding') is None:
                session['capacity_binding']=deepcopy(prior)
                session['capacity_cut_count']=len(p['cut_symbols'])
            if prior is None:
                session['capacity_binding']={'sha':binding.sha,'document':p}
                session['capacity_cut_count']=len(p['cut_symbols'])
                journals.append({'journal_key':'capacity:'+session['date'],'type':'CAPACITY_CUT_RECEIPT',
                    'session':session['date'],'at':utc(now).isoformat(),'plan_sha':binding.sha,'payload':p,
                    'a1_cut_count':len(p['cut_symbols'])})
            return p
        except AdmissionDeferred:
            return None
        except Exception:
            # Admission failure cannot unwind open-position events in store.atomic.
            code='CAPACITY_ADMISSION_UNAVAILABLE'
            if not session.get('capacity_admission_blocked'):
                session['capacity_admission_blocked']=code
                journals.append({'journal_key':'capacity-block:'+session['date'],'type':'CAPACITY_ADMISSION_BLOCKED',
                    'session':session['date'],'at':utc(now).isoformat(),'reason':code,'open_monitoring_continues':True})
            return None

    def _capture(self,state,journals,session,batch,now,*,portfolio=None,causal=None):
        if causal is None or causal.get('status')!='AVAILABLE':
            return super()._capture(state,journals,session,batch,now,portfolio=portfolio,causal=causal)
        p=self._capacity(state,journals,session,now,causal)
        if p is None:return
        filtered=deepcopy(batch)
        if isinstance(filtered.get('universe'),dict):
            filtered['universe']['instruments']=[row for row in filtered['universe'].get('instruments',[])
                if row.get('symbol') in p['admission_symbols']]
        # Causal commitment is passed unchanged; cuts are separate persistent evidence.
        return super()._capture(state,journals,session,filtered,now,portfolio=portfolio,causal=causal)

    def _entries(self,state,journals,session,batch,events,now,**kwargs):
        p=self._capacity(state,journals,session,now)
        pending=session.get('entries_pending',{})
        if p is None:
            # Terminalize pending admission so base causal barriers cannot withhold
            # later events belonging to existing positions.
            for instrument,entry in list(pending.items()):
                journals.append({'journal_key':'capacity-entry-block:'+session['date']+':'+instrument,
                    'type':'CAPACITY_ENTRY_REFUSED','session':session['date'],'instrument_key':instrument,
                    'at':utc(now).isoformat(),'reason':'CAPACITY_ADMISSION_UNAVAILABLE'})
                if instrument in session['candidates']:
                    session['candidates'][instrument].update(entry_status='REJECTED',entry_reason='CAPACITY_ADMISSION_UNAVAILABLE')
                del pending[instrument]
            return
        for instrument in list(pending):
            if instrument.removeprefix('US:') not in p['admission_symbols']:
                entry=pending.pop(instrument)
                journals.append({'journal_key':'capacity-entry-cut:'+session['date']+':'+instrument,
                    'type':'CAPACITY_ENTRY_REFUSED','session':session['date'],'instrument_key':instrument,
                    'at':utc(now).isoformat(),'reason':'DAILY_CAPACITY_CUT','plan_sha':session['capacity_binding']['sha'],
                    'entry_at':entry.get('entry_at')})
        return super()._entries(state,journals,session,batch,events,now,**kwargs)

    def _close_capture(self,state,journals,session: Any,now):
        # Keep the causal universe intact. Give deliberate exclusions their own
        # terminal evidence so the base closure only diagnoses actual missing data.
        p=None
        if session.get('capacity_binding') is not None:
            try:
                persisted: dict[str,Any]=session['capacity_binding']
                need(type(persisted) is dict and set(persisted)=={'sha','document'},'CAPACITY_CLOSURE_FIELDS')
                document: dict[str,Any]=persisted['document']
                need(type(document) is dict and isinstance(persisted['sha'],str) and
                     re.fullmatch('[0-9a-f]{64}',persisted['sha']) is not None and
                     digest(document)==persisted['sha'],'CAPACITY_CLOSURE_HASH')
                cuts=document['cut_symbols']
                need(type(cuts) is list and all(isinstance(n,str) and re.fullmatch('[A-Z0-9][A-Z0-9.-]{0,19}',n) for n in cuts)
                     and len(cuts)==len(set(cuts)),'CAPACITY_CLOSURE_CUTS')
                need(document['day']==session['date'] and document['epoch']==state['epoch'] and
                     set(cuts)<=set(document['causal']['symbols']),'CAPACITY_CLOSURE_SCOPE')
                p=document
            except Exception:
                # Corrupt optional admission evidence must not unwind open events.
                if not session.get('capacity_closure_unavailable'):
                    session['capacity_closure_unavailable']=True
                    journals.append({'journal_key':'capacity-close-unavailable:'+session['date'],
                        'type':'CAPACITY_CLOSURE_BINDING_UNAVAILABLE','session':session['date'],
                        'reason':'CAPACITY_BINDING_INVALID','at':utc(now).isoformat()})
        for symbol in p['cut_symbols'] if p is not None else []:
            name='US:'+symbol
            if name not in (session.get('universe') or []) or name in session['candidates']:
                continue
            evaluation={'status':'CAPACITY_EXCLUDED','arm':None,'reasons':['DAILY_CAPACITY_CUT']}
            session['candidates'][name]=evaluation
            session.get('pending',{}).pop(name,None)
            journals.append({'journal_key':'candidate-capacity-cut:'+session['date']+':'+name,
                'type':'CANDIDATE_CAPACITY_CUT','session':session['date'],'instrument_key':name,
                'plan_sha':session['capacity_binding']['sha'],'evaluation':evaluation})
        return super()._close_capture(state,journals,session,now)


def capacity_measurement(state, day):
    """Post-session A1 input counts only; never an admission gate or A1 verdict."""
    session=state.get('sessions',{}).get(day,{})
    persisted=session.get('capacity_binding')
    if persisted is None or digest(persisted.get('document'))!=persisted.get('sha'):
        return {'session':day,'status':'INCONCLUSIVE','cut_count':None}
    return {'session':day,'status':'INCONCLUSIVE' if session.get('capacity_admission_blocked') else 'MEASURED',
            'cut_count':len(persisted['document']['cut_symbols']),'plan_sha':persisted['sha']}
