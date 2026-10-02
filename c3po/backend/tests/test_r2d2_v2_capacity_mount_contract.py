"""Compose contract of the read-only capacity mount on r2d2-worker.

The unit suite has no Docker engine, so the host states are rendered here with the two documented
Compose rules the design relies on: `${VAR:-default}` takes the default when VAR is unset or empty,
and a short-syntax volume source is a bind only when it starts with '.', '/' or '~' (anything else
is a named volume that must be declared at the top level). The real-engine render is the pipeline
step pinned at the end of this file. The mount is support only: it does not enable capacity and
proves nothing about the planner.
"""
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from app.config import Settings


ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "c3po" / "compose.yml"
ENV_EXAMPLE = ROOT / ".env.example"
PIPELINE = ROOT / ".github" / "workflows" / "c3po-pipeline.yml"
APP = ROOT / "c3po" / "backend" / "app"
OPERATOR = ROOT / "c3po" / "deployment" / "capacity-mount"
CHECKER = OPERATOR / "check_compose_render.py"

MOUNT_VARIABLE = "C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE"
PLACEHOLDER_VOLUME = "c3po_capacity_unprovisioned"
TARGET = "/c3po-capacity"
MOUNT_LINE = f"      - ${{{MOUNT_VARIABLE}:-{PLACEHOLDER_VOLUME}}}:{TARGET}:ro"
SETTINGS_PREFIX = "C3PO_R2D2_V2_CAPACITY_"
EXAMPLE_HOST_PATH = "/srv/example-capacity-tree"
COMPOSE_COMMAND = "docker compose --env-file .env -f c3po/compose.yml"

_DEFAULTED = re.compile(r"\$\{([A-Z][A-Z0-9_]*):-([^${}]*)\}")


def _interpolate(text: str, environment: dict[str, str]) -> str:
    return _DEFAULTED.sub(lambda match: environment.get(match.group(1)) or match.group(2), text)


def _render(environment: dict[str, str]) -> dict:
    return yaml.safe_load(_interpolate(COMPOSE.read_text(encoding="utf-8"), environment))


def _short(volume: str) -> tuple[str, str, str]:
    assert isinstance(volume, str), "the design uses short syntax only"
    source, target, *mode = volume.split(":")
    assert len(mode) <= 1
    return source, target, (mode[0] if mode else "rw")


def _is_bind(source: str) -> bool:
    return source[:1] in {".", "/", "~"}


def _capacity_mounts(compose: dict) -> dict[str, list[tuple[str, str, str]]]:
    found = {}
    for name, service in compose["services"].items():
        mounts = [_short(v) for v in service.get("volumes", []) if _short(v)[1] == TARGET]
        if mounts:
            found[name] = mounts
    return found


def _resolved(environment: dict[str, str]) -> dict:
    """The shape `docker compose config --format json` gives the rendered project (volumes only)."""
    compose = _render(environment)
    services = {}
    for name, service in compose["services"].items():
        volumes = []
        for volume in service.get("volumes", []):
            source, target, mode = _short(volume)
            entry: dict[str, object] = {
                "type": "bind" if _is_bind(source) else "volume", "source": source, "target": target,
            }
            if mode == "ro":
                entry["read_only"] = True
            volumes.append(entry)
        services[name] = {"volumes": volumes, "environment": {"C3PO_DB_PASSWORD": "value-of-the-host-env"}}
    return {
        "name": "c3po",
        "services": services,
        "volumes": {key: {"name": f"c3po_{key}"} for key in compose["volumes"]},
    }


def _checker():
    # Compiled in memory: importing by path would leave a bytecode cache beside the operator script.
    namespace: dict = {"__name__": "check_compose_render"}
    exec(compile(CHECKER.read_text(encoding="utf-8"), str(CHECKER), "exec"), namespace)
    return namespace["check"]


def _step(pipeline: str, name: str) -> str:
    start = pipeline.index(f"      - name: {name}\n")
    return pipeline[start:pipeline.index("\n      - name: ", start + 1)]


def test_every_interpolation_has_a_default_so_no_host_variable_is_required() -> None:
    text = COMPOSE.read_text(encoding="utf-8")

    # A required (`:?`) or bare variable would fail or warn in every command that loads this file:
    # the deploy, the security reboot controller, the watchdog and the backup.
    assert text.count("${") == len(_DEFAULTED.findall(text))
    assert ":?" not in text
    assert "$$" not in text


def test_capacity_mount_is_one_read_only_line_on_r2d2_worker_only() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    worker = re.search(r"^  r2d2-worker:\n((?:    .*\n|\n)+)", text, re.M)

    assert worker is not None and MOUNT_LINE + "\n" in worker.group(1)
    assert text.count(TARGET) == 1
    assert text.count(MOUNT_VARIABLE) == 1
    assert text.count(PLACEHOLDER_VOLUME) == 2  # the default of the line and the declaration
    assert set(_capacity_mounts(_render({}))) == {"r2d2-worker"}
    assert set(_capacity_mounts(_render({MOUNT_VARIABLE: EXAMPLE_HOST_PATH}))) == {"r2d2-worker"}


@pytest.mark.parametrize("environment", [{}, {MOUNT_VARIABLE: ""}])
def test_unprovisioned_host_mounts_the_declared_placeholder_and_no_host_path(environment) -> None:
    compose = _render(environment)
    [(source, target, mode)] = _capacity_mounts(compose)["r2d2-worker"]

    assert (source, target, mode) == (PLACEHOLDER_VOLUME, TARGET, "ro")
    assert not _is_bind(source)
    assert PLACEHOLDER_VOLUME in compose["volumes"] and compose["volumes"][PLACEHOLDER_VOLUME] is None
    # Compose refuses a project whose service names an undeclared volume; hold that for every service.
    for service in compose["services"].values():
        for volume in service.get("volumes", []):
            named = _short(volume)[0]
            assert _is_bind(named) or named in compose["volumes"]


def test_provisioned_host_path_becomes_a_read_only_bind_and_changes_nothing_else() -> None:
    unset = _render({})
    enabled = _render({MOUNT_VARIABLE: EXAMPLE_HOST_PATH})
    [(source, target, mode)] = _capacity_mounts(enabled)["r2d2-worker"]

    assert (source, target, mode) == (EXAMPLE_HOST_PATH, TARGET, "ro")
    assert _is_bind(source) and Path(target).parent == Path("/")
    expected = copy.deepcopy(unset)
    volumes = expected["services"]["r2d2-worker"]["volumes"]
    volumes[volumes.index(f"{PLACEHOLDER_VOLUME}:{TARGET}:ro")] = f"{EXAMPLE_HOST_PATH}:{TARGET}:ro"
    assert enabled == expected


def test_the_mount_alone_does_not_enable_capacity() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    compose = _render({MOUNT_VARIABLE: EXAMPLE_HOST_PATH})

    # The settings arrive only through the host .env (env_file); nothing in the repository sets or
    # shadows them, so the variable above selects a directory and nothing more.
    assert text.count(SETTINGS_PREFIX) == 1
    for service in compose["services"].values():
        assert not [key for key in service.get("environment", {}) if key.startswith(SETTINGS_PREFIX)]
    assert compose["services"]["r2d2-worker"]["env_file"] == ["../.env"]
    active = [
        line for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if line.startswith(SETTINGS_PREFIX)
    ]
    assert active == []
    assert f"# {MOUNT_VARIABLE}=/" in ENV_EXAMPLE.read_text(encoding="utf-8")
    fields = Settings.model_fields
    assert fields["r2d2_v2_capacity_required"].default is False
    assert fields["r2d2_v2_capacity_config_file"].default == ""
    assert fields["r2d2_v2_capacity_config_sha"].default == ""
    assert "r2d2_v2_capacity_mount_source" not in fields


def test_only_r2d2_worker_runs_a_module_that_reads_the_capacity_flag() -> None:
    # The host .env is the env_file of every backend service, so the flag is visible to all of them.
    # That is acceptable only while r2d2-worker is the one compose command that reads it.
    readers = sorted(
        path.relative_to(APP).as_posix()
        for path in APP.rglob("*.py")
        if "r2d2_v2_capacity_required" in path.read_text(encoding="utf-8")
    )
    commands = {name: service.get("command") or [] for name, service in _render({})["services"].items()}
    launched = {
        name: sorted({module for word in command for module in re.findall(r"\bapp\.([a-z0-9_]+)", word)})
        for name, command in commands.items()
    }

    assert {
        name: modules for name, modules in launched.items()
        if any(f"{module}.py" in readers for module in modules)
    } == {"r2d2-worker": ["r2d2_worker"]}
    assert not [name for name, modules in launched.items() if "r2d2_v2_shadow_worker" in modules]
    # Exact list at this head. A new reader under app/ must be a deliberate update of this line:
    # re-run this file on the final merged head before the freeze.
    assert readers == ["config.py", "r2d2_v2_shadow_worker.py", "r2d2_worker.py"]


def test_what_the_controllers_observe_on_r2d2_worker_is_unchanged() -> None:
    compose = _render({MOUNT_VARIABLE: EXAMPLE_HOST_PATH})
    worker = compose["services"]["r2d2-worker"]

    assert list(compose["services"]) == [
        "db", "api", "investor-relations-worker", "valuation-worker", "server-usage-worker",
        "r2d2-worker", "r2d2-shadow-candidate-worker", "web",
    ]
    assert set(worker) == {
        "image", "build", "env_file", "environment", "command", "volumes", "depends_on", "restart", "networks",
    }
    assert worker["volumes"][:2] == [
        "../runtime/security/maintenance:/run/c3po-maintenance:ro",
        "c3po_day_d_data:/app/day-d-data",
    ]
    assert len(worker["volumes"]) == 3
    assert worker["environment"]["C3PO_MAINTENANCE_GATE_DIR"] == "/run/c3po-maintenance"
    assert worker["environment"]["C3PO_SERVICE_NAME"] == "r2d2-worker"
    assert worker["restart"] == "unless-stopped"


def test_deploy_validates_the_compose_file_before_it_recreates_any_container() -> None:
    pipeline = PIPELINE.read_text(encoding="utf-8")
    remote = pipeline.split("<<'REMOTE'", 1)[1].split("REMOTE", 1)[0]
    validate = remote.index(f"{COMPOSE_COMMAND} config --quiet")
    recreate = remote.index(f"{COMPOSE_COMMAND} up -d --no-build")

    # A host value that is neither empty nor a path names an undeclared volume. The deploy stops at
    # validation before any container is replaced; the new source tree and the new image tags are
    # already in place by then, so this guards the containers, not the release files.
    assert remote.index("rsync -a --delete") < validate < recreate


def test_render_checker_accepts_the_three_host_states_and_refuses_every_other_shape() -> None:
    check = _checker()
    unset, empty, bound = _resolved({}), _resolved({MOUNT_VARIABLE: ""}), _resolved({MOUNT_VARIABLE: EXAMPLE_HOST_PATH})

    assert check(unset, "placeholder") == []
    assert check(empty, "placeholder") == []
    assert check(bound, f"bind={EXAMPLE_HOST_PATH}") == []
    assert check(unset, f"bind={EXAMPLE_HOST_PATH}") and check(bound, "placeholder")
    assert check(bound, "bind=/srv/another-tree") and check(bound, "bind=relative") and check(bound, "anything")
    assert check(_resolved({MOUNT_VARIABLE: "bare-word"}), "bind=/bare-word")
    assert check({}, "placeholder") and check([], "placeholder")

    def mutated(change) -> list[str]:
        render = copy.deepcopy(unset)
        change(render)
        return check(render, "placeholder")

    mount = lambda render: render["services"]["r2d2-worker"]["volumes"][2]  # noqa: E731
    assert mutated(lambda render: mount(render).pop("read_only"))
    assert mutated(lambda render: mount(render).update(read_only=False))
    assert mutated(lambda render: mount(render).update(target="/app/c3po-capacity"))
    assert mutated(lambda render: render["services"]["api"]["volumes"].append(dict(mount(render))))
    assert mutated(lambda render: render["services"]["r2d2-worker"]["volumes"].append(dict(mount(render))))
    assert mutated(lambda render: render["services"]["r2d2-worker"]["volumes"].pop(0))
    assert mutated(lambda render: render["volumes"].pop(PLACEHOLDER_VOLUME))
    assert mutated(lambda render: render.update(name="other"))
    assert mutated(lambda render: render["services"]["r2d2-worker"]["volumes"].__setitem__(2, f"x:{TARGET}:ro"))


def test_render_checker_command_never_prints_the_rest_of_the_render(tmp_path) -> None:
    def run(expect: str, render: dict, *, stdin: bool = False):
        file = tmp_path / "render.json"
        file.write_text(json.dumps(render), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-B", str(CHECKER), expect, "-" if stdin else str(file)],
            input=json.dumps(render) if stdin else None, capture_output=True, text=True, check=False,
        )

    accepted = run(f"bind={EXAMPLE_HOST_PATH}", _resolved({MOUNT_VARIABLE: EXAMPLE_HOST_PATH}), stdin=True)
    refused = run("placeholder", _resolved({MOUNT_VARIABLE: EXAMPLE_HOST_PATH}))

    assert accepted.returncode == 0 and accepted.stdout.startswith("CAPACITY_MOUNT_RENDER_OK bind=")
    assert EXAMPLE_HOST_PATH in accepted.stdout and '"read_only": true' in accepted.stdout
    assert refused.returncode == 1 and "CAPACITY_MOUNT_RENDER_REFUSED" in refused.stderr and refused.stdout == ""
    assert run("placeholder", _resolved({})).returncode == 0
    for result in (accepted, refused):
        assert "value-of-the-host-env" not in result.stdout + result.stderr
    assert subprocess.run([sys.executable, "-B", str(CHECKER)], capture_output=True, check=False).returncode == 2


def test_pull_request_job_renders_the_three_host_states_on_a_real_engine() -> None:
    pipeline = PIPELINE.read_text(encoding="utf-8")
    step = _step(pipeline, "Render the compose capacity mount on a real engine")
    job = pipeline[pipeline.index("\n  frontend-build:\n"):pipeline.index("\n  security-remediation-proof:\n")]

    # The engine proof must exist before main freezes: it is a blocking step of a job the deploy needs.
    assert step in job and "needs: [sensitive-files, secret-scan, backend-tests, python-type-check, frontend-build]" in pipeline
    assert "github.event_name == 'pull_request' ||" in step
    assert "continue-on-error" not in step and "secrets." not in step
    assert f"compose=({COMPOSE_COMMAND})" in step and f"var={MOUNT_VARIABLE}" in step
    assert f"example={EXAMPLE_HOST_PATH}" in step
    assert all(value in step for value in (
        "check=c3po/deployment/capacity-mount/check_compose_render.py",
        'env -u "$var" "${compose[@]}" config --format json > "$out/compose-capacity-unset.json" || exit 1',
        'env "$var=" "${compose[@]}" config --format json > "$out/compose-capacity-empty.json" || exit 1',
        'env "$var=$example" "${compose[@]}" config --format json > "$out/compose-capacity-bind.json" || exit 1',
        'python3 "$check" placeholder "$out/compose-capacity-unset.json" || exit 1',
        'python3 "$check" placeholder "$out/compose-capacity-empty.json" || exit 1',
        'python3 "$check" "bind=$example" "$out/compose-capacity-bind.json" || exit 1',
        'if env "$var=not-a-path" "${compose[@]}" config --quiet',
        "docker compose version",
        "docker volume ls -q --filter name=c3po_capacity_unprovisioned",
    ))
    # The stand-in .env is empty, refused if one already exists, and removed again; the step only
    # renders: it starts, creates and pulls nothing.
    assert '[ ! -e .env ] ||' in step and "trap 'rm -f .env' EXIT" in step and ": > .env || exit 1" in step
    assert not re.search(r"\b(up|run|create|start|pull|build|exec)\b", step.split("run: |", 1)[1])


def test_operator_notes_match_the_contract() -> None:
    readme = (OPERATOR / "README.md").read_text(encoding="utf-8")

    # One prefix covers the mount variable and the four settings, so one expression reverts all five.
    assert MOUNT_VARIABLE.startswith(SETTINGS_PREFIX)
    assert f"sed -i '/^{SETTINGS_PREFIX}/d' .env" in readme
    assert f"sed -i '/^{SETTINGS_PREFIX}REQUIRED=/d' .env" in readme
    assert f"    ${{{MOUNT_VARIABLE}:-{PLACEHOLDER_VOLUME}}}:{TARGET}:ro\n" in readme
    assert f"`c3po_{PLACEHOLDER_VOLUME}`" in readme
    assert all(value in readme for value in (
        f'compose() {{ C3PO_BUILD_SHA="$(cat .deploy-version)" {COMPOSE_COMMAND} "$@"; }}',
        "exec 9>>runtime/security/deployment.lock && flock -w 120 9",
        "test ! -e /run/c3po-security/reboot.pending",
        f"printf '{MOUNT_VARIABLE}=%s\\n' \"$CAP\" >> .env",
        'check_compose_render.py "bind=$CAP" -',
        "compose up -d --no-build --no-deps r2d2-worker",
        "CAPACITY_STARTUP_OK ['documents', 'go', 'payload']",
        "The mount does not enable capacity and proves nothing about the planner.",
        "## Not verified on the host",
    ))
    settings = {f"C3PO_{name.upper()}" for name in Settings.model_fields if name.startswith("r2d2_v2_capacity_")}
    assert settings == {
        f"{SETTINGS_PREFIX}{suffix}" for suffix in ("REQUIRED", "VETO_MODE", "CONFIG_FILE", "CONFIG_SHA")
    }
    assert all(f"    {name}=" in readme for name in settings)
    # No private value: every host path, file name and hash in the notes is a placeholder.
    assert not re.search(r"\b[0-9a-f]{40,}\b", readme) and "/mnt/" not in readme and "/var/lib/" not in readme
