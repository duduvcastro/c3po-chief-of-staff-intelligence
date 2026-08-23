from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Literal, Mapping

from .config import Settings
from .database import Database
from .market_data.fmp import FmpClient
from .market_data.http import JsonHttpClient
from .valuation_v2_data import (
    ANALYSIS_TYPE as TARGET_ANALYSIS_TYPE,
    DATA_SCHEMA_VERSION as TARGET_DATA_SCHEMA_VERSION,
)
from .valuation_v2_engine import (
    EV_EBITDA_RANGE,
    PB_RANGE,
    PE_RANGE,
    _valid_multiple,
)
from .valuation_v3_engine import MIN_PEER_SAMPLE, QUALITY_BASES, QUALITY_PROFILES
from .valuation_v3_inputs import build_quality_index, canonical_symbol, fmp_forward_quality


PeerQualityMarket = Literal["B3", "US"]

ANALYSIS_TYPE = "valuation_v2_peer_quality"
METHODOLOGY_KEY = "valuation_v2_peer_quality_closure"
METHODOLOGY_VERSION = 1
DATA_SCHEMA_VERSION = "VALUATION-V2-PEER-QUALITY-v1"

_TARGET_MARKETS: dict[PeerQualityMarket, tuple[str, ...]] = {
    "B3": ("B3",),
    "US": ("NASDAQ", "NYSE"),
}
_ENDPOINTS = ("analyst_estimates", "key_metrics")
_FAILURE_STATUSES = {"error", "invalid_payload"}
_REJECTED_AB_CHEWIE_IDS = {
    "B3": "e86f90da-8dc3-4291-8645-25d5c30c246e",
    "NASDAQ": "b969e458-5184-426e-8ffb-4c1c1ac469f4",
    "NYSE": "bc45ee83-be9c-4cb3-8ec0-73468eb29811",
}
_MULTIPLE_BOUNDS = {
    "forward_pe": PE_RANGE,
    "pe": PE_RANGE,
    "ev_ebitda": EV_EBITDA_RANGE,
    "price_to_book": PB_RANGE,
}

logger = logging.getLogger("c3po.valuation_v2_peer_quality")


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ValuationV2PeerQualityService:
    """Close the direct-peer quality graph required by Valuation V3.1.

    This is a data-only service. It reads newly normalized V2.1 target
    packets, fetches only key metrics and analyst estimates for direct peers
    outside that target set, and persists an immutable evidence snapshot. It
    never imports into a valuation, screening or trading consumer.
    """

    def __init__(self, settings: Settings, database: Database, http: JsonHttpClient) -> None:
        self.settings = settings
        self.database = database
        self.fmp = FmpClient(settings.fmp_base_url, settings.fmp_api_token, http)

    def refresh_daily(self, market: PeerQualityMarket) -> dict[str, Any]:
        if not self.settings.fmp_api_token:
            return {
                "targets": 0,
                "unique_direct_peers": 0,
                "closure_attempted": 0,
                "fmp_forward_peers": 0,
                "pre_ab_ready": False,
            }

        target_snapshots = self._target_snapshots(market)
        self._require_current_target_schema(target_snapshots)
        target_packets = self._target_packets(target_snapshots)
        as_of = datetime.now(timezone.utc).date()
        if not target_packets:
            raise RuntimeError(f"Valuation V2.1b has no target packets for {market}")
        target_quality_count = sum(
            fmp_forward_quality(packet, as_of=as_of) is not None
            for packet in target_packets.values()
        )
        target_roe_count = sum(
            self._has_non_null_roe(packet, as_of=as_of)
            for packet in target_packets.values()
        )
        if target_roe_count == 0:
            raise RuntimeError(
                f"Valuation V2.1b target ROE gate failed for {market}: zero normalized ROE"
            )

        graph = self._direct_peer_graph(target_packets, market=market)
        target_symbols = set(target_packets)
        provider_by_peer = self._provider_symbols(graph)
        closure_symbols = sorted(set(provider_by_peer) - target_symbols)
        packets_by_provider = self.fmp.valuation_v2_peer_quality_batch(
            [provider_by_peer[symbol] for symbol in closure_symbols], workers=10
        )
        closure_packets: dict[str, dict[str, Any]] = {}
        for symbol in closure_symbols:
            provider_symbol = provider_by_peer[symbol]
            packet = packets_by_provider.get(provider_symbol) or self._missing_packet(provider_symbol)
            closure_packets[symbol] = {
                **packet,
                "symbol": symbol,
                "provider_symbol": provider_symbol,
                "coverage": self._packet_coverage(packet, as_of=as_of),
            }

        closure_summary = self._closure_summary(closure_packets)
        if closure_packets and closure_summary["endpoint_responses"] == 0:
            logger.error(
                "Valuation V2.1b provider outage market=%s attempted=%s endpoint_errors=%s; "
                "previous snapshot preserved",
                market,
                closure_summary["closure_attempted"],
                closure_summary["endpoint_errors"],
            )
            raise RuntimeError(f"FMP Valuation V2.1b provider outage for {market}")

        combined_packets = {**target_packets, **closure_packets}
        graph_sha256 = _canonical_sha256(graph)
        chewie_snapshots = self._chewie_snapshots(market)
        universe_snapshots = self._universe_snapshots(market)
        pre_ab_report = self._pre_ab_report(
            market=market,
            as_of=as_of,
            target_packets=target_packets,
            combined_packets=combined_packets,
            graph=graph,
            closure_packets=closure_packets,
            target_snapshots=target_snapshots,
            chewie_snapshots=chewie_snapshots,
            universe_snapshots=universe_snapshots,
        )
        summary = {
            "targets": len(target_packets),
            "target_roe_available": target_roe_count,
            "target_fmp_forward_quality": target_quality_count,
            "direct_peer_references": sum(len(peers) for peers in graph.values()),
            "unique_direct_peers": len(provider_by_peer),
            "direct_peers_already_in_targets": len(set(provider_by_peer) & target_symbols),
            **closure_summary,
            "graph_sha256": graph_sha256,
            "pre_ab_ready": bool(pre_ab_report["pre_ab_ready"]),
        }

        methodology_id = self.database.ensure_methodology_version(
            METHODOLOGY_KEY,
            METHODOLOGY_VERSION,
            {
                "scope": "direct_peers_only_no_recursion",
                "endpoints": "fmp_key_metrics_and_analyst_estimates",
                "min_peer_sample": MIN_PEER_SAMPLE,
                "consumers": "none_until_new_frozen_ab",
            },
            "Valuation V2.1b direct-peer quality closure for a new frozen V3 A/B.",
        )
        target_refs = self._snapshot_references(target_snapshots)
        chewie_refs = self._snapshot_references(chewie_snapshots)
        universe_refs = self._snapshot_references(universe_snapshots)
        self.database.save_analysis_snapshot(
            ANALYSIS_TYPE,
            f"{market}_V2_PEER_QUALITY",
            methodology_id,
            {
                "market": market,
                "as_of": as_of.isoformat(),
                "data_schema_version": DATA_SCHEMA_VERSION,
                "target_snapshots": target_refs,
                "chewie_snapshots": chewie_refs,
                "universe_snapshots": universe_refs,
                "graph_sha256": graph_sha256,
                **summary,
            },
            {
                "packets": closure_packets,
                "peer_graph": graph,
                "target_symbols": sorted(target_symbols),
                "data_schema_version": DATA_SCHEMA_VERSION,
                "target_snapshots": target_refs,
                "chewie_snapshots": chewie_refs,
                "universe_snapshots": universe_refs,
                "coverage_summary": summary,
                "pre_ab_report": pre_ab_report,
                "guardrails": {
                    "formula_change_authorized": False,
                    "shadow_v3_authorized": False,
                    "consumer_change_authorized": False,
                    "recursive_peer_fetch": False,
                },
            },
            datetime.now(timezone.utc),
        )
        return summary

    def refresh_all(self) -> dict[str, dict[str, Any]]:
        return {market: self.refresh_daily(market) for market in ("B3", "US")}

    def packets(self, market: PeerQualityMarket) -> dict[str, dict[str, Any]]:
        snapshot = self.database.latest_analysis_snapshot(
            ANALYSIS_TYPE, f"{market}_V2_PEER_QUALITY"
        )
        outputs = snapshot.get("outputs") if snapshot else None
        packets = outputs.get("packets") if isinstance(outputs, dict) else None
        if not isinstance(packets, dict):
            return {}
        return {
            str(symbol): packet
            for symbol, packet in packets.items()
            if isinstance(packet, dict)
        }

    def coverage_summary(self, market: PeerQualityMarket) -> dict[str, Any] | None:
        snapshot = self.database.latest_analysis_snapshot(
            ANALYSIS_TYPE, f"{market}_V2_PEER_QUALITY"
        )
        outputs = snapshot.get("outputs") if snapshot else None
        summary = outputs.get("coverage_summary") if isinstance(outputs, dict) else None
        return summary if isinstance(summary, dict) else None

    def pre_ab_report(self, market: PeerQualityMarket) -> dict[str, Any] | None:
        snapshot = self.database.latest_analysis_snapshot(
            ANALYSIS_TYPE, f"{market}_V2_PEER_QUALITY"
        )
        outputs = snapshot.get("outputs") if snapshot else None
        report = outputs.get("pre_ab_report") if isinstance(outputs, dict) else None
        return report if isinstance(report, dict) else None

    def last_refreshed_at(self) -> datetime | None:
        stamps: list[datetime] = []
        for market in ("B3", "US"):
            snapshot = self.database.latest_analysis_snapshot(
                ANALYSIS_TYPE, f"{market}_V2_PEER_QUALITY"
            )
            published = snapshot.get("published_at") if snapshot else None
            if not isinstance(published, datetime):
                return None
            stamps.append(
                published if published.tzinfo else published.replace(tzinfo=timezone.utc)
            )
        return min(stamps)

    def _target_snapshots(self, market: PeerQualityMarket) -> dict[str, dict[str, Any]]:
        keys = [f"{item}_V2_DATA" for item in _TARGET_MARKETS[market]]
        snapshots = self.database.latest_analysis_snapshots(TARGET_ANALYSIS_TYPE, keys)
        missing = [key for key in keys if key not in snapshots]
        if missing:
            raise RuntimeError(f"Valuation V2.1b missing target snapshots: {missing}")
        return snapshots

    @staticmethod
    def _require_current_target_schema(
        snapshots: Mapping[str, Mapping[str, Any]],
    ) -> None:
        stale = []
        for key, snapshot in snapshots.items():
            inputs = snapshot.get("inputs")
            schema = inputs.get("data_schema_version") if isinstance(inputs, dict) else None
            if schema != TARGET_DATA_SCHEMA_VERSION:
                stale.append(key)
        if stale:
            raise RuntimeError(
                "Valuation V2.1b requires target recollection with normalized ROE: "
                + ", ".join(sorted(stale))
            )

    @staticmethod
    def _target_packets(
        snapshots: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for key in sorted(snapshots):
            snapshot_outputs = snapshots[key].get("outputs")
            packets = (
                snapshot_outputs.get("packets")
                if isinstance(snapshot_outputs, dict)
                else None
            )
            for raw_symbol, packet in sorted((packets or {}).items()):
                if not isinstance(packet, dict):
                    continue
                symbol = canonical_symbol(str(raw_symbol))
                if symbol:
                    output.setdefault(symbol, packet)
        return output

    @staticmethod
    def _direct_peer_graph(
        target_packets: Mapping[str, Mapping[str, Any]],
        *,
        market: PeerQualityMarket,
    ) -> dict[str, list[dict[str, str]]]:
        graph: dict[str, list[dict[str, str]]] = {}
        for target, packet in sorted(target_packets.items()):
            peers: dict[str, str] = {}
            for item in packet.get("peers") or []:
                if not isinstance(item, dict):
                    continue
                provider = str(item.get("symbol") or "").strip().upper()
                canonical = canonical_symbol(
                    str(item.get("canonical_symbol") or provider)
                )
                if not provider or not canonical or canonical == target:
                    continue
                current = peers.get(canonical)
                if current is None or ValuationV2PeerQualityService._provider_rank(
                    provider, market=market
                ) < ValuationV2PeerQualityService._provider_rank(
                    current, market=market
                ):
                    peers[canonical] = provider
            graph[target] = [
                {"canonical_symbol": symbol, "provider_symbol": peers[symbol]}
                for symbol in sorted(peers)
            ]
        return graph

    @staticmethod
    def _provider_rank(
        provider_symbol: str, *, market: PeerQualityMarket,
    ) -> tuple[int, str]:
        has_b3_suffix = provider_symbol.endswith(".SA")
        preferred = has_b3_suffix if market == "B3" else not has_b3_suffix
        return (0 if preferred else 1, provider_symbol)

    @staticmethod
    def _provider_symbols(
        graph: Mapping[str, list[dict[str, str]]],
    ) -> dict[str, str]:
        candidates: dict[str, set[str]] = {}
        for peers in graph.values():
            for peer in peers:
                candidates.setdefault(peer["canonical_symbol"], set()).add(
                    peer["provider_symbol"]
                )
        return {
            symbol: sorted(provider_symbols)[0]
            for symbol, provider_symbols in sorted(candidates.items())
        }

    @staticmethod
    def _packet_coverage(packet: Mapping[str, Any], *, as_of: date) -> dict[str, Any]:
        statuses = packet.get("provider_status")
        statuses = statuses if isinstance(statuses, dict) else {}
        endpoint_statuses = [
            statuses.get(endpoint) if isinstance(statuses.get(endpoint), dict) else {}
            for endpoint in _ENDPOINTS
        ]
        provider_errors = sum(
            str(status.get("status") or "") in _FAILURE_STATUSES
            for status in endpoint_statuses
        )
        endpoint_responses = sum(
            str(status.get("status") or "") in {"ok", "empty"}
            for status in endpoint_statuses
        )
        endpoint_ok = sum(
            str(status.get("status") or "") == "ok" for status in endpoint_statuses
        )
        endpoint_empty = sum(
            str(status.get("status") or "") == "empty"
            for status in endpoint_statuses
        )
        quality = fmp_forward_quality(dict(packet), as_of=as_of)
        return {
            "provider_error_count": provider_errors,
            "endpoint_response_count": endpoint_responses,
            "endpoint_ok_count": endpoint_ok,
            "endpoint_empty_count": endpoint_empty,
            "roe_available": ValuationV2PeerQualityService._has_non_null_roe(
                packet, as_of=as_of
            ),
            "fmp_forward_quality": quality is not None,
        }

    @staticmethod
    def _has_non_null_roe(packet: Mapping[str, Any], *, as_of: date) -> bool:
        for row in packet.get("key_metrics_annual") or []:
            if not isinstance(row, dict) or _number(row.get("roe")) is None:
                continue
            try:
                fiscal_end = date.fromisoformat(str(row.get("fiscal_year_end") or ""))
            except ValueError:
                continue
            if fiscal_end <= as_of:
                return True
        return False

    @staticmethod
    def _closure_summary(packets: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
        coverages = [
            packet.get("coverage") if isinstance(packet.get("coverage"), dict) else {}
            for packet in packets.values()
        ]
        return {
            "closure_attempted": len(packets),
            "closure_calls_planned": len(packets) * len(_ENDPOINTS),
            "closure_calls_attempted": len(packets) * len(_ENDPOINTS),
            "closure_roe_available": sum(bool(item.get("roe_available")) for item in coverages),
            "fmp_forward_peers": sum(
                bool(item.get("fmp_forward_quality")) for item in coverages
            ),
            "provider_error_symbols": sum(
                bool(item.get("provider_error_count")) for item in coverages
            ),
            "endpoint_errors": sum(
                int(item.get("provider_error_count") or 0) for item in coverages
            ),
            "endpoint_responses": sum(
                int(item.get("endpoint_response_count") or 0) for item in coverages
            ),
            "endpoint_ok": sum(
                int(item.get("endpoint_ok_count") or 0) for item in coverages
            ),
            "endpoint_empty": sum(
                int(item.get("endpoint_empty_count") or 0) for item in coverages
            ),
        }

    def _pre_ab_report(
        self,
        *,
        market: PeerQualityMarket,
        as_of: date,
        target_packets: Mapping[str, dict[str, Any]],
        combined_packets: Mapping[str, dict[str, Any]],
        graph: Mapping[str, list[dict[str, str]]],
        closure_packets: Mapping[str, dict[str, Any]],
        target_snapshots: Mapping[str, Mapping[str, Any]],
        chewie_snapshots: Mapping[str, Mapping[str, Any]],
        universe_snapshots: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        quality_index = build_quality_index(
            dict(combined_packets), self._chewie_items(chewie_snapshots), as_of=as_of
        )
        by_market: dict[str, dict[str, Any]] = {}
        aggregate_eligibility = {
            metric: Counter(
                {"fmp_forward": 0, "chewie_trailing": 0, "unavailable": 0}
            )
            for metric in _MULTIPLE_BOUNDS
        }
        for target_market in _TARGET_MARKETS[market]:
            target_key = f"{target_market}_V2_DATA"
            market_packets = self._target_packets(
                {target_key: target_snapshots[target_key]}
            )
            multiples, profiles = self._multiples_and_profiles(
                target_market,
                chewie_snapshots,
                universe_snapshots,
            )
            market_report = self._market_eligibility(
                target_packets=market_packets,
                combined_packets=combined_packets,
                graph=graph,
                quality_index=quality_index,
                multiples=multiples,
                profiles=profiles,
                as_of=as_of,
            )
            by_market[target_market] = market_report
            for metric, counts in market_report[
                "structural_eligibility_by_metric"
            ].items():
                aggregate_eligibility[metric].update(counts)

        target_roe_by_market = {
            target_market: report["target_roe_non_null"]
            for target_market, report in by_market.items()
        }
        target_roe = sum(target_roe_by_market.values())
        profile_not_eligible = sum(
            report["profile_not_eligible"] for report in by_market.values()
        )
        target_schema_current = all(
            isinstance(snapshot.get("inputs"), dict)
            and snapshot["inputs"].get("data_schema_version") == TARGET_DATA_SCHEMA_VERSION
            for snapshot in target_snapshots.values()
        )
        closure_fully_attempted = len(closure_packets) == len(
            set(self._provider_symbols(graph)) - set(target_packets)
        )
        chewie_new = bool(chewie_snapshots) and all(
            str(snapshot.get("id") or "") != _REJECTED_AB_CHEWIE_IDS.get(key.split("_")[0])
            for key, snapshot in chewie_snapshots.items()
        )
        fmp_forward_by_market = {
            target_market: sum(
                counts["fmp_forward"]
                for counts in report["structural_eligibility_by_metric"].values()
            )
            for target_market, report in by_market.items()
        }
        fmp_forward_legs = sum(fmp_forward_by_market.values())
        gates = {
            "target_schema_current": target_schema_current,
            "target_roe_non_null": all(
                value > 0 for value in target_roe_by_market.values()
            ),
            "closure_fully_attempted": closure_fully_attempted,
            "chewie_snapshot_new_since_rejected_ab": chewie_new,
            "fmp_forward_structural_eligibility_nonzero": all(
                value > 0 for value in fmp_forward_by_market.values()
            ),
        }
        return {
            "as_of": as_of.isoformat(),
            "market": market,
            "target_count": len(target_packets),
            "target_roe_non_null": target_roe,
            "target_roe_by_market": target_roe_by_market,
            "profile_not_eligible": profile_not_eligible,
            "fmp_forward_eligible_legs": fmp_forward_legs,
            "fmp_forward_eligible_legs_by_market": fmp_forward_by_market,
            "structural_eligibility_by_metric": {
                metric: dict(counts)
                for metric, counts in aggregate_eligibility.items()
            },
            "by_market": by_market,
            "gates": gates,
            "pre_ab_ready": all(gates.values()),
            "formula_change_authorized": False,
            "shadow_v3_authorized": False,
            "consumer_change_authorized": False,
        }

    @staticmethod
    def _market_eligibility(
        *,
        target_packets: Mapping[str, dict[str, Any]],
        combined_packets: Mapping[str, dict[str, Any]],
        graph: Mapping[str, list[dict[str, str]]],
        quality_index: Mapping[str, dict[str, dict[str, Any]]],
        multiples: Mapping[str, dict[str, Any]],
        profiles: Mapping[str, str],
        as_of: date,
    ) -> dict[str, Any]:
        eligibility = {
            metric: Counter(
                {"fmp_forward": 0, "chewie_trailing": 0, "unavailable": 0}
            )
            for metric in _MULTIPLE_BOUNDS
        }
        target_with_peer_list = 0
        target_with_min_peer_references = 0
        target_with_min_peers_attempted = 0
        target_with_min_fmp_forward_pairs = 0
        profile_not_eligible = 0
        for symbol in sorted(target_packets):
            peer_symbols = [
                item["canonical_symbol"] for item in graph.get(symbol, [])
            ]
            target_with_peer_list += bool(peer_symbols)
            target_with_min_peer_references += len(peer_symbols) >= MIN_PEER_SAMPLE
            target_with_min_peers_attempted += (
                sum(peer in combined_packets for peer in peer_symbols)
                >= MIN_PEER_SAMPLE
            )
            target_quality = quality_index.get(symbol, {})
            fmp_forward_pairs = (
                sum(
                    "fmp_forward" in quality_index.get(peer, {})
                    for peer in peer_symbols
                )
                if "fmp_forward" in target_quality
                else 0
            )
            target_with_min_fmp_forward_pairs += (
                fmp_forward_pairs >= MIN_PEER_SAMPLE
            )

            if profiles.get(symbol) not in QUALITY_PROFILES:
                profile_not_eligible += 1
                for metric in eligibility:
                    eligibility[metric]["unavailable"] += 1
                continue
            for metric, bounds in _MULTIPLE_BOUNDS.items():
                selected_basis: str | None = None
                for basis in QUALITY_BASES:
                    if basis not in target_quality:
                        continue
                    complete = sum(
                        basis in quality_index.get(peer, {})
                        and peer in multiples
                        and _valid_multiple(multiples[peer].get(metric), bounds)
                        is not None
                        for peer in peer_symbols
                    )
                    if complete >= MIN_PEER_SAMPLE:
                        selected_basis = basis
                        break
                eligibility[metric][selected_basis or "unavailable"] += 1

        return {
            "target_count": len(target_packets),
            "target_roe_non_null": sum(
                ValuationV2PeerQualityService._has_non_null_roe(
                    packet, as_of=as_of
                )
                for packet in target_packets.values()
            ),
            "target_with_peer_list": target_with_peer_list,
            "target_with_min_peer_references": target_with_min_peer_references,
            "target_with_min_peers_attempted": target_with_min_peers_attempted,
            "target_with_min_fmp_forward_pairs": target_with_min_fmp_forward_pairs,
            "profile_not_eligible": profile_not_eligible,
            "structural_eligibility_by_metric": {
                metric: dict(counts) for metric, counts in eligibility.items()
            },
        }

    def _chewie_snapshots(
        self, market: PeerQualityMarket,
    ) -> dict[str, dict[str, Any]]:
        keys = [f"{item}_FUNDAMENTALS" for item in _TARGET_MARKETS[market]]
        return self.database.latest_analysis_snapshots("chewie_fundamentals", keys)

    def _universe_snapshots(
        self, market: PeerQualityMarket,
    ) -> dict[str, dict[str, Any]]:
        keys = [f"{item}_UNIVERSE" for item in _TARGET_MARKETS[market]]
        snapshots = self.database.latest_analysis_snapshots(
            "valuation_universe", keys
        )
        missing = [key for key in keys if key not in snapshots]
        if missing:
            raise RuntimeError(
                f"Valuation V2.1b missing universe snapshots: {missing}"
            )
        return snapshots

    @staticmethod
    def _chewie_items(
        snapshots: Mapping[str, Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for key in sorted(snapshots):
            snapshot_outputs = snapshots[key].get("outputs")
            items = snapshot_outputs.get("items") if isinstance(snapshot_outputs, dict) else None
            output.extend(item for item in (items or []) if isinstance(item, dict))
        return output

    def _multiples_and_profiles(
        self,
        target_market: str,
        chewie_snapshots: Mapping[str, Mapping[str, Any]],
        universe_snapshots: Mapping[str, Mapping[str, Any]],
    ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        multiples: dict[str, dict[str, Any]] = {}
        for item in self._chewie_items(chewie_snapshots):
            symbol = canonical_symbol(str(item.get("symbol") or ""))
            raw_multiples = item.get("multiples")
            raw_multiples = raw_multiples if isinstance(raw_multiples, dict) else {}
            if symbol:
                multiples[symbol] = {
                    metric: _number(raw_multiples.get(metric)) for metric in _MULTIPLE_BOUNDS
                }

        profiles: dict[str, str] = {}
        snapshot = universe_snapshots[f"{target_market}_UNIVERSE"]
        outputs = snapshot.get("outputs")
        rows = outputs.get("rows") if isinstance(outputs, dict) else None
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            symbol = canonical_symbol(str(row.get("symbol") or ""))
            if not symbol:
                continue
            profiles[symbol] = str(row.get("valuation_profile") or "")
            multiples[symbol] = {
                metric: _number(row.get(metric)) for metric in _MULTIPLE_BOUNDS
            }
        return multiples, profiles

    @staticmethod
    def _snapshot_references(
        snapshots: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for key, snapshot in sorted(snapshots.items()):
            published = snapshot.get("published_at")
            output[key] = {
                "id": str(snapshot.get("id") or ""),
                "published_at": (
                    published.astimezone(timezone.utc).isoformat()
                    if isinstance(published, datetime) and published.tzinfo
                    else str(published or "")
                ),
            }
        return output

    @staticmethod
    def _missing_packet(provider_symbol: str) -> dict[str, Any]:
        missing_status = {
            "status": "error",
            "error_type": "MissingBatchResult",
            "raw_rows": 0,
            "parsed_rows": 0,
        }
        return {
            "symbol": provider_symbol,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "analyst_estimates_annual": [],
            "key_metrics_annual": [],
            "provider_status": {
                endpoint: dict(missing_status) for endpoint in _ENDPOINTS
            },
        }


def main() -> int:
    from .config import get_settings
    from .market_data.service import MarketDataService
    from .valuation_v2_data import _configure_cli_logging

    _configure_cli_logging()
    settings = get_settings()
    database = Database(settings)
    database.initialize()
    market_data = MarketDataService(settings, database)
    service = ValuationV2PeerQualityService(settings, database, market_data.http)
    summaries = service.refresh_all()
    print(json.dumps(
        {
            "summaries": summaries,
            "pre_ab_reports": {
                market: service.pre_ab_report(market) for market in ("B3", "US")
            },
        },
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
