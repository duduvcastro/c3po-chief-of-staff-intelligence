"""Readiness of the Valuation ensemble grid's new epoch (PREREG_VALUATION_ENSEMBLE_PIT_US_V1 rev 2 §6): read only, before
the instrument pin is signed.

Every section of the signed rev3 manifest (stdin) runs the pinned statements check of rev 2 §2 on the reader the executor
hands it (``valuation_ensemble_frozen``): ``admitted_names`` on a ``FrozenAsFiledReader`` cut at its V3 snapshot's
``published_at`` (``valuation_ensemble_executor._written_at``; one ``FrozenIndex`` for the run), then ``compare_reference``
for every covered name, on the reader's own facts (``AsFiledReader.facts`` at T, then ``written_by`` at the cut). Only the
I/O differs from a chunk: the names are taken issuer by issuer, and each issuer's facts are read from the store ONCE (its
own query, every acceptance); a section's read at T is sliced from them as the store's SQL cuts it (``accepted_at <= T``,
in its order). Nothing beyond the statements is computed: no prices, no models, no labels; nothing is written. The pin is
signed only with every section stable, and cites ``instrument_files_sha256``: the digest of the instrument files of the
deployed checkout (``valuation_ensemble_pin.instrument_file_hashes``, this module among them), which the running modules
must equal (``valuation_ensemble_driver.running_files``) before anything is read.

Counts only (the repository is public): no symbol, issuer, value or error text; sections by their market and session.

    docker compose exec -T -e PGOPTIONS='-c default_transaction_read_only=on' api \
        python -m app.valuation_ensemble_readiness --deadline-at <epoch seconds> < rev3.json
"""
from __future__ import annotations

import argparse
import bisect
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from . import valuation_ensemble_executor as exe
from . import valuation_pit_rerun as pit
from .valuation_ensemble_driver import LEGACY_ROOT, read_rev3, running_files
from .valuation_ensemble_frozen import AdmittedName, FrozenAsFiledReader, FrozenIndex, admitted_names, compare_reference, written_by
from .valuation_ensemble_inputs import canonical_hash, utc
from .valuation_ensemble_pin import instrument_file_hashes
from .valuation_grid_preflight import _CODE, DEADLINE_FLOOR_SECONDS, _end_at_the_deadline, arm_deadline, inside_a_window


class OneIssuerStore:
    """The store's ``vintages`` for the issuer being checked: read once with every acceptance; a call at T returns what
    the store's SQL returns (``accepted_at <= T``, ordered by acceptance, document and concept)."""

    def __init__(self, store: Any) -> None:
        self.store = store
        self.key: tuple[str, str, str | None] | None = None
        self.rows: list[dict[str, Any]] = []
        self.accepted: list[datetime] = []
        self.reads = 0

    def vintages(self, market: str, issuer_key: str, *, accepted_at_or_before: datetime | None = None,
                 concepts: Iterable[str] | None = None, source: str | None = None) -> list[dict[str, Any]]:
        if concepts is not None:
            raise ValueError("readiness_store_call_unexpected")
        if (market, issuer_key, source) != self.key:
            self.rows = self.store.vintages(market, issuer_key, source=source)
            self.accepted = [utc(row["accepted_at"]) for row in self.rows]
            if self.accepted != sorted(self.accepted):
                raise ValueError("readiness_store_order_unexpected")
            self.key, self.reads = (market, issuer_key, source), self.reads + 1
        end = len(self.rows) if accepted_at_or_before is None else bisect.bisect_right(self.accepted, utc(accepted_at_or_before))
        return [dict(row) for row in self.rows[:end]]


class SlicedReader(pit.AsFiledReader):
    """``AsFiledReader`` with its store query served by ``OneIssuerStore``: its own ``facts`` (the cut at T, its checks)."""

    def present(self) -> bool:
        present = super().present()
        if present and not isinstance(self._store, OneIssuerStore):
            self._store = OneIssuerStore(self._store)
        return present


def _label(entry: Mapping[str, Any]) -> str:
    return "%s %s" % (entry.get("market"), entry.get("session_date"))


def _code(error: BaseException) -> str:
    return str(error) if isinstance(error, ValueError) and _CODE.fullmatch(str(error)) else type(error).__name__


def run(database: Any, rev3: Mapping[str, Any], *, legacy_root: Path = LEGACY_ROOT, app_dir: Path | None = None) -> dict[str, Any]:
    files = instrument_file_hashes(legacy_root)  # the deployed checkout's instrument, the bytes the pin will list
    running_files(files, app_dir or Path(__file__).resolve().parent)  # and the modules this process runs are those bytes
    pairs = exe._reference_pairs(rev3)  # the complete, signed rev3 manifest (its digest) or a refusal; the grid's order
    index = FrozenIndex.load(database)
    sections: list[dict[str, Any]] = []
    for v3_entry, served_entry in pairs:
        section: dict[str, Any] = {"label": _label(v3_entry), "market": str(v3_entry["market"]), "as_of": exe._instant(v3_entry["as_of"]),
                                   "refused": None, "names": [], "compared": 0, "not_evaluable": 0, "written": None}
        sections.append(section)
        try:
            v3_snapshot, served_snapshot = exe._snapshot(database, v3_entry), exe._snapshot(database, served_entry)
            section["written"] = exe._written_at(v3_snapshot)
            reader = FrozenAsFiledReader(database, written_until=section["written"], index=index)
            section["names"] = admitted_names(database, market=section["market"], as_of=section["as_of"], v3_snapshot=v3_snapshot,
                                              served_snapshot=served_snapshot, reader=reader)
        except ValueError as error:  # GridInputError too: the section a chunk would refuse
            section["refused"] = _code(error)
    uses: dict[str, list[tuple[dict[str, Any], AdmittedName]]] = {}
    for section in sections:
        for name in section["names"]:
            if name.issuer is None:
                section["not_evaluable"] += 1
            else:
                uses.setdefault(name.issuer, []).append((section, name))
    facts = SlicedReader(database)
    if not facts.present():
        raise ValueError("readiness_statement_vintages_unavailable")
    for issuer, issuer_uses in sorted(uses.items()):
        for section, name in issuer_uses:
            if section["refused"] is not None:
                continue
            try:
                raw = written_by(facts.facts(issuer, as_of=section["as_of"], refused=Counter()), section["written"], Counter())
                compare_reference(raw, name=name, market=section["market"], front=facts.front)
                section["compared"] += 1
            except ValueError as error:
                section["refused"] = _code(error)
    refused = [section for section in sections if section["refused"] is not None]
    written = [section["written"] for section in sections if section["written"] is not None]
    return {"sections": len(sections), "stable_sections": len(sections) - len(refused), "refused_sections": len(refused),
            "refused": [section["label"] for section in refused], "first_refused": refused[0]["label"] if refused else None,
            "refusal_reasons": dict(sorted(Counter(section["refused"] for section in refused).items())),
            "names": sum(len(section["names"]) for section in sections),
            "names_compared": sum(section["compared"] for section in sections),
            "names_not_evaluable": sum(section["not_evaluable"] for section in sections),
            "issuers_read": facts._store.reads if isinstance(facts._store, OneIssuerStore) else 0,
            "instrument_files": len(files), "instrument_files_sha256": canonical_hash(files),
            "first_rev3_write": min(written).isoformat() if written else None,
            "last_rev3_write": max(written).isoformat() if written else None}


def main(argv: list[str] | None = None, *, database: Any = None, clock: Callable[[], float] = time.time,
         on_expiry: Callable[[], None] = _end_at_the_deadline) -> int:
    parser = argparse.ArgumentParser(description="Read-only readiness of the ensemble grid's new epoch (rev3 manifest on stdin): "
                                                 "the pinned statements check of every section; counts only, never a symbol.")
    parser.add_argument("--deadline-at", type=int, required=True,
                        help="the run's absolute deadline (epoch seconds): checked with the windows when this process starts, "
                             "and the process ends there")
    args = parser.parse_args(argv)
    now = clock()  # inside the container, after every hand-over: the windows on this process's own start, its own end
    if inside_a_window(datetime.fromtimestamp(now, timezone.utc)):
        print(json.dumps({"kind": "refused", "reason": "inside_a_window"}, sort_keys=True))
        return 27
    left = args.deadline_at - now
    if left < DEADLINE_FLOOR_SECONDS:
        print(json.dumps({"kind": "refused", "reason": "deadline_too_close"}, sort_keys=True))
        return 25
    arm_deadline(left, on_expiry)
    from .valuation_accuracy_report import force_read_only_session

    force_read_only_session()
    if database is None:
        from .config import get_settings
        from .database import Database
        database = Database(get_settings())
    try:
        result = run(database, read_rev3(sys.stdin.buffer))
    except Exception as error:  # noqa: BLE001 - a code or the type alone: a message could carry a name
        print(json.dumps({"kind": "refused", "reason": _code(error)}, sort_keys=True))
        return 2
    print(json.dumps({"kind": "readiness", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
