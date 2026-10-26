"""Offline SEC/CVM source-byte extraction and exact canonical-row binding.

A digest and official-looking URL establish integrity of supplied bytes, not their
origin. These extractors never waive historical identity/class/action/source gates,
fetch a document, validate a taxonomy remotely or infer a financial classification.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
import hashlib
import html
import io
import re
from typing import Any, Iterator, Mapping, Sequence
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zipfile
from zoneinfo import ZoneInfo

from .valuation_ensemble_inputs import NotEvaluable, canonical_hash, utc
from .valuation_ensemble_adapters import _date, _instant, _jsonable


MAX_BYTES=64*1024*1024
MAX_ARCHIVE_BYTES=256*1024*1024
XBRLI="http://www.xbrl.org/2003/instance"
XBRLDI="http://xbrl.org/2006/xbrldi"


@dataclass(frozen=True)
class SourceBytes:
    kind: str
    source_url: str
    captured_at: datetime
    expected_sha256: str
    payload: bytes

    def check(self) -> dict[str,Any]:
        if self.kind not in {"sec_header","sec_xbrl_instance","cvm_archive"}:
            raise NotEvaluable("unsupported_original_kind")
        if not isinstance(self.payload,bytes) or not 0<len(self.payload)<=MAX_BYTES:
            raise NotEvaluable("original_bytes_size_or_type")
        digest=hashlib.sha256(self.payload).hexdigest()
        if not isinstance(self.expected_sha256,str) or not re.fullmatch(r"[0-9a-f]{64}",self.expected_sha256) or digest!=self.expected_sha256:
            raise NotEvaluable("original_bytes_digest_mismatch")
        parsed=urlsplit(self.source_url)
        if (parsed.scheme!="https" or parsed.username is not None or parsed.password is not None
                or parsed.port not in {None,443} or parsed.query or parsed.fragment
                or "%" in parsed.path or "\\" in parsed.path or any(x in {".",".."} for x in parsed.path.split("/"))):
            raise NotEvaluable("original_source_url_invalid")
        if self.kind.startswith("sec_"):
            if parsed.hostname!="www.sec.gov" or not parsed.path.startswith("/Archives/edgar/data/"):
                raise NotEvaluable("original_sec_url_not_supported")
        elif parsed.hostname!="dados.cvm.gov.br" or not re.fullmatch(r"/dados/CIA_ABERTA/DOC/(?:ITR|DFP)/DADOS/(?:itr|dfp)_cia_aberta_\d{4}\.zip",parsed.path):
            raise NotEvaluable("original_cvm_url_not_supported")
        return {"kind":self.kind,"source_url":self.source_url,"captured_at":utc(self.captured_at).isoformat(),
            "sha256":digest,"byte_count":len(self.payload),
            "integrity":"matches_provided_expected_digest","origin_authentication":"unverified_supplied_bytes"}


def _cik(value: Any) -> str:
    value=str(value).strip()
    if not re.fullmatch(r"\d{1,10}",value):
        raise NotEvaluable("invalid_original_cik")
    return value.zfill(10)


def _one(values: Sequence[str], name: str, *, optional: bool=False) -> str | None:
    unique={x.strip() for x in values if x.strip()}
    if len(unique)!=1:
        if not unique and optional:
            return None
        raise NotEvaluable("original_missing_or_ambiguous:"+name)
    return unique.pop()


def _decimal(value: Any) -> Decimal:
    text=str(value).strip()
    if len(text)>256 or not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?",text):
        raise NotEvaluable("unsupported_original_numeric_lexical")
    try:
        result=Decimal(text)
    except InvalidOperation as exc:
        raise NotEvaluable("invalid_original_numeric") from exc
    if not result.is_finite():
        raise NotEvaluable("nonfinite_original_numeric")
    if result and abs(result.adjusted())>308:
        raise NotEvaluable("original_numeric_out_of_supported_range")
    return result


def extract_sec_header(artifact: SourceBytes) -> dict[str,Any]:
    from .sec_xbrl import parse_filing_header
    reference=artifact.check()
    if artifact.kind!="sec_header":
        raise NotEvaluable("sec_header_bytes_required")
    text=artifact.payload.decode("utf-8",errors="strict")
    body=html.unescape(text)
    def fields(name: str) -> list[str]:
        return re.findall(r"^[ \t]*"+re.escape(name)+r":[ \t]*(.*?)[ \t]*$",body,re.MULTILINE)
    _one(re.findall(r"<ACCEPTANCE-DATETIME>\s*(\d{14})",body),"acceptance")
    accession=_one(fields("ACCESSION NUMBER"),"accession")
    form=_one(fields("CONFORMED SUBMISSION TYPE"),"form")
    cik=_cik(_one(fields("CENTRAL INDEX KEY"),"CIK"))
    if not re.fullmatch(r"\d{10}-\d{2}-\d{6}",accession or ""):
        raise NotEvaluable("invalid_original_accession")
    parsed=urlsplit(artifact.source_url)
    expected_prefix=f"/Archives/edgar/data/{int(cik)}/"
    suffix=parsed.path.removeprefix(expected_prefix)
    if not parsed.path.startswith(expected_prefix) or suffix not in {
            f"{accession}-index-headers.html",f"{accession.replace('-','')}/{accession}-index-headers.html"}:
        raise NotEvaluable("sec_header_url_identity_mismatch")
    header=parse_filing_header(text)
    if header["header_sha256"]!=reference["sha256"]:
        raise NotEvaluable("header_text_byte_digest_mismatch")
    sic=_one(fields("STANDARD INDUSTRIAL CLASSIFICATION"),"SIC",optional=True)
    code=None
    if sic is not None:
        match=re.fullmatch(r".*\[(\d{4})\]",sic)
        if not match:
            raise NotEvaluable("unsupported_original_sic_lexical")
        code=match.group(1)
    return {"kind":"sec_header","artifact":reference,"issuer_key":cik,"doc_id":accession,"document_version":1,
        "form":form,"accepted_at":header["accepted_at"].isoformat(),"accepted_source":"sec_header",
        "filed_date":_jsonable(header["filed_date"]),"period_of_report":_jsonable(header["period_of_report"]),
        "sic":{"raw":sic,"code":code,"classification_policy_applied":False},
        "proof_scope":"issuer_document_acceptance_and_reported_SIC_only",
        "instrument_validity_or_class_or_action_basis_proven":False}


def _xml(artifact: SourceBytes) -> tuple[ET.Element,dict[str,str]]:
    text=artifact.payload.decode("utf-8",errors="strict")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)",text,re.IGNORECASE):
        raise NotEvaluable("original_xml_dtd_or_entity_not_allowed")
    namespaces={}
    try:
        count=depth=0
        parsed=ET.iterparse(io.StringIO(text),events=("start-ns","start","end"))
        for event,item in parsed:
            if event=="start-ns":
                prefix,uri=item
                if prefix in namespaces and namespaces[prefix]!=uri:
                    raise NotEvaluable("original_xml_namespace_rebinding_unsupported")
                namespaces[prefix]=uri
            elif event=="start":
                count+=1;depth+=1
                if count>250000 or depth>128:
                    raise NotEvaluable("original_xml_structure_limit")
            else:
                depth-=1
        root=parsed.root
    except ET.ParseError as exc:
        raise NotEvaluable("original_xml_not_supported_well_formed_instance") from exc
    if root.tag!="{"+XBRLI+"}xbrl":
        raise NotEvaluable("only_native_xbrl_instance_supported_no_inline_transformations")
    return root,namespaces


def _qname(value: str, namespaces: Mapping[str,str]) -> str:
    parts=value.split(":")
    prefix,local=(parts if len(parts)==2 else ("",parts[0]))
    if len(parts)>2 or not local or prefix not in namespaces:
        raise NotEvaluable("original_qname_namespace_unresolved")
    return "{"+namespaces[prefix]+"}"+local


def _concept(tag: str) -> str:
    if tag.startswith("{"):
        uri,local=tag[1:].split("}",1)
        if re.fullmatch(r"https?://xbrl\.sec\.gov/dei/20\d{2}(?:q[1-4]|-\d{2}-\d{2})?",uri):
            return "dei:"+local
        if re.fullmatch(r"https?://fasb\.org/us-gaap/20\d{2}-\d{2}-\d{2}",uri):
            return "us-gaap:"+local
    return tag


def extract_sec_instance(artifact: SourceBytes, header_bytes: SourceBytes) -> dict[str,Any]:
    reference=artifact.check();header=extract_sec_header(header_bytes)
    if artifact.kind!="sec_xbrl_instance":
        raise NotEvaluable("sec_instance_bytes_required")
    prefix=f"/Archives/edgar/data/{int(header['issuer_key'])}/{header['doc_id'].replace('-','')}/"
    path=urlsplit(artifact.source_url).path
    if not path.startswith(prefix) or "/" in path[len(prefix):] or not path.endswith(".xml"):
        raise NotEvaluable("sec_instance_header_url_identity_mismatch")
    root,namespaces=_xml(artifact)
    contexts,units={},{}
    for node in root.findall("{"+XBRLI+"}context"):
        identity=node.get("id")
        identifiers=node.findall(".//{"+XBRLI+"}identifier")
        if not identity or identity in contexts or len(identifiers)!=1 or identifiers[0].get("scheme")!="http://www.sec.gov/CIK" or _cik(identifiers[0].text)!=header["issuer_key"]:
            raise NotEvaluable("original_context_identity_missing_conflicting_or_wrong_CIK")
        periods=node.findall("{"+XBRLI+"}period")
        if len(periods)!=1 or len(periods[0]) not in {1,2}:
            raise NotEvaluable("original_context_period_missing_or_ambiguous")
        period_tags=[x.tag for x in periods[0]]
        if period_tags not in [["{"+XBRLI+"}instant"],["{"+XBRLI+"}startDate","{"+XBRLI+"}endDate"]]:
            raise NotEvaluable("original_context_period_missing_or_ambiguous")
        instant=node.findtext("{"+XBRLI+"}period/{"+XBRLI+"}instant")
        start=node.findtext("{"+XBRLI+"}period/{"+XBRLI+"}startDate")
        end=node.findtext("{"+XBRLI+"}period/{"+XBRLI+"}endDate")
        if instant and not start and not end:
            period={"period_start":None,"period_end":_date(instant).isoformat()}
        elif not instant and start and end and _date(start)<=_date(end):
            period={"period_start":_date(start).isoformat(),"period_end":_date(end).isoformat()}
        else:
            raise NotEvaluable("original_context_period_missing_or_ambiguous")
        dimensions=[]
        for member in node.findall(".//{"+XBRLDI+"}explicitMember"):
            dimensions.append({"axis":_qname(member.get("dimension", ""),namespaces),
                               "member":_qname((member.text or "").strip(),namespaces)})
        if len({x["axis"] for x in dimensions})!=len(dimensions):
            raise NotEvaluable("original_context_duplicate_dimension")
        contexts[identity]={"issuer_key":header["issuer_key"],**period,"dimensions":sorted(dimensions,key=lambda x:x["axis"]),
            "typed_dimension_present":bool(node.findall(".//{"+XBRLDI+"}typedMember")),
            "unsupported_context_content_present":any(child.tag not in {"{"+XBRLDI+"}explicitMember","{"+XBRLDI+"}typedMember"}
                for container in node.findall("{"+XBRLI+"}entity/{"+XBRLI+"}segment")+node.findall("{"+XBRLI+"}scenario") for child in container)}
    for node in root.findall("{"+XBRLI+"}unit"):
        identity=node.get("id");measure=node.findall("{"+XBRLI+"}measure")
        if not identity or identity in units:
            raise NotEvaluable("original_unit_missing_or_duplicate")
        qname=_qname((measure[0].text or "").strip(),namespaces) if len(measure)==1 and len(node)==1 else None
        units[identity]="shares" if qname=="{"+XBRLI+"}shares" else qname.split("}")[-1] if qname and qname.startswith("{http://www.xbrl.org/2003/iso4217}") else None
    facts=[]
    for node in root:
        context=node.get("contextRef")
        if context is None:
            continue
        if context not in contexts or len(node):
            raise NotEvaluable("original_fact_context_missing_or_nested_content")
        if node.get("{http://www.w3.org/2001/XMLSchema-instance}nil") in {"true","1"}:
            continue
        lexical=(node.text or "").strip();unit_ref=node.get("unitRef")
        if any(node.get(name) is not None for name in ("scale","sign","format")):
            raise NotEvaluable("native_instance_numeric_transformation_not_supported")
        value=str(_decimal(lexical)) if unit_ref else lexical
        if unit_ref and (unit_ref not in units or units[unit_ref] is None):
            unit=None
        else:
            unit=units.get(unit_ref) if unit_ref else None
        fact={"concept":_concept(node.tag),"context_id":context,"context":contexts[context],"unit":unit,
              "numeric":bool(unit_ref),"value":value,"decimals":node.get("decimals"),"lexical":lexical}
        fact["original_fact_sha256"]=canonical_hash(fact)
        facts.append(fact)
    identity_checks={}
    for name,expected in (("EntityCentralIndexKey",header["issuer_key"]),("DocumentType",header["form"]),
                          ("DocumentPeriodEndDate",header["period_of_report"])):
        declared=_one([x["value"] for x in facts if x["concept"]=="dei:"+name],name,optional=True)
        if declared is not None and ((name=="EntityCentralIndexKey" and _cik(declared)!=expected)
                or (name!="EntityCentralIndexKey" and declared!=expected)):
            raise NotEvaluable("original_instance_header_identity_disagreement:"+name)
        identity_checks[name]="matches_header" if declared is not None else "not_present_in_supported_instance"
    cover=[]
    for context in sorted(contexts):
        fields={}
        for name in ("TradingSymbol","Security12bTitle","SecurityExchangeName"):
            values=[x["value"] for x in facts if x["context_id"]==context and x["concept"]=="dei:"+name]
            fields[name]=_one(values,name,optional=True)
        if any(fields.values()):
            cover.append({"context_id":context,"context":contexts[context],**fields,
                "complete_same_context_security_tuple":all(fields.values()),
                "proof_scope":"reported_in_filing_context_not_historical_validity_or_share_allocation"})
    return {"kind":"sec_xbrl_instance","artifact":reference,"header_artifact":header["artifact"],
        "issuer_key":header["issuer_key"],"doc_id":header["doc_id"],"document_version":1,"form":header["form"],
        "accepted_at":header["accepted_at"],"filed_date":header["filed_date"],"period_of_report":header["period_of_report"],
        "contexts":contexts,"facts":facts,"cover_securities":cover,"header_identity_checks":identity_checks,
        "origin_authentication":"unverified_supplied_bytes","historical_admissibility":False}


def _csv_rows(raw: bytes, required: set[str]) -> Iterator[dict[str,str]]:
    reader=csv.DictReader(io.StringIO(raw.decode("latin-1")),delimiter=";",strict=True)
    names=reader.fieldnames or []
    if len(names)!=len(set(names)) or not required<=set(names):
        raise NotEvaluable("original_csv_missing_or_duplicate_columns")
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise NotEvaluable("original_csv_column_count_mismatch")
        yield row


def extract_cvm_archive(artifact: SourceBytes, *, document_ids: tuple[str,...] | None=None) -> dict[str,Any]:
    reference=artifact.check()
    if artifact.kind!="cvm_archive":
        raise NotEvaluable("cvm_archive_bytes_required")
    match=re.fullmatch(r"/(?:dados)/CIA_ABERTA/DOC/(ITR|DFP)/DADOS/(itr|dfp)_cia_aberta_(\d{4})\.zip",urlsplit(artifact.source_url).path)
    if not match or match[1].lower()!=match[2]:
        raise NotEvaluable("cvm_archive_type_url_mismatch")
    kind,year=match[2],match[3];prefix=f"{kind}_cia_aberta_";members={}
    try:
        with zipfile.ZipFile(io.BytesIO(artifact.payload)) as archive:
            infos=archive.infolist()
            if len(infos)>1000 or sum(x.file_size for x in infos)>MAX_ARCHIVE_BYTES:
                raise NotEvaluable("original_archive_expansion_limit")
            for info in infos:
                name=info.filename
                if (name in members or "/" in name or "\\" in name or name in {".",".."}
                        or info.flag_bits&1 or info.file_size>MAX_BYTES or info.external_attr>>16&0o170000==0o120000):
                    raise NotEvaluable("original_archive_member_unsafe_or_duplicate")
                members[name]=archive.read(info)
    except (zipfile.BadZipFile,RuntimeError) as exc:
        raise NotEvaluable("invalid_original_archive") from exc
    index_name=prefix+year+".csv"
    if index_name not in members:
        raise NotEvaluable("original_cvm_document_index_missing")
    index=_csv_rows(members[index_name],{"CNPJ_CIA","DT_REFER","VERSAO","ID_DOC","DT_RECEB"})
    documents={}
    for row in index:
        if document_ids is not None and row["ID_DOC"].strip() not in document_ids:
            continue
        tax_id=row["CNPJ_CIA"].strip();version=row["VERSAO"].strip();refer=_date(row["DT_REFER"])
        if not re.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}",tax_id) or not re.fullmatch(r"[1-9]\d*",version) or refer.year!=int(year) or not row["ID_DOC"].strip():
            raise NotEvaluable("original_cvm_document_identity_invalid")
        received=_date(row["DT_RECEB"])
        accepted=datetime.combine(received,time.max,tzinfo=ZoneInfo("America/Sao_Paulo"))
        key=(tax_id,refer.isoformat(),int(version))
        document={"issuer_key":tax_id,"doc_id":row["ID_DOC"].strip(),"document_version":int(version),"form":kind.upper(),
            "period_of_report":refer.isoformat(),"filed_date":received.isoformat(),"accepted_at":utc(accepted).isoformat(),
            "accepted_source":"cvm_dt_receb_end_of_day","index_row":row,"index_row_sha256":canonical_hash(row)}
        if key in documents and documents[key]!=document:
            raise NotEvaluable("original_cvm_document_index_ambiguous")
        documents[key]=document
    if document_ids is not None and {x["doc_id"] for x in documents.values()}!=set(document_ids):
        raise NotEvaluable("requested_cvm_original_document_not_found")
    facts=[];unbound_rows=0
    capital_names={"QT_ACAO_ORDIN_CAP_INTEGR","QT_ACAO_PREF_CAP_INTEGR","QT_ACAO_TOTAL_CAP_INTEGR",
                   "QT_ACAO_ORDIN_TESOURO","QT_ACAO_PREF_TESOURO","QT_ACAO_TOTAL_TESOURO"}
    for name,raw in sorted(members.items()):
        table=re.fullmatch(re.escape(prefix)+r"([A-Z]+(?:_[A-Z]+)?_(?:con|ind)|composicao_capital)_"+year+r"\.csv",name)
        if not table:
            continue
        statement=table[1];required={"CNPJ_CIA","DT_REFER","VERSAO"}
        required|=capital_names if statement=="composicao_capital" else {"CD_CONTA","DS_CONTA","VL_CONTA","DT_FIM_EXERC","MOEDA","ESCALA_MOEDA"}
        for line,row in enumerate(_csv_rows(raw,required),2):
            version=row["VERSAO"].strip()
            if not re.fullmatch(r"[1-9]\d*",version):
                raise NotEvaluable("original_cvm_fact_version_invalid")
            document=documents.get((row["CNPJ_CIA"].strip(),_date(row["DT_REFER"]).isoformat(),int(version)))
            if document is None:
                unbound_rows+=1;continue
            base={key:document[key] for key in ("issuer_key","doc_id","document_version","form","filed_date","accepted_at")}
            values=[]
            if statement=="composicao_capital":
                values=[("cvm:composicao_capital:"+key,"shares",str(_decimal(row[key])),None,document["period_of_report"]) for key in sorted(capital_names) if row[key].strip()]
            else:
                from .cvm_fundamentals import _fold
                scale=_fold(row["ESCALA_MOEDA"])
                scales={"UNIDADE":Decimal(1),"UNIDADES":Decimal(1),"MIL":Decimal(1000),"MILHAO":Decimal(1000000),"MILHOES":Decimal(1000000)}
                if scale not in scales or _fold(row["MOEDA"])!="REAL":
                    unbound_rows+=1;continue
                description=re.sub(r"\s+"," ",row["DS_CONTA"]).strip()
                values=[("cvm:"+statement+":"+row["CD_CONTA"].strip()+":"+description,"BRL",str(_decimal(row["VL_CONTA"])*scales[scale]),
                    _date(row["DT_INI_EXERC"]).isoformat() if row.get("DT_INI_EXERC") else None,_date(row["DT_FIM_EXERC"]).isoformat())]
            for concept,unit,value,start,end in values:
                fact={**base,"concept":concept,"unit":unit,"value":value,"period_start":start,"period_end":end,
                    "entry":name,"csv_line":line,"raw_row_sha256":canonical_hash(row),"raw_row":row}
                fact["original_fact_sha256"]=canonical_hash(fact)
                facts.append(fact)
    return {"kind":"cvm_archive","artifact":reference,"documents":list(documents.values()),"facts":facts,
        "archive_members":[{"name":name,"sha256":hashlib.sha256(raw).hexdigest(),"byte_count":len(raw)} for name,raw in sorted(members.items())],
        "unbound_or_unsupported_rows":unbound_rows,"proof_scope":"official_document_index_accounts_and_class_counts_not_ticker_or_action_history",
        "requested_document_ids":sorted(document_ids) if document_ids is not None else None,
        "origin_authentication":"unverified_supplied_bytes","historical_admissibility":False}


def _bind_canonical_rows_unchecked(extracted: Mapping[str,Any], *, filings: Sequence[Mapping[str,Any]]=(),
                        facts: Sequence[Mapping[str,Any]]=()) -> dict[str,Any]:
    """Match exact original values; never sum classes or borrow an identity from symbols."""
    from .statement_vintages import vintage_row_hash
    is_sec=extracted["kind"].startswith("sec_")
    documents=extracted.get("documents",[extracted]);results=[]
    def same_issuer(a: Any,b: Any) -> bool:
        return _cik(a)==_cik(b) if is_sec else str(a)==str(b)
    for row in filings:
        reason="original_filing_identity_or_clock_mismatch"
        matches=[]
        for doc in documents:
            if (same_issuer(row.get("issuer_key"),doc["issuer_key"]) and str(row.get("doc_id"))==doc["doc_id"]
                    and int(row.get("document_version",1))==doc["document_version"] and row.get("form")==doc["form"]
                    and _instant(row.get("accepted_at"))==_instant(doc["accepted_at"])
                    and _date(row.get("filed_date")).isoformat()==doc["filed_date"]
                    and (_date(row["period_of_report"]).isoformat() if row.get("period_of_report") else None)==doc["period_of_report"]
                    and row.get("market")==("US" if is_sec else "B3")
                    and row.get("source")==("sec_edgar" if is_sec else "cvm_dados_abertos")
                    and row.get("accepted_source")==("sec_header" if is_sec else "cvm_dt_receb_end_of_day")):
                expected_header=(extracted["artifact"] if extracted["kind"]=="sec_header" else extracted.get("header_artifact"))
                if not is_sec or (expected_header and row.get("header_sha256")==expected_header["sha256"]):
                    matches.append(doc)
        results.append({"type":"filing","row_sha256":canonical_hash(_jsonable(row)),"status":"content_matched" if len(matches)==1 else "not_bound",
            "reason":None if len(matches)==1 else reason,"symbols_not_authenticated":True})
    for row in facts:
        reason="no_unique_original_fact_match_contexts_preserved";matches=[]
        if row.get("row_hash")!=vintage_row_hash(row):
            reason="canonical_fact_hash_mismatch"
        else:
            for fact in extracted.get("facts",[]):
                issuer=extracted.get("issuer_key",fact.get("issuer_key"))
                accepted=extracted.get("accepted_at",fact.get("accepted_at"))
                doc=extracted.get("doc_id",fact.get("doc_id"));version=extracted.get("document_version",fact.get("document_version"))
                form=extracted.get("form",fact.get("form"));filed=extracted.get("filed_date",fact.get("filed_date"))
                context=fact.get("context",fact)
                if context.get("dimensions") or context.get("typed_dimension_present") or context.get("unsupported_context_content_present"):
                    continue
                if (row.get("market")==("US" if is_sec else "B3")
                        and row.get("source")==("sec_xbrl_companyfacts" if is_sec else "cvm_dados_abertos")
                        and same_issuer(row.get("issuer_key"),issuer) and str(row.get("doc_id"))==doc
                        and int(row.get("document_version",1))==version and _instant(row.get("accepted_at"))==_instant(accepted)
                        and row.get("form")==form and _date(row.get("filed_date")).isoformat()==filed
                        and row.get("concept")==fact["concept"] and row.get("unit")==fact["unit"]
                        and (_date(row["period_start"]).isoformat() if row.get("period_start") else None)==context["period_start"]
                        and _date(row["period_end"]).isoformat()==context["period_end"]
                        and _decimal(row["value"])==_decimal(fact["value"])):
                    matches.append(fact["original_fact_sha256"])
        results.append({"type":"fact","row_sha256":str(row.get("row_hash")),"status":"content_matched" if len(matches)==1 else "not_bound",
            "reason":None if len(matches)==1 else reason,"original_fact_sha256":matches[0] if len(matches)==1 else None})
    return {"rows":results,"matched":sum(x["status"]=="content_matched" for x in results),
        "not_bound":sum(x["status"]!="content_matched" for x in results),"binding_scope":"original_content_equality_not_origin_or_historical_admissibility",
        "historical_admissibility":False}


def bind_canonical_rows(extracted: Mapping[str,Any], *, filings: Sequence[Mapping[str,Any]]=(),
                        facts: Sequence[Mapping[str,Any]]=()) -> dict[str,Any]:
    results=[]
    for kind,rows in (("filing",filings),("fact",facts)):
        for ordinal,row in enumerate(rows):
            if not isinstance(row,Mapping):
                raise NotEvaluable("canonical_binding_requires_mapping_rows")
            try:
                if type(row.get("document_version")) is not int or row["document_version"]<1:
                    raise NotEvaluable("canonical_document_version_invalid")
                bound=_bind_canonical_rows_unchecked(extracted,filings=(row,) if kind=="filing" else (),facts=(row,) if kind=="fact" else ())
                results.extend(bound["rows"])
            except (ValueError,TypeError,KeyError):
                results.append({"type":kind,"row_ordinal":ordinal,"row_sha256":None,
                    "status":"not_bound","reason":"canonical_row_fields_invalid_or_unsupported"})
    return {"rows":results,"matched":sum(x["status"]=="content_matched" for x in results),
        "not_bound":sum(x["status"]!="content_matched" for x in results),
        "binding_scope":"listed_original_content_fields_not_origin_or_full_row_or_historical_admissibility",
        "checked_fact_fields":["market","source","issuer_key","doc_id","document_version","form","filed_date","accepted_at",
            "concept","unit","period_start","period_end","value"],
        "unproven_row_fields":["symbols","fiscal_year","fiscal_period","first_seen_at"],"historical_admissibility":False}
