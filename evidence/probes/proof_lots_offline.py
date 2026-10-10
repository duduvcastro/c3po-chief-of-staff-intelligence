"""PROOF_LOTS_OFFLINE (Fable v3.2 build, Darwin, no effect): builds the v3.2 Linux proof's UP lot (F-E grid from
plan_up) and DOWN lot (plan_down) with the proof's OWN functions on the physical epoch-04 layout (runtime stub), binds
them as the proof does (bind.lot / owner / bound, non-physical), then judges them in PHYSICAL mode as the installer
(validate_lot + plan_rows + cross-lot check) and physical_verdict do; DOWN also with the driver's open substitution."""
import json, os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
FAM = Path(sys.argv[1])
sys.path.insert(0, str(FAM / "tests")); sys.path.insert(0, str(FAM)); sys.path.insert(0, str(FAM / "lots"))
import kit
import linux_systemd_proof as proof
import build_specs as bs
rt, fx, inst, bind = kit.rt, kit.fx, kit.inst, kit.bind
out = {"schema": "L12HOST_V32_PROOF_LOTS_OFFLINE", "cases": {}}
starts = {"now": datetime.now(timezone.utc).replace(microsecond=0)}
# also two fixed instants: one whose UP chain crosses the HH:03:40 block, one in the 00:03:40-00:45:59 BRT block
starts["fixed_2026-10-09T23:58:00Z_(20:58_BRT)"] = datetime(2026, 10, 9, 23, 58, tzinfo=timezone.utc)
starts["fixed_2026-10-10T02:59:00Z_(23:59_BRT)"] = datetime(2026, 10, 10, 2, 59, tzinfo=timezone.utc)
for label, now in starts.items():
    env = kit.Env()
    try:
        layout = {"schema": rt.LAYOUT_SCHEMA, "root": rt.EPOCH04_L12_ROOT, "veto_dir": rt.EPOCH04_VETO_DIR,
                  "unit_prefix": "l12proof-", "unit_name_suffix": "-e04", "python": "/usr/bin/python3.12",
                  "binaries": {"docker": "/usr/local/lib/l12proof-120000/docker", "systemd_run": "/usr/bin/systemd-run",
                               "systemctl": "/usr/bin/systemctl"}, "docker_config": "/var/lib/l12proof-120000/docker-cli"}
        env.layout = layout
        env.layout_path = env.base / "layout-physical.json"
        env.layout_path.write_bytes(rt.canonical(layout))
        env.runtime_path = env.base / "runtime-stub.json"
        env.runtime_path.write_bytes(bs.runtime_stub(layout))
        env.now0, env.t_sign = now, kit.past_signature_instant(now)
        env.nb, env.na = env.t_sign + timedelta(minutes=2), now + timedelta(hours=3)
        env.secrets = Path(rt.EPOCH04_K9_ROOT + "/secrets"); env.env_file = env.secrets / "provider.env"
        env.tools, env.daydir = Path(rt.EPOCH04_K9_TOOLS), Path(rt.EPOCH04_K9_DAY)
        env.receipts = env.daydir / "receipts"
        host_day = env.mk("host-day-copy"); env.mk("host-day-copy/plans")
        orig = kit.Env.k9_plan
        def k9_plan(self, op, at, budget, **kw):          # the host copy goes to a temp dir (no /var/lib on the Mac)
            saved = self.daydir; self.daydir = host_day
            try:
                return orig(self, op, at, budget, **kw)
            finally:
                self.daydir = saved
        env.k9_plan = k9_plan.__get__(env)
        t0 = int(now.timestamp())
        times = proof.plan_up(t0)
        spec, ops = proof.up_spec(env, times)
        bound = env.signed_lot(spec)
        files, extra = inst.lot_stage(str(env.stage), "UP")
        fam = inst.family_core()
        case = {"up_slots": [rt.iso(proof.utc(t)) for t in times]}
        try:
            q, authority, owner = inst.validate_lot(files, extra, "UP", fam, True)
            rows = inst.plan_rows(authority, proof.utc(times[0]) - timedelta(seconds=200), rt.stamp(owner["signed_at"]))
            inst.cross_lot_check({"UP": (authority, q)})
            case["up_physical_install_validation"] = "ACCEPTED"
            case["up_tasks"] = [{"op": t["operation"], "not_before": t["not_before"], "not_after": t["not_after"],
                                 "budget": t["budget_seconds"], "slot": t["slots"][0]["at"]} for t in spec["tasks"]]
            case["up_plan_rows_margin_seconds_at_P1_minus_200s"] = [r["margin_seconds"] for r in rows]
        except rt.Hold as error:
            case["up_physical_install_validation"] = "REFUSED:" + str(error)
        down_plan = proof.plan_down(times[-1] + 30 + 2 + 60)
        reader, sup, _ = proof.proof_unit_rows(layout, layout["binaries"]["docker"], layout["docker_config"])
        down, opening, hold = proof.proof_down_spec(env, reader, sup, env.t_sign, "aa" * 32, "bb" * 32,
                                                    {"commit_result": "cc" * 32, "publish_launch": "dd" * 32}, down_plan)
        down_out = env.stage / "lot-DOWN"
        spec_path = env.base / "spec-DOWN.json"
        spec_path.write_text(json.dumps(down))
        bind.lot(str(spec_path), str(env.layout_path), str(env.runtime_path), kit.z(env.t_sign - timedelta(minutes=30)), str(down_out))
        bind.owner(str(down_out), kit.z(env.t_sign - timedelta(minutes=1)), kit.z(env.t_sign))
        bind.bound(str(down_out), kit.z(env.t_sign + timedelta(seconds=30)))
        case["down_instants"] = {k: rt.iso(proof.utc(v)) for k, v in down_plan.items()}
        case["down_physical_without_substitution"] = proof.physical_verdict(down_out)
        saved = rt.SESSION_OPEN_UTC
        rt.SESSION_OPEN_UTC = kit.z(opening)
        try:
            case["down_physical_with_open_substitution"] = proof.physical_verdict(down_out)
        finally:
            rt.SESSION_OPEN_UTC = saved
        m = proof.model(t0)
        case["model"] = {"timer_part_minutes": round((m["end"] - t0) / 60, 1), "hold_minus_reader_check": m["hold_minus_check"],
                         "r0_minus_negatives_end": m["r0_minus_negatives_end"]}
        out["cases"][label] = case
    finally:
        env.cleanup()
print(json.dumps(out, indent=1, sort_keys=True))
