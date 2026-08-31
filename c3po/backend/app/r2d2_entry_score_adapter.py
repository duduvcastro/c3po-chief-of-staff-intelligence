from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from .database import Database


ADAPTER_VERSION = "R2D2-ENTRY-SCORE-ADAPTER-v1"

_SOURCE_SPECS = {
    "canonical": ("valuation_universe", "{market}_UNIVERSE"),
    "v2_data": ("valuation_v2_data", "{market}_V2_DATA"),
    "v2_peer_quality": ("valuation_v2_peer_quality", "{peer_market}_V2_PEER_QUALITY"),
    "v2_shadow": ("valuation_v2_shadow", "{market}_V2_SHADOW"),
    # This name is reserved by ENGINE_V3_SPEC.md for the future nightly stream.
    # A/B reports deliberately use a different analysis type and cannot satisfy it.
    "v3_shadow": ("valuation_v3_shadow", "{market}_V3_SHADOW"),
}


def _utc(value: datetime) -> datetime:
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc)


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        _json_ready(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc(parsed)


def _source_available_at(snapshot: Mapping[str, Any]) -> tuple[datetime, str]:
    published_at = _utc(snapshot["published_at"])
    explicit: list[datetime] = []
    for container_name in ("inputs", "outputs"):
        container = snapshot.get(container_name)
        if isinstance(container, Mapping):
            parsed = _timestamp(container.get("available_at"))
            if parsed is not None:
                explicit.append(parsed)
    if not explicit:
        return published_at, "analysis_snapshot.published_at"
    return max([published_at, *explicit]), "max(snapshot_published_at, source_available_at)"


def _result_rows(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    outputs = snapshot.get("outputs")
    if not isinstance(outputs, Mapping):
        return {}
    results = outputs.get("results")
    if isinstance(results, Mapping):
        return {
            str(symbol): dict(item)
            for symbol, item in results.items()
            if isinstance(item, Mapping)
        }
    rows = outputs.get("rows")
    if isinstance(rows, list):
        return {
            str(item.get("symbol")): dict(item)
            for item in rows
            if isinstance(item, Mapping) and item.get("symbol")
        }
    return {}


def _target_price(source: str, item: Mapping[str, Any]) -> float | None:
    fields = {
        "canonical": ("our_tp", "internal_tp"),
        "v2_shadow": ("v2_tp",),
        "v3_shadow": ("v3_tp",),
    }.get(source, ())
    for field in fields:
        value = _number(item.get(field))
        if value is not None and value > 0:
            return value
    return None


def _percentiles(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values.values())
    denominator = max(1, len(ordered) - 1)
    output: dict[str, float] = {}
    for symbol, value in values.items():
        below = sum(candidate < value for candidate in ordered)
        equal = sum(candidate == value for candidate in ordered)
        average_index = below + (equal - 1) / 2
        output[symbol] = round(average_index / denominator * 100, 6) if len(ordered) > 1 else 100.0
    return output


class R2D2EntryScoreAdapter:
    """Append-only observer of already-persisted valuation evidence.

    This class has no provider or valuation-engine dependency. Its return value
    is telemetry only and is never read by entry ordering or decision code.
    """

    def __init__(self, database: Database) -> None:
        self.database = database
        self._snapshot_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
        self._reference_cache: dict[str, dict[str, Any]] = {}
        if not hasattr(database, "_r2d2_entry_score_observations"):
            database._r2d2_entry_score_observations = []  # type: ignore[attr-defined]

    def record_cycle(
        self,
        *,
        experiment_id: str,
        cycle_id: str,
        policy_epoch: str,
        candidates: list[dict[str, Any]],
        decision_at: datetime,
    ) -> dict[str, Any]:
        policy_epoch = policy_epoch.strip()
        if not policy_epoch:
            raise ValueError("policy_epoch is required for entry-score observations")
        decision_at = _utc(decision_at)
        evaluated = [item for item in candidates if item.get("technical_reviewed") is not False]
        snapshots = self._snapshots({str(item["market"]) for item in evaluated}, decision_at)
        comparisons = self._comparisons(evaluated, snapshots, decision_at)
        rows = [
            self._observation(
                experiment_id=experiment_id,
                cycle_id=cycle_id,
                policy_epoch=policy_epoch,
                candidate=candidate,
                decision_at=decision_at,
                source_snapshots=snapshots.get(str(candidate["market"]), {}),
                comparisons=comparisons.get((str(candidate["market"]), str(candidate["symbol"])), {}),
            )
            for candidate in evaluated
        ]
        self._append(rows)
        return {
            "enabled": True,
            "version": ADAPTER_VERSION,
            "status": "healthy",
            "policy_epoch": policy_epoch,
            "attempted": len(evaluated),
            "written": len(rows),
            "failed": 0,
            "decision_at": decision_at.isoformat(),
        }

    def observations(self) -> list[dict[str, Any]]:
        if not self.database.database_url:
            return [dict(item) for item in self.database._r2d2_entry_score_observations]  # type: ignore[attr-defined]
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT id::text, experiment_id::text, cycle_id::text, policy_epoch,
                          adapter_version, decision_at, market, symbol, valuation_basis,
                          quote_as_of, canonical_composite_score, canonical_fundamental_score,
                          canonical_technical_score, canonical_risk_score, raw_cash_volume_usd,
                          spread_bps, source_references, valuation_comparisons,
                          candidate_context, candidate_sha256, created_at
                   FROM r2d2_entry_score_observations
                   ORDER BY decision_at, market, symbol"""
            ).fetchall()
        keys = (
            "id", "experiment_id", "cycle_id", "policy_epoch", "adapter_version",
            "decision_at", "market", "symbol", "valuation_basis", "quote_as_of",
            "canonical_composite_score", "canonical_fundamental_score",
            "canonical_technical_score", "canonical_risk_score", "raw_cash_volume_usd",
            "spread_bps", "source_references", "valuation_comparisons",
            "candidate_context", "candidate_sha256", "created_at",
        )
        return [dict(zip(keys, row)) for row in rows]

    def _snapshots(
        self,
        markets: set[str],
        decision_at: datetime,
    ) -> dict[str, dict[str, dict[str, Any] | None]]:
        output: dict[str, dict[str, dict[str, Any] | None]] = {}
        for market in sorted(markets):
            peer_market = "B3" if market == "B3" else "US"
            output[market] = {}
            for role, (analysis_type, entity_template) in _SOURCE_SPECS.items():
                entity_key = entity_template.format(market=market, peer_market=peer_market)
                cache_key = (analysis_type, entity_key)
                latest_published = self.database.latest_analysis_snapshot_published_at(
                    analysis_type, entity_key,
                )
                cached = self._snapshot_cache.get(cache_key)
                cached_published = cached.get("published_at") if cached else None
                if (
                    cached_published is not None
                    and latest_published is not None
                    and _utc(cached_published) == _utc(latest_published)
                    and _utc(cached_published) <= decision_at
                ):
                    snapshot = cached
                elif latest_published is None:
                    snapshot = None
                    self._snapshot_cache[cache_key] = None
                else:
                    snapshot = self.database.analysis_snapshot_at_or_before(
                        analysis_type, entity_key, decision_at,
                    )
                    if snapshot is not None:
                        snapshot = {
                            **snapshot,
                            "analysis_type": analysis_type,
                            "entity_key": entity_key,
                        }
                    self._snapshot_cache[cache_key] = snapshot
                output[market][role] = snapshot
        return output

    def _comparisons(
        self,
        candidates: list[dict[str, Any]],
        snapshots: dict[str, dict[str, dict[str, Any] | None]],
        decision_at: datetime,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        output: dict[tuple[str, str], dict[str, Any]] = {}
        for market in sorted({str(item["market"]) for item in candidates}):
            market_candidates = [item for item in candidates if str(item["market"]) == market]
            source_upside: dict[str, dict[str, float]] = {}
            for source in ("canonical", "v2_shadow", "v3_shadow"):
                snapshot = snapshots.get(market, {}).get(source)
                if snapshot is None:
                    source_upside[source] = {}
                    continue
                available_at, _ = _source_available_at(snapshot)
                rows = _result_rows(snapshot)
                values: dict[str, float] = {}
                for candidate in market_candidates:
                    symbol = str(candidate["symbol"])
                    item = rows.get(symbol)
                    price = _number(candidate.get("price"))
                    target = _target_price(source, item or {})
                    if available_at <= decision_at and price and target:
                        values[symbol] = round((target / price - 1) * 100, 6)
                source_upside[source] = values
            rankings = {source: _percentiles(values) for source, values in source_upside.items()}
            for candidate in market_candidates:
                key = (market, str(candidate["symbol"]))
                output[key] = {
                    source: {
                        "upside_percent": source_upside[source].get(key[1]),
                        "rank_percentile": rankings[source].get(key[1]),
                    }
                    for source in ("canonical", "v2_shadow", "v3_shadow")
                }
        return output

    def _observation(
        self,
        *,
        experiment_id: str,
        cycle_id: str,
        policy_epoch: str,
        candidate: dict[str, Any],
        decision_at: datetime,
        source_snapshots: dict[str, dict[str, Any] | None],
        comparisons: dict[str, Any],
    ) -> dict[str, Any]:
        source_references: dict[str, Any] = {}
        for role, snapshot in source_snapshots.items():
            if snapshot is None:
                source_references[role] = {
                    "status": "not_persisted",
                    "ab_report_eligible": False if role == "v3_shadow" else None,
                }
                continue
            reference = self._source_reference(snapshot)
            published_at = _timestamp(reference["published_at"])
            available_at = _timestamp(reference["available_at"])
            if published_at is None or available_at is None:
                raise ValueError("persisted snapshot reference has invalid timestamps")
            causal = published_at <= decision_at and available_at <= decision_at
            source_references[role] = {
                **reference,
                "status": "eligible" if causal else "not_yet_available",
                "causal_at_decision": causal,
            }
            if not causal and role in comparisons:
                comparisons[role] = {"upside_percent": None, "rank_percentile": None}

        context = {
            "market": str(candidate["market"]),
            "symbol": str(candidate["symbol"]),
            "price": _number(candidate.get("price")),
            "quote_as_of": _json_ready(candidate.get("quote_as_of")),
            "quote_status": candidate.get("quote_status"),
            "valuation_basis": candidate.get("valuation_basis"),
            "canonical_composite_score": _number(candidate.get("composite_score")),
            "canonical_fundamental_score": _number(candidate.get("fundamental_score")),
            "canonical_technical_score": _number(candidate.get("technical_score")),
            "canonical_risk_score": _number(candidate.get("risk_score")),
            "pretrade_rank": _number(candidate.get("pretrade_rank")),
            "raw_cash_volume_usd": _number(candidate.get("raw_cash_volume_usd")),
            "spread_bps": _number(candidate.get("spread_bps")),
            "entry_capacity_policy": _json_ready(candidate.get("entry_capacity_policy")),
        }
        return {
            "id": str(uuid4()),
            "experiment_id": experiment_id,
            "cycle_id": cycle_id,
            "policy_epoch": policy_epoch,
            "adapter_version": ADAPTER_VERSION,
            "decision_at": decision_at,
            "market": context["market"],
            "symbol": context["symbol"],
            "valuation_basis": context["valuation_basis"],
            "quote_as_of": candidate.get("quote_as_of"),
            "canonical_composite_score": context["canonical_composite_score"],
            "canonical_fundamental_score": context["canonical_fundamental_score"],
            "canonical_technical_score": context["canonical_technical_score"],
            "canonical_risk_score": context["canonical_risk_score"],
            "raw_cash_volume_usd": context["raw_cash_volume_usd"],
            "spread_bps": context["spread_bps"],
            "source_references": source_references,
            "valuation_comparisons": comparisons,
            "candidate_context": context,
            "candidate_sha256": _canonical_sha256(context),
            "created_at": datetime.now(timezone.utc),
        }

    def _source_reference(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        snapshot_id = str(snapshot["id"])
        cached = self._reference_cache.get(snapshot_id)
        if cached is not None:
            return dict(cached)
        published_at = _utc(snapshot["published_at"])
        available_at, availability_basis = _source_available_at(snapshot)
        payload = {
            "id": snapshot_id,
            "analysis_type": str(snapshot["analysis_type"]),
            "entity_key": str(snapshot["entity_key"]),
            "methodology_version_id": str(snapshot.get("methodology_version_id") or ""),
            "inputs": snapshot.get("inputs") or {},
            "outputs": snapshot.get("outputs") or {},
            "published_at": published_at.isoformat(),
        }
        reference = {
            "snapshot_id": snapshot_id,
            "snapshot_sha256": _canonical_sha256(payload),
            "published_at": published_at.isoformat(),
            "available_at": available_at.isoformat(),
            "availability_basis": availability_basis,
        }
        self._reference_cache[snapshot_id] = reference
        return dict(reference)

    def _append(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        if not self.database.database_url:
            self.database._r2d2_entry_score_observations.extend(rows)  # type: ignore[attr-defined]
            return
        with self.database.connection() as connection:
            for row in rows:
                connection.execute(
                    """INSERT INTO r2d2_entry_score_observations
                           (id, experiment_id, cycle_id, policy_epoch, adapter_version,
                            decision_at, market, symbol, valuation_basis, quote_as_of,
                            canonical_composite_score, canonical_fundamental_score,
                            canonical_technical_score, canonical_risk_score,
                            raw_cash_volume_usd, spread_bps, source_references,
                            valuation_comparisons, candidate_context, candidate_sha256, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                               %s::jsonb,%s::jsonb,%s::jsonb,%s,%s)""",
                    (
                        row["id"], row["experiment_id"], row["cycle_id"], row["policy_epoch"],
                        row["adapter_version"], row["decision_at"], row["market"], row["symbol"],
                        row["valuation_basis"], row["quote_as_of"],
                        row["canonical_composite_score"], row["canonical_fundamental_score"],
                        row["canonical_technical_score"], row["canonical_risk_score"],
                        row["raw_cash_volume_usd"], row["spread_bps"],
                        json.dumps(row["source_references"]),
                        json.dumps(row["valuation_comparisons"]),
                        json.dumps(row["candidate_context"]), row["candidate_sha256"], row["created_at"],
                    ),
                )
            connection.commit()
