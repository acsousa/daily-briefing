"""Open-Meteo daily forecast (no API key). Injectable fetcher for tests."""
from __future__ import annotations

import json

from .feeds import _http_get

# WMO weather interpretation codes -> short text
_WMO = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "freezing fog", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers",
    81: "rain showers", 82: "heavy showers", 95: "thunderstorms",
    96: "thunderstorms with hail", 99: "severe thunderstorms",
}


def get_forecast(latitude: float, longitude: float, fetcher=_http_get) -> dict | None:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
        "&temperature_unit=fahrenheit&timezone=auto&forecast_days=1"
    )
    data = json.loads(fetcher(url))
    daily = data.get("daily")
    if not daily or not daily.get("time"):
        return None
    return {
        "high_f": round(daily["temperature_2m_max"][0]),
        "low_f": round(daily["temperature_2m_min"][0]),
        "precip_pct": daily["precipitation_probability_max"][0],
        "conditions": _WMO.get(daily["weather_code"][0], "mixed conditions"),
    }
