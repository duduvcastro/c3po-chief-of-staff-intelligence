"""Pure reused SYNTHETIC ImageGo fixture helper; no old tests imported."""
import finite_batch as c
def evidence(op,t):
    w={"epoch":c.EPOCH,"day":c.DAY,"phase":op,"not_before":t["not_before"],"not_after":t["not_after"]}
    names=("signed_epoch_order_sha","release_sha","policy_sha","package_sha","calendar_pin_sha",
           "recertification_receipt_sha","wind_down_28_receipt_sha","template_sha","input_receipts_sha","phase_window_sha")
    b={k:c.sha(("SYNTHETIC_"+k).encode()) for k in names};b["phase_window_sha"]=c.sha(c.image_canonical(w))
    p={"identity":{"epoch":c.EPOCH,"first_session":c.DAY},"daily":{"day":c.DAY},"phase":op,"bindings":b,
       "consumer_capacity_binding":"UNBOUND","automatic_retry":False}
    proposed={"status":"BOUND_FOR_REVIEW_ONLY","execution_authorized":False,"missing_bindings":[],"proposal":p,
              "proposal_sha":c.sha(c.image_canonical(p)),"diff":[{"fixture":"avaliação sintética"}]}
    go={"decision":"GO","epoch":c.EPOCH,"first_session":c.DAY,"day":c.DAY,"phase":op,"proposal_sha":proposed["proposal_sha"],
        "signed_order_sha":b["signed_epoch_order_sha"],"template_sha":b["template_sha"],"mode":"INDIVIDUAL",
        "not_before":t["not_before"],"not_after":t["not_after"],"automatic_retry":False,"authority_receipts":{"phase_window":w}}
    labels=["CODEX","FABLE","DUDU","ACT_B","B_CODEX","B_FABLE","B_DUDU","TEMPLATE","GO:"+op]
    if op in ("install_release","activate"):labels.append("OWNER_GO:"+op)
    docs=tuple((k,c.canonical({"fixture":"SYNTHETIC_NOT_SIGNATURE","label":k,"go_sha":c.sha(c.image_canonical(go)),
                               "role":"DUDU" if k.startswith("OWNER_GO:") else "FABLE"})) for k in labels)
    return c.ImageGo(c.image_canonical(go),c.image_canonical(proposed),docs)
