"""MCP 接入网关（第 3 步）：外部 Agent（TRAE / ZCode）进群的一等公民通道。

- MCPServer 以 streamable-http 挂载到现有 FastAPI 的 /mcp（同端口 8899，无独立进程）。
- 四件套工具：join_room / poll_messages / send_message / declare_status。
- 每次调用携带 (agent_id, token) 双因子校验，无会话状态，吊销即时生效。
- 失败一律结构化错误文本返回（MCP isError 约定），不抛栈泄漏。
"""

import contextlib
import hashlib
import json

from mcp.server.mcpserver import MCPServer

from app.core.db import db
from app.core.message import Message
from app.files.tools import exec_fs_tool

# 群规（join_room 返回值内嵌，Agent 进群即读到使用约定；ClawSwarm cs-chat 技能同思路）
HOUSE_RULES = """【房间使用约定】
1. 用 poll_messages(cursor=0) 拉历史，之后周期性用上次返回的 next_cursor 拉增量，被 @ 时必须先 poll 再回应。
2. 发言用 send_message(text=...)；交付成果用 send_message(type="deliver")。消息全体可见，@某人写 mentions=["agent_id"]。
3. 广播消息不要求内置 Agent 回应；想请某位内置成员发言，请显式 @ 其 agent_id。
4. 收到 priority=0 的 system 消息（P0 interrupt）时，立即停止当前动作并回一条确认。
5. 你的 agent_id 与身份卡已绑定，发言请遵守身份卡职责；离线前用 declare_status(status="offline") 告别。
6. 文件读写用 fs.list / fs.read / fs.write：交付物一律 fs.write 落工作区（覆盖已有文件必须传你最近一次读到的 version 作 base_version，冲突时重读重写），写成功后可 send_message(type="deliver") 附一句说明。
7. 多房间：先用 list_rooms 查你所在的全部房间；各工具均可传 room_id（默认 default）切换操作目标。
8. 技能库：skills.list / skills.read 可查内部技能（写法规范/模板/工作流），照着做即可。"""

def _agent_tools_allow(agent_id: str) -> list[str]:
    """该外部成员绑定身份卡的工具白名单（未绑卡 = 空 = 无 fs 工具）。"""
    with db() as conn:
        row = conn.execute(
            "SELECT i.tools_allow FROM agents a JOIN identities i ON i.id=a.identity_id"
            " WHERE a.id=?",
            (agent_id,),
        ).fetchone()
    return json.loads(row["tools_allow"] or "[]") if row else []


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def authenticate(agent_id: str, token: str) -> dict:
    """双因子校验：agent 存在 + 外部身份 + token 哈希匹配。返回 agents 行 dict。"""
    if not agent_id or not token:
        raise PermissionError("缺少 agent_id 或 token")
    with db() as conn:
        row = conn.execute(
            "SELECT id, name, room_id, kind, status, identity_id FROM agents WHERE id=?",
            (agent_id,),
        ).fetchone()
    if not row or (row["kind"] or "internal") != "external":
        raise PermissionError(f"成员 {agent_id} 不存在或不是外部成员")
    with db() as conn:
        h = conn.execute(
            "SELECT api_token_hash FROM agents WHERE id=?", (agent_id,)
        ).fetchone()
    if not h["api_token_hash"] or h["api_token_hash"] != hash_token(token):
        raise PermissionError("令牌无效或已吊销")
    return dict(row)


def _member_rooms(agent_id: str) -> list[str]:
    """该成员所在的全部房间（room_members 关系表）。"""
    with db() as conn:
        rows = conn.execute(
            "SELECT room_id FROM room_members WHERE agent_id=? ORDER BY room_id",
            (agent_id,)).fetchall()
    return [r["room_id"] for r in rows]


def _require_member(agent_id: str, room_id: str):
    """校验成员归属：不在该房间则拒绝（多房间权限边界）。"""
    if room_id not in _member_rooms(agent_id):
        raise PermissionError(f"你不在房间 {room_id} 中（所在房间：{_member_rooms(agent_id)}）")


def _err(e: Exception) -> str:
    return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


def _msg_dict(r) -> dict:
    """messages 行 -> 对外消息 dict（流式分片不落库，读到的都是完整消息）。"""
    return {
        "seq": r["id"],
        "msg_id": r["msg_id"],
        "type": r["type"],
        "priority": r["priority"],
        "sender": {"kind": r["sender_kind"], "id": r["sender_id"]},
        "text": r["full_text"] if r["full_text"] is not None else r["payload_text"],
        "mentions": json.loads(r["mentions"] or "[]"),
        "created_at": r["created_at"],
    }


async def _publish_external(bus_registry, room_id: str, msg: Message):
    """外部发言经房间总线落库扇出（与人类消息同通道）。"""
    bus = bus_registry.get(room_id)
    await bus.publish(msg)


def build_mcp_server(bus_registry) -> MCPServer:
    """构造网关 MCPServer；bus_registry 传入 BusRegistry 以广播。"""
    srv = MCPServer(
        name="agent-room",
        version="0.3.0",
        instructions="本机多 Agent 群聊房间。先 join_room 报到，再 poll_messages / send_message 交流。",
    )

    @srv.tool()
    async def join_room(agent_id: str, token: str, room_id: str = "default") -> str:
        """报到进群：校验令牌、置在线，广播进群消息，返回房间信息+群规。"""
        try:
            agent = authenticate(agent_id, token)
            _require_member(agent_id, room_id)
            with db() as conn:
                conn.execute(
                    "UPDATE agents SET status='online' WHERE id=?", (agent_id,)
                )
            from app.core.message import now_cst

            await _publish_external(
                bus_registry,
                room_id,
                Message(
                    room_id=room_id, type="system", priority=3,
                    sender_kind="system", sender_id="bus",
                    payload_text=f"{agent['name']}（外部成员）已进群。",
                    created_at=now_cst(),
                ),
            )
            return json.dumps({
                "ok": True,
                "agent_id": agent_id,
                "name": agent["name"],
                "room_id": room_id,
                "rooms": _member_rooms(agent_id),
                "tools_allow": _agent_tools_allow(agent_id),
                "rules": HOUSE_RULES,
            }, ensure_ascii=False)
        except Exception as e:
            return _err(e)

    @srv.tool()
    def poll_messages(agent_id: str, token: str, cursor: int = 0, limit: int = 50,
                      room_id: str = "default") -> str:
        """按游标拉增量消息：cursor 传上次返回的 next_cursor（初始 0）。"""
        try:
            agent = authenticate(agent_id, token)
            _require_member(agent_id, room_id)
            limit = max(1, min(int(limit), 200))
            with db() as conn:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE room_id=? AND id>? AND invalidated=0"
                    " ORDER BY id LIMIT ?",
                    (room_id, int(cursor), limit),
                ).fetchall()
                last = conn.execute(
                    "SELECT COALESCE(MAX(id),0) m FROM messages WHERE room_id=?",
                    (room_id,),
                ).fetchone()
            msgs = [_msg_dict(r) for r in rows]
            next_cursor = msgs[-1]["seq"] if msgs else int(cursor)
            return json.dumps({
                "ok": True,
                "messages": msgs,
                "next_cursor": next_cursor,
                "room_latest": last["m"],
                "has_p0": any(m["priority"] == 0 for m in msgs),
            }, ensure_ascii=False)
        except Exception as e:
            return _err(e)

    @srv.tool()
    async def send_message(
        agent_id: str,
        token: str,
        text: str,
        mentions: list[str] | None = None,
        type: str = "chat",
        client_msg_id: str | None = None,
        room_id: str = "default",
    ) -> str:
        """发言/交付：type=chat 交流 | deliver 交付成果；client_msg_id 用于重试去重。"""
        try:
            agent = authenticate(agent_id, token)
            _require_member(agent_id, room_id)
            text = str(text or "").strip()
            if not text:
                raise ValueError("消息内容不能为空")
            if type not in ("chat", "deliver"):
                raise ValueError("type 仅支持 chat | deliver")
            if client_msg_id:
                with db() as conn:
                    dup = conn.execute(
                        "SELECT id, msg_id FROM messages WHERE room_id=? AND sender_id=?"
                        " AND client_msg_id=?",
                        (room_id, agent_id, client_msg_id),
                    ).fetchone()
                if dup:
                    return json.dumps({
                        "ok": True, "deduplicated": True,
                        "seq": dup["id"], "msg_id": dup["msg_id"],
                    }, ensure_ascii=False)
            m = Message(
                room_id=room_id, type=type, priority=3,
                sender_kind="agent", sender_id=agent_id,
                payload_text=text,
                mentions=[str(x) for x in (mentions or [])],
            )
            if client_msg_id:
                m.client_msg_id = client_msg_id
            await _publish_external(bus_registry, room_id, m)
            return json.dumps({
                "ok": True, "msg_id": m.msg_id, "type": type,
            }, ensure_ascii=False)
        except Exception as e:
            return _err(e)

    @srv.tool()
    def declare_status(agent_id: str, token: str, status: str) -> str:
        """上报在线状态：status=online | offline | busy。"""
        try:
            agent = authenticate(agent_id, token)
            if status not in ("online", "offline", "busy"):
                raise ValueError("status 仅支持 online | offline | busy")
            with db() as conn:
                conn.execute(
                    "UPDATE agents SET status=? WHERE id=?", (status, agent_id)
                )
            return json.dumps({"ok": True, "status": status}, ensure_ascii=False)
        except Exception as e:
            return _err(e)

    # ---- 文件工作区（第 4 步）：fs.* 经 MCP 对外暴露，按身份卡 tools_allow 过滤 ----

    def _fs_guard(agent_id: str, token: str, tool: str) -> dict:
        """双因子 + 白名单双重校验；白名单在工具定义层（list_tools）已过滤，
        此处防直接 call_tool 越权。返回 agents 行。"""
        agent = authenticate(agent_id, token)
        if tool not in _agent_tools_allow(agent_id):
            raise PermissionError(f"工具 {tool} 不在该成员身份卡的白名单内")
        return agent

    async def _warn_violation(bus_registry, room_id: str, agent_id: str, tool: str):
        """越权拒绝：统一走 responder.announce_overreach（广播 + 拉 Agent B 通报）。"""
        from app.agents.responder import announce_overreach

        await announce_overreach(bus_registry, room_id, agent_id, tool)

    @srv.tool()
    async def fs_list(agent_id: str, token: str, room_id: str = "default") -> str:
        """列出房间文件工作区的全部文件（路径 / 版本 / 作者）。"""
        try:
            agent = _fs_guard(agent_id, token, "fs.list")
            _require_member(agent_id, room_id)
            result = await exec_fs_tool(room_id, agent_id, "fs.list", {})
            return result
        except Exception as e:
            if isinstance(e, PermissionError):
                await _warn_violation(bus_registry, room_id, agent_id, "fs.list")
            return _err(e)

    @srv.tool()
    async def fs_read(agent_id: str, token: str, path: str,
                      room_id: str = "default") -> str:
        """读取工作区文件内容与版本号。path 为相对路径（如 docs/方案.md）。"""
        try:
            agent = _fs_guard(agent_id, token, "fs.read")
            _require_member(agent_id, room_id)
            result = await exec_fs_tool(room_id, agent_id, "fs.read",
                                        {"path": path})
            return result
        except Exception as e:
            if isinstance(e, PermissionError):
                await _warn_violation(bus_registry, room_id, agent_id, "fs.read")
            return _err(e)

    @srv.tool()
    async def fs_write(agent_id: str, token: str, path: str, content: str,
                       base_version: int | None = None,
                       room_id: str = "default") -> str:
        """写文件到工作区（整体覆盖）。新建省略 base_version；覆盖已有文件必须传
        最近一次读到的 version 作 base_version，冲突时重读后重写。写成功自动发
        deliver 消息进群。"""
        try:
            agent = _fs_guard(agent_id, token, "fs.write")
            _require_member(agent_id, room_id)
            result = await exec_fs_tool(
                room_id, agent_id, "fs.write",
                {"path": path, "content": content, "base_version": base_version},
                bus_registry,
            )
            return result
        except Exception as e:
            if isinstance(e, PermissionError):
                await _warn_violation(bus_registry, room_id, agent_id, "fs.write")
            return _err(e)

    # ---- 多房间（第 6 步）：成员自查所在房间 ----

    @srv.tool()
    def list_rooms(agent_id: str, token: str) -> str:
        """列出你所在的全部房间（多房间时各工具传 room_id 切换操作目标）。"""
        try:
            authenticate(agent_id, token)
            with db() as conn:
                rows = conn.execute("SELECT id, name FROM rooms").fetchall()
            names = {r["id"]: r["name"] for r in rows}
            return json.dumps({
                "ok": True,
                "rooms": [{"id": rid, "name": names.get(rid, rid)}
                          for rid in _member_rooms(agent_id)],
            }, ensure_ascii=False)
        except Exception as e:
            return _err(e)

    # ---- 内部技能库（第 6 步）：skills.* 经 MCP 对外暴露，白名单同 fs ----

    @srv.tool()
    async def skills_list(agent_id: str, token: str) -> str:
        """列出内部技能库的全部技能（写法规范/模板/工作流）。"""
        try:
            g = _fs_guard(agent_id, token, "skills.list")
            _ = g
            result = await exec_fs_tool("default", agent_id, "skills.list", {})
            return result
        except Exception as e:
            if isinstance(e, PermissionError):
                await _warn_violation(bus_registry, "default", agent_id, "skills.list")
            return _err(e)

    @srv.tool()
    async def skills_read(agent_id: str, token: str, name: str) -> str:
        """读取某个技能的完整内容（先 skills.list 看有什么）。"""
        try:
            g = _fs_guard(agent_id, token, "skills.read")
            _ = g
            result = await exec_fs_tool("default", agent_id, "skills.read", {"name": name})
            return result
        except Exception as e:
            if isinstance(e, PermissionError):
                await _warn_violation(bus_registry, "default", agent_id, "skills.read")
            return _err(e)

    @srv.tool()
    async def memory_query(agent_id: str, token: str, query: str,
                           room_id: str = "default") -> str:
        """检索房间公共记忆（历史任务结论、归档摘要）；私有记忆不在结果内。"""
        try:
            g = _fs_guard(agent_id, token, "memory.query")
            _ = g
            _require_member(agent_id, room_id)
            result = await exec_fs_tool(room_id, agent_id, "memory.query",
                                        {"query": query})
            return result
        except Exception as e:
            if isinstance(e, PermissionError):
                await _warn_violation(bus_registry, room_id, agent_id, "memory.query")
            return _err(e)

    @srv.tool()
    async def chat_delete(agent_id: str, token: str, seqs: list[int],
                          room_id: str = "default") -> str:
        """按界面序号定向删除消息（软删，立即对全群不可见）。seqs 即气泡 #n 编号列表。"""
        try:
            g = _fs_guard(agent_id, token, "chat.delete")
            _ = g
            _require_member(agent_id, room_id)
            return await exec_fs_tool(room_id, agent_id, "chat.delete",
                                      {"seqs": seqs})
        except Exception as e:
            if isinstance(e, PermissionError):
                await _warn_violation(bus_registry, room_id, agent_id, "chat.delete")
            return _err(e)

    return srv


def mount_gateway(parent_app, bus_registry):
    """把网关以 streamable-http 挂到 /gateway/mcp（同端口 8899）。

    注意：Starlette 的 Mount 不会运行子应用自己的 lifespan，因此
    session_manager.run()（async context manager，须在服务事件循环内进入）
    必须挂到父应用的 lifespan 上——这里包装父应用原有的 lifespan_context。
    """
    srv = build_mcp_server(bus_registry)
    sub = srv.streamable_http_app(stateless_http=True)

    parent_lifespan = parent_app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with srv.session_manager.run():
            async with parent_lifespan(app):
                yield

    parent_app.router.lifespan_context = lifespan
    parent_app.mount("/gateway", sub)
    return srv
