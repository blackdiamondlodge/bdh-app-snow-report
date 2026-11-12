"""Mountain conditions for other parts of the hub (e.g. the screensaver info strip)."""
from datetime import datetime, time

from bdh_sdk.provides import Stat

from .forecast import get_forecast
from .resort import get_resort
from .views import RESORT_TZ, local_now

MINUS = "\u2212"


def _temp(c):
    n = round(c)
    return f"{MINUS if n < 0 else ''}{abs(n)}°C"


def _named(rows, word):
    return next((r for r in rows if word in (r.get("name") or "").lower()), None)


def _top(rows):
    return _named(rows, "top of the world") or max(rows, key=lambda r: r.get("elevation_m") or 0, default=None)


def _bottom(rows):
    return _named(rows, "valley") or min(rows, key=lambda r: r.get("elevation_m") or 0, default=None)


def _snow(resort, period):
    row = next((r for r in resort.get("new_snow") or [] if r.get("period") == period), None)
    return f"{row['cm']:g} cm" if row and row.get("cm") is not None else None


def _sun(forecast, field, now):
    """The next sunrise/sunset ("HH:MM" resort-local per forecast day) still ahead of now."""
    for day in forecast or ():
        hh, mm = (day.get(field) or ":").split(":")
        if not (hh and mm):
            continue
        when = datetime.combine(day["date"], time(int(hh), int(mm)), tzinfo=RESORT_TZ)
        if when > now:
            return when
    return None


def build_stats(resort, forecast, now):
    resort = resort or {}
    out = []

    def add(key, label, order, value=None, when=None):
        if value is not None or when is not None:
            out.append(Stat(key, label, value=value, time=when, order=order))

    temps = [t for t in resort.get("temperatures") or [] if t.get("c") is not None]
    for order, key, label, pick in ((10, "temp_top", "Up top", _top),
                                    (11, "temp_mid", "Mid-mountain", lambda r: _named(r, "mid")),
                                    (12, "temp_village", "At the lodge", _bottom)):
        row = pick(temps)
        add(key, label, order, value=_temp(row["c"]) if row else None)
    add("snow_24h", "New snow, 24h", 20, value=_snow(resort, "24 Hr"))
    add("snow_48h", "New snow, 48h", 21, value=_snow(resort, "48 Hr"))
    base = next((r for r in resort.get("base") or [] if r.get("cm") is not None), None)
    add("base", "Base depth", 22, value=f"{base['cm']:g} cm" if base else None)
    wind = _top([w for w in resort.get("wind") or [] if w.get("kph") is not None])
    if wind:
        add("wind_top", "Wind up top", 30, value=f"{wind['kph']:g} km/h {wind.get('direction') or ''}".strip())
    add("sunrise", "Sunrise", 40, when=_sun(forecast, "sunrise", now))
    add("sunset", "Sunset", 41, when=_sun(forecast, "sunset", now))
    return out


def stats():
    return build_stats(get_resort(), get_forecast(), local_now())
