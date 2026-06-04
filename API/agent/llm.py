"""
LangChain ChatModel 工厂 (v3.0)

通过 ModelRouter 支持多模型路由、fallback 与成本追踪。
回退兼容 v2.0 单模型模式。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

from langchain_openai import ChatOpenAI

try:
    from config_deepseek import (
        API_BASE,
        API_KEY,
        MODEL_PATH,
        MAX_NEW_TOKENS,
        PLANNER_TEMPERATURE,
        INVESTIGATOR_TEMPERATURE,
        REPORTER_TEMPERATURE,
    )
except ImportError:
    from ..config_deepseek import (  # type: ignore
        API_BASE,
        API_KEY,
        MODEL_PATH,
        MAX_NEW_TOKENS,
        PLANNER_TEMPERATURE,
        INVESTIGATOR_TEMPERATURE,
        REPORTER_TEMPERATURE,
    )

logger = logging.getLogger(__name__)

_use_router: Optional[bool] = None


def _should_use_router() -> bool:
    global _use_router
    if _use_router is None:
        try:
            from config_deepseek import config as raw_config
        except ImportError:
            from ..config_deepseek import config as raw_config  # type: ignore
        models_cfg = (raw_config.get("models") or {})
        _use_router = bool(models_cfg.get("tiers"))
    return _use_router


def _make_chat(temperature: float, streaming: bool = True) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL_PATH,
        base_url=API_BASE,
        api_key=API_KEY,
        temperature=temperature,
        max_tokens=MAX_NEW_TOKENS,
        streaming=streaming,
        timeout=120,
    )


def _make_routed(tier_name: str, temperature: float, streaming: bool = True) -> ChatOpenAI:
    try:
        from model_router.router import ModelTier, get_router
    except ImportError:
        from ..model_router.router import ModelTier, get_router  # type: ignore
    tier = ModelTier(tier_name)
    return get_router().get_llm(tier, temperature=temperature, streaming=streaming, max_tokens=MAX_NEW_TOKENS)


@lru_cache(maxsize=4)
def get_planner_llm(streaming: bool = True) -> ChatOpenAI:
    if _should_use_router():
        return _make_routed("high", PLANNER_TEMPERATURE, streaming=streaming)
    return _make_chat(PLANNER_TEMPERATURE, streaming=streaming)


@lru_cache(maxsize=4)
def get_investigator_llm(streaming: bool = True) -> ChatOpenAI:
    if _should_use_router():
        return _make_routed("medium", INVESTIGATOR_TEMPERATURE, streaming=streaming)
    return _make_chat(INVESTIGATOR_TEMPERATURE, streaming=streaming)


@lru_cache(maxsize=4)
def get_reporter_llm(streaming: bool = True) -> ChatOpenAI:
    if _should_use_router():
        return _make_routed("high", REPORTER_TEMPERATURE, streaming=streaming)
    return _make_chat(REPORTER_TEMPERATURE, streaming=streaming)


def get_critic_llm(temperature: float = 0.2) -> ChatOpenAI:
    if _should_use_router():
        return _make_routed("low", temperature, streaming=False)
    return _make_chat(temperature, streaming=False)
