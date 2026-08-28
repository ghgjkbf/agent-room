"""文件工作区 HTTP API（第 4 步，人类侧）：树 / 内容 / 上传 / 删除。

- 人类直写（upload）不校验 base_version（设计决策）。
- 纯文本预览前端直接渲染；二进制按 manifest 标记 size，不回内容。
"""

import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.db import db
from app.files import workspace

router = APIRouter(prefix="/api/files")


@router.get("")
async def list_files(room_id: str = "default"):
    """全部文件索引（前端按 path 拼树）。"""
    return workspace.list_files(room_id)


@router.get("/content")
async def file_content(room_id: str, path: str):
    return workspace.read_file(room_id, path)


class WriteIn(BaseModel):
    room_id: str = "default"
    path: str
    content: str
    base_version: int | None = None


@router.post("/write")
async def write_file(body: WriteIn):
    """人类前端直写（乐观锁由前端带着 read 回来的 version 传，可选）。"""
    result = workspace.write_file(
        room_id=body.room_id, path=body.path, content=body.content,
        author="human", base_version=body.base_version,
    )
    result["ok"] = True
    return result


@router.post("/upload")
async def upload_file(room_id: str = "default", file: UploadFile = File(...)):
    """multipart 上传（人类）：读为 UTF-8 文本落盘，作者记 human。"""
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(400, "单文件超过 10MB 上限")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "MVP 仅支持 UTF-8 文本文件（二进制支持后续开放）")
    result = workspace.write_file(
        room_id=room_id, path=file.filename or f"upload_{uuid.uuid4().hex[:6]}",
        content=content, author="human",
    )
    result["ok"] = True
    return result


class DeleteIn(BaseModel):
    room_id: str = "default"
    path: str


@router.delete("")
async def delete_file(body: DeleteIn):
    return workspace.delete_file(body.room_id, body.path)
