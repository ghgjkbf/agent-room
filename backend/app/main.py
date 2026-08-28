"""agent-room 主应用：API + WS 路由 + 前端静态资源托管。

第 2 步：双 Agent + 身份卡 + @提及定向投递 + P0 interrupt 抢占。
"""

import asyncio
import json
import os
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from app.agents import routes as agent_routes
from app.agents.responder import GenerationRegistry, plan_replies, respond_agent
from app.core.config import BASE_DIR, settings
from app.core.db import db
from app.core.message import Message
from app.files import routes as file_routes
from app.identities import routes as identity_routes
from app.mcp_gateway.server import mount_gateway
from app.rooms.bus import BusRegistry

app = FastAPI(title="agent-room", version="0.4.0")
app.include_router(identity_routes.router)
app.include_router(agent_routes.router)
app.include_router(file_routes.router)
mount_gateway(app, BusRegistry)


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "agent-room"}


@app.get("/api/room/default")
async def get_default_room():
    """第 1 步固定单房间；不存在则创建并注册演示 Agent A/B。"""
    with db() as conn:
        row = conn.execute("SELECT * FROM rooms WHERE id='default'").fetchone()
        if not row:
            from app.core.message import now_cst

            conn.execute(
                "INSERT INTO rooms (id, name, created_at) VALUES ('default', '主房间', ?)",
                (now_cst(),),
            )
        for aid, name in (("agent_a", "Agent A"), ("agent_b", "Agent B")):
            agent = conn.execute("SELECT id FROM agents WHERE id=?", (aid,)).fetchone()
            if not agent:
                conn.execute(
                    "INSERT INTO agents (id, room_id, name, kind) VALUES (?, 'default', ?, 'internal')",
                    (aid, name),
                )
        agents = conn.execute(
            "SELECT a.*, i.label AS identity_label FROM agents a"
            " LEFT JOIN identities i ON i.id=a.identity_id"
            " WHERE a.room_id='default' ORDER BY a.id"
        ).fetchall()
        history = conn.execute(
            "SELECT * FROM messages WHERE room_id='default' AND invalidated=0 ORDER BY id"
        ).fetchall()
    llm_ready = bool(settings.llm_base_url and settings.llm_api_key and settings.llm_model)
    return {
        "room": {"id": "default", "name": "主房间"},
        "agents": [
            {
                "id": r["id"],
                "name": r["name"],
                "identity_id": r["identity_id"],
                "identity_label": r["identity_label"],
                "chat_turns": r["chat_turns"] or 0,
            }
            for r in agents
        ],
        "history": [Message.from_row(r).to_dict() for r in history],
        "llm_ready": llm_ready,
    }


@app.post("/api/llm-config")
async def set_llm_config(cfg: dict):
    """MVP：LLM 配置写入进程内 settings（V2 迁移到设置页+持久化）。"""
    if "base_url" in cfg:
        settings.llm_base_url = cfg["base_url"].strip().rstrip("/")
    if "api_key" in cfg:
        settings.llm_api_key = cfg["api_key"].strip()
    if "model" in cfg:
        settings.llm_model = cfg["model"].strip()
    ready = bool(settings.llm_base_url and settings.llm_api_key and settings.llm_model)
    return {"ok": True, "llm_ready": ready}


async def _ws_loop(ws: WebSocket, bus, client_id: str):
    """单连接消息循环（拆出便于阅读）。"""
    while True:
        raw = await ws.receive_text()
        data = json.loads(raw)
        mtype = data.get("type", "chat")

        # ---- P0 interrupt 抢占一切（s7）----
        if mtype == "interrupt":
            await bus.handle_interrupt(str(data.get("text", "")))
            continue

        mentions = data.get("mentions") or []
        msg = Message(
            room_id=bus.room_id,
            type=mtype,
            priority=1 if mtype == "task" else 3,
            sender_kind="human",
            sender_id="user_001",
            payload_text=str(data.get("text", "")),
            mentions=mentions,
        )
        # 先登记生成句柄再落库广播：保证 publish 期间到达的 P0 也能 cancel
        reply_plan = []
        if mtype in ("chat", "task"):
            with db() as conn:
                rows = conn.execute(
                    "SELECT id, name FROM agents WHERE room_id=? ORDER BY id",
                    (bus.room_id,),
                ).fetchall()
            online = [{"id": r["id"], "name": r["name"]} for r in rows]
            reply_plan = plan_replies(msg, online)

        tasks = []
        for agent in reply_plan:
            t = asyncio.create_task(respond_agent(bus, msg, agent))
            GenerationRegistry.register(agent["id"], t)
            tasks.append(t)

        # 等第一个 await 让事件循环轮转，使 cancel 能追上刚创建的任务
        if tasks:
            try:
                await asyncio.wait(tasks, timeout=0.05)
            except asyncio.CancelledError:
                pass

        await bus.publish(msg)


@app.websocket("/ws/{room_id}")
async def room_ws(ws: WebSocket, room_id: str):
    bus = BusRegistry.get(room_id)
    client_id = str(uuid.uuid4())
    await bus.join(client_id, ws)
    try:
        await _ws_loop(ws, bus, client_id)
    except WebSocketDisconnect:
        bus.leave(client_id)


# 前端静态资源同端口托管（设计文档 s13 决策）
_static_dir = os.path.join(os.path.dirname(BASE_DIR), "frontend")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="frontend")
