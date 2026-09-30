"""Key-free live research connector backed by the public MediaWiki API."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"


def search_wikipedia(
    topic: str,
    aspect: str,
    *,
    limit: int = 3,
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    """Return cited introductory extracts for one research aspect."""

    query = f"{topic} {aspect}".strip()
    parameters = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": str(limit),
        "prop": "extracts|info",
        "exintro": "1",
        "explaintext": "1",
        "exsentences": "3",
        "inprop": "url",
        "format": "json",
        "formatversion": "2",
    }
    url = f"{WIKIPEDIA_API}?{urllib.parse.urlencode(parameters)}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Relay-Samsung-Hackathon/0.1 (educational prototype)"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))

    sources = []
    for page in payload.get("query", {}).get("pages", []):
        extract = str(page.get("extract", "")).strip()
        full_url = str(page.get("fullurl", "")).strip()
        if not extract or not full_url:
            continue
        sources.append(
            {
                "title": str(page.get("title", "Untitled source")),
                "url": full_url,
                "extract": extract,
            }
        )
    if not sources:
        raise RuntimeError(f"No cited Wikipedia evidence found for {query!r}")
    return {
        "summary": f"Collected {len(sources)} cited sources for {aspect} of {topic}.",
        "topic": topic,
        "aspect": aspect,
        "sources": sources,
        "provider": "Wikipedia / MediaWiki Action API",
        "query_url": url,
    }
