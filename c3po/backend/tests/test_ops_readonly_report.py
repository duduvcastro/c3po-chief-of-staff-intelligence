from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

from app import operational_incidents as module
from app import valuation_env
from app.config import Settings
from app.database import Database
from app.governance_vulnerability import GOVERNANCE_INCIDENT_KEY
from app.operational_incidents import OperationalIncidentService
from app.valuation_worker_contract import VALUATION_WORKER_PHASES


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
    for code, minutes, status in ((f"one-pager-{SYMBOL}", 95, "running"), ("eodhd", 10, "running"), ("cvm", 300, "succeeded")):
        run_id = database.begin_ingestion_run(code, SYMBOL, "test", {"symbols": [SYMBOL]})
        database._ingestion_runs[run_id].update(started_at=NOW - timedelta(minutes=minutes), status=status)
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
    for forbidden in (SYMBOL, "owner", "@", "Valuation", "Governança requer", "/mnt/x", "Causas", "exit 1", "/?view", "one-pager", "eodhd"):
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
    assert report["stale_running_ingestion"] == {"threshold_minutes": 30, "count": 1, "oldest_age_minutes": 95}
    assert report["diagnostics"]["job_failure_families"] == {"other": 1}  # a free title is never a family
    assert report["diagnostics"]["governance"]["attestation"] == "missing"


def test_the_diagnostics_name_families_and_routine_blockers_in_closed_vocabularies(tmp_path: Path) -> None:
    settings = Settings(database_url="", day_d_dataset_root=tmp_path)
    database = Database(settings)
    service = OperationalIncidentService(database)
    for key in ("notification:job_failure:security-automation-failure:2026-10-22",
                "notification:job_failure:security-automation-failure:2026-10-23",
                f"notification:job_failure:valuation-phase-failure:{SYMBOL}",
                f"notification:job_failure:{SYMBOL}-failure:2026-10-23"):
        service.signal(incident_key=key, source="worker", severity="critical", title=SYMBOL, detail=SYMBOL,
                       deep_link="/", evidence={}, at=NOW - timedelta(hours=2))
    report = {"status": "attention", "dependabot": {"status": "healthy"}, "governance": {"status": "healthy"},
              "operating_system": {"status": "attention", "security_updates_pending": 3, "reboot_required": True},
              "production_images": {"status": "healthy"}, "remediation_lanes": {"status": SYMBOL, "count": 0},
              "security_automation": {"status": "attention", "detail": "reboot_deferred",
                                      "healthy_blockers": ["reboot_required", "os_security_pending", SYMBOL, "reboot_required"],
                                      "additional_by_severity": {"critical": 0, "high": 1, "medium": 2, "low": 0}},
              "post_deploy_grace": {"active": False, "reason": "layer_not_healthy", "layer": SYMBOL}}
    database.latest_governance_vulnerability_report = lambda: report  # type: ignore[method-assign]
    diagnostics = module.diagnostics(database, NOW)
    assert diagnostics.pop("decisor")["status"] in module.DECISOR_STATUSES
    assert diagnostics == {
        "job_failure_families": {"security-automation-failure": 2, "valuation-phase-failure": 1, "other": 1},
        "governance": {"attestation": "attention",
                       "layers": {"dependabot": "healthy", "governance": "healthy", "operating_system": "attention",
                                  "production_images": "healthy", "remediation_lanes": "other", "security_automation": "attention"},
                       "routine": "reboot_action", "blockers": ["os_security_pending", "other", "reboot_required"],
                       "grace": "layer_not_healthy", "os_security_pending": 3, "reboot_required": True,
                       "npm_high_or_critical": 1, "remediation_lanes": 0},
    }
    assert SYMBOL not in json.dumps(diagnostics)
    full = module.incidents_report(settings, database, NOW)
    verified = _verify(tmp_path, json.dumps(full))
    assert verified.returncode == 0, verified.stderr
    summary = (tmp_path / "verify" / "ops-readonly-report" / "summary.md").read_text(encoding="utf-8")
    assert "- Falhas de job por família: other 1, security-automation-failure 2, valuation-phase-failure 1" in summary
    assert "bloqueadores: os_security_pending, other, reboot_required; carência pós-deploy: layer_not_healthy" in summary
    assert "reboot pendente True" in summary and SYMBOL not in summary


def test_the_decisor_diagnostics_count_reason_codes_never_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import valuation_verdict_export as export

    calls: list[str] = []
    rows = [{"symbol": SYMBOL, "market": "NYSE", "verdict": "VETO", "reasons": ["TP_SESSION_STALE", "PRICE_ABOVE_BUY_IN"]},
            {"symbol": "QQQQ", "market": "NASDAQ", "verdict": "OBSERVAR", "reasons": ["PRICE_ABOVE_BUY_IN", SYMBOL]},
            {"symbol": "RRRR", "market": "NASDAQ", "verdict": "COMPRA_PERMITIDA", "reasons": ["ALL_GATES_PASSED"]}]

    def fake(_database: Any, night: str, *, now: datetime) -> dict[str, Any]:
        calls.append(night)
        if night == export.LAST_COMPLETED:
            raise export.ExportRefused("NO_DECISIONS", "the evening after the close")
        return {"document": {"night": night, "rows": rows}}

    monkeypatch.setattr(export, "night_verdicts", fake)
    monkeypatch.setattr(export, "resolve_night", lambda night, *, now: "2026-10-22")
    result = module.decisor_diagnostics(None, NOW)  # type: ignore[arg-type]
    assert calls == [export.LAST_COMPLETED, "2026-10-22"]  # the evening falls back to the night before
    assert result == {"night": "2026-10-22", "status": "ok", "rows": 3,
                      "by_verdict": {"COMPRA_PERMITIDA": 1, "OBSERVAR": 1, "VETO": 1},
                      "reasons": {"ALL_GATES_PASSED": 1, "PRICE_ABOVE_BUY_IN": 2, "TP_SESSION_STALE": 1, "other": 1},
                      "sole_blocker": {}}  # the OBSERVAR row is held by its known code AND an unknown one
    assert SYMBOL not in json.dumps(result) and "QQQQ" not in json.dumps(result)

    def refused(_database: Any, night: str, *, now: datetime) -> dict[str, Any]:
        raise export.ExportRefused("RUN_INCONSISTENT", f"{SYMBOL} disagrees")

    monkeypatch.setattr(export, "night_verdicts", refused)
    assert module.decisor_diagnostics(None, NOW)["status"] == "RUN_INCONSISTENT"  # type: ignore[arg-type]
    monkeypatch.setattr(export, "night_verdicts", lambda *_a, **_k: 1 / 0)
    assert module.decisor_diagnostics(None, NOW) == {"night": None, "status": "error", "rows": 0, "by_verdict": {},  # type: ignore[arg-type]
                                                    "reasons": {}, "sole_blocker": {}}


def test_the_sole_blocker_counts_rows_that_one_gate_alone_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import valuation_verdict_export as export

    rows = [{"verdict": "OBSERVAR", "reasons": ["E_PROFILE_WARMING_UP", "EARNINGS_DATE_ESTIMATED"]},  # a mark never holds
            {"verdict": "OBSERVAR", "reasons": ["E_PROFILE_WARMING_UP", "PRICE_ABOVE_BUY_IN"]},
            {"verdict": "VETO", "reasons": ["NOT_VALIDATED", "E_PROFILE_WARMING_UP"]},
            {"verdict": "OBSERVAR", "reasons": ["E_PROFILE_WARMING_UP"]}]
    monkeypatch.setattr(export, "night_verdicts", lambda *_a, **_k: {"document": {"night": "2026-10-22", "rows": rows}})
    result = module.decisor_diagnostics(None, NOW)  # type: ignore[arg-type]
    assert result["sole_blocker"] == {"E_PROFILE_WARMING_UP": 2}
    assert result["reasons"]["E_PROFILE_WARMING_UP"] == 4


def test_the_valuation_phases_name_each_enabled_phase_in_closed_words(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # the amber card of 30/10/2026 named no phase anywhere a reader could reach: the report now says which one, never why
    monkeypatch.setenv(valuation_env.ENSEMBLE_LIVE_ENV, "true")
    for name in (valuation_env.DECISOR_SHADOW_ENV, valuation_env.EARNINGS_CALENDAR_ENV):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(database_url="", day_d_dataset_root=tmp_path)
    database = Database(settings)
    done = NOW - timedelta(hours=1)  # 07:00 BRT: after the 01:00 BRT off-hours due time of this cycle
    outcome = {"ensemble_live": "failed", "v3_shadow": "running", "shadow": "old"}
    for phase, definition in VALUATION_WORKER_PHASES.items():
        if phase == "chewie":
            continue  # never ran
        status = {"failed": "failed", "running": "running"}.get(outcome.get(phase, ""), "succeeded")
        moment = done - timedelta(days=2) if outcome.get(phase) == "old" else done
        run_id = database.begin_ingestion_run(definition["code"], SYMBOL, "test", {"symbols": [SYMBOL]})
        database._ingestion_runs[run_id].update(started_at=moment, status=status, completed_at=None if status == "running" else moment,
                                                error_summary=f"{SYMBOL} boom owner@example.com" if status == "failed" else None)
    result = module.valuation_phase_diagnostics(settings, database, NOW)
    assert result == {"status": "ok", "phases": [
        {"phase": "canonical", "state": "ok", "advisory": False},
        {"phase": "chewie", "state": "pending", "advisory": False},
        {"phase": "ensemble_live", "state": "failed", "advisory": True},
        {"phase": "peer_quality", "state": "ok", "advisory": False},
        {"phase": "shadow", "state": "stale", "advisory": False},
        {"phase": "v2_data", "state": "ok", "advisory": False},
        {"phase": "v3_shadow", "state": "running", "advisory": False},
    ]}  # cash_yield, price_history, decisor_shadow and earnings_calendar are off: not expected, not listed
    assert SYMBOL not in json.dumps(result) and "boom" not in json.dumps(result)
    report = module.incidents_report(settings, database, NOW)
    assert report["diagnostics"]["valuation_phases"] == result
    verified = _verify(tmp_path, json.dumps(report))
    assert verified.returncode == 0, verified.stderr
    summary = (tmp_path / "verify" / "ops-readonly-report" / "summary.md").read_text(encoding="utf-8")
    assert ("- Fases do worker do Valuation: chewie sem sucesso registrado; ensemble_live falhou (consultiva); shadow sem sucesso neste ciclo; "
            "v3_shadow em execução; em dia 3") in summary
    assert SYMBOL not in summary and "boom" not in summary

    def unreadable(_codes: list[str]) -> dict[str, Any]:
        raise RuntimeError(f"{SYMBOL} connection refused")

    for phase in ("chewie", "v3_shadow", "shadow", "ensemble_live"):  # every phase in day: the summary says so in one line
        run_id = database.begin_ingestion_run(VALUATION_WORKER_PHASES[phase]["code"], SYMBOL, "test", {})
        database._ingestion_runs[run_id].update(started_at=done + timedelta(minutes=1), status="succeeded",
                                                completed_at=done + timedelta(minutes=1))
    assert {item["state"] for item in module.valuation_phase_diagnostics(settings, database, NOW)["phases"]} == {"ok"}
    verified = _verify(tmp_path, json.dumps(module.incidents_report(settings, database, NOW)))
    assert verified.returncode == 0, verified.stderr
    summary = (tmp_path / "verify" / "ops-readonly-report" / "summary.md").read_text(encoding="utf-8")
    assert "- Fases do worker do Valuation: todas em dia (7)" in summary

    # a sixth state word is a defect of the classification, never printed: the block says the reading failed
    with monkeypatch.context() as patch:
        patch.setattr("app.system_health.SystemHealthService._valuation_phase_state", staticmethod(lambda *_args: SYMBOL))
        assert module.valuation_phase_diagnostics(settings, database, NOW) == {"status": "error", "phases": []}

    database.ingestion_run_health = unreadable  # type: ignore[method-assign]
    assert module.valuation_phase_diagnostics(settings, database, NOW) == {"status": "error", "phases": []}
    report = module.incidents_report(settings, database, NOW)
    verified = _verify(tmp_path, json.dumps(report))
    assert verified.returncode == 0, verified.stderr
    summary = (tmp_path / "verify" / "ops-readonly-report" / "summary.md").read_text(encoding="utf-8")
    assert "- Fases do worker do Valuation: leitura indisponível" in summary and SYMBOL not in summary


def test_the_valuation_phase_vocabulary_follows_the_worker_contract() -> None:
    import ast

    verifier = _verifier()
    names = re.search(r"PHASE_NAMES = (\{.*?\})\n", verifier, re.S)
    states = re.search(r"PHASE_STATES = (\{.*?\})\n", verifier, re.S)
    assert names is not None and states is not None
    assert ast.literal_eval(" ".join(names.group(1).split())) == set(module.VALUATION_PHASES) == {*VALUATION_WORKER_PHASES, "other"}
    assert ast.literal_eval(states.group(1)) == set(module.VALUATION_PHASE_STATES)


def test_the_runner_vocabularies_match_the_decisor_and_the_export() -> None:
    from app.valuation_verdict_export import REFUSALS

    verifier = _verifier()
    namespace: dict[str, Any] = {}
    start = verifier.index("          DECISOR_STATUSES") if "          DECISOR_STATUSES" in verifier else verifier.index("DECISOR_STATUSES")
    block = verifier[start:verifier.index("TIMESTAMP = re.compile(")]
    exec("\n".join(line.strip() for line in block.splitlines()), namespace)  # noqa: S102 - the test's own workflow literal
    assert namespace["REASON_CODES"] == {*module.decisor_reason_codes(), "other"}
    assert namespace["DECISOR_STATUSES"] == {*module.DECISOR_STATUSES} == {*REFUSALS} - {"KEY_INVALID"} | {"ok", "error", "other"}


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
            channel: dict[str, Any] | None = None, schedule: str = "30 11 * * *") -> subprocess.CompletedProcess[str]:
    work = tmp_path / "verify"
    out = work / "ops-readonly-report"
    out.mkdir(parents=True, exist_ok=True)
    (work / "incidents.json").write_text(text, encoding="utf-8")
    (work / "comments.json").write_text(json.dumps(comments or []), encoding="utf-8")
    (work / "channel.json").write_text(json.dumps(channel or {"state": "open", "locked": False, "comments": 10}), encoding="utf-8")
    for name in ("summary.md", "output"):
        (work / name).write_text("", encoding="utf-8")
    (work / "ops-readonly-comment.md").unlink(missing_ok=True)
    env = {**os.environ, "GITHUB_STEP_SUMMARY": str(work / "summary.md"), "GITHUB_OUTPUT": str(work / "output"),
           "RUN_URL": "https://github.com/o/r/actions/runs/7", "EVENT_SCHEDULE": schedule}
    return subprocess.run([sys.executable, "-", str(work / "incidents.json"), str(out), str(work / "comments.json"), str(work / "channel.json")],
                          input=_verifier(), text=True, capture_output=True, env=env)


def _rehash(report: dict[str, Any]) -> str:
    report["report_sha256"] = module.report_sha256(report)
    return json.dumps(report)


def test_the_workflow_verifier_accepts_the_cli_output_posts_once_per_run_and_turns_red(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    out = _cli(tmp_path, capsys, monkeypatch)
    verified = _verify(tmp_path, out)
    assert verified.returncode == 0, verified.stderr
    work = tmp_path / "verify"
    summary = (work / "ops-readonly-report" / "summary.md").read_text(encoding="utf-8")
    assert summary.startswith("## Relatório read-only de incidentes — 20/10/2026 08:00 BRT")
    assert "abertos há mais de 24 h: 2" in summary and "| falha de job | worker | critical | open | 1 | 1 | 30.0 |" in summary
    assert "Ingestões em execução há mais de 30 min: 1; a mais antiga há 95 min" in summary
    assert SYMBOL not in summary and "@" not in summary
    assert json.loads((work / "ops-readonly-report" / "incidents.json").read_text(encoding="utf-8")) == json.loads(out)
    assert (work / "output").read_text(encoding="utf-8") == "post=true\nred=true\n"
    comment = (work / "ops-readonly-comment.md").read_text(encoding="utf-8").splitlines()
    assert comment[0] == "<!-- c3po-ops-readonly-report:2026-10-20:0830 -->"
    red_cards = [card for card in json.loads(out)["health"]["cards"] if card["status"] == "offline"]
    assert comment[1].startswith(f"**Relatório read-only 20/10/2026 08:00 BRT** — cartões de saúde vermelhos {len(red_cards)}, âmbar ")
    phases = "; ".join(f"{item['phase']} sem sucesso registrado" + (" (consultiva)" if item["advisory"] else "")
                       for item in json.loads(out)["diagnostics"]["valuation_phases"]["phases"])  # an empty test host: no phase ran
    assert [line for line in comment if line.startswith("- [vermelho]")] == [
        f"- [vermelho] cartão `{card['group']}/{card['card']}`" + (f" — {phases}" if card["card"] == "valuation_worker_phases" else "")
        for card in red_cards]
    assert "- [vermelho] cartão `controls/valuation_worker_phases` — canonical sem sucesso registrado; chewie sem sucesso registrado;" in "\n".join(comment)
    assert "incidentes ativos 4 (1 críticos, 2 há mais de 24 h); ingestões presas há mais de 30 min: 1" in comment[1]
    assert "- [vermelho] cartão `governance/operational_incidents`" in comment
    assert "- [crítico] 1 incidente(s) crítico(s) aberto(s)" in comment
    assert "- [> 24 h] 2 incidente(s) aberto(s) há mais de 24 h (o mais antigo há 50.0 h)" in comment
    assert SYMBOL not in "\n".join(comment)

    again = _verify(tmp_path, out, comments=["\n".join(comment)])
    assert again.returncode == 0 and "already on the channel" in again.stdout
    assert (work / "output").read_text(encoding="utf-8").endswith("post=false\nred=true\n")  # still red, never posted twice
    other_slot = _verify(tmp_path, out, comments=["\n".join(comment)], schedule="30 6 * * *")
    assert other_slot.returncode == 0 and (work / "output").read_text(encoding="utf-8").endswith("post=true\nred=true\n")
    assert (work / "ops-readonly-comment.md").read_text(encoding="utf-8").startswith("<!-- c3po-ops-readonly-report:2026-10-20:0330 -->\n")
    closed = _verify(tmp_path, out, channel={"state": "closed", "locked": False, "comments": 1})
    assert closed.returncode == 0 and "::warning::" in closed.stdout
    assert (work / "output").read_text(encoding="utf-8").endswith("post=false\nred=true\n")


def test_green_cards_and_no_critical_or_aged_incident_post_nothing(tmp_path: Path) -> None:
    settings = Settings(database_url="", day_d_dataset_root=tmp_path)
    database = Database(settings)
    OperationalIncidentService(database).signal(incident_key=GOVERNANCE_INCIDENT_KEY, source="governance", severity="attention",
                                                title="t", detail="d", deep_link="/", evidence={}, at=NOW - timedelta(hours=2))
    report = module.incidents_report(settings, database, NOW)
    # an empty test host has red cards (no worker phase ran): keep only the amber ones, as on a healthy night
    report["health"]["cards"] = [card for card in report["health"]["cards"] if card["status"] != "offline"]
    assert report["health"]["cards"] and report["incidents"]["totals"]["active"] == 1
    verified = _verify(tmp_path, _rehash(report))
    assert verified.returncode == 0, verified.stderr
    assert (tmp_path / "verify" / "output").read_text(encoding="utf-8") == "post=false\nred=false\n"
    assert not (tmp_path / "verify" / "ops-readonly-comment.md").exists()


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
        "stale_running_ingestion: the keys": mutated(lambda r: r["stale_running_ingestion"].update(sources=[SYMBOL])),
        "stale count is not a non-negative count": mutated(lambda r: r["stale_running_ingestion"].update(count=-1)),
        "do not match their oldest age": mutated(lambda r: r["stale_running_ingestion"].update(oldest_age_minutes=None)),
        "diagnostics: the keys": mutated(lambda r: r["diagnostics"].update(keys=[SYMBOL])),
        "job_failure_families is not in its closed vocabulary": mutated(
            lambda r: r["diagnostics"]["job_failure_families"].update({SYMBOL: 1})),
        "blocker is not in its closed vocabulary": mutated(lambda r: r["diagnostics"]["governance"].update(blockers=[SYMBOL])),
        "routine is not in its closed vocabulary": mutated(lambda r: r["diagnostics"]["governance"].update(routine=SYMBOL)),
        "layers: the keys": mutated(lambda r: r["diagnostics"]["governance"]["layers"].update(symbol="healthy")),
        "reboot_required is not a boolean": mutated(lambda r: r["diagnostics"]["governance"].update(reboot_required=SYMBOL)),
        "decisor reasons is not in its closed vocabulary": mutated(lambda r: r["diagnostics"]["decisor"]["reasons"].update({SYMBOL: 1})),
        "decisor sole_blocker is not in its closed vocabulary": mutated(
            lambda r: r["diagnostics"]["decisor"]["sole_blocker"].update({SYMBOL: 1})),
        "decisor night is not a date": mutated(lambda r: r["diagnostics"]["decisor"].update(night=SYMBOL)),
        "decisor status is not in its closed vocabulary": mutated(lambda r: r["diagnostics"]["decisor"].update(status=SYMBOL)),
        "the decisor verdicts do not add up": mutated(lambda r: r["diagnostics"]["decisor"].update(rows=7)),
        "valuation_phases diagnostics: the keys": mutated(lambda r: r["diagnostics"]["valuation_phases"].update(detail=SYMBOL)),
        "valuation_phases status is not in its closed vocabulary": mutated(
            lambda r: r["diagnostics"]["valuation_phases"].update(status=SYMBOL)),
        "an unreadable phase evidence lists no phase": mutated(lambda r: r["diagnostics"]["valuation_phases"].update(status="error")),
        "valuation phase: the keys": mutated(lambda r: r["diagnostics"]["valuation_phases"]["phases"][0].update(error=SYMBOL)),
        "valuation phase name is not in its closed vocabulary": mutated(
            lambda r: r["diagnostics"]["valuation_phases"]["phases"][0].update(phase=SYMBOL)),
        "valuation phase state is not in its closed vocabulary": mutated(
            lambda r: r["diagnostics"]["valuation_phases"]["phases"][0].update(state=SYMBOL)),
        "valuation phase advisory is not a boolean": mutated(
            lambda r: r["diagnostics"]["valuation_phases"]["phases"][0].update(advisory=1)),
        "valuation phases is not a short list": mutated(
            lambda r: r["diagnostics"]["valuation_phases"].update(phases=[{"phase": "other", "state": "ok", "advisory": False}] * 13)),
        "does not list the canonical phase": mutated(lambda r: r["diagnostics"]["valuation_phases"].update(
            phases=[{"phase": "chewie", "state": "ok", "advisory": False}])),
        "a valuation phase is listed twice": mutated(
            lambda r: r["diagnostics"]["valuation_phases"]["phases"].append(dict(r["diagnostics"]["valuation_phases"]["phases"][0]))),
        "report_sha256 does not recompute": json.dumps({**base, "generated_at": "2026-10-20T11:00:01+00:00"}),
        "not a single JSON document": "{" + SYMBOL,
    }
    for message, text in cases.items():
        result = _verify(tmp_path, text)
        assert result.returncode != 0 and message in result.stderr, (message, result.stderr)
        assert SYMBOL not in result.stderr + result.stdout
        assert not (tmp_path / "verify" / "ops-readonly-report" / "incidents.json").exists()


def test_the_workflow_is_read_only_scheduled_twice_and_fails_on_red() -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow[True]) == {"schedule", "workflow_dispatch"}
    assert [entry["cron"] for entry in workflow[True]["schedule"]] == ["30 6 * * *", "30 11 * * *"]  # 03:30 and 08:30 BRT
    assert set(re.findall(r"secrets\.([A-Z0-9_]+)", source)) == {"C3PO_AWS_SSH_KEY", "C3PO_AWS_KNOWN_HOSTS", "C3PO_AWS_HOST", "C3PO_AWS_USER"}
    assert set(re.findall(r"vars\.([A-Z0-9_]+)", source)) == {"C3PO_ESCALATION_ISSUE"}
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
    post = steps["Post the aggregate to the Fable-Codex channel"]
    assert post["if"] == "steps.verify.outputs.post == 'true'"
    fail = steps["Fail the run when a card is red or a critical incident is open"]
    assert fail["if"] == "steps.verify.outputs.red == 'true'" and "exit 1" in fail["run"]
    assert list(steps).index("Post the aggregate to the Fable-Codex channel") < list(steps).index(
        "Fail the run when a card is red or a critical incident is open")
    assert steps["Check out the workflow revision"]["with"] == {"persist-credentials": False}


# ----------------------------------------------------------------------- a failed run is never silent
FAILURE_STEP = "Report a failed sweep to the Fable-Codex channel"


def _failure_reporter(tmp_path: Path, steps: dict[str, Any], comments: list[str]) -> tuple[subprocess.CompletedProcess[str], Path]:
    job = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))["jobs"]["read-only-report"]
    run = next(step["run"] for step in job["steps"] if step["name"] == FAILURE_STEP)
    script = run.split("<<'PY' || exit 1\n", 1)[1].split("\nPY\n", 1)[0]
    work = tmp_path / "failure"
    work.mkdir(exist_ok=True)
    (work / "comments.json").write_text(json.dumps(comments), encoding="utf-8")
    body = work / "comment.md"
    body.unlink(missing_ok=True)
    env = {**os.environ, "STEPS_JSON": json.dumps(steps), "RUN_ID": "39525387284",
           "RUN_URL": "https://github.com/o/r/actions/runs/39525387284"}
    result = subprocess.run([sys.executable, "-", str(work / "comments.json"), str(body)],
                            input=script, text=True, capture_output=True, env=env)
    return result, body


def test_a_failed_run_posts_one_line_per_brt_day_with_the_failing_step(tmp_path: Path) -> None:
    job = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))["jobs"]["read-only-report"]
    steps = [step for step in job["steps"]]
    assert steps[-1]["name"] == FAILURE_STEP
    assert steps[-1]["if"] == "failure() && steps.fail_red.outcome != 'failure'"  # the deliberate red run already posted
    assert steps[-1]["env"]["STEPS_JSON"] == "${{ toJSON(steps) }}"
    assert not re.search(r"secrets\.", json.dumps(steps[-1]))

    outcomes = {"checkout": {"outcome": "success", "conclusion": "success", "outputs": {}},
                "ssh": {"outcome": "success", "conclusion": "success", "outputs": {}},
                "remote": {"outcome": "failure", "conclusion": "failure", "outputs": {}}}
    result, body = _failure_reporter(tmp_path, outcomes, [])
    assert result.returncode == 0, result.stderr
    lines = body.read_text(encoding="utf-8").splitlines()
    today = datetime.now(timezone(timedelta(hours=-3))).date().isoformat()
    assert lines[0] == f"<!-- c3po-ops-readonly-report-failed:{today} -->" and len(lines) == 2
    assert lines[1].startswith("varredura noturna falhou — execução 39525387284, passo: "
                               "Run the report in the running api container, read-only — [execução](")

    again, body = _failure_reporter(tmp_path, outcomes, ["\n".join(lines)])
    assert again.returncode == 0 and "already on the channel" in again.stdout and not body.exists()

    unknown, body = _failure_reporter(tmp_path, {}, [])
    assert unknown.returncode == 0 and "passo: passo não identificado" in body.read_text(encoding="utf-8")


def test_stale_running_ingestion_ignores_leftovers_older_than_the_horizon() -> None:
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from app.operational_incidents import stale_running_ingestion

    now = datetime(2026, 10, 26, 6, 30, tzinfo=timezone.utc)
    database = SimpleNamespace(database_url="", _ingestion_runs={
        "leftover": {"status": "running", "started_at": now - timedelta(days=80)},
        "stuck": {"status": "running", "started_at": now - timedelta(minutes=95)},
        "fresh": {"status": "running", "started_at": now - timedelta(minutes=5)},
        "done": {"status": "succeeded", "started_at": now - timedelta(days=1)},
    })
    report = stale_running_ingestion(database, now)  # type: ignore[arg-type]
    assert report == {"threshold_minutes": 30, "count": 1, "oldest_age_minutes": 95}
