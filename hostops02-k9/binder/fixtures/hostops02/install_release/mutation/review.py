"""The reviewer's own mutants of K10 (review of 2026-10-02, lens: purity and authentication), kept as a list of this
operation: mutate.py with HOSTOPS_MUTATION_LIST=review (records MUTATION_REVIEW.json and MUTATION_REVIEW.py312.json).

They are the rows of review-purity/mutate_review.py as the reviewer wrote them, anchors and replacements unchanged:
60 changes of the assembled source (the core, parents and files parts as K10 carries them, and the operation part), of
the generated dispatcher and of the launcher. The first suite of K10 killed 33 of them and 27 survived (reproduced on
a copy of that directory, both interpreters). Zero survivors is required now, except the two rows of EQUIVALENT.

A row is (name, target, exact anchor, replacement), or for a mutant made of several replacements a list of
(target, anchor, replacement) in MULTI. Targets: 'op' is build/install_release.py, 'dispatcher' and 'launcher' the
generated files. Every anchor must occur exactly once (mutate.py check)."""
MUTANTS=[]
MULTI={}
TARGET={'op':'op','d':'dispatcher','l':'launcher'}
def add(name,target,*pairs):
    if len(pairs)==1:MUTANTS.append((name,TARGET[target],pairs[0][0],pairs[0][1]))
    else:MULTI[name]=[(TARGET[target],old,new) for old,new in pairs]

# ---- authentication (core part inside the assembled source)
add('A01_hexpin_accepts_the_zero_hash','op',("def hexpin(value):return text(value,HEX64) and value!='0'*64","def hexpin(value):return text(value,HEX64)"))
add('A02_gate_wall_end_inclusive','op',("need(self.start<=wall<self.end and mono<self.deadline,'GO_EXPIRED')","need(self.start<=wall<=self.end and mono<self.deadline,'GO_EXPIRED')"))
add('A03_gate_deadline_inclusive','op',("need(self.start<=wall<self.end and mono<self.deadline,'GO_EXPIRED')","need(self.start<=wall<self.end and mono<=self.deadline,'GO_EXPIRED')"))
add('A04_gate_opening_end_inclusive','op',("need(start<=self.wall<end,'OUTSIDE_GO_WINDOW')","need(start<=self.wall<=end,'OUTSIDE_GO_WINDOW')"))
add('A05_span_cap_exclusive','op',("(end-start).total_seconds()<=MAX_GATE_SPAN_SECONDS,'WINDOW_SPAN')","(end-start).total_seconds()<MAX_GATE_SPAN_SECONDS,'WINDOW_SPAN')"))
add('A06_payload_bytes_not_pinned','op',("('go',go_bytes),('payload',payload_bytes)]:","('go',go_bytes)]:"))
add('A07_raw_text_of_a_refusal_leaves','op',("    if isinstance(error,Refused) and text(str(error),CODE):return str(error)\n    return fallback","    if isinstance(error,Refused):return str(error)\n    return fallback"))
add('A08_non_os_failure_of_a_mutating_call_counts_as_nothing_changed','op',("    except OSError:state.fail();raise\n    state.done();return result","    except Exception:state.fail();raise\n    state.done();return result"))
add('A09_gate_span_measured_on_the_request_only','op',("    start,end=max(starts),min(ends)\n","    start,end=max(starts),min(ends)\n    span_start,span_end=starts[0],ends[0]\n"),
    ("need(start<end and (end-start).total_seconds()<=MAX_GATE_SPAN_SECONDS,'WINDOW_SPAN')","need(start<end and (span_end-span_start).total_seconds()<=MAX_GATE_SPAN_SECONDS*4,'WINDOW_SPAN')"))
add('A10_owner_may_exceed_128_characters','op',("and len(go['owner'])<=128\n","\n"))
add('A11_evidence_role_free_text','op',("text(item['role'],'[A-Z][A-Z0-9_]{0,63}')","type(item['role']) is str"))
add('A12_plan_window_tied_to_the_gate_not_to_the_request','op',("need(instant(plan['window']['not_before'])==starts[0] and instant(plan['window']['expires_at'])==ends[0],'PLAN_WINDOW')","need(instant(plan['window']['not_before'])<=start and instant(plan['window']['expires_at'])>=end,'PLAN_WINDOW')"))
# ---- pinned parents and the walk
add('W01_row_of_the_root_not_compared','op',("            need(stat.S_ISDIR(info.st_mode) and row_equal(seen,row,compare_device),'PARENT_IDENTITY_MISMATCH')","            need(index==0 or (stat.S_ISDIR(info.st_mode) and row_equal(seen,row,compare_device)),'PARENT_IDENTITY_MISMATCH')"))
add('W02_child_verify_does_not_prove_its_parent_again','op',("                self.parent.verify(check);check()\n","                check()\n"))
add('W03_chain_row_path_not_tied_to_the_constant_path','op',("need(type(row) is dict and set(row)==set(CHAIN_ROW_KEYS) and row['path']==prefix,code)","need(type(row) is dict and set(row)==set(CHAIN_ROW_KEYS) and type(row['path']) is str,code)"))
add('W04_child_stamp_is_identity_only','op',("        info=host.fstat(fd);self.identity=(info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))\n    def stamp(self,info):return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))",
    "        info=host.fstat(fd);self.identity=(info.st_dev,info.st_ino)\n    def stamp(self,info):return (info.st_dev,info.st_ino)"))
add('W05_only_the_last_row_is_compared','op',("            need(stat.S_ISDIR(info.st_mode) and row_equal(seen,row,compare_device),'PARENT_IDENTITY_MISMATCH')","            need(index<len(rows)-1 or (stat.S_ISDIR(info.st_mode) and row_equal(seen,row,compare_device)),'PARENT_IDENTITY_MISMATCH')"))
add('W06_root_safe_ignores_group_write','op',("def row_root_safe(row):return row['uid']==0 and not row['mode']&0o022","def row_root_safe(row):return row['uid']==0 and not row['mode']&0o002"))
# ---- the creating calls and their proofs (files part)
DIRCHECK="        if not (stat.S_ISDIR(info.st_mode) and info.st_uid==0 and info.st_gid==0\n                and stat.S_IMODE(info.st_mode)==mode and info.st_dev==parent.identity[0]):"
add('F01_created_directory_group_not_checked','op',(DIRCHECK,DIRCHECK.replace("info.st_gid==0","True")))
add('F02_created_directory_owner_not_checked','op',(DIRCHECK,DIRCHECK.replace("info.st_uid==0","True")))
add('F03_created_directory_device_not_checked','op',(DIRCHECK,DIRCHECK.replace(" and info.st_dev==parent.identity[0]","")))
FILECHECK="            if not (stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==0 and info.st_gid==0\n                    and stat.S_IMODE(info.st_mode)==mode and info.st_size==len(content)\n                    and info.st_dev==directory.identity[0]):return withdrawn('CREATED_METADATA_MISMATCH')"
add('F04_created_file_size_not_checked','op',(FILECHECK,FILECHECK.replace(" and info.st_size==len(content)","")))
add('F05_created_file_group_not_checked','op',(FILECHECK,FILECHECK.replace("info.st_gid==0","True")))
add('F06_created_file_owner_not_checked','op',(FILECHECK,FILECHECK.replace("info.st_uid==0","True")))
add('F07_created_file_type_not_checked','op',(FILECHECK,FILECHECK.replace("stat.S_ISREG(info.st_mode) and ","")))
add('F08_no_gate_before_the_temporary_is_looked_at_again','op',("            gate();named=host.lstat(temp,directory.fd)\n            if (named.st_dev,named.st_ino,named.st_nlink)","            named=host.lstat(temp,directory.fd)\n            if (named.st_dev,named.st_ino,named.st_nlink)"))
add('F09_directory_readback_does_not_check_the_type','op',(" and found['type']=='dir'\n",'\n')) 
add('F10_file_readback_reads_without_noatime','op',("os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|host.noatime(),dir_fd=dir_fd)","os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=dir_fd)"))
add('F11_file_readback_size_not_compared_with_the_stat','op',("need(signature(before)==signature(after) and size==before.st_size,'FILE_CHANGED_DURING_READ')","need(signature(before)==signature(after),'FILE_CHANGED_DURING_READ')"))
add('F12_expiry_while_writing_withdraws_the_temporary','op',("        except Refused as error:return failed(code_of(error,'GO_EXPIRED'))\n        except OSError as error:return withdrawn(filesystem_code(error),error)","        except Refused as error:return withdrawn(code_of(error,'GO_EXPIRED'))\n        except OSError as error:return withdrawn(filesystem_code(error),error)"))
add('F13_eexist_at_mkdir_is_a_plain_filesystem_error','op',("code='DESTINATION_APPEARED_AFTER_PRECHECK' if error.errno==errno.EEXIST else filesystem_code(error))\n        return entry","code=filesystem_code(error))\n        return entry"))
# ---- the operation part
add('O01_umask_leaves_nothing_to_the_owner_write','op',("            host.umask(0o077)\n","            host.umask(0o277)\n"))
add('O02_precheck_swallows_the_death_of_the_process','op',("        except Exception as error:\n            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')","        except BaseException as error:\n            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')"))
PIN3=("            need(pin is not None,'MAINTENANCE_PIN_ABSENT')\n            need(pin['type']=='file','MAINTENANCE_PIN_NOT_A_REGULAR_FILE')\n            need((pin['uid'],pin['gid'])==(0,0),'MAINTENANCE_PIN_NOT_ROOT_OWNED')\n")
MK="        entry=create_directory('RELEASE_DIRECTORY',RELEASE_DIRECTORY,PRIVATE_DIRECTORY_MODE,parent,host,gate,state,handles);directories.append(entry)\n        if entry['state']!='CREATED_DURABLE':stop=entry['code'] or 'CREATION_FAILED'\n"
add('O03_pin_judged_after_the_directory_exists','op',(PIN3,""),(MK,MK+"        if stop is None and (pin is None or pin['type']!='file' or (pin['uid'],pin['gid'])!=(0,0)):stop='MAINTENANCE_PIN_ABSENT'\n"))
BOOT="            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n"
add('O04_boot_judged_after_the_directory_exists','op',(BOOT,""),(MK,MK+"        if stop is None and boot_id_sha256(host,gate)!=plan['evidence_boot_id_sha256']:stop='EVIDENCE_FROM_EARLIER_BOOT'\n"))
add('O05_destination_judged_by_the_mkdir_alone_and_free_space_after','op',("            need(free>=FREE_BYTES_FLOOR,'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR')\n",""),(MK,MK+"        if stop is None and free<FREE_BYTES_FLOOR:stop='DATA_VOLUME_FREE_SPACE_BELOW_FLOOR'\n"))
add('O06_content_written_is_not_the_checked_bytes','op',("    content=release_of(plan)                                  # pure: the bytes that will be written, and no others","    content=release_of(plan)+b'\\n'"))
add('O07_receipt_reports_the_signed_hash_as_observed','op',("'sha256':row['sha256_observed'],'bytes':row['bytes'],","'sha256':row['sha256_signed'],'bytes':row['bytes'],"))
add('O08_release_must_only_parse_at_run_time','op',("    release_facts(release_of(plan))\n    need(instant(NEW_YORK_DAY_UTC[0])<=instant(plan['window']['not_before'])","    release_of(plan)\n    need(instant(NEW_YORK_DAY_UTC[0])<=instant(plan['window']['not_before'])"),
    ("            'release':release_facts(release_of(plan)),\n","            'release':None,\n"))
add('O09_destination_symlink_counts_as_absent','op',("    except FileNotFoundError:return None\n    return {'type':kind(info.st_mode)","    except FileNotFoundError:return None\n    if stat.S_ISLNK(info.st_mode):return None\n    return {'type':kind(info.st_mode)"))
add('X01_carried_T08_clean_ignores_uncertain_calls','op',("    def clean(self):return self.succeeded==0 and self.uncertain()==0\n","    def clean(self):return self.succeeded==0\n"))
add('X02_carried_F13_created_directory_mode_not_compared','op',(DIRCHECK,DIRCHECK.replace("                and stat.S_IMODE(info.st_mode)==mode and ","                and ")))
# ---- dispatcher
add('D01_final_bundle_bytes_not_compared','d',("    need(expected==blobs['payload'],'FINAL_BUNDLE_BYTES')\n",""))
add('D02_inner_windows_not_compared_with_the_config','d',("    need(start>=instant(request['not_before']) and end<=instant(request['not_after'])\n         and start>=instant(go['not_before']) and end<=instant(go['not_after']),'INNER_WINDOW')\n",""))
add('D03_inner_hash_chain_left_to_the_source','d',("    need(authority.get('request_sha256')==sha(blobs['request']) and go.get('request_sha256')==sha(blobs['request'])\n         and go.get('authority_sha256')==sha(blobs['authority']) and go.get('payload_sha256')==sha(blobs['source'])\n         and request.get('payload_sha256')==sha(blobs['source']),'INNER_BINDINGS')\n",""))
add('D04_budget_pair_not_required','d',("    need(config['watchdog_seconds']==80 and request.get('max_seconds')==60,'PREFLIGHT_BUDGET')\n",""))
add('D05_latest_start_not_bound_to_the_watchdog','d',("    need(start<=latest_start==end-timedelta(seconds=seconds),'LATEST_START_BINDING')\n","    need(start<=latest_start,'LATEST_START_BINDING')\n"))
add('D06_resume_does_not_read_the_claim','d',("            need(read(str(attempt_path.parent/claim_name),sha(claim_raw))==claim_raw,'GO_CLAIM_CHANGED')\n",""))
add('D07_intent_not_compared_with_the_expected_one','d',("        need(intent==expected_intent and start<=instant(intent['started_at'])","        need(start<=instant(intent['started_at'])"))
add('D08_no_spawn_marker_before_the_transport','d',("        write('spawn.claim',canonical({'publication_sha256':publication_sha256,'intent_sha256':sha(intent_raw)}))\n",""))
add('D09_publication_not_bound_to_the_go','d',(" and proof.get('go_sha256')==sha(blobs['go'])\n","\n"))
add('D10_receipt_not_bound_to_the_payload','d',("and receipt.get('go_sha256')==sha(blobs['go']) and receipt.get('payload_sha256')==sha(blobs['source']),'REMOTE_RECEIPT_BINDINGS')","and receipt.get('go_sha256')==sha(blobs['go']),'REMOTE_RECEIPT_BINDINGS')"))
add('D11_partial_receipts_not_bound','d',("            if result['status'] in ('KNOWN_COMPLETE','KNOWN_PARTIAL'):","            if result['status'] in ('KNOWN_COMPLETE',):"))
add('D12_command_pin_left_to_the_transport','d',("    argv=command(config);need(transport_once.command_pin(argv)==config['command_sha256'],'COMMAND_PIN')\n","    argv=command(config)\n"))
add('D13_key_and_known_hosts_not_read_before_the_claim','d',("    for name in ('ssh_key','known_hosts'):read(config[name]['path'],config[name]['sha256'],65536);gate()\n    attempt_path=","    attempt_path="))
add('D14_publication_owner_not_compared','d',("             and proof.get('owner')==config['owner'] and type(proof.get('publication_ref')) is str","             and type(proof.get('publication_ref')) is str"))
add('D15_config_single_use_flag_not_required','d',("         and config.get('single_use') is True and config.get('retry') is False,'DISPATCH_UNBOUND')","         ,'DISPATCH_UNBOUND')"))
add('D16_request_window_may_be_narrower_than_the_config','d',("    need(start>=instant(request['not_before']) and end<=instant(request['not_after'])\n","    need(True\n"))
# ---- launcher
add('L01_source_pin_not_checked_on_stdin','l',("    if hashlib.sha256(raw['source']).hexdigest()!=PINS['payload']:\n        raise ValueError('STDIN_SOURCE_PIN')","    if False:\n        raise ValueError('STDIN_SOURCE_PIN')"))
add('L02_build_does_not_compare_the_pins','l',("    if any(hashlib.sha256(v).hexdigest()!=pins[k] for v,k in zip(values,('payload','request','authority','go'))):\n        raise ValueError('BUILD_PIN')","    if False:\n        raise ValueError('BUILD_PIN')"))

# Survivors that cannot change any result of this operation, each with its reason. Any other survivor fails the run.
# The reviewer named seven; five of them are killed now (F07, F09, F11, F12 and the core's T08 as X01: tests/test_effects_guards.py).
EQUIVALENT={
 'F08_no_gate_before_the_temporary_is_looked_at_again':
     'the gate that is removed stands between two other looks at the clock with nothing but one lstat between them: directory.verify() ends with a gate '
     'and mutate() begins with one before the link. An expiry at that instant is reported with the same code and the same ledger state by the next gate; '
     'the only difference is one read that is still made',
 'O07_receipt_reports_the_signed_hash_as_observed':
     'installed is built only when the readback passed, and the readback requires the bytes read to equal the signed bytes: in a complete receipt '
     'sha256_observed and sha256_signed are the same value',
}
