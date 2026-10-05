"""The mutants of the three bind-time tools of K10 (binding/release_fields.py, binding/linux_proof.py,
binding/predispatch.py): mutate.py with HOSTOPS_MUTATION_LIST=tools (records MUTATION_TOOLS.json and
MUTATION_TOOLS.py312.json). Zero survivors is required.

The tools are not payload bytes, but each of them stands between a state that would end the epoch and the single
dispatch, so each refusal of each tool has a mutant: one per check of the two gates (the check is answered true
whatever it finds; generated from the check names in the tool's own text, so a new check without a test is a
survivor), one per refusal of release_fields.py, and the constants and the conjuncts a check is made of.
A row is (name, target, exact anchor, replacement); the target is the tool's file name without its suffix."""
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent.parent
MUTANTS=[]
def add(name,target,old,new):MUTANTS.append((name,target,old,new))
def text_of(name):return (HERE/'binding'/(name+'.py')).read_text()

# ---------------------------------------------------------------- predispatch.py: every check answered true
ANSWER="        try:ok=test() is True\n"
for name in re.findall(r"    check\('([A-Z0-9_]+)',",text_of('predispatch')):
    add('G_%s_answered_true'%name,'predispatch',ANSWER,"        try:ok=True if name=='%s' else test() is True\n"%name)
add('G50_a_check_that_raises_is_true','predispatch',"        except Exception:ok=False\n","        except Exception:ok=True\n")
add('G51_boot_margin_dropped','predispatch',"BOOT_MARGIN_SECONDS=60 ","BOOT_MARGIN_SECONDS=0 ")
add('G52_clock_skew_one_second_more','predispatch',"CLOCK_SKEW_SECONDS=30 ","CLOCK_SKEW_SECONDS=31 ")
add('G53_snapshot_may_be_one_second_older','predispatch',"M0_MAX_AGE_SECONDS=3600 ","M0_MAX_AGE_SECONDS=3601 ")
add('G54_resume_one_second_earlier','predispatch',"RESUME_AFTER_SECONDS=120 ","RESUME_AFTER_SECONDS=119 ")
add('G55_watchdog_one_second_less','predispatch',"WATCHDOG_SECONDS=80 ","WATCHDOG_SECONDS=79 ")
add('G56_free_bytes_factor_one_less','predispatch',"FREE_BYTES_FACTOR=16 ","FREE_BYTES_FACTOR=15 ")
add('G57_free_inodes_floor_one_less','predispatch',"FREE_INODES_FLOOR=1024 ","FREE_INODES_FLOOR=1023 ")
add('G58_a_filesystem_without_hard_links_accepted','predispatch',"HARD_LINK_FILESYSTEMS=('ext4','ext3','xfs','btrfs')","HARD_LINK_FILESYSTEMS=('ext4','ext3','xfs','btrfs','vfat')")
PIN="(listing['pin']['type'],listing['pin']['uid'],listing['pin']['gid'])==('file',0,0))"
add('G59_pin_group_not_judged','predispatch',PIN,"(listing['pin']['type'],listing['pin']['uid'])==('file',0))")
add('G60_pin_owner_not_judged','predispatch',PIN,"(listing['pin']['type'],listing['pin']['gid'])==('file',0))")
add('G61_pin_type_not_judged','predispatch',PIN,"(listing['pin']['uid'],listing['pin']['gid'])==(0,0))")
add('G62_pin_presence_not_judged','predispatch',"lambda:listing['pin']['exists'] is True and (listing","lambda:(listing")
ROWS="row['type']=='dir' and (row['path'],row['device'],row['inode'],row['uid'],row['gid'],int(row['mode_octal'],8))\n            ==(want['path'],want['device'],want['inode'],want['uid'],want['gid'],want['mode'])"
for index,(label,seen,signed) in enumerate((('path',"row['path'],","want['path'],"),('device',"row['device'],","want['device'],"),('inode',"row['inode'],","want['inode'],"),
                                            ('uid',"row['uid'],","want['uid'],"),('gid',"row['gid'],","want['gid'],"),('mode',",int(row['mode_octal'],8)",",want['mode']"))):
    add('G%d_parent_row_%s_not_compared'%(63+index,label),'predispatch',ROWS,ROWS.replace(seen,'').replace(signed,''))
add('G69_parent_row_type_not_judged','predispatch',ROWS,ROWS.replace("row['type']=='dir' and ",""))
add('G70_parent_source_not_judged','predispatch',"return (volume['source']==module.DATA_VOLUME and len(seen)","return (len(seen)")
add('G71_fewer_rows_than_signed_accepted','predispatch',"len(seen)==len(signed)==3 and all(","all(")
VOLUME=("lambda:filesystem['read_only'] is False and mount['read_write'] is True\n          and mount['mount_point_is_the_path'] is True and "
        "mount['device_equals_the_directory_device'] is True and mount['mount_point']==module.DATA_VOLUME)")
for index,part in enumerate(("filesystem['read_only'] is False and ","mount['read_write'] is True\n          and ","mount['mount_point_is_the_path'] is True and ",
                             "mount['device_equals_the_directory_device'] is True and "," and mount['mount_point']==module.DATA_VOLUME")):
    add('G%d_volume_conjunct_%d_dropped'%(72+index,index+1),'predispatch',VOLUME,VOLUME.replace(part,''))
add('G77_receipt_hash_not_recomputed','predispatch',"return module.hexpin(pin) and sha(module.canonical(body))==pin","return module.hexpin(pin)")
add('G78_uncertain_snapshot_accepted','predispatch',"m0_exit['status'] in ('KNOWN_COMPLETE','KNOWN_PARTIAL')","m0_exit['status'] in ('KNOWN_COMPLETE','KNOWN_PARTIAL','UNCERTAIN')")
add('G79_exit_not_bound_to_the_receipt_bytes','predispatch',"          and m0_exit['stdout_sha256']==sha(blobs['m0-receipt']) and ","          and ")
add('G80_receipt_not_bound_to_the_m0_request','predispatch',"          and m0['request_sha256']==sha(blobs['m0-request']) and ","          and ")
add('G81_receipt_of_another_host_accepted','predispatch'," and m0['host_binding_sha256']==request['host_binding_sha256']==m0_request['host_binding_sha256'])",")")
add('G82_evidence_need_not_be_named_by_the_request','predispatch',
    "          and any(item['operation']==module.PRECHECK_OPERATION and item['receipt_sha256']==evidence['metadata_sha256'] for item in request['evidence'])\n","")
add('G83_evidence_boot_not_compared_with_the_plan','predispatch'," and evidence['items']['boot']['boot_id_sha256']==plan['evidence_boot_id_sha256'])",")")
add('G84_evidence_taken_after_the_snapshot_accepted','predispatch',"<=epoch(module,evidence['observed_at'])<=host_end())","<=epoch(module,evidence['observed_at']))")
add('G85_boot_epoch_of_any_type','predispatch',"lambda:type(sections['runtime']['boot']['boot_epoch_utc']) is int\n          and sections","lambda:sections")
add('G86_destination_candidate_row_of_another_index','predispatch',"if row.get('candidate_index')==names.index(module.RELEASE_DIRECTORY_NAME)]","]")
add('G87_destination_unanswered_counts_as_absent','predispatch',"rows[0]['status']=='COMPLETE' and rows[0]['exists'] is False","rows[0].get('exists') is not True")
add('G88_snapshot_of_another_day_accepted','predispatch',"lambda:module.instant(m0['observed_at']).date().isoformat()==request['date']\n          and -CLOCK","lambda:-CLOCK")
add('G89_snapshot_from_the_future_accepted','predispatch',"-CLOCK_SKEW_SECONDS<=now.timestamp()-host_end()<=M0_MAX_AGE_SECONDS","now.timestamp()-host_end()<=M0_MAX_AGE_SECONDS")
add('G90_spare_ignores_the_claim_of_the_primary','predispatch'," and primary_claim_exists is False)",")")
add('G91_spare_accepts_its_own_go_as_the_primary','predispatch',"              and primary['request_sha256']!=sha(blobs['request']) and ","              and ")
add('G92_spare_accepts_a_go_of_another_operation','predispatch',"lambda:primary['schema']==module.GO_SCHEMA and primary['payload_sha256']==source_sha256\n","lambda:primary['payload_sha256']==source_sha256\n")
add('G93_spare_may_omit_the_primary','predispatch',"    if spare!=('--primary-go' in found) or spare!=('--claim-root' in found):return None\n","")
add('G94_claim_looked_for_under_another_name','predispatch',"name='.go-'+sha(blobs['primary-go'])+'.claim'","name='.go-'+sha(blobs['request'])+'.claim'")
add('G95_request_of_another_payload_accepted','predispatch'," and request['payload_sha256']==source_sha256 and request['date']"," and request['date']")
add('G96_plan_not_validated','predispatch',"        module.validate_common(plan);module.validate_plan(plan);return True\n","        return True\n")
add('G97_unreadable_input_is_a_do_not_dispatch_with_exit_1','predispatch',"        sys.stderr.write('REFUSED INPUT_UNREADABLE\\n');return 2\n","        sys.stderr.write('REFUSED INPUT_UNREADABLE\\n');return 1\n")
add('G98_exit_0_whatever_failed','predispatch',"    return 0 if not failed else 1\n","    return 0\n")
add('G99_decision_allowed_whatever_failed','predispatch',"'decision':'DISPATCH_ALLOWED' if not failed else 'DO_NOT_DISPATCH'","'decision':'DISPATCH_ALLOWED'")

# ---------------------------------------------------------------- linux_proof.py: every check answered true
RECORDED="    def check(name,ok):checks.append((name,bool(ok)))\n"
proof=text_of('linux_proof')
names=re.findall(r"    check\('([A-Z0-9_]+)',",proof)+[label+name for name in re.findall(r"        check\(label\+'([A-Z0-9_]+)',",proof) for label in ('ROOT','USER')]
for name in names:
    add('L_%s_answered_true'%name,'linux_proof',RECORDED,"    def check(name,ok):checks.append((name,True if name=='%s' else bool(ok)))\n"%name)
add('L50_a_skipped_test_counts_as_passed','linux_proof',"state='skipped' if case.find('skipped') is not None else 'failed'","state='passed' if case.find('skipped') is not None else 'failed'")
add('L51_a_failed_test_counts_as_passed','linux_proof',"else 'failed' if case.find('failure') is not None or case.find('error') is not None else 'passed'","else 'passed'")
add('L52_an_error_is_not_a_failure','linux_proof',"case.find('failure') is not None or case.find('error') is not None","case.find('failure') is not None")
add('L53_one_passed_parameter_is_enough','linux_proof',"set(root['cases'][name])=={'passed'} for name in REQUIRED","'passed' in root['cases'][name] for name in REQUIRED")
add('L54_exit_0_whatever_was_decided','linux_proof',"    return 0 if result['decision']=='LINUX_PROOF_ACCEPTED' else 1\n","    return 0\n")
add('L55_accepted_whatever_failed','linux_proof',"decision='LINUX_PROOF_ACCEPTED' if not failed else 'LINUX_PROOF_REFUSED'","decision='LINUX_PROOF_ACCEPTED'")
add('L56_an_unreadable_file_is_ignored','linux_proof',"        if code is not None:problems.append('%s_FILE_%s'%(label.upper(),code))\n","        if code is not None:files[label]={'sha256':label,'bytes':0,'counts':{'tests':0,'failures':0,'errors':0,'skipped':0},'cases':{},'case_count':0,'skipped':[],'failed':[],'record':{}}\n")
add('L57_python_of_any_3_1x','linux_proof',"str(record.get('python','')).startswith('3.12.')","str(record.get('python','')).startswith('3.1')")
add('L58_case_count_not_compared_with_the_seal','linux_proof',"counts['tests']==tests==item['case_count']","counts['tests']==item['case_count']")
add('L59_declared_count_trusted_without_the_cases','linux_proof',"counts['tests']==tests==item['case_count']","counts['tests']==tests")
for index,name in enumerate(('test_native_install_creates_the_directory_and_the_file_with_exactly_these_system_calls','test_native_refusals_leave_the_real_tree_exactly_as_it_was',
                             'test_native_never_replaces_a_name_that_appears_and_withdraws_only_its_own_temporary',
                             'test_native_process_death_leaves_a_state_a_later_read_tells_apart_and_a_second_run_never_repairs',
                             'test_native_noatime_is_required_and_fails_closed_where_the_platform_lacks_it')):
    add('L%d_required_test_%d_not_required'%(60+index,index+1),'linux_proof',"'%s',\n"%name,"\n")
add('L65_recording_test_not_required','linux_proof',"          RECORD)\n","          )\n")

# ---------------------------------------------------------------- release_fields.py: every refusal
for index,(code,line) in enumerate((
    ('EXPECTATION_INVALID',"            raise Refusal('EXPECTATION_INVALID')\n"),
    ('RELEASE_SHA256_NOT_THE_EXPECTED_HASH',"    if hashlib.sha256(raw).hexdigest()!=expected['sha256']:raise Refusal('RELEASE_SHA256_NOT_THE_EXPECTED_HASH')\n"),
    ('RELEASE_CODE_REVISION_NOT_THE_EXPECTED_REVISION',"    if facts['code_revision']!=expected['code_revision']:raise Refusal('RELEASE_CODE_REVISION_NOT_THE_EXPECTED_REVISION')\n"),
    ('RELEASE_PACKAGE_NOT_THE_EXPECTED_PACKAGE',"    if facts['implementation_package_sha']!=expected['implementation_package_sha']:raise Refusal('RELEASE_PACKAGE_NOT_THE_EXPECTED_PACKAGE')\n"),
    ('RELEASE_IS_A_SYNTHETIC_FIXTURE',"    if any(text.startswith(SYNTHETIC_MARK) for text in strings(module.strict(raw))):raise Refusal('RELEASE_IS_A_SYNTHETIC_FIXTURE')\n"),
    ('EXPECTATION_NOT_THE_DEPLOYED_RELEASE',"        raise Refusal('EXPECTATION_NOT_THE_DEPLOYED_RELEASE')\n"))):
    add('B%02d_%s_not_refused'%(index+1,code),'release_fields',line,line.replace("raise Refusal('%s')"%code,'pass'))
add('B10_deployed_revision_is_another','release_fields',"DEPLOYED={'code_revision':'dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'","DEPLOYED={'code_revision':'0123456789abcdef0123456789abcdef01234567'")
add('B11_deployed_package_is_another','release_fields',"'implementation_package_sha':'b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'}","'implementation_package_sha':'"+'c'*64+"'}")
add('B12_deployed_package_not_compared','release_fields',"(expected['code_revision'],expected['implementation_package_sha'])!=(deployed['code_revision'],deployed['implementation_package_sha'])",
    "expected['code_revision']!=deployed['code_revision']")
add('B13_deployed_revision_not_compared','release_fields',"(expected['code_revision'],expected['implementation_package_sha'])!=(deployed['code_revision'],deployed['implementation_package_sha'])",
    "expected['implementation_package_sha']!=deployed['implementation_package_sha']")
add('B14_fixture_mark_is_another_text','release_fields',"SYNTHETIC_MARK='SYNTHETIC_FIXTURE'","SYNTHETIC_MARK='SYNTHETIC_FIXTURE_NOT'")
add('B15_fixture_mark_looked_for_at_the_top_level_only','release_fields',"    elif type(value) is dict:\n        for key,item in value.items():\n            yield key\n            for found in strings(item):yield found\n",
    "    elif type(value) is dict:\n        for key,item in value.items():\n            yield key\n            if type(item) is str:yield item\n")
add('B16_an_option_may_be_missing','release_fields',"    if len(paths)!=1 or set(expected)!={name for name,_ in OPTIONS.values()}:return None\n","    if len(paths)!=1:return None\n    for name,_ in OPTIONS.values():expected.setdefault(name,'0'*64)\n")
add('B17_an_option_may_be_given_twice','release_fields',"            if index+1>=len(arguments) or OPTIONS[word][0] in expected:return None\n","            if index+1>=len(arguments):return None\n")
add('B18_an_unknown_option_is_a_file','release_fields',"        elif word.startswith('-'):return None\n","")
add('B19_zero_hash_expectation_accepted','release_fields'," or expected[name]=='0'*len(expected[name]):",":")
add('B20_expectation_grammar_unchecked','release_fields',"if type(expected.get(name)) is not str or re.fullmatch(pattern,expected[name]) is None or expected[name]=='0'*len(expected[name]):",
    "if type(expected.get(name)) is not str or expected[name]=='0'*len(expected[name]):")
add('B21_refusal_is_exit_0','release_fields',"        err.write('REFUSED %s\\n'%code);return 1\n","        err.write('REFUSED %s\\n'%code);return 0\n")
add('B22_command_line_takes_the_deployed_values_from_the_file','release_fields',"    deployed=DEPLOYED if deployed is None else deployed;","    deployed={'code_revision':arguments[-3] if len(arguments)>3 else '','implementation_package_sha':arguments[-1] if arguments else ''} if deployed is None else deployed;")
COMBOS={}
REDUNDANT={}
