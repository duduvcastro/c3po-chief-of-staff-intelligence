from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[2] / "compose.yml"
JOURNALD_SERVICES = ("api", "server-usage-worker", "r2d2-worker", "r2d2-shadow-candidate-worker")


def test_operational_services_log_to_journald() -> None:
    """O5 (mesa 04/09/2026): a deploy recreates containers, and the default json-file log dies with
    the container it belonged to — the whole 04/09 session log of the R2D2 worker was lost that way.
    journald outlives the container, so `journalctl CONTAINER_NAME=<name> --since … --until …`
    keeps working after any deploy or restart."""
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    for name in JOURNALD_SERVICES:
        logging = services[name].get("logging") or {}
        assert logging.get("driver") == "journald", name
        assert (logging.get("options") or {}).get("tag") == "{{.Name}}", name


def test_database_and_web_keep_the_default_driver() -> None:
    """Scope guard: O5 touches only the four operational services named in the ratified item."""
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    for name in ("db", "web", "investor-relations-worker", "valuation-worker"):
        assert "logging" not in services[name], name
