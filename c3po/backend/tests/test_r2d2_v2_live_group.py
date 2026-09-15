from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.r2d2_v2_live_group import plan_live_group
from app.r2d2_v2_store import ShadowIntegrityError, digest
from tests.test_r2d2_v2_shadow_counterexamples import setup_state


def fixture():
    collector, state, _ = setup_state()
    saved = {'state': state, 'state_sha': digest(state)}
    return collector.release, saved


def test_union_includes_both_research_arms_and_portfolio_only_names():
    release, saved = fixture()
    ledger = saved['state']['ledger']
    original = ledger['research']['synthetic-entry']
    ledger['research']['other-arm'] = {**deepcopy(original), 'instrument_key': 'US:OTHER', 'arm': 'INELIGIBLE'}
    ledger['portfolio']['portfolio-only'] = {**deepcopy(original), 'instrument_key': 'US:ONLY'}
    ledger['research']['closed'] = {**deepcopy(original), 'instrument_key': 'US:CLOSED', 'status': 'CLOSED'}
    saved['state_sha'] = digest(saved['state'])
    plan = plan_live_group(saved, release, capacity=550, protected_symbols=['SYNTH', 'LEGACY'])
    assert plan['symbols'] == ['ONLY', 'OTHER', 'SYNTH']
    assert plan['incremental_symbols'] == 2 and plan['required_unique_symbols'] == 4
    assert plan['open_episode_counts'] == {'portfolio': 2, 'research': 2}
    assert plan['activation_authorized'] is False


def test_no_epoch_is_empty_inventory_not_permission_to_subscribe():
    release, _ = fixture()
    plan = plan_live_group(None, release, capacity=550)
    assert plan['symbols'] == [] and plan['activation_authorized'] is False


def test_capacity_never_silently_drops_an_open_symbol():
    release, saved = fixture()
    with pytest.raises(ShadowIntegrityError, match='CAPACITY_EXCEEDED'):
        plan_live_group(saved, release, capacity=1, protected_symbols=['LEGACY'])


@pytest.mark.parametrize('capacity', [0, 551, True])
def test_capacity_requires_bounded_integer(capacity):
    release, saved = fixture()
    with pytest.raises(ShadowIntegrityError, match='CAPACITY_INVALID'):
        plan_live_group(saved, release, capacity=capacity)


def test_corrupt_snapshot_and_other_release_are_refused():
    release, saved = fixture()
    saved['state']['code_revision'] = 'f' * 40
    with pytest.raises(ShadowIntegrityError, match='STATE_HASH'):
        plan_live_group(saved, release, capacity=550)
    saved['state_sha'] = digest(saved['state'])
    with pytest.raises(ShadowIntegrityError, match='RELEASE_MISMATCH'):
        plan_live_group(saved, release, capacity=550)


def test_diagnostic_never_produces_live_subscription_plan():
    with pytest.raises(ShadowIntegrityError, match='REQUIRES_CERTIFIED'):
        plan_live_group(None, SimpleNamespace(mode='DIAGNOSTIC', epoch='R2D2-V2-DIAG-X'), capacity=550)
