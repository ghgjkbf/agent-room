/* Agent Room 前端：WS 连接 + 消息流渲染 + 身份卡编辑器 + @提及。
   第 2 步：双 Agent 并行回复、群内标签、P0 interrupt。 */

const $ = (id) => document.getElementById(id);
let ws = null;
let agents = [];        // [{id,name,identity_id,identity_label,chat_turns}]
let identities = [];    // [{id,label,persona,responsibilities,tools_allow,budget_turns,version}]
const TOOL_OPTIONS = ['fs.read', 'fs.write', 'fs.list', 'shell.run', 'git.status', 'memory.query'];

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
    let name = kind === 'human' ? '你' : kind === 'orchestrator' ? 'CEO 编排' : msg.sender.id;
    if (kind === 'agent') {
      const meta = agents.find(a => a.id === msg.sender.id);
      name = meta ? meta.name : name;
    }
    who.textContent = name;
    const lbl = document.createElement('span');
    lbl.className = 'lbl';
    lbl.textContent = kind === 'agent'
      ? (msg.mentions && msg.mentions.length ? '@' + msg.mentions.join(',@') : agentLabel(msg.sender.id))
      : kind === 'human' ? '广播' : kind === 'orchestrator' ? 'L1 编排' : 'system';
    who.appendChild(lbl);
    const body = document.createElement('div');
    body.className = 'body';
    body.textContent = msg.payload.text;
    el.appendChild(who); el.appendChild(body);
  }
  feed.appendChild(el);
  feed.scrollTop = feed.scrollHeight;
  return el;
}

function agentLabel(id) {
  const m = agents.find(a => a.id === id);
  return (m && m.identity_label) ? m.identity_label : '未绑定';
}

/* 流式合并：并行 Agent 的片段会交替到达（A,B,A,B…），不能共用单一游标，
   必须按 agent_id 各自维护活跃气泡；人类/系统消息终结全部活跃气泡。 */
let streaming = {}; // agentId -> {el, body}

function finalizeStreaming() { streaming = {}; }

function handleAgentChunk(msg) {
  const st = streaming[msg.sender.id];
  if (st && document.body.contains(st.el)) {
    st.body.textContent += msg.payload.text;
    return;
  }
  const bubble = addBubble(msg);
  bubble.dataset.agent = msg.sender.id;
  streaming[msg.sender.id] = { el: bubble, body: bubble.querySelector('.body') };
}

function handleMessage(msg) {
  clearTimeout(handleMessage._t);

  if (msg.type === 'system') { finalizeStreaming(); addBubble(msg); return; }
  if (msg.type === 'deliver') { finalizeStreaming(); addDeliverBubble(msg); refreshFiles(); return; }
  if (!(msg.type === 'chat' && msg.sender.kind === 'agent' && msg.payload.text)) {
    finalizeStreaming();
    addBubble(msg);
    return;
  }

  $('typing').style.display = 'block';
  $('typing').textContent = `${agentLabel(msg.sender.id)} 正在输入…`;
  handleAgentChunk(msg);
  handleMessage._t = setTimeout(() => { $('typing').style.display = 'none'; }, 500);
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
    link.title = '点击在文件面板预览';
    link.addEventListener('click', () => {
      openPanel('rp-files');
      previewFile(path);
    });
    el.appendChild(link);
  }
}

/* 工具调用事件（不落库的广播）：在活跃气泡下附一行小字 */
function showToolEvent(msg) {
  const st = streaming[msg.sender.id];
  if (!st || !document.body.contains(st.el)) return;
  let note = st.el.querySelector('.tool-note');
  if (!note) {
    note = document.createElement('div');
    note.className = 'tool-note';
    st.el.appendChild(note);
  }
  note.textContent = `🔧 ${msg.tool_event.name} ${msg.tool_event.result_ok ? '✓' : '✗'}`;
}

/* ---------- WS ---------- */
function connect() {
  ws = new WebSocket('ws://' + location.host + '/ws/default');
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
function setChip(text, color) { $('ws-chip').textContent = text; $('ws-chip').style.color = color; }

/* 左栏会话项的「最后一条」摘要 */
function updateConvoLast(msg) {
  const text = (msg.payload && msg.payload.text) || '';
  if (!text) return;
  let who = '你';
  if (msg.sender.kind === 'agent') {
    const meta = agents.find(a => a.id === msg.sender.id);
    who = meta ? meta.name : msg.sender.id;
  } else if (msg.sender.kind === 'system') who = '';
  $('convo-last').textContent = (who ? who + '：' : '') + text.slice(0, 40);
  const t = new Date();
  $('convo-time').textContent = `${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`;
}

function sendText() {
  const ta = $('draft');
  const text = ta.value.trim();
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
  ta.value = ''; hideMentionPop();
  updateScopeTip(mentions);
  ws.send(JSON.stringify({ type: 'chat', text, mentions }));
}
function updateScopeTip(mentions) {
  $('scope-tip').textContent = mentions.length
    ? `定向投递 → ${mentions.map(id => (agents.find(a => a.id === id) || {}).name || id).join(', ')}`
    : '广播模式：全体 Agent 可见可回';
}

/* ---------- 成员列表（含换绑 + 外部成员） ---------- */
async function refreshMembers() {
  const res = await fetch('/api/agents'); agents = await res.json();
  $('agent-count').textContent = agents.length;
  $('convo-count').textContent = '· ' + agents.length + ' 成员';
  $('member-list').innerHTML = agents.map((a) => {
    const external = a.kind === 'external';
    const online = a.status === 'online';
    const badge = external
      ? `<span class="kind-badge external">${online ? '🟢' : '⚪'} 外部${online ? '在线' : '离线'}</span>`
      : `<span class="kind-badge internal">内置</span>`;
    const bindUi = external
      ? ''
      : `<select data-agent="${a.id}" title="换绑身份卡">
          <option value="">— 未绑定 —</option>
          ${identities.map(c => `<option value="${c.id}" ${c.id === a.identity_id ? 'selected' : ''}>${c.label}</option>`).join('')}
        </select>`;
    const tokUi = external
      ? `<button class="copy-tok" data-agent="${a.id}" data-name="${a.name}">复制令牌</button>`
      : '';
    return `
    <div class="member">
      <div class="avatar">${(a.name)[0].toUpperCase()}</div>
      <div style="min-width:0;">
        <div>${a.name}${badge}</div>
        <div class="lbl" style="background:var(--brand-soft);color:var(--brand-ink);font-size:10px;padding:0 6px;border-radius:999px;display:inline-block;">${a.identity_label ? a.identity_label + (external ? '' : ' · 轮数 ' + a.chat_turns) : '未绑定身份卡'}</div>
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
  $('member-list').querySelectorAll('.copy-tok').forEach(btn =>
    btn.addEventListener('click', async () => {
      const r = await fetch(`/api/agents/${btn.dataset.agent}/rotate-token`, { method: 'POST' });
      if (!r.ok) return alertSys((await r.json()).detail || '重发失败');
      const d = await r.json();
      await navigator.clipboard.writeText(d.token).catch(() => {});
      showExternalResult({ id: btn.dataset.agent, name: btn.dataset.name, token: d.token });
      refreshMembers();
    }));
  $('agent-count').textContent = agents.length;
}

/* ---------- 身份卡编辑器 ---------- */
let editingId = null; // null=新建

async function refreshIdentities() {
  const res = await fetch('/api/identities'); identities = await res.json();
  $('id-list').innerHTML = identities.map(c => `
    <div class="idcard" data-id="${c.id}">
      🪪 <b>${c.label}</b> · ${c.responsibilities.join('、') || '无职责'}
      <span class="cv">v${c.version} · ${c.budget_turns}轮</span>
    </div>`).join('');
  $('id-list').querySelectorAll('.idcard').forEach(el =>
    el.addEventListener('click', () => {
      $('id-list').querySelectorAll('.idcard').forEach(x => x.classList.remove('sel'));
      el.classList.add('sel');
      loadCard(identities.find(c => c.id === el.dataset.id));
    }));
}

function renderToolCheckboxes(selected) {
  $('id-tools').innerHTML = TOOL_OPTIONS.map(t => `
    <label><input type="checkbox" value="${t}" ${selected.includes(t) ? 'checked' : ''}>${t}</label>`).join('');
}
function loadCard(c) {
  editingId = c ? c.id : null;
  $('id-label').value = c ? c.label : '';
  $('id-persona').value = c ? c.persona : '';
  $('id-resp').value = c ? c.responsibilities.join('、') : '';
  renderToolCheckboxes(c ? c.tools_allow : []);
  $('id-turns').value = c ? c.budget_turns : 6;
  $('id-turns-v').textContent = $('id-turns').value;
}

async function saveCard() {
  const card = {
    label: $('id-label').value.trim(),
    persona: $('id-persona').value.trim(),
    responsibilities: $('id-resp').value.split(/[、,,]/).map(s => s.trim()).filter(Boolean),
    tools_allow: [...$('id-tools').querySelectorAll('input:checked')].map(i => i.value),
    budget_turns: parseInt($('id-turns').value, 10),
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
  pop.innerHTML = `<div class="mp-item all" data-id="__all__">📣 全体成员（广播）</div>` +
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
document.querySelectorAll('[data-panel]').forEach(b => { b.dataset.panel = ''; });
$('btn-panel-files').dataset.panel = 'rp-files';
$('btn-panel-members').dataset.panel = 'rp-members';
$('btn-panel-settings').dataset.panel = 'rp-identity';

$('btn-burger') && $('btn-burger').addEventListener('click', () => $('sidebar').classList.toggle('collapsed'));
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
  $('llm-chip').textContent = r.llm_ready ? 'LLM 已配置' : 'LLM 未配置';
  alertSys(r.llm_ready ? 'LLM 配置已保存，后续回复将走真实模型。' : '配置不完整。');
});
$('btn-new-id').addEventListener('click', () => { loadCard(null); });
$('btn-save-id').addEventListener('click', saveCard);
$('btn-del-id').addEventListener('click', deleteCard);
$('id-turns').addEventListener('input', () => $('id-turns-v').textContent = $('id-turns').value);

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
  $('ext-identity').innerHTML = '<option value="">— 暂不绑定 —</option>' +
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
    body: JSON.stringify({ name, identity_id: $('ext-identity').value || null }),
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
  const res = await fetch('/api/files?room_id=default');
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
      <span class="file-author ${f.author === 'human' ? 'hum' : ''}">${f.author === 'human' ? '👤' : '🤖'}${f.author === 'human' ? '人类' : f.author}</span>
      <button class="file-del" data-path="${p}" title="删除">✕</button>
    </div>`;
  }).join('') : '<div class="hint">（暂无文件；Agent 交付物与人类上传都会出现在这里）</div>';

  $('file-tree').querySelectorAll('.file-name').forEach(el =>
    el.addEventListener('click', () => previewFile(el.closest('.file-row').dataset.path)));
  $('file-tree').querySelectorAll('.file-del').forEach(el =>
    el.addEventListener('click', async () => {
      const p = el.dataset.path;
      if (!confirm(`删除文件 ${p}？`)) return;
      await fetch('/api/files', {
        method: 'DELETE', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_id: 'default', path: p }),
      });
      if (previewedFile && previewedFile.path === p) { previewedFile = null; $('file-preview').value = ''; $('file-preview-head').textContent = '点文件名预览'; }
      refreshFiles();
    }));
  $('file-count').textContent = files.length;
}

async function previewFile(path) {
  const res = await fetch('/api/files/content?room_id=default&path=' + encodeURIComponent(path));
  if (!res.ok) return alertSys((await res.json()).detail || '读取失败');
  const d = await res.json();
  previewedFile = { path: d.path, version: d.version };
  $('file-preview').value = d.content;
  $('file-preview-head').textContent = `${d.path} · v${d.version} · 作者 ${d.author}`;
}

$('btn-upload').addEventListener('click', () => $('file-input').click());
$('file-input').addEventListener('change', async () => {
  const f = $('file-input').files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append('file', f);
  const r = await fetch('/api/files/upload?room_id=default', { method: 'POST', body: fd });
  if (!r.ok) return alertSys('上传失败：' + ((await r.json()).detail || r.status));
  const d = await r.json();
  alertSys(`已上传 ${d.path}（v${d.version}）`);
  $('file-input').value = '';
  refreshFiles();
});
$('btn-save-preview').addEventListener('click', async () => {
  if (!previewedFile) return alertSys('请先点文件名选择要编辑的文件');
  const r = await fetch('/api/files/write', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      room_id: 'default', path: previewedFile.path,
      content: $('file-preview').value, base_version: previewedFile.version,
    }),
  });
  if (!r.ok) {
    const d = await r.json();
    if (d.detail && d.detail.latest_version !== undefined) {
      alertSys(`版本冲突：当前已是 v${d.detail.latest_version}，已为你刷新内容，请重新保存。`);
      previewFile(previewedFile.path); refreshFiles();
    } else alertSys('保存失败：' + (d.detail || JSON.stringify(d)));
    return;
  }
  const d = await r.json();
  alertSys(`已保存 ${d.path}（v${d.version}）`);
  previewedFile.version = d.version;
  $('file-preview-head').textContent = `${d.path} · v${d.version} · 作者 你`;
  refreshFiles();
});

/* ---------- 任务（CEO 编排闭环）与向量记忆 ---------- */
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
const SUB_CHIP = { pending: '待派发', dispatched: '执行中', accepted: '已验收', rejected: '已打回' };
const TASK_ST = { awaiting_confirm: '待确认', running: '执行中', paused: '已熔断·待裁决', done: '已完成', aborted: '已作废' };

async function fetchTasks() {
  const res = await fetch('/api/tasks?room_id=default');
  if (!res.ok) return;
  renderTasks((await res.json()).tasks || []);
}
function renderTasks(tasks) {
  const el = $('task-list');
  if (!tasks.length) {
    el.innerHTML = '<div class="hint">（暂无任务；在上方填写目标并下达，CEO 将拆解为排产单）</div>';
    return;
  }
  el.innerHTML = tasks.map(t => {
    const subs = (t.subtasks || []).map(s =>
      `<div class="subtask"><span class="st-chip st-${s.status}">${SUB_CHIP[s.status] || s.status_label}</span>` +
      `<span>#${s.seq} ${esc(s.title)} → ${esc(s.assignee)}${s.retries ? `（打回${s.retries}次）` : ''}</span></div>`).join('');
    let actions = '';
    if (t.status === 'awaiting_confirm')
      actions = `<button class="btn primary sm" data-act="confirm" data-id="${t.id}">✓ 确认开工</button>` +
                `<button class="btn danger-full sm" data-act="abort" data-id="${t.id}">作废</button>`;
    else if (t.status === 'paused')
      actions = `<button class="btn primary sm" data-act="resume" data-id="${t.id}">继续执行</button>` +
                `<button class="btn danger-full sm" data-act="abort" data-id="${t.id}">终止</button>`;
    return `<div class="task-card"><div class="task-goal">🎯 ${esc(t.goal)}</div>` +
      `<div class="task-status">状态：${TASK_ST[t.status] || t.status_label}</div>${subs}` +
      (actions ? `<div class="task-actions">${actions}</div>` : '') + '</div>';
  }).join('');
  el.querySelectorAll('button[data-act]').forEach(b => b.addEventListener('click', async () => {
    const act = b.dataset.act;
    const url = `/api/tasks/${b.dataset.id}/${act === 'abort' ? 'abort' : 'confirm'}`;
    const r = await (await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: act }),
    })).json();
    if (!r.ok) return alertSys(r.detail || '操作失败');
    alertSys(act === 'abort' ? '任务已作废。' : act === 'resume' ? '已恢复执行，CEO 按依赖继续派发。' : '已确认开工，CEO 按依赖派发排产单。');
    fetchTasks();
  }));
}
$('btn-issue-task').addEventListener('click', () => {
  const v = $('task-goal').value.trim();
  if (!v) return alertSys('请先填写任务目标');
  if (!ws || ws.readyState !== WebSocket.OPEN) return alertSys('连接未就绪');
  ws.send(JSON.stringify({ type: 'task', text: v }));
  $('task-goal').value = '';
  alertSys('任务已下达，CEO 正在拆解…');
});

async function refreshMemory() {
  const res = await fetch('/api/memory?room_id=default');
  if (!res.ok) return;
  const d = await res.json();
  const s = d.stats || {};
  const agentPart = Object.entries(s.agents || {}).map(([a, n]) => `${a}:${n}`).join('，');
  $('mem-stats').textContent = `公共记忆 ${s.public || 0} 条` + (agentPart ? `；私有记忆 ${agentPart}` : '');
  const items = d.recent || [];
  $('mem-list').innerHTML = items.length
    ? items.map(r => `<div class="mem-item">${esc(r.text)}<div class="mem-meta">${esc(r.scope)} · ${esc((r.created_at || '').slice(0, 16).replace('T', ' '))}</div></div>`).join('')
    : '<div class="hint">（暂无记忆；任务验收通过后自动沉淀）</div>';
}

/* ---------- 启动 ---------- */
async function boot() {
  const data = await (await fetch('/api/room/default')).json();
  $('llm-chip').textContent = data.llm_ready ? 'LLM 已配置' : 'LLM 未配置';
  await refreshIdentities();
  await refreshMembers();
  await refreshFiles();
  await fetchTasks();
  await refreshMemory();
  connect();
  (data.history || []).forEach(m => handleMessage(m));
}
boot();
