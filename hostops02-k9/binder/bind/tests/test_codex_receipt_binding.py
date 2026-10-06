"""Adversarial binder test: an old PRIV receipt cannot be made fresh by editing the plan timestamp."""
from types import SimpleNamespace
import pytest
import helpers as h

b = h.b
from datetime import datetime,timezone
OP = 'GO_READONLY_HOSTOPS02_DB_PRIV_01'
QUERIES = 'GO_READONLY_HOSTOPS02_DB_PREFLIGHT_01'
BOOT = 'b0' * 32


def context(observed='2026-10-05T20:30:00+00:00'):
    receipt = {'operation': OP, 'mode': 'PRIV', 'outcome': 'PRIV_COMPLETE',
               'metadata_sha256': 'd1' * 32, 'boot_id_sha256': BOOT,
               'observed_at': '2026-10-04T20:30:00+00:00'}
    plan = {'mode': 'QUERIES', 'evidence_boot_id_sha256': BOOT,
            'priv_receipt': {'operation': OP, 'mode': 'PRIV', 'outcome': 'PRIV_COMPLETE',
                             'receipt_sha256': 'd1' * 32, 'boot_id_sha256': BOOT, 'observed_at': observed}}
    return {'plan': plan, 'operation': QUERIES, 'rt': {'source': SimpleNamespace(PRIV_COMPLETE_OUTCOME='PRIV_COMPLETE',PRIV_OPERATION=OP,MODES=('QUERIES',))}, 'window': {'start':datetime(2026,10,4,20,38,tzinfo=timezone.utc)},
            'entries': [{'role': 'PRIV', 'operation': OP}], 'receipts': {'PRIV': receipt},
            'evidence_facts': [{'role': 'PRIV', 'complete': True}]}


def test_priv_timestamp_cannot_be_forged_to_today():
    with h.refused('DBR_PRIV_RECEIPT_NOT_THE_CITED_ONE'):
        b.dbr_rules(context())


def test_exact_priv_timestamp_is_bound():
    ctx = context('2026-10-04T20:30:00+00:00')
    assert b.dbr_rules(ctx) == {'priv_receipt_role': 'PRIV'}


def test_priv_timestamp_cannot_be_missing_on_the_receipt():
    ctx = context('2026-10-04T20:30:00+00:00')
    del ctx['receipts']['PRIV']['observed_at']
    with h.refused('DBR_PRIV_RECEIPT_NOT_THE_CITED_ONE'):
        b.dbr_rules(ctx)
