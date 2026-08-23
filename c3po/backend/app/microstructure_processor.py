from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
from queue import Full, Queue
import shutil
from threading import Lock, Thread
import time
from typing import Any, Callable
from uuid import uuid4
from zoneinfo import ZoneInfo


logger = logging.getLogger(__name__)
NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class ProcessorStats:
    accepted: int
    processed: int
    malformed: int
    ignored: int
    late: int
    dropped: int
    disk_guard_dropped: int
    aggregates_written: int
    write_errors: int
    queue_depth: int
    queue_capacity: int
    queue_high_water: int
    last_event_at: datetime | None


@dataclass(frozen=True)
class _Bbo:
    bid: float
    ask: float
    as_of: datetime


@dataclass
class _Aggregate:
    symbol: str
    bucket_at: datetime
    interval_seconds: int
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    trade_count: int = 0
    quote_count: int = 0
    total_volume: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    unknown_volume: float = 0.0
    buy_trades: int = 0
    sell_trades: int = 0
    unknown_trades: int = 0
    bbo_classified_trades: int = 0
    tick_rule_trades: int = 0
    inherited_tick_trades: int = 0
    classification_method_counts: dict[str, int] = field(default_factory=lambda: {
        "bbo_midpoint": 0,
        "tick_rule_at_mid": 0,
        "tick_rule_no_bbo": 0,
        "inherited_tick": 0,
        "unknown": 0,
    })
    classification_method_volumes: dict[str, float] = field(default_factory=lambda: {
        "bbo_midpoint": 0.0,
        "tick_rule_at_mid": 0.0,
        "tick_rule_no_bbo": 0.0,
        "inherited_tick": 0.0,
        "unknown": 0.0,
    })
    classification_confidence_sum: float = 0.0
    max_trade_volume: float = 0.0
    sum_squared_trade_volume: float = 0.0
    interarrival_ms_sum: float = 0.0
    interarrival_count: int = 0
    min_interarrival_ms: float | None = None
    max_interarrival_ms: float | None = None
    bbo_age_ms_sum: float = 0.0
    bbo_age_count: int = 0
    max_bbo_age_ms: float | None = None
    bbo_age_ms_samples: list[float] = field(default_factory=list)
    receive_lag_ms_sum: float = 0.0
    receive_lag_count: int = 0
    max_receive_lag_ms: float | None = None
    last_bid: float | None = None
    last_ask: float | None = None
    last_spread_bps: float | None = None
    spread_bps_sum: float = 0.0
    spread_bps_count: int = 0
    min_spread_bps: float | None = None
    max_spread_bps: float | None = None
    late_event_count: int = 0
    dropped_event_count: int = 0
    discarded_event_count: int = 0
    cumulative_volume_delta: float = 0.0
    first_event_at: datetime | None = None
    last_event_at: datetime | None = None


class MicrostructureProcessor:
    """Join trades to prior fresh BBOs and persist auditable short aggregates.

    This is a passive research sink. It never feeds the R2D2 decision path.
    Classification order is BBO midpoint, tick rule, inherited tick, unknown.
    A quote newer than a trade is never used, and stale BBOs are ignored.
    """

    _STOP = object()

    def __init__(
        self,
        root: Path,
        *,
        bbo_max_age_seconds: float = 2.0,
        intervals_seconds: tuple[int, ...] = (1, 5),
        allowed_lateness_seconds: float = 2.0,
        queue_size: int = 100_000,
        rotate_bytes: int = 256 * 1024 * 1024,
        flush_every: int = 1_000,
        minimum_free_bytes: int = 20 * 1024**3,
        disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
        disk_check_interval_seconds: float = 1.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.root = Path(root)
        self.bbo_max_age = timedelta(seconds=max(0.0, bbo_max_age_seconds))
        self.intervals = tuple(sorted({max(1, int(value)) for value in intervals_seconds}))
        self.allowed_lateness = timedelta(seconds=max(0.0, allowed_lateness_seconds))
        self.rotate_bytes = max(1_024, int(rotate_bytes))
        self.flush_every = max(1, int(flush_every))
        self.minimum_free_bytes = max(0, int(minimum_free_bytes))
        self._disk_usage = disk_usage
        self._disk_check_interval_seconds = max(
            0.1, float(disk_check_interval_seconds)
        )
        self._monotonic = monotonic
        self._cached_free_bytes: int | None = None
        self._last_disk_check: float | None = None
        self.run_id = str(uuid4())
        self._queue_capacity = max(1, int(queue_size))
        self._queue: Queue[object] = Queue(maxsize=self._queue_capacity)
        self._thread: Thread | None = None
        self._stats_lock = Lock()
        self._pending_quality_lock = Lock()
        self._pending_drops: dict[tuple[str, int, datetime], int] = {}
        self._accepted = 0
        self._processed = 0
        self._malformed = 0
        self._ignored = 0
        self._late = 0
        self._dropped = 0
        self._disk_guard_dropped = 0
        self._aggregates_written = 0
        self._write_errors = 0
        self._queue_high_water = 0
        self._last_event_at: datetime | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.root.mkdir(parents=True, exist_ok=True)
        if not self._disk_available():
            raise RuntimeError(
                "microstructure aggregate disk reserve is unavailable at startup"
            )
        self._thread = Thread(target=self._run, name="eodhd-microstructure", daemon=True)
        self._thread.start()

    def record(self, feed: str, payload: str, *, received_at: datetime) -> bool:
        observed = (
            received_at.astimezone(timezone.utc)
            if received_at.tzinfo
            else received_at.replace(tzinfo=timezone.utc)
        )
        try:
            self._queue.put_nowait((str(feed), str(payload), observed))
        except Full:
            with self._stats_lock:
                self._dropped += 1
                dropped = self._dropped
            self._record_pending_drop(str(payload), observed)
            if dropped == 1 or dropped % 10_000 == 0:
                logger.error("Microstructure processor queue full; dropped=%d", dropped)
            return False
        with self._stats_lock:
            self._accepted += 1
            self._queue_high_water = max(self._queue_high_water, self._queue.qsize())
        return True

    def stop(self) -> None:
        if not self._thread:
            return
        self._queue.put(self._STOP)
        self._thread.join(timeout=15)
        if self._thread.is_alive():
            logger.error("Microstructure processor did not stop within timeout")
        self._thread = None

    def stats(self) -> ProcessorStats:
        with self._stats_lock:
            return ProcessorStats(
                accepted=self._accepted,
                processed=self._processed,
                malformed=self._malformed,
                ignored=self._ignored,
                late=self._late,
                dropped=self._dropped,
                disk_guard_dropped=self._disk_guard_dropped,
                aggregates_written=self._aggregates_written,
                write_errors=self._write_errors,
                queue_depth=self._queue.qsize(),
                queue_capacity=self._queue_capacity,
                queue_high_water=self._queue_high_water,
                last_event_at=self._last_event_at,
            )

    def _run(self) -> None:
        bbo: dict[str, _Bbo] = {}
        last_trade: dict[str, tuple[float, str | None, datetime]] = {}
        cumulative_delta: dict[str, float] = {}
        aggregates: dict[tuple[str, int, datetime], _Aggregate] = {}
        handles: dict[tuple[str, int], tuple[int, Any, int]] = {}
        max_event_at: datetime | None = None
        writes_since_flush = 0
        try:
            while True:
                queued = self._queue.get()
                if queued is self._STOP:
                    break
                feed, payload, received_at = queued  # type: ignore[misc]
                try:
                    self._drain_pending_drops(aggregates)
                    item = json.loads(payload)
                    if not isinstance(item, dict):
                        raise ValueError("payload is not an object")
                    event_at = self._event_time(item)
                    symbol = str(item.get("s") or "").strip().upper()
                    if not symbol or event_at is None:
                        raise ValueError("missing symbol or event timestamp")
                    watermark = max_event_at - self.allowed_lateness if max_event_at else None
                    if watermark and event_at <= watermark:
                        with self._stats_lock:
                            self._late += 1
                        self._mark_quality(
                            symbol, received_at, aggregates, field_name="late_event_count"
                        )
                        continue
                    max_event_at = max(max_event_at, event_at) if max_event_at else event_at
                    if feed == "quote":
                        self._process_quote(item, symbol, event_at, received_at, bbo, aggregates)
                    elif feed == "trade":
                        if item.get("dp") is True:
                            with self._stats_lock:
                                self._ignored += 1
                            self._mark_quality(
                                symbol,
                                received_at,
                                aggregates,
                                field_name="discarded_event_count",
                            )
                            continue
                        self._process_trade(
                            item, symbol, event_at, received_at, bbo, last_trade,
                            cumulative_delta, aggregates,
                        )
                    else:
                        raise ValueError(f"unsupported feed {feed}")
                    with self._stats_lock:
                        self._processed += 1
                        self._last_event_at = event_at
                    cutoff = max_event_at - self.allowed_lateness
                    writes_since_flush += self._flush_ready(aggregates, handles, cutoff)
                    if writes_since_flush >= self.flush_every:
                        self._flush_handles(handles)
                        writes_since_flush = 0
                except (TypeError, ValueError, json.JSONDecodeError, OSError):
                    with self._stats_lock:
                        self._malformed += 1
                    logger.debug("Ignored malformed microstructure %s payload", feed, exc_info=True)
                except Exception:
                    logger.exception("Unhandled microstructure processing error")
                    with self._stats_lock:
                        self._malformed += 1
            self._drain_pending_drops(aggregates)
            for key in sorted(aggregates, key=lambda value: (value[2], value[0], value[1])):
                self._write_aggregate(aggregates[key], handles)
        finally:
            self._flush_handles(handles)
            for _, handle, _ in handles.values():
                try:
                    handle.close()
                except Exception:
                    logger.exception("Failed to close microstructure aggregate file")

    def _process_quote(
        self,
        item: dict[str, Any],
        symbol: str,
        event_at: datetime,
        received_at: datetime,
        bbo: dict[str, _Bbo],
        aggregates: dict[tuple[str, int, datetime], _Aggregate],
    ) -> None:
        bid = self._positive_float(item.get("bp"))
        ask = self._positive_float(item.get("ap"))
        if bid is None or ask is None or ask < bid:
            raise ValueError("invalid two-sided quote")
        current = bbo.get(symbol)
        if current is None or event_at >= current.as_of:
            bbo[symbol] = _Bbo(bid=bid, ask=ask, as_of=event_at)
        midpoint = (bid + ask) / 2
        spread_bps = (ask - bid) / midpoint * 10_000 if midpoint > 0 else None
        for aggregate in self._aggregates_for(symbol, event_at, aggregates):
            aggregate.quote_count += 1
            aggregate.last_bid = bid
            aggregate.last_ask = ask
            aggregate.last_spread_bps = spread_bps
            if spread_bps is not None:
                aggregate.spread_bps_sum += spread_bps
                aggregate.spread_bps_count += 1
                aggregate.min_spread_bps = (
                    spread_bps
                    if aggregate.min_spread_bps is None
                    else min(aggregate.min_spread_bps, spread_bps)
                )
                aggregate.max_spread_bps = (
                    spread_bps
                    if aggregate.max_spread_bps is None
                    else max(aggregate.max_spread_bps, spread_bps)
                )
            self._touch(aggregate, event_at, received_at)

    def _process_trade(
        self,
        item: dict[str, Any],
        symbol: str,
        event_at: datetime,
        received_at: datetime,
        bbo: dict[str, _Bbo],
        last_trade: dict[str, tuple[float, str | None, datetime]],
        cumulative_delta: dict[str, float],
        aggregates: dict[tuple[str, int, datetime], _Aggregate],
    ) -> None:
        price = self._positive_float(item.get("p"))
        if price is None:
            raise ValueError("invalid trade price")
        volume = self._positive_float(item.get("v"))
        if volume is None:
            raise ValueError("invalid trade volume")
        side, method, confidence, bbo_age_ms = self._classify(
            price, event_at, bbo.get(symbol), last_trade.get(symbol),
        )
        previous = last_trade.get(symbol)
        interarrival_ms = None
        if previous and event_at >= previous[2]:
            interarrival_ms = (event_at - previous[2]).total_seconds() * 1_000
        last_trade[symbol] = (price, side if side != "unknown" else previous[1] if previous else None, event_at)
        signed_volume = volume if side == "buy" else -volume if side == "sell" else 0.0
        cumulative_delta[symbol] = cumulative_delta.get(symbol, 0.0) + signed_volume

        for aggregate in self._aggregates_for(symbol, event_at, aggregates):
            aggregate.open = price if aggregate.open is None else aggregate.open
            aggregate.high = price if aggregate.high is None else max(aggregate.high, price)
            aggregate.low = price if aggregate.low is None else min(aggregate.low, price)
            aggregate.close = price
            aggregate.trade_count += 1
            aggregate.total_volume += volume
            aggregate.max_trade_volume = max(aggregate.max_trade_volume, volume)
            aggregate.sum_squared_trade_volume += volume * volume
            aggregate.classification_confidence_sum += confidence
            aggregate.classification_method_counts[method] += 1
            aggregate.classification_method_volumes[method] += volume
            if side == "buy":
                aggregate.buy_trades += 1
                aggregate.buy_volume += volume
            elif side == "sell":
                aggregate.sell_trades += 1
                aggregate.sell_volume += volume
            else:
                aggregate.unknown_trades += 1
                aggregate.unknown_volume += volume
            if method == "bbo_midpoint":
                aggregate.bbo_classified_trades += 1
            elif method in {"tick_rule_at_mid", "tick_rule_no_bbo"}:
                aggregate.tick_rule_trades += 1
            elif method == "inherited_tick":
                aggregate.inherited_tick_trades += 1
            if bbo_age_ms is not None:
                aggregate.bbo_age_ms_sum += bbo_age_ms
                aggregate.bbo_age_count += 1
                aggregate.max_bbo_age_ms = (
                    bbo_age_ms
                    if aggregate.max_bbo_age_ms is None
                    else max(aggregate.max_bbo_age_ms, bbo_age_ms)
                )
                aggregate.bbo_age_ms_samples.append(bbo_age_ms)
            if interarrival_ms is not None:
                aggregate.interarrival_ms_sum += interarrival_ms
                aggregate.interarrival_count += 1
                aggregate.min_interarrival_ms = (
                    interarrival_ms
                    if aggregate.min_interarrival_ms is None
                    else min(aggregate.min_interarrival_ms, interarrival_ms)
                )
                aggregate.max_interarrival_ms = (
                    interarrival_ms
                    if aggregate.max_interarrival_ms is None
                    else max(aggregate.max_interarrival_ms, interarrival_ms)
                )
            aggregate.cumulative_volume_delta = cumulative_delta[symbol]
            self._touch(aggregate, event_at, received_at)

    def _classify(
        self,
        price: float,
        event_at: datetime,
        bbo: _Bbo | None,
        previous: tuple[float, str | None, datetime] | None,
    ) -> tuple[str, str, float, float | None]:
        has_fresh_bbo = bool(
            bbo and timedelta(0) <= event_at - bbo.as_of <= self.bbo_max_age
        )
        bbo_age_ms = (
            (event_at - bbo.as_of).total_seconds() * 1_000
            if has_fresh_bbo and bbo is not None
            else None
        )
        if has_fresh_bbo and bbo is not None:
            midpoint = (bbo.bid + bbo.ask) / 2
            if price > midpoint:
                confidence = 1.0 if price >= bbo.ask else 0.8
                return "buy", "bbo_midpoint", confidence, bbo_age_ms
            if price < midpoint:
                confidence = 1.0 if price <= bbo.bid else 0.8
                return "sell", "bbo_midpoint", confidence, bbo_age_ms
        if previous:
            if price > previous[0]:
                method = "tick_rule_at_mid" if has_fresh_bbo else "tick_rule_no_bbo"
                return "buy", method, 0.6, bbo_age_ms
            if price < previous[0]:
                method = "tick_rule_at_mid" if has_fresh_bbo else "tick_rule_no_bbo"
                return "sell", method, 0.6, bbo_age_ms
            if previous[1] in {"buy", "sell"}:
                return str(previous[1]), "inherited_tick", 0.4, bbo_age_ms
        return "unknown", "unknown", 0.0, None

    def _aggregates_for(
        self,
        symbol: str,
        event_at: datetime,
        aggregates: dict[tuple[str, int, datetime], _Aggregate],
    ) -> list[_Aggregate]:
        output: list[_Aggregate] = []
        epoch = int(event_at.timestamp())
        for interval in self.intervals:
            bucket_epoch = epoch - epoch % interval
            bucket_at = datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)
            key = (symbol, interval, bucket_at)
            aggregate = aggregates.get(key)
            if aggregate is None:
                aggregate = _Aggregate(symbol=symbol, bucket_at=bucket_at, interval_seconds=interval)
                aggregates[key] = aggregate
            output.append(aggregate)
        return output

    def _flush_ready(
        self,
        aggregates: dict[tuple[str, int, datetime], _Aggregate],
        handles: dict[tuple[str, int], tuple[int, Any, int]],
        cutoff: datetime,
    ) -> int:
        ready = [
            key for key, value in aggregates.items()
            if value.bucket_at + timedelta(seconds=value.interval_seconds) <= cutoff
        ]
        for key in sorted(ready, key=lambda value: (value[2], value[0], value[1])):
            self._write_aggregate(aggregates.pop(key), handles)
        return len(ready)

    def _write_aggregate(
        self,
        aggregate: _Aggregate,
        handles: dict[tuple[str, int], tuple[int, Any, int]],
    ) -> None:
        row = asdict(aggregate)
        bbo_age_samples = row.pop("bbo_age_ms_samples")
        for key in ("bucket_at", "first_event_at", "last_event_at"):
            value = row[key]
            row[key] = value.isoformat() if value else None
        row["schema_version"] = 1
        row["provider"] = "EODHD"
        row["processor_run_id"] = self.run_id
        row["volume_delta"] = aggregate.buy_volume - aggregate.sell_volume
        row["classification_coverage"] = (
            (aggregate.trade_count - aggregate.unknown_trades) / aggregate.trade_count
            if aggregate.trade_count else 0.0
        )
        row["mean_classification_confidence"] = (
            aggregate.classification_confidence_sum / aggregate.trade_count
            if aggregate.trade_count else 0.0
        )
        row["mean_trade_volume"] = (
            aggregate.total_volume / aggregate.trade_count if aggregate.trade_count else 0.0
        )
        row["mean_interarrival_ms"] = (
            aggregate.interarrival_ms_sum / aggregate.interarrival_count
            if aggregate.interarrival_count else None
        )
        row["mean_bbo_age_ms"] = (
            aggregate.bbo_age_ms_sum / aggregate.bbo_age_count
            if aggregate.bbo_age_count else None
        )
        row["p50_bbo_age_ms"] = self._percentile(bbo_age_samples, 0.50)
        row["p95_bbo_age_ms"] = self._percentile(bbo_age_samples, 0.95)
        row["mean_spread_bps"] = (
            aggregate.spread_bps_sum / aggregate.spread_bps_count
            if aggregate.spread_bps_count else None
        )
        row["mean_receive_lag_ms"] = (
            aggregate.receive_lag_ms_sum / aggregate.receive_lag_count
            if aggregate.receive_lag_count else None
        )
        record = json.dumps(row, separators=(",", ":"), ensure_ascii=True) + "\n"
        encoded_size = len(record.encode("utf-8"))
        if not self._disk_available(encoded_size):
            with self._stats_lock:
                self._disk_guard_dropped += 1
                dropped = self._disk_guard_dropped
            if dropped == 1 or dropped % 10_000 == 0:
                logger.error(
                    "Microstructure aggregate disk reserve active; dropped=%d",
                    dropped,
                )
            return
        session = aggregate.bucket_at.astimezone(NEW_YORK).date().isoformat()
        key = (session, aggregate.interval_seconds)
        part, handle, size = handles.get(key, (0, None, 0))
        try:
            if handle is None or size + encoded_size > self.rotate_bytes:
                if handle is not None:
                    handle.flush()
                    handle.close()
                part += 1
                directory = self.root / f"session_date={session}" / f"interval={aggregate.interval_seconds}s"
                directory.mkdir(parents=True, exist_ok=True)
                path = directory / f"part-{part:05d}.ndjson"
                handle = path.open("a", encoding="utf-8")
                size = path.stat().st_size
            handle.write(record)
            self._consume_disk_bytes(encoded_size)
            handles[key] = (part, handle, size + encoded_size)
            with self._stats_lock:
                self._aggregates_written += 1
        except Exception:
            with self._stats_lock:
                self._write_errors += 1
            logger.exception("Failed to append microstructure aggregate")

    def _record_pending_drop(self, payload: str, received_at: datetime) -> None:
        try:
            item = json.loads(payload)
            symbol = str(item.get("s") or "").strip().upper()
        except (AttributeError, TypeError, json.JSONDecodeError):
            return
        if not symbol:
            return
        with self._pending_quality_lock:
            for interval in self.intervals:
                bucket = self._bucket_at(received_at, interval)
                key = (symbol, interval, bucket)
                self._pending_drops[key] = self._pending_drops.get(key, 0) + 1

    def _drain_pending_drops(
        self,
        aggregates: dict[tuple[str, int, datetime], _Aggregate],
    ) -> None:
        with self._pending_quality_lock:
            pending = self._pending_drops
            self._pending_drops = {}
        for key, count in pending.items():
            aggregate = aggregates.get(key)
            if aggregate is None:
                aggregate = _Aggregate(
                    symbol=key[0], interval_seconds=key[1], bucket_at=key[2]
                )
                aggregates[key] = aggregate
            aggregate.dropped_event_count += count

    def _mark_quality(
        self,
        symbol: str,
        received_at: datetime,
        aggregates: dict[tuple[str, int, datetime], _Aggregate],
        *,
        field_name: str,
    ) -> None:
        for interval in self.intervals:
            key = (symbol, interval, self._bucket_at(received_at, interval))
            aggregate = aggregates.get(key)
            if aggregate is None:
                aggregate = _Aggregate(
                    symbol=symbol, interval_seconds=interval, bucket_at=key[2]
                )
                aggregates[key] = aggregate
            setattr(aggregate, field_name, getattr(aggregate, field_name) + 1)

    @staticmethod
    def _bucket_at(value: datetime, interval: int) -> datetime:
        epoch = int(value.timestamp())
        return datetime.fromtimestamp(epoch - epoch % interval, tz=timezone.utc)

    def _disk_available(self, required_bytes: int = 0) -> bool:
        checked_at = self._monotonic()
        if (
            self._cached_free_bytes is None
            or self._last_disk_check is None
            or checked_at - self._last_disk_check >= self._disk_check_interval_seconds
        ):
            try:
                self._cached_free_bytes = int(self._disk_usage(self.root).free)
                self._last_disk_check = checked_at
            except OSError:
                logger.exception("Unable to inspect microstructure aggregate disk")
                return False
        return (
            self._cached_free_bytes - max(0, int(required_bytes))
            >= self.minimum_free_bytes
        )

    def _consume_disk_bytes(self, written_bytes: int) -> None:
        if self._cached_free_bytes is not None:
            self._cached_free_bytes = max(
                0, self._cached_free_bytes - max(0, int(written_bytes))
            )

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(float(value) for value in values)
        position = (len(ordered) - 1) * percentile
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = position - lower
        return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction

    @staticmethod
    def _flush_handles(handles: dict[tuple[str, int], tuple[int, Any, int]]) -> None:
        for _, handle, _ in handles.values():
            handle.flush()

    @staticmethod
    def _touch(aggregate: _Aggregate, event_at: datetime, received_at: datetime) -> None:
        aggregate.first_event_at = min(aggregate.first_event_at, event_at) if aggregate.first_event_at else event_at
        aggregate.last_event_at = max(aggregate.last_event_at, event_at) if aggregate.last_event_at else event_at
        receive_lag_ms = max(0.0, (received_at - event_at).total_seconds() * 1_000)
        aggregate.receive_lag_ms_sum += receive_lag_ms
        aggregate.receive_lag_count += 1
        aggregate.max_receive_lag_ms = (
            receive_lag_ms
            if aggregate.max_receive_lag_ms is None
            else max(aggregate.max_receive_lag_ms, receive_lag_ms)
        )

    @staticmethod
    def _event_time(item: dict[str, Any]) -> datetime | None:
        try:
            timestamp_ms = int(item.get("t") or 0)
            return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc) if timestamp_ms > 0 else None
        except (TypeError, ValueError, OSError):
            return None

    @staticmethod
    def _float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _positive_float(cls, value: Any) -> float | None:
        parsed = cls._float(value, 0.0)
        return parsed if parsed > 0 else None
