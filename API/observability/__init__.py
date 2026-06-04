"""
DeepInvestigate 可观测性模块

- langsmith_setup: 全链路 trace（LangSmith）
"""

from .langsmith_setup import setup_langsmith, is_langsmith_enabled

__all__ = ["setup_langsmith", "is_langsmith_enabled"]
