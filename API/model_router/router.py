"""
多模型路由器

支持按 tier 分配模型、主模型不可用时自动 fallback。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


class ModelTier(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ModelConfig:
    provider: str
    model_name: str
    api_key: str
    base_url: str
    tier: ModelTier
    max_rpm: int = 60


@dataclass
class _ProviderState:
    available: bool = True
    last_error_time: float = 0.0
    consecutive_errors: int = 0


class ModelRouter:
    """多模型路由器"""

    def __init__(self, configs: list[ModelConfig]):
        self.configs: dict[str, ModelConfig] = {}
        self._primary: dict[ModelTier, str] = {}
        self._fallback: dict[ModelTier, str] = {}
        self._state: dict[str, _ProviderState] = {}

        for cfg in configs:
            key = f"{cfg.provider}:{cfg.model_name}"
            self.configs[key] = cfg
            self._state[key] = _ProviderState()

    def set_primary(self, tier: ModelTier, provider: str, model_name: str):
        key = f"{provider}:{model_name}"
        if key in self.configs:
            self._primary[tier] = key

    def set_fallback(self, tier: ModelTier, provider: str, model_name: str):
        key = f"{provider}:{model_name}"
        if key in self.configs:
            self._fallback[tier] = key

    def get_llm(
        self,
        tier: ModelTier,
        temperature: float = 0.4,
        streaming: bool = True,
        max_tokens: int = 8192,
    ) -> ChatOpenAI:
        primary_key = self._primary.get(tier)
        fallback_key = self._fallback.get(tier)

        cfg = None
        used_fallback = False

        if primary_key and self._is_available(primary_key):
            cfg = self.configs[primary_key]
        elif fallback_key and self._is_available(fallback_key):
            cfg = self.configs[fallback_key]
            used_fallback = True
            logger.warning(
                "Tier %s primary unavailable, fallback to %s",
                tier.value,
                fallback_key,
            )
        elif primary_key:
            cfg = self.configs[primary_key]
        else:
            raise RuntimeError(f"No model configured for tier {tier.value}")

        llm = ChatOpenAI(
            model=cfg.model_name,
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=streaming,
            timeout=120,
        )

        llm._di_model_key = f"{cfg.provider}:{cfg.model_name}"
        llm._di_fallback_triggered = used_fallback

        return llm

    def _is_available(self, key: str) -> bool:
        state = self._state.get(key)
        if state is None:
            return False
        if not state.available:
            if time.time() - state.last_error_time > 60:
                state.available = True
                state.consecutive_errors = 0
            else:
                return False
        return True

    def mark_error(self, model_key: str):
        state = self._state.get(model_key)
        if state:
            state.consecutive_errors += 1
            state.last_error_time = time.time()
            if state.consecutive_errors >= 3:
                state.available = False
                logger.warning("Model %s marked unavailable after 3 errors", model_key)

    def mark_success(self, model_key: str):
        state = self._state.get(model_key)
        if state:
            state.consecutive_errors = 0
            state.available = True

    @classmethod
    def from_config(cls, config: dict) -> "ModelRouter":
        providers_cfg = config.get("providers", {})
        tiers_cfg = config.get("tiers", {})

        configs: list[ModelConfig] = []
        for provider_name, pcfg in providers_cfg.items():
            models = pcfg.get("models", [pcfg.get("model", "default")])
            if isinstance(models, str):
                models = [models]
            for model_name in models:
                configs.append(ModelConfig(
                    provider=provider_name,
                    model_name=model_name,
                    api_key=pcfg.get("api_key", ""),
                    base_url=pcfg.get("base_url", ""),
                    tier=ModelTier.MEDIUM,
                ))

        router = cls(configs)

        for tier_name, tcfg in tiers_cfg.items():
            try:
                tier = ModelTier(tier_name)
            except ValueError:
                continue
            primary = tcfg.get("primary", "")
            fallback = tcfg.get("fallback", "")

            if primary:
                parts = primary.split(":", 1)
                if len(parts) == 2:
                    router.set_primary(tier, parts[0], parts[1])
                else:
                    router.set_primary(tier, "deepseek", primary)

            if fallback:
                parts = fallback.split(":", 1)
                if len(parts) == 2:
                    router.set_fallback(tier, parts[0], parts[1])
                else:
                    router.set_fallback(tier, "openai", fallback)

        return router


_router: Optional[ModelRouter] = None


def get_router() -> ModelRouter:
    global _router
    if _router is None:
        try:
            from config_deepseek import config as raw_config
        except ImportError:
            from ..config_deepseek import config as raw_config
        models_cfg = raw_config.get("models", {}) or {}
        _router = ModelRouter.from_config(models_cfg)
        logger.info("ModelRouter initialized with %d providers", len(_router.configs))
    return _router
