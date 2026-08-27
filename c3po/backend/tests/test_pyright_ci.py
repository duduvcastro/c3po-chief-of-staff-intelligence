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

    assert "needs: [sensitive-files, backend-tests, python-type-check, frontend-build]" in pipeline
