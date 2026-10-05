"""Assembly specification of the core's reading demonstration operation (never bound, never dispatched)."""
NAME='selftest_read'
MODULE='selftest_read'
STEM='HOSTOPS02_SELFTEST_READ'
PARTS=['core','runner','docker','parents','lock']
HEADER='''"""OP_SELFTEST_READ: the demonstration read of the HOSTOPS02 core. NEVER BOUND AND NEVER DISPATCHED.

Observations only. This source has no call that creates, changes or removes anything on the host's filesystem; it
does not carry the files part. It runs, in small, what the tier 0 readback does: pinned directories walked from "/",
image and container metadata in the proven templates, the signed environment names of one container as booleans,
one attached container run with read-only binds and a pinned snippet on standard input, a compose render with the
override on standard input, a regular file compared with a signed hash, and a probe of the deployment lock. Each item
is observed on its own: a failed observation is UNAVAILABLE with a constant code, never an absence, and a mismatch
is a finding that leaves every other item in the receipt. The caller authenticates exact request/authority/GO/source
bytes first. No action on import.
"""
'''

def unbound_plan(module):
    return {'directories':None,'image':None,'containers':None,'environment':None,'verify':None,'render':None,'file':None,'lock':None,
            'evidence_boot_id_sha256':None}
