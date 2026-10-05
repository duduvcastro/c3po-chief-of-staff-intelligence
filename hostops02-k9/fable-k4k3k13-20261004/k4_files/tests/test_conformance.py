"""The family's conformance suite (authority, envelope, once-dispatch, launcher, transport) applied to the K4 files
source, with its CHAIN_STATIC fixture (the suite needs one bound case that completes; the modes are covered in
test_k4_files.py). Sibling operations are added when the caller names them (HOSTOPS02_TEST_OTHER_OPERATIONS)."""
import os
from pathlib import Path

import conformance
import k4f

class TestK4Files(conformance.Conformance):
    DIRECTORY=k4f.DIRECTORY
    OTHERS=tuple(Path(item).resolve() for item in os.environ.get('HOSTOPS02_TEST_OTHER_OPERATIONS','').split(os.pathsep)
                 if item and (Path(item)/'build'/'ASSEMBLY.json').is_file())
    @staticmethod
    def case(now=None):return k4f.case(now)
