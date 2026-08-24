from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx

from app.market_data.http import JsonHttpClient, MarketDataRequestError

from .models import SecurityDailySnapshot
from .qualification_scope import (
    QUALIFICATION_CALENDAR,
    QUALIFICATION_CALENDAR_PATH,
    QUALIFICATION_CALENDAR_VERSION,
    QUALIFICATION_PREVIOUS_SESSION_DATES,
    QUALIFICATION_RANKING_EARLY_CLOSES,
    QUALIFICATION_RANKING_SESSION_DATES,
    QUALIFICATION_SESSION_DATES,
)
from .universe import build_d1_universe


NEW_YORK = ZoneInfo("America/New_York")
REFERENCE_ENDPOINT = "/v3/reference/tickers"
REFERENCE_POLICY_VERSION = "DAY-D-MASSIVE-REFERENCE-TICKERS-v1"
MANIFEST_SCHEMA_VERSION = "DAY-D-POINT-IN-TIME-UNIVERSE-MANIFEST-v1"
RANKING_INPUT_SCHEMA_VERSION = "DAY-D-UNIVERSE-RANKING-INPUTS-v1"
UNIVERSE_POLICY_VERSION = "DAY-D-UNIVERSE-v1"
ELIGIBLE_PROVIDER_TYPES = frozenset({"CS"})
ELIGIBLE_LISTING_MICS = frozenset({"XNAS", "XNYS"})


class PointInTimeUniverseError(RuntimeError):
    pass


class JsonGetter(Protocol):
    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class ReferencePage:
    page_number: int
    request_url_without_api_key: str
    payload: dict[str, Any]

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.payload)


@dataclass(frozen=True, slots=True)
class ReferenceSecurity:
    symbol: str
    issuer_id: str
    listing_mic: str
    provider_type: str
    provider_name: str


@dataclass(frozen=True, slots=True)
class DailyRankingObservation:
    symbol: str
    session_date: date
    official_close_usd: Decimal
    regular_session_volume: Decimal
    regular_close_et: str

    @property
    def dollar_volume_usd(self) -> Decimal:
        return self.official_close_usd * self.regular_session_volume

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": RANKING_INPUT_SCHEMA_VERSION,
            "symbol": self.symbol,
            "session_date": self.session_date.isoformat(),
            "official_close_usd": _decimal_text(self.official_close_usd),
            "regular_session_volume": _decimal_text(self.regular_session_volume),
            "session_dollar_volume_usd": _decimal_text(self.dollar_volume_usd),
            "regular_close_et": self.regular_close_et,
        }


class MassivePointInTimeReferenceClient:
    """The only REST boundary authorized for qualification-universe identity."""

    def __init__(self, base_url: str, token: str, http: JsonGetter) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.http = http
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Massive base URL must be an absolute HTTPS URL")
        self._origin = (parsed.scheme, parsed.netloc)

    def fetch_pages(self, *, as_of: date, max_pages: int = 100) -> tuple[ReferencePage, ...]:
        if not self.token:
            raise PointInTimeUniverseError("Massive API token is not configured")
        if max_pages <= 0:
            raise ValueError("max_pages must be positive")
        url = f"{self.base_url}{REFERENCE_ENDPOINT}"
        params: dict[str, Any] = {
            "market": "stocks",
            "active": "true",
            "date": as_of.isoformat(),
            "order": "asc",
            "limit": 1000,
            "sort": "ticker",
            "apiKey": self.token,
        }
        seen_request_urls: set[str] = set()
        seen_raw_tickers: set[str] = set()
        previous_raw_ticker: str | None = None
        pages: list[ReferencePage] = []
        for page_number in range(1, max_pages + 1):
            public_request_url = self._public_request_url(url, params)
            if public_request_url in seen_request_urls:
                raise PointInTimeUniverseError("reference pagination returned a repeated URL")
            seen_request_urls.add(public_request_url)
            try:
                raw_payload = self.http.get_json(url, params=params)
            except MarketDataRequestError as exc:
                raise PointInTimeUniverseError(
                    f"Massive reference request failed: {self._redact(exc)}"
                ) from None
            if not isinstance(raw_payload, dict):
                raise PointInTimeUniverseError("reference page must be a JSON object")
            status = raw_payload.get("status")
            if status != "OK":
                raise PointInTimeUniverseError(f"reference page status is not OK: {status}")
            results = raw_payload.get("results") or []
            if not isinstance(results, list) or any(not isinstance(row, dict) for row in results):
                raise PointInTimeUniverseError("reference page results must be objects")
            for row in results:
                raw_ticker = str(row.get("ticker") or "").strip()
                if not raw_ticker:
                    raise PointInTimeUniverseError("reference page contains a tickerless row")
                if raw_ticker in seen_raw_tickers:
                    raise PointInTimeUniverseError(
                        f"reference pagination duplicated raw ticker {raw_ticker}"
                    )
                if previous_raw_ticker is not None and raw_ticker < previous_raw_ticker:
                    raise PointInTimeUniverseError("reference pages are not globally ticker-sorted")
                seen_raw_tickers.add(raw_ticker)
                previous_raw_ticker = raw_ticker

            sanitized = dict(raw_payload)
            next_url = str(raw_payload.get("next_url") or "").strip()
            if next_url:
                self._require_authorized_url(next_url)
                sanitized["next_url"] = self._sanitize_url(next_url)
            canonical = _canonical_json_bytes(sanitized)
            if self.token.encode() in canonical:
                raise PointInTimeUniverseError("reference evidence would contain the API token")
            pages.append(ReferencePage(page_number, public_request_url, sanitized))
            if not next_url:
                if not seen_raw_tickers:
                    raise PointInTimeUniverseError("reference query returned no tickers")
                return tuple(pages)
            url = next_url
            params = {"apiKey": self.token}
        raise PointInTimeUniverseError("reference pagination exceeded the safety limit")

    def _public_request_url(self, url: str, params: Mapping[str, Any]) -> str:
        clean = {key: value for key, value in params.items() if key.lower() != "apikey"}
        parsed = urlsplit(self._sanitize_url(url))
        existing = parse_qsl(parsed.query, keep_blank_values=True)
        query = urlencode([*existing, *sorted(clean.items())])
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))

    @staticmethod
    def _sanitize_url(url: str) -> str:
        parsed = urlsplit(url)
        query = urlencode([
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() != "apikey"
        ])
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))

    def _require_authorized_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if (parsed.scheme, parsed.netloc) != self._origin:
            raise PointInTimeUniverseError(
                "reference pagination attempted to leave api.massive.com"
            )
        if parsed.path != REFERENCE_ENDPOINT:
            raise PointInTimeUniverseError(
                "reference pagination attempted to use an unauthorized endpoint"
            )

    def _redact(self, exc: Exception) -> str:
        message = str(exc).replace(self.token, "[REDACTED]")
        return message.replace(urlencode({"apiKey": self.token}), "apiKey=[REDACTED]")


class PointInTimeUniverseBuilder:
    def __init__(
        self,
        *,
        root: Path,
        reference_client: MassivePointInTimeReferenceClient,
    ) -> None:
        self.root = root
        self.reference_client = reference_client

    def plan(self, *, session_date: date) -> dict[str, Any]:
        previous = self._previous_session(session_date)
        return {
            "executed": False,
            "session_date": session_date.isoformat(),
            "reference_as_of": previous.isoformat(),
            "reference_endpoint": REFERENCE_ENDPOINT,
            "reference_query": self._reference_query(previous),
            "ranking_session_dates": [
                value.isoformat()
                for value in QUALIFICATION_RANKING_SESSION_DATES[session_date]
            ],
            "manifest_path": str(self._manifest_path(session_date)),
            "network_request_count": 0,
        }

    def build_session(self, *, session_date: date, captured_at: datetime) -> Path:
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        previous = self._previous_session(session_date)
        if captured_at < self._session_close(previous):
            raise PointInTimeUniverseError(
                "reference capture timestamp cannot precede the D-1 close"
            )
        ranking_dates = QUALIFICATION_RANKING_SESSION_DATES[session_date]
        if len(ranking_dates) != 20 or ranking_dates[-1] != previous:
            raise PointInTimeUniverseError("frozen ranking calendar is invalid")
        pages = self.reference_client.fetch_pages(as_of=previous)
        securities, qqq, filter_counts = self._reference_securities(pages)
        candidate_symbols = set(securities) | {"QQQ"}

        observations: list[DailyRankingObservation] = []
        source_evidence: list[dict[str, Any]] = []
        for ranking_date in ranking_dates:
            source_path = self._minute_source_path(ranking_date)
            source_evidence.append(self._verified_source_evidence(source_path, ranking_date))
            observations.extend(self._daily_observations(
                source_path=source_path,
                session_date=ranking_date,
                symbols=candidate_symbols,
            ))
        observations.sort(key=lambda row: (row.symbol, row.session_date))
        qqq_dates = {
            row.session_date for row in observations if row.symbol == "QQQ"
        }
        if qqq_dates != set(ranking_dates):
            raise PointInTimeUniverseError("QQQ lacks a complete frozen ranking window")

        snapshots = self._snapshots(observations, securities)
        information_cutoff_at = self._session_close(previous)
        logical_generated_at = datetime.combine(
            session_date, time(9, 25), tzinfo=NEW_YORK
        )
        universe = build_d1_universe(
            session_date=session_date,
            previous_session_date=previous,
            generated_at=logical_generated_at,
            d1_information_cutoff_at=information_cutoff_at,
            snapshots=snapshots,
            selection_count=60,
        )
        if universe.shortfall or len(universe.members) != 60:
            raise PointInTimeUniverseError(
                f"qualification universe must contain 60 issuers; shortfall={universe.shortfall}"
            )

        reference_page_evidence = self._publish_reference_pages(previous, pages)
        ranking_path = self._ranking_inputs_path(session_date)
        ranking_bytes = b"".join(
            _canonical_json_bytes(row.payload()) for row in observations
        )
        _write_immutable_bytes(ranking_path, ranking_bytes)
        ranking_evidence = self._file_evidence(ranking_path)
        ranking_evidence["schema_version"] = RANKING_INPUT_SCHEMA_VERSION
        ranking_evidence["row_count"] = len(observations)
        ranking_evidence["parent_minute_aggregate_sources"] = source_evidence

        rows = [
            {
                "role": "tradeable",
                "benchmark": False,
                "rank": member.rank,
                "symbol": member.symbol,
                "issuer_id": member.issuer_id,
                "listing_mic": member.listing_mic,
                "security_type": member.security_type,
                "provider_type": securities[member.symbol].provider_type,
                "provider_name": securities[member.symbol].provider_name,
                "d1_close_usd": member.d1_close_usd,
                "median_dollar_volume_20d_usd": member.median_dollar_volume_20d_usd,
                "history_session_count": member.history_session_count,
                "liquidity_quintile": member.liquidity_quintile,
                "data_as_of": member.data_as_of.astimezone(timezone.utc).isoformat(),
                "selection_reason": member.selection_reason,
                "substitution_reason": member.substitution_reason,
            }
            for member in universe.members
        ]
        rows.append({
            "role": "benchmark",
            "benchmark": True,
            "rank": None,
            "symbol": "QQQ",
            "issuer_id": qqq.issuer_id,
            "listing_mic": qqq.listing_mic,
            "security_type": "ETF_BENCHMARK",
            "d1_close_usd": None,
            "median_dollar_volume_20d_usd": None,
            "history_session_count": 20,
            "liquidity_quintile": None,
            "data_as_of": information_cutoff_at.astimezone(timezone.utc).isoformat(),
            "selection_reason": "NON_TRADEABLE_FROZEN_BENCHMARK",
            "substitution_reason": None,
        })

        manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "policy_version": UNIVERSE_POLICY_VERSION,
            "reference_policy_version": REFERENCE_POLICY_VERSION,
            "session_date": session_date.isoformat(),
            "previous_session_date": previous.isoformat(),
            "logical_generated_at": logical_generated_at.astimezone(timezone.utc).isoformat(),
            "captured_at": captured_at.astimezone(timezone.utc).isoformat(),
            "information_cutoff_at": information_cutoff_at.astimezone(timezone.utc).isoformat(),
            "calendar": {
                "version": QUALIFICATION_CALENDAR_VERSION,
                "contract_path": "app/day_d_replay/qualification_calendar_v1.json",
                "contract_sha256": _sha256_file(QUALIFICATION_CALENDAR_PATH),
                "timezone": QUALIFICATION_CALENDAR["timezone"],
                "calendar_name": QUALIFICATION_CALENDAR["calendar_name"],
                "ranking_session_dates": [value.isoformat() for value in ranking_dates],
                "regular_open_et": QUALIFICATION_CALENDAR["regular_open_et"],
                "regular_close_et": QUALIFICATION_CALENDAR["regular_close_et"],
                "early_closes_et": QUALIFICATION_CALENDAR["early_closes_et"],
            },
            "reference": {
                "provider": "Massive",
                "endpoint": REFERENCE_ENDPOINT,
                "query": self._reference_query(previous),
                "request_count": len(pages),
                "pages": reference_page_evidence,
                "filter_counts": filter_counts,
            },
            "selection_rule": self.selection_rule(),
            "ranking_inputs": ranking_evidence,
            "universe": {
                "tradeable_count": 60,
                "benchmark_count": 1,
                "total_count": 61,
                "benchmark_is_ranked": False,
                "rows": rows,
            },
            "anti_lookahead": {
                "reference_date_equals_previous_session": True,
                "ranking_window_ends_at_previous_session_inclusive": True,
                "session_d_data_used": False,
                "future_corporate_actions_used": False,
            },
            "official_replay_ready": False,
        }
        manifest["payload_sha256"] = _payload_hash(manifest)
        target = self._manifest_path(session_date)
        _write_immutable_bytes(target, _canonical_json_bytes(manifest, pretty=True))
        return target

    @staticmethod
    def selection_rule() -> dict[str, Any]:
        return {
            "selection_count": 60,
            "benchmark_symbol": "QQQ",
            "benchmark_role": "flagged_non_tradeable_not_ranked",
            "reference_filters": {
                "market": "stocks",
                "active": True,
                "locale": "us",
                "currency_name": "usd",
                "primary_exchange_in": sorted(ELIGIBLE_LISTING_MICS),
                "provider_type_in": sorted(ELIGIBLE_PROVIDER_TYPES),
                "provider_type_mapping": {
                    "CS": "eligible_common_stock_class_for_the_frozen_universe",
                },
                "issuer_identity": "CIK_required",
                "ADR_ADS_ETF_ETN_fund_preferred_warrant_unit_right_OTC_excluded_by_provider_type": True,
            },
            "ranking_lookback_completed_sessions": 20,
            "minimum_complete_ranking_sessions": 20,
            "minimum_d1_official_close_usd": 3.0,
            "session_dollar_volume_formula": "regular_session_last_close * sum(regular_session_minute_volume)",
            "split_semantics": "session_dollar_volume_is_invariant_to_point_in_time_split_rescaling_of_price_and_volume",
            "ranking_statistic": "median_session_dollar_volume",
            "ranking_direction": "descending",
            "issuer_deduplication": "retain_highest_ranked_share_class_per_CIK",
            "tie_breaks": ["normalized_ticker_ascending", "raw_ticker_ascending"],
            "ranking_window_end": "previous_session_inclusive",
            "session_D_input_forbidden": True,
        }

    def _reference_securities(
        self,
        pages: Sequence[ReferencePage],
    ) -> tuple[dict[str, ReferenceSecurity], ReferenceSecurity, dict[str, int]]:
        filters = {
            "rows_seen": 0,
            "eligible_common_stock": 0,
            "benchmark_qqq": 0,
            "not_us_stock": 0,
            "inactive": 0,
            "wrong_exchange": 0,
            "wrong_provider_type": 0,
            "non_usd": 0,
            "missing_cik": 0,
        }
        securities: dict[str, ReferenceSecurity] = {}
        qqq: ReferenceSecurity | None = None
        for page in pages:
            for row in page.payload.get("results", []):
                filters["rows_seen"] += 1
                symbol = str(row.get("ticker") or "").strip()
                if row.get("active") is not True:
                    filters["inactive"] += 1
                    continue
                if row.get("market") != "stocks" or row.get("locale") != "us":
                    filters["not_us_stock"] += 1
                    continue
                listing_mic = str(row.get("primary_exchange") or "").strip().upper()
                if listing_mic not in ELIGIBLE_LISTING_MICS:
                    filters["wrong_exchange"] += 1
                    continue
                currency = str(row.get("currency_name") or "").strip().lower()
                if currency != "usd":
                    filters["non_usd"] += 1
                    continue
                issuer_id = str(row.get("cik") or "").strip()
                if not issuer_id:
                    filters["missing_cik"] += 1
                    continue
                provider_type = str(row.get("type") or "").strip().upper()
                security = ReferenceSecurity(
                    symbol=symbol,
                    issuer_id=issuer_id,
                    listing_mic=listing_mic,
                    provider_type=provider_type,
                    provider_name=str(row.get("name") or "").strip(),
                )
                if symbol == "QQQ":
                    qqq = security
                    filters["benchmark_qqq"] += 1
                    continue
                if provider_type not in ELIGIBLE_PROVIDER_TYPES:
                    filters["wrong_provider_type"] += 1
                    continue
                securities[symbol] = security
                filters["eligible_common_stock"] += 1
        if qqq is None:
            raise PointInTimeUniverseError("point-in-time reference lacks QQQ")
        if len(securities) < 60:
            raise PointInTimeUniverseError("point-in-time reference has fewer than 60 eligible stocks")
        return securities, qqq, filters

    def _daily_observations(
        self,
        *,
        source_path: Path,
        session_date: date,
        symbols: set[str],
    ) -> list[DailyRankingObservation]:
        regular_open = datetime.combine(session_date, time(9, 30), tzinfo=NEW_YORK)
        regular_close = self._session_close(session_date)
        by_symbol: dict[str, tuple[int, Decimal, Decimal]] = {}
        seen_windows: set[tuple[str, int]] = set()
        try:
            handle = gzip.open(source_path, "rt", encoding="utf-8", newline="")
        except OSError as exc:
            raise PointInTimeUniverseError(f"minute aggregate cannot be opened: {source_path}") from exc
        with handle:
            reader = csv.DictReader(handle)
            required = {"ticker", "window_start", "close", "volume"}
            if reader.fieldnames is None or not required <= set(reader.fieldnames):
                raise PointInTimeUniverseError(
                    f"minute aggregate columns are incomplete: {source_path}"
                )
            for row in reader:
                symbol = str(row.get("ticker") or "").strip()
                if symbol not in symbols:
                    continue
                try:
                    window_ns = int(str(row.get("window_start") or ""))
                    close = Decimal(str(row.get("close") or ""))
                    volume = Decimal(str(row.get("volume") or ""))
                except (ValueError, InvalidOperation) as exc:
                    raise PointInTimeUniverseError(
                        f"malformed ranking bar for {symbol} on {session_date}"
                    ) from exc
                if window_ns <= 0 or close <= 0 or volume < 0:
                    raise PointInTimeUniverseError(
                        f"invalid ranking bar for {symbol} on {session_date}"
                    )
                observed_at = datetime.fromtimestamp(
                    window_ns / 1_000_000_000, tz=timezone.utc
                ).astimezone(NEW_YORK)
                if observed_at.date() != session_date:
                    continue
                if not regular_open <= observed_at < regular_close:
                    continue
                key = (symbol, window_ns)
                if key in seen_windows:
                    raise PointInTimeUniverseError(
                        f"duplicate minute aggregate for {symbol} at {window_ns}"
                    )
                seen_windows.add(key)
                previous = by_symbol.get(symbol)
                if previous is None:
                    by_symbol[symbol] = (window_ns, close, volume)
                else:
                    latest_ns, latest_close, cumulative_volume = previous
                    if window_ns > latest_ns:
                        latest_ns, latest_close = window_ns, close
                    by_symbol[symbol] = (
                        latest_ns,
                        latest_close,
                        cumulative_volume + volume,
                    )
        close_text = regular_close.strftime("%H:%M:%S")
        return [
            DailyRankingObservation(
                symbol=symbol,
                session_date=session_date,
                official_close_usd=values[1],
                regular_session_volume=values[2],
                regular_close_et=close_text,
            )
            for symbol, values in sorted(by_symbol.items())
        ]

    def _snapshots(
        self,
        observations: Sequence[DailyRankingObservation],
        securities: Mapping[str, ReferenceSecurity],
    ) -> list[SecurityDailySnapshot]:
        output: list[SecurityDailySnapshot] = []
        for row in observations:
            security = securities.get(row.symbol)
            if security is None:
                continue
            output.append(SecurityDailySnapshot(
                session_date=row.session_date,
                available_at=self._session_close(row.session_date),
                symbol=row.symbol,
                issuer_id=security.issuer_id,
                listing_mic=security.listing_mic,
                security_type="US_DOMESTIC_OPERATING_COMPANY_COMMON_STOCK",
                adjusted_close_usd=float(row.official_close_usd),
                adjusted_regular_volume=float(row.regular_session_volume),
                active=True,
            ))
        return output

    def _publish_reference_pages(
        self,
        as_of: date,
        pages: Sequence[ReferencePage],
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for page in pages:
            path = self._reference_page_path(as_of, page.page_number)
            _write_immutable_bytes(path, page.canonical_bytes)
            item = self._file_evidence(path)
            item.update({
                "page_number": page.page_number,
                "request_url_without_api_key": page.request_url_without_api_key,
                "row_count": len(page.payload.get("results") or []),
                "canonicalization": "canonical_json_sorted_keys_compact_api_key_removed",
            })
            evidence.append(item)
        return evidence

    def _verified_source_evidence(self, source_path: Path, session_date: date) -> dict[str, Any]:
        if not source_path.exists():
            raise PointInTimeUniverseError(f"minute aggregate is missing: {source_path}")
        metadata_path = source_path.with_name(f"{source_path.name}.metadata.json")
        if not metadata_path.exists():
            raise PointInTimeUniverseError(f"minute aggregate metadata is missing: {source_path}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        size = source_path.stat().st_size
        sha256 = _sha256_file(source_path)
        if int(metadata.get("content_length") or -1) != size:
            raise PointInTimeUniverseError(f"minute aggregate size mismatch: {source_path}")
        if metadata.get("sha256") != sha256:
            raise PointInTimeUniverseError(f"minute aggregate checksum mismatch: {source_path}")
        return {
            "session_date": session_date.isoformat(),
            "path": self._relative(source_path),
            "bytes": size,
            "sha256": sha256,
            "metadata_path": self._relative(metadata_path),
            "metadata_sha256": _sha256_file(metadata_path),
        }

    def _file_evidence(self, path: Path) -> dict[str, Any]:
        return {
            "path": self._relative(path),
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }

    def _relative(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.root.resolve()))
        except ValueError as exc:
            raise PointInTimeUniverseError("evidence path escaped the dataset root") from exc

    @staticmethod
    def _previous_session(session_date: date) -> date:
        try:
            return QUALIFICATION_PREVIOUS_SESSION_DATES[session_date]
        except KeyError as exc:
            raise PointInTimeUniverseError(
                f"session is outside the frozen qualification scope: {session_date}"
            ) from exc

    @staticmethod
    def _reference_query(previous: date) -> dict[str, Any]:
        return {
            "market": "stocks",
            "active": True,
            "date": previous.isoformat(),
            "order": "asc",
            "limit": 1000,
            "sort": "ticker",
        }

    @staticmethod
    def _session_close(session_date: date) -> datetime:
        close_text = QUALIFICATION_RANKING_EARLY_CLOSES.get(session_date, "16:00:00")
        return datetime.combine(
            session_date,
            time.fromisoformat(close_text),
            tzinfo=NEW_YORK,
        )

    def _minute_source_path(self, session_date: date) -> Path:
        return (
            self.root
            / "provider=massive"
            / "dataset=minute_aggregates"
            / f"session_date={session_date.isoformat()}"
            / "source.csv.gz"
        )

    def _reference_page_path(self, as_of: date, page_number: int) -> Path:
        return (
            self.root
            / "provider=massive"
            / "reference-tickers"
            / f"as_of={as_of.isoformat()}"
            / f"page-{page_number:04d}.json"
        )

    def _ranking_inputs_path(self, session_date: date) -> Path:
        return (
            self.root
            / "provider=massive"
            / "universe-ranking-inputs"
            / f"session_date={session_date.isoformat()}"
            / "ranking-inputs.ndjson"
        )

    def _manifest_path(self, session_date: date) -> Path:
        return (
            self.root
            / "provider=massive"
            / "universe-manifests"
            / f"session_date={session_date.isoformat()}"
            / "universe.json"
        )


def load_point_in_time_universe_manifest(
    path: Path,
    *,
    expected_session_date: date,
) -> tuple[dict[str, Any], frozenset[str]]:
    if not path.exists():
        raise PointInTimeUniverseError(f"point-in-time universe manifest is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PointInTimeUniverseError("point-in-time universe manifest is unreadable") from exc
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise PointInTimeUniverseError("point-in-time universe manifest schema mismatch")
    if payload.get("policy_version") != UNIVERSE_POLICY_VERSION:
        raise PointInTimeUniverseError("point-in-time universe policy mismatch")
    if payload.get("session_date") != expected_session_date.isoformat():
        raise PointInTimeUniverseError("point-in-time universe belongs to another session")
    try:
        expected_previous = QUALIFICATION_PREVIOUS_SESSION_DATES[expected_session_date]
        expected_ranking_dates = QUALIFICATION_RANKING_SESSION_DATES[expected_session_date]
    except KeyError as exc:
        raise PointInTimeUniverseError(
            "point-in-time universe session is outside the frozen qualification scope"
        ) from exc
    if payload.get("previous_session_date") != expected_previous.isoformat():
        raise PointInTimeUniverseError("point-in-time universe D-1 date mismatch")
    expected_hash = str(payload.get("payload_sha256") or "")
    if expected_hash != _payload_hash(payload):
        raise PointInTimeUniverseError("point-in-time universe payload checksum mismatch")

    if payload.get("reference_policy_version") != REFERENCE_POLICY_VERSION:
        raise PointInTimeUniverseError("point-in-time reference policy mismatch")
    calendar = payload.get("calendar")
    if not isinstance(calendar, dict):
        raise PointInTimeUniverseError("point-in-time universe calendar is missing")
    if calendar.get("version") != QUALIFICATION_CALENDAR_VERSION:
        raise PointInTimeUniverseError("point-in-time universe calendar version mismatch")
    if calendar.get("contract_sha256") != _sha256_file(QUALIFICATION_CALENDAR_PATH):
        raise PointInTimeUniverseError("point-in-time universe calendar checksum mismatch")
    if calendar.get("ranking_session_dates") != [
        value.isoformat() for value in expected_ranking_dates
    ]:
        raise PointInTimeUniverseError("point-in-time universe ranking calendar mismatch")
    if payload.get("selection_rule") != PointInTimeUniverseBuilder.selection_rule():
        raise PointInTimeUniverseError("point-in-time universe selection rule mismatch")
    anti_lookahead = payload.get("anti_lookahead")
    if anti_lookahead != {
        "reference_date_equals_previous_session": True,
        "ranking_window_ends_at_previous_session_inclusive": True,
        "session_d_data_used": False,
        "future_corporate_actions_used": False,
    }:
        raise PointInTimeUniverseError("point-in-time universe anti-lookahead proof mismatch")

    reference = payload.get("reference")
    if not isinstance(reference, dict):
        raise PointInTimeUniverseError("point-in-time universe reference evidence is missing")
    if reference.get("provider") != "Massive" or reference.get("endpoint") != REFERENCE_ENDPOINT:
        raise PointInTimeUniverseError("point-in-time universe used an unauthorized endpoint")
    if reference.get("query") != PointInTimeUniverseBuilder._reference_query(
        expected_previous
    ):
        raise PointInTimeUniverseError("point-in-time reference query mismatch")
    pages = reference.get("pages")
    if not isinstance(pages, list) or not pages:
        raise PointInTimeUniverseError("point-in-time universe has no reference pages")
    if reference.get("request_count") != len(pages):
        raise PointInTimeUniverseError("point-in-time reference request count mismatch")
    if [page.get("page_number") for page in pages if isinstance(page, dict)] != list(
        range(1, len(pages) + 1)
    ):
        raise PointInTimeUniverseError("point-in-time reference page sequence mismatch")

    universe = payload.get("universe")
    rows = universe.get("rows") if isinstance(universe, dict) else None
    if not isinstance(rows, list) or len(rows) != 61:
        raise PointInTimeUniverseError("point-in-time universe must contain exactly 61 rows")
    tradeable = [row for row in rows if isinstance(row, dict) and row.get("role") == "tradeable"]
    benchmarks = [row for row in rows if isinstance(row, dict) and row.get("role") == "benchmark"]
    if len(tradeable) != 60 or len(benchmarks) != 1:
        raise PointInTimeUniverseError("point-in-time universe role counts are invalid")
    if universe.get("tradeable_count") != 60 or universe.get("benchmark_count") != 1:
        raise PointInTimeUniverseError("point-in-time universe declared counts are invalid")
    if universe.get("total_count") != 61 or universe.get("benchmark_is_ranked") is not False:
        raise PointInTimeUniverseError("point-in-time universe benchmark declaration is invalid")
    if [row.get("rank") for row in tradeable] != list(range(1, 61)):
        raise PointInTimeUniverseError("point-in-time universe ranks must be exactly 1 through 60")
    if any(row.get("benchmark") is not False for row in tradeable):
        raise PointInTimeUniverseError("tradeable universe rows cannot be benchmarks")
    if benchmarks[0].get("symbol") != "QQQ" or benchmarks[0].get("rank") is not None:
        raise PointInTimeUniverseError("QQQ must be the unranked benchmark")
    if benchmarks[0].get("benchmark") is not True:
        raise PointInTimeUniverseError("QQQ benchmark flag is missing")
    symbols = [str(row.get("symbol") or "").strip() for row in rows]
    if any(not symbol for symbol in symbols) or len(symbols) != len(set(symbols)):
        raise PointInTimeUniverseError("point-in-time universe symbols are invalid")

    dataset_root = _dataset_root_for_manifest(path)
    linked = [*pages]
    ranking = payload.get("ranking_inputs")
    if not isinstance(ranking, dict):
        raise PointInTimeUniverseError("point-in-time ranking evidence is missing")
    if ranking.get("schema_version") != RANKING_INPUT_SCHEMA_VERSION:
        raise PointInTimeUniverseError("point-in-time ranking evidence schema mismatch")
    parent_sources = ranking.get("parent_minute_aggregate_sources")
    if not isinstance(parent_sources, list) or [
        source.get("session_date") for source in parent_sources if isinstance(source, dict)
    ] != [value.isoformat() for value in expected_ranking_dates]:
        raise PointInTimeUniverseError("point-in-time ranking parent sequence mismatch")
    linked.append(ranking)
    for evidence in linked:
        if not isinstance(evidence, dict):
            raise PointInTimeUniverseError("point-in-time universe evidence is malformed")
        relative = Path(str(evidence.get("path") or ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise PointInTimeUniverseError("point-in-time evidence path is unsafe")
        evidence_path = (dataset_root / relative).resolve()
        try:
            evidence_path.relative_to(dataset_root.resolve())
        except ValueError as exc:
            raise PointInTimeUniverseError(
                "point-in-time evidence resolved outside the dataset root"
            ) from exc
        if not evidence_path.exists():
            raise PointInTimeUniverseError(f"point-in-time evidence is missing: {relative}")
        if evidence_path.stat().st_size != int(evidence.get("bytes") or -1):
            raise PointInTimeUniverseError(f"point-in-time evidence size mismatch: {relative}")
        if _sha256_file(evidence_path) != evidence.get("sha256"):
            raise PointInTimeUniverseError(f"point-in-time evidence checksum mismatch: {relative}")
    return payload, frozenset(symbols)


def _dataset_root_for_manifest(path: Path) -> Path:
    resolved = path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if parent.name == "provider=massive":
            return parent.parent
    raise PointInTimeUniverseError("universe manifest is outside provider=massive")


def _canonical_json_bytes(payload: Any, *, pretty: bool = False) -> bytes:
    if pretty:
        serialized = json.dumps(
            payload,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    else:
        serialized = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    return f"{serialized}\n".encode()


def _payload_hash(payload: Mapping[str, Any]) -> str:
    canonical = {key: value for key, value in payload.items() if key != "payload_sha256"}
    return hashlib.sha256(_canonical_json_bytes(canonical)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_immutable_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == content:
            return
        raise PointInTimeUniverseError(f"immutable evidence already differs: {path}")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.part")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise PointInTimeUniverseError(
                f"immutable evidence appeared concurrently: {path}"
            ) from exc
        temporary.unlink()
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must be timezone-aware")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    from app.config import get_settings

    parser = argparse.ArgumentParser(
        description="Plan or build frozen point-in-time qualification universes"
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--session-date", type=date.fromisoformat, action="append")
    scope.add_argument("--all-qualification-sessions", action="store_true")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="perform reference requests and publish immutable evidence",
    )
    parser.add_argument("--captured-at", type=_parse_datetime)
    args = parser.parse_args(argv)
    settings = get_settings()
    sessions = (
        sorted(QUALIFICATION_SESSION_DATES)
        if args.all_qualification_sessions
        else list(dict.fromkeys(args.session_date or []))
    )
    if not args.execute:
        placeholder = MassivePointInTimeReferenceClient(
            settings.massive_base_url,
            settings.massive_api_token or "plan-only-placeholder",
            JsonHttpClient(timeout=1, max_retries=0),
        )
        builder = PointInTimeUniverseBuilder(
            root=settings.day_d_dataset_root,
            reference_client=placeholder,
        )
        print(json.dumps({
            "executed": False,
            "plans": [builder.plan(session_date=value) for value in sessions],
        }, indent=2, sort_keys=True))
        return 0
    if not settings.day_d_point_in_time_reference_authorized:
        raise PointInTimeUniverseError(
            "point-in-time reference execution remains disabled pending reviewed merge"
        )
    if args.captured_at is None:
        parser.error("--captured-at is required with --execute")
    with httpx.Client(follow_redirects=False) as transport:
        client = MassivePointInTimeReferenceClient(
            settings.massive_base_url,
            settings.massive_api_token,
            JsonHttpClient(
                timeout=settings.market_data_timeout_seconds,
                max_retries=settings.market_data_max_retries,
                client=transport,
            ),
        )
        builder = PointInTimeUniverseBuilder(
            root=settings.day_d_dataset_root,
            reference_client=client,
        )
        manifests = [
            str(builder.build_session(session_date=value, captured_at=args.captured_at))
            for value in sessions
        ]
    print(json.dumps({"executed": True, "manifests": manifests}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
