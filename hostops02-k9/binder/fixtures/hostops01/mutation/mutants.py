"""The mutants. Each row: (name, target part, exact anchor, replacement). The anchor must occur exactly once in every
file the part is assembled into. Names beginning with A_ are the 24 survivors of the installer audit, mapped to this
code (the audit's id follows); the others are the guarantees this family adds. COMBOS remove one guarantee at every
layer that carries it at once."""

M=[]
def add(name,target,old,new):M.append((name,target,old,new))

# ---------------------------------------------------------------- the 24 survivors of the installer audit
CREATE="flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC\n"
add('A_M01_create_without_excl','op_install_units',CREATE,"flags=os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC\n")
add('A_M04_create_without_nofollow','op_install_units',CREATE,"flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC\n")
add('A_M05_create_without_excl_and_nofollow','op_install_units',CREATE,"flags=os.O_WRONLY|os.O_CREAT|os.O_CLOEXEC\n")
add('A_M06_file_fsync_dropped','op_install_units',"        try:host.fsync(fd);entry['fsync_file']=True\n","        try:entry['fsync_file']=True\n")
add('A_M07a_directory_fsync_after_mkdir_dropped','op_provision',"        host.fsync(fd);entry['fsync_directory']=True\n","        entry['fsync_directory']=True\n")
add('A_M07b_parent_fsync_after_mkdir_dropped','op_provision',"        host.fsync(parent.fd);entry['fsync_parent']=True\n","        entry['fsync_parent']=True\n")
add('A_M07c_directory_fsync_after_link_dropped','op_install_units',"        try:host.fsync(directory.fd);entry['fsync_directory_after_link']=True\n","        try:entry['fsync_directory_after_link']=True\n")
add('A_M07d_directory_fsync_after_removal_dropped','op_install_units',"    try:host.fsync(directory.fd);entry['fsync_directory_after_removal']=True\n","    try:entry['fsync_directory_after_removal']=True\n")
WALK="""    Observed rows are appended as they are read, so a refusal carries what was seen. Returns the last descriptor.\"\"\"
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
"""
add('A_M08_chain_walk_without_nofollow','core',WALK,WALK.replace('|os.O_NOFOLLOW',''))
add('A_M10a_parent_not_verified_before_mkdir','op_provision',"    try:parent.verify(gate)\n    except Refused as error:\n        entry['code']=code_of(error,'PARENT_REPLACED');return entry\n","")
add('A_M10b_directory_not_verified_before_temporary','op_install_units',"    try:directory.verify(gate)\n    except Refused as error:return failed(code_of(error,'PARENT_REPLACED'))\n    flags=","    flags=")
add('A_M10c_directory_not_verified_before_link','op_install_units',"        try:directory.verify(gate)\n        except Refused as error:return failed(code_of(error,'PARENT_REPLACED'))\n        # link() acts on the name,","        # link() acts on the name,")
add('A_M11_excl_replaced_by_trunc','op_install_units',CREATE,"flags=os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW|os.O_CLOEXEC\n")
ROWS="    fields=('device','inode','uid','gid','mode') if compare_device else ('inode','uid','gid','mode')\n"
for field in ('device','inode','uid','gid','mode'):
    add('A_M14_chain_row_%s_not_compared'%field,'core',ROWS,ROWS.replace("('device','inode','uid','gid','mode') if","(%s) if"%','.join(repr(name) for name in ('device','inode','uid','gid','mode') if name!=field)))
STARTED="    state.started=True\n    detail={'unit_directory':[],'precheck':None}"
for label,call in (('os_system',"os.system('/usr/bin/true')"),('os_spawnv',"os.spawnv(os.P_WAIT,'/usr/bin/true',['true'])"),
                   ('os_posix_spawn',"os.waitpid(os.posix_spawn('/usr/bin/true',['true'],{}),0)"),
                   ('os_fork',"(os.fork() or os._exit(0))"),('subprocess_run',"__import__('subprocess').run(['/usr/bin/true'])")):
    add('A_M15_install_starts_a_process_'+label,'op_install_units',STARTED,"    state.started=True;"+call+"\n    detail={'unit_directory':[],'precheck':None}")
add('A_M17a_fchmod_of_the_unit_directory','op_install_units',"        if code is not None:\n            return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})\n        stop=None\n        for index,(unit,content)",
    "        if code is not None:\n            return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})\n        os.fchmod(directory.fd,0o755);stop=None\n        for index,(unit,content)")
add('A_M17b_fchmod_of_a_created_file','op_install_units',"        try:host.fsync(fd);entry['fsync_file']=True\n","        try:os.fchmod(fd,0o644);host.fsync(fd);entry['fsync_file']=True\n")
add('A_M17c_fchown_of_a_created_file','op_install_units',"        entry['bytes']=written\n","        entry['bytes']=written;os.fchown(fd,os.geteuid(),os.getegid())\n")
add('A_M17d_fchmod_of_a_created_directory','op_provision',"    entry['state']='CREATED_UNVERIFIED'\n    try:fd=host.open(name,flags,dir_fd=parent.fd)\n","    entry['state']='CREATED_UNVERIFIED'\n    try:fd=host.open(name,flags,dir_fd=parent.fd);os.fchmod(fd,0o700)\n")
add('A_M17e_fchmod_of_a_parent','op_provision',"    try:mutate(state,gate,lambda:host.mkdir(name,DIRECTORY_MODE,parent.fd))\n","    try:os.fchmod(parent.fd,0o755);mutate(state,gate,lambda:host.mkdir(name,DIRECTORY_MODE,parent.fd))\n")
READER="    state.started=True\n    reader=Reader(plan,host,gate);items={}\n"
for label,call in (('os_open_creat',"os.close(os.open('hostops-mutant-marker',os.O_WRONLY|os.O_CREAT,0o600))"),('os_mkdir',"os.makedirs('hostops-mutant-directory',exist_ok=True)"),
                   ('builtin_open',"open('hostops-mutant-marker','w').close()"),('os_utime',"os.utime('.')"),
                   ('link_and_unlink',"os.close(os.open('hostops-mutant-a',os.O_WRONLY|os.O_CREAT,0o600));os.link('hostops-mutant-a','hostops-mutant-b-%d'%time.monotonic_ns());os.unlink('hostops-mutant-a')"),
                   ('os_rename',"os.close(os.open('hostops-mutant-c',os.O_WRONLY|os.O_CREAT,0o600));os.rename('hostops-mutant-c','hostops-mutant-d')")):
    add('A_M21_readback_writes_'+label,'op_readback',READER,"    state.started=True;"+call+"\n    reader=Reader(plan,host,gate);items={}\n")
add('A_A_path_grammar_widened','render',"VALUE_PATH='/[A-Za-z0-9_./-]+'\n","VALUE_PATH='/.+'\n")
COMPONENT="    need(all(part not in ('','.','..') for part in parts),'PATH_COMPONENT')\n"
add('A_B_component_check_removed','render',COMPONENT,"")
add('A_C_image_id_accepts_anything','render',"    need(type(values['IMAGE_ID']) is str and re.fullmatch(IMAGE_ID,values['IMAGE_ID']) is not None,'IMAGE_ID')\n","    need(type(values['IMAGE_ID']) is str,'IMAGE_ID')\n")
add('A_C2_image_id_match_not_fullmatch','render',"re.fullmatch(IMAGE_ID,values['IMAGE_ID']) is not None,'IMAGE_ID')","re.match(IMAGE_ID,values['IMAGE_ID']) is not None,'IMAGE_ID')")
add('A_D_network_pattern_and_ban_removed','render',"        need(re.fullmatch(NETWORK,name) is not None and name not in FORBIDDEN_NETWORKS,'NETWORK_FORBIDDEN')\n","        pass\n")
add('A_E_allowlist_membership_removed','render',"    need(type(values['NETWORK']) is str and values['NETWORK'] in network_allowlist,'NETWORK_NOT_AUTHORIZED')\n","    need(type(values['NETWORK']) is str,'NETWORK_NOT_AUTHORIZED')\n")
add('A_I_surviving_at_sign_check_removed','render',"    for key in OCCURRENCES:unit=unit.replace('@'+key+'@',values[key])\n    need('@' not in unit,'UNRESOLVED_PLACEHOLDER')\n","    for key in OCCURRENCES:unit=unit.replace('@'+key+'@',values[key])\n")
add('A_J_placeholder_count_check_removed','render',"    need(set(tokens)==set(OCCURRENCES) and all(tokens.count(key)==count for key,count in OCCURRENCES.items()),'PLACEHOLDER_COUNTS')\n","")
add('A_K_substitution_key_set_check_removed','render',"    need(type(values) is dict and set(values)==set(OCCURRENCES),'SUBSTITUTION_KEYS')\n","    need(type(values) is dict,'SUBSTITUTION_KEYS')\n")

# ---------------------------------------------------------------- rendering, beyond the audit's list
add('R01_path_and_component_both','render',"VALUE_PATH='/[A-Za-z0-9_./-]+'\n","VALUE_PATH='/[^@]+'\n")
add('R04_path_length_limit_removed','render',"    need(len(value)<=MAX_PATH_LENGTH,'PATH_TOO_LONG')\n","")
add('R05_component_length_limit_removed','render',"    need(all(len(part)<=MAX_COMPONENT_LENGTH for part in parts),'PATH_TOO_LONG')\n","")
add('R06_frozen_template_hash_not_pinned','render',"    if profile in FROZEN_TEMPLATES:need(sha(template)==FROZEN_TEMPLATES[profile],'FROZEN_TEMPLATE_HASH')\n","")
add('R07_supervisor_name_not_bound_to_its_profile','render',"    need(REQUIRED_PROFILE.get(name,profile)==profile and (profile not in FROZEN_TEMPLATES or REQUIRED_PROFILE.get(name)==profile),\n         'PROFILE_NAME_MISMATCH')\n","")
add('R08_frozen_profile_usable_for_other_names','render',"need(REQUIRED_PROFILE.get(name,profile)==profile and (profile not in FROZEN_TEMPLATES or REQUIRED_PROFILE.get(name)==profile),","need(REQUIRED_PROFILE.get(name,profile)==profile,")
add('R09_other_profile_usable_for_supervisor_names','render',"need(REQUIRED_PROFILE.get(name,profile)==profile and (profile not in FROZEN_TEMPLATES or REQUIRED_PROFILE.get(name)==profile),","need((profile not in FROZEN_TEMPLATES or REQUIRED_PROFILE.get(name)==profile),")
add('R10_rendered_hash_not_compared','render',"    need(hexpin(unit['rendered_sha256']) and sha(rendered)==unit['rendered_sha256'],'RENDERED_HASH_MISMATCH')\n","")
add('R11_rendered_size_not_compared','render',"    need(type(unit['rendered_bytes']) is int and len(rendered)==unit['rendered_bytes'],'RENDERED_SIZE_MISMATCH')\n","")
add('R12_template_hash_not_compared','render',"    need(hexpin(unit['template_sha256']) and sha(raw)==unit['template_sha256'],'TEMPLATE_HASH_MISMATCH')\n","")
add('R13_second_base64_encoding_accepted','render',"    need(base64.b64encode(raw).decode('ascii')==value,'TEMPLATE_ENCODING')\n","")
add('R14_template_size_limit_removed','render',"    need(0<len(raw)<=MAX_TEMPLATE_BYTES,'TEMPLATE_TOO_LARGE')\n","    need(0<len(raw),'TEMPLATE_TOO_LARGE')\n")
add('R15_non_ascii_template_accepted','render',"    need(re.fullmatch(rb'[\\t\\n -~]*',raw) is not None,'TEMPLATE_NOT_ASCII')\n","")
add('R16_render_size_limit_removed','render',"    need(len(rendered)<=MAX_RENDER_BYTES,'RENDER_TOO_LARGE')\n","")
add('R17_generic_surviving_at_sign','render',"    for name in sorted(placeholders):unit=unit.replace('@'+name+'@',placeholders[name]['value'])\n    need('@' not in unit,'UNRESOLVED_PLACEHOLDER')\n","    for name in sorted(placeholders):unit=unit.replace('@'+name+'@',placeholders[name]['value'])\n")
add('R18_generic_counts_not_checked','render',"    need(set(tokens)==set(placeholders) and all(tokens.count(name)==item['occurrences'] for name,item in placeholders.items()),\n         'PLACEHOLDER_COUNTS')\n","")
add('R19_generic_network_not_in_allowlist','render',"        else:need(type(item['value']) is str and item['value'] in network_allowlist,'NETWORK_NOT_AUTHORIZED')\n","        else:need(type(item['value']) is str,'NETWORK_NOT_AUTHORIZED')\n")
add('R20_verbatim_with_placeholder','render',"        need(b'@' not in template,'TIMER_PLACEHOLDER' if profile==TIMER_PROFILE else 'UNRESOLVED_PLACEHOLDER')\n","")
add('R21_extraction_without_back_reference','render',"        elif part in seen:out.append('(?P=%s)'%part)\n","        elif part in seen:out.append(VALUE_PATTERNS[part])\n")
add('R22_extraction_matches_a_prefix','render',"    match=re.fullmatch(''.join(out),candidate)\n","    match=re.match(''.join(out),candidate)\n")
add('R23_allowlist_shape_unchecked','render',"    need(type(network_allowlist) is list and 0<len(network_allowlist)<=16\n         and all(type(name) is str for name in network_allowlist)\n         and len(set(network_allowlist))==len(network_allowlist),'NETWORK_ALLOWLIST')\n","    need(type(network_allowlist) is list and all(type(name) is str for name in network_allowlist),'NETWORK_ALLOWLIST')\n")

# ---------------------------------------------------------------- core: documents and authority
add('C01_pin_not_compared_with_bytes','core',"        need(hexpin(pin) and type(data) is bytes and sha(data)==pin,'PIN_MISMATCH')\n","        need(hexpin(pin) and type(data) is bytes,'PIN_MISMATCH')\n")
add('C02_non_canonical_document_accepted','core',"    value=decode(raw);need(canonical(value)==raw,'DOCUMENT_NOT_CANONICAL');return value\n","    value=decode(raw);return value\n")
add('C03_duplicate_key_accepted','core',"            need(key not in result,'DUPLICATE_KEY');result[key]=value\n","            result[key]=value\n")
KEYS="    exact(request,REQUEST_KEYS,'REQUEST_KEYS');exact(authority,AUTHORITY_KEYS,'AUTHORITY_KEYS');exact(go,GO_KEYS,'GO_KEYS')\n"
add('C04_request_keys_not_exact','core',KEYS,"    exact(authority,AUTHORITY_KEYS,'AUTHORITY_KEYS');exact(go,GO_KEYS,'GO_KEYS')\n")
add('C05_authority_keys_not_exact','core',KEYS,"    exact(request,REQUEST_KEYS,'REQUEST_KEYS');exact(go,GO_KEYS,'GO_KEYS')\n")
add('C06_go_keys_not_exact','core',KEYS,"    exact(request,REQUEST_KEYS,'REQUEST_KEYS');exact(authority,AUTHORITY_KEYS,'AUTHORITY_KEYS')\n")
add('C07_extra_key_accepted','core',"    need(type(value) is dict and set(value)==set(keys),code);return value\n","    need(type(value) is dict and set(value)>=set(keys),code);return value\n")
add('C08_request_schema_dropped','core',"    need(request['schema']==REQUEST_SCHEMA and request['status']=='BOUND'\n","    need(request['status']=='BOUND'\n")
add('C09_request_status_dropped','core',"    need(request['schema']==REQUEST_SCHEMA and request['status']=='BOUND'\n","    need(request['schema']==REQUEST_SCHEMA\n")
add('C10_request_operation_dropped','core',"         and request['operation']==OPERATION and request['phase']==PHASE\n","         and request['phase']==PHASE\n")
add('C11_request_phase_dropped','core',"         and request['operation']==OPERATION and request['phase']==PHASE\n","         and request['operation']==OPERATION\n")
add('C12_request_scope_hash_dropped','core',"         and request['scope_sha256']==SCOPE_SHA256 and request['payload_sha256']==pins.payload\n","         and request['payload_sha256']==pins.payload\n")
add('C13_request_payload_hash_dropped','core',"         and request['scope_sha256']==SCOPE_SHA256 and request['payload_sha256']==pins.payload\n","         and request['scope_sha256']==SCOPE_SHA256\n")
UID="         and type(request['executor_uid']) is int and request['executor_uid']==0 and executor_uid()==0,'REQUEST_OR_EXECUTOR_UNBOUND')\n"
add('C14_effective_uid_not_checked','core',UID,"         and type(request['executor_uid']) is int and request['executor_uid']==0,'REQUEST_OR_EXECUTOR_UNBOUND')\n")
add('C15_declared_uid_not_checked','core',UID,"         and executor_uid()==0,'REQUEST_OR_EXECUTOR_UNBOUND')\n")
add('C16_declared_uid_type_not_checked','core',UID,"         and request['executor_uid']==0 and executor_uid()==0,'REQUEST_OR_EXECUTOR_UNBOUND')\n")
SCOPE="    need(type(request['max_seconds']) is int and request['max_seconds']==MAX_SECONDS and request['writes_allowed'] is WRITES_ALLOWED\n         and request['activation_allowed'] is False,'REQUEST_SCOPE')\n"
add('C17_request_max_seconds_dropped','core',SCOPE,"    need(request['writes_allowed'] is WRITES_ALLOWED\n         and request['activation_allowed'] is False,'REQUEST_SCOPE')\n")
add('C18_request_writes_flag_dropped','core',SCOPE,"    need(type(request['max_seconds']) is int and request['max_seconds']==MAX_SECONDS\n         and request['activation_allowed'] is False,'REQUEST_SCOPE')\n")
add('C19_request_activation_flag_dropped','core',SCOPE,"    need(type(request['max_seconds']) is int and request['max_seconds']==MAX_SECONDS and request['writes_allowed'] is WRITES_ALLOWED,'REQUEST_SCOPE')\n")
A1="    need(authority['schema']==AUTHORITY_SCHEMA and authority['operation']==OPERATION and authority['phase']==PHASE\n"
add('C20_authority_schema_dropped','core',A1,"    need(authority['operation']==OPERATION and authority['phase']==PHASE\n")
add('C21_authority_operation_dropped','core',A1,"    need(authority['schema']==AUTHORITY_SCHEMA and authority['phase']==PHASE\n")
add('C22_authority_phase_dropped','core',A1,"    need(authority['schema']==AUTHORITY_SCHEMA and authority['operation']==OPERATION\n")
A2="         and authority['status']=='SIGNED' and authority['decision']=='APPROVED' and authority['execution_authorized'] is True\n"
add('C23_authority_status_dropped','core',A2,"         and authority['decision']=='APPROVED' and authority['execution_authorized'] is True\n")
add('C24_authority_decision_dropped','core',A2,"         and authority['status']=='SIGNED' and authority['execution_authorized'] is True\n")
add('C25_authority_execution_flag_dropped','core',A2,"         and authority['status']=='SIGNED' and authority['decision']=='APPROVED'\n")
A3="         and authority['request_sha256']==pins.request and authority['payload_sha256']==pins.payload\n"
add('C26_authority_request_hash_dropped','core',A3,"         and authority['payload_sha256']==pins.payload\n")
add('C27_authority_payload_hash_dropped','core',A3,"         and authority['request_sha256']==pins.request\n")
A4="         and authority['writes_allowed'] is WRITES_ALLOWED and authority['activation_allowed'] is False\n"
add('C28_authority_writes_flag_dropped','core',A4,"         and authority['activation_allowed'] is False\n")
add('C29_authority_activation_flag_dropped','core',A4,"         and authority['writes_allowed'] is WRITES_ALLOWED\n")
OWNER_EVIDENCE="         and type(authority['owner_evidence']) is str and 0<len(authority['owner_evidence'])<=512\n         and authority['owner_evidence']!='UNBOUND','AUTHORITY_UNBOUND')\n"
add('C30_owner_evidence_dropped','core',OWNER_EVIDENCE,"         ,'AUTHORITY_UNBOUND')\n")
add('C30b_owner_evidence_may_be_the_word_unbound','core',OWNER_EVIDENCE,"         and type(authority['owner_evidence']) is str and 0<len(authority['owner_evidence'])<=512,'AUTHORITY_UNBOUND')\n")
add('C30c_owner_evidence_length_cap_dropped','core',OWNER_EVIDENCE,"         and type(authority['owner_evidence']) is str and 0<len(authority['owner_evidence'])\n         and authority['owner_evidence']!='UNBOUND','AUTHORITY_UNBOUND')\n")
G1="    need(go['schema']==GO_SCHEMA and go['status']=='SIGNED' and go['action']=='GO' and go['phase']==PHASE\n"
add('C31_go_schema_dropped','core',G1,"    need(go['status']=='SIGNED' and go['action']=='GO' and go['phase']==PHASE\n")
add('C32_go_status_dropped','core',G1,"    need(go['schema']==GO_SCHEMA and go['action']=='GO' and go['phase']==PHASE\n")
add('C33_go_action_dropped','core',G1,"    need(go['schema']==GO_SCHEMA and go['status']=='SIGNED' and go['phase']==PHASE\n")
add('C34_go_phase_dropped','core',G1,"    need(go['schema']==GO_SCHEMA and go['status']=='SIGNED' and go['action']=='GO'\n")
G2="         and go['operation']==OPERATION and go['execution_authorized'] is True\n"
add('C35_go_operation_dropped','core',G2,"         and go['execution_authorized'] is True\n")
add('C36_go_execution_flag_dropped','core',G2,"         and go['operation']==OPERATION\n")
G3="         and go['writes_allowed'] is WRITES_ALLOWED and go['activation_allowed'] is False\n"
add('C37_go_writes_flag_dropped','core',G3,"         and go['activation_allowed'] is False\n")
add('C38_go_activation_flag_dropped','core',G3,"         and go['writes_allowed'] is WRITES_ALLOWED\n")
G4="         and go['request_sha256']==pins.request and go['authority_sha256']==pins.authority\n"
add('C39_go_request_hash_dropped','core',G4,"         and go['authority_sha256']==pins.authority\n")
add('C40_go_authority_hash_dropped','core',G4,"         and go['request_sha256']==pins.request\n")
add('C41_go_payload_hash_dropped','core',"         and go['payload_sha256']==pins.payload,'GO_UNBOUND')\n","         ,'GO_UNBOUND')\n")
O1="    need(type(go['owner']) is str and go['owner'] not in ('','UNBOUND') and len(go['owner'])<=128\n         and go['owner']==authority['owner'],'OWNER_UNBOUND')\n"
add('C42_unbound_owner_accepted','core',O1,"    need(type(go['owner']) is str and len(go['owner'])<=128\n         and go['owner']==authority['owner'],'OWNER_UNBOUND')\n")
add('C43_owner_equality_dropped','core',O1,"    need(type(go['owner']) is str and go['owner'] not in ('','UNBOUND') and len(go['owner'])<=128,'OWNER_UNBOUND')\n")
H1="    need(hexpin(host) and host==authority['host_binding_sha256']==go['host_binding_sha256'],'HOST_BINDING')\n"
add('C44_null_host_binding_accepted','core',H1,"    need(host==authority['host_binding_sha256']==go['host_binding_sha256'],'HOST_BINDING')\n")
add('C45_host_binding_authority_dropped','core',H1,"    need(hexpin(host) and host==go['host_binding_sha256'],'HOST_BINDING')\n")
add('C46_host_binding_go_dropped','core',H1,"    need(hexpin(host) and host==authority['host_binding_sha256'],'HOST_BINDING')\n")
add('C46b_host_binding_equalities_dropped','core',H1,"    need(hexpin(host),'HOST_BINDING')\n")
T1="         and type(binding['target']) is str and binding['target'] and hexpin(binding['command_sha256'])\n"
add('C47_null_transport_target_accepted','core',T1,"         and hexpin(binding['command_sha256'])\n")
add('C48_null_command_pin_accepted','core',T1,"         and type(binding['target']) is str and binding['target']\n")
T2="         and binding['remote_command']==REMOTE_COMMAND and type(binding['runtime_sha256']) is dict\n         and binding['runtime_sha256'].get(SOURCE_NAME)==pins.payload,'GO_TRANSPORT_UNBOUND')\n"
add('C49_remote_command_not_pinned','core',T2,"         and type(binding['runtime_sha256']) is dict\n         and binding['runtime_sha256'].get(SOURCE_NAME)==pins.payload,'GO_TRANSPORT_UNBOUND')\n")
add('C50_runtime_pin_of_the_source_not_tied_to_the_payload','core',T2,"         and binding['remote_command']==REMOTE_COMMAND and type(binding['runtime_sha256']) is dict,'GO_TRANSPORT_UNBOUND')\n")
add('C51_null_claim_root_accepted','core',"    need(type(root) is dict and set(root)=={'path','device','inode'} and type(root['path']) is str and root['path'].startswith('/')\n         and integer(root['device']) and integer(root['inode'],1),'GO_CLAIM_ROOT_UNBOUND')\n","    need(type(root) is dict and set(root)=={'path','device','inode'},'GO_CLAIM_ROOT_UNBOUND')\n")
add('C52_date_set_dropped','core',"    need(type(request['date']) is str and request['date'] in DATES,'DATE_NOT_IN_SCOPE')\n","    need(type(request['date']) is str,'DATE_NOT_IN_SCOPE')\n")
add('C53_request_date_not_tied_to_the_windows','core',"    need(all(point.date().isoformat()==request['date'] for point in starts+ends),'DATE_WINDOW_MISMATCH')\n","")
SPAN="    need(start<end and (end-start).total_seconds()<=MAX_GATE_SPAN_SECONDS,'WINDOW_SPAN')\n"
add('C54_window_span_cap_dropped','core',SPAN,"    need(start<end,'WINDOW_SPAN')\n")
add('C55_empty_window_accepted','core',SPAN,"    need((end-start).total_seconds()<=MAX_GATE_SPAN_SECONDS,'WINDOW_SPAN')\n")
add('C56_gate_uses_first_window_only','core',"    start,end=max(starts),min(ends)\n","    start,end=starts[0],ends[0]\n")
add('C57_non_utc_offset_accepted','core',"    need(point.tzinfo is not None and offset is not None and offset.total_seconds()==0,'WINDOW_NOT_UTC')\n","    need(point.tzinfo is not None and offset is not None,'WINDOW_NOT_UTC')\n")
add('C58_gate_initial_window_dropped','core',"        need(start<=self.wall<end,'OUTSIDE_GO_WINDOW')\n","")
GATE="        need(self.start<=wall<self.end and mono<self.deadline,'GO_EXPIRED')\n"
add('C59_gate_wall_window_dropped','core',GATE,"        need(mono<self.deadline,'GO_EXPIRED')\n")
add('C60_gate_monotonic_deadline_dropped','core',GATE,"        need(self.start<=wall<self.end,'GO_EXPIRED')\n")
REV="        need(wall>=self.wall and mono>=self.mono,'CLOCK_REVERSED')\n"
add('C61_wall_clock_reversal_accepted','core',REV,"        need(mono>=self.mono,'CLOCK_REVERSED')\n")
add('C62_monotonic_reversal_accepted','core',REV,"        need(wall>=self.wall,'CLOCK_REVERSED')\n")
add('C63_plan_host_binding_dropped','core',"    need(type(plan) is dict and plan.get('host_binding_sha256')==host,'PLAN_BINDING')\n","    need(type(plan) is dict,'PLAN_BINDING')\n")
add('C64_plan_keys_not_exact','core',"    exact(plan,PLAN_COMMON_KEYS|PLAN_KEYS,'PLAN_KEYS')\n","    need(type(plan) is dict,'PLAN_KEYS')\n")
PLAN="    need(plan['schema']==PLAN_SCHEMA and plan['status']=='BOUND','PLAN_UNBOUND')\n"
add('C65_plan_schema_dropped','core',PLAN,"    need(plan['status']=='BOUND','PLAN_UNBOUND')\n")
add('C66_plan_status_dropped','core',PLAN,"    need(plan['schema']==PLAN_SCHEMA,'PLAN_UNBOUND')\n")
add('C67_plan_phase_dropped','core',"    need(plan['phase']==PHASE,'PHASE_INVALID')\n","")
add('C68_plan_limits_dropped','core',"    need(type(plan['max_seconds']) is int and plan['max_seconds']==MAX_SECONDS,'LIMITS_INVALID')\n","")
add('C69_scope_not_compared','core',"    need(type(plan['scope']) is dict and canonical(plan['scope'])==canonical(SCOPE),'SCOPE_MISMATCH')\n","    need(type(plan['scope']) is dict,'SCOPE_MISMATCH')\n")
add('C70_plan_window_not_tied_to_the_request','core',"    need(instant(plan['window']['not_before'])==starts[0] and instant(plan['window']['expires_at'])==ends[0],'PLAN_WINDOW')\n","")
EVID="    need(type(evidence) is list and len(evidence)<=16 and (evidence or not EVIDENCE_REQUIRED),'EVIDENCE_UNBOUND')\n"
add('C71_empty_evidence_accepted','core',EVID,"    need(type(evidence) is list and len(evidence)<=16,'EVIDENCE_UNBOUND')\n")
add('C72_evidence_receipt_hash_not_checked','core',"             and text(item['operation'],'[A-Z][A-Z0-9_]{0,79}') and hexpin(item['receipt_sha256']),'EVIDENCE_UNBOUND')\n","             and text(item['operation'],'[A-Z][A-Z0-9_]{0,79}'),'EVIDENCE_UNBOUND')\n")
EFF="         and canonical(authority['effects'])==effects==canonical(go['effects']),'EFFECTS_BINDING')\n"
add('C73_effects_in_the_authority_not_compared','core',EFF,"         and effects==canonical(go['effects']),'EFFECTS_BINDING')\n")
add('C74_effects_in_the_go_not_compared','core',EFF,"         and canonical(authority['effects'])==effects,'EFFECTS_BINDING')\n")
add('C74b_effects_not_compared_at_all','core',EFF,"         ,'EFFECTS_BINDING')\n")
CRIT="    need(go['scope_statement']==SCOPE_STATEMENT and go['success_criterion']==success_of(plan),'GO_CRITERION')\n"
add('C75_scope_statement_free_text','core',CRIT,"    need(go['success_criterion']==success_of(plan),'GO_CRITERION')\n")
add('C76_success_criterion_free_text','core',CRIT,"    need(go['scope_statement']==SCOPE_STATEMENT,'GO_CRITERION')\n")

# ---------------------------------------------------------------- core: effects, pinned parents, envelope
add('E01_gate_not_called_before_a_mutating_call','core',"    gate();state.issue()\n    try:result=action()\n","    state.issue()\n    try:result=action()\n")
add('E02_failed_call_left_uncertain','core',"    except OSError:state.fail();raise\n","    except OSError:raise\n")
add('E03_successful_call_not_counted','core',"    state.done();return result\n","    state.unknown();return result\n")
add('E04_escaped_exception_always_a_refusal','core',"        nothing=(not state.started) or (WRITES_ALLOWED and state.clean() and not state.pending)\n","        nothing=True\n")
add('E05_escape_after_start_of_a_write_is_a_refusal_when_uncertain','core',"        nothing=(not state.started) or (WRITES_ALLOWED and state.clean() and not state.pending)\n","        nothing=(not state.started) or WRITES_ALLOWED\n")
add('E06_reduced_receipt_stays_complete','core',"            if receipt['status']==COMPLETE_STATUS:receipt['status']=PARTIAL_STATUS;receipt['outcome']=REDUCED_OUTCOME\n","")
add('E07_chain_rows_not_compared','core',"            need(stat.S_ISDIR(info.st_mode) and row_equal(seen,row,compare_device),'PARENT_IDENTITY_MISMATCH')\n","            need(stat.S_ISDIR(info.st_mode),'PARENT_IDENTITY_MISMATCH')\n")
add('E08_symlink_component_opened','core',"                if not stat.S_ISDIR(named.st_mode):\n                    observed.append(dict(row_of(row['path'],named),type=kind(named.st_mode)))\n                    raise Refused('PARENT_SYMLINK_COMPONENT' if stat.S_ISLNK(named.st_mode) else 'PARENT_NOT_DIRECTORY')\n","")
add('E09_verify_skips_the_fresh_walk','core',"            if self.rows is not None:\n                other=walk_pinned(self.host,self.rows,check,[],self.compare_device)\n                try:need(self.stamp(self.host.fstat(other))==self.identity,'PARENT_REPLACED')\n                finally:self.host.close(other)\n            else:","            if self.rows is not None:pass\n            else:")
add('E10_verify_skips_the_name_of_a_child','core',"                need(self.stamp(self.host.lstat(self.name,self.parent.fd))==self.identity,'PARENT_REPLACED')\n","                pass\n")
add('E11_probe_follows_nothing_but_reports_a_symlink_component_absent','core',"                return {'status':'UNAVAILABLE','code':'SYMLINK_COMPONENT','exists':None,'at':prefix}\n","                return {'status':'COMPLETE','exists':False,'absent_at':prefix,'absence_proved_at_read':True}\n")
add('E12_descend_without_nofollow','core',"""    descriptor. With rows, one observed row per component ('/' included) is appended in the format a request signs.\"\"\"
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
""","""    descriptor. With rows, one observed row per component ('/' included) is appended in the format a request signs.\"\"\"
    flags=os.O_RDONLY|os.O_DIRECTORY|host.noatime()
""")
add('E13_descend_enters_a_symlink_component','core',"            need(not stat.S_ISLNK(named.st_mode),'SYMLINK_COMPONENT')\n            need(stat.S_ISDIR(named.st_mode),'COMPONENT_NOT_DIRECTORY')\n            check();child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child\n            held=host.fstat(fd);need((held.st_dev,held.st_ino)==(named.st_dev,named.st_ino),'PATH_CHANGED')\n            if rows",
    "            check();child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child\n            held=host.fstat(fd);need((held.st_dev,held.st_ino)==(named.st_dev,named.st_ino),'PATH_CHANGED')\n            if rows")
add('E14_file_change_during_read_ignored','core',"        need(signature(before)==signature(after) and size==before.st_size,'FILE_CHANGED_DURING_READ')\n","")
add('E15_file_size_limit_ignored','core',"        need(stat.S_ISREG(before.st_mode),'FILE_NOT_REGULAR');need(before.st_size<=limit,'FILE_TOO_LARGE')\n","        need(stat.S_ISREG(before.st_mode),'FILE_NOT_REGULAR')\n")
add('E16_boot_id_shape_unchecked','core',"    need(type(raw) is bytes and re.fullmatch(rb'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}\\n?',raw) is not None,'BOOT_ID_INVALID')\n","")
add('E17_noatime_not_required','core',"        flag=getattr(os,'O_NOATIME',0);need(flag,'NOATIME_UNAVAILABLE');return flag\n","        flag=getattr(os,'O_NOATIME',0);return flag\n")
add('E18_authentication_refusal_raised_out_of_run','core',"        except Refused as error:\n            return seal(envelope(REFUSED_STATUS,REFUSED_OUTCOME,code_of(error,'AUTHENTICATION_REFUSED'),\n                                 dict(bound,phase_reached='AUTHENTICATION',mutating_calls=state.counts())))\n","        except KeyError as error:\n            return seal(envelope(REFUSED_STATUS,REFUSED_OUTCOME,code_of(error,'AUTHENTICATION_REFUSED'),\n                                 dict(bound,phase_reached='AUTHENTICATION',mutating_calls=state.counts())))\n")

# ---------------------------------------------------------------- layout (provision and precheck)
add('L01_setgid_parent_accepted','layout',"        need(not rows[-1]['mode']&stat.S_ISGID,'PARENT_SETGID')\n","")
add('L02_system_chain_row_floor_removed','layout',"            code=row_accepted(row,volume);need(code is None,code or 'CHAIN_ROW_UNSAFE')\n","            pass\n")
add('L03_non_root_rows_accepted_only_inside_the_volume_removed','layout',"    if volume is None or not inside(row['path'],volume):return 'CHAIN_ROW_UNSAFE'\n","    if volume is None:return 'CHAIN_ROW_UNSAFE'\n")
add('L04_forbidden_zones_removed','layout',"    return (clean_path(value) and value!='/' and not any(inside(value,zone) for zone in FORBIDDEN_ZONES)\n","    return (clean_path(value) and value!='/'\n")
add('L05_denied_names_accepted','layout',"    return text(value,LEAF) and not any(re.fullmatch(pattern,value) for pattern in NAME_DENY)\n","    return text(value,LEAF)\n")
add('L06_capacity_inside_a_journal_accepted','layout',"        need(not any(inside(root,journal) or inside(journal,root) for journal in journals) and root!=volume\n             and not inside(volume,root),'CAPACITY_JOURNAL_OVERLAP')\n","")
add('L07_receipt_directory_anywhere','layout',"             and ((parent==root and PurePosixPath(receipts).name not in CAPACITY_ROOTS) or (parent==RDR_STATE and 'READER' in groups)),\n","             ,\n")
add('L08_group_order_and_set_unchecked','layout',"         and groups==[group for group in GROUPS if group in groups],'GROUPS_INVALID')\n","         ,'GROUPS_INVALID')\n")
add('L09_chain_set_unchecked','layout',"    need(type(chains) is dict and set(chains)==set(paths),'CHAIN_MISSING')\n","    need(type(chains) is dict and set(chains)>=set(paths),'CHAIN_MISSING')\n")
add('L10_existing_leaf_reused','layout',"        need(leaf_name(leaf) and leaf not in existing,'LEAF_INVALID')\n","        need(leaf_name(leaf),'LEAF_INVALID')\n")
add('L11_top_level_capacity_root_accepted','layout',"        need(open_path(root) and len(PurePosixPath(root).parts)>=3,'PATH_FORBIDDEN_ZONE')\n","        need(open_path(root),'PATH_FORBIDDEN_ZONE')\n")
add('L12_chain_row_shape_unchecked','core',"        need(integer(row['device']) and integer(row['inode'],1) and integer(row['uid']) and integer(row['gid'])\n             and integer(row['mode'],0,0o7777),code)\n","")

# ---------------------------------------------------------------- provision
add('P01_layout_not_compared_with_the_code_table','op_provision',"        need(type(item) is dict and set(item)==set(row)|{'expect'}\n             and canonical({key:item[key] for key in row})==canonical(row),'LAYOUT_MISMATCH')\n","        need(type(item) is dict and set(item)==set(row)|{'expect'},'LAYOUT_MISMATCH')\n")
add('P02_extra_or_missing_rows_accepted','op_provision',"    need(type(creates) is list and len(creates)==len(table),'LAYOUT_MISMATCH')\n","    need(type(creates) is list,'LAYOUT_MISMATCH')\n")
add('P03_nothing_to_create_accepted','op_provision',"    need(any(item['expect']=='ABSENT' for item in creates) or (tag is not None and tag['expect']=='ABSENT'),'NOTHING_TO_CREATE')\n","")
add('P04_present_child_under_absent_parent_accepted','op_provision',"        need(parent is None or by[parent]['expect']!='ABSENT' or item['expect']=='ABSENT','EXPECT_INVALID')\n","")
add('P05_boot_of_the_evidence_not_compared','op_provision',"            need(boot==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n","")
add('P06_executor_group_not_checked','op_provision',"            need(tuple(actor)==(0,0),'EXECUTOR_IDENTITY')\n","            need(actor[0]==0,'EXECUTOR_IDENTITY')\n")
add('P07_umask_not_set','op_provision',"            host.umask(0o077)\n","")
add('P08_precheck_result_ignored','op_provision',"        if code is not None:\n            return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})\n        stop=None\n        for item in plan['creates']:","        stop=None\n        for item in plan['creates']:")
add('P09_precheck_stops_at_the_first_destination','op_provision',"        rows.append(row);reference=item['parent']\n","        rows.append(row);reference=item['parent']\n        if len(rows)>1:row['observed']='ABSENT';continue\n")
add('P10_non_conforming_directory_called_a_prior_prefix','op_provision',"            elif row['conforms'] and row.get('foreign_entries')==0:row['state']='PRESENT_NOT_SIGNED'\n","            elif True:row['state']='PRESENT_NOT_SIGNED'\n")
add('P11_foreign_entries_ignored','op_provision',"            elif row['conforms'] and row.get('foreign_entries')==0:row['state']='PRESENT_NOT_SIGNED'\n","            elif row['conforms']:row['state']='PRESENT_NOT_SIGNED'\n")
add('P12_signed_present_identity_not_compared','op_provision',"        elif row['conforms'] and (row['device'],row['inode'],row.get('entries'))==(expect['device'],expect['inode'],expect['entries']):\n","        elif row['conforms']:\n")
add('P13_signed_present_entry_count_not_compared','op_provision',"(row['device'],row['inode'],row.get('entries'))==(expect['device'],expect['inode'],expect['entries']):","(row['device'],row['inode'])==(expect['device'],expect['inode']):")
add('P14_all_present_called_a_prefix','op_provision',"        if all(present):code='ALL_DESTINATIONS_PRESENT'\n        elif present==sorted(present,reverse=True):code='PRIOR_PROVISION_PREFIX_PRESENT'\n","        if present==sorted(present,reverse=True):code='PRIOR_PROVISION_PREFIX_PRESENT'\n")
add('P15_any_present_set_called_a_prefix','op_provision',"        elif present==sorted(present,reverse=True):code='PRIOR_PROVISION_PREFIX_PRESENT'\n","        elif True:code='PRIOR_PROVISION_PREFIX_PRESENT'\n")
add('P16_mkdir_mode_changed','op_provision',"    try:mutate(state,gate,lambda:host.mkdir(name,DIRECTORY_MODE,parent.fd))\n","    try:mutate(state,gate,lambda:host.mkdir(name,0o755,parent.fd))\n")
add('P17_failure_after_mkdir_reported_not_created','op_provision',"    entry['state']='CREATED_UNVERIFIED'\n","    entry['state']='NOT_CREATED'\n")
add('P18_created_metadata_not_checked','op_provision',"        if not (stat.S_ISDIR(info.st_mode) and info.st_uid==0 and info.st_gid==0\n                and stat.S_IMODE(info.st_mode)==DIRECTORY_MODE and info.st_dev==parent.identity[0]):\n            entry.update(state='CREATED_METADATA_MISMATCH',code='CREATED_METADATA_MISMATCH');return entry\n","")
add('P19_created_name_identity_not_checked','op_provision',"        if (named.st_dev,named.st_ino)!=(info.st_dev,info.st_ino):\n            entry['code']='CREATED_NAME_REPLACED';return entry\n","")
add('P20_created_emptiness_not_checked','op_provision',"    if entry['observed']['entries']:\n        entry.update(state='CREATED_NOT_EMPTY',code='CREATED_NOT_EMPTY');return entry\n","")
add('P21_failed_fsync_reported_durable','op_provision',"        entry.update(state='CREATED_NOT_DURABLE',code='FSYNC_FAILED',\n","        entry.update(state='CREATED_DURABLE',code=None,\n")
add('P22_refused_after_a_creation','op_provision',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n","        if True:return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n")
add('P23_creation_continues_after_a_failure','op_provision',"            if entry['state']!='CREATED_DURABLE':stop=entry['code'] or 'CREATION_FAILED'\n","            pass\n")
add('P24_signed_present_entry_is_created_again','op_provision',"            if item['expect']!='ABSENT':\n                ledger.append({'key':item['key'],'path':item['path'],'state':'PRESENT_VERIFIED_NOT_TOUCHED'","            if False:\n                ledger.append({'key':item['key'],'path':item['path'],'state':'PRESENT_VERIFIED_NOT_TOUCHED'")
add('P25_tag_absence_inferred_from_a_failed_listing','listing',"        raise Refused(str(error) if str(error) in ('GO_EXPIRED','CLOCK_REVERSED','BINARY_UNAVAILABLE_OR_UNSAFE') else 'TAG_LISTING_UNAVAILABLE') from None\n","        return []\n")
add('P26_listing_rows_unvalidated','listing',"            need(set(row)=={'id','repository','tag'} and text(row['id'],IMAGE_ID) and row['repository']==REPOSITORY\n                 and text(row['tag'],'[A-Za-z0-9_.<>-]{1,128}'),'TAG_LISTING_UNAVAILABLE')\n","")
add('P27_listing_without_the_signed_image_accepted','op_provision',"            need(any(row['id']==tag['image_id'] for row in listed),'TAG_LISTING_INCONSISTENT')\n            named=","            named=")
add('P28_existing_tag_overwritten','op_provision',"            if tag['expect']=='ABSENT':need(not named,'RETENTION_TAG_EXISTS')\n","            if tag['expect']=='ABSENT':pass\n")
add('P29_signed_present_tag_on_another_image_accepted','op_provision',"            else:need(bool(named) and named[0]['id']==tag['image_id'],'EXPECTATION_MISMATCH')\n","            else:need(bool(named),'EXPECTATION_MISMATCH')\n")
add('P30_image_id_of_the_inspect_not_compared','op_provision',"            need(image['id']==tag['image_id'],'IMAGE_ID_MISMATCH');facts['image_present']=True\n","            facts['image_present']=True\n")
add('P31_tag_step_without_budget','op_provision',"        need(gate()>=TAG_BUDGET_SECONDS,'TAG_NOT_ATTEMPTED_BUDGET')\n","        gate()\n")
add('P32_tag_step_without_the_second_listing','op_provision',"        need(not any(row['tag']==tag['tag'] for row in listed),'TAG_APPEARED_AFTER_PRECHECK')\n","")
add('P33_failed_tag_command_called_absent_without_proof','op_provision',"        try:absent=not any(row['tag']==tag['tag'] for row in listing(commands))\n        except Exception:absent=False\n","        absent=True\n")
add('P34_tag_timeout_called_not_created','op_provision',"        state.unknown();facts.update(state='UNCERTAIN',code='TAG_COMMAND_TIMEOUT' if code=='COMMAND_TIMEOUT' else code);return\n","        state.fail();facts.update(state='NOT_CREATED',code='TAG_COMMAND_TIMEOUT' if code=='COMMAND_TIMEOUT' else code);return\n")
add('P35_tag_readback_dropped','op_provision',"        need(facts['readback_id_equal'] and image['reference_among_repo_tags'],'TAG_READBACK_MISMATCH')\n","")
add('P36_tag_attempted_after_a_failed_directory','op_provision',"            elif stop is None:\n                create_tag(tag,facts,gate,state,commands)\n","            elif True:\n                create_tag(tag,facts,gate,state,commands)\n")
add('P37_readback_inside_the_run_dropped','op_provision',"        if stop is None:\n            check=readback(plan,host,gate,parents,handles,ledger)\n            if check['status']!='COMPLETE':stop=check['code'] or 'READBACK_UNAVAILABLE'\n","")
add('P38_readback_ignores_entry_counts','op_provision',"            need(same and item['entries_as_expected'],'READBACK_MISMATCH')\n","            need(same,'READBACK_MISMATCH')\n")
add('P39_readback_ignores_the_resolved_path','op_provision',"            need(same and item['entries_as_expected'],'READBACK_MISMATCH')\n","            need(item['entries_as_expected'],'READBACK_MISMATCH')\n")
add('P40_readback_ignores_the_pinned_parents','op_provision',"        for name in sorted(parents):parents[name].verify(gate)\n","")
add('P41_tag_expect_shape_unchecked','op_provision',"        need(type(tag['expect']) is str and tag['expect'] in ('ABSENT','PRESENT'),'EXPECT_INVALID')\n","")
add('P42_tag_grammar_unchecked','op_provision',"             and text(tag['tag'],TAG),'TAG_INVALID')\n","             ,'TAG_INVALID')\n")
add('P43_evidence_boot_shape_unchecked','op_provision',"    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')\n","")
add('P44_precheck_does_not_open_present_directories_nofollow','op_provision',"    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()\n    rows=[];children={}\n","    flags=os.O_RDONLY|os.O_DIRECTORY|host.noatime()\n    rows=[];children={}\n")
add('P45_created_directory_opened_following_links','op_provision',"    name=PurePosixPath(item['path']).name\n    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()\n","    name=PurePosixPath(item['path']).name\n    flags=os.O_RDONLY|os.O_DIRECTORY|host.noatime()\n")

# ---------------------------------------------------------------- unit installation
add('I01_link_replaced_by_rename','op_install_units',"    def link(self,source,target,dir_fd):os.link(source,target,src_dir_fd=dir_fd,dst_dir_fd=dir_fd,follow_symlinks=False)\n","    def link(self,source,target,dir_fd):os.rename(source,target,src_dir_fd=dir_fd,dst_dir_fd=dir_fd)\n")
add('I02_final_name_removed_instead_of_the_temporary','op_install_units',"        mutate(state,gate,lambda:host.unlink(temp,directory.fd))\n","        mutate(state,gate,lambda:host.unlink(entry['path'].rsplit('/',1)[1],directory.fd))\n")
add('I03_temporary_removed_without_identity_proof','op_install_units',"        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino):return 'TEMPORARY_REPLACED'\n","")
add('I04_temporary_name_loadable_by_systemd','op_install_units',"TEMPORARY='.hostops-%s-%d.partial'\n","TEMPORARY='hostops-%s-%d.service'\n")
add('I05_written_directly_under_the_final_name','op_install_units',"    try:fd=mutate(state,gate,lambda:host.create(temp,flags,UNIT_MODE,directory.fd))\n","    try:fd=mutate(state,gate,lambda:host.create(name,flags,UNIT_MODE,directory.fd))\n")
add('I06_precheck_result_ignored','op_install_units',"        if code is not None:\n            return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})\n        stop=None\n        for index,(unit,content)","        stop=None\n        for index,(unit,content)")
add('I07_precheck_covers_only_the_first_unit','op_install_units',"        rows.append(row);gate()\n        try:named=host.lstat(name,fd)\n        except FileNotFoundError:named=None\n","        rows.append(row);gate()\n        try:named=host.lstat(name,fd) if len(rows)==1 else None\n        except FileNotFoundError:named=None\n")
add('I08_drop_in_ignored','op_install_units',"    elif 'DROP_IN_PRESENT' in scan['finding_codes']:code='DROP_IN_PRESENT'\n","")
add('I09_enablement_link_ignored','op_install_units',"    elif 'ENABLEMENT_LINK_PRESENT' in scan['finding_codes']:code='ENABLEMENT_LINK_PRESENT'\n","")
add('I10_shadowing_unit_ignored','op_install_units',"    elif 'UNIT_SHADOWED_IN_OTHER_PATH' in scan['finding_codes']:code='UNIT_SHADOWED_IN_OTHER_PATH'\n","")
add('I11_incomplete_scan_treated_as_absence','op_install_units',"    elif scan['status']!='COMPLETE':code='CONFLICT_SCAN_UNAVAILABLE'\n","")
add('I12_unacknowledged_leftover_ignored','op_install_units',"    elif scan['leftover_count']>MAX_FINDINGS or scan['leftovers_not_acknowledged']:\n        code='TEMPORARY_NAME_OCCUPIED' if own&set(scan['leftovers_not_acknowledged']) else 'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'\n    elif own&set(seen):code='TEMPORARY_NAME_OCCUPIED'\n","")
add('I13_foreign_file_at_a_unit_name_called_a_prior_partial','op_install_units',"            elif expect=='ABSENT':row['state']='PRESENT_EQUAL_NOT_SIGNED' if conforms and named.st_nlink in (1,2) else 'PRESENT_FOREIGN'\n","            elif expect=='ABSENT':row['state']='PRESENT_EQUAL_NOT_SIGNED'\n")
add('I14_non_regular_object_at_a_unit_name_tolerated','op_install_units',"            if not stat.S_ISREG(named.st_mode):row['state']='OCCUPIED_NOT_REGULAR'\n            elif expect=='ABSENT'","            if not stat.S_ISREG(named.st_mode):row['state']='OK_ABSENT'\n            elif expect=='ABSENT'")
add('I15_signed_present_unit_bytes_not_compared','op_install_units',"            conforms=bool(equal and named.st_uid==0 and named.st_gid==0 and stat.S_IMODE(named.st_mode)==UNIT_MODE)\n","            conforms=bool(named.st_uid==0 and named.st_gid==0 and stat.S_IMODE(named.st_mode)==UNIT_MODE)\n")
add('I16_signed_present_unit_identity_not_compared','op_install_units',"            elif conforms and (named.st_dev,named.st_ino,named.st_nlink)==(expect['device'],expect['inode'],expect['links']):\n","            elif conforms:\n")
add('I17_acknowledged_leftover_not_required_to_exist','op_install_units',"    elif states&{'EXPECTED_PRESENT_ABSENT','PRESENT_IDENTITY_MISMATCH'} or set(signed)-set(seen):code='EXPECTATION_MISMATCH'\n","    elif states&{'EXPECTED_PRESENT_ABSENT','PRESENT_IDENTITY_MISMATCH'}:code='EXPECTATION_MISMATCH'\n")
add('I18_all_present_called_a_partial','op_install_units',"        code='ALL_UNITS_PRESENT' if settled else 'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'\n","        code='PRIOR_PARTIAL_REQUIRES_RECONCILIATION'\n")
add('I19_short_write_accepted','op_install_units',"                if type(size) is not int or size<=0:return withdrawn('WRITE_INCOMPLETE')\n                written+=size\n","                written+=size if size else len(content)\n")
add('I20_created_file_metadata_not_checked','op_install_units',"            if not (stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==0 and info.st_gid==0\n                    and stat.S_IMODE(info.st_mode)==UNIT_MODE and info.st_size==len(content)\n                    and info.st_dev==directory.identity[0]):return withdrawn('CREATED_METADATA_MISMATCH')\n","")
add('I21_failed_file_fsync_ignored','op_install_units',"        except OSError as error:return withdrawn('FSYNC_FAILED',error)\n        try:\n            info=host.fstat(fd)\n","        except OSError as error:pass\n        try:\n            info=host.fstat(fd)\n")
add('I22_failed_directory_fsync_after_link_ignored','op_install_units',"        try:host.fsync(directory.fd);entry['fsync_directory_after_link']=True\n        except OSError as error:return failed('FSYNC_FAILED',error)\n","        try:host.fsync(directory.fd);entry['fsync_directory_after_link']=True\n        except OSError as error:pass\n")
add('I23_refused_after_a_creation','op_install_units',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n","        if True:return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n")
add('I24_installation_continues_after_a_failure','op_install_units',"            if entry['state']!='INSTALLED_DURABLE':stop=entry['code'] or 'INSTALL_FAILED'\n","            pass\n")
add('I25_readback_inside_the_run_dropped','op_install_units',"        if stop is None:\n            check=readback(plan,rendered,directory,host,gate,ledger)\n            if check['status']!='COMPLETE':stop=check['code'] or 'READBACK_UNAVAILABLE'\n","")
add('I26_readback_does_not_compare_bytes','op_install_units',"            need(raw==content and same and info.st_uid==0","            need(same and info.st_uid==0")
add('I27_umask_not_set','op_install_units',"            host.umask(0o022)\n","")
add('I28_file_mode_constant_changed','op_install_units',"    try:fd=mutate(state,gate,lambda:host.create(temp,flags,UNIT_MODE,directory.fd))\n","    try:fd=mutate(state,gate,lambda:host.create(temp,flags,0o600,directory.fd))\n")
add('I29_boot_of_the_evidence_not_compared','op_install_units',"            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n","")
add('I30_executor_group_not_checked','op_install_units',"            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n","            need(host.identity()[0]==0,'EXECUTOR_IDENTITY')\n")
add('I31_unit_name_grammar_unchecked','op_install_units',"        need(unit_name(unit['destination_name']),'UNIT_NAME_INVALID')\n","        need(type(unit['destination_name']) is str,'UNIT_NAME_INVALID')\n")
add('I32_duplicate_destination_accepted','op_install_units',"         and len({unit['destination_name'] for unit in units})==len(units),'UNIT_NAME_DUPLICATE')\n","         ,'UNIT_NAME_DUPLICATE')\n")
add('I33_unit_directory_floor_removed','op_install_units',"    need(all(row_root_safe(row) for row in rows),'CHAIN_ROW_UNSAFE')\n","")
add('I34_setgid_unit_directory_accepted','op_install_units',"    need(not rows[-1]['mode']&stat.S_ISGID,'PARENT_SETGID')\n","")
add('I35_reload_owner_not_required','op_install_units',"    need(text(plan['daemon_reload_owner'],'[A-Z][A-Z0-9_]{2,63}') and plan['daemon_reload_owner']!='UNBOUND','RELOAD_OWNER_UNBOUND')\n","")
add('I36_template_revision_not_required','op_install_units',"    need(text(plan['template_revision'],'[0-9a-f]{40}'),'TEMPLATE_REVISION_UNBOUND')\n","")
add('I37_aggregate_template_cap_removed','op_install_units',"    need(total<=MAX_TEMPLATE_BYTES_TOTAL,'TEMPLATE_TOO_LARGE')\n","")
add('I39_mode_of_the_signed_unit_unchecked','op_install_units',"             and type(unit['mode']) is int and unit['mode']==UNIT_MODE and type(unit['placeholders']) is dict,'UNITS_INVALID')\n","             and type(unit['placeholders']) is dict,'UNITS_INVALID')\n")
add('I40_own_temporary_left_after_a_lost_race','op_install_units',"            entry['temporary_removal_code']=remove_own_temporary(temp,fd,directory,host,gate,state,entry)\n","            entry['temporary_removal_code']=None\n")
add('I41_nothing_to_create_accepted','op_install_units',"    need(any(unit['expect']=='ABSENT' for unit in units),'NOTHING_TO_CREATE')\n","")
add('I42_a_systemctl_verb_inserted','op_install_units',STARTED,"    state.started=True;os.system('/usr/bin/true daemon-reload')\n    detail={'unit_directory':[],'precheck':None}")

# ---------------------------------------------------------------- conflict scan (install, readback, precheck)
add('S01_scan_reduced_to_the_install_directory','scan',"    for directory in LOOKUP_DIRECTORIES:directories[directory]=attempt(lambda directory=directory:one(directory))\n","    for directory in LOOKUP_DIRECTORIES[4:5]:directories[directory]=attempt(lambda directory=directory:one(directory))\n")
add('S02_type_level_drop_in_ignored','scan',"    return [name+'.d',suffix+'.d']+","    return [name+'.d']+")
add('S03_prefix_drop_ins_ignored','scan',"    return [name+'.d',suffix+'.d']+['-'.join(parts[:index])+'-.'+suffix+'.d' for index in range(1,len(parts))]\n","    return [name+'.d',suffix+'.d']\n")
add('S04_upholds_and_requires_ignored','scan',"DEPENDENCY_SUFFIXES=('.wants','.requires','.upholds')\n","DEPENDENCY_SUFFIXES=('.wants',)\n")
add('S05_shadowing_unit_ignored','scan',"                if directory!=UNIT_DIRECTORY and present(name,fd) is not None:add('UNIT_SHADOWED_IN_OTHER_PATH',directory,name)\n","")
add('S06_symlinked_dependency_directory_ignored','scan',"                if not stat.S_ISDIR(info.st_mode):\n                    issues.append('DEPENDENCY_DIRECTORY_NOT_A_DIRECTORY');continue\n","                if not stat.S_ISDIR(info.st_mode):continue\n")
add('S07_scan_limit_removed','scan',"                listed.append(name);need(len(listed)<=MAX_SCAN_NAMES,'SCAN_LIMIT')\n","                listed.append(name)\n")
add('S08_unreadable_lookup_directory_reported_complete','scan',"    return {'status':'COMPLETE' if status=='COMPLETE' else 'UNAVAILABLE','directories':directories,\n","    return {'status':'COMPLETE','directories':directories,\n")
add('S09_leftover_temporaries_not_collected','scan',"                    if info is not None:leftovers.append(dict(file_row(info),name=entry))\n","                    pass\n")
add('S10_dependency_directory_opened_following_links','scan',"""    "within" is the dependency directory the name was found in or, for an alias, the unit name the link text ends in.\"\"\"
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
""","""    "within" is the dependency directory the name was found in or, for an alias, the unit name the link text ends in.\"\"\"
    flags=os.O_RDONLY|os.O_DIRECTORY|host.noatime()
""")

# ---------------------------------------------------------------- readback
TOKEN_FINDINGS="            regular=stat.S_ISREG(named.st_mode);findings=[] if entries==3 else ['CONFIG_DIRECTORY_ENTRIES']\n"
add('B01_token_opened_and_read','op_readback',TOKEN_FINDINGS,TOKEN_FINDINGS.replace("\n",";self.host.close(self.host.open('token',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd))\n"))
add('B02_token_size_emitted','op_readback',"links=named.st_nlink,size_within_1_4096=within,\n","links=named.st_nlink,size_within_1_4096=within,size=named.st_size,\n")
add('B03_token_timestamp_and_identity_emitted','op_readback',"links=named.st_nlink,size_within_1_4096=within,\n","links=named.st_nlink,size_within_1_4096=within,mtime_ns=named.st_mtime_ns,inode=named.st_ino,\n")
add('B04_absent_token_is_no_finding','op_readback',"                return done(findings=['TOKEN_ABSENT']+(['CONFIG_DIRECTORY_ENTRIES'] if entries!=2 else []),exists=False,\n","                return done(findings=[]+(['CONFIG_DIRECTORY_ENTRIES'] if entries!=2 else []),exists=False,\n")
add('B05_token_metadata_not_checked','op_readback',"            if not (named.st_uid==0 and named.st_gid==0 and stat.S_IMODE(named.st_mode)==TOKEN_MODE and named.st_nlink==1):\n                findings.append('TOKEN_METADATA')\n","")
add('B06_token_size_policy_not_checked','op_readback',"            if regular and not within:findings.append('TOKEN_SIZE_POLICY')\n","")
add('B07_token_link_count_not_checked','op_readback',"stat.S_IMODE(named.st_mode)==TOKEN_MODE and named.st_nlink==1):\n                findings.append('TOKEN_METADATA')","stat.S_IMODE(named.st_mode)==TOKEN_MODE):\n                findings.append('TOKEN_METADATA')")
add('B08_mismatch_reported_as_complete','op_readback',"    elif findings:outcome=MISMATCH_OUTCOME\n","")
add('B09_unavailable_item_reported_as_complete','op_readback',"    elif incomplete:outcome=PARTIAL_OUTCOME\n","")
add('B10_reconciliation_takes_the_gate_branch','op_readback',"    elif reconciliation:outcome=RECONCILIATION_OUTCOME\n","")
add('B11_reconciliation_without_its_mandatory_finding','op_readback',"    if reconciliation:findings=sorted(set(findings)|{'INSTALL_RECEIPT_NOT_COMPLETE'})\n","")
add('B12_expired_window_reported_as_partial_only','op_readback',"    if expired:outcome=EXPIRED_OUTCOME\n    elif incomplete:","    if False:outcome=EXPIRED_OUTCOME\n    elif incomplete:")
add('B13_unavailable_layout_path_reported_absent','op_readback',"            if found.get('status')!='COMPLETE':unavailable=True;continue\n","            if found.get('status')!='COMPLETE':findings.append('LAYOUT_ENTRY_ABSENT');continue\n")
add('B14_failed_image_inspect_reported_as_a_mismatch','op_readback',"        except CommandFailed as error:raise CommandFailed('IMAGE_ABSENT_OR_UNREADABLE',error.returncode) from None\n        equal=","        except CommandFailed as error:return done(findings=[mismatch],reference=reference)\n        equal=")
add('B15_docker_commands_without_the_unit_configuration','op_readback',"        try:facts=image_facts(self.commands,reference,self.docker_config)\n","        try:facts=image_facts(self.commands,reference,None)\n")
add('B16_docker_info_without_the_unit_configuration','op_readback',"        row=decode(self.commands.output('info',docker_config=self.docker_config))\n","        row=decode(self.commands.output('info'))\n")
add('B17_docker_handed_a_non_empty_configuration_directory','op_readback',"            if counts['SUP_DOCKER_CLI']['entries']:findings.append('DOCKER_CONFIG_NOT_EMPTY')\n            elif cli.get('metadata_matches'):self.docker_config=self.paths['SUP_DOCKER_CLI']\n","            if counts['SUP_DOCKER_CLI']['entries']:findings.append('DOCKER_CONFIG_NOT_EMPTY')\n            if cli.get('metadata_matches'):self.docker_config=self.paths['SUP_DOCKER_CLI']\n")
add('B18_docker_handed_an_unverified_configuration_directory','op_readback',"            elif cli.get('metadata_matches'):self.docker_config=self.paths['SUP_DOCKER_CLI']\n","            else:self.docker_config=self.paths['SUP_DOCKER_CLI']\n")
add('B19_configuration_directory_change_not_reported','op_readback',"+(['DOCKER_CONFIG_CHANGED_DURING_RUN'] if after!=before else []),","+[],")
add('B20_free_space_uses_the_root_figure','op_readback',"                available=v.f_bavail*v.f_frsize;floor=self.plan['free_space_floor_bytes']\n","                available=v.f_bfree*v.f_frsize;floor=self.plan['free_space_floor_bytes']\n")
add('B21_free_space_floor_not_compared','op_readback',"                return done(findings=[] if available>=floor else ['FREE_SPACE_BELOW_FLOOR'],\n","                return done(findings=[],\n")
FORMULA="    need(type(plan['free_space_floor_bytes']) is int\n         and plan['free_space_floor_bytes']==PRODUCER_FLOOR_BYTES+SESSION_BYTES*sessions+allowance,'FLOOR_NOT_THE_GATE_FORMULA')\n"
add('B22_floor_is_a_free_number_again','op_readback',FORMULA,"    need(integer(plan['free_space_floor_bytes'],PRODUCER_FLOOR_BYTES,1<<60),'FLOOR_NOT_THE_GATE_FORMULA')\n")
add('B22b_floor_formula_without_the_sessions','op_readback',FORMULA,FORMULA.replace("PRODUCER_FLOOR_BYTES+SESSION_BYTES*sessions+allowance","PRODUCER_FLOOR_BYTES+allowance"))
add('B22c_floor_formula_without_the_allowance','op_readback',FORMULA,FORMULA.replace("PRODUCER_FLOOR_BYTES+SESSION_BYTES*sessions+allowance","PRODUCER_FLOOR_BYTES+SESSION_BYTES*sessions"))
add('B22d_floor_may_exceed_the_formula','op_readback',FORMULA,FORMULA.replace("plan['free_space_floor_bytes']==PRODUCER","plan['free_space_floor_bytes']>=PRODUCER"))
add('B22e_floor_may_be_below_the_formula','op_readback',FORMULA,FORMULA.replace("plan['free_space_floor_bytes']==PRODUCER","plan['free_space_floor_bytes']<=PRODUCER"))
add('B22f_floor_type_unchecked','op_readback',FORMULA,FORMULA.replace("type(plan['free_space_floor_bytes']) is int\n         and ",""))
TERMS="    need(integer(sessions,1,MAX_SESSIONS_RETAINED) and integer(allowance,0,MAX_ALLOWANCE_BYTES),'FLOOR_TERMS_INVALID')\n"
add('B22g_zero_sessions_accepted','op_readback',TERMS,TERMS.replace("integer(sessions,1,","integer(sessions,0,"))
add('B22h_session_cap_dropped','op_readback',TERMS,TERMS.replace("integer(sessions,1,MAX_SESSIONS_RETAINED)","integer(sessions,1)"))
add('B22i_negative_allowance_accepted','op_readback',TERMS,TERMS.replace("integer(allowance,0,MAX_ALLOWANCE_BYTES)","type(allowance) is int"))
add('B24_values_echoed_from_the_request','op_readback',"        extracted=extract_values(template,self.service_bytes)\n","        extracted=dict(self.values)\n")
add('B25_unit_bytes_not_compared','op_readback',"                if not row['bytes_equal_signed_render']:findings.append('UNIT_BYTES_MISMATCH')\n","")
add('B26_unit_metadata_not_checked','op_readback',"                if not (info.st_uid==0 and info.st_gid==0 and stat.S_IMODE(info.st_mode)==UNIT_MODE and info.st_nlink==1):\n                    findings.append('UNIT_METADATA')\n","")
add('B27_unit_identity_not_compared','op_readback',"                if row['identity_equal_install_receipt'] is False:findings.append('UNIT_IDENTITY_CHANGED')\n","")
add('B28_absent_unit_is_no_finding','op_readback',"                    files[name]={'exists':False};findings.append('UNIT_ABSENT');continue\n","                    files[name]={'exists':False};continue\n")
add('B29_unit_directory_not_compared','op_readback',"            if not directory_equal:findings.append('UNIT_DIRECTORY_IDENTITY_MISMATCH')\n","")
add('B30_layout_metadata_not_checked','op_readback',"            if not found['metadata_matches']:findings.append('LAYOUT_METADATA')\n","")
add('B31_layout_identity_not_compared','op_readback',"            if found['identity_equal_provision_receipt'] is False:findings.append('LAYOUT_IDENTITY_CHANGED')\n","")
add('B32_absent_layout_entry_is_no_finding','op_readback',"                findings.append('LAYOUT_ENTRY_ABSENT');continue\n            found.pop","                continue\n            found.pop")
add('B33_data_volume_rows_not_compared','op_readback',"            if not equal:findings.append('DATA_VOLUME_ROW_CHANGED')\n","")
add('B35_catalog_names_not_checked','op_readback',"                if set(names)!=set(CATALOG_NAMES):findings.append('CATALOG_ENTRIES')\n","")
add('B36_catalog_metadata_not_checked','op_readback',"                        and stat.S_IMODE(named.st_mode)==TOKEN_MODE and named.st_nlink==1):findings.append('CATALOG_METADATA')\n","                        and stat.S_IMODE(named.st_mode)==TOKEN_MODE and named.st_nlink==1):pass\n")
add('B37_catalog_identity_not_compared','op_readback',"                if (held.st_dev,held.st_ino)!=(catalog['device'],catalog['inode']):findings.append('CATALOG_IDENTITY_MISMATCH')\n","")
add('B38_unexpected_catalog_ignored','op_readback',"            elif names:findings=[code for code in findings if code!='CATALOG_METADATA']+['CATALOG_UNEXPECTED']\n","")
add('B39_catalog_entry_limit_removed','op_readback',"                names.append(name);need(len(names)<=MAX_CATALOG_ENTRIES,'CATALOG_ENTRY_LIMIT')\n","                names.append(name)\n")
add('B40_conflict_findings_dropped','op_readback',"        findings=list(scan['finding_codes'])+(['PRIOR_TEMPORARY_PRESENT'] if scan['leftover_count'] else [])\n","        findings=[]\n")
add('B41_leftover_temporary_is_no_finding','op_readback',"        findings=list(scan['finding_codes'])+(['PRIOR_TEMPORARY_PRESENT'] if scan['leftover_count'] else [])\n","        findings=list(scan['finding_codes'])\n")
add('B42_old_systemd_accepted','op_readback',"        return done(findings=[] if number>=MINIMUM_SYSTEMD else ['SYSTEMD_TOO_OLD'],first_line=line,number=number,minimum=MINIMUM_SYSTEMD)\n","        return done(findings=[],first_line=line,number=number,minimum=MINIMUM_SYSTEMD)\n")
add('B43_old_docker_accepted','op_readback',"        if number<MINIMUM_DOCKER:findings.append('DOCKER_TOO_OLD')\n","")
add('B44_missing_init_binary_accepted','op_readback',"        if row['init_binary']=='' or self.init_present is False:findings.append('INIT_BINARY_MISSING')\n","")
add('B45_init_name_alone_is_enough','op_readback',"        if row['init_binary']=='' or self.init_present is False:findings.append('INIT_BINARY_MISSING')\n","        if row['init_binary']=='':findings.append('INIT_BINARY_MISSING')\n")
add('B46_empty_daemon_answer_trusted','op_readback',"        need(type(row['server_version']) is str and row['server_version']!='','DAEMON_INFO_EMPTY')\n","")
add('B47_inactive_docker_unit_accepted','op_readback',"        return done(findings=[] if (values['Id'],values['ActiveState'])==(DOCKER_UNIT,'active') else ['DOCKER_UNIT_NOT_ACTIVE'],properties=values)\n","        return done(findings=[],properties=values)\n")
add('B48_active_unit_accepted','op_readback',"        if values['ActiveState']!='inactive':findings.append('UNIT_NOT_INACTIVE')\n","")
add('B49_fragment_path_not_checked','op_readback',"        if values['FragmentPath'] not in ('',UNIT_DIRECTORY+'/'+name):findings.append('FRAGMENT_PATH_MISMATCH')\n","")
add('B50_drop_in_reported_by_the_manager_ignored','op_readback',"        if values['DropInPaths']:findings.append('DROP_IN_REPORTED_BY_MANAGER')\n","")
add('B51_reverse_dependency_ignored','op_readback',"        if values['WantedBy'] or values['RequiredBy']:findings.append('REVERSE_DEPENDENCY_REPORTED_BY_MANAGER')\n","")
add('B52_foreign_trigger_ignored','op_readback',"        if values['TriggeredBy'] not in ('',TIMER_NAME if name==SERVICE_NAME else ''):findings.append('TRIGGER_REPORTED_BY_MANAGER')\n","")
add('B53_unit_file_state_of_the_timer_ignored','op_readback',"            if values['UnitFileState'] not in ('','disabled'):findings.append('TIMER_NOT_DISABLED')\n","")
add('B54_is_enabled_word_not_checked','op_readback',"        if word!='disabled':findings.append('TIMER_NOT_DISABLED')\n","")
add('B55_no_answer_read_as_an_answer','op_readback',"        need(re.fullmatch(rb'[a-z-]{1,32}\\n?',raw) is not None,'IS_ENABLED_NO_ANSWER')\n","")
add('B56_enablement_sources_may_disagree','op_readback',"        if self.unit_file_state not in (None,'',word):findings.append('ENABLEMENT_SOURCES_DISAGREE')\n","")
add('B57_unit_id_not_checked','op_readback',"        need(not missing,'PROPERTY_MISSING');need(values['Id']==name,'UNIT_ID_MISMATCH');findings=[]\n","        need(not missing,'PROPERTY_MISSING');findings=[]\n")
add('B58_image_id_not_compared','op_readback',"        equal=facts['id']==self.values['IMAGE_ID'];findings=[] if equal else [mismatch]\n","        equal=facts['id']==self.values['IMAGE_ID'];findings=[]\n")
add('B59_boot_of_the_evidence_ignored','op_readback',"        return done(findings=[] if self.same_boot else ['EVIDENCE_FROM_EARLIER_BOOT'],boot_id_sha256=seen,\n","        return done(findings=[],boot_id_sha256=seen,\n")
add('B60_device_numbers_never_compared','op_readback',"        self.same_boot=signed is None or seen==signed\n","        self.same_boot=signed is None or seen==signed;self.same_boot=False if self.same_boot else False\n")
add('B61_gate_mode_accepts_an_incomplete_install','op_readback',"        need(hexpin(install['receipt_sha256']) and install['outcome']==INSTALL_COMPLETE,'INSTALL_RECEIPT_UNBOUND')\n","        need(hexpin(install['receipt_sha256']),'INSTALL_RECEIPT_UNBOUND')\n")
add('B62_gate_mode_accepts_null_identities','op_readback',"    need(numbers or (not strict_mode and item['device'] is None and item['inode'] is None),code)\n","    need(numbers or (item['device'] is None and item['inode'] is None),code)\n")
add('B63_gate_mode_accepts_a_null_install_receipt','op_readback',"        need(hexpin(install['receipt_sha256']) and install['outcome']==INSTALL_COMPLETE,'INSTALL_RECEIPT_UNBOUND')\n","        need(install['outcome']==INSTALL_COMPLETE,'INSTALL_RECEIPT_UNBOUND')\n")
add('B64_retention_reference_grammar_unchecked','op_readback',"    need(type(plan['retention_reference']) is str and re.fullmatch(re.escape(REPOSITORY)+':'+TAG,plan['retention_reference']) is not None,\n         'TAG_INVALID')\n","    need(type(plan['retention_reference']) is str,'TAG_INVALID')\n")
add('B65_catalog_expectation_shape_unchecked','op_readback',"        need(hexpin(catalog['receipt_sha256']) and integer(catalog['device']) and integer(catalog['inode'],1),'CATALOG_INVALID')\n","        pass\n")
add('B66_a_systemctl_verb_inserted','op_readback',"          'timer_enabled':['systemctl',['is-enabled',TIMER_NAME],None],\n","          'timer_enabled':['systemctl',['is-enabled','--now',TIMER_NAME],None],\n")
add('B67_tag_missing_from_repo_tags_accepted','op_readback',"        if reference!=self.values['IMAGE_ID'] and equal and not facts['reference_among_repo_tags']:findings.append(mismatch)\n","")
add('B68_provision_receipt_not_required','op_readback',"        need(hexpin(provision['receipt_sha256']),'PROVISION_RECEIPT_UNBOUND')\n        need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')\n","")

# ---------------------------------------------------------------- precheck
add('K01_secret_bearing_name_reported_with_identity','op_precheck',"    return {'status':'COMPLETE','exists':True,**{key:found[key] for key in ('type','uid','gid','mode_octal','links')}}\n","    return dict(found)\n")
add('K02_symlink_component_reported_absent_for_a_secret_name','op_precheck',"    if found.get('status')!='COMPLETE':return {key:found.get(key) for key in ('status','code','at')}\n    if not found['exists']:return {'status':'COMPLETE','exists':False,'absent_at':found['absent_at']}\n","    if found.get('status')!='COMPLETE' or not found['exists']:return {'status':'COMPLETE','exists':False,'absent_at':found.get('absent_at') or found.get('at')}\n")
add('K03_failed_image_inspect_reported_complete','op_precheck',"        except CommandFailed as error:raise CommandFailed('IMAGE_ABSENT_OR_UNREADABLE',error.returncode) from None\n        return dict(facts,","        except CommandFailed as error:return {'status':'COMPLETE','id':None,'repo_tags':[]}\n        return dict(facts,")
add('K04_retention_tag_group_accepted','op_precheck',"    need(type(groups) is list and 'RETENTION_TAG' not in groups,'GROUPS_INVALID')\n","    need(type(groups) is list,'GROUPS_INVALID')\n")
add('K05_any_image_reference_accepted','op_precheck',"    need(plan['image_reference']==PRODUCTION_REFERENCE,'IMAGE_REFERENCE_INVALID')\n","    need(type(plan['image_reference']) is str,'IMAGE_REFERENCE_INVALID')\n")
add('K06_unit_names_unchecked','op_precheck',"    need(unit_names(plan['unit_names']),'UNIT_NAME_INVALID')\n","    need(type(plan['unit_names']) is list,'UNIT_NAME_INVALID')\n")
add('K07_incomplete_precheck_reported_complete','op_precheck',"    outcome=EXPIRED_OUTCOME if expired else PARTIAL_OUTCOME if incomplete else COMPLETE_OUTCOME\n","    outcome=EXPIRED_OUTCOME if expired else COMPLETE_OUTCOME\n")
add('K08_setgid_bit_not_reported','op_precheck',"                'direct_parent_setgid':bool(rows[-1]['mode']&stat.S_ISGID),\n","                'direct_parent_setgid':False,\n")
add('K09_children_of_a_present_directory_not_split','op_precheck',"            result['table_defined_children']=defined;result['other_entries']=result['entries']-defined\n","            result['table_defined_children']=defined;result['other_entries']=0\n")
add('K10_core_pattern_content_emitted','op_precheck',"    return {'status':'COMPLETE','is_pipe':raw==b'|'}\n","    return {'status':'COMPLETE','is_pipe':raw==b'|','first_byte':raw.decode('latin-1')}\n")
for label,call in (('os_mkdir',"os.makedirs('hostops-mutant-directory',exist_ok=True)"),('builtin_open',"open('hostops-mutant-marker','w').close()")):
    add('K11_precheck_writes_'+label,'op_precheck',"    state.started=True\n    table,chains=planned(plan)","    state.started=True;"+call+"\n    table,chains=planned(plan)")
add('K12_row_acceptance_note_wrong','op_precheck',"                          'accepted_by_the_write_operations':row_accepted(row,volume) is None,\n","                          'accepted_by_the_write_operations':True,\n")
add('K13_size_of_a_unit_file_emitted','op_precheck',"**{key:value for key,value in file_row(named).items() if key!='size'}}\n","**file_row(named)}\n")
add('K14_world_writable_note_wrong','op_precheck',"                          'world_writable_without_sticky':world_writable_without_sticky(row),\n","                          'world_writable_without_sticky':False,\n")

# ---------------------------------------------------------------- runner (provision, readback, precheck)
add('N01_command_environment_inherited','runner',"        environment=dict(COMMAND_ENVIRONMENT)\n","        environment=dict(os.environ,**COMMAND_ENVIRONMENT)\n")
add('N02_docker_config_never_passed','runner',"        if docker_config is not None:environment['DOCKER_CONFIG']=docker_config\n","")
add('N03_output_limit_removed','runner',"                        output.extend(block);need(len(output)<=MAX_COMMAND_BYTES,'COMMAND_OUTPUT_LIMIT')\n","                        output.extend(block)\n")
add('N04_untrusted_binary_accepted','runner',"                return bool(stat.S_ISREG(named.st_mode) and named.st_uid==0 and not named.st_mode&0o022 and named.st_mode&0o111)\n","                return bool(stat.S_ISREG(named.st_mode))\n")
add('N05_tool_retried_after_two_timeouts','runner',"        need(self.timeouts.get(tool,0)<MAX_TOOL_TIMEOUTS,'COMMAND_SKIPPED_AFTER_TIMEOUT')\n","")
add('N06_failed_command_output_trusted','runner',"        if code!=0:raise CommandFailed('COMMAND_FAILED',code)\n","")
add('N07_image_id_shape_unchecked','runner',"    need(set(row)=={'id','repo_tags','revision'} and text(row['id'],IMAGE_ID),'IMAGE_METADATA_INVALID')\n","    need(set(row)=={'id','repo_tags','revision'},'IMAGE_METADATA_INVALID')\n")

# ---------------------------------------------------------------- dispatcher (the changed lines) and launcher
# The date literal differs between the write and the read-only dispatchers: the anchors stop before it and start after it.
add('D01_dispatcher_date_set_dropped','dispatcher',"    need(start.date().isoformat() in ('2026-10-02',","    need(True or start.date().isoformat() in ('2026-10-02',")
add('D02_dispatcher_one_day_rule_dropped','dispatcher',"') and end.date()==start.date(),'DISPATCH_DATE')\n","'),'DISPATCH_DATE')\n")
add('D14_write_dispatcher_accepts_the_first_session_day','dispatcher_write',"('2026-10-02','2026-10-03','2026-10-04')","('2026-10-02','2026-10-03','2026-10-04','2026-10-05')")
add('D03_dispatcher_signed_date_not_tied_to_the_config_day','dispatcher'," and request.get('date')==start.date().isoformat()\n","\n")
add('D04_dispatcher_config_schema_dropped','dispatcher',"_DISPATCH_AUTHORIZATION_V1' and config.get('status')=='BOUND'\n","_DISPATCH_AUTHORIZATION_V1' or config.get('status')=='BOUND'\n")
add('D05_dispatcher_unsigned_go_accepted','dispatcher',"    need('status' not in go or go['status']=='SIGNED','GO_UNSIGNED')\n","")
add('D06_dispatcher_unsigned_authority_accepted','dispatcher',"    need('status' not in authority or authority['status']=='SIGNED','AUTHORITY_UNSIGNED')\n","")
add('D07_dispatcher_claim_root_binding_dropped','dispatcher',"    need(type(go.get('claim_root_identity')) is dict and canonical(go['claim_root_identity'])==canonical(config.get('local_root_identity')),'GO_CLAIM_ROOT_BINDING')\n","")
add('D08_dispatcher_transport_binding_dropped','dispatcher',"    need(go.get('transport_binding')==expected_transport,'GO_TRANSPORT_BINDING')\n","")
add('D09_dispatcher_host_binding_dropped','dispatcher',"    need(request.get('host_binding_sha256')==authority.get('host_binding_sha256')==go.get('host_binding_sha256')==config.get('host_binding_sha256'),'HOST_BINDING')\n","")
add('D10_dispatcher_local_authentication_dropped','dispatcher',"        clock=clock,monotonic=monotonic,executor_uid=lambda:config['executor_uid'])\n    expected=","        clock=clock,monotonic=monotonic,executor_uid=lambda:config['executor_uid']) if False else None\n    expected=")
add('D11_dispatcher_receipt_schema_not_checked','dispatcher',"_RECEIPT_V1' and receipt.get('request_sha256')==sha(blobs['request'])\n","_RECEIPT_V1' or receipt.get('request_sha256')==sha(blobs['request'])\n")
add('D12_dispatcher_late_start_accepted','dispatcher',"        gate();need(clock()<=latest_start,'WINDOW_WITH_WATCHDOG')\n        if phase=='prepare':","        gate()\n        if phase=='prepare':")
add('D13_dispatcher_claim_not_exclusive','dispatcher',"            gate();claim=os.open(claim_name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=output)\n","            gate();claim=os.open(claim_name,os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=output)\n")
add('X01_launcher_enters_the_payload_with_the_refusal_exit_code','launcher',"    exit_code=3;result=module.run(","    result=module.run(")
add('X02_launcher_maps_a_refusal_to_partial','launcher',"    exit_code={'METADATA_ONLY_REQUIRES_REVIEW':0,'REFUSED':1}.get(result.get('status'),2)\n","    exit_code={'METADATA_ONLY_REQUIRES_REVIEW':0}.get(result.get('status'),2)\n")
add('X03_launcher_maps_everything_to_complete','launcher',"    exit_code={'METADATA_ONLY_REQUIRES_REVIEW':0,'REFUSED':1}.get(result.get('status'),2)\n","    exit_code={'METADATA_ONLY_REQUIRES_REVIEW':0,'REFUSED':1}.get(result.get('status'),0)\n")
add('X04_launcher_document_pins_not_checked','launcher',"        if hashlib.sha256(raw[key]).hexdigest()!=PINS[key]:\n            raise ValueError('STDIN_DOCUMENT_PIN')\n","        if False:\n            raise ValueError('STDIN_DOCUMENT_PIN')\n")

# ---------------------------------------------------------------- second review: the layer that runs as root
# The shipped Native lines. Killed only because tests/oslevel.py records the arguments the real system calls receive;
# a test double that overrode open, fstat or lstat left all of these alive.
add('W01_native_open_strips_nofollow','core',"        return os.open(name,flags) if dir_fd is None else os.open(name,flags,dir_fd=dir_fd)\n","        flags&=~os.O_NOFOLLOW;return os.open(name,flags) if dir_fd is None else os.open(name,flags,dir_fd=dir_fd)\n")
add('W01b_native_open_ignores_the_descriptor','core',"        return os.open(name,flags) if dir_fd is None else os.open(name,flags,dir_fd=dir_fd)\n","        return os.open(name,flags)\n")
add('W02_native_lstat_follows_links','core',"    def lstat(self,name,dir_fd):return os.stat(name,dir_fd=dir_fd,follow_symlinks=False)\n","    def lstat(self,name,dir_fd):return os.stat(name,dir_fd=dir_fd,follow_symlinks=True)\n")
add('W33_native_fstat_of_another_descriptor','core',"    def fstat(self,fd):return os.fstat(fd)\n","    def fstat(self,fd):return os.stat('/')\n")
add('W32_native_identity_reports_root_unconditionally','core',"    def identity(self):return os.geteuid(),os.getegid()\n","    def identity(self):return 0,0\n")
add('W03_native_fsync_is_a_noop_in_provision','op_provision',"    def mkdir(self,name,mode,dir_fd):os.mkdir(name,mode,dir_fd=dir_fd)\n    def fsync(self,fd):os.fsync(fd)\n","    def mkdir(self,name,mode,dir_fd):os.mkdir(name,mode,dir_fd=dir_fd)\n    def fsync(self,fd):pass\n")
add('W06_native_mkdir_ignores_the_signed_mode','op_provision',"    def mkdir(self,name,mode,dir_fd):os.mkdir(name,mode,dir_fd=dir_fd)\n","    def mkdir(self,name,mode,dir_fd):os.mkdir(name,0o777,dir_fd=dir_fd)\n")
add('W20_native_mkdir_not_relative_to_the_held_descriptor','op_provision',"    def mkdir(self,name,mode,dir_fd):os.mkdir(name,mode,dir_fd=dir_fd)\n","    def mkdir(self,name,mode,dir_fd):os.mkdir(name,mode)\n")
add('W04_native_fsync_is_a_noop_in_install','op_install_units',"    def write(self,fd,data):return os.write(fd,data)\n    def fsync(self,fd):os.fsync(fd)\n","    def write(self,fd,data):return os.write(fd,data)\n    def fsync(self,fd):pass\n")
add('W05_native_link_follows_a_symlinked_temporary','op_install_units',"os.link(source,target,src_dir_fd=dir_fd,dst_dir_fd=dir_fd,follow_symlinks=False)\n","os.link(source,target,src_dir_fd=dir_fd,dst_dir_fd=dir_fd)\n")
add('W21_native_unlink_not_relative_to_the_held_descriptor','op_install_units',"    def unlink(self,name,dir_fd):os.unlink(name,dir_fd=dir_fd)\n","    def unlink(self,name,dir_fd):os.unlink(name)\n")
add('W22_native_create_strips_excl','op_install_units',"    def create(self,name,flags,mode,dir_fd):return os.open(name,flags,mode,dir_fd=dir_fd)\n","    def create(self,name,flags,mode,dir_fd):return os.open(name,flags&~os.O_EXCL,mode,dir_fd=dir_fd)\n")
add('W23_native_create_strips_nofollow','op_install_units',"    def create(self,name,flags,mode,dir_fd):return os.open(name,flags,mode,dir_fd=dir_fd)\n","    def create(self,name,flags,mode,dir_fd):return os.open(name,flags&~os.O_NOFOLLOW,mode,dir_fd=dir_fd)\n")
add('W31_native_umask_is_a_noop_in_install','op_install_units',"    def umask(self,mask):return os.umask(mask)\n","    def umask(self,mask):return 0o022\n")
add('W34_native_readlink_not_relative_to_the_held_descriptor','scan',"    def readlink(self,name,dir_fd):return os.readlink(name,dir_fd=dir_fd)\n","    def readlink(self,name,dir_fd):return os.readlink(name)\n")
# Checks the contract states and no test pinned.
add('W08_existing_directory_group_not_checked','op_provision',"        row['conforms']=bool(stat.S_ISDIR(named.st_mode) and named.st_uid==0 and named.st_gid==0\n","        row['conforms']=bool(stat.S_ISDIR(named.st_mode) and named.st_uid==0\n")
add('W09_acknowledged_leftover_identity_not_compared','op_install_units',"    scan['leftovers_acknowledged']=sorted(name for name in seen if signed.get(name)==seen[name])\n    scan['leftovers_not_acknowledged']=sorted(name for name in seen if signed.get(name)!=seen[name])\n","    scan['leftovers_acknowledged']=sorted(name for name in seen if name in signed)\n    scan['leftovers_not_acknowledged']=sorted(name for name in seen if name not in signed)\n")
add('W14_created_directory_device_not_compared_with_its_parent','op_provision',"                and stat.S_IMODE(info.st_mode)==DIRECTORY_MODE and info.st_dev==parent.identity[0]):\n","                and stat.S_IMODE(info.st_mode)==DIRECTORY_MODE):\n")
add('W15_created_file_device_not_compared_with_the_directory','op_install_units',"                    and info.st_dev==directory.identity[0]):return withdrawn('CREATED_METADATA_MISMATCH')\n","                    ):return withdrawn('CREATED_METADATA_MISMATCH')\n")
add('W18_readback_in_run_ignores_the_identity_of_the_final_name','op_install_units',"            need(raw==content and same and info.st_uid==0","            need(raw==content and info.st_uid==0")

# ---------------------------------------------------------------- second review: the conflict scan
OWN="                for suffix in DEPENDENCY_SUFFIXES:\n                    if present(name+suffix,fd) is not None:add('OWN_DEPENDENCY_DIRECTORY_PRESENT',directory,name+suffix)\n"
add('S11_own_dependency_directories_not_looked_at','scan',OWN,"")
add('S12_own_dependency_directories_only_wants','scan',OWN,OWN.replace("for suffix in DEPENDENCY_SUFFIXES:","for suffix in DEPENDENCY_SUFFIXES[:1]:"))
add('S13_alias_links_not_looked_at','scan',"                        if PurePosixPath(target).name in names:\n","                        if False:\n")
add('S14_alias_only_when_the_whole_link_text_is_the_name','scan',"                        if PurePosixPath(target).name in names:\n","                        if target in names:\n")
add('S15_alias_links_only_in_the_install_directory','scan',"                if entry.endswith(types) and entry not in names:\n","                if directory==UNIT_DIRECTORY and entry.endswith(types) and entry not in names:\n")
add('S16_unreadable_link_text_is_no_alias','scan',"                        check();target=host.readlink(entry,fd)\n","                        check()\n                        try:target=host.readlink(entry,fd)\n                        except OSError:target=''\n")
add('I43_own_dependency_directory_ignored','op_install_units',"    elif 'OWN_DEPENDENCY_DIRECTORY_PRESENT' in scan['finding_codes']:code='OWN_DEPENDENCY_DIRECTORY_PRESENT'\n","")
add('I44_alias_link_ignored','op_install_units',"    elif 'ALIAS_LINK_PRESENT' in scan['finding_codes']:code='ALIAS_LINK_PRESENT'\n","")

# ---------------------------------------------------------------- second review: unit installation
SETTLED="        settled=all(present) and all(row['links']==1 for row in rows) and not scan['leftovers_not_acknowledged'] and scan['leftover_count']<=MAX_FINDINGS\n"
add('I45_all_present_said_of_a_name_with_two_links','op_install_units',SETTLED,SETTLED.replace(" and all(row['links']==1 for row in rows)",""))
add('I46_all_present_said_beside_an_unacknowledged_temporary','op_install_units',SETTLED,SETTLED.replace(" and not scan['leftovers_not_acknowledged']",""))
LOOK="            if (named.st_dev,named.st_ino,named.st_nlink)!=(info.st_dev,info.st_ino,1):return failed('TEMPORARY_REPLACED')\n"
add('I47_temporary_not_looked_at_again_before_the_link','op_install_units',LOOK,"")
add('I48_temporary_with_a_second_link_accepted_before_the_link','op_install_units',LOOK,"            if (named.st_dev,named.st_ino)!=(info.st_dev,info.st_ino):return failed('TEMPORARY_REPLACED')\n")
WITHDRAW="        failed(code,error)\n        entry['temporary_removal_code']=remove_own_temporary(temp,fd,directory,host,gate,state,entry)\n"
add('I49_incomplete_temporary_left_behind','op_install_units',WITHDRAW,"        failed(code,error)\n")
add('I50_withdrawn_temporary_still_reported_as_left','op_install_units',"        if entry['temporary_removed']:entry['state']='NOT_CREATED'\n        return entry\n    try:directory.verify(gate)","        return entry\n    try:directory.verify(gate)")
add('I51_removal_errno_overwrites_the_errno_of_the_failure','op_install_units',"        entry['temporary_removal_errno']=number(error);return 'TEMPORARY_REMOVAL_FAILED'\n","        entry['errno']=entry['temporary_removal_errno']=number(error);return 'TEMPORARY_REMOVAL_FAILED'\n")
add('I52_digest_and_size_of_foreign_content_reported','op_install_units',"                if equal:row.update(sha256=sha(raw),size=size)\n","                if equal is not None:row.update(sha256=sha(raw),size=size)\n")
add('I53_size_of_any_object_at_a_unit_name_reported','op_install_units',"            facts=file_row(named);size=facts.pop('size');row['observed']='PRESENT';row.update(facts);equal=None\n","            facts=file_row(named);size=facts['size'];row['observed']='PRESENT';row.update(facts);equal=None\n")
add('I54_install_accepts_the_first_session_day','op_install_units',"DATES=WRITE_DATES\n","DATES=READ_DATES\n")
add('I55_install_needs_no_precheck_receipt','op_install_units',"EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)\n","EVIDENCE_OPERATIONS=()\n")

# ---------------------------------------------------------------- second review: provision and layout
TAG_LISTING="    except Exception as error:\n        # also an OS error while a process is started (no descriptor, no memory): the ledger still reaches the receipt\n"
add('P46_os_error_at_the_tag_listing_escapes_the_run','op_provision',TAG_LISTING,TAG_LISTING.replace("except Exception as error","except Refused as error"))
add('P47_os_error_at_the_listing_after_a_failed_tag_escapes','op_provision',"        except Exception:absent=False\n","        except Refused:absent=False\n")
add('P48_os_error_at_the_tag_readback_escapes','op_provision',"    except Exception as error:\n        facts['code']='TAG_READBACK_MISMATCH' if code_of(error,'')","    except Refused as error:\n        facts['code']='TAG_READBACK_MISMATCH' if code_of(error,'')")
add('P49_provision_accepts_the_first_session_day','op_provision',"DATES=WRITE_DATES\n","DATES=READ_DATES\n")
add('P50_provision_needs_no_precheck_receipt','op_provision',"EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)\n","EVIDENCE_OPERATIONS=()\n")
add('L13_world_writable_volume_row_accepted','layout',"    return 'CHAIN_ROW_WORLD_WRITABLE' if world_writable_without_sticky(row) else None\n","    return None\n")
STICKY="def world_writable_without_sticky(row):return bool(row['mode']&0o002) and not row['mode']&stat.S_ISVTX\n"
add('L14_sticky_bit_not_considered','layout',STICKY,"def world_writable_without_sticky(row):return bool(row['mode']&0o002)\n")
add('L14b_group_writable_counted_as_world_writable','layout',STICKY,STICKY.replace("0o002","0o022"))
add('L15_parameter_may_be_a_fixed_path_or_above_one','layout',"            and not any(inside(fixed,value) for fixed in FIXED_PATHS)\n","")
add('L15b_parameter_may_be_above_a_fixed_path','layout',"            and not any(inside(fixed,value) for fixed in FIXED_PATHS)\n","            and value not in FIXED_PATHS\n")
add('L16_composed_journal_path_not_checked','layout',"        need(open_path(volume+'/'+leaf),'PATH_FORBIDDEN_ZONE')         # the composed path, not only its two halves\n","")
FACTS="    return {'world_writable_without_sticky':world_writable_without_sticky(rows[-1]),'device_differs_from_parent':rows[-1]['device']!=rows[-2]['device']}\n"
add('L17_volume_root_always_shown_as_a_mount_point','layout',FACTS,FACTS.replace("rows[-1]['device']!=rows[-2]['device']","True"))
add('L18_volume_root_writability_not_shown','layout',FACTS,FACTS.replace("world_writable_without_sticky(rows[-1])","False"))

# ---------------------------------------------------------------- second review: readback
add('B69_load_state_never_a_finding','op_readback',"        if values['LoadState'] in BAD_LOAD_STATES:findings.append('UNIT_LOAD_STATE')\n","")
add('B69b_masked_is_no_finding','op_readback',"BAD_LOAD_STATES=('bad-setting','error','masked')\n","BAD_LOAD_STATES=('bad-setting','error')\n")
COUNTED="            if value.get('exists') is not True or value.get('type')!='file' or value.get('uid')!=0:return False\n"
add('B70_any_object_counts_as_the_init_binary','op_readback',COUNTED,"            if value.get('exists') is not True:return False\n            return True\n")
add('B70b_init_binary_of_any_type','op_readback',COUNTED,COUNTED.replace(" or value.get('type')!='file'",""))
add('B70c_init_binary_of_any_owner','op_readback',COUNTED,COUNTED.replace(" or value.get('uid')!=0",""))
MODE="            mode=int(value['mode_octal'],8);return not mode&0o022 and bool(mode&0o111)\n"
add('B70d_init_binary_writable_by_others','op_readback',MODE,"            mode=int(value['mode_octal'],8);return bool(mode&0o111)\n")
add('B70e_init_binary_not_executable','op_readback',MODE,"            mode=int(value['mode_octal'],8);return not mode&0o022\n")
add('B71_foreign_entry_in_the_configuration_directory_ignored','op_readback',TOKEN_FINDINGS,"            regular=stat.S_ISREG(named.st_mode);findings=[]\n")
add('B71b_configuration_directory_not_counted_without_a_token','op_readback',"(['CONFIG_DIRECTORY_ENTRIES'] if entries!=2 else [])","[]")
add('B72_revision_of_the_pinned_image_not_compared','op_readback',"            if not extra['revision_equal_signed']:findings.append('IMAGE_REVISION_MISMATCH')\n","")
add('B73_revision_unbound_accepted','op_readback',"    need(text(plan['image_revision'],'[0-9a-f]{40}'),'IMAGE_REVISION_UNBOUND')\n","")
add('B74_production_flag_always_true','op_readback',"listed=PRODUCTION_REFERENCE in facts['repo_tags']\n","listed=True\n")
add('B74b_production_flag_false_when_the_tag_list_was_cut','op_readback',"True if listed else False if facts['repo_tag_count']==len(facts['repo_tags']) else None","bool(listed)")
PAIRS="            'layout':{key:pair(plan['layout'][key]) for key in LAYOUT_KEYS},'data_volume_rows':plan['data_volume']['rows'],\n"
add('B75_layout_identities_not_bound_into_the_go','op_readback',PAIRS,PAIRS.replace("{key:pair(plan['layout'][key]) for key in LAYOUT_KEYS}","{}"))
add('B75b_data_volume_rows_not_bound_into_the_go','op_readback',PAIRS,PAIRS.replace("plan['data_volume']['rows']","[]"))
HEAD="    return {'unit_directory':plan['unit_directory'],'service':pair(plan['service']),'timer':pair(plan['timer']),\n"
add('B75c_unit_directory_rows_not_bound_into_the_go','op_readback',HEAD,HEAD.replace("plan['unit_directory']","[]"))
add('B75d_unit_file_identities_not_bound_into_the_go','op_readback',HEAD,HEAD.replace("pair(plan['service'])","{}").replace("pair(plan['timer'])","{}"))
add('B75e_catalog_identity_not_bound_into_the_go','op_readback',"            'catalog':pair(plan['catalog'])}\n","            'catalog':{}}\n")
add('B76_device_dropped_from_bound_identities','op_readback',"    pair=lambda item:{'device':item['device'],'inode':item['inode']}\n","    pair=lambda item:{'inode':item['inode']}\n")
add('B77_bytes_above_the_floor_misreported','op_readback',"bytes_above_signed_floor=available-floor,","bytes_above_signed_floor=abs(available-floor),")

# ---------------------------------------------------------------- second review: what the GO shows, how the gate is bounded
add('C17b_request_max_seconds_type_unchecked','core',SCOPE,SCOPE.replace("type(request['max_seconds']) is int and ",""))
add('C71b_precheck_receipt_not_required_among_the_evidence','core',"    need(all(any(item['operation']==name for item in evidence) for name in EVIDENCE_OPERATIONS),'EVIDENCE_PRECHECK_MISSING')\n","")
add('C77_effects_compared_between_the_two_documents_only','core',EFF,"         and canonical(authority['effects'])==canonical(go['effects']),'EFFECTS_BINDING')\n")
BOUNDS="    start,end=max(starts),min(ends)\n"
add('C78_gate_ends_with_the_go_window_only','core',BOUNDS,"    start,end=max(starts),ends[2]\n")
add('C78b_gate_ends_with_the_request_window_only','core',BOUNDS,"    start,end=max(starts),ends[0]\n")
add('C78c_gate_ends_with_the_authority_window_only','core',BOUNDS,"    start,end=max(starts),ends[1]\n")
add('C78d_gate_starts_with_the_go_window_only','core',BOUNDS,"    start,end=starts[2],min(ends)\n")
add('C78e_gate_starts_with_the_request_window_only','core',BOUNDS,"    start,end=starts[0],min(ends)\n")
add('C78f_gate_starts_with_the_authority_window_only','core',BOUNDS,"    start,end=starts[1],min(ends)\n")
add('C78g_gate_takes_the_widest_window','core',BOUNDS,"    start,end=min(starts),max(ends)\n")
DAY="    need(all(point.date().isoformat()==request['date'] for point in starts+ends),'DATE_WINDOW_MISMATCH')\n"
add('C79_only_the_ends_must_lie_on_the_signed_day','core',DAY,DAY.replace("in starts+ends","in ends"))
add('C79b_only_the_starts_must_lie_on_the_signed_day','core',DAY,DAY.replace("in starts+ends","in starts"))
PLAN_WINDOW="    need(instant(plan['window']['not_before'])==starts[0] and instant(plan['window']['expires_at'])==ends[0],'PLAN_WINDOW')\n"
add('C80_plan_window_start_not_tied_to_the_request','core',PLAN_WINDOW,"    need(instant(plan['window']['expires_at'])==ends[0],'PLAN_WINDOW')\n")
add('C80b_plan_window_end_not_tied_to_the_request','core',PLAN_WINDOW,"    need(instant(plan['window']['not_before'])==starts[0],'PLAN_WINDOW')\n")
add('C81_transport_binding_keys_not_exact','core',"    need(type(binding) is dict and set(binding)=={'target','remote_command','command_sha256','runtime_sha256'}\n","    need(type(binding) is dict and set(binding)>={'target','remote_command','command_sha256','runtime_sha256'}\n")
ROOT="    need(type(root) is dict and set(root)=={'path','device','inode'} and type(root['path']) is str and root['path'].startswith('/')\n         and integer(root['device']) and integer(root['inode'],1),'GO_CLAIM_ROOT_UNBOUND')\n"
add('C82_claim_root_keys_not_exact','core',ROOT,ROOT.replace("set(root)=={'path','device','inode'}","set(root)>={'path','device','inode'}"))
add('C83_claim_root_path_unchecked','core',ROOT,ROOT.replace(" and type(root['path']) is str and root['path'].startswith('/')",""))
add('C83b_claim_root_path_may_be_relative','core',ROOT,ROOT.replace(" and root['path'].startswith('/')",""))
add('C84_claim_root_device_and_inode_unchecked','core',ROOT,ROOT.replace("\n         and integer(root['device']) and integer(root['inode'],1)",""))
add('C84b_claim_root_device_unchecked','core',ROOT,ROOT.replace("integer(root['device']) and ",""))
add('C84c_claim_root_inode_unchecked','core',ROOT,ROOT.replace(" and integer(root['inode'],1)",""))

# ---------------------------------------------------------------- the journal placement (supervisor README at a6dd2b1)
# The installer audit's A_F (journal coupling), A_H (state/config overlap), R02 and R03 are now these, one per rule.
add('A_H_state_config_overlap_allowed','render',"    need(not overlaps(state,config),'PRIVATE_PATH_OVERLAP')\n","")
add('R03_data_inside_private_allowed','render',"    need(not any(private in volume.parents for private in (state,config)),'DATA_INSIDE_PRIVATE')\n","")
add('PL00_unknown_placement_treated_as_b','render',"    need(type(placement) is str and placement in PLACEMENTS,'PLACEMENT_UNKNOWN')\n    volume=safe_path(data_volume)","    volume=safe_path(data_volume)")
add('PL01_host_journal_may_overlap_a_private_root','render',"    need(not any(overlaps(journal,private) for private in (state,config)),'HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT')\n","")
add('PL02_container_journal_may_overlap_a_fixed_target','render',"    need(not any(overlaps(container,PurePosixPath(target)) for target in FIXED_TARGETS),'CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET')\n","")
add('R02_private_root_inside_the_data_volume_allowed','render',"    need(not any(within(private,volume) for private in (state,config)),'PRIVATE_ROOT_INSIDE_DATA_VOLUME')\n","")
add('PL04_a_host_journal_inside_the_data_volume','render',"        need(not within(journal,volume),'A_HOST_JOURNAL_INSIDE_DATA_VOLUME')\n","")
add('PL05_a_host_journal_inside_the_deploy_tree','render',"        need(not within(journal,tree),'A_HOST_JOURNAL_INSIDE_DEPLOY_TREE')\n","")
add('PL06_a_container_journal_deeper_than_one_component','render',"        need(len(container.parts)==2,'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL')\n","")
add('PL07_a_container_journal_on_a_provided_directory','render',"        need(container.name not in PROVIDED_TOP_LEVEL,'A_CONTAINER_JOURNAL_PROVIDED_DIRECTORY')\n","")
add('PL07b_app_not_among_the_provided_directories','render',"PROVIDED_TOP_LEVEL=('app','bin',","PROVIDED_TOP_LEVEL=('bin',")
add('PL08_a_deploy_tree_not_required','render',"        need(type(deploy_tree) is str,'DEPLOY_TREE_PATH');tree=safe_path(deploy_tree)\n","        tree=safe_path(deploy_tree) if type(deploy_tree) is str else PurePosixPath('/nonexistent-deploy-tree')\n")
add('PL09_b_signs_a_deploy_tree','render',"        need(deploy_tree is None,'DEPLOY_TREE_PATH')\n","")
add('A_F_journal_coupling_removed','render',"        need(journal.parent==volume,'B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME')\n","")
add('PL11_b_container_journal_not_the_same_leaf','render',"        need(container==PurePosixPath(CONTAINER_DATA)/journal.name,'B_CONTAINER_JOURNAL_NOT_THE_SAME_LEAF')\n","")
add('PL12_within_does_not_include_the_tree_itself','render',"def within(path,tree):return path==tree or tree in path.parents\n","def within(path,tree):return tree in path.parents\n")
add('PL13_overlap_only_downwards','render',"def overlaps(one,other):return one==other or one in other.parents or other in one.parents\n","def overlaps(one,other):return one==other or other in one.parents\n")
add('PL14_overlap_only_upwards','render',"def overlaps(one,other):return one==other or one in other.parents or other in one.parents\n","def overlaps(one,other):return one==other or one in other.parents\n")
add('I38_data_volume_coupling_rule_removed','op_install_units',"    need((volume is not None)==supervisor,'DATA_VOLUME_PATH')\n","")
add('I56_placement_signed_without_a_supervisor_unit','op_install_units',"    need(supervisor or (placement is None and tree is None),'PLACEMENT_UNKNOWN')\n","")
add('I57_units_rendered_without_the_signed_placement','op_install_units',"        render_unit(unit,plan['network_allowlist'],volume,placement,tree);total+=len(decode_template(unit))\n","        render_unit(unit,plan['network_allowlist'],volume,'B' if supervisor else None,None);total+=len(decode_template(unit))\n")
PLACEMENT="    if 'JOURNAL_LEAF' in groups:need(type(placement) is str and placement in JOURNAL_PLACEMENTS,'PLACEMENT_UNKNOWN')\n    else:need(placement is None,'PLACEMENT_UNKNOWN')\n"
add('L19_placement_of_the_layout_unchecked','layout',PLACEMENT,"")
add('L19b_placement_signed_without_a_journal_group','layout',PLACEMENT,PLACEMENT.replace("    else:need(placement is None,'PLACEMENT_UNKNOWN')\n",""))
add('L20_placement_a_leaf_may_be_the_state_root','layout',"        need(leaf_name(leaf) and SUP_STATE_PARENT+'/'+leaf!=SUP_STATE,'LEAF_INVALID')","        need(leaf_name(leaf),'LEAF_INVALID')")
add('L21_placement_a_parent_never_pinned_by_its_own_chain','layout',"{'entry':'SUP_STATE_PARENT'} if 'SUPERVISOR' in groups else {'chain':'SUP_STATE_PARENT'})","{'entry':'SUP_STATE_PARENT'})")
add('L22_data_volume_signed_under_placement_a_without_need','layout',"    if placement=='B' or 'CAPACITY' in groups:\n","    if placement in ('A','B') or 'CAPACITY' in groups:\n")
add('L23_placement_a_journal_created_in_the_data_volume','layout',"    if 'JOURNAL_LEAF' in groups and placement=='A':\n","    if False:\n")
add('P51_directory_on_another_filesystem_conforms','op_provision',"and stat.S_IMODE(named.st_mode)==DIRECTORY_MODE and named.st_dev==parent.identity[0])\n","and stat.S_IMODE(named.st_mode)==DIRECTORY_MODE)\n")
MOUNT="        if row['device']!=previous['device']:point=row['path']\n"
add('E19_mount_point_always_the_root','core',MOUNT,"        pass\n")
add('E19b_mount_point_one_component_too_high','core',MOUNT,"        if row['device']!=previous['device']:point=previous['path']\n")
VALUES_FINDINGS="        findings=([] if extracted==self.values else ['VALUES_MISMATCH'])+([] if conform else ['PLACEMENT_MISMATCH'])\n"
add('B23_values_on_disk_not_compared','op_readback',VALUES_FINDINGS,"        findings=[]+([] if conform else ['PLACEMENT_MISMATCH'])\n")
add('B23b_placement_of_the_values_on_disk_not_judged','op_readback',VALUES_FINDINGS,"        findings=([] if extracted==self.values else ['VALUES_MISMATCH'])\n")
add('B23c_placement_of_the_values_on_disk_judged_as_b','op_readback',"            placement_rules(extracted,self.plan['data_volume']['path'],placement,self.plan['deploy_tree_path'])\n","            placement_rules(extracted,self.plan['data_volume']['path'],'B',None)\n")
OWN="                if own:findings.append('JOURNAL_ROOT_IS_A_MOUNT_POINT')\n                elif point!=signed_point:findings.append('JOURNAL_FILESYSTEM_MISMATCH')\n"
add('B34_journal_root_as_a_mount_point_ignored','op_readback',OWN,"                if point!=signed_point and not own:findings.append('JOURNAL_FILESYSTEM_MISMATCH')\n")
add('B34b_filesystem_other_than_the_signed_one_ignored','op_readback',OWN,"                if own:findings.append('JOURNAL_ROOT_IS_A_MOUNT_POINT')\n")
add('B34c_mount_point_echoed_from_the_request','op_readback',"                point=mount_point_of(chain);own=chain[-1]['device']!=chain[-2]['device']\n","                point=signed_point;own=chain[-1]['device']!=chain[-2]['device']\n")
add('B78_data_volume_rows_signed_under_placement_a','op_readback',"    else:need(volume['rows'] is None,'DATA_VOLUME_INVALID')\n","    else:pass\n")
add('B79_data_volume_rows_unchecked_under_placement_b','op_readback',"    if placement=='B':chain_rows(volume['rows'],volume['path'])\n","    if placement=='B':pass\n")
add('B80_data_volume_read_under_placement_a','op_readback',"        if self.plan['journal_placement']!='B':\n","        if False:\n")
POINT="    need(type(point) is str and (point=='/' or clean_path(point)),'JOURNAL_MOUNT_POINT_UNBOUND')\n"
add('B81_mount_point_unbound_accepted','op_readback',POINT,"")
add('B82_mount_point_not_above_the_journal_root','op_readback',"    need(inside(plan['substitutions']['HOST_JOURNAL_ROOT'],point) and point!=plan['substitutions']['HOST_JOURNAL_ROOT'],'JOURNAL_MOUNT_POINT_UNBOUND')\n","")
add('B82b_mount_point_may_be_the_journal_root_itself','op_readback'," and point!=plan['substitutions']['HOST_JOURNAL_ROOT'],'JOURNAL_MOUNT_POINT_UNBOUND')",",'JOURNAL_MOUNT_POINT_UNBOUND')")

# ---------------------------------------------------------------- third review: guards no test pinned, and redundant guards
# The third review ran 117 mutants of its own; nine survived. Two were guards nothing pinned (T01, T02). Five are guards
# a second check would also have caught, later and with another result (T03 to T07): each now has a test of the case
# in which it decides. Two cannot change any result while the other check of their pair stands (T09 with T08, T10
# with E07): they are listed in REDUNDANT, run alone for the record, and die in the combined mutant of their pair.
add('T01_tag_readback_does_not_need_the_reference','op_provision',"        need(facts['readback_id_equal'] and image['reference_among_repo_tags'],'TAG_READBACK_MISMATCH')\n","        need(facts['readback_id_equal'],'TAG_READBACK_MISMATCH')\n")
CONFORMS="            conforms=bool(equal and named.st_uid==0 and named.st_gid==0 and stat.S_IMODE(named.st_mode)==UNIT_MODE)\n"
add('T02_unit_file_group_not_checked_in_the_precheck','op_install_units',CONFORMS,CONFORMS.replace(" and named.st_gid==0",""))
add('T02b_unit_file_owner_not_checked_in_the_precheck','op_install_units',CONFORMS,CONFORMS.replace(" and named.st_uid==0",""))
add('T03_created_file_link_count_not_checked','op_install_units',"            if not (stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==0 and info.st_gid==0\n","            if not (stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_gid==0\n")
add('T04_created_file_size_not_checked','op_install_units',"                    and stat.S_IMODE(info.st_mode)==UNIT_MODE and info.st_size==len(content)\n","                    and stat.S_IMODE(info.st_mode)==UNIT_MODE\n")
IN_RUN="            need(raw==content and same and info.st_uid==0 and info.st_gid==0 and stat.S_IMODE(info.st_mode)==UNIT_MODE\n"
add('T05_in_run_readback_mode_not_checked','op_install_units',IN_RUN,IN_RUN.replace(" and stat.S_IMODE(info.st_mode)==UNIT_MODE",""))
add('T05b_in_run_readback_owner_not_checked','op_install_units',IN_RUN,IN_RUN.replace(" and info.st_uid==0",""))
add('T05c_in_run_readback_group_not_checked','op_install_units',IN_RUN,IN_RUN.replace(" and info.st_gid==0",""))
add('T05d_in_run_readback_link_count_not_checked','op_install_units',"                 and (info.st_nlink==1 or entry['state']!='INSTALLED_DURABLE'),'READBACK_HASH_MISMATCH')\n","                 ,'READBACK_HASH_MISMATCH')\n")
add('T06_link_count_after_the_removal_of_the_temporary_not_checked','op_install_units',"        if entry['links']!=1:return failed('CREATED_METADATA_MISMATCH')\n","")
add('T07_walk_does_not_compare_the_lstat_with_the_descriptor','core',"                host.close(fd);fd=child;info=host.fstat(fd)\n                need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'PARENT_CHANGED_DURING_WALK')\n","                host.close(fd);fd=child;info=host.fstat(fd)\n")
add('T08_clean_ignores_uncertain_calls','core',"    def clean(self):return self.succeeded==0 and self.uncertain()==0\n","    def clean(self):return self.succeeded==0\n")
add('T09_escape_with_a_pending_call_not_looked_at','core',"        nothing=(not state.started) or (WRITES_ALLOWED and state.clean() and not state.pending)\n","        nothing=(not state.started) or (WRITES_ALLOWED and state.clean())\n")
add('T10_verify_does_not_compare_the_fresh_walk_with_the_descriptor_held','core',"                try:need(self.stamp(self.host.fstat(other))==self.identity,'PARENT_REPLACED')\n","                try:pass\n")

# One mutant per member of what the signed GO shows: effects_of() without that member. EFFECTS is also read by
# mutate.py check, which fails when a source's effects have a member that is not listed here.
EFFECTS={
 'provision':{'top':['operation','groups','data_volume_path','journal_leaf','existing_journal_leaves','capacity','creates','directories_to_create','direct_parents','chains_sha256',
                     'data_volume_root','retention_tag','evidence_boot_id_sha256','files_created','pre_existing_objects_modified','daemon_reload','activation','journal'],
              'nested':{'creates':['key','path','mode_octal','expect'],'retention_tag':['reference','image_id','expect'],
                        'journal':['placement','path','filesystem_named_by_chain','filesystem_device','mount_point_by_device_change','data_volume_touched_for_the_journal'],
                        'capacity':['root_path','receipt_directory_path','receipts_inside_capacity_root'],
                        'data_volume_root':['world_writable_without_sticky','device_differs_from_parent'],'direct_parents':['DATA_VOLUME','ETC','VAR_LIB']}},
 'install_units':{'top':['operation','directory','directory_row','chain_sha256','units','files_to_create','network_allowlist','data_volume_path','template_revision',
                         'acknowledged_leftovers','evidence_boot_id_sha256','daemon_reload','external_processes','pre_existing_objects_modified','activation',
                         'journal_placement','deploy_tree_path'],
                  'nested':{'units':['destination_name','mode_octal','profile','template_sha256','rendered_sha256','rendered_bytes','substitutions','expect'],
                            'daemon_reload':['performed_by_this_operation','owner'],'directory_row':['path','device','inode','uid','gid','mode']}},
 'readback':{'top':['operation','mode','install_receipt_sha256','install_outcome','provision_receipt_sha256','evidence_boot_id_sha256','units','substitutions',
                    'network_allowlist','layout_paths','data_volume_path','token_path','image_id','image_revision','retention_reference','free_space_floor_bytes',
                    'sessions_retained','other_writers_allowance_bytes','unit_directory_row','data_volume_root_row','identities_sha256','catalog',
                    'gates_activation_readback','writes','activation','journal_placement','journal_mount_point','deploy_tree_path','data_volume_read'],
             'nested':{'catalog':['expected','receipt_sha256'],'units':['c3po-massive.service','c3po-massive.timer'],
                       'substitutions':['IMAGE_ID','HOST_JOURNAL_ROOT','CONTAINER_JOURNAL_ROOT','HOST_STATE_ROOT','HOST_CONFIG_DIR','NETWORK'],
                       'layout_paths':['SUP_CONFIG','SUP_MANIFESTS','SUP_DOCKER_CLI','SUP_STATE_PARENT','SUP_STATE','SUP_JOURNAL'],
                       'unit_directory_row':['path','device','inode','uid','gid','mode'],'data_volume_root_row':['path','device','inode','uid','gid','mode']}},
 'precheck':{'top':['operation','journal_placement','existing_journal_leaves','chains','destinations','unit_names','secret_bearing_names','presence_only','image_reference','writes','activation'],
             'nested':{'chains':['ETC','VAR_LIB','DATA_VOLUME','UNIT_DIRECTORY']}},
}
HEADER="def effects_of(plan):\n"
for _op,_spec in EFFECTS.items():
    for _key in _spec['top']:
        add('EF_%s__%s'%(_op,_key),'op_'+_op,HEADER,HEADER+"    value=_effects_complete(plan);value.pop(%r);return value\ndef _effects_complete(plan):\n"%_key)
    for _key,_members in _spec['nested'].items():
        for _member in _members:
            add('EF_%s__%s__%s'%(_op,_key,_member),'op_'+_op,HEADER,HEADER+
                ("    value=_effects_complete(plan);target=value[%r]\n    for item in (target if type(target) is list else [target]):\n"
                 "        if type(item) is dict:item.pop(%r,None)\n    return value\ndef _effects_complete(plan):\n")%(_key,_member))

MUTANTS=M

# Single mutants that cannot change any result while another check stands: the other check implies them. Each is run
# alone and recorded (it is expected to survive alone; that is what "redundant" means and it is never counted as a
# kill), and each must be a member of a combined mutant that removes the other check too, which must die.
REDUNDANT={
 'T09_escape_with_a_pending_call_not_looked_at':'a pending call is issued and not settled: Effects.uncertain() is then at least 1 and clean() is already false (T08)',
 'T10_verify_does_not_compare_the_fresh_walk_with_the_descriptor_held':'the fresh walk already requires every component to equal its signed row on device, inode, owner, group and mode (E07), and the identity held was read from a descriptor that passed the same walk',
}

# One guarantee removed at every layer that carries it.
COMBOS={
 'combo_date_set_both_layers':['C52_date_set_dropped','D01_dispatcher_date_set_dropped'],
 'combo_signed_date_both_layers':['C53_request_date_not_tied_to_the_windows','D03_dispatcher_signed_date_not_tied_to_the_config_day','D02_dispatcher_one_day_rule_dropped'],
 'combo_unsigned_go_both_layers':['C32_go_status_dropped','D05_dispatcher_unsigned_go_accepted'],
 'combo_unsigned_authority_both_layers':['C23_authority_status_dropped','D06_dispatcher_unsigned_authority_accepted'],
 'combo_host_binding_both_layers':['C46b_host_binding_equalities_dropped','D09_dispatcher_host_binding_dropped'],
 'combo_path_grammar_and_components':['A_A_path_grammar_widened','A_B_component_check_removed'],
 'combo_excl_and_precheck':['A_M01_create_without_excl','I12_unacknowledged_leftover_ignored'],
 'combo_reconciliation_exit_zero':['B10_reconciliation_takes_the_gate_branch','B11_reconciliation_without_its_mandatory_finding'],
 'combo_refusal_after_mutation_all_layers':['P22_refused_after_a_creation','E04_escaped_exception_always_a_refusal'],
 'combo_window_gate_both_checks':['C58_gate_initial_window_dropped','C59_gate_wall_window_dropped'],
 # second review: one guarantee, both layers or both rules
 'combo_first_session_day_for_provision_both_layers':['P49_provision_accepts_the_first_session_day','D14_write_dispatcher_accepts_the_first_session_day'],
 'combo_first_session_day_for_install_both_layers':['I54_install_accepts_the_first_session_day','D14_write_dispatcher_accepts_the_first_session_day'],
 'combo_parameter_above_the_fixed_layout_both_rules':['L15_parameter_may_be_a_fixed_path_or_above_one','L16_composed_journal_path_not_checked'],
 'combo_own_dependency_directory_scan_and_precedence':['S11_own_dependency_directories_not_looked_at','I43_own_dependency_directory_ignored'],
 'combo_alias_scan_and_precedence':['S13_alias_links_not_looked_at','I44_alias_link_ignored'],
 'combo_temporary_swap_both_looks':['I47_temporary_not_looked_at_again_before_the_link','I03_temporary_removed_without_identity_proof'],
 # third review: one combined mutant per pair of checks of which one would also have caught what the other catches
 'combo_r3_escape_with_a_pending_call_both_checks':['T09_escape_with_a_pending_call_not_looked_at','T08_clean_ignores_uncertain_calls'],
 'combo_r3_verify_fresh_walk_and_signed_rows':['T10_verify_does_not_compare_the_fresh_walk_with_the_descriptor_held','E07_chain_rows_not_compared'],
 'combo_r3_walk_lstat_and_signed_rows':['T07_walk_does_not_compare_the_lstat_with_the_descriptor','E07_chain_rows_not_compared'],
 'combo_r3_link_count_of_the_temporary_both_looks':['T03_created_file_link_count_not_checked','I48_temporary_with_a_second_link_accepted_before_the_link'],
 'combo_r3_size_at_creation_and_bytes_in_the_readback':['T04_created_file_size_not_checked','I26_readback_does_not_compare_bytes'],
 'combo_r3_mode_at_creation_and_in_the_readback':['T05_in_run_readback_mode_not_checked','I20_created_file_metadata_not_checked'],
 'combo_r3_link_count_after_the_removal_and_in_the_readback':['T06_link_count_after_the_removal_of_the_temporary_not_checked','T05d_in_run_readback_link_count_not_checked'],
}
