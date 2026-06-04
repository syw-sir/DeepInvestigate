"""
DeepInvestigate v3.0 多模型路由模块

提供：
    - ModelRouter    : 多模型选择与 fallback
    - CostTracker    : Token 用量与成本追踪
    - get_router()   : 全局单例
"""

from .router import ModelRouter, ModelTier, ModelConfig, get_router
from .cost_tracker import CostTracker, UsageRecord, get_cost_tracker

__all__ = [
    "ModelRouter",
    "ModelTier",
    "ModelConfig",
    "get_router",
    "CostTracker",
    "UsageRecord",
    "get_cost_tracker",
]
