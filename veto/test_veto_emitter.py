"""New synthetic cases only. No REAL verifier or operational evidence exists here."""
import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
loader = importlib.util.spec_from_file_location("veto_emitter", HERE / "veto_emitter.py")
v = importlib.util.module_from_spec(loader)
import sys
sys.modules[loader.name] = v
loader.loader.exec_module(v)


class EmitterTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 12, 13, 0, 4, tzinfo=timezone.utc)
        self.observation = b"SYNTHETIC_EXTERNAL_ORIGINAL_NOT_OPERATIONAL\n"
        self.authority = b"SYNTHETIC_AUTHORITY_NOT_OPERATIONAL\n"
        self.spec = {
            "schema": v.SPEC_SCHEMA, "mode": "FIXTURE",
            "context": {"epoch": "r2d2-v2-04", "first_session": "2026-10-12",
                        "day": "2026-10-12", "order_sha": "1" * 64},
            "source": {"identity": "synthetic-external-source", "implementation_sha256": "2" * 64,
                       "observation_format": "SYNTHETIC_ORIGINAL_V1"},
            "verifier": {"identity": "synthetic-verifier", "implementation_sha256": "3" * 64},
            "authority_sha256": v.digest(self.authority), "view_opens_at": "2026-10-12T13:00:00Z",
            "required_pins": sorted(["1" * 64, "2" * 64, "3" * 64, v.digest(self.authority)]),
            "maximum_age_seconds": 10,
        }
        self.row = v.VerifiedObservation(
            mode="FIXTURE", source_identity="synthetic-external-source",
            source_implementation_sha256="2" * 64, observation_format="SYNTHETIC_ORIGINAL_V1",
            original_sha256=v.digest(self.observation), authority_sha256=v.digest(self.authority),
            authority_valid_from="2026-10-12T12:59:00Z", authority_valid_until="2026-10-12T13:01:00Z",
            authority_required_pins=tuple(self.spec["required_pins"]), permitted_output_role="FABLE",
            authenticity_verified=True, authority_verified=True, revocation_checked=True,
            epoch="r2d2-v2-04", first_session="2026-10-12", day="2026-10-12", order_sha="1" * 64,
            view_opens_at="2026-10-12T13:00:00Z", status="VERIFIED",
            observed_at="2026-10-12T13:00:00Z", valid_until="2026-10-12T13:00:10Z",
            owner_veto=False, revoked_shas=())
        self.calls = []

    def verifier(self, row=None, callback=None, **overrides):
        def verify(original, authority, spec_raw, now):
            self.calls.append((original, authority, spec_raw, now))
            return self.row if row is None else row
        return v.VerifierBinding(overrides.get("identity", "synthetic-verifier"),
                                 overrides.get("pin", "3" * 64), overrides.get("mode", "FIXTURE"),
                                 verify if callback is None else callback)

    def emit(self, *, spec=None, row=None, raw=None, authority=None, pin=None, verifier=None, clock=None):
        spec_raw = v.canonical(self.spec if spec is None else spec) + b"\n"
        return v.emit_view(spec_raw,
                           self.observation if raw is None else raw,
                           self.authority if authority is None else authority,
                           v.digest(self.observation) if pin is None else pin,
                           spec_sha256=v.digest(spec_raw),
                           verifier=self.verifier(row) if verifier is None else verifier,
                           clock=(lambda: self.now) if clock is None else clock)

    def refuses(self, code, **kwargs):
        with self.assertRaisesRegex(v.Refused, "^" + code + "$"):
            self.emit(**kwargs)

    def test_fixture_is_draft_with_exact_image_body(self):
        out = self.emit()
        doc = json.loads(out.view_raw.decode().split("```json\n")[1].split("\n```")[0])
        self.assertEqual(doc["state"], "DRAFT")
        self.assertEqual(set(doc), {"schema", "kind", "state", "body"})
        self.assertEqual(set(doc["body"]), {"status", "role", "epoch", "day", "order_sha", "observed_at",
                                          "valid_until", "owner_veto", "revoked_shas", "evidence_sha"})
        self.assertEqual(doc["body"]["evidence_sha"], v.digest(self.observation))
        self.assertEqual(doc["body"]["observed_at"], self.row.observed_at)
        self.assertEqual(doc["body"]["valid_until"], self.row.valid_until)
        self.assertFalse(out.operational_GO)
        self.assertEqual(self.calls[0][:2], (self.observation, self.authority))

    def test_reinvocation_never_renews_observation(self):
        one = self.emit()
        self.now += timedelta(seconds=3)
        two = self.emit()
        self.assertEqual(one.view_raw, two.view_raw)
        self.assertEqual(one.view_sha256, two.view_sha256)

    def test_changed_original_rejected_before_callback(self):
        self.refuses("VETO_ORIGINAL_HASH", raw=self.observation + b"changed")
        self.assertEqual(self.calls, [])

    def test_absent_original(self):
        self.refuses("VETO_ORIGINAL_ABSENT", raw=b"")

    def test_authority_original_changed(self):
        self.refuses("VETO_AUTHORITY_HASH", authority=self.authority + b"changed")
        self.assertEqual(self.calls, [])

    def test_authority_interval_covers_entire_observation(self):
        for field, value in (("authority_valid_from", "2026-10-12T13:00:01Z"),
                             ("authority_valid_until", "2026-10-12T13:00:09Z")):
            self.refuses("VETO_AUTHORITY_INTERVAL", row=replace(self.row, **{field: value}))

    def test_specfile_must_match_independent_pin_before_callback(self):
        raw = v.canonical(self.spec) + b"\n"
        with self.assertRaisesRegex(v.Refused, "^VETO_SPEC_HASH$"):
            v.emit_view(raw, self.observation, self.authority, v.digest(self.observation),
                        spec_sha256="4" * 64, verifier=self.verifier(), clock=lambda: self.now)
        self.assertEqual(self.calls, [])

    def test_no_default_or_dictionary_verifier(self):
        for value in (False, {}, "trusted"):
            self.refuses("VETO_VERIFIER_UNBOUND", verifier=value)

    def test_verifier_identity_and_code_pin_are_required(self):
        for verifier in (self.verifier(identity="other"), self.verifier(pin="4" * 64)):
            self.refuses("VETO_VERIFIER_IDENTITY", verifier=verifier)

    def test_fixture_binding_cannot_be_used_as_real(self):
        spec = dict(self.spec, mode="REAL")
        self.refuses("VETO_VERIFIER_MODE", spec=spec)
        self.assertEqual(self.calls, [])

    def test_fixture_result_cannot_be_used_as_real(self):
        self.refuses("VETO_VERIFIER_MODE", spec=dict(self.spec, mode="REAL"),
                     verifier=self.verifier(mode="REAL"))

    def test_source_identity_format_and_source_code_pin(self):
        for field in ("source_identity", "observation_format", "source_implementation_sha256"):
            value = "5" * 64 if field.endswith("sha256") else "other"
            self.refuses("VETO_SOURCE_IDENTITY", row=replace(self.row, **{field: value}))

    def test_context_is_exact(self):
        mutations = {"epoch": "r2d2-v2-03", "first_session": "2026-10-13", "day": "2026-10-13", "order_sha": "5" * 64}
        for field, value in mutations.items():
            self.refuses("VETO_OBSERVATION_CONTEXT", row=replace(self.row, **{field: value}))

    def test_original_and_authority_binding_from_verifier(self):
        for field in ("original_sha256", "authority_sha256"):
            self.refuses("VETO_ORIGINAL_BINDING", row=replace(self.row, **{field: "5" * 64}))

    def test_all_external_verifications_must_be_literal_true(self):
        for field in ("authenticity_verified", "authority_verified", "revocation_checked"):
            for value in (False, 1, "True"):
                self.refuses("VETO_EXTERNAL_VERIFICATION", row=replace(self.row, **{field: value}))

    def test_revocation_scope_and_output_role_must_be_authorized(self):
        self.refuses("VETO_REVOCATION_SCOPE", row=replace(self.row, authority_required_pins=("1" * 64,)))
        self.refuses("VETO_ROLE_NOT_AUTHORIZED", row=replace(self.row, permitted_output_role="EXTERNAL_VENDOR"))

    def test_unknown_and_draft_status_refuse(self):
        for status in ("UNKNOWN", "DRAFT", "PENDING", "NO_VETO"):
            self.refuses("VETO_STATUS_UNKNOWN", row=replace(self.row, status=status))

    def test_expired_and_future_observation_refuse(self):
        self.refuses("VETO_STALE_OR_FUTURE", clock=lambda: self.now + timedelta(seconds=6))
        self.refuses("VETO_STALE_OR_FUTURE", clock=lambda: self.now - timedelta(seconds=5))

    def test_validity_is_positive_and_at_most_ten_seconds(self):
        for until in ("2026-10-12T13:00:00Z", "2026-10-12T12:59:59Z", "2026-10-12T13:00:11Z"):
            self.refuses("VETO_VALIDITY_INTERVAL", row=replace(self.row, valid_until=until))

    def test_observed_is_the_real_view_instant_not_timer_instant(self):
        self.refuses("VETO_VIEW_INSTANT", row=replace(self.row, observed_at="2026-10-12T13:00:01Z"))
        self.refuses("VETO_VIEW_INSTANT", row=replace(self.row, view_opens_at="2026-10-12T13:00:01Z"))

    def test_owner_veto_and_non_boolean_refuse(self):
        for value in (True, 0, "False"):
            self.refuses("VETO_OWNER_VETOED", row=replace(self.row, owner_veto=value))

    def test_each_critical_pin_revocation_refuses(self):
        for pin in self.spec["required_pins"]:
            self.refuses("VETO_AUTHORITY_REVOKED", row=replace(self.row, revoked_shas=(pin,)))

    def test_other_revocation_is_preserved(self):
        out = self.emit(row=replace(self.row, revoked_shas=("5" * 64,)))
        self.assertIn(b'"revoked_shas":["' + b"5" * 64 + b'"]', out.view_raw)

    def test_callback_failure_does_not_expose_original_or_error(self):
        def callback(*args):
            raise RuntimeError("private-provider-token")
        self.refuses("VETO_VERIFIER_REJECTED", verifier=self.verifier(callback=callback))

    def test_result_is_typed_not_a_status_dictionary(self):
        self.refuses("VETO_VERIFIER_RESULT", row={"status": "VERIFIED"})

    def test_verifier_delay_causes_expiry_and_rollback_refuses(self):
        for second, code in ((self.now + timedelta(seconds=6), "VETO_STALE_OR_FUTURE"),
                             (self.now - timedelta(seconds=1), "VETO_CLOCK_ROLLBACK")):
            readings = iter([self.now, second])
            self.refuses(code, clock=lambda: next(readings))

    def test_zero_pin_extra_scope_and_invalid_spec_refuse(self):
        for field, value, code in (("authority_sha256", "0" * 64, "VETO_AUTHORITY_PIN"),
                                  ("maximum_age_seconds", True, "VETO_MAX_AGE"),
                                  ("required_pins", ["1" * 64], "VETO_REQUIRED_SCOPE")):
            self.refuses(code, spec=dict(self.spec, **{field: value}))
        self.refuses("VETO_SPEC_FIELDS", spec=dict(self.spec, ignored=True))

    def test_duplicate_spec_keys_and_noncanonical_bytes_refuse(self):
        for raw, code in ((b'{"schema":1,"schema":2}', "VETO_SPEC_DUPLICATE_KEY"),
                          (json.dumps(self.spec).encode(), "VETO_SPEC_CANONICAL")):
            with self.assertRaisesRegex(v.Refused, "^" + code + "$"):
                v.read_spec(raw)

    def test_naive_clock_and_non_utc_original_refuse(self):
        self.refuses("VETO_CLOCK_UTC", clock=lambda: self.now.replace(tzinfo=None))
        self.refuses("VETO_TIME_UTC", row=replace(self.row, observed_at="2026-10-12T09:00:00-04:00"))

    def test_image_parser_reads_fixture_for_review_but_runtime_rejects_it(self):
        source = (HERE / "originals" / "r2d2_v2_document_format.py").read_bytes()
        expected = json.loads((HERE / "CONSUMER_PINS.json").read_bytes())["r2d2_v2_document_format.py"]["sha256"]
        self.assertEqual(v.digest(source), expected)
        # Execute only the pinned parser and veto-reader AST definitions, not app imports.
        names = {"parse_document", "normalized_fields", "PinnedVetoReader"}
        nodes = [n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
        self.assertEqual({n.name for n in nodes}, names)
        class ConsumerRefused(ValueError):
            pass
        def need(ok, code):
            if not ok:
                raise ConsumerRefused(code)
        scope = {"BEGIN": v.BEGIN, "END": v.END, "SCHEMA": v.DOCUMENT_SCHEMA,
                 "COMMON": {"schema", "kind", "state", "body"}, "json": json,
                 "canonical": v.canonical, "need": need, "ShadowIntegrityError": ConsumerRefused,
                 "hashlib": v.hashlib, "is_sha": lambda x: type(x) is str and v.SHA.fullmatch(x) is not None,
                 "utc": lambda x: x if isinstance(x, datetime) else v.instant(x), "timedelta": timedelta}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "pinned_consumer_selected_definitions", "exec"), scope)
        out = self.emit()
        parsed = scope["parse_document"](out.view_raw, allow_draft=True)
        self.assertEqual(parsed["body"]["observed_at"], self.row.observed_at)
        class Root:
            def read(self, name):
                return out.view_raw
        reader = scope["PinnedVetoReader"](Root(), file="fixture.md", sha256=out.view_sha256,
                                          epoch=self.row.epoch, day=self.row.day, order_sha=self.row.order_sha)
        with self.assertRaisesRegex(ConsumerRefused, "^DOCUMENT_DRAFT_OR_UNBOUND$"):
            reader(self.now)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EmitterTests))
    summary = {"schema": "CODEX_IMAGE_VETO_EMITTER_SYNTHETIC_RESULT_V1", "mode": "FIXTURE",
               "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
               "operational_GO": False, "actual_external_originals": 0, "REAL_verifier_supplied": False,
               "actual_host_operations": 0}
    (HERE / "LOCAL_RESULT.json").write_bytes(v.canonical(summary) + b"\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
