from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pytest

from app.cve_acceptance import (
    REGISTRY_RELATIVE_PATH,
    SIGNED_SPEC_SHA256,
    acceptance_entry_sha256,
    apply_acceptance_overlay,
    load_acceptance_registry,
)


NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def _entry(*, review_at: datetime | None = None, **overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "vulnerability_id": "CVE-2026-TEST",
        "package": "lib-test",
        "image": "backend",
        "target": "debian 13",
        "installed_version": "1.0-1",
        "justificativa": "sem FixedVersion upstream em 03/09/2026",
        "accepted_by": ["Dudu", "Fable", "Codex"],
        "accepted_at": (NOW - timedelta(days=1)).isoformat(),
        "review_at": (review_at or NOW + timedelta(days=29)).isoformat(),
    }
    entry.update(overrides)
    entry["entry_sha256"] = acceptance_entry_sha256(entry)
    return entry


def _write_registry(root: Path, entries: list[dict[str, object]]) -> Path:
    path = root / REGISTRY_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return path


def _production() -> dict[str, Any]:
    return {
        "status": "offline",
        "available": True,
        "finding_total": 4,
        "by_severity": {"critical": 1, "high": 1, "medium": 1, "low": 0},
        "unknown": 1,
        "fix_available": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "image_count": 3,
        "images": [
            {
                "label": "backend",
                "unfixed_high_critical": [
                    {
                        "vulnerability_id": "CVE-2026-TEST",
                        "severity": "critical",
                        "package": "lib-test",
                        "installed_version": "1.0-1",
                        "fixed_version": "",
                        "target": "debian 13",
                    },
                    {
                        "vulnerability_id": "CVE-2026-PENDING",
                        "severity": "high",
                        "package": "lib-pending",
                        "installed_version": "2.0-1",
                        "fixed_version": "",
                        "target": "debian 13",
                    },
                ],
            },
            {"label": "web", "unfixed_high_critical": []},
            {"label": "database", "unfixed_high_critical": []},
        ],
        "dead_man_configured": True,
        "generated_at": NOW.isoformat(),
        "report_sha256": "a" * 64,
    }


def test_empty_registry_is_versioned_and_exact_bytes_are_hashed(tmp_path: Path) -> None:
    path = _write_registry(tmp_path, [])

    entries, observed_hash = load_acceptance_registry(tmp_path)

    import hashlib

    assert entries == []
    assert observed_hash == hashlib.sha256(path.read_bytes()).hexdigest()
    assert SIGNED_SPEC_SHA256 == (
        "6a9dc31489959c0b5d4bcf7792e59ce6f6b2e7706802e8d2b0db9ac2e09cfd35"
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda entry: entry.update(entry_sha256="0" * 64), "entry_sha256"),
        (
            lambda entry: entry.update(
                review_at=(NOW + timedelta(days=31)).isoformat()
            ),
            "30 days",
        ),
        (lambda entry: entry.update(accepted_by=["Dudu", "Fable"]), "Dudu"),
        (
            lambda entry: entry.update(accepted_by=["Alice", "Bob", "Carol"]),
            "Dudu",
        ),
        (
            lambda entry: entry.update(review_at="2026-10-01T12:00:00-03:00"),
            "must be UTC",
        ),
        (
            lambda entry: entry.update(justificativa="risk accepted"),
            "upstream/date",
        ),
    ],
)
def test_registry_fails_closed_on_invalid_signed_entries(
    tmp_path: Path,
    mutate: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    entry = _entry()
    mutate(entry)
    _write_registry(tmp_path, [entry])

    with pytest.raises(RuntimeError, match=message):
        load_acceptance_registry(tmp_path)


def test_overlay_keeps_raw_projection_untouched_and_unknown_pending() -> None:
    production = _production()
    before = deepcopy(production)
    entry = _entry()

    result = apply_acceptance_overlay(
        production,
        [entry],
        registry_sha256="b" * 64,
        measured_at=NOW,
    )

    assert production == before
    assert result["finding_total"] == 4
    assert result["by_severity"] == before["by_severity"]
    acceptance = result["acceptance"]
    assert acceptance["counts"]["raw"] == {
        "total": 4,
        "by_severity": {"critical": 1, "high": 1, "medium": 1, "low": 0},
        "unknown": 1,
    }
    assert acceptance["counts"]["accepted"]["by_severity"]["critical"] == 1
    assert acceptance["counts"]["pending"] == {
        "total": 3,
        "by_severity": {"critical": 0, "high": 1, "medium": 1, "low": 0},
        "unknown": 1,
    }
    assert acceptance["incident_status"] == "offline"
    assert result["status"] == "offline"
    assert result["report_sha256"] == "a" * 64


@pytest.mark.parametrize(
    ("offset", "expected_status", "accepted", "pending", "expired"),
    [
        (timedelta(microseconds=-1), "aceito", 1, 0, 0),
        (timedelta(0), "aceito_vencido", 0, 1, 1),
        (timedelta(microseconds=1), "aceito_vencido", 0, 1, 1),
    ],
)
def test_expiry_boundary_uses_fixed_utc_clock(
    offset: timedelta,
    expected_status: str,
    accepted: int,
    pending: int,
    expired: int,
) -> None:
    review_at = NOW
    production = _production()
    production["finding_total"] = 1
    production["by_severity"] = {
        "critical": 1,
        "high": 0,
        "medium": 0,
        "low": 0,
    }
    production["unknown"] = 0
    production["images"][0]["unfixed_high_critical"] = [
        production["images"][0]["unfixed_high_critical"][0]
    ]

    result = apply_acceptance_overlay(
        production,
        [_entry(review_at=review_at)],
        registry_sha256="c" * 64,
        measured_at=review_at + offset,
    )

    overlay = result["acceptance"]
    assert overlay["findings"][0]["acceptance_status"] == expected_status
    assert overlay["counts"]["accepted"]["total"] == accepted
    assert overlay["counts"]["pending"]["total"] == pending
    assert overlay["counts"]["expired"]["total"] == expired
    assert result["status"] == ("attention" if accepted else "offline")
    assert overlay["incident_status"] == ("healthy" if accepted else "offline")


def test_active_registry_entry_absent_from_raw_report_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="absent from raw report"):
        apply_acceptance_overlay(
            _production(),
            [_entry(package="different-package")],
            registry_sha256="d" * 64,
            measured_at=NOW,
        )


def test_future_acceptance_cannot_apply_before_three_hands_act() -> None:
    entry = _entry(
        review_at=NOW + timedelta(days=1),
        accepted_at=(NOW + timedelta(minutes=1)).isoformat(),
    )

    with pytest.raises(RuntimeError, match="accepted_at is in the future"):
        apply_acceptance_overlay(
            _production(),
            [entry],
            registry_sha256="f" * 64,
            measured_at=NOW,
        )


def test_fixed_version_reopens_an_existing_acceptance_immediately() -> None:
    production = _production()
    finding = production["images"][0]["unfixed_high_critical"].pop(0)
    finding["fixed_version"] = "1.0-2"
    production["images"][0]["fixable_high_critical"] = [finding]

    result = apply_acceptance_overlay(
        production,
        [_entry()],
        registry_sha256="1" * 64,
        measured_at=NOW,
    )

    reopened = next(
        item
        for item in result["acceptance"]["findings"]
        if item["vulnerability_id"] == "CVE-2026-TEST"
    )
    assert reopened["acceptance_status"] == "pendente"
    assert reopened["fixed_version"] == "1.0-2"
    assert reopened["entry_sha256"] == _entry()["entry_sha256"]
    assert result["acceptance"]["counts"]["accepted"]["total"] == 0
    assert result["acceptance"]["counts"]["pending"]["total"] == 4


def test_fixable_high_critical_is_present_in_v3_as_pending() -> None:
    production = _production()
    finding = production["images"][0]["unfixed_high_critical"].pop(0)
    finding["fixed_version"] = "1.0-2"
    production["images"][0]["fixable_high_critical"] = [finding]

    result = apply_acceptance_overlay(
        production,
        [],
        registry_sha256="3" * 64,
        measured_at=NOW,
    )

    overlay_finding = next(
        item
        for item in result["acceptance"]["findings"]
        if item["vulnerability_id"] == "CVE-2026-TEST"
    )
    assert overlay_finding["acceptance_status"] == "pendente"
    assert overlay_finding["fixed_version"] == "1.0-2"


def test_missing_per_finding_evidence_never_degrades_to_aggregate_acceptance() -> None:
    production = _production()
    production["images"][0]["unfixed_high_critical"] = []

    with pytest.raises(RuntimeError, match="detailed critical/high counts"):
        apply_acceptance_overlay(
            production,
            [],
            registry_sha256="4" * 64,
            measured_at=NOW,
        )


def test_archived_entry_stays_hashed_but_no_longer_matches_live_raw() -> None:
    entry = _entry(archived_at=NOW.isoformat())
    production = _production()

    result = apply_acceptance_overlay(
        production,
        [entry],
        registry_sha256="2" * 64,
        measured_at=NOW,
    )

    assert result["acceptance"]["registry"]["active_entries"] == 0
    assert result["acceptance"]["registry"]["archived_entries"] == 1
    assert result["acceptance"]["counts"]["accepted"]["total"] == 0


def test_medium_low_only_stays_visible_but_does_not_keep_incident_open() -> None:
    production = _production()
    production["finding_total"] = 2
    production["by_severity"] = {
        "critical": 0,
        "high": 0,
        "medium": 1,
        "low": 1,
    }
    production["unknown"] = 0
    for image in production["images"]:
        image["unfixed_high_critical"] = []

    result = apply_acceptance_overlay(
        production,
        [],
        registry_sha256="e" * 64,
        measured_at=NOW,
    )

    assert result["status"] == "attention"
    assert result["acceptance"]["counts"]["pending"]["total"] == 2
    assert result["acceptance"]["incident_status"] == "healthy"


def test_registry_has_no_runtime_write_route_and_api_runner_has_incident_ledger() -> None:
    from app import main as app_main

    write_methods = {"POST", "PUT", "PATCH", "DELETE"}
    acceptance_writes = [
        (route.path, set(getattr(route, "methods", None) or []))
        for route in app_main.app.routes
        if "acceptance" in route.path.casefold()
        and set(getattr(route, "methods", None) or []).intersection(write_methods)
    ]

    assert acceptance_writes == []
    assert app_main.governance_vulnerability.operational_incidents is (
        app_main.operational_incidents
    )


def test_versioned_docs_pin_signed_spec_and_default_off() -> None:
    project = Path(__file__).resolve().parents[2]
    docs = (project / "docs" / "CVE_ACCEPTANCE_LANE_V1.md").read_text(
        encoding="utf-8"
    )
    config = (project / "backend" / "app" / "config.py").read_text(
        encoding="utf-8"
    )

    assert SIGNED_SPEC_SHA256 in docs
    assert "UNKNOWN/TEMP findings remain pending" in docs
    assert "cve_acceptance_lane_enabled: bool = False" in config
