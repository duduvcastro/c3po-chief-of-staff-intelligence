from __future__ import annotations

from datetime import datetime, timezone
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
    ) -> None:
        self.settings = settings
        self.database = database
        self.legacy = legacy
        self.open_finance = open_finance
        self.market_data = market_data
        self.server_usage = server_usage
        self.cache_seconds = cache_seconds
        self.external_get = external_get or httpx.get
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

    def _external_services_health(self, now: datetime) -> list[IntegrationHealth]:
        return [
            self._cloudflare_health(now),
            self._github_health(now),
            self._intermedia_health(now),
            self._open_meteo_health(now),
        ]

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
        return message[:180] or exc.__class__.__name__
