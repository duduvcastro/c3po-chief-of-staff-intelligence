from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app import main as app_main

app = app_main.app


def test_health_and_command_center_contracts() -> None:
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        command = client.get("/api/v1/command-center")

    assert health.status_code == 200
    assert health.json()["service"] == "c3po-api"
    assert command.status_code == 200
    payload = command.json()
    assert payload["report_title"].endswith(datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y"))
    assert payload["billfish"]["net_worth"] == "R$ 23.718.117,35"
    assert payload["provenance"]["source"] == "Legacy Summary Adapter"


def test_summary_context_tracks_sao_paulo_dayparts() -> None:
    sao_paulo = ZoneInfo("America/Sao_Paulo")

    assert app_main._current_summary_context(datetime(2026, 8, 16, 8, tzinfo=sao_paulo)) == (
        "Good morning",
        "Morning Summary - 16/08/2026",
        "16/08/2026",
    )
    assert app_main._current_summary_context(datetime(2026, 8, 16, 14, tzinfo=sao_paulo)) == (
        "Good afternoon",
        "Lunch Summary - 16/08/2026",
        "16/08/2026",
    )
    assert app_main._current_summary_context(datetime(2026, 8, 16, 19, 7, tzinfo=sao_paulo)) == (
        "Good evening",
        "Night Summary - 16/08/2026",
        "16/08/2026",
    )


def test_market_data_provider_contract() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/market-data/providers")

    assert response.status_code == 200
    providers = response.json()
    assert [item["code"] for item in providers] == ["brapi", "eodhd"]
    assert all("configured" in item and "last_success_at" in item for item in providers)


def test_global_search_finds_registered_company() -> None:
    app_main.database.register_ir_securities(
        [
            {
                "market": "B3",
                "symbol": "ZXQZ3",
                "company_name": "Zeta Search Test S.A.",
                "name_key": "zeta search test",
                "exchange": "B3",
            }
        ]
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/search", params={"q": "ZXQZ3"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "ZXQZ3"
    assert payload["companies"][0]["symbol"] == "ZXQZ3"
    assert payload["companies"][0]["company_name"] == "Zeta Search Test S.A."


def test_alerts_are_persistently_marked_read() -> None:
    app_main.database._audit_events.clear()
    app_main.database._alert_reads.clear()
    app_main.database.record_audit_event(
        actor="eu@eduardocastro.com.br",
        action="auth.login",
        subject_type="auth_session",
        subject_id="alert-read-test",
        detail={
            "display_name": "Eduardo Castro",
            "role": "owner",
            "requested_ip": "127.0.0.1",
            "client_info": {
                "device_type": "Computador Apple",
                "os": "macOS",
                "browser": "Safari",
            },
        },
    )

    with TestClient(app) as client:
        first_response = client.get("/api/v1/alerts")
        assert first_response.status_code == 200
        first = first_response.json()
        assert first["unread_count"] == len(first["items"])
        login_alert = next(item for item in first["items"] if item["source"] == "C3PO Access Control")
        assert login_alert["metadata"]["Dispositivo"] == "Computador Apple"
        assert login_alert["is_read"] is False

        alert_ids = [item["id"] for item in first["items"]]
        marked_response = client.post("/api/v1/alerts/read", json={"alert_ids": alert_ids})
        assert marked_response.status_code == 200
        assert marked_response.json()["marked_read"] == len(alert_ids)

        second_response = client.get("/api/v1/alerts")

    second = second_response.json()
    assert second["unread_count"] == 0
    assert all(item["is_read"] for item in second["items"])


def test_alerts_include_cpu_and_disk_capacity_incidents() -> None:
    app_main.database._server_usage_samples.clear()
    now = datetime.now(timezone.utc)
    app_main.database.save_server_usage_samples([
        {
            "server_id": "capacity-test",
            "server_name": "Capacity Test",
            "region": "sa-east-1",
            "collected_at": now - timedelta(minutes=2),
            "cpu_percent": 91.0,
            "disk_total_bytes": 1000,
            "disk_used_bytes": 720,
            "disk_free_bytes": 280,
            "source": "test",
        },
        {
            "server_id": "capacity-test",
            "server_name": "Capacity Test",
            "region": "sa-east-1",
            "collected_at": now,
            "cpu_percent": 96.0,
            "disk_total_bytes": 1000,
            "disk_used_bytes": 720,
            "disk_free_bytes": 280,
            "source": "test",
        },
    ])

    with TestClient(app) as client:
        response = client.get("/api/v1/alerts")

    assert response.status_code == 200
    capacity = [item for item in response.json()["items"] if item["source"] == "AWS Lightsail Telemetry"]
    assert {item["id"].split(":")[1] for item in capacity} == {"cpu", "disk"}
    assert next(item for item in capacity if ":cpu:" in item["id"])["severity"] == "Critical"
    assert next(item for item in capacity if ":disk:" in item["id"])["metadata"]["Disco usado"] == "72.0%"
    app_main.database._server_usage_samples.clear()


def test_navigation_indicators_clear_feed_badges_when_opened() -> None:
    original_views = app_main.database._navigation_feed_views.copy()
    original_events = app_main.database._ir_events.copy()
    original_security_map = app_main.database._ir_security_map.copy()
    original_valuation_changes = list(app_main.database._valuation_changes)
    app_main.database._navigation_feed_views.clear()
    app_main.database._ir_events.clear()
    app_main.database._ir_security_map.clear()
    app_main.database._valuation_changes.clear()

    try:
        with TestClient(app) as client:
            initial_response = client.get("/api/v1/navigation-indicators")
            assert initial_response.status_code == 200
            initial = initial_response.json()
            assert initial["feeds"]["relations"]["has_new"] is False
            assert initial["feeds"]["intelligence"]["has_new"] is False

            relation_seen_at = datetime.fromisoformat(initial["feeds"]["relations"]["last_seen_at"])
            intelligence_seen_at = datetime.fromisoformat(initial["feeds"]["intelligence"]["last_seen_at"])
            app_main.database._ir_security_map[("B3", "TEST3")] = "company-test"
            app_main.database._ir_events[("cvm", "event-test")] = {
                "id": "event-test",
                "company_id": "company-test",
                "collected_at": relation_seen_at + timedelta(seconds=1),
            }
            app_main.database._valuation_changes.append({
                "id": "valuation-test",
                "changed_at": intelligence_seen_at + timedelta(seconds=1),
            })

            updated_response = client.get("/api/v1/navigation-indicators")
            assert updated_response.status_code == 200
            updated = updated_response.json()
            assert updated["feeds"]["relations"]["unseen_count"] == 1
            assert updated["feeds"]["intelligence"]["unseen_count"] == 1

            marked = client.post("/api/v1/navigation-seen", json={"view": "relations"})
            assert marked.status_code == 200
            after_relation = client.get("/api/v1/navigation-indicators").json()
            assert after_relation["feeds"]["relations"]["has_new"] is False
            assert after_relation["feeds"]["intelligence"]["has_new"] is True

            marked = client.post("/api/v1/navigation-seen", json={"view": "intelligence"})
            assert marked.status_code == 200
            final = client.get("/api/v1/navigation-indicators").json()
            assert final["feeds"]["intelligence"]["has_new"] is False
    finally:
        app_main.database._navigation_feed_views = original_views
        app_main.database._ir_events = original_events
        app_main.database._ir_security_map = original_security_map
        app_main.database._valuation_changes = original_valuation_changes
