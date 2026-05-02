#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "Codex",
#   "description": "查询 OpenAI Codex CLI 用量配额",
#   "parameters": [
#     {
#       "name": "AUTH_PATH",
#       "label": "Auth 文件路径",
#       "type": "string",
#       "required": false,
#       "defaultValue": "~/.codex/auth.json",
#       "placeholder": "~/.codex/auth.json"
#     }
#   ]
# }
# /UsageBoardPlugin
"""UsageBoard plugin for OpenAI Codex CLI quota usage."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


ENDPOINT = "https://chatgpt.com/backend-api/wham/usage"
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


def load_auth(path: str) -> dict[str, Any] | None:
    expanded = os.path.expanduser(path)
    if not os.path.isfile(expanded):
        return None
    try:
        with open(expanded, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def fetch_usage(access_token: str, account_id: str) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "ChatGPT-Account-Id": account_id,
        "Origin": "https://chatgpt.com",
        "Referer": "https://chatgpt.com/",
        "User-Agent": "Mozilla/5.0",
    }
    request = urllib.request.Request(ENDPOINT, headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def epoch_ms_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return None
    timestamp = raw / 1000 if raw > 10**11 else raw
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_percent_left(window: dict[str, Any]) -> float | None:
    for key in ("percent_left", "remaining_percent"):
        value = window.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    used = window.get("used_percent")
    if used is not None:
        try:
            return max(0, 100 - float(used))
        except (TypeError, ValueError):
            pass
    return None


def get_reset_at(window: dict[str, Any]) -> str | None:
    for key in ("reset_time_ms", "reset_at"):
        value = window.get(key)
        if value is not None:
            return epoch_ms_to_iso(value)
    nested = window.get("primary_window")
    if isinstance(nested, dict):
        return get_reset_at(nested)
    return None


def color_for(percent: float) -> str:
    if percent <= 10:
        return "red"
    if percent <= 25:
        return "orange"
    if percent <= 50:
        return "yellow"
    return "blue"


def parse_window(data: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return None


def build_items(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    rate_limits = parse_window(payload, "rate_limit", "rate_limits")
    if not rate_limits:
        return [], None

    badge = payload.get("plan_type")
    if not isinstance(badge, str):
        badge = None

    items: list[dict[str, Any]] = []

    five_hour = parse_window(rate_limits, "five_hour", "five_hour_limit", "five_hour_rate_limit", "primary")
    weekly = parse_window(rate_limits, "weekly", "weekly_limit", "weekly_rate_limit", "secondary")

    if not five_hour:
        five_hour = parse_window(rate_limits, "primary_window")
    if not weekly:
        weekly = parse_window(rate_limits, "secondary_window")

    if five_hour:
        pct = get_percent_left(five_hour)
        if pct is not None:
            used = 100 - pct
            items.append({
                "id": "codex-five-hour",
                "name": "5 小时额度",
                "used": round(used, 1),
                "limit": 100,
                "displayStyle": "percent",
                "resetAt": get_reset_at(five_hour),
                "status": "critical" if pct <= 10 else "warning" if pct <= 25 else "normal",
                "color": color_for(pct),
            })

    if weekly:
        pct = get_percent_left(weekly)
        if pct is not None:
            used = 100 - pct
            items.append({
                "id": "codex-weekly",
                "name": "周额度",
                "used": round(used, 1),
                "limit": 100,
                "displayStyle": "percent",
                "resetAt": get_reset_at(weekly),
                "status": "critical" if pct <= 10 else "warning" if pct <= 25 else "normal",
                "color": color_for(pct),
            })

    return items, badge


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
                        "id": "codex-error",
                        "name": f"Codex 查询失败：{message}",
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
    params = parse_usageboard_params(sys.argv[1:])
    auth_path = params.get("AUTH_PATH", "") or os.path.expanduser("~/.codex/auth.json")

    auth = load_auth(auth_path)
    if not auth:
        return failure(f"未找到认证文件 {auth_path}")

    tokens = auth.get("tokens") if isinstance(auth.get("tokens"), dict) else {}
    access_token = tokens.get("access_token")
    account_id = tokens.get("account_id")
    if not access_token or not account_id:
        return failure("认证文件中缺少 access_token 或 account_id")

    try:
        items, badge = build_items(fetch_usage(access_token, account_id))
        if not items:
            return failure("响应中没有可识别的配额数据")
        return success(items, badge=badge)
    except urllib.error.HTTPError as error:
        if error.code == 401:
            return failure("Token 已过期，请重新登录 Codex")
        if error.code == 403:
            return failure("账号无权访问")
        return failure(f"HTTP {error.code}")
    except urllib.error.URLError as error:
        return failure(str(error.reason))
    except TimeoutError:
        return failure("请求超时")
    except Exception as error:
        return failure(str(error))


if __name__ == "__main__":
    sys.exit(main())
