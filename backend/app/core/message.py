"""消息协议（设计文档 s4，schema v1.0 冻结字段）。"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional


def now_cst() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="milliseconds")


class Message:
    """通用消息结构：一切皆消息（append-only 事件流）。"""

    def __init__(
        self,
        room_id: str,
        type: str,
        sender_kind: str,
        sender_id: str,
        payload_text: str = "",
        priority: int = 3,
        mentions: Optional[list] = None,
        parent_task_id: Optional[str] = None,
        msg_id: Optional[str] = None,
        created_at: Optional[str] = None,
        seq: Optional[int] = None,
        stream_seq: int = 0,
        is_final: bool = True,
        starred: int = 0,
    ):
        self.msg_id = msg_id or str(uuid.uuid4())
        self.schema_version = "1.0"
        self.room_id = room_id
        self.type = type  # interrupt|task|dispatch|chat|deliver|receipt|system
        self.priority = priority
        self.sender_kind = sender_kind  # human|agent|orchestrator|system
        self.sender_id = sender_id
        self.payload_text = payload_text
        self.mentions = mentions or []
        self.parent_task_id = parent_task_id
        self.created_at = created_at or now_cst()
        self.seq = seq
        # 流式分片标记：stream_seq>0 表示片段；is_final=False 后续还有片段
        self.stream_seq = stream_seq
        self.is_final = is_final
        # 星标（UI 标注）：0/1，仅前端展示语义，不影响编排与网关
        self.starred = starred
        # 连锁回复标记：内置成员接话产生的消息不再自动唤起他人（防 A↔B 死循环）；
        # 仅内存传递，不落库不进协议
        self.is_reply = False

    @classmethod
    def from_row(cls, row) -> "Message":
        # 历史回放用聚合后的完整文本（新协议分片消息落库时只存首条，full_text 即全文）
        text = row["full_text"] or row["payload_text"] or ""
        return cls(
            room_id=row["room_id"],
            type=row["type"],
            priority=row["priority"],
            sender_kind=row["sender_kind"],
            sender_id=row["sender_id"],
            payload_text=text,
            mentions=json.loads(row["mentions"] or "[]"),
            parent_task_id=row["parent_task_id"],
            msg_id=row["msg_id"],
            created_at=row["created_at"],
            seq=row["id"],
            is_final=True,
            starred=row["starred"] or 0,
        )

    def to_dict(self) -> dict:
        return {
            "msg_id": self.msg_id,
            "schema_version": self.schema_version,
            "room_id": self.room_id,
            "seq": self.seq,
            "type": self.type,
            "priority": self.priority,
            "sender": {"kind": self.sender_kind, "id": self.sender_id},
            "payload": {"text": self.payload_text},
            "mentions": self.mentions,
            "parent_task_id": self.parent_task_id,
            "created_at": self.created_at,
            "stream_seq": self.stream_seq,
            "is_final": self.is_final,
            "starred": self.starred,
        }
