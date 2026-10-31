"""The host driver of the ensemble grade: pinned files, the journal that makes an interrupted chunk lose nothing, the
operational guard and the aggregates-only output. Synthetic: the executor's own fixture (a double of the section), no
connection, no real input, no label."""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app import valuation_ensemble_driver as driver
from tests.test_valuation_ensemble_executor import NOW, fixture


def _legacy(tmp_path: Path, context: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str, str]:
    legacy = tmp_path / "legacy"
    (legacy / driver.ORDERS).mkdir(parents=True)
    (legacy / driver.PINS).mkdir(parents=True)
    order = json.dumps(context["order"], sort_keys=True).encode()
    order_sha = __import__("hashlib").sha256(order).hexdigest()
    (legacy / driver.ORDERS / f"{order_sha}.json").write_bytes(order)
    pin_sha = context["binding"].expected_pin_sha256
    (legacy / driver.PINS / f"{pin_sha}.json").write_text(json.dumps(context["pin"]), encoding="utf-8")
    monkeypatch.setattr(driver, "instrument_file_hashes", lambda root: dict(context["files"]))
    return legacy, order_sha, pin_sha


def _run(context: dict[str, Any], tmp_path: Path, legacy: Path, order_sha: str, pin_sha: str, max_runs: int) -> dict[str, Any]:
    return driver.run_chunk(context["database"], None, rev3=context["rev3"], order_sha256=order_sha, pin_sha256=pin_sha,
                            binding=context["binding"], max_runs=max_runs, stop_before=NOW + timedelta(minutes=30), legacy_root=legacy,
                            store_root=tmp_path / "store", clock=context["clock"], prices_for=context["prices"], guard=context["guard"])


def test_chunks_journal_every_section_and_resume_to_complete(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context = fixture(monkeypatch, tmp_path)
    legacy, order_sha, pin_sha = _legacy(tmp_path, context, monkeypatch)
    first = _run(context, tmp_path, legacy, order_sha, pin_sha, 2)
    assert (first["computed_this_chunk"], first["prior_entries"], first["journaled_this_chunk"], first["complete"], first["remaining"]) == (2, 0, 2, False, 2)
    assert "SYNTHETIC" not in json.dumps(first)  # aggregates only
    journal = tmp_path / "store" / f"journal-{order_sha}-{pin_sha}.jsonl"
    assert len(journal.read_text().splitlines()) == 2 and oct(journal.stat().st_mode & 0o777) == "0o600"
    for directory in ("store", "store/receipts", "store/manifests"):
        assert oct((tmp_path / directory).stat().st_mode & 0o777) == "0o700"
    second = _run(context, tmp_path, legacy, order_sha, pin_sha, 4)
    assert (second["computed_this_chunk"], second["prior_entries"], second["complete"], second["remaining"]) == (2, 2, True, 0)
    manifest = json.loads((tmp_path / "store" / "manifests" / f"{second['manifest_sha256']}.json").read_text())
    assert manifest["complete"] is True and len(manifest["entries"]) == 4
    assert manifest["entries"] == driver.read_journal(journal)  # the journal rebuilds exactly the executor's entries


def test_an_interrupted_chunk_loses_no_committed_section(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context = fixture(monkeypatch, tmp_path)
    legacy, order_sha, pin_sha = _legacy(tmp_path, context, monkeypatch)
    calls = {"n": 0}

    def fail_on_second(database: Any, **kw: Any) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise ValueError("ensemble_execution_window_ended")
    context["compute_hook"] = fail_on_second
    with pytest.raises(ValueError, match="window_ended"):
        _run(context, tmp_path, legacy, order_sha, pin_sha, 4)
    journal = tmp_path / "store" / f"journal-{order_sha}-{pin_sha}.jsonl"
    assert len(driver.read_journal(journal)) == 1
    context["compute_hook"] = None
    resumed = _run(context, tmp_path, legacy, order_sha, pin_sha, 4)
    assert (resumed["prior_entries"], resumed["computed_this_chunk"], resumed["complete"]) == (1, 3, True)


def test_a_torn_last_journal_line_is_cut_and_any_other_bad_line_refuses(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    good = json.dumps({"schema": driver.JOURNAL_SCHEMA, "entry": {"market": "NYSE", "session_date": "2021-06-01", "as_of": "x"}})
    fd = os.open(journal, os.O_WRONLY | os.O_CREAT, 0o600)
    os.write(fd, (good + "\n" + good[:20]).encode())
    os.close(fd)
    assert len(driver.read_journal(journal)) == 1
    assert journal.read_text() == good + "\n"  # the torn bytes are gone: the next append starts on its own line
    driver.append_journal(journal, {"market": "NASDAQ", "session_date": "2021-06-01", "as_of": "x"})
    assert len(driver.read_journal(journal)) == 2
    journal.write_text(good + "\nnot json\n" + good + "\n")
    with pytest.raises(ValueError):
        driver.read_journal(journal)
    journal.chmod(0o644)
    with pytest.raises(ValueError, match="journal_not_private"):
        driver.read_journal(journal)


def test_running_code_must_be_the_checkout_and_the_checkout_path_has_no_link(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    (app / "valuation_ensemble_x.py").write_bytes(b"a")
    (app / "valuation_pit_rerun.py").write_bytes(b"b")
    digest = {name: __import__("hashlib").sha256(data).hexdigest() for name, data in (("valuation_ensemble_x.py", b"a"), ("valuation_pit_rerun.py", b"b"))}
    checkout = {driver.APP_PREFIX + name: value for name, value in digest.items()}
    driver.running_files(checkout, app)
    (app / "valuation_pit_rerun.py").write_bytes(b"changed")
    with pytest.raises(ValueError, match="running_code_differs"):
        driver.running_files(checkout, app)
    (app / "valuation_pit_rerun.py").write_bytes(b"b")
    (app / "valuation_ensemble_extra.py").write_bytes(b"c")
    with pytest.raises(ValueError, match="running_modules_differ"):
        driver.running_files(checkout, app)
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "order.json").write_text("{}")
    (tmp_path / "root").mkdir()
    (tmp_path / "root" / "c3po").symlink_to(tmp_path / "real")
    with pytest.raises(ValueError, match="symlink"):
        driver.checkout_file(tmp_path / "root", Path("c3po/order.json"))


class _Database:
    database_url = ""

    def __init__(self) -> None:
        self._ingestion_runs: dict[str, dict[str, Any]] = {}
        self._data_sources: dict[str, dict[str, Any]] = {}


def test_the_guard_refuses_blocking_ingestions_and_never_waits_for_an_asfiled_poll() -> None:
    """PREREG rev 2 §2: the rev3 rule stays (the nightly worker or a long ingestion refuses); an as-filed poll in flight
    neither waits nor refuses, because each section reads the store cut at its V3 snapshot's published_at."""
    database = _Database()
    database._ingestion_runs["p"] = {"status": "running", "source_code": "sec_asfiled", "started_at": NOW - timedelta(minutes=1)}
    assert driver.operational_guard(database, clock=lambda: NOW, blocking=lambda db, now: 0)() is None
    assert driver.operational_guard(database, clock=lambda: NOW, blocking=driver.blocking_ingestions)() is None
    database._ingestion_runs["p"]["started_at"] = NOW - timedelta(minutes=31)  # a long ingestion is the rev3 rule's
    with pytest.raises(ValueError, match="blocking_ingestion"):
        driver.operational_guard(database, clock=lambda: NOW, blocking=driver.blocking_ingestions)()
    with pytest.raises(ValueError, match="blocking_ingestion"):
        driver.operational_guard(database, clock=lambda: NOW, blocking=lambda db, now: 1)()


def test_a_refusal_prints_a_code_never_free_text(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("PGOPTIONS", "")
    assert driver.refusal_code(ValueError("ensemble_owner_order_expired")) == "ensemble_owner_order_expired"
    assert driver.refusal_code(ValueError("pinned price vintage of NASDAQ AAPL")) == "exception:ValueError"
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"{}")))

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("TICKER leaked")
    monkeypatch.setattr(driver, "run_chunk", refuse)
    code = driver.main(["--owner-order-sha256", "a" * 64, "--pin-sha256", "b" * 64, "--instrument-commit", "c" * 40,
                        "--owner-signature-comment-id", "1", "--technical-go-comment-id", "2", "--max-runs", "3",
                        "--stop-before", (NOW + timedelta(hours=1)).isoformat()], database=object(), settings=object())
    out = capsys.readouterr()
    assert code == 2 and "TICKER" not in out.out and json.loads(out.out.splitlines()[-1])["reason"] == "exception:RuntimeError"


def test_the_price_reader_is_the_rev3_pin() -> None:
    assert driver.price_pin_of({"price_pin": {"requested_at": "2026-10-19T18:30:00-03:00"}}) == datetime(2026, 10, 19, 21, 30, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        driver.price_pin_of({"price_pin": {}})


def test_refusal_codes_keep_every_executor_token_and_paths_but_never_a_ticker() -> None:
    joined = "ensemble_instrument_mismatch:c3po/backend/app/valuation_ensemble_grid.py;ensemble_instrument_technical_GO_comment_id_mismatch"
    assert driver.refusal_code(ValueError(joined)) == joined.replace("technical_GO", "technical_go")
    assert driver.refusal_code(ValueError("ensemble_owner_order_expired;AAPL")) == "exception:ValueError"


def test_one_driver_at_a_time_on_the_store(tmp_path: Path) -> None:
    with driver.ChunkLock(tmp_path):
        with pytest.raises(ValueError, match="another_chunk_is_running"):
            with driver.ChunkLock(tmp_path):
                pass
    with driver.ChunkLock(tmp_path):  # released on exit
        pass


def test_the_pinned_blocking_rule_is_rev3s() -> None:
    database = _Database()
    database._data_sources = {"nightly": {"id": "s1", "source_type": "valuation_worker"}, "ir": {"id": "s2", "source_type": "regulatory_disclosure"}}
    database._ingestion_runs = {"short-ir": {"status": "running", "source_id": "s2", "started_at": NOW - timedelta(minutes=2)}}
    assert driver.blocking_ingestions(database, NOW) == 0
    database._ingestion_runs["nightly"] = {"status": "running", "source_id": "s1", "started_at": NOW - timedelta(minutes=1)}
    database._ingestion_runs["long"] = {"status": "running", "source_id": "s2", "started_at": NOW - timedelta(minutes=45)}
    database._ingestion_runs["stale"] = {"status": "running", "source_id": "s2", "started_at": NOW - timedelta(hours=13)}
    assert driver.blocking_ingestions(database, NOW) == 2


def test_the_chunk_reports_verification_and_compute_time_apart(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context = fixture(monkeypatch, tmp_path)
    legacy, order_sha, pin_sha = _legacy(tmp_path, context, monkeypatch)
    result = _run(context, tmp_path, legacy, order_sha, pin_sha, 2)
    assert {"prior_verify_seconds", "compute_seconds", "seconds_per_section"} <= set(result)
    assert result["elapsed_seconds"] >= result["compute_seconds"] >= 0
    done = _run(context, tmp_path, legacy, order_sha, pin_sha, 4)
    finished = _run(context, tmp_path, legacy, order_sha, pin_sha, 4)  # nothing left: verification only
    assert done["complete"] and finished["computed_this_chunk"] == 0 and finished["seconds_per_section"] is None and finished["compute_seconds"] == 0


class _Prices:
    """A pinned publication double: closes 100 at D, adjusted = close; labels by horizon."""

    def __init__(self, publication: str = "pub-1", closes: dict[int, float] | None = None) -> None:
        self.publication, self.closes = publication, closes or {1: 101.0, 5: 110.0, 6: 111.1}
        self.reads: list[tuple[str, int]] = []

    def vintage(self, market: str, *, available_before: datetime) -> dict[str, Any]:
        return {"status": "ok", "publication_id": self.publication, "bars_sha256": "b" * 64}

    def bars(self, market: str, symbol: str, *, available_before: datetime) -> dict[str, Any]:
        return {"2025-01-02": {"close": 100.0, "adjusted_close": 50.0}}

    def label_bar(self, market: str, symbol: str, session: Any, horizon: int, *, available_before: datetime) -> dict[str, Any]:
        self.reads.append((symbol, horizon))
        if horizon not in self.closes:
            return {"status": "not_yet_mature"}
        return {"status": "labelled", "adjusted_close": self.closes[horizon] / 2, "close": self.closes[horizon]}


def _rev3_pins() -> dict[str, Any]:
    pin = {"status": "ok", "publication_id": "pub-1", "bars_sha256": "b" * 64, "available_at": "2026-10-19T21:00:00+00:00"}
    return {"price_pin": {"requested_at": "2026-10-19T21:30:00+00:00", "NASDAQ": dict(pin), "NYSE": dict(pin)}}


def test_the_label_reader_is_rev3s_rule_on_the_pinned_publication() -> None:
    prices = _Prices()
    reader = driver.LabelReader(prices, _rev3_pins())
    row = {"market": "NYSE", "symbol": "X", "session_date": "2025-01-02", "price": 100.5}
    label = reader(row, 5)  # D -> D+5 on adjusted closes (50 -> 55), D+1 -> D+6 (50.5 -> 55.55)
    assert label["return"] == pytest.approx(0.10) and label["return_executable"] == pytest.approx(0.10) and label["reason"] is None
    immature = reader(row, 21)
    assert immature["return"] is None and immature["return_executable"] is None and immature["reason"] == "not_yet_mature"
    assert reader({**row, "price": 103.0}, 5) == {"return": None, "return_executable": None, "reason": "label_unavailable:basis_mismatch"}
    with pytest.raises(ValueError, match="label_vintage_not_the_pinned_one"):
        driver.LabelReader(_Prices(publication="pub-2"), _rev3_pins())


def test_the_reading_runs_the_full_report_from_the_private_store_and_publishes_codes_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context = fixture(monkeypatch, tmp_path)
    legacy, order_sha, pin_sha = _legacy(tmp_path, context, monkeypatch)
    done = _run(context, tmp_path, legacy, order_sha, pin_sha, 4)
    assert done["complete"]
    labels: list[Any] = []
    result = driver.run_report(context["database"], None, rev3=context["rev3"], pin_sha256=pin_sha, binding=context["binding"],
                               manifest_sha256=done["manifest_sha256"], legacy_root=legacy, store_root=tmp_path / "store",
                               label_reader=lambda row, h: labels.append(h) or {}, paired_sources_reader=lambda entry: ({}, {}))
    payload = result["payload"]
    # the executor's synthetic sections carry no models or variants: the reading is VOID, before any label
    assert payload["verdict"]["status"] == "VOID" and payload["labels_read"] == 0 and labels == []
    assert "SYNTHETIC" not in json.dumps(result)
    private = list((tmp_path / "store" / "reports").glob("*.json"))
    assert len(private) == 1 and oct(private[0].stat().st_mode & 0o777) == "0o600"
    assert json.loads(private[0].read_text())["payload_sha256"] == result["payload_sha256"]
    with pytest.raises(FileNotFoundError):
        driver.run_report(context["database"], None, rev3=context["rev3"], pin_sha256=pin_sha, binding=context["binding"], manifest_sha256="e" * 64,
                          legacy_root=legacy, store_root=tmp_path / "store", label_reader=lambda row, h: {}, paired_sources_reader=lambda entry: ({}, {}))


def test_the_public_reading_reduces_symbol_bearing_reasons() -> None:
    payload = {"verdict": {"status": "VOID", "reasons": ["ensemble_price_differs_from_rev3:AAA", "ensemble_manifest_not_complete"]}, "labels_read": 0}
    assert driver.public_payload(payload)["verdict"]["reasons"] == ["ensemble_manifest_not_complete", "ensemble_price_differs_from_rev3:redacted"]


def test_every_public_string_is_a_code_and_redaction_drops_the_private_digest() -> None:
    payload = {"schema": "VALUATION-ENSEMBLE-PIT-REPORT-v1", "protocol": {"precision": "median(abs(...)) D to D+h"},
               "verdict": {"status": "VOID", "look": "SINGLE", "reasons": ["ensemble_price_differs_from_rev3:BRK-B", "x:SEC"]},
               "model_non_evaluations": {"dcf_fcff:(34, 'Numerical result out of range')": 2, "dcf_fcff:missing_fact:capex_ttm": 1,
                                         "graham:(34, 'Numerical result out of range')": 1}, "at": "2026-10-27T13:00:00+00:00"}
    public = driver.public_payload(payload)
    assert public["protocol"] == payload["protocol"] and public["schema"] == payload["schema"] and public["at"] == payload["at"]
    assert public["verdict"] == {"status": "VOID", "look": "SINGLE", "reasons": ["ensemble_price_differs_from_rev3:redacted", "x:redacted"]}
    assert public["model_non_evaluations"] == {"dcf_fcff:redacted": 2, "dcf_fcff:missing_fact:capex_ttm": 1, "graham:redacted": 1}
    line = driver.reading_line({"payload": payload, "payload_sha256": "a" * 64, "manifest_sha256": "b" * 64}, pin_sha256="c" * 64, elapsed=1.0, repeated=False)
    assert line["payload_sha256"] is None and line["redacted"] is True and "BRK" not in json.dumps(line)


def test_the_single_look_is_kept_on_the_host(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir(mode=0o700)
    assert driver.earlier_reading(reports, "a" * 64) is None
    void = {"payload": {"verdict": {"status": "VOID"}}, "payload_sha256": "1" * 64, "manifest_sha256": "b" * 64}
    driver.write_manifest(reports, {**void, "reading_sha256": driver.canonical_hash(void)}, key="reading_sha256")
    assert driver.earlier_reading(reports, "a" * 64) is None  # a VOID reading read no label: nothing spent
    read = {"payload": {"verdict": {"status": "FAIL"}}, "payload_sha256": "2" * 64, "manifest_sha256": "a" * 64}
    driver.write_manifest(reports, {**read, "reading_sha256": driver.canonical_hash(read)}, key="reading_sha256")
    stored = driver.earlier_reading(reports, "a" * 64)  # the same manifest: the stored reading
    assert stored is not None and stored["payload_sha256"] == "2" * 64
    with pytest.raises(ValueError, match="single_look_spent_on_another_manifest"):
        driver.earlier_reading(reports, "c" * 64)


def test_a_blocking_ingestion_refuses_before_any_section_is_completed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context = fixture(monkeypatch, tmp_path)
    legacy, order_sha, pin_sha = _legacy(tmp_path, context, monkeypatch)
    ops = _Database()
    ops._ingestion_runs["poll"] = {"status": "running", "source_code": "sec_asfiled", "started_at": NOW - timedelta(minutes=1)}
    guard = driver.operational_guard(ops, clock=lambda: NOW, blocking=lambda db, now: 1)
    with pytest.raises(ValueError, match="blocking_ingestion"):
        driver.run_chunk(context["database"], None, rev3=context["rev3"], order_sha256=order_sha, pin_sha256=pin_sha, binding=context["binding"],
                         max_runs=4, stop_before=NOW + timedelta(minutes=30), legacy_root=legacy, store_root=tmp_path / "store",
                         clock=context["clock"], prices_for=context["prices"], guard=guard)
    journal = tmp_path / "store" / f"journal-{order_sha}-{pin_sha}.jsonl"
    assert driver.read_journal(journal) == [] and "compute" not in context["events"]
    headers = [path for path in (tmp_path / "store" / "receipts").glob("*.json") if json.loads(path.read_text()).get("schema") == driver.SECTION_SCHEMA]
    assert headers == []
