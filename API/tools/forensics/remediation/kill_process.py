"""
进程终止工具 (v4.1)

终止可疑进程。风险等级：Level 3（必须 HITL 审批）。
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

# 系统关键进程白名单（绝对不可终止）
PROTECTED_PROCESSES = {
    "system", "system idle process", "svchost.exe", "lsass.exe",
    "csrss.exe", "smss.exe", "winlogon.exe", "services.exe",
    "wininit.exe", "dwm.exe", "explorer.exe", "csrss.exe",
    "spoolsv.exe", "taskhostw.exe", "audiodg.exe",
}

# 备份目录
BACKUP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "workspace", "forensics_backups",
)


def _get_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return BACKUP_DIR


@tool("kill_process", parse_docstring=True)
def kill_process(
    pid: int,
    force: bool = True,
) -> str:
    """终止指定进程。

    执行前自动备份进程信息，支持后续审计和回滚查询。

    Args:
        pid: 要终止的进程 ID（必须 > 4，System 进程不可终止）。
        force: 是否强制终止，默认 True。

    Returns:
        JSON 字符串，包含操作结果和回滚信息。
    """
    if pid <= 4:
        return format_result(
            False,
            error=f"禁止终止 PID={pid}（系统核心进程，PID <= 4 受保护）",
        )

    # 获取进程信息以便备份和审计
    ps_info = (
        "Get-Process -Id {pid} -ErrorAction SilentlyContinue | "
        "Select-Object ProcessName,Id,Path,StartTime,CPU,WorkingSet | "
        "ConvertTo-Json"
    ).format(pid=pid)

    info_r = run_powershell(ps_info, timeout=10)

    process_name = f"PID_{pid}"
    process_path = ""

    if info_r["success"] and info_r["stdout"]:
        try:
            info = json.loads(info_r["stdout"])
            if isinstance(info, dict):
                process_name = info.get("ProcessName", process_name)
                process_path = info.get("Path", "")
        except json.JSONDecodeError:
            pass

    # 检查白名单
    name_lower = process_name.lower()
    for protected in PROTECTED_PROCESSES:
        if protected in name_lower or name_lower == protected:
            return format_result(
                False,
                error=f"禁止终止系统保护进程: {process_name}（白名单保护）",
            )

    # 备份进程信息
    action_id = f"kill_{pid}_{int(time.time())}"
    backup_info = {
        "action": "kill_process",
        "action_id": action_id,
        "pid": pid,
        "process_name": process_name,
        "process_path": process_path,
        "timestamp": datetime.now().isoformat(),
        "force": force,
        "backup_note": "进程已终止，无法自动恢复。如需恢复，可能需要重新启动相关服务或程序。",
    }

    backup_file = os.path.join(_get_backup_dir(), f"{action_id}.json")
    try:
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(backup_info, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"备份失败: {e}")

    # 执行终止
    force_flag = " /F" if force else ""
    cmd = f"taskkill /PID {pid}{force_flag}"
    r = run_powershell(cmd, timeout=30)

    success = r["success"]

    return format_result(
        success=success,
        data={
            "action": "kill_process",
            "action_id": action_id,
            "pid": pid,
            "process_name": process_name,
            "exit_code": r["exit_code"],
            "force": force,
            "output": r["stdout"] if success else r["stderr"],
        },
        error=None if success else (r["error"] or r["stderr"]),
    )
