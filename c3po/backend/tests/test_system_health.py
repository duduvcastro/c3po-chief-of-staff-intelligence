from contextlib import contextmanager
from datetime import datetime, timezone

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
                server_name="Chief of Staff Digital",
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
    def __init__(self, *, cloudflare: bool = False) -> None:
        self.status_code = 200
        self.headers = {"server": "cloudflare", "cf-ray": "test-GRU"} if cloudflare else {}
        self.text = "User-agent: *\nDisallow: /" if cloudflare else "{}"


def _external_get(url: str, **_kwargs):
    return _ExternalResponse(cloudflare="robots.txt" in url)


def _service(*, disk_percent: float = 62.0) -> SystemHealthService:
    now = datetime.now(timezone.utc)
    settings = Settings(
        database_url="postgresql://configured",
        exchange_server="east.EXCH025.serverdata.net",
        exchange_user="eu@eduardocastro.com.br",
        exchange_app_password="configured",
        server_usage_disk_warning_percent=70,
        server_usage_cpu_peak_warning_percent=85,
    )
    return SystemHealthService(
        settings,
        _Database(),
        _Legacy(now),
        _OpenFinance(),
        _MarketData(now),
        _ServerUsage(now, disk_percent),
        cache_seconds=0,
        external_get=_external_get,
    )


def test_consolidated_health_covers_every_operational_area() -> None:
    response = _service().snapshot(force=True)

    assert [group.key for group in response.groups] == ["apis", "external_services", "open_finance", "aws", "quotes", "official_sources", "automations"]
    assert response.status == "healthy"
    assert response.quality == 100
    assert all(group.status == "healthy" for group in response.groups)
    assert {item.name for group in response.groups for item in group.items} >= {
        "C3PO API", "PostgreSQL", "Cloudflare", "GitHub / CI-CD", "Intermedia Exchange", "Open-Meteo", "Pluggy API", "BTG Pactual", "Santander", "Itaú", "Brapi", "EODHD", "CVM Dados Abertos", "SEC EDGAR", "Issuer RI", "AWS scheduler",
    }
    assert "WhatsApp capture" not in {item.name for group in response.groups for item in group.items}


def test_resource_pressure_marks_aws_and_overall_health_for_review() -> None:
    response = _service(disk_percent=76.0).snapshot(force=True)

    aws = next(group for group in response.groups if group.key == "aws")
    assert aws.status == "attention"
    assert response.status == "attention"
    assert response.quality < 100
