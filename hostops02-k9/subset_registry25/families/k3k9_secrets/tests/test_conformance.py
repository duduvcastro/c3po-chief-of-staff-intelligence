"""The family's conformance suite (121 tests) applied to K3-K9, unchanged. The bound fixture is dated 2026-10-05 20:45 UTC
(Monday 17:45 BRT); the suite asks the other days of the class WRITE_SESSIONS itself. The operations of the tier that lie
beside the cores this one was derived from (hostops02-sealed: catalog_init, install_release, epoch_readback, activate;
hostops02-sealed-tok: token_from_env) are added to the operations whose documents this one must refuse, when present."""
import conformance
import family as f
import k3

WORK=f.CORE.parent.parent
SIBLINGS=tuple(str(path) for path in [WORK/'hostops02-sealed'/name for name in ('catalog_init','install_release','epoch_readback','activate')]
               +[WORK/'hostops02-sealed-tok'/'token_from_env'] if (path/'build'/'ASSEMBLY.json').is_file())

class TestConformance(conformance.Conformance):
    DIRECTORY=k3.DIRECTORY
    OTHERS=SIBLINGS
    @staticmethod
    def case(now=None):return k3.case(now)
