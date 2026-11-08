"""Sun Peaks resort conditions page: scraped into plain metric numbers.

In season the page has today's narrative, new snow and snow base. Off season
Sun Peaks removes those and only temperatures, air quality and wind remain.
"""
import logging
import re

import requests
from bs4 import BeautifulSoup
from django.core.cache import cache

log = logging.getLogger(__name__)

SNOW_REPORT_URL = "https://www.sunpeaksresort.com/ski-ride/weather-conditions-cams/weather-snow-report"
CACHE_KEY = "snow_report:resort"
CACHE_TTL = 10 * 60

ICONS = {
    "icon-sunny_clear_skies": "fas fa-sun",
    "icon-partly_cloudy": "fas fa-cloud-sun",
    "icon-mainly_cloudy": "fas fa-cloud",
    "icon-cloudy": "fas fa-cloud",
    "icon-overcast": "fas fa-cloud",
    "icon-light_rain_showers": "fas fa-cloud-rain",
    "icon-rain_showers": "fas fa-cloud-rain",
    "icon-snow_showers": "fas fa-snowflake",
    "icon-light_snow": "fas fa-snowflake",
    "icon-snow_flurries": "fas fa-snowflake",
    "icon-mixed_snow": "fas fa-snowflake",
    "icon-snow": "fas fa-snowflake",
    "icon-heavy_snow": "fas fa-snowflake",
    "icon-thunderstorm": "fas fa-bolt",
    "icon-fog": "fas fa-smog",
    "icon-clear_skies_night": "fas fa-moon",
    "icon-partly_cloudy_night": "fas fa-cloud-moon",
    "icon-mainly_cloudy_night": "fas fa-cloud-moon",
    "icon-cloudy_night": "fas fa-cloud-moon",
    "icon-snow_flurries_night": "fas fa-snowflake",
    "icon-mixed_snow_night": "fas fa-snowflake",
}


def sanitize_number(value):
    """Clean malformed numeric strings from the source website (e.g. '--7' → -7, 'N/A' → None)."""
    if value is None:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", str(value))
    cleaned = re.sub(r"-+", "-", cleaned)
    if not cleaned or cleaned == "-":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _text(el):
    return el.get_text(" ", strip=True) if el else ""


def _station(li):
    """Name and elevation (m) from the first cell of a station <li>/<div>."""
    name = _text(li.find("h3"))
    elevation = sanitize_number(_text(li.select_one(".value_m")))
    return name, elevation


def parse_resort_html(html):
    soup = BeautifulSoup(html, "html.parser")

    narrative = icon = None
    current = soup.find("div", class_="current-condition")
    if current:
        narrative = _text(current.find("p", class_="today-description")) or None
        span = current.find("span", class_="icon")
        icon = next((ICONS[c] for c in (span.get("class", []) if span else []) if c in ICONS), None)

    updated = None
    snow_section = soup.select_one("#snow-conditions")
    if snow_section:
        stamp = snow_section.find("p", string=re.compile(r"^\s*Updated", re.I))
        updated = _text(stamp) or None

    new_snow = []
    for li in soup.select("#snow-conditions ul.list-snow:not(.snow-base) > li"):
        period = _text(li.find("h4")).replace("*", "").strip()
        if period:
            new_snow.append({"period": period, "cm": sanitize_number(_text(li.select_one(".value_switch")))})

    base = []
    for li in soup.select("#snow-conditions ul.list-snow.snow-base > li"):
        name = _text(li.find("h4"))
        if name:
            base.append({"name": name, "cm": sanitize_number(_text(li.select_one(".value_switch")))})

    # The page repeats the temperature list for mobile; the first one is enough.
    temperatures = []
    temps_section = soup.select_one("div.current-temps")
    for li in temps_section.select("ul.list-temps > li") if temps_section else []:
        name, elevation = _station(li)
        value = sanitize_number(_text(li.select_one(".value_deg")))
        if name and value is not None:
            temperatures.append({"name": name, "elevation_m": elevation, "c": value})

    air_quality = []
    aq_section = soup.select_one("div.air-quality")
    for li in aq_section.select("ul.list-temps > li") if aq_section else []:
        name, elevation = _station(li)
        value = sanitize_number(_text(li.select_one(".weather-value")))
        if name and value is not None:
            air_quality.append({"name": name, "elevation_m": elevation, "aqhi": value})

    wind = []
    for div in soup.find_all("div", class_="wind"):
        name, elevation = _station(div)
        values = div.select(".weather-value")
        direction = _text(values[0]) if values else ""
        kph = sanitize_number(_text(div.select_one(".value_kph")))
        if name:
            wind.append({"name": name, "elevation_m": elevation, "direction": direction, "kph": kph})

    return {
        "narrative": narrative,
        "icon": icon,
        "updated": updated,
        "new_snow": new_snow,
        "base": base,
        "temperatures": temperatures,
        "air_quality": air_quality,
        "wind": wind,
    }


def get_resort():
    """Parsed resort conditions (cached), or None if the page can't be fetched."""
    data = cache.get(CACHE_KEY)
    if data is None:
        try:
            response = requests.get(SNOW_REPORT_URL, timeout=15)
            response.raise_for_status()
            data = parse_resort_html(response.content)
        except Exception:
            log.exception("Sun Peaks conditions page unavailable")
            return None
        cache.set(CACHE_KEY, data, CACHE_TTL)
    return data