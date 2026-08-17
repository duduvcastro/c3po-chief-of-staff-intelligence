import json

from app.main import b3_screener, database


database.initialize()
response = b3_screener.screen(refresh=True)
rows = [row for row in b3_screener._matrix_rows if row.get("our_tp") and row.get("buy_in")]

deduped = {}
for row in sorted(rows, key=lambda item: item.get("adtv_90d") or 0.0, reverse=True):
    deduped.setdefault(row["issuer"], row)
issuers = list(deduped.values())

tp_upside_cutoff = b3_screener._tp_upside_cutoff_percent(b3_screener._matrix_macro)
risk_cutoff = b3_screener._risk_cutoff(issuers)
gates = [
    ("tp_upside", lambda row: row["upside_percent"] >= tp_upside_cutoff),
    ("buy_in_distance", lambda row: row["price_vs_buy_in_percent"] <= 15.0),
    ("confidence", lambda row: row["valuation_confidence"] >= 70.0),
    ("dispersion", lambda row: row["method_dispersion_percent"] <= 35.0),
    ("low_risk", lambda row: row["risk_score"] < risk_cutoff),
]

remaining = issuers
sequential = []
for name, predicate in gates:
    before = len(remaining)
    remaining = [row for row in remaining if predicate(row)]
    sequential.append({"gate": name, "before": before, "after": len(remaining), "removed": before - len(remaining)})

individual = {
    name: sum(1 for row in issuers if predicate(row))
    for name, predicate in gates
}

selected = {item.symbol for item in response.items}
near_misses = []
for row in issuers:
    failures = [name for name, predicate in gates if not predicate(row)]
    if row["symbol"] in selected:
        continue
    near_misses.append({
        "symbol": row["symbol"],
        "failed": failures,
        "upside": round(row["upside_percent"], 1),
        "expected_return": round(row["expected_total_return_percent"], 1),
        "buy_in_distance": round(row["price_vs_buy_in_percent"], 1),
        "confidence": round(row["valuation_confidence"], 1),
        "dispersion": round(row["method_dispersion_percent"], 1),
        "risk": round(row["risk_score"], 1),
        "score": round(row["score"], 1),
    })

near_misses.sort(key=lambda row: (len(row["failed"]), -row["score"], -row["expected_return"]))
print(json.dumps({
    "methodology_version": response.methodology_version,
    "source_universe": response.universe_size,
    "eligible_rows": len(rows),
    "eligible_issuers": len(issuers),
    "tp_upside_cutoff": round(tp_upside_cutoff, 2),
    "risk_cutoff": round(risk_cutoff, 2),
    "selected": sorted(selected),
    "sequential": sequential,
    "individual_pass_counts": individual,
    "near_misses": near_misses[:15],
}, ensure_ascii=False, indent=2))
