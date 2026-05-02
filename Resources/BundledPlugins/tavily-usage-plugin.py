#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "Tavily",
#   "description": "查询 Tavily Search 月度用量",
#   "parameters": [
#     {
#       "name": "API_KEY",
#       "label": "Api Key",
#       "type": "secret",
#       "required": true,
#       "placeholder": "Tavily API Key"
#     }
#   ]
# }
# /UsageBoardPlugin
"""UsageBoard plugin for Tavily quota usage."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from calendar import monthrange
from typing import Any


ENDPOINT = "https://api.tavily.com/usage"
SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_usageboard_params(argv: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    index = 0
    while index < len(argv):
        if argv[index] == "--usageboard-param" and index + 1 < len(argv):
            key_value = argv[index + 1]
            if "=" in key_value:
                key, value = key_value.split("=", 1)
                if key:
                    values[key] = value
            index += 2
        else:
            index += 1
    return values


def get_api_key(argv: list[str]) -> str | None:
    return parse_usageboard_params(argv).get("API_KEY")


def fetch_usage(api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(ENDPOINT, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def next_month_start_iso() -> str:
    now = datetime.now(timezone.utc)
    year = now.year + (1 if now.month == 12 else 0)
    month = (now.month % 12) + 1
    return datetime(year, month, 1, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def numeric(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0
    return 0


def status_for(used: float, total: float) -> str:
    pct = used / total * 100 if total > 0 else 0
    if pct >= 90:
        return "critical"
    if pct >= 75:
        return "warning"
    return "normal"


def color_for(used: float, total: float) -> str:
    pct = used / total * 100 if total > 0 else 0
    if pct >= 90:
        return "red"
    if pct >= 80:
        return "orange"
    if pct >= 60:
        return "yellow"
    return "blue"


def item(item_id: str, name: str, used: float, total: float, color: str = "blue") -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "used": max(used, 0),
        "limit": max(total, 0),
        "displayStyle": "ratio",
        "resetAt": next_month_start_iso(),
        "status": status_for(used, total),
        "color": color,
    }


def build_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    account = payload.get("account", {})
    if not isinstance(account, dict):
        return []

    plan_limit = numeric(account.get("plan_limit"))
    if plan_limit <= 0:
        return []

    plan_usage = numeric(account.get("plan_usage"))
    output = [item("tavily-total-month", "总用量", plan_usage, plan_limit, color_for(plan_usage, plan_limit))]

    details = [
        ("tavily-search", "搜索", "search_usage"),
        ("tavily-crawl", "爬取", "crawl_usage"),
        ("tavily-extract", "提取", "extract_usage"),
        ("tavily-map", "地图", "map_usage"),
        ("tavily-research", "研究", "research_usage"),
    ]
    for item_id, name, key in details:
        used = numeric(account.get(key))
        if used > 0:
            output.append(item(item_id, name, used, plan_usage))

    return output


def success(items: list[dict[str, Any]]) -> int:
    print(json.dumps({"schemaVersion": SCHEMA_VERSION, "updatedAt": utc_now_iso(), "items": items}, ensure_ascii=False))
    return 0


def failure(message: str) -> int:
    print(
        json.dumps(
            {
                "schemaVersion": SCHEMA_VERSION,
                "updatedAt": utc_now_iso(),
                "items": [
                    {
                        "id": "tavily-error",
                        "name": f"Tavily 查询失败：{message}",
                        "used": 0,
                        "limit": 1,
                        "displayStyle": "percent",
                        "resetAt": None,
                        "status": "critical",
                    }
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    api_key = get_api_key(sys.argv[1:])
    if not api_key:
        return failure("请在插件设置中配置 Api Key")

    try:
        items = build_items(fetch_usage(api_key))
        if not items:
            return failure("响应中没有可识别的配额项")
        return success(items)
    except urllib.error.HTTPError as error:
        return failure(f"HTTP {error.code}")
    except urllib.error.URLError as error:
        return failure(str(error.reason))
    except TimeoutError:
        return failure("请求超时")
    except Exception as error:
        return failure(str(error))


if __name__ == "__main__":
    sys.exit(main())
