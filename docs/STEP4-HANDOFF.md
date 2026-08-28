# Agent Room · 第 4 步交接文档（新会话从这里继续）

日期：2026-08-28 · 交接人：ZCode 上一会话 · 目标：让新会话 5 分钟内接手

## 一、当前状态（第 3 步已完成并验收）

- 项目：`d:\ai-use\projects\agent-room`（git 仓库，HEAD=`54236e3`）
- 完成：MCP 接入网关——外部 Agent 进群一等公民。ZCode 本人已实测进群收发（join_room / send_message / poll_messages 全通），TRAE stdio 桥已由用户配置（当前以「TRAE·测试」身份在线）。
- 验收结论：三层验收（pytest 4 例 / SDK 模拟端到端 / GUI 走查 + ZCode 实测）全部通过。

## 二、第 4 步已确认的设计决策（无需重新讨论）

| 决策点 | 结论 |
|---|---|
| 实施顺序 | **先文件工作区，后 UI 改版**（两步在同一会话依次做） |
| 工具接入 | 内置 Agent 用 **OpenAI Function Calling 循环**（stream 中 tool_calls → 执行 → 回灌 → 直至纯文本回复） |
| 文件存储 | **磁盘目录 `backend/workspace/{room_id}/` + SQLite files 索引**（照设计文档 s11：id, room_id, path, version, author_agent, manifest_json, updated_at） |
| 并发写 | **仅 base_version 乐观锁**（冲突 409 返回 latest_version 让 Agent 重写；人类直写不校验） |
| 权限 | **按身份卡 tools_allow 严格过滤**（没勾 fs.* 的 Agent 拿不到工具定义） |
| 交付通知 | fs.write 成功后自动 `bus.publish` 一条 `type=deliver` 消息（进事件流可回放） |
| UI 改版 | **布局级重构参考微信**：左侧会话列表 + 右侧单会话视图（聊天窗内嵌身份/文件等 Tab 或面板）；保留输入框、@提及、P0 按钮；不引入前端框架（原生 HTML/CSS/JS） |

## 三、第 4 步实现要点（新会话开工清单）

1. **后端 `app/files/`**：workspace.py（路径规范化防 `../` 逃逸 + list/read/write/delete + base_version 乐观锁）、tools.py（fs.list/fs.read/fs.write 的 function calling schema + 执行器）、routes.py（`GET /api/files` 树、`GET /api/files/content`、`POST /api/files/upload` multipart、`DELETE`）、db 补 `files` 表（增量迁移）
2. **responder 改造**：`stream_text` → `run_turn` 工具循环；按 tools_allow 过滤工具；LLM 未配置时走现占位路径不动；`asyncio.to_thread` 执行工具；P0 抢占免费继承（整个循环是已登记任务）
3. **前端文件面板**：文件树 + 版本 + 作者徽标 + 上传 + 点文件名预览；deliver 消息渲染成可点击附件样式
4. **验收**：pytest（路径逃逸 / 乐观锁冲突复现与拦截）+ 真实 LLM 端到端（Agent 写交付物 → deliver 进群 → 面板见版本）+ 冲突场景（两个并发写同文件被 409 拦截且 Agent 凭 latest_version 重写成功）
5. **UI 改版**（文件区完成后）：微信式布局重构，改版后必须保留全部现有能力（双 Agent 并行流式、@提及、P0、外部成员管理、文件面板）

## 四、环境备忘（重要）

- 后端启动：`cd backend && .venv\Scripts\python.exe main.py`（127.0.0.1:8899；当前由桌面程序 sidecar 拉起，PID 会变，`netstat -ano | grep 8899` 找）
- MCP SDK 2.x 生命周期坑：`streamable_http_app` 子应用 mount 后**必须把 `srv.session_manager.run()` 挂到父应用 lifespan**（`app/mcp_gateway/server.py::mount_gateway` 已有解法，直接参考）
- 本项目已用官方 `mcp` SDK 2.x（MCPServer 替代 FastMCP）；依赖 `requirements.txt` 已含 `mcp>=1.9`
- 本机代理环境变量**会劫持 httpx2 默认客户端**——测试脚本一律 `httpx2.AsyncClient(trust_env=False)`
- Playwright 技能可用，但**Chromium 下载会卡死**，用系统 Edge：`executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'`
- 测试脚本写系统临时目录（不入库）；pytest 在 `backend/tests/`

## 五、运行时状态（新会话如需真实验收直接可用）

- 外部成员：「TRAE·测试」（agent_58c5827c，stdio 桥在线）、「ZCode Agent」（agent_df4cc624，http 在线）
- 我的 .zcode/config.json 已注册 agent-room（url http://127.0.0.1:8899/gateway/mcp + 双因子头）
- 内置双 Agent A/B 无身份卡绑定；无 LLM 配置（占位回复）

## 六、第 4 步验收标准（设计文档第 12 章原文）

> 文件工作区：上传、预览、Agent 经 MCP 工具读写（右侧底部面板呈现文件树与版本）——Agent 交付物落工作区，版本冲突可复现并被拦截
