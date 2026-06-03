# cc-cost

**不只是查账——让 Claude 自己学会省钱。**

*Not just tracking — your Claude learns to spend less.*

装完以后，Claude 每次看成本数据会自动反思、调整行为、记住教训。你不需要盯着仪表盘，Claude 自己会省。

```
/cc-cost

📊 Today — 2026-06-03
Project              Model                   Input   Output    Cache       Cost
🚀 my-saas            deepseek-v4-pro          380K     210K    32.4M      ¥1.82
📝 blog               claude-sonnet-4-6          42K      18K     5.1M      ¥0.68
────────────────────────────────────────────────────────────────────────
Total                                         422K     228K    37.5M      ¥2.50
💡 Cache hits: 37.5M tokens, saved ~¥110 (vs no cache)
```

Or weekly digest:

```
/cc-cost report

📬 Weekly Digest  06/02 → 06/08
────────────────────────────────────────
  Total:      ¥127.50
  vs last week: -15% ↓

  Sessions:   34  ·  Cache rate: 92% ✓
  Top project: 🚀 my-saas ¥89 (70%)
  Peak day:   06/05  ¥34.20

  ⚠️  Spend anomaly: 06/05 was 3x daily avg
  💡 Tip: switch to DeepSeek V3 for simple tasks → save ¥40/week
```

---

## Install

### Claude Code（推荐）

打开终端，粘贴这一行：

```bash
curl -fsSL https://raw.githubusercontent.com/Hedyzhang-Ading/cc-cost/main/install.sh | bash
```

或者在 Claude Code 里说：

> 请运行这条命令安装 cc-cost：  
> `curl -fsSL https://raw.githubusercontent.com/Hedyzhang-Ading/cc-cost/main/install.sh | bash`

装完直接用：

```
/cc-cost              # 今日用量
/cc-cost projects     # 全部项目排名
/cc-cost daily -d 7   # 7 天趋势
```

或者自然语言：

> "我这个月花了多少 token？"
> "哪个项目最烧钱？"
> "缓存命中率多少？"

### Codex

在 Codex 里说：

> Install https://github.com/Hedyzhang-Ading/cc-cost — git clone, then alias cc-cost='python3 ~/cc-cost/run.py'

然后 `cc-cost` 直接跑。

### Terminal

```bash
git clone https://github.com/Hedyzhang-Ading/cc-cost.git
python3 cc-cost/run.py

# 想更短：
echo 'alias ccc="python3 ~/cc-cost/run.py"' >> ~/.zshrc && source ~/.zshrc
ccc
```

Zero dependencies. Python >= 3.9 (macOS built-in).

---

## Commands

| Command | Shows |
|---------|-------|
| `today` (default) | Today by project + model |
| `projects` | All projects ranked by cost |
| `daily -d N` | Daily trend for N days |
| `report` | Weekly digest (vs last week) |
| `all` | One-paragraph overview |
| `insights` | Cost-saving tips |
| `compare` | Your price vs official |
| `config` | Pricing & aliases |

---

## Config (optional)

Create `~/.cc-cost-config.json`:

```json
{
  "monthly_budget": 500,
  "pricing": {
    "deepseek-v4-pro": {
      "input": 1.0,  "output": 2.0,
      "cache_read": 0.02,  "cache_write": 1.0
    }
  },
  "aliases": {
    "/Users/you/projects/my-saas": "🚀 My Project"
  }
}
```

- **monthly_budget**：月预算（元），超支自动预警
- **pricing**：你的渠道价格，用来跟官方价对比
- **aliases**：项目目录 → 可读名称Built-in comparison: Claude, DeepSeek, OpenAI, OpenRouter official prices.

---

## How

Reads `~/.claude/projects/*/<id>.jsonl` → extracts `usage` from assistant messages → aggregates by project/model/date.

Zero network. Zero telemetry. Zero deps.

---

## Roadmap

- [x] `/cc-cost` slash command for Claude Code
- [x] Token tracking by project
- [x] Daily trends + cache efficiency
- [ ] Codex native integration
- [ ] Auto daily log
- [ ] Local web dashboard
- [ ] Budget alerts

---

MIT
