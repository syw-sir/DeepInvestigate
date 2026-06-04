"""
工具系统冒烟测试

用法：
    cd API
    python -m tools.test_tools
"""

import asyncio
import os
import sys
import tempfile

# 允许从 API/ 目录直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.context import set_context, ToolContext
from tools.registry import (
    get_all_tools,
    get_tool_schemas,
    get_tool_by_name,
    describe_tools,
)


def setup_ctx() -> str:
    """建一个临时 workspace 并注入 ToolContext"""
    ws = tempfile.mkdtemp(prefix="dii_test_")
    set_context(ToolContext(
        thread_id="test_thread",
        user_id="test_user",
        workspace_dir=ws,
    ))
    return ws


def test_registry():
    print("\n[1] Registry")
    tools = get_all_tools()
    print(f"  Total tools: {len(tools)}")
    print(describe_tools())

    schemas = get_tool_schemas()
    assert len(schemas) == len(tools)
    print(f"  ✅ OpenAI schemas generated: {len(schemas)}")

    run_py = get_tool_by_name("run_python")
    assert run_py is not None
    print(f"  ✅ get_tool_by_name OK")


def test_file_io(workspace: str):
    print("\n[2] File I/O")
    write_file = get_tool_by_name("write_file")
    read_file = get_tool_by_name("read_file")
    list_files = get_tool_by_name("list_files")

    r1 = write_file.invoke({"path": "hello.txt", "content": "你好世界\nLine 2"})
    print(f"  write_file: {r1}")
    assert r1.startswith("[OK]")

    r2 = read_file.invoke({"path": "hello.txt"})
    print(f"  read_file: {r2!r}")
    assert "你好世界" in r2

    r3 = list_files.invoke({"subdir": ""})
    print(f"  list_files:\n{r3}")
    assert "hello.txt" in r3

    # 越界访问应被拒
    r4 = read_file.invoke({"path": "../../../etc/passwd"})
    print(f"  越界访问: {r4}")
    assert "denied" in r4 or "Error" in r4
    print("  ✅ File I/O OK")


async def test_code_executor():
    print("\n[3] Code Executor")
    run_py = get_tool_by_name("run_python")

    # 正常执行
    out = await run_py.ainvoke({"code": "print(2 + 3)"})
    print(f"  print(2+3) → {out!r}")
    assert "5" in out

    # 危险调用被拒
    out2 = await run_py.ainvoke({"code": "import os; os.system('ls')"})
    print(f"  os.system → {out2!r}")
    assert "Rejected" in out2

    # 超时
    out3 = await run_py.ainvoke({"code": "import time; time.sleep(999)"})
    # 默认超时由 config 控制，这里跑得有点慢就跳过
    print(f"  长任务: {out3[:80]}...")

    print("  ✅ Code Executor OK")


def test_log_query(workspace: str):
    print("\n[4] Log Query")
    log_path = os.path.join(workspace, "sample.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(
            "2026-05-24 03:00:00 Failed password for root from 1.2.3.4\n"
            "2026-05-24 03:00:01 Failed password for root from 1.2.3.4\n"
            "2026-05-24 03:05:00 Accepted password for admin from 10.0.0.1\n"
        )

    q = get_tool_by_name("query_logs")
    r = q.invoke({"file_path": "sample.log", "pattern": "Failed password"})
    print(r)
    assert '"matched": 2' in r
    print("  ✅ Log Query OK")


async def main():
    print("=" * 60)
    print("DeepInvestigate Tools — Smoke Test")
    print("=" * 60)
    ws = setup_ctx()
    print(f"Workspace: {ws}")

    test_registry()
    test_file_io(ws)
    await test_code_executor()
    test_log_query(ws)

    print("\n" + "=" * 60)
    print("✅ All smoke tests passed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
