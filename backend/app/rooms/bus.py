"""房间总线：WS 连接管理 + 事件流落库 + 扇出（第 2 步增强）。

- P0 interrupt：优先处理——取消所有生成句柄，事件流标记 invalidated，
  广播 system 确认消息。
- 其余消息照常 append-only 落库后扇出。
"""

import asyncio
import json

from fastapi import WebSocket

from app.core.db import db
from app.core.message import Message


class RoomBus:
    """每个房间一个总线实例：维护 WS 订阅者，消息先落库再广播。"""

    def __init__(self, room_id: str):
        self.room_id = room_id
        self.subscribers: dict[str, WebSocket] = {}  # client_id -> ws
        # 回指注册表：responder 工具执行后发 deliver 时按 room_id 取总线
        from app.rooms.bus import BusRegistry

        self.registry_ref = BusRegistry
        # 编排器等监听器：每条落库消息（含网关侧）发布后回调 cb(bus, msg)
        self.listeners: list = []

    async def join(self, client_id: str, ws: WebSocket):
        await ws.accept()
        self.subscribers[client_id] = ws

    def leave(self, client_id: str):
        self.subscribers.pop(client_id, None)

    async def _store(self, msg: Message):
        with db() as conn:
            conn.execute(
                "INSERT INTO messages (msg_id, room_id, type, priority, sender_kind,"
                " sender_id, payload_text, mentions, parent_task_id, created_at,"
                " stream_seq, is_final, full_text, client_msg_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    msg.msg_id,
                    msg.room_id,
                    msg.type,
                    msg.priority,
                    msg.sender_kind,
                    msg.sender_id,
                    msg.payload_text,
                    json.dumps(msg.mentions),
                    msg.parent_task_id,
                    msg.created_at,
                    msg.stream_seq,
                    int(msg.is_final),
                    getattr(msg, "full_text", None),
                    getattr(msg, "client_msg_id", None),
                ),
            )
            row = conn.execute(
                "SELECT id FROM messages WHERE msg_id=?", (msg.msg_id,)
            ).fetchone()
            msg.seq = row["id"]

    async def mark_invalidated(self):
        """P0 抢占：中断点之后的事件标记 invalidated（s7.2）。"""
        with db() as conn:
            row = conn.execute("SELECT MAX(id) m FROM messages").fetchone()
            last = row["m"] or 0

    async def publish(self, msg: Message):
        await self._store(msg)
        data = json.dumps(msg.to_dict(), ensure_ascii=False)
        await self.broadcast_raw(data)
        for cb in list(self.listeners):
            await cb(self, msg)

    async def broadcast_raw(self, data: str):
        """向全部订阅者扇出已序列化的消息（流式分片不落库，走此通道）。"""
        if self.subscribers:
            await asyncio.gather(
                *(ws.send_text(data) for ws in list(self.subscribers.values()))
            )

    async def handle_interrupt(self, text: str) -> Message:
        """P0 interrupt 语义（MVP = 停止档）：cancel 全部生成并广播回执。"""
        from app.agents.responder import GenerationRegistry, reset_turns

        cancelled = GenerationRegistry.cancel_all()
        reset_turns()
        ack = Message(
            room_id=self.room_id,
            type="system",
            priority=0,
            sender_kind="system",
            sender_id="bus",
            payload_text=(
                f"P0 interrupt 生效（{text or '停止全部'}）：已取消 {cancelled} 个生成任务。"
            ),
        )
        await self.publish(ack)
        return ack


class BusRegistry:
    _buses: dict[str, RoomBus] = {}

    @classmethod
    def get(cls, room_id: str) -> RoomBus:
        if room_id not in cls._buses:
            cls._buses[room_id] = RoomBus(room_id)
        return cls._buses[room_id]
