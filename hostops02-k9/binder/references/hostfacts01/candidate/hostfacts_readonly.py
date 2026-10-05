"""Read-only host facts for the Massive supervisor activation gates.

Observations only: metadata and versions. No shell, network, write, container
command, application import or systemd verb other than show/--version. No
environment value of any container enters this process. The only file contents
this process reads are /proc/<pid>/uid_map and /proc/<pid>/gid_map of the selected
containers; what the fixed tools do on their own is listed in SCOPE side_effects.
The caller authenticates exact request/authority/GO/source bytes first; every
step rechecks the signed UTC window and a monotonic deadline. A failed
observation is reported unavailable with a reason code and makes the receipt
PARTIAL; it is never reported as absent. No action on import.
"""
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import selectors
import stat
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone


class Refused(ValueError): pass
class CommandFailed(Refused):
    def __init__(self,code,returncode):
        Refused.__init__(self,code);self.returncode=returncode
def need(ok,code):
    if not ok:raise Refused(code)

OPERATION='GO_READONLY_SUPERVISOR_HOSTFACTS_01'
PHASE='READONLY_HOSTFACTS'
DATE='2026-10-02'
REQUEST_SCHEMA='READONLY_SUPERVISOR_HOSTFACTS_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_SUPERVISOR_HOSTFACTS_AUTHORITY_V1'
GO_SCHEMA='READONLY_SUPERVISOR_HOSTFACTS_GO_V1'
RECEIPT_SCHEMA='READONLY_SUPERVISOR_HOSTFACTS_RECEIPT_V1'
COLLECTION_SCHEMA='SUPERVISOR_READONLY_HOSTFACTS_REQUEST_V1'
OBSERVATION_SCHEMA='SUPERVISOR_READONLY_HOSTFACTS_OBSERVATION_V1'
COMPLETE_STATUS='METADATA_ONLY_REQUIRES_REVIEW'
PARTIAL_STATUS='PARTIAL_METADATA_REQUIRES_REVIEW'

MAX_SECONDS=60
CALL_SECONDS=8
MAX_TOOL_TIMEOUTS=2
MAX_COMMAND_BYTES=64*1024
MAX_LISTED=64
MAX_RUNNING=32
MAX_FAMILY=12
MAX_MOUNTS=16
MAX_NETWORKS=8
MAX_MAP_LINES=8
MAX_MAP_BYTES=4096
MAX_ENTRIES=200
MAX_ENTRY_COUNT=100000
MAX_DEPTH=16
MAX_TAGS=8
MAX_IMAGES=4
MAX_SOURCES=3
MAX_PROBLEMS=64
RECEIPT_LIMIT=60000
SEAL_OVERHEAD=100
PID_MAX=4194304

DATA_DESTINATION='/app/day-d-data'
PROJECT_LABEL='com.docker.compose.project'
SERVICE_LABEL='com.docker.compose.service'
ONEOFF_LABEL='com.docker.compose.oneoff'
REVISION_LABEL='org.opencontainers.image.revision'
PROJECT='c3po'
SERVICES=['api','investor-relations-worker','r2d2-shadow-candidate-worker','r2d2-worker','server-usage-worker','valuation-worker']
INIT_CANDIDATES=['/usr/bin/docker-init','/usr/libexec/docker/docker-init','/usr/local/bin/docker-init','/usr/sbin/docker-init']
TREES=['/etc/c3po-bar','/var/lib/c3po-bar','/opt/c3po-bar']
ACCOUNT='c3po-bar'
UNIT_DIRECTORY='/etc/systemd/system'
ZONEINFO='/usr/share/zoneinfo/America/New_York'
DOCKER_UNIT='docker.service'
UNITS=['c3po-massive.service','c3po-massive.timer']
STATVFS_PATHS=['/','/var/lib']
ENTRY_PATTERN='[A-Za-z0-9._=-]{1,64}'
# A name outside the pattern is never emitted. The filesystem's own lost+found is reported by a fixed token instead.
WELL_KNOWN_ENTRIES={'lost+found':'LOST_AND_FOUND'}
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker'],'systemctl':['/usr/bin/systemctl','/bin/systemctl'],
          'timedatectl':['/usr/bin/timedatectl','/bin/timedatectl'],'getent':['/usr/bin/getent','/bin/getent']}
MOUNT_BASIS=('"/" is reported true by definition; any other component is a mount point when its st_dev differs '
             'from its parent; a bind mount of the same filesystem is not detectable this way')

# Docker templates. Every template that names .Id runs in the CLI raw-JSON
# fallback (missingkey=error), the only inspect mode proven on this host, so
# each optional key is reached through index and never by a dotted reference.
def _label(key):
    return '{{with index .Config "Labels"}}{{json (index . "'+key+'")}}{{else}}null{{end}}'
PS_FORMAT='{"id":{{json .ID}},"name":{{json .Names}},"state":{{json .State}}}'
CLASS_FORMAT=('{"id":{{json .Id}},"running":{{json .State.Running}},"project":'+_label(PROJECT_LABEL)
              +',"service":'+_label(SERVICE_LABEL)+',"oneoff":'+_label(ONEOFF_LABEL)+'}')
FAMILY_FORMAT=('{"name":{{json .Name}},"id":{{json .Id}},"image_id":{{json .Image}},'
               '"image_reference":{{json .Config.Image}},"running":{{json .State.Running}},'
               '"state":{{json .State.Status}},"started_at":{{json .State.StartedAt}},'
               '"host_pid":{{json .State.Pid}},"restarts":{{json .RestartCount}},'
               '"project":'+_label(PROJECT_LABEL)+',"service":'+_label(SERVICE_LABEL)
               +',"oneoff":'+_label(ONEOFF_LABEL)+',"revision":'+_label(REVISION_LABEL)
               +',"user":{{json (index .Config "User")}},"userns_mode":{{json (index .HostConfig "UsernsMode")}},'
               '"readonly_rootfs":{{json (index .HostConfig "ReadonlyRootfs")}},'
               '"network_mode":{{json (index .HostConfig "NetworkMode")}},'
               '"networks":[{{range $k, $v := index .NetworkSettings "Networks"}}{{json $k}},{{end}}null],'
               '"mounts":[{{range $m := index . "Mounts"}}{"type":{{json (index $m "Type")}},'
               '"source":{{json (index $m "Source")}},"destination":{{json (index $m "Destination")}},'
               '"rw":{{json (index $m "RW")}}},{{end}}null]}')
IMAGE_FORMAT=('{"id":{{json .Id}},"repo_tags":{{json (index . "RepoTags")}},"revision":'
              '{{with index . "Config"}}{{with index . "Labels"}}{{json (index . "'+REVISION_LABEL+'")}}'
              '{{else}}null{{end}}{{else}}null{{end}}}')
VERSION_FORMAT='{{json .Server.Version}}'
INFO_FIELDS=[('security_options','SecurityOptions'),('driver','Driver'),('driver_status','DriverStatus'),
             ('docker_root_dir','DockerRootDir'),('init_binary','InitBinary'),('server_version','ServerVersion')]
# One docker info call for all six fields: the CLI runs its plugin round (see SIDE_EFFECTS) once, not six times.
INFO_FORMAT='{'+','.join('"'+key+'":{{json .'+field+'}}' for key,field in INFO_FIELDS)+'}'
TEMPLATES={'PS_FORMAT':PS_FORMAT,'CLASS_FORMAT':CLASS_FORMAT,'FAMILY_FORMAT':FAMILY_FORMAT,
           'IMAGE_FORMAT':IMAGE_FORMAT,'VERSION_FORMAT':VERSION_FORMAT,'INFO_FORMAT':INFO_FORMAT}

# The exact fixed argv prefixes. The signed request carries this table, so the
# commands this process starts are the signed bytes by construction. What those
# tools start or contact on their own is not argv of this process: SIDE_EFFECTS.
COMMANDS={'ps':['docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None],
          'class':['docker',['container','inspect','--format',CLASS_FORMAT],'64-hex container id from ps'],
          'family':['docker',['container','inspect','--format',FAMILY_FORMAT],'64-hex container id from ps'],
          'image':['docker',['image','inspect','--format',IMAGE_FORMAT],'sha256 image id of a family container'],
          'info':['docker',['info','--format',INFO_FORMAT],None],
          'version':['docker',['version','--format',VERSION_FORMAT],None],
          'systemd_version':['systemctl',['--version'],None],
          'docker_unit':['systemctl',['show',DOCKER_UNIT,'-p','Id','-p','ActiveState','-p','SubState','-p','UnitFileState'],None],
          'timedate':['timedatectl',['show','-p','Timezone','-p','NTPSynchronized','-p','LocalRTC'],None],
          'account':['getent',['passwd',ACCOUNT],None]}
COMMANDS.update({'unit:'+unit:['systemctl',['show',unit,'-p','Id','-p','LoadState','-p','ActiveState','-p','UnitFileState'],None]
                 for unit in UNITS})

SIDE_EFFECTS=['timedatectl show may start systemd-timedated on demand through D-Bus; no setting is changed',
              'docker info, run once: the Docker CLI executes every installed CLI plugin binary (for example docker-compose, '
              'docker-buildx) as root with the single argument docker-cli-plugin-metadata, and the daemon answers by running '
              'its init and runtime binaries (docker-init, runc) with --version; no setting is changed',
              'every docker command: the Docker CLI loads its client configuration file from the home directory of root '
              'when one exists; its content never reaches this process',
              'getent passwd asks the name-service sources configured on the host; a remote source, if one is configured, '
              'is contacted by getent and not by this process',
              'the two docker entries are known from the upstream source and were never observed on this host']
SCOPE={'operation':OPERATION,'date':DATE,
       'binaries':BINARIES,'commands':COMMANDS,
       'command_environment':{'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},
       'family':{'project_label':PROJECT_LABEL,'project':PROJECT,'service_label':SERVICE_LABEL,'services':SERVICES,
                 'oneoff_label':ONEOFF_LABEL,'revision_label':REVISION_LABEL,'state':'running'},
       'data_destination':DATA_DESTINATION,
       'lstat_only':{'docker_init':INIT_CANDIDATES,'supervisor_trees':TREES,'unit_directory':UNIT_DIRECTORY,'zoneinfo':ZONEINFO,
                     'data_source_and_each_ancestor':'discovered from the mount whose destination is data_destination',
                     'data_source_immediate_entries':{'name_pattern':ENTRY_PATTERN,'limit':MAX_ENTRIES,'recursion':False,
                                                     'well_known_names_reported_as_fixed_tokens':WELL_KNOWN_ENTRIES,
                                                     'fields':['type','uid','gid','mode_octal']}},
       'statvfs':STATVFS_PATHS+['data source'],
       'file_contents_read':['/proc/<host pid of a family container>/uid_map','/proc/<host pid of a family container>/gid_map'],
       'account':{'name':ACCOUNT,'output':'presence boolean only; the passwd line is not captured',
                  'basis':'getent exit status: 0 present, 2 absent, anything else unavailable; no lookup inside this process'},
       'side_effects':SIDE_EFFECTS,
       'never':['container environment','docker exec or run','any write','provider token','database content',
                'instrument symbols','file contents other than file_contents_read','recursion below the data source',
                'systemctl verbs other than show and --version','shell',
                'network connection opened by this process'],
       'limits':{'max_seconds':MAX_SECONDS,'call_seconds':CALL_SECONDS,'timeouts_before_a_tool_is_skipped':MAX_TOOL_TIMEOUTS,'command_output_bytes':MAX_COMMAND_BYTES,
                 'listed_containers':MAX_LISTED,'classified_running':MAX_RUNNING,'family_rows':MAX_FAMILY,
                 'mounts_per_container':MAX_MOUNTS,'networks_per_container':MAX_NETWORKS,'map_lines':MAX_MAP_LINES,
                 'map_bytes':MAX_MAP_BYTES,'entries':MAX_ENTRIES,'entry_scan':MAX_ENTRY_COUNT,'path_depth':MAX_DEPTH,
                 'repo_tags':MAX_TAGS,'images':MAX_IMAGES,'data_sources':MAX_SOURCES,'receipt_bytes':RECEIPT_LIMIT}}

HEX64='[0-9a-f]{64}'
NAME='[A-Za-z0-9][A-Za-z0-9_.-]{0,127}'
IMAGE_ID='sha256:[0-9a-f]{64}'
REFERENCE='[A-Za-z0-9_./:@-]{1,200}'
STAMP='[0-9TZ:.+-]{1,64}'
WORD='[A-Za-z0-9_.:-]{0,128}'
STATES=('created','running','paused','restarting','removing','exited','dead')
MOUNT_TYPES=('bind','volume','tmpfs','npipe','cluster','image')
EXPIRED=('GO_EXPIRED','CLOCK_REVERSED','DEADLINE')


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def strict(raw):
    need(type(raw) is bytes and 0<len(raw)<=65536,'DOCUMENT_SIZE')
    def pairs(items):
        result={}
        for key,value in items:
            need(key not in result,'DUPLICATE_KEY');result[key]=value
        return result
    def constant(_):raise Refused('NONFINITE_JSON')
    try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
    except Refused:raise
    except ValueError:raise Refused('JSON_INVALID')
def decode(raw):
    value=strict(raw);need(type(value) is dict,'DOCUMENT_TYPE');return value
def instant(value):
    need(type(value) is str,'WINDOW_UNBOUND')
    point=datetime.fromisoformat(value.replace('Z','+00:00'));offset=point.utcoffset()
    need(point.tzinfo is not None and offset is not None and offset.total_seconds()==0,'WINDOW_NOT_UTC')
    return point
SCOPE_SHA256=sha(canonical(SCOPE))

def text(value,pattern):return type(value) is str and re.fullmatch(pattern,value) is not None
def clean_path(value):
    return (text(value,r'/[A-Za-z0-9._=/_-]{0,199}') and '//' not in value and str(PurePosixPath(value))==value
            and '..' not in PurePosixPath(value).parts and len(PurePosixPath(value).parts)<=MAX_DEPTH+1)
def data_path(value):
    return clean_path(value) and value!='/' and not any(value==root or value.startswith(root+'/') for root in ('/proc','/sys','/dev'))
def kind(mode):
    if stat.S_ISDIR(mode):return 'dir'
    if stat.S_ISREG(mode):return 'file'
    if stat.S_ISLNK(mode):return 'symlink'
    return 'other'
def shape(info):
    return {'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,
            'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'device':info.st_dev,'inode':info.st_ino}
def safe(error):
    if isinstance(error,Refused) and re.fullmatch('[A-Z][A-Z0-9_]{0,79}',str(error)):
        result={'status':'UNAVAILABLE','code':str(error)}
        if isinstance(error,CommandFailed) and type(error.returncode) is int:result['returncode']=error.returncode
        return result
    if isinstance(error,OSError):
        return {'status':'UNAVAILABLE','code':'OS_ERROR','errno':error.errno if type(error.errno) is int else None}
    return {'status':'UNAVAILABLE','code':'OBSERVATION_FAILED'}
def attempt(action):
    try:return action()
    except Exception as error:return safe(error)
def combined(items):
    statuses=[item.get('status') for item in items]
    if statuses and all(value=='COMPLETE' for value in statuses):return 'COMPLETE'
    return 'UNAVAILABLE' if statuses and all(value=='UNAVAILABLE' for value in statuses) else 'PARTIAL'


class Native:
    """The only place that touches the host: fixed-argv commands and metadata calls."""
    def identity(self):return os.geteuid(),os.getegid()
    def noatime(self):
        flag=getattr(os,'O_NOATIME',0);need(flag,'NOATIME_UNAVAILABLE');return flag
    def open(self,name,flags,dir_fd=None):
        return os.open(name,flags) if dir_fd is None else os.open(name,flags,dir_fd=dir_fd)
    def close(self,fd):os.close(fd)
    def fstat(self,fd):return os.fstat(fd)
    def lstat(self,name,dir_fd):return os.stat(name,dir_fd=dir_fd,follow_symlinks=False)
    def fstatvfs(self,fd):return os.fstatvfs(fd)
    def read(self,fd,size):return os.read(fd,size)
    def names(self,fd):
        with os.scandir(fd) as iterator:
            for entry in iterator:yield entry.name
    def run(self,argv,gate,seconds,capture=True):
        gate()
        process=subprocess.Popen(argv,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL,
                                 env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
        output=bytearray();selector=selectors.DefaultSelector()
        try:
            until=time.monotonic()+min(seconds,gate())
            if capture:
                os.set_blocking(process.stdout.fileno(),False);selector.register(process.stdout,selectors.EVENT_READ)
                while selector.get_map():
                    remaining=min(gate(),until-time.monotonic());need(remaining>0,'COMMAND_TIMEOUT')
                    for key,_ in selector.select(min(.2,remaining)):
                        block=os.read(key.fd,8192)
                        if not block:selector.unregister(key.fileobj);continue
                        output.extend(block);need(len(output)<=MAX_COMMAND_BYTES,'COMMAND_OUTPUT_LIMIT')
            while True:
                remaining=min(gate(),until-time.monotonic());need(remaining>0,'COMMAND_TIMEOUT')
                try:code=process.wait(timeout=min(.2,remaining));break
                except subprocess.TimeoutExpired:pass
            gate();return code,bytes(output)
        finally:
            if process.poll() is None:
                process.kill()
                try:process.wait(timeout=1)
                except subprocess.TimeoutExpired:pass
            selector.close()
            if process.stdout is not None:process.stdout.close()


def trusted_executable(host,path,check):
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    fd=host.open('/',flags)
    try:
        info=host.fstat(fd);parts=PurePosixPath(path).parts[1:]
        for index,part in enumerate(parts):
            if not (stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022):return False
            check()
            try:named=host.lstat(part,fd)
            except FileNotFoundError:return False
            if index==len(parts)-1:
                return bool(stat.S_ISREG(named.st_mode) and named.st_uid==0 and not named.st_mode&0o022 and named.st_mode&0o111)
            if not stat.S_ISDIR(named.st_mode):return False
            child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child;info=host.fstat(fd)
        return False
    finally:host.close(fd)

def binary(host,candidates,check):
    for candidate in candidates:
        if trusted_executable(host,candidate,check):return candidate
    raise Refused('BINARY_UNAVAILABLE_OR_UNSAFE')


class Context:
    def __init__(self,host,gate):
        self.host,self.gate,self.started=host,gate,time.monotonic()
        self.binaries={};self.timeouts={};self.calls=0
    def check(self):
        remaining=self.gate()
        need(time.monotonic()-self.started<MAX_SECONDS,'DEADLINE')
        return remaining
    def call(self,name,*extra,capture=True):
        tool,arguments,_=COMMANDS[name]
        need(self.timeouts.get(tool,0)<MAX_TOOL_TIMEOUTS,'COMMAND_SKIPPED_AFTER_TIMEOUT')
        if tool not in self.binaries:
            try:self.binaries[tool]=binary(self.host,BINARIES[tool],self.check)
            except Exception as error:self.binaries[tool]=Refused(safe(error)['code'])
        path=self.binaries[tool]
        if isinstance(path,Exception):raise Refused(str(path))
        self.calls+=1
        try:return self.host.run([path]+list(arguments)+list(extra),self.check,CALL_SECONDS,capture)
        except Refused as error:
            if str(error)=='COMMAND_TIMEOUT':self.timeouts[tool]=self.timeouts.get(tool,0)+1
            raise
    def output(self,name,*extra):
        code,raw=self.call(name,*extra)
        if code!=0:raise CommandFailed('COMMAND_FAILED',code)
        return raw


def probe(host,path,check):
    """lstat of the leaf only; no component is followed. Absence is proved at the first missing component."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    check();fd=host.open('/',flags)
    try:
        parts=PurePosixPath(path).parts[1:];prefix=''
        for index,part in enumerate(parts):
            prefix+='/'+part;check()
            try:named=host.lstat(part,fd)
            except FileNotFoundError:
                return {'status':'COMPLETE','exists':False,'absent_at':prefix,'absence_proved_at_read':True}
            if index==len(parts)-1:return {'status':'COMPLETE','exists':True,**shape(named)}
            if stat.S_ISLNK(named.st_mode):
                return {'status':'COMPLETE','exists':None,'symlink_component_not_followed':prefix}
            need(stat.S_ISDIR(named.st_mode),'COMPONENT_NOT_DIRECTORY')
            check();child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child
            held=host.fstat(fd);need((held.st_dev,held.st_ino)==(named.st_dev,named.st_ino),'PATH_CHANGED')
        return {'status':'COMPLETE','exists':True,**shape(host.fstat(fd))}
    finally:host.close(fd)

def definite(result):
    if result.get('exists') is None:
        return {'status':'UNAVAILABLE','code':'SYMLINK_COMPONENT','at':result.get('symlink_component_not_followed')}
    return result

def descend(host,path,check,rows):
    """Open a directory component by component, never following a link. One row per component, '/' included."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    check();fd=host.open('/',flags)
    try:
        info=host.fstat(fd);rows.append({'path':'/',**shape(info),'mount_point_by_device_change':True})
        prefix='';device=info.st_dev
        for part in PurePosixPath(path).parts[1:]:
            prefix+='/'+part;check();named=host.lstat(part,fd)
            rows.append({'path':prefix,**shape(named),'mount_point_by_device_change':named.st_dev!=device})
            need(not stat.S_ISLNK(named.st_mode),'SYMLINK_COMPONENT')
            need(stat.S_ISDIR(named.st_mode),'COMPONENT_NOT_DIRECTORY')
            check();child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child
            held=host.fstat(fd);need((held.st_dev,held.st_ino)==(named.st_dev,named.st_ino),'PATH_CHANGED')
            device=held.st_dev
        check();return fd
    except BaseException:
        host.close(fd);raise

def filesystem(host,fd):
    info=host.fstat(fd);v=host.fstatvfs(fd)
    values=(v.f_frsize,v.f_blocks,v.f_bfree,v.f_bavail)
    need(all(type(value) is int and value>=0 for value in values) and v.f_frsize>0,'STATVFS_INVALID')
    return {'status':'COMPLETE','device':info.st_dev,'inode':info.st_ino,'f_frsize':v.f_frsize,'f_blocks':v.f_blocks,
            'f_bfree':v.f_bfree,'f_bavail':v.f_bavail,'bytes_total':v.f_blocks*v.f_frsize,
            'bytes_free_for_root_f_bfree':v.f_bfree*v.f_frsize,
            'bytes_available_to_non_root_f_bavail':v.f_bavail*v.f_frsize}

def reference(ctx,path):
    rows=[];fd=descend(ctx.host,path,ctx.check,rows)
    try:return filesystem(ctx.host,fd)
    finally:ctx.host.close(fd)

def entries(ctx,fd):
    host=ctx.host;before=host.fstat(fd);count=0;names=[];capped=False
    for name in host.names(fd):
        count+=1
        if len(names)<=MAX_ENTRIES:names.append(name)
        if count%64==0:ctx.check()
        if count>=MAX_ENTRY_COUNT:capped=True;break
    issues=[];rows=[];withheld=0;tokens=0
    if capped:issues.append('ENTRY_COUNT_CAPPED')
    if count>MAX_ENTRIES:
        issues.append('ENTRY_LIMIT');withheld=count
    else:
        hidden=[];known=[]
        for name in sorted(names):
            ctx.check()
            try:row=shape(host.lstat(name,fd))
            except FileNotFoundError:row={'vanished':True};issues.append('ENTRY_VANISHED')
            row.pop('device',None);row.pop('inode',None)
            if text(name,ENTRY_PATTERN):row['name']=name;rows.append(row)
            elif name in WELL_KNOWN_ENTRIES:row['name']=None;row['well_known']=WELL_KNOWN_ENTRIES[name];known.append(row)
            else:row['name']=None;row['name_withheld']=True;hidden.append(row)
        withheld=len(hidden);tokens=len(known)
        rows+=known+sorted(hidden,key=lambda row:(str(row.get('type')),str(row.get('uid')),str(row.get('gid')),str(row.get('mode_octal'))))
        if withheld:issues.append('ENTRY_NAME_WITHHELD')
    unchanged=before.st_atime_ns==host.fstat(fd).st_atime_ns
    if not unchanged:issues.append('ATIME_CHANGED_DURING_LISTING')
    return {'status':'COMPLETE' if not issues else 'PARTIAL','issues':sorted(set(issues)),'count':count,'count_capped':capped,
            'rows':rows,'names_included':count<=MAX_ENTRIES,'names_withheld':withheld,'names_well_known':tokens,
            'atime_unchanged_during_listing':unchanged,'recursion':False}

def process_maps(host,pid,check):
    need(type(pid) is int and 0<pid<=PID_MAX,'PID_INVALID')
    check();root=host.open('/proc',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        # The held directory descriptor pins this process instance: after an exit its entries fail
        # instead of resolving to a later process that reuses the number.
        check();directory=host.open(str(pid),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root)
        try:
            result={'maps_truncated':False}
            for name in ('uid_map','gid_map'):
                check();fd=host.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
                try:
                    raw=b''
                    while len(raw)<=MAX_MAP_BYTES:
                        block=host.read(fd,MAX_MAP_BYTES+1-len(raw))
                        if not block:break
                        raw+=block
                finally:host.close(fd)
                need(len(raw)<=MAX_MAP_BYTES and re.fullmatch(rb'[0-9 \t\n]*',raw) is not None,'MAP_CONTENT_INVALID')
                lines=[]
                for line in raw.decode('ascii').splitlines():
                    fields=line.split()
                    need(len(fields)==3 and all(len(field)<=10 and int(field)<=4294967295 for field in fields),'MAP_LINE_INVALID')
                    lines.append([int(field) for field in fields])
                if len(lines)>MAX_MAP_LINES:lines=lines[:MAX_MAP_LINES];result['maps_truncated']=True
                result[name]=lines
            identity=[[0,0,4294967295]]
            result['identity_mapped']=result['uid_map']==identity and result['gid_map']==identity
            return result
        finally:host.close(directory)
    finally:host.close(root)


def supervisor_trees(ctx):
    paths={path:attempt(lambda path=path:definite(probe(ctx.host,path,ctx.check))) for path in TREES}
    def account():
        code,_=ctx.call('account',capture=False)
        if code not in (0,2):raise CommandFailed('ACCOUNT_LOOKUP_FAILED',code)
        return {'status':'COMPLETE','name':ACCOUNT,'present':code==0,
                'basis':'getent exit status 0 or 2 with output discarded'}
    found=attempt(account)
    return {'status':combined(list(paths.values())+[found]),'paths':paths,'account':found}

def docker_init(ctx):
    candidates={path:attempt(lambda path=path:definite(probe(ctx.host,path,ctx.check))) for path in INIT_CANDIDATES}
    status=combined(candidates.values());present=sorted(path for path,value in candidates.items() if value.get('exists') is True)
    return {'status':status,'candidates':candidates,'present_paths':present,
            'any_present':True if present else False if status=='COMPLETE' else None,'lstat_only':True}

def docker_daemon(ctx):
    def strings(value,pattern,limit):
        return value is None or (type(value) is list and len(value)<=limit and all(text(item,pattern) for item in value))
    def pairs(value):
        return value is None or (type(value) is list and len(value)<=32 and all(
            type(item) is list and len(item)==2 and all(text(part,'[ -~]{0,128}') for part in item) for item in value))
    valid={'security_options':lambda value:strings(value,'[A-Za-z0-9_.,=:/-]{1,128}',16),
           'driver':lambda value:text(value,'[A-Za-z0-9_.-]{1,64}'),'driver_status':pairs,
           'docker_root_dir':clean_path,'init_binary':lambda value:text(value,'[A-Za-z0-9_./-]{0,128}'),
           'server_version':lambda value:text(value,'[0-9A-Za-z.+~_-]{1,64}')}
    def field(key,value):
        need(valid[key](value),'DAEMON_FIELD_INVALID');return {'status':'COMPLETE','value':value}
    failure=None
    try:
        row=decode(ctx.output('info'));need(set(row)=={key for key,_ in INFO_FIELDS},'DAEMON_INFO_INVALID')
        # A CLI that cannot reach the daemon may still print zero values and exit 0: an empty version is no answer, never a fact.
        need(type(row['server_version']) is str and row['server_version']!='','DAEMON_INFO_EMPTY')
    except Exception as error:failure=safe(error)
    fields={key:dict(failure) if failure else attempt(lambda key=key:field(key,row[key])) for key,_ in INFO_FIELDS}
    fields['server_version_from_docker_version']=attempt(lambda:field('server_version',strict(ctx.output('version'))))
    result={'status':combined(fields.values()),'fields':fields,'rootless_reported':None,'userns_remap_reported':None}
    options=fields['security_options']
    if options.get('status')=='COMPLETE':
        names=[item.split(',')[0] for item in options['value'] or []]
        result['rootless_reported']='name=rootless' in names;result['userns_remap_reported']='name=userns' in names
    return result

def family_facts(ctx,reference):
    """One validated row of metadata. Environment is never requested; network details are reduced to names."""
    row=decode(ctx.output('family',reference))
    keys={'name','id','image_id','image_reference','running','state','started_at','host_pid','restarts','project','service',
          'oneoff','revision','user','userns_mode','readonly_rootfs','network_mode','networks','mounts'}
    need(set(row)==keys and row['id']==reference and text(row['name'],'/'+NAME) and text(row['image_id'],IMAGE_ID)
         and text(row['image_reference'],REFERENCE) and type(row['running']) is bool and row['state'] in STATES
         and text(row['started_at'],STAMP) and type(row['host_pid']) is int and 0<=row['host_pid']<=PID_MAX
         and type(row['restarts']) is int and row['restarts']>=0 and row['project']==PROJECT and row['service'] in SERVICES
         and type(row['networks']) is list and row['networks'] and row['networks'][-1] is None
         and type(row['mounts']) is list and row['mounts'] and row['mounts'][-1] is None,'FAMILY_METADATA_INVALID')
    return row

def family_row(row):
    """Reduce a validated raw row to emitted fields; anything of unexpected shape is withheld and flagged."""
    issues=[]
    def optional(key,ok,code):
        if row[key] is None or ok(row[key]):return row[key]
        issues.append(code);return None
    out={'name':row['name'][1:],'container_id':row['id'],'image_id':row['image_id'],'image_reference':row['image_reference'],
         'running':row['running'],'state':row['state'],'started_at':row['started_at'],'host_pid':row['host_pid'],'restarts':row['restarts'],
         'revision_label':optional('revision',lambda value:value=='' or text(value,'[0-9a-f]{40}'),'REVISION_LABEL_INVALID'),
         'user':optional('user',lambda value:text(value,WORD),'USER_INVALID'),
         'userns_mode':optional('userns_mode',lambda value:text(value,WORD),'USERNS_MODE_INVALID'),
         'readonly_rootfs':optional('readonly_rootfs',lambda value:type(value) is bool,'READONLY_ROOTFS_INVALID'),
         'network_mode':optional('network_mode',lambda value:text(value,WORD),'NETWORK_MODE_INVALID')}
    networks=row['networks'][:-1];named=[value for value in networks if text(value,NAME)]
    if len(named)!=len(networks):issues.append('NETWORK_NAME_INVALID')
    if len(named)>MAX_NETWORKS:issues.append('NETWORK_LIMIT')
    out['networks']=sorted(named)[:MAX_NETWORKS];out['network_count']=len(networks)
    mounts=[];data=[];data_invalid=False
    for item in row['mounts'][:-1]:
        ok=(type(item) is dict and set(item)=={'type','source','destination','rw'} and item['type'] in MOUNT_TYPES
            and (item['source'] in (None,'') or clean_path(item['source'])) and clean_path(item['destination'])
            and type(item['rw']) is bool)
        targeted=type(item) is dict and item.get('destination')==DATA_DESTINATION
        if ok and targeted and data_path(item['source']):data.append(item)
        elif targeted:data_invalid=True
        if ok:mounts.append({'type':item['type'],'source':item['source'],'destination':item['destination'],'rw':item['rw']})
        else:mounts.append({'withheld':True});issues.append('MOUNT_INVALID')
    if data_invalid:issues.append('DATA_MOUNT_INVALID')
    if len(data)>1:issues.append('DATA_MOUNT_DUPLICATED')
    if len(mounts)>MAX_MOUNTS:issues.append('MOUNT_LIMIT')
    mounts.sort(key=lambda item:(str(item.get('destination')),str(item.get('source'))))
    out['mount_count']=len(mounts);out['mounts']=mounts[:MAX_MOUNTS];out['has_data_mount']=bool(data) or data_invalid
    return out,issues,data,data_invalid

def containers(ctx):
    def listing():
        rows=[decode(line) for line in ctx.output('ps').splitlines() if line]
        need(len(rows)<=MAX_LISTED,'CONTAINER_COUNT_LIMIT')
        for row in rows:
            need(set(row)=={'id','name','state'} and text(row['id'],HEX64) and text(row['name'],NAME)
                 and row['state'] in STATES,'CONTAINER_LIST_INVALID')
        need(len({row['id'] for row in rows})==len(rows),'CONTAINER_LIST_DUPLICATE')
        return sorted(rows,key=lambda row:row['id'])
    before=listing();running=[row for row in before if row['state']=='running']
    issues=[];family=[];other=set();outside=0;unclassified=0
    if len(running)>MAX_RUNNING:issues.append('RUNNING_LIMIT')
    for listed in running[:MAX_RUNNING]:
        try:
            item=decode(ctx.output('class',listed['id']))
            need(set(item)=={'id','running','project','service','oneoff'} and item['id']==listed['id'] and type(item['running']) is bool
                 and all(item[key] is None or (type(item[key]) is str and len(item[key])<=256) for key in ('project','service','oneoff')),
                 'CLASS_INVALID')
        except Exception:unclassified+=1;continue
        if item['project']!=PROJECT:outside+=1
        elif item['service'] in SERVICES:
            if item['running']:family.append(item)
            else:unclassified+=1
        elif text(item['service'],NAME):other.add(item['service'])
        else:unclassified+=1
    if unclassified:issues.append('UNCLASSIFIED_CONTAINERS')
    family.sort(key=lambda item:(item['service'],item['id']))
    if len(family)>MAX_FAMILY:issues.append('FAMILY_LIMIT')
    # A container that could not be classified or read may carry the data mount: the mount facts are then incomplete.
    rows=[];carriers=[];incomplete=bool(unclassified) or len(running)>MAX_RUNNING or len(family)>MAX_FAMILY
    for item in family[:MAX_FAMILY]:
        row={'status':'UNAVAILABLE','service':item['service'],'oneoff':item['oneoff']=='True','container_id':item['id']}
        try:
            first=family_facts(ctx,item['id']);facts,problems,data,data_invalid=family_row(first)
            row.update(facts);incomplete=incomplete or data_invalid or len(data)>1
            try:row.update(process_maps(ctx.host,first['host_pid'],ctx.check))
            except Exception as error:
                failure=safe(error);row.update(uid_map=None,gid_map=None,identity_mapped=None)
                problems.append('PROC_MAP_'+failure['code']);row['proc_map_errno']=failure.get('errno')
            if row.get('maps_truncated'):problems.append('MAP_LINE_LIMIT')
            second=family_facts(ctx,item['id']);row['unchanged_during_read']=first==second
            if first!=second:problems.append('CONTAINER_CHANGED')
            row['issues']=sorted(set(problems));row['status']='COMPLETE' if not problems else 'PARTIAL'
            if first==second and len(data)==1 and not data_invalid:
                carriers.append({'service':item['service'],'name':facts['name'],'type':data[0]['type'],
                                 'source':data[0]['source'],'rw':data[0]['rw']})
            elif first!=second:incomplete=True
        except Exception as error:
            row.update(safe(error));incomplete=True
        rows.append(row)
    after=attempt(listing);stable=after==before
    if not stable:issues.append('LIST_UNSTABLE')
    steady=[row['service'] for row in rows if not row['oneoff']]
    missing=sorted(set(SERVICES)-set(steady));duplicated=sorted({name for name in steady if steady.count(name)>1})
    if missing or duplicated:issues.append('FAMILY_SERVICE_SET_MISMATCH')
    if any(row['status']!='COMPLETE' for row in rows):issues.append('FAMILY_ROW_INCOMPLETE')
    if not rows:issues.append('FAMILY_EMPTY')
    section={'status':'UNAVAILABLE' if not rows else 'COMPLETE' if not issues else 'PARTIAL','issues':sorted(set(issues)),
             'docker_path':ctx.binaries.get('docker') if type(ctx.binaries.get('docker')) is str else None,
             'listed_before':len(before),'listed_after':len(after) if type(after) is list else None,'list_stable':stable,
             'running_listed':len(running),'family':rows,'family_count':len(family),
             'services_missing':missing,'services_duplicated':duplicated,'oneoff_count':sum(1 for row in rows if row['oneoff']),
             'stack_other_services':sorted(other)[:16],'running_outside_stack_count':outside,'unclassified_count':unclassified,
             'containers_started_outside_compose_are_not_in_family':True,'environment_requested':False}
    if not rows:section['code']='FAMILY_EMPTY'
    return section,carriers,incomplete

def images(ctx,rows):
    wanted=sorted({row['image_id'] for row in rows if text(row.get('image_id'),IMAGE_ID)})
    need(wanted,'NO_FAMILY_IMAGE')
    def one(image_id):
        row=decode(ctx.output('image',image_id))
        need(set(row)=={'id','repo_tags','revision'} and row['id']==image_id,'IMAGE_METADATA_INVALID')
        tags=row['repo_tags'];need(tags is None or type(tags) is list,'IMAGE_METADATA_INVALID')
        named=sorted(tag for tag in tags or [] if text(tag,REFERENCE));issues=[]
        if len(named)!=len(tags or []):issues.append('REPO_TAG_INVALID')
        if len(named)>MAX_TAGS:issues.append('REPO_TAG_LIMIT')
        revision=row['revision']
        if not (revision in (None,'') or text(revision,'[0-9a-f]{40}')):revision=None;issues.append('REVISION_LABEL_INVALID')
        return {'status':'COMPLETE' if not issues else 'PARTIAL','issues':issues,'id':image_id,'repo_tags':named[:MAX_TAGS],
                'repo_tag_count':len(tags or []),'revision_label':revision,
                'used_by':sorted(item['name'] for item in rows if item.get('image_id')==image_id)}
    found=[]
    for image_id in wanted[:MAX_IMAGES]:
        item=attempt(lambda image_id=image_id:one(image_id));item.setdefault('id',image_id);found.append(item)
    status=combined(found)
    if len(wanted)>MAX_IMAGES and status=='COMPLETE':status='PARTIAL'
    return {'status':status,'images':found,'image_count':len(wanted),'images_truncated':len(wanted)>MAX_IMAGES,
            'identification_basis':'the '+REVISION_LABEL+' label; the local ID is specific to this image store'}

def data_volume(ctx,carriers,incomplete):
    issues=[];references={}
    for path in STATVFS_PATHS:
        references[path]=attempt(lambda path=path:reference(ctx,path))
        if references[path].get('status')!='COMPLETE':issues.append('REFERENCE_FILESYSTEM_UNAVAILABLE')
    distinct=sorted({(item['type'],item['source']) for item in carriers})
    if incomplete:issues.append('FAMILY_MOUNT_FACTS_INCOMPLETE')
    absent='DATA_MOUNT_UNOBSERVED' if incomplete else 'DATA_MOUNT_NOT_FOUND'
    if not distinct:issues.append(absent)
    if len(distinct)>1:issues.append('DATA_SOURCE_DISAGREE')
    if len(distinct)>MAX_SOURCES:issues.append('DATA_SOURCE_LIMIT')
    def inspect(source):
        rows=[];out={'ancestors':rows}
        try:fd=descend(ctx.host,source,ctx.check,rows)
        except Exception as error:
            out.update(safe(error));return out
        try:
            out['filesystem']=attempt(lambda:filesystem(ctx.host,fd))
            out['entries']=(attempt(lambda:entries(ctx,fd)) if len(distinct)==1
                            else {'status':'UNAVAILABLE','code':'NOT_LISTED_WHILE_SOURCES_DISAGREE'})
        finally:ctx.host.close(fd)
        out['status']=combined([out['filesystem'],out['entries']]);return out
    sources=[]
    for mount_type,source in distinct[:MAX_SOURCES]:
        item={'type':mount_type,'source':source};item.update(attempt(lambda source=source:inspect(source)))
        if item.get('status')!='COMPLETE':issues.append('DATA_SOURCE_INCOMPLETE')
        sources.append(item)
    return {'status':'UNAVAILABLE' if not distinct else 'COMPLETE' if not issues else 'PARTIAL','issues':sorted(set(issues)),
            'destination':DATA_DESTINATION,'carriers':carriers,'distinct_source_count':len(distinct),'sources':sources,
            'reference_filesystems':references,'mount_point_basis':MOUNT_BASIS,
            **({'code':absent} if not distinct else {})}

def properties(raw,keys):
    need(re.fullmatch(rb'[ -~\n]*',raw) is not None,'PROPERTY_OUTPUT_INVALID')
    found={}
    for line in raw.decode('ascii').splitlines():
        if not line:continue
        key,separator,value=line.partition('=')
        need(separator=='=','PROPERTY_LINE_INVALID')
        if key in keys:
            need(key not in found and text(value,'[A-Za-z0-9_./:@+-]{0,128}'),'PROPERTY_VALUE_INVALID');found[key]=value
    return {key:found.get(key) for key in keys},sorted(set(keys)-set(found))

def systemd(ctx):
    items={'unit_directory':attempt(lambda:definite(probe(ctx.host,UNIT_DIRECTORY,ctx.check))),
           'zoneinfo_new_york':attempt(lambda:definite(probe(ctx.host,ZONEINFO,ctx.check)))}
    def version():
        raw=ctx.output('systemd_version').split(b'\n',1)[0]
        need(re.fullmatch(rb'[ -~]{1,200}',raw) is not None,'VERSION_LINE_INVALID')
        line=raw.decode('ascii');match=re.match(r'systemd ([0-9]{1,5})(?![0-9])',line)
        return {'status':'COMPLETE','first_line':line,'number':int(match.group(1)) if match else None}
    def show(name,keys,unit=None):
        values,missing=properties(ctx.output(name),keys);issues=[]
        if missing:issues.append('PROPERTY_MISSING')
        if unit is not None and values.get('Id')!=unit:issues.append('UNIT_ID_MISMATCH')
        return {'status':'COMPLETE' if not issues else 'PARTIAL','issues':issues,'properties':values}
    items['systemctl_version']=attempt(version)
    items['docker_unit']=attempt(lambda:show('docker_unit',('Id','ActiveState','SubState','UnitFileState'),DOCKER_UNIT))
    for unit in UNITS:
        items['unit:'+unit]=attempt(lambda unit=unit:show('unit:'+unit,('Id','LoadState','ActiveState','UnitFileState'),unit))
    items['timedate']=attempt(lambda:show('timedate',('Timezone','NTPSynchronized','LocalRTC')))
    return {'status':combined(items.values()),'items':items,
            'systemctl_path':ctx.binaries.get('systemctl') if type(ctx.binaries.get('systemctl')) is str else None}


def reason_codes(value,found):
    if type(value) is dict:
        if value.get('status') not in (None,'COMPLETE'):
            for code in [value.get('code')]+list(value.get('issues') or []):
                if text(code,'[A-Z][A-Z0-9_]{0,79}'):found.add(code)
        for item in value.values():reason_codes(item,found)
    elif type(value) is list:
        for item in value:reason_codes(item,found)

def validate_collection(collection):
    need(type(collection) is dict and set(collection)=={'schema','status','phase','scope','window','host_binding_sha256','max_seconds'},
         'COLLECTION_KEYS')
    need(collection['schema']==COLLECTION_SCHEMA and collection['status']=='BOUND','COLLECTION_UNBOUND')
    need(collection['phase']==PHASE,'PHASE_INVALID')
    need(type(collection['max_seconds']) is int and collection['max_seconds']==MAX_SECONDS,'LIMITS_INVALID')
    need(text(collection['host_binding_sha256'],HEX64) and collection['host_binding_sha256']!='0'*64,'HOST_UNBOUND')
    need(type(collection['scope']) is dict and canonical(collection['scope'])==canonical(SCOPE),'SCOPE_MISMATCH')
    need(type(collection['window']) is dict and set(collection['window'])=={'not_before','expires_at'},'COLLECTION_WINDOW')

def collect(request,gate,host=None):
    # All shape validation precedes the first gate call, and that first call is outside every handler:
    # a refusal or a dry-run gate stops here before anything is observed.
    validate_collection(request)
    ctx=Context(host if host is not None else Native(),gate)
    ctx.check()
    sections={};shared={'rows':[],'carriers':[],'incomplete':True}
    def run(name,action):
        try:
            ctx.check();sections[name]=action()
        except Exception as error:sections[name]=safe(error)
    def observed_containers():
        section,shared['carriers'],shared['incomplete']=containers(ctx);shared['rows']=section['family'];return section
    actor=attempt(lambda:dict(zip(('uid','gid'),ctx.host.identity())))
    run('supervisor_trees',lambda:supervisor_trees(ctx))
    run('docker_init',lambda:docker_init(ctx))
    run('docker_daemon',lambda:docker_daemon(ctx))
    run('containers',observed_containers)
    run('images',lambda:images(ctx,shared['rows']))
    run('data_volume',lambda:data_volume(ctx,shared['carriers'],shared['incomplete']))
    run('systemd',lambda:systemd(ctx))
    problems=[];expired=False
    for name in sorted(sections):
        if sections[name].get('status')!='COMPLETE':
            found=set();reason_codes(sections[name],found);expired=expired or bool(found&set(EXPIRED))
            problems+=[name+':'+code for code in sorted(found) or ['INCOMPLETE']]
    try:ctx.check()
    except Refused:expired=True
    status='PARTIAL_OR_WINDOW_EXPIRED' if expired else 'OBSERVED_COMPLETE' if not problems else 'PARTIAL_OBSERVED'
    return {'schema':OBSERVATION_SCHEMA,'status':status,'actor':actor,'host_binding_sha256':request['host_binding_sha256'],
            'scope_sha256':SCOPE_SHA256,
            'sections':sections,'problems':problems[:MAX_PROBLEMS],'problems_truncated':len(problems)>MAX_PROBLEMS,
            'commands_started':ctx.calls,
            'writes':0,'container_commands':0,'container_environment_read':False,'secret_bytes_read':0,
            'application_imports':0,'recursion':False,
            'file_contents_read':['/proc/<pid>/uid_map','/proc/<pid>/gid_map'],
            'ready':False,'installation_authorized':False,'activation_authorized':False}


# Authenticated stdin API. These primitives are also consumed by the explicitly
# adapted once dispatcher; this operation accepts no GO of an earlier operation.
@dataclass(frozen=True)
class Pins:
    payload:str
    request:str
    authority:str
    go:str
class Gate:
    def __init__(self,start,end,clock,monotonic):
        self.start,self.end,self.clock,self.monotonic=start,end,clock,monotonic
        self.wall,self.mono=clock(),monotonic();self.deadline=self.mono+MAX_SECONDS
        need(start<=self.wall<end,'OUTSIDE_GO_WINDOW')
    def __call__(self):
        wall,mono=self.clock(),self.monotonic()
        need(wall>=self.wall and mono>=self.mono,'CLOCK_REVERSED')
        self.wall,self.mono=wall,mono
        need(self.start<=wall<self.end and mono<self.deadline,'GO_EXPIRED')
        return min((self.end-wall).total_seconds(),self.deadline-mono)

def authenticate(request_bytes,authority_bytes,go_bytes,*,pins,payload_bytes,
                 clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,
                 executor_uid=os.geteuid):
    for name,data in [('request',request_bytes),('authority',authority_bytes),('go',go_bytes),('payload',payload_bytes)]:
        pin=getattr(pins,name)
        need(type(pin) is str and re.fullmatch(HEX64,pin) and pin!='0'*64 and type(data) is bytes and sha(data)==pin,'PIN_MISMATCH')
    request,authority,go=map(decode,(request_bytes,authority_bytes,go_bytes))
    need(request.get('schema')==REQUEST_SCHEMA and request.get('status')=='BOUND'
         and request.get('operation')==OPERATION and request.get('phase')==PHASE
         and request.get('date')==DATE and request.get('scope_sha256')==SCOPE_SHA256
         and request.get('payload_sha256')==pins.payload and request.get('executor_uid')==0
         and type(request.get('executor_uid')) is int and executor_uid()==0,'REQUEST_OR_EXECUTOR_UNBOUND')
    need(request.get('max_seconds')==MAX_SECONDS and request.get('writes_allowed') is False
         and request.get('activation_allowed') is False,'REQUEST_SCOPE')
    need(authority.get('schema')==AUTHORITY_SCHEMA
         and authority.get('operation')==OPERATION and authority.get('status')=='SIGNED'
         and authority.get('decision')=='APPROVED' and authority.get('execution_authorized') is True
         and authority.get('request_sha256')==pins.request and authority.get('writes_allowed') is False
         and authority.get('activation_allowed') is False,'AUTHORITY_UNBOUND')
    need(go.get('schema')==GO_SCHEMA and go.get('status')=='SIGNED'
         and go.get('action')=='GO' and go.get('phase')==PHASE
         and go.get('operation')==OPERATION and go.get('execution_authorized') is True
         and go.get('writes_allowed') is False and go.get('activation_allowed') is False
         and go.get('request_sha256')==pins.request and go.get('authority_sha256')==pins.authority
         and go.get('payload_sha256')==pins.payload,'GO_UNBOUND')
    need(type(go.get('owner')) is str and go['owner'] not in ('','UNBOUND')
         and go['owner']==authority.get('owner'),'OWNER_UNBOUND')
    host=request.get('host_binding_sha256')
    need(type(host) is str and re.fullmatch(HEX64,host) and host!='0'*64
         and host==authority.get('host_binding_sha256')==go.get('host_binding_sha256'),'HOST_BINDING')
    starts=[instant(d.get('not_before')) for d in (request,authority,go)]
    ends=[instant(d.get('not_after')) for d in (request,authority,go)]
    need(all(point.date().isoformat()==DATE for point in starts+ends),'DATE_WINDOW_MISMATCH')
    gate=Gate(max(starts),min(ends),clock,monotonic);gate()
    collection=request.get('collection')
    need(type(collection) is dict and collection.get('host_binding_sha256')==host,'COLLECTION_BINDING')
    validate_collection(collection)
    need(instant(collection['window']['not_before'])==starts[0]
         and instant(collection['window']['expires_at'])==ends[0],'COLLECTION_WINDOW')
    return collection,gate

def _reduce_mounts(observation):
    for row in observation['sections']['containers']['family']:
        if type(row.get('mounts')) is list:
            row['mounts']=[item for item in row['mounts'] if item.get('destination')==DATA_DESTINATION]
            row['mounts_reduced_for_size']=True
def _each_listing(observation):
    for source in observation['sections']['data_volume']['sources']:
        if type(source.get('entries')) is dict and type(source['entries'].get('rows')) is list:yield source['entries']
def _drop_names(observation):
    for listing in _each_listing(observation):
        for row in listing['rows']:row['name']=None
        listing['names_included']=False;listing['names_dropped_for_size']=True
def _drop_rows(observation):
    for listing in _each_listing(observation):
        listing['rows']=[];listing['rows_dropped_for_size']=True
def _reduce_family(observation):
    keep=('status','service','name','host_pid','has_data_mount','identity_mapped','code')
    section=observation['sections']['containers']
    section['family']=[{key:row[key] for key in keep if key in row} for row in section['family']]
    section['family_reduced_for_size']=True
def _reduce_sections(observation):
    observation['sections']={name:{'status':section.get('status'),'reduced_for_size':True}
                             for name,section in observation['sections'].items()}
REDUCTIONS=[('MOUNTS_REDUCED_TO_DATA_DESTINATION',_reduce_mounts),('ENTRY_NAMES_DROPPED',_drop_names),
            ('ENTRY_ROWS_DROPPED',_drop_rows),('FAMILY_ROWS_REDUCED',_reduce_family),('SECTIONS_REDUCED',_reduce_sections)]

def seal(receipt):
    """Fit the dispatcher's 64 KiB decode limit by explicit flagged reduction, then hash. Never raises."""
    def size():return len(canonical(receipt))+SEAL_OVERHEAD
    try:
        applied=[];receipt['observation']['size_reductions']=applied
        for name,step in REDUCTIONS:
            if size()<=RECEIPT_LIMIT:break
            applied.append(name);receipt['status']=PARTIAL_STATUS
            if receipt['observation'].get('status')=='OBSERVED_COMPLETE':receipt['observation']['status']='PARTIAL_OBSERVED'
            try:step(receipt['observation'])
            except Exception:applied.append(name+'_FAILED')
        need(size()<=RECEIPT_LIMIT,'RECEIPT_LIMIT')
    except Exception:
        receipt['status']=PARTIAL_STATUS
        receipt['observation']={'schema':OBSERVATION_SCHEMA,'status':'PARTIAL_OBSERVED','code':'RECEIPT_REDUCED_TO_MINIMUM',
                                'sections':{},'problems':['receipt:RECEIPT_REDUCED_TO_MINIMUM'],
                                'size_reductions':['RECEIPT_REDUCED_TO_MINIMUM']}
    receipt['metadata_sha256']=sha(canonical(receipt));return receipt

def observe(request_bytes,authority_bytes,go_bytes,*,pins,payload_bytes,
            clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,
            executor_uid=os.geteuid,collector=collect):
    collection,gate=authenticate(request_bytes,authority_bytes,go_bytes,pins=pins,payload_bytes=payload_bytes,
                                clock=clock,monotonic=monotonic,executor_uid=executor_uid)
    host=collection['host_binding_sha256']
    # The host identity itself comes from the independently reviewed pinned SSH
    # transport. The hash here is its signed reference, not a new observation.
    begun,mark=clock(),monotonic()
    try:observed=collector(collection,gate)
    except Refused:raise
    except Exception:observed=None
    if type(observed) is not dict or type(observed.get('sections')) is not dict:
        observed={'schema':OBSERVATION_SCHEMA,'status':'PARTIAL_OBSERVED','code':'COLLECTOR_FAILED','sections':{},
                  'problems':['collector:COLLECTOR_FAILED']}
    try:
        ended,elapsed=clock(),monotonic()-mark
        need(ended>=begun and elapsed>=0,'CLOCK_REVERSED')
        observed['sections']['clock']={'status':'COMPLETE','utc_start':begun.isoformat(),'utc_end':ended.isoformat(),
                                       'monotonic_elapsed_ms':int(elapsed*1000)}
    except Exception as error:observed['sections']['clock']=safe(error)
    try:gate()
    except Refused:observed['status']='PARTIAL_OR_WINDOW_EXPIRED'
    if observed['sections']['clock'].get('status')!='COMPLETE' and observed.get('status')=='OBSERVED_COMPLETE':
        observed['status']='PARTIAL_OBSERVED'
    partial=observed.get('status')!='OBSERVED_COMPLETE'
    receipt={'schema':RECEIPT_SCHEMA,
             'status':PARTIAL_STATUS if partial else COMPLETE_STATUS,
             'request_sha256':pins.request,'authority_sha256':pins.authority,'go_sha256':pins.go,
             'payload_sha256':pins.payload,'host_binding_sha256':host,'observed_at':begun.isoformat(),
             'observation':observed,'source_mutation':False,'installation_authorized':False,
             'activation_authorized':False,'ready':False,'hostfacts_is_not_readiness':True}
    return seal(receipt)

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
