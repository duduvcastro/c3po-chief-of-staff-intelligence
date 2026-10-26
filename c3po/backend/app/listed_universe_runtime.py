"""Resumable full-inventory canonical production; no generation activation.

All state is private and fsynced. Collection is bounded by an explicit quota
window and an operator-supplied rate card; no provider quota is guessed. Every
listing gets an outcome, including unavailable inputs and unresolved types.
Canonical methods receive one complete peer context, independent of batch size.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from .listed_universe import Catalogue, Listing, digest, utc
from .market_data.http import MarketDataRequestError
from . import listed_universe_telemetry as telemetry

STAGE_ANALYSIS = "full_universe_stage"
RUN_SCHEMA = "FULL-UNIVERSE-CANONICAL-RUN-v1"


class CollectionPaused(RuntimeError):
    pass


class TransientInputFailure(MarketDataRequestError):
    pass


class UnavailableInput(RuntimeError):
    """The message is a public reason code, never a provider response or secret."""


def ready(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [ready(item) for item in value]
    return value


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(ready(value), stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        parent = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def exclusive_run(directory: Path):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    with (directory / "run.lock").open("a+") as stream:
        os.chmod(directory / "run.lock", 0o600)
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CollectionPaused("another_runner_holds_checkpoint") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def producer_identity() -> dict[str, str]:
    root = Path(__file__).parent
    # Include the transport, normalizers, overlays and this runner itself. A
    # resume must never mix inputs or context captured by different code.
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*.py"))}


class QuotaWindow:
    """Reserve billable units BEFORE each read, including failed/uncertain reads.

    The ledger survives retries and process restarts. A new quota window is an
    explicit operator input, not an automatic reset at resume or midnight.
    """
    def __init__(self, directory: Path, *, window: str, limits: Mapping[str, int],
                 rate_card: Mapping[str, Mapping[str, Any]]) -> None:
        if not window or not limits or not rate_card:
            raise ValueError("an explicit quota window, limits and rate card are required")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in limits.values()):
            raise ValueError("quota limits must be non-negative integer units")
        self.directory, self.limits, self.rate_card = directory, dict(limits), dict(rate_card)
        self.window, self.lock, self.blocked_reason = window, threading.RLock(), None
        self.path = directory / ("quota-" + hashlib.sha256(window.encode()).hexdigest() + ".json")
        expected = digest({"window": window, "limits": self.limits, "rate_card": self.rate_card})
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            if self.state["policy_sha256"] != expected:
                raise ValueError("quota window policy changed; do not silently reset or enlarge its budget")
        else:
            self.state = {"window": window, "policy_sha256": expected,
                          "policy": {"window": window, "limits": self.limits, "rate_card": self.rate_card},
                          "used": {key: 0 for key in limits}, "reservations": 0,
                          "http_observations": telemetry.http_observation(complete_history=True)}
            atomic_json(self.path, self.state)
        self.blocked_reason = self.state.get("hold_reason")

    def reserve(self, provider: str, units: object) -> None:
        # A JSON rate card is untrusted input. The existing guards below narrow
        # it to an integer before any budget arithmetic or state mutation.
        with self.lock:
            if self.blocked_reason:
                raise CollectionPaused(self.blocked_reason)
            if (provider not in self.limits or isinstance(units, bool) or not isinstance(units, int) or units <= 0):
                self.blocked_reason = "provider_rate_card_missing"
                raise CollectionPaused(self.blocked_reason)
            if self.state["used"][provider] + units > self.limits[provider]:
                self.blocked_reason = "provider_quota_window_exhausted"
                raise CollectionPaused(self.blocked_reason)
            self.state["used"][provider] += units
            self.state["reservations"] += 1
            atomic_json(self.path, self.state)

    def stop(self, reason: str) -> None:
        with self.lock:
            self.blocked_reason = reason
            self.state["hold_reason"] = reason
            atomic_json(self.path, self.state)

    def check(self) -> None:
        if self.blocked_reason:
            raise CollectionPaused(self.blocked_reason)

    def http_started(self, provider):
        with self.lock:
            telemetry.http_started(self.state, provider)
            atomic_json(self.path, self.state)

    def http_finished(self, provider, *, status, size, seconds):
        with self.lock:
            telemetry.http_finished(self.state, provider, status=status, size=size, seconds=seconds)
            atomic_json(self.path, self.state)


class CanonicalAdapter(Protocol):
    @property
    def identity(self) -> Mapping[str, Any]: ...

    def collect(self, listing: Listing, quota: QuotaWindow) -> Mapping[str, Any]: ...

    def prepare_context(self, inputs: Mapping[str, Mapping[str, Any]], quota: QuotaWindow) -> Mapping[str, Any]: ...

    def value(self, inputs: Mapping[str, Mapping[str, Any]], context: Mapping[str, Any], quota: QuotaWindow) -> Mapping[str, Mapping[str, Any]]: ...


def _artifact(path: Path, *, identity: str, symbol: str, payload: Any | None = None) -> Any:
    if payload is not None:
        body = {"identity": identity, "symbol": symbol, "payload": ready(payload)}
        atomic_json(path, {**body, "sha256": digest(body)})
    stored = json.loads(path.read_text())
    core = {key: value for key, value in stored.items() if key != "sha256"}
    if (stored.get("identity") != identity or stored.get("symbol") != symbol or digest(core) != stored.get("sha256")):
        raise ValueError("checkpoint artifact identity/digest mismatch")
    return stored["payload"]


class InputFiles(Mapping[str, Mapping[str, Any]]):
    """Load one symbol at a time; do not retain every full price history in RAM."""
    def __init__(self, directory: Path, identity: str, files: Mapping[str, str]):
        self.directory, self.identity, self.files = directory, identity, dict(files)

    def __iter__(self):
        return iter(self.files)

    def __len__(self):
        return len(self.files)

    def __getitem__(self, symbol):
        return _artifact(self.directory / self.files[symbol], identity=self.identity, symbol=symbol)


def produce_catalogue(catalogue: Catalogue, directory: Path, adapter: CanonicalAdapter, *,
                      window: str, limits: Mapping[str, int], rate_card: Mapping[str, Mapping[str, Any]],
                      act: bool = False, batch_size: int = 25, max_attempts: int = 2,
                      max_batches: int | None = None) -> dict[str, Any]:
    if not 1 <= batch_size <= 100 or not 1 <= max_attempts <= 5:
        raise ValueError("batch size1..100 and attempts1..5 are required")
    if max_batches is not None and (isinstance(max_batches, bool) or not isinstance(max_batches, int) or max_batches < 1):
        raise ValueError("max_batches must be a positive integer")
    identity = digest({"catalogue": catalogue.payload()["manifest_sha256"],
                       "producer_files": producer_identity(), "adapter": ready(adapter.identity)})
    listings = [item for item in catalogue.listings if item.security_type != "ETF"]
    validate_catalogue = getattr(adapter, "validate_catalogue", None)
    if validate_catalogue is not None:
        validate_catalogue(listings)
    if not act:
        return {"schema": RUN_SCHEMA, "action": "plan", "identity": identity,
                "inventory_count": len(listings), "quota_window": window,
                "network_calls": 0, "checkpoint_written": False, "generation_activated": False}
    with exclusive_run(directory):
        state_path = directory / "checkpoint.json"
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state["identity"] != identity or state["max_attempts"] != max_attempts:
                raise ValueError("catalogue/producer/context policy changed; do not resume another run")
        else:
            if any(path.name != "run.lock" for path in directory.iterdir()):
                raise ValueError("checkpoint missing with existing artifacts; do not reset a measured run or quota")
            state = {"schema": RUN_SCHEMA, "run_id": str(uuid4()), "identity": identity,
                     "market": catalogue.market, "catalogue_manifest_sha256": catalogue.payload()["manifest_sha256"],
                     "producer_files": producer_identity(), "adapter_identity": ready(adapter.identity), "max_attempts": max_attempts,
                     "observations": telemetry.observation(complete_history=True),
                     "status": "collecting", "items": {item.symbol: {"status": "pending", "attempts": 0} for item in listings}}
            atomic_json(state_path, state)
        if set(state["items"]) != {item.symbol for item in listings}:
            raise ValueError("checkpoint inventory no longer reconciles")
        quota = QuotaWindow(directory, window=window, limits=limits, rate_card=rate_card)
        invocation_started = telemetry.begin_invocation(state, state_path, atomic_json)
        processed = 0
        item = None
        try:
            for listing in listings:
                item = state["items"][listing.symbol]
                name = hashlib.sha256(listing.symbol.encode()).hexdigest() + ".json"
                input_path = directory / "inputs" / name
                if item["status"] == "inputs_ready":
                    _artifact(directory / item["input_file"], identity=identity, symbol=listing.symbol)
                    state["observations"]["cached_input_reads"] += 1
                    continue
                if item["status"] == "valued":
                    _artifact(directory / item["row_file"], identity=identity, symbol=listing.symbol)
                    state["observations"]["cached_row_reads"] += 1
                    continue
                if item["status"] == "not_evaluable":
                    continue
                if listing.listing_class != "equity":
                    item.update(status="not_evaluable", reason="listing_classification_pending")
                elif input_path.exists():
                    _artifact(input_path, identity=identity, symbol=listing.symbol)
                    state["observations"]["cached_input_reads"] += 1
                    item.update(status="inputs_ready", input_file=str(input_path.relative_to(directory)))
                else:
                    while item["attempts"] < max_attempts:
                        item["attempts"] += 1
                        item["status"] = "fetching"
                        atomic_json(state_path, state)
                        try:
                            with telemetry.phase(state, state_path, atomic_json, "collect"):
                                payload = adapter.collect(listing, quota)
                            quota.check()  # protected clients may catch a quota exception; never call it missing data
                            _artifact(input_path, identity=identity, symbol=listing.symbol, payload=payload)
                            item.update(status="inputs_ready", input_file=str(input_path.relative_to(directory)))
                            break
                        except UnavailableInput as exc:
                            quota.check()
                            reason = str(exc)
                            if not reason or not all(character.islower() or character.isdigit() or character == "_" for character in reason):
                                reason = "required_input_unavailable"
                            item.update(status="not_evaluable", reason=reason)
                            break
                        except TransientInputFailure:
                            state["observations"]["input_transient_failures"] += 1
                            quota.check()
                            if item["attempts"] >= max_attempts:
                                item.update(status="not_evaluable", reason="provider_failure_after_bounded_retries")
                    if item["status"] == "fetching":
                        item.update(status="not_evaluable", reason="provider_failure_after_bounded_retries")
                processed += 1
                atomic_json(state_path, state)
                if max_batches is not None and processed >= max_batches * batch_size:
                    state["pause_reason"] = "requested_batch_boundary"
                    break
            pending = [symbol for symbol, value in state["items"].items() if value["status"] in {"pending", "fetching"}]
            if not pending and state["status"] != "complete":
                inputs = InputFiles(directory, identity, {symbol: value["input_file"]
                                                         for symbol, value in state["items"].items()
                                                         if value["status"] == "inputs_ready"})
                context_path = directory / "context.json"
                if context_path.exists():
                    context = _artifact(context_path, identity=identity, symbol="CONTEXT")
                else:
                    with telemetry.phase(state, state_path, atomic_json, "context"):
                        context = adapter.prepare_context(inputs, quota)
                    quota.check()
                    _artifact(context_path, identity=identity, symbol="CONTEXT", payload=context)
                with telemetry.phase(state, state_path, atomic_json, "value"):
                    rows = dict(adapter.value(inputs, context, quota))
                quota.check()
                if set(rows) - set(inputs):
                    raise ValueError("canonical adapter returned a foreign listing")
                for symbol, item in state["items"].items():
                    if item["status"] != "inputs_ready":
                        continue
                    row = rows.get(symbol)
                    if row is None:
                        item.update(status="not_evaluable", reason="canonical_inputs_or_quality_insufficient")
                    elif str(row.get("symbol") or "") != symbol:
                        raise ValueError("canonical row changed official listing identity")
                    else:
                        output_path = directory / "rows" / (hashlib.sha256(symbol.encode()).hexdigest() + ".json")
                        _artifact(output_path, identity=identity, symbol=symbol, payload=row)
                        item.update(status="valued", row_file=str(output_path.relative_to(directory)))
                state.update(status="complete", completed_at=datetime.now(timezone.utc).isoformat(), context_sha256=digest(ready(context)))
                state.pop("pause_reason", None)
        except CollectionPaused as exc:
            if item is not None and item["status"] == "fetching":
                item.update(status="pending", attempts=max(0, item["attempts"] - 1))
            state["pause_reason"] = str(exc)
        telemetry.finish_invocation(state, state_path, atomic_json, invocation_started)
        return {"schema": RUN_SCHEMA, "run_id": state["run_id"], "identity": identity,
                "status": state["status"], "complete": state["status"] == "complete",
                "inventory_count": len(state["items"]),
                "valued_count": sum(item["status"] == "valued" for item in state["items"].values()),
                "not_evaluable_count": sum(item["status"] == "not_evaluable" for item in state["items"].values()),
                "remaining": sum(item["status"] in {"pending", "fetching", "inputs_ready"} for item in state["items"].values()),
                "pause_reason": state.get("pause_reason"), "quota": quota.state,
                "observations": state["observations"],
                "generation_activated": False, "checkpoint_written": True}


def stage_predictions(database: Any, directory: Path, *, act: bool = False) -> dict[str, Any]:
    """Append genuine canonical prediction records to an UNSELECTABLE stage.

    Never save a valuation_universe snapshot: that namespace activates a
    generation automatically. Staged records refer to a real snapshot FK but
    remain invisible to current_generation/selectable_cycles and all served TPs.
    """
    from .valuation_official import OFFICIAL_SOURCES, prediction_from_row, current_generation
    from .valuation_policy import METHODOLOGY_VERSION

    with exclusive_run(directory):
        state = json.loads((directory / "checkpoint.json").read_text())
        if state["status"] != "complete":
            raise ValueError("incomplete inventory cannot be staged")
        if state["producer_files"] != producer_identity():
            raise ValueError("canonical producer files changed after the run")
        rows, unavailable = [], {}
        for symbol, item in state["items"].items():
            if item["status"] == "valued":
                rows.append(_artifact(directory / item["row_file"], identity=state["identity"], symbol=symbol))
            elif item["status"] == "not_evaluable":
                unavailable[symbol] = item["reason"]
            else:
                raise ValueError("complete checkpoint contains an unresolved listing")
        if len(rows) + len(unavailable) != len(state["items"]):
            raise ValueError("stage inventory does not reconcile")
        if not act:
            return {"action": "stage_plan", "valued": len(rows), "not_evaluable": len(unavailable),
                    "written": False, "generation_activated": False}
        stage_started = telemetry.begin_stage(state, directory / "checkpoint.json", atomic_json)
        predicted = utc(state["completed_at"])
        method = database.ensure_methodology_version("full_universe_stage", 1,
                                                    {"canonical_methodology_version": METHODOLOGY_VERSION},
                                                    "Canonical full-inventory staging; no serving promotion")
        if not state.get("stage_snapshot_id"):
            state["stage_snapshot_id"] = str(uuid4())
            atomic_json(directory / "checkpoint.json", state)
        stage_id = state["stage_snapshot_id"]
        existing = database.analysis_snapshot_by_id(stage_id)
        if existing and (existing.get("analysis_type") != STAGE_ANALYSIS
                         or existing.get("inputs", {}).get("run_identity") != state["identity"]):
            raise ValueError("reserved stage snapshot has a different identity")
        if not existing:
            # Reserving the ID is idempotent; reserving a publication time is
            # not. After an insert failure, the first actual publication must
            # use the new attempt's clock, not a backdated checkpoint clock.
            published = max(predicted, datetime.now(timezone.utc))
            database.save_analysis_snapshot(
                STAGE_ANALYSIS, state["market"], method,
                {"canonical_methodology_version": METHODOLOGY_VERSION, "run_identity": state["identity"],
                 "source_manifest_sha256": state["catalogue_manifest_sha256"]},
                {"rows": rows, "not_evaluable": unavailable, "inventory_count": len(state["items"]),
                 "context_sha256": state["context_sha256"]}, published, snapshot_id=stage_id,
            )
        else:
            published = utc(existing["published_at"])
        state["stage_published_at"] = published.isoformat()
        atomic_json(directory / "checkpoint.json", state)
        records = []
        for row in rows:
            for source in OFFICIAL_SOURCES:
                record = prediction_from_row(
                    row, market=state["market"], scope="universe", cycle_id=stage_id,
                    source_version=str(METHODOLOGY_VERSION), prediction_instant=predicted,
                    published_at=published, source_manifest_sha256=state["catalogue_manifest_sha256"], source=source,
                    extra_provenance={"full_universe_stage": True, "run_identity": state["identity"],
                                      "context_sha256": state["context_sha256"]},
                )
                if record is not None:
                    records.append(record)
        recorded = int(database.insert_valuation_predictions(records)) if records else 0
        telemetry.finish_stage(state, directory / "checkpoint.json", atomic_json, stage_started, len(records), recorded)
        return {"stage_snapshot_id": stage_id, "valued": len(rows), "not_evaluable": len(unavailable),
                "records_considered": len(records), "records_inserted": recorded,
                "written": True, "generation_activated": False,
                "current_generation_id": (current_generation(database) or {}).get("generation_id")}
