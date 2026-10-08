import copy
import unittest
from common import Hold, canonical, digest, instant
import h16


def h(v): return digest(v.encode())


def example():
    ctx = {"model": "SERVER_EPOCH_V2", "epoch": "TEST_NEW_EPOCH_20261012", "session": "2026-10-12", "lane": "AM", "release_sha256": h("release")}
    selectors, gates = {}, {}
    for role in ("commit_result", "publish_launch", "CAPACITY_DAY", "K12_FINAL"):
        other = dict(ctx, lane="S" if role in ("commit_result", "publish_launch") else "CAPACITY")
        selectors[role] = {"context": other, "operation": role, "producer_sha256": h(role), "earliest_UTC": "2026-10-11T22:00:00Z",
                           "latest_UTC": "2026-10-12T04:00:00Z", "max_age_seconds": 43200}
        detail = {"status": "VERIFIED", "documentary_authority": "VERIFIED", "capacity_gate_verified": True} if role == "CAPACITY_DAY" else (
            {"collection": "VERIFIED", "manifest_verified": True} if role == "K12_FINAL" else {})
        gates[role] = canonical({"schema": "SERVER_FAMILY_RECEIPT_V2", "context": other, "operation": role, "producer_sha256": h(role),
                                 "status": "COMPLETE", "request_sha256": h(role+"req"), "started_UTC": "2026-10-12T02:00:00Z",
                                 "finished_UTC": "2026-10-12T02:01:00Z", "detail": detail})
    req = {"schema": "SERVER_FAMILY_REQUEST_V2", "context": ctx, "operation": "F5_H16_READ", "pins": {"model_review_sha256": h("review")},
           "start_UTC": "2026-10-12T09:00:00Z", "end_UTC": "2026-10-12T09:02:01Z", "budget_seconds": 120,
           "required_gates": sorted(selectors), "payload": {"reader_id": "H16_OWN_READER_V2", "reader_source_sha256": h("reader"),
                                                            "receipt_selectors": selectors, "max_lateness_seconds": 5}}
    question = {"schema": "SERVER_OWNER_QUESTION_V2", "request_sha256": digest(canonical(req)), "published_UTC": "2026-10-11T23:00:00Z"}
    owner = {"schema": "SERVER_OWNER_RESPONSE_V2", "request_sha256": digest(canonical(req)), "question_sha256": digest(canonical(question)),
             "literal": "Assino", "channel": "REGISTRO_PELA_FABLE", "signed_at_UTC": "2026-10-11T23:01:00Z"}
    auth = {"schema": "H16_MODEL_AUTHORITY_V2", "context": ctx, "request_sha256": digest(canonical(req)), "reader_id": "H16_OWN_READER_V2",
            "reader_source_sha256": h("reader"), "model_review_sha256": h("review"), "required_selectors_sha256": digest(canonical(selectors))}
    return req, question, owner, auth, gates


class Reader:
    reader_id, source_sha256 = "H16_OWN_READER_V2", h("reader")
    calls = 0
    def read_once(self, req, binding):
        self.calls += 1
        return {"schema": "H16_READER_RESULT_V2", "status": "COMPLETE", "context": req["context"], "request_sha256": binding["request_sha256"],
                "actual_receipts": binding["actual_receipts"], "checks": {"fixture_reader": True}}


class TestH16(unittest.TestCase):
    def test_prior_specific_signature_actual_receipts_no_owner_question(self):
        args = example(); reader = Reader()
        result = h16.execute(*args, clock=lambda: "2026-10-12T09:00:00Z", recheck=lambda: None, reader=reader)
        self.assertFalse(result["owner_question_sent"]); self.assertEqual(reader.calls, 1)
        self.assertEqual(set(result["actual_receipts"]), set(args[4]))
    def test_missing_real_gate_refuses_before_reader(self):
        args = example(); del args[4]["K12_FINAL"]
        reader = Reader()
        with self.assertRaisesRegex(Hold, "H16_GATE_SET"): h16.execute(*args, clock=lambda: "2026-10-12T09:00:00Z", recheck=lambda: None, reader=reader)
        self.assertEqual(reader.calls, 0)
    def test_not_ready_and_partial_collection_are_not_final_gates(self):
        import json
        for role, detail in (("CAPACITY_DAY", {"status":"NOT_READY","documentary_authority":"VERIFIED","capacity_gate_verified":True}),
                             ("K12_FINAL", {"collection":"WRITER_PUBLISHED_BYTES_ONLY","manifest_verified":False})):
            args=example(); receipt=json.loads(args[4][role]); receipt["detail"]=detail; args[4][role]=canonical(receipt)
            with self.assertRaises(Hold): h16.authorize(*args, instant("2026-10-12T09:00:00Z"))
    def test_wrong_release_old_epoch_or_wrong_session_refused(self):
        import json
        for key,bad in (("release_sha256",h("oldrelease")),("session","2026-10-09"),("epoch","R2D2-V2-SHADOW-2026-10-05")):
            args=example(); row=json.loads(args[4]["commit_result"]); row["context"][key]=bad; args[4]["commit_result"]=canonical(row)
            with self.assertRaises(Hold): h16.authorize(*args, instant("2026-10-12T09:00:00Z"))
    def test_no_signature_from_22_to_07_or_after_2145(self):
        for signed in ("2026-10-12T01:00:00Z","2026-10-12T08:59:00Z","2026-10-12T00:45:01Z"):
            args=example(); args[2]["signed_at_UTC"]=signed
            with self.assertRaises(Hold): h16.authorize(*args, instant("2026-10-12T09:00:00Z"))
    def test_non_assino_and_another_question_refused(self):
        for key,bad in (("literal","Não"),("question_sha256",h("other"))):
            args=example();args[2][key]=bad
            with self.assertRaises(Hold): h16.authorize(*args, instant("2026-10-12T09:00:00Z"))
    def test_signature_does_not_authorize_changed_selectors(self):
        args=example();args[0]["payload"]["receipt_selectors"]["CAPACITY_DAY"]["producer_sha256"]=h("other")
        with self.assertRaises(Hold): h16.authorize(*args, instant("2026-10-12T09:00:00Z"))
    def test_stale_future_or_catchup_refused(self):
        for now in ("2026-10-12T08:59:59Z","2026-10-12T09:00:06Z","2026-10-12T09:02:01Z"):
            with self.assertRaises(Hold): h16.authorize(*example(), instant(now))
    def test_ind_historical_is_not_h16_model(self):
        args=example();args[3]["schema"]="IND"
        with self.assertRaisesRegex(Hold,"H16_AUTHORITY_BINDING"): h16.authorize(*args, instant("2026-10-12T09:00:00Z"))
    def test_actual_receipts_are_derived_not_pre_signed_future_hashes(self):
        args=example(); original=h16.authorize(*args, instant("2026-10-12T09:00:00Z"))
        self.assertNotIn("receipt_sha256",str(args[0]["payload"]["receipt_selectors"]))
        self.assertEqual(original["actual_receipts"]["commit_result"],digest(args[4]["commit_result"]))


if __name__ == "__main__": unittest.main()
