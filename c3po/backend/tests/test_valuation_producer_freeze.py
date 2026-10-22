"""Additions of the decisor branch to the shared freeze of the week of 19/10/2026 (``tests/test_valuation_freeze.py``, kept
byte-identical to the B3 branch's copy so the two never conflict): the frozen list named every ``valuation_v3_*.py`` and
``valuation_official*.py``, so ``valuation_v3_ab.py`` — read by neither PIT producer — is pinned here, and any such file the
shared list does not name fails here. A failure means a change reached a frozen file: revert it."""
from __future__ import annotations

import hashlib
from pathlib import Path

from tests.test_valuation_freeze import FROZEN

BACKEND = Path(__file__).resolve().parents[1]
EXTRA_FROZEN = {
    "app/valuation_v3_ab.py": "0aaa48ee47212016f21a693e618757ec93ba1c1eb3ba03f9b75055b94fa75721",  # main 42f4280
}


def test_every_valuation_v3_and_official_module_is_frozen() -> None:
    names = {path.relative_to(BACKEND).as_posix() for pattern in ("app/valuation_official*.py", "app/valuation_v3_*.py") for path in BACKEND.glob(pattern)}
    assert names <= {*FROZEN, *EXTRA_FROZEN}, sorted(names - {*FROZEN, *EXTRA_FROZEN})
    for name, digest in EXTRA_FROZEN.items():
        assert hashlib.sha256((BACKEND / name).read_bytes()).hexdigest() == digest, f"{name} moved during the freeze: revert it"
