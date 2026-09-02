# Agent Room · 多 Agent 群聊协作系统

> **语言 / Language:** 简体中文 · [English](README.en.md)

本机运行的多 Agent 群聊工作台：让电脑上的多个 Agent（内置 LLM Agent + 任意经 MCP 接入的外部 Agent）像拉群一样进同一房间协作。人类是群里的最高仲裁者——下目标、验收、随时 P0 打断。

基于[多 Agent 协作系统设计文档](docs/agent-collab-design.html)实现。一切皆消息（append-only 事件流），编排者不执行、执行者不编排，本机优先（程序、数据、向量记忆不出本机）。

![Agent Room 主界面](docs/screenshots/main.png)

## 功能总览

**群聊协作**
- 双内置 Agent 并行流式回复：Agent A·用户服务助手（答疑 / 提示词辅助 / **权限代理**——受你委托为成员换绑身份卡）、Agent B·群聊管家（内容治理 / 记忆管理 / 越权监管 / 定时归档 / **兼 CEO 编排**）
- 成员平权互聊：所有成员广播互通，外部成员经网关发言也能唤起内置成员；显式 @ 定向、P0 interrupt 随时打断
- 常用指令条：🧹归档 / 💾存记忆 / 🔍查记忆 / 🗑清完成任务 / ✂️删消息 / ⚠️清空记忆 / 📊房间状态，一键直达
- 消息治理：气泡 #n 编号（删除/归档后自动连续）、#n 跳转定位、单条消息星标（**豁免归档**）与软删

**编排闭环（CEO，由 Agent B 兼任）**
- 任务面板下达目标 → 拆任务分解图 → 人类确认 → 排产单按依赖派发 → 执行者交付 → 系统核验 + LLM 验收（不合格打回重做，**不设上限直至通过**）→ 汇总沉淀记忆
- 交付真实性核验：声称写了文件而工作区没有 → 直接打回，幻觉交付骗不过验收

**文件工作区**
- 群内共享工作区：上传 / 预览 / 编辑 / 删除；Agent 经 fs 工具读写同一空间
- base_version 乐观锁：并发写冲突返回 409 + 最新版本号，凭新版本重写即可
- 交付自动播报，点附件直达预览

**身份与技能**
- 身份卡：标签 / 风格 / 职责 / **发言领域 focus（广播按领域选人，留空 = 只响应 @ 与排产单）** / 工具权限
- **工具权限默认全开**：仅 🔒 核心权限（shell.run 电脑控制 / chat.archive / chat.delete / admin.* 授权）须显式勾选
- 内置双 Agent 出厂身份卡 + 岗位手册（`backend/agent_md/`）；内部技能库支持导入导出 .md、Agent 自建技能

**记忆与治理**
- 向量记忆：房间公共记忆 + Agent 私有记忆物理隔离，检索 top-k 自动注入上下文；单条删除 / 一键清空
- 聊天归档：Agent B 定时或手动归档，总结沉淀公共记忆并清理原文（星标消息豁免）；`backend/reset_init.py` 一键恢复出厂

**多群聊与界面**
- 新建群聊自选成员，消息流 / 文件 / 任务 / 记忆按群独立
- 深色「指挥室」界面：琥珀 = 人类操作、teal = 系统侧，等宽字体呈现状态数据，右侧竖向图标栏
- 中文 / English 一键切换（全站无中文残留）；背景 / 透明度 / 动效自定义

## 快速开始

### 方式一：安装包（推荐，装完桌面直接有快捷方式）

从 [Releases](https://github.com/ghgjkbf/agent-room/releases) 下载 `Agent Room_*_x64-setup.exe`（NSIS 安装包，自带 Python 运行时与全部依赖，无需装 Python）：

- 安装即用：**桌面与开始菜单自动创建 "Agent Room" 快捷方式**，双击即启动桌面窗口（内置后端 + 前端，127.0.0.1:8899）
- 静默安装：`/S` 参数；卸载走系统「应用与功能」

自行从源码打包：

```bash
npm install
backend\.venv\Scripts\python.exe scripts\prepare-tauri-resources.py   # 组装 resources/ + 嵌入式 Python + 生产依赖
npm run tauri build                                                    # 产物在 src-tauri/target/release/bundle/nsis/
```

### 方式二：源码运行（开发）

环境：Windows + Python 3.11+（开发环境为 3.14）

```bash
git clone https://github.com/ghgjkbf/agent-room.git agent-room && cd agent-room

# 创建虚拟环境并安装依赖
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
cd ..

# 启动（三选一）
# 1) 双击 scripts/launch-agent-room.vbs 或为其建桌面快捷方式（拉起后端 + 开浏览器）
# 2) 命令行：backend\.venv\Scripts\python.exe backend\main.py
# 3) 开发调试 Tauri 壳：npx tauri dev（需 Rust 工具链）
```

打开 http://127.0.0.1:8899 即是群聊界面。界面内「帮助」标签有完整使用说明与 FAQ。

**接入真实 LLM**：「模型」面板填 OpenAI 兼容端点（Base URL / API Key / 模型名），保存即自动校验连通性；未配置时全系统跑占位模式（功能链路完整可演示）。**接入外部 Agent**：「成员」面板 → 添加外部成员 → 复制令牌与 MCP 接入配置到你的 Agent。

## 架构

```
Tauri 2 桌面窗口（WebView 加载 127.0.0.1:8899；开发期可直接用浏览器）
  └─ FastAPI sidecar（127.0.0.1:8899，同端口托管前端）
       ├─ WS 房间总线（消息先落库再 asyncio.gather 扇出）
       ├─ SQLite 事件流（append-only，重启回放；tasks/subtasks/files/kv 索引表）
       ├─ 编排器（总线监听器：拆解/确认/派发/验收/汇总，署名「CEO 编排」）
       ├─ 向量记忆（公私 collection 隔离，内置向量库可换装 Chroma）
       └─ MCP 网关（streamable-http，外部 Agent 一等公民；fs/skills/list_rooms/chat_delete 工具）
```

- LLM 配置存本机数据库（重启不丢、不出本机）；embedding 默认本地哈希向量，可经环境变量接入远程
- 环境变量（均可选）：`AGENT_ROOM_PORT`、`AGENT_ROOM_LLM_BASE_URL / API_KEY / MODEL`、`AGENT_ROOM_LLM_EMBEDDING_MODEL`、`AGENT_ROOM_TASK_MAX_CHAT_TURNS`、`AGENT_ROOM_SUBTASK_MAX_RETRIES`、`AGENT_ROOM_JANITOR_INTERVAL_S / MIN_MSGS`、`AGENT_ROOM_MEMORY_TOP_K`、`AGENT_ROOM_SKILLS_ZCODE / TRAE / TRAE_BUILTIN`（本机技能库导入路径）

## API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/room/{room_id}` | 房间信息 + 历史回放 |
| GET/POST | `/api/rooms` | 群聊列表 / 新建群聊 |
| GET/POST | `/api/identities` | 身份卡管理（PUT/DELETE 同路径） |
| GET | `/api/agents?room_id=` | 成员列表（`all=1` 查注册表全量） |
| POST/DELETE | `/api/agents/external`、`/api/agents/{aid}` | 外部成员建删 / 令牌重发 |
| GET/POST/DELETE | `/api/files*` | 文件工作区（写走乐观锁） |
| GET | `/api/tasks`、`POST /api/tasks/{id}/confirm\|abort` | 任务编排 |
| GET | `/api/memory`、`/api/skills*` | 记忆只读 / 技能库 CRUD |
| DELETE/POST | `/api/messages/{msg_id}`、`/api/messages/{msg_id}/star` | 单条消息软删 / 星标 |
| POST | `/api/llm-config`、`/api/llm-test` | LLM 配置 / 连通性校验 |
| MCP | `/gateway/mcp` | 外部 Agent 网关（join_room / poll / send / fs / skills / list_rooms / chat_delete） |
| WS | `/ws/{room_id}` | 房间总线 |

## 目录

```
backend/
  main.py           启动入口（API 路由注册 / lifespan / 静态托管）
  reset_init.py     一键恢复出厂（清空运行数据，保留出厂身份卡）
  mcp_stdio.py      stdio 桥（仅支持命令行 MCP 的 Agent 接入）
  agent_md/         内置 Agent 专属行为规范（注入 system prompt）
  skills/           内置技能文档（用户可在界面增删导入导出）
  app/
    core/           配置 / SQLite / 消息协议
    rooms/          房间总线（监听器机制）/ 群聊 API / 聊天归档 janitor
    agents/         流式回复器（工具循环 / 成员互聊调度）/ 成员 API
    identities/     身份卡
    files/          文件工作区（存储 / 工具 schema / API）
    orchestrator/   编排器 + 任务 API
    memory/         向量记忆（公私隔离）+ embedding 可换装
    skills/         技能库（存储 / API）
    mcp_gateway/    MCP 接入网关（streamable-http + 双因子令牌）
frontend/           单页前端（原生 HTML/CSS/JS，深色三栏，无框架，中英双语）
src-tauri/          Tauri 2 壳（窗口 + sidecar 生命周期；NSIS 安装包 + 嵌入式运行时）
scripts/            launch-agent-room.vbs 启动器（可移植）/ prepare-tauri-resources.py 打包资源准备
docs/               设计文档 / CHANGELOG
```

## 路线图

- [x] Tauri release 打包（NSIS 安装包，桌面/开始菜单快捷方式，嵌入式 Python 运行时随包分发）
- [ ] 外部 Agent 承接排产单（claim_subtask 等工具 + 网关二次权限校验 + 无人值守开关）
- [ ] 技能驱动的工作流执行引擎（md 定义结构化步骤，编排器直接引用为子任务模板）
- [ ] 部门主管层（L2）、跨房间记忆、成本仪表盘（V2）

## License

[MIT](LICENSE)
