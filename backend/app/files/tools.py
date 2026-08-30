"""fs.* 工具集（第 4 步）：OpenAI function calling 与 MCP 网关共用的定义与执行器。

- 三个工具：fs.list / fs.read / fs.write（fs.write 内置 base_version 乐观锁）
- FS_TOOLS：OpenAI tools 参数 schema（供 responder 工具循环）
- filter_tools(tools_allow)：按身份卡白名单严格过滤，没勾的拿不到工具定义
- 执行 fs.write 成功后自动向房间总线发布 type=deliver 消息（进事件流可回放）
- 一切错误以结构化 JSON 文本返回（isError 约定），不抛栈泄漏
"""

import asyncio
import json

from fastapi import HTTPException

from app.core.db import db
from app.core.message import Message
from app.files import workspace

# ---- OpenAI function calling schema（tools 参数） ----

FS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fs.list",
            "description": "列出文件工作区中的全部文件（含版本号与作者）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fs.read",
            "description": "读取文件工作区中某个文件的完整内容与版本号。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径，如 docs/方案.md"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fs.write",
            "description": "写入文件到工作区（整体覆盖式写）。新建文件省略 base_version；"
                           "覆盖已有文件必须传你最后一次读到的 version 作为 base_version，"
                           "冲突时请重读文件再重写。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径，如 docs/方案.md"},
                    "content": {"type": "string", "description": "完整文件内容（UTF-8 文本）"},
                    "base_version": {"type": "integer", "description": "覆盖已有文件时的基准版本号；新建省略"},
                },
                "required": ["path", "content"],
            },
        },
    },
]

# ---- skills.* 工具（内部技能库：写法规范/模板/工作流 md，Agent 自查照做） ----

SKILL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "skills.list",
            "description": "列出内部技能库的全部技能（写法规范/模板/工作流）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skills.read",
            "description": "读取某个技能的完整内容（先 skills.list 看有什么）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名，如 meeting-notes"},
                },
                "required": ["name"],
            },
        },
    },
]

# ---- memory.query 工具（公共记忆检索；私有记忆永不进入结果） ----

MEMORY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "memory.query",
            "description": "检索房间公共记忆（历史任务结论、归档摘要等）。只返回公共记忆，查不到私有记忆。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索问题，如 上次口号任务的结论"},
                },
                "required": ["query"],
            },
        },
    },
]

ALL_TOOLS = FS_TOOLS + SKILL_TOOLS + MEMORY_TOOLS


def filter_tools(tools_allow: list[str] | None) -> list[dict]:
    """按身份卡 tools_allow 过滤；白名单外的工具不进定义（严格模式）。"""
    allow = set(tools_allow or [])
    return [t for t in ALL_TOOLS if t["function"]["name"] in allow]


async def _notify_deliver(bus_registry, room_id: str, author: str, path: str, version: int, size: int):
    """fs.write 成功后自动发 deliver 消息（设计决策：交付进事件流可回放）。"""
    if not bus_registry:
        return
    try:
        await bus_registry.get(room_id).publish(Message(
            room_id=room_id, type="deliver", priority=3,
            sender_kind="agent", sender_id=author,
            payload_text=f"已交付文件 {path}（v{version}，{size} 字符）",
            mentions=[],
        ))
    except Exception:
        pass  # 通知失败不影响写文件本身


def exec_fs_tool_sync(room_id: str, author: str, name: str, args: dict) -> str:
    """同步执行 fs.* 工具（供 asyncio.to_thread 调用）。返回 JSON 文本。"""
    try:
        if name == "fs.list":
            files = workspace.list_files(room_id)
            return json.dumps({"ok": True, "files": [
                {"path": f["path"], "version": f["version"], "author": f["author"]}
                for f in files
            ]}, ensure_ascii=False)

        if name == "fs.read":
            f = workspace.read_file(room_id, str(args.get("path", "")))
            return json.dumps({
                "ok": True, "path": f["path"], "version": f["version"],
                "author": f["author"], "content": f["content"],
            }, ensure_ascii=False)

        if name == "fs.write":
            result = workspace.write_file(
                room_id=room_id,
                path=str(args.get("path", "")),
                content=str(args.get("content", "")),
                author=author,
                base_version=args.get("base_version"),
            )
            result["ok"] = True
            # deliver 通知在异步上下文发（此处只存标记，由异步包装器发布）
            result["_deliver"] = {"path": result["path"], "version": result["version"],
                                  "size": len(str(args.get("content", "")))}
            return json.dumps(result, ensure_ascii=False)

        if name == "skills.list":
            from app.skills import store

            return json.dumps({"ok": True, "skills": [s["name"] for s in store.list_skills()]},
                              ensure_ascii=False)

        if name == "skills.read":
            from app.skills import store

            try:
                s = store.read_skill(str(args.get("name", "")))
                return json.dumps({"ok": True, **s}, ensure_ascii=False)
            except FileNotFoundError as e:
                return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
            except ValueError as e:
                return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

        return json.dumps({"ok": False, "error": f"未知工具：{name}"}, ensure_ascii=False)
    except HTTPException as e:
        detail = e.detail
        if isinstance(detail, dict):
            return json.dumps({"ok": False, **detail}, ensure_ascii=False)
        return json.dumps({"ok": False, "error": str(detail)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)


async def exec_fs_tool(room_id: str, author: str, name: str, args: dict,
                       bus_registry=None) -> str:
    """异步包装：磁盘/DB 操作放线程池，写成功后补发 deliver。"""
    if name == "memory.query":
        from app.memory.hub import hub

        try:
            hits = await hub.search_public(room_id, str(args.get("query", "")), k=5)
            return json.dumps({"ok": True, "hits": hits}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"},
                              ensure_ascii=False)
    result_text = await asyncio.to_thread(exec_fs_tool_sync, room_id, author, name, args)
    try:
        data = json.loads(result_text)
        deliver = data.pop("_deliver", None)
        if data.get("ok") and deliver and name == "fs.write":
            await _notify_deliver(bus_registry, room_id, author,
                                  deliver["path"], deliver["version"], deliver["size"])
            result_text = json.dumps(data, ensure_ascii=False)
    except Exception:
        pass
    return result_text


def agent_has_fs(agent_id: str, tool_name: str) -> bool:
    """运行时复核：Agent 当前绑定的身份卡是否允许该工具。"""
    with db() as conn:
        row = conn.execute(
            "SELECT i.tools_allow FROM agents a JOIN identities i ON i.id=a.identity_id"
            " WHERE a.id=?",
            (agent_id,),
        ).fetchone()
    if not row:
        return False
    allow = json.loads(row["tools_allow"] or "[]")
    return tool_name in allow
