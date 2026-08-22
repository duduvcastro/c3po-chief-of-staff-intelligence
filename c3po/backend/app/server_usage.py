from __future__ import annotations

import csv
import shutil
from collections import deque
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Any

from .api_performance import api_performance
from .config import Settings
from .database import Database
from .schemas import ServerUsageCurrent, ServerUsagePoint, ServerUsageResponse, ServerUsageServer


class ServerUsageCollector:
    def __init__(self, settings: Settings, database: Database) -> None:
        self.settings = settings
        self.database = database

    def cpu_ticks(self) -> tuple[int, int]:
        line = self.settings.server_usage_proc_stat_path.read_text(encoding="utf-8").splitlines()[0]
        fields = line.split()
        if not fields or fields[0] != "cpu":
            raise RuntimeError("Host /proc/stat does not contain an aggregate CPU row")
        values = [int(value) for value in fields[1:]]
        total = sum(values)
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return total, idle

    def disk_usage(self) -> tuple[int, int, int]:
        usage = shutil.disk_usage(self.settings.server_usage_disk_path)
        return usage.total, usage.used, usage.free

    def sample(self, previous: tuple[int, int], current: tuple[int, int], *, collected_at: datetime | None = None) -> dict[str, Any]:
        total_delta = current[0] - previous[0]
        idle_delta = current[1] - previous[1]
        cpu_percent = None
        if total_delta > 0:
            cpu_percent = max(0.0, min(100.0, (1 - idle_delta / total_delta) * 100))
        disk_total, disk_used, disk_free = self.disk_usage()
        return {
            "server_id": self.settings.server_usage_server_id,
            "server_name": self.settings.server_usage_server_name,
            "region": self.settings.server_usage_region,
            "collected_at": collected_at or datetime.now(timezone.utc),
            "cpu_percent": round(cpu_percent, 3) if cpu_percent is not None else None,
            "disk_total_bytes": disk_total,
            "disk_used_bytes": disk_used,
            "disk_free_bytes": disk_free,
            "source": "procfs+statvfs",
        }

    def import_sadf(self, payload: str) -> int:
        samples: list[dict[str, Any]] = []
        reader = csv.reader(StringIO(payload), delimiter=";")
        for row in reader:
            if not row or row[0].startswith("#") or len(row) < 10 or row[3] != "-1":
                continue
            try:
                collected_at = datetime.strptime(row[2], "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
                cpu_percent = 100.0 - float(row[9])
            except (ValueError, IndexError):
                continue
            samples.append({
                "server_id": self.settings.server_usage_server_id,
                "server_name": self.settings.server_usage_server_name,
                "region": self.settings.server_usage_region,
                "collected_at": collected_at,
                "cpu_percent": round(max(0.0, min(100.0, cpu_percent)), 3),
                "disk_total_bytes": None,
                "disk_used_bytes": None,
                "disk_free_bytes": None,
                "source": "sysstat-backfill",
            })
        return self.database.save_server_usage_samples(samples)


class ServerUsageService:
    def __init__(self, settings: Settings, database: Database) -> None:
        self.settings = settings
        self.database = database

    def snapshot(self, *, hours: int = 24) -> ServerUsageResponse:
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=hours)
        rows = self.database.list_server_usage_samples(since)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(str(row["server_id"]), []).append(row)

        servers: list[ServerUsageServer] = []
        for server_id, samples in grouped.items():
            samples.sort(key=lambda item: item["collected_at"])
            history = self._moving_average(samples)
            latest = samples[-1]
            latest_point = history[-1]
            age_seconds = (now - latest["collected_at"]).total_seconds()
            status = "healthy" if age_seconds <= 180 else "attention" if age_seconds <= 900 else "offline"
            servers.append(ServerUsageServer(
                server_id=server_id,
                server_name=str(latest["server_name"]),
                region=str(latest["region"]),
                cpu_count=self.settings.server_usage_cpu_count,
                status=status,
                current=ServerUsageCurrent(
                    cpu_percent=latest_point.cpu_percent,
                    cpu_moving_average_5m=latest_point.cpu_moving_average_5m,
                    disk_percent=latest_point.disk_percent,
                    disk_total_bytes=latest.get("disk_total_bytes"),
                    disk_used_bytes=latest.get("disk_used_bytes"),
                    disk_free_bytes=latest.get("disk_free_bytes"),
                    collected_at=latest["collected_at"],
                ),
                history=history,
            ))
        return ServerUsageResponse(
            generated_at=now,
            window_hours=hours,
            moving_average_minutes=5,
            refresh_seconds=60,
            servers=servers,
            api_endpoints=api_performance.snapshot(),
            api_window_minutes=api_performance.retention_minutes,
            methodology={
                "cpu": "Host aggregate CPU from Linux /proc/stat; initial 24h backfill from sysstat",
                "disk": "Host filesystem usage from statvfs; history starts with the C3PO collector",
                "smoothing": "Time-based rolling arithmetic mean over the preceding five minutes",
                "retention": f"{self.settings.server_usage_retention_days} days in PostgreSQL",
                "api": "In-process endpoint latency over a rolling 15-minute window",
            },
        )

    def capacity_alerts(self) -> list[dict[str, Any]]:
        snapshot = self.snapshot(hours=1)
        alerts: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        for server in snapshot.servers:
            collected_at = server.current.collected_at
            if collected_at is None or (now - collected_at).total_seconds() > 300:
                continue

            recent_cutoff = collected_at - timedelta(minutes=5)
            recent_cpu = [
                point.cpu_percent
                for point in server.history
                if point.collected_at >= recent_cutoff and point.cpu_percent is not None
            ]
            cpu_peak = max(recent_cpu) if recent_cpu else None
            cpu_average = sum(recent_cpu) / len(recent_cpu) if recent_cpu else None
            cpu_critical = (
                cpu_peak is not None
                and cpu_peak >= self.settings.server_usage_cpu_peak_critical_percent
            ) or (
                cpu_average is not None
                and cpu_average >= self.settings.server_usage_cpu_average_critical_percent
            )
            cpu_warning = cpu_critical or (
                cpu_peak is not None
                and cpu_peak >= self.settings.server_usage_cpu_peak_warning_percent
            ) or (
                cpu_average is not None
                and cpu_average >= self.settings.server_usage_cpu_average_warning_percent
            )
            if cpu_warning:
                level = "critical" if cpu_critical else "warning"
                severity = "Critical" if cpu_critical else "Capacity"
                alerts.append({
                    "id": f"capacity:cpu:{server.server_id}:{level}:{collected_at.strftime('%Y-%m-%d-%H')}",
                    "subject": f"{'CPU em nível crítico' if cpu_critical else 'Pico de CPU detectado'} · {server.server_name}",
                    "context": f"{server.region} · janela móvel de 5 minutos",
                    "action": (
                        f"Pico de {cpu_peak:.1f}% e média de {cpu_average:.1f}% nos últimos 5 minutos. "
                        f"{'Investigar processos e containers imediatamente.' if cpu_critical else 'Acompanhar a carga e identificar o processo responsável se o pico persistir.'}"
                    ),
                    "severity": severity,
                    "occurred_at": collected_at,
                    "source": "AWS Lightsail Telemetry",
                    "metadata": {
                        "Servidor": server.server_name,
                        "Região": server.region,
                        "CPU atual": self._percent(server.current.cpu_percent),
                        "CPU peak · 5 min": self._percent(cpu_peak),
                        "CPU média · 5 min": self._percent(cpu_average),
                        "Corte de aviso": self._percent(self.settings.server_usage_cpu_peak_warning_percent),
                        "Corte crítico": self._percent(self.settings.server_usage_cpu_peak_critical_percent),
                    },
                })

            disk_percent = server.current.disk_percent
            if disk_percent is None or disk_percent < self.settings.server_usage_disk_warning_percent:
                continue
            disk_critical = disk_percent >= self.settings.server_usage_disk_critical_percent
            level = "critical" if disk_critical else "warning"
            severity = "Critical" if disk_critical else "Capacity"
            alerts.append({
                "id": f"capacity:disk:{server.server_id}:{level}:{collected_at.strftime('%Y-%m-%d')}",
                "subject": f"{'Disco em nível crítico' if disk_critical else 'Capacidade de disco em atenção'} · {server.server_name}",
                "context": f"{server.region} · filesystem principal",
                "action": (
                    f"O disco está {disk_percent:.1f}% ocupado, com {self._bytes(server.current.disk_free_bytes)} livres. "
                    f"{'Liberar espaço imediatamente para preservar a operação.' if disk_critical else 'Revisar caches, imagens antigas e retenção de arquivos antes de atingir o nível crítico.'}"
                ),
                "severity": severity,
                "occurred_at": collected_at,
                "source": "AWS Lightsail Telemetry",
                "metadata": {
                    "Servidor": server.server_name,
                    "Região": server.region,
                    "Disco usado": self._percent(disk_percent),
                    "Espaço usado": self._bytes(server.current.disk_used_bytes),
                    "Espaço livre": self._bytes(server.current.disk_free_bytes),
                    "Capacidade total": self._bytes(server.current.disk_total_bytes),
                    "Corte de aviso": self._percent(self.settings.server_usage_disk_warning_percent),
                    "Corte crítico": self._percent(self.settings.server_usage_disk_critical_percent),
                },
            })
        return alerts

    @staticmethod
    def _percent(value: float | None) -> str:
        return "N/D" if value is None else f"{value:.1f}%"

    @staticmethod
    def _bytes(value: int | None) -> str:
        if value is None:
            return "N/D"
        amount = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if amount < 1024 or unit == "TB":
                return f"{amount:.1f} {unit}"
            amount /= 1024
        return f"{amount:.1f} TB"

    @staticmethod
    def _moving_average(samples: list[dict[str, Any]]) -> list[ServerUsagePoint]:
        cpu_window: deque[tuple[datetime, float]] = deque()
        output: list[ServerUsagePoint] = []
        for sample in samples:
            collected_at = sample["collected_at"]
            cpu = float(sample["cpu_percent"]) if sample.get("cpu_percent") is not None else None
            if cpu is not None:
                cpu_window.append((collected_at, cpu))
            cutoff = collected_at - timedelta(minutes=5)
            while cpu_window and cpu_window[0][0] < cutoff:
                cpu_window.popleft()
            moving_average = sum(value for _, value in cpu_window) / len(cpu_window) if cpu_window else None
            disk_total = sample.get("disk_total_bytes")
            disk_used = sample.get("disk_used_bytes")
            disk_percent = None
            if disk_total and disk_used is not None:
                disk_percent = float(disk_used) / float(disk_total) * 100
            output.append(ServerUsagePoint(
                collected_at=collected_at,
                cpu_percent=round(cpu, 2) if cpu is not None else None,
                cpu_moving_average_5m=round(moving_average, 2) if moving_average is not None else None,
                disk_percent=round(disk_percent, 2) if disk_percent is not None else None,
            ))
        return output
