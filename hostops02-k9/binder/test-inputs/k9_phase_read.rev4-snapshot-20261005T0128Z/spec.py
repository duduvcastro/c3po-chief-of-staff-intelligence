"""Assembly specification of K9R, the read program of the delegated daily phases of HOSTOPS02 (a reading source with
the modes RESULT, PROBE, POLICY and TREE)."""
NAME='k9_phase_read'
MODULE='k9_phase_read'
STEM='HOSTOPS02_K9_PHASE_READ'
PARTS=['core','runner','docker','parents']
SUCCESS_IN_TEMPLATE=False        # the success outcome follows the signed mode: the GO template carries null
HEADER='''"""OP_K9_PHASE_READ (K9R): the read program of the delegated daily phases of epoch R2D2-V2-SHADOW-2026-10-05.

Observations only. This source has no call that creates, changes or removes anything on the host's filesystem; it
does not carry the files part and its command table has no EFFECT row. Four signed modes. RESULT: the collect of one
detached K9 container: the launch record written by the write program, the container's state and exit code by a
docker inspect with this source's own fixed format (never its environment), the step's start marker and its one
receipt (the K9 runner's, or the packaged risk executor's in its spool), and the files the receipt names, hashed again
on the host. PROBE: the provider readiness of the previous session, read by one attached container of the signed image
ID with the provider environment file of the K9 tree, no bind and a read-only root filesystem, running a pinned
snippet (standard input) that calls only the image's certified producer code and prints counts and hashes. POLICY: the
installed live policy and release files read on the host, and the running worker's state and five environment names
as booleans. TREE: the weekly prerequisite read: the rows of every directory of the K9 tree and of the source root
from "/", the boot, and the metadata (never the content or size) of the secret files and the content hash of the
runner. Each item is observed on its own: a failed observation is UNAVAILABLE with a constant code, never an absence;
a mismatch is a finding that leaves every other item in the receipt. No value of an environment, no byte of a secret,
no symbol of an instrument and no provider payload leaves the run. The caller authenticates exact
request/authority/GO/source bytes first.
No action on import.
"""
'''

def unbound_plan(module):
    return {'mode':None,'epoch':None,'day':None,'k9_phase':None,'k9_operation':None,'slot':None,'attempt_key':None,'run_not_after':None,
            'constants':None,'parent_rows':None,'evidence_boot_id_sha256':None,'policy_read':None}
