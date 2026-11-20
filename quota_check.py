from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

BASE_DIR = Path(__file__).resolve().parent
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
CLAUDE_USAGE_FILE = BASE_DIR / "data" / "claude_usage.jsonl"
GEMINI_CHATS_DIR = Path.home() / ".gemini" / "tmp"
GEMINI_DAILY_LIMIT = 1500


def _pacific_tz() -> timezone | ZoneInfo:
    try:
        return ZoneInfo("America/Los_Angeles")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=-8))


def _parse_time(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(float(val), tz=timezone.utc).astimezone()
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            return datetime.fromtimestamp(float(s), tz=timezone.utc).astimezone()
        except ValueError:
            pass
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
            return dt.astimezone() if dt.tzinfo else dt.replace(tzinfo=timezone.utc).astimezone()
        except ValueError:
            return None
    return None


def _fmt_window(label: str, pct: Any, resets_at: Any, now: datetime) -> str:
    pct_num = float(pct)
    reset_dt = _parse_time(resets_at)
    if reset_dt is None:
        return f"{label}: {pct_num:g}% used, resets unknown"
    diff_h = (reset_dt - now).total_seconds() / 3600.0
    when = reset_dt.strftime("%a %b %d %H:%M")
    if diff_h <= 0:
        return f"{label}: {pct_num:g}% used, resets {when} (reset passed, needs fresh data)"
    return f"{label}: {pct_num:g}% used, resets {when} (in {diff_h:.1f}h)"


def parse_codex(path: Path | str = CODEX_SESSIONS_DIR, now: datetime | None = None) -> str:
    now = now or datetime.now().astimezone()
    p = Path(path)
    if not p.exists():
        return "Codex          unknown (no ~/.codex/sessions found)"
    if p.is_dir():
        files = sorted(p.rglob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            return "Codex          unknown (no session jsonl files)"
        candidates = files[:20]
    else:
        candidates = [p]

    last_rl: dict[str, Any] | None = None
    last_ts: Any = None
    plan: str | None = None
    for target in candidates:
        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            if not p.is_dir():
                return f"Codex          unknown ({exc})"
            continue

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            payload = obj.get("payload")
            if isinstance(payload, dict) and isinstance(payload.get("rate_limits"), dict):
                last_rl = payload["rate_limits"]
                last_ts = obj.get("timestamp") or payload.get("timestamp")
                plan = last_rl.get("plan_type") or payload.get("plan_type")
        if last_rl:
            break

    if not last_rl:
        return "Codex          unknown (no rate_limits in recent sessions)"
    try:
        pri = last_rl.get("primary") or {}
        sec = last_rl.get("secondary") or {}
        week_str = _fmt_window("week", sec["used_percent"], sec.get("resets_at"), now)
        five_str = _fmt_window("5h", pri["used_percent"], pri.get("resets_at"), now)
    except (KeyError, TypeError, ValueError):
        return "Codex          unknown (malformed rate_limits data)"

    ts_dt = _parse_time(last_ts)
    ts_str = ts_dt.strftime("%Y-%m-%d %H:%M") if ts_dt else str(last_ts or "unknown")
    head = f"Codex ({plan})" if plan else "Codex"
    return f"{head:<14} {week_str} | {five_str} | data from {ts_str}"


def parse_claude(path: Path | str = CLAUDE_USAGE_FILE, now: datetime | None = None) -> str:
    now = now or datetime.now().astimezone()
    p = Path(path)
    if not p.exists():
        return "Claude         unknown (no data/claude_usage.jsonl yet)"
    last_obj: dict[str, Any] | None = None
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "five_hour" in obj and "seven_day" in obj:
                last_obj = obj
    except OSError as exc:
        return f"Claude         unknown ({exc})"

    if not last_obj:
        return "Claude         unknown (no valid usage lines)"
    try:
        fh = last_obj["five_hour"]
        sd = last_obj["seven_day"]
        week_str = _fmt_window("week", sd["used_percentage"], sd.get("resets_at"), now)
        five_str = _fmt_window("5h", fh["used_percentage"], fh.get("resets_at"), now)
    except (KeyError, TypeError, ValueError):
        return "Claude         unknown (malformed usage line)"
    ts_dt = _parse_time(last_obj.get("ts"))
    ts_str = ts_dt.strftime("%Y-%m-%d %H:%M") if ts_dt else str(last_obj.get("ts") or "unknown")
    return f"{'Claude':<14} {week_str} | {five_str} | data from {ts_str}"


def parse_gemini(path: Path | str = GEMINI_CHATS_DIR, now: datetime | None = None) -> str:
    p = Path(path)
    if not p.exists():
        return "Gemini CLI     unknown (no ~/.gemini/tmp found)"
    tz = _pacific_tz()
    now_pt = (now or datetime.now(tz)).astimezone(tz)
    midnight_pt = now_pt.replace(hour=0, minute=0, second=0, microsecond=0)
    next_midnight_pt = midnight_pt + timedelta(days=1)
    hours_left = (next_midnight_pt - now_pt).total_seconds() / 3600.0

    count = 0
    midnight_timestamp = midnight_pt.timestamp()
    for chat_file in p.glob("*/chats/*.jsonl"):
        try:
            if chat_file.stat().st_mtime < midnight_timestamp:
                continue
            lines = chat_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict) or obj.get("type") != "gemini":
                continue
            timestamp = _parse_time(obj.get("timestamp"))
            if timestamp is not None and timestamp.astimezone(tz) >= midnight_pt:
                count += 1
    return f"{'Gemini CLI':<14} ~{count} / {GEMINI_DAILY_LIMIT} responses today | resets in {hours_left:.1f}h (Pacific midnight)"


def parse_agy_usage(text: str, now: datetime | None = None) -> list[str]:
    now = now or datetime.now().astimezone()
    groups: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        columns = line.split("\t")
        if len(columns) != 4:
            continue
        group, label, remaining, reset = columns
        if "Weekly" in label:
            window = "week"
        elif "Five Hour" in label:
            window = "5h"
        else:
            continue
        try:
            used = 100 - float(remaining.removesuffix("%").strip())
        except ValueError:
            continue
        groups.setdefault(group, {})[window] = _fmt_window(window, used, reset, now)

    if not groups:
        return ["Antigravity    unknown (no quota lines in agy /usage output)"]

    short_names = {
        "Gemini Models": "Gemini",
        "Claude and GPT models": "Claude/GPT",
        "Gemini 4 Argon": "Argon",
    }
    lines = []
    for group, windows in groups.items():
        short = short_names.get(group, group)
        lines.append(f"{'agy ' + short:<14} " + " | ".join(
            windows[window] for window in ("week", "5h") if window in windows
        ))
    return lines


def parse_antigravity(now: datetime | None = None, runner: Any = subprocess.run) -> list[str]:
    try:
        result = runner(
            ["agy", "-p", "/usage", "--print-timeout", "60s"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
        )
    except FileNotFoundError:
        return ["Antigravity    unknown (agy not found)"]
    except subprocess.TimeoutExpired:
        return ["Antigravity    unknown (agy /usage timed out)"]
    return parse_agy_usage(result.stdout, now=now)


def main() -> None:
    for line in (parse_codex(), parse_claude(), parse_gemini(), *parse_antigravity()):
        print(line)


if __name__ == "__main__":
    main()
