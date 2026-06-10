"""
取证工具公共工具函数

提供统一的 subprocess 执行、编码处理、错误处理。
支持异步安全调用，不阻塞事件循环。
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# PowerShell 执行超时（秒）
DEFAULT_TIMEOUT = 30

# PowerShell 编码模板：强制 UTF-8 输出，避免 GBK 乱码
PS_TEMPLATE = (
    'powershell -NoProfile -ExecutionPolicy Bypass -Command '
    '"$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8; {cmd}"'
)


def _run_powershell_sync(command: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """同步执行 PowerShell（在线程池中调用）。"""
    full_cmd = PS_TEMPLATE.replace("{cmd}", command)
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode,
            "error": None,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "error": f"命令执行超时（>{timeout}秒）",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "error": "PowerShell 不可用",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "error": f"{type(e).__name__}: {e}",
        }


async def _run_powershell_async(command: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """异步执行 PowerShell（不阻塞事件循环）。"""
    loop = asyncio.get_running_loop()
    # 在线程池中运行同步 subprocess，避免阻塞事件循环
    return await loop.run_in_executor(
        None, _run_powershell_sync, command, timeout
    )


def run_powershell(command: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """执行 PowerShell 命令并返回解析结果。

    优先使用异步版本；若不在 async 上下文中，回退到同步调用。

    Args:
        command: PowerShell 命令文本（不含外层 powershell 调用）。
        timeout: 超时秒数。

    Returns:
        {"success": bool, "stdout": str, "stderr": str, "exit_code": int, "error": Optional[str]}
    """
    try:
        loop = asyncio.get_running_loop()
        # 我们在 async 上下文中，不能用同步 subprocess.run 阻塞事件循环
        # 但 run_powershell 本身是同步函数（被同步 tool 调用），
        # LangGraph ToolNode 会在线程池中执行同步 tool，
        # 所以这里事件循环应该是安全的，直接用同步版本
        return _run_powershell_sync(command, timeout)
    except RuntimeError:
        # 不在 async 上下文中，直接用同步版本
        return _run_powershell_sync(command, timeout)


def safe_json_parse(text: str) -> dict:
    """安全解析 JSON，失败时返回原始文本包裹。"""
    if not text:
        return {"parse_error": True, "raw": ""}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试提取 JSON 块（PowerShell 有时会在 JSON 前后加文本）
        import re
        match = re.search(r'\{.*\}|\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {"parse_error": True, "raw": text[:2000]}


def format_result(success: bool, data: dict = None, error: str = None) -> str:
    """统一格式化工具返回结果为 JSON 字符串。"""
    result = {"success": success}
    if data is not None:
        result["data"] = data
    if error is not None:
        result["error"] = error
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)