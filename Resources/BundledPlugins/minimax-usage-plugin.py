#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "MiniMax",
#   "description": "查询 MiniMax Coding Plan 用量",
#   "parameters": [
#     {
#       "name": "API_KEY",
#       "label": "Api Key",
#       "type": "secret",
#       "required": true,
#       "placeholder": "MiniMax API Key"
#     }
#   ]
# }
# /UsageBoardPlugin
"""UsageBoard plugin for MiniMax Coding Plan quota usage."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any


ENDPOINT = "https://www.minimaxi.com/v1/api/openplatform/coding_plan/remains"
SCHEMA_VERSION = 1


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def utc_now_iso() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


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


def fetch_remains(api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        ENDPOINT,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def model_display_name(model_name: str) -> str:
    if model_name == "MiniMax-M*":
        return "文本生成"
    if model_name == "coding-plan-search":
        return "搜索"
    if model_name == "coding-plan-vlm":
        return "视觉"
    if model_name == "speech-hd":
        return "语音"
    if model_name == "music-cover":
        return "翻唱"
    if model_name == "lyrics_generation":
        return "歌词"
    if model_name.startswith("image-"):
        return "图像"
    if model_name.startswith("music-"):
        return model_name.replace("music-", "音乐 v")
    if model_name.startswith("MiniMax-Hailuo-"):
        return model_name.replace("MiniMax-Hailuo-", "视频 v")
    return model_name


def interval_label(model: dict[str, Any]) -> str:
    time_diff_ms = numeric(model.get("end_time")) - numeric(model.get("start_time"))
    hours_diff = time_diff_ms / 1000 / 3600
    if hours_diff <= 5.1:
        return "5小时"
    if hours_diff <= 24.1:
        return "天"
    if hours_diff <= 168.1:
        return "周"
    return "周期"


def numeric(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0
    return 0


def reset_at_from_remaining_ms(value: Any) -> str | None:
    remaining_ms = numeric(value)
    if remaining_ms <= 0:
        return None
    reset_at = utc_now() + timedelta(milliseconds=remaining_ms)
    return reset_at.isoformat().replace("+00:00", "Z")


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


def item(item_id: str, name: str, used: float, total: float, reset_at: str | None) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "used": max(used, 0),
        "limit": max(total, 0),
        "displayStyle": "ratio",
        "resetAt": reset_at,
        "status": status_for(used, total),
        "color": color_for(used, total),
    }


PLAN_BADGES = {600: "Starter", 1500: "Plus", 4500: "Max"}


def build_items(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    models = payload.get("model_remains", [])
    if not isinstance(models, list):
        return [], None

    badge: str | None = None
    output: list[dict[str, Any]] = []
    for model in models:
        if not isinstance(model, dict):
            continue

        raw_name = str(model.get("model_name", "unknown"))
        name = model_display_name(raw_name)
        slug = raw_name.replace(" ", "-").replace("/", "-").lower()

        interval_total = numeric(model.get("current_interval_total_count"))
        interval_remaining = numeric(model.get("current_interval_usage_count"))
        interval_used = interval_total - interval_remaining
        weekly_total = numeric(model.get("current_weekly_total_count"))
        weekly_remaining = numeric(model.get("current_weekly_usage_count"))
        weekly_used = weekly_total - weekly_remaining if weekly_total > 0 else 0

        if raw_name == "MiniMax-M*" and badge is None:
            badge = PLAN_BADGES.get(int(interval_total))

        if interval_total > 0:
            period = interval_label(model)
            output.append(
                item(
                    f"minimax-{slug}-interval",
                    f"{name} ({period})",
                    interval_used,
                    interval_total,
                    reset_at_from_remaining_ms(model.get("remains_time")),
                )
            )

        if weekly_total > 0:
            output.append(
                item(
                    f"minimax-{slug}-week",
                    f"{name} (周)",
                    weekly_used,
                    weekly_total,
                    reset_at_from_remaining_ms(model.get("weekly_remains_time")),
                )
            )

    return output, badge


def success(items: list[dict[str, Any]], badge: str | None = None) -> int:
    result: dict[str, Any] = {"schemaVersion": SCHEMA_VERSION, "updatedAt": utc_now_iso(), "items": items}
    if badge:
        result["badge"] = badge
    print(json.dumps(result, ensure_ascii=False))
    return 0


def failure(message: str) -> int:
    print(
        json.dumps(
            {
                "schemaVersion": SCHEMA_VERSION,
                "updatedAt": utc_now_iso(),
                "items": [
                    {
                        "id": "minimax-error",
                        "name": f"MiniMax 查询失败：{message}",
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
        items, badge = build_items(fetch_remains(api_key))
        if not items:
            return failure("响应中没有可识别的配额项")
        return success(items, badge=badge)
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
