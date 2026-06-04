"""
A2A 消息协议定义
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageType(Enum):
    TASK_ASSIGN = "task_assign"
    TASK_RESULT = "task_result"
    CLARIFICATION_REQUEST = "clarification_request"
    STATUS_UPDATE = "status_update"


@dataclass
class A2AMessage:
    sender: str
    receiver: str
    msg_type: MessageType
    payload: dict
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "sender": self.sender,
            "receiver": self.receiver,
            "msg_type": self.msg_type.value,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "A2AMessage":
        return cls(
            sender=data["sender"],
            receiver=data["receiver"],
            msg_type=MessageType(data["msg_type"]),
            payload=data.get("payload", {}),
            correlation_id=data.get("correlation_id", ""),
            timestamp=data.get("timestamp", time.time()),
        )
