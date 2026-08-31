# Agent Room 前端重设计 · 执行记忆文档

> **用途**：本次前端重写的唯一执行依据。任何会话续作，先通读本文档，再按【第四节】步骤执行；**每一步动手前必须先重读对应源文件原文**（防止凭记忆改写丢契约）。
> **铁律**：不修改 `backend/` 下任何文件；只替换 `frontend/` 三个文件（index.html / i18n.js / app.js）。
> 设计方向：**深色「指挥室 / Ops Console」**——琥珀色为人类操作主色、等宽字体呈现状态数据、右侧面板改竖向图标栏；功能与后端对接点 100% 保留。

---

## 一、任务与环境事实

- 用户原始请求：「重新设计前端，保留功能不变。对接后端。不要动后端。」
- 后端事实（已确认，只读）：
  - FastAPI 监听 `127.0.0.1:8899`，以 `StaticFiles(directory=frontend, html=True)` 同端口托管前端（`backend/app/main.py:281`）→ **只替换 frontend/ 三文件即可，后端零改动**。
  - 版本注入中间件（`backend/app/main.py:68-70`）：对 HTML 做精确字符串替换——`src="app.js"` → `src="app.js?v={app.version}"`，`src="i18n.js"` 同理。**新 HTML 必须写裸 src**（不带 `?v=...`），否则绕过注入、失去缓存失效机制。
  - 后端启动命令：`backend\.venv\Scripts\python.exe backend\main.py`（工作目录任意，入口 `backend/main.py`，uvicorn.run）。
- CSS 必须全部内联在 HTML 的 `<style>` 中（CSS 文件不在后端 no-cache 白名单，外链会缓存）。
- 浏览器验证用「浏览器控制」插件，访问 `http://127.0.0.1:8899`。

## 二、新设计令牌与布局规范

### 2.1 色彩令牌（CSS variables，全站统一）

```css
:root{
  --bg:#0d0f12;            /* 全局底：近黑炭色 */
  --panel:#14171c;         /* 左侧栏 / 右面板底 */
  --card:#191d23;          /* 卡片 / 气泡底 */
  --card-2:#1f242c;        /* 悬浮层 / 次级面 */
  --line:#262c35;          /* 分隔线 */
  --line-2:#333b46;        /* 强分隔 / 边框高亮 */
  --ink:#e9e7e2;           /* 主文字：暖白 */
  --muted:#8b93a1;         /* 次级文字 */
  --faint:#5b6472;         /* 弱化文字 */
  --brand:#f0a63c;         /* 琥珀主色：人类操作（发送、CTA、当前房间、人类气泡标识） */
  --brand-strong:#ffb84d;  /* 琥珀 hover/高亮 */
  --brand-soft:rgba(240,166,60,.14);  /* 琥珀软底 */
  --brand-ink:#16130b;     /* 琥珀底上的深色文字 */
  --accent:#3ecfb2;        /* teal：系统 / 编排者标识 */
  --warn:#e8b339;
  --danger:#ef6a5e;
  --ok:#4cc38a;
  --wx-green:#2fbf5f;      /* 微信绿（深色下提亮） */
  --mono:'JetBrains Mono','Cascadia Mono',Consolas,'Courier New',monospace; /* 状态数据/版本/路径/token 一律等宽 */
  --sans:'Segoe UI',system-ui,'PingFang SC','Microsoft YaHei',sans-serif;
}
```

- 成员专属色相在深色下提亮：`hsl(var(--h) 62% 62%)`（原浅色为 `hsl(var(--h) 70% 45%)`）。
- 氛围：`#chat-view` 背景允许极淡的顶部琥珀辉光（`radial-gradient`，透明度 ≤6%）+ 细网格纹理（可选），保持克制。

### 2.2 布局结构

```
#app { display:grid; grid-template-columns:264px 1fr auto; height:100vh; }
├── #chat-list        左栏（房间列表）：头部 + 搜索 + 分组 + #room-list + 底部操作
├── #chat-view        中栏：.topbar + #feed + #typing + .composer
└── #right-panel      右侧：改「竖向图标栏 + 面板体」两段式
    ├── .rp-tabs      竖向图标栏（.rp-tab[data-rp] 竖排，CSS flex-direction:column 实现竖栏，DOM 类名不变）
    └── 9 × .rp-body[id]  面板体（一次只显示一个）
```

- `#right-panel.closed` 收起（宽度归零/位移隐藏），行为与原版一致。
- 顶栏 4 个 `.icon-btn[data-panel]`（btn-panel-files/members/settings/help）保留在顶栏，由 app.js 注入 `dataset.panel` 后可点击展开对应面板。
- 琥珀使用点收敛：发送按钮、人类消息的 who-dot/名字色、当前房间高亮、主 CTA（发起任务/新建房间确认）；系统与编排者用 `--accent` teal；agent 用成员色相。

### 2.3 组件规范要点

- 气泡：`--bub-a` 控制透明度（外观面板可调），深色下默认底 `rgba(25,29,35,.92)`。
- 状态类数据（版本 chip、文件版本号、token、状态 chip st-*、时间戳）一律 `--mono`。
- 滚动条深色细条样式；modal 遮罩 `rgba(6,8,10,.6)` + backdrop blur。

---

## 三、功能契约（改皮不改骨，100% 保留）

### 3.0 执行纪律

1. 每一步开始前**先重读对应源文件**（index.html 551 行 / app.js 1103 行 / i18n.js 291 行）。
2. 步骤 0 先备份三个原文件到 `docs/backup-frontend-v0.8/`。
3. app.js 中**所有网络请求、WS 协议、状态机、事件绑定逻辑逐字保留**；只允许改两类地方：a) 渲染 innerHTML 模板适配新 DOM/类名（类名尽量保持不变，见 3.2）；b) `applyAppearance` 深色化（见 3.6）。

### 3.1 index.html 必须保留的全部 id（清单核对用）

**左栏 / 顶栏**：`chat-list, room-list, btn-new-room, btn-add-external, room-name, ws-chip, llm-chip, btn-panel-files, btn-panel-members, btn-panel-settings, btn-panel-help, btn-stop-all`
**中栏消息区**：`feed, typing, draft, mention-pop, refs-pop, btn-refs, scope-tip, btn-send`
**右面板体**：`rp-files, rp-task, rp-members, rp-identity, rp-model, rp-memory, rp-appearance, rp-skills, rp-help`
**文件面板**：`file-tree, file-preview, file-input, btn-upload, btn-save-preview, file-count, file-preview-head`
**任务面板**：`task-goal, btn-issue-task, task-list, btn-tasks-clear`
**成员面板**：`member-list, agent-count, btn-add-external2, btn-archive-now, btn-stop-all2`
**身份面板**：`id-list, btn-new-id, id-label, id-persona, id-resp, id-tools, btn-tools-rec, btn-tools-clear, btn-save-id, btn-del-id`
**模型面板**：`llm-url, llm-key, llm-model, btn-save-llm, llm-test-result`
**记忆面板**：`mem-stats, mem-list, btn-mem-clear`
**外观面板**：`lang-select, bg-presets, btn-bg-image, bg-file, btn-bg-reset, bg-mask, mask-v, bub-opacity, bub-v, fx-ripple`
**技能面板**：`skill-list, import-source, btn-import-local, skill-name, skill-content, btn-save-skill, btn-import-skill, skill-files`
**帮助面板**：`rp-help`（内部保持 `.grp` 分组标题 + `.help-item` 条目结构，i18n.js 的 I18N_HELP_EN 模板与新结构一一对应）
**弹层**：`room-modal-mask`（内含 `room-name-in, room-agent-picks, btn-room-create, btn-room-cancel`）；`modal-mask`（内含三段：`modal-form`→`ext-name, ext-identity, btn-ext-create, btn-ext-cancel`；`modal-result`→`ext-token, cfg-zcode, cfg-trae, btn-copy-all, btn-ext-done`；`modal-bind`→`bind-title, bind-identity, btn-bind-save, btn-bind-cancel`）

**结构约束**：
- 顶栏 4 个 icon-btn 初始**不带 data-panel**（app.js 注入 dataset.panel：files→rp-files、members→rp-members、settings→rp-identity、help→rp-help）。
- 右面板保留 `.rp-tabs > .rp-tab[data-rp]` 与 `.rp-body[id]` 结构（app.js openPanel 三方联动依赖），竖向仅靠 CSS。
- 脚本引用两行、顺序 i18n 先 app 后、**裸 src**：`<script src="i18n.js"></script>` `<script src="app.js"></script>`。
- `bg-file`、`file-input` 为隐藏 file input，由按钮触发 click。
- `#typing` 输入指示器保留。

### 3.2 app.js 动态 innerHTML 依赖的 class（新 CSS 必须全部提供样式）

- 房间列表：`.convo, .convo-avatar, .convo-info, .convo-name, .cnt, .convo-last, .convo-time`
- 消息：`.msg` + 修饰 `human / agent / system / orch / ghost / deliver / folded / expanded`；内部 `.who, .who-dot(内联 --h), .lbl, .body, .fold-tip, .ghost-lbl, .tool-note, .deliver-file`
- 成员：`.member, .avatar, .kind-badge(内联/外显 internal|external), .copy-tok, .bind-card, .tok2, .del-agent`
- 身份：`.idcard, .sel, .cv`
- 文件：`.file-row, .file-name, .file-dir, .file-ver, .file-author, .file-author.hum, .file-del`
- 任务：`.task-card, .task-goal, .task-status, .subtask, .st-chip(st-pending|st-dispatched|st-accepted|st-rejected), .sub-detail, .task-actions`
- 记忆：`.mem-item, .mem-meta, .mini-btn`
- @提及弹层：`.mp-item(.all 可加), .on`
- 状态 chip：`.chip(.live)`；波纹特效：`.ripple, .fx`
- 幽灵气泡（流式生成中）：`msg agent ghost` → is_final 后 commitGhost 移除并落正式气泡；**空内容永不产生气泡**

### 3.3 面板切换三方联动

- `.rp-tab[data-rp]` 点击 → openPanel；`.icon-btn[data-panel]` 点击 → 打开面板并激活对应 tab；`.rp-body[id]` 单显。
- `#right-panel` 的开合类 `.closed`；app.js 维护 `panelOpen` 状态。

### 3.4 版本 chip（boot 序列一环）

- boot：`applyLang` → `GET /api/health`（取版本）→ **`$('llm-chip').after(chip)`** 插入版本 chip（`#llm-chip` 必须存在）→ refreshRooms → refreshIdentities → renderToolCheckboxes([]) → refreshSkills → applyAppearance → `lang-select.value` 赋值 → loadRoomView → connect()。

### 3.5 i18n 新机制规格（i18n.js 重写方案）

```js
// 词典：语义 key → [zh, en]
const STR = { 'panel.files': ['文件','Files'], ... };   // 覆盖原 I18N_EN 全部约 120 条 + confirm 文案 + SUB_CHIP + TASK_ST 状态词
// 反查表（供 i18t 用）：启动时由 STR 构建 zhText → key
// 静态标注：data-i18n="key" → textContent；data-i18n-ph="key" → placeholder；data-i18n-title="key" → title
// 动态串：i18t(zh) 反查 → 当前语言文本；查不到原样返回 zh
// 帮助面板：#rp-help 整块互换（dataset.zh 备份原文 + I18N_HELP_EN 模板；模板结构须与新 HTML 的 .grp/.help-item 对应）
// applyLang(lang)：localStorage['aroom-lang'] 持久化 → 遍历 [data-i18n]/[data-i18n-ph]/[data-i18n-title] → 帮助互换 → dispatchEvent(new CustomEvent('langchange')) → applyAppearance(lang)
// app.js 保留 langchange 监听，动态区域重渲染
```

- 验收线：切 en 后界面无可见中文残留（用户内容除外）；confirm() 文案、任务状态词（TASK_ST）、子任务 chip 词（SUB_CHIP）均已翻译。

### 3.6 外观系统深色化改造点（app.js 中唯一的行为级修改）

- `BG_PRESETS` 重定义为深色系：default → `#0d0f12`（其余预设给深色友好的纯色/暗色图，保留自定义图片能力）。
- 遮罩颜色：原 `linear-gradient(rgba(246,246,248,x), rgba(246,246,248,x))` → 改 `rgba(13,15,18,x)`（--bg 同源）。
- `--bub-a`（气泡透明度）、`fx-ripple` 波纹开关、`mask-v` 遮罩滑条行为不变；`localStorage['aroom-appearance']` 结构兼容。

### 3.7 API 端点全集（app.js 逐字保留，不得增删改参数）

| 方法 | 端点 | 用途 |
|---|---|---|
| GET | `/api/agents?room_id={id}&all=1` | 成员列表（含全房间） |
| POST | `/api/agents/{id}/bind` | 绑定身份 |
| POST | `/api/agents/{id}/rotate-token` | 轮换 token |
| DELETE | `/api/agents/{id}` | 删除 agent |
| POST | `/api/agents/external` | 创建外部成员 |
| GET/POST | `/api/identities` | 身份列表 / 新建 |
| PUT/DELETE | `/api/identities/{id}` | 身份编辑 / 删除 |
| GET/DELETE | `/api/files?room_id={id}` | 文件树 / 删除文件 |
| GET | `/api/files/content?room_id={id}&path={p}` | 预览文件内容 |
| POST | `/api/files/write` | 保存预览编辑（乐观锁 base_version；冲突读 `d.detail.latest_version`） |
| POST | `/api/files/upload?room_id={id}` | 上传（FormData） |
| GET | `/api/tasks?room_id={id}` | 任务列表 |
| POST | `/api/tasks/{id}/confirm`、`/api/tasks/{id}/abort` | body `{action}` |
| DELETE | `/api/tasks/{id}` | 删除任务 |
| POST | `/api/tasks/clear-finished` | 清理已完成 |
| GET | `/api/memory?room_id={id}` | 记忆列表 |
| DELETE | `/api/memory/item?room_id={id}&id={mid}&scope={s}[&agent_id={aid}]` | 删单条 |
| POST | `/api/memory/clear` | 清空记忆 |
| GET/POST | `/api/rooms` | 房间列表 / 新建 |
| POST | `/api/rooms/archive` | 归档 |
| GET | `/api/room/{id}` | 房间详情 |
| GET/POST | `/api/skills` | 技能列表 / 新建 |
| GET/DELETE | `/api/skills/{name}` | 技能内容 / 删除 |
| POST | `/api/skills/import` | 导入技能 |
| POST | `/api/llm-config` | 保存模型配置 |
| POST | `/api/llm-test` | 测试连通 |
| GET | `/api/health` | 健康检查（取版本号） |

### 3.8 WebSocket 协议

- 连接：`ws(s)://location.host/ws/{room_id}`；断线重连逻辑保留。
- 前端发送：`{type:'chat', text, mentions}` / `{type:'interrupt', text}` / `{type:'task', text}`。
- 前端接收 type：`chat`（`sender.kind` ∈ human/agent/system/orchestrator；`is_final`；`payload.text`；`mentions`；`tool_summary`）、`system`、`deliver`、`task`、`task_plan`、`dispatch`、`receipt`、`tool_event`（`msg.tool_event.name` / `result_ok`，**不落库**）。
- mentions 匹配：`text.lastIndexOf('@')` + `a.name.split(' ')[1]` 尾部匹配 + `'a'/'b'` 前缀映射 `agent_a/agent_b`。
- deliver 附件解析正则：`/([^\s（(]+)\s*（?v(\d+)/`。

### 3.9 其他关键行为（引用片段，重写时逐字对照）

```js
// 幽灵气泡（ghostFor）
el.innerHTML = `<div class="who"><i class="who-dot" style="--h:${hueFor(aid)}"></i>${esc(name)}<span class="lbl ghost-lbl">${i18t('生成中')}</span></div><div class="body"></div>`;
```

- `hueFor(id)`：稳定哈希 → `--h` → 成员色 `hsl(var(--h) 62% 62%)`（深色版）。
- 长气泡折叠：`FOLD_PX = 240`；`folded/expanded` 由 pointerdown 切换，`.fold-tip` 提示。
- 外部成员结果页（showExternalResult）两段配置：HTTP 段（`http://127.0.0.1:8899/gateway/mcp` + `X-Agent-Id` + `Bearer token`）与 stdio 桥段（`backend/mcp_stdio.py` + env `AGENT_ROOM_URL/AGENT_ID/ROOM_TOKEN`），分别填入 `cfg-zcode` / `cfg-trae`，`btn-copy-all` 复制全文。
- `TOOL_OPTIONS = ['fs.read','fs.write','fs.list','skills.list','skills.read','skills.write','memory.query','doc.read','browser.open','shell.run','chat.archive']`（身份面板工具勾选）。
- token 复制用 clipboard；`.kind-badge` 区分 internal/external；`.bind-card` 绑定身份卡。

---

## 四、分步执行清单（按序执行，每步含验收标准）

### 步骤 0 · 备份
- 将 `frontend/index.html`、`app.js`、`i18n.js` 复制到 `docs/backup-frontend-v0.8/`。
- 验收：三文件齐备，可随时回滚。

### 步骤 1 · 重写 index.html
- 先重读原文件 → 产出新深色结构 + 内联 `<style>`（按第二节令牌）。
- 验收：a) 3.1 id 清单逐一核对无缺（可用脚本 diff 新旧 id 集合）；b) 裸 script src ×2 且顺序 i18n→app；c) CSS 全内联；d) `data-i18n/ph/title` 标注齐全；e) `.rp-tabs>.rp-tab[data-rp]`、`.rp-body[id]`×9、顶栏 icon-btn 无 data-panel；f) `#rp-help` 保持 `.grp/.help-item` 结构；g) `#llm-chip` 存在。

### 步骤 2 · 重写 i18n.js
- 按 3.5 规格实现：STR 词典（zh,en 双语）、反查 i18t、data-i18n 三类标注应用、帮助面板整块互换、applyLang + langchange。
- 验收：zh 默认完整；切 en 无中文残留（静态全覆盖 + confirm + SUB_CHIP + TASK_ST）；I18N_HELP_EN 与新帮助结构一一对应。

### 步骤 3 · 重写 app.js
- 先重读原文件 → **网络/WS/状态逻辑逐字照搬**，仅改渲染模板（类名不变为主）与 applyAppearance 深色化（3.6）。
- 验收：对照 3.7 表逐端点核对无增删；boot 顺序与 3.4 一致；ghost 流式、mentions、折叠、版本 chip、MCP 两段配置、乐观锁冲突处理行为不变。

### 步骤 4 · 联调验证（浏览器控制插件，`http://127.0.0.1:8899`）
- 启动后端：`backend\.venv\Scripts\python.exe backend\main.py`。
- 走查单：房间切换 / 发言（ghost→落定）/ @提及 / refs 引用 / 任务下发与子任务状态 / 文件树·预览·保存·上传·删除 / 成员 token 复制·轮换·绑定·删除·外部成员创建（两段配置）/ 身份增删改·工具勾选 / LLM 配置保存与测试 / 记忆列表·删除·清空 / 外观（预设·自定义图·遮罩·气泡透明度·波纹）/ 技能列表·导入·新建·删除 / 帮助 / 中英切换 / 停止全部 / 归档。
- 验收：走查单全绿；发现视觉/交互问题即迭代打磨。

## 五、进度记录

- [x] 任务 0：本记忆文档完成
- [x] 步骤 0：备份原三文件（`docs\backup-frontend-v0.8\`）
- [x] 步骤 1：index.html 重写（新视觉 + 114 处 data-i18n 标注，实测 110 唯一键）
- [x] 交接：步骤 2/3/4 已移交 ZCode，全量素材见 `docs\frontend-redesign-handoff.md`（任务 A=i18n.js / B=app.js / C=联调，含机制骨架、静态键表、70 处动态串索引、en 译表、I18N_HELP_EN 模板、深色化三处与验收线）
- [x] 步骤 2：i18n.js 重写（ZCode 执行，任务 A）——STR 词典 216 条（111 静态键 + 动态串全表）+ REV/REV_EN 双反查 + data-i18n 三类标注 + 帮助整块互换 + 六处 STATIC_I18N 定向 + feed 界面署名互换；对账审计：HTML 111 键、app.js 97 个唯一 zh 动态串 100% 入表
- [x] 步骤 3：app.js 改造（ZCode 执行，任务 B）——深色化三处（BG_PRESETS/遮罩/default 色块）+ langchange 监听（renderRooms/refreshMembers/refreshFiles/fetchTasks/refreshMemory/refreshSkills + LAST_CHIP/LAST_LLM_READY/LAST_MENTIONS 缓存重译）+ B5 两处 i18t + 持久渲染串补包裹（你/广播/CEO 编排/成员/现在等）；语言接线三行逐字保留
- [x] 步骤 4：联调走查（ZCode 执行，任务 C，2026-08-30）——en 态逐面板目检无中文残留（左栏/顶栏/九面板/两弹窗/feed 署名/chips/confirm）；zh 往返还原、刷新语言保持；功能回归：广播/@定向（scope-tip）/文件预览/任务下达链路正常；备注：CEO 拆解受所配 LLM 端点 503（model_not_found）阻断，属后端模型可用性，非本次前端回归；遗留：alertSys 错误提示与「导入完成：成功 N 个」等瞬态 toast 仍为中文（交接文档 B5 范围外，en 态仅在操作出错时短暂可见）
- [x] 附加加固：气泡折叠/展开防锁死（2026-08-30）——①切换从 pointerdown 改挂 click（拖选不再误触）+ 300ms 防双击取反守卫（双击选词不再「展开又立刻收起」）；②新增 rescanFoldAll 全量复扫（已手动展开的不动；变矮解除折叠并摘提示条；变高补折叠），接入 openPanel/closePanel 与 window resize（防抖 150ms）。浏览器实测：单击/双击/三击、流式落定、面板开合、窗口缩放四场景全过
- [x] 功能移除：气泡折叠/展开整体下线（2026-08-30，用户指令）——删除 app.js 的 scheduleFoldCheck / rescanFoldAll / click 切换守卫 / resize 防抖监听及 addBubble、commitGhost、openPanel、closePanel 四处调用点；删除 index.html 的 .msg.folded/.msg.expanded/.fold-tip CSS 与 i18n.js 的 x.expand/x.collapse 词条。验证：grep 零残留、node --check 通过、页面实测长气泡全文显示（1336px 不限高）且点击无折叠行为
- [x] Bug 修复：「气泡还在塌缩」真凶 = 波纹 .fx 类 + flex 挤压（2026-08-30）——用户点气泡触发波纹时 app.js 给气泡永久加 .fx（overflow:hidden，用于裁波纹）；.feed 是纵向 flex 容器，flex 子项一旦自身 overflow:hidden，min-height:auto 内容下限即归零，在长消息流的收缩压力下被压成 ~20px 一条（正文被裁，形似「还在折叠/点了打不开」）。修复：.fx 增加 flex-shrink:0（index.html 一行）。实测：连点 5 条气泡高度不变、正文完整、波纹正常
- [x] v0.9 小更新：消息编号 + 软删 + 星标 + 跳转（2026-08-31，grill-me 两轮澄清后实施）——后端（破例动后端，经用户决策）：messages 表加 starred 列（_migrate_messages 加一行迁移）+ Message.to_dict 带 starred + 新 app/rooms/message_routes.py（DELETE /api/messages/{msg_id} 软删置 invalidated=1 复用 P0 机制、POST /api/messages/{msg_id}/star）+ janitor 归档 DELETE 加 AND starred=0（星标免归档）；前端：addBubble 挂 attachMsgChrome（msg_id 锚 + ☆/✕ hover 按钮 + starred 描边）、renumberFeed 位置序号 1..N（system/ghost 除外，删除后自动连续）、左栏搜索框改造为跳转框（#n 回车滚动定位 + jump-flash 闪烁 2s）、乐观星标失败回滚。实测全绿：编号 46 条全覆盖、删中间消息重排（原 #4 顶上 #3）、星标刷新持久、软删对历史/网关立即隐身、en 态无中文残留（含越界提示 {n}/{m} 占位符）

