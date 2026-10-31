from __future__ import annotations

import io
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from app import sec_xbrl
from app import valuation_ensemble_readiness as readiness
from app.statement_vintages import StatementVintageStore
from app.valuation_ensemble_frozen import FrozenAsFiledReader, FrozenIndex, check_section_statements
from app.valuation_ensemble_grid import GridInputError
from app.valuation_ensemble_inputs import canonical_hash
from app.valuation_ensemble_pin import instrument_file_hashes
from tests.test_valuation_ensemble_grid import SYMBOLS, T, _block_network, _fixture  # noqa: F401

UTC = timezone.utc
REPOSITORY = Path(__file__).resolve().parents[3]
WORKFLOW = REPOSITORY / ".github/workflows/valuation-ensemble-readiness.yml"
SATURDAY = datetime(2026, 10, 31, 16, 0, tzinfo=UTC).timestamp()  # 13:00 Sao Paulo, 12:00 New York on a Saturday


def _executed() -> str:
    """The inventory digest of the executed revision: this repository's, as the runner computes it."""
    return canonical_hash(instrument_file_hashes(REPOSITORY))


def _section(monkeypatch, fixture):
    """The fixture's V3/served pair as the rev3 manifest lists it, its store written before the V3 sibling persisted."""
    database, prices, v3, served_snapshot = fixture
    cut = readiness.exe._written_at(v3)
    for row in database._statement_filings + database._statement_vintages:
        row["first_seen_at"] = min(row["first_seen_at"], cut - timedelta(days=1))
    entries = [{"market": "NASDAQ", "as_of": T.isoformat(), "session_date": prices.session_date, "cycle_id": snap["id"],
                "run_key": snap["inputs"]["run_key"]} for snap in (v3, served_snapshot)]
    monkeypatch.setattr(readiness.exe, "_reference_pairs", lambda rev3: [(entries[0], entries[1])])
    return cut


def _executor_path(fixture, cut):
    """What a chunk runs on the section: the check on the reader the executor hands it, or the refusal code."""
    database, _, v3, served_snapshot = fixture
    reader = FrozenAsFiledReader(database, written_until=cut, index=lambda: FrozenIndex.load(database))
    try:
        check_section_statements(database, market="NASDAQ", as_of=T, v3_snapshot=v3, served_snapshot=served_snapshot, reader=reader)
    except GridInputError as error:
        return str(error)
    return None


def _fact(database, *, accepted, written):
    original = next(row for row in database._statement_vintages if row["concept"] == "us-gaap:Revenues")
    StatementVintageStore(database).insert_vintages("US", original["issuer_key"], [dict(original, doc_id="later-comparative", value=1e9,
                                                                                         accepted_at=accepted)])
    for row in database._statement_vintages:
        if row["doc_id"] == "later-comparative":
            row["first_seen_at"] = written


def _filing(database, *, issuer, accepted, written):
    StatementVintageStore(database).register_filings([{"market": "US", "issuer_key": issuer, "source": sec_xbrl.FILING_SOURCE,
        "doc_id": f"{issuer}:extra", "form": "8-K", "filed_date": accepted.date(), "period_of_report": accepted.date(),
        "accepted_at": accepted, "accepted_source": "synthetic_sec_header", "symbols": [SYMBOLS[0]]}])
    for row in database._statement_filings:
        if row["doc_id"] == f"{issuer}:extra":
            row["first_seen_at"] = written


def _latest(database):
    return max(row["accepted_at"] for row in database._statement_filings if SYMBOLS[0] in (row.get("symbols") or ()))


SCENARIOS = {
    "reproduces": lambda db, cut: None,
    "fact_written_after_the_cut": lambda db, cut: _fact(db, accepted=T - timedelta(days=1), written=cut + timedelta(days=5)),
    "fact_written_before_the_cut": lambda db, cut: _fact(db, accepted=T - timedelta(days=1), written=cut - timedelta(minutes=1)),
    "tie_between_two_issuers": lambda db, cut: _filing(db, issuer="9999999999", accepted=_latest(db), written=cut - timedelta(hours=1)),
    "remap_to_an_uncovered_issuer": lambda db, cut: _filing(db, issuer="9999999999", accepted=_latest(db) + timedelta(days=1),
                                                            written=cut - timedelta(hours=1)),
    "remap_written_after_the_cut": lambda db, cut: _filing(db, issuer="9999999999", accepted=_latest(db) + timedelta(days=1),
                                                           written=cut + timedelta(hours=1)),
}
EXPECTED = {"reproduces": None, "fact_written_after_the_cut": None, "fact_written_before_the_cut": "statements_table_not_stable",
            "tie_between_two_issuers": "statements_table_not_stable", "remap_to_an_uncovered_issuer": "statements_table_not_stable",
            "remap_written_after_the_cut": None}


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_the_readiness_reaches_what_a_chunk_runs_on_every_section(monkeypatch, scenario) -> None:
    """rev 2 §6: the readiness is the executor's check (the reader cut at the V3 published_at, the names, the comparison)
    with each issuer's facts read once: the same verdict as the chunk's own path, scenario by scenario."""
    fixture = _fixture()
    cut = _section(monkeypatch, fixture)
    SCENARIOS[scenario](fixture[0], cut)
    expected = _executor_path(fixture, cut)
    assert expected == EXPECTED[scenario]
    result = readiness.run(fixture[0], {}, legacy_root=REPOSITORY, expected_instrument_sha256=_executed())
    assert result["sections"] == 1 and result["first_rev3_write"] == result["last_rev3_write"] == cut.isoformat()
    files = instrument_file_hashes(REPOSITORY)
    assert "c3po/backend/app/valuation_ensemble_readiness.py" in files and "c3po/backend/app/valuation_ensemble_frozen.py" in files
    assert ".github/workflows/valuation-ensemble-readiness.yml" in files  # Codex 6549349754: the new workflow is pinned
    assert result["instrument_files"] == len(files) and result["instrument_files_sha256"] == canonical_hash(files)
    if expected is None:
        assert result["stable_sections"] == 1 and result["refused"] == [] and result["first_refused"] is None
        assert result["names"] == result["names_compared"] == 6 and result["names_not_evaluable"] == 0 and result["issuers_read"] == 6
    else:
        label = "NASDAQ " + str(fixture[1].session_date)
        assert result["refused_sections"] == 1 and result["refused"] == [label] and result["first_refused"] == label
        assert result["refusal_reasons"] == {expected: 1}


def test_one_read_per_issuer_slices_what_the_stores_query_returns_at_each_t() -> None:
    """The I/O the readiness changes: a call at T returns the store's own rows for ``accepted_at <= T``, in its order."""
    database = _fixture()[0]
    store = StatementVintageStore(database)
    issuer = database._statement_vintages[0]["issuer_key"]
    sliced = readiness.OneIssuerStore(store)
    accepted = sorted({row["accepted_at"] for row in database._statement_vintages if row["issuer_key"] == issuer})
    for cut in [accepted[0] - timedelta(seconds=1), *accepted, accepted[-1] + timedelta(days=1), None]:
        assert sliced.vintages("US", issuer, accepted_at_or_before=cut, source=sec_xbrl.VINTAGE_SOURCE) == \
            store.vintages("US", issuer, accepted_at_or_before=cut, source=sec_xbrl.VINTAGE_SOURCE)
    assert sliced.reads == 1
    with pytest.raises(ValueError, match="readiness_store_call_unexpected"):
        sliced.vintages("US", issuer, concepts=["us-gaap:Revenues"])


def test_a_section_whose_snapshot_cannot_be_read_is_refused_and_the_others_go_on(monkeypatch) -> None:
    fixture = _fixture()
    _section(monkeypatch, fixture)
    good = readiness.exe._reference_pairs({})[0]
    missing = (dict(good[0], cycle_id="00000000-0000-0000-0000-00000000dead", session_date="2026-06-29"), good[1])
    monkeypatch.setattr(readiness.exe, "_reference_pairs", lambda rev3: [missing, good])
    result = readiness.run(fixture[0], {}, legacy_root=REPOSITORY, expected_instrument_sha256=_executed())
    assert result["sections"] == 2 and result["stable_sections"] == 1 and result["refused"] == ["NASDAQ 2026-06-29"]
    assert result["refusal_reasons"] == {"ensemble_reference_snapshot_missing_or_replaced": 1}


def _main(deadline, **kwargs):
    return readiness.main(["--deadline-at", str(int(deadline)), "--expect-instrument-sha256", kwargs.pop("expected", "a" * 64)],
                          clock=kwargs.pop("clock", lambda: SATURDAY),
                          on_expiry=kwargs.pop("on_expiry", lambda: None), **kwargs)


def test_the_process_checks_its_start_against_the_windows_and_the_original_deadline(monkeypatch, capsys) -> None:
    monday_0905 = datetime(2026, 11, 2, 14, 5, tzinfo=UTC).timestamp()  # 09:05 New York
    assert _main(monday_0905 + 3600, database=object(), clock=lambda: monday_0905) == 27
    assert json.loads(capsys.readouterr().out) == {"kind": "refused", "reason": "inside_a_window"}
    assert _main(SATURDAY + 599, database=object()) == 25
    assert json.loads(capsys.readouterr().out) == {"kind": "refused", "reason": "deadline_too_close"}
    armed = []
    monkeypatch.setattr(readiness, "arm_deadline", lambda seconds, on_expiry: armed.append(seconds))
    handed: list[str] = []

    def stable(database, rev3, *, expected_instrument_sha256):
        handed.append(expected_instrument_sha256)
        return {"sections": 2, "stable_sections": 2}
    monkeypatch.setattr(readiness, "run", stable)
    monkeypatch.setattr(readiness.sys, "stdin", type("Stdin", (), {"buffer": io.BytesIO(b"{}")})())
    monkeypatch.setattr("app.valuation_accuracy_report.force_read_only_session", lambda: None)
    assert _main(SATURDAY + 1200, database=object(), expected="b" * 64) == 0 and armed == [1200] and handed == ["b" * 64]
    assert json.loads(capsys.readouterr().out) == {"kind": "readiness", "sections": 2, "stable_sections": 2}
    monkeypatch.setattr(readiness, "run", lambda database, rev3, **kw: {"sections": 2, "stable_sections": 1})  # the gate fails visibly
    monkeypatch.setattr(readiness.sys, "stdin", type("Stdin", (), {"buffer": io.BytesIO(b"{}")})())
    assert _main(SATURDAY + 1200, database=object()) == 3
    assert json.loads(capsys.readouterr().out) == {"kind": "readiness", "sections": 2, "stable_sections": 1}

    def leaky(database, rev3, **kwargs):
        raise ValueError("issuer 0000320193 has no AAPL facts")  # a message that is no code: only the type is printed
    monkeypatch.setattr(readiness, "run", leaky)
    monkeypatch.setattr(readiness.sys, "stdin", type("Stdin", (), {"buffer": io.BytesIO(b"{}")})())
    assert _main(SATURDAY + 1200, database=object()) == 2
    assert json.loads(capsys.readouterr().out) == {"kind": "refused", "reason": "ValueError"}


def _workflow_filter() -> str:
    """The printing filter of the readiness workflow (the python between its <<'PY' and PY)."""
    workflow = yaml.safe_load(WORKFLOW.read_text())
    script = next(step["run"] for step in workflow["jobs"]["readiness"]["steps"] if step.get("name") == "Run the readiness on the host (read-only)")
    return script.split("<<'PY' || filtered=$?\n", 1)[1].split("\nPY\n", 1)[0]


def test_the_workflow_prints_the_modules_own_line_whole_and_nothing_of_another_shape(monkeypatch, tmp_path) -> None:
    fixture = _fixture()
    cut = _section(monkeypatch, fixture)
    SCENARIOS["fact_written_before_the_cut"](fixture[0], cut)
    line = {"kind": "readiness", **readiness.run(fixture[0], {}, legacy_root=REPOSITORY, expected_instrument_sha256=_executed())}
    assert line["refused_sections"] == 1
    script = tmp_path / "filter.py"
    script.write_text(_workflow_filter())
    stdout = tmp_path / "stdout.txt"
    stdout.write_text("LAUNCHED 1-1\n" + json.dumps(line, sort_keys=True) + "\n")
    printed = subprocess.run([sys.executable, "-I", str(script), str(stdout)], capture_output=True, text=True, check=True).stdout
    assert json.loads(printed.split("\nresult lines:")[0]) == json.loads(json.dumps(line))
    for leaked in (dict(line, refused=["AAPL 2026-06-29"]), dict(line, issuer="0000320193"), dict(line, names="6")):
        stdout.write_text(json.dumps(leaked) + "\n")
        run = subprocess.run([sys.executable, "-I", str(script), str(stdout)], capture_output=True, text=True)
        assert "AAPL" not in run.stdout and "0000320193" not in run.stdout and run.returncode != 0


def test_the_workflow_is_the_preflights_plumbing_with_the_readiness_module_and_no_backfill_guard() -> None:
    text = WORKFLOW.read_text()
    jobs = yaml.safe_load(text)["jobs"]
    assert list(jobs) == ["readiness"] and jobs["readiness"]["environment"] == "production"
    assert "workflow_dispatch:" in text and not any(fragment in text for fragment in ("schedule:", "push:", "DATABASE_URL"))
    assert "group: valuation-pit-backtest" in text and "contents: read" in text
    for fragment in ("default_transaction_read_only=on", "-m app.valuation_ensemble_readiness --deadline-at", "timeout -s TERM -k 120",
                     "valuation_pit_run_token=$RUN_TOKEN", "-m app[.]valuation_ensemble_readiness", "exit 27", "exit 25",
                     "sha256sum -c --strict --quiet SHA256SUMS", "73a81bcef1cd93425dfab785ae57c52118ba09493a4b7169e31a0e0b6665f805"):
        assert fragment in text, fragment
    assert "BACKFILL_ISSUERS_PER_POLL" not in text and "investor-relations-worker" not in text and "valuation_grid_preflight" not in text
    assert '[ "$REF" = refs/heads/main ]' in text and '[ ! -L "$file" ]' in text and '[ "$rc" = 0 ] || exit "$rc"' in text
    for fragment in ("ref: ${{ github.workflow_sha }}", '[ "$WORKFLOW_SHA" = "$RUN_SHA" ]', "INSTRUMENT_SHA256='$INSTRUMENT_SHA256' bash -s",
                     '--expect-instrument-sha256 "$INSTRUMENT_SHA256"', '"$INSTRUMENT_SHA256" =~ ^[0-9a-f]{64}$'):
        assert fragment in text, fragment


def test_the_readiness_refuses_to_read_when_the_running_modules_are_not_the_checkouts(monkeypatch, tmp_path) -> None:
    """The digest the pin cites is the checkout's; a process whose modules differ from it reads nothing."""
    import shutil

    fixture = _fixture()
    _section(monkeypatch, fixture)
    shutil.copytree(REPOSITORY / "c3po/backend/app", tmp_path / "c3po/backend/app")
    (tmp_path / ".github/workflows").mkdir(parents=True)
    for workflow in ("valuation-ensemble-grid.yml", "valuation-ensemble-readiness.yml"):
        shutil.copy(REPOSITORY / ".github/workflows" / workflow, tmp_path / ".github/workflows" / workflow)
    assert readiness.run(fixture[0], {}, legacy_root=tmp_path, expected_instrument_sha256=_executed())["stable_sections"] == 1
    frozen = tmp_path / "c3po/backend/app/valuation_ensemble_frozen.py"
    frozen.write_text(frozen.read_text() + "\n# another revision\n")
    with pytest.raises(ValueError, match="ensemble_driver_running_code_differs_from_checkout"):
        readiness.run(fixture[0], {}, legacy_root=tmp_path, expected_instrument_sha256=_executed())


def test_the_readiness_windows_are_the_grids() -> None:
    def at(y, mo, d, h, mi, zone):
        return datetime(y, mo, d, h, mi, tzinfo=zone)
    ny, sp = readiness.NEW_YORK, readiness.SAO_PAULO
    assert readiness.inside_a_window(at(2026, 11, 2, 9, 0, ny)) and not readiness.inside_a_window(at(2026, 11, 2, 8, 59, ny))
    assert readiness.inside_a_window(at(2026, 11, 2, 16, 29, ny)) and not readiness.inside_a_window(at(2026, 11, 2, 16, 30, ny))
    assert not readiness.inside_a_window(at(2026, 10, 31, 10, 0, ny))  # a Saturday morning in New York
    assert readiness.inside_a_window(at(2026, 10, 31, 23, 30, sp)) and readiness.inside_a_window(at(2026, 11, 1, 8, 14, sp))
    assert not readiness.inside_a_window(at(2026, 11, 1, 8, 15, sp)) and not readiness.inside_a_window(at(2026, 10, 31, 23, 29, sp))


@pytest.mark.parametrize("stdout", ["closed", "full"])
def test_the_readiness_ends_at_its_deadline_whatever_its_stdout_does(stdout) -> None:
    """A closed stdout (the line's write fails) or a full one (it blocks): the process ends with 124 either way."""
    import fcntl
    import os
    import time

    read_end, write_end = os.pipe()
    if stdout == "closed":
        os.close(read_end)
    else:
        flags = fcntl.fcntl(write_end, fcntl.F_GETFL)
        fcntl.fcntl(write_end, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        try:
            while True:
                os.write(write_end, b"x" * 4096)
        except BlockingIOError:
            pass
        fcntl.fcntl(write_end, fcntl.F_SETFL, flags)
    backend = Path(__file__).resolve().parents[1]
    code = "import time; from app import valuation_ensemble_readiness as r; r.arm_deadline(0.05, r._end_at_the_deadline); time.sleep(30)"
    started = time.monotonic()
    child = subprocess.Popen([sys.executable, "-c", code], cwd=backend, stdout=write_end, stderr=subprocess.DEVNULL)
    os.close(write_end)
    try:
        assert child.wait(timeout=20) == 124 and time.monotonic() - started < 20
    finally:
        if child.poll() is None:
            child.kill()
        if stdout == "full":
            os.close(read_end)


def test_the_readiness_runs_nothing_of_the_unpinned_preflight() -> None:
    """Everything that decides the check, the window and the deadline is in the pinned files (the digest it prints)."""
    source = (REPOSITORY / "c3po/backend/app/valuation_ensemble_readiness.py").read_text()
    assert "valuation_grid_preflight" not in source
    assert "c3po/backend/app/valuation_ensemble_readiness.py" in instrument_file_hashes(REPOSITORY)


class _Untouchable:
    """A database that fails on any use: nothing may be read before the identity checks pass."""

    def __getattr__(self, name):
        raise AssertionError(f"the database was read ({name}) before the identity checks")


def test_a_deployed_checkout_other_than_the_executed_revision_is_refused_before_any_read(tmp_path) -> None:
    """Codex 6549808485: the workflow GitHub executes (revision A) and the deployed checkout the host reads (B) must be
    one set of bytes. B differs from A only in the readiness workflow's timeout: the modules agree, and the run is still
    refused, before the database is touched."""
    import shutil

    shutil.copytree(REPOSITORY / "c3po/backend/app", tmp_path / "c3po/backend/app")
    (tmp_path / ".github/workflows").mkdir(parents=True)
    for workflow in ("valuation-ensemble-grid.yml", "valuation-ensemble-readiness.yml"):
        shutil.copy(REPOSITORY / ".github/workflows" / workflow, tmp_path / ".github/workflows" / workflow)
    copy = tmp_path / ".github/workflows/valuation-ensemble-readiness.yml"
    assert "timeout-minutes: 200" in copy.read_text()
    copy.write_text(copy.read_text().replace("timeout-minutes: 200", "timeout-minutes: 201"))
    with pytest.raises(ValueError, match="readiness_instrument_differs_from_the_executed_revision"):
        readiness.run(_Untouchable(), {}, legacy_root=tmp_path, expected_instrument_sha256=_executed())
    with pytest.raises(ValueError, match="readiness_instrument_differs_from_the_executed_revision"):
        readiness.run(_Untouchable(), {}, legacy_root=REPOSITORY, expected_instrument_sha256="0" * 64)


def test_the_command_requires_the_executed_revisions_digest(capsys) -> None:
    with pytest.raises(SystemExit):
        readiness.main(["--deadline-at", str(int(SATURDAY + 1200))], clock=lambda: SATURDAY, on_expiry=lambda: None)
    with pytest.raises(SystemExit):
        readiness.main(["--deadline-at", str(int(SATURDAY + 1200)), "--expect-instrument-sha256", "not-a-digest"],
                       clock=lambda: SATURDAY, on_expiry=lambda: None)


def test_the_runner_computes_the_executed_revisions_digest_with_the_pinned_functions_alone(tmp_path) -> None:
    """The inventory step's own script, on the standard library alone (-S), from this checkout: the digest the host
    must equal."""
    workflow = yaml.safe_load(WORKFLOW.read_text())
    step = next(step for step in workflow["jobs"]["readiness"]["steps"] if step.get("name") == "Inventory the executed revision")
    assert step["working-directory"] == "c3po/backend" and "${{ github.workflow_sha }}" in json.dumps(workflow["jobs"]["readiness"]["steps"])
    script = step["run"].split("<<'PY' >> \"$GITHUB_OUTPUT\" || exit 1\n", 1)[1].split("\nPY\n", 1)[0]
    (tmp_path / "inventory.py").write_text(script)
    run = subprocess.run([sys.executable, "-S", str(tmp_path / "inventory.py"), str(REPOSITORY)], cwd=REPOSITORY / "c3po/backend",
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-400:]
    assert run.stdout.strip() == f"instrument_sha256={_executed()}"
