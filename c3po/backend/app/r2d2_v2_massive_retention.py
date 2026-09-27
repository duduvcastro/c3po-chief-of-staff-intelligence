"""Verified retention planning only; never unlinks or changes a journal.

Execution requires a separate exclusive producer/consumer maintenance boundary
and a durable collector acknowledgement. A proposed cursor is not an ACK.
"""
import hashlib
from datetime import date
from .r2d2_v2_sources import canonical, _require


def plan_retention(journal, *, committed_sequence, retain_from_session, max_records=500000):
    _require(type(committed_sequence) is int and committed_sequence >= 0, 'RETENTION_ACK')
    _require(type(max_records) is int and 0 < max_records <= 500000, 'RETENTION_LIMIT')
    _require(isinstance(retain_from_session, str), 'RETENTION_SESSION')
    try:
        cutoff = date.fromisoformat(retain_from_session)
    except ValueError:
        raise ValueError('RETENTION_SESSION') from None
    _require(cutoff.isoformat() == retain_from_session, 'RETENTION_SESSION')
    floor = journal.retention_floor()
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
        page = journal.page(after, through=through, limit=1024)
        through = page['through']
        _require(committed_sequence <= through, 'RETENTION_ACK_AHEAD')
        for record in page['records']:
            count += 1
            _require(count <= max_records, 'RETENTION_LIMIT')
            receipt = record['receipt']
            session = receipt['event']['session']
            parsed = date.fromisoformat(session)
            _require(parsed.isoformat() == session, 'RETENTION_SESSION')
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
    latest = journal.page(through, limit=1)
    _require(latest['through'] == through, 'RETENTION_SNAPSHOT_CHANGED')
    result = {
        'status': 'REVIEW_ONLY_NO_DELETION',
        'through': through,
        'committed_sequence': committed_sequence,
        'retain_from_session': retain_from_session,
        'verified_records': count,
        'snapshot_sha256': chain.hexdigest(),
        'previous_floor': floor,
        'prune_through': floor + len(removed),
        'receipt_sha256s': removed,
        'raw_sha256s': sorted(candidate_raw - retained_raw),
    }
    result['plan_sha256'] = hashlib.sha256(canonical(result)).hexdigest()
    return result


def _committed_snapshot(store, *, epoch, release_sha):
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
    cursor = row['state'].get('raw_source_cursor')
    _require(type(cursor) is dict, 'RETENTION_CURSOR_MISSING')
    if set(cursor)=={'massive_sequence'}:
        massive = cursor
    else:
        _require(set(cursor)=={'version','quote_trade','massive'} and type(cursor['version']) is int
                 and cursor['version']==1, 'RETENTION_CURSOR_FORMAT')
        massive = cursor['massive']
    _require(type(massive) is dict and set(massive)=={'massive_sequence'}, 'RETENTION_CURSOR_FORMAT')
    sequence = massive['massive_sequence']
    _require(type(sequence) is int and sequence>=0, 'RETENTION_ACK')
    cursor_sha = hashlib.sha256(canonical(cursor)).hexdigest()
    matching = [r for r in records if r['payload'].get('type')=='SOURCE_CURSOR'
                and r['payload'].get('cursor')==cursor
                and r['payload'].get('cursor_sha256')==cursor_sha]
    _require(bool(matching), 'RETENTION_ACK_JOURNAL_MISSING')
    return {'status':'VERIFIED_ACK_OBSERVATION_NOT_DELETION_AUTHORITY',
            'epoch':epoch,'release_sha':release_sha,'committed_sequence':sequence,
            'state_sha256':row['state_sha'],'journal_head':row['journal_head'],
            'cursor_sha256':cursor_sha,'ack_record_sha256':matching[-1]['record_sha']}, records


def read_committed_ack(store, *, epoch, release_sha):
    return _committed_snapshot(store, epoch=epoch, release_sha=release_sha)[0]


def plan_committed_retention(journal, store, *, epoch, release_sha, now,
                             retain_from_session, max_records=500000):
    """Bind the local retained prefix to one verified consumer snapshot.

    No deletion: coverage of any other consumer and maintenance exclusion must
    be established separately. An equal numeric cursor alone is insufficient.
    """
    from .r2d2_v2_massive_events import journal_envelope
    ack, records = _committed_snapshot(store, epoch=epoch, release_sha=release_sha)
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
    plan = plan_retention(journal, committed_sequence=ack['committed_sequence'],
                          retain_from_session=retain_from_session,max_records=max_records)
    after = plan['previous_floor']
    verified = 0
    while after < ack['committed_sequence']:
        page = journal.page(after, through=ack['committed_sequence'], limit=1024)
        for record in page['records']:
            envelope = journal_envelope(record, now)
            digest = hashlib.sha256(canonical(envelope)).hexdigest()
            _require(committed.get(envelope['event_id'])==digest,'RETENTION_LOCAL_ACK_MISMATCH')
            verified += 1
        _require(page['after']>after,'RETENTION_ACK_PROGRESS')
        after = page['after']
    _require(journal.page(plan['through'],limit=1)['through']==plan['through'],
             'RETENTION_SNAPSHOT_CHANGED')
    result={**plan,'ack':ack,'verified_committed_receipts':verified,
            'status':'ONE_CONSUMER_BOUND_REVIEW_ONLY_NO_DELETION'}
    result.pop('plan_sha256')
    result['plan_sha256']=hashlib.sha256(canonical(result)).hexdigest()
    return result
