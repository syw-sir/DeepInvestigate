"""
并行调查协调器

支持 Planner 将独立子任务分发给多个 Investigator 并行执行。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ParallelCoordinator:
    """多 Investigator 并行调查协调器"""

    def __init__(self, max_workers: int = 3):
        self.max_workers = max_workers

    async def dispatch(
        self,
        tasks: list[dict],
        graph,
        base_state: dict,
    ) -> list[dict]:
        sem = asyncio.Semaphore(self.max_workers)

        async def run_subtask(task: dict) -> dict:
            async with sem:
                sub_state = {**base_state, "user_query": task.get("description", "")}
                try:
                    result = await graph.ainvoke(sub_state)
                    return {
                        "task_id": task.get("id", ""),
                        "result": result.get("final_answer", ""),
                        "success": True,
                    }
                except Exception as e:
                    logger.warning("Subtask %s failed: %s", task.get("id"), e)
                    return {
                        "task_id": task.get("id", ""),
                        "result": str(e),
                        "success": False,
                    }

        results = await asyncio.gather(*[run_subtask(t) for t in tasks])
        return list(results)

    @staticmethod
    def extract_parallel_tasks(plan: list[str]) -> list[dict] | None:
        """从 Planner 的 plan 中提取 [PARALLEL] 标记的子任务"""
        if not plan:
            return None

        in_parallel = False
        tasks = []
        for i, step in enumerate(plan):
            step = step.strip()
            if step.upper() == "[PARALLEL]":
                in_parallel = True
                continue
            if step.upper() == "[/PARALLEL]":
                in_parallel = False
                continue
            if in_parallel:
                tasks.append({"id": f"sub_{i}", "description": step})

        return tasks if tasks else None
