"""Simulated HTTP, files and clocks only: never use a host or real GitHub write."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("workflow_recovery", ROOT / "scripts/c3po_workflow_schedule_recovery.py")
assert SPEC and SPEC.loader
R = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = R
SPEC.loader.exec_module(R)
SHA = "a" * 40


@pytest.fixture(autouse=True)
def no_real_api(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Real HTTP must never be used by these tests")
    monkeypatch.setattr(R, "build_opener", refuse)
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "CREDENTIALS_DIRECTORY"):
        monkeypatch.delenv(name, raising=False)


def slot(workflow=R.OPS, value="2026-10-23T06:30:00Z"):
    return R.validate_slot(workflow, value)


def run(s, ident=1, *, title=None, event="schedule", status="completed", at=None, sha=SHA):
    return {"id": ident, "path": f".github/workflows/{s.workflow}", "head_branch": "main", "head_sha": sha,
            "created_at": at or s.value, "display_title": title or "Scheduled run", "event": event,
            "status": status, "conclusion": "success"}


class Fake:
    def __init__(self, s):
        self.slot = s
        self.runs = []
        self.comments = []
        self.writes = []
        self.active = True
        self.dispatch_timeout = False
        self.notice_timeout = False
        self.appear = True
        self.after_read = None
        self.run_reads = 0

    def request(self, path, method="GET", body=None):
        if method == "GET":
            return {"sha": SHA} if path == "/commits/main" else {"state": "active" if self.active else "disabled_manually"}
        self.writes.append((path, body))
        if path.endswith("/dispatches"):
            if self.appear:
                self.runs.append(run(self.slot, 100, title=f"Recovered {self.slot.tag}", event="workflow_dispatch",
                                     at=R.stamp(self.slot.at + R.MIN_AGE)))
            if self.dispatch_timeout:
                raise TimeoutError("Private HTTP body must not print")
            return None
        comment = {"id": 200, "body": body["body"]}
        self.comments.append(comment)
        if self.notice_timeout:
            raise TimeoutError("Private HTTP body must not print")
        return comment

    def pages(self, path, key=None):
        if "/runs?" in path:
            self.run_reads += 1
            if self.after_read:
                self.after_read(self)
            return list(self.runs)
        return list(self.comments)


def once(monkeypatch, tmp_path, s=None, fake=None, *, act=True):
    s = s or slot()
    fake = fake or Fake(s)
    monkeypatch.setattr(R, "slots", lambda now: [s])
    ledger = R.Ledger(tmp_path / "ledger.json")
    result = R.recover(fake, ledger, s.at + R.MIN_AGE, act=act, sleep=lambda _: None)
    return fake, ledger, result


def test_slots_grace_and_daily_weekday_weekend_contracts():
    s = slot()
    assert s not in R.slots(s.at + R.timedelta(minutes=19, seconds=59))
    assert s in R.slots(s.at + R.MIN_AGE)
    assert s in R.slots(s.at + R.MAX_AGE)
    assert s not in R.slots(s.at + R.MAX_AGE + R.timedelta(seconds=1))
    saturday = R.instant("2026-10-24T11:55:00Z")
    due = R.slots(saturday)
    assert any(x.workflow == R.OPS and x.value == "2026-10-24T11:30:00Z" for x in due)
    assert not any(x.workflow == R.EXPORT for x in due)
    assert [x.value for x in due if x.workflow == R.PIT] == ["2026-10-24T11:13:00Z"]
    monday = R.slots(R.instant("2026-10-26T11:25:00Z"))
    export = next(x for x in monday if x.workflow == R.EXPORT)
    assert export.inputs == {"recovery_slot": "2026-10-26T11:00:00Z", "night": ""}
    # XNYS resolution remains in the existing producer, not a host approximation.


def test_pit_latest_eligible_only_no_backlog_and_utc_dst():
    for moment in ("2026-10-24T12:03:00Z", "2026-11-02T12:03:00Z"):
        ticks = [x for x in R.slots(R.instant(moment)) if x.workflow == R.PIT]
        assert len(ticks) == 1 and ticks[0].value.endswith("11:43:00Z")
        assert ticks[0].inputs["dry_run"] == "false"


@pytest.mark.parametrize("workflow,value", [(R.OPS, "2026-10-23T06:31:00Z"), (R.EXPORT, "2026-10-24T11:00:00Z"),
                                          (R.PIT, "2026-10-23T06:30:00Z"), (R.PIT, "2026-10-23T06:13:00+00:00"),
                                          ("other.yml", "2026-10-23T06:13:00Z")])
def test_bad_slots_are_refused(workflow, value):
    with pytest.raises(R.RecoveryError):
        R.validate_slot(workflow, value)


def test_missed_slot_recovers_once_with_run_and_get_confirmed_receipt(monkeypatch, tmp_path):
    fake, ledger, result = once(monkeypatch, tmp_path)
    assert result == {"covered": 0, "planned": 0, "confirmed": 1, "errors": 0}
    assert fake.writes[0] == (f"/actions/workflows/{R.OPS}/dispatches", {"ref": "main", "inputs": slot().inputs})
    assert len(fake.writes) == 2 and fake.writes[1][0] == "/issues/429/comments"
    assert "run 100" in fake.comments[0]["body"] and "resultado do workflow" in fake.comments[0]["body"]
    assert ledger.entries[slot().key]["state"] == "complete"
    assert (tmp_path / "ledger.json").stat().st_mode & 0o777 == 0o600
    _, _, again = once(monkeypatch, tmp_path, fake=fake)
    assert again["covered"] == 1 and len(fake.writes) == 2


@pytest.mark.parametrize("status", ["completed", "queued", "in_progress", "waiting", "requested", "pending"])
def test_existing_run_including_failure_or_approval_is_not_retried(monkeypatch, tmp_path, status):
    s = slot()
    fake = Fake(s)
    fake.runs = [{**run(s, status=status), "conclusion": "failure"}]
    _, _, result = once(monkeypatch, tmp_path, s, fake)
    assert result["covered"] == 1 and fake.writes == []


def test_plan_and_explicit_disabled_workflow_never_post(monkeypatch, tmp_path):
    fake, ledger, result = once(monkeypatch, tmp_path, act=False)
    assert result["planned"] == 1 and fake.writes == [] and ledger.entries == {}
    fake.active = False
    _, _, result = once(monkeypatch, tmp_path, fake=fake)
    assert result["errors"] == 1 and fake.writes == []


def test_recheck_catches_late_schedule_before_post(monkeypatch, tmp_path):
    s = slot()
    fake = Fake(s)
    def late(f):
        if f.run_reads == 2:
            f.runs.append(run(s, status="queued"))
    fake.after_read = late
    _, _, result = once(monkeypatch, tmp_path, s, fake)
    assert result["covered"] == 1 and fake.writes == []


def test_recheck_uses_fresh_clock_for_run_completed_after_cycle_start(monkeypatch, tmp_path):
    s = slot()
    fake = Fake(s)
    initial = s.at + R.MIN_AGE
    live = [initial]
    def late(f):
        if f.run_reads == 2:
            live[0] = initial + R.timedelta(minutes=2)
            f.runs.append(run(s, at=R.stamp(initial + R.timedelta(minutes=1))))
    fake.after_read = late
    monkeypatch.setattr(R, "slots", lambda now: [s])
    result = R.recover(fake, R.Ledger(tmp_path / "ledger.json"), initial, act=True,
                       sleep=lambda _: None, clock=lambda: live[0])
    assert result["covered"] == 1 and fake.writes == []


def test_slot_aging_out_during_reads_and_main_moving_refuse_post(monkeypatch, tmp_path):
    s = slot()
    fake = Fake(s)
    monkeypatch.setattr(R, "slots", lambda now: [s])
    result = R.recover(fake, R.Ledger(tmp_path / "ledger.json"), s.at + R.MIN_AGE, act=True,
                       clock=lambda: s.at + R.MAX_AGE + R.timedelta(seconds=1))
    assert result["covered"] == 1 and fake.writes == []
    original = fake.request
    reads = [0]
    def moved(path, method="GET", body=None):
        if path == "/commits/main":
            reads[0] += 1
            return {"sha": SHA if reads[0] == 1 else "b" * 40}
        return original(path, method, body)
    fake.request = moved
    _, _, result = once(monkeypatch, tmp_path, s, fake)
    assert result["errors"] == 1 and fake.writes == []


def test_schedule_after_post_does_not_masquerade_as_recovery(monkeypatch, tmp_path):
    s = slot()
    fake = Fake(s)
    def late(f):
        if f.run_reads == 3:
            f.runs.append(run(s, 101, status="queued"))
    fake.after_read = late
    _, ledger, result = once(monkeypatch, tmp_path, s, fake)
    assert result["confirmed"] == 1 and ledger.entries[s.key]["run_id"] == 100
    assert len([call for call in fake.writes if call[0].endswith("/dispatches")]) == 1


def test_intent_is_on_disk_before_every_post(monkeypatch, tmp_path):
    s = slot()
    fake = Fake(s)
    original = fake.request
    def checked(path, method="GET", body=None):
        if method == "POST":
            entry = json.loads((tmp_path / "ledger.json").read_text())["entries"][s.key]
            assert entry["state"] == ("dispatch_intent" if path.endswith("/dispatches") else "notice_intent")
        return original(path, method, body)
    fake.request = checked
    once(monkeypatch, tmp_path, s, fake)


def test_ledger_write_failure_prevents_dispatch(monkeypatch, tmp_path):
    def refuse(*args):
        raise OSError("disk unavailable")
    monkeypatch.setattr(R, "atomic_write", refuse)
    fake, _, result = once(monkeypatch, tmp_path)
    assert result["errors"] == 1 and fake.writes == []


def test_hold_created_during_reads_prevents_post(monkeypatch, tmp_path):
    s = slot()
    fake = Fake(s)
    held = [False]
    def hold(f):
        if f.run_reads == 2:
            held[0] = True
    fake.after_read = hold
    monkeypatch.setattr(R, "slots", lambda now: [s])
    result = R.recover(fake, R.Ledger(tmp_path / "ledger.json"), s.at + R.MIN_AGE, act=True,
                       may_write=lambda: not held[0], sleep=lambda _: None)
    assert result["covered"] == 1 and fake.writes == []
    assert not (tmp_path / "ledger.json").exists()


def test_hold_between_intent_and_dispatch_is_known_unsent_and_can_resume(monkeypatch, tmp_path):
    s = slot()
    fake = Fake(s)
    held = [False]
    original = R.atomic_write
    def write_then_hold(path, data):
        original(path, data)
        if data["entries"][s.key]["state"] == "dispatch_intent":
            held[0] = True
    monkeypatch.setattr(R, "atomic_write", write_then_hold)
    monkeypatch.setattr(R, "slots", lambda now: [s])
    ledger = R.Ledger(tmp_path / "ledger.json")
    R.recover(fake, ledger, s.at + R.MIN_AGE, act=True, may_write=lambda: not held[0], sleep=lambda _: None)
    assert ledger.entries[s.key]["state"] == "dispatch_held" and fake.writes == []
    monkeypatch.setattr(R, "atomic_write", original)
    _, ledger, result = once(monkeypatch, tmp_path, s, fake)
    assert result["confirmed"] == 1 and ledger.entries[s.key]["state"] == "complete" and len(fake.writes) == 2


def test_slot_aging_out_during_intent_fsync_is_never_dispatched(monkeypatch, tmp_path):
    s = slot()
    fake = Fake(s)
    live = [s.at + R.MIN_AGE]
    original = R.atomic_write
    def slow_fsync(path, data):
        original(path, data)
        if data["entries"][s.key]["state"] == "dispatch_intent":
            live[0] = s.at + R.MAX_AGE + R.timedelta(seconds=1)
    monkeypatch.setattr(R, "atomic_write", slow_fsync)
    monkeypatch.setattr(R, "slots", lambda now: [s])
    ledger = R.Ledger(tmp_path / "ledger.json")
    result = R.recover(fake, ledger, live[0], act=True, clock=lambda: live[0], sleep=lambda _: None)
    assert result["covered"] == 1 and ledger.entries[s.key]["state"] == "skipped" and fake.writes == []
    _, ledger, result = once(monkeypatch, tmp_path, s, fake)
    assert result["covered"] == 1 and fake.writes == []  # durable positive non-attempt


def test_hold_before_notice_and_after_notice_intent_never_posts_until_released(monkeypatch, tmp_path):
    s = slot()
    fake = Fake(s)
    held = [False]
    original = R.atomic_write
    def write_then_hold(path, data):
        original(path, data)
        if data["entries"][s.key]["state"] == "notice_intent":
            held[0] = True
    monkeypatch.setattr(R, "atomic_write", write_then_hold)
    monkeypatch.setattr(R, "slots", lambda now: [s])
    ledger = R.Ledger(tmp_path / "ledger.json")
    R.recover(fake, ledger, s.at + R.MIN_AGE, act=True, may_write=lambda: not held[0], sleep=lambda _: None)
    assert ledger.entries[s.key]["state"] == "run_confirmed" and len(fake.writes) == 1
    R.recover(fake, ledger, s.at + R.MIN_AGE, act=True, may_write=lambda: False, sleep=lambda _: None)
    assert ledger.entries[s.key]["state"] == "run_confirmed" and len(fake.writes) == 1
    monkeypatch.setattr(R, "atomic_write", original)
    _, ledger, result = once(monkeypatch, tmp_path, s, fake)
    assert result["confirmed"] == 1 and ledger.entries[s.key]["state"] == "complete" and len(fake.writes) == 2


def test_lost_dispatch_response_reconciles_without_reposting(monkeypatch, tmp_path):
    s = slot()
    fake = Fake(s)
    fake.dispatch_timeout = True
    _, _, result = once(monkeypatch, tmp_path, s, fake)
    assert result["confirmed"] == 1 and len(fake.writes) == 2


def test_unknown_dispatch_persists_across_restart_and_never_retries(monkeypatch, tmp_path):
    s = slot()
    fake = Fake(s)
    fake.appear = False
    fake.dispatch_timeout = True
    _, ledger, result = once(monkeypatch, tmp_path, s, fake)
    assert result["errors"] == 1 and ledger.entries[s.key]["state"] == "dispatch_unknown"
    _, _, again = once(monkeypatch, tmp_path, s, fake)
    assert again["errors"] == 1 and len(fake.writes) == 1
    fake.runs.append(run(s, 100, title=f"Recovered {s.tag}", event="workflow_dispatch", at=R.stamp(s.at + R.MIN_AGE)))
    _, _, recovered = once(monkeypatch, tmp_path, s, fake)
    assert recovered["confirmed"] == 1 and len(fake.writes) == 2  # receipt only


def test_main_sha_change_after_post_stays_unknown(monkeypatch, tmp_path):
    s = slot()
    fake = Fake(s)
    def moved(f):
        for row in f.runs:
            row["head_sha"] = "b" * 40
    fake.after_read = moved
    _, ledger, result = once(monkeypatch, tmp_path, s, fake)
    assert result["errors"] == 1 and ledger.entries[s.key]["state"] == "dispatch_unknown"
    assert len(fake.writes) == 1


def test_lost_notice_response_is_reconciled_not_duplicated(monkeypatch, tmp_path):
    s = slot()
    fake = Fake(s)
    fake.notice_timeout = True
    _, ledger, result = once(monkeypatch, tmp_path, s, fake)
    assert result["errors"] == 1 and ledger.entries[s.key]["state"] == "notice_unknown"
    _, ledger, result = once(monkeypatch, tmp_path, s, fake)
    assert result["errors"] == 0 and ledger.entries[s.key]["state"] == "complete"
    assert len(fake.writes) == 2


def test_unobserved_notice_outcome_never_reposts(monkeypatch, tmp_path):
    s = slot()
    fake = Fake(s)
    fake.notice_timeout = True
    once(monkeypatch, tmp_path, s, fake)
    fake.comments = []
    _, ledger, result = once(monkeypatch, tmp_path, s, fake)
    assert result["errors"] == 1 and ledger.entries[s.key]["state"] == "notice_unknown" and len(fake.writes) == 2


def test_dry_run_does_not_cover_acting_tick_and_inputs_stay_fixed(monkeypatch, tmp_path):
    s = slot(R.PIT, "2026-10-23T06:13:00Z")
    fake = Fake(s)
    fake.runs = [run(s, title="Valuation PIT grid autopilot — dry-run", event="workflow_dispatch")]
    once(monkeypatch, tmp_path, s, fake)
    assert fake.writes[0][1]["inputs"] == {"dry_run": "false", "recovery_slot": s.value}


def test_unknown_manual_export_night_is_not_guessed(monkeypatch, tmp_path):
    s = slot(R.EXPORT, "2026-10-23T11:00:00Z")
    fake = Fake(s)
    fake.runs = [run(s, title="Decisor verdict export 2026-10-01", event="workflow_dispatch")]
    _, _, result = once(monkeypatch, tmp_path, s, fake)
    assert result["errors"] == 1 and fake.writes == []


class Pages(R.GitHub):
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, path, **kwargs):
        self.calls.append(path)
        return self.responses.pop(0)


def test_pagination_reads_later_page_and_rejects_partial_or_untrusted():
    path = f"/actions/workflows/{R.OPS}/runs"
    link = f'<https://api.github.com/repos/{R.REPO}{path}?page=2&per_page=100>; rel="next"'
    gh = Pages([({"total_count": 2, "workflow_runs": [{"id": 1}]}, link),
                ({"total_count": 2, "workflow_runs": [{"id": 2}]}, "")])
    assert [r["id"] for r in gh.pages(path, "workflow_runs")] == [1, 2] and len(gh.calls) == 2
    for response in [({"total_count": 2, "workflow_runs": []}, ""),
                     ({"total_count": 1000, "workflow_runs": []}, ""),
                     ({"total_count": 1, "workflow_runs": []}, '<https://evil.test/x>; rel="next"'),
                     ({"total_count": 0, "workflow_runs": []}, "unreadable")]:
        with pytest.raises(R.RecoveryError):
            Pages([response]).pages(path, "workflow_runs")


def test_failed_or_malformed_listing_never_posts(monkeypatch, tmp_path):
    s = slot()
    fake = Fake(s)
    fake.runs = [{**run(s), "created_at": "yesterday"}]
    _, _, result = once(monkeypatch, tmp_path, s, fake)
    assert result["errors"] == 1 and fake.writes == []
    fake.runs = [{**run(s), "head_branch": "untrusted"}]
    _, _, result = once(monkeypatch, tmp_path, s, fake)
    assert result["errors"] == 1 and fake.writes == []


def test_invalid_or_symlink_ledger_fails_closed(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text('{"schema":"wrong","entries":{}}')
    with pytest.raises(R.RecoveryError):
        R.Ledger(path)
    path.unlink()
    target = tmp_path / "target"
    target.write_text("{}")
    path.symlink_to(target)
    with pytest.raises(R.RecoveryError):
        R.Ledger(path)


def test_workflow_contracts_do_not_expand_permissions_or_grid_inputs():
    for name in R.WORKFLOWS:
        doc = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
        trigger = doc.get("on", doc.get(True))
        assert "recovery_slot" in trigger["workflow_dispatch"]["inputs"]
        assert "[recovery:{0}]" in doc["run-name"]
        assert doc["permissions"] == {"contents": "read"}
        assert doc["concurrency"]["cancel-in-progress"] is False
        assert any(step.get("name") == "Validate the optional recovery slot" for job in doc["jobs"].values() for step in job["steps"])
    pit = yaml.safe_load((ROOT / ".github/workflows" / R.PIT).read_text())
    assert set(pit.get("on", pit.get(True))["workflow_dispatch"]["inputs"]) == {"dry_run", "recovery_slot"}
    assert 'vars.C3PO_PIT_GRID_AUTOPILOT' in pit["jobs"]["tick"]["if"]
    source = (ROOT / ".github/scripts/valuation_pit_grid_autopilot.py").read_text()
    assert 'args.ref == "refs/heads/main"' in source and "deploys_in_progress(deploys)" in source


def test_validator_needs_no_credential_and_installer_is_separate():
    assert R.main(["--validate-slot", R.OPS, ""]) == 0
    assert R.main(["--validate-slot", R.OPS, "2026-10-23T06:30:00Z"]) == 0
    assert R.main(["--validate-slot", R.OPS, "invalid"]) == 2
    installer = (ROOT / "scripts/install-workflow-schedule-recovery.sh").read_text()
    assert "--install-only" in installer and "systemctl " not in installer
    assert "workflow-schedule-recovery" not in (ROOT / "scripts/install-security-daily.sh").read_text()
    assert "workflow-schedule-recovery" not in (ROOT / ".github/workflows/c3po-pipeline.yml").read_text()
    timer = (ROOT / "ops/systemd/c3po-workflow-schedule-recovery.timer").read_text()
    assert "*:03:00 UTC" in timer and "Persistent=true" in timer
    # Syntax only; never execute the installation script.
    assert subprocess.run(["bash", "-n", str(ROOT / "scripts/install-workflow-schedule-recovery.sh")], capture_output=True).returncode == 0


def test_host_installer_stages_only_against_filesystem_substitutes(tmp_path):
    project, local, etc, bindir = [tmp_path / name for name in ("project", "local", "etc", "bin")]
    (project / "scripts").mkdir(parents=True)
    (project / "ops/systemd").mkdir(parents=True)
    (etc / "systemd/system").mkdir(parents=True)
    bindir.mkdir()
    (project / ".deploy-version").write_text(SHA)
    shutil.copyfile(ROOT / "scripts/c3po_workflow_schedule_recovery.py", project / "scripts/c3po_workflow_schedule_recovery.py")
    for name in ("service", "timer"):
        source = ROOT / f"ops/systemd/c3po-workflow-schedule-recovery.{name}"
        shutil.copyfile(source, project / f"ops/systemd/{source.name}")
    shim = bindir / "install"
    shim.write_text("#!" + sys.executable + "\n" + '''import pathlib,shutil,sys
args=sys.argv[1:];out=[];directory=False;i=0
while i<len(args):
 if args[i] in ('-o','-g','-m'):i+=2;continue
 if args[i]=='-d':directory=True
 else:out.append(args[i])
 i+=1
if directory:
 for p in out:pathlib.Path(p).mkdir(parents=True,exist_ok=True)
else:
 target=pathlib.Path(out[-1])
 for p in out[:-1]:shutil.copyfile(p,target/pathlib.Path(p).name if target.is_dir() else target)
''')
    shim.chmod(0o755)
    verify = bindir / "systemd-analyze"
    verify.write_text("#!/bin/sh\nexit 0\n")
    verify.chmod(0o755)
    forbidden = bindir / "systemctl"
    forbidden.write_text("#!/bin/sh\necho 'unexpected activation' >&2\nexit 99\n")
    forbidden.chmod(0o755)
    script = (ROOT / "scripts/install-workflow-schedule-recovery.sh").read_text()
    script = script.replace("/opt/chief-of-staff-digital", str(project)).replace("/usr/local", str(local)).replace("/etc/", str(etc) + "/")
    env = {"PATH": str(bindir) + ":/usr/bin:/bin"}
    refused = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
    assert refused.returncode == 2 and not local.exists()
    staged = subprocess.run(["bash", "-c", script, "installer", "--install-only"], env=env, capture_output=True, text=True)
    assert staged.returncode == 0, staged.stderr
    assert (local / "lib/c3po-workflow-recovery/c3po_workflow_schedule_recovery.py").read_bytes() == (ROOT / "scripts/c3po_workflow_schedule_recovery.py").read_bytes()
    assert len(list((etc / "systemd/system").iterdir())) == 2


def test_separate_lock_prevents_a_second_cycle(monkeypatch, tmp_path):
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    credential = tmp_path / "credential"
    credential.write_text("test-only-not-a-credential")
    credential.chmod(0o600)
    with (state / "recovery.lock").open("a") as held:
        R.fcntl.flock(held, R.fcntl.LOCK_EX | R.fcntl.LOCK_NB)
        assert R.main(["--state-dir", str(state), "--token-file", str(credential)]) == 0
    assert not (state / "ledger.json").exists()
