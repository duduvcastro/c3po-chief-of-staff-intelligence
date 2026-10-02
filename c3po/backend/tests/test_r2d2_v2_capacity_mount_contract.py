"""Compose contract of the read-only capacity mount on r2d2-worker.

The unit suite has no Docker engine, so the host states are rendered here with the two documented
Compose rules the design relies on: `${VAR:-default}` takes the default when VAR is unset or empty,
and a short-syntax volume source is a bind only when it starts with '.', '/' or '~' (anything else
is a named volume that must be declared at the top level). The real-engine render is the pipeline
step pinned at the end of this file. The mount is support only: it does not enable capacity and
proves nothing about the planner.

The JSON shape of `docker compose config --format json` is taken from the Compose source, read on
2026-10-01, not from an engine:

- compose-go `format/volume.go` (`populateType`): a short-syntax bind gets `bind.create_host_path`
  true, a short-syntax named volume gets an empty `volume` object;
- compose-go `types` (`ServiceVolumeConfig`): `type`, `source`, `target`, `read_only` (omitted when
  false), `bind`, `volume`. From compose-go v2.10.0 `create_host_path` is omitted when true, so the
  same bind renders as `"bind": {}`;
- compose-go `loader/normalize.go` (`setNameFromKey`): a top-level volume is named `<project>_<key>`;
- docker/compose `cmd/compose/compose.go` (`ToProject`) and compose-go `WithoutUnnecessaryResources`:
  a top-level volume no service uses is dropped from the project unless `--all-resources` is given;
  `Project.MarshalJSON` omits `volumes` altogether when none is left.

The three files in fixtures/compose_capacity_mount are constructed from those rules for a checkout at
/home/runner/work/repo/repo with an empty .env; service keys other than `volumes` are trimmed. They
are not captures. Replace them with the PR job's `compose-capacity-*.json` once that job has run.
"""
import copy
import json
import posixpath
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
REBOOT_CONTROLLER = ROOT / "scripts" / "c3po_security_reboot.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "compose_capacity_mount"
PROJECT_DIRECTORY = "/home/runner/work/repo/repo/c3po"
BIND_EXPECTATION = f"bind={EXAMPLE_HOST_PATH}"
# file: (expectation, host environment, rendered with --all-resources)
ENGINE_SHAPED_RENDERS = {
    "unset.json": ("placeholder", {}, False),
    "bind-pruned.json": (BIND_EXPECTATION, {MOUNT_VARIABLE: EXAMPLE_HOST_PATH}, False),
    "bind-all-resources.json": (BIND_EXPECTATION, {MOUNT_VARIABLE: EXAMPLE_HOST_PATH}, True),
}

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


def _resolved(environment: dict[str, str], *, all_resources: bool = False) -> dict:
    """Stand-in for `docker compose config --format json` (volumes only); rules in the module docstring.

    Like the engine, it leaves out every top-level volume no service uses unless `all_resources`.
    """
    compose = _render(environment)
    services, used = {}, set()
    for name, service in compose["services"].items():
        volumes = []
        for volume in service.get("volumes", []):
            source, target, mode = _short(volume)
            if _is_bind(source):
                if not source.startswith("/"):
                    source = posixpath.normpath(posixpath.join(PROJECT_DIRECTORY, source))
                entry: dict[str, object] = {"type": "bind", "source": source, "target": target}
                options: dict[str, object] = {"bind": {"create_host_path": True}}
            else:
                used.add(source)
                entry = {"type": "volume", "source": source, "target": target}
                options = {"volume": {}}
            if mode == "ro":
                entry["read_only"] = True
            volumes.append({**entry, **options})
        services[name] = {"volumes": volumes, "environment": {"C3PO_DB_PASSWORD": "value-of-the-host-env"}}
    render = {"name": "c3po", "services": services}
    declared = {key: {"name": f"c3po_{key}"} for key in compose["volumes"] if all_resources or key in used}
    if declared:
        render["volumes"] = declared
    return render


def _contract_view(render: dict) -> tuple:
    """Everything the mount contract reads from a render, without the keys it ignores."""
    return (
        render["name"],
        {
            name: [
                (volume["type"], volume["source"], volume["target"], volume.get("read_only", False))
                for volume in service.get("volumes", [])
            ]
            for name, service in render["services"].items()
        },
        render.get("volumes", {}),
    )


def _capacity_mount(render: dict) -> dict:
    [mount] = [volume for volume in render["services"]["r2d2-worker"]["volumes"] if volume["target"] == TARGET]
    return mount


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
    assert mutated(lambda render: render["services"].update(api="not-a-mapping"))
    assert mutated(lambda render: render.update(volumes=[PLACEHOLDER_VOLUME]))


def test_bind_render_is_accepted_without_the_placeholder_declaration_compose_drops() -> None:
    check = _checker()
    pruned = _resolved({MOUNT_VARIABLE: EXAMPLE_HOST_PATH})
    kept = _resolved({MOUNT_VARIABLE: EXAMPLE_HOST_PATH}, all_resources=True)

    # With a host path no service uses the placeholder volume, and `docker compose config` leaves
    # unused top-level volumes out of the render. Requiring the declaration there refused every
    # enabled host and failed the PR step on a real engine.
    assert set(pruned["volumes"]) == {"c3po_postgres", "c3po_one_pagers", "c3po_day_d_data"}
    assert check(pruned, BIND_EXPECTATION) == []
    # A host that binds the day-d data as well has fewer volumes left; a project with none has no key.
    for remaining in ({"c3po_postgres": {"name": "c3po_c3po_postgres"}}, {}, None):
        render = copy.deepcopy(pruned)
        render["volumes"] = remaining
        assert check(render, BIND_EXPECTATION) == []
    render = copy.deepcopy(pruned)
    del render["volumes"]
    assert check(render, BIND_EXPECTATION) == []

    # `--all-resources` keeps the unused declaration: accepted, and still strict on its name.
    assert kept["volumes"][PLACEHOLDER_VOLUME] == {"name": f"c3po_{PLACEHOLDER_VOLUME}"}
    assert check(kept, BIND_EXPECTATION) == []
    for wrong in ({"name": PLACEHOLDER_VOLUME}, {"name": f"other_{PLACEHOLDER_VOLUME}"}, {}, None, f"c3po_{PLACEHOLDER_VOLUME}"):
        render = copy.deepcopy(kept)
        render["volumes"][PLACEHOLDER_VOLUME] = wrong
        assert check(render, BIND_EXPECTATION) == [
            f"placeholder volume is declared, but not as c3po_{PLACEHOLDER_VOLUME}"
        ]
    # The other assertions of the bind state do not relax with the declaration.
    for render in (pruned, kept):
        assert check(render, "placeholder") and check(render, "bind=/srv/another-tree")
        changed = copy.deepcopy(render)
        _capacity_mount(changed).pop("read_only")
        assert check(changed, BIND_EXPECTATION) == ["the capacity mount is not read-only"]


@pytest.mark.parametrize("environment", [{}, {MOUNT_VARIABLE: ""}])
@pytest.mark.parametrize("all_resources", [False, True])
def test_placeholder_render_without_the_declaration_is_refused(environment, all_resources) -> None:
    check = _checker()
    refusal = [f"placeholder volume is not declared as c3po_{PLACEHOLDER_VOLUME}"]
    render = _resolved(environment, all_resources=all_resources)

    # The placeholder is in use here, so the engine always renders its declaration.
    assert render["volumes"][PLACEHOLDER_VOLUME] == {"name": f"c3po_{PLACEHOLDER_VOLUME}"}
    assert check(render, "placeholder") == []
    for wrong in ({"name": PLACEHOLDER_VOLUME}, {}, None):
        changed = copy.deepcopy(render)
        changed["volumes"][PLACEHOLDER_VOLUME] = wrong
        assert check(changed, "placeholder") == refusal
    del render["volumes"][PLACEHOLDER_VOLUME]
    assert check(render, "placeholder") == refusal
    del render["volumes"]
    assert check(render, "placeholder") == refusal


@pytest.mark.parametrize("name", sorted(ENGINE_SHAPED_RENDERS))
def test_render_checker_reads_the_engine_shaped_fixture_renders(name) -> None:
    check = _checker()
    expect, environment, all_resources = ENGINE_SHAPED_RENDERS[name]
    render = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    other = BIND_EXPECTATION if expect == "placeholder" else "placeholder"

    assert check(render, expect) == []
    assert check(render, other)
    # The fixtures follow the compose file: when a mount changes there, they change with it.
    assert sorted(path.name for path in FIXTURES.iterdir()) == sorted(ENGINE_SHAPED_RENDERS)
    assert _contract_view(render) == _contract_view(_resolved(environment, all_resources=all_resources))

    # Keys the checker does not assert may vary with the Compose version and must not matter.
    for options in (
        {"bind": {"create_host_path": True}},   # compose-go before v2.10.0
        {"bind": {}},                           # compose-go v2.10.0 and later
        {"bind": {"create_host_path": True, "propagation": "rprivate"}, "consistency": "cached"},
        {"volume": {}},
        {},
    ):
        varied = copy.deepcopy(render)
        mount = _capacity_mount(varied)
        for key in ("bind", "volume", "consistency"):
            mount.pop(key, None)
        mount.update(options)
        varied["x-unknown-top-level"] = {"anything": True}
        varied["services"]["r2d2-worker"]["unknown_service_key"] = ["anything"]
        assert check(varied, expect) == []
    # Keys it does assert stay strict in every shape.
    for key, value in (("type", "tmpfs"), ("source", "/srv/another-tree"), ("target", "/app/c3po-capacity"), ("read_only", False)):
        varied = copy.deepcopy(render)
        _capacity_mount(varied)[key] = value
        assert check(varied, expect)
    varied = copy.deepcopy(render)
    varied["name"] = "repo"
    assert check(varied, expect) == ["project name is not c3po"]


def test_the_three_fixture_renders_are_three_different_engine_shapes() -> None:
    renders = {
        name: json.loads((FIXTURES / name).read_text(encoding="utf-8")) for name in ENGINE_SHAPED_RENDERS
    }

    assert {
        name: (
            PLACEHOLDER_VOLUME in render["volumes"],
            {key: value for key, value in _capacity_mount(render).items() if key in {"type", "bind", "volume"}},
        )
        for name, render in renders.items()
    } == {
        # variable unset: the placeholder is used, so it is declared
        "unset.json": (True, {"type": "volume", "volume": {}}),
        # variable set, default render: the unused placeholder is dropped
        "bind-pruned.json": (False, {"type": "bind", "bind": {"create_host_path": True}}),
        # variable set, --all-resources, compose-go v2.10.0 or later: declaration kept, option omitted
        "bind-all-resources.json": (True, {"type": "bind", "bind": {}}),
    }
    for render in renders.values():
        # Relative bind sources are rendered absolute; only the capacity source is the host's value.
        sources = [volume["source"] for service in render["services"].values() for volume in service.get("volumes", [])]
        assert all(source.startswith("/") or source in render["volumes"] for source in sources)
        assert all(volume == {"name": f"c3po_{key}"} for key, volume in render["volumes"].items())


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
    # The PR step passes a file; the operator pipes. Both forms, on every engine-shaped render.
    for name, (expect, _, _) in ENGINE_SHAPED_RENDERS.items():
        text = (FIXTURES / name).read_text(encoding="utf-8")
        from_file = subprocess.run(
            [sys.executable, "-B", str(CHECKER), expect, str(FIXTURES / name)], capture_output=True, text=True, check=False,
        )
        piped = subprocess.run(
            [sys.executable, "-B", str(CHECKER), expect, "-"], input=text, capture_output=True, text=True, check=False,
        )
        assert from_file.returncode == piped.returncode == 0 and from_file.stdout == piped.stdout
        assert from_file.stdout.startswith(f"CAPACITY_MOUNT_RENDER_OK {expect} ") and from_file.stdout.count("\n") == 1
        assert json.loads(from_file.stdout.split(" ", 2)[2]) == _capacity_mount(json.loads(text))
        assert from_file.stderr == "" and "C3PO_BUILD_SHA" not in from_file.stdout
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
        'mkdir -p "$out" || exit 1',
        'docker compose version | tee "$out/compose-version.txt" || exit 1',
        'cat "$out/compose-capacity-bare-word.err" || exit 1',
    ))
    script = step.split("run: |", 1)[1]
    # The stand-in .env is empty, refused if one already exists, and removed again; the step only
    # renders: it starts, creates and pulls nothing.
    assert '          [ ! -e .env ] || { echo "unexpected .env in the workspace" >&2; exit 1; }\n' in script
    assert "trap 'rm -f .env' EXIT" in script and ": > .env || exit 1" in script
    assert not re.search(r"\b(up|run|create|start|pull|build|exec)\b", script)
    # A bare word that Compose accepts fails the step.
    assert (
        '          if env "$var=not-a-path" "${compose[@]}" config --quiet 2> "$out/compose-capacity-bare-word.err"; then\n'
        '            echo "a bare word was accepted as the capacity mount source" >&2\n'
        '            exit 1\n'
        '          fi\n'
    ) in script
    # No guard relies on `set -e`: every command line carries its own failing exit.
    assert "set -uo pipefail" in script and "set -e" not in script
    commands = [
        line.strip() for line in script.splitlines()
        if line.strip().startswith(("mkdir ", ": >", "docker ", "env ", "python3 ", "cat "))
    ]
    assert len(commands) == 10 and all(line.endswith(" || exit 1") for line in commands)
    assert script.count("exit 1") == 12
    # `config` creates nothing, so the step asserts nothing about volumes or host paths: what `up`
    # creates on a host is measured by the read-back after the deploy, and the step says so.
    assert "docker volume" not in step and '-e "$example"' not in step
    assert "first measured by the read-back after the deploy" in step
    assert "creates no volume or host" not in step


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
        'check_compose_render.py "bind=$CAP" -',
        "compose up -d --no-build --no-deps r2d2-worker",
        "CAPACITY_STARTUP_OK ['documents', 'go', 'payload']",
        "The mount does not enable capacity and proves nothing about the planner.",
        "## Not verified on the host",
    ))
    flat = " ".join(readme.split())

    # Lock first, reboot marker second: the order and the paths of the deploy and of the controller.
    assert "    exec 9>>runtime/security/deployment.lock && flock -w 120 9 && test ! -e /run/c3po-security/reboot.pending\n" in readme
    assert readme.count("reboot.pending") == 1
    remote = PIPELINE.read_text(encoding="utf-8").split("<<'REMOTE'", 1)[1].split("REMOTE", 1)[0]
    assert (
        remote.index('exec 9>>"$APP_DIR/runtime/security/deployment.lock"')
        < remote.index("flock -w 120 9")
        < remote.index("if [ -e /run/c3po-security/reboot.pending ]; then")
    )
    assert "APP_DIR=/opt/chief-of-staff-digital\n" in remote and "Run in `/opt/chief-of-staff-digital`" in readme
    controller = REBOOT_CONTROLLER.read_text(encoding="utf-8")
    assert 'MARKER = Path("/run/c3po-security/reboot.pending")' in controller
    assert 'root / "runtime/security/deployment.lock"' in controller

    # Step 1: the tree exists at its canonical path before the variable is written, and is written once.
    assert (
        '    case "$CAP" in /*) true ;; *) false ;; esac \\\n'
        '      && test "$(sudo realpath "$CAP")" = "$CAP" && sudo test -d "$CAP/config" \\\n'
        f"      && ! grep -q '^{SETTINGS_PREFIX}' .env \\\n"
        f"      && printf '{MOUNT_VARIABLE}=%s\\n' \"$CAP\" >> .env\n"
    ) in readme
    # Its failure path is a command, and removes that one line only.
    assert f"    sed -i '/^{MOUNT_VARIABLE}=/d' .env\n    compose config --quiet\n" in readme

    # Step 2: the dry run constructs the real startup object and names nothing that is not in app/.
    assert (
        "r2d2-worker python -B -c 'from app.config import Settings; "
        "from app.r2d2_v2_capacity_bootstrap import CapacityConfig; c=CapacityConfig(Settings()); "
        "print(\"CAPACITY_STARTUP_OK\", sorted(c.roots), c.veto_mode); c.close()'\n"
    ) in readme
    bootstrap = (APP / "r2d2_v2_capacity_bootstrap.py").read_text(encoding="utf-8")
    assert "class CapacityConfig:" in bootstrap and "    def close(self):" in bootstrap
    assert "self.roots=" in bootstrap and "self.veto_mode=" in bootstrap

    # The notes say what the render check cannot show, and the two rules read in source only.
    assert "Expected, not yet measured:" in flat
    assert "is first measured by this read-back after the first deploy that carries the mount" in flat
    assert "at every start of the container while the variable is set" in flat
    assert "provision the tree first, set the variable second" in flat
    assert "do the full disable (below) before the tree is moved, removed or provisioned again" in flat
    backend = [name for name, service in _render({})["services"].items() if "env_file" in service]
    assert len(backend) == 6 and all(f"`{name}`" in readme for name in backend)
    assert "changes the config hash of all six" in flat
    assert "recreates only the worker; the next plain `up -d` (the deploy runs one) recreates the other five" in flat
    assert "c3po/backend/tests/fixtures/compose_capacity_mount" in readme
    settings = {f"C3PO_{name.upper()}" for name in Settings.model_fields if name.startswith("r2d2_v2_capacity_")}
    assert settings == {
        f"{SETTINGS_PREFIX}{suffix}" for suffix in ("REQUIRED", "VETO_MODE", "CONFIG_FILE", "CONFIG_SHA")
    }
    assert all(f"    {name}=" in readme for name in settings)
    # Step 3: the four settings are appended by one guarded command, each refused if already there,
    # and only with the mount variable in place. Values are shell variables, never literals.
    assert all(f"      && ! grep -q '^{name}=' .env \\\n" in readme for name in settings)
    assert f"      && grep -q '^{MOUNT_VARIABLE}=/' .env \\\n" in readme
    assert (
        f"      && printf '%s\\n' \"{SETTINGS_PREFIX}REQUIRED=true\" \"{SETTINGS_PREFIX}CONFIG_FILE=$CFG\" \\\n"
        f"        \"{SETTINGS_PREFIX}CONFIG_SHA=$SHA\" \"{SETTINGS_PREFIX}VETO_MODE=DISPATCH_AND_DERIVATION_ONLY\" >> .env\n"
    ) in readme
    assert f"    sed -i -E '/^{SETTINGS_PREFIX}(REQUIRED|CONFIG_FILE|CONFIG_SHA|VETO_MODE)=/d' .env\n" in readme
    assert readme.count(">> .env") == 2
    # No private value: every host path, file name and hash in the notes is a placeholder.
    assert not re.search(r"\b[0-9a-f]{40,}\b", readme) and "/mnt/" not in readme and "/var/lib/" not in readme
