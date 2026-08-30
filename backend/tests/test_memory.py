"""第 5 步向量记忆单测：embedding 确定性 / 公私隔离 / 跨会话持久化。"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.memory.embeddings import DIM, cosine, embed_local
from app.memory.hub import MemoryHub, format_memory_context


def test_embed_local_deterministic_and_normalized():
    a = embed_local("调研竞品并输出对比报告")
    b = embed_local("调研竞品并输出对比报告")
    assert len(a) == DIM
    assert a == b  # 确定性
    assert abs(sum(x * x for x in a) - 1.0) < 1e-6  # L2 归一化


def test_embed_local_similarity_ordering():
    base = embed_local("调研竞品并输出对比报告")
    near = embed_local("调研竞品输出报告")
    far = embed_local("今天天气不错适合散步")
    assert cosine(base, near) > cosine(base, far)


def test_memory_isolation_and_persistence(tmp_path):
    async def _run():
        root = str(tmp_path / "mem")
        hub = MemoryHub(root)

        await hub.write_public("r1", "任务调研结论：竞品 A 定价更低",
                               {"id": "m1"}, "2026-08-29T10:00:00")
        await hub.write_private("agent_a", "agent_a 的私有笔记：接口规范 v2",
                                {"id": "m2"}, "2026-08-29T10:05:00")

        # agent_a：公共 + 自己私有
        hits_a = await hub.search("r1", "agent_a", "竞品调研结论")
        scopes_a = {h["scope"] for h in hits_a}
        assert "public" in scopes_a and "private" in scopes_a
        # agent_b：只有公共，永远读不到 agent_a 私有
        hits_b = await hub.search("r1", "agent_b", "接口规范")
        assert all(h["scope"] == "public" for h in hits_b)
        assert all("接口规范" not in h["text"] for h in hits_b)

        # 跨会话持久化：新实例读同一目录
        hub2 = MemoryHub(root)
        hits3 = await hub2.search("r1", "agent_a", "竞品定价")
        assert any("竞品" in h["text"] for h in hits3)

        stats = hub2.stats("r1")
        assert stats["public"] == 1 and stats["agents"].get("agent_a") == 1
        assert len(hub2.recent("r1")) == 2

    asyncio.run(_run())


def test_format_memory_context_tags_scope_and_time():
    lines = format_memory_context([
        {"scope": "public", "text": "结论X", "created_at": "2026-08-29T10:00:00", "score": 0.9},
        {"scope": "private", "text": "笔记Y", "created_at": "2026-08-29T11:00:00", "score": 0.8},
    ])
    assert "[公共·2026-08-29T10:" in lines and "[私有·2026-08-29T11:" in lines
    assert format_memory_context([]) == ""


def test_memory_delete_and_clear(tmp_path):
    """人类管理式删除：单条删除（公/私）与清空公共记忆。"""
    import asyncio

    async def _run():
        root = str(tmp_path / "mem")
        hub = MemoryHub(root)
        await hub.write_public("r9", "结论一", {"id": "m1"}, "2026-08-29T10:00:00")
        await hub.write_public("r9", "结论二", {"id": "m2"}, "2026-08-29T10:01:00")
        await hub.write_private("agent_a", "私有笔记", {"id": "p1"}, "2026-08-29T10:02:00")

        assert hub.delete_record("r9", None, "m1", private=False) is True
        assert hub.delete_record("r9", None, "m1", private=False) is False  # 幂等
        assert hub.delete_record("r9", "agent_a", "p1", private=True) is True
        stats = hub.stats("r9")
        assert stats["public"] == 1 and stats["agents"].get("agent_a", 0) == 0

        assert hub.clear("r9", None, private=False) == 1
        assert hub.stats("r9")["public"] == 0
        # 持久化确认：重开实例仍为空
        assert MemoryHub(root).stats("r9")["public"] == 0

    asyncio.run(_run())
