"""RAW pinned-snapshot consensus for the signed ensemble grid.

Eligibility remains the frozen valuation_pit_rerun.consensus_at contract. The
ensemble additionally averages the selected house targets; it never reconstructs
an arithmetic mean from the old reader's median and count. No reader/network is
constructed here, and capture time never replaces target publication time.
"""
from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from . import valuation_pit_rerun as pit
from .valuation_ensemble_inputs import NotEvaluable, canonical_hash, utc


def grid_consensus_at(rows: Sequence[Mapping[str, Any]] | None, *, as_of: datetime,
                      currency: str, snapshot_id: str | None, market: str = "NASDAQ") -> tuple[float | None, dict[str, Any]]:
    """Return mean and the exact latest eligible per-house selection of consensus_at.

    The caller supplies the RAW target rows and the ID pinned by the sibling V3
    run. Equal publication-clock ties retain the first row as the frozen reader
    does; row indices and hashes expose that source ordering in the receipt.
    """
    cut = utc(as_of)
    if market not in {"NASDAQ", "NYSE", "B3"}:
        raise NotEvaluable("invalid_consensus_market")
    if currency != ("BRL" if market == "B3" else "USD"):
        raise NotEvaluable("consensus_market_currency_mismatch")
    metadata: dict[str, Any] = {
        "source": "valuation_pit_rerun.consensus_at:raw_pinned_snapshot_house_mean",
        "snapshot_id": snapshot_id, "currency": currency, "as_of": cut.isoformat(),
        "window_days": pit.CONSENSUS_WINDOW_DAYS, "minimum_houses": pit.MIN_CONSENSUS_HOUSES,
        "published_date_zone": "naive_is_UTC", "horizon": pit.CONSENSUS_HORIZON,
        "analyst_count": 0, "consensus_published_at": None, "public_consensus_tp": None,
        "value": None, "members": [], "refused": {}, "status": "not_evaluable",
    }
    if market == "B3":
        return None, {**metadata, "reason": "not_covered_for_B3", "refused": {"not_covered_for_B3": 1}}
    if rows is None or not isinstance(snapshot_id, str) or not snapshot_id.strip():
        return None, {**metadata, "reason": "targets_snapshot_missing", "refused": {"targets_snapshot_missing": 1}}
    # Do not weaken any frozen-reader refusal or selection rule to make a mean.
    block, refused = pit.consensus_at(rows, as_of=cut, currency=currency)
    floor = cut - timedelta(days=pit.CONSENSUS_WINDOW_DAYS)
    latest: dict[str, tuple[datetime, float, Mapping[str, Any], int]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        house = str(row.get("analystCompany") or row.get("analystName") or row.get("newsPublisher") or "").strip()
        target = pit._positive(row.get("priceTarget"))
        try:
            published = pit._instant(row.get("publishedDate"))
        except (TypeError, ValueError):
            continue
        row_currency = row.get("currency")
        if (not house or target is None or published > cut or published <= floor
                or row_currency in (None, "") or str(row_currency).strip().upper() != currency):
            continue
        if house not in latest or published > latest[house][0]:
            latest[house] = (published, target, row, index)
    members = [{"house": house, "published_at": published.isoformat(), "target": target,
                "row_index": index, "raw_row_sha256": canonical_hash(dict(row))}
               for house, (published, target, row, index) in sorted(latest.items())]
    metadata.update({"analyst_count": len(latest), "members": members, "refused": refused})
    if block is None:
        if len(latest) >= pit.MIN_CONSENSUS_HOUSES:
            raise NotEvaluable("consensus_reader_contract_mismatch")
        return None, {**metadata, "reason": "houses_below_minimum"}
    targets = [target for _, target, _, _ in latest.values()]
    if (len(latest) != block["analyst_count"] or statistics.median(targets) != block["consensus_tp"]
            or max(published for published, _, _, _ in latest.values()).isoformat() != block["published_at"]):
        raise NotEvaluable("consensus_reader_contract_mismatch")
    value = math.fsum(target / len(targets) for target in targets)
    metadata.update({"status": "evaluated", "reason": None, "value": value,
                     "public_consensus_tp": block["consensus_tp"], "consensus_published_at": block["published_at"]})
    return value, metadata
