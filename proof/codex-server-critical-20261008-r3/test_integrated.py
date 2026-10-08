"""New T10/T11/T18 integrations, actual family code and private fixture files.

Only helper data from the own F3/F4/F5 examples are reused. Their closed test
suites are not repeated. Authority, bar rows and engine are synthetic fixtures.
"""
import copy
import os
import tempfile
import unittest
from pathlib import Path
import capacity
import h16
import k12
from common import Hold,PinnedDirectory,canonical,digest,hash_value,instant,strict
from families import InputStore,CapacityAdapter,ManifestStore,K12Adapter
from manifest_writer import publish
from reader_artifacts import ArtifactReader
from test_capacity import example as cap_example,results as cap_results
from test_k12 import example as k12_example
from test_h16 import example as h16_example

def h(text):return digest(text.encode())


class TestIntegrated(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='f6-INTEGRATED-FIXTURE-',dir=str(Path(tempfile.gettempdir()).resolve()))
        os.chmod(self.tmp.name,0o700);self.base=Path(self.tmp.name);self.roots={}
        for name in ('capacity','bars','receipts','inputs','results'):
            p=self.base/name;p.mkdir(mode=0o700);self.roots[name]=PinnedDirectory(p)
    def tearDown(self):
        for root in self.roots.values():root.close()
        self.tmp.cleanup()
    def complete_capacity(self,night=False):
        if night:
            from night_fixture import example
            bundle=example()
        else:bundle=cap_example()
        bundle['verifier_source_sha256']=digest((Path(__file__).parent/'capacity.py').read_bytes())
        now='2026-10-12T01:00:01Z' if night else '2026-10-12T13:00:01Z'
        docs=capacity.build_documents(bundle,now=instant(now));args=cap_results(bundle,docs)
        if night:
            v=strict(args['current_view_raw']);v.update(observed_UTC='2026-10-12T01:00:00Z',valid_until_UTC='2026-10-12T01:00:10Z')
            args['current_view_raw']=canonical(v);args['now']=instant(now)
        options={k:args[k] for k in ('proof_raw','review_raw','current_view_raw','now')}
        report=capacity.prepare_once(bundle,output=self.roots['capacity'],recheck=lambda:None,**options)
        return bundle,docs,args,report
    def actual_bar_fixture(self,night=False):
        bundle,docs,args,report=self.complete_capacity(night=night);ctx=bundle['context'];selected=strict(self.roots['capacity'].read('CAPACITY_SELECTED.private.json'))
        # Writer argv/image values are synthetic; no Docker daemon is called.
        cap={'schema':'R2D2_CAPACITY_DAY_ONCE_REQUEST_V2','context':ctx,'window':'primary','window_slot':1,
             'view_UTC':'2026-10-12T01:10:00Z' if night else '2026-10-12T13:00:00Z','capacity_config_sha256':h('config'),
             'image_id':'sha256:'+h('image'),'writer_argv':['python','-I','-B','/own-writer/writer.py'],
             'network':'fixture-network','mounts':[]}
        bars={}
        for symbol in selected['open_preserved']+selected['new_admitted']:
            raw=canonical({'schema':'SERVER_CAUSAL_BAR_INPUT_V2','context':ctx,'symbol':symbol,'through_session':'2026-10-09',
                'status':'VERIFIED','bars':[{'session':'2026-10-09','open':10,'high':11,'low':9,'close':10,'volume':100}]})
            name='bar-'+symbol+'.json';self.roots['bars'].create(name,raw);bars[symbol]={'name':name,'sha256':digest(raw)}
        config={'schema':'SERVER_K12_WRITER_CONFIG_V2','context':ctx,'capacity_request_raw':canonical(cap).decode(),
             'capacity_day_sha256':digest(canonical(report)),'selected_sha256':digest(self.roots['capacity'].read('CAPACITY_SELECTED.private.json')),
             'through_session':'2026-10-09','bars':bars,'capacity_config_sha256':cap['capacity_config_sha256'],
             'producer_sha256':digest((Path(__file__).parent/'manifest_writer.py').read_bytes())}
        return bundle,cap,config,report
    def test_t18_capacity_actual_selection_writer_manifest_independent_consumer(self):
        bundle,cap,config,report=self.actual_bar_fixture()
        line=publish(config,self.roots['capacity'],self.roots['bars'],recheck=lambda:None)
        result=ManifestStore(self.roots['bars'],self.roots['capacity']).verify({'context':bundle['context']},cap,strict(line))
        self.assertTrue(result['manifest_verified']);self.assertEqual(result['symbol_count'],550)
        with self.assertRaisesRegex(Hold,'WRITER_ALREADY_PUBLISHED'):publish(config,self.roots['capacity'],self.roots['bars'],recheck=lambda:None)
    def test_t18_missing_or_changed_bar_body_never_becomes_final_verified(self):
        bundle,cap,config,report=self.actual_bar_fixture();symbol=next(iter(config['bars']));config['bars'][symbol]['sha256']=h('wrong')
        with self.assertRaisesRegex(Hold,'FILE_HASH'):publish(config,self.roots['capacity'],self.roots['bars'],recheck=lambda:None)
        self.assertFalse(self.roots['bars'].exists('manifest-2026-10-12.json'))
    def test_t10_native_adapter_persist_and_final_collect_exact_abi(self):
        bundle,cap,config,report=self.actual_bar_fixture();line=publish(config,self.roots['capacity'],self.roots['bars'],recheck=lambda:None)
        req,_,_,engine,now=k12_example();ctx=bundle['context'];capraw=canonical(cap)
        req['context']=ctx;req['payload']['view_UTC']=cap['view_UTC'];req['start_UTC']='2026-10-12T13:01:01Z';req['end_UTC']='2026-10-12T13:04:01Z'
        req['payload']['capacity_request_sha256']=digest(capraw)
        detail={k:req['payload'][k] for k in ('container_id','capacity_request_sha256','window','window_slot','view_UTC')};detail['image_id']=cap['image_id']
        launch=canonical({'schema':'SERVER_FAMILY_RECEIPT_V2','context':ctx,'status':'COMPLETE','operation':'F4_K12_LAUNCH',
             'request_sha256':req['payload']['launch_request_sha256'],'started_UTC':'2026-10-12T12:59:00Z','finished_UTC':'2026-10-12T12:59:05Z','detail':detail})
        req['payload']['launch_receipt_sha256']=digest(launch);engine.stdout=line
        engine.row.update(capacity_label=digest(capraw),cmd=cap['writer_argv'],network_mode=cap['network'],mounts=[],image_id=cap['image_id'])
        engine.row['finished_at']='2026-10-12T13:00:30Z'
        self.roots['inputs'].create('capacity-request.json',capraw);self.roots['inputs'].create('launch-receipt.json',launch)
        for name in ('capacity-request.json','launch-receipt.json'):os.chmod(self.base/'inputs'/name,0o400)
        req['input_refs']={'capacity_request':{'name':'capacity-request.json','sha256':digest(capraw)},'launch_receipt':{'name':'launch-receipt.json','sha256':digest(launch)}}
        class Guard:
            mode='FIXTURE';value={'source_pins':{'families.py':h('fixture family')}}
        manifests=ManifestStore(self.roots['bars'],self.roots['capacity'])
        persist=K12Adapter(req['operation'],Guard(),InputStore(self.roots['inputs']),self.roots['results'],engine,self.roots['receipts'],manifests,clock=lambda:'2026-10-12T13:01:01Z')
        out=persist.run_once(req,{}, {},lambda:None);self.assertEqual(out['effects'],1)
        req=copy.deepcopy(req);req['operation']='F4_K12_COLLECT';req['payload']['mode']='COLLECT'
        collect=K12Adapter(req['operation'],Guard(),InputStore(self.roots['inputs']),self.roots['results'],engine,self.roots['receipts'],manifests,clock=lambda:'2026-10-12T13:01:01Z')
        final=collect.run_once(req,{}, {},lambda:None);self.assertEqual(final['collection'],'VERIFIED');self.assertTrue(final['manifest_verified'])
        self.assertEqual(final['capacity_day_sha256'],digest(canonical(report)));self.assertEqual(engine.calls,['inspect','logs','inspect'])
    def test_t11_prior_owner_gate_selection_accepts_only_actual_night_originals(self):
        req,question,owner,authority,gates=h16_example()
        # Newly marked complete production-family outputs are still fixtures.
        for role,raw in list(gates.items()):self.roots['receipts'].create(role+'.json',raw)
        binding=h16.authorize(req,question,owner,authority,gates,instant('2026-10-12T09:00:00Z'))
        self.assertEqual(set(binding['actual_receipts']),set(gates));self.assertFalse(binding['new_owner_question'])
        changed=copy.deepcopy(gates);r=strict(changed['K12_FINAL']);r['detail']['manifest_verified']=False;changed['K12_FINAL']=canonical(r)
        with self.assertRaises(Hold):h16.authorize(req,question,owner,authority,changed,instant('2026-10-12T09:00:00Z'))
    def test_t18_native_capacity_adapter_reads_every_bound_original_from_private_store(self):
        bundle=cap_example();source=digest((Path(__file__).parent/'capacity.py').read_bytes());bundle['verifier_source_sha256']=source
        docs=capacity.build_documents(bundle,now=instant('2026-10-12T13:00:01Z'));args=cap_results(bundle,docs)
        req={'context':bundle['context'],'input_refs':{},'payload':{'documents_sha256':digest(canonical({
             'inputs':{k:digest(v) for k,v in docs['inputs'].items()},'sets':{k:{r:digest(v) for r,v in s.items()} for k,s in docs['sets'].items()},'chain_pins':docs['chain_pins']}))},
             'gate_selectors':{}}
        def put(role,raw):
            name=role+'.json';self.roots['inputs'].create(name,raw);os.chmod(self.base/'inputs'/name,0o400)
            req['input_refs'][role]={'name':name,'sha256':digest(raw)};return role
        roles={}
        for role in ('order','policy','calendar','release','commitment','causal_list','open_positions','publication','go_admission','go_admission_record','go_bar_manifest','go_bar_manifest_record'):
            roles[role]=put(role,bundle[role])
        roles['chain']={key:put('chain-'+key,raw) for key,raw in bundle['chain'].items()}
        roles['set_specs']={window:{key:put(window+'-'+key,raw) for key,raw in rows.items()} for window,rows in bundle['set_specs'].items()}
        descriptor={'schema':'CAPACITY_BUNDLE_DESCRIPTOR_V2','context':bundle['context'],'verifier_source_sha256':source,
                    'phase_windows':bundle['phase_windows'],'roles':roles}
        put('capacity_bundle',canonical(descriptor));put('capacity_proof',args['proof_raw']);put('capacity_review',args['review_raw']);put('current_capacity_view',args['current_view_raw'])
        class Guard:
            mode='FIXTURE';value={'source_pins':{'families.py':h('new fixture family'),'capacity.py':source}}
        adapter=CapacityAdapter('F3_CAPACITY_PREPARE',Guard(),InputStore(self.roots['inputs']),self.roots['results'],self.roots['capacity'],clock=lambda:'2026-10-12T13:00:01Z')
        adapter.validate(req,{}, {},instant('2026-10-12T13:00:01Z'));report=adapter.run_once(req,{}, {},lambda:None)
        self.assertEqual(report['counts']['total'],550);self.assertEqual(report['status'],'VERIFIED');self.assertFalse(report['operational_GO'])


if __name__=='__main__':unittest.main()
