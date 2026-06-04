"""
日志结构化查询工具

支持对 workspace 内的常见日志文件（auth.log / nginx access / syslog 等）
做结构化提取：grep、时间范围、字段聚合。

设计目标：让 Agent 不用每次都写一段 pandas 代码做 grep。
当前实现：用 Python 行扫描；后续可换成 ClickHouse / Loki 等。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool

from .context import get_workspace_dir
from .file_io import _safe_resolve  # 复用路径安全检查

logger = logging.getLogger(__name__)

MAX_MATCH_LINES = 200      # 单次最多返回行数
MAX_SCAN_LINES = 200_000   # 单次最多扫描行数


def _try_parse_time(line: str) -> Optional[datetime]:
    """从常见日志格式里粗略提取时间戳"""
    # 常见模式：syslog "May 24 03:14:15"、ISO "2026-05-24 03:14:15"、nginx "[24/May/2026:03:14:15"
    patterns = [
        ("%Y-%m-%d %H:%M:%S", r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"),
        ("%Y-%m-%dT%H:%M:%S", r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"),
        ("%b %d %H:%M:%S",    r"([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"),
        ("%d/%b/%Y:%H:%M:%S", r"(\d{2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2})"),
    ]
    for fmt, pat in patterns:
        m = re.search(pat, line)
        if m:
            try:
                return datetime.strptime(m.group(1), fmt)
            except Exception:
                continue
    return None


@tool("query_logs", parse_docstring=True)
def query_logs(
    file_path: str,
    pattern: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    max_lines: int = 100,
) -> str:
    """对 workspace 内的日志文件做结构化查询。

    可同时使用正则匹配 + 时间范围过滤。返回匹配行（最多 max_lines 条）。

    Args:
        file_path: 相对于 workspace 的日志文件路径。
        pattern: 可选正则表达式，匹配整行。
        start_time: 可选起始时间，ISO 格式，例如 "2026-05-24 00:00:00"。
        end_time: 可选结束时间，ISO 格式。
        max_lines: 最多返回多少匹配行，默认 100，上限 200。

    Returns:
        JSON 字符串：{"matched": N, "lines": [...], "scanned": M, "truncated": bool}
    """
    try:
        fp = _safe_resolve(file_path)
        if not fp.exists() or not fp.is_file():
            return json.dumps({"error": f"file not found: {file_path}"}, ensure_ascii=False)

        regex = re.compile(pattern) if pattern else None
        st = datetime.fromisoformat(start_time) if start_time else None
        et = datetime.fromisoformat(end_time) if end_time else None
        limit = min(max_lines, MAX_MATCH_LINES)

        matched_lines = []
        scanned = 0
        truncated_scan = False

        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                scanned += 1
                if scanned > MAX_SCAN_LINES:
                    truncated_scan = True
                    break

                if regex and not regex.search(line):
                    continue

                if st or et:
                    ts = _try_parse_time(line)
                    if ts is None:
                        # 没解析到时间就跳过时间过滤
                        pass
                    else:
                        if st and ts < st:
                            continue
                        if et and ts > et:
                            continue

                matched_lines.append(line.rstrip("\n"))
                if len(matched_lines) >= limit:
                    break

        return json.dumps({
            "matched": len(matched_lines),
            "scanned": scanned,
            "truncated": truncated_scan or len(matched_lines) >= limit,
            "lines": matched_lines,
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.exception("query_logs failed")
        return json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
