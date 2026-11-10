import datetime
import os
from unittest.mock import patch

from django.core.cache import cache
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import TestCase, tag
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from snow_report.forecast import get_current, get_forecast, parse_forecast, weather_effect
from snow_report.resort import SNOW_REPORT_URL, parse_resort_html, sanitize_number
from snow_report.views import RESORT_TZ, build_context

FIXTURES = os.path.join(os.path.dirname(__file__), "tests")


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return parse_resort_html(f.read())


def open_meteo_payload(days=5):
    def daily(high, low, snow, code):
        times = [(datetime.date(2026, 1, 10) + datetime.timedelta(days=i)).isoformat() for i in range(days)]
        return {"daily": {
            "time": times,
            "weather_code": [code] * days,
            "temperature_2m_max": [high] * days,
            "temperature_2m_min": [low] * days,
            "snowfall_sum": [snow] * days,
            "precipitation_probability_max": [40] * days,
            "uv_index_max": [2.4] * days,
            "sunrise": [f"{t}T07:45" for t in times],
            "sunset": [f"{t}T16:40" for t in times],
        }}
    return [daily(1.0, -6.0, 0.0, 3), daily(-7.0, -12.0, 8.4, 73)]


def fake_now(year, month, day, hour=12):
    return lambda: datetime.datetime(year, month, day, hour, tzinfo=RESORT_TZ)


class SanitizeNumberTests(TestCase):
    def test_double_dash_negative(self):
        self.assertEqual(sanitize_number("--7"), -7.0)

    def test_thousands_separator(self):
        self.assertEqual(sanitize_number("2,080"), 2080.0)

    def test_not_available(self):
        self.assertIsNone(sanitize_number("N/A"))
        self.assertIsNone(sanitize_number(""))
        self.assertIsNone(sanitize_number("-"))


class WinterParseTests(TestCase):
    """weather_bad_data.html is an in-season capture (Feb 27)."""

    def setUp(self):
        self.data = fixture("weather_bad_data.html")

    def test_narrative_and_icon(self):
        self.assertTrue(self.data["narrative"].startswith("Cloudy with sunny breaks"))
        self.assertEqual(self.data["icon"], "fas fa-cloud-sun")
        self.assertEqual(self.data["updated"], "Updated February 27th at 6:43pm")

    def test_new_snow_keeps_missing_values_as_none(self):
        self.assertEqual(
            [(s["period"], s["cm"]) for s in self.data["new_snow"]],
            [("New Snow", 0.0), ("24 Hr", None), ("48 Hr", 0.0), ("7 Days", 24.0)],
        )

    def test_snow_base(self):
        self.assertEqual([(b["name"], b["cm"]) for b in self.data["base"]],
                         [("Mid Mountain", 158.0), ("Alpine", 172.0)])

    def test_temperatures(self):
        self.assertEqual([(t["name"], t["elevation_m"], t["c"]) for t in self.data["temperatures"]], [
            ("Top of the World", 2080.0, -2.0), ("Mid-mountain", 1855.0, 0.0),
            ("Top of Morrisey", 1675.0, 0.0), ("Valley", 1255.0, 3.0),
        ])


class OffSeasonParseTests(TestCase):
    """weather_current.html is an off-season capture: no snow, narrative or forecast."""

    def setUp(self):
        self.data = fixture("weather_current.html")

    def test_no_snow_sections(self):
        self.assertIsNone(self.data["narrative"])
        self.assertEqual(self.data["new_snow"], [])
        self.assertEqual(self.data["base"], [])

    def test_air_quality_kept_out_of_temperatures(self):
        self.assertEqual({t["name"] for t in self.data["temperatures"]},
                         {"Top of the World", "Mid-mountain", "Top of Morrisey", "Valley"})
        self.assertEqual([(a["name"], a["aqhi"]) for a in self.data["air_quality"]], [
            ("Top of Sunburst", 1.0), ("Top of Sundance", 1.0), ("Top of Morrisey", 1.0), ("Valley", 1.0),
        ])

    def test_wind(self):
        self.assertEqual(self.data["wind"][0],
                         {"name": "Top of the World", "elevation_m": 2080.0, "direction": "SSE", "kph": 16.0})
        self.assertEqual(len(self.data["wind"]), 3)


class LiveResortPageTests(TestCase):
    """Catches Sun Peaks changing their page markup (CI runs this daily)."""

    def test_live_page_still_parses(self):
        import requests
        response = requests.get(SNOW_REPORT_URL, timeout=30)
        response.raise_for_status()
        data = parse_resort_html(response.content)
        self.assertGreaterEqual(len(data["temperatures"]), 3, data)
        for t in data["temperatures"]:
            self.assertTrue(1000 <= t["elevation_m"] <= 2500, t)
            self.assertTrue(-50 <= t["c"] <= 45, t)
        if data["new_snow"]:
            self.assertTrue(data["base"], "snow conditions without a snow base")


class ForecastParseTests(TestCase):
    def test_village_and_alpine_combined(self):
        days = parse_forecast(open_meteo_payload())
        self.assertEqual(len(days), 5)
        first = days[0]
        self.assertEqual(first["date"], datetime.date(2026, 1, 10))
        self.assertEqual((first["icon"], first["label"]), ("fas fa-cloud", "Overcast"))
        self.assertEqual((first["high_c"], first["low_c"]), (1.0, -6.0))
        self.assertEqual((first["alpine_high_c"], first["alpine_snow_cm"]), (-7.0, 8.4))
        self.assertEqual((first["sunrise"], first["sunset"]), ("07:45", "16:40"))

    def test_unknown_weather_code(self):
        payload = open_meteo_payload()
        payload[0]["daily"]["weather_code"][0] = 1234
        self.assertEqual(parse_forecast(payload)[0]["icon"], "fas fa-cloud")


class WeatherEffectTests(TestCase):
    def test_codes(self):
        cases = {(0, True): "sun", (1, False): "stars", (2, True): "partly", (2, False): "clouds",
                 (3, True): "clouds", (45, True): "fog", (53, True): "drizzle", (63, True): "rain",
                 (81, True): "rain", (73, True): "snow", (86, True): "snow", (95, True): "storm",
                 (1234, True): "clouds"}
        for (code, is_day), effect in cases.items():
            self.assertEqual(weather_effect(code, is_day), effect, code)

    @patch("snow_report.forecast.requests.get")
    def test_fetch_caches_current_conditions(self, get):
        cache.clear()
        payload = open_meteo_payload()
        payload[0]["current"] = {"time": "2026-01-10T20:00", "weather_code": 71, "is_day": 0}
        get.return_value.json.return_value = payload
        get_forecast()
        self.assertEqual(get_current(), {"code": 71, "is_day": False})
        self.assertIn("weather_code,is_day", get.call_args.kwargs["params"]["current"])


class BuildContextTests(TestCase):
    def test_winter_when_snow_data_present(self):
        ctx = build_context(fixture("weather_bad_data.html"), parse_forecast(open_meteo_payload()), "metric")
        self.assertEqual(ctx["season"], "winter")
        self.assertEqual(ctx["hero_icon"], "fas fa-cloud-sun")
        self.assertEqual([b["value"] for b in ctx["base"]], [158, 172])

    @patch("snow_report.views.local_now", fake_now(2026, 7, 15))
    def test_summer_without_snow_data(self):
        ctx = build_context(fixture("weather_current.html"), parse_forecast(open_meteo_payload()), "metric")
        self.assertEqual(ctx["season"], "summer")
        self.assertEqual(ctx["hero_text"], "Overcast")  # falls back to the forecast

    @patch("snow_report.views.local_now", fake_now(2026, 11, 8))
    def test_shoulder_season_without_snow_data(self):
        ctx = build_context(fixture("weather_current.html"), None, "metric")
        self.assertEqual(ctx["season"], "shoulder")

    def test_imperial_conversion(self):
        ctx = build_context(fixture("weather_bad_data.html"), parse_forecast(open_meteo_payload()), "imperial")
        self.assertEqual(ctx["temperatures"][0]["value"], 28)            # -2 °C
        self.assertEqual(ctx["temperatures"][0]["elevation"], "6,824")   # 2080 m
        self.assertEqual([s["value"] for s in ctx["new_snow"]], [0, None, 0, 9.4])
        self.assertEqual([b["value"] for b in ctx["base"]], [62, 68])
        self.assertEqual(ctx["wind"][0]["value"], 7)                     # 11 km/h
        self.assertEqual(ctx["forecast"][0]["snow"], 3.3)                # 8.4 cm

    def test_wind_arrow_points_downwind(self):
        ctx = build_context(fixture("weather_bad_data.html"), None, "metric")
        self.assertEqual([(w["direction"], w["rotation"]) for w in ctx["wind"]][:2], [("S", 0.0), ("WSW", 67.5)])

    def test_stations_ordered_top_down_and_spread_up_the_slope(self):
        ctx = build_context(fixture("weather_current.html"), None, "metric")
        self.assertEqual([t["name"] for t in ctx["temperatures"]][0], "Top of the World")
        self.assertEqual([t["height_pct"] for t in ctx["temperatures"]], [88, 64, 40, 16])

    @patch("snow_report.views.local_now", fake_now(2026, 1, 10, hour=20))
    def test_today_is_the_resort_date_not_utc(self):
        ctx = build_context(None, parse_forecast(open_meteo_payload()), "metric")
        self.assertEqual([d["name"] for d in ctx["forecast"][:2]], ["Today", "Sun"])

    @patch("snow_report.views.local_now", fake_now(2026, 1, 11, hour=1))
    def test_forecast_cached_before_midnight_starts_at_today(self):
        ctx = build_context(None, parse_forecast(open_meteo_payload()), "metric")
        self.assertEqual(ctx["today"]["date"], "Jan 11")
        self.assertEqual(ctx["forecast"][0]["name"], "Today")

    @patch("snow_report.views.local_now", fake_now(2026, 1, 10))
    def test_background_follows_current_conditions(self):
        forecast = parse_forecast(open_meteo_payload())
        self.assertEqual(build_context(None, forecast, "metric", {"code": 75, "is_day": True})["wx"], "snow")
        self.assertEqual(build_context(None, forecast, "metric")["wx"], "clouds")  # daily code 3
        self.assertIsNone(build_context(None, None, "metric")["wx"])

    @patch("snow_report.views.local_now", fake_now(2026, 1, 10, hour=22))
    def test_hero_shows_current_conditions_without_a_resort_report(self):
        forecast = parse_forecast(open_meteo_payload())  # daily code 3: Overcast
        ctx = build_context(fixture("weather_current.html"), forecast, "metric", {"code": 0, "is_day": False})
        self.assertEqual((ctx["hero_icon"], ctx["hero_text"]), ("fas fa-moon", "Clear"))
        self.assertEqual(ctx["forecast"][0]["label"], "Overcast")  # the day summary stays in the forecast
        ctx = build_context(fixture("weather_bad_data.html"), forecast, "metric", {"code": 0, "is_day": False})
        self.assertTrue(ctx["hero_text"].startswith("Cloudy with sunny breaks"))  # resort report wins

    @patch("snow_report.views.local_now", fake_now(2026, 1, 10, hour=22))
    def test_background_falls_back_to_night_after_sunset(self):
        payload = open_meteo_payload()
        payload[0]["daily"]["weather_code"][0] = 0
        self.assertEqual(build_context(None, parse_forecast(payload), "metric")["wx"], "stars")

    def test_everything_unavailable(self):
        ctx = build_context(None, None, "metric")
        self.assertFalse(ctx["resort_ok"])
        self.assertEqual(ctx["temperatures"], [])


class ViewTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("snow_report.views.get_forecast", side_effect=lambda: parse_forecast(open_meteo_payload()))
    @patch("snow_report.views.get_resort", side_effect=lambda: fixture("weather_bad_data.html"))
    def test_winter_page(self, *_):
        html = self.client.get("/snow_report/").content.decode()
        self.assertIn("Mountain Conditions", html)
        self.assertIn("Ski season", html)
        self.assertIn("Snow base", html)
        self.assertIn("5-day forecast", html)
        # The units switch shows metric selected and flips to imperial.
        self.assertIn('class="mc-units" data-unit="metric"', html)
        self.assertIn('href="?units=imperial"', html)

    @patch("snow_report.views.local_now", fake_now(2026, 7, 15))
    @patch("snow_report.views.get_forecast", return_value=None)
    @patch("snow_report.views.get_resort", side_effect=lambda: fixture("weather_current.html"))
    def test_summer_page_hides_snow_and_missing_forecast(self, *_):
        html = self.client.get("/snow_report/?units=imperial").content.decode()
        self.assertIn("Summer", html)
        self.assertIn("Air quality", html)
        self.assertNotIn("Snow base", html)
        self.assertNotIn("5-day forecast", html)
        self.assertIn("6,824 ft", html)
        self.assertIn('class="mc-units" data-unit="imperial"', html)
        self.assertIn('href="?units=metric"', html)

    @patch("snow_report.views.get_current", return_value={"code": 3, "is_day": True})
    @patch("snow_report.views.get_forecast", return_value=None)
    @patch("snow_report.views.get_resort", side_effect=lambda: fixture("weather_bad_data.html"))
    def test_weather_background_and_preview_override(self, *_):
        self.assertIn('data-wx="clouds"', self.client.get("/snow_report/").content.decode())
        self.assertIn('data-wx="snow"', self.client.get("/snow_report/?wx=snow").content.decode())
        self.assertIn('data-wx="clouds"', self.client.get("/snow_report/?wx=<b>").content.decode())

    @patch("snow_report.views.get_forecast", return_value=None)
    @patch("snow_report.views.get_resort", return_value=None)
    def test_sources_down(self, *_):
        response = self.client.get("/snow_report/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Conditions are unavailable", response.content.decode())


@tag("selenium")
class SnowReportScrollHintTest(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from tests.selenium_helpers import get_chrome_options
        cls.browser = webdriver.Chrome(options=get_chrome_options())
        cls.browser.set_window_size(1280, 700)

    @classmethod
    def tearDownClass(cls):
        cls.browser.quit()
        super().tearDownClass()

    @patch("snow_report.views.get_forecast", side_effect=lambda: parse_forecast(open_meteo_payload()))
    @patch("snow_report.views.get_resort", side_effect=lambda: fixture("weather_bad_data.html"))
    def test_scroll_hint_hides_at_bottom(self, *_):
        self.browser.get(f"{self.live_server_url}/snow_report/")
        hint = WebDriverWait(self.browser, 10).until(EC.visibility_of_element_located((By.ID, "scroll-hint")))
        self.assertNotIn("hidden", hint.get_attribute("class"))
        self.browser.execute_script("document.getElementById('scroll-sentinel').scrollIntoView();")
        WebDriverWait(self.browser, 5).until(
            lambda d: "hidden" in d.find_element(By.ID, "scroll-hint").get_attribute("class"),
            "Scroll hint should have 'hidden' class after scrolling to bottom",
        )


class HomepageHookTests(TestCase):
    def setUp(self):
        cache.clear()

    def status(self, resort):
        with patch("snow_report.homepage.get_resort", return_value=resort):
            from snow_report.homepage import status
            return status()

    def test_new_snow(self):
        resort = fixture("weather_bad_data.html")
        resort["new_snow"][0]["cm"] = 14.0
        result = self.status(resort)
        self.assertEqual((result.text, result.level), ("14 cm new snow", "on"))

    def test_skips_missing_snow_values(self):
        resort = fixture("weather_bad_data.html")
        resort["new_snow"] = [{"period": "New Snow", "cm": None}, {"period": "24 Hr", "cm": 3.0}]
        self.assertEqual(self.status(resort).text, "3 cm in 24 hr")

    def test_off_season_shows_alpine_temperature(self):
        result = self.status(fixture("weather_current.html"))
        self.assertEqual((result.text, result.level), ("4 °C at Top of the World", "info"))

    def test_unavailable(self):
        self.assertIsNone(self.status(None))