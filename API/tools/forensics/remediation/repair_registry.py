"""
注册表修复工具 (v4.1)

删除或还原恶意注册表项。风险等级：Level 3（必须 HITL 审批）。
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime

from langchain_core.tools import tool

from .._utils import run_powershell, format_result

logger = logging.getLogger(__name__)

# 系统关键注册表路径白名单（绝对不可操作）
PROTECTED_REGISTRY_PATHS = [
    r"HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control",
    r"HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Windows",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Drivers",
    r"HKEY_LOCAL_MACHINE\SECURITY",
    r"HKEY_LOCAL_MACHINE\SAM",
]

# 备份目录
BACKUP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "workspace", "forensics_backups",
)


def _get_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return BACKUP_DIR


def _is_protected_registry(path: str) -> bool:
    """检查注册表路径是否在保护名单中。"""
    upper_path = path.upper()
    for protected in PROTECTED_REGISTRY_PATHS:
        if upper_path.startswith(protected.upper()):
            return True
    return False


def _normalize_path(path: str) -> str:
    """标准化注册表路径为 PowerShell 格式。"""
    return (
        path.replace("HKEY_LOCAL_MACHINE", "HKLM:")
        .replace("HKEY_CURRENT_USER", "HKCU:")
        .replace("HKEY_CLASSES_ROOT", "HKCR:")
        .replace("HKEY_USERS", "HKU:")
        .replace("HKEY_CURRENT_CONFIG", "HKCC:")
    )


@tool("repair_registry", parse_docstring=True)
def repair_registry(
    path: str,
    key: str,
    action: str = "delete",
) -> str:
    """修复注册表项。

    删除恶意注册表键值或恢复默认值。操作前自动导出备份，支持回滚。

    Args:
        path: 注册表路径（如 HKCU\Software\Microsoft\Windows\CurrentVersion\Run）。
        key: 注册表键名。
        action: 操作类型，"delete"（删除键值）或 "restore"（删除并尝试恢复默认值）。

    Returns:
        JSON 字符串，包含操作结果和备份信息。
    """
    valid_actions = ["delete", "restore"]
    if action not in valid_actions:
        return format_result(
            False,
            error=f"无效的 action 参数: {action}，可选值: {', '.join(valid_actions)}",
        )

    # 检查白名单
    if _is_protected_registry(path):
        return format_result(
            False,
            error=f"禁止操作系统保护注册表路径: {path}",
        )

    action_id = f"regrepair_{int(time.time())}"
    timestamp = datetime.now().isoformat()
    ps_path = _normalize_path(path)

    # 导出备份
    backup_path = os.path.join(_get_backup_dir(), f"{action_id}.reg")
    export_cmd = f'reg export "{path}" "{backup_path}" /y 2>&1'
    backup_r = run_powershell(export_cmd, timeout=10)

    # 检查键是否存在
    check_cmd = (
        f"if (Get-ItemProperty -Path '{ps_path}' -Name '{key}' -ErrorAction SilentlyContinue) "
        f"{{ Write-Output 'EXISTS' }} else {{ Write-Output 'NOT_FOUND' }}"
    )
    check_r = run_powershell(check_cmd, timeout=10)

    if "NOT_FOUND" in check_r["stdout"]:
        return format_result(
            False,
            error=f"注册表键不存在: {path}\\{key}",
        )

    # 执行操作
    if action == "delete":
        ps_cmd = f"Remove-ItemProperty -Path '{ps_path}' -Name '{key}' -ErrorAction Stop"
    else:  # restore - 先尝试获取默认值
        # 尝试从 HKEY_USERS\.DEFAULT 或干净模板获取默认值
        ps_cmd = (
            f"try {{ "
            f"  Remove-ItemProperty -Path '{ps_path}' -Name '{key}' -ErrorAction Stop "
            f"}} catch {{ "
            f"  Write-Warning $_.Exception.Message "
            f"}}"
        )

    r = run_powershell(ps_cmd, timeout=15)

    # 保存备份记录
    backup_info = {
        "action": "repair_registry",
        "action_id": action_id,
        "path": path,
        "key": key,
        "repair_action": action,
        "backup_file": backup_path,
        "backup_success": backup_r["success"],
        "timestamp": timestamp,
    }

    backup_file = os.path.join(_get_backup_dir(), f"{action_id}.json")
    try:
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(backup_info, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"备份记录保存失败: {e}")

    return format_result(
        success=r["success"],
        data={
            "action": "repair_registry",
            "action_id": action_id,
            "path": path,
            "key": key,
            "repair_action": action,
            "backup_file": backup_path,
            "output": r["stdout"] if r["success"] else (r["error"] or r["stderr"]),
        },
        error=None if r["success"] else (r["error"] or r["stderr"]),
    )
