"""SQLite 连接与表初始化。

MVP 使用 SQLite（设计文档 s11），事件流 messages 表 append-only。
"""

import os
import sqlite3
import threading
from contextlib import contextmanager

from app.core.config import BASE_DIR

DB_PATH = os.path.join(BASE_DIR, "agent_room.db")
_lock = threading.Lock()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db():
    conn = get_conn()
    try:
        with _lock:
            yield conn
            conn.commit()
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  budget_limit INTEGER DEFAULT 0,
  created_by TEXT DEFAULT 'human',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY,
  room_id TEXT NOT NULL,
  name TEXT NOT NULL,
  identity_id TEXT,
  llm_config TEXT,
  kind TEXT DEFAULT 'internal',
  status TEXT DEFAULT 'online'
);
CREATE TABLE IF NOT EXISTS identities (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  config_yaml TEXT,
  author TEXT,
  version INTEGER DEFAULT 1,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  msg_id TEXT UNIQUE NOT NULL,
  room_id TEXT NOT NULL,
  type TEXT NOT NULL,
  priority INTEGER DEFAULT 3,
  sender_kind TEXT NOT NULL,
  sender_id TEXT NOT NULL,
  payload_text TEXT,
  mentions TEXT DEFAULT '[]',
  parent_task_id TEXT,
  invalidated INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room_id, id);
CREATE TABLE IF NOT EXISTS files (
  id TEXT PRIMARY KEY,
  room_id TEXT NOT NULL,
  path TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  author_agent TEXT NOT NULL,
  manifest_json TEXT DEFAULT '{}',
  updated_at TEXT NOT NULL,
  UNIQUE(room_id, path)
);
"""

# 迁移后 messages 新增列：完整文本聚合列 + 分片序号/终止标记（协议扩展，旧库自动补）


def _migrate_messages(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
    if "stream_seq" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN stream_seq INTEGER NOT NULL DEFAULT 0")
    if "is_final" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN is_final INTEGER NOT NULL DEFAULT 1")
    if "full_text" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN full_text TEXT")
    # 旧数据回填：历史上每个分片都是独立消息且 is_final=1，补全 full_text 即可回放原文
    conn.execute(
        "UPDATE messages SET full_text = payload_text"
        " WHERE (full_text IS NULL OR full_text = '') AND payload_text IS NOT NULL"
    )


def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)
        # 增量迁移：旧库补列（identities 状态/预算字段，s5 身份卡）
        cols = {r[1] for r in conn.execute("PRAGMA table_info(identities)")}
        if "persona" not in cols:
            conn.execute("ALTER TABLE identities ADD COLUMN persona TEXT DEFAULT ''")
        if "responsibilities" not in cols:
            conn.execute("ALTER TABLE identities ADD COLUMN responsibilities TEXT DEFAULT '[]'")
        if "tools_allow" not in cols:
            conn.execute("ALTER TABLE identities ADD COLUMN tools_allow TEXT DEFAULT '[]'")
        if "budget_turns" not in cols:
            conn.execute("ALTER TABLE identities ADD COLUMN budget_turns INTEGER DEFAULT 6")
        # agents 表补排产轮数计数
        acols = {r[1] for r in conn.execute("PRAGMA table_info(agents)")}
        if "chat_turns" not in acols:
            conn.execute("ALTER TABLE agents ADD COLUMN chat_turns INTEGER DEFAULT 0")
        # 第 3 步 MCP 网关：外部成员令牌哈希 + 外部消息幂等键
        if "api_token_hash" not in acols:
            conn.execute("ALTER TABLE agents ADD COLUMN api_token_hash TEXT")
        mcols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
        if "client_msg_id" not in mcols:
            conn.execute("ALTER TABLE messages ADD COLUMN client_msg_id TEXT")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_client_dedup"
            " ON messages(room_id, sender_id, client_msg_id)"
            " WHERE client_msg_id IS NOT NULL"
        )
        # 第 4 步文件工作区：files 表（旧库由 CREATE TABLE IF NOT EXISTS 兜底）
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_files_room_path ON files(room_id, path)"
        )
        _migrate_messages(conn)


init_db()
