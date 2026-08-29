"""任务编排 HTTP 路由（任务面板用）：列表 / 确认 / 恢复 / 作废。"""

import json

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.db import db
from app.orchestrator.ceo import OrchestratorRegistry, _SUB_ST, _TASK_ST
from app.rooms.bus import BusRegistry

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskAction(BaseModel):
    action: str = "confirm"


def _task_dict(row, with_subtasks: bool = True) -> dict:
    d = dict(row)
    d["status_label"] = _TASK_ST.get(d["status"], d["status"])
    if with_subtasks:
        with db() as conn:
            subs = conn.execute(
                "SELECT * FROM subtasks WHERE task_id=? ORDER BY seq",
                (d["id"],)).fetchall()
        d["subtasks"] = []
        for s in subs:
            sd = dict(s)
            sd["status_label"] = _SUB_ST.get(sd["status"], sd["status"])
            sd["depends_on"] = json.loads(sd["depends_on"] or "[]")
            d["subtasks"].append(sd)
    return d


@router.get("")
async def list_tasks(room_id: str = "default"):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE room_id=? ORDER BY created_at DESC LIMIT 5",
            (room_id,)).fetchall()
    return {"ok": True, "tasks": [_task_dict(r) for r in rows]}


@router.post("/{task_id}/confirm")
async def confirm_task(task_id: str, body: TaskAction):
    room_id = "default"
    with db() as conn:
        row = conn.execute("SELECT room_id FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row:
            room_id = row["room_id"]
    orch = OrchestratorRegistry.get(room_id)
    r = await orch.confirm(task_id, body.action)
    if not r.get("ok"):
        return r
    await orch.dispatch_ready(BusRegistry.get(room_id), task_id)
    return r


@router.post("/{task_id}/abort")
async def abort_task(task_id: str):
    with db() as conn:
        row = conn.execute("SELECT room_id FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return {"ok": False, "detail": "任务不存在"}
    return await OrchestratorRegistry.get(row["room_id"]).abort(task_id)
