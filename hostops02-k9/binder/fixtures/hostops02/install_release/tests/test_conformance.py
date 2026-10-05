"""The family's conformance suite (authority, envelope, once-dispatch, launcher, transport) applied to K10.

The two demonstration operations of the frozen core are always among the operations whose documents K10 must refuse.
The sibling operations of this family are added when the caller names them (HOSTOPS02_TEST_OTHER_OPERATIONS, the same
variable tests/test_purity.py reads): they are other directories, sealed on their own, and this suite does not depend
on their presence."""
import os
from pathlib import Path

import conformance
import k10

class TestInstallRelease(conformance.Conformance):
    DIRECTORY=k10.DIRECTORY
    OTHERS=tuple(Path(item).resolve() for item in os.environ.get('HOSTOPS02_TEST_OTHER_OPERATIONS','').split(os.pathsep)
                 if item and (Path(item)/'build'/'ASSEMBLY.json').is_file())
    @staticmethod
    def case(now=None):return k10.case(now)
