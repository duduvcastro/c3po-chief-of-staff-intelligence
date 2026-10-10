"""v3.3f mutation checks (Fable, Mac, offline). Each mutant is ONE exact-text change of a v3.3f family file in a scratch
copy of the sealed family (never in the delivery); tests/test_v33f.py of that copy must then fail ("killed").
Synthetic only; nothing is pushed, installed or run on a host.

    python3 -I -B mutants_v33f.py <sealed family dir> <scratch parent> <python> > MUTANTS.json
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

MUTANTS = [
    ("runtime_k9_network_pin_removed", "l12host_runtime.py",
     'need(not physical or networks == K9_NETWORKS_EPOCH04, "K9_NETWORKS_NOT_DNET", kind)', "pass"),
    ("runtime_reader_network_pin_removed", "l12host_runtime.py",
     'need(variables["reader_network"] == READER_NETWORK_EPOCH04, "SESSION_READER_NETWORK_NOT_DNET", kind)', "pass"),
    ("runtime_supervisor_network_pin_removed", "l12host_runtime.py",
     'need(variables["supervisor_network"] == SUPERVISOR_NETWORK_EPOCH04, "SUPERVISOR_NETWORK_NOT_DNET", kind)', "pass"),
    ("runtime_one_network_for_both_units", "l12host_runtime.py",
     '+ ["--network", supervisor_network] + UNIT_DOCKER_HARDENING', '+ ["--network", reader_network] + UNIT_DOCKER_HARDENING'),
    ("runtime_real_check_not_called", "l12host_runtime.py",
     "        validate_k9_real(a, files, files_raw, q[\"lane\"], kind)\n", "        pass\n"),
    ("runtime_real_fixed_files_not_required", "l12host_runtime.py",
     'need(files_raw is not None and all(rel in files for rel in K9_REAL_FIXED_FILES), "K9_REAL_FILE_ABSENT", kind)',
     'need(files_raw is not None, "K9_REAL_FILE_ABSENT", kind)'),
    ("runtime_registry_seal_unchecked", "l12host_runtime.py",
     'need(source["APPROVED_REGISTRY_PINS"].get(a["lot"]) == sha(policy_raw), "K9_REAL_REGISTRY_NOT_SEALED_IN_THE_VERIFIER", kind)',
     "pass"),
    ("runtime_original_registered_sha_unchecked", "l12host_runtime.py",
     'need(all(files[r["file"]] == r["sha256"] for r in originals.values()), "K9_REAL_ORIGINAL_NOT_THE_REGISTERED_ONE", kind)',
     "pass"),
    ("runtime_registry_operations_unchecked", "l12host_runtime.py",
     'for op, rel in k9["plans"].items()), "K9_REAL_REGISTRY_OPERATION_NOT_SIGNED", kind)',
     'for op, rel in k9["plans"].items()) or True, "K9_REAL_REGISTRY_OPERATION_NOT_SIGNED", kind)'),
    ("runtime_callbacks_unchecked", "l12host_runtime.py",
     'for name, identity in K9_REAL_CALLBACKS.items()), "K9_REAL_CALLBACK_NOT_THE_VERIFIER", kind)',
     'for name, identity in K9_REAL_CALLBACKS.items()) or True, "K9_REAL_CALLBACK_NOT_THE_VERIFIER", kind)'),
    ("builder_supervisor_takes_the_reader_network", "lots/build_specs.py",
     '"@NETWORK@": UNIT_NETWORKS["supervisor"]', '"@NETWORK@": UNIT_NETWORKS["reader"]'),
    ("builder_writer_accepts_any_networks", "lots/build_specs.py",
     '    refuse(networks == NETWORKS, "REAL_NETWORKS_NOT_DNET", [c for c in NETWORK_CLASSES if networks[c] != NETWORKS[c]][:1])\n    k9raw',
     "    k9raw"),
    ("builder_verifier_sha_flag_unchecked", "lots/build_specs.py",
     'refuse(rt.sha(raw["verifier"]) == real_k9["verifier_sha256"], "REAL_K9_VERIFIER_NOT_THE_PINNED_ONE")', "pass"),
    ("builder_policy_seal_unchecked", "lots/build_specs.py",
     'refuse(source["APPROVED_REGISTRY_PINS"].get(lot) == rt.sha(raw["policy"]), "REAL_K9_POLICY_NOT_SEALED_IN_THE_VERIFIER")',
     "pass"),
    ("builder_effect_rows_unchecked", "lots/build_specs.py",
     '"REAL_K9_POLICY_EFFECT_NOT_THE_DERIVED_ROW", op)', '"REAL_K9_POLICY_EFFECT_NOT_THE_DERIVED_ROW", op) if False else None'),
    ("builder_publication_go_unchecked", "lots/build_specs.py",
     '"REAL_K9_PUBLICATION_NOT_THE_GO_ONE")', '"REAL_K9_PUBLICATION_NOT_THE_GO_ONE") if False else None'),
    ("builder_act_b_pin_unchecked", "lots/build_specs.py",
     'and pins["act_b"] == constants.get("act_b_sha256"), ', ", "),
    ("builder_f1_shared_files_unchecked", "lots/build_specs.py",
     "        refuse(up[rel] == extra[rel], code)\n", "        pass\n"),
    ("builder_f1_policy_beyond_lot_unchecked", "lots/build_specs.py",
     'and dict(up_policy, lot=None) == dict(down_policy, lot=None), "REAL_DOWN_K9_POLICY_NOT_THE_UP_ONE_BUT_LOT")',
     ', "REAL_DOWN_K9_POLICY_NOT_THE_UP_ONE_BUT_LOT")'),
    ("builder_kill_record_not_rechecked", "lots/build_specs.py",
     'refuse(read_file(target / KILL_RECORD) == kill, "REAL_KILL_RECORD_NOT_THE_DERIVED_ONE")', "pass"),
    ("builder_kill_capture_slack_applied", "lots/build_specs.py",
     '"row": convert(step, secrets_root, networks, slack=op != "capture_launch")}',
     '"row": convert(step, secrets_root, networks, slack=True)}'),
    ("builder_originals_count_unchecked", "lots/build_specs.py",
     'refuse(set(raw["originals"]) == set(pins), "REAL_K9_ORIGINALS_NOT_THE_VERIFIER_ONES",',
     'refuse(set(raw["originals"]) <= set(pins) or True, "REAL_K9_ORIGINALS_NOT_THE_VERIFIER_ONES",'),
    ("question_unit_networks_removed", "bind_l12host.py",
     'lines += ["  REDES DAS UNIDADES: leitor %s, supervisor %s" % (nets[0], nets[1])]', "pass"),
    ("proof_up_lot_without_v33f", "linux_systemd_proof.py",
     "    return up_v33f(spec, env.assets), ops\n", "    return spec, ops\n"),
    ("proof_reader_keeps_c3po_default", "linux_systemd_proof.py",
     '"@NETWORK@": rt.READER_NETWORK_EPOCH04,', '"@NETWORK@": "c3po_default",'),
]


def main(family, scratch, python):
    family, scratch = Path(family), Path(scratch)
    rows = []
    for name, rel, old, new in MUTANTS:
        work = scratch / ("mutant-" + name)
        if work.exists():
            shutil.rmtree(str(work))
        shutil.copytree(str(family), str(work / "l12host"))
        target = work / "l12host" / rel
        text = target.read_text("utf-8")
        found = text.count(old)
        row = {"mutant": name, "file": rel, "occurrences": found}
        if found != 1:
            row.update(killed=None, note="PATTERN_NOT_UNIQUE")
            rows.append(row)
            continue
        target.write_text(text.replace(old, new), "utf-8")
        row["mutated_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        compiled = subprocess.run([python, "-I", "-S", "-B", "-c", "import ast,sys; ast.parse(open(sys.argv[1]).read())",
                                   str(target)], capture_output=True, timeout=60)
        row["mutant_parses"] = compiled.returncode == 0
        proc = subprocess.run([python, "-I", "-S", "-B", str(work / "l12host" / "tests" / "test_v33f.py")],
                              capture_output=True, timeout=900)
        try:
            summary = json.loads(proc.stdout.decode().strip().splitlines()[-1])
        except (ValueError, IndexError):
            summary = {}
        failing = sorted({line.split(" (")[0] for line in proc.stderr.decode().splitlines()
                          if line.startswith(("FAIL: ", "ERROR: "))})
        row.update(rc=proc.returncode, tests=summary.get("tests"), failures=summary.get("failures"),
                   errors=summary.get("errors"), killed=proc.returncode != 0, failing=failing[:6])
        rows.append(row)
        shutil.rmtree(str(work))
    out = {"schema": "L12HOST_V33F_MUTANTS", "python": python, "mutants": len(rows),
           "killed": sum(1 for r in rows if r["killed"]), "rows": rows}
    print(json.dumps(out, sort_keys=True, indent=1))
    return 0 if all(r["killed"] and r.get("mutant_parses") for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:4]))
