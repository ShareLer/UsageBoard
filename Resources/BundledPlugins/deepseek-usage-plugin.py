#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "DeepSeek",
#   "icon": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/deepseek-color.png",
#   "description": "查询 DeepSeek API 余额",
#   "parameters": [
#     {
#       "name": "API_KEY",
#       "label": "Api Key",
#       "type": "secret",
#       "required": true,
#       "placeholder": "DeepSeek API Key"
#     }
#   ]
# }
# /UsageBoardPlugin
"""UsageBoard plugin for DeepSeek API balance."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone


ENDPOINT = "https://api.deepseek.com/user/balance"
MIN_LIMIT = 100.0


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


def fetch_balance(api_key: str) -> list[dict]:
    request = urllib.request.Request(
        ENDPOINT,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read())

    items: list[dict] = []
    for info in data.get("balance_infos", []):
        currency = info.get("currency", "CNY")
        total_balance = float(info.get("total_balance", "0"))
        limit = max(total_balance, MIN_LIMIT)
        suffix = f" ({currency})" if currency != "CNY" else ""
        color = "red" if total_balance <= 10 else "orange" if total_balance <= 20 else "yellow" if total_balance <= 40 else None
        items.append({
            "id": f"balance-{currency}",
            "name": f"余额{suffix}",
            "used": round(total_balance, 2),
            "limit": round(limit, 2),
            "displayStyle": "ratio",
            "status": "normal",
            "color": color,
        })
    return items


def main() -> None:
    params = parse_usageboard_params(sys.argv[1:])
    api_key = params.get("API_KEY", "")
    if not api_key:
        print(json.dumps({"error": "缺少 API_KEY 参数"}))
        sys.exit(1)

    try:
        items = fetch_balance(api_key)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(json.dumps({"error": f"HTTP {e.code}: {body}"}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    print(json.dumps({
        "updatedAt": utc_now_iso(),
        "items": items,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
