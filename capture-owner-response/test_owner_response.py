"""Synthetic, offline cases; no owner signature, binder, host or child execution."""
import copy
import json
import unittest
import owner_response as m


class ResponseTests(unittest.TestCase):
    def setUp(self):
        self.context = dict(session="2026-10-08", run_id="37612765727", run_attempt=1,
                            nonce="a"*32, sheet_sha256="b"*64, question_body_sha256="c"*64,
                            prepared_at_utc="2026-10-08T11:46:00Z", question_created_at="2026-10-08T11:47:00Z",
                            not_before="2026-10-08T11:50:00Z", not_after="2026-10-08T12:30:00Z")
        body = {k:self.context[k] for k in ("session", "run_id", "run_attempt", "nonce", "sheet_sha256")}
        body.update(schema="CAPTURE_OWNER_ANSWER_V1", answer="Assino")
        self.comment = dict(id=1234, issue_url=m.ISSUE_URL,
                            url=m.ISSUE_URL.rsplit("/issues/",1)[0]+"/issues/comments/1234",
                            user=dict(login=m.OWNER_LOGIN,id=m.OWNER_ID,type="User"), author_association="OWNER",
                            performed_via_github_app=None, created_at="2026-10-08T12:00:00Z",
                            updated_at="2026-10-08T12:00:00Z", body=json.dumps(body))

    def validate(self, comment=None, **kwargs):
        c=self.comment if comment is None else comment
        return m.validate_owner_response(c, copy.deepcopy(c), self.context, "2026-10-08T12:01:00Z", **kwargs)

    def test_match_returns_no_signature(self):
        r=self.validate();self.assertFalse(r["is_operational_authority"])
        self.assertFalse(r["independent_human_crypto_proof"])
        self.assertEqual(r["status"],"MATCHED_DIRECT_COMMENT_NOT_SIGNED")

    def test_readback_edited(self):
        other=copy.deepcopy(self.comment);other["body"]="changed"
        with self.assertRaisesRegex(m.Refused,"READBACK_CHANGED"):
            m.validate_owner_response(self.comment,other,self.context,"2026-10-08T12:01:00Z")

    def test_duplicate_json_field(self):
        c=copy.deepcopy(self.comment);c["body"]=c["body"][:-1]+', "answer":"Assino"}'
        with self.assertRaisesRegex(m.Refused,"DUPLICATE_OWNER_FIELD"):self.validate(c)

    def test_replay(self):
        with self.assertRaisesRegex(m.Refused,"REPLAY"):self.validate(used_comment_ids=(1234,))

    def test_fable_report_is_not_owner_answer(self):
        c=copy.deepcopy(self.comment);c["body"]='Fable: dono respondeu "Assino"'
        with self.assertRaises(m.Refused):self.validate(c)

    def test_missing_app_attribution_is_not_null(self):
        c=copy.deepcopy(self.comment);del c["performed_via_github_app"]
        with self.assertRaisesRegex(m.Refused,"FORWARDED_OR_APP"):self.validate(c)

    def test_negative_author_edit_context_and_deadline(self):
        changes=[("user",dict(login=m.OWNER_LOGIN,id=1,type="User")),
                 ("user",dict(login=m.OWNER_LOGIN,id=m.OWNER_ID,type="Bot")),
                 ("user",dict(login="someone_else",id=m.OWNER_ID,type="User")),
                 ("author_association","COLLABORATOR"),("performed_via_github_app",{}),
                 ("updated_at","2026-10-08T12:00:01Z"),("id",True),
                 ("issue_url",m.ISSUE_URL.replace("429","428")),("body","Assino"),
                 ("body",'{}'),("created_at","2026-10-08T12:30:01Z"),
                 ("created_at","2026-10-08T11:49:59Z")]
        for key,value in changes:
            with self.subTest(key=key,value=value):
                c=copy.deepcopy(self.comment);c[key]=value
                with self.assertRaises(m.Refused):self.validate(c)
        for key,value in [("session","2026-10-09"),("run_id","37612765728"),("run_attempt",2),
                          ("run_attempt",True),("nonce","d"*32),("sheet_sha256","e"*64),
                          ("answer","assino"),("answer","Assino todas")]:
            with self.subTest(body_key=key):
                c=copy.deepcopy(self.comment);v=json.loads(c["body"]);v[key]=value;c["body"]=json.dumps(v)
                with self.assertRaises(m.Refused):self.validate(c)

    def test_observation_after_deadline(self):
        with self.assertRaisesRegex(m.Refused,"ORDER_OR_DEADLINE"):
            m.validate_owner_response(self.comment,self.comment,self.context,"2026-10-08T12:30:01Z")

    def test_bad_context_cannot_expand_authority(self):
        for key,value in [("session","2026-10-09"),("run_attempt",2),("nonce","a"),
                          ("not_after","2026-10-08T13:00:00Z"),("prepared_at_utc","2026-10-08T12:01:00Z")]:
            with self.subTest(key=key):
                c=copy.deepcopy(self.context);c[key]=value
                with self.assertRaises(m.Refused):
                    m.validate_owner_response(self.comment,self.comment,c,"2026-10-08T12:01:00Z")


if __name__ == "__main__":
    unittest.main()
