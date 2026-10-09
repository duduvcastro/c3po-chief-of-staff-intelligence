"""CAPACITY_MONDAY cross-request actual dependency candidate, no executor.

Sunday rule pins SOURCE/REQUEST/BOUND selectors, never future receipt/config
hashes. Actual M3, J and derived config are selected Monday under that approved
rule. DOWNSTREAM must observe actual capacity_activate from its different bound
before reader/capture effects. Original semantic/provenance and current physical
settings/worker verification remain independent pinned callbacks; no generic
receipt schema or fixture is promoted to an image COMPLETE.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
import time
import finite_batch as c
from verification_binding import Verifier

@dataclass(frozen=True)
class LinkedReceipt:
    raw:bytes
    source_sha256:str
    role:str
    context:tuple
    status:str
    completed_at:datetime
    request_raw:bytes
    bound_raw:bytes

@dataclass(frozen=True)
class CapacityMondayProof:
    mode:str
    m3:LinkedReceipt
    j:LinkedReceipt
    config_raw:bytes
    config_sha256:str
    activation:LinkedReceipt|None=None

def native_utc():return datetime.now(timezone.utc)

class CapacityMondayGate:
    def __init__(self,rule_raw,*,rule_sha256,read_proof,verify_rule,verify_original,verify_config):
        c.need(type(rule_raw)is bytes and c.pin(rule_sha256) and c.sha(rule_raw)==rule_sha256,'CAPACITY_MONDAY_RULE_PIN')
        self.rule_raw,self.rule_hash=rule_raw,rule_sha256;self.rule=c.strict(rule_raw);r=self.rule
        c.need(type(r)is dict and set(r)=={'schema','mode','epoch','day','authority_sha256','selectors','consumers','verifiers'}
               and r['schema']=='CAPACITY_MONDAY_RULE_CANDIDATE_V1' and r['mode']in{'REAL','FIXTURE'}
               and r['epoch']==c.EPOCH and r['day']==c.DAY and c.pin(r['authority_sha256']), 'CAPACITY_MONDAY_RULE_ABI')
        c.need(type(r['selectors'])is dict and set(r['selectors'])=={'m3','j','activation'},'CAPACITY_MONDAY_SELECTORS')
        for name,selector in r['selectors'].items():
            c.need(type(selector)is dict and set(selector)=={'source_sha256','request_sha256','bound_sha256','role','context'}
              and all(c.pin(selector[k])for k in ('source_sha256','request_sha256','bound_sha256'))
              and type(selector['role'])is str and type(selector['context'])is list
              and len(selector['context'])==4 and selector['context'][:3]==[c.EPOCH,c.DAY,c.PREVIOUS],
              'CAPACITY_MONDAY_SELECTOR_ABI')
        c.need(r['selectors']['m3']['role']=='activate' and r['selectors']['m3']['context'][3]=='BOOTSTRAP'
          and r['selectors']['j']['role']=='admission_manifest' and r['selectors']['j']['context'][3]=='P'
          and r['selectors']['activation']['role']=='capacity_activate' and r['selectors']['activation']['context'][3]=='P',
          'CAPACITY_MONDAY_SELECTOR_ROLE')
        c.need(type(r['consumers'])is dict and set(r['consumers'])=={'CAPACITY_MONDAY','DOWNSTREAM_AFTER_E6'},'CAPACITY_MONDAY_CONSUMERS')
        for consumer in r['consumers'].values():
            c.need(type(consumer)is dict and set(consumer)=={'request_sha256','bound_sha256','authority_sha256'}
              and all(c.pin(v)for v in consumer.values()),'CAPACITY_MONDAY_CONSUMER_PINS')
        c.need({k:r['consumers']['CAPACITY_MONDAY'][k]for k in ('request_sha256','bound_sha256')}=={k:r['selectors']['activation'][k]for k in ('request_sha256','bound_sha256')},
               'CAPACITY_MONDAY_ACTIVATION_BOUND_CHANGED')
        c.need(type(r['verifiers'])is dict and set(r['verifiers'])=={'rule','original','config'}
          and all(type(v)is Verifier for v in (verify_rule,verify_original,verify_config)) and callable(read_proof),
          'CAPACITY_MONDAY_VERIFIERS_REQUIRED')
        for n,v in [('rule',verify_rule),('original',verify_original),('config',verify_config)]:v.validate(r['verifiers'][n],r['mode'])
        self.read_proof,self.verify_rule,self.verify_original,self.verify_config=read_proof,verify_rule,verify_original,verify_config
    def __call__(self,bundle,q,task,now):
        r=self.rule;begin=native_utc();mark=time.monotonic();last_wall=begin;last_mono=mark
        c.need(type(bundle)is c.Bundle and q['lane']in r['consumers'] and c.canonical(q)==bundle.request
          and c.sha(bundle.request)==r['consumers'][q['lane']]['request_sha256']
          and c.sha(bundle.bound)==r['consumers'][q['lane']]['bound_sha256']
          and q['authority_sha256']==r['consumers'][q['lane']]['authority_sha256'] and task in q['tasks'], 'CAPACITY_MONDAY_INVOCATION_UNBOUND')
        op=task['operation'];needs_activation=op!='capacity_activate'
        c.need(op in {'capacity_activate','reader_bound','reader_cycle','policy_read','capture_launch','capture_result','capture_cleanup'},
               'CAPACITY_MONDAY_OPERATION_UNBOUND')
        deadline=mark+min(task['budget_seconds'],(c.instant(task['not_after'])-begin).total_seconds())
        def guard():
            nonlocal last_wall,last_mono
            current,mono=native_utc(),time.monotonic()
            c.need(current>=last_wall and mono>=last_mono,'CAPACITY_MONDAY_CLOCK_REGRESSION')
            last_wall,last_mono=current,mono
            c.need(c.instant(task['not_before'])<=current<c.instant(task['not_after']) and mono<deadline,'CAPACITY_MONDAY_DEADLINE')
            c.need(c.sha(self.rule_raw)==self.rule_hash and c.strict(self.rule_raw)==r
                   and c.canonical(q)==bundle.request and c.sha(bundle.request)==r['consumers'][q['lane']]['request_sha256']
                   and c.sha(bundle.bound)==r['consumers'][q['lane']]['bound_sha256']
                   and q['authority_sha256']==r['consumers'][q['lane']]['authority_sha256'],'CAPACITY_MONDAY_RULE_CHANGED')
            return current
        current=guard()
        self.verify_rule.invoke(r['verifiers']['rule'],r['mode'],self.rule_raw,bundle,q,task,current)
        current=guard();proof=self.read_proof(self.rule_raw,bundle,q,task,current);current=guard()
        c.need(type(proof)is CapacityMondayProof and proof.mode==r['mode'],'CAPACITY_MONDAY_ACTUAL_PROOF_REQUIRED')
        if needs_activation:c.need(type(proof.activation)is LinkedReceipt,'CAPACITY_NOT_ACTIVATED')
        for name,item in [('m3',proof.m3),('j',proof.j)]+([('activation',proof.activation)]if needs_activation else[]):
            selector=r['selectors'][name]
            c.need(type(item)is LinkedReceipt and type(item.raw)is bytes and 0<len(item.raw)<=c.LIMIT
              and item.status=='COMPLETE' and item.source_sha256==selector['source_sha256']
              and item.role==selector['role'] and item.context==tuple(selector['context'])
              and type(item.request_raw)is bytes and type(item.bound_raw)is bytes
              and c.sha(item.request_raw)==selector['request_sha256'] and c.sha(item.bound_raw)==selector['bound_sha256'],
              'CAPACITY_MONDAY_SOURCE_OR_BOUND_CHANGED')
            completion=c.instant(item.completed_at)
            c.need(c.instant('2026-10-12T04:00:00Z')<=completion<=current,'CAPACITY_MONDAY_RECEIPT_CLOCK')
            self.verify_original.invoke(r['verifiers']['original'],r['mode'],item,selector,self.rule_raw,bundle,q,task,current)
            current=guard()
        c.need(c.instant(proof.m3.completed_at)<=c.instant(proof.j.completed_at),'CAPACITY_MONDAY_M3_J_ORDER')
        if needs_activation:c.need(c.instant(proof.j.completed_at)<=c.instant(proof.activation.completed_at),'CAPACITY_MONDAY_AFTER_J_REQUIRED')
        c.need(type(proof.config_raw)is bytes and 0<len(proof.config_raw)<=c.LIMIT
               and c.pin(proof.config_sha256) and c.sha(proof.config_raw)==proof.config_sha256,'CAPACITY_MONDAY_CONFIG_PIN')
        j=c.strict(proof.j.raw[:-1]if proof.j.raw.endswith(b'\n')else proof.j.raw)
        c.need(j.get('schema')=='R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1' and j.get('status')=='PUBLISHED_VERIFIED'
          and j.get('mode')=='PUBLISH' and j.get('code')is None and j.get('epoch')==c.EPOCH and j.get('session')==c.DAY
          and j.get('capacity_config_sha256')==proof.config_sha256 and j.get('massive_bars_enabled')is True,
          'CAPACITY_MONDAY_J_FINAL_CONFIG_UNBOUND')
        c.need(c.instant(j.get('published_at'))==c.instant(proof.j.completed_at),'CAPACITY_MONDAY_J_CLOCK_UNBOUND')
        self.verify_config.invoke(r['verifiers']['config'],r['mode'],proof,self.rule_raw,bundle,q,task,current)
        guard();return None
