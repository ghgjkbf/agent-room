"""本地 embedding：接口留 OpenAI 兼容 /embeddings 换装位，默认降级为
确定性字符 n-gram 哈希向量（256 维，中文按字切分，离线零依赖）。

bge-m3 等本地模型待 Python 环境支持后经 embed_with_llm() 无缝替换。
"""

import hashlib
import json
import math

DIM = 256


def _slots(text: str) -> dict[int, int]:
    """字符 unigram + bigram 哈希到固定维度，权重 = 出现次数。"""
    slots: dict[int, int] = {}
    s = [c for c in text.strip() if not c.isspace()]
    grams = s + [s[i] + s[i + 1] for i in range(len(s) - 1)]
    for g in grams:
        h = int.from_bytes(hashlib.md5(g.encode("utf-8")).digest()[:4], "little")
        slots[h % DIM] = slots.get(h % DIM, 0) + 1
    return slots


def embed_local(text: str) -> list[float]:
    vec = [0.0] * DIM
    for idx, w in _slots(text).items():
        vec[idx] = float(w)
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


async def embed_with_llm(text: str, base_url: str, api_key: str, model: str) -> list[float] | None:
    """OpenAI 兼容 /embeddings；失败返回 None 由调用方降级。"""
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        r = await client.embeddings.create(input=text[:2000], model=model)
        return list(r.data[0].embedding)
    except Exception:
        return None


async def embed_text(text: str) -> list[float]:
    """优先走 LLM 端点（若配置），失败或未配置降级本地哈希向量。"""
    from app.core.config import settings

    if settings.llm_base_url and settings.llm_api_key:
        v = await embed_with_llm(text, settings.llm_base_url,
                                 settings.llm_api_key, "text-embedding-3-small")
        if v:
            return v
    return embed_local(text)


def cosine(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return num / (na * nb)


def dumps_meta(meta: dict) -> str:
    return json.dumps(meta, ensure_ascii=False)


def loads_meta(raw: str) -> dict:
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {}
