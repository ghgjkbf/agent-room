"""聊天记录定时归档清理（第 5.5 步，由内置 Agent B 承担）。

互聊轮次不设上限（s5 的 budget_turns 熔断已移除）后，为防 messages 事件流
无限膨胀，Agent B 作为「群聊管家」定时执行：
  1. 检查自上次归档游标以来的 chat 消息数，达到 janitor_min_msgs 即归档；
  2. 把这批聊天总结成摘要 → 写入房间公共记忆（LLM 总结，未配置降级占位）；
  3. 摘要完成后物理删除这批 chat 消息；dispatch/receipt/task_plan/system 等
     关键编排与系统消息保留；
  4. 群里发一条归档回执（sender=agent_b），游标存 kv 表。
定时循环由 FastAPI lifespan 拉起（main.py），run_janitor_once 可独立调用测试。
"""

import asyncio
import json

from app.core.config import settings
from app.core.db import db
from app.core.message import Message, now_cst

def cursor_key(room_id: str) -> str:
    return f"janitor_last_msg_id:{room_id}"


def _get_cursor(conn, room_id) -> int:
    row = conn.execute("SELECT v FROM kv WHERE k=?", (cursor_key(room_id),)).fetchone()
    return int(row["v"]) if row else 0


async def _summarize(blob: str, n: int) -> str:
    """LLM 总结群聊要点；未配置或失败降级占位摘要。"""
    if settings.llm_ready():
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(base_url=settings.llm_base_url,
                                 api_key=settings.llm_api_key)
            r = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content":
                        "你是群聊管家 Agent B：把群聊记录总结成 200 字以内的要点摘要"
                        "（讨论了什么、达成了什么、遗留什么），只输出摘要正文。"},
                    {"role": "user", "content": blob[:4000]},
                ],
                temperature=0.3)
            text = (r.choices[0].message.content or "").strip()
            if text:
                return text
        except Exception:
            pass
    head = blob[:100].replace("\n", " ")
    return f"（占位摘要·LLM 未配置）共 {n} 条聊天，开头内容：{head}…"


async def run_janitor_once(room_id: str = "default", bus_registry=None,
                           force: bool = False) -> dict:
    """跑一轮检查与归档；force=True 跳过阈值（手动触发/Agent 工具调用）。

    返回 {"archived": 归档条数}，未达阈值且未强制时返回 {"archived": 0}。"""
    with db() as conn:
        last = _get_cursor(conn, room_id)
        rows = conn.execute(
            "SELECT id, sender_id, COALESCE(NULLIF(full_text,''), payload_text) AS text"
            " FROM messages WHERE room_id=? AND type='chat' AND id>? ORDER BY id",
            (room_id, last),
        ).fetchall()
    if not force and len(rows) < settings.janitor_min_msgs:
        return {"archived": 0}

    cursor = rows[-1]["id"]
    blob = "\n".join(f"{r['sender_id']}: {(r['text'] or '')[:200]}" for r in rows)
    summary = await _summarize(blob, len(rows))
    ts = now_cst()
    from app.memory.hub import hub

    await hub.write_public(
        room_id, f"聊天归档摘要（Agent B · {len(rows)} 条）：{summary}",
        {"id": f"janitor_{cursor}", "kind": "chat_digest"}, ts)

    with db() as conn:
        conn.execute("DELETE FROM messages WHERE room_id=? AND type='chat' AND id<=?",
                     (room_id, cursor))
        conn.execute(
            "INSERT INTO kv (k, v) VALUES (?,?)"
            " ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (cursor_key(room_id), str(cursor)))

    if bus_registry is not None:
        await bus_registry.get(room_id).publish(Message(
            room_id=room_id, type="system", sender_kind="agent",
            sender_id="agent_b",
            payload_text=(f"🧹 群聊管家归档：本轮已总结 {len(rows)} 条聊天记录并清理存储，"
                          "摘要已写入公共记忆（记忆面板可查）。")))
    return {"archived": len(rows)}


async def janitor_loop(room_id: str = "default", bus_registry=None):
    """lifespan 拉起的定时循环：每轮遍历全部房间各检查一次，异常不中断。"""
    from app.rooms.bus import BusRegistry

    registry = bus_registry or BusRegistry
    while True:
        try:
            with db() as conn:
                rooms = [r["id"] for r in conn.execute("SELECT id FROM rooms").fetchall()]
        except Exception:
            rooms = [room_id]
        for rid in rooms:
            try:
                await run_janitor_once(rid, registry)
            except Exception:
                pass
        await asyncio.sleep(settings.janitor_interval_s)
