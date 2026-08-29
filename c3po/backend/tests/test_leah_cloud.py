from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app.config import Settings
from app.database import Database
from app.leah_cloud import LeahAuthenticationError, LeahCloudService


def test_pairing_is_single_use_and_device_token_is_scoped() -> None:
    settings = Settings(auth_secret="a-secure-test-secret-with-more-than-32-characters")
    database = Database(settings)
    service = LeahCloudService(settings, database)

    pairing = service.create_pairing("eduardo@example.com")
    paired = service.pair_device(pairing["code"], "Mac do Eduardo", "macOS")

    assert paired["device"]["owner_email"] == "eduardo@example.com"
    assert service.authenticate_device(f"Bearer {paired['token']}")["name"] == "Mac do Eduardo"
    with pytest.raises(LeahAuthenticationError):
        service.pair_device(pairing["code"], "Outro Mac", "macOS")


def test_sync_keeps_each_users_items_isolated() -> None:
    settings = Settings(auth_secret="a-secure-test-secret-with-more-than-32-characters")
    database = Database(settings)
    service = LeahCloudService(settings, database)
    eduardo_pairing = service.create_pairing("eduardo@example.com")
    nina_pairing = service.create_pairing("nina@example.com")
    eduardo = service.pair_device(eduardo_pairing["code"], "Mac Eduardo", "macOS")["device"]
    nina = service.pair_device(nina_pairing["code"], "Mac Nina", "macOS")["device"]

    service.sync(
        eduardo,
        {
            "calendar_authorized": True,
            "reminders_authorized": True,
            "items": [{
                "kind": "task",
                "external_id": "reminder-1",
                "title": "Tarefa privada Eduardo",
                "source_modified_at": datetime.now(timezone.utc),
            }],
        },
    )

    assert [item["title"] for item in database.list_leah_changes("eduardo@example.com")] == ["Tarefa privada Eduardo"]
    assert database.list_leah_changes("nina@example.com") == []
    assert service.sync(nina, {"items": []})["items"] == []


def test_web_item_round_trip_reaches_agent_and_agent_adds_external_id() -> None:
    settings = Settings(auth_secret="a-secure-test-secret-with-more-than-32-characters")
    database = Database(settings)
    service = LeahCloudService(settings, database)
    pairing = service.create_pairing("eduardo@example.com")
    paired = service.pair_device(pairing["code"], "Mac Eduardo", "macOS")
    created = database.upsert_leah_item(
        {
            "owner_email": "eduardo@example.com",
            "kind": "event",
            "title": "Reunião criada no C3PO",
            "starts_at": datetime(2026, 8, 24, 13, 0, tzinfo=timezone.utc),
            "ends_at": datetime(2026, 8, 24, 14, 0, tzinfo=timezone.utc),
            "source": "c3po",
        }
    )

    pulled = service.sync(paired["device"], {"items": []})["items"]
    assert pulled[0]["id"] == created["id"]
    service.sync(
        paired["device"],
        {
            "items": [{
                **pulled[0],
                "external_id": "eventkit-42",
                "source_modified_at": datetime.now(timezone.utc),
            }]
        },
    )
    stored = database.get_leah_item("eduardo@example.com", created["id"])
    assert stored and stored["external_id"] == "eventkit-42"


def test_web_delete_reaches_agent_as_tombstone_with_eventkit_identity() -> None:
    settings = Settings(auth_secret="a-secure-test-secret-with-more-than-32-characters")
    database = Database(settings)
    service = LeahCloudService(settings, database)
    pairing = service.create_pairing("eduardo@example.com")
    device = service.pair_device(pairing["code"], "Mac Eduardo", "macOS")["device"]
    starts_at = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)
    created = database.upsert_leah_item(
        {
            "owner_email": "eduardo@example.com",
            "kind": "event",
            "external_id": "eventkit-calendar-item-42",
            "container_id": "icloud-calendar-1",
            "title": "Evento removido no Leah",
            "starts_at": starts_at,
            "ends_at": starts_at + timedelta(hours=1),
            "source": "icloud",
        }
    )
    cursor = service.sync(device, {"items": []})["cursor"]

    assert database.delete_leah_item("eduardo@example.com", created["id"], cursor + timedelta(seconds=1))
    cursor_after_delete = cursor + timedelta(seconds=2)
    pulled = service.sync(
        device,
        {
            "cursor": cursor_after_delete,
            "replay_deleted_since": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "items": [],
        },
    )["items"]

    assert len(pulled) == 1
    assert pulled[0]["source"] == "c3po"
    assert pulled[0]["deleted_at"] is not None
    assert pulled[0]["external_id"] == "eventkit-calendar-item-42"
    assert pulled[0]["starts_at"] == starts_at


def test_eventkit_delete_uses_the_calendar_item_identifier_lookup() -> None:
    agent_root = Path(__file__).resolve().parents[3] / "tools/leah-cloud-agent/Sources/LeahCloudAgent"
    source = (agent_root / "EventKitBridge.swift").read_text()
    model_source = (agent_root / "AgentModel.swift").read_text()

    assert "store.calendarItem(withIdentifier: identifier) as? EKEvent" in source
    assert "try store.remove(existingEvent, span: .thisEvent, commit: true)" in source
    assert "private static let syncSchemaVersion = 4" in model_source
    assert "let cursor = UserDefaults.standard.object(forKey: \"serverCursor\") as? Date" in model_source
    assert "replayDeletedSince: storedSchemaVersion == Self.syncSchemaVersion ? nil : .distantPast" in model_source


def test_recurring_event_occurrences_with_same_external_id_are_preserved() -> None:
    database = Database(Settings())
    owner = "eduardo@example.com"
    first_start = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    second_start = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)

    for start in (first_start, second_start):
        database.upsert_leah_item(
            {
                "owner_email": owner,
                "kind": "event",
                "external_id": "eventkit-recurring-series",
                "title": "Pilates",
                "starts_at": start,
                "ends_at": start + timedelta(hours=1),
                "source": "icloud",
            }
        )

    occurrences = database.list_leah_changes(owner)
    assert len(occurrences) == 2
    assert {item["starts_at"] for item in occurrences} == {first_start, second_start}


def test_complete_calendar_snapshot_marks_missing_occurrence_deleted() -> None:
    settings = Settings(auth_secret="a-secure-test-secret-with-more-than-32-characters")
    database = Database(settings)
    service = LeahCloudService(settings, database)
    pairing = service.create_pairing("eduardo@example.com")
    device = service.pair_device(pairing["code"], "Mac Eduardo", "macOS")["device"]
    older_start = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    first_start = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
    second_start = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    items = [
        {
            "kind": "event",
            "external_id": "recurring-test",
            "title": "Teste",
            "starts_at": start,
            "ends_at": start + timedelta(hours=1),
        }
        for start in (older_start, first_start, second_start)
    ]

    service.sync(device, {"calendar_authorized": True, "items": items})
    service.sync(
        device,
        {
            "calendar_authorized": True,
            "items": [],
            "calendar_snapshot": [{"external_id": "recurring-test", "starts_at": second_start}],
            "calendar_snapshot_start": first_start - timedelta(days=1),
            "calendar_snapshot_end": second_start + timedelta(days=1),
        },
    )

    stored = database.list_leah_changes("eduardo@example.com")
    assert next(item for item in stored if item["starts_at"] == first_start)["deleted_at"] is not None
    assert next(item for item in stored if item["starts_at"] == second_start)["deleted_at"] is None
    assert next(item for item in stored if item["starts_at"] == older_start)["deleted_at"] is None


def test_leah_api_exposes_pairing_and_personal_items() -> None:
    with TestClient(app_main.app) as client:
        pairing = client.post("/api/v1/leah/pairings")
        assert pairing.status_code == 201
        assert len(pairing.json()["code"]) == 8

        item = client.post(
            "/api/v1/leah/items",
            json={"kind": "task", "title": "Comprar pão"},
        )
        assert item.status_code == 201
        payload = client.get("/api/v1/leah").json()
        assert any(entry["title"] == "Comprar pão" for entry in payload["items"])
