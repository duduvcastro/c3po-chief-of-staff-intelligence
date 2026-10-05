"""The systemctl rows of K5 (supervisor_activate), K13 (k13_reader_switch) and K13R (k13r_reader_liveness) on the runner's
real systemd, with STAND-IN units under the units' own names. The unit names, the property lists and the verbs are
read from the sealed op.py files by the syntax tree (never imported). What the emulations of these families cannot show:

  - `systemctl show <unit> -p ... -p ...` of an absent unit (exit, LoadState=not-found) and of a loaded one: which of
    the requested properties are printed, in which order (recorded: systemctl prints its own order), which a unit type
    lacks (a timer has no NRestarts, ExecMainStatus...);
  - `systemctl is-enabled` of a disabled and of an enabled timer (exit and word);
  - `systemctl enable --now <timer>` (exit; the manager reloaded by systemctl itself; the timer active and enabled,
    the enablement link), `start --no-block <service>` returning at once, a service ending with status 78 seen as
    Result=exit-code and ExecMainStatus=78, `reset-failed` clearing it, `disable --now`, `stop --no-block`;
  - `systemctl show docker.service` with K5's properties (the engine active);
  - the time of every call (the QUICK class is 8 s, SWITCH 30 s in the sources).

The stand-in service of K5 exits 78 at once (RestartPreventExitStatus=78, as the supervisor's refusal); the others run
/bin/true. The stand-in timers fire at 03:33 UTC only. Nothing else of the runner is touched; the stand-in unit files,
their links and their state are removed at the end and the manager reloaded.

For a THROWAWAY GitHub-hosted ubuntu-24.04 runner (systemd 255), as root. NEVER the production host (another systemd
version, the real units). It refuses unless Linux, uid 0, HOSTOPS_THROWAWAY_RUNNER=yes and RUNNER_ENVIRONMENT=github-hosted,
and unless none of the units exists.

usage: sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -I -B proof/systemd_shapes.py --out <file>
exit 0 only when every shape ran AND every expectation is met; 2 when a shape did not run; 3 when all ran and an
expectation is not met; 1 for a refusal.
"""
import json
import os
import subprocess
import sys
import time

HERE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.dirname(HERE)
sys.path.insert(0,HERE)
from docker_shapes import constants                      # the same syntax-tree reader of the sealed sources

SCHEMA='HOSTOPS02_K9_PROOF_SYSTEMD_SHAPES_V1'
SYSTEMCTL='/usr/bin/systemctl'
UNIT_DIRECTORY='/etc/systemd/system'
ENV={'PATH':'/usr/bin:/bin','LC_ALL':'C'}
QUICK=8;SWITCH=30
TIMINGS=[]

def refuse(text):
    sys.stderr.write('REFUSED: %s\n'%text);raise SystemExit(1)

def systemctl(*words,timeout=60):
    started=time.monotonic()
    done=subprocess.run([SYSTEMCTL]+list(words),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=timeout)
    elapsed=round(time.monotonic()-started,3)
    TIMINGS.append({'call':' '.join(words[:2]),'seconds':elapsed,'exit':done.returncode})
    return {'exit':done.returncode,'stdout':done.stdout.decode('utf-8','replace'),'stderr':done.stderr.decode('utf-8','replace').strip()[:300],'seconds':elapsed}

def show(unit,properties):
    tail=[part for key in properties for part in ('-p',key)]
    row=systemctl('show',unit,*tail)
    pairs=[line.split('=',1) for line in row['stdout'].splitlines() if '=' in line]
    keys=[pair[0] for pair in pairs]
    return {'exit':row['exit'],'seconds':row['seconds'],'values':dict(pairs),'printed_keys':keys,'missing_keys':[key for key in properties if key not in keys],
            'in_requested_order':keys==[key for key in properties if key in keys],'stderr':row['stderr']}

def families():
    with open(os.path.join(HERE,'UNITS.json'),'rb') as handle:units=json.load(handle)['units']
    out={}
    for suffix,names in (('supervisor_activate',('SERVICE_UNIT','TIMER_UNIT','DOCKER_UNIT','SERVICE_PROPERTIES','TIMER_PROPERTIES','DOCKER_PROPERTIES','REFUSAL_STATUS')),
                         ('k13_reader_switch',('SERVICE_UNIT','TIMER_UNIT','UNIT_PROPERTIES')),
                         ('k13r_reader_liveness',('SERVICE_UNIT','TIMER_UNIT','UNIT_PROPERTIES','TIMER_PROPERTIES'))):
        unit=next((row for row in units if row['dest'].rsplit('/',1)[-1]==suffix),None)
        if unit is None:continue
        values=constants(os.path.join(ROOT,unit['dest'],'op.py'),names)
        values['SERVICE_PROPERTIES']=values.get('SERVICE_PROPERTIES') or values.get('UNIT_PROPERTIES')
        values['TIMER_PROPERTIES']=values.get('TIMER_PROPERTIES') or values.get('UNIT_PROPERTIES')
        if not (values.get('SERVICE_UNIT') and values.get('TIMER_UNIT') and values['SERVICE_PROPERTIES'] and values['TIMER_PROPERTIES']):continue
        out[suffix]=dict(values,source=unit['dest']+'/op.py',seal=unit['seal_sha256'])
    return out

def write(path,text):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644);os.write(fd,text.encode());os.close(fd)

def stand_in(family,values):
    service,timer=values['SERVICE_UNIT'],values['TIMER_UNIT']
    status=values.get('REFUSAL_STATUS')
    exec_start='/bin/sh -c "exit %s"'%status if status else '/bin/true'
    write(os.path.join(UNIT_DIRECTORY,service),'[Unit]\nDescription=hostops02 K9 proof stand-in for %s (throwaway runner)\n\n[Service]\nType=simple\nExecStart=%s\n%s'
          %(family,exec_start,'Restart=on-failure\nRestartPreventExitStatus=%s\n'%status if status else ''))
    write(os.path.join(UNIT_DIRECTORY,timer),'[Unit]\nDescription=hostops02 K9 proof stand-in timer for %s (throwaway runner)\n\n[Timer]\nOnCalendar=*-*-* 03:33:00 UTC\n'
          'Persistent=false\nUnit=%s\n\n[Install]\nWantedBy=timers.target\n'%(family,service))

def remove(values):
    service,timer=values['SERVICE_UNIT'],values['TIMER_UNIT']
    systemctl('disable','--now',timer);systemctl('stop',service)
    for name in (service,timer):
        path=os.path.join(UNIT_DIRECTORY,name)
        if os.path.lexists(path):os.unlink(path)
    systemctl('daemon-reload');systemctl('reset-failed',service);systemctl('reset-failed',timer)

def wait_inactive(service,properties,seconds=20):
    for _ in range(seconds*2):
        row=show(service,properties)
        if row['values'].get('ActiveState') in ('inactive','failed') and row['values'].get('SubState') not in ('start','auto-restart'):return row
        time.sleep(0.5)
    return show(service,properties)

def one(family,values):
    service,timer=values['SERVICE_UNIT'],values['TIMER_UNIT'];sp,tp=values['SERVICE_PROPERTIES'],values['TIMER_PROPERTIES']
    rows={'absent_service':show(service,sp),'absent_timer':show(timer,tp)}
    rows['absent_is_enabled']=systemctl('is-enabled',timer)
    stand_in(family,values);systemctl('daemon-reload')
    try:
        rows['loaded_service']=show(service,sp);rows['loaded_timer']=show(timer,tp)
        rows['is_enabled_before']=systemctl('is-enabled',timer)
        rows['enable_now_timer']=systemctl('enable','--now',timer)
        rows['enablement_link']=os.path.islink(os.path.join(UNIT_DIRECTORY,'timers.target.wants',timer))
        rows['timer_after_enable']=show(timer,tp);rows['is_enabled_after']=systemctl('is-enabled',timer)
        rows['start_no_block']=systemctl('start','--no-block',service)
        rows['service_after_start']=wait_inactive(service,sp)
        rows['reset_failed']=systemctl('reset-failed',service)
        rows['service_after_reset']=show(service,sp)
        rows['disable_now_timer']=systemctl('disable','--now',timer)
        rows['timer_after_disable']=show(timer,tp)
        rows['stop_no_block']=systemctl('stop','--no-block',service)
        if values.get('DOCKER_UNIT') and values.get('DOCKER_PROPERTIES'):rows['docker']=show(values['DOCKER_UNIT'],values['DOCKER_PROPERTIES'])
    finally:
        remove(values)
    rows['after_cleanup_service']=show(service,sp)
    return rows

def expectations(out,found):
    checks={}
    for family,rows in out.items():
        if not rows.get('ok'):checks['%s: the shape ran'%family]=False;continue
        values=found[family];status=values.get('REFUSAL_STATUS')
        v=lambda name,key:(rows.get(name) or {}).get('values',{}).get(key)
        checks['%s: show of an absent unit exits 0 with LoadState=not-found'%family]=rows['absent_service']['exit']==0 and v('absent_service','LoadState')=='not-found'
        # which requested properties systemctl leaves out (empty values, properties of another unit type) is recorded in
        # missing_keys, not judged: the sources must read a line that is absent as absent
        checks['%s: show of the loaded service prints Id, LoadState, ActiveState and SubState'%family]=v('loaded_service','LoadState')=='loaded' \
            and all(key in rows['loaded_service']['printed_keys'] for key in ('Id','LoadState','ActiveState','SubState'))
        checks['%s: is-enabled of the disabled timer: exit not 0, "disabled"'%family]=rows['is_enabled_before']['exit']!=0 and rows['is_enabled_before']['stdout'].strip()=='disabled'
        checks['%s: enable --now of the timer: exit 0, enabled, active, the link made'%family]=rows['enable_now_timer']['exit']==0 and v('timer_after_enable','UnitFileState')=='enabled' \
            and v('timer_after_enable','ActiveState')=='active' and rows['enablement_link'] is True and rows['is_enabled_after']['stdout'].strip()=='enabled'
        checks['%s: start --no-block returns at once with exit 0'%family]=rows['start_no_block']['exit']==0 and rows['start_no_block']['seconds']<2
        if status:
            checks['%s: a service ending with %s is Result=exit-code, ExecMainStatus=%s, not restarted'%(family,status,status)]=v('service_after_start','Result')=='exit-code' \
                and v('service_after_start','ExecMainStatus')==status and v('service_after_start','NRestarts') in ('0',None)
            checks['%s: reset-failed clears it (Result=success)'%family]=rows['reset_failed']['exit']==0 and v('service_after_reset','Result')=='success'
        else:
            checks['%s: the service ran to its end (Result=success)'%family]=v('service_after_start','Result')=='success'
        checks['%s: disable --now: the timer inactive and disabled'%family]=rows['disable_now_timer']['exit']==0 and v('timer_after_disable','ActiveState')=='inactive' \
            and v('timer_after_disable','UnitFileState')=='disabled'
        checks['%s: stop --no-block exits 0'%family]=rows['stop_no_block']['exit']==0
        if 'docker' in rows:checks['%s: docker.service active'%family]=v('docker','ActiveState')=='active'
        checks['%s: nothing left (the service not-found after the cleanup)'%family]=v('after_cleanup_service','LoadState')=='not-found'
    checks['every QUICK call within %d s and every enable/disable within %d s'%(QUICK,SWITCH)]=all(row['seconds']<(SWITCH if row['call'].split()[0] in ('enable','disable','daemon-reload') else QUICK) for row in TIMINGS)
    return checks

def main(arguments):
    if len(arguments)!=2 or arguments[0]!='--out':refuse('usage: systemd_shapes.py --out <file>')
    if not sys.platform.startswith('linux') or os.geteuid()!=0:refuse('Linux and uid 0 only')
    if os.environ.get('HOSTOPS_THROWAWAY_RUNNER')!='yes' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':refuse('a throwaway GitHub-hosted runner only')
    found=families()
    for values in found.values():
        for name in (values['SERVICE_UNIT'],values['TIMER_UNIT']):
            if os.path.lexists(os.path.join(UNIT_DIRECTORY,name)) or show(name,('LoadState',))['values'].get('LoadState')!='not-found':refuse('%s exists: this is not a throwaway runner'%name)
    out={}
    for family,values in found.items():
        try:out[family]=dict(one(family,values),ok=True)
        except Exception as error:out[family]={'ok':False,'error':type(error).__name__,'message':str(error)[:300]}
    checks=expectations(out,found)
    version=systemctl('--version')['stdout'].splitlines()[:1]
    result={'schema':SCHEMA,'systemd':version,'families':{family:{'source':values['source'],'seal':values['seal'],'service':values['SERVICE_UNIT'],'timer':values['TIMER_UNIT']}
                                                         for family,values in found.items()},
            'shapes':out,'expectations':checks,'all_shapes_ran':bool(out) and all(row.get('ok') for row in out.values()),'all_expectations_met':all(checks.values()),'timings':TIMINGS}
    with open(arguments[1],'w',encoding='utf-8') as handle:handle.write(json.dumps(result,indent=1,sort_keys=True)+'\n')
    for key,value in checks.items():print('%s %s'%('MET  ' if value else 'UNMET',key))
    return 0 if result['all_shapes_ran'] and result['all_expectations_met'] else (2 if not result['all_shapes_ran'] else 3)

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
