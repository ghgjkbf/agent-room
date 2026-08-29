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
    assert "用户服务助手" in md and "行为规范" in md
    assert "职责边界" in build_system_prompt("agent_a", None)
    assert "群聊管家" in build_system_prompt("agent_b", None)
    assert load_agent_md("agent_nonexist") == ""
    # 绑定身份卡时以身份卡为准（md 不注入）
    prompt = build_system_prompt("agent_a", {"label": "测试卡", "persona": "",
                                             "responsibilities": [], "tools_allow": []})
    assert "测试卡" in prompt and "职责边界" not in prompt


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
