"""Assembly specification of K4 modes CHAIN_STATIC, PINS and LAUNCHER (epoch R2D2-V2-SHADOW-2026-10-05): the private,
non-secret file deliveries of plan rows B5, B6 and A8, one source with one signed mode per request."""
NAME='k4_files'
MODULE='k4_files'
STEM='HOSTOPS02_K4_FILES'
PARTS=['core','parents','files']
HEADER='''"""OP_K4_FILES: private, non-secret file deliveries of epoch R2D2-V2-SHADOW-2026-10-05, one signed mode per request.

CHAIN_STATIC (plan row B5): the seven chain documents (Act A's three signatures, Act B, its three approvals), whose bytes
are compiled into this source, into the documents root of the capacity tree, and the reader's static capacity config
week.static.capacity.json, whose bytes the request carries, into its config root. PINS (B6): /etc/c3po-reader/pins.env,
twelve lines rendered by this source from the twelve signed values, after the static config, the launcher and the two
installed units it names were read on the host and found to be the signed bytes. LAUNCHER (A8): the directory
/etc/c3po-reader/launcher and in it reader_launcher.py, the bytes the request carries.
Every file root:root 0600, every directory root:root 0700, created exclusively (temporary, fsync, link, removal of the
temporary proved by identity) relative to a held descriptor of a parent walked from "/" against signed rows, then
read back through descriptors inside the run. Everything is looked at before the first creation. This source starts
no process, opens no socket, reads no environment and no secret, never activates anything, never touches a container
and never changes, renames or removes an object that exists. The caller authenticates exact request/authority/GO/
source bytes first. No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=True

def unbound_plan(module):
    return {'mode':None,'delivery':None,'evidence_boot_id_sha256':None}
