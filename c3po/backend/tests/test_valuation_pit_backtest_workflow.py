"""``.github/workflows/valuation-pit-backtest.yml`` (PREREG_VALUATION_PIT_BACKTEST_US_V1 §10, §14): dispatch only, the owner's
order on every mode that writes on the host, read-only sessions for the others, the operating window, and the verifier
that keeps aggregates only — run here as the workflow carries it: a real receipt of the report (from a synthetic store)
accepted against the repository's prereg, every reading that is not valid under the prereg refused, a grid manifest whose
hash does not recompute refused, and the price backfill's per-symbol lists reduced to counts."""
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

from app import valuation_accuracy_report as accuracy
from app import valuation_official as official
from app import valuation_pit_backtest_report as backtest
from tests.test_valuation_pit_backtest_report import ENGINE, NAMES, PREREG_PATH, Synthetic, _positive, _settings, small  # noqa: F401  (small: a fixture)

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


def _verify(tmp_path: Path, mode: str, stdout: str, *, prereg: Path = PREREG_PATH, at_commit: bytes | None = None, producer: dict[str, str] | None = None,
            expected_manifest: str = "", order: str = "") -> subprocess.CompletedProcess[str]:
    raw = tmp_path / "stdout.txt"
    raw.write_text(stdout, encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    commit_copy = tmp_path / "prereg-at-commit.md"
    commit_copy.write_bytes(prereg.read_bytes() if at_commit is None else at_commit)
    producer_path = tmp_path / "producer.json"
    producer_path.write_text(json.dumps(ENGINE if producer is None else producer), encoding="utf-8")
    env = {**os.environ, "MODE": mode, "ORDER": order, "EXPECTED_MANIFEST": expected_manifest, "PREREG_COMMIT": "c" * 40, "RUN_ID": "7", "REVISION": "d" * 40,
           "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md")}
    return subprocess.run([sys.executable, "-", str(raw), str(out), str(prereg), str(commit_copy), str(producer_path)], input=_script("Verify and keep aggregates only"),
                          text=True, capture_output=True, env=env, cwd=ROOT)


def test_the_workflow_is_dispatch_only_and_guards_the_host() -> None:
    workflow = _workflow()
    assert set(workflow[True]) == {"workflow_dispatch"}  # never on push or a schedule
    inputs = workflow[True]["workflow_dispatch"]["inputs"]
    assert inputs["mode"]["options"] == ["host-check", "dry-run", "price-backfill", "fetch", "grid", "report"] and len(inputs) <= 10
    assert workflow["permissions"] == {"contents": "read", "actions": "read"} and workflow["concurrency"]["cancel-in-progress"] is False
    validate = _step("Validate the inputs")["run"]
    assert "price-backfill|fetch|grid)" in validate and "owner_order_sha256 is required" in validate and 'echo "owner order sha256: $ORDER"' in validate
    assert "^[0-9a-f]{64}$" in validate and "^[0-9]{1,4}$" in validate and "^[0-9a-f]{40}$" in validate
    remote = _step("Run on the host")["run"]
    for mode in ("host-check)", "dry-run)", "report)"):
        branch = remote.split(mode, 1)[1].split(";;", 1)[0]
        assert '"${readonly_session[@]}"' in branch, mode  # read-only in PostgreSQL itself
    assert "--backfill --months 120" in remote and "--market NYSE --fetch --no-macro" in remote and '--stop-before "$STOP_BEFORE"' in remote
    assert '--owner-order-sha256 "$ORDER"' in remote and "--statements vintages --step-sessions 5" in remote
    assert "PREREG_VALUATION_PIT_BACKTEST_US_V1.md" in remote and "reboot.pending" in remote
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "set -e\n" not in text and "set -euo" not in text  # every guard explicit
    secret_steps = {step["name"] for job in workflow["jobs"].values() for step in job["steps"] if "secrets." in json.dumps(step)}
    assert secret_steps == {"Configure deployment SSH key", "Run on the host"}
    assert "stderr.log" in remote and "cat \"$raw/stderr.log\"" not in remote  # the remote stderr is counted, never printed


def test_the_window_check_prints_the_stop_instant() -> None:
    result = subprocess.run([sys.executable, "-"], input=_script("Check the operating window"), text=True, capture_output=True, env={**os.environ, "MODE": "host-check"})
    assert result.returncode == 0, result.stderr
    keys = [line.split("=", 1)[0] for line in result.stdout.splitlines()]
    assert keys == ["stop_before", "next_window"]


def _real_receipt(store: Synthetic, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> tuple[str, dict[str, Any]]:
    manifest = store.manifest()
    monkeypatch.setattr(backtest, "get_settings", _settings)
    monkeypatch.setattr(backtest, "Database", lambda settings: store.database)
    monkeypatch.setenv("PGOPTIONS", "")
    monkeypatch.setenv("C3PO_BUILD_SHA", "b" * 40)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(manifest)))
    assert backtest.main(["--manifest", "-", "--prereg", str(PREREG_PATH)]) == 0
    return capsys.readouterr().out, manifest


def test_a_real_receipt_is_accepted_and_every_invalid_reading_is_refused(small: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
                                                                          tmp_path: Path) -> None:
    out, manifest = _real_receipt(Synthetic(_positive, seed=31, count=60), monkeypatch, capsys)
    accepted = _verify(tmp_path, "report", out, expected_manifest=manifest["manifest_sha256"])
    assert accepted.returncode == 0, accepted.stderr
    metadata = json.loads((tmp_path / "out" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["deployed_build_sha"] == "b" * 40 and metadata["manifest_sha256"] == manifest["manifest_sha256"] and metadata["verdict"] == "FAIL"
    assert metadata["code_pins_verified"] == len(backtest.PINNED_FILES) + len(backtest.PINNED_OBJECTS)
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


def test_the_grid_manifest_is_checked_and_the_host_outputs_are_reduced_to_aggregates(tmp_path: Path) -> None:
    manifest: dict[str, Any] = {"schema": backtest.MANIFEST_SCHEMA, "grid": [], "complete": False, "owner_order_sha256": "a" * 64}
    manifest["manifest_sha256"] = backtest.manifest_sha256(manifest)
    lines = [{"kind": "t", "as_of": "2021-06-02T04:00:00+00:00", "elapsed_seconds": 12.5, "runs": {}},
             {"kind": "manifest", "manifest_sha256": manifest["manifest_sha256"], "manifest": manifest, "complete": False}]
    stdout = "".join(json.dumps(line) + "\n" for line in lines)
    accepted = _verify(tmp_path, "grid", stdout, order="a" * 64)
    assert accepted.returncode == 0, accepted.stderr
    assert json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8")) == manifest
    assert json.loads((tmp_path / "out" / "metadata.json").read_text(encoding="utf-8"))["elapsed_seconds_this_chunk"] == 12.5
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
    host = "DISK 1048576 4194304 /\n" + json.dumps({"kind": "host_check", "publications": {"NASDAQ": None}, "coverage": {}}) + "\n"
    checked = _verify(tmp_path, "host-check", host)
    assert checked.returncode == 0, checked.stderr
    assert json.loads((tmp_path / "out" / "host-check.json").read_text(encoding="utf-8"))["disk"] == [{"available_kb": 1048576, "size_kb": 4194304, "mount": "/"}]
    assert _verify(tmp_path, "fetch", json.dumps({"market": "NASDAQ"}) + "\n").returncode != 0  # one result per exchange, or nothing is published
