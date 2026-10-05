"""K2a on a real engine: the operation's own perform(), command table, helpers, runner and Native, in both modes, on the
layout of supervisor operation 2 created on a throwaway runner, with an image that holds the application modules of
the release at /app. It is what closes, before the host, the shapes DESIGN.md lists as K2A-U1, U2, U3, U5 and U6: the
README's attached run with the pinned script on standard input, the two docker reads under an empty DOCKER_CONFIG,
the identity of the bound directory in the container against the host's, no container left after `--rm`, and the
readback through a descriptor held since before the run. K2A-U4 (the production image) and K2A-U7 (a timeout) stay
open. The order is the order of the host: the rehearsal first, which gives docker a directory of its own, and only
then the real run, the first docker command under the configuration directory of the unit.

The paths are the fixed ones of the operation part (its layout floor refuses any other): /etc/c3po-bar/docker-cli,
/var/lib/c3po-bar/journal, and a throwaway in /var/lib. run_catalog.sh creates them and refuses when any exists.

For a THROWAWAY GitHub-hosted ubuntu-24.04 runner, as root (run_catalog.sh prepares it). NEVER the production host: it
creates containers and directories. It refuses to run anywhere else: Linux, effective uid 0, HOSTOPS_THROWAWAY_RUNNER=yes
and RUNNER_ENVIRONMENT=github-hosted are all required. NOT RUN by its author: no Linux and no docker were available
offline. --self-test runs the same collection against the emulated engine of the core's tests/hostemu.py; it proves
that this script is coherent with the source, and nothing about a real engine.

perform() is entered directly, after validate_plan(), with a gate that only counts the 60 seconds: the documents, the
date set and the windows are the conformance suite's ground and do not depend on the engine.

usage: sudo -n env ... /usr/bin/python3 -I -B linux_root/catalog_shape.py <image ID> <revision label>
           <image ID>        local ID of an image with python and the release's c3po/backend/app at /app/app
           <revision label>  the 40-hex org.opencontainers.image.revision label that image carries
           the layout, prepared by run_catalog.sh, root:root 0700 and empty: /etc/c3po-bar/docker-cli and
           /var/lib/c3po-bar/journal, each in its 0700 parent; nothing named c3po-bar-rehearsal-ci in /var/lib
           prints one JSON object: every run, and the expectations the operation relies on, each as a boolean
       /usr/bin/python3 -B linux_root/catalog_shape.py --self-test
exit 0 only when every run was made AND every expectation is met; 2 when a run was not made; 3 when all were made and an
expectation is not met; 1 for a refusal.
"""
import json
import os
import sys
import time

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(os.path.dirname(HERE),'tests'))
import conftest                                    # puts the tests of the frozen core on the path
import family as f
import hostemu
import k2a

SCHEMA='HOSTOPS02_K2A_LINUX_ROOT_SHAPE_V1'
TARGET='/c3po-bar-journal'
THROWAWAY='c3po-bar-rehearsal-ci'
DIAG='R2D2-V2-DIAG-K2A-CI'
BOUND={'request_sha256':'1'*64,'authority_sha256':'2'*64,'go_sha256':'3'*64,'payload_sha256':'4'*64,'host_binding_sha256':'5'*64}

def plans(m,host,image,revision):
    """Both plans, with every row read from the tree as a read-only receipt would give it."""
    gate=lambda:55.0
    def rows(path):
        found=[];host.close(m.descend(host,path,gate,found));return found
    boot=m.boot_id_sha256(host,gate)
    common={'container_journal_root':TARGET,'docker_config_chain':rows(k2a.CONFIG),'image_id':image,'image_revision':revision,
            'script_sha256':m.CATALOG_SCRIPT_SHA256,'evidence_boot_id_sha256':boot}
    rehearsal=dict(common,mode='REHEARSAL',journal_chain=rows(k2a.PARENT),throwaway_name=THROWAWAY,reference_chain=rows(k2a.JOURNAL),epoch=DIAG)
    real=dict(common,mode='REAL',journal_chain=rows(k2a.JOURNAL),throwaway_name=None,reference_chain=None,epoch=m.EPOCH_COMPILED)
    return rehearsal,real

def one(m,host,plan):
    """validate_plan, then perform with a clock of its own. Returns the receipt; a failure is a row, never an exception."""
    from datetime import datetime,timezone
    started=time.monotonic()
    def gate():
        left=60.0-(time.monotonic()-started)
        if left<=0:raise m.Refused('GO_EXPIRED')
        return left
    try:
        m.validate_plan(plan)
        receipt=m.perform(plan,gate,host,dict(BOUND),lambda:datetime.now(timezone.utc),time.monotonic,m.Effects())
        return dict(receipt,ok=True)
    except Exception as error:
        return {'ok':False,'error':type(error).__name__,'code':str(error)[:80] if isinstance(error,ValueError) else None}

def collect(m,host,image,revision):
    rehearsal,real=plans(m,host,image,revision)
    out={'rehearsal':one(m,host,rehearsal),'real':one(m,host,real),'real_again_on_the_initialised_root':one(m,host,real)}
    return out

def expectations(out):
    """What the operation relies on, read from the runs: one boolean per statement, False when its run was not made."""
    rehearsal=out.get('rehearsal',{});real=out.get('real',{});again=out.get('real_again_on_the_initialised_root',{})
    def line(run):return run.get('script_line') or {}
    def root(run):return run.get('journal_root') or {}
    def catalog(run):return run.get('catalog') or {}
    def complete(run,outcome):return run.get('status')=='METADATA_ONLY_REQUIRES_REVIEW' and run.get('outcome')==outcome and run.get('code') is None
    both=(rehearsal,real)
    return {
        'K2A-U1 the README run on the throwaway root ends in the verified rehearsal outcome':complete(rehearsal,'REHEARSAL_CATALOG_READY_VERIFIED'),
        'K2A-U1 the README run on the root that stands for the real one ends in the verified outcome':complete(real,'CATALOG_READY_VERIFIED'),
        'K2A-U1 the script printed one CATALOG_READY line with created true and the signed epoch':all(line(run).get('as_signed') is True for run in both),
        'K2A-U1 uid 0 without capabilities wrote the two files 0600 root:root through the read-write bind':all(
            all((catalog(run).get('files') or {}).get(name,{}).get(key)==value for name in ('epoch.json','maintenance.lock')
                for key,value in (('type','file'),('uid',0),('gid',0),('mode_octal','0600'),('links',1))) for run in both),
        'K2A-U1 epoch.json holds the canonical bytes for the epoch and the identity of the root':all((catalog(run).get('epoch_json') or {}).get('equal_to_the_expected_bytes') is True for run in both),
        'K2A-U2 image inspect and ps run under the empty DOCKER_CONFIG':all((run.get('precheck') or {}).get('image')=={'id_as_signed':True,'revision_as_signed':True}
                                                                          and type((run.get('precheck') or {}).get('containers')) is int for run in both),
        'K2A-U2 the docker CLI wrote nothing into the configuration directory':all((run.get('docker_config') or {}).get('entries_after')==0
                                                                                   and (run.get('precheck') or {}).get('docker_config_entries_after_the_reads')==0 for run in both),
        'the rehearsal gave docker a directory of its own and the real run the directory of the unit':(
            (rehearsal.get('docker_config') or {}).get('path')==k2a.PARENT+'/'+THROWAWAY+'.docker-cli' and (rehearsal.get('docker_config') or {}).get('is_the_directory_of_the_unit') is False
            and (real.get('docker_config') or {}).get('path')==k2a.CONFIG and (real.get('docker_config') or {}).get('is_the_directory_of_the_unit') is True),
        'K2A-U3 the container saw the device and inode the host sees':all(line(run).get('device') is not None and (line(run).get('device'),line(run).get('inode'))==(root(run).get('device'),root(run).get('inode')) for run in both),
        'K2A-U5 no container is listed after the run that was not there before':all((run.get('containers') or {}).get('status')=='COMPLETE' and (run.get('containers') or {}).get('not_there_before')==0 for run in both),
        'K2A-U6 the held descriptor lists the two entries the container created':all(catalog(run).get('entries')==2 and catalog(run).get('other_entries')==0 and catalog(run).get('root_unchanged') is True for run in both),
        'K2A-U1 the run fits its class (40 s)':all(type((run.get('run') or {}).get('seconds')) in (int,float) and run['run']['seconds']<40 for run in both),
        'the rehearsal created its two directories durably and left the root that stands for the real one empty':(
            [(row.get('key'),row.get('state')) for row in rehearsal.get('directories') or []]==[('DOCKER_CONFIG','CREATED_DURABLE'),('JOURNAL_ROOT','CREATED_DURABLE')]
            and (rehearsal.get('precheck') or {}).get('real_journal_root_entries')==0 and (rehearsal.get('precheck') or {}).get('docker_config_entries')==0),
        'a second run on the initialised root is refused before any container is started':(again.get('status'),again.get('code'),again.get('run'))==('REFUSED','JOURNAL_ROOT_NOT_EMPTY',None),
    }

def report(out):
    checks=expectations(out);return {'schema':SCHEMA,'runs':out,'expectations':checks,'all_runs_made':all(row.get('ok') for row in out.values()),'all_expectations_met':all(checks.values())}

def emulated():
    """The emulated engine and host for --self-test, with the layout run_catalog.sh prepares (operation 2, placement A)."""
    k,host=k2a.world();host.docker.on_run=lambda call:k2a.catalog_model(call,call.command[4:])
    return k.m,host,hostemu.BACKEND,hostemu.REVISION

def main(arguments):
    if arguments==['--self-test']:
        m,host,image,revision=emulated();result=report(collect(m,host,image,revision))
        print(json.dumps(result,indent=1,sort_keys=True));return 0 if result['all_runs_made'] and result['all_expectations_met'] else 3 if result['all_runs_made'] else 2
    if len(arguments)!=2:
        print(__doc__);return 1
    if not (sys.platform.startswith('linux') and os.geteuid()==0 and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'):
        print('REFUSED: a throwaway GitHub-hosted Linux runner, as root, with HOSTOPS_THROWAWAY_RUNNER=yes',file=sys.stderr);return 1
    image,revision=arguments;m=k2a.K().m
    result=report(collect(m,m.Native(),image,revision))
    print(json.dumps(result,indent=1,sort_keys=True));return 0 if result['all_runs_made'] and result['all_expectations_met'] else 3 if result['all_runs_made'] else 2

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
