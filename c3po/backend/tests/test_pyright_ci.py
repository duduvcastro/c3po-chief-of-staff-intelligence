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
    import tomllib

    pipeline = (REPO_ROOT / ".github" / "workflows" / "c3po-pipeline.yml").read_text(
        encoding="utf-8"
    )
    allowlist = (REPO_ROOT / ".gitleaks.toml").read_text(encoding="utf-8")
    config = tomllib.loads(allowlist)
    identifier_allowlist = next(
        item
        for item in config["allowlists"]
        if item.get("description") == "Structured public identifier constants"
    )

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
    assert "paths" not in identifier_allowlist


def test_gitleaks_allowlist_never_excuses_adversarial_secret_shapes() -> None:
    import re
    import tomllib

    config = tomllib.loads((REPO_ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    allowlist_regexes = [
        re.compile(pattern) for pattern in config["allowlists"][0]["regexes"]
    ]
    generic = next(
        rule for rule in config["rules"] if rule["id"] == "generic-api-key"
    )
    generic_regex = re.compile(generic["regex"])

    legitimate = [
        "".join(["METHODOLOGY", '_KEY = "', "valuation", "_v2_shadow", '"']),
        "".join(["RATE_ENTITY", '_KEY = "', "US_TBILL_13", "_WEEK_COUPON_EQUIVALENT", '"']),
        "".join(["METHODOLOGY", "_KEY = ", "C3PO_VALUATION", "_POLICY.key"]),
    ]
    for line in legitimate:
        assert any(regex.search(line) for regex in allowlist_regexes), line

    # Assembled from fragments living on separate physical lines, so neither
    # the tracked test file nor any single line of it carries a secret-shaped
    # literal (the scan gates this very repository; audited with Codex).
    github_shaped = "".join([
        "LEAKED",
        "_API_KEY=",
        "ghp",
        "_AbCdEfGh",
        "12345678",
        "IjKlMnOp",
        "90QrStUv",
    ])
    hex_shaped = "".join([
        "PAYMENT",
        '_API_KEY="',
        "a1b2c3d4",
        "e5f6a7b8",
        "c9d0e1f2",
        "a3b4c5d6",
        '"',
    ])
    prefixed_shaped = "".join([
        "PAYMENT",
        '_API_KEY="',
        "sk",
        "_live_",
        "a1b2c3d4",
        "e5f6a7b8",
        '"',
    ])
    adversarial = [github_shaped, hex_shaped, prefixed_shaped]
    for line in adversarial:
        assert not any(regex.search(line) for regex in allowlist_regexes), line

    crossline = "BRAPI_TOKEN=" + "\n" + "C3PO_BRAPI_PLAN=pro"
    assert generic_regex.search(crossline) is None
    assert generic_regex.search(hex_shaped) is not None


def test_gitleaks_remediation_digest_exception_is_field_and_path_scoped() -> None:
    import re
    import tomllib

    config = tomllib.loads((REPO_ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    allowlist = next(
        item
        for item in config["allowlists"]
        if item.get("description")
        == "Deterministic remediation digest in the generated controller trigger"
    )

    assert allowlist["condition"] == "AND"
    assert allowlist["targetRules"] == ["generic-api-key"]
    assert allowlist["regexTarget"] == "line"
    assert allowlist["paths"] == [
        r"(^|/)c3po/security/container-rebuild-trigger\.json$"
    ]
    assert allowlist["regexes"] == [
        r'^\s*"remediation_key"\s*:\s*"[0-9a-f]{64}"\s*,?\s*$'
    ]

    path_regex = re.compile(allowlist["paths"][0])
    line_regex = re.compile(allowlist["regexes"][0])
    digest = "a" * 64
    assert path_regex.fullmatch("c3po/security/container-rebuild-trigger.json")
    assert not path_regex.fullmatch("tmp/adversarial/container-rebuild-trigger.json")
    assert line_regex.fullmatch(f'  "remediation_key": "{digest}",')
    assert not line_regex.fullmatch(f'  "api_key": "{digest}",')
    assert not line_regex.fullmatch(f'  "remediation_key": "{digest}x",')
