# Agent Room 前端重设计 · 交接文档（接手方：ZCode）

> **生成**：2026-08-30 ｜ **交接人**：TRAE ｜ **接手人**：ZCode
> **启动指令**：读本文档，按第四/五/六节完成剩余三步。**动手前必须先通读 `docs/frontend-redesign-memory.md`（233 行，执行唯一依据），再重读对应源文件原文**——本文件是「进度 + 素材索引 + 落地细节」的补充，不是替代。

---

## 一、任务背景与铁律

- 用户原话：「重新设计前设计前端，保留功能不变。对接后端。不要动后端。」
- 设计方向（已锁定，不得改）：**深色「指挥室 / Ops Console」**——琥珀 `#f0a63c` 人类操作侧、teal `#3ecfb2` 系统/编排侧、等宽字体呈现状态数据、右侧竖向图标栏；功能与后端对接点 100% 保留。
- 铁律：
  1. 只改 `frontend/` 三文件（index.html / i18n.js / app.js）；`backend/` 零改动。
  2. 每一步动手前**重读对应源文件原文**（重读铁律），不凭记忆改写。
  3. app.js 的网络请求、WS 协议、状态机、事件绑定逻辑**逐字保留**。
  4. 回滚保险：原三文件备份在 `docs/backup-frontend-v0.8/`。

## 二、进度一览

| 步骤 | 内容 | 状态 |
|---|---|---|
| 0 | 备份原三文件 → `docs/backup-frontend-v0.8/` | ✅ |
| 1 | index.html 重写：580 行深色结构 + 全内联 CSS + **114 处 data-i18n 标注（110 个唯一 key）** | ✅ |
| 2 | i18n.js 重写（本文第四节） | ⬜ 由 ZCode 执行 |
| 3 | app.js 渲染适配 + 深色化（本文第五节） | ⬜ 由 ZCode 执行 |
| 4 | 联调验证与打磨（本文第六节） | ⬜ 由 ZCode 执行 |

> 114 处标注中 4 处为同 key 复用：`btn.addExternal`（l.304/l.387）、`btn.cancel`（l.532/l.550/l.571）、`btn.save`（l.412/l.570）。

## 三、动手前红线清单

1. 后端 FastAPI 监听 `127.0.0.1:8899`，StaticFiles 同端口托管前端 → 换文件即生效，无需构建。
2. **裸 script src**（版本注入中间件按字面匹配 `src="app.js"` / `src="i18n.js"` 注入版本号）：新 HTML 已写裸 src（l.577-578），**不得加 `?v=`、不得改顺序**（i18n.js 在前）。
3. CSS 必须全内联在 HTML `<style>`（已做）；app.js/i18n.js 是外链 js，属 no-cache 白名单。
4. id / class 契约 → 记忆文档 3.1 / 3.2；API 全集 → 3.7；WS 协议 → 3.8；boot 序列 → 3.4。改写前逐一核对。
5. 自行复核命令（动手时执行，不要信记忆）：
   - `Grep "data-i18n" frontend/index.html`（静态标注全集）
   - `Grep "i18t\(|SUB_CHIP|TASK_ST" frontend/app.js`（动态串全集）
6. 语言接线三行**逐字保留**（app.js）：l.1081 `if (e.target && e.target.id === 'lang-select') applyLang(e.target.value)`；l.1086 boot `applyLang(localStorage.getItem(I18N_LANG_KEY) || 'zh')`；l.1099 `$('lang-select').value = I18N_LANG`。全局名 `I18N_LANG` / `I18N_LANG_KEY` / `i18t` / `applyLang` 不得改名。

---

## 四、任务 A：重写 `frontend/i18n.js`

### A.1 机制框架（记忆文档 3.5 规格的落地骨架）

```js
/* 词典：语义 key → [zh, en]。覆盖 A.2 静态键 + A.3 动态串 + SUB_CHIP/TASK_ST 状态词 */
const STR = {
  'brand.sub': ['多Agent群聊协作 · 本机运行', 'Multi-agent group chat · runs locally'],
  // ... 全表见 A.2 / A.3
};
const REV = {};                                   // zh → key 反查表（i18t 用），启动时构建
for (const [k, v] of Object.entries(STR)) REV[v[0]] = k;

let I18N_LANG = localStorage.getItem('aroom-lang') || 'zh';
const I18N_LANG_KEY = 'aroom-lang';

function i18t(zh) {                               // 动态串：整串反查 → 当前语言；查不到原样返回 zh
  const k = REV[zh];
  if (!k) return zh;
  const v = STR[k];
  return I18N_LANG === 'en' ? (v[1] || zh) : v[0];
}

function applyLang(lang) {
  I18N_LANG = lang;
  try { localStorage.setItem(I18N_LANG_KEY, lang); } catch (e) {}
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const s = STR[el.dataset.i18n]; if (s) el.textContent = I18N_LANG === 'en' ? (s[1] ?? s[0]) : s[0];
  });
  document.querySelectorAll('[data-i18n-ph]').forEach(el => {     // → placeholder
    const s = STR[el.dataset.i18nPh]; if (s) el.placeholder = I18N_LANG === 'en' ? (s[1] ?? s[0]) : s[0];
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {  // → title
    const s = STR[el.dataset.i18nTitle]; if (s) el.title = I18N_LANG === 'en' ? (s[1] ?? s[0]) : s[0];
  });
  const help = document.getElementById('rp-help');                // 帮助面板整块互换
  if (help) {
    if (!help.dataset.zh) help.dataset.zh = help.innerHTML;       // 首次备份 zh 原文
    help.innerHTML = I18N_LANG === 'en' ? I18N_HELP_EN : help.dataset.zh;
  }
  document.dispatchEvent(new CustomEvent('langchange'));          // app.js 侧监听重渲染动态区（见五.4）
  if (typeof applyAppearance === 'function') applyAppearance();   // 重渲染背景预设（p.name/p.en）
}
// 另需全局常量 I18N_HELP_EN（帮助 en 模板，结构见 A.5）
```

注意：i18t 是**整串精确反查**——`已清空任务：` 与 `已清空公共记忆：` 是不同条目；`（打回` 与 `次）` 是两个独立调用（含括号必须逐字进表）；` 个` / ` 条` 带前导空格，务必与调用处完全一致。

### A.2 STR 静态键全表（index.html 标注：key → zh → 行号）

| key | zh | 行 |
|---|---|---|
| brand.sub | 多Agent群聊协作 · 本机运行 | 297 |
| search.placeholder | 🔍 搜索会话（MVP 占位） | 299 |
| group.sessions | 会话 | 300 |
| btn.newRoom | ＋ 新建群聊 | 303 |
| btn.addExternal | ＋ 添加外部成员 | 304（复用 387） |
| title.files | 文件工作区 | 315 |
| title.members | 成员管理 | 316 |
| title.settings | 身份卡与模型设置 | 317 |
| title.help | 使用说明 | 318 |
| title.stopAll | 停止全部（P0 interrupt） | 319 |
| ph.draft | 输入消息，Enter 发送；输入 @ 弹出成员选择… | 324 |
| title.refs | 引用工作区文件 | 328 |
| btn.send | 发 送 | 331 |
| tab.files | 文件 | 339 |
| tab.task | 任务 | 340 |
| tab.members | 成员 | 341 |
| tab.identity | 身份卡 | 342 |
| tab.model | 模型 | 343 |
| tab.memory | 记忆 | 344 |
| tab.appearance | 外观 | 345 |
| tab.skills | 技能 | 346 |
| tab.help | 帮助 | 347 |
| files.workspace | 文件工作区 | 355 |
| btn.upload | ⬆ 上传 | 357 |
| files.previewHint | 点文件名预览 | 364 |
| btn.savePreview | 💾 保存 | 366 |
| ph.filePreview | 文件内容预览与编辑（保存走乐观锁，冲突会提示刷新） | 368 |
| grp.task | 任务 · CEO 编排闭环 | 374 |
| lbl.taskGoal | 任务目标（CEO 拆解为排产单，先给你确认） | 375 |
| ph.taskGoal | 如：调研竞品并输出对比报告 | 376 |
| btn.issueTask | 🎯 下达任务 | 377 |
| grp.taskProgress | 任务进度 | 378 |
| btn.tasksClear | 🧹 清空已完成任务 | 379 |
| hint.taskFlow | 流程：下达 → CEO 拆解 → 你确认 → 按依赖派发排产单 → 交付 → 验收/打回 → 汇总沉淀记忆。互聊超限自动熔断 @你裁决。 | 381 |
| grp.members | 成员 | 385 |
| grp.membersSub | （右侧下拉换绑身份卡） | 385 |
| grp.quickOps | 快捷操作 | 388 |
| btn.archiveNow | 🧹 立即归档清理（Agent B 执行） | 389 |
| btn.stopAllFull | ■ 停止全部（P0 interrupt） | 390 |
| hint.members | P0 生效会取消所有 Agent 正在进行的生成。互聊不设上限，聊天记录由 Agent B 定时总结归档清理。 | 391 |
| grp.identityList | 身份卡列表 | 395 |
| btn.newIdentity | ＋ 新建身份卡 | 397 |
| grp.editor | 编辑器 | 398 |
| lbl.idLabel | 显示标签 label | 399 |
| ph.idLabel | 如：调研员 | 400 |
| lbl.idPersona | 风格 persona | 401 |
| ph.idPersona | 严谨、简洁、不懂就问 | 402 |
| lbl.idResp | 职责 responsibilities（顿号分隔） | 403 |
| ph.idResp | 检索资料、写调研笔记 | 404 |
| grp.tools | 工具白名单 tools_allow | 405 |
| btn.toolsRec | ⚡ 一键：文件+技能 | 407 |
| btn.clear | 清空 | 408 |
| btn.save | 保存 | 412（复用 570） |
| btn.del | 删除 | 413 |
| hint.identity | 互聊轮次自 5.5 步起不设上限（Agent B 定时归档清理聊天记录防存储膨胀）。保存后可在「成员」页为 Agent 换绑。 | 415 |
| grp.model | LLM · OpenAI 兼容端点 | 419 |
| ph.llmUrl | https://api.example.com/v1 | 421 |
| ph.llmKey | sk-... | 423 |
| lbl.modelName | 模型名 | 424 |
| ph.llmModel | gpt-4o-mini / deepseek-chat … | 425 |
| btn.saveLlm | 保存并连接 | 426 |
| hint.modelTest | 保存后会自动向端点发一条测试消息验证连通性。 | 427 |
| hint.model | 配置保存后自动发一条测试消息校验连通性；配置存本机数据库（重启不丢，不出本机）；V2 迁移加密存储与多模型插槽。 | 428 |
| grp.memory | 向量记忆 · 本地存储 | 432 |
| btn.memClear | 🗑 清空公共记忆 | 435 |
| hint.memory | 公共记忆：任务验收通过后沉淀；私有记忆：Agent 交付时写入、仅本人可读。检索 top-k 自动注入 Agent 上下文并标注来源时间。闲聊不入库。每条记忆可单独删除，也可一键清空公共记忆。 | 436 |

| grp.lang | 语言 / Language | 440 |
| grp.bg | 聊天背景 | 445 |
| lbl.bgCustom | 自定义背景图（本地图片，存浏览器不外传） | 447 |
| btn.bgImage | 🖼 选择图片 | 449 |
| btn.bgReset | 恢复默认 | 451 |
| grp.opacity | 透明度 | 453 |
| lbl.mask | 背景遮罩浓度（越高文字越清晰）： | 454 |
| lbl.bub | 气泡不透明度： | 456 |
| grp.fx | 动效 | 458 |
| lbl.ripple | 点击波纹与气泡弹跳 | 460 |
| hint.appearance | 设置保存在本浏览器（localStorage），每个浏览器独立；图片不离开本机。 | 462 |
| grp.skills | 内部技能库 · 供群里 Agent 使用 | 466 |
| hint.skillsIntro | 技能 = 写法规范 / 模板 / 工作流（md 文档）。Agent 绑定含 skills.* 白名单的身份卡后，可在对话中自查技能并照做。 | 467 |
| grp.skillsImport | 从本机技能库导入 | 469 |
| skills.src.zcode | ZCode 技能库（d:/ai-use/.zcode/skills） | 472 |
| skills.src.trae | TRAE 技能库（.trae-cn/skills） | 473 |
| skills.src.builtin | TRAE 内置技能（.trae-cn/builtin_skills） | 474 |
| btn.import | 导入 | 476 |
| grp.skillsEdit | 添加 / 更新技能 | 478 |
| lbl.skillName | 技能名（文字/数字/连字符，可中文，如 周报模板） | 479 |
| lbl.skillContent | 技能内容（Markdown：用途 / 工作流 / 模板 / 要求） | 481 |
| ph.skillContent | # 技能名\n\n用途：…\n## 工作流\n1. …\n## 模板\n…\n## 要求\n- … | 482 |
| btn.saveSkill | 保存技能 | 484 |
| btn.importMd | 📥 导入 .md 文件 | 485 |
| hint.skills | 导入：可选多个 .md 文件，文件名即技能名（非法字符自动转换，同名覆盖）；列表中每个技能可导出为 .md 分享。 | 488 |
| m.roomTitle | 新建群聊 | 525 |
| lbl.roomName | 群聊名称 | 526 |
| ph.roomName | 如：项目攻坚群 | 527 |
| lbl.roomPicks | 选择加入的成员（可多选） | 528 |
| btn.roomCreate | 创建并进入 | 531 |
| btn.cancel | 取消 | 532（复用 550/571） |
| hint.roomModal | 文件工作区 / 任务 / 记忆按群聊独立隔离；外部成员被拉入后可用其网关工具传 room_id 在该群收发。 | 534 |
| m.extTitle | 添加外部成员 | 542 |
| lbl.extName | 成员名称（如：开发员·外部） | 543 |
| ph.extName | 开发员·外部 | 544 |
| lbl.extBind | 绑定身份卡（可稍后换绑） | 545 |
| opt.noBind | — 暂不绑定 — | 547 |
| btn.extCreate | 创建并发放令牌 | 549 |
| m.extResult | ✅ 成员已创建 · 令牌仅显示这一次 | 553 |
| hint.token | ROOM_TOKEN（重发将使旧令牌失效）： | 554 |
| hint.cfgHttp | 接入配置 A · HTTP 方式（适用于支持 MCP HTTP 的 Agent，填入其 MCP 服务器配置）： | 556 |
| hint.cfgStdio | 接入配置 B · 命令行方式（适用于仅支持 stdio MCP 的 Agent，启动命令如下）： | 558 |
| btn.copyAll | 📋 复制全部配置 | 561 |
| btn.done | 完成 | 562 |
| lbl.bindPick | 选择身份卡（选「解绑」恢复未绑定，按钮将变回复制令牌） | 567 |

> 自校验：写完 STR 后对 index.html 重跑 `Grep "data-i18n" frontend/index.html`（实测 114 处属性），与 STR 键逐一对账；若差 1 处以上表有笔误，以 index.html 实际标注为准。`ph.skillContent` 的 zh 串含换行，进 STR 时与 DOM 中 placeholder 实际值逐字节一致（含换行形式），建议运行时取 `元素.placeholder` 核对一次。

### A.3 动态串（app.js 既有 i18t() 调用点，实测约 70 行）

规则：这些行**调用点本身不需要改动**（旧 app.js 已大量使用 `i18t('中文整串')`，REV 按整串精确反查）；但每个传入的 zh 整串必须在 STR 中有对应条目，差一个空格/标点就回退中文。个别行若实际是 `I18N_LANG === 'en' ? … : …` 三元而非 i18t，就地改为 i18t 包裹并把 zh 串入表。完成后用 `Grep -n "i18t\(" frontend/app.js` 逐行与本表 + STR 对账，要求 100% 覆盖。

| app.js 行 | zh 整串（须入 STR） | 备注 |
|---|---|---|
| 81 | 生成中 | 流式占位 |
| 198/211/215 | ● 已连接 ／ ● 已断开，3 秒重连 | setChip 入参 |
| 253/733 | 【引用工作区文件】 | 消息前缀 |
| 276 | 外部在线 ／ 外部离线 | 两个串 |
| 277 | 内置 | |
| 286 | 绑定身份卡 | |
| 287 | 复制令牌 | |
| 288 | 删除成员 | |
| 295 | 未绑定身份卡 | |
| 321 | 删除成员？ | confirm |
| 324 | 已删除成员： | toast 前缀 |
| 334 | 绑定身份卡 ·  | 拼接前缀，注意尾部空格，与 l.286 是两个键 |
| 335 | — 解绑 — | |
| 357 | 身份卡已更新。 | |
| 495/814 | LLM 已配置 ／ LLM 未配置 | chip 文案 |
| 581 | 人类 | 发送者名 |
| 584 | （暂无文件；Agent 交付物与人类上传都会出现在这里） | |
| 591 | 删除文件？ | confirm |
| 596 | 点文件名预览 | |
| 620 | 已上传： | toast 前缀 |
| 636 | 版本冲突： ／ ，已为你刷新内容，请重新保存。 | 两个独立调用，en 语法按前后拼接写 |
| 642 | 已保存： | |
| 653-656 | 待派发／执行中／已验收／已打回 ＋ 待确认／执行中／已熔断·待裁决／已完成／已作废 | SUB_CHIP/TASK_ST 字典值，经 subChip()/taskSt() → i18t；「执行中」两处共用一条 STR |
| 666 | （暂无任务；在上方填写目标并下达，CEO 将拆解为排产单） | |
| 672 | 交付： | |
| 673 | 验收： | |
| 675 | （打回 ＋ 次） | 两个独立片段，en 需能拼接成句 |
| 679 | ✓ 确认开工 | |
| 680 | 作废 | |
| 682 | 继续执行 | |
| 683 | 终止 | |
| 685 | 删除该任务记录 | |
| 687 | 状态： | |
| 693 | 删除该任务记录？（群内消息保留） | confirm |
| 695 | 删除失败 | |
| 704 | 任务已作废。／已恢复执行，CEO 按依赖继续派发。／已确认开工，CEO 按依赖派发排产单。 | 三条 toast |
| 719 | 清空全部已结束（已完成/已作废）的任务记录？（群内消息保留） | confirm |
| 724 | 已清空任务： ＋ 个 | 「 个」带前导空格，逐字入表 |
| 730 | 请先填写任务目标 | |
| 739 | 任务已下达，CEO 正在拆解… | |
| 748 | 公共记忆 ／ 条 ／ 私有记忆 | 「 条」带前导空格 |
| 753 | 删除 | |
| 755 | （暂无记忆；任务验收通过后自动沉淀） | |
| 758 | 该条记忆无 id，无法删除 | |
| 759 | 删除这条记忆？ | confirm |
| 764 | 已删除该条记忆。 | |
| 768 | 清空本群聊的全部公共记忆？（私有记忆不受影响） | confirm |
| 773 | 已清空公共记忆： ＋ 条 | |
| 810 | 已切换到： | toast 前缀 |
| 858 | （暂无技能；在下方添加、导入 .md 文件，或参考内置示例） | |
| 860 | 删除技能？ | confirm |
| 863 | 技能已删除 | |
| 897 | 技能已保存： | |
| 903 | 请选择技能来源 | |
| 904 | 正在从本机技能库导入… | |
| 909 | 导入失败 | |
| 910 | 导入完成： ＋ 个 ＋ 跳过 | |
| 925 | ；失败 N 个： | **硬编码未包 i18t**，可选包裹后入 STR |
| 979 | 图片请小于 6MB | **硬编码未包 i18t**，同上 |
| 985 | 背景图已应用（仅存本浏览器）。 | |
| 986 | 图片过大无法本地存储，请换小图。 | |
| 993 | 外观已恢复默认。 | |
| 1036 | 立即归档清理本群聊？（自上次归档以来的聊天将总结进公共记忆并清理原文） | confirm |
| 1041 | 归档完成： ＋ 条 | |
| 1051 | （工作区暂无文件；先在「文件」面板上传或让 Agent 交付） | |
| 1053 | 点击选择要引用的文件（可多选） | |

### A.4 en 译文对照表

用法：先读旧 `frontend/i18n.js` 的 `I18N_EN`，旧串已有译法优先复用（措辞与旧版一致）；旧表查不到的按下表新增。zh 是 REV 反查键，**必须与调用点逐字节一致**。同 zh 串只留一条 STR（如「执行中」两字典共用）。

| zh 整串 / 键 | en |
|---|---|
| 生成中 | Generating… |
| ● 已连接 | ● Connected |
| ● 已断开，3 秒重连 | ● Disconnected, retrying in 3s |
| 【引用工作区文件】 | [Workspace file] |
| 外部在线 | External online |
| 外部离线 | External offline |
| 内置 | Built-in |
| 绑定身份卡 | Bind identity card |
| 绑定身份卡 ·  | Bind identity card ·  |
| 复制令牌 | Copy token |
| 删除成员 | Remove agent |
| 未绑定身份卡 | No identity card bound |
| 删除成员？ | Remove this agent? |
| 已删除成员： | Removed agent:  |
| — 解绑 — | — Unbind — |
| 身份卡已更新。 | Identity card updated. |
| LLM 已配置 | LLM configured |
| LLM 未配置 | LLM not configured |
| 人类 | Human |
| （暂无文件；Agent 交付物与人类上传都会出现在这里） | (No files yet; agent deliverables and your uploads will appear here) |
| 删除文件？ | Delete this file? |
| 点文件名预览 | Click a file name to preview |
| 已上传： | Uploaded:  |
| 版本冲突： | Version conflict:  |
| ，已为你刷新内容，请重新保存。 | — refreshed to the latest; please save again. |
| 已保存： | Saved:  |
| 待派发 | Pending |
| 执行中 | Running |
| 已验收 | Accepted |
| 已打回 | Rejected |
| 待确认 | Awaiting confirm |
| 已熔断·待裁决 | Paused · awaiting ruling |
| 已完成 | Done |
| 已作废 | Discarded |
| （暂无任务；在上方填写目标并下达，CEO 将拆解为排产单） | (No tasks yet; set a goal above and issue it — CEO will break it into work orders) |
| 交付： | Deliverables:  |
| 验收： | Acceptance:  |
| （打回 | (rejected  |
| 次） |  times) |
| ✓ 确认开工 | ✓ Approve & start |
| 作废 | Discard |
| 继续执行 | Resume |
| 终止 | Terminate |
| 删除该任务记录 | Delete task record |
| 状态： | Status:  |
| 删除该任务记录？（群内消息保留） | Delete this task record? (group messages are kept) |
| 删除失败 | Delete failed |
| 任务已作废。 | Task discarded. |
| 已恢复执行，CEO 按依赖继续派发。 | Resumed; CEO keeps dispatching by dependency. |
| 已确认开工，CEO 按依赖派发排产单。 | Approved; CEO dispatches work orders by dependency. |
| 清空全部已结束（已完成/已作废）的任务记录？（群内消息保留） | Clear all finished (done/discarded) task records? (group messages are kept) |
| 已清空任务： | Cleared tasks:  |
| 个 |  item(s) |
| 请先填写任务目标 | Set a task goal first |
| 任务已下达，CEO 正在拆解… | Task issued; CEO is planning… |
| 公共记忆 | Shared memory |
| 条 |  item(s) |
| 私有记忆 | Private memory |
| 删除 | Delete |
| （暂无记忆；任务验收通过后自动沉淀） | (No memories yet; distilled after task acceptance) |
| 该条记忆无 id，无法删除 | This memory has no id; cannot delete |
| 删除这条记忆？ | Delete this memory? |
| 已删除该条记忆。 | Memory deleted. |
| 清空本群聊的全部公共记忆？（私有记忆不受影响） | Clear ALL shared memory of this room? (private memory is unaffected) |
| 已清空公共记忆： | Cleared shared memories:  |
| 已切换到： | Switched to:  |
| （暂无技能；在下方添加、导入 .md 文件，或参考内置示例） | (No skills yet; add below, import .md files, or see the built-in sample) |
| 删除技能？ | Delete this skill? |
| 技能已删除 | Skill deleted |
| 技能已保存： | Skill saved:  |
| 请选择技能来源 | Pick a skill source first |
| 正在从本机技能库导入… | Importing from local skill library… |
| 导入失败 | Import failed |
| 导入完成： | Imported:  |
| 跳过 | skipped |
| ；失败 N 个： | ; N failed:  |
| 图片请小于 6MB | Image must be under 6MB |
| 背景图已应用（仅存本浏览器）。 | Background applied (stored in this browser only). |
| 图片过大无法本地存储，请换小图。 | Image too large to store locally; try a smaller one. |
| 外观已恢复默认。 | Appearance reset to defaults. |
| 立即归档清理本群聊？（自上次归档以来的聊天将总结进公共记忆并清理原文） | Archive & clean this room now? (chats since the last archive will be summarized into shared memory and pruned) |
| 归档完成： | Archived:  |
| （工作区暂无文件；先在「文件」面板上传或让 Agent 交付） | (Workspace is empty; upload via the Files panel or let an agent deliver) |
| 点击选择要引用的文件（可多选） | Click files to reference (multi-select) |
| grp.skillsImport | Import from local skill library |
| skills.src.zcode | ZCode skill library (d:/ai-use/.zcode/skills) |
| skills.src.trae | TRAE skill library (.trae-cn/skills) |
| skills.src.builtin | TRAE built-in skills (.trae-cn/builtin_skills) |
| btn.import | Import |
| files.previewHint | Click a file to preview |
| hint.modelTest | After saving, a test message is sent to the endpoint to verify connectivity. |

六处**无 data-i18n 的静态文案**（applyLang 末尾定向处理或并入 langchange 监听，en 如下；zh 已在 index.html）：

| id | index.html 行 | zh 初始 | en |
|---|---|---|---|
| room-name | 311 | 主房间 | Main Room |
| ws-chip | 312 | ● 连接中… | ● Connecting… |
| llm-chip | 313 | LLM 未配置 | LLM not configured |
| typing | 322 | Agent A 正在输入… | Agent A is typing… |
| scope-tip | 329 | 广播模式：全体 Agent 可见可回 | Broadcast mode: visible to and replyable by all agents |
| bind-title | 566 | 绑定身份卡 | Bind identity card |

注：`typing` 与 `scope-tip` 在 app.js 中零引用（纯静态）→ applyLang 直接 textContent 互换；`room-name`（l.797 动态覆盖）、`bind-title`（l.334 动态覆盖）、`ws-chip`（setChip）、`llm-chip`（l.495/814）以动态重设为准，applyLang 只兜底初始态。

### A.5 I18N_HELP_EN 模板（对照 index.html l.491-517 的 zh 块逐条翻译，结构必须一一对应：.grp 标题 + .help-item）

```js
const I18N_HELP_EN = `
      <div class="grp">🚀 Quick Start</div>
      <div class="help-item"><b>Send messages</b>: type in the composer and press Enter (Shift+Enter for a new line). Default is <b>broadcast</b> — every agent sees and may reply. Type <code>@</code> to pick members for a <b>direct message</b> (only the mentioned agents respond).</div>
      <div class="help-item"><b>Issue tasks</b>: open the Tasks panel → enter a goal → 🎯 Issue. The CEO breaks it into a task map for your <b>confirmation</b>; after approval it dispatches work orders by dependency, agents deliver, acceptance runs automatically (rejections get redone), and you get a summary when everything is done.</div>
      <div class="help-item"><b>File collaboration</b>: upload / preview / edit / delete files in the Files panel; agents read and write the same workspace via fs tools, announce deliverables in the room, and 📎 attachments jump straight to preview. Saving uses <b>optimistic locking</b> — on conflict you'll be prompted to refresh the latest version.</div>
      <div class="help-item"><b>Emergency stop</b>: the ⏹ button in the top bar or "Stop all" in the Members panel = P0 interrupt; it immediately cancels all in-flight agent generation.</div>

      <div class="grp" style="margin-top:14px;">✨ Features</div>
      <div class="help-item"><b>Room members</b>: two built-in agents stream replies in parallel — <b>Agent A · User Service Assistant</b> (Q&A, prompt help, guidance, dispatch supervision) and <b>Agent B · Room Butler</b> (content governance, memory management, privilege supervision, scheduled archiving). External agents join via the MCP gateway and collaborate on equal footing.</div>
      <div class="help-item"><b>Identity cards</b>: define an agent's label, persona, responsibilities and <b>tool whitelist</b> (fs.read / fs.write / fs.list / memory.query etc. — non-whitelisted tool calls are rejected). Bind / rebind in the Members panel: external members always have a "Bind identity card" button, plus "Copy token" for onboarding while unbound.</div>
      <div class="help-item"><b>External members</b>: "＋ Add external member" issues a one-time token and MCP connection config (copyable); while unbound you can re-issue via "Copy token" (the old token is invalidated instantly); ✕ removes a member.</div>
      <div class="help-item"><b>Tasks panel</b>: live task status (awaiting confirm / running / paused / done) plus per-subtask progress chips; when circuit-broken you can "Resume" or "Terminate".</div>
      <div class="help-item"><b>Vector memory</b>: shared memory (distilled after task acceptance, visible to all) and each agent's private memory (readable only by its owner) are physically isolated; while working, agents auto-retrieve relevant memories into context with source timestamps. <b>Agent-to-agent chat is unlimited</b>; Agent B periodically summarizes and archives chat logs into shared memory and prunes the originals, so key messages (files / tasks) are kept forever while pure chatter gets archived.</div>
      <div class="help-item"><b>Model config</b>: fill in an OpenAI-compatible endpoint (Base URL / API Key / model) in the Models panel to hook up a real LLM; on save a <b>test message verifies connectivity</b> (latency and reply shown). Without config the whole system runs in <b>placeholder mode</b> (full pipeline, demo-friendly).</div>
      <div class="help-item"><b>Multiple rooms</b>: "＋ New room" in the left rail creates a room and picks members (built-in / external); each room has its own message feed, file workspace, tasks and memory. Click a session in the left rail to switch.</div>
      <div class="help-item"><b>Skill library</b>: maintain writing standards / templates / workflows (markdown docs) for agents in the Skills panel. Bind an identity card whose whitelist includes skills.list / skills.read and the agent can look up skills on its own and follow them.</div>

      <div class="grp" style="margin-top:14px;">❓ FAQ</div>
      <div class="help-item"><b>Q: Replies are all "placeholder"?</b><br>A: No LLM is configured. Connect an OpenAI-compatible endpoint in the Models panel.</div>
      <div class="help-item"><b>Q: Saving a file reports a version conflict?</b><br>A: Someone (or an agent) updated the file while you were editing. The system has refreshed to the latest version — just save again; that's optimistic locking preventing overwrites.</div>
      <div class="help-item"><b>Q: Where did earlier chat messages go?</b><br>A: Archived on schedule by Agent B — summaries are distilled into shared memory in the Memory panel and originals pruned to save storage. Key messages (tasks, acceptance) are kept forever.</div>
      <div class="help-item"><b>Q: Task stuck at "Paused · awaiting ruling"?</b><br>A: Agent-to-agent chat exceeded the limit (default 12) during execution; the system pauses and waits for your ruling: pick "Resume" or "Terminate" in the Tasks panel.</div>
      <div class="help-item"><b>Q: How do I onboard a local agent / create a room?</b><br>A: Members panel → ＋ Add external member → copy the token & connection config from the popup, then paste it into your agent the way it supports (HTTP config for MCP-HTTP agents; the stdio bridge command for command-line-only MCP agents). Once connected it can chat, read/write files and take tasks through the gateway.</div>

      <div class="grp" style="margin-top:14px;">🗺️ Roadmap</div>
      <div class="hint">Shipped: group chat → identity cards / mentions / P0 → MCP gateway (external agents) → file workspace + WeChat-style UI → CEO orchestration loop + vector memory + circuit breaker. In progress: external agents taking work orders, second-layer gateway permission checks, unattended task intake.</div>`;
```

## 五、任务 B：app.js 改造（步骤 3，改动极小）

1096 行 app.js **只动以下四类点**，其余逻辑/API 对接/boot 序列一律不碰。动手前先 Read 对应行原文。

### B1. 深色化三处（唯一行为级视觉修改，均在 l.925-989 区）

| 位置 | 现状 | 改为 |
|---|---|---|
| l.946 applyAppearance 内遮罩 | `rgba(246,246,248,x)` | `rgba(13,15,18,x)`（--bg 同色） |
| l.969 renderBgPresets 内 default 色块 | `background:#f6f6f8` | `background:#151a21;border:1px solid #2a303a` |
| l.931-936 BG_PRESETS 浅色渐变 | mist/dawn/ink 为浅色 | 深色渐变：mist → `linear-gradient(135deg,#10141b 0%,#171e29 100%)`；dawn → `linear-gradient(135deg,#1a1206 0%,#2a1c0a 100%)`（琥珀暖调）；ink → `linear-gradient(135deg,#0b0c0f 0%,#12141a 100%)`；default `css:''` 保留 |

约束：preset 键名、p.name/p.en 双语机制（l.969 `I18N_LANG === 'en' && p.en ? p.en : p.name`）不得改。

### B2. 新增 langchange 监听（applyLang 会 dispatch，目前 app.js 无监听器）

在全局区（如 l.1081 语言接线附近）新增：

```js
document.addEventListener('langchange', () => {
  if (typeof renderRooms   === 'function') renderRooms();   // 左栏会话 + #room-name
  if (typeof renderMembers === 'function') renderMembers(); // 成员卡/绑定按钮
  if (typeof renderFiles   === 'function') renderFiles();   // 文件列表
  if (typeof renderTasks   === 'function') renderTasks();   // 任务卡 + SUB/TASK chips
  if (typeof renderMemory  === 'function') renderMemory();  // 记忆列表
  if (typeof renderSkills  === 'function') renderSkills();  // 技能列表
  if (LAST_CHIP && typeof setChip === 'function') setChip(LAST_CHIP); // 见 B2b
});
```

B2b：给 setChip 加一行缓存（函数体首行 `LAST_CHIP = 传入文本;`，模块级 `let LAST_CHIP = null;`），其余逻辑不动。#llm-chip 同理：l.495/814 设置处缓存最近文本，监听里重设；若拿不到状态，最低要求 = 切语言后下一次状态变化自动以新语言显示。

### B3. 六处无 data-i18n 静态文案 → applyLang 内定向处理（放在 dispatchEvent 之前）

```js
const STATIC_I18N = {
  'typing':    ['Agent A 正在输入…', 'Agent A is typing…'],
  'scope-tip': ['广播模式：全体 Agent 可见可回', 'Broadcast mode: visible to and replyable by all agents'],
  'room-name': ['主房间', 'Main Room'],
  'ws-chip':   ['● 连接中…', '● Connecting…'],
  'llm-chip':  ['LLM 未配置', 'LLM not configured'],
  'bind-title':['绑定身份卡', 'Bind identity card'],
};
for (const [id, s] of Object.entries(STATIC_I18N)) {
  const el = document.getElementById(id);
  if (el && el.textContent === (I18N_LANG === 'en' ? s[0] : s[1])) el.textContent = I18N_LANG === 'en' ? s[1] : s[0];
}
```

关键：**仅当当前文本恰好等于另一语言的初始值时才替换**——动态覆盖（room-name 群名、ws-chip 已连接、llm-chip 已配置、bind-title 带标签）后不匹配即跳过，天然防误伤。

### B4. 语言接线三行逐字保留（不改名、不挪位、不删）

- l.1081 `if (e.target && e.target.id === 'lang-select') applyLang(e.target.value)`
- l.1086 `applyLang(localStorage.getItem(I18N_LANG_KEY) || 'zh')`
- l.1099 `$('lang-select').value = I18N_LANG`

### B5. 可选加分

l.925「；失败 N 个：」与 l.979「图片请小于 6MB」包上 i18t()（zh 串用 A.4 表）。不包也只影响 en 下两处小文案。

### B6. 禁改清单

i18t() 各调用点（除 B5 两处可选）、API 全集（记忆文档 3.7）、WS 协议（3.8）、boot 序列（3.4）、SUB_CHIP/TASK_ST 字典结构与键名、全部函数名与 id。

## 六、任务 C：联调走查（步骤 4，验收门）

1. 启动后端（后端零改动）：项目根目录运行 `backend\.venv\Scripts\python.exe backend\main.py`，浏览器开 `http://127.0.0.1:8899`（FastAPI StaticFiles 同端口托管，无需另起前端服务；index.html 已裸引 `src="i18n.js"`/`src="app.js"`，版本注入中间件自动加参）。
2. 硬刷新 Ctrl+F5。
3. 走查单：
   - 视觉：深色统一（--bg #0d0f12 / 面板 #14171c / 卡片 #191d23），琥珀 #f0a63c = 人类操作、teal #3ecfb2 = 系统侧、JetBrains Mono = 状态数据、右侧竖向图标栏；
   - 功能回归：广播/@定向发消息、任务下达→CEO 拆解→确认→派发→交付→验收/打回、文件上传/预览/编辑/乐观锁冲突、记忆增删清、身份卡 CRUD/换绑、外部成员令牌与配置弹窗、技能导入导出、外观设置（背景/透明度/动效）、P0 急停；
   - i18n：zh 默认完整；切 en **无中文残留**（静态 110 键 + A.3 全部动态串 + confirm 弹窗 + SUB_CHIP/TASK_ST chips + I18N_HELP_EN 四组结构一一对应 + 六处静态定向处理）；切回 zh 还原；刷新后语言保持（localStorage['aroom-lang']）。
4. 验收线（不达标不算完）：en 态逐面板目检，发现任何中文残留 → 多半是 STR 的 zh 键与调用点整串不一致（空格/标点/省略号字符差异），修正后复测。

## 七、给 ZCode 的启动提示（复制即可）

> 读 `d:\ai-use\projects\agent-room\docs\frontend-redesign-handoff.md`（任务全量素材）与 `docs\frontend-redesign-memory.md`（机制规格与分步验收）。按顺序执行任务 A → B → C：先整文件重写 `frontend/i18n.js`（A.1 骨架 + A.2/A.3 全部 zh 键 + A.4 en 译 + A.5 I18N_HELP_EN）；再按第五节对 `frontend/app.js` 做四类小改（深色化三处 / langchange 监听 / 六处静态定向 / 保接线三行）；最后按第六节启动走查，验收线 = 切 en 无中文残留 + 功能全回归。铁律：不动后端；index.html 已完成不再改（除非走查发现标注笔误）；动手前先 Read 对应源文件原文。

—— 交接文档完 ——
