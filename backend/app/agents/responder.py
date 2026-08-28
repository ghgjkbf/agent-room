"""内置 LLM Agent 回复器（第 2 步：双 Agent + 身份卡 + 可抢占）。

- 每个在线内置 Agent 独立任务并行回复，互不共享对话（防串味，s5）。
- mentions 非空时仅被 @ 的 Agent 回复；广播时全体回复。
- 身份卡 persona/responsibilities 注入 system prompt；单 Agent 互聊
  轮数超 budget_turns 由总线发 system 熔断消息并 @人类。
- 生成句柄登记到 GenerationRegistry，P0 interrupt 可 cancel 当前流式生成。
"""

import asyncio
import json
import uuid

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.db import db
from app.core.message import Message

# 单条分段推送的最大字符数，模拟流式节奏（真实 LLM 时逐 token 分段）
CHUNK_SIZE = 24


class GenerationRegistry:
    """agent_id -> asyncio.Task；P0 到达时 cancel 对应生成。"""

    _tasks: dict[str, asyncio.Task] = {}

    @classmethod
    def register(cls, agent_id: str, task: asyncio.Task):
        cls._tasks[agent_id] = task

    @classmethod
    def cancel_all(cls) -> int:
        n = 0
        for aid, t in list(cls._tasks.items()):
            if not t.done():
                t.cancel()
                n += 1
        return n


def load_identity(agent_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT i.* FROM agents a JOIN identities i ON i.id = a.identity_id WHERE a.id=?",
            (agent_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "label": row["label"],
        "persona": row["persona"] or "",
        "responsibilities": json.loads(row["responsibilities"] or "[]"),
    }


def bump_turns(agent_id: str) -> int:
    """内置 Agent 轮数 +1 并返回剩余额度；外部成员不受熔断管辖（返回大数）。"""
    with db() as conn:
        row = conn.execute("SELECT kind FROM agents WHERE id=?", (agent_id,)).fetchone()
        if row and (row["kind"] or "internal") == "external":
            return 9999
        conn.execute("UPDATE agents SET chat_turns = chat_turns + 1 WHERE id=?", (agent_id,))
        row = conn.execute(
            "SELECT a.chat_turns, COALESCE(i.budget_turns, 6) AS budget"
            " FROM agents a LEFT JOIN identities i ON i.id = a.identity_id"
            " WHERE a.id=?",
            (agent_id,),
        ).fetchone()
    return int(row["budget"]) - int(row["chat_turns"])


def reset_turns():
    with db() as conn:
        conn.execute("UPDATE agents SET chat_turns = 0")


async def stream_text(agent_id: str, identity: dict | None, user_text: str):
    """产出文本片段。LLM 未配置时降级为本地占位（逐片 yield）。"""
    if settings.llm_base_url and settings.llm_api_key and settings.llm_model:
        client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)
        sys_parts = ["你是群聊房间里的 AI 助手，简洁回答，遵守身份卡职责。"]
        if identity:
            role = f"你的标签是「{identity['label']}」"
            if identity["persona"]:
                role += f"；风格：{identity['persona']}"
            resp = identity.get("responsibilities") or []
            if resp:
                role += "；职责：" + "、".join(resp)
            sys_parts.append(role + "。只回答与身份相关的问题，越界时简短说明并引导提问者换人。")
        else:
            sys_parts.append(f"你是 {agent_id}，未绑定身份卡。")
        stream = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "system", "content": "\n".join(sys_parts)},
                      {"role": "user", "content": user_text}],
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
        return
    name = identity["label"] if identity else agent_id
    text = (
        f"[{name}·占位] 已收到：「{user_text}」。"
        + (f"我按「{identity['label']}」的职责行事。" if identity else "我尚未绑定身份卡。")
        + "（可在左侧「模型设置」接入真实 LLM）"
    )
    for i in range(0, len(text), CHUNK_SIZE):
        await asyncio.sleep(0.35)
        yield text[i : i + CHUNK_SIZE]


def _split(text: str):
    for i in range(0, len(text), CHUNK_SIZE):
        yield text[i : i + CHUNK_SIZE]


async def respond_agent(bus, msg: Message, agent: dict):
    """单个 Agent 的回复协程：流式发布 chat 片段，异常转 system 消息。

    片段协议：同一 msg_id + stream_seq 递增，尾片 is_final=True。
    落库策略：只把首条消息存入事件流（payload 存最终全文），后续片段仅广播
    不落库——历史回放时读 full_text 即得完整原文，且消息表不再碎片化。
    """
    aid = agent["id"]
    try:
        identity = load_identity(aid)
        reply_id = str(uuid.uuid4())
        got_llm = bool(settings.llm_base_url and settings.llm_api_key and settings.llm_model)
        pieces = []
        async for piece in stream_text(aid, identity, msg.payload_text):
            pieces.append(piece)
            seq = len(pieces) - 1  # 0,1,2...；0 为首片
            if seq == 0:
                # 首片：先落一条事件流条目占位（payload 空），全文等收完再补写
                m = Message(
                    room_id=bus.room_id, type="chat",
                    sender_kind="agent", sender_id=aid,
                    payload_text="", stream_seq=0, is_final=False,
                    msg_id=reply_id,
                )
                await bus.publish(m)
            # 实际内容统一走纯广播通道（不落库）；首片也必须发，否则开头丢失
            stream_piece = Message(
                room_id=bus.room_id, type="chat",
                sender_kind="agent", sender_id=aid,
                payload_text=piece, stream_seq=seq,
                is_final=False, msg_id=reply_id,
            )
            await bus.broadcast_raw(json.dumps(stream_piece.to_dict(), ensure_ascii=False))
        final_text = "".join(pieces)
        if not final_text:
            final_text = "[占位] 已收到你的消息。" if not got_llm else "[占位] （模型未返回内容）"
            for piece in _split(final_text):
                data = json.dumps(Message(
                    room_id=bus.room_id, type="chat", sender_kind="agent",
                    sender_id=aid, payload_text=piece, stream_seq=1,
                    is_final=False, msg_id=reply_id,
                ).to_dict(), ensure_ascii=False)
                await bus.broadcast_raw(data)
        with db() as conn:
            conn.execute(
                "UPDATE messages SET payload_text=?, full_text=?, is_final=1 WHERE msg_id=?",
                (final_text, final_text, reply_id),
            )
        # 终止信号：前端用它判断该 Agent 本次流式结束（payload 可为空）
        await bus.broadcast_raw(json.dumps(Message(
            room_id=bus.room_id, type="chat", sender_kind="agent",
            sender_id=aid, payload_text="",
            stream_seq=len(pieces), is_final=True, msg_id=reply_id,
        ).to_dict(), ensure_ascii=False))
        remaining = bump_turns(aid)
        if remaining <= 0 and identity:
            label = identity["label"]
            await bus.publish(Message(
                room_id=bus.room_id, type="system", priority=2,
                sender_kind="system", sender_id="bus",
                payload_text=f"熔断：Agent {aid}（{label}）互聊轮数已达上限，已自动 @人类 裁决。",
                mentions=["human"],
            ))
    except asyncio.CancelledError:
        # 被打断的生成：首片仍留在库中（payload 空），标记终止避免前端悬挂
        try:
            with db() as conn:
                conn.execute(
                    "UPDATE messages SET payload_text='（已被 P0 中断）',"
                    " full_text='（已被 P0 中断）', is_final=1 WHERE msg_id=?",
                    (locals().get("reply_id", ""),),
                )
            reply_id = locals().get("reply_id")
            if reply_id:
                await bus.broadcast_raw(json.dumps(Message(
                    room_id=bus.room_id, type="system", priority=2,
                    sender_kind="system", sender_id="bus",
                    payload_text=f"P0 生效：{aid} 的生成已被中断。",
                ).to_dict(), ensure_ascii=False))
        except Exception:
            pass
        raise
    except Exception as e:
        await bus.publish(Message(
            room_id=bus.room_id, type="system", priority=2,
            sender_kind="system", sender_id="bus",
            payload_text=f"{aid} 回复失败：{type(e).__name__}: {e}",
        ))


def plan_replies(msg: Message, online_agents: list[dict]) -> list[dict]:
    """根据 mentions 决定谁回复：mentions 命中的优先，否则广播全员。

    防死循环规则（第 3 步）：外部 Agent 发来的消息只有显式 @ 到某内置 Agent
    才唤起它——广播不触发自动回复，避免「客套互捧」循环（设计文档风险表 s13）。
    """
    if msg.mentions:
        mentioned = [a for a in online_agents if a["id"] in msg.mentions]
        return mentioned
    if msg.sender_kind == "agent":
        # 发送方是 Agent（含外部成员经网关 send_message）时不广播接话
        return []
    return online_agents
