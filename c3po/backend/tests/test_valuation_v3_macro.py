from datetime import date

import pytest

from app.config import get_settings
from app.database import Database
from app.valuation_v3_macro import (
    SELIC_ANALYSIS_TYPE,
    SELIC_ENTITY_KEY,
    US_CURVE_ANALYSIS_TYPE,
    US_CURVE_ENTITY_KEY,
    ValuationV3MacroDataError,
    ValuationV3MacroService,
    canonical_payload_sha256,
    interpolate_us_five_year_rate,
    package_hash_is_valid,
    validate_us_curve_package,
)


AS_OF = date(2026, 8, 23)


class FakeMacroHttp:
    def __init__(self, *, mismatched_curve: bool = False) -> None:
        self.mismatched_curve = mismatched_curve
        self.calls: list[tuple[str, dict]] = []

    def get_json(self, url: str, *, params=None, **_kwargs):
        self.calls.append((url, dict(params or {})))
        if "api.bcb.gov.br" in url:
            return [
                {"data": "21/08/2026", "valor": "14.25"},
                {"data": "22/08/2026", "valor": "14.25"},
                {"data": "24/08/2026", "valor": "99.00"},
            ]
        if "US3Y.GBOND" in url:
            return [{"date": "2026-08-21", "close": 4.0}]
        if "US10Y.GBOND" in url:
            return [{
                "date": "2026-08-20" if self.mismatched_curve else "2026-08-21",
                "close": 5.0,
            }]
        raise AssertionError(url)


def _service(http: FakeMacroHttp, database: Database | None = None):
    settings = get_settings().model_copy(update={"eodhd_api_token": "token"})
    return ValuationV3MacroService(
        settings,
        database or Database(settings),
        http,  # type: ignore[arg-type]
    )


def test_selic_refresh_is_chunked_hashed_and_persisted_without_future_rows():
    http = FakeMacroHttp()
    service = _service(http)

    package = service.refresh_selic(as_of=AS_OF)

    bcb_calls = [call for call in http.calls if "api.bcb.gov.br" in call[0]]
    assert len(bcb_calls) >= 3
    assert package_hash_is_valid(package)
    assert [row["observation_date"] for row in package["observations"]] == [
        "2026-08-21",
        "2026-08-22",
    ]
    assert package["observations"][0]["annual_rate"] == 0.1425
    stored = service.database.latest_analysis_snapshot(SELIC_ANALYSIS_TYPE, SELIC_ENTITY_KEY)
    assert stored is not None
    assert stored["outputs"]["payload_sha256"] == package["payload_sha256"]


def test_us_curve_uses_same_date_and_exact_two_sevenths_interpolation():
    service = _service(FakeMacroHttp())

    package = service.refresh_us_curve(as_of=AS_OF)

    expected = 0.04 + (2 / 7) * (0.05 - 0.04)
    assert interpolate_us_five_year_rate(0.04, 0.05) == expected
    assert validate_us_curve_package(package, as_of=AS_OF) == expected
    assert package["interpolated_5y_rate"] == expected
    stored = service.database.latest_analysis_snapshot(
        US_CURVE_ANALYSIS_TYPE, US_CURVE_ENTITY_KEY
    )
    assert stored is not None
    assert stored["outputs"]["payload_sha256"] == package["payload_sha256"]


def test_curve_failure_preserves_the_previous_snapshot():
    settings = get_settings().model_copy(update={"eodhd_api_token": "token"})
    database = Database(settings)
    good = ValuationV3MacroService(settings, database, FakeMacroHttp())  # type: ignore[arg-type]
    original = good.refresh_us_curve(as_of=AS_OF)
    bad = ValuationV3MacroService(
        settings, database, FakeMacroHttp(mismatched_curve=True)  # type: ignore[arg-type]
    )

    with pytest.raises(ValuationV3MacroDataError, match="different dates"):
        bad.refresh_us_curve(as_of=AS_OF)

    stored = database.latest_analysis_snapshot(US_CURVE_ANALYSIS_TYPE, US_CURVE_ENTITY_KEY)
    assert stored is not None
    assert stored["outputs"]["payload_sha256"] == original["payload_sha256"]


def test_curve_validation_rejects_future_missing_and_tampered_inputs():
    package = _service(FakeMacroHttp()).refresh_us_curve(as_of=AS_OF)

    future = {**package, "as_of": "2026-08-20"}
    future["payload_sha256"] = canonical_payload_sha256(future)
    with pytest.raises(ValuationV3MacroDataError, match="future"):
        validate_us_curve_package(future, as_of=date(2026, 8, 20))

    missing = {**package, "points": package["points"][:1]}
    missing["payload_sha256"] = canonical_payload_sha256(missing)
    with pytest.raises(ValuationV3MacroDataError, match="exactly 3Y and 10Y"):
        validate_us_curve_package(missing, as_of=AS_OF)

    tampered = {**package, "interpolated_5y_rate": 0.99}
    assert not package_hash_is_valid(tampered)
    with pytest.raises(ValuationV3MacroDataError, match="hash mismatch"):
        validate_us_curve_package(tampered, as_of=AS_OF)

    tampered_fetch_time = {**package, "fetched_at": "2026-08-24T00:00:00+00:00"}
    assert not package_hash_is_valid(tampered_fetch_time)


def test_curve_validation_rejects_duplicate_or_ambiguous_tenors():
    package = _service(FakeMacroHttp()).refresh_us_curve(as_of=AS_OF)
    duplicate = {
        **package,
        "points": [package["points"][0], {**package["points"][1], "tenor_years": 3}],
    }
    duplicate["payload_sha256"] = canonical_payload_sha256(duplicate)
    ambiguous = {
        **package,
        "points": [{**package["points"][0], "tenor_years": 3.5}, package["points"][1]],
    }
    ambiguous["payload_sha256"] = canonical_payload_sha256(ambiguous)

    for candidate in (duplicate, ambiguous):
        with pytest.raises(ValuationV3MacroDataError, match="exactly 3Y and 10Y"):
            validate_us_curve_package(candidate, as_of=AS_OF)
