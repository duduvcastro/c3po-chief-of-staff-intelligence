"""Read-only verification of causal-list receipts against committed audit rows.

A producer-supplied timestamp or checksum is not proof that the list existed
on D−1. This verifier reads the event independently by ID. It cannot create or
backdate audit rows, publish a list, initialize the application, or call a feed.
"""
from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

from .r2d2_v2_store import canonical, utc


class PostgresCausalReceiptVerifier:
    def __init__(self, connection_factory: Callable):
        self.connection_factory = connection_factory

    def __call__(self, receipt: dict[str, Any], expected: dict[str, Any]) -> bool:
        try:
            identity = str(UUID(receipt["event_id"]))
            if identity != receipt["event_id"]:
                return False
            if expected["event_type"] not in {
                    "r2d2.v2.causal_list_built", "r2d2.v2.causal_list_published"}:
                return False
            with self.connection_factory() as connection:
                if connection is None:
                    return False
                row = connection.execute(
                    "SELECT action,occurred_at,detail FROM audit_events WHERE id=%s",
                    (identity,)).fetchone()
            if row is None:
                return False
            action, occurred_at, detail = row
            return (action == expected["event_type"]
                    and utc(occurred_at) == utc(expected["occurred_at"])
                    and canonical(detail) == canonical(expected["payload"]))
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            return False
