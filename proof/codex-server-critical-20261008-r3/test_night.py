"""Coherent new T18 fixture: actual K8/K12/artifact/H16 code and disk journal.

Night producer receipts, owner originals, SQL connector and Docker transport
are explicitly synthetic. All produced capacity/manifest/bar bytes are real
temporary fixture bytes read independently. No production evidence is invented.
"""
import copy
import os
import unittest
from pathlib import Path
from common import Hold,PinnedDirectory,canonical,digest,instant,strict
import test_integrated as integrated_helpers
from test_k12 import example as k12_example
import test_real_adapters as adapter_helpers
from test_real_adapters import OriginalsChannel
from test_native import Guard,h
from families import K12Adapter,H16Adapter,InputStore,ManifestStore
from manifest_writer import publish
from journal import Journal,IndependentWitness,bootstrap_fixture
from readers import GateReader
from reader_artifacts import ArtifactReader
from reader_checks import CompleteReader
from control import Controller,public_projection


class TestNight(unittest.TestCase):
    setUp=integrated_helpers.TestIntegrated.setUp;tearDown=integrated_helpers.TestIntegrated.tearDown
    complete_capacity=integrated_helpers.TestIntegrated.complete_capacity;actual_bar_fixture=integrated_helpers.TestIntegrated.actual_bar_fixture
    file=adapter_helpers.TestAdapters.file;db=adapter_helpers.TestAdapters.db;host=adapter_helpers.TestAdapters.host
    def setup_night(self):
        bundle,cap,config,day=self.actual_bar_fixture(night=True);capctx=bundle['context'];ctx=dict(capctx,lane='AM')
        self.assertEqual(bundle['context']['epoch'],'TEST_F6_NIGHT_20261012')
        writer=publish(config,self.roots['capacity'],self.roots['bars'],recheck=lambda:None)
        req,_,_,engine,_=k12_example();req['context']=capctx;req['payload']['view_UTC']=cap['view_UTC']
        req['start_UTC']='2026-10-12T01:11:01Z';req['end_UTC']='2026-10-12T01:14:01Z'
        cappin=digest(canonical(cap));req['payload']['capacity_request_sha256']=cappin
        detail={k:req['payload'][k] for k in ('container_id','capacity_request_sha256','window','window_slot','view_UTC')};detail['image_id']=cap['image_id']
        launch=canonical({'schema':'SERVER_FAMILY_RECEIPT_V2','mode':'FIXTURE','context':capctx,'status':'COMPLETE',
            'operation':'F4_K12_LAUNCH','request_sha256':req['payload']['launch_request_sha256'],
            'started_UTC':'2026-10-12T01:09:00Z','finished_UTC':'2026-10-12T01:09:05Z','detail':detail})
        req['payload']['launch_receipt_sha256']=digest(launch);engine.stdout=writer
        engine.row.update(capacity_label=cappin,cmd=cap['writer_argv'],network_mode=cap['network'],mounts=[],image_id=cap['image_id'],
                          started_at='2026-10-12T01:09:01Z',finished_at='2026-10-12T01:10:30Z')
        for role,raw in (('capacity_request',canonical(cap)),('launch_receipt',launch)):
            name=role+'.json';self.roots['inputs'].create(name,raw);os.chmod(self.base/'inputs'/name,0o400)
            req.setdefault('input_refs',{})[role]={'name':name,'sha256':digest(raw)}
        family_pin=digest((Path(__file__).parent/'families.py').read_bytes());guard=Guard();guard.context=ctx
        guard.value['source_pins']={'families.py':family_pin};guard.value['allowed_operations']=['F5_H16_READ']
        store=ManifestStore(self.roots['bars'],self.roots['capacity'])
        persist=K12Adapter('F4_K12_PERSIST',guard,InputStore(self.roots['inputs']),self.roots['results'],engine,self.roots['receipts'],store,
                           clock=lambda:'2026-10-12T01:11:01Z')
        persisted=persist.run_once(req,{}, {},lambda:None)
        from k12_reader_reference import k12_persisted
        wire=self.roots['receipts'].read(req['payload']['persist_name']);old_reader,line=k12_persisted(wire,{'epoch':capctx['epoch'],'container_id':'a'*64})
        self.assertEqual(line,writer);self.assertEqual(len(old_reader),18)
        collect=copy.deepcopy(req);collect['operation']='F4_K12_COLLECT';collect['payload']['mode']='COLLECT'
        final=K12Adapter(collect['operation'],guard,InputStore(self.roots['inputs']),self.roots['results'],engine,self.roots['receipts'],store,
                         clock=lambda:'2026-10-12T01:11:01Z').run_once(collect,{}, {},lambda:None)
        self.assertTrue(final['manifest_verified']);self.assertEqual(final['symbol_count'],550)
        receipt_details={'CAPACITY_DAY':day,'K12_FINAL':final,'commit_result':{},'publish_launch':{}}
        gates={};selectors={};gcfg={};upstreams={}
        for lane,roles in (('CAPACITY',('CAPACITY_DAY','K12_FINAL')),('S',('commit_result','publish_launch'))):
            gatectx=dict(ctx,lane=lane);seed={'mode':'FIXTURE','context':gatectx,'schema':'SERVER_JOURNAL_INSTALLATION_ELECTION_V2',
                                             'installation_plan_sha256':h('FIXTURE upstream '+lane)}
            for suffix in ('journal','witness','results'):
                name=lane+'-'+suffix;p=self.base/name;p.mkdir(mode=0o700);self.roots[name]=PinnedDirectory(p)
            a,b,out=[self.roots[lane+'-'+suffix] for suffix in ('journal','witness','results')]
            pins=bootstrap_fixture(a.path,b.path,seed);w=IndependentWitness(b,pins['witness']['events.jsonl'],pins['witness']['lock'],
                   election=seed,ledger_root=a.identity,independence={},mode='FIXTURE')
            journal=Journal(a,pins['ledger']['events.jsonl'],pins['ledger']['lock'],election=seed,witness=w);upstreams[lane]=(journal,out)
            for role in roles:
                operation={'CAPACITY_DAY':'F3_CAPACITY_PREPARE','K12_FINAL':'F4_K12_COLLECT'}.get(role,role)
                time={'CAPACITY_DAY':'2026-10-12T01:00:01Z','K12_FINAL':'2026-10-12T01:11:01Z',
                      'commit_result':'2026-10-12T02:01:00Z','publish_launch':'2026-10-12T02:02:00Z'}[role]
                producer=family_pin if lane=='CAPACITY' else h('FIXTURE original night producer')
                raw=canonical({'schema':'SERVER_FAMILY_RECEIPT_V2','mode':'FIXTURE','context':gatectx,'status':'COMPLETE','operation':operation,
                     'request_sha256':h('FIXTURE own '+role+' request'),'producer_sha256':producer,
                     'started_UTC':time,'finished_UTC':time,'detail':receipt_details[role]})
                key=h('FIXTURE outcome '+role);out.create(key+'.receipt.json',raw);self.roots['receipts'].create(role+'.json',raw);gates[role]=raw
                with journal.locked() as (fd,rows,anchor):
                    journal.append_witnessed(fd,rows,anchor,{'kind':'OUTCOME','attempt_key':key,'status':'COMPLETE_FIXTURE',
                          'effect_started':True,'receipt_sha256':digest(raw),'retention':None})
                selectors[role]={'context':gatectx,'operation':operation,'producer_sha256':producer,
                   'earliest_UTC':'2026-10-11T22:00:00Z','latest_UTC':'2026-10-12T04:00:00Z','max_age_seconds':43200}
                gcfg[role]={'context':gatectx,'operation':operation,'producer_sha256':producer,
                           'origin':'EXTERNAL_WITNESSED_JOURNAL','journal_id':lane}
        self.roots['receipts'].create('capacity-request.json',canonical(cap))
        artifacts=ArtifactReader(h('artifact source'),self.roots['receipts'],self.roots['bars'],self.roots['capacity'],
             selectors={role:role+'.json' for role in gates},capacity_request_name='capacity-request.json')
        database,dbcalls,dbconn=self.db();database.entry['expected_state_sha256']=h('state')
        # Connector fixture has the actual new cycle release, not a host query.
        from test_native import CTX
        self.assertEqual(ctx['release_sha256'],CTX['release_sha256'])
        host,he,row,hostcalls=self.host();he['labels']['c3po.server.epoch']=ctx['epoch']
        reader=CompleteReader(h('complete reader source'),artifacts,database,host,{'capacity_binding_sha256':h('capacity binding')})
        request={'schema':'SERVER_FAMILY_REQUEST_V2','context':ctx,'operation':'F5_H16_READ','authority_slot':'AM_OWN_1',
             'pins':{'model_review_sha256':h('new H16 own review'),'runtime_measurement_sha256':guard.value['measurement_sha256']},
             'start_UTC':'2026-10-12T09:00:00Z','end_UTC':'2026-10-12T09:02:01Z','budget_seconds':120,
             'required_gates':sorted(gates),'gate_selectors':selectors,'payload':{'reader_id':reader.reader_id,
                'reader_source_sha256':reader.source_sha256,'receipt_selectors':selectors,'max_lateness_seconds':5}}
        rp=digest(canonical(request));family={'schema':'H16_MODEL_AUTHORITY_V2','context':ctx,'request_sha256':rp,
             'reader_id':reader.reader_id,'reader_source_sha256':reader.source_sha256,'model_review_sha256':request['pins']['model_review_sha256'],
             'required_selectors_sha256':digest(canonical(selectors))}
        authority={'schema':'SERVER_OPERATION_AUTHORITY_V2','context':ctx,'slot':'AM_OWN_1','request_sha256':rp,
            'runtime_measurement_sha256':guard.value['measurement_sha256'],'registry_sha256':guard.value['registry_sha256'],
            'operation':'F5_H16_READ','family_authority':family}
        review={'schema':'SERVER_OPERATION_REVIEW_V2','context':ctx,'request_sha256':rp,'verdict':'ACCEPTED_OWN_BYTES',
             'authority_sha256':digest(canonical(authority)),'source_pins':guard.value['source_pins']}
        # Question original contains no fabricated future API publication time.
        question={'schema':'SERVER_OWNER_QUESTION_V2','request_sha256':rp}
        owner={'schema':'SERVER_OWNER_RESPONSE_V2','request_sha256':rp,'question_sha256':digest(canonical(question)),
            'literal':'Assino','channel':'REGISTRO_PELA_FABLE','signed_at_UTC':'2026-10-11T23:01:00Z'}
        bound={'schema':'SERVER_BOUND_V2','context':ctx,'request_sha256':rp,'question_sha256':digest(canonical(question)),
             'owner_sha256':digest(canonical(owner)),'review_sha256':digest(canonical(review)),
             'runtime_measurement_sha256':guard.value['measurement_sha256'],'gate_selectors_sha256':digest(canonical(selectors))}
        channel=OriginalsChannel();values=dict(request=request,authority=authority,review=review,question=question,owner=owner,bound=bound)
        refs={role:channel.put(value,{'owner':'2026-10-11T23:01:00Z','bound':'2026-10-11T23:02:00Z'}.get(role,'2026-10-11T23:00:00Z')) for role,value in values.items()}
        channel.originals=lambda references:{k:channel.original(r,channel.collection()) for k,r in references.items()}
        guard.value['election']={'mode':'FIXTURE','context':ctx,'slots':{'AM_OWN_1':{'operation':'F5_H16_READ',
             'authority_sha256':digest(canonical(authority)),'review_sha256':digest(canonical(review)),
             'pins':request['pins'],'owner_deadline_UTC':'2026-10-12T00:45:00Z','max_lateness_seconds':5,'references':refs}}}
        for suffix in ('journal','witness'):
            name='AM-'+suffix;p=self.base/name;p.mkdir(mode=0o700);self.roots[name]=PinnedDirectory(p)
        a,b=self.roots['AM-journal'],self.roots['AM-witness'];seed={'mode':'FIXTURE','context':ctx,'installation_plan_sha256':h('AM fixture plan')}
        pins=bootstrap_fixture(a.path,b.path,seed);w=IndependentWitness(b,pins['witness']['events.jsonl'],pins['witness']['lock'],election=seed,
            ledger_root=a.identity,independence={},mode='FIXTURE');journal=Journal(a,pins['ledger']['events.jsonl'],pins['ledger']['lock'],election=seed,witness=w)
        gates_reader=GateReader(guard,self.roots['results'],self.roots['receipts'],channel,dict(gcfg,_own_root_identity=a.identity),external_journals=upstreams)
        adapter=H16Adapter('F5_H16_READ',guard,InputStore(self.roots['inputs']),self.roots['results'],reader,clock=lambda:'2026-10-12T09:00:00Z')
        controller=Controller(guard,journal,{'F5_H16_READ':adapter},channel,clock=lambda:'2026-10-12T09:00:00Z',monotonic=lambda:1.0)
        view={'schema':'SERVER_AUTHORITY_VIEW_V2','context':ctx,'veto':False,'revoked_shas':[],'concurrent_attempts':[],
              'deploy_in_progress':False,'release_sha256':ctx['release_sha256'],'observed_UTC':'2026-10-12T09:00:00Z','valid_until_UTC':'2026-10-12T09:00:10Z'}
        return controller,refs,gates_reader,view,hostcalls,dbcalls,upstreams,request
    def test_t18_complete_new_night_capacity_persist_collect_h16_durable_once(self):
        controller,refs,gates,view,hostcalls,dbcalls,upstream,request=self.setup_night()
        result=controller.invoke('AM_OWN_1',{'references':refs},view_reader=lambda:view,gate_reader=gates)
        self.assertEqual(result['verdict'],'COMPLETE_FIXTURE');self.assertTrue(result['effect_started'])
        receipt=strict(self.roots['results'].read(result['attempt_key']+'.receipt.json'))
        self.assertFalse(receipt['detail']['owner_question_sent']);self.assertEqual(receipt['detail']['check_count'],8)
        self.assertEqual(len(hostcalls),3);self.assertEqual(len(dbcalls),5)
        self.assertNotIn('receipt_sha256',str(request['payload']['receipt_selectors']))
        again=controller.invoke('AM_OWN_1',{'references':refs},view_reader=lambda:view,gate_reader=gates)
        self.assertEqual(again['verdict'],'HOLD_CONSUMED');self.assertEqual(len(hostcalls),3)
    def test_t09_t18_upstream_rollback_or_actual_bar_change_blocks_h16_reader(self):
        controller,refs,gates,view,hostcalls,dbcalls,upstream,request=self.setup_night()
        path=self.base/'S-journal'/'events.jsonl';first=path.read_bytes().splitlines(keepends=True)[0];path.write_bytes(first)
        result=controller.invoke('AM_OWN_1',{'references':refs},view_reader=lambda:view,gate_reader=gates)
        self.assertEqual(result['verdict'],'HOLD_UNCERTAIN');self.assertEqual(hostcalls,[]);self.assertEqual(dbcalls,[])
    def test_t18_changed_actual_manifest_body_blocks_before_db_or_host(self):
        controller,refs,gates,view,hostcalls,dbcalls,upstream,request=self.setup_night()
        path=next((self.base/'bars').glob('bar-*.json'));path.write_bytes(canonical({'status':'not-original'}))
        result=controller.invoke('AM_OWN_1',{'references':refs},view_reader=lambda:view,gate_reader=gates)
        self.assertEqual(result['verdict'],'HOLD_UNCERTAIN');self.assertEqual(hostcalls,[]);self.assertEqual(dbcalls,[])


if __name__=='__main__':unittest.main()
