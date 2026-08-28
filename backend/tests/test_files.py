"""第 4 步文件工作区单测：路径逃逸、乐观锁冲突、权限过滤、deliver 通知。

照第 3 步测试风格：真实 DB + 纯函数调用，不起 HTTP 服务。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import HTTPException

from app.core.db import db, init_db
from app.files import workspace
from app.files.tools import FS_TOOLS, exec_fs_tool, filter_tools

init_db()
ROOM = "default"


# ---------- 路径规范化（防逃逸） ----------

@pytest.mark.parametrize("bad", [
    "../escape.md", "a/../../b.md", "..", "/abs/path.md", "C:/win.md",
    "C:\\win.md", "a\\b.md", "a//b.md", "a/../b.md", "./x.md",
])
def test_normalize_path_rejects_escape(bad):
    with pytest.raises(HTTPException) as ei:
        workspace.normalize_path(bad)
    assert ei.value.status_code == 400


@pytest.mark.parametrize("good", ["a.md", "docs/方案.md", "docs/deep/note.txt"])
def test_normalize_path_accepts_nested(good):
    assert workspace.normalize_path(good) == good


# ---------- 乐观锁 ----------

def test_write_and_optimistic_lock():
    path = "_test_lock/plan.md"
    try:
        # 新建（无 base_version）→ v1
        r1 = workspace.write_file(ROOM, path, "第一版", author="agent_test")
        assert r1["version"] == 1
        # 新建但已存在 → 409 + latest_version
        with pytest.raises(HTTPException) as ei:
            workspace.write_file(ROOM, path, "重复新建", author="agent_test")
        assert ei.value.status_code == 409
        assert ei.value.detail["latest_version"] == 1
        # 用旧 base_version=1 覆盖 → v2
        r2 = workspace.write_file(ROOM, path, "第二版", author="agent_test", base_version=1)
        assert r2["version"] == 2
        # 并发复现：另一 Agent 仍拿 base_version=1（旧读）写 → 409，返回 latest=2
        with pytest.raises(HTTPException) as ei2:
            workspace.write_file(ROOM, path, "并发写", author="agent_other", base_version=1)
        d = ei2.value.detail
        assert ei2.value.status_code == 409 and d["latest_version"] == 2
        # 凭 latest_version 重写成功
        r3 = workspace.write_file(ROOM, path, "重读后的写", author="agent_other",
                                  base_version=d["latest_version"])
        assert r3["version"] == 3
        # 人类直写不校验 base_version（先清掉 Agent 留下的版本，模拟全新直写）
        workspace.delete_file(ROOM, path)
        r4 = workspace.write_file(ROOM, path, "人类直写", author="human")
        assert r4["version"] == 1
        content = workspace.read_file(ROOM, path)
        assert content["content"] == "人类直写" and content["version"] == 1
    finally:
        try:
            workspace.delete_file(ROOM, path)
        except Exception:
            pass


def test_read_delete_not_found():
    with pytest.raises(HTTPException) as ei:
        workspace.read_file(ROOM, "_no_such/file.md")
    assert ei.value.status_code == 404
    with pytest.raises(HTTPException) as ei2:
        workspace.delete_file(ROOM, "_no_such/file.md")
    assert ei2.value.status_code == 404


# ---------- 工具白名单过滤 ----------

def test_filter_tools_strict():
    assert filter_tools(["fs.read", "fs.write"]) == [
        t for t in FS_TOOLS if t["function"]["name"] in ("fs.read", "fs.write")]
    assert filter_tools([]) == []
    assert filter_tools(None) == []
    # 白名单外的名字拿不到定义
    assert filter_tools(["shell.run"]) == []


def test_exec_fs_tool_and_whitelist_enforcement():
    """执行器基本链路 + 越权复核在 responder 侧（此处测执行器本身）。"""
    path = "_test_exec/note.md"

    async def _run():
        # 无白名单概念在执行器层（过滤在 filter_tools/responder），直接执行
        r_list = json.loads(await exec_fs_tool(ROOM, "agent_x", "fs.list", {}))
        assert r_list["ok"] is True
        r_write = json.loads(await exec_fs_tool(
            ROOM, "agent_x", "fs.write", {"path": path, "content": "内容"}))
        assert r_write["ok"] and r_write["version"] == 1
        r_read = json.loads(await exec_fs_tool(ROOM, "agent_x", "fs.read", {"path": path}))
        assert r_read["ok"] and r_read["content"] == "内容"
        # 覆盖需 base_version
        r_conflict = json.loads(await exec_fs_tool(
            ROOM, "agent_x", "fs.write", {"path": path, "content": "x"}))
        assert r_conflict["ok"] is False and r_conflict["latest_version"] == 1
        r_ok = json.loads(await exec_fs_tool(
            ROOM, "agent_x", "fs.write",
            {"path": path, "content": "v2内容", "base_version": 1}))
        assert r_ok["ok"] and r_ok["version"] == 2
        # 未知工具 / 非法路径
        r_bad = json.loads(await exec_fs_tool(ROOM, "agent_x", "fs.rm", {}))
        assert r_bad["ok"] is False
        r_esc = json.loads(await exec_fs_tool(
            ROOM, "agent_x", "fs.write", {"path": "../evil.md", "content": "x"}))
        assert r_esc["ok"] is False
        return r_ok

    try:
        r = __import__("asyncio").run(_run())
        assert r["version"] == 2
    finally:
        try:
            workspace.delete_file(ROOM, path)
        except Exception:
            pass


def test_deliver_published_on_write():
    """fs.write 成功 → bus.publish 一条 type=deliver 消息。"""
    path = "_test_deliver/out.md"

    class FakeBus:
        def __init__(self):
            self.published = []

        async def publish(self, msg):
            self.published.append(msg)

    class FakeRegistry:
        def __init__(self, bus):
            self._bus = bus

        def get(self, room_id):
            return self._bus

    async def _run():
        bus = FakeBus()
        await exec_fs_tool(ROOM, "agent_d", "fs.write",
                           {"path": path, "content": "交付物"},
                           bus_registry=FakeRegistry(bus))
        return bus

    try:
        bus = __import__("asyncio").run(_run())
        assert len(bus.published) == 1
        m = bus.published[0]
        assert m.type == "deliver" and m.sender_id == "agent_d"
        assert "_test_deliver/out.md" in m.payload_text
    finally:
        try:
            workspace.delete_file(ROOM, path)
        except Exception:
            pass
