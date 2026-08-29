"""第 5.5 步：Agent B 定时归档清理 + 删除成员 API。

janitor：低于阈值不动；达到阈值 → 摘要写公共记忆 → 旧 chat 物理删除 →
游标推进 → 群里发归档回执（sender=agent_b）；再次运行不重复归档。
delete API：内置拒绝 / 外部可删。
"""

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.core.config import settings
from app.core.db import db
from app.core.message import now_cst
from app.memory.hub import MemoryHub
from app.rooms.janitor import cursor_key, run_janitor_once


class FakeBus:
    def __init__(self, room_id):
        self.room_id = room_id
        self.published = []

        class _R:
            @staticmethod
            def get(rid):
                return self

        self.registry_ref = _R

    async def publish(self, msg):
        self.published.append(msg)


def _insert_chat(room_id, n, base_id=0):
    with db() as conn:
        for i in range(n):
            conn.execute(
                "INSERT INTO messages (msg_id, room_id, type, priority, sender_kind,"
                " sender_id, payload_text, mentions, parent_task_id, created_at,"
                " stream_seq, is_final, full_text)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"jan_{uuid.uuid4().hex[:8]}_{base_id}_{i}", room_id, "chat", 3, "agent",
                 "agent_a" if i % 2 else "user_001", f"聊天内容 {base_id}-{i}", "[]",
                 None, now_cst(), 0, 1, f"聊天内容 {base_id}-{i}"))


def _get_kv(conn, k):
    row = conn.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return int(row["v"]) if row else 0


def _cleanup_room(room):
    """测试残留清理（kv 是全局表，按房间键删除）。"""
    with db() as conn:
        conn.execute("DELETE FROM kv WHERE k=?", (cursor_key(room),))
        conn.execute("DELETE FROM messages WHERE room_id=?", (room,))


def test_janitor_threshold_and_archive(tmp_path, monkeypatch):
    room = f"jan_{uuid.uuid4().hex[:6]}"
    hub = MemoryHub(str(tmp_path))
    monkeypatch.setattr("app.memory.hub.hub", hub)
    monkeypatch.setattr(settings, "janitor_min_msgs", 5)
    monkeypatch.setattr(settings, "llm_base_url", "")
    bus = FakeBus(room)

    async def _run():
        _insert_chat(room, 4)  # 低于阈值
        assert (await run_janitor_once(room, bus.registry_ref))["archived"] == 0
        _insert_chat(room, 3, base_id=1)  # 共 7 条 → 触发
        r = await run_janitor_once(room, bus.registry_ref)
        assert r["archived"] == 7
        # 公共记忆沉淀 + 归档回执
        stats = hub.stats(room)
        assert stats["public"] == 1
        assert any("归档" in m.payload_text and m.sender_id == "agent_b"
                   for m in bus.published)
        # 旧 chat 物理删除 + 游标推进
        with db() as conn:
            left = conn.execute(
                "SELECT COUNT(*) c FROM messages WHERE room_id=? AND type='chat'",
                (room,)).fetchone()["c"]
            cursor = _get_kv(conn, cursor_key(room))
        assert left == 0 and cursor > 0
        # 再次运行：游标之后无新消息，不重复归档
        assert (await run_janitor_once(room, bus.registry_ref))["archived"] == 0

    try:
        asyncio.run(_run())
    finally:
        _cleanup_room(room)


def test_janitor_keeps_non_chat_messages(monkeypatch, tmp_path):
    """system/dispatch 等关键消息不被清理。"""
    room = f"jan_{uuid.uuid4().hex[:6]}"
    monkeypatch.setattr("app.memory.hub.hub", MemoryHub(str(tmp_path)))
    monkeypatch.setattr(settings, "janitor_min_msgs", 2)
    with db() as conn:
        conn.execute(
            "INSERT INTO messages (msg_id, room_id, type, priority, sender_kind,"
            " sender_id, payload_text, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (f"sys_{uuid.uuid4().hex[:8]}", room, "system", 3, "system", "bus",
             "关键系统消息", now_cst()))
    _insert_chat(room, 2)
    bus = FakeBus(room)

    async def _run():
        assert (await run_janitor_once(room, bus.registry_ref))["archived"] == 2
        with db() as conn:
            left = conn.execute(
                "SELECT type FROM messages WHERE room_id=?", (room,)).fetchall()
        assert [r["type"] for r in left] == ["system"]

    try:
        asyncio.run(_run())
    finally:
        _cleanup_room(room)


def test_delete_member_api():
    """内置拒绝删除；外部成员可删（令牌随之失效）。"""
    from app.agents.routes import create_external_agent, delete_agent

    async def _run():
        # 内置 Agent 拒绝
        with pytest.raises(Exception) as ei:
            await delete_agent("agent_a")
        assert "内置" in str(ei.value)
        # 建外部成员 → 删除 → 再删 404
        class _Body:
            name = "待删除·测试"
            identity_id = None
            room_id = "default"
        created = await create_external_agent(_Body())
        aid = created["id"]
        r = await delete_agent(aid)
        assert r["ok"] and r["id"] == aid
        with pytest.raises(Exception):
            await delete_agent(aid)

    asyncio.run(_run())
