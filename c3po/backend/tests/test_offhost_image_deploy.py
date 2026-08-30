import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
PIPELINE = ROOT / ".github" / "workflows" / "c3po-pipeline.yml"
COMPOSE = ROOT / "c3po" / "compose.yml"
BACKEND_DOCKERFILE = ROOT / "c3po" / "backend" / "Dockerfile"
FRONTEND_DOCKERFILE = ROOT / "c3po" / "frontend" / "Dockerfile"
DATABASE_DOCKERFILE = ROOT / "c3po" / "database" / "Dockerfile"
BACKEND_REQUIREMENTS = ROOT / "c3po" / "backend" / "requirements.txt"
FRONTEND_DOCKERIGNORE = ROOT / "c3po" / "frontend" / ".dockerignore"
RESTORE_DRILL = ROOT / ".github" / "workflows" / "postgres-backup-restore-drill.yml"


def test_all_application_services_use_the_three_named_images() -> None:
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
    assert services["db"]["image"] == "c3po/database:production"
    assert services["db"]["build"]["dockerfile"] == "database/Dockerfile"


def test_production_builds_and_transfers_images_before_connecting_to_host() -> None:
    workflow = PIPELINE.read_text(encoding="utf-8")

    assert "Validate production Docker images" in workflow
    assert "github.event_name == 'pull_request' ||" in workflow
    assert "github.event_name == 'workflow_dispatch' && inputs.remediation" in workflow
    assert "c3po/backend:pr-validation" in workflow
    assert "c3po/web:pr-validation" in workflow
    assert "c3po/database:pr-validation" in workflow
    build_index = workflow.index("Build production images outside the server")
    ssh_index = workflow.index("Configure deployment SSH key")
    assert build_index < ssh_index
    assert "--file c3po/backend/Dockerfile" in workflow
    assert "--file c3po/frontend/Dockerfile" in workflow
    assert "--file c3po/database/Dockerfile" in workflow
    assert "docker save \\" in workflow
    assert "c3po/backend:production \\" in workflow
    assert "c3po/web:production \\" in workflow
    assert "c3po/database:production \\" in workflow
    assert "sha256sum --check \"$IMAGE_SHA256\"" in workflow
    assert "gzip -dc \"$IMAGE_ARCHIVE\" | docker load" in workflow
    assert "org.opencontainers.image.revision" in workflow
    assert workflow.count(
        "--format '{{ index .Config.Labels \"org.opencontainers.image.revision\" }}'"
    ) == 6
    assert '\\\"org.opencontainers.image.revision\\\"' not in workflow


def test_production_host_never_builds_and_has_image_rollback() -> None:
    workflow = PIPELINE.read_text(encoding="utf-8")
    remote = workflow.split("<<'REMOTE'", 1)[1].split("REMOTE", 1)[0]

    assert re.search(r"^\s*docker build(?:\s|$)", remote, re.MULTILINE) is None
    assert "buildx" not in remote
    assert "--build" not in remote
    assert remote.count("up -d --no-build") == 2
    assert "c3po/backend:rollback" in remote
    assert "c3po/web:rollback" in remote
    assert "c3po/database:rollback" in remote
    assert "health gate failed; restoring the prior container images" in remote
    assert 'C3PO_BUILD_SHA="$PREVIOUS_REVISION"' in remote
    assert "rollback health gate restored the prior images" in remote
    assert "docker builder prune --force" in remote


def test_v1_does_not_add_a_registry_or_registry_credentials() -> None:
    workflow = PIPELINE.read_text(encoding="utf-8").lower()

    assert "ghcr.io" not in workflow
    assert "docker login" not in workflow


def test_frontend_image_uses_the_ci_package_manager_and_excludes_build_state() -> None:
    dockerfile = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    dockerignore = set(
        FRONTEND_DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
    )

    assert "ARG PNPM_VERSION=10.15.0" in dockerfile
    assert "corepack prepare pnpm@$PNPM_VERSION --activate" in dockerfile
    assert "pnpm install --frozen-lockfile" in dockerfile
    assert "--frozen-lockfile=false" not in dockerfile
    assert {"node_modules", ".next", "out"} <= dockerignore


def test_every_base_image_is_digest_pinned_and_restore_uses_production_db() -> None:
    digest_ref = re.compile(r"^[^\s]+@sha256:[0-9a-f]{64}(?:\s|$)")
    backend_from = [
        line.removeprefix("FROM ")
        for line in BACKEND_DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if line.startswith("FROM ")
    ]
    frontend_from = [
        line.removeprefix("FROM ")
        for line in FRONTEND_DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if line.startswith("FROM ")
    ]
    database_from = [
        line.removeprefix("FROM ")
        for line in DATABASE_DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if line.startswith("FROM ")
    ]
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    database_ref = compose["services"]["db"]["image"]

    assert backend_from and frontend_from and database_from
    assert all(
        digest_ref.match(reference)
        for reference in backend_from + frontend_from + database_from
    )
    assert database_ref == "c3po/database:production"
    restore = RESTORE_DRILL.read_text(encoding="utf-8")
    assert "--file c3po/database/Dockerfile" in restore
    assert "C3PO_SECURITY_REBUILD=$rebuild_token" in restore
    assert "c3po/database:restore-drill" in restore


def test_fixable_high_and_critical_runtime_findings_have_explicit_upgrades() -> None:
    backend = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    frontend = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    database = DATABASE_DOCKERFILE.read_text(encoding="utf-8")
    requirements = BACKEND_REQUIREMENTS.read_text(encoding="utf-8")

    assert "apt-get install --yes --no-install-recommends --only-upgrade" in backend
    assert backend.count("C3PO_SECURITY_REBUILD") == 3
    assert {"libssl3t64", "openssl", "openssl-provider-legacy"} <= set(
        backend.split()
    )
    assert "cryptography>=50,<51" in requirements
    assert "apk upgrade --no-cache libcrypto3 libssl3" in frontend
    assert frontend.count("C3PO_SECURITY_REBUILD") == 2
    assert "golang:1.25.13-alpine3.24@sha256:" in database
    assert "ARG GOSU_COMMIT=6456aaa0f3c854d199d0f037f068eb97515b7513" in database
    assert '"github.com/tianon/gosu@${GOSU_COMMIT}"' in database
    assert "CGO_ENABLED=0" in database
    assert "apk upgrade --no-cache libcrypto3 libssl3" in database
    assert database.count("C3PO_SECURITY_REBUILD") == 4
    assert "gosu nobody true" in database
