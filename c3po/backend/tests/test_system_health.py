from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace

from app.config import Settings
from app.governance_vulnerability import report_sha256
from app.schemas import (
    IntegrationHealth,
    MarketDataProviderHealth,
    ServerUsageCurrent,
    ServerUsageResponse,
    ServerUsageServer,
)
from app.system_health import SystemHealthService
from app.valuation_worker_contract import VALUATION_WORKER_PHASES


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
        valuation_phase_states: dict[str, dict] | None = None,
    ) -> None:
        self.now = now
        self.pre_ab_ready = pre_ab_ready
        self.snapshot_published_at = snapshot_published_at or now
        self.include_peer_snapshots = include_peer_snapshots
        self.valuation_phase_states = valuation_phase_states or {
            definition["code"]: {
                "last_status": "succeeded",
                "started_at": now,
                "completed_at": now,
                "last_success_at": now,
                "last_error": None,
                "metadata": {"phase": phase},
            }
            for phase, definition in VALUATION_WORKER_PHASES.items()
        }

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

    def ingestion_run_health(self, source_codes: list[str]):
        return {
            code: self.valuation_phase_states[code]
            for code in source_codes
            if code in self.valuation_phase_states
        }

    def latest_governance_vulnerability_report(self):
        report = {
            "schema": "C3PO_GOVERNANCE_VULNERABILITY_REPORT-v2",
            "session_date": self.now.date().isoformat(),
            "repository": "duduvcastro/c3po-chief-of-staff-intelligence",
            "branch": "main",
            "generated_at": self.now.isoformat(),
            "baseline": {"schema": "baseline-v1", "sha256": "a" * 64},
            "dependabot": {
                "status": "healthy",
                "open_total": 0,
                "by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            },
            "operating_system": {
                "status": "healthy",
                "available": True,
                "security_updates_pending": 0,
                "all_updates_pending": 3,
                "reboot_required": False,
                "generated_at": self.now.isoformat(),
            },
            "production_images": {
                "status": "healthy",
                "available": True,
                "finding_total": 0,
                "by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                "image_count": 3,
                "generated_at": self.now.isoformat(),
            },
            "remediation_lanes": {
                "status": "healthy",
                "available": True,
                "count": 0,
                "items": [],
            },
            "known_vulnerabilities": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "governance": {
                "status": "healthy",
                "checks": [{
                    "key": "branch_protection_enabled",
                    "label": "Branch protection",
                    "status": "healthy",
                    "expected": True,
                    "actual": True,
                }],
                "drift": [],
            },
            "status": "healthy",
        }
        report["report_sha256"] = report_sha256(report)
        return report

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
    def integration_health(self, *, timeout_seconds: float | None = None):
        assert timeout_seconds == 2.0
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

    def probe_health(self):
        raise AssertionError("system-health must read persisted provider state")


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


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _seal_result(path: Path, payload: dict) -> None:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sealed = {**payload, "self_sha256": hashlib.sha256(canonical).hexdigest()}
    _write_json(path, sealed)


def _write_resilience_evidence(root: Path, now: datetime) -> None:
    backup_root = root / "outputs/evidence/postgres-backup/2026-08-27/20260827T070000Z"
    upload = {
        "schema": "C3PO_POSTGRES_BACKUP_UPLOAD-v1",
        "session_date": "2026-08-27",
        "uploaded_at": now.isoformat(),
        "file_size": 1234,
        "file_sha256": "a" * 64,
        "bucket": "c3po-postgres-test",
        "region": "us-east-1",
        "endpoint_configured": False,
        "uploads": [{"key": "c3po-postgres/daily/2026-08-27/a.dump", "version_id": "v1"}],
    }
    result = {
        "schema": "C3PO_POSTGRES_BACKUP_RESULT-v1",
        "status": "succeeded",
        "completed_at": now.isoformat(),
        "dump_sha256": upload["file_sha256"],
        "upload_count": 1,
        "uploads": upload["uploads"],
    }
    _write_json(backup_root / "upload.json", upload)
    _seal_result(backup_root / "result.json", result)
    (backup_root / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256((backup_root / name).read_bytes()).hexdigest()}  {name}\n"
            for name in ("upload.json", "result.json")
        ),
        encoding="utf-8",
    )

    restore_root = root / "outputs/evidence/postgres-restore-drill/2026-08-27/12345"
    restore = {
        "schema": "C3PO_POSTGRES_RESTORE_DRILL-v1",
        "status": "succeeded",
        "completed_at": now.isoformat(),
        "backup_session_date": "2026-08-27",
        "object_key": upload["uploads"][0]["key"],
        "backup_sha256": upload["file_sha256"],
        "backup_size_bytes": 1234,
        "pg_restore_list_valid": True,
        "restored_public_table_count": 100,
        "critical_tables_present": 5,
    }
    _seal_result(restore_root / "result.json", restore)
    (restore_root / "SHA256SUMS").write_text(
        f"{hashlib.sha256((restore_root / 'result.json').read_bytes()).hexdigest()}  result.json\n",
        encoding="utf-8",
    )


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
    valuation_phase_states: dict[str, dict] | None = None,
) -> SystemHealthService:
    now = datetime.now(timezone.utc)
    temporary_directory = TemporaryDirectory(prefix="c3po-system-health-")
    legacy_root = Path(temporary_directory.name)
    _write_resilience_evidence(legacy_root, now)
    settings = Settings(
        database_url="postgresql://configured",
        legacy_root=legacy_root,
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
        sentry_dsn="https://public@example.ingest.sentry.io/123",
        healthcheck_valuation_worker_url="https://hc-ping.com/valuation",
        healthcheck_cash_yield_url="https://hc-ping.com/cash-yield",
        healthcheck_code_census_url="https://hc-ping.com/code-census",
        healthcheck_postgres_backup_url="https://hc-ping.com/postgres-backup",
        healthcheck_governance_url="https://hc-ping.com/governance",
        healthcheck_postgres_restore_configured=True,
        healthcheck_trivy_configured=True,
        healthcheck_unattended_upgrades_configured=True,
        postgres_backup_bucket="c3po-postgres-test",
        postgres_backup_region="us-east-1",
        postgres_backup_access_key_id="configured-writer",
        postgres_backup_secret_access_key="configured-secret",
        day_d_dataset_root=day_d_root,
        server_usage_disk_warning_percent=70,
        server_usage_cpu_peak_warning_percent=85,
    )
    service = SystemHealthService(
        settings,
        _Database(
            now,
            pre_ab_ready=pre_ab_ready,
            snapshot_published_at=snapshot_published_at,
            include_peer_snapshots=include_peer_snapshots,
            valuation_phase_states=valuation_phase_states,
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
    service._test_temporary_directory = temporary_directory
    return service


def test_consolidated_health_covers_every_operational_area() -> None:
    response = _service().snapshot(force=True)

    assert [group.key for group in response.groups] == ["apis", "external_services", "open_finance", "aws", "controls", "governance", "quotes", "official_sources", "automations"]
    assert response.status == "healthy"
    assert response.quality == 100
    assert all(group.status == "healthy" for group in response.groups)
    assert {item.name for group in response.groups for item in group.items} >= {
        "C3PO API", "PostgreSQL", "Daily API Usage", "Cloudflare", "GitHub / CI-CD", "Intermedia Exchange", "Backblaze B2", "Healthchecks.io", "Sentry", "Open-Meteo", "Pluggy API", "BTG Pactual", "Santander", "Itaú", "Brapi", "EODHD", "Finnhub", "FMP", "Massive", "CVM Dados Abertos", "SEC EDGAR", "Issuer RI", "PostgreSQL offsite backup", "AWS scheduler", "Governança & Vulnerabilidades", "Valuation worker phases", "Valuation V2.1b cycle", "V3 pre-A/B gate", "Day D disk reserve", "B2 zero-cap evidence",
    }
    assert "WhatsApp capture" not in {item.name for group in response.groups for item in group.items}


def test_resource_pressure_marks_aws_and_overall_health_for_review() -> None:
    response = _service(disk_percent=76.0).snapshot(force=True)

    aws = next(group for group in response.groups if group.key == "aws")
    assert aws.status == "attention"
    assert response.status == "attention"
    assert response.quality < 100


def test_resilience_services_are_monitored_with_distinct_evidence() -> None:
    response = _service().snapshot(force=True)

    items = {item.name: item for group in response.groups for item in group.items}
    assert items["Healthchecks.io"].status == "healthy"
    assert "8/8 dead-man checks configured" in items["Healthchecks.io"].detail
    assert items["Sentry"].status == "healthy"
    assert "DSN loaded" in items["Sentry"].detail
    assert items["PostgreSQL offsite backup"].status == "healthy"
    assert "Immutable S3 upload evidenced" in items["PostgreSQL offsite backup"].detail
    assert "restore drill verified" in items["PostgreSQL offsite backup"].detail


def test_healthchecks_is_offline_until_all_eight_checks_are_configured() -> None:
    service = _service()
    service.settings.healthcheck_governance_url = ""

    item = service._healthchecks_health(datetime.now(timezone.utc))

    assert item.status == "offline"
    assert "7/8 checks configured" in item.detail


def test_sentry_is_offline_without_an_official_dsn() -> None:
    service = _service()
    service.settings.sentry_dsn = "https://example.invalid/123"

    item = service._sentry_health(datetime.now(timezone.utc))

    assert item.status == "offline"
    assert "not configured" in item.detail


def test_postgres_backup_is_attention_before_first_sealed_upload() -> None:
    service = _service()
    evidence_root = service.settings.legacy_root / "outputs/evidence/postgres-backup"
    shutil.rmtree(evidence_root)

    item = service._postgres_backup_health(datetime.now(timezone.utc))

    assert item.status == "attention"
    assert "first sealed upload pending" in item.detail


def test_postgres_backup_fails_closed_on_a_tampered_result() -> None:
    service = _service()
    result_path = next(
        (service.settings.legacy_root / "outputs/evidence/postgres-backup").glob("*/*/result.json")
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["upload_count"] = 2
    _write_json(result_path, payload)

    item = service._postgres_backup_health(datetime.now(timezone.utc))

    assert item.status == "offline"
    assert "invalid" in item.detail


def test_postgres_backup_fails_closed_when_latest_attempt_has_no_result() -> None:
    service = _service()
    failed_run = (
        service.settings.legacy_root
        / "outputs/evidence/postgres-backup/2026-08-28/20260828T070000Z"
    )
    _write_json(failed_run / "preflight.json", {"status": "started"})

    item = service._postgres_backup_health(datetime.now(timezone.utc))

    assert item.status == "offline"
    assert "did not produce a sealed result" in item.detail


def test_day_d_and_valuation_controls_are_visible_and_healthy() -> None:
    response = _service().snapshot(force=True)

    controls = next(group for group in response.groups if group.key == "controls")
    assert controls.status == "healthy"
    assert controls.healthy_count == 5
    assert {item.name for item in controls.items} == {
        "Valuation worker phases",
        "Valuation V2.1b cycle",
        "V3 pre-A/B gate",
        "Day D disk reserve",
        "B2 zero-cap evidence",
    }


def test_governance_card_exposes_counts_contract_and_hash_metadata() -> None:
    response = _service().snapshot(force=True)
    governance = next(group for group in response.groups if group.key == "governance")
    assert governance.label == "Governança & Vulnerabilidades"
    assert governance.healthy_count == 2
    assert governance.total_count == 2
    item = governance.items[0]

    assert item.status == "healthy"
    assert item.detail == "Baseline íntegra · repo 0 · SO 0 · imagens 0"
    assert item.metadata["operating_system"]["reboot_required"] is False
    assert item.metadata["production_images"]["image_count"] == 3
    assert item.metadata["kind"] == "governance_vulnerabilities"
    assert item.metadata["dependabot"]["by_severity"]["critical"] == 0
    assert item.metadata["remediation_lanes"]["count"] == 0
    assert item.metadata["governance_checks"][0]["label"] == "Branch protection"


def test_governance_card_never_converts_unverifiable_lanes_to_zero() -> None:
    service = _service()
    original = service.database.latest_governance_vulnerability_report

    def unavailable_report():
        report = original()
        report["remediation_lanes"] = {
            "status": "attention",
            "available": False,
            "count": None,
            "items": None,
            "error": "GitHub remediation lane query is not verifiable",
        }
        report["report_sha256"] = report_sha256(report)
        return report

    service.database.latest_governance_vulnerability_report = unavailable_report  # type: ignore[method-assign]

    item = service._governance_vulnerability_health(datetime.now(timezone.utc))

    assert item.status == "attention"
    assert item.detail.startswith("Lanes de remediação não verificáveis")
    assert item.metadata["remediation_lanes"]["count"] is None


def test_governance_card_describes_the_daily_window_without_claiming_fixed_schedule() -> None:
    service = _service()
    service.database.latest_governance_vulnerability_report = lambda: None  # type: ignore[method-assign]

    item = service._governance_vulnerability_health(datetime.now(timezone.utc))

    assert item.status == "attention"
    assert item.detail == (
        "Primeiro atestado diário pendente · diário a partir de 02:15 BRT"
    )


def test_valuation_worker_phase_failure_is_persistently_visible() -> None:
    now = datetime.now(timezone.utc)
    states = {
        definition["code"]: {
            "last_status": "succeeded",
            "started_at": now,
            "completed_at": now,
            "last_success_at": now,
            "last_error": None,
            "metadata": {"phase": phase},
        }
        for phase, definition in VALUATION_WORKER_PHASES.items()
    }
    failed_code = VALUATION_WORKER_PHASES["v2_data"]["code"]
    states[failed_code] = {
        **states[failed_code],
        "last_status": "failed",
        "last_error": "RuntimeError: provider unavailable",
    }
    service = _service(valuation_phase_states=states)

    item = service._valuation_worker_phase_health(now)

    assert item.status == "offline"
    assert "v2_data" in item.detail
    assert "provider unavailable" in item.detail


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
    assert response.quality == 97
    assert response.healthy_count == 33
    assert response.total_count == 34


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


def test_external_timeout_is_unknown_not_falsely_offline() -> None:
    service = _service()

    item = service._offline_item(
        "Slow provider",
        TimeoutError("read operation timed out"),
        datetime.now(timezone.utc),
    )

    assert item.status == "attention"
    assert "Status unknown" in item.detail
    assert item.metadata["probe_status"] == "timed_out"


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


def test_slow_probe_degrades_only_its_card_within_two_second_budget() -> None:
    service = _service()
    service.settings.system_health_probe_timeout_seconds = 0.25
    original = service._cloudflare_health

    def slow_cloudflare(now: datetime) -> IntegrationHealth:
        time.sleep(0.75)
        return original(now)

    service._cloudflare_health = slow_cloudflare  # type: ignore[method-assign]

    started = time.monotonic()
    response = service.snapshot(force=True)
    elapsed = time.monotonic() - started

    external = next(
        group for group in response.groups if group.key == "external_services"
    )
    cloudflare = next(item for item in external.items if item.name == "Cloudflare")
    github = next(item for item in external.items if item.name == "GitHub / CI-CD")
    assert elapsed < 0.6
    assert cloudflare.status == "attention"
    assert cloudflare.metadata["probe_status"] == "timed_out"
    assert cloudflare.metadata["probe_timeout_seconds"] == 0.25
    assert github.status == "healthy"
    assert github.metadata["probe_status"] == "completed"


def test_timeout_storm_preserves_last_integral_snapshot_and_names_pending_checks() -> None:
    service = _service()
    baseline = service.snapshot(force=True)
    service.settings.system_health_probe_timeout_seconds = 0.25
    original_cloudflare = service._cloudflare_health
    original_github = service._github_health
    original_open_finance = service.open_finance.integration_health
    service.open_finance.integration_health = (
        lambda **_kwargs: original_open_finance(timeout_seconds=2.0)
    )

    def slow_cloudflare(now: datetime) -> IntegrationHealth:
        time.sleep(0.75)
        return original_cloudflare(now)

    def slow_github(now: datetime) -> IntegrationHealth:
        time.sleep(0.75)
        return original_github(now)

    service._cloudflare_health = slow_cloudflare  # type: ignore[method-assign]
    service._github_health = slow_github  # type: ignore[method-assign]

    response = service.snapshot(force=True)

    assert response.generated_at > baseline.generated_at
    assert response.last_verified_at == baseline.generated_at
    assert response.status == "attention"
    assert response.quality == baseline.quality
    assert response.healthy_count == baseline.healthy_count
    assert response.total_count == baseline.total_count
    assert response.probe_failure_count == 2
    assert response.probe_failures == ["cloudflare", "github"]
    assert response.groups == baseline.groups


def test_live_http_probes_receive_the_short_system_health_timeout() -> None:
    service = _service()
    observed_timeouts: list[float] = []

    def recording_get(url: str, **kwargs):
        observed_timeouts.append(float(kwargs["timeout"]))
        return _external_get(url, **kwargs)

    service.external_get = recording_get

    response = service.snapshot(force=True)

    assert response.status == "healthy"
    assert observed_timeouts
    assert set(observed_timeouts) == {2.0}
    items = [item for group in response.groups for item in group.items]
    assert all("probe_duration_ms" in item.metadata for item in items)
