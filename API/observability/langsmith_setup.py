"""
LangSmith 集成

通过设置环境变量启用 LangChain/LangGraph 全链路追踪。
启用后，每个节点的输入输出、LLM 调用、工具调用都会自动上报到 LangSmith。

启用方式（config.yaml）：
    langsmith:
      enabled: true
      project: "DeepInvestigate-Prod"
      api_key: "ls__..."
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

try:
    from config_deepseek import (
        LANGSMITH_ENABLED,
        LANGSMITH_PROJECT,
        LANGSMITH_API_KEY,
        LANGSMITH_ENDPOINT,
    )
except ImportError:
    from ..config_deepseek import (  # type: ignore
        LANGSMITH_ENABLED,
        LANGSMITH_PROJECT,
        LANGSMITH_API_KEY,
        LANGSMITH_ENDPOINT,
    )

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def setup_langsmith() -> bool:
    """初始化 LangSmith 追踪（幂等）

    Returns:
        True 表示已启用，False 表示未启用/配置缺失
    """
    if not LANGSMITH_ENABLED:
        logger.info("LangSmith disabled in config")
        return False

    if not LANGSMITH_API_KEY:
        logger.warning(
            "LangSmith enabled but api_key missing. "
            "Set langsmith.api_key in config.yaml"
        )
        return False

    # LangChain v2 追踪开关
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = LANGSMITH_PROJECT
    os.environ["LANGCHAIN_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGCHAIN_ENDPOINT"] = LANGSMITH_ENDPOINT

    # 兼容 langsmith SDK
    os.environ["LANGSMITH_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGSMITH_PROJECT"] = LANGSMITH_PROJECT

    logger.info(
        "✅ LangSmith tracing enabled: project='%s' endpoint='%s'",
        LANGSMITH_PROJECT,
        LANGSMITH_ENDPOINT,
    )
    return True


def is_langsmith_enabled() -> bool:
    """检查是否已经启用 LangSmith"""
    return os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"


def get_trace_url(run_id: str | None = None) -> str | None:
    """生成 trace URL（便于日志中打印）"""
    if not is_langsmith_enabled():
        return None
    base = "https://smith.langchain.com"
    if run_id:
        return f"{base}/o/-/projects/p/{LANGSMITH_PROJECT}/r/{run_id}"
    return f"{base}/o/-/projects/p/{LANGSMITH_PROJECT}"
