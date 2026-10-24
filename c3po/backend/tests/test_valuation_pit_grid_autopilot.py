"""``.github/workflows/valuation-pit-grid-autopilot.yml`` and its decision script (PREREG_VALUATION_PIT_BACKTEST_US_V1 §14 d):
the parameters come only from the repository variables and the owner's order of the checkout; a tick is a no-op when the
autopilot is off, after UNTIL, while a backtest run is in progress, once the grid is complete (posted once), inside or too
close to a forbidden window (daylight saving of New York and São Paulo); a retryable refusal is retried, any other failure
stops the autopilot and is posted once; nothing is dispatched while a production deploy can recreate the containers; a grid
begun under one owner order goes on under another only when that one directly supersedes it (owner order 3, past Friday);
the end (UNTIL or the order's not_after) and the link are shown on every tick past the order check, and an end reached with
the grid incomplete is posted once. The decision script runs here as the workflow runs it, over stub payloads."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from collections.abc import Mapping
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / ".github" / "scripts" / "valuation_pit_grid_autopilot.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "valuation-pit-grid-autopilot.yml"
BACKTEST_PATH = ROOT / ".github" / "workflows" / "valuation-pit-backtest.yml"
REPOSITORY = "duduvcastro/c3po-chief-of-staff-intelligence"
TICK_URL = f"https://github.com/{REPOSITORY}/actions/runs/777"
ORDER = "ba24f301f446bad09d030fdb6c3acf7b3c96f71b792b6e5b6bf4b33cac05f744"
PREREG_COMMIT = "7f147409e5b500b819b2e5151f04290be1950db3"
PIN = "2026-10-19T18:30:00-03:00"
VARIABLES = {"C3PO_PIT_GRID_ORDER_SHA256": ORDER, "C3PO_PIT_GRID_PRICE_PIN": PIN, "C3PO_PIT_GRID_CATALOGUE_PIN": PIN,
             "C3PO_PIT_GRID_PREREG_COMMIT": PREREG_COMMIT, "C3PO_PIT_GRID_MAX_RUNS": "40", "C3PO_PIT_GRID_AUTOPILOT": "on",
             "C3PO_PIT_GRID_UNTIL": "2026-10-23T23:30:00-03:00"}
# Wednesday 21/10/2026 18:00 BRT = 17:00 New York (EDT): outside both windows, 330 min before the nightly window (23:30 BRT)
NOW = dt.datetime(2026, 10, 21, 21, 0, tzinfo=dt.timezone.utc)
MANIFEST_SHA = "ab" * 32
ORDERS = ROOT / "c3po" / "ops" / "owner-orders"
ORDER_3 = "7249796f20e4f030fec1f9aee2f9d512349c0827ad456ba5cf5d325fa9ca45e6"  # owner order 3: order 2's grid until Tuesday 27/10 23:30 BRT
ORDER_3_END = "2026-10-27T23:30:00-03:00"
ORDER_3_VARIABLES = {**VARIABLES, "C3PO_PIT_GRID_ORDER_SHA256": ORDER_3, "C3PO_PIT_GRID_UNTIL": ORDER_3_END}
# Saturday 24/10/2026 12:00 BRT: after order 2's not_after; no US session on the weekend, 690 min before the nightly window
SATURDAY = dt.datetime(2026, 10, 24, 15, 0, tzinfo=dt.timezone.utc)
# a stub `gh`: records its argv; `api` serves the run list (before / after a `workflow run`) and the channel's comment pages
STUB_GH = """#!@PYTHON@
import json, os, sys
args = sys.argv[1:]
state = @STATE@
open(@CALLS@, "a").write(json.dumps(args) + "\\n")
if args[:2] == ["workflow", "run"]:
    open(os.path.join(state, "dispatched"), "w").write("1")
elif args and args[0] == "api":
    url = next(item for item in args[1:] if not item.startswith("-"))
    if "/comments" in url:
        name = "stub-comments.json"
    elif "/c3po-pipeline.yml/" in url:
        name = "stub-deploys.jsonl"
    else:
        name = "stub-runs-after.json" if os.path.exists(os.path.join(state, "dispatched")) else "stub-runs-before.json"
    path = os.path.join(state, name)
    if not os.path.exists(path):
        sys.exit(1)
    sys.stdout.write(open(path).read())
"""


def _autopilot() -> ModuleType:
    spec = importlib.util.spec_from_file_location("valuation_pit_grid_autopilot", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["valuation_pit_grid_autopilot"] = module
    spec.loader.exec_module(module)
    return module


AP = _autopilot()


def _stamp(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _run(run_id: int, *, age_minutes: float, conclusion: str | None = "success", status: str = "completed", mode: str = "grid",
         branch: str = "main", event: str = "workflow_dispatch", at: dt.datetime = NOW) -> dict[str, Any]:
    return {"id": run_id, "status": status, "conclusion": conclusion if status == "completed" else None, "event": event, "head_branch": branch,
            "path": ".github/workflows/valuation-pit-backtest.yml", "created_at": _stamp(at - dt.timedelta(minutes=age_minutes)),
            "display_title": f"Valuation PIT backtest US (PREREG_VALUATION_PIT_BACKTEST_US_V1) — {mode}"}


def _metadata(run_id: int, *, complete: bool = False, order: str | None = ORDER) -> dict[str, Any]:
    return {"run_id": str(run_id), "mode": "grid", "partial": False, "owner_order_sha256": order, "complete": complete,
            "manifest_sha256": MANIFEST_SHA, "entries": 120 if not complete else 266, "remaining": 0 if complete else 146}


def _jobs(run_id: int, failed_step: str | None) -> dict[str, Any]:
    names = ["Require exact confirmation", "Validate the inputs", "Check the operating window", "Check out the workflow revision",
             "Verify the owner's order", "Run on the host", "Verify and keep aggregates only", "Fail when the host step failed"]
    steps, failed = [], False
    for number, name in enumerate(names, start=1):
        conclusion = "skipped" if failed else ("failure" if name == failed_step else "success")
        failed = failed or name == failed_step
        steps.append({"number": number, "name": name, "conclusion": conclusion})
    return {"total_count": 1, "jobs": [{"id": 9001, "run_id": run_id, "steps": steps}]}


def _log(status: int) -> str:
    return ("2026-10-21T20:00:00.0000000Z ##[group]Run set -uo pipefail\n"
            '2026-10-21T20:00:00.0000000Z echo "remote exit status: $rc; remote stderr lines (kept private, not printed): $lines"\n'
            f"2026-10-21T20:05:00.0000000Z remote exit status: {status}; remote stderr lines (kept private, not printed): 1\n"
            '2026-10-21T20:05:01.0000000Z   if [ "$RC" != 0 ]; then echo "the host step exited with status $RC (its stderr is kept private)" >&2\n'
            f"2026-10-21T20:05:02.0000000Z the host step exited with status {status} (its stderr is kept private)\n")


def _decide(*, env: dict[str, str] | None = None, now: dt.datetime = NOW, runs: list[dict[str, Any]] | None = None, jobs: Any = None,
            log: str | None = None, metadata: Any = None, failures: Mapping[int, tuple[Any, str | None]] | None = None, root: Path = ROOT,
            deploys: Any = ()) -> Any:
    runs = runs if runs is not None else [_run(100, age_minutes=120, at=now)]
    metadata = metadata if metadata is not None else _metadata(100)
    merged: dict[int, tuple[Any, str | None]] = dict(failures or {})
    if jobs is not None:  # the one failed chunk of most tests
        merged[jobs["jobs"][0]["run_id"]] = (jobs, log)
    return AP.decide(env=env if env is not None else VARIABLES, root=root, now=now, runs=runs, failures=merged, metadata=metadata,
                     deploys=list(deploys) if isinstance(deploys, tuple) else deploys, repository=REPOSITORY, tick_url=TICK_URL)


# ---------------------------------------------------------------------------------------------------------------- the workflow
def _workflow() -> dict[Any, Any]:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _step(name: str) -> dict[str, Any]:
    return next(step for job in _workflow()["jobs"].values() for step in job["steps"] if step.get("name") == name)


def test_the_workflow_ticks_every_30_minutes_with_least_privilege_and_variables_only() -> None:
    workflow = _workflow()
    triggers = workflow[True]
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert triggers["schedule"] == [{"cron": "13,43 * * * *"}]
    assert set(triggers["workflow_dispatch"]["inputs"]) == {"dry_run", "recovery_slot"}  # no grid parameter is an input
    assert triggers["workflow_dispatch"]["inputs"]["dry_run"]["default"] is True and triggers["workflow_dispatch"]["inputs"]["dry_run"]["type"] == "boolean"
    assert workflow["permissions"] == {"contents": "read"} and workflow["concurrency"] == {"group": "valuation-pit-grid-autopilot", "cancel-in-progress": False}
    (job,) = workflow["jobs"].values()
    assert job["permissions"] == {"actions": "write", "contents": "read", "issues": "write"}
    assert job["if"] == "vars.C3PO_PIT_GRID_AUTOPILOT == 'on' || github.event_name == 'workflow_dispatch'"
    for name in AP.VARIABLES:
        assert job["env"][name] == "${{ vars.%s }}" % name
    assert job["env"]["DRY_RUN"] == "${{ github.event_name == 'workflow_dispatch' && inputs.dry_run && 'true' || 'false' }}"
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "secrets." not in text and "ssh " not in text and "C3PO_AWS" not in text  # GITHUB_TOKEN only; never the host
    assert "git push" not in text and "contents: write" not in text  # no repository write: the state is the run history
    assert _step("Check out the autopilot and the owner's orders")["with"] == {"persist-credentials": False}


def test_the_dispatch_carries_only_the_decision_of_the_variables_and_the_fixed_flags() -> None:
    step = _step("Dispatch one grid chunk")
    assert step["if"] == "steps.decide.outputs.action == 'dispatch' && steps.decide.outputs.act == 'true'"
    assert {key: value for key, value in step["env"].items() if key != "GH_TOKEN"} == {
        "ORDER": "${{ steps.decide.outputs.order }}", "PIN": "${{ steps.decide.outputs.price_pin }}",
        "CATALOGUE_PIN": "${{ steps.decide.outputs.catalogue_pin }}", "PREREG_COMMIT": "${{ steps.decide.outputs.prereg_commit }}",
        "MAX_RUNS": "${{ steps.decide.outputs.max_runs }}"}
    assert "inputs." not in step["run"] and "${{" not in step["run"]


def _bash_step(name: str, env: dict[str, str], tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    """Run a step's bash as the workflow carries it, with a stub `gh` that records its argv."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    calls = tmp_path / "gh-calls.jsonl"
    stub = bin_dir / "gh"
    stub.write_text(STUB_GH.replace("@CALLS@", repr(str(calls))).replace("@STATE@", repr(str(tmp_path))).replace("@PYTHON@", sys.executable), encoding="utf-8")
    stub.chmod(0o755)
    summary = tmp_path / "summary.md"
    full_env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_STEP_SUMMARY": str(summary),
                "RUNNER_TEMP": str(tmp_path), "GH_TOKEN": "stub", **env}
    result = subprocess.run(["bash", "-c", _step(name)["run"]], text=True, capture_output=True, env=full_env, cwd=ROOT)
    recorded = [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()] if calls.exists() else []
    return result, recorded


def _run_list(*runs: dict[str, Any]) -> str:
    return json.dumps({"total_count": len(runs), "workflow_runs": list(runs)})


def test_the_dispatch_step_runs_the_backtest_grid_with_the_fixed_flags_and_confirms_it(tmp_path: Path) -> None:
    env = {"ORDER": ORDER, "PIN": PIN, "CATALOGUE_PIN": PIN, "PREREG_COMMIT": PREREG_COMMIT, "MAX_RUNS": "40", "AUTOPILOT_POLL_SECONDS": "0"}
    (tmp_path / "stub-runs-before.json").write_text(_run_list(_run(100, age_minutes=120)), encoding="utf-8")
    (tmp_path / "stub-runs-after.json").write_text(_run_list(_run(101, age_minutes=0, status="queued"), _run(100, age_minutes=120)), encoding="utf-8")
    result, calls = _bash_step("Dispatch one grid chunk", env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert [call for call in calls if call[0] != "api"] == [["workflow", "run", "valuation-pit-backtest.yml", "--repo", REPOSITORY, "--ref", "main",
                      "-f", "confirmation=RUN VALUATION PIT BACKTEST", "-f", "mode=grid", "-f", f"owner_order_sha256={ORDER}",
                      "-f", f"price_pinned_at={PIN}", "-f", f"catalogue_pinned_at={PIN}", "-f", "max_runs=40",
                      "-f", "recompute_existing=false", "-f", f"prereg_commit={PREREG_COMMIT}"]]
    assert calls[0][0] == "api" and calls[1][:2] == ["workflow", "run"] and calls[2][0] == "api"  # listed before, confirmed after
    assert "run 101" in (tmp_path / "summary.md").read_text(encoding="utf-8")
    for bad in ({"MAX_RUNS": "201"}, {"MAX_RUNS": "0"}, {"ORDER": ORDER[:-1]}, {"PIN": "2026-10-19 18:30"}, {"PREREG_COMMIT": "main"}):
        (tmp_path / "gh-calls.jsonl").unlink(missing_ok=True)
        (tmp_path / "dispatched").unlink(missing_ok=True)
        result, calls = _bash_step("Dispatch one grid chunk", {**env, **bad}, tmp_path)
        assert result.returncode != 0 and calls == [], bad


def test_a_dispatch_that_never_appears_fails_the_tick(tmp_path: Path) -> None:
    env = {"ORDER": ORDER, "PIN": PIN, "CATALOGUE_PIN": PIN, "PREREG_COMMIT": PREREG_COMMIT, "MAX_RUNS": "40", "AUTOPILOT_POLL_SECONDS": "0"}
    listing = _run_list(_run(100, age_minutes=120))
    (tmp_path / "stub-runs-before.json").write_text(listing, encoding="utf-8")
    # after the dispatch: only an older run, a non-grid run and a scheduled run are newer than nothing that counts
    (tmp_path / "stub-runs-after.json").write_text(_run_list(_run(102, age_minutes=0, mode="dry-run"), _run(100, age_minutes=120)), encoding="utf-8")
    result, calls = _bash_step("Dispatch one grid chunk", env, tmp_path)
    assert result.returncode != 0 and "did not appear in the run list within 60 s" in result.stderr
    assert sum(1 for call in calls if call[0] == "api") == 13  # one listing before, twelve polls after
    step = _step("Dispatch one grid chunk")["run"]
    assert "interval=${AUTOPILOT_POLL_SECONDS:-5}" in step and "for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do" in step


def test_the_post_step_comments_once_on_the_channel(tmp_path: Path) -> None:
    (tmp_path / "autopilot-comment.md").write_text("<!-- valuation-pit-grid-autopilot:stop:1 -->\nbody\n", encoding="utf-8")
    step = _step("Post once to the Fable-Codex channel")
    assert step["if"] == "steps.decide.outputs.post == 'true' && steps.decide.outputs.act == 'true'"
    result, calls = _bash_step("Post once to the Fable-Codex channel", {"CHANNEL_ISSUE": "429"}, tmp_path)
    assert result.returncode == 0, result.stderr
    assert calls == [["issue", "comment", "429", "--repo", REPOSITORY, "--body-file", str(tmp_path / "autopilot-comment.md")]]


def test_the_names_the_autopilot_reads_are_the_backtest_s() -> None:
    backtest = yaml.safe_load(BACKTEST_PATH.read_text(encoding="utf-8"))
    names = [step["name"] for step in backtest["jobs"]["pit-backtest"]["steps"]]
    assert AP.WINDOW_STEP in names and AP.FAIL_STEP in names and names.index(AP.WINDOW_STEP) < names.index("Run on the host") < names.index(AP.FAIL_STEP)
    text = BACKTEST_PATH.read_text(encoding="utf-8")
    assert 'echo "remote exit status: $rc; remote stderr lines (kept private, not printed): $lines"' in text
    assert 'echo "the host step exited with status $RC (its stderr is kept private)" >&2' in text
    assert backtest["run-name"].endswith("— ${{ inputs.mode }}") and "name: valuation-pit-backtest-${{ inputs.mode }}-${{ github.run_id }}" in text
    assert sorted(AP.RETRYABLE_STATUS) == [11, 17, 19, 21, 25]
    for status, message in ((11, "the backtest must wait for recovery"), (17, "a deploy holds the deployment lock"), (19, "an R2D2/massive host service is active"),
                            (21, "the nightly valuation worker or a long ingestion is running"), (25, "before the next window")):
        assert f"exit {status}" in text or f"return {status}" in text, status
        assert message in text
    assert backtest["jobs"]["pit-backtest"]["steps"][0]["run"].count("RUN VALUATION PIT BACKTEST") == 1 and AP.CONFIRMATION == "RUN VALUATION PIT BACKTEST"


# ---------------------------------------------------------------------------------------------------------------- decisions
def test_off_is_a_no_op() -> None:
    for value in ("off", "", "ON", "true"):
        decision = _decide(env={**VARIABLES, "C3PO_PIT_GRID_AUTOPILOT": value})
        assert (decision.action, decision.reason, decision.post_key) == ("noop", "autopilot_off", None)


def test_a_chunk_is_dispatched_with_the_variables() -> None:
    decision = _decide()
    assert (decision.action, decision.reason) == ("dispatch", "next_chunk")
    assert decision.details["max_runs"] == 40 and decision.details["minutes"] == 330 and decision.post_key is None


def test_after_until_is_a_no_op() -> None:
    late = dt.datetime(2026, 10, 24, 2, 31, tzinfo=dt.timezone.utc)  # 23:31 BRT on Friday 23/10
    assert _decide(now=late).reason == "after_until"
    earlier = {**VARIABLES, "C3PO_PIT_GRID_UNTIL": "2026-10-21T17:59:00-03:00"}  # the variable may end it before the order
    assert _decide(env=earlier).reason == "after_until"
    later = {**VARIABLES, "C3PO_PIT_GRID_UNTIL": "2026-12-31T00:00:00-03:00"}  # never past the order's not_after
    assert _decide(env=later, now=late).reason == "after_until"


def test_a_run_in_progress_of_any_mode_is_a_no_op() -> None:
    for status in ("queued", "in_progress", "waiting", "pending", "requested"):
        for mode in ("grid", "dry-run", "host-check", "report"):
            runs = [_run(101, age_minutes=20, status=status, mode=mode), _run(100, age_minutes=120)]
            assert _decide(runs=runs).reason == "run_in_progress", (status, mode)
    assert _decide(runs=[_run(101, age_minutes=5, mode="host-check"), _run(100, age_minutes=120)]).reason == "recent_run"


def test_a_complete_grid_is_a_no_op_posted_once() -> None:
    decision = _decide(metadata=_metadata(100, complete=True))
    assert (decision.action, decision.reason, decision.post_key) == ("noop", "grid_complete", f"complete:{MANIFEST_SHA}")
    assert decision.post_body.startswith(f"<!-- valuation-pit-grid-autopilot:complete:{MANIFEST_SHA} -->\n")
    assert f"grid complete, manifest_sha256 `{MANIFEST_SHA}`" in decision.post_body and "run 100" in decision.post_body
    assert AP.already_posted([decision.post_body], decision.post_key)
    assert not AP.already_posted([f"quoted: {decision.post_body}"], decision.post_key)  # only a FIRST-line marker counts
    # complete wins over a later failed run (nothing more is dispatched)
    runs = [_run(101, age_minutes=60, conclusion="failure"), _run(100, age_minutes=120)]
    assert _decide(runs=runs, metadata=_metadata(100, complete=True), jobs=_jobs(101, "Validate the inputs")).reason == "grid_complete"


def test_no_chunk_of_this_order_yet_dispatches_a_capped_first_chunk_once_posted() -> None:
    for runs in ([_run(100, age_minutes=120, mode="dry-run")], [_run(100, age_minutes=120, branch="feature")], []):
        decision = _decide(runs=runs)
        assert (decision.action, decision.reason) == ("dispatch", "first_chunk")
        assert decision.details["max_runs"] == min(AP.FIRST_CHUNK_MAX_RUNS, 40) and decision.details["after_run"] is None
        assert decision.post_key == "first-chunk" and decision.post_body is not None
        assert decision.post_body.startswith("<!-- valuation-pit-grid-autopilot:first-chunk -->\n")
        assert AP.already_posted([decision.post_body], "first-chunk")
    assert _decide(metadata=_metadata(100, order="cd" * 32)).reason == "last_chunk_of_another_order"
    with pytest.raises(AP.InputError):
        _decide(metadata=_metadata(99))  # the metadata of another run


@pytest.mark.parametrize(("status", "label"), [(17, "deploy_lock"), (19, "r2d2_timer"), (21, "blocking_ingestion"), (25, "window_leg_floor")])
def test_a_retryable_refusal_is_retried(status: int, label: str) -> None:
    runs = [_run(101, age_minutes=30, conclusion="failure"), _run(100, age_minutes=120)]
    decision = _decide(runs=runs, jobs=_jobs(101, AP.FAIL_STEP), log=_log(status))
    assert (decision.action, decision.reason, decision.post_key) == ("dispatch", f"retry_after_{label}", None)
    assert decision.details["retry_of"] == 101 and decision.details["retry_status"] == status


def test_a_window_refusal_is_retried() -> None:
    runs = [_run(101, age_minutes=30, conclusion="failure"), _run(100, age_minutes=120)]
    assert _decide(runs=runs, jobs=_jobs(101, AP.WINDOW_STEP)).reason == "retry_after_window"


@pytest.mark.parametrize(("failed_step", "status", "label"), [
    (AP.FAIL_STEP, 2, "host_exit"),            # a GridError / producer mismatch (argparse error)
    (AP.FAIL_STEP, 1, "host_exit"),            # a run error re-raised after the manifest
    (AP.FAIL_STEP, 124, "host_exit"),          # the deadline's timeout: stops by design
    (AP.FAIL_STEP, 0, "published_as_error"),   # the outputs were published as an error
    (AP.FAIL_STEP, None, "status_unreadable"),
    ("Verify the owner's order", None, "step_failed"),
    ("Verify and keep aggregates only", None, "step_failed"),
])
def test_any_other_failure_stops_and_is_posted_once(failed_step: str, status: int | None, label: str) -> None:
    runs = [_run(101, age_minutes=30, conclusion="failure"), _run(100, age_minutes=120)]
    decision = _decide(runs=runs, jobs=_jobs(101, failed_step), log=_log(status) if status is not None else "no status here\n")
    assert (decision.action, decision.reason, decision.post_key) == ("stop", label, "stop:101")
    assert decision.post_body.startswith("<!-- valuation-pit-grid-autopilot:stop:101 -->\n") and "run 101" in decision.post_body
    assert (f"código remoto `{status}`" if status is not None else "código remoto não lido") in decision.post_body
    # the stop holds on every later tick while that run is the last completed grid chunk — even outside any window
    later = _decide(runs=runs, jobs=_jobs(101, failed_step), log=_log(status) if status is not None else "", now=NOW + dt.timedelta(hours=1))
    assert later.action == "stop"
    # a chunk the operator dispatches by hand and that succeeds reopens the autopilot
    reopened = [_run(102, age_minutes=20, conclusion="success"), *runs]
    assert _decide(runs=reopened, metadata=_metadata(102)).reason == "next_chunk"


def test_a_cancelled_or_timed_out_chunk_stops() -> None:
    for conclusion in ("cancelled", "timed_out", "startup_failure"):
        runs = [_run(101, age_minutes=30, conclusion=conclusion), _run(100, age_minutes=120)]
        decision = _decide(runs=runs, jobs=_jobs(101, None))
        assert (decision.action, decision.reason) == ("stop", f"conclusion_{conclusion}")


def test_an_ambiguous_remote_status_is_unreadable() -> None:
    assert AP.remote_status(_log(17) + _log(2)) is None
    assert AP.remote_status('echo "remote exit status: $rc; remote stderr lines"') is None
    assert AP.remote_status(_log(21)) == 21


def test_parameters_come_only_from_the_variables_and_must_agree_with_the_order() -> None:
    for name, value in (("C3PO_PIT_GRID_PRICE_PIN", "2026-10-19T18:31:00-03:00"), ("C3PO_PIT_GRID_CATALOGUE_PIN", "2026-10-20T18:30:00-03:00"),
                        ("C3PO_PIT_GRID_MAX_RUNS", "201"), ("C3PO_PIT_GRID_MAX_RUNS", "0"), ("C3PO_PIT_GRID_MAX_RUNS", "forty"),
                        ("C3PO_PIT_GRID_ORDER_SHA256", "fd1dea28cbab42090f6a5d19df8d3d93f1e7db0edd91793e42126a015cc184b9"),  # order 1: no grid
                        ("C3PO_PIT_GRID_ORDER_SHA256", "00" * 32), ("C3PO_PIT_GRID_PREREG_COMMIT", "7f14740"), ("C3PO_PIT_GRID_UNTIL", "friday")):
        decision = _decide(env={**VARIABLES, name: value})
        assert (decision.action, decision.reason) == ("noop", "invalid_parameters"), (name, value)
        assert decision.post_key == f"config:{NOW.astimezone(AP.SAO_PAULO).date().isoformat()}" and decision.details["problems"]
    # the same instant written in another zone is the same pin
    assert _decide(env={**VARIABLES, "C3PO_PIT_GRID_PRICE_PIN": "2026-10-19T21:30:00Z"}).action == "dispatch"


# ---------------------------------------------------------------------------------------------------------------- windows
def _utc(*args: int) -> dt.datetime:
    return dt.datetime(*args, tzinfo=dt.timezone.utc)


def test_the_windows_are_the_backtest_s_and_follow_new_york_daylight_saving() -> None:
    # Friday 30/10/2026 (EDT, UTC-4): the session opens 13:00Z; Monday 02/11/2026 (EST, UTC-5): it opens 14:00Z
    assert AP.window_state(_utc(2026, 10, 30, 13, 10))[0] is True
    inside, upcoming = AP.window_state(_utc(2026, 11, 2, 13, 10))
    assert inside is False and upcoming == _utc(2026, 11, 2, 14, 0)
    assert AP.window_state(_utc(2026, 11, 2, 21, 29))[0] is True and AP.window_state(_utc(2026, 11, 2, 21, 31))[0] is False  # 16:30 EST
    # March: New York springs forward on 08/03/2026 — Monday 09/03 opens at 13:00Z, Friday 06/03 at 14:00Z
    assert AP.window_state(_utc(2026, 3, 9, 13, 5))[0] is True and AP.window_state(_utc(2026, 3, 6, 13, 5))[0] is False
    # the weekend has no US session: Saturday 24/10 15:00Z is free (only the nightly window applies)
    assert AP.window_state(_utc(2026, 10, 24, 15, 0)) == (False, _utc(2026, 10, 25, 2, 30))


def test_the_nightly_window_follows_sao_paulo_time_including_its_past_daylight_saving() -> None:
    # today (no DST since 2019): 23:30-08:15 BRT = 02:30Z-11:15Z
    assert AP.window_state(_utc(2026, 10, 22, 2, 29))[0] is False and AP.window_state(_utc(2026, 10, 22, 2, 30))[0] is True
    assert AP.window_state(_utc(2026, 10, 22, 11, 14))[0] is True and AP.window_state(_utc(2026, 10, 22, 11, 16))[0] is False
    # São Paulo summer time (04/11/2018, UTC-2): 23:30 BRST = 01:30Z, 08:15 BRST = 10:15Z
    assert AP.window_state(_utc(2018, 11, 6, 1, 45))[0] is True and AP.window_state(_utc(2018, 11, 6, 10, 20))[0] is False
    assert AP.window_state(_utc(2018, 11, 1, 1, 45))[0] is False  # the week before, still UTC-3: 22:45


def test_inside_or_too_close_to_a_window_is_a_no_op() -> None:
    inside = _utc(2026, 10, 21, 15, 0)  # 11:00 New York
    assert _decide(now=inside).reason == "inside_window"
    close = _utc(2026, 10, 22, 1, 51)  # 22:51 BRT: 39 min before 23:30
    assert (_decide(now=close).reason, _decide(now=close).details["minutes"]) == ("window_too_close", 39)
    assert _decide(now=_utc(2026, 10, 22, 1, 50)).action == "dispatch"  # 40 min: the grid gets its 20 min before --stop-before
    # a retryable refusal is retried only outside the windows too
    runs = [_run(101, age_minutes=30, conclusion="failure", at=inside), _run(100, age_minutes=120, at=inside)]
    assert _decide(now=inside, runs=runs, jobs=_jobs(101, AP.FAIL_STEP), log=_log(17)).reason == "inside_window"
    # a future-dated run (clock skew) counts as recent: nothing is dispatched
    assert _decide(runs=[_run(100, age_minutes=-5)]).reason == "recent_run"


# ---------------------------------------------------------------------------------------------------------------- the CLI
def _cli(tmp_path: Path, *, env: dict[str, str], runs: list[dict[str, Any]], metadata: Any = None, jobs: Any = None, log: str | None = None,
         comments: list[str] | None = None, dry_run: str = "false", ref: str = "refs/heads/main",
         now: dt.datetime = NOW, deploys: Any = ()) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    files = {"runs.json": runs, "comments.json": comments or [], "metadata.json": metadata,
             "deploys.json": list(deploys) if isinstance(deploys, tuple) else deploys}
    for name, payload in files.items():
        (tmp_path / name).unlink(missing_ok=True)
        if payload is not None:
            (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    failed_dir = tmp_path / "failed"
    if failed_dir.exists():
        for item in failed_dir.iterdir():
            item.unlink()
    failed_dir.mkdir(exist_ok=True)
    if jobs is not None:
        run_id = jobs["jobs"][0]["run_id"]
        (failed_dir / f"{run_id}.jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
        if log is not None:
            (failed_dir / f"{run_id}.log").write_text(log, encoding="utf-8")
    output = tmp_path / "output.txt"
    output.write_text("", encoding="utf-8")
    (tmp_path / "comment.md").unlink(missing_ok=True)
    clean = {key: value for key, value in os.environ.items() if not key.startswith("C3PO_PIT_GRID_")}
    result = subprocess.run([sys.executable, "-I", str(SCRIPT_PATH), "decide", "--runs", str(tmp_path / "runs.json"),
                             "--failed-dir", str(failed_dir),
                             "--metadata", str(tmp_path / "metadata.json"), "--deploys", str(tmp_path / "deploys.json"),
                             "--comments", str(tmp_path / "comments.json"), "--root", str(ROOT),
                             "--repository", REPOSITORY, "--tick-url", TICK_URL, "--ref", ref, "--dry-run", dry_run, "--body", str(tmp_path / "comment.md"),
                             "--github-output", str(output), "--summary", str(tmp_path / "summary.md"), "--now", _stamp(now)],
                            text=True, capture_output=True, env={**clean, **env}, cwd=tmp_path)
    values = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines() if "=" in line)
    return result, values


def test_the_cli_outputs_the_variables_for_the_dispatch(tmp_path: Path) -> None:
    runs = [_run(100, age_minutes=120)]
    result, values = _cli(tmp_path, env=VARIABLES, runs=runs, metadata=_metadata(100))
    assert result.returncode == 0, result.stderr
    assert values == {"action": "dispatch", "reason": "next_chunk", "act": "true", "post": "false", "order": ORDER, "price_pin": PIN,
                      "catalogue_pin": PIN, "prereg_commit": PREREG_COMMIT, "max_runs": "40"}
    # a dry run or a branch never acts
    assert _cli(tmp_path, env=VARIABLES, runs=runs, metadata=_metadata(100), dry_run="true")[1]["act"] == "false"
    assert _cli(tmp_path, env=VARIABLES, runs=runs, metadata=_metadata(100), ref="refs/heads/feature")[1]["act"] == "false"
    # nothing but the variables reaches the outputs: no input, no run or metadata field
    result, values = _cli(tmp_path, env={**VARIABLES, "C3PO_PIT_GRID_MAX_RUNS": "7"}, runs=runs, metadata={**_metadata(100), "max_runs": 200})
    assert values["max_runs"] == "7"


def test_the_cli_dry_run_previews_when_off_and_never_posts_twice(tmp_path: Path) -> None:
    runs = [_run(100, age_minutes=120)]
    result, values = _cli(tmp_path, env={**VARIABLES, "C3PO_PIT_GRID_AUTOPILOT": "off"}, runs=runs, metadata=_metadata(100), dry_run="true")
    assert values == {"action": "noop", "reason": "autopilot_off", "act": "false", "post": "false"}
    assert json.loads(result.stdout)["details"]["preview"]["action"] == "dispatch"
    complete = _metadata(100, complete=True)
    result, values = _cli(tmp_path, env=VARIABLES, runs=runs, metadata=complete)
    assert (values["action"], values["post"]) == ("noop", "true") and "order" not in values
    body = (tmp_path / "comment.md").read_text(encoding="utf-8")
    result, values = _cli(tmp_path, env=VARIABLES, runs=runs, metadata=complete, comments=[body])
    assert values["post"] == "false" and not (tmp_path / "comment.md").exists()


def test_the_cli_stops_and_posts_with_run_id_and_status(tmp_path: Path) -> None:
    runs = [_run(101, age_minutes=30, conclusion="failure"), _run(100, age_minutes=120)]
    result, values = _cli(tmp_path, env=VARIABLES, runs=runs, metadata=_metadata(100), jobs=_jobs(101, AP.FAIL_STEP), log=_log(2))
    assert result.returncode == 0, result.stderr
    assert values == {"action": "stop", "reason": "host_exit", "act": "true", "post": "true"}
    body = (tmp_path / "comment.md").read_text(encoding="utf-8")
    assert body.splitlines()[0] == "<!-- valuation-pit-grid-autopilot:stop:101 -->" and "código remoto `2`" in body
    result, values = _cli(tmp_path, env=VARIABLES, runs=runs, metadata=_metadata(100), jobs=_jobs(101, AP.FAIL_STEP), log=_log(2), comments=[body])
    assert (values["action"], values["post"]) == ("stop", "false")


def test_the_cli_fails_closed_on_unreadable_state(tmp_path: Path) -> None:
    runs = [_run(101, age_minutes=30, conclusion="failure"), _run(100, age_minutes=120)]
    result, values = _cli(tmp_path, env=VARIABLES, runs=runs, metadata=_metadata(100), jobs=None, log=None)  # the failed run's jobs missing
    assert result.returncode == 1 and values == {} and "nothing is dispatched" in result.stderr
    result, values = _cli(tmp_path, env=VARIABLES, runs=[_run(100, age_minutes=120)], metadata=None)  # the chunk's metadata missing
    assert result.returncode == 1 and values == {}


def test_select_names_the_runs_to_fetch(tmp_path: Path) -> None:
    runs = [_run(103, age_minutes=10, mode="report"), _run(102, age_minutes=20, conclusion="failure"), _run(101, age_minutes=40),
            _run(100, age_minutes=60)]
    assert AP.select(runs) == ([102], 101)
    assert AP.select([_run(101, age_minutes=40), _run(100, age_minutes=60, conclusion="failure")]) == ([], 101)
    assert AP.select([_run(101, age_minutes=40, status="in_progress")]) == ([], None)
    assert AP.select([_run(100, age_minutes=40, conclusion="failure")]) == ([100], None)  # no success: every failed chunk is classified
    many = [_run(105, age_minutes=10, conclusion="failure"), _run(104, age_minutes=20, conclusion="cancelled"), _run(103, age_minutes=30, mode="dry-run"),
            _run(102, age_minutes=40, conclusion="failure"), _run(101, age_minutes=50), _run(100, age_minutes=60, conclusion="failure")]
    assert AP.select(many) == ([105, 104, 102], 101)
    (tmp_path / "runs.json").write_text(json.dumps(runs), encoding="utf-8")
    output = tmp_path / "out.txt"
    result = subprocess.run([sys.executable, "-I", str(SCRIPT_PATH), "select", "--runs", str(tmp_path / "runs.json"), "--github-output", str(output)],
                            text=True, capture_output=True)
    assert result.returncode == 0 and output.read_text(encoding="utf-8") == "failed_run_ids=102\nsuccess_run_id=101\n"


# ---------------------------------------------------------------------------------------------------------------- F1-F4
def test_a_pending_reboot_is_retried_and_said_once_per_day(tmp_path: Path) -> None:
    runs = [_run(101, age_minutes=30, conclusion="failure"), _run(100, age_minutes=120)]
    decision = _decide(runs=runs, jobs=_jobs(101, AP.FAIL_STEP), log=_log(11))
    day = NOW.astimezone(AP.SAO_PAULO).date().isoformat()
    assert (decision.action, decision.reason, decision.post_key) == ("dispatch", "retry_after_reboot_pending", f"reboot:{day}")
    assert decision.post_body.startswith(f"<!-- valuation-pit-grid-autopilot:reboot:{day} -->\n") and "código 11" in decision.post_body
    # inside a window it is not retried, but still said
    inside = _utc(2026, 10, 21, 15, 0)
    inside_runs = [_run(101, age_minutes=30, conclusion="failure", at=inside), _run(100, age_minutes=120, at=inside)]
    held = _decide(now=inside, runs=inside_runs, jobs=_jobs(101, AP.FAIL_STEP), log=_log(11))
    assert (held.action, held.reason, held.post_key) == ("noop", "inside_window", f"reboot:{day}")
    # the CLI posts it once per BRT day while it keeps repeating, and keeps dispatching
    result, values = _cli(tmp_path, env=VARIABLES, runs=runs, metadata=_metadata(100), jobs=_jobs(101, AP.FAIL_STEP), log=_log(11))
    assert (values["action"], values["post"]) == ("dispatch", "true"), result.stderr
    body = (tmp_path / "comment.md").read_text(encoding="utf-8")
    result, values = _cli(tmp_path, env=VARIABLES, runs=runs, metadata=_metadata(100), jobs=_jobs(101, AP.FAIL_STEP), log=_log(11), comments=[body])
    assert (values["action"], values["post"]) == ("dispatch", "false")
    tomorrow = NOW + dt.timedelta(days=1)
    later_runs = [_run(101, age_minutes=30, conclusion="failure", at=tomorrow), _run(100, age_minutes=120, at=tomorrow)]
    assert _decide(now=tomorrow, runs=later_runs, jobs=_jobs(101, AP.FAIL_STEP), log=_log(11)).post_key != f"reboot:{day}"


def test_any_non_retryable_chunk_since_the_last_success_stops() -> None:
    runs = [_run(103, age_minutes=20, conclusion="failure"), _run(102, age_minutes=50, conclusion="failure"), _run(100, age_minutes=120)]
    retry_then_stop = {103: (_jobs(103, AP.FAIL_STEP), _log(17)), 102: (_jobs(102, AP.FAIL_STEP), _log(2))}
    decision = _decide(runs=runs, failures=retry_then_stop)
    assert (decision.action, decision.reason, decision.post_key) == ("stop", "host_exit", "stop:102")  # an older stop is not masked by a retry
    stop_then_retry = {103: (_jobs(103, AP.FAIL_STEP), _log(2)), 102: (_jobs(102, AP.FAIL_STEP), _log(19))}
    assert _decide(runs=runs, failures=stop_then_retry).post_key == "stop:103"
    both = {103: (_jobs(103, AP.FAIL_STEP), _log(124)), 102: (_jobs(102, AP.FAIL_STEP), _log(1))}
    assert _decide(runs=runs, failures=both).post_key == "stop:103"  # the newest stopping chunk is the one posted; 124 (deadline) stops
    all_retryable = {103: (_jobs(103, AP.FAIL_STEP), _log(21)), 102: (_jobs(102, AP.WINDOW_STEP), None)}
    decision = _decide(runs=runs, failures=all_retryable)
    assert (decision.action, decision.reason) == ("dispatch", "retry_after_blocking_ingestion")
    assert decision.details["retry_of"] == 103 and decision.details["failed_since_success"] == 2
    cancelled_between = [_run(103, age_minutes=20, conclusion="failure"), _run(102, age_minutes=50, conclusion="cancelled"), _run(100, age_minutes=120)]
    assert _decide(runs=cancelled_between, failures={103: (_jobs(103, AP.FAIL_STEP), _log(17))}).post_key == "stop:102"
    # a chunk before the last success never stops it
    older = [_run(103, age_minutes=20), _run(102, age_minutes=50, conclusion="failure")]
    assert _decide(runs=older, metadata=_metadata(103)).reason == "next_chunk"
    # every failed chunk's jobs must be readable: the tick fails closed otherwise
    with pytest.raises(AP.InputError):
        _decide(runs=runs, failures={103: (_jobs(103, AP.FAIL_STEP), _log(17))})


def test_a_failing_tick_is_posted_once_per_day_when_acting(tmp_path: Path) -> None:
    step = _step("Report a failing tick to the channel (once per BRT day)")
    assert step["if"] == "failure() && env.DRY_RUN == 'false' && github.ref == 'refs/heads/main' && vars.C3PO_PIT_GRID_AUTOPILOT == 'on'"
    assert _workflow()["jobs"]["tick"]["steps"][-1]["name"] == step["name"]
    env = {"CHANNEL_ISSUE": "429", "TICK_URL": TICK_URL}
    (tmp_path / "stub-comments.json").write_text(json.dumps([{"user": {"login": "someone"}, "body": "hello"}]) + "[]", encoding="utf-8")
    result, calls = _bash_step(step["name"], env, tmp_path)
    assert result.returncode == 0, result.stderr
    posts = [call for call in calls if call[:2] == ["issue", "comment"]]
    assert posts == [["issue", "comment", "429", "--repo", REPOSITORY, "--body-file", str(tmp_path / "failing-comment.md")]]
    body = (tmp_path / "failing-comment.md").read_text(encoding="utf-8")
    today = dt.datetime.now(dt.timezone.utc).astimezone(AP.SAO_PAULO).date().isoformat()
    assert body.splitlines()[0] == f"<!-- valuation-pit-grid-autopilot:tick-failing:{today} -->" and "autopilot tick failing" in body and "run 777" in body
    # today's notice already in the channel (as the bot): nothing more
    (tmp_path / "gh-calls.jsonl").unlink()
    (tmp_path / "stub-comments.json").write_text(json.dumps([{"user": {"login": "github-actions[bot]"}, "body": body}]), encoding="utf-8")
    result, calls = _bash_step(step["name"], env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert [call for call in calls if call[:2] == ["issue", "comment"]] == []
    # the same marker by a human never suppresses it
    assert AP.failing_tick(AP.comment_bodies(json.dumps([{"user": {"login": "x"}, "body": body}])), dt.datetime.now(dt.timezone.utc), TICK_URL) is not None
    with pytest.raises(AP.InputError):
        AP.comment_bodies("[{}] not json")


def test_first_chunk_retries_a_retryable_refusal_and_stops_on_anything_else() -> None:
    failed = [_run(101, age_minutes=60, conclusion="failure")]
    retried = _decide(runs=failed, jobs=_jobs(101, AP.FAIL_STEP), log=_log(21))
    assert (retried.action, retried.reason) == ("dispatch", "retry_after_blocking_ingestion")
    assert retried.details["max_runs"] == AP.FIRST_CHUNK_MAX_RUNS
    stopped = _decide(runs=failed, jobs=_jobs(101, AP.FAIL_STEP), log=_log(2))
    assert stopped.action == "stop" and stopped.post_key == "stop:101"


def test_failed_chunk_logs_are_saved_despite_terminal_escapes() -> None:
    # gh refuses to write a job log with ANSI escapes unless allowed (ticks of 21/10/2026 failed on this)
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert '[[ "$help" == *--allow-escape-sequences* ]]' in text and "grep -q -- '--allow-escape-sequences'" not in text
    assert 'gh api ${esc[@]+"${esc[@]}"} "repos/$GITHUB_REPOSITORY/actions/jobs/$job/logs"' in text


# ---------------------------------------------------------------------------------------------------------------- the successor order
def _order_file(digest: str) -> bytes:
    return (ORDERS / f"{digest}.json").read_bytes()


def _checkout(root: Path, *orders: dict[str, Any], copy: tuple[str, ...] = (ORDER,)) -> tuple[Path, list[str]]:
    """A checkout at ``root`` with the repository's orders named in ``copy`` and ``orders``, each written as the repository
    writes them (one JSON line) and named by its sha256."""
    folder = root / "c3po" / "ops" / "owner-orders"
    folder.mkdir(parents=True, exist_ok=True)
    for digest in copy:
        (folder / f"{digest}.json").write_bytes(_order_file(digest))
    digests = []
    for order in orders:
        content = (json.dumps(order) + "\n").encode("utf-8")
        digests.append(hashlib.sha256(content).hexdigest())
        (folder / f"{digests[-1]}.json").write_bytes(content)
    return root, digests


def _successor(**changes: Any) -> dict[str, Any]:
    """Order 2 extended past Friday and naming it in ``supersedes`` (the shape of order 3), with ``changes``."""
    return {**json.loads(_order_file(ORDER)), "not_after": ORDER_3_END, "supersedes": ORDER, "note": "teste", **changes}


def _variables(order: str, **changes: str) -> dict[str, str]:
    return {**ORDER_3_VARIABLES, "C3PO_PIT_GRID_ORDER_SHA256": order, **changes}


def _backtest_order_check(order: str, now: str, **env: str) -> subprocess.CompletedProcess[str]:
    """The backtest's "Verify the owner's order" Python, exactly as valuation-pit-backtest.yml carries it, over this checkout."""
    backtest = yaml.safe_load(BACKTEST_PATH.read_text(encoding="utf-8"))
    run = next(step for step in backtest["jobs"]["pit-backtest"]["steps"] if step.get("name") == "Verify the owner's order")["run"]
    script = run.split("<<'PY'", 1)[1].split("\n", 1)[1].split("\nPY\n", 1)[0]
    variables = {"MODE": "grid", "ORDER": order, "PIN": PIN, "CATALOGUE_PIN": PIN, "MAX_RUNS": "40", "RECOMPUTE": "false",
                 "GITHUB_REF": "refs/heads/main", "ORDER_NOW": now, **env}
    return subprocess.run([sys.executable, "-", str(ROOT)], input=script, text=True, capture_output=True, env={**os.environ, **variables}, cwd=ROOT)


def test_order_3_hashes_to_its_name_and_is_order_2_extended_past_friday() -> None:
    content = _order_file(ORDER_3)
    assert hashlib.sha256(content).hexdigest() == ORDER_3
    order_2, order_3 = json.loads(_order_file(ORDER)), json.loads(content)
    assert order_3["supersedes"] == ORDER and order_3["not_after"] == ORDER_3_END == "2026-10-27T23:30:00-03:00"
    assert {key: value for key, value in order_3.items() if key not in ("not_after", "supersedes", "note")} == \
        {key: value for key, value in order_2.items() if key not in ("not_after", "note")}  # the same pins, modes, flag and cap
    assert list(order_3) == [*[key for key in order_2 if key != "note"], "supersedes", "note"]
    for raw in (content, _order_file(ORDER)):  # written as order 2 was: one line of json.dumps, ASCII, a final newline
        assert raw == (json.dumps(json.loads(raw)) + "\n").encode("ascii")
    assert "emitida pela Fable" in order_3["note"] and "#429" in order_3["note"] and "6340314970" in order_3["note"]
    assert "ate ter 27/10 23:30 BRT" in order_3["note"]
    assert AP.successor_refusal(ROOT, AP.parameters(ORDER_3_VARIABLES), ORDER) is None


def test_the_backtest_accepts_order_3_until_tuesday_when_order_2_has_expired() -> None:
    saturday = "2026-10-24T12:00:00-03:00"
    accepted = _backtest_order_check(ORDER_3, saturday)
    assert accepted.returncode == 0 and "owner's order verified" in accepted.stdout, accepted.stderr
    expired = _backtest_order_check(ORDER, saturday)
    assert expired.returncode != 0 and "has expired" in expired.stderr
    assert _backtest_order_check(ORDER, "2026-10-23T23:29:59-03:00").returncode == 0  # order 2 until Friday 23:30 BRT
    assert _backtest_order_check(ORDER_3, "2026-10-26T18:00:00-03:00").returncode == 0  # Monday evening
    assert _backtest_order_check(ORDER_3, "2026-10-27T23:29:59-03:00").returncode == 0  # order 3 until Tuesday 23:30 BRT
    assert "has expired" in _backtest_order_check(ORDER_3, "2026-10-27T23:30:01-03:00").stderr
    for env, message in (({"RECOMPUTE": "true"}, "this recompute_existing flag"), ({"PIN": "2026-10-19T18:31:00-03:00"}, "another price pin"),
                         ({"CATALOGUE_PIN": "2026-10-19T18:29:59-03:00"}, "another catalogue pin"), ({"MAX_RUNS": "201"}, "max_runs_cap"),
                         ({"MODE": "fetch"}, "does not authorise mode fetch")):
        result = _backtest_order_check(ORDER_3, saturday, **env)
        assert result.returncode != 0 and message in result.stderr, (env, result.stderr)


def test_the_direct_successor_goes_on_with_the_grid_of_the_order_it_supersedes(tmp_path: Path) -> None:
    decision = _decide(env=ORDER_3_VARIABLES)  # the last successful chunk ran under order 2; the variables name order 3
    assert (decision.action, decision.reason, decision.post_key) == ("dispatch", "next_chunk", None)
    assert decision.details["successor_of"] == ORDER and decision.details["after_run"] == 100 and decision.details["max_runs"] == 40
    # Saturday 24/10: order 2 is over (its not_after, whatever the UNTIL), order 3 goes on until Tuesday 27/10 23:30 BRT
    weekend = [_run(100, age_minutes=120, at=SATURDAY)]
    on = _decide(env=ORDER_3_VARIABLES, now=SATURDAY, runs=weekend)
    assert (on.action, on.reason, on.details["minutes"], on.details["successor_of"]) == ("dispatch", "next_chunk", 690, ORDER)
    assert _decide(now=SATURDAY, runs=weekend).reason == "after_until"
    assert _decide(env={**VARIABLES, "C3PO_PIT_GRID_UNTIL": ORDER_3_END}, now=SATURDAY, runs=weekend).reason == "after_until"
    monday = _utc(2026, 10, 26, 21, 0)  # Monday 26/10 18:00 BRT: after the US session
    assert _decide(env=ORDER_3_VARIABLES, now=monday, runs=[_run(100, age_minutes=120, at=monday)]).reason == "next_chunk"
    tuesday_late = _utc(2026, 10, 28, 2, 31)  # Tuesday 27/10 23:31 BRT
    assert _decide(env=ORDER_3_VARIABLES, now=tuesday_late, runs=[_run(100, age_minutes=120, at=tuesday_late)]).reason == "after_until"
    # the windows are unchanged, and a tick inside one (a dry run too) still shows the link it accepted
    inside = _utc(2026, 10, 22, 15, 0)  # Thursday 11:00 New York
    held = _decide(env=ORDER_3_VARIABLES, now=inside, runs=[_run(100, age_minutes=120, at=inside)])
    assert (held.action, held.reason, held.details["successor_of"]) == ("noop", "inside_window", ORDER)
    # once a chunk of order 3 succeeds the grid is its own (no link read any more)
    own = _decide(env=ORDER_3_VARIABLES, runs=[_run(101, age_minutes=30), _run(100, age_minutes=120)], metadata=_metadata(101, order=ORDER_3))
    assert own.reason == "next_chunk" and "successor_of" not in own.details and "successor" not in own.details
    # the chunk is dispatched under order 3 — the variables —, never under the order it supersedes
    result, values = _cli(tmp_path, env=ORDER_3_VARIABLES, runs=[_run(100, age_minutes=120)], metadata=_metadata(100))
    assert result.returncode == 0, result.stderr
    assert values == {"action": "dispatch", "reason": "next_chunk", "act": "true", "post": "false", "order": ORDER_3, "price_pin": PIN,
                      "catalogue_pin": PIN, "prereg_commit": PREREG_COMMIT, "max_runs": "40"}
    # a grid completed by a chunk of order 2 is said once, naming the order its manifest carries
    complete = _decide(env=ORDER_3_VARIABLES, metadata=_metadata(100, complete=True))
    assert (complete.reason, complete.post_key) == ("grid_complete", f"complete:{MANIFEST_SHA}")
    assert f"ordem do dono `{ORDER[:8]}`" in complete.post_body
    # the same pins written in another zone are the same pins
    utc = "2026-10-19T21:30:00Z"
    root, (zoned,) = _checkout(tmp_path / "zone", _successor(price_pinned_at=utc, catalogue_pinned_at=utc))
    assert _decide(env=_variables(zoned), root=root).details["successor_of"] == ORDER


def _refused(decision: Any, label: str, now: dt.datetime = NOW) -> None:
    """A refused link: nothing dispatched, the reason in the details, said once per BRT day (never silent)."""
    key = f"other-order:{now.astimezone(AP.SAO_PAULO).date().isoformat()}"
    assert (decision.action, decision.reason, decision.post_key) == ("noop", "last_chunk_of_another_order", key)
    assert decision.details["successor"] == label and "successor_of" not in decision.details
    assert decision.post_body.startswith(f"<!-- valuation-pit-grid-autopilot:{key} -->\n") and f"`{label}`" in decision.post_body
    assert "run 100" in decision.post_body


def test_an_order_that_does_not_directly_supersede_the_last_chunk_s_order_is_refused(tmp_path: Path) -> None:
    _refused(_decide(env=ORDER_3_VARIABLES, metadata=_metadata(100, order="cd" * 32)), "not_superseded")  # an order that order 3 does not name
    _refused(_decide(metadata=_metadata(100, order=ORDER_3)), "not_superseded")  # never backwards: order 2 does not supersede order 3
    _refused(_decide(env=ORDER_3_VARIABLES, metadata=_metadata(100, order=None)), "chunk_order_unreadable")
    _refused(_decide(env=ORDER_3_VARIABLES, metadata=_metadata(100, order="../" + ORDER)), "chunk_order_unreadable")
    assert "ordem `ilegível`" in _decide(env=ORDER_3_VARIABLES, metadata=_metadata(100, order="../" + ORDER)).post_body
    # `supersedes` names the order exactly: never a list, an object, another case, padding, a prefix or a list in a string
    for index, value in enumerate(([ORDER], {"order": ORDER}, ORDER.upper(), ORDER + " ", " " + ORDER, ORDER + "\n", ORDER[:-1],
                                   f"{ORDER},{'cd' * 32}", f"{'cd' * 32} {ORDER}")):
        root, (digest,) = _checkout(tmp_path / f"supersedes-{index}", _successor(supersedes=value))
        _refused(_decide(env=_variables(digest), root=root), "not_superseded")
    # one link only: an order 4 that supersedes order 3 does not take over a grid of order 2 (it would one of order 3)
    root, (order_4,) = _checkout(tmp_path / "chain", _successor(supersedes=ORDER_3), copy=(ORDER, ORDER_3))
    _refused(_decide(env=_variables(order_4), root=root), "not_superseded")
    assert _decide(env=_variables(order_4), root=root, metadata=_metadata(100, order=ORDER_3)).details["successor_of"] == ORDER_3
    # the superseded order's file must be in this checkout, unchanged and without a symbolic link
    root, (alone,) = _checkout(tmp_path / "alone", _successor(), copy=())
    _refused(_decide(env=_variables(alone), root=root), "superseded_order_missing")
    root, (tampered,) = _checkout(tmp_path / "tampered", _successor())
    path = root / "c3po" / "ops" / "owner-orders" / f"{ORDER}.json"
    path.write_bytes(path.read_bytes() + b" ")
    _refused(_decide(env=_variables(tampered), root=root), "superseded_order_hash")
    root, (linked,) = _checkout(tmp_path / "linked", _successor())
    path = root / "c3po" / "ops" / "owner-orders" / f"{ORDER}.json"
    path.rename(tmp_path / "order-2-elsewhere.json")
    path.symlink_to(tmp_path / "order-2-elsewhere.json")
    _refused(_decide(env=_variables(linked), root=root), "superseded_order_symlink")


def test_a_successor_with_other_pins_or_flags_is_refused(tmp_path: Path) -> None:
    other = "2026-10-19T18:31:00-03:00"
    for name, changes, variables, label in (
        ("price", {"price_pinned_at": other}, {"C3PO_PIT_GRID_PRICE_PIN": other}, "superseded_order_other_price_pinned_at"),
        ("catalogue", {"catalogue_pinned_at": other}, {"C3PO_PIT_GRID_CATALOGUE_PIN": other}, "superseded_order_other_catalogue_pinned_at"),
    ):
        root, (digest,) = _checkout(tmp_path / name, _successor(**changes))
        decision = _decide(env=_variables(digest, **variables), root=root)  # the variables agree with the successor, not with order 2
        assert (decision.action, decision.reason, decision.details["successor"]) == ("noop", "last_chunk_of_another_order", label), name
    # recompute_existing=true is never the autopilot's: the order of the variables is refused before any link is read
    root, (recompute,) = _checkout(tmp_path / "recompute", _successor(recompute_existing=True))
    assert _decide(env=_variables(recompute), root=root).reason == "invalid_parameters"
    # the superseded order must be a grid order of the same schema and prereg, with the same pins and recompute_existing=false
    # (exactly: `modes` a JSON list, never a string; the flag the JSON `false`, never missing, 0, "false" or an empty list)
    base = json.loads(_order_file(ORDER))
    for name, older_order, label in (("prereg", {**base, "prereg": "PREREG_OTHER"}, "superseded_order_other_prereg"),
                                     ("schema", {**base, "schema": "OTHER"}, "superseded_order_other_prereg"),
                                     ("modes", {**base, "modes": ["fetch"]}, "superseded_order_without_grid"),
                                     ("modes-string", {**base, "modes": "grid"}, "superseded_order_without_grid"),
                                     ("modes-string-list", {**base, "modes": "['grid']"}, "superseded_order_without_grid"),
                                     ("flag", {**base, "recompute_existing": True}, "recompute_existing_not_false"),
                                     ("flag-missing", {key: value for key, value in base.items() if key != "recompute_existing"},
                                      "recompute_existing_not_false"),
                                     ("flag-zero", {**base, "recompute_existing": 0}, "recompute_existing_not_false"),
                                     ("flag-string", {**base, "recompute_existing": "false"}, "recompute_existing_not_false"),
                                     ("flag-empty", {**base, "recompute_existing": []}, "recompute_existing_not_false"),
                                     ("flag-null", {**base, "recompute_existing": None}, "recompute_existing_not_false"),
                                     ("unpinned", {**base, "price_pinned_at": None}, "superseded_order_other_price_pinned_at")):
        root, (older,) = _checkout(tmp_path / f"older-{name}", older_order, copy=())
        root, (newer,) = _checkout(root, _successor(supersedes=older), copy=())
        decision = _decide(env=_variables(newer), root=root, metadata=_metadata(100, order=older))
        assert (decision.reason, decision.details["successor"]) == ("last_chunk_of_another_order", label), name


def test_a_stop_under_the_superseded_order_still_stops_under_its_successor(tmp_path: Path) -> None:
    runs = [_run(101, age_minutes=30, conclusion="failure"), _run(100, age_minutes=120)]  # 100: the last success, under order 2
    under_2 = _decide(runs=runs, jobs=_jobs(101, AP.FAIL_STEP), log=_log(2))
    under_3 = _decide(env=ORDER_3_VARIABLES, runs=runs, jobs=_jobs(101, AP.FAIL_STEP), log=_log(2))
    assert (under_2.action, under_2.reason, under_2.post_key) == ("stop", "host_exit", "stop:101")
    assert (under_3.action, under_3.reason, under_3.post_key) == ("stop", "host_exit", "stop:101")  # the same notice: posted once
    for conclusion in ("cancelled", "timed_out"):
        stopped = [_run(101, age_minutes=30, conclusion=conclusion), _run(100, age_minutes=120)]
        assert _decide(env=ORDER_3_VARIABLES, runs=stopped, jobs=_jobs(101, None)).reason == f"conclusion_{conclusion}"
    # every chunk since the last success is classified, whatever order it ran under: an older stop is not masked by a retry
    mixed = [_run(103, age_minutes=20, conclusion="failure"), _run(102, age_minutes=50, conclusion="failure"), _run(100, age_minutes=120)]
    decision = _decide(env=ORDER_3_VARIABLES, runs=mixed, failures={103: (_jobs(103, AP.FAIL_STEP), _log(17)), 102: (_jobs(102, AP.FAIL_STEP), _log(2))})
    assert (decision.action, decision.post_key) == ("stop", "stop:102")
    # a retryable refusal is retried under the successor, as under order 2
    retried = _decide(env=ORDER_3_VARIABLES, runs=runs, jobs=_jobs(101, AP.FAIL_STEP), log=_log(21))
    assert (retried.action, retried.reason, retried.details["successor_of"]) == ("dispatch", "retry_after_blocking_ingestion", ORDER)
    # the stop posted under order 2 is not posted again under order 3
    result, values = _cli(tmp_path, env=VARIABLES, runs=runs, metadata=_metadata(100), jobs=_jobs(101, AP.FAIL_STEP), log=_log(2))
    assert (values["action"], values["post"]) == ("stop", "true"), result.stderr
    body = (tmp_path / "comment.md").read_text(encoding="utf-8")
    result, values = _cli(tmp_path, env=ORDER_3_VARIABLES, runs=runs, metadata=_metadata(100), jobs=_jobs(101, AP.FAIL_STEP), log=_log(2),
                          comments=[body])
    assert (values["action"], values["post"]) == ("stop", "false"), result.stderr
    # a chunk of order 3 dispatched by hand that succeeds reopens the autopilot, under order 3
    assert _decide(env=ORDER_3_VARIABLES, runs=[_run(102, age_minutes=20), *runs], metadata=_metadata(102, order=ORDER_3)).reason == "next_chunk"


# ---------------------------------------------------------------------------------------------------------------- what a dry run shows
ORDER_3_END_UTC = "2026-10-28T02:30:00+00:00"  # Tuesday 27/10 23:30 BRT
FRIDAY_END_UTC = "2026-10-24T02:30:00+00:00"  # Friday 23/10 23:30 BRT (order 2's not_after, and its UNTIL)


def test_the_link_and_the_end_are_shown_on_every_tick_past_the_order_check(tmp_path: Path) -> None:
    running = [_run(101, age_minutes=20, status="in_progress"), _run(100, age_minutes=120)]
    for runs, reason in ((running, "run_in_progress"), ([_run(101, age_minutes=5, mode="host-check"), _run(100, age_minutes=120)], "recent_run")):
        # a chunk in progress (or just created) hides neither the link nor the end: a dry run then still says what it would follow
        shown = _decide(env=ORDER_3_VARIABLES, runs=runs)
        assert (shown.action, shown.reason, shown.post_key) == ("noop", reason, None)
        assert shown.details["successor_of"] == ORDER and shown.details["until"] == ORDER_3_END_UTC
        refused = _decide(env=ORDER_3_VARIABLES, runs=runs, metadata=_metadata(100, order="cd" * 32))
        assert (refused.reason, refused.post_key, refused.details["successor"]) == (reason, None, "not_superseded")  # said once it is idle
        assert "successor_of" not in refused.details
    # a stop and a complete grid past the link show it too
    failed = [_run(101, age_minutes=30, conclusion="failure"), _run(100, age_minutes=120)]
    stop = _decide(env=ORDER_3_VARIABLES, runs=failed, jobs=_jobs(101, AP.FAIL_STEP), log=_log(2))
    assert (stop.action, stop.details["successor_of"], stop.details["until"]) == ("stop", ORDER, ORDER_3_END_UTC)
    complete = _decide(env=ORDER_3_VARIABLES, metadata=_metadata(100, complete=True))
    assert (complete.reason, complete.details["successor_of"], complete.details["until"]) == ("grid_complete", ORDER, ORDER_3_END_UTC)
    # the end is the earlier of UNTIL and the order's not_after: a stale UNTIL shows in a Thursday dry run, before it bites
    inside = _utc(2026, 10, 22, 14, 0)  # Thursday 11:00 BRT, in the US session
    moved = _decide(env=ORDER_3_VARIABLES, now=inside, runs=[_run(100, age_minutes=120, at=inside)])
    stale = _decide(env={**ORDER_3_VARIABLES, "C3PO_PIT_GRID_UNTIL": "2026-10-23T23:30:00-03:00"}, now=inside, runs=[_run(100, age_minutes=120, at=inside)])
    assert (moved.reason, moved.details["until"], stale.reason, stale.details["until"]) == ("inside_window", ORDER_3_END_UTC, "inside_window", FRIDAY_END_UTC)
    late = _decide(env={**ORDER_3_VARIABLES, "C3PO_PIT_GRID_UNTIL": "2026-12-31T00:00:00-03:00"}, now=inside, runs=[_run(100, age_minutes=120, at=inside)])
    assert late.details["until"] == ORDER_3_END_UTC  # never past the order
    assert _decide().details["until"] == FRIDAY_END_UTC and "successor_of" not in _decide().details  # order 2, its own grid
    # the CLI prints them, in a dry run while a chunk runs and in the preview of an autopilot that is off
    result, values = _cli(tmp_path, env=ORDER_3_VARIABLES, runs=running, metadata=_metadata(100), dry_run="true")
    record = json.loads(result.stdout)
    assert values["reason"] == "run_in_progress" and record["details"]["successor_of"] == ORDER and record["details"]["until"] == ORDER_3_END_UTC
    result, values = _cli(tmp_path, env={**ORDER_3_VARIABLES, "C3PO_PIT_GRID_AUTOPILOT": "off"}, runs=[_run(100, age_minutes=120)],
                          metadata=_metadata(100), dry_run="true")
    preview = json.loads(result.stdout)["details"]["preview"]
    assert (preview["action"], preview["successor_of"], preview["until"]) == ("dispatch", ORDER, ORDER_3_END_UTC)


def test_a_refused_link_is_posted_once_per_day(tmp_path: Path) -> None:
    runs = [_run(100, age_minutes=120)]
    result, values = _cli(tmp_path, env=ORDER_3_VARIABLES, runs=runs, metadata=_metadata(100, order="cd" * 32))
    assert values == {"action": "noop", "reason": "last_chunk_of_another_order", "act": "true", "post": "true"}, result.stderr
    body = (tmp_path / "comment.md").read_text(encoding="utf-8")
    assert body.splitlines()[0] == "<!-- valuation-pit-grid-autopilot:other-order:2026-10-21 -->" and "`not_superseded`" in body
    result, values = _cli(tmp_path, env=ORDER_3_VARIABLES, runs=runs, metadata=_metadata(100, order="cd" * 32), comments=[body])
    assert (values["reason"], values["post"]) == ("last_chunk_of_another_order", "false")
    tomorrow = NOW + dt.timedelta(days=1)
    assert _decide(env=ORDER_3_VARIABLES, now=tomorrow, runs=[_run(100, age_minutes=120, at=tomorrow)],
                   metadata=_metadata(100, order="cd" * 32)).post_key == "other-order:2026-10-22"


def test_an_end_reached_with_the_grid_incomplete_is_posted_once(tmp_path: Path) -> None:
    saturday = [_run(100, age_minutes=120, at=SATURDAY)]
    # UNTIL left at Friday 23:30 while the variables name order 3: on Saturday the tick says it once, never silently
    stale = {**ORDER_3_VARIABLES, "C3PO_PIT_GRID_UNTIL": "2026-10-23T23:30:00-03:00"}
    decision = _decide(env=stale, now=SATURDAY, runs=saturday)
    assert (decision.action, decision.reason, decision.post_key) == ("noop", "after_until", f"ended:{FRIDAY_END_UTC}")
    assert decision.details == {"until": FRIDAY_END_UTC, "remaining": 146}
    assert decision.post_body.startswith(f"<!-- valuation-pit-grid-autopilot:ended:{FRIDAY_END_UTC} -->\n")
    assert "23/10/2026 23:30 BRT" in decision.post_body and "run 100" in decision.post_body and "`146` instantes" in decision.post_body
    # the order's own not_after: order 2 on Saturday, whatever its UNTIL says
    expired = _decide(env={**VARIABLES, "C3PO_PIT_GRID_UNTIL": ORDER_3_END}, now=SATURDAY, runs=saturday)
    assert (expired.reason, expired.post_key) == ("after_until", f"ended:{FRIDAY_END_UTC}")
    # order 3 running out on Tuesday 23:30 BRT with the grid incomplete
    tuesday_late = _utc(2026, 10, 28, 2, 43)
    ran_out = _decide(env=ORDER_3_VARIABLES, now=tuesday_late, runs=[_run(102, age_minutes=200, at=tuesday_late)], metadata=_metadata(102, order=ORDER_3))
    assert (ran_out.reason, ran_out.post_key) == ("after_until", f"ended:{ORDER_3_END_UTC}")
    # nothing said when the grid is complete, a backtest run is still in progress, no chunk succeeded or the metadata is not readable
    assert _decide(env=stale, now=SATURDAY, runs=saturday, metadata=_metadata(100, complete=True)).post_key is None
    running = [_run(101, age_minutes=20, status="in_progress", at=SATURDAY), *saturday]
    assert _decide(env=stale, now=SATURDAY, runs=running).post_key is None
    for metadata in (_metadata(100), {**_metadata(100), "run_id": None}):  # no successful chunk: nothing to say, whatever the metadata
        assert _decide(env=stale, now=SATURDAY, runs=[_run(100, age_minutes=120, at=SATURDAY, conclusion="failure")], metadata=metadata).post_key is None
    for metadata in ({"run_id": "100"}, _metadata(99), {**_metadata(100), "partial": True}, [1]):
        unread = _decide(env=stale, now=SATURDAY, runs=saturday, metadata=metadata)
        assert (unread.reason, unread.post_key) == ("after_until", None), metadata
    unreadable: Any = "not a list"
    assert _decide(env=stale, now=SATURDAY, runs=unreadable).post_key is None  # an unreadable listing only leaves it unsaid
    # the CLI posts it once
    result, values = _cli(tmp_path, env=stale, runs=saturday, metadata=_metadata(100), now=SATURDAY)
    assert values == {"action": "noop", "reason": "after_until", "act": "true", "post": "true"}, result.stderr
    body = (tmp_path / "comment.md").read_text(encoding="utf-8")
    result, values = _cli(tmp_path, env=stale, runs=saturday, metadata=_metadata(100), now=SATURDAY, comments=[body])
    assert (values["reason"], values["post"]) == ("after_until", "false")


# ---------------------------------------------------------------------------------------------------------------- production deploys
def _pipeline_run(run_id: int, *, age_minutes: float, status: str = "in_progress", event: str = "push", at: dt.datetime = NOW) -> dict[str, Any]:
    return {"id": run_id, "status": status, "conclusion": "success" if status == "completed" else None, "event": event,
            "head_branch": "main" if event != "pull_request" else "feature", "path": ".github/workflows/c3po-pipeline.yml",
            "created_at": _stamp(at - dt.timedelta(minutes=age_minutes)), "display_title": "merge"}


def test_no_chunk_is_dispatched_while_a_production_deploy_can_run() -> None:
    for status in ("queued", "in_progress", "waiting", "pending", "requested"):
        for event in ("push", "workflow_dispatch"):
            decision = _decide(deploys=[_pipeline_run(900, age_minutes=20, status=status, event=event)])
            assert (decision.action, decision.reason, decision.post_key) == ("noop", "deploy_in_progress", None), (status, event)
            assert decision.details["deploys"] == [900] and decision.details["waited_minutes"] == 20
    # a pull request's run never deploys, and a completed run is over: the chunk goes
    idle = [_pipeline_run(902, age_minutes=5, event="pull_request"), _pipeline_run(901, age_minutes=40, status="completed")]
    assert _decide(deploys=idle).reason == "next_chunk"
    # a retry, a first chunk and a chunk of the successor wait as well
    failed = [_run(101, age_minutes=30, conclusion="failure"), _run(100, age_minutes=120)]
    deploying = [_pipeline_run(900, age_minutes=20)]
    assert _decide(runs=failed, jobs=_jobs(101, AP.FAIL_STEP), log=_log(17), deploys=deploying).reason == "deploy_in_progress"
    assert _decide(runs=[], deploys=deploying).reason == "deploy_in_progress"
    successor = _decide(env=ORDER_3_VARIABLES, deploys=deploying)
    assert (successor.reason, successor.details["successor_of"]) == ("deploy_in_progress", ORDER)
    # a stop is still a stop, and a window is still a window (the listing is not even read there)
    stop = _decide(runs=failed, jobs=_jobs(101, AP.FAIL_STEP), log=_log(2), deploys=deploying)
    assert (stop.action, stop.post_key) == ("stop", "stop:101")
    inside = _utc(2026, 10, 21, 15, 0)
    assert _decide(now=inside, runs=[_run(100, age_minutes=120, at=inside)], deploys=None).reason == "inside_window"
    # a deploy that holds the grid 2 h is said once (the oldest one that is not completed)
    long = [_pipeline_run(905, age_minutes=10), _pipeline_run(904, age_minutes=130, status="queued"), _pipeline_run(903, age_minutes=200, status="completed")]
    held = _decide(deploys=long)
    assert (held.reason, held.details["deploys"], held.details["waited_minutes"], held.post_key) == ("deploy_in_progress", [905, 904], 130, "deploy-wait:904")
    assert held.post_body.startswith("<!-- valuation-pit-grid-autopilot:deploy-wait:904 -->\n") and "run 904" in held.post_body
    assert _decide(deploys=[_pipeline_run(904, age_minutes=AP.DEPLOY_NOTICE_MINUTES - 1)]).post_key is None


def test_an_unreadable_deploy_listing_fails_the_tick_closed(tmp_path: Path) -> None:
    for deploys in (None, {"workflow_runs": []}, [1], [{**_pipeline_run(900, age_minutes=5), "created_at": "yesterday"}],
                    [{**_pipeline_run(900, age_minutes=5), "id": "900"}],
                    [{**_pipeline_run(900, age_minutes=5, status="completed"), "path": ".github/workflows/valuation-pit-backtest.yml"}]):
        with pytest.raises(AP.InputError):
            _decide(deploys=deploys)
    # the CLI: no listing → the tick fails and nothing is dispatched
    result, values = _cli(tmp_path, env=VARIABLES, runs=[_run(100, age_minutes=120)], metadata=_metadata(100), deploys=None)
    assert result.returncode == 1 and values == {} and "nothing is dispatched" in result.stderr
    result, values = _cli(tmp_path, env=VARIABLES, runs=[_run(100, age_minutes=120)], metadata=_metadata(100),
                          deploys=[_pipeline_run(900, age_minutes=20)])
    assert values == {"action": "noop", "reason": "deploy_in_progress", "act": "true", "post": "false"}, result.stderr


@pytest.mark.skipif(shutil.which("jq") is None, reason="the runner's jq")
def test_the_tick_lists_the_production_pipeline_runs(tmp_path: Path) -> None:
    names = [step["name"] for step in _workflow()["jobs"]["tick"]["steps"]]
    assert names.index("List the backtest runs") < names.index("List the production deploys") < names.index("Decide this tick")
    assert '--deploys "$RUNNER_TEMP/deploys.json"' in _step("Decide this tick")["run"]
    runs = [_pipeline_run(901, age_minutes=5), _pipeline_run(900, age_minutes=50, status="completed")]
    (tmp_path / "stub-deploys.jsonl").write_text("".join(json.dumps(run) + "\n" for run in runs), encoding="utf-8")
    result, calls = _bash_step("List the production deploys", {}, tmp_path)
    assert result.returncode == 0, result.stderr
    assert calls == [["api", f"repos/{REPOSITORY}/actions/workflows/c3po-pipeline.yml/runs?per_page=100", "--jq", ".workflow_runs[]"]]
    assert json.loads((tmp_path / "deploys.json").read_text(encoding="utf-8")) == runs
    (tmp_path / "stub-deploys.jsonl").unlink()  # the listing fails: the step fails (the tick then fails, nothing dispatched)
    assert _bash_step("List the production deploys", {}, tmp_path)[0].returncode != 0
