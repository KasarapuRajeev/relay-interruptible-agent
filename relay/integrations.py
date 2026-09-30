"""Key-free, read-only integrations exposed through Relay's tool contract."""

from __future__ import annotations

import ast
import json
import operator
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any


JsonTransport = Callable[[str, float], dict[str, Any]]

GEOCODING_ENDPOINT = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"


def _get_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Relay-Samsung-Hackathon/0.2 (educational prototype)"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def calculate_expression(expression: str) -> dict[str, Any]:
    """Evaluate arithmetic without names, calls, attributes, or arbitrary code."""

    cleaned = expression.strip()
    if not cleaned or len(cleaned) > 160:
        raise ValueError("Expression must contain between 1 and 160 characters")
    try:
        root = ast.parse(cleaned, mode="eval")
    except SyntaxError as error:
        raise ValueError("Expression is not valid arithmetic") from error

    def evaluate(node: ast.AST, depth: int = 0) -> int | float:
        if depth > 20:
            raise ValueError("Expression is too deeply nested")
        if isinstance(node, ast.Expression):
            return evaluate(node.body, depth + 1)
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            return node.value
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            return _UNARY_OPERATORS[type(node.op)](evaluate(node.operand, depth + 1))
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            left = evaluate(node.left, depth + 1)
            right = evaluate(node.right, depth + 1)
            if isinstance(node.op, ast.Pow) and abs(right) > 12:
                raise ValueError("Exponent is outside the safe calculation limit")
            result = _BINARY_OPERATORS[type(node.op)](left, right)
            if abs(result) > 1e15:
                raise ValueError("Result is outside the safe calculation limit")
            return result
        raise ValueError("Only arithmetic numbers and operators are allowed")

    result = evaluate(root)
    return {
        "summary": f"{cleaned} = {result}",
        "expression": cleaned,
        "result": result,
        "source": "relay_safe_calculator",
    }


_WEATHER_DESCRIPTIONS = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def get_current_weather(
    location: str,
    *,
    timeout_seconds: float = 12.0,
    transport: JsonTransport = _get_json,
) -> dict[str, Any]:
    """Geocode a place and return cited current Open-Meteo conditions."""

    location = location.strip()
    if len(location) < 2 or len(location) > 120:
        raise ValueError("Location must contain between 2 and 120 characters")
    geocoding_url = f"{GEOCODING_ENDPOINT}?{urllib.parse.urlencode({'name': location, 'count': 1, 'language': 'en', 'format': 'json'})}"
    geocoding = transport(geocoding_url, timeout_seconds)
    matches = geocoding.get("results") or []
    if not matches:
        raise RuntimeError(f"No weather location found for {location!r}")
    place = matches[0]
    latitude = float(place["latitude"])
    longitude = float(place["longitude"])
    parameters = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,apparent_temperature,relative_humidity_2m,"
            "precipitation,weather_code,wind_speed_10m"
        ),
        "timezone": "auto",
    }
    forecast_url = f"{FORECAST_ENDPOINT}?{urllib.parse.urlencode(parameters)}"
    forecast = transport(forecast_url, timeout_seconds)
    current = forecast.get("current") or {}
    if "temperature_2m" not in current:
        raise RuntimeError("Open-Meteo did not return current weather conditions")
    units = forecast.get("current_units") or {}
    display_name = ", ".join(
        str(value)
        for value in (place.get("name"), place.get("admin1"), place.get("country"))
        if value
    )
    code = int(current.get("weather_code", -1))
    condition = _WEATHER_DESCRIPTIONS.get(code, f"weather code {code}")
    temperature = current["temperature_2m"]
    apparent = current.get("apparent_temperature")
    humidity = current.get("relative_humidity_2m")
    wind = current.get("wind_speed_10m")
    summary = f"Current weather in {display_name}: {condition}, {temperature}{units.get('temperature_2m', '°C')}"
    if apparent is not None:
        summary += f" (feels like {apparent}{units.get('apparent_temperature', '°C')})"
    if humidity is not None:
        summary += f", humidity {humidity}{units.get('relative_humidity_2m', '%')}"
    if wind is not None:
        summary += f", wind {wind} {units.get('wind_speed_10m', 'km/h')}"
    summary += "."
    return {
        "summary": summary,
        "location": display_name,
        "coordinates": {"latitude": latitude, "longitude": longitude},
        "observed_at": current.get("time"),
        "condition": condition,
        "temperature": temperature,
        "apparent_temperature": apparent,
        "relative_humidity": humidity,
        "precipitation": current.get("precipitation"),
        "wind_speed": wind,
        "timezone": forecast.get("timezone"),
        "sources": [
            {"title": "Open-Meteo current weather", "url": forecast_url},
            {"title": "Open-Meteo geocoding", "url": geocoding_url},
        ],
        "provider": "Open-Meteo",
    }
