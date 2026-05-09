"""Tests for claude-usage-plugin.py — run with: python3 -m pytest Tests/PluginTests/test_claude_plugin.py"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from io import StringIO
from unittest.mock import patch

PLUGIN_PATH = Path(__file__).parent.parent.parent / "Resources" / "BundledPlugins" / "claude-usage-plugin.py"


def load_plugin():
    spec = importlib.util.spec_from_file_location("claude_plugin", PLUGIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


plugin = load_plugin()


class TestTranslateSignature(unittest.TestCase):
    """translate(language, key) — language first, key second (matches all other plugins)."""

    def test_language_first_zh(self):
        result = plugin.translate("zh-Hans", "five_hour")
        self.assertEqual(result, "5 小时用量")

    def test_language_first_en(self):
        result = plugin.translate("en", "five_hour")
        self.assertEqual(result, "5-hour usage")

    def test_unknown_key_returns_key(self):
        result = plugin.translate("en", "nonexistent_key")
        self.assertEqual(result, "nonexistent_key")


class TestColorThresholds(unittest.TestCase):
    """color_for thresholds should match other plugins: ≥90 red, ≥80 orange, ≥60 yellow, <60 blue."""

    def test_90_is_red(self):
        self.assertEqual(plugin.color_for(90), "red")

    def test_80_is_orange(self):
        self.assertEqual(plugin.color_for(80), "orange")

    def test_79_is_yellow(self):
        self.assertEqual(plugin.color_for(79), "yellow")

    def test_60_is_yellow(self):
        self.assertEqual(plugin.color_for(60), "yellow")

    def test_59_is_blue(self):
        self.assertEqual(plugin.color_for(59), "blue")


class TestStatusThresholds(unittest.TestCase):
    """status_for thresholds should match other plugins: ≥90 critical, ≥75 warning, else normal."""

    def test_90_is_critical(self):
        self.assertEqual(plugin.status_for(90), "critical")

    def test_75_is_warning(self):
        self.assertEqual(plugin.status_for(75), "warning")

    def test_74_is_normal(self):
        self.assertEqual(plugin.status_for(74), "normal")

    def test_0_is_normal(self):
        self.assertEqual(plugin.status_for(0), "normal")


class TestSuccessSchemaVersion(unittest.TestCase):
    """success() output must include schemaVersion field."""

    def test_success_has_schema_version(self):
        items = [{"id": "x", "name": "x", "used": 0, "limit": 1, "displayStyle": "percent", "status": "normal"}]
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            plugin.success(items)
            output = json.loads(mock_out.getvalue())
        self.assertIn("schemaVersion", output)
        self.assertEqual(output["schemaVersion"], 1)


class TestFailureFormat(unittest.TestCase):
    """failure() must output {"error": "message"} with no items."""

    def test_failure_has_error_field(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            plugin.failure("test error")
            output = json.loads(mock_out.getvalue())
        self.assertIn("error", output)
        self.assertEqual(output["error"], "test error")

    def test_failure_has_no_items(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            plugin.failure("test error")
            output = json.loads(mock_out.getvalue())
        self.assertNotIn("items", output)


class TestMaintainCacheRefreshesToday(unittest.TestCase):
    """maintain_cache must re-scan today's data on subsequent runs (gap_days == 0).

    Regression test for bug: previously, `if gap_days <= 0: return cache` froze today's
    data after the first scan of the day, so usage that happened later wouldn't show up.
    """

    def _write_jsonl(self, path, ts_iso, model, tokens):
        record = {
            "type": "assistant",
            "timestamp": ts_iso,
            "message": {
                "id": f"msg-{ts_iso}",
                "model": model,
                "usage": {"input_tokens": 0, "output_tokens": tokens, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            },
        }
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def test_today_is_rescanned_when_gap_days_is_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects = os.path.join(tmp, "projects", "p1")
            os.makedirs(projects)
            jsonl = os.path.join(projects, "session.jsonl")

            today_str = datetime.now().strftime("%Y-%m-%d")
            now = datetime.now().astimezone()
            earlier = now - timedelta(minutes=10)
            later = now - timedelta(minutes=2)

            # First run: today has 100 tokens
            self._write_jsonl(jsonl, earlier.isoformat(), "claude-sonnet", 100)
            result1 = plugin.maintain_cache(tmp)
            self.assertEqual(result1.get(today_str, {}).get("claude-sonnet", 0), 100)

            # Append more usage in the same day — simulate user activity since first run
            self._write_jsonl(jsonl, later.isoformat(), "claude-sonnet", 250)

            # Second run (same day, gap_days == 0) — must pick up the 250 new tokens
            result2 = plugin.maintain_cache(tmp)
            self.assertEqual(
                result2.get(today_str, {}).get("claude-sonnet", 0),
                350,
                "Today's data must be re-scanned on subsequent runs, not returned from cache as-is",
            )


if __name__ == "__main__":
    unittest.main()
