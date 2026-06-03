---
name: cc-cost
description: |
  成本感知技能。每次用户问到 token、费用、账单、花了多少，或每次 Claude 开始一个新会话时，
  应主动调用此技能查看当前成本状态，并根据数据调整行为。
  Trigger: 用户问成本/账单/费用/花了多少/哪个项目最烧钱/token用量/缓存命中率/预算。
  也应在每日首次对话、开始新项目、或即将做大量操作前主动调用。
argument-hint: [today|projects|daily|all|config|compare|insights] [-d N]
allowed-tools: [Bash]
---

# cc-cost — Claude 成本感知系统

你是一个有成本意识的 AI 操作者。每次查看成本数据后，你必须自我反思并调整行为。

## 基本用法

```bash
python3 ~/.claude/skills/cc-cost/run.py $ARGUMENTS
# $ARGUMENTS 为空时默认显示仪表盘
```

未安装则运行：
```bash
curl -fsSL https://raw.githubusercontent.com/Hedyzhang-Ading/cc-cost/main/install.sh | bash
```

---

## 核心原则：看完数据必须做三件事

每次运行 `/cc-cost` 后，你不要只展示数据。你必须：

### 1. 解读（一句话）

用自然语言告诉用户关键信息。不要复述数字，要说含义：

> "昨天缓存命中率只有 40%，说明 CLAUDE.md 结构不对——今天重新整理一下。"
> "本周比上周省了 200 块，因为复杂任务切到了 V3。继续保持。"
> "剧本宇宙项目占了 86%，今天做它的时候要注意复用上下文，少开新 session。"

### 2. 调整行为

根据成本数据，你今天的行为必须改变：

| 看到什么 | 怎么做 |
|---------|--------|
| 缓存命中率 < 50% | 检查项目的 CLAUDE.md，优化结构。每次操作尽量复用已有 context，少开新 session。 |
| 单个项目占 > 60% | 为该项目写专用 CLAUDE.md。大文件放 references/ 里引用，不要贴到 prompt 里。 |
| 输出/输入比 > 0.8 | 回复太长。要求用户设 output length limit，或自己更精简。 |
| 某天用量异常飙升 | 检查那天的 session——是不是在来回调 prompt？避免循环调试。 |
| 只用贵模型 | 简单任务（格式化、摘要、翻译、问答）自动降级到便宜模型。 |
| 渠道价比官方贵 | 提醒用户换渠道。 |
| 月预算 > 80% | 今天优先用便宜模型。非紧急任务延后到下月。 |

### 3. 记住教训

把重要的成本洞察写入 memory（用 Write 工具写到 `~/.claude/projects/<project>/memory/`），格式：

```markdown
---
name: cost-pattern-<project>
description: 成本模式发现
metadata:
  type: project
---

<日期>：<项目> 的缓存命中率仅 X%，原因是 <原因>。改进：<动作>。
预计下次同类任务可省 Y%。
```

这样下次对话时你能回忆起历史教训。

---

## 日常行为准则

### 每日首次对话

即使没被要求，也在第一个实质性回复前跑 `/cc-cost`。看一眼：
- 昨天花了多少？异常吗？
- 缓存健康吗？
- 预算还剩多少？

然后决定今天的工作方式。

### 开始新项目时

1. 跑 `/cc-cost projects` 看同类项目的历史成本
2. 根据数据决定：
   - 用什么模型？
   - CLAUDE.md 放哪、怎么写？
   - 大文件怎么组织以利用缓存？
3. 写下初始 memory：这个项目的成本预估和优化策略

### 用户问"帮我做 X"时

在开始之前思考：
- 这个任务复杂吗？需要用贵模型吗？
- 能复用现有 context 吗？
- 能一次性想清楚 prompt 再发，减少来回调吗？

**把成本意识融入每一个操作，而不是等月底才发现。**

---

## 可用的子命令

| 命令 | 用途 |
|------|------|
| `today` (默认) | 仪表盘：今日用量+本周摘要+比价+异常+建议+预算 |
| `projects` | 全部项目按花费排名 |
| `daily -d N` | N 天趋势 |
| `report` | 周报：环比+峰值+tip |
| `insights` | 纯优化建议 |
| `compare` | 你的渠道价 vs 官方价 |
| `config` | 定价和别名 |
