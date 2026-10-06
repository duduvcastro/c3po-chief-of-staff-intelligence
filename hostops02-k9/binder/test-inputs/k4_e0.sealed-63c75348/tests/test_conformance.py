"""The family's conformance suite (authority, envelope, once-dispatch, launcher, transport) applied to K4-E0.

The two demonstration operations of the frozen core are always among the operations whose documents K4-E0 must refuse.
Sibling operations are added when the caller names them (HOSTOPS02_TEST_OTHER_OPERATIONS): they are other directories,
sealed on their own, and this suite does not depend on their presence."""
import os
from pathlib import Path

import conformance
import k4e0

class TestK4E0(conformance.Conformance):
    DIRECTORY=k4e0.DIRECTORY
    OTHERS=tuple(Path(item).resolve() for item in os.environ.get('HOSTOPS02_TEST_OTHER_OPERATIONS','').split(os.pathsep)
                 if item and (Path(item)/'build'/'ASSEMBLY.json').is_file())
    @staticmethod
    def case(now=None):return k4e0.case(now)
