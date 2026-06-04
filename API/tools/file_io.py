"""
文件读写工具

所有路径强制限制在当前会话 workspace 内，禁止越权访问。
"""

from __future__ import annotations

import os
from pathlib import Path

from langchain_core.tools import tool

from .context import get_workspace_dir

# 单次读取最大字符数
MAX_READ_CHARS = 8000


def _safe_resolve(rel_path: str) -> Path:
    """把相对路径解析到 workspace 内，越界则抛 ValueError"""
    workspace = Path(get_workspace_dir()).resolve()
    target = (workspace / rel_path).resolve()
    try:
        target.relative_to(workspace)
    except ValueError:
        raise ValueError(
            f"Path '{rel_path}' is outside workspace, access denied"
        )
    return target


@tool("read_file", parse_docstring=True)
def read_file(path: str, max_chars: int = MAX_READ_CHARS) -> str:
    """读取 workspace 下的文本文件内容。

    路径必须是 workspace 内的相对路径。超过 max_chars 会截断返回。
    二进制文件请使用 run_python 处理。

    Args:
        path: 相对于 workspace 的文件路径，例如 "uploaded/log.txt"。
        max_chars: 最大读取字符数，默认 8000。

    Returns:
        文件文本内容，或错误说明。
    """
    try:
        fp = _safe_resolve(path)
        if not fp.exists():
            return f"[Error]: file not found: {path}"
        if not fp.is_file():
            return f"[Error]: not a file: {path}"

        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars + 1)

        if len(content) > max_chars:
            return content[:max_chars] + f"\n\n... [truncated, total > {max_chars} chars]"
        return content
    except Exception as e:
        return f"[Error]: {type(e).__name__}: {e}"


@tool("write_file", parse_docstring=True)
def write_file(path: str, content: str) -> str:
    """在 workspace 下写入文本文件（覆盖式）。

    路径必须是 workspace 内的相对路径。父目录不存在会自动创建。

    Args:
        path: 相对于 workspace 的文件路径，例如 "generated/report.md"。
        content: 要写入的文本内容。

    Returns:
        成功提示或错误说明。
    """
    try:
        fp = _safe_resolve(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(content)
        return f"[OK]: wrote {len(content)} chars to {path}"
    except Exception as e:
        return f"[Error]: {type(e).__name__}: {e}"


@tool("list_files", parse_docstring=True)
def list_files(subdir: str = "") -> str:
    """列出 workspace 下指定子目录的文件与子目录。

    Args:
        subdir: workspace 内的子目录相对路径，留空表示根目录。

    Returns:
        文件/目录清单（每行一项，目录后跟 "/"）。
    """
    try:
        target = _safe_resolve(subdir) if subdir else Path(get_workspace_dir()).resolve()
        if not target.exists():
            return f"[Error]: directory not found: {subdir or '.'}"
        if not target.is_dir():
            return f"[Error]: not a directory: {subdir or '.'}"

        items = []
        for entry in sorted(target.iterdir()):
            name = entry.name + ("/" if entry.is_dir() else "")
            items.append(name)
        if not items:
            return "[Empty Directory]"
        return "\n".join(items)
    except Exception as e:
        return f"[Error]: {type(e).__name__}: {e}"
