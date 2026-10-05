"""The family's conformance suite (121 tests per fixture) applied to K12r in both modes. OTHERS: the sealed siblings."""
from pathlib import Path

import conformance
import k12r

SIBLINGS=tuple(str(Path(k12r.DIRECTORY).parent/name) for name in ('epoch_readback','install_release','catalog_init','activate','k12_window','k12_preflight')
               if (Path(k12r.DIRECTORY).parent/name/'build'/'ASSEMBLY.json').is_file())

class TestCollect(conformance.Conformance):
    DIRECTORY=k12r.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k12r.case('COLLECT',now)

class TestTree(conformance.Conformance):
    DIRECTORY=k12r.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k12r.case('TREE',now)
