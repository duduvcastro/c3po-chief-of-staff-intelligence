"""The family's conformance suite (121 tests) applied to DBR, once per signed mode: the bound fixture of mode QUERIES and
the bound fixture of mode PRIV are two different requests of the same source."""
import json

import conformance
import dbr
import family as f
import hostemu

class TestConformance(conformance.Conformance):
    DIRECTORY=dbr.DIRECTORY
    OTHERS=(dbr.DIRECTORY.parent/'db_preflight',)
    @staticmethod
    def case(now=None):return dbr.case(now)
