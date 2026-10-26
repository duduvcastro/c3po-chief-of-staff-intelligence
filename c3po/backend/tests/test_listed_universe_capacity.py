"""Synthetic evidence contracts: none of these fixtures attests real capacity."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from app.listed_universe import Catalogue, Listing, B3_LIST_URL, NASDAQ_LIST_URL, NYSE_LIST_URL, digest
from app.listed_universe_capacity import capacity_preflight, inspect_run, main
from app.listed_universe_producer import BudgetedHttp
from app.listed_universe_runtime import QuotaWindow, TransientInputFailure, produce_catalogue
from app.listed_universe_runtime import stage_predictions
from app.config import Settings
from app.database import Database
from test_listed_universe_runtime import Adapter, row

RATE = {"fundamentals": {"host": "provider.test", "path_prefix": "/", "provider": "TEST", "units": 20}}


class Client:
    def get(self, url, **kwargs):
        return httpx.Response(200, json={"synthetic": True}, request=httpx.Request("GET", url))


class Measured(Adapter):
    identity = {"source": "synthetic-capacity-contract-only"}
    def collect(self, listing, quota):
        BudgetedHttp(quota, client=Client()).get_json("https://provider.test/inputs")
        return {"received_at": datetime.now(timezone.utc).isoformat(),
                "quote": {"as_of": datetime.now(timezone.utc).isoformat()}, "fundamental": {}}


def catalogue(market="NASDAQ", n=3):
    at = datetime.now(timezone.utc) - timedelta(seconds=1)
    return Catalogue(market, {"B3": B3_LIST_URL, "NASDAQ": NASDAQ_LIST_URL, "NYSE": NYSE_LIST_URL}[market],
                     "b3-titulos-220-v1" if market == "B3" else "nasdaq-trader-pipe-v1", at.isoformat(),
                     at.date().isoformat() if market == "B3" else at.isoformat(),
                     "a" * 64, n, {}, tuple(Listing(market, f"S{i:04}", "Synthetic Company") for i in range(n)))


def build(tmp_path, market="NASDAQ", n=3, **kwargs):
    cat, path = catalogue(market, n), tmp_path / market
    produce_catalogue(cat, path, Measured(), window="synthetic-night", limits={"TEST": 200}, rate_card=RATE, act=True, **kwargs)
    state = json.loads((path / "checkpoint.json").read_text())
    if state["status"] == "complete":
        stage_predictions(Database(Settings(database_url="", auth_cookie_secure=False)), path, act=True)
    return cat, path, inspect_run(cat, path)


def test_import_reconciles_actual_names_artifacts_http_and_weighted_reservations(tmp_path):
    _, _, result = build(tmp_path)
    assert result["complete"] and result["processed_count"] == result["inventory_count"] == 3
    assert result["remaining"] == 0 and result["identity_verified"] and result["current_code_matches"]
    window = result["quota_windows"][0]
    assert window["reserved_billable_units"] == {"TEST": 60}  # not three billable units
    assert window["reservations"] == window["http"]["attempts_started"] == window["http"]["responses"] == 3
    assert window["http"]["response_bytes"] > 0 and window["http"]["uncertain_inflight"] == 0
    assert set(result["observations"]["phase_duration_seconds"]) == {"collect", "context", "value"}
    assert result["distinct_sec_ciks"] is None  # a stock count is not a CIK sweep measurement
    receipt = capacity_preflight({"NASDAQ": result})
    assert not receipt["capacity_evidence_ready_for_review"] and not receipt["publication"]["production_release_allowed"]


def test_pause_resume_counts_artifact_reuse_without_inventing_provider_cache_hits(tmp_path):
    cat, path, first = build(tmp_path, max_batches=1, batch_size=1)
    assert first["processed_count"] == 0 and first["remaining"] == 3
    produce_catalogue(cat, path, Measured(), window="synthetic-night", limits={"TEST": 200}, rate_card=RATE, act=True)
    result = inspect_run(cat, path)
    assert result["observations"]["cached_input_reads"] == 1
    assert result["observations"]["completed_invocations"] == 2
    assert result["quota_windows"][0]["http"]["attempts_started"] == 3


def test_old_checkpoint_telemetry_stays_unknown_instead_of_becoming_zero(tmp_path):
    cat, path, _ = build(tmp_path)
    state = json.loads((path / "checkpoint.json").read_text())
    state.pop("observations");state.pop("adapter_identity")
    (path / "checkpoint.json").write_text(json.dumps(state))
    ledger = next(path.glob("quota-*.json"));data = json.loads(ledger.read_text())
    data.pop("http_observations");data.pop("policy");ledger.write_text(json.dumps(data))
    result = inspect_run(cat, path)
    assert result["observations"] is None and result["quota_windows"][0]["http"] is None
    assert result["quota_windows"][0]["allocated_limits"] is None and not result["identity_verified"]


def test_crashed_invocation_is_marked_incomplete_and_preserves_http_uncertainty(tmp_path):
    cat, path, _ = build(tmp_path, max_batches=1, batch_size=1)
    state = json.loads((path / "checkpoint.json").read_text());state["active_invocation"] = {"started_at": state["observations"]["first_started_at"]}
    (path / "checkpoint.json").write_text(json.dumps(state))
    quota = QuotaWindow(path, window="synthetic-night", limits={"TEST": 200}, rate_card=RATE)
    quota.reserve("TEST", 20);quota.http_started("TEST")  # simulates termination before confirmed response
    produce_catalogue(cat, path, Measured(), window="synthetic-night", limits={"TEST": 200}, rate_card=RATE, act=True)
    result = inspect_run(cat, path)
    assert not result["observations"]["history_complete"] and result["observations"]["interrupted_invocations"] == 1
    assert result["quota_windows"][0]["http"]["uncertain_inflight"] == 1
    assert any("measurement" in x for x in capacity_preflight({"NASDAQ": result})["blockers"])


def test_import_is_read_only_and_refuses_active_writer_tamper_and_escape(tmp_path):
    import fcntl
    cat, path, _ = build(tmp_path)
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob("*") if p.is_file()}
    inspect_run(cat, path)
    assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob("*") if p.is_file()}
    with (path / "run.lock").open("r") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="running producer"):
            inspect_run(cat, path)
    state = json.loads((path / "checkpoint.json").read_text());state["items"]["S0000"]["input_file"] = "../outside.json"
    (path / "checkpoint.json").write_text(json.dumps(state))
    with pytest.raises(ValueError, match="inside"):
        inspect_run(cat, path)


def complete_policy():
    return {**{k: 10000 for k in ["max_catalogue_age_seconds", "max_input_age_seconds", "max_quote_age_seconds",
                                 "max_night_seconds", "max_sec_sweep_seconds", "max_operating_fact_age_seconds"]},
            "required_free_memory_bytes": 100, "required_disk_free_bytes": 100,
            "max_cpu_peak_percent": 90, "target_head_sha": "d" * 40}


def synthetic_bundle(tmp_path, runs, policy):
    """All facts are fabricated contract fixtures, never operational evidence."""
    at = datetime.now(timezone.utc)
    binding = capacity_preflight(runs, policy=policy)["bindings"]
    interval = {"measurement_started_at": (at - timedelta(hours=1)).isoformat(), "measurement_ended_at": at.isoformat()}
    claims = {
        "provider_budgets": {**interval, "providers": {"TEST": {"contracted_units": 1000, "other_workers_committed_units": 100,
                                "other_workers_measured_units": 80, "reserve_units": 100, "allocated_by_market": {m: 200 for m in runs},
                                "contracted_requests_per_second": 10, "observed_peak_requests_per_second": 2,
                                "prospective_rate_enforcement_reviewed": True}}},
        "host": {**interval, "memory_peak_bytes": 1000, "free_memory_min_bytes": 1000, "disk_free_min_bytes": 1000,
                 "cpu_peak_percent": 20, "rss_coverage_complete": True, "concurrent_workers_included": True},
        "sec": {**interval, "distinct_ciks": 2, "mapped_us_names": 6, "unmapped_us_names": 0, "complete_sweep_seconds": 20,
                "backfill_pending_ciks": 0, "configured_requests_per_second": 2.5, "shared_processes_requests_per_second": 7.5,
                "fair_access_limit_per_second": 8, "cik_population_sha256": "c" * 64, "complete": True, "all_upstream_calls_included": True},
        "operating_window": {"pit_running": 0, "pit_blocking": 0, "deployment_window_confirmed": True, "observed_at": at.isoformat()},
        "fable_review": {"verdict": "GO", "scope": "full_universe_production", "head_sha": policy["target_head_sha"],
                         "comment_url": "https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/issues/429#issuecomment-123456789"},
    }
    manifest = {"schema": "FULL-UNIVERSE-CAPACITY-BUNDLE-v1", "facts": {}}
    for kind, values in claims.items():
        value = {"schema": "FULL-UNIVERSE-CAPACITY-FACT-v1", "kind": kind, "bindings": binding,
                 "valid_from": (at - timedelta(hours=1)).isoformat(), "valid_until": (at + timedelta(hours=1)).isoformat(), "values": values}
        path = tmp_path / (kind + ".json");path.write_text(json.dumps(value))
        manifest["facts"][kind] = {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    path = tmp_path / "bundle.json";path.write_text(json.dumps(manifest))
    return path


def synthetic_verifier(value, at):
    return {"schema": "FULL-UNIVERSE-CAPACITY-ATTESTATION-v1", "kind": value["kind"], "artifact_sha256": value["artifact_sha256"],
            "bundle_sha256": value["bundle_sha256"], "bindings_sha256": value["bindings_sha256"], "verified_at": at.isoformat()}


@pytest.fixture
def world(tmp_path):
    runs = {market: build(tmp_path, market)[2] for market in ["B3", "NASDAQ", "NYSE"]}
    policy = complete_policy()
    return runs, policy, synthetic_bundle(tmp_path, runs, policy)


def test_hashes_and_declared_go_alone_never_attest_capacity_or_allow_publication(world):
    runs, policy, bundle = world
    receipt = capacity_preflight(runs, policy=policy, bundle=bundle)
    assert not receipt["capacity_evidence_ready_for_review"]
    assert sum("independent_attestation_missing" in item for item in receipt["blockers"]) == 5
    assert not receipt["publication"]["production_release_allowed"]
    assert not capacity_preflight(runs, policy=policy, bundle=bundle, evidence_verifier=lambda *args: True)["capacity_evidence_ready_for_review"]


def test_even_complete_synthetic_contract_only_prepares_review_and_has_no_writer(world):
    runs, policy, bundle = world
    receipt = capacity_preflight(runs, policy=policy, bundle=bundle, evidence_verifier=synthetic_verifier)
    assert receipt["capacity_evidence_ready_for_review"], receipt["blockers"]
    assert receipt["publication"]["state"] == "PREPARATION_ONLY"
    assert not receipt["publication"]["production_release_allowed"]
    assert not receipt["publication"]["generation_writer_implemented"] and not receipt["publication"]["schedule_installed"]


def mutate_fact(bundle, kind, change):
    manifest = json.loads(bundle.read_text());path = bundle.parent / manifest["facts"][kind]["path"]
    value = json.loads(path.read_text());change(value);path.write_text(json.dumps(value))
    manifest["facts"][kind]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest();bundle.write_text(json.dumps(manifest))


@pytest.mark.parametrize("kind,change,blocker", [
    ("provider_budgets", lambda v: v["values"]["providers"]["TEST"].update(other_workers_committed_units=900), "contract_or_shared_budget"),
    ("host", lambda v: v["values"].update(rss_coverage_complete=False), "host_capacity"),
    ("sec", lambda v: v["values"].update(mapped_us_names=5), "sec_population"),
    ("sec", lambda v: v["values"].update(backfill_pending_ciks=1), "sec_pending_backfill"),
    ("operating_window", lambda v: v["values"].update(pit_running=1), "pit_free"),
    ("operating_window", lambda v: v["values"].update(pit_running=False), "pit_free"),
    ("operating_window", lambda v: v["values"].update(observed_at="2020-01-01T00:00:00+00:00"), "pit_free"),
    ("fable_review", lambda v: v["values"].update(head_sha="e" * 40), "exact_head"),
])
def test_independent_attestation_cannot_override_concrete_capacity_gates(world, kind, change, blocker):
    runs, policy, bundle = world
    mutate_fact(bundle, kind, change)
    result = capacity_preflight(runs, policy=policy, bundle=bundle, evidence_verifier=synthetic_verifier)
    assert not result["capacity_evidence_ready_for_review"]
    assert any(blocker in item for item in result["blockers"])


def test_bundle_binding_tamper_raw_logs_and_future_input_clocks_are_refused(world, tmp_path):
    runs, policy, bundle = world
    mutate_fact(bundle, "host", lambda v: v["bindings"]["run_identities"].update(NASDAQ="f" * 64))
    with pytest.raises(ValueError, match="binding"):
        capacity_preflight(runs, policy=policy, bundle=bundle)
    bundle = synthetic_bundle(tmp_path, runs, policy)
    mutate_fact(bundle, "host", lambda v: v["values"].update(raw_private_log="never return this"))
    with pytest.raises(ValueError, match="unrecognized fields"):
        capacity_preflight(runs, policy=policy, bundle=bundle)


def test_closed_cli_accepts_empty_manifest_without_touching_database_or_network(tmp_path, monkeypatch, capsys):
    manifest = tmp_path / "runs.json";manifest.write_text("{}")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network forbidden")))
    assert main(["--runs", str(manifest)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert not result["publication"]["production_release_allowed"] and "complete_three_market_evidence_missing" in result["blockers"]


def test_future_catalogue_and_input_after_completion_are_refused(tmp_path):
    cat, path, _ = build(tmp_path)
    future = copy.deepcopy(cat.payload())
    future["received_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    from app.listed_universe import catalogue_from_payload
    future.pop("manifest_sha256");future["manifest_sha256"] = digest(future)
    future_cat = catalogue_from_payload(future)
    future_path = tmp_path / "future"
    produce_catalogue(future_cat, future_path, Measured(), window="synthetic-night", limits={"TEST": 200}, rate_card=RATE, act=True)
    with pytest.raises(ValueError, match="catalogue receipt lies in the future"):
        inspect_run(future_cat, future_path)
    state = json.loads((path / "checkpoint.json").read_text())
    artifact = path / state["items"]["S0000"]["input_file"]
    data = json.loads(artifact.read_text())
    data["payload"]["received_at"] = (datetime.now(timezone.utc) - timedelta(microseconds=1)).isoformat()
    data["sha256"] = digest({k: v for k, v in data.items() if k != "sha256"})
    artifact.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="later than completed"):
        inspect_run(cat, path)


def test_self_declared_complete_history_cannot_hide_missing_phase_or_http_metrics(tmp_path):
    cat, path, _ = build(tmp_path)
    state = json.loads((path / "checkpoint.json").read_text())
    state["observations"]["phase_calls"] = {};state["observations"]["phase_duration_seconds"] = {}
    (path / "checkpoint.json").write_text(json.dumps(state))
    with pytest.raises(ValueError, match="causal phases"):
        inspect_run(cat, path)


def test_deleted_checkpoint_does_not_reset_existing_quota_and_artifacts(tmp_path):
    cat, path, _ = build(tmp_path)
    (path / "checkpoint.json").unlink()
    with pytest.raises(ValueError, match="checkpoint missing"):
        produce_catalogue(cat, path, Measured(), window="synthetic-night", limits={"TEST": 200}, rate_card=RATE, act=True)


def test_binding_covers_unique_run_and_metric_bytes_and_reviewed_policy(world):
    runs, policy, bundle = world
    changed = copy.deepcopy(runs)
    changed["NASDAQ"]["run_id"] = "another-run-with-the-same-deterministic-identity"
    changed["NASDAQ"]["evidence_sha256"] = digest({k: v for k, v in changed["NASDAQ"].items() if k != "evidence_sha256"})
    with pytest.raises(ValueError, match="binding"):
        capacity_preflight(changed, policy=policy, bundle=bundle, evidence_verifier=synthetic_verifier)
    with pytest.raises(ValueError, match="binding"):
        capacity_preflight(runs, policy={**policy, "max_night_seconds": 20000}, bundle=bundle, evidence_verifier=synthetic_verifier)


def test_reviewed_backfill_forecast_keeps_missing_names_closed_without_changing_sec_parameters(world):
    runs, policy, bundle = world
    mutate_fact(bundle, "sec", lambda v: v["values"].update(backfill_pending_ciks=12, backfill_budget_per_poll=3,
                backfill_expected_polls=4, backfill_plan_reviewed=True, pending_names_retained_not_evaluable=True,
                pending_names_buy_denied=True, backfill_forecast_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat()))
    result = capacity_preflight(runs, policy=policy, bundle=bundle, evidence_verifier=synthetic_verifier)
    assert result["capacity_evidence_ready_for_review"], result["blockers"]
    assert not result["publication"]["production_release_allowed"]


@pytest.mark.parametrize("where", ["runtime_flag", "http_flag", "stage_flag", "stage_schema"])
def test_history_flags_are_literal_booleans_and_stage_schema_is_exact(tmp_path, where):
    cat, path, _ = build(tmp_path)
    target = next(path.glob("quota-*.json")) if where == "http_flag" else path / "checkpoint.json"
    value = json.loads(target.read_text())
    if where == "runtime_flag":
        value["observations"]["history_complete"] = "false"
    elif where == "http_flag":
        value["http_observations"]["history_complete"] = "false"
    elif where == "stage_flag":
        value["stage_observations"]["history_complete"] = "false"
    else:
        value["stage_observations"]["schema"] = "UNKNOWN"
    target.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        inspect_run(cat, path)


def test_http_status_counts_cannot_use_booleans_or_unknown_provider_groups(tmp_path):
    cat, path, _ = build(tmp_path)
    target = next(path.glob("quota-*.json"));value = json.loads(target.read_text())
    value["http_observations"]["status_counts"] = {"200": True, "404": 2}
    target.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="status counters"):
        inspect_run(cat, path)


def test_stage_publication_cannot_be_backdated_before_completion_or_future(tmp_path):
    cat, path, _ = build(tmp_path)
    target = path / "checkpoint.json";value = json.loads(target.read_text())
    value["stage_published_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    target.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="publication clock"):
        inspect_run(cat, path)
