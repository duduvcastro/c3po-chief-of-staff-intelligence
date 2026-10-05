"""Assembly specification of the reader units (MASTER_PLAN row B2) for epoch R2D2-V2-SHADOW-2026-10-05: the three
systemd units of the V2 shadow reader installed exclusively, not activated, not reloaded."""
NAME='reader_units'
MODULE='reader_units'
STEM='HOSTOPS02_READER_UNITS'
PARTS=['core','parents','files']
HEADER='''"""OP_READER_UNITS: the three systemd units of the V2 shadow reader of epoch R2D2-V2-SHADOW-2026-10-05, installed once.

c3po-reader.service (the reader README's template with the values of this source and the source-root bind of Codex
decision 6), c3po-reader.timer and c3po-reader-alert.service (verbatim) are created in /etc/systemd/system, root:root
0644, by exclusive creation only: a dot-prefixed temporary that systemd does not load, unbuffered writes, fsync,
exact metadata, a link to the final name (a link never replaces anything), fsync of the directory, removal of the
temporary once its identity is proved. The bytes are read back through a descriptor inside the run. Everything is
looked at before the first creation: the executor, the boot of the evidence, the signed rows of the unit directory,
the installed producer unit (its bytes, its journal bind and its image), the signed rows of the journal root (and
its two catalogue files, by lstat) and of the data volume, what exists at each name, the drop-ins, dependency directories and leftovers of the lookup
directories, and the time left. This source starts no process: no systemctl verb, no daemon-reload, no enablement,
no start. It reads no secret and never changes, renames or removes an object that exists. Units signed as present
are verified and never touched. The caller authenticates exact request/authority/GO/source bytes first.
No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=True

def unbound_plan(module):
    renders=module.rendered_units()
    return {'unit_rows':None,'journal_rows':None,'data_rows':None,
            'units':[{'key':key,'destination_name':name,'expect':None,'rendered_sha256':module.sha(renders[key]),'rendered_bytes':len(renders[key])}
                     for key,name in module.UNIT_ORDER],
            'acknowledged_leftovers':None,'evidence_boot_id_sha256':None}
