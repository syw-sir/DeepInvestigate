"""
网络搜索工具（可选）

默认禁用。开启需在 config.yaml 设置 tools.web_search.enabled=true 并填入 api_key。
当前为占位实现（不依赖任何具体搜索服务），便于上线后接入：
    - Tavily / Serper / Bing / DuckDuckGo HTML 等。
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

try:
    from config_deepseek import WEB_SEARCH_ENABLED, WEB_SEARCH_API_KEY
except ImportError:
    from ..config_deepseek import WEB_SEARCH_ENABLED, WEB_SEARCH_API_KEY  # type: ignore

logger = logging.getLogger(__name__)


@tool("web_search", parse_docstring=True)
def web_search(query: str, top_k: int = 5) -> str:
    """对外部互联网做关键词搜索，返回 top_k 条结果（默认禁用）。

    需在 config.yaml 启用 tools.web_search.enabled 并配置 api_key。
    当前调用环境若未启用会直接返回禁用提示。

    Args:
        query: 搜索关键词。
        top_k: 返回结果数，默认 5。

    Returns:
        JSON 字符串：{"results": [{"title": "...", "url": "...", "snippet": "..."}, ...]}
    """
    if not WEB_SEARCH_ENABLED:
        return json.dumps(
            {"error": "web_search is disabled in config"},
            ensure_ascii=False,
        )

    if not WEB_SEARCH_API_KEY:
        return json.dumps(
            {"error": "web_search api_key not configured"},
            ensure_ascii=False,
        )

    # TODO: 接入具体搜索服务，例如 Tavily：
    #
    # import httpx
    # r = httpx.post("https://api.tavily.com/search",
    #                json={"api_key": WEB_SEARCH_API_KEY, "query": query, "max_results": top_k},
    #                timeout=15)
    # data = r.json()
    # items = [{"title": x["title"], "url": x["url"], "snippet": x["content"]}
    #          for x in data.get("results", [])]
    # return json.dumps({"results": items}, ensure_ascii=False)

    return json.dumps(
        {"error": "web_search backend not implemented yet"},
        ensure_ascii=False,
    )
