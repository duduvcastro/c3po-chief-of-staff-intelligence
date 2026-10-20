"""``.github/workflows/valuation-pit-backtest.yml`` (PREREG_VALUATION_PIT_BACKTEST_US_V1 §10, §14): dispatch only; the
owner's order bound to the run (a file of main that hashes to the input and authorises this mode, these pins, this flag,
this cap, not after its deadline); the operating window (the nightly window starts at 23:30 São Paulo); the host
preflight, the shared deploy lock, `timeout` and the stop on cancel; the report's provenance, single look and manifest on
stdin; and the verifier that keeps aggregates only — every Python block run here as the workflow carries it: a real
receipt of the report accepted against the repository's prereg, every invalid reading refused, a VOID reading summarised
without statistics, partial outputs published as partial, the price backfill's per-symbol lists reduced to counts."""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

from app import valuation_official as official
from app import valuation_pit_backtest_report as backtest
from app import valuation_pit_rerun as pit
from tests.test_valuation_pit_backtest_report import PREREG_PATH, PRODUCER, SERVED_PRODUCER, Synthetic, _positive, _settings, small  # noqa: F401  (small: a fixture)

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "valuation-pit-backtest.yml"
STOP_STEP = "Stop this run's host processes on cancel or failure"


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _step(name: str) -> dict[str, Any]:
    steps = [step for job in _workflow()["jobs"].values() for step in job.get("steps", [])]
    return next(step for step in steps if step.get("name") == name)


def _script(name: str) -> str:
    """The Python of a step, exactly as the workflow file carries it."""
    run = _step(name)["run"]
    return run.split("<<'PY'", 1)[1].split("\n", 1)[1].split("\nPY\n", 1)[0]


def _python(name: str, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-", *args], input=_script(name), text=True, capture_output=True, env={**os.environ, **env}, cwd=ROOT)


def test_the_workflow_is_dispatch_only_and_guards_the_host() -> None:
    workflow = _workflow()
    assert set(workflow[True]) == {"workflow_dispatch"}  # never on push or a schedule
    inputs = workflow[True]["workflow_dispatch"]["inputs"]
    assert inputs["mode"]["options"] == ["host-check", "dry-run", "price-backfill", "fetch", "grid", "report"] and len(inputs) <= 10
    assert set(inputs) == {"confirmation", "mode", "owner_order_sha256", "price_pinned_at", "catalogue_pinned_at", "max_runs", "recompute_existing",
                           "manifest_run_id", "manifest_sha256", "prereg_commit"} and inputs["recompute_existing"]["type"] == "boolean"
    assert workflow["permissions"] == {"contents": "read", "actions": "read"} and workflow["concurrency"]["cancel-in-progress"] is False
    validate = _step("Validate the inputs")["run"]
    assert "price-backfill|fetch|grid)" in validate and "owner_order_sha256 is required" in validate and 'echo "owner order sha256: $ORDER"' in validate
    assert '[ "$MAX_RUNS" -le 200 ]' in validate and "^[0-9a-f]{40}$" in validate and "grid|report) [ -n \"$PREREG_COMMIT\" ]" in validate
    remote = _step("Run on the host")["run"]
    for mode in ("host-check", "dry-run)"):
        assert '"${readonly_session[@]}"' in remote.split(mode, 1)[1].split(";;", 1)[0] or mode == "host-check", mode
    assert 'exec "${compose[@]}" exec -T "${readonly_session[@]}" api python -m app.valuation_pit_grid --market US --host-check' in remote
    assert "flock -s -n 9" in remote and 'exec 9>>"$APP_DIR/runtime/security/deployment.lock"' in remote  # a SHARED deploy lock, never waited for
    # ONE deadline: the end is fixed once on the host; every process runs under what is left of it (writing legs: 60 s; the dry run: 10 min)
    assert remote.count("end=$(( now + DEADLINE ))") == 1 and remote.count("timeout -s TERM -k 120") == 1
    assert 'api timeout -s TERM -k 120 "$left" nice -n 10 python -X "valuation_pit_run_token=$RUN_TOKEN" -m "$@"' in remote
    assert remote.count("leg 60 app.") == 4 and remote.count("leg 600 app.") == 1
    assert "exec \"${compose[@]}\" exec -T api" not in remote  # no process outside a leg but the read-only host check
    assert "--backfill --months 120" in remote and "--market NYSE --fetch --no-macro" in remote and '--stop-before "$STOP_BEFORE"' in remote
    assert '--expect-producer-sha256 "$PRODUCER"' in remote and '--catalogue-pinned-at "$CATALOGUE_PIN"' in remote and "--statements vintages --step-sessions 5" in remote
    for guard in ("/var/run/reboot-required", "/run/c3po-security/reboot.pending", "systemctl list-units --type=timer", "--state=active,activating,reloading",
                  "'r2d2*' 'c3po-massive*'", "NextElapseUSecRealtime", '["ingestion_runs"]["blocking"]', "6291456 + reserve", "3145728",
                  "MAX_RUNS * 2 * 10240", "price-backfill) reserve=2097152", "fetch) reserve=524288", "/mnt/day-d-data", "MemAvailable"):
        assert guard in remote, guard
    assert remote.index('if [ "$MODE" = host-check ]') < remote.index("the backtest must wait for recovery")  # the host check is exempt from the reboot refusal
    assert "cannot be parsed: refused (fail closed)" in remote and "+%s 2>/dev/null) || continue" not in remote  # an unreadable timer refuses
    report = _step("Run the report on the host")["run"]
    assert '< "$RUNNER_TEMP/manifest/manifest.json"' in report and "--manifest -" in report
    assert '[ "$left" -ge 600 ]' in report and "api timeout -s TERM -k 120 $left nice -n 10 python -X valuation_pit_run_token=$RUN_TOKEN -m app.valuation_pit_backtest_report" in report
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "MANIFEST_B64" not in text and "base64" not in text  # the manifest travels on stdin, never in argv or the environment
    assert "set -e\n" not in text and "set -euo" not in text  # every guard explicit
    secret_steps = {step["name"] for job in workflow["jobs"].values() for step in job["steps"] if "secrets." in json.dumps(step)}
    assert secret_steps == {"Configure deployment SSH key", "Run on the host", "Run the report on the host", "Stop this run's host processes on cancel or failure"}
    assert "stderr.log" in remote and "cat \"$raw/stderr.log\"" not in remote  # the remote stderr is counted, never printed
    stop = _step(STOP_STEP)
    assert stop["if"].startswith("(cancelled() || failure() || (inputs.mode == 'report' && steps.report.outputs.rc || steps.host.outputs.rc) != '0')")
    assert "inputs.mode != 'host-check'" in stop["if"] and "pkill -TERM -f 'valuation_pit_run_token=$RUN_TOKEN -m app[.]valuation_'" in stop["run"]
    assert "pkill -TERM -f 'app.valuation_" not in text  # never a selector by module name alone (it matches a manual --nightly)
    for name in ("Run on the host", "Run the report on the host", STOP_STEP):
        assert _step(name)["env"]["RUN_TOKEN"] == "${{ github.run_id }}-${{ github.run_attempt }}", name
    assert "echo 'LAUNCHED $RUN_TOKEN' && docker compose" in report and "python -X valuation_pit_run_token=$RUN_TOKEN -m app.valuation_pit_backtest_report" in report
    producer_step = _step("Read the pre-registration and the producer at the prereg commit")["run"]
    listed = producer_step.split("for name in", 1)[1].split("; do", 1)[0].replace("\\", " ").split()
    assert tuple(listed) == pit.IMPLEMENTATION_FILES  # the producer the workflow checks is the run manifest's, file for file
    objects = producer_step.split("objects=(", 1)[1].split(")", 1)[0].split()
    assert tuple(f"app.database.{name}" for name in objects) == pit.IMPLEMENTATION_OBJECTS  # and reader for reader
    assert "cmp -s" in producer_step and "changed since the commit of its hash receipt" in producer_step


def _window(mode: str, now: str) -> subprocess.CompletedProcess[str]:
    return _python("Check the operating window", env={"MODE": mode, "WINDOW_NOW": now})


def test_the_operating_window_starts_at_half_past_eleven_in_sao_paulo() -> None:
    late = _window("grid", "2026-10-18T23:50:00-03:00")  # Sunday 23:50 São Paulo: the nightly cycle starts at 00:00
    assert late.returncode != 0 and "inside the US session or the nightly window" in late.stderr
    assert _window("dry-run", "2026-10-18T23:50:00-03:00").returncode != 0  # the dry run is under the window too
    assert _window("host-check", "2026-10-18T23:50:00-03:00").returncode == 0  # the only exempt mode
    evening = _window("grid", "2026-10-18T22:00:00-03:00")  # Sunday 22:00: no US session; the next window opens at 23:30
    assert evening.returncode == 0, evening.stderr
    values = dict(line.split("=", 1) for line in evening.stdout.splitlines())
    assert values["stop_before"] == "2026-10-19T02:10:00+00:00" and values["next_window"] == "2026-10-19T02:30:00+00:00"  # 23:10 and 23:30 São Paulo
    assert values["deadline_epoch"] == str(int(datetime(2026, 10, 19, 2, 20, tzinfo=timezone.utc).timestamp()))  # ONE end: 10 minutes before the window
    # the boundaries: 08:15 São Paulo opens, 09:00 New York closes, 16:30 New York opens again
    for mode, now, allowed in (("dry-run", "2026-10-19T08:14:59-03:00", False), ("dry-run", "2026-10-19T08:15:00-03:00", True),
                               ("dry-run", "2026-10-19T08:59:59-04:00", True), ("dry-run", "2026-10-19T09:00:00-04:00", False),
                               ("dry-run", "2026-10-19T16:29:59-04:00", False), ("dry-run", "2026-10-19T16:30:00-04:00", True)):
        assert (_window(mode, now).returncode == 0) is allowed, (mode, now)
    assert _window("grid", "2026-10-19T11:00:00-04:00").returncode != 0  # Monday 11:00 New York: the session
    assert _window("fetch", "2026-10-18T21:00:00-03:00").returncode == 0  # 150 minutes before the window: room for the fetch
    short = _window("fetch", "2026-10-18T22:00:00-03:00")
    assert short.returncode != 0 and "at least 120 needed" in short.stderr
    assert _window("grid", "2026-10-18T23:00:00-03:00").returncode != 0  # less than 35 minutes before the window


ORDER_STEP = "Verify the owner's order"


def _order(tmp_path: Path, **changes: Any) -> tuple[Path, str]:
    order: dict[str, Any] = {"schema": "VALUATION-PIT-BACKTEST-OWNER-ORDER-v1", "prereg": "PREREG_VALUATION_PIT_BACKTEST_US_V1", "modes": ["price-backfill", "fetch", "grid"],
                             "price_pinned_at": "2026-10-18T22:00:01-03:00", "catalogue_pinned_at": "2026-10-18T21:00:00-03:00", "recompute_existing": False,
                             "max_runs_cap": 50, "not_after": "2026-10-23T23:59:00-03:00"}
    order.update(changes)
    content = json.dumps(order, sort_keys=True).encode()
    digest = hashlib.sha256(content).hexdigest()
    folder = tmp_path / "c3po" / "ops" / "owner-orders"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{digest}.json").write_bytes(content)
    return tmp_path, digest


def _verify_order(root: Path, digest: str, **env: str) -> subprocess.CompletedProcess[str]:
    base = {"MODE": "grid", "ORDER": digest, "PIN": "2026-10-19T01:00:01+00:00", "CATALOGUE_PIN": "2026-10-19T00:00:00Z", "MAX_RUNS": "10", "RECOMPUTE": "false",
            "GITHUB_REF": "refs/heads/main", "ORDER_NOW": "2026-10-19T02:00:00+00:00"}
    return _python(ORDER_STEP, str(root), env={**base, **env})


def test_the_owners_order_binds_the_mode_the_pins_the_flag_the_cap_and_the_deadline(tmp_path: Path) -> None:
    root, digest = _order(tmp_path)
    accepted = _verify_order(root, digest)
    assert accepted.returncode == 0 and "owner's order verified" in accepted.stdout, accepted.stderr
    assert _verify_order(root, digest, MODE="fetch", PIN="", CATALOGUE_PIN="").returncode == 0  # fetch: mode and deadline only
    cases = {
        "runs only from main": {"GITHUB_REF": "refs/heads/feature"},
        "does not exist at this revision": {"ORDER": "0" * 64},
        "another price pin": {"PIN": "2026-10-19T01:00:02+00:00"},
        "another catalogue pin": {"CATALOGUE_PIN": "2026-10-19T00:00:01Z"},
        "this recompute_existing flag": {"RECOMPUTE": "true"},
        "exceeds the owner's order's max_runs_cap": {"MAX_RUNS": "51"},
        "has expired": {"ORDER_NOW": "2026-10-24T03:00:00+00:00"},
    }
    for message, env in cases.items():
        result = _verify_order(root, digest, **env)
        assert result.returncode != 0 and message in result.stderr, (message, result.stderr)
    wrong_mode_root, wrong_mode = _order(tmp_path / "m", modes=["fetch"])
    result = _verify_order(wrong_mode_root, wrong_mode)
    assert result.returncode != 0 and "does not authorise mode grid" in result.stderr
    schema_root, schema = _order(tmp_path / "s", schema="OTHER")
    assert "is not a VALUATION-PIT-BACKTEST-OWNER-ORDER-v1" in _verify_order(schema_root, schema).stderr
    tampered_root, tampered = _order(tmp_path / "t")
    path = tampered_root / "c3po" / "ops" / "owner-orders" / f"{tampered}.json"
    path.write_bytes(path.read_bytes() + b" ")
    assert "does not hash to owner_order_sha256" in _verify_order(tampered_root, tampered).stderr
    # the file of THIS checkout: no symbolic link anywhere on its path — neither the file nor a directory
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    linked_root, linked = _order(tmp_path / "l")
    linked_path = linked_root / "c3po" / "ops" / "owner-orders" / f"{linked}.json"
    linked_path.rename(elsewhere / linked_path.name)
    linked_path.symlink_to(elsewhere / linked_path.name)
    assert "holds a symbolic link" in _verify_order(linked_root, linked).stderr
    folder_root, in_folder = _order(tmp_path / "f")
    (folder_root / "c3po" / "ops" / "owner-orders").rename(tmp_path / "orders-elsewhere")
    (folder_root / "c3po" / "ops" / "owner-orders").symlink_to(tmp_path / "orders-elsewhere")
    assert "holds a symbolic link" in _verify_order(folder_root, in_folder).stderr
    # modes: a JSON list of exact names — never a string whose substring names the mode
    for modes, message in (("grid-later", "must be a JSON list of mode names"), (["grid-later", "fetch"], "does not authorise mode grid"),
                           ([["grid"]], "must be a JSON list of mode names")):
        modes_root, digest_of = _order(tmp_path / f"m-{len(str(modes))}", modes=modes)
        result = _verify_order(modes_root, digest_of)
        assert result.returncode != 0 and message in result.stderr, (modes, result.stderr)
    listed_root = tmp_path / "list"
    (listed_root / "c3po" / "ops" / "owner-orders").mkdir(parents=True)
    content = json.dumps([{"schema": "VALUATION-PIT-BACKTEST-OWNER-ORDER-v1"}]).encode()
    (listed_root / "c3po" / "ops" / "owner-orders" / f"{hashlib.sha256(content).hexdigest()}.json").write_bytes(content)
    assert "is not a JSON object" in _verify_order(listed_root, hashlib.sha256(content).hexdigest()).stderr


def test_the_report_reads_only_a_successful_grid_run_of_this_workflow_once(tmp_path: Path) -> None:
    run = {"id": 42, "path": ".github/workflows/valuation-pit-backtest.yml", "event": "workflow_dispatch", "head_branch": "main", "conclusion": "success",
           "repository": {"full_name": "owner/repo"}, "display_title": "Valuation PIT backtest US (PREREG_VALUATION_PIT_BACKTEST_US_V1) — grid"}
    env = {"GITHUB_REPOSITORY": "owner/repo", "MANIFEST_RUN_ID": "42"}

    def provenance(**changes: Any) -> subprocess.CompletedProcess[str]:
        path = tmp_path / "run.json"
        path.write_text(json.dumps({**run, **changes}), encoding="utf-8")
        return _python("Check the grid run's provenance", str(path), env=env)

    assert provenance().returncode == 0
    for changes, message in (({"path": ".github/workflows/other.yml"}, "not a run of this workflow"), ({"head_branch": "feature"}, "not a successful dispatch"),
                             ({"event": "push"}, "not a successful dispatch"), ({"conclusion": "failure"}, "not a successful dispatch"),
                             ({"repository": {"full_name": "fork/repo"}}, "not of this repository"), ({"display_title": "… — report"}, "not a grid chunk")):
        result = provenance(**changes)
        assert result.returncode != 0 and message in result.stderr, (changes, result.stderr)
    # the artifact: its metadata and its manifest must be the complete pre-registered grid with the published hash
    folder = tmp_path / "artifact"
    folder.mkdir()
    manifest: dict[str, Any] = {"schema": backtest.MANIFEST_SCHEMA, "complete": True, "market": "US", "grid_start": "2021-06-01", "step_sessions": 5,
                                "statements": "vintages", "grid": []}
    manifest["manifest_sha256"] = backtest.manifest_sha256(manifest)

    def artifact(content: dict[str, Any], metadata: dict[str, Any] | None = None, *, expected: str | None = None) -> subprocess.CompletedProcess[str]:
        (folder / "manifest.json").write_text(json.dumps(content), encoding="utf-8")
        (folder / "metadata.json").write_text(json.dumps(metadata or {"mode": "grid", "run_id": "42", "partial": False}), encoding="utf-8")
        return _python("Check the grid manifest", str(folder), env={"EXPECTED": expected or manifest["manifest_sha256"], "MANIFEST_RUN_ID": "42"})

    check = _step("Check the grid manifest")["run"]  # the artifact's own SHA256SUMS first (sha256sum is the runner's), then the manifest
    assert check.index("(cd \"$RUNNER_TEMP/manifest\" && sha256sum -c --strict --quiet SHA256SUMS) || {") < check.index("python3 - \"$RUNNER_TEMP/manifest\"")
    assert artifact(manifest).returncode == 0
    assert "not the complete output" in artifact(manifest, {"mode": "grid", "run_id": "42", "partial": True}).stderr
    assert "not the complete output" in artifact(manifest, {"mode": "fetch", "run_id": "42"}).stderr
    for key, value in (("grid_start", "2024-10-02"), ("step_sessions", 1), ("statements", "provider"), ("market", "NASDAQ"), ("complete", False)):
        other = {**manifest, key: value}
        other["manifest_sha256"] = backtest.manifest_sha256(other)
        assert "not the published one" in artifact(other).stderr
        wrong = artifact(other, expected=other["manifest_sha256"])  # published, but not the pre-registered complete grid
        assert wrong.returncode != 0 and f"not the pre-registered complete grid ({key})" in wrong.stderr, (key, wrong.stderr)
    # the single look: a previous reading of this prereg over ANOTHER manifest refuses this one
    previous = tmp_path / "previous"
    prereg_sha = hashlib.sha256(PREREG_PATH.read_bytes()).hexdigest()
    (previous / "7").mkdir(parents=True)
    (previous / "7" / "metadata.json").write_text(json.dumps({"prereg_sha256": prereg_sha, "manifest_sha256": "a" * 64}), encoding="utf-8")
    look = _python("Check the single look", str(previous), str(PREREG_PATH), env={"EXPECTED": "b" * 64})
    assert look.returncode != 0 and "the single look was spent" in look.stderr
    assert _python("Check the single look", str(previous), str(PREREG_PATH), env={"EXPECTED": "a" * 64}).returncode == 0  # the same look, repeated
    # every non-VOID verdict spends the look; a VOID reading read no label: it spends none (a new revision may follow it)
    for verdict in ("FAIL", "PASS", "UNMEASURED", "NEGATIVE"):
        spent = tmp_path / f"spent-{verdict}"
        (spent / "1").mkdir(parents=True)
        (spent / "1" / "metadata.json").write_text(json.dumps({"prereg_sha256": prereg_sha, "manifest_sha256": "a" * 64, "verdict": verdict}), encoding="utf-8")
        refused = _python("Check the single look", str(spent), str(PREREG_PATH), env={"EXPECTED": "b" * 64})
        assert refused.returncode != 0 and "the single look was spent" in refused.stderr, verdict
    voided = tmp_path / "voided"
    (voided / "9").mkdir(parents=True)
    (voided / "9" / "metadata.json").write_text(json.dumps({"prereg_sha256": prereg_sha, "manifest_sha256": "a" * 64, "verdict": "VOID"}), encoding="utf-8")
    assert _python("Check the single look", str(voided), str(PREREG_PATH), env={"EXPECTED": "b" * 64}).returncode == 0
    # the artifact's manifest is bounded before it is parsed
    huge = {**manifest, "padding": "x" * (8 * 1024 * 1024)}
    huge["manifest_sha256"] = backtest.manifest_sha256(huge)
    assert "too large" in artifact(huge, expected=huge["manifest_sha256"]).stderr


def _verify(tmp_path: Path, mode: str, stdout: str, *, prereg: Path = PREREG_PATH, at_commit: bytes | None = None, producer: dict[str, Any] | None = None,
            expected_manifest: str = "", order: str = "", rc: str = "0", served_producer: dict[str, Any] | None = SERVED_PRODUCER) -> subprocess.CompletedProcess[str]:
    raw = tmp_path / "stdout.txt"
    raw.write_text(stdout, encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    for stale in out.iterdir():
        stale.unlink()
    commit_copy = tmp_path / "prereg-at-commit.md"
    commit_copy.write_bytes(prereg.read_bytes() if at_commit is None else at_commit)
    producer_path = tmp_path / "producer.json"
    producer_path.write_text(json.dumps(PRODUCER if producer is None else producer), encoding="utf-8")
    served_path = tmp_path / "served-producer.json"  # rev 2: the served producer at the prereg commit, beside the V3 one (absent: None)
    if served_producer is None:
        served_path.unlink(missing_ok=True)
    else:
        served_path.write_text(json.dumps(served_producer), encoding="utf-8")
    marker = tmp_path / "verify-failed"
    if marker.exists():
        marker.unlink()
    env = {"MODE": mode, "ORDER": order, "RC": rc, "EXPECTED_MANIFEST": expected_manifest, "PREREG_COMMIT": "c" * 40, "RUN_ID": "7", "REVISION": "d" * 40,
           "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md")}
    return _python("Verify and keep aggregates only", str(raw), str(out), str(prereg), str(commit_copy), str(producer_path), str(marker), env=env)


def _real_receipt(store: Synthetic, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], manifest: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    manifest = manifest or store.manifest()
    monkeypatch.setattr(backtest, "get_settings", _settings)
    monkeypatch.setattr(backtest, "Database", lambda settings: store.database)
    monkeypatch.setenv("PGOPTIONS", "")
    monkeypatch.setenv("C3PO_BUILD_SHA", "b" * 40)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(manifest)))
    assert backtest.main(["--manifest", "-", "--prereg", str(PREREG_PATH)]) == 0
    return capsys.readouterr().out, manifest


def test_a_real_receipt_is_accepted_and_every_invalid_reading_is_refused(small: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
                                                                          tmp_path: Path) -> None:
    store = Synthetic(_positive, seed=31, count=60)
    out, manifest = _real_receipt(store, monkeypatch, capsys)
    accepted = _verify(tmp_path, "report", out, expected_manifest=manifest["manifest_sha256"])
    assert accepted.returncode == 0, accepted.stderr
    metadata = json.loads((tmp_path / "out" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["deployed_build_sha"] == "b" * 40 and metadata["manifest_sha256"] == manifest["manifest_sha256"] and metadata["verdict"] == "FAIL"
    assert metadata["code_pins_verified"] == len(backtest.PINNED_FILES) + len(backtest.PINNED_OBJECTS) and metadata["partial"] is False
    assert json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))["payload_sha256"] == json.loads(out)["payload_sha256"]
    assert "verdict FAIL" in (tmp_path / "summary.md").read_text(encoding="utf-8")
    receipt = json.loads(out)

    def tampered(**changes: Any) -> str:
        payload = {**receipt["payload"], **changes}
        return json.dumps({**receipt, "payload": payload, "payload_sha256": official.canonical_sha256(payload)})

    cases = {
        "not the one of this workflow revision": (tampered(prereg_sha256="e" * 64), {}),
        "does not declare its code BOUND": (tampered(code_binding={"status": "MISMATCH"}), {}),
        "not a commit sha": (tampered(code={**receipt["payload"]["code"], "build_sha": "development"}), {}),
        "the deployed code is not the pinned code": (tampered(code={**receipt["payload"]["code"], "files": {}}), {}),
        "not computed over the published grid manifest": (out, {"expected_manifest": "0" * 64}),
        "changed since the commit of its hash receipt": (out, {"at_commit": b"another prereg\n"}),
        "is not the prereg commit's": (out, {"producer": {**PRODUCER, "files": {**PRODUCER["files"], "valuation_pit_rerun.py": "1" * 64}}}),
        "reader objects of its runs": (out, {"producer": {**PRODUCER, "objects": {**PRODUCER["objects"], "app.database.Database.price_bars": "1" * 64}}}),
        "unexpected receipt shape": (json.dumps({k: v for k, v in receipt.items() if k != "provenance"}), {}),
    }
    for message, (text, options) in cases.items():
        options = {"expected_manifest": manifest["manifest_sha256"], **options}
        result = _verify(tmp_path, "report", text, **options)
        assert result.returncode != 0 and message in result.stderr, (message, result.stderr)
    forged = {**receipt, "payload": {**receipt["payload"], "verdict": {**receipt["payload"]["verdict"], "status": "PASS"}}}
    result = _verify(tmp_path, "report", json.dumps(forged), expected_manifest=manifest["manifest_sha256"])
    assert result.returncode != 0 and "does not recompute" in result.stderr
    # a VOID reading is published with its reasons only: no statistic in the summary either
    incomplete = store.manifest(complete=False)
    void_out, _ = _real_receipt(store, monkeypatch, capsys, incomplete)
    (tmp_path / "summary.md").unlink()
    voided = _verify(tmp_path, "report", void_out, expected_manifest=incomplete["manifest_sha256"])
    assert voided.returncode == 0, voided.stderr
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "verdict VOID** — reasons ['manifest_not_complete']" in summary and "IC executable" not in summary
    # a report that did not complete publishes its metadata only, marked partial
    partial = _verify(tmp_path, "report", "", expected_manifest=manifest["manifest_sha256"], rc="1")
    assert partial.returncode == 0 and not (tmp_path / "out" / "report.json").exists()
    assert json.loads((tmp_path / "out" / "metadata.json").read_text(encoding="utf-8"))["partial"] is True
    # a receipt cut short while it was printed (the timeout): metadata only, marked partial, published as an error — never read as a receipt
    cut = _verify(tmp_path, "report", out[:300] + "\n", expected_manifest=manifest["manifest_sha256"])
    assert cut.returncode == 0 and not (tmp_path / "out" / "report.json").exists()
    cut_metadata = json.loads((tmp_path / "out" / "metadata.json").read_text(encoding="utf-8"))
    assert cut_metadata["partial"] is True and cut_metadata["errors"] == ["truncated_last_line"] and "verdict" not in cut_metadata
    assert (tmp_path / "verify-failed").read_text(encoding="utf-8").strip() == "truncated_last_line"


def test_the_grid_manifest_is_checked_and_the_host_outputs_are_reduced_to_aggregates(tmp_path: Path) -> None:
    manifest: dict[str, Any] = {"schema": backtest.MANIFEST_SCHEMA, "grid": [], "complete": False, "owner_order_sha256": "a" * 64}
    manifest["manifest_sha256"] = backtest.manifest_sha256(manifest)
    lines = [{"kind": "t", "as_of": "2021-06-02T04:00:00+00:00", "elapsed_seconds": 12.5, "peak_rss_kb": 409600, "runs": {}},
             {"kind": "manifest", "manifest_sha256": manifest["manifest_sha256"], "manifest": manifest, "complete": False}]
    stdout = "PREFLIGHT disk_kb=9000000 mem_kb=4000000\n" + "".join(json.dumps(line) + "\n" for line in lines)
    accepted = _verify(tmp_path, "grid", stdout, order="a" * 64)
    assert accepted.returncode == 0, accepted.stderr
    assert json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8")) == manifest
    metadata = json.loads((tmp_path / "out" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["elapsed_seconds_this_chunk"] == 12.5 and metadata["peak_rss_kb"] == 409600 and metadata["preflight"] == ["disk_kb=9000000 mem_kb=4000000"]
    # a failed chunk: what it printed is published, marked partial (the job fails after the upload)
    partial = _verify(tmp_path, "grid", stdout, order="a" * 64, rc="1")
    assert partial.returncode == 0 and json.loads((tmp_path / "out" / "metadata.json").read_text(encoding="utf-8"))["partial"] is True
    nothing = _verify(tmp_path, "grid", json.dumps(lines[0]) + "\n", order="a" * 64, rc="137")
    assert nothing.returncode == 0 and not (tmp_path / "out" / "manifest.json").exists()  # killed before its manifest: receipts only, partial
    # killed while printing its last line: that line is dropped, the rest published as partial, and the job fails
    cut = json.dumps(lines[0]) + "\n" + json.dumps(lines[1])[:40] + "\n"
    truncated = _verify(tmp_path, "grid", cut, order="a" * 64)
    assert truncated.returncode == 0 and (tmp_path / "verify-failed").read_text(encoding="utf-8").strip() == "truncated_last_line"
    assert json.loads((tmp_path / "out" / "metadata.json").read_text(encoding="utf-8"))["partial"] is True and (tmp_path / "out" / "receipts.jsonl").exists()
    middle = _verify(tmp_path, "grid", json.dumps(lines[1])[:40] + "\n" + json.dumps(lines[0]) + "\n", order="a" * 64)
    assert middle.returncode != 0 and "is not JSON" in middle.stderr  # only the LAST line may be cut
    bad = {**manifest, "complete": True}
    refused = _verify(tmp_path, "grid", json.dumps({"kind": "manifest", "manifest_sha256": manifest["manifest_sha256"], "manifest": bad}) + "\n", order="a" * 64)
    assert refused.returncode != 0 and "does not recompute" in refused.stderr
    other_order = _verify(tmp_path, "grid", stdout, order="b" * 64)
    assert other_order.returncode != 0 and "owner order" in other_order.stderr
    # the price backfill prints per-symbol lists (missing symbols, errors, rejected rows): only their sizes leave the runner
    backfill = [{"market": market, "bars": 2500, "publication_id": "p", "available_at": "2026-10-18T23:00:00+00:00", "symbols_missing": ["AAA", "BBB"],
                 "errors": {"AAA": "HTTPError: 404", "BBB": "Timeout"}, "symbols_unreproducible": {"CCC": ["2020-01-02"]}, "rows_rejected_incomplete": {"DDD": 1}}
                for market in ("NASDAQ", "NYSE")]
    reduced = _verify(tmp_path, "price-backfill", "".join(json.dumps(item) + "\n" for item in backfill), order="a" * 64)
    assert reduced.returncode == 0, reduced.stderr
    written = (tmp_path / "out" / "price-backfill.json").read_text(encoding="utf-8")
    assert not any(symbol in written for symbol in ("AAA", "BBB", "CCC", "DDD"))
    assert json.loads(written)[0] == {"market": "NASDAQ", "bars": 2500, "publication_id": "p", "available_at": "2026-10-18T23:00:00+00:00", "symbols_missing_count": 2,
                                      "errors_count": 2, "errors_by_type": {"HTTPError": 1, "Timeout": 1}, "symbols_unreproducible_count": 1,
                                      "rows_rejected_incomplete_count": 1}
    assert _verify(tmp_path, "fetch", json.dumps({"market": "NASDAQ"}) + "\n").returncode != 0  # one result per exchange, or nothing is published
    half = _verify(tmp_path, "fetch", json.dumps({"market": "NASDAQ", "fundamentals_persisted": 300}) + "\n", rc="15")
    assert half.returncode == 0 and json.loads((tmp_path / "out" / "fetch.json").read_text(encoding="utf-8")) == [{"market": "NASDAQ", "fundamentals_persisted": 300}]
    # the host check: disk and memory parsed; below 6 GiB for the database, the check itself fails
    host = ("REBOOT absent /run/c3po-security/reboot.pending\nREBOOT pending /var/run/reboot-required\n"
            "DISK 9437184 41943040 /\nMEM MemTotal 8000000\nMEM MemAvailable 5000000\nMEM SwapTotal 0\nMEM SwapFree 0\n"
            + json.dumps({"kind": "host_check", "publications": {"NASDAQ": None}, "coverage": {}, "ingestion_runs": {"running": 1, "blocking": 0}}) + "\n")
    checked = _verify(tmp_path, "host-check", host)
    assert checked.returncode == 0, checked.stderr
    result = json.loads((tmp_path / "out" / "host-check.json").read_text(encoding="utf-8"))
    assert result["disk"] == [{"available_kb": 9437184, "size_kb": 41943040, "mount": "/"}] and result["memory_kb"]["MemAvailable"] == 5000000
    assert result["reboot"] == {"/run/c3po-security/reboot.pending": "absent", "/var/run/reboot-required": "pending"} and not (tmp_path / "verify-failed").exists()
    # below 6 GiB for the database: the host check is PUBLISHED as an error (metadata and summary), then the job fails
    low = _verify(tmp_path, "host-check", host.replace("DISK 9437184", "DISK 6000000"))
    assert low.returncode == 0 and (tmp_path / "verify-failed").read_text(encoding="utf-8").strip() == "disk_below_6_gib"
    low_metadata = json.loads((tmp_path / "out" / "metadata.json").read_text(encoding="utf-8"))
    assert low_metadata["disk_below_6_gib"] is True and low_metadata["errors"] == ["disk_below_6_gib"] and (tmp_path / "out" / "host-check.json").exists()
    assert "less than 6 GiB free" in (tmp_path / "summary.md").read_text(encoding="utf-8")
    fail_step = _step("Fail when the host step failed")["run"]
    assert '[ -e "$RUNNER_TEMP/verify-failed" ]' in fail_step


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to run the host script's leg")
def test_every_host_process_runs_under_what_is_left_of_one_deadline() -> None:
    """MAJOR 1 of the verification: the second leg of a price backfill or a fetch never gets a fresh timeout — every leg
    runs under ``end − now`` of ONE end fixed on the host, and a leg with less than its floor left does not start."""
    remote = _step("Run on the host")["run"]
    leg = remote.split("# >>> leg", 1)[1].split("# <<< leg", 1)[0]
    script = "\n".join([
        "set -uo pipefail", 'date() { echo "$FAKE_NOW"; }', "compose=(echo docker compose)", "leg_env=()", "end=1000", "RUN_TOKEN=7-1", "# >>> leg" + leg,
        'FAKE_NOW=100 leg 60 app.valuation_price_history --market NASDAQ --backfill --months 120; echo "rc=$?"',
        'FAKE_NOW=950 leg 60 app.valuation_price_history --market NYSE --backfill --months 120; echo "rc=$?"',
        "leg_env=(-e PGOPTIONS=read-only)",
        'FAKE_NOW=500 leg 600 app.valuation_pit_grid --dry-run; echo "rc=$?"',
        'FAKE_NOW=300 leg 600 app.valuation_pit_grid --dry-run; echo "rc=$?"',
    ])
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    token = "python -X valuation_pit_run_token=7-1 -m"  # every leg carries the run's token; LAUNCHED is printed only for a leg that starts
    assert result.stdout.splitlines() == [
        "LAUNCHED 7-1",
        f"docker compose exec -T api timeout -s TERM -k 120 900 nice -n 10 {token} app.valuation_price_history --market NASDAQ --backfill --months 120", "rc=0",
        "rc=25",  # 50 s left: the NYSE leg does not start (a fresh timeout would have given it the whole window again)
        "rc=25",  # the dry run needs 10 minutes
        "LAUNCHED 7-1",
        f"docker compose exec -T -e PGOPTIONS=read-only api timeout -s TERM -k 120 700 nice -n 10 {token} app.valuation_pit_grid --dry-run", "rc=0"], result.stderr
    assert "only 50 s left before the next window (60 s needed): not started" in result.stderr
    backfill = remote.rsplit("price-backfill)\n", 1)[1].split(";;", 1)[0]
    assert "for market in NASDAQ NYSE; do" in backfill and 'leg 60 app.valuation_price_history --market "$market"' in backfill and "end=" not in backfill


@pytest.mark.skipif(shutil.which("git") is None or shutil.which("bash") is None or shutil.which("sha256sum") is None, reason="git, bash and sha256sum")
def test_the_prereg_commit_is_the_last_that_changed_the_prereg_and_the_producer_is_the_grids(tmp_path: Path) -> None:
    """MINOR 2 and 3: the workflow reads the prereg and the producer at ``prereg_commit``, which must be the LAST commit
    that changed the prereg at the run's revision; its producer — the files and the Database reader methods, hashed from the
    commit's text — is exactly the grid's ``producer()`` (the ``--expect-producer-sha256`` the host compares)."""
    from app import valuation_pit_grid as grid
    repo = tmp_path / "repo"
    app_dir, docs = repo / "c3po" / "backend" / "app", repo / "c3po" / "docs"
    app_dir.mkdir(parents=True)
    docs.mkdir(parents=True)
    from app import valuation_pit_served as served
    (app_dir / "market_data").mkdir()
    for name in sorted({*pit.IMPLEMENTATION_FILES, *served.IMPLEMENTATION_FILES, "database.py", "source_identity.py"}):  # rev 2: the served producer too
        shutil.copyfile(ROOT / "c3po" / "backend" / "app" / name, app_dir / name)
    shutil.copyfile(PREREG_PATH, docs / PREREG_PATH.name)
    identity = {"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "", "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "", "GIT_CONFIG_NOSYSTEM": "1",
                "HOME": str(tmp_path)}

    def git(*args: str) -> str:
        return subprocess.run(["git", "-c", "user.useConfigOnly=false", *args], cwd=repo, check=True, capture_output=True, text=True,
                              env={**os.environ, **identity}).stdout.strip()

    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "the prereg and its producer")
    first = git("rev-parse", "HEAD")
    step = _step("Read the pre-registration and the producer at the prereg commit")["run"]

    def run(commit: str) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
        runner = tmp_path / f"runner-{commit[:8]}"
        runner.mkdir(exist_ok=True)
        output = runner / "output"
        output.write_text("", encoding="utf-8")
        result = subprocess.run(["bash", "-c", step], cwd=repo, capture_output=True, text=True,
                                env={**os.environ, "PREREG_COMMIT": commit, "RUNNER_TEMP": str(runner), "GITHUB_OUTPUT": str(output)})
        return result, dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines() if "=" in line)

    result, outputs = run(first)
    assert result.returncode == 0, result.stderr
    assert outputs["producer_sha256"] == grid.producer()["engine_sha256"]  # the workflow's producer IS the grid's, files and reader objects
    producer = json.loads((tmp_path / f"runner-{first[:8]}" / "producer.json").read_text(encoding="utf-8"))
    assert producer == {"files": grid.engine_files(), "objects": grid.engine_objects()}
    assert outputs["served_producer_sha256"] == served.producer()["engine_sha256"]  # rev 2: the served producer IS the grid's served producer
    served_producer = json.loads((tmp_path / f"runner-{first[:8]}" / "served-producer.json").read_text(encoding="utf-8"))
    assert served_producer == {"files": served.implementation_files(), "objects": served.implementation_objects()}
    (repo / "c3po" / "docs" / PREREG_PATH.name).write_text(PREREG_PATH.read_text(encoding="utf-8") + "\nrevisão\n", encoding="utf-8")
    git("commit", "-q", "-am", "a new revision")
    stale, _ = run(first)
    assert stale.returncode != 0 and "is not the last commit that changed the pre-registration" in stale.stderr


def _remote(tmp_path: Path, mode: str, *, reboot: bool, stubs: dict[str, str] | None = None, meminfo_text: str | None = None
            ) -> tuple[subprocess.CompletedProcess[str], str]:
    """The host script of "Run on the host", run for real on stubs (docker, df, systemctl, flock, date): its paths moved
    into ``tmp_path`` (the app directory, the two reboot flags, /proc/meminfo). ``stubs`` replaces a stub's body (a query
    that fails); ``meminfo_text`` replaces /proc/meminfo."""
    script = _step("Run on the host")["run"].split("<<'REMOTE' || rc=$?\n", 1)[1].split("\nREMOTE\n", 1)[0]
    app, flags, bin_dir = tmp_path / "app", tmp_path / "flags", tmp_path / "bin"
    for folder in (app / "runtime" / "security", flags, bin_dir):
        folder.mkdir(parents=True, exist_ok=True)
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: 8000000 kB\nMemAvailable: 5000000 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n" if meminfo_text is None else meminfo_text,
                       encoding="utf-8")
    for flag in ("reboot.pending", "reboot-required"):
        path = flags / flag
        if reboot:
            path.write_text("", encoding="utf-8")
        elif path.exists():
            path.unlink()
    script = (script.replace("/opt/chief-of-staff-digital", str(app)).replace("/run/c3po-security/reboot.pending", str(flags / "reboot.pending"))
              .replace("/var/run/reboot-required", str(flags / "reboot-required")).replace("/proc/meminfo", str(meminfo)))
    log = tmp_path / "calls.log"
    bodies = {
        "docker": ('echo "docker $*" >> "$STUB_LOG"\ncase "$*" in\n  *" ps -q api"*) echo cafe ;;\n  "inspect "*) echo running ;;\n'
                   '  *"--host-check"*) echo \'{"kind": "host_check", "ingestion_runs": {"running": 0, "blocking": 0}}\' ;;\nesac'),
        "df": 'echo "Filesystem 1024-blocks Used Available Capacity Mounted"\nfor arg in "$@"; do [ "$arg" = -P ] || echo "fs 41943040 0 9437184 0% $arg"; done',
        "systemctl": '[ "$1" = show ] && echo n/a\nexit 0',
        "flock": "exit 0",
        "date": ('if [ "$1" = -d ]; then python3 -c \'import datetime, sys; print(int(datetime.datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00"))'
                 '.timestamp()))\' "$2"; else /bin/date "$@"; fi'),
    }
    bodies.update(stubs or {})
    for name, body in bodies.items():
        stub = bin_dir / name
        stub.write_text("#!/bin/bash\n" + body + "\n", encoding="utf-8")
        stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "STUB_LOG": str(log), "MODE": mode, "ORDER": "", "PIN": "2026-10-19T01:00:01+00:00",
           "CATALOGUE_PIN": "2026-10-19T00:00:00+00:00", "MAX_RUNS": "10", "RECOMPUTE": "false", "STOP_BEFORE": "2026-10-19T02:10:00+00:00",
           "DEADLINE": "3600", "PRODUCER": "", "RUN_ID": "7", "RUN_TOKEN": "7-1"}
    if log.exists():
        log.unlink()
    result = subprocess.run(["bash", "-s"], input=script, capture_output=True, text=True, env=env)
    return result, log.read_text(encoding="utf-8") if log.exists() else ""


@pytest.mark.skipif(shutil.which("bash") is None or shutil.which("python3") is None, reason="bash and python3 run the host script on stubs")
def test_the_host_check_shows_a_pending_reboot_and_every_other_mode_refuses_on_it(tmp_path: Path) -> None:
    checked, calls = _remote(tmp_path, "host-check", reboot=True)
    assert checked.returncode == 0, checked.stderr
    assert f"REBOOT pending {tmp_path / 'flags' / 'reboot.pending'}" in checked.stdout and f"REBOOT pending {tmp_path / 'flags' / 'reboot-required'}" in checked.stdout
    assert "MEM MemAvailable 5000000" in checked.stdout and "--host-check" in calls and "timeout" not in calls
    for mode in ("report", "dry-run"):
        refused, calls = _remote(tmp_path, mode, reboot=True)
        assert refused.returncode == 11 and "the backtest must wait for recovery" in refused.stderr and "valuation_pit_grid --market US --price" not in calls, mode
    report, calls = _remote(tmp_path, "report", reboot=False)
    assert report.returncode == 0 and "PREFLIGHT report ok" in report.stdout, report.stderr
    dry, calls = _remote(tmp_path, "dry-run", reboot=False)
    assert dry.returncode == 0, dry.stderr
    assert "-e PGOPTIONS=-c default_transaction_read_only=on api timeout -s TERM -k 120" in calls and "--dry-run" in calls


DATE_D = ('if [ "$1" = -d ]; then python3 -c \'import datetime, sys; print(int(datetime.datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00"))'
          '.timestamp()))\' "$2"; else /bin/date "$@"; fi')
TIMER = 'case "$*" in\n  *--type=timer*) echo "r2d2-session.timer loaded active waiting R2D2 session" ;;\n  show*) echo "{next}" ;;\nesac\nexit 0'
HOST_CHECK = ('echo "docker $*" >> "$STUB_LOG"\ncase "$*" in\n  *" ps -q api"*) echo cafe ;;\n  "inspect "*) echo running ;;\n'
              '  *"--host-check"*) echo \'{body}\' ;;\nesac')


@pytest.mark.skipif(shutil.which("bash") is None or shutil.which("python3") is None, reason="bash and python3 run the host script on stubs")
def test_every_query_of_the_host_preflight_fails_closed_before_any_leg(tmp_path: Path) -> None:
    """P1 of the review of #453: a query of the preflight that cannot answer — systemctl exiting 42 with no output, an
    unreadable timer, the clock, the deploy lock, the free disk, the memory, the ingestion check — REFUSES the run with its own
    status before any leg starts (no LAUNCHED line, no python of a leg); with every query answering, both fetch legs start."""
    started, calls = _remote(tmp_path, "fetch", reboot=False)
    assert started.returncode == 0, started.stderr
    assert started.stdout.count("LAUNCHED 7-1") == 2 and "PREFLIGHT disk_kb=9437184 mem_kb=5000000" in started.stdout
    assert "python -X valuation_pit_run_token=7-1 -m app.valuation_pit_rerun --market NASDAQ --fetch" in calls
    assert "python -X valuation_pit_run_token=7-1 -m app.valuation_pit_rerun --market NYSE --fetch --no-macro" in calls
    cases: dict[str, tuple[int, dict[str, str], str | None]] = {
        "services query exits 42 with no output": (27, {"systemctl": 'case "$*" in *--type=service*) exit 42 ;; esac\n[ "$1" = show ] && echo n/a\nexit 0'}, None),
        "every systemctl query exits 42": (27, {"systemctl": "exit 42"}, None),
        "timers query fails": (28, {"systemctl": 'case "$*" in *--type=timer*) exit 42 ;; esac\nexit 0'}, None),
        "timer next elapse unreadable": (29, {"systemctl": 'case "$*" in *--type=timer*) echo "r2d2-session.timer loaded active waiting x" ;; show*) exit 3 ;; esac\nexit 0'}, None),
        "timer next elapse unparsable": (30, {"systemctl": TIMER.format(next="soon")}, None),
        "timer due inside the run": (19, {"systemctl": TIMER.format(next="2026-10-19T02:30:00+00:00")}, None),
        "service active": (19, {"systemctl": 'case "$*" in *--type=service*) echo "r2d2-session.service loaded active running x" ;; esac\nexit 0'}, None),
        "STOP_BEFORE unparsable": (18, {"date": 'if [ "$1" = -d ]; then exit 1; else /bin/date "$@"; fi'}, None),
        "host clock unreadable": (26, {"date": 'if [ "$1" = +%s ]; then exit 1; fi\n' + DATE_D}, None),
        "host clock not an epoch": (26, {"date": 'if [ "$1" = +%s ]; then exit 0; fi\n' + DATE_D}, None),
        "ingestion check fails": (20, {"docker": HOST_CHECK.format(body="x") + "\ncase \"$*\" in *--host-check*) exit 1 ;; esac"}, None),
        "ingestion check unreadable": (31, {"docker": HOST_CHECK.format(body='{"kind": "host_check"}')}, None),
        "ingestion check negative": (31, {"docker": HOST_CHECK.format(body='{"kind": "host_check", "ingestion_runs": {"blocking": -1}}')}, None),
        "blocking ingestion": (21, {"docker": HOST_CHECK.format(body='{"kind": "host_check", "ingestion_runs": {"blocking": 1}}')}, None),
        "free disk unreadable": (22, {"df": "exit 1"}, None),
        "free disk empty": (22, {"df": "exit 0"}, None),
        "memory unreadable": (32, {}, "MemTotal: 8000000 kB\n"),
        "deploy lock held": (17, {"flock": "exit 1"}, None),
        "deploy lock error": (34, {"flock": "exit 66"}, None),
    }
    for name, (status, stubs, meminfo) in cases.items():
        refused, calls = _remote(tmp_path, "fetch", reboot=False, stubs=stubs, meminfo_text=meminfo)
        assert refused.returncode == status, (name, refused.returncode, refused.stderr)
        assert "LAUNCHED" not in refused.stdout and "valuation_pit_rerun" not in calls and "timeout" not in calls, name
    # the report's preflight refuses the same way; the read-only host check refuses an unreadable disk or memory too
    report, calls = _remote(tmp_path, "report", reboot=False, stubs={"systemctl": "exit 42"})
    assert report.returncode == 27 and "PREFLIGHT report ok" not in report.stdout
    for status, stubs, meminfo in ((13, {"df": "exit 1"}, None), (14, {}, "")):
        checked, calls = _remote(tmp_path, "host-check", reboot=False, stubs=stubs, meminfo_text=meminfo)
        assert checked.returncode == status and "--host-check" not in calls, (status, checked.stderr)


def _stop(tmp_path: Path, token: str, *, stdout: str | None = None, report: str | None = None) -> tuple[subprocess.CompletedProcess[str], str]:
    """The cleanup step, run for real: ``ssh`` and ``docker`` are stubs that hand the remote ``pkill`` to the REAL pkill of
    this machine (the pattern names this run's token: nothing else can match it)."""
    runner, bin_dir, log = tmp_path / "runner", tmp_path / "stop-bin", tmp_path / "stop.log"
    for folder in (runner / "raw", bin_dir):
        folder.mkdir(parents=True, exist_ok=True)
    for name, content in (("stdout.txt", stdout), ("report.txt", report)):
        path = runner / "raw" / name
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(content, encoding="utf-8")
    stubs = {
        "ssh": 'echo "ssh $*" >> "$STUB_LOG"\nfor last; do :; done\neval "${last#"cd /opt/chief-of-staff-digital && "}"',
        "docker": 'echo "docker $*" >> "$STUB_LOG"\nwhile [ "$#" -gt 0 ] && [ "$1" != api ]; do shift; done\nshift\nexec "$@"',
    }
    for name, body in stubs.items():
        stub = bin_dir / name
        stub.write_text("#!/bin/bash\n" + body + "\n", encoding="utf-8")
        stub.chmod(0o755)
    log.unlink(missing_ok=True)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "STUB_LOG": str(log), "RUNNER_TEMP": str(runner), "RUN_TOKEN": token,
           "HOST": "host.invalid", "USER": "deploy", "HOME": str(tmp_path)}
    result = subprocess.run(["bash", "-c", _step(STOP_STEP)["run"]], capture_output=True, text=True, env=env)
    return result, log.read_text(encoding="utf-8") if log.exists() else ""


@pytest.mark.skipif(shutil.which("bash") is None or shutil.which("python3") is None, reason="bash and python3 run the host script on stubs")
def test_the_cleanup_does_nothing_when_this_run_launched_nothing(tmp_path: Path) -> None:
    """P2 of the review of #453: a refusal of the preflight launched nothing, so the cleanup stops nothing — no ssh at all."""
    refused, _calls = _remote(tmp_path, "fetch", reboot=False, stubs={"systemctl": "exit 42"})
    assert refused.returncode == 27 and "LAUNCHED" not in refused.stdout
    for stdout, report in ((refused.stdout, None), (None, None), ("PREFLIGHT report ok\n", ""), ("LAUNCHED 7-2\nLAUNCHED 17-1\n", "LAUNCHED 7-10\n")):
        result, log = _stop(tmp_path, "7-1", stdout=stdout, report=report)  # another attempt's or another run's LAUNCHED is not this run's
        assert result.returncode == 0 and "launched no process on the host: nothing to stop" in result.stdout and log == "", (stdout, report)
    assert _stop(tmp_path, "7", stdout="LAUNCHED 7\n")[0].returncode != 0  # a token that is not <run id>-<attempt> stops nothing
    assert _stop(tmp_path, "7", stdout="LAUNCHED 7\n")[1] == ""


@pytest.mark.skipif(shutil.which("bash") is None or shutil.which("pkill") is None, reason="bash and pkill run the cleanup on stubs")
def test_the_cleanup_stops_only_the_processes_carrying_this_runs_token(tmp_path: Path) -> None:
    """P2 of the review of #453: the cleanup's real ``pkill`` stops this run's leg and never an independent process — a manual
    ``valuation_price_history --nightly`` (no token) or another run's leg (a token that only extends this one)."""
    package = tmp_path / "pkg" / "app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "valuation_dummy.py").write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    token = f"{os.getpid()}{int.from_bytes(os.urandom(3), 'big')}-1"
    run_id, attempt = token.split("-")

    def start(*marker: str, args: tuple[str, ...] = ()) -> subprocess.Popen[bytes]:
        return subprocess.Popen([sys.executable, *marker, "-m", "app.valuation_dummy", *args], cwd=tmp_path / "pkg", stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)

    mine = start("-X", f"valuation_pit_run_token={token}", args=("--market", "NASDAQ", "--fetch"))
    others = [start(args=("--nightly",)), start("-X", f"valuation_pit_run_token={token}0"), start("-X", f"valuation_pit_run_token=1{token}"),
              start("-X", f"valuation_pit_run_token={run_id}-{int(attempt) + 1}")]
    try:
        result, log = _stop(tmp_path, token, stdout=f"PREFLIGHT disk_kb=1 mem_kb=1\nLAUNCHED {token}\n")
        assert result.returncode == 0 and f"a process of this run (token {token}) was running" in result.stdout, (result.stdout, result.stderr)
        assert f"pkill -TERM -f valuation_pit_run_token={token} -m app[.]valuation_" in log
        assert mine.wait(timeout=20) == -15  # SIGTERM
        assert all(other.poll() is None for other in others)  # the manual nightly and the other runs are untouched
        again, _log = _stop(tmp_path, token, report=f"LAUNCHED {token}\n")  # the report's LAUNCHED counts too; nothing of this run is left
        assert again.returncode == 0 and f"no process of this run (token {token})" in again.stdout
        assert all(other.poll() is None for other in others)
    finally:
        for process in (mine, *others):
            if process.poll() is None:
                process.kill()
                process.wait(timeout=20)
