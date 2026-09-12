from __future__ import annotations
import importlib
import json
import sys
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

@pytest.mark.parametrize('hour,minute,expected', [(10, 0, True), (11, 44, True), (11, 45, False), (12, 0, False), (20, 0, False)])
def test_reboot_reserves_time_for_postboot_recovery(hour, minute, expected):
    assert daily.reboot_window_open(datetime(2026, 9, 12, hour, minute, tzinfo=timezone.utc), {'automatic_merge': True}, False) is expected

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
