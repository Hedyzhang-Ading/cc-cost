"""Main module for cc-cost — parses Claude Code sessions and displays costs."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path


# ─── Config ───────────────────────────────────────────────

CONFIG_FILE = Path.home() / ".cc-cost-config.json"

# Pricing in RMB (元) per 1M tokens
DEFAULT_PRICING = {
    "claude-opus-4-8": {
        "input": 108.0, "output": 540.0,
        "cache_read": 10.8, "cache_write": 135.0,
    },
    "claude-sonnet-4-6": {
        "input": 21.6, "output": 108.0,
        "cache_read": 2.16, "cache_write": 27.0,
    },
    "claude-haiku-4-5": {
        "input": 5.76, "output": 28.8,
        "cache_read": 0.58, "cache_write": 7.2,
    },
    "deepseek-chat": {
        "input": 1.0, "output": 2.0,
        "cache_read": 0.02, "cache_write": 1.0,
    },
    "deepseek-reasoner": {
        "input": 3.0, "output": 6.0,
        "cache_read": 0.025, "cache_write": 3.0,
    },
    "deepseek-v4-pro": {
        "input": 1.0, "output": 2.0,
        "cache_read": 0.02, "cache_write": 1.0,
        "_note": "V4 Pro — verify actual pricing at platform.deepseek.com",
    },
    "default": {
        "input": 4.0, "output": 16.0,
        "cache_read": 0.50, "cache_write": 4.0,
    },
}

DEFAULT_ALIASES = {
    "/Users/apple": "🏠 home",
}


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
    else:
        cfg = {}
    cfg.setdefault("pricing", DEFAULT_PRICING)
    cfg.setdefault("aliases", DEFAULT_ALIASES)
    return cfg


def get_price(model: str, key: str, cfg: dict) -> float:
    pricing = cfg["pricing"]
    m = pricing.get(model, pricing.get("default", {}))
    return m.get(key, 0)


def project_name(cwd: str, cfg: dict) -> str:
    aliases = cfg["aliases"]
    if cwd in aliases:
        return aliases[cwd]
    p = Path(cwd)
    return p.name if p.name else str(p)


# ─── Data parsing ─────────────────────────────────────────

def parse_timestamp(ts_raw) -> float | None:
    """Convert ISO timestamp or epoch ms to float epoch ms."""
    try:
        if isinstance(ts_raw, (int, float)):
            return float(ts_raw)
        if isinstance(ts_raw, str):
            return datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp() * 1000
    except (ValueError, TypeError):
        pass
    return None


def iter_sessions(projects_dir: Path):
    """Yield (jsonl_path, project_dir_name, session_id) for all session files."""
    for jsonl_file in projects_dir.rglob("*.jsonl"):
        parts = jsonl_file.relative_to(projects_dir).parts
        if len(parts) == 2:
            yield jsonl_file, parts[0], jsonl_file.stem


def parse_usage(jsonl_file: Path) -> list[dict]:
    """Extract token usage records from a session JSONL file."""
    records = []
    if jsonl_file.stat().st_size == 0:
        return records
    with open(jsonl_file, errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "assistant":
                continue
            msg = d.get("message", {})
            usage = msg.get("usage", {})
            if not usage:
                continue

            records.append({
                "timestamp": parse_timestamp(d.get("timestamp")),
                "cwd": d.get("cwd", "unknown"),
                "model": msg.get("model", "unknown"),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
                "cache_write_tokens": (
                    usage.get("cache_creation", {}).get("ephemeral_5m_input_tokens", 0) +
                    usage.get("cache_creation", {}).get("ephemeral_1h_input_tokens", 0)
                ),
                "session_id": d.get("sessionId", "?"),
            })
    return records


def calc_cost(records: list[dict], cfg: dict) -> list[dict]:
    """Add cost fields to each record."""
    for r in records:
        m = r["model"]
        r["cost_input"] = r["input_tokens"] / 1e6 * get_price(m, "input", cfg)
        r["cost_output"] = r["output_tokens"] / 1e6 * get_price(m, "output", cfg)
        r["cost_cache_read"] = r["cache_read_tokens"] / 1e6 * get_price(m, "cache_read", cfg)
        r["cost_cache_write"] = r["cache_write_tokens"] / 1e6 * get_price(m, "cache_write", cfg)
        r["cost_total"] = r["cost_input"] + r["cost_output"] + r["cost_cache_read"] + r["cost_cache_write"]
    return records


def load_all_records(cfg: dict) -> list[dict]:
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return []
    records = []
    for jsonl_file, _proj_dir, _session_id in iter_sessions(projects_dir):
        records.extend(parse_usage(jsonl_file))
    return calc_cost(records, cfg)


# ─── Formatting ────────────────────────────────────────────

HR = "─" * 72


def fmt_money(cny: float) -> str:
    if cny < 0.01:
        return f"¥{cny:.4f}"
    elif cny < 1:
        return f"¥{cny:.3f}"
    else:
        return f"¥{cny:.2f}"


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)


# ─── Commands ──────────────────────────────────────────────

def cmd_today(records: list[dict], cfg: dict):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_ts = today.timestamp() * 1000
    day_records = [r for r in records if r.get("timestamp") and r["timestamp"] >= today_ts]

    if not day_records:
        print("No Claude Code activity yet today. Go build something!")
        return

    groups = defaultdict(lambda: defaultdict(lambda: {
        "input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "cost": 0.0, "msgs": 0,
    }))
    for r in day_records:
        proj = project_name(r["cwd"], cfg)
        g = groups[proj][r["model"]]
        g["input"] += r["input_tokens"]
        g["output"] += r["output_tokens"]
        g["cache_read"] += r["cache_read_tokens"]
        g["cache_write"] += r["cache_write_tokens"]
        g["cost"] += r["cost_total"]
        g["msgs"] += 1

    total_cost = sum(r["cost_total"] for r in day_records)
    total_input = sum(r["input_tokens"] for r in day_records)
    total_output = sum(r["output_tokens"] for r in day_records)
    total_cache = sum(r["cache_read_tokens"] for r in day_records)

    print(f"\n📊 Today — {datetime.now().strftime('%Y-%m-%d')}")
    print(HR)
    print(f"{'Project':<20} {'Model':<20} {'Input':>8} {'Output':>8} {'Cache':>8} {'Cost':>10}")
    print(HR)

    for proj in sorted(groups):
        models = groups[proj]
        first = True
        for model in sorted(models):
            m = models[model]
            if m["input"] == 0 and m["output"] == 0 and m["cache_read"] == 0:
                continue
            label = proj if first else ""
            print(f"{label:<20} {model:<20} {fmt_tokens(m['input']):>8} "
                  f"{fmt_tokens(m['output']):>8} {fmt_tokens(m['cache_read']):>8} "
                  f"{fmt_money(m['cost']):>10}")
            first = False
        proj_cost = sum(m["cost"] for m in models.values())
        proj_input = sum(m["input"] for m in models.values())
        proj_output = sum(m["output"] for m in models.values())
        proj_cache = sum(m["cache_read"] for m in models.values())
        print(f"{'  ── subtotal':<20} {'':<20} {fmt_tokens(proj_input):>8} "
              f"{fmt_tokens(proj_output):>8} {fmt_tokens(proj_cache):>8} "
              f"{fmt_money(proj_cost):>10}")
        print()

    print(HR)
    print(f"{'Total':<20} {'':<20} {fmt_tokens(total_input):>8} "
          f"{fmt_tokens(total_output):>8} {fmt_tokens(total_cache):>8} "
          f"{fmt_money(total_cost):>10}")

    if total_cache > 0:
        avg_input_price = sum(
            r["cache_read_tokens"] / 1e6 * get_price(r["model"], "input", cfg)
            for r in day_records
        )
        actual_cache_cost = sum(r["cost_cache_read"] for r in day_records)
        saved = avg_input_price - actual_cache_cost
        if saved > 0:
            print(f"\n💡 Cache hits: {fmt_tokens(total_cache)} tokens, "
                  f"saved ~{fmt_money(saved)}")


def cmd_projects(records: list[dict], cfg: dict):
    groups = defaultdict(lambda: {
        "input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
        "cost": 0.0, "sessions": set(), "first_seen": None, "last_seen": None,
    })
    for r in records:
        g = groups[project_name(r["cwd"], cfg)]
        g["input"] += r["input_tokens"]
        g["output"] += r["output_tokens"]
        g["cache_read"] += r["cache_read_tokens"]
        g["cache_write"] += r["cache_write_tokens"]
        g["cost"] += r["cost_total"]
        g["sessions"].add(r["session_id"])
        ts = r.get("timestamp")
        if ts:
            if g["first_seen"] is None or ts < g["first_seen"]:
                g["first_seen"] = ts
            if g["last_seen"] is None or ts > g["last_seen"]:
                g["last_seen"] = ts

    total_cost = sum(g["cost"] for g in groups.values())

    print(f"\n📊 Project Cost Overview")
    print(HR)
    print(f"{'Project':<25} {'Sessions':>8} {'Cost':>10} {'Share':>7} {'Active':>24}")
    print(HR)

    for proj, g in sorted(groups.items(), key=lambda x: x[1]["cost"], reverse=True):
        pct = g["cost"] / total_cost * 100 if total_cost > 0 else 0
        bar = "█" * int(pct / 5)
        first = datetime.fromtimestamp(g["first_seen"] / 1000).strftime("%m/%d") if g["first_seen"] else "?"
        last = datetime.fromtimestamp(g["last_seen"] / 1000).strftime("%m/%d") if g["last_seen"] else "?"
        active = f"{first} → {last}"
        print(f"{proj:<25} {len(g['sessions']):>8} {fmt_money(g['cost']):>10} "
              f"{pct:>5.0f}% {bar:<10} {active:>24}")

    print(HR)
    print(f"{'Total':<25} {'':>8} {fmt_money(total_cost):>10}")


def cmd_daily(records: list[dict], cfg: dict, days: int = 7):
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_ts = cutoff.timestamp() * 1000

    daily = defaultdict(lambda: {"cost": 0.0, "input": 0, "output": 0, "cache_read": 0})
    for r in records:
        ts = r.get("timestamp")
        if not ts or ts < cutoff_ts:
            continue
        day = datetime.fromtimestamp(ts / 1000).strftime("%m/%d")
        g = daily[day]
        g["cost"] += r["cost_total"]
        g["input"] += r["input_tokens"]
        g["output"] += r["output_tokens"]
        g["cache_read"] += r["cache_read_tokens"]

    if not daily:
        print(f"No records in the last {days} days.")
        return

    max_cost = max(g["cost"] for g in daily.values())
    bar_width = 30

    print(f"\n📈 Daily Cost Trend (last {days} days)")
    print(HR)
    print(f"{'Date':<8} {'Cost':>10} {'Input':>8} {'Output':>8} {'Cache':>8}")
    print(HR)

    for day in sorted(daily):
        g = daily[day]
        bar_len = int(g["cost"] / max_cost * bar_width) if max_cost > 0 else 0
        bar = "▓" * bar_len + "░" * (bar_width - bar_len)
        print(f"{day:<8} {fmt_money(g['cost']):>10} {fmt_tokens(g['input']):>8} "
              f"{fmt_tokens(g['output']):>8} {fmt_tokens(g['cache_read']):>8} {bar}")

    total = sum(g["cost"] for g in daily.values())
    avg = total / len(daily)
    print(HR)
    print(f"{'Total':<8} {fmt_money(total):>10}")
    print(f"\nDaily avg: {fmt_money(avg)}  |  30-day projection: {fmt_money(avg * 30)}")


def cmd_all(records: list[dict], cfg: dict):
    if not records:
        print("No Claude Code records found.")
        return

    sessions = set(r["session_id"] for r in records)
    projects = set(project_name(r["cwd"], cfg) for r in records)
    total_cost = sum(r["cost_total"] for r in records)
    total_input = sum(r["input_tokens"] for r in records)
    total_output = sum(r["output_tokens"] for r in records)
    total_cache = sum(r["cache_read_tokens"] for r in records)

    timestamps = [r["timestamp"] for r in records if r.get("timestamp")]
    first = datetime.fromtimestamp(min(timestamps) / 1000) if timestamps else datetime.now()
    last = datetime.fromtimestamp(max(timestamps) / 1000) if timestamps else datetime.now()

    cache_rate = total_cache / (total_input + total_cache) * 100 if (total_input + total_cache) > 0 else 0

    print(f"\n🔮 Claude Code — Cost Overview")
    print(HR)
    print(f"  Period:     {first.strftime('%Y-%m-%d')} → {last.strftime('%Y-%m-%d')}")
    print(f"  Sessions:   {len(sessions)}")
    print(f"  Projects:   {len(projects)}")
    print(f"  Total cost: {fmt_money(total_cost)}")
    print(f"  Input:      {fmt_tokens(total_input)} tokens")
    print(f"  Output:     {fmt_tokens(total_output)} tokens")
    print(f"  Cache hits: {fmt_tokens(total_cache)} tokens ({cache_rate:.1f}%)")
    days = max((last - first).days, 1)
    print(f"  ─────────────────────────")
    print(f"  Daily avg:  {fmt_money(total_cost / days)}")
    print()


def cmd_config(cfg: dict):
    print(f"\n⚙️  Config file: {CONFIG_FILE}")
    print(f"\nModel pricing (per 1M tokens):")
    print(f"{'Model':<25} {'Input':>8} {'Output':>8} {'Cache Read':>10} {'Cache Write':>11}")
    print(HR)
    for model, prices in cfg["pricing"].items():
        if model == "default":
            continue
        note = prices.pop("_note", "")
        print(f"{model:<25} {'¥'+str(prices['input']):>8} "
              f"{'¥'+str(prices['output']):>8} "
              f"{'¥'+str(prices['cache_read']):>10} "
              f"{'¥'+str(prices['cache_write']):>11}")
        if note:
            print(f"  ⚠️  {note}")

    if cfg.get("aliases"):
        print(f"\nProject aliases:")
        for cwd, alias in cfg["aliases"].items():
            print(f"  {cwd} → {alias}")


# ─── Entry point ───────────────────────────────────────────

def main():
    cfg = load_config()

    cmd = sys.argv[1] if len(sys.argv) > 1 else "today"
    days = 7

    args = sys.argv[2:]
    for i, a in enumerate(args):
        if a == "-d" and i + 1 < len(args):
            days = int(args[i + 1])

    records = load_all_records(cfg)

    if cmd == "today":
        cmd_today(records, cfg)
    elif cmd in ("projects", "proj"):
        cmd_projects(records, cfg)
    elif cmd in ("daily", "trend"):
        cmd_daily(records, cfg, days)
    elif cmd == "all":
        cmd_all(records, cfg)
    elif cmd == "config":
        cmd_config(cfg)
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: cc-cost [today|projects|daily|all|config] [-d N]")
        sys.exit(1)


if __name__ == "__main__":
    main()
