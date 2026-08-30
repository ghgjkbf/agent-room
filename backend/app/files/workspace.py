"""文件工作区（第 4 步）：磁盘目录 + SQLite files 索引 + base_version 乐观锁。

- 磁盘根：backend/workspace/{room_id}/（索引与磁盘文件一一对应）
- 路径规范化：统一 POSIX 相对路径，任何 ../ 或绝对路径一律拒绝（防逃逸）
- 乐观锁：Agent 写必须带 base_version（其读到的最新版本）；冲突返回 409
  并携带 latest_version，由 Agent 重读重写。人类直写（upload）不校验。
- 索引列（设计文档 s11）：id, room_id, path, version, author_agent,
  manifest_json, updated_at。author_agent="human" 表示人类/前端上传。
"""

import json
import os
import re
import uuid

from fastapi import HTTPException

from app.core.config import BASE_DIR
from app.core.db import db
from app.core.message import now_cst

WORKSPACE_ROOT = os.path.join(BASE_DIR, "workspace")

# 禁止的路径片段：绝对路径、盘符、.. 上跳、反斜杠、//、./ 前缀（统一 / 分隔）
_BAD = re.compile(r"(^/|^[A-Za-z]:|\.\.|\\|//|^(\./)+)")


def ensure_dir(room_id: str) -> str:
    d = room_dir(room_id)
    os.makedirs(d, exist_ok=True)
    return d


def room_dir(room_id: str) -> str:
    d = os.path.join(WORKSPACE_ROOT, room_id)
    os.makedirs(d, exist_ok=True)
    return d


def normalize_path(path: str) -> str:
    """校验并规范化相对路径（POSIX 风格），非法抛 HTTPException 400。"""
    raw = path or ""
    p = raw.strip().replace("\\", "/")
    if not p or p in ("/", "."):
        raise HTTPException(400, "文件路径不能为空")
    if "\\" in raw or _BAD.search(p):
        raise HTTPException(400, f"非法路径：{path}")
    return p


def _abs(room_id: str, path: str) -> str:
    """相对路径 -> 磁盘绝对路径；根目录在 room_dir 内。"""
    return os.path.join(room_dir(room_id), *path.split("/"))


def _row_to_file(r) -> dict:
    return {
        "path": r["path"],
        "version": r["version"],
        "author": r["author_agent"],
        "manifest": json.loads(r["manifest_json"] or "{}"),
        "updated_at": r["updated_at"],
    }


def list_files(room_id: str) -> list[dict]:
    """全部文件索引（树由前端按 path 拼装）。"""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM files WHERE room_id=? ORDER BY path", (room_id,)
        ).fetchall()
    return [_row_to_file(r) for r in rows]


def read_file(room_id: str, path: str) -> dict:
    p = normalize_path(path)
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM files WHERE room_id=? AND path=?", (room_id, p)
        ).fetchone()
    if not row:
        raise HTTPException(404, f"文件不存在：{p}")
    abs_path = _abs(room_id, p)
    if not os.path.isfile(abs_path):
        raise HTTPException(404, f"磁盘文件缺失：{p}（索引与磁盘不一致）")
    with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
        content = fh.read()
    return {**_row_to_file(row), "content": content}


def write_file(
    room_id: str,
    path: str,
    content: str,
    author: str,
    base_version: int | None = None,
    manifest: dict | None = None,
) -> dict:
    """Agent 写：base_version=None 表示新建（已存在则冲突）；否则必须匹配
    当前版本（乐观锁），不匹配抛 409（附 latest_version 供重写）。"""
    p = normalize_path(path)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "单文件超过 10MB 上限")
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM files WHERE room_id=? AND path=?", (room_id, p)
        ).fetchone()
        cur_version = row["version"] if row else 0
        if base_version is None:
            if row:
                raise HTTPException(409, {
                    "detail": "文件已存在，需携带 base_version 指定要覆盖的版本",
                    "latest_version": cur_version,
                })
            version = 1
        else:
            if not row:
                raise HTTPException(409, {
                    "detail": "文件不存在，新建请省略 base_version",
                    "latest_version": 0,
                })
            if int(base_version) != cur_version:
                raise HTTPException(409, {
                    "detail": f"版本冲突：你的 base_version={base_version}，"
                              f"当前已是 v{cur_version}，请重读后重写",
                    "latest_version": cur_version,
                })
            version = cur_version + 1
        abs_path = _abs(room_id, p)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        ts = now_cst()
        if row:
            conn.execute(
                "UPDATE files SET version=?, author_agent=?, manifest_json=?, updated_at=?"
                " WHERE room_id=? AND path=?",
                (version, author, json.dumps(manifest or {}), ts, room_id, p),
            )
        else:
            conn.execute(
                "INSERT INTO files (id, room_id, path, version, author_agent,"
                " manifest_json, updated_at) VALUES (?,?,?,?,?,?,?)",
                (f"file_{uuid.uuid4().hex[:12]}", room_id, p, version, author,
                 json.dumps(manifest or {}), ts),
            )
    return {"path": p, "version": version, "author": author, "updated_at": ts}


def delete_file(room_id: str, path: str):
    p = normalize_path(path)
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM files WHERE room_id=? AND path=?", (room_id, p)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"文件不存在：{p}")
        abs_path = _abs(room_id, p)
        if os.path.isfile(abs_path):
            os.remove(abs_path)
        conn.execute("DELETE FROM files WHERE room_id=? AND path=?", (room_id, p))
    return {"ok": True}
