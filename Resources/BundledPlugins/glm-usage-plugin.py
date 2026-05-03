#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "智谱",
#   "icon": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/zhipu-color.png",
#   "description": "查询智谱 Coding Plan 用量",
#   "parameters": [
#     {
#       "name": "API_KEY",
#       "label": "Api Key",
#       "type": "secret",
#       "required": true,
#       "placeholder": "Coding Plan API Key"
#     },
#     {
#       "name": "PROVIDER",
#       "label": "Provider",
#       "type": "choice",
#       "required": true,
#       "defaultValue": "GLM",
#       "options": [
#         {"label": "国内站", "value": "GLM"},
#         {"label": "国际站", "value": "ZAI"}
#       ]
#     }
#   ]
# }
# /UsageBoardPlugin
"""UsageBoard plugin for GLM quota usage."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


ENDPOINTS = {
    "GLM": "https://open.bigmodel.cn/api/monitor/usage/quota/limit",
    "ZAI": "https://api.z.ai/api/monitor/usage/quota/limit",
}
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
    params = parse_usageboard_params(argv)
    return params.get("API_KEY")


def get_provider(argv: list[str]) -> str:
    params = parse_usageboard_params(argv)
    provider = params.get("PROVIDER", "GLM").upper()
    return provider if provider in ENDPOINTS else "GLM"


def fetch_limits(api_key: str, provider: str) -> dict[str, Any]:
    request = urllib.request.Request(
        ENDPOINTS[provider],
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def reset_at_iso(limit: dict[str, Any]) -> str | None:
    reset_value = first_present(
        limit,
        (
            "nextResetTime",
            "nextResetTimestamp",
            "resetTime",
            "resetAt",
            "expireTime",
            "expiresAt",
        ),
    )
    timestamp = normalize_timestamp(reset_value)
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def first_present(source: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return value
    return None


def normalize_timestamp(value: Any) -> float | None:
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        if value.isdigit():
            value = float(value)
        else:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed.timestamp()
            except ValueError:
                return None

    if not isinstance(value, (int, float)) or value <= 0:
        return None

    # GLM docs describe nextResetTime as milliseconds, but accept seconds too
    # because some quota endpoints return 10-digit Unix timestamps.
    if value > 10_000_000_000:
        return float(value) / 1000
    return float(value)


def usage_from_percentage(limit: dict[str, Any]) -> tuple[float, float]:
    pct = limit.get("percentage", 0)
    if not isinstance(pct, (int, float)):
        pct = 0
    pct = max(0, min(float(pct), 100))
    return pct, 100


def usage_from_current_and_limit(limit: dict[str, Any]) -> tuple[float, float]:
    current = limit.get("currentValue", 0)
    usage_limit = limit.get("usage", 0)
    if not isinstance(current, (int, float)):
        current = 0
    if not isinstance(usage_limit, (int, float)):
        usage_limit = 0
    return max(float(current), 0), max(float(usage_limit), 0)


def period_for(limit: dict[str, Any]) -> tuple[str, str] | None:
    unit = limit.get("unit")
    number = limit.get("number")
    if unit == 3 and number == 5:
        return "5h", "5小时"
    if unit == 6 and number == 1:
        return "week", "周"
    if unit == 5 and number == 1:
        return "month", "月"
    return None


def quota_kind(limit: dict[str, Any]) -> tuple[str, str]:
    text = json.dumps(limit, ensure_ascii=False).lower()
    tool_markers = ("tool", "工具", "function", "mcp")
    text_markers = ("token", "text", "文本")

    if any(marker in text for marker in tool_markers):
        return "tool", "工具调用"
    if any(marker in text for marker in text_markers):
        return "text", "文本生成"
    if "currentValue" in limit or "usage" in limit:
        return "tool", "工具调用"
    return "text", "文本生成"


def usage_for(limit: dict[str, Any], kind: str) -> tuple[float, float, str]:
    if kind == "tool" and ("currentValue" in limit or "usage" in limit):
        used, total = usage_from_current_and_limit(limit)
        return used, total, "ratio"
    used, total = usage_from_percentage(limit)
    return used, total, "percent"


def item(
    item_id: str,
    name: str,
    used: float,
    limit: float,
    reset_at: str | None,
    display_style: str = "percent",
) -> dict[str, Any]:
    status = "unknown"
    pct = used / limit * 100 if limit > 0 else 0
    if pct >= 90:
        status = "critical"
    elif pct >= 75:
        status = "warning"
    else:
        status = "normal"

    return {
        "id": item_id,
        "name": name,
        "used": used,
        "limit": limit,
        "displayStyle": display_style,
        "resetAt": reset_at,
        "status": status,
        "color": color_for_percentage(pct),
    }


def color_for_percentage(pct: float) -> str:
    if pct >= 90:
        return "red"
    if pct >= 80:
        return "orange"
    if pct >= 60:
        return "yellow"
    return "blue"


def build_items(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    data = payload.get("data", {})
    limits = data.get("limits", [])
    if not isinstance(limits, list):
        return [], None

    badge = data.get("level")
    if not isinstance(badge, str):
        badge = None

    output: list[dict[str, Any]] = []

    for limit in limits:
        if not isinstance(limit, dict):
            continue

        period = period_for(limit)
        if period is None:
            continue

        period_id, period_label = period
        kind_id, kind_label = quota_kind(limit)
        used, total, display_style = usage_for(limit, kind_id)
        if total <= 0:
            continue
        reset_at = reset_at_iso(limit)

        output.append(
            item(
                f"glm-{kind_id}-{period_id}",
                f"{kind_label} ({period_label})",
                used,
                total,
                reset_at,
                display_style=display_style,
            )
        )

    display_names = {
        "glm-text-5h": "5 小时用量",
        "glm-text-week": "周用量",
        "glm-tool-month": "MCP 月用量",
    }
    order = {
        "glm-text-5h": 0,
        "glm-text-week": 1,
        "glm-tool-month": 2,
    }
    for entry in output:
        if entry["id"] in display_names:
            entry["name"] = display_names[entry["id"]]
    return sorted(output, key=lambda value: order.get(value["id"], 99)), badge


def success(items: list[dict[str, Any]], badge: str | None = None) -> int:
    result: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "updatedAt": utc_now_iso(),
        "items": items,
    }
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
                        "id": "glm-error",
                        "name": f"GLM 查询失败：{message}",
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
    provider = get_provider(sys.argv[1:])
    if not api_key:
        return failure("请在插件设置中配置 Api Key")

    try:
        payload = fetch_limits(api_key, provider)
        items, badge = build_items(payload)
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
