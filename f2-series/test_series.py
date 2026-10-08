"""Synthetic F2 tests: no network, host, real crypto, token or signature. stdlib unittest only."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
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


def eligible_raw():
    return s.canonical({"schema": "F2_ELIGIBLE_SET_V1", "types": ["COMMON_STOCK", "COMMON_STOCK_ADR"],
                        "readiness_rule": s.RULE, "provenance": {"origin": "SYNTHETIC_FIXTURE"}, "symbols": SYMBOLS})


def documents(source=b"source", seal=b"seal"):
    elig = eligible_raw()
    review_v = {"schema": "F2_CODEX_REVIEW_V1", "verdict": "ACCEPTED_OWN_BYTES_LINUX", "source_sha256": s.sha(source),
                "seal_sha256": s.sha(seal), "eligible_set_sha256": s.sha(elig), "linux_result_sha256": "1" * 64,
                "review_record_sha256": "2" * 64}
    review = s.canonical(review_v)
    config = s.canonical({"schema": "F2_LEAF_CONFIG_V1", "amendment7_sha256": "7" * 64,
                          "amendment7_signature_sha256": "8" * 64})
    request = b.request_from_inputs(config, review, elig, source, seal)
    owner = s.canonical({"schema": "F2_OWNER_SIGNATURE_V1", "request_sha256": s.sha(request),
                         "question_sha256": s.sha(s.owner_question(request)), "answer": "Assino",
                         "recorded_at_utc": "2026-10-08T23:00:00Z", "channel": "REGISTRO_PELA_FABLE"})
    return {"request": request, "owner": owner, "review": review}, elig


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


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="f2-test-", dir=str(Path.home()))
        self.root = Path(self.tmp.name) / "campaign"
        self.root.mkdir(mode=0o700)
        os.chmod(self.root, 0o700)
        (self.root / "age").write_bytes(FAKE_AGE)
        os.chmod(self.root / "age", 0o500)
        self.patches = [patch.object(s, "AGE_SHA256", s.sha(FAKE_AGE))]
        for p in self.patches:
            p.start()
        self.raws, self.elig = documents()
        FakeProvider.instances = []

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def go(self, slot, at, present=4200, advance=1.0, wall_advance=1.0, raws=None, elig=None, status=200, mono=None):
        clock, mono = Clock(at), mono or Mono()
        factory = lambda token, monotonic, clock: FakeProvider(token, monotonic, clock, body=bulk(present),
                                                               advance=advance, wall_advance=wall_advance, status=status)
        return s.run(raws or self.raws, slot, elig or self.elig, lambda: "fixture-token", clock=clock, monotonic=mono,
                     cipher=fake_cipher, provider_factory=factory, physical=False, campaign_root=str(self.root),
                     reference=s.load_reference(physical=False))

    def entries(self):
        return sorted(p.name for p in self.root.iterdir())


class ClockGuards(Base):
    def test_on_time_start_observes(self):
        r = self.go("2126", "2026-10-09T00:26:00.400Z")
        self.assertEqual(r["status"], "SLOT_OBSERVED_PASS")
        self.assertEqual(r["logical_fetch_calls"], 1)
        self.assertTrue((self.root / "2126" / s.RECEIPT_NAME).exists())
        self.assertTrue((self.root / "2126" / s.CIPHER_NAME).exists())

    def test_late_start_refused_without_effect(self):
        with self.assertRaises(s.Refusal) as e:
            self.go("2126", "2026-10-09T00:27:00.001Z")
        self.assertEqual(str(e.exception), "START_LATE_FOR_SLOT")
        self.assertEqual(self.entries(), ["age"])
        self.assertEqual(FakeProvider.instances, [])

    def test_early_start_refused(self):
        with self.assertRaises(s.Refusal) as e:
            self.go("2156", "2026-10-09T00:55:57Z")
        self.assertEqual(str(e.exception), "START_BEFORE_SLOT")
        self.assertEqual(self.entries(), ["age"])

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
        self.assertEqual(self.entries(), ["age"])

    def test_last_slot_inside_window_ok(self):
        r = self.go("0056", "2026-10-09T03:56:30Z")
        self.assertEqual(r["status"], "SLOT_OBSERVED_PASS")

    def test_receipt_after_0100_brt_is_hold(self):
        r = self.go("0056", "2026-10-09T03:56:59Z", wall_advance=190)
        self.assertEqual((r["status"], r["code"]), ("SLOT_HOLD", "RECEIVED_AFTER_0100_BRT"))
        self.assertTrue(r["slot_consumed"])
        self.assertIsNone(r["pass"])


class Ledger(Base):
    def test_duplicate_slot_refused(self):
        self.go("2226", "2026-10-09T01:26:01Z")
        with self.assertRaises(s.Refusal) as e:
            self.go("2226", "2026-10-09T01:26:02Z")
        self.assertEqual(str(e.exception), "SLOT_ALREADY_CLAIMED")
        lines = (self.root / s.LEDGER_NAME).read_bytes().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(sum(p.calls for p in FakeProvider.instances), 1)

    def test_age_missing_refused_and_nothing_written_anywhere(self):
        (self.root / "age").unlink()
        cwd = Path(self.tmp.name) / "cwd"
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
        self.assertEqual(sum(p.calls for p in FakeProvider.instances), 0)

    def test_claim_failure_after_mkdir_is_uncertain_and_writes_nothing_by_name(self):
        cwd = Path(self.tmp.name) / "cwd"
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
        self.assertEqual(sum(p.calls for p in FakeProvider.instances), 0)

    def test_existing_slot_directory_refused(self):
        os.mkdir(self.root / "2256", 0o700)
        with self.assertRaises(s.Refusal) as e:
            self.go("2256", "2026-10-09T01:56:00Z")
        self.assertEqual(str(e.exception), "SLOT_ALREADY_CLAIMED")
        self.assertEqual(sum(p.calls for p in FakeProvider.instances), 0)

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

    def test_root_not_exclusive_refused(self):
        os.chmod(self.root, 0o750)
        with self.assertRaises(s.Refusal) as e:
            self.go("2126", "2026-10-09T00:26:00Z")
        self.assertEqual(str(e.exception), "PRIVATE_ROOT_NOT_EXCLUSIVE")


class Budget(Base):
    def test_network_budget_exceeded_is_hold_and_consumed(self):
        r = self.go("2326", "2026-10-09T02:26:00Z", advance=s.NETWORK_SECONDS + 1)
        self.assertEqual((r["status"], r["code"]), ("SLOT_HOLD", "NETWORK_BUDGET_EXCEEDED"))
        self.assertTrue(r["slot_consumed"])
        self.assertEqual(r["logical_fetch_calls"], 1)
        self.assertIsNotNone(r["cipher_sha256"])      # partial evidence still sealed

    def test_total_budget_exceeded(self):
        mono = Mono()
        def slow_cipher(age_fd, out_fd, payload, seconds):
            mono.t += s.MAX_SECONDS
            fake_cipher(age_fd, out_fd, payload, seconds)
        clock = Clock("2026-10-09T02:56:00Z")
        factory = lambda token, monotonic, clock: FakeProvider(token, monotonic, clock, body=bulk(4200))
        r = s.run(self.raws, "2356", self.elig, lambda: "t", clock=clock, monotonic=mono, cipher=slow_cipher,
                  provider_factory=factory, physical=False, campaign_root=str(self.root),
                  reference=s.load_reference(physical=False))
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

    def test_tampered_eligible_set_refused(self):
        bad = eligible_raw().replace(b"S0000", b"Z0000")
        with self.assertRaises(s.Refusal) as e:
            self.go("2126", "2026-10-09T00:26:00Z", elig=bad)
        self.assertEqual(str(e.exception), "ELIGIBLE_SET_CHANGED")

    def test_unsigned_owner_refused(self):
        raws = dict(self.raws)
        owner = s.strict(raws["owner"])
        owner["answer"] = "NAO"
        raws["owner"] = s.canonical(owner)
        with self.assertRaises(s.Refusal) as e:
            self.go("2126", "2026-10-09T00:26:00Z", raws=raws)
        self.assertEqual(str(e.exception), "OWNER_NOT_SIGNED")


class Token(Base):
    def test_token_file_guards(self):
        path = Path(self.tmp.name) / "provider.env"
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
