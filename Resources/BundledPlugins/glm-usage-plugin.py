#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "智谱",
#   "name@zh-Hans": "智谱",
#   "name@en": "Zhipu",
#   "icon": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/zhipu-color.png",
#   "description": "查询智谱 / ZAI Coding Plan 用量和 token 统计",
#   "description@zh-Hans": "查询智谱 / ZAI Coding Plan 用量和 token 统计",
#   "description@en": "Query Zhipu / ZAI Coding Plan usage and token stats",
#   "parameters": [
#     {
#       "name": "API_KEY",
#       "label": "Api Key",
#       "label@zh-Hans": "Api Key",
#       "type": "secret",
#       "required": true,
#       "placeholder": "Coding Plan API Key"
#     },
#     {
#       "name": "STAT_PERIOD",
#       "label": "统计周期",
#       "label@zh-Hans": "统计周期",
#       "label@en": "Stats Period",
#       "type": "choice",
#       "required": true,
#       "defaultValue": "7d",
#       "options": [
#         {"label": "7 天",  "label@zh-Hans": "7 天",  "label@en": "7 days",  "value": "7d"},
#         {"label": "15 天", "label@zh-Hans": "15 天", "label@en": "15 days", "value": "15d"},
#         {"label": "30 天", "label@zh-Hans": "30 天", "label@en": "30 days", "value": "30d"}
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
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta, timezone
from typing import Any


QUOTA_ENDPOINT = "https://open.bigmodel.cn/api/monitor/usage/quota/limit"
MODEL_USAGE_ENDPOINT = "https://bigmodel.cn/api/monitor/usage/model-usage"
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


def get_stat_period(argv: list[str]) -> str:
    params = parse_usageboard_params(argv)
    period = params.get("STAT_PERIOD", "7d").lower()
    return period if period in ("7d", "15d", "30d") else "7d"


def get_app_language(argv: list[str]) -> str:
    return "en" if parse_usageboard_params(argv).get("USAGEBOARD_LANGUAGE") == "en" else "zh-Hans"


TRANSLATIONS = {
    "period_5h": {
        "zh-Hans": "5小时",
        "en": "5 hours",
    },
    "period_week": {
        "zh-Hans": "周",
        "en": "week",
    },
    "period_month": {
        "zh-Hans": "月",
        "en": "month",
    },
    "tool_calls": {
        "zh-Hans": "工具调用",
        "en": "Tool calls",
    },
    "text_generation": {
        "zh-Hans": "文本生成",
        "en": "Text generation",
    },
    "five_hour_usage": {
        "zh-Hans": "5 小时用量",
        "en": "5-hour usage",
    },
    "weekly_usage": {
        "zh-Hans": "周用量",
        "en": "Weekly usage",
    },
    "mcp_month_usage": {
        "zh-Hans": "MCP 月用量",
        "en": "MCP monthly usage",
    },
    "no_stats_data": {
        "zh-Hans": "暂无可用统计数据",
        "en": "No stats data available",
    },
    "missing_api_key":    {"zh-Hans": "请在插件设置中配置 API Key",          "en": "Configure API Key in plugin settings"},
    "no_quota_items":     {"zh-Hans": "未获取到配额数据",                     "en": "No quota data found."},
    "stats_query_failed": {"zh-Hans": "统计数据查询失败",                      "en": "Failed to query stats data"},
    "request_timeout":    {"zh-Hans": "请求超时，请检查网络",                  "en": "Request timed out. Check your network."},
    "http_401":           {"zh-Hans": "API Key 无效，请检查配置",             "en": "Invalid API Key. Check your settings."},
    "http_403":           {"zh-Hans": "账号无权限访问",                        "en": "Access denied. Check your plan."},
    "http_429":           {"zh-Hans": "请求频率超限，请稍后重试",               "en": "Rate limited. Try again later."},
    "http_5xx":           {"zh-Hans": "服务暂时不可用 (HTTP {code})",         "en": "Service unavailable (HTTP {code})"},
    "http_other":         {"zh-Hans": "请求失败 (HTTP {code})",              "en": "Request failed (HTTP {code})"},
    "network_error":      {"zh-Hans": "网络连接失败，请检查网络",               "en": "Network error. Check your connection."},
}


def translate(language: str, key: str, **kwargs) -> str:
    values = TRANSLATIONS.get(key, {})
    text = values.get(language) or values.get("zh-Hans") or key
    return text.format(**kwargs) if kwargs else text


def fetch_limits(api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        QUOTA_ENDPOINT,
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_model_usage(api_key: str, start_time: datetime, end_time: datetime) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "startTime": format_query_time(start_time),
            "endTime": format_query_time(end_time),
        }
    )
    request = urllib.request.Request(
        f"{MODEL_USAGE_ENDPOINT}?{query}",
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def format_query_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def stat_range(period: str) -> tuple[datetime, datetime, list[datetime], str]:
    now = datetime.now().astimezone()
    day_count = {"7d": 7, "15d": 15, "30d": 30}.get(period, 7)
    today = now.date()
    start_date = today - timedelta(days=day_count - 1)
    start = datetime.combine(start_date, time.min, tzinfo=now.tzinfo)
    end = datetime.combine(today, time.max, tzinfo=now.tzinfo).replace(microsecond=0)
    buckets = [start + timedelta(days=index) for index in range(day_count)]
    return start, end, buckets, "day"


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


def period_for(limit: dict[str, Any], language: str) -> tuple[str, str] | None:
    unit = limit.get("unit")
    number = limit.get("number")
    if unit == 3 and number == 5:
        return "5h", translate(language, "period_5h")
    if unit == 6 and number == 1:
        return "week", translate(language, "period_week")
    if unit == 5 and number == 1:
        return "month", translate(language, "period_month")
    return None


def quota_kind(limit: dict[str, Any], language: str) -> tuple[str, str]:
    text = json.dumps(limit, ensure_ascii=False).lower()
    tool_markers = ("tool", "工具", "function", "mcp")
    text_markers = ("token", "text", "文本")

    if any(marker in text for marker in tool_markers):
        return "tool", translate(language, "tool_calls")
    if any(marker in text for marker in text_markers):
        return "text", translate(language, "text_generation")
    if "currentValue" in limit or "usage" in limit:
        return "tool", translate(language, "tool_calls")
    return "text", translate(language, "text_generation")


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


def build_items(payload: dict[str, Any], language: str) -> tuple[list[dict[str, Any]], str | None]:
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

        period = period_for(limit, language)
        if period is None:
            continue

        period_id, period_label = period
        kind_id, kind_label = quota_kind(limit, language)
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
        "glm-text-5h": translate(language, "five_hour_usage"),
        "glm-text-week": translate(language, "weekly_usage"),
        "glm-tool-month": translate(language, "mcp_month_usage"),
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


def build_chart(payload: dict[str, Any], period: str, buckets: list[datetime], bucket_unit: str, language: str) -> dict[str, Any]:
    bucket_values: dict[str, dict[str, float]] = {
        bucket_id(bucket, bucket_unit): {} for bucket in buckets
    }

    apply_aligned_model_series(payload, bucket_values, bucket_unit)

    for record, inherited_model in iter_records(payload):
        model = extract_model(record)
        if model is None:
            model = inherited_model
        tokens = extract_tokens(record)
        timestamp = extract_timestamp(record)
        if not model or tokens is None or tokens <= 0 or timestamp is None:
            continue

        key = bucket_id(timestamp.astimezone(), bucket_unit)
        if key not in bucket_values:
            continue
        bucket_values[key][model] = bucket_values[key].get(model, 0) + tokens

    chart_buckets: list[dict[str, Any]] = []
    for bucket in buckets:
        key = bucket_id(bucket, bucket_unit)
        segments = [
            {"model": model, "tokens": tokens}
            for model, tokens in sorted(bucket_values[key].items())
            if tokens > 0
        ]
        chart_buckets.append(
            {
                "id": key,
                "label": bucket_label(bucket, bucket_unit),
                "segments": segments,
            }
        )

    message = None
    if not any(bucket["segments"] for bucket in chart_buckets):
        message = translate(language, "no_stats_data")

    return {
        "kind": "line",
        "period": period,
        "bucketUnit": bucket_unit,
        "buckets": chart_buckets,
        "message": message,
    }


def apply_aligned_model_series(
    payload: dict[str, Any],
    bucket_values: dict[str, dict[str, float]],
    bucket_unit: str,
) -> None:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return

    times = data.get("x_time")
    if not isinstance(times, list):
        return

    model_entries = data.get("modelDataList")
    if isinstance(model_entries, list):
        for entry in model_entries:
            if not isinstance(entry, dict):
                continue
            model = extract_model(entry)
            values = entry.get("tokensUsage")
            if not model or not isinstance(values, list):
                continue
            apply_aligned_values(times, values, model, bucket_values, bucket_unit)

    total_values = data.get("tokensUsage")
    if isinstance(total_values, list) and not any(bucket_values[key] for key in bucket_values):
        apply_aligned_values(times, total_values, "总计", bucket_values, bucket_unit)


def apply_aligned_values(
    times: list[Any],
    values: list[Any],
    model: str,
    bucket_values: dict[str, dict[str, float]],
    bucket_unit: str,
) -> None:
    for index, time_value in enumerate(times):
        if index >= len(values):
            break
        timestamp = timestamp_from_value(time_value)
        tokens = numeric_value(values[index])
        if timestamp is None or tokens is None or tokens <= 0:
            continue

        key = bucket_id(timestamp.astimezone(), bucket_unit)
        if key not in bucket_values:
            continue
        bucket_values[key][model] = bucket_values[key].get(model, 0) + tokens


def iter_records(value: Any, inherited_model: str | None = None):
    if isinstance(value, dict):
        model = extract_model(value) or inherited_model
        yield value, inherited_model
        for child in value.values():
            yield from iter_records(child, model)
    elif isinstance(value, list):
        if len(value) >= 2 and not isinstance(value[0], (dict, list)) and not isinstance(value[1], (dict, list)):
            yield {"time": value[0], "value": value[1]}, inherited_model
        for child in value:
            yield from iter_records(child, inherited_model)


def extract_model(record: dict[str, Any]) -> str | None:
    value = first_present(
        record,
        (
            "model",
            "modelName",
            "model_name",
            "modelCode",
            "model_code",
            "modelType",
            "model_type",
            "modelId",
            "model_id",
            "modelLabel",
            "model_label",
            "name",
        ),
    )
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def extract_tokens(record: dict[str, Any]) -> float | None:
    token_keys = (
        "tokens",
        "token",
        "totalTokens",
        "total_tokens",
        "totalToken",
        "total_token",
        "totalTokensUsage",
        "total_tokens_usage",
        "totalTokenUsage",
        "total_token_usage",
        "tokensUsage",
        "tokens_usage",
        "tokenCount",
        "token_count",
        "tokensCount",
        "tokens_count",
        "consumeTokens",
        "consume_tokens",
        "consumedTokens",
        "consumed_tokens",
        "usedToken",
        "used_token",
        "tokenUsage",
        "token_usage",
        "usageTokens",
        "usage_tokens",
        "usedTokens",
        "used_tokens",
        "total",
        "value",
    )
    for key in token_keys:
        value = record.get(key)
        number = numeric_value(value)
        if number is not None:
            return number

    usage = record.get("usage")
    if isinstance(usage, dict):
        for key in token_keys:
            number = numeric_value(usage.get(key))
            if number is not None:
                return number
    total_usage = record.get("totalUsage")
    if isinstance(total_usage, dict):
        for key in token_keys:
            number = numeric_value(total_usage.get(key))
            if number is not None:
                return number
    input_tokens = numeric_value(record.get("inputTokens") or record.get("input_tokens"))
    output_tokens = numeric_value(record.get("outputTokens") or record.get("output_tokens"))
    if input_tokens is not None or output_tokens is not None:
        return (input_tokens or 0) + (output_tokens or 0)
    return None


def numeric_value(value: Any) -> float | None:
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    if isinstance(value, str):
        normalized = value.strip().replace(",", "")
        if not normalized:
            return None
        try:
            number = float(normalized)
        except ValueError:
            return None
        return number if number >= 0 else None
    return None


def extract_timestamp(record: dict[str, Any]) -> datetime | None:
    value = first_present(
        record,
        (
            "time",
            "date",
            "day",
            "hour",
            "statTime",
            "stat_time",
            "statDate",
            "stat_date",
            "startTime",
            "start_time",
            "timestamp",
            "requestTime",
            "request_time",
            "createdAt",
            "created_at",
            "createTime",
            "create_time",
        ),
    )
    timestamp = normalize_timestamp(value)
    if timestamp is not None:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    if isinstance(value, str):
        return timestamp_from_value(value)
    return None


def timestamp_from_value(value: Any) -> datetime | None:
    timestamp = normalize_timestamp(value)
    if timestamp is not None:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    if isinstance(value, str):
        text = value.strip()
        for pattern in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
        ):
            try:
                return datetime.strptime(text, pattern).astimezone()
            except ValueError:
                continue
    return None


def bucket_id(value: datetime, bucket_unit: str) -> str:
    if bucket_unit == "hour":
        return value.strftime("%Y-%m-%dT%H")
    return value.strftime("%Y-%m-%d")


def bucket_label(value: datetime, bucket_unit: str) -> str:
    if bucket_unit == "hour":
        return value.strftime("%H")
    return value.strftime("%m-%d")


def chart_message(message: str, period: str, buckets: list[datetime], bucket_unit: str) -> dict[str, Any]:
    return {
        "kind": "line",
        "period": period,
        "bucketUnit": bucket_unit,
        "buckets": [
            {
                "id": bucket_id(bucket, bucket_unit),
                "label": bucket_label(bucket, bucket_unit),
                "segments": [],
            }
            for bucket in buckets
        ],
        "message": message,
    }


def success(items: list[dict[str, Any]], badge: str | None = None, chart: dict[str, Any] | None = None) -> int:
    result: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "updatedAt": utc_now_iso(),
        "items": items,
    }
    if badge:
        result["badge"] = badge
    if chart:
        result["chart"] = chart
    print(json.dumps(result, ensure_ascii=False))
    return 0


def failure(message: str, language: str) -> int:
    print(json.dumps({"error": message}, ensure_ascii=False))
    return 0


def main() -> int:
    params = parse_usageboard_params(sys.argv[1:])
    api_key = params.get("API_KEY")
    period = params.get("STAT_PERIOD", "7d").lower()
    if period not in ("7d", "15d", "30d"):
        period = "7d"
    language = "en" if params.get("USAGEBOARD_LANGUAGE") == "en" else "zh-Hans"
    if not api_key:
        return failure(translate(language, "missing_api_key"), language)

    try:
        payload = fetch_limits(api_key)
        items, badge = build_items(payload, language)
        if not items:
            return failure(translate(language, "no_quota_items"), language)
        start_time, end_time, buckets, bucket_unit = stat_range(period)
        try:
            chart_payload = fetch_model_usage(api_key, start_time, end_time)
            chart = build_chart(chart_payload, period, buckets, bucket_unit, language)
        except Exception:
            chart = chart_message(translate(language, "stats_query_failed"), period, buckets, bucket_unit)
        return success(items, badge=badge, chart=chart)
    except urllib.error.HTTPError as error:
        if error.code == 401:
            return failure(translate(language, "http_401"), language)
        if error.code == 403:
            return failure(translate(language, "http_403"), language)
        if error.code == 429:
            return failure(translate(language, "http_429"), language)
        if error.code >= 500:
            return failure(translate(language, "http_5xx", code=error.code), language)
        return failure(translate(language, "http_other", code=error.code), language)
    except urllib.error.URLError:
        return failure(translate(language, "network_error"), language)
    except TimeoutError:
        return failure(translate(language, "request_timeout"), language)
    except Exception:
        return failure(translate(language, "network_error"), language)


if __name__ == "__main__":
    sys.exit(main())
