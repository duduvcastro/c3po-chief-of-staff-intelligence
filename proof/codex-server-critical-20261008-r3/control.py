"""F6 V2: actual family dispatch, durable invocation before effects, no retry.

Runtime, elected slots and registry are supplied by a root-controlled service
acceptance, independently reviewed before installation. Request bytes cannot
choose an executable, host, SQL statement, registry, epoch or new attempt key.
"""
import time
from datetime import timedelta, timezone
from common import Hold, canonical, context, digest, instant, need, sha, strict

BRT=timezone(timedelta(hours=-3))
OPERATIONS={'F3_CAPACITY_PREPARE','F3_CAPACITY_VERIFY','F4_K12_LAUNCH','F4_K12_PERSIST',
            'F4_K12_STOP','F4_K12_COLLECT','F5_H16_READ'}
PUBLIC={'COMPLETE','COMPLETE_FIXTURE','HOLD_CONSUMED','HOLD_AUTHORITY','HOLD_OWNER',
        'HOLD_GATES','HOLD_WINDOW','HOLD_CLOCK','HOLD_RUNTIME','HOLD_ADAPTER_UNAVAILABLE',
        'HOLD_RESULT','HOLD_UNCERTAIN','HOLD_PUBLICATION_UNCERTAIN'}


class Controller:
    def __init__(self,guard,journal,registry,channel,*,clock,monotonic=time.monotonic,retainer=None):
        self.guard,self.journal,self.registry,self.channel=guard,journal,registry,channel
        self.clock,self.monotonic=clock,monotonic
        self.retainer=retainer
        self.election=guard.value['election']
        need(self.election['context']==guard.context and self.election['mode']==guard.mode,'HOLD_AUTHORITY')
        need(set(registry)<=OPERATIONS and set(registry)==set(guard.value['allowed_operations']), 'HOLD_ADAPTER_UNAVAILABLE')

    def _validate(self,slot,originals,gates,view,now,*,admission_UTC=None):
        request,question,owner,bound,authority,review=[originals[k]['value'] for k in
                       ('request','question','owner','bound','authority','review')]
        election=self.election['slots'][slot];ctx=context(request['context']);request_pin=digest(originals['request']['raw'])
        need(request['schema']=='SERVER_FAMILY_REQUEST_V2' and ctx==self.guard.context
             and election['operation']==request['operation'] and request['operation'] in OPERATIONS,'HOLD_AUTHORITY')
        need(request['authority_slot']==slot and digest(originals['authority']['raw'])==sha(election['authority_sha256'])
             and digest(originals['review']['raw'])==sha(election['review_sha256']), 'HOLD_AUTHORITY')
        need(authority['schema']=='SERVER_OPERATION_AUTHORITY_V2' and authority['context']==ctx
             and authority['slot']==slot and authority['request_sha256']==request_pin
             and authority['runtime_measurement_sha256']==self.guard.value['measurement_sha256']
             and authority['registry_sha256']==self.guard.value['registry_sha256']
             and authority['operation']==request['operation'],'HOLD_AUTHORITY')
        need(review['schema']=='SERVER_OPERATION_REVIEW_V2' and review['context']==ctx
             and review['request_sha256']==request_pin and review['verdict']=='ACCEPTED_OWN_BYTES'
             and review['authority_sha256']==election['authority_sha256']
             and review['source_pins']==self.guard.value['source_pins'],'HOLD_AUTHORITY')
        need(question['schema']=='SERVER_OWNER_QUESTION_V2' and question['request_sha256']==request_pin
             and owner['schema']=='SERVER_OWNER_RESPONSE_V2' and owner['request_sha256']==request_pin
             and owner['question_sha256']==digest(originals['question']['raw'])
             and owner['literal']=='Assino' and owner['channel']=='REGISTRO_PELA_FABLE','HOLD_OWNER')
        signed,published=instant(owner['signed_at_UTC']),instant(originals['question']['created_UTC'])
        start,end=instant(request['start_UTC']),instant(request['end_UTC']);local=signed.astimezone(BRT)
        need(published<=signed<start and signed<=instant(election['owner_deadline_UTC'])
             and 7<=local.hour and (local.hour,local.minute,local.second,local.microsecond)<=(21,45,0,0),'HOLD_OWNER')
        registered=instant(originals['owner']['created_UTC'])
        need(signed<=registered and (registered-signed).total_seconds()<=60
             and registered<=instant(originals['bound']['created_UTC'])<start
             and all(instant(originals[role]['created_UTC'])<start for role in originals), 'HOLD_OWNER')
        need(bound['schema']=='SERVER_BOUND_V2' and bound['context']==ctx
             and bound['request_sha256']==request_pin and bound['question_sha256']==digest(originals['question']['raw'])
             and bound['owner_sha256']==digest(originals['owner']['raw'])
             and bound['review_sha256']==election['review_sha256']
             and bound['runtime_measurement_sha256']==self.guard.value['measurement_sha256'],'HOLD_AUTHORITY')
        # The measured runtime is bound before signatures; the full installation
        # acceptance later pins the original authority/review IDs in the unit.
        # No self-referential acceptance/authority digest fixed point is required.
        need(request['pins']==election['pins'] and request['pins']['runtime_measurement_sha256']==self.guard.value['measurement_sha256'],
             'HOLD_AUTHORITY')
        admitted=now if admission_UTC is None else admission_UTC
        # Lateness/full remaining budget concern admission, not every later
        # readback of an already admitted effect. Runtime, veto, gates and the
        # absolute deadline remain current; elapsed budget is checked below.
        need(type(request['budget_seconds']) is int and 0<request['budget_seconds']<=120
             and start<=admitted<=now<end and admitted+timedelta(seconds=request['budget_seconds'])<end
             and (admitted-start).total_seconds()<=election['max_lateness_seconds'],'HOLD_WINDOW')
        need(view['schema']=='SERVER_AUTHORITY_VIEW_V2' and view['context']==ctx and view['veto'] is False
             and view['revoked_shas']==[] and view['concurrent_attempts']==[] and view['deploy_in_progress'] is False
             and view['release_sha256']==ctx['release_sha256'] and instant(view['observed_UTC'])<=now<instant(view['valid_until_UTC'])
             and (now-instant(view['observed_UTC'])).total_seconds()<=10,'HOLD_AUTHORITY')
        need(set(gates)==set(request['required_gates']) and bound['gate_selectors_sha256']==digest(canonical(request['gate_selectors'])),
             'HOLD_GATES')
        self.guard.allow(request['operation']);adapter=self.registry[request['operation']]
        need(adapter.operation==request['operation'] and adapter.mode==self.guard.mode
             and adapter.source_pins==self.guard.value['source_pins'],'HOLD_ADAPTER_UNAVAILABLE')
        adapter.validate(request,originals,gates,admitted)
        return request,adapter

    def invoke(self,slot,bundle,*,view_reader,gate_reader):
        # Unit-selected slot is independent of malformed/changed request bytes.
        # A service cannot invent a second slot by changing a request nonce.
        need(slot in self.election['slots'],'HOLD_AUTHORITY')
        key=digest(canonical({'context':self.guard.context,'slot':slot,'election_sha256':digest(canonical(self.election))}))
        result=None;effect=False;status='HOLD_UNCERTAIN'
        with self.journal.locked() as (fd,rows,anchor):
            consumed=any(r.get('attempt_key')==key for r in rows)
            self.journal.append_witnessed(fd,rows,anchor,{'kind':'INVOCATION','attempt_key':key,
                       'bundle_sha256':digest(canonical(bundle)),'status':'HOLD_CONSUMED' if consumed else 'RESERVED'})
            if consumed:return {'verdict':'HOLD_CONSUMED','effect_started':False,'attempt_key':key}
            began=instant(self.clock());tick=self.monotonic()
            try:
                # The native gate resolver verifies receipts against this already
                # locked, witnessed ledger. It must not acquire another lock.
                if hasattr(gate_reader,'bind_ledger'):gate_reader.bind_ledger(rows)
                need(bundle['references']==self.election['slots'][slot]['references'],'HOLD_AUTHORITY')
                originals=self.channel.originals(bundle['references'])
                gates=gate_reader(originals['request']['value'])
                request,adapter=self._validate(slot,originals,gates,view_reader(),began)
                def recheck():
                    now=instant(self.clock());elapsed=self.monotonic()-tick
                    need(0<=elapsed<request['budget_seconds'] and abs((now-began).total_seconds()-elapsed)<=1,'HOLD_CLOCK')
                    self._validate(slot,originals,gate_reader(request),view_reader(),now,admission_UTC=began)
                    self.guard.recheck()
                recheck()
                # Persist/witness the effect intent before entering any adapter.
                self.journal.append_witnessed(fd,rows,anchor,{'kind':'EFFECT_INTENT','attempt_key':key,
                                       'request_sha256':digest(canonical(request))})
                recheck();effect=True
                detail=adapter.run_once(request,originals,gates,recheck)
                now=instant(self.clock());elapsed=self.monotonic()-tick
                need(0<=elapsed<=request['budget_seconds'] and now<instant(request['end_UTC'])
                     and abs((now-began).total_seconds()-elapsed)<=1,'HOLD_CLOCK')
                self.guard.recheck();need(type(detail) is dict,'HOLD_RESULT')
                result=canonical({'schema':'SERVER_FAMILY_RECEIPT_V2','context':self.guard.context,
                        'operation':request['operation'],'status':'COMPLETE','request_sha256':digest(canonical(request)),
                        'producer_sha256':adapter.producer_sha256,'started_UTC':began.isoformat(),
                        'finished_UTC':now.isoformat(),'detail':detail,'mode':self.guard.mode})
                # No future result digest is put into an already signed BOUND.
                output_name=key+'.receipt.json';adapter.results.create(output_name,result)
                retention=None
                if self.retainer is not None:retention=self.retainer.retain(result,originals,request,recheck=recheck,gates=gates)
                elif self.guard.mode=='REAL':need(False,'RETENTION_NOT_INSTALLED')
                # Disk fsync/retention belongs to this invocation's budget;
                # completion cannot bypass a changed gate or expired runtime.
                recheck()
                status='COMPLETE' if self.guard.mode=='REAL' else 'COMPLETE_FIXTURE'
            except Hold as error:status=str(error) if str(error) in PUBLIC else 'HOLD_UNCERTAIN'
            except Exception:status='HOLD_UNCERTAIN'
            self.journal.append_witnessed(fd,rows,anchor,{'kind':'OUTCOME','attempt_key':key,'status':status,
                      'effect_started':effect,'receipt_sha256':digest(result) if result is not None and status.startswith('COMPLETE') else None,
                      'retention':retention if status.startswith('COMPLETE') else None})
            return {'verdict':status,'effect_started':effect,'attempt_key':key,
                    'receipt_sha256':digest(result) if result is not None and status.startswith('COMPLETE') else None}

    def publish(self,attempt_key,prepared,publication_store,author_id):
        """Public text is supplied by the fixed public projection below."""
        pubkey=digest(canonical({'attempt_key':attempt_key,'kind':'PUBLICATION'}))
        with self.journal.locked() as (fd,rows,anchor):
            outcomes=[r for r in rows if r.get('attempt_key')==attempt_key and r['kind']=='OUTCOME']
            need(len(outcomes)==1,'HOLD_RESULT')
            outcome=outcomes[0]
            need(prepared==public_projection({'verdict':outcome['status'],'effect_started':outcome['effect_started'],
                  'attempt_key':attempt_key,'receipt_sha256':outcome['receipt_sha256']}),'HOLD_RESULT')
            sent=any(r.get('publication_key')==pubkey for r in rows)
            if sent:
                # A repeat is read-only reconciliation, never another POST.
                saved=publication_store.read(pubkey+'.public.txt',pin=digest(prepared),modes=(0o600,))
                need(saved==prepared,'HOLD_RESULT')
                return self.channel.recover_post(prepared,author_id)
            publication_store.create(pubkey+'.public.txt',prepared)
            self.journal.append_witnessed(fd,rows,anchor,{'kind':'PUBLICATION_RESERVED','publication_key':pubkey,
                                    'prepared_sha256':digest(prepared),'attempt_key':attempt_key})
            try:
                self.channel.post_once(prepared)
                observed=self.channel.recover_post(prepared,author_id)
                self.journal.append_witnessed(fd,rows,anchor,{'kind':'PUBLICATION_CLOSED','publication_key':pubkey,**observed})
                return observed
            except Exception:return {'verdict':'HOLD_PUBLICATION_UNCERTAIN','executor_repeated':False}


def public_projection(outcome):
    need(outcome['verdict'] in PUBLIC and type(outcome['effect_started']) is bool,'PUBLIC_FIELDS')
    result={'schema':'SERVER_PUBLIC_RESULT_V2','verdict':outcome['verdict'],'effect_started':outcome['effect_started'],
            'attempt_sha256':sha(outcome['attempt_key']),'receipt_sha256':outcome.get('receipt_sha256')}
    if result['receipt_sha256'] is not None:sha(result['receipt_sha256'])
    return canonical(result)
