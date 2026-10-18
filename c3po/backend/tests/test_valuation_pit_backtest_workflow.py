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
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from app import valuation_official as official
from app import valuation_pit_backtest_report as backtest
from app import valuation_pit_rerun as pit
from tests.test_valuation_pit_backtest_report import ENGINE, PREREG_PATH, Synthetic, _positive, _settings, small  # noqa: F401  (small: a fixture)

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "valuation-pit-backtest.yml"


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
    assert 'run=(timeout -s TERM -k 120 "$DEADLINE" nice -n 10 python -m)' in remote and remote.count('"${run[@]}"') == 4
    assert "--backfill --months 120" in remote and "--market NYSE --fetch --no-macro" in remote and '--stop-before "$STOP_BEFORE"' in remote
    assert '--expect-producer-sha256 "$PRODUCER"' in remote and '--catalogue-pinned-at "$CATALOGUE_PIN"' in remote and "--statements vintages --step-sessions 5" in remote
    for guard in ("/var/run/reboot-required", "/run/c3po-security/reboot.pending", "systemctl list-units --type=timer", "--state=active,activating,reloading",
                  "'r2d2*' 'c3po-massive*'", "NextElapseUSecRealtime", "ingestion_runs_running_12h", "6291456 + reserve", "3145728", "MAX_RUNS * 2 * 10240",
                  "price-backfill) reserve=2097152", "fetch) reserve=524288", "/mnt/day-d-data", "MemAvailable"):
        assert guard in remote, guard
    report = _step("Run the report on the host")["run"]
    assert '< "$RUNNER_TEMP/manifest/manifest.json"' in report and "--manifest -" in report
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "MANIFEST_B64" not in text and "base64" not in text  # the manifest travels on stdin, never in argv or the environment
    assert "set -e\n" not in text and "set -euo" not in text  # every guard explicit
    secret_steps = {step["name"] for job in workflow["jobs"].values() for step in job["steps"] if "secrets." in json.dumps(step)}
    assert secret_steps == {"Configure deployment SSH key", "Run on the host", "Run the report on the host", "Stop the host process on cancel or failure"}
    assert "stderr.log" in remote and "cat \"$raw/stderr.log\"" not in remote  # the remote stderr is counted, never printed
    stop = _step("Stop the host process on cancel or failure")
    assert stop["if"].startswith("(cancelled() || failure())") and "pkill -TERM -f 'app.valuation_(pit_grid|price_history|pit_rerun)'" in stop["run"]
    producer_step = _step("Read the pre-registration and the producer at the prereg commit")["run"]
    listed = producer_step.split("for name in", 1)[1].split("; do", 1)[0].replace("\\", " ").split()
    assert tuple(listed) == pit.IMPLEMENTATION_FILES  # the producer the workflow checks is the run manifest's, file for file
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
    assert values["deadline_seconds"] == str(80 * 60)  # the process ends 10 minutes before the window
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


def _verify(tmp_path: Path, mode: str, stdout: str, *, prereg: Path = PREREG_PATH, at_commit: bytes | None = None, producer: dict[str, str] | None = None,
            expected_manifest: str = "", order: str = "", rc: str = "0") -> subprocess.CompletedProcess[str]:
    raw = tmp_path / "stdout.txt"
    raw.write_text(stdout, encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    for stale in out.iterdir():
        stale.unlink()
    commit_copy = tmp_path / "prereg-at-commit.md"
    commit_copy.write_bytes(prereg.read_bytes() if at_commit is None else at_commit)
    producer_path = tmp_path / "producer.json"
    producer_path.write_text(json.dumps(ENGINE if producer is None else producer), encoding="utf-8")
    env = {"MODE": mode, "ORDER": order, "RC": rc, "EXPECTED_MANIFEST": expected_manifest, "PREREG_COMMIT": "c" * 40, "RUN_ID": "7", "REVISION": "d" * 40,
           "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md")}
    return _python("Verify and keep aggregates only", str(raw), str(out), str(prereg), str(commit_copy), str(producer_path), env=env)


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
        "is not the code of the prereg commit": (out, {"producer": {**ENGINE, "valuation_pit_rerun.py": "1" * 64}}),
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
    host = ("DISK 9437184 41943040 /\nMEM MemTotal 8000000\nMEM MemAvailable 5000000\nMEM SwapTotal 0\nMEM SwapFree 0\n"
            + json.dumps({"kind": "host_check", "publications": {"NASDAQ": None}, "coverage": {}, "ingestion_runs_running_12h": 0}) + "\n")
    checked = _verify(tmp_path, "host-check", host)
    assert checked.returncode == 0, checked.stderr
    result = json.loads((tmp_path / "out" / "host-check.json").read_text(encoding="utf-8"))
    assert result["disk"] == [{"available_kb": 9437184, "size_kb": 41943040, "mount": "/"}] and result["memory_kb"]["MemAvailable"] == 5000000
    low = _verify(tmp_path, "host-check", host.replace("DISK 9437184", "DISK 6000000"))
    assert low.returncode != 0 and "less than 6 GiB free" in low.stderr
