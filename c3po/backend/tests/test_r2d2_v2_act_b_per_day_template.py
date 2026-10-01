"""Act B per-day contract template binding; synthetic offline documents only."""
import hashlib
from datetime import datetime, timezone

import pytest

from app.r2d2_v2_document_authority import DocumentAuthority
from app.r2d2_v2_document_format import BEGIN, END, SCHEMA, normalize_document
from app.r2d2_v2_epoch_assembler import DOCUMENT_ORDER_SHA, EPOCH, FIRST_SESSION, SESSIONS, canonical, digest
from app.r2d2_v2_store import ShadowIntegrityError

NOW = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
OWNER = 'a' * 64
RULE = 'OPEN_FIRST_THEN_EXISTING_CAUSAL_ORDER_V1_PROPOSED'
PHASES = ['admission', 'bar_manifest', 'quote_refresh', 'quote_capture']
ORDER = {'owner_sha': OWNER, 'epoch': EPOCH, 'authorized_sessions': list(SESSIONS), 'capacity': 550}
POLICY = {'schema': 'R2D2_V2_LIVE_POLICY_V1', 'capacity': 550}


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
    assert authority.verify_binding(binding('2026-10-09'), NOW) is False


@pytest.mark.parametrize('shas', [
    {day: digest(template(day)) for day in SESSIONS[:-1]},
    {**{day: digest(template(day)) for day in SESSIONS}, '2026-10-09': digest(template('2026-10-09'))},
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
