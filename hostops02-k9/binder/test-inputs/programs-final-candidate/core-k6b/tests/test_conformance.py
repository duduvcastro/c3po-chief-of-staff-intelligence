"""The family's conformance suite applied to the two demonstration operations of the core: what every operation built
on the core inherits is proven here on two complete sources, one that reads and one that writes."""
import conformance
import demos

class TestSelftestRead(conformance.Conformance):
    DIRECTORY=demos.READ
    @staticmethod
    def case(now=None):return demos.case('selftest_read',now)

class TestSelftestWrite(conformance.Conformance):
    DIRECTORY=demos.WRITE
    @staticmethod
    def case(now=None):return demos.case('selftest_write',now)
