"""Pure inventory/capacity plan for a proposed group on the existing stream.

No application caller activates this plan yet. Subscribing actual symbols needs
its nominal order and an independently checked live-capacity receipt. This
module does not fetch data, start a stream, mutate settings or place orders.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from .r2d2_v2_store import ShadowIntegrityError, digest

GROUP_NAME = "r2d2-v2-live"
GROUP_PRIORITY = 190  # Existing positions=200; dashboard=140; analysis=110.
MAX_SYMBOLS = 550
_INSTRUMENT = re.compile(r"US:([A-Z0-9][A-Z0-9.-]{0,19})\Z")
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.-]{0,19}\Z")


def plan_live_group(saved: dict | None, release: Any, *, capacity: int,
                    protected_symbols: Iterable[str] = ()) -> dict:
    """Union OPEN portfolio/research episodes without silently truncating.

    `capacity` must come from the audited occupancy bound, not a guessed spare
    slot count. The future caller must recheck this plan against current groups
    under the stream's lock before applying it; this is not an operational GO.
    """
    if release.mode != "CERTIFIED" or not release.epoch.startswith("R2D2-V2-SHADOW-"):
        raise ShadowIntegrityError("V2_LIVE_GROUP_REQUIRES_CERTIFIED")
    if type(capacity) is not int or not 1 <= capacity <= MAX_SYMBOLS:
        raise ShadowIntegrityError("V2_LIVE_GROUP_CAPACITY_INVALID")
    protected = set(protected_symbols)
    if not all(isinstance(s, str) and _SYMBOL.fullmatch(s) for s in protected):
        raise ShadowIntegrityError("V2_LIVE_GROUP_PROTECTED_SYMBOL_INVALID")
    symbols: set[str] = set()
    counts = {"portfolio": 0, "research": 0}
    if saved is not None:
        state = saved["state"]
        if digest(state) != saved["state_sha"]:
            raise ShadowIntegrityError("STATE_HASH_MISMATCH")
        bindings = {"epoch": release.epoch, "mode": release.mode,
            "release_sha": release.receipt_sha, "code_revision": release.code_revision,
            "implementation_package_sha": release.implementation_package_sha,
            "implementation_contract_sha": release.implementation_contract_sha}
        if any(state.get(key) != value for key, value in bindings.items()):
            raise ShadowIntegrityError("V2_LIVE_GROUP_RELEASE_MISMATCH")
        ledger = state.get("ledger")
        if not isinstance(ledger, dict):
            raise ShadowIntegrityError("V2_LIVE_GROUP_LEDGER_MISSING")
        for book in counts:
            records = ledger.get(book)
            if not isinstance(records, dict):
                raise ShadowIntegrityError("V2_LIVE_GROUP_LEDGER_MISSING")
            for record in records.values():
                if record.get("status") != "OPEN":
                    continue
                match = _INSTRUMENT.fullmatch(str(record.get("instrument_key", "")))
                if not match:
                    raise ShadowIntegrityError("V2_LIVE_GROUP_INSTRUMENT_INVALID")
                symbols.add(match[1])
                counts[book] += 1
    required = protected | symbols
    if len(required) > capacity:
        raise ShadowIntegrityError("V2_LIVE_GROUP_CAPACITY_EXCEEDED")
    return {"group": GROUP_NAME, "priority": GROUP_PRIORITY,
            "symbols": sorted(symbols), "open_episode_counts": counts,
            "unique_v2_symbols": len(symbols), "protected_unique_symbols": len(protected),
            "incremental_symbols": len(symbols - protected), "required_unique_symbols": len(required),
            "capacity": capacity, "epoch": release.epoch,
            "state_sha": saved["state_sha"] if saved else None,
            "activation_authorized": False}
