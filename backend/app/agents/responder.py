"""内置 LLM Agent 回复器（第 2 步：双 Agent + 身份卡 + 可抢占）。

- 每个在线内置 Agent 独立任务并行回复，互不共享对话（防串味，s5）。
- mentions 非空时仅被 @ 的 Agent 回复；广播时全体回复。
- 身份卡 persona/responsibilities 注入 system prompt；未绑定身份卡时使用
  内置默认职责（第 5.5 步：Agent A 服务用户，Agent B 服务群聊管家）。
- 生成句柄登记到 GenerationRegistry，P0 interrupt 可 cancel 当前流式生成。
- 第 4 步：stream_text → run_turn 工具循环（OpenAI Function Calling）——
  stream 中 tool_calls → 执行 → 回灌 → 直至纯文本回复；工具按身份卡
  tools_allow 严格过滤；LLM 未配置时占位路径原样保留。
- 第 5.5 步：互聊轮次熔断移除（不设上限，存储膨胀由 Agent B 定时归档清理，
  见 app/rooms/janitor.py）。
"""

import asyncio
import json
import uuid

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.db import db
from app.core.message import Message
from app.files.tools import exec_fs_tool, filter_tools

# 单条分段推送的最大字符数，模拟流式节奏（真实 LLM 时逐 token 分段）
CHUNK_SIZE = 24
# 工具循环上限（防失控，与互聊轮数无关）
MAX_TOOL_ROUNDS = 8

# 内置双 Agent 的默认职责（专属 md 缺失时的兜底；完整规范见 backend/agent_md/*.md）
DEFAULT_ROLES = {
    "agent_a": ("Agent A·用户服务助手：服务人类用户——答疑解惑、辅助用户生成提示词、"
                "提供指导意见、协助调度与安排任务、监督其他 Agent 的进展。"),
    "agent_b": ("Agent B·群聊管家：服务群聊本身——定期总结归档聊天记录、监督群聊"
                "定时清理、维护群聊上下文连贯与秩序。"),
}

# Agent 专属规范 md（backend/agent_md/{agent_id}.md，mtime 缓存）
_MD_CACHE: dict[str, tuple[float, str]] = {}


def load_agent_md(agent_id: str) -> str:
    import os

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "..", "agent_md", f"{agent_id}.md")
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        return ""
    try:
        mtime = os.path.getmtime(path)
        hit = _MD_CACHE.get(agent_id)
        if hit and hit[0] == mtime:
            return hit[1]
        with open(path, encoding="utf-8") as f:
            text = f.read()
        _MD_CACHE[agent_id] = (mtime, text)
        return text
    except Exception:
        return ""


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
        "tools_allow": json.loads(row["tools_allow"] or "[]"),
    }


def build_system_prompt(agent_id: str, identity: dict | None) -> str:
    sys_parts = ["你是群聊房间里的 AI 助手，简洁回答，遵守身份卡职责。",
                 "群聊输出规范：禁用 Markdown 标题、表格与代码块围栏（气泡流不是文档），分点用「1.」或「-」，每段不超过 3 行。"]
    if identity:
        role = f"你的标签是「{identity['label']}」"
        if identity["persona"]:
            role += f"；风格：{identity['persona']}"
        resp = identity.get("responsibilities") or []
        if resp:
            role += "；职责：" + "、".join(resp)
        sys_parts.append(role + "。只回答与身份相关的问题，越界时简短说明并引导提问者换人。")
    elif agent_id in DEFAULT_ROLES:
        md = load_agent_md(agent_id)
        sys_parts.append(md if md else f"你是 {DEFAULT_ROLES[agent_id]}")
    else:
        sys_parts.append(f"你是 {agent_id}，未绑定身份卡。")
    return "\n".join(sys_parts)


def placeholder_text(agent_id: str, identity: dict | None, user_text: str) -> str:
    if identity:
        name, duty = identity["label"], f"我按「{identity['label']}」的职责行事。"
    elif agent_id in DEFAULT_ROLES:
        name = "Agent A·用户服务助手" if agent_id == "agent_a" else "Agent B·群聊管家"
        duty = DEFAULT_ROLES[agent_id].split("：", 1)[1]
    else:
        name, duty = agent_id, "我尚未绑定身份卡。"
    return f"[{name}·占位] 已收到：「{user_text}」。{duty}（可在「模型」面板接入真实 LLM）"


async def run_turn(agent_id: str, identity: dict | None, user_text: str,
                   bus_registry=None, room_id: str = "default"):
    """一个完整对话轮：产出文本片段；流中携带工具调用时执行工具并回灌，
    循环直至纯文本回复。

    产出协议：
      ("tool", {name, args, result})  —— 工具调用事件（前端可展示）
      ("text", piece)                 —— 文本片段
    LLM 未配置时降级为本地占位（逐片 yield），与第 2 步行为一致。
    """
    if not settings.llm_ready():
        for piece in _split(placeholder_text(agent_id, identity, user_text)):
            await asyncio.sleep(0.35)
            yield "text", piece
        return

    client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)
    tools = filter_tools(identity.get("tools_allow") if identity else None)
    system_prompt = build_system_prompt(agent_id, identity)
    # 第 5 步：检索注入——公共记忆 + 本 Agent 私有记忆 top-k（隔离红线在 hub 内强制）
    try:
        from app.memory.hub import format_memory_context, hub

        hits = await hub.search(room_id, agent_id, user_text, settings.memory_top_k)
        mem_note = format_memory_context(hits)
        if mem_note:
            system_prompt += "\n" + mem_note
    except Exception:
        pass  # 记忆库故障不阻断回复主链路
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    for _round in range(MAX_TOOL_ROUNDS):
        stream = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=tools or None,
            stream=True,
        )
        content_parts: list[str] = []
        tool_calls: dict[int, dict] = {}  # index -> {id, name, args_json}
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue
            if delta.content:
                content_parts.append(delta.content)
                yield "text", delta.content
            for tc in (delta.tool_calls or []):
                slot = tool_calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        slot["name"] += tc.function.name
                    if tc.function.arguments:
                        slot["args"] += tc.function.arguments

        text = "".join(content_parts)
        if not tool_calls:
            return  # 纯文本回复，本轮结束

        # 工具调用：执行 → 回灌 assistant(tool_calls) + tool 消息，继续下一轮
        assistant_msg = {"role": "assistant", "content": text or None}
        assistant_msg["tool_calls"] = [
            {
                "id": slot["id"] or f"call_{i}",
                "type": "function",
                "function": {"name": slot["name"], "arguments": slot["args"] or "{}"},
            }
            for i, slot in sorted(tool_calls.items())
        ]
        messages.append(assistant_msg)
        for i, slot in sorted(tool_calls.items()):
            name = slot["name"]
            try:
                args = json.loads(slot["args"] or "{}")
            except json.JSONDecodeError:
                args = {}
            # 防越权：即便模型幻觉出白名单外的工具，执行器侧仍复核
            allowed = {t["function"]["name"] for t in tools}
            if name not in allowed:
                result = json.dumps({"ok": False, "error": f"工具 {name} 不在你的白名单内"},
                                    ensure_ascii=False)
            else:
                result = await exec_fs_tool(room_id, agent_id, name, args, bus_registry)
            yield "tool", {"name": name, "args": args, "result": result}
            messages.append({
                "role": "tool",
                "tool_call_id": slot["id"] or f"call_{i}",
                "content": result,
            })

    yield "text", "\n（工具调用轮数已达上限，停止执行。已产出的内容如需落文件，请让用户重新发起。）"


def _split(text: str):
    for i in range(0, len(text), CHUNK_SIZE):
        yield text[i : i + CHUNK_SIZE]


async def respond_agent(bus, msg: Message, agent: dict):
    """单个 Agent 的回复协程：流式发布 chat 片段，异常转 system 消息。

    片段协议：同一 msg_id + stream_seq 递增，尾片 is_final=True。
    落库策略：只把首条消息存入事件流（payload 存最终全文），后续片段仅广播
    不落库——历史回放时读 full_text 即得完整原文，且消息表不再碎片化。
    工具调用事件（"tool"）仅广播展示，不进 chat 文本，也不落库。
    """
    aid = agent["id"]
    try:
        identity = load_identity(aid)
        reply_id = str(uuid.uuid4())
        got_llm = settings.llm_ready()
        pieces = []
        tool_notes = []
        async for kind, item in run_turn(aid, identity, msg.payload_text,
                                         bus_registry=bus.registry_ref,
                                         room_id=bus.room_id):
            if kind == "tool":
                # 工具事件：纯广播（前端在气泡下附一行小字，不落库不进全文）
                tool_notes.append(f"🔧 {item['name']}")
                ev = Message(
                    room_id=bus.room_id, type="chat", sender_kind="agent",
                    sender_id=aid, payload_text="",
                    stream_seq=len(pieces), is_final=False, msg_id=reply_id,
                )
                ev_dict = ev.to_dict()
                ev_dict["tool_event"] = {
                    "name": item["name"],
                    "result_ok": _result_ok(item["result"]),
                }
                await bus.broadcast_raw(json.dumps(ev_dict, ensure_ascii=False))
                continue
            piece = item
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
        final = Message(
            room_id=bus.room_id, type="chat", sender_kind="agent",
            sender_id=aid, payload_text="",
            stream_seq=len(pieces), is_final=True, msg_id=reply_id,
        )
        final_dict = final.to_dict()
        if tool_notes:
            final_dict["tool_summary"] = tool_notes
        await bus.broadcast_raw(json.dumps(final_dict, ensure_ascii=False))
        # 第 5.5 步：互聊轮次熔断已移除（不设上限；存储膨胀由 janitor 定时归档）
        from app.orchestrator.ceo import notify_agent_final

        await notify_agent_final(bus, aid, final_text)
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


def _result_ok(result_text: str) -> bool:
    try:
        return bool(json.loads(result_text).get("ok"))
    except Exception:
        return False


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
