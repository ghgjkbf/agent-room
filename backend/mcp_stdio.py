"""agent-room MCP stdio 桥（TRAE 等仅支持命令行 MCP 的客户端用）。

用法（TRAE mcp.json 配置示例）：
  {"mcpServers": {"agent-room": {
      "command": "<venv python 路径>",
      "args": ["<本文件路径>"],
      "env": {"AGENT_ROOM_URL": "http://127.0.0.1:8899/gateway/mcp"}
  }}}

实现：stdin 收 MCP JSON-RPC 帧 -> HTTP POST 到网关 /gateway/mcp（json_response
形态，单发单收）-> stdout 回写。无状态直通，initialize 的 mcp-session-id 在
连接生命周期内保持。
"""

import asyncio
import json
import os
import sys

import httpx2

GATEWAY_URL = os.environ.get("AGENT_ROOM_URL", "http://127.0.0.1:8899/gateway/mcp")


async def _post(client: httpx2.AsyncClient, session_id: str | None, body: dict):
    # 网关挂在 8899（json_response=False），协议要求 Accept 同时含 json 与 event-stream；
    # initialize 响应可能是 SSE 帧，data: 行里取 JSON。
    headers = {"Accept": "application/json, text/event-stream"}
    if session_id:
        headers["mcp-session-id"] = session_id
    r = await client.post(GATEWAY_URL, json=body, headers=headers)
    if r.status_code == 202 or not r.content:
        return r.status_code, r.headers.get("mcp-session-id"), None
    ctype = r.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        data = None
        for line in r.text.splitlines():
            if line.startswith("data:"):
                data = line[5:].strip()
        if data:
            return r.status_code, r.headers.get("mcp-session-id"), json.loads(data)
        return r.status_code, r.headers.get("mcp-session-id"), None
    return r.status_code, r.headers.get("mcp-session-id"), r.json()


async def amain():
    client = httpx2.AsyncClient(trust_env=False, timeout=120)
    session_id: str | None = None
    loop = asyncio.get_running_loop()
    try:
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                frame = json.loads(line)
            except json.JSONDecodeError:
                continue
            is_request = "id" in frame
            status, sid, resp = await _post(client, session_id, frame)
            if sid:
                session_id = sid
            if is_request and status == 200 and resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
            # 通知或 202：无响应帧
    finally:
        await client.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(amain())
    except (KeyboardInterrupt, BrokenPipeError):
        pass
