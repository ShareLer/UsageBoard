#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "Claude Code",
#   "name@zh-Hans": "Claude Code",
#   "name@en": "Claude Code",
#   "icon": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/claude-color.png",
#   "description": "查询 Claude Code 使用量统计和会话概览",
#   "description@zh-Hans": "查询 Claude Code 使用量统计和会话概览",
#   "description@en": "Query Claude Code usage stats and session overview",
#   "parameters": [
#     {
#       "name": "DB_PATH",
#       "label": "数据库路径",
#       "label@zh-Hans": "数据库路径",
#       "label@en": "Database Path",
#       "type": "file",
#       "required": true,
#       "defaultValue": "~/.cc-switch/cc-switch.db"
#     }
#   ]
# }
# /UsageBoardPlugin
"""UsageBoard plugin for Claude Code usage stats."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _common import (
    app_language,
    failure,
    make_translator,
    parse_usageboard_params,
    success,
    utc_now_iso,
)

TRANSLATIONS = {
    "missing_db_path": {
        "zh-Hans": "请在插件设置中配置数据库路径",
        "en": "Configure database path in plugin settings",
    },
    "db_not_found": {
        "zh-Hans": "未检测到 cc-switch 数据库，请先安装 cc-switch",
        "en": "cc-switch database not found. Install cc-switch first.",
    },
    "no_usage_data": {
        "zh-Hans": "暂无使用数据",
        "en": "No usage data available",
    },
    "no_stats_data": {
        "zh-Hans": "暂无可用统计数据",
        "en": "No stats data available",
    },
    "period_today": {"zh-Hans": "今日", "en": "Today"},
    "period_7d": {"zh-Hans": "近7天", "en": "7 days"},
    "period_30d": {"zh-Hans": "近30天", "en": "30 days"},
    "period_total": {"zh-Hans": "模型总量", "en": "Total"},
    "chart_title": {"zh-Hans": "近30日趋势", "en": "30-day trend"},
    "no_session_data": {
        "zh-Hans": "暂无会话数据",
        "en": "No session data available",
    },
}

translate = make_translator(TRANSLATIONS)


def cache_rate(input_t: int, cache_read: int, cache_creation: int) -> float:
    cacheable = input_t + cache_creation + cache_read
    if cacheable <= 0:
        return 0.0
    return round(cache_read / cacheable * 100, 1)


def cache_rate_color(rate: float) -> str:
    if rate >= 90:
        return "green"
    if rate >= 80:
        return "black"
    return "red"


def format_token(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}K"
    return str(value)


def open_db(db_path: str) -> sqlite3.Connection:
    expanded = os.path.expanduser(db_path)
    if not os.path.isfile(expanded):
        raise FileNotFoundError(expanded)
    conn = sqlite3.connect(expanded)
    conn.row_factory = sqlite3.Row
    return conn


def query_sessions(conn: sqlite3.Connection) -> dict[str, Any] | None:
    now_ts = int(datetime.now().timestamp())
    today_start = int(
        datetime.combine(
            datetime.now().date(), datetime.min.time()
        ).timestamp()
    )
    two_hours_ago = now_ts - 7200

    try:
        active = conn.execute(
            """SELECT COUNT(DISTINCT session_id) as cnt
               FROM proxy_request_logs
               WHERE app_type = 'claude'
                 AND session_id IS NOT NULL
                 AND session_id != ''
                 AND created_at >= ?""",
            (two_hours_ago,),
        ).fetchone()["cnt"]

        today = conn.execute(
            """SELECT COUNT(DISTINCT session_id) as cnt
               FROM proxy_request_logs
               WHERE app_type = 'claude'
                 AND session_id IS NOT NULL
                 AND session_id != ''
                 AND created_at >= ?""",
            (today_start,),
        ).fetchone()["cnt"]

        if active == 0 and today == 0:
            return None

        return {"active": active, "today": today}
    except sqlite3.OperationalError:
        return None


def build_items(
    conn: sqlite3.Connection, language: str
) -> list[dict[str, Any]]:
    now = datetime.now()
    today_start_ts = int(
        datetime.combine(now.date(), datetime.min.time()).timestamp()
    )
    week_ago_ts = int(
        (datetime.combine(now.date(), datetime.min.time()) - timedelta(days=6)).timestamp()
    )
    month_ago_ts = int(
        (datetime.combine(now.date(), datetime.min.time()) - timedelta(days=29)).timestamp()
    )

    items: list[dict[str, Any]] = []

    periods = [
        ("today", today_start_ts, translate(language, "period_today")),
        ("7d", week_ago_ts, translate(language, "period_7d")),
        ("30d", month_ago_ts, translate(language, "period_30d")),
    ]

    for period_id, since_ts, period_label in periods:
        try:
            rows = conn.execute(
                """SELECT model,
                          SUM(input_tokens) as total_input,
                          SUM(output_tokens) as total_output,
                          SUM(cache_read_tokens) as total_cache_read,
                          SUM(cache_creation_tokens) as total_cache_creation
                   FROM proxy_request_logs
                   WHERE app_type = 'claude'
                     AND created_at >= ?
                   GROUP BY model
                   ORDER BY (total_input + total_output) DESC
                   LIMIT 3""",
                (since_ts,),
            ).fetchall()
        except sqlite3.OperationalError:
            continue

        if not rows:
            continue

        # Collect all token totals for this period
        rows_data = []
        for row in rows:
            ri = row["total_input"] or 0
            ro = row["total_output"] or 0
            rcr = row["total_cache_read"] or 0
            rcc = row["total_cache_creation"] or 0
            rows_data.append({
                "model": row["model"] or "unknown",
                "input": ri,
                "output": ro,
                "cache_read": rcr,
                "cache_creation": rcc,
            })

        total_input = sum(r["input"] for r in rows_data)
        total_output = sum(r["output"] for r in rows_data)
        total_cache_read = sum(r["cache_read"] for r in rows_data)
        total_cache_creation = sum(r["cache_creation"] for r in rows_data)
        total_cr = cache_rate(total_input, total_cache_read, total_cache_creation)
        total_all = total_input + total_output

        # Find max total in this group for progress bar baseline
        group_max = max(total_all, max(r["input"] + r["output"] for r in rows_data))

        # Period total row
        items.append({
            "id": f"cc-{period_id}-total",
            "name": translate(language, "period_total"),
            "subtitle": period_label,
            "used": total_all,
            "limit": group_max,
            "displayStyle": "value",
            "status": "normal",
            "color": "green",
            "labels": [
                {"text": format_token(total_input), "color": "blue"},
                {"text": format_token(total_output), "color": "orange"},
                {"text": f"{total_cr}%", "color": cache_rate_color(total_cr)},
            ],
        })

        # Per-model rows
        for rank, rd in enumerate(rows_data):
            m_cr = cache_rate(rd["input"], rd["cache_read"], rd["cache_creation"])
            total_m = rd["input"] + rd["output"]

            items.append({
                "id": f"cc-{period_id}-m{rank}",
                "name": f" {rd['model']}",
                "subtitle": period_label,
                "used": total_m,
                "limit": group_max,
                "displayStyle": "value",
                "status": "normal",
                "color": "green",
                "labels": [
                    {"text": format_token(rd["input"]), "color": "blue"},
                    {"text": format_token(rd["output"]), "color": "orange"},
                    {"text": f"{m_cr}%", "color": cache_rate_color(m_cr)},
                ],
            })

    return items


def query_chart_data(
    conn: sqlite3.Connection, language: str
) -> dict[str, Any] | None:
    cutoff = (datetime.now() - timedelta(days=29)).strftime("%Y-%m-%d")
    cutoff_ts = int((datetime.now() - timedelta(days=29)).timestamp())

    # Try usage_daily_rollups first (pre-aggregated)
    try:
        rows = conn.execute(
            """SELECT date,
                      model,
                      SUM(input_tokens + output_tokens) as total_tokens
               FROM usage_daily_rollups
               WHERE app_type = 'claude'
                 AND date >= ?
               GROUP BY date, model
               ORDER BY date""",
            (cutoff,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []

    # Fallback: query proxy_request_logs directly
    if not rows:
        try:
            from datetime import datetime as dt

            raw_rows = conn.execute(
                """SELECT date(datetime(created_at, 'unixepoch')) as date,
                          model,
                          SUM(input_tokens + output_tokens) as total_tokens
                   FROM proxy_request_logs
                   WHERE app_type = 'claude'
                     AND created_at >= ?
                   GROUP BY date, model
                   ORDER BY date""",
                (cutoff_ts,),
            ).fetchall()
            rows = raw_rows
        except sqlite3.OperationalError:
            return None

    if not rows:
        return None

    daily_data: dict[str, dict[str, float]] = {}
    for row in rows:
        date_key = row["date"]
        model = row["model"]
        tokens = float(row["total_tokens"] or 0)
        if date_key not in daily_data:
            daily_data[date_key] = {}
        daily_data[date_key][model] = daily_data[date_key].get(model, 0) + tokens

    sorted_dates = sorted(daily_data.keys())
    all_models: set[str] = set()
    for data in daily_data.values():
        all_models.update(data.keys())
    sorted_models = sorted(all_models)

    # Keep only top 5 models by total token usage
    model_totals: dict[str, float] = {}
    for data in daily_data.values():
        for model, tokens in data.items():
            model_totals[model] = model_totals.get(model, 0) + tokens
    top5_models = set(
        sorted(model_totals, key=model_totals.get, reverse=True)[:5]
    )

    buckets: list[dict[str, Any]] = []
    for date_key in sorted_dates:
        segments: list[dict[str, Any]] = []
        for model in sorted_models:
            if model not in top5_models:
                continue
            tokens = daily_data[date_key].get(model, 0)
            if tokens > 0:
                segments.append({"model": model, "tokens": tokens})
        if segments:
            buckets.append({
                "id": date_key,
                "label": date_key[5:],
                "segments": segments,
            })

    if not buckets:
        return None

    return {
        "kind": "line",
        "period": "30d",
        "bucketUnit": "day",
        "title": translate(language, "chart_title"),
        "showLegend": False,
        "buckets": buckets,
    }


def main() -> int:
    params = parse_usageboard_params(sys.argv[1:])
    db_path = params.get("DB_PATH", "~/.cc-switch/cc-switch.db")
    language = app_language(params)

    if not db_path:
        return failure(translate(language, "missing_db_path"))

    expanded_path = os.path.expanduser(db_path)
    if not os.path.isfile(expanded_path):
        return failure(translate(language, "db_not_found"))

    try:
        conn = open_db(db_path)
    except (FileNotFoundError, sqlite3.Error) as e:
        return failure(str(e))

    try:
        items = build_items(conn, language)

        if not items:
            conn.close()
            return failure(translate(language, "no_usage_data"))

        sessions = query_sessions(conn)
        chart = query_chart_data(conn, language)

        conn.close()

        output: dict[str, Any] = {
            "schemaVersion": 1,
            "updatedAt": utc_now_iso(),
            "items": items,
        }
        if sessions:
            output["sessions"] = sessions
        if chart:
            output["chart"] = chart

        print(json.dumps(output, ensure_ascii=False))
        return 0

    except sqlite3.Error as e:
        conn.close()
        return failure(str(e))
    except Exception as e:
        conn.close()
        return failure(str(e))


if __name__ == "__main__":
    sys.exit(main())
