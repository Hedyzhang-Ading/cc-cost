"""cc-cost — Claude Code token cost tracker."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path


# ─── ANSI color ──────────────────────────────────────────

class C:
    """Terminal colors — stripped if stdout is not a TTY."""
    _ON = sys.stdout.isatty()

    RST = "\033[0m" if _ON else ""
    BLD = "\033[1m" if _ON else ""
    DIM = "\033[2m" if _ON else ""
    RED = "\033[31m" if _ON else ""
    GRN = "\033[32m" if _ON else ""
    YLW = "\033[33m" if _ON else ""
    BLU = "\033[34m" if _ON else ""
    MAG = "\033[35m" if _ON else ""
    CYN = "\033[36m" if _ON else ""
    WHT = "\033[37m" if _ON else ""

    @staticmethod
    def bold(s: str) -> str:
        return f"{C.BLD}{s}{C.RST}"

    @staticmethod
    def green(s: str) -> str:
        return f"{C.GRN}{s}{C.RST}"

    @staticmethod
    def yellow(s: str) -> str:
        return f"{C.YLW}{s}{C.RST}"

    @staticmethod
    def dim(s: str) -> str:
        return f"{C.DIM}{s}{C.RST}"

    @staticmethod
    def cyan(s: str) -> str:
        return f"{C.CYN}{s}{C.RST}"


# ─── Config ───────────────────────────────────────────────

CONFIG_FILE = Path.home() / ".cc-cost-config.json"
DATA_DIR = Path.home() / ".claude" / "projects"

DEFAULT_PRICING = {
    "claude-opus-4-8":   {"input": 108.0, "output": 540.0, "cache_read": 10.8, "cache_write": 135.0},
    "claude-sonnet-4-6": {"input": 21.6,  "output": 108.0, "cache_read": 2.16, "cache_write": 27.0},
    "claude-haiku-4-5":  {"input": 5.76,  "output": 28.8,  "cache_read": 0.58, "cache_write": 7.2},
    "deepseek-chat":     {"input": 1.0,   "output": 2.0,   "cache_read": 0.02,  "cache_write": 1.0},
    "deepseek-reasoner": {"input": 3.0,   "output": 6.0,   "cache_read": 0.025, "cache_write": 3.0},
    "deepseek-v4-pro":   {"input": 1.0,   "output": 2.0,   "cache_read": 0.02,  "cache_write": 1.0,
                          "_note": "verify at platform.deepseek.com"},
    "default":           {"input": 4.0,   "output": 16.0,  "cache_read": 0.50,  "cache_write": 4.0},
}

DEFAULT_ALIASES: dict[str, str] = {}


def load_config() -> dict:
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
    try:
        if isinstance(ts_raw, (int, float)):
            return float(ts_raw)
        if isinstance(ts_raw, str):
            return datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp() * 1000
    except (ValueError, TypeError):
        pass
    return None


def iter_sessions(projects_dir: Path):
    for jsonl_file in projects_dir.rglob("*.jsonl"):
        parts = jsonl_file.relative_to(projects_dir).parts
        if len(parts) == 2:
            yield jsonl_file, parts[0], jsonl_file.stem


def parse_usage(jsonl_file: Path) -> list[dict]:
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
    for r in records:
        m = r["model"]
        r["cost_input"] = r["input_tokens"] / 1e6 * get_price(m, "input", cfg)
        r["cost_output"] = r["output_tokens"] / 1e6 * get_price(m, "output", cfg)
        r["cost_cache_read"] = r["cache_read_tokens"] / 1e6 * get_price(m, "cache_read", cfg)
        r["cost_cache_write"] = r["cache_write_tokens"] / 1e6 * get_price(m, "cache_write", cfg)
        r["cost_total"] = r["cost_input"] + r["cost_output"] + r["cost_cache_read"] + r["cost_cache_write"]
    return records


def load_all_records(cfg: dict) -> list[dict]:
    if not DATA_DIR.exists():
        return []
    records = []
    for jsonl_file, _proj_dir, _session_id in iter_sessions(DATA_DIR):
        records.extend(parse_usage(jsonl_file))
    return calc_cost(records, cfg)


# ─── Formatting ────────────────────────────────────────────

SEP = C.dim("─" * 72)


def fmt_money(cny: float) -> str:
    if cny < 0.01:
        return C.yellow(f"¥{cny:.4f}")
    elif cny < 1:
        return C.yellow(f"¥{cny:.3f}")
    else:
        return C.yellow(f"¥{cny:.2f}")


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)


def fmt_pct(pct: float) -> str:
    if pct >= 10:
        return C.bold(f"{pct:>5.0f}%")
    elif pct >= 1:
        return f"{pct:>5.0f}%"
    else:
        return C.dim(f"{pct:>5.0f}%")


# ─── Help ──────────────────────────────────────────────────

HELP_TEXT = f"""
{C.bold('cc-cost')} — Claude Code token cost tracker

{C.cyan('Usage:')}
  {C.bold('python3 run.py')}              Today's summary
  {C.bold('python3 run.py')} today        Today by project + model
  {C.bold('python3 run.py')} projects     All projects ranked by cost
  {C.bold('python3 run.py')} daily -d 7   Daily trend (7 days)
  {C.bold('python3 run.py')} all          Overview
  {C.bold('python3 run.py')} config       Pricing & aliases
  {C.bold('python3 run.py')} help         This message

{C.cyan('Examples:')}
  python3 run.py                    # what did I spend today?
  python3 run.py projects           # which project costs most?
  python3 run.py daily -d 30        # last month's trend

{C.cyan('Setup:')}
  Create {C.bold('~/.cc-cost-config.json')} to set pricing & project aliases.
  See {C.bold('python3 run.py config')} for current settings.

{C.dim('Zero dependencies. Zero network requests. Your data stays local.')}
"""


def print_help():
    print(HELP_TEXT)


# ─── Commands ──────────────────────────────────────────────

def _is_first_run(records: list[dict]) -> bool:
    """Detect if user likely hasn't set up aliases."""
    if not CONFIG_FILE.exists():
        return True
    cfg = load_config()
    return not cfg.get("aliases")


def _suggest_setup(cfg: dict):
    """Suggest first-time setup if no config file exists."""
    if CONFIG_FILE.exists() and cfg.get("aliases"):
        return
    print(C.dim("💡 First time?  Run ") + C.bold("python3 run.py config") + C.dim(" to see pricing."))
    print(C.dim("   Set project aliases: create ") + C.bold("~/.cc-cost-config.json"))
    print()


def cmd_today(records: list[dict], cfg: dict):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_ts = today.timestamp() * 1000
    day_records = [r for r in records if r.get("timestamp") and r["timestamp"] >= today_ts]

    if not day_records:
        print(C.dim("\n📭 No Claude Code activity yet today."))
        print(C.dim("   Go build something and come back!\n"))
        _suggest_setup(cfg)
        return

    groups: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {
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

    print(f"\n{C.bold('📊 Today')} — {datetime.now().strftime('%Y-%m-%d')}")
    print(SEP)
    header = f"{'Project':<20} {'Model':<20} {'Input':>8} {'Output':>8} {'Cache':>8} {'Cost':>10}"
    print(C.dim(header))
    print(SEP)

    for proj in sorted(groups):
        models = groups[proj]
        # Only count models with actual tokens
        visible_models = {
            m: v for m, v in models.items()
            if not (v["input"] == 0 and v["output"] == 0 and v["cache_read"] == 0)
        }
        multi = len(visible_models) > 1
        first = True
        for model in sorted(visible_models):
            m = visible_models[model]
            label = proj if first else ""
            print(f"{label:<20} {model:<20} {fmt_tokens(m['input']):>8} "
                  f"{fmt_tokens(m['output']):>8} {fmt_tokens(m['cache_read']):>8} "
                  f"{fmt_money(m['cost']):>10}")
            first = False

        if multi:
            proj_cost = sum(m["cost"] for m in visible_models.values())
            proj_input = sum(m["input"] for m in visible_models.values())
            proj_output = sum(m["output"] for m in visible_models.values())
            proj_cache = sum(m["cache_read"] for m in visible_models.values())
            print(C.dim(f"{'  ── subtotal':<20} {'':<20} {fmt_tokens(proj_input):>8} "
                        f"{fmt_tokens(proj_output):>8} {fmt_tokens(proj_cache):>8} "
                        f"{fmt_money(proj_cost):>10}"))
            print()

    print(SEP)
    print(f"{C.bold('Total'):<20} {'':<20} {fmt_tokens(total_input):>8} "
          f"{fmt_tokens(total_output):>8} {fmt_tokens(total_cache):>8} "
          f"{C.bold(fmt_money(total_cost)):>10}")

    if total_cache > 0:
        avg_input_price = sum(
            r["cache_read_tokens"] / 1e6 * get_price(r["model"], "input", cfg)
            for r in day_records
        )
        actual_cache_cost = sum(r["cost_cache_read"] for r in day_records)
        saved = avg_input_price - actual_cache_cost
        if saved > 0:
            print(f"\n{C.green('💡 Cache hits:')} {fmt_tokens(total_cache)} tokens, "
                  f"{C.green(f'saved ~{fmt_money(saved)}')}")

    _suggest_setup(cfg)


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

    print(f"\n{C.bold('📊 Project Cost Overview')}")
    print(SEP)
    print(C.dim(f"{'Project':<25} {'Sessions':>8} {'Cost':>10} {'Share':>7} {'Active':>24}"))
    print(SEP)

    for proj, g in sorted(groups.items(), key=lambda x: x[1]["cost"], reverse=True):
        pct = g["cost"] / total_cost * 100 if total_cost > 0 else 0
        bar = "█" * int(pct / 5)
        first = datetime.fromtimestamp(g["first_seen"] / 1000).strftime("%m/%d") if g["first_seen"] else "?"
        last = datetime.fromtimestamp(g["last_seen"] / 1000).strftime("%m/%d") if g["last_seen"] else "?"
        active = f"{first} → {last}"
        print(f"{proj:<25} {len(g['sessions']):>8} {fmt_money(g['cost']):>10} "
              f"{fmt_pct(pct)} {C.dim(bar):<10} {C.dim(active):>24}")

    print(SEP)
    print(f"{C.bold('Total'):<25} {'':>8} {C.bold(fmt_money(total_cost)):>10}")

    _suggest_setup(cfg)


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
        print(C.dim(f"\n📭 No records in the last {days} days."))
        return

    max_cost = max(g["cost"] for g in daily.values())
    bar_width = 30

    print(f"\n{C.bold(f'📈 Daily Cost Trend')} {C.dim(f'(last {days} days)')}")
    print(SEP)
    print(C.dim(f"{'Date':<8} {'Cost':>10} {'Input':>8} {'Output':>8} {'Cache':>8}"))
    print(SEP)

    for day in sorted(daily):
        g = daily[day]
        bar_len = int(g["cost"] / max_cost * bar_width) if max_cost > 0 else 0
        bar = "▓" * bar_len + "░" * (bar_width - bar_len)
        print(f"{day:<8} {fmt_money(g['cost']):>10} {fmt_tokens(g['input']):>8} "
              f"{fmt_tokens(g['output']):>8} {fmt_tokens(g['cache_read']):>8} "
              f"{C.dim(bar)}")

    total = sum(g["cost"] for g in daily.values())
    avg = total / len(daily)
    print(SEP)
    print(f"{C.bold('Total'):<8} {C.bold(fmt_money(total)):>10}")
    print(f"\n{C.dim('Daily avg:')} {fmt_money(avg)}  {C.dim('|  30-day projection:')} {fmt_money(avg * 30)}")


def cmd_all(records: list[dict], cfg: dict):
    if not records:
        print(C.dim("\n📭 No Claude Code records found."))
        print(C.dim("   Make sure Claude Code is installed and you have used it.\n"))
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

    print(f"\n{C.bold('🔮 Claude Code — Cost Overview')}")
    print(SEP)
    print(f"  Period:     {first.strftime('%Y-%m-%d')} → {last.strftime('%Y-%m-%d')}")
    print(f"  Sessions:   {len(sessions)}")
    print(f"  Projects:   {len(projects)}")
    print(f"  Total cost: {fmt_money(total_cost)}")
    print(f"  Input:      {fmt_tokens(total_input)} tokens")
    print(f"  Output:     {fmt_tokens(total_output)} tokens")
    print(f"  Cache hits: {fmt_tokens(total_cache)} tokens ({cache_rate:.1f}%)")
    days = max((last - first).days, 1)
    print(f"  " + C.dim("─" * 25))
    print(f"  Daily avg:  {fmt_money(total_cost / days)}")
    print()

    _suggest_setup(cfg)


def cmd_config(cfg: dict):
    print(f"\n{C.bold('⚙️  Config')}  {C.dim(str(CONFIG_FILE))}")
    if not CONFIG_FILE.exists():
        print(C.dim("   (file doesn't exist yet — using defaults)"))
        print(C.dim("   Create it to customize pricing and project names.\n"))

    print(f"\n{C.cyan('Model pricing')} {C.dim('(per 1M tokens, RMB)')}")
    print(C.dim(f"{'Model':<25} {'Input':>8} {'Output':>8} {'Cache Read':>10} {'Cache Write':>11}"))
    print(SEP)
    for model, prices in cfg["pricing"].items():
        if model == "default":
            continue
        note = prices.pop("_note", "")
        print(f"{model:<25} {'¥'+str(prices['input']):>8} "
              f"{'¥'+str(prices['output']):>8} "
              f"{'¥'+str(prices['cache_read']):>10} "
              f"{'¥'+str(prices['cache_write']):>11}")
        if note:
            print(C.dim(f"  ⚠️  {note}"))

    if cfg.get("aliases"):
        print(f"\n{C.cyan('Project aliases')}")
        for cwd, alias in cfg["aliases"].items():
            print(f"  {C.dim(cwd)} → {C.bold(alias)}")
    else:
        print(f"\n{C.dim('No project aliases set. Add some in ~/.cc-cost-config.json:')}")
        print(C.dim('  {"aliases": {"/Users/you/projects/foo": "🚀 My Project"}}'))


# ─── Entry point ───────────────────────────────────────────

def main():
    cfg = load_config()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "today"

    # Parse flags
    days = 7
    args = sys.argv[2:]
    for i, a in enumerate(args):
        if a in ("-d", "--days") and i + 1 < len(args):
            days = int(args[i + 1])

    # --- help ---
    if cmd in ("help", "-h", "--help", "-help"):
        print_help()
        return

    # --- config (no data needed) ---
    if cmd == "config":
        cmd_config(cfg)
        return

    # --- load data ---
    if not DATA_DIR.exists():
        print(C.dim("\n📭 No Claude Code data found."))
        print(C.dim(f"   Expected at: {DATA_DIR}"))
        print(C.dim("   Make sure Claude Code is installed and you've used it.\n"))
        return

    records = load_all_records(cfg)

    if not records:
        print(C.dim("\n📭 No session data found. Use Claude Code first, then try again.\n"))
        return

    # --- dispatch ---
    if cmd == "today":
        cmd_today(records, cfg)
    elif cmd in ("projects", "proj"):
        cmd_projects(records, cfg)
    elif cmd in ("daily", "trend"):
        cmd_daily(records, cfg, days)
    elif cmd == "all":
        cmd_all(records, cfg)
    else:
        print(f"\n{C.yellow('Unknown command:')} {cmd}")
        print(f"Try {C.bold('python3 run.py help')}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
