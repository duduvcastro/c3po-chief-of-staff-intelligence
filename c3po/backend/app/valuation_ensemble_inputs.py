"""Inputs for the independent valuation ensemble. No network, store or served-source imports.

The caller supplies official facts already reduced to the declared units/periods. A value is
usable only with its document and availability evidence. Model premises are recorded
separately: they are design assumptions, never presented as historical market observations.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo


class NotEvaluable(ValueError):
    """A missing or inadmissible input, with a stable reason for the receipt."""


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise NotEvaluable("instant_without_timezone")
    return value.astimezone(timezone.utc)


def number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise NotEvaluable(f"invalid_number:{name}")
    return float(value)


@dataclass(frozen=True)
class Evidence:
    source: str
    document_id: str
    available_at: datetime
    payload_sha256: str

    def check(self, as_of: datetime, allowed: set[str]) -> None:
        if not isinstance(self.source, str) or self.source not in allowed:
            raise NotEvaluable(f"source_not_allowed:{self.source}")
        if (not isinstance(self.document_id, str) or not self.document_id.strip()
                or not isinstance(self.payload_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.payload_sha256)):
            raise NotEvaluable("missing_document_or_hash")
        if utc(self.available_at) > utc(as_of):
            raise NotEvaluable("available_after_T")

    def receipt(self) -> dict[str, Any]:
        return {"source": self.source, "document_id": self.document_id,
                "available_at": utc(self.available_at).isoformat(), "payload_sha256": self.payload_sha256}


@dataclass(frozen=True)
class OfficialFact:
    value: float
    unit: str
    period_end: date
    evidence: Evidence


@dataclass(frozen=True)
class Price:
    value: float
    currency: str
    session_date: date
    basis_id: str
    evidence: Evidence


@dataclass(frozen=True)
class CompanyInputs:
    symbol: str
    market: str
    currency: str
    as_of: datetime
    basis_id: str
    price: Price
    facts: Mapping[str, OfficialFact]
    sector: str = ""
    sector_evidence: Evidence | None = None
    financial_company: bool = False
    issuer_id: str = ""

    def validate(self) -> None:
        cut = utc(self.as_of)
        if (not isinstance(self.market, str) or self.market not in {"NASDAQ", "NYSE", "B3"}
                or any(not isinstance(x, str) or not x.strip() for x in (self.symbol, self.basis_id, self.issuer_id))
                or not isinstance(self.financial_company, bool)):
            raise NotEvaluable("invalid_company_identity")
        if self.currency != ("BRL" if self.market == "B3" else "USD"):
            raise NotEvaluable("market_currency_mismatch")
        self.price.evidence.check(cut, {"PRICE"})
        if self.price.currency != self.currency or self.price.basis_id != self.basis_id:
            raise NotEvaluable("price_currency_or_share_basis_mismatch")
        if (type(self.price.session_date) is not date or self.price.session_date > self.economic_date()
                or number(self.price.value, "price") <= 0):
            raise NotEvaluable("invalid_or_future_price")

    def economic_date(self) -> date:
        zone = "America/Sao_Paulo" if self.market == "B3" else "America/New_York"
        return utc(self.as_of).astimezone(ZoneInfo(zone)).date()

    def get(self, name: str, *, positive: bool = False, nonnegative: bool = False) -> float:
        fact = self.facts.get(name)
        if not isinstance(fact, OfficialFact):
            raise NotEvaluable(f"missing_fact:{name}")
        try:
            fact.evidence.check(self.as_of, {"SEC"} if self.market != "B3" else {"CVM"})
            expected = "shares" if name == "shares" else self.currency
            if fact.unit != expected:
                raise NotEvaluable("unit_mismatch")
            if type(fact.period_end) is not date or fact.period_end > self.economic_date():
                raise NotEvaluable("period_after_T")
            value = number(fact.value, name)
            if positive and value <= 0:
                raise NotEvaluable("not_positive")
            if nonnegative and value < 0:
                raise NotEvaluable("negative")
            return value
        except NotEvaluable as exc:
            raise NotEvaluable(f"{name}:{exc}") from exc

    def sector_at_T(self) -> str:
        if not self.sector or self.sector_evidence is None:
            raise NotEvaluable("sector_unattested")
        self.sector_evidence.check(self.as_of, {"SEC"} if self.market != "B3" else {"CVM"})
        return self.sector


@dataclass(frozen=True)
class Premises:
    """Explicit design inputs; there are no default rates, growth paths or multiples."""
    policy_id: str
    scalars: Mapping[str, float] = field(default_factory=dict)
    annual_growth_path: tuple[float, ...] = ()
    minimum_peers: int = 3

    def get(self, name: str, *, positive: bool = False) -> float:
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise NotEvaluable("premise_policy_missing")
        if name not in self.scalars:
            raise NotEvaluable(f"missing_premise:{name}")
        value = number(self.scalars[name], name)
        if positive and value <= 0:
            raise NotEvaluable(f"premise_not_positive:{name}")
        return value

    def receipt(self) -> dict[str, Any]:
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise NotEvaluable("premise_policy_missing")
        if isinstance(self.minimum_peers, bool) or not isinstance(self.minimum_peers, int) or self.minimum_peers < 3:
            raise NotEvaluable("minimum_peers_below_three")
        scalars = {name: number(value, name) for name, value in sorted(self.scalars.items())}
        growth = [number(value, "growth") for value in self.annual_growth_path]
        if any(value <= -1 for value in growth):
            raise NotEvaluable("growth_not_above_minus_one")
        return {"policy_id": self.policy_id, "kind": "explicit_design_premises_not_market_observations",
                "scalars": scalars, "annual_growth_path": growth, "minimum_peers": self.minimum_peers}


@dataclass(frozen=True)
class AnalystTarget:
    house: str
    target: float
    currency: str
    horizon_sessions: int
    evidence: Evidence


def analyst_consensus(targets: tuple[AnalystTarget, ...], company: CompanyInputs) -> tuple[float | None, dict[str, Any]]:
    """Arithmetic mean, one latest eligible observation per house; never an anchor.

    Horizon agreement is required rather than assumed to be twelve months. There is no
    implicit freshness window; that choice belongs to the future signed protocol.
    """
    latest: dict[str, AnalystTarget] = {}
    refused: dict[str, int] = {}
    for item in targets:
        try:
            item.evidence.check(company.as_of, {"ANALYST_CONSENSUS"})
            if not isinstance(item.house, str) or not item.house.strip() or item.currency != company.currency:
                raise NotEvaluable("house_or_currency_mismatch")
            if isinstance(item.horizon_sessions, bool) or not isinstance(item.horizon_sessions, int) or item.horizon_sessions <= 0:
                raise NotEvaluable("horizon_unattested")
            if number(item.target, "consensus_target") <= 0:
                raise NotEvaluable("target_not_positive")
            house_id = item.house.strip().casefold()
            item = AnalystTarget(house_id, float(item.target), item.currency, item.horizon_sessions, item.evidence)
            old = latest.get(house_id)
            if old is None or utc(item.evidence.available_at) > utc(old.evidence.available_at):
                latest[house_id] = item
            elif utc(item.evidence.available_at) == utc(old.evidence.available_at) and item != old:
                raise NotEvaluable("ambiguous_house_observation")
        except NotEvaluable as exc:
            refused[str(exc)] = refused.get(str(exc), 0) + 1
    ordered = [latest[key] for key in sorted(latest)]
    receipt = {"source": "analyst_consensus_mean", "eligible_houses": len(ordered), "refused": refused,
               "members": [{"house": x.house, "target": float(x.target), "horizon_sessions": x.horizon_sessions,
                            **x.evidence.receipt()} for x in ordered]}
    if not ordered:
        return None, {**receipt, "status": "not_evaluable", "reason": "no_attested_consensus"}
    if len({x.horizon_sessions for x in ordered}) != 1 or refused.get("ambiguous_house_observation"):
        return None, {**receipt, "status": "not_evaluable", "reason": "consensus_horizon_or_identity_ambiguous"}
    # Divide first so finite source targets cannot overflow solely while summing.
    value = math.fsum(float(x.target) / len(ordered) for x in ordered)
    return value, {**receipt, "status": "evaluated", "horizon_sessions": ordered[0].horizon_sessions, "value": value}
