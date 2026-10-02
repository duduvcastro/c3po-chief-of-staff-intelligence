"""The command shapes this family has never run on any Linux host, executed with the sources' own command tables,
runner and parsers, and what the manager says of the two units before they are installed, once they are installed
without a reload, and after a reload.

For a THROWAWAY GitHub-hosted ubuntu-24.04 runner, as root (run.sh prepares it). NEVER the production host: one
shape adds an image tag. It refuses to run anywhere else: Linux, effective uid 0, HOSTOPS_THROWAWAY_RUNNER=yes and
RUNNER_ENVIRONMENT=github-hosted are all required. NOT RUN by the author of this candidate: no Linux, no docker and
no systemd were available offline. --self-test runs the same collection against the emulated CLI of
tests/hostemu.py; it proves that this script is coherent with the sources, and nothing about a real engine.

usage: sudo -n env ... /usr/bin/python3 -I -B linux_root/shapes.py --manager <label>
           one JSON line: what the manager says of the two units now (run.sh calls it before the installation and
           again before the reload, and hands the lines to the run below)
       sudo -n env ... /usr/bin/python3 -I -B linux_root/shapes.py <image ID> [<file of --manager lines>]
           one JSON object: every shape, and the expectations the sources rely on, each as a boolean
       /usr/bin/python3 -B linux_root/shapes.py --self-test
exit 0 only when every shape ran and parsed AND every expectation is met; 2 when a shape did not run; 3 when all ran
and an expectation is not met; 1 for a refusal.
"""
import json
import os
import sys
import tempfile

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(os.path.dirname(HERE),'tests'))
import family as f
import hostemu

SCHEMA='HOSTOPS01_LINUX_ROOT_SHAPES_V2'
REFERENCE='c3po/backend:massive-supervisor-ci-probe'
SNAPSHOT_LABELS=('before_installation','installed_no_daemon_reload')
CONTAINERD=['driver-type','io.containerd.snapshotter.v1']

def manager(readback,r):
    """systemctl --version, show with the ten properties for each unit, is-enabled of the timer: the readback's own
    argv table and parser."""
    result={'version_line':r.output('systemd_version').split(b'\n',1)[0].decode('ascii','replace')}
    for name in readback.UNITS:
        values,missing=readback.properties(r.output('unit:'+name),readback.UNIT_PROPERTIES)
        result[name]={'properties':values,'missing':missing,'argv_properties':len(readback.UNIT_PROPERTIES)}
    code,raw=r.call('timer_enabled');result['is_enabled']={'returncode':code,'word':raw.decode('ascii','replace').strip()}
    return result

def collect(provision,readback,provision_host,readback_host,image_id,config_directory,count):
    """Each shape with the source's own argv and parser. Returns {shape: result}; a failure is a row, never an exception."""
    gate=lambda:30.0;out={}
    p=provision.Commands(provision_host,gate);r=readback.Commands(readback_host,gate)
    def shape(name,action):
        try:out[name]=dict(action(),ok=True)
        except Exception as error:
            out[name]={'ok':False,'error':type(error).__name__,'code':str(error)[:80] if isinstance(error,ValueError) else None}
    def image_ls():
        rows=provision.listing(p);inspected=provision.image_facts(p,image_id)
        return {'argv':provision.COMMANDS['image_ls'][1],'rows':len(rows),'tags':sorted(row['tag'] for row in rows),
                'inspect_id_equals_the_given_id':inspected['id']==image_id,
                'listing_shows_the_inspect_id':any(row['id']==inspected['id'] for row in rows)}
    def image_tag():
        code,_=p.call('image_tag',image_id,REFERENCE,capture=False);after=provision.image_facts(p,REFERENCE)
        return {'returncode':code,'readback_id_equal':after['id']==image_id,'reference_among_repo_tags':after['reference_among_repo_tags']}
    def empty_config():
        before=count(config_directory);info=readback.decode(r.output('info',docker_config=config_directory))
        version=readback.strict(r.output('version',docker_config=config_directory));after=count(config_directory)
        return {'entries_before':before,'entries_after':after,'info_keys':sorted(info),'init_binary':info.get('init_binary'),'server_version':version,
                'driver':info.get('driver'),'driver_status':info.get('driver_status')}
    shape('image_ls_no_trunc_format',image_ls);shape('image_tag_on_an_id',image_tag)
    shape('is_enabled_and_show_with_ten_properties',lambda:manager(readback,r));shape('docker_info_under_an_empty_docker_config',empty_config)
    return out

def expectations(out,units):
    """What the sources rely on, read from the shapes: one boolean per statement, False when its shape did not run.
    L3 OP_PROVISION refuses (TAG_LISTING_INCONSISTENT) unless the listing shows the ID that inspect prints.
    L4 OP_PROVISION calls the tag verified only when inspect by reference prints the ID and lists the reference.
    L5 OP_READBACK needs every one of the ten properties, a unit systemd itself parses (LoadState loaded after a
       reload, at its installed path) and the word "disabled" for the timer.
    L6 OP_READBACK hands docker an empty configuration directory and gates on it staying empty."""
    ls=out.get('image_ls_no_trunc_format',{});tag=out.get('image_tag_on_an_id',{})
    seen=out.get('is_enabled_and_show_with_ten_properties',{});config=out.get('docker_info_under_an_empty_docker_config',{})
    rows=[seen.get(name) or {} for name in units]
    def loaded(name,row):
        values=row.get('properties') or {}
        return values.get('LoadState')=='loaded' and values.get('FragmentPath')=='/etc/systemd/system/'+name
    return {
        'L3_the_image_store_is_the_containerd_snapshotter':CONTAINERD in (config.get('driver_status') or []),
        'L3_the_listing_shows_the_id_that_inspect_prints':bool(ls.get('ok') and ls.get('inspect_id_equals_the_given_id') and ls.get('listing_shows_the_inspect_id')),
        'L4_a_tag_on_an_image_id_reads_back_with_the_id_and_the_reference':bool(tag.get('ok') and tag.get('returncode')==0 and tag.get('readback_id_equal')
                                                                                   and tag.get('reference_among_repo_tags')),
        'L5_show_answers_every_one_of_the_ten_properties':bool(seen.get('ok') and all(row.get('missing')==[] and row.get('argv_properties')==10 for row in rows)),
        'L5_after_a_reload_both_units_are_loaded_from_their_installed_path':bool(seen.get('ok') and all(loaded(name,row) for name,row in zip(units,rows))),
        'L5_is_enabled_says_disabled_for_the_timer':bool(seen.get('ok') and (seen.get('is_enabled') or {}).get('word')=='disabled'),
        'L6_the_empty_docker_config_stays_empty':bool(config.get('ok') and config.get('entries_before')==0 and config.get('entries_after')==0),
        'L6_info_and_version_parse_under_the_empty_docker_config':bool(config.get('ok') and type(config.get('init_binary')) is str and config.get('init_binary')
                                                                       and config.get('server_version')),
    }

def emulated():
    provision=f.load('provision').m;readback=f.load('readback').m;host=hostemu.world();host.refused=readback.Refused
    host.tree.add('/etc/c3po-bar/docker-cli',mode=0o700);host.is_enabled['c3po-massive.timer']='disabled'
    for name in readback.UNITS:host.units[name]={'Id':name,'LoadState':'loaded','ActiveState':'inactive','SubState':'dead','UnitFileState':'disabled',
                                               'FragmentPath':'/etc/systemd/system/'+name}
    return provision,readback,host

def self_test():
    provision,readback,host=emulated()
    out=collect(provision,readback,host,host,hostemu.BACKEND,'/etc/c3po-bar/docker-cli',lambda path:len(host.tree.get(path).children))
    assert all(row['ok'] for row in out.values()),out
    assert out['image_ls_no_trunc_format']=={'argv':['image','ls','--no-trunc','--format',provision.LS_FORMAT,'c3po/backend'],'rows':2,'tags':['production','rollback'],
        'inspect_id_equals_the_given_id':True,'listing_shows_the_inspect_id':True,'ok':True}
    assert out['image_tag_on_an_id']=={'returncode':0,'readback_id_equal':True,'reference_among_repo_tags':True,'ok':True}
    seen=out['is_enabled_and_show_with_ten_properties']
    assert seen['is_enabled']=={'returncode':1,'word':'disabled'} and seen['c3po-massive.timer']['missing']==[] and seen['c3po-massive.timer']['argv_properties']==10
    assert seen['c3po-massive.service']['properties']['LoadState']=='loaded' and seen['version_line'].startswith('systemd 255')
    config=out['docker_info_under_an_empty_docker_config'];assert (config['entries_before'],config['entries_after'],config['init_binary'])==(0,0,'docker-init')
    assert config['driver_status']==[CONTAINERD] and config['driver']=='overlayfs'
    assert [command['docker_config'] for command in host.commands if command['argv'][1] in ('info','version')]==['/etc/c3po-bar/docker-cli']*2
    assert [command['argv'][1:3] for command in host.commands if command['argv'][1:3]==['image','tag']]==[['image','tag']]
    met=expectations(out,readback.UNITS);assert len(met)==8 and all(value is True for value in met.values()),met
    assert status_of(out,met)==0
    # every expectation is decided by what was seen: one fact changed at a time turns exactly its own statement false
    def changed(shape,**change):
        other=json.loads(json.dumps(out));other[shape].update(change);return sorted(name for name,value in expectations(other,readback.UNITS).items() if not value)
    assert changed('image_ls_no_trunc_format',listing_shows_the_inspect_id=False)==['L3_the_listing_shows_the_id_that_inspect_prints']
    assert changed('image_tag_on_an_id',reference_among_repo_tags=False)==['L4_a_tag_on_an_image_id_reads_back_with_the_id_and_the_reference']
    assert changed('image_tag_on_an_id',returncode=1)==['L4_a_tag_on_an_image_id_reads_back_with_the_id_and_the_reference']
    assert changed('is_enabled_and_show_with_ten_properties',is_enabled={'returncode':0,'word':'enabled'})==['L5_is_enabled_says_disabled_for_the_timer']
    assert changed('docker_info_under_an_empty_docker_config',entries_after=1)==['L6_the_empty_docker_config_stays_empty']
    assert changed('docker_info_under_an_empty_docker_config',driver_status=[['Backing Filesystem','extfs']])==['L3_the_image_store_is_the_containerd_snapshotter']
    other=json.loads(json.dumps(out));other['is_enabled_and_show_with_ten_properties']['c3po-massive.service']['properties']['LoadState']='bad-setting'
    unmet=expectations(other,readback.UNITS);assert [name for name,value in unmet.items() if not value]==['L5_after_a_reload_both_units_are_loaded_from_their_installed_path']
    assert status_of(other,unmet)==3
    assert status_of(out,met,[{'ok':True},{'ok':True}])==0 and status_of(out,met,[{'ok':True},{'ok':False}])==2 and status_of(out,met,[{'ok':False,'error':'MANAGER_SNAPSHOTS_INVALID'}])==2
    # the manager line run.sh takes before the installation: both units not-found, no answer from is-enabled
    provision,readback,bare=emulated();bare.units.pop('c3po-massive.service');bare.units.pop('c3po-massive.timer');bare.is_enabled.clear()
    line=manager_line(readback,bare,'before_installation');row=json.loads(line)
    assert line.count('\n')==0 and row['label']=='before_installation' and row['ok'] is True and row['manager']['c3po-massive.timer']['properties']['LoadState']=='not-found'
    assert row['manager']['is_enabled']=={'returncode':1,'word':''} and snapshots_of([line,line.replace('before_installation','installed_no_daemon_reload')])[1]['label']=='installed_no_daemon_reload'
    for bad in ([line,line],['{}'],['not json'],[line]*3):
        try:snapshots_of(bad);raise AssertionError('accepted')
        except ValueError:pass
    # a shape that cannot run is a row with ok false, and the exit code says so
    broken=hostemu.world();broken.refused=readback.Refused;broken.tree.remove('/usr/bin/docker')
    out=collect(provision,readback,broken,broken,hostemu.BACKEND,'/etc',lambda path:0)
    assert [row['ok'] for row in out.values()]==[False,False,True,False] and out['image_tag_on_an_id']['code']=='BINARY_UNAVAILABLE_OR_UNSAFE'
    met=expectations(out,readback.UNITS);assert status_of(out,met)==2 and not any(value for name,value in met.items() if not name.startswith('L5'))
    assert allowed({'HOSTOPS_THROWAWAY_RUNNER':'yes','RUNNER_ENVIRONMENT':'github-hosted'},'linux',0) is True
    for environment,platform,uid in (({'HOSTOPS_THROWAWAY_RUNNER':'yes','RUNNER_ENVIRONMENT':'self-hosted'},'linux',0),({'RUNNER_ENVIRONMENT':'github-hosted'},'linux',0),
                                     ({'HOSTOPS_THROWAWAY_RUNNER':'yes'},'linux',0),({'HOSTOPS_THROWAWAY_RUNNER':'yes','RUNNER_ENVIRONMENT':'github-hosted'},'darwin',0),
                                     ({'HOSTOPS_THROWAWAY_RUNNER':'yes','RUNNER_ENVIRONMENT':'github-hosted'},'linux',1001)):
        assert allowed(environment,platform,uid) is False
    return 'SELF_TEST_OK emulated CLI only; nothing here was run against a real engine'

def status_of(out,met,snapshots=None):
    """2 when a shape, or one of the manager lines taken before the reload, did not run; 3 when all ran and an expectation is not met."""
    if not all(row['ok'] for row in out.values()) or (snapshots is not None and not all(row.get('ok') is True for row in snapshots)):return 2
    return 0 if all(met.values()) else 3

def allowed(environment,platform,uid):
    """A throwaway GitHub-hosted Linux runner, as root, and said so twice. Never a self-hosted runner, never a host."""
    return bool(platform=='linux' and uid==0 and environment.get('HOSTOPS_THROWAWAY_RUNNER')=='yes' and environment.get('RUNNER_ENVIRONMENT')=='github-hosted')

def manager_line(readback,host,label):
    """One JSON line for run.sh: the manager's view now. A failure is a row with ok false."""
    try:row={'label':label,'ok':True,'manager':manager(readback,readback.Commands(host,lambda:30.0))}
    except Exception as error:row={'label':label,'ok':False,'error':type(error).__name__,'code':str(error)[:80] if isinstance(error,ValueError) else None}
    return json.dumps(row,sort_keys=True)

def snapshots_of(lines):
    """The --manager lines taken earlier by run.sh, in order: exactly the two labels, each once."""
    rows=[json.loads(line) for line in lines if line.strip()]
    if [row.get('label') if type(row) is dict else None for row in rows]!=list(SNAPSHOT_LABELS):raise ValueError('MANAGER_SNAPSHOTS_INVALID')
    return rows

def main():
    arguments=sys.argv[1:]
    if arguments==['--self-test']:
        print(self_test());return 0
    if not allowed(os.environ,sys.platform,os.geteuid()):
        print('REFUSED: a throwaway GitHub-hosted Linux runner (RUNNER_ENVIRONMENT=github-hosted), root and HOSTOPS_THROWAWAY_RUNNER=yes are required');return 1
    readback=f.load('readback').m
    if len(arguments)==2 and arguments[0]=='--manager' and arguments[1] in SNAPSHOT_LABELS:
        print(manager_line(readback,readback.Native(),arguments[1]));return 0
    if len(arguments) not in (1,2) or not arguments[0].startswith('sha256:'):
        print('REFUSED: one image ID, and optionally the file of --manager lines, are required');return 1
    snapshots=None
    if len(arguments)==2:
        try:
            with open(arguments[1],encoding='ascii') as handle:snapshots=snapshots_of(handle.read(262144).splitlines())
        except (OSError,ValueError):snapshots=[{'ok':False,'error':'MANAGER_SNAPSHOTS_INVALID'}]       # the shapes below still run
    provision=f.load('provision').m
    directory=tempfile.mkdtemp(prefix='hostops-empty-docker-config-')           # 0700, empty, root's
    out=collect(provision,readback,provision.Native(),readback.Native(),arguments[0],directory,lambda path:len(os.listdir(path)))
    try:os.rmdir(directory);removed=True                                         # only when it is still empty
    except OSError:removed=False
    met=expectations(out,readback.UNITS);status=status_of(out,met,snapshots)
    print(json.dumps({'schema':SCHEMA,'image_id':arguments[0],'shapes':out,'expectations':met,'every_shape_ran':status!=2,'every_expectation_met':status==0,
                      'manager_before_the_reload':snapshots,'python':sys.version.split()[0],'empty_docker_config_removed_empty':removed,
                      'exit_status':status},indent=1,sort_keys=True))
    return status

if __name__=='__main__':raise SystemExit(main())
