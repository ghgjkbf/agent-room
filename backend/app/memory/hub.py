"""向量记忆库（第 5 步，设计文档 s9）。

- 物理隔离：collection `room_{id}_public`（房间级公共记忆）与
  `agent_{id}_private`（Agent 私有记忆）分文件存储。
- 鉴权红线：检索接口强制带 (room_id, agent_id)——公共记忆全员可查，
  私有记忆仅本人可见，任何 Agent 读不到他者私有记忆。
- 后端：MVP 用内置 JSON 向量库（暴力余弦，规模小够用；Python 3.14 暂无
  chromadb 兼容轮子）。接口与 Chroma 同形，后续换装只动本文件。
- 写入时机：任务验收通过沉淀结论到公共记忆；Agent 交付时写私有笔记；
  闲聊不入库（调用方保证）。
"""

import json
import os
import threading

from app.core.config import BASE_DIR
from app.memory.embeddings import cosine, embed_text, loads_meta

MEM_ROOT = os.path.join(BASE_DIR, "data", "memory")


def public_collection(room_id: str) -> str:
    return f"room_{room_id}_public"


def private_collection(agent_id: str) -> str:
    return f"agent_{agent_id}_private"


class Collection:
    """单 collection：JSON 落盘（records: id/text/vector/meta/created_at）。"""

    def __init__(self, name: str, root: str = MEM_ROOT):
        self.name = name
        self.path = os.path.join(root, f"{name}.json")
        self.lock = threading.Lock()
        self.records: list[dict] = []
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    self.records = json.load(f)
            except Exception:
                self.records = []

    def add(self, rid: str, text: str, vector: list[float], meta: dict, created_at: str):
        with self.lock:
            self.records.append(
                {"id": rid, "text": text, "vector": vector,
                 "meta": meta, "created_at": created_at}
            )
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.records, f, ensure_ascii=False)

    def search(self, vector: list[float], k: int) -> list[dict]:
        with self.lock:
            scored = [
                (cosine(vector, r["vector"]), r) for r in self.records
            ]
        scored.sort(key=lambda x: -x[0])
        return [{"score": round(s, 4), **{kk: r[kk] for kk in ("id", "text", "meta", "created_at")}}
                for s, r in scored[:k]]


class MemoryHub:
    """记忆门面：写入与检索都经此，隔离红线在 search 里强制执行。"""

    def __init__(self, root: str = MEM_ROOT):
        self.root = root
        self._cols: dict[str, Collection] = {}
        self._lock = threading.Lock()

    def _col(self, name: str) -> Collection:
        with self._lock:
            if name not in self._cols:
                self._cols[name] = Collection(name, self.root)
            return self._cols[name]

    async def write_public(self, room_id: str, text: str, meta: dict, created_at: str):
        col = self._col(public_collection(room_id))
        v = await embed_text(text)
        col.add(meta.get("id") or f"pub_{created_at}", text, v, meta, created_at)

    async def write_private(self, agent_id: str, text: str, meta: dict, created_at: str):
        col = self._col(private_collection(agent_id))
        v = await embed_text(text)
        col.add(meta.get("id") or f"pri_{created_at}", text, v, meta, created_at)

    async def search(self, room_id: str, agent_id: str, query: str, k: int = 3) -> list[dict]:
        """公共记忆 + 本 Agent 私有记忆合并检索（他人私有永不进入候选）。"""
        v = await embed_text(query)
        hits = self._col(public_collection(room_id)).search(v, k)
        for h in hits:
            h["scope"] = "public"
        mine = self._col(private_collection(agent_id)).search(v, k)
        for h in mine:
            h["scope"] = "private"
        hits.extend(mine)
        hits.sort(key=lambda x: -x["score"])
        return hits[:k]

    def stats(self, room_id: str) -> dict:
        pub = self._col(public_collection(room_id)).records
        agents: dict[str, int] = {}
        for name in os.listdir(self.root) if os.path.isdir(self.root) else []:
            if name.startswith("agent_") and name.endswith("_private.json"):
                aid = name[len("agent_"):-len("_private.json")]
                agents[aid] = len(self._col(private_collection(aid)).records)
        return {"public": len(pub), "agents": agents}

    def recent(self, room_id: str, n: int = 10) -> list[dict]:
        items = [{"scope": "public", **{kk: r[kk] for kk in ("text", "meta", "created_at")}}
                 for r in self._col(public_collection(room_id)).records[-n:]]
        for name in os.listdir(self.root) if os.path.isdir(self.root) else []:
            if name.startswith("agent_") and name.endswith("_private.json"):
                aid = name[len("agent_"):-len("_private.json")]
                items.extend(
                    {"scope": f"private:{aid}",
                     **{kk: r[kk] for kk in ("text", "meta", "created_at")}}
                    for r in self._col(private_collection(aid)).records[-n:])
        items.sort(key=lambda x: x["created_at"], reverse=True)
        return items[:n]


hub = MemoryHub()


def format_memory_context(hits: list[dict]) -> str:
    """检索结果 → 注入 system prompt 的文本段（标注来源与时间）。"""
    if not hits:
        return ""
    lines = ["以下是检索到的相关历史记忆（仅供参考，注意时效）："]
    for h in hits:
        tag = "公共" if h["scope"] == "public" else "私有"
        lines.append(f"- [{tag}·{h['created_at'][:16]}] {h['text']}")
    return "\n".join(lines)
