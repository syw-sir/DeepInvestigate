"""
评估运行器

用法：
    cd <project root>
    python -m eval.run_eval --dataset eval/dataset/attack_logs_eval.jsonl

可选参数：
    --limit N         只跑前 N 条
    --output PATH     报告输出路径（默认 eval/reports/report_<ts>.json）
    --concurrency K   并发数（默认 1，串行）

工作流：
    1. 读取 jsonl 数据集
    2. 逐条调用 agent.run_agent_sync()
    3. 收集 final_answer / called_tools / iterations / latency
    4. 用 eval.metrics 计算 per-task 与 aggregate 指标
    5. 输出 JSON 报告 + 终端表格摘要
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "API"))

from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402

from agent import get_graph, new_initial_state  # noqa: E402
from tools.context import set_context, ToolContext  # noqa: E402

from .metrics import compute_per_task, aggregate, TaskResult  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("eval")


def load_dataset(path: Path) -> List[Dict[str, Any]]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            items.append(json.loads(line))
    return items


def _extract_tools_and_iters(messages: List[Any]) -> tuple[List[str], int]:
    """从 messages 历史中抽取被调用的工具名 + investigator 迭代次数"""
    called = []
    iters = 0
    for m in messages or []:
        if isinstance(m, AIMessage):
            if getattr(m, "name", "") == "investigator":
                iters += 1
            for tc in getattr(m, "tool_calls", None) or []:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                if name:
                    called.append(name)
    return called, iters


async def run_one(task: Dict[str, Any]) -> TaskResult:
    """跑单个任务"""
    task_id = task["task_id"]
    user_query = task["input"]

    ws = tempfile.mkdtemp(prefix=f"dii_eval_{task_id}_")
    thread_id = f"eval_{task_id}_{int(time.time())}"
    user_id = "eval_runner"

    set_context(ToolContext(
        thread_id=thread_id,
        user_id=user_id,
        workspace_dir=ws,
    ))

    init_state = new_initial_state(
        user_query=user_query,
        thread_id=thread_id,
        user_id=user_id,
        workspace_dir=ws,
        max_iterations=10,
    )

    graph = get_graph()
    error = None
    final_answer = ""
    called_tools: List[str] = []
    iterations = 0
    t0 = time.time()

    try:
        final_state = await asyncio.wait_for(
            graph.ainvoke(init_state, config={"recursion_limit": 30}),
            timeout=300,
        )
        final_answer = final_state.get("final_answer") or ""
        called_tools, iterations = _extract_tools_and_iters(final_state.get("messages") or [])
    except asyncio.TimeoutError:
        error = "TIMEOUT (>300s)"
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        logger.exception("Task %s failed", task_id)

    latency = time.time() - t0
    result = compute_per_task(
        task=task,
        final_answer=final_answer,
        called_tools=called_tools,
        iterations=iterations,
        latency_seconds=latency,
        error=error,
    )
    # v3.0: capture additional fields from final state
    if final_state:
        result.critic_score = final_state.get("critic_score") or 0.0
        result.fallback_triggered = final_state.get("fallback_triggered") or False
        result.guardrail_triggered = final_state.get("guardrail_triggered") or False
    return result


async def run_all(tasks: List[Dict[str, Any]], concurrency: int = 1) -> List[TaskResult]:
    results: List[TaskResult] = []
    sem = asyncio.Semaphore(concurrency)

    async def guarded(t):
        async with sem:
            r = await run_one(t)
            tick = "✅" if r.success else ("⚠️" if r.error else "❌")
            print(
                f"  {tick} {r.task_id:6s} [{r.difficulty:6s}] "
                f"cov={r.keyword_coverage:.2f} tool={r.tool_call_accuracy:.2f} "
                f"iter={r.iterations} {r.latency_seconds:.1f}s"
                + (f"  ERR: {r.error}" if r.error else "")
            )
            return r

    coros = [guarded(t) for t in tasks]
    for fut in asyncio.as_completed(coros):
        r = await fut
        results.append(r)

    results.sort(key=lambda x: x.task_id)
    return results


def _format_summary_table(summary: Dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("📊 Evaluation Summary")
    lines.append("=" * 60)
    lines.append(f"  Total tasks            : {summary.get('total_tasks')}")
    lines.append(f"  Success                : {summary.get('success_count')} / {summary.get('total_tasks')}")
    lines.append(f"  Task Success Rate      : {summary.get('task_success_rate'):.1%}")
    lines.append(f"  Avg Keyword Coverage   : {summary.get('avg_keyword_coverage'):.1%}")
    lines.append(f"  Avg Tool Call Accuracy : {summary.get('avg_tool_call_accuracy'):.1%}")
    lines.append(f"  Avg Iterations         : {summary.get('avg_iterations')}")
    lines.append(f"  Avg Latency (s)        : {summary.get('avg_latency_seconds')}")
    lines.append(f"  Hallucination Rate     : {summary.get('hallucination_rate'):.1%}")
    lines.append(f"  Error Rate             : {summary.get('error_rate'):.1%}")
    lines.append(f"  Avg Critic Score       : {summary.get('avg_critic_score', 0):.1f}")
    lines.append(f"  Fallback Rate          : {summary.get('fallback_rate', 0):.1%}")
    lines.append(f"  Avg Cost per Task      : ${summary.get('avg_cost_per_task', 0):.4f}")
    lines.append(f"  Total Cost             : ${summary.get('total_cost', 0):.4f}")
    lines.append("")
    lines.append("  Success by Difficulty:")
    for d, v in (summary.get("success_by_difficulty") or {}).items():
        lines.append(f"    - {d:6s}: {v['success']}/{v['total']}  ({v['rate']:.1%})")
    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Run DeepInvestigate evaluation")
    ap.add_argument("--dataset", type=str, default="eval/dataset/attack_logs_eval.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条，0=全部")
    ap.add_argument("--output", type=str, default="")
    ap.add_argument("--concurrency", type=int, default=1)
    args = ap.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        dataset_path = ROOT / args.dataset
    if not dataset_path.exists():
        print(f"❌ Dataset not found: {args.dataset}")
        sys.exit(1)

    tasks = load_dataset(dataset_path)
    if args.limit > 0:
        tasks = tasks[: args.limit]

    print(f"\n🚀 Running eval on {len(tasks)} tasks (concurrency={args.concurrency})\n")

    t0 = time.time()
    results = asyncio.run(run_all(tasks, concurrency=args.concurrency))
    total_dt = time.time() - t0

    summary = aggregate(results)
    summary["wall_clock_seconds"] = round(total_dt, 2)
    summary["timestamp"] = datetime.now().isoformat(timespec="seconds")
    summary["dataset"] = str(dataset_path)

    print()
    print(_format_summary_table(summary))

    # 输出 JSON 报告
    out_path = args.output
    if not out_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = ROOT / "eval" / "reports" / f"report_{ts}.json"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "summary": summary,
        "results": [r.to_dict() for r in results],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n📄 Report written to: {out_path}")


if __name__ == "__main__":
    main()
