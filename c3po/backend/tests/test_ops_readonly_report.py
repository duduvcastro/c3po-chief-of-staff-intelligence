from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

from app import operational_incidents as module
from app.config import Settings
from app.database import Database
from app.governance_vulnerability import GOVERNANCE_INCIDENT_KEY
from app.operational_incidents import OperationalIncidentService


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ops-readonly-report.yml"
NOW = datetime(2026, 10, 20, 11, 0, tzinfo=timezone.utc)
SYMBOL = "ZZZZ3"  # a symbol-shaped token planted in keys, titles and details: it must never come out


def _seeded(tmp_path: Path) -> tuple[Settings, Database]:
    settings = Settings(database_url="", day_d_dataset_root=tmp_path)
    database = Database(settings)
    service = OperationalIncidentService(database)
    common = {"deep_link": "/?view=health", "evidence": {"n": 1}}
    service.signal(incident_key=f"notification:job_failure:Valuation {SYMBOL} failed", source="worker", severity="critical",
                   title=f"Valuation {SYMBOL} failed", detail=f"{SYMBOL} exit 1 owner@example.com", at=NOW - timedelta(hours=30), **common)
    service.signal(incident_key=GOVERNANCE_INCIDENT_KEY, source="governance", severity="attention",
                   title="Governança requer ação", detail="Causas: lane", at=NOW - timedelta(hours=3), **common)
    acknowledged = service.signal(incident_key="notification:disk_threshold:/mnt/x", source="host", severity="attention",
                                  title="Disk", detail="90 %", at=NOW - timedelta(hours=50), **common)
    database.transition_operational_incident(incident_id=acknowledged["id"], event_type="acknowledged",
                                             actor_email="owner@example.com", detail="seen", at=NOW - timedelta(hours=40))
    resolved = service.signal(incident_key=f"job:{SYMBOL}", source="worker", severity="critical", title=SYMBOL, detail=SYMBOL,
                              at=NOW - timedelta(hours=80), **common)
    service.resolve(resolved["id"], "owner@example.com", "done")
    service.signal(incident_key=f"custom:{SYMBOL}", source=f"robot-{SYMBOL}", severity="attention", title=SYMBOL,
                   detail=SYMBOL, at=NOW - timedelta(hours=1), **common)
    return settings, database


def _cli(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> str:
    settings, database = _seeded(tmp_path)
    monkeypatch.setenv("PGOPTIONS", "-c search_path=public")
    monkeypatch.setenv("C3PO_BUILD_SHA", "b" * 40)
    assert module.main(["--report-json"], settings=settings, database=database, now=NOW) == 0
    assert os.environ["PGOPTIONS"] == "-c search_path=public -c default_transaction_read_only=on"
    return capsys.readouterr().out


def test_the_cli_prints_aggregates_only(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    out = _cli(tmp_path, capsys, monkeypatch)
    assert out.count("\n") == 1
    report = json.loads(out)
    for forbidden in (SYMBOL, "owner", "@", "Valuation", "Governança requer", "/mnt/x", "Causas", "exit 1", "/?view"):
        assert forbidden not in out
    assert report["schema"] == module.REPORT_SCHEMA and report["build_sha"] == "b" * 40
    assert report["report_sha256"] == module.report_sha256(report)
    incidents = report["incidents"]
    assert incidents["scanned"] == 5
    assert incidents["totals"] == {"active": 4, "open": 3, "acknowledged": 1, "critical": 1, "over_24h": 2, "oldest_age_hours": 50.0}
    groups = {(group["kind"], group["source"], group["status"]): group for group in incidents["groups"]}
    assert set(groups) == {("governance-vulnerability", "governance", "open"), ("notification:job_failure", "worker", "open"),
                           ("notification:disk_threshold", "host", "acknowledged"), ("other", "other", "open")}
    job = groups[("notification:job_failure", "worker", "open")]
    assert job == {"kind": "notification:job_failure", "source": "worker", "severity": "critical", "status": "open", "count": 1,
                   "over_24h": 1, "oldest_started_at": "2026-10-19T05:00:00+00:00", "oldest_age_hours": 30.0,
                   "last_seen_at": "2026-10-19T05:00:00+00:00"}
    cards = {(card["group"], card["card"]): card["status"] for card in report["health"]["cards"]}
    assert cards[("governance", "operational_incidents")] == "offline"  # a critical incident is active
    assert cards[("governance", "governance_vulnerabilities")] == "attention"  # no attestation yet
    assert all(status in {"attention", "offline"} for status in cards.values())
    assert report["health"]["evaluated"] >= len(cards)


def test_the_report_never_reaches_the_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("network reached")

    monkeypatch.setattr(httpx, "get", refuse)
    monkeypatch.setattr(httpx, "post", refuse)
    settings, database = _seeded(tmp_path)
    module.incidents_report(settings, database, NOW)
    with pytest.raises(RuntimeError, match="never reaches the network"):
        module._refuse_network("https://example.invalid")


def test_incident_kinds_are_a_closed_vocabulary() -> None:
    assert module.GOVERNANCE_INCIDENT_KIND == GOVERNANCE_INCIDENT_KEY
    assert module.incident_kind("governance-vulnerability") == "governance-vulnerability"
    assert module.incident_kind(f"notification:job_failure:{SYMBOL}") == "notification:job_failure"
    assert module.incident_kind("notification:disk_threshold") == "notification:disk_threshold"
    assert module.incident_kind(f"notification:{SYMBOL}:x") == "other"
    assert module.incident_kind(SYMBOL.lower()) == "other"
    assert set(module.INCIDENT_KINDS) == {"governance-vulnerability", "notification:job_failure", "notification:disk_threshold", "other"}


# ----------------------------------------------------------------------- the runner's verifier
def _verifier() -> str:
    jobs = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))["jobs"]
    steps = [step for job in jobs.values() for step in job.get("steps", [])]
    script = next(step["run"] for step in steps if step.get("name") == "Verify the exact schema and keep aggregates only")
    return script.split("<<'PY' || exit 1\n", 1)[1].split("\nPY\n", 1)[0]


def _verify(tmp_path: Path, text: str, *, comments: list[str] | None = None,
            channel: dict[str, Any] | None = None) -> subprocess.CompletedProcess[str]:
    work = tmp_path / "verify"
    out = work / "ops-readonly-report"
    out.mkdir(parents=True, exist_ok=True)
    (work / "incidents.json").write_text(text, encoding="utf-8")
    (work / "comments.json").write_text(json.dumps(comments or []), encoding="utf-8")
    (work / "channel.json").write_text(json.dumps(channel or {"state": "open", "locked": False, "comments": 10}), encoding="utf-8")
    for name in ("summary.md", "output"):
        (work / name).write_text("", encoding="utf-8")
    env = {**os.environ, "GITHUB_STEP_SUMMARY": str(work / "summary.md"), "GITHUB_OUTPUT": str(work / "output"),
           "RUN_URL": "https://github.com/o/r/actions/runs/7"}
    return subprocess.run([sys.executable, "-", str(work / "incidents.json"), str(out), str(work / "comments.json"), str(work / "channel.json")],
                          input=_verifier(), text=True, capture_output=True, env=env)


def _rehash(report: dict[str, Any]) -> str:
    report["report_sha256"] = module.report_sha256(report)
    return json.dumps(report)


def test_the_workflow_verifier_accepts_the_cli_output_and_posts_once_a_day(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    out = _cli(tmp_path, capsys, monkeypatch)
    verified = _verify(tmp_path, out)
    assert verified.returncode == 0, verified.stderr
    work = tmp_path / "verify"
    summary = (work / "ops-readonly-report" / "summary.md").read_text(encoding="utf-8")
    assert summary.startswith("## Relatório read-only de incidentes — 20/10/2026 08:00 BRT")
    assert "abertos há mais de 24 h: 2" in summary and "| falha de job | worker | critical | open | 1 | 1 | 30.0 |" in summary
    assert SYMBOL not in summary and "@" not in summary
    assert json.loads((work / "ops-readonly-report" / "incidents.json").read_text(encoding="utf-8")) == json.loads(out)
    assert (work / "output").read_text(encoding="utf-8") == "post=true\n"
    comment = (work / "ops-readonly-comment.md").read_text(encoding="utf-8").splitlines()
    assert comment[0] == "<!-- c3po-ops-readonly-report:2026-10-20 -->" and len(comment) == 2
    assert comment[1].startswith("Incidentes abertos há mais de 24 h: 2 de 4 ativos (1 críticos; o mais antigo há 50.0 h)")

    again = _verify(tmp_path, out, comments=["\n".join(comment)])
    assert again.returncode == 0 and (work / "output").read_text(encoding="utf-8").endswith("post=false\n")
    closed = _verify(tmp_path, out, channel={"state": "closed", "locked": False, "comments": 1})
    assert closed.returncode == 0 and "::warning::" in closed.stdout


def test_nothing_older_than_24h_posts_nothing(tmp_path: Path) -> None:
    settings = Settings(database_url="", day_d_dataset_root=tmp_path)
    database = Database(settings)
    OperationalIncidentService(database).signal(incident_key=GOVERNANCE_INCIDENT_KEY, source="governance", severity="attention",
                                                title="t", detail="d", deep_link="/", evidence={}, at=NOW - timedelta(hours=2))
    report = module.incidents_report(settings, database, NOW)
    verified = _verify(tmp_path, json.dumps(report))
    assert verified.returncode == 0, verified.stderr
    assert (tmp_path / "verify" / "output").read_text(encoding="utf-8") == "post=false\n"


def test_the_verifier_rejects_any_key_or_string_outside_the_whitelist(tmp_path: Path) -> None:
    settings, database = _seeded(tmp_path)
    base = module.incidents_report(settings, database, NOW)

    def mutated(change: Any) -> str:
        report = copy.deepcopy(base)
        change(report)
        return _rehash(report)

    cases = {
        "report: the keys": mutated(lambda r: r.update(note=SYMBOL)),
        "incidents: the keys": mutated(lambda r: r["incidents"].update(keys=[SYMBOL])),
        "totals: the keys": mutated(lambda r: r["incidents"]["totals"].update(symbols=1)),
        "group: the keys": mutated(lambda r: r["incidents"]["groups"][0].update(incident_key=SYMBOL)),
        "kind is not in its closed vocabulary": mutated(lambda r: r["incidents"]["groups"][0].update(kind=f"notification:job_failure:{SYMBOL}")),
        "source is not in its closed vocabulary": mutated(lambda r: r["incidents"]["groups"][0].update(source=SYMBOL)),
        "status is not in its closed vocabulary": mutated(lambda r: r["incidents"]["groups"][0].update(status="resolved")),
        "last_seen_at is not a UTC timestamp": mutated(lambda r: r["incidents"]["groups"][0].update(last_seen_at=f"2026-10-20 {SYMBOL}")),
        "card: the keys": mutated(lambda r: r["health"]["cards"][0].update(detail=SYMBOL)),
        "card is not in its closed vocabulary": mutated(lambda r: r["health"]["cards"][0].update(card=SYMBOL.lower())),
        "count is not a non-negative count": mutated(lambda r: r["incidents"]["groups"][0].update(count=True)),
        "build_sha is not a commit sha": mutated(lambda r: r.update(build_sha=SYMBOL)),
        "unexpected schema": mutated(lambda r: r.update(schema="OTHER")),
        "do not add up": mutated(lambda r: r["incidents"]["totals"].update(active=99)),
        "report_sha256 does not recompute": json.dumps({**base, "generated_at": "2026-10-20T11:00:01+00:00"}),
        "not a single JSON document": "{" + SYMBOL,
    }
    for message, text in cases.items():
        result = _verify(tmp_path, text)
        assert result.returncode != 0 and message in result.stderr, (message, result.stderr)
        assert SYMBOL not in result.stderr + result.stdout
        assert not (tmp_path / "verify" / "ops-readonly-report" / "incidents.json").exists()


def test_the_workflow_is_read_only_scheduled_and_posts_only_on_aged_incidents() -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow[True]) == {"schedule", "workflow_dispatch"}
    assert [entry["cron"] for entry in workflow[True]["schedule"]] == ["30 11 * * *"]
    job = workflow["jobs"]["read-only-report"]
    assert job["permissions"] == {"contents": "read", "issues": "write"} and job["environment"] == "production"
    steps = {step["name"]: step for step in job["steps"]}
    remote = steps["Run the report in the running api container, read-only"]["run"]
    assert "-e 'PGOPTIONS=-c default_transaction_read_only=on'" in remote
    assert "api python -m app.operational_incidents --report-json </dev/null" in remote
    assert "/run/c3po-security/reboot.pending" in remote
    for forbidden in ("scp ", "docker run", " up ", "restart", "flock", "cat \"$raw/stderr.log\""):
        assert forbidden not in remote
    upload = steps["Publish the aggregate report"]
    assert upload["with"]["path"] == "${{ runner.temp }}/ops-readonly-report"
    assert "sha256sum incidents.json summary.md > SHA256SUMS" in steps["Verify the exact schema and keep aggregates only"]["run"]
    post = steps["Post the one-line aggregate to the Fable-Codex channel"]
    assert post["if"] == "steps.verify.outputs.post == 'true'"
    assert steps["Check out the workflow revision"]["with"] == {"persist-credentials": False}
