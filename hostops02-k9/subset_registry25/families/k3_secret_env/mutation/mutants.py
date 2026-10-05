"""The mutants of K3 (secret.env). Each row: (name, target, exact anchor, replacement). Target 'op': a text of op.py;
'core', 'docker', 'runner': a text of that part of the core (the secrets family's revision, core_k3) as this
operation's built source carries it. Every anchor occurs exactly once in the built source (mutate.py check). One mutant
per constant the signers rely on, per member of effects_of(), per refusal of validate_plan and of the precheck, per
condition of the worker and of its entry, per condition of the creation, readback and withdrawal, and per member of the
receipt that says what the run did; then the mutants HOC section 8 names (H*); then the functions of the core this
operation's secret depends on (as K3-K9 carries them).

HOC section 8 names four mutants: "size emitted in the refusal table" (H01, H02), "template widened" (H03, H04, and the
core's D01), "digest or length emitted" (H05, H06, H07, H08) and "written under the final name directly". The last is
this source's declared design (the token placement's D3, which K3-K9 also follows): there is no temporary to skip. What
that mutant guards against in HOC's design is a final name that holds a partial or foreign file; here the same is
guarded by the exclusive create and by the withdrawal by identity, and each of their properties is a mutant of this
list: create without O_EXCL (C13), following a link (C14), truncating (C16), a withdrawal of another inode (F06) or of a
linked file (F07), no withdrawal after a failure (F24, F20, F21, F22, F23, F31), a withdrawal stopped by the gate (F39), a file left
after a failed write said withdrawn (F10).

Left out, because no test can tell them apart from the source (said here so that a reviewer does not look for them):
- the clearing of Effects.pending after an uncertain call (state.unknown(); perform's receipt does not read pending);
- the fallback code of a stop without a code ('SECRET_ENV_NOT_PLACED'): every stop of place_secret sets a code;
- a quote or a backslash admitted by SECRET_VALUE_GRAMMAR: the core's parse never copies such a value (None), so the
  grammar never sees one; a byte outside printable ASCII likewise;
- the initial None of a fact the first statement of the precheck sets, and the texts of the scope (pinned by the static
  tests, which a mutation run deselects);
- 'regular' of the created file (an exclusive create makes a regular file);
- the first four members of READBACK_FACTS taken out of the readback's judgement (readback_same_inode,
  readback_metadata_as_created, readback_exactly_one_line, readback_name_is_the_key): readback() returns False before
  the facts are judged when the inode or the metadata differ, and equality with the line written implies one line and
  the key (the line has exactly one newline, at its end, and begins with the key). Each fact's own computation is a
  mutant (F18, F34, F35, and the tamper tests check every fact's value); the tuple is kept as the readable statement of
  what a COMPLETE readback means;
- MAX_CONFIG_ENTRIES 64 against 63 is killed (the boundary test holds 64 entries); against 65 likewise; the core's
  count_entries bound of the directory readback (MAX_CONFIG_ENTRIES+1) cannot be reached after a precheck of at most 64.
"""
MUTANTS=[]
COMBOS={}
REDUNDANT={}
def add(name,old,new,target='op'):MUTANTS.append((name,target,old,new))

# ---------------------------------------------------------------- constants the signers rely on
add('C01_another_directory',"CONFIG_DIRECTORY='/etc/c3po-reader'","CONFIG_DIRECTORY='/etc/c3po-bar'")
add('C02_directory_0750',"CONFIG_DIRECTORY_MODE=0o700","CONFIG_DIRECTORY_MODE=0o750")
add('C03_another_name',"SECRET_ENV_NAME='secret.env'","SECRET_ENV_NAME='secret.env.new'")
add('C04_file_0640',"SECRET_ENV_MODE=0o600","SECRET_ENV_MODE=0o640")
add('C05_temporary_prefix_otherwise',"TEMPORARY_PREFIX='.hostops-'","TEMPORARY_PREFIX='.hostops-x'")
add('C06_one_more_entry',"MAX_CONFIG_ENTRIES=64","MAX_CONFIG_ENTRIES=65")
add('C06b_one_entry_less',"MAX_CONFIG_ENTRIES=64","MAX_CONFIG_ENTRIES=63")
add('C07_another_key',"SECRET_KEY='C3PO_DATABASE_URL'","SECRET_KEY='C3PO_DATABASE_URI'")
add('C08_line_of_another_name',"SECRET_LINE_PREFIX=b'C3PO_DATABASE_URL='","SECRET_LINE_PREFIX=b'DATABASE_URL='")
GRAMMAR=r"SECRET_VALUE_GRAMMAR=rb'[\x21\x23-\x5b\x5d-\x7e]{1,4096}'"
add('C09_value_with_a_space',GRAMMAR,GRAMMAR.replace(r'[\x21',r'[\x20\x21'))
add('C10_value_of_4095',GRAMMAR,GRAMMAR.replace('{1,4096}','{1,4095}'))
add('C11_value_of_two_at_least',GRAMMAR,GRAMMAR.replace('{1,4096}','{2,4096}'))
add('C12_value_without_a_hash',GRAMMAR,GRAMMAR.replace(r'\x23-',r'\x24-'))
CREATE="SECRET_CREATE_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC"
add('C13_create_without_o_excl',CREATE,CREATE.replace('|os.O_EXCL',''))
add('C14_create_following_a_link',CREATE,CREATE.replace('|os.O_NOFOLLOW',''))
add('C15_create_without_o_cloexec',CREATE,CREATE.replace('|os.O_CLOEXEC',''))
add('C16_create_truncating',CREATE,CREATE+'|os.O_TRUNC')
add('C17_readback_following_a_link',"READBACK_FLAGS=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK","READBACK_FLAGS=os.O_RDONLY|os.O_NONBLOCK")
add('C18_readback_blocking',"READBACK_FLAGS=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK","READBACK_FLAGS=os.O_RDONLY|os.O_NOFOLLOW")
add('C19_readback_request_one_less',"READBACK_REQUEST=len(SECRET_LINE_PREFIX)+MAX_SECRET_VALUE_BYTES+2","READBACK_REQUEST=len(SECRET_LINE_PREFIX)+MAX_SECRET_VALUE_BYTES+1")
add('C20_less_than_the_allowance_left',"WRITE_ALLOWANCE_SECONDS=15 ","WRITE_ALLOWANCE_SECONDS=14 ")
add('C21_another_worker',"WORKER_CONTAINER_NAME='c3po-r2d2-worker-1'","WORKER_CONTAINER_NAME='c3po-api-1'")
add('C22_replicas_of_one_number_only',"WORKER_NAME_PREFIX='c3po-r2d2-worker-'","WORKER_NAME_PREFIX='c3po-r2d2-worker-2'")
add('C23_another_project',"WORKER_COMPOSE_PROJECT='c3po'","WORKER_COMPOSE_PROJECT='c3po-staging'")
add('C24_another_service',"WORKER_COMPOSE_SERVICE='r2d2-worker'","WORKER_COMPOSE_SERVICE='api'")
add('C25_labels_project_read_from_the_service',"'{\"project\":{{json (index .Config.Labels \"com.docker.compose.project\")}},'",
    "'{\"project\":{{json (index .Config.Labels \"com.docker.compose.service\")}},'")
add('C26_evidence_without_the_epoch_readback',"EVIDENCE_OPERATIONS=(PROVISION_OPERATION,EPOCH_READBACK_OPERATION)","EVIDENCE_OPERATIONS=(PROVISION_OPERATION,)")
add('C27_evidence_without_the_provisioning',"EVIDENCE_OPERATIONS=(PROVISION_OPERATION,EPOCH_READBACK_OPERATION)","EVIDENCE_OPERATIONS=(EPOCH_READBACK_OPERATION,)")
add('C28_sessions_only',"DATE_CLASS='WRITE_EPOCH'","DATE_CLASS='WRITE_SESSIONS'")

# ---------------------------------------------------------------- the plan, refused from its bytes
CHAIN="rows=validate_chain(plan['config_chain'],CONFIG_DIRECTORY,receives_entry=True)"
add('V01_an_open_root',CHAIN,"rows=validate_chain(plan['config_chain'],CONFIG_DIRECTORY,open_root='/etc',receives_entry=True)")
add('V02_a_setgid_directory',CHAIN,"rows=validate_chain(plan['config_chain'],CONFIG_DIRECTORY)")
add('V03_directory_of_any_owner_and_mode',"    need((rows[-1]['uid'],rows[-1]['gid'],rows[-1]['mode'])==(0,0,CONFIG_DIRECTORY_MODE),'CONFIG_DIRECTORY_NOT_ROOT_0700')\n","")
add('V04_directory_of_any_group',"(rows[-1]['uid'],rows[-1]['gid'],rows[-1]['mode'])==(0,0,CONFIG_DIRECTORY_MODE)","(rows[-1]['uid'],rows[-1]['mode'])==(0,CONFIG_DIRECTORY_MODE)")
add('V05_worker_id_not_checked',"    need(text(plan['worker_container_id'],CONTAINER_ID),'WORKER_CONTAINER_UNBOUND')\n","")
add('V06_boot_not_checked',"    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')\n","")

# ---------------------------------------------------------------- the effects the signers see
add('E01_effects_without_required',"dict(chain_effects(plan['config_chain']),required={'uid':0,'gid':0,'mode_octal':'0700','open_root':None,","dict(chain_effects(plan['config_chain']),required={'uid':0,'gid':0,'mode_octal':'0755','open_root':None,")
add('E02_effects_secret_env_may_exist',"'secret_env':'ABSENT','leftover_of_a_secret':'ABSENT'}),","'secret_env':'ABSENT'}),")
add('E03_effects_another_path',"            'creates':{'path':SECRET_ENV_PATH,","            'creates':{'path':CONFIG_DIRECTORY,")
add('E04_effects_file_0644',"'type':'regular file','uid':0,'gid':0,'mode_octal':'0600','links':1,\n","'type':'regular file','uid':0,'gid':0,'mode_octal':'0644','links':1,\n")
add('E05_effects_a_temporary',"'content':'exactly one line '+SECRET_KEY+'=<value> and a newline','temporary':None},","'content':'exactly one line '+SECRET_KEY+'=<value> and a newline','temporary':'.partial'},")
add('E06_effects_without_the_container_id',"'container_id':plan['worker_container_id'],","'container_id':None,")
add('E07_effects_one_read',"'compose_service':WORKER_COMPOSE_SERVICE,'reads':2},","'compose_service':WORKER_COMPOSE_SERVICE,'reads':1},")
add('E08_effects_without_the_process',"            'process':{'dumpable':0,'when':'first, before anything of the host is looked at'},\n","")
add('E09_effects_another_boot',"            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],\n","            'evidence_boot_id_sha256':None,\n")
add('E10_effects_say_a_size_may_be_in_the_receipt',"'activation':False,'value_in_receipt':False,'size_or_digest_in_receipt':False}","'activation':False,'value_in_receipt':False}")

# ---------------------------------------------------------------- the precheck: order and refusals
add('P01_process_left_dumpable',"            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');process['dumpable_disabled']=True\n","            process['dumpable_disabled']=True\n")
add('P02_any_answer_taken',"need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED')","need(host.not_dumpable() is not None,'PROCESS_DUMPABLE_NOT_DISABLED')")
add('P03_not_dumpable_after_the_executor',"            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');process['dumpable_disabled']=True\n            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n",
    "            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');process['dumpable_disabled']=True\n")
add('P04_executor_not_checked',"            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n","")
add('P05_umask_not_set',"            host.umask(0o077)\n","")
add('P06_umask_0022',"            host.umask(0o077)\n","            host.umask(0o022)\n")
add('P07_boot_not_compared',"            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n","")
add('P08_secret_env_present_not_refused',"    need(not present,'SECRET_ENV_PRESENT')\n","")
add('P09_leftover_not_refused',"    need(not leftover,'SECRET_ENV_LEFTOVER_PRESENT')\n","")
add('P10_temporaries_not_looked_for',"        elif name.startswith(TEMPORARY_PREFIX) or SECRET_ENV_NAME in name:leftover=True\n","        elif SECRET_ENV_NAME in name:leftover=True\n")
add('P11_other_secret_env_names_not_looked_for',"        elif name.startswith(TEMPORARY_PREFIX) or SECRET_ENV_NAME in name:leftover=True\n","        elif name.startswith(TEMPORARY_PREFIX):leftover=True\n")
add('P12_existing_file_not_described',"        existing.update(type=kind(info.st_mode),uid=info.st_uid,gid=info.st_gid,mode_octal='%04o'%stat.S_IMODE(info.st_mode),links=info.st_nlink)\n","        pass\n")
add('P13_entries_not_bounded',"        need(count<=MAX_CONFIG_ENTRIES,'ENTRY_LIMIT')\n","")
add('P14_leftover_before_present',"    need(not present,'SECRET_ENV_PRESENT')\n    need(not leftover,'SECRET_ENV_LEFTOVER_PRESENT')\n","    need(not leftover,'SECRET_ENV_LEFTOVER_PRESENT')\n    need(not present,'SECRET_ENV_PRESENT')\n")
add('P15_budget_not_checked',"            need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')\n","")
add('P16_budget_strictly_more',"need(left>=WRITE_ALLOWANCE_SECONDS,","need(left>WRITE_ALLOWANCE_SECONDS,")
add('P17_directory_not_proved_again',"            target.verify(gate)\n            code=None\n","            code=None\n")
add('P18_seconds_left_not_said',"left=gate();precheck['seconds_left_before_the_first_effect']=int(left)","left=gate()")
add('P19_buffers_not_zeroed',"        for buffer in buffers:zero(buffer)\n","")
add('P20_zero_does_nothing',"        for index in range(len(buffer)):buffer[index]=0\n","        pass\n")
add('P21_present_fact_inverted',"facts.update(entries_before=count,secret_env_absent=not present,no_leftover_of_a_secret=not leftover)","facts.update(entries_before=count,secret_env_absent=True,no_leftover_of_a_secret=not leftover)")
add('P22_leftover_fact_inverted',"facts.update(entries_before=count,secret_env_absent=not present,no_leftover_of_a_secret=not leftover)","facts.update(entries_before=count,secret_env_absent=not present,no_leftover_of_a_secret=True)")
add('P23_entries_said_zero',"facts.update(entries_before=count,","facts.update(entries_before=0,")
add('P24_pinned_fact_not_said',"            config['pinned']=True\n","")

# ---------------------------------------------------------------- the worker and its entry
add('W01_worker_not_in_the_list_accepted',"    need(facts['one_container_with_the_name'] and facts['id_equal_signed'],'WORKER_CONTAINER_MISMATCH')\n","")
add('W02_another_id_accepted',"need(facts['one_container_with_the_name'] and facts['id_equal_signed'],'WORKER_CONTAINER_MISMATCH')","need(facts['one_container_with_the_name'],'WORKER_CONTAINER_MISMATCH')")
add('W03_replicas_not_refused',"    need(facts['no_other_running_container_of_the_service_name'],'WORKER_NOT_THE_ONLY_ONE')\n","")
add('W04_stopped_replicas_refused',"                                                                 and row['id']!=worker and row['state']=='running']\n","                                                                 and row['id']!=worker]\n")
add('W05_the_worker_counted_as_its_own_replica',"                                                                 and row['id']!=worker and row['state']=='running']\n","                                                                 and row['state']=='running']\n")
add('W06_stopped_worker_accepted',"    need(facts['running'],'WORKER_NOT_RUNNING')\n","")
add('W07_running_said_by_the_inspect_only',"facts['running']=row['running'] is True and row['state']=='running' and named[0]['state']=='running'","facts['running']=row['running'] is True")
add('W08_inspect_by_name',"    row=container_facts(commands,worker,expected_name=WORKER_CONTAINER_NAME)\n","    row=container_facts(commands,WORKER_CONTAINER_NAME)\n")
add('W09_labels_not_judged',"    need(facts['compose_project_and_service'],'WORKER_NOT_THE_COMPOSE_SERVICE')\n","")
add('W10_project_not_compared',"facts['compose_project_and_service']=labels['project']==WORKER_COMPOSE_PROJECT and labels['service']==WORKER_COMPOSE_SERVICE","facts['compose_project_and_service']=labels['service']==WORKER_COMPOSE_SERVICE")
add('W11_service_not_compared',"facts['compose_project_and_service']=labels['project']==WORKER_COMPOSE_PROJECT and labels['service']==WORKER_COMPOSE_SERVICE","facts['compose_project_and_service']=labels['project']==WORKER_COMPOSE_PROJECT")
add('W12_labels_shape_not_checked',"    need(type(labels) is dict and set(labels)=={'project','service'},'CONTAINER_METADATA_INVALID')\n","")
add('W14_shape_not_checked',"    need(value is not None and re.fullmatch(SECRET_VALUE_GRAMMAR,value) is not None,'SECRET_VALUE_SHAPE')\n","")
add('W15_a_value_the_core_did_not_copy_accepted',"need(value is not None and re.fullmatch(SECRET_VALUE_GRAMMAR,value) is not None,","need(value is None or re.fullmatch(SECRET_VALUE_GRAMMAR,value) is not None,")
add('W17_change_not_refused',"    need(facts['read_twice_equal'],'WORKER_ENVIRONMENT_CHANGED_DURING_READ')\n","")
add('W18_presence_not_compared',"facts['read_twice_equal']=sorted(second)==sorted(first) and second[SECRET_KEY]==value","facts['read_twice_equal']=second.get(SECRET_KEY)==value or SECRET_KEY not in second")
add('W19_bytes_not_compared',"facts['read_twice_equal']=sorted(second)==sorted(first) and second[SECRET_KEY]==value","facts['read_twice_equal']=sorted(second)==sorted(first)")
add('W27_worker_read_before_the_directory',"            scan_directory(host,target,gate,config,existing)\n            content=secret_line(commands,worker,workers,buffers)\n",
    "            content=secret_line(commands,worker,workers,buffers)\n            scan_directory(host,target,gate,config,existing)\n")

# ---------------------------------------------------------------- the entry, the line (revised after the independent read)
add('W13_absent_entry_not_refused',"    need(SECRET_KEY in first,'SECRET_ENTRY_ABSENT')\n","")
add('W16_one_read_only',"    try:second=entry_values(commands,worker,'WORKER_ENVIRONMENT_CHANGED_DURING_READ')\n","    try:second=first\n")
add('W20_first_values_not_zeroed',"    first=entry_values(commands,worker,'SECRET_VALUE_SHAPE');buffers.extend(first.values())\n","    first=entry_values(commands,worker,'SECRET_VALUE_SHAPE')\n")
add('W21_second_values_not_zeroed',"    buffers.extend(second.values())\n","")
add('W22_line_not_zeroed',"    content=bytearray(len(SECRET_LINE_PREFIX)+len(value)+1);buffers.append(content)\n","    content=bytearray(len(SECRET_LINE_PREFIX)+len(value)+1)\n")
add('W23_line_without_its_newline',"content[-1]=0x0a\n","content[-1]=0x20\n")
add('W24_value_one_byte_early',"content[len(SECRET_LINE_PREFIX):-1]=value","content[len(SECRET_LINE_PREFIX)-1:-1]=value")
add('W26_facts_said_before_the_shape_check',"    need(value is not None and re.fullmatch(SECRET_VALUE_GRAMMAR,value) is not None,'SECRET_VALUE_SHAPE')\n    facts.update(entry_present=True,value_shape_met=True)",
    "    facts.update(entry_present=True,value_shape_met=True)\n    need(value is not None and re.fullmatch(SECRET_VALUE_GRAMMAR,value) is not None,'SECRET_VALUE_SHAPE')")
add('W28_entry_present_said_before_the_shape_check',"    need(SECRET_KEY in first,'SECRET_ENTRY_ABSENT')\n","    need(SECRET_KEY in first,'SECRET_ENTRY_ABSENT');facts['entry_present']=True\n")
add('W29_second_overflow_said_a_shape_fault',"    try:second=entry_values(commands,worker,'WORKER_ENVIRONMENT_CHANGED_DURING_READ')\n","    try:second=entry_values(commands,worker,'SECRET_VALUE_SHAPE')\n")
add('W30_second_overflow_without_the_fact',"        if str(error)=='WORKER_ENVIRONMENT_CHANGED_DURING_READ':facts['read_twice_equal']=False\n","        pass\n")
add('W31_first_overflow_said_a_change',"    first=entry_values(commands,worker,'SECRET_VALUE_SHAPE')","    first=entry_values(commands,worker,'WORKER_ENVIRONMENT_CHANGED_DURING_READ')")
add('F09_no_fsync_after_withdrawal',"    try:host.fsync(directory.fd)\n    except Exception as error:      # any failure here","    try:pass\n    except Exception as error:      # any failure here")
add('F38_withdrawal_fsync_failure_of_another_kind_escapes',"    except Exception as error:      # any failure here","    except OSError as error:      # any failure here")

# ---------------------------------------------------------------- the other environment files (README: a name in one file only)
add('O01_key_in_another_file_not_refused',"    need(facts['key_in_no_other_env_file'],'SECRET_KEY_IN_ANOTHER_ENV_FILE')\n","")
add('O04_name_with_trailing_space_not_seen',"line.split(b'=',1)[0].strip()==SECRET_KEY","line.split(b'=',1)[0]==SECRET_KEY")
add('O05_a_name_alone_not_a_definition',"line.split(b'=',1)[0].strip()==SECRET_KEY.encode('ascii')","b'=' in line and line.split(b'=',1)[0].strip()==SECRET_KEY.encode('ascii')")
add('O06_activation_env_not_looked_at',"OTHER_ENV_FILES=('activation.env','pins.env')","OTHER_ENV_FILES=('pins.env',)")
add('O07_pins_env_not_looked_at',"OTHER_ENV_FILES=('activation.env','pins.env')","OTHER_ENV_FILES=('activation.env',)")
add('O08_limit_one_byte_less',"OTHER_ENV_FILE_LIMIT=65536","OTHER_ENV_FILE_LIMIT=65535")
add('O09_core_codes_not_mapped',"        if str(error) in ('FILE_NOT_REGULAR','FILE_TOO_LARGE','FILE_CHANGED_DURING_READ'):raise Refused('OTHER_ENV_FILE_UNREADABLE') from None\n","")
add('O10_os_errors_not_mapped',"    except OSError:raise Refused('OTHER_ENV_FILE_UNREADABLE') from None","    except FileNotFoundError:raise Refused('OTHER_ENV_FILE_UNREADABLE') from None")
add('O11_fact_said_true_always',"    facts['key_in_no_other_env_file']=not any(","    facts['key_in_no_other_env_file']=True or not any(")
add('O12_checked_before_the_leftovers',"    need(not leftover,'SECRET_ENV_LEFTOVER_PRESENT')\n    facts['key_in_no_other_env_file']=not any(other_env_defines_the_key(host,target,gate,name) for name in sorted(others))\n",
    "    facts['key_in_no_other_env_file']=not any(other_env_defines_the_key(host,target,gate,name) for name in sorted(others))\n    need(not leftover,'SECRET_ENV_LEFTOVER_PRESENT')\n")

# ---------------------------------------------------------------- the creation, readback and withdrawal
METADATA="METADATA_FACTS=('regular','uid_0','gid_0','mode_0600','single_link','on_the_device_of_the_directory')"
add('F01_metadata_gid_not_checked',METADATA,METADATA.replace("'gid_0',",''))
add('F02_metadata_mode_not_checked',METADATA,METADATA.replace("'mode_0600',",''))
add('F03_metadata_uid_not_checked',METADATA,METADATA.replace("'uid_0',",''))
add('F04_metadata_links_not_checked',METADATA,METADATA.replace("'single_link',",''))
add('F05_metadata_device_not_checked',METADATA,METADATA.replace(",'on_the_device_of_the_directory'",''))
add('F06_withdrawal_of_another_inode',"        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino) or named.st_nlink!=1:\n","        if named.st_nlink!=1:\n")
add('F07_withdrawal_of_a_linked_file',"        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino) or named.st_nlink!=1:\n","        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino):\n")
add('F10_failed_unlink_said_withdrawn',"        row.update(withdrawal_code='SECRET_ENV_WITHDRAWAL_FAILED',withdrawal_errno=number(error));return row\n","        row.update(withdrawal_errno=number(error),withdrawn=True,state='WITHDRAWN');return row\n")
READBACK="READBACK_FACTS=('readback_same_inode','readback_metadata_as_created','readback_exactly_one_line','readback_name_is_the_key',\n                'readback_equal_to_the_worker_entry')"
add('F15_readback_equality_not_judged',READBACK,READBACK.replace(",\n                'readback_equal_to_the_worker_entry'",''))
add('F16_readback_without_noatime',"    fd=host.open(SECRET_ENV_NAME,READBACK_FLAGS|host.noatime(),dir_fd=directory.fd)\n","    fd=host.open(SECRET_ENV_NAME,READBACK_FLAGS,dir_fd=directory.fd)\n")
add('F17_readback_without_the_directory_proved',"    directory.verify(gate);gate()\n    fd=host.open(","    gate()\n    fd=host.open(")
add('F18_content_read_before_the_identity_is_proved',"        if not (row['readback_same_inode'] and row['readback_metadata_as_created']):return False\n","")
add('F19_readback_buffer_not_zeroed',"        found=bytearray();buffers.append(found)\n","        found=bytearray()\n")
add('F25_existing_name_said_filesystem_error',"code='SECRET_ENV_APPEARED_AFTER_PRECHECK' if error.errno==errno.EEXIST else filesystem_code(error))","code=filesystem_code(error))")
add('F26_write_of_nothing_accepted',"                    if type(size) is not int or size<=0:return withdraw","                    if type(size) is not int:return withdraw")
add('F27_one_write_only',"                while written<len(content):\n","                if written<len(content):\n")
add('F32_refused_after_a_creation',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n","        if state.counts()['uncertain']==0:return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n")
add('F33_all_bytes_said_written_before_the_writes',"            written=0;row['all_bytes_written']=False\n","            written=0;row['all_bytes_written']=True\n")
add('F34_readback_compares_a_prefix',"readback_equal_to_the_worker_entry=found==content)","readback_equal_to_the_worker_entry=found[:len(content)]==content)")
add('F35_readback_one_line_without_the_last_byte',"readback_exactly_one_line=found.count(b'\\n')==1 and found[-1:]==b'\\n'","readback_exactly_one_line=found.count(b'\\n')==1")
add('F37_directory_readback_failure_said_none',"                readbacks['config_directory']=code_of(error,'READBACK_UNAVAILABLE')\n","                readbacks['config_directory']=None\n")

# ---------------------------------------------------------------- the revision after the second independent read (2026-10-04)
add('W25_output_limit_code_leaks',"        if str(error) in ('COMMAND_OUTPUT_LIMIT','SECRET_ENVIRONMENT_SHAPE'):raise Refused(shape) from None\n","")
add('W32_entry_without_an_equals_sign_has_its_own_code',"if str(error) in ('COMMAND_OUTPUT_LIMIT','SECRET_ENVIRONMENT_SHAPE'):","if str(error) in ('COMMAND_OUTPUT_LIMIT',):")
add('W33_not_listed_again',"    need(facts['same_container_after_the_reads'],'WORKER_CHANGED_DURING_READ')\n","")
add('W34_listed_again_without_the_id',"facts['same_container_after_the_reads']=len(again)==1 and again[0]['id']==worker and again[0]['state']=='running'","facts['same_container_after_the_reads']=len(again)==1 and again[0]['state']=='running'")
add('W35_listed_again_without_the_state',"facts['same_container_after_the_reads']=len(again)==1 and again[0]['id']==worker and again[0]['state']=='running'","facts['same_container_after_the_reads']=len(again)==1 and again[0]['id']==worker")
add('F08_withdrawal_not_counted',"        mutate(state,ungated,lambda:host.unlink(SECRET_ENV_NAME,directory.fd))\n","        host.unlink(SECRET_ENV_NAME,directory.fd)\n")
add('F20_metadata_mismatch_kept',"                if not metadata_facts(info,row,directory):return withdraw(fd,row,directory,host,state,'SECRET_ENV_METADATA_MISMATCH')\n","                metadata_facts(info,row,directory)\n")
add('F21_readback_mismatch_kept',"                if not readback(info,row,content,directory,host,gate,buffers):return withdraw(fd,row,directory,host,state,'READBACK_MISMATCH')\n","                readback(info,row,content,directory,host,gate,buffers)\n")
add('F22_left_after_a_refusal_at_the_readback',"            except Refused as error:\n                return withdraw(fd,row,directory,host,state,str(error) if","            except Refused as error:\n                row['code']=str(error);return row\n                return withdraw(fd,row,directory,host,state,str(error) if")
add('F23_left_after_an_expiry_during_a_write',"            except Refused as error:return withdraw(fd,row,directory,host,state,code_of(error,'GO_EXPIRED'))\n","            except Refused as error:\n                row['code']=code_of(error,'GO_EXPIRED');return row\n")
add('F24_other_failure_not_withdrawn',"            if state.pending:state.unknown()\n            return withdraw(fd,row,directory,host,state,'SECRET_ENV_PLACEMENT_FAILED')\n","            if state.pending:state.unknown()\n            row['code']='SECRET_ENV_PLACEMENT_FAILED';return row\n")
add('F28_file_not_fsynced',"            try:host.fsync(fd);row['fsync_file']=True\n            except OSError as error:return withdraw(fd,row,directory,host,state,'FSYNC_FAILED',error)\n","            row['fsync_file']=True\n")
add('F29_directory_not_fsynced',"            try:host.fsync(directory.fd);row['fsync_directory']=True\n            except OSError as error:return withdraw(fd,row,directory,host,state,'FSYNC_FAILED',error)\n","            row['fsync_directory']=True\n")
add('F30_directory_readback_expects_no_new_entry',"==entries_before+1 else 'READBACK_MISMATCH'","==entries_before else 'READBACK_MISMATCH'")
add('F31_directory_readback_not_judged',"            if readbacks['config_directory']:return withdraw(fd,row,directory,host,state,'DIRECTORY_READBACK_MISMATCH')\n","")
add('F36_directory_readback_not_proved_from_root',"            try:\n                directory.verify(gate)\n                readbacks['config_directory']=","            try:\n                readbacks['config_directory']=")
add('F39_withdrawal_stopped_by_the_gate',"    try:\n        named=host.lstat(SECRET_ENV_NAME,directory.fd);held=host.fstat(fd)\n","    if row['code'] in ('GO_EXPIRED','CLOCK_REVERSED','PARENT_REPLACED'):return row\n    try:\n        named=host.lstat(SECRET_ENV_NAME,directory.fd);held=host.fstat(fd)\n")
add('F40_parent_replaced_off_the_readback_list',"str(error) if str(error) in ('GO_EXPIRED','CLOCK_REVERSED','PARENT_REPLACED') else 'READBACK_MISMATCH'","str(error) if str(error) in ('GO_EXPIRED','CLOCK_REVERSED') else 'READBACK_MISMATCH'")
add('F41_clock_reversal_off_the_readback_list',"str(error) if str(error) in ('GO_EXPIRED','CLOCK_REVERSED','PARENT_REPLACED') else 'READBACK_MISMATCH'","str(error) if str(error) in ('GO_EXPIRED','PARENT_REPLACED') else 'READBACK_MISMATCH'")
add('F42_directory_said_at_its_path_always',"    except Refused:row['directory_at_the_signed_path']=False\n","    except Refused:row['directory_at_the_signed_path']=True\n")
add('F43_directory_not_looked_for',"        directory.verify(ungated);row['directory_at_the_signed_path']=True\n","        row['directory_at_the_signed_path']=True\n")

# ---------------------------------------------------------------- the receipt
add('R01_any_code_through',"def listed(code):return code if code is None or code in RECEIPT_CODES else UNLISTED_CODE","def listed(code):return code")
add('R02_row_codes_not_listed',"        row.update(code=listed(row['code']),withdrawal_code=listed(row['withdrawal_code']))\n","")
add('R03_left_file_said_absent',"    return 1 if row['state'] in ('PLACED_VERIFIED','LEFT_UNVERIFIED') else 0\n","    return 1 if row['state']=='PLACED_VERIFIED' else 0\n")
add('R04_uncertain_creation_said_absent',"    if row['state']=='CREATE_UNCERTAIN':return None\n","")
add('R05_dumpable_fact_true_before_the_call',"            process['dumpable_disabled']=False\n            need(host.not_dumpable()","            process['dumpable_disabled']=True\n            need(host.not_dumpable()")
add('R06_readback_complete_after_a_stop',"        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None}\n","        extra={'phase_reached':'EFFECTS','readback':'COMPLETE'}\n")
add('R07_existing_said_empty',"config_directory=config,existing_secret_env=existing or None,","config_directory=config,existing_secret_env=existing,")

# ---------------------------------------------------------------- the mutants HOC section 8 names
add('H01_size_emitted_in_the_refusal_table',"links=info.st_nlink)\n","links=info.st_nlink,size=info.st_size)\n")
add('H02_size_is_zero_emitted_in_the_refusal_table',"links=info.st_nlink)\n","links=info.st_nlink,size_is_zero=info.st_size==0)\n")
add('H03_template_widened_to_a_second_name',"SECRET_ENVIRONMENT_NAMES=(SECRET_KEY,)","SECRET_ENVIRONMENT_NAMES=(SECRET_KEY,'C3PO_REDIS_URL')")
add('H04_template_widened_to_any_name_that_begins_with_it',"SECRET_ENVIRONMENT_NAMES=(SECRET_KEY,)","SECRET_ENVIRONMENT_NAMES=(SECRET_KEY,'C3PO_DATABASE_URL_OLD')")
add('H05_length_emitted',"            row['all_bytes_written']=written==len(content)\n","            row['all_bytes_written']=written\n")
add('H06_digest_emitted',"            row['all_bytes_written']=written==len(content)\n","            row['all_bytes_written']=written==len(content);row['line_sha256']=sha(bytes(content))\n")
add('H07_read_size_depends_on_the_value',"            gate();block=host.read(fd,READBACK_REQUEST)\n","            gate();block=host.read(fd,len(content)+1)\n")
add('H08_length_in_the_directory_facts',"facts.update(entries_before=count,","facts.update(entries_before=count,value_length=None,")

# ---------------------------------------------------------------- the core, as this operation carries it
DUMP="        disabled=library.prctl(PR_SET_DUMPABLE,0,0,0,0)==0 and library.prctl(PR_GET_DUMPABLE,0,0,0,0)==0\n"
add('Y01_prctl_set_not_made',DUMP,"        disabled=library.prctl(PR_GET_DUMPABLE,0,0,0,0)==0\n",'core')
add('Y02_read_back_skipped',DUMP,"        disabled=library.prctl(PR_SET_DUMPABLE,0,0,0,0)==0\n",'core')
add('Y03_attribute_set_to_1',"library.prctl(PR_SET_DUMPABLE,0,0,0,0)==0","library.prctl(PR_SET_DUMPABLE,1,0,0,0)==0",'core')
add('Y04_failure_not_refused',"    need(disabled,'PROCESS_DUMPABLE_NOT_DISABLED');return True\n","    return True\n",'core')
add('Y05_native_says_disabled_without_a_call',"    def not_dumpable(self):return dumps_disabled()","    def not_dumpable(self):return True",'core')
add('D01_template_prints_the_other_entries','{{if eq (index $p 0) "%s"}}','{{if ne (index $p 0) "%s"}}','docker')
add('D02_template_prints_unquoted','{{json .}}\\n{{end}}','{{.}}\\n{{end}}','docker')
add('D03_repeated_entry_accepted',"name=matched[0];need(name not in found,'SECRET_ENVIRONMENT_REPEATED')","name=matched[0]",'docker')
add('D05_refused_parse_not_zeroed',"    except BaseException:\n        zero_secret_values(found);raise\n","    except BaseException:\n        raise\n",'docker')
add('D08_line_of_another_name_skipped',"need(len(matched)==1 and line[-1:]==b'\"','SECRET_ENVIRONMENT_SHAPE')","need(len(matched)<=1 and line[-1:]==b'\"','SECRET_ENVIRONMENT_SHAPE')",'docker')
add('N01_secret_row_started_directly',"through==(SECRET_ENVIRONMENT_ROW if name==SECRET_ENVIRONMENT_ROW else TEMPLATE_AT_CALL_TIME","through==(through if name==SECRET_ENVIRONMENT_ROW else TEMPLATE_AT_CALL_TIME",'runner')
