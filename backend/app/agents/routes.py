"""房间成员（agents 表）：注册内置双 Agent、绑定/换绑身份卡。

第 3 步扩展：外部成员（TRAE/ZCode 等经 MCP 网关进群）——前端建员发放
ROOM_TOKEN（仅创建/重发响应可见明文，库内只存 SHA-256），可随时吊销重发。
"""

import hashlib
import secrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.db import db
from app.core.message import now_cst

router = APIRouter(prefix="/api/agents")

# 第 2 步固定的内置双 Agent
INTERNAL_AGENTS = [
    {"id": "agent_a", "name": "Agent A"},
    {"id": "agent_b", "name": "Agent B"},
]


class BindIn(BaseModel):
    identity_id: str | None = None


class ExternalAgentIn(BaseModel):
    name: str
    identity_id: str | None = None
    room_id: str = "default"


# 内置 Agent 的出厂身份卡（无卡 = 无工具；用户可在成员面板换绑）
BUILTIN_BINDINGS = {"agent_a": "idf_assistant", "agent_b": "idf_steward"}


def _ensure_internal(conn):
    for a in INTERNAL_AGENTS:
        row = conn.execute("SELECT id FROM agents WHERE id=?", (a["id"],)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO agents (id, room_id, name, kind) VALUES (?, 'default', ?, 'internal')",
                (a["id"], a["name"]),
            )
        conn.execute(
            "INSERT OR IGNORE INTO room_members (room_id, agent_id, joined_at)"
            " VALUES ('default', ?, ?)", (a["id"], now_cst()))
        # 出厂绑定：仅在完全未绑定时生效（换绑/解绑过的尊重现状）
        card = BUILTIN_BINDINGS.get(a["id"])
        if card:
            bound = conn.execute(
                "SELECT identity_id FROM agents WHERE id=?", (a["id"],)).fetchone()
            if bound and not bound["identity_id"]:
                if conn.execute("SELECT id FROM identities WHERE id=?", (card,)).fetchone():
                    conn.execute("UPDATE agents SET identity_id=? WHERE id=?", (card, a["id"]))


@router.get("")
async def list_agents(room_id: str = "default", all: int = 0):
    with db() as conn:
        _ensure_internal(conn)
        # 兜底：身份卡被直接删库等历史操作造成的悬空引用 → 视为未绑定并清理
        conn.execute(
            "UPDATE agents SET identity_id=NULL WHERE identity_id IS NOT NULL AND"
            " identity_id NOT IN (SELECT id FROM identities)")
        if all:
            # 注册表全量（新建群聊选成员用）
            rows = conn.execute(
                "SELECT a.*, i.label AS identity_label FROM agents a"
                " LEFT JOIN identities i ON i.id = a.identity_id ORDER BY a.id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT a.*, i.label AS identity_label FROM room_members m"
                " JOIN agents a ON a.id = m.agent_id"
                " LEFT JOIN identities i ON i.id = a.identity_id"
                " WHERE m.room_id=? ORDER BY a.id",
                (room_id,),
            ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "identity_id": r["identity_id"],
            "identity_label": r["identity_label"],
            "chat_turns": r["chat_turns"] or 0,
            "status": r["status"],
            "kind": r["kind"] or "internal",
        }
        for r in rows
    ]


@router.post("/{aid}/bind")
async def bind_identity(aid: str, body: BindIn):
    with db() as conn:
        agent = conn.execute("SELECT * FROM agents WHERE id=?", (aid,)).fetchone()
        if not agent:
            raise HTTPException(404, "agent not found")
        if body.identity_id is not None and body.identity_id != "":
            card = conn.execute(
                "SELECT id FROM identities WHERE id=?", (body.identity_id,)
            ).fetchone()
            if not card:
                raise HTTPException(404, "identity not found")
        conn.execute(
            "UPDATE agents SET identity_id=?, chat_turns=0 WHERE id=?",
            (body.identity_id or None, aid),
        )
    return {"ok": True}


# ---------- 外部成员（MCP 网关进群，第 3 步） ----------

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return "aroom_" + secrets.token_hex(20)


def _issue_token(conn, aid: str) -> str:
    """生成并落哈希，明文仅本次返回。"""
    token = _new_token()
    conn.execute(
        "UPDATE agents SET api_token_hash=?, status='offline' WHERE id=?",
        (_hash_token(token), aid),
    )
    return token


@router.post("/external")
async def create_external_agent(body: ExternalAgentIn):
    """前端建外部成员：生成 agent id 并发放 ROOM_TOKEN（明文只出现这一次）。"""
    if not body.name.strip():
        raise HTTPException(400, "成员名称不能为空")
    aid = "agent_" + secrets.token_hex(4)
    with db() as conn:
        if body.identity_id:
            card = conn.execute(
                "SELECT id FROM identities WHERE id=?", (body.identity_id,)
            ).fetchone()
            if not card:
                raise HTTPException(404, "identity not found")
        room = conn.execute("SELECT id FROM rooms WHERE id=?", (body.room_id,)).fetchone()
        if not room:
            raise HTTPException(404, "房间不存在")
        conn.execute(
            "INSERT INTO agents (id, room_id, name, identity_id, kind, status)"
            " VALUES (?, ?, ?, ?, 'external', 'offline')",
            (aid, body.room_id, body.name.strip(), body.identity_id or None),
        )
        conn.execute(
            "INSERT OR IGNORE INTO room_members (room_id, agent_id, joined_at)"
            " VALUES (?,?,?)", (body.room_id, aid, now_cst()))
        token = _issue_token(conn, aid)
    return {"ok": True, "id": aid, "name": body.name.strip(), "token": token,
            "room_id": body.room_id}


@router.post("/{aid}/rotate-token")
async def rotate_external_token(aid: str):
    """重发令牌：旧 token 即刻失效。仅外部成员可重发。"""
    with db() as conn:
        agent = conn.execute(
            "SELECT id, kind FROM agents WHERE id=?", (aid,)
        ).fetchone()
        if not agent:
            raise HTTPException(404, "agent not found")
        if (agent["kind"] or "internal") != "external":
            raise HTTPException(400, "内置 Agent 无需令牌")
        token = _issue_token(conn, aid)
    return {"ok": True, "id": aid, "token": token}


@router.delete("/{aid}")
async def delete_agent(aid: str):
    """删除成员（第 5.5 步）：仅外部成员可删；内置 A/B 是房间固定角色。"""
    with db() as conn:
        agent = conn.execute(
            "SELECT id, kind, name FROM agents WHERE id=?", (aid,)
        ).fetchone()
        if not agent:
            raise HTTPException(404, "agent not found")
        if (agent["kind"] or "internal") != "external":
            raise HTTPException(400, "内置 Agent 不可删除")
        conn.execute("DELETE FROM agents WHERE id=?", (aid,))
        conn.execute("DELETE FROM room_members WHERE agent_id=?", (aid,))
    return {"ok": True, "id": aid, "name": agent["name"]}
