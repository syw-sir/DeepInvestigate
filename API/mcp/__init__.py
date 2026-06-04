"""
DeepInvestigate v3.0 MCP 集成模块

提供 MCP Server（暴露工具）和 MCP Client 节点（接入 LangGraph）。
"""

from .server import create_mcp_server
from .client_node import MCPToolNode

__all__ = ["create_mcp_server", "MCPToolNode"]
