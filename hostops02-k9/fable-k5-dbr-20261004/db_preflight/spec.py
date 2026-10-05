"""Assembly specification of DBR: the three fixed read-only database queries of ORD:28 (M7)."""
NAME='db_preflight'
MODULE='db_preflight'
STEM='HOSTOPS02_DB_PREFLIGHT'
PARTS=['core','runner','docker','parents']
HEADER='''"""OP_DB_PREFLIGHT: the read-only database checks of ORDEM_EPOCA_03 line 28 (waiver M7,
READONLY_PSQL_PREFLIGHT_ONLY, no manual DDL), in two signed modes of these bytes, each its own request and GO. PRIV: the
read of the existing restricted reader role c3po_v2_risk_reader by catalog functions only (CONNECT on the database,
USAGE on public, SELECT on r2d2_v2_shadow_epochs and r2d2_v2_shadow_journal, the role restricted, the session
read-only), in one read-only transaction, booleans only. QUERIES: exactly the three ORD:28 queries (the epoch row
count; the preconditions of the causal emitter by the release's own check, as the emitter; whether the capacity
binding of the signed session is committed), and only with a signed PRIV receipt of the same boot and UTC day that
proved every privilege. No docker exec: ONE attached container of the signed backend image ID on the compose network
c3po_c3po_internal (database only, no egress), read-only root filesystem, no capability, uid 0, and read-only binds
only of what K3-K9 placed under the K9 root (root:root, every ancestor root-owned and closed to group and other
writes): the reader URL file, and in QUERIES the emitter password directory. A pinned snippet, carried in this source
and compared with its hash, prints one line of booleans, counts, constant codes and hashes; this source checks every
member and compares the signed expectations. Everything on the host is looked at first (executor, boot, the K9
secrets chain by its signed rows, the credentials by lstat only, the image, the container name); the container starts
only when nothing it would read is in doubt. No DDL, no administrator or other credential, no inferred role. This
source never reads a credential itself, writes nothing, starts no other process, and no credential, DSN or exception
text reaches the receipt. The caller authenticates exact request/authority/GO/source bytes first. No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=False                # the success outcome follows the signed mode: the GO template carries null

def unbound_plan(module):
    return {'mode':None,'priv_receipt':None,'secrets_chain':None,'image_id':None,'image_revision':None,'session':None,'release_receipt_sha256':None,'expected':None,
            'evidence_boot_id_sha256':None}
