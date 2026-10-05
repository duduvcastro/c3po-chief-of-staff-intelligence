"""Assembly specification of K4 mode E0 (epoch R2D2-V2-SHADOW-2026-10-05): the epoch's private source root, the K9
tree and the content-addressed K9 runner, delivered once before the first daily phases."""
NAME='k4_e0'
MODULE='k4_e0'
STEM='HOSTOPS02_K4_E0'
PARTS=['core','parents','files']
HEADER='''"""OP_K4_E0: the private roots of epoch R2D2-V2-SHADOW-2026-10-05 and the K9 runner, delivered once.

Private directories (root:root 0700) and one file (root:root 0600), all under /var/lib, whose chain from "/" is
controlled by root alone (no open root, uid 0 and gid 0, no group or other write, no setgid, no link): /var/lib/c3po
only if it is absent (if present it is used unchanged and must be on the filesystem of /var/lib); in it the epoch's
source root and the K9 root; in the K9 root: tools, days, claims and secrets; in tools: the runner file
k9_runner-<sha256>.py holding exactly the bytes this request carries, whose SHA-256 and size the request signs.
Exclusive creation only: one mkdir per directory by a held descriptor, a temporary file with unbuffered writes and
fsync, exact metadata, a link to the final name (a link never replaces anything), fsync of the directory, removal of
the temporary once its identity is proved. The bytes and every directory are read back through descriptors inside
the run. Everything is looked at before the first creation: the executor, the boot of the evidence, the signed rows
of the parent from "/", the state of /var/lib/c3po, the absence of both roots, 200 GiB available on that filesystem
and the time left. This source starts no process, opens no socket, reads no environment and no secret, writes no
secret, never activates anything, never touches a container and never changes, renames or removes an object that
exists. It does not judge the runner bytes beyond their signed hash and size: their review is by hash, elsewhere.
The caller authenticates exact request/authority/GO/source bytes first. No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=True

def unbound_plan(module):
    return {'parent':None,'runner':{'path':None,'content_b64':None,'sha256':None,'bytes':None},'evidence_boot_id_sha256':None}
