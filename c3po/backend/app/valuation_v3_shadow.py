from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .database import Database
from .valuation_v3_engine import ENGINE_VERSION, ValuationV3Engine
from .valuation_v3_inputs import (
    attach_quality_to_multiples,
    build_quality_index,
    canonical_symbol,
)
from .valuation_v3_macro import (
    SCHEMA_VERSION as MACRO_SCHEMA_VERSION,
    SELIC_SOURCE,
    package_hash_is_valid,
    validate_us_curve_package,
)


ANALYSIS_TYPE = "valuation_v3_shadow"
METHODOLOGY_KEY = "valuation_v3_nightly_shadow"
METHODOLOGY_VERSION = 1
SCHEMA_VERSION = "VALUATION-V3-SHADOW-v1"
MARKETS = ("B3", "NASDAQ", "NYSE")
SAO_PAULO = ZoneInfo("America/Sao_Paulo")

_CURRENT_CYCLE_ROLES = {"chewie", "v2_data", "v2_shadow", "peer_quality"}
_SOURCE_SPECS = (
    *(("universe", market, "valuation_universe", f"{market}_UNIVERSE") for market in MARKETS),
    *(("v2_data", market, "valuation_v2_data", f"{market}_V2_DATA") for market in MARKETS),
    *(("chewie", market, "chewie_fundamentals", f"{market}_FUNDAMENTALS") for market in MARKETS),
    *(("v2_shadow", market, "valuation_v2_shadow", f"{market}_V2_SHADOW") for market in MARKETS),
    ("peer_quality", "B3", "valuation_v2_peer_quality", "B3_V2_PEER_QUALITY"),
    ("peer_quality", "US", "valuation_v2_peer_quality", "US_V2_PEER_QUALITY"),
    ("selic_macro", "B3", "valuation_macro_history", "B3_SELIC_REGIME"),
    ("treasury_macro", "US", "valuation_macro_rates", "US_5Y_INTERPOLATED"),
)


class ValuationV3ShadowInputError(RuntimeError):
    pass


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


def _timestamp(value: Any, *, label: str) -> datetime:
    if isinstance(value, datetime):
        return _utc(value)
    if not isinstance(value, str) or not value.strip():
        raise ValuationV3ShadowInputError(f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValuationV3ShadowInputError(f"{label} is invalid") from exc
    return _utc(parsed)


def _snapshot_payload(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(snapshot["id"]),
        "analysis_type": str(snapshot["analysis_type"]),
        "entity_key": str(snapshot["entity_key"]),
        "methodology_version_id": str(snapshot.get("methodology_version_id") or ""),
        "inputs": snapshot.get("inputs") or {},
        "outputs": snapshot.get("outputs") or {},
        "published_at": _utc(snapshot["published_at"]).isoformat(),
    }


def _outputs(snapshot: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    value = snapshot.get("outputs")
    if not isinstance(value, dict):
        raise ValuationV3ShadowInputError(f"{label} has invalid outputs")
    return value


def _rows(snapshot: Mapping[str, Any], market: str) -> list[dict[str, Any]]:
    rows = _outputs(snapshot, label=f"{market} universe").get("rows")
    return [
        row
        for row in (rows or [])
        if isinstance(row, dict)
        and row.get("symbol")
        and (market == "B3" or row.get("security_type") == "Stock")
    ]


def _packets(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    packets = _outputs(snapshot, label=str(snapshot["entity_key"])).get("packets")
    if not isinstance(packets, dict):
        return {}
    return {
        str(symbol): packet
        for symbol, packet in packets.items()
        if isinstance(packet, dict)
    }


def _chewie_items(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = _outputs(snapshot, label=str(snapshot["entity_key"])).get("items")
    return [item for item in (items or []) if isinstance(item, dict)]


def _multiples_index(
    market: str,
    rows_by_market: Mapping[str, list[dict[str, Any]]],
    chewie_by_market: Mapping[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    source_markets = ("B3",) if market == "B3" else ("NASDAQ", "NYSE")
    index: dict[str, dict[str, Any]] = {}
    for source_market in source_markets:
        for item in chewie_by_market[source_market]:
            symbol = str(item.get("symbol") or "")
            multiples = item.get("multiples")
            multiples = multiples if isinstance(multiples, dict) else {}
            profitability = item.get("profitability")
            profitability = profitability if isinstance(profitability, dict) else {}
            roe_percent = _number(profitability.get("roe_percent"))
            if symbol:
                index[symbol] = {
                    "pe": _number(multiples.get("pe")),
                    "forward_pe": _number(multiples.get("forward_pe")),
                    "ev_ebitda": _number(multiples.get("ev_ebitda")),
                    "price_to_book": _number(multiples.get("price_to_book")),
                    "roe": roe_percent / 100 if roe_percent is not None else None,
                }
    for source_market in source_markets:
        for row in rows_by_market[source_market]:
            symbol = str(row.get("symbol") or "")
            if not symbol:
                continue
            roe = _number(row.get("roe"))
            if roe is None:
                roe_percent = _number(row.get("roe_percent"))
                roe = roe_percent / 100 if roe_percent is not None else None
            index[symbol] = {
                "pe": _number(row.get("pe")),
                "forward_pe": _number(row.get("forward_pe")),
                "ev_ebitda": _number(row.get("ev_ebitda")),
                "price_to_book": _number(row.get("price_to_book")),
                "roe": roe,
            }
    return index


def _sector_medians(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {}
    sectors = sorted({str(row.get("sector") or "") for row in rows if row.get("sector")})
    for sector in sectors:
        by_metric: dict[str, float] = {}
        for metric in ("pe", "forward_pe", "ev_ebitda", "price_to_book"):
            values = [
                value
                for row in rows
                if str(row.get("sector") or "") == sector
                and (value := _number(row.get(metric))) is not None
                and value > 0
            ]
            if len(values) >= 5:
                by_metric[metric] = median(values)
        output[sector] = by_metric
    return output


def _peer_symbols(packet: Mapping[str, Any]) -> list[str]:
    return [
        str(peer.get("canonical_symbol") or peer.get("symbol"))
        for peer in packet.get("peers") or []
        if isinstance(peer, dict) and peer.get("symbol")
    ]


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _rounded_percentile(values: list[float], fraction: float) -> float | None:
    value = _percentile(values, fraction)
    return round(value, 4) if value is not None else None


def _result_metrics(results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    internal_abs: list[float] = []
    internal_signed: list[float] = []
    final_abs: list[float] = []
    by_profile: dict[str, dict[str, list[float]]] = {}
    models = Counter()
    attribution = Counter()
    quality_statuses = Counter()
    quality_bases = Counter()
    regime_statuses = Counter()
    beta_zeroed = 0
    largest: list[dict[str, Any]] = []

    for result in results.values():
        consensus = _number(result.get("consensus_tp"))
        internal = _number(result.get("v3_internal_tp"))
        final = _number(result.get("v3_tp"))
        profile = str(result.get("profile") or "unknown")
        profile_values = by_profile.setdefault(
            profile, {"internal_abs": [], "internal_signed": []}
        )
        if consensus and consensus > 0 and internal is not None:
            signed = internal / consensus - 1
            internal_signed.append(signed)
            internal_abs.append(abs(signed))
            profile_values["internal_signed"].append(signed)
            profile_values["internal_abs"].append(abs(signed))
            largest.append({
                "symbol": str(result.get("symbol")),
                "profile": profile,
                "internal_divergence": round(abs(signed), 4),
                "internal_signed_bias": round(signed, 4),
                "attribution_model": result.get("attribution_model"),
            })
        if consensus and consensus > 0 and final is not None:
            final_abs.append(abs(final / consensus - 1))
        for model_name, model in (result.get("models") or {}).items():
            models[str(model_name)] += 1
            if isinstance(model, dict) and model.get("regime_status"):
                regime_statuses[str(model["regime_status"])] += 1
        attribution[str(result.get("attribution_model") or "none")] += 1
        for audit in (result.get("fair_multiple_audits") or {}).values():
            if not isinstance(audit, dict):
                continue
            quality_statuses[str(audit.get("quality_adjustment_status") or "missing")] += 1
            quality_bases[str(audit.get("quality_basis") or "none")] += 1
            beta_zeroed += int(bool(audit.get("quality_beta_zeroed_negative")))
            regime = audit.get("regime_adjustment")
            if isinstance(regime, dict):
                regime_statuses[str(regime.get("regime_status") or "missing")] += 1

    low_conviction = sum(bool(item.get("low_conviction")) for item in results.values())
    return {
        "evaluated": len(results),
        "with_consensus": len(internal_abs),
        "internal_divergence_p50": _rounded_percentile(internal_abs, 0.50),
        "internal_divergence_p90": _rounded_percentile(internal_abs, 0.90),
        "internal_signed_bias_median": (
            round(median(internal_signed), 4) if internal_signed else None
        ),
        "final_divergence_p50": _rounded_percentile(final_abs, 0.50),
        "final_divergence_p90": _rounded_percentile(final_abs, 0.90),
        "low_conviction": low_conviction,
        "low_conviction_rate": round(low_conviction / len(results), 4) if results else None,
        "by_profile": {
            profile: {
                "count": len(values["internal_abs"]),
                "internal_divergence_p50": _rounded_percentile(
                    values["internal_abs"], 0.50
                ),
                "internal_divergence_p90": _rounded_percentile(
                    values["internal_abs"], 0.90
                ),
                "internal_signed_bias_median": (
                    round(median(values["internal_signed"]), 4)
                    if values["internal_signed"] else None
                ),
            }
            for profile, values in sorted(by_profile.items())
        },
        "model_availability": dict(sorted(models.items())),
        "attribution_models": dict(sorted(attribution.items())),
        "largest_internal_divergences": sorted(
            largest,
            key=lambda item: (-float(item["internal_divergence"]), str(item["symbol"])),
        )[:15],
        "quality_adjustment_statuses": dict(sorted(quality_statuses.items())),
        "quality_bases": dict(sorted(quality_bases.items())),
        "quality_beta_zeroed_negative": beta_zeroed,
        "regime_statuses": dict(sorted(regime_statuses.items())),
    }


class ValuationV3ShadowService:
    """Persist the authorized V3 stream from already-persisted evidence only.

    The service has no provider client and exposes no valuation result to a
    decision path. The R2D2 entry-score adapter may observe these immutable
    snapshots after the decision path, but it cannot influence a trade.
    """

    def __init__(self, database: Database) -> None:
        self.database = database

    def run_all(self, *, now: datetime | None = None) -> dict[str, dict[str, Any]]:
        run_at = _utc(now or datetime.now(timezone.utc))
        local_run_at = run_at.astimezone(SAO_PAULO)
        cycle_floor = datetime.combine(local_run_at.date(), time(1), tzinfo=SAO_PAULO)
        if local_run_at < cycle_floor:
            raise ValuationV3ShadowInputError(
                "V3 shadow cannot run before the 01:00 America/Sao_Paulo cycle"
            )

        loaded, source_references = self._load_sources(
            run_at=run_at, cycle_floor=cycle_floor
        )
        evaluation_date = local_run_at.date()
        selic_package = self._validate_selic_package(
            loaded[("selic_macro", "B3")], run_at=run_at, evaluation_date=evaluation_date
        )
        curve_package = self._validate_curve_package(
            loaded[("treasury_macro", "US")], run_at=run_at, evaluation_date=evaluation_date
        )
        b3_rate, b3_rate_source = self._b3_risk_free_rate(
            loaded[("v2_shadow", "B3")]
        )

        implementation_files = {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in (
                "valuation_v3_engine.py",
                "valuation_v3_inputs.py",
                "valuation_v3_macro.py",
                "valuation_v3_shadow.py",
            )
        }
        source_manifest = {
            "schema_version": SCHEMA_VERSION,
            "evaluation_date": evaluation_date.isoformat(),
            "engine_version": ENGINE_VERSION,
            "implementation_file_sha256": implementation_files,
            "snapshots": source_references,
            "macro_packages": {
                "B3": {
                    "as_of": str(selic_package["as_of"]),
                    "payload_sha256": str(selic_package["payload_sha256"]),
                },
                "US": {
                    "as_of": str(curve_package["as_of"]),
                    "payload_sha256": str(curve_package["payload_sha256"]),
                },
            },
            "b3_risk_free_rate": b3_rate,
            "b3_risk_free_source": b3_rate_source,
            "external_api_calls": 0,
            "consumer_change_authorized": False,
            "official_tp_replacement_authorized": False,
        }
        source_manifest_sha256 = _canonical_sha256(source_manifest)
        cycle_id = _canonical_sha256({
            "schema_version": SCHEMA_VERSION,
            "evaluation_date": evaluation_date.isoformat(),
            "source_manifest_sha256": source_manifest_sha256,
        })

        latest = self._latest_snapshots()
        matching = {
            market: snapshot
            for market, snapshot in latest.items()
            if self._cycle_id(snapshot) == cycle_id
            and self._run_status(snapshot) == "complete"
        }
        if len(matching) == len(MARKETS):
            return {
                market: {
                    **self._summary_from_snapshot(matching[market]),
                    "cycle_id": cycle_id,
                    "idempotent": True,
                }
                for market in MARKETS
            }

        matching_streaks = {
            self._operational_streak(snapshot) for snapshot in matching.values()
        }
        if len(matching_streaks) > 1:
            raise ValuationV3ShadowInputError(
                "Partial V3 shadow cycle has inconsistent operational streaks"
            )
        operational_streak = (
            next(iter(matching_streaks))
            if matching_streaks
            else self._prior_streak(latest, evaluation_date) + 1
        )

        contexts = self._contexts(loaded, as_of=evaluation_date)
        prepared: dict[str, dict[str, Any]] = {}
        for market in MARKETS:
            engine_market = "B3" if market == "B3" else "US"
            macro_as_of = date.fromisoformat(
                str(selic_package["as_of"] if market == "B3" else curve_package["as_of"])
            )
            engine = ValuationV3Engine(
                market=engine_market,
                risk_free_rate=b3_rate if market == "B3" else None,
                today=evaluation_date,
                macro_as_of=macro_as_of,
                us_curve_package=curve_package if market != "B3" else None,
                selic_package=selic_package if market == "B3" else None,
                enable_quality=True,
                enable_selic=True,
                enable_treasury=market != "B3",
            )
            results = self._evaluate_market(engine, contexts[market])
            row_symbols = [str(row.get("symbol")) for row in contexts[market]["rows"]]
            expected_symbols = set(row_symbols)
            if len(expected_symbols) != len(row_symbols):
                raise ValuationV3ShadowInputError(
                    f"V3 shadow universe contains duplicate symbols for {market}"
                )
            missing_symbols = sorted(expected_symbols - set(results))
            summary = {
                **_result_metrics(results),
                "universe_rows": len(row_symbols),
                "not_evaluated": len(missing_symbols),
                "not_evaluated_symbols": missing_symbols,
                "asset_count_status": (
                    "explained"
                    if len(results) + len(missing_symbols) == len(row_symbols)
                    else "unreconciled"
                ),
                "input_packets": len(contexts[market]["packets"]),
                "multiples_index": len(contexts[market]["multiples_with_quality"]),
                "quality_index": len(contexts[market]["quality_index"]),
                "macro_as_of": macro_as_of.isoformat(),
                "macro_staleness_calendar_days": (evaluation_date - macro_as_of).days,
            }
            if summary["asset_count_status"] != "explained":
                raise ValuationV3ShadowInputError(
                    f"V3 shadow asset count did not reconcile for {market}"
                )
            prepared[market] = {"results": results, "summary": summary}

        methodology_id = self.database.ensure_methodology_version(
            METHODOLOGY_KEY,
            METHODOLOGY_VERSION,
            {
                "schema_version": SCHEMA_VERSION,
                "engine_version": ENGINE_VERSION,
                "external_api_calls": 0,
                "source_mode": "persisted_snapshots_only",
                "consumer_change_authorized": False,
                "official_tp_replacement_authorized": False,
                "entry_score_adapter_decision_influence": False,
            },
            "Nightly V3 shadow, append-only and observed only after the entry path.",
        )
        output: dict[str, dict[str, Any]] = {}
        for market in MARKETS:
            if market in matching:
                snapshot_id = str(matching[market]["id"])
                idempotent = True
            else:
                inputs = {
                    "schema_version": SCHEMA_VERSION,
                    "market": market,
                    "evaluation_date": evaluation_date.isoformat(),
                    "cycle_id": cycle_id,
                    "source_manifest_sha256": source_manifest_sha256,
                    "source_references": source_references,
                    "available_at": run_at.isoformat(),
                    "external_api_calls": 0,
                    "consumer_change_authorized": False,
                    "official_tp_replacement_authorized": False,
                }
                outputs = {
                    "schema_version": SCHEMA_VERSION,
                    "available_at": run_at.isoformat(),
                    "run": {
                        "status": "complete",
                        "cycle_id": cycle_id,
                        "evaluation_date": evaluation_date.isoformat(),
                        "market": market,
                        "operational_streak": operational_streak,
                        "soak_eligible": operational_streak >= 10,
                        "all_markets_required": list(MARKETS),
                    },
                    "source_manifest": source_manifest,
                    "source_manifest_sha256": source_manifest_sha256,
                    "results": prepared[market]["results"],
                    "summary": prepared[market]["summary"],
                    "governance": {
                        "append_only": True,
                        "external_api_calls": 0,
                        "decision_consumer": False,
                        "consumer_change_authorized": False,
                        "official_tp_replacement_authorized": False,
                    },
                }
                snapshot_id = self.database.save_analysis_snapshot(
                    ANALYSIS_TYPE,
                    f"{market}_V3_SHADOW",
                    methodology_id,
                    inputs,
                    outputs,
                    run_at,
                )
                idempotent = False
            output[market] = {
                **prepared[market]["summary"],
                "snapshot_id": snapshot_id,
                "cycle_id": cycle_id,
                "operational_streak": operational_streak,
                "soak_eligible": operational_streak >= 10,
                "idempotent": idempotent,
            }
        return output

    def last_run_at(self) -> datetime | None:
        snapshots = self._latest_snapshots()
        if set(snapshots) != set(MARKETS):
            return None
        cycle_ids = {self._cycle_id(snapshot) for snapshot in snapshots.values()}
        if None in cycle_ids or len(cycle_ids) != 1:
            return None
        if any(self._run_status(snapshot) != "complete" for snapshot in snapshots.values()):
            return None
        published = [
            _utc(snapshot["published_at"])
            for snapshot in snapshots.values()
            if isinstance(snapshot.get("published_at"), datetime)
        ]
        return min(published) if len(published) == len(MARKETS) else None

    def _load_sources(
        self,
        *,
        run_at: datetime,
        cycle_floor: datetime,
    ) -> tuple[dict[tuple[str, str], dict[str, Any]], list[dict[str, Any]]]:
        loaded: dict[tuple[str, str], dict[str, Any]] = {}
        references: list[dict[str, Any]] = []
        for role, market, analysis_type, entity_key in _SOURCE_SPECS:
            raw = self.database.latest_analysis_snapshot(analysis_type, entity_key)
            if raw is None:
                raise ValuationV3ShadowInputError(
                    f"Missing persisted V3 shadow source: {role}/{market}"
                )
            published_at = raw.get("published_at")
            if not isinstance(published_at, datetime):
                raise ValuationV3ShadowInputError(
                    f"Persisted V3 shadow source has no timestamp: {role}/{market}"
                )
            published_at = _utc(published_at)
            if published_at > run_at:
                raise ValuationV3ShadowInputError(
                    f"Persisted V3 shadow source is from the future: {role}/{market}"
                )
            fresh_for_cycle = published_at.astimezone(SAO_PAULO) >= cycle_floor
            if role in _CURRENT_CYCLE_ROLES and not fresh_for_cycle:
                raise ValuationV3ShadowInputError(
                    f"Persisted V3 shadow source is stale for this cycle: {role}/{market}"
                )
            snapshot = {
                **raw,
                "analysis_type": analysis_type,
                "entity_key": entity_key,
                "published_at": published_at,
            }
            loaded[(role, market)] = snapshot
            references.append({
                "role": role,
                "market": market,
                "snapshot_id": str(snapshot["id"]),
                "analysis_type": analysis_type,
                "entity_key": entity_key,
                "methodology_version_id": str(
                    snapshot.get("methodology_version_id") or ""
                ),
                "published_at": published_at.isoformat(),
                "snapshot_sha256": _canonical_sha256(_snapshot_payload(snapshot)),
                "fresh_for_cycle": fresh_for_cycle,
                "staleness_seconds_at_cycle_floor": max(
                    0,
                    int(
                        (
                            cycle_floor.astimezone(timezone.utc) - published_at
                        ).total_seconds()
                    ),
                ),
            })
        return loaded, references

    @staticmethod
    def _validate_selic_package(
        snapshot: Mapping[str, Any],
        *,
        run_at: datetime,
        evaluation_date: date,
    ) -> dict[str, Any]:
        package = _outputs(snapshot, label="B3 Selic macro")
        if not package_hash_is_valid(package):
            raise ValuationV3ShadowInputError("B3 Selic package hash mismatch")
        if (
            package.get("schema_version") != MACRO_SCHEMA_VERSION
            or package.get("engine_version") != ENGINE_VERSION
            or package.get("source") != SELIC_SOURCE
        ):
            raise ValuationV3ShadowInputError("B3 Selic package metadata mismatch")
        try:
            macro_as_of = date.fromisoformat(str(package.get("as_of") or ""))
        except ValueError as exc:
            raise ValuationV3ShadowInputError("B3 Selic package as_of is invalid") from exc
        fetched_at = _timestamp(package.get("fetched_at"), label="B3 Selic fetched_at")
        if macro_as_of > evaluation_date or fetched_at > run_at:
            raise ValuationV3ShadowInputError("B3 Selic package is not causal for this run")
        observations = package.get("observations")
        if not isinstance(observations, list) or not observations:
            raise ValuationV3ShadowInputError("B3 Selic package has no observations")
        observation_dates: set[date] = set()
        for item in observations:
            if not isinstance(item, dict):
                raise ValuationV3ShadowInputError("B3 Selic package has an invalid observation")
            try:
                observed = date.fromisoformat(str(item.get("observation_date") or ""))
            except ValueError as exc:
                raise ValuationV3ShadowInputError(
                    "B3 Selic package has an invalid observation date"
                ) from exc
            available_at = _timestamp(
                item.get("available_at"), label="B3 Selic observation available_at"
            )
            rate = _number(item.get("annual_rate"))
            if (
                observed > macro_as_of
                or observed in observation_dates
                or available_at > fetched_at
                or rate is None
                or not 0 < rate < 1
            ):
                raise ValuationV3ShadowInputError(
                    "B3 Selic package contains a non-causal or invalid observation"
                )
            observation_dates.add(observed)
        if _utc(snapshot["published_at"]) < fetched_at:
            raise ValuationV3ShadowInputError(
                "B3 Selic snapshot was published before its package was fetched"
            )
        return package

    @staticmethod
    def _validate_curve_package(
        snapshot: Mapping[str, Any],
        *,
        run_at: datetime,
        evaluation_date: date,
    ) -> dict[str, Any]:
        package = _outputs(snapshot, label="US Treasury macro")
        try:
            macro_as_of = date.fromisoformat(str(package.get("as_of") or ""))
        except ValueError as exc:
            raise ValuationV3ShadowInputError("US curve package as_of is invalid") from exc
        fetched_at = _timestamp(package.get("fetched_at"), label="US curve fetched_at")
        if macro_as_of > evaluation_date or fetched_at > run_at:
            raise ValuationV3ShadowInputError("US curve package is not causal for this run")
        if _utc(snapshot["published_at"]) < fetched_at:
            raise ValuationV3ShadowInputError(
                "US curve snapshot was published before its package was fetched"
            )
        try:
            validate_us_curve_package(package, as_of=macro_as_of)
        except Exception as exc:
            raise ValuationV3ShadowInputError(str(exc)) from exc
        return package

    @staticmethod
    def _b3_risk_free_rate(snapshot: Mapping[str, Any]) -> tuple[float, str]:
        results = _outputs(snapshot, label="B3 V2 shadow").get("results")
        if not isinstance(results, dict) or not results:
            raise ValuationV3ShadowInputError("B3 V2 shadow has no persisted results")
        rates = {
            round(value, 12)
            for item in results.values()
            if isinstance(item, dict)
            and (value := _number(item.get("risk_free_rate"))) is not None
            and value > 0
        }
        sources = {
            str(item.get("risk_free_source") or "unknown")
            for item in results.values()
            if isinstance(item, dict) and _number(item.get("risk_free_rate")) is not None
        }
        if len(rates) != 1:
            raise ValuationV3ShadowInputError(
                "B3 V2 shadow risk-free rate is missing or inconsistent"
            )
        return next(iter(rates)), ",".join(sorted(sources)) or "unknown"

    @staticmethod
    def _contexts(
        loaded: Mapping[tuple[str, str], dict[str, Any]],
        *,
        as_of: date,
    ) -> dict[str, dict[str, Any]]:
        rows_by_market = {
            market: _rows(loaded[("universe", market)], market) for market in MARKETS
        }
        packets_by_market = {
            market: _packets(loaded[("v2_data", market)]) for market in MARKETS
        }
        chewie_by_market = {
            market: _chewie_items(loaded[("chewie", market)]) for market in MARKETS
        }
        contexts: dict[str, dict[str, Any]] = {}
        for market in MARKETS:
            multiples = _multiples_index(market, rows_by_market, chewie_by_market)
            source_markets = ("B3",) if market == "B3" else ("NASDAQ", "NYSE")
            peer_market = "B3" if market == "B3" else "US"
            quality_packets = dict(_packets(loaded[("peer_quality", peer_market)]))
            quality_items: list[dict[str, Any]] = []
            for source_market in source_markets:
                quality_packets.update(packets_by_market[source_market])
                quality_items.extend(chewie_by_market[source_market])
            quality_index = build_quality_index(
                quality_packets, quality_items, as_of=as_of
            )
            contexts[market] = {
                "rows": rows_by_market[market],
                "packets": packets_by_market[market],
                "multiples_with_quality": attach_quality_to_multiples(
                    multiples, quality_index
                ),
                "quality_index": quality_index,
                "sector_medians": _sector_medians(rows_by_market[market]),
            }
        return contexts

    @staticmethod
    def _evaluate_market(
        engine: ValuationV3Engine,
        context: Mapping[str, Any],
    ) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        multiples = context["multiples_with_quality"]
        for row in context["rows"]:
            symbol = str(row.get("symbol"))
            packet = context["packets"].get(symbol)
            peer_multiples = {
                peer: multiples[peer]
                for peer in _peer_symbols(packet or {})
                if peer in multiples and peer != symbol
            }
            result = engine.evaluate(
                row,
                packet,
                peer_multiples=peer_multiples,
                sector_fair_multiples=context["sector_medians"].get(
                    str(row.get("sector") or "")
                ),
                target_quality=context["quality_index"].get(
                    canonical_symbol(symbol), {}
                ),
            )
            if result is not None:
                result["peer_multiples_resolved"] = len(peer_multiples)
                results[symbol] = result
        return results

    def _latest_snapshots(self) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for market in MARKETS:
            snapshot = self.database.latest_analysis_snapshot(
                ANALYSIS_TYPE, f"{market}_V3_SHADOW"
            )
            if snapshot is not None:
                output[market] = snapshot
        return output

    @staticmethod
    def _cycle_id(snapshot: Mapping[str, Any]) -> str | None:
        outputs = snapshot.get("outputs")
        run = outputs.get("run") if isinstance(outputs, dict) else None
        value = run.get("cycle_id") if isinstance(run, dict) else None
        return str(value) if value else None

    @staticmethod
    def _run_status(snapshot: Mapping[str, Any]) -> str | None:
        outputs = snapshot.get("outputs")
        run = outputs.get("run") if isinstance(outputs, dict) else None
        value = run.get("status") if isinstance(run, dict) else None
        return str(value) if value else None

    @staticmethod
    def _operational_streak(snapshot: Mapping[str, Any]) -> int:
        outputs = snapshot.get("outputs")
        run = outputs.get("run") if isinstance(outputs, dict) else None
        try:
            return int(run.get("operational_streak")) if isinstance(run, dict) else 0
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _summary_from_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
        outputs = snapshot.get("outputs")
        summary = outputs.get("summary") if isinstance(outputs, dict) else None
        return dict(summary) if isinstance(summary, dict) else {}

    def _prior_streak(
        self,
        latest: Mapping[str, Mapping[str, Any]],
        evaluation_date: date,
    ) -> int:
        if set(latest) != set(MARKETS):
            return 0
        cycle_ids = {self._cycle_id(snapshot) for snapshot in latest.values()}
        statuses = {self._run_status(snapshot) for snapshot in latest.values()}
        streaks = {self._operational_streak(snapshot) for snapshot in latest.values()}
        dates: set[date] = set()
        for snapshot in latest.values():
            outputs = snapshot.get("outputs")
            run = outputs.get("run") if isinstance(outputs, dict) else None
            try:
                dates.add(date.fromisoformat(str(run.get("evaluation_date") or "")))
            except (AttributeError, ValueError):
                return 0
        if (
            None in cycle_ids
            or len(cycle_ids) != 1
            or statuses != {"complete"}
            or len(streaks) != 1
            or dates != {evaluation_date - timedelta(days=1)}
        ):
            return 0
        return next(iter(streaks))
