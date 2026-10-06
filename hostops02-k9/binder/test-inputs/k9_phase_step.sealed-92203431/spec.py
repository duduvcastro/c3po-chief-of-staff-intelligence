"""Assembly specification of K9W, the write program of the delegated daily phases of HOSTOPS02 (a writing source with
the modes LAUNCH, ATTACHED and CLEANUP; the mode follows the signed operation)."""
NAME='k9_phase_step'
MODULE='k9_phase_step'
STEM='HOSTOPS02_K9_PHASE_STEP'
PARTS=['core','runner','docker','parents','files']
SUCCESS_IN_TEMPLATE=False        # the success outcome follows the mode of the signed operation: the GO template carries null
HEADER='''"""OP_K9_PHASE_STEP (K9W): the write program of the delegated daily phases of epoch R2D2-V2-SHADOW-2026-10-05.

One signed step of the closed step table per run. Everything is looked at first, read-only: the executor, the window of
D, the boot of the evidence, the signed chains of the K9 tree and of the source root from "/", the absence of this
attempt's claim, the day directory, the K9 containers the engine lists, the exited container of the previous step named
by its launch record (inspected by ID: name, image, labels, state), every input of the step by fixed path (the
predecessors' receipts, the destinations, the environment files by lstat only, the runner file, the space floor), the
signed image, and the time left. Then: the claim file by exclusive creation; the removal of the previous step's exited
container (docker rm of its ID, no -f, no -v); for collect_launch the day directories; the step plan; and one container
of the signed image ID: LAUNCH creates it (no --rm, its own timeout -s KILL limit) and starts it after every mounted
directory has been proved again, then writes the launch record; ATTACHED runs it with --rm and reads its receipt back;
CLEANUP only removes. When an input is not complete the run removes the previous exited container and refuses
(removal-only). It never reads a secret (the docker CLI reads the environment files), never stops, kills or execs into
a container, never pulls, never overwrites, renames or removes a file. The caller authenticates exact
request/authority/GO/source bytes first.
No action on import.
"""
'''

def unbound_plan(module):
    return {'mode':None,'epoch':None,'day':None,'k9_phase':None,'k9_operation':None,'slot':None,'attempt_key':None,'run_not_after':None,
            'constants':None,'parent_rows':None,'evidence_boot_id_sha256':None,'bind':None}
