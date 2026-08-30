"""第 6 步增强：内部技能库 / 多房间（room_members）/ Agent 专属 md。"""

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.core.config import settings
from app.core.db import db
from app.core.message import now_cst
from app.skills import store


# ---------- 技能库 ----------

def test_skill_crud_roundtrip():
    name = f"t_{uuid.uuid4().hex[:8]}"
    try:
        store.write_skill(name, "# 测试技能\n内容")
        assert any(s["name"] == name for s in store.list_skills())
        assert "测试技能" in store.read_skill(name)["content"]
        store.write_skill(name, "更新版")  # 同名覆盖
        assert store.read_skill(name)["content"] == "更新版"
        store.delete_skill(name)
        with pytest.raises(FileNotFoundError):
            store.read_skill(name)
    finally:
        try:
            store.delete_skill(name)
        except Exception:
            pass


def test_skill_name_validation():
    with pytest.raises(ValueError):
        store.read_skill("../escape")  # 路径逃逸拒绝
    with pytest.raises(ValueError):
        store.write_skill("a/b", "x")  # 路径分隔符拒绝
    with pytest.raises(ValueError):
        store.write_skill("a b", "x")  # 空格拒绝
    with pytest.raises(ValueError):
        store.write_skill("ok", "x" * 300_000)  # 超限拒绝
    # 中文技能名合法（文件名安全字符），用后即清
    store.write_skill("周报模板", "# 中文技能")
    try:
        assert "中文技能" in store.read_skill("周报模板")["content"]
    finally:
        store.delete_skill("周报模板")


def test_skill_tools_via_exec():
    """skills.list / skills.read 经工具执行器可用（白名单内）。"""
    from app.files.tools import exec_fs_tool_sync, filter_tools

    name = f"t_{uuid.uuid4().hex[:8]}"
    store.write_skill(name, "技能内容X")
    try:
        r = json_loads(exec_fs_tool_sync("default", "agent_a", "skills.list", {}))
        assert r["ok"] and name in r["skills"]
        r = json_loads(exec_fs_tool_sync("default", "agent_a", "skills.read", {"name": name}))
        assert r["ok"] and "技能内容X" in r["content"]
        r = json_loads(exec_fs_tool_sync("default", "agent_a", "skills.read", {"name": "nope"}))
        assert not r["ok"]
        # 白名单过滤：只勾 skills.read 时拿不到 fs 工具定义
        tools = filter_tools(["skills.read"])
        assert {t["function"]["name"] for t in tools} == {"skills.read"}
    finally:
        store.delete_skill(name)


def json_loads(s):
    import json
    return json.loads(s)


# ---------- 多房间 ----------

def _mk_room_with(agent_ids):
    rid = f"room_t_{uuid.uuid4().hex[:6]}"
    with db() as conn:
        conn.execute("INSERT INTO rooms (id, name, created_at) VALUES (?,?,?)",
                     (rid, "测试群", now_cst()))
        for aid in agent_ids:
            conn.execute(
                "INSERT OR IGNORE INTO room_members (room_id, agent_id, joined_at)"
                " VALUES (?,?,?)", (rid, aid, now_cst()))
    return rid


def _cleanup_room(rid):
    with db() as conn:
        conn.execute("DELETE FROM room_members WHERE room_id=?", (rid,))
        conn.execute("DELETE FROM rooms WHERE id=?", (rid,))


def test_room_membership_isolation():
    """A 在群1、B 在群2：成员查询互不可见（与 _ws_loop/orchestrator 同一 JOIN）。"""
    r1 = _mk_room_with(["agent_a"])
    r2 = _mk_room_with(["agent_b"])
    try:
        def members(rid):
            with db() as conn:
                rows = conn.execute(
                    "SELECT a.id FROM room_members m JOIN agents a ON a.id=m.agent_id"
                    " WHERE m.room_id=? ORDER BY a.id", (rid,)).fetchall()
            return [r["id"] for r in rows]
        assert members(r1) == ["agent_a"]
        assert members(r2) == ["agent_b"]
    finally:
        _cleanup_room(r1)
        _cleanup_room(r2)


def test_rooms_api_create_and_delete():
    from app.agents.routes import delete_agent  # 触发路由模块导入
    from app.rooms.routes import create_room, delete_room, list_rooms

    async def _run():
        class _Body:
            name = "  API测试群  "
            agent_ids = ["agent_a", "agent_b"]
        r = await create_room(_Body())
        assert r["ok"] and r["members"] == ["agent_a", "agent_b"]
        rid = r["id"]
        rooms = await list_rooms()
        assert any(x["id"] == rid and x["name"] == "API测试群" and x["member_count"] == 2
                   for x in rooms)
        # default 不可删
        with pytest.raises(Exception) as ei:
            await delete_room("default")
        assert "默认房间" in str(ei.value)
        assert (await delete_room(rid))["ok"]

    asyncio.run(_run())


def test_list_agents_by_room():
    from app.agents.routes import list_agents

    rid = _mk_room_with(["agent_a"])
    try:
        only_a = asyncio.run(list_agents(room_id=rid))
        assert [a["id"] for a in only_a] == ["agent_a"]
        registry = asyncio.run(list_agents(all=1))
        assert {a["id"] for a in registry} >= {"agent_a", "agent_b"}
    finally:
        _cleanup_room(rid)


# ---------- Agent 专属 md ----------

def test_agent_md_injected():
    from app.agents.responder import build_system_prompt, load_agent_md

    md = load_agent_md("agent_a")
    assert "用户服务助手" in md and "场景应对" in md and "决策优先级" in md
    assert "职责清单" in build_system_prompt("agent_a", None)
    assert "群聊管家" in build_system_prompt("agent_b", None)
    assert load_agent_md("agent_nonexist") == ""
    # 绑定身份卡：卡提供标签/白名单，岗位手册仍共存注入
    prompt = build_system_prompt("agent_a", {"label": "测试卡", "persona": "",
                                             "responsibilities": [], "tools_allow": []})
    assert "测试卡" in prompt and "场景应对" in prompt


# ---------- 验收真实性核验（优化迭代） ----------

def test_extract_claimed_paths():
    from app.orchestrator.ceo import extract_claimed_paths

    t = ("已写入 docs/result_23.md 与 docs/方案v2.md；结论见 notes.md。"
         "版本号 1.2 和 README 不是文件。群里聊了 v1.5。")
    paths = extract_claimed_paths(t)
    assert "docs/result_23.md" in paths and "docs/方案v2.md" in paths
    assert "notes.md" in paths
    assert all("1.2" not in p and "v1.5" not in p for p in paths)
    assert extract_claimed_paths("没写任何文件") == []


def test_verify_claims_against_workspace(tmp_path, monkeypatch):
    """声称存在且确实写了 → ✓；声称未写 → ✗；硬核验打回。"""
    from app.files import workspace
    from app.orchestrator.ceo import Orchestrator

    room = f"vf_{uuid.uuid4().hex[:6]}"
    orch = Orchestrator(room)
    workspace.write_file(room, "docs/真实交付.md", "内容X", author="agent_a")
    try:
        t = "已写入 docs/真实交付.md，另有 docs/幻觉文件.md。"
        checks = orch._verify_claims(t)
        assert any(c.startswith("✓ docs/真实交付.md") for c in checks)
        assert any(c.startswith("✗ docs/幻觉文件.md") for c in checks)

        # 真实 LLM 模式 + 声称全部缺失 + 验收员被骗放行 → 仍硬打回
        class FakeBus:
            room_id = room
            published = []
            listeners = []
            registry_ref = None
            async def publish(self, m): self.published.append(m)
            async def broadcast_raw(self, d): pass
        bus = FakeBus()
        with db() as conn:
            ts = now_cst()
            conn.execute(
                "INSERT INTO tasks (id, room_id, goal, status, plan_json, created_at,"
                " updated_at) VALUES (?,?,?,?,?,?,?)",
                ("task_vf", room, "目标", "running", "[]", ts, ts))
            conn.execute(
                "INSERT INTO subtasks (id, task_id, room_id, seq, title, guidance,"
                " assignee, depends_on, status, created_at) VALUES"
                " ('task_vf_s1','task_vf',?,1,'标题','要求','agent_a','[]','dispatched',?)",
                (room, ts))
        sub = dict(conn_row("task_vf_s1"))
        # 纯幻觉场景：声称的文件全部不存在 → 即使验收员被骗放行也硬打回
        t = "已写入 docs/幻觉文件.md。"
        monkeypatch.setattr(settings, "llm_base_url", "http://fake")
        monkeypatch.setattr(settings, "llm_api_key", "fake")
        monkeypatch.setattr(settings, "llm_model", "fake")

        async def _gullible(goal, s_, text, checks=None):
            return {"accept": True, "reason": "验收员被骗"}
        async def _run():
            orch._verdict = _gullible
            await orch._accept(bus, sub, t)
        import asyncio
        asyncio.run(_run())
        receipts = [m for m in bus.published if m.type == "receipt"]
        assert receipts and receipts[0].payload_text.startswith("验收打回")
        assert "均不存在" in receipts[0].payload_text
        # last_receipt 已落库（任务面板展示用）
        with db() as conn:
            row = conn.execute("SELECT last_receipt, status, retries FROM subtasks WHERE id='task_vf_s1'").fetchone()
        assert row["status"] == "dispatched" and row["retries"] == 1
        assert "均不存在" in row["last_receipt"]
    finally:
        workspace.delete_file(room, "docs/真实交付.md")
        with db() as conn:
            conn.execute("DELETE FROM subtasks WHERE task_id='task_vf'")
            conn.execute("DELETE FROM tasks WHERE id='task_vf'")


def conn_row(sub_id):
    with db() as conn:
        return conn.execute("SELECT * FROM subtasks WHERE id=?", (sub_id,)).fetchone()


def test_gateway_list_rooms_scoped():
    """list_rooms 只返回成员所在房间。"""
    from app.mcp_gateway.server import build_mcp_server
    from app.agents.routes import create_external_agent

    rid = _mk_room_with([])
    srv = build_mcp_server(None)
    tool = [t for t in __import__("asyncio").run(srv.list_tools()) if t.name == "list_rooms"][0]

    async def _call(aid, tok):
        fn = srv._tool_manager._tools["list_rooms"].fn
        import json as _json
        return _json.loads(fn(agent_id=aid, token=tok))

    async def _run():
        class _Body:
            name = "多房间成员"
            identity_id = None
            room_id = rid
        created = await create_external_agent(_Body())
        r = await _call(created["id"], created["token"])
        assert r["ok"] and r["rooms"] == [{"id": rid, "name": "测试群"}]
        # 误传他人房间不在列表 → join 校验拒绝（_require_member）
        from app.mcp_gateway.server import _require_member
        with pytest.raises(PermissionError):
            _require_member(created["id"], "room_other")
        from app.agents.routes import delete_agent
        await delete_agent(created["id"])

    try:
        asyncio.run(_run())
    finally:
        _cleanup_room(rid)


def test_memory_query_tool_public_only(tmp_path, monkeypatch):
    """memory.query 工具只返回公共记忆，任何 Agent 的私有记忆都不泄漏。"""
    import asyncio
    import tempfile
    from app.files.tools import exec_fs_tool, filter_tools
    from app.memory.hub import MemoryHub

    hub = MemoryHub(str(tmp_path))
    monkeypatch.setattr("app.memory.hub.hub", hub)

    async def _run():
        await hub.write_public("rm", "口号任务的结论：智聚群力", {}, "2026-08-29T10:00:00")
        await hub.write_private("agent_x", "某人的私有笔记：绝密", {}, "2026-08-29T10:01:00")
        import json as _json
        r = _json.loads(await exec_fs_tool("rm", "agent_b", "memory.query",
                                           {"query": "口号结论"}))
        assert r["ok"] and "智聚群力" in r["hits"][0]["text"]
        assert all("绝密" not in h["text"] for h in r["hits"])
        # 白名单独立：只勾 memory.query 时拿不到 fs 工具
        tools = filter_tools(["memory.query"])
        assert {tl["function"]["name"] for tl in tools} == {"memory.query"}

    asyncio.run(_run())


def test_overreach_announcement_wakes_agent_b(monkeypatch):
    """越权调用 → ⚠ 广播 + 系统 @agent_b 并拉起其通报回应（监管闭环）。"""
    import asyncio
    import json as _json
    from app.agents import responder
    from app.core.config import settings

    class _Msg:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class FakeBus:
        def __init__(self):
            self.published = []
            self.registry_ref = None
            self.room_id = "default"
        async def publish(self, m):
            self.published.append(m)
        async def broadcast_raw(self, d):
            pass

    class FakeRegistry:
        @staticmethod
        def get(rid):
            return bus

    class _Delta:
        def __init__(self, content=None, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls
    class _Chunk:
        def __init__(self, content=None, tool_calls=None):
            self.choices = [type("C", (), {"delta": _Delta(content, tool_calls)})()]

    class _Msg0:
        pass

    bus = FakeBus()
    monkeypatch.setattr(settings, "llm_base_url", "http://fake")
    monkeypatch.setattr(settings, "llm_api_key", "fake")
    monkeypatch.setattr(settings, "llm_model", "fake")
    monkeypatch.setattr(responder, "load_identity", lambda aid: {
        "id": "c", "label": "受限卡", "persona": "", "responsibilities": [],
        "tools_allow": ["fs.read"]})

    def _tc():
        fn = type("F", (), {"name": "fs.write", "arguments": _json.dumps({"path": "x.md", "content": "y"})})
        return [type("TC", (), {"index": 0, "id": "c1", "function": fn()})()]

    calls = {"n": 0}
    class _Iter:
        def __init__(self, items):
            self._items = items
        def __aiter__(self):
            async def _gen():
                for it in self._items:
                    yield it
            return _gen()

    class _Completions:
        async def create(self, *a, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return _Iter([_Chunk(tool_calls=_tc())])
            return _Iter([_Chunk(content="知道了")])

    class _Chat:
        completions = _Completions()
    class _Client:
        chat = _Chat()

    async def _fake_create(*a, **kw):
        return _Client()

    async def _run():
        import types
        monkeypatch.setattr(responder.AsyncOpenAI, "chat", _Chat(), raising=False)
        orig_init = responder.AsyncOpenAI.__init__
        monkeypatch.setattr(
            responder.AsyncOpenAI, "__init__",
            lambda self, **kw: orig_init(self, **kw) or None, raising=False)
        # 直接替换 client 构造：monkeypatch AsyncOpenAI 为返回 _Client 的类型
        monkeypatch.setattr(responder, "AsyncOpenAI", lambda **kw: _Client())

        gen = responder.run_turn("agent_x", responder.load_identity("agent_x") if False else {
            "id": "c", "label": "受限卡", "persona": "", "responsibilities": [],
            "tools_allow": ["fs.read"]}, "hi", bus_registry=FakeRegistry, room_id="default")
        kinds = [k async for k, _ in gen]
        assert "tool" in kinds
        await asyncio.sleep(2.5)  # 让 B 的通报回应跑完（占位 0.35s/片）
        warns = [m for m in bus.published if "越权拦截" in m.payload_text]
        assert warns and warns[0].mentions == ["agent_b"]
        import os
        if os.environ.get("DBG"):
            print("PUBLISHED:", [(m.type, getattr(m, "sender_id", None),
                                  (m.payload_text or "")[:30]) for m in bus.published])
        b_replies = [m for m in bus.published
                     if m.type == "chat" and m.sender_id == "agent_b"]
        assert b_replies, "Agent B 未被拉起通报"

    asyncio.run(_run())


def test_capability_tools(tmp_path, monkeypatch):
    """能力工具层：shell.run / skills.write / browser.open 负例 / 白名单独立。"""
    import asyncio
    import json as _json
    from app.files.tools import exec_fs_tool, filter_tools

    async def _run():
        # shell.run：真实执行
        r = _json.loads(await exec_fs_tool("default", "t", "shell.run",
                                           {"command": "echo caps-ok"}))
        assert r["ok"] and "caps-ok" in r["output"]
        # skills.write：Agent 自建技能
        r = _json.loads(await exec_fs_tool("default", "t", "skills.write",
                                           {"name": "agent-made", "content": "# 自建"}))
        assert r["ok"]
        from app.skills import store
        assert "自建" in store.read_skill("agent-made")["content"]
        store.delete_skill("agent-made")
        # browser.open 负例
        r = _json.loads(await exec_fs_tool("default", "t", "browser.open",
                                           {"url": "ftp://x"}))
        assert not r["ok"]
        # 白名单独立
        tools = filter_tools(["shell.run"])
        assert {tl["function"]["name"] for tl in tools} == {"shell.run"}

    asyncio.run(_run())


def test_skill_import_from_local(tmp_path):
    """从本机目录导入 SKILL.md（目录名即技能名）。"""
    import asyncio
    import os
    import sys as _sys

    src = tmp_path / "skills-src" / "my-cool-skill"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text("# cool\n说明", encoding="utf-8")
    # 嵌套目录（应跳过无 SKILL.md 的）
    (tmp_path / "skills-src" / "empty").mkdir()

    from app.skills import routes as sr, store

    class _Body:
        source = str(tmp_path / "skills-src")
        limit = 200

    async def _run():
        r = await sr.import_local_skills(_Body())
        return r

    r = asyncio.run(_run())
    assert r["ok"] and r["imported"] == ["my-cool-skill"]
    assert "cool" in store.read_skill("my-cool-skill")["content"]
    store.delete_skill("my-cool-skill")
    # 不存在的目录
    class _Bad:
        source = str(tmp_path / "nope")
        limit = 10
    r = asyncio.run(sr.import_local_skills(_Bad()))
    assert not r["ok"]
