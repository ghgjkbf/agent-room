/* i18n：界面语言切换（中文/English）。
   策略：静态 HTML 按「文本节点精确匹配」替换（结构无关，无需标注）；
   placeholder/title 属性按映射；帮助面板整块模板切换；动态字符串用 t()。
   聊天内容（Agent 回复、后端系统消息）语言跟随对话本身，不做翻译。 */

const I18N_LANG_KEY = 'aroom-lang';
let I18N_LANG = localStorage.getItem(I18N_LANG_KEY) || 'zh';

/* zh → en 静态字典（文本节点 / placeholder 共用） */
const I18N_EN = {
  /* 左栏 / 顶栏 */
  '会话': 'Sessions',
  '＋ 新建群聊': '＋ New Group',
  '＋ 添加外部成员': '＋ Add External Agent',
  '🔍 搜索会话（MVP 占位）': '🔍 Search sessions (placeholder)',
  '多Agent群聊协作 · 本机运行': 'Multi-agent group chat · runs locally',
  '● 连接中…': '● Connecting…',
  'LLM 未配置': 'LLM not configured',
  '主房间': 'Main Room',
  /* tabs */
  '文件': 'Files', '任务': 'Tasks', '成员': 'Members', '身份卡': 'Identity',
  '模型': 'Model', '记忆': 'Memory', '外观': 'Appearance', '技能': 'Skills', '帮助': 'Help',
  /* 文件面板 */
  '文件工作区 ·': 'Workspace ·',
  '⬆ 上传': '⬆ Upload',
  '点文件名预览': 'Click a file to preview',
  /* 任务面板 */
  '任务 · CEO 编排闭环': 'Tasks · CEO orchestration loop',
  '任务目标（CEO 拆解为排产单，先给你确认）': 'Goal (CEO turns it into a work plan for your confirmation)',
  '如：调研竞品并输出对比报告': 'e.g. Research competitors and produce a comparison report',
  '🎯 下达任务': '🎯 Issue task',
  '任务进度': 'Progress',
  '流程：下达 → CEO 拆解 → 你确认 → 按依赖派发排产单 → 交付 → 验收/打回 → 汇总沉淀记忆。互聊超限自动熔断 @你裁决。':
    'Flow: issue → CEO plans → you confirm → dispatch by dependency → delivery → review/reject → summary into memory. Auto circuit-break @you on chat overload.',
  /* 成员面板 */
  '成员 ·': 'Members ·',
  '（右侧下拉换绑身份卡）': '(switch identity via dropdown)',
  '＋ 添加外部成员（TRAE / ZCode）': '＋ Add External Agent',
  '快捷操作': 'Quick actions',
  '■ 停止全部（P0 interrupt）': '■ Stop all (P0 interrupt)',
  'P0 生效会取消所有 Agent 正在进行的生成。互聊不设上限，聊天记录由 Agent B 定时总结归档清理。':
    'P0 cancels all in-flight agent generation. Chat is uncapped; Agent B archives and prunes history on schedule.',
  /* 身份卡面板 */
  '身份卡列表': 'Identity cards',
  '＋ 新建身份卡': '＋ New card',
  '编辑器': 'Editor',
  '显示标签 label': 'Display label',
  '如：调研员': 'e.g. Researcher',
  '风格 persona': 'Persona',
  '严谨、简洁、不懂就问': 'rigorous, concise, asks when unsure',
  '职责 responsibilities（顿号分隔）': 'Responsibilities (comma separated)',
  '检索资料、写调研笔记': 'collect material, write research notes',
  '工具白名单 tools_allow': 'Tool allowlist (tools_allow)',
  '⚡ 一键：文件+技能': '⚡ Quick: files + skills',
  '清空': 'Clear',
  '💾 保存': '💾 Save',
  '删除': 'Delete',
  '互聊轮次自 5.5 步起不设上限（Agent B 定时归档清理聊天记录防存储膨胀）。保存后可在「成员」页为 Agent 换绑。':
    'Chat turns are uncapped since 5.5 (Agent B archives history to bound storage). Rebind agents on the Members tab after saving.',
  /* 模型面板 */
  'LLM · OpenAI 兼容端点': 'LLM · OpenAI-compatible endpoint',
  'Base URL': 'Base URL',
  'API Key': 'API Key',
  '模型名': 'Model name',
  '保存并连接': 'Save & connect',
  '配置保存后自动发一条测试消息校验连通性；配置存本机数据库（重启不丢，不出本机）；V2 迁移加密存储与多模型插槽。':
    'Saving auto-sends a test message to verify connectivity. Config is stored in the local database (survives restarts, never leaves this machine); encrypted storage & multi-model slots planned for V2.',
  /* 外观面板 */
  '聊天背景': 'Chat background',
  '自定义背景图（本地图片，存浏览器不外传）': 'Custom image (stored in your browser only)',
  '🖼 选择图片': '🖼 Choose image',
  '恢复默认': 'Reset',
  '透明度': 'Transparency',
  '背景遮罩浓度（越高文字越清晰）：': 'Backdrop veil (higher = clearer text):',
  '气泡不透明度：': 'Bubble opacity:',
  '动效': 'Motion',
  '点击波纹与气泡弹跳': 'Click ripples & bubble bounce',
  '设置保存在本浏览器（localStorage），每个浏览器独立；图片不离开本机。':
    'Settings live in this browser (localStorage); images never leave your machine.',
  '语言 / Language': '语言 / Language',
  /* 技能面板 */
  '内部技能库 · 供群里 Agent 使用': 'Skill library · for agents in the room',
  '技能 = 写法规范 / 模板 / 工作流（md 文档）。Agent 绑定含 skills.* 白名单的身份卡后，可在对话中自查技能并照做。':
    'Skills = conventions / templates / workflows (md docs). Agents with skills.* on their allowlist can look them up mid-chat and follow them.',
  '添加 / 更新技能': 'Add / update skill',
  '技能名（文字/数字/连字符，可中文，如 周报模板）': 'Skill name (letters/digits/hyphens, CJK ok, e.g. weekly-report)',
  '技能内容（Markdown：用途 / 工作流 / 模板 / 要求）': 'Skill content (Markdown: purpose / workflow / template / rules)',
  '保存技能': 'Save skill',
  '📥 导入 .md 文件': '📥 Import .md files',
  '导入：可选多个 .md 文件，文件名即技能名（非法字符自动转换，同名覆盖）；列表中每个技能可导出为 .md 分享。':
    'Import one or more .md files; the filename becomes the skill name (sanitized, overwrite on clash). Export any skill from the list to share it.',
  /* 记忆面板 */
  '向量记忆 · 本地存储': 'Vector memory · local storage',
  '公共记忆：任务验收通过后沉淀；私有记忆：Agent 交付时写入、仅本人可读。检索 top-k 自动注入 Agent 上下文并标注来源时间。闲聊不入库。':
    'Public memory settles after task acceptance; private memory is written on agent delivery and readable only by its owner. Top-k hits are injected into agent context with timestamps. Chit-chat is never stored.',
  /* 帮助面板标题（条目走整块模板） */
  '🚀 快速上手': '🚀 Quick start',
  '✨ 功能一览': '✨ Features',
  '❓ 常见问题': '❓ FAQ',
  '🗺️ 路线图': '🗺️ Roadmap',
  /* 输入区 */
  '输入消息，Enter 发送；输入 @ 弹出成员选择…': 'Type a message; Enter to send, @ to mention…',
  '发 送': 'Send',
  '广播模式：全体 Agent 可见可回': 'Broadcast: every agent can see & reply',
  /* 弹窗：添加外部成员 */
  '添加外部成员': 'Add external agent',
  '成员名称（如：开发员·外部）': 'Agent name (e.g. Dev·external)',
  '开发员·外部': 'Dev·external',
  '绑定身份卡（可稍后换绑）': 'Bind identity card (can rebind later)',
  '— 暂不绑定 —': '— Not bound —',
  '创建并发放令牌': 'Create & issue token',
  '取消': 'Cancel',
  '✅ 成员已创建 · 令牌仅显示这一次': '✅ Agent created · token shown only once',
  'ROOM_TOKEN（重发将使旧令牌失效）：': 'ROOM_TOKEN (re-issuing revokes the old one):',
  '接入配置 A · HTTP 方式（适用于支持 MCP HTTP 的 Agent，填入其 MCP 服务器配置）：':
    'Config A · HTTP (for agents that support MCP HTTP; paste into their MCP server config):',
  '接入配置 B · 命令行方式（适用于仅支持 stdio MCP 的 Agent，启动命令如下）：':
    'Config B · stdio bridge (for agents that only support command-line MCP; launch command below):',
  '📋 复制全部配置': '📋 Copy all',
  '完成': 'Done',
  /* 弹窗：新建群聊 */
  '新建群聊': 'New group',
  '群聊名称': 'Group name',
  '如：项目攻坚群': 'e.g. Project taskforce',
  '选择加入的成员（可多选）': 'Pick members (multi-select)',
  '创建并进入': 'Create & enter',
  '文件工作区 / 任务 / 记忆按群聊独立隔离；外部成员被拉入后可用其网关工具传 room_id 在该群收发。':
    'Workspace / tasks / memory are isolated per group. External agents can pass room_id to their gateway tools to chat in that group.',
  /* 弹窗：绑定身份卡 */
  '绑定身份卡': 'Bind identity card',
  '选择身份卡（选「解绑」恢复未绑定，按钮将变回复制令牌）': 'Pick a card (choose unbind to revert; the button turns back into Copy token)',
  '保存': 'Save',
  /* 文件预览 */
  '文件内容预览与编辑（保存走乐观锁，冲突会提示刷新）': 'Preview & edit file content (optimistic-lock save; conflicts prompt a refresh)',
  /* JS 动态字符串 */
  '正在输入…': 'typing…',
  '● 已连接': '● Connected',
  '● 已断开，3 秒重连': '● Disconnected, retry in 3s',
  '内置': 'Built-in',
  '未绑定身份卡': 'No identity card',
  '外部在线': 'External online',
  '外部离线': 'External offline',
  '复制令牌': 'Copy token',
  '绑定身份卡 ·': 'Bind identity ·',
  '— 解绑 —': '— Unbind —',
  '待派发': 'Queued', '执行中': 'Running', '已验收': 'Accepted', '已打回': 'Rejected',
  '待确认': 'Pending confirm', '已熔断·待裁决': 'Paused · needs you', '已完成': 'Done', '已作废': 'Aborted',
  '（暂无任务；在上方填写目标并下达，CEO 将拆解为排产单）':
    '(No tasks yet; set a goal above and issue it — CEO will plan it.)',
  '✓ 确认开工': '✓ Approve & start',
  '作废': 'Discard',
  '继续执行': 'Resume',
  '终止': 'Terminate',
  '状态：': 'Status: ',
  '（打回': ' (rejected ×', '次）': ')',
  '交付：': 'Delivery: ',
  '验收：': 'Review: ',
  '（暂无文件；Agent 交付物与人类上传都会出现在这里）':
    '(No files yet; agent deliverables and your uploads land here)',
  '删除': 'Delete',
  '（暂无记忆；任务验收通过后自动沉淀）': '(No memories yet; they settle after task acceptance)',
  '（暂无技能；在下方添加、导入 .md 文件，或参考内置示例）':
    '(No skills yet; add below, import .md files, or check the built-in samples)',
  '导出': 'Export',
  '默认': 'Default', '薄雾': 'Mist', '晨曦': 'Dawn', '暮色': 'Dusk',
  '字符 ·': ' chars ·',
  '公共记忆': 'Public memory', '私有记忆': 'Private memory',
  '条': ' item(s)',
  '：': ': ',
};

/* 帮助面板英文模板（zh 原版留在 index.html，切换时互换） */
const I18N_HELP_EN = `
      <div class="grp">🚀 Quick start</div>
      <div class="help-item"><b>Send a message</b>: type in the composer, Enter to send (Shift+Enter for a newline). Default is <b>broadcast</b> — every agent sees it; type <code>@</code> to pick a member for a <b>directed</b> message (only mentioned agents reply).</div>
      <div class="help-item"><b>Issue a task</b>: open the Tasks tab → write the goal → 🎯 Issue. The CEO drafts a plan for your <b>confirmation</b>, then dispatches work orders by dependency. Deliveries are reviewed automatically (bad ones are sent back), and you get a summary at the end.</div>
      <div class="help-item"><b>Files</b>: the Files tab uploads/previews/edits/deletes workspace files. Agents read & write the same space via fs tools; successful deliveries are announced in the room — click the 📎 attachment to preview. Saves use <b>optimistic locking</b> — on conflict you'll be prompted to refresh.</div>
      <div class="help-item"><b>Emergency stop</b>: the ⏹ button or "Stop all" on the Members tab fires a P0 interrupt, cancelling every in-flight agent generation.</div>

      <div class="grp" style="margin-top:14px;">✨ Features</div>
      <div class="help-item"><b>Room members</b>: two built-in agents stream in parallel — <b>Agent A · user assistant</b> (answers, prompt help, guidance, scheduling) and <b>Agent B · room steward</b> (scheduled chat digests, housekeeping). External agents join via the MCP gateway as first-class members.</div>
      <div class="help-item"><b>Identity cards</b>: define a label, persona, responsibilities and a <b>tool allowlist</b> (fs.read / fs.write / fs.list, … — calls outside the list are rejected). Bind on the Members tab; once bound, an external agent's "Copy token" button becomes "Bind identity".</div>
      <div class="help-item"><b>External agents</b>: "＋ Add external agent" issues a one-time token plus MCP configs (copyable). While unbound you can "Copy token" to re-issue (revokes the old one); ✕ removes the agent.</div>
      <div class="help-item"><b>Tasks tab</b>: live status (pending confirm / running / paused / done) with per-subtask chips; after a circuit break you can "Resume" or "Terminate".</div>
      <div class="help-item"><b>Vector memory</b>: public memory (settled after accepted tasks, visible to all) and per-agent private memory (owner-only) are physically isolated. Relevant memories are retrieved into agent context with timestamps. Chat is <b>uncapped</b> — Agent B periodically digests history into public memory and prunes storage, so work items are kept forever while raw chatter is archived.</div>
      <div class="help-item"><b>Appearance</b>: switch the UI language, set a chat background image or gradient, tune transparency, toggle motion. Stored locally in your browser.</div>
      <div class="help-item"><b>Model config</b>: the Model tab takes any OpenAI-compatible endpoint (Base URL / API Key / model); saving auto-verifies connectivity. Without it the whole system runs in <b>placeholder mode</b> (full pipeline, canned replies).</div>

      <div class="grp" style="margin-top:14px;">❓ FAQ</div>
      <div class="help-item"><b>Q: Replies all say "placeholder"?</b><br>A: No LLM configured. Add an OpenAI-compatible endpoint on the Model tab.</div>
      <div class="help-item"><b>Q: File save reports a version conflict?</b><br>A: Someone (or an agent) updated the file while you edited. The latest version was fetched for you — just save again. That's optimistic locking preventing overwrites.</div>
      <div class="help-item"><b>Q: Where did old chat messages go?</b><br>A: Archived by Agent B — the digest settled into the Memory tab; originals were pruned to save space. Tasks, reviews and other key events are kept forever.</div>
      <div class="help-item"><b>Q: Task stuck at "Paused · needs you"?</b><br>A: In-task chat hit the limit (default 12). Pick "Resume" or "Terminate" on the Tasks tab.</div>
      <div class="help-item"><b>Q: How do other local agents join / how to create a group?</b><br>A: This app welcomes many kinds of agents — Members tab → ＋Add external agent → copy the token and the MCP config into your agent (HTTP config for MCP-HTTP agents, stdio bridge command for CLI-only ones). Use "＋ New Group" in the left rail to spin up isolated rooms.</div>

      <div class="grp" style="margin-top:14px;">🗺️ Roadmap</div>
      <div class="hint">Shipped: group chat → identity cards/@mentions/P0 → MCP gateway → workspace + WeChat-style UI → CEO orchestration + vector memory + circuit breakers. In progress: external agents claiming work orders, gateway二次 permissions, unattended mode (see docs/STEP6-HANDOFF.md).</div>`;

/* zh→en 反查表（切回中文用） */
const I18N_ZH = {};
for (const [zh, en] of Object.entries(I18N_EN)) I18N_ZH[en] = zh;

function i18nDict() { return I18N_LANG === 'en' ? I18N_EN : I18N_ZH; }

/* 文本节点精确替换 */
function i18nApplyText(root) {
  const dict = i18nDict();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const n of nodes) {
    const key = n.textContent.trim();
    if (key && dict[key] !== undefined) n.textContent = n.textContent.replace(key, dict[key]);
  }
}

function i18nApplyAttrs(root) {
  const dict = i18nDict();
  for (const el of root.querySelectorAll('[placeholder],[title]')) {
    for (const attr of ['placeholder', 'title']) {
      const v = el.getAttribute(attr);
      if (v && dict[v.trim()] !== undefined) el.setAttribute(attr, dict[v.trim()]);
    }
  }
}

/* 帮助面板整块切换 */
function i18nApplyHelp() {
  const help = document.getElementById('rp-help');
  if (!help) return;
  if (I18N_LANG === 'en') {
    if (!help.dataset.zh) help.dataset.zh = help.innerHTML;
    help.innerHTML = I18N_HELP_EN;
  } else if (help.dataset.zh) {
    help.innerHTML = help.dataset.zh;
  }
}

function applyLang(lang) {
  I18N_LANG = lang;
  localStorage.setItem(I18N_LANG_KEY, lang);
  const root = document.getElementById('app') || document.body;
  i18nApplyText(root);
  i18nApplyAttrs(root);
  i18nApplyHelp();
  applyAppearance && applyAppearance();  // 刷新预设名等动态文案
  document.dispatchEvent(new CustomEvent('langchange', { detail: { lang } }));
}

/* 动态字符串：i18t('内置') */
function i18t(zh) {
  if (I18N_LANG !== 'en') return zh;
  return I18N_EN[zh] !== undefined ? I18N_EN[zh] : zh;
}
