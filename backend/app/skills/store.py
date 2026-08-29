"""内部技能库（第 6 步增强）：供群里 Agent 经 skills.* 工具使用的 md 文档。

- 存储：backend/skills/{name}.md，文件名即技能名（字母/数字/下划线/连字符，1-40 位）。
- 用途：写法规范、模板、工作流指引等——Agent 按白名单拿到 skills.list /
  skills.read 工具后可自查照做；用户也可在前端「技能」面板增删。
- 工作流也是技能：用 md 写清楚步骤即可，MVP 不做执行引擎。
"""

import os
import re
import threading

from app.core.config import BASE_DIR

SKILLS_DIR = os.path.join(BASE_DIR, "skills")
_NAME_RE = re.compile(r"^[\w\-]{1,40}$", re.UNICODE)  # 含中文；排除空格/点/斜杠等路径危险字符
_lock = threading.Lock()


def _path(name: str) -> str:
    if not _NAME_RE.match(name or ""):
        raise ValueError("技能名仅允许文字/数字/下划线/连字符（可中文），长度 1-40")
    return os.path.join(SKILLS_DIR, f"{name}.md")


def list_skills() -> list[dict]:
    if not os.path.isdir(SKILLS_DIR):
        return []
    out = []
    for fn in sorted(os.listdir(SKILLS_DIR)):
        if not fn.endswith(".md"):
            continue
        p = os.path.join(SKILLS_DIR, fn)
        try:
            out.append({
                "name": fn[:-3],
                "chars": os.path.getsize(p),
                "updated_at": os.path.getmtime(p),
            })
        except OSError:
            continue
    return out


def read_skill(name: str) -> dict:
    p = _path(name)
    if not os.path.isfile(p):
        raise FileNotFoundError(f"技能 {name} 不存在")
    with open(p, encoding="utf-8") as f:
        content = f.read()
    return {"name": name, "content": content}


def write_skill(name: str, content: str) -> dict:
    p = _path(name)
    if len(content) > 200_000:
        raise ValueError("技能名仅允许文字/数字/下划线/连字符（可中文），长度 1-40")
    with _lock:
        os.makedirs(SKILLS_DIR, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    return {"name": name, "chars": len(content)}


def delete_skill(name: str) -> None:
    p = _path(name)
    if not os.path.isfile(p):
        raise FileNotFoundError(f"技能 {name} 不存在")
    with _lock:
        os.remove(p)
