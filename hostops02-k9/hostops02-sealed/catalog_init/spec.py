"""Assembly specification of K2a: the catalog initialisation of the bar journal (supervisor operation 4b)."""
NAME='catalog_init'
MODULE='catalog_init'
STEM='HOSTOPS02_CATALOG_INIT'
PARTS=['core','runner','docker','parents','files']
HEADER='''"""OP_CATALOG_INIT: supervisor operation 4b, the catalog initialisation of the bar journal root. One source, two
signed modes that run the same bytes: REAL on the journal root that operation 2 created (a leaf of /var/lib/c3po-bar,
never the state root), with the epoch string that this source carries as a constant and the docker CLI under the
unit's empty configuration directory /etc/c3po-bar/docker-cli; REHEARSAL on a throwaway root and under a throwaway
configuration directory that this run creates in /var/lib, with a diagnostic epoch string. A rehearsal only reads the
real journal root and the configuration directory of the unit: none of its docker commands runs under that directory.

It starts ONE attached container of the signed image ID with the argv of the supervisor README, word for word (no
network, the journal root bound read-write at the signed container path as the only mount, the docker CLI under an
empty configuration directory), and gives it the README's pinned script on standard input. The script bytes travel
inside this source and are compared with the pinned hash before anything is looked at. REAL looks at everything
before the container is started: a refusal up to that point has changed nothing and leaves the root usable. A
REHEARSAL refuses with nothing changed up to the creation of its first directory; what a docker read finds after
that is a PARTIAL that has touched nothing of production. After the container was started nothing refuses: what it
left is read back on the host through the descriptor held since before the run (the two names, their owner, mode and
link count, and the bytes of epoch.json against the epoch and the device and inode of the root), and anything but a
verified CATALOG_READY is a PARTIAL whose root is not to be used again. Nothing is removed and nothing that exists
is overwritten, renamed, chmodded or chowned by this process; no unit is touched; no token, manifest, state root or
network reaches the container. The caller authenticates exact request/authority/GO/source bytes first.
No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=False                # the success outcome follows the signed mode: the GO template carries null

def unbound_plan(module):
    return {'mode':None,'journal_chain':None,'throwaway_name':None,'reference_chain':None,'container_journal_root':None,
            'docker_config_chain':None,'image_id':None,'image_revision':None,'epoch':None,'script_sha256':None,
            'evidence_boot_id_sha256':None}
