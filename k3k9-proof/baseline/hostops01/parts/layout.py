GROUPS=('SUPERVISOR','JOURNAL_LEAF','READER','CAPACITY','RETENTION_TAG')
DIRECTORY_MODE=0o700
SUP_CONFIG='/etc/c3po-bar'
SUP_STATE_PARENT='/var/lib/c3po-bar'
SUP_STATE=SUP_STATE_PARENT+'/supervisor'
# Where the journal root of an epoch is created (supervisor README, "Journal placement"), signed per request:
#   A  <SUP_STATE_PARENT>/<leaf>, next to the state root on the host's root filesystem; the data volume is not touched
#   B  <data volume>/<leaf>, a leaf of the data volume
JOURNAL_PLACEMENTS=('A','B')
RDR_CONFIG='/etc/c3po-reader'
RDR_STATE='/var/lib/c3po-reader'
CHAIN_PATHS={'ETC':'/etc','VAR_LIB':'/var/lib','SUP_STATE_PARENT':SUP_STATE_PARENT}
CAPACITY_ROOTS=('config','documents','payload','go')
LEAF='[A-Za-z0-9][A-Za-z0-9._-]{0,63}'
# An entry of the data volume root named r2d2-v2-release-*.json that cannot be read as JSON holds the automatic security
# reboot and merges (scripts/c3po_security_guard.py). No directory created here may take such a name.
NAME_DENY=['r2d2-v2-release-.*']
# A parameterised path (data volume, capacity root) is never one of these or below one of them.
FORBIDDEN_ZONES=['/etc','/usr','/run','/proc','/sys','/dev','/boot','/bin','/sbin','/lib','/lib64','/var/run',
                 '/var/lib/docker','/var/lib/containerd','/var/lib/c3po-bar','/var/lib/c3po-reader']
# The fixed directories of this family. A parameterised path is never one of them and never above one of them: a
# data volume named /var or /var/lib would lift the code floor from the chain the fixed layout hangs from.
FIXED_PATHS=['/etc','/etc/systemd/system','/var/lib',SUP_CONFIG,SUP_STATE_PARENT,RDR_CONFIG,RDR_STATE]
REPOSITORY='c3po/backend'
TAG='massive-supervisor-[a-z0-9][a-z0-9.-]{0,40}'
MAX_LEAVES=32

def leaf_name(value):
    return text(value,LEAF) and not any(re.fullmatch(pattern,value) for pattern in NAME_DENY)
def open_path(value):
    return (clean_path(value) and value!='/' and not any(inside(value,zone) for zone in FORBIDDEN_ZONES)
            and not any(inside(fixed,value) for fixed in FIXED_PATHS)
            and all(leaf_name(part) for part in PurePosixPath(value).parts[1:]))

def validate_parameters(groups,volume,leaf,existing,capacity,placement):
    """Everything the layout is instantiated from, before any host access. The data volume is a parameter only when
    something is created in it: a journal leaf under placement B, or the capacity tree."""
    need(type(groups) is list and groups and all(type(group) is str for group in groups)
         and groups==[group for group in GROUPS if group in groups],'GROUPS_INVALID')
    need(type(existing) is list and len(existing)<=MAX_LEAVES and all(leaf_name(name) for name in existing)
         and len(set(existing))==len(existing),'LEAF_INVALID')
    if 'JOURNAL_LEAF' in groups:need(type(placement) is str and placement in JOURNAL_PLACEMENTS,'PLACEMENT_UNKNOWN')
    else:need(placement is None,'PLACEMENT_UNKNOWN')
    if placement=='B' or 'CAPACITY' in groups:
        need(type(volume) is str and clean_path(volume),'PATH_INVALID');need(open_path(volume),'PATH_FORBIDDEN_ZONE')
    else:need(volume is None,'PATH_INVALID')
    if placement=='B':
        need(leaf_name(leaf) and leaf not in existing,'LEAF_INVALID')
        need(open_path(volume+'/'+leaf),'PATH_FORBIDDEN_ZONE')         # the composed path, not only its two halves
    elif placement=='A':
        need(leaf_name(leaf) and SUP_STATE_PARENT+'/'+leaf!=SUP_STATE,'LEAF_INVALID')      # a sibling of the state root, never the state root
    else:need(leaf is None,'LEAF_INVALID')
    if 'CAPACITY' in groups:
        need(type(capacity) is dict and set(capacity)=={'root_path','receipt_directory_path'},'PATH_INVALID')
        root,receipts=capacity['root_path'],capacity['receipt_directory_path']
        need(type(root) is str and clean_path(root) and type(receipts) is str and clean_path(receipts),'PATH_INVALID')
        need(open_path(root) and len(PurePosixPath(root).parts)>=3,'PATH_FORBIDDEN_ZONE')
        journals=[volume+'/'+name for name in existing+([leaf] if placement=='B' else [])]
        need(not any(inside(root,journal) or inside(journal,root) for journal in journals) and root!=volume
             and not inside(volume,root),'CAPACITY_JOURNAL_OVERLAP')
        parent=str(PurePosixPath(receipts).parent)
        need(leaf_name(PurePosixPath(receipts).name)
             and ((parent==root and PurePosixPath(receipts).name not in CAPACITY_ROOTS) or (parent==RDR_STATE and 'READER' in groups)),
             'CAPACITY_RECEIPTS_PARENT')
    else:need(capacity is None,'PATH_INVALID')

def layout(groups,volume,leaf,capacity,placement):
    """The whole table of what may be created, instantiated for the signed parameters, in creation order.
    Everything is a directory, root:root, mode 0700. A path outside this table is never created by this code."""
    rows=[]
    def add(key,path,parent):rows.append({'key':key,'path':path,'mode':DIRECTORY_MODE,'parent':parent})
    if 'SUPERVISOR' in groups:
        add('SUP_CONFIG',SUP_CONFIG,{'chain':'ETC'})
        add('SUP_MANIFESTS',SUP_CONFIG+'/manifests',{'entry':'SUP_CONFIG'})
        add('SUP_DOCKER_CLI',SUP_CONFIG+'/docker-cli',{'entry':'SUP_CONFIG'})
        add('SUP_STATE_PARENT',SUP_STATE_PARENT,{'chain':'VAR_LIB'})
        add('SUP_STATE',SUP_STATE,{'entry':'SUP_STATE_PARENT'})
    if 'JOURNAL_LEAF' in groups and placement=='A':
        # Below the private parent: created by this request, or (a later epoch) existing and pinned by its own chain.
        add('SUP_JOURNAL',SUP_STATE_PARENT+'/'+leaf,{'entry':'SUP_STATE_PARENT'} if 'SUPERVISOR' in groups else {'chain':'SUP_STATE_PARENT'})
    elif 'JOURNAL_LEAF' in groups:add('SUP_JOURNAL',volume+'/'+leaf,{'chain':'DATA_VOLUME'})
    if 'READER' in groups:
        add('RDR_CONFIG',RDR_CONFIG,{'chain':'ETC'})
        add('RDR_DOCKER_CLI',RDR_CONFIG+'/docker-cli',{'entry':'RDR_CONFIG'})
        add('RDR_STATE',RDR_STATE,{'chain':'VAR_LIB'})
    if 'CAPACITY' in groups:
        root,receipts=capacity['root_path'],capacity['receipt_directory_path']
        add('CAP_ROOT',root,{'chain':'DATA_VOLUME' if str(PurePosixPath(root).parent)==volume else 'CAPACITY_PARENT'})
        for name in CAPACITY_ROOTS:add('CAP_'+name.upper(),root+'/'+name,{'entry':'CAP_ROOT'})
        add('CAP_RECEIPTS',receipts,{'entry':'CAP_ROOT' if str(PurePosixPath(receipts).parent)==root else 'RDR_STATE'})
    return rows

def chain_paths(table,volume,capacity):
    """chain id -> the existing directory that chain ends at, for exactly the chains this table needs."""
    paths=dict(CHAIN_PATHS,DATA_VOLUME=volume)
    if capacity is not None:paths['CAPACITY_PARENT']=str(PurePosixPath(capacity['root_path']).parent)
    return {row['parent']['chain']:paths[row['parent']['chain']] for row in table if 'chain' in row['parent']}

def world_writable_without_sticky(row):return bool(row['mode']&0o002) and not row['mode']&stat.S_ISVTX
def row_accepted(row,volume):
    """None when a write operation accepts the signed row, otherwise the refusal code."""
    if row_root_safe(row):return None
    if volume is None or not inside(row['path'],volume):return 'CHAIN_ROW_UNSAFE'
    return 'CHAIN_ROW_WORLD_WRITABLE' if world_writable_without_sticky(row) else None

def validate_chains(chains,paths,volume):
    """Rows are observed values. Outside the data volume every component must be root-owned and not writable by
    group or other; at and below the data volume root the observed owner and mode are accepted as signed, except a
    directory any local user can write to without the sticky bit (there any user could rename what this run creates).
    The directory that receives a new entry must not be setgid: the kernel would hand its group and the bit to the child."""
    need(type(chains) is dict and set(chains)==set(paths),'CHAIN_MISSING')
    for name,path in paths.items():
        rows=chain_rows(chains[name],path)
        for row in rows:
            code=row_accepted(row,volume);need(code is None,code or 'CHAIN_ROW_UNSAFE')
        need(not rows[-1]['mode']&stat.S_ISGID,'PARENT_SETGID')

def volume_root_facts(chains,volume):
    """Two facts about the data volume root that the signers see literally in the effects, computed from the signed
    rows: whether any local user could rename an entry in it, and whether it is a mount point (its device differs
    from its parent's). On a volume that is not mounted the journal leaf would land on the parent's filesystem."""
    rows=(chains or {}).get('DATA_VOLUME')
    if volume is None or not rows or len(rows)<2:return {'world_writable_without_sticky':None,'device_differs_from_parent':None}
    return {'world_writable_without_sticky':world_writable_without_sticky(rows[-1]),'device_differs_from_parent':rows[-1]['device']!=rows[-2]['device']}
