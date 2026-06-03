---
name: cc-cost
description: |
  This skill should be used when the user asks about their Claude Code token usage,
  costs, spending, or bills. Trigger phrases include "花了多少","token 用量","cost",
  "账单","费用","spending","usage stats","今天花了","本周花了","哪个项目最烧钱",
  "cost breakdown","token tracking","缓存命中","cache hit" — any question about
  Claude Code usage or AI API costs.
argument-hint: [today|projects|daily|all|config] [-d N]
allowed-tools: [Bash]
---

# cc-cost — Claude Code Cost Tracker

Show the user their Claude Code token usage and costs at a glance.

## How to run

The skill is installed at `~/.claude/skills/cc-cost/`. Run:

```bash
python3 ~/.claude/skills/cc-cost/run.py $ARGUMENTS
```

If `$ARGUMENTS` is empty, default to `today`.

## Available commands

| Command | What it shows |
|---------|--------------|
| `today` (default) | Today's token usage by project + model |
| `projects` | All projects ranked by total cost |
| `daily -d N` | Daily cost trend for last N days |
| `all` | One-paragraph overview of all history |
| `insights` | Cost-saving optimization tips |
| `config` | Current pricing and project aliases |

## What to do

1. Run the command with whatever arguments the user provided (or `today` if none).
2. Display the output exactly as-is — the tool already formats it with colors and emoji.
3. If the output mentions "First time?", suggest the user run `/cc-cost config` to see pricing, and mention they can create `~/.cc-cost-config.json` to set custom pricing and project aliases.

## Important notes

- The tool reads Claude Code's local session data — no network requests, no API keys.
- It works automatically — no setup required for basic usage.
- Pricing defaults are built-in for Claude (Opus/Sonnet/Haiku) and DeepSeek (V3/R1/V4).
- If the user's provider or pricing differs, tell them to customize via `~/.cc-cost-config.json`.
