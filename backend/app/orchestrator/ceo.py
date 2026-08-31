"""CEO 编排器（第 5 步，设计文档 s6 职位化编排）。

黄金法则：编排者永不执行，执行者永不编排。L1 CEO 只做：
拆目标（任务分解图）→ 人类确认 → dispatch 排产单按依赖派发 →
收 deliver/交付说明后验收 receipt（不合格打回）→ 全部完成汇总 @人类。

- 触发：人类 WS 消息 type=task 下达目标；确认/恢复/终止走 HTTP /api/tasks。
- 接线：挂为 RoomBus 监听器（bus.listeners），一切经 bus.publish 落库的
  消息都会流经 on_message（内部 WS / 网关 / deliver 统一覆盖）；
  内置执行者的最终回复另经 respond_agent 收尾钩子 notify_agent_final 进入。
- 熔断：已移除（互聊与打回重做均不设上限，任务只走
  拆解 → 确认 → 派发 → 验收 → 汇总 的完整闭环，直至验收通过）。
- LLM 未配置时占位路径：固定双子任务模板 + 占位验收默认通过，全流程可测。
- 向量记忆：验收通过沉淀公共记忆；收到 deliver 写发送者私有记忆。
"""

import asyncio
import json
import re
import uuid

from app.core.config import settings
from app.core.db import db
from app.core.message import Message, now_cst
from app.memory.hub import hub

# 编排器自己发布的消息不再回流处理（防递归）
_IGNORED = {"task_plan", "dispatch", "receipt", "system", "interrupt"}
_SUB_ST = {"pending": "待派发", "dispatched": "执行中", "accepted": "已验收",
           "rejected": "已打回"}
_TASK_ST = {"awaiting_confirm": "待确认", "running": "执行中",
            "paused": "已熔断·待人类裁决", "done": "已完成", "aborted": "已作废"}


# 交付文本中「声称写过的文件路径」：至少带一层目录或常见扩展名，避免误伤版本号等
_CLAIM_RE = re.compile(
    r"[\w\-一-鿿]+(?:/[\w\-.一-鿿]+)*\.(?:md|markdown|txt|json|csv|log|yaml|yml|py|js|ts|html|css)\b",
    re.IGNORECASE)


def extract_claimed_paths(text: str) -> list[str]:
    seen, out = set(), []
    for m in _CLAIM_RE.finditer(text or ""):
        p = m.group(0).rstrip(".,;、）)】\"'`，。")
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


class Orchestrator:
    def __init__(self, room_id: str):
        self.room_id = room_id

    def _verify_claims(self, delivery_text: str) -> list[str]:
        """核对交付文本声称的文件是否真的在工作区（防「声称交付」骗过验收）。"""
        from app.files import workspace

        checks = []
        for p in extract_claimed_paths(delivery_text):
            try:
                f = workspace.read_file(self.room_id, p)
                checks.append(f"✓ {f['path']}（v{f['version']}，{len(f['content'])} 字符）")
            except Exception:
                checks.append(f"✗ {p} 未在工作区找到")
        return checks

    # ---------- 消息入口 ----------

    async def on_message(self, bus, msg: Message):
        if msg.type in _IGNORED:
            return
        if msg.type == "task" and msg.sender_kind == "human":
            await self.create_task(bus, msg.payload_text)
            return
        if msg.type == "deliver" and msg.sender_kind == "agent":
            # 私有记忆沉淀（Agent 交付时可写私有笔记；闲聊不入库）
            try:
                await hub.write_private(
                    msg.sender_id, f"交付记录：{msg.payload_text}",
                    {"room_id": self.room_id, "msg_id": msg.msg_id}, now_cst())
            except Exception:
                pass
            sub = self._open_subtask_of(msg.sender_id)
            if sub:
                await self._accept(bus, sub, msg.payload_text)
            return
        # 其余（人类 chat / 无任务时的 agent chat）与编排无关，忽略

    async def notify_agent_final(self, bus, agent_id: str, text: str):
        """respond_agent 收尾钩子：执行者交付说明 → 验收。互聊不熔断（无上限）。"""
        task = self._active_task()
        if not task:
            return
        sub = self._open_subtask_of(agent_id)
        if sub:
            await self._accept(bus, sub, text)

    # ---------- 任务生命周期 ----------

    async def create_task(self, bus, goal: str):
        goal = (goal or "").strip()
        if not goal:
            return
        if self._active_task():
            await bus.publish(Message(
                room_id=self.room_id, type="system", sender_kind="system",
                sender_id="ceo",
                payload_text="已有进行中的任务（待确认/执行中/已熔断），请先完成或在任务面板作废后再下达。"))
            return
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        executors = self._executors()
        plan = await self._plan(goal, task_id, executors)
        ts = now_cst()
        with db() as conn:
            conn.execute(
                "INSERT INTO tasks (id, room_id, goal, status, plan_json, created_at,"
                " updated_at) VALUES (?,?,?,?,?,?,?)",
                (task_id, self.room_id, goal, "awaiting_confirm",
                 json.dumps(plan, ensure_ascii=False), ts, ts))
            for st in plan:
                conn.execute(
                    "INSERT INTO subtasks (id, task_id, room_id, seq, title, guidance,"
                    " assignee, depends_on, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (f"{task_id}_s{st['seq']}", task_id, self.room_id, st["seq"],
                     st["title"], st.get("guidance", ""), st["assignee"],
                     json.dumps(st.get("depends_on", [])), ts))
        lines = [f"任务分解图（{len(plan)} 个子任务，确认后按依赖派发）："]
        for st in plan:
            dep = "、".join(f"{d}" for d in st.get("depends_on", []))
            lines.append(f"#{st['seq']} {st['title']} → {st['assignee']}"
                         + (f"（依赖 #{dep}）" if dep else ""))
        await bus.publish(Message(
            room_id=self.room_id, type="task_plan", sender_kind="orchestrator",
            sender_id="ceo", parent_task_id=task_id,
            payload_text="\n".join(lines), mentions=["human"]))

    async def confirm(self, task_id: str, action: str = "confirm") -> dict:
        """人类确认开工 / 熔断后恢复。"""
        with db() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row or row["room_id"] != self.room_id:
                return {"ok": False, "detail": "任务不存在"}
            if action == "resume" and row["status"] != "paused":
                return {"ok": False, "detail": "任务不在熔断暂停状态"}
            if action == "confirm" and row["status"] != "awaiting_confirm":
                return {"ok": False, "detail": "任务不在待确认状态"}
            conn.execute("UPDATE tasks SET status='running', updated_at=? WHERE id=?",
                         (now_cst(), task_id))
        return {"ok": True}

    async def abort(self, task_id: str) -> dict:
        with db() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row or row["room_id"] != self.room_id:
                return {"ok": False, "detail": "任务不存在"}
            if row["status"] in ("done", "aborted"):
                return {"ok": False, "detail": "任务已结束"}
            conn.execute("UPDATE tasks SET status='aborted', updated_at=? WHERE id=?",
                         (now_cst(), task_id))
        return {"ok": True}

    async def dispatch_ready(self, bus, task_id: str):
        """派发所有依赖已满足的 pending 子任务（确认/上一环验收后调用）。"""
        from app.agents.responder import GenerationRegistry, respond_agent

        for sub in self._subtasks(task_id):
            if sub["status"] != "pending" or not self._deps_met(sub):
                continue
            task = self._task(task_id)
            with db() as conn:
                conn.execute("UPDATE subtasks SET status='dispatched' WHERE id=?",
                             (sub["id"],))
                conn.execute("UPDATE tasks SET updated_at=? WHERE id=?",
                             (now_cst(), task_id))
            m = Message(
                room_id=self.room_id, type="dispatch", priority=1,
                sender_kind="orchestrator", sender_id="ceo",
                parent_task_id=task_id, mentions=[sub["assignee"]],
                payload_text=(f"【排产单 #{sub['seq']}】{sub['title']}\n"
                              f"目标：{task['goal']}\n要求：{sub['guidance'] or '按身份卡职责完成'}\n"
                              f"完成后交付文件（fs.write），并在群里简述结果。"))
            await bus.publish(m)
            t = asyncio.create_task(respond_agent(bus, m, {"id": sub["assignee"]}))
            GenerationRegistry.register(sub["assignee"], t)

    # ---------- 验收 ----------

    async def _accept(self, bus, sub: dict, delivery_text: str):
        if sub["status"] != "dispatched":
            return  # 幂等：打回等待重做/已验收时忽略重复触发
        task = self._task(sub["task_id"])
        checks = self._verify_claims(delivery_text)
        verdict = await self._verdict(task["goal"], sub, delivery_text, checks)
        # 硬核验：真实 LLM 模式下，声称写了文件而工作区一个都没有 → 无视验收员直接打回
        if settings.llm_ready() and checks and all(c.startswith("✗") for c in checks):
            verdict = {"accept": False,
                       "reason": "声称的交付文件经核验均不存在（" + "；".join(checks) + "）"}
        if verdict["accept"]:
            with db() as conn:
                conn.execute(
                    "UPDATE subtasks SET status='accepted', delivery_text=?,"
                    " last_receipt=?, accepted_at=? WHERE id=?",
                    (delivery_text, verdict["reason"], now_cst(), sub["id"]))
            await bus.publish(Message(
                room_id=self.room_id, type="receipt", sender_kind="orchestrator",
                sender_id="ceo", parent_task_id=sub["task_id"],
                payload_text=f"验收通过：#{sub['seq']} {sub['title']}（{verdict['reason']}）"))
            try:  # 结论沉淀公共记忆（验收通过才写入，防错误结论污染）
                await hub.write_public(
                    self.room_id,
                    f"任务「{task['goal']}」子任务「{sub['title']}」已验收：{delivery_text[:200]}",
                    {"id": sub["id"], "task_id": sub["task_id"]}, now_cst())
            except Exception:
                pass
            remaining = [s for s in self._subtasks(sub["task_id"])
                         if s["status"] != "accepted"]
            if remaining:
                await self.dispatch_ready(bus, sub["task_id"])
            else:
                await self._finalize(bus, sub["task_id"])
        else:
            # 打回重做不设熔断上限：反复打回直至验收通过
            with db() as conn:
                conn.execute("UPDATE subtasks SET status='rejected', retries=?,"
                             " delivery_text=?, last_receipt=? WHERE id=?",
                             (sub["retries"] + 1, delivery_text, verdict["reason"], sub["id"]))
            await bus.publish(Message(
                room_id=self.room_id, type="receipt", sender_kind="orchestrator",
                sender_id="ceo", parent_task_id=sub["task_id"],
                payload_text=(f"验收打回：#{sub['seq']} {sub['title']}——{verdict['reason']}"
                              f"（第 {sub['retries'] + 1} 次，重做中）")))
            with db() as conn:
                conn.execute("UPDATE subtasks SET status='dispatched' WHERE id=?",
                             (sub["id"],))
            m = Message(
                room_id=self.room_id, type="dispatch", priority=1,
                sender_kind="orchestrator", sender_id="ceo",
                parent_task_id=sub["task_id"], mentions=[sub["assignee"]],
                payload_text=(f"【打回重做 #{sub['seq']}】{sub['title']}\n"
                              f"打回原因：{verdict['reason']}\n原要求：{sub['guidance'] or '按身份卡职责完成'}"))
            await bus.publish(m)
            from app.agents.responder import GenerationRegistry, respond_agent
            t = asyncio.create_task(respond_agent(bus, m, {"id": sub["assignee"]}))
            GenerationRegistry.register(sub["assignee"], t)

    async def _finalize(self, bus, task_id: str):
        task = self._task(task_id)
        subs = self._subtasks(task_id)
        lines = [f"任务「{task['goal']}」全部完成（{len(subs)} 个子任务）："]
        for s in subs:
            lines.append(f"✓ #{s['seq']} {s['title']} → {s['assignee']}")
        lines.append("以上结果已沉淀到房间公共记忆，请查收。")
        with db() as conn:
            conn.execute("UPDATE tasks SET status='done', summary=?, updated_at=?"
                         " WHERE id=?", ("\n".join(lines), now_cst(), task_id))
        await bus.publish(Message(
            room_id=self.room_id, type="system", sender_kind="orchestrator",
            sender_id="ceo", parent_task_id=task_id,
            payload_text="\n".join(lines), mentions=["human"]))

    async def _pause_for_human(self, bus, task_id: str, reason: str):
        with db() as conn:
            conn.execute("UPDATE tasks SET status='paused', updated_at=? WHERE id=?",
                         (now_cst(), task_id))
        await bus.publish(Message(
            room_id=self.room_id, type="system", priority=2,
            sender_kind="orchestrator", sender_id="ceo", parent_task_id=task_id,
            payload_text=reason, mentions=["human"]))

    # ---------- LLM / 占位 ----------

    @staticmethod
    def _clean(s):
        """LLM JSON 里常出现字面 \\n（双反斜杠转义），规范成真实换行。"""
        return s.replace("\\n", "\n") if isinstance(s, str) else s

    async def _plan(self, goal: str, task_id: str, executors: list[str]) -> list[dict]:
        data = await self._llm_json(
            "你是 CEO 总编排器：把目标拆解为子任务排产单。只输出 JSON（不要多余字段）："
            '{"subtasks":[{"seq":1,"title":"...","assignee":"agent_a",'
            '"depends_on":[],"guidance":"给执行者的具体要求"}]}。'
            f"执行者只能是 {executors}；编排者不执行；子任务不超过 3 个；"
            "title 不超过 12 个字；guidance 必须写明交付文件的具体路径（如 docs/xxx.md）"
            "与可核验的完成标准，禁止空泛表述。")
        subs = (data or {}).get("subtasks") or []
        ok = isinstance(subs, list) and subs and all(
            isinstance(s, dict) and s.get("title") and s.get("assignee") in executors
            for s in subs)
        if ok:
            for s in subs[:3]:
                s["title"] = self._clean(s.get("title", ""))
                s["guidance"] = self._clean(s.get("guidance", ""))
            return subs[:3]
        return _placeholder_plan(goal, task_id, executors)

    async def _verdict(self, goal: str, sub: dict, delivery_text: str,
                       checks: list[str] | None = None) -> dict:
        user = (f"总目标：{goal}\n子任务：#{sub['seq']} {sub['title']}\n"
                f"要求：{sub['guidance']}\n交付内容：{delivery_text[:800]}\n"
                "判定要点：声称写了文件但系统核验为缺失 = 未交付；复述排产单原文不算交付内容。")
        if checks:
            user += "\n系统文件核验结果（声称写了文件时以此为准）：\n" + "\n".join(checks)
        data = await self._llm_json(
            "你是编排层验收员。判断交付是否满足子任务要求，只输出 JSON："
            '{"accept":true/false,"reason":"一句话原因"}。', user)
        if data and isinstance(data.get("accept"), bool):
            return {"accept": data["accept"],
                    "reason": self._clean(data.get("reason", ""))}
        return {"accept": True, "reason": "占位验收：LLM 未配置或输出异常，默认通过"}

    async def _llm_json(self, system: str, user: str = "") -> dict | None:
        if not settings.llm_ready():
            return None
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(base_url=settings.llm_base_url,
                                 api_key=settings.llm_api_key)
            r = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[{"role": "system", "content": system}] + (
                    [{"role": "user", "content": user}] if user else []),
                temperature=0.2)
            content = (r.choices[0].message.content or "").strip()
            for fence in ("```json", "```"):
                if content.startswith(fence):
                    content = content[len(fence):]
            if content.endswith("```"):
                content = content[:-3]
            return json.loads(content.strip())
        except Exception:
            return None

    # ---------- 查询辅助 ----------

    def _task(self, task_id: str) -> dict:
        with db() as conn:
            return dict(conn.execute("SELECT * FROM tasks WHERE id=?",
                                     (task_id,)).fetchone())

    def _active_task(self) -> dict | None:
        with db() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE room_id=? AND status IN"
                " ('awaiting_confirm','running','paused') ORDER BY created_at DESC",
                (self.room_id,)).fetchone()
        return dict(row) if row else None

    def _subtasks(self, task_id: str) -> list[dict]:
        with db() as conn:
            rows = conn.execute(
                "SELECT * FROM subtasks WHERE task_id=? ORDER BY seq",
                (task_id,)).fetchall()
        return [dict(r) for r in rows]

    def _open_subtask_of(self, agent_id: str) -> dict | None:
        """该 Agent 当前被派发未验收的子任务（每 Agent 同时只认一张排产单）。"""
        task = self._active_task()
        if not task:
            return None
        for sub in self._subtasks(task["id"]):
            if sub["assignee"] == agent_id and sub["status"] == "dispatched":
                return sub
        return None

    def _deps_met(self, sub: dict) -> bool:
        done = {s["seq"] for s in self._subtasks(sub["task_id"])
                if s["status"] == "accepted"}
        return all(d in done for d in json.loads(sub["depends_on"] or "[]"))

    def _executors(self) -> list[str]:
        with db() as conn:
            rows = conn.execute(
                "SELECT a.id FROM room_members m JOIN agents a ON a.id = m.agent_id"
                " WHERE m.room_id=? AND (a.kind='internal' OR a.kind IS NULL)"
                " ORDER BY a.id", (self.room_id,)).fetchall()
        return [r["id"] for r in rows] or ["agent_a", "agent_b"]


def _placeholder_plan(goal: str, task_id: str, executors: list[str]) -> list[dict]:
    """LLM 未配置时的固定双子任务模板（调研 → 执行，依赖串联，全流程可测）。"""
    a = executors[0] if executors else "agent_a"
    b = executors[1] if len(executors) > 1 else a
    tag = task_id.split("_")[-1]
    return [
        {"seq": 1, "title": "调研与方案", "assignee": a, "depends_on": [],
         "guidance": f"围绕目标「{goal}」完成调研分析，把方案要点写入交付文件"
                     f"（建议 docs/plan_{tag}.md），并在群里简述结论。"},
        {"seq": 2, "title": "执行与交付", "assignee": b, "depends_on": [1],
         "guidance": f"基于上一环节产出继续完成「{goal}」的执行部分，把最终结果写入"
                     f"交付文件（建议 docs/result_{tag}.md），并在群里简述结果。"},
    ]


class OrchestratorRegistry:
    _insts: dict[str, Orchestrator] = {}

    @classmethod
    def get(cls, room_id: str) -> Orchestrator:
        if room_id not in cls._insts:
            cls._insts[room_id] = Orchestrator(room_id)
        return cls._insts[room_id]


async def notify_agent_final(bus, agent_id: str, text: str):
    """respond_agent 收尾统一入口（异常不外泄，绝不影响回复主链路）。"""
    try:
        await OrchestratorRegistry.get(bus.room_id).notify_agent_final(bus, agent_id, text)
    except Exception:
        pass
