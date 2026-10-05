"""The family's conformance suite applied to K13r, mode LIVE on the emulated host of tests/k13r.py. Sibling operations
are added when the caller names them (HOSTOPS02_TEST_OTHER_OPERATIONS); the suite does not depend on them."""
import os
from pathlib import Path

import conformance
import k13r

class TestK13r(conformance.Conformance):
    DIRECTORY=k13r.DIRECTORY
    OTHERS=tuple(Path(item).resolve() for item in os.environ.get('HOSTOPS02_TEST_OTHER_OPERATIONS','').split(os.pathsep)
                 if item and (Path(item)/'build'/'ASSEMBLY.json').is_file())
    @staticmethod
    def case(now=None):return k13r.case(now)
