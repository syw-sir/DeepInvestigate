"""
DeepInvestigate 工具集

所有工具基于 LangChain `@tool` 装饰器实现，可直接交给 LangGraph 的 ToolNode。

工具清单：
    - run_python       : Python 沙箱执行
    - read_file        : 读取 workspace 文件
    - write_file       : 写入 workspace 文件
    - query_logs       : 结构化日志查询
    - search_cve       : CVE 漏洞检索
    - rag_search       : RAG 知识库检索
    - recall_memory    : 长期记忆召回
    - web_search       : 网络搜索（可选）

通过 `get_all_tools()` 获取全部工具列表。
"""

from .registry import (
    get_all_tools,
    get_tool_schemas,
    get_tool_by_name,
    TOOL_REGISTRY,
)

__all__ = [
    "get_all_tools",
    "get_tool_schemas",
    "get_tool_by_name",
    "TOOL_REGISTRY",
]
