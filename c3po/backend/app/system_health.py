from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any, Callable
from zoneinfo import ZoneInfo

import httpx

from .config import Settings
from .schemas import AiUsageMetric, ApiUsageMetric, IntegrationHealth, SystemHealthGroup, SystemHealthResponse


SAO_PAULO = ZoneInfo("America/Sao_Paulo")


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

    def snapshot(self, *, force: bool = False) -> SystemHealthResponse:
        now = datetime.now(timezone.utc)
        if (
            not force
            and self._cached_at
            and self._cached_response
            and (now - self._cached_at).total_seconds() < self.cache_seconds
        ):
            return self._cached_response

        api_usage = self._api_usage(now)
        ai_usage = self._ai_usage(now)
        groups = [
            self._group("apis", "Core APIs", [*self._core_api_health(now), self._api_usage_health(api_usage, now)]),
            self._group("external_services", "Contracted & External Services", self._external_services_health(now)),
            self._group("open_finance", "Pluggy & Banks", self._safe_items("Pluggy API", self.open_finance.integration_health, now)),
            self._group("aws", "AWS Infrastructure", self._aws_health(now)),
            self._group("controls", "Day D & Valuation Controls", self._day_d_and_valuation_health(now)),
            self._group("quotes", "Market Quotes", self._quote_health(now)),
            self._group("official_sources", "Official Intelligence", self._official_sources_health(now)),
            self._group("automations", "Automatic Routines", self._automation_health(now)),
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
        self._cached_at = now
        self._cached_response = response
        return response

    def _api_usage(self, now: datetime) -> list[ApiUsageMetric]:
        metrics: list[ApiUsageMetric] = []
        if self.settings.eodhd_api_token:
            try:
                base_url = self.settings.eodhd_base_url.rstrip("/")
                usage_url = f"{base_url}/user/" if base_url.endswith("/api") else f"{base_url}/api/user/"
                response = self.external_get(
                    usage_url,
                    params={"api_token": self.settings.eodhd_api_token, "fmt": "json"},
                    timeout=self.settings.system_health_external_timeout_seconds,
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
                timeout=self.settings.system_health_external_timeout_seconds,
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
                timeout=self.settings.system_health_external_timeout_seconds,
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
        try:
            probe = getattr(self.market_data, "probe_health", None)
            providers = probe() if callable(probe) else self.market_data.health()
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
        items.append(self._finnhub_health(now))
        items.append(self._fmp_health(now))
        items.append(self._massive_health(now))
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
                timeout=self.settings.system_health_external_timeout_seconds,
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
                timeout=self.settings.system_health_external_timeout_seconds,
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
                timeout=self.settings.system_health_external_timeout_seconds,
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
            self._open_meteo_health(now),
        ]

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
            config=Config(signature_version="s3v4"),
        )

    def _cloudflare_health(self, now: datetime) -> IntegrationHealth:
        url = f"{self.settings.public_url.rstrip('/')}/robots.txt"
        try:
            response = self.external_get(
                url,
                timeout=self.settings.system_health_external_timeout_seconds,
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
                timeout=self.settings.system_health_external_timeout_seconds,
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
                timeout=self.settings.system_health_external_timeout_seconds,
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
        try:
            servers = self.server_usage.snapshot(hours=1).servers
        except Exception as exc:
            return [self._offline_item("AWS Lightsail", exc, now)]
        if not servers:
            return [IntegrationHealth(
                name="AWS Lightsail",
                status="offline",
                detail="No recent server telemetry",
                last_update=self._format_time(now),
            )]

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
        return items

    def _day_d_and_valuation_health(self, now: datetime) -> list[IntegrationHealth]:
        return [
            *self._valuation_v2_1b_health(now),
            self._day_d_disk_health(now),
            self._b2_zero_cap_health(now),
        ]

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
        return IntegrationHealth(
            name=name,
            status="offline",
            detail=f"Health check failed · {self._safe_error(exc)}",
            last_update=self._format_time(now),
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
