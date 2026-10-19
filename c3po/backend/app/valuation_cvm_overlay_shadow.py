"""CVM field-wise overlay — the shadow of the nightly B3 build and its read-only before/after receipt (owner 2026-10-19).

The owner's direction: the B3 TP is computed from the OFFICIAL CVM statements (DFP/ITR, DRE/DVA/DFC/BP, collected by the
IR worker into ``official_statements``) as the source of record, EODHD only as the per-field fallback. The field-wise
overlay exists (``official_statements.apply_official_statements``) and is served only under
``C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_ENABLED``. Before the owner turns it on, this module measures what it would change:

1. **Shadow** (``C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_SHADOW``, ``valuation_env``; off by default). The nightly B3 build
   hands every EODHD payload it consumed to a ``ShadowCapture`` (the SAME payloads, at the same instant as the served
   overlay); after the served cycle is published the build values the universe a second time under the field-wise
   overlay — the same catalog, quotes, Brapi statistics, history, macro and consensus — and this module persists ONE
   snapshot per cycle (``analysis_snapshots``, ``analysis_type = valuation_cvm_overlay_shadow``, entity ``B3_UNIVERSE``):
   an ``aggregate`` without a single symbol (per-field source counts, EBITDA corrections, the internal TP and buy-in
   before → after as median/p90 of ``after/before − 1`` and of its size) and a ``private_detail`` keyed by symbol that
   never leaves the host database (the aggregate carries its hash). Nothing here is served, recorded as a prediction or
   selectable (``valuation_official.market_of_entity`` ignores the type); a failure is logged and the build goes on.
2. **Receipt** (``python -m app.valuation_cvm_overlay_shadow --before-after``; ``valuation-readonly-report.yml``,
   ``report=cvm-before-after``). Reads the latest shadow snapshot, re-hashes its aggregate (``report_sha256``, stored by
   the producer, must recompute), and prints the aggregate with the snapshot's identity, the build that PRODUCED the
   aggregate (``producer_build_sha``, ``C3PO_BUILD_SHA`` read by the nightly process that computed it) and the build that
   read it (``reader_build_sha``), all bound by ``receipt_sha256`` — the pattern of the P1 receipt
   (``valuation_official.attest_before_after``), in a module of its own. ``before_after_markdown`` renders the Portuguese
   summary from the receipt alone.

``report_sha256`` names the CONTENT the owner accepts (no build identity inside, as in P1); ``receipt_sha256`` binds the
content to its snapshot and to both builds.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .official_statements import (
    SOURCE_FIELDS,
    SOURCES,
    apply_official_statements,
    fieldwise_sources,
    official_overlays,
)
from .valuation_official import canonical_sha256

logger = logging.getLogger(__name__)

ANALYSIS_TYPE = "valuation_cvm_overlay_shadow"
ENTITY_KEY = "B3_UNIVERSE"
SNAPSHOT_SCHEMA = "VALUATION_CVM_OVERLAY_SHADOW_V1"
RECEIPT_SCHEMA = "VALUATION_CVM_BEFORE_AFTER_V1"
METHODOLOGY_KEY = "valuation_cvm_overlay_shadow"
METHODOLOGY_VERSION = 1
METHODOLOGY_PARAMETERS = {
    "before": "the served nightly B3 build (legacy overlay unless C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_ENABLED)",
    "after": "the same build inputs valued under official_statements.apply_official_statements (field-wise CVM overlay)",
    "ratio": "after / before - 1 of the internal TP and of the internal buy-in, names valued in both with positive values",
    "quantiles": "linear interpolation between order statistics (numpy's default)",
    "privacy": "per-symbol detail stored in private_detail only; the aggregate names no symbol",
}
SHADOW_OVERLAY = "fieldwise"
CHANGE_TOLERANCE = 0.0005  # |after/before - 1| above 0.05 % counts as a change (float noise is far below it)
EBITDA_TOLERANCE = 0.01  # |after/before - 1| of TTM EBITDA above 1 % counts as an EBITDA change
SHARES_SCALE_SUSPECT = 100.0  # CVM shares vs EODHD shares off by >= 100x: a thousands/units mix-up, never served blindly
STATS_KEYS = ("n", "median", "p90", "abs_median", "abs_p90", "changed", "over_5_percent", "over_20_percent")
AGGREGATE_KEYS = (
    "schema", "market", "cycle_id", "basis_at", "statements_as_of", "served_overlay", "shadow_overlay", "universe",
    "overlay_origin", "pit_excluded", "names", "internal_tp", "internal_buy_in", "internal_validation", "field_sources",
    "ebitda", "shares_scale_suspect", "private_detail_sha256",
)
NAMES_KEYS = ("served", "shadow", "pairs", "only_served", "only_shadow")
ORIGIN_KEYS = ("statements", "legacy", "none")
VALIDATION_KEYS = ("served_validated", "shadow_validated", "changed")
EBITDA_KEYS = ("changed", "legacy_partial_window", "corrected")
ATTESTATION_KEYS = ("report_sha256", "snapshot_id", "snapshot_published_at", "producer_build_sha", "reader_build_sha", "receipt_sha256")


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    return str(value) if value is not None else None


def quantile(values: Sequence[float], fraction: float) -> float | None:
    """Linear interpolation between order statistics (numpy's default, ``method='linear'``); ``None`` when empty."""
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _rounded(value: float | None) -> float | None:
    return round(value, 8) if value is not None else None  # a stored ratio round-trips JSONB unchanged


def ratio_stats(ratios: Sequence[float]) -> dict[str, Any]:
    """``after/before − 1`` over the pairs: median and p90 of the signed change and of its size, and change counts."""
    sizes = [abs(value) for value in ratios]
    return {
        "n": len(ratios),
        "median": _rounded(quantile(ratios, 0.5)),
        "p90": _rounded(quantile(ratios, 0.9)),
        "abs_median": _rounded(quantile(sizes, 0.5)),
        "abs_p90": _rounded(quantile(sizes, 0.9)),
        "changed": sum(size > CHANGE_TOLERANCE for size in sizes),
        "over_5_percent": sum(size > 0.05 for size in sizes),
        "over_20_percent": sum(size > 0.20 for size in sizes),
    }


@dataclass
class ShadowCapture:
    """What the served build consumed, overlaid both ways, collected while it runs. ``add`` never raises: a failure is
    recorded (``failure``) and logged, and the served build is untouched."""

    served_overlay: str | None = None
    statements_as_of: datetime | None = None
    served: dict[str, dict[str, Any]] = field(default_factory=dict)
    shadow: dict[str, dict[str, Any]] = field(default_factory=dict)
    sources: dict[str, dict[str, str]] = field(default_factory=dict)
    origins: dict[str, str | None] = field(default_factory=dict)
    pit_excluded: set[str] = field(default_factory=set)
    shares_ratio: dict[str, float] = field(default_factory=dict)
    failure: str | None = None

    def add(
        self,
        database: Any,
        provider: Mapping[str, dict[str, Any]],
        served: Mapping[str, dict[str, Any]],
        *,
        served_overlay: str,
        market: str = "B3",
        as_of: datetime | None = None,
    ) -> None:
        if self.failure is not None:
            return
        try:
            instant = as_of or datetime.now(timezone.utc)
            overlays = official_overlays(database, list(provider), market=market, as_of=instant)
            for symbol, fundamentals in provider.items():
                chosen = overlays[symbol]
                self.shadow[symbol] = apply_official_statements(fundamentals, chosen.overlay)
                self.sources[symbol] = fieldwise_sources(fundamentals, chosen.overlay)
                self.origins[symbol] = chosen.origin
                if chosen.pit_excluded:
                    self.pit_excluded.add(symbol)
                else:
                    self.pit_excluded.discard(symbol)
                official_shares = _positive((chosen.overlay or {}).get("sharesOutstanding"))
                provider_shares = _positive(fundamentals.get("sharesOutstanding"))
                if official_shares and provider_shares:
                    self.shares_ratio[symbol] = official_shares / provider_shares
                else:
                    self.shares_ratio.pop(symbol, None)
            self.served.update(served)
            self.served_overlay = served_overlay
            self.statements_as_of = instant
        except Exception as exc:  # the shadow never breaks the served build
            self.failure = type(exc).__name__
            logger.exception("CVM field-wise overlay shadow: overlaying the build's payloads failed; the served build is unaffected")


def _legacy_partial_window(served: Mapping[str, Any]) -> bool:
    """The EBITDA-halving signature of the legacy overlay (VALUATION_CVM_STATEMENTS_V1.md): the official rows replaced
    whole, so among the four newest quarters SOME — not all — carry EBITDA, and the served TTM summed only those."""
    official = served.get("officialFundamentals")
    if not isinstance(official, dict) or official.get("overlay") == "fieldwise":
        return False
    rows = [row for row in served.get("quarterlyIncome") or [] if isinstance(row, dict)][:4]
    carried = sum(_number(row.get("ebitda")) is not None for row in rows)
    return 0 < carried < 4


def build_shadow_outputs(
    capture: ShadowCapture,
    *,
    served_rows: Sequence[Mapping[str, Any]],
    shadow_rows: Sequence[Mapping[str, Any]],
    universe_symbols: Sequence[str],
    cycle_id: str | None,
    basis_at: datetime,
    producer_build_sha: str | None,
) -> dict[str, Any]:
    """The snapshot outputs: the aggregate (no symbol), its ``report_sha256``, the producing build and the private detail."""
    served_by_symbol = {str(row.get("symbol") or "").upper(): row for row in served_rows if row.get("symbol")}
    shadow_by_symbol = {str(row.get("symbol") or "").upper(): row for row in shadow_rows if row.get("symbol")}
    served_valued = {symbol for symbol, row in served_by_symbol.items() if _positive(row.get("internal_tp"))}
    shadow_valued = {symbol for symbol, row in shadow_by_symbol.items() if _positive(row.get("internal_tp"))}
    pairs = sorted(served_valued & shadow_valued)

    def ratios(column: str) -> list[float]:
        output = []
        for symbol in pairs:
            before, after = _positive(served_by_symbol[symbol].get(column)), _positive(shadow_by_symbol[symbol].get(column))
            if before and after:
                output.append(after / before - 1)
        return output

    universe = [symbol for symbol in dict.fromkeys(str(symbol).upper() for symbol in universe_symbols) if symbol in capture.shadow]
    field_sources = {name: {source: 0 for source in SOURCES} for name in SOURCE_FIELDS}
    origin_counts = {key: 0 for key in ORIGIN_KEYS}
    ebitda_counts = {key: 0 for key in EBITDA_KEYS}
    detail: dict[str, dict[str, Any]] = {}
    for symbol in universe:
        sources = capture.sources.get(symbol) or {}
        for name in SOURCE_FIELDS:
            field_sources[name][sources.get(name, "absent")] += 1
        origin_counts[capture.origins.get(symbol) or "none"] += 1
        served_fundamentals = capture.served.get(symbol) or {}
        before_ebitda, after_ebitda = _number(served_fundamentals.get("ebitda")), _number(capture.shadow[symbol].get("ebitda"))
        changed = bool(before_ebitda and after_ebitda is not None and abs(after_ebitda / before_ebitda - 1) > EBITDA_TOLERANCE)
        partial = _legacy_partial_window(served_fundamentals)
        ebitda_counts["changed"] += changed
        ebitda_counts["legacy_partial_window"] += partial
        ebitda_counts["corrected"] += changed and partial
        served_row, shadow_row = served_by_symbol.get(symbol) or {}, shadow_by_symbol.get(symbol) or {}
        detail[symbol] = {
            "origin": capture.origins.get(symbol),
            "pit_excluded": symbol in capture.pit_excluded,
            "sources": dict(sources),
            "ebitda_before": before_ebitda,
            "ebitda_after": after_ebitda,
            "ebitda_legacy_partial_window": partial,
            "shares_ratio": capture.shares_ratio.get(symbol),
            "internal_tp_before": _positive(served_row.get("internal_tp")),
            "internal_tp_after": _positive(shadow_row.get("internal_tp")),
            "internal_buy_in_before": _positive(served_row.get("internal_buy_in")),
            "internal_buy_in_after": _positive(shadow_row.get("internal_buy_in")),
            "internal_validation_before": served_row.get("internal_tp_validation_status"),
            "internal_validation_after": shadow_row.get("internal_tp_validation_status"),
        }

    def validated(row: Mapping[str, Any] | None) -> bool:
        return bool(row) and (row or {}).get("internal_tp_validation_status") == "validated"

    aggregate = {
        "schema": RECEIPT_SCHEMA,
        "market": "B3",
        "cycle_id": cycle_id,
        "basis_at": _iso(basis_at),
        "statements_as_of": _iso(capture.statements_as_of),
        "served_overlay": capture.served_overlay,
        "shadow_overlay": SHADOW_OVERLAY,
        "universe": len(universe),
        "overlay_origin": origin_counts,
        "pit_excluded": sum(symbol in capture.pit_excluded for symbol in universe),
        "names": {
            "served": len(served_valued), "shadow": len(shadow_valued), "pairs": len(pairs),
            "only_served": len(served_valued - shadow_valued), "only_shadow": len(shadow_valued - served_valued),
        },
        "internal_tp": ratio_stats(ratios("internal_tp")),
        "internal_buy_in": ratio_stats(ratios("internal_buy_in")),
        "internal_validation": {
            "served_validated": sum(validated(served_by_symbol.get(symbol)) for symbol in served_by_symbol),
            "shadow_validated": sum(validated(shadow_by_symbol.get(symbol)) for symbol in shadow_by_symbol),
            "changed": sum(validated(served_by_symbol.get(symbol)) != validated(shadow_by_symbol.get(symbol))
                           for symbol in set(served_by_symbol) | set(shadow_by_symbol)),
        },
        "field_sources": field_sources,
        "ebitda": ebitda_counts,
        "shares_scale_suspect": sum(
            1 for symbol in universe
            if (ratio := capture.shares_ratio.get(symbol)) is not None and not 1 / SHARES_SCALE_SUSPECT < ratio < SHARES_SCALE_SUSPECT
        ),
        "private_detail_sha256": canonical_sha256(detail),
    }
    if tuple(aggregate) != AGGREGATE_KEYS:  # the workflow verifier pins these keys: a new one is reviewed there first
        raise RuntimeError("the CVM overlay shadow aggregate keys drifted from AGGREGATE_KEYS")
    return {
        "schema": SNAPSHOT_SCHEMA,
        "aggregate": aggregate,
        "report_sha256": canonical_sha256(aggregate),
        "producer_build_sha": producer_build_sha,
        "private_detail": detail,
    }


def save_shadow_snapshot(database: Any, outputs: Mapping[str, Any], *, published_at: datetime) -> str:
    methodology_id = database.ensure_methodology_version(
        METHODOLOGY_KEY, METHODOLOGY_VERSION, METHODOLOGY_PARAMETERS,
        "Shadow of the nightly B3 build under the field-wise CVM overlay: aggregate before/after, nothing served.",
    )
    aggregate = outputs.get("aggregate") or {}
    return database.save_analysis_snapshot(
        ANALYSIS_TYPE,
        ENTITY_KEY,
        methodology_id,
        {"schema": SNAPSHOT_SCHEMA, "cycle_id": aggregate.get("cycle_id"), "report_sha256": outputs.get("report_sha256")},
        dict(outputs),
        published_at,
    )


def before_after_receipt(database: Any, *, reader_build_sha: str | None) -> dict[str, Any]:
    """The latest shadow snapshot as a receipt: its aggregate (re-hashed: ``report_sha256`` must recompute), the snapshot
    identity, the producing and the reading builds, bound by ``receipt_sha256``. Never the private detail.
    ``LookupError`` without a snapshot; ``ValueError`` on a snapshot whose aggregate is not exactly the aggregate or
    does not recompute."""
    snapshot = database.latest_analysis_snapshot(ANALYSIS_TYPE, ENTITY_KEY)
    if not snapshot:
        raise LookupError("no CVM overlay shadow snapshot yet: set C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_SHADOW=true and wait for a nightly B3 cycle")
    outputs = snapshot.get("outputs") if isinstance(snapshot.get("outputs"), dict) else {}
    aggregate = outputs.get("aggregate")
    if outputs.get("schema") != SNAPSHOT_SCHEMA or not isinstance(aggregate, dict) or tuple(sorted(aggregate)) != tuple(sorted(AGGREGATE_KEYS)):
        raise ValueError("the latest CVM overlay shadow snapshot is not a VALUATION_CVM_OVERLAY_SHADOW_V1 aggregate")
    report_sha256 = canonical_sha256(aggregate)
    if report_sha256 != outputs.get("report_sha256"):
        raise ValueError("the stored aggregate does not recompute to its report_sha256: the snapshot was altered")
    receipt = {
        **aggregate,
        "report_sha256": report_sha256,
        "snapshot_id": str(snapshot.get("id")),
        "snapshot_published_at": _iso(snapshot.get("published_at")),
        "producer_build_sha": outputs.get("producer_build_sha"),
        "reader_build_sha": reader_build_sha,
    }
    return {**receipt, "receipt_sha256": canonical_sha256(receipt)}


def _pt(value: Any, *, digits: int = 2, percent: bool = True, signed: bool = True) -> str:
    number = _number(value)
    if number is None:
        return "n/d"
    if percent:
        number *= 100
    text = f"{number:+.{digits}f}" if signed else f"{number:.{digits}f}"
    return text.replace(".", ",") + (" %" if percent else "")


def before_after_markdown(receipt: Mapping[str, Any]) -> str:
    """The receipt as the owner reads it — Portuguese, rendered ONLY from the aggregate: no symbol can reach it, so it is
    safe in a public CI log. It quotes ``report_sha256`` (the content the owner accepts), ``receipt_sha256`` and the
    producing build."""
    names = receipt.get("names") or {}
    origin = receipt.get("overlay_origin") or {}
    ebitda = receipt.get("ebitda") or {}
    validation = receipt.get("internal_validation") or {}
    lines = [
        "## Valuation B3 — antes/depois do overlay campo a campo da CVM (sombra)",
        "",
        f"- Recibo `report_sha256`: `{receipt.get('report_sha256')}` (esquema `{receipt.get('schema')}`)",
        f"- Produzido pela revisão implantada `{receipt.get('producer_build_sha')}` no ciclo noturno (`receipt_sha256` "
        f"`{receipt.get('receipt_sha256')}`; lido pela revisão `{receipt.get('reader_build_sha')}`)",
        f"- Ciclo B3 `{receipt.get('cycle_id')}`, base `{receipt.get('basis_at')}`; demonstrações lidas até `{receipt.get('statements_as_of')}`",
        f"- Antes: overlay servido `{receipt.get('served_overlay')}`; depois: `{receipt.get('shadow_overlay')}` (nada servido muda)",
        f"- Universo com fundamentos: {receipt.get('universe')}; origem do overlay: demonstrações completas {origin.get('statements')}, "
        f"legado {origin.get('legacy')}, nenhum {origin.get('none')}; afastados por data de recebimento posterior ao corte: {receipt.get('pit_excluded')}",
        f"- Nomes com TP interno: antes {names.get('served')}, depois {names.get('shadow')}, nos dois {names.get('pairs')} "
        f"(só antes {names.get('only_served')}, só depois {names.get('only_shadow')})",
        f"- TP interno validado: antes {validation.get('served_validated')}, depois {validation.get('shadow_validated')}, mudam {validation.get('changed')}",
        f"- EBITDA TTM: muda (> 1 %) em {ebitda.get('changed')}; assinatura do defeito da metade no legado em {ebitda.get('legacy_partial_window')}; "
        f"corrigidos {ebitda.get('corrected')}",
        f"- Ações CVM × EODHD fora de 100× (suspeita de escala): {receipt.get('shares_scale_suspect')}",
        "",
        "| Medida (depois/antes − 1) | n | mediana | p90 | mediana do módulo | p90 do módulo | mudam (> 0,05 %) | > 5 % | > 20 % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, key in (("TP interno", "internal_tp"), ("Buy-in interno", "internal_buy_in")):
        stats = receipt.get(key) or {}
        lines.append(
            f"| {label} | {stats.get('n')} | {_pt(stats.get('median'))} | {_pt(stats.get('p90'))} | {_pt(stats.get('abs_median'), signed=False)} | "
            f"{_pt(stats.get('abs_p90'), signed=False)} | {stats.get('changed')} | {stats.get('over_5_percent')} | {stats.get('over_20_percent')} |"
        )
    lines += ["", "| Campo | CVM | EODHD | misto | ausente |", "|---|---:|---:|---:|---:|"]
    for name, counts in (receipt.get("field_sources") or {}).items():
        counts = counts if isinstance(counts, Mapping) else {}
        lines.append(f"| `{name}` | {counts.get('cvm')} | {counts.get('eodhd')} | {counts.get('mixed')} | {counts.get('absent')} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CVM field-wise overlay shadow: the read-only before/after receipt (aggregate only)")
    parser.add_argument("--before-after", action="store_true", required=True,
                        help="print the receipt of the latest shadow snapshot: aggregate, report_sha256, producer/reader builds, receipt_sha256")
    parser.parse_args(argv)
    from .config import get_settings
    from .database import Database

    database = Database(get_settings())
    try:
        receipt = before_after_receipt(database, reader_build_sha=os.environ.get("C3PO_BUILD_SHA"))
    except (LookupError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 3
    print(json.dumps(receipt, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
