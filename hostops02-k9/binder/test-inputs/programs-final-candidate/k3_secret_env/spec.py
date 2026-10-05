"""Assembly specification of K3 (row A7 of the epoch plan): the secret.env of the V2 shadow reader, placed once in
/etc/c3po-reader for epoch R2D2-V2-SHADOW-2026-10-05, exactly to HOC section 8 (hostops01/candidate/CONTRACT.txt)."""
NAME='k3_secret_env'
MODULE='k3_secret_env'
STEM='HOSTOPS02_K3_SECRET_ENV'
PARTS=['core','runner','docker','parents','files']
HEADER='''"""OP_K3_SECRET_ENV: the one secret of the V2 shadow reader, /etc/c3po-reader/secret.env (root:root 0600, one
link), placed once: exactly one line C3PO_DATABASE_URL=<value> and its newline, the value copied in memory from the
environment of the running container c3po-r2d2-worker-1 (compose project c3po, service r2d2-worker), whose ID the
request signs.

First of all, before anything of the host is looked at, it makes its own process non-dumpable (prctl PR_SET_DUMPABLE
0, read back 0 with PR_GET_DUMPABLE, through the core's dumps_disabled): no core dump of it, to a file or through a
pipe to a crash collector, can carry the value out. If that cannot be done and proved, it refuses with nothing changed.

The directory /etc/c3po-reader is reached by a descriptor walk from "/" against signed rows (every component root-owned
and not writable by group or other, the directory itself root:root 0700, not setgid) and held. secret.env must be
absent, and no name holding "secret.env" and no temporary of the core's file writer may be in the directory. The
worker must be the one running container of that name, with the signed ID and the two compose labels; one fixed docker
container inspect template, signed in the scope, prints the one entry C3PO_DATABASE_URL as a JSON string (never the
whole environment), read twice and compared (only that entry). The value must be 1 to 4096 bytes of printable ASCII
without a space, a quote or a backslash. Everything is looked at before the creation.

Then one exclusive create of the final name (O_CREAT|O_EXCL|O_NOFOLLOW, 0600 under umask 0077) relative to the held
directory, written from a bytearray that is zeroed afterwards, fsynced, its metadata proved through the descriptor, the
directory fsynced, and the name opened again and proved: the same inode, regular, uid 0, gid 0, mode 0600, one link,
and its bytes compared in memory with the line (booleans only). No size, digest or length of the value, the line or
the file is computed for a receipt or reaches one. If a step after the creation fails, the file this run created is
removed again, and only while its name still shows the inode this run holds (an exception to rule 4 of the core,
declared in the signed scope). It never overwrites, renames, chmods, chowns or truncates anything, never reads a file
of the deploy tree, never runs anything but docker ps and docker container inspect, and never activates anything. The
receipt carries listed codes, booleans and identity rows only. The caller authenticates exact request/authority/GO/
source bytes first.
No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=True

def unbound_plan(module):
    return {'config_chain':None,'worker_container_id':None,'evidence_boot_id_sha256':None}
