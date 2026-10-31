"""Adversarial binding tests use synthetic trust anchors, never real signatures/data."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from app.valuation_ensemble_inputs import canonical_hash
from app.valuation_ensemble_pin import (
    InstrumentBinding, MANIFEST_SCHEMA, PIN_SCHEMA, PREREG_COMMIT, PREREG_SHA256,
    PROTOCOL_CONSTANTS, REV3_MANIFEST_SHA256, instrument_file_hashes, validate_instrument_pin, validate_manifest_binding,
)


FILES = {f"c3po/backend/app/{name}": "a" * 64 for name in (
    "valuation_ensemble_grid.py", "valuation_ensemble_grid_consensus.py", "valuation_ensemble_report.py",
    "valuation_ensemble_executor.py", "valuation_ensemble_pin.py", "valuation_ensemble_models.py",
    "valuation_ensemble_inputs.py", "valuation_ensemble_aggregation.py", "valuation_pit_rerun.py", "valuation_accuracy_report.py",
    "valuation_ensemble_frozen.py", "valuation_ensemble_readiness.py",  # rev 2's required modules
)}
FILES[".github/workflows/valuation-ensemble-grid.yml"] = "b" * 64
FILES[".github/workflows/valuation-ensemble-readiness.yml"] = "b" * 64  # Codex 6549349754: the readiness workflow is pinned
for _dependency in ("valuation_pit_backtest_report.py", "valuation_pit_panel.py", "valuation_panel.py",
                    "valuation_price_history.py", "statement_vintages.py", "sec_xbrl.py", "cvm_fundamentals.py",
                    "valuation_asfiled.py", "valuation_v2_engine.py", "valuation_pit_served.py", "valuation_official.py", "valuation_v3_macro.py"):
    FILES[f"c3po/backend/app/{_dependency}"] = "a" * 64
COMMIT = "c" * 40


def packet():
    pin = {"schema": PIN_SCHEMA, "prereg_commit": PREREG_COMMIT, "prereg_sha256": PREREG_SHA256,
           "instrument_commit": COMMIT, "owner_signature_comment_id": 111, "technical_GO_comment_id": 222,
           "published_at": "2026-10-27T14:00:00Z", "constants": deepcopy(PROTOCOL_CONSTANTS), "files": dict(FILES)}
    return pin, InstrumentBinding(canonical_hash(pin), PREREG_COMMIT, COMMIT, 111, 222)


def manifest(pin, binding):
    return {"schema": MANIFEST_SCHEMA, "complete": True, "prereg_sha256": PREREG_SHA256,
            "rev3_manifest_sha256": REV3_MANIFEST_SHA256,
            "instrument_pin_sha256": binding.expected_pin_sha256,
            "entries": [{"market": "NASDAQ", "session_date": "2021-06-01", "as_of": "2021-06-02T03:59:59Z",
                         "started_at": "2026-10-27T14:00:01Z", "instrument_commit": COMMIT,
                         "instrument_pin_sha256": binding.expected_pin_sha256,
                         "implementation_files": dict(pin["files"])}]}


def anchored(pin, original_binding=None):
    """Synthetic external digest fixture; this function does not authenticate a human."""
    binding = original_binding or packet()[1]
    return replace(binding, expected_pin_sha256=canonical_hash(pin))


def test_exact_pin_and_per_run_files_against_external_anchor_pass_synthetic_binding():
    pin, binding = packet()
    assert validate_instrument_pin(pin, file_hashes=FILES, binding=binding) == []
    assert validate_manifest_binding(manifest(pin, binding), pin, binding) == []


def test_json_cannot_self_authenticate_or_repin_by_changing_its_own_digest_field():
    pin, binding = packet()
    pin["owner_signed"] = True
    pin["GO"] = True
    pin["expected_pin_sha256"] = canonical_hash(pin)
    assert "ensemble_instrument_pin_identity_mismatch" in validate_instrument_pin(pin, file_hashes=FILES, binding=binding)
    altered = deepcopy(pin)
    altered["files"]["c3po/backend/app/valuation_ensemble_models.py"] = "d" * 64
    assert "ensemble_instrument_pin_identity_mismatch" in validate_instrument_pin(altered, file_hashes=FILES, binding=binding)


def test_missing_pin_is_not_an_operational_permission_or_valid_report():
    _, binding = packet()
    assert validate_instrument_pin(None, file_hashes=FILES, binding=binding) == ["ensemble_instrument_not_pinned"]


@pytest.mark.parametrize("key,bad", [("prereg_commit", "d" * 40), ("prereg_sha256", "e" * 64),
                                     ("instrument_commit", "f" * 40), ("schema", "different")])
def test_freshly_hashed_wrong_protocol_or_commit_still_refuses(key, bad):
    pin, binding = packet()
    pin[key] = bad
    assert validate_instrument_pin(pin, file_hashes=FILES, binding=anchored(pin, binding))


def test_freshly_hashed_constants_cannot_change_the_signed_model_or_statistics():
    pin, binding = packet()
    pin["constants"]["minimum_values"] = 2
    assert "ensemble_instrument_constants_mismatch" in validate_instrument_pin(pin, file_hashes=FILES, binding=anchored(pin, binding))


@pytest.mark.parametrize("key", ["owner_signature_comment_id", "technical_GO_comment_id"])
def test_bool_comment_identity_does_not_equal_integer_one(key):
    pin, binding = packet()
    pin[key] = True
    binding = replace(binding, **{key: 1})
    errors = validate_instrument_pin(pin, file_hashes=FILES, binding=anchored(pin, binding))
    assert "ensemble_instrument_" + key + "_mismatch" in errors


@pytest.mark.parametrize("key", ["owner_signature_comment_id", "technical_GO_comment_id"])
@pytest.mark.parametrize("bad", [True, 0, -1, "1"])
def test_malformed_external_comment_identity_cannot_authenticate_a_pin(key, bad):
    pin, binding = packet()
    binding = replace(binding, **{key: bad})
    assert "ensemble_instrument_" + key + "_mismatch" in validate_instrument_pin(pin, file_hashes=FILES, binding=binding)


def test_source_byte_tamper_new_extra_module_and_omitted_file_all_refuse():
    pin, binding = packet()
    changed = {**FILES, "c3po/backend/app/valuation_ensemble_models.py": "d" * 64}
    assert "ensemble_instrument_mismatch:c3po/backend/app/valuation_ensemble_models.py" in validate_instrument_pin(pin, file_hashes=changed, binding=binding)
    extra = {**FILES, "c3po/backend/app/valuation_ensemble_extra.py": "d" * 64}
    assert "ensemble_instrument_file_inventory_mismatch" in validate_instrument_pin(pin, file_hashes=extra, binding=binding)
    del pin["files"]["c3po/backend/app/valuation_ensemble_models.py"]
    assert "ensemble_instrument_file_inventory_mismatch" in validate_instrument_pin(pin, file_hashes=FILES, binding=anchored(pin, binding))


def test_transitive_statistical_dependency_is_required_even_if_both_supplied_maps_omit_it():
    pin, binding = packet()
    del pin["files"]["c3po/backend/app/valuation_accuracy_report.py"]
    assert "ensemble_instrument_required_file_missing" in validate_instrument_pin(pin, file_hashes=pin["files"], binding=anchored(pin, binding))


def test_matching_malformed_file_keys_fail_closed_without_typeerror():
    pin, binding = packet()
    pin["files"][7] = "a" * 64
    hashes = {**FILES, 7: "a" * 64}
    assert validate_instrument_pin(pin, file_hashes=hashes, binding=binding)
    pin, binding = packet()
    assert validate_instrument_pin(pin, file_hashes=hashes, binding=binding)


def test_required_file_paths_cannot_be_replaced_by_basename_lookalikes_outside_instrument():
    pin, binding = packet()
    pin["files"] = {"../../escape/" + Path(name).name: value for name, value in FILES.items()}
    assert validate_instrument_pin(pin, file_hashes=pin["files"], binding=anchored(pin, binding))


@pytest.mark.parametrize("bad", [[], False, "owner signed", 7])
def test_malformed_pin_document_fails_closed_instead_of_raising(bad):
    _, binding = packet()
    assert validate_instrument_pin(bad, file_hashes=FILES, binding=binding)


@pytest.mark.parametrize("timestamp", [None, "2026-10-27T14:00:00", "invalid", True, 123])
def test_pin_publication_requires_real_zoned_timestamp(timestamp):
    pin, binding = packet()
    pin["published_at"] = timestamp
    assert "ensemble_instrument_pin_publication_time_invalid" in validate_instrument_pin(pin, file_hashes=FILES, binding=anchored(pin, binding))


def test_run_before_pin_or_with_different_instrument_refuses_the_manifest():
    pin, binding = packet()
    m = manifest(pin, binding)
    m["entries"][0]["started_at"] = "2026-10-27T13:59:59Z"
    assert "ensemble_run_precedes_published_instrument_pin" in validate_manifest_binding(m, pin, binding)
    m = manifest(pin, binding)
    m["entries"][0]["implementation_files"]["c3po/backend/app/valuation_ensemble_models.py"] = "f" * 64
    assert "ensemble_run_instrument_files_mismatch" in validate_manifest_binding(m, pin, binding)


@pytest.mark.parametrize("entries", [None, [], "not a list", [None]])
def test_manifest_malformed_entries_refuse_without_labels(entries):
    pin, binding = packet()
    m = manifest(pin, binding)
    m["entries"] = entries
    assert validate_manifest_binding(m, pin, binding)


def test_manifest_duplicate_sessions_and_unhashable_identity_refuse_without_typeerror():
    pin, binding = packet()
    m = manifest(pin, binding)
    m["entries"].append(deepcopy(m["entries"][0]))
    assert "ensemble_manifest_duplicate_or_invalid_session" in validate_manifest_binding(m, pin, binding)
    m = manifest(pin, binding)
    m["entries"][0]["market"] = ["NASDAQ"]
    assert "ensemble_manifest_duplicate_or_invalid_session" in validate_manifest_binding(m, pin, binding)


@pytest.mark.parametrize("bad", [[], False, "not a manifest", 1])
def test_manifest_invalid_top_level_type_refuses(bad):
    pin, binding = packet()
    assert validate_manifest_binding(bad, pin, binding)


def test_inventory_reads_all_ensemble_sources_and_requires_the_workflow(tmp_path):
    app = tmp_path / "c3po/backend/app"
    app.mkdir(parents=True)
    workflow = tmp_path / ".github/workflows/valuation-ensemble-grid.yml"
    workflow.parent.mkdir(parents=True)
    for name in FILES:
        p = tmp_path / name
        p.write_text("synthetic source bytes")
    (app / "valuation_ensemble_extra.py").write_text("additional source bytes")
    got = instrument_file_hashes(tmp_path)
    assert "c3po/backend/app/valuation_ensemble_extra.py" in got
    assert set(got) == set(FILES) | {"c3po/backend/app/valuation_ensemble_extra.py"}
    workflow.unlink()
    with pytest.raises((OSError, ValueError)):
        instrument_file_hashes(tmp_path)


def test_report_missing_or_tampered_pin_never_calls_label_reader():
    from app.valuation_ensemble_report import build_report
    pin, binding = packet()
    calls = []
    def labels(row, h):
        calls.append((row, h))
        raise AssertionError("labels must remain behind the binding gate")
    for candidate in (None, {**pin, "prereg_sha256": "f" * 64}):
        report = build_report({}, [], rev3_manifest={}, pin=candidate, binding=binding, file_hashes=FILES,
                              label_reader=labels, index_of={}, mature_through={})
        assert report["payload"]["labels_read"] == 0
        assert report["payload"]["verdict"]["status"] == "VOID"
    assert calls == []
