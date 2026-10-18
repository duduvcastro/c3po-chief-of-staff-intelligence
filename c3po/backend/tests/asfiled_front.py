"""The as-filed front (migration 051's store, the SEC concept ladder, the as-of bridge) for the tests of its consumers.

The modules belong to the as-filed front (branch fable/val-xbrl: ``app/statement_vintages.py``, ``app/sec_xbrl.py``,
``app/valuation_asfiled.py``). A module that is in the tree is used as is. Until that branch is merged,
``asfiled_front_snapshot/`` holds BYTE-IDENTICAL copies taken at fable/val-xbrl ``f973dc4`` (their sha256 is checked
before loading), installed under their ``app.*`` names for the duration of a test only — so the consumers are tested
against the real store, never a double. Nothing here is a migration: the in-memory database stands for the tables.

Delete ``asfiled_front_snapshot/`` (and the snapshot branch below) once the front is merged.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

SNAPSHOT = Path(__file__).with_name("asfiled_front_snapshot")
SNAPSHOT_COMMIT = "f973dc41c00f5abe8ded001eda8a6f5521199b15"  # fable/val-xbrl
SNAPSHOT_SHA256 = {  # in dependency order: the ladder imports the store, the bridge imports both
    "statement_vintages": "7a151f51bb83eb33d890ba595478a8ca56dbb9f8483b9a97daf10c7766e6fc81",
    "sec_xbrl": "d0b94c61be42867f1e51001b39f28fbf1b2814b83f58dd90ca84f0fc9e29205a",
    "valuation_asfiled": "6b0d2fa2f0b1e9934bc5569a07dd5920a99b1ae34aa299906d43054770ae41a4",
}


@contextmanager
def installed() -> Iterator[SimpleNamespace]:
    """The three modules, importable as ``app.<name>`` inside the block: the tree's own when present, else the snapshot
    (``origin``: ``tree``, ``snapshot`` or both), which leaves ``sys.modules`` on exit."""
    with pytest.MonkeyPatch.context() as patch:
        modules: dict[str, ModuleType] = {}
        origins: set[str] = set()
        for name, expected in SNAPSHOT_SHA256.items():
            qualified = f"app.{name}"
            if qualified in sys.modules or importlib.util.find_spec(qualified) is not None:  # a snapshot never outlives its block
                modules[name] = importlib.import_module(qualified)
                origins.add("tree")
                continue
            path = SNAPSHOT / f"{name}.py"
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == expected, f"{path.name} is not the snapshot of fable/val-xbrl {SNAPSHOT_COMMIT[:7]} ({digest})"
            spec = importlib.util.spec_from_file_location(qualified, path)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            patch.setitem(sys.modules, qualified, module)
            spec.loader.exec_module(module)
            modules[name] = module
            origins.add("snapshot")
        yield SimpleNamespace(**modules, origin="+".join(sorted(origins)))
