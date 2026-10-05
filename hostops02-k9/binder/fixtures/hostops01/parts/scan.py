UNIT_DIRECTORY='/etc/systemd/system'
UNIT_NAME=r'c3po-[a-z0-9]+(-[a-z0-9]+)*\.(service|timer)'
MAX_UNITS=8
# The system manager's unit search path, highest priority first. /lib/systemd/system is left out on purpose: on a
# merged-/usr host /lib is a symbolic link to usr/lib, so it is the same directory as /usr/lib/systemd/system.
LOOKUP_DIRECTORIES=['/etc/systemd/system.control','/run/systemd/system.control','/run/systemd/transient',
                    '/run/systemd/generator.early','/etc/systemd/system','/etc/systemd/system.attached',
                    '/run/systemd/system','/run/systemd/system.attached','/run/systemd/generator',
                    '/usr/local/lib/systemd/system','/usr/lib/systemd/system','/run/systemd/generator.late']
DEPENDENCY_SUFFIXES=('.wants','.requires','.upholds')
LEFTOVER=r'\.hostops-[0-9a-f]{16}-[0-9]{1,2}\.partial'
SCAN_NAME='[A-Za-z0-9@._:-]{1,128}'
MAX_SCAN_NAMES=4096
MAX_FINDINGS=64
# What the scan looks for; every source that carries the scan signs this text in its scope.
CONFLICT_SCAN_SCOPE={'lookup_directories':LOOKUP_DIRECTORIES,'dependency_suffixes':list(DEPENDENCY_SUFFIXES),
                     'drop_in_forms':['<name>.d','<type>.d','<dash-truncated prefix>-.<type>.d'],
                     'own_dependency_directories':['<name>.wants','<name>.requires','<name>.upholds'],
                     'alias_links':'a symbolic link named *.<type> whose text ends in a signed unit name; the text is read, the link is never followed',
                     'not_scanned':['/lib/systemd/system when /lib is a symbolic link (same directory as /usr/lib/systemd/system)',
                                    'a link inside a dependency directory whose own name is not a signed name but whose text ends in one',
                                    'user-manager directories']}

class NativeScan:
    """The one read primitive only the scan needs: the text of a symbolic link. The link is never followed."""
    def readlink(self,name,dir_fd):return os.readlink(name,dir_fd=dir_fd)

def unit_name(value):return text(value,UNIT_NAME) and len(value)<=64
def unit_names(value):
    return (type(value) is list and 0<len(value)<=MAX_UNITS and all(unit_name(name) for name in value)
            and len(set(value))==len(value))
def drop_in_names(name):
    """<name>.d, the type-level <type>.d, and each dash-truncated prefix form the manager also reads."""
    stem,_,suffix=name.rpartition('.');parts=stem.split('-')
    return [name+'.d',suffix+'.d']+['-'.join(parts[:index])+'-.'+suffix+'.d' for index in range(1,len(parts))]
def file_row(info):
    """Metadata of a unit file or of a leftover temporary of this family, size included. A caller that reports a file
    it did not prove to be the signed render removes the size (it would measure foreign content)."""
    return {'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),
            'links':info.st_nlink,'size':info.st_size,'device':info.st_dev,'inode':info.st_ino}

def conflict_scan(host,names,check):
    """lstat only, no content. In every lookup directory: a unit of the same name anywhere but the install directory,
    every drop-in directory form, the unit's own dependency directories (<name>.wants and the like, which add
    dependencies to the unit without any drop-in), the name inside every dependency directory, and every symbolic
    link of a unit type whose text ends in one of the names (an alias). In the install directory also the leftover
    temporaries of this family. A directory that cannot be read is UNAVAILABLE, never an absence. In a finding row
    "within" is the dependency directory the name was found in or, for an alias, the unit name the link text ends in."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    findings=[];leftovers=[];directories={}
    types=tuple(sorted({'.'+name.rpartition('.')[2] for name in names}))
    def present(name,fd):
        check()
        try:return host.lstat(name,fd)
        except FileNotFoundError:return None
    def add(code,directory,name,within=None):
        findings.append({'code':code,'directory':directory,'name':name,'within':within})
    def one(directory):
        try:fd=descend(host,directory,check)
        except FileNotFoundError:return {'status':'COMPLETE','exists':False}
        try:
            listed=[];issues=[]
            for name in host.names(fd):
                listed.append(name);need(len(listed)<=MAX_SCAN_NAMES,'SCAN_LIMIT')
                if len(listed)%256==0:check()
            for name in names:
                if directory!=UNIT_DIRECTORY and present(name,fd) is not None:add('UNIT_SHADOWED_IN_OTHER_PATH',directory,name)
                for candidate in drop_in_names(name):
                    if present(candidate,fd) is not None:add('DROP_IN_PRESENT',directory,candidate)
                for suffix in DEPENDENCY_SUFFIXES:
                    if present(name+suffix,fd) is not None:add('OWN_DEPENDENCY_DIRECTORY_PRESENT',directory,name+suffix)
            for entry in sorted(listed):
                if directory==UNIT_DIRECTORY and text(entry,LEFTOVER):
                    info=present(entry,fd)
                    if info is not None:leftovers.append(dict(file_row(info),name=entry))
                if entry.endswith(types) and entry not in names:
                    info=present(entry,fd)
                    if info is not None and stat.S_ISLNK(info.st_mode):
                        check();target=host.readlink(entry,fd)
                        need(type(target) is str,'LINK_TEXT_UNREADABLE')
                        if PurePosixPath(target).name in names:
                            add('ALIAS_LINK_PRESENT',directory,entry if text(entry,SCAN_NAME) else None,PurePosixPath(target).name)
                if not entry.endswith(DEPENDENCY_SUFFIXES):continue
                info=present(entry,fd)
                if info is None:continue
                label=entry if text(entry,SCAN_NAME) else None
                if not stat.S_ISDIR(info.st_mode):
                    issues.append('DEPENDENCY_DIRECTORY_NOT_A_DIRECTORY');continue
                check();child=host.open(entry,flags,dir_fd=fd)
                try:
                    held=host.fstat(child);need((held.st_dev,held.st_ino)==(info.st_dev,info.st_ino),'PATH_CHANGED')
                    for name in names:
                        if present(name,child) is not None:add('ENABLEMENT_LINK_PRESENT',directory,name,label)
                finally:host.close(child)
            return {'status':'COMPLETE' if not issues else 'UNAVAILABLE','exists':True,'entries':len(listed),
                    **({'code':issues[0]} if issues else {})}
        finally:host.close(fd)
    for directory in LOOKUP_DIRECTORIES:directories[directory]=attempt(lambda directory=directory:one(directory))
    status=combined(directories.values())
    return {'status':'COMPLETE' if status=='COMPLETE' else 'UNAVAILABLE','directories':directories,
            'findings':findings[:MAX_FINDINGS],'findings_truncated':len(findings)>MAX_FINDINGS,
            'finding_codes':sorted({item['code'] for item in findings}),'leftovers':leftovers[:MAX_FINDINGS],
            'leftover_count':len(leftovers)}
