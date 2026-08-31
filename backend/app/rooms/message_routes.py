"""消息 UI API（v0.9 小更新）：单条软删 + 星标。

- 软删复用 invalidated=1（P0 中断同款机制）：Agent 网关读历史自动过滤，
  事件流保留审计痕迹；
- 星标落 messages.starred 列，惰性同步（拉历史时携带，无 WS 广播）。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.db import db

router = APIRouter(prefix="/api/messages", tags=["messages"])


def _load(conn, msg_id: str):
    row = conn.execute(
        "SELECT id, room_id, type, sender_kind, invalidated FROM messages WHERE msg_id=?",
        (msg_id,)).fetchone()
    if not row:
        raise HTTPException(404, "消息不存在")
    return row


@router.delete("/{msg_id}")
async def delete_message(msg_id: str):
    """软删：置 invalidated=1，历史/网关即不可见，库内留痕。"""
    with db() as conn:
        row = _load(conn, msg_id)
        if row["invalidated"]:
            return {"ok": True, "msg_id": msg_id}  # 幂等
        conn.execute("UPDATE messages SET invalidated=1 WHERE msg_id=?", (msg_id,))
    return {"ok": True, "msg_id": msg_id}


class StarIn(BaseModel):
    starred: int = 0  # 0/1


@router.post("/{msg_id}/star")
async def star_message(msg_id: str, body: StarIn):
    with db() as conn:
        _load(conn, msg_id)
        conn.execute("UPDATE messages SET starred=? WHERE msg_id=?",
                     (1 if body.starred else 0, msg_id))
    return {"ok": True, "msg_id": msg_id, "starred": 1 if body.starred else 0}
