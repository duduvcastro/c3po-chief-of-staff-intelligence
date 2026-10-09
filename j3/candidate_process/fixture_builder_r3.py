"""New R2 defect-delta only; three namespaces differ, no REAL authority supplied."""
import ast
from dataclasses import replace
from datetime import datetime,timedelta,timezone,date
import json
from pathlib import Path
import sys
import types
import unittest
from zoneinfo import ZoneInfo
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import config_finalizer as f
import veto_emitter as v
import consumer_codec as codec
import process_receipt as receipt
import os


class FixtureBuilder(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,12,13,0,4,tzinfo=timezone.utc)
        self.observation=b'SYNTHETIC_ORIGINAL_NOT_REAL\n';self.va=b'SYNTHETIC_VETO_AUTHORITY\n';self.ca=b'SYNTHETIC_CONFIG_AUTHORITY\n'
        p=lambda text:v.digest(text.encode())
        self.order={'epoch':f.EPOCH,'authorized_sessions':f.SESSIONS,'capacity':550,'owner_sha':p('SYNTHETIC-machine-owner')}
        self.order_raw=v.canonical(self.order);self.machine_sha=v.digest(v.canonical(self.order))
        self.runtime_sha=p('runtime-intrinsic-pin-DISTINCT');self.markdown_sha=p('signed-Markdown-order-DISTINCT')
        templates=[{'sha':p('template-'+day),'epoch':f.EPOCH,'first_session':f.FIRST,'authorized_sessions':[day],
                    'phases':['admission','bar_manifest','quote_refresh','quote_capture']}for day in f.SESSIONS]
        self.act={'status':'ACCEPTED','chain_head':p('A-DUDU-head'),'order_sha':self.machine_sha,'policy_sha':p('policy'),
                  'capacity':550,'cut_rule':'OPEN_FIRST_THEN_EXISTING_CAUSAL_ORDER_V1_PROPOSED','subphases':{},
                  'individual_go_issuers':['FABLE'],'owner_countersign_phases':['bar_merge_deploy_recertify','install_release','activate','wind_down_28'],
                  'rollback_disposition':'REVALIDATE_UNCOMMITTED_ONLY','epoch':f.EPOCH,'first_session':f.FIRST,
                  'authorized_sessions':f.SESSIONS,'causal_order':{'primary':'ADV_DESC','tie_break':'SYMBOL_ASC','cut':'TAIL_NEW_ONLY'},
                  'policy_epoch_validity':True,'automatic_retry':False,'document_order_sha':self.markdown_sha,
                  'act_a_scope_map':{},'templates':templates,'template_set_sha':v.digest(v.canonical(templates)),
                  'template_shas':{day:p('template-'+day)for day in f.SESSIONS}}
        self.act_raw=self.document(self.act)
        self.template={'schema':f.CONFIG_SCHEMA,'r2d2_v2_capacity_veto_mode':f.MODE,
                       'identity':{'epoch':f.EPOCH,'namespace':f.EPOCH,'first_session':f.FIRST,'authorized_sessions':f.SESSIONS,
                                   'document_order_sha':self.markdown_sha,'runtime_order_sha':self.runtime_sha},
                       'calendar_pin_sha':p('calendar'),'release_sha':p('release'),'package_sha':p('package'),
                       'roots':{key:{'path':'/synthetic-only/'+key,'identity':p('root-'+key)}for key in('documents','payload','go')},
                       'document_pins':{label:{'file':label+'.md','sha256':p(label)}for label in sorted(f.DOCUMENT_LABELS)},
                       'veto_views':{},'restore_revocation':None}
        self.template['document_pins']['ACT_B']['sha256']=v.digest(self.act_raw)
        self.template_raw=v.canonical(self.template)+b'\n'
        self.spec={'schema':f.SPEC_SCHEMA,'mode':'FIXTURE','day':f.FIRST,'template_sha256':v.digest(self.template_raw),
                   'emitter_implementation_sha256':f.EMITTER_SHA256,'authority_sha256':v.digest(self.ca),
                   'verifier':{'identity':'synthetic-config-verifier','implementation_sha256':p('config-verifier')},
                   'build_sha':'1'*40,'runtime_authority_sha256':p('runtime-authority'),
                   'settings_file':'/synthetic-only/config/capacity.json','veto_file':'veto.md',
                   'act_b_order_sha':self.machine_sha,'act_b_original_sha256':v.digest(self.act_raw),
                   'machine_order_original_sha256':v.digest(self.order_raw),
                   'process_nonce':'a'*32,'process_worker_sha256':v.digest((HERE/'veto_worker.py').read_bytes()),
                   'process_receipt_implementation_sha256':v.digest((HERE/'process_receipt.py').read_bytes())}
        static={self.spec['process_worker_sha256'],self.spec['process_receipt_implementation_sha256'],self.spec['template_sha256'],self.spec['emitter_implementation_sha256'],self.spec['authority_sha256'],
                self.spec['verifier']['implementation_sha256'],self.spec['runtime_authority_sha256'],self.machine_sha,v.digest(self.act_raw),v.digest(self.order_raw),
                self.markdown_sha,self.runtime_sha,*[self.template[k]for k in('calendar_pin_sha','release_sha','package_sha')],
                *[item['sha256']for item in self.template['document_pins'].values()]}
        self.vspec={'schema':v.SPEC_SCHEMA,'mode':'FIXTURE','context':{'epoch':f.EPOCH,'first_session':f.FIRST,'day':f.FIRST,'order_sha':self.machine_sha},
                    'source':{'identity':'synthetic-source','implementation_sha256':p('source'),'observation_format':'SYNTHETIC_ONLY'},
                    'verifier':{'identity':'synthetic-veto-verifier','implementation_sha256':p('veto-verifier')},
                    'authority_sha256':v.digest(self.va),'view_opens_at':'2026-10-12T13:00:00Z','maximum_age_seconds':5,
                    'required_pins':sorted(static|{v.digest(self.va),p('source'),p('veto-verifier')})}
        self.vspec['consumer_config_template_sha256']=v.digest(self.template_raw);self.vspec['consumer_document_pins']=sorted({x['sha256']for x in self.template['document_pins'].values()})
        base=dict(self.vspec);base.pop('view_opens_at')
        self.rule={'schema':v.DERIVATION_SCHEMA,'purpose':'IMAGE_ADMISSION_MONDAY','spec_base':base,
            'observe_not_before':'2026-10-12T12:59:00Z','observe_not_after':'2026-10-12T13:01:00Z'}
        self.rule_raw=v.canonical(self.rule)+b'\n';self.rule_sha=v.digest(self.rule_raw)
        self.spec['derivation_rule_sha256']=self.rule_sha
        static.add(self.rule_sha)
        self.vspec_raw=v.canonical(self.vspec)+b'\n';self.spec['veto_spec_sha256']=v.digest(self.vspec_raw)
        self.spec['required_pins']=sorted(static|{self.spec['veto_spec_sha256']});self.spec_raw=v.canonical(self.spec)+b'\n'
        self.vrow=v.VerifiedObservation('FIXTURE','synthetic-source',p('source'),'SYNTHETIC_ONLY',v.digest(self.observation),v.digest(self.va),
                    '2026-10-12T12:59:00Z','2026-10-12T13:01:00Z',tuple(sorted(set(self.vspec['required_pins'])|{self.rule_sha})),'FABLE',True,True,True,
                    f.EPOCH,f.FIRST,f.FIRST,self.machine_sha,'2026-10-12T13:00:00Z','VERIFIED','2026-10-12T13:00:00Z','2026-10-12T13:00:05Z',False,())
        self.vbinding=v.VerifierBinding('synthetic-veto-verifier',p('veto-verifier'),'FIXTURE',lambda *args:self.vrow)
        self.calls=[]
        self.cb=f.ConfigVerifierBinding('synthetic-config-verifier',p('config-verifier'),'FIXTURE',self.verify)
        self.emission=v.emit_view(self.vspec_raw,self.observation,self.va,v.digest(self.observation),spec_sha256=v.digest(self.vspec_raw),verifier=self.vbinding,clock=lambda:self.now,consumer_template_raw=self.template_raw,derivation_rule_raw=self.rule_raw,derivation_rule_sha=self.rule_sha)
        self.receipt_raw=receipt.make(self.emission,nonce=self.spec['process_nonce'],worker_sha256=self.spec['process_worker_sha256'],worker_pid=os.getpid(),rule_sha256=self.rule_sha,template_sha256=v.digest(self.template_raw))

    def document(self,act,state='ISSUED'):
        doc={'schema':v.DOCUMENT_SCHEMA,'kind':'ACT_B','state':state,'body':act}
        return b'SYNTHETIC TEST VECTOR ONLY; NOT AN APPROVAL\n'+v.BEGIN.encode()+b'\n```json\n'+v.canonical(doc)+b'\n```\n'+v.END.encode()+b'\n'

    def verify(self,*args):
        self.calls.append(args)
        spec=json.loads(args[0]);now=args[-1]
        return f.VerifiedConfigAuthority(mode='FIXTURE',spec_sha256=v.digest(args[0]),template_sha256=spec['template_sha256'],
                authority_sha256=spec['authority_sha256'],build_sha=spec['build_sha'],runtime_authority_sha256=spec['runtime_authority_sha256'],
                act_b_order_sha=spec['act_b_order_sha'],act_b_original_sha256=spec['act_b_original_sha256'],
                machine_order_original_sha256=spec['machine_order_original_sha256'],required_pins=tuple(spec['required_pins']),checked_at=now.isoformat(),
                valid_from='2026-10-12T12:59:00Z',valid_until='2026-10-12T13:01:00Z',permitted_settings_file=spec['settings_file'],
                permitted_veto_file=spec['veto_file'],identity_verified=True,static_pins_verified=True,document_authority_verified=True,
                act_b_machine_order_verified=True,runtime_snapshot_verified=True,output_rule_authorized=True,revocation_checked=True,revoked_shas=())

    def finalize(self,**changes):
        args={'spec_raw':self.spec_raw,'template_raw':self.template_raw,'config_authority_raw':self.ca,'spec_sha256':v.digest(self.spec_raw),
              'emission':self.emission,'veto_spec_raw':self.vspec_raw,'veto_authority_raw':self.va,'observation_raw':self.observation,
              'act_b_raw':self.act_raw,'machine_order_raw':self.order_raw,'veto_verifier':self.vbinding,'config_verifier':self.cb,'clock':lambda:self.now,'derivation_rule_raw':self.rule_raw,'emission_receipt_raw':self.receipt_raw}
        args.update(changes);return f.finalize_config(**args)
