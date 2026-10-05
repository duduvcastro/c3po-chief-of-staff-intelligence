"""Assembly specification of K6b, capacity switch (epoch R2D2-V2-SHADOW-2026-10-05, session days): MOUNT, ENABLE,
DISABLE_FAST, DISABLE_FULL of the capacity of the compose worker, one signed mode per request."""
NAME='capacity_switch'
MODULE='capacity_switch'
STEM='HOSTOPS02_CAPACITY_SWITCH'
PARTS=['core','runner','docker','parents','files','lock']
HEADER='''"""OP_CAPACITY_SWITCH: the capacity mount, enable and disable of the compose worker r2d2-worker for epoch
R2D2-V2-SHADOW-2026-10-05, one signed mode per request (MOUNT, ENABLE, DISABLE_FAST, DISABLE_FULL), on a session day.

What c3po/deployment/capacity-mount/README.md at the release does by hand (step 1, step 3, fast and full disable),
in the HOSTOPS02 family and with the compose file list of the activation (K6a): the compose file of the deploy plus
the override the activation delivered, so that a recreate keeps the release and live-policy pins. Under the
deployment lock it edits the environment file of the project in place through one attached container of the signed
backend image, run as the account that owns that file, with no network, a read-only root and that one file bound
read-write: the trailing block of capacity settings is appended to or cut, every other byte stays as it was. It then
renders the project from the edited file and recreates that one service. Everything is looked at before the first
effect: the executor, the boot of the evidence, the deploy tree, the deployed revision, the environment file (in
memory only) and the block it holds, the compose file, the override (compared with the four signed values), the
capacity tree and its static config (MOUNT and ENABLE), the worker, its image, its environment (booleans), its mounts,
the render, the lock (waited for at most the signed seconds and never past the point where both effects would no
longer fit), and under it: no security reboot pending, every held directory still reached by its name, nothing
changed since the first look, no container left by an interrupted recreate of the service. Every effect is read back
inside the run. When the render after the edit is not as signed, the edit is withdrawn by the same editor and the
worker is not recreated. It never runs docker exec, a shell, a systemctl verb or a pull, never writes the capacity
tree, and prints no value it read from an environment, from the render or from the environment file. A run that
changed anything and did not finish is PARTIAL, never a refusal, and says which of its effects exist. The caller
authenticates exact request/authority/GO/source bytes first. No action on import.
"""
'''

def unbound_plan(module):
    return {key:None for key in sorted(module.PLAN_KEYS)}
