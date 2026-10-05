"""The family's conformance suite (121 tests) applied to K12p. OTHERS: the sealed siblings."""
from pathlib import Path

import conformance
import k12p

SIBLINGS=tuple(str(Path(k12p.DIRECTORY).parent/name) for name in ('epoch_readback','install_release','catalog_init','activate','k12_window','k12_collect')
               if (Path(k12p.DIRECTORY).parent/name/'build'/'ASSEMBLY.json').is_file())

class TestPreflight(conformance.Conformance):
    DIRECTORY=k12p.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k12p.case(now)
