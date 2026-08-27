from datetime import date, datetime, timezone
import traceback
from urllib.parse import urlencode

import pytest

from app.market_data.massive import MassiveClient, MassiveResponseError
from app.market_data.http import MarketDataRequestError


class FakeHttp:
    def __init__(self, payloads: list[object]) -> None:
        self.payloads = list(payloads)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_json(self, url: str, *, params: dict[str, object]) -> object:
        self.calls.append((url, params))
        return self.payloads.pop(0)


def test_massive_trades_preserve_participant_and_sip_timestamps_across_pages() -> None:
    http = FakeHttp([
        {
            "results": [{
                "id": "t1",
                "participant_timestamp": 1_517_562_000_015_577_000,
                "sip_timestamp": 1_517_562_000_016_036_600,
                "price": 171.55,
                "decimal_size": "100.5",
                "exchange": 11,
                "sequence_number": 1063,
                "conditions": [12, 41],
                "tape": 3,
            }],
            "next_url": "https://api.massive.com/v3/trades/AAPL?cursor=next",
        },
        {
            "results": [{
                "id": "t2",
                "participant_timestamp": 1_517_562_000_015_577_600,
                "sip_timestamp": 1_517_562_000_016_038_100,
                "price": 171.56,
                "size": 50,
            }],
        },
    ])
    client = MassiveClient(
        "https://api.massive.com",
        "secret-token",
        http,  # type: ignore[arg-type]
        historical_access_authorized=True,
    )

    trades = list(client.iter_trades("aapl", session_date=date(2018, 2, 2)))

    assert [trade["trade_id"] for trade in trades] == ["t1", "t2"]
    assert trades[0]["symbol"] == "AAPL"
    assert trades[0]["size"] == 100.5
    assert trades[0]["event_at"] == datetime.fromtimestamp(
        1_517_562_000_015_577_000 / 1_000_000_000,
        tz=timezone.utc,
    )
    assert trades[0]["available_at"] > trades[0]["event_at"]
    assert http.calls[0][1] == {
        "timestamp": "2018-02-02",
        "order": "asc",
        "sort": "timestamp",
        "limit": 50_000,
        "apiKey": "secret-token",
    }
    assert http.calls[1] == (
        "https://api.massive.com/v3/trades/AAPL?cursor=next",
        {"apiKey": "secret-token"},
    )


def test_massive_bounded_trade_window_preserves_raw_rows() -> None:
    raw = {
        "id": "t1",
        "participant_timestamp": 1_777_300_800_000_000_000,
        "sip_timestamp": 1_777_300_800_001_000_000,
        "price": 100.0,
        "size": 2,
        "conditions": [2],
    }
    http = FakeHttp([{"results": [raw]}])
    client = MassiveClient(
        "https://api.massive.com",
        "secret-token",
        http,  # type: ignore[arg-type]
        historical_access_authorized=True,
    )
    start = datetime(2026, 4, 28, 14, 0, tzinfo=timezone.utc)
    end = datetime(2026, 4, 28, 14, 10, tzinfo=timezone.utc)

    assert list(client.iter_raw_trades_between("AAPL", start_at=start, end_at=end)) == [raw]
    assert http.calls == [(
        "https://api.massive.com/v3/trades/AAPL",
        {
            "timestamp.gte": 1_777_384_800_000_000_000,
            "timestamp.lt": 1_777_385_400_000_000_000,
            "order": "asc",
            "sort": "timestamp",
            "limit": 50_000,
            "apiKey": "secret-token",
        },
    )]


def test_massive_trade_conditions_use_stocks_trade_filter() -> None:
    payload = {
        "id": 2,
        "asset_class": "stocks",
        "data_types": ["trade"],
        "update_rules": {"consolidated": {"updates_high_low": False}},
    }
    http = FakeHttp([{"results": [payload]}])
    client = MassiveClient(
        "https://api.massive.com",
        "secret-token",
        http,  # type: ignore[arg-type]
        historical_access_authorized=True,
    )

    assert client.trade_conditions() == [payload]
    assert http.calls == [(
        "https://api.massive.com/v3/reference/conditions",
        {
            "asset_class": "stocks",
            "data_type": "trade",
            "order": "asc",
            "sort": "id",
            "limit": 1_000,
            "apiKey": "secret-token",
        },
    )]


def test_massive_quotes_drop_incomplete_or_noncausal_bbo_rows() -> None:
    http = FakeHttp([{
        "results": [
            {
                "sequence_number": 1,
                "participant_timestamp": 1_517_562_000_015_000_000,
                "sip_timestamp": 1_517_562_000_016_000_000,
                "bid_price": 170.0,
                "ask_price": 170.1,
                "bid_size": 2,
                "ask_size": 3,
            },
            {
                "sequence_number": 2,
                "participant_timestamp": 1_517_562_000_015_000_000,
                "sip_timestamp": 1_517_562_000_016_000_000,
                "bid_price": 170.0,
                "ask_price": 0,
                "bid_size": 2,
                "ask_size": 0,
            },
            {
                "sequence_number": 3,
                "participant_timestamp": 1_517_562_000_017_000_000,
                "sip_timestamp": 1_517_562_000_016_000_000,
                "bid_price": 170.0,
                "ask_price": 170.1,
                "bid_size": 2,
                "ask_size": 3,
            },
        ],
    }])
    client = MassiveClient(
        "https://api.massive.com",
        "token",
        http,  # type: ignore[arg-type]
        historical_access_authorized=True,
    )

    quotes = list(client.iter_quotes("AAPL", session_date=date(2018, 2, 2)))

    assert len(quotes) == 1
    assert quotes[0]["quote_id"] == "1"
    assert quotes[0]["bid"] == 170.0
    assert quotes[0]["ask"] == 170.1


def test_massive_pagination_cannot_leave_configured_origin() -> None:
    client = MassiveClient(
        "https://api.massive.com",
        "token",
        FakeHttp([{"results": [], "next_url": "https://attacker.invalid/steal"}]),  # type: ignore[arg-type]
        historical_access_authorized=True,
    )

    with pytest.raises(MassiveResponseError, match="leave the configured origin"):
        list(client.iter_trades("AAPL", session_date=date(2026, 8, 21)))


def test_massive_rejects_unconfigured_token_and_unsafe_symbol() -> None:
    client = MassiveClient(
        "https://api.massive.com",
        "",
        FakeHttp([]),  # type: ignore[arg-type]
        historical_access_authorized=True,
    )

    with pytest.raises(ValueError, match="not configured"):
        list(client.iter_trades("AAPL", session_date=date(2026, 8, 21)))
    with pytest.raises(ValueError, match="invalid Massive stock symbol"):
        list(client.iter_trades("../AAPL", session_date=date(2026, 8, 21)))


def test_massive_redacts_api_key_from_rest_error_and_traceback() -> None:
    token = "massive/secret+token"

    class FailingHttp:
        def get_json(self, url: str, *, params: dict[str, object]) -> object:
            raise MarketDataRequestError(
                f"403 for {url}?{urlencode(params)}&cursor=next"
            )

    client = MassiveClient(
        "https://api.massive.com",
        token,
        FailingHttp(),  # type: ignore[arg-type]
        historical_access_authorized=True,
    )

    with pytest.raises(MassiveResponseError) as captured:
        list(client.iter_trades("AAPL", session_date=date(2026, 8, 21)))

    rendered_traceback = "".join(traceback.format_exception(captured.value))
    assert token not in str(captured.value)
    assert "massive%2Fsecret%2Btoken" not in str(captured.value)
    assert token not in rendered_traceback
    assert "[REDACTED]" in str(captured.value)


def test_massive_historical_rest_is_blocked_by_default() -> None:
    client = MassiveClient(
        "https://api.massive.com",
        "token",
        FakeHttp([]),  # type: ignore[arg-type]
    )

    with pytest.raises(MassiveResponseError, match="historical REST access is disabled"):
        list(client.iter_trades("AAPL", session_date=date(2026, 8, 21)))
