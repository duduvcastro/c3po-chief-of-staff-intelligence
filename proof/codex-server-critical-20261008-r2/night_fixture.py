"""New coherent synthetic Sunday night, never operational originals or signatures.

Helper construction recomputes the seven chains, thirteen inputs and all set
pins from the stated fixture timestamps. Closed family suites are not run.
"""
from datetime import timedelta
import capacity as c
from common import canonical,digest,hash_value,instant,strict

def h(text): return digest(text.encode())
def doc(kind, body): return canonical({"schema":"R2D2_DOCUMENTARY_EVIDENCE_V1","kind":kind,"state":"ISSUED","body":body})


def example():
    ctx={"model":"SERVER_EPOCH_V2","epoch":"TEST_F6_NIGHT_20261012","session":"2026-10-12","lane":"CAPACITY","release_sha256":h("release")}
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
    windows={phase:{"not_before":"2026-10-11T23:00:00Z","not_after":"2026-10-11T23:30:00Z"} for phase in c.PHASES}
    causal=["FIXTURE%04d"%i for i in range(600)]
    commitment={"schema":"CAPACITY_CAUSAL_COMMITMENT_V2","context":ctx,"order_sha256":hash_value(order),"list_sha256":digest(canonical(causal)),"list_count":len(causal)}
    publication=doc("PUBLICATION",{"context":ctx,"phase":"bar_manifest","template_sha256":hash_value(tmpl),"role":"FABLE","published_at_UTC":"2026-10-11T22:30:00Z"})
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
        view_at=["2026-10-11T23:45:00Z","2026-10-12T00:15:00Z","2026-10-12T00:45:00Z"][index-1]
        view=canonical({"schema":"CAPACITY_VETO_VIEW_V2","context":ctx,"order_sha256":hash_value(order),"owner_veto":False,"revoked_shas":[],"status":"VERIFIED",
                        "observed_UTC":view_at,"valid_until_UTC":(instant(view_at)+timedelta(seconds=10)).isoformat()})
        config=canonical({"schema":"CAPACITY_CONFIG_V2","context":ctx,"window":name,"chain_pins":pins,"input_pins":{k:digest(v) for k,v in inputs.items()},"veto_view_sha256":digest(view)})
        req=canonical({"schema":"R2D2_CAPACITY_DAY_ONCE_REQUEST_V2","context":ctx,"window":name,"window_slot":index,"cutoff_UTC":"2026-10-12T13:20:00+00:00",
                       "start_UTC":(instant(view_at)-timedelta(seconds=60)).isoformat(),"view_UTC":view_at,"end_UTC":(instant(view_at)+timedelta(seconds=60)).isoformat(),
                       "contract_sha256":digest(inputs["CONTRACT.json"]),"template_sha256":hash_value(tmpl),"capacity_config_sha256":digest(config)})
        dispatch=canonical({"schema":"CAPACITY_DISPATCH_GO_V2","context":ctx,"decision":"GO","request_sha256":digest(req),"automatic_retry":False})
        bundle["set_specs"][name]={"view_raw":view,"request_raw":req,"dispatch_go_raw":dispatch,"config_raw":config}
    return bundle

