#!/usr/bin/env python3
"""Escalate aged governance signals to the Fable/Codex channel (issue #429).

Runs on GitHub with the workflow GITHUB_TOKEN only. It reads data GitHub
already holds (open pull requests and workflow runs); it never reads the app
database or the host. The in-app incident carries the same verdict in its
``escalation`` evidence, but GitHub cannot read it without a new credential.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SAO_PAULO = ZoneInfo("America/Sao_Paulo")
INCIDENT_KEY = "governance-vulnerability"
THRESHOLD = timedelta(hours=24)
SUCCESSFUL = {"success", "skipped", "neutral"}
BOT_LOGIN = "github-actions[bot]"
CHANNEL_COMMENT_LIMIT = 2400


def _parse_time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def _age(delta: timedelta) -> str:
    hours = max(0, int(delta.total_seconds() // 3600))
    return f"{hours // 24}d" if hours >= 24 else f"{hours}h"


def _text(value: Any, limit: int = 100) -> str:
    """Untrusted text: no HTML comment delimiters (dedupe marker spoofing),
    no mentions, no code spans; single line; truncated."""
    text = str(value)
    for token in ("<!--", "-->", "@", "`"):
        text = text.replace(token, "")
    text = " ".join(text.split()).replace("|", "/")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def marker(now: datetime) -> str:
    day = now.astimezone(SAO_PAULO).date().isoformat()
    return f"<!-- c3po-incident-escalation:{INCIDENT_KEY}:{day} -->"


def lane_signals(pulls: Any, repository: str, now: datetime) -> list[str]:
    """Trusted automation/* lanes (same rule as the app) open for more than 24h."""
    if not isinstance(pulls, list):
        raise ValueError("pull request listing is not a list")
    signals: list[tuple[datetime, str]] = []
    for pull in pulls:
        if not isinstance(pull, dict):
            raise ValueError("pull request entry is not an object")
        head = pull.get("head") or {}
        if (
            not str(head.get("ref") or "").startswith("automation/")
            or (head.get("repo") or {}).get("full_name") != repository
            or (pull.get("base") or {}).get("ref") != "main"
            or (pull.get("user") or {}).get("login") != BOT_LOGIN
        ):
            continue
        number = pull.get("number")
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            raise ValueError("lane number is invalid")
        created_at = _parse_time(pull.get("created_at"))
        if now - created_at <= THRESHOLD:
            continue
        signals.append((
            created_at,
            f"lane de remediação [#{number}](https://github.com/{repository}/pull/{number}) "
            f"aberta há {_age(now - created_at)} — {_text(pull.get('title'))}",
        ))
    return [text for _created, text in sorted(signals)]


def workflow_signal(workflow: str, runs: Any, now: datetime, repository: str) -> str | None:
    """Latest completed main-branch run failed and nothing succeeded for >24h."""
    if not isinstance(runs, list):
        raise ValueError(f"{workflow}: run listing is not a list")
    completed = sorted(
        (
            run for run in runs
            if isinstance(run, dict)
            and run.get("status") == "completed"
            and run.get("head_branch") == "main"
        ),
        key=lambda run: _parse_time(run.get("created_at")),
        reverse=True,
    )
    if not completed or completed[0].get("conclusion") in SUCCESSFUL:
        return None
    last_success = next(
        (run for run in completed if run.get("conclusion") == "success"), None
    )
    if last_success is not None:
        since_success = now - _parse_time(last_success.get("created_at"))
        if since_success <= THRESHOLD:
            return None
        quiet = f"último sucesso há {_age(since_success)}"
    else:
        quiet = f"nenhum sucesso nas últimas {len(completed)} execuções concluídas"
    latest = completed[0]
    run_id = latest.get("id")
    if isinstance(run_id, bool) or not isinstance(run_id, int):
        raise ValueError(f"{workflow}: run id is invalid")
    return (
        f"`{workflow}` sem sucesso: {quiet}; última conclusão "
        f"`{_text(latest.get('conclusion'), 30)}` no "
        f"[run {run_id}](https://github.com/{repository}/actions/runs/{run_id})"
    )


def already_escalated(channel_comments: Any, escalation_marker: str) -> bool:
    """Dedupe only on a bot comment whose FIRST line is the marker; a marker
    quoted anywhere else in a comment never suppresses the escalation."""
    if not isinstance(channel_comments, list):
        raise ValueError("channel comment listing is not a list")
    return any(
        isinstance(body, str) and body.split("\n", 1)[0].strip() == escalation_marker
        for body in channel_comments
    )


def channel_problem(channel: Any, *, limit: int = CHANNEL_COMMENT_LIMIT) -> str | None:
    if not isinstance(channel, dict):
        return "metadados do canal ilegíveis"
    if channel.get("state") != "open":
        return f"canal não está aberto (state={_text(channel.get('state'), 20)})"
    if channel.get("locked") is not False:
        return "canal está trancado (locked)"
    comments = channel.get("comments")
    if isinstance(comments, bool) or not isinstance(comments, int):
        return "contagem de comentários do canal ilegível"
    if comments >= limit:
        return f"canal com {comments} comentários (limite operacional {limit}); abra um canal novo e aponte C3PO_ESCALATION_ISSUE"
    return None


def render(signals: list[str], escalation_marker: str, run_url: str) -> str:
    lines = [
        escalation_marker,
        "## ESCALADO (>24h) — Governança e vulnerabilidades",
        "",
        "O detector agendado do GitHub encontrou sinais de segurança parados há mais "
        "de 24h. Fonte: apenas dados que o próprio GitHub já tem (PRs e runs); o banco "
        "do app não é lido.",
        "",
        *[f"- {signal}" for signal in signals],
        "",
        "Responsável: Fable/Codex (triagem e correção), sem depender do dono. Fechar a "
        "lane obsoleta ou corrigir a falha encerra o sinal; o incidente do app resolve "
        "sozinho no próximo atestado saudável.",
        "",
        f"[Run do detector]({run_url}) · no máximo um comentário por incidente por dia (BRT).",
        "",
    ]
    return "\n".join(lines)


def decide(
    *,
    pulls: Any,
    runs: dict[str, Any],
    channel_comments: Any,
    repository: str,
    run_url: str,
    now: datetime,
) -> tuple[bool, str, str]:
    signals = lane_signals(pulls, repository, now)
    for workflow in sorted(runs):
        signal = workflow_signal(workflow, runs[workflow], now, repository)
        if signal:
            signals.append(signal)
    escalation_marker = marker(now)
    if not signals:
        return False, "no aged GitHub-visible signal", ""
    if already_escalated(channel_comments, escalation_marker):
        return False, "already escalated today", ""
    return True, f"{len(signals)} aged signal(s)", render(signals, escalation_marker, run_url)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pulls", type=Path, required=True)
    parser.add_argument("--runs", action="append", default=[], metavar="WORKFLOW=FILE")
    parser.add_argument("--channel-comments", type=Path, required=True,
                        help="JSON list of recent bot comment bodies on the channel issue")
    parser.add_argument("--channel-meta", type=Path, required=True,
                        help="JSON {state, locked, comments} of the channel issue")
    parser.add_argument("--channel-issue", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--body", type=Path, required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    parser.add_argument("--now", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.run_url.startswith("https://github.com/"):
        raise SystemExit("run_url must be an HTTPS GitHub URL")
    if not args.channel_issue.isdigit():
        raise SystemExit("channel issue must be a number")
    runs: dict[str, Any] = {}
    for item in args.runs:
        workflow, _, path = item.partition("=")
        if not workflow.endswith(".yml") or not path:
            raise SystemExit(f"invalid --runs value: {item}")
        runs[workflow] = json.loads(Path(path).read_text(encoding="utf-8"))
    now = _parse_time(args.now) if args.now else datetime.now(timezone.utc)
    post, reason, body = decide(
        pulls=json.loads(args.pulls.read_text(encoding="utf-8")),
        runs=runs,
        channel_comments=json.loads(args.channel_comments.read_text(encoding="utf-8")),
        repository=args.repository,
        run_url=args.run_url,
        now=now,
    )
    problem = (
        channel_problem(json.loads(args.channel_meta.read_text(encoding="utf-8")))
        if post else None
    )
    if problem:
        # Fail the run (red) instead of silently losing the escalation; the
        # undelivered text stays in the run log. It never contains secrets.
        print(f"::error::Escalonamento não publicado no canal #{args.channel_issue}: {problem}")
        print(body)
        post = False
    if post:
        args.body.write_text(body, encoding="utf-8")
    with args.github_output.open("a", encoding="utf-8") as handle:
        handle.write(f"post={'true' if post else 'false'}\n")
    print(json.dumps({"post": post, "reason": problem or reason}, sort_keys=True))
    return 1 if problem else 0


if __name__ == "__main__":
    raise SystemExit(main())
