from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / ".github" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import c3po_m1_formal_orchestration as orchestration
import c3po_m1_incremental_reducer as frozen
from test_m1_formal_checkpoint_contract import _baseline, _build, _sessions, _snapshot


def _write_canonical(path: Path, value: object) -> None:
    path.write_text(orchestration.canonical_json(value) + "\n", encoding="utf-8")


def _pending() -> dict[str, object]:
    return {
        "schema": orchestration.STATE_SCHEMA,
        "status": "PENDING_15",
        "checkpoint": 15,
        "artifact_sha256": None,
        "checkpoint_binding_sha256": None,
        "expires_at": None,
    }


def _continuing(payload: dict[str, object]) -> dict[str, object]:
    return {
        "schema": orchestration.STATE_SCHEMA,
        "status": "CONTINUE_TO_20",
        "checkpoint": 15,
        "artifact_sha256": payload["artifact_sha256"],
        "checkpoint_binding_sha256": payload["checkpoint_binding_sha256"],
        "expires_at": "2026-10-17T22:00:00Z",
    }


def test_preseeded_pending_state_is_the_only_path_to_checkpoint_15(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state.json"
    _write_canonical(state_path, _pending())
    result = orchestration.validate_private_state(
        state_path,
        now=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )
    assert result == {"action": "BUILD_15", "checkpoint": 15}

    state = _pending()
    state["artifact_sha256"] = "a" * 64
    _write_canonical(state_path, state)
    with pytest.raises(orchestration.OrchestrationError, match="not empty and exact"):
        orchestration.validate_private_state(state_path)

    with pytest.raises(orchestration.OrchestrationError, match="missing"):
        orchestration.validate_private_state(tmp_path / "absent.json")


def test_continue_state_rebinds_a_fresh_recomputation_to_the_canonical_15(
    tmp_path: Path,
) -> None:
    payload = _build(["upper_first"] * 15, 15, orchestrated=True)
    assert payload is not None
    state_path = tmp_path / "state.json"
    _write_canonical(state_path, _continuing(payload))
    state = orchestration.validate_private_state(
        state_path,
        now=datetime(2026, 9, 23, tzinfo=timezone.utc),
    )
    assert state["action"] == "BUILD_20"
    assert state["prior_15_artifact_sha256"] == payload["artifact_sha256"]

    recomputed = copy.deepcopy(payload)
    recomputed["generated_at"] = "2026-09-23T23:37:00+00:00"
    recomputed.pop("artifact_sha256")
    recomputed["artifact_sha256"] = frozen.canonical_sha256(recomputed)
    payload_path = tmp_path / "recomputed.json"
    _write_canonical(payload_path, recomputed)
    result = orchestration.validate_recomputed_prior(
        payload_path,
        state_path,
        authorized_formal_source_sha256=payload["frozen_contract"][
            "formal_checkpoint_sha256"
        ],
        now=datetime(2026, 9, 23, tzinfo=timezone.utc),
    )
    assert result["canonical_prior_15_artifact_sha256"] == payload[
        "artifact_sha256"
    ]
    assert result["recomputed_prior_15_artifact_sha256"] == recomputed[
        "artifact_sha256"
    ]


def test_binding_drift_and_expired_tombstones_fail_closed(tmp_path: Path) -> None:
    payload = _build(["upper_first"] * 15, 15, orchestrated=True)
    assert payload is not None
    state = _continuing(payload)
    state["checkpoint_binding_sha256"] = "f" * 64
    state_path = tmp_path / "state.json"
    payload_path = tmp_path / "checkpoint.json"
    _write_canonical(state_path, state)
    _write_canonical(payload_path, payload)
    with pytest.raises(orchestration.OrchestrationError, match="differs"):
        orchestration.validate_recomputed_prior(
            payload_path,
            state_path,
            authorized_formal_source_sha256=payload["frozen_contract"][
                "formal_checkpoint_sha256"
            ],
            now=datetime(2026, 9, 23, tzinfo=timezone.utc),
        )

    expired = {
        **_continuing(payload),
        "status": "EXPIRED",
        "expires_at": "2026-09-22T00:00:00Z",
    }
    _write_canonical(state_path, expired)
    with pytest.raises(orchestration.OrchestrationError, match="expired"):
        orchestration.validate_private_state(
            state_path,
            now=datetime(2026, 9, 23, tzinfo=timezone.utc),
        )


def test_terminal_state_suppresses_reemission(tmp_path: Path) -> None:
    payload = _build(["lower_first"] * 15, 15, orchestrated=True)
    assert payload is not None
    state = {
        "schema": orchestration.STATE_SCHEMA,
        "status": "TERMINAL_15",
        "checkpoint": 15,
        "artifact_sha256": payload["artifact_sha256"],
        "checkpoint_binding_sha256": payload["checkpoint_binding_sha256"],
        "expires_at": "2026-10-17T22:00:00Z",
    }
    path = tmp_path / "state.json"
    _write_canonical(path, state)
    result = orchestration.validate_private_state(
        path,
        now=datetime(2026, 9, 23, tzinfo=timezone.utc),
    )
    assert result["action"] == "NO_WORK"
    assert result["status"] == "TERMINAL_15"


def test_snapshot_reader_stops_on_exact_measured_prefix(
    tmp_path: Path,
) -> None:
    sessions = _sessions(17)
    categories = [None] + ["upper_first"] * 16
    enumeration = tmp_path / "sessions.txt"
    enumeration.write_text("\n".join(sessions) + "\n", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(_baseline()), encoding="utf-8")
    snapshots: list[Path] = []
    for session, category in zip(sessions, categories):
        path = tmp_path / f"session-{session}.json"
        path.write_text(json.dumps(_snapshot(session, category)), encoding="utf-8")
        snapshots.append(path)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(frozen, "verify_baseline", lambda _report: None)
        not_ready = orchestration.checkpoint_progress(
            baseline,
            enumeration,
            snapshots[:15],
            checkpoint=15,
        )
        ready = orchestration.checkpoint_progress(
            baseline,
            enumeration,
            snapshots[:16],
            checkpoint=15,
        )
        with pytest.raises(
            orchestration.OrchestrationError,
            match="extend beyond the exact checkpoint",
        ):
            orchestration.checkpoint_progress(
                baseline,
                enumeration,
                snapshots,
                checkpoint=15,
            )

    assert not_ready == {
        "status": "NOT_READY",
        "checkpoint": 15,
        "measured_session_count": 14,
        "source_session_count": 15,
    }
    assert ready == {
        "status": "READY",
        "checkpoint": 15,
        "measured_session_count": 15,
        "source_session_count": 16,
    }


def test_signed_envelope_binds_release_run_attempt_and_public_artifact(
    tmp_path: Path,
) -> None:
    payload = _build(["upper_first"] * 15, 15, orchestrated=True)
    assert payload is not None
    payload_path = tmp_path / "checkpoint.json"
    output = tmp_path / "envelope.json"
    _write_canonical(payload_path, payload)
    formal_source = SCRIPTS / "c3po_m1_formal_checkpoint.py"
    formal_sha = hashlib.sha256(formal_source.read_bytes()).hexdigest()
    assert payload["frozen_contract"]["formal_checkpoint_sha256"] == formal_sha
    result = orchestration.build_ingress_envelope(
        payload_path,
        checkpoint=15,
        source_head_sha="a" * 40,
        authorized_formal_source_sha256=formal_sha,
        formal_source_path=formal_source,
        source_release_id=101,
        source_run_id=202,
        source_run_attempt=3,
        public_artifact_id=404,
        output=output,
    )
    assert set(result) == orchestration.INGRESS_KEYS
    assert result["source_release_id"] == 101
    assert result["source_run_id"] == 202
    assert result["source_run_attempt"] == 3
    assert result["public_artifact_id"] == 404
    assert result["checkpoint_binding_sha256"] == payload[
        "checkpoint_binding_sha256"
    ]
    assert output.read_bytes() == (
        orchestration.canonical_json(result) + "\n"
    ).encode()


def test_public_workflow_pins_remote_clock_read_only_path_and_ephemeral_channel() -> None:
    workflow = (ROOT / ".github/workflows/m1-formal-checkpoint.yml").read_text()
    assert 'cron: "37 23 * * *"' in workflow
    assert "environment: production" in workflow
    assert "RUN M1 FORMAL CHECKPOINT READ" in workflow
    assert "C3PO_M1_FORMAL_AUTOMATION_ENABLED" in workflow
    assert "C3PO_M1_AUTHORIZED_PUBLIC_HEAD_SHA" in workflow
    assert "C3PO_M1_AUTHORIZED_FORMAL_SOURCE_SHA256" in workflow
    assert "WORKFLOW_SHA: ${{ github.workflow_sha }}" in workflow
    assert 'test "$WORKFLOW_SHA" = "$AUTHORIZED_HEAD"' in workflow
    assert "actions/create-github-app-token@v2" in workflow
    assert "steps.transfer-app.outputs.app-slug" in workflow
    assert "gh api user --jq .login" not in workflow
    assert "C3PO_M1_TRANSFER_APP_PRIVATE_KEY" in workflow
    assert "C3PO_M1_FORMAL_SIGNING_KEY" in workflow
    assert "C3PO_HEALTHCHECK_M1_FORMAL_URL" in workflow
    assert workflow.index("echo 'enabled=true' >> \"$GITHUB_OUTPUT\"") < workflow.index(
        "for required in AWS_HOST"
    )
    assert "PERSONAL_ACCESS_TOKEN" not in workflow
    assert "m1-formal-state" in workflow
    assert "PENDING_15" not in workflow  # state semantics live in the validator
    assert "docker compose --env-file .env -f c3po/compose.yml exec -T" in workflow
    assert "docker compose --env-file .env -f c3po/compose.yml run" not in workflow
    assert "role=pg_read_all_data" in workflow
    assert "default_transaction_read_only=on" in workflow
    assert "--orchestrated" in workflow
    assert "retention-days: 1" in workflow
    assert "--draft" in workflow
    assert 'asset="m1-formal-checkpoint-$CHECKPOINT-$ARTIFACT_SHA256.zip"' in workflow
    assert (
        'tag="m1-formal-transfer-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT-'
        '$PUBLIC_ARTIFACT_ID"'
    ) in workflow
    assert (
        "name: m1-formal-checkpoint-${{ steps.build.outputs.checkpoint }}-"
        "${{ steps.build.outputs.artifact_sha256 }}-source-${{ github.run_id }}-"
        "attempt-${{ github.run_attempt }}"
    ) in workflow
    assert "m1-formal-private-store.yml" in workflow
    assert (
        'inputs:{confirmation:"STORE FORMAL M1 CHECKPOINT V1",'
        'release_id:$release_id,source_run_id:$source_run_id,'
        'source_run_attempt:$source_run_attempt,'
        'public_artifact_id:$public_artifact_id}'
    ) in workflow
    assert "public_run_id" not in workflow
    assert "public_run_attempt" not in workflow
    assert "public_artifact_id" in workflow
    assert "Expunge the public handoff artifact on every outcome" in workflow
    assert (
        "if: always() && steps.public-artifact.outputs.artifact-id != ''"
    ) in workflow
    assert (
        "EXPECTED_TAG: m1-formal-transfer-${{ github.run_id }}-"
        "${{ github.run_attempt }}-${{ steps.public-artifact.outputs.artifact-id }}"
    ) in workflow
    assert workflow.index("printf 'tag=%s\\napp_actor=%s\\n'") < workflow.index(
        'gh release create "$tag"'
    )
    assert "actions/artifacts/$ARTIFACT_ID" in workflow
    assert "m1-formal-ingress" not in workflow
    assert "git push" not in workflow
    assert "checkpoint-progress" in workflow
    assert 'if test "$progress_status" = READY; then' in workflow
    assert 'test "${#snapshots[@]}" = "$(wc -l < "$root/snapshot-prefix.txt"' in workflow
    assert 'test "${#snapshots[@]}" = "$(wc -l < "$root/sessions.txt"' not in workflow
    assert "private_main_sha" in workflow
    assert workflow.count('test "$current_main" = "$PRIVATE_MAIN_SHA"') == 2
    assert 'test "$(jq -r .head_sha <<< "$run")" = "$PRIVATE_MAIN_SHA"' in workflow
    assert workflow.count("test \"$(jq '.parents | length' <<< \"$commit\")\" -le 1") == 2
    assert 'test "$(jq -r \'.tree[0].path\' <<< "$tree")" = state.json' in workflow
    assert workflow.index("Signal the remote dead-man start") < workflow.index(
        "Enumerate finalized policy sessions"
    )
    assert workflow.index("Destroy all transient source") < workflow.index(
        "Complete the remote dead-man signal"
    )
    assert 'target="$target/fail"' in workflow
    assert "JOB_STATUS: ${{ job.status }}" in workflow
    assert workflow.index("Preflight the private controls") < workflow.index(
        "Publish the one-day public handoff artifact"
    )
    assert "if: steps.build.outputs.ready == 'true'" in workflow
