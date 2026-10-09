"""Candidate decoder for the actual K9_STEP_RECEIPT_V1 byte ABI.

It never runs/imports a runner or fabricates a receipt/GO. The historical runner
563a4797 is epoch03 and is refused for Monday04. Actual04 runner source, exact
step-plan bytes, command registry and original file provenance remain required.
AST literal reconciliation only binds declared ABI constants; the mandatory
independent verifier must attest the complete approved source/command/authority,
original file identity/readback and outputs against the real execution.
"""
from __future__ import annotations
import ast,copy,json,re,time
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
import finite_batch as c
from verification_binding import Verifier

RECEIPT_KEYS={'schema','status','code','epoch','day','phase','operation','attempt_key','step_plan_sha256',
              'started_at','completed_at','package_sha256','build_sha','outputs','aggregates','counts'}
PLAN_KEYS={'schema','epoch','day','k9_phase','k9_operation','slot','attempt_key','request_sha256','go_sha256',
           'run_not_after','constants','network_class','database','risk','step_row'}
CONST_KEYS={'package_sha256','code_revision','act_b_sha256','release_sha256','policy_sha256','runner_sha256',
            'risk_source_pins_sha256','risk_limits','disk_floor_bytes'}
OUTPUT=re.compile(r'(day|source)(/[A-Za-z0-9][A-Za-z0-9._=-]{0,127}){1,8}\Z')
COUNT=re.compile(r'[a-z][a-z0-9]{0,30}(_[a-z0-9]{1,30}){1,4}\Z')
GIT=re.compile(r'[0-9a-f]{40}\Z')
ALIASES={'collect':'collect_launch','commit_result':'commit_launch',
         'publish_launch':'publish_launch','capture_launch':'capture_launch'}

@dataclass(frozen=True)
class Binding:
    core_operation:str
    step_plan_raw:bytes
    runner_source_raw:bytes
    runner_source_sha256:str
    provenance_binding_sha256:str

@dataclass(frozen=True)
class Approval:
    # The expected rule hash comes from the approved owner/authority/installer
    # outside Binding. It is never inferred from Binding's self-consistent pins.
    rule_raw:bytes
    rule_sha256:str
    k9_request_raw:bytes
    k9_go_raw:bytes


def native_utc():return datetime.now(timezone.utc)


def compiled_literals(source):
    tree=ast.parse(source);compiled={}
    wanted={'EPOCH','DAYS','PACKAGE','REVISION','OPS','RECEIPT_KEYS','PLAN_KEYS','CONST_KEYS','LIMITS','FLOOR','DB'}
    allowed=set()
    for node in tree.body:
        if type(node)is ast.Assign and len(node.targets)==1 and type(node.targets[0])is ast.Name and node.targets[0].id in wanted:
            target=node.targets[0];c.need(target.id not in compiled,'K9_COMPILED_BINDING_DUPLICATED')
            try:compiled[target.id]=ast.literal_eval(node.value)
            except (ValueError,TypeError):raise c.Hold('K9_COMPILED_BINDING_NOT_LITERAL') from None
            allowed.add(id(target))
    # Fail closed on every other Store/Del of these roots, not just top-level
    # literal Assign. Mutating method calls on protected roots are forbidden.
    def rooted(node):
        while type(node)in(ast.Attribute,ast.Subscript):node=node.value
        return type(node)is ast.Name and node.id in wanted
    for node in ast.walk(tree):
        if type(node)is ast.Name and node.id in wanted and isinstance(node.ctx,(ast.Store,ast.Del)):
            c.need(id(node)in allowed,'K9_COMPILED_REBINDING_FORBIDDEN')
        if type(node)is ast.Call and type(node.func)is ast.Attribute and rooted(node.func.value):
            c.need(node.func.attr in {'get','keys','values','items'},'K9_COMPILED_MUTATION_FORBIDDEN')
        if type(node)in(ast.Assign,ast.AnnAssign,ast.AugAssign,ast.Delete):
            targets=node.targets if type(node)in(ast.Assign,ast.Delete)else[node.target]
            for target in targets:
                if type(target)in(ast.Attribute,ast.Subscript)and rooted(target):
                    raise c.Hold('K9_COMPILED_REBINDING_FORBIDDEN')
    c.need(set(compiled)==wanted,'K9_COMPILED_BINDING_MISSING')
    return compiled

def original_json(raw):
    c.need(type(raw) is bytes and 0<len(raw)<=256*1024,'K9_ORIGINAL_BYTES_INVALID')
    body=raw[:-1] if raw.endswith(b'\n') else raw
    return c.strict(body) # preserves the supplied original bytes in Receipt.raw

def utc(value):
    c.need(type(value) is str and 0<len(value)<=40,'K9_RECEIPT_CLOCK_INVALID')
    try:parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:raise c.Hold('K9_RECEIPT_CLOCK_INVALID') from None
    c.need(parsed.utcoffset()==timedelta(0),'K9_RECEIPT_CLOCK_INVALID')
    return parsed.astimezone(timezone.utc)

def counts(value,depth=0):
    return type(value) is dict and len(value)<=64 and all(type(k) is str and COUNT.fullmatch(k)
          and (type(v) is int and 0<=v<=10**7 or depth==0 and counts(v,1)) for k,v in value.items())

class K9ReceiptAdapter:
    def __init__(self,binding,verify_original,*,approval,verify_approval):
        c.need(type(approval)is Approval and type(approval.rule_raw)is bytes and c.pin(approval.rule_sha256)
               and c.sha(approval.rule_raw)==approval.rule_sha256,'K9_EXTERNAL_APPROVAL_REQUIRED')
        rule=original_json(approval.rule_raw)
        c.need(type(rule)is dict and set(rule)=={'schema','mode','epoch','day','runner_source_sha256',
          'step_plan_sha256','provenance_binding_sha256','invocation_request_sha256','invocation_bound_sha256',
          'k9_request_sha256','k9_go_sha256','phase_not_before','phase_not_after','verifiers'} and rule['schema']=='K9_APPROVED_DECODER_RULE_CANDIDATE_V1'
          and rule['mode']in{'REAL','FIXTURE'} and rule['epoch']==c.EPOCH and rule['day']==c.DAY
          and all(c.pin(rule[k])for k in ('runner_source_sha256','step_plan_sha256','provenance_binding_sha256',
                'invocation_request_sha256','invocation_bound_sha256','k9_request_sha256','k9_go_sha256')),
          'K9_APPROVAL_RULE_ABI')
        c.need(utc(rule['phase_not_before'])<utc(rule['phase_not_after']),'K9_APPROVED_PHASE_WINDOW')
        c.need(type(rule['verifiers'])is dict and set(rule['verifiers'])=={'approval','original'}
          and type(verify_approval)is Verifier and type(verify_original)is Verifier,'K9_VERIFIERS_UNAVAILABLE')
        verify_approval.validate(rule['verifiers']['approval'],rule['mode']);verify_original.validate(rule['verifiers']['original'],rule['mode'])
        c.need(type(approval.k9_request_raw)is bytes and type(approval.k9_go_raw)is bytes
          and c.sha(approval.k9_request_raw)==rule['k9_request_sha256'] and c.sha(approval.k9_go_raw)==rule['k9_go_sha256'],
          'K9_APPROVAL_ORIGINALS_CHANGED')
        c.need(type(binding)is Binding and binding.runner_source_sha256==rule['runner_source_sha256']
          and binding.provenance_binding_sha256==rule['provenance_binding_sha256']
          and c.sha(binding.step_plan_raw)==rule['step_plan_sha256'],'K9_NOT_APPROVED_EXTERNAL_SOURCE')
        c.need(type(binding.runner_source_raw)is bytes and 0<len(binding.runner_source_raw)<=1024*1024
               and c.sha(binding.runner_source_raw)==rule['runner_source_sha256'],'K9_RUNNER_SOURCE_PIN_CHANGED')
        compiled=compiled_literals(binding.runner_source_raw)
        c.need(compiled['EPOCH']==c.EPOCH and type(compiled['DAYS']) in (tuple,list) and c.DAY in compiled['DAYS'],
               'K9_RUNNER_EPOCH04_ORIGINAL_REQUIRED')
        c.need(compiled['RECEIPT_KEYS']==RECEIPT_KEYS and compiled['PLAN_KEYS']==PLAN_KEYS
               and compiled['CONST_KEYS']==CONST_KEYS and c.pin(compiled['PACKAGE'])
               and type(compiled['REVISION']) is str and GIT.fullmatch(compiled['REVISION']), 'K9_COMPILED_ABI_CHANGED')
        plan=original_json(binding.step_plan_raw)
        c.need(set(plan)==PLAN_KEYS and plan['schema']=='K9_STEP_PLAN_V1' and plan['epoch']==c.EPOCH
               and plan['day']==c.DAY and type(plan['constants']) is dict and set(plan['constants'])==CONST_KEYS,
               'K9_STEP_PLAN_UNBOUND')
        op=plan['k9_operation'];ops=compiled['OPS']
        c.need(type(op) is str and type(ops) is dict and op in ops and type(ops[op]) in (tuple,list)
               and len(ops[op])==3 and plan['k9_phase']==ops[op][0] and plan['network_class']==ops[op][1],
               'K9_STEP_PLAN_OPERATION_UNBOUND')
        key=c.sha(json.dumps([c.EPOCH,c.DAY,plan['k9_phase'],op],separators=(',',':'),ensure_ascii=True).encode('ascii'))
        constants=plan['constants']
        c.need(plan['attempt_key']==key and plan['request_sha256']==rule['k9_request_sha256'] and plan['go_sha256']==rule['k9_go_sha256']
               and constants['runner_sha256']==binding.runner_source_sha256
               and constants['package_sha256']==compiled['PACKAGE'] and constants['code_revision']==compiled['REVISION']
               and constants['risk_limits']==compiled['LIMITS'] and constants['disk_floor_bytes']==compiled['FLOOR']
               and all(c.pin(constants[k]) for k in ('act_b_sha256','release_sha256','policy_sha256','risk_source_pins_sha256')),
               'K9_STEP_PLAN_CONSTANTS_CHANGED')
        c.need(plan['database']==(compiled['DB'] if op in ('commit_launch','publish_launch') else None),
               'K9_STEP_PLAN_DATABASE_CHANGED')
        # No generic role mapping. Result/cleanup/readiness/risk and new lane
        # adapters have different ABIs and are not accepted by this decoder.
        c.need(type(binding.core_operation) is str and binding.core_operation in ALIASES
               and op==ALIASES[binding.core_operation],
               'K9_CORE_OPERATION_UNBOUND')
        self.binding,self.verify_original=binding,verify_original
        self.approval,self.rule,self.verify_approval=approval,rule,verify_approval
        self.approval_fingerprint=c.sha(approval.rule_raw),c.sha(approval.k9_request_raw),c.sha(approval.k9_go_raw)
        self.plan,self.compiled=plan,compiled
        self.compiled_original=copy.deepcopy(compiled)
        self.fingerprint=c.sha(binding.step_plan_raw),c.sha(binding.runner_source_raw)
    def decode(self,raw,invocation,*,now=None):
        c.need(now is None,"K9_CLOCK_INJECTION_FORBIDDEN")
        current,mark=native_utc(),time.monotonic()
        start,monostart=current,mark
        def guard():
            nonlocal current,mark
            wall,mono=native_utc(),time.monotonic()
            c.need(wall>=current and mono>=mark,"K9_CLOCK_REGRESSION")
            current,mark=wall,mono
            c.need(current<invocation.deadline_utc and mono<invocation.deadline_monotonic,"K9_ORIGINAL_AFTER_DEADLINE")
            c.need(self.approval_fingerprint==(c.sha(self.approval.rule_raw),c.sha(self.approval.k9_request_raw),c.sha(self.approval.k9_go_raw))
              and self.rule==original_json(self.approval.rule_raw),"K9_APPROVAL_CHANGED")
            return current
        c.need(type(invocation) is c.Invocation and invocation.operation==self.binding.core_operation
               and invocation.context==(c.EPOCH,c.DAY,c.PREVIOUS,'P')
               and invocation.request_sha256==self.rule['invocation_request_sha256']
               and invocation.bound_sha256==self.rule['invocation_bound_sha256'],'K9_INVOCATION_CONTEXT_CHANGED')
        guard()
        self.verify_approval.invoke(self.rule['verifiers']['approval'],self.rule['mode'],self.approval,self.binding,invocation,current)
        guard()
        c.need(self.fingerprint==(c.sha(self.binding.step_plan_raw),c.sha(self.binding.runner_source_raw)),
               'K9_BINDING_CHANGED')
        doc=original_json(raw);plan=self.plan;compiled=self.compiled;current=guard()
        c.need(compiled==self.compiled_original,'K9_COMPILED_ORIGINAL_CHANGED')
        c.need(type(doc) is dict and set(doc)==RECEIPT_KEYS and doc['schema']=='K9_STEP_RECEIPT_V1'
               and doc['status']=='COMPLETE' and doc['code'] is None and doc['epoch']==c.EPOCH
               and doc['day']==c.DAY and doc['phase']==plan['k9_phase'] and doc['operation']==plan['k9_operation']
               and doc['attempt_key']==plan['attempt_key'] and doc['step_plan_sha256']==c.sha(self.binding.step_plan_raw)
               and doc['package_sha256']==compiled['PACKAGE'] and doc['build_sha']==compiled['REVISION'],
               'K9_ORIGINAL_NOT_EXACT_COMPLETE')
        started,completed=utc(doc['started_at']),utc(doc['completed_at'])
        c.need(started<=completed<=current<invocation.deadline_utc and completed<utc(plan['run_not_after']),
               'K9_ORIGINAL_AFTER_DEADLINE')
        c.need(utc(self.rule['phase_not_before'])<=started<=completed<utc(self.rule['phase_not_after']),
               'K9_ORIGINAL_OUTSIDE_APPROVED_PHASE')
        if plan['k9_operation']=='capture_launch':
            c.need(utc('2026-10-12T04:00:00Z')<=started and completed>=utc('2026-10-12T14:01:00Z'),
                   'K9_CAPTURE_MONDAY_CLOSE_REQUIRED')
        outputs,aggregates=doc['outputs'],doc['aggregates']
        c.need(type(outputs) is dict and type(aggregates) is dict and len(outputs)<=64 and len(aggregates)<=8
               and all(type(k) is str and OUTPUT.fullmatch(k) and '/.' not in k for k in list(outputs)+list(aggregates))
               and all(c.pin(v) for v in outputs.values()) and counts(doc['counts']),'K9_ORIGINAL_RECEIPT_GRAMMAR')
        if plan['k9_operation']=='capture_launch':
            c.need(doc['counts'].get('capture_complete')==1 and type(doc['counts'].get('capture_complete')) is int
                   and doc['counts'].get('consumer_failed')==0 and type(doc['counts'].get('consumer_failed')) is int
                   and set(outputs)=={'source/snapshot.json','source/tape/'+c.DAY+'.us-quote.ndjson'},
                   'K9_CAPTURE_ACTUAL_COMPLETE_REQUIRED')
        self.verify_original.invoke(self.rule["verifiers"]["original"],self.rule["mode"],raw,self.binding,self.approval,invocation,current,doc,plan,compiled)
        guard()
        c.need(self.fingerprint==(c.sha(self.binding.step_plan_raw),c.sha(self.binding.runner_source_raw))
               and doc==original_json(raw) and plan==original_json(self.binding.step_plan_raw)
               and compiled==self.compiled_original,
               'K9_VERIFIER_CHANGED_ORIGINALS')
        return c.Receipt(raw,self.binding.core_operation,invocation.context,'COMPLETE',completed)
