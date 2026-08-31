"""成员互聊回复调度（v0.9 成员平权）。

挂为 RoomBus 总线监听器：任何成员（人类 WS / 外部网关 / 内置）发布的
agent chat 广播，按 plan_replies 平权唤起在线成员接话。
- 防死循环护栏：连锁回复（is_reply=True）不再自动唤起他人，只有
  显式 @（mentions 非空，经 WS/网关发出）或排产单 dispatch 定向唤起。
- 人类消息（sender_kind=human）照旧在 _ws_loop 内联调度，本监听器跳过。
"""

import asyncio
import json

from app.agents.responder import GenerationRegistry, plan_replies, respond_agent
from app.core.db import db


async def dispatch_replies(bus, msg):
    """总线监听器：agent chat 广播 → 平权唤起在线成员（含 is_reply 护栏）。"""
    if msg.type != "chat" or msg.sender_kind != "agent":
        return
    # 流式中间片 / 终止信号不触发回复（真实正文落库后带 is_reply 的是首条）
    if not msg.is_final or msg.stream_seq > 0:
        return
    if getattr(msg, "is_reply", False):
        return  # 连锁回复不再唤起，防 A↔B 死循环
    with db() as conn:
        rows = conn.execute(
            "SELECT a.id, a.name FROM room_members m"
            " JOIN agents a ON a.id = m.agent_id"
            " WHERE m.room_id=? ORDER BY a.id",
            (bus.room_id,),
        ).fetchall()
    online = [{"id": r["id"], "name": r["name"]} for r in rows]
    for agent in plan_replies(msg, online):
        reply_msg = json.loads(json.dumps(msg.to_dict(), ensure_ascii=False))
        t = asyncio.create_task(respond_agent(bus, msg, agent))
        GenerationRegistry.register(agent["id"], t)
