"""向量记忆路由（记忆面板用）：统计 + 最近记忆 + 人类管理式删除。

只读检索不含私有内容（私有记忆仅经检索注入进对应 Agent 的上下文）；
删除/清空是人类的管理操作，允许覆盖公私两种记忆。
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.memory.hub import hub

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryClearIn(BaseModel):
    room_id: str = "default"
    scope: str = "public"          # public | private
    agent_id: str | None = None


@router.get("")
async def memory_overview(room_id: str = "default"):
    return {
        "ok": True,
        "room_id": room_id,
        "stats": hub.stats(room_id),
        "recent": [
            {"scope": r["scope"], "id": r.get("id", ""), "text": r["text"],
             "created_at": r["created_at"]}
            for r in hub.recent(room_id, 12)
        ],
    }


@router.delete("/item")
async def delete_memory_item(room_id: str, id: str, scope: str = "public",
                             agent_id: str | None = None):
    """删除单条记忆。scope=public | private（private 需带 agent_id）。"""
    if not id:
        return {"ok": False, "detail": "缺少记忆 id"}
    removed = hub.delete_record(room_id, agent_id, id, private=(scope == "private"))
    return {"ok": removed, "detail": None if removed else "未找到该条记忆"}


@router.post("/clear")
async def clear_memory(body: MemoryClearIn):
    """清空指定范围记忆（公共；或某成员的私有）。"""
    n = hub.clear(body.room_id, body.agent_id, private=(body.scope == "private"))
    return {"ok": True, "cleared": n}
