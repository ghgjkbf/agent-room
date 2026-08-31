"""初始化重置：清空全部运行数据，恢复出厂状态（v0.9.1）。

保留：出厂身份卡（管家·出厂 / 服务·出厂，含白名单与 focus 预设）、
schema、全部代码与配置。清空：消息、任务、文件索引与工作区文件、
向量记忆、成员注册表（含外部成员及其令牌）、群聊房间（除 default）、
归档游标、LLM 配置等 kv 运行时数据。

用法：backend\\.venv\\Scripts\\python.exe backend\\reset_init.py [--force]
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings  # noqa: E402
from app.core.db import DB_PATH, db, init_db  # noqa: E402

WORKSPACE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")
MEMORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "memory")


def reset():
    with db() as conn:
        # 运行数据全清（顺序：先子后父）
        for table in ("subtasks", "tasks", "messages", "files",
                      "room_members", "agents", "rooms", "kv"):
            conn.execute(f"DELETE FROM {table}")
        # 身份卡只留出厂两张（用户自建卡一并清除）
        conn.execute("DELETE FROM identities WHERE id NOT IN ('idf_steward','idf_assistant')")
        # 出厂卡恢复预设（清掉演示期可能的人工改动，回到发布基线）
        import json
        conn.execute(
            "UPDATE identities SET tools_allow=?, focus=? WHERE id='idf_steward'",
            (json.dumps(["fs.read", "fs.write", "fs.list", "memory.query"]),
             json.dumps(["归档", "记忆", "治理", "越权", "群务", "清理", "秩序"], ensure_ascii=False)))
        conn.execute(
            "UPDATE identities SET tools_allow=?, focus=? WHERE id='idf_assistant'",
            (json.dumps(["fs.read", "fs.write", "fs.list", "memory.query"]),
             json.dumps(["答疑", "帮助", "怎么", "求助", "问题", "如何"], ensure_ascii=False)))
    # 磁盘：工作区文件 + 向量记忆
    for d in (WORKSPACE, MEMORY_DIR):
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)
    print("reset done: messages/tasks/files/members/rooms/kv cleared;")
    print("workspace & memory dirs recreated; factory identity cards restored.")


if __name__ == "__main__":
    if "--force" not in sys.argv:
        ans = input("将清空全部运行数据（消息/任务/文件/成员/记忆/LLM 配置），确定？[y/N] ")
        if ans.strip().lower() != "y":
            print("aborted")
            sys.exit(0)
    init_db()
    reset()
