from datetime import datetime
from pathlib import Path

from app.legacy import LegacySummaryReader


def test_latest_legacy_summary_is_normalized() -> None:
    root = Path(__file__).resolve().parents[3]
    snapshot = LegacySummaryReader(root).read()

    assert snapshot["report_title"]
    assert set(snapshot["markets"]) == {"Index", "Currencies", "CRIPTO"}
    assert len(snapshot["portfolio"]) >= 1
    assert snapshot["billfish"].get("source") == "BTG PDF"
    assert snapshot["billfish"].get("net_worth") == "R$ 23.718.117,35"
    assert len(snapshot["metrics"]) == 4


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
