"""SYNTHETIC FIXTURE verifier (tests only; FIXTURE mode is refused on the host). Accepts by returning None."""


def accept(*args):
    return None


def refuse(*args):
    raise ValueError("FIXTURE_VERIFIER_REFUSED")
