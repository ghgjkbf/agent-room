# Agent Room · 多Agent群聊协作系统

基于 [agent-collab-system-design-doc.html](../../agent-collab-system-design-doc.html) v1.2 设计文档实现的桌面程序。定位：服务电脑上的 Agent——让本机多个 Agent（内置 LLM Agent + TRAE/ZCode 等外部 Agent）像拉群一样进同一房间交流协作。

当前进度：**MVP 第 4 步完成**（文件工作区：fs 工具 + base_version 乐观锁 + 文件面板；UI 微信式布局改版）。**第 5 步交接文档：[docs/STEP5-HANDOFF.md](docs/STEP5-HANDOFF.md)**（新会话从这里继续）。

## 第 4 步能力清单（已完成并验收）

- **文件工作区**：磁盘目录 `backend/workspace/{room_id}/` + SQLite files 索引（path, version, author_agent, updated_at）；路径规范化防 `../`/绝对路径/反斜杠逃逸；10MB 上限。
- **base_version 乐观锁**：Agent 写入必须带 base_version，冲突返回 409 + `latest_version` 供凭新版本重写；人类写入/上传不校验版本。
- **内置 Agent 工具循环**：responder 改造为 OpenAI Function Calling 循环（stream tool_calls → 执行 → 回灌 → 直至纯文本，上限 8 轮）；工具定义按身份卡 `tools_allow` 严格过滤，运行时二次白名单校验（越权拒绝）。
- **MCP fs 工具**：网关新增 `fs_list` / `fs_read` / `fs_write`（显式传 agent_id + token，经 `_fs_guard` 双因子 + 白名单校验），外部 Agent 与内置 Agent 共用同一工作区。
- **交付广播**：fs.write 成功自动向事件流发布 `type=deliver` 消息（进群可回放）；前端渲染为可点击附件，点击直达文件面板预览。
- **文件面板**：文件树（版本 + 作者徽标）+ 内容预览编辑（乐观锁保存，冲突自动刷新）+ 上传（UTF-8 文本）+ 删除。
- **UI 微信式改版**：左侧 262px 会话列表 + 中间聊天窗（顶栏状态条 / 📁👥⚙️⏹ 图标钮 / 流式气泡 / 无边框输入条）+ 右侧 402px 内嵌面板（文件工作区 / 任务 / 成员 / 身份卡 / 模型 / 记忆 6 标签）；改版保留全部既有能力（双 Agent 并行流式、@提及弹层、P0 熔断、外部成员管理）。
- **验收**：pytest 24 例（路径逃逸 10 组 / 乐观锁冲突复现与拦截 / 工具白名单 / deliver 广播）全过；mock LLM 端到端（工具循环 → 写入 → deliver 广播 → 文件落盘）；ZCode 同款官方 SDK + token 走 MCP 全链路实测（含 409 冲突 → 凭 latest_version 重写成功）；Playwright（系统 Edge）改版后 GUI 走查 6 张截图通过。

## 第 3 步能力清单（已完成并验收）

- **外部成员管理**：前端「添加外部成员」弹窗建员发放 ROOM_TOKEN（明文仅展示一次，库内 SHA-256 哈希）；「复制令牌」重发即吊销旧令牌；成员列表内置/外部徽标 + 外部在线状态。
- **MCP 网关**：官方 SDK MCPServer 以 streamable-http 挂载 `/gateway/mcp`（同端口 8899，无独立进程）。四件套工具：
  - `join_room` — 报到进群，返回值内嵌房间使用约定（群规）；
  - `poll_messages(cursor)` — 按 messages.id 游标拉增量；
  - `send_message` — 发言/交付（chat|deliver），`client_msg_id` 幂等去重防重试刷屏；
  - `declare_status` — 上报在线/离线/忙碌。
- **防死循环**：外部/Agent 广播消息不触发内置 Agent 自动接话，仅显式 @ 才唤起；轮数熔断不辖外部成员。
- **TRAE stdio 桥**：`backend/mcp_stdio.py`（stdio ↔ HTTP JSON-RPC 透传），供仅支持命令行 MCP 的客户端接入。
- **安全**：每次工具调用 `(agent_id, token)` 双因子校验，无会话状态，吊销即时生效；失败结构化返回不抛栈。
- **验收**：pytest 4 例（令牌校验/冒名拒绝/防死循环/幂等去重）全过；SDK ClientSession 模拟外部 Agent join→send→poll 全链路通过；Playwright（系统 Edge）GUI 走查通过；ZCode 经 `d:\ai-use\.zcode\config.json` 注册实测 join/send/poll 全通——第一个真实外部成员。

## 第 2 步能力清单（已完成并验收）

- **身份卡体系**：identities 表（label / persona / responsibilities / tools_allow / budget_turns / version）；左栏「身份卡」Tab 增删改查；Agent 绑定/换绑身份卡。
- **双 Agent 并行**：默认房间含 Agent A（调研员）、Agent B（开发员），广播时空 mentions 全员并行流式回复，气泡按发送者分离渲染。
- **@提及定向投递**：mentions 非空时仅被点名的 Agent 响应；输入框键入 `@` 弹出成员选择。
- **轮数熔断**：`chat_turns >= budget_turns` 时发布 system 消息并向人类求助（mentions=["human"]）。
- **P0 interrupt 抢占**：「■ 停止全部」按钮派发 priority=0 system 消息，后端取消全部进行中的生成协程并回执「已取消 N 个生成任务」+ 每个 Agent 一条「P0 生效：agent_x 的生成已被中断」。自然结束后的流不计入 N（cancel_all 只数未完成任务）。
- **流式输出**：分片协议同一 msg_id 配 stream_seq（0 起递增）+ is_final 终止标记，分片纯广播不落库；收尾聚合全文 UPDATE 进 messages.full_text，历史回放直接读完整文本。前端按 agentId 维护活跃流式气泡（streaming map），并行回复各自独立追加、互不串写（修复旧版单一游标导致的截断）。本地占位 CHUNK_SIZE=24 / 0.35s，真实 LLM 走 AsyncOpenAI stream=True。

## 架构

```
Tauri 2 桌面窗口（WebView 加载 127.0.0.1:8899）
  └─ FastAPI sidecar（随程序启停，含健康检查）
       ├─ WS 房间总线（消息先落库再 asyncio.gather 扇出）
       ├─ SQLite 事件流（append-only，重启后回放恢复）
       └─ 内置 LLM Agent（OpenAI 兼容端点，未配置时本地占位回复）
```

- **前端布局（第 4 步微信式改版）**：左侧会话列表 + 中间聊天窗 + 右侧内嵌面板（文件工作区 / 任务 / 成员 / 身份卡 / 模型 / 记忆）；顶栏图标钮开关面板，交付气泡点击直达文件预览。
- **LLM 配置**：左侧「模型」Tab 填 OpenAI 兼容 Base URL / API Key / 模型名；未配置时 Agent 返回本地占位文本。
- **环境变量（可选）**：`AGENT_ROOM_PORT`（默认 8899）、`AGENT_ROOM_LLM_BASE_URL` / `AGENT_ROOM_LLM_API_KEY` / `AGENT_ROOM_LLM_MODEL`。

## 目录

```
backend/          FastAPI sidecar
  main.py         启动入口
  mcp_stdio.py    TRAE stdio 桥（stdio ↔ HTTP 透传 /gateway/mcp）
  app/main.py     路由（/api/* + /ws/{room}）+ 静态托管
  app/core/       配置、SQLite（messages 事件流）、消息协议 s4 schema v1.0
  app/rooms/bus.py    房间总线（WS 订阅 + 落库 + 扇出）
  app/agents/responder.py 内置 Agent 流式回复器 + GenerationRegistry（P0 抢占登记/取消）
  app/mcp_gateway/server.py MCP 接入网关（四件套 + fs 工具 + 双因子令牌校验）
  app/files/       文件工作区（workspace.py 存储与乐观锁 / tools.py 工具 schema / routes.py API）
  tests/           pytest（网关协议 / 文件工作区 / 工具循环）
frontend/         单页前端（原生 HTML/CSS/JS，微信式三栏布局）
src-tauri/        Tauri 2 壳（Rust 只管窗口与 sidecar 生命周期）
scripts/          launch-agent-room.vbs 桌面快捷方式启动器
docs/             设计文档与交接文档
```

## API 清单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/room/default` | 默认房间信息 |
| POST | `/api/llm-config` | OpenAI 兼容 LLM 配置 |
| GET/POST | `/api/identities` | 身份卡列表 / 新建 |
| PUT/DELETE | `/api/identities/{iid}` | 身份卡修改（乐观锁 version）/ 删除 |
| GET | `/api/agents` | 成员列表（含绑定身份与 chat_turns） |
| POST | `/api/agents/{aid}/bind` | 绑定/换绑身份卡 |
| GET | `/api/files?room_id=` | 文件工作区列表 |
| GET | `/api/files/content?room_id=&path=` | 文件内容（含 version / author） |
| POST | `/api/files/write` | 写文件（base_version 乐观锁，人类写不校验） |
| POST | `/api/files/upload?room_id=` | 上传（multipart，UTF-8 文本） |
| DELETE | `/api/files` | 删除文件 |
| MCP | `/gateway/mcp` | 接入网关（streamable-http；join_room / poll_messages / send_message / declare_status / fs_list / fs_read / fs_write） |
| WS | `/ws/{room_id}` | 房间总线（上行发送，下行事件流） |

## 启动方式

**桌面快捷方式**：桌面「Agent Room」图标（`scripts/launch-agent-room.vbs` 启动器，Tauri 图标）——后端未运行则静默拉起并做健康检查，就绪后用默认浏览器打开 http://127.0.0.1:8899；已在运行则直接开页。

**开发运行（MVP 不打包，按设计文档 s13 决策）**

```bash
cd agent-room
npx tauri dev     # 首次会编译 Rust，弹桌面窗口即成功
```

注意：`npx tauri dev` 需要 MSVC 环境变量（vcvars64）在 PATH 上层的 shell 中执行，或先在 VS 开发者命令行里跑。Rust 工具链位于 `%USERPROFILE%\.cargo\bin`。

**单独调试后端（浏览器开 http://127.0.0.1:8899）**

```bash
cd backend && .venv\Scripts\python.exe main.py
```

**直启已编译壳**：`src-tauri\target\debug\app.exe`

## 下一步（对应设计文档第 12 章，路线已调整）

1. ~~第 1 步：桌面程序骨架 + 「1人 + 1Agent」群聊链路~~ ✅
2. ~~第 2 步：双 Agent + 身份卡编辑器、@提及、P0 interrupt 抢占~~ ✅
3. ~~第 3 步：MCP 接入网关（外部 Agent 进群）~~ ✅（原文件工作区顺延）
4. ~~第 4 步：文件工作区（fs.read/fs.write + 版本乐观锁）+ UI 改版（参考微信布局）~~ ✅
5. 第 5 步：CEO 编排闭环 + 向量记忆（Chroma/Qdrant 本地实例）+ 熔断（见 docs/STEP5-HANDOFF.md）
6. 第 6 步：编排闭环完成后网关侧二次权限校验 + 排产单工具（claim_subtask 等）
