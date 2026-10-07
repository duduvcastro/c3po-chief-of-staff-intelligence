"""Dated single-job orchestration policy. An adapter must prove, not assert, gates.

No live adapter is hidden in this policy. The offline proof exercises scheduling,
identity, immutable signed bytes and refusal paths. It cannot grant authority or
stand in for the separate integrated/Linux/runtime/operator proof.
"""
import datetime as dt
import hashlib
import json
import re

SESSION = '2026-10-08'
OPERATIONS = ('policy_read', 'capture_launch', 'capture_result', 'capture_cleanup')
WINDOWS = {
    'policy_read': ('2026-10-08T12:26:00Z', '2026-10-08T12:34:59Z'),
    'capture_launch': ('2026-10-08T13:50:00Z', '2026-10-08T13:59:59Z'),
    'capture_result': ('2026-10-08T14:26:00Z', '2026-10-08T14:35:59Z'),
    'capture_cleanup': ('2026-10-08T14:29:00Z', '2026-10-08T14:34:59Z'),
}
LATEST = {k: (dt.datetime.fromisoformat(v[1].replace('Z', '+00:00')) - dt.timedelta(seconds=80)).strftime('%Y-%m-%dT%H:%M:%SZ') for k, v in WINDOWS.items()}

class Refused(ValueError):
    pass

def need(ok, code):
    if not ok:
        raise Refused(code)

def instant(text):
    need(type(text) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', text), 'FLOW_UTC')
    return dt.datetime.fromisoformat(text.replace('Z', '+00:00'))

def pin(text):
    need(type(text) is str and re.fullmatch('[0-9a-f]{64}', text) and text != '0' * 64, 'FLOW_PIN')
    return text

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def job(value):
    need(value.get('session') == SESSION and type(value.get('run_id')) is str
         and re.fullmatch('[1-9][0-9]{5,19}', value['run_id']) and type(value.get('run_attempt')) is int
         and value['run_attempt'] == 1 and type(value.get('nonce')) is str
         and re.fullmatch('[0-9a-f]{32}', value['nonce']), 'FLOW_JOB')
    return {k: value[k] for k in ('session', 'run_id', 'run_attempt', 'nonce')}

def verified_gate(gate, operation, slot, identity):
    """Input is the adapter's re-derived status + signed REQUEST, never raw stdout."""
    need(slot in ('PRIMARY', 'SPARE'), 'FLOW_TRACK')
    need(gate.get('verified') is True and gate.get('status') == 'KNOWN_COMPLETE'
         and gate.get('outcome') and gate['outcome'] == gate.get('success_criterion')
         and gate.get('day') == SESSION and gate.get('grid') == 'G19'
         and gate.get('k9_operation') == operation and gate.get('slot') == slot
         and gate.get('host_binding_sha256') == identity, 'FLOW_PREREQUISITE_NOT_COMPLETE')
    for key in ('request_sha256', 'payload_sha256', 'receipt_sha256'):
        pin(gate.get(key))

def sheet(value, operation, current):
    need(job(value) == current and value.get('operation') == operation and value.get('signature_model') == 'PRE'
         and value.get('slot') == 'PRIMARY' and value.get('signed') is True
         and value.get('own_owner_record_verified') is True and value.get('bound_review_verified') is True,
         'FLOW_SHEET_NOT_OWN_SIGNED_REVIEWED')
    need(value.get('not_before') == WINDOWS[operation][0] and value.get('not_after') == WINDOWS[operation][1], 'FLOW_WINDOW_CHANGED')
    need(instant('2026-10-08T11:50:00Z') <= instant(value['answered_at_utc']) <= instant('2026-10-08T12:30:00Z')
         and instant(value['observed_at_utc']) <= instant('2026-10-08T12:30:00Z'), 'FLOW_OWNER_BAND')
    need(value['answered_at_utc'] <= value['observed_at_utc'], 'FLOW_OWNER_ORDER')
    for key in ('sheet_sha256', 'request_sha256', 'payload_sha256', 'config_sha256', 'owner_packet_sha256'):
        pin(value.get(key))
    return dict(value)

def run(adapter):
    """One logical run, no restart/retry. Every side effect belongs to the adapter.

    The adapter must authenticate dated authority, physical runtime and same job
    before each operation, run the guarded binder's real checks, publish/read back
    exact intent, invoke the sealed dispatcher once and re-derive stored status.
    Until that adapter is delivered and independently proved, this is a component.
    """
    current = job(adapter.identity())
    adapter.verify_authority_runtime(current)
    adapter.wait_until('2026-10-08T11:45:00Z')
    need(adapter.now() < instant('2026-10-08T11:52:00Z'), 'FLOW_CHALLENGE_PREPARE_MISSED')
    transport = adapter.challenge(current)
    need(job(transport) == current and transport.get('verified') is True
         and transport.get('status') == 'KNOWN_COMPLETE' and transport.get('remote_uid') == 0
         and transport.get('attempts') == 1 and transport.get('retry') is False
         and transport.get('remote_command') == 'sudo -n /usr/bin/python3 -I -B -'
         and transport.get('no_host_file_access') is True, 'FLOW_TRANSPORT_NOT_PROVEN')
    pin(transport['config_sha256']); pin(transport['receipt_sha256'])
    frozen = {}
    for op in OPERATIONS:
        adapter.verify_authority_runtime(current)
        need(adapter.now() <= instant('2026-10-08T12:30:00Z'), 'FLOW_OWNER_DEADLINE_MISSED')
        frozen[op] = sheet(adapter.prepare_sign_review(op, current, transport), op, current)
    need(adapter.now() <= instant('2026-10-08T12:30:00Z'), 'FLOW_ALL_SHEETS_MISSED')
    completed = {}
    for op in OPERATIONS:
        adapter.wait_until(WINDOWS[op][0])
        need(adapter.now() <= instant(LATEST[op]), 'FLOW_LATEST_START_MISSED')
        adapter.verify_authority_runtime(current)
        need(adapter.snapshot(op) == frozen[op], 'FLOW_SIGNED_FIELDS_CHANGED')
        if op == 'capture_launch':
            branch = adapter.night_branch()
            need(branch in ('PRIMARY', 'SPARE'), 'FLOW_NO_REAL_NIGHT_BRANCH')
            for gate_op in ('commit_result', 'publish_launch'):
                verified_gate(adapter.prerequisite(gate_op, branch), gate_op, branch, frozen[op]['host_binding_sha256'])
            need('policy_read' in completed, 'FLOW_POLICY_NOT_COMPLETE')
        elif op in ('capture_result', 'capture_cleanup'):
            need('capture_launch' in completed, 'FLOW_CAPTURE_LAUNCH_NOT_COMPLETE')
        adapter.check(op, 'prepare')
        publication = adapter.prepare_publish(op)
        need(type(publication.get('comment_id')) is int and publication['comment_id'] > 0
             and publication.get('readback_exact') is True and publication.get('attempts') == 1,
             'FLOW_PUBLICATION_NOT_VERIFIED')
        published = instant(publication['created_at'])
        need(published <= adapter.now(), 'FLOW_PUBLICATION_FUTURE')
        adapter.wait_until((published + dt.timedelta(seconds=120)).strftime('%Y-%m-%dT%H:%M:%SZ'))
        need(adapter.now() <= instant(LATEST[op]), 'FLOW_PUBLICATION_DELAY_MISSED')
        adapter.verify_authority_runtime(current)
        need(adapter.snapshot(op) == frozen[op], 'FLOW_SIGNED_FIELDS_CHANGED')
        if op == 'capture_launch':
            for gate_op in ('commit_result', 'publish_launch'):
                verified_gate(adapter.prerequisite(gate_op, branch), gate_op, branch, frozen[op]['host_binding_sha256'])
        adapter.check(op, 'resume')
        adapter.resume_once(op)
        result = adapter.status(op)
        need(result.get('verified') is True and result.get('status') == 'KNOWN_COMPLETE'
             and result.get('outcome') and result['outcome'] == result.get('success_criterion')
             and result.get('config_sha256') == frozen[op]['config_sha256'], 'FLOW_RESULT_INCOMPLETE_OR_UNCERTAIN')
        completed[op] = result
    return {'status': 'FLOW_COMPLETE', 'session': SESSION, 'completed': list(completed), 'attempts': 1,
            'no_retry': True, 'operational_READY': False}
