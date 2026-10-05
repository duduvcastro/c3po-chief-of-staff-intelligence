"""Assembly specification of K5: supervisor operation (5), the activation of the bar supervisor timer (B11)."""
NAME='supervisor_activate'
MODULE='supervisor_activate'
STEM='HOSTOPS02_SUPERVISOR_ACTIVATE'
PARTS=['core','runner','docker','parents']
HEADER='''"""OP_SUPERVISOR_ACTIVATE: supervisor operation (5) of ORDEM_EPOCA_03 (B11), the activation of the bar supervisor
units that operation (3) installed without activation and without a reload. Two signed modes of these bytes, one GO
each, one effect each. ACTIVATE: systemctl enable --now c3po-massive.timer, the timer only (systemctl reloads the
manager itself: this is the reload the installation named operation 5 the owner of), read back at once; the immediate
start of c3po-massive.service that the timer causes is not waited for (core rule 9). RESET: a later run that sees that
start (its signed InvocationID) ended in the supervisor's terminal refusal (exit 78, not restarted, no claim, no container),
then systemctl reset-failed c3po-massive.service. Everything is looked at before the one effect: the executor, the
boot of the evidence, the window of the GO (never inside the session window of a session day, with a margin), the
signed rows of the unit directory, the bytes and identity of both unit files, no drop-in, the enablement link (absent
before ACTIVATE, present before RESET), the states of both units and of docker.service, the image and its retention
tag, no container named c3po-massive, the token metadata (never its content or size), the entry counts of the journal
root, the claim root and the docker CLI directory, and the time left. After the effect nothing refuses and what the run
leaves is read back. It reads no secret, writes no file itself, starts no container, never starts or enables the
service directly, never stops, disables or removes anything, and never waits. The caller authenticates exact
request/authority/GO/source bytes first. No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=False                # the success outcome follows the signed mode: the GO template carries null

def unbound_plan(module):
    return {'mode':None,'unit_directory':None,'units':None,'supervisor_paths':None,'expected_entries':None,'image_id':None,
            'retention_reference':None,'invocation_id':None,'evidence_boot_id_sha256':None}
