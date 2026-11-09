# bdh-app-snow-report

Black Diamond Hub app: **Mountain Conditions** for Sun Peaks (tile title; the
app id, package and URL are still `snow_report`). Moved out of
[BlackDiamondHub](https://github.com/blackdiamondlodge/BlackDiamondHub) and
installed into the hub through the `blackdiamondhub.plugins` entry point
(see [bdh-sdk](https://github.com/blackdiamondlodge/bdh-sdk)).

Page: `/snow_report/` (`?units=metric|imperial`).

## Data sources

- **Sun Peaks Resort** conditions page (`resort.py`, cached 10 min): the
  daily narrative, new snow, snow base, temperatures by elevation, wind and
  air quality (AQHI). Sun Peaks drops the narrative and snow sections out of
  season, and the page hides whichever sections are missing.
- **Open-Meteo** (`forecast.py`, cached 30 min, no API key): the 5-day
  forecast for the village (1,255 m) and the alpine (2,080 m).

## Today card background

The Today card has a subtle animated background (clouds, sun, stars, fog,
drizzle, rain, snow or storm). It follows the village's current weather code
from Open-Meteo, falling back to today's forecast code (day or night from
sunrise and sunset). Preview any effect with `?wx=<effect>`, e.g.
`/snow_report/?wx=snow`. The animation stops when the device asks for
reduced motion.

Without a resort report (off-season), the Today card's icon and text also
show current conditions, so they match the background. The whole-day summary
stays in the forecast's Today tile.

## Seasons

- **Ski season:** Sun Peaks is publishing snow data. Shows snowfall, snow
  base and alpine snow in the forecast.
- **Summer** (June–September without snow data): warm theme. Shows UV,
  chance of rain and sunset.
- **Off-season** (any other month without snow data): the winter layout
  without the snow cards, so you can watch the forecast for the first snow.

The homepage tile shows new snow when there is some. Otherwise it shows the
temperature at the top of the mountain.

## Development

CI (`.github/workflows/ci.yml`) uses the reusable `app-ci.yml` from
bdh-sdk. It builds the wheel, installs it next to the hub, then runs
`hub_smoke`, the app tests and the selenium tests. CI also runs daily, because some tests hit the live site this app scrapes.

To release, bump `version` in `pyproject.toml`. When that lands on
`main`, `release.yml` tags it and publishes the wheel, and the release
notes include the hashed line for the hub's `sites/<site>/apps.txt`.
