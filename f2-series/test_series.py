"""Synthetic F2 tests: no network, host, real crypto, token or signature. stdlib unittest only.

A synthetic installation (source root + campaign root under a private temp directory, real family
bytes, fake age, empty ledger) is measured with a fixture probe; documents are built from that
measurement exactly as bind_series.py does.
"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import series_runtime as s
import series_analyze as a
import install_series as ins
import bind_series as b

FAKE_AGE = b"#!/bin/sh\nexit 0\n"
SYMBOLS = ["S%04d" % i for i in range(4200)]          # required minimum = ceil(0.95*4200) = 3990
AMENDMENT_DOC = "7" * 64
OWNER_AT = "2026-10-08T23:00:00Z"
PUBLISHED_AT = "2026-10-08T22:58:00Z"


def utc(text):
    return s.stamp(text)


class Clock:
    def __init__(self, at):
        self.now = utc(at) if isinstance(at, str) else at

    def __call__(self):
        return self.now


class Mono:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeProbe:
    def __init__(self):
        self.vals = {"platform": "linux", "euid": os.geteuid(), "boot": b"boot-fixture-1\n", "version": "3.12.3",
                     "exe": ("/usr/bin/python3.12", b"python-fixture")}

    def platform(self):
        return self.vals["platform"]

    def euid(self):
        return self.vals["euid"]

    def boot_id(self):
        return self.vals["boot"]

    def python_version(self):
        return self.vals["version"]

    def executable(self):
        return self.vals["exe"]


def eligible_raw():
    return s.canonical({"schema": "F2_ELIGIBLE_SET_V1", "types": ["COMMON_STOCK", "COMMON_STOCK_ADR"],
                        "readiness_rule": s.RULE, "provenance": {"origin": "SYNTHETIC_FIXTURE"}, "symbols": SYMBOLS})


def amendment_original(**over):
    value = {"schema": "DUDU_AMENDMENT_SIGNATURE_V1", "amendment": "A2_EMENDA_07", "revision": 1,
             "document_file": "A2_EMENDA_07_rev1.md", "document_sha256": AMENDMENT_DOC,
             "answer": "Assino a emenda 7 da A2", "signed_at_utc": "2026-10-08T21:00:00Z",
             "channel": "Claude Code (Fable), AskUserQuestion"}
    value.update(over)
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")   # original, NOT canonical


def build(measured, *, owner_at=OWNER_AT, published_at=PUBLISHED_AT, original=None, config_sig=None,
          validate=True, owner_over=None):
    runtime, election = s.canonical(measured["runtime"]), s.canonical(measured["election"])
    src = Path(s.SOURCE_ROOT) / s.FAMILY_DIR
    source, seal = (src / "series_runtime.py").read_bytes(), (src / "SHA256SUMS").read_bytes()
    elig = (Path(s.SOURCE_ROOT) / "ELIGIBLE_SET.json").read_bytes()
    original = original if original is not None else amendment_original()
    config = s.canonical({"schema": "F2_LEAF_CONFIG_V1", "amendment7_sha256": AMENDMENT_DOC,
                          "amendment7_signature_sha256": config_sig or s.sha(original)})
    signature = s.canonical(s.amendment_wrapper(original))
    review = s.canonical({"schema": "F2_CODEX_REVIEW_V2", "verdict": "ACCEPTED_OWN_BYTES_LINUX_AND_RUNTIME",
                          "source_sha256": s.sha(source), "seal_sha256": s.sha(seal), "reference_sha256": s.REFERENCE,
                          "eligible_set_sha256": s.sha(elig), "runtime_sha256": s.sha(runtime),
                          "election_sha256": s.sha(election), "amendment7_signature_sha256": s.sha(original),
                          "linux_result_sha256": "1" * 64, "review_record_sha256": "2" * 64})
    if validate:
        request = b.request_from_inputs(config, review, runtime, election, signature, elig, source, seal)
    else:
        request = s.canonical(b.request_value(config, review, runtime, election, elig, source, seal))
    owner = {"schema": "F2_OWNER_SIGNATURE_V1", "request_sha256": s.sha(request),
             "question_sha256": s.sha(s.owner_question(request)), "answer": "Assino",
             "question_published_at_utc": published_at, "recorded_at_utc": owner_at, "channel": "REGISTRO_PELA_FABLE"}
    owner.update(owner_over or {})
    return {"request": request, "owner": s.canonical(owner), "amendment_signature": signature, "election": election,
            "runtime": runtime, "review": review}


def bulk(present, day=s.BULK_DAY, extra=0):
    rows = [{"code": sym, "date": day, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}
            for sym in SYMBOLS[:present]]
    rows += [{"code": "X%04d" % i, "date": day, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1} for i in range(extra)]
    return json.dumps(rows).encode()


class FakeProvider:
    instances = []

    def __init__(self, token, monotonic, clock, body=None, advance=1.0, wall_advance=1.0, status=200):
        self.token, self.monotonic, self.clock = token, monotonic, clock
        self.calls, self.body, self.advance, self.wall_advance, self.status = 0, body, advance, wall_advance, status
        FakeProvider.instances.append(self)

    def fetch(self, deadline):
        s.need(self.calls == 0, "PROVIDER_CALL_LIMIT_EXCEEDED")
        self.calls += 1
        begun = self.clock()
        self.monotonic.t += self.advance
        self.clock.now = self.clock.now + timedelta(seconds=self.wall_advance)
        raw = self.body
        return raw, {"path": s.BULK_PATH, "bulk_date": s.BULK_DAY, "started_at": s.iso(begun),
                     "received_at": s.iso(self.clock()), "http_status": self.status, "content_type": "application/json",
                     "body_sha256": s.sha(raw), "body_bytes": len(raw), "body_complete": True,
                     "code": None if self.status == 200 else "PROVIDER_HTTP_NOT_OK"}


def fake_cipher(_age_fd, out_fd, payload, seconds):
    s.need(seconds > 0, "CIPHER_DEADLINE")
    os.write(out_fd, b"age-encryption.org/v1\n" + s.sha(payload).encode())


def rewrite(path, raw):
    os.chmod(path, 0o600)
    with open(path, "r+b") as handle:      # same inode, new bytes
        handle.truncate(0)
        handle.write(raw)
    os.chmod(path, 0o400)


def install_synthetic(src, camp, age=FAKE_AGE):
    """What `prepare` lays out, without the staging/seal checks (those are tested in Install)."""
    os.mkdir(src, 0o700)
    os.mkdir(src / s.FAMILY_DIR, 0o700)
    for name in ("series_runtime.py", "SHA256SUMS", "reference_extract.py"):
        shutil.copyfile(HERE / name, src / s.FAMILY_DIR / name)
        os.chmod(src / s.FAMILY_DIR / name, 0o400)
    (src / "ELIGIBLE_SET.json").write_bytes(eligible_raw())
    os.chmod(src / "ELIGIBLE_SET.json", 0o400)
    os.mkdir(camp, 0o700)
    (camp / "age").write_bytes(age)
    os.chmod(camp / "age", 0o500)
    (camp / s.LEDGER_NAME).write_bytes(b"")
    os.chmod(camp / s.LEDGER_NAME, 0o600)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="f2t-", dir=str(Path.home()))
        os.chmod(self.tmp.name, 0o700)
        self.base = Path(self.tmp.name)
        self.src, self.root = self.base / "src", self.base / "campaign"
        self.patches = [patch.object(s, "AGE_SHA256", s.sha(FAKE_AGE)),
                        patch.object(s, "SOURCE_ROOT", str(self.src)), patch.object(s, "CAMPAIGN_ROOT", str(self.root)),
                        patch.object(s, "ELIGIBLE_SET_PIN", s.sha(eligible_raw())),
                        patch.object(s, "ELIGIBLE_COUNT", len(SYMBOLS))]
        for p in self.patches:
            p.start()
        self.probe = FakeProbe()
        self.setup_install()
        FakeProvider.instances = []

    def setup_install(self):
        install_synthetic(self.src, self.root)
        self.measured = s.measure(self.probe, utc("2026-10-08T22:30:00Z"))
        self.raws = build(self.measured)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        for path in self.base.rglob("*"):
            if path.is_dir() and not path.is_symlink():
                os.chmod(path, 0o700)
        self.tmp.cleanup()

    def go(self, slot, at, present=4200, advance=1.0, wall_advance=1.0, raws=None, status=200, mono=None,
           hook=None, cipher=fake_cipher, clock=None):
        clock, mono = clock or Clock(at), mono or Mono()
        factory = lambda token, monotonic, clock: FakeProvider(token, monotonic, clock, body=bulk(present),
                                                               advance=advance, wall_advance=wall_advance, status=status)
        return s.run(raws or self.raws, slot, lambda: "fixture-token", clock=clock, monotonic=mono,
                     cipher=cipher, provider_factory=factory, physical=False, probe=self.probe,
                     between_claim_and_get=hook)

    def entries(self):
        return sorted(p.name for p in self.root.iterdir())

    def calls(self):
        return sum(p.calls for p in FakeProvider.instances)


class ClockGuards(Base):
    def test_on_time_start_observes(self):
        r = self.go("2126", "2026-10-09T00:26:00.400Z")
        self.assertEqual((r["status"], r["pre_get_recheck"]), ("SLOT_OBSERVED_PASS", "PASS"))
        self.assertEqual(r["logical_fetch_calls"], 1)
        self.assertTrue((self.root / "2126" / s.RECEIPT_NAME).exists())
        self.assertTrue((self.root / "2126" / s.CIPHER_NAME).exists())

    def test_late_start_refused_without_effect(self):
        with self.assertRaises(s.Refusal) as e:
            self.go("2126", "2026-10-09T00:27:00.001Z")
        self.assertEqual(str(e.exception), "START_LATE_FOR_SLOT")
        self.assertEqual(self.entries(), ["age", s.LEDGER_NAME])
        self.assertEqual(FakeProvider.instances, [])

    def test_early_start_refused(self):
        with self.assertRaises(s.Refusal) as e:
            self.go("2156", "2026-10-09T00:55:57Z")
        self.assertEqual(str(e.exception), "START_BEFORE_SLOT")
        self.assertEqual(self.entries(), ["age", s.LEDGER_NAME])

    def test_unknown_slot_refused(self):
        with self.assertRaises(s.Refusal) as e:
            self.go("2127", "2026-10-09T00:27:00Z")
        self.assertEqual(str(e.exception), "SLOT_UNKNOWN")

    def test_refusal_at_or_after_0058_brt(self):
        with self.assertRaises(s.Refusal) as e:
            self.go("0056", "2026-10-09T03:58:00Z")
        self.assertEqual(str(e.exception), "START_AFTER_CUTOFF_0058_BRT")
        with patch.object(s, "LATE_SECONDS", 600):
            with self.assertRaises(s.Refusal) as e:
                s.clock_guard("0026", utc("2026-10-09T03:58:30Z"))
        self.assertEqual(str(e.exception), "START_AFTER_CUTOFF_0058_BRT")
        self.assertEqual(self.entries(), ["age", s.LEDGER_NAME])

    def test_last_slot_inside_window_ok(self):
        r = self.go("0056", "2026-10-09T03:56:30Z")
        self.assertEqual(r["status"], "SLOT_OBSERVED_PASS")

    def test_receipt_after_0100_brt_is_hold(self):
        r = self.go("0056", "2026-10-09T03:56:59Z", wall_advance=190)
        self.assertEqual((r["status"], r["code"]), ("SLOT_HOLD", "RECEIVED_AFTER_0100_BRT"))
        self.assertTrue(r["slot_consumed"])
        self.assertIsNone(r["pass"])


# ---------------------------------------------------------------- B3: pins (before claim / between claim and GET)
def mutate_euid(t):
    t.probe.vals["euid"] = os.geteuid() + 1


def mutate_boot(t):
    t.probe.vals["boot"] = b"boot-fixture-2\n"


def mutate_python_version(t):
    t.probe.vals["version"] = "3.12.4"


def mutate_python_bytes(t):
    t.probe.vals["exe"] = ("/usr/bin/python3.12", b"python-other")


def mutate_python_path(t):
    t.probe.vals["exe"] = ("/usr/local/bin/python3.12", b"python-fixture")


def mutate_file(name):
    def change(t):
        path = (t.src / s.FAMILY_DIR / name) if name != "ELIGIBLE_SET.json" else (t.src / name)
        rewrite(path, path.read_bytes() + b"\n")
    return change


def mutate_age_bytes(t):
    os.chmod(t.root / "age", 0o700)
    with open(t.root / "age", "r+b") as handle:
        handle.write(b"#!/bin/sh\nexit 1\n")       # same size and inode, different bytes
    os.chmod(t.root / "age", 0o500)


def mutate_ancestor_mode(t):
    os.chmod(t.src, 0o750)


def mutate_family_dir_replaced(t):
    os.rename(t.src / s.FAMILY_DIR, t.src / "old-family")
    os.mkdir(t.src / s.FAMILY_DIR, 0o700)
    for name in ("series_runtime.py", "SHA256SUMS", "reference_extract.py"):
        shutil.copyfile(t.src / "old-family" / name, t.src / s.FAMILY_DIR / name)


def mutate_root_replaced(t):
    os.rename(t.root, t.base / "campaign-old")
    os.mkdir(t.root, 0o700)
    shutil.copyfile(t.base / "campaign-old" / "age", t.root / "age")
    os.chmod(t.root / "age", 0o500)
    (t.root / s.LEDGER_NAME).write_bytes(b"")


def mutate_ledger_absent(t):
    os.rename(t.root / s.LEDGER_NAME, t.base / "ledger-away")


def mutate_ledger_recreated(t):
    os.rename(t.root / s.LEDGER_NAME, t.base / "ledger-old")     # old inode kept alive: new one differs
    (t.root / s.LEDGER_NAME).write_bytes(b"")
    os.chmod(t.root / s.LEDGER_NAME, 0o600)


MUTATIONS = {"euid": mutate_euid, "boot": mutate_boot, "python_version": mutate_python_version,
             "python_bytes": mutate_python_bytes, "python_path": mutate_python_path,
             "source": mutate_file("series_runtime.py"), "seal": mutate_file("SHA256SUMS"),
             "reference": mutate_file("reference_extract.py"), "eligible": mutate_file("ELIGIBLE_SET.json"),
             "age": mutate_age_bytes, "ancestor_mode": mutate_ancestor_mode,
             "family_dir_replaced": mutate_family_dir_replaced, "root_replaced": mutate_root_replaced,
             "ledger_absent": mutate_ledger_absent, "ledger_recreated": mutate_ledger_recreated}


class Pins(Base):
    def test_each_pin_divergent_before_claim_refuses_without_effect(self):
        for name, change in MUTATIONS.items():
            with self.subTest(pin=name):
                self.tearDown()
                self.setUp()
                change(self)
                with self.assertRaises(s.Refusal):
                    self.go("2126", "2026-10-09T00:26:00Z")
                self.assertFalse((self.root / "2126").exists())
                self.assertFalse((self.base / "campaign-old" / "2126").exists())
                self.assertEqual(FakeProvider.instances, [])
                for ledger in (self.root / s.LEDGER_NAME, self.base / "ledger-old", self.base / "ledger-away"):
                    if ledger.exists():
                        self.assertEqual(ledger.read_bytes(), b"")

    def test_each_pin_divergent_between_claim_and_get_is_hold_without_get(self):
        for name, change in MUTATIONS.items():
            with self.subTest(pin=name):
                self.tearDown()
                self.setUp()
                r = self.go("2156", "2026-10-09T00:56:00Z", hook=lambda: change(self))
                self.assertEqual((r["status"], r["pre_get_recheck"], r["slot_consumed"]), ("SLOT_HOLD", "FAIL", True))
                self.assertEqual((r["logical_fetch_calls"], self.calls()), (0, 0))
                self.assertIsNone(r["cipher_sha256"])              # no child after the environment changed
                slot_dir = (self.base / "campaign-old" / "2156") if name == "root_replaced" else (self.root / "2156")
                self.assertTrue((slot_dir / s.RECEIPT_NAME).exists())
                self.assertFalse((slot_dir / s.CIPHER_NAME).exists())

    def test_revoked_between_claim_and_get_is_hold_without_get(self):
        r = self.go("2126", "2026-10-09T00:26:00Z", hook=lambda: (self.root / s.REVOKED_NAME).write_bytes(b"{}\n"))
        self.assertEqual((r["status"], r["code"], r["logical_fetch_calls"]), ("SLOT_HOLD", "CAMPAIGN_REVOKED_BEFORE_GET", 0))
        self.assertEqual(self.calls(), 0)

    def test_clock_jump_between_claim_and_get_is_hold_without_get(self):
        clock = Clock("2026-10-09T00:26:00Z")
        def jump():
            clock.now = clock.now + timedelta(seconds=5)
        r = self.go("2126", None, clock=clock, hook=jump)
        self.assertEqual((r["status"], r["code"], r["logical_fetch_calls"]), ("SLOT_HOLD", "CLOCK_WALL_MONOTONIC_DIVERGED", 0))
        self.assertEqual(self.calls(), 0)

    def test_clock_jump_backwards_is_hold(self):
        clock = Clock("2026-10-09T00:26:30Z")
        def jump():
            clock.now = clock.now - timedelta(seconds=3)
        r = self.go("2126", None, clock=clock, hook=jump)
        self.assertEqual((r["code"], r["logical_fetch_calls"]), ("CLOCK_WALL_MONOTONIC_DIVERGED", 0))

    def test_calendar_cut_between_claim_and_get_is_hold(self):
        clock, mono = Clock("2026-10-09T00:26:59Z"), Mono()
        def late():
            clock.now = clock.now + timedelta(seconds=2)
            mono.t += 2
        r = self.go("2126", None, clock=clock, mono=mono, hook=late)
        self.assertEqual((r["code"], r["logical_fetch_calls"]), ("START_LATE_FOR_SLOT", 0))

    def test_installed_measurement_is_stable(self):
        again = s.measure(self.probe, utc("2026-10-08T22:31:00Z"))
        self.assertEqual(again["election"], self.measured["election"])
        self.assertNotEqual(again["runtime"]["measurement_record_sha256"], self.measured["runtime"]["measurement_record_sha256"])


class Ledger(Base):
    def test_duplicate_slot_refused(self):
        self.go("2226", "2026-10-09T01:26:01Z")
        with self.assertRaises(s.Refusal) as e:
            self.go("2226", "2026-10-09T01:26:02Z")
        self.assertEqual(str(e.exception), "SLOT_ALREADY_CLAIMED")
        lines = (self.root / s.LEDGER_NAME).read_bytes().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(self.calls(), 1)

    def test_ledger_reset_after_claims_cannot_reopen(self):
        self.go("2126", "2026-10-09T00:26:00Z")
        rewrite(self.root / s.LEDGER_NAME, b"")              # same inode, emptied
        os.chmod(self.root / s.LEDGER_NAME, 0o600)
        with self.assertRaises(s.Refusal) as e:
            self.go("2156", "2026-10-09T00:56:00Z")
        self.assertEqual(str(e.exception), "LEDGER_SLOT_DIRECTORY_MISMATCH")
        self.assertEqual(self.calls(), 1)

    def test_runtime_never_creates_the_ledger(self):
        os.unlink(self.root / s.LEDGER_NAME)
        with self.assertRaises(s.Refusal) as e:
            self.go("2126", "2026-10-09T00:26:00Z")
        self.assertEqual(str(e.exception), "LEDGER_UNAVAILABLE")
        self.assertFalse((self.root / s.LEDGER_NAME).exists())

    def test_age_missing_refused_and_nothing_written_anywhere(self):
        (self.root / "age").unlink()
        cwd = self.base / "cwd"
        cwd.mkdir()
        old = os.getcwd()
        os.chdir(cwd)
        try:
            with self.assertRaises(s.Refusal):
                self.go("2126", "2026-10-09T00:26:00Z")
        finally:
            os.chdir(old)
        self.assertEqual(list(cwd.iterdir()), [])
        self.assertNotIn("2126", self.entries())
        self.assertEqual(self.calls(), 0)

    def test_claim_failure_after_mkdir_is_uncertain_and_writes_nothing_by_name(self):
        cwd = self.base / "cwd"
        cwd.mkdir()
        real = s.write_new
        def failing(dir_fd, name, raw):
            if name == s.CLAIM_NAME:
                raise OSError(28, "No space left on device")
            return real(dir_fd, name, raw)
        old = os.getcwd()
        os.chdir(cwd)
        try:
            with patch.object(s, "write_new", failing):
                r = self.go("2156", "2026-10-09T00:56:00Z")
        finally:
            os.chdir(old)
        self.assertEqual((r["status"], r["code"], r["slot_consumed"]), ("SLOT_HOLD", "SLOT_CLAIM_UNCERTAIN", True))
        self.assertEqual(list(cwd.iterdir()), [])
        self.assertEqual(list((self.root / "2156").iterdir()), [])
        self.assertEqual(self.calls(), 0)

    def test_existing_slot_directory_refused(self):
        os.mkdir(self.root / "2256", 0o700)
        with self.assertRaises(s.Refusal) as e:
            self.go("2256", "2026-10-09T01:56:00Z")
        self.assertIn(str(e.exception), ("SLOT_ALREADY_CLAIMED", "LEDGER_SLOT_DIRECTORY_MISMATCH"))
        self.assertEqual(self.calls(), 0)

    def test_ledger_is_append_only_across_slots(self):
        self.go("2126", "2026-10-09T00:26:00Z")
        first = (self.root / s.LEDGER_NAME).read_bytes()
        self.go("2156", "2026-10-09T00:56:00Z")
        second = (self.root / s.LEDGER_NAME).read_bytes()
        self.assertTrue(second.startswith(first))
        self.assertEqual([json.loads(x)["slot"] for x in second.splitlines()], ["2126", "2156"])

    def test_revoked_campaign_refused(self):
        (self.root / s.REVOKED_NAME).write_bytes(b"{}\n")
        with self.assertRaises(s.Refusal) as e:
            self.go("2126", "2026-10-09T00:26:00Z")
        self.assertEqual(str(e.exception), "CAMPAIGN_REVOKED")
        self.assertFalse((self.root / "2126").exists())


# ---------------------------------------------------------------- B2: signatures in time
class Signatures(Base):
    def refused(self, raws, code, slot="2126", at="2026-10-09T00:26:00Z"):
        with self.assertRaises(s.Refusal) as e:
            self.go(slot, at, raws=raws)
        self.assertEqual(str(e.exception), code)
        self.assertEqual(self.entries(), ["age", s.LEDGER_NAME])
        self.assertEqual(FakeProvider.instances, [])

    def test_owner_after_slot_refused_but_later_slot_ok(self):
        raws = build(self.measured, owner_at="2026-10-09T00:30:00Z", published_at="2026-10-09T00:29:00Z")
        self.refused(raws, "OWNER_SIGNED_AFTER_SLOT")
        r = self.go("2156", "2026-10-09T00:56:00Z", raws=raws)
        self.assertEqual(r["status"], "SLOT_OBSERVED_PASS")

    def test_owner_exactly_at_slot_refused(self):
        raws = build(self.measured, owner_at="2026-10-09T00:26:00Z", published_at="2026-10-09T00:25:00Z")
        self.refused(raws, "OWNER_SIGNED_AFTER_SLOT")

    def test_clock_not_after_owner_record_refused(self):
        raws = build(self.measured, owner_at="2026-10-09T00:25:59.500Z", published_at="2026-10-09T00:25:00Z")
        self.refused(raws, "CLOCK_NOT_AFTER_OWNER_SIGNATURE", at="2026-10-09T00:25:59Z")

    def test_owner_after_2145_brt_refused(self):
        raws = build(self.measured, owner_at="2026-10-09T00:45:01Z", published_at="2026-10-09T00:40:00Z")
        self.refused(raws, "OWNER_SIGNED_AFTER_2145_BRT", slot="2156", at="2026-10-09T00:56:00Z")

    def test_owner_at_2145_brt_accepted_for_later_slot(self):
        raws = build(self.measured, owner_at="2026-10-09T00:45:00Z", published_at="2026-10-09T00:40:00Z")
        self.assertEqual(self.go("2156", "2026-10-09T00:56:00Z", raws=raws)["status"], "SLOT_OBSERVED_PASS")

    def test_question_published_after_answer_refused(self):
        raws = build(self.measured, owner_at="2026-10-08T23:00:00Z", published_at="2026-10-08T23:00:01Z")
        self.refused(raws, "OWNER_ANSWER_BEFORE_QUESTION")

    def test_owner_missing_publication_field_refused(self):
        raws = build(self.measured)
        owner = s.strict(raws["owner"])
        del owner["question_published_at_utc"]
        raws["owner"] = s.canonical(owner)
        self.refused(raws, "OWNER_NOT_SIGNED")

    def test_unsigned_owner_refused(self):
        raws = build(self.measured, owner_over={"answer": "NAO"})
        self.refused(raws, "OWNER_NOT_SIGNED")

    def test_amendment_wrong_answer_refused(self):
        with self.assertRaises(s.Refusal) as e:
            build(self.measured, original=amendment_original(answer="Assino"))
        self.assertEqual(str(e.exception), "AMENDMENT_NOT_SIGNED")
        raws = build(self.measured, original=amendment_original(answer="Assino a emenda 6 da A2"), validate=False)
        self.refused(raws, "AMENDMENT_NOT_SIGNED")

    def test_amendment_wrong_document_hash_refused(self):
        raws = build(self.measured, original=amendment_original(document_sha256="6" * 64), validate=False)
        self.refused(raws, "AMENDMENT_NOT_SIGNED")

    def test_amendment_wrong_number_refused(self):
        raws = build(self.measured, original=amendment_original(amendment="A2_EMENDA_06"), validate=False)
        self.refused(raws, "AMENDMENT_NOT_SIGNED")

    def test_amendment_original_bytes_hash_mismatch_refused(self):
        raws = build(self.measured, config_sig="9" * 64, validate=False)
        self.refused(raws, "AMENDMENT_ORIGINAL_BYTES_CHANGED")

    def test_amendment_bytes_recanonicalized_refused(self):
        raws = build(self.measured)
        canon = s.canonical(json.loads(amendment_original()))
        raws["amendment_signature"] = s.canonical(s.amendment_wrapper(canon))     # same content, other bytes
        self.refused(raws, "BOUND_INPUT_PIN_MISMATCH" if False else "AMENDMENT_ORIGINAL_BYTES_CHANGED")

    def test_amendment_signed_after_owner_refused(self):
        raws = build(self.measured, original=amendment_original(signed_at_utc="2026-10-08T23:30:00Z"), validate=False)
        self.refused(raws, "OWNER_SIGNED_BEFORE_AMENDMENT")

    def test_amendment_signed_after_deadline_refused(self):
        raws = build(self.measured, original=amendment_original(signed_at_utc="2026-10-09T00:46:00Z"), validate=False)
        self.refused(raws, "AMENDMENT_SIGNED_AFTER_DEADLINE")

    def test_original_bytes_preserved_in_bound(self):
        original = amendment_original()
        wrapper = s.strict(self.raws["amendment_signature"])
        import base64
        self.assertEqual(base64.b64decode(wrapper["original_record_base64"]), original)
        self.assertNotEqual(original, s.canonical(json.loads(original)))

    def test_request_pins_runtime_election_and_provenance(self):
        q = s.strict(self.raws["request"])
        self.assertEqual(q["runtime_sha256"], s.sha(self.raws["runtime"]))
        self.assertEqual(q["election_sha256"], s.sha(self.raws["election"]))
        p = q["eligible_provenance"]
        self.assertEqual((p["registry_raw_sha256"], p["normalizer_reference_sha256"], p["types"], p["bulk_date"]),
                         (s.F1_REGISTRY_RAW_SHA256, s.REFERENCE, s.TYPES, "2026-10-08"))
        self.assertEqual(p["calendar_utc"], s.SLOTS)
        text = s.owner_question(self.raws["request"]).decode()
        self.assertIn("21:45 BRT", text)
        self.assertIn(q["runtime_sha256"], text)


class Budget(Base):
    def test_network_budget_exceeded_is_hold_and_consumed(self):
        r = self.go("2326", "2026-10-09T02:26:00Z", advance=s.NETWORK_SECONDS + 1, wall_advance=s.NETWORK_SECONDS + 1)
        self.assertEqual((r["status"], r["code"]), ("SLOT_HOLD", "NETWORK_BUDGET_EXCEEDED"))
        self.assertTrue(r["slot_consumed"])
        self.assertEqual(r["logical_fetch_calls"], 1)
        self.assertIsNotNone(r["cipher_sha256"])      # partial evidence still sealed

    def test_total_budget_exceeded(self):
        mono = Mono()
        def slow_cipher(age_fd, out_fd, payload, seconds):
            mono.t += s.MAX_SECONDS
            fake_cipher(age_fd, out_fd, payload, seconds)
        r = self.go("2356", "2026-10-09T02:56:00Z", mono=mono, cipher=slow_cipher)
        self.assertEqual((r["status"], r["code"]), ("SLOT_HOLD", "EXECUTION_BUDGET_EXCEEDED"))

    def test_http_not_ok_is_hold(self):
        r = self.go("2126", "2026-10-09T00:26:00Z", status=503)
        self.assertEqual((r["status"], r["code"], r["http_status"]), ("SLOT_HOLD", "PROVIDER_HTTP_NOT_OK", 503))

    def test_single_get_enforced(self):
        p = FakeProvider("t", Mono(), Clock("2026-10-09T00:26:00Z"), body=b"[]")
        p.fetch(0)
        with self.assertRaises(s.Hold):
            p.fetch(0)
        real = s.Provider("t")
        real.calls = 1
        with self.assertRaises(s.Hold) as e:
            real.fetch(10 ** 9)
        self.assertEqual(str(e.exception), "PROVIDER_CALL_LIMIT_EXCEEDED")


class Rule(Base):
    def test_threshold_pass_and_fail(self):
        r = self.go("2126", "2026-10-09T00:26:00Z", present=3990)
        self.assertEqual((r["status"], r["pass"], r["counts"]["required_minimum"]), ("SLOT_OBSERVED_PASS", True, 3990))
        r = self.go("2156", "2026-10-09T00:56:00Z", present=3989)
        self.assertEqual((r["status"], r["pass"]), ("SLOT_OBSERVED_FAIL", False))
        self.assertEqual(r["counts"]["absent_eligible_symbols"], 211)

    def test_public_result_has_no_symbol_or_token(self):
        r = self.go("2126", "2026-10-09T00:26:00Z", present=4000)
        text = (self.root / "2126" / s.RECEIPT_NAME).read_text()
        self.assertNotIn("S0001", text)
        self.assertNotIn("fixture-token", text)
        self.assertEqual(json.loads(text), r)

    def test_eligible_set_other_than_fixed_refused(self):
        with patch.object(s, "ELIGIBLE_SET_PIN", "a" * 64):
            with self.assertRaises(s.Refusal) as e:
                self.go("2126", "2026-10-09T00:26:00Z")
        self.assertEqual(str(e.exception), "ELIGIBLE_SET_NOT_THE_FIXED_ONE")


class Token(Base):
    def test_token_file_guards(self):
        path = self.base / "provider.env"
        path.write_text("OTHER=1\nC3PO_EODHD_API_TOKEN=\"abc123\"\n")
        os.chmod(path, 0o600)
        self.assertEqual(s.read_token(str(path), "C3PO_EODHD_API_TOKEN", physical=False), "abc123")
        os.chmod(path, 0o644)
        with self.assertRaises(s.Refusal):
            s.read_token(str(path), "C3PO_EODHD_API_TOKEN", physical=False)
        os.chmod(path, 0o600)
        path.write_text("OTHER=1\n")
        with self.assertRaises(s.Refusal):
            s.read_token(str(path), "C3PO_EODHD_API_TOKEN", physical=False)


class FixedNow(datetime):
    at = None

    @classmethod
    def now(cls, tz=None):
        return cls.at


class Main(Base):
    """Exit codes: only a Refusal is 3/no effect; anything else escaping run() is HOLD/2 (UNKNOWN)."""

    def main(self, runner):
        bound = s.canonical({"schema": "F2_BOUND_V2", "documents": {k: s.strict(v) for k, v in self.raws.items()}})
        (self.src / "BOUND.json").write_bytes(bound)
        out = []
        real_write = os.write
        def capture(fd, data):
            if fd == 1:
                out.append(data)
                return len(data)
            return real_write(fd, data)
        FixedNow.at = utc("2026-10-09T00:26:00Z")
        with patch.object(s, "datetime", FixedNow), patch.object(s.os, "write", capture):
            code = s.main(["run", "--bound", str(self.src / "BOUND.json"), "--slot", "2126"], runner=runner)
        return code, json.loads(b"".join(out)) if out else None

    def test_unexpected_exception_is_hold_exit_2_unknown(self):
        def boom(*_a, **_k):
            raise RuntimeError("free text never public")
        code, out = self.main(boom)
        self.assertEqual((code, out["status"], out["code"], out["slot_consumed"]), (2, "SLOT_HOLD", "SERIES_INTERNAL_FAILURE", "UNKNOWN"))

    def test_refusal_is_exit_3(self):
        def refuse(*_a, **_k):
            raise s.Refusal("LEDGER_BUSY")
        code, out = self.main(refuse)
        self.assertEqual((code, out["status"], out["slot_consumed"]), (3, "SLOT_REFUSED_NO_EFFECT", False))

    def test_hold_from_run_is_exit_2(self):
        code, out = self.main(lambda *_a, **_k: {"status": "SLOT_HOLD", "code": "X"})
        self.assertEqual(code, 2)

    def test_failed_final_write_keeps_exit_code(self):
        bound = s.canonical({"schema": "F2_BOUND_V2", "documents": {k: s.strict(v) for k, v in self.raws.items()}})
        (self.src / "BOUND.json").write_bytes(bound)
        def broken(fd, data):
            raise OSError(32, "Broken pipe")
        FixedNow.at = utc("2026-10-09T00:26:00Z")
        with patch.object(s, "datetime", FixedNow), patch.object(s.os, "write", broken):
            code = s.main(["run", "--bound", str(self.src / "BOUND.json"), "--slot", "2126"],
                          runner=lambda *_a, **_k: {"status": "SLOT_OBSERVED_PASS"})
        self.assertEqual(code, 0)

    def test_bound_path_not_pinned_refused(self):
        FixedNow.at = utc("2026-10-09T00:26:00Z")
        with patch.object(s, "datetime", FixedNow), patch.object(s.os, "write", lambda fd, d: len(d)):
            code = s.main(["run", "--bound", str(self.base / "BOUND.json"), "--slot", "2126"])
        self.assertEqual(code, 3)


# ---------------------------------------------------------------- B3: two-phase install
class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="f2i-", dir=str(Path.home()))
        os.chmod(self.tmp.name, 0o700)
        self.base = Path(self.tmp.name)
        self.src, self.root = self.base / "src", self.base / "campaign"
        self.patches = [patch.object(s, "AGE_SHA256", s.sha(FAKE_AGE)),
                        patch.object(s, "SOURCE_ROOT", str(self.src)), patch.object(s, "CAMPAIGN_ROOT", str(self.root)),
                        patch.object(s, "ELIGIBLE_SET_PIN", s.sha(eligible_raw())),
                        patch.object(s, "ELIGIBLE_COUNT", len(SYMBOLS))]
        for p in self.patches:
            p.start()
        self.stage = self.base / "stage"
        (self.stage / s.FAMILY_DIR).mkdir(parents=True)
        for line in (HERE / "SHA256SUMS").read_text().splitlines():
            name = line.split("  ", 1)[1]
            shutil.copyfile(HERE / name, self.stage / s.FAMILY_DIR / name)
        shutil.copyfile(HERE / "SHA256SUMS", self.stage / s.FAMILY_DIR / "SHA256SUMS")
        (self.stage / "ELIGIBLE_SET.json").write_bytes(eligible_raw())
        self.f1_age = self.base / "f1-age"
        self.f1_age.write_bytes(FAKE_AGE)
        self.probe = FakeProbe()
        self.argv = []
        self.stage_amendment()

    def stage_amendment(self, seal=None, signed_at="2026-10-08T21:00:00Z", answer="Assino a emenda 7 da A2"):
        """Emenda 7 document naming this family's seal, its ORIGINAL Assino and the leaf config, staged."""
        seal = seal or s.sha((self.stage / s.FAMILY_DIR / "SHA256SUMS").read_bytes())
        doc = ("# A2 - EMENDA 7 (fixture)\nselo `" + seal + "`\nResposta: Assino a emenda 7 da A2\n").encode()
        globals()["AMENDMENT_DOC"] = s.sha(doc)
        original = amendment_original(signed_at_utc=signed_at, answer=answer)
        (self.stage / ins.AMENDMENT_DOCUMENT).write_bytes(doc)
        (self.stage / ins.AMENDMENT_ORIGINAL).write_bytes(original)
        (self.stage / ins.LEAF_CONFIG).write_bytes(s.canonical({"schema": "F2_LEAF_CONFIG_V1", "amendment7_sha256": s.sha(doc),
                                                                "amendment7_signature_sha256": s.sha(original)}))

    def tearDown(self):
        for p in self.patches:
            p.stop()
        for path in self.base.rglob("*"):
            if path.is_dir() and not path.is_symlink():
                os.chmod(path, 0o700)
        self.tmp.cleanup()

    def prepare(self, token=lambda: "present", now="2026-10-08T21:30:00Z"):
        return ins.prepare(self.stage, f1_age=self.f1_age, require_root=False, token_check=token, clock=lambda: utc(now))

    def test_prepare_refuses_before_amendment7_signature_without_effect(self):
        with self.assertRaises(s.Hold) as e:
            self.prepare(now="2026-10-08T20:59:59Z")          # Emenda 7 signed at 21:00:00Z
        self.assertEqual(str(e.exception), "PREPARE_BEFORE_AMENDMENT7_SIGNATURE")
        self.assertFalse(self.src.exists() or self.root.exists())

    def test_prepare_refuses_amendment_naming_another_seal_or_wrong_literal(self):
        for kw, code in (({"seal": "0" * 64}, "AMENDMENT7_DOES_NOT_NAME_THIS_SEAL"),
                         ({"answer": "Assino"}, "AMENDMENT_NOT_SIGNED")):
            with self.subTest(**{k: str(v)[:8] for k, v in kw.items()}):
                self.stage_amendment(**kw)
                with self.assertRaises(s.Hold) as e:
                    self.prepare()
                self.assertEqual(str(e.exception), code)
                self.assertFalse(self.src.exists() or self.root.exists())
        # Another revision's document that merely mentions this seal is refused (one labelled seal only).
        seal = s.sha((self.stage / s.FAMILY_DIR / "SHA256SUMS").read_bytes())
        other = ("# Emenda 7 rev X\nselo `" + "1" * 64 + "`\nsubstitui a rev 3.2 (selo `" + seal + "`), revogada\n").encode()
        orig = amendment_original()
        globals()["AMENDMENT_DOC"] = s.sha(other)
        orig = amendment_original()
        (self.stage / ins.AMENDMENT_DOCUMENT).write_bytes(other)
        (self.stage / ins.AMENDMENT_ORIGINAL).write_bytes(orig)
        (self.stage / ins.LEAF_CONFIG).write_bytes(s.canonical({"schema": "F2_LEAF_CONFIG_V1", "amendment7_sha256": s.sha(other),
                                                                "amendment7_signature_sha256": s.sha(orig)}))
        with self.assertRaises(s.Hold) as e:
            self.prepare()
        self.assertEqual(str(e.exception), "AMENDMENT7_DOES_NOT_NAME_THIS_SEAL")
        self.assertFalse(self.src.exists() or self.root.exists())
        # Original that differs from the config pin is refused.
        self.stage_amendment()
        (self.stage / ins.AMENDMENT_ORIGINAL).write_bytes(amendment_original(channel="other"))
        with self.assertRaises(s.Hold):
            self.prepare()
        self.assertFalse(self.src.exists() or self.root.exists())
        self.stage_amendment()
        (self.stage / ins.AMENDMENT_DOCUMENT).write_bytes(b"other document")
        with self.assertRaises(s.Hold) as e:
            self.prepare()
        self.assertEqual(str(e.exception), "AMENDMENT7_DOCUMENT_MISMATCH")

    def test_measure_without_prepare_receipt_fails(self):
        self.prepare()
        os.chmod(self.src, 0o700)
        os.unlink(self.src / ins.PREPARE_RECEIPT)
        with self.assertRaises(BaseException):
            ins.measure(self.probe, utc("2026-10-08T21:40:00Z"), physical=False)

    def test_measurement_carries_prepare_receipt_bound_to_amendment(self):
        r = self.prepare()
        self.assertEqual(r["amendment7_signed_at_utc"], "2026-10-08T21:00:00Z")
        measured = ins.measure(self.probe, utc("2026-10-08T21:40:00Z"), physical=False)
        m = measured["measurement"]
        self.assertEqual(m["prepare_receipt_sha256"], r["prepare_receipt_sha256"])
        self.assertEqual(measured["runtime"]["measurement_record_sha256"], s.sha(s.canonical(m)))
        sig = s.canonical(s.amendment_wrapper((self.stage / ins.AMENDMENT_ORIGINAL).read_bytes()))
        b.measured_before_signature(s.canonical(m), s.canonical(measured["runtime"]), sig)
        other = s.canonical(s.amendment_wrapper(amendment_original(signed_at_utc="2026-10-08T20:00:00Z")))
        with self.assertRaises(s.Hold) as e:
            b.measured_before_signature(s.canonical(m), s.canonical(measured["runtime"]), other)
        self.assertEqual(str(e.exception), "PREPARE_RECEIPT_UNBOUND")

    def bound(self, measured, **kw):
        raws = build(measured, **kw)
        raw = s.canonical({"schema": "F2_BOUND_V2", "documents": {k: s.strict(v) for k, v in raws.items()}})
        (self.stage / "BOUND.json").write_bytes(raw)
        return s.sha(raw)

    def install(self, digest, now="2026-10-08T23:10:00Z"):
        return ins.install(self.stage, digest, probe=self.probe, runner=lambda argv: self.argv.append(argv) or 0,
                           clock=lambda: utc(now), require_root=False, token_check=lambda: "present", physical=False)

    def test_prepare_measure_install_happy_path(self):
        r = self.prepare()
        self.assertEqual((r["status"], r["timers"]), ("PREPARED_NO_TIMER", 0))
        self.assertEqual((self.root / s.LEDGER_NAME).read_bytes(), b"")
        self.assertEqual(oct((self.root / s.LEDGER_NAME).stat().st_mode & 0o777), "0o600")
        self.assertFalse((self.src / "BOUND.json").exists())
        self.assertEqual(self.argv, [])
        measured = ins.measure(self.probe, utc("2026-10-08T22:40:00Z"), physical=False)
        out = self.install(self.bound(measured))
        self.assertEqual((out["remeasure"], out["preflight"], len(out["timers"])), ("EQUAL", "PASS", 8))
        self.assertNotIn("code", out)
        self.assertEqual(len(self.argv), 8)
        self.assertEqual(oct((self.src / "BOUND.json").stat().st_mode & 0o777), "0o400")

    def test_install_skips_slots_not_after_owner_record(self):
        self.prepare()
        measured = ins.measure(self.probe, utc("2026-10-08T22:40:00Z"), physical=False)
        out = self.install(self.bound(measured, owner_at="2026-10-09T00:30:00Z", published_at="2026-10-09T00:29:00Z"),
                           now="2026-10-09T00:31:00Z")
        self.assertNotIn("2126", [t["slot"] for t in out["timers"]])
        self.assertEqual(len(self.argv), 7)

    def test_prepare_refuses_existing_roots_and_token_absent_creates_nothing(self):
        def absent():
            raise s.Refusal("PROVIDER_TOKEN_UNAVAILABLE")
        with self.assertRaises(s.Refusal):
            self.prepare(token=absent)
        self.assertFalse(self.src.exists() or self.root.exists())
        os.mkdir(self.root, 0o700)
        with self.assertRaises(s.Hold) as e:
            self.prepare()
        self.assertEqual(str(e.exception), "ROOTS_ALREADY_EXIST")
        self.assertFalse(self.src.exists())

    def test_prepare_refuses_other_eligible_set_before_any_root(self):
        (self.stage / "ELIGIBLE_SET.json").write_bytes(eligible_raw().replace(b"S0000", b"Z0000"))
        with self.assertRaises(s.Hold) as e:
            self.prepare()
        self.assertEqual(str(e.exception), "STAGE_ELIGIBLE_SET_NOT_FIXED")
        self.assertFalse(self.src.exists() or self.root.exists())

    def test_install_with_divergent_remeasurement_creates_zero_timers(self):
        cases = {"boot": lambda: self.probe.vals.update(boot=b"other-boot\n"),
                 "uid": lambda: self.probe.vals.update(euid=os.geteuid() + 1),
                 "python": lambda: self.probe.vals.update(version="3.12.9"),
                 "ledger_recreated": lambda: (os.rename(self.root / s.LEDGER_NAME, self.base / "old-ledger"),
                                              (self.root / s.LEDGER_NAME).write_bytes(b"")),
                 "ledger_not_empty": lambda: (self.root / s.LEDGER_NAME).write_bytes(b"x"),
                 "root_mode": lambda: os.chmod(self.root, 0o750),
                 "source_bytes": lambda: rewrite(self.src / s.FAMILY_DIR / "series_runtime.py",
                                                 (self.src / s.FAMILY_DIR / "series_runtime.py").read_bytes() + b"\n")}
        for name, change in cases.items():
            with self.subTest(case=name):
                self.tearDown()
                self.setUp()
                self.prepare()
                measured = ins.measure(self.probe, utc("2026-10-08T22:40:00Z"), physical=False)
                digest = self.bound(measured)
                change()
                with self.assertRaises(s.Hold):
                    self.install(digest)
                self.assertEqual(self.argv, [])

    def test_install_before_owner_record_refuses_without_effect(self):
        self.prepare()
        measured = ins.measure(self.probe, utc("2026-10-08T22:40:00Z"), physical=False)
        digest = self.bound(measured)                      # owner recorded at OWNER_AT = 23:00Z
        with self.assertRaises(s.Hold) as e:
            self.install(digest, now="2026-10-08T22:59:59Z")
        self.assertEqual(str(e.exception), "INSTALL_BEFORE_OWNER_RECORD")
        self.assertFalse((self.src / "BOUND.json").exists())
        self.assertEqual(self.argv, [])

    def test_runner_failure_mid_loop_is_uncertain_and_lists_created_timers(self):
        self.prepare()
        measured = ins.measure(self.probe, utc("2026-10-08T22:40:00Z"), physical=False)
        digest = self.bound(measured)
        calls = []
        def runner(argv):
            calls.append(argv)
            if len(calls) == 3:
                raise subprocess.TimeoutExpired(argv, 30)
            return 0
        out = ins.install(self.stage, digest, probe=self.probe, runner=runner, clock=lambda: utc("2026-10-08T23:10:00Z"),
                          require_root=False, token_check=lambda: "present", physical=False)
        self.assertEqual(out["code"], "TIMER_INSTALL_UNCERTAIN")
        self.assertEqual([t["installed"] for t in out["timers"]], [True, True, "UNCERTAIN"])
        self.assertEqual(len(calls), 3)

    def test_bind_request_refuses_measurement_before_amendment7(self):
        self.prepare()
        measured = ins.measure(self.probe, utc("2026-10-08T21:40:00Z"), physical=False)
        late_sig = s.canonical(s.amendment_wrapper(amendment_original(signed_at_utc="2026-10-08T21:45:00Z")))
        with self.assertRaises(s.Hold) as e:
            b.measured_before_signature(s.canonical(measured["measurement"]), s.canonical(measured["runtime"]), late_sig)
        self.assertEqual(str(e.exception), "MEASUREMENT_BEFORE_AMENDMENT7")

    def test_install_refuses_wrong_bound_hash_without_copy(self):
        self.prepare()
        measured = ins.measure(self.probe, utc("2026-10-08T22:40:00Z"), physical=False)
        self.bound(measured)
        with self.assertRaises(s.Hold) as e:
            self.install("a" * 64)
        self.assertEqual(str(e.exception), "STAGE_BOUND_MISMATCH")
        self.assertFalse((self.src / "BOUND.json").exists())
        self.assertEqual(self.argv, [])

    def test_bind_measurement_split_checks_record(self):
        self.prepare()
        measured = ins.measure(self.probe, utc("2026-10-08T22:40:00Z"), physical=False)
        parts = b.split_measurement(s.canonical(measured))
        self.assertEqual(s.strict(parts["runtime"]), measured["runtime"])
        bad = dict(measured, runtime=dict(measured["runtime"], boot_id_sha256="b" * 64))
        with self.assertRaises(s.Hold):
            b.split_measurement(s.canonical(bad))


class Systemd(unittest.TestCase):
    def test_slots_are_brt_minus_three(self):
        for slot, at in s.SLOTS.items():
            local = utc(at) - timedelta(hours=3)
            self.assertEqual(local.strftime("%H%M"), slot)
            self.assertEqual(local.date().isoformat(), "2026-10-08" if slot[0] == "2" else "2026-10-09")
            self.assertEqual(at[:10], "2026-10-09")

    def test_calendar_and_argv(self):
        argv = ins.slot_command("2126")
        self.assertEqual(argv[0], "/usr/bin/systemd-run")
        self.assertIn("--on-calendar=2026-10-09 00:26:00 UTC", argv)
        self.assertIn("--timer-property=AccuracySec=1s", argv)
        self.assertIn("--unit=f2s-20261008-2126", argv)
        self.assertIn("--property=WorkingDirectory=" + s.CAMPAIGN_ROOT, argv)
        self.assertIn("--property=LimitCORE=0", argv)
        joined = " ".join(argv)
        for banned in ("Persistent", "Restart", "TOKEN", "api_token", "--setenv", "-E"):
            self.assertNotIn(banned, joined)
        self.assertEqual(argv[-4:], ["--bound", s.SOURCE_ROOT + "/BOUND.json", "--slot", "2126"])
        self.assertEqual(ins.calendar("0056"), "2026-10-09 03:56:00 UTC")

    def test_plan_only_future_slots_with_margin(self):
        rows = ins.plan(utc("2026-10-09T00:23:01Z"))       # 2126 has 179 s: excluded
        self.assertEqual([r["slot"] for r in rows], ["2156", "2226", "2256", "2326", "2356", "0026", "0056"])
        rows = ins.plan(utc("2026-10-09T00:23:00Z"))       # exactly 180 s: included
        self.assertEqual(rows[0]["slot"], "2126")
        self.assertEqual(ins.plan(utc("2026-10-09T03:53:01Z")), [])
        rows = ins.plan(utc("2026-10-08T21:30:00Z"))
        self.assertEqual(len(rows), 8)
        self.assertEqual([r["utc"] for r in rows], sorted(s.SLOTS.values()))


def public(slot, status, present=None, eligible=4200, code=None, started=None, received=None):
    c = None
    passed = None
    if status != "SLOT_HOLD":
        c = {"eligible_symbols": eligible, "present_eligible_symbols": present, "required_minimum": 3990}
        passed = status == "SLOT_OBSERVED_PASS"
    at = s.SLOTS[slot]
    return {"schema": "F2_PUBLIC_SLOT_RESULT_V1", "family": s.FAMILY, "slot": slot, "scheduled_at": at,
            "status": status, "code": code, "pass": passed, "counts": c, "eligible_set_sha256": "e" * 64,
            "request_sha256": "r" * 64, "started_at": started or at, "fetch_started_at": started or at,
            "received_at": received or s.iso(utc(at) + timedelta(seconds=5)), "http_status": 200 if c else None,
            "body_sha256": None, "logical_fetch_calls": 1 if c else 0}


class Analyzer(unittest.TestCase):
    def test_first_pass_last_fail_gaps_regressions(self):
        rs = [public("2126", "SLOT_OBSERVED_FAIL", 3000), public("2156", "SLOT_OBSERVED_FAIL", 3900),
              public("2226", "SLOT_OBSERVED_PASS", 4100), public("2256", "SLOT_OBSERVED_FAIL", 3980),
              public("2356", "SLOT_HOLD", code="NETWORK_BUDGET_EXCEEDED"), public("0026", "SLOT_OBSERVED_PASS", 4150)]
        out = a.analyze([a.load(json.dumps(r)) for r in rs])
        self.assertEqual(out["first_pass"]["slot"], "2226")
        self.assertEqual(out["last_fail_before_first_pass"]["slot"], "2156")
        self.assertEqual([(g["slot"], g["reason"]) for g in out["gaps"]],
                         [("2326", "NO_RESULT"), ("2356", "HOLD"), ("0056", "NO_RESULT")])
        kinds = [(x["from"], x["to"], x["kind"]) for x in out["regressions"]]
        self.assertIn(("2226", "2256", "PASS_TO_FAIL"), kinds)
        self.assertIn(("2226", "2256", "PRESENT_DECREASED"), kinds)
        self.assertEqual(out["slots"][0]["fetch_seconds"], 5.0)
        self.assertFalse(out["readiness_or_GO_granted"])

    def test_no_pass(self):
        out = a.analyze([a.load(json.dumps(public("2126", "SLOT_OBSERVED_FAIL", 10)))])
        self.assertIsNone(out["first_pass"])
        self.assertEqual(out["last_fail_before_first_pass"]["slot"], "2126")

    def test_inconsistent_pass_rejected(self):
        bad = public("2126", "SLOT_OBSERVED_PASS", 10)
        with self.assertRaises(s.Hold):
            a.load(json.dumps(bad))

    def test_duplicate_slot_rejected(self):
        r = a.load(json.dumps(public("2126", "SLOT_OBSERVED_FAIL", 10)))
        with self.assertRaises(s.Hold):
            a.analyze([r, r])


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    print(json.dumps({"schema": "F2_TEST_RESULT_V1", "ran": result.testsRun, "failures": len(result.failures),
                      "errors": len(result.errors), "ok": result.wasSuccessful()}, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
