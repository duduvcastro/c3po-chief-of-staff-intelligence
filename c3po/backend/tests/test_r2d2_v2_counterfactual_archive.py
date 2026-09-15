"""Immutable archive binding and explicit limits of P5's real export path."""
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime

import pytest

from app.r2d2_v2_counterfactual_archive import summarize
from app.r2d2_v2_store import MemoryShadowStore, PostgresShadowStore, ShadowIntegrityError, digest, utc
from tests.test_r2d2_v2_portfolio import apply, candidate, event
from tests.test_r2d2_v2_eod_portfolio import q

EPOCH = "R2D2-V2-SHADOW-ARCHIVE-TEST"
CLOSE = "2026-09-08T20:00:00+00:00"


def archive(*, eod=True):
    ledger, _, _ = candidate()
    quote = q(price=101 if eod else 99)
    ledger = apply(ledger, quote)
    if not eod:
        ledger = apply(ledger, event("TRADE", 2, at="2026-09-08T19:59:45+00:00", price=90, regular=True))
    state = {"epoch": EPOCH, "mode": "CERTIFIED", "manifest_sha": "a" * 64,
             "release_sha": "b" * 64, "ledger": ledger,
             "event_receipts": {quote["event_id"]: "c" * 64}}
    payload = {"journal_key": "event:" + quote["event_id"], "type": "SOURCE_EVENT",
               "source": {"event_id": quote["event_id"], "envelope_sha256": "c" * 64},
               "applied_event": quote}
    store = MemoryShadowStore()
    store.atomic(EPOCH, state, lambda s: (s, [payload], None), utc(CLOSE))
    return store, store.read_with_journal(EPOCH)


def test_real_archive_does_not_infer_detector_coverage_from_empty_or_successful_event_tape():
    _, (saved, journal) = archive()
    before = deepcopy(saved)
    result = summarize(saved, journal, sessions=["2026-09-08"], cutoff=CLOSE)
    arm = result["arms"]["ELIGIBLE"]
    assert result["archive_status"] == "VERIFIED" and result["archive_record_count"] == 1
    assert arm["subjected_episodes"] == 1 and arm["counterfactual_defined"] == 0
    assert arm["nd_counts"]["CF_EVENT_CLOCK_UNAVAILABLE"] == 1
    assert arm["difference_pnl_usd_sum"] is None and arm["paired_coverage"] == 0
    assert saved == before and result["official_effect"] is False


def test_unaltered_trajectory_is_a_defined_zero_difference_with_its_denominator():
    _, (saved, journal) = archive(eod=False)
    result = summarize(saved, journal, sessions=["2026-09-08"], cutoff=CLOSE)
    arm = result["arms"]["ELIGIBLE"]
    assert arm["subjected_episodes"] == arm["counterfactual_defined"] == arm["paired_episodes"] == 1
    assert arm["difference_pnl_usd_sum"] == arm["difference_pnl_r_sum"] == 0
    assert arm["paired_coverage"] == 1


@pytest.mark.parametrize("mutation", ["bytes", "truncate", "wrong_head", "state_bytes", "foreign_epoch"])
def test_archive_tampering_is_rejected_before_any_comparison(mutation):
    _, (saved, journal) = archive()
    if mutation == "bytes":
        journal[0]["payload"]["applied_event"]["bid"] = 500
    elif mutation == "truncate":
        journal.clear()
    elif mutation == "wrong_head":
        saved["journal_head"] = "d" * 64
    elif mutation == "state_bytes":
        saved["state"]["ledger"]["cash"] += 1
    else:
        journal[0]["epoch"] = "R2D2-V2-SHADOW-OTHER"
    with pytest.raises(ShadowIntegrityError):
        summarize(saved, journal, sessions=["2026-09-08"], cutoff=CLOSE)


def test_valid_chain_cannot_bind_a_source_receipt_from_another_snapshot():
    _, (saved, journal) = archive()
    saved["state"]["event_receipts"] = {}
    saved["state_sha"] = digest(saved["state"])
    with pytest.raises(ShadowIntegrityError, match="P5_SOURCE_RECEIPT_MISMATCH"):
        summarize(saved, journal, sessions=["2026-09-08"], cutoff=CLOSE)


def test_later_entry_sessions_and_later_outcomes_cannot_change_fixed_cohort_comparison():
    _, (saved, journal) = archive()
    result = summarize(saved, journal, sessions=["2026-09-07"], cutoff=CLOSE)
    assert result["arms"]["ELIGIBLE"]["subjected_episodes"] == 0
    old = summarize(saved, journal, sessions=["2026-09-08"], cutoff="2026-09-08T19:59:00+00:00")
    # Neither a future EOD window nor its future terminal result enters this
    # reading's denominator; journal rows after cutoff are also excluded.
    assert old["arms"]["ELIGIBLE"]["subjected_episodes"] == 0
    assert old["arms"]["ELIGIBLE"]["counterfactual_defined"] == 0
    assert old["archive_record_count"] == 0


def test_postgres_archive_read_uses_one_read_only_repeatable_snapshot_and_reconstructs_hash_clock():
    _, (saved, journal) = archive()
    calls = []
    class Connection:
        def execute(self, sql, params=None):
            calls.append(sql)
            self.sql = sql
            return self
        def fetchone(self):
            return tuple(saved[k] for k in ("state", "state_sha", "manifest_sha", "version", "journal_head"))
        def fetchall(self):
            return [tuple(datetime.fromisoformat(row[k]) if k == "recorded_at" else row[k]
                          for k in ("epoch", "sequence", "journal_key", "recorded_at", "payload", "previous_sha", "record_sha"))
                    for row in journal]
    @contextmanager
    def connect():
        yield Connection()
    row, records = PostgresShadowStore(connect).read_with_journal(EPOCH)
    assert row["state_sha"] == saved["state_sha"] and records == journal
    assert calls[0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
    assert len(calls) == 3 and all(sql.startswith("SELECT") for sql in calls[1:])
