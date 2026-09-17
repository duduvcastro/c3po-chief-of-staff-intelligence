"""RC4-bis direct insider evidence, bounded and replay-verifiable.

No database writes. Finnhub's documented 100-record cap is handled by splitting
inclusive date windows; a saturated single day remains UNKNOWN. A successful
empty Finnhub population may select EODHD fallback, never union providers.
"""
from __future__ import annotations

import base64
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import re
from typing import Any

from app.market_data.eodhd import EodhdClient
from app.market_data.finnhub import FinnhubClient
from app.r2d2_v2_risk_acquisition import RiskAcquirer, SourceReceipt, SourceRequest
from app.r2d2_v2_risk_normalization import canonical_symbol, insider_event_candidates, strict_day
from app.r2d2_v2_risk_source import ComponentEvidence, InsiderActivity, ORIGIN_REVISION

SCHEMA = "DIRECT_INSIDER_RC4BIS_V1"
PATH = "/api/v1/stock/insider-transactions"
CAP = 100


def encode_receipt(receipt: SourceReceipt) -> dict[str, Any]:
    return {"provider": receipt.request.provider, "path": receipt.request.path,
            "parameters": dict(receipt.request.parameters), "started_at": receipt.started_at.isoformat(),
            "received_at": receipt.received_at.isoformat(), "status": receipt.status,
            "body_b64": base64.b64encode(receipt.body).decode("ascii"),
            "payload_sha256": receipt.payload_sha256, "diagnostic": receipt.diagnostic}


def decode_receipt(value: dict[str, Any]) -> SourceReceipt:
    return SourceReceipt(SourceRequest(value["provider"], value["path"], value["parameters"]),
                         datetime.fromisoformat(value["started_at"]), datetime.fromisoformat(value["received_at"]),
                         value["status"], base64.b64decode(value["body_b64"], validate=True),
                         value["payload_sha256"], value["diagnostic"])


def _payload(receipt: SourceReceipt, *, cutoff: datetime) -> Any:
    if (receipt.status != 200 or receipt.diagnostic is not None
            or receipt.started_at.tzinfo is None or receipt.received_at.tzinfo is None
            or not cutoff <= receipt.started_at <= receipt.received_at
            or hashlib.sha256(receipt.body).hexdigest() != receipt.payload_sha256):
        raise ValueError("DIRECT_INSIDER_RECEIPT_INVALID")
    return receipt.payload()


def _finnhub_rows(receipt: SourceReceipt, *, symbol: str, start: date, end: date,
                  cutoff: datetime) -> list[dict[str, Any]]:
    expected = {"symbol": symbol, "from": start.isoformat(), "to": end.isoformat()}
    if receipt.request != SourceRequest("finnhub", PATH, expected):
        raise ValueError("FINNHUB_REQUEST_BINDING_INVALID")
    payload = _payload(receipt, cutoff=cutoff)
    if (not isinstance(payload, dict) or canonical_symbol(payload.get("symbol")) != symbol
            or not isinstance(payload.get("data"), list)):
        raise ValueError("FINNHUB_ENVELOPE_IDENTITY_UNKNOWN")
    rows = payload["data"]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("FINNHUB_ROWS_INVALID")
    for row in rows:
        transaction_day = strict_day(row.get("transactionDate"))
        if transaction_day is None or not start <= transaction_day <= end:
            raise ValueError("FINNHUB_REQUEST_WINDOW_NOT_OBSERVED")
    return rows


def _requires_split(receipt: SourceReceipt, rows: list[dict[str, Any]]) -> bool:
    payload = receipt.payload()
    continuation = any(payload.get(key) not in (None, False, "", [], {})
                       for key in ("next", "nextPage", "next_page", "nextCursor", "next_cursor", "hasMore", "has_more", "pagination", "links"))
    for key in ("total", "totalCount", "total_count"):
        if key in payload:
            count = payload[key]
            if type(count) is not int or count < len(rows):
                raise ValueError("FINNHUB_TOTAL_METADATA_INVALID")
            continuation = continuation or count > len(rows)
    return len(rows) >= CAP or continuation


def _event(transaction: dict[str, Any] | None, *, symbol: str, provider: str,
           cutoff: datetime) -> dict[str, Any] | None:
    if transaction is None:
        raise ValueError("DIRECT_INSIDER_NORMALIZATION_LOSS")
    day = strict_day(transaction.get("transaction_date"))
    name = str(transaction.get("insider_name") or "").strip()
    code = str(transaction.get("transaction_code") or "").strip().upper()
    if day is None or not name or not code:
        raise ValueError("DIRECT_INSIDER_RECORD_INVALID")
    published = datetime.combine(day, time.min, timezone.utc)
    if published > cutoff:
        raise ValueError("DIRECT_INSIDER_FUTURE_RECORD")
    if published < cutoff - timedelta(days=180):
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return {"symbol": symbol, "market": "US", "source_code": "sec", "event_type": "Insider Transaction",
            "external_id": f"{provider}-insider-{symbol}-{day.isoformat()}-{slug}-{code}",
            "published_at": published, "raw_metadata": {"source": provider, **transaction}}


def _dedup(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Same source_code/external_id upsert semantics as save_ir_events.
    unique = {(event["source_code"], event["external_id"]): event for event in events}
    return list(unique.values())


def _finnhub_replay(receipts: list[SourceReceipt], symbol: str, cutoff: datetime) -> tuple[list[dict[str, Any]], bool]:
    position = 0
    has_rows = False
    events: list[dict[str, Any]] = []

    def visit(start: date, end: date) -> None:
        nonlocal position, has_rows
        if position >= len(receipts):
            raise ValueError("FINNHUB_WINDOW_INCOMPLETE")
        receipt = receipts[position]
        position += 1
        rows = _finnhub_rows(receipt, symbol=symbol, start=start, end=end, cutoff=cutoff)
        if _requires_split(receipt, rows):
            if start == end:
                raise ValueError("FINNHUB_SINGLE_DAY_SATURATED")
            midpoint = start + timedelta(days=(end-start).days//2)
            visit(start, midpoint)
            visit(midpoint+timedelta(days=1), end)
            return
        has_rows = has_rows or bool(rows)
        for row in rows:
            # Provider responses may include non-directional transactions;
            # preserve them through normalization, then score only P/S.
            if "symbol" in row and canonical_symbol(row["symbol"]) != symbol:
                raise ValueError("FINNHUB_ROW_IDENTITY_MISMATCH")
            normalized = FinnhubClient._normalize_transaction(row)
            event = _event(normalized, symbol=symbol, provider="finnhub", cutoff=cutoff)
            if event is not None:
                events.append(event)
    visit((cutoff-timedelta(days=180)).date(), cutoff.date())
    if position != len(receipts):
        raise ValueError("FINNHUB_UNEXPECTED_RECEIPTS")
    return _dedup(events), has_rows


def _eodhd_replay(receipts: list[SourceReceipt], symbol: str, cutoff: datetime,
                  identity: SourceReceipt | None) -> list[dict[str, Any]]:
    recognized = False
    if identity is not None:
        provider_symbol = symbol if "." in symbol else symbol+".US"
        # Identity snapshot may precede the current query; never invent its time.
        if (identity.request.provider == "eodhd" and identity.request.path == "/api/v1.1/fundamentals/"+provider_symbol
                and identity.status == 200 and identity.diagnostic is None
                and identity.started_at.tzinfo is not None and identity.received_at.tzinfo is not None
                and identity.started_at <= identity.received_at
                and hashlib.sha256(identity.body).hexdigest() == identity.payload_sha256):
            payload = identity.payload()
            recognized = canonical_symbol(payload.get("General", {}).get("Code")) == symbol
    events: list[dict[str, Any]] = []
    offset = 0
    ended = False
    for receipt in receipts:
        if ended or receipt.request != SourceRequest("eodhd", f"/api/sec-filings/{symbol}/form4", {"page[offset]":offset,"page[limit]":100}):
            raise ValueError("EODHD_REQUEST_BINDING_INVALID")
        payload = _payload(receipt, cutoff=cutoff)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list) or not isinstance(payload.get("links"), dict) or "next" not in payload["links"]:
            raise ValueError("EODHD_ENVELOPE_INVALID")
        filings = payload["data"]
        if len(filings)>100:
            raise ValueError("EODHD_PAGE_SIZE_INVALID")
        for filing in filings:
            if not isinstance(filing, dict):
                raise ValueError("EODHD_FILING_INVALID")
            if "symbol" in filing:
                if canonical_symbol(filing["symbol"]) != symbol:
                    raise ValueError("EODHD_FILING_IDENTITY_MISMATCH")
                recognized = True
            filing_day = strict_day(filing.get("filed_at"))
            if filing_day is None or filing_day > cutoff.date():
                raise ValueError("EODHD_FILING_DATE_INVALID")
            rows = filing.get("non_derivative")
            if not isinstance(rows, list):
                raise ValueError("EODHD_TRANSACTIONS_INVALID")
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("EODHD_TRANSACTION_INVALID")
                event = _event(EodhdClient._normalize_form4_row(row, filing_day.isoformat()), symbol=symbol,provider="eodhd",cutoff=cutoff)
                if event is not None:
                    events.append(event)
        next_link = payload["links"]["next"]
        ended = next_link is None
        if not ended:
            from urllib.parse import parse_qs, urlsplit
            if not isinstance(next_link,str) or not filings:
                raise ValueError("EODHD_NEXT_INVALID")
            parsed=urlsplit(next_link)
            if (parsed.scheme or parsed.netloc or parsed.fragment or parsed.path not in (f"/api/sec-filings/{symbol}/form4",f"/api/sec-filings/{symbol}.US/form4")
                    or parse_qs(parsed.query)!={"page[offset]":[str(offset+len(filings))],"page[limit]":["100"]}):
                raise ValueError("EODHD_NEXT_INVALID")
        offset+=len(filings)
    if not ended:
        raise ValueError("EODHD_PAGINATION_INCOMPLETE")
    if not recognized:
        raise ValueError("EODHD_IDENTITY_UNKNOWN")
    return _dedup(events)


def assess_direct_insider(snapshot: dict[str, Any], *, received_at: datetime,
                          computed_at: datetime) -> tuple[InsiderActivity | None, ComponentEvidence, list[str]]:
    """Recompute coverage from original bytes and exact window tree, not flags."""
    symbol=canonical_symbol(snapshot.get("symbol"))
    cutoff=datetime.fromisoformat(snapshot["query_cutoff_at"])
    if snapshot.get("schema")!=SCHEMA or snapshot.get("market")!="US" or cutoff.tzinfo is None:
        raise ValueError("DIRECT_INSIDER_SNAPSHOT_INVALID")
    diagnostics: list[str]=[]
    events: list[dict[str,Any]]=[]
    provider="finnhub"
    complete=False
    acquisition_completed=None
    try:
        limits = snapshot.get("request_limits", {})
        finn_limit, eod_limit = limits.get("finnhub"), limits.get("eodhd")
        if type(finn_limit) is not int or not 1 <= finn_limit <= 512 or type(eod_limit) is not int or not 1 <= eod_limit <= 100:
            raise ValueError("DIRECT_INSIDER_RECEIPT_BUDGET_INVALID")
        if len(snapshot["finnhub_receipts"]) > finn_limit or len(snapshot.get("eodhd_receipts", [])) > eod_limit:
            raise ValueError("DIRECT_INSIDER_RECEIPT_BUDGET_EXCEEDED")
        finnhub=[decode_receipt(row) for row in snapshot["finnhub_receipts"]]
        fallback=[decode_receipt(row) for row in snapshot.get("eodhd_receipts",[])]
        events,has_rows=_finnhub_replay(finnhub,symbol,cutoff)
        if not has_rows:
            provider="eodhd"
            identity=decode_receipt(snapshot["eodhd_identity_receipt"]) if snapshot.get("eodhd_identity_receipt") else None
            events=_eodhd_replay(fallback,symbol,cutoff,identity)
        elif fallback:
            raise ValueError("INSIDER_PROVIDERS_MUST_NOT_UNION")
        clocks=[receipt.received_at for receipt in finnhub+fallback]
        if provider == "eodhd" and snapshot.get("eodhd_identity_receipt"):
            clocks.append(decode_receipt(snapshot["eodhd_identity_receipt"]).received_at)
        acquisition_completed=max(clocks)
        if not cutoff <= acquisition_completed <= received_at <= computed_at:
            raise ValueError("DIRECT_INSIDER_CLOCK_ORDER_INVALID")
        complete=True
    except (ValueError,TypeError,KeyError,IndexError) as exc:
        diagnostics.append(str(exc) if isinstance(exc,ValueError) and re.fullmatch(r"[A-Z0-9_]+",str(exc)) else "DIRECT_INSIDER_EVIDENCE_INVALID")
    value=insider_event_candidates(events,symbol=symbol,decision_at=cutoff) if complete else None
    source_at=max((event["published_at"] for event in events),default=acquisition_completed)
    digest=hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
    evidence=ComponentEvidence(True,complete,"DIRECT_INSIDER_RC4BIS/"+provider,ORIGIN_REVISION,digest,
        source_at,received_at,"Owner RC4bis direct180d; original transactionDate00Z/name/code/dedup; Finnhub split cap100; EODHD only empty fallback; no DB ingestion")
    return value,evidence,diagnostics


class DirectInsiderAcquirer:
    def __init__(self,acquirer:RiskAcquirer,*,max_requests:int=128)->None:
        if type(max_requests)is not int or not 1<=max_requests<=512:
            raise ValueError("DIRECT_INSIDER_BUDGET_INVALID")
        self.acquirer=acquirer
        self.max_requests=max_requests

    def acquire(self,symbol:str,*,cutoff:datetime,eodhd_identity:SourceReceipt|None=None)->dict[str,Any]:
        symbol=canonical_symbol(symbol)
        if cutoff.tzinfo is None:
            raise ValueError("DIRECT_INSIDER_CUTOFF_INVALID")
        receipts:list[SourceReceipt]=[]
        diagnostic=None
        def visit(start:date,end:date)->None:
            if len(receipts)>=self.max_requests:
                raise ValueError("FINNHUB_REQUEST_BUDGET_EXHAUSTED")
            receipt=self.acquirer._read(SourceRequest("finnhub",PATH,{"symbol":symbol,"from":start.isoformat(),"to":end.isoformat()}))
            receipts.append(receipt)
            rows=_finnhub_rows(receipt,symbol=symbol,start=start,end=end,cutoff=cutoff)
            if _requires_split(receipt, rows):
                if start==end:raise ValueError("FINNHUB_SINGLE_DAY_SATURATED")
                midpoint=start+timedelta(days=(end-start).days//2)
                visit(start,midpoint);visit(midpoint+timedelta(days=1),end)
        fallback:list[SourceReceipt]=[]
        try:
            visit((cutoff-timedelta(days=180)).date(),cutoff.date())
            events,has_rows=_finnhub_replay(receipts,symbol,cutoff)
            if not has_rows:
                fallback=list(self.acquirer.form4_fallback_diagnostic(symbol).receipts)
        except (ValueError,TypeError,KeyError) as exc:
            diagnostic=str(exc) if isinstance(exc,ValueError) and re.fullmatch(r"[A-Z0-9_]+",str(exc)) else "DIRECT_INSIDER_EVIDENCE_INVALID"
        return {"schema":SCHEMA,"symbol":symbol,"market":"US","query_cutoff_at":cutoff.isoformat(),
                "request_limits":{"finnhub":self.max_requests,"eodhd":self.acquirer.max_pages,"total":self.max_requests+self.acquirer.max_pages},
                "finnhub_receipts":[encode_receipt(row) for row in receipts],
                "eodhd_receipts":[encode_receipt(row) for row in fallback],
                "eodhd_identity_receipt":encode_receipt(eodhd_identity) if eodhd_identity else None,
                "acquisition_diagnostic":diagnostic}
