"""Assembly specification of K12p (epoch R2D2-V2-SHADOW-2026-10-05): the writer's --preflight in the dispatch's own
layout, mandatory before the first primary window (plan row D0; CAP README "--preflight")."""
NAME='k12_preflight'
MODULE='k12_preflight'
STEM='HOSTOPS02_K12_PREFLIGHT'
PARTS=['core','runner','docker','parents','files']
HEADER='''"""OP_K12_PREFLIGHT: the capacity-day writer's --preflight in the dispatch layout, epoch R2D2-V2-SHADOW-2026-10-05.

One attached docker run --rm of the signed backend image (--pull never, --init, --user 0:0, --read-only, --cap-drop
ALL, no-new-privileges) with exactly the name, network, two environment files, four inline values and four binds that
the primary window's REQUEST (the documents tool's, carried byte for byte) gives the detached launch, the manifests
directory bound read-write as in the dispatch (the writer's preflight refuses a read-only one), running python -I -B on
the writer delivered by hash in the capacity tree's config root with that REQUEST's argv plus --preflight. A WRITE
program: before the run it creates one claim file (root:root 0600, exclusive, fsync, read back) in the capacity
receipts directory, one preflight per day; its effects on the manifests directory are closed: the container is proved
gone and every entry of the directory and the directory itself unchanged afterwards. Every bind source and every one of
its ancestors is controlled by root alone, except the named read-only data volume (/mnt/day-d-data, whose
release file is hashed before and after the run). Everything is looked at before the claim: the writer's and the window
config's bytes, pins.env's bytes, secret.env's metadata only, the empty docker CLI directory, the journal catalog, the
image. Standard output is the one line, parsed and reduced to what may leave the host. Nothing else is started,
created, changed or removed. The caller authenticates exact request/authority/GO/source bytes first. No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=True

def unbound_plan(module):
    return {'capacity_request':None,'parent_rows':None,'evidence_boot_id_sha256':None}
