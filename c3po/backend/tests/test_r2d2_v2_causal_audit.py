from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.r2d2_v2_causal_audit import PostgresCausalReceiptVerifier


def evidence():
    expected = {"event_type": "r2d2.v2.causal_list_built",
        "occurred_at": "2026-09-04T21:00:00+00:00",
        "payload": {"epoch": "R2D2-V2-SHADOW-SYNTHETIC", "session": "2026-09-08",
                    "list_sha256": "a" * 64}}
    receipt = {"event_id": "00000000-0000-0000-0000-000000000001", **expected}
    row = (expected["event_type"], datetime(2026, 9, 4, 21, tzinfo=timezone.utc), expected["payload"])
    return receipt, expected, row


class ReadOnlyConnection:
    def __init__(self, row):
        self.row = row
        self.calls = []
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, sql, params):
        assert sql.startswith("SELECT ") and "FROM audit_events WHERE id=%s" in sql
        self.calls.append((sql, params))
        return SimpleNamespace(fetchone=lambda: self.row)


def test_receipt_must_have_independent_database_readback():
    receipt, expected, row = evidence()
    connection = ReadOnlyConnection(row)
    assert PostgresCausalReceiptVerifier(lambda: connection)(receipt, expected)
    assert connection.calls[0][1] == (receipt["event_id"],)
    assert not PostgresCausalReceiptVerifier(lambda: ReadOnlyConnection(None))(receipt, expected)
    assert not PostgresCausalReceiptVerifier(lambda: None)(receipt, expected)


@pytest.mark.parametrize("mutation", ["action", "timestamp", "payload", "missing_id", "bad_id"])
def test_self_consistent_file_does_not_override_committed_audit_row(mutation):
    receipt, expected, row = evidence()
    if mutation == "action":
        row = ("unrelated.event", row[1], row[2])
    elif mutation == "timestamp":
        row = (row[0], datetime(2026, 9, 8, 14, tzinfo=timezone.utc), row[2])
    elif mutation == "payload":
        row = (row[0], row[1], dict(row[2], list_sha256="b" * 64))
    elif mutation == "missing_id":
        receipt.pop("event_id")
    else:
        receipt["event_id"] = "'; SELECT secret"
    assert not PostgresCausalReceiptVerifier(lambda: ReadOnlyConnection(row))(receipt, expected)
