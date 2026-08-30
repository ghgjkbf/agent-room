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

# ---- 能力工具层（解决内置 Agent 白板：电脑控制/浏览器/文档/技能创建） ----
# 全部白名单门控；shell.run 属高危能力，不进出厂卡，需显式勾选

CAP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "shell.run",
            "description": "在本机执行命令行（PowerShell/cmd），工作目录为房间工作区。高危能力："
                           "仅在你确需执行命令时使用，输出超长会被截断。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令"},
                    "timeout": {"type": "integer", "description": "超时秒数，默认 30，最大 120"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser.open",
            "description": "读取网页内容：抓取 URL 并返回标题 + 正文文本（去脚本/样式，截断保存）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "完整 URL（http/https）"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "doc.read",
            "description": "读取文档文件为 Markdown（支持 pdf/docx/pptx/xlsx/epub 等，"
                           "依赖 markitdown；工作区内传相对路径，本机文件传绝对路径）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "工作区相对路径或本机绝对路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skills.write",
            "description": "创建或更新内部技能（把你的经验/方法沉淀为技能，供全群使用）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名（文字/数字/连字符）"},
                    "content": {"type": "string", "description": "Markdown 内容：用途/工作流/模板/要求"},
                },
                "required": ["name", "content"],
            },
        },
    },
]

ALL_TOOLS = FS_TOOLS + SKILL_TOOLS + MEMORY_TOOLS + CAP_TOOLS


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


async def _exec_shell(room_id: str, command: str, timeout: int) -> str:
    """电脑控制：本机命令执行（cwd=房间工作区；输出截断 4000 字）。"""
    import asyncio as _aio
    from app.files import workspace

    workspace.ensure_dir(room_id)
    timeout = max(1, min(timeout, 120))
    try:
        proc = await _aio.create_subprocess_shell(
            command, cwd=workspace.room_dir(room_id),
            stdout=_aio.subprocess.PIPE, stderr=_aio.subprocess.STDOUT)
        try:
            out, _ = await _aio.wait_for(proc.communicate(), timeout=timeout)
            text = out.decode("utf-8", errors="replace")
            code = proc.returncode
        except _aio.TimeoutError:
            proc.kill()
            return json.dumps({"ok": False, "error": f"命令超时（>{timeout}s）已终止"},
                              ensure_ascii=False)
        return json.dumps({"ok": code == 0, "exit_code": code,
                           "output": text[:4000]}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"},
                          ensure_ascii=False)


async def _exec_browser(url: str) -> str:
    """浏览器控制（读取）：抓取网页标题与正文文本。"""
    import re as _re

    if not url.startswith(("http://", "https://")):
        return json.dumps({"ok": False, "error": "仅支持 http/https URL"}, ensure_ascii=False)
    try:
        import httpx2

        async with httpx2.AsyncClient(trust_env=False, timeout=20, follow_redirects=True) as c:
            resp = await c.get(url)
            html = resp.text
        title = _re.search(r"<title[^>]*>(.*?)</title>", html, _re.S | _re.I)
        body = _re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
        body = _re.sub(r"(?s)<[^>]+>", " ", body)
        body = _re.sub(r"\s+", " ", body).strip()
        return json.dumps({"ok": True, "url": str(resp.url),
                           "title": title.group(1).strip() if title else "",
                           "text": body[:6000]}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"},
                          ensure_ascii=False)


async def _exec_doc_read(room_id: str, path: str) -> str:
    """文档技能：pdf/docx/pptx/xlsx 等 → Markdown（markitdown，可选依赖）。"""
    import os

    from app.files import workspace

    if os.path.isabs(path):
        fp = path
    else:
        try:
            fp = workspace.read_file(room_id, path)["path"]
            fp = os.path.join(workspace.room_dir(room_id), fp)
        except Exception:
            fp = os.path.join(workspace.room_dir(room_id), path)
    if not os.path.isfile(fp):
        return json.dumps({"ok": False, "error": f"文件不存在：{path}"}, ensure_ascii=False)
    try:
        from markitdown import MarkItDown

        text = MarkItDown().convert(fp).text_content
        return json.dumps({"ok": True, "path": path, "markdown": text[:12000]},
                          ensure_ascii=False)
    except ImportError:
        return json.dumps({"ok": False, "error":
            "需要 markitdown 支持：backend\.venv\Scripts\pip install markitdown"},
            ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"},
                          ensure_ascii=False)


async def exec_fs_tool(room_id: str, author: str, name: str, args: dict,
                       bus_registry=None) -> str:
    """异步包装：磁盘/DB 操作放线程池，写成功后补发 deliver。"""
    if name == "shell.run":
        return await _exec_shell(room_id, str(args.get("command", "")),
                                 int(args.get("timeout") or 30))
    if name == "browser.open":
        return await _exec_browser(str(args.get("url", "")))
    if name == "doc.read":
        return await _exec_doc_read(room_id, str(args.get("path", "")))
    if name == "skills.write":
        from app.skills import store

        try:
            out = store.write_skill(str(args.get("name", "")), str(args.get("content", "")))
            return json.dumps({"ok": True, **out}, ensure_ascii=False)
        except (ValueError, OSError) as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
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
