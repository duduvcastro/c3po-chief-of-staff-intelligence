"""The §7.3 panel as the point-in-time re-executor's records need it (``v3_2_shadow``): the two PIT reading rules, OUTSIDE
the pinned panel module.

``valuation_panel.py`` is pinned byte for byte by ``PREREG_VALUATION_DECISOR_V1`` §17 (``file app/valuation_panel.py``):
any change to its bytes voids every accuracy reading (§10) and is a new PREREG revision with a new ``H0``. The two rules
the PIT re-executor (``valuation_pit_rerun``, design rev 2 §3 and P2-2) needs from the panel therefore live here, and
``PitPanelService`` applies them around the panel's own, unchanged ``PanelService.measure``:

* **an unattested horizon** — a consensus block whose ``horizon`` is a literal that attests nothing
  (``UNATTESTED_HORIZONS = ("N/D",)``, the re-executor's block: the provider exposes no horizon per target) is read as a
  missing horizon, ``consensus_unattested:horizon`` exactly as ``None``/``""`` (PROMO-2 c): never compared, out of the
  common mask; the official emitter's ``12m`` stays ``present``. The private detail keeps the literal the record
  persisted;
* **a superseded run** — ``v3_2_shadow`` only: a record whose ``provenance.run_key`` lies in the ``inputs.supersedes``
  chain of the LATEST ``valuation_pit_rerun`` run of its ``(market, prediction_instant)`` is refused as
  ``superseded_run`` BEFORE the panel's one-per-session dedup, so neither the earliest published (superseded) cycle nor
  a crashed partial cycle whose inputs changed ever shadows the current run. ``records.read`` counts it,
  ``records.refused.superseded_run`` names it.

Everything else — admissibility, cohorts, labels, metrics, decision, the no-network reader — is the panel's, read
through the module itself. The receipt is the panel's with the two rules in ``payload.pit_rules`` and its own schema
(``PIT_SCHEMA_VERSION``), re-hashed: a PIT reading is never mistaken for a reading of the pinned panel. Read-only, no
network, nothing written to the store. CLI: ``python -m app.valuation_pit_panel --as-of … [--sources v3_2_shadow]``.
"""
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, cast

from . import valuation_panel as panel
from .config import get_settings
from .database import Database
from .valuation_official import SOURCE_V3_2_SHADOW, canonical_sha256
from .valuation_price_history import PriceHistoryService

PIT_SCHEMA_VERSION = f"{panel.SCHEMA_VERSION}+PIT-v1"
DEFAULT_SOURCES: tuple[str, ...] = (SOURCE_V3_2_SHADOW,)
UNATTESTED_HORIZONS: tuple[str, ...] = ("N/D",)  # a horizon literal that attests nothing (the PIT re-executor's consensus, design §3): ``consensus_unattested:horizon``, as None/""
SUPERSEDED_RUN = "superseded_run"  # v3_2_shadow only: the record's provenance.run_key was superseded by a later run of the same (market, T) — never served
PIT_RERUN_ANALYSIS_TYPE = "valuation_pit_rerun"  # the re-executor's one-snapshot-per-run (inputs: run_key, market, as_of, supersedes?)


def pit_rules() -> dict[str, Any]:
    """The two rules, as the receipt carries them (inside the hashed payload)."""
    return {
        "schema": PIT_SCHEMA_VERSION,
        "unattested_horizons": list(UNATTESTED_HORIZONS),
        "unattested_horizon_rule": "a consensus horizon in unattested_horizons is read as missing: consensus_unattested:horizon, never compared",
        "superseded_run_rule": (f"{SOURCE_V3_2_SHADOW} only: a record whose provenance.run_key lies in the inputs.supersedes chain of the latest "
                                f"{PIT_RERUN_ANALYSIS_TYPE} run of its (market, prediction_instant) is {SUPERSEDED_RUN}, refused before the one-per-session dedup"),
        "panel_module": "valuation_panel (unchanged; PREREG_VALUATION_DECISOR_V1 §17)",
    }


def superseded_run_keys(database: Database, *, market: str, as_of: str) -> set[str]:
    """The ``run_key`` chain the LATEST ``valuation_pit_rerun`` run of ``(market, T)`` supersedes, transitively
    (``inputs.supersedes`` of the latest run, then of the run it names, …): every run of that T but the current one —
    a rerun after changed inputs, or a partial cycle whose inputs changed before it was completed. Read-only, through
    the existing snapshot API (``latest_analysis_snapshot_by_inputs``); a cycle in the chain stops it."""
    chain: set[str] = set()
    snapshot = database.latest_analysis_snapshot_by_inputs(PIT_RERUN_ANALYSIS_TYPE, {"market": market, "as_of": as_of})
    while snapshot is not None:
        superseded = str(panel._mapping(snapshot.get("inputs")).get("supersedes") or "")
        if not superseded or superseded in chain:
            break
        chain.add(superseded)
        snapshot = database.latest_analysis_snapshot_by_inputs(PIT_RERUN_ANALYSIS_TYPE, {"run_key": superseded})
    return chain


def refuse_superseded_runs(records: Iterable[Mapping[str, Any]], *, database: Database, market: str) -> tuple[list[dict[str, Any]], int]:
    """``v3_2_shadow`` only (P2-2): a record whose ``provenance.run_key`` lies in the supersedes chain of its
    ``(market, prediction_instant)`` is ``superseded_run`` — refused BEFORE the one-per-session dedup, so the earliest
    published (superseded) cycle never shadows the current one. Returns the surviving records and the count refused."""
    chains: dict[str, set[str]] = {}
    kept: list[dict[str, Any]] = []
    refused = 0
    for record in records:
        instant = panel._parse_instant(record.get("prediction_instant"))
        run_key = str(panel._mapping(panel._mapping(record.get("decomposition")).get("provenance")).get("run_key") or "")
        if instant is not None and run_key:
            as_of = instant.isoformat()
            if as_of not in chains:
                chains[as_of] = superseded_run_keys(database, market=market, as_of=as_of)
            if run_key in chains[as_of]:
                refused += 1
                continue
        kept.append(dict(record))
    return kept, refused


def _unattested_horizon(record: Mapping[str, Any]) -> str | None:
    """The literal the record's consensus block persisted as its horizon when it attests nothing, else ``None``."""
    horizon = panel._mapping(panel._mapping(record.get("decomposition")).get("consensus")).get("horizon")
    return horizon if isinstance(horizon, str) and horizon in UNATTESTED_HORIZONS else None


def _as_missing_horizon(record: Mapping[str, Any]) -> dict[str, Any]:
    """A copy of the record whose consensus horizon is missing (``None``) — what the panel reads as
    ``consensus_unattested:horizon``. The record itself is never touched (its ``row_sha256`` is read as stored)."""
    copied = copy.deepcopy(dict(record))
    decomposition = panel._mapping(copied.get("decomposition"))
    copied["decomposition"] = {**decomposition, "consensus": {**panel._mapping(decomposition.get("consensus")), "horizon": None}}
    return copied


def consensus_of(record: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    """The panel's ``_consensus_of`` under the unattested-horizon rule: a horizon in ``UNATTESTED_HORIZONS`` is
    ``consensus_unattested:<first missing field>`` exactly as a missing one; the block reported keeps the literal."""
    literal = _unattested_horizon(record)
    if literal is None:
        return panel._consensus_of(record)
    consensus, status = panel._consensus_of(_as_missing_horizon(record))
    return {**consensus, "horizon": literal}, status


def _identity(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return str(row.get("cycle_id")), str(row.get("symbol")), str(row.get("row_sha256"))


class _PitRecords:
    """The store as ONE ``measure`` call of the PIT panel reads it: ``list_valuation_predictions_in_window`` returns the
    records the two rules leave (superseded runs refused for ``v3_2_shadow``; an unattested horizon read as missing),
    and keeps what the cell must report (the superseded count, the literals to restore in the detail). Everything else
    is delegated untouched. One instance per call: two concurrent runs share nothing."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self.superseded = 0
        self.literals: dict[tuple[str, str, str], str] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._database, name)

    def list_valuation_predictions_in_window(self, market: str, *, source: str, since: datetime | None = None, until: datetime | None = None) -> list[dict[str, Any]]:
        records = self._database.list_valuation_predictions_in_window(market, source=source, since=since, until=until)
        if source == SOURCE_V3_2_SHADOW:  # P2-2: a superseded PIT run is refused before the one-per-session dedup
            records, self.superseded = refuse_superseded_runs(records, database=self._database, market=market)
        read: list[dict[str, Any]] = []
        for record in records:
            literal = _unattested_horizon(record)
            if literal is None:
                read.append(record)
                continue
            self.literals[_identity(record)] = literal
            read.append(_as_missing_horizon(record))
        return read


class PitPanelService(panel.PanelService):
    """``valuation_panel.PanelService`` with the two PIT rules: the panel's own ``measure`` runs on a per-call view of
    the store (``_PitRecords``); the cell then counts the superseded records it never saw and the detail gets back the
    horizon literal each record persisted. Never writes, never fetches."""

    def measure(self, market: str, source: str, *, cut: datetime, since: datetime | None, until: datetime | None,
                profile_label: str | None, reader: PriceHistoryService | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        reader = reader if reader is not None else self._reader()  # the run's reader (and its introspection) stays on this instance
        view = _PitRecords(self.database)
        call = copy.copy(self)  # the panel's measure, unchanged, over the view: nothing shared with another call
        call.database = cast(Database, view)
        aggregate, observations = panel.PanelService.measure(call, market, source, cut=cut, since=since, until=until,
                                                             profile_label=profile_label, reader=reader)
        if view.superseded:
            records = aggregate["records"]
            records["read"] += view.superseded  # read from the store, refused before admissibility
            records["refused"] = panel._counts(Counter({**records["refused"], SUPERSEDED_RUN: view.superseded}))
        for row in observations:
            literal = view.literals.get(_identity(row))
            if literal is not None and row["consensus"].get("horizon") is None:
                row["consensus"]["horizon"] = literal  # the private detail reports what the record persisted
        return aggregate, observations

    def run(self, *, cut: datetime, markets: Iterable[str] = panel.MARKETS, sources: Iterable[str] = DEFAULT_SOURCES, since: datetime | None = None,
            until: datetime | None = None, profile_label: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """The panel's ``run`` with this service's ``measure``; the receipt carries ``pit_rules`` and the PIT schema."""
        result, detail = super().run(cut=cut, markets=markets, sources=sources, since=since, until=until, profile_label=profile_label)
        payload = {**result["payload"], "schema": PIT_SCHEMA_VERSION, "pit_rules": pit_rules()}
        return {"schema": PIT_SCHEMA_VERSION, "payload": payload, "payload_sha256": canonical_sha256(payload)}, detail


# ------------------------------------------------------------------ CLI
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valuation V3.2 §7.3 panel with the point-in-time rules (unattested horizon, superseded runs) for the "
                                                 "re-executor's records — measurement only (no gate, nothing served changes, no network). Prints the receipt (no symbols).")
    parser.add_argument("--as-of", required=True, help="the cut C (ISO-8601 WITH zone; naive refused): records with published_at < C, bars available before C")
    parser.add_argument("--markets", default=",".join(panel.MARKETS), help="comma-separated subset of B3,NASDAQ,NYSE (default: all three)")
    parser.add_argument("--sources", default=",".join(DEFAULT_SOURCES), help="comma-separated prediction sources (default: v3_2_shadow)")
    parser.add_argument("--since", default=None, help="lower bound (inclusive) of prediction_instant, ISO-8601 with zone")
    parser.add_argument("--until", default=None, help="upper bound (exclusive) of prediction_instant, ISO-8601 with zone")
    parser.add_argument("--profile-label", default=None, help="label the level/dispersion profile with this instead of the record's source_version")
    parser.add_argument("--detail", type=Path, default=None, help="write the PRIVATE per-symbol detail to this NEW path (O_EXCL|O_NOFOLLOW, 0600)")
    args = parser.parse_args(argv)
    cut = panel._cli_instant(parser, "--as-of", args.as_of)
    since, until = panel._cli_instant(parser, "--since", args.since), panel._cli_instant(parser, "--until", args.until)
    assert cut is not None
    markets = [market.strip().upper() for market in args.markets.split(",") if market.strip()]
    if not markets or any(market not in panel.MARKETS for market in markets):
        parser.error(f"--markets must be a non-empty subset of {','.join(panel.MARKETS)}, got {args.markets!r}")
    sources = [source.strip() for source in args.sources.split(",") if source.strip()]
    if not sources:
        parser.error("--sources must name at least one prediction source")
    if args.detail is not None and (args.detail.is_symlink() or args.detail.exists()):
        parser.error(f"--detail {args.detail} exists (or is a symlink): the private detail is written to a NEW path only, nothing written")
    if since is not None and until is not None and since >= until:
        parser.error("--since must precede --until")
    database = Database(get_settings())
    service = PitPanelService(database, settings=get_settings())
    result, detail = service.run(cut=cut, markets=markets, sources=sources, since=since, until=until, profile_label=args.profile_label)
    if args.detail is not None:
        panel.write_private_detail(args.detail, {"schema": f"{PIT_SCHEMA_VERSION}:detail", "cut": result["payload"]["cut"], "payload_sha256": result["payload_sha256"],
                                                 "rows": detail})
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
