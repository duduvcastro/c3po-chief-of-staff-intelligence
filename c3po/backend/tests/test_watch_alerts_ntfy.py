import hashlib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "c3po" / "compose.yml"
PIPELINE = ROOT / ".github" / "workflows" / "c3po-pipeline.yml"
NTFY_CONFIG = ROOT / "c3po" / "ntfy" / "server.yml"
CADDY = ROOT / "Caddyfile"
SPEC = ROOT / "c3po" / "docs" / "C3PO_WATCH_ALERTS_NTFY_V1.md"
EXPECTED_SPEC_SHA256 = "91a58458a5c5a48f0124c344d1429daaeea8f7a9defa9abb9c930fea3982e076"
NTFY_IMAGE = (
    "binwiederhier/ntfy:v2.28.0@"
    "sha256:6ef4b819f722fccdc036af611c4774cfdc2de821ab74fdd48bbf4c9d6f8973da"
)


def test_frozen_watch_contract_is_byte_identical_to_the_signed_hash() -> None:
    assert hashlib.sha256(SPEC.read_bytes()).hexdigest() == EXPECTED_SPEC_SHA256


def test_ntfy_service_is_digest_pinned_private_and_fail_closed() -> None:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    service = compose["services"]["ntfy"]
    config = yaml.safe_load(NTFY_CONFIG.read_text(encoding="utf-8"))

    assert service["image"] == NTFY_IMAGE
    assert "ports" not in service
    assert service["restart"] == "unless-stopped"
    assert service["healthcheck"]["timeout"] == "3s"
    assert service["networks"]["legacy_proxy"]["aliases"] == ["c3po-ntfy"]
    assert config["auth-default-access"] == "deny-all"
    assert config["upstream-base-url"] == "https://ntfy.sh"
    assert config["base-url"] == "https://ntfy.eduardocastro.com.br"
    assert config["web-root"] == "disable"


def test_ntfy_is_only_exposed_through_the_existing_caddy_network() -> None:
    caddy = CADDY.read_text(encoding="utf-8")

    assert "ntfy.eduardocastro.com.br" in caddy
    assert "reverse_proxy c3po-ntfy:80" in caddy
    assert "X-Robots-Tag" in caddy


def test_pipeline_separates_device_secret_and_requires_healthy_relay() -> None:
    workflow = PIPELINE.read_text(encoding="utf-8")
    stage = workflow.split("Stage push and Watch alert configuration", 1)[1].split(
        "- name: Deploy and verify", 1
    )[0]
    remote = workflow.split("<<'REMOTE'", 1)[1].split("REMOTE", 1)[0]

    for secret in (
        "C3PO_NTFY_AUTH_USERS",
        "C3PO_NTFY_TOPIC",
        "C3PO_NTFY_PUBLISH_TOKEN",
        "C3PO_NTFY_SUBSCRIBE_TOKEN",
    ):
        assert secret in stage
    assert "c3po-publisher" in stage
    assert ":wo,dudu-devices:" in stage
    assert ":ro" in stage
    assert "c3po/ntfy.env" in remote
    assert "ntfy_target.chmod(0o600)" in remote
    assert "--exclude='c3po/ntfy.env'" in remote
    assert "C3PO_NTFY_SUBSCRIBE_TOKEN" not in remote
    assert f"docker pull {NTFY_IMAGE}" in remote
    assert "caddy validate" in remote
    assert "caddy reload" in remote
    assert 'ntfy_status" = "healthy"' in remote
    assert "ntfy deny-all gate failed" in remote
    assert "401|403" in remote
    assert "logs --tail=120 api web ntfy" in remote


def test_ntfy_updates_are_manual_only() -> None:
    repository_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (COMPOSE, PIPELINE, ROOT / "docker-compose.yml")
    ).lower()

    assert "watchtower" not in repository_text
    assert "manual-only" in (
        ROOT / "c3po" / "docs" / "C3PO_WATCH_ALERTS_NTFY_V1_RUNBOOK.md"
    ).read_text(encoding="utf-8")
