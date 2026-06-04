"""
Token 用量与成本追踪器
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

PRICING = {
    "deepseek:deepseek-chat":       {"prompt": 0.14, "completion": 0.28},
    "deepseek:deepseek-reasoner":   {"prompt": 0.55, "completion": 2.19},
    "openai:gpt-4o":                {"prompt": 2.50, "completion": 10.00},
    "openai:gpt-4o-mini":           {"prompt": 0.15, "completion": 0.60},
    "openai:gpt-4":                 {"prompt": 30.00, "completion": 60.00},
}


@dataclass
class UsageRecord:
    timestamp: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    node: str
    thread_id: str


class CostTracker:
    """Token 用量与成本追踪器"""

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._buffer: list[UsageRecord] = []

    def record(
        self,
        model_key: str,
        prompt_tokens: int,
        completion_tokens: int,
        node: str = "",
        thread_id: str = "",
    ):
        pricing = PRICING.get(model_key, {"prompt": 0.14, "completion": 0.28})
        cost = (
            prompt_tokens / 1_000_000 * pricing["prompt"]
            + completion_tokens / 1_000_000 * pricing["completion"]
        )
        record = UsageRecord(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            model=model_key,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=round(cost, 6),
            node=node,
            thread_id=thread_id,
        )
        self._buffer.append(record)

        if self.redis:
            try:
                key = f"usage:{datetime.now().strftime('%Y%m%d')}"
                self.redis.lpush(key, json.dumps(asdict(record), ensure_ascii=False))
                self.redis.expire(key, 86400 * 30)
            except Exception as e:
                logger.warning("Failed to write usage to Redis: %s", e)

    def get_daily_stats(self, days: int = 7) -> dict:
        stats: dict = {
            "total_cost": 0.0,
            "total_tokens": 0,
            "by_model": {},
            "by_node": {},
            "by_day": {},
        }
        if not self.redis:
            if self._buffer:
                return self._aggregate_buffer(stats)
            return stats

        try:
            for i in range(days):
                day = datetime.fromtimestamp(time.time() - i * 86400).strftime("%Y%m%d")
                key = f"usage:{day}"
                records = self.redis.lrange(key, 0, -1)
                for r in records:
                    try:
                        rec = json.loads(r) if isinstance(r, (str, bytes)) else r
                        if isinstance(r, bytes):
                            rec = json.loads(r.decode())
                    except (json.JSONDecodeError, TypeError):
                        continue
                    stats["total_cost"] += rec.get("cost_usd", 0)
                    stats["total_tokens"] += rec.get("prompt_tokens", 0) + rec.get("completion_tokens", 0)
                    model = rec.get("model", "unknown")
                    node = rec.get("node", "unknown")
                    stats["by_model"].setdefault(model, {"cost": 0, "tokens": 0})
                    stats["by_model"][model]["cost"] += rec.get("cost_usd", 0)
                    stats["by_model"][model]["tokens"] += rec.get("prompt_tokens", 0) + rec.get("completion_tokens", 0)
                    stats["by_node"].setdefault(node, {"cost": 0, "calls": 0})
                    stats["by_node"][node]["cost"] += rec.get("cost_usd", 0)
                    stats["by_node"][node]["calls"] += 1
                    stats["by_day"].setdefault(day, {"cost": 0, "tokens": 0})
                    stats["by_day"][day]["cost"] += rec.get("cost_usd", 0)
                    stats["by_day"][day]["tokens"] += rec.get("prompt_tokens", 0) + rec.get("completion_tokens", 0)
        except Exception as e:
            logger.warning("Failed to query usage stats: %s", e)

        stats["total_cost"] = round(stats["total_cost"], 6)
        return stats

    def _aggregate_buffer(self, stats: dict) -> dict:
        for rec in self._buffer:
            stats["total_cost"] += rec.cost_usd
            stats["total_tokens"] += rec.prompt_tokens + rec.completion_tokens
            model = rec.model
            node = rec.node
            stats["by_model"].setdefault(model, {"cost": 0, "tokens": 0})
            stats["by_model"][model]["cost"] += rec.cost_usd
            stats["by_model"][model]["tokens"] += rec.prompt_tokens + rec.completion_tokens
            stats["by_node"].setdefault(node, {"cost": 0, "calls": 0})
            stats["by_node"][node]["cost"] += rec.cost_usd
            stats["by_node"][node]["calls"] += 1
        stats["total_cost"] = round(stats["total_cost"], 6)
        return stats


_cost_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    global _cost_tracker
    if _cost_tracker is None:
        try:
            from memory.redis_client import get_redis_client
            redis = get_redis_client()
        except Exception:
            redis = None
        _cost_tracker = CostTracker(redis)
    return _cost_tracker
