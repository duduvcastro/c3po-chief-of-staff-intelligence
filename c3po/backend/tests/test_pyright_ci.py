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


def test_secret_scan_is_pinned_and_proves_adversarial_detection() -> None:
    pipeline = (REPO_ROOT / ".github" / "workflows" / "c3po-pipeline.yml").read_text(
        encoding="utf-8"
    )
    allowlist = (REPO_ROOT / ".gitleaks.toml").read_text(encoding="utf-8")

    assert "GITLEAKS_VERSION: \"8.30.1\"" in pipeline
    assert (
        "GITLEAKS_LINUX_X64_SHA256: "
        "\"551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb\""
        in pipeline
    )
    assert "sha256sum -c -" in pipeline
    assert "--config .gitleaks.toml" in pipeline
    assert "adversarial fixtures were NOT detected" in pipeline
    assert "useDefault = true" in allowlist
    assert "paths" not in allowlist.split("[allowlist]")[1].split("[[rules]]")[0]


def test_gitleaks_allowlist_never_excuses_adversarial_secret_shapes() -> None:
    import re
    import tomllib

    config = tomllib.loads((REPO_ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    allowlist_regexes = [
        re.compile(pattern) for pattern in config["allowlist"]["regexes"]
    ]
    generic = next(
        rule for rule in config["rules"] if rule["id"] == "generic-api-key"
    )
    generic_regex = re.compile(generic["regex"])

    legitimate = [
        'METHODOLOGY_KEY = "valuation_v2_shadow"',
        'RATE_ENTITY_KEY = "US_TBILL_13_WEEK_COUPON_EQUIVALENT"',
        "METHODOLOGY_KEY = C3PO_VALUATION_POLICY.key",
    ]
    for line in legitimate:
        assert any(regex.search(line) for regex in allowlist_regexes), line

    adversarial = [
        'LEAKED_API_KEY=ghp_AbCdEfGh12345678IjKlMnOp90QrStUv',
        'PAYMENT_API_KEY="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"',
        'PAYMENT_API_KEY="sk_live_a1b2c3d4e5f6a7b8"',
    ]
    for line in adversarial:
        assert not any(regex.search(line) for regex in allowlist_regexes), line

    crossline = 'BRAPI_TOKEN=\nC3PO_BRAPI_PLAN=pro'
    assert generic_regex.search(crossline) is None
    assert generic_regex.search(adversarial[1]) is not None
