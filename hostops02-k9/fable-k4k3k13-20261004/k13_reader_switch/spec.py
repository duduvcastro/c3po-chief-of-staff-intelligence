"""Assembly specification of K13 (epoch R2D2-V2-SHADOW-2026-10-05): the reader switch. One source, three modes signed
in the plan: ACTIVATE (plan row M6, with reconcile), RESTART (A2 row RST) and DEACTIVATE (plan row X1)."""
NAME='k13_reader_switch'
MODULE='k13_reader_switch'
STEM='HOSTOPS02_K13_READER_SWITCH'
PARTS=['core','runner','docker','parents','files']
HEADER='''"""OP_K13_READER_SWITCH: the switch of the V2 shadow reader unit of epoch R2D2-V2-SHADOW-2026-10-05.

One payload, three modes signed in the plan. ACTIVATE: every guard of the reader README (operation 4) that this core
can express is read first (executor, boot, the session day and the launch window, the three reader unit files, the
producer unit file, the launcher and pins.env by signed SHA-256, the shape of secret.env by metadata only, the release
file, the journal root, its catalog file, its device against the data volume's, its free space, the root-only chains
of the bind sources (Codex decision 6; the data volume bind is reported as not meeting it), the engine's security
options, the pinned image, no other reader container or process); then /etc/c3po-reader/activation.env is created
exclusively with its two constant lines (or, when it already holds exactly those bytes, accepted: reconcile), then
"systemctl enable --now c3po-reader.timer" and "systemctl start --no-block c3po-reader.service", each read back.
RESTART: the same guards with the activation file required, then "systemctl reset-failed" and "systemctl start
--no-block" of the service. DEACTIVATE: no file is read, then "systemctl disable --now c3po-reader.timer" and
"systemctl stop --no-block c3po-reader.service"; nothing is deleted. The only file this source can create is
activation.env (constant, not secret); it never reads, hashes, sizes or prints secret.env, never prints a container's
environment or its command line, never runs docker run, docker exec, docker stop or docker rm, never runs
daemon-reload by itself (enable and disable reload the manager as systemd documents), never waits for a unit to
settle and never retries. The caller authenticates exact request/authority/GO/source bytes first. No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=False

def unbound_plan(module):
    return {'mode':None,'evidence_boot_id_sha256':None,'unit_rows':None,'config_rows':None,'launcher_rows':None,'journal_rows':None,
            'release_rows':None,'release':{'name':None,'sha256':None},
            'files':{'reader_service':None,'reader_timer':None,'reader_alert':None,'producer_service':None,'launcher':None,'pins':None},
            'image_id':None,'journal_free_floor_bytes':None,'source_rows':None,'capacity_rows':None}
