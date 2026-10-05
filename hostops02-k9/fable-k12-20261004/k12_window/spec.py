"""Assembly specification of K12w (epoch R2D2-V2-SHADOW-2026-10-05): the write program of the morning capacity
dispatch, one signed mode per request: LAUNCH (D1), PERSIST (D3), STOP (D4) and REMOVE (X3)."""
NAME='k12_window'
MODULE='k12_window'
STEM='HOSTOPS02_K12_WINDOW'
PARTS=['core','runner','docker','parents','files']
HEADER='''"""OP_K12_WINDOW: the capacity-day window of epoch R2D2-V2-SHADOW-2026-10-05, one signed mode per request.

LAUNCH (plan row D1): docker create and docker start of one detached container of the signed backend image, without
--rm, that runs the capacity-day writer (manifest_writer, delivered by hash into the capacity tree's config root) with
the exact arguments, binds, network and environment files of the documents tool's REQUEST for that window, which the
plan carries byte for byte, every bind source and every one of its ancestors controlled by root alone except the named read-only data
volume (its release file hashed before the create and after the start); the container
parks until its veto view. PERSIST (D3): docker logs, bounded in seconds and bytes, of the exited container identified
by ID, name and labels, with a known exit code; exactly one complete writer receipt consistent with that exit code, or
nothing is written; stored with the exit state in one private file (root:root 0600, created exclusively, fsync, read
back) in the capacity receipts directory. STOP (D4): docker stop of the parked container of that window before its
view. REMOVE (X3, Friday 09/10): docker rm, without -f or -v, of exited capacity-day containers whose private receipt
is on the host or which ended by a stop before their view. Every container is identified by its name, its two labels,
its image, its argv and its binds before anything is done to it. Everything is looked at before the first effect;
every effect is read back inside the run. This source never writes into the manifests directory, the capacity tree,
the journal or the data directory, never
reads or hashes the environment files beyond the metadata of the secret one, never prints a container's environment,
the manifest hash or the symbol count, never activates anything and never pulls an image. The caller authenticates
exact request/authority/GO/source bytes first. No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=True

def unbound_plan(module):
    return {'mode':None,'capacity_request':None,'launch_request_sha256':None,'removals':None,'parent_rows':None,'evidence_boot_id_sha256':None}
