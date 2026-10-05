"""The family's conformance suite (121 tests of the frozen core) applied to K6b, in mode MOUNT (the fixture of the
suite) and, through a second class, in mode DISABLE_FAST (a worker that need not run, no tree read): authentication,
windows, the date class, the envelope, the once dispatcher, the launcher and the transport, and every host call
failing once in four ways."""
import conformance
import k6b

class TestCapacitySwitchMount(conformance.Conformance):
    DIRECTORY=k6b.DIRECTORY
    @staticmethod
    def case(now=None):return k6b.case(now,mode='MOUNT')

class TestCapacitySwitchFastDisable(conformance.Conformance):
    DIRECTORY=k6b.DIRECTORY
    @staticmethod
    def case(now=None):return k6b.case(now,mode='DISABLE_FAST')
