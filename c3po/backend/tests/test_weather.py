from __future__ import annotations

from typing import Any

from app.weather import FORECAST_URL, GEOCODING_URL, WeatherLocationNotFound, WeatherService


class FakeWeatherHttp:
    def __init__(self) -> None:
        self.forecast_calls = 0
        self.geocoding_queries: list[dict[str, Any]] = []

    def get_json(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
        del headers
        if url == GEOCODING_URL:
            self.geocoding_queries.append(params or {})
            if (params or {}).get("name") == "cidade inexistente":
                return {"results": []}
            if (params or {}).get("name") == "Miami, Florida, USA":
                return {
                    "results": [
                        {
                            "id": 4164138,
                            "name": "Miami",
                            "admin1": "Florida",
                            "country": "Estados Unidos",
                            "latitude": 25.7743,
                            "longitude": -80.1937,
                        }
                    ]
                }
            return {
                "results": [
                    {
                        "id": 3390760,
                        "name": "Recife",
                        "admin1": "Pernambuco",
                        "country": "Brasil",
                        "latitude": -8.05,
                        "longitude": -34.9,
                    }
                ]
            }
        assert url == FORECAST_URL
        self.forecast_calls += 1
        hours = [f"2026-08-14T{hour:02d}:00" for hour in range(24)]
        return {
            "timezone": "America/Sao_Paulo",
            "current": {
                "time": hours[0],
                "temperature_2m": 24.4,
                "apparent_temperature": 25.1,
                "weather_code": 2,
                "wind_speed_10m": 18.52,
                "wind_direction_10m": 90,
                "precipitation": 0,
            },
            "hourly": {
                "time": hours,
                "temperature_2m": [24 + index / 10 for index in range(24)],
                "apparent_temperature": [25 + index / 10 for index in range(24)],
                "precipitation_probability": [index for index in range(24)],
                "weather_code": [2] * 24,
                "wind_speed_10m": [18.52] * 24,
                "wind_direction_10m": [90] * 24,
            },
        }


def test_weather_snapshot_keeps_fixed_locations_and_adds_search() -> None:
    http = FakeWeatherHttp()
    service = WeatherService(http=http, cache_seconds=300)  # type: ignore[arg-type]

    payload = service.snapshot(search="Recife")

    assert [item.key for item in payload.locations[:2]] == ["leblon-rj", "campo-belo-sp"]
    assert payload.locations[2].label == "Recife, Pernambuco, Brasil"
    assert len(payload.locations[0].hours) == 24
    assert payload.locations[0].current_wind_kts == 10.0
    assert payload.locations[0].current_wind_direction == "E"
    assert payload.locations[0].hours[-1].rain_probability_percent == 23
    assert http.forecast_calls == 3

    service.snapshot()
    assert http.forecast_calls == 3


def test_weather_search_reports_unknown_location() -> None:
    service = WeatherService(http=FakeWeatherHttp())  # type: ignore[arg-type]

    try:
        service.snapshot(search="cidade inexistente")
    except WeatherLocationNotFound as exc:
        assert "cidade inexistente" in str(exc)
    else:
        raise AssertionError("Unknown locations must return a controlled error")


def test_weather_search_is_worldwide_and_keeps_the_full_query() -> None:
    http = FakeWeatherHttp()
    service = WeatherService(http=http)  # type: ignore[arg-type]

    payload = service.snapshot(search="Miami, Florida, USA")

    assert payload.locations[-1].label == "Miami, Florida, Estados Unidos"
    assert payload.locations[-1].country == "Estados Unidos"
    assert http.geocoding_queries[-1]["name"] == "Miami, Florida, USA"
    assert http.geocoding_queries[-1]["count"] == 10
    assert "countryCode" not in http.geocoding_queries[-1]
