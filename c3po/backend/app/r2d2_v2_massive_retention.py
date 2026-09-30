"""Verified retention planning only; never unlinks or changes a journal.

Execution requires a separate exclusive producer/consumer maintenance boundary
and a durable collector acknowledgement. A proposed cursor is not an ACK.
"""
from .r2d2_v2_massive_maintenance import journal_access
from .r2d2_v2_massive_sessions import MAX_SESSIONS
import hashlib
from typing import Any, cast
from datetime import date, timedelta
from zoneinfo import ZoneInfo
import re
from .r2d2_v2_sources import canonical, _require, _time


def plan_retention(journal, *, committed_sequence, retain_from_session, max_records=500000):
    with journal_access(journal.path.parent):
        return _plan_retention_locked(journal, committed_sequence=committed_sequence,
                                      retain_from_session=retain_from_session, max_records=max_records)


def _plan_retention_locked(journal, *, committed_sequence, retain_from_session, max_records=500000, journal_session=None):
    _require(type(committed_sequence) is int and committed_sequence >= 0, 'RETENTION_ACK')
    _require(type(max_records) is int and 0 < max_records <= 500000, 'RETENTION_LIMIT')
    _require(isinstance(retain_from_session, str), 'RETENTION_SESSION')
    try:
        cutoff = date.fromisoformat(retain_from_session)
    except ValueError:
        raise ValueError('RETENTION_SESSION') from None
    _require(cutoff.isoformat() == retain_from_session, 'RETENTION_SESSION')
    previous_cutoff = journal._retention_cutoff_locked()
    _require(not previous_cutoff or retain_from_session >= previous_cutoff,
             'RETENTION_CUTOFF_REVERSED')
    floor = journal._retention_floor_locked()
    _require(committed_sequence >= floor, 'RETENTION_ACK_PRUNED')
    after = floor
    through = None
    previous_session = None
    prefix_open = True
    removed = []
    candidate_raw = set()
    retained_raw = set()
    count = 0
    chain = hashlib.sha256()
    while True:
        page = journal._page_locked(after, through=through, limit=1024)
        through = page['through']
        _require(committed_sequence <= through, 'RETENTION_ACK_AHEAD')
        for record in page['records']:
            count += 1
            _require(count <= max_records, 'RETENTION_LIMIT')
            receipt = record['receipt']
            session = receipt['event']['session']
            parsed = date.fromisoformat(session)
            _require(parsed.isoformat() == session, 'RETENTION_SESSION')
            _require(journal_session is None or session==journal_session, 'RETENTION_JOURNAL_SESSION_MISMATCH')
            _require(previous_session is None or session >= previous_session,
                     'RETENTION_SESSION_REVERSED')
            previous_session = session
            chain.update(canonical({'sequence': record['sequence'],
                                    'receipt_sha256': record['receipt_sha256']}))
            # Keep the last acknowledged receipt as the source predecessor.
            # Remove only a contiguous old prefix, never holes in retained data.
            eligible = session < retain_from_session and record['sequence'] < committed_sequence
            prefix_open = prefix_open and eligible
            raw = receipt.get('raw_sha256')
            if prefix_open:
                removed.append(record['receipt_sha256'])
                if raw is not None: candidate_raw.add(raw)
            elif raw is not None:
                retained_raw.add(raw)
        after = page['after']
        if not page['has_more']: break
    # A concurrent append makes this a stale plan; no execution is implied.
    latest = journal._page_locked(through, limit=1)
    _require(latest['through'] == through, 'RETENTION_SNAPSHOT_CHANGED')
    result = {
        **({'journal_session':journal_session} if journal_session is not None else {}),
        'status': 'REVIEW_ONLY_NO_DELETION',
        'through': through,
        'committed_sequence': committed_sequence,
        'retain_from_session': retain_from_session,
        'verified_records': count,
        'snapshot_sha256': chain.hexdigest(),
        'previous_floor': floor,
        'previous_cutoff': previous_cutoff,
        'prune_through': floor + len(removed),
        'receipt_sha256s': removed,
        'raw_sha256s': sorted(candidate_raw - retained_raw),
    }
    result['plan_sha256'] = hashlib.sha256(canonical(result)).hexdigest()
    return result


def _committed_snapshot(store, *, epoch, release_sha, session=None):
    """Read the verified PostgreSQL state/journal snapshot, never a proposal.

    This is an ACK observation, not permission to delete: maintenance exclusion
    and binding retained evidence to all relevant consumers remain necessary.
    """
    from .r2d2_v2_store import PostgresShadowStore
    _require(isinstance(store, PostgresShadowStore), 'RETENTION_PERSISTENT_STORE_REQUIRED')
    _require(type(release_sha) is str and len(release_sha)==64
             and all(c in '0123456789abcdef' for c in release_sha), 'RETENTION_RELEASE')
    row, records = store.read_with_journal(epoch)
    _require(row is not None, 'RETENTION_EPOCH_MISSING')
    _require(row['state']['release_sha']==release_sha, 'RETENTION_RELEASE_MISMATCH')
    cursor = cast(dict[str, Any], row['state'].get('raw_source_cursor'))
    _require(type(cursor) is dict, 'RETENTION_CURSOR_MISSING')
    if set(cursor) in ({'massive_sequence'}, {'version','epoch','sessions'}):
        massive = cursor
    else:
        _require(type(cursor.get('version')) is int, 'RETENTION_CURSOR_FORMAT')
        if cursor['version']==1:
            _require(set(cursor)=={'version','quote_trade','massive'}, 'RETENTION_CURSOR_FORMAT')
        else:
            _require(cursor['version'] in (2,3) and set(cursor)=={'version','quote_trade','massive','barrier'},
                     'RETENTION_CURSOR_FORMAT')
            from .r2d2_v2_composite_source import CompositeEventSource
            _require(len(canonical(cursor))<=2_000_000, 'RETENTION_CURSOR_LIMIT')
            raw: dict[str, Any] = cursor['quote_trade']
            _require(type(raw) is dict and set(raw)<={'files'}
                     and type(raw.get('files',{})) is dict and len(raw.get('files',{}))<=4096,
                     'RETENTION_CURSOR_FORMAT')
            for name, saved_value in raw.get('files',{}).items():
                saved = cast(dict[str, Any], saved_value)
                _require(type(name) is str and type(saved) is dict
                         and set(saved) in ({'offset','sequence','device','inode','witness'},
                                            {'offset','sequence','device','inode','witness','received_max'})
                         and all(type(saved[k]) is int and saved[k]>=0
                                 for k in ('offset','sequence','device','inode'))
                         and type(saved['witness']) is str
                         and re.fullmatch(r'[0-9a-f]{64}',saved['witness']) is not None,
                         'RETENTION_CURSOR_FORMAT')
                if saved.get('received_max') is not None:_time(saved['received_max'])
            barrier: dict[str, Any] = cursor['barrier']
            fields={'resolved','sequence'} | ({'pending_raw','read_cursor','scope_sequences'} if cursor['version']==3 else set())
            _require(type(barrier) is dict and (set(barrier)==fields or cursor['version']==3 and set(barrier)==fields|{'file_bases'})
                     and type(barrier['sequence']) is int and barrier['sequence']>=0
                     and type(barrier['resolved']) is dict
                     and len(barrier['resolved'])<=CompositeEventSource.MAX_PROOFS,
                     'RETENTION_BARRIER_FORMAT')
            if cursor['version']==3:
                CompositeEventSource._validate_scoped(barrier,retained=raw)
            for key, proof_value in barrier['resolved'].items():
                proof = cast(dict[str, Any], proof_value)
                _require(type(key) is str and len(key)<=200 and type(proof) is dict
                         and set(proof)=={'end_at','event_id','envelope_sha256'}, 'RETENTION_BARRIER_PROOF')
                parts=cast(str, key).split('|')
                _require(len(parts)==3 and re.fullmatch(r'US:[A-Z0-9._-]+',parts[0]) is not None
                         and _time(parts[2]).astimezone(ZoneInfo('America/New_York')).date().isoformat()==parts[1]
                         and _time(proof['end_at'])-_time(parts[2])==timedelta(minutes=1)
                         and type(proof['event_id']) is str and 0<len(proof['event_id'])<=256
                         and type(proof['envelope_sha256']) is str
                         and re.fullmatch(r'[0-9a-f]{64}',proof['envelope_sha256']) is not None,
                         'RETENTION_BARRIER_PROOF')
        massive = cursor['massive']
    _require(type(massive) is dict, 'RETENTION_CURSOR_FORMAT')
    if set(massive)=={'massive_sequence'}:
        _require(session is None, 'RETENTION_LEGACY_SESSION_UNBOUND')
        sequence = massive['massive_sequence']
        _require(type(sequence) is int and sequence>=0, 'RETENTION_ACK')
        position: dict[str, Any] = {'committed_sequence':sequence}
    else:
        _require(set(massive)=={'version','epoch','sessions'} and type(massive['version']) is int
                 and massive['version']==2 and massive['epoch']==epoch
                 and type(massive['sessions']) is dict and len(massive['sessions'])<=MAX_SESSIONS,
                 'RETENTION_SESSION_CURSOR')
        for day, sequence in massive['sessions'].items():
            _require(type(day) is str and date.fromisoformat(day).isoformat()==day
                     and type(sequence) is int and sequence>=0, 'RETENTION_SESSION_ACK')
        position={'committed_sessions':dict(massive['sessions'])}
        if session is not None:
            _require(type(session) is str and date.fromisoformat(session).isoformat()==session
                     and session in massive['sessions'], 'RETENTION_SESSION_ACK_MISSING')
            position.update(session=session, committed_sequence=massive['sessions'][session])
    cursor_sha = hashlib.sha256(canonical(cursor)).hexdigest()
    matching = [r for r in records if r['payload'].get('type')=='SOURCE_CURSOR'
                and r['payload'].get('cursor')==cursor
                and r['payload'].get('cursor_sha256')==cursor_sha]
    _require(bool(matching), 'RETENTION_ACK_JOURNAL_MISSING')
    return {'status':'VERIFIED_ACK_OBSERVATION_NOT_DELETION_AUTHORITY',
            'epoch':epoch,'release_sha':release_sha,**position,
            'state_sha256':row['state_sha'],'journal_head':row['journal_head'],
            'cursor_sha256':cursor_sha,'ack_record_sha256':matching[-1]['record_sha']}, records


def read_committed_ack(store, *, epoch, release_sha, session=None):
    return _committed_snapshot(store, epoch=epoch, release_sha=release_sha, session=session)[0]


def plan_committed_retention(journal, store, *, epoch, release_sha, now,
                             retain_from_session, max_records=500000, session=None):
    with journal_access(journal.path.parent):
        return _plan_committed_retention_locked(
            journal, store, epoch=epoch, release_sha=release_sha, now=now,
            retain_from_session=retain_from_session, max_records=max_records, session=session)


def _plan_committed_retention_locked(journal, store, *, epoch, release_sha, now,
                                     retain_from_session, max_records=500000, session=None):
    """Bind the local retained prefix to one verified consumer snapshot.

    No deletion: coverage of any other consumer and maintenance exclusion must
    be established separately. An equal numeric cursor alone is insufficient.
    """
    from .r2d2_v2_massive_events import journal_envelope
    ack, records = _committed_snapshot(store, epoch=epoch, release_sha=release_sha, session=session)
    _require('committed_sequence' in ack, 'RETENTION_SESSION_REQUIRED')
    _require(len(records)<=max_records, 'RETENTION_ACK_RECORD_LIMIT')
    committed = {}
    for record in records:
        payload = record['payload']
        if payload.get('type')!='SOURCE_CURSOR': continue
        receipts = payload.get('raw_receipts', {})
        _require(type(receipts) is dict, 'RETENTION_ACK_RECEIPTS')
        for identity, digest in receipts.items():
            _require(identity not in committed or committed[identity]==digest,
                     'RETENTION_ACK_RECEIPT_CONFLICT')
            committed[identity]=digest
            _require(len(committed)<=max_records,'RETENTION_ACK_RECEIPT_LIMIT')
    plan = _plan_retention_locked(journal, committed_sequence=ack['committed_sequence'],
                          retain_from_session=retain_from_session,max_records=max_records,journal_session=session)
    after = plan['previous_floor']
    verified = 0
    while after < ack['committed_sequence']:
        page = journal._page_locked(after, through=ack['committed_sequence'], limit=1024)
        for record in page['records']:
            if session is None:
                envelope = journal_envelope(record, now)
            else:
                from .r2d2_v2_massive_events import session_envelope
                _require(record['receipt']['event']['session']==session, 'RETENTION_JOURNAL_SESSION_MISMATCH')
                envelope = session_envelope(record, now, epoch=epoch, session=session)
            digest = hashlib.sha256(canonical(envelope)).hexdigest()
            _require(committed.get(envelope['event_id'])==digest,'RETENTION_LOCAL_ACK_MISMATCH')
            verified += 1
        _require(page['after']>after,'RETENTION_ACK_PROGRESS')
        after = page['after']
    _require(journal._page_locked(plan['through'],limit=1)['through']==plan['through'],
             'RETENTION_SNAPSHOT_CHANGED')
    result={**plan,'ack':ack,'verified_committed_receipts':verified,
            'status':'ONE_CONSUMER_BOUND_REVIEW_ONLY_NO_DELETION'}
    result.pop('plan_sha256')
    result['plan_sha256']=hashlib.sha256(canonical(result)).hexdigest()
    return result


def plan_consumers_retention(journal, consumers, *, required_consumers, now,
                             retain_from_session, max_records=500000, session=None):
    """Bind every explicitly required consumer; inventory authority is external.

    Each descriptor contains a persistent store, epoch and release SHA. The
    lowest verified ACK limits pruning. This remains a plan, never deletion.
    """
    _require(type(required_consumers) in (list, tuple) and bool(required_consumers)
             and all(type(name) is str and bool(name) for name in required_consumers)
             and len(set(required_consumers)) == len(required_consumers),
             'RETENTION_CONSUMER_INVENTORY')
    _require(type(consumers) is dict and set(consumers) == set(required_consumers),
             'RETENTION_CONSUMER_COVERAGE')
    with journal_access(journal.path.parent):
        plans = {}
        for name in sorted(consumers):
            descriptor = cast(dict[str, Any], consumers[name])
            _require(type(descriptor) is dict and set(descriptor) == {'store', 'epoch', 'release_sha'},
                     'RETENTION_CONSUMER_DESCRIPTOR')
            plans[name] = _plan_committed_retention_locked(
                journal, descriptor['store'], epoch=descriptor['epoch'],
                release_sha=descriptor['release_sha'], now=now,
                retain_from_session=retain_from_session, max_records=max_records, session=session)
        first = next(iter(plans.values()))
        for plan in plans.values():
            _require(all(plan[key] == first[key] for key in
                         ('through', 'previous_floor', 'previous_cutoff', 'snapshot_sha256')),
                     'RETENTION_CONSUMER_SNAPSHOT_CHANGED')
        minimum = min(plan['committed_sequence'] for plan in plans.values())
        result = _plan_retention_locked(journal, committed_sequence=minimum,
            retain_from_session=retain_from_session, max_records=max_records, journal_session=session)
        _require(all(result[key] == first[key] for key in
                     ('through', 'previous_floor', 'previous_cutoff', 'snapshot_sha256')),
                 'RETENTION_CONSUMER_SNAPSHOT_CHANGED')
        result.pop('plan_sha256')
        result.update(status='EXPLICIT_CONSUMERS_BOUND_REVIEW_ONLY_NO_DELETION',
                      consumer_acks={name: plan['ack'] for name, plan in plans.items()},
                      consumer_inventory_authority_verified=False)
        result['plan_sha256'] = hashlib.sha256(canonical(result)).hexdigest()
        return result
