"""Assembly specification of K8 (epoch R2D2-V2-SHADOW-2026-10-05): the eve delivery E6 of one session day, the day's
signed capacity documents and the payload file assembled on the host from the committed causal list."""
NAME='k8_eve'
MODULE='k8_eve'
STEM='HOSTOPS02_K8_EVE_DELIVERY'
PARTS=['core','parents','files']
HEADER='''"""OP_K8_EVE: the eve delivery (E6) of one session day of epoch R2D2-V2-SHADOW-2026-10-05.

Into the capacity tree /var/lib/c3po-capacity, whose four roots (config, documents, go, payload) must already exist as
root:root 0700 directories: the twelve signed files of the day (template, two GO records, publication record and one
veto view per window into documents; the admission and bar_manifest GO files into go; one capacity config per window
into config), each holding exactly the bytes whose SHA-256 and size the request signs; and the payload file
session=<day>.json into payload, the canonical JSON of the signed contract and of the causal object of the day's
committed causal list, read by fixed path from the K9 tree (/var/lib/c3po/r2d2-v2-k9-20261005/days/<day>/causal) and
accepted only when its bytes are the ones the day's commit receipt names and its two hashes are the contract's causal
scope. Every file root:root 0600, by exclusive creation: a temporary file with unbuffered writes and fsync, exact
metadata, a link to the final name (a link never replaces anything), fsync of the directory, removal of the temporary
once its identity is proved; every file read back through descriptors inside the run. Everything is looked at before
the first creation: the executor, the window, the boot of the evidence, the signed chain to the K9 days, the capacity
tree, the commit receipt and the commitment, the seven chain documents the configs pin, the absence of every name, the
roots' identities, free space and the time left. This source starts no process, opens no socket, reads no environment
and no secret, writes no secret, never activates anything, never touches a container and never changes, renames or
removes an object that exists. No symbol and no hash or size of the payload file reaches its receipt. The caller
authenticates exact request/authority/GO/source bytes first. No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=True

def unbound_plan(module):
    return {'day':None,'windows':None,'contract':None,'files':None,'days_parent':None,'identity_rule':None,'evidence_boot_id_sha256':None}
