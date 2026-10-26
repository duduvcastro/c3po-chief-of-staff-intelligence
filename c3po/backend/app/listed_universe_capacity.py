"""Read-only capacity evidence importer and closed publication preparation.

Local checkpoint integrity is verifiable here. A digest is not authority for a
provider contract, host/SEC measurement, PIT window or Fable's verdict: external
facts need an independently injected verifier. No verifier, write, activation or
schedule is provided by the CLI. Synthetic tests are never a capacity attestation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from .listed_universe import Catalogue, catalogue_from_payload, digest, utc
from .listed_universe_runtime import RUN_SCHEMA, producer_identity

SCHEMA = "FULL-UNIVERSE-CAPACITY-EVIDENCE-v1"
MARKETS = {"B3", "NASDAQ", "NYSE"}
KINDS = {"provider_budgets", "host", "sec", "operating_window", "fable_review"}
Verifier = Callable[[Mapping[str, Any], datetime], Mapping[str, Any] | None]
MEASURED = {"measurement_started_at", "measurement_ended_at"}
PROVIDER_FIELDS = {"contracted_units", "other_workers_committed_units", "other_workers_measured_units", "reserve_units",
                   "contracted_requests_per_second", "observed_peak_requests_per_second", "allocated_by_market",
                   "prospective_rate_enforcement_reviewed"}
FACT_FIELDS = {"provider_budgets": MEASURED | {"providers"},
               "host": MEASURED | {"memory_peak_bytes", "free_memory_min_bytes", "disk_free_min_bytes", "cpu_peak_percent",
                                    "rss_coverage_complete", "concurrent_workers_included"},
               "sec": MEASURED | {"distinct_ciks", "mapped_us_names", "unmapped_us_names", "complete_sweep_seconds",
                                   "backfill_pending_ciks", "configured_requests_per_second", "shared_processes_requests_per_second",
                                   "fair_access_limit_per_second", "cik_population_sha256", "complete", "all_upstream_calls_included"},
               "operating_window": {"pit_running", "pit_blocking", "deployment_window_confirmed", "observed_at"},
               "fable_review": {"verdict", "scope", "head_sha", "comment_url"}}
FACT_FIELDS["sec"] |= {"backfill_plan_reviewed", "backfill_budget_per_poll", "backfill_expected_polls",
                       "backfill_forecast_at", "pending_names_retained_not_evaluable", "pending_names_buy_denied"}


def _number(value, *, integer=False):
    return (not isinstance(value, bool) and isinstance(value, int if integer else (int, float))
            and math.isfinite(value) and value >= 0)


def _json(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("evidence must be a bounded ordinary local file")
    raw = path.read_bytes()
    def invalid_constant(_):
        raise ValueError("non-finite evidence numbers are not accepted")
    return json.loads(raw, parse_constant=invalid_constant), hashlib.sha256(raw).hexdigest()


def _inside(directory: Path, name: str) -> Path:
    part = Path(name)
    if part.is_absolute() or not part.parts or any(item in {".", ".."} for item in part.parts):
        raise ValueError("evidence path must stay inside its supplied directory")
    target = directory / part
    if any(parent.is_symlink() for parent in [target, *target.parents] if parent != directory.parent):
        raise ValueError("symlinked evidence paths are not accepted")
    if not target.resolve().is_relative_to(directory.resolve()):
        raise ValueError("evidence path escapes its supplied directory")
    return target


@contextmanager
def _read_lock(directory: Path):
    # Opening r, no mkdir/chmod/touch: inspection cannot create a fake run.
    with _inside(directory, "run.lock").open("r") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("a running producer is changing this checkpoint") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _artifact(directory, name, identity, symbol):
    value, sha = _json(_inside(directory, name))
    core = {key: item for key, item in value.items() if key != "sha256"}
    if (value.get("identity") != identity or value.get("symbol") != symbol
            or value.get("sha256") != digest(core)):
        raise ValueError("checkpoint artifact identity/digest mismatch")
    return value["payload"], sha


def inspect_run(catalogue: Catalogue, directory: Path, *, now: datetime | None = None) -> dict:
    """Reconcile actual local artifacts without contacting a provider or DB."""
    at = utc(now or datetime.now(timezone.utc))
    files, inputs, quote_times, receipt_times = {}, {}, [], []
    with _read_lock(directory):
        state, files["checkpoint.json"] = _json(_inside(directory, "checkpoint.json"))
        names = {item.symbol for item in catalogue.listings if item.security_type != "ETF"}
        if (state.get("schema") != RUN_SCHEMA or state.get("market") != catalogue.market
                or state.get("catalogue_manifest_sha256") != catalogue.payload()["manifest_sha256"]
                or set(state.get("items", {})) != names):
            raise ValueError("checkpoint does not reconcile to the supplied complete official catalogue")
        adapter = state.get("adapter_identity")
        if not re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", str(state.get("run_id") or "")):
            raise ValueError("checkpoint run UUID is invalid")
        identity_verified = isinstance(adapter, Mapping) and state["identity"] == digest({
            "catalogue": catalogue.payload()["manifest_sha256"], "producer_files": state["producer_files"], "adapter": adapter})
        if adapter is not None and not identity_verified:
            raise ValueError("checkpoint run identity does not match its recorded pins")
        if utc(catalogue.received_at) > at:
            raise ValueError("catalogue receipt lies in the future")
        counts = Counter()
        attempts, reasons, ciks = 0, Counter(), set()
        for symbol, item in state["items"].items():
            status = item.get("status")
            if status not in {"pending", "fetching", "inputs_ready", "valued", "not_evaluable"}:
                raise ValueError("unknown checkpoint outcome")
            if not _number(item.get("attempts"), integer=True):
                raise ValueError("invalid input attempt count")
            counts[status] += 1
            attempts += item["attempts"]
            if status == "not_evaluable":
                if not re.fullmatch(r"[a-z0-9_]+", str(item.get("reason") or "")):
                    raise ValueError("not-evaluable name lacks its public reason")
                reasons[item["reason"]] += 1
            if item.get("input_file"):
                value, sha = _artifact(directory, item["input_file"], state["identity"], symbol)
                files[item["input_file"]] = sha
                inputs[symbol] = True
                for field, target in [("received_at", receipt_times)]:
                    if value.get(field) is not None:
                        target.append(utc(value[field]))
                quote = value.get("quote")
                if isinstance(quote, Mapping) and quote.get("as_of") is not None:
                    quote_times.append(utc(quote["as_of"]))
                raw_cik = (value.get("fundamental") or {}).get("cik")
                if isinstance(raw_cik, (int, str)) and re.fullmatch(r"[0-9]{1,10}", str(raw_cik)):
                    ciks.add(str(raw_cik).zfill(10))
            if status in {"inputs_ready", "valued"} and not item.get("input_file"):
                raise ValueError("resolved name lacks its input artifact")
            if status == "valued":
                value, sha = _artifact(directory, item["row_file"], state["identity"], symbol)
                files[item["row_file"]] = sha
                if value.get("symbol") != symbol:
                    raise ValueError("valued row changed official identity")
        if any(value > at for value in [*receipt_times, *quote_times]):
            raise ValueError("input/quote receipt lies in the future")
        complete = state.get("status") == "complete"
        if complete and counts["pending"] + counts["fetching"] + counts["inputs_ready"]:
            raise ValueError("complete checkpoint still has pending names")
        if complete:
            context, sha = _artifact(directory, "context.json", state["identity"], "CONTEXT")
            files["context.json"] = sha
            if digest(context) != state.get("context_sha256") or utc(state["completed_at"]) > at:
                raise ValueError("completed context or completion clock is inconsistent")
            cut = utc(state["completed_at"])
            if any(value > cut for value in [utc(catalogue.received_at), *receipt_times, *quote_times]):
                raise ValueError("catalogue/input/quote receipt is later than completed valuation")
        windows = []
        for path in sorted(directory.glob("quota-*.json")):
            ledger, sha = _json(path)
            files[path.name] = sha
            if path.name != "quota-" + hashlib.sha256(ledger["window"].encode()).hexdigest() + ".json":
                raise ValueError("quota ledger window filename mismatch")
            policy = ledger.get("policy")
            if policy is not None and digest(policy) != ledger.get("policy_sha256"):
                raise ValueError("quota policy/digest mismatch")
            if policy is not None and (policy.get("window") != ledger["window"]
                                       or set(policy.get("limits", {})) != set(ledger.get("used", {}))
                                       or not all(_number(v, integer=True) for v in policy.get("limits", {}).values())
                                       or any(ledger["used"][k] > v for k, v in policy.get("limits", {}).items())):
                raise ValueError("quota reservations exceed the recorded policy")
            if (not isinstance(ledger.get("used"), Mapping) or not all(_number(v, integer=True) for v in ledger["used"].values())
                    or not all(isinstance(k, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", k) for k in ledger["used"])
                    or not _number(ledger.get("reservations"), integer=True)):
                raise ValueError("invalid quota reservation counters")
            http = ledger.get("http_observations")
            if http is not None:
                numeric = ["attempts_started", "responses", "transport_failures", "uncertain_inflight", "response_bytes"]
                statuses = http.get("status_counts")
                if (not isinstance(statuses, Mapping) or not all(isinstance(k, str) and re.fullmatch(r"[1-5][0-9]{2}", k)
                                                                and _number(v, integer=True) for k, v in statuses.items())):
                    raise ValueError("HTTP status counters are invalid")
                if (http.get("schema") != "FULL-UNIVERSE-HTTP-OBSERVATIONS-v1" or not isinstance(http.get("history_complete"), bool)
                        or not all(_number(http.get(key), integer=True) for key in numeric)
                        or http["responses"] + http["transport_failures"] + http["uncertain_inflight"] != http["attempts_started"]
                        or sum(http.get("status_counts", {}).values()) != http["responses"]
                        or http["attempts_started"] > ledger["reservations"]):
                    raise ValueError("HTTP counters do not reconcile to quota reservations")
                groups = http.get("by_provider")
                if (not isinstance(groups, Mapping) or set(groups) - set(ledger["used"])
                        or any(not isinstance(v, Mapping) for v in groups.values())):
                    raise ValueError("HTTP provider counters are incomplete")
                for key in ["attempts_started", "responses", "transport_failures", "response_bytes"]:
                    if not all(_number(v.get(key), integer=True) for v in groups.values()) or sum(v[key] for v in groups.values()) != http[key]:
                        raise ValueError("HTTP provider counters do not reconcile")
                if not _number(http.get("observed_seconds")) or ((http["responses"] + http["transport_failures"]) and http["observed_seconds"] <= 0):
                    raise ValueError("HTTP measurement duration is incomplete")
                if http["attempts_started"]:
                    first, last = utc(http["first_started_at"]), utc(http["last_started_at"])
                    if first > last or last > at or (complete and last > utc(state["completed_at"])):
                        raise ValueError("HTTP measurement interval is inconsistent")
            windows.append({"window": ledger["window"], "policy_sha256": ledger["policy_sha256"],
                            "allocated_limits": policy.get("limits") if policy else None,
                            "reserved_billable_units": ledger["used"], "reservations": ledger["reservations"],
                            "http": http, "hold_reason": ledger.get("hold_reason")})
        stats = state.get("observations")
        times = [utc(value) for value in [stats.get("first_started_at") if stats else None,
                                         stats.get("last_finished_at") if stats else None] if value is not None]
        if len(times) == 2 and (times[0] > times[1] or times[1] > at):
            raise ValueError("runtime measurement interval is inconsistent")
        if stats is not None:
            counters = ["completed_invocations", "interrupted_invocations", "cached_input_reads", "cached_row_reads", "input_transient_failures"]
            if (stats.get("schema") != "FULL-UNIVERSE-OBSERVATIONS-v1" or not isinstance(stats.get("history_complete"), bool)
                    or not all(_number(stats.get(k), integer=True) for k in counters)
                    or not _number(stats.get("observed_duration_seconds"))):
                raise ValueError("runtime observation counters are incomplete")
            calls, seconds, failures = stats.get("phase_calls"), stats.get("phase_duration_seconds"), stats.get("phase_failures")
            if (not all(isinstance(v, Mapping) for v in [calls, seconds, failures])
                    or set(calls) - {"collect", "context", "value"} or set(calls) != set(seconds)
                    or not all(_number(v, integer=True) for v in calls.values())
                    or not all(_number(v) and (calls[k] == 0 or v > 0) for k, v in seconds.items())
                    or set(failures) - set(calls) or not all(_number(v, integer=True) and v <= calls[k] for k, v in failures.items())):
                raise ValueError("runtime phase observations are incomplete")
            if stats.get("history_complete") is True and not state.get("active_invocation"):
                if (len(times) != 2 or utc(catalogue.received_at) > times[0] or not stats["completed_invocations"]
                        or stats["observed_duration_seconds"] <= 0
                        or sum(seconds.values()) > stats["observed_duration_seconds"]
                        or (complete and (not calls.get("context") or not calls.get("value") or calls.get("collect", 0) < attempts))):
                    raise ValueError("complete measured run lacks its causal phases/interval")
        stage = state.get("stage_observations")
        if stage is not None and (stage.get("schema") != "FULL-UNIVERSE-STAGE-OBSERVATIONS-v1"
                                  or not isinstance(stage.get("history_complete"), bool)):
            raise ValueError("stage observation schema/history flag is invalid")
        if stage is not None and not state.get("active_stage_attempt"):
            if (not _number(stage.get("attempts"), integer=True) or not stage["attempts"]
                    or not _number(stage.get("observed_seconds")) or stage["observed_seconds"] <= 0
                    or not _number(stage.get("records_considered"), integer=True)
                    or not _number(stage.get("records_inserted_last_attempt"), integer=True)):
                raise ValueError("stage observations are incomplete")
            if (utc(stage["first_started_at"]) < utc(state["completed_at"])
                    or utc(stage["last_finished_at"]) < utc(stage["first_started_at"]) or utc(stage["last_finished_at"]) > at
                    or stage["records_considered"] != counts["valued"] * 2
                    or stage["records_inserted_last_attempt"] > stage["records_considered"]):
                raise ValueError("stage measurement or dual-record completeness is inconsistent")
            if (not re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", str(state.get("stage_snapshot_id") or ""))
                    or not utc(state["completed_at"]) <= utc(state["stage_published_at"]) <= utc(stage["last_finished_at"])):
                raise ValueError("stage identity/publication clock is inconsistent")
    result = {"schema": "FULL-UNIVERSE-RUN-EVIDENCE-v1", "market": catalogue.market, "run_id": state["run_id"], "identity": state["identity"],
            "catalogue_manifest_sha256": catalogue.payload()["manifest_sha256"],
            "catalogue_received_at": catalogue.received_at, "catalogue_source_date": catalogue.source_date,
            "code_pins_sha256": digest(state["producer_files"]), "current_code_matches": state["producer_files"] == producer_identity(),
            "identity_verified": identity_verified, "complete": complete, "inventory_count": len(names),
            "processed_count": counts["valued"] + counts["not_evaluable"], "valued_count": counts["valued"],
            "not_evaluable_count": counts["not_evaluable"], "remaining": counts["pending"] + counts["fetching"] + counts["inputs_ready"],
            "classified_equity_count": sum(item.listing_class == "equity" for item in catalogue.listings if item.security_type != "ETF"),
            "not_evaluable_reasons": dict(reasons), "input_attempts": attempts,
            "input_retry_attempts": sum(max(0, item["attempts"] - 1) for item in state["items"].values()),
            "input_artifacts": len(inputs), "dated_input_receipts": len(receipt_times), "dated_quotes": len(quote_times),
            "oldest_input_received_at": min(receipt_times).isoformat() if receipt_times else None,
            "oldest_quote_at": min(quote_times).isoformat() if quote_times else None,
            "known_ciks_in_inputs": len(ciks), "distinct_sec_ciks": None,
            "sec_population_completeness": "not_measured_by_this_producer",
            "observations": stats, "active_invocation": state.get("active_invocation"),
            "stage_observations": state.get("stage_observations"), "stage_snapshot_id": state.get("stage_snapshot_id"),
            "active_stage_attempt": state.get("active_stage_attempt"),
            "quota_windows": windows, "artifact_sha256": files,
            "integrity_note": "local bytes/digests checked; not an external capacity or scientific attestation"}
    result["evidence_sha256"] = digest(result)
    return result


def _external_facts(bundle: Path | None, bindings: Mapping, at: datetime, verifier: Verifier | None):
    facts, errors = {}, []
    if bundle is None:
        return facts, ["external_capacity_evidence_missing"]
    manifest, manifest_sha = _json(bundle)
    if manifest.get("schema") != "FULL-UNIVERSE-CAPACITY-BUNDLE-v1":
        raise ValueError("unknown capacity evidence bundle")
    for kind in sorted(KINDS):
        reference = manifest.get("facts", {}).get(kind)
        if not isinstance(reference, Mapping):
            errors.append(kind + "_evidence_missing")
            continue
        value, sha = _json(_inside(bundle.parent, reference["path"]))
        if (sha != reference.get("sha256") or value.get("schema") != "FULL-UNIVERSE-CAPACITY-FACT-v1"
                or value.get("kind") != kind or value.get("bindings") != bindings
                or not isinstance(value.get("values"), Mapping)):
            raise ValueError("capacity evidence artifact/schema/binding mismatch")
        if set(value["values"]) - FACT_FIELDS[kind]:
            raise ValueError("capacity fact contains unrecognized fields; no raw logs or credentials accepted")
        if kind == "provider_budgets":
            providers = value["values"].get("providers", {})
            if (not isinstance(providers, Mapping) or any(not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", key)
                                                        or not isinstance(item, Mapping) or set(item) - PROVIDER_FIELDS
                                                        for key, item in providers.items())):
                raise ValueError("invalid provider fact fields")
        # Receipts expose typed aggregate facts, never arbitrary raw text/logs.
        for key, item in value["values"].items():
            if key == "providers":
                for data in item.values():
                    for metric, number in data.items():
                        if metric == "allocated_by_market":
                            if not isinstance(number, Mapping) or set(number) - MARKETS or any(not _number(n, integer=True) for n in number.values()):
                                raise ValueError("invalid allocated quota values")
                        elif number is not None and not isinstance(number, (int, float, bool)):
                            raise ValueError("provider receipt accepts aggregate numbers only")
            elif key in MEASURED or key in {"observed_at", "backfill_forecast_at"}:
                if item is not None:
                    try:
                        utc(item)
                    except (TypeError, ValueError):
                        raise ValueError("invalid capacity measurement clock") from None
            elif key in {"head_sha", "cik_population_sha256"}:
                if item is not None and not re.fullmatch(r"[a-f0-9]{" + ("40" if key == "head_sha" else "64") + "}", str(item)):
                    raise ValueError("invalid capacity source pin")
            elif key == "comment_url":
                if not re.fullmatch(r"https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/issues/429#issuecomment-[0-9]+", str(item)):
                    raise ValueError("review source must identify the coordination issue comment")
            elif key == "verdict":
                if item not in {None, "GO", "NO_GO", "PENDING"}:
                    raise ValueError("invalid review verdict")
            elif key == "scope":
                if item not in {None, "full_universe_production"}:
                    raise ValueError("invalid review scope")
            elif item is not None and not isinstance(item, (int, float, bool)):
                raise ValueError("capacity receipt accepts aggregate numbers only")
        valid = utc(value["valid_from"]) <= at < utc(value["valid_until"])
        attested = False
        if verifier is not None and valid:
            try:
                checked = verifier({"kind": kind, "artifact_sha256": sha, "bundle_sha256": manifest_sha,
                                    "bindings_sha256": digest(bindings), "fact": value}, at)
                expected = {"schema": "FULL-UNIVERSE-CAPACITY-ATTESTATION-v1", "kind": kind,
                            "artifact_sha256": sha, "bundle_sha256": manifest_sha,
                            "bindings_sha256": digest(bindings), "verified_at": at.isoformat()}
                attested = isinstance(checked, Mapping) and all(checked.get(k) == v for k, v in expected.items())
            except Exception:
                attested = False
        facts[kind] = {"artifact_sha256": sha, "valid_now": valid, "independently_attested": attested,
                       "reported_values": value["values"]}
        if not valid:
            errors.append(kind + "_evidence_expired_or_future")
        if not attested:
            errors.append(kind + "_independent_attestation_missing")
    return facts, errors


def capacity_preflight(runs: Mapping[str, Mapping], *, policy: Mapping | None = None,
                       bundle: Path | None = None, now: datetime | None = None,
                       evidence_verifier: Verifier | None = None) -> dict:
    """Prepare a reviewable plan; this function has no publication capability."""
    at, policy = utc(now or datetime.now(timezone.utc)), dict(policy or {})
    blockers = []
    for run in runs.values():
        if (run.get("schema") != "FULL-UNIVERSE-RUN-EVIDENCE-v1"
                or run.get("evidence_sha256") != digest({k: v for k, v in run.items() if k != "evidence_sha256"})):
            raise ValueError("run evidence envelope/digest mismatch; inspect the actual checkpoint first")
    if set(runs) != MARKETS:
        blockers.append("complete_three_market_evidence_missing")
    bindings = {"catalogue_manifests": {m: r["catalogue_manifest_sha256"] for m, r in sorted(runs.items())},
                "run_identities": {m: r["identity"] for m, r in sorted(runs.items())},
                "run_ids": {m: r["run_id"] for m, r in sorted(runs.items())},
                "run_evidence": {m: r["evidence_sha256"] for m, r in sorted(runs.items())},
                "policy_sha256": digest(policy),
                "code_pins": {m: r["code_pins_sha256"] for m, r in sorted(runs.items())}}
    facts, errors = _external_facts(bundle, bindings, at, evidence_verifier)
    blockers.extend(errors)
    limits = ["max_catalogue_age_seconds", "max_input_age_seconds", "max_quote_age_seconds", "max_night_seconds",
              "required_free_memory_bytes", "required_disk_free_bytes", "max_cpu_peak_percent", "max_sec_sweep_seconds",
              "max_operating_fact_age_seconds"]
    if not all(_number(policy.get(key)) and policy[key] > 0 for key in limits):
        blockers.append("reviewed_capacity_and_freshness_policy_missing")
    for market, run in sorted(runs.items()):
        prefix = market + ":"
        if (run.get("market") != market or run.get("complete") is not True or run.get("remaining") != 0
                or run.get("processed_count") != run.get("inventory_count") or not run.get("valued_count")):
            blockers.append(prefix + "complete_reconciled_valued_cohort_missing")
        if run.get("identity_verified") is not True or run.get("current_code_matches") is not True:
            blockers.append(prefix + "current_pinned_run_identity_missing")
        stats = run.get("observations")
        if (not stats or stats.get("history_complete") is not True or run.get("active_invocation")
                or stats.get("interrupted_invocations") or not stats.get("last_finished_at")):
            blockers.append(prefix + "complete_measured_interval_missing")
        elif _number(policy.get("max_night_seconds")) and (utc(stats["last_finished_at"]) - utc(stats["first_started_at"])).total_seconds() > policy["max_night_seconds"]:
            blockers.append(prefix + "night_window_exceeded")
        stage = run.get("stage_observations")
        if (not run.get("stage_snapshot_id") or not stage or stage.get("history_complete") is not True
                or run.get("active_stage_attempt") or not stage.get("last_finished_at")):
            blockers.append(prefix + "canonical_stage_measurement_missing_or_interrupted")
        elif stats and _number(policy.get("max_night_seconds")) and (utc(stage["last_finished_at"]) - utc(stats["first_started_at"])).total_seconds() > policy["max_night_seconds"]:
            blockers.append(prefix + "night_window_exceeded_including_stage")
        for field, limit in [("catalogue_received_at", "max_catalogue_age_seconds"),
                             ("oldest_input_received_at", "max_input_age_seconds"), ("oldest_quote_at", "max_quote_age_seconds")]:
            if not run.get(field) or not _number(policy.get(limit)) or not 0 <= (at - utc(run[field])).total_seconds() <= policy[limit]:
                blockers.append(prefix + limit.replace("max_", "") + "_unverified_or_stale")
        if run.get("dated_input_receipts") != run.get("input_artifacts") or run.get("dated_quotes") != run.get("input_artifacts"):
            blockers.append(prefix + "full_input_and_quote_clock_coverage_missing")
        if not run.get("quota_windows"):
            blockers.append(prefix + "quota_window_evidence_missing")
        for window in run.get("quota_windows", []):
            http = window.get("http")
            if (not window.get("allocated_limits") or not http or http.get("history_complete") is not True
                    or http.get("uncertain_inflight") or window.get("hold_reason")):
                blockers.append(prefix + "complete_quota_and_http_measurements_missing")
        if (sum(w.get("http", {}).get("responses", 0) for w in run.get("quota_windows", []) if w.get("http"))
                < run.get("input_artifacts", 0)):
            blockers.append(prefix + "input_collection_http_response_coverage_missing")
    # External facts are reported as claims until the independent callback
    # authenticates their provenance. Even authenticated facts need these gates.
    def values(kind):
        item = facts.get(kind, {})
        return item.get("reported_values", {}) if item.get("independently_attested") else {}
    observed_starts = [utc(r["observations"]["first_started_at"]) for r in runs.values() if r.get("observations")]
    observed_ends = [utc(r["observations"]["last_finished_at"]) for r in runs.values()
                     if (r.get("observations") or {}).get("last_finished_at")]
    observed_ends.extend(utc(r["stage_observations"]["last_finished_at"]) for r in runs.values()
                         if (r.get("stage_observations") or {}).get("last_finished_at"))
    def measured(values, *, covers_cohort=False):
        try:
            start, end = utc(values["measurement_started_at"]), utc(values["measurement_ended_at"])
            return bool(start <= end <= at and observed_starts and observed_ends
                        and (start <= min(observed_starts) and end >= max(observed_ends) if covers_cohort else end >= min(observed_starts)))
        except (KeyError, TypeError, ValueError):
            return False
    providers = values("provider_budgets").get("providers")
    observed, allocations = Counter(), {m: Counter() for m in runs}
    for market, run in runs.items():
        for window in run.get("quota_windows", []):
            observed.update(window["reserved_billable_units"])
            allocations[market].update(window.get("allocated_limits") or {})
    if not isinstance(providers, Mapping) or not set(observed) <= set(providers):
        blockers.append("contracted_provider_and_shared_worker_budgets_unverified")
    else:
        for provider, reserved in observed.items():
            budget = providers[provider]
            keys = ["contracted_units", "other_workers_committed_units", "other_workers_measured_units", "reserve_units",
                    "contracted_requests_per_second", "observed_peak_requests_per_second"]
            allocated = budget.get("allocated_by_market", {})
            if (not all(_number(budget.get(k)) for k in keys) or set(allocated) != MARKETS
                    or not all(_number(v, integer=True) for v in allocated.values())
                    or any(allocated.get(m, 0) < allocations[m][provider] for m in runs)
                    or budget["contracted_requests_per_second"] <= 0 or budget["observed_peak_requests_per_second"] <= 0
                    or sum(allocated.values()) + budget["other_workers_committed_units"] + budget["reserve_units"] > budget["contracted_units"]
                    or budget["other_workers_measured_units"] > budget["other_workers_committed_units"]
                    or budget["observed_peak_requests_per_second"] > budget["contracted_requests_per_second"]
                    or budget.get("prospective_rate_enforcement_reviewed") is not True
                    or reserved > sum(allocated.values())):
                blockers.append(provider + ":contract_or_shared_budget_or_rate_gate_failed")
    if not measured(values("provider_budgets"), covers_cohort=True):
        blockers.append("shared_worker_measurement_interval_does_not_cover_cohort")
    host = values("host")
    host_numbers = ["memory_peak_bytes", "free_memory_min_bytes", "disk_free_min_bytes", "cpu_peak_percent"]
    if (not all(_number(host.get(k)) for k in host_numbers) or not host.get("memory_peak_bytes") or host.get("rss_coverage_complete") is not True
            or host.get("concurrent_workers_included") is not True
            or not measured(host, covers_cohort=True)
            or not _number(policy.get("required_free_memory_bytes"))
            or not _number(policy.get("required_disk_free_bytes")) or not _number(policy.get("max_cpu_peak_percent"))
            or host.get("free_memory_min_bytes", -1) < policy.get("required_free_memory_bytes", math.inf)
            or host.get("disk_free_min_bytes", -1) < policy.get("required_disk_free_bytes", math.inf)
            or host.get("cpu_peak_percent", math.inf) > policy.get("max_cpu_peak_percent", -1)):
        blockers.append("complete_host_capacity_or_headroom_unverified")
    sec = values("sec")
    sec_keys = ["distinct_ciks", "mapped_us_names", "unmapped_us_names", "complete_sweep_seconds", "backfill_pending_ciks",
                "configured_requests_per_second", "shared_processes_requests_per_second", "fair_access_limit_per_second"]
    if (not all(_number(sec.get(k)) for k in sec_keys) or sec.get("complete") is not True
            or sec.get("all_upstream_calls_included") is not True or sec.get("unmapped_us_names") != 0
            or sec.get("mapped_us_names") != sum(run.get("classified_equity_count", 0) for m, run in runs.items() if m != "B3")
            or not sec.get("distinct_ciks")
            or sec.get("distinct_ciks", math.inf) > sec.get("mapped_us_names", -1)
            or not _number(policy.get("max_sec_sweep_seconds"))
            or not measured(sec)
            or sec.get("complete_sweep_seconds", math.inf) > policy.get("max_sec_sweep_seconds", -1)
            or sec.get("shared_processes_requests_per_second", math.inf) > sec.get("fair_access_limit_per_second", -1)
            or sec.get("configured_requests_per_second", 0) <= 0
            or sec.get("configured_requests_per_second", math.inf) > sec.get("shared_processes_requests_per_second", -1)
            or not re.fullmatch(r"[a-f0-9]{64}", str(sec.get("cik_population_sha256") or ""))):
        blockers.append("complete_sec_population_sweep_backfill_and_shared_rate_unverified")
    pending_backfill = sec.get("backfill_pending_ciks")
    if _number(pending_backfill) and pending_backfill > 0:
        try:
            budget, polls = sec["backfill_budget_per_poll"], sec["backfill_expected_polls"]
            backfill_plan = (_number(budget, integer=True) and budget > 0 and _number(polls, integer=True)
                             and polls >= math.ceil(pending_backfill / budget) and sec.get("backfill_plan_reviewed") is True
                             and sec.get("pending_names_retained_not_evaluable") is True and sec.get("pending_names_buy_denied") is True
                             and utc(sec["backfill_forecast_at"]) > at)
        except (KeyError, TypeError, ValueError):
            backfill_plan = False
        if not backfill_plan:
            blockers.append("sec_pending_backfill_requires_reviewed_budget_forecast_and_closed_missing_name_guards")
    window = values("operating_window")
    try:
        observed_window_at = utc(window["observed_at"])
        timely_window = (_number(policy.get("max_operating_fact_age_seconds"))
                         and 0 <= (at - observed_window_at).total_seconds() <= policy["max_operating_fact_age_seconds"])
    except (KeyError, TypeError, ValueError):
        timely_window = False
    if (not _number(window.get("pit_running"), integer=True) or not _number(window.get("pit_blocking"), integer=True)
            or window.get("pit_running") != 0 or window.get("pit_blocking") != 0
            or not timely_window or window.get("deployment_window_confirmed") is not True):
        blockers.append("genuine_current_pit_free_operating_window_unverified")
    review = values("fable_review")
    if (review.get("verdict") != "GO" or review.get("scope") != "full_universe_production"
            or not re.fullmatch(r"[a-f0-9]{40}", str(policy.get("target_head_sha") or ""))
            or review.get("head_sha") != policy.get("target_head_sha")):
        blockers.append("fable_production_review_on_exact_head_missing")
    if not review.get("comment_url"):
        blockers.append("fable_review_source_comment_missing")
    blockers = sorted(set(blockers))
    receipt = {"schema": SCHEMA, "as_of": at.isoformat(), "bindings": bindings, "runs": dict(runs), "facts": facts,
            "capacity_evidence_ready_for_review": not blockers, "blockers": blockers,
            "publication": {"state": "PREPARATION_ONLY", "production_release_allowed": False,
                            "generation_writer_implemented": False, "schedule_installed": False,
                            "buy_permission": "DENY_WITHOUT_SEPARATELY_VERIFIED_SCIENTIFIC_SCOPE",
                            "unselected_stages": {m: {"stage_snapshot_id": r.get("stage_snapshot_id"),
                                                       "run_identity": r["identity"], "catalogue_manifest_sha256": r["catalogue_manifest_sha256"]}
                                                  for m, r in sorted(runs.items())},
                            "remaining_code_gate": "reviewed_atomic_three_market_publication_and_expected_generation_cas_required",
                            "future_transaction_contract": [
                                "Re-read genuine current generation/source/version; reject changed predecessor, active freeze or explicit-order conflict, never thaw",
                                "Revalidate three stage snapshot FKs, both canonical record hashes, catalogue counts and unavailable reasons from Database",
                                "Write all three official cycles and records atomically without the per-market automatic activation hook",
                                "Validate all three cycles for exactly the already-selected source/version; never switch source or scientific scope",
                                "Select one generation with expected-predecessor CAS, abort on race; preserve automatic freeze/order/targeted/capture guards",
                                "Review ownership of legacy nightly and IR/on-demand writers so a later capped cycle cannot replace the expanded generation",
                                "Enable a reviewed opt-in schedule only after this transaction exists, capacity/Fable/window interlocks pass and old/new writers cannot race or downgrade coverage"],
                            "no_promotion_via_save_valuation_universe_or_select_generation_cli": True},
            "no_network_no_database_write_no_host_change": True}
    receipt["receipt_sha256"] = digest(receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True, help="JSON market -> catalogue/checkpoint relative paths")
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args(argv)
    manifest, _ = _json(args.runs)
    at = datetime.now(timezone.utc)
    runs = {}
    for market, item in manifest.items():
        catalogue, _ = _json(_inside(args.runs.parent, item["catalogue"]))
        runs[market] = inspect_run(catalogue_from_payload(catalogue), _inside(args.runs.parent, item["checkpoint"]), now=at)
    policy = _json(args.policy)[0] if args.policy else None
    receipt = capacity_preflight(runs, policy=policy, bundle=args.bundle, now=at)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
