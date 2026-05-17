#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "DeepSeek",
#   "name@zh-Hans": "DeepSeek",
#   "name@en": "DeepSeek",
#   "icon": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/deepseek-color.png",
#   "description": "查询 DeepSeek API 余额和消费统计",
#   "description@zh-Hans": "查询 DeepSeek API 余额和消费统计",
#   "description@en": "Query DeepSeek API balance and spending stats",
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
#       "name": "DB_PATH",
#       "label": "数据库路径",
#       "label@zh-Hans": "数据库路径",
#       "label@en": "Database Path",
#       "type": "file",
#       "required": false,
#       "defaultValue": ""
#     }
#   ]
# }
# /UsageBoardPlugin
"""UsageBoard plugin for DeepSeek API balance."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
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
DEFAULT_LIMIT = 100.0


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
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise ValueError(f"Unexpected HTTP {response.status}")
        body = response.read()
        return json.loads(body)


def query_cost(conn: sqlite3.Connection, since_ts: int, model_filter: str) -> float:
    try:
        row = conn.execute(
            """SELECT SUM(CAST(total_cost_usd AS REAL)) as cost
               FROM proxy_request_logs
               WHERE model LIKE ?
                 AND created_at >= ?""",
            (model_filter, since_ts),
        ).fetchone()
        return round(row["cost"] or 0, 4)
    except (sqlite3.OperationalError, TypeError):
        return 0.0


def query_cache_rate(conn: sqlite3.Connection, since_ts: int, model_filter: str) -> float | None:
    try:
        row = conn.execute(
            """SELECT SUM(input_tokens) as inp,
                      SUM(cache_read_tokens) as cr,
                      SUM(cache_creation_tokens) as cc
               FROM proxy_request_logs
               WHERE model LIKE ?
                 AND created_at >= ?""",
            (model_filter, since_ts),
        ).fetchone()
        inp = row["inp"] or 0
        cr = row["cr"] or 0
        cc = row["cc"] or 0
        cacheable = inp + cc + cr
        if cacheable <= 0:
            return None
        return round(cr / cacheable * 100, 1)
    except (sqlite3.OperationalError, TypeError):
        return None


def build_items(data: dict[str, Any], language: str, limit_amount: float,
                translate: Any, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    items: list[dict] = []

    # Balance row (no subtitle)
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

    # Per-model cost + cache rate (flash / pro) from cc-switch DB
    if conn is None:
        return items

    today_ts = int(datetime.combine(datetime.now().date(), datetime.min.time()).timestamp())
    model_groups = [
        ("deepseek-v4-flash", "deepseek-flash"),
        ("deepseek-v4-pro", "deepseek-pro"),
    ]

    for db_model, short_name in model_groups:
        cost = query_cost(conn, today_ts, f"%{db_model}%")
        cache_rate_val = query_cache_rate(conn, today_ts, f"%{db_model}%")

        items.append({
            "id": f"ds-cost-{short_name}",
            "name": translate(language, "today_cost"),
            "subtitle": short_name,
            "used": cost,
            "limit": 1,
            "displayStyle": "value",
            "status": "normal",
            "color": "orange",
        })
        items.append({
            "id": f"ds-cache-{short_name}",
            "name": translate(language, "cache_rate"),
            "subtitle": short_name,
            "used": cache_rate_val if cache_rate_val is not None else 0,
            "limit": 100,
            "displayStyle": "percent2",
            "status": "normal",
            "color": "green" if cache_rate_val is not None and cache_rate_val >= 90 else "blue",
        })

    return items


def build_cost_chart(conn: sqlite3.Connection, language: str, translate: Any) -> dict[str, Any] | None:
    cutoff_ts = int((datetime.now() - timedelta(days=29)).timestamp())

    try:
        rows = conn.execute(
            """SELECT date(datetime(created_at, 'unixepoch')) as date,
                      model,
                      SUM(CAST(total_cost_usd AS REAL)) as cost
               FROM proxy_request_logs
               WHERE model LIKE 'deepseek%'
                 AND created_at >= ?
               GROUP BY date, model
               ORDER BY date""",
            (cutoff_ts,),
        ).fetchall()
    except sqlite3.OperationalError:
        return None

    if not rows:
        return None

    daily: dict[str, dict[str, float]] = {}
    for row in rows:
        d = row["date"]
        m = _short_model(row["model"])
        c = round(row["cost"] or 0, 4)
        if d not in daily:
            daily[d] = {}
        daily[d][m] = daily[d].get(m, 0) + c

    # Aggregate: keep flash + pro + compute total
    sorted_dates = sorted(daily.keys())
    buckets: list[dict[str, Any]] = []
    for d in sorted_dates:
        segments = []
        for model, cost in sorted(daily[d].items()):
            short = "pro" if "pro" in model else ("flash" if "flash" in model else model)
            if cost > 0:
                segments.append({"model": short, "tokens": round(cost, 4)})
        if segments:
            buckets.append({"id": d, "label": d[5:], "segments": segments})

    if not buckets:
        return None

    return {
        "kind": "line",
        "period": "30d",
        "bucketUnit": "day",
        "title": translate(language, "cost_chart_title"),
        "showLegend": True,
        "buckets": buckets,
        "unitLabel": "$",
    }


def _short_model(model: str) -> str:
    m = model.lower()
    if "pro" in m:
        return "pro"
    if "flash" in m:
        return "flash"
    return m


def main() -> int:
    params = parse_usageboard_params(sys.argv[1:])
    language = params.get("USAGEBOARD_LANGUAGE", "en")
    language = "en" if language == "en" else "zh-Hans"
    translate = make_translator({
        "balance": {"zh-Hans": "余额", "en": "Balance"},
        "today_cost": {"zh-Hans": "今日消费", "en": "Today cost"},
        "cache_rate": {"zh-Hans": "缓存率", "en": "Cache rate"},
        "cost_chart_title": {"zh-Hans": "近30日消费趋势", "en": "30-day cost trend"},
    })

    api_key = params.get("API_KEY", "")
    if not api_key:
        return failure(translate(language, "missing_api_key"))
    limit_amount = parse_limit(params.get("LIMIT", ""))

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

    # Optional DB connection for cost data
    conn = None
    db_path = params.get("DB_PATH", "")
    if db_path:
        expanded = os.path.expanduser(db_path)
        if os.path.isfile(expanded):
            try:
                conn = sqlite3.connect(expanded)
                conn.row_factory = sqlite3.Row
            except sqlite3.Error:
                conn = None

    try:
        items = build_items(payload, language, limit_amount, translate, conn)
    except Exception:
        if conn:
            conn.close()
        return failure(translate(language, "usage_parse_failed"))

    chart = None
    if conn:
        try:
            chart = build_cost_chart(conn, language, translate)
        except Exception:
            pass
        conn.close()

    return success(items, chart=chart)


if __name__ == "__main__":
    sys.exit(main())
