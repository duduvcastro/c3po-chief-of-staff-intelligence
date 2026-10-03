"""The mutants of the token placement's own part. Each row: (name, 'op', exact anchor, replacement). The anchor must
occur exactly once in the built source and be a text of op.py (mutate.py check). One mutant per constant the signers
rely on, per member of effects_of(), per refusal of validate_plan and of the precheck, per rule of the parser of the
environment file, per condition of the creation, the readback and the withdrawal, and per member of the receipt that
says what the run did.

Left out, because no test can tell them apart from the source (said here so that a reviewer does not look for them):
the clearing of Effects.pending after an uncertain call (state.unknown(); perform's own receipt does not read
`pending`), the fallback code of a run that stopped without a code (unreachable: every stop sets one), `<=` against `<`
in the line loop of the parser (the last segment of a file that ends with a newline is empty, hence blank), `closing>0`
for a quoted value (an unclosed quote leaves the opening quote as the tail, which the tail rule refuses). The facts
`regular` and `size_within_1_4096` cannot be false in a run (the created file and the one read_regular returns are
regular, and their sizes are 17 to 513 bytes by construction): each fact is reported because the README's readback names it; tests/test_token_from_env.py judges it, and the size fact, on the
function itself), and a write loop that never advances (it would loop until the time
limit of the harness).

Revision 2: R17 of revision 1 (separator!=b':' in place of separator==b'=') is left out: a statement now always has "="
or ":", so the two conditions are the same. R05c (the body of a quoted value taken with its opening quote) is equivalent
for the same kind of reason: the opening quote neither makes two backslashes nor ends the body.

Revision 3 (the process made non-dumpable first, CONTRACT D9): X01 to X12 are mutants of the operation part (the call
removed, its answer not checked or any true answer taken, the call moved after the executor check, after the walk of
the deploy chain or after the read of .env, the fact of the receipt, the listed code, the effects); Y01 to Y09 are
mutants of the core's dumps_disabled() as this operation's built source carries it (target "core", mutate.py): the set
not made, the read-back skipped, the two calls swapped, either option number wrong, the attribute set to 1, any
read-back but -1 accepted, a failure not refused, NativeRead.not_dumpable() saying True without a call. Left out as
equivalent: the initial None of the fact (the first statement of the precheck sets it to False before the call, and a
run that never reaches the precheck has no receipt of perform()), and the texts of the scope (PROCESS_SCOPE and the
sentence of SCOPE_STATEMENT are pinned by the static tests, which a mutation run deselects)."""
MUTANTS=[]
COMBOS={}
REDUNDANT={}
def add(name,old,new):MUTANTS.append((name,'op',old,new))

# ---------------------------------------------------------------- constants the signers rely on
add('C01_the_day_before_is_a_token_day',"TOKEN_DAYS=('2026-10-03','2026-10-04')","TOKEN_DAYS=('2026-10-02','2026-10-03','2026-10-04')")
add('C02_sunday_is_not_a_token_day',"TOKEN_DAYS=('2026-10-03','2026-10-04')","TOKEN_DAYS=('2026-10-03',)")
add('C03_writes_any_day_of_the_epoch',"DATE_CLASS='WRITE_WEEKEND'","DATE_CLASS='WRITE_EPOCH'")
add('C04_configuration_directory_0750',"CONFIG_DIRECTORY_MODE=0o700","CONFIG_DIRECTORY_MODE=0o750")
add('C05_another_name',"TOKEN_NAME='token'","TOKEN_NAME='token.new'")
add('C06_token_file_0640',"TOKEN_FILE_MODE=0o600","TOKEN_FILE_MODE=0o640")
add('C07_readback_limit_below_the_longest_value',"TOKEN_MAX_FILE_BYTES=4096","TOKEN_MAX_FILE_BYTES=512")
add('C08_create_without_o_excl',"TOKEN_CREATE_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC","TOKEN_CREATE_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC")
add('C09_create_following_a_link',"TOKEN_CREATE_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC","TOKEN_CREATE_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC")
add('C10_create_without_o_cloexec',"TOKEN_CREATE_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC","TOKEN_CREATE_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW")
add('C11_create_truncating',"TOKEN_CREATE_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC","TOKEN_CREATE_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_TRUNC")
add('C12_another_environment_file',"ENV_FILE_NAME='.env'","ENV_FILE_NAME='.env.local'")
add('C13_environment_file_bound_one_byte_more',"MAX_ENV_FILE_BYTES=65536","MAX_ENV_FILE_BYTES=65537")
add('C14_only_the_short_name',"TOKEN_KEYS=('C3PO_MASSIVE_API_TOKEN','MASSIVE_API_TOKEN')","TOKEN_KEYS=('MASSIVE_API_TOKEN',)")
add('C15_only_the_prefixed_name',"TOKEN_KEYS=('C3PO_MASSIVE_API_TOKEN','MASSIVE_API_TOKEN')","TOKEN_KEYS=('C3PO_MASSIVE_API_TOKEN',)")
GRAMMAR="TOKEN_VALUE_GRAMMAR='[A-Za-z0-9._~+/=-]{16,512}'"
add('C16_value_of_one_character',GRAMMAR,GRAMMAR.replace('{16,512}','{1,512}'))
add('C17_value_of_fifteen_characters',GRAMMAR,GRAMMAR.replace('{16,512}','{15,512}'))
add('C18_value_of_513_characters',GRAMMAR,GRAMMAR.replace('{16,512}','{16,513}'))
add('C19_value_with_a_dollar',GRAMMAR,GRAMMAR.replace('=-]','=$-]'))
add('C20_value_with_a_space_and_a_hash',GRAMMAR,GRAMMAR.replace('=-]','=# -]'))
add('C21_value_of_any_byte_but_a_newline',GRAMMAR,"TOKEN_VALUE_GRAMMAR='[^\\\\n]{16,512}'")
add('C22_value_with_quotes',GRAMMAR,GRAMMAR.replace('=-]','="\\\'-]'))
add('C23_value_with_non_ascii',GRAMMAR,GRAMMAR.replace('=-]','=\\\\x80-\\\\xff-]'))
add('C24_less_than_the_allowance_left',"WRITE_ALLOWANCE_SECONDS=15 ","WRITE_ALLOWANCE_SECONDS=14 ")
add('C25_provisioning_evidence_not_required',"EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PROVISION_OPERATION)","EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)")
add('C26_precheck_evidence_not_required',"EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PROVISION_OPERATION)","EVIDENCE_OPERATIONS=(PROVISION_OPERATION,)")
add('C27_activation_allowed',"\nACTIVATION_ALLOWED=False\n","\nACTIVATION_ALLOWED=True\n")
add('C28_gate_longer_than_a_write_may_have',"MAX_GATE_SPAN_SECONDS=900","MAX_GATE_SPAN_SECONDS=901")
add('C29_comment_after_indentation_not_a_comment',"ENV_LINE_COMMENT=rb'[ \\t]*#.*'","ENV_LINE_COMMENT=rb'#.*'")
add('C30_blank_line_only_when_empty',"ENV_LINE_BLANK=rb'[ \\t]*'","ENV_LINE_BLANK=rb''")
STATEMENT="ENV_LINE_STATEMENT=rb'([ \\t]*)(export[ \\t]+)?([A-Za-z0-9_.\\[\\]-]+)([ \\t]*)([=:])([ \\t]*)(.*)'"
add('C31_names_without_dots_dashes_brackets',STATEMENT,STATEMENT.replace('[A-Za-z0-9_.\\[\\]-]+','[A-Za-z0-9_]+'))
add('C32_no_yaml_separator',STATEMENT,STATEMENT.replace('([=:])','(=)'))
add('C33_a_name_without_a_value_accepted',STATEMENT,STATEMENT.replace('([=:])([ \\t]*)(.*)','(?:([=:])([ \\t]*)(.*))?'))
add('C34_export_not_recognised',STATEMENT,STATEMENT.replace('(export[ \\t]+)?','()?'))
add('C35_anything_after_a_closing_quote',"ENV_QUOTED_TAIL=rb'[ \\t]*(?:#.*)?'","ENV_QUOTED_TAIL=rb'.*'")
add('C36_spaces_but_no_comment_after_a_closing_quote',"ENV_QUOTED_TAIL=rb'[ \\t]*(?:#.*)?'","ENV_QUOTED_TAIL=rb'[ \\t]*'")
add('C37_the_name_looked_for_in_capitals',"TOKEN_NAME_FOLDED=b'massive_api_token'","TOKEN_NAME_FOLDED=b'MASSIVE_API_TOKEN'")
add('C38_the_name_looked_for_without_its_middle',"TOKEN_NAME_FOLDED=b'massive_api_token'","TOKEN_NAME_FOLDED=b'massive_api_tokenx'")

# ---------------------------------------------------------------- the parser
add('R01_carriage_return_accepted',"    need(b'\\r' not in raw and b'\\x00' not in raw,'ENV_FILE_SYNTAX_UNSUPPORTED')","    need(b'\\x00' not in raw,'ENV_FILE_SYNTAX_UNSUPPORTED')")
add('R02_nul_accepted',"    need(b'\\r' not in raw and b'\\x00' not in raw,'ENV_FILE_SYNTAX_UNSUPPORTED')","    need(b'\\r' not in raw,'ENV_FILE_SYNTAX_UNSUPPORTED')")
add('R03_line_outside_the_rules_ignored',"                need(match is not None,'ENV_FILE_SYNTAX_UNSUPPORTED')\n                lead,export,key,space,separator,gap=match.group(1,2,3,4,5,6)",
    "                if match is None:\n                    position=end+1;continue\n                lead,export,key,space,separator,gap=match.group(1,2,3,4,5,6)")
add('R04_value_end_not_judged',"                    value_boundary(other[match.start(7):])\n","")
add('R05_a_quoted_value_may_hold_two_backslashes',"        need(b'\\\\\\\\' not in body and ","        need(")
add('R05b_a_backslash_may_stand_before_the_closing_quote',"body[-1:]!=b'\\\\' and re.fullmatch(","re.fullmatch(")
add('R06_quoted_tail_not_judged',"and re.fullmatch(ENV_QUOTED_TAIL,value[closing+1:]) is not None,'ENV_FILE_SYNTAX_UNSUPPORTED')","and True,'ENV_FILE_SYNTAX_UNSUPPORTED')")
add('R07_value_may_begin_with_a_vertical_tab',"        need(value[:1] not in (b'\\x0b',b'\\x0c') and","        need(value[:1] not in (b'\\x0c',) and")
add('R08_value_may_begin_with_a_form_feed',"        need(value[:1] not in (b'\\x0b',b'\\x0c') and","        need(value[:1] not in (b'\\x0b',) and")
add('R09_value_may_begin_with_any_byte',"and (not value or value[0]<0x80),'ENV_FILE_SYNTAX_UNSUPPORTED')","and True,'ENV_FILE_SYNTAX_UNSUPPORTED')")
add('R10_only_a_double_quote_opens_a_quoted_value',"    if value[:1] in (b'\"',b\"'\"):","    if value[:1] in (b'\"',):")
add('R11_names_compared_with_their_case',"                if key.upper() in names:","                if key in names:")
PLAIN="                    need(not lead and export is None and key in names and not space and separator==b'=' and not gap,'ENV_TOKEN_DEFINITION_NOT_PLAIN')"
add('R12_definition_may_be_indented',PLAIN,PLAIN.replace('not lead and ',''))
add('R13_definition_may_be_exported',PLAIN,PLAIN.replace('export is None and ',''))
add('R14_definition_may_be_spaced_before_the_sign',PLAIN,PLAIN.replace('not space and ',''))
add('R15_definition_may_use_a_colon',PLAIN,PLAIN.replace("separator==b'=' and ",''))
add('R16_definition_may_be_spaced_after_the_sign',PLAIN,PLAIN.replace(' and not gap',''))
add('R18_value_offset_includes_the_sign',"                    found.append((names[key],position+match.start(7),end))","                    found.append((names[key],position+match.start(5),end))")
add('R19_only_the_last_definition_kept',"                    found.append((names[key],position+match.start(7),end))","                    found[:]=[(names[key],position+match.start(7),end)]")
add('R20_last_line_loses_its_last_byte',"            if end<0:end=size\n","            if end<0:end=size-1\n")
add('R28_the_name_allowed_in_other_lines',"                    need(TOKEN_NAME_FOLDED not in folded(other),'ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION')\n","")
add('R29_the_kelvin_sign_not_read_as_k',"    return line.replace(KELVIN_SIGN,b'k').lower()","    return line.lower()")
add('R30_other_lines_compared_with_their_case',"    return line.replace(KELVIN_SIGN,b'k').lower()","    return line.replace(KELVIN_SIGN,b'k')")
add('R31_only_the_name_of_another_line_searched',"                    need(TOKEN_NAME_FOLDED not in folded(other),","                    need(TOKEN_NAME_FOLDED not in folded(key),")
add('R32_a_definition_judged_by_the_boundary_of_other_values',"                    found.append((names[key],position+match.start(7),end))",
    "                    value_boundary(bytes(line)[match.start(7):]);found.append((names[key],position+match.start(7),end))")
add('R33_a_definition_also_searched_for_the_name',"                    found.append((names[key],position+match.start(7),end))",
    "                    need(folded(bytes(line)).count(TOKEN_NAME_FOLDED)==1,'ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION');found.append((names[key],position+match.start(7),end))")
add('R21_no_definition_is_an_empty_value',"    need(found,'ENV_TOKEN_ABSENT')\n","")
add('R22_definitions_not_compared',"        need(all(view[start:end]==first for _,start,end in found),'ENV_TOKEN_DEFINITIONS_DISAGREE')\n","")
add('R23_only_the_first_two_compared',"        need(all(view[start:end]==first for _,start,end in found),","        need(all(view[start:end]==first for _,start,end in found[:2]),")
add('R24_value_grammar_not_judged',"        need(re.fullmatch(TOKEN_VALUE,first) is not None,'ENV_TOKEN_VALUE_GRAMMAR')\n","")
add('R25_value_grammar_a_prefix_only',"        need(re.fullmatch(TOKEN_VALUE,first) is not None,","        need(re.match(TOKEN_VALUE,first) is not None,")
add('R26_no_newline_after_the_value',"content[len(first)]=0x0a\n","content[len(first)]=0x20\n")
add('R27_buffer_not_zeroed',"        for index in range(len(buffer)):buffer[index]=0\n","        pass\n")

# ---------------------------------------------------------------- the signed plan
add('P01_setgid_configuration_directory_accepted',"    rows=validate_chain(plan['config_chain'],CONFIG_DIRECTORY,receives_entry=True)","    rows=validate_chain(plan['config_chain'],CONFIG_DIRECTORY,receives_entry=False)")
ROW="    need((rows[-1]['gid'],rows[-1]['mode'])==(0,CONFIG_DIRECTORY_MODE),'CONFIG_DIRECTORY_NOT_ROOT_0700')"
add('P02_group_of_the_configuration_directory_unchecked',ROW,"    need(rows[-1]['mode']==CONFIG_DIRECTORY_MODE,'CONFIG_DIRECTORY_NOT_ROOT_0700')")
add('P03_mode_of_the_configuration_directory_unchecked',ROW,"    need(rows[-1]['gid']==0,'CONFIG_DIRECTORY_NOT_ROOT_0700')")
add('P04_deploy_directory_any_text',"    need(clean_path(deploy),'DEPLOY_DIRECTORY_INVALID')\n","    need(type(deploy) is str,'DEPLOY_DIRECTORY_INVALID')\n")
add('P05_deploy_directory_inside_the_configuration_directory',"    need(not inside(deploy,CONFIG_DIRECTORY) and not inside(CONFIG_DIRECTORY,deploy),","    need(not inside(CONFIG_DIRECTORY,deploy),")
add('P06_deploy_directory_above_the_configuration_directory',"    need(not inside(deploy,CONFIG_DIRECTORY) and not inside(CONFIG_DIRECTORY,deploy),","    need(not inside(deploy,CONFIG_DIRECTORY),")
add('P07_boot_unbound',"    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')\n","")
add('P08_any_day_of_the_class',"    need(instant(plan['window']['not_before']).date().isoformat() in TOKEN_DAYS,'WINDOW_NOT_ON_A_TOKEN_DAY')\n","")

# ---------------------------------------------------------------- effects_of(): one mutant per member
add('E01_effects_name_another_operation',"    return {'operation':OPERATION,\n","    return {'operation':PROVISION_OPERATION,\n")
add('E02_effects_without_the_required_identity',"required={'uid':0,'gid':0,'mode_octal':'%04o'%CONFIG_DIRECTORY_MODE}","required=None")
add('E03_effects_without_the_chain',"            'config_directory':dict(chain_effects(plan['config_chain']),","            'config_directory':dict({},")
add('E04_effects_token_path',"            'token_file':{'path':TOKEN_PATH,'expect':'ABSENT',","            'token_file':{'path':CONFIG_DIRECTORY,'expect':'ABSENT',")
add('E05_effects_token_expected_present',"            'token_file':{'path':TOKEN_PATH,'expect':'ABSENT',","            'token_file':{'path':TOKEN_PATH,'expect':'ANY',")
add('E06_effects_token_mode',"'mode_octal':'%04o'%TOKEN_FILE_MODE,'links':1,\n","'mode_octal':'0644','links':1,\n")
add('E07_effects_token_links',"'mode_octal':'%04o'%TOKEN_FILE_MODE,'links':1,\n","'mode_octal':'%04o'%TOKEN_FILE_MODE,'links':2,\n")
add('E08_effects_token_content',"'content':'the value of the environment file, then one newline'","'content':'the value of the environment file'")
add('E09_effects_token_size',"'size':'within 1-%d (a boolean, never the size)'%TOKEN_MAX_FILE_BYTES","'size':'within 1-%d'%TOKEN_MAX_FILE_BYTES")
add('E10_effects_token_owner',"            'token_file':{'path':TOKEN_PATH,'expect':'ABSENT','uid':0,'gid':0,","            'token_file':{'path':TOKEN_PATH,'expect':'ABSENT','uid':1000,'gid':0,")
add('E11_effects_environment_path',"            'environment_file':{'path':deploy+'/'+ENV_FILE_NAME,","            'environment_file':{'path':deploy,")
add('E12_effects_deploy_directory',"'deploy_directory':deploy,'keys':list(TOKEN_KEYS),","'deploy_directory':None,'keys':list(TOKEN_KEYS),")
add('E13_effects_keys',"'deploy_directory':deploy,'keys':list(TOKEN_KEYS),","'deploy_directory':deploy,'keys':['MASSIVE_API_TOKEN'],")
add('E14_effects_grammar',"'value_grammar':TOKEN_VALUE_GRAMMAR,\n                                'chain'","'value_grammar':None,\n                                'chain'")
add('E15_effects_chain_said_signed',"                                'chain':'walked by this run, not signed'},","                                'chain':'signed'},")
add('E16_effects_token_days',"            'token_days':list(TOKEN_DAYS),'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],","            'token_days':list(DATES),'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],")
add('E17_effects_boot',"            'token_days':list(TOKEN_DAYS),'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],","            'token_days':list(TOKEN_DAYS),'evidence_boot_id_sha256':None,")
add('E18_effects_say_objects_modified',"            'pre_existing_objects_modified':False,'process_started':False,'activation':False,'value_in_receipt':False}",
    "            'pre_existing_objects_modified':True,'process_started':False,'activation':False,'value_in_receipt':False}")
add('E19_effects_say_a_process',"            'pre_existing_objects_modified':False,'process_started':False,'activation':False,'value_in_receipt':False}",
    "            'pre_existing_objects_modified':False,'process_started':True,'activation':False,'value_in_receipt':False}")
add('E20_effects_say_activation',"            'pre_existing_objects_modified':False,'process_started':False,'activation':False,'value_in_receipt':False}",
    "            'pre_existing_objects_modified':False,'process_started':False,'activation':True,'value_in_receipt':False}")
add('E21_effects_say_the_value_in_the_receipt',"            'pre_existing_objects_modified':False,'process_started':False,'activation':False,'value_in_receipt':False}",
    "            'pre_existing_objects_modified':False,'process_started':False,'activation':False,'value_in_receipt':None}")

# ---------------------------------------------------------------- the precheck
add('K01_executor_not_checked',"            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n","")
add('K02_umask_not_set',"            host.umask(0o077)\n            need(boot_id_sha256","            need(boot_id_sha256")
add('K03_umask_0022',"            host.umask(0o077)\n            need(boot_id_sha256","            host.umask(0o022)\n            need(boot_id_sha256")
add('K04_boot_not_compared',"            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n","")
add('K05_existing_token_not_refused',"                precheck['token_file_absent']=False;raise Refused('TOKEN_FILE_PRESENT')\n","                precheck['token_file_absent']=False\n")
add('K06_absence_not_reported',"            except FileNotFoundError:precheck['token_file_absent']=True\n","            except FileNotFoundError:pass\n")
add('K07_budget_not_checked',"            need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')\n","")
add('K08_budget_not_reported',"            left=gate();precheck['seconds_left_before_the_creation']=int(left)\n","            left=gate()\n")
add('K09_configuration_directory_not_proved_again',"            config.verify(gate)\n            code=None\n","            code=None\n")
add('K10_failing_system_call_of_the_precheck_not_told_apart',"            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')\n","            code=code_of(error,'PRECHECK_FAILED')\n")
add('K11_deploy_chain_walked_by_the_signed_rule_for_root',"        try:validate_chain(observed,deploy,open_root=deploy)\n","        try:validate_chain(observed,deploy)\n")
add('K12_deploy_chain_not_judged',"        try:validate_chain(observed,deploy,open_root=deploy)\n","        try:pass\n")
add('K13_absent_deploy_directory_not_said',"    except FileNotFoundError:raise Refused('DEPLOY_DIRECTORY_ABSENT') from None\n","")
add('K14_chain_fact_includes_the_deploy_directory',"all(row_root_safe(row) for row in observed[:-1])","all(row_root_safe(row) for row in observed)")
add('K15_chain_fact_of_writable_inverted',"facts['no_component_world_writable_without_sticky']=not any(","facts['no_component_world_writable_without_sticky']=any(")
add('K16_walk_fact_not_set',"        facts['walked_without_following_a_link']=True\n","")
add('K17_symlink_code_lost',"DEPLOY_CODES={'SYMLINK_COMPONENT':'DEPLOY_CHAIN_SYMLINK',","DEPLOY_CODES={'SYMLINK_COMPONENT':'SYMLINK_COMPONENT',")
add('K18_not_a_directory_code_lost',"'COMPONENT_NOT_DIRECTORY':'DEPLOY_CHAIN_NOT_A_DIRECTORY',","'COMPONENT_NOT_DIRECTORY':'COMPONENT_NOT_DIRECTORY',")
add('K22_changed_during_the_walk_code_lost',"'PATH_CHANGED':'DEPLOY_CHAIN_CHANGED_DURING_WALK',","'PATH_CHANGED':'PATH_CHANGED',")
add('K19_unsafe_row_code_lost',"'CHAIN_ROW_UNSAFE':'DEPLOY_CHAIN_UNSAFE_ABOVE_THE_DEPLOY_DIRECTORY',","'CHAIN_ROW_UNSAFE':'CHAIN_ROW_UNSAFE',")
add('K20_world_writable_code_lost',"'CHAIN_ROW_WORLD_WRITABLE':'DEPLOY_CHAIN_WORLD_WRITABLE'}","'CHAIN_ROW_WORLD_WRITABLE':'CHAIN_ROW_WORLD_WRITABLE'}")
ORDER="""            gate()
            try:host.lstat(TOKEN_NAME,config.fd)
            except FileNotFoundError:precheck['token_file_absent']=True
            else:
                precheck['token_file_absent']=False;raise Refused('TOKEN_FILE_PRESENT')
            fd,observed=deploy_chain(host,deploy,gate,chain);held.append(fd)
            raw=environment_bytes(host,fd,observed[-1]['uid'],gate,environment)
"""
add('K21_environment_file_read_before_the_token_is_looked_for',ORDER,"""            fd,observed=deploy_chain(host,deploy,gate,chain);held.append(fd)
            raw=environment_bytes(host,fd,observed[-1]['uid'],gate,environment)
            gate()
            try:host.lstat(TOKEN_NAME,config.fd)
            except FileNotFoundError:precheck['token_file_absent']=True
            else:
                precheck['token_file_absent']=False;raise Refused('TOKEN_FILE_PRESENT')
""")

# ---------------------------------------------------------------- the environment file
add('N01_absent_file_not_said',"    except FileNotFoundError:raise Refused('ENV_FILE_ABSENT') from None\n","    except FileNotFoundError:raise\n")
add('N02_link_or_special_file_read',"    need(stat.S_ISREG(named.st_mode),'ENV_FILE_NOT_REGULAR');facts['regular']=True\n","    facts['regular']=True\n")
add('N03_world_writable_file_read',"    need(not named.st_mode&0o002,'ENV_FILE_WORLD_WRITABLE');","    need(True,'ENV_FILE_WORLD_WRITABLE');")
add('N04_group_writable_refused_in_place_of_world',"    need(not named.st_mode&0o002,'ENV_FILE_WORLD_WRITABLE');","    need(not named.st_mode&0o020,'ENV_FILE_WORLD_WRITABLE');")
add('N05_owner_not_checked',"    need(named.st_uid in (0,owner),'ENV_FILE_OWNER_UNEXPECTED');","    need(True,'ENV_FILE_OWNER_UNEXPECTED');")
add('N06_root_owner_refused',"    need(named.st_uid in (0,owner),'ENV_FILE_OWNER_UNEXPECTED');","    need(named.st_uid==owner,'ENV_FILE_OWNER_UNEXPECTED');")
add('N07_vanished_while_read_not_said',"    except FileNotFoundError:raise Refused('ENV_FILE_CHANGED_DURING_READ') from None\n    except Refused as error:raise renamed(error,ENV_CODES) from None\n",
    "    except Refused as error:raise renamed(error,ENV_CODES) from None\n")
add('N08_vanished_after_the_read_not_said',"    try:after=host.lstat(ENV_FILE_NAME,fd)\n    except FileNotFoundError:raise Refused('ENV_FILE_CHANGED_DURING_READ') from None\n","    after=host.lstat(ENV_FILE_NAME,fd)\n")
add('N09_replaced_before_the_open_not_seen',"    need(stat_signature(info)==stat_signature(named)==stat_signature(after),","    need(stat_signature(named)==stat_signature(after),")
add('N10_replaced_after_the_read_not_seen',"    need(stat_signature(info)==stat_signature(named)==stat_signature(after),","    need(stat_signature(info)==stat_signature(named),")
add('N11_size_code_lost',"'FILE_TOO_LARGE':'ENV_FILE_TOO_LARGE',","'FILE_TOO_LARGE':'FILE_TOO_LARGE',")
add('N12_changed_code_lost',"'FILE_CHANGED_DURING_READ':'ENV_FILE_CHANGED_DURING_READ'}","'FILE_CHANGED_DURING_READ':'FILE_CHANGED_DURING_READ'}")
add('N13_regular_code_lost',"ENV_CODES={'FILE_NOT_REGULAR':'ENV_FILE_NOT_REGULAR',","ENV_CODES={'FILE_NOT_REGULAR':'FILE_NOT_REGULAR',")
add('N14_names_defined_reported_false',"    facts['names_defined']={key:any(name==key for name,_,_ in found) for key in TOKEN_KEYS}\n","    facts['names_defined']={key:False for key in TOKEN_KEYS}\n")
add('N15_syntax_fact_not_set',"    found=token_definitions(raw);facts['syntax_within_the_accepted_subset']=True;","    found=token_definitions(raw);")
add('N16_agreement_fact_not_set',"    facts['definitions_agree']=True;facts['value_grammar_met']=True\n","    facts['value_grammar_met']=True\n")
add('N17_read_fact_not_set',"    facts['unchanged_during_read']=True\n","")
add('N18_a_second_link_read',"    need(named.st_nlink==1,'ENV_FILE_LINKED');","    ")
add('N19_link_fact_not_set',"'ENV_FILE_LINKED');facts['single_link']=True","'ENV_FILE_LINKED')")
add('N20_readable_fact_inverted',"    facts['not_readable_by_group_or_other']=not named.st_mode&0o044","    facts['not_readable_by_group_or_other']=bool(named.st_mode&0o044)")
add('N21_readable_fact_of_other_only',"    facts['not_readable_by_group_or_other']=not named.st_mode&0o044","    facts['not_readable_by_group_or_other']=not named.st_mode&0o004")
add('N22_readable_fact_after_the_refusals',"    facts['not_readable_by_group_or_other']=not named.st_mode&0o044          # the exposure as found: said, never a refusal\n","")

# ---------------------------------------------------------------- the list of receipt codes
add('L01_code_of_the_run_not_listed',"        return seal(envelope(status,outcome,listed(code),","        return seal(envelope(status,outcome,code,")
add('L02_codes_of_the_token_file_not_listed',"        token[0].update(code=listed(token[0]['code']),withdrawal_code=listed(token[0]['withdrawal_code']))\n","")
add('L03_withdrawal_code_not_listed',"withdrawal_code=listed(token[0]['withdrawal_code']))","withdrawal_code=token[0]['withdrawal_code'])")
add('L04_a_code_missing_from_the_list',"    'TOKEN_FILE_PRESENT',\n","")
add('L05_every_text_listed',"def listed(code):return code if code is None or code in RECEIPT_CODES else UNLISTED_CODE","def listed(code):return code")

# ---------------------------------------------------------------- the creation, the readback, the withdrawal
add('W01_existing_name_reported_as_a_filesystem_error',"code='TOKEN_FILE_APPEARED_AFTER_PRECHECK' if error.errno==errno.EEXIST else filesystem_code(error))","code=filesystem_code(error))")
add('W02_refused_creation_not_said',"            row.update(state='NOT_CREATED',errno=number(error),","            row.update(state='NOT_CREATED',errno=None,")
add('W03_uncertain_creation_called_not_created',"            row.update(state='CREATE_UNCERTAIN',code='TOKEN_CREATE_UNCERTAIN');return row","            row.update(state='NOT_CREATED',code='TOKEN_CREATE_UNCERTAIN');return row")
add('W04_write_that_wrote_nothing_accepted',"                    if type(size) is not int or size<=0:return withdraw(fd,row,config,host,gate,state,'TOKEN_WRITE_INCOMPLETE')\n",
    "                    if type(size) is not int or size<=0:return row\n")
add('W05_write_error_left_in_place',"            except OSError as error:return withdraw(fd,row,config,host,gate,state,filesystem_code(error),error)\n",
    "            except OSError as error:\n                row['code']=filesystem_code(error);return row\n")
add('W06_failed_fsync_of_the_file_ignored',"            try:host.fsync(fd);row['fsync_file']=True\n            except OSError as error:return withdraw(fd,row,config,host,gate,state,'FSYNC_FAILED',error)\n",
    "            try:host.fsync(fd);row['fsync_file']=True\n            except OSError as error:pass\n")
add('W07_size_not_compared',"                if not (metadata_facts(info,row,config) and info.st_size==len(content)):","                if not metadata_facts(info,row,config):")
add('W08_metadata_not_compared',"                if not (metadata_facts(info,row,config) and info.st_size==len(content)):","                if not info.st_size==len(content):")
add('W09_failed_fsync_of_the_directory_ignored',"            try:host.fsync(config.fd);row['fsync_directory']=True\n            except OSError as error:return withdraw(fd,row,config,host,gate,state,'FSYNC_FAILED',error)\n",
    "            try:host.fsync(config.fd);row['fsync_directory']=True\n            except OSError as error:pass\n")
add('W10_directory_not_proved_before_the_readback',"            try:config.verify(gate)\n            except Refused as error:\n                row['code']=code_of(error,'PARENT_REPLACED');return row\n","")
add('W11_readback_inode_not_compared',"                if not (row['readback_same_inode'] and row['readback_bytes_equal_what_was_written'] and metadata_facts(seen,row,config)):",
    "                if not (row['readback_bytes_equal_what_was_written'] and metadata_facts(seen,row,config)):")
add('W12_readback_bytes_not_compared',"                if not (row['readback_same_inode'] and row['readback_bytes_equal_what_was_written'] and metadata_facts(seen,row,config)):",
    "                if not (row['readback_same_inode'] and metadata_facts(seen,row,config)):")
add('W13_readback_metadata_not_compared',"                if not (row['readback_same_inode'] and row['readback_bytes_equal_what_was_written'] and metadata_facts(seen,row,config)):",
    "                if not (row['readback_same_inode'] and row['readback_bytes_equal_what_was_written']):")
add('W14_expiry_in_the_readback_withdraws',"                if str(error) in ('GO_EXPIRED','CLOCK_REVERSED'):\n                    row['code']=str(error);return row\n","")
add('W15_failed_readback_left_in_place',"            except OSError as error:return withdraw(fd,row,config,host,gate,state,'READBACK_UNAVAILABLE',error)\n",
    "            except OSError as error:\n                row['code']='READBACK_UNAVAILABLE';return row\n")
add('W16_unexpected_failure_left_in_place',"            return withdraw(fd,row,config,host,gate,state,'TOKEN_PLACEMENT_FAILED')\n","            row['code']='TOKEN_PLACEMENT_FAILED';return row\n")
WITHDRAW="        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino) or named.st_nlink!=1:\n"
add('W17_withdrawal_removes_whatever_has_the_name',WITHDRAW,"        if named.st_nlink!=1:\n")
add('W18_withdrawal_removes_a_file_with_another_name',WITHDRAW,"        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino):\n")
add('W19_withdrawal_without_its_fsync',"    row.update(withdrawn=True,state='WITHDRAWN_NOT_DURABLE')\n    try:host.fsync(config.fd)\n","    row.update(withdrawn=True,state='WITHDRAWN_NOT_DURABLE')\n    try:pass\n")
add('W20_failed_withdrawal_said_withdrawn',"        row.update(withdrawal_code='TOKEN_WITHDRAWAL_FAILED',withdrawal_errno=number(error));return row\n","        row.update(withdrawal_code=None,withdrawn=True,state='WITHDRAWN');return row\n")
add('W21_uncertain_withdrawal_not_said',"        row['withdrawal_code']='TOKEN_WITHDRAWAL_UNCERTAIN';return row\n","        row['withdrawal_code']=None;return row\n")
add('W22_withdrawal_not_durable_called_durable',"        row.update(withdrawal_code='FSYNC_FAILED',withdrawal_errno=number(error));return row\n    row.update(state='WITHDRAWN',fsync_directory_after_withdrawal=True);return row\n",
    "        pass\n    row.update(state='WITHDRAWN',fsync_directory_after_withdrawal=True);return row\n")
add('W23_withdrawal_errno_of_the_cause_lost',"    if error is not None:row['errno']=number(error)\n","")
add('W24_uid_fact_always_true',"uid_0=info.st_uid==0,","uid_0=True,")
add('W25_gid_fact_always_true',"gid_0=info.st_gid==0,","gid_0=True,")
add('W26_mode_fact_always_true',"mode_0600=stat.S_IMODE(info.st_mode)==TOKEN_FILE_MODE,","mode_0600=True,")
add('W27_link_fact_always_true',"single_link=info.st_nlink==1,","single_link=True,")
add('W28_size_fact_always_true',"size_within_1_4096=1<=info.st_size<=TOKEN_MAX_FILE_BYTES,","size_within_1_4096=True,")
add('W29_device_fact_always_true',"on_the_device_of_the_directory=info.st_dev==config.identity[0])","on_the_device_of_the_directory=True)")
add('W30_regular_fact_always_true',"    row.update(regular=stat.S_ISREG(info.st_mode),","    row.update(regular=True,")
add('W31_supervisor_rules_without_the_mode',"row['meets_the_supervisor_file_rules']=all(row[key] for key in ('regular','uid_0','mode_0600','single_link','size_within_1_4096'))",
    "row['meets_the_supervisor_file_rules']=all(row[key] for key in ('regular','uid_0','single_link','size_within_1_4096'))")
add('W32_group_not_part_of_the_verdict',"    return row['meets_the_supervisor_file_rules'] and row['gid_0'] and row['on_the_device_of_the_directory']\n","    return row['meets_the_supervisor_file_rules'] and row['on_the_device_of_the_directory']\n")
add('W33_device_not_part_of_the_verdict',"    return row['meets_the_supervisor_file_rules'] and row['gid_0'] and row['on_the_device_of_the_directory']\n","    return row['meets_the_supervisor_file_rules'] and row['gid_0']\n")
add('W34_identity_of_the_file_not_reported',"                info=host.fstat(fd);row.update(device=info.st_dev,inode=info.st_ino)\n","                info=host.fstat(fd)\n")
add('W35_placed_without_its_code_cleared',"            row.update(state='PLACED_VERIFIED',code=None);return row\n","            row.update(state='PLACED_VERIFIED',code='DONE');return row\n")
add('W36_created_not_reported',"        row['created']=True;row['state']='LEFT_UNVERIFIED'\n","        row['state']='LEFT_UNVERIFIED'\n")

# ---------------------------------------------------------------- the verdict and the receipt
add('V01_a_refusal_after_a_failed_creation_called_partial',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n","")
add('V02_objects_left_by_a_placed_file',"    if row['state'] in ('PLACED_VERIFIED','LEFT_UNVERIFIED'):return 1\n","    if row['state'] in ('LEFT_UNVERIFIED',):return 1\n")
add('V03_objects_left_by_a_file_left',"    if row['state'] in ('PLACED_VERIFIED','LEFT_UNVERIFIED'):return 1\n","    if row['state'] in ('PLACED_VERIFIED',):return 1\n")
add('V04_uncertain_creation_counted_as_nothing_left',"    return None if row['state']=='CREATE_UNCERTAIN' else 0\n","    return 0\n")
add('V05_receipt_without_the_rows_as_read',"            config_directory={'rows':config_rows,'pinned':bool(pinned)},","            config_directory={'rows':[],'pinned':bool(pinned)},")
add('V06_receipt_says_pinned_always',"            config_directory={'rows':config_rows,'pinned':bool(pinned)},","            config_directory={'rows':config_rows,'pinned':True},")
add('V07_receipt_without_the_chain_facts',"deploy_chain=chain,environment_file=environment,precheck=precheck,","deploy_chain=chain_facts(),environment_file=environment,precheck=precheck,")
add('V08_receipt_without_the_environment_facts',"deploy_chain=chain,environment_file=environment,precheck=precheck,","deploy_chain=chain,environment_file=environment_facts(),precheck=precheck,")
add('V09_receipt_without_the_precheck',"deploy_chain=chain,environment_file=environment,precheck=precheck,","deploy_chain=chain,environment_file=environment,precheck={},")
add('V10_receipt_says_objects_modified',"left_by_this_run(token[0]),pre_existing_objects_modified=False,**extra)))","left_by_this_run(token[0]),pre_existing_objects_modified=None,**extra)))")
add('V11_receipt_without_the_clock',"            clock=timing(begun,mark,clock,monotonic),mutating_calls=state.counts(),","            clock=None,mutating_calls=state.counts(),")
add('V12_receipt_without_the_mutating_calls',"            clock=timing(begun,mark,clock,monotonic),mutating_calls=state.counts(),","            clock=timing(begun,mark,clock,monotonic),mutating_calls=None,")
add('V13_readback_said_complete_after_a_stop',"        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None}","        extra={'phase_reached':'EFFECTS','readback':'COMPLETE'}")
add('V14_buffer_not_handed_to_the_zeroing',"            content=environment_token(raw,environment);buffers.append(content);raw=None\n","            content=environment_token(raw,environment);raw=None\n")
add('V15_reduction_keeps_the_rows',"def _reduce_config(receipt):receipt['config_directory']={'rows_reduced_for_size':len((receipt.get('config_directory') or {}).get('rows') or [])}",
    "def _reduce_config(receipt):receipt['config_directory']=dict(receipt.get('config_directory') or {})")

# ---------------------------------------------------------------- revision 3: the process made non-dumpable first (CONTRACT D9)
FIRST=("            process['dumpable_disabled']=False\n"
       "            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');process['dumpable_disabled']=True\n")
EXECUTOR="            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n"
WALK="            fd,observed=deploy_chain(host,deploy,gate,chain);held.append(fd)\n"
READ="            raw=environment_bytes(host,fd,observed[-1]['uid'],gate,environment)\n"
PRECHECK_TO_READ=(FIRST+EXECUTOR+"""            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            config=Pinned(host,walk_pinned(host,plan['config_chain'],gate,config_rows),rows=plan['config_chain']);pinned.append(config)
            gate()
            try:host.lstat(TOKEN_NAME,config.fd)
            except FileNotFoundError:precheck['token_file_absent']=True
            else:
                precheck['token_file_absent']=False;raise Refused('TOKEN_FILE_PRESENT')
"""+WALK+READ)
add('X01_process_not_made_non_dumpable',FIRST,"            process['dumpable_disabled']=False\n")
add('X02_answer_of_the_host_not_checked',"            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');","            host.not_dumpable();")
add('X03_any_true_answer_taken',"            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');","            need(host.not_dumpable(),'PROCESS_DUMPABLE_NOT_DISABLED');")
add('X04_after_the_executor_check',FIRST+EXECUTOR,EXECUTOR+FIRST)
add('X05_after_the_walk_of_the_deploy_chain',PRECHECK_TO_READ,PRECHECK_TO_READ.replace(FIRST,'').replace(WALK,WALK+FIRST))
add('X06_after_the_read_of_the_environment_file',PRECHECK_TO_READ,PRECHECK_TO_READ.replace(FIRST,'').replace(READ,READ+FIRST))
add('X07_fact_not_set_true',"'PROCESS_DUMPABLE_NOT_DISABLED');process['dumpable_disabled']=True\n","'PROCESS_DUMPABLE_NOT_DISABLED')\n")
add('X08_fact_true_before_the_call',"            process['dumpable_disabled']=False\n","            process['dumpable_disabled']=True\n")
add('X09_receipt_says_disabled_always',"mutating_calls=state.counts(),process=process,","mutating_calls=state.counts(),process={'dumpable_disabled':True},")
add('X10_code_missing_from_the_list',"    'PROCESS_DUMPABLE_NOT_DISABLED','EXECUTOR_IDENTITY',","    'EXECUTOR_IDENTITY',")
add('X11_effects_without_the_process',"            'process':{'dumpable':0,'when':'first, before the deploy directory or the environment file is opened','core_dump':'none, to a file or through a pipe'},\n","")
add('X12_effects_say_dumpable',"            'process':{'dumpable':0,'when'","            'process':{'dumpable':1,'when'")

def core(name,old,new):MUTANTS.append((name,'core',old,new))
DUMP="        disabled=library.prctl(PR_SET_DUMPABLE,0,0,0,0)==0 and library.prctl(PR_GET_DUMPABLE,0,0,0,0)==0\n"
core('Y01_prctl_set_not_made',DUMP,"        disabled=library.prctl(PR_GET_DUMPABLE,0,0,0,0)==0\n")
core('Y02_read_back_skipped',DUMP,"        disabled=library.prctl(PR_SET_DUMPABLE,0,0,0,0)==0\n")
core('Y03_read_back_before_the_set',DUMP,"        disabled=library.prctl(PR_GET_DUMPABLE,0,0,0,0)==0 and library.prctl(PR_SET_DUMPABLE,0,0,0,0)==0\n")
core('Y04_set_with_the_option_number_of_get',"PR_SET_DUMPABLE=4\n","PR_SET_DUMPABLE=3\n")
core('Y05_get_with_the_option_number_of_set',"PR_GET_DUMPABLE=3\n","PR_GET_DUMPABLE=4\n")
core('Y06_attribute_set_to_1',"library.prctl(PR_SET_DUMPABLE,0,0,0,0)==0","library.prctl(PR_SET_DUMPABLE,1,0,0,0)==0")
core('Y07_any_read_back_accepted',"library.prctl(PR_GET_DUMPABLE,0,0,0,0)==0\n","library.prctl(PR_GET_DUMPABLE,0,0,0,0)!=-1\n")
core('Y08_failure_not_refused',"    need(disabled,'PROCESS_DUMPABLE_NOT_DISABLED');return True\n","    return True\n")
core('Y09_native_says_disabled_without_a_call',"    def not_dumpable(self):return dumps_disabled()","    def not_dumpable(self):return True")
