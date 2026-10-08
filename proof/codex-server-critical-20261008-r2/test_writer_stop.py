"""Native child writer parent binding and C35 integration, all isolated fixtures."""
import copy
import os
import unittest
from pathlib import Path
import test_integrated as helpers
from test_k12 import example as k12_example
from test_native import Guard,h
from common import Hold,canonical,digest,strict
from families import K12Adapter,InputStore,ManifestStore
from processes import DockerEngine
from writer_main import run


class TestWriterStop(unittest.TestCase):
    setUp=helpers.TestIntegrated.setUp;tearDown=helpers.TestIntegrated.tearDown
    complete_capacity=helpers.TestIntegrated.complete_capacity;actual_bar_fixture=helpers.TestIntegrated.actual_bar_fixture
    def writer(self,wrong=False):
        bundle,cap,config,day=self.actual_bar_fixture(night=True);ctx=bundle['context'];guard=Guard();guard.context=ctx
        configpin=digest(canonical(config));source=digest((Path(__file__).parent/'manifest_writer.py').read_bytes())
        parent={'schema':'SERVER_FAMILY_REQUEST_V2','context':dict(ctx,session='2026-10-09') if wrong else ctx,
          'operation':'F4_K12_LAUNCH','payload':{'configuration_sha256':configpin},
          'start_UTC':'2026-10-12T01:09:00Z','end_UTC':'2026-10-12T01:11:01Z','budget_seconds':120}
        files={}
        for role,value in (('writer_configuration',config),('writer_parent_request',parent)):
            raw=canonical(value);self.roots['inputs'].create(role+'.json',raw);p=self.base/'inputs'/(role+'.json');os.chmod(p,0o400)
            files[role]={'path':str(p),'sha256':digest(raw)}
        guard.value.update(source_pins={'manifest_writer.py':source},spec={'files':files,'roots':{k:str(self.base/k) for k in ('capacity','bars')}},
           measurement={'roots':{k:[{'identity':self.roots[k].identity}] for k in ('capacity','bars')}},
           writer_registry={'start_UTC':parent['start_UTC'],'end_UTC':parent['end_UTC'],'budget_seconds':120,
                            'parent_request_sha256':digest(canonical(parent))})
        return guard
    def test_t05_t18_native_child_reads_exact_parent_then_publishes_once(self):
        guard=self.writer();line=run(guard,clock=lambda:'2026-10-12T01:09:00Z');self.assertEqual(strict(line)['symbol_count'],550)
        with self.assertRaises(FileExistsError):run(guard,clock=lambda:'2026-10-12T01:09:00Z')
        self.assertTrue(self.roots['bars'].exists('writer-2026-10-12.claim.json'))
    def test_t05_t16_wrong_parent_cycle_refuses_before_claim(self):
        guard=self.writer(wrong=True)
        with self.assertRaisesRegex(Hold,'WRITER_PARENT_REQUEST'):run(guard,clock=lambda:'2026-10-12T01:09:00Z')
        self.assertFalse(self.roots['bars'].exists('writer-2026-10-12.claim.json'))
    def stop(self,bad=None):
        bundle,cap,config,day=self.actual_bar_fixture(night=True);ctx=bundle['context'];req,_,_,fake,_=k12_example('STOP')
        req['context']=ctx;req['required_gates']=['CAPACITY_DAY'];req['payload']['view_UTC']=cap['view_UTC']
        req['payload']['capacity_request_sha256']=digest(canonical(cap));req.update(start_UTC='2026-10-12T01:08:30Z',
                end_UTC='2026-10-12T01:09:40Z',budget_seconds=28)
        detail={k:req['payload'][k] for k in ('container_id','capacity_request_sha256','window','window_slot','view_UTC')};detail['image_id']=cap['image_id']
        launch=canonical({'schema':'SERVER_FAMILY_RECEIPT_V2','context':ctx,'operation':'F4_K12_LAUNCH','status':'COMPLETE',
             'request_sha256':req['payload']['launch_request_sha256'],'started_UTC':'2026-10-12T01:06:59Z',
             'finished_UTC':'2026-10-12T01:07:00Z','detail':detail})
        req['payload']['launch_receipt_sha256']=digest(launch)
        fake.row.update(image_id=cap['image_id'],cmd=cap['writer_argv'],network_mode=cap['network'],mounts=[],
              capacity_label=digest(canonical(cap)),started_at='2026-10-12T01:07:00Z')
        if bad=='budget':req['budget_seconds']=27
        if bad=='margin':req['end_UTC']='2026-10-12T01:08:58Z'
        if bad=='predecessor':req['start_UTC']='2026-10-12T01:07:00Z'
        for role,raw in (('capacity_request',canonical(cap)),('launch_receipt',launch)):
            name=role+'.json';self.roots['inputs'].create(name,raw);os.chmod(self.base/'inputs'/name,0o400)
            req.setdefault('input_refs',{})[role]={'name':name,'sha256':digest(raw)}
        guard=Guard();guard.context=ctx;source=digest((Path(__file__).parent/'families.py').read_bytes());guard.value['source_pins']={'families.py':source}
        capreceipt=canonical({'schema':'SERVER_FAMILY_RECEIPT_V2','context':ctx,'mode':'FIXTURE','operation':'F3_CAPACITY_PREPARE',
              'producer_sha256':source,'status':'COMPLETE','request_sha256':h('own capacity req'),
              'started_UTC':'2026-10-12T01:00:01Z','finished_UTC':'2026-10-12T01:00:01Z','detail':day})
        req['gate_selectors']={'CAPACITY_DAY':{'context':ctx,'operation':'F3_CAPACITY_PREPARE','producer_sha256':source,'sha256':digest(capreceipt)}}
        calls=[]
        class Runner:
            def run(_,argv,**opts):
                calls.append(argv);action=argv[3]
                if action=='inspect':return {'returncode':0,'stdout':canonical(fake.row)}
                if action=='stop':fake.row.update(state='exited',running=False,exit_code=143,finished_at='2026-10-12T01:08:40Z');return {'returncode':0,'stdout':b'fixture-id\n'}
                raise AssertionError('Unregistered fixture action')
        adapter=K12Adapter('F4_K12_STOP',guard,InputStore(self.roots['inputs']),self.roots['results'],DockerEngine(guard,Runner()),
                          self.roots['receipts'],ManifestStore(self.roots['bars'],self.roots['capacity']),clock=lambda:'2026-10-12T01:08:30Z')
        return adapter,req,{'CAPACITY_DAY':capreceipt},calls
    def test_t10_c35_native_fixed_stop_after_actual_predecessor_with_positive_floor(self):
        adapter,req,gates,calls=self.stop();from common import instant
        adapter.validate(req,{},gates,instant('2026-10-12T01:08:30Z'));out=adapter.run_once(req,{},gates,lambda:None)
        self.assertEqual(out['effects'],1);self.assertEqual([x[3] for x in calls],['inspect','stop','inspect'])
        self.assertEqual(calls[1][-4:],['stop','--time','10','a'*64]);self.assertEqual(out['manifest_counts']['published'],0)
    def test_t10_c35_insufficient_budget_margin_or_unfinished_predecessor_no_engine(self):
        adapter,req,gates,calls=self.stop(bad='margin');from common import instant
        with self.assertRaisesRegex(Hold,'C35_NO_POSITIVE_FLOOR'):adapter.validate(req,{},gates,instant('2026-10-12T01:08:30Z'))
        self.assertEqual(calls,[])
    def test_t10_c35_budget_less_than_28_has_no_engine_effect(self):
        adapter,req,gates,calls=self.stop(bad='budget');from common import instant
        with self.assertRaisesRegex(Hold,'C35_BUDGET'):adapter.validate(req,{},gates,instant('2026-10-12T01:08:30Z'))
        self.assertEqual(calls,[])
    def test_t10_c35_window_equal_predecessor_has_no_positive_floor(self):
        adapter,req,gates,calls=self.stop(bad='predecessor');from common import instant
        with self.assertRaisesRegex(Hold,'C35_NO_POSITIVE_FLOOR'):adapter.validate(req,{},gates,instant('2026-10-12T01:08:30Z'))
        self.assertEqual(calls,[])


if __name__=='__main__':unittest.main()
