"""Assembly specification of the core's writing demonstration operation (never bound, never dispatched)."""
NAME='selftest_write'
MODULE='selftest_write'
STEM='HOSTOPS02_SELFTEST_WRITE'
PARTS=['core','runner','docker','parents','files','lock']
HEADER='''"""OP_SELFTEST_WRITE: the demonstration write of the HOSTOPS02 core. NEVER BOUND AND NEVER DISPATCHED.

It exists so that every piece of the frozen core runs inside one assembled source under the core's tests, and so
that an author of a real operation has a complete worked example. In one run it does, in small, what the tier 0
writes do: a private directory created in a pinned parent, files delivered into it (temporary, fsync, link, proved
removal), one attached container run that writes through a bind, and the recreate of one compose service under the
deployment lock with an explicit file list. Everything is looked at before the first creation; every effect is read
back inside the run; a run that changed anything and did not finish is PARTIAL, never a refusal. The caller
authenticates exact request/authority/GO/source bytes first. No action on import.
"""
'''

def unbound_plan(module):
    return {'parent':None,'open_root':None,'directory_name':None,'files':None,'container':None,'recreate':None,'evidence_boot_id_sha256':None}
