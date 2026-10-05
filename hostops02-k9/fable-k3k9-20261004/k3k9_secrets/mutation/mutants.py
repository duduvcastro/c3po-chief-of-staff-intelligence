"""The mutants of K3-K9. Each row: (name, target, exact anchor, replacement). Target 'op': a text of op.py; 'core',
'docker', 'runner': a text of that part of the core (the secrets family's revision) as this operation's built source
carries it. Every anchor occurs exactly once in the built source (mutate.py check). One mutant per constant the
signers rely on, per member of effects_of(), per refusal of validate_plan and of the precheck, per condition of the
worker's environment and of the two files of September, per condition of the creations, readbacks and withdrawals, and
per member of the receipt that says what the run did; then the functions of the core this operation's secrets depend on.

Left out, because no test can tell them apart from the source (said here so that a reviewer does not look for them):
- the clearing of Effects.pending after an uncertain call (state.unknown(); perform's receipt does not read pending);
- the fallback codes of a stop without a code ('EMITTER_DIRECTORY_NOT_CREATED', 'SECRET_FILE_NOT_PLACED'): every stop of
  create_directory and of place_file sets a code;
- the 'CLOCK_REVERSED' and 'PARENT_REPLACED' members of the readback's stop list against a withdrawal: a replaced
  directory makes withdraw() find another inode or none, and leave the file as LEFT_UNVERIFIED either way;
- present[0] against present[-1] as the value written (the values present are byte-equal by then);
- the initial None of a fact the first statement of the precheck sets, and the texts of the scope (pinned by the static
  tests, which a mutation run deselects);
- facts that cannot be false in a run: 'walked_without_following_a_link' (a walk that follows nothing either completes
  or refuses), 'regular' of a created file (an exclusive create makes a regular file);
- the group of the K9 root and of secrets in their own 0:0:0700 checks (revision 2): CHAIN_ROW_NOT_ROOT_GROUP, judged
  before them, requires gid 0 on every row of the chain;
- the read bound of the URL file (RISK_URL_MAX_FILE_BYTES 4096 against 4097): the grammar ({1,4082} after the scheme,
  then at most one newline) refuses a 4097-byte file with the same code and the same facts; likewise
- the read bound of the password (EMITTER_PASSWORD_MAX_FILE_BYTES 64 against 65): the grammar of exactly 64 bytes refuses
  a 65-byte file with the same code and the same facts;
- three bounds of the core's parse of the template's output that this operation's own grammar implies (a quote or a
  backslash in a value, a value over 4096 bytes: the token grammar refuses both with the same code) and its refusal of a
  target that is not an ID (validate_plan admits only a 64-hex ID), and a value outside them copied instead of None (the
  token grammar refuses it with the same code, and the copy is zeroed): the core's own list kills them (SEC13, SEC12,
  SEC19, SEC10).
"""
MUTANTS=[]
COMBOS={}
REDUNDANT={}
def add(name,old,new,target='op'):MUTANTS.append((name,target,old,new))

# ---------------------------------------------------------------- constants the signers rely on
add('C01_the_k9_root_on_the_data_volume',"K9_ROOT='/var/lib/c3po/r2d2-v2-k9-20261005' ","K9_ROOT='/mnt/day-d-data/r2d2-v2-k9-20261005' ")
add('C02_the_source_open_root_one_level_up',"SOURCE_OPEN_ROOT='/mnt/day-d-data'\n","SOURCE_OPEN_ROOT='/mnt'\n")
add('C03_secrets_directory_0750',"K9_SECRETS_DIRECTORY_MODE=0o700","K9_SECRETS_DIRECTORY_MODE=0o750")
add('C04_files_0640',"K9_SECRET_FILE_MODE=0o600","K9_SECRET_FILE_MODE=0o640")
add('C05_emitter_named_otherwise',"K9_EMITTER_NAME='emitter'","K9_EMITTER_NAME='emitter-password'")
add('C06_provider_file_named_otherwise',"PROVIDER_ENV_NAME='provider.env'","PROVIDER_ENV_NAME='providers.env'")
add('C07_risk_file_named_otherwise',"RISK_DB_ENV_NAME='risk-db.env'","RISK_DB_ENV_NAME='risk.env'")
add('C08_password_named_otherwise',"EMITTER_PASSWORD_NAME='password'","EMITTER_PASSWORD_NAME='password.txt'")
CREATE="SECRET_CREATE_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC"
add('C09_create_without_o_excl',CREATE,CREATE.replace('|os.O_EXCL',''))
add('C10_create_following_a_link',CREATE,CREATE.replace('|os.O_NOFOLLOW',''))
add('C11_create_without_o_cloexec',CREATE,CREATE.replace('|os.O_CLOEXEC',''))
add('C12_create_truncating',CREATE,CREATE+'|os.O_TRUNC')
add('C13_readback_following_a_link',"READBACK_FLAGS=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK","READBACK_FLAGS=os.O_RDONLY|os.O_NONBLOCK")
add('C14_readback_blocking',"READBACK_FLAGS=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK","READBACK_FLAGS=os.O_RDONLY|os.O_NOFOLLOW")
add('C15_another_worker',"WORKER_CONTAINER_NAME='c3po-r2d2-worker-1'","WORKER_CONTAINER_NAME='c3po-api-1'")
NAMES="PROVIDER_TOKEN_NAMES=(('C3PO_EODHD_API_TOKEN','EODHD_API_TOKEN'),('C3PO_FINNHUB_API_TOKEN','FINNHUB_API_TOKEN'),('C3PO_FMP_API_TOKEN','FMP_API_TOKEN'))"
add('C16_only_the_prefixed_names',NAMES,"PROVIDER_TOKEN_NAMES=(('C3PO_EODHD_API_TOKEN',),('C3PO_FINNHUB_API_TOKEN',),('C3PO_FMP_API_TOKEN',))")
add('C17_only_the_plain_names',NAMES,"PROVIDER_TOKEN_NAMES=(('EODHD_API_TOKEN',),('FINNHUB_API_TOKEN',),('FMP_API_TOKEN',))")
add('C18_the_plain_name_written',NAMES,"PROVIDER_TOKEN_NAMES=(('EODHD_API_TOKEN','C3PO_EODHD_API_TOKEN'),('C3PO_FINNHUB_API_TOKEN','FINNHUB_API_TOKEN'),('C3PO_FMP_API_TOKEN','FMP_API_TOKEN'))")
add('C19_two_tokens_only',NAMES,"PROVIDER_TOKEN_NAMES=(('C3PO_EODHD_API_TOKEN','EODHD_API_TOKEN'),('C3PO_FINNHUB_API_TOKEN','FINNHUB_API_TOKEN'))")
TOKEN="PROVIDER_TOKEN_GRAMMAR=rb'[A-Za-z0-9._~+/=-]{16,512}'"
add('C20_token_of_one_character',TOKEN,TOKEN.replace('{16,512}','{1,512}'))
add('C21_token_of_fifteen',TOKEN,TOKEN.replace('{16,512}','{15,512}'))
add('C22_token_of_513',TOKEN,TOKEN.replace('{16,512}','{16,513}'))
add('C23_token_with_a_space_and_a_dollar',TOKEN,TOKEN.replace('=-]','= $-]'))
URL="RISK_URL_GRAMMAR=rb'postgresql://[\\x21-\\x7e]{1,4083}'"
add('C28_risk_url_of_another_role',"RISK_URL_READER_PREFIX=b'postgresql://c3po_v2_risk_reader:'","RISK_URL_READER_PREFIX=b'postgresql://c3po_v2_risk_reader'")
add('C29_risk_url_key_otherwise',"RISK_URL_KEY='C3PO_R2D2_RISK_DATABASE_URL'","RISK_URL_KEY='C3PO_DATABASE_URL'")
add('C30_password_of_63',"EMITTER_PASSWORD_GRAMMAR=rb'[A-Za-z0-9_-]{64}'","EMITTER_PASSWORD_GRAMMAR=rb'[A-Za-z0-9_-]{63,64}'")
add('C31_password_with_a_dot',"EMITTER_PASSWORD_GRAMMAR=rb'[A-Za-z0-9_-]{64}'","EMITTER_PASSWORD_GRAMMAR=rb'[A-Za-z0-9_.-]{64}'")
add('C33_less_than_the_allowance_left',"WRITE_ALLOWANCE_SECONDS=15 ","WRITE_ALLOWANCE_SECONDS=14 ")
add('C34_another_source_of_the_url',"RISK_URL_NAME='risk-database-url'","RISK_URL_NAME='database-url'")
add('C35_another_source_of_the_password',"EMITTER_SOURCE_DIRECTORY=SOURCE_OPEN_ROOT+'/.c3po-role-executor-20260908-r2/secret'","EMITTER_SOURCE_DIRECTORY=SOURCE_OPEN_ROOT+'/.c3po-role-executor-20260908-r2'")

URL="RISK_URL_GRAMMAR=rb'postgresql://[\\x21-\\x7e]{1,4082}'"
add('C25_risk_url_with_a_space',URL,URL.replace('\\x21-','\\x20-'))
add('C26_risk_url_of_any_scheme',URL,"RISK_URL_GRAMMAR=rb'[a-z]+://[\\x21-\\x7e]{1,4082}'")
add('C27_risk_url_value_one_longer',URL,URL.replace('4082','4083'))
add('C41_data_volume_not_in_the_effects',"                      'data_volume':dict(chain_effects(plan['data_volume_chain']),open_root_of='the two walks of the files of September only'),\n","")

E3="EVIDENCE_OPERATIONS=(K4_E0_OPERATION,EPOCH_READBACK_OPERATION,K9_TREE_OPERATION)"
add('C36_evidence_without_the_epoch_readback',E3,"EVIDENCE_OPERATIONS=(K4_E0_OPERATION,K9_TREE_OPERATION)")
add('C37_evidence_without_k4_e0',E3,"EVIDENCE_OPERATIONS=(EPOCH_READBACK_OPERATION,K9_TREE_OPERATION)")
add('C38_evidence_without_the_tree_read',E3,"EVIDENCE_OPERATIONS=(K4_E0_OPERATION,EPOCH_READBACK_OPERATION)")
add('C40_data_volume_chain_not_judged',"    volume=validate_chain(plan['data_volume_chain'],SOURCE_OPEN_ROOT,open_root=SOURCE_OPEN_ROOT)     # \"/\" and \"/mnt\" root-owned and closed\n","    volume=plan['data_volume_chain']\n")
add('C42_data_volume_need_not_be_a_mount_point',"    need(mount_point_of(volume)==SOURCE_OPEN_ROOT,'DATA_VOLUME_NOT_A_MOUNT_POINT')\n","")
add('C43_source_rows_not_checked',"                 for row,path in zip(sources,SOURCE_PATHS)),'SOURCE_ROWS_INVALID')","                 for row,path in zip(sources,SOURCE_PATHS)) or True,'SOURCE_ROWS_INVALID')")
add('C44_source_rows_of_any_path',"set(row)==set(SOURCE_ROW_KEYS) and row['path']==path and","set(row)==set(SOURCE_ROW_KEYS) and")
add('C45_source_rows_off_the_volume',"    need(all(row['device']==volume[-1]['device'] for row in sources),'SOURCE_ROWS_OFF_THE_DATA_VOLUME')\n","")
add('C46_source_rows_group_writable',"    need(all(not row['mode']&0o022 for row in sources),'SOURCE_ROWS_WRITABLE_BY_GROUP_OR_OTHER')\n","    need(all(not row['mode']&0o002 or row['mode']&0o1000 for row in sources),'SOURCE_ROWS_WRITABLE_BY_GROUP_OR_OTHER')\n")
add('C47_source_rows_of_any_owner',"    need(all(row['uid'] in (0,volume[-1]['uid']) for row in sources),'SOURCE_ROWS_OWNER_UNEXPECTED')\n","")
add('C48_k9_chain_of_any_group',"    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),'CHAIN_ROW_NOT_ROOT_GROUP')\n","")
add('C49_k9_chain_setgid_accepted',"row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows","row['gid']==0 for row in rows")
add('C50_effects_without_the_source_rows',"                      'source_rows_sha256':sha(canonical(plan['source_rows'])),\n","")

# ---------------------------------------------------------------- the plan, refused from its bytes
add('V01_an_open_root_for_the_k9_tree',"rows=validate_chain(plan['secrets_chain'],K9_SECRETS_DIRECTORY,receives_entry=True)",
    "rows=validate_chain(plan['secrets_chain'],K9_SECRETS_DIRECTORY,open_root='/var/lib/c3po',receives_entry=True)")
add('V02_a_setgid_secrets_directory',"rows=validate_chain(plan['secrets_chain'],K9_SECRETS_DIRECTORY,receives_entry=True)",
    "rows=validate_chain(plan['secrets_chain'],K9_SECRETS_DIRECTORY)")
add('V03_k9_root_of_any_mode',"    need((rows[-2]['uid'],rows[-2]['gid'],rows[-2]['mode'])==(0,0,K9_SECRETS_DIRECTORY_MODE),'K9_ROOT_NOT_ROOT_0700')\n","")
add('V04_secrets_directory_of_any_owner_and_mode',"    need((rows[-1]['uid'],rows[-1]['gid'],rows[-1]['mode'])==(0,0,K9_SECRETS_DIRECTORY_MODE),'SECRETS_DIRECTORY_NOT_ROOT_0700')\n","")
add('V06_worker_id_not_checked',"    need(text(plan['worker_container_id'],CONTAINER_ID),'WORKER_CONTAINER_UNBOUND')\n","")
add('V07_boot_not_checked',"    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')\n","")

# ---------------------------------------------------------------- the effects the signers see
add('E01_effects_without_the_k9_root',"    return {'operation':OPERATION,'k9_root':K9_ROOT,'placement':'N-8',","    return {'operation':OPERATION,'placement':'N-8',")
add('E02_effects_placement_proposed',"'k9_root':K9_ROOT,'placement':'N-8',","'k9_root':K9_ROOT,'placement':'PROPOSED',")
add('E13_effects_say_an_open_root',"'k9_root':'root:root 0700','open_root':None}),","'k9_root':'root:root 0700','open_root':SOURCE_OPEN_ROOT}),")
add('E03_effects_secrets_directory_without_required',"dict(chain_effects(plan['secrets_chain']),required={'uid':0,'gid':0,'mode_octal':'0700','entries':0,'k9_root':'root:root 0700','open_root':None})","chain_effects(plan['secrets_chain'])")
add('E04_effects_directory_0755',"'creates':{'directory':{'path':K9_EMITTER_DIRECTORY,'uid':0,'gid':0,'mode_octal':'0700'},","'creates':{'directory':{'path':K9_EMITTER_DIRECTORY,'uid':0,'gid':0,'mode_octal':'0755'},")
add('E05_effects_files_without_links',"'files':[{'path':path,'uid':0,'gid':0,'mode_octal':'0600','links':1} for path in TARGET_PATHS]},","'files':[{'path':path,'uid':0,'gid':0,'mode_octal':'0600'} for path in TARGET_PATHS]},")
add('E06_effects_without_the_container_id',"                                      'container_id':plan['worker_container_id']},\n","                                      'container_id':None},\n")
add('E07_effects_without_the_names',"'values':{'provider_env':{'names':[list(pair) for pair in PROVIDER_TOKEN_NAMES],","'values':{'provider_env':{'names':[],")
add('E08_effects_url_from_elsewhere',"'risk_db_env':{'name':RISK_URL_KEY,'from_file':RISK_URL_DIRECTORY+'/'+RISK_URL_NAME},","'risk_db_env':{'name':RISK_URL_KEY,'from_file':RISK_URL_DIRECTORY},")
add('E09_effects_password_from_elsewhere',"'emitter_password':{'from_file':EMITTER_SOURCE_DIRECTORY+'/'+EMITTER_SOURCE_NAME}},","'emitter_password':{'from_file':EMITTER_SOURCE_DIRECTORY}},")
add('E10_effects_without_the_process',"            'process':{'dumpable':0,'when':'first, before anything of the host is looked at'},\n","")
add('E11_effects_another_boot',"            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],\n","            'evidence_boot_id_sha256':None,\n")
add('E12_effects_say_a_value_may_be_in_the_receipt',"'activation':False,'value_in_receipt':False,'size_or_digest_in_receipt':False}","'activation':False,'value_in_receipt':False}")

# ---------------------------------------------------------------- the precheck: order and refusals
add('P01_process_left_dumpable',"            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');process['dumpable_disabled']=True\n","            process['dumpable_disabled']=True\n")
add('P02_any_answer_taken',"need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED')","need(host.not_dumpable() is not None,'PROCESS_DUMPABLE_NOT_DISABLED')")
add('P03_not_dumpable_after_the_executor',"            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');process['dumpable_disabled']=True\n            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n",
    "            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');process['dumpable_disabled']=True\n")
add('P04_executor_not_checked',"            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n","")
add('P05_umask_not_set',"            host.umask(0o077)\n","")
add('P06_umask_0022',"            host.umask(0o077)\n","            host.umask(0o022)\n")
add('P07_boot_not_compared',"            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n","")
add('P08_secrets_directory_need_not_be_empty',"            need(secrets['empty'],'SECRETS_DIRECTORY_NOT_EMPTY')\n","")
add('P09_one_entry_is_empty',"secrets['empty']=count_entries(host,target.fd,gate)==0","secrets['empty']=count_entries(host,target.fd,gate)<=1")
add('P11_budget_not_checked',"            need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')\n","")
add('P12_budget_strictly_more',"need(left>=WRITE_ALLOWANCE_SECONDS,","need(left>WRITE_ALLOWANCE_SECONDS,")
add('P13_directory_not_proved_again',"            target.verify(gate)\n            code=None\n","            code=None\n")
add('P14_seconds_left_not_said',"left=gate();precheck['seconds_left_before_the_first_effect']=int(left)","left=gate()")
add('P15_buffers_not_zeroed',"        for buffer in buffers:zero(buffer)\n","")
add('P16_zero_does_nothing',"        for index in range(len(buffer)):buffer[index]=0\n","        pass\n")

# ---------------------------------------------------------------- the worker and its environment
add('W01_worker_not_in_the_list_accepted',"    need(facts['one_container_with_the_name'] and facts['id_equal_signed'],'WORKER_CONTAINER_MISMATCH')\n","")
add('W02_another_id_accepted',"need(facts['one_container_with_the_name'] and facts['id_equal_signed'],'WORKER_CONTAINER_MISMATCH')","need(facts['one_container_with_the_name'],'WORKER_CONTAINER_MISMATCH')")
add('W03_stopped_worker_accepted',"    need(facts['running'],'WORKER_NOT_RUNNING')\n","")
add('W04_running_said_by_the_inspect_only',"facts['running']=row['running'] is True and row['state']=='running' and listed_rows[0]['state']=='running'","facts['running']=row['running'] is True")
add('W05_inspect_by_name',"    row=container_facts(commands,worker,expected_name=WORKER_CONTAINER_NAME)\n","    row=container_facts(commands,WORKER_CONTAINER_NAME)\n")
add('W06_one_read_only',"    second=token_values(commands,worker);buffers.extend(second.values())\n","    second=first\n")
add('W07_presence_not_compared',"read_twice_equal=sorted(first)==sorted(second) and all(first[name]==second[name] for name in first))","read_twice_equal=all(first[name]==second.get(name) for name in first))")
add('W08_change_not_refused',"    need(facts['read_twice_equal'],'WORKER_ENVIRONMENT_CHANGED_DURING_READ')\n","")
add('W12_disagreement_accepted',"        need(all(value==present[0] for value in present),'PROVIDER_TOKEN_DEFINITIONS_DISAGREE')\n","")
add('W14_first_values_not_zeroed',"    first=token_values(commands,worker);buffers.extend(first.values())\n","    first=token_values(commands,worker)\n")
add('W15_second_values_not_zeroed',"    second=token_values(commands,worker);buffers.extend(second.values())\n","    second=token_values(commands,worker)\n")
add('W16_content_not_zeroed',"    content=bytearray();buffers.append(content)\n    for (name,_),value","    content=bytearray()\n    for (name,_),value")
add('W17_line_without_its_newline',"content.extend(name.encode('ascii'));content.extend(b'=');content.extend(value);content.extend(b'\\n')","content.extend(name.encode('ascii'));content.extend(b'=');content.extend(value)")
add('W18_names_present_said_of_the_second_read',"names_present={name:name in first for name in SECRET_ENVIRONMENT_NAMES}","names_present={name:True for name in SECRET_ENVIRONMENT_NAMES}")

add('W09_absent_token_accepted',"    need(all(any(name in first for name in pair) for pair in PROVIDER_TOKEN_NAMES),'PROVIDER_TOKEN_ABSENT')\n","")
add('W10_grammar_not_checked',"    need(all(value is not None and re.fullmatch(PROVIDER_TOKEN_GRAMMAR,value) is not None for value in first.values()),'PROVIDER_TOKEN_GRAMMAR')\n","")
add('W11_a_value_the_core_did_not_copy_accepted',"need(all(value is not None and re.fullmatch(PROVIDER_TOKEN_GRAMMAR,value) is not None for value in first.values()),","need(all(value is None or re.fullmatch(PROVIDER_TOKEN_GRAMMAR,value) is not None for value in first.values()),")
add('W13_output_limit_code_leaks',"        if str(error)=='COMMAND_OUTPUT_LIMIT':raise Refused('PROVIDER_TOKEN_GRAMMAR') from None\n","")
add('W19_grammar_before_presence',"    need(all(any(name in first for name in pair) for pair in PROVIDER_TOKEN_NAMES),'PROVIDER_TOKEN_ABSENT')\n    need(all(value is not None and re.fullmatch(PROVIDER_TOKEN_GRAMMAR,value) is not None for value in first.values()),'PROVIDER_TOKEN_GRAMMAR')\n",
    "    need(all(value is not None and re.fullmatch(PROVIDER_TOKEN_GRAMMAR,value) is not None for value in first.values()),'PROVIDER_TOKEN_GRAMMAR')\n    need(all(any(name in first for name in pair) for pair in PROVIDER_TOKEN_NAMES),'PROVIDER_TOKEN_ABSENT')\n")

# ---------------------------------------------------------------- the files of September
add('S07_second_link_accepted',"        need(named.st_nlink==1,prefix+'_FILE_LINKED');","        need(named.st_nlink>=1,prefix+'_FILE_LINKED');")
add('S08_not_regular_accepted',"        need(stat.S_ISREG(named.st_mode),prefix+'_FILE_NOT_REGULAR');","        need(True,prefix+'_FILE_NOT_REGULAR');")
add('S09_change_while_read_accepted',"        need(stat_signature(info)==stat_signature(named)==stat_signature(after),prefix+'_FILE_CHANGED_DURING_READ')\n","")
add('S10_too_large_has_its_own_code',"'FILE_TOO_LARGE':'FORMAT',","'FILE_TOO_LARGE':'FILE_TOO_LARGE',")
add('S11_readable_fact_inverted',"facts['not_readable_by_group_or_other']=not named.st_mode&0o044","facts['not_readable_by_group_or_other']=not named.st_mode&0o004")
add('S12_url_two_newlines_accepted',"        value=view[:-1] if raw[-1:]==b'\\n' else view\n","        value=view[:len(raw.rstrip(b'\\n'))]\n")
add('S14_url_line_without_its_newline',"content.extend(RISK_URL_KEY.encode('ascii'));content.extend(b'=');content.extend(value);content.extend(b'\\n')","content.extend(RISK_URL_KEY.encode('ascii'));content.extend(b'=');content.extend(value)")
add('S15_password_with_a_newline_added',"    content=bytearray(raw);buffers.append(content);return content\n","    content=bytearray(raw+b'\\n');buffers.append(content);return content\n")
add('S16_facts_of_the_url_said_before_its_grammar',"        need(re.fullmatch(RISK_URL_GRAMMAR,value) is not None,'RISK_URL_FORMAT')\n        facts.update(unchanged_during_read=True,grammar_met=True)\n",
    "        facts.update(unchanged_during_read=True,grammar_met=re.fullmatch(RISK_URL_GRAMMAR,value) is not None)\n        need(facts['grammar_met'],'RISK_URL_FORMAT')\n")
add('S17_facts_of_the_password_said_before_its_grammar',"    need(re.fullmatch(EMITTER_PASSWORD_GRAMMAR,raw) is not None,'EMITTER_PASSWORD_FORMAT')\n    facts.update(unchanged_during_read=True,grammar_met=True)\n",
    "    facts.update(unchanged_during_read=True,grammar_met=re.fullmatch(EMITTER_PASSWORD_GRAMMAR,raw) is not None)\n    need(facts['grammar_met'],'EMITTER_PASSWORD_FORMAT')\n")
add('S18_url_content_not_zeroed',"        content=bytearray();buffers.append(content)\n        content.extend(RISK_URL_KEY","        content=bytearray()\n        content.extend(RISK_URL_KEY")
add('S19_password_content_not_zeroed',"    content=bytearray(raw);buffers.append(content);return content\n","    content=bytearray(raw);return content\n")
add('S23_absent_file_with_another_code',"        except FileNotFoundError:raise Refused(prefix+'_FILE_ABSENT') from None\n        facts['present']=True\n","        except FileNotFoundError:raise Refused(prefix+'_DIRECTORY_ABSENT') from None\n        facts['present']=True\n")

add('P10_sources_read_before_the_docker_commands',"            provider=provider_content(commands,worker,workers,buffers)\n            volume,sources=plan['data_volume_chain'],plan['source_rows']\n",
    "            volume,sources=plan['data_volume_chain'],plan['source_rows']\n            source_bytes(host,'RISK_URL',volume+sources[0:2],RISK_URL_MAX_FILE_BYTES,gate,source_facts())\n            provider=provider_content(commands,worker,workers,buffers)\n")
add('S01_component_opened_before_it_is_compared',"            need(stat.S_ISDIR(named.st_mode) and as_signed(named,row),prefix+'_COMPONENT_DIVERGES')\n","            need(stat.S_ISDIR(named.st_mode),prefix+'_COMPONENT_DIVERGES')\n")
add('S02_component_not_compared_at_all',"            need(stat.S_ISDIR(named.st_mode) and as_signed(named,row),prefix+'_COMPONENT_DIVERGES')\n","            need(stat.S_ISDIR(named.st_mode),prefix+'_COMPONENT_DIVERGES')\n            row={'mode':stat.S_IMODE(named.st_mode)}\n")
add('S03_root_not_compared',"        need(as_signed(host.fstat(fd),rows[0]),prefix+'_COMPONENT_DIVERGES')\n","")
add('S04_held_descriptor_not_compared',"            need((held.st_dev,held.st_ino)==(named.st_dev,named.st_ino) and as_signed(held,row),prefix+'_COMPONENT_DIVERGES')\n","")
add('S05_file_not_compared',"        need(as_signed(named,rows[-1]),prefix+'_FILE_DIVERGES');facts['file_as_signed']=True\n","        facts['file_as_signed']=True\n")
add('S06_instants_not_compared',"          'mtime_ns':info.st_mtime_ns,'ctime_ns':info.st_ctime_ns}","          }")
add('S13_url_role_not_checked',"        need(facts['userinfo_names_the_restricted_reader'],'RISK_DATABASE_URL_NOT_THE_RESTRICTED_READER')\n","")
add('S20_device_not_compared',"    seen={'device':info.st_dev,'inode':info.st_ino,","    seen={'inode':info.st_ino,")
add('S21_mode_not_compared',"'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode),","'gid':info.st_gid,")
add('S22_absent_component_with_another_code',"            except FileNotFoundError:raise Refused(prefix+'_COMPONENT_ABSENT') from None\n","            except FileNotFoundError:raise Refused(prefix+'_FILE_ABSENT') from None\n")
add('S24_query_parameters_accepted',"        need(facts['no_query_or_fragment'],'RISK_DATABASE_URL_WITH_PARAMETERS')\n","")
add('S25_fragment_accepted',"re.search(rb'[?#]',value) is None","re.search(rb'[?]',value) is None")
add('S26_owner_not_compared',"    seen={'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid,","    seen={'device':info.st_dev,'inode':info.st_ino,")
add('S27_components_fact_said_before_the_walk',"        facts['components_as_signed']=True\n        return fd\n","        return fd\n")

# ---------------------------------------------------------------- the creations, readbacks, withdrawals
add('F01_metadata_gid_not_checked',"    return all(row[key] for key in ('regular','uid_0','gid_0','mode_0600','single_link','on_the_device_of_the_directory'))\n",
    "    return all(row[key] for key in ('regular','uid_0','mode_0600','single_link','on_the_device_of_the_directory'))\n")
add('F02_metadata_mode_not_checked',"    return all(row[key] for key in ('regular','uid_0','gid_0','mode_0600','single_link','on_the_device_of_the_directory'))\n",
    "    return all(row[key] for key in ('regular','uid_0','gid_0','single_link','on_the_device_of_the_directory'))\n")
add('F03_metadata_uid_not_checked',"    return all(row[key] for key in ('regular','uid_0','gid_0','mode_0600','single_link','on_the_device_of_the_directory'))\n",
    "    return all(row[key] for key in ('regular','gid_0','mode_0600','single_link','on_the_device_of_the_directory'))\n")
add('F04_metadata_links_not_checked',"    return all(row[key] for key in ('regular','uid_0','gid_0','mode_0600','single_link','on_the_device_of_the_directory'))\n",
    "    return all(row[key] for key in ('regular','uid_0','gid_0','mode_0600','on_the_device_of_the_directory'))\n")
add('F05_metadata_device_not_checked',"    return all(row[key] for key in ('regular','uid_0','gid_0','mode_0600','single_link','on_the_device_of_the_directory'))\n",
    "    return all(row[key] for key in ('regular','uid_0','gid_0','mode_0600','single_link'))\n")
add('F06_withdrawal_of_another_inode',"        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino) or named.st_nlink!=1:\n","        if named.st_nlink!=1:\n")
add('F07_withdrawal_of_a_linked_file',"        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino) or named.st_nlink!=1:\n","        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino):\n")
add('F08_withdrawal_not_counted',"        mutate(state,gate,lambda:host.unlink(name,directory.fd))\n","        host.unlink(name,directory.fd)\n")
add('F09_no_fsync_after_withdrawal',"    try:host.fsync(directory.fd)\n    except OSError as error:\n        row.update(withdrawal_code='FSYNC_FAILED',withdrawal_errno=number(error));return row\n    row.update(state='WITHDRAWN',",
    "    row.update(state='WITHDRAWN',")
add('F10_failed_unlink_said_withdrawn',"        row.update(withdrawal_code='SECRET_FILE_WITHDRAWAL_FAILED',withdrawal_errno=number(error));return row\n","        row.update(withdrawal_errno=number(error),withdrawn=True,state='WITHDRAWN');return row\n")
add('F11_readback_inode_not_compared',"    return row['readback_same_inode'] and row['readback_metadata_as_created']\n","    return row['readback_metadata_as_created']\n")
add('F12_readback_metadata_not_compared',"    return row['readback_same_inode'] and row['readback_metadata_as_created']\n","    return row['readback_same_inode']\n")
add('F13_readback_without_noatime',"    fd=host.open(name,READBACK_FLAGS|host.noatime(),dir_fd=directory.fd)\n","    fd=host.open(name,READBACK_FLAGS,dir_fd=directory.fd)\n")
add('F14_readback_without_the_directory_proved',"    directory.verify(gate);gate()\n","    gate()\n")
add('F15_existing_name_said_filesystem_error',"code='SECRET_FILE_APPEARED_AFTER_PRECHECK' if error.errno==errno.EEXIST else filesystem_code(error))","code=filesystem_code(error))")
add('F16_write_of_nothing_accepted',"                    if type(size) is not int or size<=0:return withdraw","                    if type(size) is not int:return withdraw")
add('F17_one_write_only',"                while written<len(content):\n","                if written<len(content):\n")
add('F18_file_not_fsynced',"            try:host.fsync(fd);row['fsync_file']=True\n            except OSError as error:return withdraw(name,fd,row,directory,host,gate,state,'FSYNC_FAILED',error)\n","            row['fsync_file']=True\n")
add('F19_directory_not_fsynced',"            try:host.fsync(directory.fd);row['fsync_directory']=True\n            except OSError as error:return withdraw(name,fd,row,directory,host,gate,state,'FSYNC_FAILED',error)\n","            row['fsync_directory']=True\n")
add('F20_metadata_mismatch_kept',"                if not metadata_facts(info,row,directory):return withdraw(name,fd,row,directory,host,gate,state,'SECRET_FILE_METADATA_MISMATCH')\n","                metadata_facts(info,row,directory)\n")
add('F21_readback_mismatch_kept',"                if not readback(name,info,row,directory,host,gate):return withdraw(name,fd,row,directory,host,gate,state,'READBACK_MISMATCH')\n","                readback(name,info,row,directory,host,gate)\n")
add('F22_withdrawn_after_an_expiry',"                if str(error) in ('GO_EXPIRED','CLOCK_REVERSED','PARENT_REPLACED'):\n","                if str(error) in ('CLOCK_REVERSED','PARENT_REPLACED'):\n")
add('F23_expiry_during_a_write_withdraws',"            except Refused as error:\n                row['code']=code_of(error,'GO_EXPIRED');return row\n            except OSError as error:return withdraw(name,fd,row,directory,host,gate,state,filesystem_code(error),error)\n",
    "            except Refused as error:return withdraw(name,fd,row,directory,host,gate,state,code_of(error,'GO_EXPIRED'))\n            except OSError as error:return withdraw(name,fd,row,directory,host,gate,state,filesystem_code(error),error)\n")
add('F24_other_failure_not_withdrawn',"            if state.pending:state.unknown()\n            return withdraw(name,fd,row,directory,host,gate,state,'SECRET_FILE_PLACEMENT_FAILED')\n","            if state.pending:state.unknown()\n            row['code']='SECRET_FILE_PLACEMENT_FAILED';return row\n")
add('F25_placement_continues_after_a_failure',"                    stop=row['code'] or 'SECRET_FILE_NOT_PLACED';break\n","                    stop=row['code'] or 'SECRET_FILE_NOT_PLACED'\n")
add('F26_secrets_readback_expects_four',"target,host,gate,3)","target,host,gate,4)")
add('F27_emitter_readback_expects_none',"handles['EMITTER'],host,gate,1)","handles['EMITTER'],host,gate,0)")
add('F28_directory_readback_not_judged',"            if readbacks['secrets_directory'] or readbacks['emitter_directory']:stop='DIRECTORY_READBACK_MISMATCH'\n","")
add('F29_password_in_the_secrets_directory',"(rows[2],EMITTER_PASSWORD_NAME,emitter,handles['EMITTER'])","(rows[2],EMITTER_PASSWORD_NAME,emitter,target)")
add('F30_emitter_directory_0750',"directory[0]=create_directory('EMITTER',K9_EMITTER_DIRECTORY,0o700,","directory[0]=create_directory('EMITTER',K9_EMITTER_DIRECTORY,0o750,")
add('F31_files_placed_without_the_directory',"        stop=None if directory[0]['state']=='CREATED_DURABLE' else (directory[0]['code'] or 'EMITTER_DIRECTORY_NOT_CREATED')\n","        stop=None\n")
add('F32_refused_after_a_creation',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n","        if state.counts()['uncertain']==0:return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n")

# ---------------------------------------------------------------- the receipt
add('R01_any_code_through',"def listed(code):return code if code is None or code in RECEIPT_CODES else UNLISTED_CODE","def listed(code):return code")
add('R02_row_codes_not_listed',"        for row in rows:row.update(code=listed(row['code']),withdrawal_code=listed(row['withdrawal_code']))\n","")
add('R03_objects_left_without_the_directory',"    created=0 if directory_row['state'] in ('NOT_ATTEMPTED','NOT_CREATED') else 1\n","    created=0\n")
add('R04_objects_left_without_left_files',"    return created+sum(1 for row in rows if row['state'] in ('PLACED_VERIFIED','LEFT_UNVERIFIED'))\n","    return created+sum(1 for row in rows if row['state']=='PLACED_VERIFIED')\n")
add('R05_uncertain_creation_said_zero',"    if any(row['state']=='CREATE_UNCERTAIN' for row in rows):return None\n","")
add('R06_dumpable_fact_true_before_the_call',"            process['dumpable_disabled']=False\n            need(host.not_dumpable()","            process['dumpable_disabled']=True\n            need(host.not_dumpable()")
add('R07_secrets_empty_fact_not_said',"            secrets['empty']=count_entries(host,target.fd,gate)==0\n            need(secrets['empty'],","            need(count_entries(host,target.fd,gate)==0,")
add('R08_readback_complete_after_a_stop',"        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None}\n","        extra={'phase_reached':'EFFECTS','readback':'COMPLETE'}\n")

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

# Revision 3: the operation no longer uses the inspect template or its start rule.
# Those four mutants are outside this operation's exercised path, not reported as killed.
REMOVED_UNUSED_REV3={'W04_running_said_by_the_inspect_only','W05_inspect_by_name','W13_output_limit_code_leaks',
                     'D01_template_prints_the_other_entries','D02_template_prints_unquoted','D08_line_of_another_name_skipped','N01_secret_row_started_directly'}
MUTANTS=[row for row in MUTANTS if row[0] not in REMOVED_UNUSED_REV3]
updated=[]
for name,target,old,new in MUTANTS:
    if name=='E07_effects_without_the_names':
        old=old.replace("'values':{'provider_env':", "'provider_env':")
        new=new.replace("'values':{'provider_env':", "'provider_env':")
    if name=='P02_any_answer_taken':
        old="process['dumpable_disabled']=False\n            "+old
        new="process['dumpable_disabled']=False\n            "+new
    old=old.replace('token_values(commands,worker)','token_values(commands.host,commands.gate,worker)')
    new=new.replace('token_values(commands,worker)','token_values(commands.host,commands.gate,worker)')
    updated.append((name,target,old,new))
MUTANTS=updated
add('CFG01_root_chain_not_enforced',"need(all(row['uid']==0 and not row['mode']&0o022 for row in observed),'WORKER_CONFIG_CHAIN_UNSAFE')","need(True,'WORKER_CONFIG_CHAIN_UNSAFE')")
add('CFG03_config_metadata_not_enforced',"and stat.S_IMODE(named.st_mode)==0o600,'WORKER_CONFIG_METADATA_UNSAFE')","or True,'WORKER_CONFIG_METADATA_UNSAFE')")
add('CFG04_config_identity_not_enforced',"type(body) is dict and body.get('ID')==worker and body.get('Name')=='/'+WORKER_CONTAINER_NAME","type(body) is dict")
add('CFG05_read_bound_doubled',"WORKER_CONFIG_MAX_BYTES=1048576","WORKER_CONFIG_MAX_BYTES=2097152")
add('CFG06_second_presence_not_checked',"    need(len(after)==1 and after[0]['id']==worker,'WORKER_CONTAINER_MISMATCH')\n","")
add('CFG07_second_running_not_checked',"    need(after[0]['state']=='running','WORKER_NOT_RUNNING')\n","")

add('CFG08_name_descriptor_metadata_not_compared',"need((info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode,info.st_nlink,info.st_mtime_ns,info.st_ctime_ns)==\n             (named.st_dev,named.st_ino,named.st_uid,named.st_gid,named.st_mode,named.st_nlink,named.st_mtime_ns,named.st_ctime_ns),'WORKER_CONFIG_CHANGED')","need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'WORKER_CONFIG_CHANGED')")
