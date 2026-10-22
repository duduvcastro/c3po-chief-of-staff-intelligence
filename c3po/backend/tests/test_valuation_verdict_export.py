"""The decisor's verdicts of one night for the R2D2 lab, ENCRYPTED (owner's order of 2026-10-20): the CLI prints only an
X25519 → HKDF-SHA256 → AES-256-GCM envelope (counts and the plaintext's sha256 in clear, no symbol), refuses an absent or
incomplete night, and the public workflow's runner check accepts exactly the envelope's schema before anything is uploaded."""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import yaml
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from app import valuation_decision as decisor
from app import valuation_official as official
from app import valuation_verdict_export as export
from app.config import Settings
from app.database import Database

UTC = timezone.utc
NIGHT = "2026-10-23"  # Friday: the night Monday 26/10 trades on
RUN = datetime(2026, 10, 24, 4, 30, tzinfo=UTC)  # 01:30 BRT Saturday: the decisor's off-hours phase
NOW = datetime(2026, 10, 26, 11, 0, tzinfo=UTC)  # 08:00 BRT Monday: the scheduled export
NEXT_OPEN = datetime(2026, 10, 26, 13, 30, tzinfo=UTC)  # 09:30 EDT Monday
WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "decisor-verdict-export.yml"
SYMBOLS = ("AAP.L", "K.O", "MSF.T", "XO.M")  # each with a dot: never a substring of base64 by chance


def _keys() -> tuple[str, str]:
    secret = X25519PrivateKey.generate()
    private = secret.private_bytes(encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw,
                                   encryption_algorithm=serialization.NoEncryption())
    public = secret.public_key().public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    return base64.b64encode(private).decode(), base64.b64encode(public).decode()


def _database(generations: list[tuple[datetime, str]], us_cycles: dict[str, str] | None = None) -> Database:
    """A generation's US cycles default to its own id (every generation changes the US inputs); ``us_cycles`` maps a
    generation id to the US cycle it serves, so two generations can share their US view (a B3-only republish)."""
    database = Database(Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))

    def selection_at(instant: datetime) -> dict[str, Any] | None:
        known = [(at, generation) for at, generation in generations if at <= instant]
        if not known:
            return None
        generation = max(known)[1]
        us = (us_cycles or {}).get(generation, generation)
        return {"generation_id": generation, "source": "official_blend_v1", "source_version": "v1",
                "cycles": {"NASDAQ": us, "NYSE": us, "B3": generation}, "targeted": {}}

    database.valuation_official_selection_at = selection_at  # type: ignore[method-assign]
    return database


def _record(*, run_id: str, generation: str, market: str, symbol: str, verdict: str, without: str, at: datetime = RUN,
            published: datetime | None = None, session: str = NIGHT) -> dict[str, Any]:
    row = {"generation_id": generation, "tp_source": "official_blend_v1", "official_cycle_id": str(uuid4()), "official_row_sha256": "c" * 64,
           "prediction_instant": at - timedelta(hours=1), "our_tp": 120.0, "buy_in": 100.0}
    codes = [decisor.ALL_GATES_PASSED] if verdict == decisor.COMPRA_PERMITIDA else ["PRICE_ABOVE_BUY_IN"]
    outcome = {"verdict": verdict, "reason_codes": codes, "price": 90.0, "e_profile": 0.1, "h_market": 0.04,
               "checks": {"counterfactual": {"verdict_without_events": without, "reason_codes_without_events": codes}, "events": {"marks": []}}}
    return decisor.decision_record(run_id=run_id, market=market, symbol=symbol, session_date=session, prediction_instant=at,
                                   published_at=published or at + timedelta(seconds=5), row=row, outcome=outcome, inputs={"night": session},
                                   thresholds_hash=decisor.thresholds_sha256())


def _night(database: Database, *, generation: str, at: datetime = RUN, published: datetime | None = None) -> str:
    run_id = str(uuid4())
    verdicts = {"AAP.L": (decisor.COMPRA_PERMITIDA, decisor.COMPRA_PERMITIDA), "K.O": (decisor.OBSERVAR, decisor.COMPRA_PERMITIDA),
                "MSF.T": (decisor.VETO, decisor.VETO), "XO.M": (decisor.COMPRA_PERMITIDA, decisor.COMPRA_PERMITIDA)}
    records = [_record(run_id=run_id, generation=generation, market="NYSE" if symbol in ("K.O", "XO.M") else "NASDAQ", symbol=symbol,
                       verdict=verdict, without=without, at=at, published=published) for symbol, (verdict, without) in verdicts.items()]
    # a B3 verdict of the same run: never exported (US only)
    records.append(_record(run_id=run_id, generation=generation, market="B3", symbol="PETR.4", verdict=decisor.COMPRA_PERMITIDA,
                           without=decisor.COMPRA_PERMITIDA, at=at, published=published))
    assert database.insert_valuation_decisions(records) == len(records)
    return run_id


def test_the_envelope_round_trips_and_carries_no_symbol_in_clear() -> None:
    private, public = _keys()
    generation = str(uuid4())
    database = _database([(RUN - timedelta(hours=2), generation)])
    run_id = _night(database, generation=generation)
    envelope = export.export(database, NIGHT, public, now=NOW)
    text = json.dumps(envelope)
    assert set(envelope) == export.ENVELOPE_KEYS and not any(symbol in text for symbol in (*SYMBOLS, "PETR.4"))
    assert envelope["night"] == NIGHT and envelope["decision_run_id"] == run_id and envelope["generation_id"] == generation
    assert envelope["recipient_public_key"] == public and envelope["thresholds_sha256"] == decisor.thresholds_sha256()
    assert envelope["counts"] == {"rows": 4, "by_market": {"NASDAQ": 2, "NYSE": 2},
                                  "by_verdict": {"COMPRA_PERMITIDA": 2, "OBSERVAR": 1, "VETO": 1},
                                  "by_verdict_without_events": {"COMPRA_PERMITIDA": 3, "OBSERVAR": 0, "VETO": 1}}
    document = export.decrypt(envelope, private)
    assert set(document) == export.PLAINTEXT_KEYS and document["night"] == NIGHT and document["decision_instant"] == RUN.isoformat()
    assert [(row["market"], row["symbol"], row["verdict"], row["verdict_without_events"]) for row in document["rows"]] == [
        ("NASDAQ", "AAP.L", "COMPRA_PERMITIDA", "COMPRA_PERMITIDA"), ("NASDAQ", "MSF.T", "VETO", "VETO"),
        ("NYSE", "K.O", "OBSERVAR", "COMPRA_PERMITIDA"), ("NYSE", "XO.M", "COMPRA_PERMITIDA", "COMPRA_PERMITIDA")]
    assert document["rows"][0]["reasons"] == [decisor.ALL_GATES_PASSED]
    assert official.canonical_sha256(document) == envelope["plaintext_sha256"]  # the canonical bytes are the ones hashed
    # the blinding: two exports of the same night never share a plaintext hash (a guessed list cannot be confirmed)
    assert export.export(database, NIGHT, public, now=NOW)["plaintext_sha256"] != envelope["plaintext_sha256"]


def test_the_clear_header_is_authenticated_and_only_the_lab_key_opens_it() -> None:
    private, public = _keys()
    other, _ = _keys()
    generation = str(uuid4())
    database = _database([(RUN - timedelta(hours=2), generation)])
    _night(database, generation=generation)
    envelope = export.export(database, NIGHT, public, now=NOW)
    tampered = json.loads(json.dumps(envelope))
    tampered["counts"]["by_verdict"] = {"COMPRA_PERMITIDA": 4, "OBSERVAR": 0, "VETO": 0}
    with pytest.raises(InvalidTag):
        export.decrypt(tampered, private)
    with pytest.raises(ValueError, match="another key"):
        export.decrypt(envelope, other)
    grown = {**envelope, "rows": []}
    with pytest.raises(ValueError, match="exactly"):
        export.check_envelope(grown)


def test_the_latest_run_published_before_the_next_open_answers_and_a_later_one_never_does() -> None:
    private, public = _keys()
    first, retry = str(uuid4()), str(uuid4())
    database = _database([(RUN - timedelta(hours=2), first), (RUN + timedelta(hours=20), retry)])
    _night(database, generation=first)
    # Sunday night: the decisor decided Friday's session again over the canonical retry
    sunday = datetime(2026, 10, 26, 3, 0, tzinfo=UTC)
    rerun = _night(database, generation=retry, at=sunday)
    # a run published after Monday's open is never Friday's night for an entry on Monday
    _night(database, generation=retry, at=NEXT_OPEN + timedelta(minutes=30))
    assert export.export(database, NIGHT, public, now=NOW)["decision_run_id"] == rerun
    assert export.decrypt(export.export(database, NIGHT, public, now=NOW + timedelta(days=2)), private)["decision_instant"] == sunday.isoformat()


@pytest.mark.parametrize("case", ["absent", "not_closed", "saturday", "invalid", "generation", "after_open", "unverified", "key"])
def test_an_absent_or_incomplete_night_is_refused_and_nothing_is_encrypted(case: str) -> None:
    _, public = _keys()
    generation, later = str(uuid4()), str(uuid4())
    database = _database([(RUN - timedelta(hours=2), generation)])
    night, now, key = NIGHT, NOW, public
    expected = {"absent": "NO_DECISIONS", "not_closed": "NIGHT_NOT_CLOSED", "saturday": "NOT_A_SESSION", "invalid": "NIGHT_INVALID",
                "generation": "GENERATION_NOT_DECIDED", "after_open": "DECISIONS_ONLY_AFTER_NEXT_OPEN", "unverified": "UNVERIFIED_DECISIONS",
                "key": "KEY_INVALID"}[case]
    if case != "absent":
        _night(database, generation=generation, at=NEXT_OPEN + timedelta(hours=1) if case == "after_open" else RUN)
    if case == "not_closed":
        now = datetime(2026, 10, 23, 18, 0, tzinfo=UTC)  # Friday 14:00 EDT: the session is still open
    elif case == "saturday":
        night = "2026-10-24"
    elif case == "invalid":
        night = "23/10/2026"
    elif case == "generation":  # a canonical retry activated a later generation that nobody decided again
        database = _database([(RUN - timedelta(hours=2), generation), (RUN + timedelta(hours=3), later)])
        _night(database, generation=generation)
    elif case == "after_open":
        now = NEXT_OPEN + timedelta(hours=2)
    elif case == "unverified":
        database._valuation_decisions[0]["verdict"] = decisor.COMPRA_PERMITIDA if database._valuation_decisions[0]["verdict"] != decisor.COMPRA_PERMITIDA else decisor.VETO
    elif case == "key":
        key = base64.b64encode(b"short").decode()
    with pytest.raises(export.ExportRefused) as refused:
        export.export(database, night, key, now=now)
    assert refused.value.code == expected
    assert not any(symbol in str(refused.value) for symbol in SYMBOLS)


def test_the_cli_prints_one_envelope_line_in_a_read_only_session(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    private, public = _keys()
    generation = str(uuid4())
    database = _database([(RUN - timedelta(hours=2), generation)])
    _night(database, generation=generation)
    monkeypatch.setattr("app.database.Database", lambda settings: database)
    monkeypatch.setattr(decisor, "get_settings", lambda: Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))
    monkeypatch.setenv("PGOPTIONS", "-c statement_timeout=0")
    real = export.night_verdicts
    monkeypatch.setattr(export, "night_verdicts", lambda db, night, now=None: real(db, night, now=NOW))
    assert decisor.main(["--export-verdicts", "--night", NIGHT, "--recipient-public-key", public]) == 0
    printed = capsys.readouterr().out
    assert printed.count("\n") == 1 and not any(symbol in printed for symbol in (*SYMBOLS, "PETR.4"))
    assert export.decrypt(json.loads(printed), private)["night"] == NIGHT
    assert os.environ["PGOPTIONS"] == "-c statement_timeout=0 " + export.READ_ONLY_PGOPTION
    # a refusal: one line, its code and the night, exit 3 — never the detail
    assert decisor.main(["--export-verdicts", "--night", "2026-10-22", "--recipient-public-key", public]) == decisor.EXPORT_REFUSED_EXIT
    assert json.loads(capsys.readouterr().out) == {"schema": export.REFUSAL_SCHEMA, "night": "2026-10-22", "refused": "NO_DECISIONS"}
    # last-completed resolves to the last closed NYSE session at the run's clock (Monday 08:00 BRT → Friday)
    assert decisor.main(["--export-verdicts", "--night", "last-completed", "--recipient-public-key", public]) == 0
    assert json.loads(capsys.readouterr().out)["night"] == NIGHT
    with pytest.raises(SystemExit):
        decisor.main(["--export-verdicts", "--night", NIGHT])
    with pytest.raises(SystemExit):
        decisor.main(["--dry-run", "--night", NIGHT])


def test_the_session_reader_counts_what_does_not_verify() -> None:
    generation = str(uuid4())
    database = _database([(RUN - timedelta(hours=2), generation)])
    _night(database, generation=generation)
    records, unverified = database.valuation_decisions_of_session(["NASDAQ", "NYSE"], NIGHT)
    assert sorted(record["symbol"] for record in records) == sorted(SYMBOLS) and unverified == 0
    assert database.valuation_decisions_of_session(["B3"], NIGHT)[0][0]["symbol"] == "PETR.4"
    assert database.valuation_decisions_of_session(["NASDAQ"], "2026-10-22") == ([], 0)
    database._valuation_decisions[0]["symbol"] = "ZZZZ"
    assert database.valuation_decisions_of_session(["NASDAQ", "NYSE"], NIGHT)[1] == 1


# ------------------------------------------------------------------ the public workflow


def _steps() -> dict[str, dict[str, Any]]:
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    return {step["name"]: step for job in jobs.values() for step in job.get("steps", []) if step.get("name")}


def _runner_script(step: dict[str, Any]) -> str:
    return str(step["run"]).split("<<'PY' || exit 1\n", 1)[1].split("\nPY\n", 1)[0]


def _verify(tmp_path: Path, text: str, *, public: str, requested: str = NIGHT) -> subprocess.CompletedProcess[str]:
    script = _runner_script(_steps()["Verify the envelope's exact schema and keep it only"])
    source, out = tmp_path / "stdout.json", tmp_path / "out"
    out.mkdir(exist_ok=True)
    source.write_text(text, encoding="utf-8")
    env = {**os.environ, "REQUESTED": requested, "PUBKEY": public, "RUN_ID": "7", "REVISION": "c" * 40,
           "GITHUB_OUTPUT": str(tmp_path / "output"), "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md")}
    return subprocess.run([sys.executable, "-", str(source), str(out)], input=script, text=True, capture_output=True, env=env)


def test_the_workflow_uploads_only_an_envelope_of_the_exact_schema(tmp_path: Path) -> None:
    private, public = _keys()
    _, other = _keys()
    generation = str(uuid4())
    database = _database([(RUN - timedelta(hours=2), generation)])
    _night(database, generation=generation)
    envelope = export.export(database, NIGHT, public, now=NOW)
    accepted = _verify(tmp_path, json.dumps(envelope) + "\n", public=public, requested="last-completed")
    assert accepted.returncode == 0, accepted.stderr
    written = {path.name: path.read_text(encoding="utf-8") for path in (tmp_path / "out").iterdir()}
    assert set(written) == {"envelope.json", "metadata.json"}
    assert not any(symbol in text for text in (*written.values(), accepted.stdout, (tmp_path / "summary.md").read_text()) for symbol in SYMBOLS)
    assert export.decrypt(json.loads(written["envelope.json"]), private)["night"] == NIGHT  # what is uploaded still opens
    metadata = json.loads(written["metadata.json"])
    assert metadata["night"] == NIGHT and metadata["counts"] == envelope["counts"] and metadata["plaintext_sha256"] == envelope["plaintext_sha256"]
    assert (tmp_path / "output").read_text() == f"night={NIGHT}\n"
    refused = {
        "keys are not exactly": {**envelope, "rows": [{"symbol": "AAP.L"}]},
        "keys are not exactly ": {key: value for key, value in envelope.items() if key != "nonce"},
        "not encrypted to C3PO_R2D2_LAB_VERDICT_PUBKEY": {**envelope, "recipient_public_key": other},
        "counts.by_verdict": {**envelope, "counts": {**envelope["counts"], "by_verdict": {"COMPRA_PERMITIDA": 9, "OBSERVAR": 0, "VETO": 0}}},
        "unexpected counts shape": {**envelope, "counts": {**envelope["counts"], "symbols": ["AAP.L"]}},
        "is not an identifier": {**envelope, "decisor_version": "AAP.L KO MSF.T"},
        "not base64": {**envelope, "nonce": "AAP.L"},
        "another night": envelope,
    }
    for message, candidate in refused.items():
        result = _verify(tmp_path, json.dumps(candidate), public=public, requested="2026-10-22" if message == "another night" else NIGHT)
        assert result.returncode != 0 and message.strip() in result.stderr, (message, result.stderr)
        assert not any(symbol in result.stderr + result.stdout for symbol in SYMBOLS)
    garbage = _verify(tmp_path, "AAP.L is permitted\n", public=public)
    assert garbage.returncode != 0 and "AAP.L" not in garbage.stderr


def test_the_workflow_reads_the_host_read_only_on_schedule_and_prints_a_refusal_code_only(tmp_path: Path) -> None:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = document[True] if True in document else document["on"]  # PyYAML reads the bare key `on` as True
    assert triggers["schedule"] == [{"cron": "0 11 * * 1-5"}] and "night" in triggers["workflow_dispatch"]["inputs"]
    assert document["permissions"] == {"contents": "read"}
    job = document["jobs"]["export"]
    assert job["environment"] == "production"
    steps = _steps()
    remote = steps["Export the encrypted verdicts in the running api container, read-only"]["run"]
    assert "-e 'PGOPTIONS=-c default_transaction_read_only=on'" in remote and "exec -T" in remote
    assert "--export-verdicts --night \"$NIGHT\" --recipient-public-key \"$PUBKEY\"" in remote
    assert "reboot.pending" in remote and "cat " not in remote and remote.count("stderr.log") == 2  # written, then only counted
    assert steps["Validate the night and the lab's public key"]["env"]["PUBKEY"] == "${{ vars.C3PO_R2D2_LAB_VERDICT_PUBKEY }}"
    upload = steps["Publish the encrypted envelope"]["with"]
    assert upload["name"] == "decisor-verdicts-${{ steps.verify.outputs.night }}" and upload["path"] == "${{ runner.temp }}/decisor-verdicts"
    # the refusal reader prints the code from a fixed list, never the remote output
    script = _runner_script({"run": remote})
    assert set(export.REFUSALS) == set(re.findall(r'"([A-Z_]+)"', script.split("CODES = ", 1)[1].split("}", 1)[0]))
    source = tmp_path / "refusal.json"
    source.write_text(json.dumps({"schema": export.REFUSAL_SCHEMA, "night": NIGHT, "refused": "NO_DECISIONS"}))
    result = subprocess.run([sys.executable, "-", str(source)], input=script, text=True, capture_output=True)
    assert result.returncode == 0 and "NO_DECISIONS" in result.stdout
    source.write_text(json.dumps({"schema": export.REFUSAL_SCHEMA, "night": NIGHT, "refused": "AAP.L"}))
    result = subprocess.run([sys.executable, "-", str(source)], input=script, text=True, capture_output=True)
    assert result.returncode != 0 and "AAP.L" not in result.stdout + result.stderr


def test_a_later_b3_only_generation_does_not_void_the_us_night() -> None:
    private, public = _keys()
    decided, b3_only = str(uuid4()), str(uuid4())
    database = _database([(RUN - timedelta(hours=2), decided), (RUN + timedelta(hours=3), b3_only)], us_cycles={b3_only: decided})
    _night(database, generation=decided)
    envelope = export.export(database, NIGHT, public, now=NOW)
    assert envelope["generation_id"] == decided and export.decrypt(envelope, private)["night"] == NIGHT
