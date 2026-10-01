"""Epoch identity constants against the real XNYS calendar; offline, no authority."""
from datetime import date

import pytest

from app import r2d2_v2_live_controller as live
from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_epoch_assembler import (DOCUMENT_ORDER_SHA, EPOCH, FIRST_SESSION, REQUIRED_BINDINGS,
                                         RUNTIME_ORDER_SHA, SESSIONS, Refused, is_sha, plan, validate_identity)

IDENTITY = {'epoch': EPOCH, 'namespace': EPOCH, 'first_session': FIRST_SESSION, 'authorized_sessions': list(SESSIONS),
            'document_order_sha': DOCUMENT_ORDER_SHA, 'runtime_order_sha': RUNTIME_ORDER_SHA}
UNBOUND = {name: None for name in REQUIRED_BINDINGS}


def refusal(call):
    with pytest.raises(Refused) as error:
        call()
    return str(error.value)


def test_epoch_is_the_five_certified_sessions_from_its_first_session():
    calendar = ShadowCalendar()
    assert EPOCH == 'R2D2-V2-SHADOW-' + FIRST_SESSION == 'R2D2-V2-SHADOW-2026-10-05'
    assert SESSIONS == ('2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09')
    assert tuple(d.isoformat() for d in calendar.sessions(date.fromisoformat(FIRST_SESSION), 5)) == SESSIONS
    assert [validate_identity(dict(IDENTITY), day, calendar)['day'] for day in SESSIONS] == list(SESSIONS)
    assert validate_identity(dict(IDENTITY), FIRST_SESSION, calendar)['previous_session'] == '2026-10-02'


def test_abandoned_epoch_and_adjacent_sessions_are_refused():
    calendar = ShadowCalendar()
    for day in ('2026-10-02', '2026-10-12'):
        assert calendar.is_session(date.fromisoformat(day))
        assert refusal(lambda: validate_identity(dict(IDENTITY), day, calendar)) == 'DAY_NOT_AUTHORIZED'
    old = 'R2D2-V2-SHADOW-2026-10-02'
    assert refusal(lambda: validate_identity({**IDENTITY, 'epoch': old, 'namespace': old}, FIRST_SESSION, calendar)) == 'EPOCH_IDENTITY'
    assert refusal(lambda: validate_identity({**IDENTITY, 'first_session': '2026-10-02'}, FIRST_SESSION, calendar)) == 'EPOCH_IDENTITY'
    stale = ['2026-10-02', *SESSIONS[:-1]]
    assert refusal(lambda: validate_identity({**IDENTITY, 'authorized_sessions': stale}, FIRST_SESSION, calendar)) == 'AUTHORIZED_SESSIONS'


def test_runtime_order_is_the_controller_order_and_document_order_is_a_digest():
    assert RUNTIME_ORDER_SHA == live.ORDER_SHA
    assert is_sha(DOCUMENT_ORDER_SHA) and DOCUMENT_ORDER_SHA != RUNTIME_ORDER_SHA


@pytest.mark.parametrize('phase', ['install_release', 'readback', 'activate'])
def test_first_session_phases_are_refused_on_later_sessions(phase):
    calendar = ShadowCalendar()
    first = plan(dict(IDENTITY), day=FIRST_SESSION, phase=phase, bindings=dict(UNBOUND), policy=None, calendar=calendar)
    assert first['status'] == 'UNBOUND' and first['execution_authorized'] is False
    assert first['proposal']['authority_mode'] == 'INDIVIDUAL_ONLY'
    for day in SESSIONS[1:]:
        assert refusal(lambda: plan(dict(IDENTITY), day=day, phase=phase, bindings=dict(UNBOUND),
                                    policy=None, calendar=calendar)) == 'FIRST_SESSION_PHASE_ONLY'
