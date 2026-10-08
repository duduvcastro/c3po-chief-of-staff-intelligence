"""New isolated safety/causality cases. No historical test suite is rerun."""
import copy
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from decision_contracts import (CHAIN, E6_INPUTS, SETS, SET_DOCUMENTS, Hold, bulk_series,
                                canonical, capacity_gate, c34_dependencies,
                                c35_window, decision_table, digest,
                                night_authorization, strict_json)
from server_controller import Controller, Ledger, reconcile_publication


H = "a" * 64
CONTEXT = {"epoch": "FIXTURE_NEW_EPOCH", "session_date": "2026-10-12", "lane": "FIXTURE"}


class Witness:
    def __init__(self, anchor):
        self.anchor = copy.deepcopy(anchor)
        self.fail = False

    def read(self):
        return copy.deepcopy(self.anchor)

    def advance(self, previous, following):
        if self.fail:
            return None
        if previous != self.anchor:
            raise Hold("WITNESS_CONFLICT")
        self.anchor = copy.deepcopy(following)
        return self.read()


class FixtureAdapter:
    mode = "FIXTURE"
    operation = "FIXTURE_NIGHT"

    def __init__(self):
        self.calls = 0
        self.pins = {"source": H, "runtime": H, "root": H, "calendar": H}
        self.fail = False
        self.bad_receipt = False

    def recheck(self):
        return copy.deepcopy(self.pins)

    def run_once(self, request):
        self.calls += 1
        if self.fail:
            raise RuntimeError("SECRET_HOST_PATH_TOKEN_RAW_MUST_NOT_LEAK")
        return {"schema": "F6_FIXTURE_RECEIPT_V1", "status": "COMPLETE",
                "request_sha256": "b" * 64 if self.bad_receipt else digest(canonical(request)),
                "context": copy.deepcopy(request["context"])}


def bundle_fixture():
    authority = {"context": CONTEXT, "slot": "ONLY_ATTEMPT", "epoch": "FIXTURE_NEW_EPOCH",
                 "session_date": "2026-10-12", "operation": "FIXTURE_NIGHT",
                 "revoked": False, "accepted": True, "mode": "FIXTURE",
                 "pins": {"source": H, "runtime": H, "root": H, "calendar": H}}
    request = {"schema": "F6_REQUEST_CANDIDATE_V1", "context": CONTEXT,
               "authority_slot": "ONLY_ATTEMPT", "epoch": "FIXTURE_NEW_EPOCH",
               "session_date": "2026-10-12", "operation": "FIXTURE_NIGHT",
               "start_UTC": "2026-10-12T00:26:00Z", "end_UTC": "2026-10-12T00:33:00Z",
               "budget_seconds": 120, "pins": copy.deepcopy(authority["pins"]),
               "required_gates": ["CAPACITY", "PREDECESSOR"]}
    question = {"request_sha256": digest(canonical(request)), "published_UTC": "2026-10-11T23:00:00Z",
                "published_readback": "GET1_GET2_EXACT_UNEDITED"}
    owner = {"literal": "Assino", "channel": "REGISTRO_PELA_FABLE",
             "request_sha256": digest(canonical(request)), "question_sha256": digest(canonical(question)),
             "signed_at_UTC": "2026-10-11T23:01:00Z", "original_readback": "OWN_EXACT_UNEDITED"}
    bound = {"request_sha256": digest(canonical(request)), "question_sha256": digest(canonical(question)),
             "owner_sha256": digest(canonical(owner)), "own_review": "ACCEPTED"}
    return authority, {"request": request, "question": question, "owner": owner, "bound": bound,
                       "gates": {"CAPACITY": "OWN_COMPLETE", "PREDECESSOR": "OWN_COMPLETE"}}


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp" if Path("/private/tmp").exists() else None)
        self.root = Path(self.temp.name) / "private-state"
        self.election = {"mode": "FIXTURE", "epoch": "FIXTURE_NEW_EPOCH", "identity": H}
        self.initial = Ledger.create_fixture(self.root, self.election)
        self.witness = Witness(self.initial)
        self.ledger = Ledger(self.root, self.election)
        self.now = "2026-10-12T00:26:01Z"
        self.controller = Controller(self.ledger, self.witness, wall_clock=lambda: self.now)
        self.authority, self.bundle = bundle_fixture()
        self.adapter = FixtureAdapter()

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def invoke(self):
        return self.controller.invoke(self.authority, self.bundle, self.adapter)

    def test_valid_fixture_then_refused_replay(self):
        self.assertEqual(self.invoke()["verdict"], "COMPLETE_FIXTURE")
        self.assertEqual(self.invoke()["verdict"], "HOLD_CONSUMED")
        self.assertEqual(self.adapter.calls, 1)

    def test_early_refusal_consumes_before_effect(self):
        self.now = "2026-10-12T00:25:59Z"
        self.assertEqual(self.invoke()["verdict"], "HOLD_WINDOW")
        self.now = "2026-10-12T00:26:01Z"
        self.assertEqual(self.invoke()["verdict"], "HOLD_CONSUMED")
        self.assertEqual(self.adapter.calls, 0)

    def test_no_catchup_after_end(self):
        self.now = "2026-10-12T00:33:01Z"
        self.assertEqual(self.invoke()["verdict"], "HOLD_WINDOW")
        self.assertEqual(self.adapter.calls, 0)

    def test_changed_nonce_cannot_create_second_option(self):
        self.invoke()
        self.bundle["request"]["nonce"] = "NEW_NONCE"
        self.assertEqual(self.invoke()["verdict"], "HOLD_CONSUMED")

    def test_crash_or_uncertain_result_never_reexecutes(self):
        self.adapter.fail = True
        result = self.invoke()
        self.assertEqual(result["verdict"], "HOLD_UNCERTAIN")
        self.assertNotIn("SECRET", str(result))
        self.adapter.fail = False
        self.assertEqual(self.invoke()["verdict"], "HOLD_CONSUMED")
        self.assertEqual(self.adapter.calls, 1)

    def test_changed_source_after_assino(self):
        self.bundle["request"]["pins"]["source"] = "b" * 64
        self.assertEqual(self.invoke()["verdict"], "HOLD_INVALID_BUNDLE")
        self.assertEqual(self.adapter.calls, 0)

    def test_physical_recheck_change(self):
        self.adapter.pins["runtime"] = "b" * 64
        self.assertEqual(self.invoke()["verdict"], "HOLD_RUNTIME")
        self.assertEqual(self.adapter.calls, 0)

    def test_owner_no_and_late_do_not_execute(self):
        self.bundle["owner"]["literal"] = "Não"
        self.assertEqual(self.invoke()["verdict"], "HOLD_INVALID_BUNDLE")
        self.assertEqual(self.adapter.calls, 0)

    def test_owner_late_even_with_internally_matching_hashes(self):
        self.bundle["owner"]["signed_at_UTC"] = self.bundle["request"]["start_UTC"]
        self.bundle["bound"]["owner_sha256"] = digest(canonical(self.bundle["owner"]))
        self.assertEqual(self.invoke()["verdict"], "HOLD_INVALID_BUNDLE")
        self.assertEqual(self.adapter.calls, 0)

    def test_predecessor_not_ready(self):
        self.bundle["gates"]["PREDECESSOR"] = "NOT_READY"
        self.assertEqual(self.invoke()["verdict"], "HOLD_GATES")
        self.assertEqual(self.adapter.calls, 0)

    def test_production_has_no_generic_fallback(self):
        self.authority["mode"] = "REAL"
        self.assertEqual(self.invoke()["verdict"], "HOLD_ADAPTER_UNAVAILABLE")
        self.assertEqual(self.adapter.calls, 0)

    def test_restart_preserves_consumption(self):
        self.invoke()
        other = Ledger(self.root, self.election)
        try:
            controller = Controller(other, self.witness, wall_clock=lambda: self.now)
            self.assertEqual(controller.invoke(self.authority, self.bundle, self.adapter)["verdict"], "HOLD_CONSUMED")
        finally:
            other.close()

    def test_rollback_detected_against_independent_witness(self):
        original = (self.root / "ledger.jsonl").read_bytes()
        self.invoke()
        (self.root / "ledger.jsonl").write_bytes(original)
        with self.assertRaisesRegex(Hold, "LEDGER_WITNESS_MISMATCH"):
            self.invoke()
        self.assertEqual(self.adapter.calls, 1)

    def test_incomplete_journal_never_repaired_by_reset(self):
        with (self.root / "ledger.jsonl").open("ab") as f:
            f.write(b'{"torn":')
        with self.assertRaisesRegex(Hold, "LEDGER_INCOMPLETE"):
            self.invoke()
        self.assertEqual(self.adapter.calls, 0)

    def test_lost_root_or_symlink(self):
        linked = Path(self.temp.name) / "link"
        linked.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(Hold, "STATE_ANCESTOR_LINK"):
            Ledger(linked, self.election)

    def test_private_permissions(self):
        os.chmod(self.root / "ledger.jsonl", 0o644)
        with self.assertRaisesRegex(Hold, "PRIVATE_FILE_IDENTITY"):
            self.invoke()
        self.assertEqual(self.adapter.calls, 0)

    def test_witness_uncertain_reservation_blocks_all_effects(self):
        self.witness.fail = True
        with self.assertRaisesRegex(Hold, "WITNESS_ADVANCE_UNCERTAIN"):
            self.invoke()
        self.assertEqual(self.adapter.calls, 0)
        self.witness.fail = False
        with self.assertRaisesRegex(Hold, "LEDGER_WITNESS_MISMATCH"):
            self.invoke()

    def test_concurrent_invocations_one_effect(self):
        results = []
        failures = []
        barrier = threading.Barrier(2)
        def call():
            try:
                barrier.wait()
                results.append(self.invoke()["verdict"])
            except BaseException as exc:
                failures.append(type(exc).__name__)
        threads = [threading.Thread(target=call) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual(failures, [])
        self.assertCountEqual(results, ["COMPLETE_FIXTURE", "HOLD_CONSUMED"])
        self.assertEqual(self.adapter.calls, 1)

    def test_clock_jump_before_effect(self):
        times = iter([self.now, "2026-10-12T00:26:20Z"])
        self.controller.wall_clock = lambda: next(times)
        self.assertEqual(self.invoke()["verdict"], "HOLD_CLOCK")
        self.assertEqual(self.adapter.calls, 0)

    def test_foreign_result_context_consumes(self):
        self.adapter.bad_receipt = True
        self.assertEqual(self.invoke()["verdict"], "HOLD_RESULT")
        self.assertEqual(self.invoke()["verdict"], "HOLD_CONSUMED")


class ContractTests(unittest.TestCase):
    def series(self):
        campaign = {"schema": "F2_CAMPAIGN_CANDIDATE_V1", "authority_status": "OWN_SIGNED",
                    "max_sample_seconds": 120, "campaign_id": "SYNTHETIC", "bulk_date": "2026-10-09",
                    "registry_sha256": H, "rule_sha256": H, "calendar_sha256": H, "eligible": 5784,
                    "cut_UTC": "2026-10-12T04:00:00Z",
                    "slots_UTC": ["2026-10-11T23:26:00Z", "2026-10-11T23:56:00Z", "2026-10-12T00:26:00Z"]}
        observations = []
        for slot, present in zip(campaign["slots_UTC"], [5449, 5500, 5679]):
            received = (datetime.fromisoformat(slot.replace("Z", "+00:00")) + timedelta(seconds=10)).isoformat()
            observations.append({"schema": "F2_OBSERVATION_CANDIDATE_V1", "slot_UTC": slot,
                                 "campaign_id": "SYNTHETIC", "bulk_date": "2026-10-09",
                                 "registry_sha256": H, "rule_sha256": H, "status": "COMPLETE",
                                 "started_UTC": slot, "received_UTC": received, "http_status": 200,
                                 "body_complete": True, "raw_sha256": H, "eligible": 5784,
                                 "present": present, "usable": present, "duplicates": 0, "conflicts": 0})
        return campaign, observations

    def test_series_bracket_without_absolute_crossing_claim(self):
        report = bulk_series(*self.series())
        self.assertEqual(report["preceding_observed_fail_UTC"], "2026-10-11T23:26:10+00:00")
        self.assertEqual(report["first_observed_pass_UTC"], "2026-10-11T23:56:10+00:00")
        self.assertFalse(report["absolute_first_crossing_known"])
        self.assertFalse(report["operational_GO"])

    def test_regression_not_hidden(self):
        campaign, obs = self.series()
        obs[-1]["present"] = obs[-1]["usable"] = 5449
        self.assertTrue(bulk_series(campaign, obs)["regression"])

    def test_gap_does_not_claim_30_minute_precision(self):
        campaign, obs = self.series()
        report = bulk_series(campaign, [obs[0], obs[2]])
        self.assertEqual(len(report["unknown_slots"]), 1)
        self.assertFalse(report["stable_observed_suffix"])

    def test_changed_registry_not_compared_as_same_cohort(self):
        campaign, obs = self.series()
        obs[-1]["registry_sha256"] = "b" * 64
        with self.assertRaisesRegex(Hold, "OBS_CONTEXT"):
            bulk_series(campaign, obs)

    def test_body_after_cut_invalid(self):
        campaign, obs = self.series()
        obs[-1]["received_UTC"] = campaign["cut_UTC"]
        with self.assertRaisesRegex(Hold, "OBS_TIME"):
            bulk_series(campaign, obs)

    def test_duplicate_observation_cannot_hide_failure(self):
        campaign, obs = self.series()
        with self.assertRaisesRegex(Hold, "DUPLICATE_OR_FOREIGN_SLOT"):
            bulk_series(campaign, obs + [obs[0]])

    def test_no_late_sample_catchup(self):
        campaign, obs = self.series()
        obs[0]["started_UTC"] = "2026-10-11T23:26:06Z"
        with self.assertRaisesRegex(Hold, "NO_CATCH_UP"):
            bulk_series(campaign, obs)

    def test_unsigned_campaign_cannot_become_f1_retry(self):
        campaign, obs = self.series()
        campaign["authority_status"] = "F1_OLD_SIGNATURE"
        with self.assertRaisesRegex(Hold, "CAMPAIGN_UNSIGNED"):
            bulk_series(campaign, obs)

    def capacity(self):
        return {"schema": "F3_CAPACITY_GATE_CANDIDATE_V1", "context": CONTEXT,
                "status": "VERIFIED", "documentary_authority": "VERIFIED",
                "inputs": {k: H for k in E6_INPUTS}, "chain": {k: H for k in CHAIN},
                "sets": {k: {name: H for name in SET_DOCUMENTS} for k in SETS}, "own_linux_review": "ACCEPTED"}

    def test_capacity_missing_raw_or_old_session_blocks(self):
        value = self.capacity()
        del value["inputs"]["veto_view-primary.raw"]
        with self.assertRaisesRegex(Hold, "CAPACITY_INPUTS"):
            capacity_gate(value, CONTEXT)
        value = self.capacity()
        with self.assertRaisesRegex(Hold, "CAPACITY_CONTEXT"):
            capacity_gate(value, dict(CONTEXT, session_date="2026-10-09"))

    def test_capacity_three_complete_sets_required(self):
        value = self.capacity()
        self.assertTrue(capacity_gate(value, CONTEXT))
        del value["sets"]["contingency_2"]["veto_view"]
        with self.assertRaisesRegex(Hold, "CAPACITY_SET_DOCUMENTS"):
            capacity_gate(value, CONTEXT)

    def test_decision_design_only_or_unknown_eta_is_no_go(self):
        row = {"id": "F6", "exists": True, "review": "DESIGN_ONLY", "proof": "PENDING",
               "authority": "PENDING", "critical": True, "when": None}
        result = decision_table([row])
        self.assertEqual(result["verdict"], "NO_GO")
        self.assertEqual(result["blockers"][0]["when"], "SEM_ETA_COMPROVADO")

    def test_all_closed_is_only_conditional_preparation(self):
        row = {"id": "F6", "exists": True, "review": "OWN_BYTES_ACCEPTED", "proof": "OWN_LINUX_ACCEPTED",
               "authority": "OWN_VALID", "critical": True, "artifact_sha256": H}
        result = decision_table([row])
        self.assertEqual(result["verdict"], "GO_PREPARATION_CONDITIONAL")
        self.assertFalse(result["Monday_entries_guaranteed"])

    def launch(self):
        return {"context": CONTEXT, "status": "COMPLETE", "request_sha256": H,
                "receipt_sha256": H, "view_UTC": "2026-10-12T10:45:00Z",
                "finished_UTC": "2026-10-12T10:39:00Z"}

    def test_c34_pending_persist_then_persist_without_collect_cycle(self):
        request = {"context": CONTEXT, "launch_request_sha256": H,
                   "required_roles": ["TREE", "CAPACITY", "LAUNCH"],
                   "not_before_UTC": "2026-10-12T10:46:00Z"}
        result = c34_dependencies(request, self.launch(), {"context": CONTEXT})
        self.assertEqual(result["collection_before_persist"], "PENDING_PERSIST")
        request["required_roles"].append("K12_COLLECT_COMPLETE")
        with self.assertRaisesRegex(Hold, "C34_CYCLE"):
            c34_dependencies(request, self.launch(), {"context": CONTEXT})

    def test_c35_separate_window_positive_and_boundary_refused(self):
        request = {"context": CONTEXT, "launch_request_sha256": H, "budget_seconds": 28,
                   "start_UTC": "2026-10-12T10:40:00Z", "end_UTC": "2026-10-12T10:43:00Z",
                   "view_UTC": "2026-10-12T10:45:00Z"}
        self.assertEqual(c35_window(request, self.launch(), "2026-10-12T10:40:00Z")["remaining_seconds"], 152)
        request["start_UTC"] = self.launch()["finished_UTC"]
        with self.assertRaisesRegex(Hold, "STOP_NO_POSITIVE_FLOOR"):
            c35_window(request, self.launch(), "2026-10-12T10:40:00Z")

    def night(self):
        envelope = {"schema": "H16_PREAUTH_CANDIDATE_V1", "context": CONTEXT,
                    "start_UTC": "2026-10-12T09:00:00Z", "end_UTC": "2026-10-12T09:05:00Z",
                    "budget_seconds": 120, "required_gates": ["DBR", "E6"], "authority_status": "NEW_MODEL_ACCEPTED"}
        question = {"request_sha256": digest(canonical(envelope)), "published_UTC": "2026-10-12T00:00:00Z"}
        owner = {"request_sha256": digest(canonical(envelope)), "question_sha256": digest(canonical(question)),
                 "signed_at_UTC": "2026-10-12T00:30:00Z", "literal": "Assino", "channel": "REGISTRO_PELA_FABLE"}
        gates = {k: {"context": CONTEXT, "status": "COMPLETE", "receipt_sha256": H} for k in ("DBR", "E6")}
        return envelope, question, owner, CONTEXT, gates, "2026-10-12T09:00:00Z"

    def test_h16_previous_evening_signature_no_new_question_at06(self):
        result = night_authorization(*self.night())
        self.assertFalse(result["new_owner_question_needed"])
        self.assertFalse(result["old_IND_reused"])

    def test_h16_signature_at22_or_missing_actual_gate_holds(self):
        args = self.night()
        args[2]["signed_at_UTC"] = "2026-10-12T01:00:00Z"
        with self.assertRaisesRegex(Hold, "H16_OWNER_UNAVAILABLE"):
            night_authorization(*args)
        args = self.night()
        args[4]["E6"]["status"] = "PENDING"
        with self.assertRaisesRegex(Hold, "H16_PREDECESSOR"):
            night_authorization(*args)

    def test_h16_unaccepted_new_model_is_not_authority(self):
        args = self.night()
        args[0]["authority_status"] = "DRAFT"
        args[1]["request_sha256"] = args[2]["request_sha256"] = digest(canonical(args[0]))
        args[2]["question_sha256"] = digest(canonical(args[1]))
        with self.assertRaisesRegex(Hold, "H16_AUTHORITY_PENDING"):
            night_authorization(*args)

    def test_duplicate_json_and_nonfinite_numbers_rejected(self):
        for data in (b'{"x":1,"x":2}', b'{"x":NaN}'):
            with self.assertRaises(Hold):
                strict_json(data)

    def test_uncertain_post_recovery_does_not_execute(self):
        data = b"allowed fixture verdict\n"
        row = {"id": 1, "body_sha256": digest(data), "author_id": 313137248, "context": CONTEXT,
               "created_at": "2026-10-12T00:30:00Z", "updated_at": "2026-10-12T00:30:00Z",
               "pages_complete": True, "get1": data, "get2": data}
        self.assertFalse(reconcile_publication(data, [row], 313137248, CONTEXT)["executor_repeated"])
        row["get2"] = b"edited"
        with self.assertRaisesRegex(Hold, "PUBLICATION_READBACK"):
            reconcile_publication(data, [row], 313137248, CONTEXT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
