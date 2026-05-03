#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "FlowerCloud",
#   "icon": "https://api-flowercloud.com/favicon.ico",
#   "description": "查询 FlowerCloud 代理用量",
#   "parameters": [
#     {
#       "name": "TOKEN",
#       "label": "Token",
#       "type": "secret",
#       "required": true,
#       "placeholder": "FlowerCloud Authentication Token"
#     }
#   ]
# }
# /UsageBoardPlugin
"""UsageBoard plugin for FlowerCloud proxy traffic usage."""

from __future__ import annotations

import calendar
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


ENDPOINT = "https://api.xmancdn.net/osubscribe.php"
SCHEMA_VERSION = 1
TRAFFIC_PATTERN = re.compile(
    r"Traffic:\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?B)\s*\|\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?B)",
    re.IGNORECASE,
)
EXPIRE_PATTERN = re.compile(r"Expire:\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)


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


def get_token(argv: list[str]) -> str | None:
    return parse_usageboard_params(argv).get("TOKEN")


def fetch_subscription(token: str) -> str:
    query = urllib.parse.urlencode({"token2": token, "sip002": "1", "ss": "1"})
    request = urllib.request.Request(f"{ENDPOINT}?{query}")
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read().decode("utf-8", errors="replace")


def url_decode(text: str) -> str:
    decoded = text
    for _ in range(3):
        next_decoded = urllib.parse.unquote_plus(decoded)
        if next_decoded == decoded:
            return decoded
        decoded = next_decoded
    return decoded


def gb_value(value: str, unit: str) -> float:
    multipliers = {
        "KB": 1 / 1024 / 1024,
        "MB": 1 / 1024,
        "GB": 1,
        "TB": 1024,
    }
    return float(value) * multipliers.get(unit.upper(), 1)


def next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def monthly_reset_at(day: int, now: datetime | None = None) -> datetime:
    current = now or datetime.now().astimezone()
    year = current.year
    month = current.month
    if current.day >= day:
        year, month = next_month(year, month)

    while day > calendar.monthrange(year, month)[1]:
        year, month = next_month(year, month)

    return datetime(year, month, day, tzinfo=current.tzinfo)


def reset_at_iso(value: str | None, now: datetime | None = None) -> str | None:
    if not value:
        return None
    parsed = datetime.strptime(value, "%Y-%m-%d")
    reset_at = monthly_reset_at(parsed.day, now=now)
    return reset_at.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def status_for(used: float, total: float) -> str:
    pct = used / total * 100 if total > 0 else 0
    if pct >= 90:
        return "critical"
    if pct >= 75:
        return "warning"
    return "normal"


def parse_items(raw_text: str) -> list[dict[str, Any]]:
    decoded = url_decode(raw_text)
    traffic_match = TRAFFIC_PATTERN.search(decoded)
    if not traffic_match:
        return []

    used = gb_value(traffic_match.group(1), traffic_match.group(2))
    total = gb_value(traffic_match.group(3), traffic_match.group(4))
    expire_match = EXPIRE_PATTERN.search(decoded)
    reset_at = reset_at_iso(expire_match.group(1) if expire_match else None)

    return [
        {
            "id": "flowercloud-traffic",
            "name": "代理流量",
            "used": round(max(used, 0), 2),
            "limit": round(max(total, 0), 2),
            "displayStyle": "ratio",
            "resetAt": reset_at,
            "status": status_for(used, total),
        }
    ]


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
                        "id": "flowercloud-error",
                        "name": f"FlowerCloud 查询失败：{message}",
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
    token = get_token(sys.argv[1:])
    if not token:
        return failure("请在插件设置中配置 Token")

    try:
        items = parse_items(fetch_subscription(token))
        if not items:
            return failure("响应中没有可识别的流量或过期信息")
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
