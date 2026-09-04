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
    assert isinstance(payload["billfish"], dict)
    assert isinstance(payload["portfolio"], list)
    assert set(payload["markets"]) == {"Index", "Currencies", "CRIPTO"}
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
            "display_name": "Dudu Castro",
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
    items = response.json()["items"]
    occurred_at = [datetime.fromisoformat(item["occurred_at"]) for item in items]
    assert occurred_at == sorted(occurred_at, reverse=True)
    capacity = [item for item in items if item["source"] == "AWS Lightsail Telemetry"]
    assert {item["id"].split(":")[1] for item in capacity} == {"cpu", "disk"}
    assert next(item for item in capacity if ":cpu:" in item["id"])["severity"] == "Critical"
    assert next(item for item in capacity if ":disk:" in item["id"])["metadata"]["Disco usado"] == "72.0%"
    app_main.database._server_usage_samples.clear()


def test_alerts_include_cash_yield_failure_and_recovery_events() -> None:
    app_main.database._audit_events.clear()
    app_main.database._alert_reads.clear()
    app_main.database.record_audit_event(
        actor="valuation-worker",
        action="r2d2.cash_yield.failed",
        subject_type="r2d2_cash_yield_session",
        subject_id="2026-08-26",
        detail={
            "scheduled_for": "2026-08-26T06:00:00-03:00",
            "error": "CashYieldDataError: Treasury observation missing",
        },
    )
    app_main.database.record_audit_event(
        actor="valuation-worker",
        action="r2d2.cash_yield.recovered",
        subject_type="r2d2_cash_yield_session",
        subject_id="2026-08-26",
        detail={"scheduled_for": "2026-08-26T06:00:00-03:00"},
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/alerts")

    assert response.status_code == 200
    alerts = [
        item for item in response.json()["items"]
        if item["source"] == "R2D2 Accounting Controls"
    ]
    assert {item["severity"] for item in alerts} == {"Critical", "Operational"}
    failure = next(item for item in alerts if item["severity"] == "Critical")
    recovery = next(item for item in alerts if item["severity"] == "Operational")
    assert failure["metadata"]["Erro"] == "CashYieldDataError: Treasury observation missing"
    assert recovery["metadata"]["Erro"] == "Nenhum; processamento recuperado"
    app_main.database._audit_events.clear()


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


def test_r2d2_reads_are_served_from_the_single_flight_cache(monkeypatch) -> None:
    calls = {"dashboard": 0, "live": 0}
    real_dashboard = app_main.r2d2.dashboard
    real_live = app_main.r2d2.live_positions

    def counted_dashboard():
        calls["dashboard"] += 1
        return real_dashboard()

    def counted_live():
        calls["live"] += 1
        return real_live()

    monkeypatch.setattr(app_main.r2d2, "dashboard", counted_dashboard)
    monkeypatch.setattr(app_main.r2d2, "live_positions", counted_live)
    monkeypatch.setattr(app_main, "_r2d2_read_cache_ttl_seconds", lambda: 60.0)
    monkeypatch.setattr(app_main.r2d2_read_cache, "_ttl_seconds", app_main._r2d2_read_cache_ttl_seconds)
    app_main.r2d2_read_cache.invalidate()
    with TestClient(app) as client:
        first = client.get("/api/v1/r2d2")
        second = client.get("/api/v1/r2d2")
        live_first = client.get("/api/v1/r2d2/live-positions")
        live_second = client.get("/api/v1/r2d2/live-positions")
    app_main.r2d2_read_cache.invalidate()

    assert first.status_code == second.status_code == 200
    assert live_first.status_code == live_second.status_code == 200
    assert first.json() == second.json()
    assert live_first.json() == live_second.json()
    assert calls == {"dashboard": 1, "live": 1}
    assert isinstance(first.json()["market_session_open"], bool)
    assert isinstance(live_first.json()["market_session_open"], bool)


def test_r2d2_read_cache_ttl_follows_the_market_session(monkeypatch) -> None:
    monkeypatch.setattr(app_main.r2d2_session_clock, "is_open", lambda now=None: True)
    assert app_main._r2d2_read_cache_ttl_seconds() == float(app_main.settings.r2d2_read_cache_open_seconds)
    monkeypatch.setattr(app_main.r2d2_session_clock, "is_open", lambda now=None: False)
    assert app_main._r2d2_read_cache_ttl_seconds() == float(app_main.settings.r2d2_read_cache_closed_seconds)
    assert app_main.settings.r2d2_read_cache_open_seconds == 5
    assert app_main.settings.r2d2_read_cache_closed_seconds == 30


def test_leah_sync_guard_rejections_map_to_retry_after_responses(monkeypatch) -> None:
    from app.leah_sync_guard import LeahSyncBusy, LeahSyncTimeout

    monkeypatch.setattr(
        app_main.leah_cloud, "authenticate_device",
        lambda authorization: {"id": "device-1", "owner_email": "eduardo@example.com"},
    )
    outcomes = iter([
        LeahSyncTimeout("prazo", retry_after=30),
        LeahSyncBusy("ocupado", retry_after=30),
        {"cursor": datetime.now(timezone.utc), "items": []},
    ])

    def fake_run(identity, body, work):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(app_main.leah_sync_guard, "run", fake_run)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer device-token"}
        timeout = client.post("/api/v1/leah/agent/sync", json={"items": []}, headers=headers)
        busy = client.post("/api/v1/leah/agent/sync", json={"items": []}, headers=headers)
        ok = client.post("/api/v1/leah/agent/sync", json={"items": []}, headers=headers)

    assert timeout.status_code == 504
    assert timeout.headers["retry-after"] == "30"
    assert busy.status_code == 503
    assert busy.headers["retry-after"] == "30"
    assert ok.status_code == 200
    assert ok.json()["items"] == []


def test_command_center_without_include_keeps_the_legacy_contract(monkeypatch) -> None:
    calls = {"health": 0}
    real = app_main.system_health.snapshot

    def counted():
        calls["health"] += 1
        return real()

    monkeypatch.setattr(app_main.system_health, "snapshot", counted)
    with TestClient(app) as client:
        response = client.get("/api/v1/command-center")
    assert response.status_code == 200
    payload = response.json()
    assert payload["sections"] is None
    assert payload["section_status"] == {}
    assert calls == {"health": 0}


def test_command_center_aggregate_isolates_a_failing_section(monkeypatch) -> None:
    def broken():
        raise RuntimeError("probe timeout storm")

    monkeypatch.setattr(app_main.system_health, "snapshot", broken)
    app_main.command_center_cache.invalidate()
    app_main.r2d2_read_cache.invalidate()
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/command-center",
            params={"include": "alerts,navigation_indicators,system_health,reports,market_data_providers,r2d2,markets_live,markets_index"},
        )
    app_main.command_center_cache.invalidate()
    assert response.status_code == 200
    payload = response.json()
    statuses = payload["section_status"]
    assert set(statuses) == {
        "alerts", "navigation_indicators", "system_health", "reports",
        "market_data_providers", "r2d2", "markets_live", "markets_index",
    }
    assert statuses["system_health"]["status"] == "error"
    assert "probe timeout storm" in statuses["system_health"]["error"]
    assert payload["sections"]["system_health"] is None
    assert statuses["reports"]["status"] == "ok"
    assert isinstance(payload["sections"]["reports"], list)
    assert statuses["r2d2"]["status"] == "ok"
    assert payload["sections"]["r2d2"]["starting_capital_usd"] == 1_000_000
    assert statuses["alerts"]["status"] == "ok"
    assert "unread_count" in payload["sections"]["alerts"]
    for name, item in statuses.items():
        assert item["status"] in {"ok", "error", "skipped"}, name
        assert item["duration_ms"] >= 0
    assert payload["report_title"].endswith(datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y"))


def test_command_center_aggregate_rejects_unknown_sections() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/command-center", params={"include": "alerts,shell_exec"})
    assert response.status_code == 422


def test_command_center_aggregate_cache_is_segregated_by_actor_and_permissions(monkeypatch) -> None:
    calls = {"reports": 0}
    real_history = app_main.legacy.report_history

    def counted():
        calls["reports"] += 1
        return real_history()

    monkeypatch.setattr(app_main.legacy, "report_history", counted)
    actors = {
        "owner": {"email": "owner@example.com", "permissions": ["command", "alerts", "candidates"], "role": "owner"},
        "member": {"email": "member@example.com", "permissions": ["command"], "role": "member"},
    }
    current = {"key": "owner"}
    monkeypatch.setattr(app_main, "current_access_actor", lambda request: actors[current["key"]])
    monkeypatch.setattr(app_main.command_center_cache, "_ttl_seconds", lambda: 60.0)
    app_main.command_center_cache.invalidate()
    with TestClient(app) as client:
        first = client.get("/api/v1/command-center", params={"include": "reports,alerts"})
        second = client.get("/api/v1/command-center", params={"include": "reports,alerts"})
        current["key"] = "member"
        third = client.get("/api/v1/command-center", params={"include": "reports,alerts"})
    app_main.command_center_cache.invalidate()
    assert first.status_code == second.status_code == third.status_code == 200
    assert calls["reports"] == 2  # owner computed once (cached), member computed once
    assert first.json()["section_status"]["alerts"]["status"] == "ok"
    assert third.json()["section_status"]["alerts"]["status"] == "skipped"  # no 'alerts' permission
    assert third.json()["sections"]["alerts"] is None
