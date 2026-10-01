"""Act B per-day contract template binding; synthetic offline documents only."""
import hashlib
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_capacity_authority import calendar_pin, validate_contract
from app.r2d2_v2_document_authority import DocumentAuthority
from app.r2d2_v2_document_format import BEGIN, END, SCHEMA, normalize_document
from app.r2d2_v2_epoch_assembler import (DOCUMENT_ORDER_SHA, EPOCH, FIRST_SESSION, RUNTIME_ORDER_SHA, SESSIONS,
                                         canonical, digest, plan)
from app.r2d2_v2_store import ShadowIntegrityError, digest as store_digest

NOW = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
OWNER = 'a' * 64
RULE = 'OPEN_FIRST_THEN_EXISTING_CAUSAL_ORDER_V1_PROPOSED'
PHASES = ['admission', 'bar_manifest', 'quote_refresh', 'quote_capture']
ORDER = {'owner_sha': OWNER, 'epoch': EPOCH, 'authorized_sessions': list(SESSIONS), 'capacity': 550}
POLICY = {'schema': 'R2D2_V2_LIVE_POLICY_V1', 'mode': 'LIVE', 'epoch': EPOCH, 'capacity': 550,
          'order_sha': RUNTIME_ORDER_SHA, 'release_sha': '1' * 64, 'package_sha': '2' * 64, 'code_revision': 'c' * 40,
          'c8_receipt_sha': '3' * 64, 'head_go_sha': '4' * 64,
          'valid_from': '2026-10-05T13:00:00+00:00', 'valid_until': '2026-10-09T21:00:00+00:00'}
OUTSIDE = ('2026-10-02', '2026-10-12')  # XNYS sessions adjacent to the epoch, never authorized by it


def template(day):
    return {'owner_sha': OWNER, 'epoch': EPOCH, 'day': day, 'phases': PHASES, 'rule': RULE}


def entry(day):
    return {'sha': digest(template(day)), 'epoch': EPOCH, 'first_session': FIRST_SESSION,
            'authorized_sessions': [day], 'phases': PHASES}


def document(kind, body):
    payload = canonical({'schema': SCHEMA, 'kind': kind, 'state': 'ISSUED', 'body': body}).decode()
    return f'# {kind}\n{BEGIN}\n```json\n{payload}\n```\n{END}\n'.encode()


class Root:
    def __init__(self):
        self.files = {}

    def read(self, name):
        return self.files[name]


def scope(days):
    return {'epoch': EPOCH, 'first_session': FIRST_SESSION, 'authorized_sessions': list(days)}


def build(days=SESSIONS, *, act_overrides=None, templates=None):
    root, pins = Root(), {}

    def put(label, raw):
        name = label.lower() + '.md'
        root.files[name] = raw
        pins[label] = {'file': name, 'sha256': hashlib.sha256(raw).hexdigest()}

    previous = None
    for role in ('CODEX', 'FABLE', 'DUDU'):
        body = {'role': role, 'decision': 'APPROVED', 'previous_sha': previous,
                'document_sha256': DOCUMENT_ORDER_SHA, **scope(days)}
        if role == 'DUDU':
            body['owner_evidence'] = {'verbatim': 'Assino a ordem.', 'channel': 'synthetic',
                                      'signed_at_utc': '2026-10-01T11:00:00+00:00'}
        put(role, document('APPROVAL', body))
        previous = pins[role]['sha256']
    templates = [entry(day) for day in days] if templates is None else templates
    act = {'status': 'ACCEPTED', 'chain_head': pins['DUDU']['sha256'], 'order_sha': digest(ORDER),
           'template_shas': {day: digest(template(day)) for day in days}, 'policy_sha': digest(POLICY),
           'capacity': 550, 'cut_rule': RULE, 'subphases': {}, 'individual_go_issuers': ['FABLE'],
           'owner_countersign_phases': ['bar_merge_deploy_recertify', 'install_release', 'activate', 'wind_down_28'],
           'rollback_disposition': 'REVALIDATE_UNCOMMITTED_ONLY', **scope(days),
           'causal_order': {'primary': 'ADV_DESC', 'tie_break': 'SYMBOL_ASC', 'cut': 'TAIL_NEW_ONLY'},
           'policy_epoch_validity': True, 'automatic_retry': False, 'document_order_sha': DOCUMENT_ORDER_SHA,
           'act_a_scope_map': {role: {'signature_sha': pins[role]['sha256'], 'document_sha256': DOCUMENT_ORDER_SHA,
                                      **scope(days)} for role in ('CODEX', 'FABLE', 'DUDU')},
           'templates': templates, 'template_set_sha': digest(templates)}
    for key, value in (act_overrides or {}).items():
        if value is None:
            act.pop(key, None)
        else:
            act[key] = value
    put('ACT_B', document('ACT_B', act))
    previous = None
    for role in ('CODEX', 'FABLE', 'DUDU'):
        body = {'role': role, 'decision': 'APPROVED', 'previous_sha': previous, **scope(days),
                'body_sha': pins['ACT_B']['sha256'], 'act_a_head': pins['DUDU']['sha256']}
        if role == 'DUDU':
            body['owner_evidence'] = {'verbatim': 'Assino o ato B', 'channel': 'synthetic',
                                      'signed_at_utc': '2026-10-01T11:30:00+00:00'}
        put('B_' + role, document('APPROVAL', body))
        previous = pins['B_' + role]['sha256']
    return DocumentAuthority(root=root, pins=pins), root, pins


def binding(day, template_day=None):
    return {'epoch': EPOCH, 'day': day,
            'contract': {'assembler_plan': {'proposal': {'identity': {'first_session': FIRST_SESSION}}},
                         'order': ORDER, 'policy': POLICY, 'template': template(template_day or day)}}


def act_b_code(authority):
    with pytest.raises(ShadowIntegrityError) as error:
        authority.act_b(NOW, day=FIRST_SESSION)
    return str(error.value)


def test_five_day_act_b_binds_each_days_own_contract_template():
    authority, _, _ = build()
    assert len({digest(template(day)) for day in SESSIONS}) == len(SESSIONS)
    for day in SESSIONS:
        assert authority.act_b(NOW, day=day)['template_shas'][day] == digest(template(day))
        assert authority.verify_binding(binding(day), NOW) is True


def test_wrong_day_template_is_refused():
    authority, _, _ = build()
    for day in SESSIONS:
        for other in SESSIONS:
            if other != day:
                assert authority.verify_binding(binding(day, other), NOW) is False


def test_day_outside_the_epoch_is_refused():
    authority, _, _ = build()
    assert not set(OUTSIDE) & set(SESSIONS)
    for day in OUTSIDE:
        assert authority.verify_binding(binding(day), NOW) is False


@pytest.mark.parametrize('shas', [
    {day: digest(template(day)) for day in SESSIONS[:-1]},
    {**{day: digest(template(day)) for day in SESSIONS}, OUTSIDE[1]: digest(template(OUTSIDE[1]))},
    {**{day: digest(template(day)) for day in SESSIONS}, SESSIONS[1]: 'B' * 64},
    {**{day: digest(template(day)) for day in SESSIONS}, SESSIONS[1]: digest(template(SESSIONS[2]))},
    [digest(template(day)) for day in SESSIONS],
])
def test_missing_extra_malformed_or_duplicate_map_is_refused(shas):
    authority, root, pins = build(act_overrides={'template_shas': shas})
    with pytest.raises(ShadowIntegrityError, match='ACT_B_TEMPLATE_MAP'):
        normalize_document('ACT_B', root.read(pins['ACT_B']['file']))
    assert all(authority.verify_binding(binding(day), NOW) is False for day in SESSIONS)


@pytest.mark.parametrize('overrides', [
    {'template_sha': None, 'template_shas': None},
    {'template_sha': digest(template(FIRST_SESSION))},
])
def test_exactly_one_template_form_is_required(overrides):
    authority, _, _ = build(act_overrides=overrides)
    assert act_b_code(authority) == 'ACT_B_TEMPLATE_FORM'
    assert all(authority.verify_binding(binding(day), NOW) is False for day in SESSIONS)


def test_single_day_scalar_act_b_still_binds_its_one_day():
    days = (FIRST_SESSION,)
    authority, _, _ = build(days, act_overrides={'template_shas': None, 'template_sha': digest(template(FIRST_SESSION))})
    assert authority.verify_binding(binding(FIRST_SESSION), NOW) is True
    assert authority.verify_binding(binding(FIRST_SESSION, SESSIONS[1]), NOW) is False
    assert authority.verify_binding(binding(SESSIONS[1]), NOW) is False


def test_scalar_act_b_cannot_cover_several_days():
    authority, _, _ = build(act_overrides={'template_shas': None, 'template_sha': digest(template(FIRST_SESSION))})
    assert act_b_code(authority) == 'ACT_B_TEMPLATE_SCALAR'
    assert all(authority.verify_binding(binding(day), NOW) is False for day in SESSIONS)


def test_tampered_act_b_bytes_are_refused_by_the_pin():
    authority, root, pins = build()
    raw = root.read(pins['ACT_B']['file'])
    first, second = digest(template(SESSIONS[1])), digest(template(SESSIONS[2]))
    root.files[pins['ACT_B']['file']] = raw.replace(first.encode(), b'#').replace(second.encode(), first.encode()).replace(b'#', second.encode())
    assert root.read(pins['ACT_B']['file']) != raw
    assert act_b_code(authority) == 'DOCUMENT_HASH_MISMATCH'
    assert all(authority.verify_binding(binding(day), NOW) is False for day in SESSIONS)


def test_repinned_act_b_without_new_b_signatures_is_refused():
    authority, root, pins = build()
    swapped, _, swapped_pins = build(act_overrides={'template_shas': {
        **{day: digest(template(day)) for day in SESSIONS},
        SESSIONS[1]: digest(template(SESSIONS[2])), SESSIONS[2]: digest(template(SESSIONS[1]))}})
    root.files[pins['ACT_B']['file']] = swapped.root.read(swapped_pins['ACT_B']['file'])
    pins['ACT_B'] = swapped_pins['ACT_B']
    assert act_b_code(authority) == 'ACT_B_DOCUMENT_CHAIN'
    assert all(authority.verify_binding(binding(day), NOW) is False for day in SESSIONS)


def test_signed_map_must_agree_with_the_signed_template_set():
    swapped = {**{day: digest(template(day)) for day in SESSIONS},
               SESSIONS[1]: digest(template(SESSIONS[2])), SESSIONS[2]: digest(template(SESSIONS[1]))}
    authority, _, _ = build(act_overrides={'template_shas': swapped})
    assert act_b_code(authority) == 'TEMPLATE_MAP_SET'
    assert authority.verify_binding(binding(SESSIONS[1], SESSIONS[2]), NOW) is False
    assert authority.verify_binding(binding(SESSIONS[0]), NOW) is False
    partial, _, _ = build(templates=[entry(day) for day in SESSIONS[:-1]])
    assert act_b_code(partial) == 'TEMPLATE_MAP_SET'


def code(call):
    with pytest.raises(ShadowIntegrityError) as error:
        call()
    return str(error.value)


def wide(day):
    return {**entry(day), 'authorized_sessions': list(SESSIONS)}


def swapped_map():
    return {**{day: digest(template(day)) for day in SESSIONS},
            SESSIONS[1]: digest(template(SESSIONS[2])), SESSIONS[2]: digest(template(SESSIONS[1]))}


def test_swapped_map_over_wide_entries_is_refused():
    authority, _, _ = build(act_overrides={'template_shas': swapped_map()}, templates=[wide(day) for day in SESSIONS])
    assert act_b_code(authority) == 'TEMPLATE_MAP_SET'
    assert authority.verify_binding(binding(SESSIONS[2], SESSIONS[1]), NOW) is False
    assert all(authority.verify_binding(binding(day), NOW) is False for day in SESSIONS)
    honest, _, _ = build(templates=[wide(day) for day in SESSIONS])
    assert act_b_code(honest) == 'TEMPLATE_MAP_SET'
    mixed, _, _ = build(templates=[entry(day) for day in SESSIONS] + [wide(SESSIONS[1])])
    assert act_b_code(mixed) == 'TEMPLATE_MAP_SET'


def test_template_day_must_equal_the_document_day():
    first, second = SESSIONS[1], SESSIONS[2]
    shas = swapped_map()
    authority, _, _ = build(act_overrides={'template_shas': shas},
                            templates=[{**entry(day), 'sha': shas[day]} for day in SESSIONS])
    assert authority.act_b(NOW, day=first)['template_shas'][first] == digest(template(second))
    assert code(lambda: authority.check_binding(binding(first, second), NOW)) == 'DOCUMENT_TEMPLATE_DAY'
    assert authority.verify_binding(binding(first, second), NOW) is False
    assert code(lambda: authority.check_binding(binding(first), NOW)) == 'DOCUMENT_BINDING'
    assert authority.verify_binding(binding(SESSIONS[0]), NOW) is True


def test_unsorted_days_are_refused():
    days = (SESSIONS[1], SESSIONS[0], *SESSIONS[2:])
    authority, _, _ = build(days)
    assert act_b_code(authority) == 'DOCUMENT_SESSION_SCOPE'
    assert all(authority.verify_binding(binding(day), NOW) is False for day in SESSIONS)


@pytest.mark.parametrize('odd_character', ['\u00c9', '\x7f'])
def test_template_outside_the_shared_digest_namespace_is_refused_with_its_own_code(odd_character):
    day, rule = SESSIONS[0], RULE + odd_character
    odd = {**template(day), 'rule': rule}
    assert digest(odd) != store_digest(odd) and digest(template(day)) == store_digest(template(day))
    assert canonical(odd).isascii() is (odd_character == '\x7f')
    shas = {**{d: digest(template(d)) for d in SESSIONS}, day: digest(odd)}
    authority, _, _ = build(act_overrides={'template_shas': shas, 'cut_rule': rule},
                            templates=[{**entry(d), 'sha': shas[d]} for d in SESSIONS])
    assert authority.act_b(NOW, day=day)['template_shas'][day] == digest(odd)
    document = binding(day)
    document['contract']['template'] = odd
    assert code(lambda: authority.check_binding(document, NOW)) == 'DOCUMENT_BINDING_DIGEST_NAMESPACE'
    assert authority.verify_binding(document, NOW) is False


@pytest.mark.parametrize('odd_owner', ['\u00e9' * 64, 'a' * 63 + '\x7f', '\ud800'])
def test_order_outside_the_shared_digest_namespace_is_refused_with_its_own_code(odd_owner):
    authority, _, _ = build()
    document = binding(SESSIONS[0])
    document['contract']['order'] = {**ORDER, 'owner_sha': odd_owner}
    assert code(lambda: authority.check_binding(document, NOW)) == 'DOCUMENT_BINDING_DIGEST_NAMESPACE'
    assert authority.verify_binding(document, NOW) is False
    assert authority.verify_binding(binding(SESSIONS[0]), NOW) is True


def arm_go(authority, root, pins, *, day, pinned_day, digest_day):
    """Pin one TEMPLATE entry and one individual admission GO for `day`."""
    sha = digest(template(digest_day))
    go = {'decision': 'GO', 'epoch': EPOCH, 'first_session': FIRST_SESSION, 'day': day, 'phase': 'admission',
          'proposal_sha': '5' * 64, 'signed_order_sha': digest(ORDER), 'template_sha': sha, 'mode': 'INDIVIDUAL',
          'not_before': NOW.isoformat(), 'not_after': (NOW + timedelta(minutes=5)).isoformat(),
          'automatic_retry': False, 'authority_receipts': {}}
    record = {'go_sha': digest(go), 'template_sha': sha, 'decision': 'GO', 'role': 'FABLE', 'epoch': EPOCH,
              'first_session': FIRST_SESSION, 'day': day, 'phase': 'admission'}
    for label, raw in (('TEMPLATE', document('TEMPLATE', entry(pinned_day))), ('GO:admission', document('GO', record))):
        name = label.lower().replace(':', '_') + '.md'
        root.files[name] = raw
        pins[label] = {'file': name, 'sha256': hashlib.sha256(raw).hexdigest()}
    authority.revocation_reader = lambda now: {
        'status': 'VERIFIED', 'observed_at': now.isoformat(), 'valid_until': (now + timedelta(seconds=5)).isoformat(),
        'owner_veto': False, 'revoked_shas': []}
    return go, {'proposal': {'identity': scope(SESSIONS)}}


def test_go_is_accepted_only_with_its_own_days_template_pin():
    for day, other in zip(SESSIONS, SESSIONS[1:] + SESSIONS[:1]):
        authority, root, pins = build()
        go, proposal = arm_go(authority, root, pins, day=day, pinned_day=day, digest_day=day)
        assert authority.verify_go(go, proposal, NOW) is True
        go, proposal = arm_go(authority, root, pins, day=day, pinned_day=other, digest_day=day)
        assert authority.verify_go(go, proposal, NOW) is False
        go, proposal = arm_go(authority, root, pins, day=day, pinned_day=other, digest_day=other)
        assert authority.verify_go(go, proposal, NOW) is False


def contract(day, calendar, template_day=None):
    """A fully bound admission contract for `day`, built with the real assembler."""
    identity = {**scope(SESSIONS), 'namespace': EPOCH, 'document_order_sha': DOCUMENT_ORDER_SHA,
                'runtime_order_sha': RUNTIME_ORDER_SHA}
    chosen = template(template_day or day)
    symbols = ['AAPL', 'MSFT']
    causal = {'epoch': EPOCH, 'session': day, 'commitment_sha256': '9' * 64, 'symbols': symbols,
              'list_sha256': store_digest(symbols)}
    causal_scope = {key: causal[key] for key in ('epoch', 'session', 'commitment_sha256', 'list_sha256')}
    inputs = {'owner_sha': OWNER, 'order': ORDER, 'policy': POLICY, 'template': chosen, 'causal_scope': causal_scope}
    consumer = {'schema': 'CAPACITY_CONSUMER_INPUT_BINDING_V1', 'authority_inputs_sha': store_digest(inputs)}
    bindings = {'signed_epoch_order_sha': store_digest(ORDER), 'release_sha': POLICY['release_sha'],
                'policy_sha': digest(POLICY), 'package_sha': POLICY['package_sha'],
                'calendar_pin_sha': calendar_pin(calendar, identity), 'recertification_receipt_sha': '6' * 64,
                'wind_down_28_receipt_sha': '7' * 64, 'template_sha': store_digest(chosen),
                'input_receipts_sha': '8' * 64, 'phase_window_sha': 'a' * 64}

    def planned(phase, window):
        return plan(identity, day=day, phase=phase, bindings={**bindings, 'phase_window_sha': window},
                    policy=POLICY, calendar=calendar, consumer_binding=consumer)

    body = {**inputs, 'assembler_plan': planned('admission', 'a' * 64),
            'consumer_plans': {phase: planned(phase, window * 64) for phase, window in
                               (('bar_manifest', 'b'), ('quote_refresh', 'd'), ('quote_capture', 'e'))}}
    release = SimpleNamespace(epoch=EPOCH, first_session=date.fromisoformat(FIRST_SESSION), receipt_sha=POLICY['release_sha'])
    return body, {'release': release, 'day': day, 'causal': causal, 'calendar': calendar}


def test_real_contract_validation_binds_the_days_own_template():
    calendar = ShadowCalendar()
    authority, _, _ = build()
    day, other = SESSIONS[2], SESSIONS[3]
    body, arguments = contract(day, calendar)
    assert body['assembler_plan']['status'] == 'BOUND_FOR_REVIEW_ONLY'
    validated = validate_contract(body, **arguments)
    assert validated['template'] == template(day)
    assert authority.verify_binding({'epoch': EPOCH, 'day': day, 'contract': validated}, NOW) is True
    foreign, arguments = contract(day, calendar, template_day=other)
    assert code(lambda: validate_contract(foreign, **arguments)) == 'CAPACITY_AUTHORITY_SCOPE'
    assert authority.verify_binding({'epoch': EPOCH, 'day': day, 'contract': foreign}, NOW) is False
