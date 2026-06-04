"""
MCP Server — 将 9 个工具暴露为 MCP 标准协议

启动方式：
    python -m API.mcp.server --transport stdio
    python -m API.mcp.server --transport sse --port 8202
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def create_mcp_server():
    """创建并返回 MCP Server 实例"""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        logger.error("mcp package not installed. Run: pip install mcp")
        raise

    mcp = FastMCP("DeepInvestigate Tools")

    @mcp.tool()
    def run_python(code: str) -> str:
        """在沙箱中执行 Python 代码并返回输出"""
        from tools.code_executor import run_python as _run
        result = _run.invoke({"code": code})
        return str(result)

    @mcp.tool()
    def query_logs(query: str, time_range: str = "24h") -> str:
        """结构化日志查询"""
        from tools.log_query import query_logs as _query
        result = _query.invoke({"query": query, "time_range": time_range})
        return str(result)

    @mcp.tool()
    def search_cve(cve_id: str = "", keyword: str = "") -> str:
        """CVE 漏洞信息查询"""
        from tools.cve_search import search_cve as _search
        result = _search.invoke({"cve_id": cve_id, "keyword": keyword})
        return str(result)

    @mcp.tool()
    def rag_search(query: str, top_k: int = 5) -> str:
        """知识库检索（MITRE ATT&CK / CVE）"""
        from tools.rag_search import rag_search as _search
        result = _search.invoke({"query": query, "top_k": top_k})
        return str(result)

    @mcp.tool()
    def recall_memory(query: str, mem_type: str = "episodic") -> str:
        """长期记忆召回"""
        from tools.recall_memory import recall_memory as _recall
        result = _recall.invoke({"query": query, "mem_type": mem_type})
        return str(result)

    @mcp.tool()
    def web_search(query: str) -> str:
        """网络搜索"""
        from tools.web_search import web_search as _search
        result = _search.invoke({"query": query})
        return str(result)

    @mcp.tool()
    def read_file(path: str) -> str:
        """读取 workspace 文件"""
        from tools.file_io import read_file as _read
        result = _read.invoke({"path": path})
        return str(result)

    @mcp.tool()
    def write_file(path: str, content: str) -> str:
        """写入文件"""
        from tools.file_io import write_file as _write
        result = _write.invoke({"path": path, "content": content})
        return str(result)

    @mcp.tool()
    def list_files(path: str = ".") -> str:
        """列出目录文件"""
        from tools.file_io import list_files as _list
        result = _list.invoke({"path": path})
        return str(result)

    return mcp


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    transport = "stdio"
    port = 8202
    for i, arg in enumerate(sys.argv):
        if arg == "--transport" and i + 1 < len(sys.argv):
            transport = sys.argv[i + 1]
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])

    mcp = create_mcp_server()
    if transport == "sse":
        mcp.run(transport="sse", port=port)
    else:
        mcp.run(transport="stdio")
