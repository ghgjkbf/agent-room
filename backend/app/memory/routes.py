"""向量记忆查询路由（记忆面板用）：统计 + 最近记忆。只读，不含私有检索接口
（私有记忆仅经检索注入进对应 Agent 的上下文，不对外暴露）。"""

from fastapi import APIRouter

from app.memory.hub import hub

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("")
async def memory_overview(room_id: str = "default"):
    return {
        "ok": True,
        "room_id": room_id,
        "stats": hub.stats(room_id),
        "recent": [
            {"scope": r["scope"], "text": r["text"], "created_at": r["created_at"]}
            for r in hub.recent(room_id, 12)
        ],
    }
