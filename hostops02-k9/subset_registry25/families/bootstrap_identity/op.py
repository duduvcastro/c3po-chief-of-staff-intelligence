OPERATION='GO_WRITE_HOSTOPS02_BOOTSTRAP_IDENTITY_01'
PHASE='WRITE_BOOTSTRAP_IDENTITY_EPOCH_CLAIM'
REQUEST_SCHEMA='WRITE_HOSTOPS02_BOOTSTRAP_IDENTITY_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_BOOTSTRAP_IDENTITY_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_BOOTSTRAP_IDENTITY_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_BOOTSTRAP_IDENTITY_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_BOOTSTRAP_IDENTITY_PLAN_V1'
SOURCE_NAME='bootstrap_identity.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
DATE_CLASS='WRITE_BOOTSTRAP'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=('GO_WRITE_HOSTOPS02_K4_E0_01','GO_READONLY_HOSTOPS02_EPOCH_READBACK_01','GO_READONLY_HOSTOPS02_K9_PHASE_READ_01')
MAX_GATE_SPAN_SECONDS=300
COMPLETE_OUTCOME='BOOTSTRAP_IDENTITY_AND_EPOCH_CLAIM_VERIFIED'
PARTIAL_OUTCOME='PARTIAL_BOOTSTRAP_CLAIM_CONSUMED_REQUIRES_REVIEW'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='PARTIAL_BOOTSTRAP_CLAIM_CONSUMED_REQUIRES_REVIEW'
ESCAPED_OUTCOME='PARTIAL_BOOTSTRAP_CLAIM_CONSUMED_REQUIRES_REVIEW'
BOOTSTRAP_MODE='BOOTSTRAP_IDENTITY'
BOOTSTRAP_EPOCH='R2D2-V2-SHADOW-2026-10-05'
BOOTSTRAP_SLOT='FIRST_NIGHT_20261006'
BOOTSTRAP_START='2026-10-06T12:26:00+00:00'
BOOTSTRAP_END='2026-10-06T12:31:00+00:00'
K9_PACKAGE_SHA256='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
K9_CODE_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
PLAN_KEYS=frozenset(('mode','epoch','slot','attempt_key','constants','parent_rows','data_volume_chain','source_rows','evidence_boot_id_sha256','policy_read'))

# ---------------------------------------------------------------- placement (N-8): Codex's decision of 2026-10-04
# (W/codex-n8-placement-20261004.txt, sha256 d30f7f90...2c53). The K9 tree lies under a chain controlled by root alone:
# no open root, no ancestor of uid 1000, nothing writable by group or other, no link. Codex's decision 6 (#429,
# comment 5985748037): the source root moves under the same root-only chain (no open root, gid 0, no setgid, 0700), on
# the filesystem of days/ (one floor). The data volume is read only for the September secret sources (lstat only, the
# volume as open root) and by POLICY (the files install_release and activate put there).
# Every host path this source reads is derived from these constants and from nothing else. They are fixed words of the
# sealed bytes (the env file is a fixed word of the probe row), so a change is a new payload hash and a new review.
K9_DATA_VOLUME='/mnt/day-d-data'
K9_ROOT='/var/lib/c3po/r2d2-v2-k9-20261005'
K9_SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'
K9_PLACEMENT={'k9_root':K9_ROOT,'source_root':K9_SOURCE_ROOT,'days':K9_ROOT+'/days','tools':K9_ROOT+'/tools','claims':K9_ROOT+'/claims',
              'secrets':K9_ROOT+'/secrets','emitter':K9_ROOT+'/secrets/emitter','provider_env_file':K9_ROOT+'/secrets/provider.env',
              'risk_db_env_file':K9_ROOT+'/secrets/risk-db.env','emitter_password':K9_ROOT+'/secrets/emitter/password',
              'source_open_root':None,'k9_open_root':None,'september_open_root':K9_DATA_VOLUME,
              'decision':'d30f7f9048af4a39cf4fa7d9f49292ad387a2d41f33bad39816e83d3d1fc2c53','decision_6':'#429 comment 5985748037'}
# The chains every K9 request of the week signs (rows copied from the TREE receipt of the same boot); claims is K9W's.
K9_PARENT_CHAINS=('days','source_root','secrets','tools','claims')
K9_RECEIVES_ENTRY=('days','source_root','claims')
# What the TREE read walks: (item key, placement key). Every one is a private directory of root (0:0 0700).
K9_TREE_DIRECTORIES=(('K9_ROOT','k9_root'),('DAYS','days'),('TOOLS','tools'),('CLAIMS','claims'),('SECRETS','secrets'),
                     ('EMITTER','emitter'),('SOURCE_ROOT','source_root'))
K9_SECRET_FILES=(('SECRETS','provider.env'),('SECRETS','risk-db.env'),('EMITTER','password'))
# The two September secret sources K3-K9 copies from (its draft: RISK_URL_DIRECTORY, EMITTER_SOURCE_DIRECTORY), whose
# identity K3-K9 signs from this TREE read: every component below the data volume by lstat only (never opened past a
# directory, never a size, a length or a digest). The last entry of each chain is the secret file.
K9_SEPTEMBER_SOURCES=(('.r2d2-v2-risk-secrets','risk-database-url'),('.c3po-role-executor-20260908-r2','secret','password'))
K9_PRIVATE_DIRECTORY_MODE=0o700
# Codex (#429, comment 5984327121): 200 GiB available (f_bavail * f_frsize of fstatvfs on the open descriptor of days/,
# never f_bfree) on the filesystem that contains days/; below it: HOLD. The source root's capacity is reported apart.
K9_DISK_FLOOR_BYTES=214748364800

K9_PRIVATE_DIRECTORY_MODE=0o700
K9_PRIVATE_FILE_MODE=0o600
K9_DISK_FLOOR_BYTES=214748364800
K9_MAX_COUNT=10000000
K9_MAX_PLAN_FILE=16777216
K9_MAX_RUNNER_FILE=4194304
K9_MAX_POLICY_FILE=8192
K9_MAX_RELEASE_FILE=65536
K9_ENTRY='[A-Za-z0-9][A-Za-z0-9._-]{0,127}'
K9_EXPIRED=('GO_EXPIRED','CLOCK_REVERSED')
K9_WALK_FINDINGS=('PARENT_MISSING','PARENT_SYMLINK_COMPONENT','PARENT_NOT_DIRECTORY','PARENT_IDENTITY_MISMATCH','SYMLINK_COMPONENT','COMPONENT_NOT_DIRECTORY')
K9_ROW_FIELDS=('device','inode','uid','gid','mode')
BOOTSTRAP_CONSTANT_KEYS=frozenset(('package_sha256','code_revision','release_sha256','policy_sha256','image_id','runner_sha256','disk_floor_bytes','placement'))
SOURCE_PATHS=tuple(K9_DATA_VOLUME+'/'+part for part in ('.r2d2-v2-risk-secrets','.r2d2-v2-risk-secrets/risk-database-url','.c3po-role-executor-20260908-r2','.c3po-role-executor-20260908-r2/secret','.c3po-role-executor-20260908-r2/secret/password'))
SOURCE_ROW_KEYS=frozenset(('path','device','inode','uid','gid','mode','mtime_ns','ctime_ns'))
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'the compiled worker name or its observed ID','QUICK','READ'),
          'container_environment':command_row('docker',['container','inspect','--format'],'the five approved LIVE booleans template then the observed worker ID','QUICK','READ')}
CLAIM_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
class Native(NativeRead,NativeRunner,NativeClaim):
    pass

def k9_free_inodes(host,fd):
    """Inodes a non-root writer can still take on the filesystem of a held descriptor; None where none are counted."""
    numbers=host.fstatvfs(fd);total,free=getattr(numbers,'f_files',0),getattr(numbers,'f_favail',None)
    return free if integer(total,1) and integer(free) else None

def k9_root_group_rows(rows):
    """Every component of a K9 chain in the group of root and not setgid (K4-E0's rule for the same chain)."""
    return all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows)

def k9_chain(item,path,receives_entry,code):
    """One signed directory of the placement: exactly {path, rows, open_root}, the compiled path, open_root null (N-8 and
    decision 6: no open root anywhere in these chains), rows from a read of the same boot, every component uid 0, gid 0,
    not setgid, not group/other-writable."""
    need(type(item) is dict and set(item)=={'path','rows','open_root'} and item['path']==path and item['open_root'] is None and item['rows'] is not None,code)
    validate_chain(item['rows'],path,None,receives_entry)
    need(k9_root_group_rows(item['rows']),'CHAIN_ROW_NOT_ROOT_GROUP')
    return item

def k9_free_chain(item,code):
    """A signed directory whose path the plan gives (the policy and the release directories)."""
    need(type(item) is dict and set(item)=={'path','rows','open_root'} and type(item['path']) is str and clean_path(item['path']) and item['path']!='/'
         and item['rows'] is not None,code)
    root=item['open_root']
    need(root is None or (type(root) is str and clean_path(root) and root!='/' and inside(item['path'],root)),code)
    validate_chain(item['rows'],item['path'],root)
    return item

def k9_policy_read(plan):
    """POLICY: the installed policy and release files (directory rows signed, file names) and the worker's data bind."""
    value=plan['policy_read']
    need(type(value) is dict and set(value)=={'policy','release','worker'},'POLICY_READ_INVALID')
    worker=value['worker']
    need(type(worker) is dict and set(worker)=={'container','data_source','data_target'} and text(worker['container'],CONTAINER_NAME)
         and not text(worker['container'],CONTAINER_ID)
         and all(type(worker[key]) is str and clean_path(worker[key]) and worker[key]!='/' for key in ('data_source','data_target')),'POLICY_READ_INVALID')
    need(worker['data_source']==K9_DATA_VOLUME,'POLICY_READ_NOT_THE_DATA_VOLUME')
    for key in ('policy','release'):
        item=value[key]
        need(type(item) is dict and set(item)=={'directory','file_name'} and text(item['file_name'],K9_ENTRY),'POLICY_READ_INVALID')
        k9_free_chain(item['directory'],'POLICY_READ_INVALID')
        need(inside(item['directory']['path'],worker['data_source']) and item['directory']['path']!=worker['data_source'],'POLICY_READ_OUTSIDE_THE_DATA_VOLUME')
        need(clean_path(k9_in_worker(plan,key)) and len(k9_in_worker(plan,key))<=256,'POLICY_READ_INVALID')
    return value

def k9_host_file(plan,key):
    item=plan['policy_read'][key];return item['directory']['path']+'/'+item['file_name']

def k9_in_worker(plan,key):
    """A host file on the data volume as the worker sees it through its bind."""
    worker=plan['policy_read']['worker'];path=k9_host_file(plan,key);return worker['data_target']+path[len(worker['data_source']):]

def k9_expected_environment(plan):
    """The five names of the running worker after activate, with the values activate wrote (C3PO_R2D2_V2_*) and the revision."""
    values=plan['constants']
    return {'C3PO_R2D2_V2_LIVE_POLICY_FILE':k9_in_worker(plan,'policy'),'C3PO_R2D2_V2_LIVE_POLICY_SHA':values['policy_sha256'],
            'C3PO_R2D2_V2_SHADOW_RELEASE_FILE':k9_in_worker(plan,'release'),'C3PO_R2D2_V2_SHADOW_RELEASE_SHA':values['release_sha256'],
            'C3PO_BUILD_SHA':values['code_revision']}

def k9_item(status='COMPLETE',findings=(),**fields):
    codes=sorted(set(findings))
    return dict(fields,status=status,findings=codes,matches=(not codes) if status=='COMPLETE' else None)

def k9_child(host,parent_fd,name,gate):
    """A directory entry of a held directory, classified by lstat and opened without following a link: (fd, fstat)."""
    gate();named=host.lstat(name,parent_fd)
    need(not stat.S_ISLNK(named.st_mode),'SYMLINK_COMPONENT');need(stat.S_ISDIR(named.st_mode),'COMPONENT_NOT_DIRECTORY')
    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent_fd)
    try:
        info=host.fstat(fd);need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'PATH_CHANGED');return fd,info
    except BaseException:
        host.close(fd);raise

def k9_descend(host,base_fd,parts,gate):
    """The directory reached from a held one by the given names (each opened without following a link). The caller
    closes what is returned; nothing is returned for no name (the held one itself)."""
    fd=None
    try:
        for part in parts:
            child,_=k9_child(host,base_fd if fd is None else fd,part,gate)
            if fd is not None:host.close(fd)
            fd=child
        return fd
    except BaseException:
        if fd is not None:host.close(fd)
        raise

def k9_read(host,base_fd,parts,gate,limit):
    """(bytes, fstat) of a regular file below a held directory. FileNotFoundError when a component or the file is absent."""
    fd=k9_descend(host,base_fd,parts[:-1],gate)
    try:
        gate();named=host.lstat(parts[-1],base_fd if fd is None else fd)
        need(stat.S_ISREG(named.st_mode),'FILE_NOT_REGULAR')
        raw,info=read_regular(host,parts[-1],base_fd if fd is None else fd,gate,limit)
        need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'FILE_CHANGED_DURING_READ');return raw,info
    finally:
        if fd is not None:host.close(fd)

def k9_private(info,mode):
    return (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,mode) and (not stat.S_ISREG(info.st_mode) or info.st_nlink==1)

def k9_document(raw,code):
    try:value=strict(raw,K9_MAX_PLAN_FILE)
    except Refused:raise Refused(code) from None
    need(type(value) is dict,code);return value

class BootstrapReader:
    def __init__(self,plan,host,gate,commands,bound,clock,monotonic):
        self.plan,self.host,self.gate,self.commands,self.clock,self.monotonic=plan,host,gate,commands,clock,monotonic
        self.mode=BOOTSTRAP_MODE;self.values=plan['constants'];self.held={};self.same_boot=True
        self.image_ok=False;self.worker_id=None;self.boot_hash=None
    def boot(self):
        self.boot_hash=boot_id_sha256(self.host,self.gate)
        if self.mode=='TREE':return k9_item(boot_id_sha256=self.boot_hash)     # the boot the week's requests will sign
        self.same_boot=self.boot_hash==self.plan['evidence_boot_id_sha256']
        return k9_item(findings=[] if self.same_boot else ['EVIDENCE_FROM_EARLIER_BOOT'],equal_to_the_evidence=self.same_boot,device_numbers_compared=self.same_boot)

    def directory(self,key,path,spec=None,private=True):
        """One directory walked from "/" without following a link and held to the end of the run: against the signed
        rows when there are, otherwise recorded (TREE) with its rows in the receipt."""
        host=self.host;observed=[];findings=[];fd=None
        try:
            if spec is None:fd=descend(host,path,self.gate,observed)
            else:fd=walk_pinned(host,spec['rows'],self.gate,observed,self.same_boot)
        except FileNotFoundError:findings.append('PARENT_MISSING')
        except Refused as error:
            if str(error) not in K9_WALK_FINDINGS:raise
            findings.append(str(error))
        facts={'path':path,'rows_signed':spec is not None,'components_observed':len(observed),'held':fd is not None}
        if fd is None:
            if spec is not None and findings==['PARENT_IDENTITY_MISMATCH']:
                facts['fields_that_differ']={field:observed[-1][field]!=spec['rows'][len(observed)-1][field] for field in K9_ROW_FIELDS}
            if spec is None:facts['observed_rows']=observed
            return k9_item(findings=findings,**facts)
        try:self.held[key]=Pinned(host,fd,rows=[dict(row) for row in observed] if spec is None else spec['rows'],compare_device=spec is None or self.same_boot)
        except BaseException:
            host.close(fd);raise
        leaf=observed[-1]
        # judged as the K9 requests judge their chains: no open root (POLICY's directories on the data volume carry signed
        # rows and are compared with them; for them this is a fact only)
        try:validate_chain([dict(row) for row in observed],path);acceptable=k9_root_group_rows(observed)
        except Refused:acceptable=False
        root_private=(leaf['uid'],leaf['gid'],leaf['mode'])==(0,0,K9_PRIVATE_DIRECTORY_MODE)
        if private and not root_private:findings.append('DIRECTORY_NOT_ROOT_PRIVATE')
        if spec is None and not acceptable:findings.append('ROWS_NOT_ACCEPTABLE_TO_THE_K9_REQUESTS')
        # every component from "/": owned by root and closed to group and other writes (outside an open root)
        loose=[row['path'] for row in observed if not row_root_safe(row) or not k9_root_group_rows([row])]
        available=free_bytes(host,fd)
        facts.update(as_signed=None if spec is None else True,owner_uid=leaf['uid'],owner_gid=leaf['gid'],mode_octal='%04o'%leaf['mode'],
                     root_private=root_private,rows_acceptable_to_the_k9_requests=acceptable,
                     open_root=None,components_not_root_controlled=loose,
                     mount_point_by_device_change=mount_point_of(observed),bytes_available=available,
                     entries=count_entries(host,fd,self.gate,K9_MAX_COUNT))
        if spec is None:facts['observed_rows']=observed
        return k9_item(findings=findings,**facts)

    def k9_filesystem(self,floor):
        """The filesystem of the K9 tree: one device for k9_root and every directory below it (no mount inside the tree),
        the source root on the filesystem of days/ (decision 6: one floor), free bytes of days/ against the signed floor
        and free inodes."""
        root=self.held.get('K9_ROOT');need(root is not None,'DIRECTORY_NOT_HELD');root.verify(self.gate)
        device=root.identity[0];keys=[key for key,_ in K9_TREE_DIRECTORIES if key not in ('K9_ROOT','SOURCE_ROOT')]
        held=[key for key in keys if key in self.held];spans=[key for key in held if self.held[key].identity[0]!=device]
        source=self.held.get('SOURCE_ROOT')
        days=self.held.get('DAYS');need(days is not None,'DIRECTORY_NOT_HELD');days.verify(self.gate)
        # the floor is judged on the filesystem that contains days/, by fstatvfs of its own open descriptor (f_bavail * f_frsize)
        available,inodes=free_bytes(self.host,days.fd),k9_free_inodes(self.host,days.fd)
        if source is not None:source.verify(self.gate)
        together=None if source is None else source.identity[0]==days.identity[0]
        findings=(['K9_TREE_SPANS_FILESYSTEMS'] if spans else [])+(['SOURCE_ROOT_NOT_ON_THE_FILESYSTEM_OF_DAYS'] if together is False else [])
        if available<floor:findings.append('DISK_FREE_BELOW_FLOOR')
        return k9_item(findings=findings,directories_compared=len(held),directories_on_another_device=spans,
                       source_root_on_the_filesystem_of_days=together,days_bytes_available=available,floor_bytes=floor,hold=available<floor,
                       days_inodes_available=inodes,
                       filesystem_type='NOT_EXPOSED_BY_THE_CORE')

    def september_sources(self):
        """The September secret sources, below the data volume walked from "/" (the volume's open root, its rows in the
        receipt): per component its identity, owner, mode, both change instants, links and whether it is a link, by
        lstat in the held parent; a directory is opened by descriptor without following a link to reach the next; the
        file at the end is never opened. Never a size, a length or a digest."""
        rows=[];volume=descend(self.host,K9_DATA_VOLUME,self.gate,rows)
        try:
            device=self.host.fstat(volume).st_dev;findings=[];components=[]
            try:validate_chain([dict(row) for row in rows],K9_DATA_VOLUME,K9_DATA_VOLUME);acceptable=True
            except Refused:acceptable=False
            if not acceptable:findings.append('DATA_VOLUME_ROWS_NOT_ACCEPTABLE')
            if mount_point_of(rows)!=K9_DATA_VOLUME:findings.append('DATA_VOLUME_NOT_A_MOUNT_POINT')
            for chain in K9_SEPTEMBER_SOURCES:
                fd=None;path=K9_DATA_VOLUME
                try:
                    for index,name in enumerate(chain):
                        path+='/'+name;self.gate()
                        try:found=self.host.lstat(name,volume if fd is None else fd)
                        except FileNotFoundError:
                            findings.append('SEPTEMBER_SOURCE_ABSENT');components.append({'path':path,'exists':False});break
                        link=stat.S_ISLNK(found.st_mode);directory=stat.S_ISDIR(found.st_mode)
                        components.append({'path':path,'exists':True,'type':kind(found.st_mode),'device':found.st_dev,'inode':found.st_ino,'uid':found.st_uid,
                                           'gid':found.st_gid,'mode_octal':'%04o'%stat.S_IMODE(found.st_mode),'mtime_ns':found.st_mtime_ns,
                                           'ctime_ns':found.st_ctime_ns,'nlink':found.st_nlink,'is_link':link})
                        if link:findings.append('SEPTEMBER_SOURCE_IS_A_LINK');break
                        if found.st_dev!=device:findings.append('SEPTEMBER_SOURCE_ON_ANOTHER_DEVICE')
                        last=index==len(chain)-1
                        if directory and found.st_mode&0o022:findings.append('SEPTEMBER_DIRECTORY_GROUP_OR_WORLD_WRITABLE')
                        if last:
                            if not stat.S_ISREG(found.st_mode):findings.append('SEPTEMBER_SOURCE_NOT_A_REGULAR_FILE')
                            break
                        if not directory:findings.append('SEPTEMBER_SOURCE_NOT_A_DIRECTORY');break
                        child,_=k9_child(self.host,volume if fd is None else fd,name,self.gate)
                        if fd is not None:self.host.close(fd)
                        fd=child
                finally:
                    if fd is not None:self.host.close(fd)
            return k9_item(findings=findings,data_volume_rows=rows,data_volume_rows_acceptable=acceptable,data_volume_device=device,components=components)
        finally:self.host.close(volume)

    def runner_file(self):
        """The content-addressed runner of the tools directory: its bytes hash to the signed runner hash; root's, private."""
        parent=self.held.get('TOOLS');need(parent is not None,'DIRECTORY_NOT_HELD');parent.verify(self.gate)
        name='k9_runner-'+self.values['runner_sha256']+'.py'
        try:raw,info=k9_read(self.host,parent.fd,[name],self.gate,K9_MAX_RUNNER_FILE)
        except FileNotFoundError:return k9_item(findings=['RUNNER_FILE_ABSENT'],exists=False)
        equal=sha(raw)==self.values['runner_sha256'];private=k9_private(info,K9_PRIVATE_FILE_MODE)
        return k9_item(findings=([] if equal else ['RUNNER_BYTES_NOT_THE_SIGNED_ONES'])+([] if private else ['RUNNER_FILE_NOT_PRIVATE']),
                       exists=True,bytes_equal_signed=equal,private=private,owner_uid=info.st_uid,owner_gid=info.st_gid,
                       mode_octal='%04o'%stat.S_IMODE(info.st_mode),links=info.st_nlink,size=info.st_size)

    def image(self):
        found=image_facts(self.commands,self.values['image_id']);equal=found['id']==self.values['image_id'];revision=found['revision_label']==K9_CODE_REVISION
        self.image_ok=equal and revision
        return k9_item(findings=([] if equal else ['IMAGE_ID_MISMATCH'])+([] if revision else ['IMAGE_REVISION_MISMATCH']),id_equal_signed=equal,
                       revision_equal_signed=revision,repo_tag_count=found['repo_tag_count'])

    def installed(self,key):
        """The installed policy or release file, read on the host: its hash is the Act B's, it is root's and private;
        for the policy, the instant of the read lies in its window. Nothing of its content leaves."""
        directory=self.held.get(key.upper());need(directory is not None,'DIRECTORY_NOT_HELD');directory.verify(self.gate)
        item=self.plan['policy_read'][key];limit=K9_MAX_POLICY_FILE if key=='policy' else K9_MAX_RELEASE_FILE
        try:raw,info=k9_read(self.host,directory.fd,[item['file_name']],self.gate,limit)
        except FileNotFoundError:return k9_item(findings=[key.upper()+'_FILE_ABSENT'],exists=False)
        except Refused as error:
            if str(error)!='FILE_TOO_LARGE':raise
            return k9_item(findings=[key.upper()+'_FILE_TOO_LARGE'],exists=True)
        equal=sha(raw)==self.values[key+'_sha256'];private=k9_private(info,K9_PRIVATE_FILE_MODE)
        findings=([] if equal else [key.upper()+'_SHA_NOT_THE_SIGNED_ONE'])+([] if private else [key.upper()+'_FILE_NOT_PRIVATE'])
        facts={'exists':True,'bytes_equal_signed':equal,'private':private}
        if key=='policy':
            try:
                body=k9_document(raw,'POLICY_UNREADABLE');start,end=instant(body.get('valid_from')),instant(body.get('valid_until'));now=self.clock()
                inside_window=start<=now<end;facts.update(window_readable=True,inside_its_window=inside_window)
                if not inside_window:findings.append('POLICY_OUTSIDE_ITS_WINDOW')
            except Refused:
                facts.update(window_readable=False,inside_its_window=None);findings.append('POLICY_WINDOW_UNREADABLE')
        return k9_item(findings=findings,**facts)

    def worker(self):
        signed=self.plan['policy_read']['worker'];found=container_facts(self.commands,signed['container'])
        self.worker_id=found['id'];equal=found['image_id']==self.values['image_id'];running=found['running'] and found['state']=='running'
        return k9_item(findings=([] if equal else ['WORKER_IMAGE_NOT_THE_SIGNED_ONE'])+([] if running else ['WORKER_NOT_RUNNING']),
                       container=signed['container'],container_id=found['id'],image_id_equal_signed=equal,running=running,state=found['state'],restarts=found['restarts'],
                       health=found['health'],started_at=found['started_at'])

    def worker_environment(self):
        """Booleans only: the four live names with the values activate wrote, and the revision."""
        need(self.worker_id is not None,'WORKER_NOT_OBSERVED')
        expected=k9_expected_environment(self.plan);values=container_environment(self.commands,self.worker_id,expected)
        live=[key for key in sorted(expected) if key!='C3PO_BUILD_SHA'];build=values['C3PO_BUILD_SHA']['equal']
        equal=all(values[key]['equal'] for key in live)
        return k9_item(findings=([] if equal else ['WORKER_LIVE_NAMES_NOT_AS_SIGNED'])+([] if build else ['WORKER_BUILD_REVISION_MISMATCH']),
                       live_names_present=len([key for key in live if values[key]['present']]),live_names_equal=len([key for key in live if values[key]['equal']]),
                       build_revision_equal_signed=build,names={key:values[key] for key in sorted(values)})

    def stable(self):
        """Every directory held is still the one its way from "/" shows."""
        result={}
        for key in sorted(self.held):
            try:self.held[key].verify(self.gate);result[key]=True
            except Refused as error:
                if str(error) in K9_EXPIRED:raise
                result[key]=False
        return k9_item(findings=[] if all(result.values()) else ['DIRECTORY_REPLACED_DURING_RUN'],directories=result)


# ---- Positive empty-tree observations, limited to compiled entries under the held SECRETS descriptor.
def bootstrap_key():return sha(canonical([BOOTSTRAP_EPOCH,BOOTSTRAP_SLOT]))
def claim_name():return 'bootstrap-'+bootstrap_key()+'.claim'

def validate_plan(plan):
    need(plan['mode']==BOOTSTRAP_MODE,'BOOTSTRAP_MODE_INVALID')
    need(plan['epoch']==BOOTSTRAP_EPOCH,'BOOTSTRAP_EPOCH_INVALID')
    need(plan['slot']==BOOTSTRAP_SLOT and plan['attempt_key']==bootstrap_key(),'BOOTSTRAP_SLOT_OR_KEY_INVALID')
    need(instant(plan['window']['not_before'])==instant(BOOTSTRAP_START) and instant(plan['window']['expires_at'])==instant(BOOTSTRAP_END),'BOOTSTRAP_WINDOW_NOT_COMPILED')
    values=plan['constants'];need(type(values) is dict and set(values)==BOOTSTRAP_CONSTANT_KEYS,'CONSTANTS_INVALID')
    need(values['package_sha256']==K9_PACKAGE_SHA256 and values['code_revision']==K9_CODE_REVISION and values['placement']==K9_PLACEMENT,'CONSTANTS_NOT_COMPILED')
    need(values['disk_floor_bytes']==K9_DISK_FLOOR_BYTES,'DISK_FLOOR_NOT_COMPILED')
    need(all(hexpin(values[key]) for key in ('release_sha256','policy_sha256','runner_sha256')) and text(values['image_id'],IMAGE_ID),'CONSTANTS_INVALID')
    rows=plan['parent_rows'];need(type(rows) is dict and set(rows)==set(K9_PARENT_CHAINS),'PARENT_ROWS_INVALID')
    for name in K9_PARENT_CHAINS:k9_chain(rows[name],K9_PLACEMENT[name],name in K9_RECEIVES_ENTRY,'PARENT_ROWS_INVALID')
    root_rows=rows['secrets']['rows'];need((root_rows[-2]['uid'],root_rows[-2]['gid'],root_rows[-2]['mode'])==(0,0,0o700),'K9_ROOT_NOT_ROOT_PRIVATE')
    need(all((rows[name]['rows'][-1]['uid'],rows[name]['rows'][-1]['gid'],rows[name]['rows'][-1]['mode'])==(0,0,0o700) for name in K9_PARENT_CHAINS),'PARENT_NOT_ROOT_PRIVATE')
    volume=validate_chain(plan['data_volume_chain'],K9_DATA_VOLUME,K9_DATA_VOLUME)
    need(mount_point_of(volume)==K9_DATA_VOLUME,'DATA_VOLUME_NOT_A_MOUNT_POINT')
    sources=plan['source_rows']
    need(type(sources) is list and len(sources)==len(SOURCE_PATHS) and all(type(row) is dict and set(row)==set(SOURCE_ROW_KEYS) and row['path']==path and integer(row['device']) and integer(row['inode'],1) and integer(row['uid']) and integer(row['gid']) and integer(row['mode'],0,0o7777) and integer(row['mtime_ns']) and integer(row['ctime_ns']) for row,path in zip(sources,SOURCE_PATHS)),'SOURCE_ROWS_INVALID')
    need(all(row['device']==volume[-1]['device'] and not row['mode']&0o022 and row['uid'] in (0,volume[-1]['uid']) for row in sources),'SOURCE_ROWS_UNSAFE')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    k9_policy_read(plan)
    need(all(plan['policy_read'][key]['directory']['open_root'] in (None,K9_DATA_VOLUME) for key in ('policy','release')),'BOOTSTRAP_NEW_OPEN_ROOT_NOT_ALLOWED')
    need(plan['policy_read']['worker']['container']=='c3po-r2d2-worker-1','WORKER_NAME_NOT_COMPILED')


def effects_of(plan):
    return {'operation':OPERATION,'mode':BOOTSTRAP_MODE,'epoch':BOOTSTRAP_EPOCH,'slot':BOOTSTRAP_SLOT,'attempt_key':bootstrap_key(),
            'constants':plan['constants'],'parent_rows':{name:dict(chain_effects(item['rows']),open_root=None) for name,item in plan['parent_rows'].items()},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'reads':{'policy':k9_host_file(plan,'policy'),'release':k9_host_file(plan,'release'),'expected_live_environment':k9_expected_environment(plan),'secret_contents':False,'september_sources':'metadata_only','worker':'c3po-r2d2-worker-1'},
            'claim':{'path':K9_PLACEMENT['claims']+'/'+claim_name(),'key':bootstrap_key(),'name':claim_name(),'schema':'HOSTOPS02_BOOTSTRAP_EPOCH_CLAIM_V1','uid':0,'gid':0,'mode_octal':'0600','links':1,'file_fsync':True,'directory_fsync':True,'never_remove':True,'key_uses_go_hash':False},
            'writes_at_most':1,'claims_at_most':1,'other_files_changed':False,'containers_run':0,'containers_removed':0,'activation':False,
            'uncertain_creation_consumes_slot':True,'receipt_reuse_not_same_as_execution':True,
            'environment_read_limit':'Python receives five LIVE booleans only; Docker CLI/daemon process Config.Env internally'}

def success_of(plan):return COMPLETE_OUTCOME

SCOPE_STATEMENT=('First-night bootstrap: observes boot and worker identity, installed policy/release hashes, image/revision and five LIVE comparison booleans; verifies held root-controlled chains, runner and September source metadata. Positively verifies SECRETS empty and EMITTER/provider.env/risk-db.env absent by lstat of fixed names under the held SECRETS descriptor; derives password ABSENT_PARENT_CONFIRMED without opening a nonexistent directory. The only host effect is one durable exclusive 0600 claim in the compiled CLAIMS directory, keyed by epoch and bootstrap slot, independent of GO. Never removes a claim, repairs a mode or retries after possible creation. Does not open secret contents. Docker CLI/daemon process the inspect object including Config.Env; this Python process receives only five approved presence/equality booleans, never secret values. This is not a claim that no other process reads environment entries.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,'writes_allowed':True,'activation_allowed':False,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,'command_variables':COMMAND_VARIABLES,
       'epoch':BOOTSTRAP_EPOCH,'mode':BOOTSTRAP_MODE,'slot':BOOTSTRAP_SLOT,'window':{'not_before':BOOTSTRAP_START,'expires_at':BOOTSTRAP_END},'placement':K9_PLACEMENT,
       'claim':{'key':bootstrap_key(),'name':claim_name(),'outside_secrets':True,'independent_of_go':True,'mode_octal':'0600','never_remove':True,'possible_creation_is_consumed':True},
       'never':['secret contents opened','secret values in this Python process or receipt','unlink','mkdir','chmod','chown','rename','truncate','claim removal','claim repair','SPARE','daily policy attempt','docker run','docker exec','activation'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,'runner_bytes':K9_MAX_RUNNER_FILE,'policy_bytes':K9_MAX_POLICY_FILE,'release_bytes':K9_MAX_RELEASE_FILE,'claim_bytes':4096,'claim_count':1}}
SCOPE_SHA256=sha(canonical(SCOPE))


def private_directory(reader,key,name,spec):
    item=reader.directory(key,K9_PLACEMENT[name],spec)
    handle=reader.held.get(key)
    if handle is not None:
        item['pinned']=True;item['observed_rows']=[dict(row) for row in handle.rows]
        item['rows_acceptable_to_the_k9_requests']=k9_root_group_rows(handle.rows)
    return item


def empty_secrets(reader):
    parent=reader.held.get('SECRETS');need(parent is not None,'DIRECTORY_NOT_HELD');parent.verify(reader.gate)
    count=count_entries(reader.host,parent.fd,reader.gate,K9_MAX_COUNT);parent.verify(reader.gate)
    return k9_item(findings=[] if count==0 else ['SECRETS_DIRECTORY_NOT_EMPTY'],entries=count,held=True,pinned=True,root_private=True,
                   path=K9_PLACEMENT['secrets'],observed_rows=[dict(row) for row in parent.rows],rows_acceptable_to_the_k9_requests=True)


def absent_entry(reader,name):
    parent=reader.held.get('SECRETS');need(parent is not None,'DIRECTORY_NOT_HELD');parent.verify(reader.gate);reader.gate()
    try:reader.host.lstat(name,parent.fd)
    except FileNotFoundError as error:
        need(error.errno==errno.ENOENT,'ABSENCE_ERRNO_NOT_ENOENT');parent.verify(reader.gate)
        return k9_item(exists=False,absence_confirmed=True,errno=errno.ENOENT,parent_item='directory:SECRETS',name=name,
                       code='ABSENT_FROM_HELD_SECRETS' if name=='emitter' else 'ABSENT_ENTRY_CONFIRMED',held=False if name=='emitter' else None,
                       path=K9_PLACEMENT['secrets']+'/'+name)
    return k9_item(findings=['BOOTSTRAP_ENTRY_ALREADY_PRESENT'],exists=True,absence_confirmed=False,parent_item='directory:SECRETS',name=name)


def absent_password(emitter):
    need(emitter.get('status')=='COMPLETE' and emitter.get('matches') is True and emitter.get('exists') is False and emitter.get('absence_confirmed') is True,'EMITTER_ABSENCE_NOT_CONFIRMED')
    return k9_item(exists=False,parent_absent_confirmed=True,code='ABSENT_PARENT_CONFIRMED',path=K9_PLACEMENT['emitter_password'],parent_item='directory:EMITTER')


def september_pinned(reader):
    item=reader.september_sources()
    if item.get('status')!='COMPLETE' or item.get('findings'):return item
    expected=reader.plan['source_rows'];seen=item.get('components') or []
    valid=len(seen)==len(expected) and item.get('data_volume_rows')==reader.plan['data_volume_chain']
    for observed,signed in zip(seen,expected):
        valid=valid and all(observed.get(key)==value for key,value in signed.items() if key!='mode') and observed.get('mode_octal')=='%04o'%signed['mode']
    leaves=[row for row in seen if row.get('path') in (SOURCE_PATHS[1],SOURCE_PATHS[4])]
    valid=valid and len(leaves)==2 and all(row.get('type')=='file' and row.get('nlink')==1 for row in leaves)
    return dict(item,findings=[] if valid else ['SEPTEMBER_SOURCE_NOT_THE_PINNED_ROWS'],matches=bool(valid),rows_equal_signed=bool(valid))


def claim_record():
    return {'state':'NOT_ATTEMPTED','code':None,'errno':None,'key':bootstrap_key(),'name':claim_name(),'path':K9_PLACEMENT['claims']+'/'+claim_name(),
            'possible_creation':False,'created_by_this_run':False,'usage_consumed':False,'file_fsync':False,'directory_fsync':False,'readback_verified':False,'parent_stable':False,'metadata':None}


def exclusive_epoch_claim(host,parent,gate,state,bound,boot,worker,row):
    fd=None;failed=None
    content=canonical({'schema':'HOSTOPS02_BOOTSTRAP_EPOCH_CLAIM_V1','epoch':BOOTSTRAP_EPOCH,'slot':BOOTSTRAP_SLOT,'attempt_key':bootstrap_key(),
                       'request_sha256':bound['request_sha256'],'go_sha256':bound['go_sha256'],'payload_sha256':bound['payload_sha256'],
                       'boot_id_sha256':boot,'worker_container_id':worker})
    need(len(content)<=4096,'CLAIM_CONTENT_LIMIT')
    try:
        parent.verify(gate);need(gate()>=15,'BUDGET_INSUFFICIENT_BEFORE_CLAIM')
        # Existence before our creating call is a proved no-effect refusal; never open or remove it.
        try:host.lstat(row['name'],parent.fd)
        except FileNotFoundError as error:need(error.errno==errno.ENOENT,'CLAIM_ABSENCE_ERRNO')
        else:
            row.update(state='EXISTING',code='BOOTSTRAP_EPOCH_ALREADY_CLAIMED',usage_consumed=True);return row
        parent.verify(gate);gate();row.update(state='CREATE_UNCERTAIN',possible_creation=True,created_by_this_run=None,usage_consumed=True)
        state.issue()
        try:fd=host.create(row['name'],CLAIM_FLAGS,0o600,parent.fd)
        except OSError as error:
            if error.errno==errno.EEXIST:
                state.fail();row.update(state='EXISTING',possible_creation=False,created_by_this_run=False,usage_consumed=True,code='BOOTSTRAP_EPOCH_ALREADY_CLAIMED',errno=error.errno);return row
            state.unknown();row.update(code='CLAIM_CREATE_UNCERTAIN',errno=error.errno);return row
        except BaseException:
            state.unknown();raise
        state.done();row.update(state='CREATED',created_by_this_run=True)
        gate();info=host.fstat(fd);named=host.lstat(row['name'],parent.fd)
        row['metadata']=dict(shape(info),links=info.st_nlink)
        need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,0o600,1),'CLAIM_METADATA_INVALID')
        need(info.st_dev==parent.identity[0] and (named.st_dev,named.st_ino)==(info.st_dev,info.st_ino),'CLAIM_NAME_OR_DEVICE_CHANGED')
        offset=0
        while offset<len(content):
            gate();state.issue()
            try:written=host.write(fd,content[offset:])
            except BaseException:state.unknown();raise
            state.done();need(type(written) is int and 0<written<=len(content)-offset,'CLAIM_WRITE_INCOMPLETE');offset+=written
        row['state']='WRITTEN';parent.verify(gate);gate();state.issue()
        try:host.fsync(fd)
        except BaseException:state.unknown();raise
        state.done();row.update(state='FILE_SYNCED',file_fsync=True)
        parent.verify(gate);gate();state.issue()
        try:host.fsync(parent.fd)
        except BaseException:state.unknown();raise
        state.done();row.update(state='DIRECTORY_SYNCED',directory_fsync=True)
        parent.verify(gate);row['parent_stable']=True
        readback,after=read_regular(host,row['name'],parent.fd,gate,4096);named_after=host.lstat(row['name'],parent.fd)
        need(readback==content and (after.st_dev,after.st_ino)==(info.st_dev,info.st_ino)==(named_after.st_dev,named_after.st_ino),'CLAIM_READBACK_INVALID')
        need((after.st_uid,after.st_gid,stat.S_IMODE(after.st_mode),after.st_nlink)==(0,0,0o600,1),'CLAIM_READBACK_METADATA_INVALID')
        row.update(readback_verified=True,content_sha256=sha(content));parent.verify(gate);gate();row['state']='VERIFIED'
    except BaseException as error:
        failed=error;row['code']=code_of(error,'CLAIM_EFFECT_FAILED')
        if isinstance(error,OSError):row['errno']=error.errno
    finally:
        if fd is not None:
            try:host.close(fd)
            except BaseException as error:
                row['close_error']=safe(error)
                if row['code'] is None:row['code']='CLAIM_DESCRIPTOR_CLOSE_FAILED'
                if row['state']=='VERIFIED':row['state']='DIRECTORY_SYNCED'
    return row


def _reduce_bootstrap_items(receipt):
    receipt['expectations_met']=False;receipt['dependents_hold']=True
    receipt['items']={name:{key:item.get(key) for key in ('status','matches','findings','code','errno')} for name,item in (receipt.get('items') or {}).items()}
REDUCTIONS=[('BOOTSTRAP_ITEMS_REDUCED_TO_STATUS',_reduce_bootstrap_items)]


def perform(plan,gate,host,bound,clock,monotonic,state):
    gate()
    begun,mark=clock(),monotonic();items={};row=claim_record();failure=None
    commands=Commands(host,gate);reader=BootstrapReader(plan,host,gate,commands,bound,clock,monotonic)
    first_worker=None;first_environment=None
    def observe(label,action):
        gate()
        try:found=action()
        except Exception as error:found=safe(error)
        items[label]=found
        if found.get('status')!='COMPLETE' or found.get('matches') is not True or found.get('findings'):
            raise Refused(found.get('code') if text(found.get('code'),CODE) else (found.get('findings') or ['BOOTSTRAP_OBSERVATION_INCOMPLETE'])[0])
        return found
    try:
        state.started=True;need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
        validate_plan(plan)
        observe('boot',reader.boot)
        # All reads occur before the first possible claim effect.
        rows=plan['parent_rows']
        root_spec=dict(rows['secrets'],path=K9_ROOT,rows=rows['secrets']['rows'][:-1])
        observe('directory:K9_ROOT',lambda:private_directory(reader,'K9_ROOT','k9_root',root_spec))
        for key,name in K9_TREE_DIRECTORIES:
            if key in ('K9_ROOT','EMITTER'):continue
            observe('directory:'+key,lambda key=key,name=name:private_directory(reader,key,name,rows[name]))
        observe('directory:SECRETS',lambda:empty_secrets(reader))
        emitter=observe('directory:EMITTER',lambda:absent_entry(reader,'emitter'))
        observe('secret:EMITTER/password',lambda:absent_password(emitter))
        for name in ('provider.env','risk-db.env'):observe('secret:SECRETS/'+name,lambda name=name:absent_entry(reader,name))
        observe('k9_filesystem',lambda:reader.k9_filesystem(K9_DISK_FLOOR_BYTES))
        observe('runner_file',reader.runner_file)
        observe('september_sources',lambda:september_pinned(reader))
        for key in ('policy','release'):
            spec=plan['policy_read'][key]['directory']
            observe('directory:'+key.upper(),lambda key=key,spec=spec:reader.directory(key.upper(),spec['path'],spec,private=False))
            observe(key+'_file',lambda key=key:reader.installed(key))
        first_worker=observe('worker',reader.worker)
        first_environment=observe('worker_environment',reader.worker_environment)
        observe('image',reader.image)
        # Confirm the observed identity and environment have not changed while other items were read.
        worker=observe('worker_stable',reader.worker)
        need(worker==first_worker,'WORKER_CHANGED_DURING_BOOTSTRAP')
        environment=observe('worker_environment_stable',reader.worker_environment)
        need(environment==first_environment,'WORKER_ENVIRONMENT_CHANGED_DURING_BOOTSTRAP')
        seen_boot=boot_id_sha256(host,gate)
        observe('boot_stable',lambda:k9_item(findings=[] if seen_boot==reader.boot_hash else ['BOOT_CHANGED_DURING_BOOTSTRAP'],equal_to_first=seen_boot==reader.boot_hash))
        # Repeat the positive absence/emptiness checks immediately before the claim.
        observe('directory:SECRETS',lambda:empty_secrets(reader));emitter=observe('directory:EMITTER',lambda:absent_entry(reader,'emitter'))
        observe('secret:EMITTER/password',lambda:absent_password(emitter))
        for name in ('provider.env','risk-db.env'):observe('secret:SECRETS/'+name,lambda name=name:absent_entry(reader,name))
        observe('directories_stable',reader.stable)
        parent=reader.held['CLAIMS']
        exclusive_epoch_claim(host,parent,gate,state,bound,reader.boot_hash,reader.worker_id,row)
        if row['state']!='VERIFIED':raise Refused(row['code'] or 'BOOTSTRAP_CLAIM_NOT_VERIFIED')
        # After the effect, these are readbacks: a change consumes the claim and holds every dependent.
        worker=observe('worker_postclaim',reader.worker)
        need(worker==first_worker,'WORKER_CHANGED_AFTER_CLAIM')
        environment=observe('worker_environment_postclaim',reader.worker_environment)
        need(environment==first_environment,'WORKER_ENVIRONMENT_CHANGED_AFTER_CLAIM')
        observe('image_postclaim',reader.image)
        for key in ('policy','release'):observe(key+'_file_postclaim',lambda key=key:reader.installed(key))
        observe('runner_file_postclaim',reader.runner_file)
        observe('september_sources_postclaim',lambda:september_pinned(reader))
        observe('k9_filesystem_postclaim',lambda:reader.k9_filesystem(K9_DISK_FLOOR_BYTES))
        last_boot=boot_id_sha256(host,gate)
        observe('boot_postclaim',lambda:k9_item(findings=[] if last_boot==reader.boot_hash else ['BOOT_CHANGED_AFTER_CLAIM'],equal_to_first=last_boot==reader.boot_hash))
        observe('directory:SECRETS_postclaim',lambda:empty_secrets(reader))
        emitter_after=observe('directory:EMITTER_postclaim',lambda:absent_entry(reader,'emitter'))
        observe('secret:EMITTER/password_postclaim',lambda:absent_password(emitter_after))
        for name in ('provider.env','risk-db.env'):observe('secret:SECRETS/'+name+'_postclaim',lambda name=name:absent_entry(reader,name))
        observe('directories_stable_postclaim',reader.stable)
        gate()
    except BaseException as error:
        failure=code_of(error,'BOOTSTRAP_FAILED');items['failure']=safe(error)
    finally:
        cleanup=[]
        for key,handle in reader.held.items():
            try:handle.close()
            except BaseException as error:cleanup.append(dict(item=key,**safe(error)))
        if cleanup:
            items['descriptor_cleanup']={'status':'UNAVAILABLE','code':'BOOTSTRAP_DESCRIPTOR_CLOSE_FAILED','failures':cleanup}
            if failure is None:failure='BOOTSTRAP_DESCRIPTOR_CLOSE_FAILED'
    final_mono=None
    try:
        final_wall,final_mono=clock(),monotonic()
        final_clock={'utc_start':begun.isoformat(),'utc_end':final_wall.isoformat(),'monotonic_elapsed_ms':int((final_mono-mark)*1000)}
    except BaseException as error:
        final_clock=None;items['final_clock_failure']=safe(error)
    valid_clock=False
    if type(final_clock) is dict:
        try:
            end=instant(final_clock['utc_end']);start=instant(final_clock['utc_start'])
            last_wall=getattr(gate,'wall',None);last_mono=getattr(gate,'mono',None)
            valid_clock=(instant(BOOTSTRAP_START)<=start<=end<instant(BOOTSTRAP_END) and integer(final_clock['monotonic_elapsed_ms'],0,MAX_SECONDS*1000-1)
                         and (last_wall is None or end>=last_wall)
                         and (last_mono is None or (final_mono is not None and final_mono>=last_mono)))
        except (Refused,KeyError,TypeError):valid_clock=False
    if not valid_clock and failure is None:failure='BOOTSTRAP_FINAL_CLOCK_INVALID'
    effect=row['possible_creation'] or row['created_by_this_run'] is True or not state.clean()
    if failure is None and row['state']=='VERIFIED':status,outcome,code=COMPLETE_STATUS,COMPLETE_OUTCOME,None
    elif effect:status,outcome,code=PARTIAL_STATUS,PARTIAL_OUTCOME,failure or row['code'] or 'BOOTSTRAP_CLAIM_UNCERTAIN'
    else:status,outcome,code=REFUSED_STATUS,REFUSED_OUTCOME,failure or row['code'] or 'BOOTSTRAP_REFUSED'
    findings=sorted({code for item in items.values() for code in item.get('findings') or []})
    return seal(envelope(status,outcome,code,dict(bound,mode=BOOTSTRAP_MODE,epoch=BOOTSTRAP_EPOCH,slot=BOOTSTRAP_SLOT,attempt_key=bootstrap_key(),
        boot_id_sha256=reader.boot_hash,claim=row,effects=effects_of(plan),items=items,findings=findings,
        items_not_complete=sorted(name for name,item in items.items() if item.get('status')!='COMPLETE'),
        expectations_met=status==COMPLETE_STATUS,mutating_calls=state.counts(),clock=final_clock,
        commands_started=dict(commands.started),phase_reached='CLAIM' if row['state']!='NOT_ATTEMPTED' else 'PRECHECK',
        nothing_changed_by_this_run=not effect,dependents_hold=status!=COMPLETE_STATUS,secret_contents_opened=False,
        environment_inspection_scope='Docker CLI/daemon process Config.Env; Python receives five approved LIVE booleans only')))
