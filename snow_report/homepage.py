from django.core.cache import cache

from bdh_sdk import INFO, ON, Status

from .resort import get_resort

CACHE_KEY = "snow_report:homepage"
CACHE_TTL = 15 * 60


def _summary():
    data = get_resort()
    if not data:
        return {}
    for snow in data["new_snow"]:
        if snow["cm"] is not None:
            return {"period": snow["period"], "cm": round(snow["cm"])}
    if data["temperatures"]:
        top = max(data["temperatures"], key=lambda t: t["elevation_m"] or 0)
        return {"temp_c": round(top["c"]), "where": top["name"]}
    return {"description": data["narrative"]} if data["narrative"] else {}


def status():
    summary = cache.get(CACHE_KEY)
    if summary is None:
        summary = _summary()
        cache.set(CACHE_KEY, summary, CACHE_TTL)
    if "cm" in summary:
        period = summary["period"]
        if "new" in period.lower():
            text = f"{summary['cm']} cm new snow"
        else:
            text = f"{summary['cm']} cm in {period.lower()}"
        return Status(text, ON if summary["cm"] > 0 else INFO)
    if "temp_c" in summary:
        return Status(f"{summary['temp_c']} °C at {summary['where']}")
    if summary.get("description"):
        return Status(summary["description"])
    return None