from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]


def test_summary_runtime_json_uses_the_mounted_outputs_directory() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    cloud_run = (ROOT / "work" / "cloud_run.sh").read_text(encoding="utf-8")

    assert "./work/whatsapp_unread_today.json" not in compose
    for service in ("morning-summary", "whatsapp-login", "whatsapp-capture"):
        match = re.search(
            rf"(?ms)^  {re.escape(service)}:\n.*?(?=^  [A-Za-z0-9_-]+:\n|\Z)",
            compose,
        )
        assert match is not None
        assert "- ./outputs:/app/outputs" in match.group(0)
    assert '"--output", "outputs/whatsapp_unread_today.json"' in compose
    assert "work/whatsapp_unread_today.json" not in cloud_run
    assert cloud_run.count("outputs/whatsapp_unread_today.json") == 2
