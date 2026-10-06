import selectors
import subprocess

CALL_SECONDS=8
MAX_TOOL_TIMEOUTS=2
MAX_COMMAND_BYTES=64*1024
COMMAND_ENVIRONMENT={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'}

class NativeRunner:
    """Fixed-argv commands: absolute binary, no shell, stdin and stderr /dev/null, bounded output and time.
    The runner of the reviewed read-only family; the only addition is one optional DOCKER_CONFIG value."""
    def run(self,argv,gate,seconds,capture=True,docker_config=None):
        gate()
        environment=dict(COMMAND_ENVIRONMENT)
        if docker_config is not None:environment['DOCKER_CONFIG']=docker_config
        process=subprocess.Popen(argv,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL,env=environment)
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


class Commands:
    """Starts only rows of the signed COMMANDS table, with at most the arguments that row allows."""
    def __init__(self,host,gate):
        self.host,self.gate=host,gate;self.binaries={};self.timeouts={};self.calls=0
    def call(self,name,*extra,capture=True,docker_config=None):
        tool,arguments,_=COMMANDS[name]
        need(self.timeouts.get(tool,0)<MAX_TOOL_TIMEOUTS,'COMMAND_SKIPPED_AFTER_TIMEOUT')
        if tool not in self.binaries:
            try:self.binaries[tool]=binary(self.host,BINARIES[tool],self.gate)
            except Exception as error:self.binaries[tool]=Refused(safe(error)['code'])
        path=self.binaries[tool]
        if isinstance(path,Exception):raise Refused(str(path))
        self.calls+=1
        try:return self.host.run([path]+list(arguments)+list(extra),self.gate,CALL_SECONDS,capture,docker_config)
        except Refused as error:
            if str(error)=='COMMAND_TIMEOUT':self.timeouts[tool]=self.timeouts.get(tool,0)+1
            raise
    def output(self,name,*extra,docker_config=None):
        code,raw=self.call(name,*extra,docker_config=docker_config)
        if code!=0:raise CommandFailed('COMMAND_FAILED',code)
        return raw


REVISION_LABEL='org.opencontainers.image.revision'
REFERENCE='[A-Za-z0-9_./:@-]{1,200}'
MAX_TAGS=8
# Same template as the reviewed read-only family: every optional key is reached through index, so it also runs in the
# CLI raw-JSON fallback (missingkey=error), the only inspect mode proven on this host.
IMAGE_FORMAT=('{"id":{{json .Id}},"repo_tags":{{json (index . "RepoTags")}},"revision":'
              '{{with index . "Config"}}{{with index . "Labels"}}{{json (index . "'+REVISION_LABEL+'")}}'
              '{{else}}null{{end}}{{else}}null{{end}}}')

def image_facts(commands,reference,docker_config=None):
    """docker image inspect of one ID or reference: local ID, tags, revision label. Nothing else is requested."""
    row=decode(commands.output('image',reference,docker_config=docker_config))
    need(set(row)=={'id','repo_tags','revision'} and text(row['id'],IMAGE_ID),'IMAGE_METADATA_INVALID')
    tags=row['repo_tags'];need(tags is None or type(tags) is list,'IMAGE_METADATA_INVALID')
    named=sorted(tag for tag in tags or [] if text(tag,REFERENCE));revision=row['revision']
    return {'id':row['id'],'repo_tags':named[:MAX_TAGS],'repo_tag_count':len(tags or []),
            'repo_tags_all_valid':len(named)==len(tags or []),'reference_among_repo_tags':reference in named,
            'revision_label':revision if revision in (None,'') or text(revision,'[0-9a-f]{40}') else None}
