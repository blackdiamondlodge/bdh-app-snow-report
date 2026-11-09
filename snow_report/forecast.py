"""5-day forecast for the village and the alpine from Open-Meteo (no API key)."""
import logging
from datetime import date

import requests
from django.core.cache import cache

log = logging.getLogger(__name__)

LATITUDE = 50.8838
LONGITUDE = -119.8902
ELEVATIONS = {"village": 1255, "alpine": 2080}  # m, Valley and Top of the World stations
DAYS = 5
URL = "https://api.open-meteo.com/v1/forecast"
CACHE_KEY = "snow_report:forecast"
CURRENT_CACHE_KEY = "snow_report:current"
CACHE_TTL = 30 * 60
DAILY = (
    "weather_code,temperature_2m_max,temperature_2m_min,snowfall_sum,"
    "precipitation_probability_max,uv_index_max,sunrise,sunset"
)

# WMO weather interpretation codes → (Font Awesome icon, label)
WMO = {
    0: ("fas fa-sun", "Clear"),
    1: ("fas fa-sun", "Mainly clear"),
    2: ("fas fa-cloud-sun", "Partly cloudy"),
    3: ("fas fa-cloud", "Overcast"),
    45: ("fas fa-smog", "Fog"),
    48: ("fas fa-smog", "Freezing fog"),
    51: ("fas fa-cloud-rain", "Light drizzle"),
    53: ("fas fa-cloud-rain", "Drizzle"),
    55: ("fas fa-cloud-rain", "Heavy drizzle"),
    56: ("fas fa-cloud-rain", "Freezing drizzle"),
    57: ("fas fa-cloud-rain", "Freezing drizzle"),
    61: ("fas fa-cloud-rain", "Light rain"),
    63: ("fas fa-cloud-showers-heavy", "Rain"),
    65: ("fas fa-cloud-showers-heavy", "Heavy rain"),
    66: ("fas fa-cloud-rain", "Freezing rain"),
    67: ("fas fa-cloud-showers-heavy", "Freezing rain"),
    71: ("fas fa-snowflake", "Light snow"),
    73: ("fas fa-snowflake", "Snow"),
    75: ("fas fa-snowflake", "Heavy snow"),
    77: ("fas fa-snowflake", "Snow grains"),
    80: ("fas fa-cloud-sun-rain", "Showers"),
    81: ("fas fa-cloud-showers-heavy", "Showers"),
    82: ("fas fa-cloud-showers-heavy", "Heavy showers"),
    85: ("fas fa-snowflake", "Snow showers"),
    86: ("fas fa-snowflake", "Heavy snow showers"),
    95: ("fas fa-bolt", "Thunderstorm"),
    96: ("fas fa-bolt", "Thunderstorm with hail"),
    99: ("fas fa-bolt", "Thunderstorm with hail"),
}

# Background animations for the Today card.
EFFECTS = ("sun", "stars", "partly", "clouds", "fog", "drizzle", "rain", "snow", "storm")


def weather_effect(code, is_day=True):
    """WMO weather code → Today-card background animation (one of EFFECTS)."""
    if code in (0, 1):
        return "sun" if is_day else "stars"
    if code == 2:
        return "partly" if is_day else "clouds"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 57:
        return "drizzle"
    if 61 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if 95 <= code <= 99:
        return "storm"
    return "clouds"


def describe(code):
    return WMO.get(code, ("fas fa-cloud", "—"))


def parse_forecast(payload):
    """Open-Meteo multi-location response (village first, alpine second) → list of days."""
    village, alpine = payload[0]["daily"], payload[1]["daily"]
    days = []
    for i, day in enumerate(village["time"][:DAYS]):
        icon, label = describe(village["weather_code"][i])
        days.append({
            "date": date.fromisoformat(day),
            "code": village["weather_code"][i],
            "icon": icon,
            "label": label,
            "high_c": village["temperature_2m_max"][i],
            "low_c": village["temperature_2m_min"][i],
            "alpine_high_c": alpine["temperature_2m_max"][i],
            "alpine_low_c": alpine["temperature_2m_min"][i],
            "alpine_snow_cm": alpine["snowfall_sum"][i],
            "precip_chance": village["precipitation_probability_max"][i],
            "uv": village["uv_index_max"][i],
            "sunrise": village["sunrise"][i][-5:],
            "sunset": village["sunset"][i][-5:],
        })
    return days


def get_forecast():
    """Forecast days (cached), or None if Open-Meteo can't be reached."""
    days = cache.get(CACHE_KEY)
    if days is None:
        names = list(ELEVATIONS)
        params = {
            "latitude": ",".join([str(LATITUDE)] * len(names)),
            "longitude": ",".join([str(LONGITUDE)] * len(names)),
            "elevation": ",".join(str(ELEVATIONS[n]) for n in names),
            "daily": DAILY,
            "current": "weather_code,is_day",
            "timezone": "America/Vancouver",
            "forecast_days": DAYS,
        }
        try:
            response = requests.get(URL, params=params, timeout=15)
            response.raise_for_status()
            payload = response.json()
            days = parse_forecast(payload)
        except Exception:
            log.exception("Open-Meteo forecast unavailable")
            return None
        cache.set(CACHE_KEY, days, CACHE_TTL)
        current = payload[0].get("current") or {}
        if current.get("weather_code") is not None:
            cache.set(CURRENT_CACHE_KEY, {"code": current["weather_code"], "is_day": bool(current.get("is_day", 1))},
                      CACHE_TTL)
    return days


def get_current():
    """Village current conditions ({code, is_day}) from the last forecast fetch, or None."""
    return cache.get(CURRENT_CACHE_KEY)