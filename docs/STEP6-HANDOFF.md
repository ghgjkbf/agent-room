# Agent Room · 第 6 步交接文档（新会话从这里继续）

日期：2026-08-29 · 交接人：ZCode 第 5/5.5 步会话 · 目标：让新会话 5 分钟内接手

## 〇、第 5.5 步增量（2026-08-29 用户反馈迭代）

- **互聊轮次不设上限**：budget_turns 轮数熔断已移除（`bump_turns` 只剩兼容 stub；
  身份卡编辑器无轮数滑杆）；任务级熔断保留。
- **Agent B 定时归档清理** `app/rooms/janitor.py`：lifespan 拉起 `janitor_loop`；
  聊天达阈值（默认 60 条）→ Agent B 总结写公共记忆 → 物理删除该批 chat 消息
  （关键编排/系统消息保留）→ 发归档回执；游标**按房间**存 kv 表
  （`janitor_last_msg_id:{room_id}`，测试会污染全局 kv 表，清理时注意）。
- **内置双 Agent 职责分化**：不绑身份卡时 agent_a=用户服务助手、agent_b=群聊管家
  （`responder.DEFAULT_ROLES`）；绑定身份卡后以身份卡为准。
- **删除成员** `DELETE /api/agents/{aid}`：仅外部成员可删；成员面板 ✕ 按钮。
- **外部成员按钮切换**：未绑定→「复制令牌」；已绑定→「绑定身份卡」弹窗（换绑/解绑）；
  `list_agents` 会兜底清理悬空身份卡引用（历史直接清库遗留）。

## 一、当前状态（第 5 步已完成并验收）

- 项目：`d:\ai-use\projects\agent-room`（git 仓库，HEAD=`519533b`）
- 完成：CEO 编排闭环（拆解→确认→dispatch→receipt→汇总）+ 向量记忆（公私隔离 + 检索注入）+ 任务级熔断
- 验收结论：pytest 34 例全过；真机 e2e（WS 下达 → 确认 → 两环依赖验收 → 汇总 → 公共记忆沉淀）；GUI 走查（Playwright + 系统 Edge）通过
- 补充：桌面快捷方式可用（`scripts/launch-agent-room.vbs` + 桌面「Agent Room.lnk」）；`backend/data/`（记忆库）与 `backend/workspace/` 均已 gitignore，验收残留已清理

## 二、第 5 步落地架构（改哪里先看这里）

- **编排器 `app/orchestrator/ceo.py`**：`Orchestrator` 挂为 `RoomBus.listeners` 监听器（每条落库消息发布后回调 `cb(bus, msg)`），内部 WS / MCP 网关 / deliver 统一覆盖；内置执行者的最终回复经 `respond_agent` 收尾钩子 `notify_agent_final` 进入（chat 首片落库时全文未回填，验收不能靠 publish 时刻的 payload）。编排器自己发的 task_plan/dispatch/receipt/system 在 `on_message` 里忽略（防递归）。
- **type=task 不再直触 responder**：`main._ws_loop` 只对 `chat` 触发回复；task 由编排器独占（设计文档黄金法则）。
- **向量记忆 `app/memory/hub.py`**：collection `room_{id}_public` / `agent_{id}_private` 分 JSON 文件存 `backend/data/memory/`；`MemoryHub(root)` 可重定向目录（测试用）；检索强制带 `(room_id, agent_id)`，私有仅本人。**注意 Python 3.14 无 chromadb 兼容轮子**，现为内置 JSON 向量库（暴力余弦）；`Collection`/`MemoryHub` 接口与 Chroma 同形，换装只动 hub.py。
- **embedding `app/memory/embeddings.py`**：`embed_text()` 优先 OpenAI 兼容 `/embeddings`（硬编码模型名 `text-embedding-3-small`，可改），失败降级确定性字符 n-gram 哈希 256 维。
- **熔断两层**：房间级（agents.chat_turns vs 身份卡 budget_turns，原有）+ 任务级（tasks.chat_count vs `settings.task_max_chat_turns`=12，超限 → 任务 paused + system @人类；任务面板「继续执行」= confirm action=resume 续派）。
- **占位链路**：LLM 未配置时 CEO 用双子任务模板（#1 调研 agent_a → #2 执行 agent_b 依赖串联）、验收默认通过——全流程可跑通，配真实 LLM 后自动切换 LLM 拆解/验收。

## 三、第 6 步范围（README 路线 + 设计文档 §10/§14）

1. **网关侧二次权限校验**：排产单驱动下，外部 Agent 调工具时校验「该子任务是否派给
   它、工具是否在身份卡白名单」（现在 fs.* 只有白名单一层的校验；编排层缺第二道）
2. **排产单工具**：`claim_subtask` / `report_progress` / `submit_delivery` 等 MCP 工具，
   外部 Agent 可像内置 Agent 一样承接排产单（当前排产单只派给内置 Agent）
3. **无人值守自动接活**（设计文档 §14，原第 5 步顺延项）：每外部 Agent 实例独立开关——
   开启时 room-bridge 订阅总线自动唤醒认领子任务；关闭时拉取式接活
4. **成本仪表盘**（V2 顺延可选项）：三层预算 + 实时仪表盘

## 四、环境备忘（重要，沿用）

- 后端启动：`cd backend && .venv\Scripts\python.exe main.py`（127.0.0.1:8899）；桌面快捷方式（vbs 启动器）会自动拉起 + 开浏览器
- MCP SDK 2.x：服务端 lifespan 挂载见 `app/mcp_gateway/server.py::mount_gateway`；客户端 `streamable_http_client(url, http_client=create_mcp_http_client(headers=...))` 返回 2 元组、`list_tools().tools`
- 代理会劫持 httpx2 默认客户端——测试脚本一律 `httpx2.AsyncClient(trust_env=False)`；WS 测试用 `websockets.connect`（venv 有 websockets 17.1，httpx 没有 ws 支持）
- Playwright 用系统 Edge（Chromium 下载卡死）：`executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'`；右侧面板默认收起，脚本里用 `page.evaluate(() => openPanel('rp-task'))` 打开
- 测试脚本写系统临时目录；pytest 在 `backend/tests/`（34 例是回归底线）
- Git Bash 终端 curl 中文显示乱码是 GBK 控制台问题，用 venv python 验证 UTF-8 完整性

## 五、运行时状态

- 外部成员：「TRAE·测试」（agent_58c5827c，stdio 桥）、「ZCode Agent」（agent_df4cc624，http）——.zcode/config.json 已注册网关
- 内置双 Agent A/B 无身份卡绑定；LLM 未配置（占位链路）；`backend/agent_room.db` 保留历史（含第 5 步 e2e 的 2 个 done 任务，可在任务面板看到）
- 排产单当前只派内置 Agent（`_executors()` 过滤 kind=internal）——第 6 步放开外部承接时改这里 + 网关工具

## 六、第 6 步验收标准（对齐设计文档 §12「第 5 步」原文）

> 本地 Agent 接入：MCP 网关上线，先联调 TRAE 再复制到 ZCode；「无人值守自动接活」实现为每实例可选开关——TRAE 经网关收发消息并完成一次交付，越权被拦截；开关切换后两种模式行为均正确。

（收发/交付部分第 3 步已验收；第 6 步重点 = 排产单承接 + 二次权限校验 + 无人值守开关。）
