"""The as-filed front (migration 051's store, the SEC concept ladder, the as-of bridge) for the tests of its consumers.

The modules belong to the as-filed front (``app/statement_vintages.py``, ``app/sec_xbrl.py``, ``app/valuation_asfiled.py``),
now merged: the consumers are tested against the tree's real store, never a double. The byte-identical snapshot of
fable/val-xbrl ``f973dc4`` that stood in for them before the merge is gone. Nothing here is a migration: the in-memory
database stands for the tables.
"""
from __future__ import annotations

import importlib
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace

MODULES = ("statement_vintages", "sec_xbrl", "valuation_asfiled")  # in dependency order: the ladder imports the store, the bridge imports both


@contextmanager
def installed() -> Iterator[SimpleNamespace]:
    """The three modules of the tree, as ``app.<name>`` (``origin`` = ``tree``)."""
    yield SimpleNamespace(**{name: importlib.import_module(f"app.{name}") for name in MODULES}, origin="tree")
