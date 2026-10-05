"""The family's conformance suite (authority, envelope, once-dispatch, launcher, transport) applied to K13, mode ACTIVATE
on the emulated launch host (tests/k13.py). The two demonstration operations of the frozen core are always among the
operations whose documents K13 must refuse; sibling operations are added when the caller names them
(HOSTOPS02_TEST_OTHER_OPERATIONS): they are sealed on their own and this suite does not depend on them."""
import os
from pathlib import Path

import conformance
import k13

class TestK13(conformance.Conformance):
    DIRECTORY=k13.DIRECTORY
    OTHERS=tuple(Path(item).resolve() for item in os.environ.get('HOSTOPS02_TEST_OTHER_OPERATIONS','').split(os.pathsep)
                 if item and (Path(item)/'build'/'ASSEMBLY.json').is_file())
    @staticmethod
    def case(now=None):return k13.case(now)
