import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
PIPELINE = ROOT / ".github" / "workflows" / "c3po-pipeline.yml"
COMPOSE = ROOT / "c3po" / "compose.yml"


def test_all_application_services_use_the_two_named_images() -> None:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = compose["services"]

    for service in (
        "api",
        "investor-relations-worker",
        "valuation-worker",
        "server-usage-worker",
        "r2d2-worker",
    ):
        assert services[service]["image"] == "c3po/backend:production"
        assert services[service]["build"]["dockerfile"] == "backend/Dockerfile"

    assert services["web"]["image"] == "c3po/web:production"
    assert services["web"]["build"]["context"] == "./frontend"


def test_production_builds_and_transfers_images_before_connecting_to_host() -> None:
    workflow = PIPELINE.read_text(encoding="utf-8")

    build_index = workflow.index("Build production images outside the server")
    ssh_index = workflow.index("Configure deployment SSH key")
    assert build_index < ssh_index
    assert "--file c3po/backend/Dockerfile" in workflow
    assert "--file c3po/frontend/Dockerfile" in workflow
    assert "docker save c3po/backend:production c3po/web:production" in workflow
    assert "sha256sum --check \"$IMAGE_SHA256\"" in workflow
    assert "gzip -dc \"$IMAGE_ARCHIVE\" | docker load" in workflow
    assert "org.opencontainers.image.revision" in workflow


def test_production_host_never_builds_and_has_image_rollback() -> None:
    workflow = PIPELINE.read_text(encoding="utf-8")
    remote = workflow.split("<<'REMOTE'", 1)[1].split("REMOTE", 1)[0]

    assert re.search(r"^\s*docker build(?:\s|$)", remote, re.MULTILINE) is None
    assert "buildx" not in remote
    assert "--build" not in remote
    assert remote.count("up -d --no-build") == 2
    assert "c3po/backend:rollback" in remote
    assert "c3po/web:rollback" in remote
    assert "health gate failed; restoring the prior container images" in remote
    assert 'C3PO_BUILD_SHA="$PREVIOUS_REVISION"' in remote
    assert "rollback health gate restored the prior images" in remote
    assert "docker builder prune --force" in remote


def test_v1_does_not_add_a_registry_or_registry_credentials() -> None:
    workflow = PIPELINE.read_text(encoding="utf-8").lower()

    assert "ghcr.io" not in workflow
    assert "docker login" not in workflow
