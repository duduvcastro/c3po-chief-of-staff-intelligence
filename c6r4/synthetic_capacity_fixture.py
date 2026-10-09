"""SYNTHETIC capacity helper extracted by AST; no closed test class imported/run."""
import ast
import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import image_path_adapter as a
OPEN = datetime(2026, 10, 12, 13, 30, tzinfo=timezone.utc)
PREPARED = OPEN - timedelta(hours=2)
CAPTURE_OPEN = datetime(2026, 10, 12, 14, 0, tzinfo=timezone.utc)
CAPTURE_CLOSE = CAPTURE_OPEN + timedelta(minutes=1)

def fixture():
    (uid, gid) = (0, 0)
    s = a.Scope('1' * 40, 'sha256:' + '2' * 64, '3' * 64, '4' * 64, '5' * 64, '6' * 64, '7' * 64, '8' * 64, '9' * 64, uid, '/fixture-private-manifests', OPEN, PREPARED - timedelta(seconds=1), PREPARED + timedelta(seconds=12), PREPARED, 'DELEGATED_ACT_B')
    document = {'schema': 'V2_DAILY_CAPACITY_BINDING_CANDIDATE_V1', 'epoch': s.epoch, 'day': s.day, 'release_sha': s.release_sha256, 'monitored_symbols': ['FIXA', 'FIXB'], 'contract': {'synthetic': True}}
    binding = {'sha': a.digest(document), 'document': document}
    state = {'epoch': s.epoch, 'release_sha': s.release_sha256, 'daily_capacity': {s.day: binding}, 'sessions': {}}
    payload = {'journal_key': 'capacity-prepared:' + s.day, 'type': 'CAPACITY_DAY_PREPARED', 'session': s.day, 'plan_sha': binding['sha'], 'payload': document}
    record = {'epoch': s.epoch, 'sequence': 1, 'journal_key': payload['journal_key'], 'recorded_at': PREPARED.isoformat(), 'payload': payload, 'previous_sha': ''}
    record['record_sha'] = a.digest(record)
    row = {'state': state, 'state_sha': a.digest(state), 'journal_head': record['record_sha']}
    manifest = a.FileEvidence(a.canonical({'epoch': s.epoch, 'session': s.day, 'symbols': document['monitored_symbols'], 'owner_uid': uid}), 1, 2, uid, gid, 384, 1)
    receipt = {'schema': 'R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1', 'status': 'PUBLISHED_VERIFIED', 'code': None, 'mode': 'PUBLISH', 'epoch': s.epoch, 'session': s.day, 'owner_uid': uid, 'build_sha': s.build_sha, 'release_sha256': s.release_sha256, 'package_sha256': s.package_sha256, 'capacity_config_sha256': s.capacity_config_sha256, 'capacity_veto_mode': 'DISPATCH_AND_DERIVATION_ONLY', 'massive_bars_enabled': True, 'cutoff_at': (OPEN - timedelta(minutes=10)).isoformat(), 'go_mode': s.require_go_mode, 'go_sha256': 'a' * 64, 'template_sha256': 'b' * 64, 'binding_sha256': binding['sha'], 'manifest_sha256': a.sha(manifest.raw), 'symbol_count': 2, 'file': {'uid': uid, 'gid': gid, 'mode': '0600', 'nlink': 1, 'device': 1, 'inode': 2, 'size_within_limit': True}, 'view': {'observed_at': PREPARED.isoformat(), 'valid_until': (PREPARED + timedelta(seconds=10)).isoformat()}}
    ready = a.FileEvidence(a.canonical({'epoch': s.epoch, 'session': s.day}), 1, 3, uid, gid, 384, 1)
    directory = a.DirectoryPin(1, 44, uid)
    catalog = a.FileEvidence(a.canonical({'schema': 'MASSIVE_SESSION_V1', 'epoch': s.epoch, 'session': s.day, 'symbols': document['monitored_symbols'], 'device': 1, 'inode': 44}), 1, 4, uid, gid, 384, 1)
    return (s, receipt, row, [record], manifest, ready, catalog, directory)
