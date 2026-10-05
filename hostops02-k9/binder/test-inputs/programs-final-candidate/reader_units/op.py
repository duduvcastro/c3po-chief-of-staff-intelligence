OPERATION='GO_WRITE_HOSTOPS02_READER_UNITS_01'
PHASE='WRITE_READER_UNITS_NO_ACTIVATION'
REQUEST_SCHEMA='WRITE_HOSTOPS02_READER_UNITS_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_READER_UNITS_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_READER_UNITS_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_READER_UNITS_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_READER_UNITS_PLAN_V1'
SOURCE_NAME='reader_units.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
DATE_CLASS='WRITE_SESSIONS'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The read-only precheck of the boot (it scanned the three reader names, alias links included, which this source
# cannot: section "Conflict scan" below), the install receipt of the producer unit and its readback.
PRODUCER_INSTALL_OPERATION='GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01'
PRODUCER_READBACK_OPERATION='GO_READONLY_SUPERVISOR_READBACK_01'
# Codex, #429 5985937724 E1-19: B2 only after E3 and the real catalogue. The catalogue initialisation (A9) is cited,
# and its two files are looked at in the journal root before anything is created.
CATALOG_INIT_OPERATION='GO_WRITE_HOSTOPS02_CATALOG_INIT_01'
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PRODUCER_INSTALL_OPERATION,PRODUCER_READBACK_OPERATION,CATALOG_INIT_OPERATION)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CREATED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
PLAN_KEYS=frozenset(('unit_rows','journal_rows','data_rows','units','acknowledged_leftovers','evidence_boot_id_sha256'))
UNIT_KEYS=frozenset(('key','destination_name','expect','rendered_sha256','rendered_bytes'))
EXPECT_KEYS=frozenset(('device','inode','links'))
LEFTOVER_KEYS=frozenset(('name','device','inode'))

# ---- PLACEMENT of epoch R2D2-V2-SHADOW-2026-10-05. A request cannot move any of these: they are bytes of the signed
# ---- source. Where each value comes from is in DESIGN.md, section 3 (every one copied by command from a receipt, a
# ---- decision or the reader README; none typed from memory).
READER_EPOCH='R2D2-V2-SHADOW-2026-10-05'
UNIT_DIRECTORY='/etc/systemd/system'
UNIT_MODE=0o644
READER_SERVICE_NAME='c3po-reader.service'
READER_TIMER_NAME='c3po-reader.timer'
READER_ALERT_NAME='c3po-reader-alert.service'
UNIT_ORDER=(('READER_SERVICE',READER_SERVICE_NAME),('READER_TIMER',READER_TIMER_NAME),('READER_ALERT',READER_ALERT_NAME))
READER_VALUES={'IMAGE_ID':'sha256:f86bfb198c186657598c2c410fb39ca3dfed781d0db0522b9a796b80275cb621',
               'HOST_DATA_ROOT':'/mnt/day-d-data',
               'HOST_JOURNAL_ROOT':'/var/lib/c3po-bar/journal',
               'CONTAINER_JOURNAL_ROOT':'/c3po-bar-journal',
               'HOST_CAPACITY_ROOT':'/var/lib/c3po-capacity',
               'HOST_SOURCE_ROOT':'/var/lib/c3po/r2d2-v2-source-20261005',
               'CONTAINER_SOURCE_ROOT':'/c3po-source',
               'HOST_CONFIG_DIR':'/etc/c3po-reader',
               'NETWORK':'c3po_c3po_internal'}
# The installed producer unit (e3-20261004-a, KNOWN_COMPLETE; read back by l6-20261004-a): its bytes are the signed
# render of the supervisor template, and the reader's journal bind and image are taken from them.
PRODUCER_SERVICE_NAME='c3po-massive.service'
PRODUCER_SHA256='662c57b939d1a21e67e332434d3fa40368e2d503f3772f1cf3f7bd3631bdbc06'
PRODUCER_BYTES=1674
# Who reloads the manager: nobody here. The reader switch (K13, mode ACTIVATE, plan row M6) runs systemctl enable
# --now, which reloads the manager unless --no-reload (Codex decision 3 of 2026-10-04).
DAEMON_RELOAD_OWNER='GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01'
# The real catalogue in the journal root (catalog_init, A9 CATALOG_READY_VERIFIED): lstat only, never opened.
CATALOG_FILE_NAMES=('epoch.json','maintenance.lock')
CATALOG_FILE_MODE=0o600
# ---- end of the placement

# ---- TEMPLATES. The reader README directory of the installation candidate (opsart branch
# ---- ops/r2d2-v2-epoch03-artifacts-20261002, commit below; not in the release revision dd4ec4bb). The timer and the
# ---- alert unit are verbatim. The service is the README's c3po-reader.service (D1 default: the launcher) with exactly
# ---- two insertions for Codex decision 6 (#429 5985748037, 5985768668): the epoch's source root, outside the data
# ---- volume under a chain controlled by root alone, as a fifth read-only bind and in RequiresMountsFor.
TEMPLATE_REVISION='4a6f7675b8e418e0e7ee55a446250815f3bd5562'
README_SERVICE_SHA256='8d2ff7a91b94e39b8c7a0e91fae34b16dbc9d55f7af407b8464486a9bd064fab'
READER_SERVICE_TEMPLATE=r"""[Unit]
Description=Day-bounded R2D2 V2 shadow reader
Wants=network-online.target
Requires=docker.service
After=network-online.target docker.service
RequiresMountsFor=@HOST_DATA_ROOT@ @HOST_JOURNAL_ROOT@ @HOST_CAPACITY_ROOT@ @HOST_SOURCE_ROOT@ @HOST_CONFIG_DIR@
StartLimitIntervalSec=8h
StartLimitBurst=40
OnFailure=c3po-reader-alert.service

[Service]
Type=exec
Environment=DOCKER_CONFIG=@HOST_CONFIG_DIR@/docker-cli
ExecCondition=/usr/bin/test -f @HOST_CONFIG_DIR@/secret.env
ExecCondition=/usr/bin/test -f @HOST_CONFIG_DIR@/pins.env
ExecCondition=/usr/bin/test -f @HOST_CONFIG_DIR@/activation.env
ExecStartPre=-/usr/bin/docker rm c3po-reader
ExecStartPre=/usr/bin/docker image inspect --format {{.Id}} @IMAGE_ID@
ExecStart=/usr/bin/docker run --rm --init --restart no --name c3po-reader --pull never \
  --user 0:0 --workdir /app --network @NETWORK@ \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,nodev,size=256m \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 512 --stop-timeout 25 \
  --env-file @HOST_CONFIG_DIR@/secret.env \
  --env-file @HOST_CONFIG_DIR@/pins.env \
  --env-file @HOST_CONFIG_DIR@/activation.env \
  --mount type=bind,source=@HOST_DATA_ROOT@,target=/app/day-d-data,readonly \
  --mount type=bind,source=@HOST_JOURNAL_ROOT@,target=@CONTAINER_JOURNAL_ROOT@,readonly \
  --mount type=bind,source=@HOST_CAPACITY_ROOT@,target=/c3po-capacity,readonly \
  --mount type=bind,source=@HOST_SOURCE_ROOT@,target=@CONTAINER_SOURCE_ROOT@,readonly \
  --mount type=bind,source=@HOST_CONFIG_DIR@/launcher,target=/c3po-reader,readonly \
  @IMAGE_ID@ \
  python -I -B /c3po-reader/reader_launcher.py
ExecStop=-/usr/bin/docker stop -t 25 c3po-reader
ExecStopPost=-/usr/bin/docker stop -t 25 c3po-reader
Restart=on-failure
RestartSec=5s
RestartPreventExitStatus=78
TimeoutStartSec=60s
TimeoutStopSec=30s
KillMode=control-group
UMask=0077
NoNewPrivileges=true
StandardOutput=journal
StandardError=journal
SyslogIdentifier=c3po-reader
""".encode('ascii')
READER_SERVICE_TEMPLATE_SHA256='3dc976807a0ff443307fa12e357d478980441b26d19761b0d7964b5580327770'
READER_TIMER_TEMPLATE=r"""[Unit]
Description=Start the approved V2 shadow reader on session days

[Timer]
OnBootSec=90s
OnCalendar=Mon..Fri *-*-* 04:00:00 America/New_York
OnCalendar=Mon..Fri *-*-* 09:29:20 America/New_York
Persistent=false
AccuracySec=1s
Unit=c3po-reader.service

[Install]
WantedBy=timers.target
""".encode('ascii')
READER_TIMER_TEMPLATE_SHA256='dc81e21bfc2398330dd7eff02cbc8cf8d0e035bce883653cab4b10a1078ed4ba'
READER_ALERT_TEMPLATE=r"""[Unit]
Description=Record that the V2 shadow reader unit entered the failed state

[Service]
Type=oneshot
UMask=0077
ExecStart=/bin/sh -c 'umask 077 && set -C && /usr/bin/systemctl show c3po-reader.service --property=Result,ExecMainCode,ExecMainStatus,NRestarts > /var/lib/c3po-reader/failed.`/usr/bin/date -u +%%Y%%m%%dT%%H%%M%%SZ`'
StandardOutput=journal
StandardError=journal
SyslogIdentifier=c3po-reader-alert
""".encode('ascii')
READER_ALERT_TEMPLATE_SHA256='0653bf416e77c5b69d66e4952468380e89b2a79d1cc38c40509332ae015cce2f'
# Placeholders of the service and how often each occurs (the README's table, plus the two of decision 6).
SERVICE_OCCURRENCES={'IMAGE_ID':2,'HOST_DATA_ROOT':2,'HOST_JOURNAL_ROOT':2,'CONTAINER_JOURNAL_ROOT':1,'HOST_CAPACITY_ROOT':2,
                     'HOST_SOURCE_ROOT':2,'CONTAINER_SOURCE_ROOT':1,'HOST_CONFIG_DIR':9,'NETWORK':1}
HOST_PATH_NAMES=('HOST_DATA_ROOT','HOST_JOURNAL_ROOT','HOST_CAPACITY_ROOT','HOST_SOURCE_ROOT','HOST_CONFIG_DIR')
CONTAINER_TARGET_NAMES=('CONTAINER_JOURNAL_ROOT','CONTAINER_SOURCE_ROOT')
# The README's substitution grammar: four (here five) host paths, a positive grammar for a container path at a child
# of "/", the image by ID, and the network by name.
HOST_PATH_GRAMMAR='/[A-Za-z0-9._/-]+'
CONTAINER_TARGET_GRAMMAR='/c3po-[a-z0-9][a-z0-9-]*'
CONTAINER_TARGETS_TAKEN=('/c3po-capacity','/c3po-reader')
NETWORK_GRAMMAR='[A-Za-z0-9][A-Za-z0-9_.-]*'
FORBIDDEN_NETWORKS=('host','none','bridge')
TEMPLATE_FORBIDDEN_CHARACTERS=('%','$','"',"'",';')
MAX_UNIT_BYTES=16384
WRITE_ALLOWANCE_SECONDS=15                # what must be left of the budget before the first creation (the writes take milliseconds)

# ---- CONFLICT SCAN: the reviewed scan of HOSTOPS01 (scan.py) without alias links. A link's text cannot be read here:
# ---- the frozen core has no readlink and an operation part makes no system call of its own (CORE.md rule 4). The
# ---- precheck receipt of the same boot, which this request must cite, scanned the three names alias links included.
SCAN_DIRECTORIES=('/etc/systemd/system.control','/run/systemd/system.control','/run/systemd/transient',
                  '/run/systemd/generator.early','/etc/systemd/system','/etc/systemd/system.attached',
                  '/run/systemd/system','/run/systemd/system.attached','/run/systemd/generator',
                  '/usr/local/lib/systemd/system','/usr/lib/systemd/system','/run/systemd/generator.late')
DEPENDENCY_SUFFIXES=('.wants','.requires','.upholds')
SCAN_ENTRY_NAME='[A-Za-z0-9@._:-]{1,128}'
MAX_SCAN_ENTRIES=4096
MAX_FINDINGS=64
MAX_LEFTOVERS=16
SCAN_SCOPE={'lookup_directories':list(SCAN_DIRECTORIES),'dependency_suffixes':list(DEPENDENCY_SUFFIXES),
            'drop_in_forms':['<name>.d','<type>.d','<dash-truncated prefix>-.<type>.d'],
            'own_dependency_directories':['<name>.wants','<name>.requires','<name>.upholds'],
            'leftovers':'temporaries of the family in the unit directory, by name and identity',
            'not_scanned':['alias links (a symbolic link of a unit type whose text ends in a signed name): the frozen core reads no link text; '
                           'the cited precheck scanned them','/lib/systemd/system when /lib is a symbolic link (same directory as /usr/lib/systemd/system)',
                           'a link inside a dependency directory whose own name is not a signed name but whose text ends in one',
                           'user-manager directories']}

SCOPE_STATEMENT=('Creates only the three units of the V2 shadow reader in '+UNIT_DIRECTORY+' (c3po-reader.service rendered with the '
                 'values of this source, c3po-reader.timer and c3po-reader-alert.service verbatim), root:root, mode 0644, each written '
                 'under a dot-prefixed temporary name that systemd does not load, fsynced, then linked to its final name (a link never '
                 'replaces anything), after which the temporary of this run is removed once its identity is proved; nothing else is ever '
                 'removed. The installed producer unit, the journal root and the data volume are only read. No process is started: no '
                 'systemctl verb, no daemon-reload, no enablement, no start, no drop-in, no overwrite, no chmod, chown or rename. The '
                 'manager is reloaded by the reader switch under its own GO, never by this operation. A spent GO is never retried; after '
                 'anything other than the success criterion the host state is established by a read-only operation under its own GO.')


def overlap(first,second):return inside(first,second) or inside(second,first)

def placement_findings(values,producer_sources=()):
    """The README's isolation rules on the values, and the same relation between the host journal root and the other
    bind sources of the installed producer unit. Returns the codes of every rule broken, in a fixed order. Pure."""
    data,journal,capacity=values['HOST_DATA_ROOT'],values['HOST_JOURNAL_ROOT'],values['HOST_CAPACITY_ROOT']
    source,config=values['HOST_SOURCE_ROOT'],values['HOST_CONFIG_DIR']
    found=[]
    if any(overlap(config,other) for other in (data,capacity,journal,source)):found.append('CONFIG_DIRECTORY_OVERLAPS_A_BIND_SOURCE')
    if any(overlap(journal,other) for other in (data,capacity,source)):found.append('HOST_JOURNAL_OVERLAPS_A_BIND_SOURCE')
    if any(overlap(source,other) for other in (data,capacity)):found.append('SOURCE_ROOT_OVERLAPS_A_BIND_SOURCE')
    if overlap(capacity,data):found.append('CAPACITY_ROOT_OVERLAPS_THE_DATA_VOLUME')
    if any(overlap(journal,other) for other in producer_sources if other!=journal):found.append('HOST_JOURNAL_OVERLAPS_A_PRODUCER_PRIVATE_ROOT')
    targets=[values[name] for name in CONTAINER_TARGET_NAMES]
    if len(set(targets))!=len(targets) or any(target in CONTAINER_TARGETS_TAKEN for target in targets):found.append('CONTAINER_TARGETS_NOT_DISTINCT')
    return found

def render_service(template,values):
    """Plain textual substitution after the README's grammar: every value checked before rendering, each placeholder
    occurring exactly as counted, nothing of the form @NAME@ left. Returns the bytes. Pure."""
    need(type(template) is bytes and re.fullmatch(rb'[\x20-\x7e\n]*',template) is not None
         and not any(character.encode('ascii') in template for character in TEMPLATE_FORBIDDEN_CHARACTERS),'TEMPLATE_CHARACTERS')
    found=re.findall(rb'@([A-Z_]+)@',template)
    need({name.decode('ascii'):found.count(name) for name in set(found)}==SERVICE_OCCURRENCES,'PLACEHOLDER_COUNTS')
    need(type(values) is dict and set(values)==set(SERVICE_OCCURRENCES) and all(type(value) is str for value in values.values()),'SUBSTITUTION_KEYS')
    for name in HOST_PATH_NAMES:need(text(values[name],HOST_PATH_GRAMMAR) and clean_path(values[name]),'PATH_INVALID')
    for name in CONTAINER_TARGET_NAMES:need(text(values[name],CONTAINER_TARGET_GRAMMAR),'CONTAINER_TARGET_INVALID')
    need(text(values['IMAGE_ID'],IMAGE_ID),'IMAGE_ID_INVALID')
    network=values['NETWORK']
    need(text(network,NETWORK_GRAMMAR) and network not in FORBIDDEN_NETWORKS,'NETWORK_FORBIDDEN')        # container:* fails the grammar
    findings=placement_findings(values)
    need(not findings,findings[0] if findings else 'PLACEMENT_INVALID')
    rendered=template
    for name in sorted(values):rendered=rendered.replace(('@'+name+'@').encode('ascii'),values[name].encode('ascii'))
    need(b'@' not in rendered,'UNRESOLVED_PLACEHOLDER')         # the README: the render fails if any '@' survives
    need(len(rendered)<=MAX_UNIT_BYTES,'RENDER_TOO_LARGE')
    return rendered

def verbatim(template):
    """A unit installed as it stands: ASCII, no placeholder sign at all."""
    need(type(template) is bytes and re.fullmatch(rb'[\x20-\x7e\n]*',template) is not None and b'@' not in template
         and 0<len(template)<=MAX_UNIT_BYTES,'VERBATIM_TEMPLATE_INVALID')
    return template

def rendered_units():
    """The three files this source installs, by key, from its own templates and values. Pure."""
    need(sha(READER_SERVICE_TEMPLATE)==READER_SERVICE_TEMPLATE_SHA256 and sha(READER_TIMER_TEMPLATE)==READER_TIMER_TEMPLATE_SHA256
         and sha(READER_ALERT_TEMPLATE)==READER_ALERT_TEMPLATE_SHA256,'TEMPLATE_HASH_MISMATCH')
    return {'READER_SERVICE':render_service(READER_SERVICE_TEMPLATE,READER_VALUES),'READER_TIMER':verbatim(READER_TIMER_TEMPLATE),
            'READER_ALERT':verbatim(READER_ALERT_TEMPLATE)}

def producer_facts(raw):
    """What the installed producer unit says of the journal and of the image, read from its own text: the source and the
    target of the one bind whose target is its --journal-root argument, the image it names (twice, one ID), and the
    sources of its other binds. Pure; raises PRODUCER_UNIT_NOT_AS_SIGNED for any other shape."""
    need(type(raw) is bytes and re.fullmatch(rb'[\x20-\x7e\n]*',raw) is not None,'PRODUCER_UNIT_NOT_AS_SIGNED')
    body=raw.decode('ascii')
    binds=re.findall(r'(?m)^  --mount type=bind,source=(/[A-Za-z0-9._/-]+),target=(/[A-Za-z0-9._/-]+)(,readonly)? \\$',body)
    roots=re.findall(r' --journal-root (/[A-Za-z0-9._/-]+) ',body);images=re.findall(r'sha256:[0-9a-f]{64}',body)
    need(len(roots)==1 and body.count('--journal-root')==1 and len(images)==2 and len(set(images))==1 and body.count('--mount ')==len(binds),'PRODUCER_UNIT_NOT_AS_SIGNED')
    journal=[(source,target,readonly) for source,target,readonly in binds if target==roots[0]]
    need(len(journal)==1 and journal[0][2]=='','PRODUCER_UNIT_NOT_AS_SIGNED')
    return {'journal_source':journal[0][0],'journal_target':journal[0][1],'image_id':images[0],
            'other_sources':sorted(source for source,target,_ in binds if target!=roots[0])}

def root_only_chain(rows,path,code):
    """Signed rows of an existing directory under a chain controlled by root alone: no open root, every component uid 0
    and gid 0, not writable by group or other, not setgid (Codex decision 6 for bind sources; the unit directory too)."""
    rows=validate_chain(rows,path,open_root=None,receives_entry=True)
    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),code)
    return rows

def units_of(plan):
    """The three signed unit rows, in the fixed order, each compared with this source's own render. Pure.
    Returns [(unit, bytes)]."""
    units=plan['units'];renders=rendered_units()
    need(type(units) is list and len(units)==len(UNIT_ORDER),'UNITS_INVALID')
    out=[]
    for unit,(key,name) in zip(units,UNIT_ORDER):
        need(type(unit) is dict and set(unit)==set(UNIT_KEYS),'UNITS_INVALID')
        need(unit['key']==key and unit['destination_name']==name,'UNIT_NAME_INVALID')
        expect=unit['expect']
        need(expect=='ABSENT' or (type(expect) is dict and set(expect)==set(EXPECT_KEYS) and integer(expect['device'])
                                  and integer(expect['inode'],1) and integer(expect['links'],1,2)),'EXPECT_INVALID')
        content=renders[key]
        need(unit['rendered_sha256']==sha(content) and unit['rendered_bytes']==len(content),'RENDERED_HASH_MISMATCH')
        out.append((unit,content))
    need(any(unit['expect']=='ABSENT' for unit,_ in out),'NOTHING_TO_CREATE')
    return out

def leftovers_of(plan):
    items=plan['acknowledged_leftovers']
    need(type(items) is list and len(items)<=MAX_LEFTOVERS,'LEFTOVERS_INVALID')
    for item in items:
        need(type(item) is dict and set(item)==set(LEFTOVER_KEYS) and text(item['name'],LEFTOVER)
             and integer(item['device']) and integer(item['inode'],1),'LEFTOVERS_INVALID')
    need(len({item['name'] for item in items})==len(items),'LEFTOVERS_INVALID')
    return items

def validate_plan(plan):
    root_only_chain(plan['unit_rows'],UNIT_DIRECTORY,'UNIT_CHAIN_NOT_ROOT_CONTROLLED')
    journal=root_only_chain(plan['journal_rows'],READER_VALUES['HOST_JOURNAL_ROOT'],'JOURNAL_CHAIN_NOT_ROOT_CONTROLLED')
    need((journal[-1]['uid'],journal[-1]['gid'],journal[-1]['mode'])==(0,0,0o700),'JOURNAL_ROOT_NOT_PRIVATE')
    data=validate_chain(plan['data_rows'],READER_VALUES['HOST_DATA_ROOT'],open_root=READER_VALUES['HOST_DATA_ROOT'])
    need(mount_point_of(data)==READER_VALUES['HOST_DATA_ROOT'],'DATA_VOLUME_NOT_A_MOUNT_POINT')
    need(journal[-1]['device']!=data[-1]['device'],'JOURNAL_ON_THE_DATA_VOLUME')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    units_of(plan);leftovers_of(plan)

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    renders=rendered_units()
    return {'operation':OPERATION,'epoch':READER_EPOCH,'directory':chain_effects(plan['unit_rows']),
            'units':[{'destination_name':unit['destination_name'],'mode_octal':'%04o'%UNIT_MODE,'uid':0,'gid':0,
                      'rendered_sha256':sha(renders[unit['key']]),'rendered_bytes':len(renders[unit['key']]),
                      'expect':'ABSENT' if unit['expect']=='ABSENT' else 'PRESENT'} for unit in plan['units']],
            'files_to_create':sum(1 for unit in plan['units'] if unit['expect']=='ABSENT'),
            'values':dict(READER_VALUES),'template_revision':TEMPLATE_REVISION,
            'journal':chain_effects(plan['journal_rows']),'data_volume':chain_effects(plan['data_rows']),
            'producer_unit':{'path':UNIT_DIRECTORY+'/'+PRODUCER_SERVICE_NAME,'sha256':PRODUCER_SHA256,'bytes':PRODUCER_BYTES,'read_only':True},
            'acknowledged_leftovers':[item['name'] for item in plan['acknowledged_leftovers']],
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'daemon_reload':{'performed_by_this_operation':False,'owner':DAEMON_RELOAD_OWNER},
            'external_processes':0,'pre_existing_objects_modified':False,'activation':False}
def success_of(plan):return COMPLETE_OUTCOME

_RENDERED=rendered_units()
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,'epoch':READER_EPOCH,'unit_directory':UNIT_DIRECTORY,
       'units':[{'key':key,'destination_name':name,'rendered_sha256':sha(_RENDERED[key]),'rendered_bytes':len(_RENDERED[key]),
                 'template_sha256':{'READER_SERVICE':READER_SERVICE_TEMPLATE_SHA256,'READER_TIMER':READER_TIMER_TEMPLATE_SHA256,
                                    'READER_ALERT':READER_ALERT_TEMPLATE_SHA256}[key],
                 'how':'rendered' if key=='READER_SERVICE' else 'verbatim'} for key,name in UNIT_ORDER],
       'every_file':{'type':'regular file','uid':0,'gid':0,'mode_octal':'%04o'%UNIT_MODE,'umask_octal':'0022','links':1},
       'values':dict(READER_VALUES),'service_occurrences':dict(SERVICE_OCCURRENCES),'template_revision':TEMPLATE_REVISION,
       'template_deviation':{'readme_service_sha256':README_SERVICE_SHA256,
                             'inserted':['@HOST_SOURCE_ROOT@ in RequiresMountsFor, after @HOST_CAPACITY_ROOT@',
                                         '  --mount type=bind,source=@HOST_SOURCE_ROOT@,target=@CONTAINER_SOURCE_ROOT@,readonly \\ after the capacity bind'],
                             'why':'Codex decision 6 (#429 5985748037) and the placement 5985768668: the source root leaves the data volume'},
       'grammar':{'host_path':HOST_PATH_GRAMMAR,'container_target':CONTAINER_TARGET_GRAMMAR,'container_targets_taken':list(CONTAINER_TARGETS_TAKEN),
                  'image_id':IMAGE_ID,'network':NETWORK_GRAMMAR,'forbidden_networks':list(FORBIDDEN_NETWORKS)+['container:*'],
                  'template_forbidden_characters':list(TEMPLATE_FORBIDDEN_CHARACTERS)},
       'producer_unit':{'path':UNIT_DIRECTORY+'/'+PRODUCER_SERVICE_NAME,'sha256':PRODUCER_SHA256,'bytes':PRODUCER_BYTES,
                        'required':'regular, root:root 0644, one link, these bytes; its journal bind and image equal the reader values; '
                                   'its other bind sources do not overlap the host journal root'},
       'catalog':{'files':list(CATALOG_FILE_NAMES),'required':'regular, root:root 0600, one link, by lstat only (Codex E1-19: B2 only after E3 and the real catalogue)'},
       'journal':{'path':READER_VALUES['HOST_JOURNAL_ROOT'],'chain':'controlled by root alone (uid 0, gid 0, no group or other write, no setgid, no open root)',
                  'leaf':'root:root 0700','device':'differs from the data volume'},
       'data_volume':{'path':READER_VALUES['HOST_DATA_ROOT'],'open_root':READER_VALUES['HOST_DATA_ROOT'],'mount_point':True,
                      'decision_6':'NOT root-controlled (uid 1000): the one bind source of the unit outside decision 6; an open question, see DESIGN.md'},
       'bind_sources_not_opened_here':{'capacity':READER_VALUES['HOST_CAPACITY_ROOT'],'source_root':READER_VALUES['HOST_SOURCE_ROOT'],
                                       'launcher':READER_VALUES['HOST_CONFIG_DIR']+'/launcher'},
       'expect':['ABSENT: created exclusively','PRESENT with signed device, inode and link count: verified against the render, never touched'],
       'temporary_name':TEMPORARY%('<first 16 hex of the GO hash>',0),'leftover_pattern':LEFTOVER,
       'conflict_scan':SCAN_SCOPE,'files':FILES_SCOPE,'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'daemon_reload':{'performed_by_this_operation':False,'owner':DAEMON_RELOAD_OWNER},
       'file_contents_read':[BOOT_ID_PATH,UNIT_DIRECTORY+'/'+PRODUCER_SERVICE_NAME,
                             'a regular file found at a destination name, only to say whether its bytes equal the render: of a file that is not '
                             'the render no digest and no size is reported','the unit files this run installed (readback inside the run)'],
       'external_processes':0,
       'never':['a process','systemctl','daemon-reload','enablement link','start','drop-in','overwrite','chmod','chown','rename','truncate',
                'removal of anything but the temporary this run created and proved by identity','repair of an existing object',
                'docker','container environment','a secret','shell','network connection','a second attempt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'unit_bytes':MAX_UNIT_BYTES,'scan_entries':MAX_SCAN_ENTRIES,
                 'findings':MAX_FINDINGS,'leftovers':MAX_LEFTOVERS,'write_allowance_seconds':WRITE_ALLOWANCE_SECONDS,'receipt_bytes':RECEIPT_LIMIT}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeFiles):
    """Everything this source can do to the host: the read primitives and the creating calls. No process."""


# ---------------------------------------------------------------- the conflict scan (lstat and names only)
def drop_in_names(name):
    """<name>.d, the type-level <type>.d, and each dash-truncated prefix form the manager also reads."""
    stem,_,suffix=name.rpartition('.');parts=stem.split('-')
    return [name+'.d',suffix+'.d']+['-'.join(parts[:index])+'-.'+suffix+'.d' for index in range(1,len(parts))]

def conflict_scan(host,names,check):
    """lstat only, no content, no link text. In every lookup directory: a unit of the same name anywhere but the
    install directory, every drop-in directory form, the unit's own dependency directories, and the name inside every
    dependency directory. In the install directory also the leftover temporaries of this family. A directory that
    cannot be read is UNAVAILABLE, never an absence."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    findings=[];leftovers=[];directories={}
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
                listed.append(name);need(len(listed)<=MAX_SCAN_ENTRIES,'SCAN_LIMIT')
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
                    if info is not None:
                        leftovers.append({'name':entry,'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,
                                          'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'links':info.st_nlink,'device':info.st_dev,'inode':info.st_ino})
                if not entry.endswith(DEPENDENCY_SUFFIXES):continue
                info=present(entry,fd)
                if info is None:continue
                label=entry if text(entry,SCAN_ENTRY_NAME) else None
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
    for directory in SCAN_DIRECTORIES:directories[directory]=attempt(lambda directory=directory:one(directory))
    status=combined(directories.values())
    return {'status':'COMPLETE' if status=='COMPLETE' else 'UNAVAILABLE','directories':directories,
            'findings':findings[:MAX_FINDINGS],'findings_truncated':len(findings)>MAX_FINDINGS,
            'finding_codes':sorted({item['code'] for item in findings}),'leftovers':leftovers[:MAX_FINDINGS],
            'leftover_count':len(leftovers)}


# ---------------------------------------------------------------- the precheck
def producer_unit(host,directory,gate):
    """The installed producer unit, read by descriptor without following a link: regular, root:root 0644, one link,
    exactly the signed bytes; then its journal bind and image, which must be the reader's."""
    gate()
    try:named=host.lstat(PRODUCER_SERVICE_NAME,directory.fd)
    except FileNotFoundError:raise Refused('PRODUCER_UNIT_ABSENT') from None
    need(stat.S_ISREG(named.st_mode) and (named.st_uid,named.st_gid,stat.S_IMODE(named.st_mode),named.st_nlink)==(0,0,UNIT_MODE,1),
         'PRODUCER_UNIT_NOT_AS_SIGNED')
    raw,info=read_regular(host,PRODUCER_SERVICE_NAME,directory.fd,gate,MAX_UNIT_BYTES)
    need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino) and len(raw)==PRODUCER_BYTES and sha(raw)==PRODUCER_SHA256,'PRODUCER_UNIT_NOT_AS_SIGNED')
    facts=producer_facts(raw)
    need((facts['journal_source'],facts['journal_target'],facts['image_id'])
         ==(READER_VALUES['HOST_JOURNAL_ROOT'],READER_VALUES['CONTAINER_JOURNAL_ROOT'],READER_VALUES['IMAGE_ID']),'PRODUCER_VALUES_NOT_THE_READER_VALUES')
    findings=placement_findings(READER_VALUES,facts['other_sources'])
    need(not findings,findings[0] if findings else 'PLACEMENT_INVALID')
    return {'path':UNIT_DIRECTORY+'/'+PRODUCER_SERVICE_NAME,'sha256':PRODUCER_SHA256,'bytes':len(raw),'device':info.st_dev,'inode':info.st_ino,
            'journal_source':facts['journal_source'],'journal_target':facts['journal_target'],'image_id':facts['image_id'],
            'other_sources':facts['other_sources']}

def catalog_files(host,journal,gate):
    """The real catalogue is there (E1-19): epoch.json and maintenance.lock in the held journal root, each a regular
    file, root:root 0600, one link. lstat only: nothing of the catalogue is opened, read or locked here."""
    found={}
    for name in CATALOG_FILE_NAMES:
        gate()
        try:info=host.lstat(name,journal.fd)
        except FileNotFoundError:raise Refused('CATALOG_NOT_INITIALISED') from None
        found[name]={'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'links':info.st_nlink}
        need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,CATALOG_FILE_MODE,1),
             'CATALOG_FILE_NOT_PRIVATE')
    return found

def unit_table(units,host,directory,gate):
    """Per name: what exists there, by lstat; a regular file found there is read only to say whether it is the signed
    render. Its digest and size are reported ONLY when it is (a foreign unit may carry an inline secret)."""
    rows=[]
    for unit,content in units:
        name=unit['destination_name'];expect=unit['expect']
        row={'key':unit['key'],'destination_name':name,'expected':'ABSENT' if expect=='ABSENT' else 'PRESENT'}
        rows.append(row);gate()
        try:named=host.lstat(name,directory.fd)
        except FileNotFoundError:named=None
        if named is None:
            row['observed']='ABSENT';row['state']='OK_ABSENT' if expect=='ABSENT' else 'EXPECTED_PRESENT_ABSENT';continue
        row.update(observed='PRESENT',type=kind(named.st_mode),uid=named.st_uid,gid=named.st_gid,mode_octal='%04o'%stat.S_IMODE(named.st_mode),
                   links=named.st_nlink,device=named.st_dev,inode=named.st_ino);equal=None
        if stat.S_ISREG(named.st_mode):
            try:
                raw,info=read_regular(host,name,directory.fd,gate,MAX_UNIT_BYTES)
                equal=raw==content and (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino)
            except Refused as error:row['read_code']=code_of(error,'FILE_UNREADABLE')
            row['bytes_equal_signed_render']=equal
            if equal:row.update(sha256=sha(raw),size=len(raw))
        conforms=bool(equal and named.st_uid==0 and named.st_gid==0 and stat.S_IMODE(named.st_mode)==UNIT_MODE)
        if not stat.S_ISREG(named.st_mode):row['state']='OCCUPIED_NOT_REGULAR'
        elif expect=='ABSENT':row['state']='PRESENT_EQUAL_NOT_SIGNED' if conforms and named.st_nlink in (1,2) else 'PRESENT_FOREIGN'
        elif conforms and (named.st_dev,named.st_ino,named.st_nlink)==(expect['device'],expect['inode'],expect['links']):row['state']='OK_PRESENT'
        else:row['state']='PRESENT_IDENTITY_MISMATCH'
    return rows

def precedence(rows,scan,signed,own):
    """The refusal of the unit table and of the scan, in a fixed order, or None. None of these says that an installation
    happened: they say what exists."""
    states={row['state'] for row in rows};seen={item['name']:(item['device'],item['inode']) for item in scan['leftovers']}
    if 'OCCUPIED_NOT_REGULAR' in states:return 'UNIT_NAME_OCCUPIED'
    if 'PRESENT_FOREIGN' in states:return 'UNIT_PRESENT_FOREIGN_CONTENT'
    if states&{'EXPECTED_PRESENT_ABSENT','PRESENT_IDENTITY_MISMATCH'} or set(signed)-set(seen):return 'EXPECTATION_MISMATCH'
    if 'PRESENT_EQUAL_NOT_SIGNED' in states:
        # "All present" is said only of one-link files with no unacknowledged temporary beside them; a name that still
        # shares its inode with a temporary is the state an interrupted run leaves.
        settled=all(row['observed']=='PRESENT' for row in rows) and all(row['links']==1 for row in rows) and not scan['leftovers_not_acknowledged'] \
            and scan['leftover_count']<=MAX_FINDINGS
        return 'ALL_UNITS_PRESENT' if settled else 'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'
    if scan['leftover_count']>MAX_FINDINGS or scan['leftovers_not_acknowledged']:
        return 'TEMPORARY_NAME_OCCUPIED' if own&set(scan['leftovers_not_acknowledged']) else 'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'
    for code in ('DROP_IN_PRESENT','OWN_DEPENDENCY_DIRECTORY_PRESENT','ENABLEMENT_LINK_PRESENT','UNIT_SHADOWED_IN_OTHER_PATH'):
        if code in scan['finding_codes']:return code
    if scan['status']!='COMPLETE':return 'CONFLICT_SCAN_UNAVAILABLE'
    return None


def _reduce_scan(receipt):
    scan=((receipt.get('precheck') or {}).get('conflicts'))
    if type(scan) is dict:scan['directories']={name:item.get('status') for name,item in scan.get('directories',{}).items()}
def _reduce_precheck(receipt):
    table=receipt.get('precheck') or {}
    receipt['precheck']={'units':[{'key':row.get('key'),'state':row.get('state')} for row in table.get('units',[])],
                         'finding_codes':(table.get('conflicts') or {}).get('finding_codes')}
REDUCTIONS=[('SCAN_DIRECTORIES_REDUCED_TO_STATUS',_reduce_scan),('PRECHECK_REDUCED_TO_STATES',_reduce_precheck)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    units=units_of(plan)                                      # pure: the bytes that will be written, and no others
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    detail={'unit_directory':[],'journal':[],'data_volume':[],'producer':None,'catalog':None,'precheck':None};ledger=[];held=[];directory=None
    go16=bound['go_sha256'][:16]
    def finish(status,outcome,code,extra):
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),mutating_calls=state.counts(),unit_directory=detail['unit_directory'],
            journal=detail['journal'],data_volume=detail['data_volume'],producer=detail['producer'],catalog=detail['catalog'],precheck=detail['precheck'],
            ledger=ledger,objects_left_by_this_run=objects_left([],ledger),external_processes=0,daemon_reload_owner=DAEMON_RELOAD_OWNER,
            pre_existing_objects_modified=False,**extra)))
    try:
        # ---- everything is looked at before the first creation
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o022)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            directory=Pinned(host,walk_pinned(host,plan['unit_rows'],gate,detail['unit_directory']),rows=plan['unit_rows']);held.append(directory)
            detail['producer']=producer_unit(host,directory,gate)
            journal=Pinned(host,walk_pinned(host,plan['journal_rows'],gate,detail['journal']),rows=plan['journal_rows']);held.append(journal)
            detail['catalog']=catalog_files(host,journal,gate)
            # Each walk compares the device of every component with its signed row, and validate_plan refused rows that
            # put the journal on the data volume's device: what is held here is two filesystems.
            held.append(Pinned(host,walk_pinned(host,plan['data_rows'],gate,detail['data_volume']),rows=plan['data_rows']))
            rows=unit_table(units,host,directory,gate)
            scan=conflict_scan(host,[name for _,name in UNIT_ORDER],gate)
            signed={item['name']:(item['device'],item['inode']) for item in plan['acknowledged_leftovers']}
            seen={item['name']:(item['device'],item['inode']) for item in scan['leftovers']}
            scan['leftovers_acknowledged']=sorted(name for name in seen if signed.get(name)==seen[name])
            scan['leftovers_not_acknowledged']=sorted(name for name in seen if signed.get(name)!=seen[name])
            own={TEMPORARY%(go16,index) for index,(unit,_) in enumerate(units) if unit['expect']=='ABSENT'}
            detail['precheck']={'units':rows,'conflicts':scan}
            code=precedence(rows,scan,signed,own)
            if code is None:
                # The last refusal that costs nothing on the host: the time the creations and the readback may take.
                left=gate();detail['precheck']['seconds_left_before_first_effect']=int(left)
                need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK','readback':None})
        # ---- from here on nothing refuses unless nothing has changed
        stop=None
        for index,(unit,content) in enumerate(units):
            path=UNIT_DIRECTORY+'/'+unit['destination_name']
            if unit['expect']!='ABSENT' or stop is not None:
                ledger.append({'key':unit['key'],'path':path,'code':None,'sha256_signed':sha(content),'sha256_observed':None,
                               'state':'NOT_ATTEMPTED' if unit['expect']=='ABSENT' else 'PRESENT_VERIFIED_NOT_TOUCHED'});continue
            row=create_file(index,unit['key'],path,content,UNIT_MODE,directory,host,gate,state,go16);ledger.append(row)
            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'
        # ---- the readback inside the run: every name through the held directory, then the directory from "/"
        if stop is None:
            for (unit,content),row in zip(units,ledger):
                if stop is not None:break
                if row['state']=='INSTALLED_DURABLE':
                    stop=readback_file(row,content,UNIT_MODE,directory,host,gate);continue
                try:
                    raw,info=read_regular(host,unit['destination_name'],directory.fd,gate,MAX_UNIT_BYTES)
                    row['sha256_observed']=sha(raw);expect=unit['expect']
                    need(raw==content and (info.st_dev,info.st_ino,info.st_nlink)==(expect['device'],expect['inode'],expect['links'])
                         and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,UNIT_MODE),'READBACK_HASH_MISMATCH')
                except Exception as error:stop=code_of(error,'READBACK_UNAVAILABLE')
        if stop is None:
            try:directory.verify(gate)
            except Exception as error:stop=code_of(error,'READBACK_UNAVAILABLE')
        extra={'phase_reached':'CREATION','readback':'COMPLETE' if stop is None else None}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for handle in held:
            try:handle.close()
            except Exception:pass
