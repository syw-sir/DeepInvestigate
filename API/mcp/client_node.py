"""
MCP Client 节点 — 从 MCP Server 发现工具并封装为 LangChain Tool

用于 LangGraph 中替代直连 ToolNode，通过 MCP 协议调用工具。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)


class MCPToolNode:
    """MCP Client 工具节点"""

    def __init__(self, server_command: list[str] | None = None):
        self.server_command = server_command or ["python", "-m", "API.mcp.server"]
        self._tools: list[StructuredTool] = []
        self._session = None
        self._read = None
        self._write = None

    async def discover(self) -> list[StructuredTool]:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            logger.error("mcp package not installed. Run: pip install mcp")
            return []

        params = StdioServerParameters(
            command=self.server_command[0],
            args=self.server_command[1:],
        )

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                self._tools = []
                for t in tools_result.tools:
                    tool = self._to_langchain_tool(t, session)
                    self._tools.append(tool)
                logger.info("Discovered %d tools from MCP server", len(self._tools))

        return self._tools

    def _to_langchain_tool(self, mcp_tool, session) -> StructuredTool:
        async def _call(**kwargs):
            result = await session.call_tool(mcp_tool.name, arguments=kwargs)
            if result.content:
                return result.content[0].text
            return str(result)

        return StructuredTool(
            name=mcp_tool.name,
            description=mcp_tool.description or "",
            coroutine=_call,
        )

    def get_tools(self) -> list[StructuredTool]:
        return self._tools


async def _discover_and_cache():
    node = MCPToolNode()
    tools = await node.discover()
    return tools


mcp_tool_executor = None

try:
    _tools = asyncio.run(_discover_and_cache())
    if _tools:
        from langgraph.prebuilt import ToolNode
        mcp_tool_executor = ToolNode(_tools)
        logger.info("MCP ToolNode initialized with %d tools", len(_tools))
except Exception as e:
    logger.warning("Failed to initialize MCP ToolNode: %s", e)
