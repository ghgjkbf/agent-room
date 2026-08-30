"""第 5 步编排器单测 + mock 全链路 e2e。

覆盖：占位拆解 → 人类确认 → 按依赖派发 dispatch → 交付验收 receipt →
打回重试 → 重试上限熔断暂停 → 互聊条数熔断 → 占位验收全流程（含公共记忆沉淀）。
"""

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.core.config import settings
from app.core.db import db
from app.core.message import Message, now_cst
from app.memory.hub import MemoryHub
from app.orchestrator.ceo import Orchestrator, OrchestratorRegistry


class FakeBus:
    """只记录 publish 的消息；broadcast/registry 不参与。"""

    def __init__(self, room_id):
        self.room_id = room_id
        self.published = []
        self.listeners = []
        self.registry_ref = None

    async def publish(self, msg):
        self.published.append(msg)

    async def broadcast_raw(self, data):
        pass

    def by_type(self, t):
        return [m for m in self.published if m.type == t]


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "")
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_model", "")


@pytest.fixture
def room():
    """独立房间 id，避免污染 default；返回 (room, orch, bus)。"""
    rid = f"orch_{uuid.uuid4().hex[:6]}"
    orch = Orchestrator(rid)
    bus = FakeBus(rid)
    return rid, orch, bus


def _task_rows(rid):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE room_id=? ORDER BY created_at", (rid,)).fetchall()
    return [dict(r) for r in rows]


def _sub_rows(task_id):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM subtasks WHERE task_id=? ORDER BY seq", (task_id,)).fetchall()
    return [dict(r) for r in rows]


def test_placeholder_plan_and_confirm_dispatch(room):
    rid, orch, bus = room

    async def _run():
        await orch.create_task(bus, "调研竞品并输出对比报告")
        plans = bus.by_type("task_plan")
        assert len(plans) == 1 and plans[0].mentions == ["human"]
        task = _task_rows(rid)[-1]
        assert task["status"] == "awaiting_confirm"
        subs = _sub_rows(task["id"])
        assert [s["seq"] for s in subs] == [1, 2]
        assert subs[0]["assignee"] == "agent_a" and subs[1]["assignee"] == "agent_b"
        assert subs[1]["depends_on"] == "[1]"  # 依赖串联

        # 已有待确认任务时再下达 → 拒绝并提示
        await orch.create_task(bus, "第二个任务")
        assert any(m.type == "system" and "已有进行中的任务" in m.payload_text
                   for m in bus.published)

        # 确认开工 → 仅派发依赖满足的 #1
        r = await orch.confirm(task["id"], "confirm")
        assert r["ok"]
        await orch.dispatch_ready(bus, task["id"])
        disp = bus.by_type("dispatch")
        assert len(disp) == 1
        assert disp[0].mentions == ["agent_a"] and disp[0].priority == 1
        assert disp[0].parent_task_id == task["id"]
        assert _sub_rows(task["id"])[0]["status"] == "dispatched"
        assert _sub_rows(task["id"])[1]["status"] == "pending"  # #2 等依赖

    asyncio.run(_run())


def test_reject_retry_then_pause_for_human(room, monkeypatch):
    rid, orch, bus = room

    async def _run():
        await orch.create_task(bus, "做一件事")
        task = _task_rows(rid)[-1]
        await orch.confirm(task["id"], "confirm")
        await orch.dispatch_ready(bus, task["id"])
        sub = _sub_rows(task["id"])[0]

        async def _reject(goal, s, text, checks=None):
            return {"accept": False, "reason": "不合格"}

        monkeypatch.setattr(orch, "_verdict", _reject)
        for i in range(1, 4):  # 三次交付：2 次打回，第 3 次超上限熔断
            n_before = len(bus.by_type("receipt"))
            s_now = [s for s in _sub_rows(task["id"]) if s["id"] == sub["id"]][0]
            await orch._accept(bus, s_now, f"交付 v{i}")
            receipts = bus.by_type("receipt")[n_before:]
            if i <= settings.subtask_max_retries:
                assert receipts and receipts[0].payload_text.startswith("验收打回")
            else:
                sysm = [m for m in bus.published if m.type == "system"
                        and "已暂停并 @人类" in m.payload_text]
                assert sysm and sysm[-1].mentions == ["human"]
                assert _task_rows(rid)[-1]["status"] == "paused"
                return
        pytest.fail("重试上限未触发熔断")

    asyncio.run(_run())


def test_chat_flood_breaker(room, monkeypatch):
    rid, orch, bus = room
    monkeypatch.setattr(settings, "task_max_chat_turns", 2)

    async def _run():
        await orch.create_task(bus, "目标 X")
        task = _task_rows(rid)[-1]
        await orch.confirm(task["id"], "confirm")
        await orch.dispatch_ready(bus, task["id"])

        # 非当前执行者（agent_b）的互聊 → 计入任务级熔断
        await orch.notify_agent_final(bus, "agent_b", "闲聊一句")
        assert _task_rows(rid)[-1]["status"] == "running"
        await orch.notify_agent_final(bus, "agent_b", "再聊一句")
        assert _task_rows(rid)[-1]["status"] == "paused"
        sysm = [m for m in bus.published if m.type == "system" and "熔断" in m.payload_text]
        assert sysm and sysm[-1].mentions == ["human"]

        # 恢复后继续跑
        r = await orch.confirm(task["id"], "resume")
        assert r["ok"] and _task_rows(rid)[-1]["status"] == "running"

    asyncio.run(_run())


def test_abort(room):
    rid, orch, bus = room

    async def _run():
        await orch.create_task(bus, "目标 Y")
        task = _task_rows(rid)[-1]
        assert (await orch.abort(task["id"]))["ok"]
        assert _task_rows(rid)[-1]["status"] == "aborted"
        assert not (await orch.abort(task["id"]))["ok"]  # 幂等拒绝
        # 作废后可再次下达
        await orch.create_task(bus, "目标 Z")
        assert len(_task_rows(rid)) == 2

    asyncio.run(_run())


def test_full_loop_with_placeholder_acceptance(room, monkeypatch):
    """mock 全链路 e2e：确认 → #1 派发 → 执行者交付说明 → 验收 → #2 → 汇总。"""
    rid, orch, bus = room
    mem = MemoryHub(str(uuid.uuid4().hex))  # root 不存在也不读写（patch 后用 tmp）
    import tempfile

    mem = MemoryHub(tempfile.mkdtemp())
    monkeypatch.setattr("app.orchestrator.ceo.hub", mem)

    async def _run():
        await orch.create_task(bus, "产出双 Agent 协作交付物")
        task = _task_rows(rid)[-1]
        await orch.confirm(task["id"], "confirm")
        await orch.dispatch_ready(bus, task["id"])
        assert len(bus.by_type("dispatch")) == 1  # 只有 #1

        # 执行者 agent_a 回复（真实路径同 respond_agent 收尾钩子）
        await orch.notify_agent_final(bus, "agent_a", "调研完成，方案已写入 docs/plan_x.md")
        subs = _sub_rows(task["id"])
        assert subs[0]["status"] == "accepted"
        assert len(bus.by_type("receipt")) == 1
        # #2 依赖满足被自动派发
        disp2 = bus.by_type("dispatch")
        assert len(disp2) == 2 and disp2[1].mentions == ["agent_b"]

        await orch.notify_agent_final(bus, "agent_b", "执行完成，结果已写入 docs/result_x.md")
        assert _task_rows(rid)[-1]["status"] == "done"
        summary = [m for m in bus.published if m.type == "system" and "全部完成" in m.payload_text]
        assert summary and summary[-1].mentions == ["human"]

        # 公共记忆沉淀（验收通过才写入），且 agent_b 私有不可见于 agent_a
        stats = mem.stats(rid)
        assert stats["public"] == 2
        hits_a = await mem.search(rid, "agent_a", "执行结果")
        assert all("执行完成" not in h["text"] or h["scope"] == "public" for h in hits_a)

        # 幂等：任务结束后重复交付说明不再触发任何动作
        n = len(bus.published)
        await orch.notify_agent_final(bus, "agent_a", "再补一句")
        assert len(bus.published) == n

    asyncio.run(_run())


def test_registry_singleton():
    assert OrchestratorRegistry.get("default") is OrchestratorRegistry.get("default")


def test_task_cleanup_endpoints():
    """已结束任务可删/可清空；未结束的拒绝。"""
    from app.orchestrator import routes as tr

    rid = f"tc_{uuid.uuid4().hex[:6]}"
    ids = {}
    with db() as conn:
        for i, st in enumerate(("done", "aborted", "running")):
            tid = f"task_tc{i}_{uuid.uuid4().hex[:4]}"
            ids[st] = tid
            ts = now_cst()
            conn.execute(
                "INSERT INTO tasks (id, room_id, goal, status, plan_json, created_at,"
                " updated_at) VALUES (?,?,?,?,?,?,?)",
                (tid, rid, f"目标{i}", st, "[]", ts, ts))
            conn.execute(
                "INSERT INTO subtasks (id, task_id, room_id, seq, title, assignee,"
                " depends_on, created_at) VALUES (?,?,?,1,'t','agent_a','[]',?)",
                (tid + "_s1", tid, rid, ts))

    async def _run():
        # running 拒绝删除
        r = await tr.delete_task(ids["running"])
        assert not r["ok"] and "未结束" in r["detail"]
        # done 可删（连子任务）
        assert (await tr.delete_task(ids["done"]))["ok"]
        # 清空剩余已结束（aborted）
        r = await tr.clear_finished_tasks(tr.ClearIn(room_id=rid))
        assert r["ok"] and r["cleared"] == 1
        # running 仍在
        r = await tr.list_tasks(room_id=rid)
        assert len(r["tasks"]) == 1 and r["tasks"][0]["status"] == "running"

    try:
        asyncio.run(_run())
    finally:
        with db() as conn:
            conn.execute("DELETE FROM subtasks WHERE room_id=?", (rid,))
            conn.execute("DELETE FROM tasks WHERE room_id=?", (rid,))
