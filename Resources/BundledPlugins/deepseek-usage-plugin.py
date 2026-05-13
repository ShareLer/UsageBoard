#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "DeepSeek",
#   "name@zh-Hans": "DeepSeek",
#   "name@en": "DeepSeek",
#   "icon": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/deepseek-color.png",
#   "description": "查询 DeepSeek API 余额",
#   "description@zh-Hans": "查询 DeepSeek API 余额",
#   "description@en": "Query DeepSeek API balance",
#   "parameters": [
#     {
#       "name": "API_KEY",
#       "label": "Api Key",
#       "label@zh-Hans": "Api Key",
#       "label@en": "API Key",
#       "type": "secret",
#       "required": true,
#       "placeholder": "DeepSeek API Key"
#     },
#     {
#       "name": "LIMIT",
#       "label": "Amount Limit",
#       "label@zh-Hans": "金额上限",
#       "label@en": "Amount Limit",
#       "type": "integer",
#       "required": false,
#       "defaultValue": "100",
#       "placeholder": "100"
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
DEFAULT_LIMIT = 100.0
SCHEMA_VERSION = 1


def color_for_balance(balance: float, limit: float) -> str | None:
    if limit <= 0:
        return None
    ratio = balance / limit
    if ratio <= 0.10:
        return "red"
    if ratio <= 0.20:
        return "orange"
    if ratio <= 0.40:
        return "yellow"
    return "blue"


def parse_limit(raw: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return value if value > 0 else DEFAULT_LIMIT


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


def app_language(params: dict[str, str]) -> str:
    return "en" if params.get("USAGEBOARD_LANGUAGE") == "en" else "zh-Hans"


TRANSLATIONS = {
    "balance":          {"zh-Hans": "余额",                              "en": "Balance"},
    "missing_api_key":  {"zh-Hans": "请在插件设置中配置 API Key",          "en": "Configure API Key in plugin settings"},
    "http_401":         {"zh-Hans": "API Key 无效，请检查配置",            "en": "Invalid API Key. Check your settings."},
    "http_403":         {"zh-Hans": "账号无权限访问",                      "en": "Access denied. Check your plan."},
    "http_429":         {"zh-Hans": "请求频率超限，请稍后重试",              "en": "Rate limited. Try again later."},
    "http_5xx":         {"zh-Hans": "服务暂时不可用 (HTTP {code})",        "en": "Service unavailable (HTTP {code})"},
    "http_other":       {"zh-Hans": "请求失败 (HTTP {code})",             "en": "Request failed (HTTP {code})"},
    "request_timeout":  {"zh-Hans": "请求超时，请检查网络",                 "en": "Request timed out. Check your network."},
    "network_error":    {"zh-Hans": "网络连接失败，请检查网络",              "en": "Network error. Check your connection."},
}


def translate(language: str, key: str, **kwargs) -> str:
    values = TRANSLATIONS.get(key, {})
    text = values.get(language) or values.get("zh-Hans") or key
    return text.format(**kwargs) if kwargs else text


def fetch_balance(api_key: str, language: str, limit_amount: float) -> list[dict]:
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
        suffix = f" ({currency})" if currency != "CNY" else ""
        items.append({
            "id": f"balance-{currency}",
            "name": f"{translate(language, 'balance')}{suffix}",
            "used": round(total_balance, 2),
            "limit": round(limit_amount, 2),
            "displayStyle": "ratio",
            "status": "normal",
            "color": color_for_balance(total_balance, limit_amount),
        })
    return items


def success(items: list[dict]) -> int:
    print(json.dumps({"schemaVersion": SCHEMA_VERSION, "updatedAt": utc_now_iso(), "items": items}, ensure_ascii=False))
    return 0


def failure(message: str) -> int:
    print(json.dumps({"error": message}, ensure_ascii=False))
    return 0


def main() -> int:
    params = parse_usageboard_params(sys.argv[1:])
    language = app_language(params)
    api_key = params.get("API_KEY", "")
    if not api_key:
        return failure(translate(language, "missing_api_key"))
    limit_amount = parse_limit(params.get("LIMIT", ""))

    try:
        items = fetch_balance(api_key, language, limit_amount)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return failure(translate(language, "http_401"))
        if e.code == 403:
            return failure(translate(language, "http_403"))
        if e.code == 429:
            return failure(translate(language, "http_429"))
        if e.code >= 500:
            return failure(translate(language, "http_5xx", code=e.code))
        return failure(translate(language, "http_other", code=e.code))
    except TimeoutError:
        return failure(translate(language, "request_timeout"))
    except Exception:
        return failure(translate(language, "network_error"))

    return success(items)


if __name__ == "__main__":
    sys.exit(main())
