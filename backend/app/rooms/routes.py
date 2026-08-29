"""群聊房间 API（第 6 步增强）：新建群聊并选择成员加入。

- agents 表保留为成员「全局注册表」（名字/令牌/身份卡绑定）；
  房间归属走 room_members 关系表 (room_id, agent_id)。
- default 房间固定存在；新群可勾选任意已注册成员（内置 A/B、外部成员）。
- 文件工作区 / 任务编排 / 向量记忆 / 消息流均按 room_id 天然隔离。
"""

import secrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.db import db
from app.core.message import now_cst

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


class RoomIn(BaseModel):
    name: str
    agent_ids: list[str] = []


@router.get("")
async def list_rooms():
    with db() as conn:
        rows = conn.execute(
            "SELECT r.id, r.name, r.created_at,"
            " (SELECT COUNT(*) FROM room_members m WHERE m.room_id=r.id) AS member_count"
            " FROM rooms r ORDER BY r.created_at"
        ).fetchall()
    return [
        {"id": r["id"], "name": r["name"], "member_count": r["member_count"],
         "created_at": r["created_at"]}
        for r in rows
    ]


@router.post("")
async def create_room(body: RoomIn):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "群聊名称不能为空")
    rid = "room_" + secrets.token_hex(4)
    ts = now_cst()
    with db() as conn:
        conn.execute(
            "INSERT INTO rooms (id, name, created_at) VALUES (?,?,?)", (rid, name, ts))
        for aid in dict.fromkeys(body.agent_ids):  # 去重保序
            agent = conn.execute("SELECT id, name FROM agents WHERE id=?", (aid,)).fetchone()
            if not agent:
                raise HTTPException(404, f"成员不存在：{aid}")
            conn.execute(
                "INSERT OR IGNORE INTO room_members (room_id, agent_id, joined_at)"
                " VALUES (?,?,?)", (rid, aid, ts))
        members = conn.execute(
            "SELECT agent_id FROM room_members WHERE room_id=?", (rid,)).fetchall()
    return {"ok": True, "id": rid, "name": name,
            "members": [m["agent_id"] for m in members]}


@router.delete("/{rid}")
async def delete_room(rid: str):
    if rid == "default":
        raise HTTPException(400, "默认房间不可删除")
    with db() as conn:
        row = conn.execute("SELECT id FROM rooms WHERE id=?", (rid,)).fetchone()
        if not row:
            raise HTTPException(404, "房间不存在")
        conn.execute("DELETE FROM room_members WHERE room_id=?", (rid,))
        conn.execute("DELETE FROM rooms WHERE id=?", (rid,))
    return {"ok": True, "id": rid}
