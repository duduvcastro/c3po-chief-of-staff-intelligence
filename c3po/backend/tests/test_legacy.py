from datetime import datetime
from pathlib import Path

from app.legacy import LegacySummaryReader


def test_latest_legacy_summary_is_normalized(tmp_path) -> None:
    root = tmp_path
    output_dir = root / "outputs"
    output_dir.mkdir()
    (output_dir / "morning-summary-2026-08-17.txt").write_text(
        "\n".join(
            [
                "Morning Summary - 17/08/2026",
                "Gerado em 17/08/2026 07:00",
                "Markets",
                "Index",
                "- S&P 500: 6.500,00 | +0,50% | 07:00",
                "Currencies",
                "- USD/BRL: 5,40 | -0,10% | 07:00",
                "CRIPTO",
                "- BTC: 100.000,00 | +1,00% | 07:00",
                "Portfolio Stocks",
                "- AMZN: 220,00 | +0,25% | 07:00",
                "Billfish FIA",
                "- Status 15/08/2026 | net worth R$ 23.718.117,35 | fonte BTG PDF",
                "DAILY PRIORITIES",
                "1. Revisar a carteira",
            ]
        ),
        encoding="utf-8",
    )
    snapshot = LegacySummaryReader(root).read()

    assert snapshot["report_title"]
    assert set(snapshot["markets"]) == {"Index", "Currencies", "CRIPTO"}
    assert snapshot["portfolio"][0].symbol == "AMZN"
    assert snapshot["billfish"].get("source") == "BTG PDF"
    assert snapshot["billfish"].get("net_worth") == "R$ 23.718.117,35"
    assert snapshot["priorities"] == ["Revisar a carteira"]


def test_automation_health_recognizes_a_valid_cron_execution() -> None:
    root = Path(__file__).resolve().parents[3]
    reader = LegacySummaryReader(root)
    lines = [
        "Automation Health",
        "- AWS cron: ultima execucao 15/08 13:01",
        "DAILY PRIORITIES",
    ]

    health = {item.name: item for item in reader._health(lines, datetime.now().astimezone())}

    assert health["AWS cron"].status == "healthy"
    assert "Billfish BTG" not in health
    assert "Open Finance" not in health


def test_automation_health_keeps_missing_cron_log_in_attention() -> None:
    root = Path(__file__).resolve().parents[3]
    reader = LegacySummaryReader(root)
    lines = [
        "Automation Health",
        "- AWS cron: ultima execucao nao disponivel",
        "DAILY PRIORITIES",
    ]

    health = {item.name: item for item in reader._health(lines, datetime.now().astimezone())}

    assert health["AWS cron"].status == "attention"
