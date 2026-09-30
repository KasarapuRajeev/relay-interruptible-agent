import unittest

from relay.security import sanitize_error


class SecurityTests(unittest.TestCase):
    def test_openai_style_secret_is_redacted(self):
        fake_secret = "sk-" + "project-secret123456789"
        value = sanitize_error(f"Request failed with {fake_secret}")
        self.assertNotIn("secret123456789", value)
        self.assertIn("[REDACTED]", value)

    def test_gemini_style_secret_is_redacted(self):
        fake_secret = "AIza" + "SyA123456789012345678901234"
        value = sanitize_error(f"API key: {fake_secret}")
        self.assertNotIn("AIza", value)
        self.assertIn("[REDACTED]", value)

    def test_external_error_is_single_line_and_bounded(self):
        value = sanitize_error("failure\n" + "x" * 1_000)
        self.assertNotIn("\n", value)
        self.assertLessEqual(len(value), 300)
