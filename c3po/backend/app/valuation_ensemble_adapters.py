"""Read-only adapters over the canonical statement/price/source stores.

SEC/CVM acceptance, source capture and price publication are distinct clocks. In
particular, a price captured in 2026 is not made available in 2021 merely because
its economic session was in 2021. There is no provider-fundamentals fallback.
"""
from __future__ import annotations

import math
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Mapping, Protocol, Sequence
from zoneinfo import ZoneInfo

from .valuation_ensemble_inputs import AnalystTarget, CompanyInputs, Evidence, NotEvaluable, OfficialFact, Price, canonical_hash, number, utc


@dataclass(frozen=True)
class CompanyRequest:
    market: str
    symbol: str
    as_of: datetime
    basis_id: str


@dataclass(frozen=True)
class AdaptedCompany:
    company: CompanyInputs | None
    analyst_targets: tuple[AnalystTarget, ...]
    provenance: dict[str, Any]


class Sources(Protocol):
    def filings(self, market: str) -> Sequence[Mapping[str, Any]]: ...
    def facts(self, market: str, issuer: str, as_of: datetime) -> Sequence[Mapping[str, Any]]: ...
    def price_series(self, market: str, symbol: str, as_of: datetime) -> Mapping[str, Any]: ...
    def consensus_snapshot(self, market: str, symbol: str) -> Mapping[str, Any] | None: ...


class CanonicalSources:
    """Only public canonical reader methods are called; no source refresh or SQL writes."""
    def __init__(self, statement_store: Any, price_reader: Any, database: Any) -> None:
        self.statements, self.prices, self.database = statement_store, price_reader, database

    def filings(self, market: str) -> Sequence[Mapping[str, Any]]:
        return self.statements.filings("B3" if market == "B3" else "US",
                                       source="cvm_dados_abertos" if market == "B3" else "sec_edgar")

    def facts(self, market: str, issuer: str, as_of: datetime) -> Sequence[Mapping[str, Any]]:
        return self.statements.vintages("B3" if market == "B3" else "US", issuer,
                                        accepted_at_or_before=utc(as_of),
                                        source="cvm_dados_abertos" if market == "B3" else "sec_xbrl_companyfacts")

    def price_series(self, market: str, symbol: str, as_of: datetime) -> Mapping[str, Any]:
        return self.prices.series(market, symbol, available_before=utc(as_of))

    def consensus_snapshot(self, market: str, symbol: str) -> Mapping[str, Any] | None:
        symbol_key = hashlib.sha256(symbol.strip().upper().encode()).hexdigest()[:16]
        return self.database.latest_analysis_snapshot("valuation_pit_source", f"{market}_FMP_TARGETS_{symbol_key}")


class BundleSources:
    """The same adapters can read an offline export, with original row hashes preserved."""
    def __init__(self, bundle: Mapping[str, Any]) -> None:
        if not isinstance(bundle, Mapping) or bundle.get("schema") != "VALUATION-ENSEMBLE-SOURCE-EXPORT-v1":
            raise NotEvaluable("unsupported_source_export_schema")
        self.bundle = bundle

    def filings(self, market: str) -> Sequence[Mapping[str, Any]]:
        return self.bundle.get("filings", [])

    def facts(self, market: str, issuer: str, as_of: datetime) -> Sequence[Mapping[str, Any]]:
        return self.bundle.get("facts", [])

    def price_series(self, market: str, symbol: str, as_of: datetime) -> Mapping[str, Any]:
        return self.bundle.get("price_series", {}).get(f"{market}:{symbol}", {"status": "no_vintage"})

    def consensus_snapshot(self, market: str, symbol: str) -> Mapping[str, Any] | None:
        return self.bundle.get("consensus_snapshots", {}).get(f"{market}:{symbol}")


def _instant(value: Any) -> datetime:
    try:
        return utc(value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except (ValueError, TypeError) as exc:
        raise NotEvaluable("unattested_instant") from exc


def _date(value: Any) -> date:
    if type(value) is date:
        return value
    if not isinstance(value, str):
        raise NotEvaluable("invalid_period_date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise NotEvaluable("invalid_period_date") from exc


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return utc(value).isoformat()
    if type(value) is date:
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _reference(rows: Sequence[Mapping[str, Any]], *, source: str, value: float, end: date,
               rule: str) -> tuple[OfficialFact, dict[str, Any]]:
    refs = [{"doc_id": str(x["doc_id"]), "row_hash": str(x["row_hash"]),
             "concept":str(x["concept"]),"period_start":_jsonable(x.get("period_start")),"period_end":_jsonable(x["period_end"]),
             "unit":str(x["unit"]),"effective_value":float(x["value"]),"value_transform":x.get("value_transform","identity"),
             "accepted_at": _instant(x["accepted_at"]).isoformat(),
             "captured_at": _instant(x["first_seen_at"]).isoformat() if x.get("first_seen_at") else None}
            for x in rows]
    refs = sorted({canonical_hash(x):x for x in refs}.values(), key=lambda x:(x["accepted_at"],x["doc_id"],x["row_hash"]))
    derivation = {"rule": rule, "rows": refs}
    available = max(_instant(x["accepted_at"]) for x in rows)
    evidence = Evidence(source, "+".join(sorted({str(x["doc_id"]) for x in rows})), available, canonical_hash(derivation))
    return OfficialFact(value, "shares" if rule == "shares" else ("BRL" if source == "CVM" else "USD"), end, evidence), derivation


# This separate ladder may read concepts already in the append-only store. It never
# changes the frozen SEC collector, requests extra data or assumes missing values are0.
SEC_FIELDS = {
    "revenue": ("us-gaap:Revenues", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "us-gaap:SalesRevenueNet"),
    "net_income": ("us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic", "us-gaap:NetIncomeLoss", "us-gaap:ProfitLoss"),
    "operating_income": ("us-gaap:OperatingIncomeLoss",),
    "d_and_a": ("us-gaap:DepreciationDepletionAndAmortization", "us-gaap:DepreciationAndAmortization"),
    "operating_cash_flow": ("us-gaap:NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", "us-gaap:PaymentsToAcquireProductiveAssets"),
    "dividends": ("us-gaap:PaymentsOfDividendsCommonStock",),
    "cash": ("us-gaap:CashAndCashEquivalentsAtCarryingValue", "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "book_equity": ("us-gaap:StockholdersEquity",),
    "debt_total": ("us-gaap:LongTermDebt",),
    "debt_noncurrent": ("us-gaap:LongTermDebtNoncurrent",),
    "debt_current": ("us-gaap:DebtCurrent", "us-gaap:LongTermDebtCurrent"),
    "shares": ("dei:EntityCommonStockSharesOutstanding",),
    "current_assets": ("us-gaap:AssetsCurrent",),
    "total_liabilities": ("us-gaap:Liabilities",),
    "goodwill": ("us-gaap:Goodwill",),
    "intangible_assets_excluding_goodwill": ("us-gaap:FiniteLivedIntangibleAssetsNet",),
}
FLOW_FIELDS = {"revenue", "net_income", "operating_income", "d_and_a", "operating_cash_flow", "capex", "dividends"}


def _cvm_field(concept: str) -> tuple[str, bool] | None:
    from .cvm_fundamentals import _fold
    if concept == "cvm:composicao_capital:QT_ACAO_TOTAL_CAP_INTEGR":
        return "shares_gross", False
    if concept == "cvm:composicao_capital:QT_ACAO_TOTAL_TESOURO":
        return "shares_treasury", False
    parts = concept.split(":", 3)
    if len(parts) != 4 or not parts[1].endswith("_con"):
        return None  # individual and consolidated accounts are never silently mixed
    statement, code, text = parts[1].rsplit("_",1)[0], parts[2], _fold(parts[3])
    from .cvm_fundamentals import INCOME_CONCEPTS, VALUE_ADDED_CONCEPTS, CASH_FLOW_CONCEPTS
    groups = {"DRE": INCOME_CONCEPTS, "DVA": VALUE_ADDED_CONCEPTS, "DFC_MI": CASH_FLOW_CONCEPTS, "DFC_MD": CASH_FLOW_CONCEPTS}
    names = {"totalRevenue":"revenue", "netIncome":"net_income", "operatingIncome":"operating_income",
             "depreciationAndAmortization":"d_and_a", "totalCashFromOperatingActivities":"operating_cash_flow",
             "capitalExpenditures":"capex"}
    for spec in groups.get(statement, ()):
        if spec.field in names and spec.matches(code,text):
            return names[spec.field], spec.magnitude or spec.field == "capitalExpenditures"
    if statement == "BPA":
        if code == "1.01.01" and text.startswith("CAIXA E EQUIVALENTES DE CAIXA"):
            return "cash",False
        if code == "1.01" and text.startswith("ATIVO CIRCULANTE"):
            return "current_assets",False
    if statement == "BPP":
        checks = (("2.03","PATRIMONIO LIQUIDO","book_equity"),
                  ("2.01.04","EMPRESTIMOS E FINANCIAMENTOS","debt_current"),
                  ("2.02.01","EMPRESTIMOS E FINANCIAMENTOS","debt_noncurrent"),
                  ("2.01","PASSIVO CIRCULANTE","liabilities_current"),
                  ("2.02","PASSIVO NAO CIRCULANTE","liabilities_noncurrent"))
        for wanted, prefix, field in checks:
            if code == wanted and text.startswith(prefix):
                return field,False
    return None


def _facts_at_T(rows: Sequence[Mapping[str, Any]], filings: Mapping[str, Mapping[str, Any]], request: CompanyRequest,
                issuer: str, refused: Counter[str]) -> tuple[dict[str,OfficialFact], dict[str,Any]]:
    from .statement_vintages import vintage_row_hash
    from .sec_xbrl import discrete_quarters, trailing_quarters
    source, store_market = ("CVM","B3") if request.market == "B3" else ("SEC","US")
    cut = utc(request.as_of)
    economic = cut.astimezone(ZoneInfo("America/Sao_Paulo" if source == "CVM" else "America/New_York")).date()
    groups: dict[tuple[str,date|None,date], list[Mapping[str,Any]]] = {}
    blocked_concepts: set[str] = set()
    for original in rows:
        try:
            row = dict(original)
            # An observation outside T cannot invalidate the eligible field at T,
            # even when its exported content/identity is corrupt. Establish the
            # causal cut before any check that can populate blocked_concepts.
            accepted = _instant(row["accepted_at"])
            if accepted > cut:
                raise NotEvaluable("fact_available_after_T")
            if row.get("market") != store_market or str(row.get("issuer_key")) != issuer:
                raise NotEvaluable("wrong_fact_identity")
            if row.get("source") != ("cvm_dados_abertos" if source == "CVM" else "sec_xbrl_companyfacts"):
                raise NotEvaluable("wrong_fact_source")
            if row.get("row_hash") != vintage_row_hash(row):
                raise NotEvaluable("fact_hash_mismatch")
            doc = filings.get(str(row["doc_id"]))
            if doc is None or accepted != _instant(doc["accepted_at"]):
                raise NotEvaluable("fact_filing_acceptance_mismatch")
            end = _date(row["period_end"])
            start = _date(row["period_start"]) if row.get("period_start") else None
            if end > economic or (start is not None and start > end):
                raise NotEvaluable("fact_period_after_T_or_invalid")
            value = float(row["value"])
            if isinstance(row["value"],bool) or not math.isfinite(value):
                raise NotEvaluable("invalid_fact_value")
            row.update(accepted_at=accepted,period_start=start,period_end=end,value=value)
            groups.setdefault((str(row["concept"]),start,end),[]).append(row)
        except (ValueError,TypeError,KeyError) as exc:
            refused[str(exc) if isinstance(exc,NotEvaluable) else "malformed_fact"] += 1
            if isinstance(exc,NotEvaluable) and str(exc) in {"fact_hash_mismatch","fact_filing_acceptance_mismatch"}:
                blocked_concepts.add(str(original.get("concept")))
    selected = []
    for key, candidates in sorted(groups.items(),key=lambda x:repr(x[0])):
        latest = max(x["accepted_at"] for x in candidates)
        vintage = {x["row_hash"]:x for x in candidates if x["accepted_at"] == latest}
        if len(vintage) != 1:
            refused["ambiguous_latest_fact"] += 1
            blocked_concepts.add(key[0])
            continue
        selected.append(next(iter(vintage.values())))
    # Select a concept per field/span; SEC ladder order is explicit. Distinct CVM
    # accounts mapping to the same field/span are refused instead of guessed/summed.
    mapped: dict[tuple[str,date|None,date], list[tuple[int,Mapping[str,Any]]]] = {}
    blocked_fields = {field for field,names in SEC_FIELDS.items() if any(x in blocked_concepts for x in names)} if source == "SEC" else {
        match[0] for concept in blocked_concepts if (match := _cvm_field(concept)) is not None}
    for row in selected:
        concept = str(row["concept"])
        if source == "SEC":
            matches = [(field, names.index(concept),False) for field,names in SEC_FIELDS.items() if concept in names]
        else:
            match = _cvm_field(concept)
            matches = [(match[0],0,match[1])] if match else []
        for field, priority, magnitude in matches:
            if field in blocked_fields:
                continue
            expected = "shares" if field.startswith("shares") else ("BRL" if source == "CVM" else "USD")
            if row["unit"] != expected:
                refused[f"unit_mismatch:{field}"] += 1
                continue
            transformed = {**row,"value":abs(row["value"]) if magnitude else row["value"],
                           "value_transform":"absolute_magnitude" if magnitude else "identity"}
            mapped.setdefault((field,row["period_start"],row["period_end"]),[]).append((priority,transformed))
    by_field: dict[str,dict[tuple[date|None,date],Mapping[str,Any]]] = {}
    for (field,start,end), entries in mapped.items():
        priority = min(x[0] for x in entries)
        best = [x[1] for x in entries if x[0] == priority]
        if len(best) != 1:
            refused[f"ambiguous_field:{field}"] += 1
            continue
        by_field.setdefault(field,{})[(start,end)] = best[0]
    facts: dict[str,OfficialFact] = {}
    derivations: dict[str,Any] = {}
    for field, spans in by_field.items():
        if field in FLOW_FIELDS:
            durations = {(start,end):row for (start,end),row in spans.items() if start is not None}
            quarters = discrete_quarters(durations)
            chain = trailing_quarters(quarters)
            if len(chain) != 4:
                refused[f"four_contiguous_quarters_missing:{field}"] += 1
                continue
            used = [row for key in chain for row in quarters[key]["facts"]]
            value = math.fsum(float(quarters[key]["value"]) for key in chain)
            name = field+"_ttm"
            facts[name],derivations[name] = _reference(used,source=source,value=value,end=max(key[1] for key in chain),rule="four_contiguous_quarters")
        else:
            instants = {end:row for (start,end),row in spans.items() if start is None}
            if not instants:
                continue
            end = max(instants)
            facts[field],derivations[field] = _reference([instants[end]],source=source,value=float(instants[end]["value"]),end=end,rule="shares" if field.startswith("shares") else "latest_instant")
    def combine(name: str, left: str, right: str, sign: int=1) -> None:
        if left not in facts or right not in facts:
            return
        a,b = facts[left],facts[right]
        if a.period_end != b.period_end:
            refused[f"period_mismatch:{name}"] += 1
            return
        derivation = {"rule":f"{left}{'+' if sign == 1 else '-'}{right}","components":[derivations[left],derivations[right]]}
        evidence = Evidence(source,a.evidence.document_id+"+"+b.evidence.document_id,max(a.evidence.available_at,b.evidence.available_at),canonical_hash(derivation))
        facts[name] = OfficialFact(a.value+sign*b.value,a.unit,a.period_end,evidence)
        derivations[name] = derivation
    if source == "CVM":
        combine("shares","shares_gross","shares_treasury",-1)
        combine("total_liabilities","liabilities_current","liabilities_noncurrent")
    # Both debt components must be present; an absent component is never assumed zero.
    combine("debt","debt_noncurrent","debt_current")
    return facts,derivations


def adapt_company(sources: Sources, request: CompanyRequest) -> AdaptedCompany:
    cut = utc(request.as_of)
    if request.market not in {"B3","NASDAQ","NYSE"} or not request.symbol or not request.basis_id:
        raise NotEvaluable("invalid_company_request")
    refused: Counter[str] = Counter()
    provenance: dict[str,Any] = {"market":request.market,"symbol":request.symbol,"as_of":cut.isoformat(),
        "price_availability_policy":"strict_publication_no_later_than_T","refused":{},"captured_clock_is_not_availability":True,
        "historical_proof_gates": {
            "original_document_authentication":{"status":"unattested","reason":"canonical_readers_do_not_expose_original_document_bytes"},
            "instrument_identity":{"status":"unattested","reason":"filing_symbols_are_detection_time_associations"},
            "share_basis":{"status":"unattested","reason":"basis_id_is_caller_assertion","basis_id":request.basis_id},
            "corporate_action_basis":{"status":"unattested","reason":"price_bars_do_not_attest_corporate_action_coverage"},
        }}
    source = "CVM" if request.market == "B3" else "SEC"
    registered: dict[str,Mapping[str,Any]] = {}
    filing_groups: dict[str,list[Mapping[str,Any]]] = {}
    for raw in sources.filings(request.market):
        try:
            row = dict(raw)
            if row.get("market") != ("B3" if source == "CVM" else "US") or row.get("source") != ("cvm_dados_abertos" if source == "CVM" else "sec_edgar"):
                raise NotEvaluable("wrong_filing_source_or_market")
            accepted = _instant(row["accepted_at"])
            if accepted > cut:
                raise NotEvaluable("filing_available_after_T")
            if row.get("accepted_source") != ("cvm_dt_receb_end_of_day" if source == "CVM" else "sec_header"):
                raise NotEvaluable("filing_acceptance_unattested")
            if (not isinstance(row.get("issuer_key"),str) or not row["issuer_key"].strip()
                    or not isinstance(row.get("doc_id"),str) or not row["doc_id"].strip()
                    or not isinstance(row.get("symbols"),list)):
                raise NotEvaluable("filing_identity_unattested")
            if source == "CVM" and accepted != datetime.combine(_date(row["filed_date"]),time.max,tzinfo=ZoneInfo("America/Sao_Paulo")).astimezone(cut.tzinfo):
                raise NotEvaluable("cvm_acceptance_not_receipt_day_end")
            if source == "SEC" and (not isinstance(row.get("header_sha256"),str) or not re.fullmatch(r"[0-9a-f]{64}",row["header_sha256"])):
                raise NotEvaluable("sec_header_hash_missing")
            filing_groups.setdefault(str(row["doc_id"]),[]).append(row)
        except (ValueError,TypeError,KeyError) as exc:
            refused[str(exc) if isinstance(exc,NotEvaluable) else "malformed_filing"] += 1
    for document,rows in sorted(filing_groups.items()):
        # A document has one acceptance/issuer/header. Conflicting exported registry
        # entries must not be resolved by iteration order or a favorable vintage.
        core_keys=("market","issuer_key","source","doc_id","accepted_at","accepted_source","header_sha256","form","symbols")
        cores={canonical_hash({key:_jsonable(row.get(key)) for key in core_keys}) for row in rows}
        if len(cores)!=1:
            refused["ambiguous_filing_registry"] += 1
            continue
        registered[document]=min(rows,key=lambda row:canonical_hash(_jsonable(row)))
    candidates=[row for row in registered.values() if request.symbol in (row.get("symbols") or [])]
    if not candidates:
        provenance.update(status="not_evaluable",reason="official_symbol_issuer_unattested",refused=dict(sorted(refused.items())))
        return AdaptedCompany(None,(),provenance)
    latest = max(_instant(x["accepted_at"]) for x in candidates)
    issuers = {str(x["issuer_key"]) for x in candidates if _instant(x["accepted_at"]) == latest}
    if len(issuers) != 1:
        provenance.update(status="not_evaluable",reason="symbol_issuer_ambiguous",refused=dict(sorted(refused.items())))
        return AdaptedCompany(None,(),provenance)
    issuer = issuers.pop()
    own_filings = {key:x for key,x in registered.items() if str(x["issuer_key"]) == issuer}
    facts,derivations = _facts_at_T(sources.facts(request.market,issuer,cut),own_filings,request,issuer,refused)
    provenance.update(issuer_id=issuer,fact_derivations=derivations,facts_available=sorted(facts),
        filing_evidence=[{key:_jsonable(row.get(key)) for key in
            ("doc_id","issuer_key","accepted_at","accepted_source","header_sha256","first_seen_at")}
            for row in sorted(own_filings.values(),key=lambda x:(_instant(x["accepted_at"]),str(x["doc_id"])))])
    series = sources.price_series(request.market,request.symbol,cut)
    provenance["price"] = {key:series.get(key) for key in ("status","publication_id","available_at","fetched_at","first_captured_at")}
    try:
        from .valuation_price_history import SOURCE as PRICE_SOURCE, bar_content_sha256, session_close
        if series.get("status") != "ok":
            raise NotEvaluable(f"price_series:{series.get('status')}")
        available = _instant(series.get("available_at"))
        if available > cut:
            raise NotEvaluable("price_publication_after_T")
        if _instant(series.get("fetched_at")) > available:
            raise NotEvaluable("price_publication_precedes_capture_without_independent_proof")
        bars = []
        for session_key,row in (series.get("bars") or {}).items():
            session = _date(row["session_date"])
            if session_close(request.market,session) > cut:
                continue
            if session_key != session.isoformat():
                raise NotEvaluable("price_session_key_mismatch")
            if row.get("market") != request.market or row.get("symbol") != request.symbol or row.get("source") != PRICE_SOURCE:
                raise NotEvaluable("price_bar_identity_mismatch")
            if _instant(row.get("fetched_at"))>_instant(series.get("fetched_at")):
                raise NotEvaluable("price_bar_capture_after_vintage")
            if row.get("bar_sha256") != bar_content_sha256(row):
                raise NotEvaluable("price_bar_hash_mismatch")
            bars.append(row)
        if not bars:
            raise NotEvaluable("no_closed_price_session_before_T")
        row = max(bars,key=lambda x:_date(x["session_date"]))
        currency = "BRL" if source == "CVM" else "USD"
        if row.get("currency") != currency:
            raise NotEvaluable("price_currency_mismatch")
        price = Price(number(row["close"],"price"),currency,_date(row["session_date"]),request.basis_id,
                      Evidence("PRICE",str(series["publication_id"]),available,str(row["bar_sha256"])))
        # The store has no attested sector/classification contract. Unknown is explicit:
        # equity kernels can run, enterprise/peer models refuse instead of assuming industrial.
        company = CompanyInputs(request.symbol,request.market,currency,cut,request.basis_id,price,facts,
                                financial_company=None,issuer_id=issuer)
        company.validate()
    except (ValueError,TypeError,KeyError) as exc:
        provenance.update(status="not_evaluable",reason=str(exc) if isinstance(exc,NotEvaluable) else "malformed_price_series",refused=dict(sorted(refused.items())))
        return AdaptedCompany(None,(),provenance)
    targets = []
    snapshot = sources.consensus_snapshot(request.market,request.symbol)
    if snapshot:
        try:
            symbol_key=hashlib.sha256(request.symbol.strip().upper().encode()).hexdigest()[:16]
            if (snapshot.get("analysis_type")!="valuation_pit_source" or snapshot.get("entity_key")!=f"{request.market}_FMP_TARGETS_{symbol_key}"
                    or snapshot["inputs"].get("market")!=request.market or snapshot["inputs"].get("symbol")!=request.symbol
                    or snapshot["inputs"].get("provider")!="fmp"):
                raise NotEvaluable("consensus_snapshot_identity_mismatch")
            if _instant(snapshot["inputs"].get("fetched_at"))>_instant(snapshot.get("published_at")):
                raise NotEvaluable("consensus_capture_after_snapshot_publication")
            payload = snapshot["outputs"]["payload"]
            digest = canonical_hash(payload)
            if digest != snapshot["outputs"].get("payload_sha256") or digest != snapshot["inputs"].get("payload_sha256"):
                raise NotEvaluable("consensus_payload_hash_mismatch")
            provenance["consensus_capture"] = {"snapshot_id":snapshot.get("id"),"captured_at":snapshot["inputs"].get("fetched_at"),
                                               "published_at":_instant(snapshot["published_at"]).isoformat(),"payload_sha256":digest}
            for item in payload if isinstance(payload,list) else []:
                try:
                    if item.get("symbol",request.symbol)!=request.symbol:
                        raise NotEvaluable("consensus_target_symbol_mismatch")
                    # No horizon/currency defaults, no naive publishedDate-as-UTC hypothesis.
                    available = _instant(item["publishedDate"])
                    horizon = item["horizon_sessions"]
                    if isinstance(horizon,bool) or not isinstance(horizon,int) or horizon <= 0:
                        raise NotEvaluable("consensus_horizon_unattested")
                    if not isinstance(item["analystCompany"],str) or not item["analystCompany"].strip() or isinstance(item["priceTarget"],bool):
                        raise NotEvaluable("consensus_house_or_target_invalid")
                    targets.append(AnalystTarget(item["analystCompany"],float(item["priceTarget"]),str(item["currency"]),horizon,
                                                Evidence("ANALYST_CONSENSUS",str(item.get("document_id") or item.get("newsURL") or ""),available,canonical_hash(item))))
                except (ValueError,TypeError,KeyError) as exc:
                    refused[str(exc) if isinstance(exc,NotEvaluable) else "consensus_required_field_missing"] += 1
        except (ValueError,TypeError,KeyError) as exc:
            refused[str(exc) if isinstance(exc,NotEvaluable) else "malformed_consensus_snapshot"] += 1
    provenance.update(status="adapted",refused=dict(sorted(refused.items())),classification="unattested_no_industrial_default")
    return AdaptedCompany(company,tuple(targets),provenance)
