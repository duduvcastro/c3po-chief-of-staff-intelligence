from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from .market_data.http import JsonHttpClient, MarketDataRequestError
from .schemas import WeatherHour, WeatherLocation, WeatherResponse


FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


class WeatherRequestError(RuntimeError):
    pass


class WeatherLocationNotFound(WeatherRequestError):
    pass


@dataclass(frozen=True)
class LocationSpec:
    key: str
    label: str
    city: str
    region: str
    country: str
    latitude: float
    longitude: float
    fixed: bool = False


FIXED_LOCATIONS = (
    LocationSpec(
        key="leblon-rj",
        label="Leblon, Rio de Janeiro",
        city="Rio de Janeiro",
        region="RJ",
        country="Brasil",
        latitude=-22.9847,
        longitude=-43.2237,
        fixed=True,
    ),
    LocationSpec(
        key="campo-belo-sp",
        label="Campo Belo, São Paulo",
        city="São Paulo",
        region="SP",
        country="Brasil",
        latitude=-23.6260,
        longitude=-46.6694,
        fixed=True,
    ),
)


class WeatherService:
    def __init__(self, http: JsonHttpClient | None = None, *, cache_seconds: int = 300) -> None:
        self.http = http or JsonHttpClient(timeout=12, max_retries=1)
        self.cache_seconds = max(30, cache_seconds)
        self._cache: dict[str, tuple[datetime, WeatherLocation]] = {}
        self._lock = Lock()

    def snapshot(self, search: str | None = None) -> WeatherResponse:
        locations: list[WeatherLocation] = []
        errors: list[str] = []

        for spec in FIXED_LOCATIONS:
            try:
                locations.append(self._forecast(spec))
            except WeatherRequestError as exc:
                errors.append(f"{spec.label}: {exc}")

        normalized_search = " ".join((search or "").split()).strip()
        if normalized_search:
            try:
                searched_spec = self._geocode(normalized_search)
                locations.append(self._forecast(searched_spec))
            except WeatherLocationNotFound:
                raise
            except WeatherRequestError as exc:
                errors.append(f"{normalized_search}: {exc}")

        if not locations:
            raise WeatherRequestError("Weather data is currently unavailable")

        return WeatherResponse(
            generated_at=datetime.now(timezone.utc),
            refresh_seconds=self.cache_seconds,
            source="Open-Meteo multi-model forecast",
            searched_for=normalized_search or None,
            locations=locations,
            errors=errors,
        )

    def _geocode(self, query: str) -> LocationSpec:
        try:
            payload = self.http.get_json(
                GEOCODING_URL,
                params={"name": query, "count": 10, "language": "pt", "format": "json"},
                headers={"User-Agent": "C3PO-Chief-of-Staff/1.0"},
            )
        except MarketDataRequestError as exc:
            raise WeatherRequestError("location search is unavailable") from exc

        results = payload.get("results", []) if isinstance(payload, dict) else []
        if not results:
            raise WeatherLocationNotFound(f"No location found for '{query}'")

        item = results[0]
        name = str(item.get("name") or query)
        region = str(item.get("admin1") or item.get("admin2") or "")
        country = str(item.get("country") or "")
        latitude = self._number(item.get("latitude"))
        longitude = self._number(item.get("longitude"))
        if latitude is None or longitude is None:
            raise WeatherLocationNotFound(f"No coordinates found for '{query}'")

        label_parts = [name]
        if region and region.casefold() != name.casefold():
            label_parts.append(region)
        if country:
            label_parts.append(country)
        identifier = str(item.get("id") or f"{latitude:.4f}-{longitude:.4f}")
        return LocationSpec(
            key=f"search-{identifier}",
            label=", ".join(label_parts),
            city=name,
            region=region,
            country=country,
            latitude=latitude,
            longitude=longitude,
        )

    def _forecast(self, spec: LocationSpec) -> WeatherLocation:
        cached = self._cached(spec.key)
        if cached:
            return cached.model_copy(deep=True)

        params = {
            "latitude": spec.latitude,
            "longitude": spec.longitude,
            "timezone": "auto",
            "forecast_hours": 24,
            "current": (
                "temperature_2m,apparent_temperature,weather_code,"
                "wind_speed_10m,wind_direction_10m,precipitation"
            ),
            "hourly": (
                "temperature_2m,apparent_temperature,precipitation_probability,"
                "weather_code,wind_speed_10m,wind_direction_10m"
            ),
        }
        try:
            payload = self.http.get_json(
                FORECAST_URL,
                params=params,
                headers={"User-Agent": "C3PO-Chief-of-Staff/1.0"},
            )
        except MarketDataRequestError as exc:
            raise WeatherRequestError("forecast source is unavailable") from exc
        if not isinstance(payload, dict):
            raise WeatherRequestError("forecast response is invalid")

        current = payload.get("current") or {}
        hourly = payload.get("hourly") or {}
        hours = self._hours(hourly)
        if not hours:
            raise WeatherRequestError("hourly forecast is empty")

        wind_speed = self._number(current.get("wind_speed_10m"))
        wind_direction = self._number(current.get("wind_direction_10m"))
        weather_code = self._integer(current.get("weather_code"))
        result = WeatherLocation(
            key=spec.key,
            label=spec.label,
            city=spec.city,
            region=spec.region,
            country=spec.country,
            latitude=spec.latitude,
            longitude=spec.longitude,
            timezone=str(payload.get("timezone") or "auto"),
            fixed=spec.fixed,
            current_temperature_c=self._number(current.get("temperature_2m")),
            current_apparent_c=self._number(current.get("apparent_temperature")),
            current_weather_code=weather_code,
            current_condition=self._condition(weather_code),
            current_precipitation_mm=self._number(current.get("precipitation")),
            current_wind_kts=self._to_knots(wind_speed),
            current_wind_direction_deg=wind_direction,
            current_wind_direction=self._compass(wind_direction),
            as_of=str(current.get("time") or hours[0].time),
            hours=hours,
        )
        self._store(spec.key, result)
        return result.model_copy(deep=True)

    def _hours(self, hourly: dict[str, Any]) -> list[WeatherHour]:
        times = hourly.get("time") or []
        temperatures = hourly.get("temperature_2m") or []
        apparent = hourly.get("apparent_temperature") or []
        rain = hourly.get("precipitation_probability") or []
        codes = hourly.get("weather_code") or []
        wind_speeds = hourly.get("wind_speed_10m") or []
        wind_directions = hourly.get("wind_direction_10m") or []
        points: list[WeatherHour] = []
        for index, time_value in enumerate(times[:24]):
            wind_direction = self._indexed_number(wind_directions, index)
            code = self._indexed_integer(codes, index)
            points.append(
                WeatherHour(
                    time=str(time_value),
                    temperature_c=self._indexed_number(temperatures, index),
                    apparent_c=self._indexed_number(apparent, index),
                    rain_probability_percent=self._indexed_number(rain, index),
                    weather_code=code,
                    condition=self._condition(code),
                    wind_kts=self._to_knots(self._indexed_number(wind_speeds, index)),
                    wind_direction_deg=wind_direction,
                    wind_direction=self._compass(wind_direction),
                )
            )
        return points

    def _cached(self, key: str) -> WeatherLocation | None:
        now = datetime.now(timezone.utc)
        with self._lock:
            item = self._cache.get(key)
            if not item or now - item[0] > timedelta(seconds=self.cache_seconds):
                self._cache.pop(key, None)
                return None
            return item[1]

    def _store(self, key: str, value: WeatherLocation) -> None:
        with self._lock:
            self._cache[key] = (datetime.now(timezone.utc), value.model_copy(deep=True))

    @staticmethod
    def _indexed_number(values: list[Any], index: int) -> float | None:
        return WeatherService._number(values[index]) if index < len(values) else None

    @staticmethod
    def _indexed_integer(values: list[Any], index: int) -> int | None:
        return WeatherService._integer(values[index]) if index < len(values) else None

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _integer(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_knots(value_kmh: float | None) -> float | None:
        return round(value_kmh / 1.852, 1) if value_kmh is not None else None

    @staticmethod
    def _compass(degrees: float | None) -> str:
        if degrees is None:
            return "N/D"
        points = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
        return points[int((degrees % 360) / 22.5 + 0.5) % 16]

    @staticmethod
    def _condition(code: int | None) -> str:
        if code is None:
            return "Condição indisponível"
        if code == 0:
            return "Céu limpo"
        if code in {1, 2}:
            return "Parcialmente nublado"
        if code == 3:
            return "Nublado"
        if code in {45, 48}:
            return "Nevoeiro"
        if code in {51, 53, 55, 56, 57}:
            return "Garoa"
        if code in {61, 63, 65, 66, 67, 80, 81, 82}:
            return "Chuva"
        if code in {71, 73, 75, 77, 85, 86}:
            return "Neve"
        if code in {95, 96, 99}:
            return "Tempestade"
        return "Tempo variável"
