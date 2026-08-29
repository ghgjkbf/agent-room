"""第 6 步增强：内部技能库 / 多房间（room_members）/ Agent 专属 md。"""

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

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
        store.write_skill("含中文", "x")
    with pytest.raises(ValueError):
        store.write_skill("ok", "x" * 300_000)  # 超限拒绝


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
