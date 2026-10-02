"""Pins the three pipeline steps that exercise the reader unit and the capacity-day manifest writer on the
runner's Docker engine, and runs offline everything in them that needs no engine.

Offline here means: the workflow is parsed, the shell text of each step is checked with `bash -n`, and the Python
programs embedded in the steps are extracted and run for real against the checkout (the unit render, the mount
check, the three receipt checks, and the stop driver with a real launcher process and a real SIGTERM). No docker command of the
steps is run by this file: what the steps prove on an engine exists only after a pipeline run.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import date, timedelta

import pytest
import yaml

from app.config import Settings
from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_epoch_assembler import SESSIONS

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parents[1]
PIPELINE = ROOT / '.github' / 'workflows' / 'c3po-pipeline.yml'
READER = BACKEND.parent / 'deployment' / 'reader'
CAPACITY_DAY = BACKEND.parent / 'deployment' / 'capacity-day'
SUPERVISOR = 'Exercise the Massive supervisor unit against the backend image'
REFUSAL = 'Exercise the reader unit refusal against the backend image'
STOP = 'Exercise the reader stop against the backend image'
WRITER = 'Exercise the manifest writer off path against the backend image'
UPLOAD = 'Publish backend runtime check'
NEW_STEPS = (REFUSAL, STOP, WRITER)
ARTEFACTS = {REFUSAL: 'reader-refusal', STOP: 'reader-stop', WRITER: 'writer-off'}
IMAGE = 'sha256:' + 'ab' * 32
MARKER = 'c3po-reader-stand-in-worker'
ACTIVATION_SHA = '2053f3f6f528ad7dc56d500666ac2cf48f79c3aadd3c98eb35b53ee92eff611b'
CEILING_SECONDS = 90.0
JOURNAL = '/c3po-journal'                 # the container journal root of the smoke: a child of '/', outside the data bind
DATA_NAMES = ['C3PO_R2D2_V2_SHADOW_RELEASE_FILE', 'C3PO_R2D2_V2_SHADOW_SOURCE_DIR', 'C3PO_R2D2_MICROSTRUCTURE_RAW_DIR']


def steps():
    workflow = yaml.safe_load(PIPELINE.read_text(encoding='utf-8'))
    return workflow['jobs']['frontend-build']['steps']


def step(name):
    found, = [item for item in steps() if item.get('name') == name]
    return found


def raw(name):
    """The step as written, comments included (the parsed form has no comments)."""
    text = PIPELINE.read_text(encoding='utf-8')
    start = text.index('      - name: ' + name + '\n')
    return text[start:text.index('\n      - name: ', start + 1)]


def programs(name):
    """(the shell line that starts it, the program) for every Python program embedded in a step, in order."""
    lines = step(name)['run'].split('\n'); found = []; index = 0
    while index < len(lines):
        if lines[index].rstrip().endswith("<<'PY'") or "<<'PY' ||" in lines[index]:
            end = lines.index('PY', index + 1)
            found.append((lines[index].strip(), '\n'.join(lines[index + 1:end]) + '\n'))
            index = end
        index += 1
    return found


def program(name, starts):
    body, = [body for head, body in programs(name) if head.startswith(starts)]
    return body


def run_program(body, *arguments, cwd=ROOT):
    return subprocess.run([sys.executable, '-B', '-', *map(str, arguments)], input=body, cwd=str(cwd),
        capture_output=True, text=True, timeout=CEILING_SECONDS)


def render(tmp_path, name, flag, pin='c' * 64, cwd=ROOT):
    """Runs the render program of a reader step as the step does. (result, out directory, stage directory)."""
    out = tmp_path / ('out-' + flag); stage = tmp_path / ('stage-' + flag)
    out.mkdir(); stage.mkdir()
    done = run_program(program(name, 'python3 - "$id" "$base" "$out" "$stage"'), IMAGE, '/throwaway', out, stage,
        ARTEFACTS[name], pin, flag, cwd=cwd)
    return done, out, stage


def environment(stage, pins='pins'):
    """What the docker CLI would hand the container from the three files, in the order of the unit."""
    values = {}
    for name in ('secret', pins, 'activation'):
        for line in (stage / (name + '.env')).read_text().splitlines():
            key, separator, value = line.partition('=')
            assert separator == '=' and key not in values and re.fullmatch(r'C3PO_[A-Z0-9_]+', key)
            values[key] = value
    return values


def readme_block(name):
    found = re.search(r'<!-- %s:begin -->\n```\n(.*?)```\n<!-- %s:end -->' % (name, name), (READER / 'README.md').read_text(), re.S)
    assert found is not None
    return found.group(1)


# ---------------------------------------------------------------- the three steps in the workflow

def test_the_three_steps_follow_the_supervisor_step_and_precede_the_artefact_upload():
    listed = steps(); names = [item.get('name') for item in listed]
    at = names.index(SUPERVISOR)
    # The compose capacity-mount render (PR #437) sits between the supervisor step and these three.
    assert names[at:at + 6] == [SUPERVISOR, 'Render the compose capacity mount on a real engine', REFUSAL, STOP, WRITER, UPLOAD]
    built = step('Validate production Docker images')
    assert '--tag c3po/backend:pr-validation' in built['run']
    for name in NEW_STEPS:
        item = step(name)
        # Skipped exactly when the image they run was not built; never soft-failed; never fed a secret.
        assert item['if'] == built['if'] == step(SUPERVISOR)['if']
        assert set(item) == {'name', 'if', 'working-directory', 'timeout-minutes', 'shell', 'run'}
        assert (item['shell'], item['timeout-minutes'], item['working-directory']) == ('bash', 5, '${{ github.workspace }}')
        text = raw(name)
        assert not any(word in text for word in ('continue-on-error', 'secrets.', 'MASSIVE_API_KEY', 'postgres'))
        assert not re.search(r'^\s+env:', text, re.M)
        assert '${{' not in item['run'] and 'c3po/backend:pr-validation' in item['run']
    upload = step(UPLOAD)
    assert upload['if'].startswith('always() &&') and upload['with']['path'] == '${{ runner.temp }}/backend-runtime'


@pytest.mark.parametrize('name', NEW_STEPS)
def test_each_step_is_valid_shell_guards_explicitly_and_prints_its_artefacts_on_failure(name):
    script = step(name)['run']; prefix = ARTEFACTS[name]
    lines = script.splitlines()
    assert lines[:3] == ['set -uo pipefail', 'out="$RUNNER_TEMP/backend-runtime"', 'mkdir -p "$out" || exit 1']
    assert not re.search(r'^\s*set -[a-z]*e', script, re.M) and 'Every guard is explicit' in raw(name)
    # One function prints every text artefact of the step; every failure goes through it.
    assert 'for item in "$out"/%s-*.txt "$out"/%s-*.log; do' % (prefix, prefix) in script
    assert re.search(r'^fail\(\) \{ echo "\$1" >&2; show >&2; exit 1; \}$', script, re.M) or (
        'fail() {\n  echo "$1" >&2; show >&2\n  docker rm --force c3po-reader > /dev/null 2>&1 || true\n  exit 1\n}' in script)
    assert script.count('|| fail "') >= 12
    # Every artefact the step writes carries the step's prefix, inside the uploaded directory.
    written = re.findall(r'\$out/([A-Za-z0-9$._-]+)', script)
    assert len(written) >= 5 and all(name.startswith(prefix + '-') for name in written)
    assert ('out + "/" + prefix + "-"' in script) == (name != WRITER)
    bash = shutil.which('bash')
    if bash is None:
        pytest.skip('no bash on this machine')
    checked = subprocess.run([bash, '-n'], input=script, capture_output=True, text=True, timeout=CEILING_SECONDS)
    assert (checked.returncode, checked.stderr) == (0, '')
    for head, body in programs(name):
        compile(body, head, 'exec')


def test_the_refusal_step_runs_the_rendered_unit_and_requires_one_documented_refusal():
    text = raw(REFUSAL)
    assert all(value in text for value in (
        'c3po/deployment/reader/c3po-reader.service', 'launcher=c3po/deployment/reader/reader_launcher.py',
        "docker image inspect --format '{{.Id}}' c3po/backend:pr-validation", '^sha256:[0-9a-f]{64}$',
        'pin="$(sha256sum "$launcher" | cut -d \' \' -f 1)"',
        'sudo install -d -m 0700 -o 0 -g 0 "$base/data" "$base/journal" "$base/capacity" "$base/etc"',
        '"$base/etc/docker-cli" "$base/etc/launcher"', '"@NETWORK@": "none"',
        '"@HOST_JOURNAL_ROOT@": base + "/journal"', '"@CONTAINER_JOURNAL_ROOT@": "%s"' % JOURNAL,
        '(values["@HOST_JOURNAL_ROOT@"], values["@CONTAINER_JOURNAL_ROOT@"])',
        '"C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR=" + values["@CONTAINER_JOURNAL_ROOT@"]',
        'rendered ExecStart does not have exactly the four read-only binds', '[ "${#argv[@]}" -ge 46 ] ||',
        'python3 - "$id" "$base" "$out" "$stage" reader-refusal "$pin" false <<\'PY\'',
        'sudo install -m 0600 -o 0 -g 0 "$launcher" "$base/etc/launcher/reader_launcher.py"',
        'sudo install -m 0600 -o 0 -g 0 "$stage/$name.env" "$base/etc/$name.env"',
        'sudo /usr/bin/test -f "$base/etc/$name.env"',
        'seen="$(sudo env "DOCKER_CONFIG=$base/etc/docker-cli" "${check[@]}")"', '[ "$seen" = "$id" ] ||',
        'sudo env "DOCKER_CONFIG=$base/etc/docker-cli" "${argv[@]}" \\',
        '[ "$rc" -eq 78 ] ||', 'if len(lines) != 1:', 'event["status"] != "REFUSED"',
        'refusal flags-off READER_SESSION READER_WINDOW READER_DISABLED ||',
        'sudo install -m 0600 -o 0 -g 0 "$stage/pins-other.env" "$base/etc/pins.env"',
        'refusal other-pin READER_LAUNCHER_PIN ||',
        'sudo find "$base/data" "$base/journal" "$base/capacity" -mindepth 1', "docker ps -a --filter 'name=^c3po-reader$' -q"))
    # The container journal root is written once and reused: no step names a journal under the data bind.
    for name in (REFUSAL, STOP):
        assert step(name)['run'].count('"%s"' % JOURNAL) == 1 and '/app/day-d-data/smoke/journal' not in raw(name)
        assert 'C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR=/' not in raw(name)
        # Both steps refuse a rendered start shorter than the one with the journal bind (46 elements).
        assert step(name)['run'].count('[ "${#argv[@]}" -ge 46 ] || fail "rendered ExecStart is too short"') == 1
        assert not re.search(r'#argv\[@\]\}" -ge (?!46 )', step(name)['run'])
    # The comment says what is bound: three directories and the launcher subdirectory, never the configuration directory.
    assert all(phrase in text for phrase in (
        '# database: throwaway root-owned 0700 directories; data, journal and capacity are bound',
        '# read-only, the journal one at the container journal root that pins.env names, and of',
        '# the configuration directory only its launcher subdirectory is bound, read-only (the',
        '# configuration directory itself is never mounted)'))
    assert 'each bound read-only' not in text
    assert '(values["@HOST_CONFIG_DIR@"] + "/launcher", "/c3po-reader")' in text
    # The start is the rendered argument list, unchanged: nothing is appended to it and nothing is replaced in it.
    script = step(REFUSAL)['run']
    assert not re.search(r'^\s*argv(\[[^\]]*\])?\+?=', script, re.M) and '--env ' not in script
    assert re.search(r'^\s*argv(\[[^\]]*\])?\+?=', step(STOP)['run'], re.M)       # the pattern does see a replacement
    # The codes the step accepts are refusals of the launcher, and each is in its document.
    source = (READER / 'reader_launcher.py').read_text(); document = (READER / 'README.md').read_text()
    for code in ('READER_SESSION', 'READER_WINDOW', 'READER_DISABLED', 'READER_LAUNCHER_PIN'):
        assert "'%s'" % code in source and '`%s`' % code in document
    assert 'READER_SETTINGS_INVALID' not in text and 'TERMINAL_EXIT = 78' in source


def test_the_stop_step_stops_the_rendered_start_with_the_rendered_stop():
    text = raw(STOP); script = step(STOP)['run']
    assert all(value in text for value in (
        'python3 - "$id" "$base" "$out" "$stage" reader-stop "$pin" true <<\'PY\'',
        'marker=' + MARKER, 'command -v pgrep > /dev/null ||',
        'cat > "$stage/stop_driver.py" <<\'PY\'',
        '[ "${argv[$last]}" = /c3po-reader/reader_launcher.py ] ||', 'argv[$last]=/c3po-reader/stop_driver.py',
        'sudo install -m 0600 -o 0 -g 0 "$stage/stop_driver.py" "$base/etc/launcher/stop_driver.py"',
        '> "$out/reader-stop-stdout.log" 2> "$out/reader-stop-stderr.log" &', 'runner=$!',
        'docker top c3po-reader > "$out/reader-stop-top.txt"', '[ "$(grep -c -- "$marker" "$out/reader-stop-top.txt")" -eq 1 ]',
        'sudo kill -0 "$runner"', "docker inspect --format '{{.HostConfig.Init}}' c3po-reader", '[ "$init" = true ] ||',
        "docker inspect --format '{{json .Mounts}}' c3po-reader > \"$out/reader-stop-mounts.txt\"",
        'python3 - "$out/reader-stop-argv.bin" "$out/reader-stop-mounts.txt" <<\'PY\' '
        '|| fail "the engine does not list the four read-only binds of the rendered unit"',
        '|| fail "the mounts of the container could not be read"',
        '[ "${#argv[@]}" -ge 46 ] || fail "rendered ExecStart is too short"',
        'sudo install -d -m 0700 -o 0 -g 0 "$base/data" "$base/journal" "$base/capacity" "$base/etc"',
        'sudo find "$base/data" "$base/journal" "$base/capacity" -mindepth 1',
        'sudo env "DOCKER_CONFIG=$base/etc/docker-cli" "${stop[@]}" > "$out/reader-stop-docker-stop.log" 2>&1',
        'wait "$runner" || rc=$?', '[ "$rc" -eq 0 ] ||', '[ "$elapsed" -lt 20 ] ||',
        '!= ["STARTING", "STOPPED"]', '"child_signal": "SIGTERM"', '"killed": False', '"launcher_pinned": True',
        "docker ps -a --filter 'name=^c3po-reader$' -q", 'if pgrep -f -- "$marker" > "$out/reader-stop-left.txt"; then'))
    # Exactly one element of the rendered start is replaced, and the container is stopped only by the unit's own line.
    assert script.count('argv[$last]=') == 1 and script.count('"${stop[@]}"') == 1
    # The engine's list of mounts is read while the container runs: after the stand-in is seen, before the stop.
    assert script.index('[ "$running" -eq 1 ] ||') < script.index('{{json .Mounts}}') < script.index('"${stop[@]}"')
    assert 'docker stop' not in script.replace('after docker stop', '').replace('"docker", "stop"', '')
    assert 'docker kill' not in script and script.count('docker rm --force c3po-reader') == 1
    driver = program(STOP, 'cat > "$stage/stop_driver.py"')
    assert '"%s"' % MARKER in driver and driver.count('launcher.main(') == 1
    assert 'launcher.main([], utcnow=lambda: frozen, child_argv=stand_in)' in driver
    # The driver touches the launcher only through its two documented test seams.
    source = (READER / 'reader_launcher.py').read_text()
    assert 'def main(argv=None, *, utcnow=None, child_argv=None):' in source
    assert not re.search(r'(?<!\w)launcher\.(?!main\(|APP_ROOT\b)\w+', driver)


def test_the_writer_step_feeds_the_script_on_standard_input_with_the_shadow_flag_off():
    text = raw(WRITER); script = step(WRITER)['run']
    block = re.search(r'^argv=\((.*?)\)$', script, re.S | re.M)
    assert block is not None
    argv = shlex.split(block.group(1).replace('$base', '/throwaway').replace('$id', IMAGE))
    assert argv == ['/usr/bin/docker', 'run', '--rm', '-i', '--name', 'c3po-capacity-day-smoke', '--pull', 'never', '--init',
        '--user', '0:0', '--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--mount', 'type=bind,source=/throwaway/manifests,target=/etc/c3po-bar/manifests',
        '--env', 'C3PO_R2D2_V2_SHADOW_ENABLED=false',
        IMAGE, 'python', '-I', '-B', '-', '--day', '2026-10-05', '--manifest-directory', '/etc/c3po-bar/manifests']
    assert all(value in text for value in (
        'script=c3po/deployment/capacity-day/manifest_writer.py',
        'sudo install -d -m 0700 -o 0 -g 0 "$base/manifests" "$base/docker-cli"',
        'sudo env "DOCKER_CONFIG=$base/docker-cli" "${argv[@]}" < "$script" \\',
        '> "$out/writer-off-stdout.log" 2> "$out/writer-off-stderr.log" || rc=$?',
        '[ "$rc" -eq 3 ] ||', '[ ! -s "$out/writer-off-stderr.log" ] ||', '"code": "MANIFEST_SHADOW_OFF"',
        'sudo find "$base/manifests" -mindepth 1', "docker ps -a --filter 'name=^c3po-capacity-day-smoke$' -q"))
    # The code and the exit status are the documented ones, and the documented run form is the one used.
    document = (CAPACITY_DAY / 'README.md').read_text(); source = (CAPACITY_DAY / 'manifest_writer.py').read_text()
    assert 'one line, `MANIFEST_SHADOW_OFF`, exit 3' in document and 'python -I -B - <arguments> < manifest_writer.py' in document
    assert "need(getattr(settings, 'r2d2_v2_shadow_enabled', False), 'MANIFEST_SHADOW_OFF')" in source
    assert 'EXIT_OK, EXIT_UNVERIFIED, EXIT_REFUSED = 0, 1, 3' in source
    assert Settings.model_fields['r2d2_v2_shadow_enabled'].default is False


# ---------------------------------------------------------------- the embedded programs, run for real

def test_both_reader_steps_embed_the_same_render_and_it_renders_the_unit_and_the_three_files(tmp_path):
    head = 'python3 - "$id" "$base" "$out" "$stage"'
    assert program(REFUSAL, head) == program(STOP, head)
    done, out, stage = render(tmp_path, REFUSAL, 'false')
    assert (done.returncode, done.stdout, done.stderr) == (0, '', '')
    unit = (READER / 'c3po-reader.service').read_text()
    values = {'@IMAGE_ID@': IMAGE, '@HOST_DATA_ROOT@': '/throwaway/data', '@HOST_JOURNAL_ROOT@': '/throwaway/journal',
              '@CONTAINER_JOURNAL_ROOT@': JOURNAL, '@HOST_CAPACITY_ROOT@': '/throwaway/capacity',
              '@HOST_CONFIG_DIR@': '/throwaway/etc', '@NETWORK@': 'none'}
    assert set(values) == set(re.findall(r'@[A-Z_]+@', unit))
    for name, value in values.items():
        unit = unit.replace(name, value)
    start, = [line for line in unit.replace('\\\n', ' ').splitlines() if line.startswith('ExecStart=')]

    def argv(name):
        items = (out / ('reader-refusal-' + name + '.bin')).read_text().split('\0')
        assert items[-1] == ''
        return items[:-1]

    assert argv('argv') == shlex.split(start[len('ExecStart='):]) and len(argv('argv')) == 46
    # Four binds, each read-only: the journal directory at the container journal root, outside the data bind.
    binds = [argv('argv')[at + 1] for at, value in enumerate(argv('argv')) if value == '--mount']
    assert binds == ['type=bind,source=/throwaway/data,target=/app/day-d-data,readonly',
                     'type=bind,source=/throwaway/journal,target=%s,readonly' % JOURNAL,
                     'type=bind,source=/throwaway/capacity,target=/c3po-capacity,readonly',
                     'type=bind,source=/throwaway/etc/launcher,target=/c3po-reader,readonly']
    assert argv('argv')[-4:] == ['python', '-I', '-B', '/c3po-reader/reader_launcher.py']
    assert argv('check-argv') == ['/usr/bin/docker', 'image', 'inspect', '--format', '{{.Id}}', IMAGE]
    assert argv('stop-argv') == ['/usr/bin/docker', 'stop', '-t', '25', 'c3po-reader']
    assert sorted(entry.name for entry in out.iterdir()) == ['reader-refusal-argv.bin', 'reader-refusal-check-argv.bin',
                                                              'reader-refusal-stop-argv.bin']
    assert sorted(entry.name for entry in stage.iterdir()) == ['activation.env', 'pins-other.env', 'pins.env', 'secret.env']
    # The three files have the documented names in the documented order; the database line has no value.
    assert (stage / 'secret.env').read_text() == 'C3PO_DATABASE_URL=\n'
    documented = [line.split('=', 1)[0] for line in readme_block('pins-env').splitlines()]
    pins = (stage / 'pins.env').read_text().splitlines()
    assert [line.split('=', 1)[0] for line in pins] == documented and pins[-1] == 'C3PO_READER_LAUNCHER_SHA256=' + 'c' * 64
    # The journal directory of pins.env is the target of the journal bind, never a leaf of the data bind; the release
    # file and the two source directories are the only values still under /app/day-d-data.
    assert pins[documented.index('C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR')] == 'C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR=' + JOURNAL
    assert [line.split('=', 1)[0] for line in pins if '/app/day-d-data' in line] == DATA_NAMES
    # The smoke's container journal root is inside the grammar of the document, which the document states.
    assert re.fullmatch(r'/c3po-[a-z0-9][a-z0-9-]*', JOURNAL) and JOURNAL not in ('/c3po-capacity', '/c3po-reader')
    assert len(Path(JOURNAL).parts) == 2 and '`^/c3po-[a-z0-9][a-z0-9-]*$`' in (READER / 'README.md').read_text()
    other = (stage / 'pins-other.env').read_text().splitlines()
    assert other[:-1] == pins[:-1] and other[-1] == 'C3PO_READER_LAUNCHER_SHA256=' + '0' * 64
    assert (stage / 'activation.env').read_text() == readme_block('activation-env').replace('=true', '=false')
    # With the flag on, the activation file is the constant bytes of the document.
    done, _, stage_on = render(tmp_path, STOP, 'true')
    assert done.returncode == 0 and (stage_on / 'activation.env').read_text() == readme_block('activation-env')
    assert hashlib.sha256((stage_on / 'activation.env').read_bytes()).hexdigest() == ACTIVATION_SHA
    # It never overwrites a file of an earlier run, and it refuses a pin or a flag outside its grammar.
    assert run_program(program(REFUSAL, head), IMAGE, '/throwaway', out, stage, 'reader-refusal', 'c' * 64, 'false').returncode == 1
    for pin, flag in (('C' * 64, 'false'), ('c' * 63, 'false'), ('c' * 64, 'True')):
        fresh = tmp_path / ('refused-' + pin[:1] + str(len(pin)) + flag); fresh.mkdir()
        refused = run_program(program(REFUSAL, head), IMAGE, '/throwaway', fresh, fresh, 'reader-refusal', pin, flag)
        assert refused.returncode == 1 and list(fresh.iterdir()) == []


@pytest.mark.parametrize('old,new,message', [
    ('ExecCondition=/usr/bin/test -f @HOST_CONFIG_DIR@/activation.env\n', '', '3 ExecCondition line'),
    ('--env-file @HOST_CONFIG_DIR@/pins.env \\\n', '--env-file @HOST_CONFIG_DIR@/other.env \\\n', 'three environment files'),
    ('python -I -B /c3po-reader/reader_launcher.py', 'python -B -m app.r2d2_v2_shadow_worker', 'launcher command'),
    ('--init ', '', 'docker run --init'),
    ('ExecStop=-/usr/bin/docker stop -t 25 c3po-reader', 'ExecStop=-/usr/bin/docker kill c3po-reader', 'stop of the reader'),
    ('--network @NETWORK@', '--network @NETWORK@ --label x=@OTHER@', 'seven documented substitutions'),
    # The journal bind: removed, read-write, under the data bind, from another source, or joined by a fifth bind.
    ('  --mount type=bind,source=@HOST_JOURNAL_ROOT@,target=@CONTAINER_JOURNAL_ROOT@,readonly \\\n', '', 'seven documented substitutions'),
    ('target=@CONTAINER_JOURNAL_ROOT@,readonly', 'target=@CONTAINER_JOURNAL_ROOT@', 'four read-only binds'),
    ('target=@CONTAINER_JOURNAL_ROOT@,readonly', 'target=/app/day-d-data@CONTAINER_JOURNAL_ROOT@,readonly', 'four read-only binds'),
    ('source=@HOST_JOURNAL_ROOT@,', 'source=@HOST_DATA_ROOT@/journal,', 'four read-only binds'),
    ('target=/c3po-capacity,readonly', 'target=/c3po-capacity,readonly --mount type=bind,source=@HOST_JOURNAL_ROOT@,target=/extra',
     'four read-only binds'),
    ('ExecStartPre=/usr/bin/docker image inspect', 'ExecStartPre=-/usr/bin/docker image inspect', '1 ExecStartPre line'),
])
def test_the_render_refuses_a_unit_that_is_no_longer_the_documented_one(tmp_path, old, new, message):
    tree = tmp_path / 'tree'; target = tree / 'c3po' / 'deployment' / 'reader'
    target.mkdir(parents=True)
    unit = (READER / 'c3po-reader.service').read_text()
    assert unit.count(old) == 1
    (target / 'c3po-reader.service').write_text(unit.replace(old, new))
    done, out, stage = render(tmp_path, REFUSAL, 'false', cwd=tree)
    assert done.returncode == 1 and message in done.stderr
    assert list(out.iterdir()) == [] and list(stage.iterdir()) == []


def load_launcher():
    import importlib.util
    spec = importlib.util.spec_from_file_location('c3po_reader_launcher_for_pipeline', READER / 'reader_launcher.py')
    module = importlib.util.module_from_spec(spec)
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def test_the_smoke_environment_loads_in_the_real_settings_and_ends_in_the_accepted_refusals(tmp_path, monkeypatch):
    """Inside a session window the unmodified launcher reads the settings. With the files of the refusal step
    that must end in READER_DISABLED, never in READER_SETTINGS_INVALID, which the step does not accept."""
    done, _, stage = render(tmp_path, REFUSAL, 'false')
    assert done.returncode == 0
    launcher = load_launcher(); calendar = ShadowCalendar()
    for key in [key for key in os.environ if key.startswith('C3PO_')]:
        monkeypatch.delenv(key)

    def end(pins, now, pin_of_file='c' * 64):
        values = environment(stage, pins)
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        notices = []
        status = launcher.supervise(utcnow=lambda: now, sleep=pytest.fail, notice=notices.append, spawn=pytest.fail,
            calendar=calendar, sessions=SESSIONS, settings=Settings, stop_requested=lambda: False,
            launcher_sha=pin_of_file, launcher_pin=values[launcher.LAUNCHER_PIN_ENV])
        (notice,) = notices
        assert status == 78 and set(notice) == {'status', 'code', 'restart_allowed', 'session', 'at'}
        return notice['code']

    settings_names = {name[len('C3PO_'):].lower() for name in environment(stage) if name != launcher.LAUNCHER_PIN_ENV}
    assert settings_names <= set(Settings.model_fields) and len(settings_names) == 14
    assert environment(stage)['C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR'] == JOURNAL
    first = date.fromisoformat(sorted(SESSIONS)[0]); opened = calendar.details(first)['open']
    assert end('pins', opened - timedelta(hours=1)) == 'READER_DISABLED'
    assert end('pins', opened + timedelta(hours=1)) == 'READER_DISABLED'
    assert end('pins', opened - timedelta(hours=7)) == 'READER_WINDOW'
    assert end('pins', opened - timedelta(days=2)) == 'READER_SESSION'
    # The other pin is refused before the day is looked at, whatever the clock.
    for now in (opened - timedelta(hours=1), opened - timedelta(days=2)):
        assert end('pins-other', now) == 'READER_LAUNCHER_PIN'


def test_the_mount_check_of_the_stop_step_accepts_only_the_four_read_only_binds_of_the_render(tmp_path):
    """The check reads the rendered argument list and the engine's list of mounts. The list here has the shape
    `docker inspect --format '{{json .Mounts}}'` prints; what a real engine prints is seen only in a pipeline run."""
    done, out, _ = render(tmp_path, STOP, 'true')
    assert done.returncode == 0
    check = program(STOP, 'python3 - "$out/reader-stop-argv.bin" "$out/reader-stop-mounts.txt"')
    rendered = out / 'reader-stop-argv.bin'

    def bind(source, target, writable=False):
        return {'Type': 'bind', 'Source': source, 'Destination': target, 'Mode': '', 'RW': writable, 'Propagation': 'rprivate'}

    engine = [bind('/throwaway/data', '/app/day-d-data'), bind('/throwaway/journal', JOURNAL),
              bind('/throwaway/capacity', '/c3po-capacity'), bind('/throwaway/etc/launcher', '/c3po-reader')]
    tmpfs = {'Type': 'tmpfs', 'Source': '', 'Destination': '/tmp', 'Mode': '', 'RW': True, 'Propagation': ''}

    def judged(listed, argv=rendered):
        path = tmp_path / ('mounts-%d.txt' % len(list(tmp_path.iterdir())))
        path.write_text(listed if isinstance(listed, str) else json.dumps(listed) + '\n')
        return run_program(check, argv, path).returncode

    assert judged(engine) == 0 and judged(list(reversed(engine)) + [tmpfs]) == 0
    journal = engine[1]
    for other in ([engine[0]] + engine[2:],                                                     # no journal bind
                  [engine[0], {**journal, 'RW': True}] + engine[2:],                            # writable
                  [engine[0], {**journal, 'Destination': '/app/day-d-data/journal'}] + engine[2:],   # under the data bind
                  [engine[0], {**journal, 'Source': '/throwaway/data/journal'}] + engine[2:],   # another directory
                  engine + [bind('/throwaway/etc', '/etc/c3po-reader')],                        # a fifth bind
                  [{**item, 'RW': True} for item in engine], [], 'not json'):
        assert judged(other) != 0, other
    # A rendered start whose journal bind lost `readonly` is refused whatever the engine lists.
    items = rendered.read_text().split('\0')
    at = items.index('type=bind,source=/throwaway/journal,target=%s,readonly' % JOURNAL)
    for changed in (items[at][:-len(',readonly')], items[at] + ',bind-propagation=shared', items[at].replace('type=bind', 'type=volume')):
        loose = tmp_path / ('argv-%d.bin' % len(list(tmp_path.iterdir())))
        loose.write_text('\0'.join(items[:at] + [changed] + items[at + 1:]))
        assert judged([engine[0], {**journal, 'RW': changed.endswith(JOURNAL)}] + engine[2:], argv=loose) != 0, changed
    fewer = tmp_path / 'argv-fewer.bin'
    fewer.write_text('\0'.join(items[:at - 1] + items[at + 1:]))
    assert judged([engine[0]] + engine[2:], argv=fewer) != 0


def sample(tmp_path, name, *lines):
    path = tmp_path / name
    path.write_text(''.join(line + '\n' for line in lines))
    return path


def test_the_refusal_check_accepts_exactly_one_refusal_line_with_a_listed_code(tmp_path):
    check = program(REFUSAL, 'python3 - "$out/reader-refusal-$name-stdout.log" "$@"')
    notice = {'status': 'REFUSED', 'code': 'READER_SESSION', 'restart_allowed': False, 'session': '2026-10-01',
              'at': '2026-10-02T00:47:14+00:00'}
    codes = ('READER_SESSION', 'READER_WINDOW', 'READER_DISABLED')

    def judged(*lines, accepted=codes):
        return run_program(check, sample(tmp_path, 'notices-%d.log' % len(list(tmp_path.iterdir())), *lines), *accepted)

    good = judged(json.dumps(notice, sort_keys=True))
    assert (good.returncode, good.stdout) == (0, 'refusal code: READER_SESSION\n')
    assert judged(json.dumps({**notice, 'code': 'READER_DISABLED'})).returncode == 0
    assert judged(json.dumps({**notice, 'code': 'READER_LAUNCHER_PIN'}), accepted=('READER_LAUNCHER_PIN',)).returncode == 0
    for lines in ([], [json.dumps(notice)] * 2, [json.dumps({**notice, 'code': 'READER_LAUNCHER_PIN'})],
                  [json.dumps({**notice, 'code': 'READER_SETTINGS_INVALID'})], [json.dumps({**notice, 'status': 'FAILED'})],
                  [json.dumps({**notice, 'restart_allowed': True})], [json.dumps({**notice, 'phase': 'PRE_OPEN'})],
                  [json.dumps({key: value for key, value in notice.items() if key != 'session'})], ['not json']):
        assert judged(*lines).returncode != 0, lines
    assert judged(json.dumps(notice), accepted=('READER_LAUNCHER_PIN',)).returncode != 0


def children_of(pid):
    # One -o per column: procps reads `pid=,ppid=,args=` as a single column whose header is the rest of the text.
    listed = subprocess.run(['ps', '-A', '-ww', '-o', 'pid=', '-o', 'ppid=', '-o', 'args='], capture_output=True,
                            text=True, timeout=30).stdout
    found = []
    for line in listed.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[1] == str(pid):
            found.append((int(parts[0]), parts[2]))
    return found


def test_the_stop_driver_and_the_notice_check_of_the_step_on_a_real_launcher_process(tmp_path):
    """The driver exactly as the step writes it, beside a launcher whose only edit is the application root, started
    as the unit's command starts it (`python -I -B <file>`), with the environment of the three rendered files and
    stopped by a real SIGTERM. The engine, docker-init and the image are what this cannot stand in for."""
    mounted = tmp_path / 'launcher'; mounted.mkdir()
    source = (READER / 'reader_launcher.py').read_text()
    assert source.count("APP_ROOT = '/app'\n") == 1
    (mounted / 'reader_launcher.py').write_text(source.replace("APP_ROOT = '/app'\n", 'APP_ROOT = %r\n' % str(BACKEND)))
    (mounted / 'stop_driver.py').write_text(program(STOP, 'cat > "$stage/stop_driver.py"'))
    pin = hashlib.sha256((mounted / 'reader_launcher.py').read_bytes()).hexdigest()
    done, _, stage = render(tmp_path, STOP, 'true', pin=pin)
    assert done.returncode == 0
    # The listing must see a known child before anything is started: the stand-in sleeps for an hour.
    assert os.getpid() in [pid for pid, _ in children_of(os.getppid())]
    keep = {key: value for key, value in os.environ.items() if not key.startswith(('C3PO_', 'PYTHON'))}
    parent = subprocess.Popen([sys.executable, '-I', '-B', str(mounted / 'stop_driver.py')], cwd=str(tmp_path),
        env={**keep, **environment(stage)}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    child = None
    try:
        deadline = time.monotonic() + CEILING_SECONDS
        while child is None and parent.poll() is None and time.monotonic() < deadline:
            found = [pid for pid, arguments in children_of(parent.pid) if MARKER in arguments]
            child = found[0] if found else None
            time.sleep(0.1)
        if child is None:
            # Never wait for the stand-in's own end: ask the launcher to stop it, within the ceiling.
            if parent.poll() is None:
                parent.send_signal(signal.SIGTERM)
            try:
                seen = parent.communicate(timeout=CEILING_SECONDS)
            except subprocess.TimeoutExpired:
                parent.kill(); seen = parent.communicate()
            pytest.fail('the stand-in worker never appeared under the launcher: %r' % (seen,))
        time.sleep(0.5)                                        # past at least one tick of the launcher's loop
        assert parent.poll() is None
        parent.send_signal(signal.SIGTERM)
        out, err = parent.communicate(timeout=CEILING_SECONDS)
    finally:
        if parent.poll() is None:
            parent.kill(); parent.communicate()
        if child is not None:
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
    assert (parent.returncode, err) == (0, '')
    starting, stopped = [json.loads(line) for line in out.splitlines()]
    assert (starting['status'], starting['phase'], starting['session']) == ('STARTING', 'PRE_OPEN', sorted(SESSIONS)[0])
    assert (stopped['status'], stopped['reason'], stopped['child_signal'], stopped['killed']) == ('STOPPED', 'SIGNAL', 'SIGTERM', False)
    with pytest.raises(ProcessLookupError):
        os.kill(child, 0)                                      # reaped by the launcher: the pid is gone
    # The step's own check accepts these notices, with the pin of the launcher that ran ...
    check = program(STOP, 'python3 - "$out/reader-stop-stdout.log" "$pin"')
    assert run_program(check, sample(tmp_path, 'stop.log', *out.splitlines()), pin).returncode == 0
    # ... and refuses another launcher hash, a killed child, a missing end, a failure and a refusal.
    assert run_program(check, sample(tmp_path, 'stop.log', *out.splitlines()), 'd' * 64).returncode != 0
    for index, lines in enumerate((
            [json.dumps(starting), json.dumps({**stopped, 'killed': True, 'child_signal': 'SIGKILL'})],
            [json.dumps(starting), json.dumps({**stopped, 'reason': 'END_OF_DAY'})],
            [json.dumps(starting), json.dumps({**stopped, 'dropped_lines': 3})],
            [json.dumps({**starting, 'launcher_pinned': False}), json.dumps(stopped)],
            [json.dumps({**starting, 'build_sha': None}), json.dumps(stopped)],
            [json.dumps(starting)], [json.dumps(stopped)], [],
            [json.dumps(starting), json.dumps({**stopped, 'status': 'FAILED'})],
            [json.dumps({'status': 'REFUSED', 'code': 'READER_DISABLED'})])):
        assert run_program(check, sample(tmp_path, 'bad-%d.log' % index, *lines), pin).returncode != 0, lines


def test_the_writer_receipt_check_accepts_only_the_documented_off_refusal(tmp_path):
    """The script on standard input under `python -I -B -` with the step's own arguments; the only edit is the
    application root, which in the image is /app. Its real output is then judged by the step's own check."""
    text = (CAPACITY_DAY / 'manifest_writer.py').read_text()
    assert text.count("APPLICATION_ROOT = '/app'") == 1
    directory = tmp_path / 'manifests'; directory.mkdir(mode=0o700)
    environment_off = {key: value for key, value in os.environ.items() if not key.startswith(('C3PO_', 'PYTHON'))}
    done = subprocess.run([sys.executable, '-I', '-B', '-', '--day', '2026-10-05', '--manifest-directory', str(directory)],
        input=text.replace("APPLICATION_ROOT = '/app'", 'APPLICATION_ROOT = ' + repr(str(BACKEND))), cwd=str(tmp_path),
        env={**environment_off, 'C3PO_R2D2_V2_SHADOW_ENABLED': 'false'}, capture_output=True, text=True, timeout=180)
    assert (done.returncode, done.stderr) == (3, '') and list(directory.iterdir()) == []
    check = program(WRITER, 'python3 - "$out/writer-off-stdout.log"')
    receipt = tmp_path / 'receipt.log'; receipt.write_text(done.stdout)
    assert run_program(check, receipt).returncode == 0
    line = json.loads(done.stdout)
    for index, other in enumerate((done.stdout * 2, done.stdout.rstrip('\n'), '', json.dumps({**line, 'code': 'MANIFEST_DAY_INVALID'}) + '\n',
                                   json.dumps({**line, 'status': 'UNVERIFIED'}) + '\n', json.dumps({**line, 'epoch': 'x'}) + '\n',
                                   json.dumps({**line, 'session': '2026-10-06'}) + '\n')):
        changed = tmp_path / ('changed-%d.log' % index); changed.write_text(other)
        assert run_program(check, changed).returncode != 0, other


# ---------------------------------------------------------------- the documents name the steps and claim no run

def test_the_documents_name_the_steps_and_say_that_they_had_not_run():
    reader = (READER / 'README.md').read_text(); capacity = (CAPACITY_DAY / 'README.md').read_text()
    assert '`%s`' % REFUSAL in reader and '`%s`' % STOP in reader and '`%s`' % WRITER in capacity
    for document in (reader, capacity):
        assert '**Unverified on the host.**' in document
        assert 'had not run' in document and 'this directory has no pipeline step yet' not in document
