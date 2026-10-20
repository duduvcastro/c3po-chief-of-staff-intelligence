#!/usr/bin/env python3
"""Merge green SECURITY updates inside the safe window (security-merge-window.yml).

Runs on GitHub with the workflow GITHUB_TOKEN only: no secret, no host, no database.

What it merges (everything else is reported, never touched):
  * a Dependabot pull request whose every dependency is linked to an OPEN Dependabot alert that the
    new version fixes (``first_patched_version`` <= new version), bumped by a semver patch or minor
    (0.x minor and 0.0.x patch count as major), touching only modified dependency manifests of the
    allowlist (never a workflow, a Dockerfile, app code, a frozen file or an R2D2 PACKAGE_FILES file);
  * the repository's own container lane (``automation/container-security-rebuild-*``, authored by
    github-actions[bot]) that changes only the rebuild trigger and whose remediation proof
    (``Security remediation proof``: every required job plus the zero-fixable C/H scan) is green on
    the exact head.

How:
  * all required checks green on the exact head and GitHub's own ``mergeable_state == clean``;
  * a BEHIND pull request is updated (update-branch, with the expected head) and, because a push made
    with GITHUB_TOKEN never triggers workflows, the pipeline is dispatched on its branch with
    ``deploy=false`` to validate the new head; the run then waits a bounded time for those checks and
    merges only if they are green — otherwise the next run merges it. Never force, never an admin
    bypass, never a rebase of someone else's commits;
  * at most ``--max-merges`` merges per run, sequential, squash, each with the expected head sha, and
    each only after the clock is re-checked: the merge and the 45-minute deploy that follows must both
    fit outside the US/B3 session (10:00-17:30 BRT and 09:30-16:15 ET on weekdays) and the nightly
    valuation cycle (23:30-08:15 BRT), with no PIT backtest run active (it holds the deploy lock);
  * a merge made with GITHUB_TOKEN emits no ``push`` event, so the deploy is dispatched explicitly ONCE
    at the end (c3po-pipeline.yml, ``deploy=true``, ref = the main head at that moment — never an
    older sha). A main head whose deploy is missing or failed (e.g. the 120 s lock timeout while a PIT
    backtest wrote) is redeployed by the next run inside the window.

Review hardening (20/10/2026):
  * opt-in: the workflow passes ``--mode live`` only while vars.C3PO_SECURITY_MERGE_WINDOW == 'on';
  * only GitHub Actions check runs count (``app.slug == github-actions``);
  * the Dependabot commit must be signed (``verification.verified``) and committed by GitHub (web-flow)
    or dependabot[bot]; update-branch merge commits signed and committed by web-flow; added manifest
    lines may not change where packages come from (pip index/options/URLs/VCS, npm registry/tarball
    outside registry.npmjs.org, git/github/file/link specifiers); an uninspectable diff is refused;
  * right before every update-branch and every merge the PR is re-read and RE-CLASSIFIED (fresh files,
    commits, labels: ``security-merge-hold`` stops it), and a new head after update-branch must be
    exactly GitHub's signed merge of (old head, the main read before the update);
  * the gate is re-checked after the bounded pipeline wait; a dispatched deploy still queued when the
    window closes is cancelled; only a main head this workflow merged is ever (re)deployed, and only
    after ``failure``/``timed_out`` (never ``cancelled``). The 45-minute deploy horizon is an
    assumption (no offline p95 of deploy durations).

One aggregate summary per BRT day goes to the Fable/Codex channel (issue #429) through the workflow,
with the marker on its first line (the pattern of c3po_incident_escalation.py).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time as time_module
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from c3po_incident_escalation import _text, channel_problem  # noqa: E402


SAO_PAULO = ZoneInfo("America/Sao_Paulo")
NEW_YORK = ZoneInfo("America/New_York")
MARKER_PREFIX = "c3po-security-merge-window"
DEPENDABOT_LOGIN = "dependabot[bot]"
ACTIONS_LOGIN = "github-actions[bot]"
HOLD_LABEL = "security-merge-hold"
PIPELINE = "c3po-pipeline.yml"
PIT_BACKTEST = "valuation-pit-backtest.yml"
REQUIRED_CHECKS = ("Sensitive files", "Secret scan", "Backend tests", "Python type check", "Frontend build")
PROOF_CHECK = "Security remediation proof"
DEPLOY_JOB = "Deploy production"
CONTAINER_LANE_PREFIX = "automation/container-security-rebuild-"
CONTAINER_TRIGGER = "c3po/security/container-rebuild-trigger.json"
CONTAINER_TRIGGER_SCHEMA = "C3PO_CONTAINER_REMEDIATION_TRIGGER-v1"
# Dependency manifests a security update may modify; nothing else. None of them is app code, a frozen
# file of the week of 19/10 or an R2D2 V2 PACKAGE_FILES entry (all of those live under c3po/backend/app/).
MANIFEST_ALLOWLIST = frozenset({
    "c3po/backend/requirements.txt",
    "requirements.txt",
    "c3po/frontend/package.json",
    "c3po/frontend/pnpm-lock.yaml",
})
# Reported by name when a pull request reaches them (the allowlist already refuses them).
FORBIDDEN_PREFIXES = (
    (".github/", "workflow/automação do GitHub"),
    ("c3po/backend/app/", "código do app (inclui arquivos congelados e PACKAGE_FILES do R2D2 V2)"),
    ("c3po/docs/", "documento (inclui pré-registros congelados)"),
    ("scripts/", "script de operação"),
    ("c3po/security/", "contrato de segurança"),
)
RED_CONCLUSIONS = frozenset({"failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale"})
# A deploy that failed or timed out (e.g. the 120 s deploy lock held by a PIT backtest write) is retried;
# a cancelled one is not (someone cancelled it on purpose).
REDEPLOY_CONCLUSIONS = frozenset({"failure", "timed_out"})
CHECKS_APP = "github-actions"  # only check runs created by GitHub Actions count (another app could fake a name)
GITHUB_COMMITTER = "web-flow"  # GitHub's own committer for commits it signs (API/UI merges, update-branch)
# Committers accepted for the single Dependabot commit. The exact value must be checked on the first real
# Dependabot PR after this lands (c3po/docs/DAILY_SECURITY_MAINTENANCE.md): an unexpected one only refuses.
DEPENDABOT_COMMITTERS = frozenset({GITHUB_COMMITTER, DEPENDABOT_LOGIN})
QUEUED_STATUSES = frozenset({"queued", "waiting", "requested", "pending"})
REQUIREMENT_FILES = frozenset({"c3po/backend/requirements.txt", "requirements.txt"})
NPM_FILES = frozenset({"c3po/frontend/package.json", "c3po/frontend/pnpm-lock.yaml"})
NPM_REGISTRY_HOST = "registry.npmjs.org"
# An added requirements line may not change where pip installs from or install from a URL/VCS/path.
REQUIREMENT_OPTION = re.compile(
    r"(--extra-index-url|--index-url|--find-links|--trusted-host|--editable|--no-index|--pre\b|(^|\s)-[ief](\s|=|$)"
    r"|git\+|https?:|file:|\s@\s)", re.IGNORECASE)
URL_PATTERN = re.compile(r"[a-z][a-z0-9+.-]*://[^\s'\"),}\]]+", re.IGNORECASE)
ACTIVE_RUN_STATUSES = ("queued", "in_progress", "waiting", "requested", "pending")
UPDATE_ORDER = {"patch": 0, "minor": 1, "major": 2}

NIGHTLY_START, NIGHTLY_END = time(23, 30), time(8, 15)      # BRT, every day
BRT_MARKET_START, BRT_MARKET_END = time(10, 0), time(17, 30)  # BRT, weekdays (owner's rule)
US_SESSION_START, US_SESSION_END = time(9, 30), time(16, 15)  # New York clock, weekdays (close + 15 min)
DEPLOY_MARGIN = timedelta(minutes=45)
WINDOW_STEP = timedelta(minutes=5)


# ----------------------------------------------------------------------------------------- clock
def closed_reason(at: datetime) -> str | None:
    """Why ``at`` is outside the safe window, or None. Holidays are treated as sessions (conservative)."""
    local = at.astimezone(SAO_PAULO)
    clock = local.time()
    if clock >= NIGHTLY_START or clock < NIGHTLY_END:
        return "ciclo noturno do valuation (23:30–08:15 BRT)"
    if local.weekday() < 5 and BRT_MARKET_START <= clock < BRT_MARKET_END:
        return "pregão B3/EUA (10:00–17:30 BRT)"
    new_york = at.astimezone(NEW_YORK)
    if new_york.weekday() < 5 and US_SESSION_START <= new_york.time() < US_SESSION_END:
        return "pregão dos EUA (09:30–16:15 ET)"
    return None


def window_problem(at: datetime) -> str | None:
    """None when a merge at ``at`` AND the deploy it triggers (DEPLOY_MARGIN) stay in the safe window."""
    reason = closed_reason(at)
    if reason:
        return f"janela fechada: {reason}"
    probe = at + WINDOW_STEP
    while probe <= at + DEPLOY_MARGIN:
        reason = closed_reason(probe)
        if reason:
            return f"o deploy de até 45 min invadiria: {reason}"
        probe += WINDOW_STEP
    return None


def next_open(at: datetime, limit: timedelta) -> datetime | None:
    """First minute in (at, at+limit] where window_problem is None."""
    probe = at.replace(second=0, microsecond=0) + timedelta(minutes=1)
    while probe <= at + limit:
        if window_problem(probe) is None:
            return probe
        probe += timedelta(minutes=1)
    return None


def marker(now: datetime) -> str:
    return f"<!-- {MARKER_PREFIX}:{now.astimezone(SAO_PAULO).date().isoformat()} -->"


def already_posted(channel_comments: Any, day_marker: str) -> bool:
    if not isinstance(channel_comments, list):
        raise ValueError("channel comment listing is not a list")
    return any(isinstance(body, str) and body.split("\n", 1)[0].strip() == day_marker for body in channel_comments)


# ----------------------------------------------------------------------------------- versions
VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")


def version_tuple(value: Any) -> tuple[int, int, int] | None:
    match = VERSION.match(str(value or "").strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def bump_kind(old: Any, new: Any) -> str | None:
    """patch/minor/major of a stable upgrade; None when not comparable or not an upgrade.
    In 0.x a minor change is breaking, and in 0.0.x a patch change is: both count as major."""
    before, after = version_tuple(old), version_tuple(new)
    if before is None or after is None or after <= before:
        return None
    if after[0] != before[0]:
        return "major"
    if after[1] != before[1]:
        return "major" if before[0] == 0 else "minor"
    return "major" if before[0] == 0 and before[1] == 0 else "patch"


def normalize_package(name: Any) -> str:
    return re.sub(r"[-_.]+", "-", str(name or "").strip().lower())


# ----------------------------------------------------------------------- dependabot metadata
def parse_updated_dependencies(message: str) -> list[dict[str, str]]:
    """The ``updated-dependencies`` block Dependabot writes in its commit message (what
    dependabot/fetch-metadata parses), read without a YAML dependency."""
    lines = message.splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == "updated-dependencies:")
    except StopIteration:
        return []
    dependencies: list[dict[str, str]] = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped in {"...", "---"} or (stripped and not line.startswith((" ", "-"))):
            break
        match = re.match(r"^(-\s+)?([a-z-]+):\s*(.*)$", stripped)
        if not match:
            continue
        key, value = match.group(2), match.group(3).strip().strip("'\"")
        if match.group(1):
            dependencies.append({})
        if dependencies:
            dependencies[-1][key] = value
    return [item for item in dependencies if item.get("dependency-name")]


def previous_versions(title: str, body: str) -> dict[str, tuple[str, str]]:
    """name -> (from, to) as Dependabot states it in the title and body."""
    found: dict[str, tuple[str, str]] = {}
    patterns = (
        r"^Bump (\S+) from (\S+) to (\S+?)(?: in \S+)?$",
        r"Bumps \[([^\]]+)\]\([^)]*\) from (\S+?) to (\S+?)\.?(?:\s|$)",
        r"Updates `([^`]+)` from (\S+?) to (\S+?)\.?(?:\s|$)",
    )
    for pattern in patterns:
        for text in (title, body):
            for match in re.finditer(pattern, text or "", re.MULTILINE):
                found.setdefault(normalize_package(match.group(1)), (match.group(2), match.group(3).rstrip(".")))
    return found


def forbidden_reason(path: str) -> str | None:
    name = path.rsplit("/", 1)[-1]
    if name.startswith("Dockerfile") or name.endswith(".dockerfile") or name.startswith(("compose", "docker-compose")):
        return "Dockerfile/compose"
    for prefix, label in FORBIDDEN_PREFIXES:
        if path.startswith(prefix):
            return label
    return None


def files_problem(files: Any, allowed: frozenset[str], statuses: tuple[str, ...] = ("modified",)) -> str | None:
    if not isinstance(files, list) or not files:
        return "lista de arquivos ilegível ou vazia"
    for item in files:
        path = str((item or {}).get("filename") or "")
        if path not in allowed:
            reason = forbidden_reason(path)
            if reason:
                return f"toca arquivo proibido ({reason}): {_text(path, 80)}"
            return f"toca arquivo fora da lista permitida: {_text(path, 80)}"
        if (item or {}).get("status") not in statuses:
            return f"arquivo {_text(path, 80)} com status {_text((item or {}).get('status'), 20)} (só modificação é aceita)"
        previous = (item or {}).get("previous_filename")
        if previous and previous != path:
            return "renomeia arquivo"
    return None


def added_lines(patch: str) -> list[str]:
    return [line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")]


def manifest_content_problem(files: Any) -> str | None:
    """Inside the allowlisted manifests, refuse any added line that changes WHERE packages come from: a pip
    index/option/URL/VCS line, or an npm/pnpm registry or tarball outside registry.npmjs.org, or a
    git/github/file/link specifier. A diff GitHub does not return (too large) cannot be inspected: refused."""
    if not isinstance(files, list):
        return "lista de arquivos ilegível"
    for item in files:
        path = str((item or {}).get("filename") or "")
        patch = (item or {}).get("patch")
        if not isinstance(patch, str) or not patch.strip():
            return f"diff de {_text(path, 80)} indisponível para inspeção (grande demais ou binário)"
        for line in added_lines(patch):
            if path in REQUIREMENT_FILES and REQUIREMENT_OPTION.search(line):
                return f"{_text(path, 80)}: linha adicionada muda índice, opção ou origem do pip"
            if path in NPM_FILES:
                lowered = line.lower()
                urls = URL_PATTERN.findall(line)
                if any(urlsplit(url).hostname != NPM_REGISTRY_HOST for url in urls):
                    return f"{_text(path, 80)}: URL fora de {NPM_REGISTRY_HOST}"
                if ("registry" in lowered or "tarball" in lowered) and not urls:
                    return f"{_text(path, 80)}: chave registry/tarball sem URL do registro oficial"
                if re.search(r"(git\+|github:|file:|link:|git://)", lowered):
                    return f"{_text(path, 80)}: especificador fora do registro (git/github/file/link)"
    return None


def commits_problem(commits: Any) -> tuple[str | None, dict[str, Any] | None]:
    """(problem, the single Dependabot commit). Exactly one non-merge commit, authored by Dependabot, signed
    (verification.verified) and committed by GitHub or Dependabot; merge commits (update-branch) signed and
    committed by GitHub (web-flow)."""
    if not isinstance(commits, list) or not commits:
        return "commits ilegíveis", None
    own: list[dict[str, Any]] = []
    for commit in commits:
        commit = commit if isinstance(commit, dict) else {}
        verified = ((commit.get("commit") or {}).get("verification") or {}).get("verified") is True
        committer = (commit.get("committer") or {}).get("login")
        if len(commit.get("parents") or []) >= 2:
            if not verified or committer != GITHUB_COMMITTER:
                return "commit de merge sem assinatura do GitHub (web-flow verificado)", None
            continue
        own.append(commit)
    if len(own) != 1 or (own[0].get("author") or {}).get("login") != DEPENDABOT_LOGIN:
        return "commits que não são do Dependabot (só merges de atualização são aceitos)", None
    if ((own[0].get("commit") or {}).get("verification") or {}).get("verified") is not True:
        return "commit do Dependabot sem assinatura verificada", None
    if (own[0].get("committer") or {}).get("login") not in DEPENDABOT_COMMITTERS:
        return f"committer inesperado no commit do Dependabot ({_text((own[0].get('committer') or {}).get('login'), 40)})", None
    return None, own[0]


def alert_fix(dependency: str, version: str, changed: set[str], alerts: list[dict[str, Any]]) -> str | None:
    """GHSA id of an OPEN alert on a changed manifest that ``version`` fixes."""
    wanted, new = normalize_package(dependency), version_tuple(version)
    if new is None:
        return None
    for alert in alerts:
        if not isinstance(alert, dict) or alert.get("state") != "open":
            continue
        dependency_block = alert.get("dependency") or {}
        package = dependency_block.get("package") or {}
        if normalize_package(package.get("name")) != wanted or dependency_block.get("manifest_path") not in changed:
            continue
        patched = ((alert.get("security_vulnerability") or {}).get("first_patched_version") or {}).get("identifier")
        fixed = version_tuple(patched)
        if fixed is not None and new >= fixed:
            ghsa = str((alert.get("security_advisory") or {}).get("ghsa_id") or "")
            return ghsa if re.fullmatch(r"GHSA(-[23456789cfghjmpqrvwx]{4}){3}", ghsa) else "alerta"
    return None


@dataclass
class Candidate:
    number: int
    lane: str  # "dependabot" | "container"
    head_sha: str
    head_ref: str
    created_at: str
    security: bool  # a security signal exists (alert-linked or the container lane): worth a report
    eligible: bool
    reason: str
    detail: str = ""


def classify_dependabot(pull: dict[str, Any], files: Any, commits: Any, alerts: list[dict[str, Any]] | None,
                        repository: str) -> Candidate:
    number = int(pull["number"])
    head = pull.get("head") or {}
    candidate = Candidate(number, "dependabot", str(head.get("sha") or ""), str(head.get("ref") or ""),
                          str(pull.get("created_at") or ""), False, False, "")

    def refuse(reason: str) -> Candidate:
        candidate.reason = reason
        return candidate

    if (head.get("repo") or {}).get("full_name") != repository or not candidate.head_ref.startswith("dependabot/"):
        return refuse("branch fora do repositório ou fora de dependabot/*")
    if (pull.get("base") or {}).get("ref") != "main":
        return refuse("base diferente de main")
    if pull.get("draft"):
        return refuse("rascunho")
    if pull.get("state", "open") != "open":
        return refuse("PR não está aberta")
    commit_problem, own = commits_problem(commits)
    if commit_problem or own is None:
        return refuse(commit_problem or "commits ilegíveis")
    dependencies = parse_updated_dependencies(str((own.get("commit") or {}).get("message") or ""))
    if not dependencies:
        return refuse("metadados updated-dependencies ausentes")
    stated = previous_versions(str(pull.get("title") or ""), str(pull.get("body") or ""))
    changed = {str((item or {}).get("filename") or "") for item in files} if isinstance(files, list) else set()
    summaries: list[str] = []
    problems: list[str] = []
    linked = 0
    for dependency in dependencies:
        name = dependency["dependency-name"]
        new = dependency.get("dependency-version") or (stated.get(normalize_package(name)) or ("", ""))[1]
        old = (stated.get(normalize_package(name)) or ("", ""))[0]
        computed = bump_kind(old, new)
        declared = {"version-update:semver-patch": "patch", "version-update:semver-minor": "minor",
                    "version-update:semver-major": "major"}.get(dependency.get("update-type", ""))
        kinds = [kind for kind in (computed, declared) if kind]
        kind = max(kinds, key=UPDATE_ORDER.__getitem__) if computed else None
        ghsa = alert_fix(name, new, changed, alerts) if alerts is not None else None
        linked += ghsa is not None
        summaries.append(f"{_text(name, 60)} {_text(old, 30)}→{_text(new, 30)} ({kind or 'versão não comparável'}"
                         f"{', ' + ghsa if ghsa else ''})")
        if ghsa is None:
            problems.append(f"{_text(name, 60)} sem alerta Dependabot aberto corrigido por {_text(new, 30)}")
        if kind not in {"patch", "minor"}:
            problems.append(f"{_text(name, 60)}: salto {kind or 'não comparável'} (só patch/minor)")
    candidate.detail = "; ".join(summaries)
    candidate.security = linked > 0 or alerts is None  # unknown is reported, never silently dropped
    if alerts is None:
        return refuse("alertas Dependabot ilegíveis: não é possível provar que é atualização de segurança")
    if linked == 0:
        return refuse("atualização de versão sem alerta de segurança")
    if HOLD_LABEL in {str((label or {}).get("name")) for label in pull.get("labels") or []}:
        return refuse(f"rótulo {HOLD_LABEL}")
    problem = files_problem(files, MANIFEST_ALLOWLIST) or manifest_content_problem(files)
    if problem:
        return refuse(problem)
    if problems:
        return refuse("; ".join(problems))
    candidate.eligible, candidate.reason = True, "atualização de segurança elegível"
    return candidate


def classify_container(pull: dict[str, Any], files: Any, trigger: Any, repository: str) -> Candidate:
    number = int(pull["number"])
    head = pull.get("head") or {}
    candidate = Candidate(number, "container", str(head.get("sha") or ""), str(head.get("ref") or ""),
                          str(pull.get("created_at") or ""), True, False, "rebuild das imagens de produção")
    if ((head.get("repo") or {}).get("full_name") != repository or (pull.get("user") or {}).get("login") != ACTIONS_LOGIN
            or (pull.get("base") or {}).get("ref") != "main" or pull.get("draft")):
        candidate.security, candidate.reason = False, "lane fora do padrão (autor, repositório, base ou rascunho)"
        return candidate
    if pull.get("state", "open") != "open":
        candidate.reason = "PR não está aberta"
        return candidate
    if HOLD_LABEL in {str((label or {}).get("name")) for label in pull.get("labels") or []}:
        candidate.reason = f"rótulo {HOLD_LABEL}"
        return candidate
    problem = files_problem(files, frozenset({CONTAINER_TRIGGER}), ("modified", "added"))
    if problem:
        candidate.reason = problem
        return candidate
    if not isinstance(files, list) or [item.get("filename") for item in files] != [CONTAINER_TRIGGER]:
        candidate.reason = "a lane deve mudar somente o gatilho de rebuild"
        return candidate
    if (not isinstance(trigger, dict) or trigger.get("schema") != CONTAINER_TRIGGER_SCHEMA
            or trigger.get("dry_run") is not False
            or not re.fullmatch(r"[0-9a-f]{64}", str(trigger.get("remediation_key") or ""))):
        candidate.reason = "gatilho de rebuild inválido ou de ensaio (dry_run)"
        return candidate
    candidate.eligible, candidate.reason = True, "lane de contêiner elegível"
    return candidate


def checks_verdict(check_runs: Any, required: tuple[str, ...]) -> tuple[bool, bool, str]:
    """(green, settled, reason) for the check runs of ONE head sha: every required check's latest run
    succeeded and no latest run of any check is red. ``settled`` is False while a required one runs."""
    if not isinstance(check_runs, list):
        return False, True, "checks ilegíveis"
    latest: dict[str, dict[str, Any]] = {}
    for run in check_runs:
        if not isinstance(run, dict) or (run.get("app") or {}).get("slug") != CHECKS_APP:
            continue
        name = str(run.get("name") or "")
        if name not in latest or int(run.get("id") or 0) > int(latest[name].get("id") or 0):
            latest[name] = run
    red = sorted(name for name, run in latest.items()
                 if run.get("status") == "completed" and run.get("conclusion") in RED_CONCLUSIONS)
    if red:
        return False, True, "check vermelho: " + ", ".join(_text(name, 40) for name in red)
    missing = [name for name in required if name not in latest]
    pending = [name for name in required if name in latest and latest[name].get("status") != "completed"]
    if pending or missing:
        return False, not pending and not missing, "checks pendentes ou ausentes no head exato: " + ", ".join(pending + missing)
    not_green = [name for name in required if latest[name].get("conclusion") != "success"]
    if not_green:
        return False, True, "checks obrigatórios sem sucesso: " + ", ".join(not_green)
    return True, True, "checks verdes no head exato"


# ------------------------------------------------------------------------------------ GitHub
class ApiError(RuntimeError):
    """Never carries a response body (it may echo request data)."""

    def __init__(self, method: str, path: str, status: int) -> None:
        super().__init__(f"GitHub API {method} {path.split('?', 1)[0]} returned HTTP {status}")
        self.status = status


class GitHub:
    def __init__(self, token: str, repository: str, api: str = "https://api.github.com") -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("invalid repository")
        self.token, self.root, self.base = token, api + "/", f"{api}/repos/{repository}"

    def _call(self, method: str, path: str, body: Any = None) -> tuple[int, Any, str]:
        url = path if path.startswith("https://") else self.base + path
        if not url.startswith(self.root):
            raise ValueError("pagination left the GitHub API")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "c3po-security-merge-window",
            **({"Content-Type": "application/json"} if data is not None else {}),
        })
        try:
            with urlopen(request, timeout=60) as response:
                raw = response.read()
                link = response.headers.get("Link") or ""
                return response.status, json.loads(raw) if raw else None, link
        except HTTPError as error:
            raise ApiError(method, path, error.code) from None
        except URLError:
            raise ApiError(method, path, 0) from None

    def request(self, method: str, path: str, body: Any = None) -> Any:
        return self._call(method, path, body)[1]

    def pages(self, path: str, key: str | None = None) -> list[Any]:
        items: list[Any] = []
        url: str | None = path
        while url:
            _status, payload, link = self._call("GET", url)
            page = payload.get(key) if key and isinstance(payload, dict) else payload
            if not isinstance(page, list):
                raise ApiError("GET", path, -1)
            items.extend(page)
            match = re.search(r'<([^>]+)>;\s*rel="next"', link)
            url = match.group(1) if match else None
        return items


# ------------------------------------------------------------------------------------- the run
@dataclass
class Outcome:
    candidate: Candidate
    action: str  # merged | updated | skipped | would-merge | would-update
    reason: str


@dataclass
class Report:
    started_at: datetime
    live: bool
    max_merges: int
    gate: str | None = None
    alerts: str = ""
    outcomes: list[Outcome] = field(default_factory=list)
    ignored: list[Candidate] = field(default_factory=list)
    deploy: str = ""

    @property
    def merged(self) -> list[Outcome]:
        return [outcome for outcome in self.outcomes if outcome.action == "merged"]

    def worth_posting(self) -> bool:
        return self.live and (bool(self.outcomes) or bool(self.deploy and not self.deploy.startswith("não necessário")))


class MergeWindow:
    def __init__(self, api: Any, *, repository: str, live: bool, max_merges: int = 3,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 sleep: Callable[[float], None] = time_module.sleep,
                 window_wait: timedelta = timedelta(minutes=30), busy_wait: timedelta = timedelta(minutes=20),
                 validation_wait: timedelta = timedelta(minutes=35), deploy_wait: timedelta = timedelta(minutes=60),
                 poll_seconds: float = 60.0) -> None:
        self.api, self.repository, self.live, self.max_merges = api, repository, live, max_merges
        self.clock, self.sleep = clock, sleep
        self.window_wait, self.busy_wait = window_wait, busy_wait
        self.validation_wait, self.deploy_wait, self.poll_seconds = validation_wait, deploy_wait, poll_seconds
        self.alerts: list[dict[str, Any]] | None = None
        self.merged_shas: list[str] = []  # merge commits this run created (the only heads it ever deploys)

    # -- reading
    def _alerts(self, report: Report) -> list[dict[str, Any]] | None:
        try:
            alerts = self.api.pages("/dependabot/alerts?state=open&per_page=100")
        except ApiError as error:
            report.alerts = f"alertas Dependabot ilegíveis (HTTP {error.status})"
            return None
        report.alerts = f"{len(alerts)} alerta(s) Dependabot aberto(s) lido(s)"
        return alerts

    def _trigger(self, sha: str) -> Any:
        try:
            content = self.api.request("GET", f"/contents/{CONTAINER_TRIGGER}?ref={sha}")
            return json.loads(base64.b64decode(str((content or {}).get("content") or "")).decode("utf-8"))
        except (ApiError, ValueError):
            return None

    def classify(self, report: Report) -> list[Candidate]:
        pulls = self.api.pages("/pulls?state=open&base=main&per_page=100")
        alerts: list[dict[str, Any]] | None = None
        alerts_read = False
        candidates: list[Candidate] = []
        for pull in pulls:
            login = (pull.get("user") or {}).get("login")
            ref = str((pull.get("head") or {}).get("ref") or "")
            number = int(pull["number"])
            labels = {str((label or {}).get("name")) for label in pull.get("labels") or []}
            if login == DEPENDABOT_LOGIN:
                if not alerts_read:
                    alerts, alerts_read = self._alerts(report), True
                    self.alerts = alerts
            elif not ref.startswith(CONTAINER_LANE_PREFIX):
                continue
            candidate = self._classify_one(pull)
            if candidate.eligible and HOLD_LABEL in labels:
                candidate.eligible, candidate.reason = False, f"rótulo {HOLD_LABEL}"
            candidates.append(candidate)
        return sorted(candidates, key=lambda item: (item.created_at, item.number))

    def _classify_one(self, pull: dict[str, Any]) -> Candidate:
        """Classify ``pull`` on freshly read files and commits (or trigger): used at listing time and again
        on the fresh detail right before every update-branch and every merge."""
        number = int(pull["number"])
        files = self.api.pages(f"/pulls/{number}/files?per_page=100")
        if (pull.get("user") or {}).get("login") == DEPENDABOT_LOGIN:
            commits = self.api.pages(f"/pulls/{number}/commits?per_page=100")
            return classify_dependabot(pull, files, commits, self.alerts, self.repository)
        trigger = self._trigger(str((pull.get("head") or {}).get("sha") or ""))
        return classify_container(pull, files, trigger, self.repository)

    def _fresh(self, candidate: Candidate, sha: str) -> tuple[str | None, dict[str, Any]]:
        """(problem, fresh detail): the PR as GitHub has it NOW must still be open, without the hold label, at
        ``sha``, and eligible under the classifier on freshly read files and commits."""
        detail = self._pull(candidate.number)
        if detail.get("state") != "open":
            return "PR fechada durante o run", detail
        if HOLD_LABEL in {str((label or {}).get("name")) for label in detail.get("labels") or []}:
            return f"rótulo {HOLD_LABEL}", detail
        if (detail.get("head") or {}).get("sha") != sha:
            return "head mudou durante o run", detail
        fresh = self._classify_one(detail)
        if not fresh.eligible or fresh.head_sha != sha:
            return f"reclassificada na hora: {fresh.reason}", detail
        return None, detail

    def _active_runs(self, workflow: str) -> int:
        return sum(len(self.api.pages(f"/actions/workflows/{workflow}/runs?status={status}&per_page=100", "workflow_runs"))
                   for status in ACTIVE_RUN_STATUSES)

    def _checks(self, sha: str, lane: str) -> tuple[bool, bool, str]:
        required = REQUIRED_CHECKS + ((PROOF_CHECK,) if lane == "container" else ())
        runs = self.api.pages(f"/commits/{sha}/check-runs?per_page=100", "check_runs")
        return checks_verdict(runs, required)

    def _pull(self, number: int) -> dict[str, Any]:
        detail: dict[str, Any] = {}
        for _attempt in range(6):
            detail = self.api.request("GET", f"/pulls/{number}") or {}
            if detail.get("mergeable") is not None or detail.get("state") != "open":
                return detail
            self.sleep(5)
        return detail

    # -- gates
    def _gate(self) -> str | None:
        """Re-checked before every write: the clock and the PIT backtest (it holds the deploy lock)."""
        problem = window_problem(self.clock())
        if problem:
            return problem
        if self._active_runs(PIT_BACKTEST):
            return "backtest PIT em execução (segura a trava de deploy)"
        return None

    def _wait_pipeline_idle(self) -> str | None:
        deadline = self.clock() + self.busy_wait
        while self._active_runs(PIPELINE):
            if self.clock() >= deadline:
                return "pipeline de produção ocupado além da espera limitada"
            self.sleep(self.poll_seconds)
        return None

    # -- writes
    def _dispatch(self, ref: str, sha: str, *, deploy: bool, remediation: bool) -> None:
        self.api.request("POST", f"/actions/workflows/{PIPELINE}/dispatches", {
            "ref": ref,
            "inputs": {"ref": sha, "deploy": "true" if deploy else "false", "remediation": "true" if remediation else "false"},
        })

    def _merge(self, candidate: Candidate, sha: str) -> Outcome:
        gate = self._gate()
        if gate:
            return Outcome(candidate, "skipped", gate)
        problem, detail = self._fresh(candidate, sha)
        if problem:
            return Outcome(candidate, "skipped", problem)
        if detail.get("mergeable_state") not in {"clean", "has_hooks"}:
            return Outcome(candidate, "skipped", f"estado de merge {_text(detail.get('mergeable_state'), 20)}")
        green, _settled, reason = self._checks(sha, candidate.lane)
        if not green:
            return Outcome(candidate, "skipped", reason)
        try:
            result = self.api.request("PUT", f"/pulls/{candidate.number}/merge", {"sha": sha, "merge_method": "squash"})
        except ApiError as error:
            return Outcome(candidate, "skipped", f"merge recusado pelo GitHub (HTTP {error.status})")
        if not isinstance(result, dict) or result.get("merged") is not True:
            return Outcome(candidate, "skipped", "merge não confirmado pelo GitHub")
        merge_sha = str(result.get("sha") or "")
        if re.fullmatch(r"[0-9a-f]{40}", merge_sha):
            self.merged_shas.append(merge_sha)
        return Outcome(candidate, "merged", f"squash do head {sha[:7]}")

    def _update_and_validate(self, candidate: Candidate, sha: str) -> Outcome:
        # the clock again AFTER the bounded pipeline wait: the wait itself may have closed the window
        gate = self._gate() or self._wait_pipeline_idle() or self._gate()
        if gate:
            return Outcome(candidate, "skipped", f"atrás da main; {gate}")
        problem, _detail = self._fresh(candidate, sha)
        if problem:
            return Outcome(candidate, "skipped", problem)
        main_before = str(((self.api.request("GET", "/git/ref/heads/main") or {}).get("object") or {}).get("sha") or "")
        try:
            self.api.request("PUT", f"/pulls/{candidate.number}/update-branch", {"expected_head_sha": sha})
        except ApiError as error:
            return Outcome(candidate, "skipped", f"update-branch recusado (HTTP {error.status})")
        new_sha = sha
        deadline = self.clock() + timedelta(minutes=2)
        while new_sha == sha and self.clock() < deadline:
            self.sleep(5)
            new_sha = str(((self._pull(candidate.number).get("head") or {}).get("sha")) or sha)
        if new_sha == sha:
            return Outcome(candidate, "updated", "update-branch aceito; novo head ainda não visível — próximo run valida e mescla")
        # the new head must be exactly GitHub's signed merge of (old head, the main read before the update)
        commit = self.api.request("GET", f"/commits/{new_sha}") or {}
        parents = [str((parent or {}).get("sha") or "") for parent in commit.get("parents") or []]
        verified = ((commit.get("commit") or {}).get("verification") or {}).get("verified") is True
        if parents != [sha, main_before] or not verified:
            return Outcome(candidate, "skipped", f"novo head {new_sha[:7]} não é o merge assinado esperado de (head, main) — "
                                                 "nada validado nem mesclado")
        # GITHUB_TOKEN pushes trigger no workflow: validate the new head explicitly (never deploy).
        self._dispatch(candidate.head_ref, new_sha, deploy=False, remediation=candidate.lane == "container")
        deadline = self.clock() + self.validation_wait
        while True:
            green, settled, reason = self._checks(new_sha, candidate.lane)
            if green or settled or self.clock() >= deadline:
                break
            self.sleep(self.poll_seconds)
        if not green:
            return Outcome(candidate, "updated", f"atualizada para {new_sha[:7]}; validação ainda não verde ({reason}) — próximo run")
        detail = self._pull(candidate.number)
        if (detail.get("head") or {}).get("sha") != new_sha or detail.get("mergeable_state") != "clean":
            return Outcome(candidate, "updated", f"atualizada e validada; estado de merge {_text(detail.get('mergeable_state'), 20)} — próximo run")
        return self._merge(candidate, new_sha)

    def _merged_by_window(self, sha: str) -> bool:
        """``sha`` is the merge commit of a PR merged by this workflow (github-actions[bot], a Dependabot or
        container-lane PR): the only kind of main head this workflow ever (re)deploys."""
        try:
            pulls = self.api.pages(f"/commits/{sha}/pulls?per_page=10")
        except ApiError:
            return False
        for pull in pulls:
            detail = self.api.request("GET", f"/pulls/{int(pull['number'])}") or {}
            ref = str((detail.get("head") or {}).get("ref") or "")
            if (detail.get("merge_commit_sha") == sha and (detail.get("merged_by") or {}).get("login") == ACTIONS_LOGIN
                    and ((detail.get("user") or {}).get("login") == DEPENDABOT_LOGIN or ref.startswith(CONTAINER_LANE_PREFIX))):
                return True
        return False

    def _main_deploy_state(self, sha: str) -> str:
        """deployed | in_progress | missing | failed | not_attempted for the main head ``sha``."""
        runs = [run for run in self.api.pages(f"/actions/workflows/{PIPELINE}/runs?head_sha={sha}&per_page=50", "workflow_runs")
                if run.get("head_sha") == sha and run.get("event") in {"push", "workflow_dispatch"}]
        if any(run.get("status") != "completed" for run in runs):
            return "in_progress"
        if not runs:
            return "missing"
        failed = False
        for run in sorted(runs, key=lambda item: int(item.get("id") or 0), reverse=True):
            for job in self.api.pages(f"/actions/runs/{run['id']}/jobs?per_page=100", "jobs"):
                if job.get("name") != DEPLOY_JOB:
                    continue
                if job.get("conclusion") == "success":
                    return "deployed"
                failed = failed or job.get("conclusion") in REDEPLOY_CONCLUSIONS
        return "failed" if failed else "not_attempted"

    def _deploy(self, reason: str) -> str:
        gate = self._gate() or self._wait_pipeline_idle() or self._gate()
        if gate:
            return f"pendente ({reason}); não disparado: {gate} — próximo run tenta de novo"
        main_sha = str(((self.api.request("GET", "/git/ref/heads/main") or {}).get("object") or {}).get("sha") or "")
        if not re.fullmatch(r"[0-9a-f]{40}", main_sha):
            return "pendente; head da main ilegível"
        if main_sha not in self.merged_shas and not self._merged_by_window(main_sha):
            # someone else's commit is on top: its own push event deploys it (and everything below it)
            return f"não disparado: a main (`{main_sha[:7]}`) avançou além do merge da janela; o push desse commit faz o deploy"
        previous = max((int(run.get("id") or 0) for run in self.api.pages(
            f"/actions/workflows/{PIPELINE}/runs?event=workflow_dispatch&head_sha={main_sha}&per_page=50", "workflow_runs")), default=0)
        self._dispatch("main", main_sha, deploy=True, remediation=False)
        deadline = self.clock() + self.deploy_wait
        run: dict[str, Any] | None = None
        while self.clock() < deadline:
            self.sleep(self.poll_seconds)
            runs = [item for item in self.api.pages(
                f"/actions/workflows/{PIPELINE}/runs?event=workflow_dispatch&head_sha={main_sha}&per_page=50", "workflow_runs")
                if int(item.get("id") or 0) > previous]
            run = max(runs, key=lambda item: int(item.get("id") or 0)) if runs else None
            if run is not None and run.get("status") == "completed":
                break
            if run is not None and run.get("status") in QUEUED_STATUSES and window_problem(self.clock()):
                # still waiting in the queue when the window closed: it must not start a deploy now
                try:
                    self.api.request("POST", f"/actions/runs/{int(run['id'])}/cancel")
                except ApiError as error:
                    return f"disparado para `{main_sha[:7]}` ({reason}); a janela fechou com o run na fila e o cancelamento falhou (HTTP {error.status})"
                return (f"cancelado na fila para `{main_sha[:7]}` ({reason}): {window_problem(self.clock())} — "
                        "o próximo run redeploya")
        if run is None:
            return f"disparado para `{main_sha[:7]}` ({reason}); run não localizado na espera limitada"
        label = f"run [{run['id']}](https://github.com/{self.repository}/actions/runs/{run['id']})"
        if run.get("status") != "completed":
            return f"disparado para `{main_sha[:7]}` ({reason}); {label} ainda em andamento"
        state = self._main_deploy_state(main_sha)
        if state == "deployed":
            return f"concluído para `{main_sha[:7]}` ({reason}); {label}"
        return (f"FALHOU para `{main_sha[:7]}` ({reason}); {label} — se foi a trava do backtest PIT (120 s), "
                "o próximo run redeploya")

    def run(self) -> Report:
        report = Report(started_at=self.clock(), live=self.live, max_merges=self.max_merges)
        candidates = self.classify(report)
        report.ignored = [candidate for candidate in candidates if not candidate.eligible]
        report.outcomes = [Outcome(candidate, "skipped", candidate.reason)
                           for candidate in report.ignored if candidate.security]
        eligible = [candidate for candidate in candidates if candidate.eligible]
        main_sha = str(((self.api.request("GET", "/git/ref/heads/main") or {}).get("object") or {}).get("sha") or "")
        deploy_state = self._main_deploy_state(main_sha) if re.fullmatch(r"[0-9a-f]{40}", main_sha) else "unknown"
        # only a head this workflow merged itself is ever redeployed (anything else deploys on its own push)
        pending_deploy = deploy_state in {"missing", "failed"} and self._merged_by_window(main_sha)
        if not eligible and not pending_deploy:
            report.deploy = "não necessário"
            return report  # nothing to write: no window wait, no pipeline wait
        problem = window_problem(self.clock())
        if problem:
            opens = next_open(self.clock(), self.window_wait)
            if opens is not None:
                self.sleep(max(0.0, (opens - self.clock()).total_seconds()))
                problem = window_problem(self.clock())
        report.gate = problem
        if problem is None:
            report.gate = self._gate() or ((self._wait_pipeline_idle() or self._gate()) if self.live else None)
        if report.gate:
            for candidate in eligible:
                report.outcomes.append(Outcome(candidate, "skipped", report.gate))
            report.deploy = (f"main `{main_sha[:7]}` sem deploy concluído ({deploy_state}); fica para o próximo run"
                             if pending_deploy else "não necessário")
            return report
        merges = 0
        stop: str | None = None
        for candidate in eligible:
            if stop:
                report.outcomes.append(Outcome(candidate, "skipped", stop))
                continue
            if merges >= self.max_merges:
                report.outcomes.append(Outcome(candidate, "skipped", f"limite de {self.max_merges} merges por run"))
                continue
            detail = self._pull(candidate.number)
            sha = str((detail.get("head") or {}).get("sha") or "")
            if detail.get("state") != "open" or sha != candidate.head_sha:
                report.outcomes.append(Outcome(candidate, "skipped", "head mudou ou PR fechada durante o run"))
                continue
            if HOLD_LABEL in {str((label or {}).get("name")) for label in detail.get("labels") or []}:
                report.outcomes.append(Outcome(candidate, "skipped", f"rótulo {HOLD_LABEL}"))
                continue
            state = detail.get("mergeable_state")
            if state == "behind":
                if not self.live:
                    report.outcomes.append(Outcome(candidate, "would-update", "atrás da main: seria atualizada e validada"))
                    continue
                outcome = self._update_and_validate(candidate, sha)
            elif state in {"clean", "has_hooks"}:
                green, _settled, reason = self._checks(sha, candidate.lane)
                if not green:
                    outcome = Outcome(candidate, "skipped", reason)
                elif not self.live:
                    outcome = Outcome(candidate, "would-merge", "seria mesclada (squash)")
                else:
                    outcome = self._merge(candidate, sha)
            else:
                meaning = {"dirty": "conflito com a main", "blocked": "bloqueada pelas regras da main (checks obrigatórios)",
                           "unstable": "algum check não obrigatório está vermelho", "draft": "rascunho"}
                outcome = Outcome(candidate, "skipped", meaning.get(str(state), f"estado de merge {_text(state, 20)}"))
            report.outcomes.append(outcome)
            if outcome.action == "merged":
                merges += 1
            elif outcome.reason.startswith(("janela fechada", "o deploy de até", "backtest PIT")):
                stop = outcome.reason
        if not self.live:
            report.deploy = (f"seria disparado para a main ({deploy_state})" if pending_deploy else "não necessário")
        elif merges:
            report.deploy = self._deploy(f"{merges} merge(s) deste run")
        elif pending_deploy:
            report.deploy = self._deploy(f"main sem deploy concluído: {deploy_state}")
        else:
            report.deploy = "não necessário"
        return report


# ------------------------------------------------------------------------------------ summary
ACTION_LABELS = (
    ("merged", "Mescladas (squash)"),
    ("would-merge", "Seriam mescladas (dry-run)"),
    ("updated", "Atualizadas com a main (update-branch) e validação disparada"),
    ("would-update", "Seriam atualizadas com a main (dry-run)"),
    ("skipped", "Não mescladas"),
)


def render(report: Report, *, run_url: str, now: datetime) -> str:
    local = report.started_at.astimezone(SAO_PAULO)
    lines = [
        marker(now),
        f"## Janela de merge de segurança — {local:%d/%m/%Y %H:%M} BRT"
        + ("" if report.live else " (dry-run: nada foi escrito)"),
        "",
        f"- Janela: {report.gate or 'aberta'} · limite {report.max_merges} merge(s) por run"
        + (f" · {report.alerts}" if report.alerts else ""),
    ]
    for action, label in ACTION_LABELS:
        items = [outcome for outcome in report.outcomes if outcome.action == action]
        if not items:
            continue
        lines.append(f"- {label}:")
        for outcome in items:
            detail = f" — {outcome.candidate.detail}" if outcome.candidate.detail else ""
            lines.append(f"  - #{outcome.candidate.number} ({outcome.candidate.lane}){detail}: {_text(outcome.reason, 220)}")
    ignored = [candidate for candidate in report.ignored if not candidate.security]
    if ignored:
        lines.append(f"- Fora do escopo (sem sinal de segurança): {', '.join(f'#{item.number}' for item in ignored)}")
    lines += [
        f"- Deploy de produção: {report.deploy or 'não necessário'}",
        "",
        "Só entram atualizações de segurança (alerta Dependabot aberto corrigido pela nova versão, patch/minor, "
        "somente manifestos) e a lane de contêiner com prova de zero C/H fixável; checks obrigatórios verdes no head exato.",
        "",
        f"[Run da janela]({run_url}) · no máximo um comentário por dia (BRT).",
        "",
    ]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--channel-issue", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--mode", choices=("live", "dry-run"), required=True)
    parser.add_argument("--max-merges", type=int, default=3)
    parser.add_argument("--body", type=Path, required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, api: Any = None,
         clock: Callable[[], datetime] | None = None, sleep: Callable[[float], None] | None = None) -> int:
    args = parse_args(argv)
    if not args.run_url.startswith("https://github.com/"):
        raise SystemExit("run_url must be an HTTPS GitHub URL")
    if not args.channel_issue.isdigit():
        raise SystemExit("channel issue must be a number")
    if not 1 <= args.max_merges <= 5:
        raise SystemExit("max merges must be between 1 and 5")
    if api is None:
        token = os.environ.get("GH_TOKEN") or ""
        if not token:
            raise SystemExit("GH_TOKEN is required")
        api = GitHub(token, args.repository)
    window = MergeWindow(api, repository=args.repository, live=args.mode == "live", max_merges=args.max_merges)
    if clock is not None:
        window.clock = clock
    if sleep is not None:
        window.sleep = sleep
    report = window.run()
    now = window.clock()
    body = render(report, run_url=args.run_url, now=now)
    print(body)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(body.split("\n", 1)[1] + "\n")
    post, problem = False, None
    if report.worth_posting():
        since = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        comments = [item.get("body") for item in api.pages(
            f"/issues/{args.channel_issue}/comments?since={quote(since)}&per_page=100")
            if (item.get("user") or {}).get("login") == ACTIONS_LOGIN]
        if not already_posted(comments, marker(now)):
            problem = channel_problem(api.request("GET", f"/issues/{args.channel_issue}"))
            post = problem is None
    if problem:
        print(f"::error::Resumo da janela de segurança não publicado no canal #{args.channel_issue}: {problem}")
    if post:
        args.body.write_text(body, encoding="utf-8")
    with args.github_output.open("a", encoding="utf-8") as handle:
        handle.write(f"post={'true' if post else 'false'}\n")
        handle.write(f"merged={len(report.merged)}\n")
    return 1 if problem else 0


if __name__ == "__main__":
    raise SystemExit(main())
