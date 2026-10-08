"""New F1 proof only, all identities/signatures/provider/crypto are synthetic.

No network, app import, host, SQL, real key, owner question or real operation.
The runtime DI seam is called only by these tests; the CLI has no test bypass.
"""
import concurrent.futures
import ast
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagnostic_runtime as d
import bind_diagnostic as binder
import verify_family as verifier

NOW = d.stamp("2026-10-08T20:26:01Z")
TOKEN = "SYNTHETIC_PRIVATE_TOKEN_NOT_A_CREDENTIAL"
AMENDMENT_RAW = d.canonical({"schema": "DUDU_AMENDMENT_SIGNATURE_V1", "amendment": "A2_EMENDA_06", "revision": 1,
    "document_file": "/SYNTHETIC_NOT_A_REAL_OWNER_RECORD", "document_sha256": d.AMENDMENT,
    "answer": "Assino a emenda 6 da A2", "signed_at_utc": "2026-10-08T16:34:25Z",
    "channel": "Claude Code (Fable), AskUserQuestion"})


def fixtures():
    registry = [{"Code": "AA", "Exchange": "NYSE", "Type": "Common Stock"},
                {"Code": "BB", "Exchange": "NASDAQ", "Type": "Common Stock"},
                {"Code": "CC", "Exchange": "NYSE", "Type": "Common Stock"},
                {"Code": "DD", "Exchange": "NYSE", "Type": "Common Stock"},
                {"Code": "EF", "Exchange": "NYSE", "Type": "ETF"},
                {"Code": "BAD?", "Exchange": "NYSE", "Type": "Common Stock"},
                {"Code": "OT", "Exchange": "OTC", "Type": "Common Stock"}]
    def bar(code, **kw):
        return dict({"code": code, "date": d.BULK_DAY, "open": 10, "high": 12, "low": 9,
                     "close": 11, "volume": 100}, **kw)
    bulk = [bar("AA"), bar("AA"), bar("CC", volume=-1), bar("DD"), bar("DD", close=10),
            bar("AA", date="2026-10-06"), bar("EF"), {"not": "a dated bar"}]
    return d.canonical(registry), d.canonical(bulk)


def signed_fixtures(root, day="2026-10-08"):
    """Synthetic parser witnesses, never published as a real signed leaf."""
    election = {"schema": "F1_SINGLE_ELECTION_V1", "epoch": d.EPOCH, "operation": d.OPERATION,
                "amendment_sha256": d.AMENDMENT, "private_root": str(root),
                "parent_identities": [{"path": x, "device": 0, "inode": 1, "uid": os.geteuid(), "gid": 0, "mode": 0o700}
                                      for x in d.paths_to_root(str(root))], "claim_name": d.CLAIM_NAME}
    runtime = {"schema": "F1_RUNTIME_IDENTITY_V1", "source_sha256": d.sha(Path(d.__file__).read_bytes()),
               "reference_sha256": d.REFERENCE, "seal_sha256": "1" * 64, "age_sha256": d.AGE_SHA256,
               "python_version": "%d.%d.%d" % sys.version_info[:3], "python_executable_sha256": "6" * 64,
               "boot_id_sha256": "2" * 64,
               "executor_uid": os.geteuid(), "platform": "linux", "measurement_record_sha256": "3" * 64}
    amendment = d.amendment_record(AMENDMENT_RAW)
    config = {"schema": "F1_LEAF_CONFIG_V1", "execution_date": day,
              "not_before": day + "T20:26:00Z" if day == "2026-10-08" else day + "T17:26:00Z",
              "not_after": day + "T20:33:39Z" if day == "2026-10-08" else day + "T17:33:39Z",
              "age_path": str(root / "age")}
    eraw, rraw = d.canonical(election), d.canonical(runtime)
    review = {"schema": "F1_CODEX_REVIEW_V1", "verdict": "ACCEPTED_OWN_BYTES_LINUX_AND_RUNTIME",
              "source_sha256": runtime["source_sha256"], "reference_sha256": d.REFERENCE,
              "seal_sha256": runtime["seal_sha256"], "runtime_sha256": d.sha(rraw), "election_sha256": d.sha(eraw),
              "linux_result_sha256": "4" * 64, "review_record_sha256": "5" * 64}
    ar = d.canonical(amendment)
    # Request builder must pin the actual provided sums bytes; this fixture's
    # fake sums are not a seal. Override the synthetic runtime to that digest.
    sums = b"SYNTHETIC_SUMS_NOT_AN_OPERATIONAL_SEAL"
    runtime["seal_sha256"] = d.sha(sums)
    rraw = d.canonical(runtime)
    review["seal_sha256"] = d.sha(sums)
    review["runtime_sha256"] = d.sha(rraw)
    vr = d.canonical(review)
    request = binder.request_from_inputs(d.canonical(config), eraw, rraw, vr, ar,
                                         Path(d.__file__).read_bytes(), sums)
    owner = {"schema": "F1_OWNER_SIGNATURE_V1", "request_sha256": d.sha(request),
             "question_sha256": d.sha(d.owner_question(request)), "answer": "Assino",
             "recorded_at_utc": "2026-10-08T20:25:00Z", "channel": "REGISTRO_PELA_FABLE"}
    return {"request": request, "owner": d.canonical(owner), "election": eraw, "runtime": rraw,
            "review": vr, "amendment_signature": ar}


class FakeProvider:
    def __init__(self, fail=None):
        self.calls, self.fail = 0, fail
        self.registry, self.bulk = fixtures()

    def fetch(self, kind, deadline):
        self.calls += 1
        raw = self.registry if kind == "registry" else self.bulk
        if kind == self.fail:
            raw = raw[:15]
        return raw, {"kind": kind, "started_at": d.iso(NOW), "received_at": d.iso(NOW),
                     "http_status": 200, "body_sha256": d.sha(raw), "body_bytes": len(raw),
                     "body_complete": kind != self.fail, "code": "PROVIDER_BODY_PARTIAL" if kind == self.fail else None}


class DiagnosticTest(unittest.TestCase):
    def test_sets_present_rule_and_provenance(self):
        a, b = fixtures()
        r = d.analyze(a, b, NOW, NOW)
        self.assertEqual(r["counts"]["eligible_symbols"], 4)
        self.assertEqual(r["counts"]["present_eligible_symbols"], 3)
        self.assertEqual(r["counts"]["usable_eligible_symbols"], 1)
        self.assertEqual(r["counts"]["required_minimum"], 4)
        self.assertEqual(r["counts"]["absent_eligible_symbols"], 1)
        self.assertEqual(r["eligible_absent"][0]["symbol"], "BB")
        self.assertEqual(r["eligible_absent"][0]["registry_pointer"], "/1")
        self.assertEqual(r["counts"]["duplicate_eligible_rows"], 1)
        self.assertEqual(r["counts"]["conflicting_eligible_symbols"], 1)
        self.assertEqual(r["raw_sha256"], {"registry": d.sha(a), "bulk": d.sha(b)})
        self.assertEqual(r["status"], "DIAGNOSTIC_COMPLETE_WITH_LAST_TRADE_UNKNOWN")
        self.assertNotIn("readiness", r)

    def test_no_last_trade_inferred_from_any_timestamps(self):
        a, b = fixtures()
        rows = json.loads(a)
        rows[0]["last_trade"] = "2026-10-07"
        rows[0]["updated_at"] = "2026-10-08"
        r = d.analyze(d.canonical(rows), b, NOW, NOW)
        self.assertEqual(r["counts"]["last_trade_unknown_symbols"], 4)
        self.assertTrue(all(x["status"] == "UNKNOWN_NOT_PROVIDED" for x in r["last_trade"]))

    def test_duplicate_registry_first_wins_like_pinned_normalizer(self):
        rows = [{"Code": "AA", "Exchange": "NYSE", "Type": "ETF"},
                {"Code": "AA", "Exchange": "NYSE", "Type": "Common Stock"}]
        r = d.analyze(d.canonical(rows), b"[]", NOW, NOW)
        self.assertEqual(r["counts"]["eligible_symbols"], 0)
        self.assertEqual(r["counts"]["registry_duplicate_rows"], 1)

    def test_technical_reasons_for_unusable_rows(self):
        registry = d.canonical([{"Code": "AA", "Exchange": "NYSE", "Type": "Common Stock"}])
        cases = [({"volume": -1}, "NEGATIVE_VOLUME"), ({"open": 0}, "NONPOSITIVE_PRICE"),
                 ({"high": 2}, "OHLC_ORDER_INVALID"), ({"close": True}, "INVALID_NUMBER_CLOSE"),
                 ({"close": "10"}, "INVALID_NUMBER_CLOSE")]
        for patch_values, reason in cases:
            row = dict(code="AA", date=d.BULK_DAY, open=10, high=12, low=9, close=11, volume=100)
            row.update(patch_values)
            r = d.analyze(registry, d.canonical([row]), NOW, NOW)
            self.assertIn(reason, r["present_unusable"][0]["reasons"])
        del row["close"]
        r = d.analyze(registry, d.canonical([row]), NOW, NOW)
        self.assertIn("MISSING_CLOSE", r["present_unusable"][0]["reasons"])

    def test_registry_before_close_and_invalid_bulk_hold(self):
        a, b = fixtures()
        with self.assertRaises(d.Hold):
            d.analyze(a, b, d.stamp(d.PREVIOUS_CLOSE), NOW)
        with self.assertRaises(d.Hold):
            d.analyze(a, b"{}", NOW, NOW)

    def test_window_forbidden_minutes_and_80_second_margin(self):
        for point in ("20:15:00", "20:25:59", "20:03:40", "20:08:40", "20:33:40", "20:37:59"):
            self.assertFalse(d.allowed_start(d.stamp("2026-10-08T" + point + "Z")))
        for point in ("20:26:00", "20:33:39", "20:38:00", "20:03:39", "20:08:39"):
            self.assertTrue(d.allowed_start(d.stamp("2026-10-08T" + point + "Z")))
        with tempfile.TemporaryDirectory() as td:
            raw = signed_fixtures(Path(td))
            d.validate_documents(raw, NOW)
            q = d.strict(raw["request"])
            for start in ("2026-10-08T20:15:00Z", "2026-10-08T19:26:00Z"):
                bad = dict(q, not_before=start)
                with self.assertRaises(d.Hold):
                    d.validate_window(bad)

    def test_last_start_budget_and_expiry_refused(self):
        with tempfile.TemporaryDirectory() as td:
            raw = signed_fixtures(Path(td))
            d.validate_documents(raw, d.stamp("2026-10-08T20:31:39Z"))
            for now in (d.stamp("2026-10-08T20:31:40Z"), d.stamp("2026-10-08T20:33:39Z")):
                with self.assertRaisesRegex(d.Hold, "OUTSIDE_START_WINDOW"):
                    d.validate_documents(raw, now)

    def test_missing_no_unsigned_altered_scope_and_pin_refused(self):
        with tempfile.TemporaryDirectory() as td:
            raws = signed_fixtures(Path(td))
            for answer in ("NÃO", "", "assino", "Assino outra coisa"):
                owner = dict(d.strict(raws["owner"]), answer=answer)
                with self.assertRaisesRegex(d.Hold, "OWNER_NOT_SIGNED"):
                    d.validate_documents(dict(raws, owner=d.canonical(owner)), NOW)
            for key, value in (("retry_limit", 1), ("bulk_date", "2026-10-08"),
                               ("runtime_sha256", "0" * 64), ("recipient", "age1wrong")):
                request = dict(d.strict(raws["request"]));request[key] = value
                with self.assertRaises(d.Hold):
                    d.validate_documents(dict(raws, request=d.canonical(request)), NOW)
            with self.assertRaises(d.Hold):
                d.validate_documents({k: v for k, v in raws.items() if k != "owner"}, NOW)

    def test_review_linux_runtime_election_and_signature_required(self):
        with tempfile.TemporaryDirectory() as td:
            raws = signed_fixtures(Path(td))
            for name in ("review", "runtime", "election", "amendment_signature"):
                with self.assertRaisesRegex(d.Hold, "BOUND_INPUT_PIN_MISMATCH"):
                    d.validate_documents(dict(raws, **{name: d.canonical({"schema": "INVALID"})}), NOW)

    def test_unsigned_request_preflight_rejects_review_and_signature_before_question(self):
        with tempfile.TemporaryDirectory() as td:
            raws = signed_fixtures(Path(td))
            q = d.strict(raws["request"])
            config = d.canonical({"schema": "F1_LEAF_CONFIG_V1", "execution_date": q["execution_date"],
                                 "not_before": q["not_before"], "not_after": q["not_after"], "age_path": q["age_path"]})
            for review, signature in ((d.canonical({"schema": "INVALID"}), raws["amendment_signature"]),
                                      (raws["review"], d.canonical({"schema": "INVALID"}))):
                with self.assertRaises(d.Hold):
                    binder.request_from_inputs(config, raws["election"], raws["runtime"], review, signature,
                                               Path(d.__file__).read_bytes(), b"SYNTHETIC_SUMS_NOT_AN_OPERATIONAL_SEAL")

    def test_amendment_adapter_requires_unchanged_original_bytes(self):
        self.assertEqual(d.amendment_record(AMENDMENT_RAW)["original_record_sha256"], d.sha(AMENDMENT_RAW))
        for raw in (AMENDMENT_RAW + b"\n", b'{}'):
            with self.assertRaisesRegex(d.Hold, "AMENDMENT_ORIGINAL_BYTES_CHANGED"):
                d.amendment_record(raw)

    def test_physical_identity_refusal_has_zero_fetches_and_no_claim(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td);raws = signed_fixtures(root);provider = FakeProvider()
            with patch.object(d.sys, "platform", "other"):
                with self.assertRaisesRegex(d.Hold, "RUNTIME_CHANGED"):
                    d.run(raws, provider, clock=lambda: NOW, physical=True)
            self.assertEqual(provider.calls, 0)
            self.assertFalse((root / d.CLAIM_NAME).exists())

    def test_strict_canonical_duplicate_and_nonfinite(self):
        for raw in (b'{"a":1,"a":2}', b'{"a": NaN}', b'{"a":1} ', b'[]'):
            with self.assertRaises(d.Hold):
                d.strict(raw)

    def test_extract_ast_normalizes_only_empty_new_python_fields(self):
        raw = Path(d.__file__).with_name("reference_extract.py").read_bytes()
        original = ast.dump(verifier.normalize_ast(ast.parse(raw)), include_attributes=False)
        tree = ast.parse(raw)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                if "type_params" not in node._fields:node._fields += ("type_params",)
                node.type_params = []
        self.assertEqual(ast.dump(verifier.normalize_ast(tree), include_attributes=False), original)
        tree = ast.parse(raw)
        tree.body[0].type_params = [ast.Name(id="unexpected")]
        with self.assertRaises(AssertionError):verifier.normalize_ast(tree)

    def test_cli_refuses_before_token_and_never_echoes_private_arguments(self):
        with tempfile.TemporaryDirectory() as td:
            bound = Path(td) / "invalid.json";bound.write_bytes(b'{}');out = []
            with patch.object(d, "Provider", side_effect=AssertionError("TOKEN_CONSTRUCTION_BEFORE_AUTH")), \
                 patch.object(d.os, "write", lambda fd, raw: out.append(raw)):
                self.assertEqual(d.main(["--bound", str(bound)]), 2)
                self.assertEqual(d.main(["--bound", str(bound), "--unexpected", TOKEN]), 2)
            self.assertEqual(len(out), 2)
            for raw in out:
                self.assertNotIn(TOKEN.encode(), raw)
                self.assertNotIn(str(bound).encode(), raw)
                self.assertEqual(json.loads(raw)["logical_fetch_calls"], 0)

    def test_bundle_full_raw_manifest_and_bounded_archive(self):
        a, b = fixtures()
        payload, inv = d.private_bundle({"registry.raw": a, "bulk.raw": b})
        with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
            self.assertEqual(archive.extractfile("registry.raw").read(), a)
            self.assertEqual(archive.extractfile("bulk.raw").read(), b)
            manifest = archive.extractfile("inventory.json").read()
            self.assertEqual(d.sha(manifest), inv)
            self.assertEqual(json.loads(manifest)["files"]["bulk.raw"]["sha256"], d.sha(b))
        with patch.object(d, "PRIVATE_LIMIT", 10):
            with self.assertRaisesRegex(d.Hold, "PRIVATE_BUNDLE_TOO_LARGE"):
                d.private_bundle({"registry.raw": a})
        with self.assertRaises(d.Hold):
            d.private_bundle({"../escape": b"x"})

    def run_fixture(self, root, raws, provider, fail_cipher=False):
        seen = []
        def cipher(age_fd, output_fd, payload, seconds):
            seen.append(payload)
            if fail_cipher:
                raise d.Hold("CIPHER_FAILED_OR_DEADLINE")
            os.write(output_fd, b"age-encryption.org/v1\nSYNTHETIC_NOT_ENCRYPTION\n" + d.sha(payload).encode())
        def root_fd(q):
            return os.open(str(root), os.O_RDONLY | os.O_DIRECTORY)
        with patch.object(d, "open_private_root", root_fd):
            result = d.run(raws, provider, clock=lambda: NOW, monotonic=lambda: 1.0,
                           cipher=cipher, age_opener=lambda q: os.open(str(Path(__file__)), os.O_RDONLY), physical=False)
        return result, seen

    def test_complete_synthetic_pipeline_has_no_public_symbols_or_token(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td);raw = signed_fixtures(root);provider = FakeProvider()
            result, seen = self.run_fixture(root, raw, provider)
            self.assertEqual(result["status"], "DIAGNOSTIC_COMPLETE_WITH_LAST_TRADE_UNKNOWN")
            self.assertEqual(provider.calls, 2)
            self.assertFalse(result["provider_ready_granted"])
            self.assertFalse(result["capacity_or_E6_or_GO_granted"])
            public = d.canonical(result)
            for private in (b'"AA"', b'"BB"', TOKEN.encode(), str(root).encode()):
                self.assertNotIn(private, public)
            self.assertEqual(len(seen), 1)
            with tarfile.open(fileobj=io.BytesIO(seen[0])) as archive:
                self.assertEqual(archive.extractfile("registry.raw").read(), provider.registry)
                self.assertEqual(archive.extractfile("bulk.raw").read(), provider.bulk)
            self.assertEqual(os.stat(root / d.CLAIM_NAME).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(root / d.CIPHER_NAME).st_mode & 0o777, 0o600)

    def test_partial_body_is_retained_private_and_no_second_get_or_retry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td);provider = FakeProvider(fail="registry")
            result, seen = self.run_fixture(root, signed_fixtures(root), provider)
            self.assertEqual(result["status"], "DIAGNOSTIC_HOLD")
            self.assertEqual(provider.calls, 1)
            self.assertTrue(result["attempt_consumed"])
            with tarfile.open(fileobj=io.BytesIO(seen[0])) as archive:
                self.assertEqual(archive.extractfile("registry.raw").read(), provider.registry[:15])
                self.assertIn("failure.json", archive.getnames())
                self.assertNotIn("bulk.raw", archive.getnames())

    def test_cipher_failure_spends_attempt_and_preserves_existing_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td);raw = signed_fixtures(root)
            result, _ = self.run_fixture(root, raw, FakeProvider(), fail_cipher=True)
            self.assertEqual(result["status"], "DIAGNOSTIC_HOLD")
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            again, _ = self.run_fixture(root, raw, FakeProvider())
            self.assertEqual(again["code"], "ATTEMPT_ALREADY_CONSUMED")
            self.assertEqual(again["logical_fetch_calls"], 0)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_reservation_is_shared_across_execution_dates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td);raw = signed_fixtures(root)
            first, _ = self.run_fixture(root, raw, FakeProvider())
            friday = signed_fixtures(root, "2026-10-09")
            fake = FakeProvider()
            with patch.object(d, "open_private_root", lambda q: os.open(str(root), os.O_RDONLY | os.O_DIRECTORY)):
                again = d.run(friday, fake, clock=lambda: d.stamp("2026-10-09T17:26:01Z"), monotonic=lambda: 1.0,
                              age_opener=lambda q: None, physical=False)
            self.assertTrue(first["attempt_consumed"])
            self.assertEqual(again["code"], "ATTEMPT_ALREADY_CONSUMED")
            self.assertEqual(fake.calls, 0)
            self.assertEqual(d.strict(raw["request"])["election_sha256"], d.strict(friday["request"])["election_sha256"])

    def test_atomic_reservation_only_one_winner(self):
        with tempfile.TemporaryDirectory() as td:
            root = os.open(td, os.O_RDONLY | os.O_DIRECTORY)
            def claim(_):
                try:
                    d.reserve(root, {"election_sha256": "1" * 64}, "2" * 64)
                    return "won"
                except d.Hold:
                    return "lost"
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    outcomes = list(pool.map(claim, range(4)))
                self.assertEqual(outcomes.count("won"), 1)
            finally:
                os.close(root)

    def test_private_root_link_and_identity_changes_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = [{"path": p, "device": 0, "inode": 1, "uid": 0, "gid": 0, "mode": 0o700}
                    for p in d.paths_to_root(str(root))]
            with self.assertRaises(d.Hold):
                d.open_private_root({"private_root": str(root), "parent_identities": fake})
            for path in (str(root / ".."), str(root) + "//other", "/bad/../root"):
                with self.assertRaises(d.Hold):
                    d.paths_to_root(path)

    def test_http_fixed_origin_zero_retry_no_redirect_and_partial_overflow(self):
        class Response:
            status, length = 503, None
            def getheaders(self):return [("Content-Type", "application/json")]
            def read1(self, n):
                body = getattr(self, "body", b"partial-evidence");self.body = b"";return body[:n]
            def getheader(self, name, default):return default
        response = Response()
        class Connection:
            sock = None
            def __init__(self, *args, **kw):self.args = args
            def request(self, method, url, headers):seen.append((method, url, headers))
            def getresponse(self):return response
            def close(self):pass
        seen = []
        with patch.object(d.http.client, "HTTPSConnection", Connection):
            provider = d.Provider(TOKEN, monotonic=lambda: 0, clock=lambda: NOW)
            body, meta = provider.fetch("bulk", 15)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(body, b"partial-evidence")
        self.assertEqual(meta["code"], "PROVIDER_HTTP_NOT_OK")
        self.assertTrue(seen[0][1].startswith(d.BULK_PATH + "?"))
        self.assertIn("date=2026-10-07", seen[0][1])
        self.assertEqual(seen[0][0], "GET")
        self.assertEqual(seen[0][2]["Accept-Encoding"], "identity")

    def test_http_received_partial_bytes_retained_after_timeout_and_content_length_short(self):
        for mode in ("timeout", "short", "redirect", "overflow"):
            class Response:
                status = 302 if mode == "redirect" else 200
                length = 10 if mode == "short" else None
                step = 0
                def getheaders(self):return [("Content-Length", "10")]
                def read1(self, n):
                    self.step += 1
                    if self.step == 1:return b"partial" if mode != "overflow" else b"x" * n
                    if mode == "timeout":raise TimeoutError("PRIVATE_ERROR_MUST_NOT_ESCAPE")
                    return b""
                def getheader(self, name, default):return default
            class Connection:
                sock = None
                def __init__(self, *args, **kw):pass
                def request(self, *args, **kw):pass
                def getresponse(self):return Response()
                def close(self):pass
            with patch.object(d.http.client, "HTTPSConnection", Connection), patch.object(d, "REGISTRY_LIMIT", 6):
                provider = d.Provider(TOKEN, monotonic=lambda: 0, clock=lambda: NOW)
                # Use bulk for ordinary partial witnesses; registry limit six
                # exercises overflow retaining exactly limit+1 received bytes.
                body, meta = provider.fetch("registry" if mode == "overflow" else "bulk", 15)
            expected = {"timeout": "PROVIDER_TRANSPORT_FAILED", "short": "PROVIDER_BODY_PARTIAL",
                        "redirect": "PROVIDER_HTTP_NOT_OK", "overflow": "PROVIDER_BODY_TOO_LARGE"}[mode]
            self.assertEqual(meta["code"], expected)
            self.assertEqual(provider.calls, 1)
            self.assertEqual(body, b"x" * 7 if mode == "overflow" else b"partial")
            self.assertNotIn("PRIVATE_ERROR", str(meta))


def run_tests():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DiagnosticTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    record = {"schema": "F1_SYNTHETIC_TEST_RESULT_V1", "tests": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors), "complete_run": result.wasSuccessful(),
              "fixture_only": True, "real_provider_calls": 0, "real_crypto": False,
              "app_imports": 0, "host_calls": 0, "real_owner_signatures": 0,
              "source_sha256": d.sha(Path(d.__file__).read_bytes()), "reference_sha256": d.REFERENCE,
              "python": "%d.%d.%d" % sys.version_info[:3]}
    print(d.canonical(record).decode())
    return 0 if result.wasSuccessful() else 1


def main():
    # Pin substitution exists only in this synthetic proof, never on the CLI.
    with patch.object(d, "AMENDMENT_SIGNATURE_ORIGINAL", d.sha(AMENDMENT_RAW)):
        return run_tests()


if __name__ == "__main__":
    raise SystemExit(main())
