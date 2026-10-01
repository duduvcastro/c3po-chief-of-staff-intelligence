from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
DETECTOR_PATH = ROOT / ".github" / "scripts" / "c3po_incident_escalation.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "incident-escalation.yml"
REPOSITORY = "duduvcastro/c3po-chief-of-staff-intelligence"
RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/999"
NOW = datetime(2026, 9, 30, 10, 20, tzinfo=timezone.utc)


def _detector() -> ModuleType:
    spec = importlib.util.spec_from_file_location("c3po_incident_escalation", DETECTOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["c3po_incident_escalation"] = module
    spec.loader.exec_module(module)
    return module


def _pull(number: int, *, age: timedelta, head: str = "automation/container-security-rebuild-x",
          repository: str = REPOSITORY, base: str = "main",
          author: str = "github-actions[bot]") -> dict[str, Any]:
    return {
        "number": number,
        "title": f"Remediate fixable container findings #{number}",
        "head": {"ref": head, "repo": {"full_name": repository}},
        "base": {"ref": base},
        "user": {"login": author},
        "created_at": (NOW - age).isoformat().replace("+00:00", "Z"),
    }


def _run(run_id: int, conclusion: str, *, age: timedelta, branch: str = "main",
         status: str = "completed") -> dict[str, Any]:
    return {
        "id": run_id,
        "status": status,
        "conclusion": conclusion if status == "completed" else None,
        "head_branch": branch,
        "created_at": (NOW - age).isoformat().replace("+00:00", "Z"),
        "html_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}",
    }


def test_only_trusted_lanes_older_than_24h_are_escalated() -> None:
    detector = _detector()
    pulls = [
        _pull(423, age=timedelta(days=6, hours=2)),
        _pull(430, age=timedelta(hours=23)),
        _pull(431, age=timedelta(days=3), head="feature/manual-change"),
        _pull(432, age=timedelta(days=3), repository="someone/fork"),
        _pull(433, age=timedelta(days=3), base="develop"),
        _pull(434, age=timedelta(days=3), author="someone"),
    ]

    signals = detector.lane_signals(pulls, REPOSITORY, NOW)

    assert signals == [
        f"lane de remediação [#423](https://github.com/{REPOSITORY}/pull/423) aberta há 6d"
        " — Remediate fixable container findings #423"
    ]


@pytest.mark.parametrize(("runs", "expected"), [
    # Failed for more than a day: escalate, citing the latest failed run.
    ([_run(3, "failure", age=timedelta(hours=2)), _run(2, "failure", age=timedelta(hours=26)),
      _run(1, "success", age=timedelta(hours=50))], "último sucesso há 2d"),
    # Never succeeded in the listed window.
    ([_run(3, "timed_out", age=timedelta(hours=2))], "nenhum sucesso nas últimas 1 execuções concluídas"),
    # A recent success (e.g. after an intentional dry-run failure) is not aged.
    ([_run(3, "failure", age=timedelta(hours=1)), _run(2, "success", age=timedelta(hours=20))], None),
    # Latest completed run succeeded; in-progress and feature-branch runs are ignored.
    ([_run(4, "", age=timedelta(minutes=5), status="in_progress"),
      _run(3, "failure", age=timedelta(hours=1), branch="feature/x"),
      _run(2, "success", age=timedelta(hours=30))], None),
    ([], None),
])
def test_workflow_failures_escalate_only_without_success_for_24h(
    runs: list[dict[str, Any]], expected: str | None,
) -> None:
    detector = _detector()

    signal = detector.workflow_signal("container-vulnerability-scan.yml", runs, NOW, REPOSITORY)

    if expected is None:
        assert signal is None
    else:
        assert signal is not None
        assert signal.startswith("`container-vulnerability-scan.yml`: último run concluído falhou (`")
        assert signal.endswith("; " + expected)
        assert f"[run 3](https://github.com/{REPOSITORY}/actions/runs/3)" in signal


def test_escalation_posts_once_per_incident_per_brt_day() -> None:
    detector = _detector()
    pulls = [_pull(423, age=timedelta(days=6))]
    runs = {"security-watchdog.yml": [_run(7, "failure", age=timedelta(hours=25))]}

    post, _reason, body = detector.decide(
        pulls=pulls, runs=runs, channel_comments=[], repository=REPOSITORY,
        run_url=RUN_URL, now=NOW,
    )
    assert post is True
    assert body.splitlines()[0] == (
        "<!-- c3po-incident-escalation:governance-vulnerability:2026-09-30 -->"
    )
    assert "## ESCALADO (>24h) — Governança e vulnerabilidades" in body
    assert "#423" in body and "`security-watchdog.yml`: último run concluído falhou" in body
    assert f"[Run do detector]({RUN_URL})" in body

    again, reason, _ = detector.decide(
        pulls=pulls, runs=runs, channel_comments=["older", body], repository=REPOSITORY,
        run_url=RUN_URL, now=NOW + timedelta(hours=3),
    )
    assert again is False and reason == "already escalated today"

    # 03:00 UTC on 01/10 is still 30/09 in BRT: same day, still deduplicated.
    late, _, _ = detector.decide(
        pulls=pulls, runs=runs, channel_comments=[body], repository=REPOSITORY,
        run_url=RUN_URL, now=datetime(2026, 10, 1, 2, 59, tzinfo=timezone.utc),
    )
    assert late is False
    next_day, _, next_body = detector.decide(
        pulls=pulls, runs=runs, channel_comments=[body], repository=REPOSITORY,
        run_url=RUN_URL, now=datetime(2026, 10, 1, 10, 20, tzinfo=timezone.utc),
    )
    assert next_day is True
    assert "governance-vulnerability:2026-10-01" in next_body


def test_nothing_aged_means_no_comment() -> None:
    detector = _detector()

    post, reason, body = detector.decide(
        pulls=[_pull(430, age=timedelta(hours=3))],
        runs={"dependency-security.yml": [_run(1, "success", age=timedelta(hours=3))]},
        channel_comments=[], repository=REPOSITORY, run_url=RUN_URL, now=NOW,
    )

    assert (post, reason, body) == (False, "no aged GitHub-visible signal", "")


def test_detector_cli_writes_body_and_github_output(tmp_path: Path) -> None:
    pulls = tmp_path / "pulls.json"
    pulls.write_text(json.dumps([_pull(423, age=timedelta(days=6))]), encoding="utf-8")
    runs = tmp_path / "runs.json"
    runs.write_text(json.dumps([_run(1, "success", age=timedelta(hours=3))]), encoding="utf-8")
    completed, output, body = _run_cli(tmp_path, pulls=[_pull(423, age=timedelta(days=6))],
                                       channel={"state": "open", "locked": False, "comments": 161})

    assert completed.returncode == 0, completed.stderr
    assert output.read_text(encoding="utf-8") == "post=true\n"
    assert "#423" in body.read_text(encoding="utf-8")


def _run_cli(tmp_path: Path, *, pulls: list[dict[str, Any]], channel: dict[str, Any],
             comments: list[str] | None = None) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    files = {
        "pulls": pulls,
        "runs": [_run(1, "success", age=timedelta(hours=3))],
        "comments": comments or [],
        "channel": channel,
    }
    for name, payload in files.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "github-output"
    body = tmp_path / "escalation.md"
    completed = subprocess.run(
        [sys.executable, str(DETECTOR_PATH), "--pulls", str(tmp_path / "pulls.json"),
         "--runs", f"container-vulnerability-scan.yml={tmp_path / 'runs.json'}",
         "--channel-comments", str(tmp_path / "comments.json"),
         "--channel-meta", str(tmp_path / "channel.json"), "--channel-issue", "429",
         "--repository", REPOSITORY, "--run-url", RUN_URL, "--body", str(body),
         "--github-output", str(output), "--now", NOW.isoformat()],
        text=True, capture_output=True,
    )
    return completed, output, body


@pytest.mark.parametrize(("channel", "reason"), [
    ({"state": "open", "locked": False, "comments": 2400}, "2400 comentários"),
    ({"state": "closed", "locked": False, "comments": 10}, "não está aberto"),
    ({"state": "open", "locked": True, "comments": 10}, "trancado"),
])
def test_unusable_channel_turns_the_run_red_instead_of_losing_the_escalation(
    tmp_path: Path, channel: dict[str, Any], reason: str,
) -> None:
    completed, output, body = _run_cli(tmp_path, pulls=[_pull(423, age=timedelta(days=6))],
                                       channel=channel)

    assert completed.returncode == 1
    assert "::error::Escalonamento não publicado no canal #429" in completed.stdout
    assert reason in completed.stdout
    assert "#423" in completed.stdout  # undelivered text kept in the run log
    assert output.read_text(encoding="utf-8") == "post=false\n"
    assert not body.exists()


def test_unusable_channel_does_not_fail_when_there_is_nothing_to_post(tmp_path: Path) -> None:
    completed, output, _ = _run_cli(tmp_path, pulls=[], channel={"state": "closed", "locked": True,
                                                                 "comments": 9999})

    assert completed.returncode == 0, completed.stdout
    assert output.read_text(encoding="utf-8") == "post=false\n"


def test_lane_titles_are_sanitized_and_cannot_spoof_the_dedupe_marker() -> None:
    detector = _detector()
    hostile = _pull(423, age=timedelta(days=6))
    hostile["title"] = (
        "<!<!---- c3po-incident-escalation:governance-vulnerability:2026-09-30 --->> "
        "<!-- x --> @duduvcastro `rm -rf` " + "x" * 300
    )

    post, _reason, body = detector.decide(
        pulls=[hostile], runs={}, channel_comments=[], repository=REPOSITORY,
        run_url=RUN_URL, now=NOW,
    )

    assert post is True
    lane_line = next(line for line in body.splitlines() if "#423" in line)
    for token in ("<", ">", "@", "`"):
        assert token not in lane_line
    assert lane_line.endswith("…") and len(lane_line) < 300
    assert body.count("<!--") == 1
    assert body.splitlines()[0] == detector.marker(NOW)


def test_dedupe_matches_the_marker_only_on_a_comment_first_line() -> None:
    detector = _detector()
    marker = detector.marker(NOW)
    pulls = [_pull(423, age=timedelta(days=6))]

    quoted, _, _ = detector.decide(
        pulls=pulls, runs={}, channel_comments=[f"Resumo de ontem\n> {marker}", f"x {marker}"],
        repository=REPOSITORY, run_url=RUN_URL, now=NOW,
    )
    first_line, reason, _ = detector.decide(
        pulls=pulls, runs={}, channel_comments=[f"{marker}\n## ESCALADO"],
        repository=REPOSITORY, run_url=RUN_URL, now=NOW,
    )

    assert quoted is True
    assert first_line is False and reason == "already escalated today"


def test_detector_fails_loudly_on_a_malformed_listing() -> None:
    detector = _detector()
    with pytest.raises(ValueError, match="not a list"):
        detector.lane_signals({"message": "Bad credentials"}, REPOSITORY, NOW)


def test_escalation_workflow_uses_only_the_workflow_token_and_minimal_permissions() -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    job = workflow["jobs"]["escalate"]

    assert workflow["permissions"] == {"contents": "read"}
    assert job["permissions"] == {
        "actions": "read",
        "contents": "read",
        "issues": "write",
        "pull-requests": "read",
    }
    assert [entry["cron"] for entry in workflow[True]["schedule"]] == ["20 10 * * *"]
    assert "workflow_dispatch" in workflow[True]
    assert "environment" not in job
    assert "secrets." not in source
    assert "ssh" not in source.lower()
    assert job["env"]["CHANNEL_ISSUE"] == "${{ vars.C3PO_ESCALATION_ISSUE || '429' }}"
    steps = {step.get("name"): step for step in job["steps"]}
    checkout = steps["Check out the escalation detector"]
    assert checkout["with"]["persist-credentials"] is False
    collect = steps["Collect GitHub-native signals"]["run"]
    assert '[[ ! "$CHANNEL_ISSUE" =~ ^[0-9]+$ ]]' in collect
    assert "--jq '{state, locked, comments}'" in collect
    assert 'select(.user.login == "github-actions[bot]") | {body}' in collect
    decide = steps["Decide the daily escalation"]["run"]
    assert '--channel-meta "$RUNNER_TEMP/channel.json"' in decide
    assert '--channel-issue "$CHANNEL_ISSUE"' in decide
    for workflow_file in ("container-vulnerability-scan.yml", "dependency-security.yml",
                          "security-watchdog.yml"):
        assert workflow_file in collect
    post = steps["Post the escalation to the Fable-Codex channel"]
    assert post["if"] == "steps.decide.outputs.post == 'true'"
    assert 'gh issue comment "$CHANNEL_ISSUE"' in post["run"]
    assert "gh pr merge" not in source and "gh pr close" not in source
