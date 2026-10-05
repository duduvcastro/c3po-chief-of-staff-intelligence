"""The mutants of the core. Each row: (name, target, exact anchor, replacement). The anchor must occur exactly once in
every file the target is applied to (mutate.py check). PORTED are the rows of the sealed HOSTOPS01 list that still
apply unchanged; the rows below are the guarantees this core adds or changes. COMBOS remove one guarantee at every
layer that carries it at once."""
from mutants_ported import PORTED,PORTED_COMBOS,PORTED_REDUNDANT

# one ported row does not fit the new call (its line now stands inside a try block); R43 below replaces it
M=[row for row in PORTED if row[0]!='N05_tool_retried_after_two_timeouts']
def add(name,target,old,new):M.append((name,target,old,new))


# ---------------------------------------------------------------- core: what this core changes in the HOSTOPS01 core
FLAG="    need(type(request['max_seconds']) is int and request['max_seconds']==MAX_SECONDS and request['writes_allowed'] is WRITES_ALLOWED\n         and request['activation_allowed'] is ACTIVATION_ALLOWED,'REQUEST_SCOPE')\n"
add('K01_request_activation_flag_dropped','core',FLAG,FLAG.replace("\n         and request['activation_allowed'] is ACTIVATION_ALLOWED",""))
add('K02_request_activation_flag_any_boolean','core',FLAG,FLAG.replace("request['activation_allowed'] is ACTIVATION_ALLOWED","type(request['activation_allowed']) is bool"))
add('K03_request_activation_flag_must_be_false_as_in_hostops01','core',FLAG,FLAG.replace("is ACTIVATION_ALLOWED","is False"))
add('K04_request_writes_flag_dropped','core',FLAG,FLAG.replace(" and request['writes_allowed'] is WRITES_ALLOWED",""))
add('K05_request_max_seconds_dropped','core',FLAG,FLAG.replace("type(request['max_seconds']) is int and request['max_seconds']==MAX_SECONDS and ",""))
add('K06_request_max_seconds_type_unchecked','core',FLAG,FLAG.replace("type(request['max_seconds']) is int and ",""))
AUTHORITY_FLAGS="         and authority['writes_allowed'] is WRITES_ALLOWED and authority['activation_allowed'] is ACTIVATION_ALLOWED\n"
add('K07_authority_activation_flag_dropped','core',AUTHORITY_FLAGS,"         and authority['writes_allowed'] is WRITES_ALLOWED\n")
add('K08_authority_writes_flag_dropped','core',AUTHORITY_FLAGS,"         and authority['activation_allowed'] is ACTIVATION_ALLOWED\n")
add('K09_authority_activation_flag_must_be_false','core',AUTHORITY_FLAGS,AUTHORITY_FLAGS.replace("is ACTIVATION_ALLOWED","is False"))
GO_FLAGS="         and go['writes_allowed'] is WRITES_ALLOWED and go['activation_allowed'] is ACTIVATION_ALLOWED\n"
add('K10_go_activation_flag_dropped','core',GO_FLAGS,"         and go['writes_allowed'] is WRITES_ALLOWED\n")
add('K11_go_writes_flag_dropped','core',GO_FLAGS,"         and go['activation_allowed'] is ACTIVATION_ALLOWED\n")
add('K12_go_activation_flag_must_be_false','core',GO_FLAGS,GO_FLAGS.replace("is ACTIVATION_ALLOWED","is False"))
add('K13_required_evidence_operation_not_required','core',"    need(all(any(item['operation']==name for item in evidence) for name in EVIDENCE_OPERATIONS),'EVIDENCE_OPERATION_MISSING')\n","")
add('K14_one_required_evidence_operation_is_enough','core',"    need(all(any(item['operation']==name for item in evidence) for name in EVIDENCE_OPERATIONS),'EVIDENCE_OPERATION_MISSING')\n",
    "    need(not EVIDENCE_OPERATIONS or any(item['operation'] in EVIDENCE_OPERATIONS for item in evidence),'EVIDENCE_OPERATION_MISSING')\n")
DAYS="EPOCH_DAYS=('2026-10-02','2026-10-03','2026-10-04','2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10')\n"
add('K15_epoch_ends_one_day_earlier','core',DAYS,DAYS.replace(",'2026-10-10'",""))
add('K16_epoch_goes_on_one_more_day','core',DAYS,DAYS.replace("'2026-10-10')","'2026-10-10','2026-10-11')"))
add('K17_epoch_starts_one_day_earlier','core',DAYS,DAYS.replace("('2026-10-02'","('2026-10-01','2026-10-02'"))
add('K18_weekend_writes_reach_the_first_session_day','core',"'WRITE_WEEKEND':EPOCH_DAYS[:3],","'WRITE_WEEKEND':EPOCH_DAYS[:4],")
add('K19_first_session_class_holds_two_days','core',"'WRITE_FIRST_SESSION':EPOCH_DAYS[3:4],","'WRITE_FIRST_SESSION':EPOCH_DAYS[3:5],")
add('K20_first_session_class_is_the_weekend','core',"'WRITE_FIRST_SESSION':EPOCH_DAYS[3:4],","'WRITE_FIRST_SESSION':EPOCH_DAYS[2:4],")
add('K21_session_writes_start_on_sunday','core',"'WRITE_SESSIONS':EPOCH_DAYS[3:],","'WRITE_SESSIONS':EPOCH_DAYS[2:],")
add('K22_epoch_writes_include_friday_the_second','core',"'WRITE_EPOCH':EPOCH_DAYS[1:]}","'WRITE_EPOCH':EPOCH_DAYS}")
add('K23_read_class_stops_before_the_last_day','core',"DATE_SETS={'READ':EPOCH_DAYS,","DATE_SETS={'READ':EPOCH_DAYS[:-1],")
add('K24_document_size_limit_removed','core',"    need(type(raw) is bytes and 0<len(raw)<=limit,'DOCUMENT_SIZE')\n","    need(type(raw) is bytes and 0<len(raw),'DOCUMENT_SIZE')\n")
add('K25_document_limit_argument_ignored','core',"    need(type(raw) is bytes and 0<len(raw)<=limit,'DOCUMENT_SIZE')\n","    need(type(raw) is bytes and 0<len(raw)<=65536,'DOCUMENT_SIZE')\n")
add('K26_receipt_does_not_name_the_core','core',"'scope_sha256':SCOPE_SHA256,'core_sha256':CORE_SHA256,'activation_performed':False","'scope_sha256':SCOPE_SHA256,'activation_performed':False")
add('K27_escape_of_a_switching_source_says_false','core',"        unknown={'activation_performed':None,'daemon_reload_performed':None} if ACTIVATION_ALLOWED else {}\n","        unknown={}\n")
add('K28_minimum_receipt_loses_the_core_hash','core',"'host_binding_sha256','scope_sha256','core_sha256','mutating_calls'","'host_binding_sha256','scope_sha256','mutating_calls'")
add('K29_timing_raises_when_a_clock_fails','core',"        return {'utc_start':begun.isoformat(),'utc_end':ended.isoformat(),'monotonic_elapsed_ms':int(elapsed*1000)}\n    except Exception:return None\n",
    "        return {'utc_start':begun.isoformat(),'utc_end':ended.isoformat(),'monotonic_elapsed_ms':int(elapsed*1000)}\n    except KeyError:return None\n")

# ---------------------------------------------------------------- runner: standard input, classes, the budget before an effect
add('R01_working_directory_inherited','runner',"env=environment,cwd=COMMAND_DIRECTORY,\n","env=environment,\n")
add('R02_standard_input_never_closed','runner',"                        if sent>=len(stdin):\n                            selector.unregister(key.fileobj);process.stdin.close()\n",
    "                        if sent>=len(stdin):\n                            selector.unregister(key.fileobj)\n")
add('R03_standard_input_bytes_dropped','runner',"stdin=subprocess.DEVNULL if stdin is None else subprocess.PIPE,","stdin=subprocess.DEVNULL,")
add('R04_only_the_first_block_of_standard_input_is_written','runner',"                        if sent>=len(stdin):\n","                        if sent>0:\n")
add('R05_process_that_cannot_be_created_is_an_ordinary_refusal','runner',"        except OSError:raise NotStarted('COMMAND_NOT_STARTED') from None\n","        except OSError:raise Refused('COMMAND_NOT_STARTED') from None\n")
add('R44_expiry_before_the_process_exists_is_an_ordinary_refusal','runner',"        try:gate()\n        except Refused as error:raise NotStarted(code_of(error,'COMMAND_NOT_STARTED')) from None\n        environment=dict(COMMAND_ENVIRONMENT)","        gate()\n        environment=dict(COMMAND_ENVIRONMENT)")
add('R06_process_that_cannot_be_created_raises_the_os_error','runner',"        except OSError:raise NotStarted('COMMAND_NOT_STARTED') from None\n        output=bytearray()","        except KeyError:raise NotStarted('COMMAND_NOT_STARTED') from None\n        output=bytearray()")
add('R07_output_limit_of_the_call_ignored','runner',"                    output.extend(block);need(len(output)<=limit,'COMMAND_OUTPUT_LIMIT')\n","                    output.extend(block);need(len(output)<=1048576,'COMMAND_OUTPUT_LIMIT')\n")
add('R08_output_limit_removed','runner',"                    output.extend(block);need(len(output)<=limit,'COMMAND_OUTPUT_LIMIT')\n","                    output.extend(block)\n")
add('R09_time_limit_of_the_call_ignored','runner',"            until=time.monotonic()+min(seconds,gate())\n","            until=time.monotonic()+gate()\n")
add('R10_budget_ignored_by_the_time_limit','runner',"            until=time.monotonic()+min(seconds,gate())\n","            until=time.monotonic()+seconds\n")
add('R11_variables_never_passed','runner',"        if variables is not None:environment.update(variables)\n","")
add('R12_timed_out_process_left_running','runner',"            if process.returncode is None:\n","            if process.returncode is None and False:\n")
KILL="                try:os.killpg(process.pid,signal.SIGKILL)\n                except OSError:pass\n"
add('R45_only_the_process_itself_is_killed_not_its_group','runner',KILL,"                process.kill()\n")
add('R46_command_stays_in_the_session_and_group_of_the_run','runner',",\n                                     start_new_session=True)\n",")\n")
add('R47_process_that_already_ended_is_not_a_reason_to_kill_what_it_left','runner',"            if process.returncode is None:\n","            if process.poll() is None:\n")
CALL=("            need(through==(TEMPLATE_AT_CALL_TIME if row['argv'][-1:]==['--format'] else STARTED_THROUGH[row['kind']])\n"
      "                 and (row['kind']!='EFFECT' or WRITES_ALLOWED is True),'COMMAND_KIND')\n")
add('R13_effect_row_startable_without_being_counted','runner',CALL,"            need(row['kind']!='EFFECT' or WRITES_ALLOWED is True,'COMMAND_KIND')\n")
add('R14_effect_row_startable_in_a_reading_source','runner',CALL,CALL.replace("\n                 and (row['kind']!='EFFECT' or WRITES_ALLOWED is True)",""))
add('R48_container_row_startable_directly','runner',CALL,CALL.replace("need(through==(","need((row['kind']=='CONTAINER' and through is None) or through==("))
add('R49_row_with_a_template_at_call_time_startable_directly','runner',CALL,CALL.replace("need(through==(","need((row['argv'][-1:]==['--format'] and through is None) or through==("))
add('R50_any_helper_starts_any_row','runner',CALL,CALL.replace("need(through==(TEMPLATE_AT_CALL_TIME if row['argv'][-1:]==['--format'] else STARTED_THROUGH[row['kind']])","need((through is None)==(row['kind']=='READ' and row['argv'][-1:]!=['--format'])"))
add('R51_container_helper_is_the_way_in_for_effect_rows_too','runner',"STARTED_THROUGH={'READ':None,'CONTAINER':'container_run','EFFECT':'effect'}\n","STARTED_THROUGH={'READ':None,'CONTAINER':'container_run','EFFECT':'container_run'}\n")
BUDGET="            if row['kind']!='READ':need(remaining>=limits['seconds']+AFTER_EFFECT_RESERVE_SECONDS,'COMMAND_NOT_STARTED_BUDGET')\n"
add('R15_budget_rule_before_an_effect_removed','runner',BUDGET,"")
add('R16_budget_rule_without_the_reserve','runner',BUDGET,BUDGET.replace("limits['seconds']+AFTER_EFFECT_RESERVE_SECONDS","limits['seconds']"))
add('R17_budget_rule_for_effects_only_not_for_container_runs','runner',BUDGET,BUDGET.replace("if row['kind']!='READ'","if row['kind']=='EFFECT'"))
add('R18_budget_rule_strict_inequality','runner',BUDGET,BUDGET.replace("remaining>=","remaining>"))
add('R19_refusal_before_a_process_is_not_marked_not_started','runner',"        except Refused as error:raise NotStarted(code_of(error,'COMMAND_NOT_STARTED')) from None\n        self.calls+=1\n","        except Refused as error:raise Refused(code_of(error,'COMMAND_NOT_STARTED')) from None\n        self.calls+=1\n")
add('R20_standard_input_scope_of_the_row_unchecked','runner',"            need((stdin is not None) is row['stdin'] and (stdin is None or (type(stdin) is bytes and 0<len(stdin)<=MAX_STDIN_BYTES)),'COMMAND_STDIN')\n",
    "            need(stdin is None or (type(stdin) is bytes and 0<len(stdin)<=MAX_STDIN_BYTES),'COMMAND_STDIN')\n")
add('R21_standard_input_size_and_type_unchecked','runner',"            need((stdin is not None) is row['stdin'] and (stdin is None or (type(stdin) is bytes and 0<len(stdin)<=MAX_STDIN_BYTES)),'COMMAND_STDIN')\n",
    "            need((stdin is not None) is row['stdin'],'COMMAND_STDIN')\n")
VARIABLES="""            need(variables is None or (type(variables) is dict and all(key in COMMAND_VARIABLES and key!='DOCKER_CONFIG'
                                                                       and text(value,COMMAND_VARIABLES[key]) for key,value in variables.items())),'COMMAND_VARIABLES')
"""
add('R22_any_variable_may_be_added_to_the_environment','runner',VARIABLES,"")
add('R23_variable_values_unchecked','runner',VARIABLES,VARIABLES.replace("\n                                                                       and text(value,COMMAND_VARIABLES[key])",""))
add('R24_docker_config_value_unchecked','runner',"            need(docker_config is None or text(docker_config,COMMAND_VARIABLES['DOCKER_CONFIG']),'COMMAND_VARIABLES')\n","")
ARGUMENTS="""            need((row['middle'] is not None or not middle) and len(middle)<=MAX_ARGUMENTS
                 and all(type(item) is str and item and '\\x00' not in item and len(item)<=8192 for item in middle),'COMMAND_ARGUMENTS')
"""
add('R25_arguments_unchecked','runner',ARGUMENTS,"")
add('R26_a_row_without_arguments_takes_arguments','runner',ARGUMENTS,ARGUMENTS.replace("(row['middle'] is not None or not middle) and ",""))
RUN="            result=self.host.run([path]+list(row['argv'])+list(middle)+list(row['tail']),self.gate,limits['seconds'],capture,\n                                 docker_config,stdin,variables,limits['output_bytes'])\n"
add('R27_tail_of_the_row_dropped','runner',RUN,RUN.replace("+list(row['tail'])",""))
add('R28_class_time_not_passed_to_the_runner','runner',RUN,RUN.replace("limits['seconds'],capture","8,capture"))
add('R29_class_output_limit_not_passed_to_the_runner','runner',RUN,RUN.replace("limits['output_bytes']","65536"))
add('R30_standard_input_not_passed_to_the_runner','runner',RUN,RUN.replace("docker_config,stdin,variables","docker_config,None,variables"))
add('R31_started_commands_not_counted_by_kind','runner',"        self.started[row['kind']]+=1;return result\n","        return result\n")
EFFECT="    need(COMMANDS[name]['kind']=='EFFECT','COMMAND_KIND')\n    state.issue()\n"
add('R32_effect_accepts_any_row','runner',EFFECT,"    state.issue()\n")
add('R33_effect_not_issued','runner',EFFECT,"    need(COMMANDS[name]['kind']=='EFFECT','COMMAND_KIND')\n")
add('R34_effect_that_never_started_left_uncertain','runner',"    except NotStarted as error:\n        state.fail();return","    except NotStarted as error:\n        state.unknown();return")
add('R35_effect_that_started_and_did_not_return_called_unchanged','runner',"    except Exception as error:\n        state.unknown();return {'started':True,'returned':False","    except Exception as error:\n        state.fail();return {'started':True,'returned':False")
add('R36_effect_that_returned_settled_as_done_without_a_readback','runner',"    return {'started':True,'returned':True,'returncode':returncode,'output':output,'code':None}\n\n",
    "    state.done();return {'started':True,'returned':True,'returncode':returncode,'output':output,'code':None}\n\n")
add('R37_effect_not_started_through_the_helper','runner',"variables=variables,through='effect')\n    except NotStarted as error:","variables=variables,through=None)\n    except NotStarted as error:")
add('R38_effects_budget_without_the_reserve','runner',"for name in names)+AFTER_EFFECT_RESERVE_SECONDS\n","for name in names)\n")
add('R39_effects_budget_accepts_read_rows','runner',"    need(all(COMMANDS[name]['kind']!='READ' for name in names),'COMMAND_KIND')\n","")
add('R40_reserve_shortened','runner',"AFTER_EFFECT_RESERVE_SECONDS=4\n","AFTER_EFFECT_RESERVE_SECONDS=1\n")
add('R41_recreate_class_longer','runner',"'RECREATE':{'seconds':30,","'RECREATE':{'seconds':45,")
add('R42_run_class_shorter','runner',"'RUN':{'seconds':40,","'RUN':{'seconds':20,")
add('R43_tool_started_again_after_two_timeouts','runner',"            need(self.timeouts.get(tool,0)<MAX_TOOL_TIMEOUTS,'COMMAND_SKIPPED_AFTER_TIMEOUT')\n","")

# ---------------------------------------------------------------- docker: metadata, the attached run, compose
FACTS="    need(set(row)==set(CONTAINER_KEYS) and (row['id']==target if text(target,CONTAINER_ID) else row['name']=='/'+target)\n         and (expected_name is None or row['name']=='/'+expected_name)\n"
add('D01_container_identity_of_the_answer_not_compared','docker',FACTS,"    need(set(row)==set(CONTAINER_KEYS)\n         and (expected_name is None or row['name']=='/'+expected_name)\n")
add('D02_container_expected_name_not_compared','docker',FACTS,FACTS.replace("\n         and (expected_name is None or row['name']=='/'+expected_name)",""))
add('D03_container_restart_count_shape_unchecked','docker',"and integer(row['host_pid']) and integer(row['restarts']) and","and integer(row['host_pid']) and")
add('D04_container_state_word_unchecked','docker',"and type(row['state']) is str and row['state'] in CONTAINER_STATES\n         and (row['health']","\n         and (row['health']")
add('D05_container_running_flag_type_unchecked','docker',"and type(row['running']) is bool\n","\n")
add('D06_container_image_id_shape_unchecked','docker',"and text(row['id'],CONTAINER_ID) and text(row['image_id'],IMAGE_ID)\n","and text(row['id'],CONTAINER_ID)\n")
add('D07_container_target_grammar_unchecked','docker',"    need(text(target,CONTAINER_NAME) and (expected_name is None or text(expected_name,CONTAINER_NAME)),'CONTAINER_TARGET')\n","")
add('D08_duplicate_container_rows_accepted','docker',"    need(len({row['id'] for row in rows})==len(rows),'CONTAINER_LIST_INVALID')\n","")
add('D09_container_list_unbounded','docker',"        rows.append(row);need(len(rows)<=MAX_CONTAINERS,'CONTAINER_LIST_INVALID')\n","        rows.append(row)\n")
add('D10_container_list_row_shape_unchecked','docker',"        need(set(row)=={'id','name','state'} and text(row['id'],CONTAINER_ID) and text(row['name'],CONTAINER_NAME)\n             and type(row['state']) is str and row['state'] in CONTAINER_STATES,'CONTAINER_LIST_INVALID')\n","")
add('D11_container_list_not_sorted','docker',"    return sorted(rows,key=lambda row:row['id'])\n","    return rows\n")
EXPECTATION="""    need(type(expected) is dict and 0<len(expected)<=MAX_ENVIRONMENT_NAMES
         and all(text(key,ENVIRONMENT_NAME) and text(value,ENVIRONMENT_VALUE) for key,value in expected.items()),'ENVIRONMENT_EXPECTATION')
"""
add('D12_environment_value_grammar_unchecked','docker',EXPECTATION,EXPECTATION.replace(" and text(value,ENVIRONMENT_VALUE)",""))
add('D13_environment_name_grammar_unchecked','docker',EXPECTATION,EXPECTATION.replace("text(key,ENVIRONMENT_NAME) and ",""))
add('D14_environment_expectation_may_be_empty_or_long','docker',EXPECTATION,EXPECTATION.replace("0<len(expected)<=MAX_ENVIRONMENT_NAMES\n         and ",""))
add('D15_environment_equal_whenever_the_name_is_present','docker',"{{ $p = true }}{{ if eq . \"'+key+'='+expected[key]+'\" }}{{ $e = true }}{{ end }}{{ end }}{{ end }}'","{{ $p = true }}{{ $e = true }}{{ end }}{{ end }}'")
add('D16_environment_name_compared_as_a_prefix_of_the_entry','docker',"'{{ if eq (index $pieces 0) \"'+key+'\" }}","'{{ if eq (index (split (index $pieces 0) \"_\") 0) (index (split \"'+key+'\" \"_\") 0) }}")
add('D17_environment_of_a_container_asked_by_name','docker',"    need(text(target,CONTAINER_ID),'CONTAINER_TARGET')\n    row=decode(commands.output('container_environment'","    row=decode(commands.output('container_environment'")
add('D18_environment_answer_shape_unchecked','docker',"    need(set(row)==set(expected) and all(type(item) is dict and set(item)=={'present','equal'} and type(item['present']) is bool\n                                         and type(item['equal']) is bool and (item['present'] or not item['equal']) for item in row.values()),\n         'ENVIRONMENT_METADATA_INVALID')\n","")
MOUNT="""    need(type(mount) is dict and set(mount)=={'source','target','read_only'} and type(mount['read_only']) is bool
         and all(text(mount[key],MOUNT_PATH) and clean_path(mount[key]) for key in ('source','target')),'MOUNT_INVALID')
"""
add('D19_mount_path_grammar_unchecked','docker',MOUNT,MOUNT.replace("text(mount[key],MOUNT_PATH) and ",""))
add('D20_mount_path_not_a_clean_path','docker',MOUNT,MOUNT.replace(" and clean_path(mount[key])",""))
add('D22_mount_read_only_flag_type_unchecked','docker',MOUNT,MOUNT.replace(" and type(mount['read_only']) is bool",""))
add('D23_read_only_bind_written_as_read_write','docker',"mount['target'],',readonly' if mount['read_only'] else '')","mount['target'],'')")
add('D24_every_bind_read_only','docker',"mount['target'],',readonly' if mount['read_only'] else '')","mount['target'],',readonly')")
add('D25_container_row_takes_a_writable_bind','docker',"    need(row['kind']=='EFFECT' or all(mount['read_only'] for mount in mounts),'MOUNT_NOT_READ_ONLY')\n","")
add('D26_image_may_be_a_reference','docker',"    need(text(image_id,IMAGE_ID),'IMAGE_ID')\n    need(type(mounts) is list","    need(type(mounts) is list")
add('D27_two_binds_on_one_target','docker',"    need(len({mount['target'] for mount in mounts})==len(mounts),'MOUNT_INVALID')\n","")
add('D28_number_of_binds_unbounded','docker',"    need(type(mounts) is list and len(mounts)<=MAX_MOUNTS,'MOUNT_INVALID')\n","    need(type(mounts) is list,'MOUNT_INVALID')\n")
COMMAND="""    need(type(command) is list and 0<len(command)<=MAX_RUN_WORDS and all(text(word,RUN_WORD) for word in command)
         and not command[0].startswith('-'),'RUN_COMMAND_INVALID')
"""
add('D29_run_command_words_unchecked','docker',COMMAND,COMMAND.replace(" and all(text(word,RUN_WORD) for word in command)",""))
add('D30_run_command_may_begin_with_an_option','docker',COMMAND,COMMAND.replace("\n         and not command[0].startswith('-')",""))
add('D31_run_arguments_for_any_row','docker',"    need(row['tool']=='docker' and row['argv'][:2]==['run','--rm'] and row['kind'] in ('CONTAINER','EFFECT') and row['stdin'] is True,'COMMAND_KIND')\n","")
add('D32_container_name_grammar_unchecked','docker',"    need(container_name is None or text(container_name,'[a-z0-9][a-z0-9_.-]{0,62}'),'CONTAINER_TARGET')\n","")
add('D33_container_run_starts_an_effect_row_uncounted','docker',"    need(COMMANDS[name]['kind']=='CONTAINER','COMMAND_KIND')\n","")
add('D34_container_run_raises_for_a_timeout','docker',"    except Exception as error:return {'started':True,'returned':False,'returncode':None,'output':b'','code':code_of(error,'COMMAND_FAILED')}\n    return {'started':True,'returned':True,'returncode':returncode,'output':output,'code':None}\n\ndef container_effect",
    "    return {'started':True,'returned':True,'returncode':returncode,'output':output,'code':None}\n\ndef container_effect")
add('D35_container_run_calls_a_run_that_never_started_started','docker',"    except NotStarted as error:return {'started':False,'returned':False,'returncode':None,'output':b'','code':code_of(error,'COMMAND_NOT_STARTED')}\n    except Exception as error:return {'started':True,'returned':False",
    "    except NotStarted as error:return {'started':True,'returned':False,'returncode':None,'output':b'','code':code_of(error,'COMMAND_NOT_STARTED')}\n    except Exception as error:return {'started':True,'returned':False")
add('D36_several_lines_accepted_as_one','docker',"    need(type(raw) is bytes and raw.endswith(b'\\n') and raw.count(b'\\n')==1,'RUN_OUTPUT_NOT_ONE_LINE')\n    return decode(raw[:-1])\n",
    "    need(type(raw) is bytes and raw.endswith(b'\\n'),'RUN_OUTPUT_NOT_ONE_LINE')\n    return decode(raw.split(b'\\n')[0])\n")
ARGS="    out=['--project-name',project,'--env-file',env_file]\n    for item in files:out+=['-f',item]\n    return out+(['-f','-'] if standard_input_last else [])\n"
add('D37_compose_without_the_project_name','docker',ARGS,ARGS.replace("['--project-name',project,'--env-file',env_file]","['--env-file',env_file]"))
add('D38_compose_without_the_environment_file','docker',ARGS,ARGS.replace("['--project-name',project,'--env-file',env_file]","['--project-name',project]"))
add('D39_compose_without_the_file_list','docker',ARGS,ARGS.replace("    for item in files:out+=['-f',item]\n",""))
add('D40_compose_only_the_first_file','docker',ARGS,ARGS.replace("for item in files:","for item in files[:1]:"))
add('D41_compose_standard_input_never_named','docker',ARGS,ARGS.replace("out+(['-f','-'] if standard_input_last else [])","out"))
add('D42_compose_project_grammar_unchecked','docker',"    need(text(project,COMPOSE_PROJECT),'COMPOSE_PROJECT')\n","")
FILES="""    need(type(env_file) is str and clean_path(env_file) and env_file!='/' and type(files) is list and 0<len(files)<=MAX_COMPOSE_FILES
         and all(type(item) is str and clean_path(item) and item!='/' for item in files) and len(set(files))==len(files),'COMPOSE_FILES')
"""
add('D43_compose_file_paths_unchecked','docker',FILES,FILES.replace("all(type(item) is str and clean_path(item) and item!='/' for item in files) and ",""))
add('D44_compose_file_list_may_be_empty','docker',FILES,FILES.replace("0<len(files)<=MAX_COMPOSE_FILES","len(files)<=MAX_COMPOSE_FILES"))
add('D45_compose_file_list_unbounded_and_repeated','docker',FILES,FILES.replace("0<len(files)<=MAX_COMPOSE_FILES","0<len(files)").replace(" and len(set(files))==len(files)",""))
add('D46_compose_environment_file_unchecked','docker',FILES,FILES.replace("type(env_file) is str and clean_path(env_file) and env_file!='/' and ",""))
RENDER_ROW="""    need(row['tool']=='docker' and row['argv']==['compose'] and row['tail']==COMPOSE_CONFIG_TAIL and row['kind']=='READ'
         and row['stdin'] is (override is not None),'COMMAND_KIND')
"""
add('D47_render_through_any_row','docker',RENDER_ROW,"")
add('D48_render_without_the_build_revision','docker',"stdin=override,\n                        variables={'C3PO_BUILD_SHA':build_sha})","stdin=override,\n                        variables=None)")
add('D49_render_that_is_not_an_object_accepted','docker',"    need(type(value) is dict and type(value.get('services')) is dict,'COMPOSE_RENDER_INVALID')\n    return value\n","    return value\n")
add('D50_render_failure_keeps_the_parser_code','docker',"    except Refused:raise Refused('COMPOSE_RENDER_INVALID') from None\n","    except Refused:raise\n")
SERVICE="""    need(type(row) is dict and type(row.get('image')) is str and row['image'] and type(row.get('environment',{})) is dict
         and all(type(key) is str and (value is None or type(value) is str) for key,value in row.get('environment',{}).items()),'COMPOSE_SERVICE_INVALID')
"""
add('D51_rendered_service_shape_unchecked','docker',SERVICE,"    need(type(row) is dict,'COMPOSE_SERVICE_INVALID')\n")
UP_ROW="""    need(row['tool']=='docker' and row['argv']==['compose'] and row['tail'][:1]==['up'] and row['tail']==compose_up_tail(row['tail'][-1])
         and row['stdin'] is False,'COMMAND_KIND')
"""
add('D52_recreate_through_any_row','docker',UP_ROW,"")
add('D53_recreate_without_the_build_revision','docker',"capture=False,docker_config=docker_config,\n                  variables={'C3PO_BUILD_SHA':build_sha})","capture=False,docker_config=docker_config,\n                  variables=None)")
add('D54_recreate_output_captured','docker',"*compose_arguments(project,env_file,files),capture=False,docker_config=docker_config,","*compose_arguments(project,env_file,files),capture=True,docker_config=docker_config,")
TAIL="    return ['up','-d','--no-deps','--no-build','--pull','never','--force-recreate',service]\n"
add('D55_recreate_with_dependencies','docker',TAIL,TAIL.replace("'--no-deps',",""))
add('D56_recreate_may_build','docker',TAIL,TAIL.replace("'--no-build',",""))
add('D57_recreate_may_pull','docker',TAIL,TAIL.replace("'--pull','never',",""))
add('D58_recreate_not_forced','docker',TAIL,TAIL.replace("'--force-recreate',",""))
add('D59_recreate_attached','docker',TAIL,TAIL.replace("'-d',",""))
add('D60_compose_service_grammar_unchecked','docker',"    need(text(service,COMPOSE_SERVICE),'COMPOSE_SERVICE')\n","")
PREFIX="RUN_PREFIX=['run','--rm','-i','--pull','never','--init','--user','0:0','--network','none','--read-only','--cap-drop','ALL',\n            '--security-opt','no-new-privileges']\n"
for label,old,new in (('with_a_network',"'--network','none',","'--network','bridge',"),('that_may_pull',"'--pull','never',",""),('that_stays',"'--rm',",""),
                      ('with_a_writable_root',"'--read-only',",""),('with_capabilities',"'--cap-drop','ALL',",""),('without_standard_input',"'-i',",""),
                      ('as_another_user',"'--user','0:0',","'--user','1000:1000',"),('with_new_privileges',"'--cap-drop','ALL',\n            '--security-opt','no-new-privileges']","'--cap-drop','ALL']"),
                      ('without_an_init_process',"'--init',","")):
    add('D61_container_'+label,'docker',PREFIX,PREFIX.replace(old,new))

# ---------------------------------------------------------------- parents: which signed rows are accepted
add('P01_any_owner_accepted_outside_an_open_root','parents',"    if open_root is None or not inside(row['path'],open_root):return 'CHAIN_ROW_UNSAFE'\n","    if open_root is None:return 'CHAIN_ROW_UNSAFE'\n")
add('P02_world_writable_directory_accepted_inside_an_open_root','parents',"    return 'CHAIN_ROW_WORLD_WRITABLE' if world_writable_without_sticky(row) else None\n","    return None\n")
add('P03_sticky_bit_does_not_excuse','parents',"def world_writable_without_sticky(row):return bool(row['mode']&0o002) and not row['mode']&stat.S_ISVTX\n","def world_writable_without_sticky(row):return bool(row['mode']&0o002)\n")
add('P04_group_writable_counted_as_world_writable','parents',"def world_writable_without_sticky(row):return bool(row['mode']&0o002) and not row['mode']&stat.S_ISVTX\n","def world_writable_without_sticky(row):return bool(row['mode']&0o022) and not row['mode']&stat.S_ISVTX\n")
add('P05_setgid_parent_accepted','parents',"    need(not receives_entry or not rows[-1]['mode']&stat.S_ISGID,'PARENT_SETGID')\n","")
add('P06_setgid_refused_even_when_nothing_is_created_there','parents',"    need(not receives_entry or not rows[-1]['mode']&stat.S_ISGID,'PARENT_SETGID')\n","    need(not rows[-1]['mode']&stat.S_ISGID,'PARENT_SETGID')\n")
add('P07_open_root_unchecked','parents',"    need(open_root is None or (type(open_root) is str and clean_path(open_root) and open_root!='/'),'PATH_INVALID')\n","")
add('P08_open_root_may_be_the_whole_tree','parents',"clean_path(open_root) and open_root!='/'),'PATH_INVALID')","clean_path(open_root)),'PATH_INVALID')")
add('P09_rows_of_the_chain_not_validated','parents',"    rows=chain_rows(rows,path)\n    for row in rows:\n        code=row_accepted","    for row in rows:\n        code=row_accepted")
add('P10_chain_effects_name_the_first_row','parents',"return {'path':rows[-1]['path'],'row':rows[-1],","return {'path':rows[-1]['path'],'row':rows[0],")
add('P11_chain_hash_of_the_last_row_only','parents',"'chain_sha256':sha(canonical(rows)),","'chain_sha256':sha(canonical(rows[-1:])),")
add('P12_free_bytes_counts_blocks_reserved_for_root','parents',"    return numbers.f_bavail*numbers.f_frsize\n","    return numbers.f_bfree*numbers.f_frsize\n")
add('P13_signature_without_the_content_change_instants','parents',"return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_uid","return (info.st_dev,info.st_ino,info.st_size,info.st_uid")
add('P14_signature_without_identity','parents',"return (info.st_dev,info.st_ino,info.st_size,","return (info.st_size,")
add('P15_signature_without_owner_and_mode','parents',"info.st_ctime_ns,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))","info.st_ctime_ns)")

# ---------------------------------------------------------------- files: what this core adds to the installer's body
add('F01_directory_mode_unchecked_before_the_mkdir','files',"    if not (type(mode) is int and mode in DIRECTORY_MODES and named_in(path,parent)):\n","    if not named_in(path,parent):\n")
add('F02_directory_path_not_tied_to_the_pinned_parent','files',"    if not (type(mode) is int and mode in DIRECTORY_MODES and named_in(path,parent)):\n","    if not (type(mode) is int and mode in DIRECTORY_MODES):\n")
REQUEST="""    if not (type(content) is bytes and 0<len(content)<=MAX_FILE_BYTES and type(mode) is int and mode in FILE_MODES
            and named_in(path,directory) and text(go16,'[0-9a-f]{16}') and integer(index,0,99)):return failed('FILE_REQUEST_INVALID')
"""
add('F03_file_mode_unchecked_before_the_creation','files',REQUEST,REQUEST.replace(" and type(mode) is int and mode in FILE_MODES",""))
add('F04_file_size_unbounded','files',REQUEST,REQUEST.replace("0<len(content)<=MAX_FILE_BYTES","0<len(content)"))
add('F05_empty_file_accepted','files',REQUEST,REQUEST.replace("0<len(content)<=MAX_FILE_BYTES","len(content)<=MAX_FILE_BYTES"))
add('F06_file_name_unchecked','files',REQUEST,REQUEST.replace("named_in(path,directory) and ",""))
add('F07_go_prefix_unchecked','files',REQUEST,REQUEST.replace(" and text(go16,'[0-9a-f]{16}')",""))
NAMED="""    return (type(path) is str and clean_path(path) and text(PurePosixPath(path).name,FILE_NAME)
            and (parent.rows is None or str(PurePosixPath(path).parent)==parent.rows[-1]['path']))
"""
add('F08_name_grammar_unchecked','files',NAMED,NAMED.replace(" and text(PurePosixPath(path).name,FILE_NAME)",""))
add('F09_path_need_not_lie_in_the_pinned_parent','files',NAMED,NAMED.replace("\n            and (parent.rows is None or str(PurePosixPath(path).parent)==parent.rows[-1]['path'])",""))
add('F10_same_temporary_name_for_every_file','files',"temp=entry['temporary_name']=TEMPORARY%(go16,index)\n","temp=entry['temporary_name']=TEMPORARY%(go16,0)\n")
add('F11_temporary_name_not_keyed_by_the_go','files',"temp=entry['temporary_name']=TEMPORARY%(go16,index)\n","temp=entry['temporary_name']=TEMPORARY%('0'*16,index)\n")
add('F12_mkdir_with_a_fixed_mode','files',"    try:mutate(state,gate,lambda:host.mkdir(name,mode,parent.fd))\n","    try:mutate(state,gate,lambda:host.mkdir(name,0o755,parent.fd))\n")
add('F13_created_directory_mode_compared_with_a_constant','files',"                and stat.S_IMODE(info.st_mode)==mode and info.st_dev==parent.identity[0]):\n            entry.update(state='CREATED_METADATA_MISMATCH'",
    "                and info.st_dev==parent.identity[0]):\n            entry.update(state='CREATED_METADATA_MISMATCH'")
add('F14_created_file_mode_not_compared','files',"                    and stat.S_IMODE(info.st_mode)==mode and info.st_size==len(content)\n","                    and info.st_size==len(content)\n")
READBACK="""        need(raw==content and (info.st_dev,info.st_ino)==(entry['device'],entry['inode']) and info.st_uid==0 and info.st_gid==0
             and stat.S_IMODE(info.st_mode)==mode and info.st_nlink==1,'READBACK_HASH_MISMATCH')
"""
add('F15_readback_does_not_compare_the_bytes','files',READBACK,READBACK.replace("raw==content and ",""))
add('F16_readback_does_not_compare_the_identity','files',READBACK,READBACK.replace("(info.st_dev,info.st_ino)==(entry['device'],entry['inode']) and ",""))
add('F17_readback_does_not_compare_the_owner','files',READBACK,READBACK.replace("info.st_uid==0 and info.st_gid==0\n             and ",""))
add('F18_readback_does_not_compare_the_mode','files',READBACK,READBACK.replace("stat.S_IMODE(info.st_mode)==mode and ",""))
add('F19_readback_does_not_compare_the_link_count','files',READBACK,READBACK.replace(" and info.st_nlink==1",""))
add('F20_readback_without_proving_the_directory_again','files',"    try:\n        directory.verify(gate)\n        raw,info=read_regular(host,PurePosixPath(entry['path']).name","    try:\n        raw,info=read_regular(host,PurePosixPath(entry['path']).name")
DIRECTORY_READBACK="""        need(bool(found.get('exists')) and (found['device'],found['inode'])==handle.identity[:2] and found['type']=='dir'
             and (found['uid'],found['gid'],found['mode_octal'])==(0,0,'%04o'%mode)
             and count_entries(host,handle.fd,gate,MAX_DIRECTORY_ENTRIES)==entries,'READBACK_MISMATCH')
"""
add('F21_directory_readback_ignores_the_entries','files',DIRECTORY_READBACK,DIRECTORY_READBACK.replace("\n             and count_entries(host,handle.fd,gate,MAX_DIRECTORY_ENTRIES)==entries",""))
add('F22_directory_readback_ignores_the_resolved_path','files',DIRECTORY_READBACK,DIRECTORY_READBACK.replace(" and (found['device'],found['inode'])==handle.identity[:2]",""))
add('F23_directory_readback_ignores_owner_and_mode','files',DIRECTORY_READBACK,DIRECTORY_READBACK.replace("\n             and (found['uid'],found['gid'],found['mode_octal'])==(0,0,'%04o'%mode)",""))
add('F24_objects_left_forgets_a_temporary','files',"    left+=sum(1 for row in files if row['state'] in ('TEMPORARY_ONLY','INSTALLED_DURABLE','INSTALLED_NOT_DURABLE'))\n","    left+=sum(1 for row in files if row['state'] in ('INSTALLED_DURABLE','INSTALLED_NOT_DURABLE'))\n")
add('F25_objects_left_counts_a_linked_pair_once','files',"    return left+2*sum(1 for row in files if row['state']=='LINKED_TEMPORARY_PRESENT')\n","    return left+sum(1 for row in files if row['state']=='LINKED_TEMPORARY_PRESENT')\n")
add('F26_file_request_accepts_any_mode','files',"            and type(mode) is int and mode in FILE_MODES)\n","            )\n")
add('F27_file_request_accepts_the_null_hash','files',"not text(name,LEFTOVER) and hexpin(content_sha256) and","not text(name,LEFTOVER) and")

# ---------------------------------------------------------------- lock
ACQUIRE="        try:host.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);return attempts\n"
add('L01_lock_taken_shared','lock',ACQUIRE,ACQUIRE.replace("fcntl.LOCK_EX|fcntl.LOCK_NB","fcntl.LOCK_SH|fcntl.LOCK_NB"))
add('L02_lock_requested_blocking','lock',ACQUIRE,ACQUIRE.replace("fcntl.LOCK_EX|fcntl.LOCK_NB","fcntl.LOCK_EX"))
WAIT="        need(attempts<most and gate()-LOCK_POLL_SECONDS>limit,'DEPLOY_LOCK_BUSY')\n"
add('L03_wait_not_bounded_by_the_budget','lock',WAIT,"        need(attempts<most,'DEPLOY_LOCK_BUSY')\n")
add('L04_wait_not_bounded_by_the_number_of_attempts','lock',WAIT,"        need(gate()-LOCK_POLL_SECONDS>limit,'DEPLOY_LOCK_BUSY')\n")
add('L05_wait_ignores_what_must_be_kept','lock',"    limit=budget-min(wait_seconds,budget-keep_seconds);attempts=0","    limit=budget-wait_seconds;attempts=0")
add('L06_wait_ignores_the_signed_seconds','lock',"    limit=budget-min(wait_seconds,budget-keep_seconds);attempts=0;most=int(wait_seconds/LOCK_POLL_SECONDS)+1","    limit=keep_seconds;attempts=0;most=int(MAX_LOCK_WAIT_SECONDS/LOCK_POLL_SECONDS)+1")
add('L07_lock_asked_for_without_the_budget_to_use_it','lock',"    budget=gate();need(budget>keep_seconds,'LOCK_NOT_TAKEN_BUDGET')\n","    budget=gate()\n")
add('L08_wait_arguments_unchecked','lock',"    need(integer(wait_seconds,0,MAX_LOCK_WAIT_SECONDS) and integer(keep_seconds,0,MAX_SECONDS),'LOCK_WAIT_INVALID')\n","")
add('L09_wait_longer_than_twenty_seconds_allowed','lock',"MAX_LOCK_WAIT_SECONDS=20\n","MAX_LOCK_WAIT_SECONDS=40\n")
add('L10_no_pause_between_attempts','lock',"        host.pause(LOCK_POLL_SECONDS)\n\ndef release_lock","        pass\n\ndef release_lock")
add('L11_any_error_of_the_lock_call_counts_as_busy','lock',"            need(error.errno in (errno.EWOULDBLOCK,errno.EAGAIN,errno.EACCES),'LOCK_UNAVAILABLE')\n        # The budget","            pass\n        # The budget")
add('L12_lock_file_with_several_names_accepted','lock',"    need(stat.S_ISREG(named.st_mode) and named.st_nlink==1,'LOCK_FILE_NOT_REGULAR')\n","    need(stat.S_ISREG(named.st_mode),'LOCK_FILE_NOT_REGULAR')\n")
add('L13_lock_file_type_unchecked','lock',"    need(stat.S_ISREG(named.st_mode) and named.st_nlink==1,'LOCK_FILE_NOT_REGULAR')\n","    need(named.st_nlink==1,'LOCK_FILE_NOT_REGULAR')\n")
add('L14_lock_file_swap_between_lstat_and_open_unnoticed','lock',"        need(stat.S_ISREG(held.st_mode) and (held.st_dev,held.st_ino)==(named.st_dev,named.st_ino),'LOCK_FILE_REPLACED')\n","        need(stat.S_ISREG(held.st_mode),'LOCK_FILE_REPLACED')\n")
add('L15_lock_file_opened_following_a_link','lock',"fd=host.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory.fd)","fd=host.open(name,os.O_RDONLY|os.O_NONBLOCK,dir_fd=directory.fd)")
add('L16_descriptor_left_open_when_the_lock_file_was_replaced','lock',"    except BaseException:\n        host.close(fd);raise\n\ndef lock_still_named","    except BaseException:\n        raise\n\ndef lock_still_named")
add('L17_absent_lock_file_raises_the_os_error','lock',"    except FileNotFoundError:raise Refused('LOCK_FILE_ABSENT') from None\n","    except KeyError:raise Refused('LOCK_FILE_ABSENT') from None\n")
add('L18_replaced_lock_file_still_said_to_be_named','lock',"        return bool(stat.S_ISREG(named.st_mode) and (named.st_dev,named.st_ino)==(held.st_dev,held.st_ino))\n","        return bool(stat.S_ISREG(named.st_mode))\n")
add('L19_vanished_lock_file_still_said_to_be_named','lock',"    except OSError:return False\n\ndef acquire_lock","    except OSError:return True\n\ndef acquire_lock")
add('L20_release_does_not_unlock','lock',"    try:host.flock(fd,fcntl.LOCK_UN)\n    except Exception:pass\n    try:host.close(fd)","    try:pass\n    except Exception:pass\n    try:host.close(fd)")
add('L21_release_does_not_close','lock',"    try:host.close(fd)\n    except Exception:pass\n\ndef probe_lock","    try:pass\n    except Exception:pass\n\ndef probe_lock")
PROBE="    try:host.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)\n"
add('L22_probe_takes_the_lock_exclusively','lock',PROBE,PROBE.replace("LOCK_SH","LOCK_EX"))
add('L23_probe_blocks','lock',PROBE,PROBE.replace("fcntl.LOCK_SH|fcntl.LOCK_NB","fcntl.LOCK_SH"))
add('L24_probe_keeps_the_lock','lock',"    host.flock(fd,fcntl.LOCK_UN);return 'FREE'\n","    return 'FREE'\n")
add('L25_probe_calls_any_error_busy','lock',"        need(error.errno in (errno.EWOULDBLOCK,errno.EAGAIN,errno.EACCES),'LOCK_UNAVAILABLE')\n        return 'BUSY'\n","        return 'BUSY'\n")

# ---------------------------------------------------------------- the dispatcher's date literal, per class
add('D70_read_dispatcher_date_set_dropped','dispatcher_read',"need(start.date().isoformat() in ('2026-10-02','2026-10-03','2026-10-04','2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10') and end.date()==start.date(),'DISPATCH_DATE')",
    "need(end.date()==start.date(),'DISPATCH_DATE')")
add('D71_write_dispatcher_date_set_dropped','dispatcher_write',"need(start.date().isoformat() in ('2026-10-03','2026-10-04','2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10') and end.date()==start.date(),'DISPATCH_DATE')",
    "need(end.date()==start.date(),'DISPATCH_DATE')")
add('D72_write_dispatcher_accepts_friday_the_second','dispatcher_write',"start.date().isoformat() in ('2026-10-03',","start.date().isoformat() in ('2026-10-02','2026-10-03',")
add('D73_read_dispatcher_accepts_the_day_after_the_epoch','dispatcher_read',"'2026-10-09','2026-10-10') and end.date()==start.date()","'2026-10-09','2026-10-10','2026-10-11') and end.date()==start.date()")

# ---------------------------------------------------------------- assemble.py: the rules a source must meet
def rule(name,old,new=''):add('A_'+name,'assemble',old,new)
rule('R01_effect_row_allowed_in_a_reading_source',"            rule(row['kind']!='EFFECT' or writes,'COMMANDS[%r] is an EFFECT in a source that does not write'%name)\n")
rule('R02_switching_verb_needs_no_declaration',"                rule((row['kind']=='READ') if row['argv'][0] in READ_VERBS else (activation and row['kind']=='EFFECT'),","                rule(True,")
rule('R03_docker_kind_need_not_fit_the_verb',"                rule(reading==(row['kind']=='READ'),'COMMANDS[%r]: kind %s does not fit the docker verb'%(name,row['kind']))\n")
rule('R04_docker_exec_allowed',"                rule(row['argv'][0]!='exec','COMMANDS[%r]: docker exec is not used by this core'%name)\n")
rule('R05_attached_run_shape_unchecked',"                if verb==['run']:\n","                if verb==['never']:\n")
rule('R06_fixed_template_may_print_the_environment',"            rule('Env' not in ''.join(words),'COMMANDS[%r] names the environment of a container in a fixed template'%name)\n")
rule('R07_any_row_may_take_a_template_at_call_time',"            rule(row['argv'][-1]!='--format' or (name=='container_environment' and row['argv']==['container','inspect','--format'] and not row['tail']),","            rule(True,")
rule('R08_reading_source_may_carry_the_files_part',"        rule('files' not in parts and not [name for name in dir(native) if name in WRITE_CALLS],","        rule(True,")
rule('R09_date_class_need_not_fit_the_writes_flag',"and (m.DATE_CLASS=='READ')==(not writes),\n","and True,\n")
rule('R10_dates_need_not_be_a_class_of_the_core',"    rule(m.DATE_CLASS in m.DATE_SETS and m.DATES==m.DATE_SETS[m.DATE_CLASS] and","    rule(m.DATE_CLASS in m.DATE_SETS and")
rule('R11_activation_without_writes_allowed',"and (writes or not activation),'WRITES_ALLOWED and ACTIVATION_ALLOWED are booleans","and True,'WRITES_ALLOWED and ACTIVATION_ALLOWED are booleans")
rule('R12_gate_span_unbounded',"    rule(type(m.MAX_GATE_SPAN_SECONDS) is int and 0<m.MAX_GATE_SPAN_SECONDS<=(900 if writes else 3600),","    rule(type(m.MAX_GATE_SPAN_SECONDS) is int and 0<m.MAX_GATE_SPAN_SECONDS,")
rule('R13_schema_names_free',"    rule((m.REQUEST_SCHEMA,m.AUTHORITY_SCHEMA,m.GO_SCHEMA,m.RECEIPT_SCHEMA,m.PLAN_SCHEMA)==(doc+'_REQUEST_V1',doc+'_AUTHORITY_V1',doc+'_GO_V1',doc+'_RECEIPT_V1',spec.STEM+'_PLAN_V1'),","    rule(True,")
rule('R14_operation_name_free',"    rule(type(m.OPERATION) is str and re.fullmatch(('GO_WRITE_' if writes else 'GO_READONLY_')+'HOSTOPS02_[A-Z][A-Z0-9_]{1,50}_[0-9]{2}',m.OPERATION) is not None,","    rule(type(m.OPERATION) is str,")
rule('R15_imports_unchecked',"    rule(imports-allowed_imports<=OPERATION_IMPORTS,","    rule(True,")
rule('R16_os_members_unchecked',"    rule(attributes<=allowed_os,","    rule(True,")
rule('R17_forbidden_names_allowed',"    rule(not names&FORBIDDEN_NAMES,","    rule(True,")
rule('R18_subprocess_use_unchecked',"    rule('shell' not in keywords and 'preexec_fn' not in keywords and process<=(SUBPROCESS if 'runner' in parts else set()),","    rule(True,")
rule('R19_scope_need_not_name_the_core',"         and scope.get('core_sha256')==m.CORE_SHA256 and type(scope.get('never')) is list","         and type(scope.get('never')) is list")
rule('R20_scope_hash_unchecked',"    try:rule(m.SCOPE_SHA256==sha(canonical(scope)),'SCOPE_SHA256 is not the hash of SCOPE')\n","    try:rule(True,'SCOPE_SHA256 is not the hash of SCOPE')\n")
rule('R21_scope_need_not_carry_the_command_tables',"        rule(hasattr(m,'BINARIES') and scope.get('commands') is commands and scope.get('binaries') is m.BINARIES and scope.get('command_classes') is m.COMMAND_CLASSES\n","        rule(hasattr(m,'BINARIES') and scope.get('commands') is commands and scope.get('binaries') is m.BINARIES\n")
rule('R22_source_name_free',"    rule(m.SOURCE_NAME==spec.MODULE+'.py','SOURCE_NAME is not <MODULE>.py')\n")
rule('R23_success_outcome_may_equal_another',"    rule(m.REFUSED_OUTCOME!=m.COMPLETE_OUTCOME and m.PARTIAL_OUTCOME!=m.COMPLETE_OUTCOME and m.ESCAPED_OUTCOME!=m.COMPLETE_OUTCOME\n         and m.REDUCED_OUTCOME!=m.COMPLETE_OUTCOME,","    rule(True,")
rule('R24_plan_keys_may_shadow_the_common_ones',"not m.PLAN_KEYS&m.PLAN_COMMON_KEYS and ","")
rule('R25_operation_part_may_carry_a_marker',"    if '# ==== ' in own:refuse('OPERATION_PART_CARRIES_A_MARKER')\n")
rule('R26_unbound_plan_keys_unchecked',"    if not (type(own) is dict and set(own)==set(module.PLAN_KEYS)):refuse('UNBOUND_PLAN_KEYS: unbound_plan() must return exactly PLAN_KEYS')\n")
rule('R27_changed_part_accepted',"    if PINS.get(relative)!=sha(raw):refuse('CORE_CHANGED '+relative)\n")
rule('R28_parts_in_any_order',"parts[0]=='core' and parts==[name for name in PART_ORDER if name in parts]\n            and","parts[0]=='core'\n            and")
rule('R29_stem_of_another_family_accepted',"re.fullmatch('HOSTOPS02_[A-Z][A-Z0-9_]{1,40}',spec.STEM)","re.fullmatch('[A-Z][A-Z0-9_]{1,40}',spec.STEM)")
rule('R30_activation_flag_of_the_templates_always_false',"'writes_allowed':module.WRITES_ALLOWED,'activation_allowed':module.ACTIVATION_ALLOWED,'evidence':[],'plan':plan}","'writes_allowed':module.WRITES_ALLOWED,'activation_allowed':False,'evidence':[],'plan':plan}")
rule('R31_operation_part_may_bind_a_name_of_the_core_again',"    rule(not bound&shared,","    rule(True,")
rule('R32_operation_part_may_store_into_an_object_of_the_core',"    rule(not stored&shared,","    rule(True,")
rule('R33_constants_of_the_core_may_differ_after_the_operation_part',"    rule(not changed,","    rule(True,")
rule('R34_operation_part_may_name_any_module',"    rule(not {node.id for node in named}&OWN_MODULES_FORBIDDEN,","    rule(True,")
rule('R35_operation_part_may_call_the_os_module',"    rule(all(node.attr.startswith('O_') for node in flags) and len([node for node in named if node.id=='os'])==len(flags),","    rule(True,")
rule('R36_operation_part_may_name_the_os_module_bare',"    rule(all(node.attr.startswith('O_') for node in flags) and len([node for node in named if node.id=='os'])==len(flags),","    rule(all(node.attr.startswith('O_') for node in flags),")
rule('R37_operation_part_may_pose_as_a_helper',"    rule('through' not in {node.arg for node in ast.walk(own) if isinstance(node,ast.keyword)},","    rule(True,")
rule('R38_any_tool_may_be_named',"        rule(type(binaries) is dict and set(binaries)<=TOOLS and all(","        rule(type(binaries) is dict and all(")
rule('R39_tool_paths_unchecked',"and all(type(path) is str and re.fullmatch('(/[a-z]+)+/'+tool,path) for path in paths)","and all(type(path) is str for path in paths)")
rule('R40_container_row_may_be_any_command',"            rule(row['kind']!='CONTAINER' or (row['tool']=='docker' and row['argv'][:1]==['run']),","            rule(True,")
rule('R41_attached_run_may_fix_a_bind',"RUN_WORDS_FORBIDDEN=('-v','--volume','--mount','--device','--cap-add')","RUN_WORDS_FORBIDDEN=('-v','--volume','--device','--cap-add')")
rule('R42_attached_run_may_add_a_device',"RUN_WORDS_FORBIDDEN=('-v','--volume','--mount','--device','--cap-add')","RUN_WORDS_FORBIDDEN=('-v','--volume','--mount','--cap-add')")
rule('R43_attached_run_may_add_a_capability',"RUN_WORDS_FORBIDDEN=('-v','--volume','--mount','--device','--cap-add')","RUN_WORDS_FORBIDDEN=('-v','--volume','--mount','--device')")
rule('R44_docker_read_need_not_fix_its_template',"                rule(not reading or verb==['compose'] or '--format' in row['argv'],","                rule(True,")
rule('R45_bindings_inside_if_and_try_not_seen',"                for field in ('body','orelse','finalbody'):\n                    if isinstance(getattr(node,field,None),list):walk(getattr(node,field))\n","")
rule('R46_loop_targets_not_seen',"                if isinstance(node,ast.For):target(node.target)\n","")
rule('R47_augmented_assignments_not_seen',"            elif isinstance(node,(ast.AugAssign,ast.AnnAssign)):target(node.target)\n","")
rule('R48_imports_not_seen_as_bindings',"            elif isinstance(node,(ast.Import,ast.ImportFrom)):bound.update((alias.asname or alias.name).split('.')[0] for alias in node.names)\n","")
rule('R49_deletions_not_seen',"            elif isinstance(node,(ast.Assign,ast.Delete)):\n","            elif isinstance(node,ast.Assign):\n")
rule('R50_definitions_not_seen_as_bindings',"            if isinstance(node,(ast.FunctionDef,ast.ClassDef)):bound.add(node.name)\n            elif isinstance(node,(ast.Assign,ast.Delete)):\n","            if isinstance(node,(ast.Assign,ast.Delete)):\n")
rule('R51_operation_part_may_import_a_module_it_must_not_use',"    rule(not own_imports&OWN_MODULES_FORBIDDEN,","    rule(True,")
rule('R52_operation_part_may_name_ctypes',"OWN_MODULES_FORBIDDEN={'subprocess','selectors','signal','fcntl','time','ctypes'}","OWN_MODULES_FORBIDDEN={'subprocess','selectors','signal','fcntl','time'}")
rule('R53_from_imports_of_the_operation_part_not_seen',"|{\n        (node.module or '').split('.')[0] for node in ast.walk(own) if isinstance(node,ast.ImportFrom)}","")
rule('R54_renamed_imports_of_the_operation_part_not_seen',"    own_imports={alias.name.split('.')[0] for node in ast.walk(own) if isinstance(node,ast.Import) for alias in node.names}|{","    own_imports=set()|{")
rule('R55_ctypes_for_anything',"    rule(len(loads)==len([node for node in ast.walk(tree) if isinstance(node,ast.Name) and node.id=='ctypes'])<=1,","    rule(True,")
rule('R56_ctypes_twice',"and node.id=='ctypes'])<=1,","and node.id=='ctypes'])<=2,")
rule('R57_ctypes_load_of_any_library_or_errno',"isinstance(node,ast.Call) and ast.dump(node)==the_load]","isinstance(node,ast.Call) and ast.dump(node.func)==ast.dump(ast.parse(CTYPES_LOAD,mode='eval').body.func)]")
rule('R58_core_may_not_import_ctypes',"IMPORTS_OF={'core':{'ctypes','dataclasses',","IMPORTS_OF={'core':{'dataclasses',")

# ---------------------------------------------------------------- core: the process made non-dumpable (the token family's revision, CORE.md section 14)
DUMP="        disabled=library.prctl(PR_SET_DUMPABLE,0,0,0,0)==0 and library.prctl(PR_GET_DUMPABLE,0,0,0,0)==0\n"
add('DUMP01_prctl_set_not_made','core',DUMP,"        disabled=library.prctl(PR_GET_DUMPABLE,0,0,0,0)==0\n")
add('DUMP02_read_back_skipped','core',DUMP,"        disabled=library.prctl(PR_SET_DUMPABLE,0,0,0,0)==0\n")
add('DUMP03_read_back_before_the_set','core',DUMP,"        disabled=library.prctl(PR_GET_DUMPABLE,0,0,0,0)==0 and library.prctl(PR_SET_DUMPABLE,0,0,0,0)==0\n")
add('DUMP04_set_with_the_option_number_of_get','core',"PR_SET_DUMPABLE=4\n","PR_SET_DUMPABLE=3\n")
add('DUMP05_get_with_the_option_number_of_set','core',"PR_GET_DUMPABLE=3\n","PR_GET_DUMPABLE=4\n")
add('DUMP06_attribute_set_to_1','core',"library.prctl(PR_SET_DUMPABLE,0,0,0,0)==0","library.prctl(PR_SET_DUMPABLE,1,0,0,0)==0")
add('DUMP07_any_read_back_accepted','core',"library.prctl(PR_GET_DUMPABLE,0,0,0,0)==0\n","library.prctl(PR_GET_DUMPABLE,0,0,0,0)!=-1\n")
add('DUMP08_failure_not_refused','core',"    need(disabled,'PROCESS_DUMPABLE_NOT_DISABLED');return True\n","    return True\n")
add('DUMP09_exception_of_the_library_escapes','core',"    except Exception:disabled=False\n    need(disabled,","    except ZeroDivisionError:disabled=False\n    need(disabled,")
add('DUMP10_another_library','core',"if library is None:library=ctypes.CDLL(None,use_errno=True)","if library is None:library=ctypes.CDLL('libc.so.6',use_errno=True)")
add('DUMP11_errno_not_kept_by_ctypes','core',"if library is None:library=ctypes.CDLL(None,use_errno=True)","if library is None:library=ctypes.CDLL(None)")
add('DUMP12_injected_library_ignored','core',"if library is None:library=ctypes.CDLL(None,use_errno=True)","library=ctypes.CDLL(None,use_errno=True)")
add('DUMP13_native_says_disabled_without_a_call','core',"    def not_dumpable(self):return dumps_disabled()","    def not_dumpable(self):return True")

# ---------------------------------------------------------------- core-k6b: the one in-place edit (IN_PLACE_EDIT_EXCEPTION)
X="                    rule(user==['0:0'] or (excepted and row['argv']==IN_PLACE_EDIT_EXCEPTION['argv'] and row['kind']==IN_PLACE_EDIT_EXCEPTION['kind']\n"
rule('X01_any_user_allowed',X,X.replace("rule(user==['0:0'] or (","rule(True or ("))
rule('X02_any_argv_for_the_exception',X,X.replace("row['argv']==IN_PLACE_EDIT_EXCEPTION['argv'] and ",""))
rule('X03_any_kind_for_the_exception',X,X.replace(" and row['kind']==IN_PLACE_EDIT_EXCEPTION['kind']",""))
rule('X04_exception_for_any_source',"                    excepted=(spec.NAME,name)==(IN_PLACE_EDIT_EXCEPTION['source'],IN_PLACE_EDIT_EXCEPTION['row'])\n","                    excepted=name==IN_PLACE_EDIT_EXCEPTION['row']\n")
rule('X05_exception_for_any_row',"                    excepted=(spec.NAME,name)==(IN_PLACE_EDIT_EXCEPTION['source'],IN_PLACE_EDIT_EXCEPTION['row'])\n","                    excepted=spec.NAME==IN_PLACE_EDIT_EXCEPTION['source']\n")
rule('X06_no_user_is_root',"                    user=row['argv'][row['argv'].index('--user')+1:][:1] if '--user' in row['argv'] else []\n","                    user=row['argv'][row['argv'].index('--user')+1:][:1] if '--user' in row['argv'] else ['0:0']\n")
rule('X07_exception_argv_any_user',"    'argv':['run','--rm','-i','--pull','never','--init','--user','1000:1000',","    'argv':['run','--rm','-i','--pull','never','--init','--user','1001:1001',")
rule('X08_exception_argv_with_the_network',"'1000:1000','--network','none','--read-only'","'1000:1000','--network','bridge','--read-only'")
rule('X09_exception_without_stdin',"                                           and row['stdin'] is IN_PLACE_EDIT_EXCEPTION['stdin'] and not row['tail'] and writes),","                                           and not row['tail'] and writes),")
rule('X10_exception_another_source',"IN_PLACE_EDIT_EXCEPTION={'source':'capacity_switch',","IN_PLACE_EDIT_EXCEPTION={'source':'selftest_write',")


MUTANTS=M
COMBOS=dict(PORTED_COMBOS)
REDUNDANT=dict(PORTED_REDUNDANT)
