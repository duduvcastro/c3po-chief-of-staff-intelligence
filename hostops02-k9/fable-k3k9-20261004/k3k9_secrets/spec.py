"""Assembly specification of K3-K9 (decision N-5 of the K9 interface note, revision 2): the two environment files and the
emitter password of the delegated daily phases of epoch R2D2-V2-SHADOW-2026-10-05, placed once under the K9 root."""
NAME='k3k9_secrets'
MODULE='k3k9_secrets'
STEM='HOSTOPS02_K3K9_SECRETS'
PARTS=['core','runner','docker','parents','files']
HEADER='''"""OP_K3K9_SECRETS: the secrets of the K9 daily phases, placed once under <K9 root>/secrets (root:root 0700, created
empty by K4 mode E0): provider.env (C3PO_EODHD_API_TOKEN, C3PO_FINNHUB_API_TOKEN, C3PO_FMP_API_TOKEN), risk-db.env
(C3PO_R2D2_RISK_DATABASE_URL) and emitter/password, every file root:root 0600, the directory emitter root:root 0700.

First of all, before anything of the host is looked at, it makes its own process non-dumpable (prctl PR_SET_DUMPABLE
0, read back 0 with PR_GET_DUMPABLE, through the core's dumps_disabled): no core dump of it, to a file or through a
pipe to a crash collector, can carry a value out. If that cannot be done and proved, it refuses with nothing changed.

The three provider tokens are copied in memory from the environment of the running container c3po-r2d2-worker-1,
whose ID the request signs, each from its prefixed or its unprefixed name (the two the settings accept; every one
present byte-equal): the root-private config.v2.json of the signed ID is read twice inside protected Python,
with root-only descriptor traversal, bounded strict JSON and comparison; no worker inspect subprocess. The database URL of the restricted reader and
the emitter password are copied in memory from the two files of September on the data volume
(/mnt/day-d-data/.r2d2-v2-risk-secrets/risk-database-url and
/mnt/day-d-data/.c3po-role-executor-20260908-r2/secret/password): "/", "/mnt" and the data volume (a mount point) equal
to their signed rows, then every directory below it and the file equal to signed identity rows (device, inode, owner,
mode, both change instants; never the size) before each is opened, never following a link; each file regular, with one
link, unchanged while read, and its content within a fixed grammar (the URL that of the restricted reader, with no
query or fragment). Both docker ps checks finish before the first file of September is opened; neither acquires
secret values. Everything is looked at before the
first creation; the secrets directory must be the signed one and empty.

Then one mkdir of emitter and three exclusive creates (O_CREAT|O_EXCL|O_NOFOLLOW, 0600 under umask 0077) relative to
held descriptors, each file written from a bytearray that is zeroed afterwards, fsynced, its metadata proved through
the descriptor, the directory fsynced, and the name opened again and proved by descriptor: the same inode, regular,
uid 0, gid 0, mode 0600, one link. The content is never read back, and no size, digest or length of any value, line or
file is computed for a receipt or reaches one. If a step after a creation fails, the file this run created is removed
again, and only while its name still shows the inode this run holds (an exception to rule 4 of the core, declared in
the signed scope). It never overwrites, renames, chmods, chowns or truncates anything, never reads a file of the deploy
tree, never runs anything but docker ps, and never activates anything. The receipt
carries listed codes, booleans and identity rows only. The caller authenticates exact request/authority/GO/source
bytes first.
No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=True

def unbound_plan(module):
    return {'secrets_chain':None,'data_volume_chain':None,'source_rows':None,'worker_container_id':None,'evidence_boot_id_sha256':None}
