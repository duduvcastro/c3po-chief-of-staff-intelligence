"""New native integration cases. Every original/channel/DB/engine is a fixture.

Only temporary private files and isolated fixture children have effects here.
No Docker, SQL connection, provider, owner question, installation or real GO.
"""
import copy
import io
import json
import os
import pwd
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from common import Hold,PinnedDirectory,canonical,digest,instant,strict
from runtime import identity,measure,physical,RuntimeGuard
from test_native import Guard,Channel,envelope,CTX,h
from installation import ROOT_ROLES,host_preamble,prepare,units
from acceptance import build
from observer import Observer
from retention import pack,unpack,NativeRetainer,MAXIMUM
from reader_checks import DBReader,ReaderHost,BEGIN,TIMEOUT,PRIVILEGES,EPOCH,BINDING,UNIT_FORMAT


class OriginalsChannel:
    def __init__(self):self.rows={};self.counter=0
    def collection(self):return list(self.rows)
    def put(self,value,created='2026-10-11T23:01:00Z'):
        self.counter+=1;raw=canonical(value)
        ref={'id':self.counter,'author_id':313137248,'author_type':'User','body_sha256':digest(raw)}
        self.rows[self.counter]={'raw':raw,'value':value,'created_UTC':created,'id':self.counter};return ref
    def original(self,reference,collection):
        result=copy.deepcopy(self.rows[reference['id']])
        if digest(result['raw'])!=reference['body_sha256']:raise Hold('FIXTURE_ORIGINAL_PIN')
        return result


class TestAdapters(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='f6-adapters-FIXTURE-',dir=str(Path(tempfile.gettempdir()).resolve()))
        self.base=Path(self.tmp.name);os.chmod(self.base,0o700);self.open=[]
        # Local Mac launcher has a symlinked framework ancestor. The fixture
        # explicitly selects its physical executable; production is unrelaxed.
        self.python=patch('sys.executable',str(Path(sys.executable).resolve()));self.python.start()
    def tearDown(self):
        for d in self.open:d.close()
        self.python.stop()
        self.tmp.cleanup()
    def directory(self,name):
        p=self.base/name;p.mkdir(mode=0o700);d=PinnedDirectory(p);self.open.append(d);return d
    def file(self,name,raw,mode=0o400):
        p=self.base/name;p.write_bytes(raw);os.chmod(p,mode);return p
    def installation(self):
        channel=OriginalsChannel();source=self.file('own-fixture.py',b'# explicit FIXTURE source\n')
        plan={'schema':'SERVER_INSTALLATION_PLAN_V2','mode':'FIXTURE','context':CTX,'host':host_preamble('FIXTURE'),
            'source_files':[{'path':str(source),'sha256':digest(source.read_bytes())}],
            'claim_parent':str(self.base),'claim_name':'own-installation.claim.json',
            'roots':{role:str(self.base/role) for role in ROOT_ROLES},
            'registry_template':{'schema':'SERVER_NATIVE_REGISTRY_V2','context':CTX,'operations':['F3_CAPACITY_VERIFY']},
            'assets':[],'channel':{},'start_UTC':'2026-10-11T23:04:00Z','end_UTC':'2026-10-11T23:07:00Z',
            'budget_seconds':60,'witness_independence':{'fixture_same_device':True}}
        subject=digest(canonical(plan));question={'schema':'SERVER_INSTALLATION_QUESTION_V2','context':CTX,'subject_sha256':subject}
        q=channel.put(question,'2026-10-11T23:00:00Z')
        owner={'schema':'SERVER_INSTALLATION_OWNER_V2','context':CTX,'subject_sha256':subject,'question_sha256':q['body_sha256'],
            'literal':'Assino a instalação F6','channel':'REGISTRO_PELA_FABLE','signed_at_UTC':'2026-10-11T23:01:00Z'}
        o=channel.put(owner)
        review={'schema':'SERVER_INSTALLATION_REVIEW_V2','context':CTX,'subject_sha256':subject,'verdict':'ACCEPTED_OWN_BYTES',
            'host':plan['host'],'source_files':plan['source_files']};r=channel.put(review)
        plan['authority_references']={'question':q,'owner':o,'review':r}
        return plan,channel,source
    def test_t08_t13_explicit_preparation_separate_genesis_no_timer_no_auto_repair(self):
        plan,channel,source=self.installation();receipt=prepare(canonical(plan),clock=lambda:'2026-10-11T23:05:00Z',fixture=True,channel=channel)
        self.assertEqual(receipt['timers_installed'],0);self.assertFalse(receipt['operational_GO'])
        seed=receipt['journal_election'];self.assertNotIn('slots',seed)
        self.assertEqual(strict((self.base/'journal'/'events.jsonl').read_bytes())['election'],seed)
        self.assertEqual(set(receipt['roots']),ROOT_ROLES)
        with self.assertRaisesRegex(Hold,'INSTALL_ROOT_ALREADY_EXISTS'):prepare(canonical(plan),clock=lambda:'2026-10-11T23:05:00Z',fixture=True,channel=channel)
        self.assertTrue((self.base/'own-installation.claim.json').is_file())
    def test_t04_t08_install_refusal_or_changed_source_has_no_first_claim(self):
        plan,channel,source=self.installation();ref=plan['authority_references']['owner'];channel.rows[ref['id']]['value']['literal']='Não'
        with self.assertRaisesRegex(Hold,'INSTALL_OWNER'):prepare(canonical(plan),clock=lambda:'2026-10-11T23:05:00Z',fixture=True,channel=channel)
        self.assertFalse((self.base/'own-installation.claim.json').exists())
        os.chmod(source,0o600);source.write_bytes(b'# changed\n');os.chmod(source,0o400)
        with self.assertRaisesRegex(Hold,'INSTALL_SOURCE_CHANGED'):prepare(canonical(plan),clock=lambda:'2026-10-11T23:05:00Z',fixture=True,channel=channel)
    def acceptance(self):
        plan,channel,source=self.installation();prepared=prepare(canonical(plan),clock=lambda:'2026-10-11T23:05:00Z',fixture=True,channel=channel)
        registry=self.base/'inputs'/'registry.json'
        manifest={'files':[{'name':'own-fixture.py','bytes':len(source.read_bytes()),'sha256':digest(source.read_bytes())}]}
        mpfile=self.file('fixture-manifest.json',canonical(manifest))
        spec={'mode':'FIXTURE','context':CTX,'roots':plan['roots'],
              'files':{'registry':{'path':str(registry),'sha256':digest(registry.read_bytes()),'mode':0o400},
                       'source_manifest':{'path':str(mpfile),'sha256':digest(mpfile.read_bytes()),'mode':0o400},
                       'own-fixture.py':{'path':str(source),'sha256':digest(source.read_bytes()),'mode':0o400}},
              'mutable_files':{},'executables':{'python':{'path':sys.executable,'sha256':digest(physical(sys.executable,maximum=128*1024*1024,executable=True)[0])}},'socket':None}
        for role in ('journal','witness'):
            for name in ('events.jsonl','lock'):
                path=self.base/role/name;spec['mutable_files'][role+'-'+name]={'path':str(path),'identity':identity(path.stat())}
        measurement=measure(spec);mp=digest(canonical(measurement));guard=Guard();guard.value['measurement_sha256']=mp
        guard.value['registry_sha256']=digest(registry.read_bytes());guard.value['source_pins']={'own-fixture.py':digest(source.read_bytes())}
        originals,bundle,election,view=envelope(guard)
        refs={role:channel.put(v['value'],v['created_UTC']) for role,v in originals.items()}
        slots={'OWN_SLOT_1':{'references':refs,'owner_deadline_UTC':'2026-10-12T00:45:00Z','max_lateness_seconds':5}}
        defn={'schema':'SERVER_RUNTIME_ELECTION_DEFINITION_V2','mode':'FIXTURE','context':CTX,'slots':slots,'extensions':{}}
        # The exact subject is independently supplied, not generated as a PASS
        # by acceptance.build. This deliberately labelled fixture emulates it.
        slot=dict(slots['OWN_SLOT_1'],operation='F3_CAPACITY_VERIFY',authority_sha256=refs['authority']['body_sha256'],
                  review_sha256=refs['review']['body_sha256'],pins=originals['request']['value']['pins'],
                  start_UTC=originals['request']['value']['start_UTC'],end_UTC=originals['request']['value']['end_UTC'],budget_seconds=60)
        subject={'spec_sha256':digest(canonical(spec)),'measurement_sha256':mp,'prepared_sha256':digest(canonical(prepared)),
                 'manifest_sha256':digest(canonical(manifest)),'slots_sha256':digest(canonical({'OWN_SLOT_1':slot})),
                 'extensions_sha256':digest(canonical({})),'context':CTX,'mode':'FIXTURE'}
        rr={'schema':'SERVER_RUNTIME_REVIEW_V2','subject':subject,'mode':'FIXTURE','verdict':'ACCEPTED_OWN_BYTES_AND_PHYSICAL_RUNTIME',
            'rollback_independence_verified':True,'fixture_emulation_not_physical':True}
        defn['runtime_review']=channel.put(rr,'2026-10-11T23:07:00Z')
        return list(map(canonical,(spec,measurement,prepared,manifest,defn))),channel,source
    def test_t05_t08_native_runtime_acceptance_own_originals_then_exact_units_data_only(self):
        args,channel,source=self.acceptance();raw=build(*args,channel=channel,clock=lambda:'2026-10-11T23:08:00Z',fixture=True)
        p=self.file('acceptance.json',raw);guard=RuntimeGuard(p,digest(raw),fixture=True);guard.recheck()
        formatted=units(raw,h('manifest'),source_root='/fixture/source',acceptance_path='/fixture/acceptance.json',
                        executor_user=pwd.getpwuid(os.geteuid()).pw_name,fixture=True)
        self.assertEqual(len(formatted),2);timer=next(v for k,v in formatted.items() if k.endswith('.timer'));service=next(v for k,v in formatted.items() if k.endswith('.service'))
        self.assertIn(b'Persistent=false',timer);self.assertIn(b'2026-10-11 23:10:00 UTC',timer);self.assertIn(b'Restart=no',service)
        self.assertIn(b' -I -S -B ',service)
        with self.assertRaises(Hold):RuntimeGuard(p,digest(raw))
        os.chmod(source,0o600);source.write_bytes(b'# changed after acceptance\n');os.chmod(source,0o400)
        with self.assertRaisesRegex(Hold,'RUNTIME_FILE_PIN'):guard.recheck()
    def test_t05_t16_bad_runtime_review_old_epoch_or_missing_bound_refuses_acceptance(self):
        args,channel,source=self.acceptance();definition=strict(args[-1]);ref=definition['runtime_review']
        channel.rows[ref['id']]['value']['verdict']='PENDING'
        with self.assertRaisesRegex(Hold,'ACCEPTANCE_INDEPENDENT_RUNTIME_REVIEW'):build(*args,channel=channel,clock=lambda:'2026-10-11T23:08:00Z',fixture=True)
        definition['slots']['OWN_SLOT_1']['references'].pop('bound');args[-1]=canonical(definition)
        with self.assertRaisesRegex(Hold,'ACCEPTANCE_ORIGINAL_SET'):build(*args,channel=channel,clock=lambda:'2026-10-11T23:08:00Z',fixture=True)
        spec=strict(args[0]);spec['context']['session']='2026-10-09';args[0]=canonical(spec)
        with self.assertRaises(Hold):build(*args,channel=channel,clock=lambda:'2026-10-11T23:08:00Z',fixture=True)
    def test_t09_fresh_complete_observer_preserves_original_expiry_and_blocks_changed_feed(self):
        store=self.directory('observer');guard=Guard();entry={k:h(k) for k in ('producer_sha256','review_sha256','feed_producer_sha256','feed_runtime_sha256','feed_review_sha256','feed_authority_sha256')}
        _,_,_,view=envelope(guard);release=canonical({'context':CTX,'release_sha256':CTX['release_sha256']})
        p=self.file('release.json',release);entry.update(feed_name='feed.json',release_path=str(p),release_document_sha256=digest(release))
        record={'schema':'SERVER_GLOBAL_CONTROL_ORIGINAL_V2','mode':'FIXTURE','complete':True,'view':view,
                 'producer_sha256':entry['feed_producer_sha256'],'runtime_sha256':entry['feed_runtime_sha256'],
                 'review_sha256':entry['feed_review_sha256'],'authority_sha256':entry['feed_authority_sha256']}
        store.create('feed.json',canonical(record));clock=['2026-10-11T23:10:00Z'];observer=Observer(guard,store,entry,clock=lambda:clock[0])
        out=strict(observer.observe());self.assertEqual(out['view']['valid_until_UTC'],view['valid_until_UTC'])
        clock[0]='2026-10-11T23:10:06Z'
        with self.assertRaisesRegex(Hold,'GLOBAL_CONTROL_STALE'):observer.observe()
        clock[0]='2026-10-11T23:10:00Z';record['complete']=False;(self.base/'observer'/'feed.json').write_bytes(canonical(record))
        with self.assertRaisesRegex(Hold,'GLOBAL_CONTROL_NOT_ELECTED'):observer.observe()
    def test_t14_private_capsule_exact_originals_and_adversarial_members(self):
        members={'REQUEST.json':b'opaque original\n','RESULT.json':canonical({'fixture':True})};raw,pin=pack(members)
        self.assertEqual(unpack(raw),members);self.assertEqual(len(pin),64)
        with self.assertRaises(Hold):pack({'../secret':b'x'})
        with self.assertRaisesRegex(Hold,'CAPSULE_LIMIT'):pack({'huge':b'x'*MAXIMUM})
        for name,kind in (('../escape',tarfile.REGTYPE),('link',tarfile.SYMTYPE)):
            out=io.BytesIO()
            with tarfile.open(fileobj=out,mode='w') as archive:
                info=tarfile.TarInfo(name);info.type=kind;info.size=1 if kind==tarfile.REGTYPE else 0;info.linkname='outside';archive.addfile(info,io.BytesIO(b'x'))
            with self.assertRaises(Hold):unpack(out.getvalue())
    def test_t14_real_retention_failure_never_creates_complete_cipher(self):
        store=self.directory('retention');guard=Guard();guard.value['spec']['executables']['age']={'path':'/fixture/age'}
        entry={'recipient':'age1'+'x'*58,'authority_sha256':h('own retention')};request={'pins':{'retention_authority_sha256':entry['authority_sha256']}}
        class BadRunner:
            def run(_,argv,**kw):return {'returncode':1,'stdout':b'bad cipher'}
        retainer=NativeRetainer(guard,BadRunner(),store,entry)
        with self.assertRaisesRegex(Hold,'RETENTION_CIPHER_UNCERTAIN'):retainer.retain(b'fixture',{'request':{'raw':b'fixture'}},request,recheck=lambda:None)
        self.assertEqual(list((self.base/'retention').iterdir()),[])

    def test_t14_disk_full_preserves_partial_cipher_and_refuses_second_write(self):
        import errno
        store=self.directory('retention-full');guard=Guard();guard.value['spec']['executables']['age']={'path':'/fixture/age'}
        entry={'recipient':'age1'+'x'*58,'authority_sha256':h('retention disk fixture')}
        request={'pins':{'retention_authority_sha256':entry['authority_sha256']}}
        class Runner:
            calls=0
            def run(other,argv,**kw):
                other.calls+=1;return {'returncode':0,'stdout':b'age-encryption.org/v1\nFIXTURE_CIPHER'}
        runner=Runner();retainer=NativeRetainer(guard,runner,store,entry);result=b'FIXTURE result'
        with patch('common.os.write',side_effect=OSError(errno.ENOSPC,'explicit fixture disk full')):
            with self.assertRaises(OSError):retainer.retain(result,{'request':{'raw':b'FIXTURE original'}},request,recheck=lambda:None)
        path=store.path/(digest(result)+'.age');self.assertTrue(path.exists());self.assertEqual(path.stat().st_size,0)
        # Existing uncertainty is retained; the controller already consumed its
        # invocation. A direct adapter call cannot overwrite even that file.
        with self.assertRaises(FileExistsError):store.create(path.name,b'forbidden replacement')
        self.assertEqual(runner.calls,1)
    def db(self,bad=False):
        guard=Guard();dsn=b'dbname=FIXTURE_DO_NOT_CONNECT user=fixture';p=self.file('credential',dsn)
        entry={'credential_path':str(p),'credential_sha256':digest(dsn),'database':'FIXTURE_DO_NOT_CONNECT','restricted_role':'fixture',
               'expected_state_sha256':h('state'),'expected_version':1};calls=[]
        class Connection:
            rolled=closed=False
            def execute(self,sql,params=None):
                calls.append((sql,params));self.sql=sql;return self
            def fetchone(self):
                if self.sql==PRIVILEGES:return (entry['database'],'fixture','fixture','on',not bad,True,True)
                if self.sql==EPOCH:return (1,entry['expected_state_sha256'],1,CTX['release_sha256'])
                if self.sql==BINDING:return (h('capacity binding'),1)
            def rollback(self):self.rolled=True
            def close(self):self.closed=True
        connection=Connection()
        def connector(value,**options):self.assertEqual(value,dsn.decode());self.assertFalse(options['autocommit']);return connection
        return DBReader(guard,entry,connector),calls,connection
    def test_t11_t12_native_db_reader_exact_read_only_parameterized_queries_rollback(self):
        reader,calls,connection=self.db();out=reader.read(CTX,h('capacity binding'))
        self.assertTrue(out['readonly_role']);self.assertEqual([c[0] for c in calls],[BEGIN,TIMEOUT,PRIVILEGES,EPOCH,BINDING])
        self.assertEqual(calls[3][1],(CTX['epoch'],));self.assertTrue(connection.rolled and connection.closed)
        self.assertFalse(out['mutation_performed'])
    def test_t09_t12_privilege_failure_rolls_back_and_never_reads_or_writes_state(self):
        reader,calls,connection=self.db(bad=True)
        with self.assertRaisesRegex(Hold,'H16_DB_PRIVILEGES'):reader.read(CTX,h('capacity binding'))
        self.assertEqual(len(calls),3);self.assertTrue(connection.rolled and connection.closed)
    def host(self):
        guard=Guard();guard.value['spec']['executables']['systemctl']={'path':'/fixture/systemctl'}
        fragment=self.file('fragment.service',b'FIXTURE reviewed unit\n');readsource=self.file('readonly-source',b'FIXTURE source\n')
        entry={'container_id':'c'*64,'image_id':'sha256:'+h('reader image'),'argv':['/fixture/reader'],
          'labels':{'c3po.server.epoch':CTX['epoch'],'c3po.server.release_sha256':CTX['release_sha256']},
          'user':'2000:2000','network':'fixture','mounts':[{'source':'/fixture/a','destination':'/fixture/b','rw':False}],
          'readonly_sources':[{'path':str(readsource),'sha256':digest(readsource.read_bytes())}],'units':{}}
        for role in ('service','timer'):
            state={'ActiveState':'active' if role=='timer' else 'inactive','SubState':'waiting' if role=='timer' else 'dead',
                 'LoadState':'loaded','UnitFileState':'enabled','FragmentPath':str(fragment),'ExecMainStatus':'0','MainPID':'0'}
            entry['units'][role]={'name':'fixture.'+role,'expected':state,'fragment_sha256':digest(fragment.read_bytes())}
        row={'Id':entry['container_id'],'Image':entry['image_id'],'Config':{'Cmd':entry['argv'],'Labels':entry['labels'],'User':entry['user']},
             'State':{'Running':True,'Status':'running'},'RestartCount':0,
             'HostConfig':{'ReadonlyRootfs':True,'NetworkMode':'fixture','RestartPolicy':{'Name':'no'}},
             'Mounts':[{'Source':'/fixture/a','Destination':'/fixture/b','RW':False}]};calls=[]
        class Runner:
            def run(_,argv,**kw):
                calls.append(argv)
                if argv[0]=='/fixture/docker':return {'returncode':0,'stdout':canonical(row)}
                role=argv[-1].split('.')[-1];expected=entry['units'][role]['expected']
                return {'returncode':0,'stdout':('\n'.join(k+'='+expected[k] for k in UNIT_FORMAT)+'\n').encode()}
        return ReaderHost(guard,Runner(),entry),entry,row,calls
    def test_t11_t12_native_reader_host_only_inspect_show_and_pinned_fragments(self):
        reader,entry,row,calls=self.host();result=reader.read(CTX)
        self.assertFalse(result['activation_performed']);self.assertEqual(len(calls),3)
        self.assertEqual(calls[0][3],'inspect');self.assertTrue(all(c[1]=='show' for c in calls[1:]))
        row['RestartCount']=1
        with self.assertRaisesRegex(Hold,'H16_READER_IDENTITY_POSTURE'):reader.read(CTX)
    def test_t08_t11_reader_host_missing_component_or_writable_mount_holds(self):
        reader,entry,row,calls=self.host();entry['units'].pop('timer')
        with self.assertRaisesRegex(Hold,'H16_READER_COMPONENT_SET'):reader.read(CTX)
        row['Mounts'][0]['RW']=True
        with self.assertRaisesRegex(Hold,'H16_READER_MOUNTS'):reader.read(CTX)


if __name__=='__main__':unittest.main()
