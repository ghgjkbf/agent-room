/* i18n v2（深色重设计版）：词典 STR = 语义 key → [zh, en]。
   - 静态标注：data-i18n="key" → textContent；data-i18n-ph → placeholder；data-i18n-title → title
   - 动态串：i18t(zh) 按 REV（zh 整串精确反查）取当前语言；查不到原样返回 zh
   - 帮助面板：#rp-help 整块互换（dataset.zh 备份 zh 原文 + I18N_HELP_EN 模板）
   - applyLang 末尾 dispatch 'langchange'，app.js 侧监听重渲染动态区域
   聊天内容（Agent 回复、后端系统消息）语言跟随对话本身，不做翻译。 */

const STR = {
  /* ===== 静态键（index.html data-i18n 标注，110 唯一键） ===== */
  /* 左栏 / 顶栏 */
  'brand.sub': ['多Agent群聊协作 · 本机运行', 'Multi-agent group chat · runs locally'],
  'search.placeholder': ['🔍 #37 跳转到消息', '🔍 #37 jump to message'],
  'search.jumpNotFound': ['没有第 {n} 条消息（当前共 {m} 条）', 'No message #{n} ({m} total)'],
  'group.sessions': ['会话', 'Sessions'],
  'btn.newRoom': ['＋ 新建群聊', '＋ New Group'],
  'btn.addExternal': ['＋ 添加外部成员', '＋ Add External Agent'],
  'title.files': ['文件工作区', 'Files workspace'],
  'title.members': ['成员管理', 'Members'],
  'title.settings': ['身份卡与模型设置', 'Identity & model settings'],
  'title.help': ['使用说明', 'Help'],
  'title.stopAll': ['停止全部（P0 interrupt）', 'Stop all (P0 interrupt)'],
  'ph.draft': ['输入消息，Enter 发送；输入 @ 弹出成员选择…', 'Type a message; Enter to send, @ to mention…'],
  'title.refs': ['引用工作区文件', 'Reference workspace files'],
  'btn.send': ['发 送', 'Send'],
  /* 右面板 tabs */
  'tab.files': ['文件', 'Files'],
  'tab.task': ['任务', 'Tasks'],
  'tab.members': ['成员', 'Members'],
  'tab.identity': ['身份卡', 'Identity'],
  'tab.model': ['模型', 'Model'],
  'tab.memory': ['记忆', 'Memory'],
  'tab.appearance': ['外观', 'Appearance'],
  'tab.skills': ['技能', 'Skills'],
  'tab.help': ['帮助', 'Help'],
  /* 文件面板 */
  'files.workspace': ['文件工作区', 'Files workspace'],
  'btn.upload': ['⬆ 上传', '⬆ Upload'],
  'files.previewHint': ['点文件名预览', 'Click a file to preview'],
  'btn.savePreview': ['💾 保存', '💾 Save'],
  'ph.filePreview': ['文件内容预览与编辑（保存走乐观锁，冲突会提示刷新）', 'Preview & edit file content (optimistic-lock save; conflicts prompt a refresh)'],
  /* 任务面板 */
  'grp.task': ['任务 · CEO 编排闭环', 'Tasks · CEO orchestration loop'],
  'lbl.taskGoal': ['任务目标（CEO 拆解为排产单，先给你确认）', 'Goal (CEO turns it into a work plan for your confirmation)'],
  'ph.taskGoal': ['如：调研竞品并输出对比报告', 'e.g. Research competitors and produce a comparison report'],
  'btn.issueTask': ['🎯 下达任务', '🎯 Issue task'],
  'grp.taskProgress': ['任务进度', 'Progress'],
  'btn.tasksClear': ['🧹 清空已完成任务', '🧹 Clear finished tasks'],
  'hint.taskFlow': ['流程：下达 → 编排拆解 → 你确认 → 按依赖派发排产单 → 交付 → 验收/打回（不设上限直至通过）→ 汇总沉淀记忆。',
    'Flow: issue → orchestration plans → you confirm → dispatch by dependency → delivery → review/reject (no cap, redone until accepted) → summary into memory.'],
  /* 成员面板 */
  'grp.members': ['成员', 'Members'],
  'grp.membersSub': ['（右侧下拉换绑身份卡）', '(switch identity via dropdown)'],
  'grp.quickOps': ['快捷操作', 'Quick actions'],
  'btn.archiveNow': ['🧹 立即归档清理（Agent B 执行）', '🧹 Archive now (run by Agent B)'],
  'btn.stopAllFull': ['■ 停止全部（P0 interrupt）', '■ Stop all (P0 interrupt)'],
  'hint.members': ['P0 生效会取消所有 Agent 正在进行的生成。互聊不设上限，聊天记录由 Agent B 定时总结归档清理。',
    'P0 cancels all in-flight agent generation. Chat is uncapped; Agent B archives and prunes history on schedule.'],
  /* 身份卡面板 */
  'grp.identityList': ['身份卡列表', 'Identity cards'],
  'btn.newIdentity': ['＋ 新建身份卡', '＋ New card'],
  'grp.editor': ['编辑器', 'Editor'],
  'lbl.idLabel': ['显示标签 label', 'Display label'],
  'ph.idLabel': ['如：调研员', 'e.g. Researcher'],
  'lbl.idPersona': ['风格 persona', 'Persona'],
  'ph.idPersona': ['严谨、简洁、不懂就问', 'rigorous, concise, asks when unsure'],
  'lbl.idResp': ['职责 responsibilities（顿号分隔）', 'Responsibilities (comma separated)'],
  'lbl.idFocus': ['发言领域 focus（顿号分隔，命中才接话广播；留空 = 只响应 @ 与排产单）', 'Focus keywords (comma separated; only matched keywords wake this member on broadcasts; empty = respond to @ and work orders only)'],
  'ph.idFocus': ['前端、样式、组件', 'frontend, styling, components'],
  'ph.idResp': ['检索资料、写调研笔记', 'collect material, write research notes'],
  'grp.tools': ['核心权限勾选 tools_allow（🔒 须勾选，其余默认可用）', 'Core permissions tools_allow (🔒 opt-in; the rest are open by default)'],
  'btn.toolsRec': ['⚡ 一键：勾全部核心', '⚡ Check all core'],
  'btn.clear': ['清空', 'Clear'],
  'btn.save': ['保存', 'Save'],
  'btn.del': ['删除', 'Delete'],
  'hint.identity': ['互聊轮次自 5.5 步起不设上限（Agent B 定时归档清理聊天记录防存储膨胀）。保存后可在「成员」页为 Agent 换绑。',
    'Chat turns are uncapped since 5.5 (Agent B archives history to bound storage). Rebind agents on the Members tab after saving.'],
  /* 模型面板 */
  'grp.model': ['LLM · OpenAI 兼容端点', 'LLM · OpenAI-compatible endpoint'],
  'ph.llmUrl': ['https://api.example.com/v1', 'https://api.example.com/v1'],
  'ph.llmKey': ['sk-...', 'sk-...'],
  'lbl.modelName': ['模型名', 'Model name'],
  'ph.llmModel': ['gpt-4o-mini / deepseek-chat …', 'gpt-4o-mini / deepseek-chat …'],
  'btn.saveLlm': ['保存并连接', 'Save & connect'],
  'hint.modelTest': ['保存后会自动向端点发一条测试消息验证连通性。', 'After saving, a test message is sent to the endpoint to verify connectivity.'],
  'hint.model': ['配置保存后自动发一条测试消息校验连通性；配置存本机数据库（重启不丢，不出本机）；V2 迁移加密存储与多模型插槽。',
    'Saving auto-sends a test message to verify connectivity. Config is stored in the local database (survives restarts, never leaves this machine); encrypted storage & multi-model slots planned for V2.'],
  /* 记忆面板 */
  'grp.memory': ['向量记忆 · 本地存储', 'Vector memory · local storage'],
  'btn.memClear': ['🗑 清空公共记忆', '🗑 Clear public memory'],
  'hint.memory': ['公共记忆：任务验收通过后沉淀；私有记忆：Agent 交付时写入、仅本人可读。检索 top-k 自动注入 Agent 上下文并标注来源时间。闲聊不入库。每条记忆可单独删除，也可一键清空公共记忆。',
    'Public memory settles after task acceptance; private memory is written on agent delivery and readable only by its owner. Top-k hits are injected into agent context with timestamps. Chit-chat is never stored. Each memory can be deleted individually, or clear the public store in one click.'],
  /* 外观面板 */
  'grp.lang': ['语言 / Language', '语言 / Language'],
  'grp.bg': ['聊天背景', 'Chat background'],
  'lbl.bgCustom': ['自定义背景图（本地图片，存浏览器不外传）', 'Custom image (stored in your browser only)'],
  'btn.bgImage': ['🖼 选择图片', '🖼 Choose image'],
  'btn.bgReset': ['恢复默认', 'Reset'],
  'grp.opacity': ['透明度', 'Transparency'],
  'lbl.mask': ['背景遮罩浓度（越高文字越清晰）：', 'Backdrop veil (higher = clearer text):'],
  'lbl.bub': ['气泡不透明度：', 'Bubble opacity:'],
  'grp.fx': ['动效', 'Motion'],
  'lbl.ripple': ['点击波纹与气泡弹跳', 'Click ripples & bubble bounce'],
  'hint.appearance': ['设置保存在本浏览器（localStorage），每个浏览器独立；图片不离开本机。',
    'Settings live in this browser (localStorage); images never leave your machine.'],
  /* 技能面板 */
  'grp.skills': ['内部技能库 · 供群里 Agent 使用', 'Skill library · for agents in the room'],
  'hint.skillsIntro': ['技能 = 写法规范 / 模板 / 工作流（md 文档）。Agent 绑定含 skills.* 白名单的身份卡后，可在对话中自查技能并照做。',
    'Skills = conventions / templates / workflows (md docs). Agents with skills.* on their allowlist can look them up mid-chat and follow them.'],
  'grp.skillsImport': ['从本机技能库导入', 'Import from local skill library'],
  'skills.src.zcode': ['ZCode 技能库（d:/ai-use/.zcode/skills）', 'ZCode skill library (d:/ai-use/.zcode/skills)'],
  'skills.src.trae': ['TRAE 技能库（.trae-cn/skills）', 'TRAE skill library (.trae-cn/skills)'],
  'skills.src.builtin': ['TRAE 内置技能（.trae-cn/builtin_skills）', 'TRAE built-in skills (.trae-cn/builtin_skills)'],
  'btn.import': ['导入', 'Import'],
  'grp.skillsEdit': ['添加 / 更新技能', 'Add / update skill'],
  'lbl.skillName': ['技能名（文字/数字/连字符，可中文，如 周报模板）', 'Skill name (letters/digits/hyphens, CJK ok, e.g. weekly-report)'],
  'lbl.skillContent': ['技能内容（Markdown：用途 / 工作流 / 模板 / 要求）', 'Skill content (Markdown: purpose / workflow / template / rules)'],
  'ph.skillContent': ['# 技能名\n\n用途：…\n## 工作流\n1. …\n## 模板\n…\n## 要求\n- …',
    '# Skill name\n\nPurpose: …\n## Workflow\n1. …\n## Template\n…\n## Rules\n- …'],
  'btn.saveSkill': ['保存技能', 'Save skill'],
  'btn.importMd': ['📥 导入 .md 文件', '📥 Import .md files'],
  'hint.skills': ['导入：可选多个 .md 文件，文件名即技能名（非法字符自动转换，同名覆盖）；列表中每个技能可导出为 .md 分享。',
    'Import one or more .md files; the filename becomes the skill name (sanitized, overwrite on clash). Export any skill from the list to share it.'],
  /* 弹窗：新建群聊 */
  'm.roomTitle': ['新建群聊', 'New group'],
  'lbl.roomName': ['群聊名称', 'Group name'],
  'ph.roomName': ['如：项目攻坚群', 'e.g. Project taskforce'],
  'lbl.roomPicks': ['选择加入的成员（可多选）', 'Pick members (multi-select)'],
  'btn.roomCreate': ['创建并进入', 'Create & enter'],
  'btn.cancel': ['取消', 'Cancel'],
  'hint.roomModal': ['文件工作区 / 任务 / 记忆按群聊独立隔离；外部成员被拉入后可用其网关工具传 room_id 在该群收发。',
    'Workspace / tasks / memory are isolated per group. External agents can pass room_id to their gateway tools to chat in that group.'],
  /* 弹窗：添加外部成员 */
  'm.extTitle': ['添加外部成员', 'Add external agent'],
  'lbl.extName': ['成员名称（如：开发员·外部）', 'Agent name (e.g. Dev·external)'],
  'ph.extName': ['开发员·外部', 'Dev·external'],
  'lbl.extBind': ['绑定身份卡（可稍后换绑）', 'Bind identity card (can rebind later)'],
  'opt.noBind': ['— 暂不绑定 —', '— Not bound —'],
  'btn.extCreate': ['创建并发放令牌', 'Create & issue token'],
  'm.extResult': ['✅ 成员已创建 · 令牌仅显示这一次', '✅ Agent created · token shown only once'],
  'hint.token': ['ROOM_TOKEN（重发将使旧令牌失效）：', 'ROOM_TOKEN (re-issuing revokes the old one):'],
  'hint.cfgHttp': ['接入配置 A · HTTP 方式（适用于支持 MCP HTTP 的 Agent，填入其 MCP 服务器配置）：',
    'Config A · HTTP (for agents that support MCP HTTP; paste into their MCP server config):'],
  'hint.cfgStdio': ['接入配置 B · 命令行方式（适用于仅支持 stdio MCP 的 Agent，启动命令如下）：',
    'Config B · stdio bridge (for agents that only support command-line MCP; launch command below):'],
  'btn.copyAll': ['📋 复制全部配置', '📋 Copy all'],
  'btn.done': ['完成', 'Done'],
  /* 弹窗：绑定身份卡 */
  'lbl.bindPick': ['选择身份卡（选「解绑」恢复未绑定，按钮将变回复制令牌）', 'Pick a card (choose unbind to revert; the button turns back into Copy token)'],

  /* ===== 动态串（app.js i18t() 调用点，zh 整串精确反查） ===== */
  'dyn.generating': ['生成中', 'Generating…'],
  'dyn.wsConnected': ['● 已连接', '● Connected'],
  'dyn.wsDisconnected': ['● 已断开，3 秒重连', '● Disconnected, retrying in 3s'],
  'dyn.refsPrefix': ['【引用工作区文件】', '[Workspace file]'],
  'dyn.extOnline': ['外部在线', 'External online'],
  'dyn.extOffline': ['外部离线', 'External offline'],
  'dyn.builtin': ['内置', 'Built-in'],
  'dyn.bindCard': ['绑定身份卡', 'Bind identity card'],
  'dyn.bindCardDot': ['绑定身份卡 · ', 'Bind identity card · '],
  'dyn.copyToken': ['复制令牌', 'Copy token'],
  'dyn.delMember': ['删除成员', 'Remove agent'],
  'dyn.noIdentity': ['未绑定身份卡', 'No identity card bound'],
  'dyn.confirmDelMember': ['删除成员？', 'Remove this agent?'],
  'dyn.removedMember': ['已删除成员：', 'Removed agent: '],
  'dyn.unbind': ['— 解绑 —', '— Unbind —'],
  'dyn.identityUpdated': ['身份卡已更新。', 'Identity card updated.'],
  'dyn.llmReady': ['LLM 已配置', 'LLM configured'],
  'dyn.llmNotReady': ['LLM 未配置', 'LLM not configured'],
  'dyn.human': ['人类', 'Human'],
  'dyn.noFiles': ['（暂无文件；Agent 交付物与人类上传都会出现在这里）', '(No files yet; agent deliverables and your uploads will appear here)'],
  'dyn.confirmDelFile': ['删除文件？', 'Delete this file?'],
  'dyn.uploaded': ['已上传：', 'Uploaded: '],
  'dyn.versionConflict': ['版本冲突：', 'Version conflict: '],
  'dyn.conflictRefreshed': ['，已为你刷新内容，请重新保存。', '— refreshed to the latest; please save again.'],
  'dyn.saved': ['已保存：', 'Saved: '],
  /* SUB_CHIP / TASK_ST 状态词（「执行中」两字典共用一条） */
  'st.pending': ['待派发', 'Pending'],
  'st.running': ['执行中', 'Running'],
  'st.accepted': ['已验收', 'Accepted'],
  'st.rejected': ['已打回', 'Rejected'],
  'st.awaiting': ['待确认', 'Awaiting confirm'],
  'st.paused': ['已暂停', 'Paused'],
  'st.done': ['已完成', 'Done'],
  'st.aborted': ['已作废', 'Discarded'],
  'dyn.noTasks': ['（暂无任务；在上方填写目标并下达，CEO 将拆解为排产单）', '(No tasks yet; set a goal above and issue it — CEO will break it into work orders)'],
  'dyn.delivery': ['交付：', 'Deliverables: '],
  'dyn.acceptance': ['验收：', 'Acceptance: '],
  'dyn.rejectPre': ['（打回', '(rejected '],
  'dyn.rejectSuf': ['次）', ' times)'],
  'dyn.confirmStart': ['✓ 确认开工', '✓ Approve & start'],
  'dyn.discard': ['作废', 'Discard'],
  'dyn.resume': ['继续执行', 'Resume'],
  'dyn.terminate': ['终止', 'Terminate'],
  'dyn.delTaskRecord': ['删除该任务记录', 'Delete task record'],
  'dyn.status': ['状态：', 'Status: '],
  'dyn.confirmDelTask': ['删除该任务记录？（群内消息保留）', 'Delete this task record? (group messages are kept)'],
  'dyn.delFailed': ['删除失败', 'Delete failed'],
  'dyn.taskAborted': ['任务已作废。', 'Task discarded.'],
  'dyn.taskResumed': ['已恢复执行，CEO 按依赖继续派发。', 'Resumed; CEO keeps dispatching by dependency.'],
  'dyn.taskApproved': ['已确认开工，CEO 按依赖派发排产单。', 'Approved; CEO dispatches work orders by dependency.'],
  'dyn.confirmClearTasks': ['清空全部已结束（已完成/已作废）的任务记录？（群内消息保留）', 'Clear all finished (done/discarded) task records? (group messages are kept)'],
  'dyn.clearedTasks': ['已清空任务：', 'Cleared tasks: '],
  'dyn.items': ['个', 'item(s)'],
  'dyn.itemsSp': [' 个', ' item(s)'],
  'dyn.needGoal': ['请先填写任务目标', 'Set a task goal first'],
  'dyn.taskIssued': ['任务已下达，CEO 正在拆解…', 'Task issued; CEO is planning…'],
  'dyn.publicMem': ['公共记忆', 'Shared memory'],
  'dyn.count': ['条', 'item(s)'],
  'dyn.countSp': [' 条', ' item(s)'],
  'dyn.privateMem': ['私有记忆', 'Private memory'],
  'dyn.noMemory': ['（暂无记忆；任务验收通过后自动沉淀）', '(No memories yet; distilled after task acceptance)'],
  'dyn.memNoId': ['该条记忆无 id，无法删除', 'This memory has no id; cannot delete'],
  'dyn.confirmDelMem': ['删除这条记忆？', 'Delete this memory?'],
  'dyn.memDeleted': ['已删除该条记忆。', 'Memory deleted.'],
  'dyn.confirmClearMem': ['清空本群聊的全部公共记忆？（私有记忆不受影响）', 'Clear ALL shared memory of this room? (private memory is unaffected)'],
  'dyn.clearedMem': ['已清空公共记忆：', 'Cleared shared memories: '],
  'dyn.switchedTo': ['已切换到：', 'Switched to: '],
  'dyn.noSkills': ['（暂无技能；在下方添加、导入 .md 文件，或参考内置示例）', '(No skills yet; add below, import .md files, or see the built-in sample)'],
  'dyn.confirmDelSkill': ['删除技能？', 'Delete this skill?'],
  'dyn.skillDeleted': ['技能已删除', 'Skill deleted'],
  'dyn.skillSaved': ['技能已保存：', 'Skill saved: '],
  'dyn.pickSource': ['请选择技能来源', 'Pick a skill source first'],
  'dyn.importing': ['正在从本机技能库导入…', 'Importing from local skill library…'],
  'dyn.importFailed': ['导入失败', 'Import failed'],
  'dyn.imported': ['导入完成：', 'Imported: '],
  'dyn.skipped': ['跳过', 'skipped'],
  'dyn.nFailed': ['；失败 N 个：', '; N failed: '],
  'dyn.imgSize': ['图片请小于 6MB', 'Image must be under 6MB'],
  'dyn.bgApplied': ['背景图已应用（仅存本浏览器）。', 'Background applied (stored in this browser only).'],
  'dyn.bgTooLarge': ['图片过大无法本地存储，请换小图。', 'Image too large to store locally; try a smaller one.'],
  'dyn.appearanceReset': ['外观已恢复默认。', 'Appearance reset to defaults.'],
  'dyn.confirmArchive': ['立即归档清理本群聊？（自上次归档以来的聊天将总结进公共记忆并清理原文）', 'Archive & clean this room now? (chats since the last archive will be summarized into shared memory and pruned)'],
  'dyn.archived': ['归档完成：', 'Archived: '],
  'dyn.wsEmpty': ['（工作区暂无文件；先在「文件」面板上传或让 Agent 交付）', '(Workspace is empty; upload via the Files panel or let an agent deliver)'],
  'dyn.pickRefs': ['点击选择要引用的文件（可多选）', 'Click files to reference (multi-select)'],

  /* ===== 常用指令条 ===== */
  'cmd.archive': ['🧹 归档清理', '🧹 Archive'],
  'cmd.archive.tip': ['立即归档清理本群聊', 'Archive & clean this room now'],
  'cmd.memSummary': ['💾 存记忆', '💾 Save memory'],
  'cmd.memSummary.tip': ['让 B 总结本轮讨论并存入公共记忆', 'Ask B to digest this session into shared memory'],
  'cmd.memQuery': ['🔍 查记忆', '🔍 Query memory'],
  'cmd.memQuery.tip': ['让 B 检索公共记忆（补上要查的问题）', 'Ask B to search shared memory (append your question)'],
  'cmd.clearDone': ['🗑 清完成任务', '🗑 Clear done tasks'],
  'cmd.clearDone.tip': ['清空已结束的任务记录', 'Clear finished task records'],
  'cmd.clearChat': ['✂️ 删消息', '✂️ Delete messages'],
  'cmd.clearChat.tip': ['让 B 定向删除消息（补 #序号）', 'Ask B to delete messages by #number'],
  'cmd.memClear': ['⚠️ 清空记忆', '⚠️ Clear memory'],
  'cmd.memClear.tip': ['清空本群全部公共记忆（慎用）', 'Clear ALL shared memory of this room (careful)'],
  'cmd.status': ['📊 房间状态', '📊 Room status'],
  'cmd.status.tip': ['让 A 汇总成员状态与任务进展', 'Ask A to summarize members and task progress'],

  /* ===== 消息序号 / 星标 / 软删 / 跳转 ===== */
  'dyn.confirmDelMsg': ['删除这条消息？（群内其他成员将不再可见）', 'Delete this message? (it disappears for everyone in the room)'],
  'dyn.msgDeleted': ['消息已删除。', 'Message deleted.'],
  'dyn.msgDelFailed': ['删除失败', 'Delete failed'],
  'dyn.starFailed': ['星标操作失败，已还原。', 'Star toggle failed; reverted.'],
  'dyn.starOn': ['星标（免归档）', 'Star (exempt from archiving)'],
  'dyn.starOff': ['取消星标', 'Unstar'],
  'dyn.delMsg': ['删除消息', 'Delete message'],

  /* ===== 动态渲染补充（A.3 表外、但 en 态持久可见的渲染串） ===== */
  'x.you': ['你', 'You'],
  'x.ceo': ['CEO 编排', 'CEO Orchestrator'],
  'x.broadcast': ['广播', 'Broadcast'],
  'x.l1': ['L1 编排', 'L1 Orchestrator'],
  'x.previewTip': ['点击在文件面板预览', 'Click to preview in Files panel'],
  'x.direct': ['定向投递 → ', 'Direct to '],
  'x.broadcastTip': ['广播模式：全体 Agent 可见可回', 'Broadcast mode: visible to and replyable by all agents'],
  'x.rebind': ['换绑身份卡', 'Rebind identity card'],
  'x.unbound': ['— 未绑定 —', '— Unbound —'],
  'x.by': ['作者', 'by'],
  'x.newSession': ['— 新会话，说点什么吧 —', '— New session, say something —'],
  'x.now': ['现在', 'now'],
  'x.loading': ['（加载中…）', '(loading…)'],
  'x.external': ['外部', 'External'],
  'x.noMembers': ['（暂无成员）', '(No members)'],
  'x.chars': ['字符 ·', ' chars ·'],
  'x.export': ['导出', 'Export'],
  'x.allMembers': ['📣 全体成员（广播）', '📣 Everyone (broadcast)'],
  'x.colon': ['：', ': '],
};

/* zh → key 反查表（i18t 用），启动时构建；en → zh 反查（切回中文用） */
const REV = {};
const REV_EN = {};
for (const [k, v] of Object.entries(STR)) { REV[v[0]] = k; REV_EN[v[1]] = v[0]; }

const I18N_LANG_KEY = 'aroom-lang';
let I18N_LANG = localStorage.getItem(I18N_LANG_KEY) || 'zh';

/* 六处无 data-i18n 的静态文案：仅当当前文本恰好等于另一语言的初始值时才替换，
   动态覆盖（群名 / 已连接 / 已配置 / 带标签的绑定标题）后不匹配即跳过，天然防误伤 */
const STATIC_I18N = {
  'typing':     ['Agent A 正在输入…', 'Agent A is typing…'],
  'scope-tip':  ['广播模式：全体 Agent 可见可回', 'Broadcast mode: visible to and replyable by all agents'],
  'room-name':  ['主房间', 'Main Room'],
  'ws-chip':    ['● 连接中…', '● Connecting…'],
  'llm-chip':   ['LLM 未配置', 'LLM not configured'],
  'bind-title': ['绑定身份卡', 'Bind identity card'],
};

/* 帮助面板英文模板（与 index.html zh 块的 .grp / .help-item 结构一一对应） */
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
      <div class="help-item"><b>Tasks panel</b>: live task status (awaiting confirm / running / paused / done) plus per-subtask progress chips; a paused task can be "Resume"d or "Terminate"d.</div>
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
      <div class="hint">Shipped: group chat → identity cards / mentions / P0 → MCP gateway (external agents) → file workspace + WeChat-style UI → CEO orchestration loop + vector memory. In progress: external agents taking work orders, second-layer gateway permission checks, unattended task intake.</div>`;

/* 消息流界面 chrome（.who 署名 / .lbl 标签 / .fold-tip / ghost .ghost-lbl）随语言互换。
   只替换「整个文本节点精确等于」词条的节点，消息正文（长文本节点）天然不受影响。 */
function i18nApplyFeedChrome() {
  const feed = document.getElementById('feed');
  if (!feed) return;
  const en = I18N_LANG === 'en';
  const walker = document.createTreeWalker(feed, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const n of nodes) {
    const t = n.textContent.trim();
    if (!t) continue;
    const k = REV[t];
    if (k !== undefined) {
      if (en) n.textContent = n.textContent.replace(t, STR[k][1] ?? t);
    } else if (!en) {
      const zh = REV_EN[t];
      if (zh !== undefined) n.textContent = n.textContent.replace(t, zh);
    }
  }
}

/* 动态串：整串精确反查 → 当前语言；查不到原样返回 zh。
   快捷路径：传 STR 语义 key（如 'cmd.archive'）直接取词条，供新 UI 免建 zh 反查。 */
function i18t(zh) {
  if (Object.prototype.hasOwnProperty.call(STR, zh)) {
    const direct = STR[zh];
    return I18N_LANG === 'en' ? (direct[1] ?? direct[0]) : direct[0];
  }
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
  for (const [id, s] of Object.entries(STATIC_I18N)) {            // 六处静态定向（dispatch 之前）
    const el = document.getElementById(id);
    if (el && el.textContent === (I18N_LANG === 'en' ? s[0] : s[1])) el.textContent = I18N_LANG === 'en' ? s[1] : s[0];
  }
  i18nApplyFeedChrome();                                          // 消息流界面署名（你/广播/CEO 编排等）随语言互换
  document.dispatchEvent(new CustomEvent('langchange'));          // app.js 侧监听重渲染动态区
  if (typeof applyAppearance === 'function') applyAppearance();   // 重渲染背景预设（p.name/p.en）
}
