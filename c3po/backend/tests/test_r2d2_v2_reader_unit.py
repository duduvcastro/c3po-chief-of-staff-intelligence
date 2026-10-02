"""Pins the text of the reader units and of their document (c3po/deployment/reader).

Offline: the unit files are read and parsed here, never by systemd; the docker argument list is split
with shlex, never run. The alert unit's shell text is run with its paths replaced by temporary ones.
"""
from datetime import date, datetime, time as clock_time, timedelta
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

from app.config import Settings
from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_epoch_assembler import SESSIONS

BACKEND = Path(__file__).resolve().parents[1]
UNIT_ROOT = BACKEND.parent / 'deployment' / 'reader'
SUPERVISOR_ROOT = BACKEND.parent / 'deployment' / 'massive-supervisor'
PLACEHOLDERS = ('@IMAGE_ID@', '@HOST_DATA_ROOT@', '@HOST_JOURNAL_ROOT@', '@CONTAINER_JOURNAL_ROOT@', '@HOST_CAPACITY_ROOT@',
                '@HOST_CONFIG_DIR@', '@NETWORK@')
HOST_PATHS = ('@HOST_DATA_ROOT@', '@HOST_JOURNAL_ROOT@', '@HOST_CAPACITY_ROOT@', '@HOST_CONFIG_DIR@')
# The producer's own bind line with `readonly` added: same source, same container path.
JOURNAL_MOUNT = 'type=bind,source=@HOST_JOURNAL_ROOT@,target=@CONTAINER_JOURNAL_ROOT@,readonly'
REQUIRES = 'RequiresMountsFor=@HOST_DATA_ROOT@ @HOST_JOURNAL_ROOT@ @HOST_CAPACITY_ROOT@ @HOST_CONFIG_DIR@'
ENV_FILES = ['@HOST_CONFIG_DIR@/secret.env', '@HOST_CONFIG_DIR@/pins.env', '@HOST_CONFIG_DIR@/activation.env']
LAUNCHER_TAIL = ['python', '-I', '-B', '/c3po-reader/reader_launcher.py']
WORKER_TAIL = ['python', '-B', '-m', 'app.r2d2_v2_shadow_worker']
VALUELESS = ('--rm', '--init', '--read-only')
OPTIONS = [('--rm', None), ('--init', None), ('--restart', 'no'), ('--name', 'c3po-reader'), ('--pull', 'never'),
    ('--user', '0:0'), ('--workdir', '/app'), ('--network', '@NETWORK@'), ('--read-only', None),
    ('--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=256m'), ('--cap-drop', 'ALL'),
    ('--security-opt', 'no-new-privileges'), ('--pids-limit', '512'), ('--stop-timeout', '25'),
    ('--env-file', ENV_FILES[0]), ('--env-file', ENV_FILES[1]), ('--env-file', ENV_FILES[2]),
    ('--mount', 'type=bind,source=@HOST_DATA_ROOT@,target=/app/day-d-data,readonly'),
    ('--mount', JOURNAL_MOUNT),
    ('--mount', 'type=bind,source=@HOST_CAPACITY_ROOT@,target=/c3po-capacity,readonly')]
LAUNCHER_MOUNT = ('--mount', 'type=bind,source=@HOST_CONFIG_DIR@/launcher,target=/c3po-reader,readonly')
FORBIDDEN = {'-d', '--detach', '-t', '--tty', '-i', '--interactive', '-e', '--env', '-v', '--volume', '--privileged',
             '--cap-add', '--cidfile', '--pid', '--ipc', '--device', '--add-host', '--publish', '-p', '--userns',
             '--label', '-l', '--entrypoint', '--volumes-from', '--uts', '--cgroupns'}
NEW_YORK = ZoneInfo('America/New_York')
ACTIVATION_SHA = '2053f3f6f528ad7dc56d500666ac2cf48f79c3aadd3c98eb35b53ee92eff611b'


def text(name):
    return (UNIT_ROOT / name).read_text()


def exec_start(unit):
    lines = [line for line in unit.replace('\\\n', ' ').splitlines() if line.startswith('ExecStart=')]
    assert len(lines) == 1
    return shlex.split(lines[0][len('ExecStart='):])


def run_options(argv, image):
    """(options before the image, command after it); only --rm, --init and --read-only take no value."""
    assert argv[:2] == ['/usr/bin/docker', 'run'] and argv.count(image) == 1
    at = argv.index(image); head = argv[2:at]; options = []; index = 0
    while index < len(head):
        assert head[index].startswith('--')
        if head[index] in VALUELESS:
            options.append((head[index], None)); index += 1
        else:
            options.append((head[index], head[index + 1])); index += 2
    return options, argv[at + 1:]


def mounts(options):
    result = []
    for name, value in options:
        if name == '--mount':
            fields = value.split(',')
            result.append({**dict(item.split('=', 1) for item in fields if '=' in item), 'flags': [f for f in fields if '=' not in f]})
    return result


def block(name):
    """The lines between a pair of markers of the document, each ended by a newline."""
    found = re.search(r'<!-- %s:begin -->\n```\n(.*?)```\n<!-- %s:end -->' % (name, name), text('README.md'), re.S)
    assert found is not None
    return found.group(1)


def launcher():
    spec = importlib.util.spec_from_file_location('c3po_reader_launcher_for_units', UNIT_ROOT / 'reader_launcher.py')
    module = importlib.util.module_from_spec(spec)
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True    # no bytecode next to a deployment file
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


# ---------------------------------------------------------------- the service

def test_the_directory_holds_exactly_the_five_files():
    assert sorted(entry.name for entry in UNIT_ROOT.iterdir() if entry.name != '__pycache__') == [
        'README.md', 'c3po-reader-alert.service', 'c3po-reader.service', 'c3po-reader.timer', 'reader_launcher.py']


def test_unit_container_arguments_are_pinned():
    unit = text('c3po-reader.service')
    options, tail = run_options(exec_start(unit), '@IMAGE_ID@')
    assert options == OPTIONS + [LAUNCHER_MOUNT]
    assert tail == LAUNCHER_TAIL
    assert set(re.findall(r'@[A-Z_]+@', unit)) == set(PLACEHOLDERS)
    assert unit.count('@') == 2 * len(re.findall(r'@[A-Z_]+@', unit))
    assert [unit.count(name) for name in PLACEHOLDERS] == [2, 2, 2, 1, 2, 9, 1]
    # None of these in the template is what makes a textual render equal to systemd's own parsing.
    assert not set('%$"\';') & set(unit)
    assert not any(line.lstrip().startswith('#') for line in unit.splitlines())


def test_every_mount_is_a_read_only_bind_and_the_fixed_targets_are_children_of_the_root():
    options, _ = run_options(exec_start(text('c3po-reader.service')), '@IMAGE_ID@')
    found = mounts(options)
    assert len(found) == 4 and all(mount['type'] == 'bind' and mount['flags'] == ['readonly'] for mount in found)
    assert all(set(mount) == {'type', 'source', 'target', 'flags'} for mount in found)
    assert [mount['target'] for mount in found] == ['/app/day-d-data', '@CONTAINER_JOURNAL_ROOT@', '/c3po-capacity', '/c3po-reader']
    # AnchoredRoot hashes (device, inode) of every component below '/': a pinned capacity root must have no
    # component on the container's own filesystem, so its mount target is a child of '/'.
    assert all(len(Path(mount['target']).parts) == 2 for mount in found[2:])
    # The configuration directory is never visible in the container: only its launcher subdirectory is.
    assert [mount['source'] for mount in found] == ['@HOST_DATA_ROOT@', '@HOST_JOURNAL_ROOT@', '@HOST_CAPACITY_ROOT@',
                                                    '@HOST_CONFIG_DIR@/launcher']
    assert not any(option in ('-v', '--volume') or 'docker.sock' in (value or '') for option, value in options)


def test_the_journal_bind_is_the_producer_line_made_read_only_at_the_same_path_and_uid():
    unit = text('c3po-reader.service'); producer = (SUPERVISOR_ROOT / 'c3po-massive.service').read_text()
    options, _ = run_options(exec_start(unit), '@IMAGE_ID@')
    producer_options, producer_tail = run_options(exec_start(producer), '@IMAGE_ID@')
    writable, = [value for name, value in producer_options if name == '--mount' and 'JOURNAL' in value]
    assert writable == 'type=bind,source=@HOST_JOURNAL_ROOT@,target=@CONTAINER_JOURNAL_ROOT@'
    # One journal bind in the reader, and it is the producer's line with `readonly` appended: never read-write.
    assert [value for name, value in options if name == '--mount' and 'JOURNAL' in value] == [writable + ',readonly'] == [JOURNAL_MOUNT]
    # The path the producer writes to is the path it binds, so it is the path the reader's pins name.
    assert producer_tail[producer_tail.index('--journal-root') + 1] == '@CONTAINER_JOURNAL_ROOT@'
    # Both sides are uid 0 with no capability: the reader reads the producer's private objects as their owner.
    for side in (options, producer_options):
        assert ('--user', '0:0') in side and ('--cap-drop', 'ALL') in side
    # The two names appear in the reader unit only where the bind and its mount ordering need them.
    lines = unit.splitlines()
    assert [line for line in lines if '@HOST_JOURNAL_ROOT@' in line] == [REQUIRES, '  --mount ' + JOURNAL_MOUNT + ' \\']
    assert [line for line in lines if '@CONTAINER_JOURNAL_ROOT@' in line] == ['  --mount ' + JOURNAL_MOUNT + ' \\']
    assert REQUIRES.split('=', 1)[1].split() == list(HOST_PATHS)


def test_the_environment_arrives_only_through_the_three_private_files():
    unit = text('c3po-reader.service'); argv = exec_start(unit)
    assert not FORBIDDEN & set(argv) and not any(value.split('=', 1)[0] in FORBIDDEN for value in argv)
    assert [argv[index + 1] for index, value in enumerate(argv) if value == '--env-file'] == ENV_FILES
    assert not any(value.startswith(('--env-file=', '--env=', '--restart=', '--init=', '--network=')) for value in argv)
    assert [argv[index + 1] for index, value in enumerate(argv) if value == '--restart'] == ['no']
    assert [argv[index + 1] for index, value in enumerate(argv) if value == '--network'] == ['@NETWORK@']
    assert argv.count('--init') == 1
    assert not any(value in unit for value in ('docker.sock', 'DOCKER_HOST', 'c3po/backend:production', ':rollback',
        'User=', 'Group=', 'TZ=', 'rm -f', '--force', 'C3PO_', 'DATABASE', 'postgresql', 'EnvironmentFile',
        'docker exec', 'compose', 'SuccessExitStatus', 'RuntimeMaxSec', 'network host', 'network=host'))
    lines = unit.splitlines()
    assert [line for line in lines if line.startswith('Environment')] == ['Environment=DOCKER_CONFIG=@HOST_CONFIG_DIR@/docker-cli']


def test_an_unactivated_unit_is_skipped_by_one_condition_per_environment_file():
    lines = text('c3po-reader.service').splitlines()
    conditions = [line for line in lines if line.startswith('ExecCondition=')]
    assert conditions == ['ExecCondition=/usr/bin/test -f ' + path for path in ENV_FILES]
    # Conditions come before the two preconditions, which come before the run.
    order = [index for index, line in enumerate(lines) if line.startswith(('ExecCondition=', 'ExecStartPre=', 'ExecStart='))]
    kinds = [lines[index].split('=', 1)[0] for index in order]
    assert kinds == ['ExecCondition'] * 3 + ['ExecStartPre'] * 2 + ['ExecStart']
    assert [line for line in lines if line.startswith('ExecStartPre=')] == ['ExecStartPre=-/usr/bin/docker rm c3po-reader',
        'ExecStartPre=/usr/bin/docker image inspect --format {{.Id}} @IMAGE_ID@']


def test_unit_binds_the_restart_and_stop_contract():
    unit = text('c3po-reader.service'); lines = unit.splitlines()
    assert all(value in lines for value in ('Type=exec', 'Requires=docker.service', 'Restart=on-failure', 'RestartSec=5s',
        'RestartPreventExitStatus=78', 'StartLimitIntervalSec=8h', 'StartLimitBurst=40', 'TimeoutStartSec=60s',
        'TimeoutStopSec=30s', 'KillMode=control-group', 'UMask=0077', 'NoNewPrivileges=true',
        'SyslogIdentifier=c3po-reader', 'OnFailure=c3po-reader-alert.service',
        REQUIRES,
        'ExecStop=-/usr/bin/docker stop -t 25 c3po-reader', 'ExecStopPost=-/usr/bin/docker stop -t 25 c3po-reader'))
    assert [sum(line.startswith(key + '=') for line in lines) for key in ('ExecCondition', 'ExecStartPre', 'ExecStart',
        'ExecStop', 'ExecStopPost', 'Restart', 'RestartSec', 'StartLimitBurst', 'RestartPreventExitStatus',
        'OnFailure')] == [3, 2, 1, 1, 1, 1, 1, 1, 1, 1]
    # Start limit and failure hook belong to [Unit]; the rest to [Service].
    unit_section = unit.split('[Service]')[0]
    assert all(key in unit_section for key in ('StartLimitIntervalSec=8h', 'StartLimitBurst=40', 'OnFailure='))
    # The launcher gives its child 20 s, docker gives the container 25 s, systemd gives the stop 30 s.
    grace = int(dict((name, value) for name, value in run_options(exec_start(unit), '@IMAGE_ID@')[0] if value)['--stop-timeout'])
    script = launcher()
    assert script.CHILD_TERM_GRACE_SECONDS < grace == 25 < 30
    assert script.TERMINAL_EXIT == 78 and script.APP_ROOT == '/app'
    # The unit's command is the launcher by its mounted path, in isolated mode, with no argument.
    assert Path(LAUNCHER_TAIL[-1]).name == 'reader_launcher.py' and (UNIT_ROOT / 'reader_launcher.py').is_file()


# ---------------------------------------------------------------- the timer

def test_timer_lines_fit_the_launcher_window_and_follow_the_producer_timer():
    timer = text('c3po-reader.timer').splitlines()
    assert all(value in timer for value in ('OnBootSec=90s', 'Persistent=false', 'AccuracySec=1s',
        'Unit=c3po-reader.service', 'WantedBy=timers.target'))
    calendar_lines = [line for line in timer if line.startswith('OnCalendar=')]
    assert calendar_lines == ['OnCalendar=Mon..Fri *-*-* 04:00:00 America/New_York',
                              'OnCalendar=Mon..Fri *-*-* 09:29:20 America/New_York']
    assert '@' not in '\n'.join(timer)
    producer = (SUPERVISOR_ROOT / 'c3po-massive.timer').read_text().splitlines()
    assert 'OnCalendar=Mon..Fri *-*-* 09:29:00 America/New_York' in producer
    script = launcher(); calendar = ShadowCalendar()
    for day in SESSIONS:
        session = date.fromisoformat(day); details = calendar.details(session)
        first = datetime.combine(session, clock_time(4, 0, 0), NEW_YORK)
        second = datetime.combine(session, clock_time(9, 29, 20), NEW_YORK)
        producer_start = datetime.combine(session, clock_time(9, 29, 0), NEW_YORK)
        handover = details['open'] - timedelta(seconds=script.HANDOVER_BEFORE_OPEN_SECONDS)
        deadline = details['open'] - timedelta(seconds=script.READY_DEADLINE_BEFORE_OPEN_SECONDS)
        # 04:00 starts the pre-open phase, inside the launcher's window.
        assert details['open'] - timedelta(seconds=script.PRE_OPEN_SECONDS) <= first < handover
        # The handover precedes the producer's start; the second line follows it and precedes the marker deadline.
        assert handover < producer_start < second < deadline < details['open']
        # No session of the epoch is an early close: the fixed clock times of this document hold all week.
        assert details['close'] == datetime.combine(session, clock_time(16, 0), NEW_YORK)


# ---------------------------------------------------------------- the alert unit

def alert_command():
    unit = text('c3po-reader-alert.service'); lines = unit.splitlines()
    assert all(value in lines for value in ('Type=oneshot', 'UMask=0077', 'SyslogIdentifier=c3po-reader-alert'))
    line, = [line for line in lines if line.startswith('ExecStart=')]
    assert '@' not in unit and '$' not in unit and '"' not in unit and '[Install]' not in unit
    # systemd reads %% as one percent sign and passes the single-quoted text as one argument.
    assert unit.count('%') == 2 * unit.count('%%') == 12
    argv = shlex.split(line[len('ExecStart='):].replace('%%', '%'))
    assert argv[:2] == ['/bin/sh', '-c'] and len(argv) == 3
    return argv[2]


def test_the_alert_unit_writes_one_private_dated_marker_and_never_overwrites(tmp_path):
    command = alert_command()
    assert command == ("umask 077 && set -C && /usr/bin/systemctl show c3po-reader.service "
        "--property=Result,ExecMainCode,ExecMainStatus,NRestarts > /var/lib/c3po-reader/failed.`/usr/bin/date -u +%Y%m%dT%H%M%SZ`")
    state = tmp_path / 'state'; state.mkdir(mode=0o700)
    systemctl = tmp_path / 'systemctl'
    systemctl.write_text('#!/bin/sh\necho "$@"\necho Result=exit-code\necho ExecMainStatus=78\n'); systemctl.chmod(0o700)
    fixed = tmp_path / 'date'; fixed.write_text('#!/bin/sh\necho 20261005T133000Z\n'); fixed.chmod(0o700)

    def run(date_program):
        replaced = (command.replace('/var/lib/c3po-reader', str(state)).replace('/usr/bin/systemctl', str(systemctl))
                    .replace('/usr/bin/date', str(date_program)))
        previous = os.umask(0o022)       # the marker is private because of the command's own umask
        try:
            return subprocess.run(['/bin/sh', '-c', replaced], capture_output=True, text=True, timeout=30)
        finally:
            os.umask(previous)

    assert run(shutil.which('date')).returncode == 0
    marker, = list(state.iterdir())
    assert re.fullmatch(r'failed\.\d{8}T\d{6}Z', marker.name)
    assert stat.S_IMODE(marker.stat().st_mode) == 0o600
    assert marker.read_text() == ('show c3po-reader.service --property=Result,ExecMainCode,ExecMainStatus,NRestarts\n'
                                  'Result=exit-code\nExecMainStatus=78\n')
    marker.unlink()
    assert run(fixed).returncode == 0
    marker = state / 'failed.20261005T133000Z'
    marker.write_text('first')
    again = run(fixed)                   # the same second: refused by the no-clobber option, nothing rewritten
    assert again.returncode != 0 and marker.read_text() == 'first' and len(list(state.iterdir())) == 1


# ---------------------------------------------------------------- a render with sample values

def render(template, values):
    """The substitution grammar of the document; refuses what the installer must refuse."""
    assert set(values) == set(PLACEHOLDERS)
    for name in HOST_PATHS:
        value = values[name]
        if not re.fullmatch(r'/[A-Za-z0-9._/-]+', value) or value.endswith('/') or any(
                part in ('', '.', '..') for part in value.split('/')[1:]):
            raise ValueError(name)
    # One component below '/', and none of the names this container already uses there.
    container = values['@CONTAINER_JOURNAL_ROOT@']
    if not re.fullmatch(r'/[A-Za-z0-9._-]+', container) or container in ('/.', '/..', '/app', '/tmp', '/c3po-capacity',
                                                                         '/c3po-reader'):
        raise ValueError('@CONTAINER_JOURNAL_ROOT@')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', values['@IMAGE_ID@']):
        raise ValueError('@IMAGE_ID@')
    network = values['@NETWORK@']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', network) or network in ('host', 'none', 'bridge'):
        raise ValueError('@NETWORK@')
    config = Path(values['@HOST_CONFIG_DIR@']); journal = Path(values['@HOST_JOURNAL_ROOT@'])
    for other in (Path(values['@HOST_DATA_ROOT@']), Path(values['@HOST_CAPACITY_ROOT@']), journal):
        if config == other or other in config.parents:
            raise ValueError('@HOST_CONFIG_DIR@')
    # The journal root is none of the other three, lies inside none of them and contains none of them.
    for other in (Path(values['@HOST_DATA_ROOT@']), Path(values['@HOST_CAPACITY_ROOT@']), config):
        if journal == other or other in journal.parents or journal in other.parents:
            raise ValueError('@HOST_JOURNAL_ROOT@')
    for name, value in values.items():
        template = template.replace(name, value)
    if '@' in template:
        raise ValueError('placeholder left')
    return template


SAMPLE = {'@IMAGE_ID@': 'sha256:' + 'a' * 64, '@HOST_DATA_ROOT@': '/mnt/day-d-data',
          '@HOST_JOURNAL_ROOT@': '/var/lib/c3po-bar/journal', '@CONTAINER_JOURNAL_ROOT@': '/c3po-journal',
          '@HOST_CAPACITY_ROOT@': '/mnt/day-d-data/r2d2-v2-capacity-epoch03', '@HOST_CONFIG_DIR@': '/etc/c3po-reader',
          '@NETWORK@': 'c3po_c3po_internal'}


def test_rendered_unit_matches_the_backend_data_mount():
    unit = render(text('c3po-reader.service'), SAMPLE)
    options, tail = run_options(exec_start(unit), SAMPLE['@IMAGE_ID@'])
    assert tail == LAUNCHER_TAIL and ('--network', 'c3po_c3po_internal') in options
    assert [mount['source'] for mount in mounts(options)] == ['/mnt/day-d-data', '/var/lib/c3po-bar/journal',
        '/mnt/day-d-data/r2d2-v2-capacity-epoch03', '/etc/c3po-reader/launcher']
    # Every target but the data volume's is a child of '/': the journal is not reached through the data bind.
    targets = [mount['target'] for mount in mounts(options)]
    assert targets == ['/app/day-d-data', '/c3po-journal', '/c3po-capacity', '/c3po-reader']
    assert all(len(Path(target).parts) == 2 for target in targets[1:])
    assert 'RequiresMountsFor=/mnt/day-d-data /var/lib/c3po-bar/journal /mnt/day-d-data/r2d2-v2-capacity-epoch03 /etc/c3po-reader' \
        in unit.splitlines()
    assert [value for name, value in options if name == '--env-file'] == [
        '/etc/c3po-reader/secret.env', '/etc/c3po-reader/pins.env', '/etc/c3po-reader/activation.env']
    # Same data mount as the compose services: the release file and the source directories keep their container paths.
    compose = (BACKEND.parent / 'compose.yml').read_text()
    worker = re.search(r'^  r2d2-worker:\n((?:    .*\n|\n)+)', compose, re.M)
    assert worker is not None and re.search(r'^      - \S+:/app/day-d-data$', worker.group(1), re.M)
    assert re.search(r'^      C3PO_DATABASE_URL: \S+@db:5432/c3po$', worker.group(1), re.M)
    assert re.search(r'^      - c3po_internal$', worker.group(1), re.M)
    # No compose service launches the reader, by module or by script.
    assert 'r2d2_v2_shadow_worker' not in compose and 'reader_launcher' not in compose
    assert not re.search(r'^\s*USER\b', (BACKEND / 'Dockerfile').read_text(), re.M)
    producer = (SUPERVISOR_ROOT / 'c3po-massive.service').read_text()
    assert 'ExecStartPre=/usr/bin/docker image inspect --format {{.Id}} @IMAGE_ID@' in producer   # one image, one check
    # The producer template rendered with the same two values binds the same directory at the same path, read-write,
    # and writes to it; the reader's line differs by `readonly` alone.
    for name in ('@HOST_JOURNAL_ROOT@', '@CONTAINER_JOURNAL_ROOT@'):
        producer = producer.replace(name, SAMPLE[name])
    assert '  --mount type=bind,source=/var/lib/c3po-bar/journal,target=/c3po-journal \\\n' in producer
    assert '  --mount type=bind,source=/var/lib/c3po-bar/journal,target=/c3po-journal,readonly \\\n' in unit
    assert ' --journal-root /c3po-journal ' in producer


@pytest.mark.parametrize('name,value', [
    ('@NETWORK@', 'host'), ('@NETWORK@', 'none'), ('@NETWORK@', 'bridge'), ('@NETWORK@', 'container:db'),
    ('@NETWORK@', 'a b'), ('@IMAGE_ID@', 'c3po/backend:production'), ('@IMAGE_ID@', 'sha256:' + 'A' * 64),
    ('@HOST_DATA_ROOT@', '/mnt/day d'), ('@HOST_DATA_ROOT@', '/mnt/../etc'), ('@HOST_DATA_ROOT@', '/mnt/day-d-data/'),
    ('@HOST_CAPACITY_ROOT@', '/mnt/x,readonly=false'), ('@HOST_CAPACITY_ROOT@', '/mnt/%h'), ('@HOST_CAPACITY_ROOT@', '/mnt/$x'),
    ('@HOST_CONFIG_DIR@', '/mnt/day-d-data/reader'), ('@HOST_CONFIG_DIR@', '/mnt/day-d-data'), ('@HOST_CONFIG_DIR@', 'etc/c3po-reader'),
    ('@HOST_CONFIG_DIR@', '/var/lib/c3po-bar/journal/reader'), ('@HOST_CONFIG_DIR@', '/var/lib/c3po-bar/journal'),
    # The earlier layout, the journal root as a leaf of the data volume, is refused on both sides.
    ('@HOST_JOURNAL_ROOT@', '/mnt/day-d-data/r2d2-v2-massive-epoch03'), ('@HOST_JOURNAL_ROOT@', '/mnt/day-d-data'),
    ('@HOST_JOURNAL_ROOT@', '/mnt'), ('@HOST_JOURNAL_ROOT@', '/mnt/day-d-data/r2d2-v2-capacity-epoch03/journal'),
    ('@HOST_JOURNAL_ROOT@', '/etc/c3po-reader/journal'), ('@HOST_JOURNAL_ROOT@', '/etc'),
    ('@HOST_JOURNAL_ROOT@', '/var/lib/c3po-bar/journal/'), ('@HOST_JOURNAL_ROOT@', 'var/lib/c3po-bar/journal'),
    ('@HOST_JOURNAL_ROOT@', '/var/lib/x,readonly=false'), ('@HOST_JOURNAL_ROOT@', '/var/lib/../journal'),
    ('@CONTAINER_JOURNAL_ROOT@', '/app/day-d-data/r2d2-v2-massive-epoch03'), ('@CONTAINER_JOURNAL_ROOT@', '/app/day-d-data'),
    ('@CONTAINER_JOURNAL_ROOT@', '/app'), ('@CONTAINER_JOURNAL_ROOT@', '/tmp'), ('@CONTAINER_JOURNAL_ROOT@', '/c3po-capacity'),
    ('@CONTAINER_JOURNAL_ROOT@', '/c3po-reader'), ('@CONTAINER_JOURNAL_ROOT@', '/var/journal'), ('@CONTAINER_JOURNAL_ROOT@', '/..'),
    ('@CONTAINER_JOURNAL_ROOT@', '/c3po-journal/'), ('@CONTAINER_JOURNAL_ROOT@', 'c3po-journal'),
    ('@CONTAINER_JOURNAL_ROOT@', '/c3po journal'), ('@CONTAINER_JOURNAL_ROOT@', '/c3po-journal,readonly=false')])
def test_the_render_refuses_values_outside_the_grammar(name, value):
    with pytest.raises(ValueError):
        render(text('c3po-reader.service'), {**SAMPLE, name: value})
    document = text('README.md')
    assert all(phrase in document for phrase in ('`^/[A-Za-z0-9._/-]+$`', '`^sha256:[0-9a-f]{64}$`', '`^/[A-Za-z0-9._-]+$`',
        'for the four host paths', '`/app`, `/tmp`, `/c3po-capacity` and `/c3po-reader`',
        '**A journal root inside the data volume is the earlier layout and is refused**',
        'when either journal value differs from the one in the installed producer unit',
        '`host`, `none`, `bridge` and `container:*` are **forbidden in production**', 'must fail if any `@` survives'))


# ---------------------------------------------------------------- the worker-direct fallback (D1)

def test_the_fallback_unit_is_the_shipped_unit_without_the_launcher():
    shipped = text('c3po-reader.service'); fallback = block('fallback-service')
    options, tail = run_options(exec_start(fallback), '@IMAGE_ID@')
    assert options == OPTIONS and tail == WORKER_TAIL
    # Exactly three differences: no launcher mount, the worker as the command, 143 counted as a clean stop.
    expected = (shipped.replace('  --mount type=bind,source=@HOST_CONFIG_DIR@/launcher,target=/c3po-reader,readonly \\\n', '')
                .replace('  python -I -B /c3po-reader/reader_launcher.py\n', '  python -B -m app.r2d2_v2_shadow_worker\n')
                .replace('RestartPreventExitStatus=78\n', 'RestartPreventExitStatus=78\nSuccessExitStatus=143\n'))
    assert fallback == expected != shipped
    assert [fallback.count(name) for name in PLACEHOLDERS] == [2, 2, 2, 1, 2, 8, 1]
    assert not FORBIDDEN & set(exec_start(fallback)) and not set('%$"\';') & set(fallback)
    stop_service = block('fallback-stop-service').splitlines()
    assert 'Type=oneshot' in stop_service and 'ExecStart=/usr/bin/systemctl stop c3po-reader.service' in stop_service
    stop_timer = block('fallback-stop-timer').splitlines()
    assert [line for line in stop_timer if line.startswith('OnCalendar=')] == ['OnCalendar=Mon..Fri *-*-* 16:20:00 America/New_York']
    assert all(value in stop_timer for value in ('Unit=c3po-reader-stop.service', 'Persistent=false', 'WantedBy=timers.target'))
    script = launcher(); calendar = ShadowCalendar()
    for day in SESSIONS:
        session = date.fromisoformat(day)
        stop = datetime.combine(session, clock_time(16, 20), NEW_YORK)
        assert stop == calendar.details(session)['close'] + timedelta(seconds=script.STOP_AFTER_CLOSE_SECONDS)
    assert WORKER_TAIL[-1] == script.WORKER_MODULE


# ---------------------------------------------------------------- the document

def read_by_code():
    """Every settings attribute the worker and the capacity bootstrap read."""
    names = set()
    for module in ('r2d2_v2_shadow_worker.py', 'r2d2_v2_capacity_bootstrap.py'):
        source = (BACKEND / 'app' / module).read_text()
        names |= set(re.findall(r"\bsettings\.([a-z0-9_]+)", source))
        names |= set(re.findall(r"getattr\(settings, ?'([a-z0-9_]+)'", source))
    return names


def test_the_environment_names_of_the_document_are_the_ones_the_code_reads():
    pins = block('pins-env').splitlines(); activation = block('activation-env')
    pin_names = [line.split('=', 1)[0] for line in pins]
    assert pin_names == ['C3PO_BUILD_SHA', 'C3PO_R2D2_V2_SHADOW_RELEASE_FILE', 'C3PO_R2D2_V2_SHADOW_RELEASE_SHA',
        'C3PO_R2D2_V2_SHADOW_SOURCE_DIR', 'C3PO_R2D2_MICROSTRUCTURE_RAW_DIR', 'C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR',
        'C3PO_R2D2_V2_CAPACITY_REQUIRED', 'C3PO_R2D2_V2_CAPACITY_VETO_MODE', 'C3PO_R2D2_V2_CAPACITY_CONFIG_FILE',
        'C3PO_R2D2_V2_CAPACITY_CONFIG_SHA', 'C3PO_R2D2_V2_SHADOW_POLL_SECONDS', 'C3PO_READER_LAUNCHER_SHA256']
    assert pin_names[-1] == launcher().LAUNCHER_PIN_ENV
    # The journal directory is the producer unit's container root, read from the installed unit: no longer a leaf of
    # the data volume. Only the release file and the two source directories are still under /app/day-d-data.
    assert pins[pin_names.index('C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR')] == \
        'C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR=<@CONTAINER_JOURNAL_ROOT@ of the installed producer unit>'
    assert [name for name, line in zip(pin_names, pins) if '/app/day-d-data' in line] == [
        'C3PO_R2D2_V2_SHADOW_RELEASE_FILE', 'C3PO_R2D2_V2_SHADOW_SOURCE_DIR', 'C3PO_R2D2_MICROSTRUCTURE_RAW_DIR']
    assert '/app/day-d-data/<journal leaf>' not in text('README.md')
    assert activation == 'C3PO_R2D2_V2_SHADOW_ENABLED=true\nC3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true\n'
    assert hashlib.sha256(activation.encode()).hexdigest() == ACTIVATION_SHA and ACTIVATION_SHA in text('README.md')
    documented = set(pin_names[:-1]) | {line.split('=', 1)[0] for line in activation.splitlines()} | {'C3PO_DATABASE_URL'}
    assert '\nC3PO_DATABASE_URL=<value>\n' in text('README.md') and len(documented) == 14
    # Each documented name is a field of the settings class under its prefix ...
    assert Settings.model_config.get('env_prefix') == 'C3PO_'
    fields = {name[len('C3PO_'):].lower() for name in documented}
    assert fields <= set(Settings.model_fields)
    # ... and the set is exactly what the worker and the capacity bootstrap read from the settings object.
    assert fields == read_by_code()
    # The values of the document's constant lines are accepted by the real class.
    settings = Settings(r2d2_v2_shadow_enabled='true', r2d2_v2_massive_bars_enabled='true', r2d2_v2_capacity_required='true',
                        r2d2_v2_capacity_veto_mode='DISPATCH_AND_DERIVATION_ONLY', r2d2_v2_shadow_poll_seconds='1.0')
    assert (settings.r2d2_v2_shadow_enabled, settings.r2d2_v2_massive_bars_enabled, settings.r2d2_v2_capacity_required,
            settings.r2d2_v2_shadow_poll_seconds) == (True, True, True, 1.0)
    # Without its line the journal directory is not the producer's: the default is another path.
    assert str(Settings.model_fields['r2d2_v2_massive_journal_dir'].default) == '/app/data/r2d2-v2-massive'


def test_the_document_states_what_is_open_what_is_refused_and_what_is_unverified():
    document = text('README.md')
    top = document.split('## Contract')[0]
    assert '## Open decisions' in top and all('| %s |' % name in top for name in ('D1', 'D3', 'D4', 'D6', 'D11', 'L1', 'L2'))
    assert '**Unverified on the host.**' in top and 'Offline candidate.' in top
    source = text('reader_launcher.py')
    for code in sorted(set(re.findall(r"'(READER_[A-Z_]+)'", source))):
        assert '`%s`' % code in document, code
    for status in ('REFUSED', 'STARTING', 'HANDOVER', 'READY_OBSERVED', 'READY_NOT_OBSERVED', 'STATUS_WITHHELD', 'STOPPED', 'FAILED'):
        assert "'%s'" % status in source and '`%s`' % status in document
    never = next(paragraph for paragraph in document.split('\n\n') if paragraph.startswith('Never add:'))
    for option in ('`-d`', '`-t`', '`-i`', '`-e`/`--env`', '`-v`/`--volume`', '`--privileged`', '`--cap-add`', '`--cidfile`',
                   '`--pid`', '`--ipc`', '`--label`', '`--network host`', '`EnvironmentFile=`', '`SuccessExitStatus=`',
                   '`docker exec`', 'a fourth `--env-file`', 'Docker socket'):
        assert option in never, option
    for heading in ('## Journal root', '## Daily contract', '## The launcher file', '## Environment files', '## Units',
                    '## Process and restart contract', '## Operations', '### 1. Provisioning', '### 2. Unit installation (no activation, no overwrite)',
                    '### 3. Pins', '### 4. Activation', '### 5. Pins replacement', '### 6. Liveness readbacks',
                    '### 7. Restart with the same pinned bytes', '### 8. Deactivation', '## Stop',
                    '## Worker-direct fallback (D1)', '## Known limits', '## Offline verification and pending checks'):
        assert '\n' + heading + '\n' in document, heading
    # Exit table: every status the unit can see is a row.
    table = document.split('Exit statuses seen by systemd:')[1].split('\n\n')[1]
    assert [row.split('|')[1].strip() for row in table.splitlines()[2:]] == [
        '0', '1', '78', '`ExecCondition` 1', 'status of `ExecStartPre`', '125, 126, 127', '137', '143']
    # The times of the daily contract are the launcher's constants.
    script = launcher()
    assert (script.HANDOVER_BEFORE_OPEN_SECONDS, script.READY_DEADLINE_BEFORE_OPEN_SECONDS, script.STOP_AFTER_CLOSE_SECONDS,
            script.PRE_OPEN_SECONDS) == (90, 10, 1200, 21600)
    assert all(phrase in document for phrase in ('09:28:30 (open − 90 s)', '09:29:50 (open − 10 s)',
        'close + 20 min (16:20:00)', 'open − 6 h … close + 20 min', "`APP_ROOT = '/app'`"))


def test_the_document_places_the_journal_outside_the_data_volume_and_states_its_guards():
    from app import r2d2_v2_massive_producer as producer
    document = text('README.md'); unit = text('c3po-reader.service')
    # The placeholder table is the unit: seven names, each with its count.
    assert '| `c3po-reader.service` | `/etc/systemd/system/c3po-reader.service`, rendered | seven |' in document
    table = dict(re.findall(r'^\| `(@[A-Z_]+@)` \| (\d+) \|', document, re.M))
    assert table == {name: str(unit.count(name)) for name in PLACEHOLDERS} and len(table) == 7
    section = document.split('\n## Journal root\n')[1].split('\n## ')[0]
    assert all(phrase in section for phrase in (
        '**not inside the data volume**', "the host's **root filesystem**", '`/var/lib/c3po-bar/journal`',
        'Nothing is deleted or moved', 'its journal bind is the producer\'s own `--mount` line with `,readonly` appended',
        'never typed a second time', '**Why a child of `/`.**', '**Effective filesystem.**',
        '**Ownership under `--cap-drop ALL`.**', 'The producer unit runs `--user 0:0`', 'reads them **as their owner**',
        'uid 1000, mode 0755', '`r2d2_v2_massive_producer.py` lines 61–62', '*(unverified)*'))
    # The figures of the decision are the producer's constants, for the five sessions of the epoch.
    per_session = producer.MAX_SESSION_EVIDENCE_BYTES + producer.MAX_SESSION_INDEX_BYTES
    assert (producer.MIN_SESSION_FREE_BYTES, per_session, len(SESSIONS)) == (53687091200, 603979776, 5)
    assert producer.MIN_SESSION_FREE_BYTES + len(SESSIONS) * per_session == 56706990080
    assert all(str(number) in section for number in (53687091200, 56706990080))
    source = (BACKEND / 'app' / 'r2d2_v2_massive_producer.py').read_text().splitlines()
    assert 'os.fstatvfs(directory)' in source[60] and 'f_bavail*capacity.f_frsize' in source[61]
    # The guards of the installation, of the pins and of the activation name the same checks.
    install = document.split('\n### 2. Unit installation (no activation, no overwrite)\n')[1].split('\n### ')[0]
    pins = document.split('\n### 3. Pins\n')[1].split('\n### ')[0]
    activation = document.split('\n### 4. Activation\n')[1].split('\n### ')[0]
    assert all(phrase in install for phrase in (
        'the producer unit is installed', 'Without an installed producer unit the installation refuses',
        '`findmnt -n -o TARGET,SOURCE,FSTYPE --target @HOST_JOURNAL_ROOT@`', '`stat -c %d @HOST_JOURNAL_ROOT@`',
        '**differs** from `stat -c %d @HOST_DATA_ROOT@`', '`root:root`, mode 0700', '**isolation:**',
        'validates the seven values against the grammar'))
    assert 'equals the `@CONTAINER_JOURNAL_ROOT@` value of the installed producer unit' in pins
    assert 'is not under `/app/day-d-data`' in pins and 'journal leaf' not in document
    assert all(phrase in activation for phrase in (
        '**parameters and mounts:**', '**effective filesystem:**', '**ownership:**', '**catalog binding:**',
        '**free space, revalidated:**', "`stat -c '%d %i' @HOST_JOURNAL_ROOT@`", '`f_bavail × f_frsize` of `statvfs`',
        '53687091200', '603979776', '56706990080', 'the device number differs from the data volume\'s'))
    # Nothing in the document still places the journal in the data volume, except where it names the earlier layout.
    for line in document.splitlines():
        if 'journal' in line.lower() and '/app/day-d-data/<leaf>' in line:
            assert 'earlier' in line, line
    assert 'the same inode, as the producer\'s journal root. The reader takes' not in document
    assert 'all four mounts are read-only' in document and '**Four read-only binds**' in document
