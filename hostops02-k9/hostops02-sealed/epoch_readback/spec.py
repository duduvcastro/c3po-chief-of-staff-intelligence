"""Assembly specification of K11, the epoch readback of HOSTOPS02 (a reading source with the modes PRE and POST)."""
NAME='epoch_readback'
MODULE='epoch_readback'
STEM='HOSTOPS02_EPOCH_READBACK'
PARTS=['core','runner','docker','parents','lock']
SUCCESS_IN_TEMPLATE=False        # the success outcome follows the signed mode: the GO template carries null
HEADER='''"""OP_EPOCH_READBACK (K11): the readback of epoch R2D2-V2-SHADOW-2026-10-05, modes PRE (dry run) and POST.

Observations only. This source has no call that creates, changes or removes anything on the host's filesystem; it
does not carry the files part and its command table has no EFFECT row. PRE takes the release bytes from the signed
request and requires that nothing stands yet where install_release will create its directory; POST reads the
installed release file. In both modes the release is verified by the deployed code itself (Release.verify) in one
attached container of the signed image ID that has no network, a read-only root filesystem and at most one read-only
bind (POST: the installed release directory; PRE: none, or an existing private directory signed as a probe of the
bind of the bind itself); the pinned snippet travels on standard input and prints booleans and codes (the release's own
refusal code or the name of an exception's class, never a message). The live policy candidate is put to the deployed
controller's and assembler's own validators in that same container. What install_release and activate refuse on
before any effect is looked at beforehand and is a finding here: the place of each directory they create, the pin,
the free space, the live names of the running worker, the bind of the data volume in the render, and the signed
milliseconds of the docker reads. Around it: pinned directories walked from "/", the compose render with the intended override on
standard input (never written to the host), image and worker metadata, the signed environment names of the worker
as booleans, unit states, free space of the journal filesystem, and a probe of the deployment lock. Each item is
observed on its own: a failed observation is UNAVAILABLE with a constant code, never an absence; a mismatch is a
finding that leaves every other item in the receipt; what the signed plan omits is not observed and the receipt
says so. No value of an environment, no byte of the release, of the policy or of the render, and no name of an
instrument leaves the run. The caller authenticates exact request/authority/GO/source bytes first.
No action on import.
"""
'''

def unbound_plan(module):
    return {'mode':None,'evidence_boot_id_sha256':None,'revision':None,'package_sha256':None,'image':None,'worker':None,'release':None,
            'policy':None,'render':None,'deploy':None,'units':None,'journal':None,'docker_config':None,'rows_in_receipt':None,'bind_probe':None,
            'dry_run':None,'live':None,'limits':None}
