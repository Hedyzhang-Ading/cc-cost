# cc-cost

**在 Claude Code 里一句话看光 token 消耗。不离开对话。**

*See where your tokens go — without leaving your conversation.*

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

---

## Install

### Claude Code

在 Claude Code 里粘贴这句话：

> 请帮我安装这个插件：https://github.com/Hedyzhang-Ading/cc-cost
> 把仓库 clone 到 ~/.claude/skills/cc-cost/ 目录。

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
| `all` | One-paragraph overview |
| `config` | Pricing & aliases |

---

## Config (optional)

Create `~/.cc-cost-config.json`:

```json
{
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

Built-in pricing: Claude Opus/Sonnet/Haiku, DeepSeek V3/R1/V4.

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
