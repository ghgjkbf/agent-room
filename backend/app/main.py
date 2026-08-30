"""agent-room 主应用：API + WS 路由 + 前端静态资源托管。

第 2 步：双 Agent + 身份卡 + @提及定向投递 + P0 interrupt 抢占。
"""

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from app.agents import routes as agent_routes
from app.agents.responder import GenerationRegistry, plan_replies, respond_agent
from app.core.config import BASE_DIR, settings
from app.core.db import db
from app.core.message import Message, now_cst
from app.files import routes as file_routes
from app.identities import routes as identity_routes
from app.memory import routes as memory_routes
from app.mcp_gateway.server import mount_gateway
from app.orchestrator import routes as task_routes
from app.orchestrator.ceo import OrchestratorRegistry
from app.rooms import routes as room_routes
from app.rooms.bus import BusRegistry
from app.rooms.janitor import janitor_loop
from app.skills import routes as skill_routes

app = FastAPI(title="agent-room", version="0.8.0")


@asynccontextmanager
async def _lifespan(_app):
    """Agent B 群聊管家定时归档循环（互聊不设上限后的存储防膨胀）。"""
    _janitor = asyncio.create_task(janitor_loop("default"))
    yield
    _janitor.cancel()


app.router.lifespan_context = _lifespan
app.include_router(identity_routes.router)
app.include_router(agent_routes.router)
app.include_router(file_routes.router)
app.include_router(task_routes.router)
app.include_router(memory_routes.router)
app.include_router(room_routes.router)
app.include_router(skill_routes.router)
mount_gateway(app, BusRegistry)  # 包装上面的 lifespan，追加 MCP session_manager


@app.middleware("http")
async def no_cache_frontend(request, call_next):
    # 根路径无版本参数 → 302 到 /?v=<版本>：HTML 缓存键随版本变化，
    # 旧缓存（加 no-cache 头之前存的）从此不会再被命中
    if request.url.path == "/" and not request.url.query:
        from starlette.responses import RedirectResponse

        return RedirectResponse(url=f"/?v={app.version}", status_code=302)
    resp = await call_next(request)
    if request.url.path in ("/", "/index.html", "/app.js"):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "agent-room", "version": app.version}


@app.get("/api/room/default")
async def get_default_room():
    """第 1 步固定单房间；不存在则创建并注册演示 Agent A/B。"""
    with db() as conn:
        row = conn.execute("SELECT * FROM rooms WHERE id='default'").fetchone()
        if not row:
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
        # 成员归属关系幂等补齐（第 6 步 room_members）
        conn.execute(
            "INSERT OR IGNORE INTO room_members (room_id, agent_id, joined_at)"
            " SELECT room_id, id, ? FROM agents WHERE room_id='default'", (now_cst(),))
        agents = conn.execute(
            "SELECT a.*, i.label AS identity_label FROM room_members m"
            " JOIN agents a ON a.id = m.agent_id"
            " LEFT JOIN identities i ON i.id=a.identity_id"
            " WHERE m.room_id='default' ORDER BY a.id"
        ).fetchall()
        history = conn.execute(
            "SELECT * FROM messages WHERE room_id='default' AND invalidated=0 ORDER BY id"
        ).fetchall()
    llm_ready = settings.llm_ready()
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


_LLM_KEYS = ("llm_base_url", "llm_api_key", "llm_model", "llm_embedding_model")


def _load_llm_config():
    """LLM 配置持久化：启动时从 kv 表读回（set_llm_config 写入）。

    MVP 决策修订：密钥落本机 agent_room.db（已 gitignore，不出本机），
    换取「重启不丢配置」；V2 再迁加密存储。
    """
    with db() as conn:
        for key in _LLM_KEYS:
            row = conn.execute("SELECT v FROM kv WHERE k=?", ("llm_" + key,)).fetchone()
            if row and row["v"]:
                setattr(settings, key, row["v"])


_load_llm_config()


@app.post("/api/llm-config")
async def set_llm_config(cfg: dict):
    """MVP：LLM 配置写入进程内 settings（V2 迁移到设置页+持久化）。

    模型名/Base URL 做 ASCII 归一化：复制粘贴常混入 U+2011 等非断行连字符
    与全角空格，会让中转站查无此模型（model_not_found）。
    """
    _dash = str.maketrans({
        "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
        "\u2014": "-", "\u2212": "-", "－": "-", "\u00a0": " ", "　": " ",
    })

    def _norm(s: str) -> str:
        return s.strip().translate(_dash)

    if "base_url" in cfg:
        settings.llm_base_url = _norm(cfg["base_url"]).rstrip("/")
    if "api_key" in cfg:
        settings.llm_api_key = cfg["api_key"].strip()
    if "model" in cfg:
        settings.llm_model = _norm(cfg["model"])
    # 持久化到 kv（重启自动读回；单项更新只写传入字段，其余保留）
    with db() as conn:
        for key in ("llm_base_url", "llm_api_key", "llm_model"):
            local = {"llm_base_url": "base_url", "llm_api_key": "api_key",
                     "llm_model": "model"}[key]
            if local in cfg:
                conn.execute(
                    "INSERT INTO kv (k, v) VALUES (?,?)"
                    " ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                    ("llm_" + key, getattr(settings, key)))
    return {"ok": True, "llm_ready": settings.llm_ready(), "model": settings.llm_model}


@app.post("/api/llm-test")
async def test_llm():
    """API 连通性校验：向已配置端点发一条最小对话请求，确认链路可用。"""
    import time

    if not settings.llm_ready():
        return {"ok": False, "error": "LLM 未配置（先填 Base URL / API Key / 模型名）"}
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key,
                             timeout=20, max_retries=0)
        t0 = time.monotonic()
        r = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": "连接测试：请只回复两个字：成功"}],
            max_tokens=16, temperature=0)
        ms = int((time.monotonic() - t0) * 1000)
        reply = (r.choices[0].message.content or "").strip() if r.choices else ""
        return {"ok": True, "latency_ms": ms, "model": settings.llm_model, "reply": reply}
    except Exception as e:
        return {"ok": False, "model": settings.llm_model,
                "error": f"{type(e).__name__}: {str(e)[:300]}"}


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
        # 第 5 步：type=task（人类下达目标）改由 CEO 编排器独占——执行者
        # 等排产单 dispatch 才动工，编排者不执行、执行者不编排
        reply_plan = []
        if mtype == "chat":
            with db() as conn:
                rows = conn.execute(
                    "SELECT a.id, a.name FROM room_members m"
                    " JOIN agents a ON a.id = m.agent_id"
                    " WHERE m.room_id=? ORDER BY a.id",
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
    orch = OrchestratorRegistry.get(room_id)  # CEO 编排器挂为总线监听器
    if orch.on_message not in bus.listeners:
        bus.listeners.append(orch.on_message)
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
