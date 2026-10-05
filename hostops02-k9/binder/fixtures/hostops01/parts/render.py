import base64

# Validation and rendering of the supervisor unit: validate_substitutions() and the render loop are Codex's
# (supervisor-installer-rev2, installer.py sha256 c53732b0be2469344c3b39bd182c401c13dff52dc0d33430cdd838df02751356),
# judged correct by the audit, with the audit's corrections: item types are checked before set(), containment is
# refused in both directions, and paths, components and the rendered text have length limits.
# The journal placement is the README's "Substitution grammar" as it stands at repository revision a6dd2b1 (README
# sha256 27bf0e5a...dc2b): the placement (A outside the data volume, B a leaf of it) is signed, and the path rules
# follow it. The codes and their order are those of the repository's own reading of that prose (placement_refusal in
# backend/tests/test_r2d2_v2_massive_supervisor.py), so the two can be compared case by case.
SERVICE_PROFILE='MASSIVE_SUPERVISOR_SERVICE_V1'
TIMER_PROFILE='MASSIVE_SUPERVISOR_TIMER_V1'
PROFILES=(SERVICE_PROFILE,TIMER_PROFILE,'VERBATIM_V1','GENERIC_KINDS_V1')
FROZEN_TEMPLATES={SERVICE_PROFILE:'9e7de1c6eaf937e5b1fc9540986fdbdf2a2f821a9c57b944f9534a605d07f04a',
                  TIMER_PROFILE:'ec61b1d6cbd1d604e5c2177d186f9045e67bf21ecc092498691591dfd9164ee6'}
# The supervisor's two names can only be installed from the frozen templates, and the frozen profiles serve no other name.
REQUIRED_PROFILE={'c3po-massive.service':SERVICE_PROFILE,'c3po-massive.timer':TIMER_PROFILE}
OCCURRENCES={'IMAGE_ID':2,'HOST_JOURNAL_ROOT':2,'CONTAINER_JOURNAL_ROOT':2,
             'HOST_STATE_ROOT':2,'HOST_CONFIG_DIR':3,'NETWORK':1}
PATH_VALUES=('HOST_JOURNAL_ROOT','CONTAINER_JOURNAL_ROOT','HOST_STATE_ROOT','HOST_CONFIG_DIR')
PLACEMENTS=('A','B')
CONTAINER_DATA='/app/day-d-data'
# Under placement A the container journal root is exactly one new top-level directory: none of these, which the image
# or the runtime provides at "/" (the README's list; it calls the list a floor).
PROVIDED_TOP_LEVEL=('app','bin','boot','dev','etc','home','lib','lib64','media','mnt','opt','proc','root','run','sbin','srv','sys','tmp','usr','var')
# The unit's own container targets, literal in the frozen template: the state root, the configuration directory, the tmpfs.
FIXED_TARGETS=('/var/lib/c3po-bar/supervisor','/etc/c3po-bar','/tmp')
VALUE_PATH='/[A-Za-z0-9_./-]+'
NETWORK='[A-Za-z0-9][A-Za-z0-9_.-]{0,127}'
FORBIDDEN_NETWORKS=('host','none')
KINDS=('IMAGE_ID','ABSOLUTE_PATH','NETWORK')
PLACEHOLDER='[A-Z][A-Z0-9_]{0,63}'
MAX_PATH_LENGTH=200
MAX_COMPONENT_LENGTH=64
MAX_TEMPLATE_BYTES=16384
MAX_TEMPLATE_BYTES_TOTAL=24576
MAX_RENDER_BYTES=65536
MAX_PLACEHOLDERS=16

def safe_path(value):
    need(type(value) is str and re.fullmatch(VALUE_PATH,value) is not None,'PATH_INVALID')
    need(len(value)<=MAX_PATH_LENGTH,'PATH_TOO_LONG')
    parts=value.split('/')[1:]
    need(all(part not in ('','.','..') for part in parts),'PATH_COMPONENT')
    need(all(len(part)<=MAX_COMPONENT_LENGTH for part in parts),'PATH_TOO_LONG')
    return PurePosixPath(value)

def validate_allowlist(network_allowlist):
    need(type(network_allowlist) is list and 0<len(network_allowlist)<=16
         and all(type(name) is str for name in network_allowlist)
         and len(set(network_allowlist))==len(network_allowlist),'NETWORK_ALLOWLIST')
    for name in network_allowlist:
        need(re.fullmatch(NETWORK,name) is not None and name not in FORBIDDEN_NETWORKS,'NETWORK_FORBIDDEN')

def overlaps(one,other):return one==other or one in other.parents or other in one.parents
def within(path,tree):return path==tree or tree in path.parents

def validate_substitutions(values,network_allowlist,data_volume,placement,deploy_tree):
    """The six values, in the signed placement. The data volume and (under placement A) the deploy tree are signed
    strings used for the path rules only; nothing here touches the host."""
    need(type(values) is dict and set(values)==set(OCCURRENCES),'SUBSTITUTION_KEYS')
    for name in PATH_VALUES:safe_path(values[name])
    need(type(values['IMAGE_ID']) is str and re.fullmatch(IMAGE_ID,values['IMAGE_ID']) is not None,'IMAGE_ID')
    validate_allowlist(network_allowlist)
    need(type(values['NETWORK']) is str and values['NETWORK'] in network_allowlist,'NETWORK_NOT_AUTHORIZED')
    placement_rules(values,data_volume,placement,deploy_tree)

def placement_rules(values,data_volume,placement,deploy_tree):
    """Where the journal root may be, for the four path values: the README's placement rules and nothing else. Also
    applied by the readback to the values it parses from the installed unit."""
    need(type(placement) is str and placement in PLACEMENTS,'PLACEMENT_UNKNOWN')
    volume=safe_path(data_volume);journal=safe_path(values['HOST_JOURNAL_ROOT'])
    container=safe_path(values['CONTAINER_JOURNAL_ROOT']);state=safe_path(values['HOST_STATE_ROOT']);config=safe_path(values['HOST_CONFIG_DIR'])
    # In every placement.
    need(not any(overlaps(journal,private) for private in (state,config)),'HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT')
    need(not any(overlaps(container,PurePosixPath(target)) for target in FIXED_TARGETS),'CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET')
    need(not any(within(private,volume) for private in (state,config)),'PRIVATE_ROOT_INSIDE_DATA_VOLUME')
    if placement=='A':
        need(type(deploy_tree) is str,'DEPLOY_TREE_PATH');tree=safe_path(deploy_tree)
        need(not within(journal,volume),'A_HOST_JOURNAL_INSIDE_DATA_VOLUME')
        need(not within(journal,tree),'A_HOST_JOURNAL_INSIDE_DEPLOY_TREE')
        need(len(container.parts)==2,'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL')
        need(container.name not in PROVIDED_TOP_LEVEL,'A_CONTAINER_JOURNAL_PROVIDED_DIRECTORY')
    else:
        need(deploy_tree is None,'DEPLOY_TREE_PATH')
        need(journal.parent==volume,'B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME')
        need(container==PurePosixPath(CONTAINER_DATA)/journal.name,'B_CONTAINER_JOURNAL_NOT_THE_SAME_LEAF')
    # Beyond the README, from the installer audit: the data volume is not inside a private root either, and the two
    # private roots do not overlap each other.
    need(not any(private in volume.parents for private in (state,config)),'DATA_INSIDE_PRIVATE')
    need(not overlaps(state,config),'PRIVATE_PATH_OVERLAP')

def render_service(template,values):
    """Six substitutions into the frozen bytes (the caller has pinned them); fails if any '@' survives. No host access."""
    unit=template.decode('ascii')
    tokens=re.findall(r'@([A-Z_]+)@',unit)
    need(set(tokens)==set(OCCURRENCES) and all(tokens.count(key)==count for key,count in OCCURRENCES.items()),'PLACEHOLDER_COUNTS')
    for key in OCCURRENCES:unit=unit.replace('@'+key+'@',values[key])
    need('@' not in unit,'UNRESOLVED_PLACEHOLDER')
    return unit.encode('ascii')

def render_generic(template,placeholders,network_allowlist):
    """Units other than the supervisor's (the reader's, under their own GO): the signed placeholder set, each value
    in the grammar of its kind, exact occurrence counts. The binding guard is the signed rendered hash."""
    need(type(placeholders) is dict and 0<len(placeholders)<=MAX_PLACEHOLDERS
         and all(text(name,PLACEHOLDER) for name in placeholders),'SUBSTITUTION_KEYS')
    for name,item in placeholders.items():
        need(type(item) is dict and set(item)=={'kind','value','occurrences'} and item['kind'] in KINDS
             and integer(item['occurrences'],1,64),'SUBSTITUTION_KEYS')
        if item['kind']=='ABSOLUTE_PATH':safe_path(item['value'])
        elif item['kind']=='IMAGE_ID':need(text(item['value'],IMAGE_ID),'IMAGE_ID')
        else:need(type(item['value']) is str and item['value'] in network_allowlist,'NETWORK_NOT_AUTHORIZED')
    unit=template.decode('ascii')
    tokens=re.findall('@('+PLACEHOLDER+')@',unit)
    need(set(tokens)==set(placeholders) and all(tokens.count(name)==item['occurrences'] for name,item in placeholders.items()),
         'PLACEHOLDER_COUNTS')
    for name in sorted(placeholders):unit=unit.replace('@'+name+'@',placeholders[name]['value'])
    need('@' not in unit,'UNRESOLVED_PLACEHOLDER')
    return unit.encode('ascii')

def decode_template(unit):
    value=unit['template_b64']
    need(type(value) is str and len(value)<=4*((MAX_TEMPLATE_BYTES+2)//3),'TEMPLATE_TOO_LARGE')
    try:raw=base64.b64decode(value.encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused('TEMPLATE_ENCODING') from None
    need(base64.b64encode(raw).decode('ascii')==value,'TEMPLATE_ENCODING')
    need(0<len(raw)<=MAX_TEMPLATE_BYTES,'TEMPLATE_TOO_LARGE')
    need(hexpin(unit['template_sha256']) and sha(raw)==unit['template_sha256'],'TEMPLATE_HASH_MISMATCH')
    need(re.fullmatch(rb'[\t\n -~]*',raw) is not None,'TEMPLATE_NOT_ASCII')
    return raw

def render_unit(unit,network_allowlist,data_volume,placement=None,deploy_tree=None):
    """One signed unit -> the exact bytes to install. Pure: nothing here touches the host."""
    name,profile=unit['destination_name'],unit['profile']
    need(type(profile) is str and profile in PROFILES,'PROFILE_UNKNOWN')
    need(REQUIRED_PROFILE.get(name,profile)==profile and (profile not in FROZEN_TEMPLATES or REQUIRED_PROFILE.get(name)==profile),
         'PROFILE_NAME_MISMATCH')
    template=decode_template(unit)
    if profile in FROZEN_TEMPLATES:need(sha(template)==FROZEN_TEMPLATES[profile],'FROZEN_TEMPLATE_HASH')
    if profile==SERVICE_PROFILE:
        validate_substitutions(unit['placeholders'],network_allowlist,data_volume,placement,deploy_tree)
        rendered=render_service(template,unit['placeholders'])
    elif profile=='GENERIC_KINDS_V1':rendered=render_generic(template,unit['placeholders'],network_allowlist)
    else:
        need(unit['placeholders']=={},'SUBSTITUTION_KEYS')
        need(b'@' not in template,'TIMER_PLACEHOLDER' if profile==TIMER_PROFILE else 'UNRESOLVED_PLACEHOLDER')
        rendered=template
    need(len(rendered)<=MAX_RENDER_BYTES,'RENDER_TOO_LARGE')
    need(hexpin(unit['rendered_sha256']) and sha(rendered)==unit['rendered_sha256'],'RENDERED_HASH_MISMATCH')
    need(type(unit['rendered_bytes']) is int and len(rendered)==unit['rendered_bytes'],'RENDERED_SIZE_MISMATCH')
    return rendered

VALUE_PATTERNS={'IMAGE_ID':IMAGE_ID,'HOST_JOURNAL_ROOT':VALUE_PATH,'CONTAINER_JOURNAL_ROOT':VALUE_PATH,
                'HOST_STATE_ROOT':VALUE_PATH,'HOST_CONFIG_DIR':VALUE_PATH,'NETWORK':NETWORK}
def extract_values(template,installed):
    """The six values as they stand in installed bytes: the template is cut at its placeholders and the installed text
    must match literal segment by literal segment, a repeated placeholder repeating its value. A parse of what is on
    disk, not a second run of the renderer. None when the bytes are not this template with six well-formed values."""
    try:pattern_text,candidate=template.decode('ascii'),installed.decode('ascii')
    except UnicodeDecodeError:return None
    parts=re.split(r'@([A-Z_]+)@',pattern_text);seen=[];out=[]
    for index,part in enumerate(parts):
        if index%2==0:out.append(re.escape(part))
        elif part not in VALUE_PATTERNS:return None
        elif part in seen:out.append('(?P=%s)'%part)
        else:seen.append(part);out.append('(?P<%s>%s)'%(part,VALUE_PATTERNS[part]))
    match=re.fullmatch(''.join(out),candidate)
    if match is None or set(seen)!=set(VALUE_PATTERNS):return None
    return {name:match.group(name) for name in sorted(seen)}
