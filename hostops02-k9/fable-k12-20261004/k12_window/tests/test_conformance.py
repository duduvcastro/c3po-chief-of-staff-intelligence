"""The family's conformance suite (121 tests per fixture) applied to K12w in each of its four modes. OTHERS: the sealed
siblings of hostops02 beside this directory (links), as they are on disk when the suite runs; one that is not there is
not asked (the private copies of a mutation run have none)."""
from pathlib import Path

import conformance
import k12w

SIBLINGS=tuple(str(Path(k12w.DIRECTORY).parent/name) for name in ('epoch_readback','install_release','catalog_init','activate','k12_collect','k12_preflight')
               if (Path(k12w.DIRECTORY).parent/name/'build'/'ASSEMBLY.json').is_file())

class TestLaunch(conformance.Conformance):
    DIRECTORY=k12w.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k12w.case('LAUNCH',now)

class TestPersist(conformance.Conformance):
    DIRECTORY=k12w.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k12w.case('PERSIST',now)

class TestStop(conformance.Conformance):
    DIRECTORY=k12w.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k12w.case('STOP',now)

class TestRemove(conformance.Conformance):
    DIRECTORY=k12w.DIRECTORY;OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k12w.case('REMOVE',now)
