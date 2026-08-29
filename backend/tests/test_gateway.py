"""第 3 步网关协议单测：令牌校验、冒名拒绝、幂等去重、防死循环、增量游标。"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.agents.responder import plan_replies
from app.core.db import db, init_db
from app.core.message import Message
from app.mcp_gateway.server import authenticate, build_mcp_server

init_db()


def _make_external(name: str = "TRAE·测试"):
    import asyncio

    from app.agents.routes import create_external_agent

    r = asyncio.run(create_external_agent(type("B", (), {"name": name, "identity_id": None})()))
    return r["id"], r["token"]


def _cleanup(aid: str):
    with db() as conn:
        conn.execute("DELETE FROM messages WHERE sender_id=?", (aid,))
        conn.execute("DELETE FROM agents WHERE id=?", (aid,))


def test_authenticate_ok_and_wrong_token():
    aid, token = _make_external()
    try:
        row = authenticate(aid, token)
        assert row["kind"] == "external"
        with pytest.raises(PermissionError):
            authenticate(aid, "wrong-token")
        with pytest.raises(PermissionError):
            authenticate("agent_a", token)  # 冒名：内置成员拿外部 token 也拒
    finally:
        _cleanup(aid)


def test_plan_replies_anti_loop():
    agents = [{"id": "agent_a"}, {"id": "agent_b"}]
    # 人类广播 → 全员
    m = Message(room_id="default", type="chat", sender_kind="human", sender_id="u", payload_text="hi")
    assert [a["id"] for a in plan_replies(m, agents)] == ["agent_a", "agent_b"]
    # 外部广播 → 无人自动接话
    m = Message(room_id="default", type="chat", sender_kind="agent", sender_id="agent_trae", payload_text="hi")
    assert plan_replies(m, agents) == []
    # 外部 @A → 仅 A
    m = Message(room_id="default", type="chat", sender_kind="agent", sender_id="agent_trae", payload_text="hi", mentions=["agent_a"])
    assert [a["id"] for a in plan_replies(m, agents)] == ["agent_a"]


def test_internal_default_roles():
    """第 5.5 步：A/B 不绑身份卡时使用内置默认职责（A 服务用户 / B 服务群聊）。"""
    from app.agents.responder import DEFAULT_ROLES, build_system_prompt, placeholder_text

    assert "用户服务助手" in build_system_prompt("agent_a", None)
    assert "群聊管家" in build_system_prompt("agent_b", None)
    assert "未绑定身份卡" in build_system_prompt("agent_x", None)  # 其他内置无默认职责
    assert "用户服务助手" in placeholder_text("agent_a", None, "你好")
    assert "群聊管家" in placeholder_text("agent_b", None, "你好")
    assert set(DEFAULT_ROLES) == {"agent_a", "agent_b"}


def test_deduplicate_client_msg_id():
    """send_message 幂等：同 (sender_id, client_msg_id) 只落一条。

    用真实 DB：第一次调用经 FakeBus 计数（不落库），手动把首条按真实存储
    语义插入 messages 带 client_msg_id，再调第二次应命中去重分支。
    """
    import asyncio

    from app.mcp_gateway.server import _publish_external

    aid, token = _make_external()
    bus_calls = []

    class FakeBus:
        async def publish(self, msg):
            bus_calls.append(msg)

    class FakeRegistry:
        @staticmethod
        def get(room_id):
            return FakeBus()

    srv = build_mcp_server(FakeRegistry)
    tool = next(
        t for t in srv._tool_manager._tools.values() if t.name == "send_message"
    )
    fn = tool.fn

    async def _run():
        r1 = json.loads(await fn(agent_id=aid, token=token, text="第一条", client_msg_id="k1"))
        # 模拟 bus.publish 已落库：插入首条消息（与 _store 相同的关键列）
        with db() as conn:
            conn.execute(
                "INSERT INTO messages (msg_id, room_id, type, priority, sender_kind,"
                " sender_id, payload_text, mentions, created_at, stream_seq, is_final,"
                " full_text, client_msg_id) VALUES (?,'default','chat',3,'agent',?,?,'[]',"
                " datetime('now'),0,1,?,?)",
                (r1["msg_id"], aid, "第一条", "第一条", "k1"),
            )
        r2 = json.loads(await fn(agent_id=aid, token=token, text="第一条(重试)", client_msg_id="k1"))
        return r1, r2

    r1, r2 = asyncio.run(_run())
    assert r1["ok"] and r2["deduplicated"] is True
    assert r2["msg_id"] == r1["msg_id"]
    assert len(bus_calls) == 1  # 重试没有再次扇出
    _cleanup(aid)
