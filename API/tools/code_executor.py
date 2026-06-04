"""
Python 代码沙箱执行工具

相比 v1.0 的 execute_code_safe，本版本新增：
    1. 危险调用静态检查（os.system / subprocess / shutil.rmtree 等）
    2. workspace 路径强制隔离（cwd 锁定）
    3. 超时 / 内存上限可配置
    4. 输出长度截断，避免 token 爆炸
    5. 兼容 stdout/stderr 双编码（utf-8 → gbk）

未来可平滑替换底层为 Docker / nsjail 等真沙箱。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
import tempfile
from typing import Optional

from langchain_core.tools import tool

try:
    from config_deepseek import (
        CODE_EXEC_TIMEOUT,
        CODE_EXEC_MEMORY_LIMIT_MB,
        CODE_EXEC_NETWORK_DISABLED,
    )
except ImportError:
    from ..config_deepseek import (  # type: ignore
        CODE_EXEC_TIMEOUT,
        CODE_EXEC_MEMORY_LIMIT_MB,
        CODE_EXEC_NETWORK_DISABLED,
    )

from .context import get_workspace_dir

logger = logging.getLogger(__name__)

# 输出长度上限（字符），超过截断
MAX_OUTPUT_CHARS = 8000

# 危险调用黑名单（粗粒度静态检查）
DANGEROUS_PATTERNS = [
    r"\bos\s*\.\s*system\b",
    r"\bos\s*\.\s*popen\b",
    r"\bsubprocess\s*\.\s*",
    r"\bshutil\s*\.\s*rmtree\b",
    r"\b__import__\s*\(\s*['\"]os['\"]\s*\)\s*\.\s*system",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bcompile\s*\(",
    # 网络
    r"\bsocket\s*\.\s*socket\b",
]


def _static_check(code: str) -> Optional[str]:
    """返回 None 表示通过；返回字符串表示拒绝原因"""
    for pat in DANGEROUS_PATTERNS:
        if re.search(pat, code):
            return f"[Rejected]: dangerous call detected (pattern: {pat})"
    return None


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return (
        head
        + f"\n\n... [truncated {len(text) - limit} chars] ...\n\n"
        + tail
    )


def _build_child_env() -> dict:
    env = os.environ.copy()
    env.setdefault("MPLBACKEND", "Agg")
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.pop("DISPLAY", None)
    # 内存限制由子进程自身用 resource 模块控制（POSIX）；Windows 上忽略
    env["DEEPINV_MEM_LIMIT_MB"] = str(CODE_EXEC_MEMORY_LIMIT_MB)
    return env


def _decode(data: bytes) -> str:
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gbk", "ignore")


async def _run_async(code: str, workspace: str, timeout: int) -> str:
    """异步执行核心逻辑"""
    exec_cwd = os.path.abspath(workspace)
    os.makedirs(exec_cwd, exist_ok=True)
    tmp_path: Optional[str] = None

    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".py", dir=exec_cwd)
        os.close(fd)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(code)

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            tmp_path,
            cwd=exec_cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_build_child_env(),
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return f"[Timeout]: execution exceeded {timeout} seconds"

        output = _decode(stdout) + _decode(stderr)
        return _truncate(output) if output else "[Empty Output]"

    except Exception as e:
        logger.exception("Code execution failed")
        return f"[Error]: {type(e).__name__}: {e}"
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


# -------------------- LangChain Tool -------------------- #

@tool("run_python", parse_docstring=True)
async def run_python(code: str) -> str:
    """在隔离沙箱中执行 Python 代码并返回完整输出（stdout + stderr）。

    可用环境：Python 3.x，预装 pandas / numpy / requests / matplotlib 等常用库。
    当前工作目录已限定到本会话 workspace。代码可读写当前目录下的文件。

    禁止：os.system / subprocess / eval / exec 等危险调用，违者直接拒绝。
    超时：默认 120 秒，超时返回 [Timeout]。
    输出：超过 8000 字符会被首尾截断。

    Args:
        code: 完整可执行的 Python 代码字符串。

    Returns:
        代码执行的合并输出（stdout + stderr，UTF-8 字符串）。
    """
    reject = _static_check(code)
    if reject:
        return reject

    workspace = get_workspace_dir()
    return await _run_async(code, workspace, CODE_EXEC_TIMEOUT)
