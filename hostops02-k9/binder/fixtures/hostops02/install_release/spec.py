"""Assembly specification of K10, install_release (tier 0, Monday 2026-10-05, single shot for the epoch)."""
NAME='install_release'
MODULE='install_release'
STEM='HOSTOPS02_INSTALL_RELEASE'
PARTS=['core','parents','files']
HEADER='''"""OP_INSTALL_RELEASE: the signed release file of epoch R2D2-V2-SHADOW-2026-10-05, delivered once.

One private directory (root:root 0700) is created in the root of the data volume and one file (root:root 0600) in
it: the release bytes this request carries, whose SHA-256 and size the request signs. Exclusive creation only:
a temporary, unbuffered writes, fsync, exact metadata, a link to the final name (a link never replaces anything),
fsync of the directory, removal of the temporary once its identity is proved. The bytes are read back through a
descriptor inside the run. Everything is looked at before the first creation: the executor, the New York day, the
boot of the evidence, the signed rows of every parent from "/", the maintenance pin, the absence of the destination,
free space and the time left. This source starts no process, opens no socket, reads no environment and no secret,
never activates anything, never recreates a container and never changes, renames or removes an object that exists.
It does not verify the release with the application: the epoch readback does, in a container, under its own GO.
The caller authenticates exact request/authority/GO/source bytes first. No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=True

def unbound_plan(module):
    return {'parent':None,'release':{'path':module.RELEASE_PATH,'content_b64':None,'sha256':None,'bytes':None},'evidence_boot_id_sha256':None}
