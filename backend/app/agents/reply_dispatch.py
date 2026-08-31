"""成员互聊回复调度（v0.9 成员平权 + 按卡选人）。

挂为 RoomBus 总线监听器：任何成员（人类 WS / 外部网关 / 内置）发布的
agent chat 广播，按 plan_replies 决定谁接话。
- 人类消息（sender_kind=human）照旧在 _ws_loop 内联调度，本监听器跳过。
- 防死循环护栏：连锁回复（is_reply=True）不再自动唤起他人，只有
  显式 @（mentions 非空，经 WS/网关发出）或排产单 dispatch 定向唤起。
- 噪声控制（按卡选人）：广播唤起先做 focus 领域匹配（身份卡 focus
  关键词 vs 消息文本），命中的才接话；无命中时管家 B（或首个内置成员）
  兜底，外部成员默认静默——「来干活，不唠嗑」。
"""

import asyncio
import json

from app.agents.responder import GenerationRegistry, plan_replies, respond_agent
from app.core.db import db

BUILTIN_IDS = ("agent_a", "agent_b")
STEWARD_ID = "agent_b"


def _load_cards(agent_ids: list[str]) -> dict[str, list[str]]:
    """批量取成员身份卡的 focus 关键词；无卡/未绑定 → []（默认静默）。"""
    if not agent_ids:
        return {}
    out = {}
    with db() as conn:
        q = ",".join("?" for _ in agent_ids)
        rows = conn.execute(
            f"SELECT a.id AS aid, i.focus FROM agents a"
            f" LEFT JOIN identities i ON i.id = a.identity_id WHERE a.id IN ({q})",
            agent_ids,
        ).fetchall()
    for r in rows:
        try:
            out[r["aid"]] = json.loads(r["focus"] or "[]")
        except Exception:
            out[r["aid"]] = []
    return out


def _focus_match(text: str, agents: list[dict]) -> list[dict]:
    """focus 关键词与消息文本做不区分大小写的包含匹配；命中者接话。"""
    text_low = (text or "").lower()
    hits = []
    cards = _load_cards([a["id"] for a in agents])
    for a in agents:
        kws = [k.lower() for k in cards.get(a["id"], []) if k]
        if any(k in text_low for k in kws):
            hits.append(a)
    return hits


def _fallback_builtin(agents: list[dict]) -> list[dict]:
    """无命中时唤起管家 B；B 不在场则任一内置成员；都没有则静默。"""
    for pref in (STEWARD_ID,) + BUILTIN_IDS:
        for a in agents:
            if a["id"] == pref:
                return [a]
    return []


async def dispatch_replies(bus, msg):
    """总线监听器：agent chat 广播 → 按卡选人唤起（含 is_reply 护栏）。"""
    if msg.type != "chat" or msg.sender_kind != "agent":
        return
    # 流式中间片 / 终止信号不触发回复（真实正文落库后带 is_reply 的是首条）
    if not msg.is_final or msg.stream_seq > 0:
        return
    if getattr(msg, "is_reply", False):
        return  # 连锁回复不再唤起，防 A↔B 死循环
    with db() as conn:
        rows = conn.execute(
            "SELECT a.id, a.name FROM room_members m"
            " JOIN agents a ON a.id = m.agent_id"
            " WHERE m.room_id=? ORDER BY a.id",
            (bus.room_id,),
        ).fetchall()
    online = [{"id": r["id"], "name": r["name"]} for r in rows]
    # mentions 命中（@定向）由 plan_replies 处理，不受 focus 限制
    if msg.mentions:
        selected = plan_replies(msg, online)
    else:
        hits = _focus_match(msg.payload_text, [a for a in online if a["id"] != msg.sender_id])
        selected = hits or _fallback_builtin(online)
        # 兜底人与发言者重合时静默（自己不接自己的话）
        selected = [a for a in selected if a["id"] != msg.sender_id]

    for agent in selected:
        t = asyncio.create_task(respond_agent(bus, msg, agent))
        GenerationRegistry.register(agent["id"], t)
