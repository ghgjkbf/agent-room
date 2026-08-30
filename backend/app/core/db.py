"""SQLite 连接与表初始化。

MVP 使用 SQLite（设计文档 s11），事件流 messages 表 append-only。
"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager

from app.core.config import BASE_DIR
from app.core.message import now_cst

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
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  room_id TEXT NOT NULL,
  goal TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'awaiting_confirm',
  plan_json TEXT DEFAULT '[]',
  chat_count INTEGER NOT NULL DEFAULT 0,
  summary TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subtasks (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  room_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  title TEXT NOT NULL,
  guidance TEXT DEFAULT '',
  assignee TEXT NOT NULL,
  depends_on TEXT DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'pending',
  retries INTEGER NOT NULL DEFAULT 0,
  delivery_text TEXT,
  accepted_at TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_subtasks_task ON subtasks(task_id, seq);
CREATE TABLE IF NOT EXISTS kv (
  k TEXT PRIMARY KEY,
  v TEXT
);
CREATE TABLE IF NOT EXISTS room_members (
  room_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  joined_at TEXT,
  PRIMARY KEY (room_id, agent_id)
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
        # 第 6 步多房间：成员归属关系表（agents 表保留为全局注册表）；
        # 迁移：把 agents 表现有行映射为成员关系（幂等）
        conn.execute(
            "INSERT OR IGNORE INTO room_members (room_id, agent_id, joined_at)"
            " SELECT room_id, id, ? FROM agents", (now_cst(),))
        # 出厂身份卡（幂等）：A/B 的默认工具白名单；用户可在界面换绑/编辑
        # 出厂卡白名单升级：仍是旧默认集合时追加新能力工具（用户改过则不动）
        _old_default = '["fs.list","fs.read","memory.query","skills.list","skills.read"]'
        _new_default = ('["fs.list","fs.read","memory.query","skills.list","skills.read",'
                        '"skills.write","doc.read","browser.open"]')
        conn.execute(
            "UPDATE identities SET tools_allow=? WHERE id IN ('idf_steward','idf_assistant')"
            " AND tools_allow=?", (_new_default, _old_default))
        _steward_tools = '["fs.list","fs.read","memory.query","skills.list","skills.read"]'
        for _cid, _label, _resp, _tools in (
            ("idf_steward", "管家·出厂",
             ["群内容治理", "记忆管理", "越权监管", "归档清理"], _steward_tools),
            ("idf_assistant", "服务·出厂",
             ["答疑", "提示词辅助", "调度建议", "进展监督"], _steward_tools),
        ):
            # responsibilities 列约定为 JSON 数组（load_identity json.loads）
            conn.execute(
                "INSERT OR IGNORE INTO identities (id, label, persona, responsibilities,"
                " tools_allow, budget_turns, version, created_at) VALUES"
                " (?,?, '', ?, ?, 6, 1, ?)",
                (_cid, _label, json.dumps(_resp, ensure_ascii=False), _tools, now_cst()))
        # 优化迭代：子任务落最近一次验收结论（任务面板展示裁决依据）
        scols = {r[1] for r in conn.execute("PRAGMA table_info(subtasks)")}
        if scols and "last_receipt" not in scols:
            conn.execute("ALTER TABLE subtasks ADD COLUMN last_receipt TEXT")
        _migrate_messages(conn)


init_db()
