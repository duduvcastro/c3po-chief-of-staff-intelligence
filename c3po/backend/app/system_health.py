from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import shutil
from threading import Lock
import time
from typing import Any, Callable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx

from .config import Settings
from .cve_acceptance import validate_acceptance_overlay_payload
from .governance_vulnerability import report_sha256
from .observability import HealthcheckPing
from .schemas import AiUsageMetric, ApiUsageMetric, IntegrationHealth, SystemHealthGroup, SystemHealthResponse
from .valuation_worker_contract import (
    VALUATION_WORKER_CANONICAL_PHASE,
    VALUATION_WORKER_OFFHOURS_PHASES,
    VALUATION_WORKER_PHASES,
)


SAO_PAULO = ZoneInfo("America/Sao_Paulo")
logger = logging.getLogger("c3po.system_health")


class SystemHealthService:
    def __init__(
        self,
        settings: Settings,
        database: Any,
        legacy: Any,
        open_finance: Any,
        market_data: Any,
        server_usage: Any,
        *,
        cache_seconds: int = 60,
        external_get: Callable[..., Any] | None = None,
        backblaze_client: Any | None = None,
        disk_usage: Callable[[Path], Any] | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.legacy = legacy
        self.open_finance = open_finance
        self.market_data = market_data
        self.server_usage = server_usage
        self.cache_seconds = cache_seconds
        self.external_get = external_get or httpx.get
        self.backblaze_client = backblaze_client
        self.disk_usage = disk_usage or shutil.disk_usage
        self._cached_at: datetime | None = None
        self._cached_response: SystemHealthResponse | None = None
        self._refresh_lock = Lock()

    def snapshot(self, *, force: bool = False) -> SystemHealthResponse:
        now = datetime.now(timezone.utc)
        if not force and self._cache_is_fresh(now):
            return self._cached_response

        acquired = self._refresh_lock.acquire(blocking=force)
        if not acquired:
            if self._cached_response is not None:
                return self._cached_response
            acquired = self._refresh_lock.acquire(
                timeout=self.settings.system_health_probe_timeout_seconds + 0.25
            )
            if acquired and self._cached_response is not None:
                self._refresh_lock.release()
                return self._cached_response
            if not acquired:
                return self._startup_degraded_response(now)

        try:
            if not force and self._cache_is_fresh(now):
                return self._cached_response
            response = self._refresh_snapshot(now)
            self._cached_at = now
            self._cached_response = response
            return response
        finally:
            self._refresh_lock.release()

    def _refresh_snapshot(self, now: datetime) -> SystemHealthResponse:
        timeout = self.settings.system_health_probe_timeout_seconds
        probes: dict[str, Callable[[], Any]] = {
            "api_usage": lambda: self._api_usage(now),
            "openai_usage": lambda: self._openai_usage(now),
            "anthropic_usage": lambda: self._anthropic_usage(now),
            "core": lambda: self._core_api_health(now),
            "cloudflare": lambda: self._cloudflare_health(now),
            "github": lambda: self._github_health(now),
            "intermedia": lambda: self._intermedia_health(now),
            "backblaze": lambda: self._backblaze_health(now),
            "healthchecks": lambda: self._healthchecks_health(now),
            "sentry": lambda: self._sentry_health(now),
            "open_meteo": lambda: self._open_meteo_health(now),
            "open_finance": lambda: self.open_finance.integration_health(
                timeout_seconds=timeout
            ),
            "aws": lambda: self._aws_health(now),
            "controls": lambda: self._day_d_and_valuation_health(now),
            "governance": lambda: self._governance_vulnerability_health(now),
            "incidents": lambda: self._operational_incident_health(now),
            "quote_providers": lambda: self._quote_provider_health(now),
            "finnhub": lambda: self._finnhub_health(now),
            "fmp": lambda: self._fmp_health(now),
            "massive": lambda: self._massive_health(now),
            "official_sources": lambda: self._official_sources_health(now),
            "automations": lambda: self._automation_health(now),
        }
        results, failures, durations_ms = self._run_probes(probes, timeout)

        api_usage = results.get("api_usage") or []
        api_usage_health = (
            self._probe_degraded_item(
                "Daily API Usage", "api_usage", failures["api_usage"], now
            )
            if "api_usage" in failures
            else self._api_usage_health(api_usage, now)
        )
        api_usage_health = self._with_probe_metadata(
            api_usage_health,
            "api_usage",
            durations_ms.get("api_usage"),
            timeout,
        )
        ai_usage = [
            results.get("openai_usage")
            or self._degraded_ai_usage(
                "OpenAI", "GPT Codex", failures.get("openai_usage"), now
            ),
            results.get("anthropic_usage")
            or self._degraded_ai_usage(
                "Anthropic", "Claude Code", failures.get("anthropic_usage"), now
            ),
        ]
        groups = [
            self._group(
                "apis",
                "Core APIs",
                [
                    *self._probe_items(
                        results, failures, durations_ms, "core", "Core APIs", now, timeout
                    ),
                    api_usage_health,
                ],
            ),
            self._group(
                "external_services",
                "Contracted & External Services",
                self._probe_items_many(
                    results,
                    failures,
                    durations_ms,
                    [
                        ("cloudflare", "Cloudflare"),
                        ("github", "GitHub / CI-CD"),
                        ("intermedia", "Intermedia Exchange"),
                        ("backblaze", "Backblaze B2"),
                        ("healthchecks", "Healthchecks.io"),
                        ("sentry", "Sentry"),
                        ("open_meteo", "Open-Meteo"),
                    ],
                    now,
                    timeout,
                ),
            ),
            self._group(
                "open_finance",
                "Pluggy & Banks",
                self._probe_items(
                    results, failures, durations_ms, "open_finance", "Pluggy API", now, timeout
                ),
            ),
            self._group(
                "aws",
                "AWS Infrastructure",
                self._probe_items(
                    results, failures, durations_ms, "aws", "AWS Infrastructure", now, timeout
                ),
            ),
            self._group(
                "controls",
                "Day D & Valuation Controls",
                self._probe_items(
                    results,
                    failures,
                    durations_ms,
                    "controls",
                    "Day D & Valuation Controls",
                    now,
                    timeout,
                ),
            ),
            self._group(
                "governance",
                "Governança & Vulnerabilidades",
                self._probe_items(
                    results,
                    failures,
                    durations_ms,
                    "governance",
                    "Governança & Vulnerabilidades",
                    now,
                    timeout,
                ) + self._probe_items(
                    results,
                    failures,
                    durations_ms,
                    "incidents",
                    "Incidentes operacionais",
                    now,
                    timeout,
                ),
            ),
            self._group(
                "quotes",
                "Market Quotes",
                self._probe_items_many(
                    results,
                    failures,
                    durations_ms,
                    [
                        ("quote_providers", "Market data APIs"),
                        ("finnhub", "Finnhub"),
                        ("fmp", "FMP"),
                        ("massive", "Massive"),
                    ],
                    now,
                    timeout,
                ),
            ),
            self._group(
                "official_sources",
                "Official Intelligence",
                self._probe_items(
                    results,
                    failures,
                    durations_ms,
                    "official_sources",
                    "Official intelligence sources",
                    now,
                    timeout,
                ),
            ),
            self._group(
                "automations",
                "Automatic Routines",
                self._probe_items(
                    results,
                    failures,
                    durations_ms,
                    "automations",
                    "Summary scheduler",
                    now,
                    timeout,
                ),
            ),
        ]
        items = [item for group in groups for item in group.items]
        healthy_count = sum(item.status == "healthy" for item in items)
        status = self._aggregate_status([group.status for group in groups])
        response = SystemHealthResponse(
            generated_at=now,
            status=status,
            quality=round(healthy_count / len(items) * 100) if items else 0,
            healthy_count=healthy_count,
            total_count=len(items),
            api_usage=api_usage,
            ai_usage=ai_usage,
            groups=groups,
        )
        return response

    def _cache_is_fresh(self, now: datetime) -> bool:
        return bool(
            self._cached_at
            and self._cached_response
            and (now - self._cached_at).total_seconds() < self.cache_seconds
        )

    def _run_probes(
        self,
        probes: dict[str, Callable[[], Any]],
        timeout_seconds: float,
    ) -> tuple[dict[str, Any], dict[str, str], dict[str, float]]:
        executor = ThreadPoolExecutor(
            max_workers=len(probes),
            thread_name_prefix="system-health",
        )
        submitted: dict[str, float] = {}

        def measured_loader(loader: Callable[[], Any]) -> tuple[Any, float]:
            started = time.monotonic()
            value = loader()
            return value, round((time.monotonic() - started) * 1000, 1)

        futures: dict[Future[Any], str] = {}
        for key, loader in probes.items():
            submitted[key] = time.monotonic()
            futures[executor.submit(measured_loader, loader)] = key
        done, pending = wait(futures, timeout=timeout_seconds)
        results: dict[str, Any] = {}
        failures: dict[str, str] = {}
        durations_ms: dict[str, float] = {}
        observed_at = time.monotonic()

        for future in done:
            key = futures[future]
            try:
                results[key], durations_ms[key] = future.result()
            except Exception as exc:
                durations_ms[key] = round(
                    (observed_at - submitted[key]) * 1000, 1
                )
                failures[key] = f"failed fast · {self._safe_error(exc)}"
                logger.warning("System-health probe failed: %s", key, exc_info=True)
        for future in pending:
            key = futures[future]
            durations_ms[key] = round(
                (observed_at - submitted[key]) * 1000, 1
            )
            failures[key] = f"timed out after {timeout_seconds:.1f}s"
            future.cancel()
            logger.warning(
                "System-health probe timed out after %.1fs: %s",
                timeout_seconds,
                key,
            )

        executor.shutdown(wait=False, cancel_futures=True)
        return results, failures, durations_ms

    def _probe_items_many(
        self,
        results: dict[str, Any],
        failures: dict[str, str],
        durations_ms: dict[str, float],
        definitions: list[tuple[str, str]],
        now: datetime,
        timeout_seconds: float,
    ) -> list[IntegrationHealth]:
        return [
            item
            for key, name in definitions
            for item in self._probe_items(
                results,
                failures,
                durations_ms,
                key,
                name,
                now,
                timeout_seconds,
            )
        ]

    def _probe_items(
        self,
        results: dict[str, Any],
        failures: dict[str, str],
        durations_ms: dict[str, float],
        key: str,
        name: str,
        now: datetime,
        timeout_seconds: float,
    ) -> list[IntegrationHealth]:
        if key in failures:
            return [
                self._probe_degraded_item(
                    name, key, failures[key], now, durations_ms.get(key)
                )
            ]
        value = results.get(key)
        items = (
            value
            if isinstance(value, list)
            else [value]
            if isinstance(value, IntegrationHealth)
            else []
        )
        if not items:
            return [
                self._probe_degraded_item(
                    name,
                    key,
                    "returned no health signal",
                    now,
                    durations_ms.get(key),
                )
            ]
        return [
            self._with_probe_metadata(
                item, key, durations_ms.get(key), timeout_seconds
            )
            for item in items
        ]

    @staticmethod
    def _with_probe_metadata(
        item: IntegrationHealth,
        key: str,
        duration_ms: float | None,
        timeout_seconds: float,
    ) -> IntegrationHealth:
        metadata = {
            **item.metadata,
            "probe_key": key,
            "probe_duration_ms": duration_ms,
            "probe_timeout_seconds": timeout_seconds,
            "probe_status": item.metadata.get("probe_status", "completed"),
        }
        return item.model_copy(update={"metadata": metadata})

    def _probe_degraded_item(
        self,
        name: str,
        key: str,
        reason: str,
        now: datetime,
        duration_ms: float | None = None,
    ) -> IntegrationHealth:
        return IntegrationHealth(
            name=name,
            status="attention",
            detail=f"Status unknown · health probe {reason}",
            last_update=self._format_time(now),
            metadata={
                "probe_key": key,
                "probe_duration_ms": duration_ms,
                "probe_timeout_seconds": self.settings.system_health_probe_timeout_seconds,
                "probe_status": (
                    "timed_out" if reason.startswith("timed out") else "failed"
                ),
            },
        )

    @staticmethod
    def _degraded_ai_usage(
        provider: str,
        product: str,
        reason: str | None,
        now: datetime,
    ) -> AiUsageMetric:
        return AiUsageMetric(
            provider=provider,
            product=product,
            status="attention",
            detail=f"Usage probe {reason or 'returned no signal'}",
            measured_at=now,
        )

    def _startup_degraded_response(self, now: datetime) -> SystemHealthResponse:
        item = self._probe_degraded_item(
            "System health refresh",
            "snapshot",
            "timed out waiting for the initial refresh",
            now,
        )
        group = self._group("apis", "Core APIs", [item])
        return SystemHealthResponse(
            generated_at=now,
            status="attention",
            quality=0,
            healthy_count=0,
            total_count=1,
            api_usage=[],
            ai_usage=[],
            groups=[group],
        )

    def _api_usage(self, now: datetime) -> list[ApiUsageMetric]:
        metrics: list[ApiUsageMetric] = []
        if self.settings.eodhd_api_token:
            try:
                base_url = self.settings.eodhd_base_url.rstrip("/")
                usage_url = f"{base_url}/user/" if base_url.endswith("/api") else f"{base_url}/api/user/"
                response = self.external_get(
                    usage_url,
                    params={"api_token": self.settings.eodhd_api_token, "fmt": "json"},
                timeout=self.settings.system_health_probe_timeout_seconds,
                    follow_redirects=True,
                    headers={"User-Agent": "C3PO-API-Usage/1.0"},
                )
                response.raise_for_status()
                payload = response.json()
                used = max(0, int(payload.get("apiRequests") or 0))
                limit = max(1, int(payload.get("dailyRateLimit") or 0))
                percent = round(used / limit * 100, 2)
                status = "critical" if percent > 90 else "attention" if percent > 70 else "healthy"
                metrics.append(ApiUsageMetric(
                    provider="EODHD",
                    used=used,
                    limit=limit,
                    percent_used=percent,
                    status=status,
                    detail=f"Official provider counter · resets daily · {max(0, limit - used):,} remaining",
                    measured_at=now,
                ))
            except Exception:
                pass
        return metrics

    def _ai_usage(self, now: datetime) -> list[AiUsageMetric]:
        return [self._openai_usage(now), self._anthropic_usage(now)]

    def _openai_usage(self, now: datetime) -> AiUsageMetric:
        if not self.settings.openai_admin_api_key:
            return AiUsageMetric(
                provider="OpenAI",
                product="GPT Codex",
                status="unavailable",
                detail="OpenAI Admin API key required for organization usage telemetry",
                measured_at=now,
            )
        try:
            params: list[tuple[str, str | int]] = [
                ("start_time", int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())),
                ("bucket_width", "1d"),
                ("limit", 31),
                ("group_by", "model"),
            ]
            params.extend(("project_ids", value) for value in self.settings.openai_usage_projects)
            response = self.external_get(
                "https://api.openai.com/v1/organization/usage/completions",
                params=params,
                timeout=self.settings.system_health_probe_timeout_seconds,
                headers={"Authorization": f"Bearer {self.settings.openai_admin_api_key}", "Content-Type": "application/json"},
            )
            response.raise_for_status()
            results = [result for bucket in response.json().get("data", []) for result in bucket.get("results", [])]
            codex_results = [result for result in results if "codex" in str(result.get("model") or "").lower()]
            scoped_results = codex_results or results
            input_tokens = sum(int(result.get("input_tokens") or 0) for result in scoped_results)
            output_tokens = sum(int(result.get("output_tokens") or 0) for result in scoped_results)
            cached_tokens = sum(int(result.get("input_cached_tokens") or 0) for result in scoped_results)
            requests = sum(int(result.get("num_model_requests") or 0) for result in scoped_results)
            detail = "Codex model usage" if codex_results else "OpenAI organization usage; no Codex model breakdown returned"
            return AiUsageMetric(
                provider="OpenAI", product="GPT Codex", status="healthy",
                input_tokens=input_tokens, output_tokens=output_tokens,
                cached_input_tokens=cached_tokens, requests=requests,
                detail=detail, measured_at=now,
            )
        except Exception as exc:
            return AiUsageMetric(
                provider="OpenAI", product="GPT Codex", status="attention",
                detail=f"Usage API unavailable · {self._safe_error(exc)}", measured_at=now,
            )

    def _anthropic_usage(self, now: datetime) -> AiUsageMetric:
        if not self.settings.anthropic_admin_api_key:
            detail = (
                "Claude runtime key connected; Anthropic Admin API key required for usage telemetry"
                if self.settings.anthropic_api_key else
                "Anthropic Admin API key required for organization usage telemetry"
            )
            return AiUsageMetric(
                provider="Anthropic", product="Claude Code", status="unavailable",
                detail=detail, measured_at=now,
            )
        try:
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
            params: list[tuple[str, str | int]] = [
                ("starting_at", month_start), ("bucket_width", "1d"), ("limit", 31), ("group_by[]", "model"),
            ]
            params.extend(("workspace_ids[]", value) for value in self.settings.anthropic_usage_workspaces)
            response = self.external_get(
                "https://api.anthropic.com/v1/organizations/usage_report/messages",
                params=params,
                timeout=self.settings.system_health_probe_timeout_seconds,
                headers={
                    "x-api-key": self.settings.anthropic_admin_api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            results = [result for bucket in response.json().get("data", []) for result in bucket.get("results", [])]
            input_tokens = sum(
                int(result.get("uncached_input_tokens") or 0)
                + int(result.get("cache_read_input_tokens") or 0)
                + sum(int(value or 0) for value in (result.get("cache_creation") or {}).values())
                for result in results
            )
            output_tokens = sum(int(result.get("output_tokens") or 0) for result in results)
            cached_tokens = sum(
                int(result.get("cache_read_input_tokens") or 0)
                + sum(int(value or 0) for value in (result.get("cache_creation") or {}).values())
                for result in results
            )
            return AiUsageMetric(
                provider="Anthropic", product="Claude Code", status="healthy",
                input_tokens=input_tokens, output_tokens=output_tokens,
                cached_input_tokens=cached_tokens,
                detail="Anthropic workspace usage", measured_at=now,
            )
        except Exception as exc:
            return AiUsageMetric(
                provider="Anthropic", product="Claude Code", status="attention",
                detail=f"Usage API unavailable · {self._safe_error(exc)}", measured_at=now,
            )

    def _api_usage_health(self, metrics: list[ApiUsageMetric], now: datetime) -> IntegrationHealth:
        if not metrics:
            return IntegrationHealth(
                name="Daily API Usage",
                status="attention",
                detail="Official daily usage counter unavailable",
                last_update=self._format_time(now),
            )

        summary = " · ".join(f"{metric.provider} {metric.percent_used:.1f}%" for metric in metrics)
        return IntegrationHealth(
            name="Daily API Usage",
            # Availability and quota pressure are separate signals. A valid
            # provider counter proves the integration is operational even when
            # the consumption gauge is in its warning or critical range.
            status="healthy",
            detail=f"Official counter active · {summary}",
            last_update=self._format_time(now),
        )

    def _core_api_health(self, now: datetime) -> list[IntegrationHealth]:
        timestamp = self._format_time(now)
        items = [
            IntegrationHealth(
                name="C3PO API",
                status="healthy",
                detail="FastAPI online · authenticated health endpoint responding",
                last_update=timestamp,
            )
        ]
        if not self.settings.database_url:
            items.append(IntegrationHealth(
                name="PostgreSQL",
                status="attention",
                detail="Local fallback storage is active",
                last_update=timestamp,
            ))
            return items
        try:
            with self.database.connection() as connection:
                connection.execute("SELECT 1").fetchone()
            items.append(IntegrationHealth(
                name="PostgreSQL",
                status="healthy",
                detail="Database connection and query confirmed",
                last_update=timestamp,
            ))
        except Exception as exc:
            items.append(IntegrationHealth(
                name="PostgreSQL",
                status="offline",
                detail=f"Database check failed · {self._safe_error(exc)}",
                last_update=timestamp,
            ))
        return items

    def _quote_health(self, now: datetime) -> list[IntegrationHealth]:
        return [
            *self._quote_provider_health(now),
            self._finnhub_health(now),
            self._fmp_health(now),
            self._massive_health(now),
        ]

    def _quote_provider_health(self, now: datetime) -> list[IntegrationHealth]:
        try:
            providers = self.market_data.health()
        except Exception as exc:
            return [self._offline_item("Market data APIs", exc, now)]
        items: list[IntegrationHealth] = []
        for provider in providers:
            status = "offline" if provider.status == "unconfigured" else provider.status
            detail = f"{provider.market} · {provider.plan}"
            if provider.last_error and status != "healthy":
                detail = f"{detail} · {provider.last_error}"
            items.append(IntegrationHealth(
                name=provider.name,
                status=status,
                detail=detail,
                last_update=self._format_time(provider.last_success_at) if provider.last_success_at else "No successful quote yet",
            ))
        return items or [IntegrationHealth(
            name="Market data APIs",
            status="offline",
            detail="No quote provider is registered",
            last_update=self._format_time(now),
        )]

    def _finnhub_health(self, now: datetime) -> IntegrationHealth:
        if not self.settings.finnhub_api_token:
            return IntegrationHealth(
                name="Finnhub",
                status="offline",
                detail="Fundamental-1 credential is not configured",
                last_update=self._format_time(now),
            )
        try:
            response = self.external_get(
                f"{self.settings.finnhub_base_url.rstrip('/')}/api/v1/stock/insider-transactions",
                params={"symbol": "AAPL", "token": self.settings.finnhub_api_token},
                timeout=self.settings.system_health_probe_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "C3PO-Systems-Conditions/1.0"},
            )
            response.raise_for_status()
            return IntegrationHealth(
                name="Finnhub",
                status="healthy",
                detail="United States · Fundamental-1 · insider transactions",
                last_update=self._format_time(now),
            )
        except Exception as exc:
            return self._offline_item("Finnhub", exc, now)

    def _fmp_health(self, now: datetime) -> IntegrationHealth:
        if not self.settings.fmp_api_token:
            return IntegrationHealth(
                name="FMP",
                status="offline",
                detail="Ultimate credential is not configured",
                last_update=self._format_time(now),
            )
        try:
            response = self.external_get(
                f"{self.settings.fmp_base_url.rstrip('/')}/stable/price-target-consensus",
                params={"symbol": "AAPL", "apikey": self.settings.fmp_api_token},
                timeout=self.settings.system_health_probe_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "C3PO-Systems-Conditions/1.0"},
            )
            response.raise_for_status()
            return IntegrationHealth(
                name="FMP",
                status="healthy",
                detail="United States · Ultimate · consensus, grades, 13F",
                last_update=self._format_time(now),
            )
        except Exception as exc:
            return self._offline_item("FMP", exc, now)

    def _massive_health(self, now: datetime) -> IntegrationHealth:
        if not self.settings.massive_api_token:
            return IntegrationHealth(
                name="Massive",
                status="offline",
                detail="Stocks Advanced credential is not configured",
                last_update=self._format_time(now),
            )
        try:
            response = self.external_get(
                f"{self.settings.massive_base_url.rstrip('/')}/v1/marketstatus/now",
                params={"apiKey": self.settings.massive_api_token},
                timeout=self.settings.system_health_probe_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "C3PO-Systems-Conditions/1.0"},
            )
            response.raise_for_status()
            return IntegrationHealth(
                name="Massive",
                status="healthy",
                detail="United States · Stocks Advanced · SIP replay reference",
                last_update=self._format_time(now),
            )
        except Exception as exc:
            return self._offline_item("Massive", exc, now)

    def _external_services_health(self, now: datetime) -> list[IntegrationHealth]:
        return [
            self._cloudflare_health(now),
            self._github_health(now),
            self._intermedia_health(now),
            self._backblaze_health(now),
            self._healthchecks_health(now),
            self._sentry_health(now),
            self._open_meteo_health(now),
        ]

    def _healthchecks_health(self, now: datetime) -> IntegrationHealth:
        configured_checks = (
            self.settings.healthcheck_valuation_worker_url,
            self.settings.healthcheck_cash_yield_url,
            self.settings.healthcheck_code_census_url,
            self.settings.healthcheck_postgres_backup_url,
            self.settings.healthcheck_governance_url,
        )
        configured_count = sum(
            HealthcheckPing(url).configured for url in configured_checks
        ) + sum((
            int(self.settings.healthcheck_postgres_restore_configured),
            int(self.settings.healthcheck_trivy_configured),
            int(self.settings.healthcheck_unattended_upgrades_configured),
        ))
        expected_count = 8
        if configured_count < expected_count:
            return IntegrationHealth(
                name="Healthchecks.io",
                status="offline",
                detail=(
                    "Dead-man monitoring incomplete · "
                    f"{configured_count}/{expected_count} checks configured"
                ),
                last_update=self._format_time(now),
            )
        try:
            response = self.external_get(
                "https://healthchecks.io/",
                timeout=self.settings.system_health_probe_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "C3PO-Systems-Conditions/1.0"},
            )
            status = "healthy" if response.status_code < 400 else "attention" if response.status_code < 500 else "offline"
            return IntegrationHealth(
                name="Healthchecks.io",
                status=status,
                detail=(
                    f"{expected_count}/{expected_count} dead-man checks configured · "
                    f"SaaS HTTP {response.status_code}"
                ),
                last_update=self._format_time(now),
            )
        except Exception as exc:
            return self._offline_item("Healthchecks.io", exc, now)

    def _sentry_health(self, now: datetime) -> IntegrationHealth:
        dsn = self.settings.sentry_dsn.strip()
        parsed = urlsplit(dsn)
        if (
            not dsn
            or parsed.scheme != "https"
            or not (parsed.hostname or "").lower().endswith(".sentry.io")
        ):
            return IntegrationHealth(
                name="Sentry",
                status="offline",
                detail="Official SaaS DSN is not configured",
                last_update=self._format_time(now),
            )
        try:
            response = self.external_get(
                "https://status.sentry.io/api/v2/status.json",
                timeout=self.settings.system_health_probe_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "C3PO-Systems-Conditions/1.0"},
            )
            indicator = str((response.json().get("status") or {}).get("indicator") or "unknown")
            if response.status_code >= 500 or indicator in {"major", "critical"}:
                status = "offline"
            elif response.status_code >= 400 or indicator not in {"none", "unknown"}:
                status = "attention"
            else:
                status = "healthy"
            return IntegrationHealth(
                name="Sentry",
                status=status,
                detail=f"DSN loaded · PII disabled · SaaS status {indicator}",
                last_update=self._format_time(now),
            )
        except Exception as exc:
            return self._offline_item("Sentry", exc, now)

    def _backblaze_health(self, now: datetime) -> IntegrationHealth:
        if not all((
            self.settings.day_d_b2_key_id,
            self.settings.day_d_b2_application_key,
            self.settings.day_d_b2_bucket,
        )):
            return IntegrationHealth(
                name="Backblaze B2",
                status="offline",
                detail="Day D cold-storage credentials are not configured",
                last_update=self._format_time(now),
            )
        try:
            client = self.backblaze_client or self._build_backblaze_client()
            client.head_bucket(Bucket=self.settings.day_d_b2_bucket)
            return IntegrationHealth(
                name="Backblaze B2",
                status="healthy",
                detail=(
                    f"Day D cold storage · private bucket access confirmed · "
                    f"{self.settings.day_d_b2_region}"
                ),
                last_update=self._format_time(now),
            )
        except Exception as exc:
            return self._offline_item("Backblaze B2", exc, now)

    def _build_backblaze_client(self) -> Any:
        import boto3
        from botocore.config import Config

        return boto3.client(
            "s3",
            endpoint_url=self.settings.day_d_b2_endpoint,
            aws_access_key_id=self.settings.day_d_b2_key_id,
            aws_secret_access_key=self.settings.day_d_b2_application_key,
            region_name=self.settings.day_d_b2_region,
            config=Config(
                signature_version="s3v4",
                connect_timeout=self.settings.system_health_probe_timeout_seconds,
                read_timeout=self.settings.system_health_probe_timeout_seconds,
                retries={"max_attempts": 1},
            ),
        )

    def _cloudflare_health(self, now: datetime) -> IntegrationHealth:
        url = f"{self.settings.public_url.rstrip('/')}/robots.txt"
        try:
            response = self.external_get(
                url,
                timeout=self.settings.system_health_probe_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "C3PO-Systems-Conditions/1.0"},
            )
            server = str(response.headers.get("server") or "").lower()
            cf_ray = str(response.headers.get("cf-ray") or "")
            protected = "disallow: /" in str(response.text or "").lower()
            cloudflare_confirmed = "cloudflare" in server or bool(cf_ray)
            if response.status_code >= 500:
                status = "offline"
            elif cloudflare_confirmed and protected:
                status = "healthy"
            else:
                status = "attention"
            detail_parts = [f"HTTP {response.status_code}"]
            detail_parts.append("DNS, TLS and proxy confirmed" if cloudflare_confirmed else "Cloudflare headers not confirmed")
            detail_parts.append("search robots blocked" if protected else "anti-indexation not confirmed")
            return IntegrationHealth(
                name="Cloudflare",
                status=status,
                detail=" · ".join(detail_parts),
                last_update=self._format_time(now),
            )
        except Exception as exc:
            return self._offline_item("Cloudflare", exc, now)

    def _github_health(self, now: datetime) -> IntegrationHealth:
        try:
            response = self.external_get(
                f"{self.settings.github_api_url.rstrip('/')}/rate_limit",
                timeout=self.settings.system_health_probe_timeout_seconds,
                follow_redirects=True,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "C3PO-Systems-Conditions/1.0",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            if response.status_code >= 500:
                status = "offline"
            elif response.status_code >= 400:
                status = "attention"
            else:
                status = "healthy"

            revision = ""
            deployed_at = now
            marker = self.settings.deploy_version_file
            try:
                revision = marker.read_text(encoding="utf-8").strip()
                deployed_at = datetime.fromtimestamp(marker.stat().st_mtime, tz=timezone.utc)
            except OSError:
                if self.settings.environment.lower() == "production" and status == "healthy":
                    status = "attention"

            repository = self.settings.github_repository
            if revision:
                detail = f"GitHub API · {repository} · deployed {revision[:10]}"
            else:
                detail = f"GitHub API · {repository} · awaiting first pipeline marker"
            return IntegrationHealth(
                name="GitHub / CI-CD",
                status=status,
                detail=detail,
                last_update=self._format_time(deployed_at),
            )
        except Exception as exc:
            return self._offline_item("GitHub / CI-CD", exc, now)

    def _intermedia_health(self, now: datetime) -> IntegrationHealth:
        if not self.settings.exchange_server or not self.settings.exchange_user or not self.settings.exchange_app_password:
            return IntegrationHealth(
                name="Intermedia Exchange",
                status="offline",
                detail="Exchange credentials are not configured",
                last_update=self._format_time(now),
            )
        try:
            snapshot = self.legacy.read()
            email = next((item for item in snapshot.get("integrations", []) if item.name == "Email"), None)
            if email is None:
                return IntegrationHealth(
                    name="Intermedia Exchange",
                    status="attention",
                    detail="EWS configured · no recent delivery evidence",
                    last_update=self._format_time(now),
                )
            return IntegrationHealth(
                name="Intermedia Exchange",
                status=email.status,
                detail=f"EWS mailbox and report delivery · {email.detail}",
                last_update=email.last_update,
            )
        except Exception as exc:
            return self._offline_item("Intermedia Exchange", exc, now)

    def _open_meteo_health(self, now: datetime) -> IntegrationHealth:
        try:
            response = self.external_get(
                "https://api.open-meteo.com/v1/forecast",
                params={"latitude": -22.98, "longitude": -43.22, "current": "temperature_2m"},
                timeout=self.settings.system_health_probe_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "C3PO-Systems-Conditions/1.0"},
            )
            status = "healthy" if response.status_code == 200 else "attention" if response.status_code < 500 else "offline"
            return IntegrationHealth(
                name="Open-Meteo",
                status=status,
                detail=f"Weather forecast API · HTTP {response.status_code}",
                last_update=self._format_time(now),
            )
        except Exception as exc:
            return self._offline_item("Open-Meteo", exc, now)

    def _official_sources_health(self, now: datetime) -> list[IntegrationHealth]:
        definitions = {
            "cvm": ("CVM Dados Abertos", "Brazilian filings and company disclosures"),
            "sec": ("SEC EDGAR", "United States regulatory filings"),
            "ri": ("Issuer RI", "Official investor-relations pages"),
        }
        try:
            states = self.database.ir_source_health()
        except Exception as exc:
            return [self._offline_item("Official intelligence sources", exc, now)]

        items: list[IntegrationHealth] = []
        for code, (name, detail) in definitions.items():
            state = states.get(code, {})
            last_success_at = state.get("last_success_at")
            status = "healthy" if state.get("last_status") == "succeeded" else "attention"
            if state.get("last_error"):
                detail = f"{detail} · {str(state['last_error']).replace(chr(10), ' ')[:180]}"
            items.append(IntegrationHealth(
                name=name,
                status=status,
                detail=detail,
                last_update=self._format_time(last_success_at) if isinstance(last_success_at, datetime) else "No successful collection yet",
            ))
        return items

    def _aws_health(self, now: datetime) -> list[IntegrationHealth]:
        backup = self._postgres_backup_health(now)
        try:
            servers = self.server_usage.snapshot(hours=1).servers
        except Exception as exc:
            return [self._offline_item("AWS Lightsail", exc, now), backup]
        if not servers:
            return [IntegrationHealth(
                name="AWS Lightsail",
                status="offline",
                detail="No recent server telemetry",
                last_update=self._format_time(now),
            ), backup]

        items: list[IntegrationHealth] = []
        for server in servers:
            cpu = server.current.cpu_percent
            disk = server.current.disk_percent
            status = server.status
            if status == "healthy" and (
                (cpu is not None and cpu >= self.settings.server_usage_cpu_peak_warning_percent)
                or (disk is not None and disk >= self.settings.server_usage_disk_warning_percent)
            ):
                status = "attention"
            detail_parts = [server.region]
            detail_parts.append(f"CPU {cpu:.1f}%" if cpu is not None else "CPU unavailable")
            detail_parts.append(f"disk {disk:.1f}%" if disk is not None else "disk unavailable")
            items.append(IntegrationHealth(
                name=server.server_name,
                status=status,
                detail=" · ".join(detail_parts),
                last_update=self._format_time(server.current.collected_at) if server.current.collected_at else "No recent sample",
            ))
        return [*items, backup]

    def _postgres_backup_health(self, now: datetime) -> IntegrationHealth:
        if not all((
            self.settings.postgres_backup_bucket,
            self.settings.postgres_backup_region,
            self.settings.postgres_backup_access_key_id,
            self.settings.postgres_backup_secret_access_key,
        )):
            return IntegrationHealth(
                name="PostgreSQL offsite backup",
                status="offline",
                detail="S3 writer or bucket is not configured",
                last_update=self._format_time(now),
            )

        evidence_root = self.settings.legacy_root / "outputs" / "evidence"
        backup_root = evidence_root / "postgres-backup"
        try:
            run_directories = [path for path in backup_root.glob("*/*") if path.is_dir()]
            latest_run = max(run_directories, key=lambda path: path.stat().st_mtime) if run_directories else None
        except OSError as exc:
            return self._offline_item("PostgreSQL offsite backup", exc, now)
        if latest_run is None:
            return IntegrationHealth(
                name="PostgreSQL offsite backup",
                status="attention",
                detail="Private versioned S3 bucket configured · first sealed upload pending",
                last_update=self._format_time(now),
            )
        result_path = latest_run / "result.json"
        if not result_path.is_file():
            return IntegrationHealth(
                name="PostgreSQL offsite backup",
                status="offline",
                detail="Latest backup attempt did not produce a sealed result",
                last_update=self._format_time(
                    datetime.fromtimestamp(latest_run.stat().st_mtime, tz=timezone.utc)
                ),
            )

        try:
            result = self._verified_result_evidence(
                result_path,
                schema="C3PO_POSTGRES_BACKUP_RESULT-v1",
            )
            upload_path = result_path.with_name("upload.json")
            self._require_sha256s_entry(upload_path)
            upload = self._read_evidence(upload_path)
            uploads = upload.get("uploads")
            if (
                upload.get("schema") != "C3PO_POSTGRES_BACKUP_UPLOAD-v1"
                or upload.get("bucket") != self.settings.postgres_backup_bucket
                or upload.get("region") != self.settings.postgres_backup_region
                or upload.get("file_sha256") != result.get("dump_sha256")
                or not isinstance(uploads, list)
                or len(uploads) != int(result.get("upload_count") or 0)
                or result.get("uploads") != uploads
                or not uploads
                or any(
                    not isinstance(item, dict)
                    or not str(item.get("key") or "").startswith(
                        f"{self.settings.postgres_backup_prefix.strip('/')}/"
                    )
                    for item in uploads
                )
            ):
                raise ValueError("backup upload evidence does not reconcile")
            completed_at = self._payload_time(result, "completed_at")
            if completed_at is None:
                raise ValueError("backup completion time is missing")
            if completed_at.astimezone(timezone.utc) > now + timedelta(minutes=5):
                raise ValueError("backup completion time is in the future")
        except Exception as exc:
            return IntegrationHealth(
                name="PostgreSQL offsite backup",
                status="offline",
                detail=f"Latest backup evidence is invalid · {self._safe_error(exc)}",
                last_update=self._format_time(now),
            )

        age_hours = max(0.0, (now - completed_at.astimezone(timezone.utc)).total_seconds() / 3600)
        if age_hours > 54:
            status = "offline"
        elif age_hours > 30:
            status = "attention"
        else:
            status = "healthy"

        restore_detail = "restore drill pending"
        try:
            restore_paths = list((evidence_root / "postgres-restore-drill").glob("*/*/result.json"))
            restore_path = max(restore_paths, key=lambda path: path.stat().st_mtime) if restore_paths else None
        except OSError as exc:
            restore_detail = f"restore drill evidence unavailable · {self._safe_error(exc)}"
            restore_path = None
            status = "attention" if status == "healthy" else status
        if restore_path is not None:
            try:
                restore = self._verified_result_evidence(
                    restore_path,
                    schema="C3PO_POSTGRES_RESTORE_DRILL-v1",
                )
                restored_at = self._payload_time(restore, "completed_at")
                if restored_at is None:
                    raise ValueError("restore drill completion time is missing")
                if restored_at.astimezone(timezone.utc) > now + timedelta(minutes=5):
                    raise ValueError("restore drill completion time is in the future")
                restore_age_days = max(0.0, (now - restored_at.astimezone(timezone.utc)).total_seconds() / 86400)
                if restore_age_days <= 35:
                    restore_detail = "restore drill verified"
                else:
                    restore_detail = f"restore drill stale ({restore_age_days:.0f}d)"
                    status = "attention" if status == "healthy" else status
            except Exception as exc:
                restore_detail = f"restore drill invalid · {self._safe_error(exc)}"
                status = "attention" if status == "healthy" else status
        elif status == "healthy":
            status = "attention"

        return IntegrationHealth(
            name="PostgreSQL offsite backup",
            status=status,
            detail=(
                f"Immutable S3 upload evidenced · {len(uploads)} object(s) · "
                f"{restore_detail}"
            ),
            last_update=self._format_time(completed_at),
        )

    def _day_d_and_valuation_health(self, now: datetime) -> list[IntegrationHealth]:
        return [
            self._valuation_worker_phase_health(now),
            *self._valuation_v2_1b_health(now),
            self._day_d_disk_health(now),
            self._b2_zero_cap_health(now),
        ]

    def _operational_incident_health(self, now: datetime) -> IntegrationHealth:
        loader = getattr(self.database, "list_operational_incidents", None)
        incidents = loader(limit=20) if loader else []
        active = [item for item in incidents if item["status"] != "resolved"]
        critical = sum(item["severity"] == "critical" for item in active)
        status = "offline" if critical else "attention" if active else "healthy"
        detail = (
            f"{len(active)} ativo(s) · {critical} crítico(s)"
            if active else "Nenhum incidente operacional ativo"
        )
        latest_at = incidents[0]["last_seen_at"] if incidents else now
        return IntegrationHealth(
            name="Incidentes operacionais",
            status=status,
            detail=detail,
            last_update=self._format_time(latest_at),
            metadata={
                "kind": "operational_incidents",
                "active_count": len(active),
                "critical_count": critical,
                "incidents": incidents,
            },
        )

    def _governance_vulnerability_health(self, now: datetime) -> IntegrationHealth:
        try:
            report = self.database.latest_governance_vulnerability_report()
        except Exception as exc:
            return self._offline_item("Governança & Vulnerabilidades", exc, now)
        if not report:
            return IntegrationHealth(
                name="Governança & Vulnerabilidades",
                status="attention",
                detail="Primeiro atestado diário pendente · diário a partir de 02:15 BRT",
                last_update=self._format_time(now),
                metadata={"kind": "governance_vulnerabilities"},
            )
        if report.get("report_sha256") != report_sha256(report):
            return IntegrationHealth(
                name="Governança & Vulnerabilidades",
                status="offline",
                detail="Atestado diário com hash inválido",
                last_update=self._format_time(now),
                metadata={"kind": "governance_vulnerabilities"},
            )
        try:
            generated_at = datetime.fromisoformat(str(report["generated_at"]))
            if generated_at.tzinfo is None:
                generated_at = generated_at.replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            return IntegrationHealth(
                name="Governança & Vulnerabilidades",
                status="offline",
                detail="Atestado diário sem horário válido",
                last_update=self._format_time(now),
                metadata={"kind": "governance_vulnerabilities"},
            )
        stale = now - generated_at > timedelta(hours=36)
        dependabot = report.get("dependabot") or {}
        operating_system = report.get("operating_system") or {}
        production_images = report.get("production_images") or {}
        remediation_lanes = report.get("remediation_lanes") or {}
        governance = report.get("governance") or {}
        drift = governance.get("drift") or []
        open_total = int(dependabot.get("open_total") or 0)
        status = "offline" if stale else str(report.get("status") or "offline")
        layers_complete = bool(operating_system) and bool(production_images)
        remediation_lane_count = remediation_lanes.get("count")
        remediation_lane_items = remediation_lanes.get("items")
        remediation_lanes_complete = (
            remediation_lanes.get("available") is True
            and isinstance(remediation_lane_count, int)
            and not isinstance(remediation_lane_count, bool)
            and remediation_lane_count >= 0
            and isinstance(remediation_lane_items, list)
            and len(remediation_lane_items) == remediation_lane_count
        )
        if not layers_complete and status == "healthy":
            status = "attention"
        if (
            not remediation_lanes_complete
            or int(remediation_lane_count or 0) > 0
        ) and status == "healthy":
            status = "attention"
        os_pending = operating_system.get("security_updates_pending")
        acceptance = production_images.get("acceptance") or {}
        if acceptance.get("enabled") is True:
            try:
                validate_acceptance_overlay_payload(production_images)
            except RuntimeError:
                return IntegrationHealth(
                    name="Governança & Vulnerabilidades",
                    status="offline",
                    detail="Atestado diário com camada de aceite inválida",
                    last_update=self._format_time(generated_at),
                    metadata={"kind": "governance_vulnerabilities"},
                )
        acceptance_counts = acceptance.get("counts") or {}
        pending_acceptance = acceptance_counts.get("pending") or {}
        image_total = (
            pending_acceptance.get("total")
            if acceptance.get("enabled") is True
            else production_images.get("finding_total")
        )
        if acceptance.get("enabled") is True:
            raw_acceptance = acceptance_counts.get("raw") or {}
            accepted_acceptance = acceptance_counts.get("accepted") or {}
            image_detail = (
                f"imagens {image_total if image_total is not None else '?'} pendentes · "
                f"{accepted_acceptance.get('total', '?')} aceitas · "
                f"{raw_acceptance.get('total', '?')} brutas"
            )
        else:
            image_detail = f"imagens {image_total if image_total is not None else '?'}"
        layer_detail = (
            f"repo {open_total} · SO {os_pending if os_pending is not None else '?'} · "
            f"{image_detail}"
        )
        if stale:
            detail = "Atestado diário vencido há mais de 36h"
        elif not remediation_lanes_complete:
            detail = f"Lanes de remediação não verificáveis · {layer_detail}"
        elif int(remediation_lanes["count"]) > 0:
            detail = (
                f"{int(remediation_lanes['count'])} lane(s) de remediação aberta(s) · "
                f"{layer_detail}"
            )
        elif drift:
            fields = ", ".join(str(item.get("field")) for item in drift)
            detail = f"Drift de governança: {fields} · {layer_detail}"
        elif not layers_complete:
            detail = f"Camadas de servidor aguardando primeiro atestado · {layer_detail}"
        else:
            detail = f"Baseline íntegra · {layer_detail}"
        return IntegrationHealth(
            name="Governança & Vulnerabilidades",
            status=status,
            detail=detail,
            last_update=self._format_time(generated_at),
            metadata={
                "kind": "governance_vulnerabilities",
                "generated_at": generated_at.isoformat(),
                "revision": int(report.get("revision") or 1),
                "baseline_sha256": str((report.get("baseline") or {}).get("sha256") or ""),
                "dependabot": dependabot,
                "operating_system": operating_system,
                "production_images": production_images,
                "remediation_lanes": remediation_lanes,
                "known_vulnerabilities": report.get("known_vulnerabilities") or {},
                "governance_checks": governance.get("checks") or [],
                "drift_fields": [str(item.get("field")) for item in drift],
                "stale": stale,
            },
        )

    def _valuation_worker_phase_health(self, now: datetime) -> IntegrationHealth:
        definitions = {
            phase: definition
            for phase, definition in VALUATION_WORKER_PHASES.items()
            if phase != "cash_yield" or self.settings.r2d2_cash_yield_accounting_enabled
        }
        codes = [definition["code"] for definition in definitions.values()]
        try:
            states = self.database.ingestion_run_health(codes)
        except Exception as exc:
            return IntegrationHealth(
                name="Valuation worker phases",
                status="offline",
                detail=f"Phase evidence unavailable · {self._safe_error(exc)}",
                last_update=self._format_time(now),
            )

        local_now = now.astimezone(SAO_PAULO)
        midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        offhours_due = midnight.replace(hour=1)
        window_end = midnight.replace(hour=8)
        phase_due_at = {
            phase: midnight.replace(hour=6) if phase == "cash_yield" else offhours_due
            for phase in VALUATION_WORKER_OFFHOURS_PHASES
            if phase in definitions
        }
        expected_at = {
            VALUATION_WORKER_CANONICAL_PHASE: midnight,
            **{
                phase: due_at if local_now >= due_at else due_at - timedelta(days=1)
                for phase, due_at in phase_due_at.items()
            },
        }

        failed: list[str] = []
        pending: list[str] = []
        running: list[str] = []
        updates: list[datetime] = []
        for phase, definition in definitions.items():
            state = states.get(definition["code"], {})
            status = state.get("last_status")
            last_success = state.get("last_success_at")
            for field in ("completed_at", "started_at", "last_success_at"):
                value = state.get(field)
                if isinstance(value, datetime):
                    updates.append(value if value.tzinfo else value.replace(tzinfo=timezone.utc))
            if status == "failed":
                error = str(state.get("last_error") or "unknown error").replace("\n", " ")[:120]
                failed.append(f"{phase}: {error}")
                continue
            if status == "running":
                running.append(phase)
                continue
            if not isinstance(last_success, datetime):
                pending.append(phase)
                continue
            success_local = (
                last_success if last_success.tzinfo else last_success.replace(tzinfo=timezone.utc)
            ).astimezone(SAO_PAULO)
            if success_local < expected_at[phase]:
                pending.append(phase)

        if failed:
            status = "offline"
            detail = "Failed · " + " · ".join(failed)
        elif running or pending:
            latest_window_end = midnight.replace(hour=10) if "cash_yield" in definitions else window_end
            status = "attention" if local_now < latest_window_end else "offline"
            parts = []
            if running:
                parts.append("running: " + ", ".join(running))
            if pending:
                parts.append("pending/stale: " + ", ".join(pending))
            detail = "Phase evidence · " + " · ".join(parts)
        else:
            status = "healthy"
            detail = "Canonical and all configured phases succeeded for the expected cycle"

        return IntegrationHealth(
            name="Valuation worker phases",
            status=status,
            detail=detail,
            last_update=self._format_time(max(updates) if updates else now),
        )

    def _valuation_v2_1b_health(self, now: datetime) -> list[IntegrationHealth]:
        keys = ["B3_V2_PEER_QUALITY", "US_V2_PEER_QUALITY"]
        try:
            snapshots = self.database.latest_analysis_snapshot_outputs(
                "valuation_v2_peer_quality", keys, "pre_ab_report"
            )
        except Exception as exc:
            detail = f"Snapshot check failed · {self._safe_error(exc)}"
            return [
                IntegrationHealth(
                    name="Valuation V2.1b cycle",
                    status="offline",
                    detail=detail,
                    last_update=self._format_time(now),
                ),
                IntegrationHealth(
                    name="V3 pre-A/B gate",
                    status="offline",
                    detail=detail,
                    last_update=self._format_time(now),
                ),
            ]

        local_now = now.astimezone(SAO_PAULO)
        due_today = local_now.replace(hour=1, minute=0, second=0, microsecond=0)
        expected_due = due_today if local_now >= due_today else due_today - timedelta(days=1)
        window_end = due_today.replace(hour=8)
        published: dict[str, datetime] = {}
        for key, snapshot in snapshots.items():
            value = snapshot.get("published_at")
            if isinstance(value, datetime):
                published[key] = value if value.tzinfo else value.replace(tzinfo=timezone.utc)

        missing = [key.split("_")[0] for key in keys if key not in published]
        stale = [
            key.split("_")[0]
            for key, value in published.items()
            if value.astimezone(SAO_PAULO) < expected_due
        ]
        if not published:
            cycle_status = "attention"
            cycle_detail = "First V2.1b evidence pending · scheduled window 01:00–08:00 BRT"
            cycle_update = self._format_time(now)
        elif not missing and not stale:
            cycle_status = "healthy"
            cycle_detail = "B3 and US peer-quality snapshots completed for the expected cycle"
            cycle_update = self._format_time(min(published.values()))
        else:
            inside_current_window = due_today <= local_now < window_end and expected_due == due_today
            cycle_status = "attention" if inside_current_window else "offline"
            pending = sorted(set(missing + stale))
            cycle_detail = (
                f"Expected cycle since {expected_due:%d/%m %H:%M} BRT · pending: "
                + ", ".join(pending)
            )
            cycle_update = (
                self._format_time(max(published.values()))
                if published
                else self._format_time(now)
            )

        reports: dict[str, dict[str, Any]] = {}
        for key, snapshot in snapshots.items():
            report = snapshot.get("output")
            if isinstance(report, dict):
                reports[key.split("_")[0]] = report

        if len(reports) < 2:
            gate_status = "attention"
            gate_detail = "Pre-A/B report pending for: " + ", ".join(
                market for market in ("B3", "US") if market not in reports
            )
        else:
            failed: list[str] = []
            for market, report in sorted(reports.items()):
                gates = report.get("gates")
                if not isinstance(gates, dict):
                    failed.append(f"{market}:report_malformed")
                    continue
                failed.extend(
                    f"{market}:{name}"
                    for name, passed in gates.items()
                    if passed is not True
                )
                if report.get("pre_ab_ready") is not True and not any(
                    item.startswith(f"{market}:") for item in failed
                ):
                    failed.append(f"{market}:pre_ab_ready")
            gate_status = "offline" if failed else "healthy"
            gate_detail = (
                "All five frozen gates pass in B3 and US"
                if not failed
                else "Blocked · " + ", ".join(failed)
            )

        return [
            IntegrationHealth(
                name="Valuation V2.1b cycle",
                status=cycle_status,
                detail=cycle_detail,
                last_update=cycle_update,
            ),
            IntegrationHealth(
                name="V3 pre-A/B gate",
                status=gate_status,
                detail=gate_detail,
                last_update=cycle_update,
            ),
        ]

    def _day_d_disk_health(self, now: datetime) -> IntegrationHealth:
        root = self.settings.day_d_dataset_root
        minimum_free_bytes = int(self.settings.day_d_dataset_min_free_disk_gb * 1024**3)
        try:
            usage = self.disk_usage(root)
            free_bytes = int(usage.free)
        except Exception as exc:
            return IntegrationHealth(
                name="Day D disk reserve",
                status="offline",
                detail=f"Dedicated mount unavailable · {self._safe_error(exc)}",
                last_update=self._format_time(now),
            )
        status = "healthy" if free_bytes >= minimum_free_bytes else "offline"
        return IntegrationHealth(
            name="Day D disk reserve",
            status=status,
            detail=(
                f"{free_bytes / 1024**3:.1f} GiB free · frozen minimum "
                f"{minimum_free_bytes / 1024**3:.1f} GiB · {root}"
            ),
            last_update=self._format_time(now),
        )

    def _b2_zero_cap_health(self, now: datetime) -> IntegrationHealth:
        root = self.settings.day_d_dataset_root
        reports_root = root / "provider=backblaze" / "raw-restore-reports"
        try:
            reports = [
                (path, self._read_evidence(path))
                for path in reports_root.glob("lot_id=*/raw-restore-*.json")
            ]
        except Exception as exc:
            return IntegrationHealth(
                name="B2 zero-cap evidence",
                status="offline",
                detail=f"Evidence check failed · {self._safe_error(exc)}",
                last_update=self._format_time(now),
            )
        if not reports:
            return IntegrationHealth(
                name="B2 zero-cap evidence",
                status="healthy",
                detail="No RAW restore drill is waiting for a zero-cap restoration record",
                last_update=self._format_time(now),
            )

        raw_path, raw = max(
            reports,
            key=lambda item: self._evidence_time(item[1]) or datetime.min.replace(tzinfo=timezone.utc),
        )
        lot_id = str(raw.get("lot_id") or "unknown")
        if raw.get("schema_version") != "DAY-D-B2-RAW-RESTORE-v1" or raw.get("passed") is not True:
            return IntegrationHealth(
                name="B2 zero-cap evidence",
                status="offline",
                detail=f"Latest RAW drill is not valid · lot {lot_id}",
                last_update=self._evidence_display_time(raw, now),
            )

        expected_ref = {
            "path": str(raw_path.resolve()),
            "sha256": self._sha256_file(raw_path),
        }
        cap_root = root / "provider=backblaze" / "billing-cap-evidence" / f"lot_id={lot_id}"
        try:
            caps = [self._read_evidence(path) for path in cap_root.glob("billing-cap-*.json")]
        except Exception as exc:
            return IntegrationHealth(
                name="B2 zero-cap evidence",
                status="offline",
                detail=f"Cap evidence check failed · {self._safe_error(exc)}",
                last_update=self._evidence_display_time(raw, now),
            )
        valid_caps = [
            cap
            for cap in caps
            if cap.get("schema_version") == "DAY-D-B2-BILLING-CAP-v1"
            and cap.get("operator_attestation") is True
            and cap.get("raw_restore_report") == expected_ref
            and self._exact_zero(cap.get("original_cap_usd_per_day"))
            and self._exact_zero(cap.get("final_cap_usd_per_day"))
            and self._payload_time(cap, "restored_at") is not None
        ]
        if not valid_caps:
            return IntegrationHealth(
                name="B2 zero-cap evidence",
                status="offline",
                detail=f"Zero-cap restoration is not evidenced · lot {lot_id} · deletion remains blocked",
                last_update=self._evidence_display_time(raw, now),
            )
        latest_cap = max(
            valid_caps,
            key=lambda item: self._evidence_time(item) or datetime.min.replace(tzinfo=timezone.utc),
        )
        return IntegrationHealth(
            name="B2 zero-cap evidence",
            status="healthy",
            detail=f"Exact US$0/day restoration evidenced · lot {lot_id}",
            last_update=self._evidence_display_time(latest_cap, now),
        )

    @staticmethod
    def _read_evidence(path: Path) -> dict[str, Any]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"evidence is not an object: {path}")
        return payload

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _verified_result_evidence(
        self,
        path: Path,
        *,
        schema: str,
    ) -> dict[str, Any]:
        self._require_sha256s_entry(path)
        payload = self._read_evidence(path)
        if payload.get("schema") != schema or payload.get("status") != "succeeded":
            raise ValueError(f"unexpected evidence contract: {path.name}")
        declared_self_hash = str(payload.get("self_sha256") or "")
        canonical_payload = dict(payload)
        canonical_payload.pop("self_sha256", None)
        canonical = json.dumps(
            canonical_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        actual_self_hash = hashlib.sha256(canonical).hexdigest()
        if not declared_self_hash or declared_self_hash != actual_self_hash:
            raise ValueError(f"self-hash mismatch: {path.name}")
        return payload

    def _require_sha256s_entry(self, path: Path) -> None:
        sums_path = path.with_name("SHA256SUMS")
        expected: str | None = None
        for line in sums_path.read_text(encoding="utf-8").splitlines():
            fields = line.strip().split(maxsplit=1)
            if len(fields) != 2:
                continue
            filename = fields[1].lstrip("*")
            if filename == path.name:
                expected = fields[0]
                break
        if expected is None or expected != self._sha256_file(path):
            raise ValueError(f"SHA256SUMS mismatch: {path.name}")

    @staticmethod
    def _evidence_time(payload: dict[str, Any]) -> datetime | None:
        return SystemHealthService._payload_time(payload, "measured_at")

    @staticmethod
    def _payload_time(payload: dict[str, Any], key: str) -> datetime | None:
        try:
            value = datetime.fromisoformat(str(payload.get(key) or ""))
        except ValueError:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    @staticmethod
    def _exact_zero(value: Any) -> bool:
        try:
            return float(value) == 0.0
        except (TypeError, ValueError):
            return False

    def _evidence_display_time(self, payload: dict[str, Any], fallback: datetime) -> str:
        return self._format_time(self._evidence_time(payload) or fallback)

    def _automation_health(self, now: datetime) -> list[IntegrationHealth]:
        try:
            snapshot = self.legacy.read()
        except Exception as exc:
            return [self._offline_item("Summary scheduler", exc, now)]

        generated_at = snapshot.get("generated_at")
        if not isinstance(generated_at, datetime):
            generated_at = now
        if generated_at.tzinfo is None:
            generated_at = generated_at.astimezone()
        age_hours = max(0.0, (now - generated_at.astimezone(timezone.utc)).total_seconds() / 3600)
        report_status = "healthy" if age_hours <= 13 else "attention" if age_hours <= 24 else "offline"
        items = [IntegrationHealth(
            name="Summary scheduler",
            status=report_status,
            detail="Morning · Lunch · Night summaries",
            last_update=self._format_time(generated_at),
        )]

        display_names = {
            "AWS cron": "AWS scheduler",
            "PDF enviado": "PDF generation",
        }
        for item in snapshot.get("integrations", []):
            if item.name not in display_names:
                continue
            item_status = item.status
            if age_hours > 13 and item_status == "healthy":
                item_status = "attention"
            items.append(IntegrationHealth(
                name=display_names[item.name],
                status=item_status,
                detail=item.detail,
                last_update=item.last_update,
            ))
        return items

    def _safe_items(
        self,
        name: str,
        loader: Callable[[], list[IntegrationHealth]],
        now: datetime,
    ) -> list[IntegrationHealth]:
        try:
            items = loader()
            return items or [IntegrationHealth(
                name=name,
                status="offline",
                detail="No health signal returned",
                last_update=self._format_time(now),
            )]
        except Exception as exc:
            return [self._offline_item(name, exc, now)]

    def _offline_item(self, name: str, exc: Exception, now: datetime) -> IntegrationHealth:
        timed_out = self._is_timeout_error(exc)
        if timed_out:
            logger.warning(
                "System-health external probe timed out: %s (%s)",
                name,
                exc.__class__.__name__,
            )
        return IntegrationHealth(
            name=name,
            status="attention" if timed_out else "offline",
            detail=(
                f"Status unknown · health probe timed out · {self._safe_error(exc)}"
                if timed_out
                else f"Health check failed · {self._safe_error(exc)}"
            ),
            last_update=self._format_time(now),
            metadata={"probe_status": "timed_out" if timed_out else "failed"},
        )

    @staticmethod
    def _is_timeout_error(exc: Exception) -> bool:
        return isinstance(exc, (TimeoutError, httpx.TimeoutException)) or "timeout" in (
            exc.__class__.__name__.lower()
        )

    def _group(self, key: str, label: str, items: list[IntegrationHealth]) -> SystemHealthGroup:
        healthy_count = sum(item.status == "healthy" for item in items)
        return SystemHealthGroup(
            key=key,
            label=label,
            status=self._aggregate_status([item.status for item in items]),
            healthy_count=healthy_count,
            total_count=len(items),
            items=items,
        )

    @staticmethod
    def _aggregate_status(statuses: list[str]) -> str:
        if statuses and all(status == "healthy" for status in statuses):
            return "healthy"
        if statuses and all(status == "offline" for status in statuses):
            return "offline"
        return "attention"

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.astimezone(SAO_PAULO).strftime("%d/%m %H:%M")

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        message = str(exc).replace("\n", " ").strip()
        message = re.sub(
            r"(?i)(api_key|apikey|api_token|token|application_key|applicationkey|secret_key|secretkey)=([^&\s]+)",
            r"\1=[redacted]",
            message,
        )
        return message[:180] or exc.__class__.__name__
