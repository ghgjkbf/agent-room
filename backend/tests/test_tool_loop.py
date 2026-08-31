"""第 4 步 e2e：mock OpenAI 的 function-calling 工具循环 → fs.write → deliver 广播。

不起真实 LLM：monkeypatch AsyncOpenAI.chat.completions.create，第一轮返回
fs.write 工具调用，第二轮返回纯文本。验证：
1. 工具按 tools_allow 过滤（未授权工具不执行）
2. 工具循环正确回灌并产出最终文本
3. fs.write 落库 + 版本号正确
4. deliver 消息进事件流
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.agents.responder import run_turn
from app.core.config import settings
from app.core.db import db
from app.files import workspace

ROOM = "default"
PATH = "_e2e/deliverable.md"


class FakeChunk:
    """模拟 OpenAI 流式 chunk。"""

    def __init__(self, content=None, tool_calls=None):
        class _Delta:
            def __init__(self):
                self.content = content
                self.tool_calls = tool_calls

        class _Choice:
            def __init__(self):
                self.delta = _Delta()

        self.choices = [_Choice()]


def _fake_completions(round_no):
    """round 0 → fs.write 调用；round 1 → 纯文本。"""

    def _tc():
        class _Fn:
            name = "fs.write"
            arguments = json.dumps({"path": PATH, "content": "e2e 交付物"})

        class _TC:
            index = 0
            id = "call_e2e"
            function = _Fn()

        return [_TC()]

    async def _create(*a, **kw):
        if round_no[0] == 0:
            round_no[0] += 1
            return [FakeChunk(tool_calls=_tc()), FakeChunk()]
        return [FakeChunk(content="已写入 " + PATH), FakeChunk()]

    return _create


class FakeIter:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        async def _gen():
            for c in self._chunks:
                yield c
        return _gen()


@pytest.fixture(autouse=True)
def _llm_env(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "http://fake")
    monkeypatch.setattr(settings, "llm_api_key", "fake")
    monkeypatch.setattr(settings, "llm_model", "fake-model")
    yield
    try:
        workspace.delete_file(ROOM, PATH)
    except Exception:
        pass


def test_run_turn_tool_loop_and_deliver(monkeypatch):
    identity = {
        "id": "identity_e2e", "label": "执行员",
        "persona": "", "responsibilities": [],
        "tools_allow": ["fs.write"],  # 只授权 fs.write
    }
    round_no = [0]
    fake = _fake_completions(round_no)

    # 需要一个可迭代的异步流：直接让 create 返回可 async-iter 的对象
    async def _create(*a, **kw):
        return FakeIter(await fake(*a, **kw))

    from openai.resources.chat import AsyncCompletions
    monkeypatch.setattr(AsyncCompletions, "create", _create)

    events = []

    async def _run():
        async for kind, item in run_turn("agent_x", identity, "请把方案写入工作区"):
            events.append((kind, item))

    import asyncio
    asyncio.run(_run())

    kinds = [k for k, _ in events]
    assert kinds == ["tool", "text"]
    name, args, result = events[0][1]["name"], events[0][1]["args"], events[0][1]["result"]
    assert name == "fs.write"
    assert json.loads(result)["ok"] is True and json.loads(result)["version"] == 1
    text = "".join(item for k, item in events if k == "text")
    assert "已写入" in text

    # 文件已落工作区
    f = workspace.read_file(ROOM, PATH)
    assert f["content"] == "e2e 交付物" and f["version"] == 1


def test_tool_whitelist_blocked_in_run_turn(monkeypatch):
    """模型幻觉出核心权限工具（未勾选 shell.run）→ 不执行，结构化拒绝。"""
    identity = {
        "id": "identity_e2e2", "label": "受限员",
        "persona": "", "responsibilities": [],
        "tools_allow": [],  # v0.9.1：核心权限 shell.run 未勾选
    }

    async def _create(*a, **kw):
        class _Fn:
            name = "shell.run"
            arguments = json.dumps({"command": "echo blocked"})

        class _TC:
            index = 0
            id = "call_x"
            function = _Fn()

        return FakeIter([FakeChunk(tool_calls=[_TC()]), FakeChunk()])

    import openai
    from openai.resources.chat import AsyncCompletions
    monkeypatch.setattr(AsyncCompletions, "create", _create)

    events = []

    async def _run():
        async for kind, item in run_turn("agent_y", identity, "跑个命令"):
            events.append((kind, item))

    import asyncio
    asyncio.run(_run())
    tool_ev = next(ev for ev in events if ev[0] == "tool")
    result = json.loads(tool_ev[1]["result"])
    assert result["ok"] is False
    assert "白名单" in result["error"]
    # shell.run 不可能被真的执行（未勾选即拒绝）
    assert "blocked" not in result["error"]
