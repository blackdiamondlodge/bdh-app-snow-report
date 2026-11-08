from bdh_sdk import PluginSpec, Tile

spec = PluginSpec(
    id="snow_report",
    app="snow_report",
    urls="snow_report.urls",
    status="snow_report.homepage.status",
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
