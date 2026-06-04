"""
评估指标

提供 6 类核心指标：
    1. keyword_coverage      : 期望关键词命中率（最终回答中包含多少）
    2. tool_call_accuracy    : 期望工具是否被调用
    3. task_success          : 综合判定（关键词全部命中 + 无 fatal 错误）
    4. avg_iterations        : 平均推理轮数
    5. avg_latency_seconds   : 平均完成时间
    6. hallucination_flag    : 是否包含「不知道/无法回答」的明显幻觉/拒答信号

用法（独立可调）：
    from eval.metrics import compute_per_task, aggregate
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


HALLUCINATION_PATTERNS = [
    r"我无法",
    r"作为一个 ?AI",
    r"无法 ?提供",
    r"无法 ?判断",
    r"我不 ?清楚",
]


@dataclass
class TaskResult:
    task_id: str
    category: str
    difficulty: str
    success: bool = False
    keyword_coverage: float = 0.0          # 0~1
    matched_keywords: List[str] = field(default_factory=list)
    missed_keywords: List[str] = field(default_factory=list)
    tool_call_accuracy: float = 0.0        # 0~1
    called_tools: List[str] = field(default_factory=list)
    iterations: int = 0
    latency_seconds: float = 0.0
    hallucination: bool = False
    error: Optional[str] = None
    final_answer_preview: str = ""
    # v3.0 新增
    critic_score: float = 0.0
    fallback_triggered: bool = False
    guardrail_triggered: bool = False
    cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _norm(text: str) -> str:
    return (text or "").lower().replace(" ", "")


def keyword_coverage(answer: str, expected: List[str]) -> tuple[float, List[str], List[str]]:
    if not expected:
        return 1.0, [], []
    norm_ans = _norm(answer)
    matched, missed = [], []
    for kw in expected:
        if _norm(kw) in norm_ans:
            matched.append(kw)
        else:
            missed.append(kw)
    return len(matched) / len(expected), matched, missed


def tool_call_accuracy(called: List[str], expected: List[str]) -> float:
    """期望工具被调用的比例（顺序不敏感）"""
    if not expected:
        return 1.0
    called_set = set(called or [])
    hit = sum(1 for t in expected if t in called_set)
    return hit / len(expected)


def detect_hallucination(answer: str) -> bool:
    text = answer or ""
    return any(re.search(p, text) for p in HALLUCINATION_PATTERNS)


def compute_per_task(
    *,
    task: Dict[str, Any],
    final_answer: str,
    called_tools: List[str],
    iterations: int,
    latency_seconds: float,
    error: Optional[str] = None,
) -> TaskResult:
    expected_kw = task.get("expected_keywords") or []
    expected_tools = task.get("expected_tools") or []

    cov, matched, missed = keyword_coverage(final_answer, expected_kw)
    t_acc = tool_call_accuracy(called_tools, expected_tools)
    halluc = detect_hallucination(final_answer)

    # 任务成功定义：关键词覆盖 ≥ 0.6 且 无 fatal 错误 且 无幻觉
    success = (cov >= 0.6) and (error is None) and (not halluc)

    return TaskResult(
        task_id=task.get("task_id", ""),
        category=task.get("category", ""),
        difficulty=task.get("difficulty", ""),
        success=success,
        keyword_coverage=round(cov, 3),
        matched_keywords=matched,
        missed_keywords=missed,
        tool_call_accuracy=round(t_acc, 3),
        called_tools=called_tools,
        iterations=iterations,
        latency_seconds=round(latency_seconds, 2),
        hallucination=halluc,
        error=error,
        final_answer_preview=(final_answer or "")[:300],
    )


def aggregate(results: List[TaskResult]) -> Dict[str, Any]:
    if not results:
        return {}
    n = len(results)
    succ = sum(1 for r in results if r.success)

    def avg(vals):
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    by_diff: Dict[str, Dict[str, Any]] = {}
    for r in results:
        d = r.difficulty or "unknown"
        by_diff.setdefault(d, {"total": 0, "success": 0})
        by_diff[d]["total"] += 1
        if r.success:
            by_diff[d]["success"] += 1
    for d, v in by_diff.items():
        v["rate"] = round(v["success"] / v["total"], 3)

    return {
        "total_tasks": n,
        "success_count": succ,
        "task_success_rate": round(succ / n, 3),
        "avg_keyword_coverage": avg([r.keyword_coverage for r in results]),
        "avg_tool_call_accuracy": avg([r.tool_call_accuracy for r in results]),
        "avg_iterations": avg([r.iterations for r in results]),
        "avg_latency_seconds": avg([r.latency_seconds for r in results]),
        "hallucination_rate": round(sum(1 for r in results if r.hallucination) / n, 3),
        "error_rate": round(sum(1 for r in results if r.error) / n, 3),
        "success_by_difficulty": by_diff,
        # v3.0 新增
        "avg_critic_score": avg([r.critic_score for r in results if r.critic_score > 0]),
        "fallback_rate": round(sum(1 for r in results if r.fallback_triggered) / n, 3),
        "guardrail_trigger_rate": round(sum(1 for r in results if r.guardrail_triggered) / n, 3),
        "avg_cost_per_task": avg([r.cost_usd for r in results if r.cost_usd > 0]),
        "total_cost": round(sum(r.cost_usd for r in results), 6),
    }
