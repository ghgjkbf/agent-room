"""技能库 HTTP API（前端「技能」面板用）。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.skills import store

router = APIRouter(prefix="/api/skills", tags=["skills"])


class SkillIn(BaseModel):
    name: str
    content: str


@router.get("")
async def list_skills():
    return store.list_skills()


@router.get("/{name}")
async def read_skill(name: str):
    try:
        return store.read_skill(name)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("")
async def write_skill(body: SkillIn):
    try:
        return {"ok": True, **store.write_skill(body.name.strip(), body.content)}
    except ValueError as e:
        raise HTTPException(400, str(e))


# 本机技能源（可选环境变量覆盖；导入 = 复制其 SKILL.md 为内部技能）。
# 默认关闭——发布版不预设任何开发者本机路径，用户经 env 或前端传本机绝对路径按需启用。
import os as _os

BUILTIN_SOURCES = {
    "zcode": _os.environ.get("AGENT_ROOM_SKILLS_ZCODE", ""),
    "trae": _os.environ.get("AGENT_ROOM_SKILLS_TRAE", ""),
    "trae-builtin": _os.environ.get("AGENT_ROOM_SKILLS_TRAE_BUILTIN", ""),
}


class ImportIn(BaseModel):
    source: str                 # BUILTIN_SOURCES 的 key 或本机绝对路径
    limit: int = 200


@router.post("/import")
async def import_local_skills(body: ImportIn):
    """从本机技能目录批量导入 SKILL.md（目录名即技能名；同名覆盖）。"""
    import os
    import re as _re

    src = BUILTIN_SOURCES.get(body.source, body.source)
    if not os.path.isdir(src):
        return {"ok": False, "detail": f"目录不存在：{src}"}
    imported, skipped = [], []
    for root, dirs, files in os.walk(src):
        if "SKILL.md" not in files:
            continue
        name = _re.sub(r"[^\w\-]+", "-", os.path.basename(root)).strip("-").lower()
        if not name:
            continue
        try:
            with open(os.path.join(root, "SKILL.md"), encoding="utf-8") as f:
                content = f.read()
            store.write_skill(name, content)
            imported.append(name)
        except (OSError, ValueError) as e:
            skipped.append({"dir": os.path.basename(root), "reason": str(e)})
        if len(imported) >= body.limit:
            break
    return {"ok": True, "imported": imported, "skipped": skipped,
            "count": len(imported)}


@router.delete("/{name}")
async def delete_skill(name: str):
    try:
        store.delete_skill(name)
        return {"ok": True}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
