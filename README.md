# cc-cost

**One command to see where your Claude Code tokens go.**

一行命令，看光 Claude Code 的 token 消耗和费用。

```
$ cc-cost today

📊 Today — 2026-06-03
────────────────────────────────────────────────────────────────────────
Project              Model                   Input   Output    Cache       Cost
────────────────────────────────────────────────────────────────────────
🏠 home               deepseek-v4-pro          637K     338K    57.7M      ¥2.47
剧本宇宙                deepseek-v4-pro           75K      90K    25.5M     ¥0.76
皮球侠                  deepseek-v4-pro            1K       4K     3.3M     ¥0.08
────────────────────────────────────────────────────────────────────────
Total                                         722K     437K    89.0M      ¥3.38

💡 Cache hits: 89.0M tokens, saved ~¥87.19
```

---

## Why?

If you use Claude Code heavily, you know the feeling: the monthly bill arrives and you have no idea where it went. Which project burned the most? Was that prompt-tuning session worth it? Did the cache actually help?

`cc-cost` answers all of this in one command. **No network requests. Your data stays local.**

---

## 为什么？

重度使用 Claude Code 的人都知道这种感觉：月底账单来了，钱花哪了完全不知道。哪个项目最烧钱？调 prompt 那次浪费了没有？缓存到底有没有用？

`cc-cost` 一行命令全回答。**不做网络请求，数据只在你本机。**

---

## Install

```bash
pip install git+https://github.com/ai-operator/cc-cost.git
```

Or from source:

```bash
git clone https://github.com/ai-operator/cc-cost.git
cd cc-cost
pip install -e .
```

Requires Python >= 3.9. Zero dependencies beyond the standard library.

---

## Usage

```bash
cc-cost              # Today's summary (default)
cc-cost today        # Today by project + model
cc-cost projects     # All projects ranked by cost
cc-cost daily -d 7   # Daily trend (last 7 days)
cc-cost daily -d 30  # Daily trend (last 30 days)
cc-cost all          # One-paragraph overview
cc-cost config       # Show current pricing & aliases
```

---

## Configuration

Optional: create `~/.cc-cost-config.json` to customize pricing and project names.

```json
{
  "pricing": {
    "deepseek-v4-pro": {
      "input": 1.0,
      "output": 2.0,
      "cache_read": 0.02,
      "cache_write": 1.0
    }
  },
  "aliases": {
    "/Users/you/projects/my-saas": "🚀 My SaaS",
    "/Users/you/projects/blog": "📝 Blog"
  }
}
```

- **pricing**: CNY per 1M tokens. Match your actual provider pricing.
- **aliases**: Map working directories to readable project names.

Built-in pricing covers Claude Opus/Sonnet/Haiku and DeepSeek V3/R1/V4.

---

## How it works

`cc-cost` parses Claude Code's local session files (`~/.claude/projects/*/<session-id>.jsonl`), extracts `usage` blocks from every assistant message, and aggregates by project, model, and date.

No API keys. No cloud. No telemetry. **Pure local data.**

---

## Roadmap

- [x] Token cost tracking by project
- [x] Daily cost trends
- [x] Cache hit efficiency
- [ ] Auto daily log generation (what did I do today?)
- [ ] Local web dashboard
- [ ] Cursor / Windsurf support
- [ ] Budget alerts

---

## Keywords

`claude-code` `token-tracker` `ai-cost` `ai-operator` `cost-tracking` `deepseek`

---

## License

MIT © AI Operator
