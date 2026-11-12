from bdh_sdk import PluginSpec, Tile
from bdh_sdk.provides import STATS

STAT_KEYS = (
    ("temp_top", "Temp up top"),
    ("temp_mid", "Temp mid-mountain"),
    ("temp_village", "Temp at the lodge"),
    ("snow_24h", "New snow, 24h"),
    ("snow_48h", "New snow, 48h"),
    ("base", "Base depth"),
    ("wind_top", "Wind up top"),
    ("sunrise", "Sunrise"),
    ("sunset", "Sunset"),
    ("sun", "Next sunrise or sunset"),
)

spec = PluginSpec(
    id="snow_report",
    app="snow_report",
    urls="snow_report.urls",
    status="snow_report.homepage.status",
    provides={STATS: "snow_report.provides.stats"},
    stat_keys=STAT_KEYS,
    tiles=(
        Tile(
            title="Mountain Conditions",
            url_name="snow_report",
            icon="snow_report/hub/icon.svg",
            section="mountain",
            subtitle="Snow, weather & forecast",
            order=10,
        ),
    ),
)
