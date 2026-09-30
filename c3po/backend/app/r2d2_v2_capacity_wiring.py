"""Offline documentary-authority wiring; real format and Act B remain UNBOUND."""
from datetime import date
from pathlib import Path
from .r2d2_v2_epoch_assembler import canonical,digest,validate_go
from .r2d2_v2_capacity_anchored import AnchoredRoot,need
from .r2d2_v2_document_authority import DocumentAuthority
from .r2d2_v2_capacity_bound import DailyCapacityBinding,CapacityBoundCollector,AdmissionDeferred,derive_document
from .r2d2_v2_store import utc


class CapacityLoader:
    def __init__(self,*,root,go_root,release,calendar,authority,clock,binding_reader):
        self.root=root;self.go_root=go_root;self.release=release;self.calendar=calendar
        self.authority=authority;self.clock=clock;self.binding_reader=binding_reader

    def __call__(self,day):
        persisted=self.binding_reader(day)
        need(persisted is not None,'CAPACITY_COMMITTED_BINDING_REQUIRED')
        return DailyCapacityBinding.restore(persisted,release=self.release,calendar=self.calendar,
            authority_verifier=lambda doc:self.authority.verify_binding(doc,self.clock()))

    def derive(self,day,state,causal=None):
        # This method is invoked only by the collector/store transition. No external
        # state snapshot or payload age must race the transaction's live state.
        need(type(day) is str and date.fromisoformat(day).isoformat()==day,'WIRING_DAY')
        payload=self.root.json('session='+day+'.json')
        need(set(payload)=={'contract','causal'},'CAPACITY_INPUT_FIELDS')
        c=payload['contract'];source=payload['causal'];now=self.clock()
        self.authority.current(now)
        act=self.authority.act_b(now,epoch=self.release.epoch,first=self.release.first_session.isoformat(),day=day)
        need(act.get('rollback_disposition')=='REVALIDATE_UNCOMMITTED_ONLY','ROLLBACK_DISPOSITION_UNBOUND')
        go=self.go_root.json('session='+day+'.admission.json')['go'];proposal=c['assembler_plan']
        need(utc(go['not_before'])<=self.calendar.details(date.fromisoformat(day))['open'],'ADMISSION_WINDOW_LATE')
        if now<utc(go['not_before']):raise AdmissionDeferred('ADMISSION_NOT_STARTED')
        if causal is not None:
            need(all(causal[k]==source[k] for k in ('symbols','list_sha256','commitment_sha256')),'CAUSAL_TRANSACTION_MISMATCH')
        validate_go(go,proposal,now=now,authority_verifier=lambda g,p:self.authority.verify_go(g,p,self.clock()))
        # _LazyPortfolio exposes its live ledger as MappingProxyType; snapshot that
        # read-only view without changing or finishing the surrounding transaction.
        snapshot={**state,'ledger':dict(state['ledger'])}
        saved={'state':snapshot,'state_sha':digest(snapshot)}
        doc=derive_document(release=self.release,day=day,causal=source,saved=saved,observed_at=now,
            capacity=550,rule_sha=digest(c['template']),contract=c,calendar=self.calendar)
        result=DailyCapacityBinding(doc,release=self.release,causal=source,saved=saved,now=now,
            maximum_age_seconds=1,authority_verifier=lambda d:self.authority.verify_binding(d,self.clock()),
            contract=c,calendar=self.calendar)
        self.root.verify();self.go_root.verify()
        validate_go(go,proposal,now=self.clock(),authority_verifier=lambda g,p:self.authority.verify_go(g,p,self.clock()))
        after=self.clock();need(now<=after and utc(go['not_before'])<=after<utc(go['not_after']),'GO_WINDOW_AFTER_AUTHORITY')
        return result


def prepare_capacity_day(store,collector,day):
    """Explicit authorized pre-open transaction, no session-open side effect."""
    now=collector.clock()
    def transition(state):
        existing=state.get('daily_capacity',{}).get(day)
        if existing is not None:
            DailyCapacityBinding.restore(existing,release=collector.release,calendar=collector.calendar,
                authority_verifier=collector.capacity_authority_verifier)
            return state,[],{'status':'ALREADY_COMMITTED','sha':existing['sha']}
        binding=collector.capacity_loader.derive(day,state)
        state.setdefault('daily_capacity',{})[day]={'sha':binding.sha,'document':binding.document}
        return state,[{'journal_key':'capacity-prepared:'+day,'type':'CAPACITY_DAY_PREPARED','session':day,
            'plan_sha':binding.sha,'at':now.isoformat(),'a1_cut_count':len(binding.document['cut_symbols']),'payload':binding.document}],{'status':'COMMITTED','sha':binding.sha}
    return store.atomic(collector.release.epoch,collector._initial(),transition,now)


class ConsumerEntrypoints:
    def __init__(self,*,loader,authority,attempt_root,attempt_identity,clock,calendar):
        need(attempt_identity is not None,'ATTEMPT_IDENTITY_UNBOUND')
        self.loader=loader;self.authority=authority;self.attempts=AnchoredRoot(attempt_root,expected_identity=attempt_identity)
        self.clock=clock;self.calendar=calendar

    def gate(self,go,proposal):
        self.attempts.verify();now=self.clock()
        result=validate_go(go,proposal,now=now,authority_verifier=lambda g,p:self.authority.verify_go(g,p,self.clock()))
        self.attempts.verify()
        after=self.clock()
        need(now<=after and utc(go['not_before'])<=after<utc(go['not_after']),'GO_WINDOW_AFTER_AUTHORITY')
        return result

    def _admit(self,phase,day,go):
        binding=self.loader(day)
        p=binding.document['contract'];proposal=p['assembler_plan'] if phase=='admission' else p['consumer_plans'][phase]
        receipt=self.gate(go,proposal)
        self.attempts.reserve(receipt['attempt_key']+'.json',canonical({'go_sha':digest(go),'phase':phase,'day':day}))
        self.gate(go,proposal)  # fsync/read/rename cannot extend authority.
        return binding,proposal

    def bar(self,*,day,state,owner_uid,go,run_session,producer_arguments):
        b,p=self._admit('bar_manifest',day,go)
        manifest=b.bar_manifest(owner_uid=owner_uid,state=state,current_day=day,now=self.clock(),calendar=self.calendar)
        need('manifest' not in producer_arguments,'WIRING_MANIFEST_OVERRIDE')
        self.gate(go,p)
        return run_session(manifest=manifest,**producer_arguments)

    async def quote_capture(self,*,day,state,go,root,components,ticks,sleep):
        b,p=self._admit('quote_capture',day,go)
        self.gate(go,p)
        return await b.quote_capture(root=root,state=state,current_day=day,calendar=self.calendar,
            components=components,ticks=ticks,clock=self.clock,sleep=sleep)



def build_capacity_collector(*,store,source,release,calendar,config):
    needed={'payload_root','go_root','authority','clock','binding_reader','epoch'}
    need(type(config) is dict and set(config)==needed and config['epoch']==release.epoch,'WIRING_CONFIG_FIELDS')
    need(isinstance(config['authority'],DocumentAuthority),'DOCUMENT_AUTHORITY_REQUIRED')
    loader=CapacityLoader(root=AnchoredRoot(config['payload_root']),go_root=AnchoredRoot(config['go_root']),release=release,
        calendar=calendar,authority=config['authority'],clock=config['clock'],binding_reader=config['binding_reader'])
    return CapacityBoundCollector(store,source,release,calendar=calendar,clock=config['clock'],capacity_loader=loader,
        capacity_authority_verifier=lambda doc:config['authority'].verify_binding(doc,config['clock']()))


def controller_planner(*,calendar,authority):
    """Pass into the existing worker's sole LiveGroupController at activation."""
    from .r2d2_v2_capacity_live import capacity_live_plan
    return lambda saved,release,policy,now:capacity_live_plan(saved,release,policy,now,calendar=calendar,authority=authority)


def bootstrap_capacity_planner(settings):
    """__main__ seam; no context means UNBOUND, never silently open-only."""
    context=getattr(settings,'r2d2_v2_capacity_context',None)
    need(type(context) is dict and set(context)=={'calendar','authority'},'CAPACITY_BOOTSTRAP_UNBOUND')
    need(isinstance(context['authority'],DocumentAuthority),'DOCUMENT_AUTHORITY_REQUIRED')
    return controller_planner(calendar=context['calendar'],authority=context['authority'])
