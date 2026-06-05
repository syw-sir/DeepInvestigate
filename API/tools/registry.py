"""
工具注册表

统一收口所有 @tool，提供：
    - get_all_tools()    : 返回 list[StructuredTool]，可直接喂 LangGraph ToolNode
    - get_tool_schemas() : 返回 OpenAI Tool Schema 列表，可直接喂 OpenAI SDK
    - get_tool_by_name() : 按名查找
    - TOOL_REGISTRY      : {name: tool} 字典
"""

from __future__ import annotations

from typing import Dict, List, Optional

from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

# 各工具模块
from .code_executor import run_python
from .file_io import read_file, write_file, list_files
from .rag_search import rag_search
from .recall_memory import recall_memory
from .log_query import query_logs
from .cve_search import search_cve
from .web_search import web_search

# v4.0 取证工具
from .forensics.process_scanner import scan_processes
from .forensics.network_monitor import check_network
from .forensics.system_info import collect_system_info
from .forensics.defender_checker import check_defender_logs
from .forensics.login_auditor import audit_logins
from .forensics.startup_checker import check_startup
from .forensics.registry_scanner import scan_registry
from .forensics.file_integrity import check_file_integrity


# ----- 全量工具清单（顺序即是给 LLM 看到的顺序） -----
_ALL_TOOLS: List[BaseTool] = [
    run_python,
    read_file,
    write_file,
    list_files,
    query_logs,
    search_cve,
    rag_search,
    recall_memory,
    web_search,
    # v4.0 取证工具
    scan_processes,
    check_network,
    collect_system_info,
    check_defender_logs,
    audit_logins,
    check_startup,
    scan_registry,
    check_file_integrity,
]


# ----- 注册表 -----
TOOL_REGISTRY: Dict[str, BaseTool] = {t.name: t for t in _ALL_TOOLS}


def get_all_tools() -> List[BaseTool]:
    """返回全部已注册工具（list[StructuredTool]）"""
    return list(_ALL_TOOLS)


def get_tool_by_name(name: str) -> Optional[BaseTool]:
    """按名称取工具"""
    return TOOL_REGISTRY.get(name)


def get_tool_schemas() -> List[dict]:
    """返回 OpenAI Function Calling 格式的工具 schema 列表"""
    return [convert_to_openai_tool(t) for t in _ALL_TOOLS]


def describe_tools() -> str:
    """生成一段人类可读的工具清单（用于调试或 Prompt 注入）"""
    lines = []
    for t in _ALL_TOOLS:
        desc = (t.description or "").strip().split("\n")[0]
        lines.append(f"- {t.name}: {desc}")
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== Registered Tools ===")
    print(describe_tools())
    print("\n=== OpenAI Schemas Count ===", len(get_tool_schemas()))
