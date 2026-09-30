import json
import unittest
from unittest.mock import patch

from relay.research import search_wikipedia


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class ResearchConnectorTests(unittest.TestCase):
    @patch("relay.research.urllib.request.urlopen")
    def test_returns_cited_mediawiki_evidence(self, urlopen):
        urlopen.return_value = _Response(
            {
                "query": {
                    "pages": [
                        {
                            "title": "Quantum computing",
                            "fullurl": "https://en.wikipedia.org/wiki/Quantum_computing",
                            "extract": "Quantum computing uses quantum phenomena.",
                        }
                    ]
                }
            }
        )

        result = search_wikipedia("quantum computing", "overview")

        self.assertEqual(result["aspect"], "overview")
        self.assertEqual(result["sources"][0]["title"], "Quantum computing")
        self.assertTrue(result["sources"][0]["url"].startswith("https://"))
        request = urlopen.call_args.args[0]
        self.assertIn("generator=search", request.full_url)

    @patch("relay.research.urllib.request.urlopen")
    def test_empty_mediawiki_result_is_a_visible_failure(self, urlopen):
        urlopen.return_value = _Response({"query": {"pages": []}})

        with self.assertRaisesRegex(RuntimeError, "No cited Wikipedia evidence"):
            search_wikipedia("topic with no results", "overview")


if __name__ == "__main__":
    unittest.main()
