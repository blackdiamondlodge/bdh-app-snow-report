from datetime import datetime
from zoneinfo import ZoneInfo

from django.shortcuts import render

from .forecast import EFFECTS, describe, get_current, get_forecast, weather_effect
from .resort import get_resort, sanitize_number  # noqa: F401  (re-exported for older callers)

COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
AQHI_LEVELS = ((3, "low", "Low risk"), (6, "moderate", "Moderate"), (10, "high", "High risk"))
RESORT_TZ = ZoneInfo("America/Vancouver")


def local_now():
    """Wall-clock time at the resort (the server runs in UTC)."""
    return datetime.now(RESORT_TZ)


class Units:
    def __init__(self, system):
        self.imperial = system == "imperial"
        self.system = "imperial" if self.imperial else "metric"
        self.temp = "°F" if self.imperial else "°C"
        self.depth = "in" if self.imperial else "cm"
        self.height = "ft" if self.imperial else "m"
        self.speed = "mph" if self.imperial else "km/h"

    def t(self, c):
        if c is None:
            return None
        return round(c * 9 / 5 + 32) if self.imperial else round(c)

    def d(self, cm):
        if cm is None:
            return None
        if not self.imperial:
            return round(cm)
        inches = round(cm / 2.54, 1) if cm < 25 else round(cm / 2.54)
        return int(inches) if inches == int(inches) else inches

    def h(self, m):
        if m is None:
            return None
        return f"{round(m * 3.28084):,}" if self.imperial else f"{round(m):,}"

    def s(self, kph):
        if kph is None:
            return None
        return round(kph * 0.621371) if self.imperial else round(kph)


def _aqhi(value):
    for limit, level, label in AQHI_LEVELS:
        if value <= limit:
            return level, label
    return "very-high", "Very high risk"


def _wind_rotation(direction):
    """Degrees to rotate an up-arrow so it points where the wind is blowing to."""
    if direction.upper() not in COMPASS:
        return None
    return (COMPASS.index(direction.upper()) * 22.5 + 180) % 360


def build_context(resort, forecast, units, current=None):
    u = Units(units)
    resort = resort or {}
    now = local_now()
    if resort.get("new_snow") or resort.get("base"):
        season = "winter"
    elif 6 <= now.month <= 9:
        season = "summer"
    else:
        season = "shoulder"

    temperatures = sorted(
        ({"name": t["name"], "elevation": u.h(t["elevation_m"]), "elevation_m": t["elevation_m"] or 0,
          "value": u.t(t["c"])} for t in resort.get("temperatures", [])),
        key=lambda t: -t["elevation_m"],
    )
    # Stations sit evenly up the slope (highest at the peak) so their labels never collide.
    steps = max(len(temperatures) - 1, 1)
    for rank, t in enumerate(reversed(temperatures)):
        t["height_pct"] = round(16 + 72 * rank / steps)

    new_snow = [{"period": s["period"], "value": u.d(s["cm"])} for s in resort.get("new_snow", [])]
    base = [{"name": b["name"], "value": u.d(b["cm"])} for b in resort.get("base", [])]

    wind = [{"name": w["name"], "elevation": u.h(w["elevation_m"]), "direction": w["direction"],
             "rotation": _wind_rotation(w["direction"]), "value": u.s(w["kph"])}
            for w in resort.get("wind", [])]

    air_quality = []
    for a in resort.get("air_quality", []):
        level, label = _aqhi(a["aqhi"])
        air_quality.append({"name": a["name"], "elevation": u.h(a["elevation_m"]),
                            "value": round(a["aqhi"]), "level": level, "label": label})

    forecast = forecast or []
    if any(day["date"] == now.date() for day in forecast):
        forecast = [day for day in forecast if day["date"] >= now.date()]  # cached from before midnight
    days = []
    for day in forecast:
        days.append({
            "code": day.get("code"),
            "name": "Today" if day["date"] == now.date() else day["date"].strftime("%a"),
            "date": f"{day['date']:%b} {day['date'].day}",
            "icon": day["icon"], "label": day["label"],
            "high": u.t(day["high_c"]), "low": u.t(day["low_c"]),
            "alpine_high": u.t(day["alpine_high_c"]), "alpine_low": u.t(day["alpine_low_c"]),
            "snow": u.d(day["alpine_snow_cm"]) if day["alpine_snow_cm"] else 0,
            "precip_chance": day["precip_chance"], "uv": round(day["uv"]) if day["uv"] is not None else None,
            "sunrise": day["sunrise"], "sunset": day["sunset"],
        })

    today = days[0] if days else None
    if resort.get("narrative"):  # the resort's daily report wins (ski season)
        hero_icon = resort.get("icon") or (today["icon"] if today else "fas fa-mountain")
        hero_text = resort["narrative"]
    elif current:  # otherwise what it's doing right now, matching the background
        hero_icon, hero_text = describe(current["code"], current["is_day"])
    else:
        hero_icon = resort.get("icon") or (today["icon"] if today else "fas fa-mountain")
        hero_text = today["label"] if today else None

    if current:
        wx = weather_effect(current["code"], current["is_day"])
    elif today and today["code"] is not None:
        is_day = today["sunrise"] <= now.strftime("%H:%M") < today["sunset"]
        wx = weather_effect(today["code"], is_day)
    else:
        wx = None

    return {
        "units": u.system,
        "u": u,
        "season": season,
        "hero_icon": hero_icon,
        "hero_text": hero_text,
        "wx": wx,
        "updated": resort.get("updated"),
        "today": today,
        "temperatures": temperatures,
        "new_snow": new_snow,
        "base": base,
        "wind": wind,
        "air_quality": air_quality,
        "forecast": days,
        "resort_ok": bool(resort),
    }


def snow_report(request):
    units = request.GET.get("units", "metric")
    context = build_context(get_resort(), get_forecast(), units, get_current())
    if request.GET.get("wx") in EFFECTS:  # preview a background
        context["wx"] = request.GET["wx"]
    return render(request, "snow_report/snow_report.html", context)