"""New protected H16 reader for actual sealed capacity/K12/night artifacts.

This is a read-only data verifier, not DBR, M6, reader activation or liveness.
Those checks require their own exact program and original receipt selectors.
Importing or reading these artifacts never sends an owner question.
"""
from common import canonical, context, digest, fields, linked_receipt, need, sha, strict
from families import ManifestStore


class ArtifactReader:
    reader_id='H16_SEALED_ARTIFACT_READER_V2'
    def __init__(self,source_pin,receipt_store,manifest_store,capacity_store,*,selectors,capacity_request_name):
        self.source_sha256=sha(source_pin);self.receipts=receipt_store
        self.manifests=ManifestStore(manifest_store,capacity_store);self.capacity=capacity_store
        self.selectors=selectors;self.capacity_request_name=capacity_request_name

    def read_once(self,request,binding):
        ctx=context(request['context']);need(binding['reader_id']==self.reader_id and binding['reader_source_sha256']==self.source_sha256,
                                            'ARTIFACT_READER_BINDING')
        gates={}
        need(set(self.selectors)==set(binding['actual_receipts']),'ARTIFACT_READER_ROLE_SET')
        for role,name in self.selectors.items():
            raw=self.receipts.read(name,pin=binding['actual_receipts'][role],modes=(0o600,0o400))
            sel=request['payload']['receipt_selectors'][role]
            value=linked_receipt(raw,sel['context'],operation=sel['operation'])
            need(value['producer_sha256']==sel['producer_sha256'],'ARTIFACT_READER_PRODUCER');gates[role]=value
        day_raw=self.capacity.read('CAPACITY_DAY.json',modes=(0o600,));day=strict(day_raw)
        selected_raw=self.capacity.read('CAPACITY_SELECTED.private.json',modes=(0o600,));selected=strict(selected_raw)
        need(day==gates['CAPACITY_DAY']['detail'] and day['status']==day['documentary_authority']=='VERIFIED'
             and day['capacity_gate_verified'] is True,'ARTIFACT_READER_CAPACITY')
        need(selected['context']==day['context'] and all(day['context'][k]==ctx[k] for k in ('model','epoch','session','release_sha256')),
             'ARTIFACT_READER_CYCLE')
        final=gates['K12_FINAL']['detail']
        need(final['collection']=='VERIFIED' and final['manifest_verified'] is True and final['capacity_day_sha256']==digest(day_raw)
             and final['selected_sha256']==digest(selected_raw),'ARTIFACT_READER_K12_FINAL')
        # H16 checks the actual final manifest and every private bar body again.
        config=self.receipts.read(self.capacity_request_name,modes=(0o400,0o600))
        cap=strict(config);manifest_raw=self.manifests.directory.read('manifest-'+ctx['session']+'.json',modes=(0o400,0o600))
        line={'manifest_sha256':final['manifest_sha256'],'symbol_count':final['symbol_count'],
              'capacity_config_sha256':cap['capacity_config_sha256']}
        actual=self.manifests.verify(dict(request,context=cap['context']),cap,line)
        need(actual['manifest_sha256']==digest(manifest_raw),'ARTIFACT_READER_MANIFEST')
        counts=day['counts'];need(counts['total']==len(selected['open_preserved'])+len(selected['new_admitted'])<=550,
                                  'ARTIFACT_READER_COUNTS')
        return {'schema':'H16_READER_RESULT_V2','status':'COMPLETE','context':ctx,'request_sha256':binding['request_sha256'],
                'actual_receipts':binding['actual_receipts'],'checks':{'night_originals':True,'capacity_original':True,
                   'k12_final_manifest':True,'bar_input_bodies':True,'capacity_counts':True},
                'scope':'SEALED_ARTIFACTS_ONLY','activation_performed':False,'owner_question_sent':False}
