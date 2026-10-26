"""Official listing inventory and a read model independent of screening eligibility.

This module never computes a second TP or changes a frozen PIT producer. A listing
without a canonical record remains visible with null values and explicit reasons.
An inventory entry, a minimum badge or membership of a tested sample cannot grant
buy permission: an existing permission AND a separately verified PASS scope are
required. Capture/production rollout remains subject to the capacity receipt.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

MARKETS = frozenset({"B3", "NASDAQ", "NYSE"})
CATALOGUE_SCHEMA = "OFFICIAL-LISTED-UNIVERSE-v1"
CATALOGUE_ANALYSIS = "official_listing_catalogue"
POPULATION_ANALYSIS = "valuation_pit_buy_population"
NASDAQ_LIST_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NYSE_LIST_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
B3_LIST_URL = (
    "https://bvmf.bmfbovespa.com.br/suplemento/ExecutaAcaoDownload.asp"
    "?arquivo=Titulos_Negociaveis.zip&server=L"
)


def utc(value: datetime | str) -> datetime:
    if not isinstance(value, (str, datetime)):
        raise ValueError("an instant must be a dated string or datetime")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        raise ValueError("an explicit timezone is required")
    return parsed.astimezone(timezone.utc)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def positive(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) and result > 0 else None


@dataclass(frozen=True)
class Listing:
    market: str
    symbol: str
    name: str
    security_type: str = "Stock"
    listing_class: str = "equity"
    isin: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Catalogue:
    market: str
    source_url: str
    source_format: str
    received_at: str
    source_date: str
    raw_sha256: str
    source_row_count: int
    excluded_counts: dict[str, int]
    listings: tuple[Listing, ...]

    def __post_init__(self) -> None:
        expected = {"B3": B3_LIST_URL, "NASDAQ": NASDAQ_LIST_URL, "NYSE": NYSE_LIST_URL}
        if self.market not in expected or self.source_url != expected[self.market]:
            raise ValueError("catalogue origin does not match its official market source")
        expected_format = "b3-titulos-220-v1" if self.market == "B3" else "nasdaq-trader-pipe-v1"
        if self.source_format != expected_format or not re.fullmatch(r"[a-f0-9]{64}", self.raw_sha256):
            raise ValueError("invalid catalogue format or source digest")
        if (isinstance(self.source_row_count, bool) or not isinstance(self.source_row_count, int)
                or any(isinstance(count, bool) or not isinstance(count, int) or count < 0
                       for count in self.excluded_counts.values())
                or self.source_row_count != len(self.listings) + sum(self.excluded_counts.values())):
            raise ValueError("official catalogue row counts do not reconcile")
        utc(self.received_at)
        if self.market == "B3":
            datetime.strptime(self.source_date, "%Y-%m-%d")
        else:
            utc(self.source_date)
        if not self.listings or len({item.symbol for item in self.listings}) != len(self.listings):
            raise ValueError("missing or duplicate official listing identity")
        if any(item.market != self.market or not item.symbol or not item.name
               or item.security_type not in {"Stock", "ETF", "Other"} for item in self.listings):
            raise ValueError("invalid official listing identity or type")

    def payload(self) -> dict[str, Any]:
        result = {"schema": CATALOGUE_SCHEMA, **asdict(self)}
        result["listings"] = [asdict(item) for item in self.listings]
        result["manifest_sha256"] = digest(result)
        return result


def _unique(listings: Iterable[Listing]) -> tuple[Listing, ...]:
    result: dict[str, Listing] = {}
    for item in listings:
        if not item.symbol or item.symbol in result:
            raise ValueError("missing or duplicate official listing identity")
        result[item.symbol] = item
    if not result:
        raise ValueError("official catalogue contains no in-scope listing")
    return tuple(sorted(result.values(), key=lambda item: item.symbol))


def _nasdaq_kind(name: str, etf: str) -> tuple[str, str]:
    if etf == "Y":
        return "ETF", "etf"
    # A word in the COMPANY NAME is not an instrument type: Our Bond's common
    # stock and an ADS describing the 'right to receive' shares are equities.
    # Ambiguous/non-ETF entries remain visible until their type is reviewed.
    if re.search(r"\b(COMMON STOCK|ORDINARY SHARES?|PREFERRED (STOCK|SHARES?)|"
                 r"DEPOSITARY SHARES?|DEPOSITORY SHARES?|CAPITAL STOCK)\b", name.upper()):
        return "Stock", "equity"
    return "Other", "classification_pending"


def parse_nasdaq_directory(raw: bytes, *, market: str, received_at: datetime) -> Catalogue:
    """Read the COMPLETE Nasdaq Trader directory, including its creation footer.

    ``otherlisted`` exchange N is NYSE; Arca/American are not silently re-labelled
    NYSE. ETFs and out-of-scope securities are counted separately, not promoted.
    """
    if market not in {"NASDAQ", "NYSE"}:
        raise ValueError("Nasdaq directory market must be NASDAQ or NYSE")
    lines = raw.decode("utf-8-sig").splitlines()
    if len(lines) < 3 or not lines[-1].startswith("File Creation Time:"):
        raise ValueError("missing official directory completion footer")
    footer = lines[-1].split("|", 1)[0].removeprefix("File Creation Time:").strip()
    if not re.fullmatch(r"\d{10}:?\d{2}", footer):
        raise ValueError("invalid directory creation time")
    created_at = datetime.strptime(footer.replace(":", ""), "%m%d%Y%H%M").replace(tzinfo=ZoneInfo("America/New_York"))
    rows = list(csv.DictReader(io.StringIO("\n".join(lines[:-1])), delimiter="|"))
    required = {"Security Name", "ETF", "Test Issue", "Symbol" if market == "NASDAQ" else "ACT Symbol"}
    if not required.issubset(rows[0] if rows else {}):
        raise ValueError("unexpected official directory columns")
    if market == "NYSE" and "Exchange" not in rows[0]:
        raise ValueError("otherlisted directory must identify the exchange")
    excluded: dict[str, int] = {}
    listings = []
    for row in rows:
        reason = None
        if row.get("Test Issue") not in {"Y", "N"} or row.get("ETF") not in {"Y", "N"}:
            raise ValueError("unknown official test/ETF flag")
        if row["Test Issue"] == "Y":
            reason = "test_issue"
        elif market == "NYSE" and row.get("Exchange") != "N":
            reason = "other_exchange"
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        symbol = row["Symbol" if market == "NASDAQ" else "ACT Symbol"].strip().upper()
        name = row["Security Name"].strip()
        if not name:
            raise ValueError("official listing name is missing")
        kind, listing_class = _nasdaq_kind(name, row["ETF"])
        listings.append(Listing(market, symbol, name, kind, listing_class, attributes=dict(row)))
    return Catalogue(market, NASDAQ_LIST_URL if market == "NASDAQ" else NYSE_LIST_URL,
                     "nasdaq-trader-pipe-v1", utc(received_at).isoformat(), created_at.isoformat(),
                     hashlib.sha256(raw).hexdigest(), len(rows), excluded, _unique(listings))


def parse_b3_titulos(raw: bytes, *, received_at: datetime) -> Catalogue:
    """Official 220-byte Títulos Negociáveis layout, with trailer reconciliation.

    All cash listings are retained. An unfamiliar specification stays visible as
    classification_pending; an undocumented ticker suffix never excludes a name.
    Fractional and derivative markets are counted separately from cash listings.
    """
    records = raw.splitlines()
    if len(records) < 3 or any(len(row) != 220 for row in records):
        raise ValueError("B3 directory requires complete 220-byte records")
    if records[0][:2] != b"00" or records[-1][:2] != b"09":
        raise ValueError("missing B3 header/trailer")
    if records[0][2:30].decode("latin-1").strip() != "TITULOS NEGOCIAVEIS":
        raise ValueError("unexpected B3 directory header")
    if int(records[-1][2:9]) != len(records):
        raise ValueError("B3 trailer count does not reconcile")
    source_date = records[0][30:40].decode("ascii")
    datetime.strptime(source_date, "%Y-%m-%d")
    companies = {}
    for row in records[1:-1]:
        if row[:2] == b"01":
            key = row[2:6].decode("latin-1").strip()
            name = row[6:66].decode("latin-1").strip()
            if key in companies or not key or not name:
                raise ValueError("missing or duplicate B3 company record")
            companies[key] = name
        elif row[:2] != b"02":
            raise ValueError("unknown B3 directory record type")
    listings, excluded = [], {}
    source_rows = 0
    for row in records[1:-1]:
        if row[:2] != b"02":
            continue
        source_rows += 1
        market_code = row[108:111].decode("ascii").strip()
        if market_code != "010":
            excluded["non_cash_market"] = excluded.get("non_cash_market", 0) + 1
            continue
        symbol = row[2:14].decode("latin-1").strip().upper()
        company = row[14:18].decode("latin-1").strip()
        if company not in companies:
            raise ValueError("B3 security has no company identity")
        spec = row[133:143].decode("latin-1").strip().upper()
        description = row[21:81].decode("latin-1").strip()
        if "ETF" in spec or "FUNDO DE INDICE" in description.upper():
            kind, listing_class = "ETF", "etf"
        elif re.match(r"^(ON|PN[A-Z]?|UNT|UNIT)(\s|$)", spec):
            kind, listing_class = "Stock", "equity"
        else:
            kind, listing_class = "Other", "classification_pending"
        listings.append(Listing("B3", symbol, companies[company], kind, listing_class,
                                row[81:93].decode("latin-1").strip() or None,
                                {"specification": spec, "bdi_code": row[18:21].decode("ascii"),
                                 "bdi_description": description, "market_code": market_code}))
    return Catalogue("B3", B3_LIST_URL, "b3-titulos-220-v1", utc(received_at).isoformat(), source_date,
                     hashlib.sha256(raw).hexdigest(), source_rows, excluded, _unique(listings))


def catalogue_from_payload(payload: Mapping[str, Any]) -> Catalogue:
    data = dict(payload)
    manifest = data.pop("manifest_sha256", None)
    if data.pop("schema", None) != CATALOGUE_SCHEMA:
        raise ValueError("unknown catalogue schema")
    if manifest != digest({"schema": CATALOGUE_SCHEMA, **data}):
        raise ValueError("catalogue manifest digest mismatch")
    if data.get("market") not in MARKETS:
        raise ValueError("unknown catalogue market")
    data["listings"] = _unique(Listing(**item) for item in data["listings"])
    if any(item.market != data["market"] for item in data["listings"]):
        raise ValueError("catalogue contains another market")
    utc(data["received_at"])
    return Catalogue(**data)


def buy_scope_allows(evidence: Mapping[str, Any] | None, *, market: str, symbol: str,
                     tp_source_version: str | None, now: datetime) -> bool:
    """A restrictive membership guard, never a replacement for the decisor gates.

    No scope is installed by this module. FAIL/VOID/missing/malformed/expired scope
    cannot grant permission. A pass for one version or exchange covers no other.
    """
    if not isinstance(evidence, Mapping) or evidence.get("schema") != "PIT-BUY-POPULATION-v1":
        return False
    try:
        entries = evidence["members"]
        return bool(
            evidence["market"] == market and evidence["verdict"] == "PASS"
            and evidence.get("approved_for_buy") is True
            and re.fullmatch(r"[a-f0-9]{64}", evidence["receipt_sha256"])
            and re.fullmatch(r"[a-f0-9]{64}", evidence["prereg_sha256"])
            and isinstance(tp_source_version, str) and tp_source_version
            and evidence["tp_source_version"] == tp_source_version
            and utc(evidence["valid_from"]) <= utc(now) < utc(evidence["valid_until"])
            and isinstance(entries, list) and all(isinstance(item, str) and item and item == item.strip().upper() for item in entries)
            and len(set(entries)) == len(entries)
            and evidence["population_sha256"] == digest(sorted(entries))
            and symbol in entries
        )
    except (KeyError, ValueError, TypeError):
        return False


def universe_response(catalogue: Catalogue, canonical_rows: Mapping[str, Mapping[str, Any]], *,
                      observations: Mapping[str, Mapping[str, Any]] | None = None,
                      population: Mapping[str, Any] | None = None,
                      now: datetime | None = None) -> dict[str, Any]:
    """Join ALL official stock/pending listings; no rank, minimum or quantity cap.

    ETFs stay on their existing path. Quote/size/liquidity observations can mark a
    minimum but cannot replace the immutable canonical TP or claim a generation.
    """
    instant = utc(now or datetime.now(timezone.utc))
    observations = observations or {}
    items = []
    for listing in catalogue.listings:
        if listing.security_type == "ETF":
            continue
        row = canonical_rows.get(listing.symbol) or {}
        observation = observations.get(listing.symbol) or {}
        price = positive(row.get("price")) or positive(observation.get("price"))
        market_cap = positive(row.get("market_cap")) or positive(observation.get("market_cap"))
        liquidity = (positive(row.get("adtv_90d")) or positive(row.get("cash_volume"))
                     or positive(observation.get("cash_volume")))
        thresholds = {"price": 1.0 if listing.market == "B3" else 3.0,
                      "market_cap": 750_000_000.0,
                      "liquidity": 5_000_000.0 if listing.market == "B3" else 20_000_000.0}
        badges = {key: {"value": value, "minimum": thresholds[key],
                        "status": "missing" if value is None else "passed" if value >= thresholds[key] else "below_minimum"}
                  for key, value in {"price": price, "market_cap": market_cap, "liquidity": liquidity}.items()}
        tp = positive(row.get("our_tp"))
        reasons = []
        if listing.listing_class == "classification_pending":
            reasons.append("listing_classification_pending")
        if price is None:
            reasons.append("price_missing")
        if not row:
            reasons.append("canonical_valuation_missing")
        elif tp is None:
            reasons.append("canonical_tp_missing")
        elif not (row.get("official_generation_id") and row.get("official_row_sha256") and row.get("tp_source_version")):
            reasons.append("canonical_provenance_missing")
        history_days = positive(row.get("history_days"))
        if "history_days" in row and (history_days is None or history_days < 40):
            reasons.append("insufficient_history")
        scope = buy_scope_allows(population, market=listing.market, symbol=listing.symbol,
                                tp_source_version=row.get("tp_source_version"), now=instant)
        existing_permission = row.get("decisor_verdict") == "COMPRA_PERMITIDA"
        items.append({
            "symbol": listing.symbol, "name": listing.name, "market": listing.market,
            "listing_class": listing.listing_class, "isin": listing.isin,
            "valuation_status": "not_evaluable" if reasons else "valued", "not_evaluable_reasons": reasons,
            "price": price, "our_tp": tp, "buy_in": positive(row.get("buy_in")),
            "minimum_badges": badges, "pit_buy_scope_verified": scope,
            "buy_permission": bool(existing_permission and scope and not reasons),
            "buy_permission_reason": ("existing_decisor_and_verified_pit_scope" if existing_permission and scope and not reasons
                                      else "pit_buy_scope_unverified" if not scope else "decisor_gates_not_passed"),
            **{key: row.get(key) for key in ("tp_source", "tp_source_version", "official_generation_id",
                                            "official_cycle_id", "official_row_sha256", "prediction_instant")},
        })
    payload = catalogue.payload()
    return {"market": catalogue.market, "generated_at": instant.isoformat(),
            "catalogue": {key: value for key, value in payload.items() if key != "listings"},
            "universe_size": len(items), "item_count": len(items),
            "valued_count": sum(item["valuation_status"] == "valued" for item in items),
            "not_evaluable_count": sum(item["valuation_status"] == "not_evaluable" for item in items),
            "etfs_on_existing_path": sum(item.security_type == "ETF" for item in catalogue.listings),
            "classification_pending_count": sum(item.listing_class == "classification_pending" for item in catalogue.listings),
            "classified_equity_count": sum(item.security_type == "Stock" for item in catalogue.listings),
            "quantity_limit": None, "items": items}


def read_universe(database: Any, market: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Read-only API path: no upstream fetch, producer build or database write."""
    from .valuation_official import current_generation, official_rows

    market = market.upper()
    if market not in MARKETS:
        raise ValueError("unknown market")
    stored = database.latest_analysis_snapshot(CATALOGUE_ANALYSIS, market)
    if not stored:
        raise LookupError("Official listing inventory has not been captured for this market")
    catalogue = catalogue_from_payload(stored["outputs"])
    if catalogue.market != market:
        raise ValueError("stored catalogue market mismatch")
    generation = current_generation(database)
    rows = official_rows(database, market, generation=generation) if generation else {}
    scope = database.latest_analysis_snapshot(POPULATION_ANALYSIS, market)
    return universe_response(catalogue, rows, population=scope.get("outputs") if scope else None, now=now)
