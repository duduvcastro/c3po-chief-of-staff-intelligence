"""Assembly specification of K6a, activate (epoch R2D2-V2-SHADOW-2026-10-05, first session only, single shot)."""
NAME='activate'
MODULE='activate'
STEM='HOSTOPS02_ACTIVATE'
PARTS=['core','runner','docker','parents','files','lock']
HEADER='''"""OP_ACTIVATE: the activation of the compose worker for epoch R2D2-V2-SHADOW-2026-10-05, once, on the first session day.

What the activation of 2026-09-28 did, in the HOSTOPS02 family: under the deployment lock it creates one private
directory in a signed parent of the data volume, delivers into it the signed live policy and a compose override that
sets four names of the environment of the service r2d2-worker (live policy file and hash, release file and hash),
and recreates that one service with the file list of the deploy plus the override. Everything is looked at before
the first creation: the executor, the boot of the evidence, the four pinned directories, the release an earlier
operation installed (read and compared by hash), the deployed revision, the maintenance pin, the worker and its
image, the environment file and the compose file of the project, the render of the project with the override on
standard input, the lock (waited for at most the signed seconds and never past the point where the recreate would no
longer fit), and under it: no security reboot pending, every held directory still reached by its name, nothing changed
since the first look, no container left by an interrupted recreate of the service, room on the data volume. Every
effect is read back inside the run: the files by descriptor, the worker twice with a fixed pause between, its
environment inside a docker template that prints booleans only, every other container by ID, the environment file and
the compose file by signature and by a hash that stays in memory, the release by its name. It never runs docker exec,
a shell, a systemctl verb or a pull, never overwrites, renames, chmods, chowns or removes anything but its own
temporary, and prints no value it read from an environment (the four signed values of the override are shown in the
effects). A run that changed anything and did not finish is PARTIAL, never a refusal, and says which of its effects
exist. The caller authenticates exact request/authority/GO/source bytes first. No action on import.
"""
'''

def unbound_plan(module):
    return {key:None for key in sorted(module.PLAN_KEYS)}
