/* Agent Room 前端：WS 连接 + 消息流渲染 + 身份卡编辑器 + @提及。
   第 2 步：双 Agent 并行回复、群内标签、P0 interrupt。 */

const $ = (id) => document.getElementById(id);
let ws = null;
let currentRoom = 'default';   // 当前会话（第 6 步多房间）
let rooms = [];                // [{id,name,member_count}]
let roomLast = {};             // rid -> 最近一条预览文本
let LAST_CHIP = null;          // setChip 最近入参缓存（langchange 重渲染用）
let LAST_LLM_READY = null;     // llm-chip 最近就绪状态缓存（同上）
let LAST_MENTIONS = [];        // 最近一次 @ 定向名单（切语言后重设 scope-tip 用）
const R = () => currentRoom;
let agents = [];        // [{id,name,identity_id,identity_label,chat_turns}]
let identities = [];    // [{id,label,persona,responsibilities,tools_allow,version}]
const TOOL_OPTIONS = ['fs.read', 'fs.write', 'fs.list', 'skills.list', 'skills.read', 'skills.write', 'memory.query', 'doc.read', 'browser.open', 'shell.run', 'chat.archive', 'chat.delete', 'admin.list_members', 'admin.list_identities', 'admin.bind_identity'];
const RESTRICTED_TOOLS = ['shell.run', 'chat.archive', 'chat.delete', 'admin.list_members', 'admin.list_identities', 'admin.bind_identity'];  // 核心权限：默认不开放，勾选才生效

/* 签名元素：成员专属色相（id 稳定哈希 → hsl 色环），一眼分辨谁在说话 */
function hueFor(id) {
  let h = 0;
  for (const c of String(id)) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

/* ---------- 消息渲染 ---------- */
function addBubble(msg) {
  const feed = $('feed');
  const el = document.createElement('div');
  const kind = msg.sender.kind;
  el.className = 'msg ' + (kind === 'human' ? 'human' : kind === 'system' ? 'system' : 'agent')
    + (['task_plan', 'dispatch', 'receipt'].includes(msg.type) ? ' orch' : '');

  if (kind === 'system') {
    el.textContent = msg.payload.text;
  } else {
    const who = document.createElement('div');
    who.className = 'who';
    let name = kind === 'human' ? i18t('你') : kind === 'orchestrator' ? i18t('CEO 编排') : msg.sender.id;
    if (kind === 'agent') {
      const meta = agents.find(a => a.id === msg.sender.id);
      name = meta ? meta.name : name;
    }
    if (kind === 'agent' || kind === 'orchestrator') {
      const dot = document.createElement('i');
      dot.className = 'who-dot';
      dot.style.setProperty('--h', hueFor(msg.sender.id));
      who.appendChild(dot);
    }
    who.appendChild(document.createTextNode(name));
    const lbl = document.createElement('span');
    lbl.className = 'lbl';
    lbl.textContent = kind === 'agent'
      ? (msg.mentions && msg.mentions.length ? '@' + msg.mentions.join(',@') : agentLabel(msg.sender.id))
      : kind === 'human' ? i18t('广播') : kind === 'orchestrator' ? i18t('L1 编排') : 'system';
    who.appendChild(lbl);
    const body = document.createElement('div');
    body.className = 'body';
    body.textContent = msg.payload.text;
    el.appendChild(who); el.appendChild(body);
    if (msg.msg_id) attachMsgChrome(el, msg);        // 编号锚 + 星标/删除（system 不挂；需在入 DOM 后挂）
    renumberFeed();
  }
  el.dataset.ts = String(Date.now());
  feed.appendChild(el);
  feed.scrollTop = feed.scrollHeight;
  return el;
}

/* 位置序号：按 feed 当前顺序对非 system 消息 1..N 重排（删除/归档后自然连续） */
function renumberFeed() {
  let n = 0;
  document.querySelectorAll('#feed .msg').forEach(m => {
    if (m.classList.contains('system') || m.classList.contains('ghost')) return;
    n += 1;
    m.dataset.no = String(n);
    let no = m.querySelector('.who .msg-no');
    if (!no) {
      no = document.createElement('span');
      no.className = 'msg-no';
      m.querySelector('.who').insertBefore(no, m.querySelector('.msg-ops'));
    }
    no.textContent = '#' + n;
  });
}

async function toggleStar(el) {
  if (!el.dataset.msgId) return;
  const on = !el.classList.contains('starred');
  el.classList.toggle('starred', on);           // 乐观切换，失败回滚
  const mark = el.querySelector('.star-mark');
  const btn = el.querySelector('.star-btn');
  if (mark) mark.style.display = on ? '' : 'none';
  if (btn) { btn.textContent = on ? '★' : '☆'; btn.title = on ? i18t('取消星标') : i18t('星标（免归档）'); }
  try {
    const r = await fetch(`/api/messages/${el.dataset.msgId}/star`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ starred: on ? 1 : 0 }),
    });
    if (!r.ok) throw new Error(r.status);
  } catch (e) {
    el.classList.toggle('starred', !on);
    if (mark) mark.style.display = on ? 'none' : '';
    if (btn) { btn.textContent = on ? '☆' : '★'; btn.title = on ? i18t('星标（免归档）') : i18t('取消星标'); }
    alertSys(i18t('星标操作失败，已还原。'));
  }
}

async function deleteMsg(el) {
  if (!el.dataset.msgId) return;
  if (!confirm(i18t('删除这条消息？（群内其他成员将不再可见）'))) return;
  const r = await fetch(`/api/messages/${el.dataset.msgId}`, { method: 'DELETE' }).catch(() => null);
  if (!r || !r.ok) return alertSys(i18t('删除失败'));
  el.remove();
  renumberFeed();
  alertSys(i18t('消息已删除。'));
}

/* 跳转：#n 回车 → 滚动定位 + 高亮闪烁 2 秒 */
function jumpToMsg(n) {
  const target = document.querySelector(`#feed .msg[data-no="${n}"]`);
  if (!target) {
    const total = document.querySelectorAll('#feed .msg[data-no]').length;
    alertSys(i18t('没有第 {n} 条消息（当前共 {m} 条）').replace('{n}', String(n)).replace('{m}', String(total)));
    return;
  }
  target.scrollIntoView({ block: 'center', behavior: 'smooth' });
  target.classList.remove('jump-flash');
  void target.offsetWidth;                     // 重启动画
  target.classList.add('jump-flash');
  setTimeout(() => target.classList.remove('jump-flash'), 2200);
}

function agentLabel(id) {
  const m = agents.find(a => a.id === id);
  return (m && m.identity_label) ? m.identity_label : '未绑定';
}

/* 跳转框：输入 #37 或 37 回车 → 定位高亮 */
$('jump-input').addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return;
  e.preventDefault();
  const v = parseInt(e.target.value.replace(/^#/, '').trim(), 10);
  e.target.value = '';
  if (Number.isFinite(v) && v > 0) jumpToMsg(v);
});

/* 流式渲染 v2：正式气泡只在有完整内容时诞生。
   流式片段写入「幽灵面板」（虚线框、头像呼吸、随内容置底），终态一次性
   落成正式气泡——气泡永远出生即完整，空壳在结构上不可能出现。 */
let streaming = {}; // agentId -> {el, body}

function ghostFor(aid) {
  if (streaming[aid] && document.body.contains(streaming[aid].el)) return streaming[aid].el;
  const meta = agents.find(a => a.id === aid);
  const name = meta ? meta.name : aid;
  const el = document.createElement('div');
  el.className = 'msg agent ghost';
  el.dataset.ts = String(Date.now());
  el.innerHTML = `<div class="who"><i class="who-dot" style="--h:${hueFor(aid)}"></i>${esc(name)}<span class="lbl ghost-lbl">${i18t('生成中')}</span></div><div class="body"></div>`;
  $('feed').appendChild(el);
  $('feed').scrollTop = $('feed').scrollHeight;
  streaming[aid] = { el, body: el.querySelector('.body') };
  return el;
}

function commitGhost(aid, msg, text) {
  const st = streaming[aid];
  delete streaming[aid];
  if (st && document.body.contains(st.el)) st.el.remove();
  if (!text) return;  // 空内容直接丢弃——永不产生空泡
  const el = addBubble(msg || { sender: { kind: 'agent', id: aid }, payload: { text: '' } });
  el.querySelector('.body').textContent = text;
  if (msg && msg.tool_summary && msg.tool_summary.length) {
    const note = document.createElement('div');
    note.className = 'tool-note';
    note.textContent = msg.tool_summary.join(' ');
    el.appendChild(note);
  }
  if (msg && msg.msg_id) attachMsgChrome(el, msg);   // 落定补挂编号/星标/删除
  renumberFeed();
}

/* 气泡的编号锚 + 星标/删除操作（system 胶囊不挂；重复调用安全） */
function attachMsgChrome(el, msg) {
  if (!msg.msg_id) return;
  if (!el.dataset.msgId) el.dataset.msgId = msg.msg_id;
  if (msg.starred) el.classList.add('starred');
  const who = el.querySelector('.who');
  if (!who) return;
  let ops = who.querySelector('.msg-ops');
  if (ops) { refreshOps(el, ops, msg.starred); renumberFeed(); return; }
  const starMark = document.createElement('span');
  starMark.className = 'star-mark';
  starMark.textContent = '★';
  if (!msg.starred) starMark.style.display = 'none';
  ops = document.createElement('span');
  ops.className = 'msg-ops';
  ops.innerHTML = '<button class="star-btn"></button><button class="del-btn">✕</button>';
  refreshOps(el, ops, msg.starred);
  ops.querySelector('.star-btn').addEventListener('click', () => toggleStar(el));
  ops.querySelector('.del-btn').addEventListener('click', () => deleteMsg(el));
  who.appendChild(starMark);
  who.appendChild(ops);
  renumberFeed();
}
function refreshOps(el, ops, starred) {
  const btn = ops.querySelector('.star-btn');
  if (!btn) return;
  btn.textContent = starred ? '★' : '☆';
  btn.title = starred ? i18t('取消星标') : i18t('星标（免归档）');
  ops.querySelector('.del-btn').title = i18t('删除消息');
}

function finalizeStreaming() {
  // 人类/系统消息（含 P0）到达：把还在流式的幽灵按已有内容落泡（可能不完整，
  // 但绝不丢弃用户已看到的内容），空幽灵静默移除
  for (const aid in streaming) {
    const st = streaming[aid];
    const text = st && st.body ? st.body.textContent : '';
    commitGhost(aid, null, text);
  }
  streaming = {};
}

function handleMessage(msg) {
  clearTimeout(handleMessage._t);

  if (msg.type === 'system') { finalizeStreaming(); addBubble(msg); return; }

  // 流式片段 / 终止信号：写入幽灵面板，终态落泡（不再产生任何空气泡）
  if (msg.type === 'chat' && msg.sender.kind === 'agent') {
    const ghost = ghostFor(msg.sender.id);
    const body = ghost.querySelector('.body');
    if (msg.payload.text) {
      body.textContent += msg.payload.text;
      $('feed').appendChild(ghost);   // 活跃流保持在底部
      $('feed').scrollTop = $('feed').scrollHeight;
    }
    if (msg.is_final) {
      commitGhost(msg.sender.id, msg, body.textContent);
      return;
    }
    return;
  }

  if (msg.type === 'deliver') { finalizeStreaming(); addDeliverBubble(msg); refreshFiles(); return; }
  if (!(msg.type === 'chat' && msg.sender.kind === 'agent' && msg.payload.text)) {
    finalizeStreaming();
    addBubble(msg);
    return;
  }

  // 理论上不会再走到这里（上面已分流）；兜底按普通气泡渲染
  addBubble(msg);
}

/* deliver 消息：渲染成可点击附件样式（点击预览工作区文件） */
function addDeliverBubble(msg) {
  const el = addBubble(msg);
  el.classList.add('deliver');
  const m = (msg.payload.text || '').match(/([^\s（(]+)\s*（?v(\d+)/);
  if (m) {
    const path = m[1];
    const link = document.createElement('span');
    link.className = 'deliver-file';
    link.textContent = '📎 ' + path;
    link.title = i18t('点击在文件面板预览');
    link.addEventListener('click', () => {
      openPanel('rp-files');
      previewFile(path);
    });
    el.appendChild(link);
  }
}

/* 工具调用事件（不落库的广播）：在活跃气泡下附一行小字 */
function showToolEvent(msg) {
  if (!streaming[msg.sender.id] || !document.body.contains(streaming[msg.sender.id].el)) return;
  const el = streaming[msg.sender.id].el;
  let note = el.querySelector('.tool-note');
  if (!note) {
    note = document.createElement('div');
    note.className = 'tool-note';
    el.appendChild(note);
  }
  note.textContent = `🔧 ${msg.tool_event.name} ${msg.tool_event.result_ok ? '✓' : '✗'}`;
}

/* ---------- WS ---------- */
function connect() {
  ws = new WebSocket('ws://' + location.host + '/ws/' + currentRoom);
  ws.onopen = () => setChip('● 已连接', '#10b981');
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.tool_event) { showToolEvent(msg); return; }  // 工具调用事件，不进消息流
    handleMessage(msg);
    if (msg.type === 'system') refreshMembers(); // 熔断等系统事件后刷新轮数
    if (msg.type !== 'system' || (msg.payload && msg.payload.text)) updateConvoLast(msg);
    if (msg.type === 'deliver') refreshFiles();  // 交付消息同步文件面板
    if (['task', 'task_plan', 'dispatch', 'receipt'].includes(msg.type)) {
      fetchTasks();                                // 编排事件 → 任务面板同步
      if (msg.type === 'receipt') refreshMemory(); // 验收沉淀记忆后同步记忆面板
    }
  };
  ws.onclose = () => { setChip('● 已断开，3 秒重连', '#b42318'); setTimeout(connect, 3000); };
  ws.onerror = () => ws.close();
}
function setChip(text, color) {
  LAST_CHIP = { text, color };
  text = i18t(text);
  $('ws-chip').textContent = text;
  $('ws-chip').style.color = color;
  $('ws-chip').classList.toggle('live', color === '#10b981');
}

/* 左栏会话项的「最后一条」摘要（多房间：存 roomLast 再重渲染） */
function updateConvoLast(msg) {
  const text = (msg.payload && msg.payload.text) || '';
  if (!text) return;
  let who = i18t('你');
  if (msg.sender.kind === 'agent') {
    const meta = agents.find(a => a.id === msg.sender.id);
    who = meta ? meta.name : msg.sender.id;
  } else if (msg.sender.kind === 'system') who = '';
  const t = new Date();
  roomLast[currentRoom] = {
    text: (who ? who + i18t('：') : '') + text.slice(0, 40),
    time: `${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`,
  };
  renderRooms();
}

function sendText() {
  const ta = $('draft');
  let text = ta.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
  const atIdx = text.lastIndexOf('@');
  let mentions = [];
  if (atIdx >= 0) {
    const tail = text.slice(atIdx + 1).trim();
    agents.forEach(a => {
      if (tail.startsWith(a.name.split(' ')[1] || a.name)) mentions.push(a.id);
    });
    if (!mentions.includes('agent_a') && tail.toLowerCase().startsWith('a')) mentions.push('agent_a');
    if (!mentions.includes('agent_b') && tail.toLowerCase().startsWith('b')) mentions.push('agent_b');
  }
  if (pendingRefs.size) {
    text = `${i18t('【引用工作区文件】')}${[...pendingRefs].join('、')}
${text}`;
    pendingRefs.clear(); hideRefsPop();
  }
  ta.value = ''; hideMentionPop();
  updateScopeTip(mentions);
  ws.send(JSON.stringify({ type: 'chat', text, mentions }));
}
function updateScopeTip(mentions) {
  LAST_MENTIONS = mentions || [];
  $('scope-tip').textContent = mentions.length
    ? `${i18t('定向投递 → ')}${mentions.map(id => (agents.find(a => a.id === id) || {}).name || id).join(', ')}`
    : i18t('广播模式：全体 Agent 可见可回');
}

/* ---------- 成员列表（含换绑 + 外部成员） ---------- */
async function refreshMembers() {
  const res = await fetch(`/api/agents?room_id=${currentRoom}`); agents = await res.json();
  $('agent-count').textContent = agents.length;
  renderRooms();
  $('member-list').innerHTML = agents.map((a) => {
    const external = a.kind === 'external';
    const online = a.status === 'online';
    const badge = external
      ? `<span class="kind-badge external">${online ? '🟢' : '⚪'} ${i18t(online ? '外部在线' : '外部离线')}</span>`
      : `<span class="kind-badge internal">${i18t('内置')}</span>`;
    const bindUi = external
      ? ''
      : `<select data-agent="${a.id}" title="${i18t('换绑身份卡')}">
          <option value="">${i18t('— 未绑定 —')}</option>
          ${identities.map(c => `<option value="${c.id}" ${c.id === a.identity_id ? 'selected' : ''}>${c.label}</option>`).join('')}
        </select>`;
    // 外部成员：始终可「绑定身份卡」（换绑/解绑）；未绑定时另有「复制令牌」用于接入
    const tokUi = external
      ? `<button class="copy-tok bind-card" data-agent="${a.id}" data-name="${a.name}">${i18t('绑定身份卡')}</button>` +
        (a.identity_id ? '' : `<button class="copy-tok tok2" data-agent="${a.id}" data-name="${a.name}">${i18t('复制令牌')}</button>`) +
        `<button class="del-agent" data-agent="${a.id}" data-name="${a.name}" title="${i18t('删除成员')}">✕</button>`
      : '';
    return `
    <div class="member">
      <div class="avatar" style="--h:${hueFor(a.id)}">${(a.name)[0].toUpperCase()}</div>
      <div style="min-width:0;">
        <div>${a.name}${badge}</div>
        <div class="lbl" style="background:var(--brand-soft);color:var(--brand-ink);font-size:10px;padding:0 6px;border-radius:999px;display:inline-block;">${a.identity_label || i18t('未绑定身份卡')}</div>
      </div>
      ${bindUi}${tokUi}
    </div>`;
  }).join('');
  $('member-list').querySelectorAll('select').forEach(sel =>
    sel.addEventListener('change', async () => {
      await fetch(`/api/agents/${sel.dataset.agent}/bind`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identity_id: sel.value }),
      });
      refreshMembers();
    }));
  $('member-list').querySelectorAll('.copy-tok:not(.bind-card)').forEach(btn =>
    btn.addEventListener('click', async () => {
      const r = await fetch(`/api/agents/${btn.dataset.agent}/rotate-token`, { method: 'POST' });
      if (!r.ok) return alertSys((await r.json()).detail || '重发失败');
      const d = await r.json();
      await navigator.clipboard.writeText(d.token).catch(() => {});
      showExternalResult({ id: btn.dataset.agent, name: btn.dataset.name, token: d.token });
      refreshMembers();
    }));
  $('member-list').querySelectorAll('.bind-card').forEach(btn =>
    btn.addEventListener('click', () => openBindCard(btn.dataset.agent, btn.dataset.name)));
  $('member-list').querySelectorAll('.del-agent').forEach(btn =>
    btn.addEventListener('click', async () => {
      if (!confirm(i18t('删除成员？') + btn.dataset.name)) return;
      const r = await fetch(`/api/agents/${btn.dataset.agent}`, { method: 'DELETE' });
      if (!r.ok) return alertSys((await r.json()).detail || i18t('删除失败'));
      alertSys(i18t('已删除成员：') + btn.dataset.name);
      refreshMembers();
    }));
  $('agent-count').textContent = agents.length;
}

/* 第 5.5 步：外部成员绑定/换绑身份卡弹窗 */
let bindTarget = null;
function openBindCard(agentId, agentName) {
  bindTarget = agentId;
  $('bind-title').textContent = i18t('绑定身份卡 · ') + agentName;
  $('bind-identity').innerHTML = `<option value="">${i18t('— 解绑 —')}</option>` +
    identities.map(c => `<option value="${c.id}">${c.label}</option>`).join('');
  const cur = (agents.find(a => a.id === agentId) || {}).identity_id || '';
  $('bind-identity').value = cur;
  $('modal-form').style.display = 'none';
  $('modal-result').style.display = 'none';
  $('modal-bind').style.display = 'block';
  $('modal-mask').classList.add('on');
}
$('btn-bind-cancel').addEventListener('click', () => {
  $('modal-mask').classList.remove('on');
  $('modal-bind').style.display = 'none';
});
$('btn-bind-save').addEventListener('click', async () => {
  if (!bindTarget) return;
  const r = await fetch(`/api/agents/${bindTarget}/bind`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identity_id: $('bind-identity').value || null }),
  });
  if (!r.ok) return alertSys('绑定失败：' + JSON.stringify(await r.json()));
  $('modal-mask').classList.remove('on');
  $('modal-bind').style.display = 'none';
  alertSys(i18t('身份卡已更新。'));
  refreshMembers();
});

/* ---------- 身份卡编辑器 ---------- */
let editingId = null; // null=新建

async function refreshIdentities() {
  const res = await fetch('/api/identities'); identities = await res.json();
  $('id-list').innerHTML = identities.map(c => `
    <div class="idcard" data-id="${c.id}">
      🪪 <b>${c.label}</b> · ${c.responsibilities.join('、') || '无职责'}
      <span class="cv">v${c.version}</span>
    </div>`).join('');
  $('id-list').querySelectorAll('.idcard').forEach(el =>
    el.addEventListener('click', () => {
      $('id-list').querySelectorAll('.idcard').forEach(x => x.classList.remove('sel'));
      el.classList.add('sel');
      loadCard(identities.find(c => c.id === el.dataset.id));
    }));
}

function renderToolCheckboxes(selected) {
  $('id-tools').innerHTML = TOOL_OPTIONS.map(t => {
    const core = RESTRICTED_TOOLS.includes(t);
    return `<label style="${core ? 'color:var(--brand-strong);' : 'opacity:.85;'}">` +
      `<input type="checkbox" value="${t}" ${selected.includes(t) ? 'checked' : ''}>${t}${core ? ' 🔒' : ''}</label>`;
  }).join('') +
  `<div class="hint" style="margin-top:4px;">非 🔒 工具默认全员可用；🔒 核心权限（高危/治理/授权）须勾选才开放。</div>`;
}
function loadCard(c) {
  editingId = c ? c.id : null;
  $('id-label').value = c ? c.label : '';
  $('id-persona').value = c ? c.persona : '';
  $('id-resp').value = c ? c.responsibilities.join('、') : '';
  $('id-focus').value = c ? (c.focus || []).join('、') : '';
  renderToolCheckboxes(c ? c.tools_allow : []);
}

async function saveCard() {
  const card = {
    label: $('id-label').value.trim(),
    persona: $('id-persona').value.trim(),
    responsibilities: $('id-resp').value.split(/[、,,]/).map(s => s.trim()).filter(Boolean),
    focus: $('id-focus').value.split(/[、,,]/).map(s => s.trim()).filter(Boolean),
    tools_allow: [...$('id-tools').querySelectorAll('input:checked')].map(i => i.value),
  };
  if (!card.label) return alertSys('请填写显示标签 label');
  const url = editingId ? `/api/identities/${editingId}` : '/api/identities';
  const res = await fetch(url, {
    method: editingId ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(card),
  });
  if (!res.ok) { alertSys('保存失败：' + JSON.stringify(await res.json())); return; }
  alertSys(editingId ? `身份卡「${card.label}」已更新` : `身份卡「${card.label}」已创建`);
  await refreshIdentities(); await refreshMembers();
}

async function deleteCard() {
  if (!editingId) return alertSys('请先在上方列表选择一张身份卡');
  const res = await fetch(`/api/identities/${editingId}`, { method: 'DELETE' });
  if (!res.ok) { alertSys((await res.json()).detail || '删除失败'); return; }
  loadCard(null); await refreshIdentities(); await refreshMembers();
  alertSys('已删除');
}
function alertSys(text) {
  addBubble({ sender: { kind: 'system' }, payload: { text } });
}

/* ---------- @提及弹出层 ---------- */
function showMentionPop() {
  const pop = $('mention-pop');
  pop.innerHTML = `<div class="mp-item all" data-id="__all__">${i18t('📣 全体成员（广播）')}</div>` +
    agents.map(a => `<div class="mp-item" data-id="${a.id}"><div class="avatar" style="width:22px;height:22px;font-size:10px;">${a.name[0]}</div>@${a.name}${a.identity_label ? ` · ${a.identity_label}` : ''}</div>`).join('');
  pop.style.display = 'block';
  pop.querySelectorAll('.mp-item').forEach(item => item.addEventListener('mousedown', (e) => {
    e.preventDefault();
    const ta = $('draft');
    ta.value = ta.value.replace(/@\S*$/, '') + (item.dataset.id === '__all__' ? '' : ' @' +
      ((agents.find(a => a.id === item.dataset.id) || {}).name || '').split(' ').pop());
    hideMentionPop(); ta.focus(); updateScopeTip(parseMentionsFromText(ta.value));
  }));
}
function hideMentionPop() { $('mention-pop').style.display = 'none'; }
function parseMentionsFromText(text) {
  const at = text.lastIndexOf('@'); if (at < 0) return [];
  const tail = text.slice(at + 1).trim();
  return agents.filter(a => tail.startsWith(a.name.split(' ')[1] || a.name)).map(a => a.id);
}

/* ---------- Tab / 面板交互（微信式右侧内嵌面板） ---------- */
let panelOpen = false;
function openPanel(tab) {
  panelOpen = true;
  $('right-panel').classList.remove('closed');
  document.querySelectorAll('.rp-tab').forEach(x => x.classList.toggle('on', x.dataset.rp === tab));
  document.querySelectorAll('.rp-body').forEach(b => b.classList.toggle('on', b.id === tab));
  document.querySelectorAll('.icon-btn[data-panel]').forEach(b =>
    b.classList.toggle('on', b.dataset.panel === tab));
}
function closePanel() {
  panelOpen = false;
  $('right-panel').classList.add('closed');
  document.querySelectorAll('.icon-btn[data-panel]').forEach(b => b.classList.remove('on'));
}
function togglePanel(tab) {
  // 再点同一 Tab 图标 = 收起面板；否则切换/打开
  if (panelOpen && $('right-panel').querySelector('.rp-body.on')?.id === tab) closePanel();
  else openPanel(tab);
}
document.querySelectorAll('.rp-tab').forEach(t =>
  t.addEventListener('click', () => openPanel(t.dataset.rp)));
$('btn-panel-files').addEventListener('click', () => togglePanel('rp-files'));
$('btn-panel-members').addEventListener('click', () => togglePanel('rp-members'));
$('btn-panel-settings').addEventListener('click', () => togglePanel('rp-identity'));
$('btn-panel-help').addEventListener('click', () => togglePanel('rp-help'));
document.querySelectorAll('[data-panel]').forEach(b => { b.dataset.panel = ''; });
$('btn-panel-files').dataset.panel = 'rp-files';
$('btn-panel-members').dataset.panel = 'rp-members';
$('btn-panel-settings').dataset.panel = 'rp-identity';
$('btn-panel-help').dataset.panel = 'rp-help';

$('btn-send').addEventListener('click', sendText);
$('draft').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText(); }
});
$('draft').addEventListener('input', () => {
  const v = $('draft').value;
  if (v.endsWith('@')) showMentionPop();
  else { hideMentionPop(); updateScopeTip(parseMentionsFromText(v)); }
});
function stopAll() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'interrupt', text: '停止全部' }));
  }
}
$('btn-stop-all').addEventListener('click', stopAll);
$('btn-stop-all2').addEventListener('click', stopAll);
$('btn-save-llm').addEventListener('click', async () => {
  const cfg = { base_url: $('llm-url').value.trim(), api_key: $('llm-key').value.trim(), model: $('llm-model').value.trim() };
  if (!cfg.base_url || !cfg.model) return alertSys('请至少填写 Base URL 与模型名');
  const r = await (await fetch('/api/llm-config', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cfg),
  })).json();
  LAST_LLM_READY = r.llm_ready;
  $('llm-chip').textContent = r.llm_ready ? i18t('LLM 已配置') : i18t('LLM 未配置');
  alertSys(r.llm_ready ? 'LLM 配置已保存，正在校验连通性…' : '配置不完整。');
  if (!r.llm_ready) return;
  const tr = await (await fetch('/api/llm-test', { method: 'POST' })).json();
  $('llm-test-result').textContent = tr.ok
    ? `✓ 连接成功 · 模型 ${tr.model} · 延迟 ${tr.latency_ms}ms · 端点回复「${(tr.reply || '').slice(0, 20)}」`
    : `✗ 连接失败：${tr.error}`;
  alertSys(tr.ok ? `API 校验通过（${tr.latency_ms}ms）。` : `API 校验失败：${(tr.error || '').slice(0, 80)}`);
});
$('btn-new-id').addEventListener('click', () => { loadCard(null); });
$('btn-save-id').addEventListener('click', saveCard);
$('btn-del-id').addEventListener('click', deleteCard);

/* ---------- 外部成员（第 3 步 MCP 网关） ---------- */
function showExternalResult(d) {
  $('modal-form').style.display = 'none';
  $('modal-result').style.display = 'block';
  $('ext-token').textContent = d.token;
  $('cfg-zcode').value = JSON.stringify({
    mcp: { servers: { 'agent-room': {
      type: 'http', url: 'http://127.0.0.1:8899/gateway/mcp',
      headers: { 'X-Agent-Id': d.id, Authorization: 'Bearer ' + d.token },
      timeoutMs: 60000,
    }}}
  }, null, 2);
  $('cfg-trae').value = JSON.stringify({
    mcpServers: { 'agent-room': {
      command: '<backend venv python.exe 路径>',
      args: ['<项目>/backend/mcp_stdio.py'],
      env: {
        AGENT_ROOM_URL: 'http://127.0.0.1:8899/gateway/mcp',
        AGENT_ID: d.id, ROOM_TOKEN: d.token,
      },
    }}
  }, null, 2);
  $('modal-mask').classList.add('on');
}
async function openAddExternal() {
  $('ext-name').value = '';
  $('ext-identity').innerHTML = `<option value="">${i18t('— 暂不绑定 —')}</option>` +
    identities.map(c => `<option value="${c.id}">${c.label}</option>`).join('');
  $('modal-form').style.display = 'block';
  $('modal-result').style.display = 'none';
  $('modal-mask').classList.add('on');
}
$('btn-add-external').addEventListener('click', openAddExternal);
$('btn-add-external2').addEventListener('click', openAddExternal);
$('btn-ext-cancel').addEventListener('click', () => $('modal-mask').classList.remove('on'));
$('btn-ext-done').addEventListener('click', () => $('modal-mask').classList.remove('on'));
$('btn-ext-create').addEventListener('click', async () => {
  const name = $('ext-name').value.trim();
  if (!name) return alertSys('请填写成员名称');
  const r = await fetch('/api/agents/external', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, identity_id: $('ext-identity').value || null, room_id: currentRoom }),
  });
  if (!r.ok) return alertSys('创建失败：' + JSON.stringify(await r.json()));
  const d = await r.json();
  showExternalResult(d);
  await refreshMembers();
  alertSys(`外部成员「${name}」已创建，请立即复制令牌与接入配置。`);
});
$('btn-copy-all').addEventListener('click', async () => {
  const text = `TOKEN: ${$('ext-token').textContent}\n\n[ZCode .zcode/config.json]\n${$('cfg-zcode').value}\n\n[TRAE stdio]\n${$('cfg-trae').value}`;
  await navigator.clipboard.writeText(text).catch(() => {});
  alertSys('已复制令牌与两段接入配置。');
});

/* ---------- 文件工作区（第 4 步） ---------- */
let files = [];          // [{path, version, author, updated_at}]
let previewedFile = null; // {path, version} 当前预览的文件

async function refreshFiles() {
  const res = await fetch(`/api/files?room_id=${currentRoom}`);
  if (!res.ok) return;
  files = await res.json();
  const tree = {};
  files.forEach(f => tree[f.path] = f);
  const paths = Object.keys(tree).sort();
  $('file-tree').innerHTML = paths.length ? paths.map(p => {
    const f = tree[p];
    const dir = p.includes('/') ? p.slice(0, p.lastIndexOf('/') + 1) : '';
    const name = p.slice(dir.length);
    return `<div class="file-row" data-path="${p}">
      <span class="file-name" title="${p}">📄 ${dir ? `<span class="file-dir">${dir}</span>` : ''}${name}</span>
      <span class="file-ver">v${f.version}</span>
      <span class="file-author ${f.author === 'human' ? 'hum' : ''}">${f.author === 'human' ? '👤' : '🤖'}${f.author === 'human' ? i18t('人类') : f.author}</span>
      <button class="file-del" data-path="${p}" title="${i18t('删除')}">✕</button>
    </div>`;
  }).join('') : `<div class="hint">${i18t('（暂无文件；Agent 交付物与人类上传都会出现在这里）')}</div>`;

  $('file-tree').querySelectorAll('.file-name').forEach(el =>
    el.addEventListener('click', () => previewFile(el.closest('.file-row').dataset.path)));
  $('file-tree').querySelectorAll('.file-del').forEach(el =>
    el.addEventListener('click', async () => {
      const p = el.dataset.path;
      if (!confirm(i18t('删除文件？') + p)) return;
      await fetch('/api/files', {
        method: 'DELETE', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_id: currentRoom, path: p }),
      });
      if (previewedFile && previewedFile.path === p) { previewedFile = null; $('file-preview').value = ''; $('file-preview-head').textContent = i18t('点文件名预览'); }
      refreshFiles();
    }));
  $('file-count').textContent = files.length;
}

async function previewFile(path) {
  const res = await fetch(`/api/files/content?room_id=${currentRoom}&path=` + encodeURIComponent(path));
  if (!res.ok) return alertSys((await res.json()).detail || '读取失败');
  const d = await res.json();
  previewedFile = { path: d.path, version: d.version };
  $('file-preview').value = d.content;
  $('file-preview-head').textContent = `${d.path} · v${d.version} · ${i18t('作者')} ${d.author}`;
}

$('btn-upload').addEventListener('click', () => $('file-input').click());
$('file-input').addEventListener('change', async () => {
  const f = $('file-input').files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append('file', f);
  const r = await fetch(`/api/files/upload?room_id=${currentRoom}`, { method: 'POST', body: fd });
  if (!r.ok) return alertSys('上传失败：' + ((await r.json()).detail || r.status));
  const d = await r.json();
  alertSys(i18t('已上传：') + d.path + ' v' + d.version);
  $('file-input').value = '';
  refreshFiles();
});
$('btn-save-preview').addEventListener('click', async () => {
  if (!previewedFile) return alertSys('请先点文件名选择要编辑的文件');
  const r = await fetch('/api/files/write', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      room_id: currentRoom, path: previewedFile.path,
      content: $('file-preview').value, base_version: previewedFile.version,
    }),
  });
  if (!r.ok) {
    const d = await r.json();
    if (d.detail && d.detail.latest_version !== undefined) {
      alertSys(i18t('版本冲突：') + 'v' + d.detail.latest_version + i18t('，已为你刷新内容，请重新保存。'));
      previewFile(previewedFile.path); refreshFiles();
    } else alertSys('保存失败：' + (d.detail || JSON.stringify(d)));
    return;
  }
  const d = await r.json();
  alertSys(i18t('已保存：') + d.path + ' v' + d.version);
  previewedFile.version = d.version;
  $('file-preview-head').textContent = `${d.path} · v${d.version} · ${i18t('作者')} ${i18t('你')}`;
  refreshFiles();
});

/* ---------- 任务（CEO 编排闭环）与向量记忆 ---------- */
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
const SUB_CHIP = { pending: '待派发', dispatched: '执行中', accepted: '已验收', rejected: '已打回' };
const TASK_ST = { awaiting_confirm: '待确认', running: '执行中', paused: '已熔断·待裁决', done: '已完成', aborted: '已作废' };
const subChip = k => i18t(SUB_CHIP[k]);
const taskSt = k => i18t(TASK_ST[k]);

async function fetchTasks() {
  const res = await fetch(`/api/tasks?room_id=${currentRoom}`);
  if (!res.ok) return;
  renderTasks((await res.json()).tasks || []);
}
function renderTasks(tasks) {
  const el = $('task-list');
  if (!tasks.length) {
    el.innerHTML = `<div class="hint">${i18t('（暂无任务；在上方填写目标并下达，CEO 将拆解为排产单）')}</div>`;
    return;
  }
  el.innerHTML = tasks.map(t => {
    const subs = (t.subtasks || []).map(s => {
      const detail =
        (s.delivery_text ? `<div class="sub-detail">${i18t('交付：')}${esc(s.delivery_text.slice(0, 100))}${s.delivery_text.length > 100 ? '…' : ''}</div>` : '') +
        (s.last_receipt ? `<div class="sub-detail">${i18t('验收：')}${esc(s.last_receipt.slice(0, 100))}${s.last_receipt.length > 100 ? '…' : ''}</div>` : '');
      return `<div class="subtask"><span class="st-chip st-${s.status}">${subChip(s.status) || s.status_label}</span>` +
        `<span>#${s.seq} ${esc(s.title)} → ${esc(s.assignee)}${s.retries ? i18t('（打回') + s.retries + i18t('次）') : ''}</span></div>${detail}`;
    }).join('');
    let actions = '';
    if (t.status === 'awaiting_confirm')
      actions = `<button class="btn primary sm" data-act="confirm" data-id="${t.id}">${i18t('✓ 确认开工')}</button>` +
                `<button class="btn danger-full sm" data-act="abort" data-id="${t.id}">${i18t('作废')}</button>`;
    else if (t.status === 'paused')
      actions = `<button class="btn primary sm" data-act="resume" data-id="${t.id}">${i18t('继续执行')}</button>` +
                `<button class="btn danger-full sm" data-act="abort" data-id="${t.id}">${i18t('终止')}</button>`;
    if (t.status === 'done' || t.status === 'aborted')
      actions += `<button class="btn ghost sm" data-act="del" data-id="${t.id}" title="${i18t('删除该任务记录')}">🗑</button>`;
    return `<div class="task-card"><div class="task-goal">🎯 ${esc(t.goal)}</div>` +
      `<div class="task-status">${i18t('状态：')}${taskSt(t.status) || t.status_label}</div>${subs}` +
      (actions ? `<div class="task-actions">${actions}</div>` : '') + '</div>';
  }).join('');
  el.querySelectorAll('button[data-act]').forEach(b => b.addEventListener('click', async () => {
    const act = b.dataset.act;
    if (act === 'del') {
      if (!confirm(i18t('删除该任务记录？（群内消息保留）'))) return;
      const r = await (await fetch(`/api/tasks/${b.dataset.id}`, { method: 'DELETE' })).json();
      if (!r.ok) return alertSys(r.detail || i18t('删除失败'));
      return fetchTasks();
    }
    const url = `/api/tasks/${b.dataset.id}/${act === 'abort' ? 'abort' : 'confirm'}`;
    const r = await (await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: act }),
    })).json();
    if (!r.ok) return alertSys(r.detail || '操作失败');
    alertSys(act === 'abort' ? i18t('任务已作废。') : act === 'resume' ? i18t('已恢复执行，CEO 按依赖继续派发。') : i18t('已确认开工，CEO 按依赖派发排产单。'));
    fetchTasks();
  }));
}
/* 身份卡：一键白名单组合 */
$('btn-tools-rec').addEventListener('click', () => {
  $('id-tools').querySelectorAll('input').forEach(i => { i.checked = true; });  // 一键勾全部核心权限
});
$('btn-tools-clear').addEventListener('click', () => {
  $('id-tools').querySelectorAll('input').forEach(i => { i.checked = false; });
});

$('btn-tasks-clear').addEventListener('click', async () => {
  if (!confirm(i18t('清空全部已结束（已完成/已作废）的任务记录？（群内消息保留）'))) return;
  const r = await (await fetch('/api/tasks/clear-finished', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ room_id: currentRoom }),
  })).json();
  alertSys(i18t('已清空任务：') + (r.cleared || 0) + i18t(' 个'));
  fetchTasks();
});

$('btn-issue-task').addEventListener('click', () => {
  const v = $('task-goal').value.trim();
  if (!v) return alertSys(i18t('请先填写任务目标'));
  if (!ws || ws.readyState !== WebSocket.OPEN) return alertSys('连接未就绪');
  if (pendingRefs.size) {
    v = `${i18t('【引用工作区文件】')}${[...pendingRefs].join('、')}
${v}`;
    pendingRefs.clear(); hideRefsPop();
  }
  ws.send(JSON.stringify({ type: 'task', text: v }));
  $('task-goal').value = '';
  alertSys(i18t('任务已下达，CEO 正在拆解…'));
});

async function refreshMemory() {
  const res = await fetch(`/api/memory?room_id=${currentRoom}`);
  if (!res.ok) return;
  const d = await res.json();
  const s = d.stats || {};
  const agentPart = Object.entries(s.agents || {}).map(([a, n]) => `${a}:${n}`).join(', ');
  $('mem-stats').textContent = `${i18t('公共记忆')} ${s.public || 0} ${i18t('条')}` + (agentPart ? ` · ${i18t('私有记忆')} ${agentPart}` : '');
  const items = d.recent || [];
  $('mem-list').innerHTML = items.length
    ? items.map(r => `<div class="mem-item">${esc(r.text)}
        <div class="mem-meta">${esc(r.scope)} · ${esc((r.created_at || '').slice(0, 16).replace('T', ' '))}
          <button class="mini-btn" data-mem-del="${esc(r.scope)}|${esc(r.id || '')}" style="color:#b42318;margin-left:6px;">${i18t('删除')}</button>
        </div></div>`).join('')
    : `<div class="hint">${i18t('（暂无记忆；任务验收通过后自动沉淀）')}</div>`;
  $('mem-list').querySelectorAll('[data-mem-del]').forEach(b => b.addEventListener('click', async () => {
    const [scope, id] = b.dataset.memDel.split('|');
    if (!id) return alertSys(i18t('该条记忆无 id，无法删除'));
    if (!confirm(i18t('删除这条记忆？'))) return;
    const qs = new URLSearchParams({ room_id: currentRoom, id, scope: scope === 'public' ? 'public' : 'private',
      ...(scope !== 'public' ? { agent_id: scope.slice(8) } : {}) });
    const r = await (await fetch(`/api/memory/item?${qs}`, { method: 'DELETE' })).json();
    if (!r.ok) return alertSys(r.detail || i18t('删除失败'));
    alertSys(i18t('已删除该条记忆。')); refreshMemory();
  }));
}
$('btn-mem-clear').addEventListener('click', async () => {
  if (!confirm(i18t('清空本群聊的全部公共记忆？（私有记忆不受影响）'))) return;
  const r = await (await fetch('/api/memory/clear', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ room_id: currentRoom, scope: 'public' }),
  })).json();
  alertSys(i18t('已清空公共记忆：') + (r.cleared || 0) + i18t(' 条'));
  refreshMemory();
});

/* ---------- 多房间（第 6 步）：会话列表 / 新建群聊 / 切换 ---------- */
async function refreshRooms() {
  rooms = await (await fetch('/api/rooms')).json();
  renderRooms();
}
function renderRooms() {
  const el = $('room-list');
  el.innerHTML = rooms.map(r => {
    const last = roomLast[r.id] || (r.id === currentRoom ? { text: i18t('— 新会话，说点什么吧 —'), time: i18t('现在') } : {});
    return `<div class="convo ${r.id === currentRoom ? 'active' : ''}" data-room="${r.id}">
      <div class="convo-avatar">${esc((r.name || '?')[0])}</div>
      <div class="convo-info">
        <div class="convo-name">${esc(r.name)} <span class="cnt">· ${r.member_count} ${i18t('成员')}</span></div>
        <div class="convo-last">${esc(last.text || ' ')}</div>
      </div>
      <div class="convo-time">${esc(last.time || '')}</div>
    </div>`;
  }).join('');
  el.querySelectorAll('.convo').forEach(c =>
    c.addEventListener('click', () => switchRoom(c.dataset.room)));
  $('room-name').textContent = (rooms.find(r => r.id === currentRoom) || {}).name || currentRoom;
}
async function switchRoom(rid) {
  if (rid === currentRoom) return;
  currentRoom = rid;
  if (ws) { ws.onclose = null; ws.onerror = null; ws.close(); ws = null; }
  $('feed').innerHTML = '';
  $('file-tree').innerHTML = `<div class="hint">${i18t('（加载中…）')}</div>`;
  $('file-preview').value = ''; previewedFile = null;
  $('task-list').innerHTML = ''; $('mem-list').innerHTML = '';
  renderRooms();
  await loadRoomView();
  connect();
  alertSys(i18t('已切换到：') + ((rooms.find(r => r.id === currentRoom) || {}).name || currentRoom));
}
async function loadRoomView() {
  const data = await (await fetch('/api/room/' + currentRoom)).json();
  LAST_LLM_READY = data.llm_ready;
  $('llm-chip').textContent = data.llm_ready ? i18t('LLM 已配置') : i18t('LLM 未配置');
  await refreshMembers();
  await refreshFiles();
  await fetchTasks();
  await refreshMemory();
  (data.history || []).forEach(m => handleMessage(m));
  renumberFeed();   // 历史回放完成后统一编 1..N（回放逐条已编，此处收敛幂等）
}

/* 新建群聊弹窗 */
$('btn-new-room').addEventListener('click', async () => {
  const all = await (await fetch('/api/agents?all=1')).json();
  $('room-agent-picks').innerHTML = all.map(a =>
    `<label style="display:flex;align-items:center;gap:8px;padding:3px 0;font-size:13px;">
      <input type="checkbox" value="${a.id}" ${a.id === 'agent_a' || a.id === 'agent_b' ? '' : ''}>
      ${esc(a.name)}<span class="kind-badge ${a.kind === 'external' ? 'external' : 'internal'}">${a.kind === 'external' ? i18t('外部') : i18t('内置')}</span>
    </label>`).join('') || `<div class="hint">${i18t('（暂无成员）')}</div>`;
  $('room-name-in').value = '';
  $('room-modal-mask').classList.add('on');
});
$('btn-room-cancel').addEventListener('click', () => $('room-modal-mask').classList.remove('on'));
$('btn-room-create').addEventListener('click', async () => {
  const name = $('room-name-in').value.trim();
  if (!name) return alertSys('请填写群聊名称');
  const ids = [...$('room-agent-picks').querySelectorAll('input:checked')].map(i => i.value);
  const r = await (await fetch('/api/rooms', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, agent_ids: ids }),
  })).json();
  if (!r.ok) return alertSys(r.detail || '创建失败');
  $('room-modal-mask').classList.remove('on');
  await refreshRooms();
  await switchRoom(r.id);
});

/* ---------- 内部技能库（第 6 步） ---------- */
async function refreshSkills() {
  const list = await (await fetch('/api/skills')).json();
  const el = $('skill-list');
  el.innerHTML = list.length ? list.map(s =>
    `<div class="mem-item"><b>${esc(s.name)}</b>.md
      <div class="mem-meta">${s.chars} ${i18t('字符 ·')}
        <button class="mini-btn" data-export="${esc(s.name)}">${i18t('导出')}</button> ·
        <button class="mini-btn" data-skill="${esc(s.name)}" style="color:#b42318;">${i18t('删除')}</button></div>
    </div>`).join('')
    : `<div class="hint">${i18t('（暂无技能；在下方添加、导入 .md 文件，或参考内置示例）')}</div>`;
  el.querySelectorAll('button[data-skill]').forEach(b => b.addEventListener('click', async () => {
    if (!confirm(i18t('删除技能？') + b.dataset.skill)) return;
    const r = await fetch(`/api/skills/${b.dataset.skill}`, { method: 'DELETE' });
    if (!r.ok) return alertSys(i18t('删除失败'));
    alertSys(i18t('技能已删除')); refreshSkills();
  }));
  el.querySelectorAll('button[data-export]').forEach(b => b.addEventListener('click', async () => {
    const d = await (await fetch(`/api/skills/${b.dataset.export}`)).json();
    if (!d.content) return alertSys('读取失败');
    const blob = new Blob([d.content], { type: 'text/markdown' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${b.dataset.export}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  }));
}
/* 文件名 → 合法技能名（非法字符转连字符，防重尾） */
function skillNameFromFile(filename) {
  const base = filename.replace(/\.(md|markdown|txt)$/i, '');
  return base.replace(/[\/:*?"<>|]+/g, '-').replace(/\s+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40)
    || 'imported-skill';
}
async function saveSkillRemote(name, content) {
  const r = await (await fetch('/api/skills', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  })).json();
  return r.ok || !!r.name ? null : (r.detail || '保存失败');
}
$('btn-save-skill').addEventListener('click', async () => {
  const name = $('skill-name').value.trim();
  const content = $('skill-content').value;
  if (!name) return alertSys('请填写技能名');
  if (!content.trim()) return alertSys('请填写技能内容');
  const err = await saveSkillRemote(name, content);
  if (err) return alertSys(err);
  $('skill-name').value = ''; $('skill-content').value = '';
  alertSys(i18t('技能已保存：') + name);
  refreshSkills();
});
$('btn-import-skill').addEventListener('click', () => $('skill-files').click());
$('btn-import-local').addEventListener('click', async () => {
  const src = $('import-source').value;
  if (!src) return alertSys(i18t('请选择技能来源'));
  alertSys(i18t('正在从本机技能库导入…'));
  const r = await (await fetch('/api/skills/import', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source: src }),
  })).json();
  if (!r.ok) return alertSys(r.detail || i18t('导入失败'));
  alertSys(i18t('导入完成：') + `${r.count} ${i18t('个')}` + (r.skipped && r.skipped.length ? ` (${i18t('跳过')} ${r.skipped.length})` : ''));
  refreshSkills();
});
$('skill-files').addEventListener('change', async () => {
  const files = [...$('skill-files').files];
  $('skill-files').value = '';
  if (!files.length) return;
  const ok = [], fail = [];
  for (const f of files) {
    if (f.size > 200_000) { fail.push(`${f.name}（超 20 万字符）`); continue; }
    const content = await f.text();
    const err = await saveSkillRemote(skillNameFromFile(f.name), content);
    (err ? fail : ok).push(err ? `${f.name}（${err}）` : skillNameFromFile(f.name));
  }
  alertSys(`导入完成：成功 ${ok.length} 个${ok.length ? '（' + ok.join('、') + '）' : ''}` +
    (fail.length ? i18t('；失败 N 个：').replace('N', String(fail.length)) + fail.join('、') : ''));
  refreshSkills();
});


/* ---------- 外观（背景/透明度/动效，localStorage 持久化） ---------- */
const BG_PRESETS = [
  { id: 'default', name: '默认', en: 'Default', css: '' },
  { id: 'mist', name: '薄雾', en: 'Mist', css: 'linear-gradient(135deg,#10141b 0%,#171e29 100%)' },
  { id: 'dawn', name: '晨曦', en: 'Dawn', css: 'linear-gradient(135deg,#1a1206 0%,#2a1c0a 100%)' },
  { id: 'ink', name: '暮色', en: 'Dusk', css: 'linear-gradient(135deg,#0b0c0f 0%,#12141a 100%)' },
];
let appearance = Object.assign(
  { preset: 'default', image: null, mask: 0, bubble: 100, ripple: true },
  JSON.parse(localStorage.getItem('aroom-appearance') || '{}'));

function saveAppearance() { localStorage.setItem('aroom-appearance', JSON.stringify(appearance)); }

function applyAppearance() {
  const feed = $('feed');
  const preset = BG_PRESETS.find(p => p.id === appearance.preset) || BG_PRESETS[0];
  const mask = `linear-gradient(rgba(13,15,18,${appearance.mask / 100}), rgba(13,15,18,${appearance.mask / 100}))`;
  if (appearance.image) {
    feed.style.background = `${mask}, center/cover fixed no-repeat url(${appearance.image})`;
  } else if (preset.css) {
    feed.style.background = `${mask}, ${preset.css} fixed`;
  } else {
    feed.style.background = '';
  }
  document.documentElement.style.setProperty('--bub-a', appearance.bubble / 100);
  $('mask-v').textContent = appearance.mask;
  $('bg-mask').value = appearance.mask;
  $('bub-v').textContent = appearance.bubble;
  $('bub-opacity').value = appearance.bubble;
  $('fx-ripple').checked = appearance.ripple;
  renderBgPresets();
}
function renderBgPresets() {
  const el = $('bg-presets');
  el.innerHTML = BG_PRESETS.map(p => {
    const active = !appearance.image && appearance.preset === p.id;
    return `<div data-preset="${p.id}" title="${p.name}" style="cursor:pointer;height:44px;border-radius:8px;
      border:2px solid ${active ? 'var(--brand)' : 'var(--line)'};background:${p.css || 'var(--bg)'};
      display:flex;align-items:end;justify-content:center;font-size:9px;color:var(--muted);padding-bottom:2px;
      ${p.id === 'default' ? 'background:#151a21;border:1px solid #2a303a;' : ''}">${I18N_LANG === 'en' && p.en ? p.en : p.name}</div>`;
  }).join('');
  el.querySelectorAll('[data-preset]').forEach(d => d.addEventListener('click', () => {
    appearance.preset = d.dataset.preset; appearance.image = null; saveAppearance(); applyAppearance();
  }));
}
$('btn-bg-image').addEventListener('click', () => $('bg-file').click());
$('bg-file').addEventListener('change', () => {
  const f = $('bg-file').files[0];
  if (!f) return;
  if (f.size > 6 * 1024 * 1024) return alertSys(i18t('图片请小于 6MB'));
  const rd = new FileReader();
  rd.onload = () => {
    try {
      appearance.image = rd.result; appearance.preset = 'custom';
      saveAppearance(); applyAppearance();
      alertSys(i18t('背景图已应用（仅存本浏览器）。'));
    } catch (e) { alertSys(i18t('图片过大无法本地存储，请换小图。')); }
  };
  rd.readAsDataURL(f);
  $('bg-file').value = '';
});
$('btn-bg-reset').addEventListener('click', () => {
  appearance = { preset: 'default', image: null, mask: 0, bubble: 100, ripple: appearance.ripple };
  saveAppearance(); applyAppearance(); alertSys(i18t('外观已恢复默认。'));
});
$('bg-mask').addEventListener('input', () => {
  appearance.mask = +$('bg-mask').value; saveAppearance(); applyAppearance();
});
$('bub-opacity').addEventListener('input', () => {
  appearance.bubble = +$('bub-opacity').value; saveAppearance(); applyAppearance();
});
$('fx-ripple').addEventListener('change', () => {
  appearance.ripple = $('fx-ripple').checked; saveAppearance();
});

/* ---------- 动态点击效果：波纹 + 气泡弹跳 ---------- */
document.addEventListener('pointerdown', (e) => {
  if (!appearance.ripple) return;
  const t = e.target.closest('.msg.agent, .msg.orch, .send, .btn, .icon-btn, .rp-tab');
  if (!t) return;
  const r = t.getBoundingClientRect();
  const rip = document.createElement('span');
  const size = Math.max(r.width, r.height);
  rip.className = 'ripple';
  rip.style.width = rip.style.height = size + 'px';
  rip.style.left = (e.clientX - r.left - size / 2) + 'px';
  rip.style.top = (e.clientY - r.top - size / 2) + 'px';
  t.classList.add('fx');
  t.appendChild(rip);
  setTimeout(() => rip.remove(), 500);
});
// 气泡点击不再重播形变动画（scale 弹跳可能被流式 reflow 打断停在缩小帧，
// 视觉上即「点击后缩半」）；波纹保留

/* 手动归档清理（Agent B janitor 流程立即执行） */
$('btn-archive-now').addEventListener('click', async () => {
  if (!confirm(i18t('立即归档清理本群聊？（自上次归档以来的聊天将总结进公共记忆并清理原文）'))) return;
  const r = await (await fetch('/api/rooms/archive', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ room_id: currentRoom }),
  })).json();
  alertSys(i18t('归档完成：') + `${r.archived || 0} ${i18t('条')}`);
  refreshMemory();
});

/* ---------- 引用工作区文件（随消息发给 Agent） ---------- */
let pendingRefs = new Set();
function hideRefsPop() { $('refs-pop').style.display = 'none'; }
function renderRefsPop() {
  const pop = $('refs-pop');
  if (!files.length) {
    pop.innerHTML = `<div class="mp-item" style="color:var(--muted);">${i18t('（工作区暂无文件；先在「文件」面板上传或让 Agent 交付）')}</div>`;
  } else {
    pop.innerHTML = `<div class="mp-item all" style="font-weight:600;color:var(--brand-ink);">${i18t('点击选择要引用的文件（可多选）')}</div>` +
      files.map(f => {
        const on = pendingRefs.has(f.path);
        return `<div class="mp-item ${on ? 'on' : ''}" data-ref="${esc(f.path)}" style="display:flex;gap:6px;align-items:center;">
          <span>${on ? '☑' : '☐'}</span><span style="min-width:0;overflow:hidden;text-overflow:ellipsis;">📄 ${esc(f.path)}</span>
          <span style="margin-left:auto;color:var(--muted);font-size:10px;">v${f.version}</span></div>`;
      }).join('');
  }
  pop.style.display = 'block';
  pop.querySelectorAll('[data-ref]').forEach(item => item.addEventListener('mousedown', (e) => {
    e.preventDefault();
    const p = item.dataset.ref;
    pendingRefs.has(p) ? pendingRefs.delete(p) : pendingRefs.add(p);
    renderRefsPop();
  }));
}
$('btn-refs').addEventListener('click', (e) => {
  e.stopPropagation();
  const pop = $('refs-pop');
  if (pop.style.display === 'block') { hideRefsPop(); return; }
  renderRefsPop();
});
document.addEventListener('click', (e) => {
  if (!e.target.closest('#refs-pop') && !e.target.closest('#btn-refs')) hideRefsPop();
});

/* 语言切换：document 级委托（不依赖 boot 内联注册时序） */
document.addEventListener('change', (e) => {
  if (e.target && e.target.id === 'lang-select') applyLang(e.target.value);
});

/* langchange：切语言后以新语言重渲染动态区域（applyLang 在 dispatch 前已换静态文案） */
document.addEventListener('langchange', () => {
  if (typeof renderRooms === 'function') renderRooms();     // 左栏会话 + #room-name
  if (typeof refreshMembers === 'function') refreshMembers(); // 成员卡/绑定按钮
  if (typeof refreshFiles === 'function') refreshFiles();   // 文件列表
  if (typeof fetchTasks === 'function') fetchTasks();       // 任务卡 + SUB/TASK chips
  if (typeof refreshMemory === 'function') refreshMemory(); // 记忆列表
  if (typeof refreshSkills === 'function') refreshSkills(); // 技能列表
  if (LAST_CHIP && typeof setChip === 'function') setChip(LAST_CHIP.text, LAST_CHIP.color);
  if (LAST_LLM_READY !== null) $('llm-chip').textContent = LAST_LLM_READY ? i18t('LLM 已配置') : i18t('LLM 未配置');
  if (typeof updateScopeTip === 'function') updateScopeTip(LAST_MENTIONS);
  document.querySelectorAll('#feed .msg[data-no] .msg-ops').forEach(ops =>   // 星标/删除按钮提示随语言重译
    refreshOps(null, ops, ops.closest('.msg').classList.contains('starred')));
});

/* ---------- 启动 ---------- */
async function boot() {
  applyLang(localStorage.getItem(I18N_LANG_KEY) || 'zh');
  fetch('/api/health').then(r => r.json()).then(h => {
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.textContent = 'v' + (h.version || '?');
    chip.title = '页面代码版本：若与你发布的版本不符，说明浏览器在跑旧缓存（Ctrl+F5 强刷）';
    $('llm-chip').after(chip);
  }).catch(() => {});
  await refreshRooms();
  await refreshIdentities();
  renderToolCheckboxes([]);   // 初始即渲染工具复选框（新建卡状态），一键白名单随时可用
  await refreshSkills();
  applyAppearance();
  $('lang-select').value = I18N_LANG;
  await loadRoomView();
  connect();
}
boot();
