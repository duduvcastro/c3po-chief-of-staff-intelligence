from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .schemas import IntegrationHealth, MarketItem, Metric, PortfolioItem


SECTION_NAMES = {
    "Markets",
    "Billfish FIA",
    "Brokerage Notes",
    "Candidate Stocks",
    "Agenda",
    "Forecast",
    "News",
    "Decision Queue",
    "Follow-ups Pendentes",
    "BRASILEIRAO",
    "Automation Health",
    "DAILY PRIORITIES",
}


class LegacySummaryReader:
    def __init__(self, root: Path) -> None:
        self.root = root

    def latest_report(self) -> Path | None:
        output_dir = self.root / "outputs"
        reports = list(output_dir.glob("*summary-*.txt"))
        return max(reports, key=lambda item: item.stat().st_mtime) if reports else None

    def read(self) -> dict:
        path = self.latest_report()
        if path is None:
            return self._empty_snapshot()

        content = path.read_text(encoding="utf-8", errors="replace")
        lines = [line.rstrip() for line in content.splitlines()]
        title = lines[0] if lines else "C3PO"
        generated = self._parse_generated(lines)
        report_date = self._parse_report_date(title)

        return {
            "generated_at": generated,
            "report_title": title,
            "report_path": str(path),
            "report_date": report_date,
            "metrics": self._metrics(lines),
            "markets": self._markets(lines),
            "portfolio": self._portfolio(lines),
            "billfish": self._billfish(lines),
            "priorities": self._bullets(self._section(lines, "DAILY PRIORITIES"), numbered=True),
            "agenda": self._bullets(self._section(lines, "Agenda")),
            "decision_queue": self._decisions(lines),
            "integrations": self._health(lines, generated),
        }

    def report_history(self, limit: int = 20) -> list[dict[str, str]]:
        reports = sorted(
            (self.root / "outputs").glob("*summary-*.pdf"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[:limit]
        return [
            {
                "name": report.name,
                "path": str(report),
                "updated_at": datetime.fromtimestamp(report.stat().st_mtime).isoformat(),
                "size": self._human_size(report.stat().st_size),
            }
            for report in reports
        ]

    def _empty_snapshot(self) -> dict:
        now = datetime.now().astimezone()
        return {
            "generated_at": now,
            "report_title": "C3PO",
            "report_path": None,
            "report_date": now.strftime("%d/%m/%Y"),
            "metrics": [],
            "markets": {"Index": [], "Currencies": [], "CRIPTO": []},
            "portfolio": [],
            "billfish": {},
            "priorities": [],
            "agenda": [],
            "decision_queue": [],
            "integrations": [],
        }

    def _parse_generated(self, lines: list[str]) -> datetime:
        for line in lines[:6]:
            match = re.search(r"Gerado em (\d{2}/\d{2}/\d{4}) (\d{2}:\d{2})", line)
            if match:
                return datetime.strptime(" ".join(match.groups()), "%d/%m/%Y %H:%M").astimezone()
        return datetime.now().astimezone()

    def _parse_report_date(self, title: str) -> str:
        match = re.search(r"(\d{2}/\d{2}/\d{4})", title)
        return match.group(1) if match else ""

    def _section(self, lines: list[str], name: str) -> list[str]:
        try:
            start = lines.index(name) + 1
        except ValueError:
            return []
        result: list[str] = []
        for line in lines[start:]:
            if line in SECTION_NAMES:
                break
            result.append(line)
        return result

    def _subsection(self, lines: list[str], parent: str, name: str, stops: set[str]) -> list[str]:
        section = self._section(lines, parent)
        try:
            start = section.index(name) + 1
        except ValueError:
            return []
        result: list[str] = []
        for line in section[start:]:
            if line in stops:
                break
            result.append(line)
        return result

    def _bullets(self, lines: Iterable[str], numbered: bool = False) -> list[str]:
        values = []
        pattern = r"^\d+\.\s+" if numbered else r"^-\s+"
        for line in lines:
            if re.match(pattern, line):
                values.append(re.sub(pattern, "", line).strip())
        return values

    def _market_rows(self, lines: Iterable[str]) -> list[MarketItem]:
        rows = []
        for line in lines:
            match = re.match(r"^- ([^:]+): (.+?) \| (.+?) \| (.+)$", line)
            if not match:
                continue
            symbol, price, change, time = match.groups()
            rows.append(
                MarketItem(
                    symbol=symbol,
                    price=price,
                    change=change,
                    time=time,
                    direction=self._direction(change),
                )
            )
        return rows

    def _markets(self, lines: list[str]) -> dict[str, list[MarketItem]]:
        stops = {"Index", "Currencies", "CRIPTO", "Portfolio Stocks"}
        return {
            "Index": self._market_rows(self._subsection(lines, "Markets", "Index", stops)),
            "Currencies": self._market_rows(self._subsection(lines, "Markets", "Currencies", stops)),
            "CRIPTO": self._market_rows(self._subsection(lines, "Markets", "CRIPTO", stops)),
        }

    def _portfolio(self, lines: list[str]) -> list[PortfolioItem]:
        rows = self._market_rows(
            self._subsection(
                lines,
                "Markets",
                "Portfolio Stocks",
                {"Index", "Currencies", "CRIPTO", "Portfolio Stocks"},
            )
        )
        return [
            PortfolioItem(symbol=row.symbol, price=row.price, change=row.change, direction=row.direction)
            for row in rows
        ]

    def _billfish(self, lines: list[str]) -> dict[str, str]:
        section = self._section(lines, "Billfish FIA")
        row = next((line for line in section if line.startswith("- Status ")), "")
        if not row:
            return {}
        fields = [field.strip() for field in row[2:].split("|")]
        result = {"raw": row[2:]}
        labels = {
            "Status ": "status",
            "daily change ": "daily_change",
            "net worth change ": "net_worth_change",
            "net worth ": "net_worth",
            "fonte ": "source",
            "Month: ": "month",
            "Year: ": "year",
        }
        for field in fields:
            for prefix, key in labels.items():
                if field.startswith(prefix):
                    result[key] = field[len(prefix) :].strip()
                    break
        return result

    def _decisions(self, lines: list[str]) -> list[dict[str, str]]:
        rows = []
        for item in self._bullets(self._section(lines, "Decision Queue")):
            subject, separator, rest = item.partition(": ")
            body, action_separator, action = rest.partition(" | Acao: ")
            rows.append(
                {
                    "subject": subject,
                    "context": body if separator else "",
                    "action": action if action_separator else rest,
                }
            )
        return rows

    def _metrics(self, lines: list[str]) -> list[Metric]:
        decisions = len(self._bullets(self._section(lines, "Decision Queue")))
        agenda = len(self._bullets(self._section(lines, "Agenda")))
        followups = len(self._bullets(self._section(lines, "Follow-ups Pendentes")))
        whatsapp = 0
        whatsapp_file = self.root / "work" / "whatsapp_unread_today.json"
        if whatsapp_file.exists():
            try:
                import json

                payload = json.loads(whatsapp_file.read_text(encoding="utf-8"))
                whatsapp = len(payload) if isinstance(payload, list) else len(payload.get("messages", []))
            except (OSError, ValueError, TypeError):
                whatsapp = 0

        return [
            Metric(label="Decisions", value=str(decisions), detail="waiting for review", tone="critical" if decisions else "neutral"),
            Metric(label="Follow-ups", value=str(followups), detail="open threads", tone="warning" if followups else "neutral"),
            Metric(label="Agenda", value=str(agenda), detail="today's commitments"),
            Metric(label="WhatsApp", value=str(whatsapp), detail="unread messages", tone="warning" if whatsapp else "positive"),
        ]

    def _health(self, lines: list[str], generated: datetime) -> list[IntegrationHealth]:
        parsed = {}
        for item in self._bullets(self._section(lines, "Automation Health")):
            name, separator, detail = item.partition(": ")
            if separator:
                parsed[name] = detail

        names = ["Email", "WhatsApp", "AWS cron", "PDF enviado"]
        result = []
        for name in names:
            detail = parsed.get(name, "No recent status")
            normalized = detail.lower()
            negative_tokens = (
                "atencao",
                "erro",
                "failed",
                "indisponivel",
                "nao configurado",
                "nao disponivel",
                "not_logged_in",
                "sem dados",
            )
            has_failure = any(token in normalized for token in negative_tokens)
            has_success = any(token in normalized for token in ("ok", "fonte encontrada", "sim", "enviado"))
            if name == "AWS cron":
                has_success = bool(re.search(r"ultima execucao \d{2}/\d{2} \d{2}:\d{2}", normalized))
            status = "healthy" if has_success and not has_failure else "attention"
            result.append(
                IntegrationHealth(
                    name=name,
                    status=status,
                    detail=detail,
                    last_update=generated.strftime("%d/%m %H:%M"),
                )
            )
        return result

    @staticmethod
    def _direction(value: str) -> str:
        if "+" in value:
            return "up"
        if "-" in value:
            return "down"
        return "flat"

    @staticmethod
    def _human_size(value: int) -> str:
        if value < 1024 * 1024:
            return f"{value / 1024:.0f} KB"
        return f"{value / (1024 * 1024):.1f} MB"
