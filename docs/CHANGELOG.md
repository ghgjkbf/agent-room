# Changelog · 能力清单（按迭代）

## 第 8 轮：深色「指挥室」重设计 + 消息编号/星标/软删（v0.9.0）

- **深色 Ops Console 界面重设计**：近黑炭底（--bg #0d0f12）+ 琥珀 #f0a63c 人类操作主色 + teal #3ecfb2 系统侧；等宽字体呈现状态数据；右侧改竖向图标栏 + 面板体两段式；CSS 全内联；功能与后端对接点 100% 保留
- **i18n 机制重写**：data-i18n 三类标注（文本/placeholder/title）+ 语义词典 STR（221 条）+ 整串反查 i18t；切 en 全站无中文残留（静态 + 动态 + confirm + 状态 chips + 帮助面板整块互换），zh 往返还原、刷新语言保持
- **消息编号**：对话气泡（人类/Agent/编排/交付）位置序号 #n，删除/归档后自动连续重排；system 不编号
- **跳转定位**：左栏跳转框输入 #37 回车 → 滚动居中 + 琥珀描边闪烁 2 秒；越界双语提示
- **消息星标**：hover ☆/★ 切换，标过的琥珀描边 + 角标；落库 messages.starred；**星标消息豁免归档**（正文永久保留）；乐观切换失败自动回滚
- **单条消息软删**：hover ✕ 删除，复用 P0 的 invalidated=1 机制——对界面与 Agent 网关立即隐身，库内留审计痕迹；编号自动补位
- **chat.delete 治理工具**（Agent 侧定向删除）：内置 Agent function calling 与 MCP 网关（chat_delete）双暴露，按界面 #n 序号批量软删（seqs 参数），群管家 B 出厂白名单默认含；删除后向群里发系统回执
- **稳定性**：修复气泡点击塌缩（波纹 .fx 的 overflow:hidden 使 flex 子项 min-height 归零，被长消息流挤压成一条；加 flex-shrink:0 根治）；按用户决策移除长气泡折叠功能
- 验收：pytest 54 例全过；浏览器逐面板走查（en 无中文残留 / 编号连续性 / 删除重排 / 星标持久化 / 跳转闪烁 / 双语往返）全绿

---

## 第 7 轮：能力工具层 + 双 Agent 岗位化（v0.8.0）

- **内置 Agent 白板终结**：能力工具 shell.run（电脑控制）/ browser.open（网页读取）/ doc.read（文档转 Markdown）/ skills.write（Agent 自建技能）/ chat.archive（主动归档），全部白名单门控
- **出厂身份卡**：管家·出厂（B）/ 服务·出厂（A）默认绑定，白名单条件升级机制；岗位手册（agent_md）与身份卡共存注入
- **A/B 岗位手册**：职责清单按优先级 + 场景应对表 + 决策优先级链 + 行为红线 + dispatch 执行守则；B 增越权监管（越权事件群内可见并 @B 通报）
- **技能库扩容**：从本机技能库一键导入 SKILL.md（ZCode 39 + TRAE 3）；Agent 可经 skills.write 自建技能
- **界面**：中文/English 切换、聊天背景与透明度、点击动效、工作区文件引用（消息/任务下达均带附件清单）；（长消息折叠已在 v0.9.0 移除）
- **管理**：向量记忆单条删除/清空公共记忆、已结束任务单条删除/一键清空、手动归档清理按钮
- 验收：pytest 54 例全过；各能力真机验证（工具执行 / 导入 42 技能 / 归档 34 条 / 任务清理）

---


本文件收录各迭代的能力与验收记录；面向使用者的功能总览见 [README](README.md)。

当前进度：**MVP 第 5 步完成**（CEO 编排闭环 + 向量记忆 + 任务级熔断）；第 6 步增强：API 连通性校验、Agent 专属规范 md、内部技能库（含 .md 文件导入导出）、多群聊（新建/切换）；优化迭代：验收真实性核验、list_rooms、一键白名单、任务详情、全房间归档。

## 优化迭代能力清单（验收真实性 + 体验补全）

- **验收真实性核验**：交付文本中声称的文件路径自动提取并核对工作区（`extract_claimed_paths` + `_verify_claims`），核验结果注入验收员提示词；真实 LLM 模式下「声称的交付文件全部不存在」时无视验收员直接打回（堵住幻觉交付骗过验收的漏洞；占位模式不启用防自锁）。
- **验收结论落库**：subtasks 新增 `last_receipt`（最近一次验收/打回原因），任务面板每个子任务显示交付摘要与验收结论。
- **网关 `list_rooms` 工具**：外部 Agent 自查所在房间（仅返回自己被拉入的）。
- **身份卡一键白名单**：「⚡ 一键：文件+技能」快捷勾选 fs.* + skills.*（工具复选框初始即渲染）。
- **janitor 按房间遍历**：归档清理覆盖全部群聊。
- **验收**：pytest 47 例全过（+路径提取 / 工作区核验含被骗验收员场景 / list_rooms 隔离）；真机 e2e（SDK 调 list_rooms 只见所在房间 + 占位闭环 last_receipt 落库）；GUI 走查通过。

## 第 6 步增强能力清单（已完成并验收）

- **API 连通性校验**：「模型」面板保存后自动向端点发一条最小对话请求（`POST /api/llm-test`，20s 超时、零重试），显示延迟 / 端点回复 / 错误详情；LLM 配置改为落本机 kv 表（重启不丢）。
- **Agent 专属规范 md**：`backend/agent_md/agent_a.md`、`agent_b.md`（角色定位 / 职责边界 / 行为规范 / 输出要求，借鉴 agent-md 结构），未绑定身份卡时全文注入 system prompt（mtime 缓存，改文件即时生效）；绑定身份卡后以身份卡为准。
- **内部技能库**：`backend/skills/*.md`（技能 = 写法规范 / 模板 / 工作流文档）；前端「技能」面板增删；`skills.list` / `skills.read` 工具进入身份卡白名单选项，内置 Agent 与外部 Agent（MCP 网关同名工具）均可按白名单使用；内置两个示例技能（群公告写作、会议纪要模板）。
- **多群聊**：`room_members` 成员归属关系表（agents 表保留为全局注册表，删除成员同步清理）；「＋新建群聊」选择成员创建（外部成员也可拉入），每个群独立的消息流 / 文件工作区 / 任务 / 记忆；左栏会话列表动态渲染 + 点击切换；MCP 网关全工具支持 `room_id` 参数（默认 default，成员归属校验越权拒绝）；pytest 44 例全过 + 多房间真机 e2e（建群 → 成员隔离 → 新群 WS 聊天仅本群成员回复 → 技能 CRUD → 删群）。

## 第 5.5 步能力清单（已完成并验收）

- **互聊轮次不设上限**：移除 budget_turns 轮数熔断（身份卡编辑器不再有轮数滑杆）；任务级熔断保留（防死锁，超限暂停 @人类裁决，非硬上限）。
- **Agent B 定时归档清理**（`app/rooms/janitor.py`，lifespan 拉起）：互聊不设上限后的存储防膨胀——每 `janitor_interval_s`（默认 1800s）检查一次，自上次游标以来的 chat 消息达 `janitor_min_msgs`（默认 60）即由 Agent B（群聊管家）总结成摘要写入公共记忆，然后物理删除这批 chat 消息（dispatch/receipt/task_plan/system 等关键消息保留），群里发归档回执；游标按房间存 kv 表。LLM 未配置时占位摘要。阈值可经环境变量 `AGENT_ROOM_JANITOR_INTERVAL_S` / `AGENT_ROOM_JANITOR_MIN_MSGS` 调整。
- **内置双 Agent 职责分化**（不绑定身份卡时生效）：Agent A·用户服务助手（答疑、辅助提示词生成、指导意见、调度安排、监督进展）；Agent B·群聊管家（总结归档、监督清理、维护上下文）。
- **删除成员**：成员面板外部成员新增 ✕ 删除（`DELETE /api/agents/{aid}`，令牌即刻失效；内置 A/B 不可删）。
- **外部成员按钮随绑定状态切换**：未绑定 → 「复制令牌」（拿去接入）；已绑定 → 「绑定身份卡」（弹窗换绑/解绑）；成员列表兜底清理悬空身份卡引用。
- **验收**：pytest 37 例全过（新增 janitor 归档/清理/游标房间隔离、内置默认职责、删除成员用例）；GUI 走查（Playwright + Edge）确认按钮切换、绑定弹窗、删除流程、滑杆移除。

## 第 5 步能力清单（已完成并验收）

- **CEO 编排闭环**（设计文档 s6）：任务面板下达目标 → CEO 拆任务分解图（LLM JSON 拆解，未配置时占位双子任务模板）→ 人类确认 → `dispatch` 排产单按 `depends_on` 依赖派发 → 执行者交付（deliver 或交付说明）→ 验收 `receipt`（不合格打回附原因重做，上限 2 次超限熔断）→ 全部完成汇总 @人类。黄金法则「编排者不执行、执行者不编排」：CEO 是总线监听器（L1 编排，不占成员席位），`type=task` 消息不再直触 responder。
- **任务级熔断**：执行期间互聊条数超 `task_max_chat_turns`（默认 12）→ system @人类并暂停任务；任务面板可「继续执行」（resume 按依赖续派）或终止。房间级轮数熔断（budget_turns）保留不变。
- **向量记忆**（设计文档 s9）：collection `room_{id}_public` / `agent_{id}_private` 物理隔离存储于 `backend/data/memory/`；检索接口强制带 `(room_id, agent_id)`，私有记忆仅本人可见；写入时机=验收通过沉淀公共结论 + Agent 交付写私有笔记，闲聊不入库；responder 组装上下文时检索 top-k 注入并标注来源时间。
- **本地向量库选型**：内置 JSON 向量库（暴力余弦，Python 3.14 暂无 chromadb 兼容轮子；接口与 Chroma 同形，换装只动 `app/memory/hub.py`）；embedding 留 OpenAI 兼容 `/embeddings` 接口位，未配置时降级为确定性字符 n-gram 哈希 256 维（离线零依赖）。
- **前端**：任务面板（下达/分解图确认/子任务状态 chips/熔断恢复/作废）+ 记忆面板（统计/最近记忆）；CEO 编排气泡（「L1 编排」标签）随事件流渲染。
- **验收**：pytest 34 例全过（新增记忆隔离/持久化 4 例 + 编排 6 例：拆解/依赖派发/打回重试上限/互聊熔断/作废/mock 全链路含记忆沉淀）；真机 e2e（WS 下达 → 确认 → 7 秒完成两环验收 → 汇总 → 公共记忆沉淀）；GUI 走查（Playwright + 系统 Edge）通过。

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
- **验收**：pytest 4 例（令牌校验/冒名拒绝/防死循环/幂等去重）全过；SDK ClientSession 模拟外部 Agent join→send→poll 全链路通过；Playwright（系统 Edge）GUI 走查通过；ZCode 经 `.zcode/config.json` 注册实测 join/send/poll 全通——第一个真实外部成员。

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
- **LLM 配置**：右侧「模型」面板填 OpenAI 兼容 Base URL / API Key / 模型名；未配置时 Agent 返回本地占位文本、CEO 用占位双子任务模板（全流程仍可跑通）。
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
  app/orchestrator/ CEO 编排器（ceo.py 拆解/派发/验收/熔断 / routes.py 任务 API）
  app/memory/      向量记忆（hub.py 公私隔离向量库 / embeddings.py 可换装 embedding）
  app/skills/      内部技能库（store.py md 存储 / routes.py API + skills.* 工具）
  agent_md/        内置 Agent 专属行为规范（agent_a.md / agent_b.md，注入 system prompt）
  skills/          技能文档（*.md，前端「技能」面板与 skills.* 工具共用）
  tests/           pytest（网关 / 文件工作区 / 工具循环 / 编排 / 记忆）
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
| GET | `/api/tasks?room_id=` | 任务列表（含子任务状态） |
| POST | `/api/tasks/{id}/confirm` | 确认开工 / 熔断后恢复（action=resume） |
| POST | `/api/tasks/{id}/abort` | 作废任务 |
| GET | `/api/memory?room_id=` | 记忆统计 + 最近记忆（只读） |
| GET/POST | `/api/rooms` | 房间列表 / 新建群聊（选择成员） |
| DELETE | `/api/rooms/{rid}` | 删除群聊（default 不可删） |
| GET/POST | `/api/skills` | 技能库列表 / 保存技能 |
| GET/DELETE | `/api/skills/{name}` | 读技能 / 删技能 |
| POST | `/api/llm-test` | LLM 端点连通性校验 |
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
5. ~~第 5 步：CEO 编排闭环 + 向量记忆 + 熔断~~ ✅
6. 第 6 步：网关侧二次权限校验 + 排产单工具（claim_subtask 等）+ 无人值守开关
