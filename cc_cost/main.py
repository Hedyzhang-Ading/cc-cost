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

# Official benchmark prices (元/1M tokens) for comparison
# Format: (input, output, cache_read, source)
BENCHMARK_PRICES: dict[str, list[tuple[str, float, float, float, str]]] = {
    "claude-opus-4-8": [
        ("Anthropic 官方", 108.0, 540.0, 10.8, "anthropic.com/pricing"),
    ],
    "claude-sonnet-4-6": [
        ("Anthropic 官方", 21.6, 108.0, 2.16, "anthropic.com/pricing"),
    ],
    "claude-haiku-4-5": [
        ("Anthropic 官方", 5.76, 28.8, 0.58, "anthropic.com/pricing"),
    ],
    "deepseek-chat": [
        ("DeepSeek 官方", 1.0, 2.0, 0.02, "platform.deepseek.com"),
    ],
    "deepseek-reasoner": [
        ("DeepSeek 官方", 3.0, 6.0, 0.025, "platform.deepseek.com"),
    ],
    "deepseek-v4-pro": [
        ("DeepSeek 官方", 1.0, 2.0, 0.02, "platform.deepseek.com"),
        ("OpenRouter", 1.1, 2.2, 0.028, "openrouter.ai"),
    ],
    "gpt-4o": [
        ("OpenAI 官方", 18.0, 72.0, 9.0, "openai.com/pricing"),
        ("OpenRouter", 18.0, 72.0, 9.0, "openrouter.ai"),
    ],
    "gpt-4o-mini": [
        ("OpenAI 官方", 1.08, 4.32, 0.54, "openai.com/pricing"),
        ("OpenRouter", 1.08, 4.32, 0.54, "openrouter.ai"),
    ],
    "claude-3.5-sonnet": [
        ("Anthropic 官方", 21.6, 108.0, 2.16, "anthropic.com/pricing"),
    ],
}


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
  {C.bold('python3 run.py')} report       Weekly digest
  {C.bold('python3 run.py')} all          Overview
  {C.bold('python3 run.py')} config       Pricing & aliases
  {C.bold('python3 run.py')} insights     Cost-saving tips
  {C.bold('python3 run.py')} compare      Compare vs official prices
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

    # Quick insight
    insights = analyze(day_records, cfg)
    if insights:
        print(f"  {insights[0]}")

    # Anomaly check
    anomaly_msg = _anomaly_warning(records)
    if anomaly_msg:
        print(f"  {anomaly_msg}")

    # Budget check
    budget_msg = check_budget(records, cfg)
    if budget_msg:
        print(f"  {budget_msg}")

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

    # Quick insights
    insights = analyze(records, cfg)
    if insights:
        print(f"\n  {C.bold('Top insight:')} {insights[0]}")

    # Budget
    budget_msg = check_budget(records, cfg)
    if budget_msg:
        print(f"  {budget_msg}")
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


# ─── Insights engine ───────────────────────────────────────

def analyze(records: list[dict], cfg: dict) -> list[str]:
    """Generate cost-saving insights from usage patterns."""
    insights = []

    if not records:
        return insights

    # Group by model (skip synthetic/unknown)
    model_stats: dict[str, dict] = defaultdict(lambda: {
        "cost": 0.0, "input": 0, "output": 0, "msgs": 0,
    })
    for r in records:
        m = r["model"]
        if m in ("<synthetic>", "unknown", "default"):
            continue
        model_stats[m]["cost"] += r["cost_total"]
        model_stats[m]["input"] += r["input_tokens"]
        model_stats[m]["output"] += r["output_tokens"]
        model_stats[m]["msgs"] += 1

    total_cost = sum(s["cost"] for s in model_stats.values())
    total_input = sum(s["input"] for s in model_stats.values())
    total_output = sum(s["output"] for s in model_stats.values())
    total_cache_read = sum(r["cache_read_tokens"] for r in records)
    total_cache_write = sum(r["cache_write_tokens"] for r in records)

    # ── 1. Model tier check ──
    # Compare: what if user switched to a cheaper model?
    current_model = max(model_stats, key=lambda m: model_stats[m]["cost"])
    alternatives = {
        "deepseek-v4-pro": ("deepseek-chat", "DeepSeek V3"),
        "deepseek-reasoner": ("deepseek-chat", "DeepSeek V3"),
        "claude-opus-4-8": ("claude-sonnet-4-6", "Claude Sonnet"),
        "claude-sonnet-4-6": ("claude-haiku-4-5", "Claude Haiku"),
    }
    if current_model in alternatives:
        alt_id, alt_name = alternatives[current_model]
        s = model_stats[current_model]
        alt_cost = (
            s["input"] / 1e6 * get_price(alt_id, "input", cfg) +
            s["output"] / 1e6 * get_price(alt_id, "output", cfg)
        )
        saved = s["cost"] - alt_cost
        if saved > s["cost"] * 0.1:  # >10% savings
            insights.append(
                f"{C.yellow('💡 Model switch:')} {current_model} → {alt_name} "
                f"would save ~{fmt_money(saved)} "
                f"({saved / s['cost'] * 100:.0f}% cheaper). "
                f"Use for routine tasks, keep {current_model} for complex work."
            )

    # ── 2. Cache efficiency ──
    cache_hit_rate = (
        total_cache_read / (total_input + total_cache_read) * 100
        if (total_input + total_cache_read) > 0 else 0
    )
    if cache_hit_rate < 50 and total_cache_read > 0:
        insights.append(
            f"{C.yellow('💡 Cache hit rate:')} {cache_hit_rate:.1f}% — low. "
            f"Structure your CLAUDE.md and prompts consistently "
            f"to increase cache reuse. Each 1% → save ~{fmt_money(total_cost * 0.005)}."
        )
    elif cache_hit_rate > 90:
        insights.append(
            f"{C.green('✅ Cache hit rate:')} {cache_hit_rate:.1f}% — excellent. "
            f"Your prompt structure is cache-friendly."
        )

    if total_cache_write > total_cache_read * 2 and total_cache_write > 1_000_000:
        insights.append(
            f"{C.yellow('💡 Cache waste:')} Writing {fmt_tokens(total_cache_write)} "
            f"but only reading {fmt_tokens(total_cache_read)}. "
            f"Long sessions without follow-up waste cache writes."
        )

    # ── 3. Spend concentration ──
    proj_costs: dict[str, float] = defaultdict(float)
    for r in records:
        proj_costs[project_name(r["cwd"], cfg)] += r["cost_total"]
    sorted_projects = sorted(proj_costs.values(), reverse=True)
    if len(sorted_projects) >= 2:
        top1 = sorted_projects[0]
        top2 = sorted_projects[1] if len(sorted_projects) > 1 else 0
        if top1 > total_cost * 0.6 and total_cost > 10:
            insights.append(
                f"{C.yellow('💡 Top project:')} One project accounts for "
                f"{top1 / total_cost * 100:.0f}% of spend. "
                f"Consider a dedicated CLAUDE.md with cache-friendly structure "
                f"to reduce token waste on repeated context."
            )

    # ── 4. Output/input ratio ──
    if total_input > 0:
        ratio = total_output / total_input
        if ratio > 0.8:
            insights.append(
                f"{C.yellow('💡 Output ratio:')} {ratio:.1f}:1 — high. "
                f"Model is generating long responses. Tighter prompts with "
                f"output length limits could reduce costs."
            )
        elif ratio < 0.2 and total_output > 100_000:
            insights.append(
                f"{C.green('✅ Output ratio:')} {ratio:.1f}:1 — lean. "
                f"Good prompt discipline."
            )

    # ── 5. Single-model risk ──
    if len(model_stats) == 1 and current_model != "default":
        m = list(model_stats.keys())[0]
        expensive_models = ["claude-opus-4-8", "claude-sonnet-4-6", "deepseek-reasoner"]
        if m in expensive_models:
            insights.append(
                f"{C.yellow('💡 One-model trap:')} You only use {m}. "
                f"Many tasks (summaries, formatting, simple Q&A) don't need "
                f"a reasoning model. Routing simple tasks to a cheaper model "
                f"can cut costs 50-80%."
            )

    return insights


def cmd_insights(records: list[dict], cfg: dict):
    """Show optimization insights."""
    insights = analyze(records, cfg)
    if not insights:
        print(f"\n{C.green('🎉 No obvious savings found.')} "
              f"Your usage looks efficient!\n")
        return

    print(f"\n{C.bold('🧠 Optimization Insights')}")
    print(SEP)
    for i, insight in enumerate(insights, 1):
        print(f"  {i}. {insight}")
        print()

    # Summary
    total_cost = sum(r["cost_total"] for r in records)
    potential_savings = sum(
        # Recalculate model switch savings
        sum(r["cost_total"] for r in records if r["model"] == m) * 0.3
        for m in ["claude-opus-4-8", "deepseek-reasoner"]
        if any(r["model"] == m for r in records)
    )
    if potential_savings > 0:
        print(SEP)
        print(f"  {C.bold('Estimated savings potential:')} {fmt_money(potential_savings)}")
    print()


# ─── Price comparison ──────────────────────────────────────

def cmd_compare(records: list[dict], cfg: dict):
    """Compare your pricing vs official benchmarks."""
    user_pricing = cfg["pricing"]

    # Find which models are actually in use
    models_in_use: dict[str, dict] = defaultdict(lambda: {
        "input": 0, "output": 0, "cache_read": 0, "msgs": 0,
    })
    for r in records:
        m = r["model"]
        if m in ("<synthetic>", "unknown"):
            continue
        models_in_use[m]["input"] += r["input_tokens"]
        models_in_use[m]["output"] += r["output_tokens"]
        models_in_use[m]["cache_read"] += r["cache_read_tokens"]
        models_in_use[m]["msgs"] += 1

    if not models_in_use:
        print(C.dim("\n📭 No model usage data to compare.\n"))
        return

    print(f"\n{C.bold('🏦 Price Comparison')} {C.dim('— your channel vs official')}")
    print(SEP)
    print(f"  {C.dim(f'{"Model":<22} {"Source":<18} {"Input/1M":>10} {"Output/1M":>10} {"Status":>12}')}")

    total_you = 0.0
    total_cheapest = 0.0
    found_issues = False

    for model in sorted(models_in_use):
        usage = models_in_use[model]
        benchmarks = BENCHMARK_PRICES.get(model, [])

        # User's current price
        up = user_pricing.get(model, user_pricing.get("default", {}))
        u_input = up.get("input", 0)
        u_output = up.get("output", 0)

        # Calculate user's actual cost
        user_cost = (
            usage["input"] / 1e6 * u_input +
            usage["output"] / 1e6 * u_output
        )

        # Find the cheapest benchmark for this model
        cheapest = None
        for name, b_input, b_output, b_cache, source in benchmarks:
            b_cost = (
                usage["input"] / 1e6 * b_input +
                usage["output"] / 1e6 * b_output
            )
            if cheapest is None or b_cost < cheapest[0]:
                cheapest = (b_cost, name, b_input, b_output, source)

        print(f"\n  {C.bold(model)}")
        used_in = fmt_tokens(usage["input"])
        used_out = fmt_tokens(usage["output"])
        used_msgs = usage["msgs"]
        print(f"  {C.dim(f'  Used: {used_in} in + {used_out} out  ·  {used_msgs} msgs')}")

        # Show user's price
        line = f"  {'Your channel':<20} {'':<18} {'¥'+str(u_input):>10} {'¥'+str(u_output):>10}"
        print(f"  {line}  {C.dim(f'(paid {fmt_money(user_cost)})')}")
        total_you += user_cost

        # Show all benchmarks
        for name, b_input, b_output, b_cache, source in benchmarks:
            b_cost = (
                usage["input"] / 1e6 * b_input +
                usage["output"] / 1e6 * b_output
            )
            marker = ""
            if b_input == u_input and b_output == u_output:
                marker = C.green("  ← match")
            line = f"  {name:<20} {C.dim(source):<18} {'¥'+str(b_input):>10} {'¥'+str(b_output):>10}"
            print(f"  {line}{marker}")
            if cheapest and name == cheapest[1]:
                total_cheapest += b_cost

        # Overpayment warning
        if cheapest and user_cost > cheapest[0] * 1.05:  # 5% threshold
            diff = user_cost - cheapest[0]
            pct = (user_cost / cheapest[0] - 1) * 100
            print(f"  {C.yellow(f'⚠️  You pay {pct:.0f}% more than {cheapest[1]} → overpaid ~{fmt_money(diff)}')}")
            found_issues = True

        # If user's model has NO benchmark, flag it
        if not benchmarks:
            print(f"  {C.dim('  (no official benchmark for this model)')}")

    print(f"\n{SEP}")
    if total_cheapest > 0 and total_you > total_cheapest * 1.05:
        overpayment = total_you - total_cheapest
        print(f"  {C.yellow(f'Total overpayment: {fmt_money(overpayment)}')}")
        print(f"  {C.dim(f'Your cost: {fmt_money(total_you)}  |  Official: {fmt_money(total_cheapest)}')}")
    else:
        print(f"  {C.green('✅ Price match — you are paying official rates.')}")
    print()


# ─── Budget check ─────────────────────────────────────────

def check_budget(records: list[dict], cfg: dict) -> str | None:
    """Return budget warning if approaching/exceeding monthly limit."""
    budget = cfg.get("monthly_budget", 0)
    if not budget:
        return None

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start_ts = month_start.timestamp() * 1000

    month_cost = sum(
        r["cost_total"] for r in records
        if r.get("timestamp") and r["timestamp"] >= month_start_ts
    )
    pct = month_cost / budget * 100
    days_elapsed = now.day
    days_total = (now.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    days_total = days_total.day
    daily_rate = month_cost / max(days_elapsed, 1)
    projected = daily_rate * days_total
    overshoot_day = None
    if daily_rate > 0:
        remaining = budget - month_cost
        days_left = remaining / daily_rate
        if days_left < days_total - days_elapsed:
            overshoot_day = (now + timedelta(days=days_left + 1)).day

    if pct >= 100:
        return (
            f"{C.yellow('🚨 Budget exceeded:')} {fmt_money(month_cost)} / "
            f"{fmt_money(budget)} ({pct:.0f}%). "
            f"Projected month-end: {fmt_money(projected)}."
        )
    elif pct >= 80:
        return (
            f"{C.yellow('⚠️  Budget warning:')} {fmt_money(month_cost)} / "
            f"{fmt_money(budget)} ({pct:.0f}%). "
            + (f"At this rate, exceeds on day {overshoot_day}." if overshoot_day else "")
        )
    elif pct >= 50:
        return (
            f"{C.dim(f'💳 Budget: {fmt_money(month_cost)} / {fmt_money(budget)} ({pct:.0f}%)  '
                     f'|  projected: {fmt_money(projected)}')}"
        )
    return None


# ─── Anomaly detection ─────────────────────────────────────

def detect_anomaly(records: list[dict]) -> dict | None:
    """Check if today's spend is statistically unusual.

    Returns a dict with anomaly info, or None if normal.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_ts = today_start.timestamp() * 1000
    cutoff = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_ts = cutoff.timestamp() * 1000

    # Daily totals for last 30 days (excluding today)
    daily: dict[str, float] = defaultdict(float)
    for r in records:
        ts = r.get("timestamp")
        if not ts or ts < cutoff_ts:
            continue
        day = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
        daily[day] += r["cost_total"]

    today_key = now.strftime("%Y-%m-%d")
    today_cost = daily.get(today_key, 0)

    # Exclude today from baseline
    past_costs = [c for d, c in daily.items() if d != today_key]
    if len(past_costs) < 5:
        return None

    mean = sum(past_costs) / len(past_costs)
    variance = sum((c - mean) ** 2 for c in past_costs) / len(past_costs)
    std = variance ** 0.5

    if std < 0.1 or today_cost <= mean + 2 * std:
        return None

    # Find the most expensive session today
    top_session = None
    top_cost = 0.0
    today_records = [r for r in records if r.get("timestamp") and r["timestamp"] >= today_ts]
    session_costs: dict[str, float] = defaultdict(float)
    for r in today_records:
        sid = r.get("session_id", "?")
        session_costs[sid] += r["cost_total"]
    if session_costs:
        top_sid = max(session_costs, key=session_costs.get)
        top_cost = session_costs[top_sid]

    return {
        "today_cost": today_cost,
        "mean": mean,
        "std": std,
        "multiplier": today_cost / mean if mean > 0 else 0,
        "top_session_id": top_sid[:8] if top_sid else "?",
        "top_session_cost": top_cost,
    }


def _anomaly_warning(records: list[dict]) -> str | None:
    """Return anomaly warning string or None."""
    a = detect_anomaly(records)
    if not a:
        return None
    return (
        f"{C.yellow('⚠️  Spend anomaly:')} {fmt_money(a['today_cost'])} today "
        f"vs daily avg {fmt_money(a['mean'])} "
        f"({a['multiplier']:.1f}x). "
        f"Top session: {a['top_session_id']}… ({fmt_money(a['top_session_cost'])})."
    )


# ─── Weekly report ─────────────────────────────────────────

def cmd_report(records: list[dict], cfg: dict):
    """Generate a weekly cost digest."""
    now = datetime.now(timezone.utc)

    # This week: Monday 00:00 → now
    monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    monday_ts = monday.timestamp() * 1000
    now_ts = now.timestamp() * 1000

    # Last week: previous Monday → this Monday
    last_monday = monday - timedelta(days=7)
    last_monday_ts = last_monday.timestamp() * 1000

    this_week = [r for r in records if r.get("timestamp") and monday_ts <= r["timestamp"] <= now_ts]
    last_week = [r for r in records if r.get("timestamp") and last_monday_ts <= r["timestamp"] < monday_ts]

    if not this_week:
        print(C.dim("\n📭 No activity this week yet.\n"))
        return

    this_cost = sum(r["cost_total"] for r in this_week)
    this_input = sum(r["input_tokens"] for r in this_week)
    this_output = sum(r["output_tokens"] for r in this_week)
    this_cache = sum(r["cache_read_tokens"] for r in this_week)
    this_sessions = len(set(r["session_id"] for r in this_week))

    last_cost = sum(r["cost_total"] for r in last_week)

    # Top project
    proj_costs: dict[str, float] = defaultdict(float)
    for r in this_week:
        proj_costs[project_name(r["cwd"], cfg)] += r["cost_total"]
    top_proj = max(proj_costs, key=proj_costs.get) if proj_costs else "?"
    top_proj_pct = proj_costs[top_proj] / this_cost * 100 if this_cost > 0 else 0

    # Most expensive session
    session_costs: dict[str, float] = defaultdict(float)
    session_models: dict[str, str] = {}
    for r in this_week:
        sid = r["session_id"]
        session_costs[sid] += r["cost_total"]
        session_models[sid] = r.get("model", "?")
    top_session_id = max(session_costs, key=session_costs.get) if session_costs else "?"
    top_session_cost = session_costs[top_session_id]

    # Day with most activity
    day_costs: dict[str, float] = defaultdict(float)
    for r in this_week:
        if r.get("timestamp"):
            day = datetime.fromtimestamp(r["timestamp"] / 1000).strftime("%m/%d")
            day_costs[day] += r["cost_total"]
    peak_day = max(day_costs, key=day_costs.get) if day_costs else "?"
    peak_cost = day_costs[peak_day]

    # Cache efficiency
    cache_rate = this_cache / (this_input + this_cache) * 100 if (this_input + this_cache) > 0 else 0

    # Print digest
    mon_str = monday.strftime("%m/%d")
    now_str = now.strftime("%m/%d")
    print(f"\n{C.bold('📬 Weekly Digest')}  {C.dim(f'{mon_str} → {now_str}')}")
    print(SEP)

    # Big number: total
    print(f"  {C.bold('Total:')}      {fmt_money(this_cost)}")
    if last_cost > 0:
        change = (this_cost / last_cost - 1) * 100
        arrow = "↑" if change > 0 else "↓"
        color = C.yellow if abs(change) > 30 else C.dim
        print(f"  {C.dim('vs last week:')} {color(f'{change:+.0f}% {arrow}')}  "
              f"({fmt_money(last_cost)} → {fmt_money(this_cost)})")
    print()

    # Stats row
    print(f"  {C.dim('Sessions:')}    {this_sessions}")
    print(f"  {C.dim('Tokens in:')}   {fmt_tokens(this_input)}  "
          f"{C.dim('out:')} {fmt_tokens(this_output)}")
    print(f"  {C.dim('Cache rate:')}  {cache_rate:.1f}% "
          + (C.green("✓ healthy") if cache_rate > 80 else C.yellow("⚠ low")))
    print()

    # Top project
    print(f"  {C.dim('Top project:')} {C.bold(top_proj)}  "
          f"{fmt_money(proj_costs[top_proj])} ({top_proj_pct:.0f}%)")
    print(f"  {C.dim('Peak day:')}    {peak_day}  {fmt_money(peak_cost)}")
    most_expensive_model = session_models.get(top_session_id, "?")
    print(f"  {C.dim('Priciest session:')} {top_session_id[:8]}… "
          f"{fmt_money(top_session_cost)}  ({most_expensive_model})")

    # Anomaly check
    anomaly = detect_anomaly(records)
    if anomaly:
        print(f"\n  {_anomaly_warning(records)}")
    else:
        print(f"\n  {C.dim('Spending pattern: normal.')}")

    # Tip
    insights_data = analyze(this_week, cfg)
    tips = [i for i in insights_data if C.YLW in i]
    if tips:
        print(f"\n  {C.bold('💡 Tip:')}")
        print(f"  {tips[0]}")
    elif insights_data:
        print(f"\n  {insights_data[0]}")

    print()


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
    elif cmd == "insights":
        cmd_insights(records, cfg)
    elif cmd in ("compare", "cmp"):
        cmd_compare(records, cfg)
    elif cmd in ("report", "weekly"):
        cmd_report(records, cfg)
    else:
        print(f"\n{C.yellow('Unknown command:')} {cmd}")
        print(f"Try {C.bold('python3 run.py help')}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
