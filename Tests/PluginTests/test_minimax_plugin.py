"""Tests for minimax-usage-plugin.py across supported Python interpreters."""

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


PLUGIN_PATH = Path(__file__).parent.parent.parent / "Resources" / "BundledPlugins" / "minimax-usage-plugin.py"
HOMEBREW_PREFIX = os.environ.get("HOMEBREW_PREFIX")
HOMEBREW_PYTHON = Path(HOMEBREW_PREFIX) / "bin/python3" if HOMEBREW_PREFIX else None
HOMEBREW_ENVIRONMENT = {
    "HOMEBREW_PREFIX": HOMEBREW_PREFIX or "",
    "HOMEBREW_CELLAR": os.environ.get("HOMEBREW_CELLAR", str(Path(HOMEBREW_PREFIX) / "Cellar")) if HOMEBREW_PREFIX else "",
    "HOMEBREW_REPOSITORY": os.environ.get("HOMEBREW_REPOSITORY", HOMEBREW_PREFIX or ""),
}


def expected_interpreters():
    interpreters = [Path("/usr/bin/python3")]
    if HOMEBREW_PYTHON is not None:
        interpreters.append(HOMEBREW_PYTHON)
    return interpreters


def available_interpreters():
    for interpreter in expected_interpreters():
        if interpreter.exists():
            yield interpreter


def run_plugin_with_interpreter(interpreter: Path) -> dict:
    payload = {
        "base_resp": {"status_code": 0},
        "model_remains": [
            {
                "model_name": "MiniMax-M*",
                "current_interval_usage_count": 0,
                "current_interval_total_count": 1500,
                "current_weekly_usage_count": 3,
                "current_weekly_total_count": 15000,
                "start_time": 0,
                "end_time": 5 * 60 * 60 * 1000,
                "weekly_start_time": 0,
                "weekly_end_time": 7 * 24 * 60 * 60 * 1000,
                "remains_time": 1,
                "weekly_remains_time": 2,
            }
        ],
    }
    wrapper = textwrap.dedent(
        f"""
        import importlib.util
        import sys

        plugin_path = {str(PLUGIN_PATH)!r}
        payload = {payload!r}

        spec = importlib.util.spec_from_file_location("minimax_plugin", plugin_path)
        plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin)
        plugin.fetch_remains = lambda api_key: payload
        sys.argv = ["minimax-usage-plugin.py", "--usageboard-param", "API_KEY=fake"]
        raise SystemExit(plugin.main())
        """
    )

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as file:
        file.write(wrapper)
        wrapper_path = file.name

    try:
        env = os.environ.copy()
        env.update({
            "PYTHONIOENCODING": "utf-8",
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
        })
        if HOMEBREW_PYTHON is not None and interpreter == HOMEBREW_PYTHON:
            env.update(HOMEBREW_ENVIRONMENT)
        result = subprocess.run(
            [str(interpreter), wrapper_path],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
    finally:
        os.unlink(wrapper_path)

    return json.loads(result.stdout)


class TestMiniMaxInterpreterCompatibility(unittest.TestCase):
    def test_output_decodes_with_expected_interpreters(self):
        interpreters = list(available_interpreters())
        if not interpreters:
            self.skipTest("No configured Python interpreters are available")

        for interpreter in interpreters:
            with self.subTest(interpreter=str(interpreter)):
                output = run_plugin_with_interpreter(interpreter)
                self.assertEqual(output["schemaVersion"], 1)
                self.assertEqual(output["badge"], "Starter")
                self.assertEqual(len(output["items"]), 2)
                self.assertEqual(output["items"][0]["displayStyle"], "ratio")
                self.assertEqual(output["items"][0]["status"], "normal")
                self.assertIn(".", output["items"][0]["resetAt"])
                self.assertTrue(output["items"][0]["resetAt"].endswith("Z"))


if __name__ == "__main__":
    unittest.main()
