"""Assembly specification of K13r (epoch R2D2-V2-SHADOW-2026-10-05): the read-only liveness readback of the V2 shadow
reader (plan row M7, A2 rows V-1, V-2, V-s), and its stop readback after a deactivation (X1)."""
NAME='k13r_reader_liveness'
MODULE='k13r_reader_liveness'
STEM='HOSTOPS02_K13R_READER_LIVENESS'
PARTS=['core','runner','docker']
HEADER='''"""OP_K13R_READER_LIVENESS: the read-only liveness readback of the V2 shadow reader of epoch R2D2-V2-SHADOW-2026-10-05.

Read-only. Mode LIVE (after an activation or a restart): the boot, the reader service and timer as systemd shows them
(systemctl show, is-enabled), exactly one container named c3po-reader, running, its image ID equal to the signed pin,
its start instant and restart count, its binds through a template that prints .Mounts only (each a read-only bind:
the four of the reader README and the epoch source root of Codex decision 6; the uid-1000 data volume bind reported), its main command (the launcher under python -I -B, with an init
process, a read-only root filesystem and uid 0), and the main command of every other running container (no second
reader). Mode STOPPED (after a deactivation): the timer disabled and inactive, the service inactive or failed, no container
named c3po-reader, no reader process elsewhere. Each item is observed on its own; a failed observation is
UNAVAILABLE, never an absence; a mismatch is a finding. Never prints docker inspect unformatted, an environment, a
command line, a log line; never starts, stops, creates or removes anything; starts no container; makes no system call
that changes the host. The caller authenticates exact request/authority/GO/source bytes first. No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=False

def unbound_plan(module):
    return {'mode':None,'image_id':None,'evidence_boot_id_sha256':None,'source_target':None}
