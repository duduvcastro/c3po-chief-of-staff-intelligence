"""pytest wiring of K3's tests: this directory and the tests of the frozen core on sys.path, nothing else.
The core is the sibling directory `core_k3` of this operation directory (CORE.md, section 7: a byte copy of the secrets
family's revision, generation 232f4180...); a private copy of the operation directory made by the mutation harness lies
deeper, so the first `core_k3` with a seal above this file is taken. HOSTOPS02_TEST_CORE names it explicitly."""
import os
import sys

HERE=os.path.dirname(os.path.abspath(__file__))
def core_directory():
    candidates=[os.environ['HOSTOPS02_TEST_CORE']] if os.environ.get('HOSTOPS02_TEST_CORE') else []
    directory=HERE
    for _ in range(8):
        directory=os.path.dirname(directory);candidates.append(os.path.join(directory,'core_k3'))
    for candidate in candidates:
        if os.path.isfile(os.path.join(candidate,'CORE_SHA256SUMS')) and os.path.isfile(os.path.join(candidate,'tests','family.py')):return candidate
    raise RuntimeError('the frozen core (core_k3/CORE_SHA256SUMS) was not found above '+HERE)
sys.path.insert(0,os.path.join(core_directory(),'tests'))
sys.path.insert(0,HERE)
