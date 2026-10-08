"""Fixed production family integrations, with original file provenance.

These adapters are source implementations. Calling them requires a reviewed
REAL installation acceptance and actual elected channel originals. Fixtures use
the same family code but are clearly marked and never certify a server.
"""
import capacity
import h16
import k12
import math
from common import Hold, canonical, context, digest, fields, instant, linked_receipt, need, sha, strict


class InputStore:
    def __init__(self,directory):self.directory=directory

    def get(self,request,role,*,limit=1024*1024):
        ref=request['input_refs'][role];fields(ref,('name','sha256'),'INPUT_REFERENCE_FIELDS')
        return self.directory.read(ref['name'],pin=sha(ref['sha256']),limit=limit,modes=(0o400,0o444))

    def bundle(self,request):
        desc=strict(self.get(request,'capacity_bundle'))
        # No dynamic Python objects or file paths: descriptors resolve only
        # canonical original byte roles in the private elected input directory.
        need(desc['schema']=='CAPACITY_BUNDLE_DESCRIPTOR_V2' and desc['context']==request['context'],'CAP_BUNDLE_DESCRIPTOR')
        result={'context':desc['context'],'verifier_source_sha256':desc['verifier_source_sha256'],
                'phase_windows':desc['phase_windows']}
        for role in ('order','policy','calendar','release','commitment','causal_list','open_positions','publication',
                     'go_admission','go_admission_record','go_bar_manifest','go_bar_manifest_record'):
            result[role]=self.get(request,desc['roles'][role])
        result['chain']={name:self.get(request,refrole) for name,refrole in desc['roles']['chain'].items()}
        result['set_specs']={name:{key:self.get(request,refrole) for key,refrole in refs.items()}
                             for name,refs in desc['roles']['set_specs'].items()}
        return result


class BaseAdapter:
    def __init__(self,operation,guard,inputs,results):
        self.operation,self.guard,self.inputs,self.results=operation,guard,inputs,results
        self.mode=guard.mode;self.source_pins=guard.value['source_pins']
        self.producer_sha256=sha(self.source_pins['families.py'])

    def validate_gates(self,request,gates):
        selectors=request['gate_selectors']
        need(set(selectors)==set(gates),'FAMILY_GATE_ROLES')
        for role,raw in gates.items():
            sel=selectors[role];r=linked_receipt(raw,sel['context'],operation=sel['operation'])
            need(r['mode']==self.mode and r['producer_sha256']==sha(sel['producer_sha256']), 'FAMILY_GATE_PRODUCER')
            # Exact known originals use digest pins. Deferred H16 gates use the
            # signed selectors plus a COMPLETE outcome from the own journal.
            if 'sha256' in sel:need(digest(raw)==sha(sel['sha256']),'FAMILY_GATE_ORIGINAL_HASH')


class CapacityAdapter(BaseAdapter):
    def __init__(self,operation,guard,inputs,results,output,*,clock):
        super().__init__(operation,guard,inputs,results);self.output,self.clock=output,clock

    def validate(self,request,originals,gates,now):
        self.validate_gates(request,gates)
        bundle=self.inputs.bundle(request)
        need(bundle['verifier_source_sha256']==self.source_pins['capacity.py'],'CAP_VERIFIER_NOT_ELECTED')
        documents=capacity.build_documents(bundle,now=now)
        need(request['payload']['documents_sha256']==digest(canonical({
             'inputs':{k:digest(v) for k,v in documents['inputs'].items()},
             'sets':{k:{r:digest(v) for r,v in s.items()} for k,s in documents['sets'].items()},
             'chain_pins':documents['chain_pins']})),'CAP_DOCUMENT_SET_NOT_BOUND')
        proof=strict(self.inputs.get(request,'capacity_proof'));review=strict(self.inputs.get(request,'capacity_review'))
        need(proof['source_sha256']==self.source_pins['capacity.py'] and review['source_sha256']==self.source_pins['capacity.py'],
             'CAP_PROOF_SOURCE_NOT_ELECTED')

    def run_once(self,request,originals,gates,recheck):
        bundle=self.inputs.bundle(request);now=instant(self.clock())
        kwargs={'proof_raw':self.inputs.get(request,'capacity_proof'),'review_raw':self.inputs.get(request,'capacity_review'),
                'current_view_raw':self.inputs.get(request,'current_capacity_view'),'now':now}
        recheck()
        if self.operation=='F3_CAPACITY_PREPARE':
            return capacity.prepare_once(bundle,output=self.output,recheck=recheck,**kwargs)
        need(self.operation=='F3_CAPACITY_VERIFY','CAP_OPERATION')
        return capacity.verify_day(capacity.build_documents(bundle,now=now),bundle,
                k8_raw=self.output.read('K8_RESULT.json',modes=(0o600,)),
                selected_raw=self.output.read('CAPACITY_SELECTED.private.json',modes=(0o600,)),**kwargs)


class ManifestStore:
    def __init__(self,directory,capacity_directory):self.directory,self.capacity=directory,capacity_directory
    def recheck(self):self.directory.recheck();self.capacity.recheck()
    def state(self,session):
        name='manifest-'+session+'.json'
        if not self.directory.exists(name):return {'published':0,'manifest_sha256':None}
        raw=self.directory.read(name,modes=(0o600,0o400));return {'published':1,'manifest_sha256':digest(raw)}

    def verify(self,request,cap,writer_line):
        ctx=context(request['context']);self.recheck()
        manifest_raw=self.directory.read('manifest-'+ctx['session']+'.json',modes=(0o600,0o400))
        selected_raw=self.capacity.read('CAPACITY_SELECTED.private.json',modes=(0o600,))
        day_raw=self.capacity.read('CAPACITY_DAY.json',modes=(0o600,))
        manifest,selected,day=[strict(v) for v in (manifest_raw,selected_raw,day_raw)]
        need(manifest['schema']=='SERVER_K12_MANIFEST_V2' and manifest['context']==ctx
             and selected['context']==day['context'] and all(day['context'][k]==ctx[k] for k in ('model','epoch','session','release_sha256')),
             'MANIFEST_NEW_MODEL_CONTEXT')
        need(day['schema']=='CAPACITY_DAY_VERIFIED_REPORT_V2' and day['status']==day['documentary_authority']=='VERIFIED'
             and day['capacity_gate_verified'] is True,'MANIFEST_CAPACITY_UNVERIFIED')
        need(manifest['capacity_day_sha256']==digest(day_raw) and manifest['selected_sha256']==digest(selected_raw)
             and manifest['capacity_request_sha256']==digest(canonical(cap)) and manifest['symbols']==selected['open_preserved']+selected['new_admitted'],
             'MANIFEST_SELECTED_OR_REQUEST_BINDING')
        need(writer_line['manifest_sha256']==digest(manifest_raw) and writer_line['symbol_count']==len(manifest['symbols'])
             and writer_line['capacity_config_sha256']==cap['capacity_config_sha256'],'MANIFEST_WRITER_BINDING')
        need(type(manifest['inputs']) is dict and manifest['inputs'] and type(manifest['checks']) is dict
             and manifest['checks'] and all(v is True for v in manifest['checks'].values()),'MANIFEST_INCOMPLETE')
        # Each actual bar input is private, hash checked and tied to the selected
        # symbol/date, so a published flag cannot manufacture data completeness.
        need(set(manifest['inputs'])==set(manifest['symbols']) and len(set(manifest['symbols']))==len(manifest['symbols'])<=550,
             'MANIFEST_SYMBOL_SET')
        for symbol,ref in manifest['inputs'].items():
            raw=self.directory.read(ref['name'],pin=sha(ref['sha256']),modes=(0o400,0o600))
            value=strict(raw)
            need(value['schema']=='SERVER_CAUSAL_BAR_INPUT_V2' and value['symbol']==symbol
                 and value['context']==ctx and value['status']=='VERIFIED' and value['through_session']==manifest['through_session'],
                 'MANIFEST_BAR_CONTEXT')
            bars=value['bars'];need(type(bars) is list and bars,'MANIFEST_BARS_EMPTY')
            previous=None
            for bar in bars:
                fields(bar,('session','open','high','low','close','volume'),'MANIFEST_BAR_FIELDS')
                from datetime import date
                day=date.fromisoformat(bar['session']);need(previous is None or day>previous,'MANIFEST_BAR_ORDER');previous=day
                need(all(type(bar[k]) in (int,float) and math.isfinite(bar[k]) and bar[k]>0 for k in ('open','high','low','close'))
                     and type(bar['volume']) in (int,float) and math.isfinite(bar['volume']) and bar['volume']>=0
                     and bar['low']<=min(bar['open'],bar['close'])<=max(bar['open'],bar['close'])<=bar['high'],
                     'MANIFEST_BAR_VALUES')
            need(previous.isoformat()==manifest['through_session'],'MANIFEST_BAR_LAST_SESSION')
        return {'collection':'VERIFIED','manifest_verified':True,'manifest_sha256':digest(manifest_raw),
                'selected_sha256':digest(selected_raw),'capacity_day_sha256':digest(day_raw),'symbol_count':len(manifest['symbols'])}


class K12Adapter(BaseAdapter):
    def __init__(self,operation,guard,inputs,results,engine,receipts,manifests,*,clock):
        super().__init__(operation,guard,inputs,results)
        self.engine,self.receipts,self.manifests,self.clock=engine,receipts,manifests,clock

    def validate(self,request,originals,gates,now):
        self.validate_gates(request,gates);cap_raw=self.inputs.get(request,'capacity_request');cap=strict(cap_raw)
        need(cap['context']==request['context'],'K12_CAPACITY_REQUEST_SCOPE')
        # Both the actual verified day receipt and final selection must exist;
        # LAUNCH cannot infer capacity from a successful unrelated container.
        need('CAPACITY_DAY' in gates,'K12_CAPACITY_GATE_ABSENT')
        day_ctx=request['gate_selectors']['CAPACITY_DAY']['context']
        need(all(day_ctx[k]==request['context'][k] for k in ('model','epoch','session','release_sha256')),'K12_CAPACITY_DAY_CYCLE')
        day=linked_receipt(gates['CAPACITY_DAY'],day_ctx)['detail']
        need(day['status']==day['documentary_authority']=='VERIFIED' and day['capacity_gate_verified'] is True,
             'K12_CAPACITY_GATE_UNVERIFIED')
        if self.operation!='F4_K12_LAUNCH':k12.plan(request,self.inputs.get(request,'launch_receipt'),cap_raw,now)

    def run_once(self,request,originals,gates,recheck):
        recheck();cap_raw=self.inputs.get(request,'capacity_request')
        if self.operation=='F4_K12_LAUNCH':return self.engine.launch(request,cap_raw,recheck)
        launch_raw=self.inputs.get(request,'launch_receipt')
        result=k12.execute(request,launch_raw,cap_raw,engine=self.engine,receipts=self.receipts,
                           manifests=self.manifests,clock=self.clock,recheck=recheck)
        if self.operation=='F4_K12_COLLECT' and result['collection']=='WRITER_PUBLISHED_BYTES_ONLY':
            p,cap,_=k12.plan(request,launch_raw,cap_raw,instant(self.clock()))
            _,line=k12.persisted(self.receipts.read(p['persist_name'],modes=(0o600,)),p,cap,request['context'])
            recheck();result.update(self.manifests.verify(request,cap,line))
        return result


class H16Adapter(BaseAdapter):
    def __init__(self,operation,guard,inputs,results,reader,*,clock):
        super().__init__(operation,guard,inputs,results);self.reader,self.clock=reader,clock

    def validate(self,request,originals,gates,now):
        self.validate_gates(request,gates)
        return h16.authorize(request,originals['question']['value'],originals['owner']['value'],
                             originals['authority']['value']['family_authority'],gates,now,
                             question_published_UTC=originals['question']['created_UTC'])

    def run_once(self,request,originals,gates,recheck):
        return h16.execute(request,originals['question']['value'],originals['owner']['value'],
                  originals['authority']['value']['family_authority'],gates,clock=self.clock,recheck=recheck,reader=self.reader,
                  question_published_UTC=originals['question']['created_UTC'])
