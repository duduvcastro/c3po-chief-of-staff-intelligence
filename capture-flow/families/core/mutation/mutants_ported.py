"""Mutants of HOSTOPS01 that apply unchanged to the HOSTOPS02 core: the same anchor occurs exactly once in every source
that carries the part. Generated once from the sealed HOSTOPS01 list (mutation/mutants.py, sha256 6954ce2f...d9df) by
copying each row whose anchor still applies; nothing here is read from HOSTOPS01 at run time. Targets: core, runner,
docker and files are parts of this core (hostops01's installer and provisioner bodies became parts/files.py);
dispatcher, dispatcher_write and launcher are the generated runtime files."""
PORTED=[('A_M01_create_without_excl', 'files', 'flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC\n', 'flags=os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC\n'),
 ('A_M04_create_without_nofollow', 'files', 'flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC\n', 'flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC\n'),
 ('A_M05_create_without_excl_and_nofollow', 'files', 'flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC\n', 'flags=os.O_WRONLY|os.O_CREAT|os.O_CLOEXEC\n'),
 ('A_M06_file_fsync_dropped', 'files', "        try:host.fsync(fd);entry['fsync_file']=True\n", "        try:entry['fsync_file']=True\n"),
 ('A_M07a_directory_fsync_after_mkdir_dropped', 'files', "        host.fsync(fd);entry['fsync_directory']=True\n", "        entry['fsync_directory']=True\n"),
 ('A_M07b_parent_fsync_after_mkdir_dropped', 'files', "        host.fsync(parent.fd);entry['fsync_parent']=True\n", "        entry['fsync_parent']=True\n"),
 ('A_M07c_directory_fsync_after_link_dropped', 'files', "        try:host.fsync(directory.fd);entry['fsync_directory_after_link']=True\n", "        try:entry['fsync_directory_after_link']=True\n"),
 ('A_M07d_directory_fsync_after_removal_dropped', 'files', "    try:host.fsync(directory.fd);entry['fsync_directory_after_removal']=True\n", "    try:entry['fsync_directory_after_removal']=True\n"),
 ('A_M08_chain_walk_without_nofollow',
  'core',
  '    Observed rows are appended as they are read, so a refusal carries what was seen. Returns the last descriptor."""\n    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()\n',
  '    Observed rows are appended as they are read, so a refusal carries what was seen. Returns the last descriptor."""\n    flags=os.O_RDONLY|os.O_DIRECTORY|host.noatime()\n'),
 ('A_M10a_parent_not_verified_before_mkdir', 'files', "    try:parent.verify(gate)\n    except Refused as error:\n        entry['code']=code_of(error,'PARENT_REPLACED');return entry\n", ''),
 ('A_M10b_directory_not_verified_before_temporary', 'files', "    try:directory.verify(gate)\n    except Refused as error:return failed(code_of(error,'PARENT_REPLACED'))\n    flags=", '    flags='),
 ('A_M10c_directory_not_verified_before_link',
  'files',
  "        try:directory.verify(gate)\n        except Refused as error:return failed(code_of(error,'PARENT_REPLACED'))\n        # link() acts on the name,",
  '        # link() acts on the name,'),
 ('A_M11_excl_replaced_by_trunc', 'files', 'flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC\n', 'flags=os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW|os.O_CLOEXEC\n'),
 ('A_M14_chain_row_device_not_compared',
  'core',
  "    fields=('device','inode','uid','gid','mode') if compare_device else ('inode','uid','gid','mode')\n",
  "    fields=('inode','uid','gid','mode') if compare_device else ('inode','uid','gid','mode')\n"),
 ('A_M14_chain_row_inode_not_compared',
  'core',
  "    fields=('device','inode','uid','gid','mode') if compare_device else ('inode','uid','gid','mode')\n",
  "    fields=('device','uid','gid','mode') if compare_device else ('inode','uid','gid','mode')\n"),
 ('A_M14_chain_row_uid_not_compared',
  'core',
  "    fields=('device','inode','uid','gid','mode') if compare_device else ('inode','uid','gid','mode')\n",
  "    fields=('device','inode','gid','mode') if compare_device else ('inode','uid','gid','mode')\n"),
 ('A_M14_chain_row_gid_not_compared',
  'core',
  "    fields=('device','inode','uid','gid','mode') if compare_device else ('inode','uid','gid','mode')\n",
  "    fields=('device','inode','uid','mode') if compare_device else ('inode','uid','gid','mode')\n"),
 ('A_M14_chain_row_mode_not_compared',
  'core',
  "    fields=('device','inode','uid','gid','mode') if compare_device else ('inode','uid','gid','mode')\n",
  "    fields=('device','inode','uid','gid') if compare_device else ('inode','uid','gid','mode')\n"),
 ('A_M17b_fchmod_of_a_created_file', 'files', "        try:host.fsync(fd);entry['fsync_file']=True\n", "        try:os.fchmod(fd,0o644);host.fsync(fd);entry['fsync_file']=True\n"),
 ('A_M17c_fchown_of_a_created_file', 'files', "        entry['bytes']=written\n", "        entry['bytes']=written;os.fchown(fd,os.geteuid(),os.getegid())\n"),
 ('A_M17d_fchmod_of_a_created_directory',
  'files',
  "    entry['state']='CREATED_UNVERIFIED'\n    try:fd=host.open(name,flags,dir_fd=parent.fd)\n",
  "    entry['state']='CREATED_UNVERIFIED'\n    try:fd=host.open(name,flags,dir_fd=parent.fd);os.fchmod(fd,0o700)\n"),
 ('C01_pin_not_compared_with_bytes',
  'core',
  "        need(hexpin(pin) and type(data) is bytes and sha(data)==pin,'PIN_MISMATCH')\n",
  "        need(hexpin(pin) and type(data) is bytes,'PIN_MISMATCH')\n"),
 ('C02_non_canonical_document_accepted', 'core', "    value=decode(raw);need(canonical(value)==raw,'DOCUMENT_NOT_CANONICAL');return value\n", '    value=decode(raw);return value\n'),
 ('C03_duplicate_key_accepted', 'core', "            need(key not in result,'DUPLICATE_KEY');result[key]=value\n", '            result[key]=value\n'),
 ('C04_request_keys_not_exact',
  'core',
  "    exact(request,REQUEST_KEYS,'REQUEST_KEYS');exact(authority,AUTHORITY_KEYS,'AUTHORITY_KEYS');exact(go,GO_KEYS,'GO_KEYS')\n",
  "    exact(authority,AUTHORITY_KEYS,'AUTHORITY_KEYS');exact(go,GO_KEYS,'GO_KEYS')\n"),
 ('C05_authority_keys_not_exact',
  'core',
  "    exact(request,REQUEST_KEYS,'REQUEST_KEYS');exact(authority,AUTHORITY_KEYS,'AUTHORITY_KEYS');exact(go,GO_KEYS,'GO_KEYS')\n",
  "    exact(request,REQUEST_KEYS,'REQUEST_KEYS');exact(go,GO_KEYS,'GO_KEYS')\n"),
 ('C06_go_keys_not_exact',
  'core',
  "    exact(request,REQUEST_KEYS,'REQUEST_KEYS');exact(authority,AUTHORITY_KEYS,'AUTHORITY_KEYS');exact(go,GO_KEYS,'GO_KEYS')\n",
  "    exact(request,REQUEST_KEYS,'REQUEST_KEYS');exact(authority,AUTHORITY_KEYS,'AUTHORITY_KEYS')\n"),
 ('C07_extra_key_accepted', 'core', '    need(type(value) is dict and set(value)==set(keys),code);return value\n', '    need(type(value) is dict and set(value)>=set(keys),code);return value\n'),
 ('C08_request_schema_dropped', 'core', "    need(request['schema']==REQUEST_SCHEMA and request['status']=='BOUND'\n", "    need(request['status']=='BOUND'\n"),
 ('C09_request_status_dropped', 'core', "    need(request['schema']==REQUEST_SCHEMA and request['status']=='BOUND'\n", "    need(request['schema']==REQUEST_SCHEMA\n"),
 ('C10_request_operation_dropped', 'core', "         and request['operation']==OPERATION and request['phase']==PHASE\n", "         and request['phase']==PHASE\n"),
 ('C11_request_phase_dropped', 'core', "         and request['operation']==OPERATION and request['phase']==PHASE\n", "         and request['operation']==OPERATION\n"),
 ('C12_request_scope_hash_dropped',
  'core',
  "         and request['scope_sha256']==SCOPE_SHA256 and request['payload_sha256']==pins.payload\n",
  "         and request['payload_sha256']==pins.payload\n"),
 ('C13_request_payload_hash_dropped',
  'core',
  "         and request['scope_sha256']==SCOPE_SHA256 and request['payload_sha256']==pins.payload\n",
  "         and request['scope_sha256']==SCOPE_SHA256\n"),
 ('C14_effective_uid_not_checked',
  'core',
  "         and type(request['executor_uid']) is int and request['executor_uid']==0 and executor_uid()==0,'REQUEST_OR_EXECUTOR_UNBOUND')\n",
  "         and type(request['executor_uid']) is int and request['executor_uid']==0,'REQUEST_OR_EXECUTOR_UNBOUND')\n"),
 ('C15_declared_uid_not_checked',
  'core',
  "         and type(request['executor_uid']) is int and request['executor_uid']==0 and executor_uid()==0,'REQUEST_OR_EXECUTOR_UNBOUND')\n",
  "         and executor_uid()==0,'REQUEST_OR_EXECUTOR_UNBOUND')\n"),
 ('C16_declared_uid_type_not_checked',
  'core',
  "         and type(request['executor_uid']) is int and request['executor_uid']==0 and executor_uid()==0,'REQUEST_OR_EXECUTOR_UNBOUND')\n",
  "         and request['executor_uid']==0 and executor_uid()==0,'REQUEST_OR_EXECUTOR_UNBOUND')\n"),
 ('C20_authority_schema_dropped',
  'core',
  "    need(authority['schema']==AUTHORITY_SCHEMA and authority['operation']==OPERATION and authority['phase']==PHASE\n",
  "    need(authority['operation']==OPERATION and authority['phase']==PHASE\n"),
 ('C21_authority_operation_dropped',
  'core',
  "    need(authority['schema']==AUTHORITY_SCHEMA and authority['operation']==OPERATION and authority['phase']==PHASE\n",
  "    need(authority['schema']==AUTHORITY_SCHEMA and authority['phase']==PHASE\n"),
 ('C22_authority_phase_dropped',
  'core',
  "    need(authority['schema']==AUTHORITY_SCHEMA and authority['operation']==OPERATION and authority['phase']==PHASE\n",
  "    need(authority['schema']==AUTHORITY_SCHEMA and authority['operation']==OPERATION\n"),
 ('C23_authority_status_dropped',
  'core',
  "         and authority['status']=='SIGNED' and authority['decision']=='APPROVED' and authority['execution_authorized'] is True\n",
  "         and authority['decision']=='APPROVED' and authority['execution_authorized'] is True\n"),
 ('C24_authority_decision_dropped',
  'core',
  "         and authority['status']=='SIGNED' and authority['decision']=='APPROVED' and authority['execution_authorized'] is True\n",
  "         and authority['status']=='SIGNED' and authority['execution_authorized'] is True\n"),
 ('C25_authority_execution_flag_dropped',
  'core',
  "         and authority['status']=='SIGNED' and authority['decision']=='APPROVED' and authority['execution_authorized'] is True\n",
  "         and authority['status']=='SIGNED' and authority['decision']=='APPROVED'\n"),
 ('C26_authority_request_hash_dropped',
  'core',
  "         and authority['request_sha256']==pins.request and authority['payload_sha256']==pins.payload\n",
  "         and authority['payload_sha256']==pins.payload\n"),
 ('C27_authority_payload_hash_dropped',
  'core',
  "         and authority['request_sha256']==pins.request and authority['payload_sha256']==pins.payload\n",
  "         and authority['request_sha256']==pins.request\n"),
 ('C30_owner_evidence_dropped',
  'core',
  "         and type(authority['owner_evidence']) is str and 0<len(authority['owner_evidence'])<=512\n         and authority['owner_evidence']!='UNBOUND','AUTHORITY_UNBOUND')\n",
  "         ,'AUTHORITY_UNBOUND')\n"),
 ('C30b_owner_evidence_may_be_the_word_unbound',
  'core',
  "         and type(authority['owner_evidence']) is str and 0<len(authority['owner_evidence'])<=512\n         and authority['owner_evidence']!='UNBOUND','AUTHORITY_UNBOUND')\n",
  "         and type(authority['owner_evidence']) is str and 0<len(authority['owner_evidence'])<=512,'AUTHORITY_UNBOUND')\n"),
 ('C30c_owner_evidence_length_cap_dropped',
  'core',
  "         and type(authority['owner_evidence']) is str and 0<len(authority['owner_evidence'])<=512\n         and authority['owner_evidence']!='UNBOUND','AUTHORITY_UNBOUND')\n",
  "         and type(authority['owner_evidence']) is str and 0<len(authority['owner_evidence'])\n         and authority['owner_evidence']!='UNBOUND','AUTHORITY_UNBOUND')\n"),
 ('C31_go_schema_dropped',
  'core',
  "    need(go['schema']==GO_SCHEMA and go['status']=='SIGNED' and go['action']=='GO' and go['phase']==PHASE\n",
  "    need(go['status']=='SIGNED' and go['action']=='GO' and go['phase']==PHASE\n"),
 ('C32_go_status_dropped',
  'core',
  "    need(go['schema']==GO_SCHEMA and go['status']=='SIGNED' and go['action']=='GO' and go['phase']==PHASE\n",
  "    need(go['schema']==GO_SCHEMA and go['action']=='GO' and go['phase']==PHASE\n"),
 ('C33_go_action_dropped',
  'core',
  "    need(go['schema']==GO_SCHEMA and go['status']=='SIGNED' and go['action']=='GO' and go['phase']==PHASE\n",
  "    need(go['schema']==GO_SCHEMA and go['status']=='SIGNED' and go['phase']==PHASE\n"),
 ('C34_go_phase_dropped',
  'core',
  "    need(go['schema']==GO_SCHEMA and go['status']=='SIGNED' and go['action']=='GO' and go['phase']==PHASE\n",
  "    need(go['schema']==GO_SCHEMA and go['status']=='SIGNED' and go['action']=='GO'\n"),
 ('C35_go_operation_dropped', 'core', "         and go['operation']==OPERATION and go['execution_authorized'] is True\n", "         and go['execution_authorized'] is True\n"),
 ('C36_go_execution_flag_dropped', 'core', "         and go['operation']==OPERATION and go['execution_authorized'] is True\n", "         and go['operation']==OPERATION\n"),
 ('C39_go_request_hash_dropped', 'core', "         and go['request_sha256']==pins.request and go['authority_sha256']==pins.authority\n", "         and go['authority_sha256']==pins.authority\n"),
 ('C40_go_authority_hash_dropped', 'core', "         and go['request_sha256']==pins.request and go['authority_sha256']==pins.authority\n", "         and go['request_sha256']==pins.request\n"),
 ('C41_go_payload_hash_dropped', 'core', "         and go['payload_sha256']==pins.payload,'GO_UNBOUND')\n", "         ,'GO_UNBOUND')\n"),
 ('C42_unbound_owner_accepted',
  'core',
  "    need(type(go['owner']) is str and go['owner'] not in ('','UNBOUND') and len(go['owner'])<=128\n         and go['owner']==authority['owner'],'OWNER_UNBOUND')\n",
  "    need(type(go['owner']) is str and len(go['owner'])<=128\n         and go['owner']==authority['owner'],'OWNER_UNBOUND')\n"),
 ('C43_owner_equality_dropped',
  'core',
  "    need(type(go['owner']) is str and go['owner'] not in ('','UNBOUND') and len(go['owner'])<=128\n         and go['owner']==authority['owner'],'OWNER_UNBOUND')\n",
  "    need(type(go['owner']) is str and go['owner'] not in ('','UNBOUND') and len(go['owner'])<=128,'OWNER_UNBOUND')\n"),
 ('C44_null_host_binding_accepted',
  'core',
  "    need(hexpin(host) and host==authority['host_binding_sha256']==go['host_binding_sha256'],'HOST_BINDING')\n",
  "    need(host==authority['host_binding_sha256']==go['host_binding_sha256'],'HOST_BINDING')\n"),
 ('C45_host_binding_authority_dropped',
  'core',
  "    need(hexpin(host) and host==authority['host_binding_sha256']==go['host_binding_sha256'],'HOST_BINDING')\n",
  "    need(hexpin(host) and host==go['host_binding_sha256'],'HOST_BINDING')\n"),
 ('C46_host_binding_go_dropped',
  'core',
  "    need(hexpin(host) and host==authority['host_binding_sha256']==go['host_binding_sha256'],'HOST_BINDING')\n",
  "    need(hexpin(host) and host==authority['host_binding_sha256'],'HOST_BINDING')\n"),
 ('C46b_host_binding_equalities_dropped',
  'core',
  "    need(hexpin(host) and host==authority['host_binding_sha256']==go['host_binding_sha256'],'HOST_BINDING')\n",
  "    need(hexpin(host),'HOST_BINDING')\n"),
 ('C47_null_transport_target_accepted',
  'core',
  "         and type(binding['target']) is str and binding['target'] and hexpin(binding['command_sha256'])\n",
  "         and hexpin(binding['command_sha256'])\n"),
 ('C48_null_command_pin_accepted',
  'core',
  "         and type(binding['target']) is str and binding['target'] and hexpin(binding['command_sha256'])\n",
  "         and type(binding['target']) is str and binding['target']\n"),
 ('C49_remote_command_not_pinned',
  'core',
  "         and binding['remote_command']==REMOTE_COMMAND and type(binding['runtime_sha256']) is dict\n         and binding['runtime_sha256'].get(SOURCE_NAME)==pins.payload,'GO_TRANSPORT_UNBOUND')\n",
  "         and type(binding['runtime_sha256']) is dict\n         and binding['runtime_sha256'].get(SOURCE_NAME)==pins.payload,'GO_TRANSPORT_UNBOUND')\n"),
 ('C50_runtime_pin_of_the_source_not_tied_to_the_payload',
  'core',
  "         and binding['remote_command']==REMOTE_COMMAND and type(binding['runtime_sha256']) is dict\n         and binding['runtime_sha256'].get(SOURCE_NAME)==pins.payload,'GO_TRANSPORT_UNBOUND')\n",
  "         and binding['remote_command']==REMOTE_COMMAND and type(binding['runtime_sha256']) is dict,'GO_TRANSPORT_UNBOUND')\n"),
 ('C51_null_claim_root_accepted',
  'core',
  "    need(type(root) is dict and set(root)=={'path','device','inode'} and type(root['path']) is str and root['path'].startswith('/')\n"
  "         and integer(root['device']) and integer(root['inode'],1),'GO_CLAIM_ROOT_UNBOUND')\n",
  "    need(type(root) is dict and set(root)=={'path','device','inode'},'GO_CLAIM_ROOT_UNBOUND')\n"),
 ('C52_date_set_dropped', 'core', "    need(type(request['date']) is str and request['date'] in DATES,'DATE_NOT_IN_SCOPE')\n", "    need(type(request['date']) is str,'DATE_NOT_IN_SCOPE')\n"),
 ('C53_request_date_not_tied_to_the_windows', 'core', "    need(all(point.date().isoformat()==request['date'] for point in starts+ends),'DATE_WINDOW_MISMATCH')\n", ''),
 ('C54_window_span_cap_dropped', 'core', "    need(start<end and (end-start).total_seconds()<=MAX_GATE_SPAN_SECONDS,'WINDOW_SPAN')\n", "    need(start<end,'WINDOW_SPAN')\n"),
 ('C55_empty_window_accepted',
  'core',
  "    need(start<end and (end-start).total_seconds()<=MAX_GATE_SPAN_SECONDS,'WINDOW_SPAN')\n",
  "    need((end-start).total_seconds()<=MAX_GATE_SPAN_SECONDS,'WINDOW_SPAN')\n"),
 ('C56_gate_uses_first_window_only', 'core', '    start,end=max(starts),min(ends)\n', '    start,end=starts[0],ends[0]\n'),
 ('C57_non_utc_offset_accepted',
  'core',
  "    need(point.tzinfo is not None and offset is not None and offset.total_seconds()==0,'WINDOW_NOT_UTC')\n",
  "    need(point.tzinfo is not None and offset is not None,'WINDOW_NOT_UTC')\n"),
 ('C58_gate_initial_window_dropped', 'core', "        need(start<=self.wall<end,'OUTSIDE_GO_WINDOW')\n", ''),
 ('C59_gate_wall_window_dropped', 'core', "        need(self.start<=wall<self.end and mono<self.deadline,'GO_EXPIRED')\n", "        need(mono<self.deadline,'GO_EXPIRED')\n"),
 ('C60_gate_monotonic_deadline_dropped', 'core', "        need(self.start<=wall<self.end and mono<self.deadline,'GO_EXPIRED')\n", "        need(self.start<=wall<self.end,'GO_EXPIRED')\n"),
 ('C61_wall_clock_reversal_accepted', 'core', "        need(wall>=self.wall and mono>=self.mono,'CLOCK_REVERSED')\n", "        need(mono>=self.mono,'CLOCK_REVERSED')\n"),
 ('C62_monotonic_reversal_accepted', 'core', "        need(wall>=self.wall and mono>=self.mono,'CLOCK_REVERSED')\n", "        need(wall>=self.wall,'CLOCK_REVERSED')\n"),
 ('C63_plan_host_binding_dropped', 'core', "    need(type(plan) is dict and plan.get('host_binding_sha256')==host,'PLAN_BINDING')\n", "    need(type(plan) is dict,'PLAN_BINDING')\n"),
 ('C64_plan_keys_not_exact', 'core', "    exact(plan,PLAN_COMMON_KEYS|PLAN_KEYS,'PLAN_KEYS')\n", "    need(type(plan) is dict,'PLAN_KEYS')\n"),
 ('C65_plan_schema_dropped', 'core', "    need(plan['schema']==PLAN_SCHEMA and plan['status']=='BOUND','PLAN_UNBOUND')\n", "    need(plan['status']=='BOUND','PLAN_UNBOUND')\n"),
 ('C66_plan_status_dropped', 'core', "    need(plan['schema']==PLAN_SCHEMA and plan['status']=='BOUND','PLAN_UNBOUND')\n", "    need(plan['schema']==PLAN_SCHEMA,'PLAN_UNBOUND')\n"),
 ('C67_plan_phase_dropped', 'core', "    need(plan['phase']==PHASE,'PHASE_INVALID')\n", ''),
 ('C68_plan_limits_dropped', 'core', "    need(type(plan['max_seconds']) is int and plan['max_seconds']==MAX_SECONDS,'LIMITS_INVALID')\n", ''),
 ('C69_scope_not_compared',
  'core',
  "    need(type(plan['scope']) is dict and canonical(plan['scope'])==canonical(SCOPE),'SCOPE_MISMATCH')\n",
  "    need(type(plan['scope']) is dict,'SCOPE_MISMATCH')\n"),
 ('C70_plan_window_not_tied_to_the_request', 'core', "    need(instant(plan['window']['not_before'])==starts[0] and instant(plan['window']['expires_at'])==ends[0],'PLAN_WINDOW')\n", ''),
 ('C71_empty_evidence_accepted',
  'core',
  "    need(type(evidence) is list and len(evidence)<=16 and (evidence or not EVIDENCE_REQUIRED),'EVIDENCE_UNBOUND')\n",
  "    need(type(evidence) is list and len(evidence)<=16,'EVIDENCE_UNBOUND')\n"),
 ('C72_evidence_receipt_hash_not_checked',
  'core',
  "             and text(item['operation'],'[A-Z][A-Z0-9_]{0,79}') and hexpin(item['receipt_sha256']),'EVIDENCE_UNBOUND')\n",
  "             and text(item['operation'],'[A-Z][A-Z0-9_]{0,79}'),'EVIDENCE_UNBOUND')\n"),
 ('C73_effects_in_the_authority_not_compared',
  'core',
  "         and canonical(authority['effects'])==effects==canonical(go['effects']),'EFFECTS_BINDING')\n",
  "         and effects==canonical(go['effects']),'EFFECTS_BINDING')\n"),
 ('C74_effects_in_the_go_not_compared',
  'core',
  "         and canonical(authority['effects'])==effects==canonical(go['effects']),'EFFECTS_BINDING')\n",
  "         and canonical(authority['effects'])==effects,'EFFECTS_BINDING')\n"),
 ('C74b_effects_not_compared_at_all', 'core', "         and canonical(authority['effects'])==effects==canonical(go['effects']),'EFFECTS_BINDING')\n", "         ,'EFFECTS_BINDING')\n"),
 ('C75_scope_statement_free_text',
  'core',
  "    need(go['scope_statement']==SCOPE_STATEMENT and go['success_criterion']==success_of(plan),'GO_CRITERION')\n",
  "    need(go['success_criterion']==success_of(plan),'GO_CRITERION')\n"),
 ('C76_success_criterion_free_text',
  'core',
  "    need(go['scope_statement']==SCOPE_STATEMENT and go['success_criterion']==success_of(plan),'GO_CRITERION')\n",
  "    need(go['scope_statement']==SCOPE_STATEMENT,'GO_CRITERION')\n"),
 ('E01_gate_not_called_before_a_mutating_call', 'core', '    gate();state.issue()\n    try:result=action()\n', '    state.issue()\n    try:result=action()\n'),
 ('E02_failed_call_left_uncertain', 'core', '    except OSError:state.fail();raise\n', '    except OSError:raise\n'),
 ('E03_successful_call_not_counted', 'core', '    state.done();return result\n', '    state.unknown();return result\n'),
 ('E04_escaped_exception_always_a_refusal', 'core', '        nothing=(not state.started) or (WRITES_ALLOWED and state.clean() and not state.pending)\n', '        nothing=True\n'),
 ('E05_escape_after_start_of_a_write_is_a_refusal_when_uncertain',
  'core',
  '        nothing=(not state.started) or (WRITES_ALLOWED and state.clean() and not state.pending)\n',
  '        nothing=(not state.started) or WRITES_ALLOWED\n'),
 ('E06_reduced_receipt_stays_complete', 'core', "            if receipt['status']==COMPLETE_STATUS:receipt['status']=PARTIAL_STATUS;receipt['outcome']=REDUCED_OUTCOME\n", ''),
 ('E07_chain_rows_not_compared',
  'core',
  "            need(stat.S_ISDIR(info.st_mode) and row_equal(seen,row,compare_device),'PARENT_IDENTITY_MISMATCH')\n",
  "            need(stat.S_ISDIR(info.st_mode),'PARENT_IDENTITY_MISMATCH')\n"),
 ('E08_symlink_component_opened',
  'core',
  '                if not stat.S_ISDIR(named.st_mode):\n'
  "                    observed.append(dict(row_of(row['path'],named),type=kind(named.st_mode)))\n"
  "                    raise Refused('PARENT_SYMLINK_COMPONENT' if stat.S_ISLNK(named.st_mode) else 'PARENT_NOT_DIRECTORY')\n",
  ''),
 ('E09_verify_skips_the_fresh_walk',
  'core',
  '            if self.rows is not None:\n'
  '                other=walk_pinned(self.host,self.rows,check,[],self.compare_device)\n'
  "                try:need(self.stamp(self.host.fstat(other))==self.identity,'PARENT_REPLACED')\n"
  '                finally:self.host.close(other)\n'
  '            else:',
  '            if self.rows is not None:pass\n            else:'),
 ('E10_verify_skips_the_name_of_a_child', 'core', "                need(self.stamp(self.host.lstat(self.name,self.parent.fd))==self.identity,'PARENT_REPLACED')\n", '                pass\n'),
 ('E11_probe_follows_nothing_but_reports_a_symlink_component_absent',
  'core',
  "                return {'status':'UNAVAILABLE','code':'SYMLINK_COMPONENT','exists':None,'at':prefix}\n",
  "                return {'status':'COMPLETE','exists':False,'absent_at':prefix,'absence_proved_at_read':True}\n"),
 ('E12_descend_without_nofollow',
  'core',
  '    descriptor. With rows, one observed row per component (\'/\' included) is appended in the format a request signs."""\n    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()\n',
  '    descriptor. With rows, one observed row per component (\'/\' included) is appended in the format a request signs."""\n    flags=os.O_RDONLY|os.O_DIRECTORY|host.noatime()\n'),
 ('E13_descend_enters_a_symlink_component',
  'core',
  "            need(not stat.S_ISLNK(named.st_mode),'SYMLINK_COMPONENT')\n"
  "            need(stat.S_ISDIR(named.st_mode),'COMPONENT_NOT_DIRECTORY')\n"
  '            check();child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child\n'
  "            held=host.fstat(fd);need((held.st_dev,held.st_ino)==(named.st_dev,named.st_ino),'PATH_CHANGED')\n"
  '            if rows',
  '            check();child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child\n'
  "            held=host.fstat(fd);need((held.st_dev,held.st_ino)==(named.st_dev,named.st_ino),'PATH_CHANGED')\n"
  '            if rows'),
 ('E14_file_change_during_read_ignored', 'core', "        need(signature(before)==signature(after) and size==before.st_size,'FILE_CHANGED_DURING_READ')\n", ''),
 ('E15_file_size_limit_ignored',
  'core',
  "        need(stat.S_ISREG(before.st_mode),'FILE_NOT_REGULAR');need(before.st_size<=limit,'FILE_TOO_LARGE')\n",
  "        need(stat.S_ISREG(before.st_mode),'FILE_NOT_REGULAR')\n"),
 ('E16_boot_id_shape_unchecked', 'core', "    need(type(raw) is bytes and re.fullmatch(rb'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}\\n?',raw) is not None,'BOOT_ID_INVALID')\n", ''),
 ('E17_noatime_not_required', 'core', "        flag=getattr(os,'O_NOATIME',0);need(flag,'NOATIME_UNAVAILABLE');return flag\n", "        flag=getattr(os,'O_NOATIME',0);return flag\n"),
 ('E18_authentication_refusal_raised_out_of_run',
  'core',
  '        except Refused as error:\n'
  "            return seal(envelope(REFUSED_STATUS,REFUSED_OUTCOME,code_of(error,'AUTHENTICATION_REFUSED'),\n"
  "                                 dict(bound,phase_reached='AUTHENTICATION',mutating_calls=state.counts())))\n",
  '        except KeyError as error:\n'
  "            return seal(envelope(REFUSED_STATUS,REFUSED_OUTCOME,code_of(error,'AUTHENTICATION_REFUSED'),\n"
  "                                 dict(bound,phase_reached='AUTHENTICATION',mutating_calls=state.counts())))\n"),
 ('L12_chain_row_shape_unchecked',
  'core',
  "        need(integer(row['device']) and integer(row['inode'],1) and integer(row['uid']) and integer(row['gid'])\n             and integer(row['mode'],0,0o7777),code)\n",
  ''),
 ('P07_umask_not_set', 'files', '            host.umask(0o077)\n', ''),
 ('P17_failure_after_mkdir_reported_not_created', 'files', "    entry['state']='CREATED_UNVERIFIED'\n", "    entry['state']='NOT_CREATED'\n"),
 ('P19_created_name_identity_not_checked', 'files', "        if (named.st_dev,named.st_ino)!=(info.st_dev,info.st_ino):\n            entry['code']='CREATED_NAME_REPLACED';return entry\n", ''),
 ('P20_created_emptiness_not_checked', 'files', "    if entry['observed']['entries']:\n        entry.update(state='CREATED_NOT_EMPTY',code='CREATED_NOT_EMPTY');return entry\n", ''),
 ('P22_refused_after_a_creation',
  'files',
  '        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n',
  '        if True:return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n'),
 ('P43_evidence_boot_shape_unchecked', 'files', "    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')\n", ''),
 ('I01_link_replaced_by_rename',
  'files',
  '    def link(self,source,target,dir_fd):os.link(source,target,src_dir_fd=dir_fd,dst_dir_fd=dir_fd,follow_symlinks=False)\n',
  '    def link(self,source,target,dir_fd):os.rename(source,target,src_dir_fd=dir_fd,dst_dir_fd=dir_fd)\n'),
 ('I02_final_name_removed_instead_of_the_temporary',
  'files',
  '        mutate(state,gate,lambda:host.unlink(temp,directory.fd))\n',
  "        mutate(state,gate,lambda:host.unlink(entry['path'].rsplit('/',1)[1],directory.fd))\n"),
 ('I03_temporary_removed_without_identity_proof', 'files', "        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino):return 'TEMPORARY_REPLACED'\n", ''),
 ('I04_temporary_name_loadable_by_systemd', 'files', "TEMPORARY='.hostops-%s-%d.partial'\n", "TEMPORARY='hostops-%s-%d.service'\n"),
 ('I19_short_write_accepted',
  'files',
  "                if type(size) is not int or size<=0:return withdrawn('WRITE_INCOMPLETE')\n                written+=size\n",
  '                written+=size if size else len(content)\n'),
 ('I21_failed_file_fsync_ignored',
  'files',
  "        except OSError as error:return withdrawn('FSYNC_FAILED',error)\n        try:\n            info=host.fstat(fd)\n",
  '        except OSError as error:pass\n        try:\n            info=host.fstat(fd)\n'),
 ('I22_failed_directory_fsync_after_link_ignored',
  'files',
  "        try:host.fsync(directory.fd);entry['fsync_directory_after_link']=True\n        except OSError as error:return failed('FSYNC_FAILED',error)\n",
  "        try:host.fsync(directory.fd);entry['fsync_directory_after_link']=True\n        except OSError as error:pass\n"),
 ('I23_refused_after_a_creation',
  'files',
  '        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n',
  '        if True:return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n'),
 ('I29_boot_of_the_evidence_not_compared', 'files', "            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n", ''),
 ('I30_executor_group_not_checked', 'files', "            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n", "            need(host.identity()[0]==0,'EXECUTOR_IDENTITY')\n"),
 ('I40_own_temporary_left_after_a_lost_race',
  'files',
  "            entry['temporary_removal_code']=remove_own_temporary(temp,fd,directory,host,gate,state,entry)\n",
  "            entry['temporary_removal_code']=None\n"),
 ('N01_command_environment_inherited', 'runner', '        environment=dict(COMMAND_ENVIRONMENT)\n', '        environment=dict(os.environ,**COMMAND_ENVIRONMENT)\n'),
 ('N02_docker_config_never_passed', 'runner', "        if docker_config is not None:environment['DOCKER_CONFIG']=docker_config\n", ''),
 ('N04_untrusted_binary_accepted',
  'runner',
  '                return bool(stat.S_ISREG(named.st_mode) and named.st_uid==0 and not named.st_mode&0o022 and named.st_mode&0o111)\n',
  '                return bool(stat.S_ISREG(named.st_mode))\n'),
 ('N05_tool_retried_after_two_timeouts', 'runner', "        need(self.timeouts.get(tool,0)<MAX_TOOL_TIMEOUTS,'COMMAND_SKIPPED_AFTER_TIMEOUT')\n", ''),
 ('N06_failed_command_output_trusted', 'runner', "        if code!=0:raise CommandFailed('COMMAND_FAILED',code)\n", ''),
 ('N07_image_id_shape_unchecked',
  'docker',
  "    need(set(row)=={'id','repo_tags','revision'} and text(row['id'],IMAGE_ID),'IMAGE_METADATA_INVALID')\n",
  "    need(set(row)=={'id','repo_tags','revision'},'IMAGE_METADATA_INVALID')\n"),
 ('D02_dispatcher_one_day_rule_dropped', 'dispatcher', "') and end.date()==start.date(),'DISPATCH_DATE')\n", "'),'DISPATCH_DATE')\n"),
 ('D03_dispatcher_signed_date_not_tied_to_the_config_day', 'dispatcher', " and request.get('date')==start.date().isoformat()\n", '\n'),
 ('D04_dispatcher_config_schema_dropped', 'dispatcher', "_DISPATCH_AUTHORIZATION_V1' and config.get('status')=='BOUND'\n", "_DISPATCH_AUTHORIZATION_V1' or config.get('status')=='BOUND'\n"),
 ('D05_dispatcher_unsigned_go_accepted', 'dispatcher', "    need('status' not in go or go['status']=='SIGNED','GO_UNSIGNED')\n", ''),
 ('D06_dispatcher_unsigned_authority_accepted', 'dispatcher', "    need('status' not in authority or authority['status']=='SIGNED','AUTHORITY_UNSIGNED')\n", ''),
 ('D07_dispatcher_claim_root_binding_dropped',
  'dispatcher',
  "    need(type(go.get('claim_root_identity')) is dict and canonical(go['claim_root_identity'])==canonical(config.get('local_root_identity')),'GO_CLAIM_ROOT_BINDING')\n",
  ''),
 ('D08_dispatcher_transport_binding_dropped', 'dispatcher', "    need(go.get('transport_binding')==expected_transport,'GO_TRANSPORT_BINDING')\n", ''),
 ('D09_dispatcher_host_binding_dropped',
  'dispatcher',
  "    need(request.get('host_binding_sha256')==authority.get('host_binding_sha256')==go.get('host_binding_sha256')==config.get('host_binding_sha256'),'HOST_BINDING')\n",
  ''),
 ('D10_dispatcher_local_authentication_dropped',
  'dispatcher',
  "        clock=clock,monotonic=monotonic,executor_uid=lambda:config['executor_uid'])\n    expected=",
  "        clock=clock,monotonic=monotonic,executor_uid=lambda:config['executor_uid']) if False else None\n    expected="),
 ('D11_dispatcher_receipt_schema_not_checked',
  'dispatcher',
  "_RECEIPT_V1' and receipt.get('request_sha256')==sha(blobs['request'])\n",
  "_RECEIPT_V1' or receipt.get('request_sha256')==sha(blobs['request'])\n"),
 ('D12_dispatcher_late_start_accepted',
  'dispatcher',
  "        gate();need(clock()<=latest_start,'WINDOW_WITH_WATCHDOG')\n        if phase=='prepare':",
  "        gate()\n        if phase=='prepare':"),
 ('D13_dispatcher_claim_not_exclusive',
  'dispatcher',
  '            gate();claim=os.open(claim_name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=output)\n',
  '            gate();claim=os.open(claim_name,os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=output)\n'),
 ('X01_launcher_enters_the_payload_with_the_refusal_exit_code', 'launcher', '    exit_code=3;result=module.run(', '    result=module.run('),
 ('X02_launcher_maps_a_refusal_to_partial',
  'launcher',
  "    exit_code={'METADATA_ONLY_REQUIRES_REVIEW':0,'REFUSED':1}.get(result.get('status'),2)\n",
  "    exit_code={'METADATA_ONLY_REQUIRES_REVIEW':0}.get(result.get('status'),2)\n"),
 ('X03_launcher_maps_everything_to_complete',
  'launcher',
  "    exit_code={'METADATA_ONLY_REQUIRES_REVIEW':0,'REFUSED':1}.get(result.get('status'),2)\n",
  "    exit_code={'METADATA_ONLY_REQUIRES_REVIEW':0,'REFUSED':1}.get(result.get('status'),0)\n"),
 ('X04_launcher_document_pins_not_checked',
  'launcher',
  "        if hashlib.sha256(raw[key]).hexdigest()!=PINS[key]:\n            raise ValueError('STDIN_DOCUMENT_PIN')\n",
  "        if False:\n            raise ValueError('STDIN_DOCUMENT_PIN')\n"),
 ('W01_native_open_strips_nofollow',
  'core',
  '        return os.open(name,flags) if dir_fd is None else os.open(name,flags,dir_fd=dir_fd)\n',
  '        flags&=~os.O_NOFOLLOW;return os.open(name,flags) if dir_fd is None else os.open(name,flags,dir_fd=dir_fd)\n'),
 ('W01b_native_open_ignores_the_descriptor', 'core', '        return os.open(name,flags) if dir_fd is None else os.open(name,flags,dir_fd=dir_fd)\n', '        return os.open(name,flags)\n'),
 ('W02_native_lstat_follows_links',
  'core',
  '    def lstat(self,name,dir_fd):return os.stat(name,dir_fd=dir_fd,follow_symlinks=False)\n',
  '    def lstat(self,name,dir_fd):return os.stat(name,dir_fd=dir_fd,follow_symlinks=True)\n'),
 ('W33_native_fstat_of_another_descriptor', 'core', '    def fstat(self,fd):return os.fstat(fd)\n', "    def fstat(self,fd):return os.stat('/')\n"),
 ('W32_native_identity_reports_root_unconditionally', 'core', '    def identity(self):return os.geteuid(),os.getegid()\n', '    def identity(self):return 0,0\n'),
 ('W06_native_mkdir_ignores_the_signed_mode',
  'files',
  '    def mkdir(self,name,mode,dir_fd):os.mkdir(name,mode,dir_fd=dir_fd)\n',
  '    def mkdir(self,name,mode,dir_fd):os.mkdir(name,0o777,dir_fd=dir_fd)\n'),
 ('W20_native_mkdir_not_relative_to_the_held_descriptor',
  'files',
  '    def mkdir(self,name,mode,dir_fd):os.mkdir(name,mode,dir_fd=dir_fd)\n',
  '    def mkdir(self,name,mode,dir_fd):os.mkdir(name,mode)\n'),
 ('W04_native_fsync_is_a_noop_in_install',
  'files',
  '    def write(self,fd,data):return os.write(fd,data)\n    def fsync(self,fd):os.fsync(fd)\n',
  '    def write(self,fd,data):return os.write(fd,data)\n    def fsync(self,fd):pass\n'),
 ('W05_native_link_follows_a_symlinked_temporary',
  'files',
  'os.link(source,target,src_dir_fd=dir_fd,dst_dir_fd=dir_fd,follow_symlinks=False)\n',
  'os.link(source,target,src_dir_fd=dir_fd,dst_dir_fd=dir_fd)\n'),
 ('W21_native_unlink_not_relative_to_the_held_descriptor', 'files', '    def unlink(self,name,dir_fd):os.unlink(name,dir_fd=dir_fd)\n', '    def unlink(self,name,dir_fd):os.unlink(name)\n'),
 ('W22_native_create_strips_excl',
  'files',
  '    def create(self,name,flags,mode,dir_fd):return os.open(name,flags,mode,dir_fd=dir_fd)\n',
  '    def create(self,name,flags,mode,dir_fd):return os.open(name,flags&~os.O_EXCL,mode,dir_fd=dir_fd)\n'),
 ('W23_native_create_strips_nofollow',
  'files',
  '    def create(self,name,flags,mode,dir_fd):return os.open(name,flags,mode,dir_fd=dir_fd)\n',
  '    def create(self,name,flags,mode,dir_fd):return os.open(name,flags&~os.O_NOFOLLOW,mode,dir_fd=dir_fd)\n'),
 ('W31_native_umask_is_a_noop_in_install', 'files', '    def umask(self,mask):return os.umask(mask)\n', '    def umask(self,mask):return 0o022\n'),
 ('W15_created_file_device_not_compared_with_the_directory',
  'files',
  "                    and info.st_dev==directory.identity[0]):return withdrawn('CREATED_METADATA_MISMATCH')\n",
  "                    ):return withdrawn('CREATED_METADATA_MISMATCH')\n"),
 ('I47_temporary_not_looked_at_again_before_the_link', 'files', "            if (named.st_dev,named.st_ino,named.st_nlink)!=(info.st_dev,info.st_ino,1):return failed('TEMPORARY_REPLACED')\n", ''),
 ('I48_temporary_with_a_second_link_accepted_before_the_link',
  'files',
  "            if (named.st_dev,named.st_ino,named.st_nlink)!=(info.st_dev,info.st_ino,1):return failed('TEMPORARY_REPLACED')\n",
  "            if (named.st_dev,named.st_ino)!=(info.st_dev,info.st_ino):return failed('TEMPORARY_REPLACED')\n"),
 ('I49_incomplete_temporary_left_behind',
  'files',
  "        failed(code,error)\n        entry['temporary_removal_code']=remove_own_temporary(temp,fd,directory,host,gate,state,entry)\n",
  '        failed(code,error)\n'),
 ('I51_removal_errno_overwrites_the_errno_of_the_failure',
  'files',
  "        entry['temporary_removal_errno']=number(error);return 'TEMPORARY_REMOVAL_FAILED'\n",
  "        entry['errno']=entry['temporary_removal_errno']=number(error);return 'TEMPORARY_REMOVAL_FAILED'\n"),
 ('C77_effects_compared_between_the_two_documents_only',
  'core',
  "         and canonical(authority['effects'])==effects==canonical(go['effects']),'EFFECTS_BINDING')\n",
  "         and canonical(authority['effects'])==canonical(go['effects']),'EFFECTS_BINDING')\n"),
 ('C78_gate_ends_with_the_go_window_only', 'core', '    start,end=max(starts),min(ends)\n', '    start,end=max(starts),ends[2]\n'),
 ('C78b_gate_ends_with_the_request_window_only', 'core', '    start,end=max(starts),min(ends)\n', '    start,end=max(starts),ends[0]\n'),
 ('C78c_gate_ends_with_the_authority_window_only', 'core', '    start,end=max(starts),min(ends)\n', '    start,end=max(starts),ends[1]\n'),
 ('C78d_gate_starts_with_the_go_window_only', 'core', '    start,end=max(starts),min(ends)\n', '    start,end=starts[2],min(ends)\n'),
 ('C78e_gate_starts_with_the_request_window_only', 'core', '    start,end=max(starts),min(ends)\n', '    start,end=starts[0],min(ends)\n'),
 ('C78f_gate_starts_with_the_authority_window_only', 'core', '    start,end=max(starts),min(ends)\n', '    start,end=starts[1],min(ends)\n'),
 ('C78g_gate_takes_the_widest_window', 'core', '    start,end=max(starts),min(ends)\n', '    start,end=min(starts),max(ends)\n'),
 ('C79_only_the_ends_must_lie_on_the_signed_day',
  'core',
  "    need(all(point.date().isoformat()==request['date'] for point in starts+ends),'DATE_WINDOW_MISMATCH')\n",
  "    need(all(point.date().isoformat()==request['date'] for point in ends),'DATE_WINDOW_MISMATCH')\n"),
 ('C79b_only_the_starts_must_lie_on_the_signed_day',
  'core',
  "    need(all(point.date().isoformat()==request['date'] for point in starts+ends),'DATE_WINDOW_MISMATCH')\n",
  "    need(all(point.date().isoformat()==request['date'] for point in starts),'DATE_WINDOW_MISMATCH')\n"),
 ('C80_plan_window_start_not_tied_to_the_request',
  'core',
  "    need(instant(plan['window']['not_before'])==starts[0] and instant(plan['window']['expires_at'])==ends[0],'PLAN_WINDOW')\n",
  "    need(instant(plan['window']['expires_at'])==ends[0],'PLAN_WINDOW')\n"),
 ('C80b_plan_window_end_not_tied_to_the_request',
  'core',
  "    need(instant(plan['window']['not_before'])==starts[0] and instant(plan['window']['expires_at'])==ends[0],'PLAN_WINDOW')\n",
  "    need(instant(plan['window']['not_before'])==starts[0],'PLAN_WINDOW')\n"),
 ('C81_transport_binding_keys_not_exact',
  'core',
  "    need(type(binding) is dict and set(binding)=={'target','remote_command','command_sha256','runtime_sha256'}\n",
  "    need(type(binding) is dict and set(binding)>={'target','remote_command','command_sha256','runtime_sha256'}\n"),
 ('C82_claim_root_keys_not_exact',
  'core',
  "    need(type(root) is dict and set(root)=={'path','device','inode'} and type(root['path']) is str and root['path'].startswith('/')\n"
  "         and integer(root['device']) and integer(root['inode'],1),'GO_CLAIM_ROOT_UNBOUND')\n",
  "    need(type(root) is dict and set(root)>={'path','device','inode'} and type(root['path']) is str and root['path'].startswith('/')\n"
  "         and integer(root['device']) and integer(root['inode'],1),'GO_CLAIM_ROOT_UNBOUND')\n"),
 ('C83_claim_root_path_unchecked',
  'core',
  "    need(type(root) is dict and set(root)=={'path','device','inode'} and type(root['path']) is str and root['path'].startswith('/')\n"
  "         and integer(root['device']) and integer(root['inode'],1),'GO_CLAIM_ROOT_UNBOUND')\n",
  "    need(type(root) is dict and set(root)=={'path','device','inode'}\n         and integer(root['device']) and integer(root['inode'],1),'GO_CLAIM_ROOT_UNBOUND')\n"),
 ('C83b_claim_root_path_may_be_relative',
  'core',
  "    need(type(root) is dict and set(root)=={'path','device','inode'} and type(root['path']) is str and root['path'].startswith('/')\n"
  "         and integer(root['device']) and integer(root['inode'],1),'GO_CLAIM_ROOT_UNBOUND')\n",
  "    need(type(root) is dict and set(root)=={'path','device','inode'} and type(root['path']) is str\n         and integer(root['device']) and integer(root['inode'],1),'GO_CLAIM_ROOT_UNBOUND')\n"),
 ('C84_claim_root_device_and_inode_unchecked',
  'core',
  "    need(type(root) is dict and set(root)=={'path','device','inode'} and type(root['path']) is str and root['path'].startswith('/')\n"
  "         and integer(root['device']) and integer(root['inode'],1),'GO_CLAIM_ROOT_UNBOUND')\n",
  "    need(type(root) is dict and set(root)=={'path','device','inode'} and type(root['path']) is str and root['path'].startswith('/'),'GO_CLAIM_ROOT_UNBOUND')\n"),
 ('C84b_claim_root_device_unchecked',
  'core',
  "    need(type(root) is dict and set(root)=={'path','device','inode'} and type(root['path']) is str and root['path'].startswith('/')\n"
  "         and integer(root['device']) and integer(root['inode'],1),'GO_CLAIM_ROOT_UNBOUND')\n",
  "    need(type(root) is dict and set(root)=={'path','device','inode'} and type(root['path']) is str and root['path'].startswith('/')\n"
  "         and integer(root['inode'],1),'GO_CLAIM_ROOT_UNBOUND')\n"),
 ('C84c_claim_root_inode_unchecked',
  'core',
  "    need(type(root) is dict and set(root)=={'path','device','inode'} and type(root['path']) is str and root['path'].startswith('/')\n"
  "         and integer(root['device']) and integer(root['inode'],1),'GO_CLAIM_ROOT_UNBOUND')\n",
  "    need(type(root) is dict and set(root)=={'path','device','inode'} and type(root['path']) is str and root['path'].startswith('/')\n"
  "         and integer(root['device']),'GO_CLAIM_ROOT_UNBOUND')\n"),
 ('E19_mount_point_always_the_root', 'core', "        if row['device']!=previous['device']:point=row['path']\n", '        pass\n'),
 ('E19b_mount_point_one_component_too_high', 'core', "        if row['device']!=previous['device']:point=row['path']\n", "        if row['device']!=previous['device']:point=previous['path']\n"),
 ('T03_created_file_link_count_not_checked',
  'files',
  '            if not (stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==0 and info.st_gid==0\n',
  '            if not (stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_gid==0\n'),
 ('T06_link_count_after_the_removal_of_the_temporary_not_checked', 'files', "        if entry['links']!=1:return failed('CREATED_METADATA_MISMATCH')\n", ''),
 ('T07_walk_does_not_compare_the_lstat_with_the_descriptor',
  'core',
  "                host.close(fd);fd=child;info=host.fstat(fd)\n                need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'PARENT_CHANGED_DURING_WALK')\n",
  '                host.close(fd);fd=child;info=host.fstat(fd)\n'),
 ('T08_clean_ignores_uncertain_calls', 'core', '    def clean(self):return self.succeeded==0 and self.uncertain()==0\n', '    def clean(self):return self.succeeded==0\n'),
 ('T09_escape_with_a_pending_call_not_looked_at',
  'core',
  '        nothing=(not state.started) or (WRITES_ALLOWED and state.clean() and not state.pending)\n',
  '        nothing=(not state.started) or (WRITES_ALLOWED and state.clean())\n'),
 ('T10_verify_does_not_compare_the_fresh_walk_with_the_descriptor_held',
  'core',
  "                try:need(self.stamp(self.host.fstat(other))==self.identity,'PARENT_REPLACED')\n",
  '                try:pass\n'),
 ('EF_provision__operation', 'files', 'def effects_of(plan):\n', "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('operation');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__groups', 'files', 'def effects_of(plan):\n', "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('groups');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__data_volume_path',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('data_volume_path');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__journal_leaf', 'files', 'def effects_of(plan):\n', "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('journal_leaf');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__existing_journal_leaves',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('existing_journal_leaves');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__capacity', 'files', 'def effects_of(plan):\n', "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('capacity');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__creates', 'files', 'def effects_of(plan):\n', "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('creates');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__directories_to_create',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('directories_to_create');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__direct_parents',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('direct_parents');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__chains_sha256',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('chains_sha256');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__data_volume_root',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('data_volume_root');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__retention_tag',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('retention_tag');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__evidence_boot_id_sha256',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('evidence_boot_id_sha256');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__files_created',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('files_created');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__pre_existing_objects_modified',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('pre_existing_objects_modified');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__daemon_reload',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('daemon_reload');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__activation', 'files', 'def effects_of(plan):\n', "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('activation');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__journal', 'files', 'def effects_of(plan):\n', "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('journal');return value\ndef _effects_complete(plan):\n"),
 ('EF_provision__creates__key',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['creates']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('key',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__creates__path',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['creates']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('path',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__creates__mode_octal',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['creates']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('mode_octal',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__creates__expect',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['creates']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('expect',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__retention_tag__reference',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['retention_tag']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('reference',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__retention_tag__image_id',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['retention_tag']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('image_id',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__retention_tag__expect',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['retention_tag']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('expect',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__journal__placement',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['journal']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('placement',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__journal__path',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['journal']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('path',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__journal__filesystem_named_by_chain',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['journal']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('filesystem_named_by_chain',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__journal__filesystem_device',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['journal']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('filesystem_device',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__journal__mount_point_by_device_change',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['journal']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('mount_point_by_device_change',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__journal__data_volume_touched_for_the_journal',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['journal']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('data_volume_touched_for_the_journal',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__capacity__root_path',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['capacity']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('root_path',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__capacity__receipt_directory_path',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['capacity']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('receipt_directory_path',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__capacity__receipts_inside_capacity_root',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['capacity']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('receipts_inside_capacity_root',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__data_volume_root__world_writable_without_sticky',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['data_volume_root']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('world_writable_without_sticky',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__data_volume_root__device_differs_from_parent',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['data_volume_root']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('device_differs_from_parent',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__direct_parents__DATA_VOLUME',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['direct_parents']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('DATA_VOLUME',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__direct_parents__ETC',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['direct_parents']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('ETC',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_provision__direct_parents__VAR_LIB',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['direct_parents']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('VAR_LIB',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__operation', 'files', 'def effects_of(plan):\n', "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('operation');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__directory', 'files', 'def effects_of(plan):\n', "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('directory');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__directory_row',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('directory_row');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__chain_sha256',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('chain_sha256');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__units', 'files', 'def effects_of(plan):\n', "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('units');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__files_to_create',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('files_to_create');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__network_allowlist',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('network_allowlist');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__data_volume_path',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('data_volume_path');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__template_revision',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('template_revision');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__acknowledged_leftovers',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('acknowledged_leftovers');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__evidence_boot_id_sha256',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('evidence_boot_id_sha256');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__daemon_reload',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('daemon_reload');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__external_processes',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('external_processes');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__pre_existing_objects_modified',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('pre_existing_objects_modified');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__activation', 'files', 'def effects_of(plan):\n', "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('activation');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__journal_placement',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('journal_placement');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__deploy_tree_path',
  'files',
  'def effects_of(plan):\n',
  "def effects_of(plan):\n    value=_effects_complete(plan);value.pop('deploy_tree_path');return value\ndef _effects_complete(plan):\n"),
 ('EF_install_units__units__destination_name',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['units']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('destination_name',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__units__mode_octal',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['units']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('mode_octal',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__units__profile',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['units']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('profile',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__units__template_sha256',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['units']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('template_sha256',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__units__rendered_sha256',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['units']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('rendered_sha256',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__units__rendered_bytes',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['units']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('rendered_bytes',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__units__substitutions',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['units']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('substitutions',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__units__expect',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['units']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('expect',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__daemon_reload__performed_by_this_operation',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['daemon_reload']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('performed_by_this_operation',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__daemon_reload__owner',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['daemon_reload']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('owner',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__directory_row__path',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['directory_row']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('path',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__directory_row__device',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['directory_row']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('device',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__directory_row__inode',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['directory_row']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('inode',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__directory_row__uid',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['directory_row']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('uid',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__directory_row__gid',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['directory_row']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('gid',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n'),
 ('EF_install_units__directory_row__mode',
  'files',
  'def effects_of(plan):\n',
  'def effects_of(plan):\n'
  "    value=_effects_complete(plan);target=value['directory_row']\n"
  '    for item in (target if type(target) is list else [target]):\n'
  "        if type(item) is dict:item.pop('mode',None)\n"
  '    return value\n'
  'def _effects_complete(plan):\n')]
PORTED_COMBOS={'combo_host_binding_both_layers': ['C46b_host_binding_equalities_dropped', 'D09_dispatcher_host_binding_dropped'],
 'combo_r3_escape_with_a_pending_call_both_checks': ['T09_escape_with_a_pending_call_not_looked_at', 'T08_clean_ignores_uncertain_calls'],
 'combo_r3_link_count_of_the_temporary_both_looks': ['T03_created_file_link_count_not_checked', 'I48_temporary_with_a_second_link_accepted_before_the_link'],
 'combo_r3_verify_fresh_walk_and_signed_rows': ['T10_verify_does_not_compare_the_fresh_walk_with_the_descriptor_held', 'E07_chain_rows_not_compared'],
 'combo_r3_walk_lstat_and_signed_rows': ['T07_walk_does_not_compare_the_lstat_with_the_descriptor', 'E07_chain_rows_not_compared'],
 'combo_refusal_after_mutation_all_layers': ['P22_refused_after_a_creation', 'E04_escaped_exception_always_a_refusal'],
 'combo_signed_date_both_layers': ['C53_request_date_not_tied_to_the_windows', 'D03_dispatcher_signed_date_not_tied_to_the_config_day', 'D02_dispatcher_one_day_rule_dropped'],
 'combo_temporary_swap_both_looks': ['I47_temporary_not_looked_at_again_before_the_link', 'I03_temporary_removed_without_identity_proof'],
 'combo_unsigned_authority_both_layers': ['C23_authority_status_dropped', 'D06_dispatcher_unsigned_authority_accepted'],
 'combo_unsigned_go_both_layers': ['C32_go_status_dropped', 'D05_dispatcher_unsigned_go_accepted'],
 'combo_window_gate_both_checks': ['C58_gate_initial_window_dropped', 'C59_gate_wall_window_dropped']}
PORTED_REDUNDANT={'T09_escape_with_a_pending_call_not_looked_at': 'a pending call is issued and not settled: Effects.uncertain() is then at least 1 and clean() is already false (T08)',
 'T10_verify_does_not_compare_the_fresh_walk_with_the_descriptor_held': 'the fresh walk already requires every component to equal its signed row on device, inode, owner, group and mode (E07), and '
                                                                        'the identity held was read from a descriptor that passed the same walk'}
