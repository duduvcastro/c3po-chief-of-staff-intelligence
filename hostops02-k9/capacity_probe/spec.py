"""Assembly specification of PROBE (K6b's probe source): the capacity probe of the epoch, steps CALENDAR, IDENT and LOAD."""
NAME='capacity_probe'
MODULE='capacity_probe'
STEM='HOSTOPS02_CAPACITY_PROBE'
PARTS=['core','runner','docker','parents']
SUCCESS_IN_TEMPLATE=False        # the success outcome follows the signed step: the GO template carries null
HEADER='''"""OP_CAPACITY_PROBE: the capacity probe of epoch R2D2-V2-SHADOW-2026-10-05, one signed step per request.
A reading source of the frozen core: it creates and changes nothing on the filesystem of the host.

Each request names ONE step and the source starts attached containers of the signed image ID (the production backend
image by its local ID, carrying the release revision label) with the core's argv: removed on exit, never a pull, an
init process, uid 0, no network, a read-only root filesystem, no capability, no new privilege. The pinned script of
the step travels on standard input to python -I -B -.
CALENDAR (A5): one container with no bind runs calendar-pin.py, carried byte for byte (sha256 5a6066ae...), and the
printed line must name the epoch, the package and the document order this source pins.
IDENT (A5): the capacity tree is walked from "/" by its signed parent rows and held; the root and its four children
must be root-owned 0700 directories; two containers, one after the other, each with the tree bound read-only at
/c3po-capacity, print the AnchoredRoot identities of documents, payload and go (and config); both runs must agree and
equal the identities this source computes from the device and inode numbers it read on the host.
LOAD (B4c): the running worker c3po-r2d2-worker-1 must be on the signed image with exactly one mount at
/c3po-capacity, a read-only bind of the signed tree; the static config file is read on the host and must have the
signed hash; then one fresh container with the same read-only bind loads Settings and CapacityConfig with the signed
config path, config hash and release hash, and must print CAPACITY_STARTUP_OK with the roots documents, go and payload
and the veto mode DISPATCH_AND_DERIVATION_ONLY.
Before any container: the executor, the boot of the evidence, the image, the tree, the worker and the container list,
under which a refusal has started nothing. After: the container list again (and the worker, and the held tree), so
that the receipt says whether anything of the run is left. Nothing is removed, retried or repaired by this process.
The caller authenticates exact request/authority/GO/source bytes first; the source accepts only a window inside the
band of its step (A2 rev 3, section 6-A).
No action on import.
"""
'''

def unbound_plan(module):
    return {'step':None,'image_id':None,'image_revision':None,'capacity':None,'load':None,'evidence_boot_id_sha256':None}
