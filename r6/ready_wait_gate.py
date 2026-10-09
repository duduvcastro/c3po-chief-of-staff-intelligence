"""Finite read-only READY wait INSIDE one outer CLAIM, BEFORE final veto.

No execute/reclaim/ready creation, fallback, future clock or operational GO.
Only absent ready may wait; a present divergent file fails immediately. A new
fresh complete capacity snapshot is still mandatory at FIRST_SESSION after the
core rereads dependencies/authority/identity/veto. Outer watchdog owns hard kill.
"""
from datetime import datetime,timezone
import time
import finite_batch as c
import image_path_adapter as image
from verification_binding import Verifier

def native_utc():return datetime.now(timezone.utc)

class ReadyWaitGate:
    def __init__(self,rule_raw,*,rule_sha256,read_ready,verify_rule,verify_ready):
        c.need(type(rule_raw)is bytes and c.pin(rule_sha256) and c.sha(rule_raw)==rule_sha256,'READY_WAIT_RULE_PIN')
        self.rule_raw,self.rule_hash=rule_raw,rule_sha256;self.rule=c.strict(rule_raw)
        r=self.rule
        c.need(type(r)is dict and set(r)=={'schema','mode','epoch','day','request_sha256','bound_sha256',
          'calendar_sha256','not_before','not_after','max_wait_seconds','poll_seconds','verifiers'}
          and r['schema']=='L12_READY_WAIT_RULE_CANDIDATE_V1' and r['mode']in{'REAL','FIXTURE'}
          and r['epoch']==c.EPOCH and r['day']==c.DAY,'READY_WAIT_RULE_ABI')
        c.need(all(c.pin(r[k])for k in ('request_sha256','bound_sha256','calendar_sha256')),'READY_WAIT_RULE_PINS')
        c.need(c.instant(r['not_before'])<c.instant(r['not_after'])
          and type(r['max_wait_seconds'])in(int,float) and 0<r['max_wait_seconds']<=120
          and type(r['poll_seconds'])in(int,float) and 0<r['poll_seconds']<=1,'READY_WAIT_BUDGET')
        c.need(type(r['verifiers'])is dict and set(r['verifiers'])=={'rule','ready'},'READY_WAIT_VERIFIERS')
        c.need(type(verify_rule)is Verifier and type(verify_ready)is Verifier and callable(read_ready),'READY_WAIT_ADAPTERS_UNAVAILABLE')
        verify_rule.validate(r['verifiers']['rule'],r['mode']);verify_ready.validate(r['verifiers']['ready'],r['mode'])
        self.read_ready,self.verify_rule,self.verify_ready=read_ready,verify_rule,verify_ready
    def __call__(self,bundle,q,task,now):
        r=self.rule;start=native_utc();mark=time.monotonic();last_wall=start;last_mono=mark
        c.need(type(bundle)is c.Bundle and c.sha(bundle.request)==r['request_sha256']
               and c.sha(bundle.bound)==r['bound_sha256'] and c.canonical(q)==bundle.request
               and task in q['tasks'] and task['operation']=='reader_cycle','READY_WAIT_INVOCATION_UNBOUND')
        c.need(c.sha(self.rule_raw)==self.rule_hash and c.strict(self.rule_raw)==r,'READY_WAIT_RULE_CHANGED')
        begin=max(c.instant(task['not_before']),c.instant(r['not_before']))
        end=min(c.instant(task['not_after']),c.instant(r['not_after']))
        deadline=mark+min(task['budget_seconds'],r['max_wait_seconds'],(end-start).total_seconds())
        def guard():
            nonlocal last_wall,last_mono
            current,mono=native_utc(),time.monotonic()
            c.need(current>=last_wall and mono>=last_mono,'READY_WAIT_CLOCK_REGRESSION')
            last_wall,last_mono=current,mono
            c.need(begin<=current<end and mono<deadline,'READY_WAIT_DEADLINE')
            c.need(c.sha(self.rule_raw)==self.rule_hash and c.strict(self.rule_raw)==r
                   and c.sha(bundle.request)==r['request_sha256'] and c.sha(bundle.bound)==r['bound_sha256'],
                   'READY_WAIT_RULE_CHANGED')
            return current
        while True:
            current=guard()
            self.verify_rule.invoke(r['verifiers']['rule'],r['mode'],self.rule_raw,bundle,q,task,current)
            current=guard();evidence=self.read_ready(r,task,current);current=guard()
            if evidence is not None:
                c.need(type(evidence)is image.FileEvidence,'READY_WAIT_ORIGINAL_UNBOUND')
                body=image.strict_json(evidence.raw)
                c.need(body=={'epoch':c.EPOCH,'session':c.DAY},'READY_WAIT_ORIGINAL_DIVERGENT')
                self.verify_ready.invoke(r['verifiers']['ready'],r['mode'],evidence,self.rule_raw,bundle,q,task,current)
                guard();return None
            # Sleep only after a verified absence, within the SAME consumed call.
            # It never grants another effect, request, physical slot or GO.
            guard();time.sleep(min(r['poll_seconds'],max(0,deadline-time.monotonic())))
