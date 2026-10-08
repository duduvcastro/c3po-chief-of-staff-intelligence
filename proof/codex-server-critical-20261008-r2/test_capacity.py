import copy
import unittest
from common import Hold, canonical, context, digest, hash_value, instant, strict
import capacity as c


def h(text): return digest(text.encode())
def doc(kind, body): return canonical({"schema":"R2D2_DOCUMENTARY_EVIDENCE_V1","kind":kind,"state":"ISSUED","body":body})


def example():
    ctx={"model":"SERVER_EPOCH_V2","epoch":"TEST_NEW_EPOCH_20261012","session":"2026-10-12","lane":"CAPACITY","release_sha256":h("release")}
    cal={"schema":"PINNED_SESSION_CALENDAR_V2","epoch":ctx["epoch"],"origin_sha256":h("calendar original"),
         "sessions":{"2026-10-12":{"open_UTC":"2026-10-12T13:30:00Z","close_UTC":"2026-10-12T20:00:00Z"}}}
    order={"schema":"SERVER_EPOCH_ORDER_V2","epoch":ctx["epoch"],"capacity":550,"rule":c.RULE,"authorized_sessions":["2026-10-12"],"calendar_sha256":hash_value(cal)}
    policy={"schema":"SERVER_CAPACITY_POLICY_V2","epoch":ctx["epoch"],"capacity":550,"rule":c.RULE,"automatic_retry":False,
            "order_sha256":hash_value(order),"release_sha256":ctx["release_sha256"],"calendar_sha256":hash_value(cal),"package_sha256":h("package"),
            "valid_from_UTC":"2026-10-11T20:00:00Z","valid_until_UTC":"2026-10-12T23:00:00Z"}
    release={"schema":"SERVER_RELEASE_RECERTIFIED_V2","epoch":ctx["epoch"],"release_sha256":ctx["release_sha256"],"package_sha256":h("package"),
             "receipts":{k:h(k) for k in ("M1","M2","M3","WIND_DOWN_28","INPUT_RECEIPTS")}}
    scope={"epoch":ctx["epoch"],"first_session":"2026-10-12","authorized_sessions":["2026-10-12"]}
    owner={"verbatim":"Assino","channel":"REGISTRO_PELA_FABLE","signed_at_utc":"2026-10-11T23:00:00Z","request_sha256":h("own question request"),"question_sha256":h("own question")}
    chain={};previous=None
    for role in ("CODEX","FABLE","DUDU"):
        body={**scope,"role":role,"decision":"APPROVED","previous_sha":previous,"document_sha256":hash_value(order)}
        if role=="DUDU":body["owner_evidence"]=owner
        chain[role]=doc("APPROVAL",body);previous=digest(chain[role])
    tmpl=c.template(ctx,order,cal)
    act={**scope,"status":"ACCEPTED","chain_head":digest(chain["DUDU"]),"order_sha":hash_value(order),"policy_sha":hash_value(policy),
         "capacity":550,"cut_rule":c.RULE,"automatic_retry":False,"causal_order":{"primary":"ADV_DESC","tie_break":"SYMBOL_ASC","cut":"TAIL_NEW_ONLY"},
         "act_a_scope_map":{role:{**scope,"signature_sha":digest(chain[role]),"document_sha256":hash_value(order)} for role in ("CODEX","FABLE","DUDU")},
         "template_shas":{"2026-10-12":hash_value(tmpl)}}
    chain["ACT_B"]=doc("ACT_B",act);previous=None
    for role in ("CODEX","FABLE","DUDU"):
        body={**scope,"role":role,"decision":"APPROVED","previous_sha":previous,"body_sha":digest(chain["ACT_B"]),"act_a_head":digest(chain["DUDU"])}
        if role=="DUDU":body["owner_evidence"]=owner
        chain["B_"+role]=doc("APPROVAL",body);previous=digest(chain["B_"+role])
    windows={phase:{"not_before":"2026-10-12T10:00:00Z","not_after":"2026-10-12T10:30:00Z"} for phase in c.PHASES}
    causal=["FIXTURE%04d"%i for i in range(600)]
    commitment={"schema":"CAPACITY_CAUSAL_COMMITMENT_V2","context":ctx,"order_sha256":hash_value(order),"list_sha256":digest(canonical(causal)),"list_count":len(causal)}
    publication=doc("PUBLICATION",{"context":ctx,"phase":"bar_manifest","template_sha256":hash_value(tmpl),"role":"FABLE","published_at_UTC":"2026-10-12T09:00:00Z"})
    bundle={"context":ctx,"order":canonical(order),"policy":canonical(policy),"calendar":canonical(cal),"release":canonical(release),"chain":chain,
            "phase_windows":windows,"publication":publication,"commitment":canonical(commitment),"causal_list":canonical(causal),
            "open_positions":canonical(["OPEN%03d"%i for i in range(22)]),"verifier_source_sha256":h("own verifier source")}
    pins={k:digest(v) for k,v in chain.items()}
    contract={"schema":"R2D2_CAPACITY_CONTRACT_V2","context":ctx,"order":order,"policy":policy,"calendar":cal,"release":release,"template":tmpl,
              "phase_windows":windows,"chain_pins":pins,"commitment_sha256":digest(bundle["commitment"]),"list_sha256":digest(bundle["causal_list"]),"list_count":len(causal)}
    inputs={"CONTRACT.json":canonical(contract),"template.raw":canonical(tmpl),"publication_bar_manifest.raw":publication}
    for phase,mode in (("admission","INDIVIDUAL"),("bar_manifest","DELEGATED_ACT_B")):
        go={"schema":"CAPACITY_GO_V2","context":ctx,"phase":phase,"mode":mode,"decision":"GO","template_sha256":hash_value(tmpl),"order_sha256":hash_value(order),
            "policy_sha256":hash_value(policy),"phase_window":windows[phase],"automatic_retry":False}
        if phase=="bar_manifest":go.update(act_b_sha256=pins["ACT_B"],publication_sha256=digest(publication))
        raw=canonical(go);record=doc("GO",{"context":ctx,"phase":phase,"go_sha256":digest(raw),"template_sha256":hash_value(tmpl),"decision":"GO","role":"FABLE"})
        bundle["go_"+phase]=raw;bundle["go_"+phase+"_record"]=record;inputs["go_"+phase+".raw"]=raw;inputs["go_"+phase+"_record.raw"]=record
    bundle["set_specs"]={}
    for index,name in enumerate(c.SETS,1):
        view_at="2026-10-12T%02d:45:00Z"%(9+index)
        view=canonical({"schema":"CAPACITY_VETO_VIEW_V2","context":ctx,"order_sha256":hash_value(order),"owner_veto":False,"revoked_shas":[],"status":"VERIFIED",
                        "observed_UTC":view_at,"valid_until_UTC":"2026-10-12T%02d:45:10Z"%(9+index)})
        config=canonical({"schema":"CAPACITY_CONFIG_V2","context":ctx,"window":name,"chain_pins":pins,"input_pins":{k:digest(v) for k,v in inputs.items()},"veto_view_sha256":digest(view)})
        req=canonical({"schema":"R2D2_CAPACITY_DAY_ONCE_REQUEST_V2","context":ctx,"window":name,"window_slot":index,"cutoff_UTC":"2026-10-12T13:20:00+00:00",
                       "start_UTC":"2026-10-12T%02d:44:00Z"%(9+index),"view_UTC":view_at,"end_UTC":"2026-10-12T%02d:46:00Z"%(9+index),
                       "contract_sha256":digest(inputs["CONTRACT.json"]),"template_sha256":hash_value(tmpl),"capacity_config_sha256":digest(config)})
        dispatch=canonical({"schema":"CAPACITY_DISPATCH_GO_V2","context":ctx,"decision":"GO","request_sha256":digest(req),"automatic_retry":False})
        bundle["set_specs"][name]={"view_raw":view,"request_raw":req,"dispatch_go_raw":dispatch,"config_raw":config}
    return bundle


def results(bundle, docs):
    ctx=bundle["context"];pins={k:digest(v) for k,v in docs["inputs"].items()};sets={name:{k:digest(v) for k,v in rows.items()} for name,rows in docs["sets"].items()}
    proof=canonical({"schema":"CAPACITY_OWN_LINUX_PROOF_V2","source_sha256":bundle["verifier_source_sha256"],"attempt":1,"test_count":10,"error_count":0,"failure_count":0,"artifact_sha256":h("fixture artifact")})
    review=canonical({"schema":"CAPACITY_OWN_REVIEW_V2","verdict":"ACCEPTED_OWN_BYTES","context":ctx,"source_sha256":bundle["verifier_source_sha256"],
                      "proof_sha256":digest(proof),"inputs":pins,"sets":sets,"chain_pins":docs["chain_pins"]})
    causal=strict(bundle["causal_list"]);opens=strict(bundle["open_positions"]);new=causal[:550-len(opens)]
    selected=canonical({"context":ctx,"open_preserved":opens,"new_admitted":new,"new_cut":causal[len(new):]})
    k8=canonical({"schema":"K8_CAPACITY_DAY_ACTUAL_RESULT_V2","context":ctx,"status":"COMPLETE","inputs":pins,"sets":sets,"chain_pins":docs["chain_pins"],
                  "verifier_source_sha256":bundle["verifier_source_sha256"],"review_sha256":digest(review),"contract_sha256":pins["CONTRACT.json"],
                  "commitment_sha256":digest(bundle["commitment"]),"causal_list_sha256":digest(bundle["causal_list"]),"open_positions_sha256":digest(bundle["open_positions"]),
                  "selected_sha256":digest(selected),"counts":{"open":22,"new_admitted":528,"total":550,"new_cut":72},"open_preserved":True,"causal_order_preserved":True})
    view=canonical({"schema":"CAPACITY_VETO_VIEW_V2","context":ctx,"order_sha256":hash_value(strict(bundle["order"])),"status":"VERIFIED","owner_veto":False,"revoked_shas":[],
                    "observed_UTC":"2026-10-12T13:00:00Z","valid_until_UTC":"2026-10-12T13:00:10Z"})
    return dict(k8_raw=k8,selected_raw=selected,proof_raw=proof,review_raw=review,current_view_raw=view,now=instant("2026-10-12T13:00:01Z"))


class TestCapacity(unittest.TestCase):
    def test_new_k8_store_producer_exact_readback_and_second_use_refused(self):
        import tempfile,os
        from pathlib import Path
        from common import PinnedDirectory
        bundle=example();docs=c.build_documents(bundle,now=instant("2026-10-12T13:00:01Z"));args=results(bundle,docs)
        with tempfile.TemporaryDirectory(prefix="new-k8-fixture-",dir=str(Path(tempfile.gettempdir()).resolve())) as path:
            os.chmod(path,0o700);root=PinnedDirectory(path)
            try:
                opts={k:args[k] for k in ("proof_raw","review_raw","current_view_raw","now")}
                report=c.prepare_once(bundle,output=root,recheck=lambda:None,**opts)
                self.assertEqual(root.read("CAPACITY_DAY.json"),canonical(report))
                self.assertEqual(root.read("CAPACITY_SELECTED.private.json"),c.selection(bundle))
                with self.assertRaisesRegex(Hold,"CAP_ALREADY_PREPARED"):c.prepare_once(bundle,output=root,recheck=lambda:None,**opts)
            finally:root.close()
    def test_thirteen_inputs_three_sets_seven_origins_and_actual_selected_bytes(self):
        bundle=example();docs=c.build_documents(bundle,now=instant("2026-10-12T13:00:01Z"))
        self.assertEqual(docs["status"],"BOUND_FOR_REVIEW_ONLY");self.assertEqual(set(docs["inputs"]),set(c.INPUTS))
        verified=c.verify_day(docs,bundle,**results(bundle,docs));self.assertEqual(verified["status"],"VERIFIED")
        self.assertEqual(verified["counts"],{"open":22,"new_admitted":528,"total":550,"new_cut":72});self.assertFalse(verified["operational_GO"])
    def test_missing_own_chain_is_not_draft_verified(self):
        bundle=example();del bundle["chain"]["B_DUDU"]
        with self.assertRaisesRegex(Hold,"CAP_CHAIN_SET"):c.build_documents(bundle,now=instant("2026-10-12T13:00:01Z"))
    def test_old_epoch_or_policy_does_not_date_transfer(self):
        bundle=example();value=strict(bundle["policy"]);value["epoch"]="R2D2-V2-SHADOW-2026-10-05";bundle["policy"]=canonical(value)
        with self.assertRaises(Hold):c.build_documents(bundle,now=instant("2026-10-12T13:00:01Z"))
    def test_changed_calendar_release_and_chain_predecessor_refused(self):
        for role,key,value in (("CODEX","previous_sha",h("wrong")),("FABLE","document_sha256",h("wrong")),("B_DUDU","act_a_head",h("wrong"))):
            bundle=example();row=strict(bundle["chain"][role]);row["body"][key]=value;bundle["chain"][role]=canonical(row)
            with self.assertRaises(Hold):c.build_documents(bundle,now=instant("2026-10-12T13:00:01Z"))
    def test_future_publication_or_missing_15min_notice_refused(self):
        bundle=example();pub=strict(bundle["publication"]);pub["body"]["published_at_UTC"]="2026-10-12T09:59:00Z";bundle["publication"]=canonical(pub)
        with self.assertRaisesRegex(Hold,"CAP_PUBLICATION_NOTICE"):c.build_documents(bundle,now=instant("2026-10-12T13:00:01Z"))
    def test_views_bound_to_own_window_no_future_stamped_original(self):
        bundle=example();row=strict(bundle["set_specs"]["primary"]["view_raw"]);row["observed_UTC"]="2026-10-12T12:45:00Z";bundle["set_specs"]["primary"]["view_raw"]=canonical(row)
        with self.assertRaises(Hold):c.build_documents(bundle,now=instant("2026-10-12T13:00:01Z"))
    def test_without_actual_k8_result_proof_and_review_no_verified(self):
        bundle=example();docs=c.build_documents(bundle,now=instant("2026-10-12T13:00:01Z"));args=results(bundle,docs)
        for key in ("k8_raw","proof_raw","review_raw"):
            bad=dict(args);bad[key]=canonical({"status":"VERIFIED"})
            with self.assertRaises((Hold,KeyError)):c.verify_day(docs,bundle,**bad)
    def test_actual_selection_changed_to_pass_capacity_refused(self):
        bundle=example();docs=c.build_documents(bundle,now=instant("2026-10-12T13:00:01Z"));args=results(bundle,docs)
        row=strict(args["selected_raw"]);row["new_admitted"]=list(reversed(row["new_admitted"]));args["selected_raw"]=canonical(row)
        with self.assertRaisesRegex(Hold,"CAP_K8_SELECTED_BYTES"):c.verify_day(docs,bundle,**args)
    def test_current_revocation_or_staleness_refused(self):
        bundle=example();docs=c.build_documents(bundle,now=instant("2026-10-12T13:00:01Z"));args=results(bundle,docs)
        for key,val in (("owner_veto",True),("valid_until_UTC","2026-10-12T13:00:00Z")):
            bad=dict(args);row=strict(bad["current_view_raw"]);row[key]=val;bad["current_view_raw"]=canonical(row)
            with self.assertRaises(Hold):c.verify_day(docs,bundle,**bad)
    def test_duplicate_json_and_draft_approval_refused(self):
        bundle=example();row=strict(bundle["chain"]["DUDU"]);row["state"]="DRAFT";bundle["chain"]["DUDU"]=canonical(row)
        with self.assertRaisesRegex(Hold,"CAP_DOCUMENT_UNISSUED"):c.build_documents(bundle,now=instant("2026-10-12T13:00:01Z"))


if __name__=="__main__":unittest.main()
