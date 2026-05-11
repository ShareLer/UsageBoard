#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "name": "Claude",
#   "name@zh-Hans": "Claude",
#   "name@en": "Claude",
#   "icon": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/claude-color.png",
#   "description": "查询 Claude 订阅用量和统计",
#   "description@zh-Hans": "查询 Claude 订阅用量和统计",
#   "description@en": "Query Claude subscription usage and stats",
#   "parameters": [
#     {
#       "name": "PLAN",
#       "label": "Subscription Plan",
#       "label@zh-Hans": "订阅计划",
#       "label@en": "Subscription Plan",
#       "type": "choice",
#       "required": false,
#       "defaultValue": "pro",
#       "options": [
#         {"label": "Pro",     "label@zh-Hans": "Pro",     "label@en": "Pro",     "value": "pro"},
#         {"label": "Max 5X",  "label@zh-Hans": "Max 5X",  "label@en": "Max 5X",  "value": "max5"},
#         {"label": "Max 20X", "label@zh-Hans": "Max 20X", "label@en": "Max 20X", "value": "max20"}
#       ]
#     },
#     {
#       "name": "STAT_PERIOD",
#       "label": "Stats Period",
#       "label@zh-Hans": "统计周期",
#       "label@en": "Stats Period",
#       "type": "choice",
#       "required": false,
#       "defaultValue": "7d",
#       "options": [
#         {"label": "7 days",  "label@zh-Hans": "7 天",  "label@en": "7 days",  "value": "7d"},
#         {"label": "15 days", "label@zh-Hans": "15 天", "label@en": "15 days", "value": "15d"},
#         {"label": "30 days", "label@zh-Hans": "30 天", "label@en": "30 days", "value": "30d"}
#       ]
#     },
#     {
#       "name": "CLAUDE_ONLY",
#       "label": "Claude Models Only",
#       "label@zh-Hans": "仅 Claude 模型",
#       "label@en": "Claude Models Only",
#       "type": "boolean",
#       "required": false,
#       "defaultValue": "false"
#     },
#     {
#       "name": "DATA_DIR",
#       "label": "Data Directory",
#       "label@zh-Hans": "数据目录",
#       "label@en": "Data Directory",
#       "type": "directory",
#       "required": false,
#       "defaultValue": "~/.claude",
#       "placeholder": "~/.claude"
#     }
#   ]
# }
# /UsageBoardPlugin

import json
import os
import sys
import glob
import subprocess
from datetime import datetime, timezone, timedelta
from urllib import request as urllib_request

# ─── Constants ────────────────────────────────────────────────────────────────

PLAN_5H = {"pro": 44_000, "max5": 88_000, "max20": 220_000}
CACHE_VERSION = 2
CACHE_FILENAME = ".usageboard-chart-cache.json"

TRANSLATIONS = {
    "five_hour":     {"en": "5-hour usage",                                             "zh-Hans": "5 小时用量"},
    "weekly":        {"en": "Weekly usage",                                              "zh-Hans": "周用量"},
    "design_weekly": {"en": "Design weekly usage",                                       "zh-Hans": "Design 周用量"},
    "no_data_dir":   {"en": "~/.claude not found. Install Claude Code CLI first.",       "zh-Hans": "~/.claude 目录不存在，请先安装 Claude Code CLI"},
    "login_hint":    {"en": "Not signed in. Run claude to sign in.",                     "zh-Hans": "未找到登录凭证，请运行 claude 登录"},
    "api_error":     {"en": "API request failed. Check your network.",                   "zh-Hans": "API 请求失败，请检查网络"},
    "api_401":       {"en": "Credentials expired. Sign in again.",                       "zh-Hans": "登录凭证已失效，请重新登录"},
    "api_5xx":       {"en": "Service unavailable (HTTP {code})",                        "zh-Hans": "服务暂时不可用 (HTTP {code})"},
    "no_stats_data": {"en": "No stats data available",                                   "zh-Hans": "暂无可用统计数据"},
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def parse_usageboard_params():
    params = {}
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--usageboard-param" and i + 1 < len(argv):
            kv = argv[i + 1].split("=", 1)
            if len(kv) == 2:
                params[kv[0]] = kv[1]
            i += 2
        else:
            i += 1
    return params

def app_language(params):
    lang = params.get("USAGEBOARD_LANGUAGE", "en")
    return "zh-Hans" if "zh" in lang else "en"

def translate(lang, key, **kwargs):
    text = TRANSLATIONS.get(key, {}).get(lang, key)
    return text.format(**kwargs) if kwargs else text

def color_for(pct):
    if pct >= 90: return "red"
    if pct >= 80: return "orange"
    if pct >= 60: return "yellow"
    return "blue"

def status_for(pct):
    if pct >= 90: return "critical"
    if pct >= 75: return "warning"
    return "normal"

def to_k(tokens):
    return round(tokens / 1000, 1)

def utc_now():
    return datetime.now(timezone.utc)

def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def local_today():
    return datetime.now().strftime("%Y-%m-%d")

def is_claude_model(model_name):
    return model_name.startswith("claude-")

SCHEMA_VERSION = 1

def success(items, chart=None, badge=None):
    out = {"schemaVersion": SCHEMA_VERSION, "updatedAt": utc_now_iso(), "items": items}
    if chart is not None:
        out["chart"] = chart
    if badge is not None:
        out["badge"] = badge
    print(json.dumps(out, ensure_ascii=False))

def failure(message):
    print(json.dumps({"error": message}, ensure_ascii=False))

# ─── OAuth ────────────────────────────────────────────────────────────────────

def load_oauth_token():
    try:
        cmd = ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            token = data.get("claudeAiOauth", {}).get("accessToken")
            if token:
                return token
    except Exception:
        pass
    cred_path = os.path.expanduser("~/.claude/.credentials.json")
    if os.path.isfile(cred_path):
        try:
            with open(cred_path) as f:
                data = json.load(f)
            return data.get("claudeAiOauth", {}).get("accessToken")
        except Exception:
            pass
    return None

def fetch_oauth_usage(token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "anthropic-beta": "oauth-2025-04-20",
    }
    req = urllib_request.Request(
        "https://api.anthropic.com/api/oauth/usage", headers=headers
    )
    try:
        with urllib_request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()), None
    except urllib_request.HTTPError as e:
        return None, e.code
    except Exception:
        return None, None

def build_items_from_oauth(data, lang, params, daily):
    fh = data.get("five_hour", {})
    sd = data.get("seven_day", {})
    design_week = data.get("seven_day_omelette", {})
    fh_pct = float(fh.get("utilization", 0))
    sd_pct = float(sd.get("utilization", 0))
    fh_resets = fh.get("resets_at")
    sd_resets = sd.get("resets_at")

    stat_period = params.get("STAT_PERIOD", "7d")
    claude_only = params.get("CLAUDE_ONLY", "false").lower() == "true"
    plan = params.get("PLAN", "pro")
    limit_5h = PLAN_5H.get(plan, 44_000)

    stat_days = {"7d": 7, "15d": 15, "30d": 30}.get(stat_period, 7)
    date_list = [
        (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(stat_days - 1, -1, -1)
    ]
    tokens_stat = sum_tokens(daily, date_list, claude_only)
    multiplier = {"7d": 33.6, "15d": 72.0, "30d": 144.0}.get(stat_period, 33.6)
    limit_stat_k = to_k(limit_5h * multiplier)
    stat_pct = (to_k(tokens_stat) / limit_stat_k * 100) if limit_stat_k > 0 else 0

    items = [
        {
            "id": "claude-five-hour",
            "name": translate(lang, "five_hour"),
            "displayStyle": "percent",
            "used": round(min(fh_pct, 100), 1),
            "limit": 100,
            "resetAt": fh_resets,
            "color": color_for(fh_pct),
            "status": status_for(fh_pct),
        },
        {
            "id": "claude-seven-day",
            "name": translate(lang, "weekly"),
            "displayStyle": "percent",
            "used": round(min(sd_pct, 100), 1),
            "limit": 100,
            "resetAt": sd_resets,
            "color": color_for(sd_pct),
            "status": status_for(sd_pct),
        },
    ]

    if isinstance(design_week, dict) and design_week:
        design_pct = float(design_week.get("utilization", 0))
        items.append({
            "id": "claude-design-seven-day",
            "name": translate(lang, "design_weekly"),
            "displayStyle": "percent",
            "used": round(min(design_pct, 100), 1),
            "limit": 100,
            "resetAt": design_week.get("resets_at"),
            "color": color_for(design_pct),
            "status": status_for(design_pct),
        })

    return items

# ─── JSONL scanning ───────────────────────────────────────────────────────────

def all_jsonl_files(data_dir):
    expanded = os.path.expanduser(data_dir)
    return glob.glob(os.path.join(expanded, "projects", "**", "*.jsonl"), recursive=True)

def recent_jsonl_files(data_dir):
    yesterday_midnight = (
        datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    ).timestamp()
    return [f for f in all_jsonl_files(data_dir) if os.path.getmtime(f) >= yesterday_midnight]

def parse_records(files, start_dt, end_dt):
    seen_ids = set()
    records = []
    for filepath in files:
        try:
            with open(filepath, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if obj.get("type") != "assistant":
                        continue
                    msg = obj.get("message", {})
                    msg_id = msg.get("id")
                    if not msg_id or msg_id in seen_ids:
                        continue
                    seen_ids.add(msg_id)
                    usage = msg.get("usage", {})
                    total = (
                        usage.get("input_tokens", 0)
                        + usage.get("output_tokens", 0)
                        + usage.get("cache_creation_input_tokens", 0)
                        + usage.get("cache_read_input_tokens", 0)
                    )
                    if total <= 0:
                        continue
                    raw_ts = obj.get("timestamp", "")
                    if not raw_ts:
                        continue
                    try:
                        ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                    except Exception:
                        continue
                    if start_dt <= ts <= end_dt:
                        records.append((ts, msg.get("model", "unknown"), total))
        except Exception:
            continue
    return records

def group_by_local_date(records):
    result = {}
    for ts, model, tokens in records:
        day = ts.astimezone().strftime("%Y-%m-%d")
        result.setdefault(day, {})
        result[day][model] = result[day].get(model, 0) + tokens
    return result

# ─── Stats cache ──────────────────────────────────────────────────────────────

def _cache_path(data_dir):
    return os.path.join(os.path.expanduser(data_dir), CACHE_FILENAME)

def load_stats_cache(data_dir):
    path = _cache_path(data_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        if data.get("version") != CACHE_VERSION:
            return None
        return data
    except Exception:
        return None

def save_stats_cache(data_dir, cache_data):
    path = _cache_path(data_dir)
    try:
        with open(path, "w") as f:
            json.dump(cache_data, f)
    except Exception:
        pass

def _parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()

def _format_date(d):
    return d.strftime("%Y-%m-%d")

def maintain_cache(data_dir):
    """Build and maintain a 30-day chart cache. Returns {date: {model: tokens}}."""
    today = _parse_date(local_today())
    cutoff = today - timedelta(days=29)

    cache = load_stats_cache(data_dir)
    now = utc_now()

    def full_scan_and_save():
        start_dt = datetime.combine(cutoff, datetime.min.time(), tzinfo=now.astimezone().tzinfo) - timedelta(hours=14)
        records = parse_records(all_jsonl_files(data_dir), start_dt, now)
        by_day = group_by_local_date(records)
        days = {d: by_day.get(d, {}) for d in
                (_format_date(cutoff + timedelta(days=i)) for i in range(30))
                if _parse_date(d) <= today}
        save_stats_cache(data_dir, {
            "version": CACHE_VERSION,
            "last_date": _format_date(today),
            "days": days,
        })
        return days

    if cache is None:
        return full_scan_and_save()

    last_date = _parse_date(cache.get("last_date", "2000-01-01"))
    gap_days = (today - last_date).days

    if gap_days < 0 or gap_days > 30:
        return full_scan_and_save()

    # Today is always dirty — re-scan it. If gap_days >= 1, also scan the missed days.
    scan_start = today if gap_days == 0 else last_date + timedelta(days=1)
    start_dt = datetime.combine(scan_start, datetime.min.time(), tzinfo=now.astimezone().tzinfo) - timedelta(hours=14)
    cutoff_ts = start_dt.timestamp()
    recent_files = [f for f in all_jsonl_files(data_dir) if os.path.getmtime(f) >= cutoff_ts]
    records = parse_records(recent_files, start_dt, now)
    new_days = group_by_local_date(records)

    merged = {}
    for d, v in cache.get("days", {}).items():
        parsed = _parse_date(d)
        if cutoff <= parsed < scan_start:
            merged[d] = v

    day_count = (today - scan_start).days + 1
    for i in range(day_count):
        date_str = _format_date(scan_start + timedelta(days=i))
        merged[date_str] = new_days.get(date_str, {})

    save_stats_cache(data_dir, {
        "version": CACHE_VERSION,
        "last_date": _format_date(today),
        "days": merged,
    })
    return merged

# ─── Token summing ────────────────────────────────────────────────────────────

def sum_tokens(daily, date_list, claude_only):
    total = 0
    for date in date_list:
        for model, tokens in daily.get(date, {}).items():
            if claude_only and not is_claude_model(model):
                continue
            total += tokens
    return total

# ─── Chart ────────────────────────────────────────────────────────────────────

def build_chart(params, daily, lang):
    stat_period = params.get("STAT_PERIOD", "7d")
    claude_only = params.get("CLAUDE_ONLY", "false").lower() == "true"
    stat_days = {"7d": 7, "15d": 15, "30d": 30}.get(stat_period, 7)

    date_list = [
        (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(stat_days - 1, -1, -1)
    ]

    buckets = []
    for date in date_list:
        day_data = daily.get(date, {})
        segments = []
        for model, tokens in sorted(day_data.items()):
            if claude_only and not is_claude_model(model):
                continue
            if tokens > 0:
                segments.append({"model": model, "tokens": tokens})
        buckets.append({"id": date, "label": date[5:], "segments": segments})

    message = None
    if not any(b["segments"] for b in buckets):
        message = translate(lang, "no_stats_data")

    return {"kind": "line", "period": stat_period, "bucketUnit": "day", "buckets": buckets, "message": message}

# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    params = parse_usageboard_params()
    lang = app_language(params)
    data_dir = params.get("DATA_DIR", "~/.claude")

    if not os.path.isdir(os.path.expanduser(data_dir)):
        failure(translate(lang, "no_data_dir"))
        return

    token = load_oauth_token()
    if not token:
        failure(translate(lang, "login_hint"))
        return

    oauth_data, http_code = fetch_oauth_usage(token)
    if not oauth_data:
        if http_code == 401:
            failure(translate(lang, "api_401"))
        elif http_code and http_code >= 500:
            failure(translate(lang, "api_5xx", code=http_code))
        else:
            failure(translate(lang, "api_error"))
        return

    daily = maintain_cache(data_dir)
    items = build_items_from_oauth(oauth_data, lang, params, daily)
    badge = str(oauth_data.get("plan_type", params.get("PLAN", "pro"))).capitalize()
    chart = build_chart(params, daily, lang)

    success(items, chart=chart, badge=badge)

if __name__ == "__main__":
    main()
