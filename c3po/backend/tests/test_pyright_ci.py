from __future__ import annotations

import json
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]


def test_pyright_checks_new_modules_and_pins_the_ci_version() -> None:
    config = json.loads((BACKEND_ROOT / "pyrightconfig.json").read_text(encoding="utf-8"))
    pipeline = (REPO_ROOT / ".github" / "workflows" / "c3po-pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert config["include"] == ["app"]
    assert len(config["exclude"]) <= 42
    assert config["pythonVersion"] == "3.12"
    assert config["typeCheckingMode"] == "standard"
    assert "PYRIGHT_VERSION: \"1.1.411\"" in pipeline
    assert "pyright --pythonpath \"$(command -v python)\"" in pipeline


def test_production_deploy_requires_the_type_check() -> None:
    pipeline = (REPO_ROOT / ".github" / "workflows" / "c3po-pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert "needs: [sensitive-files, secret-scan, backend-tests, python-type-check, frontend-build]" in pipeline


def test_secret_scan_is_pinned_and_uses_the_house_allowlist() -> None:
    pipeline = (REPO_ROOT / ".github" / "workflows" / "c3po-pipeline.yml").read_text(
        encoding="utf-8"
    )
    allowlist = (REPO_ROOT / ".gitleaks.toml").read_text(encoding="utf-8")

    assert "GITLEAKS_VERSION: \"8.30.1\"" in pipeline
    assert "GITLEAKS_LINUX_X64_SHA256" in pipeline
    assert "sha256sum -c -" in pipeline
    assert "--config .gitleaks.toml" in pipeline
    assert "useDefault = true" in allowlist
