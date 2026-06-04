"""
护栏审计日志

记录所有护栏拦截事件到 Redis，支持按时间/类型查询。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AuditEvent:
    timestamp: str
    event_type: str
    user_id: str
    thread_id: str
    detail: str
    original_preview: str


class AuditLogger:
    """护栏审计日志"""

    def __init__(self, redis_client):
        self.redis = redis_client

    def log(self, event: AuditEvent):
        if not self.redis:
            return
        try:
            key = f"audit:{event.timestamp[:10]}"
            self.redis.lpush(key, json.dumps(asdict(event), ensure_ascii=False))
            self.redis.expire(key, 86400 * 90)
        except Exception as e:
            logger.warning("Failed to write audit log: %s", e)

    def query(self, days: int = 7, event_type: Optional[str] = None) -> list:
        if not self.redis:
            return []
        results = []
        try:
            from datetime import timedelta
            today = datetime.now()
            for i in range(days):
                day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                key = f"audit:{day}"
                records = self.redis.lrange(key, 0, -1)
                for r in records:
                    try:
                        rec = json.loads(r) if isinstance(r, (str, bytes)) else r
                        if isinstance(r, bytes):
                            rec = json.loads(r.decode())
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if event_type and rec.get("event_type") != event_type:
                        continue
                    results.append(rec)
        except Exception as e:
            logger.warning("Failed to query audit logs: %s", e)
        return results
