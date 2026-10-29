"""``.github/workflows/valuation-asfiled-receipt.yml``: the read-only as-filed receipt as the workflow carries it — its
inner Python run against a fake ``app`` (the real ``valuation_env``) and its post-filter run by bash. The primary receipt
(WORKER/SWITCH/RUNS/RUN) is always delivered; the Decisor's clocks are optional context under a bounded budget, so a
stalled or refused second connection prints a fixed reason and never holds the receipt (Codex 6486289773); a count field
that is null, a bool or another type prints ``na`` (Codex 6473684710 P3-2); a receipt is exactly one accepted line of each
mandatory kind (P3-1)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "valuation-asfiled-receipt.yml"
APP = Path(__file__).resolve().parents[1] / "app"

FAKE_DATABASE = '''
import os, time
from contextlib import contextmanager
from datetime import datetime, timezone

T = datetime(2026, 10, 29, 0, 22, 53, 123456, tzinfo=timezone.utc)
CALLS = {"n": 0}


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Connection:
    def execute(self, sql, params=None):
        if sql.startswith("SET "):
            return _Result([])
        if "valuation_decisions" in sql:
            if os.environ["FAKE_DECISOR"] == "query_fails":
                raise RuntimeError("relation does not exist")
            return _Result([(datetime(2026, 10, 29, 4, 9, tzinfo=timezone.utc), datetime(2026, 10, 29, 4, 1, 0, 500000, tzinfo=timezone.utc))])
        assert "sec_asfiled" in sql
        return _Result([
            ("succeeded", T, T, 597, 2206, {"issuers": 597, "failed_issuers": [], "observed_issuers": ["x"] * 597,
                                             "unattributed_failures": 0, "header_failures": 0}, True),
            ("succeeded", T, T, 597, 0, {"issuers": None, "failed_issuers": None, "observed_issuers": False,
                                          "unattributed_failures": True, "header_failures": "3"}, False),
            ("running", T, None, 0, 0, {}, False)])


class Database:
    def __init__(self, settings):
        pass

    @contextmanager
    def connection(self):
        CALLS["n"] += 1
        if CALLS["n"] == 2:
            mode = os.environ["FAKE_DECISOR"]
            if mode == "stall":
                time.sleep(60)
            if mode == "refused":
                raise ConnectionRefusedError("connection refused")
        yield _Connection()
'''


def _run_script() -> str:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]["receipt"]["steps"][1]["run"]


def _inner_python() -> str:
    remote = _run_script().split("<<'REMOTE'", 1)[1].split("\nREMOTE\n", 1)[0]
    return remote.split("<<'PY' || exit 14\n", 1)[1].split("\nPY\n", 1)[0]


def _post_filter() -> str:
    """The workflow's own post-processing: the lines after the remote heredoc."""
    return _run_script().split("\nREMOTE\n", 1)[1]


def _fake_app(root: Path) -> Path:
    package = root / "app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "config.py").write_text("def get_settings():\n    return None\n")
    (package / "database.py").write_text(FAKE_DATABASE)
    shutil.copy(APP / "valuation_env.py", package / "valuation_env.py")
    return root


def _receipt(tmp_path: Path, decisor: str) -> tuple[str, float]:
    root = _fake_app(tmp_path / "fake")
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(root), "RUNS": "3", "RAW_ENABLED": "false",
           "RAW_BACKFILL": "0", "FAKE_DECISOR": decisor}
    start = time.monotonic()
    # run from the fake root: ``python -`` puts the working directory first on sys.path (the real ``app`` must not shadow it)
    done = subprocess.run([sys.executable, "-"], input=_inner_python(), text=True, capture_output=True, env=env, timeout=60, cwd=root)
    assert done.returncode == 0, done.stderr
    lines = ["WORKER state=running started=2026-10-29T00:21:23.123456789Z", *done.stdout.splitlines()]
    return "\n".join(lines) + "\n", time.monotonic() - start


def _filtered(tmp_path: Path, out: str, rc: int = 0) -> subprocess.CompletedProcess:
    (tmp_path / "out.txt").write_text(out)
    script = "rc=%d\n%s" % (rc, _post_filter())
    env = {"PATH": os.environ.get("PATH", ""), "RUNNER_TEMP": str(tmp_path), "GITHUB_STEP_SUMMARY": str(tmp_path / "summary")}
    return subprocess.run(["bash", "-eo", "pipefail", "-c", script], text=True, capture_output=True, env=env, timeout=30)


def test_the_receipt_and_the_decisor_clocks_at_full_precision(tmp_path: Path) -> None:
    out, _ = _receipt(tmp_path, "ok")
    assert "SWITCH enabled=off setting=false backfill_per_poll=0" in out and "RUNS listed=3" in out
    assert "RUN status=succeeded started=2026-10-29T00:22:53.123456Z" in out
    assert "issuers=na observed=na failed=na unattributed=na header_failures=na" in out  # null, bool, str: never a 0
    assert "DECISOR run instant=2026-10-29T04:01:00.500000Z published=2026-10-29T04:09:00.000000Z" in out
    done = _filtered(tmp_path, out)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "other lines (counted, not printed): 0" in done.stdout and "DECISOR runs listed=1" in done.stdout


@pytest.mark.parametrize(("decisor", "reason", "within"), [("stall", "timeout", 30.0), ("refused", "connect", 10.0),
                                                           ("query_fails", "query", 10.0)])
def test_a_stalled_or_failing_decisor_read_never_holds_the_primary_receipt(tmp_path: Path, decisor: str, reason: str,
                                                                          within: float) -> None:
    out, seconds = _receipt(tmp_path, decisor)
    assert seconds < within  # the 15 s budget, never the job's 10 min
    assert out.index("RUN status=") < out.index("DECISOR unavailable reason=%s" % reason)
    assert "DECISOR runs listed=0" in out
    done = _filtered(tmp_path, out)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "RUNS listed=3" in done.stdout and "DECISOR unavailable reason=%s" % reason in done.stdout


def test_a_receipt_is_exactly_one_accepted_line_of_each_mandatory_kind(tmp_path: Path) -> None:
    out, _ = _receipt(tmp_path, "ok")
    for broken in (out.replace("RUNS listed=3\n", ""), out.replace("SWITCH enabled=off", "SWITCH enabled=OFF"),
                   out + "RUNS listed=3\n", out.replace("DECISOR runs listed=1\n", ""),
                   re.sub(r"RUN status=running[^\n]*\n", "", out)):
        done = _filtered(tmp_path, broken)
        assert done.returncode == 15 and "receipt incomplete" in done.stdout
    assert _filtered(tmp_path, out, rc=14).returncode == 14  # the remote's own failure stays a failure
