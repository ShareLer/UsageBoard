"""Tests for deepseek-usage-plugin-v2.py — run with: python3 -m unittest Tests.PluginTests.test_deepseek_plugin_v2"""

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

PLUGIN_PATH = Path(__file__).parent.parent.parent / "Resources" / "BundledPlugins" / "deepseek-usage-plugin-v2.py"


def load_plugin():
    plugin_dir = str(PLUGIN_PATH.parent)
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)
    spec = importlib.util.spec_from_file_location("deepseek_plugin_v2", PLUGIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


plugin = load_plugin()

FAKE_BALANCE_RESPONSE = {"balance_infos": [{"currency": "CNY", "total_balance": "50.0"}]}


def run_main(argv_extra=None):
    """Run plugin main() with given argv, return parsed stdout JSON."""
    argv = ["deepseek-usage-plugin-v2.py"] + (argv_extra or [])
    with patch("sys.argv", argv):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            try:
                plugin.main()
            except SystemExit:
                pass
            return json.loads(mock_out.getvalue())


class TestErrorFormat(unittest.TestCase):
    """Error output must use {"error": "message"} format with no items."""

    def test_missing_api_key_outputs_error_field_not_items(self):
        output = run_main([])
        self.assertIn("error", output)
        self.assertNotIn("items", output)

    def test_missing_api_key_exits_zero(self):
        with patch("sys.argv", ["deepseek-usage-plugin-v2.py"]):
            with patch("sys.stdout", new_callable=StringIO):
                try:
                    plugin.main()
                    exit_code = 0
                except SystemExit as e:
                    exit_code = e.code or 0
        self.assertEqual(exit_code, 0)


class TestColorForBalance(unittest.TestCase):
    """Test color threshold logic (inherited from v1)."""

    def test_zero_balance_is_red(self):
        self.assertEqual(plugin.color_for_balance(0, 100), "red")

    def test_custom_limit_scales_thresholds(self):
        self.assertEqual(plugin.color_for_balance(30, 200), "orange")

    def test_zero_limit_returns_none(self):
        self.assertIsNone(plugin.color_for_balance(50, 0))


class TestSchemaVersion(unittest.TestCase):
    """Success output must include schemaVersion."""

    def test_success_output_has_schema_version(self):
        argv = ["deepseek-usage-plugin-v2.py", "--usageboard-param", "API_KEY=fake", "--usageboard-param", "PLATFORM_TOKEN=fake"]
        with patch("sys.argv", argv):
            with patch.object(plugin, "fetch_balance", return_value=FAKE_BALANCE_RESPONSE):
                with patch.object(plugin, "fetch_platform_cost", return_value=None):
                    with patch.object(plugin, "fetch_platform_usage", return_value=None):
                            with patch("sys.stdout", new_callable=StringIO) as mock_out:
                                try:
                                    plugin.main()
                                except SystemExit:
                                    pass
                                output = json.loads(mock_out.getvalue())
        self.assertIn("schemaVersion", output)


class TestHistory(unittest.TestCase):
    """History persistence: load/save history JSON."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        tmp_file = os.path.join(self.tmp_dir, "deepseek-history.json")
        tmp_cache = os.path.join(self.tmp_dir, "deepseek-cache.json")
        self.patches = [
            patch.object(plugin, "HISTORY_DIR", self.tmp_dir),
            patch.object(plugin, "HISTORY_FILE", tmp_file),
            patch.object(plugin, "CACHE_FILE", tmp_cache),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp_dir)

    def test_load_history_returns_defaults_when_no_file(self):
        history = plugin.load_history()
        self.assertEqual(history["todayDate"], "")
        self.assertEqual(history["todayStartingBalance"], 0.0)
        self.assertEqual(history["dailyRecords"], [])

    def test_save_and_load_history_roundtrip(self):
        history = {
            "schemaVersion": 1,
            "todayDate": "2026-05-16",
            "todayStartingBalance": 100.0,
            "dailyRecords": [{"date": "2026-05-15", "consumption": 5.0}],
        }
        plugin.save_history(history)
        loaded = plugin.load_history()
        self.assertEqual(loaded["todayDate"], "2026-05-16")
        self.assertEqual(loaded["todayStartingBalance"], 100.0)
        self.assertEqual(len(loaded["dailyRecords"]), 1)

    def test_load_history_returns_defaults_on_corrupt_file(self):
        with open(os.path.join(self.tmp_dir, "deepseek-history.json"), "w") as f:
            f.write("not json")
        history = plugin.load_history()
        self.assertEqual(history["todayDate"], "")


class TestUpdateHistory(unittest.TestCase):
    """update_history(): day boundary detection, consumption calculation."""

    def test_first_run_sets_today_starting_balance(self):
        history = {"todayDate": "", "todayStartingBalance": 0, "dailyRecords": []}
        with patch.object(plugin, "date_type") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-05-16"
            result = plugin.update_history(history, 100.0)
        self.assertEqual(result["todayDate"], "2026-05-16")
        self.assertEqual(result["todayStartingBalance"], 100.0)

    def test_same_day_consumption_tracks_difference(self):
        history = {"todayDate": "2026-05-16", "todayStartingBalance": 100.0, "dailyRecords": []}
        with patch.object(plugin, "date_type") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-05-16"
            result = plugin.update_history(history, 95.0)
        today_rec = [r for r in result["dailyRecords"] if r["date"] == "2026-05-16"]
        self.assertEqual(len(today_rec), 1)
        self.assertEqual(today_rec[0]["consumption"], 5.0)

    def test_day_boundary_records_yesterday_consumption(self):
        history = {"todayDate": "2026-05-15", "todayStartingBalance": 100.0, "dailyRecords": []}
        with patch.object(plugin, "date_type") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-05-16"
            result = plugin.update_history(history, 90.0)
        may15_rec = [r for r in result["dailyRecords"] if r["date"] == "2026-05-15"]
        self.assertEqual(len(may15_rec), 1)
        self.assertEqual(may15_rec[0]["consumption"], 10.0)
        self.assertEqual(result["todayDate"], "2026-05-16")
        self.assertEqual(result["todayStartingBalance"], 90.0)

    def test_consumption_clamped_to_zero(self):
        history = {"todayDate": "2026-05-16", "todayStartingBalance": 100.0, "dailyRecords": []}
        with patch.object(plugin, "date_type") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-05-16"
            result = plugin.update_history(history, 200.0)
        today_rec = [r for r in result["dailyRecords"] if r["date"] == "2026-05-16"]
        self.assertEqual(today_rec[0]["consumption"], 0)

    def test_daily_records_trimmed_to_30(self):
        records = [{"date": f"2026-{m:02d}-{d:02d}", "consumption": 1.0}
                   for m in range(1, 6) for d in range(1, 29)][:35]
        history = {"todayDate": "2026-05-16", "todayStartingBalance": 100.0, "dailyRecords": records}
        with patch.object(plugin, "date_type") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-05-16"
            result = plugin.update_history(history, 95.0)
        self.assertLessEqual(len(result["dailyRecords"]), 30)


class TestBuildItems(unittest.TestCase):
    """build_items produces balance + per-model today-cost + cache rate items."""

    def make_translate(self):
        return plugin.make_translator({
            "consumption": {"zh-Hans": "消费", "en": "Cost"},
            "cache_rate": {"zh-Hans": "缓存率", "en": "Cache Rate"},
            "today_cost": {"zh-Hans": "今日消费", "en": "Today's Cost"},
        })

    def test_balance_item_always_present(self):
        data = {"balance_infos": [{"currency": "CNY", "total_balance": "58.91"}]}
        items = plugin.build_items(data, "zh-Hans", 100, self.make_translate())
        balance = [i for i in items if i["id"] == "balance-CNY"]
        self.assertEqual(len(balance), 1)
        self.assertEqual(balance[0]["used"], 58.91)

    def test_per_model_cost_items(self):
        data = {"balance_infos": [{"currency": "CNY", "total_balance": "100.0"}]}
        today_cost = {
            "date": "2026-05-16", "total": 7.7,
            "models": [
                {"name": "deepseek-v4-pro", "cost": 6.35},
                {"name": "deepseek-v4-flash", "cost": 1.35},
            ],
        }
        items = plugin.build_items(data, "zh-Hans", 100, self.make_translate(), today_cost)
        pro = [i for i in items if i["id"] == "today-deepseek-v4-pro"]
        flash = [i for i in items if i["id"] == "today-deepseek-v4-flash"]
        self.assertEqual(len(pro), 1)
        self.assertEqual(items[1]["name"], "pro 今日消费")
        self.assertEqual(items[1]["used"], 6.35)
        self.assertEqual(items[1]["limit"], 7.7)
        self.assertEqual(items[1]["color"], "orange")
        self.assertEqual(len(flash), 1)
        self.assertEqual(flash[0]["name"], "flash 今日消费")
        self.assertEqual(flash[0]["used"], 1.35)
        self.assertEqual(flash[0]["limit"], 7.7)
        self.assertEqual(flash[0]["color"], "orange")

    def test_no_cost_items_when_today_cost_none(self):
        data = {"balance_infos": [{"currency": "CNY", "total_balance": "100.0"}]}
        items = plugin.build_items(data, "zh-Hans", 100, self.make_translate(), None)
        cost_items = [i for i in items if i["id"].startswith("today-")]
        self.assertEqual(len(cost_items), 0)

    def test_no_cost_items_when_total_zero(self):
        data = {"balance_infos": [{"currency": "CNY", "total_balance": "100.0"}]}
        today_cost = {"date": "2026-05-16", "total": 0, "models": []}
        items = plugin.build_items(data, "zh-Hans", 100, self.make_translate(), today_cost)
        cost_items = [i for i in items if i["id"].startswith("today-")]
        self.assertEqual(len(cost_items), 0)

    def test_cache_rate_items_appear_below_cost(self):
        data = {"balance_infos": [{"currency": "CNY", "total_balance": "100.0"}]}
        today_cost = {
            "date": "2026-05-16", "total": 7.7,
            "models": [
                {"name": "deepseek-v4-pro", "cost": 6.35},
            ],
        }
        cache_rates = {"pro": 99.1, "flash": 98.6}
        items = plugin.build_items(data, "zh-Hans", 100, self.make_translate(), today_cost, cache_rates)
        cache = [i for i in items if i["id"].startswith("cache-")]
        self.assertEqual(len(cache), 1)
        self.assertEqual(cache[0]["name"], "pro缓存率")
        self.assertEqual(cache[0]["used"], 99.1)
        self.assertEqual(cache[0]["limit"], 100)
        self.assertEqual(cache[0]["displayStyle"], "percent2")
        # Cost row should be immediately before its cache row
        cost_idx = next(i for i, v in enumerate(items) if v["id"] == "today-deepseek-v4-pro")
        cache_idx = next(i for i, v in enumerate(items) if v["id"] == "cache-deepseek-v4-pro")
        self.assertEqual(cache_idx, cost_idx + 1)

    def test_today_cost_from_api_flow(self):
        """Integration: fetch_platform_cost data feeds into build_items."""
        records = [
            {"date": "2026-05-16", "total": 7.7, "models": [
                {"name": "deepseek-v4-pro", "cost": 6.35},
                {"name": "deepseek-v4-flash", "cost": 1.35},
            ]},
        ]
        today_cost = next((r for r in records if r["date"] == "2026-05-16"), None)
        data = {"balance_infos": [{"currency": "CNY", "total_balance": "100.0"}]}
        items = plugin.build_items(data, "zh-Hans", 100, self.make_translate(), today_cost)
        cost_items = [i for i in items if i["id"].startswith("today-")]
        self.assertEqual(len(cost_items), 2)
        self.assertEqual(cost_items[0]["color"], "orange")


class TestBuildChart(unittest.TestCase):
    """build_chart produces daily consumption trend chart."""

    def make_translate(self):
        return plugin.make_translator({"cost": {"zh-Hans": "消费", "en": "Cost"}})

    def test_chart_has_correct_structure(self):
        history = {
            "todayDate": "2026-05-16",
            "todayStartingBalance": 50.0,
            "dailyRecords": [
                {"date": "2026-04-17", "consumption": 3.1},
                {"date": "2026-04-18", "consumption": 5.2},
            ],
        }
        chart = plugin.build_chart(history, "zh-Hans", self.make_translate())
        self.assertIsNotNone(chart)
        self.assertEqual(chart["kind"], "line")
        self.assertEqual(chart["period"], "30d")
        self.assertEqual(chart["bucketUnit"], "day")
        self.assertEqual(len(chart["buckets"]), 2)
        self.assertEqual(chart["buckets"][0]["id"], "2026-04-17")
        self.assertEqual(chart["buckets"][0]["segments"][0]["model"], "消费")
        self.assertEqual(chart["buckets"][0]["segments"][0]["tokens"], 3.1)

    def test_chart_sorted_by_date(self):
        history = {
            "todayDate": "2026-05-16",
            "todayStartingBalance": 50.0,
            "dailyRecords": [
                {"date": "2026-05-01", "consumption": 2.0},
                {"date": "2026-04-15", "consumption": 1.0},
            ],
        }
        chart = plugin.build_chart(history, "en", self.make_translate())
        self.assertEqual(chart["buckets"][0]["id"], "2026-04-15")
        self.assertEqual(chart["buckets"][1]["id"], "2026-05-01")

    def test_chart_returns_none_when_no_records(self):
        history = {"todayDate": "2026-05-16", "todayStartingBalance": 100.0, "dailyRecords": []}
        self.assertIsNone(plugin.build_chart(history, "en", self.make_translate()))


class TestBuildUsageChart(unittest.TestCase):
    """build_usage_chart produces chart from platform usage API data."""

    def test_usage_chart_has_input_output_segments(self):
        records = [
            {
                "date": "2026-04-17", "total": 4300,
                "models": [
                    {"name": "deepseek-v4-pro", "input": 2000, "output": 1100},
                    {"name": "deepseek-v4-flash", "input": 800, "output": 400},
                ],
            },
        ]
        chart = plugin.build_usage_chart(records)
        self.assertIsNotNone(chart)
        self.assertEqual(chart["kind"], "line")
        self.assertEqual(chart["bucketUnit"], "day")
        self.assertEqual(len(chart["buckets"]), 1)
        # Two models × 2 segments each = 4 segments, flash before pro
        segs = chart["buckets"][0]["segments"]
        self.assertEqual(len(segs), 4)
        self.assertEqual(segs[0]["model"], "flash-in")
        self.assertEqual(segs[0]["tokens"], 800)
        self.assertEqual(segs[1]["model"], "flash-out")
        self.assertEqual(segs[1]["tokens"], 400)
        self.assertEqual(segs[2]["model"], "pro-in")
        self.assertEqual(segs[2]["tokens"], 2000)
        self.assertEqual(segs[3]["model"], "pro-out")
        self.assertEqual(segs[3]["tokens"], 1100)

    def test_usage_chart_skips_zero_token_days(self):
        """Days with zero tokens have empty segments."""
        records = [
            {
                "date": "2026-05-01", "total": 0,
                "models": [
                    {"name": "deepseek-v4-pro", "input": 0, "output": 0},
                    {"name": "deepseek-v4-flash", "input": 0, "output": 0},
                ],
            },
        ]
        chart = plugin.build_usage_chart(records)
        self.assertEqual(len(chart["buckets"][0]["segments"]), 0)

    def test_usage_chart_limited_to_30_days(self):
        records = [
            {"date": f"2026-{m:02d}-{d:02d}", "total": 1000, "models": [{"name": "m", "input": 1000, "output": 0}]}
            for m in range(1, 3) for d in range(1, 31)
        ]
        chart = plugin.build_usage_chart(records)
        self.assertLessEqual(len(chart["buckets"]), 30)

    def test_usage_chart_returns_none_when_no_records(self):
        self.assertIsNone(plugin.build_usage_chart([]))


class TestFetchPlatformUsage(unittest.TestCase):
    """fetch_platform_usage parses DeepSeek platform API response."""

    def test_fetch_platform_usage_parses_valid_response(self):
        fake_body = json.dumps({
            "code": 0,
            "msg": "",
            "data": {
                "biz_code": 0,
                "biz_msg": "",
                "biz_data": {
                    "total": [],
                    "days": [
                        {
                            "date": "2026-05-01",
                            "data": [
                                {
                                    "model": "deepseek-chat",
                                    "usage": [
                                        {"type": "PROMPT_TOKEN", "amount": "500"},
                                        {"type": "RESPONSE_TOKEN", "amount": "1200"},
                                    ],
                                },
                            ],
                        },
                        {
                            "date": "2026-05-02",
                            "data": [
                                {
                                    "model": "deepseek-v4-pro",
                                    "usage": [
                                        {"type": "PROMPT_TOKEN", "amount": "300"},
                                    ],
                                },
                            ],
                        },
                    ],
                },
            },
        })
        with patch.object(plugin, "urllib") as mock_urllib:
            mock_resp = unittest.mock.MagicMock()
            mock_resp.__enter__.return_value.read.return_value = fake_body
            mock_urllib.request.Request.return_value = None
            mock_urllib.request.urlopen.return_value = mock_resp

            records = plugin.fetch_platform_usage("fake-token", 5, 2026)
            self.assertIsNotNone(records)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["date"], "2026-05-01")
            self.assertEqual(records[0]["total"], 1700)
            self.assertEqual(len(records[0]["models"]), 1)
            self.assertEqual(records[0]["models"][0]["name"], "deepseek-chat")
            self.assertEqual(records[0]["models"][0]["input"], 500)
            self.assertEqual(records[0]["models"][0]["output"], 1200)
            self.assertEqual(records[1]["date"], "2026-05-02")
            self.assertEqual(records[1]["total"], 300)
            self.assertEqual(records[1]["models"][0]["name"], "deepseek-v4-pro")
            self.assertEqual(records[1]["models"][0]["input"], 300)
            self.assertEqual(records[1]["models"][0]["output"], 0)

    def test_fetch_platform_usage_returns_none_on_error(self):
        with patch.object(plugin, "urllib") as mock_urllib:
            mock_urllib.request.urlopen.side_effect = Exception("network error")
            records = plugin.fetch_platform_usage("fake-token", 5, 2026)
            self.assertIsNone(records)


class TestFetchPlatformCost(unittest.TestCase):
    """fetch_platform_cost parses DeepSeek platform cost API response."""

    def test_fetch_platform_cost_parses_valid_response(self):
        fake_body = json.dumps({
            "code": 0,
            "msg": "",
            "data": {
                "biz_code": 0,
                "biz_msg": "",
                "biz_data": [{
                    "total": [],
                    "days": [
                        {
                            "date": "2026-05-01",
                            "data": [
                                {
                                    "model": "deepseek-chat",
                                    "usage": [
                                        {"type": "PROMPT_TOKEN", "amount": "0.5"},
                                        {"type": "RESPONSE_TOKEN", "amount": "1.2"},
                                    ],
                                },
                            ],
                        },
                    ],
                }],
            },
        })
        with patch.object(plugin, "urllib") as mock_urllib:
            mock_resp = unittest.mock.MagicMock()
            mock_resp.__enter__.return_value.read.return_value = fake_body
            mock_urllib.request.Request.return_value = None
            mock_urllib.request.urlopen.return_value = mock_resp

            records = plugin.fetch_platform_cost("fake-token", 5, 2026)
            self.assertIsNotNone(records)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["date"], "2026-05-01")
            self.assertEqual(records[0]["total"], 1.7)
            self.assertEqual(records[0]["models"][0]["name"], "deepseek-chat")
            self.assertEqual(records[0]["models"][0]["cost"], 1.7)

    def test_fetch_platform_cost_returns_none_on_error(self):
        with patch.object(plugin, "urllib") as mock_urllib:
            mock_urllib.request.urlopen.side_effect = Exception("network error")
            records = plugin.fetch_platform_cost("fake-token", 5, 2026)
            self.assertIsNone(records)


class TestFetchCacheRates(unittest.TestCase):
    """fetch_cache_rates extracts per-model cache hit rates."""

    def test_fetch_cache_rates_parses_valid_response(self):
        fake_body = json.dumps({
            "code": 0, "msg": "", "data": {
                "biz_code": 0, "biz_msg": "",
                "biz_data": {
                    "total": [], "days": [
                        {
                            "date": "2026-05-16",
                            "data": [
                                {
                                    "model": "deepseek-v4-pro",
                                    "usage": [
                                        {"type": "PROMPT_CACHE_HIT_TOKEN", "amount": "900"},
                                        {"type": "PROMPT_CACHE_MISS_TOKEN", "amount": "100"},
                                        {"type": "PROMPT_TOKEN", "amount": "0"},
                                    ],
                                },
                            ],
                        },
                    ],
                },
            },
        })
        with patch.object(plugin, "urllib") as mock_urllib:
            mock_resp = unittest.mock.MagicMock()
            mock_resp.__enter__.return_value.read.return_value = fake_body
            mock_urllib.request.Request.return_value = None
            mock_urllib.request.urlopen.return_value = mock_resp
            rates = plugin.fetch_cache_rates("fake-token", 5, 2026, "2026-05-16")
            self.assertIsNotNone(rates)
            self.assertIn("pro", rates)
            self.assertEqual(rates["pro"], 90.0)

    def test_fetch_cache_rates_returns_none_on_no_match(self):
        fake_body = json.dumps({
            "code": 0, "msg": "", "data": {
                "biz_code": 0, "biz_msg": "",
                "biz_data": {"total": [], "days": []},
            },
        })
        with patch.object(plugin, "urllib") as mock_urllib:
            mock_resp = unittest.mock.MagicMock()
            mock_resp.__enter__.return_value.read.return_value = fake_body
            mock_urllib.request.Request.return_value = None
            mock_urllib.request.urlopen.return_value = mock_resp
            rates = plugin.fetch_cache_rates("fake-token", 5, 2026, "2026-05-16")
            self.assertIsNone(rates)


if __name__ == "__main__":
    unittest.main()
