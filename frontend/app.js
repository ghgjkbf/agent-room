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
  el.className = 'msg ' + (kind === 'human' ? 'human' : kind === 'system' ? 'system' : 'agent');

  if (kind === 'system') {
    el.textContent = msg.payload.text;
  } else {
    const who = document.createElement('div');
    who.className = 'who';
    let name = kind === 'human' ? '你' : msg.sender.id;
    if (kind === 'agent') {
      const meta = agents.find(a => a.id === msg.sender.id);
      name = meta ? meta.name : name;
    }
    who.textContent = name;
    const lbl = document.createElement('span');
    lbl.className = 'lbl';
    lbl.textContent = kind === 'agent'
      ? (msg.mentions && msg.mentions.length ? '@' + msg.mentions.join(',@') : agentLabel(msg.sender.id))
      : kind === 'human' ? '广播' : 'system';
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

/* ---------- WS ---------- */
function connect() {
  ws = new WebSocket('ws://' + location.host + '/ws/default');
  ws.onopen = () => setChip('● 已连接', '#10b981');
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    handleMessage(msg);
    if (msg.type === 'system') refreshMembers(); // 熔断等系统事件后刷新轮数
  };
  ws.onclose = () => { setChip('● 已断开，3 秒重连', '#b42318'); setTimeout(connect, 3000); };
  ws.onerror = () => ws.close();
}
function setChip(text, color) { $('ws-chip').textContent = text; $('ws-chip').style.color = color; }

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

/* ---------- Tab / 面板交互 ---------- */
document.querySelectorAll('.tab').forEach((t) =>
  t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((x) => x.classList.toggle('on', x === t));
    document.querySelectorAll('.pane').forEach((p) => p.classList.toggle('on', p.id === t.dataset.pane));
  }));
document.querySelectorAll('.bp-tab').forEach((t) =>
  t.addEventListener('click', () => {
    document.querySelectorAll('.bp-tab').forEach((x) => x.classList.toggle('on', x === t));
    document.querySelectorAll('.bp-body').forEach((b) => b.classList.toggle('on', b.id === t.dataset.bp));
  }));

$('btn-burger').addEventListener('click', () => $('sidebar').classList.toggle('collapsed'));
$('btn-send').addEventListener('click', sendText);
$('draft').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText(); }
});
$('draft').addEventListener('input', () => {
  const v = $('draft').value;
  if (v.endsWith('@')) showMentionPop();
  else { hideMentionPop(); updateScopeTip(parseMentionsFromText(v)); }
});
$('btn-stop-all').addEventListener('click', () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'interrupt', text: '停止全部' }));
  }
});
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

/* ---------- 启动 ---------- */
async function boot() {
  const data = await (await fetch('/api/room/default')).json();
  $('llm-chip').textContent = data.llm_ready ? 'LLM 已配置' : 'LLM 未配置';
  await refreshIdentities();
  await refreshMembers();
  connect();
  (data.history || []).forEach(m => handleMessage(m));
}
boot();
