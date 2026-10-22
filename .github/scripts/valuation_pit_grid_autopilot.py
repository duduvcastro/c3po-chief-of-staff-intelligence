#!/usr/bin/env python3
"""The decision of ``.github/workflows/valuation-pit-grid-autopilot.yml`` (PREREG_VALUATION_PIT_BACKTEST_US_V1 §14 d).

One tick decides whether to dispatch ONE more chunk of the US PIT grid through ``valuation-pit-backtest.yml`` (mode
``grid``), with the parameters of the repository variables ``C3PO_PIT_GRID_*`` only — never an input, never a value read
from a run, a log or a comment. It reads data GitHub already holds (the backtest's runs, the jobs and the log of the last
failed grid chunk, the metadata artifact of the last successful one, the channel's recent bot comments) and the owner's
order file of the checkout; it never touches the host or the database. The state is the run history: nothing is written
to the repository.

Order of the checks (the first that applies decides):
  1. ``C3PO_PIT_GRID_AUTOPILOT`` is not ``on``                          → no-op
  2. now is after ``C3PO_PIT_GRID_UNTIL``                              → no-op
  3. a variable is invalid or disagrees with the owner's order file    → no-op, one channel comment per BRT day;
     now is after the order's not_after                                → no-op
  4. a run of valuation-pit-backtest.yml (any mode) is not completed, or one was created in the last 10 min → no-op
  5. no successful grid chunk of this owner order yet                  → the FIRST chunk, capped at FIRST_CHUNK_MAX_RUNS (§14 d "start
     with 10"), posted once; the operator does the post-first-chunk checks and turns the autopilot off if they fail;
     the last successful chunk ran under another owner order           → no-op, unless the order of the variables is that
     order's direct successor (below): then the grid goes on under it
  6. the last successful chunk's manifest says ``complete: true``      → no-op, one channel comment per manifest
  7. grid chunks completed AFTER the last successful one did not succeed — EVERY one of them is classified:
       a retryable refusal (the window step; remote status 11 reboot pending, 17 deploy lock, 19 R2D2/massive timer,
       21 blocking ingestion, 25 not enough time left before the window) → go on (retried this tick; a repeating
       reboot pending is posted once per BRT day)
       anything else, in ANY of them (a run error, a producer mismatch, a data error, the deadline's 124, a cancel, an
       unreadable status) → STOP: no-op, one channel comment per stopping run; the stop lasts until a newer grid chunk
       succeeds (a chunk the operator dispatches by hand and that succeeds reopens the autopilot)
  8. now is inside a forbidden window or less than 40 min before the next one → no-op
  9. otherwise                                                          → dispatch one chunk

Successor order (owner order 3 of 22/10/2026 extends the grid to the weekend): a grid begun under one owner order goes on
under the order of the variables only when that order DIRECTLY supersedes it — its file (this checkout's, verified by its
hash) carries ``"supersedes": <the order of the last successful chunk>``, and the superseded order's file, in this checkout
too and verified by its hash, is a grid order of the same schema and prereg with the same two pins (as instants) and
``recompute_existing=false`` in both. One link only: the order that the superseded one superseded counts for nothing.
Anything else stays the no-op ``last_chunk_of_another_order``. The chunks completed after the last success are classified
whatever order they ran under (a stop under the superseded order still stops under its successor).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
BACKTEST_WORKFLOW = ".github/workflows/valuation-pit-backtest.yml"
CONFIRMATION = "RUN VALUATION PIT BACKTEST"
GRID_TITLE_SUFFIX = "— grid"
LEAD_MINUTES = 40  # never dispatch less than this before the next forbidden window (the grid itself refuses under 35)
RECENT_RUN_MINUTES = 10  # a run created this recently may not be listed as in progress yet: wait for the next tick
MAX_RUNS_LIMIT = 200
FIRST_CHUNK_MAX_RUNS = 10
RETRYABLE_STATUS = {11: "reboot_pending", 17: "deploy_lock", 19: "r2d2_timer", 21: "blocking_ingestion", 25: "window_leg_floor"}
WINDOW_STEP = "Check the operating window"
FAIL_STEP = "Fail when the host step failed"
MARKER = "valuation-pit-grid-autopilot"
BOT_LOGIN = "github-actions[bot]"
VARIABLES = ("C3PO_PIT_GRID_ORDER_SHA256", "C3PO_PIT_GRID_PRICE_PIN", "C3PO_PIT_GRID_CATALOGUE_PIN", "C3PO_PIT_GRID_PREREG_COMMIT",
             "C3PO_PIT_GRID_MAX_RUNS", "C3PO_PIT_GRID_AUTOPILOT", "C3PO_PIT_GRID_UNTIL")
INSTANT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$")  # the backtest's
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
# the two lines the backtest prints with the remote exit status (its "Run on the host" and "Fail when the host step
# failed" steps); the step's own script, echoed in the log, carries `$rc`/`$RC` there and never matches the digits
REMOTE_STATUS = (re.compile(r"remote exit status: ([0-9]{1,3}); remote stderr lines"),
                 re.compile(r"the host step exited with status ([0-9]{1,3}) \(its stderr is kept private\)"))


class InputError(Exception):
    """A GitHub payload this tick cannot read: the tick fails (red) and dispatches nothing."""


def instant(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or INSTANT.match(value) is None:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(dt.timezone.utc) if parsed.tzinfo is not None else None


def _time(value: Any) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise InputError("a run timestamp cannot be read") from error
    if parsed.tzinfo is None:
        raise InputError("a run timestamp has no zone")
    return parsed.astimezone(dt.timezone.utc)


# ---------------------------------------------------------------------------------------------------------------- parameters
@dataclass(frozen=True)
class Parameters:
    autopilot: bool
    order_sha256: str
    price_pinned_at: str
    catalogue_pinned_at: str
    prereg_commit: str
    max_runs: int
    until: dt.datetime | None
    problems: tuple[str, ...] = ()


def parameters(env: Mapping[str, str]) -> Parameters:
    """The grid's parameters from the repository variables (and nowhere else); a malformed one is a named problem."""
    problems: list[str] = []
    order = env.get("C3PO_PIT_GRID_ORDER_SHA256", "").strip()
    price_pin = env.get("C3PO_PIT_GRID_PRICE_PIN", "").strip()
    catalogue_pin = env.get("C3PO_PIT_GRID_CATALOGUE_PIN", "").strip()
    commit = env.get("C3PO_PIT_GRID_PREREG_COMMIT", "").strip()
    raw_max = env.get("C3PO_PIT_GRID_MAX_RUNS", "").strip()
    raw_until = env.get("C3PO_PIT_GRID_UNTIL", "").strip()
    if SHA256.match(order) is None:
        problems.append("C3PO_PIT_GRID_ORDER_SHA256 não é um sha256 (64 hex minúsculos)")
    if instant(price_pin) is None:
        problems.append("C3PO_PIT_GRID_PRICE_PIN não é um instante ISO-8601 com fuso")
    if instant(catalogue_pin) is None:
        problems.append("C3PO_PIT_GRID_CATALOGUE_PIN não é um instante ISO-8601 com fuso")
    if COMMIT.match(commit) is None:
        problems.append("C3PO_PIT_GRID_PREREG_COMMIT não é um commit (40 hex)")
    max_runs = int(raw_max) if re.fullmatch(r"[0-9]{1,3}", raw_max) else 0
    if not 1 <= max_runs <= MAX_RUNS_LIMIT:
        problems.append(f"C3PO_PIT_GRID_MAX_RUNS não é um inteiro de 1 a {MAX_RUNS_LIMIT}")
    until = instant(raw_until)
    if until is None:
        problems.append("C3PO_PIT_GRID_UNTIL não é um instante ISO-8601 com fuso")
    return Parameters(autopilot=env.get("C3PO_PIT_GRID_AUTOPILOT", "").strip() == "on", order_sha256=order, price_pinned_at=price_pin,
                      catalogue_pinned_at=catalogue_pin, prereg_commit=commit, max_runs=max_runs, until=until, problems=tuple(problems))


ORDER_FILE_PROBLEMS = {  # what is wrong with the order file of the variables, as posted to the channel
    "not_sha256": "C3PO_PIT_GRID_ORDER_SHA256 não é um sha256 (64 hex minúsculos)",
    "symlink": "o caminho da ordem do dono tem uma ligação simbólica",
    "missing": "a ordem do dono C3PO_PIT_GRID_ORDER_SHA256 não existe nesta revisão",
    "hash": "o ficheiro da ordem do dono não tem o sha256 da variável",
    "not_json": "a ordem do dono não é JSON",
    "not_object": "a ordem do dono não é um objeto JSON",
}


def read_order(root: Path, digest: str) -> tuple[dict[str, Any] | None, str]:
    """``c3po/ops/owner-orders/<digest>.json`` of this checkout, read as the backtest reads it — no symbolic link on its
    path, its bytes hash to its name, a JSON object: (the object, "") or (None, what is wrong: a key of ORDER_FILE_PROBLEMS)."""
    if SHA256.match(digest) is None:
        return None, "not_sha256"
    root = root.resolve()
    relative = Path("c3po") / "ops" / "owner-orders" / f"{digest}.json"
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return None, "symlink"
    path = root / relative
    if not path.is_file():
        return None, "missing"
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != digest:
        return None, "hash"
    try:
        data = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, "not_json"
    if not isinstance(data, dict):
        return None, "not_object"
    return data, ""


def order_check(root: Path, params: Parameters) -> tuple[list[str], dt.datetime | None]:
    """The owner's order file of this checkout must exist, hash to the variable and authorise exactly these parameters
    (the backtest verifies it again at its own revision): a disagreement here dispatches nothing."""
    if SHA256.match(params.order_sha256) is None:
        return [], None  # already a named problem
    data, problem = read_order(root, params.order_sha256)
    if data is None:
        return [ORDER_FILE_PROBLEMS[problem]], None
    problems: list[str] = []
    if data.get("schema") != "VALUATION-PIT-BACKTEST-OWNER-ORDER-v1" or data.get("prereg") != "PREREG_VALUATION_PIT_BACKTEST_US_V1":
        problems.append("a ordem do dono não é uma VALUATION-PIT-BACKTEST-OWNER-ORDER-v1 deste pré-registro")
    modes = data.get("modes")
    if not isinstance(modes, list) or "grid" not in modes:
        problems.append("a ordem do dono não autoriza o modo grid")
    if instant(params.price_pinned_at) is not None and instant(data.get("price_pinned_at")) != instant(params.price_pinned_at):
        problems.append("C3PO_PIT_GRID_PRICE_PIN difere do pino de preços da ordem")
    if instant(params.catalogue_pinned_at) is not None and instant(data.get("catalogue_pinned_at")) != instant(params.catalogue_pinned_at):
        problems.append("C3PO_PIT_GRID_CATALOGUE_PIN difere do pino do catálogo da ordem")
    if data.get("recompute_existing") is not False:
        problems.append("a ordem do dono não autoriza recompute_existing=false")
    cap = data.get("max_runs_cap")
    if not isinstance(cap, int) or isinstance(cap, bool) or params.max_runs > cap:
        problems.append("C3PO_PIT_GRID_MAX_RUNS excede o max_runs_cap da ordem")
    not_after = instant(data.get("not_after"))
    if not_after is None:
        problems.append("a ordem do dono não tem not_after legível")
    return problems, not_after


def successor_refusal(root: Path, params: Parameters, chunk_order: Any) -> str | None:
    """None when the order of the variables (already checked by ``order_check``) DIRECTLY supersedes ``chunk_order``, the
    order under which the last successful chunk ran: its file names that order in ``supersedes``, and that order's file —
    in this checkout too, verified by its hash — has the same schema and prereg, the grid among its modes, the same two
    pins (as instants) and ``recompute_existing=false``, as the successor has. One link only. Otherwise the reason (a label)."""
    if not isinstance(chunk_order, str) or SHA256.match(chunk_order) is None:
        return "chunk_order_unreadable"
    current, problem = read_order(root, params.order_sha256)
    if current is None:
        return f"order_{problem}"
    if current.get("supersedes") != chunk_order:
        return "not_superseded"
    previous, problem = read_order(root, chunk_order)
    if previous is None:
        return f"superseded_order_{problem}"
    if previous.get("schema") != current.get("schema") or previous.get("prereg") != current.get("prereg"):
        return "superseded_order_other_prereg"
    modes = previous.get("modes")
    if not isinstance(modes, list) or "grid" not in modes:
        return "superseded_order_without_grid"
    for key in ("price_pinned_at", "catalogue_pinned_at"):
        pin = instant(previous.get(key))
        if pin is None or pin != instant(current.get(key)):
            return f"superseded_order_other_{key}"
    if previous.get("recompute_existing") is not False or current.get("recompute_existing") is not False:
        return "recompute_existing_not_false"
    return None


# ---------------------------------------------------------------------------------------------------------------- windows
def forbidden_windows(now: dt.datetime) -> list[tuple[dt.datetime, dt.datetime]]:
    """The backtest's windows, exactly as its "Check the operating window" step builds them: the US session with its
    buffer, 09:00-16:30 America/New_York on weekdays (holidays count as sessions), and the nightly window, 23:30 of the
    previous day to 08:15 America/Sao_Paulo. Wall-clock times in each zone: daylight saving is the zone's."""
    windows = []
    for offset in range(-2, 6):
        day = now.astimezone(NEW_YORK).date() + dt.timedelta(days=offset)
        if day.weekday() < 5:
            windows.append((dt.datetime.combine(day, dt.time(9, 0), NEW_YORK), dt.datetime.combine(day, dt.time(16, 30), NEW_YORK)))
        local = now.astimezone(SAO_PAULO).date() + dt.timedelta(days=offset)
        windows.append((dt.datetime.combine(local - dt.timedelta(days=1), dt.time(23, 30), SAO_PAULO), dt.datetime.combine(local, dt.time(8, 15), SAO_PAULO)))
    return windows


def window_state(now: dt.datetime) -> tuple[bool, dt.datetime]:
    """(inside a forbidden window, the start of the next one)."""
    windows = forbidden_windows(now)
    inside = any(start <= now < end for start, end in windows)
    upcoming = min(start for start, _end in windows if start > now)
    return inside, upcoming


# ---------------------------------------------------------------------------------------------------------------- runs
def _id(run: Mapping[str, Any]) -> int:
    value = run.get("id")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InputError("a run id is invalid")
    return value


def _runs(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list) or not all(isinstance(run, dict) for run in payload):
        raise InputError("the run listing is not a list of runs")
    return sorted(payload, key=lambda run: (_time(run.get("created_at")), _id(run)), reverse=True)  # newest first


def is_grid_chunk(run: Mapping[str, Any]) -> bool:
    """A grid chunk of the backtest dispatched from main (the run-name ends with the mode)."""
    path = str(run.get("path") or "")
    return ((path == BACKTEST_WORKFLOW or path.startswith(BACKTEST_WORKFLOW + "@")) and run.get("event") == "workflow_dispatch"
            and run.get("head_branch") == "main" and str(run.get("display_title") or "").endswith(GRID_TITLE_SUFFIX))


def select(payload: Any) -> tuple[list[int], int | None]:
    """(every completed grid chunk newer than the last successful one — none succeeded —, newest first; the last
    successful grid chunk) — what the workflow fetches before the decision (each failed run's jobs and log, the
    successful run's metadata artifact). Without a successful chunk every completed grid chunk is classified (a
    non-retryable one stops the first chunk too)."""
    completed = [run for run in _runs(payload) if is_grid_chunk(run) and run.get("status") == "completed"]
    index = next((position for position, run in enumerate(completed) if run.get("conclusion") == "success"), None)
    if index is None:
        return [_id(run) for run in completed], None
    return [_id(run) for run in completed[:index]], _id(completed[index])


def remote_status(log: str) -> int | None:
    """The remote exit status the failed chunk printed — one value, or None when absent or ambiguous."""
    found = {int(match.group(1)) for pattern in REMOTE_STATUS for match in pattern.finditer(log)}
    return found.pop() if len(found) == 1 else None


@dataclass(frozen=True)
class Failure:
    retryable: bool
    label: str
    status: int | None = None
    step: str | None = None


def classify(run: Mapping[str, Any], jobs: Any, log: str | None) -> Failure:
    """A failed chunk: retryable refusals go on; anything else stops the autopilot (the operator decides)."""
    conclusion = str(run.get("conclusion") or "")
    if conclusion != "failure":
        return Failure(False, f"conclusion_{re.sub(r'[^a-z_]', '', conclusion) or 'unknown'}")
    if not isinstance(jobs, dict) or not isinstance(jobs.get("jobs"), list):
        raise InputError("the failed run's jobs cannot be read")
    failed_steps: list[tuple[int, str]] = []
    for job in jobs["jobs"]:
        if not isinstance(job, dict) or job.get("run_id") != _id(run):
            raise InputError("a job of the listing is not of the failed run")
        for step in job.get("steps") or []:
            if isinstance(step, dict) and step.get("conclusion") == "failure":
                number = step.get("number")
                failed_steps.append((number if isinstance(number, int) and not isinstance(number, bool) else 10 ** 6, str(step.get("name") or "")))
    if not failed_steps:
        return Failure(False, "no_failed_step")
    step = min(failed_steps)[1]
    if step == WINDOW_STEP:
        return Failure(True, "window", step=step)
    if step != FAIL_STEP:
        return Failure(False, "step_failed", step=step)
    status = remote_status(log or "")
    if status is None:
        return Failure(False, "status_unreadable", step=step)
    if status in RETRYABLE_STATUS:
        return Failure(True, RETRYABLE_STATUS[status], status, step)
    if status == 0:
        return Failure(False, "published_as_error", status, step)
    return Failure(False, "host_exit", status, step)


# ---------------------------------------------------------------------------------------------------------------- decision
@dataclass
class Decision:
    action: str  # noop | dispatch | stop
    reason: str
    post_key: str | None = None
    post_body: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def _text(value: Any, limit: int = 80) -> str:
    text = str(value)
    for token in ("<", ">", "@", "`", "|", "[", "]", "(", ")"):
        text = text.replace(token, "")
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def marker(key: str) -> str:
    return f"<!-- {MARKER}:{key} -->"


def already_posted(comments: Any, key: str) -> bool:
    """Only a bot comment whose FIRST line is the marker counts (a marker quoted elsewhere never suppresses a post)."""
    if not isinstance(comments, list):
        raise InputError("the channel comment listing is not a list")
    return any(isinstance(body, str) and body.split("\n", 1)[0].strip() == marker(key) for body in comments)


def _run_url(repository: str, run_id: int) -> str:
    return f"https://github.com/{repository}/actions/runs/{run_id}"


def decide(*, env: Mapping[str, str], root: Path, now: dt.datetime, runs: Any, failures: Mapping[int, tuple[Any, str | None]], metadata: Any,
           repository: str, tick_url: str) -> Decision:
    params = parameters(env)
    if not params.autopilot:
        return Decision("noop", "autopilot_off")
    if params.until is not None and now > params.until:
        return Decision("noop", "after_until", details={"until": params.until.isoformat()})
    order_problems, not_after = order_check(root, params)
    problems = [*params.problems, *order_problems]
    if problems:
        key = f"config:{now.astimezone(SAO_PAULO).date().isoformat()}"
        body = "\n".join([marker(key), "**Autopiloto da grade PIT EUA sem despachar** — variáveis do repositório inválidas ou em desacordo com a ordem "
                          "do dono (nada é despachado; os parâmetros só mudam por decisão do operador):", "",
                          *[f"- {problem}" for problem in problems], "", f"[Tick do autopiloto]({tick_url}) · no máximo um aviso por dia (BRT).", ""])
        return Decision("noop", "invalid_parameters", key, body, {"problems": problems})
    if not_after is not None and now > not_after:  # never past the owner's order, whatever C3PO_PIT_GRID_UNTIL says
        return Decision("noop", "after_until", details={"until": not_after.isoformat()})
    ordered = _runs(runs)
    active = [_id(run) for run in ordered if run.get("status") != "completed"]
    if active:
        return Decision("noop", "run_in_progress", details={"runs": active})
    recent = [_id(run) for run in ordered if now - _time(run.get("created_at")) < dt.timedelta(minutes=RECENT_RUN_MINUTES)]
    if recent:
        return Decision("noop", "recent_run", details={"runs": recent})
    failed_ids, success_id = select(runs)
    if success_id is None:
        metadata = None
    elif not isinstance(metadata, dict) or metadata.get("mode") != "grid" or str(metadata.get("run_id")) != str(success_id):
        raise InputError("the last successful chunk's metadata is not that run's grid metadata")
    successor_of: str | None = None  # the last successful chunk's order, when the order of the variables directly supersedes it
    if metadata is not None and metadata.get("owner_order_sha256") != params.order_sha256:
        refusal = successor_refusal(root, params, metadata.get("owner_order_sha256"))
        if refusal is not None:
            return Decision("noop", "last_chunk_of_another_order", details={"run": success_id, "successor": refusal})
        successor_of = str(metadata["owner_order_sha256"])
    if metadata is not None and metadata.get("partial") is not False:
        raise InputError("the last successful chunk's metadata is marked partial")
    if metadata is not None and metadata.get("complete") is True:
        digest = metadata.get("manifest_sha256")
        if not isinstance(digest, str) or SHA256.match(digest) is None:
            raise InputError("the complete chunk's manifest_sha256 cannot be read")
        key = f"complete:{digest}"
        body = "\n".join([marker(key), f"**grid complete, manifest_sha256 `{digest}`** — grade PIT EUA completa no lote "
                          f"[run {success_id}]({_run_url(repository, success_id)}) (ordem do dono `{(successor_of or params.order_sha256)[:8]}`, {metadata.get('entries')} "
                          f"entradas). O autopiloto não despacha mais nada.", "",
                          f"Próximo passo (operador, §14 d/e): publicar este `manifest_sha256` e, depois, o modo `report` com `manifest_run_id` "
                          f"{success_id}, este `manifest_sha256` e `prereg_commit` `{params.prereg_commit}`.", "",
                          f"[Tick do autopiloto]({tick_url})", ""])
        return Decision("noop", "grid_complete", key, body, {"run": success_id, "manifest_sha256": digest})
    by_id = {_id(run): run for run in ordered}
    classified = [(failed_id, classify(by_id[failed_id], *failures.get(failed_id, (None, None)))) for failed_id in failed_ids]
    retry: Failure | None = classified[0][1] if classified else None  # the newest failed chunk: the one retried
    for failed_id, failure in classified:  # newest first: the newest stopping chunk is the one posted
        failed_run = by_id[failed_id]
        if not failure.retryable:
            key = f"stop:{failed_id}"
            status = "não lido" if failure.status is None else f"`{failure.status}`"
            body = "\n".join([marker(key), f"**Autopiloto da grade PIT EUA PARADO** — o lote [run {failed_id}]({_run_url(repository, failed_id)}) terminou "
                              f"`{_text(failed_run.get('conclusion'), 20)}`; passo `{_text(failure.step or '-')}`; código remoto {status} "
                              f"(`{failure.label}`; só o agregado, o stderr fica privado no host).", "",
                              "Não é uma recusa reexecutável (janela; 11 reinício pendente; 17 lock de deploy; 19 timer R2D2/massive; 21 ingestão bloqueante; 25 sem tempo "
                              "antes da janela). Regra de parada do §14 d: o autopiloto **não despacha mais nada** e nunca muda parâmetros. O operador "
                              "decide — diagnosticar; erro de dados → corrigir e retomar com os MESMOS parâmetros. Um lote despachado à mão que termine "
                              "com sucesso reabre o autopiloto; `C3PO_PIT_GRID_AUTOPILOT=off` desliga-o.", "",
                              f"[Tick do autopiloto]({tick_url}) · um aviso por lote parado.", ""])
            return Decision("stop", failure.label, key, body, {"run": failed_id, "status": failure.status, "step": failure.step})
    inside, upcoming = window_state(now)
    minutes = (upcoming - now).total_seconds() / 60
    if inside:
        decision = Decision("noop", "inside_window", details={"next_window": upcoming.isoformat()})
    elif minutes < LEAD_MINUTES:
        decision = Decision("noop", "window_too_close", details={"next_window": upcoming.isoformat(), "minutes": round(minutes)})
    else:
        first = success_id is None
        details: dict[str, Any] = {"after_run": success_id, "next_window": upcoming.isoformat(), "minutes": round(minutes),
                                   "max_runs": min(params.max_runs, FIRST_CHUNK_MAX_RUNS) if first else params.max_runs,
                                   "remaining": None if metadata is None else metadata.get("remaining")}
        if retry is not None:
            details.update({"retry_of": failed_ids[0], "retry_status": retry.status, "failed_since_success": len(failed_ids)})
        reason = f"retry_after_{retry.label}" if retry is not None else ("first_chunk" if first else "next_chunk")
        decision = Decision("dispatch", reason, details=details)
        if first:
            key = "first-chunk"
            decision.post_key = key
            decision.post_body = "\n".join([marker(key), f"**Autopiloto da grade PIT EUA: primeiro lote despachado** (ordem do dono `{params.order_sha256[:8]}`, "
                                              f"`max_runs` {details['max_runs']}, §14 d \"start with 10\"). O operador faz as conferências pós-primeiro-lote "
                                              "(`covered_without_rows_by_T` de 2021, `volume_basis` e o primeiro `manifest_sha256` no canal, custo por data) e "
                                              "desliga o autopiloto (`C3PO_PIT_GRID_AUTOPILOT=off`) se alguma falhar.", "",
                                              f"[Tick do autopiloto]({tick_url}) · um aviso só.", ""])
    if successor_of is not None:  # the link to the superseded order, shown on every tick past it (a dry run inside a window too)
        decision.details["successor_of"] = successor_of
    if retry is not None and retry.label == "reboot_pending":  # retried, but a reboot that stays pending is said once per BRT day
        key = f"reboot:{now.astimezone(SAO_PAULO).date().isoformat()}"
        decision.post_key = key
        decision.post_body = "\n".join([marker(key), f"**Autopiloto da grade PIT EUA: reinício de segurança pendente no host** — o lote "
                                         f"[run {failed_ids[0]}]({_run_url(repository, failed_ids[0])}) foi recusado com o código 11 "
                                         f"({len(failed_ids)} lote(s) sem sucesso desde o último). O autopiloto continua a tentar a cada tick; o "
                                         "reinício pendente é um incidente a tratar (o controlador de reinício espera as escritas).", "",
                                         f"[Tick do autopiloto]({tick_url}) · no máximo um aviso por dia (BRT).", ""])
    return decision


def failing_tick(comments: Any, now: dt.datetime, tick_url: str) -> tuple[str, str] | None:
    """The once-per-BRT-day notice of a failing tick (marker key, body), or None when today's was already posted."""
    key = f"tick-failing:{now.astimezone(SAO_PAULO).date().isoformat()}"
    if already_posted(comments, key):
        return None
    run_id = tick_url.rstrip("/").rsplit("/", 1)[-1]
    body = "\n".join([marker(key), f"**Autopiloto da grade PIT EUA: autopilot tick failing** — o tick [run {_text(run_id, 24)}]({tick_url}) falhou "
                      "(estado do GitHub ilegível, despacho não confirmado ou passo com erro): nada foi despachado por ele. Os ticks seguintes "
                      "tentam de novo; conferir o run.", "", "No máximo um aviso por dia (BRT).", ""])
    return key, body


def comment_bodies(raw: str) -> list[str]:
    """The bot comment bodies of `gh api --paginate` over an issue's comments (one JSON array per page, concatenated)."""
    decoder, position, bodies = json.JSONDecoder(), 0, []
    text = raw.strip()
    while position < len(text):
        try:
            page, end = decoder.raw_decode(text, position)
        except ValueError as error:
            raise InputError("the channel comment pages are not JSON") from error
        if not isinstance(page, list):
            raise InputError("a channel comment page is not a list")
        bodies += [str(item.get("body") or "") for item in page if isinstance(item, dict) and (item.get("user") or {}).get("login") == BOT_LOGIN]
        position = end
        while position < len(text) and text[position].isspace():
            position += 1
    return bodies


# ---------------------------------------------------------------------------------------------------------------- CLI
def _load(path: Path | None) -> Any:
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise InputError(f"{path.name} is not JSON") from error


def _output(path: Path | None, values: Mapping[str, str]) -> None:
    for key, value in values.items():
        if "\n" in value or "\r" in value:
            raise SystemExit(f"output {key} holds a line break")
    if path is None:
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write("".join(f"{key}={value}\n" for key, value in values.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="valuation PIT grid autopilot: one tick")
    sub = parser.add_subparsers(dest="command", required=True)
    pick = sub.add_parser("select")
    pick.add_argument("--runs", type=Path, required=True)
    pick.add_argument("--github-output", type=Path)
    tick = sub.add_parser("decide")
    tick.add_argument("--runs", type=Path, required=True)
    tick.add_argument("--failed-dir", type=Path, help="<run id>.jobs.json and <run id>.log of each failed chunk since the last success")
    tick.add_argument("--metadata", type=Path)
    tick.add_argument("--comments", type=Path, required=True)
    tick.add_argument("--root", type=Path, required=True)
    tick.add_argument("--repository", required=True)
    tick.add_argument("--tick-url", required=True)
    tick.add_argument("--ref", required=True)
    tick.add_argument("--dry-run", choices=("true", "false"), required=True)
    tick.add_argument("--body", type=Path, required=True)
    tick.add_argument("--github-output", type=Path)
    tick.add_argument("--summary", type=Path)
    tick.add_argument("--now", default=None, help="tests only")
    fail = sub.add_parser("failing")
    fail.add_argument("--comments-raw", type=Path, required=True, help="the raw `gh api --paginate` output over the channel's recent comments")
    fail.add_argument("--tick-url", required=True)
    fail.add_argument("--body", type=Path, required=True)
    fail.add_argument("--github-output", type=Path)
    fail.add_argument("--now", default=None, help="tests only")
    args = parser.parse_args(argv)
    try:
        if args.command == "select":
            failed, success = select(_load(args.runs))
            _output(args.github_output, {"failed_run_ids": " ".join(str(item) for item in failed), "success_run_id": str(success or "")})
            print(json.dumps({"failed_run_ids": failed, "success_run_id": success}, sort_keys=True))
            return 0
        if not args.tick_url.startswith("https://github.com/"):
            raise SystemExit("the tick url is invalid")
        if args.command == "failing":
            moment = instant(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
            if moment is None:
                raise SystemExit("--now must be ISO-8601 with a zone")
            notice = failing_tick(comment_bodies(args.comments_raw.read_text(encoding="utf-8")), moment, args.tick_url)
            if notice is not None:
                args.body.write_text(notice[1], encoding="utf-8")
            _output(args.github_output, {"post": "true" if notice is not None else "false"})
            return 0
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository) is None or not args.tick_url.startswith("https://github.com/"):
            raise SystemExit("repository or tick url is invalid")
        now = instant(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
        if now is None:
            raise SystemExit("--now must be ISO-8601 with a zone")
        runs = _load(args.runs)
        failures: dict[int, tuple[Any, str | None]] = {}
        for failed_id in select(runs)[0]:
            jobs_path = args.failed_dir / f"{failed_id}.jobs.json" if args.failed_dir is not None else None
            log_path = args.failed_dir / f"{failed_id}.log" if args.failed_dir is not None else None
            log = log_path.read_text(encoding="utf-8", errors="replace") if log_path is not None and log_path.is_file() else None
            failures[failed_id] = (_load(jobs_path), log)
        inputs: dict[str, Any] = {"root": args.root, "now": now, "runs": runs, "failures": failures, "metadata": _load(args.metadata),
                                  "repository": args.repository, "tick_url": args.tick_url}
        decision = decide(env=os.environ, **inputs)
        if decision.reason == "autopilot_off" and args.dry_run == "true":  # a dry run shows what the tick WOULD do were it on (never acted on)
            preview = decide(env={**os.environ, "C3PO_PIT_GRID_AUTOPILOT": "on"}, **inputs)
            decision.details["preview"] = {"action": preview.action, "reason": preview.reason, **preview.details}
        post = decision.post_key is not None and not already_posted(_load(args.comments) or [], decision.post_key)
    except InputError as error:
        print(f"::error::the tick cannot read GitHub's state ({error}): nothing is dispatched", file=sys.stderr)
        return 1
    act = args.dry_run == "false" and args.ref == "refs/heads/main"
    params = parameters(os.environ)
    values = {"action": decision.action, "reason": decision.reason, "act": "true" if act else "false", "post": "true" if post else "false"}
    if decision.action == "dispatch":
        values.update({"order": params.order_sha256, "price_pin": params.price_pinned_at, "catalogue_pin": params.catalogue_pinned_at,
                       "prereg_commit": params.prereg_commit, "max_runs": str(decision.details.get("max_runs", params.max_runs))})
    if post and decision.post_body is not None:
        args.body.write_text(decision.post_body, encoding="utf-8")
    _output(args.github_output, values)
    record = {"action": decision.action, "reason": decision.reason, "act": act, "post": post, "details": decision.details}
    print(json.dumps(record, sort_keys=True, default=str))
    if args.summary is not None:
        mode = "ACT" if act else "DRY-RUN (nothing dispatched, nothing posted)"
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write(f"## Valuation PIT grid autopilot — {mode}\n\n- action `{decision.action}`, reason `{decision.reason}`, channel post {post}\n"
                         f"- details `{json.dumps(decision.details, sort_keys=True, default=str)}`\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
