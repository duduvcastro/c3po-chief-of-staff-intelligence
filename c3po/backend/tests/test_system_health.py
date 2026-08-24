from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.schemas import (
    IntegrationHealth,
    MarketDataProviderHealth,
    ServerUsageCurrent,
    ServerUsageResponse,
    ServerUsageServer,
)
from app.system_health import SystemHealthService


class _Cursor:
    def fetchone(self):
        return (1,)


class _Connection:
    def execute(self, _query: str):
        return _Cursor()


class _Database:
    def __init__(
        self,
        now: datetime,
        *,
        pre_ab_ready: bool = True,
        snapshot_published_at: datetime | None = None,
        include_peer_snapshots: bool = True,
    ) -> None:
        self.now = now
        self.pre_ab_ready = pre_ab_ready
        self.snapshot_published_at = snapshot_published_at or now
        self.include_peer_snapshots = include_peer_snapshots

    @contextmanager
    def connection(self):
        yield _Connection()

    def ir_source_health(self):
        now = datetime.now(timezone.utc)
        return {
            "cvm": {"last_status": "succeeded", "last_success_at": now, "last_error": None},
            "sec": {"last_status": "succeeded", "last_success_at": now, "last_error": None},
            "ri": {"last_status": "succeeded", "last_success_at": now, "last_error": None},
        }

    def latest_analysis_snapshot_outputs(
        self,
        analysis_type: str,
        entity_keys: list[str],
        output_key: str,
    ):
        if analysis_type != "valuation_v2_peer_quality" or not self.include_peer_snapshots:
            return {}
        assert output_key == "pre_ab_report"
        gates = {
            "target_schema_current": self.pre_ab_ready,
            "target_roe_non_null": True,
            "closure_fully_attempted": True,
            "chewie_snapshot_new_since_rejected_ab": True,
            "fmp_forward_structural_eligibility_nonzero": True,
        }
        return {
            key: {
                "published_at": self.snapshot_published_at,
                "output": {
                    "gates": dict(gates),
                    "pre_ab_ready": self.pre_ab_ready,
                },
            }
            for key in entity_keys
        }


class _Legacy:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def read(self):
        return {
            "generated_at": self.now,
            "integrations": [
                IntegrationHealth(name="AWS cron", status="healthy", detail="ultima execucao 16/08 19:00", last_update="16/08 19:00"),
                IntegrationHealth(name="Email", status="healthy", detail="ok", last_update="16/08 19:00"),
                IntegrationHealth(name="PDF enviado", status="healthy", detail="sim", last_update="16/08 19:00"),
                IntegrationHealth(name="WhatsApp", status="healthy", detail="ok", last_update="16/08 19:00"),
            ],
        }


class _OpenFinance:
    def integration_health(self):
        return [
            IntegrationHealth(name="Pluggy API", status="healthy", detail="authenticated", last_update="16/08 19:00"),
            IntegrationHealth(name="BTG Pactual", status="healthy", detail="synced", last_update="16/08 19:00"),
            IntegrationHealth(name="Santander", status="healthy", detail="synced", last_update="16/08 19:00"),
            IntegrationHealth(name="Itaú", status="healthy", detail="synced", last_update="16/08 19:00"),
        ]


class _MarketData:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def health(self):
        return [
            MarketDataProviderHealth(code="brapi", name="Brapi", market="Brazil / B3", configured=True, plan="pro", status="healthy", last_success_at=self.now),
            MarketDataProviderHealth(code="eodhd", name="EODHD", market="United States / Global", configured=True, plan="all-in-one", status="healthy", last_success_at=self.now),
        ]


class _ServerUsage:
    def __init__(self, now: datetime, disk_percent: float = 62.0) -> None:
        self.now = now
        self.disk_percent = disk_percent

    def snapshot(self, *, hours: int):
        assert hours == 1
        return ServerUsageResponse(
            generated_at=self.now,
            window_hours=hours,
            moving_average_minutes=5,
            refresh_seconds=60,
            servers=[ServerUsageServer(
                server_id="lightsail",
                server_name="Chief of Staff Intelligence",
                region="São Paulo · sa-east-1",
                cpu_count=2,
                status="healthy",
                current=ServerUsageCurrent(
                    cpu_percent=18.0,
                    cpu_moving_average_5m=16.0,
                    disk_percent=self.disk_percent,
                    disk_total_bytes=100,
                    disk_used_bytes=62,
                    disk_free_bytes=38,
                    collected_at=self.now,
                ),
                history=[],
            )],
            methodology={},
        )


class _ExternalResponse:
    def __init__(self, *, cloudflare: bool = False, usage: bool = False) -> None:
        self.status_code = 200
        self.headers = {"server": "cloudflare", "cf-ray": "test-GRU"} if cloudflare else {}
        self.text = "User-agent: *\nDisallow: /" if cloudflare else "{}"
        self.usage = usage

    def raise_for_status(self):
        return None

    def json(self):
        return {"apiRequests": 60_000, "dailyRateLimit": 100_000} if self.usage else {}


def _external_get(url: str, **_kwargs):
    assert "/api/api/" not in url
    return _ExternalResponse(cloudflare="robots.txt" in url, usage="/api/user/" in url)


class _BackblazeClient:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.requested_bucket = None

    def head_bucket(self, *, Bucket: str):
        self.requested_bucket = Bucket
        if self.error:
            raise self.error
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}


def _service(
    *,
    disk_percent: float = 62.0,
    eodhd_base_url: str = "https://eodhd.com",
    day_d_root: Path = Path("/__c3po_system_health_day_d_test__"),
    day_d_free_gib: float = 30.0,
    pre_ab_ready: bool = True,
    snapshot_published_at: datetime | None = None,
    include_peer_snapshots: bool = True,
) -> SystemHealthService:
    now = datetime.now(timezone.utc)
    settings = Settings(
        database_url="postgresql://configured",
        exchange_server="east.EXCH025.serverdata.net",
        exchange_user="eu@eduardocastro.com.br",
        exchange_app_password="configured",
        eodhd_api_token="configured",
        eodhd_base_url=eodhd_base_url,
        finnhub_api_token="configured",
        fmp_api_token="configured",
        massive_api_token="configured",
        day_d_b2_key_id="configured-key-id",
        day_d_b2_application_key="configured-application-key",
        day_d_b2_bucket="c3po-day-d-cold-test",
        day_d_dataset_root=day_d_root,
        server_usage_disk_warning_percent=70,
        server_usage_cpu_peak_warning_percent=85,
    )
    return SystemHealthService(
        settings,
        _Database(
            now,
            pre_ab_ready=pre_ab_ready,
            snapshot_published_at=snapshot_published_at,
            include_peer_snapshots=include_peer_snapshots,
        ),
        _Legacy(now),
        _OpenFinance(),
        _MarketData(now),
        _ServerUsage(now, disk_percent),
        cache_seconds=0,
        external_get=_external_get,
        backblaze_client=_BackblazeClient(),
        disk_usage=lambda _path: SimpleNamespace(free=int(day_d_free_gib * 1024**3)),
    )


def test_consolidated_health_covers_every_operational_area() -> None:
    response = _service().snapshot(force=True)

    assert [group.key for group in response.groups] == ["apis", "external_services", "open_finance", "aws", "controls", "quotes", "official_sources", "automations"]
    assert response.status == "healthy"
    assert response.quality == 100
    assert all(group.status == "healthy" for group in response.groups)
    assert {item.name for group in response.groups for item in group.items} >= {
        "C3PO API", "PostgreSQL", "Daily API Usage", "Cloudflare", "GitHub / CI-CD", "Intermedia Exchange", "Backblaze B2", "Open-Meteo", "Pluggy API", "BTG Pactual", "Santander", "Itaú", "Brapi", "EODHD", "Finnhub", "FMP", "Massive", "CVM Dados Abertos", "SEC EDGAR", "Issuer RI", "AWS scheduler", "Valuation V2.1b cycle", "V3 pre-A/B gate", "Day D disk reserve", "B2 zero-cap evidence",
    }
    assert "WhatsApp capture" not in {item.name for group in response.groups for item in group.items}


def test_resource_pressure_marks_aws_and_overall_health_for_review() -> None:
    response = _service(disk_percent=76.0).snapshot(force=True)

    aws = next(group for group in response.groups if group.key == "aws")
    assert aws.status == "attention"
    assert response.status == "attention"
    assert response.quality < 100


def test_day_d_and_valuation_controls_are_visible_and_healthy() -> None:
    response = _service().snapshot(force=True)

    controls = next(group for group in response.groups if group.key == "controls")
    assert controls.status == "healthy"
    assert controls.healthy_count == 4
    assert {item.name for item in controls.items} == {
        "Valuation V2.1b cycle",
        "V3 pre-A/B gate",
        "Day D disk reserve",
        "B2 zero-cap evidence",
    }


def test_pre_ab_gate_is_red_when_any_frozen_gate_fails() -> None:
    response = _service(pre_ab_ready=False).snapshot(force=True)

    gate = next(
        item
        for group in response.groups
        for item in group.items
        if item.name == "V3 pre-A/B gate"
    )
    assert gate.status == "offline"
    assert "target_schema_current" in gate.detail


def test_v2_1b_cycle_is_red_after_the_window_when_snapshots_are_stale() -> None:
    published = datetime(2026, 8, 22, 4, 0, tzinfo=timezone.utc)
    now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    service = _service(snapshot_published_at=published)

    cycle = next(
        item
        for item in service._valuation_v2_1b_health(now)
        if item.name == "Valuation V2.1b cycle"
    )
    assert cycle.status == "offline"
    assert "B3" in cycle.detail
    assert "US" in cycle.detail


def test_first_v2_1b_cycle_without_evidence_is_pending_not_falsely_red() -> None:
    service = _service(include_peer_snapshots=False)

    cycle, gate = service._valuation_v2_1b_health(
        datetime(2026, 8, 24, 2, 0, tzinfo=timezone.utc)
    )

    assert cycle.status == "attention"
    assert "First V2.1b evidence pending" in cycle.detail
    assert gate.status == "attention"


def test_day_d_disk_reserve_is_red_below_the_frozen_20_gib() -> None:
    response = _service(day_d_free_gib=19.99).snapshot(force=True)

    reserve = next(
        item
        for group in response.groups
        for item in group.items
        if item.name == "Day D disk reserve"
    )
    assert reserve.status == "offline"
    assert "20.0 GiB" in reserve.detail


def test_b2_cap_stays_red_until_exact_zero_evidence_is_chained(tmp_path: Path) -> None:
    measured_at = datetime(2026, 8, 23, 18, 6, tzinfo=timezone.utc)
    lot_id = "qualification-2024-12-24"
    raw_path = (
        tmp_path
        / "provider=backblaze"
        / "raw-restore-reports"
        / f"lot_id={lot_id}"
        / "raw-restore-test.json"
    )
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text(json.dumps({
        "schema_version": "DAY-D-B2-RAW-RESTORE-v1",
        "lot_id": lot_id,
        "measured_at": measured_at.isoformat(),
        "passed": True,
        "restored_sample_removed": True,
    }), encoding="utf-8")
    service = _service(day_d_root=tmp_path)

    pending = service._b2_zero_cap_health(measured_at + timedelta(minutes=5))

    assert pending.status == "offline"
    assert "deletion remains blocked" in pending.detail

    cap_path = (
        tmp_path
        / "provider=backblaze"
        / "billing-cap-evidence"
        / f"lot_id={lot_id}"
        / "billing-cap-test.json"
    )
    cap_path.parent.mkdir(parents=True)
    raw_sha = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    cap_path.write_text(json.dumps({
        "schema_version": "DAY-D-B2-BILLING-CAP-v1",
        "lot_id": lot_id,
        "measured_at": (measured_at + timedelta(minutes=10)).isoformat(),
        "operator_attestation": True,
        "raw_restore_report": {"path": str(raw_path.resolve()), "sha256": raw_sha},
        "original_cap_usd_per_day": 0.0,
        "temporary_cap_usd_per_day": 0.5,
        "final_cap_usd_per_day": 0.0,
        "restored_at": (measured_at + timedelta(minutes=9)).isoformat(),
    }), encoding="utf-8")

    restored = service._b2_zero_cap_health(measured_at + timedelta(minutes=11))

    assert restored.status == "healthy"
    assert "Exact US$0/day restoration evidenced" in restored.detail


def test_missing_daily_api_usage_counter_prevents_full_readiness() -> None:
    service = _service()
    service.settings.eodhd_api_token = ""

    response = service.snapshot(force=True)

    usage = next(item for group in response.groups for item in group.items if item.name == "Daily API Usage")
    assert usage.status == "attention"
    assert response.status == "attention"
    assert response.quality == 96
    assert response.healthy_count == 27
    assert response.total_count == 28


def test_finnhub_is_monitored_in_market_quotes() -> None:
    response = _service().snapshot(force=True)

    quotes = next(group for group in response.groups if group.key == "quotes")
    finnhub = next(item for item in quotes.items if item.name == "Finnhub")
    assert finnhub.status == "healthy"
    assert "Fundamental-1" in finnhub.detail


def test_fmp_is_monitored_in_market_quotes() -> None:
    response = _service().snapshot(force=True)

    quotes = next(group for group in response.groups if group.key == "quotes")
    fmp = next(item for item in quotes.items if item.name == "FMP")
    assert fmp.status == "healthy"
    assert "Ultimate" in fmp.detail
    assert quotes.total_count == 5


def test_fmp_is_offline_without_a_configured_credential() -> None:
    service = _service()
    service.settings.fmp_api_token = ""

    response = service.snapshot(force=True)

    quotes = next(group for group in response.groups if group.key == "quotes")
    fmp = next(item for item in quotes.items if item.name == "FMP")
    assert fmp.status == "offline"
    assert "not configured" in fmp.detail


def test_massive_is_monitored_in_market_quotes() -> None:
    response = _service().snapshot(force=True)

    quotes = next(group for group in response.groups if group.key == "quotes")
    massive = next(item for item in quotes.items if item.name == "Massive")
    assert massive.status == "healthy"
    assert "Stocks Advanced" in massive.detail
    assert "SIP replay reference" in massive.detail


def test_massive_is_offline_without_a_configured_credential() -> None:
    service = _service()
    service.settings.massive_api_token = ""

    response = service.snapshot(force=True)

    quotes = next(group for group in response.groups if group.key == "quotes")
    massive = next(item for item in quotes.items if item.name == "Massive")
    assert massive.status == "offline"
    assert "not configured" in massive.detail


def test_backblaze_is_monitored_as_a_contracted_service() -> None:
    service = _service()

    response = service.snapshot(force=True)

    external = next(group for group in response.groups if group.key == "external_services")
    backblaze = next(item for item in external.items if item.name == "Backblaze B2")
    assert backblaze.status == "healthy"
    assert "private bucket access confirmed" in backblaze.detail
    assert service.backblaze_client.requested_bucket == "c3po-day-d-cold-test"


def test_backblaze_is_offline_without_credentials() -> None:
    service = _service()
    service.settings.day_d_b2_application_key = ""

    response = service.snapshot(force=True)

    backblaze = next(item for group in response.groups for item in group.items if item.name == "Backblaze B2")
    assert backblaze.status == "offline"
    assert "not configured" in backblaze.detail


def test_backblaze_reports_bucket_access_failure_without_leaking_credentials() -> None:
    service = _service()
    service.backblaze_client = _BackblazeClient(error=RuntimeError("applicationKey=super-secret failed"))

    response = service.snapshot(force=True)

    backblaze = next(item for group in response.groups for item in group.items if item.name == "Backblaze B2")
    assert backblaze.status == "offline"
    assert "super-secret" not in backblaze.detail


def test_health_error_redacts_market_data_credentials() -> None:
    error = RuntimeError("GET https://api.massive.com/v1/status?apiKey=secret-value&x=1 failed")

    assert "secret-value" not in SystemHealthService._safe_error(error)
    assert "apiKey=[redacted]" in SystemHealthService._safe_error(error)


def test_daily_api_usage_accepts_base_url_that_already_contains_api_path() -> None:
    response = _service(eodhd_base_url="https://eodhd.com/api").snapshot(force=True)

    assert response.api_usage[0].provider == "EODHD"
    assert response.api_usage[0].percent_used == 60.0


def test_high_api_consumption_does_not_mark_operational_connection_unhealthy() -> None:
    service = _service()

    def high_usage_get(url: str, **_kwargs):
        response = _ExternalResponse(cloudflare="robots.txt" in url, usage=False)
        if "/api/user/" in url:
            response.json = lambda: {"apiRequests": 95_000, "dailyRateLimit": 100_000}
        return response

    service.external_get = high_usage_get
    response = service.snapshot(force=True)

    assert response.api_usage[0].status == "critical"
    usage_health = next(item for group in response.groups for item in group.items if item.name == "Daily API Usage")
    assert usage_health.status == "healthy"
    assert response.status == "healthy"
    assert response.quality == 100


def test_ai_usage_reports_setup_requirements_without_admin_credentials() -> None:
    service = _service()
    service.settings.anthropic_api_key = "runtime-configured"

    response = service.snapshot(force=True)

    openai, anthropic = response.ai_usage
    assert openai.provider == "OpenAI"
    assert openai.status == "unavailable"
    assert "Admin API key" in openai.detail
    assert anthropic.provider == "Anthropic"
    assert anthropic.status == "unavailable"
    assert "runtime key connected" in anthropic.detail
    assert response.quality == 100


def test_ai_usage_aggregates_official_provider_reports() -> None:
    service = _service()
    service.settings.openai_admin_api_key = "openai-admin"
    service.settings.anthropic_admin_api_key = "anthropic-admin"

    def usage_get(url: str, **_kwargs):
        response = _ExternalResponse(usage="/api/user/" in url)
        if "openai.com" in url:
            response.json = lambda: {"data": [{"results": [{
                "model": "gpt-5-codex", "input_tokens": 12_000,
                "output_tokens": 3_000, "input_cached_tokens": 5_000,
                "num_model_requests": 18,
            }]}]}
        elif "anthropic.com" in url:
            response.json = lambda: {"data": [{"results": [{
                "model": "claude-sonnet-4", "uncached_input_tokens": 7_000,
                "cache_read_input_tokens": 2_000,
                "cache_creation": {"ephemeral_5m_input_tokens": 1_000},
                "output_tokens": 4_000,
            }]}]}
        return response

    service.external_get = usage_get
    response = service.snapshot(force=True)

    openai, anthropic = response.ai_usage
    assert openai.status == "healthy"
    assert openai.input_tokens == 12_000
    assert openai.output_tokens == 3_000
    assert openai.cached_input_tokens == 5_000
    assert openai.requests == 18
    assert anthropic.status == "healthy"
    assert anthropic.input_tokens == 10_000
    assert anthropic.output_tokens == 4_000
    assert anthropic.cached_input_tokens == 3_000
