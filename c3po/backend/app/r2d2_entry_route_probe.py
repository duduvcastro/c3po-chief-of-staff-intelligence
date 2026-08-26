from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import get_settings
from .database import Database
from .r2d2_entry_quality_study import (
    CURRENT_M1_POLICY_EPOCH,
    PolicyEpoch,
    _epoch_for,
    _load_policy_epochs,
)
from .r2d2_exit_policy_engine import Episode, LedgerFill, build_episodes
from .r2d2_exit_policy_study import (
    LedgerReader,
    canonical_sha256,
    sha256_file,
    write_immutable_json,
)


REPORT_SCHEMA_VERSION = "R2D2-ENTRY-ROUTE-PROBE-v1"
LEGACY_START = date(2026, 8, 17)
LEGACY_END = date(2026, 8, 24)
PROVISIONAL_ROUTE = "full-exchange provisional technical scan"


@dataclass(frozen=True, slots=True)
class EpisodeRouteRow:
    episode_id: str
    era: str
    policy_epoch: str
    valuation_basis: str
    symbol: str
    opened_at: datetime
    closed_at: datetime | None
    buy_count: int
    buy_gross_value_usd: float
    allocated_cost_basis_usd: float
    net_realized_pnl_usd: float | None


def _era_for(episode: Episode, policy_epoch: str) -> str:
    if policy_epoch == CURRENT_M1_POLICY_EPOCH:
        return CURRENT_M1_POLICY_EPOCH
    session = episode.entry_session
    if LEGACY_START <= session <= LEGACY_END:
        return "2026-08-17_to_2026-08-24"
    return "outside_requested_windows"


def _opening_buy(episode: Episode) -> LedgerFill:
    for fill in episode.fills:
        if fill.side == "BUY":
            return fill
    raise ValueError(f"episode has no opening BUY: {episode.id}")


def _episode_row(episode: Episode, epochs: Sequence[PolicyEpoch]) -> EpisodeRouteRow:
    opening = _opening_buy(episode)
    epoch = _epoch_for(opening, epochs)
    buys = [fill for fill in episode.fills if fill.side == "BUY"]
    sells = [fill for fill in episode.fills if fill.side == "SELL"]
    net_pnl: float | None = None
    if episode.closed:
        missing = [fill.id for fill in sells if fill.realized_pnl_usd is None]
        if missing:
            raise ValueError(
                f"closed episode {episode.id} has SELL rows without realized P&L: {missing}"
            )
        net_pnl = sum(float(fill.realized_pnl_usd) for fill in sells)
    return EpisodeRouteRow(
        episode_id=episode.id,
        era=_era_for(episode, epoch),
        policy_epoch=epoch,
        valuation_basis=str(
            opening.decision_snapshot.get("valuation_basis") or "missing"
        ),
        symbol=episode.symbol,
        opened_at=episode.opened_at,
        closed_at=episode.closed_at,
        buy_count=len(buys),
        buy_gross_value_usd=sum(fill.gross_value_usd for fill in buys),
        allocated_cost_basis_usd=sum(
            fill.gross_value_usd + fill.fees_usd for fill in buys
        ),
        net_realized_pnl_usd=net_pnl,
    )


def _round_money(value: float) -> float:
    return round(value + 0.0, 2)


def build_probe_report(
    fills: Sequence[LedgerFill],
    epochs: Sequence[PolicyEpoch],
    *,
    experiment: Mapping[str, Any],
    policy_epoch_evidence: Mapping[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    episodes, construction = build_episodes(fills)
    organic = [episode for episode in episodes if not episode.strategy_excluded]
    rows = [_episode_row(episode, epochs) for episode in organic]

    grouped: dict[tuple[str, str], list[EpisodeRouteRow]] = defaultdict(list)
    for row in rows:
        grouped[(row.era, row.valuation_basis)].append(row)

    groups = []
    for (era, valuation_basis), values in sorted(grouped.items()):
        closed = [row for row in values if row.net_realized_pnl_usd is not None]
        provisional_symbols = sorted({
            row.symbol for row in values
            if row.valuation_basis == PROVISIONAL_ROUTE
        })
        groups.append({
            "era": era,
            "valuation_basis": valuation_basis,
            "policy_epochs": sorted({row.policy_epoch for row in values}),
            "episode_count": len(values),
            "closed_episode_count": len(closed),
            "open_episode_count": len(values) - len(closed),
            "buy_count": sum(row.buy_count for row in values),
            "buy_gross_value_usd": _round_money(sum(
                row.buy_gross_value_usd for row in values
            )),
            "allocated_cost_basis_usd": _round_money(sum(
                row.allocated_cost_basis_usd for row in values
            )),
            "winner_count": sum(
                row.net_realized_pnl_usd > 0 for row in closed
            ),
            "loser_count": sum(
                row.net_realized_pnl_usd < 0 for row in closed
            ),
            "flat_count": sum(
                row.net_realized_pnl_usd == 0 for row in closed
            ),
            "net_realized_pnl_usd": _round_money(sum(
                float(row.net_realized_pnl_usd) for row in closed
            )),
            "provisional_symbols": provisional_symbols,
        })

    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": generated_at,
        "governance": {
            "read_only": True,
            "descriptive_only": True,
            "confidence_intervals_computed": False,
            "funnel_change_authorized": False,
            "strategy_change_authorized": False,
        },
        "experiment": {
            "id": str(experiment["id"]),
            "code": str(experiment["code"]),
            "status": str(experiment["status"]),
        },
        "definitions": {
            "episode": "flat-to-flat; correction rows excluded by the shared episode builder",
            "route": "valuation_basis from the opening BUY decision_snapshot",
            "allocated_cost_basis_usd": "sum of BUY gross_value_usd plus BUY fees_usd",
            "net_realized_pnl_usd": "sum of persisted SELL realized_pnl_usd for closed organic episodes",
            "administrative_exclusion": "episodes containing operator_wind_down are excluded",
        },
        "policy_epoch_evidence": dict(policy_epoch_evidence),
        "ledger": {
            "row_count": len(fills),
            "canonical_json_sha256": canonical_sha256([
                {
                    "id": fill.id,
                    "executed_at": fill.executed_at,
                    "side": fill.side,
                    "market": fill.market,
                    "symbol": fill.symbol,
                    "quantity": fill.quantity,
                    "gross_value_usd": fill.gross_value_usd,
                    "fees_usd": fill.fees_usd,
                    "realized_pnl_usd": fill.realized_pnl_usd,
                    "reason": fill.reason,
                    "decision_snapshot": fill.decision_snapshot,
                }
                for fill in fills
            ]),
        },
        "construction": {
            **construction,
            "constructed_episode_count": len(episodes),
            "organic_episode_count": len(organic),
            "administrative_episode_count": len(episodes) - len(organic),
        },
        "groups": groups,
        "provisional_symbols": sorted({
            row.symbol for row in rows
            if row.valuation_basis == PROVISIONAL_ROUTE
        }),
        "episode_rows": [
            {
                "episode_id": row.episode_id,
                "era": row.era,
                "policy_epoch": row.policy_epoch,
                "valuation_basis": row.valuation_basis,
                "symbol": row.symbol,
                "opened_at": row.opened_at,
                "closed_at": row.closed_at,
                "buy_count": row.buy_count,
                "buy_gross_value_usd": _round_money(row.buy_gross_value_usd),
                "allocated_cost_basis_usd": _round_money(
                    row.allocated_cost_basis_usd
                ),
                "net_realized_pnl_usd": (
                    _round_money(row.net_realized_pnl_usd)
                    if row.net_realized_pnl_usd is not None else None
                ),
            }
            for row in rows
        ],
    }
    report["report_sha256"] = canonical_sha256(report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only descriptive H3 layer-one probe by entry valuation route",
    )
    parser.add_argument("--policy-epochs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = get_settings()
    database = Database(settings.database_url)
    experiment, fills = LedgerReader(database).read(settings.r2d2_experiment_code)
    epochs, evidence = _load_policy_epochs(args.policy_epochs)
    report = build_probe_report(
        fills,
        epochs,
        experiment=experiment,
        policy_epoch_evidence=evidence,
    )
    write_immutable_json(args.output, report)
    print(json.dumps({
        "output": str(args.output),
        "file_sha256": sha256_file(args.output),
        "report_sha256": report["report_sha256"],
        "group_count": len(report["groups"]),
        "organic_episode_count": report["construction"]["organic_episode_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
