# Agent Room · 第 5 步交接文档（新会话从这里继续）

日期：2026-08-29 · 交接人：ZCode 上一步会话 · 目标：让新会话 5 分钟内接手

## 一、当前状态（第 4 步已完成并验收）

- 项目：`d:\ai-use\projects\agent-room`（git 仓库，HEAD=`80d72e7`，两个提交：`9981ec2` 第 4 步上半文件工作区、`80d72e7` 下半 UI 微信式改版）
- 完成：文件工作区（fs 工具 + base_version 乐观锁 + 文件面板）+ UI 微信式布局改版（左会话列表 + 右聊天窗 + 右侧内嵌 6 标签面板）
- 验收结论：pytest 24 例全过；mock LLM 端到端（工具循环 → 写入 → deliver 广播 → 文件落盘）；ZCode 同款官方 SDK + token 走 MCP 全链路实测（含 409 冲突 → 凭 latest_version 重写成功）；Playwright（系统 Edge）GUI 走查通过
- 补充：桌面快捷方式已就位（`scripts/launch-agent-room.vbs` 启动器 + 桌面「Agent Room.lnk」，冷启动实测通过）；`backend/workspace/` 验收残留已清理（.gitignore 已覆盖，运行时自动重建）

## 二、第 5 步范围（设计文档原文，路线已对齐：实际第 5 步 = 设计文档 v1.2 第 12 章「第 4 步」）

> 编排闭环：CEO 拆目标 → 确认 → 排产单 → 验收 + 向量记忆 + 熔断。
> 验收标准：完整跑通一个双 Agent 协作任务，死锁能自动求助。

设计文档相关章节（`d:\ai-use\agent-collab-system-design-doc.html`）：

- **§6 职位化自主编排**：L0 人类 / L1 CEO 总编排器（✔）/ L2 部门主管（V2，不做）/ L3 执行者（✔ A/B）。黄金法则：**编排者永不执行，执行者永不编排**；小任务（≤3 子任务）自动退化为单层排产。
- **§6.2 标准编排流程**：用户下达 task → CEO 生成**任务分解图**（子任务+依赖+所需身份）→ **先给用户确认**（可配置自动通过）→ 确认后发 `dispatch` 排产单 → 总线按依赖顺序投递 → 执行者互聊走 @提及（计入轮数）→ `deliver` → 编排层验收发 `receipt`（不合格打回附原因，计入轮数）→ 全部完成 CEO 汇总 + 成本报告 @人类。
- **§9 多方记忆与向量库**：Chroma / Qdrant **本地实例** + 本地中文友好 embedding（如 bge-m3），**记忆数据不出本机**；collection 按 `room_{id}_public` 与 `agent_{id}_private` **物理隔离**，检索接口强制带身份鉴权；写入时机：验收通过才沉淀公共记忆、Agent 交付时可写私有笔记、闲聊不入库；检索注入：收到排产单时自动 top-k 注入上下文并标注来源时间；公共记忆写入需编排层确认。
- **§10 熔断**：单任务互聊超 `max_chat_turns` 或 token 超预算 → system 消息中断并 @人类裁决（现有 budget_turns 轮数熔断是房间级，第 5 步补任务级）。
- **消息协议**：`dispatch`（P1, orchestrator）、`receipt`（P3, 编排层）为第 5 步新增消息类型，schema 仍是 s4 v1.0 的 type 扩展。

## 三、第 5 步待确认的设计决策（新会话开工前先与用户对齐，不要自行拍板）

| 决策点 | 选项 / 建议 |
|---|---|
| 向量库选型 | Chroma（纯 Python 内嵌，零部署）vs Qdrant（独立进程/容器）。建议 **Chroma 内嵌**（persist 目录放 backend/data/chroma），贴合「sidecar 一体、本机优先」 |
| embedding 方案 | bge-m3 本地部署体积大（~2GB，需下载）。备选：先用 OpenAI 兼容 embeddings API 留接口 + 本地降级占位；或 sentence-transformers 裁剪小模型。**需用户定** |
| CEO 形态 | 建议：CEO = 内置特殊 Agent（独立身份卡，tools_allow 不含 fs.*，仅编排），走现有 responder 工具循环扩展 dispatch 工具；「编排者不执行」由身份卡白名单保证 |
| 任务分解图确认闸 UI | 微信式布局下建议走「任务」面板（rp-task 目前是空壳）+ 系统消息通知确认 |
| 排产单存储 | 建议 SQLite 新表 subtasks（id, room_id, parent_task, assignee, depends_on, status, delivery_file…），dispatch/receipt 全部走事件流落库可回放 |
| 无人值守开关 | 设计文档将其列在第 5 步（每外部 Agent 实例独立开关）；可顺延到第 6 步网关二次权限校验一起做，**需用户定** |

## 四、第 5 步实现要点建议（开工清单）

1. **数据表**：subtasks 表 + memory 相关表（或直接靠向量库 collection 元数据）；messages 表无需动（新 type 直接落库）
2. **编排器 `app/orchestrator/`**：ceo.py（任务分解图生成→确认闸→dispatch 派发→receipt 验收→汇总），挂在 bus 消费侧；dispatch/receipt 均为 bus.publish 的消息类型
3. **执行侧**：responder 收到 dispatch（mentions 定向）时按 subtask 工作；交付沿用 fs.write → deliver 链路；receipt 打回时凭原因重做（计入轮数）
4. **熔断**：任务级互聊轮数/token 预算计数器，超限发 system + @human（复用现有 P0/interrupt 通道）
5. **向量记忆 `app/memory/`**：写入钩子（receipt 通过 → 公共 collection；Agent 交付 → 私有 collection）；检索注入点：responder 组装上下文时 top-k；鉴权：检索接口按 (room_id, agent_id) 强制隔离
6. **前端**：任务面板（rp-task）渲染分解图/排产单/验收状态；确认闸交互
7. **验收**：真实 LLM 配置下完整跑通一个双 Agent 协作任务（拆解→确认→并行/串行执行→交付→验收→汇总）；人为构造死锁（互聊循环）验证熔断自动 @人类；记忆跨会话可检索且私有隔离可复现

## 五、环境备忘（重要，沿用第 4 步）

- 后端启动：`cd backend && .venv\Scripts\python.exe main.py`（127.0.0.1:8899）；或直接双击桌面「Agent Room」快捷方式（vbs 启动器会拉起后端并开浏览器）
- MCP SDK 2.x 生命周期坑：`streamable_http_app` 子应用 mount 后**必须把 `srv.session_manager.run()` 挂到父应用 lifespan**（`app/mcp_gateway/server.py::mount_gateway` 已有解法）
- MCP 客户端 2.x：`streamable_http_client(url, http_client=create_mcp_http_client(headers=...))` 返回 **2 元组**；`list_tools()` 返回 ListToolsResult（取 `.tools`）
- 本机代理环境变量**会劫持 httpx2 默认客户端**——测试脚本一律 `httpx2.AsyncClient(trust_env=False)`
- Playwright 技能可用，但 **Chromium 下载会卡死**，用系统 Edge：`executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'`
- 测试脚本写系统临时目录（不入库）；pytest 在 `backend/tests/`（现有 24 例是回归底线，改动后须全绿）
- 依赖装在 `backend/.venv`（requirements.txt 已含 mcp、openai、uvicorn、fastapi；第 5 步新增 chromadb 等记得同步 requirements.txt）

## 六、运行时状态（新会话如需真实验收直接可用）

- 外部成员：「TRAE·测试」（agent_58c5827c，stdio 桥）、「ZCode Agent」（agent_df4cc624，http）——本人 .zcode/config.json 已注册 agent-room 网关（url + 双因子头）
- 内置双 Agent A/B 无身份卡绑定；无 LLM 配置（占位回复）——第 5 步编排闭环验收**必须配真实 LLM**（前端「模型」面板或 /api/llm-config）
- `backend/workspace/` 已清空（运行时自动重建）；`backend/agent_room.db` 保留历史消息流

## 七、第 5 步验收标准（设计文档第 12 章原文）

> 编排闭环：CEO 拆目标→确认→排产单→验收 + 向量记忆 + 熔断——完整跑通一个双 Agent 协作任务，死锁能自动求助。
