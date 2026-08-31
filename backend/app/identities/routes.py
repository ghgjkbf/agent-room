"""身份卡（设计文档 s5）：YAML/JSON 存库，MVP 提供字段化读写。"""

import json
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.db import db
from app.core.message import now_cst

router = APIRouter(prefix="/api/identities")

# MVP 工具白名单候选（第 3 步起与 MCP 工具层对接）
AVAILABLE_TOOLS = ["fs.read", "fs.write", "fs.list", "shell.run", "git.status", "memory.query"]


class IdentityIn(BaseModel):
    label: str
    persona: str = ""
    responsibilities: list[str] = []
    tools_allow: list[str] = []
    focus: list[str] = []   # 发言领域关键词：广播唤起按此匹配，空 = 只响应 @/排产单
    budget_turns: int = 6


def row_to_card(row) -> dict:
    return {
        "id": row["id"],
        "label": row["label"],
        "persona": row["persona"] or "",
        "responsibilities": json.loads(row["responsibilities"] or "[]"),
        "tools_allow": json.loads(row["tools_allow"] or "[]"),
        "focus": json.loads(row["focus"] or "[]") if "focus" in row.keys() else [],
        "budget_turns": row["budget_turns"] if "budget_turns" in row.keys() else 6,
        "version": row["version"],
    }


@router.get("")
async def list_identities():
    with db() as conn:
        rows = conn.execute("SELECT * FROM identities ORDER BY created_at").fetchall()
    return [row_to_card(r) for r in rows]


@router.post("")
async def create_identity(card: IdentityIn):
    iid = f"identity_{uuid.uuid4().hex[:8]}"
    with db() as conn:
        conn.execute(
            "INSERT INTO identities (id, label, persona, responsibilities, tools_allow,"
            " focus, budget_turns, version, created_at) VALUES (?,?,?,?,?,?,?,1,?)",
            (
                iid,
                card.label,
                card.persona,
                json.dumps(card.responsibilities, ensure_ascii=False),
                json.dumps(card.tools_allow),
                json.dumps(card.focus, ensure_ascii=False),
                card.budget_turns,
                now_cst(),
            ),
        )
    return {"ok": True, "id": iid}


@router.put("/{iid}")
async def update_identity(iid: str, card: IdentityIn):
    with db() as conn:
        row = conn.execute("SELECT id FROM identities WHERE id=?", (iid,)).fetchone()
        if not row:
            raise HTTPException(404, "identity not found")
        conn.execute(
            "UPDATE identities SET label=?, persona=?, responsibilities=?,"
            " tools_allow=?, focus=?, budget_turns=?, version=version+1 WHERE id=?",
            (
                card.label,
                card.persona,
                json.dumps(card.responsibilities, ensure_ascii=False),
                json.dumps(card.tools_allow),
                json.dumps(card.focus, ensure_ascii=False),
                card.budget_turns,
                iid,
            ),
        )
    return {"ok": True}


@router.delete("/{iid}")
async def delete_identity(iid: str):
    with db() as conn:
        used = conn.execute(
            "SELECT COUNT(*) c FROM agents WHERE identity_id=?", (iid,)
        ).fetchone()["c"]
        if used:
            raise HTTPException(400, "身份卡已被 Agent 绑定，请先解绑")
        conn.execute("DELETE FROM identities WHERE id=?", (iid,))
    return {"ok": True}
