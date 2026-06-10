"""
文件隔离工具 (v4.1)

将可疑文件隔离到安全目录。风险等级：Level 3（必须 HITL 审批）。
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
from datetime import datetime
from typing import Optional

from langchain_core.tools import tool

from .._utils import run_powershell, format_result

logger = logging.getLogger(__name__)

# 系统目录白名单（绝对不可操作）
PROTECTED_PATHS = [
    r"C:\Windows\System32",
    r"C:\Windows\SysWOW64",
    r"C:\Windows\Boot",
    r"C:\Windows\WinSxS",
    r"C:\Program Files\Windows Defender",
    r"C:\Windows\System32\drivers",
]

# 隔离目录
QUARANTINE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "workspace", "quarantine",
)

# 备份目录
BACKUP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "workspace", "forensics_backups",
)


def _get_quarantine_dir():
    os.makedirs(QUARANTINE_DIR, exist_ok=True)
    return QUARANTINE_DIR


def _get_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return BACKUP_DIR


def _calc_sha256(file_path: str) -> Optional[str]:
    """计算文件 SHA256。"""
    try:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        logger.warning(f"SHA256 计算失败: {e}")
        return None


def _is_protected_path(file_path: str) -> bool:
    """检查是否在系统保护路径内。"""
    normalized = os.path.normpath(file_path).lower()
    for protected in PROTECTED_PATHS:
        if normalized.startswith(protected.lower()):
            return True
    return False


@tool("quarantine_file", parse_docstring=True)
def quarantine_file(
    file_path: str,
) -> str:
    """隔离可疑文件到安全目录。

    计算 SHA256 -> 移动到隔离区 -> 原位置写入空文件占位。
    支持后续回滚恢复。

    Args:
        file_path: 文件的绝对路径。

    Returns:
        JSON 字符串，包含操作结果、SHA256 和回滚信息。
    """
    # 路径规范化
    file_path = os.path.normpath(file_path)

    # 检查文件是否存在
    if not os.path.exists(file_path):
        return format_result(False, error=f"文件不存在: {file_path}")

    # 检查白名单
    if _is_protected_path(file_path):
        return format_result(
            False,
            error=f"禁止操作系统保护目录中的文件: {file_path}",
        )

    # 获取文件信息
    file_name = os.path.basename(file_path)
    file_size = 0
    try:
        file_size = os.path.getsize(file_path)
    except OSError:
        pass

    # 计算 SHA256
    sha256 = _calc_sha256(file_path)
    if not sha256:
        return format_result(False, error="无法计算文件 SHA256，操作中止")

    # 创建操作 ID 和备份记录
    action_id = f"quarantine_{int(time.time())}"
    timestamp = datetime.now().isoformat()

    # 隔离文件
    quarantine_path = os.path.join(_get_quarantine_dir(), f"{sha256}_{file_name}")

    try:
        # 移动文件到隔离区
        shutil.move(file_path, quarantine_path)

        # 在原位置创建空文件占位（标记已被隔离）
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# QUARANTINED by DeepInvestigate\n")
            f.write(f"# Action: {action_id}\n")
            f.write(f"# SHA256: {sha256}\n")
            f.write(f"# Original file moved to: {quarantine_path}\n")
            f.write(f"# Timestamp: {timestamp}\n")

        success = True
        error = None
    except PermissionError:
        # Python 文件操作可能失败，尝试通过 PowerShell
        ps_cmd = (
            f"Move-Item -Path '{file_path}' -Destination '{quarantine_path}' -Force; "
            f"Set-Content -Path '{file_path}' -Value "
            f"'# QUARANTINED by DeepInvestigate`n# Action: {action_id}`n# SHA256: {sha256}' -Encoding UTF8"
        )
        r = run_powershell(ps_cmd, timeout=30)
        success = r["success"]
        error = r["error"] if not success else None
    except Exception as e:
        success = False
        error = f"{type(e).__name__}: {e}"

    # 保存备份记录
    backup_info = {
        "action": "quarantine_file",
        "action_id": action_id,
        "original_path": file_path,
        "quarantine_path": quarantine_path,
        "file_name": file_name,
        "file_size": file_size,
        "sha256": sha256,
        "timestamp": timestamp,
    }

    backup_file = os.path.join(_get_backup_dir(), f"{action_id}.json")
    try:
        with open(backup_file, "w", encoding="utf-8") as f:
            import json
            json.dump(backup_info, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"备份记录保存失败: {e}")

    return format_result(
        success=success,
        data={
            "action": "quarantine_file",
            "action_id": action_id,
            "sha256": sha256,
            "original_path": file_path,
            "quarantine_path": quarantine_path,
            "file_name": file_name,
            "file_size": file_size,
        },
        error=error,
    )
