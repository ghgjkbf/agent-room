# 第 3 步设计：MCP 接入网关（外部 Agent 进群）

日期：2026-08-27 · 状态：已确认，待实现

## 同类项目参考（ClawSwarm，2026-08-27 调研）

[1Panel-dev/ClawSwarm](https://github.com/1Panel-dev/ClawSwarm)：开源多 Agent 群聊协作编排系统（FastAPI + Vue3 + OpenClaw channel 插件），定位与本项目高度重合（Agent 互聊群聊 + 服务端调度）。架构对照结论：

- **同构点印证设计**：scheduler-server（FastAPI 消息/群组/调度 API）≈ 我们的 sidecar；channel 插件（外部 Agent 侧接入件）≈ 我们的 MCP 网关工具集；WS 通知 + HTTP 增量拉取的消息链路 ≈ 我们的 WS 广播 + poll_messages 游标。多 Agent 群聊「服务端权威事件流 + 客户端拉取/推送」的路线相互印证。
- **差异点（不跟随）**：ClawSwarm 面向服务器 Docker 部署、Agent 实例经 OpenClaw 插件承载；本项目定位本机桌面程序（Tauri sidecar）、外部 Agent 经 MCP 直连，无需插件层与容器。
- **已吸收（2 项）**：
  1. **群规写进 join_room 返回值**——Agent 进群即收到房间使用约定（何时 poll_messages、deliver 用法、P0 interrupt 语义、@提及规则），类似其 cs-chat 技能文档随插件分发的思路；
  2. **client_msg_id 幂等去重**——send_message 增加可选 client_msg_id，服务端按 (agent_id, client_msg_id) 去重，挡外部客户端重试导致的重复刷屏。
- **V2 备忘（不在本步做）**：ClawSwarm 的群组/成员关系表（chat_groups + chat_group_members）是多房间模型的基础；本项目 MVP 单房间直接用 agents.room_id，多房间需求出现时再引入 membership 关系表。

## 背景与目标

原设计文档第 12 章将「文件工作区」列为第 3 步、MCP 网关列为第 5 步。2026-08-27 讨论确认：本产品的核心定位是**让本机两个以上 Agent（TRAE / ZCode / 内置 LLM Agent）经此平台交流协作**，因此将 **MCP 接入网关提前为第 3 步**，文件工作区顺延为第 4 步。

本步目标：外部 Agent（TRAE / ZCode）成为房间一等公民成员——前端建成员发 ROOM_TOKEN、外部 Agent 经 MCP 工具进群、发言/交付入事件流、群内成员可见其在线状态。验收标准：真实外部 Agent（先 ZCode，后 TRAE）进群完成一次收发。

## 已确认的关键决策

| 决策点 | 结论 |
|---|---|
| 路线调整 | MCP 网关提前为第 3 步，文件工作区顺延为第 4 步 |
| MCP 承载方式 | 官方 SDK FastMCP + streamable-http，挂载到现有 FastAPI 同端口 `/mcp`（127.0.0.1:8899），不起独立进程 |
| 外部成员产生 | 前端「添加外部成员」建员发 token（人来发牌），ROOM_TOKEN 按 Agent 单独发放、可吊销重发 |
| 联调顺序 | 先 ZCode（本会话可自动化实测）后 TRAE（用户手动添加同地址） |
| 消息收发语义 | 外部 Agent 仅主动发言 + 被 @ 时由内置 Agent 应答；外部发言默认不触发内置 Agent 自动回复（防客套死循环） |
| 工具范围 | 四件套最小集：join_room / poll_messages / send_message / declare_status；fs_*、claim_subtask 等留待文件区/编排步 |
| 轮数熔断 | 仅作用于内置 Agent；外部成员不受限（节奏由各自客户端驱动） |
| P0 interrupt | 对外部语义：广播 priority=0 system 消息，外部 Agent 下次 poll_messages 读到后停止动作 |
| 身份卡 | 同一身份卡可同时绑内置与外部实例（如「开发员」卡既有 Agent A 又有 TRAE） |

## 数据模型（增量迁移，沿用现有 init_db 模式）

- `agents` 表补列 `api_token_hash TEXT`（ROOM_TOKEN 的 SHA-256，创建时一次性明文展示，事后可重发使旧 token 立即失效）
- `messages` 表补列 `client_msg_id TEXT`（外部消息幂等键；同 (sender_id, client_msg_id) 重复提交直接返回已有消息，不落库不扇出）
- `kind` 已有 `external` 值可复用；`status` 承担在线/离线标记
- 新增 `agent_tokens` 审计表（可选 V2，本步先用 agents.api_token_hash + 事件流审计）

## 后端新模块 `backend/app/mcp_gateway/`

### server.py
- 官方 SDK `FastMCP` 构造 MCP Server，streamable-http 方式挂载到现有 FastAPI 的 `/mcp`（同端口 8899）
- 新增依赖：`mcp>=1.9`（当前 PyPI 2.1.1，dry-run 与 FastAPI 0.141 / Python 3.14 兼容，会带入 sse-starlette 等）

### tools.py — 四件套最小工具集
每次调用携带 `(agent_id, token)` 双因子校验（无会话状态，吊销即时生效）；失败返回结构化错误（MCP isError 约定），不抛栈泄漏。

| 工具 | 语义 |
|---|---|
| `join_room(room_id)` | 报到进群；校验通过 status=online，广播「X 进群」system 消息；**返回值附房间使用约定**（poll 时机、deliver 用法、P0 语义、@提及规则） |
| `poll_messages(cursor, limit=50)` | 按 messages.id 游标拉增量（流式分片不落库，拉到的均为完整消息，自带 sender/type/mentions） |
| `send_message(text, mentions=[], type="chat"\|"deliver", client_msg_id=可选)` | 经 bus.publish 落库扇出，内置 Agent 与人类均可见；**按 (agent_id, client_msg_id) 幂等去重**，重复提交返回首次结果 |
| `declare_status(status)` | 上报在线/离线 |

### stdiobridge.py
TRAE 兼容薄桥：`mcp_stdio.py` 独立入口，stdio ↔ HTTP 透传到 `/mcp`，供仅支持命令行接入的客户端（设计文档 14.2 TRAE 一侧形态）。

### 身份映射与权限
- 外部实例绑定身份卡（前端可随时换绑），群内标签与内置 Agent 一致
- 白名单与 fs_scope 网关侧强制校验属第 5 步（文件区落地后），本步工具集内无文件工具，无越权面
- 外部 Agent 默认不授予 shell.run（设计文档安全红线，本步未开放任何 shell 工具）

## 防死循环规则（对应设计文档风险表第一行）

外部发言默认不触发内置 Agent 自动回复——`plan_replies` 仅当显式 @ 到某内置 Agent 时才唤起它；避免「客套互捧」循环。轮数熔断对外部成员不生效。

## 前端（左栏「成员」Tab 增强）

- 「+ 添加外部成员」弹窗：填名称 + 选身份卡 → 创建记录；弹窗一次性展示 ROOM_TOKEN + 两段现成接入配置（ZCode 的 `.zcode/config.json` url 片段、TRAE 的 stdio 命令片段），一键复制
- 成员列表加「内置/外部」徽标与外部成员在线状态点；「复制令牌」按钮支持事后重发（旧 token 立即失效）

## 错误处理

- 错误 token / 未注册成员 → 结构化错误返回，不抛栈泄漏
- 越权尝试（用 A 的 token 冒充 B）照常入事件流审计（sender_kind 标记来源），满足「可追责」

## 验收方案（三层递进）

1. **pytest 协议单测**：token 校验、冒名拒绝、游标增量正确性、deliver 消息入流
2. **模拟外部端到端**：起后端后用 SDK ClientSession 当「假 TRAE」走完 join → poll → send 全链路
3. **GUI 双通道验证**：
   - Playwright（可见 Chromium）访问 127.0.0.1:8899 截图验证：添加成员弹窗、token 展示、外部成员气泡、徽标渲染
   - 网关注册进 `.zcode/config.json`，ZCode 本人作为第一个真实外部成员进群实测收发（最硬验收）
   - 用户手动在 TRAE 界面添加同一地址，完成「先 ZCode 后 TRAE」闭环

## 明确不做（YAGNI）

- 文件工作区（fs_read/fs_write 工具、文件树面板、上传预览）→ 顺延第 4 步
- 桥接守护进程 room-bridge（无人值守自动接活）→ 设计文档 V2 场景
- HTTP API 接入模式（SSE/长轮询）→ 本步只做 MCP 网关
- claim_subtask / report_receipt（排产单相关）→ 第 5 步编排闭环
- memory.query → 向量记忆步
