"""Rendering, the substitution grammar and the extraction parse. Pure functions: nothing here touches a host.
The reference is the repository's own loop (test_r2d2_v2_massive_supervisor.py), not the candidate's renderer; the
reference for the journal placement rules is the repository's own reading of the README (placement_refusal, same file,
revision a6dd2b1), copied below and compared case by case."""
import base64
import hashlib
from pathlib import Path
import random
import string

import pytest

import family as f

k=f.load('install_units');m=k.m
ALLOW=['bridge'];VOLUME='/mnt/day-d-data';TREE='/opt/chief-of-staff-digital'
SAMPLE_A=dict(f.README_SAMPLE,HOST_JOURNAL_ROOT='/var/lib/c3po-bar/journal',CONTAINER_JOURNAL_ROOT='/c3po-bar-journal')      # the README's own example pair

def refusal(action):
    with pytest.raises(m.Refused) as caught:action()
    return str(caught.value)
def service(values,**changes):
    unit=f.unit('S','c3po-massive.service','MASSIVE_SUPERVISOR_SERVICE_V1',f.SERVICE,dict(values),f.reference_render(f.README_SAMPLE))
    unit.update(changes);return unit
def check(values,allow=ALLOW,volume=VOLUME,placement='B',tree=None):return lambda:m.validate_substitutions(values,allow,volume,placement,tree)
def check_a(values,volume=VOLUME,tree=TREE):return check(values,volume=volume,placement='A',tree=tree)
def sample_a(**changes):
    values=dict(SAMPLE_A);values.update(changes);return values
def sample(**changes):
    values=dict(f.README_SAMPLE);values.update(changes);return values


def test_known_answer_of_the_readme_sample_against_the_repository_reference_loop():
    reference=f.reference_render(f.README_SAMPLE)
    assert len(reference)==1746 and f.sha(reference)=='9010fee9c08b31f641c559e1712a0b671aaf3a6fc682bf5bf7240301fd53ac03'
    assert m.render_unit(service(f.README_SAMPLE),ALLOW,VOLUME,'B')==reference
    # the README's placement A pair renders to its own known answer, and only under placement A with a deploy tree signed
    outside=f.reference_render(SAMPLE_A);assert len(outside)==1674 and f.sha(outside)=='4f44015e1a14d8e5219393e3540ba89324d26f5ea8b80c15cbc0cc04652db4ac'
    unit=f.unit('S','c3po-massive.service','MASSIVE_SUPERVISOR_SERVICE_V1',f.SERVICE,dict(SAMPLE_A),outside)
    assert m.render_unit(unit,ALLOW,VOLUME,'A',TREE)==outside and m.extract_values(f.SERVICE,outside)==SAMPLE_A
    assert b'source=/var/lib/c3po-bar/journal,target=/c3po-bar-journal ' in outside and b'--journal-root /c3po-bar-journal ' in outside
    assert refusal(lambda:m.render_unit(unit,ALLOW,VOLUME,'B'))=='B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME'
    assert refusal(lambda:m.render_unit(service(f.README_SAMPLE),ALLOW,VOLUME,'A',TREE))=='A_HOST_JOURNAL_INSIDE_DATA_VOLUME'
    for placement,tree in ((None,None),('C',None),('a',TREE),(['A'],TREE),(1,None)):
        assert refusal(lambda:m.render_unit(unit,ALLOW,VOLUME,placement,tree))=='PLACEMENT_UNKNOWN'
    assert m.render_service(f.SERVICE,f.README_SAMPLE)==reference
    timer=f.unit('T','c3po-massive.timer','MASSIVE_SUPERVISOR_TIMER_V1',f.TIMER,{},f.TIMER)
    assert m.render_unit(timer,ALLOW,VOLUME)==f.TIMER and len(f.TIMER)==234
    assert m.extract_values(f.SERVICE,reference)==f.README_SAMPLE

def valid_sets(count,seed=20261001):
    rng=random.Random(seed);alpha=string.ascii_letters+string.digits+'._-'
    def component():
        while True:
            value=''.join(rng.choice(alpha) for _ in range(rng.randint(1,12)))
            if value not in ('.','..'):return value
    def path(prefix,depth):return prefix+''.join('/'+component() for _ in range(depth))
    for _ in range(count):
        leaf=component();volume=path('/mnt',rng.randint(0,2)) if rng.random()<.8 else '/'+component()
        yield volume,{'IMAGE_ID':'sha256:'+''.join(rng.choice('0123456789abcdef') for _ in range(64)),
                      'HOST_JOURNAL_ROOT':volume+'/'+leaf,'CONTAINER_JOURNAL_ROOT':'/app/day-d-data/'+leaf,
                      'HOST_STATE_ROOT':path('/var/lib',rng.randint(1,3)),'HOST_CONFIG_DIR':path('/etc',rng.randint(1,3)),
                      'NETWORK':rng.choice(string.ascii_letters+string.digits)+''.join(rng.choice(alpha+'_') for _ in range(rng.randint(0,10)))}

def test_two_thousand_random_valid_value_sets_render_like_the_reference_and_parse_back():
    divergent=0;checked=0
    for volume,values in valid_sets(2400):
        if values['NETWORK'] in ('host','none'):continue
        state,config=values['HOST_STATE_ROOT'],values['HOST_CONFIG_DIR']
        reference=f.reference_render(values);checked+=1
        unit=f.unit('S','c3po-massive.service','MASSIVE_SUPERVISOR_SERVICE_V1',f.SERVICE,values,reference)
        if m.render_unit(unit,[values['NETWORK']],volume,'B')!=reference or m.extract_values(f.SERVICE,reference)!=values:divergent+=1
        # the same set with a journal pair of placement A
        outside=dict(values,HOST_JOURNAL_ROOT='/var/lib/c3po-bar/'+values['HOST_JOURNAL_ROOT'].rsplit('/',1)[1],CONTAINER_JOURNAL_ROOT='/c3po-bar-journal')
        if m.overlaps(Path(outside['HOST_JOURNAL_ROOT']),Path(state)) or m.within(Path(state),Path(volume)):continue
        reference=f.reference_render(outside);unit=f.unit('S','c3po-massive.service','MASSIVE_SUPERVISOR_SERVICE_V1',f.SERVICE,outside,reference)
        if m.render_unit(unit,[values['NETWORK']],volume,'A',TREE)!=reference or m.extract_values(f.SERVICE,reference)!=outside:divergent+=1
    assert checked>=2000 and divergent==0

HOSTILE=[' ','%','$',',',';','"',"'",'\\','\n','\t','@','=','*','?','~','#','!','é','\x00','{','}','(','&','|','<','`',':','+']
@pytest.mark.parametrize('name',['HOST_JOURNAL_ROOT','CONTAINER_JOURNAL_ROOT','HOST_STATE_ROOT','HOST_CONFIG_DIR'])
def test_path_grammar_each_hostile_character_and_shape_has_its_code(name):
    base=f.README_SAMPLE[name]
    for character in HOSTILE:
        for value in (base+character,base+character+'x',base[:5]+character+base[5:]):
            assert refusal(check(sample(**{name:value})))=='PATH_INVALID',repr(value)
            assert refusal(check_a(sample_a(**{name:value})))=='PATH_INVALID',repr(value)
    for value in (None,7,['/etc'],b'/etc/c3po-bar','','etc/c3po-bar','relative','//','/'):
        assert refusal(check(sample(**{name:value}))) in ('PATH_INVALID','PATH_COMPONENT'),repr(value)
    for value in (base+'/',base+'//x',base+'/./x',base+'/../x',base+'/..',base+'/.'):
        assert refusal(check(sample(**{name:value})))=='PATH_COMPONENT',repr(value)
    assert refusal(check(sample(**{name:'/'+'a/'*100+'b'})))=='PATH_TOO_LONG'
    assert refusal(check(sample(**{name:base+'/'+'c'*65})))=='PATH_TOO_LONG'
    assert m.safe_path('/a/'+'c'*64) and m.safe_path('/'+'/'.join(['abc']*50))

@pytest.mark.parametrize('value',['c3po/backend:production','sha256:'+'A'*64,'sha256:'+'a'*63,'sha256:'+'a'*65,'sha256:'+'a'*64+'\n',
                                  ' sha256:'+'a'*64,'sha512:'+'a'*64,'a'*64,None,7,'sha256:'+'g'*64,'sha256:'+'a'*64+' --privileged'])
def test_image_id_is_exactly_a_sha256_id(value):
    assert refusal(check(sample(IMAGE_ID=value)))=='IMAGE_ID'

def test_network_allowlist_and_forbidden_networks():
    assert refusal(check(sample(NETWORK='c3po_internal')))=='NETWORK_NOT_AUTHORIZED'
    assert refusal(check(sample(NETWORK=None)))=='NETWORK_NOT_AUTHORIZED'
    for allow in (['host'],['none'],['bridge','host'],['container:c3po-api-1'],['a b'],['-x'],[''],['x'*129],['bridge;rm']):
        assert refusal(check(sample(NETWORK=allow[0]),allow=allow))=='NETWORK_FORBIDDEN',allow
    for allow in ([],'bridge',None,('bridge',),['bridge','bridge'],['n%d'%index for index in range(17)],[['bridge']],[None],[1],{'bridge':1}):
        assert refusal(check(sample(),allow=allow))=='NETWORK_ALLOWLIST',allow
    m.validate_substitutions(sample(NETWORK='c3po_c3po_internal'),['bridge','c3po_c3po_internal'],VOLUME,'B',None)

def test_placement_b_journal_is_a_leaf_of_the_data_volume_and_private_roots_stay_outside_it_in_both_directions():
    assert refusal(check(sample(CONTAINER_JOURNAL_ROOT='/app/day-d-data/other')))=='B_CONTAINER_JOURNAL_NOT_THE_SAME_LEAF'
    assert refusal(check(sample(CONTAINER_JOURNAL_ROOT='/app/other/r2d2-v2-massive-epoch03')))=='B_CONTAINER_JOURNAL_NOT_THE_SAME_LEAF'
    assert refusal(check(sample(CONTAINER_JOURNAL_ROOT='/c3po-bar-journal')))=='B_CONTAINER_JOURNAL_NOT_THE_SAME_LEAF'
    assert refusal(check(sample(HOST_JOURNAL_ROOT='/mnt/day-d-data/x/r2d2-v2-massive-epoch03')))=='B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME'
    assert refusal(check(sample(HOST_JOURNAL_ROOT='/mnt/r2d2-v2-massive-epoch03')))=='B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME'
    assert refusal(check(sample(HOST_JOURNAL_ROOT='/var/lib/c3po-bar/journal')))=='B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME'
    assert refusal(check(sample(),volume='/mnt'))=='B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME'
    assert refusal(check(sample(),tree=TREE))=='DEPLOY_TREE_PATH','placement B signs no deploy tree'
    journal=f.README_SAMPLE['HOST_JOURNAL_ROOT']
    for name in ('HOST_STATE_ROOT','HOST_CONFIG_DIR'):
        assert refusal(check(sample(**{name:VOLUME+'/private'})))=='PRIVATE_ROOT_INSIDE_DATA_VOLUME',name
        for value in (VOLUME,journal,journal+'/state'):          # the data volume itself as a private root would contain the journal root
            assert refusal(check(sample(**{name:value})))=='HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT',(name,value)
        assert refusal(check(sample(**{name:'/mnt'})))=='HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT'          # the journal root would be inside it
    assert refusal(check(sample(HOST_STATE_ROOT='/etc/c3po-bar')))=='PRIVATE_PATH_OVERLAP'
    assert refusal(check(sample(HOST_STATE_ROOT='/etc/c3po-bar/state')))=='PRIVATE_PATH_OVERLAP'
    assert refusal(check(sample(HOST_CONFIG_DIR='/var/lib/c3po-bar/supervisor/config')))=='PRIVATE_PATH_OVERLAP'

def test_placement_a_journal_is_outside_the_data_volume_the_deploy_tree_and_the_image_tree():
    m.validate_substitutions(SAMPLE_A,ALLOW,VOLUME,'A',TREE)
    for host,code in ((VOLUME,'A_HOST_JOURNAL_INSIDE_DATA_VOLUME'),(VOLUME+'/r2d2-v2-massive-epoch03','A_HOST_JOURNAL_INSIDE_DATA_VOLUME'),
                      (VOLUME+'/a/b','A_HOST_JOURNAL_INSIDE_DATA_VOLUME'),(TREE,'A_HOST_JOURNAL_INSIDE_DEPLOY_TREE'),(TREE+'/runtime/journal','A_HOST_JOURNAL_INSIDE_DEPLOY_TREE'),
                      ('/var/lib/c3po-bar/supervisor','HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT'),('/var/lib/c3po-bar','HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT'),
                      ('/var/lib/c3po-bar/supervisor/journal','HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT'),('/etc/c3po-bar/journal','HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT'),
                      ('/etc','HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT')):
        assert refusal(check_a(sample_a(HOST_JOURNAL_ROOT=host)))==code,host
    # the container journal root of placement A is exactly one new top-level directory
    for container,code in (('/app','A_CONTAINER_JOURNAL_PROVIDED_DIRECTORY'),('/app/day-d-data/journal','A_CONTAINER_JOURNAL_NOT_TOP_LEVEL'),('/app/journal','A_CONTAINER_JOURNAL_NOT_TOP_LEVEL'),
                           ('/usr/journal','A_CONTAINER_JOURNAL_NOT_TOP_LEVEL'),('/srv/c3po-bar-journal','A_CONTAINER_JOURNAL_NOT_TOP_LEVEL'),('/c3po-bar-journal/nested','A_CONTAINER_JOURNAL_NOT_TOP_LEVEL'),
                           ('/run/c3po/journal','A_CONTAINER_JOURNAL_NOT_TOP_LEVEL'),
                           ('/var/lib/c3po-bar','CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET'),('/var/lib/c3po-bar/supervisor','CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET'),
                           ('/etc/c3po-bar/journal','CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET'),('/tmp/journal','CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET'),
                           ('/tmp','CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET'),('/var','CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET'),('/etc','CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET')):
        assert refusal(check_a(sample_a(CONTAINER_JOURNAL_ROOT=container)))==code,container
    assert m.PROVIDED_TOP_LEVEL==('app','bin','boot','dev','etc','home','lib','lib64','media','mnt','opt','proc','root','run','sbin','srv','sys','tmp','usr','var')
    for name in m.PROVIDED_TOP_LEVEL:
        expected='CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET' if name in ('etc','tmp','var') else 'A_CONTAINER_JOURNAL_PROVIDED_DIRECTORY'
        assert refusal(check_a(sample_a(CONTAINER_JOURNAL_ROOT='/'+name)))==expected,name
        assert refusal(check_a(sample_a(CONTAINER_JOURNAL_ROOT='/'+name+'/journal'))) in ('A_CONTAINER_JOURNAL_NOT_TOP_LEVEL','CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET'),name
    for name in ('HOST_STATE_ROOT','HOST_CONFIG_DIR'):
        assert refusal(check_a(sample_a(**{name:VOLUME+'/private'})))=='PRIVATE_ROOT_INSIDE_DATA_VOLUME'
        assert refusal(check_a(sample_a(**{name:'/mnt'})))=='DATA_INSIDE_PRIVATE'
    for tree in (None,7,['/opt'],'relative','/opt/x y','/opt/../etc'):
        assert refusal(check_a(SAMPLE_A,tree=tree)) in ('DEPLOY_TREE_PATH','PATH_INVALID','PATH_COMPONENT'),tree
    assert refusal(check_a(SAMPLE_A,tree=None))=='DEPLOY_TREE_PATH'
    for container in ('/c3po-bar-journal','/c3po-bar-journal-2','/journal','/application'):m.validate_substitutions(sample_a(CONTAINER_JOURNAL_ROOT=container),ALLOW,VOLUME,'A',TREE)
    for host in ('/var/lib/c3po-bar/journal','/var/lib/c3po-bar/journal-epoch04','/srv/journal','/mnt/day-d-data-journal','/opt/chief-of-staff-digital-other/journal'):
        m.validate_substitutions(sample_a(HOST_JOURNAL_ROOT=host),ALLOW,VOLUME,'A',TREE)

# ---- the repository's own reading of the README grammar (backend/tests/test_r2d2_v2_massive_supervisor.py at a6dd2b1),
# copied verbatim: three functions and the constants they use. A reading of the prose, not the candidate's code.
DATA_VOLUME=Path('/mnt/day-d-data');DATA_TARGET=Path('/app/day-d-data');DEPLOY_TREE=Path('/opt/chief-of-staff-digital')
HOST_STATE_ROOT=Path('/var/lib/c3po-bar/supervisor');HOST_CONFIG_DIR=Path('/etc/c3po-bar')
FIXED_TARGETS=(Path('/var/lib/c3po-bar/supervisor'),Path('/etc/c3po-bar'),Path('/tmp'))
PROVIDED_TOP_LEVEL=frozenset('app bin boot dev etc home lib lib64 media mnt opt proc root run sbin srv sys tmp usr var'.split())
REFERENCE='''def overlaps(one,other):return one==other or one in other.parents or other in one.parents


def within(path,tree):return path==tree or tree in path.parents


def placement_refusal(placement,host,container,*,state=HOST_STATE_ROOT,config=HOST_CONFIG_DIR):
    """The refusals of the README's "Substitution grammar" that follow from the paths alone.

    A reading of the prose, not the installer (which is not in this repository). "The journal root is a mount
    point" and "the values differ from the signed ones" need the host and the authorisation; they are not here."""
    host,container,state,config=(Path(value) for value in (host,container,state,config))
    if any(overlaps(host,other) for other in (state,config)):return 'HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT'
    if any(overlaps(container,other) for other in FIXED_TARGETS):return 'CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET'
    if any(within(other,DATA_VOLUME) for other in (state,config)):return 'PRIVATE_ROOT_INSIDE_DATA_VOLUME'
    if placement=='A':
        if within(host,DATA_VOLUME):return 'A_HOST_JOURNAL_INSIDE_DATA_VOLUME'
        if within(host,DEPLOY_TREE):return 'A_HOST_JOURNAL_INSIDE_DEPLOY_TREE'
        # Exactly one component below "/", and not a directory the image or the runtime provides (/app among them).
        if len(container.parts)!=2:return 'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL'
        if container.name in PROVIDED_TOP_LEVEL:return 'A_CONTAINER_JOURNAL_PROVIDED_DIRECTORY'
        return None
    if placement=='B':
        if host.parent!=DATA_VOLUME:return 'B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME'
        if container!=DATA_TARGET/host.name:return 'B_CONTAINER_JOURNAL_NOT_THE_SAME_LEAF'
        return None
    return 'PLACEMENT_UNKNOWN'
'''
exec(REFERENCE)
REPOSITORY_TEST=f.ROOT.parent.parent/'actb-multiday'/'repo'/'c3po'/'backend'/'tests'/'test_r2d2_v2_massive_supervisor.py'

def test_static_reference_reading_is_the_repository_text():
    assert hashlib.sha256(REFERENCE.encode()).hexdigest()=='aae5f117d86cbd0a652696150b7eac8d943e58f42eb7f444a545b170b4d23dc5'
    if not REPOSITORY_TEST.is_file():pytest.skip('the repository is not on this machine')
    assert REFERENCE in REPOSITORY_TEST.read_text(),'the repository changed its reading of the placement rules: compare again'

def candidate_refusal(placement,host,container,state='/var/lib/c3po-bar/supervisor',config='/etc/c3po-bar'):
    values=dict(f.README_SAMPLE,HOST_JOURNAL_ROOT=host,CONTAINER_JOURNAL_ROOT=container,HOST_STATE_ROOT=state,HOST_CONFIG_DIR=config)
    try:m.validate_substitutions(values,ALLOW,str(DATA_VOLUME),placement,str(DEPLOY_TREE) if placement=='A' else None)
    except m.Refused as error:return str(error)
    return None

def test_placement_rules_agree_with_the_repository_reading_on_its_own_cases_and_on_every_pair_of_a_path_pool():
    a_host,a_container='/var/lib/c3po-bar/journal','/c3po-bar-journal';b_host,b_container='/mnt/day-d-data/r2d2-v2-massive-epoch03','/app/day-d-data/r2d2-v2-massive-epoch03'
    cases={('A',a_host,a_container):None,('B',b_host,b_container):None,
        ('A',b_host,a_container):'A_HOST_JOURNAL_INSIDE_DATA_VOLUME',('A',str(DATA_VOLUME),a_container):'A_HOST_JOURNAL_INSIDE_DATA_VOLUME',
        ('A',a_host,b_container):'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL',('A',a_host,'/app'):'A_CONTAINER_JOURNAL_PROVIDED_DIRECTORY',
        ('A',a_host,'/app/journal'):'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL',('A',a_host,'/usr/journal'):'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL',
        ('A',a_host,'/srv/c3po-bar-journal'):'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL',('A',a_host,a_container+'/nested'):'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL',
        ('A',a_host,'/run/c3po/journal'):'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL',
        **{('A',a_host,'/'+name):'A_CONTAINER_JOURNAL_PROVIDED_DIRECTORY' for name in ('usr','lib','lib64','bin','sbin','proc','sys','dev','run','boot','home','media','mnt','opt','root','srv')},
        ('A',a_host,'/c3po-bar-journal-2'):None,
        ('A',str(DEPLOY_TREE/'runtime'/'journal'),a_container):'A_HOST_JOURNAL_INSIDE_DEPLOY_TREE',
        ('B',a_host,b_container):'B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME',
        ('B',str(DATA_VOLUME/'nested'/'leaf'),str(DATA_TARGET/'leaf')):'B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME',
        ('B',b_host,str(DATA_TARGET/'another-leaf')):'B_CONTAINER_JOURNAL_NOT_THE_SAME_LEAF',('B',b_host,a_container):'B_CONTAINER_JOURNAL_NOT_THE_SAME_LEAF',
        ('A',str(HOST_STATE_ROOT),a_container):'HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT',('A',str(HOST_STATE_ROOT.parent),a_container):'HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT',
        ('A',str(HOST_STATE_ROOT/'journal'),a_container):'HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT',('B',str(HOST_CONFIG_DIR/'journal'),b_container):'HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT',
        ('A',a_host,'/var/lib/c3po-bar'):'CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET',('A',a_host,'/etc/c3po-bar/journal'):'CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET',
        ('A',a_host,'/tmp/journal'):'CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET',('B',b_host,'/var'):'CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET'}
    assert {case:placement_refusal(*case) for case in cases}==cases=={case:candidate_refusal(*case) for case in cases}
    assert placement_refusal('A',a_host,a_container,state=DATA_VOLUME/'state')==candidate_refusal('A',a_host,a_container,state=str(DATA_VOLUME/'state'))=='PRIVATE_ROOT_INSIDE_DATA_VOLUME'
    assert placement_refusal('B',b_host,b_container,config=DATA_VOLUME/'etc')==candidate_refusal('B',b_host,b_container,config=str(DATA_VOLUME/'etc'))=='PRIVATE_ROOT_INSIDE_DATA_VOLUME'
    assert placement_refusal('C',a_host,a_container)==candidate_refusal('C',a_host,a_container)=='PLACEMENT_UNKNOWN'
    # every (placement, host, container) of a pool of paths around each boundary, with the default private roots and with moved ones
    pool=['/var/lib/c3po-bar/journal','/var/lib/c3po-bar','/var/lib/c3po-bar/supervisor','/var/lib/c3po-bar/supervisor/x','/var/lib','/var','/etc','/etc/c3po-bar','/etc/c3po-bar/x',
          '/mnt','/mnt/day-d-data','/mnt/day-d-data/leaf','/mnt/day-d-data/a/leaf','/mnt/day-d-data-journal','/opt','/opt/chief-of-staff-digital','/opt/chief-of-staff-digital/x',
          '/opt/chief-of-staff-digital-other','/app','/app/day-d-data','/app/day-d-data/leaf','/app/day-d-data/other','/app/x','/application','/c3po-bar-journal','/tmp','/tmp/x',
          '/srv/journal','/leaf','/usr','/usr/journal','/proc','/run/x','/srv','/home']
    compared=agreed=stricter=0
    for state,config in ((str(HOST_STATE_ROOT),str(HOST_CONFIG_DIR)),('/mnt/day-d-data/state',str(HOST_CONFIG_DIR)),(str(HOST_STATE_ROOT),'/srv/config'),('/srv/state','/srv/state/config'),
                         ('/mnt',str(HOST_CONFIG_DIR))):
        for placement in ('A','B'):
            for host in pool:
                for container in pool:
                    theirs=placement_refusal(placement,host,container,state=state,config=config);mine=candidate_refusal(placement,host,container,state,config);compared+=1
                    if theirs==mine:agreed+=1
                    else:
                        # the candidate is the stricter one, and only by the two rules it keeps from the installer audit
                        assert theirs is None and mine in ('DATA_INSIDE_PRIVATE','PRIVATE_PATH_OVERLAP'),(placement,host,container,state,config,theirs,mine);stricter+=1
    assert compared==2*len(pool)**2*5 and agreed+stricter==compared and stricter>0 and agreed>10*stricter,(compared,agreed,stricter)

def test_substitution_key_set_is_exact():
    for values in (None,[],'x',{},{name:value for name,value in f.README_SAMPLE.items() if name!='NETWORK'},dict(f.README_SAMPLE,EXTRA='x'),
                   dict(f.README_SAMPLE,TZ='UTC')):
        assert refusal(check(values))=='SUBSTITUTION_KEYS'

def test_placeholder_counts_and_surviving_at_sign():
    text=f.SERVICE.decode()
    assert refusal(lambda:m.render_service(text.replace('@NETWORK@','bridge').encode(),f.README_SAMPLE))=='PLACEHOLDER_COUNTS'
    assert refusal(lambda:m.render_service((text+'# @IMAGE_ID@\n').encode(),f.README_SAMPLE))=='PLACEHOLDER_COUNTS'
    assert refusal(lambda:m.render_service((text+'# @TZ@\n').encode(),f.README_SAMPLE))=='PLACEHOLDER_COUNTS'
    assert refusal(lambda:m.render_service((text+'# operator@example\n').encode(),f.README_SAMPLE))=='UNRESOLVED_PLACEHOLDER'
    assert refusal(lambda:m.render_service((text+'# @lower@\n').encode(),f.README_SAMPLE))=='UNRESOLVED_PLACEHOLDER'

def test_profiles_are_bound_to_the_supervisor_names_in_code():
    reference=f.reference_render(f.README_SAMPLE)
    for name,profile,template,rendered,holders,code in (
            ('c3po-massive.service','VERBATIM_V1',f.TIMER,f.TIMER,{},'PROFILE_NAME_MISMATCH'),
            ('c3po-massive.service','GENERIC_KINDS_V1',f.SERVICE,reference,{},'PROFILE_NAME_MISMATCH'),
            ('c3po-massive.service','MASSIVE_SUPERVISOR_TIMER_V1',f.TIMER,f.TIMER,{},'PROFILE_NAME_MISMATCH'),
            ('c3po-massive.timer','VERBATIM_V1',f.TIMER,f.TIMER,{},'PROFILE_NAME_MISMATCH'),
            ('c3po-massive.timer','MASSIVE_SUPERVISOR_SERVICE_V1',f.SERVICE,reference,dict(f.README_SAMPLE),'PROFILE_NAME_MISMATCH'),
            ('c3po-reader.service','MASSIVE_SUPERVISOR_SERVICE_V1',f.SERVICE,reference,dict(f.README_SAMPLE),'PROFILE_NAME_MISMATCH'),
            ('c3po-reader.timer','MASSIVE_SUPERVISOR_TIMER_V1',f.TIMER,f.TIMER,{},'PROFILE_NAME_MISMATCH'),
            ('c3po-reader.service','UNKNOWN_V9',f.TIMER,f.TIMER,{},'PROFILE_UNKNOWN'),('c3po-reader.service',None,f.TIMER,f.TIMER,{},'PROFILE_UNKNOWN'),
            ('c3po-reader.service',['VERBATIM_V1'],f.TIMER,f.TIMER,{},'PROFILE_UNKNOWN')):
        assert refusal(lambda:m.render_unit(f.unit('X',name,profile,template,holders,rendered),ALLOW,VOLUME,'B'))==code,(name,profile)

def test_frozen_template_hash_template_encoding_and_signed_render():
    changed=f.SERVICE.replace(b'--cap-drop ALL',b'--cap-add ALL');reference=f.reference_render(f.README_SAMPLE)
    unit=f.unit('S','c3po-massive.service','MASSIVE_SUPERVISOR_SERVICE_V1',changed,dict(f.README_SAMPLE),f.reference_render(f.README_SAMPLE,changed))
    assert refusal(lambda:m.render_unit(unit,ALLOW,VOLUME,'B'))=='FROZEN_TEMPLATE_HASH'
    timer=f.unit('T','c3po-massive.timer','MASSIVE_SUPERVISOR_TIMER_V1',f.TIMER+b'#\n',{},f.TIMER+b'#\n')
    assert refusal(lambda:m.render_unit(timer,ALLOW,VOLUME))=='FROZEN_TEMPLATE_HASH'
    good=base64.b64encode(f.SERVICE).decode();alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    assert good.endswith('=') and not good.endswith('==')
    loose=good[:-2]+alphabet[alphabet.index(good[-2])+1]+'='          # same bytes, non-zero padding bits: a second encoding
    assert base64.b64decode(loose,validate=True)==f.SERVICE
    for value,code in ((good[:-4]+'!!!!','TEMPLATE_ENCODING'),(good+'\n','TEMPLATE_ENCODING'),(loose,'TEMPLATE_ENCODING'),
                       ('é','TEMPLATE_ENCODING'),(None,'TEMPLATE_TOO_LARGE'),(7,'TEMPLATE_TOO_LARGE'),('','TEMPLATE_TOO_LARGE'),
                       (base64.b64encode(b'x'*16385).decode(),'TEMPLATE_TOO_LARGE')):
        assert refusal(lambda:m.render_unit(service(f.README_SAMPLE,template_b64=value),ALLOW,VOLUME,'B'))==code,repr(value)[:40]
    for value in ('0'*64,None,f.sha(f.TIMER)):
        assert refusal(lambda:m.render_unit(service(f.README_SAMPLE,template_sha256=value),ALLOW,VOLUME,'B'))=='TEMPLATE_HASH_MISMATCH'
    binary=f.unit('B','c3po-reader.service','VERBATIM_V1','é=1\n'.encode(),{},'é=1\n'.encode())
    assert refusal(lambda:m.render_unit(binary,ALLOW,VOLUME))=='TEMPLATE_NOT_ASCII'
    for value in ('0'*64,None,f.sha(f.SERVICE),f.sha(reference).upper()):
        assert refusal(lambda:m.render_unit(service(f.README_SAMPLE,rendered_sha256=value),ALLOW,VOLUME,'B'))=='RENDERED_HASH_MISMATCH'
    for value in (1745,1747,None,'1746',1746.0,True):
        assert refusal(lambda:m.render_unit(service(f.README_SAMPLE,rendered_bytes=value),ALLOW,VOLUME,'B'))=='RENDERED_SIZE_MISMATCH'
    # a different value set with the old signed hash: the render is recomputed, never trusted
    other=sample(NETWORK='c3po_internal')
    assert refusal(lambda:m.render_unit(service(other),['c3po_internal'],VOLUME,'B'))=='RENDERED_HASH_MISMATCH'

GENERIC=b'[Service]\nEnvironment=DOCKER_CONFIG=@CONFIG_DIR@/docker-cli\nExecStart=/usr/bin/docker run --network @NETWORK@ --mount source=@CONFIG_DIR@ @IMAGE_ID@\n'
def holders(**changes):
    values={'CONFIG_DIR':{'kind':'ABSOLUTE_PATH','value':'/etc/c3po-reader','occurrences':2},
            'NETWORK':{'kind':'NETWORK','value':'c3po_internal','occurrences':1},
            'IMAGE_ID':{'kind':'IMAGE_ID','value':'sha256:'+'b'*64,'occurrences':1}}
    values.update(changes);return values
def generic(placeholders,template=GENERIC):
    rendered=template.decode()
    try:
        for name in sorted(placeholders):rendered=rendered.replace('@'+name+'@',str(placeholders[name]['value']))
    except Exception:pass
    return f.unit('G','c3po-reader.service','GENERIC_KINDS_V1',template,placeholders,rendered.encode())
def test_generic_profile_for_later_units_signed_kinds_counts_and_values():
    expected=GENERIC.replace(b'@CONFIG_DIR@',b'/etc/c3po-reader').replace(b'@NETWORK@',b'c3po_internal').replace(b'@IMAGE_ID@',b'sha256:'+b'b'*64)
    assert m.render_unit(generic(holders()),['c3po_internal'],None)==expected and b'@' not in expected
    verbatim=f.unit('V','c3po-reader-alert.service','VERBATIM_V1',b'[Unit]\nDescription=x\n',{},b'[Unit]\nDescription=x\n')
    assert m.render_unit(verbatim,ALLOW,None)==b'[Unit]\nDescription=x\n'
    for placeholders,code in (
            (holders(CONFIG_DIR={'kind':'ABSOLUTE_PATH','value':'/etc/c3po reader','occurrences':2}),'PATH_INVALID'),
            (holders(CONFIG_DIR={'kind':'ABSOLUTE_PATH','value':'/etc/../x','occurrences':2}),'PATH_COMPONENT'),
            (holders(CONFIG_DIR={'kind':'ABSOLUTE_PATH','value':'/etc/c3po-reader','occurrences':1}),'PLACEHOLDER_COUNTS'),
            (holders(CONFIG_DIR={'kind':'ABSOLUTE_PATH','value':'/etc/c3po-reader','occurrences':0}),'SUBSTITUTION_KEYS'),
            (holders(CONFIG_DIR={'kind':'SHELL','value':'/etc/c3po-reader','occurrences':2}),'SUBSTITUTION_KEYS'),
            (holders(CONFIG_DIR={'kind':'ABSOLUTE_PATH','value':'/etc/c3po-reader'}),'SUBSTITUTION_KEYS'),
            (holders(IMAGE_ID={'kind':'IMAGE_ID','value':'c3po/backend:production','occurrences':1}),'IMAGE_ID'),
            (holders(NETWORK={'kind':'NETWORK','value':'host','occurrences':1}),'NETWORK_NOT_AUTHORIZED'),
            (holders(NETWORK={'kind':'NETWORK','value':'bridge','occurrences':1}),'NETWORK_NOT_AUTHORIZED'),
            (holders(EXTRA={'kind':'IMAGE_ID','value':'sha256:'+'b'*64,'occurrences':1}),'PLACEHOLDER_COUNTS'),
            ({name:item for name,item in holders().items() if name!='NETWORK'},'PLACEHOLDER_COUNTS'),
            ({},'SUBSTITUTION_KEYS'),({'lower':{'kind':'IMAGE_ID','value':'sha256:'+'b'*64,'occurrences':1}},'SUBSTITUTION_KEYS')):
        assert refusal(lambda:m.render_unit(generic(placeholders),['c3po_internal'],None))==code,placeholders
    assert refusal(lambda:m.render_unit(generic(holders(),GENERIC+b'# root@host\n'),['c3po_internal'],None))=='UNRESOLVED_PLACEHOLDER'
    stray=f.unit('V','c3po-reader-alert.service','VERBATIM_V1',b'ExecStart=/bin/x @IMAGE_ID@\n',{},b'ExecStart=/bin/x @IMAGE_ID@\n')
    assert refusal(lambda:m.render_unit(stray,ALLOW,None))=='UNRESOLVED_PLACEHOLDER'
    assert refusal(lambda:m.render_unit(dict(stray,placeholders={'IMAGE_ID':'x'}),ALLOW,None))=='SUBSTITUTION_KEYS'
    many={'P%02d'%index:{'kind':'ABSOLUTE_PATH','value':'/'+'/'.join(['a'*49]*4),'occurrences':64} for index in range(16)}
    big=''.join(('@%s@\n'%name)*64 for name in sorted(many)).encode()
    assert len(big)<=16384 and refusal(lambda:m.render_unit(generic(many,big),ALLOW,None))=='RENDER_TOO_LARGE'

def test_extraction_is_a_parse_of_the_installed_bytes_not_a_second_render():
    reference=f.reference_render(f.README_SAMPLE)
    tricky=sample(HOST_CONFIG_DIR='/etc/c3po-bar/docker-cli');assert m.extract_values(f.SERVICE,f.reference_render(tricky))==tricky
    assert m.extract_values(f.SERVICE,reference.replace(b'--cap-drop ALL',b'--cap-add ALL')) is None
    assert m.extract_values(f.SERVICE,reference.replace(b'/etc/c3po-bar,target=',b'/etc/other,target=')) is None      # one occurrence differs
    assert m.extract_values(f.SERVICE,reference+b'ExecStartPost=/bin/true\n') is None
    assert m.extract_values(f.SERVICE,reference[:-1]) is None and m.extract_values(f.SERVICE,b'') is None
    assert m.extract_values(f.SERVICE,reference.replace(b'bridge',b'host net')) is None
    assert m.extract_values(f.SERVICE,reference.replace(b'sha256:'+b'a'*64,b'c3po/backend:production')) is None
    assert m.extract_values(f.SERVICE,'é'.encode()) is None and m.extract_values(f.TIMER,f.TIMER) is None
    # a value set that renders but differs from the signed one is extracted as what is on disk
    other=sample(NETWORK='c3po_internal');assert m.extract_values(f.SERVICE,f.reference_render(other))==other!=f.README_SAMPLE
