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


@router.delete("/{name}")
async def delete_skill(name: str):
    try:
        store.delete_skill(name)
        return {"ok": True}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
