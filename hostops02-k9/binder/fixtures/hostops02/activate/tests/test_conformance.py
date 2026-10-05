"""The family's conformance suite (121 tests of the frozen core) applied to K6a: authentication, windows, the date
class, the envelope, the once dispatcher, the launcher and the transport, and every host call failing once in four ways."""
import conformance
import k6a

class TestActivate(conformance.Conformance):
    DIRECTORY=k6a.DIRECTORY
    @staticmethod
    def case(now=None):return k6a.case(now)
