"""
Agent 端到端冒烟测试

用法：
    cd API
    python -m agent.test_agent

注意：
    - 需要 DeepSeek API Key 有效（config.yaml 已配）
    - Redis / Chroma 未启动也能跑（memory/RAG 节点会降级）
"""

import asyncio
import logging
import os
import sys
import tempfile

# 让 module 能从 API/ 目录直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import run_agent_sync, get_graph, new_initial_state, stream_agent_as_openai_sse
from tools.context import set_context, ToolContext

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("test_agent")


def setup_ctx() -> str:
    ws = tempfile.mkdtemp(prefix="dii_agent_test_")
    set_context(ToolContext(
        thread_id="test_thread_001",
        user_id="test_user",
        workspace_dir=ws,
    ))
    # 准备一个测试日志文件
    log_path = os.path.join(ws, "auth.log")
    with open(log_path, "w", encoding="utf-8") as f:
        for _ in range(15):
            f.write("2026-05-24 03:00:00 Failed password for root from 1.2.3.4 port 22 ssh2\n")
        f.write("2026-05-24 03:05:00 Accepted password for admin from 10.0.0.1\n")
        for _ in range(8):
            f.write("2026-05-24 03:10:00 Failed password for root from 5.6.7.8 port 22 ssh2\n")
    return ws


async def test_graph_structure():
    print("\n[1] Graph structure check")
    g = await get_graph()
    nodes = list(g.get_graph().nodes)
    print(f"  Nodes: {nodes}")
    expected = {"retrieve_memory", "retrieve_knowledge", "planner",
                "investigator", "tool_executor", "reporter", "update_memory"}
    missing = expected - set(nodes)
    assert not missing, f"missing nodes: {missing}"
    print("  ✅ All expected nodes present")


async def test_sync_run(workspace: str):
    print("\n[2] Sync end-to-end run (this calls DeepSeek API)")
    query = "请读取 auth.log 文件，分析是否存在 SSH 暴力破解，给出来源 IP 与建议"
    state = await run_agent_sync(
        user_query=query,
        thread_id="test_thread_001",
        user_id="test_user",
        workspace_dir=workspace,
        max_iterations=10,
    )
    final = state.get("final_answer") or ""
    print("---- Final Answer (head 500) ----")
    print(final[:500])
    print("...")
    assert final, "no final answer"
    print(f"  ✅ Final answer generated ({len(final)} chars)")


async def test_streaming(workspace: str):
    print("\n[3] Streaming run (OpenAI SSE)")
    init = new_initial_state(
        user_query="列出 workspace 下的文件",
        thread_id="test_stream",
        user_id="test_user",
        workspace_dir=workspace,
        max_iterations=5,
    )
    g = await get_graph()
    n_chunks = 0
    async for chunk in stream_agent_as_openai_sse(g, init, model="deepseek-chat"):
        n_chunks += 1
        if n_chunks <= 5:
            print(f"  chunk[{n_chunks}]: {chunk[:120].rstrip()}")
    print(f"  ✅ Received {n_chunks} SSE chunks")


async def main():
    print("=" * 60)
    print("DeepInvestigate Agent — End-to-End Smoke Test")
    print("=" * 60)
    ws = setup_ctx()
    print(f"Workspace: {ws}")

    await test_graph_structure()
    await test_sync_run(ws)
    await test_streaming(ws)

    print("\n" + "=" * 60)
    print("✅ Agent smoke tests passed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
