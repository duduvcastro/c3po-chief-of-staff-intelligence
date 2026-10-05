"""A private temporary tree that stands in for "/" in the native tests of the reader units: install_release's tree
(tests/native_support.py: the data volume with its pin, the boot identifier) plus what E1, A9 and E3 left on the
host: the unit directory with the installed producer unit (the render of the e3 request), and the journal root with
the two catalogue files. Test user reported as root by the core's oslevel substitution; nothing here is a host."""
import os

import native_support
import ru

def build(base):
    root=native_support.build_tree(base)
    units=root/'etc'/'systemd'/'system';units.mkdir(parents=True)
    for path in (root/'etc'/'systemd',units):os.chmod(path,0o755)
    producer=units/'c3po-massive.service';producer.write_bytes(ru.producer_bytes());os.chmod(producer,0o644)
    journal=root/'var'/'lib'/'c3po-bar'/'journal';journal.mkdir(parents=True)
    for path in (root/'var',root/'var'/'lib'):os.chmod(path,0o755)
    for path in (root/'var'/'lib'/'c3po-bar',journal):os.chmod(path,0o700)
    for name,content in (('epoch.json',ru.EPOCH_FILE),('maintenance.lock',b'')):
        (journal/name).write_bytes(content);os.chmod(journal/name,0o600)
    return root

def fields(root,expect=None,leftovers=()):
    return {'unit_rows':native_support.rows(root,ru.UNITS),'journal_rows':native_support.rows(root,ru.JOURNAL),
            'data_rows':native_support.rows(root,ru.DATA),'units':ru.unit_rows(None,expect),'acknowledged_leftovers':list(leftovers),
            'evidence_boot_id_sha256':ru.f.sha(native_support.BOOT.strip())}
