"""The reader units (MASTER_PLAN row B2) on the emulated host: the templates and the render, every refusal of the plan,
every refusal of the precheck with the host unchanged, the creation, its readback, the continuation over units signed
as present, and what each failure of an effect leaves. Tests named "static" pin bytes; the others judge behaviour."""
import errno
import json
import re

import pytest

import family as f
import hostemu
import ru
import unit_texts

K=ru.K
SERVICE,TIMER,ALERT=(name for _,name in ru.NAMES)
HOST_SOURCE='/var/lib/c3po/r2d2-v2-source-20261005'
IMAGE='sha256:f86bfb198c186657598c2c410fb39ca3dfed781d0db0522b9a796b80275cb621'

def run(docs,host,**options):return docs.chain().run(host,**options)
def plan_refusal(change):
    docs,host=ru.case();change(docs.plan,host);docs.chain()
    return f.refusal(docs.authenticate)
def refused_unchanged(docs,host,code,**options):
    before=ru.state_of(host);receipt=run(docs,host,**options)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED','REFUSED_NOTHING_CREATED',code),(receipt['code'],receipt['outcome'])
    assert ru.state_of(host)==before and receipt['mutating_calls']['issued']==0 and host.fds=={} and f.sealed(receipt)
    assert not host.mutating() and not host.commands
    return receipt
def text_of(key):return K().m.rendered_units()[key].decode('ascii')


# ---------------------------------------------------------------- templates and render
def test_static_templates_are_the_readme_bytes_and_the_service_differs_by_exactly_two_insertions():
    m=K().m
    assert m.READER_TIMER_TEMPLATE==unit_texts.README_TIMER and m.READER_ALERT_TEMPLATE==unit_texts.README_ALERT
    assert f.sha(unit_texts.README_SERVICE)==m.README_SERVICE_SHA256=='8d2ff7a91b94e39b8c7a0e91fae34b16dbc9d55f7af407b8464486a9bd064fab'
    readme=unit_texts.README_SERVICE.decode('ascii').split('\n');mine=m.READER_SERVICE_TEMPLATE.decode('ascii').split('\n')
    assert len(mine)==len(readme)+1
    changed=[(a,b) for a,b in zip(readme,mine) if a!=b]
    assert changed[0]==('RequiresMountsFor=@HOST_DATA_ROOT@ @HOST_JOURNAL_ROOT@ @HOST_CAPACITY_ROOT@ @HOST_CONFIG_DIR@',
                        'RequiresMountsFor=@HOST_DATA_ROOT@ @HOST_JOURNAL_ROOT@ @HOST_CAPACITY_ROOT@ @HOST_SOURCE_ROOT@ @HOST_CONFIG_DIR@')
    inserted='  --mount type=bind,source=@HOST_SOURCE_ROOT@,target=@CONTAINER_SOURCE_ROOT@,readonly \\'
    at=mine.index(inserted);assert mine[:at]!=readme[:at] and mine[at+1:]==readme[at:]
    assert mine[at-1]=='  --mount type=bind,source=@HOST_CAPACITY_ROOT@,target=/c3po-capacity,readonly \\'
    assert [f.sha(m.READER_SERVICE_TEMPLATE),f.sha(m.READER_TIMER_TEMPLATE),f.sha(m.READER_ALERT_TEMPLATE)]==[
        m.READER_SERVICE_TEMPLATE_SHA256,m.READER_TIMER_TEMPLATE_SHA256,m.READER_ALERT_TEMPLATE_SHA256]
    assert m.TEMPLATE_REVISION=='4a6f7675b8e418e0e7ee55a446250815f3bd5562'

def test_static_rendered_hashes_and_sizes():
    done=K().m.rendered_units()
    assert {key:(f.sha(raw),len(raw)) for key,raw in done.items()}==RENDERED

RENDERED={'READER_SERVICE':('1a01a7d7eb6cede1ca4d406278fa03e4beabd86231a7dfacc5556ab92139aace',2108),'READER_TIMER':('dc81e21bfc2398330dd7eff02cbc8cf8d0e035bce883653cab4b10a1078ed4ba',289),
          'READER_ALERT':('0653bf416e77c5b69d66e4952468380e89b2a79d1cc38c40509332ae015cce2f',414)}

def test_rendered_service_holds_the_values_of_this_epoch():
    service=text_of('READER_SERVICE');lines=service.split('\n')
    assert 'RequiresMountsFor=/mnt/day-d-data /var/lib/c3po-bar/journal /var/lib/c3po-capacity '+HOST_SOURCE+' /etc/c3po-reader' in lines
    assert 'Environment=DOCKER_CONFIG=/etc/c3po-reader/docker-cli' in lines
    assert [line for line in lines if line.startswith('ExecCondition=')]==['ExecCondition=/usr/bin/test -f /etc/c3po-reader/'+name
                                                                        for name in ('secret.env','pins.env','activation.env')]
    assert 'ExecStartPre=/usr/bin/docker image inspect --format {{.Id}} '+IMAGE in lines
    assert '  --user 0:0 --workdir /app --network c3po_c3po_internal \\' in lines
    assert [line for line in lines if '--env-file' in line]==['  --env-file /etc/c3po-reader/%s \\'%name for name in ('secret.env','pins.env','activation.env')]
    assert [line for line in lines if '--mount' in line]==[
        '  --mount type=bind,source=/mnt/day-d-data,target=/app/day-d-data,readonly \\',
        '  --mount type=bind,source=/var/lib/c3po-bar/journal,target=/c3po-bar-journal,readonly \\',
        '  --mount type=bind,source=/var/lib/c3po-capacity,target=/c3po-capacity,readonly \\',
        '  --mount type=bind,source='+HOST_SOURCE+',target=/c3po-source,readonly \\',
        '  --mount type=bind,source=/etc/c3po-reader/launcher,target=/c3po-reader,readonly \\']
    assert lines[lines.index('  python -I -B /c3po-reader/reader_launcher.py')-1]=='  '+IMAGE+' \\'
    assert service.count(IMAGE)==2 and '@' not in service and service.count('c3po_c3po_internal')==1
    assert 'OnFailure=c3po-reader-alert.service' in lines and service.endswith('SyslogIdentifier=c3po-reader\n')

def test_rendered_service_meets_the_unit_guards_of_the_reader_switch_and_of_pins():
    """K13 (unit_text_checks: each bind exactly once, every --mount counted, the image twice, no '@'; the producer's
    journal bind and argument) and K4 PINS (bind_source: the source of the one bind of each target), with the source
    root of decision 6 added to K13's four pairs."""
    service=text_of('READER_SERVICE').encode('ascii');producer=ru.producer_bytes()
    pairs=[('/mnt/day-d-data','/app/day-d-data'),('/var/lib/c3po-bar/journal','/c3po-bar-journal'),('/var/lib/c3po-capacity','/c3po-capacity'),
           (HOST_SOURCE,'/c3po-source'),('/etc/c3po-reader/launcher','/c3po-reader')]
    assert all(service.count(('  --mount type=bind,source=%s,target=%s,readonly \\\n'%pair).encode())==1 for pair in pairs)
    assert service.count(b'--mount ')==len(pairs) and service.count(IMAGE.encode())==2 and b'@' not in service
    assert producer.count(b'  --mount type=bind,source=/var/lib/c3po-bar/journal,target=/c3po-bar-journal \\\n')==1
    assert producer.count(b' --journal-root /c3po-bar-journal ')==1 and producer.count(IMAGE.encode())==2
    def bind_source(unit,target,suffix):
        found=re.findall(r'(?m)^  --mount type=bind,source=(/[A-Za-z0-9._/-]+),target='+re.escape(target)+re.escape(suffix)+r' \\$',unit)
        return found[0] if len(found)==1 else None
    unit=service.decode()
    assert [bind_source(unit,target,',readonly') for target in ('/c3po-bar-journal','/c3po-source','/c3po-capacity','/c3po-reader')]==[
        '/var/lib/c3po-bar/journal',HOST_SOURCE,'/var/lib/c3po-capacity','/etc/c3po-reader/launcher']
    assert bind_source(producer.decode(),'/c3po-bar-journal','')=='/var/lib/c3po-bar/journal'

def test_timer_and_alert_are_the_readme_units_verbatim():
    done=K().m.rendered_units()
    assert done['READER_TIMER']==unit_texts.README_TIMER and done['READER_ALERT']==unit_texts.README_ALERT
    assert b'Unit=c3po-reader.service\n' in done['READER_TIMER'] and b'/var/lib/c3po-reader/failed.' in done['READER_ALERT']

def values(**changes):
    out=dict(K().m.READER_VALUES);out.update(changes);return out
RENDER_REFUSALS=[
    ({'HOST_DATA_ROOT':'mnt/day-d-data'},'PATH_INVALID'),({'HOST_JOURNAL_ROOT':'/var/lib/c3po-bar/journal/'},'PATH_INVALID'),
    ({'HOST_CAPACITY_ROOT':'/var/lib/../c3po-capacity'},'PATH_INVALID'),({'HOST_SOURCE_ROOT':'/'},'PATH_INVALID'),
    ({'HOST_CONFIG_DIR':'/etc/c3po reader'},'PATH_INVALID'),({'HOST_CONFIG_DIR':'/etc/c3po=reader'},'PATH_INVALID'),
    ({'HOST_SOURCE_ROOT':'/var/lib//c3po'},'PATH_INVALID'),
    ({'CONTAINER_JOURNAL_ROOT':'/app/day-d-data/journal'},'CONTAINER_TARGET_INVALID'),({'CONTAINER_SOURCE_ROOT':'/etc'},'CONTAINER_TARGET_INVALID'),
    ({'CONTAINER_SOURCE_ROOT':'/c3po-a/b'},'CONTAINER_TARGET_INVALID'),({'CONTAINER_JOURNAL_ROOT':'/c3po-'},'CONTAINER_TARGET_INVALID'),
    ({'CONTAINER_SOURCE_ROOT':'/c3po-capacity'},'CONTAINER_TARGETS_NOT_DISTINCT'),({'CONTAINER_JOURNAL_ROOT':'/c3po-reader'},'CONTAINER_TARGETS_NOT_DISTINCT'),
    ({'CONTAINER_SOURCE_ROOT':'/c3po-bar-journal'},'CONTAINER_TARGETS_NOT_DISTINCT'),
    ({'IMAGE_ID':'c3po/backend:production'},'IMAGE_ID_INVALID'),({'IMAGE_ID':'sha256:'+'F'*64},'IMAGE_ID_INVALID'),
    ({'NETWORK':'host'},'NETWORK_FORBIDDEN'),({'NETWORK':'none'},'NETWORK_FORBIDDEN'),({'NETWORK':'bridge'},'NETWORK_FORBIDDEN'),
    ({'NETWORK':'container:c3po-db-1'},'NETWORK_FORBIDDEN'),({'NETWORK':'-x'},'NETWORK_FORBIDDEN'),
    ({'HOST_CONFIG_DIR':'/mnt/day-d-data/reader'},'CONFIG_DIRECTORY_OVERLAPS_A_BIND_SOURCE'),
    ({'HOST_CONFIG_DIR':'/var/lib/c3po-capacity/reader'},'CONFIG_DIRECTORY_OVERLAPS_A_BIND_SOURCE'),
    ({'HOST_CONFIG_DIR':'/var/lib/c3po-bar/journal/reader'},'CONFIG_DIRECTORY_OVERLAPS_A_BIND_SOURCE'),
    ({'HOST_CONFIG_DIR':HOST_SOURCE+'/reader'},'CONFIG_DIRECTORY_OVERLAPS_A_BIND_SOURCE'),
    ({'HOST_CONFIG_DIR':'/var/lib'},'CONFIG_DIRECTORY_OVERLAPS_A_BIND_SOURCE'),
    ({'HOST_JOURNAL_ROOT':'/mnt/day-d-data/journal'},'HOST_JOURNAL_OVERLAPS_A_BIND_SOURCE'),
    ({'HOST_JOURNAL_ROOT':'/var/lib/c3po-capacity'},'HOST_JOURNAL_OVERLAPS_A_BIND_SOURCE'),
    ({'HOST_JOURNAL_ROOT':HOST_SOURCE+'/journal'},'HOST_JOURNAL_OVERLAPS_A_BIND_SOURCE'),
    ({'HOST_SOURCE_ROOT':'/mnt/day-d-data/r2d2-v2-source-20261005'},'SOURCE_ROOT_OVERLAPS_A_BIND_SOURCE'),
    ({'HOST_SOURCE_ROOT':'/var/lib/c3po-capacity/source'},'SOURCE_ROOT_OVERLAPS_A_BIND_SOURCE'),
    ({'HOST_CAPACITY_ROOT':'/mnt/day-d-data/capacity'},'CAPACITY_ROOT_OVERLAPS_THE_DATA_VOLUME'),
    ({'HOST_CAPACITY_ROOT':'/mnt'},'CAPACITY_ROOT_OVERLAPS_THE_DATA_VOLUME'),
]
@pytest.mark.parametrize('changes,code',RENDER_REFUSALS)
def test_render_refuses_every_value_outside_the_readme_grammar_and_rules(changes,code):
    m=K().m;assert f.refusal(lambda:m.render_service(m.READER_SERVICE_TEMPLATE,values(**changes)))==code

def test_render_refuses_a_template_that_is_not_the_counted_one():
    m=K().m;template=m.READER_SERVICE_TEMPLATE
    cases=[(template+b'# 100%\n','TEMPLATE_CHARACTERS'),(template+b'X=$HOME\n','TEMPLATE_CHARACTERS'),(template+b'X="a"\n','TEMPLATE_CHARACTERS'),
           (template+b"X='a'\n",'TEMPLATE_CHARACTERS'),(template+b'X=a;b\n','TEMPLATE_CHARACTERS'),(template+b'X=\xc3\xa9\n','TEMPLATE_CHARACTERS'),
           (template+b'X=a\tb\n','TEMPLATE_CHARACTERS'),('text','TEMPLATE_CHARACTERS'),
           (template+b'X=@NETWORK@\n','PLACEHOLDER_COUNTS'),(template.replace(b' @HOST_SOURCE_ROOT@ @HOST_CONFIG_DIR@',b' @HOST_CONFIG_DIR@'),'PLACEHOLDER_COUNTS'),
           (template+b'X=@OTHER@\n','PLACEHOLDER_COUNTS'),
           (template+b'X=user@host\n','UNRESOLVED_PLACEHOLDER'),(template+b'#'*16384+b'\n','RENDER_TOO_LARGE')]
    for raw,code in cases:assert f.refusal(lambda:m.render_service(raw,values()))==code,code
    extra=values();extra['OTHER']='/x'
    assert f.refusal(lambda:m.render_service(template,extra))=='SUBSTITUTION_KEYS'
    missing=values();del missing['NETWORK'];assert f.refusal(lambda:m.render_service(template,missing))=='SUBSTITUTION_KEYS'
    wrong=values();wrong['NETWORK']=1;assert f.refusal(lambda:m.render_service(template,wrong))=='SUBSTITUTION_KEYS'
    assert f.refusal(lambda:m.render_service(template,None))=='SUBSTITUTION_KEYS'

def test_verbatim_units_carry_no_placeholder_sign():
    m=K().m
    for raw in (m.READER_TIMER_TEMPLATE+b'X=a@b\n',b'',m.READER_TIMER_TEMPLATE+b'\xc3\xa9',m.READER_TIMER_TEMPLATE+b'#'*16384,'text'):
        assert f.refusal(lambda:m.verbatim(raw))=='VERBATIM_TEMPLATE_INVALID'
    assert m.verbatim(m.READER_TIMER_TEMPLATE)==m.READER_TIMER_TEMPLATE

def test_rendered_units_refuses_a_template_whose_hash_is_not_the_pinned_one(monkeypatch):
    m=K().m
    for name in ('READER_SERVICE_TEMPLATE','READER_TIMER_TEMPLATE','READER_ALERT_TEMPLATE'):
        with monkeypatch.context() as patch:
            patch.setattr(m,name,getattr(m,name)+b'\n');assert f.refusal(m.rendered_units)=='TEMPLATE_HASH_MISMATCH'

def test_placement_findings_judge_the_journal_against_the_producer_private_roots():
    m=K().m
    assert m.placement_findings(values(),['/var/lib/c3po-bar/supervisor','/etc/c3po-bar'])==[]
    assert m.placement_findings(values(),['/var/lib/c3po-bar/journal/state'])==['HOST_JOURNAL_OVERLAPS_A_PRODUCER_PRIVATE_ROOT']
    assert m.placement_findings(values(),['/var/lib/c3po-bar'])==['HOST_JOURNAL_OVERLAPS_A_PRODUCER_PRIVATE_ROOT']
    assert m.placement_findings(values(),['/var/lib/c3po-bar/journal'])==[]
    assert m.placement_findings(values(HOST_CONFIG_DIR='/mnt/day-d-data/x',CONTAINER_SOURCE_ROOT='/c3po-reader'))==[
        'CONFIG_DIRECTORY_OVERLAPS_A_BIND_SOURCE','CONTAINER_TARGETS_NOT_DISTINCT']

def test_producer_facts_read_the_journal_bind_and_the_image_from_the_installed_bytes():
    m=K().m;raw=ru.producer_bytes()
    assert m.producer_facts(raw)=={'journal_source':'/var/lib/c3po-bar/journal','journal_target':'/c3po-bar-journal','image_id':IMAGE,
                                   'other_sources':['/etc/c3po-bar','/var/lib/c3po-bar/supervisor']}
    line=b'  --mount type=bind,source=/var/lib/c3po-bar/journal,target=/c3po-bar-journal \\\n'
    bad=[raw.replace(line,line.replace(b' \\',b',readonly \\')),raw.replace(b'--journal-root /c3po-bar-journal ',b'--journal-root /c3po-other '),
         raw.replace(b' --manifest-directory',b' --journal-root /c3po-bar-journal --manifest-directory'),
         raw.replace(IMAGE.encode()+b' \\',b'sha256:'+b'1'*64+b' \\'),raw.replace(line,b''),raw+b'X=\xc3\xa9\n',
         raw.replace(line,line+line),raw.replace(line,b'  --mount type=volume,source=x,target=/c3po-bar-journal \\\n'),
         raw.replace(b'ExecStartPre=/usr/bin/docker image inspect --format {{.Id}} '+IMAGE.encode(),b'ExecStartPre=/bin/true'),'text']
    for item in bad:assert f.refusal(lambda:m.producer_facts(item))=='PRODUCER_UNIT_NOT_AS_SIGNED'


# ---------------------------------------------------------------- plan refusals (validate_plan, also the dispatcher's)
def rows_set(member,index,**changes):
    def change(plan,host):plan[member][index].update(changes)
    return change
def unit_set(index,**changes):
    def change(plan,host):plan['units'][index].update(changes)
    return change
PLAN_REFUSALS=[
    ('unit rows of another path',lambda p,h:p.update(unit_rows=hostemu.rows(h,'/etc/systemd')),'CHAIN_ROW_INVALID'),
    ('unit rows missing',lambda p,h:p.update(unit_rows=None),'CHAIN_ROW_INVALID'),
    ('unit directory owned by 1000',rows_set('unit_rows',3,uid=1000),'CHAIN_ROW_UNSAFE'),
    ('/etc group-writable',rows_set('unit_rows',1,mode=0o775),'CHAIN_ROW_UNSAFE'),
    ('unit directory group 1000',rows_set('unit_rows',3,gid=1000),'UNIT_CHAIN_NOT_ROOT_CONTROLLED'),
    ('/etc setgid',rows_set('unit_rows',1,mode=0o2755),'UNIT_CHAIN_NOT_ROOT_CONTROLLED'),
    ('unit directory setgid',rows_set('unit_rows',3,mode=0o2755),'PARENT_SETGID'),
    ('journal rows of the parent',lambda p,h:p.update(journal_rows=hostemu.rows(h,'/var/lib/c3po-bar')),'CHAIN_ROW_INVALID'),
    ('journal owned by 1000',rows_set('journal_rows',4,uid=1000),'CHAIN_ROW_UNSAFE'),
    ('/var/lib group 1000',rows_set('journal_rows',2,gid=1000),'JOURNAL_CHAIN_NOT_ROOT_CONTROLLED'),
    ('journal root 0750',rows_set('journal_rows',4,mode=0o750),'JOURNAL_ROOT_NOT_PRIVATE'),
    ('journal root 0755',rows_set('journal_rows',4,mode=0o755),'JOURNAL_ROOT_NOT_PRIVATE'),
    ('journal root group 0, but 0711',rows_set('journal_rows',4,mode=0o711),'JOURNAL_ROOT_NOT_PRIVATE'),
    ('data rows of /mnt',lambda p,h:p.update(data_rows=hostemu.rows(h,'/mnt')),'CHAIN_ROW_INVALID'),
    ('data volume writable by anyone',rows_set('data_rows',2,mode=0o777),'CHAIN_ROW_WORLD_WRITABLE'),
    ('/mnt owned by 1000',rows_set('data_rows',1,uid=1000),'CHAIN_ROW_UNSAFE'),
    ('data volume not a mount point',rows_set('data_rows',2,device=hostemu.ROOT_DEVICE),'DATA_VOLUME_NOT_A_MOUNT_POINT'),
    ('journal on the data volume device',lambda p,h:[row.update(device=hostemu.DATA_DEVICE) for row in p['journal_rows'][3:]],'JOURNAL_ON_THE_DATA_VOLUME'),
    ('boot unbound',lambda p,h:p.update(evidence_boot_id_sha256=None),'EVIDENCE_BOOT_UNBOUND'),
    ('boot zero',lambda p,h:p.update(evidence_boot_id_sha256='0'*64),'EVIDENCE_BOOT_UNBOUND'),
    ('units not a list',lambda p,h:p.update(units={}),'UNITS_INVALID'),
    ('two units',lambda p,h:p['units'].pop(),'UNITS_INVALID'),
    ('four units',lambda p,h:p['units'].append(dict(p['units'][0])),'UNITS_INVALID'),
    ('unit with a mode',unit_set(0,mode=420),'UNITS_INVALID'),
    ('unit not a dict',lambda p,h:p['units'].__setitem__(1,'c3po-reader.timer'),'UNITS_INVALID'),
    ('units in another order',lambda p,h:p['units'].reverse(),'UNIT_NAME_INVALID'),
    ('another name',unit_set(1,destination_name='c3po-reader2.timer'),'UNIT_NAME_INVALID'),
    ('another key',unit_set(2,key='READER_ALARM'),'UNIT_NAME_INVALID'),
    ('expect null',unit_set(0,expect=None),'EXPECT_INVALID'),
    ('expect PRESENT word',unit_set(0,expect='PRESENT'),'EXPECT_INVALID'),
    ('expect without links',unit_set(0,expect={'device':1,'inode':2}),'EXPECT_INVALID'),
    ('expect inode zero',unit_set(0,expect={'device':1,'inode':0,'links':1}),'EXPECT_INVALID'),
    ('expect three links',unit_set(0,expect={'device':1,'inode':2,'links':3}),'EXPECT_INVALID'),
    ('expect device negative',unit_set(0,expect={'device':-1,'inode':2,'links':1}),'EXPECT_INVALID'),
    ('expect links a bool',unit_set(0,expect={'device':1,'inode':2,'links':True}),'EXPECT_INVALID'),
    ('rendered hash of another unit',lambda p,h:p['units'][0].update(rendered_sha256=p['units'][1]['rendered_sha256']),'RENDERED_HASH_MISMATCH'),
    ('rendered size one less',lambda p,h:p['units'][2].update(rendered_bytes=p['units'][2]['rendered_bytes']-1),'RENDERED_HASH_MISMATCH'),
    ('nothing to create',lambda p,h:[unit.update(expect={'device':1,'inode':2+index,'links':1}) for index,unit in enumerate(p['units'])],'NOTHING_TO_CREATE'),
    ('leftovers null',lambda p,h:p.update(acknowledged_leftovers=None),'LEFTOVERS_INVALID'),
    ('leftover of another pattern',lambda p,h:p.update(acknowledged_leftovers=[{'name':'.hostops-x.partial','device':1,'inode':2}]),'LEFTOVERS_INVALID'),
    ('leftover without identity',lambda p,h:p.update(acknowledged_leftovers=[{'name':'.hostops-'+'a'*16+'-0.partial'}]),'LEFTOVERS_INVALID'),
    ('leftover inode zero',lambda p,h:p.update(acknowledged_leftovers=[{'name':'.hostops-'+'a'*16+'-0.partial','device':1,'inode':0}]),'LEFTOVERS_INVALID'),
    ('leftover twice',lambda p,h:p.update(acknowledged_leftovers=[{'name':'.hostops-'+'a'*16+'-0.partial','device':1,'inode':2}]*2),'LEFTOVERS_INVALID'),
    ('seventeen leftovers',lambda p,h:p.update(acknowledged_leftovers=[{'name':'.hostops-%016x-0.partial'%n,'device':1,'inode':2} for n in range(17)]),'LEFTOVERS_INVALID'),
    ('leftover not a dict',lambda p,h:p.update(acknowledged_leftovers=['.hostops-'+'a'*16+'-0.partial']),'LEFTOVERS_INVALID'),
]
@pytest.mark.parametrize('label,change,code',PLAN_REFUSALS,ids=[row[0] for row in PLAN_REFUSALS])
def test_every_plan_refusal_comes_from_the_bytes(label,change,code):
    assert plan_refusal(change)==code

def test_sixteen_acknowledged_leftovers_and_units_signed_present_are_valid_plans():
    docs,host=ru.case();docs.plan['acknowledged_leftovers']=[{'name':'.hostops-%016x-1.partial'%n,'device':1,'inode':2} for n in range(16)]
    docs.plan['units'][0]['expect']={'device':1,'inode':2,'links':2};docs.chain();docs.authenticate()


# ---------------------------------------------------------------- the complete run
def test_complete_run_installs_the_three_units_exactly_and_changes_nothing_else():
    docs,host=ru.case();before=set(host.tree.paths());receipt=run(docs,host);done=K().m.rendered_units()
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED',None)
    assert f.sealed(receipt) and receipt['activation_performed'] is False and receipt['daemon_reload_performed'] is False and receipt['readback']=='COMPLETE'
    assert set(host.tree.paths())-before=={ru.UNITS+'/'+name for _,name in ru.NAMES}
    for key,name in ru.NAMES:
        node=host.tree.get(ru.UNITS+'/'+name)
        assert (node.kind,node.uid,node.gid,node.mode,node.nlink,bytes(node.content),node.dev)==('file',0,0,0o644,1,done[key],hostemu.ROOT_DEVICE)
    assert [row['state'] for row in receipt['ledger']]==['INSTALLED_DURABLE']*3 and receipt['objects_left_by_this_run']==3
    assert [row['sha256_observed'] for row in receipt['ledger']]==[f.sha(done[key]) for key,_ in ru.NAMES]
    assert [row['temporary_name'] for row in receipt['ledger']]==['.hostops-%s-%d.partial'%(docs.go16(),index) for index in range(3)]
    assert receipt['mutating_calls']=={'issued':12,'succeeded':12,'failed_nothing_changed':0,'uncertain':0}
    changes=[entry[:2] for entry in host.log if entry[0] in hostemu.MUTATING]
    temporaries=[ru.UNITS+'/.hostops-%s-%d.partial'%(docs.go16(),index) for index in range(3)]
    assert changes==[item for index,(_,name) in enumerate(ru.NAMES) for item in
                     (('create',temporaries[index]),('write',temporaries[index]),('link',temporaries[index]),('unlink',ru.UNITS+'/'+temporaries[index].rsplit('/',1)[1]))]
    assert [entry[1] for entry in host.log if entry[0]=='umask']==[0o022]
    assert not host.commands and host.fds=={} and receipt['external_processes']==0
    assert receipt['producer']['sha256']==unit_texts.PRODUCER_RENDER_SHA256 and receipt['producer']['image_id']==IMAGE
    assert receipt['catalog']=={'epoch.json':{'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1},
                                'maintenance.lock':{'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1}}
    assert receipt['daemon_reload_owner']=='GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01' and receipt['pre_existing_objects_modified'] is False
    assert receipt['precheck']['seconds_left_before_first_effect']>=15 and receipt['precheck']['conflicts']['status']=='COMPLETE'
    assert [row['state'] for row in receipt['precheck']['units']]==['OK_ABSENT']*3
    assert len(f.line(receipt))<60000

def test_nothing_of_the_catalogue_or_the_data_volume_is_opened_as_a_file():
    docs,host=ru.case();run(docs,host)
    opened=[entry[1] for entry in host.log if entry[0]=='open']
    assert not [path for path in opened if path.startswith(ru.JOURNAL+'/') or path.startswith(ru.DATA+'/')]
    reads=[entry[1] for entry in host.log if entry[0]=='read']
    assert set(reads)=={'/proc/sys/kernel/random/boot_id',ru.PRODUCER_PATH}|{ru.UNITS+'/'+name for _,name in ru.NAMES}

def test_effects_show_what_is_installed_with_which_values_and_who_reloads():
    docs,_=ru.case();m=K().m;effects=m.effects_of(docs.plan);done=m.rendered_units()
    assert effects['units']==[{'destination_name':name,'mode_octal':'0644','uid':0,'gid':0,'rendered_sha256':f.sha(done[key]),'rendered_bytes':len(done[key]),
                               'expect':'ABSENT'} for key,name in ru.NAMES]
    assert effects['files_to_create']==3 and effects['values']==m.READER_VALUES and effects['values']['HOST_SOURCE_ROOT']==HOST_SOURCE
    assert effects['values']['NETWORK']=='c3po_c3po_internal' and effects['values']['CONTAINER_SOURCE_ROOT']=='/c3po-source'
    assert effects['daemon_reload']=={'performed_by_this_operation':False,'owner':'GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01'}
    assert effects['producer_unit']=={'path':ru.PRODUCER_PATH,'sha256':unit_texts.PRODUCER_RENDER_SHA256,'bytes':1674,'read_only':True}
    assert effects['directory']['path']==ru.UNITS and effects['journal']['path']==ru.JOURNAL and effects['data_volume']['mount_point_by_device_change']==ru.DATA
    assert (effects['activation'],effects['external_processes'],effects['pre_existing_objects_modified'])==(False,0,False)
    assert effects['epoch']=='R2D2-V2-SHADOW-2026-10-05' and effects['template_revision']=='4a6f7675b8e418e0e7ee55a446250815f3bd5562'
    docs.plan['units'][1]['expect']={'device':1,'inode':2,'links':1};docs.plan['acknowledged_leftovers']=[{'name':'.hostops-'+'b'*16+'-1.partial','device':1,'inode':3}]
    effects=m.effects_of(docs.plan)
    assert [unit['expect'] for unit in effects['units']]==['ABSENT','PRESENT','ABSENT'] and effects['files_to_create']==2
    assert effects['acknowledged_leftovers']==['.hostops-'+'b'*16+'-1.partial']

def test_scope_names_the_evidence_the_dates_and_the_flags():
    m=K().m
    assert m.EVIDENCE_OPERATIONS==('GO_READONLY_HOSTOPS_PRECHECK_01','GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01','GO_READONLY_SUPERVISOR_READBACK_01',
                                   'GO_WRITE_HOSTOPS02_CATALOG_INIT_01')
    assert m.DATES==('2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10')
    assert (m.WRITES_ALLOWED,m.ACTIVATION_ALLOWED,m.MAX_GATE_SPAN_SECONDS,m.EVIDENCE_REQUIRED)==(True,False,900,True)
    assert m.SCOPE['values']==m.READER_VALUES and m.SCOPE['daemon_reload']['performed_by_this_operation'] is False
    assert m.SCOPE['catalog']['files']==['epoch.json','maintenance.lock'] and m.SCOPE['external_processes']==0
    assert 'daemon-reload' in m.SCOPE['never'] and 'systemctl' in m.SCOPE['never'] and 'start' in m.SCOPE['never']
    assert [unit['rendered_sha256'] for unit in m.SCOPE['units']]==[f.sha(m.rendered_units()[key]) for key,_ in ru.NAMES]
    assert m.SCOPE['limits']['write_allowance_seconds']==15 and m.SCOPE['every_file']['mode_octal']=='0644'


# ---------------------------------------------------------------- precheck refusals: nothing changes
def symlink(path):
    def setup(host):host.tree.remove(path);host.tree.add(path,kind='symlink',mode=0o777)
    return setup
def node(path,**changes):
    def setup(host):
        for key,value in changes.items():setattr(host.tree.get(path),key,bytearray(value) if key=='content' else value)
    return setup
def add(path,**attributes):
    def setup(host):host.tree.add(path,**attributes)
    return setup
def remove(path):
    def setup(host):host.tree.remove(path)
    return setup
def foreign(name,**attributes):
    def setup(host):host.tree.add(ru.UNITS+'/'+name,kind='file',mode=attributes.pop('mode',0o644),content=attributes.pop('content',b'[Unit]\nX=1\n'),**attributes)
    return setup
def equal(key,**attributes):
    def setup(host):
        name=dict(ru.NAMES)[key];host.tree.add(ru.UNITS+'/'+name,kind='file',mode=attributes.pop('mode',0o644),content=K().m.rendered_units()[key],**attributes)
    return setup
PRODUCER_TEXT=None
PRECHECK_REFUSALS=[
    ('producer unit absent',remove(ru.PRODUCER_PATH),'PRODUCER_UNIT_ABSENT'),
    ('producer unit other bytes',node(ru.PRODUCER_PATH,content=b'[Unit]\n'),'PRODUCER_UNIT_NOT_AS_SIGNED'),
    ('producer unit one byte more',lambda host:host.tree.get(ru.PRODUCER_PATH).content.extend(b'\n'),'PRODUCER_UNIT_NOT_AS_SIGNED'),
    ('producer unit 0600',node(ru.PRODUCER_PATH,mode=0o600),'PRODUCER_UNIT_NOT_AS_SIGNED'),
    ('producer unit 0664',node(ru.PRODUCER_PATH,mode=0o664),'PRODUCER_UNIT_NOT_AS_SIGNED'),
    ('producer unit owned by 1000',node(ru.PRODUCER_PATH,uid=1000),'PRODUCER_UNIT_NOT_AS_SIGNED'),
    ('producer unit group 1000',node(ru.PRODUCER_PATH,gid=1000),'PRODUCER_UNIT_NOT_AS_SIGNED'),
    ('producer unit two links',node(ru.PRODUCER_PATH,nlink=2),'PRODUCER_UNIT_NOT_AS_SIGNED'),
    ('producer unit a link',symlink(ru.PRODUCER_PATH),'PRODUCER_UNIT_NOT_AS_SIGNED'),
    ('producer unit a directory',lambda host:(host.tree.remove(ru.PRODUCER_PATH),host.tree.add(ru.PRODUCER_PATH)),'PRODUCER_UNIT_NOT_AS_SIGNED'),
    ('unit directory replaced',node(ru.UNITS,ino=99),'PARENT_IDENTITY_MISMATCH'),
    ('journal root replaced',node(ru.JOURNAL,ino=98),'PARENT_IDENTITY_MISMATCH'),
    ('journal root now 0755',node(ru.JOURNAL,mode=0o755),'PARENT_IDENTITY_MISMATCH'),
    ('journal root a link',symlink(ru.JOURNAL),'PARENT_SYMLINK_COMPONENT'),
    ('journal root absent',remove(ru.JOURNAL),'PARENT_MISSING'),
    ('data volume replaced',node(ru.DATA,ino=97),'PARENT_IDENTITY_MISMATCH'),
    ('catalogue absent',lambda host:(host.tree.remove(ru.JOURNAL+'/epoch.json'),host.tree.remove(ru.JOURNAL+'/maintenance.lock')),'CATALOG_NOT_INITIALISED'),
    ('epoch file absent',remove(ru.JOURNAL+'/epoch.json'),'CATALOG_NOT_INITIALISED'),
    ('catalogue lock absent',remove(ru.JOURNAL+'/maintenance.lock'),'CATALOG_NOT_INITIALISED'),
    ('epoch file 0644',node(ru.JOURNAL+'/epoch.json',mode=0o644),'CATALOG_FILE_NOT_PRIVATE'),
    ('epoch file owned by 1000',node(ru.JOURNAL+'/epoch.json',uid=1000),'CATALOG_FILE_NOT_PRIVATE'),
    ('epoch file group 1000',node(ru.JOURNAL+'/epoch.json',gid=1000),'CATALOG_FILE_NOT_PRIVATE'),
    ('epoch file two links',node(ru.JOURNAL+'/epoch.json',nlink=2),'CATALOG_FILE_NOT_PRIVATE'),
    ('epoch file a link',symlink(ru.JOURNAL+'/epoch.json'),'CATALOG_FILE_NOT_PRIVATE'),
    ('catalogue lock a directory',lambda host:(host.tree.remove(ru.JOURNAL+'/maintenance.lock'),host.tree.add(ru.JOURNAL+'/maintenance.lock',mode=0o600)),'CATALOG_FILE_NOT_PRIVATE'),
    ('catalogue lock 0640',node(ru.JOURNAL+'/maintenance.lock',mode=0o640),'CATALOG_FILE_NOT_PRIVATE'),
    ('service name holds a directory',add(ru.UNITS+'/'+SERVICE),'UNIT_NAME_OCCUPIED'),
    ('timer name holds a link',add(ru.UNITS+'/'+TIMER,kind='symlink',mode=0o777),'UNIT_NAME_OCCUPIED'),
    ('alert name holds a fifo',add(ru.UNITS+'/'+ALERT,kind='fifo',mode=0o644),'UNIT_NAME_OCCUPIED'),
    ('service name holds another unit',foreign(SERVICE),'UNIT_PRESENT_FOREIGN_CONTENT'),
    ('timer equal bytes but 0600',equal('READER_TIMER',mode=0o600),'UNIT_PRESENT_FOREIGN_CONTENT'),
    ('alert equal bytes owned by 1000',equal('READER_ALERT',uid=1000),'UNIT_PRESENT_FOREIGN_CONTENT'),
    ('alert equal bytes group 1000',equal('READER_ALERT',gid=1000),'UNIT_PRESENT_FOREIGN_CONTENT'),
    ('service equal bytes three links',equal('READER_SERVICE',nlink=3),'UNIT_PRESENT_FOREIGN_CONTENT'),
    ('service too large to be the render',foreign(SERVICE,content=b'#'*20000),'UNIT_PRESENT_FOREIGN_CONTENT'),
    ('timer present and equal, unsigned',equal('READER_TIMER'),'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'),
    ('drop-in of the service',add(ru.UNITS+'/'+SERVICE+'.d'),'DROP_IN_PRESENT'),
    ('type-level timer drop-in in /run',add('/run/systemd/system/timer.d'),'DROP_IN_PRESENT'),
    ('dash-truncated drop-in',add('/usr/lib/systemd/system/c3po-.service.d'),'DROP_IN_PRESENT'),
    ('dash-truncated drop-in of the alert',add(ru.UNITS+'/c3po-reader-.service.d'),'DROP_IN_PRESENT'),
    ('own wants directory of the service',add(ru.UNITS+'/'+SERVICE+'.wants'),'OWN_DEPENDENCY_DIRECTORY_PRESENT'),
    ('own requires directory of the timer',add('/run/systemd/generator/'+TIMER+'.requires'),'OWN_DEPENDENCY_DIRECTORY_PRESENT'),
    ('own upholds directory of the alert',add(ru.UNITS+'/'+ALERT+'.upholds'),'OWN_DEPENDENCY_DIRECTORY_PRESENT'),
    ('timer already enabled',add(ru.UNITS+'/timers.target.wants/'+TIMER,kind='symlink',mode=0o777),'ENABLEMENT_LINK_PRESENT'),
    ('service required by a target in /usr/lib',add('/usr/lib/systemd/system/multi-user.target.requires/'+SERVICE,kind='symlink',mode=0o777),'ENABLEMENT_LINK_PRESENT'),
    ('service shadowed in /run',add('/run/systemd/system/'+SERVICE,kind='file',mode=0o644),'UNIT_SHADOWED_IN_OTHER_PATH'),
    ('timer shadowed in /usr/local',add('/usr/local/lib/systemd/system/'+TIMER,kind='file',mode=0o644),'UNIT_SHADOWED_IN_OTHER_PATH'),
    ('alert in the transient directory',add('/run/systemd/transient/'+ALERT,kind='file',mode=0o644),'UNIT_SHADOWED_IN_OTHER_PATH'),
    ('a lookup directory behind a link',add('/usr/local/lib/systemd/system',kind='symlink',mode=0o777),'CONFLICT_SCAN_UNAVAILABLE'),
    ('a lookup directory is a file',add('/run/systemd/transient',kind='file',mode=0o644),'CONFLICT_SCAN_UNAVAILABLE'),
    ('a dependency directory that is a file',add(ru.UNITS+'/sockets.target.wants',kind='file',mode=0o644),'CONFLICT_SCAN_UNAVAILABLE'),
    ('a leftover of an earlier run',add(ru.UNITS+'/.hostops-'+'c'*16+'-0.partial',kind='file',mode=0o644),'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'),
]
@pytest.mark.parametrize('label,setup,code',PRECHECK_REFUSALS,ids=[row[0] for row in PRECHECK_REFUSALS])
def test_every_precheck_refusal_leaves_the_host_unchanged(label,setup,code):
    docs,host=ru.case();setup(host);receipt=refused_unchanged(docs,host,code)
    assert receipt['phase_reached']=='PRECHECK' and receipt['ledger']==[] and receipt['objects_left_by_this_run']==0

def test_executor_and_boot_are_looked_at_first():
    docs,host=ru.case();host.actor=(1000,1000);receipt=refused_unchanged(docs,host,'EXECUTOR_IDENTITY')
    assert [entry[0] for entry in host.log]==[]
    docs,host=ru.case();docs.plan['evidence_boot_id_sha256']='b'*64;receipt=refused_unchanged(docs,host,'EVIDENCE_FROM_EARLIER_BOOT')
    assert [entry[0] for entry in host.log if entry[0]=='lstat']==[] and receipt['unit_directory']==[]

def test_a_foreign_unit_is_never_hashed_or_sized_in_the_receipt():
    docs,host=ru.case();foreign(SERVICE,content=b'[Service]\nEnvironment=C3PO_DATABASE_URL=postgresql://c3po:'+hostemu.SECRET.encode()+b'@db/c3po\n')(host)
    receipt=refused_unchanged(docs,host,'UNIT_PRESENT_FOREIGN_CONTENT');row=receipt['precheck']['units'][0]
    assert row['bytes_equal_signed_render'] is False and 'sha256' not in row and 'size' not in row and row['state']=='PRESENT_FOREIGN'
    assert hostemu.SECRET not in json.dumps(receipt)

def test_all_three_units_present_and_equal_is_said_and_refused():
    docs,host=ru.case()
    for key,_ in ru.NAMES:equal(key)(host)
    receipt=refused_unchanged(docs,host,'ALL_UNITS_PRESENT')
    assert [row['state'] for row in receipt['precheck']['units']]==['PRESENT_EQUAL_NOT_SIGNED']*3
    assert all(row['sha256']==f.sha(K().m.rendered_units()[row['key']]) for row in receipt['precheck']['units'])
    docs,host=ru.case()
    for key,_ in ru.NAMES:equal(key)(host)
    host.tree.get(ru.UNITS+'/'+TIMER).nlink=2;refused_unchanged(docs,host,'PRIOR_PARTIAL_REQUIRES_RECONCILIATION')
    docs,host=ru.case()
    for key,_ in ru.NAMES:equal(key)(host)
    add(ru.UNITS+'/.hostops-'+'c'*16+'-0.partial',kind='file',mode=0o644)(host);refused_unchanged(docs,host,'PRIOR_PARTIAL_REQUIRES_RECONCILIATION')

def test_units_signed_present_must_be_there_with_their_identity():
    docs,host=ru.case();docs.plan['units'][0]['expect']={'device':hostemu.ROOT_DEVICE,'inode':12345,'links':1}
    receipt=refused_unchanged(docs,host,'EXPECTATION_MISMATCH');assert receipt['precheck']['units'][0]['state']=='EXPECTED_PRESENT_ABSENT'
    docs,host=ru.case();identity=ru.installed(host,'READER_SERVICE');identity['inode']+=1;docs.plan['units'][0]['expect']=identity
    receipt=refused_unchanged(docs,host,'EXPECTATION_MISMATCH');assert receipt['precheck']['units'][0]['state']=='PRESENT_IDENTITY_MISMATCH'
    docs,host=ru.case();identity=ru.installed(host,'READER_SERVICE');identity['links']=2;docs.plan['units'][0]['expect']=identity
    refused_unchanged(docs,host,'EXPECTATION_MISMATCH')
    docs,host=ru.case();identity=ru.installed(host,'READER_SERVICE');host.tree.get(ru.UNITS+'/'+SERVICE).content.extend(b'#')
    docs.plan['units'][0]['expect']=identity;refused_unchanged(docs,host,'EXPECTATION_MISMATCH')
    docs,host=ru.case();docs.plan['acknowledged_leftovers']=[{'name':'.hostops-'+'d'*16+'-0.partial','device':1,'inode':2}]
    refused_unchanged(docs,host,'EXPECTATION_MISMATCH')

def test_the_own_temporary_name_taken_refuses_acknowledged_or_not():
    docs,host=ru.case();name='.hostops-%s-1.partial'%docs.go16();node_=host.tree.add(ru.UNITS+'/'+name,kind='file',mode=0o644)
    refused_unchanged(docs,host,'TEMPORARY_NAME_OCCUPIED')
    docs,host=ru.case();docs.chain();name='.hostops-%s-2.partial'%docs.go16();node_=host.tree.add(ru.UNITS+'/'+name,kind='file',mode=0o644)
    docs.plan['acknowledged_leftovers']=[{'name':name,'device':node_.dev,'inode':node_.ino}];docs.chain()
    # the GO hash moved with the plan: the name is no longer this run's own temporary, it is an acknowledged leftover
    receipt=run(docs,host);assert receipt['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'

def test_precedence_of_the_refusals_is_fixed():
    pairs=[(['service name holds a directory','service name holds another unit'],'UNIT_NAME_OCCUPIED'),
           (['timer name holds a link','drop-in of the service'],'UNIT_NAME_OCCUPIED'),
           (['service name holds another unit','timer present and equal, unsigned'],'UNIT_PRESENT_FOREIGN_CONTENT'),
           (['timer present and equal, unsigned','drop-in of the service'],'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'),
           (['a leftover of an earlier run','drop-in of the service'],'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'),
           (['drop-in of the service','own wants directory of the service'],'DROP_IN_PRESENT'),
           (['own wants directory of the service','timer already enabled'],'OWN_DEPENDENCY_DIRECTORY_PRESENT'),
           (['timer already enabled','service shadowed in /run'],'ENABLEMENT_LINK_PRESENT'),
           (['service shadowed in /run','a lookup directory behind a link'],'UNIT_SHADOWED_IN_OTHER_PATH'),
           (['producer unit absent','service name holds a directory'],'PRODUCER_UNIT_ABSENT'),
           (['catalogue absent','service name holds a directory'],'CATALOG_NOT_INITIALISED'),
           (['journal root replaced','catalogue absent'],'PARENT_IDENTITY_MISMATCH')]
    by={row[0]:row[1] for row in PRECHECK_REFUSALS}
    for labels,code in pairs:
        docs,host=ru.case()
        for label in labels:by[label](host)
        refused_unchanged(docs,host,code)

def test_scan_limit_and_findings_cap():
    docs,host=ru.case()
    for index in range(4097):host.tree.add('/run/systemd/generator/x%05d.service'%index,kind='file',mode=0o644)
    receipt=refused_unchanged(docs,host,'CONFLICT_SCAN_UNAVAILABLE')
    assert receipt['precheck']['conflicts']['directories']['/run/systemd/generator']=={'status':'UNAVAILABLE','code':'SCAN_LIMIT'}
    docs,host=ru.case()
    for index in range(70):host.tree.add('/run/systemd/system/x%02d.target.wants/%s'%(index,SERVICE),kind='symlink',mode=0o777)
    receipt=refused_unchanged(docs,host,'ENABLEMENT_LINK_PRESENT');scan=receipt['precheck']['conflicts']
    assert len(scan['findings'])==64 and scan['findings_truncated'] is True

def test_budget_before_the_first_creation():
    for left,outcome in ((14.99,'REFUSED_NOTHING_CREATED'),(15,'UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED')):
        docs,host=ru.case();before=ru.state_of(host);docs.chain()
        receipt=docs.perform(host,gate=lambda:left)
        assert receipt['outcome']==outcome
        if outcome.startswith('REFUSED'):assert receipt['code']=='BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT' and ru.state_of(host)==before


# ---------------------------------------------------------------- continuation over what an earlier run left
def test_continuation_installs_only_what_is_absent_and_verifies_what_is_signed_present():
    docs,host=ru.case();identity=ru.installed(host,'READER_SERVICE');docs.plan['units'][0]['expect']=identity
    leftover=host.tree.add(ru.UNITS+'/.hostops-'+'e'*16+'-0.partial',kind='file',mode=0o644,content=b'[Unit')
    docs.plan['acknowledged_leftovers']=[{'name':'.hostops-'+'e'*16+'-0.partial','device':leftover.dev,'inode':leftover.ino}]
    service=host.tree.get(ru.UNITS+'/'+SERVICE);snapshot=(service.ino,bytes(service.content),service.mtime)
    receipt=run(docs,host)
    assert receipt['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED' and receipt['readback']=='COMPLETE'
    assert [row['state'] for row in receipt['ledger']]==['PRESENT_VERIFIED_NOT_TOUCHED','INSTALLED_DURABLE','INSTALLED_DURABLE']
    assert receipt['ledger'][0]['sha256_observed']==receipt['ledger'][0]['sha256_signed']
    assert (service.ino,bytes(service.content),service.mtime)==snapshot and host.tree.get(ru.UNITS+'/.hostops-'+'e'*16+'-0.partial') is leftover
    assert receipt['mutating_calls']['issued']==8 and receipt['precheck']['conflicts']['leftovers_acknowledged']==['.hostops-'+'e'*16+'-0.partial']
    assert [row['state'] for row in receipt['precheck']['units']]==['OK_PRESENT','OK_ABSENT','OK_ABSENT']

def test_a_unit_signed_present_with_its_temporary_still_linked_is_accepted_as_signed():
    docs,host=ru.case();identity=ru.installed(host,'READER_TIMER');unit=host.tree.get(ru.UNITS+'/'+TIMER)
    temporary='.hostops-'+'f'*16+'-1.partial';host.tree.get(ru.UNITS).children[temporary]=unit;unit.nlink=2;identity['links']=2
    docs.plan['units'][1]['expect']=identity;docs.plan['acknowledged_leftovers']=[{'name':temporary,'device':unit.dev,'inode':unit.ino}]
    receipt=run(docs,host);assert receipt['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'
    assert [row['state'] for row in receipt['ledger']]==['INSTALLED_DURABLE','PRESENT_VERIFIED_NOT_TOUCHED','INSTALLED_DURABLE'] and unit.nlink==2

def test_a_unit_signed_present_that_changes_before_the_readback_makes_the_run_partial():
    docs,host=ru.case();identity=ru.installed(host,'READER_ALERT');docs.plan['units'][2]['expect']=identity
    def hook(host,name,detail,calls):
        if name=='unlink' and detail[0].endswith('-1.partial'):host.tree.get(ru.UNITS+'/'+ALERT).content.extend(b'#')
    host.hook=hook;receipt=run(docs,host)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_REQUIRES_RECONCILIATION','READBACK_HASH_MISMATCH')
    assert receipt['readback'] is None

def test_a_unit_signed_present_replaced_before_the_readback_makes_the_run_partial():
    docs,host=ru.case();identity=ru.installed(host,'READER_ALERT');docs.plan['units'][2]['expect']=identity
    def hook(host,name,detail,calls):
        if name=='unlink' and detail[0].endswith('-1.partial'):
            old=host.tree.get(ru.UNITS+'/'+ALERT);host.tree.remove(ru.UNITS+'/'+ALERT)
            host.tree.add(ru.UNITS+'/'+ALERT,kind='file',mode=0o644,content=bytes(old.content))
    host.hook=hook;receipt=run(docs,host);assert (receipt['outcome'],receipt['code'])==('PARTIAL_REQUIRES_RECONCILIATION','READBACK_HASH_MISMATCH')
    docs,host=ru.case();identity=ru.installed(host,'READER_ALERT');docs.plan['units'][2]['expect']=identity
    def chmod(host,name,detail,calls):
        if name=='unlink' and detail[0].endswith('-1.partial'):host.tree.get(ru.UNITS+'/'+ALERT).mode=0o600
    host.hook=chmod;receipt=run(docs,host);assert (receipt['outcome'],receipt['code'])==('PARTIAL_REQUIRES_RECONCILIATION','READBACK_HASH_MISMATCH')
    docs,host=ru.case();identity=ru.installed(host,'READER_ALERT');docs.plan['units'][2]['expect']=identity
    def gone(host,name,detail,calls):
        if name=='unlink' and detail[0].endswith('-1.partial'):host.tree.remove(ru.UNITS+'/'+ALERT)
    host.hook=gone;receipt=run(docs,host);assert (receipt['outcome'],receipt['code'])==('PARTIAL_REQUIRES_RECONCILIATION','READBACK_UNAVAILABLE')


# ---------------------------------------------------------------- what each failure of an effect leaves
def failing(name,error,nth=1):
    seen=[0]
    def hook(host,call,detail,calls):
        if call==name:
            seen[0]+=1
            if seen[0]==nth:raise error
    return hook

def test_a_read_only_filesystem_at_the_first_creation_is_a_refusal_with_nothing_left():
    docs,host=ru.case();host.readonly=True;before=ru.state_of(host);receipt=run(docs,host)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED','REFUSED_NOTHING_CREATED','FILESYSTEM_READ_ONLY')
    assert ru.state_of(host)==before and receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0}
    assert [row['state'] for row in receipt['ledger']]==['NOT_CREATED','NOT_ATTEMPTED','NOT_ATTEMPTED'] and receipt['phase_reached']=='CREATION'

def test_a_name_taken_after_the_precheck_is_left_alone_and_the_run_is_partial():
    docs,host=ru.case()
    def hook(host,name,detail,calls):
        if name=='link' and detail[1].endswith('/'+TIMER):host.tree.add(ru.UNITS+'/'+TIMER,kind='file',mode=0o644,content=b'other\n')
    host.hook=hook;receipt=run(docs,host)
    assert (receipt['outcome'],receipt['code'])==('PARTIAL_REQUIRES_RECONCILIATION','DESTINATION_APPEARED_AFTER_PRECHECK')
    assert [row['state'] for row in receipt['ledger']]==['INSTALLED_DURABLE','NOT_CREATED','NOT_ATTEMPTED']
    assert bytes(host.tree.get(ru.UNITS+'/'+TIMER).content)==b'other\n' and host.tree.get(ru.UNITS+'/'+ALERT) is None
    assert sorted(name for name in host.tree.get(ru.UNITS).children if name.startswith('.hostops'))==[] and receipt['objects_left_by_this_run']==1

def test_a_full_filesystem_on_the_second_unit_withdraws_its_temporary_and_stops():
    docs,host=ru.case();host.hook=failing('write',OSError(errno.ENOSPC,'full'),2);receipt=run(docs,host)
    assert (receipt['outcome'],receipt['code'])==('PARTIAL_REQUIRES_RECONCILIATION','FILESYSTEM_FULL')
    assert [row['state'] for row in receipt['ledger']]==['INSTALLED_DURABLE','NOT_CREATED','NOT_ATTEMPTED'] and receipt['ledger'][1]['temporary_removed'] is True
    assert sorted(host.tree.get(ru.UNITS).children)==sorted(set(hostemu.world().tree.get(ru.UNITS).children)|{'c3po-massive.service',SERVICE})

def test_a_readback_that_finds_other_bytes_makes_the_run_partial():
    docs,host=ru.case()
    def hook(host,name,detail,calls):
        if name=='unlink' and detail[0].endswith('-2.partial'):host.tree.get(ru.UNITS+'/'+SERVICE).content[0:1]=b'#'
    host.hook=hook;receipt=run(docs,host)
    assert (receipt['outcome'],receipt['code'],receipt['readback'])==('PARTIAL_REQUIRES_RECONCILIATION','READBACK_HASH_MISMATCH',None)
    assert [row['state'] for row in receipt['ledger']]==['INSTALLED_DURABLE']*3

def test_the_unit_directory_replaced_after_the_creations_makes_the_run_partial():
    docs,host=ru.case();done=[False]
    def hook(host,name,detail,calls):
        if name=='read' and detail[0]==ru.UNITS+'/'+ALERT and not done[0]:done[0]=True;host.tree.get(ru.UNITS).mode=0o775
    host.hook=hook;receipt=run(docs,host)
    assert (receipt['outcome'],receipt['code'])==('PARTIAL_REQUIRES_RECONCILIATION','PARENT_REPLACED')

def test_a_death_after_the_link_leaves_a_linked_temporary_and_no_receipt():
    docs,host=ru.case();host.hook=failing('link',hostemu.Death(),2)
    with pytest.raises(hostemu.Death):docs.chain().perform(host)
    children=host.tree.get(ru.UNITS).children;temporary='.hostops-%s-1.partial'%docs.go16()
    assert SERVICE in children and temporary in children and TIMER not in children
    host.hook=None;docs2=f.Docs(K(),ru.fields(host));receipt=run(docs2,host)
    assert receipt['code']=='PRIOR_PARTIAL_REQUIRES_RECONCILIATION' and receipt['precheck']['conflicts']['leftovers_not_acknowledged']==[temporary]


# ---------------------------------------------------------------- every lookup directory is scanned; the producer's values
OTHER_LOOKUP=['/etc/systemd/system.control','/run/systemd/system.control','/run/systemd/transient','/run/systemd/generator.early',
              '/etc/systemd/system.attached','/run/systemd/system','/run/systemd/system.attached','/run/systemd/generator',
              '/usr/local/lib/systemd/system','/usr/lib/systemd/system','/run/systemd/generator.late']
@pytest.mark.parametrize('directory',OTHER_LOOKUP)
def test_a_unit_of_the_same_name_in_any_other_lookup_directory_refuses(directory):
    docs,host=ru.case();host.tree.add(directory+'/'+TIMER,kind='file',mode=0o644);receipt=refused_unchanged(docs,host,'UNIT_SHADOWED_IN_OTHER_PATH')
    assert receipt['precheck']['conflicts']['findings']==[{'code':'UNIT_SHADOWED_IN_OTHER_PATH','directory':directory,'name':TIMER,'within':None}]

@pytest.mark.parametrize('directory',OTHER_LOOKUP+['/etc/systemd/system'])
def test_a_drop_in_in_any_lookup_directory_refuses(directory):
    docs,host=ru.case();host.tree.add(directory+'/c3po-reader-alert.service.d');refused_unchanged(docs,host,'DROP_IN_PRESENT')

def test_the_lookup_directories_are_the_reviewed_list():
    assert list(K().m.SCAN_DIRECTORIES)==['/etc/systemd/system.control','/run/systemd/system.control','/run/systemd/transient',
        '/run/systemd/generator.early','/etc/systemd/system','/etc/systemd/system.attached','/run/systemd/system','/run/systemd/system.attached',
        '/run/systemd/generator','/usr/local/lib/systemd/system','/usr/lib/systemd/system','/run/systemd/generator.late']
    assert K().m.drop_in_names('c3po-reader-alert.service')==['c3po-reader-alert.service.d','service.d','c3po-.service.d','c3po-reader-.service.d']

def test_an_installed_producer_whose_values_are_not_the_reader_values_refuses(monkeypatch):
    m=K().m
    for name,value in (('IMAGE_ID','sha256:'+'1'*64),('CONTAINER_JOURNAL_ROOT','/c3po-journal')):
        with monkeypatch.context() as patch:
            patch.setitem(m.READER_VALUES,name,value);docs,host=ru.case();refused_unchanged(docs,host,'PRODUCER_VALUES_NOT_THE_READER_VALUES')

def test_a_producer_private_root_around_the_journal_refuses(monkeypatch):
    m=K().m;raw=ru.producer_bytes()
    facts=m.producer_facts(raw);facts['other_sources']=['/var/lib/c3po-bar']
    monkeypatch.setattr(m,'producer_facts',lambda raw:dict(facts))
    docs,host=ru.case();refused_unchanged(docs,host,'HOST_JOURNAL_OVERLAPS_A_PRODUCER_PRIVATE_ROOT')

def test_effects_carry_the_boot_and_the_chains_of_the_plan():
    docs,host=ru.case();effects=K().m.effects_of(docs.plan)
    assert effects['evidence_boot_id_sha256']==f.BOOT_SHA and effects['directory']['row']==docs.plan['unit_rows'][-1]
    assert effects['journal']['chain_sha256']==f.sha(f.canonical(docs.plan['journal_rows'])) and effects['data_volume']['row']==docs.plan['data_rows'][-1]


# ---------------------------------------------------------------- answers to the first mutation run
def test_producer_of_the_same_size_but_one_byte_changed_refuses():
    docs,host=ru.case();content=host.tree.get(ru.PRODUCER_PATH).content;content[-2:-1]=b'X'
    refused_unchanged(docs,host,'PRODUCER_UNIT_NOT_AS_SIGNED')

def test_producer_read_must_be_the_object_seen_by_lstat():
    docs,host=ru.case();real=host.lstat
    def lstat(name,dir_fd):
        info=real(name,dir_fd)
        if name=='c3po-massive.service':info.st_ino+=1
        return info
    host.lstat=lstat;refused_unchanged(docs,host,'PRODUCER_UNIT_NOT_AS_SIGNED')

def test_a_precheck_refusal_keeps_its_code_when_little_time_is_left():
    docs,host=ru.case();add(ru.UNITS+'/'+SERVICE+'.d')(host);docs.chain();before=ru.state_of(host)
    receipt=docs.perform(host,gate=lambda:5);assert receipt['code']=='DROP_IN_PRESENT' and ru.state_of(host)==before

def test_a_leftover_acknowledged_with_another_identity_is_not_acknowledged():
    docs,host=ru.case();name='.hostops-'+'c'*16+'-0.partial';node_=host.tree.add(ru.UNITS+'/'+name,kind='file',mode=0o644)
    docs.plan['acknowledged_leftovers']=[{'name':name,'device':node_.dev,'inode':node_.ino+1}]
    receipt=refused_unchanged(docs,host,'PRIOR_PARTIAL_REQUIRES_RECONCILIATION')
    assert receipt['precheck']['conflicts']['leftovers_not_acknowledged']==[name] and receipt['precheck']['conflicts']['leftovers_acknowledged']==[]

def test_a_temporary_that_cannot_be_removed_stops_the_run_at_that_unit():
    docs,host=ru.case();host.hook=failing('unlink',OSError(errno.EACCES,'denied'),1);receipt=run(docs,host)
    assert (receipt['outcome'],receipt['code'])==('PARTIAL_REQUIRES_RECONCILIATION','TEMPORARY_REMOVAL_FAILED')
    assert [row['state'] for row in receipt['ledger']]==['LINKED_TEMPORARY_PRESENT','NOT_ATTEMPTED','NOT_ATTEMPTED'] and host.tree.get(ru.UNITS+'/'+TIMER) is None

def test_success_criterion_and_receipt_reductions():
    m=K().m;docs,_=ru.case()
    assert m.success_of(docs.plan)=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'==docs.go['success_criterion']
    assert [name for name,_ in m.REDUCTIONS]==['SCAN_DIRECTORIES_REDUCED_TO_STATUS','PRECHECK_REDUCED_TO_STATES']
    receipt={'precheck':{'units':[{'key':'K','state':'S','x':1}],'conflicts':{'directories':{'/a':{'status':'COMPLETE','entries':3}},'finding_codes':['X']}}}
    m.REDUCTIONS[0][1](receipt);assert receipt['precheck']['conflicts']['directories']=={'/a':'COMPLETE'}
    m.REDUCTIONS[1][1](receipt);assert receipt['precheck']=={'units':[{'key':'K','state':'S'}],'finding_codes':['X']}
