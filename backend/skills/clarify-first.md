---
name: clarify-first
description: "Proactive task clarification. Use when the user assigns a task that is vague, ambiguous, or missing key details (goal, scope, inputs/outputs, constraints, acceptance criteria, paths, target platform) — BEFORE starting any analysis-heavy or implementation work. During task analysis, whenever uncertainty arises that cannot be resolved by reading files/code/config yourself, stop and ask the user targeted questions instead of guessing. Trigger phrases: 布置任务、模糊需求、帮我做、写一个、优化一下、改一下 with unclear specifics, or any task where you notice yourself about to guess. Do NOT use for trivial unambiguous operations (read a file, run a command, answer a question)."
---

# clarify-first — 任务受理先澄清

**核心原则：不确定就问，不靠猜。** 猜错方向返工的代价比问一句话高一个数量级。

## 触发时机

- 用户布置了任务，但缺少目标、范围、输入输出、约束、验收标准中的至少一项
- 分析任务的途中冒出"这里它到底指什么？"的疑问，且**无法通过自己查文件/代码/配置解决**
- 你发现自己正准备基于假设动手 → 停，先问

**不触发**：任务含义明确的小操作（读文件、跑命令、纯问答）；能通过查仓库/记忆自己消除的不确定（先查，查不到再问）。

## 工作流

### 第 1 步：静默分析，列出不确定点

拿到任务后先自己分析一遍，产出四个要素的清单：

| 要素 | 问自己 |
|------|--------|
| 目标 | 任务完成后什么样的状态算"成功"？ |
| 范围 | 动哪些东西，明确不碰哪些？ |
| 线索 | 输入在哪、输出到哪、依赖什么环境/工具？ |
| 验收 | 用户会怎么检查结果？ |

把**答案未知且查不到**的项按影响排序。影响小的自己定默认值并在结果里说明；影响大的进入第 2 步。

### 第 2 步：主动提问，一次问全

- 优先使用 ZCode 内置 `AskUserQuestion` 工具提问（结构化选项 + Other 自由输入，用户点选即可），最多 **4 个问题**；每个问题给出你推荐的选项（放第一个并标注"推荐"）。
- 工具不可用或问题需要长描述时，用文字提问：编号列出，每问附上"为什么需要这个信息"。
- **禁止**分多轮挤牙膏式提问——一轮问全，问完就干活。
- **必答问题未得到回答、或用户未同意按你声明的假设继续之前，不开始实现**——提前动手 = 把提问省下的时间赔进返工。

```text
好问题 vs 坏问题：
✅ "目标是让现有脚本提速，还是重写成更稳的版本？"（二选一，直指方案分叉点）
❌ "你想要什么样的效果？"（开放式，把分析工作推回给用户）
✅ "输出放 D:\ai-use\output 还是项目目录下？"（具体到可点选）
❌ "放哪里？"（上下文都没有）
```

### 第 3 步：复述确认，闭环

拿到回答后用一两句复述理解："明确了：目标是 X，范围限 Y，输出到 Z。"用户未纠正即视为确认，随后直接进入执行，不再反复确认。

### 第 4 步：链式移交（按任务类型）

澄清完成后，若任务属于以下类型，移交给对应技能继续：

| 任务性质 | 移交 |
|----------|------|
| 创造性/新功能/设计类，需要探索方案 | `brainstorming` |
| 方案有风险，需要压力测试决策 | `grilling` |
| 需要选技术栈/找现成方案 | `search-first` |
| 依赖本机程序/仓库位置 | `tool-location-confirm` |
| 普通实现任务 | 直接做（编码时遵守 `auto_skill_first.md` 黄金链） |

## 边界

- 提问不是免责：能查到的（文件内容、配置、历史记忆）自己查，只把**真正需要用户决策**的问题抛出去
- 用户已明确说"别问，直接做"时跳过本技能，把假设写进最终报告
- 一次任务只走一轮澄清；执行中若出现**改变方案走向**的新疑问，才允许追加提问

## 假设兜底（用户不回应时）

提问后用户未回答，或用户明确表示"你看着办"时：

1. 把每个不确定点改写为**显式假设**，注明依据（"假设输出为 Markdown，因为你日常文档都用它"）
2. 按风险分层处理：**低风险假设**直接按假设执行；**高风险假设**（不可逆操作、删改数据、外部发布、大方向选择）必须等到答复，不得默认推进
3. 假设清单写进最终报告的"本次假设"小节，方便用户事后纠偏

原则：**宁愿显式地猜，不要隐式地猜**——隐式猜测错了没人发现，显式假设错了能被一行纠正。
