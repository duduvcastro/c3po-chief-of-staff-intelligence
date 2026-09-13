from __future__ import annotations
import importlib
import json
import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
reboot = importlib.import_module('c3po_security_reboot')
watchdog = importlib.import_module('c3po_security_watchdog')
daily = importlib.import_module('c3po_security_daily')

@pytest.fixture
def host(tmp_path, monkeypatch):
    (tmp_path / 'runtime/security').mkdir(parents=True)
    (tmp_path / '.deploy-version').write_text('a' * 40)
    for name in ('BOOT_ID', 'REQUIRED', 'MARKER'):
        monkeypatch.setattr(reboot, name, tmp_path / name)
    reboot.BOOT_ID.write_text('old-boot')
    reboot.REQUIRED.touch()
    gate = tmp_path / 'runtime/security/maintenance'
    gate.mkdir()
    for name in ('admission.lock', 'work.lock'):
        (gate / name).touch(mode=0o644)
    monkeypatch.setattr(reboot, 'admission_coverage', lambda *args: True)
    class Pause:
        keep = False
        def __init__(self, *args): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def idle(self): return True
    monkeypatch.setattr(reboot, 'SchedulingPause', Pause)
    monkeypatch.setattr(reboot, 'DPKG_LOCKS', (tmp_path / 'dpkg1', tmp_path / 'dpkg2'))
    for path in reboot.DPKG_LOCKS:
        path.touch()
    return tmp_path

class GH:
    busy = False
    def pages(self, *args):
        return [1] if self.busy else []

def runner(calls, *, ingestion='0', active='0'):
    def run(args):
        calls.append(args)
        if args[:2] == ['systemctl', 'show']:
            return 'inactive'
        if args[0:2] == ['docker', 'compose']:
            return 'db-id'
        if args[0:2] == ['docker', 'inspect']:
            return json.dumps([{'Id': 'id', 'Name': '/db', 'Image': 'sha256:image', 'State': {'Running': True, 'StartedAt': '2026-09-11T16:48:21Z'}}])
        if 'psql' in args:
            return ingestion if 'ingestion_runs' in args[-1] else active
        return ''
    return run

def request(host, gh=None, **overrides):
    calls = []
    options = dict(command=runner(calls), healthy=lambda _: True, write=daily.write_report, allowed=lambda: True)
    options.update(overrides)
    result = reboot.request_reboot(host, gh or GH(), {'automatic_reboot': True}, datetime.now(timezone.utc), **options)
    return result, calls

def test_reboot_receipt_is_durable_before_command_and_no_loop(host):
    calls = []
    run = runner(calls)
    def observed(args):
        if args[:2] == ['systemctl', 'reboot']:
            assert reboot.MARKER.exists()
            assert json.loads((host / 'runtime/security' / reboot.STATE).read_text())['state'] == 'requested'
        return run(args)
    assert request(host, command=observed)[0] == 'requested'
    assert request(host)[0] == 'cooldown'
    assert sum(c[:2] == ['systemctl', 'reboot'] for c in calls) == 1

@pytest.mark.parametrize('kind', ['pipeline', 'database', 'ingestion', 'late_hold', 'packages'])
def test_busy_or_hold_never_reboots(host, kind):
    gh = GH()
    gh.busy = kind == 'pipeline'
    calls = []
    run = runner(calls, ingestion='1' if kind == 'ingestion' else '0', active='1' if kind == 'database' else '0')
    if kind == 'packages':
        original = run
        run = lambda a: 'active' if a[:2] == ['systemctl', 'show'] else original(a)
    answers = iter([True, False]) if kind == 'late_hold' else iter([True, True])
    result, _ = request(host, gh, command=run, allowed=lambda: next(answers))
    assert result != 'requested' and not reboot.MARKER.exists()
    assert not any(c[:2] == ['systemctl', 'reboot'] for c in calls)

def test_failed_reboot_command_removes_marker_and_records_failure(host):
    run = runner([])
    def failed(args):
        if args[:2] == ['systemctl', 'reboot']:
            raise RuntimeError('sanitized')
        return run(args)
    with pytest.raises(RuntimeError):
        request(host, command=failed)
    assert not reboot.MARKER.exists()
    assert json.loads((host / 'runtime/security' / reboot.STATE).read_text())['state'] == 'failed'

def test_actual_boot_and_application_health_required_for_success(host):
    assert request(host)[0] == 'requested'
    reboot.BOOT_ID.write_text('new-boot')
    def broken(_):
        raise ConnectionError('not yet ready')
    assert reboot.boot_receipt(host, daily.write_report, broken, datetime.now(timezone.utc))['state'] == 'verifying'
    assert reboot.boot_receipt(host, daily.write_report, lambda _: True, datetime.now(timezone.utc))['state'] == 'verifying'
    reboot.REQUIRED.unlink()
    assert reboot.boot_receipt(host, daily.write_report, lambda _: True, datetime.now(timezone.utc))['state'] == 'verified'

def test_reboot_not_occurred_is_failed_after_fifteen_minutes(host):
    request(host)
    state = reboot.boot_receipt(host, daily.write_report, lambda _: True, datetime.now(timezone.utc) + timedelta(minutes=16))
    assert state['state'] == 'failed' and not reboot.MARKER.exists()

def test_failed_reboot_does_not_disable_its_own_future_retry(host):
    request(host)
    now = datetime.now(timezone.utc) + timedelta(minutes=16)
    def run(args):
        if '-p' in args:
            return 'enabled' if 'UnitFileState' in args else 'active'
        return ''
    report = watchdog.check(host, now, run=run, health=lambda _: True, hold=host/'hold')
    assert report['status'] == 'reboot_retry_pending'
    assert report['healthy'] is False and report['errors'] == []
    assert report['reboot']['state'] == 'failed'

def test_watchdog_recovers_timer_and_stale_cycle_preserving_hold(host):
    calls = []
    def run(args):
        calls.append(args)
        if '-p' in args:
            return 'disabled' if 'UnitFileState' in args else 'inactive'
        return ''
    report = watchdog.check(host, datetime.now(timezone.utc), run=run, health=lambda _: True, hold=host/'hold')
    assert len(report['repairs']) == 9
    assert ['systemctl', 'start', '--no-block', 'c3po-security-daily.service'] in calls
    (host/'hold').touch()
    calls.clear()
    assert watchdog.check(host, datetime.now(timezone.utc), run=run, hold=host/'hold')['status'] == 'explicit_maintenance_hold'
    assert calls == []

def test_watchdog_recovers_only_existing_required_containers(host, monkeypatch):
    monkeypatch.setattr(watchdog, "recovery_allowed", lambda *_: True)
    request(host)
    reboot.BOOT_ID.write_text('new-boot')
    calls = []
    def run(args):
        calls.append(args)
        if '-p' in args:
            return 'enabled' if 'UnitFileState' in args else 'active'
        return ''
    report = watchdog.check(host, datetime.now(timezone.utc), run=run, health=lambda _: False, hold=host/'hold')
    docker = [c for c in calls if c[0] == 'docker']
    assert len(docker) == 1 and docker[0][-4:] == ['start', 'db', 'api', 'web']
    assert report['status'] == 'failed'

def test_concurrent_deploy_lock_prevents_reboot(host):
    import fcntl
    with (host/'runtime/security/deployment.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result, calls = request(host)
    assert result == 'waiting_packages_or_deploy'
    assert not reboot.MARKER.exists()
    assert not any(c[:2] == ['systemctl', 'reboot'] for c in calls)


def test_job_started_after_idle_check_prevents_reboot(host):
    from app.maintenance_gate import admit
    calls, leases = [], []
    original = runner(calls)
    def run(args):
        # A new job enters after the optimistic DB check, before drain begins.
        if args[:2] == ['docker', 'inspect'] and not leases:
            leases.append(admit(host/'runtime/security/maintenance'))
        return original(args)
    try:
        result, _ = request(host, command=run)
        assert result == 'waiting_active_jobs'
        assert not any(c[:2] == ['systemctl', 'reboot'] for c in calls)
    finally:
        for lease in leases:
            lease.close()


def test_admission_stays_closed_after_systemctl_returns(host, monkeypatch):
    import app.maintenance_gate as gate
    boot = '12345678-1234-1234-1234-123456789012'
    reboot.BOOT_ID.write_text(boot)
    monkeypatch.setattr(gate, 'boot_identity', lambda: reboot.BOOT_ID.read_text())
    assert request(host)[0] == 'requested'
    with pytest.raises(gate.MaintenanceBusy):
        gate.admit(host/'runtime/security/maintenance')
    reboot.BOOT_ID.write_text('12345678-1234-1234-1234-123456789013')
    with gate.admit(host/'runtime/security/maintenance'):
        pass


def test_unknown_container_coverage_never_reboots(host, monkeypatch):
    monkeypatch.setattr(reboot, 'admission_coverage', lambda *args: False)
    result, calls = request(host)
    assert result == 'waiting_admission_coverage'
    assert not any(c[:2] == ['systemctl', 'reboot'] for c in calls)


def test_scheduler_pause_never_stops_active_service_and_restores_on_deferral(host, monkeypatch):
    import c3po_security_schedulers as schedulers
    monkeypatch.setattr(schedulers, 'BOOT_ID', reboot.BOOT_ID)
    calls = []
    def run(args):
        calls.append(args)
        if args[1] == 'list-units':
            return 'backup.timer loaded active waiting Backup\nc3po-security-watchdog.timer loaded active waiting Watchdog'
        if 'MainPID' in args:
            return '0'
        if 'Triggers' in args:
            return 'backup.service'
        if 'ActiveState' in args:
            return 'active'
        return ''
    with schedulers.SchedulingPause(host, run, daily.write_report) as pause:
        assert not pause.idle()
    assert ['systemctl', 'stop', 'backup.timer'] in calls
    assert ['systemctl', 'start', 'backup.timer'] in calls
    assert not any('backup.service' in c and 'stop' in c for c in calls)
    receipt = json.loads((host/'runtime/security/reboot-schedulers.json').read_text())
    assert receipt['restored'] is True


@pytest.mark.skipif(not hasattr(os, 'pidfd_open'), reason='Linux pidfd integration')
def test_scheduler_signal_pauses_only_parent_and_resumes_it(host, monkeypatch):
    import subprocess
    import signal
    import time
    import c3po_security_schedulers as schedulers
    monkeypatch.setattr(schedulers, 'BOOT_ID', reboot.BOOT_ID)
    code = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); print(p.pid,flush=True); time.sleep(30)"
    parent = subprocess.Popen([sys.executable, '-c', code], stdout=subprocess.PIPE, text=True)
    child = int(parent.stdout.readline())
    def status(pid):
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
    def run(args):
        if 'MainPID' in args:
            return str(parent.pid)
        return ''
    try:
        with schedulers.SchedulingPause(host, run, daily.write_report):
            deadline = time.monotonic() + 2
            while status(parent.pid) != 'T' and time.monotonic() < deadline:
                time.sleep(0.01)
            assert status(parent.pid) == 'T'
            assert status(child) != 'T'  # Existing job continues; no group signal.
        deadline = time.monotonic() + 2
        while status(parent.pid) == 'T' and time.monotonic() < deadline:
            time.sleep(0.01)
        assert status(parent.pid) != 'T'
    finally:
        os.kill(parent.pid, signal.SIGCONT)
        os.kill(child, signal.SIGTERM)
        parent.terminate()
        parent.wait(timeout=5)

def test_ingestion_filter_uses_oldest_current_container_without_editing_history(host):
    result, calls = request(host)
    assert result == 'requested'
    sql = [c[-1] for c in calls if 'psql' in c and 'ingestion_runs' in c[-1]]
    assert len(sql) == 1 and "started_at >= '2026-09-11T16:48:21+00:00'::timestamptz" in sql[0]
    assert sql[0].startswith('SELECT ')


def test_current_trial_and_locked_history_veto_maintenance(tmp_path):
    import fcntl
    guard = importlib.import_module('c3po_security_guard')
    now = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)
    historical = tmp_path / '.r2d2-v2-probe-20260910'
    historical.mkdir()
    lock = historical / 'probe.lock'
    lock.touch()
    assert guard.recovery_allowed(now, tmp_path/'hold', tmp_path)
    with lock.open('r') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert not guard.recovery_allowed(now, tmp_path/'hold', tmp_path)
    (tmp_path / '.r2d2-v2-trial-20260914').mkdir()
    assert not guard.recovery_allowed(now, tmp_path/'hold', tmp_path)
    assert not guard.recovery_allowed(now.replace(hour=20), tmp_path/'hold', tmp_path)

@pytest.mark.parametrize('day,hour,minute,expected', [(12, 23, 0, True), (12, 12, 0, True),
    (14, 12, 59, True), (14, 13, 0, False), (14, 21, 29, False), (14, 21, 30, True)])
def test_reboot_flexible_hours_preserve_sessions_and_holds(day, hour, minute, expected, monkeypatch):
    monkeypatch.setattr(daily, 'trial_present', lambda _: False)
    now = datetime(2026, 9, day, hour, minute, tzinfo=timezone.utc)
    config = {'automatic_reboot': True, 'automatic_merge': False}
    assert daily.reboot_window_open(now, config, False) is expected
    assert not daily.reboot_window_open(now, config, True)
    monkeypatch.setattr(daily, 'trial_present', lambda _: True)
    assert not daily.reboot_window_open(now, config, False)


def test_workflow_inactivity_recovered_but_manual_suspension_preserved():
    class Workflows:
        state = 'disabled_inactivity'
        calls = []
        def request(self, path, method='GET'):
            self.calls.append((path, method))
            return {'state': self.state}
    gh = Workflows()
    daily.ensure_workflows(gh, False)
    assert sum(method == 'PUT' for _, method in gh.calls) == 3
    gh.calls.clear()
    gh.state = 'disabled_manually'
    with pytest.raises(RuntimeError):
        daily.ensure_workflows(gh, False)
    assert not any(method == 'PUT' for _, method in gh.calls)
    daily.ensure_workflows(gh, True)

@pytest.mark.parametrize('content', [
    {'mode': 'CERTIFIED', 'epoch': 'R2D2-V2-SHADOW-20260916'},
    {'mode': 'CERTIFIED', 'epoch': 'R2D2-V2-SHADOW-20260916', 'terminal': True},
    {'mode': 'DIAGNOSTIC', 'epoch': 'R2D2-V2-SHADOW-20260916'},
    {}, [], 'broken-json',
])
def test_installed_certified_or_unknown_release_vetoes_until_archived(tmp_path, content):
    guard = importlib.import_module('c3po_security_guard')
    now = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)
    release = tmp_path / 'r2d2-v2-release-session.json'
    release.write_text(content if isinstance(content, str) else json.dumps(content))
    assert not guard.recovery_allowed(now, tmp_path/'hold', tmp_path)
    assert guard.trial_present(now.replace(year=2027), tmp_path)
    archive = tmp_path / 'retired'
    archive.mkdir()
    release.rename(archive/release.name)
    assert guard.recovery_allowed(now, tmp_path/'hold', tmp_path)


def test_diagnostic_distinguished_but_pinned_marker_and_symlinks_veto(tmp_path):
    guard = importlib.import_module('c3po_security_guard')
    now = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)
    release = tmp_path / 'r2d2-v2-release-diagnostic.json'
    release.write_text(json.dumps({'mode': 'DIAGNOSTIC', 'epoch': 'R2D2-V2-DIAG-example'}))
    assert not guard.trial_present(now, tmp_path)
    marker = tmp_path / '.r2d2-v2-pinned'
    marker.touch()
    assert guard.trial_present(now, tmp_path)
    marker.unlink()
    marker.symlink_to(tmp_path/'missing')
    assert guard.trial_present(now, tmp_path)
    marker.unlink()
    release.unlink()
    release.symlink_to(tmp_path/'missing')
    assert guard.trial_present(now, tmp_path)
