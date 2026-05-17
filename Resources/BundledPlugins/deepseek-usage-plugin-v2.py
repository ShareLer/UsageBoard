#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "DeepSeek-V4",
#   "name@zh-Hans": "DeepSeek-V4",
#   "name@en": "DeepSeek-V4",
#   "icon": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/deepseek-color.png",
#   "description": "查询 DeepSeek API 余额（含消费统计）",
#   "description@zh-Hans": "查询 DeepSeek API 余额（含消费统计）",
#   "description@en": "Query DeepSeek API balance with spending stats",
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
#     },
#     {
#       "name": "PLATFORM_TOKEN",
#       "label": "Platform Token",
#       "label@zh-Hans": "平台 Token",
#       "label@en": "Platform Token",
#       "type": "secret",
#       "required": true,
#       "placeholder": "DeepSeek Platform Token"
#     },
#     {
#       "name": "CHART_DAYS",
#       "label": "Chart Days",
#       "label@zh-Hans": "图表天数",
#       "label@en": "Chart Days",
#       "type": "integer",
#       "required": false,
#       "defaultValue": "30",
#       "placeholder": "30"
#     }
#   ]
# }
# /UsageBoardPlugin
"""UsageBoard plugin for DeepSeek API balance with spending tracking."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date as date_type
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _common import (  # noqa: E402
    failure,
    handle_http_error,
    handle_url_error,
    make_translator,
    parse_usageboard_params,
    success,
    utc_now_iso,
)


ENDPOINT = "https://api.deepseek.com/user/balance"
COST_API = "https://platform.deepseek.com/api/v0/usage/cost"
USAGE_API = "https://platform.deepseek.com/api/v0/usage/amount"
DEFAULT_LIMIT = 100.0

# FIXME: 后续改为可配置参数, 或复用 API_KEY
HISTORY_DIR = os.path.expanduser("~/Library/Application Support/UsageBoard")
HISTORY_FILE = os.path.join(HISTORY_DIR, "deepseek-history.json")
CACHE_FILE = os.path.join(HISTORY_DIR, "deepseek-cache.json")


def _short_model(name: str) -> str:
    return name.replace("deepseek-v4-", "").replace("deepseek-", "")


def _load_cache() -> dict[str, Any]:
    """Load API cache from disk. Returns {key: {cached_date, data}}."""
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict[str, Any]) -> None:
    """Save API cache to disk."""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, ensure_ascii=False)


def _fetch_cached(api_type: str, month: int, year: int, fetcher: Any) -> Any:
    """Fetch data with per-day caching. Re-fetches if cached date != today."""
    today = date_type.today().isoformat()
    key = f"{api_type}_{year}_{month}"
    cache = _load_cache()
    entry = cache.get(key)
    if entry and entry.get("cached_date") == today:
        return entry.get("data")
    data = fetcher()
    if data is not None:
        cache[key] = {"cached_date": today, "data": data}
        _save_cache(cache)
    return data


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


def fetch_balance(api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        ENDPOINT,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        if response.status != 200:
            raise ValueError(f"Unexpected HTTP {response.status}")
        body = response.read()
        return json.loads(body)


def fetch_platform_cost(bearer_token: str, month: int, year: int) -> list[dict[str, Any]] | None:
    """Fetch daily cost data from DeepSeek platform API.

    Returns list of {date, total, models: [{name, cost}]} or None on failure.
    """
    url = f"{COST_API}?month={month}&year={year}"
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {bearer_token}",
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "x-app-version": "1.0.0",
    }
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as resp:
            data = json.loads(resp.read())
        biz_data = data["data"]["biz_data"]
        if not biz_data:
            return None
        days = biz_data[0]["days"]
        records = []
        for day in days:
            total = 0.0
            models = []
            for model_entry in day.get("data", []):
                model_name = model_entry.get("model", "unknown")
                model_cost = 0.0
                for usage in model_entry.get("usage", []):
                    amount = float(usage.get("amount", 0))
                    total += amount
                    model_cost += amount
                models.append({"name": model_name, "cost": round(model_cost, 2)})
            records.append({"date": day["date"], "total": round(total, 2), "models": models})
        return records
    except Exception:
        return None


def fetch_cache_rates(bearer_token: str, month: int, year: int, target_date: str) -> dict[str, float] | None:
    """Fetch per-model cache hit rate from amount API for a specific date.

    Returns {model_short_name: cache_rate_percent} or None.
    """
    url = f"{USAGE_API}?month={month}&year={year}"
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {bearer_token}",
        "user-agent": "Mozilla/5.0",
    }
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as resp:
            data = json.loads(resp.read())
        days = data["data"]["biz_data"]["days"]
        for day in days:
            if day["date"] != target_date:
                continue
            rates = {}
            for model_entry in day.get("data", []):
                name = _short_model(model_entry.get("model", ""))
                hit = total_prompt = 0
                for usage in model_entry.get("usage", []):
                    t = usage.get("type", "")
                    amt = int(usage.get("amount", 0))
                    if t == "PROMPT_CACHE_HIT_TOKEN":
                        hit = amt
                    if t in ("PROMPT_CACHE_HIT_TOKEN", "PROMPT_CACHE_MISS_TOKEN", "PROMPT_TOKEN"):
                        total_prompt += amt
                if total_prompt > 0:
                    rates[name] = round(hit / total_prompt * 100, 1)
            return rates if rates else None
        return None
    except Exception:
        return None


def fetch_platform_usage(bearer_token: str, month: int, year: int) -> list[dict[str, Any]] | None:
    """Fetch daily token usage from DeepSeek platform API.

    Returns list of {date, total, models: [{name, input, output}]} or None on failure.
    """
    url = f"{USAGE_API}?month={month}&year={year}"
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {bearer_token}",
        "user-agent": "Mozilla/5.0",
    }
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as resp:
            data = json.loads(resp.read())
        biz_data = data["data"]["biz_data"]
        if not biz_data:
            return None
        days = biz_data["days"]
        records = []
        for day in days:
            total = 0
            models = []
            for model_entry in day.get("data", []):
                model_name = model_entry.get("model", "unknown")
                inp = out = 0
                for usage in model_entry.get("usage", []):
                    amt = int(usage.get("amount", 0))
                    t = usage.get("type", "")
                    if t in ("PROMPT_TOKEN", "PROMPT_CACHE_HIT_TOKEN", "PROMPT_CACHE_MISS_TOKEN"):
                        inp += amt
                    elif t == "RESPONSE_TOKEN":
                        out += amt
                    total += amt
                cache_hit = sum(int(u.get("amount", 0)) for u in model_entry.get("usage", [])
                                if u.get("type") == "PROMPT_CACHE_HIT_TOKEN")
                models.append({"name": model_name, "input": inp, "output": out, "cache_hit": cache_hit})
            records.append({"date": day["date"], "total": total, "models": models})
        return records
    except Exception:
        return None


def load_history() -> dict[str, Any]:
    """Load spending history from JSON file."""
    try:
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
            if "todayDate" in data and "dailyRecords" in data:
                return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {
        "schemaVersion": 1,
        "todayDate": "",
        "todayStartingBalance": 0.0,
        "dailyRecords": [],
    }


def save_history(history: dict[str, Any]) -> None:
    """Save spending history to JSON file."""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def update_history(history: dict[str, Any], current_balance: float) -> dict[str, Any]:
    """Update history with current balance, returning updated copy.

    - If today is new: record yesterday's consumption, set today's starting balance
    - If same day: compute today_consumption as starting_balance - current_balance
    """
    today = date_type.today().isoformat()
    today_date = history.get("todayDate", "")
    today_starting = history.get("todayStartingBalance", 0.0)
    daily_records = list(history.get("dailyRecords", []))

    if today_date != today:
        # Day boundary crossed -- record yesterday's consumption
        if today_date and today_starting > 0:
            yesterday_consumption = max(0, today_starting - current_balance)
            for i, rec in enumerate(daily_records):
                if rec["date"] == today_date:
                    daily_records[i] = {"date": today_date, "consumption": round(yesterday_consumption, 2)}
                    break
            else:
                daily_records.append({"date": today_date, "consumption": round(yesterday_consumption, 2)})
        # Start a new day
        today_starting = current_balance
        today_date = today

    # Compute today's consumption
    today_consumption = max(0, today_starting - current_balance)

    # Update today's record in daily_records
    found = False
    for i, rec in enumerate(daily_records):
        if rec["date"] == today:
            daily_records[i]["consumption"] = round(today_consumption, 2)
            found = True
            break
    if not found:
        daily_records.append({"date": today, "consumption": round(today_consumption, 2)})

    # Trim to last 30 days
    daily_records.sort(key=lambda r: r["date"], reverse=True)
    daily_records = daily_records[:30]

    return {
        "schemaVersion": 1,
        "todayDate": today_date,
        "todayStartingBalance": today_starting,
        "dailyRecords": daily_records,
    }


def build_items(data: dict[str, Any], language: str, limit_amount: float,
                translate: Any, today_cost: dict[str, Any] | None = None,
                cache_rates: dict[str, float] | None = None) -> list[dict[str, Any]]:
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

    # Per-model today's cost + cache rate items (pro and flash only)
    if today_cost and today_cost.get("models"):
        today_total = today_cost["total"]
        for model in today_cost["models"]:
            short_name = _short_model(model["name"])
            if short_name not in ("pro", "flash"):
                continue
            cost = round(model["cost"], 2)
            items.append({
                "id": f"today-{model['name']}",
                "name": translate(language, "today_cost"),
                "subtitle": f"deepseek-{short_name}",
                "used": cost,
                "limit": 1,
                "displayStyle": "value",
                "status": "normal",
                "color": "orange",
            })
            # Cache rate row directly below
            rate = cache_rates.get(short_name) if cache_rates else None
            items.append({
                "id": f"cache-{model['name']}",
                "name": translate(language, "cache_rate"),
                "subtitle": f"deepseek-{short_name}",
                "used": rate if rate is not None else 0,
                "limit": 100,
                "displayStyle": "percent2",
                "status": "normal",
                "color": "green" if rate is not None and rate >= 90 else "blue",
            })

    return items


def build_chart(history: dict[str, Any], language: str, translate: Any) -> dict[str, Any] | None:
    """Build a 30-day consumption trend chart from history."""
    records = history.get("dailyRecords", [])
    if not records:
        return None

    sorted_records = sorted(records, key=lambda r: r["date"])
    cost_label = translate(language, "cost")

    buckets = []
    for rec in sorted_records:
        date_str = rec["date"]
        parts = date_str.split("-")
        label = f"{int(parts[1])}/{int(parts[2])}" if len(parts) == 3 else date_str

        buckets.append({
            "id": date_str,
            "label": label,
            "segments": [
                {"model": cost_label, "tokens": round(rec.get("consumption", 0), 2)},
            ],
        })

    return {
        "kind": "line",
        "period": "30d",
        "bucketUnit": "day",
        "buckets": buckets,
    }


def build_cost_chart(cost_records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Build a 30-day cost trend chart with total + flash + pro lines."""
    if not cost_records:
        return None

    today = date_type.today()
    sorted_records = sorted(
        (r for r in cost_records if r["date"] <= today.isoformat()),
        key=lambda r: r["date"],
    )[-30:]
    if not sorted_records:
        return None

    buckets = []
    for rec in sorted_records:
        parts = rec["date"].split("-")
        label = f"{int(parts[1])}/{int(parts[2])}"
        segments = []
        for m in sorted(rec.get("models", []), key=lambda x: x["name"]):
            short = _short_model(m["name"])
            if short in ("pro", "flash") and m.get("cost", 0) > 0:
                segments.append({"model": short, "tokens": round(m["cost"], 4)})
        if segments:
            buckets.append({
            "id": rec["date"],
            "label": label,
            "segments": segments,
        })

    return {
        "kind": "line",
        "period": "30d",
        "bucketUnit": "day",
        "buckets": buckets,
    }


def main() -> int:
    params = parse_usageboard_params(sys.argv[1:])
    language = params.get("USAGEBOARD_LANGUAGE", "en")
    language = "en" if language == "en" else "zh-Hans"
    translate = make_translator({
        "balance": {"zh-Hans": "余额", "en": "Balance"},
        "consumption": {"zh-Hans": "消费", "en": "Cost"},
        "cache_rate": {"zh-Hans": "缓存率", "en": "Cache Rate"},
        "today_cost": {"zh-Hans": "今日消费", "en": "Today's Cost"},
    })
    api_key = params.get("API_KEY", "")
    if not api_key:
        return failure(translate(language, "missing_api_key"))
    limit_amount = parse_limit(params.get("LIMIT", ""))
    platform_token = params.get("PLATFORM_TOKEN", "")
    if not platform_token:
        return failure("请配置 Platform Token")
    chart_days_str = params.get("CHART_DAYS", "30")
    try:
        chart_days = max(1, int(chart_days_str))
    except (ValueError, TypeError):
        chart_days = 30


    try:
        payload = fetch_balance(api_key)
    except urllib.error.HTTPError as error:
        return handle_http_error(error, translate, language)
    except urllib.error.URLError as error:
        return handle_url_error(error, translate, language)
    except TimeoutError:
        return failure(translate(language, "request_timeout"))
    except json.JSONDecodeError:
        return failure(translate(language, "usage_parse_failed"))
    except Exception:
        return failure(translate(language, "network_error"))

    try:
        today = date_type.today()
        cur_month, cur_year = today.month, today.year
        today_str = today.isoformat()

        # Fetch cost data with daily cache
        today_cost = None
        all_cost = None
        try:
            cost_records = fetch_platform_cost(platform_token, cur_month, cur_year)
            if cost_records:
                prev_month = cur_month - 1 if cur_month > 1 else 12
                prev_year = cur_year if cur_month > 1 else cur_year - 1
                prev_records = fetch_platform_cost(platform_token, prev_month, prev_year)
                all_cost = (prev_records or []) + (cost_records or [])
                for rec in sorted(all_cost, key=lambda r: r["date"], reverse=True):
                    if rec["date"] <= today_str and rec.get("models") and rec.get("total", 0) > 0:
                        today_cost = rec
                        break
        except Exception:
            pass

        # Fetch usage data — use for both cache rates and chart
        cache_rates = None
        chart = None
        try:
            months = [(cur_month, cur_year)]
            if cur_month > 1:
                months.append((cur_month - 1, cur_year))
            else:
                months.append((12, cur_year - 1))

            all_amount_records = []
            for m, y in months:
                records = fetch_platform_usage(platform_token, m, y)
                if records:
                    all_amount_records.extend(records)

            if all_amount_records:
                today_cache_data = next((r for r in all_amount_records if r["date"] == today_str), None)
                if today_cache_data:
                    rates = {}
                    for m in today_cache_data.get("models", []):
                        short = _short_model(m["name"])
                        hit = m.get("cache_hit", 0)
                        inp = m.get("input", 0)
                        if inp > 0:
                            rates[short] = round(hit / inp * 100, 1)
                    cache_rates = rates if rates else None

                chart = build_cost_chart(all_cost) if all_cost else None
        except Exception:
            pass

        items = build_items(payload, language, limit_amount, translate, today_cost, cache_rates)
    except Exception:
        return failure(translate(language, "usage_parse_failed"))

    return success(items, chart=chart)


if __name__ == "__main__":
    sys.exit(main())
