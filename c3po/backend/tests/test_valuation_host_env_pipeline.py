"""The deploy stages the optional valuation settings into the host .env (VALUATION_ASFILED_US_V1.md, Operação; the B3 CVM
overlay keys of VALUATION_CVM_STATEMENTS_V1.md, Rollout): the SEC contact from a secret, the as-filed switch and backfill
budget and the two CVM field-wise overlay switches (shadow, serving) from repository variables. Every value is validated as
a whole string before it is written, so no value can add a line to .env, and an empty value writes nothing."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "c3po-pipeline.yml"
STEP = "Stage host env settings (push notifications, valuation as-filed)"


def _step() -> dict[str, object]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = [step for job in workflow["jobs"].values() for step in job.get("steps", []) if step.get("name") == STEP]
    assert len(steps) == 1
    return steps[0]


def test_the_step_reads_the_contact_from_a_secret_and_the_switches_from_variables() -> None:
    env = _step()["env"]
    assert isinstance(env, dict)
    assert env["SEC_CONTACT"] == "${{ secrets.C3PO_SEC_CONTACT }}"
    assert env["ASFILED_ENABLED"] == "${{ vars.C3PO_VALUATION_ASFILED_ENABLED }}"
    assert env["ASFILED_BACKFILL"] == "${{ vars.C3PO_VALUATION_ASFILED_BACKFILL_ISSUERS_PER_POLL }}"
    assert env["CVM_OVERLAY_SHADOW"] == "${{ vars.C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_SHADOW }}"
    assert env["CVM_OVERLAY_ENABLED"] == "${{ vars.C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_ENABLED }}"
    assert env["DECISOR_SHADOW"] == "${{ vars.C3PO_VALUATION_DECISOR_SHADOW }}"
    assert env["EARNINGS_CALENDAR_ENABLED"] == "${{ vars.C3PO_VALUATION_EARNINGS_CALENDAR_ENABLED }}"
    assert env["LAB_TOKEN"] == "${{ secrets.C3PO_R2D2_LAB_TOKEN }}"


def test_the_step_cannot_be_skipped_and_runs_right_before_the_host_merge() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["deploy-production"]
    names = [step.get("name") for step in job["steps"]]
    at = names.index(STEP)
    assert names[at + 1] == "Deploy and verify"
    for step in job["steps"][at : at + 2]:  # a failed validation must stop the job before the host merge
        assert not {"if", "continue-on-error", "shell"} & set(step)
    assert "defaults" not in workflow and "defaults" not in job  # GitHub's default: bash -e on ubuntu


def _run(tmp_path: Path, **values: str) -> tuple[int, str, str]:
    run = _step()["run"]
    assert isinstance(run, str)
    out = tmp_path / "staged.env"
    script = tmp_path / "step.sh"
    script.write_text("set -e\n" + run.replace("/tmp/c3po-push.env", '"$OUT"').split("scp -i")[0], encoding="utf-8")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PUSH_PRIVATE": "p", "PUSH_PUBLIC": "q", "OUT": str(out), **values}
    done = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, check=False)
    return done.returncode, out.read_text(encoding="utf-8") if out.exists() else "", done.stderr


bash_missing = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required to execute the workflow step")


@bash_missing
def test_valid_values_are_staged_and_empty_values_write_nothing(tmp_path: Path) -> None:
    code, staged, _ = _run(tmp_path, SEC_CONTACT="ops.contact@example.com", ASFILED_ENABLED="true", ASFILED_BACKFILL="30", DECISOR_SHADOW="true",
                           EARNINGS_CALENDAR_ENABLED="false")
    assert code == 0
    assert staged.splitlines() == [
        "C3PO_PUSH_VAPID_PRIVATE_KEY=p",
        "C3PO_PUSH_VAPID_PUBLIC_KEY=q",
        "C3PO_SEC_CONTACT=ops.contact@example.com",
        "C3PO_VALUATION_ASFILED_ENABLED=true",
        "C3PO_VALUATION_ASFILED_BACKFILL_ISSUERS_PER_POLL=30",
        "C3PO_VALUATION_DECISOR_SHADOW=true",
        "C3PO_VALUATION_EARNINGS_CALENDAR_ENABLED=false",
    ]
    for token in ("f" * 64, "Ab+/9_-." * 6 + "=="):  # hex, base64 or URL-safe: whatever the secret was minted as
        code, staged, _ = _run(tmp_path, LAB_TOKEN=token)
        assert code == 0 and staged.splitlines()[-1] == "C3PO_R2D2_LAB_TOKEN=" + token
    code, staged, _ = _run(tmp_path, EARNINGS_CALENDAR_ENABLED="true")
    assert code == 0 and staged.splitlines()[-1] == "C3PO_VALUATION_EARNINGS_CALENDAR_ENABLED=true"
    code, staged, _ = _run(tmp_path)
    assert code == 0 and staged.splitlines() == ["C3PO_PUSH_VAPID_PRIVATE_KEY=p", "C3PO_PUSH_VAPID_PUBLIC_KEY=q"]


@bash_missing
@pytest.mark.parametrize(("shadow", "enabled"), [("true", ""), ("true", "true"), ("false", "true"), ("", "false")])
def test_the_cvm_overlay_switches_are_staged_as_given(tmp_path: Path, shadow: str, enabled: str) -> None:
    """Each rollout step of the B3 CVM overlay is one pair of repository variables (shadow → receipt → owner → enable)."""
    code, staged, _ = _run(tmp_path, CVM_OVERLAY_SHADOW=shadow, CVM_OVERLAY_ENABLED=enabled)
    expected = ["C3PO_PUSH_VAPID_PRIVATE_KEY=p", "C3PO_PUSH_VAPID_PUBLIC_KEY=q"]
    if shadow:
        expected.append(f"C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_SHADOW={shadow}")
    if enabled:
        expected.append(f"C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_ENABLED={enabled}")
    assert code == 0 and staged.splitlines() == expected


def test_the_staged_names_are_the_names_the_code_reads() -> None:
    from app import official_statements, r2d2_lab_live, valuation_env

    run = str(_step()["run"])
    assert f"printf '{valuation_env.CVM_OVERLAY_SHADOW_ENV}=%s\\n'" in run
    assert f"printf '{official_statements.FIELDWISE_OVERLAY_ENV}=%s\\n'" in run
    assert f"printf '{r2d2_lab_live.TOKEN_ENV}=%s\\n'" in run


@bash_missing
@pytest.mark.parametrize(
    "values",
    [
        {"SEC_CONTACT": "ops@example.com\nC3PO_INJECTED=1"},
        {"SEC_CONTACT": "ops @example.com"},
        {"SEC_CONTACT": "not-an-address"},
        {"ASFILED_ENABLED": "yes"},
        {"ASFILED_ENABLED": "true\nC3PO_INJECTED=1"},
        {"ASFILED_BACKFILL": "201"},
        {"ASFILED_BACKFILL": "-1"},
        {"ASFILED_BACKFILL": "30\nC3PO_INJECTED=1"},
        {"SEC_CONTACT": "x\nC3PO_INJECTED=ops@example.com"},
        {"ASFILED_ENABLED": "x\nC3PO_INJECTED=true"},
        {"ASFILED_BACKFILL": "x\nC3PO_INJECTED=30"},
        {"CVM_OVERLAY_SHADOW": "yes"},
        {"CVM_OVERLAY_SHADOW": "TRUE"},
        {"CVM_OVERLAY_SHADOW": "1"},
        {"CVM_OVERLAY_SHADOW": "true\nC3PO_INJECTED=1"},
        {"CVM_OVERLAY_SHADOW": "x\nC3PO_INJECTED=true"},
        {"CVM_OVERLAY_SHADOW": "true "},
        {"CVM_OVERLAY_SHADOW": "true\r"},
        {"CVM_OVERLAY_ENABLED": "on"},
        {"CVM_OVERLAY_ENABLED": "True"},
        {"CVM_OVERLAY_ENABLED": "false\nC3PO_INJECTED=1"},
        {"CVM_OVERLAY_ENABLED": "x\nC3PO_INJECTED=false"},
        {"CVM_OVERLAY_ENABLED": "true\u2028C3PO_INJECTED=1"},
        {"CVM_OVERLAY_SHADOW": "true", "CVM_OVERLAY_ENABLED": "true;C3PO_INJECTED=1"},
        {"SEC_CONTACT": "ops@example.com\r"},
        {"SEC_CONTACT": "ops@example.com\u2028C3PO_INJECTED=1"},
        {"DECISOR_SHADOW": "on"},
        {"DECISOR_SHADOW": "True"},
        {"DECISOR_SHADOW": "true\nC3PO_INJECTED=1"},
        {"DECISOR_SHADOW": "x\nC3PO_INJECTED=true"},
        {"EARNINGS_CALENDAR_ENABLED": "1"},
        {"EARNINGS_CALENDAR_ENABLED": "false "},
        {"EARNINGS_CALENDAR_ENABLED": "false\nC3PO_INJECTED=1"},
        {"EARNINGS_CALENDAR_ENABLED": "x\nC3PO_INJECTED=false"},
        {"EARNINGS_CALENDAR_ENABLED": "true\r"},
        {"LAB_TOKEN": "short"},
        {"LAB_TOKEN": "f" * 64 + "\nC3PO_INJECTED=1"},
        {"LAB_TOKEN": "f" * 64 + " "},
        {"LAB_TOKEN": "f" * 32 + "$(id)" + "f" * 32},
        {"LAB_TOKEN": "f" * 129},
    ],
)
def test_an_invalid_value_fails_the_deploy_before_anything_is_staged(tmp_path: Path, values: dict[str, str]) -> None:
    code, staged, stderr = _run(tmp_path, **values)
    assert code != 0 and staged == "" and "C3PO_INJECTED" not in stderr and "@" not in stderr
