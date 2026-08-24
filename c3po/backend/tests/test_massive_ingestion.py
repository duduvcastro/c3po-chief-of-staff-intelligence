from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from app.day_d_replay.massive_ingestion import (
    MassiveIngestionError,
    MassiveR1Normalizer,
    RowDisposition,
)
from app.day_d_replay.point_in_time_universe import (
    MANIFEST_SCHEMA_VERSION,
    RANKING_INPUT_SCHEMA_VERSION,
    REFERENCE_ENDPOINT,
    REFERENCE_POLICY_VERSION,
    UNIVERSE_POLICY_VERSION,
    PointInTimeUniverseBuilder,
)
from app.day_d_replay.qualification_scope import (
    QUALIFICATION_CALENDAR_PATH,
    QUALIFICATION_CALENDAR_VERSION,
    QUALIFICATION_PREVIOUS_SESSION_DATES,
    QUALIFICATION_RANKING_SESSION_DATES,
)


SESSION = date(2026, 8, 21)
OPEN = datetime(2026, 8, 21, 13, 30, tzinfo=timezone.utc)
CLOSE = datetime(2026, 8, 21, 20, 0, tzinfo=timezone.utc)


def _ns(value: datetime) -> int:
    return int(value.timestamp() * 1_000_000_000)


def _trade(**overrides) -> dict[str, object]:
    row: dict[str, object] = {
        "ticker": "AAPL",
        "participant_timestamp": _ns(datetime(2026, 8, 21, 14, tzinfo=timezone.utc)),
        "sip_timestamp": _ns(datetime(2026, 8, 21, 14, tzinfo=timezone.utc)) + 1_000,
        "sequence_number": 10,
        "exchange": 11,
        "price": 225.5,
        "size": 100,
        "conditions": "[12]",
    }
    row.update(overrides)
    return row


def _quote(**overrides) -> dict[str, object]:
    row: dict[str, object] = {
        "ticker": "AAPL",
        "participant_timestamp": _ns(datetime(2026, 8, 21, 14, tzinfo=timezone.utc)),
        "sip_timestamp": _ns(datetime(2026, 8, 21, 14, tzinfo=timezone.utc)) + 1_000,
        "sequence_number": 10,
        "bid_price": 225.4,
        "ask_price": 225.6,
        "bid_size": 2,
        "ask_size": 3,
        "bid_exchange": 11,
        "ask_exchange": 12,
    }
    row.update(overrides)
    return row


def _csv(path: Path, rows: list[dict[str, object]]) -> None:
    columns = sorted({key for row in rows for key in row})
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(str(row.get(column, "")) for column in columns))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _normalizer(*, permissive: bool = False) -> MassiveR1Normalizer:
    normalizer = MassiveR1Normalizer()
    if permissive:
        normalizer.quality_thresholds = {"trades": 1.0, "quotes": 1.0}
    return normalizer


def _canonical(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _universe_manifest(tmp_path: Path, *, primary_symbol: str = "AAPL") -> Path:
    root = tmp_path / "day-d-data"
    previous = QUALIFICATION_PREVIOUS_SESSION_DATES[SESSION]
    page = (
        root
        / "provider=massive"
        / "reference-tickers"
        / f"as_of={previous.isoformat()}"
        / "page-0001.json"
    )
    page.parent.mkdir(parents=True)
    page.write_bytes(_canonical({"results": [], "status": "OK"}))
    ranking = (
        root
        / "provider=massive"
        / "universe-ranking-inputs"
        / f"session_date={SESSION.isoformat()}"
        / "ranking-inputs.ndjson"
    )
    ranking.parent.mkdir(parents=True)
    ranking.write_bytes(b"{}\n")

    tradeable_symbols = [primary_symbol, *(f"T{index:03d}" for index in range(59))]
    rows = [
        {
            "role": "tradeable",
            "benchmark": False,
            "rank": index,
            "symbol": symbol,
        }
        for index, symbol in enumerate(tradeable_symbols, start=1)
    ]
    rows.append({
        "role": "benchmark",
        "benchmark": True,
        "rank": None,
        "symbol": "QQQ",
    })
    relative_page = page.relative_to(root)
    relative_ranking = ranking.relative_to(root)
    payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "policy_version": UNIVERSE_POLICY_VERSION,
        "reference_policy_version": REFERENCE_POLICY_VERSION,
        "session_date": SESSION.isoformat(),
        "previous_session_date": previous.isoformat(),
        "calendar": {
            "version": QUALIFICATION_CALENDAR_VERSION,
            "contract_sha256": _sha256(QUALIFICATION_CALENDAR_PATH),
            "ranking_session_dates": [
                value.isoformat()
                for value in QUALIFICATION_RANKING_SESSION_DATES[SESSION]
            ],
        },
        "reference": {
            "provider": "Massive",
            "endpoint": REFERENCE_ENDPOINT,
            "query": PointInTimeUniverseBuilder._reference_query(previous),
            "request_count": 1,
            "pages": [{
                "page_number": 1,
                "path": str(relative_page),
                "bytes": page.stat().st_size,
                "sha256": _sha256(page),
            }],
        },
        "selection_rule": PointInTimeUniverseBuilder.selection_rule(),
        "ranking_inputs": {
            "schema_version": RANKING_INPUT_SCHEMA_VERSION,
            "path": str(relative_ranking),
            "bytes": ranking.stat().st_size,
            "sha256": _sha256(ranking),
            "parent_minute_aggregate_sources": [
                {"session_date": value.isoformat()}
                for value in QUALIFICATION_RANKING_SESSION_DATES[SESSION]
            ],
        },
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
    }
    payload["payload_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    manifest = (
        root
        / "provider=massive"
        / "universe-manifests"
        / f"session_date={SESSION.isoformat()}"
        / "universe.json"
    )
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def test_r1_accounts_every_trade_as_emitted_dropped_or_filtered(tmp_path: Path) -> None:
    raw = tmp_path / "trades.csv"
    valid = _trade()
    duplicate = dict(valid)
    negative = _trade(sequence_number=11, price=-1)
    outside_symbol = _trade(sequence_number=12, ticker="MSFT")
    premarket = _trade(
        sequence_number=13,
        participant_timestamp=_ns(datetime(2026, 8, 21, 12, tzinfo=timezone.utc)),
        sip_timestamp=_ns(datetime(2026, 8, 21, 12, tzinfo=timezone.utc)) + 1_000,
    )
    _csv(raw, [valid, duplicate, negative, outside_symbol, premarket])
    output = tmp_path / "normalized.ndjson"

    manifest_path = _normalizer(permissive=True).normalize_file(
        raw_path=raw,
        output_path=output,
        dataset="trades",
        session_date=SESSION,
        regular_open=OPEN,
        regular_close=CLOSE,
        universe_manifest_path=_universe_manifest(tmp_path),
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counters = manifest["counters"]
    assert counters["raw_rows_seen"] == 5
    assert counters["emitted_rows"] == 1
    assert counters["dropped_rows"] == 2
    assert counters["filtered_rows"] == 2
    assert counters["drop_reasons"]["duplicate_exact"] == 1
    assert counters["drop_reasons"]["nonpositive_price"] == 1
    assert counters["filter_reasons"]["symbol_not_in_scope"] == 1
    assert counters["filter_reasons"]["out_of_session_window"] == 1
    samples = manifest["discard_samples_first_100_per_reason"]
    assert len(samples["symbol_not_in_scope"]) == 1
    assert len(samples["out_of_session_window"]) == 1
    assert counters["clamped_rows"] == counters["imputed_rows"] == 0
    assert manifest["identity"]["passed"] is True
    assert len(output.read_text(encoding="utf-8").splitlines()) == 1


def test_r1_scope_matches_provider_symbols_case_sensitively(tmp_path: Path) -> None:
    raw = tmp_path / "trades.csv"
    _csv(raw, [
        _trade(ticker="ALPA", sequence_number=10),
        _trade(ticker="ALpA", sequence_number=11),
    ])
    output = tmp_path / "normalized.ndjson"

    manifest_path = _normalizer(permissive=True).normalize_file(
        raw_path=raw,
        output_path=output,
        dataset="trades",
        session_date=SESSION,
        regular_open=OPEN,
        regular_close=CLOSE,
        universe_manifest_path=_universe_manifest(tmp_path, primary_symbol="ALPA"),
    )

    emitted = json.loads(output.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert emitted["symbol"] == "ALPA"
    assert manifest["counters"]["emitted_rows"] == 1
    assert manifest["counters"]["filtered_rows"] == 1
    assert manifest["counters"]["filter_reasons"]["symbol_not_in_scope"] == 1


def test_r1_preserves_legitimate_one_sided_quote_and_drops_crossed_bbo(tmp_path: Path) -> None:
    raw = tmp_path / "quotes.csv"
    one_sided = _quote(ask_price=0, ask_size=0)
    crossed = _quote(sequence_number=11, bid_price=226, ask_price=225)
    _csv(raw, [one_sided, crossed])
    output = tmp_path / "quotes.ndjson"

    manifest_path = _normalizer(permissive=True).normalize_file(
        raw_path=raw,
        output_path=output,
        dataset="quotes",
        session_date=SESSION,
        regular_open=OPEN,
        regular_close=CLOSE,
        universe_manifest_path=_universe_manifest(tmp_path),
    )

    emitted = json.loads(output.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert emitted["bid"] == 225.4
    assert emitted["ask"] is None
    assert manifest["counters"]["drop_reasons"]["crossed_or_invalid_bbo"] == 1


def test_r1_does_not_dedupe_distinct_sequences_and_rejects_empty_bbo(tmp_path: Path) -> None:
    universe_manifest = _universe_manifest(tmp_path)
    trades = tmp_path / "trades.csv"
    _csv(trades, [_trade(sequence_number=10), _trade(sequence_number=11)])
    trade_output = tmp_path / "trades.ndjson"
    _normalizer(permissive=True).normalize_file(
        raw_path=trades,
        output_path=trade_output,
        dataset="trades",
        session_date=SESSION,
        regular_open=OPEN,
        regular_close=CLOSE,
        universe_manifest_path=universe_manifest,
    )

    quotes = tmp_path / "quotes.csv"
    _csv(quotes, [_quote(bid_size=0, ask_size=0)])
    quote_output = tmp_path / "quotes.ndjson"
    manifest_path = _normalizer(permissive=True).normalize_file(
        raw_path=quotes,
        output_path=quote_output,
        dataset="quotes",
        session_date=SESSION,
        regular_open=OPEN,
        regular_close=CLOSE,
        universe_manifest_path=universe_manifest,
    )

    assert len(trade_output.read_text(encoding="utf-8").splitlines()) == 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["counters"]["drop_reasons"]["duplicate_exact"] == 0
    assert manifest["counters"]["drop_reasons"]["crossed_or_invalid_bbo"] == 1


def test_r1_quality_threshold_quarantines_file_and_emits_no_dataset(tmp_path: Path) -> None:
    raw = tmp_path / "trades.csv"
    _csv(raw, [_trade(), _trade(sequence_number=11, price=-1)])
    output = tmp_path / "normalized.ndjson"

    with pytest.raises(MassiveIngestionError, match="quality threshold exceeded"):
        MassiveR1Normalizer().normalize_file(
            raw_path=raw,
            output_path=output,
            dataset="trades",
            session_date=SESSION,
            regular_open=OPEN,
            regular_close=CLOSE,
            universe_manifest_path=_universe_manifest(tmp_path),
        )

    assert not output.exists()
    assert not output.with_name("normalized.ndjson.manifest.json").exists()
    reports = list((tmp_path / "quarantine").glob("*.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["normalized_artifact_emitted"] is False
    assert report["reason"] == "quality_drop_rate_exceeded"


def test_r1_unknown_terminal_outcome_fails_closed_and_is_quarantined(tmp_path: Path) -> None:
    class BrokenNormalizer(MassiveR1Normalizer):
        def _classify(self, **_kwargs):  # noqa: ANN202
            return RowDisposition("unknown")

    raw = tmp_path / "trades.csv"
    _csv(raw, [_trade()])
    output = tmp_path / "normalized.ndjson"

    with pytest.raises(MassiveIngestionError, match="unknown terminal outcome"):
        BrokenNormalizer().normalize_file(
            raw_path=raw,
            output_path=output,
            dataset="trades",
            session_date=SESSION,
            regular_open=OPEN,
            regular_close=CLOSE,
            universe_manifest_path=_universe_manifest(tmp_path),
        )

    assert not output.exists()
    report = json.loads(next((tmp_path / "quarantine").glob("*.json")).read_text())
    assert report["reason"] == "normalization_failure"


def test_r1_keeps_at_most_first_100_samples_per_quality_reason(tmp_path: Path) -> None:
    raw = tmp_path / "trades.csv"
    rows = [_trade(sequence_number=index + 1, price=-1) for index in range(105)]
    _csv(raw, rows)
    output = tmp_path / "normalized.ndjson"

    manifest_path = _normalizer(permissive=True).normalize_file(
        raw_path=raw,
        output_path=output,
        dataset="trades",
        session_date=SESSION,
        regular_open=OPEN,
        regular_close=CLOSE,
        universe_manifest_path=_universe_manifest(tmp_path),
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["discard_samples_first_100_per_reason"]["nonpositive_price"]) == 100


def test_r1_session_manifest_reconciles_file_manifests(tmp_path: Path) -> None:
    normalizer = _normalizer(permissive=True)
    universe_manifest = _universe_manifest(tmp_path)
    manifests = []
    for dataset, row in (("trades", _trade()), ("quotes", _quote())):
        raw = tmp_path / f"{dataset}.csv"
        _csv(raw, [row])
        manifests.append(normalizer.normalize_file(
            raw_path=raw,
            output_path=tmp_path / f"{dataset}.ndjson",
            dataset=dataset,
            session_date=SESSION,
            regular_open=OPEN,
            regular_close=CLOSE,
            universe_manifest_path=universe_manifest,
        ))

    session_path = normalizer.aggregate_session(
        manifest_paths=(path for path in manifests),
        output_path=tmp_path / "session-manifest.json",
    )

    payload = json.loads(session_path.read_text(encoding="utf-8"))
    assert payload["counters"]["raw_rows_seen"] == 2
    assert payload["counters"]["emitted_rows"] == 2
    assert payload["identity"]["passed"] is True
    assert payload["file_manifests"] == [str(path) for path in manifests]
    assert set(payload["quality_by_dataset"]) == {"trades", "quotes"}
    assert payload["quality_by_dataset"]["trades"]["passed"] is True
    assert "duplicate_exact" in payload["discard_samples_first_100_per_reason"]
    assert payload["point_in_time_universe"]["symbol_count"] == 61


def test_r1_refuses_to_run_without_a_hash_bound_universe(tmp_path: Path) -> None:
    raw = tmp_path / "trades.csv"
    _csv(raw, [_trade()])
    output = tmp_path / "normalized.ndjson"

    with pytest.raises(MassiveIngestionError, match="requires a hash-bound"):
        _normalizer(permissive=True).normalize_file(
            raw_path=raw,
            output_path=output,
            dataset="trades",
            session_date=SESSION,
            regular_open=OPEN,
            regular_close=CLOSE,
            universe_manifest_path=None,
        )

    assert not output.exists()


def test_r1_refuses_a_tampered_universe_manifest(tmp_path: Path) -> None:
    universe_manifest = _universe_manifest(tmp_path)
    payload = json.loads(universe_manifest.read_text(encoding="utf-8"))
    payload["universe"]["rows"][0]["symbol"] = "MSFT"
    universe_manifest.write_text(json.dumps(payload), encoding="utf-8")
    raw = tmp_path / "trades.csv"
    _csv(raw, [_trade()])

    with pytest.raises(MassiveIngestionError, match="payload checksum mismatch"):
        _normalizer(permissive=True).normalize_file(
            raw_path=raw,
            output_path=tmp_path / "normalized.ndjson",
            dataset="trades",
            session_date=SESSION,
            regular_open=OPEN,
            regular_close=CLOSE,
            universe_manifest_path=universe_manifest,
        )
