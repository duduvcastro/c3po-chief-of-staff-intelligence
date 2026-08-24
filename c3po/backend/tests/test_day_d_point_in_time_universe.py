from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.day_d_replay.point_in_time_universe import (
    REFERENCE_ENDPOINT,
    MassivePointInTimeReferenceClient,
    PointInTimeUniverseBuilder,
    PointInTimeUniverseError,
    ReferencePage,
    load_point_in_time_universe_manifest,
)
from app.day_d_replay.models import SecurityDailySnapshot
from app.day_d_replay.qualification_scope import (
    QUALIFICATION_PREVIOUS_SESSION_DATES,
    QUALIFICATION_RANKING_SESSION_DATES,
    QUALIFICATION_SESSION_DATES,
)
from app.day_d_replay.universe import build_d1_universe


NEW_YORK = ZoneInfo("America/New_York")
SESSION = date(2026, 8, 21)


class _PaginatedHttp:
    def __init__(
        self,
        *,
        off_origin: bool = False,
        unauthorized_path: bool = False,
    ) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.off_origin = off_origin
        self.unauthorized_path = unauthorized_path

    def get_json(self, url: str, *, params=None, headers=None):  # noqa: ANN001, ANN201
        del headers
        self.calls.append((url, dict(params or {})))
        if len(self.calls) == 1:
            if self.off_origin:
                next_url = "https://evil.example/v3/reference/tickers?cursor=unsafe"
            elif self.unauthorized_path:
                next_url = "https://api.massive.com/v3/trades/AAPL?cursor=unsafe"
            else:
                next_url = (
                    "https://api.massive.com/v3/reference/tickers"
                    "?cursor=next&apiKey=secret"
                )
            return {
                "status": "OK",
                "results": [{"ticker": "AAPL"}],
                "next_url": next_url,
            }
        return {"status": "OK", "results": [{"ticker": "MSFT"}]}


class _StaticReferenceClient:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.requests: list[date] = []

    def fetch_pages(self, *, as_of: date, max_pages: int = 100):  # noqa: ANN201
        del max_pages
        self.requests.append(as_of)
        return (
            ReferencePage(
                page_number=1,
                request_url_without_api_key=(
                    "https://api.massive.com/v3/reference/tickers"
                    f"?active=True&date={as_of.isoformat()}&limit=1000"
                    "&market=stocks&order=asc&sort=ticker"
                ),
                payload={"status": "OK", "results": self.rows},
            ),
        )


class _SinglePageHttp:
    def __init__(self, tickers: list[str]) -> None:
        self.tickers = tickers

    def get_json(self, url: str, *, params=None, headers=None):  # noqa: ANN001, ANN201
        del url, params, headers
        return {
            "status": "OK",
            "results": [{"ticker": ticker} for ticker in self.tickers],
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reference_rows() -> list[dict[str, object]]:
    rows = [
        {
            "ticker": f"S{index:03d}",
            "name": f"Issuer {index}",
            "market": "stocks",
            "locale": "us",
            "active": True,
            "primary_exchange": "XNAS" if index % 2 == 0 else "XNYS",
            "currency_name": "usd",
            "cik": f"{index + 1:010d}",
            "type": "CS",
        }
        for index in range(61)
    ]
    rows.append({
        "ticker": "QQQ",
        "name": "Invesco QQQ Trust",
        "market": "stocks",
        "locale": "us",
        "active": True,
        "primary_exchange": "XNAS",
        "currency_name": "usd",
        "cik": "0001067839",
        "type": "ETF",
    })
    return sorted(rows, key=lambda row: str(row["ticker"]))


def _write_minute_source(root: Path, session_date: date) -> Path:
    target = (
        root
        / "provider=massive"
        / "dataset=minute_aggregates"
        / f"session_date={session_date.isoformat()}"
        / "source.csv.gz"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    observed_at = datetime.combine(session_date, time(15, 59), tzinfo=NEW_YORK)
    window_ns = int(observed_at.astimezone(timezone.utc).timestamp() * 1_000_000_000)
    with gzip.open(target, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("ticker", "window_start", "close", "volume"),
        )
        writer.writeheader()
        for index in range(61):
            writer.writerow({
                "ticker": f"S{index:03d}",
                "window_start": window_ns,
                "close": "10",
                "volume": str(10_000 - index),
            })
        writer.writerow({
            "ticker": "QQQ",
            "window_start": window_ns,
            "close": "500",
            "volume": "50000",
        })
    metadata = {
        "content_length": target.stat().st_size,
        "sha256": _sha256(target),
    }
    target.with_name(f"{target.name}.metadata.json").write_text(
        json.dumps(metadata, sort_keys=True),
        encoding="utf-8",
    )
    return target


def test_reference_client_uses_only_the_authorized_paginated_endpoint() -> None:
    http = _PaginatedHttp()
    client = MassivePointInTimeReferenceClient(
        "https://api.massive.com",
        "secret",
        http,
    )

    pages = client.fetch_pages(as_of=date(2026, 8, 20))

    assert len(pages) == len(http.calls) == 2
    assert all(REFERENCE_ENDPOINT in call[0] for call in http.calls)
    assert http.calls[0][1] == {
        "market": "stocks",
        "active": "true",
        "date": "2026-08-20",
        "order": "asc",
        "limit": 1000,
        "sort": "ticker",
        "apiKey": "secret",
    }
    assert http.calls[1] == (
        "https://api.massive.com/v3/reference/tickers",
        {"cursor": "next", "apiKey": "secret"},
    )
    assert pages[1].request_url_without_api_key == (
        "https://api.massive.com/v3/reference/tickers?cursor=next"
    )
    evidence = b"".join(page.canonical_bytes for page in pages)
    assert b"secret" not in evidence
    assert all("secret" not in page.request_url_without_api_key for page in pages)


def test_reference_client_validates_provider_raw_ticker_order_before_normalization() -> None:
    client = MassivePointInTimeReferenceClient(
        "https://api.massive.com",
        "secret",
        _SinglePageHttp(["ACRX", "ACRpC"]),
    )

    pages = client.fetch_pages(as_of=date(2022, 6, 10))

    assert len(pages) == 1
    assert [row["ticker"] for row in pages[0].payload["results"]] == ["ACRX", "ACRpC"]


def test_reference_client_keeps_case_distinct_provider_symbols_separate() -> None:
    client = MassivePointInTimeReferenceClient(
        "https://api.massive.com",
        "secret",
        _SinglePageHttp(["ALPA", "ALpA"]),
    )

    pages = client.fetch_pages(as_of=date(2022, 6, 10))

    assert [row["ticker"] for row in pages[0].payload["results"]] == ["ALPA", "ALpA"]


def test_reference_client_still_rejects_exact_raw_ticker_duplicates() -> None:
    client = MassivePointInTimeReferenceClient(
        "https://api.massive.com",
        "secret",
        _SinglePageHttp(["ALPA", "ALPA"]),
    )

    with pytest.raises(PointInTimeUniverseError, match="duplicated raw ticker ALPA"):
        client.fetch_pages(as_of=date(2022, 6, 10))


def test_builder_keeps_preferred_case_variant_out_of_common_stock_bars(
    tmp_path: Path,
) -> None:
    rows = [
        {
            "ticker": "ALPA",
            "name": "Alpha Pro Tech, Ltd.",
            "market": "stocks",
            "locale": "us",
            "active": True,
            "primary_exchange": "XNYS",
            "currency_name": "usd",
            "cik": "0000884269",
            "type": "CS",
        },
        *[
            {
                "ticker": f"S{index:03d}",
                "name": f"Issuer {index}",
                "market": "stocks",
                "locale": "us",
                "active": True,
                "primary_exchange": "XNAS",
                "currency_name": "usd",
                "cik": f"{index + 1:010d}",
                "type": "CS",
            }
            for index in range(59)
        ],
        {
            "ticker": "ALpA",
            "name": "Air Lease Corporation Preferred Series A",
            "market": "stocks",
            "locale": "us",
            "active": True,
            "primary_exchange": "XNYS",
            "currency_name": "usd",
            "cik": "0001487712",
            "type": "PFD",
        },
        {
            "ticker": "QQQ",
            "name": "Invesco QQQ Trust",
            "market": "stocks",
            "locale": "us",
            "active": True,
            "primary_exchange": "XNAS",
            "currency_name": "usd",
            "cik": "0001067839",
            "type": "ETF",
        },
    ]
    page = ReferencePage(1, "https://api.massive.com/v3/reference/tickers", {
        "status": "OK",
        "results": rows,
    })
    builder = PointInTimeUniverseBuilder(
        root=tmp_path,
        reference_client=_StaticReferenceClient(rows),
    )

    securities, _qqq, filters = builder._reference_securities((page,))

    assert "ALPA" in securities
    assert "ALpA" not in securities
    assert filters["wrong_provider_type"] == 1

    source = tmp_path / "source.csv.gz"
    observed_at = datetime(2022, 6, 10, 15, 59, tzinfo=NEW_YORK)
    window_ns = int(observed_at.astimezone(timezone.utc).timestamp() * 1_000_000_000)
    with gzip.open(source, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("ticker", "window_start", "close", "volume"))
        writer.writeheader()
        writer.writerow({"ticker": "ALPA", "window_start": window_ns, "close": "4", "volume": "100"})
        writer.writerow({"ticker": "ALpA", "window_start": window_ns, "close": "25", "volume": "900"})

    observations = builder._daily_observations(
        source_path=source,
        session_date=date(2022, 6, 10),
        symbols=set(securities),
    )

    assert [(row.symbol, str(row.official_close_usd), str(row.regular_session_volume)) for row in observations] == [
        ("ALPA", "4", "100")
    ]


def test_reference_client_still_rejects_raw_ticker_order_inversion() -> None:
    client = MassivePointInTimeReferenceClient(
        "https://api.massive.com",
        "secret",
        _SinglePageHttp(["MSFT", "AAPL"]),
    )

    with pytest.raises(PointInTimeUniverseError, match="globally ticker-sorted"):
        client.fetch_pages(as_of=date(2022, 6, 10))


def test_reference_client_refuses_off_origin_pagination() -> None:
    client = MassivePointInTimeReferenceClient(
        "https://api.massive.com",
        "secret",
        _PaginatedHttp(off_origin=True),
    )

    with pytest.raises(PointInTimeUniverseError, match="leave api.massive.com"):
        client.fetch_pages(as_of=date(2026, 8, 20))


def test_reference_client_refuses_another_endpoint_on_the_same_origin() -> None:
    client = MassivePointInTimeReferenceClient(
        "https://api.massive.com",
        "secret",
        _PaginatedHttp(unauthorized_path=True),
    )

    with pytest.raises(PointInTimeUniverseError, match="unauthorized endpoint"):
        client.fetch_pages(as_of=date(2026, 8, 20))


def test_frozen_calendar_has_exactly_twenty_d1_sessions_for_each_lot() -> None:
    assert len(QUALIFICATION_SESSION_DATES) == 12
    for session_date in QUALIFICATION_SESSION_DATES:
        ranking_dates = QUALIFICATION_RANKING_SESSION_DATES[session_date]
        assert len(ranking_dates) == len(set(ranking_dates)) == 20
        assert ranking_dates == tuple(sorted(ranking_dates))
        assert ranking_dates[-1] == QUALIFICATION_PREVIOUS_SESSION_DATES[session_date]
        assert max(ranking_dates) < session_date


def test_raw_ticker_is_the_deterministic_secondary_tie_break() -> None:
    d1 = date(2026, 8, 20)
    cutoff = datetime(2026, 8, 20, 16, tzinfo=NEW_YORK)
    snapshots = [
        SecurityDailySnapshot(
            session_date=d1 - timedelta(days=19 - offset),
            available_at=cutoff,
            symbol=symbol,
            issuer_id="same-issuer",
            listing_mic="XNAS",
            security_type="US_DOMESTIC_OPERATING_COMPANY_COMMON_STOCK",
            adjusted_close_usd=10.0,
            adjusted_regular_volume=1_000.0,
            active=True,
        )
        for symbol in ("AAA", "AA.A")
        for offset in range(20)
    ]

    universe = build_d1_universe(
        session_date=SESSION,
        previous_session_date=d1,
        generated_at=datetime(2026, 8, 21, 9, 25, tzinfo=NEW_YORK),
        d1_information_cutoff_at=cutoff,
        snapshots=snapshots,
        selection_count=1,
    )

    assert universe.members[0].symbol == "AA.A"


def test_plan_is_network_free_and_writes_no_evidence(tmp_path: Path) -> None:
    reference = _StaticReferenceClient(_reference_rows())
    builder = PointInTimeUniverseBuilder(root=tmp_path, reference_client=reference)

    plan = builder.plan(session_date=SESSION)

    assert plan["executed"] is False
    assert plan["reference_as_of"] == "2026-08-20"
    assert plan["network_request_count"] == 0
    assert reference.requests == []
    assert not list(tmp_path.rglob("*"))


def test_builder_refuses_a_capture_timestamp_before_d1_close(tmp_path: Path) -> None:
    builder = PointInTimeUniverseBuilder(
        root=tmp_path,
        reference_client=_StaticReferenceClient(_reference_rows()),
    )

    with pytest.raises(PointInTimeUniverseError, match="cannot precede the D-1 close"):
        builder.build_session(
            session_date=SESSION,
            captured_at=datetime(2026, 8, 20, 19, tzinfo=timezone.utc),
        )


def test_builder_is_deterministic_immutable_and_ignores_session_d(tmp_path: Path) -> None:
    ranking_dates = QUALIFICATION_RANKING_SESSION_DATES[SESSION]
    for ranking_date in ranking_dates:
        _write_minute_source(tmp_path, ranking_date)
    future_source = (
        tmp_path
        / "provider=massive"
        / "dataset=minute_aggregates"
        / f"session_date={SESSION.isoformat()}"
        / "source.csv.gz"
    )
    future_source.parent.mkdir(parents=True)
    future_source.write_bytes(b"this session-D file must never be opened")

    reference = _StaticReferenceClient(_reference_rows())
    builder = PointInTimeUniverseBuilder(root=tmp_path, reference_client=reference)
    captured_at = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)
    manifest_path = builder.build_session(
        session_date=SESSION,
        captured_at=captured_at,
    )
    original_bytes = manifest_path.read_bytes()
    payload, symbols = load_point_in_time_universe_manifest(
        manifest_path,
        expected_session_date=SESSION,
    )

    assert reference.requests == [date(2026, 8, 20)]
    assert len(symbols) == 61
    assert "S060" not in symbols
    assert "QQQ" in symbols
    assert payload["universe"]["rows"][-1]["role"] == "benchmark"
    assert payload["universe"]["rows"][-1]["rank"] is None
    assert payload["universe"]["rows"][0]["provider_type"] == "CS"
    assert payload["reference"]["request_count"] == 1
    assert [
        row["session_date"]
        for row in payload["ranking_inputs"]["parent_minute_aggregate_sources"]
    ] == [value.isoformat() for value in ranking_dates]
    assert payload["anti_lookahead"]["session_d_data_used"] is False

    future_source.write_bytes(b"changed future data remains irrelevant")
    assert builder.build_session(
        session_date=SESSION,
        captured_at=captured_at,
    ).read_bytes() == original_bytes

    with pytest.raises(PointInTimeUniverseError, match="immutable evidence already differs"):
        builder.build_session(
            session_date=SESSION,
            captured_at=datetime(2026, 8, 24, 13, tzinfo=timezone.utc),
        )


def test_manifest_loader_rejects_semantic_drift_even_with_a_new_self_hash(
    tmp_path: Path,
) -> None:
    for ranking_date in QUALIFICATION_RANKING_SESSION_DATES[SESSION]:
        _write_minute_source(tmp_path, ranking_date)
    builder = PointInTimeUniverseBuilder(
        root=tmp_path,
        reference_client=_StaticReferenceClient(_reference_rows()),
    )
    manifest_path = builder.build_session(
        session_date=SESSION,
        captured_at=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["selection_rule"]["minimum_d1_official_close_usd"] = 2.0
    canonical = {
        key: value for key, value in payload.items() if key != "payload_sha256"
    }
    payload["payload_sha256"] = hashlib.sha256(
        (json.dumps(
            canonical,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ) + "\n").encode()
    ).hexdigest()
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PointInTimeUniverseError, match="selection rule mismatch"):
        load_point_in_time_universe_manifest(
            manifest_path,
            expected_session_date=SESSION,
        )
