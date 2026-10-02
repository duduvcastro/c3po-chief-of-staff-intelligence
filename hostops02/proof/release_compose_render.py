"""The compose file of the RELEASE (c3po/compose.yml at dd4ec4bb), rendered on a real engine by the helpers of the two
sealed sources that will read it on the host: the epoch readback (K11: render_base, render_override) and activate
(K6a: render). `docker compose config` loads, interpolates and prints; it creates nothing. No project is started
from this file here, and none named c3po exists on a throwaway runner.

What it adds to the shapes of the two operations, which render a minimal project written by the job: the rule both
sources apply to the worker's volumes (activate: service_of; readback: data_bind_of) is applied to what the runner's
compose plugin prints for the REAL service, with its three volumes, and the size and duration of the REAL render are
held against the class (1 MiB, 15 s). DESIGN.md of activate: UA-1, UA-2, UA-6; of the readback: K11-U6; CORE.md: U4, U6.

The tree is a throwaway one prepared by release_image.sh, shaped like the deploy tree: <work>/deploy/.env (one line,
the data mount source), <work>/deploy/c3po (a copy of the checkout's c3po directory), <work>/data.

For a THROWAWAY GitHub-hosted ubuntu-24.04 runner, as root. It refuses anywhere else. NOT RUN by its author on a real
engine. --self-test runs the same collection on the emulated engine of the core (a canned render): it proves that this
script is coherent with the two sources, and nothing about a real compose plugin.

usage: sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -B release_compose_render.py <work directory>
       python3 -B release_compose_render.py --self-test
exit 0 only when every shape ran AND every expectation is met; 2 when a shape did not run; 3 when all ran and an
expectation is not met; 1 for a refusal. One JSON object on standard output: structure and booleans, never a value
of the environment file or of a service's environment.
"""
import json
import os
import sys
import time

HERE=os.path.dirname(os.path.abspath(__file__))
FAMILY=os.path.dirname(HERE)
sys.path.insert(0,os.path.join(FAMILY,'core','tests'))
import family as f

SCHEMA='HOSTOPS02_PROOF_RELEASE_COMPOSE_RENDER_V1'
REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
PROJECT='c3po'
TARGET='/app/day-d-data'
LIMIT=1048576

def plan_of(data,deploy,project=PROJECT,target=TARGET):
    """The members activate's environment_of, override_of and service_of read, for the places Monday's request signs."""
    return {'data_root':data,'live_parent':[{'path':data+'/r2d2-v2-live'}],'directory_name':'2026-10-05','policy':{'name':'policy.json','sha256':'5'*64},
            'override_name':'compose.override.json',
            'release':{'parent':[{'path':data}],'directory_name':'r2d2-v2-release-20261005','file_name':'release.CERTIFIED.json','sha256':'6'*64},
            'worker':{'image_id':'sha256:'+'0'*64,'mount_target':target},
            'compose':{'project':project,'env_file':deploy+'/.env','files':[deploy+'/'+project+'/compose.yml']}}

def collect(a,m,host_a,host_m,plan,gate=lambda:55.0):
    """a: the module of activate; m: the module of the epoch readback. A failure is a row, never an exception."""
    out={};ca=a.Commands(host_a,gate);cm=m.Commands(host_m,gate);compose=plan['compose'];arguments=(compose['project'],compose['env_file'],compose['files'])
    service=a.WORKER_SERVICE;expected=a.environment_of(plan);kept={}
    def shape(label,action):
        try:out[label]=dict(action(),ok=True)
        except Exception as error:
            out[label]={'ok':False,'error':type(error).__name__,'code':str(error)[:80] if isinstance(error,ValueError) else None}
    def volumes_of(rendered):
        rows=rendered['services'][service].get('volumes')
        return [{'keys':sorted(item),'type':item.get('type'),'target':item.get('target'),'read_only':item.get('read_only'),
                 'source_is_the_data_root':a.plain(item.get('source'))==plan['data_root']} for item in rows] if type(rows) is list else None
    def base():
        started=time.monotonic();raw=cm.output('render_base',*m.compose_arguments(*arguments),variables={'C3PO_BUILD_SHA':REVISION})
        seconds=round(time.monotonic()-started,2);rendered=m.strict(raw,LIMIT);row=m.compose_service(rendered,service);environment=row['environment']
        return {'seconds':seconds,'output_bytes':len(raw),'services':len(rendered['services']),'worker_volumes':volumes_of(rendered),
                'build_revision_is_the_variable':environment.get(a.BUILD_KEY)==REVISION,'override_names_absent':not [key for key in expected if key in environment]}
    def override():
        started=time.monotonic();rendered=m.compose_render(cm,'render_override',*arguments,REVISION,override=a.override_of(plan))
        seconds=round(time.monotonic()-started,2);kept['readback']=rendered;row=m.compose_service(rendered,service)
        paths=[expected[a.KEY_POLICY_FILE],expected[a.KEY_RELEASE_FILE]]
        return {'seconds':seconds,'worker_volumes':volumes_of(rendered),'override_names_equal':all(row['environment'].get(key)==value for key,value in expected.items()),
                'readback_rule_for_the_data_bind':m.data_bind_of(rendered['services'][service].get('volumes'),paths,plan['data_root'],plan['worker']['mount_target'])}
    def activate():
        started=time.monotonic();rendered=a.compose_render(ca,'render',*arguments,REVISION,override=a.override_of(plan))
        seconds=round(time.monotonic()-started,2);accepted=a.service_of(rendered,plan)
        return {'seconds':seconds,'accepted_by_service_of':set(accepted)=={'image','environment'},'image_reference':accepted['image'],
                'the_same_object_the_readback_received':'readback' in kept and rendered==kept['readback']}
    def wrong_target():
        other=dict(plan,worker=dict(plan['worker'],mount_target='/app/elsewhere'))
        rendered=a.compose_render(ca,'render',*arguments,REVISION,override=a.override_of(other))
        try:a.service_of(rendered,other)
        except a.Refused as error:return {'refused':True,'code':str(error)}
        return {'refused':False,'code':None}
    shape('readback_render_of_the_file_list',base);shape('readback_render_with_the_override_on_standard_input',override)
    shape('activate_render_with_the_override_on_standard_input',activate);shape('activate_rule_on_a_target_the_render_does_not_bind',wrong_target)
    return out

def expectations(out):
    base=out.get('readback_render_of_the_file_list',{});over=out.get('readback_render_with_the_override_on_standard_input',{})
    act=out.get('activate_render_with_the_override_on_standard_input',{});wrong=out.get('activate_rule_on_a_target_the_render_does_not_bind',{})
    volumes=over.get('worker_volumes') or [];data=[row for row in volumes if row.get('target')==TARGET]
    return {
        'U4/UA-1 compose renders the compose file of the release as root with the fixed environment (no HOME), from the file list and with the override on standard input':
            base.get('ok') is True and over.get('ok') is True and act.get('ok') is True,
        'compose interpolates C3PO_BUILD_SHA from the variable of the call, and the four names come only from the override':
            base.get('build_revision_is_the_variable') is True and base.get('override_names_absent') is True and over.get('override_names_equal') is True,
        'K11-U6/UA-2 every volume of the worker is printed in the long form with a target, and the data root is one bind at the signed target, not read-only':
            bool(volumes) and all(type(row.get('target')) is str and row['target'] for row in volumes) and len(data)==1
            and (data[0].get('type'),data[0].get('source_is_the_data_root'))==('bind',True) and data[0].get('read_only') in (None,False),
        'UA-2 activate accepts what the render says of the worker of the real compose file':act.get('accepted_by_service_of') is True,
        'K11-U6 the readback gives the same verdict by its own rule':over.get('readback_rule_for_the_data_bind') is True,
        'the two sources receive the same object for the same file list and override':act.get('the_same_object_the_readback_received') is True,
        'a target the render does not bind is refused by the rule of activate':(wrong.get('refused'),wrong.get('code'))==(True,'WORKER_MOUNT_NOT_AS_SIGNED'),
        'U6/UA-6 the render of the real file fits its class (1 MiB, 15 s)':type(base.get('output_bytes')) is int and 0<base['output_bytes']<=LIMIT
            and all(type(row.get('seconds')) in (int,float) and row['seconds']<15 for row in (base,over,act)),
    }

def report(out):
    met=expectations(out);ran=all(row.get('ok') for row in out.values())
    return {'schema':SCHEMA,'revision':REVISION,'shapes':out,'expectations':met,'every_shape_ran':ran,'every_expectation_met':all(met.values())},(0 if ran and all(met.values()) else 3 if ran else 2)

def emulated():
    """--self-test: the emulated host of activate's tests (its compose answers with a canned render of the project)."""
    sys.path.insert(0,os.path.join(FAMILY,'activate','tests'))
    import hostemu
    import k6a
    k=k6a.load();host=k6a.world(k);other=f.load(os.path.join(FAMILY,'epoch_readback'))
    assert (hostemu.REVISION,hostemu.PROJECT,k6a.TARGET)==(REVISION,PROJECT,TARGET)
    return k.m,other.m,host,f.wire(other,host),plan_of(hostemu.DATA,hostemu.DEPLOY)

def main(arguments):
    if arguments==['--self-test']:
        result,code=report(collect(*emulated()));sys.stdout.write(json.dumps(dict(result,self_test_on_the_emulation=True),sort_keys=True)+'\n');return code
    if len(arguments)!=1:
        sys.stdout.write(__doc__);return 1
    if not (sys.platform.startswith('linux') and os.geteuid()==0 and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'):
        sys.stdout.write('REFUSED: a throwaway GitHub-hosted Linux runner as root only\n');return 1
    work=arguments[0];deploy,data=work+'/deploy',work+'/data'
    if not (os.path.isfile(deploy+'/.env') and os.path.isfile(deploy+'/'+PROJECT+'/compose.yml') and os.path.isdir(data) and os.stat(work).st_uid==0):
        sys.stdout.write('REFUSED: the work directory is not the tree release_image.sh prepares\n');return 1
    a=f.load(os.path.join(FAMILY,'activate')).m;m=f.load(os.path.join(FAMILY,'epoch_readback')).m
    result,code=report(collect(a,m,a.Native(),m.Native(),plan_of(data,deploy)));sys.stdout.write(json.dumps(result,sort_keys=True)+'\n');return code

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
