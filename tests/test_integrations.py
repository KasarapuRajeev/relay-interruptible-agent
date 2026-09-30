import unittest

from relay.demo import MANIFEST
from relay.integrations import calculate_expression, get_current_weather


class CalculatorIntegrationTests(unittest.TestCase):
    def test_calculates_arithmetic_without_code_execution(self):
        result = calculate_expression("(1250 * 3) + 499")
        self.assertEqual(result["result"], 4249)
        self.assertEqual(result["source"], "relay_safe_calculator")

    def test_rejects_names_calls_and_unsafe_exponents(self):
        for expression in ("open('secret')", "x + 1", "2 ** 100"):
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    calculate_expression(expression)


class WeatherIntegrationTests(unittest.TestCase):
    def test_returns_cited_current_weather_after_geocoding(self):
        requested_urls = []

        def transport(url, timeout):
            requested_urls.append(url)
            if "geocoding-api" in url:
                return {
                    "results": [
                        {
                            "name": "Bengaluru",
                            "admin1": "Karnataka",
                            "country": "India",
                            "latitude": 12.97,
                            "longitude": 77.59,
                        }
                    ]
                }
            return {
                "current": {
                    "time": "2026-09-29T12:00",
                    "temperature_2m": 25.4,
                    "apparent_temperature": 26.1,
                    "relative_humidity_2m": 65,
                    "precipitation": 0,
                    "weather_code": 2,
                    "wind_speed_10m": 8.2,
                },
                "current_units": {
                    "temperature_2m": "°C",
                    "apparent_temperature": "°C",
                    "relative_humidity_2m": "%",
                    "wind_speed_10m": "km/h",
                },
                "timezone": "Asia/Kolkata",
            }

        result = get_current_weather("Bengaluru", transport=transport)

        self.assertIn("Bengaluru, Karnataka, India", result["summary"])
        self.assertEqual(result["condition"], "partly cloudy")
        self.assertEqual(len(result["sources"]), 2)
        self.assertEqual(len(requested_urls), 2)
        self.assertIn("name=Bengaluru", requested_urls[0])
        self.assertIn("current=", requested_urls[1])

    def test_unknown_location_fails_truthfully(self):
        with self.assertRaisesRegex(RuntimeError, "No weather location found"):
            get_current_weather(
                "Unknown place",
                transport=lambda *_: {"results": []},
            )


class CapabilityManifestTests(unittest.TestCase):
    def test_new_integrations_are_read_only_declared_capabilities(self):
        definitions = {item["name"]: item for item in MANIFEST}
        self.assertIn("get_current_weather", definitions)
        self.assertIn("calculate", definitions)
        self.assertFalse(definitions["get_current_weather"]["state_modifying"])
        self.assertFalse(definitions["calculate"]["state_modifying"])


if __name__ == "__main__":
    unittest.main()
