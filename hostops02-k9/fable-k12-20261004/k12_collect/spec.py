"""Assembly specification of K12r (epoch R2D2-V2-SHADOW-2026-10-05): the read program of the morning capacity dispatch,
modes COLLECT (plan row D2) and TREE (the rows every K12 request signs)."""
NAME='k12_collect'
MODULE='k12_collect'
STEM='HOSTOPS02_K12_COLLECT'
PARTS=['core','runner','docker','parents']
HEADER='''"""OP_K12_COLLECT: the read of the capacity-day window of epoch R2D2-V2-SHADOW-2026-10-05, one signed mode per request.

COLLECT (plan row D2): the container of one window, by its deterministic name, inspected with this family's own format
(state, exit code, labels, argv, binds; never its environment); the private receipt that K12w PERSIST wrote for it in
the capacity receipts directory, with the writer's one line inside; the day's manifest in the manifests directory
(owner, mode, links, and whether its SHA-256 equals the line's), read on the host. The receipt says, at its top, the
verdict of the window (VERIFIED, TERMINAL_EMPTY_LIST, STOPPED_BEFORE_THE_VIEW, NOT_VERIFIED, PENDING_PERSIST or
UNCERTAIN) and only what may leave the host:
never the manifest hash or the symbol count. TREE: the signed rows of every directory a K12 request walks (each judged
controlled by root alone from '/', the release directory of the named read-only data volume by its own rule), the boot, and the metadata (never the bytes) of the environment files and of the journal catalog. Read-only: no file is created,
written or removed, no container is created, started, stopped or removed, no image is pulled. The caller authenticates
exact request/authority/GO/source bytes first. No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=True

def unbound_plan(module):
    return {'mode':None,'capacity_request':None,'launch_request_sha256':None,'tree_journal':None,'parent_rows':None,'evidence_boot_id_sha256':None}
