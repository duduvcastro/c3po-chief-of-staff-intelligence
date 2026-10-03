"""C3 on a real engine: the operation's own perform(), command table, helpers, runner and Native, with the probe's own
argv on the network bridge of a throwaway runner, against stand-ins INSIDE the runner (linux_root/stubs.py): a DNS
server that the engine gives the network bridge (run.sh sets the daemon's "dns" to the gateway of that network) and
that answers the provider's name with the gateway, and a TLS server on the gateway's port 443 with a certificate of a
throwaway authority made by run.sh. The provider is never contacted: the container's resolver is checked to be the
stand-in before any probe runs, and run.sh rejects every forwarded connection of the bridge to port 443 or 53 and
counts what it rejected.

The authority is trusted only by a TEST image (the release's base by digest, with the authority appended to its
default bundle at build time); a second image, the base as it is, does not trust it. The sealed source is not changed
in any way: it runs its pinned script with the default verifying context, and whether that context trusts the
authority is a property of the image alone.

What it shows, each as a boolean (the expectations below): the network bridge, no bind, --rm and no leftover (by the
source's own listing, by `docker events` and by an inspect of the running container); the TLS path verified for the
provider's name against the server's leaf; the refusals of verification (an authority the image does not trust, a
certificate of another name); a refused port; a name that does not exist; a handshake never answered, bounded by the
script's own seconds; and that no application byte reached the server.

For a THROWAWAY GitHub-hosted ubuntu-24.04 runner, as root (run.sh prepares it). NEVER the production host. It refuses
to run anywhere else: Linux, effective uid 0, HOSTOPS_THROWAWAY_RUNNER=yes and RUNNER_ENVIRONMENT=github-hosted are
all required. NOT RUN by its author: no Linux and no docker were available offline. --self-test runs the same
collection against the emulated engine of the core's tests/hostemu.py; it proves that this script is coherent with the
source, and nothing about a real engine.

perform() is entered directly, after validate_members(), with a gate that only counts the 60 seconds: the documents,
the date set, the band and the windows are the conformance suite's ground and do not depend on the engine.

usage: sudo -n env ... /usr/bin/python3 -I -B linux_root/probe_shape.py <work directory> <gateway>
           <work directory>  made by run.sh: ca.pem, leaf.pem, leaf.key, other.pem, other.key, images.json
           <gateway>         the IPv4 gateway of the network bridge, as `docker network inspect bridge` prints it
       /usr/bin/python3 -B linux_root/probe_shape.py --self-test
exit 0 only when every run was made AND every expectation is met; 2 when a run was not made; 3 when all were made and
an expectation is not met; 1 for a refusal.
"""
import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
import threading
import time
from datetime import datetime,timezone

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
sys.path.insert(0,os.path.join(os.path.dirname(HERE),'tests'))
import conftest                                    # puts the tests of the frozen core on the path
import family as f
import hostemu
import c3
import stubs

SCHEMA='HOSTOPS02_TLS_PROBE_LINUX_ROOT_SHAPE_V1'
DOCKER='/usr/bin/docker'
SLEEPER=b'import time\ntime.sleep(5)\n'
# One probe per situation: which image, what the DNS stand-in answers, what the TLS stand-in does; and the verdict
# the source must give.
CASES=[('verified','trusting','answer','good',('METADATA_ONLY_REQUIRES_REVIEW','TLS_VERIFIED_TO_THE_PROVIDER_HOST',None)),
       ('image_without_the_test_authority','stock','answer','good',('PARTIAL_METADATA_REQUIRES_REVIEW','PROBE_RAN_TLS_NOT_VERIFIED','TLS_CERTIFICATE_NOT_VERIFIED')),
       ('certificate_of_another_name','trusting','answer','other_name',('PARTIAL_METADATA_REQUIRES_REVIEW','PROBE_RAN_TLS_NOT_VERIFIED','TLS_CERTIFICATE_NOT_VERIFIED')),
       ('port_refused','trusting','answer','closed',('PARTIAL_METADATA_REQUIRES_REVIEW','PROBE_RAN_TLS_NOT_VERIFIED','TCP_REFUSED')),
       ('name_not_found','trusting','nxdomain','good',('PARTIAL_METADATA_REQUIRES_REVIEW','PROBE_RAN_TLS_NOT_VERIFIED','DNS_NAME_NOT_RESOLVED')),
       ('handshake_never_answered','trusting','answer','hang',('PARTIAL_METADATA_REQUIRES_REVIEW','PROBE_RAN_TLS_NOT_VERIFIED','TLS_HANDSHAKE_TIMEOUT'))]

def bound(label):
    digest=hashlib.sha256(label.encode()).hexdigest()
    return {'request_sha256':'1'*64,'authority_sha256':'2'*64,'go_sha256':digest,'payload_sha256':'4'*64,'host_binding_sha256':'5'*64}

def plan_of(m,host,image):
    gate=lambda:55.0
    return {'image_id':image['id'],'image_revision':m.RELEASE_REVISION,'retention_tag':image['tag'],'script_sha256':m.PROBE_SCRIPT_SHA256,
            'evidence_boot_id_sha256':m.boot_id_sha256(host,gate)}

def one(m,host,plan,label):
    """validate_members, then perform with a clock of its own. Returns the receipt; a failure is a row, never an exception."""
    started=time.monotonic()
    def gate():
        left=60.0-(time.monotonic()-started)
        if left<=0:raise m.Refused('GO_EXPIRED')
        return left
    try:
        m.validate_members(plan)
        receipt=m.perform(plan,gate,host,bound(label),lambda:datetime.now(timezone.utc),time.monotonic,m.Effects())
        return dict(receipt,ok=True,container_name=m.container_name(bound(label)))
    except Exception as error:
        return {'ok':False,'error':type(error).__name__,'code':str(error)[:80] if isinstance(error,ValueError) else None}


class Real:
    """The engine of the runner, the two stand-ins on the gateway, and the source's own Native."""
    def __init__(self,m,work,gateway):
        self.m,self.work,self.gateway=m,work,gateway
        with open(os.path.join(work,'images.json')) as handle:self.images=json.load(handle)
        self.certificates={'ca':os.path.join(work,'ca.pem')}
        for name in ('leaf','other'):self.certificates.update({name:os.path.join(work,name+'.pem'),name+'_key':os.path.join(work,name+'.key')})
        with open(self.certificates['leaf']) as handle:self.leaf_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(handle.read())).hexdigest()
        self.dns=stubs.DnsStub(gateway,53);self.tls=stubs.TlsStub(gateway,443,self.certificates)
    def host(self):return self.m.Native()
    def situation(self,dns,tls):self.dns.mode=dns;self.tls.set_mode(tls)
    def docker(self,*arguments,stdin=None,timeout=40):
        done=subprocess.run([DOCKER]+list(arguments),input=stdin,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env={'PATH':'/usr/bin:/bin'},timeout=timeout)
        return done.returncode,done.stdout
    def resolver(self):
        """The name servers a container of the network bridge gets, and what the provider's name resolves to in it."""
        image=self.images['stock']['id'];base=['run','--rm','-i','--pull','never','--network','bridge','--read-only','--cap-drop','ALL',image,'python','-I','-B','-']
        code,out=self.docker(*base,stdin=b"import re,sys\nsys.stdout.write(' '.join(re.findall(r'^nameserver\\s+(\\S+)',open('/etc/resolv.conf').read(),re.M)))\n")
        servers=out.decode().split() if code==0 else None
        self.situation('answer','good')
        code,out=self.docker(*base,stdin=b"import socket,sys\nsys.stdout.write(' '.join(sorted({row[4][0] for row in socket.getaddrinfo('socket.massive.com',443,0,socket.SOCK_STREAM)})))\n")
        return {'name_servers_are_the_stand_in':servers==[self.gateway],'provider_name_resolves_to_the_stand_in_only':code==0 and out.decode().split()==[self.gateway]}
    def shape(self):
        """The source's own row and helper, with a sleeping snippet in place of the probe so that the container can be
        inspected while it runs; then the listing. Returns the facts as booleans."""
        m=self.m;commands=m.Commands(self.host(),lambda:55.0);name=m.CONTAINER_PREFIX+'5'*16;image=self.images['stock']['id'];result={}
        runner=threading.Thread(target=lambda:result.update(m.container_run(commands,m.RUN_ROW,image,[],m.PROBE_COMMAND,SLEEPER,container_name=name)))
        runner.start();found=None;deadline=time.monotonic()+4
        while found is None and time.monotonic()<deadline:
            code,out=self.docker('container','inspect','--format','{{json .}}',name,timeout=8)
            if code==0:found=json.loads(out)
            else:time.sleep(0.2)
        runner.join(30)
        code,image_raw=self.docker('image','inspect','--format','{{json .Config.Env}}',image,timeout=8)
        code_after,listed=self.docker('ps','-a','--no-trunc','--format','{{.Names}}',timeout=8)
        return facts_of(found,json.loads(image_raw) if code==0 else None,name,image,result,listed.decode().split() if code_after==0 else None)
    def events(self,since,until,name):
        code,out=self.docker('events','--since',str(int(since)),'--until',str(int(until)+1),'--format','{{json .}}',timeout=20)
        return [json.loads(line) for line in out.decode().splitlines() if line.strip()] if code==0 else None
    def close(self):
        self.dns.close();self.tls.close()


def facts_of(found,image_environment,name,image,result,listed):
    host_config=(found or {}).get('HostConfig') or {};config=(found or {}).get('Config') or {}
    return {'inspected_while_running':found is not None,
            'network_bridge_only':host_config.get('NetworkMode')=='bridge' and sorted(((found or {}).get('NetworkSettings') or {}).get('Networks') or {})==['bridge'],
            'no_bind_no_mount_no_volume':not host_config.get('Binds') and not (found or {}).get('Mounts') and not host_config.get('Mounts') and not config.get('Volumes'),
            'removed_by_the_engine_on_exit':host_config.get('AutoRemove') is True,
            'read_only_root_filesystem':host_config.get('ReadonlyRootfs') is True,
            'no_capability':host_config.get('CapDrop') in (['ALL'],['all']) and not host_config.get('CapAdd') and host_config.get('Privileged') is False
                            and not host_config.get('Devices'),
            'no_new_privileges_and_an_init':host_config.get('SecurityOpt')==['no-new-privileges'] and host_config.get('Init') is True,
            'uid_0':config.get('User')=='0:0',
            'image_by_id_and_the_command':(found or {}).get('Image')==image and config.get('Cmd')==['python','-I','-B','-'],
            'no_variable_added_to_the_image_environment':image_environment is not None and config.get('Env')==image_environment,
            'standard_input_attached_once':config.get('OpenStdin') is True and config.get('StdinOnce') is True,
            'the_run_returned_zero':result.get('returned') is True and result.get('returncode')==0,
            'no_container_of_its_name_listed_after_the_run':listed is not None and name not in listed}

def event_facts(events,name):
    """From the engine's events of the verified probe: created, attached to bridge, started, ended 0, destroyed."""
    if events is None:return {'events_read':False}
    mine=[event for event in events if event.get('Type')=='container' and (event.get('Actor') or {}).get('Attributes',{}).get('name')==name]
    actions=[event.get('Action') for event in mine];ids={(event.get('Actor') or {}).get('ID') for event in mine}
    networks=[event for event in events if event.get('Type')=='network' and (event.get('Actor') or {}).get('Attributes',{}).get('container') in ids]
    return {'events_read':True,
            'created_started_died_destroyed_in_order':[action for action in actions if action in ('create','start','die','destroy')]==['create','start','die','destroy'],
            'one_container':len(ids)==1,
            'attached_to_bridge_only':bool(networks) and all((event.get('Actor') or {}).get('Attributes',{}).get('name')=='bridge' for event in networks)
                                      and any(event.get('Action')=='connect' for event in networks),
            'ended_with_status_0':[(event.get('Actor') or {}).get('Attributes',{}).get('exitCode') for event in mine if event.get('Action')=='die']==['0']}


def collect(engine):
    m=engine.m;out={'resolver':engine.resolver(),'cases':{},'server':{},'events':None,'shape':None}
    if not all(out['resolver'].values()):
        out['not_run']='the container of the network bridge does not resolve through the stand-in: no probe is started'
        return out
    host=engine.host()
    for label,image,dns,tls,_ in CASES:
        engine.situation(dns,tls);before=len(engine.tls.connections);questions=len(engine.dns.questions);since=time.time()
        receipt=one(m,host,plan_of(m,host,engine.images[image]),label)
        out['cases'][label]=receipt
        out['server'][label]={'connections':engine.tls.connections[before:],'questions':engine.dns.questions[questions:]}
        if label=='verified':out['events']=event_facts(engine.events(since,time.time(),receipt.get('container_name')),receipt.get('container_name'))
    engine.situation('answer','good')
    out['shape']=engine.shape()
    return out

def expectations(out,leaf_sha256):
    cases=out.get('cases') or {};server=out.get('server') or {};verified=cases.get('verified') or {}
    def verdict(run):return (run.get('status'),run.get('outcome'),run.get('code'))
    def probe(run):return run.get('probe') or {}
    def tls(run):return probe(run).get('tls') or {}
    def connections(label):return (server.get(label) or {}).get('connections') or []
    questions=[question for label in server for question in (server[label] or {}).get('questions') or []]
    every=[cases.get(label) or {} for label,_,_,_,_ in CASES]
    return {
        'the container of the network bridge asks the stand-in, and the provider name resolves to the stand-in only':bool(out.get('resolver')) and all(out['resolver'].values()),
        'every probe ends in the verdict of its situation':all(verdict(cases.get(label) or {})==expected for label,_,_,_,expected in CASES),
        'the verified probe names the leaf the server presented, for the provider name':tls(verified).get('leaf_sha256')==leaf_sha256 and tls(verified).get('verified') is True
            and tls(verified).get('version') in ('TLSv1.2','TLSv1.3'),
        'the server saw the provider name and no application byte':connections('verified')==[{'mode':'good','server_name':'socket.massive.com','handshake':True,'application_bytes':0}],
        'an image without the test authority does not verify (unknown issuer)':tls(cases.get('image_without_the_test_authority') or {}).get('verify_code') in (19,20),
        'a certificate of another name does not verify (host name mismatch)':tls(cases.get('certificate_of_another_name') or {}).get('verify_code')==62,
        'no connection reaches a refused port and none follows a name that does not exist':'port_refused' in server and 'name_not_found' in server
            and connections('port_refused')==[] and connections('name_not_found')==[],
        'the handshake that is never answered ends at the script bound, far inside the class':(lambda run:type((run.get('container') or {}).get('seconds')) in (int,float)
            and 4<=run['container']['seconds']<14 and 4000<=tls(run).get('ms',0)<5000)(cases.get('handshake_never_answered') or {}),
        'every probe ran under 20 s and left no container':all(type((run.get('container') or {}).get('seconds')) in (int,float) and run['container']['seconds']<20
                                                            and run.get('container_removed') is True for run in every),
        'every probe started exactly one container and read four times':all(run.get('commands_started')=={'READ':4,'CONTAINER':1,'EFFECT':0} for run in every),
        'the stand-in DNS was asked for the provider name only':bool(questions) and all(question['name']=='socket.massive.com' for question in questions),
        'the engine created, attached to bridge only, started, ended 0 and destroyed the verified probe':bool(out.get('events')) and all(out['events'].values()),
        'the running container has the network bridge, no bind, --rm, a read-only root, no capability, uid 0, the image by ID':bool(out.get('shape')) and all(out['shape'].values()),
    }

def report(out,leaf_sha256):
    checks=expectations(out,leaf_sha256);cases=out.get('cases') or {}
    made=len(cases)==len(CASES) and all(run.get('ok') for run in cases.values()) and out.get('shape') is not None
    return {'schema':SCHEMA,'runs':out,'expectations':checks,'all_runs_made':made,'all_expectations_met':all(checks.values())}


class Emulated:
    """The emulated engine of the core's tests, with the two stand-ins modelled: every answer of the container is the
    model line of tests/c3.py for the situation, and the inspect and the events are derived from the parsed argv."""
    def __init__(self):
        k,host=c3.world();self.m=k.m;self._host=host;self.leaf_sha256=c3.LEAF;self.gateway='gateway'
        trusting=c3.backend(host);stock=json.loads(json.dumps(trusting));stock['Id']='sha256:'+'5a'*32;stock['RepoTags']=['c3po/backend:massive-supervisor-ci-stock']
        trusting['RepoTags'].append('c3po/backend:massive-supervisor-ci-trusting');host.docker.images.append(stock)
        self.images={'trusting':{'id':trusting['Id'],'tag':'c3po/backend:massive-supervisor-ci-trusting'},'stock':{'id':stock['Id'],'tag':stock['RepoTags'][0]}}
        self.dns=type('Dns',(),{'mode':'answer','questions':[]})();self.tls=type('Tls',(),{'mode':'good','connections':[]})()
        self.calls=[];host.docker.on_run=self.container
    def host(self):return self._host
    def situation(self,dns,tls):self.dns.mode=dns;self.tls.mode=tls
    def container(self,call):
        self.calls.append(call)
        if call.stdin!=self.m.script_bytes():return 0,b''
        c3.assert_probe_run(call,call.image);assert call.image in (self.images['trusting']['id'],self.images['stock']['id'])
        self.dns.questions.append({'name':'socket.massive.com','type':1,'mode':self.dns.mode})
        if self.dns.mode=='nxdomain':return 0,c3.line_bytes(c3.model_line('nxdomain'))
        if self.tls.mode=='closed':return 0,c3.line_bytes(c3.model_line('refused'))
        trusting=call.image==self.images['trusting']['id']
        if self.tls.mode=='hang':
            self.tls.connections.append({'mode':'hang','server_name':None,'handshake':False,'application_bytes':None});time.sleep(4.05)
            line=c3.model_line('hang');line['tls']['ms']=4002;line['total_ms']=4010;return 0,c3.line_bytes(line)
        self.tls.connections.append({'mode':self.tls.mode,'server_name':'socket.massive.com','handshake':trusting and self.tls.mode=='good',
                                     'application_bytes':0 if trusting and self.tls.mode=='good' else None})
        if not trusting:return 0,c3.line_bytes(c3.model_line('untrusted'))
        return 0,c3.line_bytes(c3.model_line('other_name' if self.tls.mode=='other_name' else 'verified'))
    def resolver(self):return {'name_servers_are_the_stand_in':True,'provider_name_resolves_to_the_stand_in_only':True}
    def shape(self):
        m=self.m;commands=m.Commands(self._host,lambda:55.0);name=m.CONTAINER_PREFIX+'5'*16;image=self.images['stock']['id']
        result=m.container_run(commands,m.RUN_ROW,image,[],m.PROBE_COMMAND,SLEEPER,container_name=name);call=self.calls[-1]
        found={'Image':call.image,'HostConfig':{'NetworkMode':call.network,'Binds':None,'AutoRemove':'--rm' in call.flags,'ReadonlyRootfs':call.read_only_root,
                                                 'CapDrop':call.options.get('--cap-drop'),'CapAdd':None,'Privileged':False,'Devices':[],
                                                 'SecurityOpt':call.options.get('--security-opt'),'Init':'--init' in call.flags},
               'Config':{'User':call.options['--user'][0],'Cmd':call.command,'Env':['PATH=/usr/local/bin:/usr/bin'],'OpenStdin':'-i' in call.flags,
                         'StdinOnce':'-i' in call.flags,'Volumes':None},
               'Mounts':[{'source':mount['source']} for mount in call.mounts],'NetworkSettings':{'Networks':{call.network:{}}}}
        listed=[row['name'] for row in m.container_list(commands)]
        return facts_of(found,['PATH=/usr/local/bin:/usr/bin'],name,image,result,listed)
    def events(self,since,until,name):
        identifier='e'*64
        return [{'Type':'container','Action':action,'Actor':{'ID':identifier,'Attributes':dict({'name':name},**({'exitCode':'0'} if action=='die' else {}))}}
                for action in ('create',)]+[{'Type':'network','Action':'connect','Actor':{'ID':'n'*64,'Attributes':{'container':identifier,'name':'bridge'}}}]+[
               {'Type':'container','Action':action,'Actor':{'ID':identifier,'Attributes':dict({'name':name},**({'exitCode':'0'} if action=='die' else {}))}}
                for action in ('start','die','destroy')]
    def close(self):pass

def main(arguments):
    if arguments==['--self-test']:
        engine=Emulated()
        try:result=report(collect(engine),engine.leaf_sha256)
        finally:engine.close()
        print(json.dumps(result,indent=1,sort_keys=True));return 0 if result['all_runs_made'] and result['all_expectations_met'] else 3 if result['all_runs_made'] else 2
    if len(arguments)!=2:
        print(__doc__);return 1
    if not (sys.platform.startswith('linux') and os.geteuid()==0 and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'):
        print('REFUSED: a throwaway GitHub-hosted Linux runner, as root, with HOSTOPS_THROWAWAY_RUNNER=yes',file=sys.stderr);return 1
    work,gateway=arguments
    if not re.fullmatch(r'(?:[0-9]{1,3}\.){3}[0-9]{1,3}',gateway):
        print('REFUSED: the gateway is not an IPv4 address',file=sys.stderr);return 1
    engine=Real(c3.K().m,work,gateway)
    try:result=report(collect(engine),engine.leaf_sha256)
    finally:engine.close()
    print(json.dumps(result,indent=1,sort_keys=True));return 0 if result['all_runs_made'] and result['all_expectations_met'] else 3 if result['all_runs_made'] else 2

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
